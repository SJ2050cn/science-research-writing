"""The Antigravity guard hook: merge it into, or remove it from, Antigravity's hooks.json.

Antigravity reads global hooks from ~/.gemini/config/hooks.json
($SCIENCE_RESEARCH_WRITING_ANTIGRAVITY_HOOKS overrides the path, for tests), and
project hooks from <project>/.agents/hooks.json, never from SKILL.md frontmatter.
Our entry is a single top-level named hook keyed by MARKER with a flat Stop handler
list. The command names this skill's real install path (symlinks resolved) and prints
{} quietly when the engine or python3 is gone, so a leftover entry does nothing.
"""
import json
import os
import shlex
import sys
from pathlib import Path

from . import hookfile

ENV = "SCIENCE_RESEARCH_WRITING_ANTIGRAVITY_HOOKS"
MARKER = "science-research-writing-guard"
ENGINE = (Path(__file__).resolve().parents[1] / "engine.py").resolve()
AUTO_LOAD = "Antigravity loads ~/.gemini/config/hooks.json automatically."
SHELLS = ("sh", "bash", "zsh")
_SHELL_SEPS = frozenset((";", "&&", "||", "|", "&", "(", ")"))
_ALLOWED_FORMATS = frozenset(("auto", "antigravity"))


def hooks_path():
    return Path(os.environ.get(ENV) or Path.home() / ".gemini" / "config" / "hooks.json")


def command():
    inner = (': %s; E=%s; [ -f "$E" ] && command -v python3 >/dev/null 2>&1 '
             '&& exec python3 "$E" guard --format antigravity; cat >/dev/null; printf "{}\\n"; exit 0') % (
        MARKER, shlex.quote(str(ENGINE)))
    return "/bin/sh -c " + shlex.quote(inner)


def _entry():
    return {"Stop": [{"type": "command", "command": command(), "timeout": 10}]}


def _load(path=None):
    p = hooks_path() if path is None else Path(path)
    try:
        raw = p.read_bytes()
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("top-level JSON must be an object")
    except FileNotFoundError:
        return None, {}
    except (OSError, ValueError, UnicodeDecodeError) as e:  # a sandbox denial too: never a traceback
        raise ValueError("cannot read %s as Antigravity hooks (%s); left unchanged" % (p, e))
    return raw, data


def _is_enabled(entry):
    return isinstance(entry, dict) and entry.get("enabled", True) is True


def _stop_handlers(entry):
    stops = entry.get("Stop") if isinstance(entry, dict) else None
    if not isinstance(stops, list):
        return []
    return [h for h in stops if isinstance(h, dict) and h.get("type", "command") == "command"]


def _has_current_command(entry):
    if not _is_enabled(entry):
        return False
    handlers = _stop_handlers(entry)
    return len(handlers) == 1 and handlers[0].get("command") == command()


def _split_tokens(text):
    try:
        lexer = shlex.shlex(text, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        return list(lexer)
    except ValueError:
        return text.split()


def _guard_format_ok(tokens):
    positions = [i for i, tok in enumerate(tokens) if tok == "guard"]
    if not positions:
        return False
    for i in positions:
        fmt = "auto"
        j = i + 1
        while j < len(tokens) and tokens[j] not in _SHELL_SEPS:
            tok = tokens[j]
            if tok == "--format":
                fmt = tokens[j + 1] if j + 1 < len(tokens) and tokens[j + 1] not in _SHELL_SEPS else ""
                j += 2
                continue
            if tok.startswith("--format="):
                fmt = tok.split("=", 1)[1]
            j += 1
        if fmt not in _ALLOWED_FORMATS:
            return False
    return True


def _invokes_this_guard(cmd, project_root=None):
    if not isinstance(cmd, str) or not cmd.strip():
        return False
    if cmd == command():
        return True
    tokens = _split_tokens(cmd)
    if len(tokens) >= 2 and Path(tokens[0]).name == "env":
        tokens = tokens[1:]
    if len(tokens) >= 3 and Path(tokens[0]).name in SHELLS and tokens[1] in ("-c", "-lc"):
        tokens = _split_tokens(tokens[2])
    if not _guard_format_ok(tokens):
        return False
    bases = [Path(project_root) / ".agents"] if project_root is not None else []  # Antigravity runs project hooks from .agents
    for tok in tokens:
        var, sep, val = tok.partition("=")
        if sep and var.isidentifier():
            tok = val
        tok = os.path.expandvars(tok)
        if not tok or not tok.endswith("engine.py"):
            continue
        p = Path(tok).expanduser()
        candidates = [p] if p.is_absolute() else [b / p for b in bases]
        for c in candidates:
            try:
                if c.resolve() == ENGINE:
                    return True
            except OSError:
                continue
    return False


def _has_project_guard(entry, project_root):
    if not _is_enabled(entry):
        return False
    return any(_invokes_this_guard(h.get("command"), project_root) for h in _stop_handlers(entry))


def installed(project_root=None):
    """True when an active guard hook is installed globally or in project_root/.agents/hooks.json."""
    try:
        if _has_current_command(_load()[1].get(MARKER)):
            return True
    except ValueError:
        pass
    if project_root is not None:
        try:
            project_hooks = Path(project_root) / ".agents" / "hooks.json"
            if _has_project_guard(_load(project_hooks)[1].get(MARKER), project_root):
                return True
        except ValueError:
            pass
    return False


def install():
    """Add (or refresh) our named Stop hook. Returns True if the file changed."""
    original, data = _load()
    if _has_current_command(data.get(MARKER)):
        return False
    data[MARKER] = _entry()
    hookfile.write_json_with_backup(hooks_path(), original, data)
    return True


def uninstall():
    """Remove only our named hook entry. Returns True if the file changed."""
    original, data = _load()
    if original is None or MARKER not in data:
        return False
    del data[MARKER]
    hookfile.write_json_with_backup(hooks_path(), original, data)
    return True


def main(argv):
    try:
        if argv == ["--uninstall"]:
            print("Removed the guard hook from %s." % hooks_path() if uninstall()
                  else "No guard hook in %s; nothing to remove." % hooks_path())
            return 0
        if argv:
            print("usage: install_antigravity_hook.py [--uninstall]", file=sys.stderr)
            return 2
        changed = install()
    except ValueError as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    except OSError as e:
        print("error: cannot write %s (%s); if a sandbox blocks writes outside the workspace, "
              "rerun with non-workspace access approved" % (hooks_path(), e.strerror or e), file=sys.stderr)
        return 1
    if changed:
        print("Installed the guard hook in %s." % hooks_path())
    else:
        print("The guard hook is already installed; nothing changed in %s." % hooks_path())
    if changed and hooks_path().with_name(hooks_path().name + ".bak").exists():
        print("The previous file is kept as %s.bak." % hooks_path().name)
    print(AUTO_LOAD)
    return 0
