# SPDX-License-Identifier: Apache-2.0
"""Voice input, offline (bpy-free, so it is tested without Blender): record from the microphone
into a 16 kHz mono WAV with a recorder already on the machine, transcribe it with whisper.cpp
(`maris3d install --voice` fetches both the program and a small English model), and clean the
words up into a prompt.

The add-on runs these command lines with subprocess; nothing here leaves the machine."""
import os
import re
import shutil
import sys

RATE = 16000                 # whisper.cpp wants 16 kHz mono 16-bit WAV
MAX_SECONDS = 30             # a prompt is a sentence or two; the recorder stops itself after this


def find_recorder(which=shutil.which, platform=sys.platform):
    """(name, path) of the first recorder found: sox's `rec`, ffmpeg, ALSA's `arecord` (Linux),
    else Windows' own sound recorder through PowerShell; None if there is none."""
    for name in ("rec", "ffmpeg") + (("arecord",) if platform.startswith("linux") else ()):
        p = which(name)
        if p:
            return name, p
    if platform == "win32":
        p = which("powershell") or which("pwsh")
        if p:
            return "mci", p
    return None


def record_command(recorder, wav, platform=sys.platform, seconds=MAX_SECONDS):
    """The command line that records the default microphone into `wav` until it is stopped
    (or `seconds` pass)."""
    name, path = recorder
    wav = str(wav)
    if name == "rec":
        return [path, "-q", "-r", str(RATE), "-c", "1", "-b", "16", wav, "trim", "0", str(seconds)]
    if name == "ffmpeg":
        src = {"darwin": ["-f", "avfoundation", "-i", ":0"],
               "win32": ["-f", "dshow", "-i", "audio=default"]}.get(platform, ["-f", "pulse", "-i", "default"])
        return [path, "-hide_banner", "-loglevel", "error", "-y", *src, "-t", str(seconds),
                "-ac", "1", "-ar", str(RATE), "-sample_fmt", "s16", wav]
    if name == "arecord":
        return [path, "-q", "-f", "S16_LE", "-r", str(RATE), "-c", "1", "-d", str(seconds), wav]
    if name == "mci":            # Windows: winmm records until a line arrives on stdin
        w = wav.replace("'", "''")
        script = ("$s=Add-Type -PassThru -Name M -Namespace W -MemberDefinition "
                  "'[DllImport(\"winmm.dll\")] public static extern int mciSendString(string c, "
                  "System.Text.StringBuilder r, int n, System.IntPtr h);';"
                  "$null=$s::mciSendString('open new type waveaudio alias mic',$null,0,0);"
                  f"$null=$s::mciSendString('set mic bitspersample 16 channels 1 samplespersec {RATE}',$null,0,0);"
                  "$null=$s::mciSendString('record mic',$null,0,0);"
                  f"$null=[Console]::In.ReadLine();"
                  f"$null=$s::mciSendString('save mic \"{w}\"',$null,0,0);"
                  "$null=$s::mciSendString('close mic',$null,0,0)")
        return [path, "-NoProfile", "-Command", script]
    raise ValueError(f"unknown recorder {name}")


def stops_by_stdin(recorder):
    """True when the recorder is stopped by a line on its stdin (else by an interrupt)."""
    return recorder[0] in ("mci", "ffmpeg")


def stop_line(recorder):
    return "q\n" if recorder[0] == "ffmpeg" else "\n"


def transcribe_command(whisper, model, wav, threads=None):
    """whisper.cpp's command line: English, plain text, no timestamps, no progress."""
    threads = threads or max(1, min(8, (os.cpu_count() or 4) - 1))
    return [str(whisper), "-m", str(model), "-f", str(wav), "-l", "en", "-nt", "-np",
            "-t", str(threads)]


_NOISE = re.compile(r"\[[^\]]*\]|\([^)]*\)|\*[^*]*\*")      # [BLANK_AUDIO], (wind blowing), *music*


def clean_transcript(text):
    """The spoken words as a prompt: one line, no sound tags, no trailing full stop."""
    text = _NOISE.sub(" ", text or "")
    text = " ".join(text.split())
    text = text.strip(" .")
    return text


def find_whisper(cache_dir, which=shutil.which, exe=None):
    """The whisper.cpp program `maris3d install --voice` unpacked under cache_dir, else one on
    PATH (Homebrew's whisper-cpp installs `whisper-cli`)."""
    from pathlib import Path
    exe = exe or ("whisper-cli.exe" if sys.platform == "win32" else "whisper-cli")
    for p in sorted(Path(cache_dir).glob(f"whisper/*/**/{exe}"), reverse=True):
        if p.is_file():
            return str(p)
    return which("whisper-cli")
