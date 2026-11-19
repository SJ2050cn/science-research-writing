"""Black-box tests for request classification, journal samples and whole papers,
through the engine's command line.
Run with:  python3 -m unittest discover -s tests -v
"""
import json
import re
import unittest

import test_engine as te

MD = (
    "# Nitrate prediction\n\n"
    "## Introduction\n\n"
    "Nitrate above 50 mg/L is a health risk [@who2017]. We sampled 120 wells to learn how land use "
    "relates to nitrate in the groundwater of the region.\n\n"
    "## Methods\n\n"
    "We used a random forest [@breiman2001]. It ran on 120 wells and used the land use around each "
    "well as its predictors.\n"
)
PLAIN = (
    "Nitrate above 50 mg/L is a health risk. We sampled 120 wells. Land use matters.\n"
    "We used a random forest on 120 wells. It reached an R2 of 0.81.\n"
    "This agrees with earlier work. We did not test other regions.\n"
)
PAPER = (
    "\\title{Nitrate}\n"
    "\\begin{abstract}\nWe sampled 120 wells. The forest reached $R^2=0.81$ on them.\n\\end{abstract}\n"
    "\\section{Introduction}\nNitrate above 50~mg/L is a risk \\cite{who2017}. Land use matters.\n"
    "\\section{Methods}\nWe used 120 wells. A forest was trained on them.\n"
    "\\section{Related work}\nOthers used trees \\cite{breiman2001}. They found little.\n"
    "\\end{document}\n"
)
REPORT = {"changes": [], "questions": [], "conflicts": [], "deviations": []}


class Case(te.EngineCase):
    def begin(self, text, *args, name="in.txt"):
        self.input_path = self.write(name, text)
        return self.run_engine("start", "--input", str(self.input_path), *args)

    def read(self, path):
        with open(path, encoding="utf-8") as f:
            return f.read()

    def plan_of(self, out):
        return re.sub(r"run=\S+", "run=X", out["plan"])

    def answer(self, value):
        return self.submit({"answer": value})

    def revise_until_report(self, step):
        """Submit the unchanged part text as the revision; returns the report step."""
        text = self.read(step["read"][-1])
        _, step, _ = self.submit_text(text)
        return step


class ClassifyTests(Case):
    def test_markup_is_detected_by_code_the_same_way_every_time(self):
        texts = (("Nitrate is a risk \\cite{who2017}. We used 120 wells. Land use matters.\n", "latex"),
                 ("Nitrate is a risk [@who2017]. We used **120** wells. Land use matters.\n", "markdown"),
                 (PLAIN, "plain"))
        for text, markup in texts:
            plans = set()
            for _ in range(2):
                _, out, _ = self.begin(text, "--section", "other")
                plans.add(self.plan_of(out))
                self.tearDownRuns()
            self.assertEqual(len(plans), 1)
            self.assertIn("markup=" + markup, plans.pop())

    def tearDownRuns(self):
        import shutil
        shutil.rmtree(self.proj / ".agents", ignore_errors=True)

    def test_mode_comes_from_the_shape_of_the_input(self):
        _, out, _ = self.begin(te.INTRO)
        self.assertIn("Plan: revise · introduction", out["plan"])
        self.tearDownRuns()
        notes = "- nitrate is a risk \\cite{who2017}\n- we sampled 120 wells\n- goal: predict risk\n"
        _, out, _ = self.begin(notes, "--section", "abstract")
        self.assertIn("Plan: draft · abstract", out["plan"])
        self.assertEqual(out["step"]["id"], "draft")

    def test_assessment_request_makes_a_review(self):
        _, out, _ = self.begin(te.INTRO, "--mode", "review")
        self.assertIn("Plan: review · introduction", out["plan"])
        self.assertEqual(out["step"]["id"], "review")

    def test_a_heading_settles_the_section(self):
        _, out, _ = self.begin(te.INTRO)
        self.assertIn("introduction", out["plan"])
        self.tearDownRuns()
        _, out, _ = self.begin("## Results\n\n" + PLAIN)
        self.assertIn("Plan: revise · results · markup=markdown", out["plan"])

    def test_agreeing_model_and_code_do_not_ask(self):
        _, out, _ = self.begin(te.INTRO, "--section", "introduction", "--mode", "revise")
        self.assertEqual(out["step"]["kind"], "work")


class TitleTests(Case):
    TITLE = "Predicting nitrate risk in groundwater with random forests\n"

    def tearDownRuns(self):  # one open run per project: a subTest loop starts several
        self.run_engine("abandon")

    def test_one_short_line_of_title_text_is_revised(self):
        for args in (("--section", "title"), ("--section", "title", "--mode", "revise")):
            with self.subTest(args=args):
                self.tearDownRuns()
                _, out, _ = self.begin(self.TITLE, *args)
                self.assertEqual(out["step"], {"id": "revise", "kind": "work"})
                self.assertIn("Plan: revise · title", out["plan"])

    def test_a_latex_title_command_is_revised(self):
        _, out, _ = self.begin("\\title{Predicting nitrate risk with random forests}\n")
        self.assertIn("Plan: revise · title", out["plan"])

    def test_notes_or_a_paragraph_are_drafted_into_a_title(self):
        notes = "- nitrate risk in groundwater\n- random forest on 120 wells\n"
        paragraph = ("Nitrate above 50 mg/L is a health risk. We sampled 120 wells to learn how land use "
                     "relates to nitrate in the groundwater of the region.\n")
        for text in (notes, paragraph, self.TITLE + "\nrandom forest, 120 wells\n"):
            with self.subTest(text=text):
                self.tearDownRuns()
                _, out, _ = self.begin(text, "--section", "title")
                self.assertIn("Plan: draft · title", out["plan"])

    def test_the_rule_is_for_titles_only(self):
        _, out, _ = self.begin(self.TITLE, "--section", "abstract")
        self.assertIn("Plan: draft · abstract", out["plan"])


class DisagreementTests(Case):
    def test_section_disagreement_asks_one_fixed_question(self):
        code, out, _ = self.begin(te.INTRO, "--section", "methods")
        self.assertEqual(code, 0)
        self.assertEqual(out["step"], {"id": "clarify", "kind": "ask"})
        self.assertEqual(out["context"]["options"], ["introduction", "methods"])
        self.assertIn("introduction", out["context"]["question"])
        self.assertIn("methods", out["context"]["question"])
        self.assertEqual(set(out["expect"]["fields"]), {"answer"})
        self.assertNotIn("Plan: revise", out["plan"])

    def test_mode_disagreement_asks(self):
        _, out, _ = self.begin(te.INTRO, "--mode", "draft")
        self.assertEqual(out["step"]["kind"], "ask")
        self.assertEqual(out["context"]["options"], ["revise", "draft"])

    def test_no_heading_and_no_section_asks(self):
        _, out, _ = self.begin(PLAIN)
        self.assertEqual(out["step"]["kind"], "ask")
        self.assertIn("methods", out["context"]["options"])

    def test_the_answer_resolves_the_field_and_the_run_goes_on(self):
        _, out, _ = self.begin(te.INTRO, "--section", "methods")
        old = out["run"]
        code, step, _ = self.answer("methods")
        self.assertEqual(code, 0)
        self.assertEqual(step["step"], {"id": "revise", "kind": "work"})
        self.assertIn("Plan: revise · methods · markup=latex · samples=no · run=", step["plan"])
        self.assertTrue(step["run"].endswith("-revise-methods"))
        self.assertFalse(self.run_dir(old).exists())
        self.assertTrue((self.run_dir(step["run"]) / "input.txt").is_file())

    def test_two_disagreements_are_asked_one_after_the_other(self):
        _, out, _ = self.begin(te.INTRO, "--section", "methods", "--mode", "draft")
        self.assertEqual(out["context"]["field"], "section")
        _, out, _ = self.answer("introduction")
        self.assertEqual((out["step"]["kind"], out["context"]["field"]), ("ask", "mode"))
        _, out, _ = self.answer("draft")
        self.assertEqual(out["step"]["id"], "draft")

    def test_an_answer_outside_the_options_returns_the_same_step(self):
        self.begin(te.INTRO, "--section", "methods")
        code, out, err = self.answer("results")
        self.assertEqual(code, 5)
        self.assertEqual(out["step"]["id"], "clarify")
        self.assertIn("introduction", out["error"])

    def test_nothing_else_is_written_before_the_answer(self):
        _, out, _ = self.begin(te.INTRO, "--section", "methods")
        files = sorted(p.name for p in self.run_dir(out["run"]).iterdir())
        self.assertEqual(files, ["input.txt", "results", "state.json"])

    def test_a_stated_preference_is_saved_before_the_question_is_asked(self):
        _, out, _ = self.begin(te.INTRO, "--section", "methods", "--preference", "I always use we")
        self.assertEqual(out["step"]["id"], "save-preference")
        entry = {"heading": "Voice & person", "text": "Use we.", "replaces": ""}
        _, out, _ = self.submit({"entries": [entry]})
        self.assertEqual(out["step"]["id"], "clarify")
        _, out, _ = self.answer("introduction")
        self.assertEqual(out["step"]["id"], "revise")


class OtherRouteTests(Case):
    def test_other_reads_principles_and_runs_the_check(self):
        text = ("Figure 2. Map of the 120 wells in the study area. Dots mark the wells that exceeded "
                "the guideline value in the survey, and the shaded area shows the catchment.\n")
        _, out, _ = self.begin(text, "--section", "other", "--mode", "revise")
        self.assertIn("Plan: revise · other ·", out["plan"])
        self.assertEqual([p.rsplit("/", 1)[1] for p in out["read"]],
                         ["language.md", "SKILL.md", "input.txt"])
        _, step, _ = self.submit_text(text.replace("120", "130"))
        self.assertEqual(step["step"]["id"], "fix")
        _, step, _ = self.submit_text(text)
        self.assertEqual(step["step"]["id"], "report")


class SamplesTests(Case):
    def sample(self, name="paper1.txt"):
        return str(self.write(name, "Sample paper text.\n"))

    def test_samples_yes_without_files_is_rejected(self):
        code, out, err = self.begin(te.INTRO, "--samples", "yes")
        self.assertEqual((code, out), (3, None))
        self.assertIn("sample", err)

    def test_journal_model_runs_before_the_main_step_and_the_main_step_reads_it(self):
        s1, s2 = self.sample(), self.sample("paper2.txt")
        _, out, _ = self.begin(te.INTRO, "--samples", "yes",
                               "--sample-file", s1, "--sample-file", s2)
        self.assertEqual(out["step"], {"id": "journal-model", "kind": "work"})
        self.assertIn("samples=yes", out["plan"])
        names = [p.rsplit("/", 1)[1] for p in out["read"]]
        self.assertEqual(names, ["reverse-engineering.md", "paper1.txt", "paper2.txt"])
        model = self.write("model.md", "Move 1: state the risk.\n")
        _, step, _ = self.submit({"text_file": str(model)})
        self.assertEqual(step["step"]["id"], "revise")
        names = [p.rsplit("/", 1)[1] for p in step["read"]]
        self.assertTrue(step["read"][-1].endswith("journal-model.txt"))
        self.assertEqual(self.read(step["read"][-1]), "Move 1: state the risk.\n")

    def test_journal_model_result_is_validated(self):
        self.begin(te.INTRO, "--samples", "yes", "--sample-file", self.sample())
        code, out, _ = self.submit({"text_file": "/no/such/file"})
        self.assertEqual((code, out["step"]["id"]), (5, "journal-model"))

    def test_samples_flow_ends_in_the_same_output(self):
        self.begin(te.INTRO, "--samples", "yes", "--sample-file", self.sample())
        self.submit({"text_file": str(self.write("model.md", "m\n"))})
        _, step, _ = self.submit_text(te.GOOD)
        _, done, _ = self.submit(REPORT)
        self.assertEqual(done["step"]["kind"], "done")
        self.assertIn("samples=yes", done["output"])


class WholePaperTests(Case):
    def part_plans(self, output):
        return re.findall(r"(?m)^Plan: .*$", output)

    def run_all(self, text, *args, name="paper.tex"):
        _, step, _ = self.begin(text, *args, name=name)
        seen = []
        while step["step"]["kind"] != "done":
            self.assertLess(len(seen), 10)
            seen.append(step["plan"])
            step = self.revise_until_report(step)
            self.assertEqual(step["step"]["id"], "report")
            _, step, _ = self.submit(REPORT)
        return seen, step

    def test_latex_is_split_at_headings_and_run_in_manuscript_order(self):
        seen, done = self.run_all(PAPER)
        order = [re.search(r"revise · (\S+) ·", p).group(1) for p in seen]
        self.assertEqual(order, ["title", "abstract", "introduction", "methods", "other"])
        out = done["output"]
        self.assertEqual(len(self.part_plans(out)), 5)
        self.assertEqual(out.count("## Check"), 5)
        self.assertEqual(out.count("## Revised text"), 5)

    def test_one_run_and_the_parts_cover_the_input_exactly(self):
        _, step, _ = self.begin(PAPER, name="paper.tex")
        self.assertEqual(step["step"]["id"], "revise")
        self.assertIn("revise · title ·", step["plan"])
        runs = list((self.proj / ".agents/log/science-research-writing").iterdir())
        self.assertEqual(len(runs), 1)
        parts = sorted((runs[0] / "parts").glob("*/input.txt"))
        self.assertEqual("".join(p.read_text() for p in parts), PAPER)
        self.assertEqual([p.parent.name for p in parts],
                         ["01-title", "02-abstract", "03-introduction", "04-methods", "05-other"])
        state = json.loads((runs[0] / "state.json").read_text())
        self.assertEqual(state["status"], "open")

    def test_status_open_until_the_last_section_is_done(self):
        _, step, _ = self.begin(PAPER, name="paper.tex")
        run = step["run"]
        for _ in range(4):
            step = self.revise_until_report(step)
            _, step, _ = self.submit(REPORT)
        self.assertEqual(step["status"], "open")
        self.assertIn("other", step["plan"])
        _, st, _ = self.run_engine("status")
        self.assertEqual(st["run"], run)
        self.assertEqual(st["part"], {"index": 5, "of": 5, "section": "other"})

    def test_the_check_runs_for_each_section(self):
        _, step, _ = self.begin(PAPER, name="paper.tex")
        _, step, _ = self.submit_text("\\title{Nitrate 9}\n")
        self.assertEqual(step["step"]["id"], "fix")
        self.assertIn("title", step["plan"])

    def test_markdown_is_split_at_headings_of_the_section_level(self):
        seen, done = self.run_all(MD, name="paper.md")
        order = [re.search(r"revise · (\S+) ·", p).group(1) for p in seen]
        self.assertEqual(order, ["introduction", "methods"])
        self.assertIn("markup=markdown", seen[0])
        self.assertEqual(len(self.part_plans(done["output"])), 2)

    def test_a_single_heading_is_not_a_whole_paper(self):
        _, step, _ = self.begin(te.INTRO)
        self.assertNotIn("whole-paper", step["plan"])

    def test_model_whole_paper_against_a_single_heading_asks(self):
        _, out, _ = self.begin(te.INTRO, "--section", "whole-paper")
        self.assertEqual(out["context"]["options"], ["introduction", "whole-paper"])

    def test_answering_whole_paper_splits_the_input_in_the_renamed_run(self):
        _, out, _ = self.begin(PAPER, "--section", "methods", name="paper.tex")
        old = out["run"]
        _, step, _ = self.answer("whole-paper")
        self.assertTrue(step["run"].endswith("-revise-whole-paper"), step["run"])
        self.assertEqual(step["part"], {"index": 1, "of": 5, "section": "title"})
        self.assertFalse(self.run_dir(old).exists())
        parts = sorted((self.run_dir(step["run"]) / "parts").glob("*/input.txt"))
        self.assertEqual("".join(p.read_text() for p in parts), PAPER)

    def test_the_run_flags_and_notices_show_in_every_section(self):
        _, step, _ = self.begin(PAPER, "--agent", "codex", "--preference", "I always use we", name="paper.tex")
        self.assertEqual(step["step"]["id"], "setup")
        self.submit({"answer": "declined"})
        _, step, _ = self.submit({"entries": [{"heading": "Voice & person", "text": "Use we.", "replaces": ""}]})
        notice, plans = step["notices"][0], []
        while step["step"]["kind"] != "done":
            plans.append(step["plan"])
            step = self.revise_until_report(step)
            _, step, _ = self.submit(REPORT)
        out_plans = self.part_plans(step["output"])
        self.assertEqual((len(plans), len(out_plans)), (5, 5))
        self.assertTrue(all(p.endswith(" · guard=off") for p in plans + out_plans), plans + out_plans)
        self.assertEqual(step["output"].count(notice), 1)
        self.assertTrue(step["output"].startswith(out_plans[0] + "\n\n" + notice + "\n\n## "), step["output"][:300])


class WholePaperRunRulesTests(Case):
    def guard(self):
        payload = json.dumps({"hook_event_name": "Stop", "cwd": str(self.proj), "stop_hook_active": False})
        code, out, _ = self.run_engine("guard", stdin=payload)
        return out

    def test_a_whole_paper_is_one_open_run_until_its_last_section(self):
        _, step, _ = self.begin(PAPER, name="paper.tex")
        run = step["run"]
        for _ in range(4):
            step = self.revise_until_report(step)
            _, step, _ = self.submit(REPORT)
            code, _, err = self.run_engine("start", "--input", str(self.input_path))
            self.assertEqual(code, 9)
            self.assertIn(run, err)
        step = self.revise_until_report(step)
        _, done, _ = self.submit(REPORT)
        self.assertEqual(done["step"]["kind"], "done")
        self.assertEqual(self.run_engine("start", "--input", str(self.input_path))[0], 0)

    def test_the_guard_blocks_on_the_current_section_and_sees_progress(self):
        _, step, _ = self.begin(PAPER, name="paper.tex")
        for _ in range(5):  # more blocks than the stall limit, with progress between them
            for _ in range(2):
                out = self.guard()
                self.assertEqual(out["decision"], "block")
                self.assertIn(step["run"], out["reason"])
            self.assertIn("Revise the", out["reason"])
            step = self.revise_until_report(step)
            _, step, _ = self.submit(REPORT)
            if step["step"]["kind"] == "done":
                break
        self.assertIsNone(self.guard())

    def test_the_guard_lets_the_author_answer_a_clarifying_question(self):
        self.begin(te.INTRO, "--section", "methods")
        self.assertIsNone(self.guard())


class PlainSplitTests(Case):
    def start_plain(self):
        return self.begin(PLAIN, "--section", "whole-paper", "--mode", "revise")

    def split(self, *ranges):
        return self.submit({"parts": [{"section": s, "start": a, "end": b} for s, a, b in ranges]})

    def test_plain_whole_paper_starts_with_a_split_step(self):
        _, out, _ = self.start_plain()
        self.assertEqual(out["step"], {"id": "split", "kind": "work"})
        self.assertEqual(out["context"]["lines"], 3)
        self.assertEqual(set(out["expect"]["fields"]), {"parts"})

    def test_gaps_overlaps_and_short_splits_are_rejected(self):
        self.start_plain()
        cases = {
            "gap": [("introduction", 1, 1), ("methods", 3, 3)],
            "overlap": [("introduction", 1, 2), ("methods", 2, 3)],
            "late start": [("introduction", 2, 3)],
            "short": [("introduction", 1, 2)],
            "long": [("introduction", 1, 4)],
            "backwards": [("introduction", 1, 0), ("methods", 1, 3)],
        }
        for name, ranges in cases.items():
            with self.subTest(name):
                code, out, _ = self.split(*ranges)
                self.assertEqual((code, out["step"]["id"]), (5, "split"))
                self.assertTrue(out["error"])

    def test_bad_section_values_are_rejected(self):
        self.start_plain()
        code, out, _ = self.split(("appendix", 1, 3))
        self.assertEqual((code, out["step"]["id"]), (5, "split"))
        code, out, _ = self.split(("whole-paper", 1, 3))
        self.assertEqual(code, 5)

    def test_an_exact_split_runs_the_sections_in_order(self):
        _, out, _ = self.start_plain()
        run = out["run"]
        code, step, _ = self.split(("introduction", 1, 1), ("methods", 2, 2), ("other", 3, 3))
        self.assertEqual(code, 0)
        self.assertIn("revise · introduction ·", step["plan"])
        self.assertEqual((step["part"]["index"], step["part"]["of"]), (1, 3))
        order = []
        while step["step"]["kind"] != "done":
            order.append(re.search(r"revise · (\S+) ·", step["plan"]).group(1))
            step = self.revise_until_report(step)
            _, step, _ = self.submit(REPORT)
        self.assertEqual(order, ["introduction", "methods", "other"])
        self.assertEqual(step["output"].count("## Check"), 3)
        parts = sorted((self.run_dir(run) / "parts").glob("*/input.txt"))
        self.assertEqual("".join(p.read_text() for p in parts), PLAIN)


if __name__ == "__main__":
    unittest.main()
