"""The Run: one run of the engine, kept in state.json in its run folder (runstore.py).

Every command goes through a Run, and nothing else saves or decodes a run's state:
  Run.start(...)     classify the request, make the run folder, queue the steps that come
                     before the main step (guard setup, then the profile steps), save
  Run.open(root, data, run_id=None)   a run by id, or the project's open run
  run.response(error=None)            the current step response (contract in workflow.json)
  run.submit(result)                  apply one result (JSON text); the next step's response,
                                      or the same step with error set when it was refused
  run.resume() / run.abandon()
A refusal leaves the run as it was: the step works on a copy of the state and its files are
staged in the folder, and only an accepted result commits both. A submission is progress, so
the stall flag is cleared before the step accepts it, and an output rendered at that step
never shows it.

Steps: STEPS joins the step tables of workflow, wholepaper, profile_flows and guard; done is
answered here. A step's accept(run, payload) checks the result, records it (run.record) and
returns the step to go to: an id, (id, attempt), or NEXT for the next queued step (else the
main step). Going to done finishes the run. A whole paper's sections are child Runs: the
current one answers the response and the submissions, and shows the whole run's flags.

Step response (JSON on stdout, the same for start, submit and status; rebuilt every time):
  plan, run, step {id, kind}, attempt, read, instruction, expect, context, error, status,
  notices; at done also output_file and output; in a whole paper, part {index, of, section}.
load_data refuses a workflow.json whose steps and table differ.
"""
import copy
import json

from . import classify, errors, guard, profile_flows, runstore, submission, wholepaper, workflow
from .workflow import NEXT

STEPS = {**workflow.STEPS, **wholepaper.STEPS, **profile_flows.STEPS, **guard.STEPS}
OWN = {"done"}  # answered by this module: the finished run


def load_data():
    data = workflow.load_data()
    check_steps(data)
    submission.check_types(data)
    return data


def check_steps(data):
    """Raise ValueError unless every step id in workflow.json has exactly one way to be answered."""
    ids = {k.split("@")[0] for k in data["steps"]}
    if ids != set(STEPS) | OWN:
        raise ValueError("workflow.json steps and the step table differ: no entry for %s, no definition for %s"
                         % (sorted(ids - set(STEPS) - OWN) or "none", sorted((set(STEPS) | OWN) - ids) or "none"))


def refuse_if_open(root):
    found = runstore.open_run(root)
    if found:
        raise errors.EngineError(errors.OPEN_RUN, "run %s is still open in this project: `resume` it or "
                                                  "`abandon` it first" % found["id"])


class Run:
    def __init__(self, root, data, state, folder=None, parent=None):
        self.root, self.data, self.state, self.parent = root, data, state, parent
        self.folder = folder or runstore.Folder.of(root, state["id"])

    @classmethod
    def start(cls, root, data, task, raw, agent, given=None, sample_files=(), preferences=()):
        """task: section (given holds section, mode, samples; None lets code decide), scan-profile
        or study-profile. raw: the input bytes, None for a study."""
        refuse_if_open(root)
        preferences = list(preferences) if task == "section" else []
        notices, pre = profile_flows.pre_steps(preferences)
        if task == "section":
            values, asks = classify.decide(raw.decode("utf-8", errors="replace"), given["section"], given["mode"], data)
            values["samples"] = given["samples"]
            # an open ask leaves mode or section unknown; the run is renamed once both are settled
            folder = runstore.Folder.create(root, values["mode"] or "ask", values["section"] or "pending", raw)
            run = cls(root, data, workflow.new_state(folder.id, values, sample_files, agent, asks), folder)
            main = workflow.begin(run)
        else:
            state, folder = profile_flows.start_task(task, agent, raw, root)
            run, main = cls(root, data, state, folder), state["step"]["id"]
        run.state.update(notices=notices, preferences=preferences, main=main, pre=guard.pre_steps(agent) + pre)
        run.go(NEXT)
        run.save()
        return run

    @classmethod
    def open(cls, root, data, run_id=None):
        return cls(root, data, runstore.load_state(root, run_id))

    @classmethod
    def find(cls, root, data):
        """The project's open run, or None."""
        state = runstore.open_run(root)
        return cls(root, data, state) if state else None

    def save(self):
        self.folder.commit(self.state)

    def refuse_unless_open(self):
        if self.state["status"] != "open":
            raise errors.EngineError(errors.RUN, "run %s is %s, not open" % (self.state["id"], self.state["status"]))

    # --- what the steps use --------------------------------------------------------

    def plan(self):
        """The plan line: this run's fields, the whole run's flags."""
        return workflow.plan_line(self.state, self.data, (self.parent or self).state)

    def head(self):
        """The top of an output: the plan line, and under it the run's notices (in a whole
        paper, under the first section's plan line only)."""
        top = self.parent or self
        first = self.parent is None or top.state["part"] == 0
        return "\n\n".join([self.plan()] + (top.state.get("notices", []) if first else []))

    def store(self, step, ext, content):
        """Stage results/NN-<step>.<ext>, NN the order of arrival; returns its relative path."""
        return self.folder.add_result(len(self.state["history"]) + 1, step, ext, content)

    def record(self, step, ext, content, attempt=1, **extra):
        """Store a result and append its history entry; returns the entry."""
        entry = {"step": step, "attempt": attempt, "result": self.store(step, ext, content), **extra}
        self.state["history"].append(entry)
        return entry

    def go(self, to):
        if to == NEXT:
            to = self.state["pre"].pop(0) if self.state["pre"] else self.state["main"]
        sid, attempt = (to, 1) if isinstance(to, str) else to
        self.state["step"] = {"id": sid, "attempt": attempt}
        if sid == "done":
            self.state["status"] = "done"

    def child(self):
        """A whole paper's current section, as a Run in its part folder."""
        p = self.state["parts"][self.state["part"]]
        return Run(self.root, self.data, p["state"], self.folder.part(p["dir"]), self)

    # --- steps ---------------------------------------------------------------------

    def _step_def(self):
        return workflow.step_def(self.data, self.state["step"]["id"], self.state["fields"]["mode"])

    def _context(self):
        entry = STEPS.get(self.state["step"]["id"])
        return entry.context(self) if entry and entry.context else None

    def _respond(self, error):
        sid, sdef = self.state["step"]["id"], self._step_def()
        resp = {
            "plan": self.plan(), "run": self.state["id"],
            "step": {"id": sid, "kind": sdef["kind"]}, "attempt": self.state["step"]["attempt"],
            "read": workflow.read_files(self, sdef["read"]),
            "instruction": sdef["instruction"].format(**self.state["fields"]),
            "expect": sdef["expect"], "context": self._context(), "error": error,
            "status": self.state["status"],
        }
        if sdef["kind"] == "done":
            resp["output_file"] = self.folder.file(runstore.OUTPUT)
            resp["output"] = self.folder.output()
        return resp

    def response(self, error=None):
        if self.state["step"]["id"] == "parts":
            place = {"index": self.state["part"] + 1, "of": len(self.state["parts"]),
                     "section": self.state["parts"][self.state["part"]]["section"]}
            resp = dict(self.child()._respond(error), part=place)
        else:
            resp = self._respond(error)
        return dict(resp, notices=self.state.get("notices", []))

    def accept(self, payload):
        """Check one result against the current step and move the run on. Raises errors.Malformed."""
        if self._step_def()["kind"] == "done":
            raise errors.Malformed("the run is finished; nothing more to submit")
        if self.state["step"]["id"] != "parts":  # a whole paper's current section checks its own
            submission.accept(self._step_def()["expect"], payload, self._context())
        self.go(STEPS[self.state["step"]["id"]].accept(self, payload))

    def submit(self, result):
        """result: the submitted JSON, as text or bytes."""
        self.refuse_unless_open()
        work = Run(self.root, self.data, copy.deepcopy(self.state))
        guard.reset(work.state)  # progress: the run is not stalled any more, in this step's output too
        try:
            try:
                payload = json.loads(result)
            except ValueError as e:
                raise errors.Malformed("result is not valid JSON: %s" % e)
            work.accept(payload)
        except errors.Malformed as e:
            return self.response(error=str(e))
        work.save()
        self.state, self.folder = work.state, work.folder  # answering an ask may have renamed the run
        return self.response()

    def resume(self):
        guard.reset(self.state)
        self.save()
        return self.response()

    def abandon(self):
        self.state["status"] = "abandoned"
        self.save()
        return {"run": self.state["id"], "status": self.state["status"]}
