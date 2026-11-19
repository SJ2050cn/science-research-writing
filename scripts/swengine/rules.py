"""Rule names. A rule is a top-level list item in a reference file whose text starts
with a bold plain-English name: `- **Name.** text` or `1. **Name.** text`. The
reference files are the single source; nothing here repeats a name."""
import re
from pathlib import Path

NAME = re.compile(r"^(?:- |\d+\. )\*\*(.+?)\.\*\*", re.M)


def names(path):
    """Rule names of one reference file, in file order."""
    return NAME.findall(Path(path).read_text(encoding="utf-8"))


def known(paths):
    """Every rule name in the given files (the files a review step reads)."""
    return {n for p in paths for n in names(p)}
