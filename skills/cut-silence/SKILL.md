---
name: cut-silence
description: Cuts silence from ONE video with auto-editor and normalizes the audio to -16 LUFS. With the `--fillers` flag, also removes filler words and stutters using word-level transcription (Brazilian Portuguese only). Triggers "cut the silences", "remove the pauses from this video", "trim the dead air", "speed this video up by cutting pauses", "corta os silêncios", "tira as pausas do vídeo", "tira os tempos mortos", "tira os né/tá do vídeo", "corta as gagueiras". Do NOT use for creative editing (choosing takes, burned-in captions, color grading, overlays, cutting by content) — this skill only removes silence and parasitic sound. If the request is vague like "edit my video", ask what exactly before triggering.
argument-hint: <video-path> [--fillers]
license: MIT
---

## What this skill does

Automatically cuts pauses and silence from talking-head videos using `auto-editor`, then normalizes the audio loudness with `ffmpeg-normalize`.

- **Cost:** $0 in default mode — the tools are free, open source and fully offline
- **Quality:** keeps the original video quality (no video re-encode during normalization, `-c:v copy`)
- **Audio:** linear EBU R128 loudness normalization (no dynamic compression, no effects) — raises quiet audio and lowers loud audio to the same perceived level, without ever clipping
- **Output:** writes the edited video to `<OUTPUT>/` (see convention below), never overwrites the original

**Optional `--fillers` mode:** also removes filler words ("né", "tá", parasitic "tipo") and stutters. Costs a few cents of API (OpenRouter) because it has to transcribe, and it is **Brazilian Portuguese only** — the judgment prompt is written in PT-BR and calibrated on it. **Never runs unless the user asks.** See "Step 5b".

---

## Path convention

This skill is portable: it works copied to any machine, without depending on any project's structure.

| Marker | Means |
|---|---|
| `<OUTPUT>` | `<folder containing the video>/edited` — created if missing. **Never** the original's folder. |
| `<SKILL-FOLDER>` | the folder this `SKILL.md` lives in. The script is at `<SKILL-FOLDER>/scripts/remove-fillers.py` |

If the user asks for a different destination, use theirs. In batch mode, keep every video in the same `<OUTPUT>`.

**Shell.** The commands below are POSIX (bash/zsh). On Windows PowerShell the equivalents are:

| POSIX | PowerShell |
|---|---|
| `test -f "$1"` | `Test-Path -PathType Leaf "$path"` |
| `rm -rf "<folder>"` | `Remove-Item -Recurse -Force "<folder>"` |
| `rm -f "<file>"` | `Remove-Item -Force "<file>"` |
| `df -h` | `Get-PSDrive -PSProvider FileSystem` |

Use the shell tool native to the environment. The `auto-editor`, `ffmpeg-normalize` and `ffprobe` calls are identical on both.

---

## Steps

### 1. Receive the file

The video path arrives as an argument: `$1`

If no argument was given, ask:
> "What's the path to the video you want to edit?"

### 2. Check dependencies

Run in the terminal:

```bash
python --version
auto-editor --version
ffmpeg -version
ffmpeg-normalize --version
```

If a Python package is missing, install it:

```bash
pip install auto-editor ffmpeg-normalize
```

If `ffmpeg` is missing, instruct per platform:

| System | Command |
|---|---|
| Windows | `winget install Gyan.FFmpeg` (or download from https://ffmpeg.org/download.html and add to PATH) |
| macOS | `brew install ffmpeg` |
| Linux (Debian/Ubuntu) | `sudo apt install ffmpeg` |

**Only for `--fillers` mode** (skip if the user didn't ask): needs `pip install openai` and an OpenRouter key in `OPENROUTER_API_KEY`, either as an environment variable or in a `.env`. The script looks for the key in the environment first and, failing that, walks up the folder tree looking for a `.env` — reading **only** `OPENROUTER_API_KEY`, never the user's other variables. Without a key it stops with an explanatory message, it doesn't crash.

Do not proceed without the dependencies.

### 3. Check the input file

Confirm the file exists before anything else:

```bash
test -f "$1" && echo "OK" || echo "FILE NOT FOUND"
```

If it doesn't exist, report:
> "File not found: `$1`. Check the path and try again."

### 4. Define the file names

- Extract the base name without extension.
- Intermediate (cut, before normalizing): `<OUTPUT>/_tmp/<base-name>.<ext>`
- Final: `<OUTPUT>/<base-name>_edited.<ext>`
- Isolated auto-editor cache: `<OUTPUT>/_tmp/cache_<base-name>/`

Example: `C:/Videos/lessons/tutorial.mp4` → `C:/Videos/lessons/edited/tutorial_edited.mp4`

### 5. Run the silence cut

```bash
auto-editor "<video-path>" \
  --edit "audio:threshold=4%" \
  --margin "0.2s" \
  --temp-dir "<OUTPUT>/_tmp/cache_<base-name>" \
  -o "<OUTPUT>/_tmp/<base-name>.<ext>" \
  --no-open
```

**Parameters explained:**
- `--edit "audio:threshold=4%"` → treats anything below 4% of peak volume as silence
- `--margin` → breathing room kept before and after each phrase (see table below)
- `--temp-dir` → cache exclusive to this video (see the parallelism guardrail below)
- `--no-open` → don't open the file automatically after export

**The margin changes with the video type.** Don't use 0.2s for everything:

| Video type | `--margin` | Why |
|---|---|---|
| Lesson, tutorial, long talking video | `0.2s` | The breathing room at the edges keeps speech natural and avoids abrupt cuts |
| **Creative, ad, VSL, short-form** | **`0.0s`** | Pacing is everything. Every 0.2s kept per phrase adds up and kills the cut; ads want speech glued together |

When in doubt between the two, ask whether it's an ad or long-form content. If the user says it feels rushed, raise the margin; if it drags, lower it.

After running, delete the cache folder: `rm -rf "<OUTPUT>/_tmp/cache_<base-name>"`.

> **Note:** The `--video-codec copy` and `--audio-codec copy` flags are **not supported** in auto-editor 29.x (they raise `Unknown encoder: copy`). Don't try to use them. auto-editor keeps quality close to the original with its default codec (h264+aac).

### 5b. Cut filler words (ONLY with `--fillers`)

**Skip this whole step if the user didn't ask.** It costs API money and takes time.

**This mode is Brazilian Portuguese only.** The transcription is pinned to `language: pt` and the judgment prompt is written in PT-BR. On English audio it produces garbage — see "Language support" below.

This step replaces steps 5 and 6, because the filler cut goes into the *same* auto-editor call as the silence cut. One encode, no quality loss from encoding twice.

**1) Analyze** (cuts nothing, just finds the fillers):

```bash
python "<SKILL-FOLDER>/scripts/remove-fillers.py" "<ORIGINAL-video-path>" --json "<output>.json"
```

Use the **original** video, never the already-cut one: the timestamps have to line up with the timeline auto-editor will receive.

The script transcribes with word-level timestamps (`openai/whisper-large-v3-turbo` via OpenRouter), detects stutters heuristically, submits the rest to an LLM for judgment, and prints each cut with its surrounding sentence.

**2) Show the list to the user and WAIT for approval.** Don't apply it on your own. Show the report exactly as the script printed it (timestamp, type, sentence with the word in brackets) and ask whether you can apply it. If they want some removed from the list, edit the `cortes` array in the JSON before continuing.

**3) Apply.** After approval, the script itself cuts and normalizes:

```bash
python "<SKILL-FOLDER>/scripts/remove-fillers.py" --aplicar "<ORIGINAL-video>" "<fillers>.json" "<output>.mp4"
```

For ad creative, pass the margin along using the same rule as the step 5 table (the `--aplicar` default is `0.2s`):

```bash
python "<SKILL-FOLDER>/scripts/remove-fillers.py" --aplicar "<video>" "<fillers>.json" "<output>.mp4" --margin 0.0s
```

**Don't hand-build the `auto-editor` call for this.** In version 29.x, `--cut-out` accepts **one range per occurrence of the flag**, despite `--help` advertising `[START,STOP ...]`. Passing several together makes it treat the last one as the input file and die with `Could not open input file: 432.42sec,432.96sec`. The right way is to repeat the flag (`--cut-out A,B --cut-out C,D ...`), which is what the script does.

Silence cut and filler cut come out in the same pass, and normalization rides along: one encode.

**Guardrails the script already applies on its own** (no need to redo them, but know they exist):
- Aborts if the judgment marks more than 15% of the words — that isn't filler, that's the LLM misunderstanding
- Refuses blocks longer than 6 consecutive words
- Protects vocatives (`pessoal`, `galera`, `gente`, `cara`) and pronouns (`eu`, `ele`, `você`): people recording talk to their audience constantly, and cutting the subject breaks the sentence ("o que ele corrigiu" becomes "o que corrigiu")
- On stutters, keeps the **last** repetition, which is the one that connects to the sentence

**If the user says it came out choppy:** the problem is almost always the volume of cuts, not the splices. Run it again without `--fillers` and compare.

### 6. Normalize the audio

Skip this step if you ran `5b` — `--aplicar` already normalized.

```bash
ffmpeg-normalize "<OUTPUT>/_tmp/<base-name>.<ext>" \
  -o "<OUTPUT>/<base-name>_edited.<ext>" \
  -c:a aac -b:a 192k \
  -t -16 -tp -1.5 \
  --auto-lower-loudness-target \
  --print-stats -f
```

**Parameters explained:**
- `-t -16` → integrated EBU R128 loudness target: -16 LUFS (standard for voice/lessons)
- `-tp -1.5` → true peak ceiling at -1.5 dBTP, never clips even when raising quiet audio
- `--auto-lower-loudness-target` → guarantees **linear** normalization (flat gain). Without this flag, audio that can't reach the target without clipping falls back automatically to **dynamic** normalization (an effect similar to a compressor) — which violates "no compression, no effects"
- `-c:a aac -b:a 192k` → re-encodes audio only; video is copied (`-c:v copy` is the tool's default, no need to pass it)
- `--print-stats` → logs how much gain was applied to each video

After a successful normalization, delete the intermediate and the scratch folder, so no junk is left in the user's folder:

```bash
rm -f "<OUTPUT>/_tmp/<base-name>.<ext>"
rmdir "<OUTPUT>/_tmp" 2>/dev/null || true   # only removes it if empty
```

### 7. Run in the background (long videos)

For videos longer than ~10 minutes the process can take a while. Run it in the background and monitor progress:

```bash
tail -f "<output-file>" | grep -E --line-buffered "%|done|error|Error|Traceback"
```

### 8. Report the result

Once finished, report:

```
✅ Video edited successfully!

📁 Original file: <original-path>
💾 Edited file:   <OUTPUT>/<edited-name>

⏱️ Original duration: X min Y sec
⏱️ Final duration:    X min Y sec
✂️  Time saved:       Z sec (N% of the video)
🔊 Audio normalized:  -16 LUFS (peak ceiling -1.5 dBTP)
```

To get the durations, use:

```bash
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "<file>"
```

---

## Language support

| Feature | Works in |
|---|---|
| Silence cut + normalization (default mode) | **Any language.** It's waveform analysis — it never looks at words |
| Stutter removal (`--fillers`) | **Any language** in principle — the heuristic just spots adjacent repeated words |
| Filler-word removal (`--fillers`) | **Brazilian Portuguese only** |

Three things pin `--fillers` to PT-BR: the transcription request hardcodes `"language": "pt"`, the judgment prompt is written in Portuguese, and the `PROTEGIDO` list protects Portuguese pronouns and vocatives. On English audio, Whisper is told to transcribe Portuguese and the protection list guards the wrong words — so the LLM can cut subjects and break sentences.

If the user has non-Portuguese audio, run the default mode and say the `--fillers` mode doesn't cover their language yet.

---

## Guardrails

- **Never overwrite the original** — output always goes to `<OUTPUT>/`, never replaces the input file.
- **Don't proceed without dependencies** — without `ffmpeg`, `auto-editor` and `ffmpeg-normalize` installed, the skill stops and instructs the user.
- **Don't invent paths** — if the file isn't found, stop and ask for the correct path.
- **Don't batch without confirmation** — if the user passes a folder instead of a file, confirm before processing them all.
- **`--fillers` never runs on its own** — the default mode is free and offline; the filler cut spends API money. It only happens if the user explicitly asks. And even then, the cut list goes to approval before being applied.
- **Filler cutting always starts from the original video** — if you transcribe the already-cut video and apply the ranges to the original (or vice versa), the timestamps don't line up and the skill cuts real speech.
- **Never run two `auto-editor` instances at once without an isolated `--temp-dir` per video** — cache collision corrupts the output (audio/video with invalid data, or worse, content mixed in from another leftover cache). To process several videos in parallel, each call needs its own `--temp-dir`, deleted right after use.
- **Check disk space before a large batch** — each video needs ~2.3x its own size free on disk (the cut intermediate and the final file coexist). Check free space before processing several large videos; if it doesn't fit, pause and ask the user to free space instead of letting ffmpeg fail halfway.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `auto-editor: command not found` | `pip install auto-editor` |
| `ffmpeg-normalize: command not found` | `pip install ffmpeg-normalize` |
| `ffmpeg: command not found` | Install ffmpeg and add it to PATH (see the step 2 table) |
| Error with `--video-codec copy` | Don't use it — the flag doesn't exist in auto-editor 29.x |
| Video with desynced audio | Don't use `copy` on videos with multiple audio tracks |
| Cuts too aggressive / feels rushed | Raise `--margin` to `0.3s` or `0.4s` |
| Creative drags, too much breathing room | Lower `--margin` to `0.0s` — that's the default for ads |
| Natural pauses being cut | Lower the threshold: `--edit "audio:threshold=2%"`. The lower the threshold, the less counts as silence. (The `--silent-threshold` flag was removed from auto-editor; it no longer exists in 29.x) |
| `Invalid NAL unit size` / `Found duplicated MOOV Atom` / decode error during normalization | The `auto-editor` cache collided with another instance running at the same time. Delete that video's `--temp-dir` and run it again alone (no parallelism) or with an exclusive `--temp-dir` |
| `--fillers`: `OPENROUTER_API_KEY nao encontrada` | Set the environment variable, or copy the skill's `.env.example` to `.env` and fill in the key |
| `--fillers`: `ABORTADO: marcou N% das palavras` | The LLM misunderstood the task. Run it again; if it repeats, the audio probably has noise/music confusing the transcription |
| `--fillers`: `transcricao voltou sem timestamps por palavra` | The chosen model doesn't support `verbose_json`. Only `openai/whisper-large-v3`, `whisper-large-v3-turbo` and `whisper-1` do. `gpt-4o-transcribe` and `qwen3-asr` return 400 |
| `--fillers`: several repeated "Obrigado" nobody said | A known Whisper hallucination in PT: it invents "Obrigado" over silent stretches. Not a script bug. Those cuts land on silence, which `--edit` would remove anyway, so they're harmless. Just don't count them as "real stutters" when reporting |
| `--fillers` on non-Portuguese audio produces garbage | Expected — the mode is PT-BR only. See "Language support" |
| Accented path not found in background Bash (Windows) | The background shell mangles accents (`Módulo` → not found). Use PowerShell for those paths |
| `Could not open input file: 432.42sec,432.96sec` | `--cut-out` takes one range per occurrence. Repeat the flag for each range, don't pass several together |
