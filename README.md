# Science Research Writing skill

This is an agent skill for drafting, revising and reviewing the sections of a journal research article: Title, Abstract, Introduction, Methods, Results, Discussion and Conclusion. Its section models and language rules are distilled from Hilary Glasman-Deal, *Science Research Writing for Native and Non-Native Speakers of English* (2nd ed., 2020).

## Install

### From GitHub with `npx skills`

```bash
npx skills add SJ2050cn/science-research-writing -g
```

The `-g` flag installs the skill for your user account rather than one project. The CLI asks which agents to install it for; add `-y` to skip the prompts. Update it later with `npx skills update`.

### From a local copy

Keep one copy of the skill folder and link it into each agent's skills folder:

```bash
git clone https://github.com/SJ2050cn/science-research-writing.git ~/.agents/skills/science-research-writing

ln -s ~/.agents/skills/science-research-writing ~/.claude/skills/science-research-writing  # Claude Code
ln -s ~/.agents/skills/science-research-writing ~/.codex/skills/science-research-writing   # Codex
```

Because the agents link to one copy, they all share the same style profile. Update it later with `git pull` in that folder.

Whichever way you install, start a new agent session afterwards.

## Use

Ask in plain words. The skill works out which section you mean and whether to draft, revise or review.

| To | Ask, for example |
|---|---|
| Draft | "Draft an Abstract from these notes: …" |
| Revise | "Revise my Introduction. Keep my LaTeX." |
| Review | "Review my Discussion and tell me what needs fixing." |
| Match a journal | "Revise my Methods to match these two papers from *Journal X*." (attach the papers) |

What you get:

- **Drafts** come straight away. Missing facts are marked `[placeholder: …]`, and the skill never invents numbers, results or citations.
- **Revisions** give the revised text, then a short list of the important changes, then questions for you.
- **Reviews** list the problems from most to least serious, each with a suggested rewrite. The skill doesn't rewrite your whole text.
- **Your markup** (LaTeX or Markdown) is kept intact. Spelling follows your manuscript or journal, with US spelling as the default.

## Your style profile

The skill keeps your preferences in `user-style.md` in the skill folder. The file is created the first time a preference is saved. Git ignores it, so `git pull` never overwrites it.

- **Say it once:** "I always use *we*." The skill saves this at once and tells you.
- **Correct an edit:** when you reject one of its changes, it offers to save that as a preference.
- **Ask for a scan:** "Scan this sample of my writing for style preferences." Only the ones you approve are saved.
- **Edit the file yourself,** then ask "Study my style profile." The skill restates each entry, flags any that are unclear, and changes nothing without your approval.

If your profile conflicts with the journal's guidelines, the journal wins for that task. The skill lists the conflict at the end and saves your answer. The rule against inventing or overstating results always wins.

## What's inside

- `SKILL.md`: the entry point the agent reads first.
- `references/`: one file per section, plus files for language, the review checklist, target-journal models and style-profile rules.

## Scope

The skill covers journal research articles only. It doesn't cover grant proposals, theses, cover letters, responses to reviewers or review articles.
