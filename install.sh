#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Maris3D one-line install for macOS and Linux:
#
#   curl -fsSL https://raw.githubusercontent.com/slm4apps/maris3d/main/install.sh | sh
#
# What it does, in order (nothing else):
#   1. finds Python 3.9+ (python3)
#   2. makes a private Python environment in ~/.local/share/maris3d/venv (no admin rights, no system packages touched)
#   3. installs the maris3d package from this repository's release into it
#   4. links the `maris3d` command into ~/.local/bin
#   5. runs `maris3d install`: the Blender add-on, the model files from Hugging Face (about 543 MB,
#      sha256-checked) and llama-server if you have none, then a self-test in your Blender
# Pass arguments after `sh -s --`, for example `... | sh -s -- --express` to answer every question with yes.
# Remove everything again: `maris3d` files live in ~/.local/share/maris3d and ~/.cache/maris3d.
set -eu

VERSION="0.2.1.1"
WHEEL_URL="${MARIS3D_WHEEL:-https://github.com/slm4apps/maris3d/releases/download/v${VERSION}/maris3d-${VERSION}-py3-none-any.whl}"
HOME_DIR="${MARIS3D_HOME:-$HOME/.local/share/maris3d}"
BIN_DIR="$HOME/.local/bin"

say() { printf '%s\n' "maris3d: $*"; }
fail() { printf '%s\n' "maris3d: $*" >&2; exit 1; }

PY=""
for cand in python3 python; do
  if command -v "$cand" >/dev/null 2>&1 && "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
    PY="$cand"; break
  fi
done
[ -n "$PY" ] || fail "Python 3.9 or newer is needed (macOS: https://www.python.org/downloads/ or 'brew install python'; Linux: your package manager)."
say "using $($PY --version 2>&1)"

say "making a private environment in $HOME_DIR/venv"
"$PY" -m venv "$HOME_DIR/venv" 2>/dev/null || fail "could not make a Python environment (Debian/Ubuntu: sudo apt install python3-venv)."
"$HOME_DIR/venv/bin/python" -m pip install --quiet --upgrade pip >/dev/null 2>&1 || true

say "installing maris3d $VERSION"
"$HOME_DIR/venv/bin/python" -m pip install --quiet --upgrade "$WHEEL_URL" \
  || fail "could not install maris3d from $WHEEL_URL"

mkdir -p "$BIN_DIR"
for cmd in maris3d maris3d-mcp maris3d-setup; do
  ln -sf "$HOME_DIR/venv/bin/$cmd" "$BIN_DIR/$cmd"
done
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) say "to type 'maris3d' anywhere, add $BIN_DIR to your PATH, for example:"
     say "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.zshrc   (bash: ~/.bashrc)"
     say "until then: $BIN_DIR/maris3d";;
esac

say "setting up Blender and the model"
# reading answers from the terminal even when this script itself arrives through a pipe
# (no terminal at all, as in CI: the installer sees that and asks nothing)
if [ ! -t 0 ] && (exec </dev/tty) 2>/dev/null; then
  "$HOME_DIR/venv/bin/maris3d" install "$@" </dev/tty
else
  "$HOME_DIR/venv/bin/maris3d" install "$@"
fi
