"""Keeps every engine run away from the author's real profile and home folder."""
import os
from pathlib import Path

PROFILE_ENV = "SCIENCE_RESEARCH_WRITING_PROFILE_DIR"
LEGACY_ENV = "SCIENCE_RESEARCH_WRITING_LEGACY_DIR"
HOOKS_ENV = "SCIENCE_RESEARCH_WRITING_CODEX_HOOKS"
ANTIGRAVITY_HOOKS_ENV = "SCIENCE_RESEARCH_WRITING_ANTIGRAVITY_HOOKS"
LOCK_ENV = "SCIENCE_RESEARCH_WRITING_SKILLS_LOCK"
REAL_HOME = Path(os.path.expanduser("~")).resolve()  # captured before any test patches HOME
REAL_DIRS = (REAL_HOME / ".codex", REAL_HOME / ".agents", REAL_HOME / ".claude", REAL_HOME / ".gemini")


def sandbox_env(base):
    """Environment overrides that point the profile, the old in-folder profile, the Codex and
    Antigravity hooks files, the skills lock file and HOME into base."""
    base = Path(base)
    return {PROFILE_ENV: str(base / "profile"), LEGACY_ENV: str(base / "legacy"), "HOME": str(base / "home"),
            HOOKS_ENV: str(base / "codex" / "hooks.json"),
            ANTIGRAVITY_HOOKS_ENV: str(base / "antigravity" / "hooks.json"),
            LOCK_ENV: str(base / "skill-lock.json")}


def _in_real_dirs(path):
    p = Path(path).resolve()
    return any(d == p or d in p.parents for d in REAL_DIRS)


def assert_sandboxed(env):
    """Fail if an engine run would use the default profile or real agent home directories."""
    d = env.get(PROFILE_ENV)
    if not d:
        raise AssertionError("%s is not set: the engine would use the default profile location" % PROFILE_ENV)
    if _in_real_dirs(d):
        raise AssertionError("profile location %s is inside the real home folder" % d)
    if env.get(LEGACY_ENV) and _in_real_dirs(env[LEGACY_ENV]):
        raise AssertionError("%s=%s is inside the real home folder" % (LEGACY_ENV, env[LEGACY_ENV]))
    for name in (HOOKS_ENV, ANTIGRAVITY_HOOKS_ENV, LOCK_ENV):
        if not env.get(name):
            raise AssertionError("%s is not set: the real home folder would be used" % name)
        if _in_real_dirs(env[name]):
            raise AssertionError("%s=%s is inside the real home folder" % (name, Path(env[name]).resolve()))
    if env.get("HOME"):
        home = Path(env["HOME"]).resolve()
        if home == REAL_HOME or _in_real_dirs(home):
            raise AssertionError("HOME is the real home folder")
