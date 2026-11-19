"""Black-box tests for the Codex hook installer (scripts/install_codex_hook.py),
run as a subprocess against a temporary hooks.json. SCIENCE_RESEARCH_WRITING_CODEX_HOOKS
redirects the hooks file; HOME is a temporary folder too, so nothing here can reach
the real ~/.codex/hooks.json."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sandbox import HOOKS_ENV, REAL_HOME, assert_sandboxed, sandbox_env

SCRIPTS = (Path(__file__).resolve().parent.parent / "scripts").resolve()
INSTALLER = SCRIPTS / "install_codex_hook.py"
OTHER = {"type": "command", "command": "/bin/echo other-tool", "timeout": 5}
EXISTING = {"hooks": {
    "SessionStart": [{"hooks": [OTHER]}],
    "Stop": [{"hooks": [OTHER, {"type": "command", "command": "/bin/echo second"}]}],
}}


class HookCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name).resolve()
        self.env = sandbox_env(self.base)
        assert_sandboxed(self.env)
        patch = mock.patch.dict(os.environ, self.env)
        patch.start()
        self.addCleanup(patch.stop)
        self.hooks = self.base / "codex" / "hooks.json"
        self.bak = self.hooks.with_name("hooks.json.bak")
        self.hooks.parent.mkdir()

    def run_script(self, *args, script=INSTALLER):
        p = subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True)
        return p.returncode, p.stdout, p.stderr

    def write(self, data):
        self.hooks.write_text(json.dumps(data, indent=2) + "\n")

    def load(self):
        return json.loads(self.hooks.read_text())

    def own_commands(self, data=None):
        data = data or self.load()
        return [h["command"] for g in data["hooks"].get("Stop", []) for h in g["hooks"]
                if "science-research-writing-guard" in h["command"]]


class TestInstaller(HookCase):
    def test_sandbox_guard_rejects_the_real_home(self):
        with self.assertRaises(AssertionError):
            assert_sandboxed(dict(self.env, **{HOOKS_ENV: str(REAL_HOME / ".codex" / "hooks.json")}))
        with self.assertRaises(AssertionError):
            assert_sandboxed({k: v for k, v in self.env.items() if k != HOOKS_ENV})

    def test_creates_the_file_when_missing_without_a_backup(self):
        code, out, err = self.run_script()
        self.assertEqual(code, 0, err)
        self.assertEqual(len(self.own_commands()), 1)
        self.assertFalse(self.bak.exists())

    def test_merges_keeping_existing_hooks_and_backs_up_first(self):
        self.write(EXISTING)
        before = self.hooks.read_bytes()
        code, out, err = self.run_script()
        self.assertEqual(code, 0, err)
        self.assertEqual(self.bak.read_bytes(), before)
        data = self.load()
        self.assertEqual(data["hooks"]["SessionStart"], EXISTING["hooks"]["SessionStart"])
        self.assertEqual(data["hooks"]["Stop"][0], EXISTING["hooks"]["Stop"][0])
        self.assertEqual(len(self.own_commands(data)), 1)

    def test_a_reinstall_keeps_the_first_backup(self):
        self.hooks.write_text(json.dumps(EXISTING, indent=4))  # not the engine's own layout
        before = self.hooks.read_bytes()
        self.run_script()
        self.run_script("--uninstall")
        self.run_script()
        self.assertEqual(self.bak.read_bytes(), before)

    def test_second_run_changes_nothing(self):
        self.write(EXISTING)
        self.run_script()
        after_first, bak_first = self.hooks.read_bytes(), self.bak.read_bytes()
        code, out, _ = self.run_script()
        self.assertEqual(code, 0)
        self.assertEqual((self.hooks.read_bytes(), self.bak.read_bytes()), (after_first, bak_first))
        self.assertIn("already", out)

    def test_command_uses_the_real_install_path(self):
        link = self.base / "linked-scripts"
        link.symlink_to(SCRIPTS)
        self.assertEqual(self.run_script(script=link / "install_codex_hook.py")[0], 0)
        command = self.own_commands()[0]
        self.assertIn(str(SCRIPTS / "engine.py"), command)
        self.assertNotIn(str(link), command)

    def test_reminds_to_trust_the_hook(self):
        self.assertIn("/hooks", self.run_script()[1])
        self.assertIn("/hooks", self.run_script()[1])  # also when nothing changed

    def test_uninstall_removes_only_its_own_entry(self):
        self.write(EXISTING)
        self.run_script()
        code, out, err = self.run_script("--uninstall")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.load(), EXISTING)
        self.assertEqual(self.run_script("--uninstall")[0], 0)  # nothing left: still fine
        self.assertEqual(self.load(), EXISTING)

    def test_uninstall_with_no_file_does_nothing(self):
        self.assertEqual(self.run_script("--uninstall")[0], 0)
        self.assertFalse(self.hooks.exists())

    def test_invalid_hooks_file_is_left_alone(self):
        self.hooks.write_text("{not json")
        code, out, err = self.run_script()
        self.assertNotEqual(code, 0)
        self.assertEqual(self.hooks.read_text(), "{not json")
        self.assertFalse(self.bak.exists())

    def test_installed_command_is_quiet_when_the_engine_is_gone(self):
        self.run_script()
        command = self.own_commands()[0]
        gone = command.replace(str(SCRIPTS), str(self.base / "removed"))
        p = subprocess.run(["sh", "-c", gone], input="{}", capture_output=True, text=True)
        self.assertEqual((p.returncode, p.stdout, p.stderr), (0, "", ""))

    def test_installed_command_runs_the_guard_when_the_engine_exists(self):
        self.run_script()
        proj = self.base / "proj"
        (proj / ".git").mkdir(parents=True)
        (proj / "a.tex").write_text("\\section{Introduction}\nWe used 3 wells. Land use matters for nitrate in groundwater, so we ask how far it predicts the risk to drinking water.\n")
        payload = json.dumps({"cwd": str(proj)})
        run = lambda cmd: subprocess.run(cmd, input=payload, capture_output=True, text=True, cwd=str(proj))
        p = run(["sh", "-c", self.own_commands()[0]])
        self.assertEqual((p.returncode, p.stdout), (0, ""))  # no open run
        engine = [sys.executable, str(SCRIPTS / "engine.py")]
        self.assertEqual(run(engine + ["start", "--section", "introduction", "--mode", "revise", "--samples", "no",
                                       "--input", "a.tex"]).returncode, 0)
        p = run(["sh", "-c", self.own_commands()[0]])
        self.assertEqual(json.loads(p.stdout)["decision"], "block")


if __name__ == "__main__":
    unittest.main()
