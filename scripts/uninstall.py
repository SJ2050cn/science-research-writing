#!/usr/bin/env python3
"""Uninstall helper for the science-research-writing skill. Run it before removing the skill.

  uninstall.py [--keep-profile | --remove-profile]

Asks whether to delete your style profile (default: keep). Without a terminal, pass
--keep-profile or --remove-profile; with neither, the profile is kept. Removes the
guard hook from Codex's and Antigravity's hooks.json files (other hooks stay). Never
touches project logs (.agents/log/ in your projects). Prints, never runs, the command
that removes the skill: `npx skills remove science-research-writing -g` when the skills
lock file lists it, else the `rm` commands for a local install. Python 3.9+, standard
library only.
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from swengine import antigravityhook, codexhook, profile  # noqa: E402

NAME = "science-research-writing"
SKILL = Path(__file__).resolve().parents[1]
LOCK_ENV = "SCIENCE_RESEARCH_WRITING_SKILLS_LOCK"


def listed_in_lock():
    lock = Path(os.environ.get(LOCK_ENV) or Path.home() / ".agents" / ".skill-lock.json")
    try:
        return NAME in json.loads(lock.read_text(encoding="utf-8")).get("skills", {})
    except (OSError, ValueError, AttributeError):
        return False


def removal_commands():
    if listed_in_lock():
        return ["npx skills remove %s -g" % NAME]
    cmds = []
    for c in (Path.home() / ".claude" / "skills" / NAME,
              Path.home() / ".agents" / "skills" / NAME,
              Path.home() / ".gemini" / "config" / "skills" / NAME):
        if c.is_symlink():
            cmds.append('rm "%s"' % c)
        elif c.exists() and c.resolve() != SKILL:
            cmds.append('rm -rf "%s"' % c)
    return cmds + ['rm -rf "%s"' % SKILL]


def remove_profile():
    """Delete user-style*.md (the profile and its conflict backups), then the folder if it is empty."""
    folder = profile.profile_dir()
    files = sorted(folder.glob("user-style*.md")) if folder.is_dir() else []
    for f in files:
        f.unlink()
    if folder.is_dir() and not any(folder.iterdir()):
        folder.rmdir()
    return files


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--keep-profile", action="store_true")
    g.add_argument("--remove-profile", action="store_true")
    args = ap.parse_args(argv)

    path = profile.path()
    delete = args.remove_profile
    if not (args.keep_profile or args.remove_profile) and path.exists():
        if sys.stdin.isatty():
            delete = input("Delete your style profile at %s? [y/N] " % path).strip().lower() in ("y", "yes")
        else:
            print("No terminal and no flag: keeping your profile at %s (pass --remove-profile to delete it)." % path)

    failed = False
    for agent, hook in (("Codex", codexhook), ("Antigravity", antigravityhook)):
        try:
            print("Removed the %s guard hook." % agent if hook.uninstall() else "No %s guard hook to remove." % agent)
        except (OSError, ValueError) as e:  # a broken hooks file must not stop the rest of the uninstall
            print("error: could not remove the %s guard hook: %s" % (agent, e), file=sys.stderr)
            failed = True
    if delete:
        gone = remove_profile()
        print("Deleted your style profile (%d file%s)." % (len(gone), "" if len(gone) == 1 else "s"))
    elif path.exists():
        print("Kept your style profile at %s." % path)
    print("Project logs under .agents/log/ were not touched.")
    print("To finish, remove the skill itself with:")
    for c in removal_commands():
        print("  " + c)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
