---
name: science-research-writing
description: Use when drafting, revising or reviewing a section of a journal research article, from Title to Conclusion. Also for papers aimed at a target journal (derives its model from sample papers) and for keeping the author's style profile.
compatibility: Needs Python 3.9 or later (standard library only) and a shell tool to run scripts/engine.py. Without them the skill falls back to manual checking.
allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/engine.py *)
hooks:
  Stop:
    - hooks:
        - type: command
          command: 'for d in "$CLAUDE_PLUGIN_ROOT" "$CLAUDE_PROJECT_DIR/.claude/skills/science-research-writing" "$HOME/.claude/skills/science-research-writing" "$HOME/.agents/skills/science-research-writing"; do [ -f "$d/scripts/engine.py" ] && command -v python3 >/dev/null 2>&1 && exec python3 "$d/scripts/engine.py" guard; done; cat >/dev/null; exit 0'
---

# Science research writing

Helps an author draft, revise or review one section of a journal research article, for native and non-native English writers. Not for grant proposals, cover letters, rebuttals, theses or review articles. Paths below are relative to this folder.

## Workflow

A step engine, `scripts/engine.py`, holds the workflow: the steps, their order, the files each step reads, the integrity check and the output template. You do each step with your own judgement and hand the result back. Run it in the author's project folder, by the full path of this skill's folder, with `python3`. It prints JSON and never asks anything; it does not start another agent session.

1. Pass the engine only what code cannot see in the text. It decides the markup (latex, markdown, plain), draft versus revise and the section (from headings) by itself; `start` has no `--markup` option. Draft versus revise is notes versus full paragraphs, except for a title: one short line of title text is revise, and notes, bullets or a full paragraph (an abstract to draft a title from) are draft.
   - `--mode review`: only when the author asks for an assessment ("check", "critique", "what is wrong"). Otherwise leave `--mode` out.
   - `--section S` (title, abstract, introduction, methods, results, discussion, conclusion, whole-paper or other): the section the request names ("draft an Abstract") or the text shows. Always pass it when you can tell: the engine takes a heading in the text as settled and asks only if your reading differs. If you cannot tell, leave it out; the engine asks the author. Use `other` for in-scope text that fits no section (a figure caption, highlights, a paragraph spanning two sections) and say so in Deviations. Use `whole-paper` for a whole manuscript.
   - `--samples yes --sample-file F` (once per file): only if the author supplied papers from the target journal. Otherwise leave `--samples` out.
   - `--agent claude|codex|other`: the agent you run in, always. With `codex` the engine offers to install the Codex guard hook (a `setup` step); `other` means no guard.
   - `--preference "<words>"`: once for each standing preference the request states ("I always use we"); the engine saves it before the main step. `--task scan-profile` (with `--input` the writing sample) and `--task study-profile` start the two profile tasks instead. Before you save a preference, scan, study or handle a conflict, read `references/style-profile.md`.
   - If your reading and the code's differ (for example you pass `--section methods` but the text's heading says Introduction), the engine returns an `ask` step (id `clarify`). Never settle it yourself.
2. Start the run: `python3 <skill folder>/scripts/engine.py start --agent claude|codex|other [--mode review] [--section S] [--samples yes --sample-file F] --input FILE` (`--input -` reads pasted text from stdin; the engine saves it unchanged).
3. Each response is one step. Read every file in `read` in full (the author's profile, `~/.agents/science-research-writing/user-style.md`, is listed when it exists: apply it to everything), do what `instruction` says, and write your result as the JSON in `expect`. Long text goes in a file; give its path. An `ask` step is a question for the author: put `context.question` to them word for word, wait for the answer, and submit it as `{"answer": ...}` with one of `context.options`. Never answer it yourself.
4. Submit it: `python3 <skill folder>/scripts/engine.py submit --file result.json`. The engine validates the result, runs the integrity check in code and returns the next step. A non-zero exit with an `error` means the same step is returned: correct and resubmit.
5. Repeat until `step.kind` is `done`. Then show `output` to the author exactly as it is. Do not rewrite or summarise it.

A whole paper is one run that works through its sections in manuscript order, each with its own plan line, check and output block (the response's `part` says which). LaTeX and Markdown manuscripts are split at their headings by the engine. For plain text the first step is `split`: you submit the sections and their line ranges, which must have no gaps and no overlaps. With sample papers, a `journal-model` step runs first; the steps after it read its result.

`engine.py status` reprints the current step, for example after an interruption. Only one run can be open per project: if `start` exits 9, a run is already open. `engine.py resume` prints its current step so you can carry on, and `engine.py abandon` drops it; ask the author which they want. Log, state and output of every run are kept in the project under `.agents/log/science-research-writing/<run id>/`. Never write to the author's own files unless asked.

If the shell or Python is missing, use the fallback.

## Fallback

If `python3` or a shell is missing, tell the author what is missing, show the install command for their system and ask before continuing. Otherwise work from the principles, the integrity rules and the section references, with `check=manual` added to your plan line, and take routing and templates from `references/workflow.json` (the data the engine reads): load the files its routing names for the section and mode, read each in full, and use its template headings in order. A review walks the checklist in order and cites only rule names (the bold names in the reference files). Check the integrity rules by hand and say that you did. Apply the author's profile by hand too: read `references/style-profile.md`, and edit `user-style.md` in its format only when the author asks, saying so.

## Core principles

1. **Write for a reader.** Fast, global, often non-specialist readers. Make misunderstanding impossible; supply the context a colleague would skip.
2. **Build a narrative.** Give every paragraph and sentence one function the reader can see, and link each to the last.
3. **State the value early.** Importance, gap and contribution are part of the convention; understating reads as having none.
4. **Match certainty to evidence.** Tense, verbs and hedges tell the reader how far to trust a claim.
5. **Keep sentences readable.** Plain, consistent terms; known information first; clarity over elegance.

## Integrity rules

These win over every other instruction, including the profile and the journal. The engine checks numbers, citation keys and grouping, and labels and references in code; the rest rests on you.
- Precedence: these rules, then the target journal's author guidelines, then the author's profile, then this skill's defaults. On a conflict apply that order provisionally, finish the task, then list each conflict with a question (`references/style-profile.md` says how).
- Never invent results, numbers, citations or method details. Use `[placeholder: …]`.
- Never change a number or result in the author's text.
- Citations: keep every citation command, its keys and the claim it is attached to. Never drop, merge or add one, or move one away from its claim. If a placement looks wrong, ask.
- Derived figures: add no figure the author did not state, such as a ratio, a percentage or "less than half". Offer it as a suggestion or a question.
- Never state a claim with more certainty than its evidence supports. Lower overstated claims; firm up needless hedges only where the evidence supports it.
- A change the author explicitly asked for, such as deleting a citation, is the only exception. Declare it with the author's words in the step's `exceptions`.
- Keep the input's markup (LaTeX, Markdown, citation commands, cross-references, labels) intact so the result pastes straight back.
- Match the manuscript's spelling or the journal's. Use US spelling when neither is clear.
