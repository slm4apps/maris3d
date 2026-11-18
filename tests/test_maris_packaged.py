# SPDX-License-Identifier: Apache-2.0
"""The package carries Maris (an installed wheel builds the add-on from it), byte-equal to assets/maris."""
import os
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
PKG = os.path.join(ROOT, "src", "maris3d", "addon", "maris")
SRC = os.path.join(ROOT, "assets", "maris")


class MarisPackaged(unittest.TestCase):
    def test_the_package_has_maris_and_it_matches_the_source(self):
        for name in ("maris.json", "maris.blend"):
            with open(os.path.join(PKG, name), "rb") as a, open(os.path.join(SRC, name), "rb") as b:
                self.assertEqual(a.read(), b.read(), name + " in the package differs from assets/maris")


if __name__ == "__main__":
    unittest.main()
