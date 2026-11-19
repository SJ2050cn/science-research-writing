"""Command line: start, submit, status, resume, abandon, guard, profile. Data on stdout as
JSON, diagnostics on stderr, one exit code per failure kind (errors.py), never prompts.
Every run command goes through a Run (run.py)."""
import argparse
import json
import os
import sys

from . import errors, fields, guard, profile, run, runstore


def _emit(obj):
    sys.stdout.write(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def _read_input(spec):
    if spec == "-":
        return sys.stdin.buffer.read()
    try:
        with open(spec, "rb") as f:
            return f.read()
    except OSError as e:
        raise errors.EngineError(errors.INPUT, "cannot read input %s: %s" % (spec, e.strerror))


def cmd_start(args, root, data):
    run.refuse_if_open(root)  # before the fields and the input, so an open run is the error reported
    given = None
    if args.task == "section":
        if not args.input:
            raise errors.EngineError(errors.INVALID_FIELDS, "start needs --input")
        given = {n: getattr(args, n) for n in fields.NAMES if n != "samples"} \
            | {"samples": args.samples or ("yes" if args.sample_file else "no")}
        fields.validate(given, args.sample_file, data)
    elif args.task == "scan-profile" and not args.input:
        raise errors.EngineError(errors.INPUT, "scan-profile needs --input, the writing sample")
    raw = _read_input(args.input) if args.input else None
    _emit(run.Run.start(root, data, args.task, raw, args.agent, given, args.sample_file, args.preference).response())


def cmd_submit(args, root, data):
    r = run.Run.open(root, data, args.run)
    r.refuse_unless_open()  # before the result is read, so a closed run is the error reported
    resp = r.submit(_read_input(args.file))
    _emit(resp)
    if resp["error"]:
        raise errors.EngineError(errors.MALFORMED, resp["error"])


def cmd_status(args, root, data):
    _emit(run.Run.open(root, data, args.run).response())


def cmd_resume(args, root, data):
    _emit(run.Run.open(root, data).resume())


def cmd_abandon(args, root, data):
    _emit(run.Run.open(root, data).abandon())


def cmd_guard(args, root, data):
    sys.exit(guard.run(sys.stdin.read(), lambda project: run.Run.find(project, data)))


def cmd_profile(args, root, data):
    """profile add|replace|remove: one write, tagged and checked by the engine."""
    notice, _ = profile.migrate()
    if args.action == "remove":
        ops = [{"op": "remove", "old": args.line}]
    else:
        ops = [{"op": args.action, "old": getattr(args, "old", ""), "heading": args.heading,
                "text": args.text, "source": args.source}]
    said = profile.apply(ops, data["profile"])
    _emit({"announce": said[0], "notice": notice, "path": str(profile.path())})


def build_parser():
    p = argparse.ArgumentParser(prog="engine.py", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("start", help="start a run and print its first step")
    s.add_argument("--task", default="section", choices=["section", "scan-profile", "study-profile"],
                   help="section (default) needs the four fields and --input; scan-profile needs --input; study-profile none")
    for n in fields.NAMES:  # the markup is decided by code, so it has no option
        s.add_argument("--" + n)
    s.add_argument("--input", help="path to the author's text, or - for stdin")
    s.add_argument("--preference", action="append", default=[],
                   help="a standing preference the author stated in the request, in their words (repeatable)")
    s.add_argument("--sample-file", action="append", default=[])
    s.add_argument("--agent", default="other", choices=["claude", "codex", "other"])
    sb = sub.add_parser("submit", help="submit the current step's result and print the next step")
    sb.add_argument("--file", required=True, help="JSON result file, or - for stdin")
    sb.add_argument("--run", help="run ID; default the open run")
    st = sub.add_parser("status", help="print the current step of a run")
    st.add_argument("--run")
    sub.add_parser("resume", help="print the current step of the open run and clear a stall")
    sub.add_parser("abandon", help="close the open run without finishing it")
    sub.add_parser("guard", help="Stop hook: read the hook JSON on stdin and block while a run is unfinished")
    pp = sub.add_parser("profile", help="write the style profile")
    act = pp.add_subparsers(dest="action", required=True)
    for name in ("add", "replace", "remove"):
        a = act.add_parser(name)
        if name == "remove":
            a.add_argument("--line", dest="line", required=True, help="the entry to remove, with or without its tag")
            continue
        if name == "replace":
            a.add_argument("--old", required=True, help="the entry to replace, with or without its tag")
        a.add_argument("--heading", required=True)
        a.add_argument("--text", required=True, help="one line, no tag")
        a.add_argument("--source", required=True, help="stated, corrected, scanned or edited")
    return p


COMMANDS = {"start": cmd_start, "submit": cmd_submit, "status": cmd_status, "resume": cmd_resume, "abandon": cmd_abandon, "guard": cmd_guard, "profile": cmd_profile}


def main(argv=None):
    args = build_parser().parse_args(argv)
    root = runstore.project_root(os.getcwd())
    try:
        COMMANDS[args.command](args, root, run.load_data())
    except errors.EngineError as e:
        sys.stderr.write("error: %s\n" % e.message)
        return e.code
    return 0
