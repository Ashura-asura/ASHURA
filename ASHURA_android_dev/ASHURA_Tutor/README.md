# ASHURA Tutor

Offline-first, Android-first adaptive learning platform.

**Status:** v0.5.0 — offline learning core with a persistent local model, a ChatGPT-style tutor chat, richer mixed test
sets from imported PDF/Office/image notes, on-device OCR, and 200 bundled open-licensed study sets. See `CHECKPOINT.md`,
`docs/ARCHITECTURE_STATUS.md` and `docs/RUNTIME_INTEGRATION.md`.
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
  composer. Suggested topics appear on an empty conversation.
- **Documents** — import Markdown/text, PDF, DOCX, XLSX, PPTX and PNG/JPEG/WebP. Text PDFs use embedded text; scanned pages
  and photos use bundled ML Kit Latin + Devanagari OCR. Each passage keeps its page, slide or sheet label for citations.
- **Mixed test sets** — importing a document and tapping *Quiz me* builds up to 20 questions: recall cloze plus definition
  and explanation prompts, spread across pages/slides/sheets. It is deterministic and works without a model.
- **Bundled study sets** — 200 offline Markdown notes (20 each for mathematics, general science, physics, chemistry,
  Python, C, Rust, electrical engineering, basic electronics, and advanced calculus) sourced from Wikipedia under
  CC BY-SA 4.0. The Library lists them by subject; add one or a whole subject, then tap *Quiz me*. The manifest records the
  exact source URL and a SHA-256 checksum for every note, and the app verifies it before import. Rebuild with
  `python tools/fetch_study_sets.py` (network is needed only for rebuilding, never at app runtime).

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

Install JDK 17 or newer and Android SDK Platform 35 plus Build Tools 35.0.0. The Gradle Wrapper
is checked in; on first use it downloads Gradle 8.14.4. On Windows:

```powershell
sdkmanager "platform-tools" "platforms;android-35" "build-tools;35.0.0"
sdkmanager --licenses
.\gradlew.bat testDebugUnitTest assembleDebug
```

The wrapper download and initial dependency resolution require network access. Android SDK
installation and accepting its licenses are separate machine setup steps.

No model weights or training are part of this checkout.

---

Built and powered by **Bishal Bhandari** from Nepal.
