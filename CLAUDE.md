# CLAUDE.md

Instructions for any agent working in this repository.

This is a **skills factory**. What ships here gets installed on other people's
machines and runs with full agent permissions against their files.

## Where the knowledge lives

| Question | Read |
|---|---|
| How does skill X work, what are its parameters | `skills/<name>/SKILL.md` — the source of truth for that skill |
| Has this failed before | **[MISTAKES.md](MISTAKES.md)** |
| What does it do for a user | `skills/<name>/README.md` |

**Read MISTAKES.md before changing parameters, heuristics, or a batch path.**
Every entry is a bug that already shipped. It also names the recurring patterns
behind them — read those first; they apply to skills that don't exist yet.

## Layout

```
skills/<name>/SKILL.md          the skill
skills/<name>/scripts/          its scripts, self-contained
.claude-plugin/plugin.json      list every new skill path here
README.md                       one row per skill in the table
```

Flat, one folder per skill. **Don't nest them under `ready/` and `wip/`** — the
installer scans recursively and finds a skill wherever it sits, so the folder
hides nothing (tested: a skill under `skills/wip/` installs just fine). All it
would buy is a path change the day a skill graduates, breaking its `plugin.json`
entry, its README link, and the install of anyone who already had it.

## Is a skill ready?

**`plugin.json` is the manifest of what ships.** A skill missing from its `skills`
array is not finished, whatever state its folder is in. That is the signal to read
before deciding whether to commit, publish, or announce something — and it is the
only one that is both explicit and machine-readable.

What actually keeps unfinished work out of people's hands is the branch: anything
unmerged simply isn't in the repo they install from. The manifest says *ready*;
the branch is what *enforces* it.

A new skill touches three places: its folder, `plugin.json`, the README table.
Adding the `plugin.json` line is what declares it done — do it last, not first.

## Development loop

`.claude/skills/<name>` is a **junction** into `skills/<name>`, so an edit here is
live immediately. It is gitignored — git follows junctions and would commit every
file twice.

```powershell
New-Item -ItemType Junction -Path ".claude\skills\NOME" -Target "skills\NOME"
```

Symlinks need admin on Windows; junctions don't.

`~/.claude/skills/` and the plugin cache are **separate installed copies** that
lag behind this repo. Before testing anything serious, work inside the repo or
run `npx skills update <name> -g -y`.

## Before committing

```bash
python scripts/validar-skills.py            # invariantes do repo
python skills/<name>/scripts/<script>.py --autoteste
```

`validar-skills.py` confere o que não aparece lendo diff: frontmatter que o
YAML aceita, e toda skill presente no `plugin.json`, no README e no CI.

**Um `: ` solto dentro da `description` faz a skill parar de carregar**, sem
erro nenhum — ela só some da lista. Use `description: >-` e quebre o texto
indentado abaixo; aí dois-pontos, aspas e acento passam sem escapar.

Non-trivial logic leaves one runnable check behind. When a real bug is fixed,
**the real case becomes the test**, with its actual numbers — so nobody loosens a
limit later without the test failing.

## Git

`master` is what `npx skills add` and `/plugin marketplace add` install from.
**It is the product, not a workspace.** Never push something you haven't run.

Untested work goes on a branch — per *change*, not per skill, since skills are
independent folders and never conflict:

```powershell
git switch -c feat/nome
# test it
git switch master; git merge feat/nome; git push
```

No branch protection: it's a control for teams, and gating on a CI that only runs
unit tests would grant false confidence. CI runs `--autoteste` on every push and
touches no API and no real media — a green check is a narrow signal.

## PowerShell traps (Windows)

| Trap | Do this instead |
|---|---|
| `git commit -m @'...'@` breaks when the message has double quotes | write to a file, `git commit -F` |
| `Get-Content`/`Set-Content` on PS 5.1 mangle UTF-8 accents | `[System.IO.File]::ReadAllText/WriteAllText` with explicit UTF-8 |
| `tail -f` holds the handle; the writer then fails silently | read open-and-close: `Select-String -Path <log> -Pattern ...` |
| `-Encoding utf8` writes a BOM | read config files as `utf-8-sig` |

## Conventions

Repo, docs and skill names are in **English** — the audience is the wider
ecosystem. Where a skill is calibrated for one language, that belongs in its own
SKILL.md, not here.

Each SKILL.md `description:` is the surface matched against what the user says.
Write it in the language the user will speak, and in both when the audience is
split.
