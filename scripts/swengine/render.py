"""Output renderer: turns the run's artifact (modes.artifact), the model's report and the
check report into the fixed template from references/workflow.json. Pure functions."""
import re


def _fence(text, language):
    # Longer than any backtick run inside, so the author's own code fences survive.
    ticks = "`" * max(3, max((len(r) for r in re.findall(r"`+", text)), default=0) + 1)
    return "%s%s\n%s\n%s" % (ticks, language, text.rstrip("\n"), ticks)


def _bullets(items, none):
    return "\n".join("- " + i for i in items) if items else none


def _check_line(report, tpl, mode):
    t = tpl["check"]
    ph = report["placeholders"]
    ex = report["excepted"]
    fmt = {
        "verified": t.get("verified_" + mode, t["verified"]), "not_verified": t["not_verified"], "count": "%d failure(s)" % len(report["failures"]),
        "placeholders": "%d (%s)" % (len(ph), "; ".join(ph)) if ph else "none",
        "exceptions": "%d (%s)" % (len(ex), "; ".join("%s: \"%s\"" % (e["item"], e["quote"]) for e in ex))
        if ex else "none",
    }
    return t["passed" if report["passed"] else "failed"].format(**fmt)


def _table(findings, block, none):
    """Findings sorted high to low (input order within a severity), numbered after sorting."""
    if not findings:
        return none
    rank = {v: i for i, v in enumerate(block["sort"])}
    rows = sorted(findings, key=lambda f: rank[f["severity"]])
    cell = lambda v: " ".join(str(v).split()).replace("|", "\\|")
    lines = ["| " + " | ".join(block["columns"]) + " |", "|" + "---|" * len(block["columns"])]
    for n, f in enumerate(rows, 1):
        vals = [n] + [f[k] for k in ("severity", "where", "rule", "problem", "rewrite")]
        lines.append("| " + " | ".join(cell(v) for v in vals) + " |")
    return "\n".join(lines)


def render(plan, mode, markup, artifact, report_fields, check_report, tpl):
    """artifact: {text} or {findings}. report_fields: the model's changes/questions/conflicts/deviations lists."""
    sources = {
        **artifact,
        "deviations": report_fields["deviations"] + [
            "Accepted exception, %s (author asked: \"%s\")" % (e["item"], e["quote"])
            for e in check_report["excepted"]] + [
            "Declared exception not needed, %s (author asked: \"%s\")" % (e["item"], e["quote"])
            for e in check_report["unused_exceptions"]],
        "check": _check_line(check_report, tpl, mode),
        "placeholders": check_report["placeholders"],
    }
    parts = []
    if not check_report["passed"]:
        parts.append(tpl["check"]["notice"].format(
            failures="; ".join(f["message"] for f in check_report["failures"])))
    parts.append(plan)
    for block in tpl[mode]:
        body = sources.get(block["from"], report_fields.get(block["from"]))
        if block["as"] == "table":
            body = _table(body, block, tpl["none"])
        elif block["as"] == "fence":
            body = _fence(body, tpl["fence_language"][markup])
        elif block["as"] == "list":
            body = _bullets(body, tpl["none"])
        parts.append("## " + block["heading"] + "\n\n" + body)
    return "\n\n".join(parts) + "\n"
