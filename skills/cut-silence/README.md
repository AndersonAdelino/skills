# cut-silence

Cuts the pauses out of talking-head video and normalizes the audio. In default mode it runs **offline and free**: just `auto-editor` and `ffmpeg`, no API, no upload.

With the `--fillers` flag it also removes filler words and stutters using word-level transcription. That mode costs a few cents of API and is **Brazilian Portuguese only** — see [Language support](#language-support).

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

### Dependencies

**This is where most people get stuck, not the skill install.** Two things: the Python packages and `ffmpeg`.

```bash
pip install -r requirements.txt
```

And `ffmpeg` (with `ffprobe`) on your PATH:

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

## How `--fillers` works

1. **Analyze** — transcribes with `openai/whisper-large-v3-turbo` (word-level timestamps), catches stutters heuristically and submits the rest to an LLM for judgment
2. **Shows the list and waits for your OK** — nothing is cut without approval. Each cut shows up with its timestamp and the sentence around it
3. **Apply** — silence cut and filler cut come out in the same `auto-editor` pass, with normalization along for the ride: one encode

```bash
# 1. analyze (cuts nothing)
python scripts/remove-fillers.py video.mp4 --json fillers.json

# 2. review the list, edit the "cortes" array in the JSON to drop any you want to keep

# 3. apply
python scripts/remove-fillers.py --aplicar video.mp4 fillers.json output.mp4
# for ads, glue the speech together:  --margin 0.0s
```

The script refuses to do anything stupid on its own:

- Aborts if the judgment marks more than **15%** of the words (that isn't filler, that's the LLM misunderstanding)
- Refuses blocks longer than **6 consecutive words**
- Protects vocatives (`pessoal`, `galera`, `gente`) and pronouns (`eu`, `ele`, `você`) — cutting the subject breaks the sentence
- On stutters, keeps the **last** repetition, the one that connects to the sentence

Self-test the heuristics without spending API money:

```bash
python scripts/remove-fillers.py --autoteste
```

## Language support

| Feature | Works in |
|---|---|
| Silence cut + normalization (default mode) | **Any language.** It's waveform analysis — it never looks at words |
| Stutter removal (`--fillers`) | **Any language** in principle — the heuristic just spots adjacent repeated words |
| Filler-word removal (`--fillers`) | **Brazilian Portuguese only** |

Three things pin `--fillers` to PT-BR: the transcription request hardcodes `"language": "pt"`, the judgment prompt is written in Portuguese, and the protected-word list guards Portuguese pronouns and vocatives. Point it at English audio and Whisper is told to transcribe Portuguese while the protection list guards the wrong words — so the LLM can cut subjects and break sentences.

**If your audio isn't Portuguese, use the default mode.** It's the bulk of the value, it's free, and it's language-agnostic. English support for `--fillers` is on the list.

## Known limits

- Filler judgment is **PT-BR only** — the prompt is written and calibrated in Brazilian Portuguese
- Whisper hallucinates "Obrigado" over silent stretches in PT. Since those cuts land on silence, which `--edit` would remove anyway, they're harmless
- `--video-codec copy` / `--audio-codec copy` don't exist in `auto-editor` 29.x (they raise `Unknown encoder: copy`)
- Running two `auto-editor` processes in parallel without separate `--temp-dir`s corrupts the output
- Each video needs ~2.3x its own size free on disk during processing

## Tested with

`auto-editor` 29.3.1 · `ffmpeg-normalize` 1.42.0 · Python 3.12 · Windows 11

## License

MIT.
