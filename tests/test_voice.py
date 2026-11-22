# SPDX-License-Identifier: Apache-2.0
"""Voice input (bpy-free): recorder choice, command lines, transcript clean-up."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from maris3d.copilot import voice  # noqa: E402


def which_of(*names):
    return lambda n: f"/usr/bin/{n}" if n in names else None


class Recorder(unittest.TestCase):
    def test_order(self):
        self.assertEqual(voice.find_recorder(which_of("rec", "ffmpeg"), "darwin")[0], "rec")
        self.assertEqual(voice.find_recorder(which_of("ffmpeg"), "darwin")[0], "ffmpeg")
        self.assertEqual(voice.find_recorder(which_of("arecord"), "linux")[0], "arecord")
        self.assertIsNone(voice.find_recorder(which_of("arecord"), "darwin"))
        self.assertEqual(voice.find_recorder(which_of("powershell"), "win32")[0], "mci")
        self.assertIsNone(voice.find_recorder(which_of(), "linux"))

    def test_commands_are_16k_mono_and_capped(self):
        for rec, plat in ((("rec", "rec"), "darwin"), (("ffmpeg", "ffmpeg"), "darwin"),
                          (("ffmpeg", "ffmpeg"), "win32"), (("ffmpeg", "ffmpeg"), "linux"),
                          (("arecord", "arecord"), "linux")):
            cmd = voice.record_command(rec, "/x/a.wav", plat)
            self.assertEqual(cmd[-1] if rec[0] != "rec" else cmd[8], "/x/a.wav")
            self.assertIn("16000", cmd)
            self.assertIn(str(voice.MAX_SECONDS), cmd)
        self.assertIn("avfoundation", voice.record_command(("ffmpeg", "f"), "a.wav", "darwin"))
        self.assertIn("dshow", voice.record_command(("ffmpeg", "f"), "a.wav", "win32"))
        ps = voice.record_command(("mci", "powershell"), "C:\\t\\it's.wav", "win32")
        self.assertIn("it''s.wav", ps[-1])
        self.assertTrue(voice.stops_by_stdin(("mci", "p")) and voice.stops_by_stdin(("ffmpeg", "f")))
        self.assertFalse(voice.stops_by_stdin(("rec", "r")))
        self.assertEqual(voice.stop_line(("ffmpeg", "f")), "q\n")


class Transcribe(unittest.TestCase):
    def test_command(self):
        cmd = voice.transcribe_command("/w/whisper-cli", "/w/m.en.bin", "/t/a.wav", threads=4)
        self.assertEqual(cmd[:7], ["/w/whisper-cli", "-m", "/w/m.en.bin", "-f", "/t/a.wav", "-l", "en"])
        self.assertIn("-nt", cmd)

    def test_language_follows_the_model(self):
        """an English-only model is told English; the many-language model detects the language"""
        en = voice.transcribe_command("w", "/c/whisper/ggml-base.en-q5_1.bin", "a.wav", threads=2)
        multi = voice.transcribe_command("w", "/c/whisper/ggml-base-q5_1.bin", "a.wav", threads=2)
        self.assertEqual(en[en.index("-l") + 1], "en")
        self.assertEqual(multi[multi.index("-l") + 1], "auto")

    def test_both_voice_models_are_pinned(self):
        from maris3d import cli
        self.assertEqual(set(cli.WHISPER_MODELS), {"en", "multi"})
        for name, sha in cli.WHISPER_MODELS.values():
            self.assertTrue(name.startswith("ggml-") and name.endswith(".bin"))
            self.assertEqual(len(sha), 64)
        self.assertIn(".en", cli.WHISPER_MODELS["en"][0])
        self.assertNotIn(".en", cli.WHISPER_MODELS["multi"][0])

    def test_clean(self):
        self.assertEqual(voice.clean_transcript(" Add a red cube named Box.\n"), "Add a red cube named Box")
        self.assertEqual(voice.clean_transcript("[BLANK_AUDIO]"), "")
        self.assertEqual(voice.clean_transcript("(wind blowing) Make the roof\n white."), "Make the roof white")
        self.assertEqual(voice.clean_transcript(None), "")

    def test_find_whisper_in_cache(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(voice.find_whisper(d, which=lambda n: None, exe="whisper-cli"))
            p = Path(d) / "whisper" / "b5454" / "Release" / "whisper-cli"
            p.parent.mkdir(parents=True)
            p.write_text("")
            self.assertEqual(voice.find_whisper(d, which=lambda n: None, exe="whisper-cli"), str(p))


if __name__ == "__main__":
    unittest.main()
