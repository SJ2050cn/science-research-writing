"""Whole-paper runs: one run whose sections are processed one at a time, in manuscript
order, each as its own single-section sub-run.

Layout: <run>/parts/NN-<section>/ holds that section's input.txt, results/, check-report.json
and output.md, exactly like a single-section run folder. state["parts"] is a list of
{section, start, end, dir, state}, where state is the section's own run state (same run ID,
so every plan line names this run). At step parts the run hands each result to the current
section, a child Run (run.py). The top-level state stays open until the last section is
done, then the sections' outputs are joined into <run>/output.md.

Where the split comes from: LaTeX and Markdown are split by code (classify.split); plain text
is split by the model in a `split` step and accepted only without gaps and overlaps.
"""
import json

from . import classify, workflow

SEPARATOR = "\n---\n\n"


def _text(run):
    return run.folder.input_bytes().decode("utf-8")


def make_parts(run, ranges):
    """Create the section sub-runs for (section, first line, last line) ranges; returns the step parts."""
    state = run.state
    lines = classify.lines_of(_text(run))
    state["parts"], state["part"] = [], 0
    for k, (section, a, b) in enumerate(ranges, 1):
        name = run.folder.add_part(k, section, "".join(lines[a - 1:b]).encode("utf-8"))
        fields = dict(state["fields"], section=section)
        ps = workflow.new_state(state["id"], fields, state["sample_files"], state["agent"])
        ps["journal_model"] = state["journal_model"]
        state["parts"].append({"section": section, "start": a, "end": b, "dir": name, "state": ps})
    return "parts"


def enter(run):
    """The first step of the main part of a whole-paper run."""
    markup = run.state["fields"]["markup"]
    return "split" if markup == "plain" else make_parts(run, classify.split(_text(run), markup, run.data))


def _split_context(run):
    return {"lines": len(classify.lines_of(_text(run))),
            "sections": [x for x in run.data["fields"]["section"] if x != "whole-paper"]}


def _accept_split(run, payload):
    """The model's split, already checked for gaps and overlaps against the context (list[part])."""
    run.record("split", "json", json.dumps(payload, indent=2))
    return make_parts(run, [(p["section"], p["start"], p["end"]) for p in payload["parts"]])


def _accept_section(run, payload):
    """The current section takes the result. Once it is done, on to the next section; after
    the last one, join the sections' outputs and finish the run."""
    state = run.state
    run.child().accept(payload)
    if state["parts"][state["part"]]["state"]["status"] != "done":
        return "parts"
    state["part"] += 1
    if state["part"] < len(state["parts"]):
        return "parts"
    run.folder.put_output(SEPARATOR.join(run.folder.part(p["dir"]).output() for p in state["parts"]))
    return "done"


STEPS = {"split": workflow.Step(_accept_split, _split_context), "parts": workflow.Step(_accept_section)}
