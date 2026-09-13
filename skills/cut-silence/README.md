# cut-silence

**The dead air, the "ums", the takes you restarted — gone. And the cuts land where an editor would put them.**

Point it at a talking-head video. It removes the silence, and on request the filler words, the stutters, and the moments you flubbed a line and started the sentence over. Default mode runs **offline and free** — no API, no upload, your footage never leaves the machine.

```
12.2 min  ─────────────────────────────────────►  9.0 min
          silence · 13 "ok?" · 3 stutters · 11 restarts
```

## Why the cuts don't sound cut

Most auto-editors ask *what* to remove. The hard part is *where the scissors touch*.

A transcription model says "the word ends at 149.20s". That is an **estimate**. Miss by three hundredths and you leave a shard of the word behind — the classic robotic stutter of automated editing. One real `"ok?"` in our test footage was **0.16 seconds long**: about ten frames. There is no room for error at that size.

So this skill doesn't trust the timestamp. It looks at the **waveform**.

```
          the ASR says the word ends here
                        │
                        ▼
   ▁▂▅█▇█▅▃▂▁▁▁▂▄▇█▇▅▃▂▁▁▁▁▁▂▃▅█▇█▆▄▂▁
   └──── "ativos" ────┘   └─ "ok?" ─┘ └── "É a mesma..." ──┘
                            ▲      ▲
                            │      └── and here
                     cut here ──────┘
                     ( the valley — where the sound actually stops )
```

Every cut boundary slides up to **150 ms** to land on the point of lowest energy nearby. Not where a model *thinks* the word ended — where the audio is genuinely quiet.

That is what a human editor does, and it is why the splices don't click, clip, or chop a syllable in half.

## It doesn't cut the same everywhere

Every other tool gives you **one** tightness setting for the whole video. But nobody edits that way:

```
   ┌─ inside a sentence ──────────┐   almost no air
   │  "…um perfil no Facebook▏que ▏que é importante…"
   └──────────────────────────────┘

   ┌─ between sentences ──────────┐   the pause IS the punctuation
   │  "…melhor para você.▏▏▏ Então prioriza…"
   └──────────────────────────────┘

   ┌─ new topic ──────────────────┐   the pause IS the paragraph
   │  "…você já vai entender.▏▏▏▏▏▏ Vou abrir aqui…"
   └──────────────────────────────┘
```

Tight everywhere and a lesson gets chopped into pieces. Loose everywhere and it drags.

The transcript knows where sentences end — words come back punctuated. So the skill cuts tight *inside* sentences and **hands the air back at the boundaries**, using a longer pause where the speaker turns to a new subject.

On a real 12-minute lesson: **61 breathing points preserved, 31 of them topic turns.** Thirty-one places where a single number would have been wrong.

## It checks its own work

Cutting is easy. Knowing the cut *landed* is the part everyone skips.

After editing, the skill **transcribes the result and reads it back**: did those 13 `"ok?"` actually disappear? Did the restarted take really go? Anything that survived gets reported — instead of a green checkmark over a file nobody verified.

Same for the numbers. Duration, percentage, loudness, peak: all **measured on the delivered file**, never copied from the command that asked for them.

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

- Silence and pauses removed, with every boundary snapped to the waveform valley
- Audio at **-14 LUFS** — the YouTube reference, not the podcast one. YouTube only ever turns loud uploads *down*; ship quieter than -14 and you play quieter than everything around you, forever
- Peak ceiling **-1.0 dBTP** via linear gain plus a limiter. The limiter shaves transients (mouse clicks, keyboard) — **the dynamics of your voice are never compressed**
- The loudness is **measured on the delivered file**. If it lands more than 1 LU off target, the skill says so instead of repeating the number it asked for
- Video never re-encoded during normalization (`-c:v copy`)
- **Your original is never touched.** Output goes to a separate folder, always

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
                    snap every boundary to
                    the waveform valley
                             │
                    auto-editor: silence + cuts
                    gain + limiter → -14 LUFS
                             │
                    measure the result, report
                    what it actually is
                             │
                             ▼
                      video_edited.mp4
                             │
      │◄──── "these cuts landed, these didn't" ◄─ transcribe it back ───────  │
```

**Nothing is cut without your approval.** The report groups cuts by type, with counts, and for duplicates it prints the full text of what leaves and what stays — you can't approve a 5-second cut from a timestamp alone.

### The three things it detects

| Type | What it is | Example |
|---|---|---|
| **Filler** | Parasitic sound that leaves without changing meaning | "e aí **né** a gente vai" |
| **Stutter** | Word repeated glued to itself | "hoje **hoje** eu vou falar" |
| **Duplicate** | Abandoned take — you erred, stopped, and redid the segment from the top | "Fala pessoal, hoje eu vou…" → *(pause)* → "Olá pessoal, Anderson aqui" |

That third one is the one other tools don't have, and it's the one that saves the most time.

### How it finds a restart

Searching for repeated text doesn't work. Watch:

```
   "Fala pessoal,  hoje eu vou falar…"   ▏ ONE word in common
   "Olá  pessoal,  Anderson aqui"        ▏ → needs a SHORT comparison

   "Ok,    parece muita coisa mas não é" ▏ FIRST word differs
   "Certo, parece muita coisa mas não é" ▏ → needs a LONG one
```

Compare two words and the second case scores 0.74 and slips past. Compare six and the first never matches at all. **No fixed size works**, which is why so few tools attempt this.

So it starts somewhere else — **the pause**:

```
   ────speech────  ▎ silence ▎  ────speech────
                   └─ 0.35s ─┘
                        ▲
        nobody restarts without stopping first
```

Only a word preceded by real silence can begin a new take. From each of those points it looks backwards at four different comparison lengths and keeps the best match. The pause anchor is what lets the comparison be short without flagging every sentence that happens to end the same way.

Then **you** decide. Each candidate is shown with the full text of what leaves and what stays, because a five-second cut can't be approved from a timestamp. The rule the skill applies:

> Second version **adds information** → deliberate emphasis, keep both.
> Second version **says the same thing better** → restart, cut the first.

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

Stated plainly, because every one of these was found the hard way:

- Transcription is pinned to `language: pt`; other languages need that made configurable
- ASR models hallucinate "Obrigado" over silent stretches in PT. Those land on silence the cut removes anyway, so they're harmless
- Duplicate detection needs a **real pause** before the restart. Someone who redoes a line without stopping won't be caught
- It's deliberately permissive and **will propose false positives** — that's the design. Recall is mechanical and free; precision comes from you reading the text before anything is applied. A restart longer than 15s is rejected outright: nobody rambles for half a minute, notices, and starts over
- Restarts with **no repeated words at all** ("…deixa eu explicar de outro jeito") aren't detected yet
- Breaths are treated as sound, not as a separate thing to remove
- Cut points are chosen from the audio only. If you're on camera, a cut can still land mid-gesture
- `--video-codec copy` / `--audio-codec copy` don't exist in `auto-editor` 29.x (they raise `Unknown encoder: copy`)
- Running two `auto-editor` processes in parallel without separate `--temp-dir`s corrupts the output
- Each video needs ~2.3x its own size free on disk during processing

## Tested with

`auto-editor` 29.3.1 · `ffmpeg-normalize` 1.42.0 · Python 3.12 · Windows 11

## License

MIT.
