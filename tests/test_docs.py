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
        for needle in ("Python 3.9", "no extra packages", "by hand"):
            self.assertIn(needle, s)

    def test_install_sections_cover_claude_codex_and_antigravity(self):
        npx = section(README, "From GitHub with `npx skills`")
        for needle in ("npx skills add SJ2050cn/science-research-writing -g", "Antigravity"):
            self.assertIn(needle, npx)
        local = section(README, "From a local copy")
        for needle in (
            "~/.agents/skills/science-research-writing",
            "~/.claude/skills/science-research-writing",
            "~/.gemini/config/skills/science-research-writing",
            ".agents/skills/",
        ):
            self.assertIn(needle, local)

    def test_codex_section(self):
        s = section(README, "Codex: install the Stop hook")
        for needle in ("scripts/install_codex_hook.py", "/hooks", "first Codex run"):
            self.assertIn(needle, s)

    def test_antigravity_hook_section(self):
        s = section(README, "Antigravity: install the Stop hook")
        for needle in ("scripts/install_antigravity_hook.py", "~/.gemini/config/hooks.json", "first Antigravity run"):
            self.assertIn(needle, s)
        self.assertRegex(s, r"(?i)no\b[^.\n]*`/hooks`[^.\n]*trust")

    def test_approve_prompts_section(self):
        s = section(README, "Approve the engine's prompts")
        for needle in (
            "approval",
            "Codex",
            "sandbox",
            "Antigravity",
            "non-workspace",
            "global skill folder",
            "~/.agents/science-research-writing/user-style.md",
            "Antigravity Settings",
        ):
            self.assertIn(needle, s)

    def test_profile_section_names_the_new_location(self):
        s = section(README, "Your style profile")
        self.assertIn("~/.agents/science-research-writing/user-style.md", s)
        self.assertNotIn("git pull", s)
        self.assertNotRegex(s, r"user-style.md. in the skill folder")

    def test_uninstall_section_runs_the_script_before_removal(self):
        s = section(README, "Uninstall")
        for needle in (
            "before you remove the skill",
            "scripts/uninstall.py",
            "Codex",
            "Antigravity",
            "--keep-profile",
            "--remove-profile",
            "run logs",
            "prints the command that removes the skill",
        ):
            self.assertIn(needle, s)
        self.assertLess(s.index("uninstall.py"), s.index("prints the command that removes the skill"))

    def test_codex_reads_the_shared_skills_folder(self):
        self.assertNotIn("~/.codex/skills", README)

    def test_git_pull_no_longer_protects_a_profile(self):
        self.assertNotRegex(README, r"(?i)git pull[^.\n]*(never overwrites|protect)")


class TestSkillBody(unittest.TestCase):
    def test_only_the_planned_sections_remain(self):
        heads = re.findall(r"^## (.+)$", BODY, re.M)
        self.assertEqual(heads, ["Workflow", "Fallback", "Core principles", "Integrity rules"])

    def test_start_names_the_agent_so_codex_and_antigravity_get_the_guard_offer(self):
        self.assertGreaterEqual(len(re.findall(r"--agent claude\|codex\|antigravity\|other", BODY)), 2)
        self.assertNotRegex(BODY, r"--agent claude\|codex\|other")
        self.assertRegex(BODY, r"(?i)`codex`[^.\n]*`antigravity`[^.\n]*`setup`")

    def test_fallback_tells_asks_and_marks_the_plan_line(self):
        s = section(BODY, "Fallback")
        for needle in ("tell the author", "install command", "ask", "check=manual", "references/workflow.json"):
            self.assertIn(needle, s)


if __name__ == "__main__":
    unittest.main()
