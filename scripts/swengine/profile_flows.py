"""Profile workflows, wired in by run.py (workflow.py knows nothing of them).

Section runs may begin with two extra steps before the main step:
  profile-conflict (ask)   only when an old in-folder profile and the new one both exist
  save-preference (work)   only when the request states a preference (start --preference)
Two tasks have a graph of their own, begun by `start --task`:
  scan-profile   propose (work) -> ask -> done
  study-profile  restate (work) -> ask -> done
Nothing is written to the profile before the author's approval in `ask`, and the
approved items are applied all together or not at all. The model decides what
to write; profile.py enforces the format.
"""
import json

from . import errors, profile, runstore, workflow
from .errors import Malformed
from .workflow import NEXT

MAIN = {"scan-profile": "propose", "study-profile": "restate"}
SLUG = {"scan-profile": "scan", "study-profile": "study"}


def pre_steps(preferences):
    """Run the one-time move and verify profile access before a run folder is created; return notices and pre-steps."""
    notice, conflict = profile.migrate()
    profile.check_accessible()
    return [notice] if notice else [], ["profile-conflict"] * bool(conflict) + ["save-preference"] * bool(preferences)


def start_task(task, agent, input_bytes, root):
    """Begin a scan-profile or study-profile run. input_bytes is None for a study.
    Call after pre_steps: the one-time move may bring the profile a study needs."""
    if task == "study-profile":
        input_bytes = profile.read_bytes()
        if input_bytes is None:
            raise errors.EngineError(errors.PROFILE, "no profile to study at %s" % profile.path())
    folder = runstore.Folder.create(root, SLUG[task], "profile", input_bytes)
    state = workflow.new_state(folder.id, {"mode": SLUG[task]}, [], agent)  # mode only names step overrides
    state.update(task=task, step={"id": MAIN[task], "attempt": 1})
    return state, folder


# --- the profile steps --------------------------------------------------------

def _refuse(fn, *a):
    try:
        return fn(*a)
    except profile.ProfileIOError:
        raise
    except errors.EngineError as e:
        raise Malformed(e.message)


def _apply(ops, rules):
    return _refuse(profile.apply, ops, rules)


def _valid_entry(heading, text, source, replaces, rules):
    _refuse(profile.check_entry, heading, text, source, rules)
    if replaces:
        _refuse(profile.find_old, replaces)


def _record(run, payload):
    run.record(run.state["step"]["id"], "json", json.dumps(payload, indent=2, ensure_ascii=False),
               run.state["step"]["attempt"])


def _accept_conflict(run, payload):
    profile.resolve_conflict(payload["choice"])
    run.state["notices"].append("Both profiles existed; kept %s as the profile, the other is beside it as a backup."
                                % ("the one at " + str(profile.path()) if payload["choice"] == "keep-profile"
                                   else "the old in-folder one at " + str(profile.path())))
    _record(run, payload)
    return NEXT


def _accept_preference(run, payload):
    entries = payload["entries"]
    if not entries:
        raise Malformed("entries needs at least one entry")
    ops = [{"op": "replace" if e["replaces"] else "add", "old": e["replaces"], "heading": e["heading"],
            "text": e["text"], "source": "stated"} for e in entries]
    run.state["notices"] += _apply(ops, run.data["profile"])
    _record(run, payload)
    return NEXT


def _accept_propose(run, payload):
    props = payload["proposals"]
    for n, p in enumerate(props, 1):
        _valid_entry(p["heading"], p["text"], "scanned", p["replaces"], run.data["profile"])
        if not p["evidence"].strip():
            raise Malformed("proposal %d needs its evidence" % n)
    run.state["items"] = [dict(p, n=n) for n, p in enumerate(props, 1)]
    _record(run, payload)
    return "ask"


def _accept_restate(run, payload):
    _restate(run.state, payload, run.data["profile"])
    _record(run, payload)
    return "ask"


def _ask_context(run):
    ctx = {"items": run.state["items"]}
    if "restated" in run.state:
        ctx["restated"] = run.state["restated"]
    return ctx


def _restate(state, payload, rules):
    entries, changes = payload["entries"], payload["changes"]
    lines = [b for _, _, b in profile.bullets(profile.read() or "")]
    seen = [e["entry"] for e in entries]
    missing = [b for b in lines if b not in seen]
    unknown = [e for e in seen if e not in lines]
    if missing or unknown or len(set(seen)) != len(seen):
        raise Malformed("entries must restate every profile entry exactly once; missing %s, not in the profile %s"
                                 % (missing or "none", unknown or "none"))
    for e in entries:
        flags = e["flags"]
        if not isinstance(flags, list) or any(f not in rules["flags"] for f in flags):
            raise Malformed("flags must be a list drawn from: " + ", ".join(rules["flags"]))
        if not e["restatement"].strip():
            raise Malformed("restatement of %r is empty" % e["entry"])
        if not profile.TAG.search(e["entry"]) and "untagged" not in flags:
            raise Malformed("%r has no (source, date) tag, so it must carry the flag untagged" % e["entry"])
    for n, c in enumerate(changes, 1):
        if c["entry"] not in lines or c["action"] not in ("replace", "remove") or not c["reason"].strip():
            raise Malformed("change %d needs an existing entry, action replace or remove, and a reason" % n)
        if c["action"] == "replace":
            _refuse(profile.check_entry, c["heading"], c["text"], "edited", rules)
    state["restated"] = entries
    state["items"] = [dict(c, n=n) for n, c in enumerate(changes, 1)]


def _accept_ask(run, payload):
    """The author's approval (item numbers already checked against the context): apply the
    approved items all together or not at all, and finish the task."""
    state, rules = run.state, run.data["profile"]
    items = state["items"]
    chosen = [items[i - 1] for i in sorted(payload["approved"])]
    scan = state["task"] == "scan-profile"
    ops = []
    for it in chosen:
        if scan:
            ops.append({"op": "replace" if it["replaces"] else "add", "old": it["replaces"], "heading": it["heading"],
                        "text": it["text"], "source": "scanned"})
        elif it["action"] == "remove":
            ops.append({"op": "remove", "old": it["entry"]})
        else:
            ops.append({"op": "replace", "old": it["entry"], "heading": it["heading"], "text": it["text"],
                        "source": "edited"})
    said = _apply(ops, rules) if ops else []
    run.record("ask", "json", json.dumps(payload, indent=2))
    run.folder.put_output(_render(run, chosen, said))
    return "done"


def _render(run, chosen, said):
    state, data = run.state, run.data
    t = data["templates"]["profile_task"][SLUG[state["task"]]]
    none = data["templates"]["none"]
    def block(heading, rows):
        return "## %s\n\n%s" % (heading, "\n".join("- " + r for r in rows) if rows else none)
    label = lambda it: it["text"] if state["task"] == "scan-profile" else \
        "%s %s" % (it["action"], it["entry"] if it["action"] == "remove" else "%s -> %s" % (it["entry"], it["text"]))
    left = [label(i) for i in state["items"] if i not in chosen]
    parts = [run.plan()]
    if state["task"] == "scan-profile":
        parts += [block(t["saved"], said), block(t["not_saved"], left)]
    else:
        flagged = lambda e: "%s: %s%s%s" % (e["entry"], e["restatement"],
                                            " [flags: %s]" % ", ".join(e["flags"]) if e["flags"] else "",
                                            " Question: %s" % e["question"] if e["question"] else "")
        parts += [block(t["restated"], [flagged(e) for e in state["restated"]]),
                  block(t["applied"], said), block(t["not_applied"], left)]
    return "\n\n".join(parts) + "\n"


STEPS = {
    "profile-conflict": workflow.Step(_accept_conflict, lambda run: {
        "in_folder": str(profile.legacy_path()), "profile": str(profile.path())}),
    "save-preference": workflow.Step(_accept_preference, lambda run: {
        "preferences": run.state["preferences"]}),
    "propose": workflow.Step(_accept_propose),
    "restate": workflow.Step(_accept_restate),
    "ask": workflow.Step(_accept_ask, _ask_context),
}
