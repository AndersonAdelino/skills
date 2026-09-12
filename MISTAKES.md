# MISTAKES.md

Every bug that shipped, why it happened, and what fixed it.

This exists because the same mistakes were being made twice across sessions. If
you are about to touch audio parameters, detection heuristics, or a batch path,
read the relevant entry first.

---

## The root pattern

> **A fixed parameter assumed to be valid for variable input.**

Five of the bugs below are the same shape. A constant tuned against one file,
silently wrong on the next, and invisible because nothing measured the result.

The second pattern, smaller but more dangerous: **reporting a number that came
from a parameter instead of from the file.**

---

## Audio

### 2026-09-12 — Loudness target silently abandoned (critical)

**Symptom.** 18 lessons reported as "-14 LUFS"; measured, they were between
-17.8 and -27.1 — a 9.3 LU spread. They would have been published that way.

**Cause.** `ffmpeg-normalize --auto-lower-loudness-target` guarantees pure linear
gain, and pays for it by abandoning the target whenever the required gain would
breach the peak ceiling — by a different amount per file. Sources with a ~22 dB
crest factor (mouse clicks and keyboard over quiet speech) never got close. The
quietest needed 30 dB of gain; by 21 dB the peak was already at the ceiling.

The skill promised **both** "-14 LUFS" and "linear, no compression". For these
sources those are incompatible, and it dropped the first without saying so. All
18 pinned to the peak ceiling at a different loudness each — normalization
destroying the exact consistency it exists to provide.

**Compounding error.** This hypothesis was raised earlier the same day and
*dismissed*, because it was measured on one file already at -16.9 LUFS that
needed 1 dB of gain. With and without the flag were identical there. Generalizing
from one benign sample.

**Fix.** Linear gain + peak limiter, an explicit choice instead of a silent
tradeoff. A limiter is not a compressor: it shaves the transient and never
touches the dynamics of the voice, which is what the promise was protecting.
The result is always measured, and a deviation over 1 LU is reported.
`ganho_para_alvo()` is tested against the real -44.4 LUFS case.

### 2026-09-11 — -16 LUFS on YouTube output

**Symptom.** Audio still quiet, never reaching yellow on a meter.

**Cause.** -16 LUFS is the podcast standard (Apple Podcasts, Spotify spoken).
This skill produces YouTube uploads, where the reference is -14 — and **YouTube
only ever turns loud content down**, never boosts quiet uploads. Shipping at -16
means playing quieter than everything around it, permanently.

**Fix.** Default -14 LUFS, ceiling -1.0 dBTP. Measured: peak went from -2.82 to
-0.97 dBTP, about 2 dB of headroom that was going unused.

---

## Cutting

### 2026-09-11 — Fixed threshold destroyed quiet recordings (critical)

**Symptom.** A 163-second video came out as 2.7 seconds. Three files were
processed that way before a human noticed the durations.

**Cause.** `auto-editor`'s threshold is **absolute** — 4% of full scale, about
-28 dB — not relative to the file's own peak. A lesson recorded at
`mean_volume -48.2 dB` had 0.8% of its frames above that line, so the cut deleted
the speech and kept the gaps.

**Fix.** Level the audio *before* cutting, so a fixed threshold means something
again. On that same file, frames above the threshold went from 0.8% to 81.5%.
Costs two audio passes and no extra video encode, since `ffmpeg-normalize` copies
the video stream.

### 2026-09-11 — Success reported on a destroyed file

**Cause.** Nothing compared durations. A broken file exits zero and looks like a
finished job.

**Fix.** `corte_suspeito()` — over 70% removed is not an edit, it is a failure.
Step 7b of the SKILL.md requires comparing durations before reporting success,
checking every file in a batch, and stopping on the first suspicious one instead
of grinding through the rest destroying footage.

### 2026-09-12 — No guardrail for a pointless cut

**Symptom.** One file burned an hour of CPU to remove 4 seconds (0.7%).

**Cause.** Only the destructive extreme was guarded. An already-edited video has
no dead air, so the run was a re-encode wearing a cut's clothes: costs quality,
delivers nothing.

**Fix.** `corte_irrelevante()` — under 2% removed, stop and offer the original.

### 2026-09-11 — `margin 0.1s` on lesson content

**Symptom.** "Cut in the middle of the conversation, then jumps somewhere
disconnected."

**Cause.** 0.1s is ad pacing. In a lesson the micro-pauses are not dead air —
they are breathing, reasoning, the time the student needs. Removing them makes
sentences collide.

**Fix.** Cut-strength vocabulary in SKILL.md so "cut it tighter" resolves to a
number without anyone reasoning about the inverted scale (smaller margin = harder
cut).

---

## Detection

### 2026-09-11 — Duplicate detection missed the case it was built for

**Cause.** Fixed 3-word probes compared across the transcript. The motivating
example — "Fala pessoal" restarted as "Olá pessoal" — shares exactly one word, so
any probe long enough to be safe scored below threshold, and the boundary landed
a word early.

**Fix.** Anchor on **pauses**, not text. People stop before they restart, so only
a word preceded by a ≥0.35s pause can begin a new take. That lets the probe be
short without drowning in false positives, because only restart points are tested.

### 2026-09-11 — Duplicate detection proposed cutting 36 seconds of good narration

**Cause.** On the first run against real audio, "e cada" (8.96s) matched "cada um"
(45.48s) at 0.727, purely on the shared word "cada". Three things were wrong: a
45s span cap (nobody rambles for 36 seconds, notices, and starts over), a 0.72
threshold the false positive squeaked through, and a length check applied only to
the forward probe — a 5-character target anchored the whole thing.

**Fix.** 15s cap, 0.78 threshold, length check on both sides. All three set from
that case rather than from theory, and the case is now a regression test.

The agent had already rejected it by reading the text, which is the design
working — but the detector should never have proposed it.

---

## Secrets and config

### 2026-09-11 — A BOM hid the API key

**Symptom.** Key reported as missing while the `.env` looked perfect in every
editor.

**Cause.** Notepad and `Out-File -Encoding utf8` write a BOM on Windows. Read as
plain `utf-8`, the first key became `﻿OPENROUTER_API_KEY` and never matched.

**Fix.** Read as `utf-8-sig`. The self-test writes a real BOM and asserts the
bytes are present, so the codec cannot be quietly downgraded.

### 2026-09-11 — The whole `.env` was loaded into the process

**Cause.** `os.environ.setdefault()` ran for every key found. The skill is
installed inside other people's projects, whose `.env` files are full of
credentials that have nothing to do with cutting video.

**Fix.** Read only `OPENROUTER_API_KEY`. Parser extracted to `_chave_no_env()`
and covered by a test asserting that a neighbouring key does **not** leak.

### 2026-09-11 — A traceback where a beginner needed instructions

**Cause.** Missing key raised an uncaught `RuntimeError`. The audience is content
creators; a ten-line stack trace reads as "it crashed", not "you still have to
configure something".

**Fix.** Clean message with the exact command per platform, plus the reminder
that silence cutting and normalization need no key at all.

---

## Batch and environment

### 2026-09-12 — Parallel lanes were slower, then killed a video

**Measured on the same file:**

| Lanes | Encoder CPU | Cut phase |
|---|---|---|
| 3 | 26% of one core | 2h09 (never finished) |
| 1 | ~5 cores | 1h03 (finished) |

Three lanes split the same CPU and competed for RAM until one died with
`Cannot allocate memory` in the `loudnorm` filter (11.8 GB total, 1.7 GB free).

**Cause.** The skill warned about cache collision — correct, and it worked — but
said nothing about memory, which is what actually broke.

**Fix.** Serial by default. Parallel only with measured free memory, and the
skill now says the gain is often negative on a normal laptop.

### 2026-09-12 — Resume by file existence shipped a truncated file

**Cause.** `META ADS - AULA 04` was left with no `moov` atom when processes were
stopped. A naive "the output exists, skip it" would have delivered it.

**Fix.** Resume by probing duration, never by existence. If `ffprobe` can't read
a duration, or it's implausible against the source, redo the file.

### 2026-09-12 — HEVC input cost ~6x with no warning

**Cause.** Decoding HEVC into an h264 encode is far more expensive, and nothing
checked the input codec or warned about the time. It looked like a hang.

**Fix.** Check the input codec alongside disk and RAM before a batch.

### 2026-09-12 — `tail -f` made a healthy job look dead

**Cause.** Git's `tail.exe` holds the file handle on Windows, so PowerShell's
`Add-Content` then fails silently. Stopping the task kills the shell but leaves
`tail` orphaned, still holding the handle. Roughly 10 minutes spent diagnosing
"workers aren't running" while they were running fine.

**Fix.** Step 7 now reads the log open-and-close, with the Windows note.

---

## Tooling

### 2026-09-11 — PowerShell here-string broke `git commit` twice

**Cause.** `git commit -m @'...'@` loses the quoting when the message contains
double quotes; git then parses the body as pathspecs.

**Fix.** Write the message to a file and use `git commit -F`.

### 2026-09-11 — Bulk edit mangled every accent

**Cause.** `Get-Content`/`Set-Content` on PS 5.1 read UTF-8 as ANSI and rewrote
it as UTF-8. `silêncios` became `silÃªncios` across three files.

**Fix.** `git checkout` to revert, then `[System.IO.File]::ReadAllText/WriteAllText`
with UTF-8 specified on both ends.
