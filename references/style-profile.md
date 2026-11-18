# Style profile rules

The profile is the author's standing writing preferences. It lives in `user-style.md` in this skill's folder, next to `SKILL.md`. It is never shipped in the source, so updating or reinstalling the skill cannot overwrite it, and every agent that uses this folder shares it. This file says how to keep it.

## 1. Format and creation

- The file has these headings, in this order: **Voice & person**; **Tone & certainty** (include words to avoid); **Sentences**; **Terminology** (required terms and swaps); **Conventions** (serial comma, numbers and units, abbreviations); **Section habits**; **Exemplars**; **Resolutions**.
- One entry per bullet, one line, in plain words a later reader can test against a text.
- Every entry ends with a tag: `(stated|corrected|scanned|edited, YYYY-MM-DD)`. The source says how the entry got in; the date is the day it was saved, so stale or inferred entries show.
- **Exemplars**: at most 5 short passages (a few sentences each) the author approved as sounding like them. Use them to match voice, not to copy content. When a sixth arrives, ask which one to drop.
- **Resolutions**: the author's answers to past conflicts, one line each, naming both sides and the choice (see section 4).
- First save with no `user-style.md`: copy `references/profile-template.md` to `user-style.md`, then add the entry under its heading. The template holds headings only. If the file exists, edit it in place; never recreate it, never remove an entry the author did not ask to remove.
- Before a save, check for an entry with the same meaning. Update that line (new date) instead of adding a duplicate.
- Read `user-style.md` at the start of every task. An untagged line is the author's own edit: apply it if its meaning is clear, and treat it as `edited` with an unknown date.

## 2. Four ways in, and how far each is trusted

| Route | Trigger | Save rule |
| --- | --- | --- |
| **Stated** | The author says a preference ("I always use we", "never write novel") | Save at once. Tell the author in one line: what was saved and under which heading. Highest trust. |
| **Corrected** | The author rejects or reverses one of your edits | Propose an entry in one line. Save only if the author confirms. Until then apply nothing beyond the current text. |
| **Scanned** | The author asks for a style scan of a writing sample | Read the sample. Propose a numbered list of entries, each with the evidence that suggested it (a pattern seen at least three times). Save only the ones the author approves. |
| **Edited** | The author edited the file and asks you to study it | Run the procedure in section 3. |

Rules for all four:
- Nothing inferred is saved without confirmation. Only a direct statement counts as stated.
- A preference stated for one passage only ("not here") is not a profile entry. If unsure whether it is standing, ask.
- A stated preference is saved at once, even when it contradicts an existing entry. It replaces that entry with a new date, and the announcement names the entry it replaced.
- Report each save in one line, even a confirmed one.

## 3. Studying the author's edits

1. Read the whole file.
2. Restate every entry in one line of your own words, so the author can check you read it as meant.
3. Flag each entry that is unclear (no way to test a text against it), untagged, in the wrong heading, or contradicts another entry. For each flag, ask a question or offer a clearer wording as an option. A general rule beside a section-specific one ("we" everywhere; passive in Methods) is not a contradiction: the specific one governs its section.
4. Offer to reformat into the standard headings and tags: which entries would move, which tags would be added. State plainly what would change.
5. Write nothing until the author approves. After approval, change only what was approved. Change an entry's meaning only after asking.
6. Until the author answers, apply the clear entries and leave the flagged ones unapplied.

Done means every entry has been restated, each unclear or contradictory one is flagged, and the file is untouched until approval.

## 4. Precedence and conflicts

The precedence order is in `SKILL.md` (Style profile). This section says how to handle conflicts.

- Journal guidelines count only when the author gave them in the request or in supplied text.
- **Provisional resolution.** When two sources disagree, apply the stronger one, finish the task, and list each conflict after the output. Never stop the task to ask.
- **Report format.** One item per conflict: what the profile says, what the stronger source says, what you applied, and a question ("Keep the journal's spelling for this paper only, or make it a standing rule?").
- **Integrity conflicts** (a profile entry that would invent, change or strengthen a result, number or citation) are always reported, every time, and integrity always wins. A saved resolution never overrides integrity.
- **Two profile entries in conflict**: apply the more specific one (section habit over general voice), or the later date if equally specific, and report it.
- **Profile against a book default**: the profile wins. Report the conflict once, with a question, and save the author's answer under Resolutions. After that, do not raise it again.
- **Saving the answer.** When the author answers, add one line under Resolutions naming both sides and the choice, tagged `(stated, date)`. A resolution says which source wins for that case; it does not rewrite the entry it overruled. Apply a saved resolution from then on and do not raise that conflict again. Not applicable to integrity conflicts.
- **Review mode** skips anything the profile or a resolution already settles. It still reports integrity problems and conflicts with the journal that have no resolution yet.

## 5. Applying the profile

- Apply entries to the draft, revision or review. A preference that shapes only sentence-level choices (person, spelling, terms, serial comma) changes the text; a section habit shapes structure.
- A word to avoid is avoided in your own text; leave the author's quotations and terms of art as written unless asked.
- In revise mode, make only edits the profile allows, and list a profile-driven change in the short change list only if it is important.
- Mention the profile in the output only to announce a save or report a conflict.
