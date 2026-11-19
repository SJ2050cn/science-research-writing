"""Keeps every engine run away from the author's real profile and home folder."""
import os
from pathlib import Path

PROFILE_ENV = "SCIENCE_RESEARCH_WRITING_PROFILE_DIR"
LEGACY_ENV = "SCIENCE_RESEARCH_WRITING_LEGACY_DIR"
HOOKS_ENV = "SCIENCE_RESEARCH_WRITING_CODEX_HOOKS"
LOCK_ENV = "SCIENCE_RESEARCH_WRITING_SKILLS_LOCK"
REAL_HOME = Path(os.path.expanduser("~")).resolve()  # captured before any test patches HOME


def sandbox_env(base):
    """Environment overrides that point the profile, the old in-folder profile, the Codex hooks file,
    the skills lock file and HOME into base."""
    base = Path(base)
    return {PROFILE_ENV: str(base / "profile"), LEGACY_ENV: str(base / "legacy"), "HOME": str(base / "home"),
            HOOKS_ENV: str(base / "codex" / "hooks.json"), LOCK_ENV: str(base / "skill-lock.json")}


def assert_sandboxed(env):
    """Fail if an engine run would use the default profile location."""
    d = env.get(PROFILE_ENV)
    if not d:
        raise AssertionError("%s is not set: the engine would use the default profile location" % PROFILE_ENV)
    resolved = Path(d).resolve()
    if resolved == REAL_HOME / ".agents" or (REAL_HOME / ".agents") in resolved.parents:
        raise AssertionError("profile location %s is inside the real ~/.agents" % d)
    for name in (HOOKS_ENV, LOCK_ENV):
        if not env.get(name):
            raise AssertionError("%s is not set: the real home folder would be used" % name)
        p = Path(env[name]).resolve()
        if any(d == p or d in p.parents for d in (REAL_HOME / ".codex", REAL_HOME / ".agents", REAL_HOME / ".claude")):
            raise AssertionError("%s=%s is inside the real home folder" % (name, p))
    if env.get("HOME") and Path(env["HOME"]).resolve() == REAL_HOME:
        raise AssertionError("HOME is the real home folder")
