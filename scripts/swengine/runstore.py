"""Run store: one folder per run under <project>/.agents/log/science-research-writing/<id>/.

Layout of a run folder (a Folder names each file; nothing else spells these names):
  state.json          the whole run state; every step response is rebuilt from it
  input.txt           the author's input, byte for byte
  results/NN-<step>.json|.txt   each submitted result, NN = order of arrival
  check-report.json   the latest integrity report
  output.md           the rendered output, written at done
  parts/NN-<section>/ a whole paper's sections, each laid out like a run folder (no state.json)
The engine writes nowhere else, and never to the author's own files.

A Folder stages its writes until commit(), so a step that refuses leaves no file behind.
Its reads see the staged files.
"""
import io
import json
import os
from datetime import datetime
from pathlib import Path

from . import errors

LOG = Path(".agents") / "log"
RUNS = LOG / "science-research-writing"
STATE, INPUT, CHECK, OUTPUT = "state.json", "input.txt", "check-report.json", "output.md"


def project_root(cwd):
    """Nearest enclosing folder with a .git entry (dir or file), else cwd itself."""
    cwd = Path(cwd).resolve()
    for p in [cwd] + list(cwd.parents):
        if (p / ".git").exists():
            return p
    return cwd


class Folder:
    def __init__(self, path, sub="", staged=None):
        self.path, self.sub = path, sub  # sub: "" for the run, "parts/NN-<section>/" for a section
        self._staged = {} if staged is None else staged  # shared with the part folders: {rel: str | bytes}

    @classmethod
    def of(cls, root, run_id):
        return cls(root / RUNS / run_id)

    @classmethod
    def create(cls, root, mode, section, input_bytes):
        """Make the run folder (collision-safe), the log .gitignore and input.txt, at once."""
        log = root / LOG
        try:
            log.mkdir(parents=True, exist_ok=True)
            gi = log / ".gitignore"
            if not gi.exists():
                gi.write_text("*\n")
            base = "%s-%s-%s" % (datetime.now().strftime("%Y%m%d-%H%M%S"), mode, section)
            n = 1
            while True:
                run_id = base if n == 1 else "%s-%d" % (base, n)
                try:
                    (root / RUNS / run_id).mkdir(parents=True)
                    break
                except FileExistsError:
                    n += 1
            folder = cls.of(root, run_id)
            (folder.path / "results").mkdir()
            (folder.path / INPUT).write_bytes(input_bytes)
        except OSError as e:
            raise errors.EngineError(
                errors.LOG_FOLDER,
                "cannot write the run log in %s (%s). The engine keeps every run there and cannot work without "
                "it. If your sandbox mounts .agents read-only (Codex's workspace-write does), rerun this command "
                "with the sandbox's approval; or the author can add %s as a writable root."
                % (log, e.strerror or e, root / ".agents"))
        return folder

    @property
    def id(self):
        return self.path.name

    def file(self, rel):
        """The absolute path of a file in this folder, as shown in a step response."""
        return str(self.path / (self.sub + rel))

    def _bytes(self, rel):
        rel = self.sub + rel
        return self._staged[rel] if rel in self._staged else (self.path / rel).read_bytes()

    def read(self, rel):
        """A file's text, line endings translated as open() does."""
        data = self._bytes(rel)
        return data if isinstance(data, str) else io.TextIOWrapper(io.BytesIO(data), encoding="utf-8").read()

    def _put(self, rel, content):
        self._staged[self.sub + rel] = content

    # the named files
    def input(self):
        return self.read(INPUT)

    def input_bytes(self):
        return self._bytes(INPUT)

    def check_report(self):
        return json.loads(self.read(CHECK))

    def put_check_report(self, report):
        self._put(CHECK, json.dumps(report, indent=2))

    def output(self):
        return self.read(OUTPUT)

    def put_output(self, text):
        self._put(OUTPUT, text)

    def add_result(self, n, step, ext, content):
        """Stage results/NN-<step>.<ext>; returns its path relative to this folder."""
        rel = "results/%02d-%s.%s" % (n, step, ext)
        self._put(rel, content)
        return rel

    def add_part(self, n, section, input_bytes):
        """Stage the folder of a whole paper's n-th section; returns its name."""
        name = "%02d-%s" % (n, section)
        self._staged["parts/%s/%s" % (name, INPUT)] = input_bytes
        self._staged["parts/%s/results/" % name] = None  # an empty folder
        return name

    def part(self, name):
        return Folder(self.path, "parts/%s/" % name, self._staged)

    # the run folder itself
    def final_id(self, mode, section):
        """The <timestamp>-<mode>-<section> id for a run opened with an ask, free in the log."""
        base = "%s-%s-%s" % (self.id[:15], mode, section)
        new_id, n = base, 1
        while new_id != self.id and (self.path.parent / new_id).exists():
            n += 1
            new_id = "%s-%d" % (base, n)
        return new_id

    def commit(self, state):
        """Rename the folder to the state's id, write the staged files, then state.json."""
        if state["id"] != self.id:
            new = self.path.with_name(state["id"])
            os.rename(str(self.path), str(new))
            self.path = new
        for rel, content in self._staged.items():
            p = self.path / rel
            if content is None:
                p.mkdir(parents=True, exist_ok=True)
                continue
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(content) if isinstance(content, bytes) else p.write_text(content, encoding="utf-8")
        self._staged.clear()
        tmp = self.path / (STATE + ".tmp")
        tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(str(tmp), str(self.path / STATE))


def open_run(root):
    """The newest open run of the project, or None. At most one is ever open."""
    base = root / RUNS
    for d in sorted(base.iterdir(), reverse=True) if base.is_dir() else []:
        try:
            st = json.loads((d / STATE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if st.get("status") == "open":
            return st
    return None


def load_state(root, run_id=None):
    """Load a run by id, or the open run when run_id is None."""
    if run_id is None:
        st = open_run(root)
        if st is None:
            raise errors.EngineError(errors.RUN, "no open run in this project")
        return st
    try:
        return json.loads((root / RUNS / run_id / STATE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise errors.EngineError(errors.RUN, "no readable run %r in this project" % run_id)
