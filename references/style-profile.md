# Style profile rules

The profile is the author's standing writing preferences. It lives in `user-style.md` in `~/.agents/science-research-writing/` (the engine's `SCIENCE_RESEARCH_WRITING_PROFILE_DIR` variable redirects the folder), outside the skill folder. Installing, updating or removing the skill never touches it, and every agent shares it. A profile an older version left in the skill folder is moved there once; the engine says so. If both exist the engine overwrites nothing and gives you a `profile-conflict` step: put the question to the author. This file says how to keep the profile.

## 1. Format and creation

- The file has these headings, in this order: **Voice & person**; **Tone & certainty** (include words to avoid); **Sentences**; **Terminology** (required terms and swaps); **Conventions** (serial comma, numbers and units, abbreviations); **Section habits**; **Exemplars**; **Resolutions**. The engine accepts no other heading.
- One entry per bullet, one line, in plain words a later reader can test against a text. You write the entry's words only; the engine adds the tag.
- Every entry ends with a tag: `(stated|corrected|scanned|edited, YYYY-MM-DD)`. The source says how the entry got in; the date is the day it was saved, so stale or inferred entries show.
- **Exemplars**: at most 5 short passages (a few sentences each) the author approved as sounding like them. Use them to match voice, not to copy content. The engine refuses a sixth and lists the five: ask the author which to drop, `profile remove` it, then add the new one.
- **Resolutions**: the author's answers to past conflicts, one line each, naming both sides and the choice (see section 4).
- The first save creates the file from `references/profile-template.md` (headings only); the engine does this, you do not copy it. Existing entries are never removed unless you call `profile remove` at the author's request.
- Before a save, check whether an existing entry means the same. If so, use `profile replace --old "<that entry>"` so the entry is updated (new date) instead of duplicated. Meaning is your judgement; the engine only finds the old line.
- Read the profile at the start of every task (the engine lists it in `read`). An untagged line is the author's own edit: apply it if its meaning is clear, and treat it as `edited` with an unknown date.

The engine commands, all through `python3 <skill folder>/scripts/engine.py`:
- `profile add --heading H --text T --source S`
- `profile replace --old OLD --heading H --text T --source S`
- `profile remove --line LINE`

`S` is stated, corrected, scanned or edited. OLD and LINE are the entry's text, with or without its tag. Each prints one announcement line; a refusal prints why and writes nothing.

## 2. Four ways in, and how far each is trusted

| Route | Trigger | Save rule |
| --- | --- | --- |
| **Stated** | The author says a preference ("I always use we", "never write novel") | Pass it to `start` as `--preference "<their words>"`. The engine adds a `save-preference` step before the main step; submit the entries, and the output announces the save in one line. Highest trust. |
| **Corrected** | The author rejects or reverses one of your edits | Propose an entry in one line. Only if the author confirms, run `profile add --source corrected` (or `replace`). Until then apply nothing beyond the current text. |
| **Scanned** | The author asks for a style scan of a writing sample | `start --task scan-profile --input FILE`. At `propose`, list entries, each with the evidence that suggested it (a pattern seen at least three times). At `ask`, show them numbered and submit only the numbers the author approves. |
| **Edited** | The author edited the file and asks you to study it | `start --task study-profile`. Follow section 3. |

Rules for all four:
- Nothing inferred is saved without confirmation. Only a direct statement counts as stated.
- A preference stated for one passage only ("not here") is not a profile entry; do not pass it as `--preference`. If unsure whether it is standing, ask.
- A stated preference is saved even when it contradicts an existing entry: put that entry in `replaces`. The announcement names the entry it replaced.
- Report each save in one line, even a confirmed one. The engine announces `save-preference` and scan or study saves itself; announce a `profile add` you run yourself.

## 3. Studying the author's edits

1. Start the task and read the whole profile.
2. At `restate`, give every entry in `entries` with a one-line restatement in your own words, so the author can check you read it as meant. The engine rejects a result that skips an entry.
3. Flag each entry that is unclear (no way to test a text against it), untagged, in the wrong heading, or contradicts another entry. For each flag, give a question or offer a clearer wording as an option. A general rule beside a section-specific one ("we" everywhere; passive in Methods) is not a contradiction: the specific one governs its section.
4. In `changes`, propose the reformatting into the standard headings and tags: which entries would move, which tags would be added. Change an entry's meaning only after asking.
5. At `ask`, put the numbered changes to the author. Nothing is written before the answer; after it, the engine applies only the approved numbers.
6. Until the author answers, apply the clear entries and leave the flagged ones unapplied. If the author cannot answer now, stop at `ask`: the run stays open and nothing is written.

Done means every entry has been restated, each unclear or contradictory one is flagged, and the file is untouched until approval.

## 4. Precedence and conflicts

The precedence order is in `SKILL.md` (Integrity rules). This section says how to handle conflicts.

- Journal guidelines count only when the author gave them in the request or in supplied text.
- **Provisional resolution.** When two sources disagree, apply the stronger one, finish the task, and list each conflict after the output. Never stop the task to ask.
- **Report format.** One item per conflict: what the profile says, what the stronger source says, what you applied, and a question ("Keep the journal's spelling for this paper only, or make it a standing rule?").
- **Integrity conflicts** (a profile entry that would invent, change or strengthen a result, number or citation) are always reported, every time, and integrity always wins. A saved resolution never overrides integrity.
- **Two profile entries in conflict**: apply the more specific one (section habit over general voice), or the later date if equally specific, and report it.
- **Profile against a book default**: the profile wins. Report the conflict once, with a question, and save the author's answer under Resolutions. After that, do not raise it again.
- **Saving the answer.** When the author answers, `profile add --heading Resolutions --source stated` one line under Resolutions naming both sides and the choice, tagged `(stated, date)`. A resolution says which source wins for that case; it does not rewrite the entry it overruled. Apply a saved resolution from then on and do not raise that conflict again. Not applicable to integrity conflicts.
- **Review mode** skips anything the profile or a resolution already settles. It still reports integrity problems and conflicts with the journal that have no resolution yet.

## 5. Applying the profile

- Apply entries to the draft, revision or review. A preference that shapes only sentence-level choices (person, spelling, terms, serial comma) changes the text; a section habit shapes structure.
- A word to avoid is avoided in your own text; leave the author's quotations and terms of art as written unless asked.
- In revise mode, make only edits the profile allows, and list a profile-driven change in the short change list only if it is important.
- Mention the profile in the output only to announce a save or report a conflict.
