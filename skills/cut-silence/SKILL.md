---
name: cut-silence
description: Cuts silence from ONE video with auto-editor and normalizes the audio to -16 LUFS. With the `--fillers` flag, also removes filler words, stutters and duplicate takes (the speaker restarting a segment after an error), using word-level transcription plus agent judgment. Triggers "cut the silences", "remove the pauses from this video", "trim the dead air", "speed this video up by cutting pauses", "corta os silêncios", "tira as pausas do vídeo", "tira os tempos mortos", "tira os né/tá do vídeo", "corta as gagueiras". Do NOT use for creative editing (choosing takes, burned-in captions, color grading, overlays, cutting by content) — this skill only removes silence and parasitic sound. If the request is vague like "edit my video", ask what exactly before triggering.
argument-hint: <video-path> [--fillers]
license: MIT
---

## What this skill does

Automatically cuts pauses and silence from talking-head videos using `auto-editor`, then normalizes the audio loudness with `ffmpeg-normalize`.

- **Cost:** $0 in default mode — the tools are free, open source and fully offline
- **Quality:** keeps the original video quality (no video re-encode during normalization, `-c:v copy`)
- **Audio:** linear EBU R128 loudness normalization (no dynamic compression, no effects) — raises quiet audio and lowers loud audio to the same perceived level, without ever clipping
- **Output:** writes the edited video to `<OUTPUT>/` (see convention below), never overwrites the original

**Optional `--fillers` mode:** also removes filler words ("né", "tá", parasitic "tipo"), stutters, and duplicate takes — where the speaker errs, stops, and redoes a segment from the top. Costs a few cents of API (OpenRouter) because it has to transcribe. **Never runs unless the user asks.** See "Step 5b".

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

If `ffmpeg` is missing, **offer to install it and run the command yourself** once the user says yes. Don't just paste the command and walk away — this is the step most people get stuck on.

| System | Command | Run it yourself? |
|---|---|---|
| Windows | `winget install Gyan.FFmpeg` | Yes. May raise a UAC prompt the user has to accept |
| macOS | `brew install ffmpeg` | Yes. No elevation needed |
| Linux (Debian/Ubuntu) | `sudo apt install ffmpeg` | **No** — `sudo` wants a password you can't type. Give the command and let the user run it |

**After a successful install, do NOT re-run `ffmpeg -version` and conclude it failed.** A newly installed binary is not on the PATH of an already-running shell, so the check will fail even though the install worked. That false negative is the single most confusing moment for a beginner.

Do this instead: confirm the binary is on disk, then ask for a restart.

```bash
# Windows
where.exe ffmpeg 2>nul || dir /s /b "%LOCALAPPDATA%\Microsoft\WinGet\Packages\*ffmpeg.exe" 2>nul
# macOS / Linux
command -v ffmpeg || ls -1 /opt/homebrew/bin/ffmpeg /usr/local/bin/ffmpeg 2>/dev/null
```

Found on disk but not on PATH → tell the user plainly:

> ffmpeg foi instalado. **Feche e abra o terminal** (ou o Claude Code) e me peça de novo — o PATH só atualiza numa sessão nova.

Then stop. Don't try to work around the stale PATH by calling ffmpeg with an absolute path: `auto-editor` and `ffmpeg-normalize` also look for it on the PATH, so the next step would fail anyway.

**Only for `--fillers` mode** (skip if the user didn't ask): needs an OpenRouter key in `OPENROUTER_API_KEY`, either as an environment variable or in a `.env`. No extra Python package — the transcription request goes out over the stdlib. The script looks for the key in the environment first and, failing that, walks up the folder tree looking for a `.env` — reading **only** `OPENROUTER_API_KEY`, never the user's other variables. Without a key it stops with an explanatory message, it doesn't crash.

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

### 5. Level the audio, THEN cut the silence

**Normalize before cutting. This order is not optional.**

`auto-editor`'s threshold is **absolute** — 4% of full scale, roughly -28 dB — not relative to the file's own peak. A quietly recorded video has its entire speech below that line, so the cut deletes the talking and keeps nothing.

This is not hypothetical. A real batch hit it: a lesson recorded at `mean_volume -48.2 dB` had **0.8%** of its frames above the threshold, and a 163-second video came out at 2.7 seconds. After leveling first, 81.5% of frames cleared the same threshold and the cut was normal.

```bash
# 1. level the input so the fixed threshold means something
ffmpeg-normalize "<video-path>" \
  -o "<OUTPUT>/_tmp/pre_<base-name>.<ext>" \
  -c:a aac -b:a 192k \
  -t -16 -tp -1.5 \
  --auto-lower-loudness-target -f

# 2. cut the silence from the LEVELED file
auto-editor "<OUTPUT>/_tmp/pre_<base-name>.<ext>" \
  --edit "audio:threshold=4%" \
  --margin "0.2s" \
  --temp-dir "<OUTPUT>/_tmp/cache_<base-name>" \
  -o "<OUTPUT>/_tmp/<base-name>.<ext>" \
  --no-open
```

Delete `pre_<base-name>.<ext>` once auto-editor is done.

This costs two audio passes, not two video encodes: `ffmpeg-normalize` copies the video stream (`-c:v copy`), so `auto-editor` remains the only re-encode.

**You still normalize again in step 6.** Removing silence raises the integrated loudness of what's left, so the file has drifted off -16 LUFS by the time the cut is done.

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

**Careful: the scale is inverted.** A *smaller* margin is a *stronger* cut. When the user asks for cut strength in words, translate with this table — don't reason about it from scratch, it's easy to get backwards:

| The user says | `--margin` |
|---|---|
| "softer", "gentler", "leave some breathing room", "it felt rushed" | `0.3s` |
| "normal", nothing said, lesson or tutorial | `0.2s` (default) |
| "tighter", "a bit stronger" | `0.1s` |
| "strongest", "as tight as possible", "glue the speech", ad or VSL | `0.0s` |

These are starting points on a continuous knob, not fixed presets: any value in between is valid. If the user names a number, use theirs.

After running, delete the cache folder: `rm -rf "<OUTPUT>/_tmp/cache_<base-name>"`.

> **Note:** The `--video-codec copy` and `--audio-codec copy` flags are **not supported** in auto-editor 29.x (they raise `Unknown encoder: copy`). Don't try to use them. auto-editor keeps quality close to the original with its default codec (h264+aac).

### 5b. Cut filler words (ONLY with `--fillers`)

**Skip this whole step if the user didn't ask.** It costs API money and takes time.

**The script does not judge fillers. You do.** It only transcribes and finds the mechanical candidates; deciding what is parasitic speech is your job, following the steps below. That is cheaper than a remote LLM, works in any language, and lets the user argue with a cut in conversation instead of editing JSON by hand.

This step replaces steps 5 and 6, because the filler cut goes into the *same* auto-editor call as the silence cut. One encode, no quality loss from encoding twice.

#### 1) Transcribe and collect candidates

```bash
python "<SKILL-FOLDER>/scripts/remove-fillers.py" "<ORIGINAL-video-path>" --json "<output>.json"
```

Use the **original** video, never the already-cut one: the timestamps have to line up with the timeline auto-editor will receive.

The script prints the estimated cost **before** spending it, transcribes with `deepgram/nova-3` via OpenRouter, and writes a JSON with every word (`i`, `word`, `start`, `end`) plus two candidate lists: `gagueiras` and `duplicatas`.

If the model returns no word timestamps, the script says so and suggests `--modelo microsoft/mai-transcribe-2`. Pass it along and re-run.

#### 2) Read the JSON and fix the transcript

Before judging anything, correct what the ASR misheard — tool names, jargon, proper nouns (`Cloud Code` → `Claude Code`, `N8N` → `n8n`). Do this in your head, for your own judgment; don't rewrite the JSON. A wrong word leads to a wrong cut decision.

Whisper-family models hallucinate "Obrigado" over silent stretches in PT. If you see repeated thank-yous nobody said, ignore them — they land on silence that `--edit` removes anyway.

#### 3) Decide the cuts, in three categories

- **Fillers** — parasitic sound that can leave without changing meaning: "né", "hum", "ahn", hesitant "é é é", "tipo" meaning "sort of" (not the category sense), confirmation "tá?" at the end of a sentence. **Never cut** vocatives the speaker aims at the audience (`pessoal`, `galera`, `gente`), connectives that carry reasoning (`então`, `aí`, `olha`, `bom`, `agora`), or any word whose removal breaks the sentence. When in doubt, keep it — a stray "né" is cheap; a missing subject ruins the take.
- **Stutters** — the `gagueiras` list. Already precise; just sanity-check a few.
- **Duplicates** — the `duplicatas` list. **Confirm each one by reading the text**, because these cuts are long. A genuine restart is the speaker abandoning a take and redoing it. A deliberate recap, a returning topic, or a catchphrase the speaker always uses is *not* a duplicate and must stay.

#### 4) Show the grouped report and WAIT for approval

Never apply on your own. Print it in this shape:

```
72 palavras · 1.2 min de fala · deepgram/nova-3 · transcrição $0.005

CORTES PROPOSTOS: 14   (8.3s, 11.4% da fala)
   9 vícios de linguagem   (2.1s)
   3 gagueiras             (0.9s)
   2 duplicatas            (5.3s)

── VÍCIOS DE LINGUAGEM (9) ─────────────
    12.40s  → e aí [né] a gente vai
    ...
── GAGUEIRAS (3) ──────────────────────
    31.02s  → hoje [hoje] eu vou falar
── DUPLICATAS (2) ─────────────────────
    45.10s  (4.2s, similaridade 0.86)
      SAI:  Fala pessoal hoje eu vou falar
      FICA: Olá pessoal Anderson aqui
```

For duplicates, always print the **full text** of what leaves and what stays. The user cannot approve a 5-second cut from a timestamp alone.

Then ask. If they disagree with any cut, drop it and re-print — don't make them edit JSON.

#### 5) Write the approved cuts and apply

Write a JSON with only `{"cortes": [[start, end], ...]}` — the approved ranges, in seconds — then:

```bash
python "<SKILL-FOLDER>/scripts/remove-fillers.py" --aplicar "<ORIGINAL-video>" "<cuts>.json" "<output>.mp4"
```

For ad creative, pass the margin along using the same rule as the step 5 table (the `--aplicar` default is `0.2s`):

```bash
python "<SKILL-FOLDER>/scripts/remove-fillers.py" --aplicar "<video>" "<cuts>.json" "<output>.mp4" --margin 0.0s
```

**Don't hand-build the `auto-editor` call for this.** In version 29.x, `--cut-out` accepts **one range per occurrence of the flag**, despite `--help` advertising `[START,STOP ...]`. Passing several together makes it treat the last one as the input file and die with `Could not open input file: 432.42sec,432.96sec`. The right way is to repeat the flag (`--cut-out A,B --cut-out C,D ...`), which is what the script does.

Silence cut and filler cut come out in the same pass, and normalization rides along: one encode.

**Guardrails the script enforces mechanically** (you can't override them, and shouldn't try):
- Refuses blocks longer than 6 consecutive words — except duplicates, which are long by nature
- Protects vocatives and pronouns from filler judgment; stutters and duplicates are exempt, because the word survives in the other occurrence
- On stutters, keeps the **last** repetition, the one that connects to the sentence
- Duplicate detection is anchored on pauses: a word not preceded by a ≥0.35s pause can't start a new take

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

### 7b. Sanity-check the result before reporting success

**Compare the durations and refuse to call it done if too much vanished.**

Normal speech with pauses loses 10–45%. Past **70% removed**, the threshold didn't match the recording level and the cut ate the speech — you have a destroyed file, not a tight edit.

```bash
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "<original>"
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "<edited>"
```

Over 70%? Don't report success. Say plainly that the cut looks broken, and offer a lower threshold:

```bash
--edit "audio:threshold=2%"
```

**In batch, check every video, not just the first.** Recording levels vary between files, so one good result says nothing about the next. A real run produced 12–19% on some files and 98% on others in the same folder.

**In batch, stop on the first suspicious file.** Don't grind through the remaining videos producing broken output — the user is waiting on a job that's destroying their footage.

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
| Stutter and duplicate detection | **Any language.** Both are mechanical: repeated tokens and pause-anchored echoes |
| Filler judgment | **Any language** — you do the judging, and you are not tied to one |

Moving the judgment out of a remote LLM removed the old PT-BR limitation: there is no Portuguese prompt to calibrate anymore.

Two Portuguese-specific bits remain, and both are small:

- The transcription request still sends `"language": "pt"`. For non-Portuguese audio, that has to change or the ASR is told the wrong language.
- `PROTEGIDO` holds Portuguese vocatives and pronouns. For another language, the equivalent words aren't guarded — so be stricter yourself about not cutting subjects and vocatives.

Until those are parameterized, treat non-Portuguese `--fillers` as usable but unpolished, and say so to the user.

---

## Guardrails

- **Never overwrite the original** — output always goes to `<OUTPUT>/`, never replaces the input file.
- **Don't proceed without dependencies** — without `ffmpeg`, `auto-editor` and `ffmpeg-normalize` installed, the skill stops and instructs the user.
- **Don't invent paths** — if the file isn't found, stop and ask for the correct path.
- **Don't batch without confirmation** — if the user passes a folder instead of a file, confirm before processing them all.
- **`--fillers` never runs on its own** — the default mode is free and offline; the filler cut spends API money. It only happens if the user explicitly asks. And even then, the cut list goes to approval before being applied.
- **Filler cutting always starts from the original video** — if you transcribe the already-cut video and apply the ranges to the original (or vice versa), the timestamps don't line up and the skill cuts real speech.
- **Never run two `auto-editor` instances at once without an isolated `--temp-dir` per video** — cache collision corrupts the output (audio/video with invalid data, or worse, content mixed in from another leftover cache). To process several videos in parallel, each call needs its own `--temp-dir`, deleted right after use.
- **Never report success without comparing durations** — see step 7b. A destroyed file exits cleanly and looks like a finished job; only the duration gives it away.
- **Check disk space before a large batch** — each video needs ~3.3x its own size free on disk (the leveled input, the cut intermediate, and the final file coexist). Check free space before processing several large videos; if it doesn't fit, pause and ask the user to free space instead of letting ffmpeg fail halfway.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `auto-editor: command not found` | `pip install auto-editor` |
| `ffmpeg-normalize: command not found` | `pip install ffmpeg-normalize` |
| `ffmpeg: command not found` | Install ffmpeg and add it to PATH (see the step 2 table) |
| Error with `--video-codec copy` | Don't use it — the flag doesn't exist in auto-editor 29.x |
| Video with desynced audio | Don't use `copy` on videos with multiple audio tracks |
| **Output is a fraction of the original** (163s → 2.7s) | The recording is quiet and its speech sits below the absolute 4% threshold. You skipped the leveling pass in step 5 — normalize first. If it persists, lower the threshold: `--edit "audio:threshold=2%"` |
| Same threshold works on one video and destroys another | Recording levels differ between files. That's exactly what the step 5 leveling pass is for |
| Cuts too aggressive / feels rushed | Raise `--margin` to `0.3s` or `0.4s` |
| Creative drags, too much breathing room | Lower `--margin` to `0.0s` — that's the default for ads |
| Natural pauses being cut | Lower the threshold: `--edit "audio:threshold=2%"`. The lower the threshold, the less counts as silence. (The `--silent-threshold` flag was removed from auto-editor; it no longer exists in 29.x) |
| `Invalid NAL unit size` / `Found duplicated MOOV Atom` / decode error during normalization | The `auto-editor` cache collided with another instance running at the same time. Delete that video's `--temp-dir` and run it again alone (no parallelism) or with an exclusive `--temp-dir` |
| `--fillers`: `OPENROUTER_API_KEY nao encontrada` | Set the environment variable, or copy the skill's `.env.example` to `.env` and fill in the key |
| `--fillers`: `ABORTADO: marcou N% das palavras` | The LLM misunderstood the task. Run it again; if it repeats, the audio probably has noise/music confusing the transcription |
| `--fillers`: `transcricao voltou sem timestamps por palavra` | The chosen model doesn't support `verbose_json`. Only `openai/whisper-large-v3`, `whisper-large-v3-turbo` and `whisper-1` do. `gpt-4o-transcribe` and `qwen3-asr` return 400 |
| `--fillers`: several repeated "Obrigado" nobody said | A known Whisper hallucination in PT: it invents "Obrigado" over silent stretches. Not a script bug. Those cuts land on silence, which `--edit` would remove anyway, so they're harmless. Just don't count them as "real stutters" when reporting |
| `--fillers` on non-Portuguese audio transcribes badly | The request still sends `language: pt`. See "Language support" |
| Accented path not found in background Bash (Windows) | The background shell mangles accents (`Módulo` → not found). Use PowerShell for those paths |
| `Could not open input file: 432.42sec,432.96sec` | `--cut-out` takes one range per occurrence. Repeat the flag for each range, don't pass several together |
