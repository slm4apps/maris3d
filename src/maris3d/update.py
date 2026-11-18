# SPDX-License-Identifier: Apache-2.0
"""Install and update the model files: fetch only what changed, check it, remove what it replaced.

The model is one base file (about 530 MB) plus small adapters (about 6 MB each), one per role
(one, parts). A new adapter version must not cost a new download of the base.

  maris3d update [--from <folder or URL>]          (the same thing from the main command)
  python3 -m maris3d.update update --from <folder or URL> [--models <folder>]
  python3 -m maris3d.update status [--models <folder>]
  python3 -m maris3d.update manifest <folder> --release 0.1.1 base=v1:<file> one=v1:<file> ...
        [--needs-app 0.2.0]

The source holds MANIFEST.json: the ONE current file of every role, with its sha256.
`update` compares it with the models folder:
  * a file already there with the right sha256 is kept (also one the user fetched by hand);
  * a file that is missing or different is fetched to <name>.part, its sha256 is checked, and
    only then does it take its place. A wrong sha256 leaves the old file serving and is an error;
  * when a role has a new file, the old file of that role is removed -- only if this tool
    installed it (it is listed in installed.json). Nothing else in the folder is ever touched.
Nothing runs on its own: this is only ever started by the person at the keyboard.

Swapping an adapter for a retrained one. Three things in the manifest make that safe:
  * `needs_app`: the oldest program version that can use this release. An older program refuses
    the whole update and says "update the program first"; nothing in the folder is touched.
  * an entry's `format`: the shape of the adapter's answers ("final/1"). A format this program
    cannot read is refused the same way.

Moving to another repository:
  * `moved_to` (manifest level): where newer releases are. The old repository keeps serving its own
    files and the update says where to go next; nothing is fetched from there on its own.
  * `retire` (manifest level): roles the new release no longer has. A retired role's file is removed
    if this tool installed it, and the role leaves installed.json.
  * a file renamed between releases but with the same sha256 (the base) is moved, not fetched again.
"""
import hashlib
import json
import os
import re
import shutil
import sys


MANIFEST = "MANIFEST.json"
INSTALLED = "installed.json"
SCHEMA = "maris3d-files/1"
ROLES = ("base", "one", "parts")      # also the order of --lora on the serve line
# answer shapes this program can read, per role (an entry without "format" is taken as readable)
FORMATS = {"parts": ("parts/1", "final/1"), "one": ("final/1",)}
DEFAULT_MODELS = os.path.join("~", ".cache", "maris3d", "models")   # where `maris3d install` puts them
CHUNK = 1 << 20


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def is_url(source):
    return "://" in str(source)


def _open(source, name):
    if is_url(source):
        from .net import urlopen
        return urlopen(str(source).rstrip("/") + "/" + name, timeout=60)
    return open(os.path.join(os.path.expanduser(str(source)), name), "rb")


def _numbers(version):
    """(0, 1, 0) for "0.1.0", "v0.1" or "0.1.0.dev0": the first three numbers of a version."""
    found = [int(n) for n in re.findall(r"\d+", str(version))[:3]]
    return tuple(found + [0] * (3 - len(found)))


def app_version():
    from . import __version__
    return __version__


def read_manifest(source, app=None, for_this_program=True):
    with _open(source, MANIFEST) as f:
        manifest = json.loads(f.read().decode("utf-8"))
    if manifest.get("schema") != SCHEMA or not isinstance(manifest.get("files"), list):
        raise ValueError(f"{MANIFEST} at {source} is not a {SCHEMA} manifest")
    if "moved_to" in manifest and not (isinstance(manifest["moved_to"], str) and is_url(manifest["moved_to"])):
        raise ValueError(f"{MANIFEST} at {source}: moved_to must be a URL")
    retire = manifest.get("retire", [])
    if not isinstance(retire, list) or any(not isinstance(r, str) for r in retire):
        raise ValueError(f"{MANIFEST} at {source}: retire must list roles")
    app = app or app_version()
    if not for_this_program:            # the publisher's check: a release may be for a newer program
        app, known_formats = "999", {}
    else:
        known_formats = FORMATS
    if manifest.get("needs_app") and _numbers(manifest["needs_app"]) > _numbers(app):
        raise ValueError(f"release {manifest.get('release')} needs maris3d {manifest['needs_app']} or newer and this "
                         f"is {app}: update the program first (the add-on and the command), then run the update "
                         f"again. Nothing was changed")
    for entry in manifest["files"]:
        known = known_formats.get(entry.get("role"))
        if entry.get("format") and known and entry["format"] not in known:
            raise ValueError(f"the {entry.get('role')} file of release {manifest.get('release')} answers in the format "
                             f"{entry['format']!r}, which maris3d {app} cannot read: update the program first. "
                             f"Nothing was changed")
    seen = set()
    for entry in manifest["files"]:
        missing = [k for k in ("role", "version", "file", "sha256", "bytes") if k not in entry]
        if missing:
            raise ValueError(f"manifest entry {entry.get('file')!r} has no {', '.join(missing)}")
        if entry["role"] not in ROLES or entry["role"] in seen:
            raise ValueError(f"manifest role {entry['role']!r} is unknown or listed twice")
        if os.path.basename(entry["file"]) != entry["file"] or entry["file"] in (MANIFEST, INSTALLED):
            raise ValueError(f"manifest file name {entry['file']!r} is not a plain file name")
        seen.add(entry["role"])
    return manifest


def read_installed(models):
    path = os.path.join(models, INSTALLED)
    if not os.path.exists(path):
        return {"schema": SCHEMA, "release": None, "files": []}
    with open(path) as f:
        return json.load(f)


def _write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, path)


def _has(path, entry, record=None):
    """Is the file at `path` the one the manifest means? A file this tool wrote and that has not
    changed since (same size and time) is not hashed again: the base is 530 MB."""
    if not os.path.isfile(path) or os.path.getsize(path) != entry["bytes"]:
        return False
    if record and record.get("sha256") == entry["sha256"] and record.get("mtime") == os.path.getmtime(path):
        return True
    return sha256_of(path) == entry["sha256"]


def _renamed_twin(old, entry, models, moved):
    """An installed file, put there by this tool, with this entry's sha256 under another name."""
    for was in old.values():
        if (was.get("by") == "update" and was.get("sha256") == entry["sha256"] and was["file"] != entry["file"]
                and was["file"] not in moved and _has(os.path.join(models, was["file"]), entry, was)):
            return was
    return None


def _fetch(source, entry, models):
    """Fetch one file next to its place, check it, then move it in. Returns bytes transferred."""
    target = os.path.join(models, entry["file"])
    part = target + ".part"
    h, done = hashlib.sha256(), 0
    try:
        with _open(source, entry["file"]) as src, open(part, "wb") as dst:
            for block in iter(lambda: src.read(CHUNK), b""):
                h.update(block)
                dst.write(block)
                done += len(block)
        if h.hexdigest() != entry["sha256"]:
            raise ValueError(f"sha256 of {entry['file']} is {h.hexdigest()[:12]}..., the manifest says "
                             f"{entry['sha256'][:12]}...: not installed")
        os.replace(part, target)
    finally:
        if os.path.exists(part):
            os.remove(part)
    return done


def update(source, models=DEFAULT_MODELS, log=print):
    """Bring the models folder to what the source's manifest lists. Returns a report dict;
    report["failed"] is empty when everything the manifest lists is in place and checked."""
    models = os.path.expanduser(models)
    os.makedirs(models, exist_ok=True)
    manifest = read_manifest(source)
    installed = read_installed(models)
    old = {e["role"]: e for e in installed.get("files", [])}
    report = {"release": manifest.get("release"), "kept": [], "fetched": [], "removed": [], "failed": [],
              "renamed": [], "bytes_transferred": 0}
    if manifest.get("moved_to"):
        report["moved_to"] = manifest["moved_to"]
        log(f"newer releases are at {manifest['moved_to']}: update the program, then run the update again")
    now, moved = {}, set()
    for entry in manifest["files"]:
        role, target = entry["role"], os.path.join(models, entry["file"])
        was = old.get(role)
        same = bool(was) and was["file"] == entry["file"]
        by = was.get("by", "found") if same else "found"
        twin = _renamed_twin(old, entry, models, moved)
        if _has(target, entry, was if same else None):
            report["kept"].append(entry["file"])
        elif twin:                       # the same bytes under the old name: move, do not fetch again
            os.replace(os.path.join(models, twin["file"]), target)
            moved.add(twin["file"])
            by = "update"
            report["renamed"].append([twin["file"], entry["file"]])
            log(f"renamed {twin['file']} -> {entry['file']} (same file, nothing fetched)")
        else:
            try:
                report["bytes_transferred"] += _fetch(source, entry, models)
                report["fetched"].append(entry["file"])
                by = "update"
                log(f"fetched {entry['file']} ({role} {entry['version']}, {entry['bytes']:,} bytes)")
            except Exception as error:                       # the old file of this role keeps serving
                report["failed"].append({"file": entry["file"], "error": str(error)[:300]})
                log(f"FAILED {entry['file']}: {error}")
                if was:
                    now[role] = was
                continue
        now[role] = dict(entry, mtime=os.path.getmtime(target), by=by)
    # remove what was replaced: only files this tool fetched, and never one still in use
    in_use = {e["file"] for e in now.values()}
    retire = set(manifest.get("retire", []))
    for role, was in old.items():
        if was["file"] in moved or was["file"] in in_use or role in now and now[role]["file"] == was["file"]:
            continue
        if role not in now and role not in retire:
            continue
        path = os.path.join(models, was["file"])
        if was.get("by") == "update" and os.path.isfile(path):
            os.remove(path)
            report["removed"].append(was["file"])
            log(f"removed {was['file']} ({role} {was['version']}, "
                + (f"replaced by {now[role]['version']})" if role in now else "this release has no such role)"))
        elif os.path.isfile(path):
            log(f"left {was['file']} in place: it was not installed by this tool")
    for role, was in old.items():            # a role the new manifest no longer lists stays as it is,
        if role not in retire:               # unless the manifest retires it
            now.setdefault(role, was)
    _write_json(os.path.join(models, INSTALLED),
                {"schema": SCHEMA, "release": manifest.get("release") if not report["failed"] else installed.get("release"),
                 "files": [now[r] for r in ROLES if r in now]})
    report["serve"] = serve_command(models)
    return report


def serve_command(models=DEFAULT_MODELS, port=8080, llama_server="llama-server"):
    """The llama-server line for what is installed: the base, then every adapter in role order,
    loaded at scale 0 (the copilot sets the scale and the repeat penalty per request and finds each adapter
    by its name)."""
    models = os.path.expanduser(models)
    files = {e["role"]: os.path.join(models, e["file"]) for e in read_installed(models).get("files", [])}
    if "base" not in files:
        return None
    cmd = [llama_server, "-m", files["base"], "--jinja", "-c", "8192", "--temp", "0", "--port", str(port)]
    adapters = [files[r] for r in ROLES[1:] if r in files]
    for path in adapters:
        cmd += ["--lora", path]
    if adapters:
        cmd.append("--lora-init-without-apply")
    return cmd


def write_manifest(folder, entries, release, needs_app=None, extra=None, moved_to=None, retire=None):
    """MANIFEST.json for a folder that is about to be published. entries: [(role, version, file)];
    extra: {role: {"format": ..., "system": ...}} (what the adapter of that role was trained on)."""
    folder = os.path.expanduser(folder)
    files = []
    for role, version, name in entries:
        path = os.path.join(folder, name)
        files.append(dict({"role": role, "version": version, "file": name, "sha256": sha256_of(path),
                           "bytes": os.path.getsize(path)}, **(extra or {}).get(role, {})))
    manifest = {"schema": SCHEMA, "release": release, "files": files}
    if needs_app:
        manifest["needs_app"] = needs_app
    if moved_to:
        manifest["moved_to"] = moved_to
    if retire:
        manifest["retire"] = list(retire)
    _write_json(os.path.join(folder, MANIFEST), manifest)
    read_manifest(folder, for_this_program=False)           # the structure checks a user's update runs
    return manifest


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else ""

    def opt(name, default=None):
        return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default

    models = opt("--models", DEFAULT_MODELS)
    if cmd == "update" and opt("--from"):
        report = update(opt("--from"), models)
        print(json.dumps({k: v for k, v in report.items() if k != "serve"}, indent=1))
        if report["serve"]:
            print(" ".join(report["serve"]))
        return 1 if report["failed"] else 0
    if cmd == "status":
        print(json.dumps(read_installed(os.path.expanduser(models)), indent=1))
        return 0
    if cmd == "manifest" and len(argv) >= 3:
        entries = []
        for word in argv[2:]:
            if "=" in word and ":" in word and not word.startswith("--"):
                role, rest = word.split("=", 1)
                version, name = rest.split(":", 1)
                entries.append((role, version, name))
        extra = {}
        print(json.dumps(write_manifest(argv[1], entries, opt("--release", "0.0.0"), opt("--needs-app"), extra), indent=1))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
