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
        self.assertEqual(out["context"]["agent"], "codex")
        self.assertIn("install_codex_hook.py", out["context"]["command"])
        self.assertEqual(out["context"]["hooks_file"], os.environ["SCIENCE_RESEARCH_WRITING_CODEX_HOOKS"])
        self.assertIn("/hooks", out["context"]["post_install"])
        self.assertIn("trust", out["context"]["post_install"].lower())
        self.assertIn("context.command", out["instruction"])
        self.assertIn("context.hooks_file", out["instruction"])
        self.assertIn("context.post_install", out["instruction"])
        self.assertNotIn("Codex", out["instruction"])
        self.assertNotIn("/hooks", out["instruction"])
        self.assertNotIn("guard=off", out["plan"])
        self.assertEqual(self.guard(), (0, None))  # waiting for the author's answer

    def test_declining_turns_the_guard_off_in_the_plan_line(self):
        self.start("--agent", "codex")
        code, out, _ = self.submit({"answer": "declined"})
        self.assertEqual((code, out["step"]["id"]), (0, "revise"))
        self.assertTrue(out["plan"].endswith(" · guard=off"), out["plan"])

    def test_installed_answer_is_checked_against_the_hooks_file(self):
        codex_hooks = os.environ["SCIENCE_RESEARCH_WRITING_CODEX_HOOKS"]
        self.start("--agent", "codex")
        code, out, err = self.submit({"answer": "installed"})
        self.assertEqual((code, out["step"]["id"]), (5, "setup"))
        self.assertIn(codex_hooks, out["error"])
        self.assertIn(codex_hooks, err)
        # Installing the Antigravity hook does not satisfy a Codex setup step.
        self.assertEqual(subprocess.run([sys.executable, str(SCRIPTS / "install_antigravity_hook.py")],
                                        capture_output=True, text=True).returncode, 0)
        code, out, _ = self.submit({"answer": "installed"})
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


class TestAntigravitySetup(GuardCase):
    """start --agent antigravity offers the Antigravity guard installer when no active hook is installed."""

    def installer(self, *args, env=None):
        return subprocess.run([sys.executable, str(SCRIPTS / "install_antigravity_hook.py"), *args],
                              capture_output=True, text=True, env=env).returncode

    def ag_guard(self, cwd=None):
        payload = json.dumps({"hookEventName": "Stop", "cwd": str(cwd or self.proj), "terminationReason": "NO_TOOL_CALL"})
        p = subprocess.run([sys.executable, str(ENGINE), "guard", "--format", "antigravity"],
                           cwd=str(self.base), input=payload, capture_output=True, text=True)
        return p.returncode, json.loads(p.stdout)

    def test_invalid_agent_choice_is_rejected(self):
        code, out, err = self.engine(*START, "--agent", "unknown")
        self.assertNotEqual(code, 0)
        self.assertIsNone(out)
        self.assertIn("invalid choice", err)

    def test_missing_hook_makes_setup_the_first_step(self):
        out = self.start("--agent", "antigravity")
        self.assertEqual(out["step"], {"id": "setup", "kind": "setup"})
        self.assertEqual(out["context"]["agent"], "antigravity")
        self.assertIn("install_antigravity_hook.py", out["context"]["command"])
        self.assertEqual(out["context"]["hooks_file"], os.environ["SCIENCE_RESEARCH_WRITING_ANTIGRAVITY_HOOKS"])
        self.assertTrue(out["context"]["post_install"].strip())
        self.assertNotIn("/hooks", out["context"]["post_install"])
        self.assertNotIn("Codex", out["context"]["post_install"])
        self.assertIn("context.command", out["instruction"])
        self.assertIn("context.hooks_file", out["instruction"])
        self.assertIn("context.post_install", out["instruction"])
        self.assertNotIn("Codex", out["instruction"])
        self.assertNotIn("~/.codex/hooks.json", out["instruction"])
        self.assertNotIn("/hooks", out["instruction"])
        self.assertNotIn("guard=off", out["plan"])
        self.assertEqual(self.ag_guard(), (0, {}))  # waiting for the author's answer

    def test_installed_answer_is_checked_against_the_antigravity_hooks_file(self):
        ag_hooks = os.environ["SCIENCE_RESEARCH_WRITING_ANTIGRAVITY_HOOKS"]
        self.start("--agent", "antigravity")
        code, out, err = self.submit({"answer": "installed"})
        self.assertEqual((code, out["step"]["id"]), (5, "setup"))
        self.assertIn(ag_hooks, out["error"])
        self.assertIn(ag_hooks, err)
        # Installing the Codex hook does not satisfy an Antigravity setup step.
        self.assertEqual(subprocess.run([sys.executable, str(SCRIPTS / "install_codex_hook.py")],
                                        capture_output=True, text=True).returncode, 0)
        code, out, _ = self.submit({"answer": "installed"})
        self.assertEqual((code, out["step"]["id"]), (5, "setup"))
        self.assertEqual(self.installer(), 0)
        code, out, _ = self.submit({"answer": "installed"})
        self.assertEqual((code, out["step"]["id"]), (0, "revise"))
        self.assertNotIn("guard=off", out["plan"])
        self.assertEqual(self.ag_guard()[1]["decision"], "continue")

    def test_default_hooks_path_names_home_gemini_config_hooks_json(self):
        env = dict(os.environ)
        env.pop("SCIENCE_RESEARCH_WRITING_ANTIGRAVITY_HOOKS", None)
        expected = str(self.base / "home" / ".gemini" / "config" / "hooks.json")
        p_start = subprocess.run([sys.executable, str(ENGINE), *START, "--agent", "antigravity"],
                                 cwd=str(self.proj), capture_output=True, text=True, env=env)
        self.assertEqual(p_start.returncode, 0, p_start.stderr)
        out = json.loads(p_start.stdout)
        self.assertEqual(out["step"]["id"], "setup")
        self.assertEqual(out["context"]["hooks_file"], expected)
        result_file = self.base / "installed.json"
        result_file.write_text(json.dumps({"answer": "installed"}))
        p_refuse = subprocess.run([sys.executable, str(ENGINE), "submit", "--file", str(result_file)],
                                  cwd=str(self.proj), capture_output=True, text=True, env=env)
        self.assertEqual(p_refuse.returncode, 5)
        self.assertIn(expected, json.loads(p_refuse.stdout)["error"])
        self.assertEqual(self.installer(env=env), 0)
        p_ok = subprocess.run([sys.executable, str(ENGINE), "submit", "--file", str(result_file)],
                              cwd=str(self.proj), capture_output=True, text=True, env=env)
        self.assertEqual(p_ok.returncode, 0, p_ok.stderr)
        self.assertEqual(json.loads(p_ok.stdout)["step"]["id"], "revise")

    def test_declining_turns_the_guard_off_in_the_plan_line(self):
        self.start("--agent", "antigravity")
        code, out, err = self.submit({"answer": "declined"})
        self.assertEqual((code, out["step"]["id"]), (0, "revise"), err)
        self.assertTrue(out["plan"].endswith(" · guard=off"), out["plan"])

    def test_no_setup_once_global_hook_is_installed_or_for_non_setup_agents(self):
        self.assertEqual(self.start()["step"]["id"], "revise")  # default --agent other
        self.engine("abandon")
        self.assertEqual(self.start("--agent", "claude")["step"]["id"], "revise")
        self.engine("abandon")
        self.assertEqual(self.start("--agent", "other")["step"]["id"], "revise")
        self.engine("abandon")
        self.assertEqual(self.installer(), 0)
        out = self.start("--agent", "antigravity")
        self.assertEqual(out["step"]["id"], "revise")
        self.assertNotIn("guard=off", out["plan"])

    def test_active_project_level_hook_skips_setup_from_root_and_subdir(self):
        project_hooks = self.proj / ".agents" / "hooks.json"
        project_hooks.parent.mkdir(parents=True)
        # Direct absolute path to this skill's engine guard
        project_hooks.write_text(json.dumps({
            "science-research-writing-guard": {
                "Stop": [{"type": "command",
                          "command": "python3 %s guard --format antigravity" % ENGINE.resolve(),
                          "timeout": 10}]
            }
        }))
        out = self.start("--agent", "antigravity")
        self.assertEqual(out["step"]["id"], "revise")
        self.assertNotIn("guard=off", out["plan"])
        self.engine("abandon")

        # Subdirectory inside the git project still finds <project>/.agents/hooks.json
        sub = self.proj / "sections"
        sub.mkdir()
        code, out, err = self.engine("start", "--section", "introduction", "--mode", "revise",
                                     "--samples", "no", "--input", str(self.proj / "intro.tex"),
                                     "--agent", "antigravity", cwd=sub)
        self.assertEqual(code, 0, err)
        self.assertEqual(out["step"]["id"], "revise")
        self.engine("abandon")

        # Project-relative command via .agents/skills/<skill> symlink also counts as active
        skill_link = self.proj / ".agents" / "skills" / "science-research-writing"
        skill_link.parent.mkdir(parents=True)
        skill_link.symlink_to(SCRIPTS.parent.resolve())
        project_hooks.write_text(json.dumps({
            "science-research-writing-guard": {
                "Stop": [{"type": "command",
                          "command": "python3 skills/science-research-writing/scripts/engine.py guard --format antigravity",
                          "timeout": 10}]
            }
        }))
        self.assertEqual(self.start("--agent", "antigravity")["step"]["id"], "revise")
        self.engine("abandon")

        # Adding an active project-level hook during setup also satisfies `installed`.
        project_hooks.unlink()
        self.assertEqual(self.start("--agent", "antigravity")["step"]["id"], "setup")
        project_hooks.write_text(json.dumps({
            "science-research-writing-guard": {
                "Stop": [{"type": "command",
                          "command": "python3 %s guard --format antigravity" % ENGINE.resolve(),
                          "timeout": 10}]
            }
        }))
        code, next_step, err = self.submit({"answer": "installed"})
        self.assertEqual((code, next_step["step"]["id"]), (0, "revise"), err)
        self.assertNotIn("guard=off", next_step["plan"])

    def test_portable_home_env_project_hook_skips_setup(self):
        home_skill = Path(os.environ["HOME"]) / ".agents" / "skills" / "science-research-writing"
        home_skill.parent.mkdir(parents=True)
        home_skill.symlink_to(SCRIPTS.parent.resolve())
        project_hooks = self.proj / ".agents" / "hooks.json"
        project_hooks.parent.mkdir(parents=True)
        commands = [
            'python3 "$HOME/.agents/skills/science-research-writing/scripts/engine.py" guard --format antigravity',
            "python3 $HOME/.agents/skills/science-research-writing/scripts/engine.py guard --format antigravity",
            "python3 ${HOME}/.agents/skills/science-research-writing/scripts/engine.py guard --format antigravity",
        ]
        for cmd in commands:
            with self.subTest(cmd=cmd):
                project_hooks.write_text(json.dumps({
                    "science-research-writing-guard": {
                        "Stop": [{"type": "command", "command": cmd, "timeout": 10}]
                    }
                }))
                out = self.start("--agent", "antigravity")
                try:
                    self.assertEqual(out["step"]["id"], "revise")
                    self.assertNotIn("guard=off", out["plan"])
                finally:
                    self.engine("abandon")

    def test_shell_wrapped_project_hook_skips_setup(self):
        home_skill = Path(os.environ["HOME"]) / ".agents" / "skills" / "science-research-writing"
        home_skill.parent.mkdir(parents=True)
        home_skill.symlink_to(SCRIPTS.parent.resolve())
        project_hooks = self.proj / ".agents" / "hooks.json"
        project_hooks.parent.mkdir(parents=True)
        commands = [
            "bash -c 'E=\"$HOME/.agents/skills/science-research-writing/scripts/engine.py\"; "
            "[ -f \"$E\" ] && exec python3 \"$E\" guard --format antigravity; printf \"{}\\n\"'",
            "/bin/bash -c 'python3 \"$HOME/.agents/skills/science-research-writing/scripts/engine.py\" guard'",
            "zsh -c 'python3 ${HOME}/.agents/skills/science-research-writing/scripts/engine.py guard --format=auto'",
        ]
        for cmd in commands:
            with self.subTest(cmd=cmd):
                project_hooks.write_text(json.dumps({
                    "science-research-writing-guard": {
                        "Stop": [{"type": "command", "command": cmd, "timeout": 10}]
                    }
                }))
                out = self.start("--agent", "antigravity")
                try:
                    self.assertEqual(out["step"]["id"], "revise")
                    self.assertNotIn("guard=off", out["plan"])
                finally:
                    self.engine("abandon")

    def test_project_hook_claude_format_is_rejected_while_auto_and_antigravity_pass(self):
        engine = str(ENGINE.resolve())
        project_hooks = self.proj / ".agents" / "hooks.json"
        project_hooks.parent.mkdir(parents=True)
        rejected = [
            "python3 %s guard --format claude" % engine,
            "python3 %s guard --format=claude" % engine,
            "bash -c 'E=%s; [ -f \"$E\" ] && exec python3 \"$E\" guard --format claude; exit 0'" % engine,
            "python3 %s guard --format" % engine,
        ]
        for cmd in rejected:
            with self.subTest(rejected=cmd):
                project_hooks.write_text(json.dumps({
                    "science-research-writing-guard": {
                        "Stop": [{"type": "command", "command": cmd, "timeout": 10}]
                    }
                }))
                out = self.start("--agent", "antigravity")
                try:
                    self.assertEqual(out["step"]["id"], "setup")
                    code, refused, _ = self.submit({"answer": "installed"})
                    self.assertEqual((code, refused["step"]["id"]), (5, "setup"))
                finally:
                    self.engine("abandon")

        accepted = [
            "python3 %s guard" % engine,
            "python3 %s guard --format auto" % engine,
            "python3 %s guard --format=auto" % engine,
            "python3 %s guard --format antigravity" % engine,
            "python3 %s guard --format=antigravity" % engine,
        ]
        for cmd in accepted:
            with self.subTest(accepted=cmd):
                project_hooks.write_text(json.dumps({
                    "science-research-writing-guard": {
                        "Stop": [{"type": "command", "command": cmd, "timeout": 10}]
                    }
                }))
                out = self.start("--agent", "antigravity")
                try:
                    self.assertEqual(out["step"]["id"], "revise")
                    self.assertNotIn("guard=off", out["plan"])
                finally:
                    self.engine("abandon")

    def test_disabled_global_and_project_hooks_offer_setup_and_reinstall_clears_it(self):
        ag_hooks = Path(os.environ["SCIENCE_RESEARCH_WRITING_ANTIGRAVITY_HOOKS"])
        self.assertEqual(self.installer(), 0)
        data = json.loads(ag_hooks.read_text(encoding="utf-8"))
        data["science-research-writing-guard"]["enabled"] = False
        ag_hooks.write_text(json.dumps(data), encoding="utf-8")

        out = self.start("--agent", "antigravity")
        self.assertEqual(out["step"]["id"], "setup")
        code, refused, _ = self.submit({"answer": "installed"})
        self.assertEqual((code, refused["step"]["id"]), (5, "setup"))
        self.assertEqual(self.installer(), 0)  # re-enables in place
        code, next_step, err = self.submit({"answer": "installed"})
        self.assertEqual((code, next_step["step"]["id"]), (0, "revise"), err)
        self.assertNotIn("guard=off", next_step["plan"])
        self.engine("abandon")

        # Remove global hook and test disabled project hook
        self.assertEqual(self.installer("--uninstall"), 0)
        project_hooks = self.proj / ".agents" / "hooks.json"
        project_hooks.parent.mkdir(parents=True, exist_ok=True)
        project_hooks.write_text(json.dumps({
            "science-research-writing-guard": {
                "enabled": False,
                "Stop": [{"type": "command",
                          "command": "python3 %s guard --format antigravity" % ENGINE.resolve(),
                          "timeout": 10}]
            }
        }))
        self.assertEqual(self.start("--agent", "antigravity")["step"]["id"], "setup")

    def test_moved_global_and_project_hooks_offer_setup_and_reinstall_refreshes(self):
        ag_hooks = Path(os.environ["SCIENCE_RESEARCH_WRITING_ANTIGRAVITY_HOOKS"])
        ag_hooks.parent.mkdir(parents=True, exist_ok=True)
        ag_hooks.write_text(json.dumps({
            "science-research-writing-guard": {
                "Stop": [{"type": "command",
                          "command": "/bin/sh -c ': science-research-writing-guard; E=/old/path/engine.py; exit 0'",
                          "timeout": 10}]
            }
        }))
        out = self.start("--agent", "antigravity")
        self.assertEqual(out["step"]["id"], "setup")
        code, refused, _ = self.submit({"answer": "installed"})
        self.assertEqual((code, refused["step"]["id"]), (5, "setup"))
        self.assertEqual(self.installer(), 0)  # refreshes in place
        code, next_step, err = self.submit({"answer": "installed"})
        self.assertEqual((code, next_step["step"]["id"]), (0, "revise"), err)
        self.engine("abandon")

        # Remove global hook and test moved project hook
        self.assertEqual(self.installer("--uninstall"), 0)
        project_hooks = self.proj / ".agents" / "hooks.json"
        project_hooks.parent.mkdir(parents=True, exist_ok=True)
        project_hooks.write_text(json.dumps({
            "science-research-writing-guard": {
                "Stop": [{"type": "command",
                          "command": "python3 /old/location/scripts/engine.py guard --format antigravity",
                          "timeout": 10}]
            }
        }))
        self.assertEqual(self.start("--agent", "antigravity")["step"]["id"], "setup")

    def test_project_root_relative_hook_offers_setup_because_it_runs_from_agents(self):
        skill_link = self.proj / ".agents" / "skills" / "science-research-writing"
        skill_link.parent.mkdir(parents=True)
        skill_link.symlink_to(SCRIPTS.parent.resolve())
        (self.proj / ".agents" / "hooks.json").write_text(json.dumps({
            "science-research-writing-guard": {
                "Stop": [{"type": "command", "timeout": 10, "command":
                          "python3 .agents/skills/science-research-writing/scripts/engine.py guard --format antigravity"}]
            }
        }))
        self.assertEqual(self.start("--agent", "antigravity")["step"]["id"], "setup")

    @unittest.skipIf(os.geteuid() == 0, "root reads any folder")
    def test_unreadable_hooks_folder_offers_setup_instead_of_crashing(self):
        folder = Path(os.environ["SCIENCE_RESEARCH_WRITING_ANTIGRAVITY_HOOKS"]).parent
        folder.mkdir(parents=True)
        (folder / "hooks.json").write_text("{}")
        folder.chmod(0)
        self.addCleanup(folder.chmod, 0o755)
        code, out, err = self.engine(*START, "--agent", "antigravity")
        self.assertEqual(code, 0, err)
        self.assertEqual(out["step"]["id"], "setup")

    def test_setup_comes_before_save_preference_profile_tasks_and_whole_paper(self):
        # Ahead of save-preference
        out = self.start("--agent", "antigravity", "--preference", "I always use we")
        self.assertEqual(out["step"]["id"], "setup")
        code, pref_step, err = self.submit({"answer": "declined"})
        self.assertEqual((code, pref_step["step"]["id"]), (0, "save-preference"), err)
        self.assertTrue(pref_step["plan"].endswith(" · guard=off"), pref_step["plan"])
        self.engine("abandon")

        # Ahead of scan-profile
        (self.proj / "sample.txt").write_text("We measured nitrate in three wells.\n")
        code, out, err = self.engine("start", "--task", "scan-profile", "--input", "sample.txt",
                                     "--agent", "antigravity")
        self.assertEqual(code, 0, err)
        self.assertEqual(out["step"]["id"], "setup")
        code, propose_step, err = self.submit({"answer": "declined"})
        self.assertEqual((code, propose_step["step"]["id"]), (0, "propose"), err)
        self.assertTrue(propose_step["plan"].endswith(" · guard=off"), propose_step["plan"])
        self.engine("abandon")

        # Ahead of study-profile
        profile_dir = Path(os.environ["SCIENCE_RESEARCH_WRITING_PROFILE_DIR"])
        profile_dir.mkdir(parents=True, exist_ok=True)
        (profile_dir / "user-style.md").write_text(
            "# Author Style Profile\n\n## Voice & person\n- Use we (stated, 2026-01-01)\n",
            encoding="utf-8",
        )
        code, out, err = self.engine("start", "--task", "study-profile", "--agent", "antigravity")
        self.assertEqual(code, 0, err)
        self.assertEqual(out["step"]["id"], "setup")
        code, restate_step, err = self.submit({"answer": "declined"})
        self.assertEqual((code, restate_step["step"]["id"]), (0, "restate"), err)
        self.assertTrue(restate_step["plan"].endswith(" · guard=off"), restate_step["plan"])
        self.engine("abandon")

        # Ahead of whole-paper
        paper = (
            "\\title{Nitrate in wells}\n"
            "\\begin{abstract}\nWe sampled 120 wells. The forest reached $R^2=0.81$ on them.\n\\end{abstract}\n"
            "\\section{Introduction}\nNitrate above 50~mg/L is a risk \\cite{who2017}. Land use matters.\n"
            "\\section{Methods}\nWe used 120 wells. A forest was trained on them.\n"
            "\\end{document}\n"
        )
        (self.proj / "paper.tex").write_text(paper)
        code, out, err = self.engine("start", "--section", "whole-paper", "--mode", "revise",
                                     "--samples", "no", "--input", "paper.tex", "--agent", "antigravity")
        self.assertEqual(code, 0, err)
        self.assertEqual(out["step"]["id"], "setup")
        code, part_step, err = self.submit({"answer": "declined"})
        self.assertEqual(code, 0, err)
        self.assertEqual(part_step["part"]["index"], 1)
        self.assertTrue(part_step["plan"].endswith(" · guard=off"), part_step["plan"])
        self.engine("abandon")

        # Installing the hook skips setup on whole-paper and profile tasks too
        self.assertEqual(self.installer(), 0)
        code, out, err = self.engine("start", "--task", "study-profile", "--agent", "antigravity")
        self.assertEqual((code, out["step"]["id"]), (0, "restate"), err)
        self.assertNotIn("guard=off", out["plan"])


class TestAntigravityGuard(GuardCase):
    """Black-box CLI tests for the Antigravity Stop-hook guard protocol and --format selection."""

    def run_guard(self, payload, *extra_args, cwd=None):
        """Invoke `engine.py guard` with raw payload (str, bytes, or dict) and return CompletedProcess."""
        if isinstance(payload, dict):
            payload = json.dumps(payload)
        if isinstance(payload, bytes):
            return subprocess.run([sys.executable, str(ENGINE), "guard", *extra_args],
                                  cwd=str(cwd or self.base), input=payload, capture_output=True)
        return subprocess.run([sys.executable, str(ENGINE), "guard", *extra_args],
                              cwd=str(cwd or self.base), input=payload, capture_output=True, text=True)

    def test_format_option_rejects_unknown_value(self):
        p = self.run_guard("{}", "--format", "unknown")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("invalid choice", p.stderr)

    def test_antigravity_format_continues_open_run_with_step_details_and_commands(self):
        first = self.start()
        p = self.run_guard({"hookEventName": "Stop", "cwd": str(self.proj), "terminationReason": "NO_TOOL_CALL"},
                           "--format", "antigravity")
        self.assertEqual(p.returncode, 0, p.stderr)
        out = json.loads(p.stdout)
        self.assertEqual(out["decision"], "continue")
        self.assertIn(first["run"], out["reason"])
        self.assertIn("revise", out["reason"])
        self.assertIn(first["instruction"][:60], out["reason"])
        self.assertIn("submit --file", out["reason"])
        self.assertIn("abandon", out["reason"])

    def test_auto_format_detects_each_antigravity_camelcase_key(self):
        self.start()
        cases = [
            {"hookEventName": "Stop", "cwd": str(self.proj)},
            {"conversationId": "conv-123", "cwd": str(self.proj)},
            {"terminationReason": "", "cwd": str(self.proj)},
            {"workspacePaths": [], "cwd": str(self.proj)},
            {"continuationActive": False, "cwd": str(self.proj)},
        ]
        for payload in cases:
            with self.subTest(keys=sorted(payload)):
                self.engine("resume")  # keep below MAX_BLOCKS across subtests
                p = self.run_guard(payload)  # default --format auto
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertEqual(json.loads(p.stdout)["decision"], "continue")

    def test_auto_format_keeps_claude_protocol_without_antigravity_keys(self):
        self.start()
        for extra in ((), ("--format", "auto")):
            with self.subTest(extra=extra):
                p = self.run_guard({"hook_event_name": "Stop", "cwd": str(self.proj)}, *extra)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertEqual(json.loads(p.stdout)["decision"], "block")

    def test_explicit_claude_format_overrides_antigravity_keys(self):
        p_none = self.run_guard({"hookEventName": "Stop", "cwd": str(self.proj)}, "--format", "claude")
        self.assertEqual((p_none.returncode, p_none.stdout), (0, ""))
        self.start()
        p = self.run_guard({"hookEventName": "Stop", "cwd": str(self.proj), "terminationReason": "USER_CANCELED"},
                           "--format", "claude")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout)["decision"], "block")

    def test_non_normal_termination_reasons_allow_stop_without_burning_retries_or_stalling(self):
        self.start()
        normal = {"hookEventName": "Stop", "cwd": str(self.proj), "terminationReason": "NO_TOOL_CALL"}
        for _ in range(2):
            p = self.run_guard(normal)
            self.assertEqual(json.loads(p.stdout)["decision"], "continue")
        reasons = (
            "USER_CANCELED", "ERROR", "MAX_INVOCATIONS", "MAX_FORCED_INVOCATIONS",
            "MAX_TOKEN_BUDGET_EXCEEDED", "TERMINAL_STEP_TYPE", "TERMINAL_CUSTOM_HOOK", "INJECTED_RESPONSE",
        )
        for reason in reasons:
            with self.subTest(terminationReason=reason):
                p = self.run_guard({"hookEventName": "Stop", "cwd": str(self.proj), "terminationReason": reason})
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertEqual(json.loads(p.stdout), {})
        # Still below the 3-block limit: 3rd normal call continues, and USER_CANCELED right after does not stall it.
        self.assertEqual(json.loads(self.run_guard(normal).stdout)["decision"], "continue")
        p_cancel = self.run_guard({"hookEventName": "Stop", "cwd": str(self.proj), "terminationReason": "USER_CANCELED"})
        self.assertEqual((p_cancel.returncode, json.loads(p_cancel.stdout)), (0, {}))
        self.assertNotIn("stalled", self.engine("status")[1]["plan"])

    def test_missing_empty_or_no_tool_call_termination_reason_continues_open_run(self):
        self.start()
        for payload in (
            {"hookEventName": "Stop", "cwd": str(self.proj)},
            {"hookEventName": "Stop", "cwd": str(self.proj), "terminationReason": ""},
            {"hookEventName": "Stop", "cwd": str(self.proj), "terminationReason": None},
            {"hookEventName": "Stop", "cwd": str(self.proj), "terminationReason": "NO_TOOL_CALL"},
        ):
            with self.subTest(terminationReason=payload.get("terminationReason", "<absent>")):
                self.engine("resume")
                p = self.run_guard(payload)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertEqual(json.loads(p.stdout)["decision"], "continue")

    def test_missing_or_empty_cwd_falls_back_to_first_non_empty_workspace_path(self):
        self.start()
        sub = self.proj / "sections"
        sub.mkdir()
        other = self.base / "other"
        (other / ".git").mkdir(parents=True)
        for payload in (
            {"hookEventName": "Stop", "workspacePaths": [str(self.proj), str(other)]},
            {"hookEventName": "Stop", "cwd": "", "workspacePaths": ["", None, str(sub), str(other)]},
            {"hookEventName": "Stop", "cwd": None, "workspacePaths": [str(self.proj)]},
        ):
            with self.subTest(payload=payload):
                self.engine("resume")
                p = self.run_guard(payload, cwd=self.base)  # process cwd is outside the project
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertEqual(json.loads(p.stdout)["decision"], "continue")

    def test_non_empty_cwd_takes_precedence_over_workspace_paths(self):
        self.start()
        other = self.base / "other"
        (other / ".git").mkdir(parents=True)
        p_other = self.run_guard({"hookEventName": "Stop", "cwd": str(other), "workspacePaths": [str(self.proj)]})
        self.assertEqual((p_other.returncode, json.loads(p_other.stdout)), (0, {}))
        p_proj = self.run_guard({"hookEventName": "Stop", "cwd": str(self.proj), "workspacePaths": [str(other)]})
        self.assertEqual(p_proj.returncode, 0, p_proj.stderr)
        self.assertEqual(json.loads(p_proj.stdout)["decision"], "continue")

    def test_falls_back_to_process_cwd_when_cwd_and_workspace_paths_absent_or_empty(self):
        self.start()
        for payload in (
            {"hookEventName": "Stop"},
            {"hookEventName": "Stop", "cwd": "", "workspacePaths": []},
            {"hookEventName": "Stop", "cwd": "", "workspacePaths": ["", None]},
            {"hookEventName": "Stop", "workspacePaths": "not-a-list"},
        ):
            with self.subTest(payload=payload):
                self.engine("resume")
                p = self.run_guard(payload, cwd=self.proj)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertEqual(json.loads(p.stdout)["decision"], "continue")

    def test_no_open_finished_and_abandoned_runs_output_empty_json_object(self):
        payload = {"hookEventName": "Stop", "cwd": str(self.proj), "terminationReason": "NO_TOOL_CALL"}
        p = self.run_guard(payload)
        self.assertEqual((p.returncode, p.stdout), (0, "{}\n"))
        self.start()
        revised = self.base / "revised.txt"
        revised.write_text(INTRO)
        self.assertEqual(self.submit({"text_file": str(revised), "exceptions": []})[0], 0)
        self.assertEqual(self.submit({"changes": [], "questions": [], "conflicts": [], "deviations": []})[1]["step"]["kind"], "done")
        p_done = self.run_guard(payload)
        self.assertEqual((p_done.returncode, p_done.stdout), (0, "{}\n"))
        self.start()
        self.assertEqual(self.engine("abandon")[0], 0)
        p_abandoned = self.run_guard(payload)
        self.assertEqual((p_abandoned.returncode, p_abandoned.stdout), (0, "{}\n"))

    def test_waiting_ask_and_setup_steps_output_empty_json_object(self):
        payload = {"hookEventName": "Stop", "cwd": str(self.proj), "terminationReason": "NO_TOOL_CALL"}
        (self.proj / "sample.txt").write_text("Short sample.\n")
        self.assertEqual(self.engine("start", "--task", "scan-profile", "--input", "sample.txt")[0], 0)
        out = self.submit({"proposals": [{"heading": "Sentences", "text": "Uses we.", "evidence": "we", "replaces": ""}]})[1]
        self.assertEqual(out["step"]["kind"], "ask")
        p_ask = self.run_guard(payload)
        self.assertEqual((p_ask.returncode, p_ask.stdout), (0, "{}\n"))
        self.engine("abandon")
        setup_out = self.start("--agent", "codex")
        self.assertEqual(setup_out["step"]["kind"], "setup")
        p_setup = self.run_guard(payload)
        self.assertEqual((p_setup.returncode, p_setup.stdout), (0, "{}\n"))

    def test_third_continue_stalls_outputs_empty_json_and_progress_or_resume_resets(self):
        payload = {"hookEventName": "Stop", "cwd": str(self.proj), "terminationReason": "NO_TOOL_CALL"}
        self.start()
        for _ in range(3):
            p = self.run_guard(payload)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(json.loads(p.stdout)["decision"], "continue")
        p_stall = self.run_guard(payload)
        self.assertEqual((p_stall.returncode, p_stall.stdout), (0, "{}\n"))
        self.assertTrue(self.engine("status")[1]["plan"].endswith(" · stalled"))
        p_already = self.run_guard(payload)
        self.assertEqual((p_already.returncode, p_already.stdout), (0, "{}\n"))
        # Resume clears stalled and restores continuations
        self.assertNotIn("stalled", self.engine("resume")[1]["plan"])
        self.assertEqual(json.loads(self.run_guard(payload).stdout)["decision"], "continue")
        self.assertEqual(json.loads(self.run_guard(payload).stdout)["decision"], "continue")
        # Accepted submission resets the counter
        revised = self.base / "revised.txt"
        revised.write_text(INTRO)
        self.assertEqual(self.submit({"text_file": str(revised), "exceptions": []})[0], 0)
        for _ in range(3):
            self.assertEqual(json.loads(self.run_guard(payload).stdout)["decision"], "continue")
        self.assertEqual(self.run_guard(payload).stdout, "{}\n")

    def test_malformed_stdin_under_antigravity_format_allows_stop_with_empty_json(self):
        self.start()
        for bad in ("", "not json", "[1, 2]", "null", b"\xff\xfe"):
            with self.subTest(bad=bad):
                p = self.run_guard(bad, "--format", "antigravity", cwd=self.proj)
                stdout = p.stdout.decode("utf-8") if isinstance(p.stdout, bytes) else p.stdout
                self.assertEqual((p.returncode, stdout), (0, "{}\n"))
        # Valid empty JSON object is NOT malformed: falls back to process cwd and continues.
        p_valid = self.run_guard("{}", "--format", "antigravity", cwd=self.proj)
        self.assertEqual(p_valid.returncode, 0, p_valid.stderr)
        self.assertEqual(json.loads(p_valid.stdout)["decision"], "continue")

    def test_unexpected_internal_error_under_antigravity_outputs_empty_json_and_exits_zero(self):
        broken = self.proj / ".agents" / "log" / "science-research-writing" / "20260101-000000-revise-introduction"
        broken.mkdir(parents=True)
        (broken / "state.json").write_text(json.dumps({"status": "open"}))  # missing required keys -> KeyError in decide
        for extra in ((), ("--format", "antigravity")):
            with self.subTest(extra=extra):
                p = self.run_guard({"hookEventName": "Stop", "cwd": str(self.proj)}, *extra)
                self.assertEqual((p.returncode, p.stdout, p.stderr), (0, "{}\n", ""))


if __name__ == "__main__":
    unittest.main()
