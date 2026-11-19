"""Field classifier. Code decides what it can see in the input; the model's readings
(--section, --mode) are only compared with it. A difference is never resolved here:
it becomes an ask step (see workflow.begin). Pure functions.

  markup   latex | markdown | plain, from the syntax present
  mode     draft when the input has no full paragraph (notes), else revise; for a title,
           revise when it is one short line of title text and draft for notes or a paragraph;
           review only when the model reports that an assessment was requested
  section  from the headings: one known heading names it, two or more make it whole-paper
"""
import re

LATEX = re.compile(r"\\[A-Za-z]+\*?(?:\[[^\]]*\])?\{")
MARKDOWN = re.compile(r"(?m)^#{1,6}\s+\S|\[@[^\]]+\]|\*\*[^*\n]+\*\*|\[[^\]\n]+\]\([^)\n]+\)|^```")
# Lines that are not running prose: list items, headings, structural commands.
NOT_PROSE = re.compile(
    r"^\s*(?:[-*+\u2022]\s|\d+[.)]\s|\\item\b|#|\\(?:section|subsection|label|begin|end|title|"
    r"maketitle|documentclass|usepackage|author)\b)")
LIST_ITEM = re.compile(r"^\s*(?:[-*+\u2022]\s|\d+[.)]\s|\\item\b)")
TITLE_WORDS = 30  # a title line longer than this is a paragraph to draft a title from
LATEX_HEADING = re.compile(
    r"\\(?:section|chapter)\*?\{([^}]*)\}|(\\title)\{|\\begin\{(abstract)\}")
MD_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
NUMBERING = re.compile(r"^(?:\d+(?:\.\d+)*\.?|[IVX]+\.)\s+")


def lines_of(text):
    """Lines with their line ends, split at \\n only (the unit of every line range)."""
    return re.findall(r"[^\n]*\n|[^\n]+", text)


def markup(text):
    if LATEX.search(text):
        return "latex"
    return "markdown" if MARKDOWN.search(text) else "plain"


def mode(text, section=None):
    """draft when no block of the text is a full paragraph (two sentences, 20 words).
    A title is revised only when the text is one short line, no list item, no full paragraph."""
    paragraph = any(
        len(prose.split()) >= 20 and len(re.findall(r"[.!?](?:\s|$)", prose)) >= 2
        for prose in (" ".join(l.strip() for l in block.splitlines() if l.strip() and not NOT_PROSE.match(l))
                      for block in re.split(r"\n\s*\n", text)))
    if section == "title":
        lines = [l for l in text.splitlines() if l.strip()]
        one = len(lines) == 1 and not LIST_ITEM.match(lines[0]) and len(lines[0].split()) <= TITLE_WORDS
        return "revise" if one and not paragraph else "draft"
    return "revise" if paragraph else "draft"


def _section_of(name, headings):
    name = NUMBERING.sub("", name.strip().strip("*").strip()).rstrip(".:").lower()
    return next((s for s, names in headings.items() if name in names), None)


def headings(text, kind, data):
    """Section headings in order: [(line index, section or 'other', recognised)].
    LaTeX: \\section, \\title, abstract environment. Markdown: the heading level of the
    known headings. Plain: a line that is only a known heading (kept for the single-section
    case; plain whole papers are split by the model)."""
    known = data["headings"]
    found = []
    for i, line in enumerate(lines_of(text)):
        if kind == "latex":
            m = LATEX_HEADING.search(line)
            if m:
                name = m.group(1) if m.group(1) is not None else ("title" if m.group(2) else m.group(3))
                found.append((i, name, None))
        elif kind == "markdown":
            m = MD_HEADING.match(line.rstrip("\r\n"))
            if m:
                found.append((i, m.group(2), len(m.group(1))))
        elif line.strip() and len(line) < 60 and _section_of(line, known):
            found.append((i, line, None))
    out = [(i, _section_of(n, known), lvl) for i, n, lvl in found]
    if kind == "markdown":
        levels = [lvl for _, s, lvl in out if s]
        out = [(i, s, lvl) for i, s, lvl in out if levels and lvl == min(levels)]
    return [(i, s or "other", s is not None) for i, s, _ in out]


def section(text, kind, data):
    """The section the headings settle, or None. Needs one known heading at least."""
    hs = headings(text, kind, data)
    if not any(known for _, _, known in hs):
        return None
    return "whole-paper" if len(hs) > 1 else hs[0][1]


def split(text, kind, data):
    """Code split of a LaTeX or Markdown manuscript: [(section, first line, last line)],
    1-based, covering every line. Text before the first heading joins the first section."""
    n = len(lines_of(text))
    hs = headings(text, kind, data)
    starts = [i for i, _, _ in hs] or [0]
    names = [s for _, s, _ in hs] or ["other"]
    starts[0] = 0  # shortcut: no separate preamble part; upgrade if preambles need their own pass
    ends = [s for s in starts[1:]] + [n]
    return [(names[k], starts[k] + 1, ends[k]) for k in range(len(starts))]


SHAPES = ({"draft": "no full paragraphs", "revise": "full paragraphs"},
          {"draft": "notes or a paragraph", "revise": "one short line of title text"})  # by title or not


def decide(text, model_section, model_mode, data):
    """Returns (fields, asks). fields: section, mode, markup; a value is None while an ask
    is open for it. asks: the fixed questions to put to the author, in order."""
    kind = markup(text)
    code_section = section(text, kind, data)
    code_mode = mode(text, code_section or model_section)
    asks = []

    def ask(field, key, options, **fmt):
        asks.append({"field": field, "options": options,
                     "question": data["asks"][key].format(**fmt)})

    if code_section is None and model_section is None:
        sec = None
        ask("section", "section_unknown", [s for s in data["fields"]["section"]])
    elif code_section is not None and model_section not in (None, code_section):
        sec = None
        ask("section", "section_conflict", [code_section, model_section],
            code=code_section, model=model_section)
    else:
        sec = code_section or model_section
    if model_mode in (None, "review", code_mode):
        md = model_mode or code_mode
    else:
        md = None
        ask("mode", "mode_conflict", [code_mode, model_mode], code=code_mode, model=model_mode,
            shape=SHAPES[sec == "title"][code_mode])
    return {"section": sec, "mode": md, "markup": kind}, asks
