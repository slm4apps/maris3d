# SPDX-License-Identifier: Apache-2.0
"""`python -m maris3d`: the same as the `maris3d` command (used where a launcher .exe is blocked)."""
import sys

from .cli import main

sys.exit(main())
