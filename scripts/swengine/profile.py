"""Profile store: the author's style profile, outside the skill folder.

Location: $SCIENCE_RESEARCH_WRITING_PROFILE_DIR if set, else
~/.agents/science-research-writing/. The file is user-style.md. The old
location is user-style.md in the skill folder ($SCIENCE_RESEARCH_WRITING_LEGACY_DIR
overrides it, for tests); migrate() moves it once.

All writes go through apply(), which changes nothing unless every operation
succeeds: only the fixed headings, only the four sources, at most five
exemplars, the (source, date) tag added here, never an entry removed unless
asked. What to write is the model's decision.
"""
import os
import re
import shutil
from datetime import date
from pathlib import Path

from . import errors

PROFILE_ENV = "SCIENCE_RESEARCH_WRITING_PROFILE_DIR"
LEGACY_ENV = "SCIENCE_RESEARCH_WRITING_LEGACY_DIR"
NAME = "user-style.md"
SKILL_ROOT = Path(__file__).resolve().parents[2]
TAG = re.compile(r"\s*\((stated|corrected|scanned|edited), \d{4}-\d{2}-\d{2}\)$")


def profile_dir():
    return Path(os.environ.get(PROFILE_ENV) or Path.home() / ".agents" / "science-research-writing")


def path():
    return profile_dir() / NAME


def legacy_path():
    return Path(os.environ.get(LEGACY_ENV) or SKILL_ROOT) / NAME


def _fail(message):
    raise errors.EngineError(errors.PROFILE, message)


class ProfileIOError(errors.EngineError):
    """Filesystem failure accessing the shared style profile outside the workspace sandbox."""
    def __init__(self, message):
        super().__init__(errors.PROFILE, message)


def _io_error(target, action, exc):
    return ProfileIOError(
        "cannot %s the style profile at %s (%s). The shared style profile sits outside the workspace "
        "sandbox; rerun this command with non-workspace access approved (or allow access to %s)."
        % (action, target, exc.strerror or exc, profile_dir()))


def migrate():
    """Move the in-folder profile to the new location, once. Returns (notice, conflict)."""
    old, new = legacy_path(), path()
    try:
        has_old = old.is_file()
    except OSError as e:
        raise _io_error(old, "read", e)
    if not has_old:
        return None, False
    try:
        has_new = new.exists()
    except OSError as e:
        raise _io_error(new, "read", e)
    if has_new:
        return ("Both %s (old location) and %s exist. Nothing was overwritten; the author is asked which to keep."
                % (old, new)), True
    try:
        new.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(old), str(new))
    except OSError as e:
        raise _io_error(new, "move", e)
    return "Your style profile was moved from %s to %s so that updating the skill cannot delete it." % (old, new), False


def resolve_conflict(choice):
    """Both files exist: nothing is lost. The loser is kept beside the profile as user-style.<name>.md."""
    old, new = legacy_path(), path()
    try:
        if choice == "keep-profile":
            shutil.move(str(old), str(new.with_name("user-style.in-folder.md")))
        else:
            backup = new.with_name("user-style.previous.md")
            shutil.move(str(new), str(backup))
            try:
                shutil.move(str(old), str(new))
            except OSError:
                try:
                    shutil.move(str(backup), str(new))
                except OSError:
                    pass
                raise
    except OSError as e:
        raise _io_error(new, "move", e)


def bullets(text):
    """[(heading, line index, body)] for each '- ' entry under a '## ' heading."""
    out, heading = [], None
    for i, ln in enumerate(text.split("\n")):
        if ln.startswith("## "):
            heading = ln[3:].strip()
        elif ln.startswith("- ") and heading:
            out.append((heading, i, ln[2:].strip()))
    return out


def check_entry(heading, body, source, rules):
    """Raise unless heading, source and one-line text are acceptable for a new entry."""
    if heading not in rules["headings"]:
        _fail("heading %r is not allowed; choose one of: %s" % (heading, "; ".join(rules["headings"])))
    if source not in rules["sources"]:
        _fail("source %r is not allowed; choose one of: %s" % (source, ", ".join(rules["sources"])))
    if not isinstance(body, str) or not body.strip() or "\n" in body or TAG.search(body):
        _fail("an entry is one non-empty line without a tag; the engine adds (source, date)")


def _find(lines, old):
    old = old[2:] if old.startswith("- ") else old
    hits = [i for h, i, b in bullets("\n".join(lines)) if b == old.strip() or TAG.sub("", b) == old.strip()]
    if len(hits) != 1:
        _fail("%s entry matching %r in the profile" % ("no" if not hits else "more than one", old))
    return hits[0]


def _insert(lines, heading, bullet):
    try:
        h = lines.index("## " + heading)
    except ValueError:
        # shortcut: a hand-edited file missing a heading gets it appended; reorder by hand if it matters.
        lines += ["", "## " + heading]
        h = len(lines) - 1
    end = next((i for i in range(h + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    last = max((i for i in range(h + 1, end) if lines[i].strip()), default=h)
    lines.insert(last + 1, bullet)


def exists():
    """Whether the profile file exists; raises ProfileIOError if the folder cannot be inspected."""
    target = path()
    try:
        return target.is_file()
    except OSError as e:
        raise _io_error(target, "read", e)


def check_accessible():
    """Verify the profile location can be inspected before creating a run; raises ProfileIOError if not."""
    exists()


def read():
    """The profile's text, or None when there is no profile yet."""
    target = path()
    try:
        return target.read_text(encoding="utf-8") if target.is_file() else None
    except OSError as e:
        raise _io_error(target, "read", e)


def read_bytes():
    """The profile's raw bytes, or None when there is no profile yet."""
    target = path()
    try:
        return target.read_bytes() if target.is_file() else None
    except OSError as e:
        raise _io_error(target, "read", e)


def find_old(old):
    """Raise unless exactly one existing entry matches old (with or without its tag)."""
    _find((read() or "").split("\n"), old)


def apply(ops, rules):
    """ops: [{op: add|replace|remove, heading, text, source, old}]. All or nothing.
    Returns one announcement line per op. rules: the 'profile' block of workflow.json."""
    target = path()
    text = read()
    if text is None:
        text = (SKILL_ROOT / "references" / "profile-template.md").read_text(encoding="utf-8")
    lines = text.rstrip("\n").split("\n")
    today, said = date.today().isoformat(), []
    for o in ops:
        if o["op"] in ("replace", "remove"):
            i = _find(lines, o["old"])
            old_body = lines.pop(i)[2:]
        if o["op"] == "remove":
            said.append("Removed from your style profile: %s" % old_body)
            continue
        heading, body, source = o["heading"], o["text"], o["source"]
        check_entry(heading, body, source, rules)
        _insert(lines, heading, "- %s (%s, %s)" % (body.strip(), source, today))
        said.append("Saved to your style profile, %s: %s (%s, %s)" % (heading, body.strip(), source, today)
                    + (" Replaced: %s" % old_body if o["op"] == "replace" else ""))
        ex = [b for h, _, b in bullets("\n".join(lines)) if h == "Exemplars"]
        if len(ex) > rules["exemplar_limit"]:
            _fail("the profile already holds %d exemplars; which one should be dropped? Current exemplars: %s"
                  % (rules["exemplar_limit"], " | ".join(ex[:-1])))
    tmp = target.with_name(NAME + ".tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.replace(str(tmp), str(target))
    except OSError as e:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise _io_error(target, "write", e)
    return said
