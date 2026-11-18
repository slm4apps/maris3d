# SPDX-License-Identifier: Apache-2.0
import json
import os
import socket
import subprocess
import threading
import time

from ..copilot.session import Executor
from .compile import compile_call

_BLENDER_PATHS = ("/Applications/Blender.app/Contents/MacOS/Blender", "/usr/bin/blender", "/usr/local/bin/blender",
                  "C:/Program Files/Blender Foundation/Blender/blender.exe")


def _find_blender():
    env = os.getenv("BLENDER_BIN")
    if env:
        return env
    import shutil
    return shutil.which("blender") or next((p for p in _BLENDER_PATHS if os.path.exists(p)), None)


def _running(pid):
    """True for a live process; a defunct (zombie) one counts as gone."""
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    try:
        import subprocess
        st = subprocess.run(["ps", "-p", str(pid), "-o", "stat="], capture_output=True, text=True, timeout=5).stdout.strip()
        return bool(st) and not st.startswith("Z")
    except Exception:
        return True


class LiveExecutor(Executor):
    """Our own Blender window (blender/live_server.py): newline JSON over TCP, lock, lazy reconnect."""

    def __init__(self, host="127.0.0.1", port=9877, timeout=180, blender_bin=None, state_dir=None):
        self.addr, self.timeout = (host, port), timeout
        self.blender_bin = blender_bin
        self.state_dir = state_dir or os.path.expanduser("~/.cache/maris3d/live")
        self.lock, self.sock, self.f = threading.Lock(), None, None

    def rpc(self, cmd, **kw):
        with self.lock:
            for attempt in (0, 1):
                try:
                    if self.f is None:
                        self.sock = socket.create_connection(self.addr, timeout=3)
                        self.sock.settimeout(self.timeout)
                        self.f = self.sock.makefile("rwb")
                    self.f.write((json.dumps(dict(kw, cmd=cmd)) + "\n").encode())
                    self.f.flush()
                    line = self.f.readline()
                    if not line:
                        raise ConnectionError("closed")
                    return json.loads(line)
                except Exception:
                    self.sock = self.f = None
                    if attempt:
                        raise

    def alive(self):
        try:
            return bool(self.rpc("ping").get("ok"))
        except Exception:
            return False

    def ensure(self, wait_s=120):
        """Attach to the open window, or launch ONE Blender with the live add-on (detached) and wait for it.
        Never starts a second one on the same port: a known pid that is alive but silent is reported as busy."""
        if self.alive():
            return
        pidfile = os.path.join(self.state_dir, "blender-live.pid")
        try:
            pid = int(open(pidfile).read().strip())
            if not _running(pid):
                raise ProcessLookupError(pid)
            raise RuntimeError(f"Blender (pid {pid}) is running but not answering on port {self.addr[1]}: it is busy or hung")
        except (OSError, ValueError):
            pass
        binary = self.blender_bin or _find_blender()
        if not binary:
            raise RuntimeError("Blender not found: set BLENDER_BIN or open Blender with the live add-on")
        os.makedirs(self.state_dir, exist_ok=True)
        addon = os.path.join(os.path.dirname(__file__), "..", "blender", "live_server.py")
        env = dict(os.environ, BLENDER_LIVE_PORT=str(self.addr[1]), BLENDER_LIVE_SHOTS=self.state_dir)
        log = open(os.path.join(self.state_dir, "blender-launch.log"), "ab", buffering=0)
        proc = subprocess.Popen([binary, "--factory-startup", "--window-geometry", "40", "60", "1280", "800", "--python", addon],
                                stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True, env=env)
        try:
            open(pidfile, "w").write(str(proc.pid))
        except OSError:
            pass
        deadline = time.time() + wait_s
        while time.time() < deadline:
            time.sleep(1.0)
            if self.alive():
                return
            if proc.poll() is not None:
                raise RuntimeError(f"Blender exited at start-up with status {proc.returncode} (see {self.state_dir}/blender-launch.log)")
        raise RuntimeError(f"Blender did not answer on port {self.addr[1]} within {wait_s}s")

    def run_call(self, call):
        code, err = compile_call(call)
        if err:
            return False, err
        res = self.rpc("exec", code=code, reuse_materials=True)  # same colour name reuses one material instead of Red, Red.001, ...
        error = res.get("error") or (None if res.get("ok", True) else "failed")
        return (error is None), error

    def reset(self):
        self.rpc("reset")

    def objects(self):
        return [{"name": o["name"], "type": o["type"], "loc": o.get("loc", [0, 0, 0]),
                 "dims": o.get("dims", [0, 0, 0]), "material": (o.get("mat") or [None])[0],
                 "parent": o.get("parent")} for o in self.rpc("summary").get("objects", [])]
