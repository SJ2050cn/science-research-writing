"""Black-box tests: every test runs the engine's command line as a subprocess
in a temporary project folder and asserts on stdout JSON, exit codes and files.
Run with:  python3 -m unittest discover -s tests -v
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sandbox import sandbox_env

ENGINE = Path(__file__).resolve().parent.parent / "scripts" / "engine.py"

INTRO = (
    "\\section{Introduction}\r\n"
    "\\label{sec:intro}  \r\n"
    "Nitrate above 50~mg/L is a risk \\cite{who2017}. Land use matters "
    "\\cite{nolan2015,rodriguez2019}. We used 120 wells and got $R^2=0.81$ "
    "(Table~\\ref{tab:perf}, Eq.~\\eqref{eq:r2}). See Section~\\ref{sec:methods}.\r\n"
)
# A faithful revision: same numbers, citations, labels and refs.
GOOD = (
    "\\section{Introduction}\n\\label{sec:intro}\n"
    "Nitrate above 50\\,mg/L is a health risk \\cite{who2017}. Land use matters "
    "\\cite{nolan2015,rodriguez2019}. With 120 wells we reached $R^2=0.81$ "
    "(Table~\\ref{tab:perf}, Eq.~\\eqref{eq:r2}). Section~\\ref{sec:methods} gives details.\n"
)
REPORT = {
    "changes": ["Added a gap statement"],
    "questions": ["Is land use the strongest predictor?"],
    "conflicts": [],
    "deviations": [],
}
START = ["start", "--section", "introduction", "--mode", "revise",
         "--samples", "no"]


class EngineCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patch = mock.patch.dict(os.environ, sandbox_env(Path(self._tmp.name).resolve()))  # never the real profile
        patch.start()
        self.addCleanup(patch.stop)
        self.proj = Path(self._tmp.name).resolve() / "proj"
        (self.proj / ".git").mkdir(parents=True)
        self.input_path = self.proj / "intro.tex"
        self.input_path.write_bytes(INTRO.encode())

    def run_engine(self, *args, stdin=None, cwd=None):
        p = subprocess.run(
            [sys.executable, str(ENGINE), *args], cwd=str(cwd or self.proj),
            input=stdin, capture_output=True, text=True,
        )
        out = json.loads(p.stdout) if p.stdout.strip() else None
        return p.returncode, out, p.stderr

    def start(self, *extra):
        return self.run_engine(*START, "--input", str(self.input_path), *extra)

    def write(self, name, content):
        p = self.proj / name
        p.write_text(content)
        return p

    def submit(self, payload, *extra):
        return self.run_engine("submit", "--file", "-", *extra, stdin=json.dumps(payload))

    def submit_text(self, text, exceptions=None):
        f = self.write("rev.tex", text)
        return self.submit({"text_file": str(f), "exceptions": exceptions or []})

    def run_dir(self, run_id):
        return self.proj / ".agents" / "log" / "science-research-writing" / run_id

    def finish(self, text=GOOD, exceptions=None):
        """start, revise, any fixes, report; returns the last response."""
        _, step, _ = self.start()
        _, step, _ = self.submit_text(text, exceptions)
        while step["step"]["id"] == "fix":
            _, step, _ = self.submit_text(text, exceptions)
        _, step, _ = self.submit(REPORT)
        return step


class StartTests(EngineCase):
    def test_start_returns_revise_step(self):
        code, out, _ = self.start()
        self.assertEqual(code, 0)
        self.assertRegex(out["run"], r"^\d{8}-\d{6}-revise-introduction(-\d+)?$")
        self.assertEqual(
            out["plan"],
            "Plan: revise · introduction · markup=latex · samples=no · run=" + out["run"])
        self.assertEqual(out["step"], {"id": "revise", "kind": "work"})
        self.assertEqual(out["attempt"], 1)
        reads = [Path(p).as_posix() for p in out["read"]]
        self.assertTrue(any(p.endswith("references/introduction.md") for p in reads))
        self.assertTrue(any(p.endswith("references/language.md") for p in reads))
        self.assertTrue(any(p.endswith("/input.txt") for p in reads))
        self.assertFalse(any(p.endswith("checklist.md") for p in reads))
        self.assertTrue(all(os.path.isfile(p) for p in out["read"]))
        self.assertTrue(out["instruction"].strip())
        self.assertEqual(out["expect"]["format"], "json")
        self.assertEqual(set(out["expect"]["fields"]), {"text_file", "exceptions"})
        self.assertIsNone(out.get("error"))

    def test_revise_builds_a_missing_move_only_from_the_text(self):
        _, out, _ = self.start()
        ins = out["instruction"]
        self.assertIn("section model", ins)
        self.assertIn("[placeholder:", ins)

    def test_report_asks_a_question_for_each_missing_fact(self):
        _, step, _ = self.start()
        _, step, _ = self.submit_text(GOOD)
        self.assertEqual(step["step"]["id"], "report")
        ins = step["instruction"]
        self.assertIn("did not have", ins)
        self.assertIn("one question for each", ins)

    def test_section_other_reads_language_and_the_principles(self):
        self.input_path.write_bytes(INTRO.split("\n", 2)[2].encode())  # no section heading
        code, out, _ = self.run_engine(
            "start", "--section", "other", "--mode", "revise", "--samples", "no",
            "--input", str(self.input_path))
        self.assertEqual(code, 0)
        mds = [Path(p).name for p in out["read"] if p.endswith(".md")]
        self.assertEqual(mds, ["language.md", "SKILL.md"])

    def test_run_folder_and_input_saved_unchanged(self):
        _, out, _ = self.start()
        d = self.run_dir(out["run"])
        self.assertEqual((d / "input.txt").read_bytes(), INTRO.encode())
        state = json.loads((d / "state.json").read_text())
        self.assertEqual(state["fields"], {
            "section": "introduction", "mode": "revise",
            "samples": "no", "markup": "latex"})
        self.assertEqual((self.proj / ".agents/log/.gitignore").read_text(), "*\n")
        self.assertEqual(self.input_path.read_bytes(), INTRO.encode())

    def test_pasted_text_from_stdin_saved_unchanged(self):
        code, out, _ = self.run_engine(*START, "--input", "-", stdin=INTRO)
        self.assertEqual(code, 0)
        self.assertEqual((self.run_dir(out["run"]) / "input.txt").read_bytes(),
                         INTRO.encode())

    def test_project_root_is_nearest_git_folder_else_cwd(self):
        sub = self.proj / "a" / "b"
        sub.mkdir(parents=True)
        _, out, _ = self.run_engine(*START, "--input", str(self.input_path), cwd=sub)
        self.assertTrue(self.run_dir(out["run"]).is_dir())
        bare = Path(self._tmp.name) / "bare"
        bare.mkdir()
        _, out, _ = self.run_engine(*START, "--input", str(self.input_path), cwd=bare)
        self.assertTrue((bare / ".agents/log/science-research-writing" / out["run"]).is_dir())

    def test_run_id_gets_numeric_suffix_on_collision(self):
        ids = set()
        for _ in range(3):
            ids.add(self.start()[1]["run"])
            self.run_engine("abandon")  # one open run per project
        self.assertEqual(len(ids), 3)


class HappyPathTests(EngineCase):
    def test_clean_run_renders_exact_revise_template(self):
        _, step, _ = self.start()
        run = step["run"]
        code, step, _ = self.submit_text(GOOD)
        self.assertEqual(code, 0)
        self.assertEqual(step["step"], {"id": "report", "kind": "work"})
        self.assertEqual(set(step["expect"]["fields"]),
                         {"changes", "questions", "conflicts", "deviations"})
        code, step, _ = self.submit(REPORT)
        self.assertEqual(code, 0)
        self.assertEqual(step["step"], {"id": "done", "kind": "done"})
        self.assertEqual(step["status"], "done")
        plan = ("Plan: revise \u00b7 introduction \u00b7 markup=latex \u00b7 samples=no \u00b7 run="
                + run)
        expected = "\n".join([
            plan, "",
            "## Revised text", "", "```latex", GOOD.rstrip("\n"), "```", "",
            "## Changes", "", "- Added a gap statement", "",
            "## Questions", "", "- Is land use the strongest predictor?", "",
            "## Conflicts", "", "None", "",
            "## Deviations", "", "None", "",
            "## Check", "",
            "Check: passed. Verified by code: numbers, citations, cross-references. "
            "Placeholders: none. Exceptions accepted: none. Not verified by code: "
            "citation placement relative to its claim, spelled-out quantities.",
        ]) + "\n"
        self.assertEqual(step["output"], expected)
        d = self.run_dir(run)
        self.assertEqual((d / "output.md").read_text(), expected)
        self.assertEqual(json.loads((d / "check-report.json").read_text())["passed"], True)
        self.assertEqual(sorted(p.name for p in (d / "results").iterdir()),
                         ["01-revise.json", "01-revise.txt", "02-check.json", "03-report.json"])
        self.assertEqual((d / "results" / "01-revise.txt").read_text(), GOOD)

    def test_status_reports_current_and_finished_steps(self):
        _, step, _ = self.start()
        code, st, _ = self.run_engine("status")
        self.assertEqual((code, st["step"]["id"], st["attempt"]), (0, "revise", 1))
        self.submit_text(GOOD)
        done = self.submit(REPORT)[1]
        code, st, _ = self.run_engine("status", "--run", done["run"])
        self.assertEqual((code, st["step"]["kind"]), (0, "done"))
        code, _, err = self.run_engine("status")  # no open run any more
        self.assertEqual(code, 4)
        self.assertIn("no open run", err)

    def test_markdown_input_gets_markdown_fence(self):
        self.input_path.write_text("We used 5 wells [@smith2020].\n")
        self.run_engine("start", "--section", "other", "--mode", "revise", "--samples", "no",
                        "--input", str(self.input_path))
        self.submit({"answer": "revise"})  # no full paragraph: code reads draft, the request says revise
        self.submit_text("We sampled 5 wells [@smith2020].\n")
        _, step, _ = self.submit(REPORT)
        self.assertIn("```markdown\nWe sampled 5 wells [@smith2020].\n```", step["output"])


class CheckerTests(EngineCase):
    def kinds_for(self, text, exceptions=None):
        self.run_engine("abandon")  # one open run per project; a subTest loop starts several
        self.start()
        _, step, _ = self.submit_text(text, exceptions)
        if step["step"]["id"] == "fix":
            self.assertEqual(step["attempt"], 1)
            return sorted((f["kind"], f["item"]) for f in step["context"]["failures"])
        return []

    def test_added_number(self):
        bad = GOOD.replace("120 wells", "120 wells at 12 sites")
        self.assertEqual(self.kinds_for(bad), [("number_added", "12")])

    def test_removed_number(self):
        bad = GOOD.replace("above 50\\,mg/L", "above the limit")
        self.assertEqual(self.kinds_for(bad), [("number_removed", "50")])

    def test_numbers_compare_after_normalising_latex_escapes_and_spacing(self):
        self.input_path.write_text("We drilled 1\\,000 wells, 50~mg/L and 2{,}500 more.\n")
        self.start()
        self.submit({"answer": "revise"})  # no full paragraph: code reads draft, the request says revise
        _, step, _ = self.submit_text("There were 1000 wells; 50 mg/L; 2,500 more.\n")
        self.assertEqual(step["step"]["id"], "report")

    def test_changed_citation_key_is_not_a_number_failure(self):
        bad = GOOD.replace("who2017", "who2018")
        self.assertEqual(self.kinds_for(bad), [
            ("citation_added", "who2018"), ("citation_removed", "who2017")])

    def test_merged_citation_grouping(self):
        bad = GOOD.replace("\\cite{nolan2015,rodriguez2019}", "\\cite{nolan2015}\\cite{rodriguez2019}")
        self.assertEqual(self.kinds_for(bad), [
            ("citation_added", "nolan2015"), ("citation_added", "rodriguez2019"),
            ("citation_removed", "nolan2015,rodriguez2019")])

    def test_dropped_label_ref_and_eqref(self):
        for cmd in ("\\label{sec:intro}", "\\ref{tab:perf}", "\\eqref{eq:r2}"):
            with self.subTest(cmd=cmd):
                self.assertEqual(self.kinds_for(GOOD.replace(cmd, "")), [("reference_removed", cmd)])

    def test_markdown_and_numbered_citations(self):
        self.input_path.write_text("A [@a2020; @b2021] and B [1, 2] with 3 wells.\n")
        self.run_engine("start", "--section", "other", "--mode", "revise", "--samples", "no",
                        "--input", str(self.input_path))
        self.submit({"answer": "revise"})  # no full paragraph: code reads draft, the request says revise
        _, step, _ = self.submit_text("A [@a2020] and B [1, 2] with 3 wells.\n")
        self.assertEqual(sorted(f["kind"] for f in step["context"]["failures"]),
                         ["citation_added", "citation_removed"])

    def test_placeholders_counted_and_listed(self):
        text = GOOD + "[placeholder: sample size] and [placeholder: site name]\n"
        done = self.finish(text)
        self.assertIn("Placeholders: 2 ([placeholder: sample size]; [placeholder: site name])",
                      done["output"])
        rep = json.loads((self.run_dir(done["run"]) / "check-report.json").read_text())
        self.assertEqual(rep["placeholders"],
                         ["[placeholder: sample size]", "[placeholder: site name]"])

    def test_declared_exception_passes_and_is_listed(self):
        bad = GOOD.replace(" \\cite{who2017}", "")
        ex = [{"item": "\\cite{who2017}", "quote": "please delete the WHO citation"}]
        done = self.finish(bad, ex)
        self.assertEqual(done["step"]["id"], "done")
        self.assertNotIn("failed", done["output"])
        self.assertIn('Accepted exception, who2017 (author asked: "please delete the WHO citation")',
                      done["output"])
        self.assertIn('Exceptions accepted: 1 (who2017: "please delete the WHO citation")',
                      done["output"])

    def test_fix_then_pass(self):
        self.start()
        _, step, _ = self.submit_text(GOOD.replace("120", "130"))
        self.assertEqual((step["step"]["id"], step["attempt"]), ("fix", 1))
        self.assertTrue(step["instruction"].strip())
        self.assertTrue(any(p.endswith("check-report.json") for p in step["read"]))
        _, step, _ = self.submit_text(GOOD)
        self.assertEqual(step["step"]["id"], "report")
        _, done, _ = self.submit(REPORT)
        self.assertTrue(done["output"].startswith("Plan:"))
        state = json.loads((self.run_dir(done["run"]) / "state.json").read_text())
        self.assertEqual([(h["step"], h["attempt"]) for h in state["history"]],
                         [("revise", 1), ("check", 1), ("fix", 1), ("check", 2), ("report", 1)])

    def test_failure_notice_after_two_failed_fixes(self):
        bad = GOOD.replace("120", "130")
        self.start()
        _, step, _ = self.submit_text(bad)
        self.assertEqual((step["step"]["id"], step["attempt"]), ("fix", 1))
        _, step, _ = self.submit_text(bad)
        self.assertEqual((step["step"]["id"], step["attempt"]), ("fix", 2))
        _, step, _ = self.submit_text(bad)
        self.assertEqual(step["step"]["id"], "report")
        _, done, _ = self.submit(REPORT)
        lines = done["output"].splitlines()
        self.assertIn("Integrity check failed", lines[0])
        self.assertIn("number 130 is in the output", lines[0])
        self.assertIn("number 120 is in the input", lines[0])
        self.assertTrue(lines[2].startswith("Plan:"))
        self.assertIn("Check: FAILED (2 failure(s))", done["output"])


class ValidationTests(EngineCase):
    def start_with(self, **over):
        f = {"section": "introduction", "mode": "revise", "samples": "no"}
        f.update(over)
        args = ["start", "--input", str(self.input_path)]
        for k, v in f.items():
            args += ["--" + k, v]
        return self.run_engine(*args)

    def test_values_outside_closed_lists_are_rejected(self):
        for field, bad in (("section", "appendix"), ("mode", "rewrite"),
                           ("samples", "maybe")):
            with self.subTest(field=field):
                code, out, err = self.start_with(**{field: bad})
                self.assertEqual((code, out), (3, None))
                self.assertIn(bad, err)
        self.assertFalse((self.proj / ".agents").exists())

    def test_impossible_combinations_are_rejected(self):
        code, out, err = self.start_with(samples="yes")
        self.assertEqual((code, out), (3, None))
        self.assertIn("sample", err)
        code, _, _ = self.run_engine(*START, "--input", str(self.input_path),
                                     "--sample-file", str(self.input_path))
        self.assertEqual(code, 3)

    def test_an_unwritable_log_folder_fails_with_its_own_code_and_a_plain_message(self):
        (self.proj / ".agents").write_text("a file where the folder should be\n")  # also fails as root
        code, out, err = self.start()
        self.assertEqual((code, out), (10, None))
        self.assertNotIn("Traceback", err)
        for needle in (".agents/log", "approval", "writable"):
            self.assertIn(needle, err)

    def test_missing_input_file(self):
        code, out, err = self.run_engine(*START, "--input", str(self.proj / "nope.tex"))
        self.assertEqual((code, out), (8, None))
        self.assertIn("nope.tex", err)

    def test_malformed_submissions_return_the_same_step_with_the_error(self):
        _, first, _ = self.start()
        cases = {
            "not json": "{oops",
            "not an object": json.dumps(["x"]),
            "missing field": json.dumps({"text_file": str(self.input_path)}),
            "extra field": json.dumps({"text_file": str(self.input_path), "exceptions": [], "x": 1}),
            "missing file": json.dumps({"text_file": str(self.proj / "no.tex"), "exceptions": []}),
            "exception without quote": json.dumps({
                "text_file": str(self.input_path), "exceptions": [{"item": "50", "quote": " "}]}),
        }
        for name, raw in cases.items():
            with self.subTest(name):
                code, out, err = self.run_engine("submit", "--file", "-", stdin=raw)
                self.assertEqual(code, 5)
                self.assertTrue(out["error"])
                self.assertIn(out["error"], err)
                self.assertEqual((out["step"], out["attempt"], out["run"]),
                                 (first["step"], first["attempt"], first["run"]))
        code, out, _ = self.submit_text(GOOD)
        self.assertEqual((code, out["step"]["id"]), (0, "report"))
        code, out, _ = self.submit({"changes": "x", "questions": [], "conflicts": [], "deviations": []})
        self.assertEqual((code, out["step"]["id"]), (5, "report"))

    def test_submit_to_a_finished_or_unknown_run(self):
        done = self.finish()
        code, _, err = self.run_engine("submit", "--file", "-", "--run", done["run"], stdin="{}")
        self.assertEqual(code, 4)
        self.assertIn("not open", err)
        self.assertEqual(self.run_engine("status", "--run", "20000101-000000-revise-title")[0], 4)

    def test_engine_never_prompts(self):
        p = subprocess.run([sys.executable, str(ENGINE), *START, "--input", str(self.input_path)],
                           cwd=str(self.proj), stdin=subprocess.DEVNULL, capture_output=True,
                           text=True, timeout=30)
        self.assertEqual(p.returncode, 0)


class PackagingTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parent.parent

    def test_engine_source_parses_as_python_3_9(self):
        import ast
        for f in (self.ROOT / "scripts").rglob("*.py"):
            ast.parse(f.read_text(encoding="utf-8"), filename=str(f), feature_version=(3, 9))

    @unittest.skipUnless(hasattr(sys, "stdlib_module_names"), "sys.stdlib_module_names needs Python 3.10")
    def test_engine_imports_only_the_standard_library(self):
        import re
        local = {"swengine"} | {f.stem for f in (self.ROOT / "scripts" / "swengine").glob("*.py")}
        for f in (self.ROOT / "scripts").rglob("*.py"):
            for m in re.finditer(r"^\s*(?:from|import)\s+([A-Za-z_][\w]*)", f.read_text(), re.M):
                self.assertTrue(m.group(1) in local or m.group(1) in sys.stdlib_module_names, (f, m.group(1)))

    def test_skill_frontmatter_states_the_python_requirement(self):
        head = (self.ROOT / "SKILL.md").read_text().split("---")[1]
        self.assertRegex(head, r"(?m)^compatibility:.*Python 3\.9")

    def test_templates_and_routing_are_data_files_the_engine_reads(self):
        data = json.loads((self.ROOT / "references" / "workflow.json").read_text())
        self.assertEqual([b["heading"] for b in data["templates"]["revise"]],
                         ["Revised text", "Changes", "Questions", "Conflicts", "Deviations", "Check"])
        for names in data["routing"]["section"].values():
            for n in names:
                self.assertTrue((self.ROOT / n).is_file(), n)


if __name__ == "__main__":
    unittest.main()
