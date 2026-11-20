# Science Research Writing skill

This agent skill drafts, revises and reviews a journal research article, one section from Title to Conclusion or the whole manuscript. Its section models and language rules come from Hilary Glasman-Deal, *Science Research Writing for Native and Non-Native Speakers of English* (2nd ed., 2020). It covers journal research articles only, not grant proposals, theses, cover letters, responses to reviewers or review articles.

## Features

- **Every run follows the same steps.** A step engine leads the agent through each step in order and checks each result before the run moves on.
- **Your facts stay yours.** Code checks every result against your text for changed numbers, citations and cross-references. A missing fact is marked `[placeholder: …]`, never invented.
- **Your target journal.** Give it a few papers from the journal, and it writes to that journal's model.
- **Your style, remembered.** It keeps your preferences in a profile and applies them to every run.
- **Your LaTeX or Markdown comes back intact,** so the result pastes straight into your manuscript.

## Install

Install the skill in one of the two ways below, then start a new agent session.

### [Step 0] Requirements

The skill needs Python 3.9 or later, with no extra packages. Without Python, it still works, and the agent does the checks by hand.

### [Step 1a] From GitHub with `npx skills`

```bash
npx skills add SJ2050cn/science-research-writing -g
```

The `-g` flag installs the skill globally for your user account (Claude Code, Codex and Antigravity), not for one project. Update it later with `npx skills update`.

### [Step 1b] From a local copy

Clone the skill, then link it into each agent's skills folder. Codex reads `~/.agents/skills` itself, so it needs no link.

```bash
git clone https://github.com/SJ2050cn/science-research-writing.git ~/.agents/skills/science-research-writing
ln -s ~/.agents/skills/science-research-writing ~/.claude/skills/science-research-writing        # Claude Code
ln -s ~/.agents/skills/science-research-writing ~/.gemini/config/skills/science-research-writing # Antigravity
```

For a single project in Antigravity, place the skill in the repository's `.agents/skills/science-research-writing` folder instead. Update a local clone later with `git pull` in that folder.

### [Step 1.1a] Codex only: install the Stop hook

Claude Code gets the Stop hook from the skill itself. Codex needs one command. Use the path where you installed the skill:

```bash
python3 ~/.agents/skills/science-research-writing/scripts/install_codex_hook.py
```

Then open `/hooks` in Codex and trust the hook. If you skip the command, the first Codex run offers to run it for you.

### [Step 1.1b] Antigravity only: install the Stop hook

Antigravity reads hooks from `~/.gemini/config/hooks.json`, not from `SKILL.md`. Run one command using the path where you installed the skill:

```bash
python3 ~/.agents/skills/science-research-writing/scripts/install_antigravity_hook.py
```

No `/hooks` trust step is needed: Antigravity loads the hooks file automatically. If you skip the command, the first Antigravity run offers to run it for you.

### [Step 2] Approve the engine's prompts

Your agent asks for your approval before the engine runs, and Codex asks again before the engine writes outside its sandbox. Approve these prompts. To stop repeat prompts, choose the option that remembers your answer.

In Antigravity, the terminal sandbox blocks access outside your workspace by default. Approve non-workspace prompts when the agent runs the engine from your global skill folder or reads and updates your style profile at `~/.agents/science-research-writing/user-style.md`. To avoid repeat prompts, allow them in Antigravity Settings (Non-Workspace File Access or Command Allowlist).

## Use

Ask in plain words. The skill works out which section you mean and whether to draft, revise or review.

| To | Ask, for example |
|---|---|
| Draft | "Draft an Abstract from these notes: …" |
| Revise | "Revise my Introduction. Keep my LaTeX." |
| Review | "Review my Discussion and tell me what needs fixing." |
| Match a journal | "Revise my Methods to match these two papers from *Journal X*." (attach the papers) |

### What you get

- A draft marks each missing fact `[placeholder: …]`.
- A revision gives the revised text, then a short list of the important changes, then questions for you.
- A review lists the problems from most to least serious, each with a suggested rewrite. It doesn't rewrite your whole text.

## Your style profile

The skill keeps your preferences in `~/.agents/science-research-writing/user-style.md`, outside the skill folder, so an update or a reinstall keeps them. You can add to the profile in four ways:

- State a preference once: "I always use *we*." The skill saves it and tells you.
- Reject one of its edits. The skill offers to save that as a preference.
- Ask for a scan: "Scan this sample of my writing for style preferences." Only the entries you approve are saved.
- Edit the file yourself, then ask "Study my style profile." The skill restates each entry, flags the unclear ones, and changes nothing without your approval.

If your profile conflicts with the journal's guidelines, the journal wins for that task. The skill lists the conflict at the end and saves your answer. The rule against inventing or overstating results always wins.

## Uninstall

Run the uninstall script before you remove the skill:

```bash
python3 ~/.agents/skills/science-research-writing/scripts/uninstall.py
```

The script removes the Codex and Antigravity guard hooks and asks whether to delete your style profile. The default keeps it. Outside a terminal, pass `--keep-profile` or `--remove-profile`. The run logs in your projects stay. At the end, the script prints the command that removes the skill. Run that command yourself.

## What's inside

- `SKILL.md`: the entry point the agent reads first.
- `references/`: one file per section, plus files for language, the review checklist, target-journal models and style-profile rules, and `workflow.json`, the routing and output templates the engine reads.
- `scripts/`: the step engine (`engine.py`), the Codex and Antigravity hook installers and the uninstall script.
- `tests/`: `python3 -m unittest discover -s tests`.

Each run's state, input, results, check report and output are kept in your project under `.agents/log/science-research-writing/<run id>/`. Git ignores that folder.
