# cut-silence

Cuts the pauses out of talking-head video and normalizes the audio. In default mode it runs **offline and free**: just `auto-editor` and `ffmpeg`, no API, no upload.

With the `--fillers` flag it also removes filler words, stutters, and **duplicate takes** — where you err, stop, and redo a segment from the top. That mode costs a few cents of API to transcribe; the judging happens in your agent, so nothing is cut without you seeing it first.

<!-- TODO: before/after demo GIF goes here.
     Record one pass of the skill on a real video and drop the file in this folder:
     ![Before and after](demo.gif) -->

## Installation

Inside Claude Code (no Node required):

```
/plugin marketplace add AndersonAdelino/skills
/plugin install adelino-skills@adelino
```

Or, if you want editable files inside your project: `npx skills add AndersonAdelino/skills`.
Or copy the `cut-silence/` folder into `.claude/skills/` in your project (or `~/.claude/skills/` for all of them).

### Dependencies — the skill handles these

You don't have to set anything up first. Ask it to cut a video and it checks what's missing, installs the Python packages itself, and offers to install `ffmpeg` for you:

| Dependency | Who does it |
|---|---|
| `auto-editor`, `ffmpeg-normalize` | **The skill installs them** |
| `ffmpeg` — Windows (`winget`) and macOS (`brew`) | **The skill offers to install it** |
| `ffmpeg` — Linux (`sudo apt`) | You run it — `sudo` needs a password the agent can't type |

> After installing ffmpeg you have to **close and reopen your terminal**. A new binary isn't on the PATH of a shell that's already running. The skill tells you this instead of reporting a phantom failure.

Prefer to do it by hand:

```bash
pip install -r requirements.txt
```

| System | Command |
|---|---|
| Windows | `winget install Gyan.FFmpeg` |
| macOS | `brew install ffmpeg` |
| Linux (Debian/Ubuntu) | `sudo apt install ffmpeg` |

Check that everything is up:

```bash
auto-editor --version && ffmpeg-normalize --version && ffmpeg -version
```

All three have to answer with a version number. If one complains:

| Error | What to do |
|---|---|
| `ffmpeg is not recognized` / `command not found` | ffmpeg installed but didn't land on PATH. **Close and reopen your terminal** — that fixes it most of the time. If it persists, add ffmpeg's `bin` folder to PATH manually |
| `pip is not recognized` | Python isn't installed or fell off PATH. Reinstall from [python.org](https://www.python.org/downloads/) with **"Add Python to PATH"** checked |
| `auto-editor is not recognized` (but `pip install` worked) | pip's scripts folder is off PATH. Work around it by running `python -m auto_editor` instead of `auto-editor` |

### Only for `--fillers` mode

Needs an [OpenRouter](https://openrouter.ai/keys) key in `OPENROUTER_API_KEY`. The safest route is an environment variable, since it creates no file that can leak:

```powershell
# Windows (PowerShell) — applies to this terminal window only
$env:OPENROUTER_API_KEY = "sk-or-..."
```

```bash
# macOS / Linux
export OPENROUTER_API_KEY="sk-or-..."
```

To avoid retyping it every session, use a `.env` — but read the warning below:

```bash
cp .env.example .env
# open .env and fill in the key
```

The script checks the environment first; failing that it walks up the folder tree looking for a `.env`. It reads **only** `OPENROUTER_API_KEY` — no other variable from your `.env` enters the process. Without a key it stops with an explanatory message, it doesn't break halfway.

> ⚠️ **If you use `.env`, make sure it's in your project's `.gitignore`.** This repository's `.gitignore` blocks `.env`, but once you install the skill inside another project, that project's `.gitignore` is the one that counts. A `.env` sitting in `.claude/skills/cut-silence/` will land in your commit if your project has no `.env` rule.
>
> Also: a `.env` placed inside the installed skill folder is **wiped by `skills update`**, since the update replaces those files. An environment variable survives updates — that's the main reason to prefer it.

## Usage

Just talk to Claude:

> cut the silences out of `C:/videos/lesson-03.mp4`

> trim the pauses and the filler words from this one: `~/recordings/live.mp4` --fillers

Or call it directly: `/cut-silence <video-path> [--fillers]`

## Where the video is saved

In an `edited/` subfolder **next to your video**. The skill has no folder of its own and writes nowhere else on your system: where the input is, that's where the output goes.

```
C:\Users\john\Downloads\
├── live.mp4                    ← your file, untouched
└── edited\
    └── live_edited.mp4         ← the result
```

Same on macOS and Linux: `~/videos/lesson.mp4` becomes `~/videos/edited/lesson_edited.mp4`.

Three guarantees the skill takes seriously:

- **The original is never overwritten.** The output always has a different name and folder
- During processing an `edited/_tmp/` appears with the intermediate file. It is **deleted at the end**, folder included
- If you want a different destination, just say so: "save it to `D:/done`" and it uses yours

## What comes out the other side

- Silence and pauses removed (`--edit audio:threshold=4%`, with `0.2s` of breathing room at the edges)
- Audio normalized to **-16 LUFS** with a peak ceiling at **-1.5 dBTP**, via **linear** EBU R128 loudness — raises quiet audio without clipping and **without a compressor**, so the dynamics of the voice stay intact
- Video not re-encoded during the normalization step (`-c:v copy`)

## Adjustments worth making

| Situation | What to change |
|---|---|
| Lesson, tutorial, long video | `--margin 0.2s` (default) |
| Ad, VSL, short-form | `--margin 0.0s` — every kept breath kills the pacing |
| Came out too rushed | Raise the margin to `0.3s` or `0.4s` |
| It's eating natural pauses | Lower the threshold: `--edit "audio:threshold=2%"` |

### Cut strength

`--margin` is the strength knob, and **the scale is inverted**: a smaller margin cuts harder. You don't have to remember the numbers — just ask in words and the skill translates:

| Say this | You get |
|---|---|
| "cut it softer" / "it felt rushed" | `0.3s` |
| nothing — lesson or tutorial | `0.2s` |
| "a bit tighter" | `0.1s` |
| "cut it as tight as possible" / ad, VSL | `0.0s` |

Any value in between works too. If you name a number, it uses yours.

## How `--fillers` works

The API only transcribes. **Everything that requires judgment happens in your agent** — not in a remote model behind a prompt. That's cheaper, works in any language, and lets you argue with a cut in conversation instead of hand-editing JSON.

```
     YOU                    SCRIPT                    API                   AGENT
      │                       │                        │                      │
  "cut the ───────────────►  │                        │                      │
   fillers"              extract audio                 │                      │
                         (ffmpeg)                      │                      │
                             │                         │                      │
                        show estimated ───► "12.4 min · $0.053 · nova-3"      │
                           cost                        │                      │
                             │────── transcribe ──────►│                      │
                             │◄─── words + timings ────│                      │
                             │                         │                      │
                      find mechanical                  │                      │
                       candidates:                     │                      │
                       · stutters                      │                      │
                       · duplicates                    │                      │
                             │                         │                      │
                          cuts.json ───────────────────────────────────────►  │
                                                                        1. fix ASR
                                                                        2. judge fillers
                                                                        3. confirm duplicates
      │◄────────────── grouped report ──────────────────────────────────────  │
      │
  you approve
   or object
      │──────────────────────────────────────────────────────────────────►   │
                             │◄──────── approved cuts ──────────────────────  │
                             │
                    auto-editor: silence + cuts
                    ffmpeg-normalize: -16 LUFS
                             │
                             ▼
                      video_edited.mp4
```

**Nothing is cut without your approval.** The report groups cuts by type, with counts, and for duplicates it prints the full text of what leaves and what stays — you can't approve a 5-second cut from a timestamp alone.

### The three things it detects

| Type | What it is | Example |
|---|---|---|
| **Filler** | Parasitic sound that leaves without changing meaning | "e aí **né** a gente vai" |
| **Stutter** | Word repeated glued to itself | "hoje **hoje** eu vou falar" |
| **Duplicate** | Abandoned take — the speaker erred, stopped, and redid the segment from the top | "Fala pessoal, hoje eu vou…" → *(pause)* → "Olá pessoal, Anderson aqui" |

Stutters and duplicates are found mechanically (free, deterministic, unit-tested). Duplicate detection is anchored on **pauses**: people stop before they restart, so a word not preceded by a ≥0.35s pause can't begin a new take. That anchor is what keeps it from flagging every sentence that happens to end the same way.

### Transcription model and cost

Default: **`deepgram/nova-3`** via OpenRouter. Deepgram derives word timing frame by frame from the acoustic model; Whisper infers it with DTW over cross-attention, which [varies by 100–400 ms](https://arxiv.org/pdf/2408.16589) for the same audio — enough for a cut to clip the next word.

| Video length | `deepgram/nova-3` (default) | `microsoft/mai-transcribe-2` | `openai/whisper-large-v3-turbo` |
|---|---|---|---|
| 10 min | **$0.043** | $0.017 | $0.002 |
| 30 min | **$0.129** | $0.050 | $0.005 |
| 60 min | **$0.258** | $0.100 | $0.011 |

Switch with `--modelo <id>`. Nova-3 costs the most on this list and it's still 26 cents for an hour of video — pick on timestamp quality, not price. Deepgram also gives **$200 in free credit** to new accounts, around 640 hours of transcription.

The script prints the estimate **before** spending anything, so you can back out.

### Running it by hand

```bash
# 1. transcribe + find candidates (cuts nothing)
python scripts/remove-fillers.py video.mp4 --json cuts.json

# 2. the agent reads cuts.json, judges, and shows you the report

# 3. apply the approved ranges
python scripts/remove-fillers.py --aplicar video.mp4 approved.json output.mp4
# for ads, glue the speech together:  --margin 0.0s
```

Guardrails the script enforces no matter what the agent decides:

- Refuses blocks longer than **6 consecutive words** — except duplicates, long by nature
- Protects vocatives (`pessoal`, `galera`, `gente`) and pronouns (`eu`, `ele`, `você`) from filler judgment
- On stutters, keeps the **last** repetition, the one that connects to the sentence

Self-test every heuristic, offline and free:

```bash
python scripts/remove-fillers.py --autoteste
```

## Language support

| Feature | Works in |
|---|---|
| Silence cut + normalization (default mode) | **Any language.** It's waveform analysis — it never looks at words |
| Stutter and duplicate detection | **Any language.** Both are mechanical: repeated tokens and pause-anchored echoes |
| Filler judgment | **Any language** — your agent judges, and it isn't tied to one |

Moving the judgment out of a remote LLM removed the old Portuguese-only limitation: there's no PT-BR prompt to calibrate anymore.

Two Portuguese-specific bits remain, both small:

- The transcription request still sends `"language": "pt"`
- The protected-word list holds Portuguese vocatives and pronouns, so other languages aren't guarded against losing a subject

Non-Portuguese `--fillers` is usable but unpolished until those are parameterized.

## Known limits

- Transcription is still pinned to `language: pt`; other languages need that made configurable
- ASR models hallucinate "Obrigado" over silent stretches in PT. Since those land on silence, which `--edit` removes anyway, they're harmless
- Duplicate detection needs a real pause before the restart. A speaker who redoes a line without stopping won't be caught
- `--video-codec copy` / `--audio-codec copy` don't exist in `auto-editor` 29.x (they raise `Unknown encoder: copy`)
- Running two `auto-editor` processes in parallel without separate `--temp-dir`s corrupts the output
- Each video needs ~2.3x its own size free on disk during processing

## Tested with

`auto-editor` 29.3.1 · `ffmpeg-normalize` 1.42.0 · Python 3.12 · Windows 11

## License

MIT.
