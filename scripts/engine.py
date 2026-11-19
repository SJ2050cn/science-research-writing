#!/usr/bin/env python3
"""Step engine for the science-research-writing skill (entry point).

Python 3.9+, standard library only. The code lives in the swengine package
next to this file; this stub only makes it importable.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from swengine.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
