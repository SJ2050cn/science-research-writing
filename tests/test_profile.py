"""Black-box tests for the style profile: profile commands, the one-time move,
the save-preference step, and the scan and study workflows. Every test runs the
engine's command line on temporary folders and a temporary profile location.
Run with:  python3 -m unittest discover -s tests -v
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

from sandbox import PROFILE_ENV, assert_sandboxed, sandbox_env

SKILL = Path(__file__).resolve().parent.parent
ENGINE = SKILL / "scripts" / "engine.py"
TODAY = date.today().isoformat()
HEADINGS = ["Voice & person", "Tone & certainty", "Sentences", "Terminology",
            "Conventions", "Section habits", "Exemplars", "Resolutions"]
SEED = ("# Style profile\n\n## Voice & person\n- Always write \"we\". (stated, 2026-11-01)\n"
        "- Prefer the passive in Methods. (edited, 2026-11-10)\n\n## Tone & certainty\n- Be careful with claims.\n\n"
        "## Sentences\n\n## Terminology\n\n## Conventions\n- British spelling. (stated, 2026-11-01)\n\n"
        "## Section habits\n\n## Exemplars\n\n## Resolutions\n")
OLD = "# Style profile\n\n## Conventions\n- British spelling. (stated, 2026-11-01)\n"
NEWER = "# Style profile\n\n## Conventions\n- Newer. (stated, 2026-11-10)\n"


class ProfileCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name).resolve()
        self.env = dict(os.environ, **sandbox_env(self.base))
        self.proj = self.base / "proj"
        (self.proj / ".git").mkdir(parents=True)
        self.profile = self.base / "profile" / "user-style.md"
        self.legacy = self.base / "legacy" / "user-style.md"

    def run_engine(self, *args, stdin=None, env=None):
        env = env or self.env
        assert_sandboxed(env)
        p = subprocess.run([sys.executable, str(ENGINE), *args], cwd=str(self.proj), env=env,
                           input=stdin, capture_output=True, text=True)
        out = json.loads(p.stdout) if p.stdout.strip() else None
        return p.returncode, out, p.stderr

    def submit(self, payload):
        return self.run_engine("submit", "--file", "-", stdin=json.dumps(payload))

    def padd(self, heading, text, source="stated"):
        return self.run_engine("profile", "add", "--heading", heading, "--text", text, "--source", source)

    def seed(self, text, where=None):
        where = where or self.profile
        where.parent.mkdir(parents=True, exist_ok=True)
        where.write_text(text, encoding="utf-8")

    def lines(self):
        return self.profile.read_text(encoding="utf-8").splitlines()

    def section(self, heading):
        """Bullet lines under a heading of the profile file."""
        out, on = [], False
        for ln in self.lines():
            if ln.startswith("## "):
                on = ln == "## " + heading
            elif on and ln.startswith("- "):
                out.append(ln)
        return out

    def start_section(self, *extra):
        inp = self.proj / "a.txt"
        inp.write_text("We measured nitrate in 12 wells. Land use matters for nitrate in groundwater, so we ask how far it predicts the risk to drinking water.\n")
        return self.run_engine("start", "--section", "other", "--mode", "revise", "--samples", "no",
                               "--input", str(inp), *extra)


class SandboxGuard(ProfileCase):
    def test_default_location_is_refused_under_test(self):
        with self.assertRaises(AssertionError):
            assert_sandboxed({})
        real = Path(os.path.expanduser("~")) / ".agents" / "science-research-writing"
        with self.assertRaises(AssertionError):
            assert_sandboxed({PROFILE_ENV: str(real)})
        assert_sandboxed(self.env)

    def test_default_location_is_under_home_agents(self):
        env = {k: v for k, v in self.env.items() if k != PROFILE_ENV}  # HOME is still a temp folder
        p = subprocess.run([sys.executable, str(ENGINE), "profile", "add", "--heading", "Conventions",
                            "--text", "Use the serial comma.", "--source", "stated"],
                           cwd=str(self.proj), env=env, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        default = self.base / "home" / ".agents" / "science-research-writing" / "user-style.md"
        self.assertTrue(default.is_file())
        self.assertFalse(self.profile.exists())


class ProfileCommands(ProfileCase):
    def test_first_save_creates_file_from_template(self):
        code, out, _ = self.padd("Conventions", "Use the serial comma.")
        self.assertEqual(code, 0)
        self.assertEqual([l for l in self.lines() if l.startswith("## ")], ["## " + h for h in HEADINGS])
        self.assertEqual(self.section("Conventions"), ["- Use the serial comma. (stated, %s)" % TODAY])
        self.assertIn("Conventions", out["announce"])
        self.assertIn("Use the serial comma.", out["announce"])

    def test_template_headings_match_engine_headings(self):
        tpl = (SKILL / "references" / "profile-template.md").read_text()
        self.assertEqual(re.findall(r"^## (.+)$", tpl, re.M), HEADINGS)

    def test_rejects_unknown_heading_and_source(self):
        code, _, err = self.padd("Hobbies", "x")
        self.assertEqual(code, 20)
        self.assertIn("Voice & person", err)
        code, _, err = self.padd("Conventions", "x", "guessed")
        self.assertNotEqual(code, 0)
        self.assertFalse(self.profile.exists())

    def test_all_four_sources_are_tagged(self):
        for src in ("stated", "corrected", "scanned", "edited"):
            self.assertEqual(self.padd("Sentences", "Entry from %s." % src, src)[0], 0)
        self.assertEqual(self.section("Sentences"),
                         ["- Entry from %s. (%s, %s)" % (s, s, TODAY) for s in ("stated", "corrected", "scanned", "edited")])

    def test_rejects_multiline_or_pretagged_text(self):
        self.assertEqual(self.padd("Sentences", "two\nlines")[0], 20)
        self.assertEqual(self.padd("Sentences", "Already tagged. (stated, 2026-01-01)")[0], 20)

    def test_existing_entries_untouched_by_add_and_replace(self):
        self.seed(SEED)
        self.padd("Conventions", "Use the serial comma.")
        code, out, _ = self.run_engine("profile", "replace", "--old", "British spelling.", "--heading", "Conventions",
                                       "--text", "American spelling.", "--source", "stated")
        self.assertEqual(code, 0)
        self.assertIn("British spelling", out["announce"])
        self.assertEqual(self.section("Voice & person"),
                         ["- Always write \"we\". (stated, 2026-11-01)", "- Prefer the passive in Methods. (edited, 2026-11-10)"])
        self.assertEqual(self.section("Tone & certainty"), ["- Be careful with claims."])
        self.assertEqual(sorted(self.section("Conventions")),
                         sorted(["- Use the serial comma. (stated, %s)" % TODAY, "- American spelling. (stated, %s)" % TODAY]))

    def test_remove_only_the_named_entry(self):
        self.padd("Conventions", "One.")
        self.padd("Conventions", "Two.")
        code, out, _ = self.run_engine("profile", "remove", "--line", "- One. (stated, %s)" % TODAY)
        self.assertEqual(code, 0)
        self.assertEqual(self.section("Conventions"), ["- Two. (stated, %s)" % TODAY])
        self.assertEqual(self.run_engine("profile", "remove", "--line", "Missing.")[0], 20)
        self.assertEqual(self.section("Conventions"), ["- Two. (stated, %s)" % TODAY])

    def test_replace_unknown_old_line_fails_and_writes_nothing(self):
        self.padd("Conventions", "One.")
        before = self.profile.read_text()
        code, _, _ = self.run_engine("profile", "replace", "--old", "Nope.", "--heading", "Conventions",
                                     "--text", "New.", "--source", "stated")
        self.assertEqual(code, 20)
        self.assertEqual(self.profile.read_text(), before)

    def test_sixth_exemplar_is_refused(self):
        for i in range(5):
            self.assertEqual(self.padd("Exemplars", "Passage %d." % i)[0], 0)
        before = self.profile.read_text()
        code, _, err = self.padd("Exemplars", "Passage 6.")
        self.assertEqual(code, 20)
        self.assertIn("which", err.lower())
        self.assertIn("Passage 0.", err)
        self.assertEqual(self.profile.read_text(), before)
        code, _, _ = self.run_engine("profile", "replace", "--old", "Passage 0.", "--heading", "Exemplars",
                                     "--text", "Passage 6.", "--source", "stated")
        self.assertEqual(code, 0)
        self.assertEqual(len(self.section("Exemplars")), 5)
        self.run_engine("profile", "remove", "--line", "Passage 1.")
        self.assertEqual(self.padd("Exemplars", "Passage 7.")[0], 0)


class Migration(ProfileCase):
    def test_moves_in_folder_profile_once_with_notice(self):
        self.seed(OLD, self.legacy)
        code, out, _ = self.padd("Conventions", "Use the serial comma.")
        self.assertEqual(code, 0)
        self.assertFalse(self.legacy.exists())
        self.assertIn("British spelling. (stated, 2026-11-01)", self.profile.read_text())
        self.assertIn("moved", out["notice"].lower())
        self.assertIn(str(self.profile), out["notice"])
        _, out2, _ = self.padd("Conventions", "Another.")
        self.assertIsNone(out2["notice"])

    def test_section_start_moves_profile_and_notifies(self):
        self.seed(OLD, self.legacy)
        code, out, _ = self.start_section()
        self.assertEqual(code, 0)
        self.assertTrue(self.profile.exists() and not self.legacy.exists())
        self.assertTrue(any("moved" in n.lower() for n in out["notices"]))
        self.assertIn(str(self.profile), out["read"])

    def test_both_exist_overwrites_nothing_and_asks(self):
        self.seed(OLD, self.legacy)
        self.seed(NEWER)
        code, out, _ = self.padd("Conventions", "Use the serial comma.")
        self.assertEqual(code, 0)
        self.assertIn("both", out["notice"].lower())
        self.assertTrue(self.legacy.exists())
        self.assertNotIn("British", self.profile.read_text())
        code, step, _ = self.start_section()
        self.assertEqual((step["step"]["id"], step["step"]["kind"]), ("profile-conflict", "ask"))
        self.assertTrue(self.legacy.exists())
        code, step, _ = self.submit({"choice": "keep-profile"})
        self.assertEqual(step["step"]["id"], "revise")
        self.assertFalse(self.legacy.exists())
        self.assertIn("Newer.", self.profile.read_text())
        kept = list(self.profile.parent.glob("user-style.*.md"))
        self.assertEqual(len(kept), 1)
        self.assertIn("British", kept[0].read_text())

    def test_answer_use_in_folder_keeps_current_as_backup(self):
        self.seed(OLD, self.legacy)
        self.seed(NEWER)
        self.start_section()
        code, step, _ = self.submit({"choice": "nonsense"})
        self.assertEqual((code, step["step"]["id"]), (5, "profile-conflict"))
        code, step, _ = self.submit({"choice": "use-in-folder"})
        self.assertEqual(step["step"]["id"], "revise")
        self.assertIn("British", self.profile.read_text())
        kept = list(self.profile.parent.glob("user-style.*.md"))
        self.assertIn("Newer.", kept[0].read_text())


class SectionRun(ProfileCase):
    def test_profile_listed_in_first_step_only_when_it_exists(self):
        _, step, _ = self.start_section()
        self.assertNotIn(str(self.profile), step["read"])
        self.padd("Conventions", "Use the serial comma.")
        self.run_engine("abandon")  # one open run per project
        _, step, _ = self.start_section()
        self.assertIn(str(self.profile), step["read"])
        self.assertEqual(step["step"]["id"], "revise")

    def test_no_save_preference_step_without_preference(self):
        _, step, _ = self.start_section()
        self.assertEqual(step["step"]["id"], "revise")
        self.assertEqual(step["notices"], [])

    def test_stated_preference_adds_save_preference_step_first(self):
        code, step, _ = self.start_section("--preference", "I always want the serial comma")
        self.assertEqual(code, 0)
        self.assertEqual((step["step"]["id"], step["step"]["kind"]), ("save-preference", "work"))
        self.assertIn("I always want the serial comma", json.dumps(step["context"]))
        self.assertIn(str(SKILL / "references" / "style-profile.md"), step["read"])
        self.assertFalse(self.profile.exists())
        entry = {"heading": "Conventions", "text": "Use the serial comma.", "replaces": ""}
        code, step, _ = self.submit({"entries": [entry]})
        self.assertEqual(code, 0)
        self.assertEqual(step["step"]["id"], "revise")
        self.assertEqual(self.section("Conventions"), ["- Use the serial comma. (stated, %s)" % TODAY])
        self.assertEqual(len(step["notices"]), 1)
        self.assertIn("Use the serial comma.", step["notices"][0])
        self.assertIn(str(self.profile), step["read"])
        rev = self.base / "rev.txt"
        rev.write_text("We measured nitrate in 12 wells. Land use matters for nitrate in groundwater, so we ask how far it predicts the risk to drinking water.\n")
        self.submit({"text_file": str(rev), "exceptions": []})
        code, step, _ = self.submit({"changes": [], "questions": [], "conflicts": [], "deviations": []})
        self.assertEqual(step["step"]["kind"], "done")
        lines = step["output"].splitlines()
        i = next(n for n, l in enumerate(lines) if l.startswith("Plan:"))
        after = next(l for l in lines[i + 1:] if l.strip())
        self.assertIn("Saved to your style profile", after)
        self.assertIn("Use the serial comma.", after)

    def test_save_preference_replaces_a_same_meaning_entry(self):
        self.seed(OLD)
        self.start_section("--preference", "American spelling from now on")
        code, step, _ = self.submit({"entries": [
            {"heading": "Conventions", "text": "American spelling.", "replaces": "British spelling."}]})
        self.assertEqual(self.section("Conventions"), ["- American spelling. (stated, %s)" % TODAY])
        self.assertIn("British spelling.", step["notices"][0])

    def test_bad_save_preference_returns_same_step_and_writes_nothing(self):
        self.start_section("--preference", "x")
        for bad in ({"entries": []},
                    {"entries": [{"heading": "Hobbies", "text": "x", "replaces": ""}]},
                    {"entries": [{"heading": "Conventions", "text": "x", "replaces": "no such entry"}]},
                    {"entries": "x"}):
            code, step, _ = self.submit(bad)
            self.assertEqual(code, 5)
            self.assertEqual(step["step"]["id"], "save-preference")
            self.assertTrue(step["error"])
        self.assertFalse(self.profile.exists())


class Scan(ProfileCase):
    PROPOSALS = {"proposals": [
        {"heading": "Voice & person", "text": "Write \"we\" for own actions.", "evidence": "3 uses", "replaces": ""},
        {"heading": "Sentences", "text": "Keep sentences under 25 words.", "evidence": "seen 4 times", "replaces": ""},
        {"heading": "Conventions", "text": "American spelling.", "evidence": "color x3", "replaces": "British spelling."}]}

    def start(self):
        sample = self.proj / "sample.txt"
        sample.write_text("We show. We show. We show.\n")
        return self.run_engine("start", "--task", "scan-profile", "--input", str(sample))

    def test_sequence_and_only_approved_written(self):
        self.seed(SEED)
        code, step, _ = self.start()
        self.assertEqual(code, 0)
        self.assertRegex(step["run"], r"^\d{8}-\d{6}-scan-profile$")
        self.assertEqual((step["step"]["id"], step["step"]["kind"]), ("propose", "work"))
        self.assertTrue(step["plan"].startswith("Plan: scan-profile"))
        self.assertIn(str(SKILL / "references" / "style-profile.md"), step["read"])
        run_dir = self.proj / ".agents" / "log" / "science-research-writing" / step["run"]
        self.assertIn(str(run_dir / "input.txt"), step["read"])
        code, step, _ = self.submit(self.PROPOSALS)
        self.assertEqual((step["step"]["id"], step["step"]["kind"]), ("ask", "ask"))
        self.assertEqual(len(step["context"]["items"]), 3)
        self.assertEqual(self.profile.read_text(), SEED)  # nothing written before approval
        code, step, _ = self.submit({"approved": [1, 3]})
        self.assertEqual((step["step"]["id"], step["status"]), ("done", "done"))
        self.assertEqual(self.section("Voice & person")[-1], "- Write \"we\" for own actions. (scanned, %s)" % TODAY)
        self.assertEqual(self.section("Sentences"), [])
        self.assertEqual(self.section("Conventions"), ["- American spelling. (scanned, %s)" % TODAY])
        saved, not_saved = step["output"].split("## Not saved")
        self.assertIn("Write \"we\" for own actions.", saved)
        self.assertIn("Keep sentences under 25 words.", not_saved)

    def test_approving_nothing_writes_nothing(self):
        self.seed(SEED)
        self.start()
        self.submit(self.PROPOSALS)
        code, step, _ = self.submit({"approved": []})
        self.assertEqual(step["step"]["kind"], "done")
        self.assertEqual(self.profile.read_text(), SEED)

    def test_bad_answers_and_proposals_are_refused(self):
        self.seed(SEED)
        self.start()
        code, step, _ = self.submit({"proposals": [{"heading": "Hobbies", "text": "x", "evidence": "y", "replaces": ""}]})
        self.assertEqual((code, step["step"]["id"]), (5, "propose"))
        code, step, _ = self.submit({"proposals": [{"heading": "Sentences", "text": "x", "evidence": "", "replaces": ""}]})
        self.assertEqual((code, step["step"]["id"]), (5, "propose"))
        self.submit(self.PROPOSALS)
        code, step, _ = self.submit({"approved": [4]})
        self.assertEqual((code, step["step"]["id"]), (5, "ask"))
        self.assertEqual(self.profile.read_text(), SEED)

    def test_failing_approved_write_is_atomic(self):
        for i in range(5):
            self.padd("Exemplars", "P%d." % i)
        before = self.profile.read_text()
        self.start()
        self.submit({"proposals": [
            {"heading": "Sentences", "text": "Short.", "evidence": "3x", "replaces": ""},
            {"heading": "Exemplars", "text": "Sixth.", "evidence": "liked", "replaces": ""}]})
        code, step, _ = self.submit({"approved": [1, 2]})
        self.assertEqual((code, step["step"]["id"]), (5, "ask"))
        self.assertIn("which", step["error"].lower())
        self.assertEqual(self.profile.read_text(), before)

    def test_scan_without_existing_profile_creates_it_from_template(self):
        self.start()
        self.submit(self.PROPOSALS_NO_REPLACE)
        self.submit({"approved": [1]})
        self.assertEqual([l for l in self.lines() if l.startswith("## ")], ["## " + h for h in HEADINGS])

    PROPOSALS_NO_REPLACE = {"proposals": [
        {"heading": "Sentences", "text": "Keep sentences short.", "evidence": "4x", "replaces": ""}]}


class Study(ProfileCase):
    ENTRIES = [
        ("Always write \"we\". (stated, 2026-11-01)", []),
        ("Prefer the passive in Methods. (edited, 2026-11-10)", []),
        ("Be careful with claims.", ["unclear", "untagged"]),
        ("British spelling. (stated, 2026-11-01)", []),
    ]

    def start(self):
        return self.run_engine("start", "--task", "study-profile")

    def result(self):
        return {"entries": [{"entry": e, "restatement": "Restated: " + e, "flags": f, "question": "Clearer?" if f else ""}
                            for e, f in self.ENTRIES],
                "changes": [{"entry": "Be careful with claims.", "action": "replace", "heading": "Tone & certainty",
                             "text": "Hedge a claim when the evidence is indirect.", "reason": "no testable meaning"},
                            {"entry": "Prefer the passive in Methods. (edited, 2026-11-10)", "action": "replace",
                             "heading": "Section habits", "text": "Prefer the passive in Methods.",
                             "reason": "section-specific"},
                            {"entry": "British spelling. (stated, 2026-11-01)", "action": "remove", "heading": "",
                             "text": "", "reason": "not needed"}]}

    def test_study_without_profile_fails(self):
        code, _, err = self.start()
        self.assertEqual(code, 20)
        self.assertIn("no profile", err.lower())

    def test_sequence_nothing_written_before_approval_only_approved_applied(self):
        self.seed(SEED)
        code, step, _ = self.start()
        self.assertRegex(step["run"], r"^\d{8}-\d{6}-study-profile$")
        self.assertEqual((step["step"]["id"], step["step"]["kind"]), ("restate", "work"))
        self.assertIn(str(self.profile), step["read"])
        self.assertIn(str(SKILL / "references" / "style-profile.md"), step["read"])
        code, step, _ = self.submit(self.result())
        self.assertEqual((code, step["step"]["id"], step["step"]["kind"]), (0, "ask", "ask"))
        self.assertEqual(len(step["context"]["items"]), 3)
        self.assertEqual(self.profile.read_text(), SEED)
        code, step, _ = self.submit({"approved": [1, 3]})
        self.assertEqual(step["step"]["id"], "done")
        self.assertEqual(self.section("Tone & certainty"),
                         ["- Hedge a claim when the evidence is indirect. (edited, %s)" % TODAY])
        self.assertEqual(self.section("Conventions"), [])
        self.assertEqual(self.section("Section habits"), [])  # change 2 was not approved
        self.assertEqual(self.section("Voice & person"),
                         ["- Always write \"we\". (stated, 2026-11-01)", "- Prefer the passive in Methods. (edited, 2026-11-10)"])
        self.assertIn("Restated: Be careful with claims.", step["output"])

    def test_every_entry_must_be_restated_and_untagged_flagged(self):
        self.seed(SEED)
        self.start()
        r = self.result()
        r["entries"] = r["entries"][:-1]
        code, step, _ = self.submit(r)
        self.assertEqual((code, step["step"]["id"]), (5, "restate"))
        self.assertIn("British spelling", step["error"])
        r = self.result()
        r["entries"][2]["flags"] = ["unclear"]
        code, step, _ = self.submit(r)
        self.assertEqual((code, step["step"]["id"]), (5, "restate"))
        self.assertIn("untagged", step["error"])
        r = self.result()
        r["entries"][2]["flags"] = ["weird", "untagged"]
        self.assertEqual(self.submit(r)[0], 5)
        r = self.result()
        r["changes"][0]["entry"] = "Not in the file."
        self.assertEqual(self.submit(r)[0], 5)
        self.assertEqual(self.profile.read_text(), SEED)

    def test_approve_nothing_changes_nothing(self):
        self.seed(SEED)
        self.start()
        self.submit(self.result())
        code, step, _ = self.submit({"approved": []})
        self.assertEqual(step["step"]["kind"], "done")
        self.assertEqual(self.profile.read_text(), SEED)


if __name__ == "__main__":
    unittest.main()
