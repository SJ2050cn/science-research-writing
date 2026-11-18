---
name: science-research-writing
description: Use when drafting, revising or reviewing a section of a journal research article, from Title to Conclusion. Also for papers aimed at a target journal (derives its model from sample papers) and for keeping the author's style profile.
---

# Science research writing

Helps an author draft, revise or review one section of a journal research article, for native and non-native English writers. Not for grant proposals, cover letters, rebuttals, theses or review articles. All paths below are relative to this folder.

## Workflow

1. Read `user-style.md` if it exists. It holds the author's profile; apply it to everything below.
2. Identify the section and the mode from the request and the text. Ask only if neither can be inferred.
   - **Draft**: the author gives notes, an outline, bullets or data and wants text written.
   - **Revise**: the author gives text and wants it improved.
   - **Review**: the author gives text and wants an assessment ("check", "critique", "what is wrong").
3. Load the files the routing table names for that section and mode. Read each in full before writing.
4. Produce the output in the mode's contract below. Done means every move of the section model is present or deliberately skipped, and every integrity rule held.
5. If any conflict arose (see Style profile), list it after the output.

## Output contracts

- **Draft**: write the text at once. Mark each missing fact, number or detail as `[placeholder: what is needed]`. Stop to ask only when the main contribution or main finding is unknown. Add a short note of what the placeholders need.
- **Revise**: the revised text, then a short list of the important changes (structure, hedging, emphasis; no comma-level changes), then questions for the author wherever the revision needed information you did not have.
- **Review**: findings ordered by severity. Tie each to a section-model move or a checklist item and give a suggested rewrite of the affected sentence, in the input's markup. Include missing moves (no gap statement, no value statement). Leave the rest of the text as written.

## Core principles

1. **Write for a reader.** Fast, global, often non-specialist readers. Make misunderstanding impossible; supply the context a colleague would skip.
2. **Build a narrative.** Give every paragraph and sentence one function the reader can see, and link each to the last.
3. **State the value early.** Importance, gap and contribution are part of the convention; understating reads as having none.
4. **Match certainty to evidence.** Tense, verbs and hedges tell the reader how far to trust a claim.
5. **Keep sentences readable.** Plain, consistent terms; known information first; clarity over elegance.

## Integrity rules

These win over every other instruction, including the profile and the journal.
- Never invent results, numbers, citations or method details. Use `[placeholder: …]`.
- Never change a number or result in the author's text.
- Citations: keep every citation command, its keys and the claim it is attached to. Never drop, merge or add one, or move one away from its claim. If a placement looks wrong, ask.
- Derived figures: add no figure the author did not state, such as a ratio, a percentage or "less than half". Offer it as a suggestion or a question.
- Never state a claim with more certainty than its evidence supports. Lower overstated claims; firm up needless hedges only where the evidence supports it.

## Style profile

- Precedence: integrity rules, then the target journal's author guidelines, then the author's profile, then this skill's defaults.
- A preference the author states ("I always use we") is saved at once to `user-style.md`, and you say so. A preference you infer from a correction, a writing sample or an edited profile is saved only after the author confirms.
- On a conflict, apply the precedence provisionally, finish the task, then list each conflict with a question. Save the author's answer under Resolutions.
- Always report integrity conflicts. In review mode, skip anything the profile already settles.
- Load `references/style-profile.md` before saving, studying or scanning, or handling a conflict. It has the format and the capture rules.

## Routing

Section and mode decide the files. Always load the section file and `references/language.md`.

| When | Load |
| --- | --- |
| Title | `references/title.md` |
| Abstract | `references/abstract.md` |
| Introduction | `references/introduction.md` |
| Methods | `references/methods.md` |
| Results | `references/results.md` |
| Discussion | `references/discussion.md` |
| Conclusion | `references/conclusion.md` |
| Every task | `references/language.md` |
| Review mode | `references/checklist.md` |
| The author supplies papers from the target journal | `references/reverse-engineering.md` |
| A preference is saved, scanned or studied, or a conflict is handled | `references/style-profile.md` |
| First save to a profile that does not exist yet | copy `references/profile-template.md` to `user-style.md` |

A request that spans sections (a whole paper) takes the files for each section in turn.

## Format

- Keep the input's markup (LaTeX, Markdown, citation commands, cross-references, labels) intact so the result pastes straight back.
- Match the manuscript's spelling or the journal's. Use US spelling when neither is clear.
