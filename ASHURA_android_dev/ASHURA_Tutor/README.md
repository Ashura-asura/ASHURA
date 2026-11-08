# ASHURA Tutor

Offline-first, Android-first adaptive learning platform.

**Status:** v0.5.15 — offline learning core with a persistent local model, a ChatGPT/Claude-style tutor chat,
chat history with reopen/delete, regenerate, timed four-option tests (Quick 20 / Medium 35 / Long 50) with
saved marks, time taken and score change, on-device OCR with editable text, honest confidence labels, a hint
ladder, explain-my-mistake, Library import status with re-index, clear added/not-added study-set states, and
200 bundled open-licensed study sets. Home now leads with the next action: continue the recommended topic,
today's review, ask, learn, import material, recent items, model/offline status and a privacy line.
Library is split into Material, Study sets and Tests, with Recent/Documents/Notes filters and a detail
view for every imported item. Tutor says whether it is searching notes or writing, and Progress shows
qualitative mastery bands instead of a precise-looking percentage, and a due topic can be reviewed directly.
With no model loaded, Tutor shows an explicit setup banner instead of a grey dot, and the typing dots stop
moving when system animations are off.
See `CHECKPOINT.md`, `docs/ARCHITECTURE_STATUS.md` and `docs/RUNTIME_INTEGRATION.md`.
**Spec:** `docs/PRODUCT_SPEC.md` (architecture v5.0).  
**Target:** 4 GB RAM Android phones (primary), 6 GB (standard), 8 GB+ (enhanced).

## Local model

No weights are bundled. Settings → *Local tutor model* offers two pinned artifacts:

| Model | Tier | Size |
|---|---|---|
| Qwen2.5-1.5B-Instruct Q8 | 6 GB+ | 1.6 GB |
| Qwen3-0.6B INT4 | 4 GB+ | 343 MB |

Downloads are HTTPS-only and checked against a pinned SHA-256; a `.litertlm` file can also be imported through the system
file picker, but only if its size and hash match the catalog. One model is installed and loaded at a time. A verified model
is loaded automatically at app start and stays loaded until the learner explicitly unloads it; memory-pressure callbacks no
longer unload it mid-session. Until a model is loaded, the tutor answers with the deterministic tools and an honest offline
study scaffold.

## Tutor, documents and study sets

- **Chat tutor** — the Tutor tab is a full-height conversation with bubbles, streaming text, stop, citations and a pinned
  composer. Suggested topics appear on an empty conversation. Every answer carries an honest confidence label
  (verified by calculation / based on your notes / model-only / insufficient evidence), the latest answer can be
  regenerated, and the history button reopens or deletes past chats. Settings can clear all chat history without
  touching notes or progress.
- **Practice** — a hint ladder notices repeated wrong attempts and offers the next hint, then the worked solution;
  saying “just tell me” in Socratic mode switches that answer to a direct explanation. After a wrong answer,
  *Explain my mistake* compares what you wrote with the correct answer and gives the reason, the method and a next
  step from deterministic rules.
- **Documents** — import Markdown/text, CSV/TSV, PDF, DOCX, XLSX, PPTX and PNG/JPEG/WebP. Text PDFs use embedded
  text; thin or scanned pages and photos use bundled ML Kit Latin + Devanagari OCR with orientation retry. Each passage
  keeps its page, slide or sheet label for citations, spreadsheets keep `A1` cell references and formulas, and OCR text
  can be corrected in Library → edit, which re-indexes the passages. Each Library item shows its size, passage count and
  date added; an item with no searchable passages is marked *not indexed* and gets a Re-index button.
- **Timed tests** — choose Quick (20 questions), Medium (35) or Long (50) in Library. Each question is a
  four-option “choose the best answer” item built deterministically from your imported notes; there are no
  fill-in-the-blank or free-text items. The timer is selected from the mode (60 seconds per question), and
  obtained marks, time taken and the change from the previous test of the same mode are stored on the device
  and listed in Progress. A single note can also start a shorter Quick test from its own facts.
- **Bundled study sets** — 200 offline Markdown notes (20 each for mathematics, general science, physics, chemistry,
  Python, C, Rust, electrical engineering, basic electronics, and advanced calculus) sourced from Wikipedia under
  CC BY-SA 4.0. The Library lists them by subject with a live “X of Y added” count, a check mark on added sets
  and a minus action to remove one after confirmation. Add one or a whole subject, then start a timed test. The
  manifest records the exact source URL and a SHA-256 checksum for every note, and the app verifies it before import.
  Rebuild with `python tools/fetch_study_sets.py` (network is needed only for rebuilding, never at app runtime).

## Not implemented yet

The v5.0 spec is broader than this build. These are deliberately absent and should not be advertised:
online research/web search, speech input or text-to-speech, diagram/chart understanding beyond OCR, plotting
and simulations, a code-execution sandbox, science/programming specialist engines, semantic or hybrid
retrieval, evidence-coverage verification, a multi-subject curriculum graph beyond the 4 topic seed pack,
original-file storage with hashes, and device benchmarks. See `docs/ARCHITECTURE_STATUS.md` for the
section-by-section gap matrix.

## Current implementation layout

This checkout is an early vertical slice, not the full target module layout. The Kotlin app is
currently a single `app` module; the content, model, scripts, and expanded test areas in the spec
are planned work.

## Target repository layout (spec §20)

```
android/        — Kotlin + Jetpack Compose application
core/           — domain, application, data modules
feature/        — tutoring, curriculum, assessment, library, research, settings
engine/         — inference, retrieval, documents, tools, verification, speech, vision, plotting
content/        — curriculum packs, subjects, language packs
model/          — model manifests, prompts, compatibility, evaluation
training/       — future SFT pipeline (deferred, not launch dependency)
tests/          — unit, integration, retrieval, model_quality, device, security
docs/           — architecture, decisions, testing, privacy, release
scripts/        — setup, test, build_debug, benchmark (PowerShell)
```

## Immediate build order (spec §25 — first vertical slice)

1. Android project + core module boundaries
2. Home and Tutor screens
3. Integrate one local model
4. Streaming, cancellation and bounded context
5. Basic task controller
6. Deterministic calculator
7. One lesson flow for one subject
8. Small diagnostic and practice loop
9. Persist the learning event locally
10. Benchmark on a real low-memory Android device

## Build prerequisites

Install JDK 21 and Android SDK Platform 35 plus Build Tools 35.0.0. The app compiles to Java 17
bytecode, but the pinned LiteRT-LM 0.19.1 classes need a Java 21 runtime for the JVM unit tests.
The Gradle Wrapper is checked in; on first use it downloads Gradle 8.14.4. On Windows:

```powershell
sdkmanager "platform-tools" "platforms;android-35" "build-tools;35.0.0"
sdkmanager --licenses
.\gradlew.bat testDebugUnitTest assembleDebug
```

The debug APK is written to `app/build/outputs/apk/debug/app-debug.apk`. `dist/` is not produced by
Gradle; it is a local folder for named copies using the pattern
`ashura-tutor-<version>-debug.apk` (for example `dist/ashura-tutor-0.5.15-debug.apk`) and
`dist/*.apk` is git-ignored, so APKs are never committed.

The wrapper download and initial dependency resolution require network access. Android SDK
installation and accepting its licenses are separate machine setup steps.

CI (`.github/workflows/android-ci.yml` at the repository root, because GitHub only reads workflows
there) runs the same three tasks with JDK 21, caches Gradle, and uploads the debug APK plus the test
and lint reports. Existing lint warnings are recorded in `app/lint-baseline.xml`; new issues are still
reported and any lint error still fails the build.

No model weights or training are part of this checkout.

---

Built and powered by **Bishal Bhandari** from Nepal.
