# Science Research Writing skill

This is an agent skill for drafting, revising and reviewing the sections of a journal research article: Title, Abstract, Introduction, Methods, Results, Discussion and Conclusion. Its section models and language rules are distilled from Hilary Glasman-Deal, *Science Research Writing for Native and Non-Native Speakers of English* (2nd ed., 2020).

## Requirements

Python 3.9 or later, standard library only. The skill's step engine is a Python script, so check it first:

```bash
python3 --version
```

If that fails or prints something older than 3.9, install Python:

| System | Command |
|---|---|
| Debian, Ubuntu (apt) | `sudo apt install python3` |
| Fedora, RHEL (dnf) | `sudo dnf install python3` |
| macOS (Homebrew) | `brew install python` |
| Windows | Use WSL, then follow the apt line inside it. Native Windows isn't supported. |

Without Python or a shell the skill still works. It tells you what's missing, shows the install command and asks before it continues with the checks done by hand. The plan line then says `check=manual`.

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
```

Codex reads `~/.agents/skills` itself, so it needs no link. Update the copy later with `git pull` in that folder.

Whichever way you install, start a new agent session afterwards.

## Codex

The skill keeps an unfinished run from ending early with a Stop hook. Claude Code gets it from the skill itself. Codex only reads hooks from `~/.codex/hooks.json` (or `config.toml`), so one command adds it:

```bash
python3 ~/.agents/skills/science-research-writing/scripts/install_codex_hook.py
```

Use the path where you installed the skill. The script merges one Stop entry into `~/.codex/hooks.json` and keeps your other hooks. It backs the old file up to `hooks.json.bak` first, and running it again changes nothing. Add `--uninstall` to remove only its entry.

Then open `/hooks` in Codex and trust the new hook. Until you do, Codex ignores it.

You can skip the command: the first Codex run offers to run it for you. If you decline, the plan line shows `guard=off` and the skill still works, without the guard. If you remove the skill without uninstalling, the leftover hook does nothing.

Codex's default sandbox also keeps a project's `.agents/` folder read-only, so the engine can't create its run log in `.agents/log/` until you approve running it outside the sandbox, or add that folder as a writable root. The same goes for the profile folder when a preference is saved.

## Permissions

In Claude Code the skill pre-approves its engine command through `allowed-tools`, but that covers only the turn in which the skill is invoked. To avoid a prompt at every later step, add a permanent rule to your user settings (`~/.claude/settings.json`):

```json
{
  "permissions": {
    "allow": ["Bash(python3 */science-research-writing/scripts/engine.py *)"]
  }
}
```

The rule matches the engine wherever the skill is installed. Use the full path of your install instead if you want it narrower. Codex asks for its own approvals under its sandbox settings.

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

The skill keeps your preferences in `~/.agents/science-research-writing/user-style.md`, outside the skill folder, so updating or reinstalling the skill never deletes it. The file is created the first time a preference is saved. A profile an older version left inside the skill folder is moved there once, and the skill tells you. Codex's sandbox may ask you to approve writing there.

- **Say it once:** "I always use *we*." The skill saves this at once and tells you.
- **Correct an edit:** when you reject one of its changes, it offers to save that as a preference.
- **Ask for a scan:** "Scan this sample of my writing for style preferences." Only the ones you approve are saved.
- **Edit the file yourself,** then ask "Study my style profile." The skill restates each entry, flags any that are unclear, and changes nothing without your approval.

If your profile conflicts with the journal's guidelines, the journal wins for that task. The skill lists the conflict at the end and saves your answer. The rule against inventing or overstating results always wins.

## Uninstall

Run the uninstall script before you remove the skill:

```bash
python3 ~/.agents/skills/science-research-writing/scripts/uninstall.py
```

It asks whether to delete your style profile (default: keep). Outside a terminal, pass `--keep-profile` or `--remove-profile` instead. It also removes the Codex hook and leaves the run logs in your projects' `.agents/log/` alone. At the end it prints the command that removes the skill: `npx skills remove science-research-writing -g` for an `npx skills` install, or `rm` commands for a local one. Run that command yourself.

## What's inside

- `SKILL.md`: the entry point the agent reads first.
- `references/`: one file per section, plus files for language, the review checklist, target-journal models and style-profile rules, and `workflow.json`, the routing and output templates the engine reads.
- `scripts/`: the step engine (`engine.py`), the Codex hook installer and the uninstall script.
- `tests/`: `python3 -m unittest discover -s tests`.

Each run's state, input, results, check report and output are kept in your project under `.agents/log/science-research-writing/<run id>/`. The folder is git-ignored, and the skill never writes to your own files unless you ask.

## Scope

The skill covers journal research articles only. It doesn't cover grant proposals, theses, cover letters, responses to reviewers or review articles.
