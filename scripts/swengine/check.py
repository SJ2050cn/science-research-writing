"""Integrity checker: pure functions, no I/O. Compares the author's input with the
output and reports failures; declared exceptions excuse matching failures.

Checked: numbers added or removed, citation groups (keys and grouping), and
\\label / \\ref / \\eqref removal. Counted: placeholders. Not checked, and the
output says so: citation placement, spelled-out quantities.

shortcut: numbers and citations compare as sets/multisets of tokens, so a moved
citation or a reordered number passes. That is the "not verified" caveat.
"""
import re
from collections import Counter

# \cite, \Citep, \parencite, \textcite ... with optional [pre][post] arguments; the plural
# forms (\cites{a}{b}) repeat the key group.
CITE_CMD = re.compile(r"\\[A-Za-z]*[Cc]ite[A-Za-z]*\*?")
CITE_ARGS = re.compile(r"(?:\s*\[[^\]]*\]){0,2}\s*\{([^}]*)\}")
MD_CITE = re.compile(r"\[(@[^\]]+)\]")
NUMBERED_CITE = re.compile(r"\[(\d+(?:\s*[,\u2013-]\s*\d+)*)\]")
RANGE_DASH = re.compile(r"\s*[\u2013-]\s*")
REF = re.compile(r"\\(label|ref|eqref|cref|Cref|autoref|pageref)\s*\{([^}]*)\}")
# Commands whose argument is an identifier, not prose: digits in it are not numbers.
IDENT_ARG = re.compile(
    r"\\(?:[A-Za-z]*ref|label|url|href|input|include|includegraphics|bibliography|"
    r"bibliographystyle|usepackage|documentclass)\*?(?:\s*\[[^\]]*\])*\s*\{[^}]*\}")
PLACEHOLDER = re.compile(r"\[placeholder:[^\]]*\]")
NUMBER = re.compile(r"\d+(?:\.\d+)?")
# A separator between digit groups: 1\,000  1{,}000  1,000  1~000  1\nobreakspace{}000
THIN = re.compile(r"(?<=\d)(?:\\[,;:! ]|\\(?:nobreakspace|thinspace)(?:\{\})?|\{,\}|[,~   ])(?=\d{3}(?!\d))")
SPACING = re.compile(r"\\[,;:! ]|~|\\nobreakspace|\\thinspace")

NOT_VERIFIED = "citation placement relative to its claim, spelled-out quantities"


def _keys(group):
    return ",".join(sorted(k.strip() for k in group.split(",") if k.strip()))


def _numbered(group):
    """[2,1] and [1,2] are one group, and an en dash is a hyphen; a merged or split group is not."""
    parts = [RANGE_DASH.sub("-", p.strip()) for p in group.split(",")]
    return ",".join(sorted(parts, key=lambda p: int(p.split("-")[0])))


def latex_cites(text):
    """Every LaTeX citation command: [(start, end, [key group, ...])]. \\cites{a}{b} has two groups."""
    found, pos = [], 0
    while True:
        m = CITE_CMD.search(text, pos)
        if not m:
            return found
        end, groups = m.end(), []
        a = CITE_ARGS.match(text, end)
        while a:
            groups.append(_keys(a.group(1)))
            end = a.end()
            a = CITE_ARGS.match(text, end) if m.group().rstrip("*").lower().endswith("cites") else None
        if groups:
            found.append((m.start(), end, groups))
        pos = max(end, m.end())


def citation_groups(text, markup):
    """Canonical key groups of every citation, in order of appearance."""
    spans = []
    if markup == "latex":
        spans += [(start, g) for start, _, groups in latex_cites(text) for g in groups]
    if markup == "markdown":
        spans += [(m.start(), ",".join(sorted(re.findall(r"@([^\s;,\]]+)", m.group(1)))))
                  for m in MD_CITE.finditer(text)]
    if markup in ("markdown", "plain"):
        spans += [(m.start(), _numbered(m.group(1))) for m in NUMBERED_CITE.finditer(text)]
    return [g for _, g in sorted(spans)]


def references(text):
    return Counter((m.group(1), m.group(2).strip()) for m in REF.finditer(text))


def numbers(text, markup):
    """Numeric tokens after dropping citations, identifiers and placeholders and
    normalising LaTeX spacing and thousands separators."""
    t = PLACEHOLDER.sub(" ", text)
    if markup == "latex":
        for start, end, _ in reversed(latex_cites(t)):
            t = t[:start] + " " + t[end:]
    else:
        for rx in (MD_CITE, NUMBERED_CITE):
            t = rx.sub(" ", t)
    t = IDENT_ARG.sub(" ", t)
    t = THIN.sub("", t)
    t = SPACING.sub(" ", t)
    return NUMBER.findall(t)


def _canon(item):
    """Let an exception name an item the way the author or model would write it."""
    item = item.strip()
    cites = latex_cites(item)
    if cites:
        return cites[0][2][0]
    m = REF.search(item)
    if m:
        return "\\%s{%s}" % (m.group(1), m.group(2).strip())
    return item


def find_failures(inp, out, markup):
    fails = []
    nin, nout = numbers(inp, markup), numbers(out, markup)
    for n in dict.fromkeys(nout):
        if n not in nin:
            fails.append(("number_added", n, "number %s is in the output but not in the input" % n))
    for n in Counter(nin) - Counter(nout):  # each occurrence counts: 5 and 5 mm -> 5 mm drops one
        fails.append(("number_removed", n, "number %s is in the input but missing from the output" % n))
    cin, cout = Counter(citation_groups(inp, markup)), Counter(citation_groups(out, markup))
    for g in cout - cin:
        fails.append(("citation_added", g, "citation group {%s} is in the output but not in the input" % g))
    for g in cin - cout:
        fails.append(("citation_removed", g, "citation group {%s} is in the input but missing from the output" % g))
    for (cmd, key) in references(inp) - references(out):
        fails.append(("reference_removed", "\\%s{%s}" % (cmd, key),
                      "\\%s{%s} is in the input but missing from the output" % (cmd, key)))
    return fails


def _report(fails, exceptions, placeholders):
    """Apply declared exceptions to (kind, item, message) failures; build the report."""
    declared = {_canon(e["item"]): e for e in exceptions}
    failures, excepted, used = [], [], set()
    for kind, item, msg in fails:
        ex = declared.get(item)
        if ex:
            used.add(item)
            excepted.append({"kind": kind, "item": item, "message": msg, "quote": ex["quote"]})
        else:
            failures.append({"kind": kind, "item": item, "message": msg})
    return {
        "passed": not failures, "failures": failures, "excepted": excepted,
        "unused_exceptions": [e for k, e in declared.items() if k not in used],
        "placeholders": placeholders,
        "not_verified": NOT_VERIFIED,
    }


def run(inp, out, markup, exceptions):
    """Revise. exceptions: [{item, quote}]. Returns the check report (JSON-ready)."""
    return _report(find_failures(inp, out, markup), exceptions, PLACEHOLDER.findall(out))


def _added(src, out, markup, where="the notes", label=""):
    """Numbers and citation groups in out that src lacks (the draft and review rule)."""
    fails = []
    nsrc = numbers(src, markup)
    for n in dict.fromkeys(numbers(out, markup)):
        if n not in nsrc:
            fails.append(("number_added", n, "%snumber %s is not in %s" % (label, n, where)))
    for g in Counter(citation_groups(out, markup)) - Counter(citation_groups(src, markup)):
        fails.append(("citation_added", g, "%scitation group {%s} is not in %s" % (label, g, where)))
    return fails


def run_draft(notes, out, markup, exceptions):
    """Draft: the text may add no number or citation that the notes lack."""
    return _report(_added(notes, out, markup), exceptions, PLACEHOLDER.findall(out))


def run_review(findings, markup, exceptions):
    """Review: each rewrite may add no number or citation to its source sentence and
    must keep the source's citations, labels and references. Source quotes are validated before this runs."""
    fails, placeholders = [], []
    for i, f in enumerate(findings, 1):
        label = "finding %d: rewrite: " % i
        fails += _added(f["source"], f["rewrite"], markup, "its source sentence", label)
        for g in Counter(citation_groups(f["source"], markup)) - Counter(citation_groups(f["rewrite"], markup)):
            fails.append(("citation_removed", g, "%scitation group {%s} of the source sentence is dropped" % (label, g)))
        for cmd, key in references(f["source"]) - references(f["rewrite"]):
            fails.append(("reference_removed", "\\%s{%s}" % (cmd, key),
                          "%s\\%s{%s} of the source sentence is dropped" % (label, cmd, key)))
        placeholders += PLACEHOLDER.findall(f["rewrite"])
    return _report(fails, exceptions, placeholders)
