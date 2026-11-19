"""In-process tests through the Run interface (run.py), for what the command line cannot
reach easily: a workflow.json changed in memory, and the guard acting on the same run."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sandbox import sandbox_env

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from swengine import errors, guard, run, submission  # noqa: E402

GIVEN = {"section": "title", "mode": "revise", "samples": "no"}
REPORT = {"changes": ["shorter"], "questions": [], "conflicts": [], "deviations": []}


class RunCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name).resolve()
        patch = mock.patch.dict(os.environ, sandbox_env(base))  # never the real profile
        patch.start()
        self.addCleanup(patch.stop)
        self.root = base / "proj"
        (self.root / ".git").mkdir(parents=True)
        self.data = run.load_data()

    def file(self, name, content):
        p = self.root / name
        p.write_bytes(content if isinstance(content, bytes) else content.encode())
        return str(p)

    def submit(self, r, payload):
        return r.submit(json.dumps(payload))


class TestRun(RunCase):
    def test_a_stalled_run_that_finishes_shows_no_stall_in_its_output(self):
        r = run.Run.start(self.root, self.data, "section", b"A study of heat in porous media\n", "claude", GIVEN)
        self.submit(r, {"text_file": self.file("rev.txt", "Heat in porous media\n"), "exceptions": []})
        for _ in range(guard.MAX_BLOCKS + 1):
            guard.decide(r)
        self.assertIn("stalled", r.response()["plan"])
        done = self.submit(r, REPORT)
        self.assertEqual(done["step"]["kind"], "done")
        self.assertNotIn("stalled", done["plan"])
        self.assertNotIn("stalled", done["output"].splitlines()[0])

    def test_a_refused_result_leaves_the_saved_run_as_it_was(self):
        r = run.Run.start(self.root, self.data, "section", b"A study of heat in porous media\n", "claude",
                          dict(GIVEN, samples="yes"), [self.file("sample.txt", "a sample paper\n")])
        self.assertEqual(r.response()["step"]["id"], "journal-model")
        refused = self.submit(r, {"text_file": self.file("model.txt", b"\xff\xfe not utf-8")})
        self.assertIn("UTF-8", refused["error"])
        self.assertEqual(refused["step"]["id"], "journal-model")
        saved = run.Run.open(self.root, self.data).state
        self.assertEqual((saved["step"]["id"], saved["history"]), ("journal-model", []))
        self.assertIn("not valid JSON", r.submit("{").get("error"))

    def test_a_step_that_refuses_after_writing_leaves_no_file_behind(self):
        r = run.Run.start(self.root, self.data, "section", b"A study of heat in porous media\n", "claude", GIVEN)
        folder = self.root / ".agents" / "log" / "science-research-writing" / r.state["id"]
        before = sorted(p.relative_to(folder) for p in folder.rglob("*"))

        def refuse_after_writing(*args):
            accept_revise(*args)  # writes the result and the check report
            raise errors.Malformed("refused after the writes")

        accept_revise = run.STEPS["revise"].accept
        with mock.patch.dict(run.STEPS, {"revise": run.STEPS["revise"]._replace(accept=refuse_after_writing)}):
            refused = self.submit(r, {"text_file": self.file("rev.txt", "Heat in porous media\n"), "exceptions": []})
        self.assertEqual(refused["error"], "refused after the writes")
        self.assertEqual(sorted(p.relative_to(folder) for p in folder.rglob("*")), before)

    def test_a_mode_override_is_enforced_as_shown(self):
        propose = self.data["steps"]["propose"]
        fields = dict(propose["expect"]["fields"], notes={"type": "list[string]", "about": "notes"})
        self.data["steps"]["propose@scan"] = dict(propose, expect={"format": "json", "fields": fields})
        r = run.Run.start(self.root, self.data, "scan-profile", b"a writing sample\n", "claude")
        self.assertIn("notes", r.response()["expect"]["fields"])
        step = self.submit(r, {"proposals": [], "notes": []})
        self.assertEqual((step["error"], step["step"]["id"]), (None, "ask"))


class TestWorkflowData(RunCase):
    def test_an_unknown_field_type_is_refused_at_load(self):
        self.data["steps"]["report"]["expect"]["fields"]["changes"]["type"] = "list[strng]"
        with self.assertRaisesRegex(ValueError, r"report\.changes: list\[strng\]"):
            submission.check_types(self.data)

    def test_a_step_without_a_table_entry_is_refused_at_load(self):
        self.data["steps"]["mystery"] = dict(self.data["steps"]["report"])
        with self.assertRaisesRegex(ValueError, "no entry for .*mystery"):
            run.check_steps(self.data)


if __name__ == "__main__":
    unittest.main()
