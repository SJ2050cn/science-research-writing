"""The guard: a Stop hook that keeps the agent from ending its turn mid-run.

`engine.py guard` reads the hook's JSON on stdin and looks for an open run in the
project of its `cwd` (or, for Antigravity, the first entry of `workspacePaths` when
`cwd` is absent). It supports both the Claude Code / Codex Stop-hook protocol
({"decision": "block", "reason": ...} on block, empty stdout on allow) and
Antigravity's Stop-hook protocol ({"decision": "continue", "reason": ...} on block,
{} on allow, allowing non-NO_TOOL_CALL terminations immediately without counting
against MAX_BLOCKS). After MAX_BLOCKS blocks with no step progress it gives up,
marks the run stalled (shown in the plan line) and allows the stop. It never fails
loudly: any trouble means the stop is allowed.

State kept in state.json: guard = {blocks}, stalled, guard_off. Progress is an accepted
submit, or a resume: both clear the counter and the stall (reset).

Also here: the `setup` step. `start --agent codex` or `start --agent antigravity`
with no active guard hook makes setup the first step; the agent asks the author, who
installs the hook (install_codex_hook.py or install_antigravity_hook.py) or declines,
which puts guard=off in the plan line.
"""
import json
import os
import sys
from pathlib import Path

from . import antigravityhook, codexhook, runstore, workflow
from .errors import Malformed

MAX_BLOCKS = 3
WAITING = ("ask", "setup")
ANTIGRAVITY_KEYS = ("hookEventName", "conversationId", "terminationReason", "workspacePaths", "continuationActive")
ENGINE = Path(__file__).resolve().parents[1] / "engine.py"
INSTALLER = ENGINE.with_name("install_codex_hook.py")
ANTIGRAVITY_INSTALLER = ENGINE.with_name("install_antigravity_hook.py")
SETUP_AGENTS = {
    "codex": {
        "installed": lambda root: codexhook.installed(),
        "hooks_path": codexhook.hooks_path,
        "installer": INSTALLER,
        "post_install": "Tell the author to open /hooks in Codex and trust the science-research-writing guard hook; Codex ignores it until they do.",
    },
    "antigravity": {
        "installed": lambda root: antigravityhook.installed(project_root=root),
        "hooks_path": antigravityhook.hooks_path,
        "installer": ANTIGRAVITY_INSTALLER,
        "post_install": "No separate trust step is needed; Antigravity loads the hooks file automatically.",
    },
}


def reset(state):
    """Called on progress (submit) and on resume: the run is not stalled any more."""
    state.pop("stalled", None)
    state.pop("guard", None)


def decide(run, decision="block"):
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
    return {"decision": decision, "reason": reason}


def _parse_payload(stdin_text):
    try:
        parsed = json.loads(stdin_text)
    except (ValueError, TypeError):
        return {}, False
    return (parsed, True) if isinstance(parsed, dict) else ({}, False)


def _protocol(fmt, payload):
    if fmt == "auto":
        return "antigravity" if any(k in payload for k in ANTIGRAVITY_KEYS) else "claude"
    return fmt


def _stop_allowed_by_termination(payload):
    reason = payload.get("terminationReason")
    if isinstance(reason, str):
        reason = reason.strip()
    return bool(reason) and reason != "NO_TOOL_CALL"


def _antigravity_allows_stop(payload, valid):
    return not valid or _stop_allowed_by_termination(payload)


PROTOCOLS = {
    "claude": {
        "decision": "block",
        "allow_output": "",
        "use_workspace_paths": False,
        "allow_stop": lambda payload, valid: False,
    },
    "antigravity": {
        "decision": "continue",
        "allow_output": "{}\n",
        "use_workspace_paths": True,
        "allow_stop": _antigravity_allows_stop,
    },
}


def _project_dir(payload, proto):
    cwd = payload.get("cwd")
    if isinstance(cwd, str) and cwd.strip():
        return cwd
    if proto["use_workspace_paths"]:
        ws = payload.get("workspacePaths")
        if isinstance(ws, list):
            for path in ws:
                if isinstance(path, str) and path.strip():
                    return path
    return os.getcwd()


def _emit(proto, answer):
    out = json.dumps(answer) + "\n" if answer else proto["allow_output"]
    if out:
        sys.stdout.write(out)


def run(stdin_text, find_run, fmt="auto"):
    """find_run(root): the project's open Run, or None."""
    proto = PROTOCOLS[fmt if fmt != "auto" else "claude"]
    answer = None
    try:
        payload, valid = _parse_payload(stdin_text)
        proto = PROTOCOLS[_protocol(fmt, payload)]
        if not proto["allow_stop"](payload, valid):
            found = find_run(runstore.project_root(_project_dir(payload, proto)))
            if found is not None:
                answer = decide(found, decision=proto["decision"])
    except Exception:  # a hook must never break the session
        answer = None
    _emit(proto, answer)
    return 0


def pre_steps(agent, project_root=None):
    """setup comes first when a Codex or Antigravity run has no active guard hook installed."""
    cfg = SETUP_AGENTS.get(agent)
    return ["setup"] if cfg and not cfg["installed"](project_root) else []


def _accept_setup(run, payload):
    answer = payload["answer"]
    cfg = SETUP_AGENTS[run.state["agent"]]
    if answer == "installed" and not cfg["installed"](run.root):
        raise Malformed("the guard hook is not active in %s yet: run context.command and submit installed, "
                        "or submit declined" % cfg["hooks_path"]())
    run.state["guard_off"] = answer == "declined"
    run.record("setup", "json", json.dumps(payload))
    return workflow.NEXT


def _setup_context(run):
    agent = run.state["agent"]
    cfg = SETUP_AGENTS[agent]
    return {
        "agent": agent,
        "command": "python3 %s" % cfg["installer"],
        "hooks_file": str(cfg["hooks_path"]()),
        "post_install": cfg["post_install"],
    }


STEPS = {"setup": workflow.Step(_accept_setup, _setup_context)}
