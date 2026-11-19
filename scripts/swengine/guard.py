"""The guard: a Stop hook that keeps the agent from ending its turn mid-run.

`engine.py guard` reads the hook's JSON on stdin and looks for an open run in the
project of its `cwd`. No open run: exit 0 at once, no output. A run waiting for the
author (step kind ask or setup): allow the stop. Otherwise print
{"decision": "block", "reason": ...}. After MAX_BLOCKS blocks with no step progress
it gives up, marks the run stalled (shown in the plan line) and allows the stop.
It never fails loudly: any trouble means the stop is allowed.

State kept in state.json: guard = {blocks}, stalled, guard_off. Progress is an accepted
submit, or a resume: both clear the counter and the stall (reset).

Also here: the `setup` step. `start --agent codex` with no guard hook in the hooks
file makes setup the first step; the agent asks the author, who installs the hook
(install_codex_hook.py) or declines, which puts guard=off in the plan line.
"""
import json
import os
import sys
from pathlib import Path

from . import codexhook, runstore, workflow
from .errors import Malformed

MAX_BLOCKS = 3
WAITING = ("ask", "setup")
ENGINE = Path(__file__).resolve().parents[1] / "engine.py"
INSTALLER = ENGINE.with_name("install_codex_hook.py")


def reset(state):
    """Called on progress (submit) and on resume: the run is not stalled any more."""
    state.pop("stalled", None)
    state.pop("guard", None)


def decide(run):
    """The hook's answer for an open Run (run.py): a dict to print, or None to allow the stop."""
    state, step = run.state, run.response()
    if state.get("stalled") or step["step"]["kind"] in WAITING:
        return None
    blocks = (state.get("guard") or {}).get("blocks", 0)
    if blocks >= MAX_BLOCKS:
        state["stalled"] = True
        run.save()
        return None
    state["guard"] = {"blocks": blocks + 1}
    run.save()
    reason = ("Run %s is not finished: it is at step %s. %s Do it, then submit the result with "
              "`python3 %s submit --file RESULT.json` and continue until the step kind is done. "
              "To drop the run instead: `python3 %s abandon`."
              % (state["id"], state["step"]["id"], step["instruction"], ENGINE, ENGINE))
    return {"decision": "block", "reason": reason}


def run(stdin_text, find_run):
    """find_run(root): the project's open Run, or None."""
    try:
        try:
            cwd = json.loads(stdin_text).get("cwd")
        except (ValueError, AttributeError):
            cwd = None
        found = find_run(runstore.project_root(cwd or os.getcwd()))  # a payload without cwd: the hook's own folder
        if found is None:
            return 0
        answer = decide(found)
    except Exception:  # a hook must never break the session
        return 0
    if answer:
        sys.stdout.write(json.dumps(answer) + "\n")
    return 0


def pre_steps(agent):
    """setup comes first when a Codex run has no guard hook installed."""
    return ["setup"] if agent == "codex" and not codexhook.installed() else []


def _accept_setup(run, payload):
    answer = payload["answer"]
    if answer == "installed" and not codexhook.installed():
        raise Malformed("the guard hook is not in %s yet: run context.command and submit installed, "
                        "or submit declined" % codexhook.hooks_path())
    run.state["guard_off"] = answer == "declined"
    run.record("setup", "json", json.dumps(payload))
    return workflow.NEXT


STEPS = {"setup": workflow.Step(_accept_setup, lambda run: {
    "command": "python3 %s" % INSTALLER, "hooks_file": str(codexhook.hooks_path())})}
