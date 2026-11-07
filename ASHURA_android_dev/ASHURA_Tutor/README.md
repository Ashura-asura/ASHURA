# ASHURA Tutor

Offline-first, Android-first adaptive learning platform.

**Status:** v0.3.0 — offline learning core plus an integrated local-model runtime (LiteRT-LM), verified model downloads and
SAF import. See `CHECKPOINT.md`, `docs/ARCHITECTURE_STATUS.md` and `docs/RUNTIME_INTEGRATION.md`.
**Spec:** `docs/PRODUCT_SPEC.md` (architecture v5.0).  
**Target:** 4 GB RAM Android phones (primary), 6 GB (standard), 8 GB+ (enhanced).

## Local model

No weights are bundled. Settings → *Local tutor model* offers two pinned artifacts:

| Model | Tier | Size |
|---|---|---|
| Qwen2.5-1.5B-Instruct Q8 | 6 GB+ | 1.6 GB |
| Qwen3-0.6B INT4 | 4 GB+ | 343 MB |

Downloads are HTTPS-only and checked against a pinned SHA-256; a `.litertlm` file can also be imported through the system
file picker, but only if its size and hash match the catalog. One model is installed and loaded at a time. Until a model is
loaded, the tutor answers with the deterministic tools and an honest offline study scaffold.

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
