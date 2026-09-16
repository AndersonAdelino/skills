# MISTAKES.md

Every bug that shipped, why it happened, and what fixed it.

This exists because the same mistakes were being made twice across sessions.
Read the relevant entry first if you are about to touch audio parameters,
detection heuristics, a batch path, a third-party API, a deploy, or anything
that renders with headless Chrome.

The recurring patterns below apply to skills that do not exist yet. Read those
even when nothing here matches what you are building.

---

## The recurring patterns

Read these before the entries. They generalise past any one skill.

### 1. A fixed parameter assumed to be valid for variable input

Five of the bugs below are this shape: a constant tuned against one file,
silently wrong on the next, invisible because nothing measured the result.

- `threshold=4%` — absolute, destroyed a quiet recording (163s → 2.7s)
- `-16 LUFS` — podcast target on YouTube output
- `--auto-lower-loudness-target` — harmless at 1 dB of gain, abandoned the target at 30
- `margin 0.1s` — ad pacing applied to a lesson
- a fixed 3-word probe — missed the exact case the feature was built for

Before hardcoding a number, ask what input would make it wrong, and whether the
code would *notice*.

### 2. Reporting a number that came from a parameter, not from the file

The command asks; only the measurement knows. A broken file exits zero and looks
like a finished job. Probe the delivered artefact for every figure you report.

### 3. Generalising from one benign sample

A hypothesis tested against a single easy case and dismissed. It came back as the
most expensive bug in this list.

### 4. A heuristic standing in for a judgement

Every detector written here died the same way: a parameter tuned against one
file, a new file it got wrong, another parameter to patch that, repeat. The
restart detector reached **eight** calibrated numbers and was still wrong on the
last real test. The stutter detector was smaller and honest, and still rejected
10 of the 13 hits it produced, because `"o que que eu faço"` is ordinary spoken
Portuguese and no comparison of identical words can know that.

Both were answering semantic questions — *is this a stutter, did he restart the
sentence* — by measuring characters.

They were deleted. The script now measures (timestamps, pauses, confidence,
waveform energy) and the agent reads and decides. **The first output produced
that way was better than every heuristic version before it**, on the same file,
judged by the person whose video it is.

The tell, before it becomes obvious: a parameter added to fix a specific file.
One is a calibration. Three is a category error.

### 5. The error message names the wrong cause

An error arrives with a confident explanation attached, and the explanation is
wrong. You then spend the time on the thing it named.

Twice in one day a `403` meant "no User-Agent header" and was read as "bad
credentials" — once by me, once by my own error message, which told the user to
go check token permissions that were never the problem. The test that settled
it took ten seconds: **send the same request with no credentials at all.** Same
error. So it was never about credentials.

Before acting on an error's stated cause, find the cheapest request that
isolates it. And when *you* write the error text, only name a cause you
actually checked — a guess in an error message sends someone hunting for hours.

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

### 2026-09-13 — Stopping a task leaves the encode running, and it compounds

**Symptom.** Two apply runs died in a row. The first with `WinError 8` — the
system could not create the ffmpeg process at all. The second with exit code 1
and no message whatsoever.

**Cause.** An `auto-editor` orphaned hours earlier by a cancelled task, holding
935 MB. Stopping a task kills the shell; the child process keeps running. Same
trap already recorded for `tail -f`, different victim.

And it **compounds**: each run that dies leaves its own orphan, so every retry
has less memory than the last. Two failures in, three orphans were alive.

**Fix.** `ram_livre_mb()` warns below 1.8 GB and, when it does, `encodes_rodando()`
counts live ffmpeg/auto-editor processes and says so — because the number the user
needs is not "you are low on memory", it is "there are three encodes running and
you are not editing three videos".

### 2026-09-13 — Three careful layers produced a silent exit

**Symptom.** Exit code 1, no traceback, no message, nothing.

**Cause.** `medir_loudness()` returned `(None, None)` when its regex missed,
`normalizar()` passed that through, `aplicar()` called `sys.exit(1)`. Every layer
did the defensive thing, and together they produced a program that stops without a
word — worse than a traceback, which at least gives you something to search for.

**Fix.** Each failure names itself: `OSError` caught separately (that is where
`WinError 8` lands) and repeating the RAM warning there, ffmpeg's exit code and
output tail when the measurement is missing, and one plain line before giving up.

### 2026-09-12 — `tail -f` made a healthy job look dead

**Cause.** Git's `tail.exe` holds the file handle on Windows, so PowerShell's
`Add-Content` then fails silently. Stopping the task kills the shell but leaves
`tail` orphaned, still holding the handle. Roughly 10 minutes spent diagnosing
"workers aren't running" while they were running fine.

**Fix.** Step 7 now reads the log open-and-close, with the Windows note.

---

## Deploy and third-party APIs

Found publishing a real client site to a real HostGator. None of it would have
shown up locally.

### 2026-09-16 — A 403 blamed the token; it was a missing User-Agent

**Symptom.** Every cPanel API call returned `403` with `error code: 1010`. The
script said "the cPanel refused the token. Check user, token, and File Manager
permission." The token was correct the whole time.

**Cause.** HostGator serves cPanel behind Cloudflare, which rejects requests
with no `User-Agent` **before** looking at authentication. The same thing had
already happened with the Pexels API an hour earlier, and the `stock` command
of another skill had never worked for anyone because of it.

**Fix.** Send a browser `User-Agent` on every third-party call. When `1010`
appears anyway, say explicitly that it is *not* the token. Pinned by a test
that asserts the header reaches the request.

The diagnosis that ended it: the same request **with no credentials at all**
returned the identical error. See recurring pattern 5.

### 2026-09-16 — `Fileman::mkdir` does not exist, and the old script called it

**Symptom.** Creating a client folder failed with "The system could not find
the function mkdir in the module Fileman".

**Cause.** That UAPI function does not exist in this cPanel version — nor
`create_directory`, nor `makedir`. I asked the server instead of guessing
again. The previous bash version of the deploy called `Fileman::mkdir`, so it
could never have created a client folder; nobody had noticed because nobody had
run it against a fresh destination.

**Fix.** Not a fix — a deletion. `Fileman::upload_files` creates the directory
tree on its own, nested included, so `criar_caminho`, `pastas_para_criar` and
`criar_pasta` were removed. The test is behavioural:
`assert not hasattr(Cpanel, "criar_pasta")`.

Before writing against a remote API, ask it what it has. Docs and memory both
lie, and the server is authoritative and free to query.

### 2026-09-16 — The second deploy of every client would have failed

**Symptom.** First deploy: 10/10 files. Redeploy after an edit: 0/10, "the file
for upload already exists".

**Cause.** `Fileman::upload_files` refuses to overwrite unless `overwrite=1` is
in the request. The first run works, which is exactly the run everyone tests.
**Republishing after a tweak is the most common operation this skill has**, and
it was broken in every case.

**Fix.** `overwrite=1`, plus a guard that makes overwriting safe: the deploy
reads the `<title>` already on the server and stops if it belongs to a
different business. Both pinned by tests.

The general form: **the second run is a different test from the first.** Idempotency,
overwrite, resume and re-entry never show up in a first-run demo.

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

### 2026-09-16 — An estimator that could not be accurate, proven by measuring

**Symptom.** A Python function estimated how many lines of text would fit on a
rendered slide, from average character width. It produced a false positive on
the first real carousel, warning that a slide would not fit when it did.

**Cause.** Not a bad constant — a wrong idea. Measured against Chrome with the
real reference copy, **no single characters-per-line value reproduces the
browser**: at 40px one sentence needs more than 52 per line and another at most
43, in the same box. Proportional fonts, accents and word-wrap make it
unestimable, and any constant is wrong for some input.

**Fix.** Deleted, not tuned. The layout measures itself: the page carries every
slide, shrinks the type until all of them fit, and paints a red bar into the PNG
when one still does not. What stayed in Python is the one thing the browser
cannot report — **which** slide is dragging the whole carousel down — with
budgets measured by binary search in Chrome, not derived.

Before writing an estimator, spend ten minutes checking whether the quantity is
estimable at all. If the ground truth is cheap to query, query it.

### 2026-09-16 — A skill prescribed tools it did not ship

**Symptom.** `local-site-lift` told the agent to source images "real photo →
Pexels → AI" and had **no script for any of it**. When I built a site with it, I
pulled another skill's script out of git with `git show`. A user installing this
skill alone could not have done that.

**Cause.** The rule was written while the tooling lived elsewhere and felt
available. It was not: skills install independently.

**Fix.** Its own `scripts/imagens.py`. And the general check: **every capability
a SKILL.md asks for must exist inside that skill's folder.** Prose that names an
API the skill cannot call is a promise the agent will improvise badly — here it
would have hit the Pexels 403 above and given up.

### 2026-09-16 — A clean merge silently dropped three registrations

**Symptom.** Two feature branches merged into `master` with **no conflict**. The
result was missing the CI line for one skill, that skill's entry in
`plugin.json`, and another skill's row in the README table.

**Cause.** Both branches edited the same regions of `test.yml` and the README
table. One branch had *deliberately removed* the carousel's CI line, because
that folder did not exist on it. Git resolved the overlap on its own and
preferred the removal. A skill would have shipped **outside the manifest and
outside CI** — installed by nobody, tested by nothing.

**Fix.** Never trust "no conflict" as "correct" when branches touch the same
lists. After any merge, check the invariants instead of reading the diff:

- every skill folder with a `SKILL.md` appears in `plugin.json`
- every `scripts/*.py` appears in the CI workflow
- every skill has a row in the root README

Three one-line checks, and they caught what the merge hid.

### 2026-09-16 — `Test-Path` reported a stale screenshot as a fresh one

**Symptom.** A rendered page was reported as showing the new image. It showed
the old one. The image file on disk was correct; the screenshot was 13 minutes
old.

**Cause.** The capture had failed, and the check was
`if (Test-Path $png) { "OK" }`. A previous run's file was sitting there, so the
check passed on an artefact the run never produced.

**Fix.** Delete the output before generating it, and check the **timestamp**,
not existence. This is recurring pattern 2 with a twist: the file was not just
unverified, it was *someone else's*. Existence is not freshness.

### 2026-09-16 — `Stop-Process chrome` killed the user's own browser

**Symptom.** "caralho, para de ficar fechando o navegador, to tentando
trabalhar em paralelo."

**Cause.** Headless Chrome instances were piling up and breaking later
screenshots, so the cleanup was `Get-Process chrome | Stop-Process -Force`.
That matches every Chrome on the machine, including the windows the person is
working in.

**Fix.** Only kill what this session started, by filtering on the command line:

```powershell
Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" |
  Where-Object { $_.CommandLine -like "*--headless*" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

The machine is not yours. Any `Stop-Process`, `taskkill`, `pkill` or
`rm -rf` by name hits the user's work too.

### 2026-09-15 — `--window-size` is a request, and Windows can refuse it

Found while building a skill that was later abandoned. The trap outlives it,
and it applies to anything here that renders with headless Chrome.

**Symptom.** A page screenshotted at `--window-size=390,844` came back with text
cut off mid-word at the right edge, looking exactly like a CSS overflow bug. The
page was fine: measured in the browser, `scrollWidth` was 390 with nothing
overflowing.

**Cause.** Windows enforces a minimum window width, and `--headless=new` creates
a real OS window. Chrome laid the page out in a **500px** viewport and wrote a
390px PNG — a crop, presented as a phone rendering. The file had the right
dimensions and the wrong content.

**Fix.** Render inside an `<iframe>` sized exactly as requested, in a window wide
enough for the OS. The iframe defines the viewport, so media queries, `vw` and
`vh` all resolve correctly. Verified: viewport 390, `scrollWidth` 390.

**What this means for `thread-carousel`.** It is not hit today: 1080px is far
above the floor. What protects it is not luck but `png_dimensoes()` — it probes
the delivered PNG instead of trusting the flag it passed. Any future render
narrower than ~500px would silently crop, and only a check like that one would
notice.

The general shape, which is pattern 2 again: a flag states an intention, and only
the artefact knows what happened. PNG dimensions matching what you asked for does
not prove the browser laid the page out that way.
