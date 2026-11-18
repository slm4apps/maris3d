#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Draw the SVG figures of TECHNICAL-REPORT.md from release/results/*.json and docs/figures/ladder.json (standard library only).

    python3 scripts/make_figures.py          # write docs/figures/*.svg and failure-categories.json
"""
import collections, json, os, re

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
FIG = os.path.join(ROOT, "docs", "figures")
INK, MUTED, GRID = "#1f2937", "#6b7280", "#e5e7eb"
C = {"0.5b": "#d97706", "0.5b+": "#92400e", "1.5b": "#2563eb"}


def load(rel):
    return json.load(open(os.path.join(ROOT, rel)))


def svg(w, h, body, title):
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d" role="img" aria-label="%s" font-family="Helvetica, Arial, sans-serif" font-size="12">\n'
            '<title>%s</title><rect width="100%%" height="100%%" fill="#ffffff"/>\n%s</svg>\n' % (w, h, w, h, title, title, body))


def text(x, y, s, size=12, anchor="start", fill=INK, weight="normal"):
    return '<text x="%s" y="%s" font-size="%s" text-anchor="%s" fill="%s" font-weight="%s">%s</text>\n' % (x, y, size, anchor, fill, weight, s)


def by_level_chart():
    runs = [("Maris3D SLM Blender 0.5B, bare", "0.5b", load("release/results/maris3d-0.5b-v0.1-q8_0.json")),
            ("Maris3D SLM Blender 0.5B, retry loop", "0.5b+", load("release/results/maris3d-0.5b-v0.1-q8_0-repair2.json")),
            ("Maris3D-SLM-Blender-1.5B, bare", "1.5b", load("release/results/maris3d-1.5b-dev-q8_0.json"))]
    W, H, L, T, B = 640, 340, 60, 50, 60
    pw, ph = W - L - 20, H - T - B
    b = text(L, 24, "Pass rate by level, 206-prompt benchmark", 15, weight="bold")
    for g in range(0, 101, 20):
        y = T + ph - ph * g / 100
        b += '<line x1="%d" x2="%d" y1="%.1f" y2="%.1f" stroke="%s"/>\n' % (L, W - 20, y, y, GRID) + text(L - 8, y + 4, "%d%%" % g, 11, "end", MUTED)
    gw = pw / 4
    bw = gw / 4.2
    for li, lv in enumerate(["1", "2", "3", "4"]):
        for ri, (label, key, r) in enumerate(runs):
            v = r["summary"]["by_level"][lv]
            x = L + li * gw + (ri + 0.5) * bw + 6
            h = ph * v / 100
            b += '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s"/>\n' % (x, T + ph - h, bw - 3, h, C[key])
            b += text(x + (bw - 3) / 2, T + ph - h - 4, "%g" % v, 10, "middle")
        b += text(L + li * gw + gw / 2, H - B + 18, "L%s" % lv, 12, "middle")
    for i, (label, key, _) in enumerate(runs):
        b += '<rect x="%d" y="%d" width="10" height="10" fill="%s"/>' % (L + i * 200, H - 22, C[key]) + text(L + i * 200 + 15, H - 13, label, 11)
    open(os.path.join(FIG, "pass-by-level.svg"), "w").write(svg(W, H, b, "Pass rate by level for the two sizes"))


def ladder_chart():
    steps = load("docs/figures/ladder.json")["steps"]
    W, rowh, L, T = 720, 30, 300, 44
    H = T + rowh * len(steps) + 20
    b = text(10, 24, "Pass % on the 206 prompts along the development", 15, weight="bold")
    for i, s in enumerate(steps):
        y = T + i * rowh
        col = C["1.5b"] if s["label"].startswith("1.5B") else C["0.5b"]
        w = (W - L - 60) * s["pass_pct"] / 100
        b += text(L - 8, y + 16, s["label"], 11, "end") + '<rect x="%d" y="%d" width="%.1f" height="18" fill="%s"/>\n' % (L, y + 3, w, col)
        b += text(L + w + 6, y + 16, "%g%%" % s["pass_pct"], 11)
    open(os.path.join(FIG, "ladder.svg"), "w").write(svg(W, H, b, "Pass rate along the development of the models"))


def categories(rows):
    rules = [("object count wrong", r"mesh count"), ("size, extent or face count outside range", r"top z|extent|dim\[|scale/dims|faces|vertices"),
             ("material missing or wrong", r"material"), ("position or rotation wrong", r"rotated|nothing at"),
             ("modifier missing", r"modifier"), ("world, scene settings, animation or markers", r"world|animat|keyframe|frame_|engine|resolution|markers"),
             ("curve or text object missing", r"curve|text object")]
    out = collections.Counter()
    for r in rows:
        if r["passed"]:
            continue
        if not r["ran"]:
            out["script did not run"] += 1
            continue
        f = r["fails"][0]
        out[next((n for n, rx in rules if re.search(rx, f)), "other")] += 1
    return out


def failure_chart():
    res = load("release/results/maris3d-1.5b-dev-q8_0.json")
    cats = categories(res["rows"])
    json.dump({"source": "release/results/maris3d-1.5b-dev-q8_0.json", "note": "first failed check of each failed prompt, grouped by its wording (coarse)", "counts": dict(cats.most_common())},
              open(os.path.join(FIG, "failure-categories.json"), "w"), indent=1)
    items = cats.most_common()
    W, rowh, L, T = 640, 28, 300, 44
    H = T + rowh * len(items) + 16
    b = text(10, 24, "Maris3D-SLM-Blender-1.5B: why %d of 206 prompts failed" % sum(cats.values()), 15, weight="bold")
    mx = max(v for _, v in items)
    for i, (k, v) in enumerate(items):
        y = T + i * rowh
        w = (W - L - 60) * v / mx
        b += text(L - 8, y + 15, k, 11, "end") + '<rect x="%d" y="%d" width="%.1f" height="16" fill="%s"/>\n' % (L, y + 2, w, C["1.5b"]) + text(L + w + 6, y + 15, str(v), 11)
    open(os.path.join(FIG, "failure-categories.svg"), "w").write(svg(W, H, b, "Failure categories of the 1.5B model"))


def pipeline():
    boxes = ["request (text)", "Maris3D\nJSON tool calls", "compile_calls\nbpy script", "headless Blender\nscene dump", "scene check\npass / fail"]
    W, H = 760, 150
    b = text(10, 24, "From request to verified scene", 15, weight="bold")
    for i, t in enumerate(boxes):
        x = 10 + i * 148
        b += '<rect x="%d" y="50" width="124" height="54" rx="6" fill="#f3f4f6" stroke="#9ca3af"/>\n' % x
        for j, line in enumerate(t.split("\n")):
            b += text(x + 62, 74 + j * 15 - (7 if "\n" in t else 0) + 7, line, 11, "middle")
        if i < len(boxes) - 1:
            b += '<line x1="%d" y1="77" x2="%d" y2="77" stroke="%s" stroke-width="2"/><polygon points="%d,72 %d,77 %d,82" fill="%s"/>\n' % (x + 124, x + 146, INK, x + 146, x + 152, x + 146, INK)
    b += text(10, 135, "On a failed check the failed message can go back to the model (retry loop, up to 2 times).", 11, fill=MUTED)
    open(os.path.join(FIG, "pipeline.svg"), "w").write(svg(W, H, b, "Pipeline from request to verified scene"))


def comparison_180_chart():
    d = load("docs/figures/comparison-180.json")
    models = d["models"]
    W, rowh, L, T = 800, 46, 360, 64
    H = T + rowh * len(models) + 44
    b = text(10, 24, "Pass and usable rate, 180-request Blender benchmark", 15, weight="bold")
    b += text(10, 42, "real agent loop, native tool calls; every scene executed and checked in headless Blender (Nov 2026)", 10, fill=MUTED)
    pw = W - L - 90
    for g in range(0, 101, 20):
        x = L + pw * g / 100.0
        b += '<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="%s"/>\n' % (x, T - 4, x, H - 44, GRID) + text(x, H - 30, "%d%%" % g, 10, "middle", MUTED)
    CP, CU = "#d97706", "#2563eb"
    for i, m in enumerate(models):
        y = T + i * rowh
        w = "bold" if m.get("ours") else "normal"
        b += text(L - 8, y + 23, m["name"], 11, "end", INK, w)
        wp, wu = pw * m["pass_pct"] / 100.0, pw * m["usable_pct"] / 100.0
        b += '<rect x="%d" y="%d" width="%.1f" height="12" fill="%s"/>\n' % (L, y + 6, wp, CP) + text(L + wp + 5, y + 16, "%g" % m["pass_pct"], 10)
        b += '<rect x="%d" y="%d" width="%.1f" height="12" fill="%s"/>\n' % (L, y + 22, wu, CU) + text(L + wu + 5, y + 32, "%g" % m["usable_pct"], 10)
    b += '<rect x="%d" y="%d" width="10" height="10" fill="%s"/>' % (L, H - 18, CP) + text(L + 15, H - 10, "pass % (every check holds)", 10)
    b += '<rect x="%d" y="%d" width="10" height="10" fill="%s"/>' % (L + 220, H - 18, CU) + text(L + 235, H - 10, "usable % (pass or small fixes)", 10)
    open(os.path.join(FIG, "comparison-180.svg"), "w").write(svg(W, H, b, "Maris3D SLM Blender 0.5B versus untrained base models on the 180-request benchmark"))


def external_chart():
    d = load("docs/figures/external-benchmarks.json")
    tests, names = d["tests"], list(d["tests"][0]["models"])
    cols = {"Maris3D SLM Blender 0.5B": "#d97706", "Qwen2.5-Coder-0.5B (untrained)": "#9ca3af", "Qwen3.5-0.8B (untrained)": "#2563eb"}
    W, H, L, T, B = 720, 430, 56, 64, 118
    pw, ph = W - L - 20, H - T - B
    b = text(L - 36, 24, "Public tool-calling benchmarks, identical settings", 15, weight="bold")
    b += text(L - 36, 42, "llama-server, greedy decoding, native tool calls, 4 threads (Nov 2026)", 10, fill=MUTED)
    for g in range(0, 101, 20):
        y = T + ph - ph * g / 100.0
        b += '<line x1="%d" x2="%d" y1="%.1f" y2="%.1f" stroke="%s"/>\n' % (L, W - 20, y, y, GRID) + text(L - 8, y + 4, "%d%%" % g, 11, "end", MUTED)
    gw = pw / len(tests)
    bw = gw / (len(names) + 1.6)
    for ti, t in enumerate(tests):
        for ni, n in enumerate(names):
            v = t["models"][n]
            x = L + ti * gw + (ni + 0.6) * bw + 4
            h = ph * v / 100.0
            b += '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s"/>\n' % (x, T + ph - h, bw - 3, h, cols[n])
            b += text(x + (bw - 3) / 2, T + ph - h - 4, "%g" % v, 10, "middle")
        b += text(L + ti * gw + gw / 2, T + ph + 16, t["name"], 10.5, "middle")
    for i, n in enumerate(names):
        b += '<rect x="%d" y="%d" width="10" height="10" fill="%s"/>' % (L - 36 + i * 235, H - 88, cols[n]) + text(L - 36 + i * 235 + 15, H - 79, n, 10.5)
    for i, note in enumerate(d["notes"][:3]):
        b += text(L - 36, H - 46 + i * 13, "- " + note[:115], 10, fill=MUTED)
    open(os.path.join(FIG, "external-benchmarks.svg"), "w").write(svg(W, H, b, "Maris3D SLM Blender 0.5B on public tool-calling benchmarks versus untrained models"))


if __name__ == "__main__":
    os.makedirs(FIG, exist_ok=True)
    by_level_chart(); ladder_chart(); failure_chart(); pipeline(); comparison_180_chart(); external_chart()
    print("figures written to docs/figures")
