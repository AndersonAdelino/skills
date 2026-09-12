# CLAUDE.md

Instructions for any agent working in this repository.

This is a **skills factory**: the skills published here get installed on other
people's machines and run with full agent permissions against their files. A bug
here is a bug on a stranger's video library.

**Read [MISTAKES.md](MISTAKES.md) before changing audio parameters, detection
heuristics, or anything in a batch path.** Every entry in it is a bug that
already shipped once. It is not decoration.

## The pattern that causes most bugs here

> **A fixed parameter assumed to be valid for variable input.**

Half the failures in MISTAKES.md are the same shape: a constant that worked on
the file it was tuned against, silently wrong on the next one.

- `threshold=4%` — absolute, destroyed a quiet recording (163s → 2.7s)
- `-16 LUFS` — podcast target on YouTube output
- `--auto-lower-loudness-target` — fine at 1 dB of gain, abandoned the target at 30
- `margin 0.1s` — ad pacing applied to a lesson
- a 3-word probe — missed the exact case the feature was built for

Before hardcoding a number, ask what input would make it wrong, and whether the
code would *notice*. Most of these were invisible because nothing measured the
result.

## Never report a number you did not measure

Duration, percentage cut, loudness, peak — probe the delivered file. A batch of
18 lessons was reported at "-14 LUFS" because -14 was in the command; measured,
they ranged from -17.8 to -27.1. The command asks; only the measurement knows.

A broken file exits zero and looks like a finished job.

## Layout

```
skills/<name>/SKILL.md          the skill itself
skills/<name>/scripts/          its scripts, self-contained
.claude-plugin/plugin.json      list every new skill path here
README.md                       one row per skill in the table
```

A new skill touches three places: its folder, `plugin.json`, and the README table.

## Development loop

`.claude/skills/<name>` is a **junction** into `skills/<name>`, so a skill edited
here is live immediately — no push, no `skills update`. It is gitignored; git
follows junctions and would commit every file twice.

New skill:

```powershell
New-Item -ItemType Junction -Path ".claude\skills\NOME" -Target "skills\NOME"
```

Symlinks need admin on Windows; junctions do not.

Note that `~/.claude/skills/` and the plugin cache are **separate installed
copies** and lag behind this repo. When testing anything serious, either work
inside this repo or run `npx skills update <name> -g -y` first.

## Before committing

```bash
python skills/<name>/scripts/<script>.py --autoteste
```

Non-trivial logic leaves one runnable check behind. When a real-world bug is
fixed, **the real case becomes the test** — with its actual numbers, so nobody
loosens the limit later without the test failing.

## Git

`master` is what `npx skills add` and `/plugin marketplace add` install from.
**It is the product, not a workspace.** Never push something you have not run.

Work that is not yet tested goes on a branch:

```powershell
git switch -c feat/nome
# test it
git switch master; git merge feat/nome; git push
```

Branch per *change*, not per skill — skills are independent folders and never
conflict. No branch protection: it is a control for teams, and gating on a CI
that only runs unit tests would grant false confidence.

CI runs `--autoteste` on every push. It does **not** touch the API or any real
media, so a green check is a narrow signal.

## PowerShell traps (Windows)

| Trap | Do this instead |
|---|---|
| `git commit -m @'...'@` breaks when the message contains double quotes | write the message to a file, `git commit -F` |
| `Get-Content` / `Set-Content` on PS 5.1 read UTF-8 as ANSI and mangle accents (`silêncios` → `silÃªncios`) | `[System.IO.File]::ReadAllText/WriteAllText` with explicit UTF-8 |
| `tail -f` holds the file handle; the writer then fails silently | read the log open-and-close: `Select-String -Path <log> -Pattern ...` |
| `-Encoding utf8` writes a BOM | read `.env`-style files as `utf-8-sig` |

## Language

Repo, docs and skill names are in **English** — the audience is the wider
ecosystem. `remove-fillers.py` stays in Portuguese on purpose, documented in its
docstring: the `--fillers` mode was calibrated for PT-BR speech.

The `description:` in each SKILL.md frontmatter is **bilingual on purpose**. It
is the surface matched against what the user says, and this audience says both
"cut the silences" and "corta os silêncios".
