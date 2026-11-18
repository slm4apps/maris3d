#!/usr/bin/env python3
"""Mac copy (adds --device mps, staged lines E5/P4). LoRA trainer for the head-to-head (Linux, PEFT, fp16 on the GTX 980M; no truncation).

- Loss only on assistant turns (spans found by rendering message prefixes); an assistant turn with "weight": 0 is context only.
- lm_head applied only to supervised positions, in chunks (the 248k vocab makes full logits too big).
- Gradient checkpointing, batch 1, grad accumulation ACCUM; one "update" = one optimizer step.
- Saves a PEFT adapter at each --save-every updates, and a JSONL log with seconds per update and peak GPU memory.

usage: train_lora.py --base <dir> --rows <jsonl> --out <dir> --updates N [--save-every K] [--seed S] [--max-len L]
"""
import argparse, json, os, random, time
import torch
import torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import LoraConfig, get_peft_model

p = argparse.ArgumentParser()
p.add_argument("--base", required=True)
p.add_argument("--rows", required=True)
p.add_argument("--out", required=True)
p.add_argument("--updates", type=int, default=100)
p.add_argument("--save-every", type=int, default=0)
p.add_argument("--accum", type=int, default=4)
p.add_argument("--lr", type=float, default=1e-4)
p.add_argument("--rank", type=int, default=8)
p.add_argument("--alpha", type=int, default=160)
p.add_argument("--chunk", type=int, default=256)
p.add_argument("--max-len", type=int, default=4096)
p.add_argument("--seed", type=int, default=367)
p.add_argument("--first-layer", type=int, default=8)
p.add_argument("--embed", type=int, default=0)
p.add_argument("--resume", default="")
p.add_argument("--train-tag-rows", action="store_true", help="opt-in: train a small delta on the <tool_call>/</tool_call> embedding rows (tied lm_head), saved as tag_rows.pt next to each adapter")
p.add_argument("--device", default="cuda", choices=["cuda", "cpu", "mps"])
p.add_argument("--dtype", default="fp16", choices=["fp16", "fp32"])
args = p.parse_args()
os.makedirs(args.out, exist_ok=True)
torch.manual_seed(args.seed)

tok = AutoTokenizer.from_pretrained(args.base)

def as_ids(x):
    return x["input_ids"] if hasattr(x, "keys") else x

def encode(r):
    """Return (input_ids, labels); labels = -100 outside assistant turns. Never truncates."""
    msgs, tools = r["messages"], r.get("tools")
    full = as_ids(tok.apply_chat_template(msgs, tools=tools, tokenize=True))
    labels = [-100] * len(full)
    for i, m in enumerate(msgs):
        if m["role"] != "assistant" or m.get("weight", 1) == 0:  # weight 0: kept as context, not learned (lazy "Done." turns)
            continue
        pre = as_ids(tok.apply_chat_template(msgs[:i], tools=tools, tokenize=True, add_generation_prompt=True))
        upto = as_ids(tok.apply_chat_template(msgs[: i + 1], tools=tools, tokenize=True))
        assert full[: len(upto)] == upto, "template prefix mismatch"
        for j in range(len(pre), len(upto)):
            labels[j] = full[j]
    return full, labels

import hashlib, pickle
cache = os.path.join(args.out, "encoded.pkl")
src_sha = hashlib.sha256(open(args.rows, "rb").read()).hexdigest()
if os.path.exists(cache) and pickle.load(open(cache, "rb"))["sha"] == src_sha:
    encoded = pickle.load(open(cache, "rb"))["rows"]
else:
    encoded = []
    with open(args.rows) as f:
        for k, line in enumerate(f):
            encoded.append(encode(json.loads(line)))
            if k % 500 == 0:
                print(f"encoded {k}", flush=True)
    pickle.dump({"sha": src_sha, "rows": encoded}, open(cache, "wb"))
rows = [(ids, lab) for ids, lab in encoded if len(ids) <= args.max_len]  # longer rows skipped, never cut
print(f"rows usable at max_len {args.max_len}: {len(rows)}", flush=True)
assert rows, "no rows fit"

DT = torch.float16 if args.dtype == "fp16" else torch.float32
model = AutoModelForCausalLM.from_pretrained(args.base, dtype=DT).to(args.device)
model.config.use_cache = False
for prm in model.parameters():
    prm.requires_grad_(False)
targets = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
nl = model.config.num_hidden_layers
if args.embed: targets = targets + ["embed_tokens"]
cfg = LoraConfig(r=args.rank, lora_alpha=args.alpha, lora_dropout=0.0, target_modules=targets, layers_to_transform=list(range(args.first_layer, nl)) if args.first_layer else None, bias="none")
model = get_peft_model(model, cfg)
if args.resume:  # continue from the previous line adapter (staged plan)
    from safetensors.torch import load_file
    from peft import set_peft_model_state_dict
    set_peft_model_state_dict(model, load_file(args.resume + "/adapter_model.safetensors"))
    print("resumed from", args.resume, flush=True)
for prm in model.parameters():
    if prm.requires_grad:
        prm.data = prm.data.float()  # LoRA weights fp32, base fp16
model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
model.enable_input_require_grads()
model.print_trainable_parameters()

inner = model.base_model.model          # causal LM
backbone = inner.model
lm_head = inner.lm_head
params = [prm for prm in model.parameters() if prm.requires_grad]
tag_delta = None
if args.train_tag_rows:
    # Tied embeddings: lm_head is never trained, so a base without <tool_call> rows emits junk. Train a delta for those 2 rows only
    # (added to the input embedding and to the output logits; same shared row). Merge by adding tag_delta to embed_tokens[tag_ids].
    tag_ids = tok.convert_tokens_to_ids(["<tool_call>", "</tool_call>"])
    assert all(isinstance(i, int) and i >= 0 and i != tok.unk_token_id for i in tag_ids), tag_ids
    tag_t = torch.tensor(tag_ids, device=args.device)
    tag_delta = torch.nn.Parameter(torch.zeros(2, inner.config.hidden_size, device=args.device, dtype=torch.float32))
    def _emb_hook(mod, inp, out):
        m = (inp[0].unsqueeze(-1) == tag_t).to(out.dtype)          # (..., 2)
        return out + m @ tag_delta.to(out.dtype)
    backbone.embed_tokens.register_forward_hook(_emb_hook)
    params.append(tag_delta)
    print("train-tag-rows: ids", tag_ids, flush=True)

def save_tag_rows(d):
    if tag_delta is not None:
        torch.save({"ids": tag_ids, "delta": tag_delta.detach().cpu()}, os.path.join(d, "tag_rows.pt"))
opt = torch.optim.AdamW(params, lr=args.lr, weight_decay=0.0)
rng = random.Random(args.seed)
order = list(range(len(rows)))
rng.shuffle(order)
pos = 0

def next_row():
    global pos
    if pos >= len(order):
        rng.shuffle(order)
        pos = 0
    r = rows[order[pos]]
    pos += 1
    return r

def row_loss(ids, lab):
    x = torch.tensor([ids], device=args.device)
    y = torch.tensor(lab[1:], device=args.device)
    h = backbone(input_ids=x).last_hidden_state[0, :-1]
    sel = (y != -100).nonzero(as_tuple=True)[0]
    hs, ys = h[sel], y[sel]
    total = h.new_zeros((), dtype=torch.float32)
    for c in range(0, hs.shape[0], args.chunk):
        hc = hs[c : c + args.chunk]
        logits = lm_head(hc).float()
        if tag_delta is not None:
            logits = logits.index_add(1, tag_t, hc.float() @ tag_delta.t())
        total = total + F.cross_entropy(logits, ys[c : c + args.chunk], reduction="sum")
    return total, int(sel.numel())

log = open(os.path.join(args.out, "train_log.jsonl"), "w")
import resource
if args.device == "cuda":
    torch.cuda.reset_peak_memory_stats()
def peak_mb():
    if args.device == "cuda":
        return round(torch.cuda.max_memory_allocated() / 2**20, 1)
    if args.device == "mps":
        return round(torch.mps.driver_allocated_memory() / 2**20, 1)
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)  # CPU: process max RSS
model.train()
t_start = time.time()
for upd in range(1, args.updates + 1):
    t0 = time.time()
    batch = [next_row() for _ in range(args.accum)]
    ntok = sum(sum(1 for v in lab[1:] if v != -100) for _, lab in batch)
    tot_loss = 0.0
    for ids, lab in batch:
        loss_sum, _ = row_loss(ids, lab)
        (loss_sum / ntok).backward()
        tot_loss += loss_sum.item()
    torch.nn.utils.clip_grad_norm_(params, 1.0)
    opt.step()
    opt.zero_grad(set_to_none=True)
    dt = time.time() - t0
    rec = {"update": upd, "loss": round(tot_loss / ntok, 5), "sec": round(dt, 3),
           "peak_mb": peak_mb(),
           "tokens": sum(len(i) for i, _ in batch)}
    log.write(json.dumps(rec) + "\n"); log.flush()
    if upd <= 3 or upd % 10 == 0:
        print(rec, flush=True)
    if args.save_every and upd % args.save_every == 0:
        model.save_pretrained(os.path.join(args.out, f"checkpoint-{upd}"))
        save_tag_rows(os.path.join(args.out, f"checkpoint-{upd}"))
model.save_pretrained(os.path.join(args.out, "final"))
save_tag_rows(os.path.join(args.out, "final"))
print(f"done updates={args.updates} wall={time.time()-t_start:.1f}s "
      f"peak_mb={peak_mb()}", flush=True)
