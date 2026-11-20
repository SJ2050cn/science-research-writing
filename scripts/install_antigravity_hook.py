#!/usr/bin/env python3
"""Install (or with --uninstall, remove) the science-research-writing guard in Antigravity's
~/.gemini/config/hooks.json. Keeps your other hooks, backs the file up to hooks.json.bak first,
and changes nothing on a second run. Python 3.9+, standard library only."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from swengine import antigravityhook  # noqa: E402

if __name__ == "__main__":
    sys.exit(antigravityhook.main(sys.argv[1:]))
