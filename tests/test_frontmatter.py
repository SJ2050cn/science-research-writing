"""The skill's frontmatter registers the guard as a Stop hook and pre-approves the engine.
The hook command is run for real with `sh -c`, with HOME and the project in temporary folders."""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from sandbox import assert_sandboxed, sandbox_env

SKILL = Path(__file__).resolve().parent.parent
FRONT = SKILL.joinpath("SKILL.md").read_text(encoding="utf-8").split("---")[1]


def hook_command():
    m = re.search(r"^\s+command: '(.*)'\s*$", FRONT, re.M)
    return m.group(1).replace("''", "'") if m else None


class TestFrontmatter(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name).resolve()
        self.env = dict(os.environ, **sandbox_env(self.base))
        assert_sandboxed(self.env)
        self.proj = self.base / "proj"
        (self.proj / ".git").mkdir(parents=True)
        (self.proj / "a.tex").write_text("\\section{Introduction}\nWe used 3 wells. Land use matters for nitrate in groundwater, so we ask how far it predicts the risk to drinking water.\n")

    def hook(self, **env):
        e = {k: v for k, v in self.env.items() if k not in ("CLAUDE_PLUGIN_ROOT", "CLAUDE_PROJECT_DIR")}
        e.update(env)
        return subprocess.run(["sh", "-c", hook_command()], input=json.dumps({"cwd": str(self.proj)}),
                              capture_output=True, text=True, env=e, cwd=str(self.base))

    def start_run(self):
        subprocess.run([sys.executable, str(SKILL / "scripts" / "engine.py"), "start", "--section", "introduction",
                        "--mode", "revise", "--samples", "no", "--input", "a.tex"],
                       cwd=str(self.proj), env=self.env, check=True, capture_output=True)

    def test_stop_hook_runs_the_guard(self):
        self.assertIsNotNone(hook_command(), "no Stop hook command in the frontmatter")
        self.assertRegex(FRONT, r"(?m)^hooks:\n  Stop:")
        self.assertIn('engine.py" guard', hook_command())

    def test_hook_blocks_through_the_skill_folder_the_agent_exports(self):
        self.start_run()
        p = self.hook(CLAUDE_PLUGIN_ROOT=str(SKILL))  # observed on Claude Code 2.1.325
        self.assertEqual(json.loads(p.stdout)["decision"], "block")

    def test_hook_blocks_through_the_project_skill_folder(self):
        self.start_run()
        skills = self.proj / ".claude" / "skills"
        skills.mkdir(parents=True)
        (skills / "science-research-writing").symlink_to(SKILL)
        p = self.hook(CLAUDE_PROJECT_DIR=str(self.proj))
        self.assertEqual(json.loads(p.stdout)["decision"], "block")

    def test_hook_is_quiet_when_it_cannot_find_the_engine(self):
        self.start_run()
        p = self.hook(CLAUDE_PLUGIN_ROOT=str(self.base / "nowhere"), CLAUDE_PROJECT_DIR=str(self.base / "nowhere"))
        self.assertEqual((p.returncode, p.stdout, p.stderr), (0, "", ""))

    def test_engine_command_is_pre_approved(self):
        self.assertIn("allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/engine.py *)", FRONT)

    def test_existing_frontmatter_is_kept(self):
        self.assertIn("name: science-research-writing", FRONT)
        self.assertIn("compatibility: Needs Python 3.9", FRONT)


if __name__ == "__main__":
    unittest.main()
