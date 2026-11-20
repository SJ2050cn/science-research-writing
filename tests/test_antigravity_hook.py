"""Black-box tests for the Antigravity hook installer (scripts/install_antigravity_hook.py),
run as a subprocess against a temporary hooks.json. SCIENCE_RESEARCH_WRITING_ANTIGRAVITY_HOOKS
redirects the hooks file; HOME is a temporary folder too, so nothing here can reach
the real ~/.gemini/config/hooks.json."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sandbox import ANTIGRAVITY_HOOKS_ENV, HOOKS_ENV, LOCK_ENV, PROFILE_ENV, REAL_HOME, assert_sandboxed, sandbox_env

SCRIPTS = (Path(__file__).resolve().parent.parent / "scripts").resolve()
INSTALLER = SCRIPTS / "install_antigravity_hook.py"
MARKER = "science-research-writing-guard"
EXISTING = {
    "lint-checker": {
        "PostToolUse": [
            {"matcher": "run_command", "hooks": [{"type": "command", "command": "./scripts/lint.sh", "timeout": 10}]}
        ]
    },
    "safety-gate": {
        "enabled": False,
        "PreToolUse": [
            {"matcher": "run_command", "hooks": [{"command": "./scripts/safety-check.sh"}]}
        ]
    },
    "reminder": {
        "PreInvocation": [{"type": "command", "command": "./scripts/reminder.sh"}]
    },
    "other-stop": {
        "Stop": [{"type": "command", "command": "/bin/echo other-stop", "timeout": 5}]
    },
    "custom-sibling": {"nonstandard": [1, "kept", {"nested": True}]},
}


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
        self.hooks = self.base / "antigravity" / "hooks.json"
        self.bak = self.hooks.with_name("hooks.json.bak")

    def run_script(self, *args, script=INSTALLER, env=None):
        p = subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True, env=env)
        return p.returncode, p.stdout, p.stderr

    def write(self, data):
        self.hooks.parent.mkdir(parents=True, exist_ok=True)
        self.hooks.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def load(self):
        return json.loads(self.hooks.read_text(encoding="utf-8"))


class TestSandboxIsolation(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name).resolve()
        self.env = sandbox_env(self.base)

    def test_sandbox_sets_antigravity_hooks_and_rejects_real_gemini_dir(self):
        self.assertIn(ANTIGRAVITY_HOOKS_ENV, self.env)
        self.assertTrue(Path(self.env[ANTIGRAVITY_HOOKS_ENV]).resolve().is_relative_to(self.base))
        assert_sandboxed(self.env)

        with self.assertRaises(AssertionError):
            assert_sandboxed({k: v for k, v in self.env.items() if k != ANTIGRAVITY_HOOKS_ENV})
        with self.assertRaises(AssertionError):
            assert_sandboxed(dict(self.env, **{
                ANTIGRAVITY_HOOKS_ENV: str(REAL_HOME / ".gemini" / "config" / "hooks.json")
            }))
        with self.assertRaises(AssertionError):
            assert_sandboxed(dict(self.env, **{
                HOOKS_ENV: str(REAL_HOME / ".gemini" / "config" / "hooks.json")
            }))
        with self.assertRaises(AssertionError):
            assert_sandboxed(dict(self.env, **{
                LOCK_ENV: str(REAL_HOME / ".gemini" / "skill-lock.json")
            }))
        with self.assertRaises(AssertionError):
            assert_sandboxed(dict(self.env, **{
                PROFILE_ENV: str(REAL_HOME / ".gemini" / "profile")
            }))


class TestInstaller(HookCase):
    def test_creates_the_file_when_missing_without_a_backup(self):
        code, out, err = self.run_script()
        self.assertEqual(code, 0, err)
        self.assertFalse(self.bak.exists())
        data = self.load()
        self.assertEqual(list(data.keys()), [MARKER])
        entry = data[MARKER]
        self.assertNotEqual(entry.get("enabled"), False)
        stops = entry["Stop"]
        self.assertEqual(len(stops), 1)
        self.assertEqual(stops[0]["type"], "command")
        self.assertEqual(stops[0]["timeout"], 10)
        self.assertIn(MARKER, stops[0]["command"])
        self.assertIn(str(SCRIPTS / "engine.py"), stops[0]["command"])
        self.assertIn("guard --format antigravity", stops[0]["command"])
        self.assertIsNone(re.search(r"(?:^|\s)/hooks(?:\s|[.,;]|$)", out))
        self.assertNotIn("Codex", out)
        self.assertNotIn("trust", out.lower())
        self.assertIn("~/.gemini/config/hooks.json", out)
        self.assertIn("automatically", out.lower())

    def test_defaults_to_home_gemini_config_hooks_json(self):
        env = dict(os.environ)
        env.pop(ANTIGRAVITY_HOOKS_ENV, None)
        code, out, err = self.run_script(env=env)
        self.assertEqual(code, 0, err)
        default_path = self.base / "home" / ".gemini" / "config" / "hooks.json"
        self.assertTrue(default_path.is_file())
        self.assertFalse(self.hooks.exists())
        data = json.loads(default_path.read_text(encoding="utf-8"))
        self.assertIn(MARKER, data)

    def test_merges_keeping_sibling_hooks_and_backs_up_first(self):
        self.write(EXISTING)
        before = self.hooks.read_bytes()
        code, out, err = self.run_script()
        self.assertEqual(code, 0, err)
        self.assertEqual(self.bak.read_bytes(), before)
        self.assertIn("hooks.json.bak", out)
        data = self.load()
        for key, value in EXISTING.items():
            self.assertEqual(data[key], value)
        self.assertIn(MARKER, data)
        self.assertEqual(len(data[MARKER]["Stop"]), 1)

    def test_second_run_changes_nothing(self):
        self.write(EXISTING)
        self.run_script()
        after_first, bak_first = self.hooks.read_bytes(), self.bak.read_bytes()
        code, out, err = self.run_script()
        self.assertEqual(code, 0, err)
        self.assertEqual((self.hooks.read_bytes(), self.bak.read_bytes()), (after_first, bak_first))
        self.assertIn("already", out.lower())
        self.assertIsNone(re.search(r"(?:^|\s)/hooks(?:\s|[.,;]|$)", out))
        self.assertIn("~/.gemini/config/hooks.json", out)

    def test_already_installed_entry_without_backup_is_untouched(self):
        self.assertEqual(self.run_script()[0], 0)
        entry = self.load()[MARKER]
        custom = dict(EXISTING)
        custom[MARKER] = {"enabled": True, "Stop": entry["Stop"]}
        self.hooks.write_text(json.dumps(custom, indent=4), encoding="utf-8")
        before = self.hooks.read_bytes()
        code, out, err = self.run_script()
        self.assertEqual(code, 0, err)
        self.assertEqual(self.hooks.read_bytes(), before)
        self.assertFalse(self.bak.exists())
        self.assertIn("already", out.lower())

    def test_unknown_argument_exits_nonzero_and_changes_nothing(self):
        code, out, err = self.run_script("--bogus")
        self.assertEqual(code, 2)
        self.assertFalse(self.hooks.exists())
        self.assertIn("usage:", (out + err).lower())

    def test_disabled_entry_is_replaced_in_place(self):
        self.run_script()
        current = self.load()[MARKER]
        disabled = dict(EXISTING)
        disabled[MARKER] = {"enabled": False, "Stop": current["Stop"]}
        self.hooks.unlink()
        self.write(disabled)
        before = self.hooks.read_bytes()
        code, out, err = self.run_script()
        self.assertEqual(code, 0, err)
        self.assertNotIn("already", out.lower())
        self.assertEqual(self.bak.read_bytes(), before)
        data = self.load()
        for key, value in EXISTING.items():
            self.assertEqual(data[key], value)
        self.assertNotIn("enabled", data[MARKER])
        self.assertEqual(data[MARKER]["Stop"], current["Stop"])
        # Repeat run is now a no-op
        code2, out2, err2 = self.run_script()
        self.assertEqual(code2, 0, err2)
        self.assertIn("already", out2.lower())

    def test_moved_skill_entry_is_replaced_in_place(self):
        self.run_script()
        current_cmd = self.load()[MARKER]["Stop"][0]["command"]
        moved_cmd = current_cmd.replace(str(SCRIPTS), str(self.base / "old-location" / "scripts"))
        moved = dict(EXISTING)
        moved[MARKER] = {"Stop": [{"type": "command", "command": moved_cmd, "timeout": 10}]}
        self.hooks.unlink()
        self.write(moved)
        before = self.hooks.read_bytes()
        code, out, err = self.run_script()
        self.assertEqual(code, 0, err)
        self.assertNotIn("already", out.lower())
        self.assertEqual(self.bak.read_bytes(), before)
        data = self.load()
        for key, value in EXISTING.items():
            self.assertEqual(data[key], value)
        self.assertEqual(data[MARKER]["Stop"][0]["command"], current_cmd)

    def test_reinstall_keeps_the_first_backup(self):
        self.hooks.parent.mkdir(parents=True, exist_ok=True)
        self.hooks.write_text(json.dumps(EXISTING, indent=4), encoding="utf-8")
        before = self.hooks.read_bytes()
        self.assertEqual(self.run_script()[0], 0)
        self.assertEqual(self.run_script("--uninstall")[0], 0)
        self.assertEqual(self.run_script()[0], 0)
        self.assertEqual(self.bak.read_bytes(), before)

    def test_command_uses_the_real_install_path(self):
        link = self.base / "linked-scripts"
        link.symlink_to(SCRIPTS)
        code, out, err = self.run_script(script=link / "install_antigravity_hook.py")
        self.assertEqual(code, 0, err)
        cmd = self.load()[MARKER]["Stop"][0]["command"]
        self.assertIn(str(SCRIPTS / "engine.py"), cmd)
        self.assertNotIn(str(link), cmd)

    def test_uninstall_removes_only_its_own_entry(self):
        self.write(EXISTING)
        self.assertEqual(self.run_script()[0], 0)
        code, out, err = self.run_script("--uninstall")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.load(), EXISTING)
        self.assertIn("Removed", out)
        code2, out2, err2 = self.run_script("--uninstall")
        self.assertEqual(code2, 0, err2)
        self.assertEqual(self.load(), EXISTING)
        self.assertIn("nothing to remove", out2)

    def test_uninstall_with_no_file_does_nothing(self):
        code, out, err = self.run_script("--uninstall")
        self.assertEqual(code, 0, err)
        self.assertFalse(self.hooks.exists())
        self.assertFalse(self.hooks.parent.exists())

    def test_invalid_and_non_object_hooks_files_are_left_alone(self):
        self.hooks.parent.mkdir(parents=True, exist_ok=True)
        for bad in ("{not json", "[]", '"string"', "42", "null"):
            for args in ((), ("--uninstall",)):
                with self.subTest(bad=bad, args=args):
                    if self.bak.exists():
                        self.bak.unlink()
                    self.hooks.write_text(bad, encoding="utf-8")
                    code, out, err = self.run_script(*args)
                    self.assertNotEqual(code, 0)
                    self.assertEqual(self.hooks.read_text(encoding="utf-8"), bad)
                    self.assertFalse(self.bak.exists())
                    self.assertIn("error:", (out + err).lower())
                    self.assertNotIn("Traceback", out + err)

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root ignores chmod permissions")
    def test_unwritable_hooks_dir_fails_cleanly_without_traceback_or_tmp(self):
        self.hooks.parent.mkdir(parents=True, exist_ok=True)
        self.hooks.parent.chmod(0o555)
        self.addCleanup(self.hooks.parent.chmod, 0o755)
        code, out, err = self.run_script()
        self.assertEqual(code, 1)
        self.assertIn("error:", err.lower())
        self.assertIn(str(self.hooks), err)
        self.assertNotIn("Traceback", out + err)
        self.assertFalse(self.hooks.with_name("hooks.json.tmp").exists())

        # Existing readable hooks.json in a read-only folder also fails cleanly on install and --uninstall.
        self.hooks.parent.chmod(0o755)
        self.assertEqual(self.run_script()[0], 0)
        before = self.hooks.read_bytes()
        self.hooks.parent.chmod(0o555)
        code_u, out_u, err_u = self.run_script("--uninstall")
        self.assertEqual(code_u, 1)
        self.assertIn("error:", err_u.lower())
        self.assertIn(str(self.hooks), err_u)
        self.assertNotIn("Traceback", out_u + err_u)
        self.assertEqual(self.hooks.read_bytes(), before)
        self.assertFalse(self.hooks.with_name("hooks.json.tmp").exists())

    def test_installed_command_outputs_empty_json_when_engine_is_gone(self):
        self.assertEqual(self.run_script()[0], 0)
        cmd = self.load()[MARKER]["Stop"][0]["command"]
        gone = cmd.replace(str(SCRIPTS), str(self.base / "removed"))
        payload = json.dumps({"hookEventName": "Stop", "terminationReason": "NO_TOOL_CALL"})
        p = subprocess.run(["sh", "-c", gone], input=payload, capture_output=True, text=True)
        self.assertEqual((p.returncode, p.stdout, p.stderr), (0, "{}\n", ""))

    def test_installed_command_outputs_empty_json_when_python3_is_missing(self):
        self.assertEqual(self.run_script()[0], 0)
        cmd = self.load()[MARKER]["Stop"][0]["command"]
        cat_bin = shutil.which("cat")
        self.assertIsNotNone(cat_bin)
        fake_bin = self.base / "no-python-bin"
        fake_bin.mkdir()
        (fake_bin / "cat").symlink_to(cat_bin)
        payload = json.dumps({"hookEventName": "Stop", "terminationReason": "NO_TOOL_CALL"})
        env = dict(os.environ, PATH=str(fake_bin))
        p = subprocess.run(["/bin/sh", "-c", cmd], input=payload, capture_output=True, text=True, env=env)
        self.assertEqual((p.returncode, p.stdout, p.stderr), (0, "{}\n", ""))

    def test_installed_command_runs_guard_with_antigravity_format(self):
        self.assertEqual(self.run_script()[0], 0)
        cmd = self.load()[MARKER]["Stop"][0]["command"]
        proj = self.base / "proj"
        (proj / ".git").mkdir(parents=True)
        (proj / "a.tex").write_text(
            "\\section{Introduction}\nWe used 3 wells. Land use matters for nitrate in groundwater, "
            "so we ask how far it predicts the risk to drinking water.\n",
            encoding="utf-8",
        )
        ag_payload = json.dumps({
            "hookEventName": "Stop",
            "workspacePaths": [str(proj)],
            "terminationReason": "NO_TOOL_CALL",
        })
        # Run from the hooks.json directory (outside the project), mirroring Antigravity's hook runner.
        p = subprocess.run(["sh", "-c", cmd], input=ag_payload, capture_output=True, text=True,
                           cwd=str(self.hooks.parent))
        self.assertEqual((p.returncode, p.stdout, p.stderr), (0, "{}\n", ""))

        engine = [sys.executable, str(SCRIPTS / "engine.py")]
        started = subprocess.run(
            engine + ["start", "--section", "introduction", "--mode", "revise", "--samples", "no", "--input", "a.tex"],
            capture_output=True, text=True, cwd=str(proj),
        )
        self.assertEqual(started.returncode, 0, started.stderr)

        p = subprocess.run(["sh", "-c", cmd], input=ag_payload, capture_output=True, text=True,
                           cwd=str(self.hooks.parent))
        self.assertEqual((p.returncode, p.stderr), (0, ""))
        out = json.loads(p.stdout)
        self.assertEqual(out["decision"], "continue")
        self.assertIn("revise", out["reason"])

        # Even without Antigravity camelCase keys, --format antigravity forces the Antigravity contract.
        p_cwd_only = subprocess.run(["sh", "-c", cmd], input=json.dumps({"cwd": str(proj)}),
                                    capture_output=True, text=True, cwd=str(self.hooks.parent))
        self.assertEqual((p_cwd_only.returncode, p_cwd_only.stderr), (0, ""))
        self.assertEqual(json.loads(p_cwd_only.stdout)["decision"], "continue")

        # User cancellation allows stop immediately with {}.
        cancel = json.dumps({
            "hookEventName": "Stop",
            "workspacePaths": [str(proj)],
            "terminationReason": "USER_CANCELED",
        })
        p_cancel = subprocess.run(["sh", "-c", cmd], input=cancel, capture_output=True, text=True,
                                  cwd=str(self.hooks.parent))
        self.assertEqual((p_cancel.returncode, p_cancel.stdout, p_cancel.stderr), (0, "{}\n", ""))


if __name__ == "__main__":
    unittest.main()
