"""Black-box tests for the guard, one open run per project, resume and abandon.
Every test runs the engine's command line on a temporary project and a temporary
home; none touches the real profile, hooks file or home folder."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sandbox import assert_sandboxed, sandbox_env

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
ENGINE = SCRIPTS / "engine.py"
INTRO = "\\section{Introduction}\nWe used 120 wells \\cite{a2020}. Land use matters for nitrate in groundwater, so we ask how far it predicts the risk to drinking water.\n"
START = ["start", "--section", "introduction", "--mode", "revise",
         "--samples", "no", "--input", "intro.tex"]


class GuardCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name).resolve()
        env = sandbox_env(self.base)
        assert_sandboxed(env)
        patch = mock.patch.dict(os.environ, env)
        patch.start()
        self.addCleanup(patch.stop)
        self.proj = self.base / "proj"
        (self.proj / ".git").mkdir(parents=True)
        (self.proj / "intro.tex").write_text(INTRO)

    def engine(self, *args, stdin=None, cwd=None):
        p = subprocess.run([sys.executable, str(ENGINE), *args], cwd=str(cwd or self.proj),
                           input=stdin, capture_output=True, text=True)
        return p.returncode, (json.loads(p.stdout) if p.stdout.strip() else None), p.stderr

    def guard(self, cwd=None):
        """Pipe a Stop-hook payload to `guard`; return (exit code, parsed stdout or None)."""
        payload = json.dumps({"hook_event_name": "Stop", "cwd": str(cwd or self.proj), "stop_hook_active": False})
        p = subprocess.run([sys.executable, str(ENGINE), "guard"], cwd=str(self.base),
                           input=payload, capture_output=True, text=True)
        return p.returncode, (json.loads(p.stdout) if p.stdout.strip() else None)

    def start(self, *extra):
        code, out, err = self.engine(*START, *extra)
        self.assertEqual(code, 0, err)
        return out

    def submit(self, payload):
        f = self.base / "result.json"
        f.write_text(json.dumps(payload))
        return self.engine("submit", "--file", str(f))


class TestGuard(GuardCase):
    def test_no_open_run_exits_quietly(self):
        self.assertEqual(self.guard(), (0, None))

    def test_a_hook_payload_without_cwd_uses_the_process_folder(self):
        self.start()
        for payload in ('{"hook_event_name": "Stop"}', "", "not json"):
            with self.subTest(payload=payload):
                p = subprocess.run([sys.executable, str(ENGINE), "guard"], cwd=str(self.proj),
                                   input=payload, capture_output=True, text=True)
                self.assertEqual(p.returncode, 0)
                self.assertEqual(json.loads(p.stdout)["decision"], "block")

    def test_open_run_blocks_naming_run_step_and_instruction(self):
        first = self.start()
        code, out = self.guard()
        self.assertEqual(code, 0)
        self.assertEqual(out["decision"], "block")
        self.assertIn(first["run"], out["reason"])
        self.assertIn("revise", out["reason"])
        self.assertIn(first["instruction"][:60], out["reason"])

    def test_finished_run_is_not_blocked(self):
        self.start()
        revised = self.base / "revised.txt"
        revised.write_text(INTRO)
        self.assertEqual(self.submit({"text_file": str(revised), "exceptions": []})[0], 0)
        out = self.submit({"changes": [], "questions": [], "conflicts": [], "deviations": []})[1]
        self.assertEqual(out["step"]["kind"], "done")
        self.assertEqual(self.guard(), (0, None))

    def test_ask_step_lets_the_stop_through(self):
        (self.proj / "sample.txt").write_text("Short sample.\n")
        code, out, err = self.engine("start", "--task", "scan-profile", "--input", "sample.txt")
        self.assertEqual(code, 0, err)
        out = self.submit({"proposals": [{"heading": "Sentences", "text": "Uses we.", "evidence": "we", "replaces": ""}]})[1]
        self.assertEqual(out["step"]["kind"], "ask")
        self.assertEqual(self.guard(), (0, None))

    def test_third_block_without_progress_is_the_last(self):
        self.start()
        for _ in range(3):
            self.assertEqual(self.guard()[1]["decision"], "block")
        self.assertEqual(self.guard(), (0, None))
        plan = self.engine("status")[1]["plan"]
        self.assertTrue(plan.endswith(" · stalled"), plan)
        self.assertEqual(self.guard(), (0, None))  # stays quiet while stalled

    def test_progress_resets_the_count(self):
        self.start()
        self.guard(), self.guard()
        revised = self.base / "revised.txt"
        revised.write_text(INTRO)
        self.submit({"text_file": str(revised), "exceptions": []})  # moves to report
        for _ in range(3):
            self.assertEqual(self.guard()[1]["decision"], "block")
        self.assertEqual(self.guard(), (0, None))

    def test_other_project_is_unaffected(self):
        self.start()
        other = self.base / "other"
        (other / ".git").mkdir(parents=True)
        self.assertEqual(self.guard(cwd=other), (0, None))

    def test_bad_stdin_never_breaks_the_session(self):
        p = subprocess.run([sys.executable, str(ENGINE), "guard"], input="not json",
                           capture_output=True, text=True)
        self.assertEqual((p.returncode, p.stdout), (0, ""))


class TestOneOpenRun(GuardCase):
    def test_start_refuses_while_a_run_is_open(self):
        first = self.start()
        code, out, err = self.engine(*START)
        self.assertEqual(code, 9)
        self.assertIsNone(out)
        self.assertIn(first["run"], err)
        self.assertIn("resume", err)
        self.assertIn("abandon", err)

    def test_start_refuses_a_profile_task_too(self):
        self.start()
        (self.proj / "sample.txt").write_text("x\n")
        self.assertEqual(self.engine("start", "--task", "scan-profile", "--input", "sample.txt")[0], 9)

    def test_resume_continues_the_open_run_and_clears_stalled(self):
        first = self.start()
        for _ in range(4):
            self.guard()
        self.assertIn("stalled", self.engine("status")[1]["plan"])
        code, out, _ = self.engine("resume")
        self.assertEqual(code, 0)
        self.assertEqual((out["run"], out["step"]["id"]), (first["run"], "revise"))
        self.assertNotIn("stalled", out["plan"])
        self.assertEqual(self.guard()[1]["decision"], "block")

    def test_resume_without_an_open_run_fails(self):
        self.assertEqual(self.engine("resume")[0], 4)

    def test_abandon_closes_the_run_and_frees_the_project(self):
        first = self.start()
        code, out, _ = self.engine("abandon")
        self.assertEqual(code, 0)
        self.assertEqual((out["run"], out["status"]), (first["run"], "abandoned"))
        self.assertEqual(self.guard(), (0, None))
        self.assertEqual(self.engine("abandon")[0], 4)
        second = self.start()
        self.assertNotEqual(second["run"], first["run"])
        self.assertTrue((self.proj / ".agents/log/science-research-writing" / first["run"] / "state.json").exists())

    def test_submit_to_an_abandoned_run_is_refused(self):
        first = self.start()
        self.engine("abandon")
        self.assertEqual(self.submit({"text_file": "x", "exceptions": []})[0], 4)
        self.assertEqual(self.engine("submit", "--run", first["run"], "--file", str(self.base / "result.json"))[0], 4)


class TestCodexSetup(GuardCase):
    """start --agent codex offers the guard installer when the hook is missing (hooks file redirected to a temp folder)."""

    def installer(self, *args):
        return subprocess.run([sys.executable, str(SCRIPTS / "install_codex_hook.py"), *args],
                              capture_output=True, text=True).returncode

    def test_missing_hook_makes_setup_the_first_step(self):
        out = self.start("--agent", "codex")
        self.assertEqual(out["step"], {"id": "setup", "kind": "setup"})
        self.assertIn("install_codex_hook.py", out["context"]["command"])
        self.assertNotIn("guard=off", out["plan"])
        self.assertEqual(self.guard(), (0, None))  # waiting for the author's answer

    def test_declining_turns_the_guard_off_in_the_plan_line(self):
        self.start("--agent", "codex")
        code, out, _ = self.submit({"answer": "declined"})
        self.assertEqual((code, out["step"]["id"]), (0, "revise"))
        self.assertTrue(out["plan"].endswith(" · guard=off"), out["plan"])

    def test_installed_answer_is_checked_against_the_hooks_file(self):
        self.start("--agent", "codex")
        code, out, err = self.submit({"answer": "installed"})
        self.assertEqual((code, out["step"]["id"]), (5, "setup"))
        self.assertEqual(self.installer(), 0)
        code, out, _ = self.submit({"answer": "installed"})
        self.assertEqual((code, out["step"]["id"]), (0, "revise"))
        self.assertNotIn("guard=off", out["plan"])

    def test_no_setup_once_the_hook_is_installed_or_for_other_agents(self):
        self.assertEqual(self.start("--agent", "claude")["step"]["id"], "revise")
        self.engine("abandon")
        self.assertEqual(self.start("--agent", "other")["step"]["id"], "revise")
        self.engine("abandon")
        self.assertEqual(self.installer(), 0)
        self.assertEqual(self.start("--agent", "codex")["step"]["id"], "revise")

    def test_setup_comes_before_save_preference_and_before_profile_tasks(self):
        out = self.start("--agent", "codex", "--preference", "I always use we")
        self.assertEqual(out["step"]["id"], "setup")
        self.assertEqual(self.submit({"answer": "declined"})[1]["step"]["id"], "save-preference")
        self.engine("abandon")
        (self.proj / "sample.txt").write_text("x\n")
        code, out, _ = self.engine("start", "--task", "scan-profile", "--input", "sample.txt", "--agent", "codex")
        self.assertEqual(out["step"]["id"], "setup")
        self.assertEqual(self.submit({"answer": "declined"})[1]["step"]["id"], "propose")

    def test_a_moved_skill_counts_as_not_installed(self):
        hooks = Path(os.environ["SCIENCE_RESEARCH_WRITING_CODEX_HOOKS"])
        hooks.parent.mkdir(parents=True)
        hooks.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [
            {"type": "command", "command": "/bin/sh -c ': science-research-writing-guard; exit 0'"}]}]}}))
        self.assertEqual(self.start("--agent", "codex")["step"]["id"], "setup")


if __name__ == "__main__":
    unittest.main()
