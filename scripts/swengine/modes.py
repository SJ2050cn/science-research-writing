"""What differs between modes when a main or fix result arrives: how the result is
checked against the run and which integrity check runs on it (its shape was checked
by submission.py), and what of the stored result the output shows (artifact). All
failures raise ValueError; the caller turns them into a refusal that returns the same step.

  revise  text file; input and output compared both ways (check.run)
  draft   text file; output may add no number or citation to the notes (check.run_draft)
  review  findings list; each quoted source sentence must be in the input and each
          rewrite is compared with its source sentence (check.run_review)
"""
import json
from pathlib import Path

from . import check

SEVERITY = ("high", "medium", "low")


def _flat(s):
    return " ".join(s.split())


def validate_findings(findings, inp, known_rules):
    """Rule name known, severity high|medium|low, source sentence word for word in the input
    (whitespace and line wraps do not count)."""
    flat = _flat(inp)
    for i, f in enumerate(findings, 1):
        if f["severity"] not in SEVERITY:
            raise ValueError("finding %d: severity %r is not one of %s" % (i, f["severity"], ", ".join(SEVERITY)))
        if f["rule"] not in known_rules:
            raise ValueError("finding %d: rule %r is not a rule name in the files to read; use a checklist "
                             "item, a language rule or a move of this section, exactly as written" % (i, f["rule"]))
        if _flat(f["source"]) not in flat:
            raise ValueError("finding %d: source is not word for word in the input: %r" % (i, f["source"]))


def ingest(mode, payload, inp, markup, exceptions, known_rules):
    """Returns (text, report). text is the final text to store, or None when the
    submitted JSON itself is the artifact (review)."""
    if mode == "review":
        validate_findings(payload["findings"], inp, known_rules)
        return None, check.run_review(payload["findings"], markup, exceptions)
    text = Path(payload["text_file"]).read_text(encoding="utf-8")
    run = check.run_draft if mode == "draft" else check.run
    return text, run(inp, text, markup, exceptions)


def artifact(mode, stored):
    """The output's source in a stored main or fix result: the findings of a review, else the text."""
    return {"findings": json.loads(stored)["findings"]} if mode == "review" else {"text": stored}
