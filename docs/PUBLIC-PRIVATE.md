# What stays private and what goes public

Rule: **private information stays in the private working space; public information lives in this repository.** The preparation history on `main` is local only. The public repository gets a single clean commit.

| Public (in this repository) | Private (never copied here) |
|---|---|
| Code, tests, scripts, docs | Ticket numbers, agent/orchestrator names, internal channel and tool names |
| The 26-tool set (`TOOLS.json`), the scoring rules, the 206-prompt benchmark | The frozen 180-request yardstick, training data, raw teacher outputs, rejected rows, spend and cost figures |
| Result files in public form (no generated code, no paths) | Raw run logs, generated code per prompt, machine paths and server names |
| Model cards and checksums; weights go to Hugging Face, not git | Internal run tags (v2, v3, r1 ...), adapter folders, intermediate GGUFs |
| Hyperparameters (`train/configs/`) | Credentials, API keys, tokens, hostnames, addresses, e-mail addresses, personal home paths |
| Public release numbers (v0.1, v0.2 ...) | The mapping from release numbers to internal runs |

## How it is enforced
1. `scripts/scan_private.py` (also run by CI, `promote.py` and `first_push.sh`) fails on secrets, internal hosts and addresses, personal paths, ticket references and e-mail addresses. It never prints matched text. Binary files are read too (a `.blend` stores the folder it was saved in, an FBX the path of its source file): the readable strings of scene files, exported models and pictures are searched, a compressed `.blend` is opened first, and one that cannot be opened is a finding.
2. `.gitignore` keeps weights, `results/`, `.env` and keys out.
3. `scripts/first_push.sh --author "Name <mail>"` creates the branch `public` with ONE commit whose author and committer are the public identity given (never the identity configured on the machine), after the scan and the tests have passed on a copy of exactly the tree that is published; it never adds a remote, never pushes. The maintainers run the printed push commands.
4. Public names: the product is Maris3D; the v0.1 model is `Maris3D-SLM-Blender-0.5B` (Hugging Face org `slm4apps`, repository `Maris3D-Blender`; versions are git tags such as `v0.1.0`). Internal tags never appear in names, cards or GGUF metadata (`promote.py` has a gate for the GGUF header). The earlier `Maris3D-SLM-Blender-1.5B` / `Maris3D-SLM-Blender-0.5B` development names belong to the superseded line and appear only in the history sections.
5. The private workspace is read-only for this project: numbers are copied into `release/results/` with the source described generically.
