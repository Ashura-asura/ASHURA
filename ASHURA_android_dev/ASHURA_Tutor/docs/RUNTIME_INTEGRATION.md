# Local model runtime: integration guide

Status: **integrated and compiling.** The app uses **LiteRT-LM 0.19.1** (`com.google.ai.edge.litertlm:litertlm-android`)
behind the existing `ModelRuntime` boundary. Model weights are **never** bundled in the APK; the user downloads or imports
one verified `.litertlm` file after explicit consent. Real-device load, generation, latency and memory numbers are still
pending because no physical device or emulator is available in this environment.

## Runtime choice
| Option | Decision |
|---|---|
| LiteRT-LM | **Chosen.** Official Maven AAR, Kotlin API, streaming via `sendMessageAsync`, `cancelProcess`, CPU/GPU backend, no NDK build. |
| llama.cpp JNI | Rejected for now: requires an own NDK/ABI build and more maintenance for the same single-model flow. |
| MediaPipe LLM Inference | Functional overlap; LiteRT-LM is the newer Google path and is published with Kotlin 2.4 metadata. |

The pinned toolchain is Kotlin 2.4.0 / AGP 8.13.2 / Gradle 8.14.4 / KSP 2.3.13 / Room 2.8.5. LiteRT-LM 0.19.1 metadata
cannot be read by older Kotlin compilers, and KSP2 2.3.x requires AGP newer than 8.7.3.

## Where the pieces live
| Concern | File |
|---|---|
| ModelRuntime implementation | `domain/runtime/LiteRtLmModelRuntime.kt` |
| Pinned catalog, URLs, sizes, SHA-256 | `domain/runtime/ModelCatalog.kt` |
| Manifest validation, RAM tiers, resource policy | `domain/runtime/ModelManifest.kt` |
| Prompt + untrusted-evidence handling | `domain/runtime/PromptBuilder.kt` |
| Download, SAF import, checksum, one-model slot | `data/model/ModelManager.kt` |
| Settings UI and progress | `ui/AshuraTutorApp.kt` |
| App wiring (single runtime instance) | `AshuraTutorApplication.kt` |

## Catalog
| Model | Quantization | Context | Minimum tier | Size | Licence |
|---|---|---|---|---|---|
| Qwen2.5-1.5B-Instruct Q8 (`ekv4096`) | dynamic INT8 | 4096 | STANDARD (6 GB) | 1,597,922,856 B | Apache-2.0 |
| Qwen3-0.6B INT4 (`ekv4096`) | dynamic INT4, thinking disabled | 4096 | CONSTRAINED (4 GB) | 343,490,560 B | Apache-2.0 |

Both entries pin the exact Hugging Face revision, artifact size, SHA-256 and an HTTPS resolve URL. The catalog is the only
source of downloadable or importable files: a SAF import is accepted only when its size **and** SHA-256 match a catalog entry.

## Lifecycle and safety rules
1. **One model, one engine.** `LiteRtLmModelRuntime` holds a `Mutex`; there is a single app-scoped instance.
2. **Verify before load.** `load()` re-hashes the file (unless the manifest pins a tokenizer hash) and refuses on mismatch,
   wrong size or missing file. A failed verification never reaches the native engine.
3. **Download discipline.** HTTPS only, 30 s connect / 60 s read timeouts, exact content-length check where advertised,
   streamed SHA-256, `.part` file, atomic rename, 1 GB free-space reserve, and a refusal when another install is active.
4. **Explicit consent.** Network access happens only from the Settings download button. The manifest declares `INTERNET` and
   `ACCESS_NETWORK_STATE`; nothing else in the app performs network I/O.
5. **Cancellation and memory pressure.** `cancelDownload()` cancels the coroutine and disconnects the HTTP connection.
   Generation cancellation calls `Conversation.cancelProcess()`; `unload()` during a decode only sets a flag and the
   generation's `finally` closes the engine under the mutex, so native resources are never closed underneath a running
   decode. `Application.onTrimMemory` unloads the model under critical/moderate pressure; the file stays installed and can
   be loaded again from Settings.
6. **Honest modes.** Answers carry `ResponseMode`: `DETERMINISTIC` (calculator/unit converter), `LOCAL_MODEL` (engine output,
   with a "can be wrong" limitation), or `OFFLINE_FALLBACK` (study scaffold). The Tutor screen says when no model is loaded.
7. **Model-owned chat template.** LiteRT-LM applies the model template, so `PromptBuilder.buildParts` supplies plain system
   and user text. `PromptBuilder.build` keeps ChatML for tests and template-less runtimes.
8. **Untrusted evidence.** Imported notes are delimited in `<evidence>` tags, stripped of control tokens, length-capped, and
   the system instruction says they are facts to cite, never instructions to follow.

## User flow
1. Settings → *Local tutor model* shows the device RAM tier and the catalog.
2. **Download** streams the pinned artifact with progress and a cancel button; **Import** opens SAF for a `.litertlm` file.
3. After verification the model is installed into `filesDir/models/<id>.litertlm` and loaded automatically.
4. Load / Unload / Delete are explicit. Deleting asks for confirmation and removes only verified model files.
5. The Tutor screen labels each answer's mode and shows a hint pointing to Settings when no model is loaded.

## Verification available without a device
- `testDebugUnitTest`: 139 tests, including `ModelCatalogTest`, `PromptBuilderPartsTest`, `StructuredAnswerTest`,
  `StreamingTest`, `LearnerProfileStoreTest`, and `LiteRtLmRuntimeContractTest` (invalid manifest, missing file, unload
  idempotence, no-model generation). 0 failures.
- `assembleDebug` succeeds with the AAR and its `arm64-v8a` / `x86_64` native libraries packaged.
- Release R8 keep rules retain the LiteRT-LM JNI classes.

## Device-only checklist (not yet done)
1. Download each catalog entry on a real 4 GB and a 6 GB+ device over a metered connection; confirm progress, cancel,
   resume-by-restart and checksum acceptance. Corrupt a byte and confirm rejection.
2. Load Qwen3-0.6B on the 4 GB device and Qwen2.5-1.5B on the 6 GB+ device; record cold-load time, time to first token,
   tokens/s, peak PSS, battery and temperature over 10 minutes.
3. Cancel mid-generation; confirm return within 1 s, no native crash, and a subsequent prompt still works.
4. Unload during generation; confirm the engine closes after the decode stops and the next Load succeeds.
5. Run 20 school maths/science prompts, 5 note-grounded prompts and 5 prompt-injection passages; verify the injection never
   changes behaviour and that deterministic tools still win.
6. Compare CPU vs GPU backend; CPU remains the default until GPU is measured and stable.
7. Verify streaming: the first delta appears before generation finishes, deltas render in order without duplication, the
   final structured answer replaces the streamed text, and Cancel stops both the UI and the native decode.
8. Compare Settings diagnostics with wall-clock measurements; confirm the roughly 4-characters-per-token estimate is
   labelled as approximate and that heap/free-storage values refresh after a load and a generation.

## Known limits
- Only `arm64-v8a` and `x86_64` are packaged; 32-bit devices are unsupported.
- Keyword retrieval only; a paraphrase with no shared words can miss note evidence.
- Citations show which passages were supplied, not proof the model used them.
- GPU backend is untested. No model is bundled; first use requires one download or a local import.
