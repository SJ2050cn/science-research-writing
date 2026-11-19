"""Submission checks: a submitted result against its step's expect in workflow.json.

accept(expect, payload, context) refuses with errors.Malformed unless the payload has exactly
the expected fields, each valid for its type. context is the step's context, the one the
agent was shown: choice (context.options), list[part] (context.lines and context.sections)
and list[int] (numbers of context.items) are checked against it. Checks that need more of
the run, such as review findings against the input, stay with the step that accepts them.
CHECKS has one checker per type name; check_types refuses a workflow.json naming any other.
"""
from pathlib import Path

from .errors import Malformed

FINDING = ("severity", "where", "rule", "problem", "source", "rewrite")
RECORD = {  # the string fields of each list[<record>] item; flags is a list, checked by its step
    "profile-entry": ("heading", "text", "replaces"),
    "proposal": ("heading", "text", "evidence", "replaces"),
    "restatement": ("entry", "restatement", "flags", "question"),
    "change": ("entry", "action", "heading", "text", "reason"),
}


def _path(name, v, spec, ctx):
    if not isinstance(v, str) or not Path(v).is_file():
        raise Malformed("%s must be the path of an existing file" % name)
    try:
        Path(v).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise Malformed("%s must be a readable UTF-8 text file: %s" % (name, e))


def _strings(name, v, spec, ctx):
    if not isinstance(v, list) or not all(isinstance(i, str) for i in v):
        raise Malformed("%s must be a list of strings" % name)


def _conflicts(name, v, spec, ctx):
    _strings(name, v, spec, ctx)
    bare = [i for i in v if "?" not in i]
    if bare:
        raise Malformed("each conflict needs its question, ending in a question mark; none in: %s" % "; ".join(bare))


def _exceptions(name, v, spec, ctx):
    ok = isinstance(v, list) and all(
        isinstance(i, dict) and set(i) == {"item", "quote"}
        and all(isinstance(i[k], str) and i[k].strip() for k in i) for i in v)
    if not ok:
        raise Malformed("%s must be a list of {item, quote} with non-empty strings; "
                        "quote is the author's own words" % name)


def _enum(name, v, spec, ctx):
    if v not in spec["values"]:
        raise Malformed("%s must be one of: %s" % (name, ", ".join(spec["values"])))


def _choice(name, v, spec, ctx):
    if v not in ctx["options"]:
        raise Malformed("%s must be exactly one of: %s" % (name, ", ".join(ctx["options"])))


def _findings(name, v, spec, ctx):
    if not isinstance(v, list):
        raise Malformed("%s must be a list of {%s}" % (name, ", ".join(FINDING)))
    for i, f in enumerate(v, 1):
        if not (isinstance(f, dict) and set(f) == set(FINDING) and all(isinstance(f[k], str) for k in FINDING)):
            raise Malformed("finding %d must have exactly the string fields: %s" % (i, ", ".join(FINDING)))
        for k in ("where", "rule", "problem", "source", "rewrite"):
            if not f[k].strip():
                raise Malformed("finding %d: %s must not be empty" % (i, k))


def _int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _numbers(name, v, spec, ctx):
    n = len(ctx["items"])
    if not isinstance(v, list) or not all(_int(i) for i in v) or len(set(v)) != len(v) \
            or any(not 1 <= i <= n for i in v):
        raise Malformed("%s must be distinct item numbers from 1 to %d" % (name, n))


def _parts(name, v, spec, ctx):
    """The model's split of a plain-text manuscript: contiguous 1-based line ranges
    that start at line 1 and end at the last line."""
    n, sections = ctx["lines"], ctx["sections"]
    if not isinstance(v, list) or not v:
        raise Malformed("%s must be a non-empty list of {section, start, end}" % name)
    expected = 1
    for i, p in enumerate(v, 1):
        if not (isinstance(p, dict) and set(p) == {"section", "start", "end"}
                and isinstance(p["section"], str) and _int(p["start"]) and _int(p["end"])):
            raise Malformed("part %d must be {section: string, start: integer, end: integer}" % i)
        if p["section"] not in sections:
            raise Malformed("part %d: section %r is not one of: %s" % (i, p["section"], ", ".join(sections)))
        if p["end"] < p["start"]:
            raise Malformed("part %d: end %d is before start %d" % (i, p["end"], p["start"]))
        if p["start"] > expected:
            raise Malformed("gap: lines %d-%d are in no part" % (expected, p["start"] - 1))
        if p["start"] < expected:
            raise Malformed("overlap: lines %d-%d are in part %d and the one before" % (p["start"], expected - 1, i))
        expected = p["end"] + 1
    if expected - 1 < n:
        raise Malformed("gap: lines %d-%d are in no part" % (expected, n))
    if expected - 1 > n:
        raise Malformed("the last part ends at line %d but the input has %d lines" % (expected - 1, n))


def _records(kind):
    keys = RECORD[kind]

    def check(name, v, spec, ctx):
        if not isinstance(v, list):
            raise Malformed("%s must be a list" % name)
        for n, item in enumerate(v, 1):
            if not isinstance(item, dict) or set(item) != set(keys):
                raise Malformed("%s item %d must have exactly the fields %s" % (name, n, list(keys)))
            for k in keys:
                if k != "flags" and not isinstance(item[k], str):
                    raise Malformed("%s item %d: %s must be a string" % (name, n, k))
    return check


CHECKS = {
    "path": _path, "list[string]": _strings, "list[conflict]": _conflicts, "list[exception]": _exceptions,
    "enum": _enum, "choice": _choice, "list[finding]": _findings, "list[int]": _numbers, "list[part]": _parts,
    **{"list[%s]" % k: _records(k) for k in RECORD},
}


def check_types(data):
    """Raise ValueError if a step in workflow.json expects a field type with no checker."""
    bad = ["%s.%s: %s" % (sid, f, spec["type"]) for sid, s in data["steps"].items()
           for f, spec in ((s.get("expect") or {}).get("fields") or {}).items() if spec["type"] not in CHECKS]
    if bad:
        raise ValueError("workflow.json: field types with no checker: " + ", ".join(bad))


def accept(expect, payload, context=None):
    """Refuse (errors.Malformed) unless payload has exactly expect's fields, each of its type."""
    if not isinstance(payload, dict):
        raise Malformed("result must be a JSON object with fields: " + ", ".join(expect["fields"]))
    missing = [k for k in expect["fields"] if k not in payload]
    extra = [k for k in payload if k not in expect["fields"]]
    if missing or extra:
        raise Malformed("fields wrong: missing %s, unexpected %s; expected exactly %s"
                        % (missing or "none", extra or "none", list(expect["fields"])))
    for name, spec in expect["fields"].items():
        CHECKS[spec["type"]](name, payload[name], spec, context)
