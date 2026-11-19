"""Black-box tests for the integrity checker's finer points, through the engine's command line."""
import test_draft_review as tdr
import test_engine as te

PAD = ("This sentence pads the paragraph so that the classifier reads running prose. "
       "A second sentence does the same job here. ")


class CheckCase(te.EngineCase):
    def failures(self, inp, out, exceptions=None):
        """Run a revise on PAD + inp, submit PAD + out; the (kind, item) failures of the first check."""
        self.run_engine("abandon")  # one open run per project; a subTest loop starts several
        self.input_path.write_text(PAD + inp + "\n")
        code, _, err = self.start()
        self.assertEqual(code, 0, err)
        _, step, _ = self.submit_text(PAD + out + "\n", exceptions)
        if step["step"]["id"] == "fix":
            return sorted((f["kind"], f["item"]) for f in step["context"]["failures"])
        self.assertEqual(step["step"]["id"], "report")
        return []


class MarkupTests(CheckCase):
    def test_the_code_decides_markup_and_start_has_no_markup_option(self):
        code, out, err = self.run_engine(*te.START, "--markup", "plain", "--input", str(self.input_path))
        self.assertEqual((code, out), (2, None))
        self.assertIn("--markup", err)

    def test_a_dropped_citep_is_caught_on_latex_input(self):
        self.assertEqual(self.failures("It holds \\citep{smith}.", "It holds."),
                         [("citation_removed", "smith")])


class CitationCommandTests(CheckCase):
    def test_cite_family_matches_in_any_case(self):
        for cmd in ("\\Citep", "\\Cite", "\\Citet", "\\Parencite", "\\citep", "\\textcite"):
            with self.subTest(cmd=cmd):
                self.assertEqual(self.failures("It holds %s{smith}." % cmd, "It holds."),
                                 [("citation_removed", "smith")])

    def test_cites_checks_every_key_group(self):
        inp = "It holds \\cites{a}{b}."
        self.assertEqual(self.failures(inp, inp), [])
        self.assertEqual(self.failures(inp, "It holds \\cites{a}."), [("citation_removed", "b")])
        self.assertEqual(self.failures(inp, "It holds \\cites{b}."), [("citation_removed", "a")])


class NumberTests(CheckCase):
    def test_thin_and_nonbreaking_spaces_between_digit_groups_are_one_number(self):
        for a, b in (("10\\,000", "10~000"), ("10~000", "10000"), ("10\\;000", "10\\,000"),
                     ("10\\nobreakspace{}000", "10000"), ("1\\,000\\,000", "1~000~000"),
                     ("10 000", "10\\,000")):
            with self.subTest(a=a, b=b):
                self.assertEqual(self.failures("We saw %s wells." % a, "We saw %s wells." % b), [])

    def test_revise_counts_each_removed_occurrence(self):
        self.assertEqual(self.failures("It used 5 and 5 mm.", "It used 5 mm."), [("number_removed", "5")])
        self.assertEqual(self.failures("It used 5 and 5 mm.", "It used 5 and 5 mm."), [])

    def test_revise_still_lets_a_repeated_number_be_added_once_known(self):
        self.assertEqual(self.failures("It used 5 mm.", "It used 5 mm, so 5 mm."), [])


class NumberedCitationTests(CheckCase):
    def test_order_and_dash_kind_do_not_matter(self):
        for a, b in (("[2,1]", "[1,2]"), ("[1–3]", "[1-3]"), ("[3, 1, 2]", "[1,2,3]"),
                     ("[4,1–3]", "[1-3,4]")):
            with self.subTest(a=a, b=b):
                self.assertEqual(self.failures("It holds %s." % a, "It holds %s." % b), [])

    def test_merged_or_split_groups_still_fail(self):
        merged = self.failures("It holds [1] and [2].", "It holds [1,2].")
        self.assertIn(("citation_added", "1,2"), merged)
        split = self.failures("It holds [1,2].", "It holds [1] and [2].")
        self.assertIn(("citation_removed", "1,2"), split)


class ReviewReferenceTests(tdr.ReviewCase):
    SRC = "Our model reached $R^2=0.81$ on 120 wells (Table~\\ref{tab:perf})."

    def test_a_rewrite_that_drops_a_ref_fails_the_check(self):
        self.start_review()
        _, step, _ = self.submit_findings([tdr.finding(
            severity="low", rule="Link sentences", source=self.SRC,
            rewrite="Our model reached $R^2=0.81$ on 120 wells.")])
        self.assertEqual(step["step"]["id"], "fix")
        self.assertEqual([(f["kind"], f["item"]) for f in step["context"]["failures"]],
                         [("reference_removed", "\\ref{tab:perf}")])
        self.assertIn("finding 1", step["context"]["failures"][0]["message"])

    def test_a_rewrite_that_keeps_the_ref_passes(self):
        self.start_review()
        _, step, _ = self.submit_findings([tdr.finding(
            severity="low", rule="Link sentences", source=self.SRC,
            rewrite="The model reached $R^2=0.81$ on 120 wells (Table~\\ref{tab:perf}).")])
        self.assertEqual(step["step"]["id"], "report")

    def test_a_cut_names_where_the_citation_goes(self):
        _, out, _ = self.start_review()
        self.assertRegex(out["instruction"], r"cut.*citation or label.*where it goes")
        self.assertIn("\\cite{key}", out["instruction"])
        _, step, _ = self.submit_findings([tdr.finding(
            severity="low", rule="Cut lexical tics", source=tdr.S_CITE,
            rewrite="(delete; move \\cite{nolan2015,rodriguez2019} to the previous sentence)")])
        self.assertEqual(step["step"]["id"], "report")


class UnusedExceptionTests(CheckCase):
    def test_a_declared_but_unneeded_exception_is_listed_in_deviations(self):
        ex = [{"item": "\\cite{who2017}", "quote": "please delete the WHO citation"}]
        done = self.finish(te.GOOD, ex)
        self.assertEqual(done["step"]["kind"], "done")
        self.assertIn('Declared exception not needed, \\cite{who2017} (author asked: "please delete the WHO citation")',
                      done["output"].split("## Deviations")[1].split("## Check")[0])


class ConflictQuestionTests(CheckCase):
    NO_QUESTION = "The journal wants we, the profile wants I."
    ASKED = "The journal wants we, the profile wants I; which should win?"

    def test_revise_report_rejects_a_conflict_without_a_question(self):
        self.start()
        self.submit_text(te.GOOD)
        rest = {"changes": [], "questions": [], "deviations": []}
        code, out, _ = self.submit({**rest, "conflicts": [self.NO_QUESTION]})
        self.assertEqual((code, out["step"]["id"]), (5, "report"))
        self.assertIn("question", out["error"])
        code, out, _ = self.submit({**rest, "conflicts": [self.ASKED]})
        self.assertEqual((code, out["step"]["kind"]), (0, "done"))

    def test_questions_may_stay_empty(self):
        self.start()
        self.submit_text(te.GOOD)
        code, out, _ = self.submit({"changes": [], "questions": [], "conflicts": [], "deviations": []})
        self.assertEqual((code, out["step"]["kind"]), (0, "done"))


class DraftConflictTests(tdr.DraftCase):
    def test_draft_report_rejects_a_conflict_without_a_question(self):
        self.start_draft()
        self.submit_text(tdr.DRAFT)
        code, out, _ = self.submit({"conflicts": ["no question here"], "deviations": []})
        self.assertEqual((code, out["step"]["id"]), (5, "report"))
        code, out, _ = self.submit({"conflicts": ["which one wins?"], "deviations": []})
        self.assertEqual((code, out["step"]["kind"]), (0, "done"))


class ReviewConflictTests(tdr.ReviewCase):
    def test_review_report_rejects_a_conflict_without_a_question(self):
        self.start_review()
        self.submit_findings([])
        code, out, _ = self.submit({"conflicts": ["no question here"], "deviations": []})
        self.assertEqual((code, out["step"]["id"]), (5, "report"))
        code, out, _ = self.submit({"conflicts": ["which one wins?"], "deviations": []})
        self.assertEqual((code, out["step"]["kind"]), (0, "done"))
