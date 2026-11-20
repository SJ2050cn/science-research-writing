"""Black-box tests for scripts/uninstall.py, run as a subprocess. HOME, the profile folder,
the Codex hooks file and the skills lock file all point into a temporary folder."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sandbox import LOCK_ENV, assert_sandboxed, sandbox_env

SCRIPTS = (Path(__file__).resolve().parent.parent / "scripts").resolve()
UNINSTALL = SCRIPTS / "uninstall.py"
INSTALLER = SCRIPTS / "install_codex_hook.py"
AG_INSTALLER = SCRIPTS / "install_antigravity_hook.py"
OTHER = {"type": "command", "command": "/bin/echo other-tool"}
AG_SIBLINGS = {
    "lint-checker": {"PostToolUse": [{"matcher": "run_command", "hooks": [OTHER]}]},
    "other-stop": {"Stop": [OTHER]},
}
NAME = "science-research-writing"


class UninstallCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name).resolve()
        env = sandbox_env(self.base)
        assert_sandboxed(env)
        patch = mock.patch.dict(os.environ, env)
        patch.start()
        self.addCleanup(patch.stop)
        self.profile_dir = self.base / "profile"
        self.profile = self.profile_dir / "user-style.md"
        self.profile_dir.mkdir()
        self.profile.write_text("## Sentences\n- Use we. (stated, 2026-11-18)\n")
        self.hooks = self.base / "codex" / "hooks.json"
        self.hooks.parent.mkdir()
        self.hooks.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [OTHER]}]}}))
        subprocess.run([sys.executable, str(INSTALLER)], check=True, capture_output=True)
        self.ag_hooks = self.base / "antigravity" / "hooks.json"
        self.ag_hooks.parent.mkdir()
        self.ag_hooks.write_text(json.dumps(AG_SIBLINGS))
        subprocess.run([sys.executable, str(AG_INSTALLER)], check=True, capture_output=True)
        self.logs = self.base / "proj" / ".agents" / "log" / NAME / "20260101-000000-revise-abstract"
        self.logs.mkdir(parents=True)
        (self.logs / "state.json").write_text("{}")

    def run_script(self, *args, stdin=subprocess.DEVNULL):
        p = subprocess.run([sys.executable, str(UNINSTALL), *args], stdin=stdin, capture_output=True, text=True)
        return p.returncode, p.stdout, p.stderr

    def hook_commands(self):
        return [h["command"] for g in json.loads(self.hooks.read_text())["hooks"]["Stop"] for h in g["hooks"]]

    def ag_data(self):
        return json.loads(self.ag_hooks.read_text())


class TestUninstall(UninstallCase):
    def test_keep_profile_removes_only_the_hook(self):
        code, out, err = self.run_script("--keep-profile")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.hook_commands(), [OTHER["command"]])
        self.assertEqual(self.ag_data(), AG_SIBLINGS)
        self.assertIn("Antigravity", out)
        self.assertTrue(self.profile.exists())

    def test_remove_profile_deletes_it_and_its_backups(self):
        (self.profile_dir / "user-style.previous.md").write_text("old")
        code, out, err = self.run_script("--remove-profile")
        self.assertEqual(code, 0, err)
        self.assertFalse(self.profile_dir.exists())

    def test_remove_profile_keeps_unrelated_files_in_the_folder(self):
        (self.profile_dir / "notes.txt").write_text("mine")
        self.run_script("--remove-profile")
        self.assertFalse(self.profile.exists())
        self.assertTrue((self.profile_dir / "notes.txt").exists())

    def test_without_a_terminal_and_without_a_flag_the_profile_is_kept(self):
        code, out, _ = self.run_script()
        self.assertEqual(code, 0)
        self.assertTrue(self.profile.exists())
        self.assertIn("--remove-profile", out)

    def test_contradicting_flags_are_refused_and_change_nothing(self):
        before = self.hooks.read_bytes()
        ag_before = self.ag_hooks.read_bytes()
        self.assertNotEqual(self.run_script("--keep-profile", "--remove-profile")[0], 0)
        self.assertEqual(self.hooks.read_bytes(), before)
        self.assertEqual(self.ag_hooks.read_bytes(), ag_before)
        self.assertTrue(self.profile.exists())

    def test_never_touches_project_logs(self):
        self.run_script("--remove-profile")
        self.assertTrue((self.logs / "state.json").exists())

    def test_asks_on_a_terminal_and_defaults_to_keep(self):
        import pty
        for answer, kept in (("\n", True), ("n\n", True), ("y\n", False)):
            with self.subTest(answer=answer):
                self.profile_dir.mkdir(exist_ok=True)
                self.profile.write_text("## Sentences\n")
                master, slave = pty.openpty()
                os.write(master, answer.encode())
                code, out, err = self.run_script(stdin=slave)
                os.close(master), os.close(slave)
                self.assertEqual(code, 0, err)
                self.assertEqual(self.profile.exists(), kept)

    def test_missing_hooks_file_and_missing_profile_are_fine(self):
        self.hooks.unlink()
        self.ag_hooks.unlink()
        self.profile.unlink()
        self.assertEqual(self.run_script("--remove-profile")[0], 0)
        self.assertFalse(self.hooks.exists())
        self.assertFalse(self.ag_hooks.exists())

    def test_succeeds_when_only_one_hooks_file_exists(self):
        # Only Antigravity hooks file exists (Codex absent).
        self.hooks.unlink()
        code, out, err = self.run_script("--keep-profile")
        self.assertEqual(code, 0, err)
        self.assertFalse(self.hooks.exists())
        self.assertEqual(self.ag_data(), AG_SIBLINGS)
        self.assertIn("Removed the Antigravity guard hook", out)

        # Only Codex hooks file exists (Antigravity absent).
        self.ag_hooks.unlink()
        self.hooks.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [OTHER]}]}}))
        subprocess.run([sys.executable, str(INSTALLER)], check=True, capture_output=True)
        code, out, err = self.run_script("--keep-profile")
        self.assertEqual(code, 0, err)
        self.assertFalse(self.ag_hooks.exists())
        self.assertEqual(self.hook_commands(), [OTHER["command"]])
        self.assertIn("Removed the Codex guard hook", out)
        self.assertIn("No Antigravity guard hook to remove", out)

    def test_broken_antigravity_hooks_file_is_reported_and_the_rest_still_runs(self):
        self.ag_hooks.write_text('{"a": 1,}\n')
        code, out, err = self.run_script("--remove-profile")
        self.assertEqual(code, 1)
        self.assertIn("Antigravity", err)
        self.assertNotIn("Traceback", err)
        self.assertEqual(self.ag_hooks.read_text(), '{"a": 1,}\n')  # left unchanged
        self.assertEqual(self.hook_commands(), [OTHER["command"]])  # Codex hook still removed
        self.assertFalse(self.profile.exists())
        self.assertIn('rm -rf "%s"' % SCRIPTS.parent, out)


class TestRemovalCommand(UninstallCase):
    def test_npx_command_when_the_lock_file_lists_the_skill(self):
        Path(os.environ[LOCK_ENV]).write_text(json.dumps({"version": 3, "skills": {NAME: {"source": "x"}}}))
        out = self.run_script("--keep-profile")[1]
        self.assertIn("npx skills remove science-research-writing -g", out)
        self.assertNotIn("rm ", out)

    def test_rm_commands_for_a_local_install(self):
        Path(os.environ[LOCK_ENV]).write_text(json.dumps({"version": 3, "skills": {"other": {}}}))
        link = self.base / "home" / ".claude" / "skills" / NAME
        link.parent.mkdir(parents=True)
        link.symlink_to(SCRIPTS.parent)
        out = self.run_script("--keep-profile")[1]
        self.assertNotIn("npx skills", out)
        self.assertIn('rm "%s"' % link, out)
        self.assertIn('rm -rf "%s"' % SCRIPTS.parent, out)
        self.assertTrue(link.is_symlink())  # printed, never run

    def test_rm_commands_when_there_is_no_lock_file(self):
        out = self.run_script("--keep-profile")[1]
        self.assertIn('rm -rf "%s"' % SCRIPTS.parent, out)

    def test_rm_commands_include_antigravity_symlink_for_local_install(self):
        Path(os.environ[LOCK_ENV]).write_text(json.dumps({"version": 3, "skills": {"other": {}}}))
        link = self.base / "home" / ".gemini" / "config" / "skills" / NAME
        link.parent.mkdir(parents=True)
        link.symlink_to(SCRIPTS.parent)
        out = self.run_script("--keep-profile")[1]
        self.assertNotIn("npx skills", out)
        self.assertIn('rm "%s"' % link, out)
        self.assertIn('rm -rf "%s"' % SCRIPTS.parent, out)
        self.assertTrue(link.is_symlink())  # printed, never run

    def test_rm_commands_include_antigravity_folder_for_local_install(self):
        folder = self.base / "home" / ".gemini" / "config" / "skills" / NAME
        folder.mkdir(parents=True)
        out = self.run_script("--keep-profile")[1]
        self.assertIn('rm -rf "%s"' % folder, out)
        self.assertIn('rm -rf "%s"' % SCRIPTS.parent, out)
        self.assertTrue(folder.is_dir())  # printed, never run


if __name__ == "__main__":
    unittest.main()
