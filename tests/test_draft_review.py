"""Black-box tests for Draft and Review modes, through the engine's command line.
Run with:  python3 -m unittest discover -s tests -v
"""
import json
import re
import unittest
from pathlib import Path

import test_engine as te

ROOT = Path(__file__).resolve().parent.parent
REFS = ROOT / "references"

NOTES = (
    "- nitrate above 50 mg/L is a health risk \\cite{who2017}\r\n"
    "- we sampled 120 wells; goal: predict risk with a random forest\r\n"
    "- results: R^2 = ?? (fill in); land use matters \\cite{nolan2015,rodriguez2019}\r\n"
)
DRAFT = (
    "Nitrate above 50\\,mg/L is a health risk \\cite{who2017}. Here we predict that risk "
    "from 120 wells with a random forest and reach $R^2=$ [placeholder: R^2 value]. "
    "Land use matters \\cite{nolan2015,rodriguez2019}. "
    "[placeholder: main achievement, one sentence]\n"
)
DRAFT_REPORT = {"conflicts": [], "deviations": []}

DISC = (
    "Our model reached $R^2=0.81$ on 120 wells (Table~\\ref{tab:perf}). "
    "This agrees with earlier work \\cite{nolan2015,rodriguez2019}. "
    "Land use clearly proves that fertilizer causes the nitrate rise.\r\n"
    "We did not test other regions. Nitrate stayed below 50~mg/L at most sites \\cite{who2017}.\n"
)
S_CLAIM = "Land use clearly proves that fertilizer causes the nitrate rise."
S_CITE = "This agrees with earlier work \\cite{nolan2015,rodriguez2019}."


def finding(**kw):
    f = {"severity": "high", "where": "Paragraph 1, sentence 3", "rule": "Overstatement",
         "problem": "Proves is stronger than the data allow.", "source": S_CLAIM,
         "rewrite": "Land use was associated with the nitrate rise."}
    f.update(kw)
    return f


def names_in(path):
    """Bold lead names of top-level list items, in order."""
    return [m.group(1) for m in re.finditer(
        r"(?m)^(?:- |\d+\. )\*\*(.+?)\.\*\*", Path(path).read_text(encoding="utf-8"))]


class DraftCase(te.EngineCase):
    def setUp(self):
        super().setUp()
        self.input_path = self.proj / "notes.txt"
        self.input_path.write_bytes(NOTES.encode())

    def start_draft(self, section="abstract"):
        return self.run_engine(
            "start", "--section", section, "--mode", "draft", "--samples", "no",
            "--input", str(self.input_path))

    def draft_done(self, text=DRAFT):
        self.start_draft()
        _, step, _ = self.submit_text(text)
        self.assertEqual(step["step"]["id"], "report")
        return self.submit(DRAFT_REPORT)[1]

    def history(self, run):
        state = json.loads((self.run_dir(run) / "state.json").read_text())
        return [(h["step"], h["attempt"]) for h in state["history"]]


class DraftTests(DraftCase):
    def test_first_step_is_draft_with_section_and_language_files(self):
        code, out, _ = self.start_draft()
        self.assertEqual(code, 0)
        self.assertRegex(out["run"], r"^\d{8}-\d{6}-draft-abstract(-\d+)?$")
        self.assertIn("Plan: draft \u00b7 abstract \u00b7 markup=latex", out["plan"])
        self.assertEqual(out["step"], {"id": "draft", "kind": "work"})
        names = [Path(p).name for p in out["read"]]
        self.assertEqual(names, ["language.md", "abstract.md", "input.txt"])
        self.assertEqual(set(out["expect"]["fields"]), {"text_file", "exceptions"})
        self.assertIn("placeholder", out["instruction"])

    def test_clean_draft_sequence_and_exact_template(self):
        _, step, _ = self.start_draft()
        run = step["run"]
        _, step, _ = self.submit_text(DRAFT)
        self.assertEqual(step["step"]["id"], "report")
        self.assertEqual(set(step["expect"]["fields"]), {"conflicts", "deviations"})
        _, done, _ = self.submit(DRAFT_REPORT)
        self.assertEqual(done["step"]["kind"], "done")
        self.assertEqual(self.history(run), [("draft", 1), ("check", 1), ("report", 1)])
        plan = "Plan: draft \u00b7 abstract \u00b7 markup=latex \u00b7 samples=no \u00b7 run=" + run
        expected = "\n".join([
            plan, "",
            "## Draft", "", "```latex", DRAFT.rstrip("\n"), "```", "",
            "## Placeholders", "", "- [placeholder: R^2 value]",
            "- [placeholder: main achievement, one sentence]", "",
            "## Conflicts", "", "None", "",
            "## Deviations", "", "None", "",
            "## Check", "",
            "Check: passed. Verified by code: numbers, citations. "
            "Placeholders: 2 ([placeholder: R^2 value]; [placeholder: main achievement, one sentence]). "
            "Exceptions accepted: none. Not verified by code: "
            "citation placement relative to its claim, spelled-out quantities.",
        ]) + "\n"
        self.assertEqual(done["output"], expected)

    def test_no_placeholders_says_none(self):
        done = self.draft_done("Nitrate above 50 mg/L is a risk \\cite{who2017}.\n")
        self.assertIn("## Placeholders\n\nNone\n", done["output"])

    def test_check_fails_on_number_not_in_notes_then_fix(self):
        self.start_draft()
        _, step, _ = self.submit_text(DRAFT.replace("120 wells", "120 wells at 12 sites"))
        self.assertEqual((step["step"]["id"], step["attempt"]), ("fix", 1))
        self.assertEqual([(f["kind"], f["item"]) for f in step["context"]["failures"]],
                         [("number_added", "12")])
        self.assertEqual(set(step["expect"]["fields"]), {"text_file", "exceptions"})
        _, step, _ = self.submit_text(DRAFT)
        self.assertEqual(step["step"]["id"], "report")
        done = self.submit(DRAFT_REPORT)[1]
        self.assertEqual(self.history(done["run"]),
                         [("draft", 1), ("check", 1), ("fix", 1), ("check", 2), ("report", 1)])

    def test_check_fails_on_citation_not_in_notes(self):
        self.start_draft()
        _, step, _ = self.submit_text(DRAFT + "Rain also matters \\cite{smith2020}.\n")
        self.assertEqual([(f["kind"], f["item"]) for f in step["context"]["failures"]],
                         [("citation_added", "smith2020")])

    def test_regrouped_citation_fails(self):
        self.start_draft()
        _, step, _ = self.submit_text(
            DRAFT.replace("\\cite{nolan2015,rodriguez2019}", "\\cite{nolan2015}"))
        self.assertEqual([f["kind"] for f in step["context"]["failures"]], ["citation_added"])

    def test_draft_may_leave_notes_numbers_and_citations_out(self):
        done = self.draft_done("We sampled wells and used a model [placeholder: how many wells].\n")
        self.assertNotIn("FAILED", done["output"])

    def test_declared_exception_passes_in_draft(self):
        self.start_draft()
        ex = [{"item": "13", "quote": "add that we also visited 13 farms"}]
        _, step, _ = self.submit_text(DRAFT + "We also visited 13 farms.\n", ex)
        self.assertEqual(step["step"]["id"], "report")
        done = self.submit(DRAFT_REPORT)[1]
        self.assertIn('Exceptions accepted: 1 (13: "add that we also visited 13 farms")',
                      done["output"])

    def test_failure_notice_after_two_failed_fixes(self):
        bad = DRAFT.replace("120", "130")
        self.start_draft()
        for attempt in (1, 2):
            _, step, _ = self.submit_text(bad)
            self.assertEqual((step["step"]["id"], step["attempt"]), ("fix", attempt))
        _, step, _ = self.submit_text(bad)
        self.assertEqual(step["step"]["id"], "report")
        done = self.submit(DRAFT_REPORT)[1]
        self.assertIn("Integrity check failed", done["output"].splitlines()[0])
        self.assertIn("Check: FAILED (1 failure(s))", done["output"])


class RuleNameTests(unittest.TestCase):
    SECTIONS = ["title", "abstract", "introduction", "methods", "results", "discussion", "conclusion"]

    def rules_in(self, path):
        """(line, has_name) for every top-level list item that is a rule: not in
        the phrase banks and not in the checklist's how-to-use section."""
        skip = False
        out = []
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.startswith("#"):
                skip = "Phrases by move" in line or "How to use it" in line
            elif not skip and re.match(r"(?:- |\d+\. )", line):
                out.append((line, bool(re.match(r"(?:- |\d+\. )\*\*[^*]+\.\*\*", line))))
        return out

    def test_every_rule_has_a_plain_name_unique_within_its_file(self):
        for f in self.SECTIONS + ["language", "checklist"]:
            with self.subTest(file=f):
                path = REFS / (f + ".md")
                unnamed = [l[:60] for l, ok in self.rules_in(path) if not ok]
                self.assertEqual(unnamed, [])
                names = names_in(path)
                self.assertTrue(names)
                self.assertEqual(len(names), len(set(names)),
                                 [n for n in names if names.count(n) > 1])
                self.assertTrue(all(len(n.split()) <= 10 and not re.search(r"[`\"]", n)
                                    for n in names), names)

    def test_checklist_is_an_ordered_list_of_names(self):
        names = names_in(REFS / "checklist.md")
        self.assertEqual(names[0], "Plan from the destination")
        self.assertEqual(names[-1], "Check against the target journal")
        self.assertLess(names.index("Make the value explicit"), names.index("Flag key points"))
        self.assertLess(names.index("Flag key points"), names.index("Cut lexical tics"))


class ReviewCase(te.EngineCase):
    def setUp(self):
        super().setUp()
        self.input_path = self.proj / "disc.tex"
        self.input_path.write_bytes(DISC.encode())

    def start_review(self, section="discussion"):
        return self.run_engine(
            "start", "--section", section, "--mode", "review", "--samples", "no",
            "--input", str(self.input_path))

    def submit_findings(self, findings, exceptions=None):
        return self.submit({"findings": findings, "exceptions": exceptions or []})

    def history(self, run):
        state = json.loads((self.run_dir(run) / "state.json").read_text())
        return [(h["step"], h["attempt"]) for h in state["history"]]


class ReviewStepTests(ReviewCase):
    def test_review_step_reads_checklist_and_walks_it_in_order(self):
        code, out, _ = self.start_review()
        self.assertEqual(code, 0)
        self.assertRegex(out["run"], r"^\d{8}-\d{6}-review-discussion(-\d+)?$")
        self.assertEqual(out["step"], {"id": "review", "kind": "work"})
        self.assertEqual([Path(p).name for p in out["read"]],
                         ["language.md", "discussion.md", "checklist.md", "input.txt"])
        self.assertEqual(set(out["expect"]["fields"]), {"findings", "exceptions"})
        self.assertIn("in order", out["instruction"])
        self.assertEqual(out["context"]["checklist"], names_in(REFS / "checklist.md"))

    def test_review_sequence_and_exact_template(self):
        _, step, _ = self.start_review()
        run = step["run"]
        findings = [
            finding(severity="low", rule="Cut lexical tics", where="Paragraph 1",
                    problem="Clearly adds noise.", source=S_CLAIM,
                    rewrite="Land use proves that fertilizer causes the nitrate rise."),
            finding(severity="high"),
            finding(severity="medium", rule="Map to existing knowledge", where="Sentence 2",
                    problem="Agreement is not qualified | no scope.", source=S_CITE,
                    rewrite="This agrees with earlier work \\cite{nolan2015,rodriguez2019} in sandy soils."),
        ]
        code, step, _ = self.submit_findings(findings)
        self.assertEqual((code, step["step"]["id"]), (0, "report"))
        self.assertEqual(set(step["expect"]["fields"]), {"conflicts", "deviations"})
        _, done, _ = self.submit(DRAFT_REPORT)
        self.assertEqual(self.history(run), [("review", 1), ("check", 1), ("report", 1)])
        plan = ("Plan: review \u00b7 discussion \u00b7 markup=latex \u00b7 samples=no \u00b7 run=" + run)
        expected = "\n".join([
            plan, "",
            "## Findings", "",
            "| # | Severity | Where | Rule | Problem | Suggested rewrite |",
            "|---|---|---|---|---|---|",
            "| 1 | high | Paragraph 1, sentence 3 | Overstatement | Proves is stronger than the "
            "data allow. | Land use was associated with the nitrate rise. |",
            "| 2 | medium | Sentence 2 | Map to existing knowledge | Agreement is not qualified "
            "\\| no scope. | This agrees with earlier work \\cite{nolan2015,rodriguez2019} in sandy soils. |",
            "| 3 | low | Paragraph 1 | Cut lexical tics | Clearly adds noise. | Land use proves that "
            "fertilizer causes the nitrate rise. |", "",
            "## Conflicts", "", "None", "",
            "## Deviations", "", "None", "",
            "## Check", "",
            "Check: passed. Verified by code: quoted sentences, and numbers and citations in each "
            "suggested rewrite. Placeholders: none. Exceptions accepted: none. Not verified by code: "
            "citation placement relative to its claim, spelled-out quantities.",
        ]) + "\n"
        self.assertEqual(done["output"], expected)
        self.assertNotIn("```", done["output"])  # the author's text is not rewritten as a whole

    def test_no_findings_renders_none(self):
        self.start_review()
        self.submit_findings([])
        _, done, _ = self.submit(DRAFT_REPORT)
        self.assertIn("## Findings\n\nNone\n", done["output"])

    def test_source_matches_across_line_wraps_and_crlf(self):
        self.start_review()
        src = "Our model reached $R^2=0.81$ on 120 wells (Table~\\ref{tab:perf}). This agrees"
        _, step, _ = self.submit_findings([finding(
            severity="low", rule="Link sentences", source=src, rewrite="Our model reached $R^2=0.81$ "
            "on 120 wells (Table~\\ref{tab:perf}). It agrees")])
        self.assertEqual(step["step"]["id"], "report")

    def test_other_section_reads_language_principles_and_checklist(self):
        _, out, _ = self.start_review("other")
        self.assertEqual([Path(p).name for p in out["read"]],
                         ["language.md", "SKILL.md", "checklist.md", "input.txt"])


class ReviewRejectionTests(ReviewCase):
    def rejected(self, findings):
        self.start_review()
        code, out, err = self.submit_findings(findings)
        self.assertEqual((code, out["step"]["id"], out["attempt"]), (5, "review", 1))
        self.assertTrue(out["error"])
        self.assertIn(out["error"], err)
        return out["error"]

    def test_unknown_rule_name(self):
        msg = self.rejected([finding(rule="Rule 7.3")])
        self.assertIn("Rule 7.3", msg)
        self.assertIn("finding 1", msg)

    def test_rules_from_checklist_language_and_section_moves_are_known(self):
        self.start_review()
        rules = ["Plan from the destination", "Agentless passives",
                 "State the achievement and contribution", "Overstatement"]
        _, step, _ = self.submit_findings([finding(rule=r) for r in rules])
        self.assertEqual(step["step"]["id"], "report")

    def test_move_of_another_section_is_unknown(self):
        self.assertIn("Locate the gap and motivate the study",
                      self.rejected([finding(rule="Locate the gap and motivate the study")]))

    def test_bad_severity(self):
        for bad in ("critical", "High", ""):
            with self.subTest(bad=bad):
                self.assertIn("severity", self.rejected([finding(), finding(severity=bad)]))

    def test_source_not_in_input(self):
        msg = self.rejected([finding(source="Land use proves that fertilizer causes nitrate.")])
        self.assertIn("finding 1", msg)
        self.assertIn("input", msg)

    def test_shape_errors(self):
        bad = finding()
        del bad["rewrite"]
        self.rejected([bad])
        self.rejected([dict(finding(), extra="x")])
        self.rejected([dict(finding(), problem=" ")])
        self.rejected("not a list")

    def test_resubmission_after_rejection_succeeds(self):
        self.rejected([finding(rule="Nope")])
        _, step, _ = self.submit_findings([finding()])
        self.assertEqual(step["step"]["id"], "report")


class ReviewCheckTests(ReviewCase):
    def failures(self, **kw):
        self.start_review()
        _, step, _ = self.submit_findings([finding(**kw)])
        self.assertEqual((step["step"]["id"], step["attempt"]), ("fix", 1))
        self.assertEqual(set(step["expect"]["fields"]), {"findings", "exceptions"})
        return sorted((f["kind"], f["item"]) for f in step["context"]["failures"])

    def test_rewrite_adding_a_number_fails(self):
        self.assertEqual(self.failures(rewrite="Land use explained 40% of the nitrate rise."),
                         [("number_added", "40")])

    def test_rewrite_adding_a_citation_fails(self):
        self.assertEqual(self.failures(rewrite="Land use was linked to the rise \\cite{smith2020}."),
                         [("citation_added", "smith2020")])

    def test_rewrite_dropping_a_citation_fails(self):
        self.assertEqual(
            self.failures(rule="Map to existing knowledge", source=S_CITE,
                          rewrite="This agrees with earlier work."),
            [("citation_removed", "nolan2015,rodriguez2019")])

    def test_rewrite_regrouping_a_citation_fails(self):
        self.assertEqual(
            self.failures(rule="Map to existing knowledge", source=S_CITE,
                          rewrite="This agrees with \\cite{nolan2015} and \\cite{rodriguez2019}."),
            [("citation_added", "nolan2015"), ("citation_added", "rodriguez2019"),
             ("citation_removed", "nolan2015,rodriguez2019")])

    def test_placeholder_in_rewrite_is_allowed_and_listed(self):
        self.start_review()
        _, step, _ = self.submit_findings([finding(
            rewrite="Land use was associated with the rise [placeholder: citation].")])
        self.assertEqual(step["step"]["id"], "report")
        _, done, _ = self.submit(DRAFT_REPORT)
        self.assertIn("Placeholders: 1 ([placeholder: citation])", done["output"])

    def test_numbers_in_the_source_may_be_kept(self):
        self.start_review()
        src = "Nitrate stayed below 50~mg/L at most sites \\cite{who2017}."
        _, step, _ = self.submit_findings([finding(
            severity="low", rule="Evaluate numbers in words", source=src,
            rewrite="Nitrate stayed below 50 mg/L at most sites \\cite{who2017}, as required.")])
        self.assertEqual(step["step"]["id"], "report")

    def test_fix_resubmits_findings_then_report(self):
        run = self.start_review()[1]["run"]
        self.submit_findings([finding(rewrite="Land use explained 40% of the rise.")])
        code, step, _ = self.submit_findings([finding()])
        self.assertEqual((code, step["step"]["id"]), (0, "report"))
        done = self.submit(DRAFT_REPORT)[1]
        self.assertEqual(self.history(run),
                         [("review", 1), ("check", 1), ("fix", 1), ("check", 2), ("report", 1)])
        self.assertNotIn("FAILED", done["output"])

    def test_fix_step_validates_findings_too(self):
        self.start_review()
        self.submit_findings([finding(rewrite="Land use explained 40% of the rise.")])
        code, step, _ = self.submit_findings([finding(rule="Nope")])
        self.assertEqual((code, step["step"]["id"], step["attempt"]), (5, "fix", 1))

    def test_failure_notice_after_two_failed_fixes(self):
        bad = finding(rewrite="Land use explained 40% of the rise.")
        self.start_review()
        for attempt in (1, 2):
            _, step, _ = self.submit_findings([bad])
            self.assertEqual((step["step"]["id"], step["attempt"]), ("fix", attempt))
        _, step, _ = self.submit_findings([bad])
        self.assertEqual(step["step"]["id"], "report")
        done = self.submit(DRAFT_REPORT)[1]
        self.assertIn("Integrity check failed", done["output"].splitlines()[0])
        self.assertIn("number 40", done["output"].splitlines()[0])
        self.assertIn("Check: FAILED (1 failure(s))", done["output"])

    def test_declared_exception_passes_in_review(self):
        self.start_review()
        ex = [{"item": "40", "quote": "suggest quoting the 40% from the abstract"}]
        _, step, _ = self.submit_findings([finding(rewrite="Land use explained 40% of the rise.")], ex)
        self.assertEqual(step["step"]["id"], "report")
        done = self.submit(DRAFT_REPORT)[1]
        self.assertIn("Exceptions accepted: 1", done["output"])
        self.assertIn("Accepted exception, 40", done["output"])


if __name__ == "__main__":
    unittest.main()
