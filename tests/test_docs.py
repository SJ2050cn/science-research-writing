"""README and SKILL.md carry what the install, fallback and uninstall paths promise.
Reads the two files as text; the behaviour itself is tested through the scripts elsewhere."""
import re
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
README = SKILL.joinpath("README.md").read_text(encoding="utf-8")
BODY = SKILL.joinpath("SKILL.md").read_text(encoding="utf-8").split("---", 2)[2]


def section(text, title):
    m = re.search(r"^#{2,3} %s\s*$(.*?)(?=^#{2,3} |\Z)" % re.escape(title), text, re.M | re.S)
    return m.group(1) if m else ""


class TestReadme(unittest.TestCase):
    def test_requirements_section(self):
        s = section(README, "Requirements")
        for needle in ("python3 --version", "3.9", "apt", "dnf", "brew", "WSL"):
            self.assertIn(needle, s)

    def test_codex_section(self):
        s = section(README, "Codex")
        for needle in ("scripts/install_codex_hook.py", "--uninstall", "~/.codex/hooks.json", "/hooks", "read-only", ".agents/log"):
            self.assertIn(needle, s)

    def test_permissions_section(self):
        s = section(README, "Permissions")
        for needle in ("permissions", "allow", "Bash(python3 ", "scripts/engine.py *)", "allowed-tools"):
            self.assertIn(needle, s)

    def test_profile_section_names_the_new_location(self):
        s = section(README, "Your style profile")
        self.assertIn("~/.agents/science-research-writing/user-style.md", s)
        self.assertNotIn("git pull", s)
        self.assertNotRegex(s, r"user-style.md. in the skill folder")

    def test_uninstall_section_runs_the_script_before_removal(self):
        s = section(README, "Uninstall")
        self.assertIn("scripts/uninstall.py", s)
        for needle in ("--keep-profile", "--remove-profile", "npx skills remove science-research-writing -g", ".agents/log"):
            self.assertIn(needle, s)
        self.assertLess(s.index("uninstall.py"), s.index("npx skills remove"))

    def test_codex_reads_the_shared_skills_folder(self):
        self.assertNotIn("~/.codex/skills", README)

    def test_git_pull_no_longer_protects_a_profile(self):
        self.assertNotRegex(README, r"(?i)git pull[^.\n]*(never overwrites|protect)")


class TestSkillBody(unittest.TestCase):
    def test_only_the_planned_sections_remain(self):
        heads = re.findall(r"^## (.+)$", BODY, re.M)
        self.assertEqual(heads, ["Workflow", "Fallback", "Core principles", "Integrity rules"])

    def test_start_names_the_agent_so_codex_gets_the_guard_offer(self):
        self.assertRegex(BODY, r"--agent claude\|codex\|other")

    def test_fallback_tells_asks_and_marks_the_plan_line(self):
        s = section(BODY, "Fallback")
        for needle in ("tell the author", "install command", "ask", "check=manual", "references/workflow.json"):
            self.assertIn(needle, s)


if __name__ == "__main__":
    unittest.main()
