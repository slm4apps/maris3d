# Security policy

## What can go wrong in this project
- The MCP server and the bridge **run model-written Python inside Blender**. The model output is compiled from a fixed JSON tool set
  (`src/maris3d/dsl/tools.py`), not executed as free code, but a Blender process still has the permissions of the user who starts it.
- The bridge listens on `127.0.0.1` only. Never bind it to a public address; it has no authentication.
- A model can be wrong, wasteful or build huge scenes. The live server refuses calls that would exceed face limits, but treat all output as untrusted.

## Supported versions
Only the latest release on the default branch and the latest Hugging Face revision.

## Reporting a vulnerability
Use GitHub private vulnerability reporting (Security tab, "Report a vulnerability"). Please do not open a public issue for a vulnerability. Expect an
acknowledgement within 7 days (target, not a guarantee).

## Secrets
Never commit tokens or keys. `scripts/scan_private.py` runs in CI and before every release commit and fails on common secret patterns.
