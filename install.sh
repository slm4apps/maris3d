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
#   4. links the `maris3d` command into ~/.local/bin and adds that folder to your PATH (one line in ~/.zshrc or ~/.bashrc)
#   5. runs `maris3d install`: the Blender add-on, the model files from Hugging Face (about 554 MB,
#      sha256-checked), llama-server if you have none, the voice and picture modules (about 60 MB and 546 MB,
#      sha256-checked), then a self-test in your Blender
#   6. starts the local server, so Blender can use it straight away
# It asks nothing (running it is the yes). To be asked before each step: `... | MARIS3D_ASK=1 sh`.
# To leave your shell files alone: `... | MARIS3D_NO_MODIFY_PATH=1 sh`. Read the script first: open the URL in a browser.
# Remove everything again: `maris3d` files live in ~/.local/share/maris3d and ~/.cache/maris3d.
set -eu

VERSION="0.3.0"
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
# put the command on PATH for new terminals: one line in the shell's start-up file, added once
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *)
    if [ -n "${MARIS3D_NO_MODIFY_PATH:-}" ]; then
      say "left your shell files alone (MARIS3D_NO_MODIFY_PATH is set); run $BIN_DIR/maris3d, or add $BIN_DIR to your PATH"
    else
    case "${SHELL:-}" in
      */zsh)  RC="$HOME/.zshrc"; LINE='export PATH="$HOME/.local/bin:$PATH"' ;;
      */fish) RC="$HOME/.config/fish/config.fish"; LINE='fish_add_path $HOME/.local/bin' ;;
      *)      RC="$HOME/.bashrc"; LINE='export PATH="$HOME/.local/bin:$PATH"' ;;
    esac
    mkdir -p "$(dirname "$RC")"
    if ! grep -qs '\.local/bin' "$RC" 2>/dev/null; then
      printf '\n# added by the Maris3D installer\n%s\n' "$LINE" >> "$RC"
      say "added $BIN_DIR to your PATH in $RC (open a new terminal to use 'maris3d' anywhere)"
    fi
    fi;;
esac

say "setting up Blender and the model"
# this one command is the consent: no questions unless you pass your own arguments or set MARIS3D_ASK=1
if [ $# -eq 0 ] && [ -z "${MARIS3D_ASK:-}" ]; then set -- --express; fi
# reading answers from the terminal even when this script itself arrives through a pipe
# (no terminal at all, as in CI: the installer sees that and asks nothing)
if [ ! -t 0 ] && (exec </dev/tty) 2>/dev/null; then
  "$HOME_DIR/venv/bin/maris3d" install "$@" </dev/tty
else
  "$HOME_DIR/venv/bin/maris3d" install "$@"
fi

# start the local server so it is ready when Blender opens (it keeps running in the background)
if "$HOME_DIR/venv/bin/maris3d" serve start; then
  say "done. Open Blender, press N in the 3D View and pick the Maris3D Copilot tab."
else
  say "the server did not start; run 'maris3d doctor' to see what is missing."
fi
