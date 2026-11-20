"""Section runs: step definitions, the plan line, the run state, and the steps of a section.

A step definition 'id@mode' in workflow.json overrides 'id' for that mode (step_def). Each
step id the engine can be at has one entry in a STEPS table: Step(accept, context).
  context(run)          the step's context: shown to the agent in the step response, and
                        what its result is checked against
  accept(run, payload)  apply a result that passed the step's expect: record it, and return
                        the step to go to (run.py); raise errors.Malformed to refuse
The run (run.py) gives a step its state, data and folder (runstore.Folder), and record/store.
This module has the section steps: clarify (kind ask; context: field, question, options),
journal-model, the main step (revise, draft or review), fix, report. The integrity check
runs in code, right after every main or fix result. Whole papers add split and parts
(wholepaper.py), profiles their own steps (profile_flows.py), the guard setup (guard.py);
run.py joins the tables. While an ask is open the plan line is data["plan_pending"],
because mode or section is not known yet.
"""
import json
from collections import namedtuple
from pathlib import Path

from . import modes, profile, render, rules, runstore
from .errors import Malformed

SKILL_ROOT = Path(__file__).resolve().parents[2]
MAX_FIX = 2
NEXT = "<next queued>"  # a step's accept returns it to leave a step queued before the main step
Step = namedtuple("Step", "accept context", defaults=(None,))


def step_def(data, sid, mode):
    return data["steps"].get("%s@%s" % (sid, mode)) or data["steps"][sid]


def load_data():
    return json.loads((SKILL_ROOT / "references" / "workflow.json").read_text(encoding="utf-8"))


def plan_line(state, data, flags):
    """flags: the state whose guard=off and stalled flags show (a whole paper's, for a section)."""
    if state.get("task"):  # profile tasks have no section, markup or samples
        line = data["plan_task"].format(run=state["id"], task=state["task"])
    elif None in state["fields"].values():  # an ask is open: mode or section is not known yet
        return data["plan_pending"].format(run=state["id"])
    else:
        line = data["plan"].format(run=state["id"], **state["fields"])
    for flag, on in (("guard=off", flags.get("guard_off")), ("stalled", flags.get("stalled"))):
        line += " · " + flag if on else ""
    return line


def new_state(run_id, fields, sample_files, agent, asks=()):
    """The one constructor of a run state, for section runs, profile tasks and the sections of
    a whole paper. run.py adds the queue of steps before the main step to a run's own state."""
    return {
        "id": run_id, "agent": agent,
        "fields": fields, "sample_files": list(sample_files),
        "status": "open", "step": {"id": fields["mode"], "attempt": 1},
        "fix_attempts": 0, "exceptions": [], "text": None, "history": [],
        "asks": list(asks), "journal_model": None,
    }


def begin(run):
    """The first step of a freshly classified run: an open ask, else the journal model when
    sample papers came with it, else the main part of the run."""
    if run.state["asks"]:
        return "clarify"
    if run.state["fields"]["samples"] == "yes":
        return "journal-model"
    return main_part(run)


def main_part(run):
    f = run.state["fields"]
    if f["section"] == "whole-paper":
        from . import wholepaper
        return wholepaper.enter(run)
    return f["mode"]


def _routing_refs(run):
    r, f = run.data["routing"], run.state["fields"]
    return [str(SKILL_ROOT / n) for n in r["always"] + r["section"][f["section"]] + r["mode"][f["mode"]]]


def read_files(run, tokens):
    state, files = run.state, []
    for t in tokens:
        if t == "sample_files":
            files += [str(Path(f).resolve()) for f in state["sample_files"]]
        elif t == "journal_model":
            files += [state["journal_model"]] if state["journal_model"] else []
        elif t == "routing":
            files += _routing_refs(run)
            if profile.exists():
                files.append(str(profile.path()))
        elif t == "profile":
            if profile.exists():
                files.append(str(profile.path()))
        elif t.startswith("skill:"):
            files.append(str(SKILL_ROOT / t[6:]))
        elif t == "input":
            files.append(run.folder.file(runstore.INPUT))
        elif t == "last_text":
            files.append(run.folder.file(state["text"]))
        elif t == "check_report":
            files.append(run.folder.file(runstore.CHECK))
    return files


# --- the section steps --------------------------------------------------------

def _accept_clarify(run, payload):
    state = run.state
    ask = state["asks"][0]
    run.record("clarify", "json", json.dumps(payload, indent=2))
    state["fields"][ask["field"]] = payload["answer"]
    state["asks"].pop(0)
    if state["asks"]:
        return "clarify"
    state["id"] = run.folder.final_id(state["fields"]["mode"], state["fields"]["section"])  # the folder follows at save
    return begin(run)


def _accept_journal_model(run, payload):
    entry = run.record("journal-model", "txt", Path(payload["text_file"]).read_text(encoding="utf-8"))
    run.state["journal_model"] = run.folder.file(entry["result"])
    return main_part(run)


def _accept_main(run, payload):
    """A main or fix result: run the integrity check, then fix (at most MAX_FIX) or report."""
    state = run.state
    sid, mode = state["step"]["id"], state["fields"]["mode"]
    try:
        text, report = modes.ingest(mode, payload, run.folder.input(), state["fields"]["markup"],
                                    state["exceptions"] + payload["exceptions"],
                                    rules.known(_routing_refs(run)))
    except ValueError as e:
        raise Malformed(str(e))
    # review: the findings JSON is itself the artifact; both files share one NN, so the text is stored first
    text_rel = None if text is None else run.store(sid, "txt", text)
    entry = run.record(sid, "json", json.dumps(payload, indent=2), state["step"]["attempt"])
    entry["text"] = text_rel or entry["result"]
    state["text"] = entry["text"]
    state["exceptions"] += payload["exceptions"]
    n = len([h for h in state["history"] if h["step"] == "check"]) + 1
    run.record("check", "json", json.dumps(report, indent=2), n, passed=report["passed"])
    run.folder.put_check_report(report)
    if report["passed"] or state["fix_attempts"] >= MAX_FIX:
        return "report"
    state["fix_attempts"] += 1
    return "fix", state["fix_attempts"]


def _accept_report(run, payload):
    f = run.state["fields"]
    run.record("report", "json", json.dumps(payload, indent=2))
    run.folder.put_output(render.render(run.head(), f["mode"], f["markup"], modes.artifact(f["mode"], run.folder.read(run.state["text"])),
                                        payload, run.folder.check_report(), run.data["templates"]))
    return "done"


def _review_context(run):
    return {"checklist": rules.names(SKILL_ROOT / "references" / "checklist.md")}


def _fix_context(run):
    return {"failures": run.folder.check_report()["failures"]}


STEPS = {
    "clarify": Step(_accept_clarify, lambda run: dict(run.state["asks"][0])),
    "journal-model": Step(_accept_journal_model),
    "revise": Step(_accept_main), "draft": Step(_accept_main), "review": Step(_accept_main, _review_context),
    "fix": Step(_accept_main, _fix_context),
    "report": Step(_accept_report),
}
