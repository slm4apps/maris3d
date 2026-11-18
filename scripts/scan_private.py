#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fail when the tree contains secrets, private addresses, personal paths, ticket references or e-mail addresses.

    python3 scripts/scan_private.py                 # scan every file git would commit (tracked + untracked, minus .gitignore)
    python3 scripts/scan_private.py --walk          # scan all files under the root, ignoring git
    python3 scripts/scan_private.py path1 path2     # scan given files
    python3 scripts/scan_private.py --json

Used by CI, by scripts/promote.py and by scripts/first_push.sh. Findings never print the matched text, only rule, file and line, so the
scan output itself is safe to paste. A line containing the marker `scan: allow` is skipped (use it for the rule definitions and
test fixtures only, never for real data). Exit code 0 = clean, 1 = findings, 2 = usage error.
The patterns are assembled from pieces so that this file does not match its own rules."""
import argparse, json, os, re, subprocess, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
J = "".join


def R(*parts, flags=re.I):
    return re.compile(J(parts), flags)


RULES = [
    # --- secrets and tokens
    ("secret:gitlab-token", R("gl", "pat-[A-Za-z0-9_-]{10,}", flags=0)),
    ("secret:github-token", R("(?:gh", "p_|gho_|ghs_|ghu_|github_", "pat_)[A-Za-z0-9_]{20,}", flags=0)),
    ("secret:openai-style-key", R(r"\bs", "k-[A-Za-z0-9_-]{20,}", flags=0)),
    ("secret:aws-key-id", R(r"\bAK", "IA[0-9A-Z]{16}\\b", flags=0)),
    ("secret:huggingface-token", R(r"\bh", "f_[A-Za-z0-9]{30,}", flags=0)),
    ("secret:slack-token", R(r"\bxo", "x[abp]-[A-Za-z0-9-]{10,}", flags=0)),
    ("secret:bearer-token", R(r"\bBear", "er\\s+[A-Za-z0-9._~+/=-]{16,}")),
    ("secret:private-key-header", R("-----BEGIN ", "[A-Z ]*PRIVATE KEY-----", flags=0)),
    ("secret:assigned-credential", R(r"\b(?:pass", "word|passwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token)\\b\\s*[:=]\\s*[\"'][^\"'\\s]{6,}[\"']")),
    ("secret:azure-or-openai-key", R(r"(?:az", "ure|open", "ai)[^\\n]{0,60}(?:key|secret)[^\\n]{0,20}[:=]\\s*[\"']?[A-Za-z0-9]{24,}")),
    ("secret:webhook", R(r"(?:discord(?:app)?\.com/api/web", "hooks|hooks\\.sla", "ck\\.com/services)")),
    # --- private network addresses
    ("internal:vpn-address", R(r"\b100\.64\.\d+\.\d+")),
    ("internal:private-address", R(r"\b10\.100\.\d+\.\d+")),
    # --- personal paths
    ("path:home-directory", R(r"(?:/Us", "ers/[A-Za-z0-9._-]+|C:\\\\Us", "ers\\\\|/home/(?!runner\\b)[A-Za-z0-9._-]+)")),
    # --- ticket references
    ("ticket:hash-number", re.compile(r"(?<![\w&/#-])#\d{2,4}(?![\w.])")),
    ("ticket:task-tag", R(r"\btask-\d{2,4}\b")),
    ("ticket:issue-url", R(r"/issues/\d+")),
    # --- e-mail addresses (GitHub noreply addresses are allowed)
    ("email:address", re.compile(r"\b[A-Za-z0-9._%+-]+@(?!users\.noreply\.github\.com)[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b")),
]
# Names that are private in themselves (a company, a machine, a workspace, a user name) cannot be
# spelled in a public file, not even to search for them. The maintainers keep those rules in a
# file that is not part of the public tree; the scanner adds them when the file is there.
PRIVATE_RULES = os.path.join(ROOT, "internal", "release", "scan-rules-private.json")
if os.path.exists(PRIVATE_RULES):
    with open(PRIVATE_RULES) as _f:
        RULES += [(_name, re.compile(_pattern, re.I)) for _name, _pattern in json.load(_f)]
ALLOW_MARK = "scan: " + "allow"
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "build", "dist"}
INTERNAL = "internal"  # maintainer-only working notes: tracked on main, never part of the public release commit (see scripts/first_push.sh)
MAX_BYTES = 200_000_000     # above this only model weights, which are not part of the tree


def scan_text(text, name="<text>"):
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        if ALLOW_MARK in line:
            continue
        for rule, rx in RULES:
            if rx.search(line):
                out.append({"file": name, "line": n, "rule": rule})
    return out


ZSTD, GZIP = b"\x28\xb5\x2f\xfd", b"\x1f\x8b"


def _inflate(raw):
    """The bytes inside a compressed file (a .blend is saved zstd- or gzip-compressed), or None
    when this machine cannot read them."""
    if raw[:4] == ZSTD:
        try:
            from compression import zstd                      # Python 3.14+
            return zstd.decompress(raw)
        except Exception:
            pass
        try:
            return subprocess.run(["zstd", "-dc"], input=raw, capture_output=True, check=True).stdout
        except (OSError, subprocess.CalledProcessError):
            return None
    if raw[:2] == GZIP:
        import gzip
        try:
            return gzip.decompress(raw)
        except Exception:
            return None
    return raw


def scan_binary(raw, rel):
    """A scene file, an exported model or a picture can carry the path it was saved from, a user
    name or a host name (an FBX stores the path of the .blend it came from). Its readable strings
    (runs of 8 or more printable characters) are searched with every rule except the ticket and
    e-mail ones, which random bytes match by chance. A compressed file that cannot be opened here
    is a finding: nothing goes out unread."""
    data = _inflate(raw)
    if data is None:
        return [{"file": rel, "line": 0, "rule": "unread:compressed-file"}]
    text = b"\n".join(re.findall(rb"[\x20-\x7e]{8,}", data)).decode("ascii")
    return [{"file": rel, "line": 0, "rule": rule} for rule, rx in RULES
            if not rule.startswith(("ticket:", "email:")) and rx.search(text)]


def scan_file(path, rel):
    out = [{"file": rel, "line": 0, "rule": r} for r, rx in RULES if rx.search(rel)]  # file names count too
    try:
        if os.path.getsize(path) > MAX_BYTES:
            return out + [{"file": rel, "line": 0, "rule": "skip:too-large"}]
        with open(path, "rb") as f:
            raw = f.read()
    except OSError:
        return out
    if b"\0" in raw[:4096] or raw[:4] == ZSTD or raw[:2] == GZIP:  # binary
        return out + scan_binary(raw, rel)
    return out + scan_text(raw.decode("utf-8", "replace"), rel)


def git_files(root):
    try:
        r = subprocess.run(["git", "-C", root, "ls-files", "-z", "--cached", "--others", "--exclude-standard"], capture_output=True, check=True)
        files = [p for p in r.stdout.decode().split("\0") if p]
        return [p for p in files if os.path.exists(os.path.join(root, p)) and p.split("/")[0] != INTERNAL]
    except (OSError, subprocess.CalledProcessError):
        return None


def walk_files(root):
    out = []
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS and not (d == root and x == INTERNAL)]
        out += [os.path.relpath(os.path.join(d, f), root) for f in files]
    return out


def scan_tree(root=ROOT, files=None, walk=False):
    files = files if files is not None else ((None if walk else git_files(root)) or walk_files(root))
    findings = []
    for rel in sorted(files):
        findings += scan_file(os.path.join(root, rel), rel)
    return files, findings


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--root", default=ROOT)
    ap.add_argument("--walk", action="store_true", help="ignore git, scan every file under root")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    files, findings = scan_tree(a.root, a.paths or None, a.walk)
    real = [f for f in findings if not f["rule"].startswith("skip:")]
    if a.json:
        print(json.dumps({"files": len(files), "findings": findings}, indent=1))
    else:
        for f in findings:
            print(f"{f['file']}:{f['line']}: {f['rule']}")
        print(f"scan: {'clean' if not real else str(len(real)) + ' finding(s)'} ({len(files)} files, {len(RULES)} rules)")
    return 1 if real else 0


if __name__ == "__main__":
    sys.exit(main())
