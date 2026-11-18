# SPDX-License-Identifier: Apache-2.0
import contextlib, io, os, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import scan_private as S  # noqa: E402


def rules(text):
    return {f["rule"] for f in S.scan_text(text)}


class ScanRules(unittest.TestCase):
    # every sample is assembled from pieces so this file does not trip the scanner itself
    def test_each_category_fires(self):
        samples = {
            "secret:github-token": "tok = " + "gh" + "p_" + "a" * 30,
            "secret:openai-style-key": "k = " + "s" + "k-" + "A1b2" * 8,
            "secret:aws-key-id": "AK" + "IA" + "ABCDEFGHIJKLMNOP",
            "secret:private-key-header": "-----BEGIN " + "RSA PRIVATE KEY-----",
            "secret:assigned-credential": "pass" + "word = 'hunter22xx'",
            "secret:bearer-token": "Authorization: Bear" + "er " + "a1b2c3d4e5f6g7h8i9",
            "internal:vpn-address": "host 100." + "64.1.2",
            "path:home-directory": "/Us" + "ers/someone/project",
            "ticket:hash-number": "fixes #" + "118 today",
            "ticket:task-tag": "task" + "-104 data",
            "email:address": "mail me at someone@" + "example.com",
        }
        for rule, text in samples.items():
            self.assertIn(rule, rules(text), rule)

    def test_clean_text_passes(self):
        self.assertEqual(rules("Add a cube; version 0.1.0; see issue tracker; 100% done; C# is fine; #include <x>"), set())
        self.assertEqual(rules("noreply: 123+user@users.noreply.github.com"), set())

    def test_allow_marker_skips_line(self):
        self.assertEqual(rules("mail someone@" + "example.com  " + S.ALLOW_MARK), set())

    def test_a_binary_file_is_read_for_the_path_it_was_saved_from(self):
        home = ("/Us" + "ers/someone/project/scene.blend").encode()
        fbx = b"Kaydara FBX Binary  \x00\x1a\x00" + b"\x01\x02" * 50 + b"S\x40\x00\x00\x00" + home + b"\x00\x07" * 20
        clean = b"Kaydara FBX Binary  \x00\x1a\x00" + b"\x01\x02" * 50 + b"/tmp/export/scene.blend\x00#12 a@" + b"b.cd\x00"
        with tempfile.TemporaryDirectory() as tmp:
            for name, data in (("leak.fbx", fbx), ("clean.fbx", clean)):
                with open(os.path.join(tmp, name), "wb") as f:
                    f.write(data)
            self.assertEqual({f["rule"] for f in S.scan_file(os.path.join(tmp, "leak.fbx"), "leak.fbx")},
                             {"path:home-directory"})
            self.assertEqual(S.scan_file(os.path.join(tmp, "clean.fbx"), "clean.fbx"), [])

    def test_a_compressed_scene_file_is_opened_or_reported_never_passed_unread(self):
        import gzip
        inner = b"BLENDER-v500" + b"\x00" * 64 + ("/ho" + "me/someone/take/scene.blend").encode() + b"\x00" * 64
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "scene.blend")
            with open(path, "wb") as f:
                f.write(gzip.compress(inner))
            self.assertEqual({f["rule"] for f in S.scan_file(path, "scene.blend")}, {"path:home-directory"})
            with open(path, "wb") as f:
                f.write(S.ZSTD + b"not a real zstd frame")
            self.assertEqual({f["rule"] for f in S.scan_file(path, "scene.blend")}, {"unread:compressed-file"})

    def test_output_never_contains_the_match(self):
        f = S.scan_text("pass" + "word = 'hunter22xx'", "x.py")
        self.assertTrue(f and "hunter" not in str(f))

    def _run(self, argv):
        with contextlib.redirect_stdout(io.StringIO()):
            return S.main(argv)

    def test_scan_tree_and_exit_codes(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "ok.txt"), "w").write("nothing here\n")
            open(os.path.join(d, "bad.txt"), "w").write("contact: a@" + "b.org\n")
            self.assertEqual(self._run(["--root", d, "--walk"]), 1)
            os.remove(os.path.join(d, "bad.txt"))
            self.assertEqual(self._run(["--root", d, "--walk"]), 0)

    def test_file_names_are_scanned(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "task" + "-104-notes.txt"), "w").write("x")
            self.assertEqual(self._run(["--root", d, "--walk"]), 1)

    @unittest.skipUnless(os.path.exists(S.PRIVATE_RULES), "the maintainers' private rules are not in this tree")
    def test_the_private_name_rules_are_loaded_and_fire(self):
        names = {name for name, _rx in S.RULES}
        with open(S.PRIVATE_RULES) as f:
            for name, pattern in __import__("json").load(f):
                self.assertIn(name, names)
                self.assertTrue(pattern)

    def test_own_tree_is_clean(self):
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        _, findings = S.scan_tree(root)
        self.assertEqual([f for f in findings if not f["rule"].startswith("skip:")], [])


if __name__ == "__main__":
    unittest.main()
