#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Test a version BEFORE it is published (every version, patches too). Run from the repo root:
#   scripts/prerelease_test.sh [git-ref]          # default HEAD
# On the exact tree that would be pushed (the ref minus internal/), in throwaway folders:
#   1. unit tests, private scan, release check
#   2. builds the wheel, runs install.sh against it in a fresh HOME (add-on, models, self-test)
#   3. replays the standard prompts headless in Blender through the installed add-on
# Model files are copied from MARIS3D_MODELS (default ~/.cache/maris3d/models) when present, so nothing
# is downloaded twice; without them the installer downloads from Hugging Face as a user would.
# Uses the llama-server at MARIS3D_TEST_SERVER (default http://127.0.0.1:9931) if one answers,
# otherwise starts one from the test HOME and stops it at the end. Nothing is left running.
set -eu
REF="${1:-HEAD}"
ROOT=$(git rev-parse --show-toplevel)
WORK=$(mktemp -d "${TMPDIR:-/tmp}/maris3d-prerelease.XXXXXX")
SERVER="${MARIS3D_TEST_SERVER:-http://127.0.0.1:9931}"
MODELS="${MARIS3D_MODELS:-$HOME/.cache/maris3d/models}"
BLENDER="${BLENDER_BIN:-/Applications/Blender.app/Contents/MacOS/Blender}"
STARTED=""
cleanup() {
  if [ -n "$STARTED" ]; then HOME="$WORK/testhome" "$WORK/testhome/.local/bin/maris3d" serve stop >/dev/null 2>&1 || true; fi
  rm -rf "$WORK"
}
trap cleanup EXIT INT TERM
step() { printf '\n== %s\n' "$*"; }

step "public tree of $REF (without internal/)"
IDX="$WORK/index"
GIT_INDEX_FILE="$IDX" git -C "$ROOT" read-tree "$REF"
GIT_INDEX_FILE="$IDX" git -C "$ROOT" rm -rq --cached --ignore-unmatch internal
TREE=$(GIT_INDEX_FILE="$IDX" git -C "$ROOT" write-tree)
mkdir "$WORK/tree"
git -C "$ROOT" archive "$TREE" | tar -x -C "$WORK/tree"
if [ -n "$(git -C "$ROOT" ls-tree -r --name-only "$TREE" | grep '^internal/' || true)" ]; then echo "FAIL internal/ in the public tree"; exit 1; fi
VERSION=$(cd "$WORK/tree" && PYTHONPATH=src python3 -c 'import maris3d; print(maris3d.__version__)')
echo "version $VERSION"

step "unit tests, scan, release check"
(cd "$WORK/tree" && PYTHONPATH=src python3 -m unittest discover -s tests 2>&1 | grep -E '^(Ran|OK|FAILED \(|FAIL:|ERROR:)')
(cd "$WORK/tree" && PYTHONPATH=src python3 -m unittest discover -s tests >/dev/null 2>&1) || { echo "FAIL unit tests"; exit 1; }
(cd "$WORK/tree" && PYTHONPATH=src python3 scripts/scan_private.py | tail -1)
if (cd "$WORK/tree" && PYTHONPATH=src python3 scripts/release_check.py 2>&1 | grep '^FAIL'); then echo "FAIL release check"; exit 1; fi
grep -q "^## \[$VERSION\]" "$WORK/tree/CHANGELOG.md" || { echo "FAIL no CHANGELOG entry for $VERSION"; exit 1; }
grep -q "^VERSION=\"$VERSION\"" "$WORK/tree/install.sh" || { echo "FAIL install.sh VERSION is not $VERSION"; exit 1; }
grep -q "^\$Version = \"$VERSION\"" "$WORK/tree/install.ps1" || { echo "FAIL install.ps1 Version is not $VERSION"; exit 1; }
echo "OK versions agree: $VERSION"

step "wheel + install.sh in a fresh HOME"
(cd "$WORK/tree" && python3 -m pip wheel . -w "$WORK/wheel" --no-deps -q 2>/dev/null)
WHEEL=$(ls "$WORK"/wheel/maris3d-"$VERSION"-py3-none-any.whl)
mkdir -p "$WORK/testhome/.cache/maris3d/models"
if [ -d "$MODELS" ]; then cp -c "$MODELS"/*.gguf "$WORK/testhome/.cache/maris3d/models/" 2>/dev/null || cp "$MODELS"/*.gguf "$WORK/testhome/.cache/maris3d/models/" 2>/dev/null || true; fi
HOME="$WORK/testhome" BLENDER_USER_RESOURCES="$WORK/testhome/blender" BLENDER_BIN="$BLENDER" MARIS3D_WHEEL="$WHEEL" \
  sh "$WORK/tree/install.sh" --express </dev/null >"$WORK/install.log" 2>&1 || { tail -20 "$WORK/install.log"; echo "FAIL install.sh"; exit 1; }
grep -E "SELFTEST|Ready" "$WORK/install.log" | cut -c1-200
grep -q "SELFTEST READY" "$WORK/install.log" || { echo "FAIL self-test"; exit 1; }
"$WORK/testhome/.local/bin/maris3d" --version

step "headless replay of the standard prompts"
if ! curl -fsS -m 5 "$SERVER/health" >/dev/null 2>&1; then
  HOME="$WORK/testhome" "$WORK/testhome/.local/bin/maris3d" serve start >/dev/null && STARTED=1
  SERVER=http://127.0.0.1:9931
fi
BLENDER_USER_RESOURCES="$WORK/testhome/blender" "$BLENDER" -b --factory-startup \
  --python "$WORK/tree/scripts/prerelease_replay.py" -- "$SERVER" >"$WORK/replay.log" 2>&1 || true
grep -E '^(STEP|PASS|FAIL|REPLAY)' "$WORK/replay.log" || tail -20 "$WORK/replay.log"
grep -q '^REPLAY OK' "$WORK/replay.log" || { echo "FAIL replay"; exit 1; }

printf '\nPRERELEASE OK %s (%s). Not covered here: install.ps1 on Windows.\n' "$VERSION" "$REF"
