"""The Codex guard hook: merge it into, or remove it from, Codex's hooks.json.

Codex reads hooks from ~/.codex/hooks.json ($SCIENCE_RESEARCH_WRITING_CODEX_HOOKS
overrides the path, for tests), never from a skill. Our entry is one Stop hook whose
command carries the marker MARKER, which is how we recognise it later. The command
names this skill's real install path (symlinks resolved) and exits quietly when the
engine or python3 is gone, so a leftover entry does nothing.
"""
import json
import os
import shlex
from pathlib import Path

ENV = "SCIENCE_RESEARCH_WRITING_CODEX_HOOKS"
MARKER = "science-research-writing-guard"
ENGINE = Path(__file__).resolve().parents[1] / "engine.py"


def hooks_path():
    return Path(os.environ.get(ENV) or Path.home() / ".codex" / "hooks.json")


def command():
    inner = ": %s; E=%s; [ -f \"$E\" ] && command -v python3 >/dev/null 2>&1 && exec python3 \"$E\" guard; cat >/dev/null; exit 0" % (
        MARKER, shlex.quote(str(ENGINE)))
    return "/bin/sh -c " + shlex.quote(inner)


def _load():
    p = hooks_path()
    if not p.exists():
        return None, {"hooks": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        hooks = data.setdefault("hooks", {})
        groups = hooks.get("Stop", [])
        if not (isinstance(data, dict) and isinstance(hooks, dict) and isinstance(groups, list)
                and all(isinstance(g, dict) and isinstance(g.get("hooks"), list) for g in groups)):
            raise ValueError("unexpected shape")
    except (ValueError, AttributeError) as e:
        raise ValueError("cannot read %s as Codex hooks (%s); left unchanged" % (p, e))
    return p.read_bytes(), data


def _own(data):
    return [h for g in data["hooks"].get("Stop", []) for h in g["hooks"]
            if isinstance(h, dict) and MARKER in str(h.get("command", ""))]


def installed():
    try:
        return any(h["command"] == command() for h in _own(_load()[1]))
    except ValueError:
        return False


def _write(original, data):
    p = hooks_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    bak = p.with_name(p.name + ".bak")
    if original is not None and not bak.exists():  # keep the first backup: it is the author's original
        bak.write_bytes(original)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(str(tmp), str(p))


def install():
    """Add (or refresh) our Stop hook. Returns True if the file changed."""
    original, data = _load()
    own = _own(data)
    if own and all(h["command"] == command() for h in own) and len(own) == 1:
        return False
    for h in own:  # a moved skill: point the existing entry at the new path
        h["command"] = command()
    if not own:
        data["hooks"].setdefault("Stop", []).append(
            {"hooks": [{"type": "command", "command": command(), "timeout": 10}]})
    _write(original, data)
    return True


def uninstall():
    """Remove only our entry. Returns True if the file changed."""
    original, data = _load()
    if original is None or not _own(data):
        return False
    groups = data["hooks"]["Stop"]
    for g in groups:
        g["hooks"] = [h for h in g["hooks"] if not (isinstance(h, dict) and MARKER in str(h.get("command", "")))]
    data["hooks"]["Stop"] = [g for g in groups if g["hooks"]]
    if not data["hooks"]["Stop"]:
        del data["hooks"]["Stop"]
    _write(original, data)
    return True


TRUST = "In Codex, open /hooks and trust the science-research-writing guard hook; Codex ignores it until you do."


def main(argv):
    try:
        if argv[:1] == ["--uninstall"]:
            print("Removed the guard hook from %s." % hooks_path() if uninstall()
                  else "No guard hook in %s; nothing to remove." % hooks_path())
            return 0
        if argv:
            print("usage: install_codex_hook.py [--uninstall]")
            return 2
        changed = install()
    except ValueError as e:
        print("error: %s" % e)
        return 1
    print("%s the guard hook %s %s." % ("Installed" if changed else "The guard hook is already installed;", "in" if changed else "nothing changed in", hooks_path()))
    if changed and hooks_path().with_name(hooks_path().name + ".bak").exists():
        print("The previous file is kept as %s.bak." % hooks_path().name)
    print(TRUST)
    return 0
