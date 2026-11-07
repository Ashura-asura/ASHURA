# Local model runtime: integration guide

Status: **not integrated.** The app ships the interface, manifest validation, resource policy, prompt builder, file
verifier and contract tests. A real runtime needs the Android NDK/SDK and a physical device, so it cannot be completed or
claimed without them.

## Choose one runtime (spike both if time allows)
| Option | Pros | Cons |
|---|---|---|
| MediaPipe LLM Inference (`tasks-genai`) | Maven dependency, no JNI, GPU/CPU delegates | Limited model formats, less control over sampling/cancel |
| llama.cpp via JNI | GGUF, small quantised models, fine control | Own NDK build, ABI matrix, more code to maintain |

## Steps
1. Implement `ModelRuntime` (`load`, `generate`, `unload`, `health`); run on a background dispatcher, never the main thread.
2. Make `generate` cancellable: stop native work when the coroutine is cancelled; enforce `GenerationLimits.timeoutMillis`.
3. Download models to a temp file, check `ModelFileVerifier.hasSpaceFor`, verify `ModelFileVerifier.verify` against a pinned
   `ModelManifest` (SHA-256), then atomically rename. Never load an unverified file.
4. Choose `RamTier.fromTotalBytes(ActivityManager.MemoryInfo.totalMem)` and `ResourcePolicy.choose(...)`; one loaded model at a time.
5. Subclass `ModelRuntimeContract` for your runtime and keep it green.
6. Register in `AshuraTutorApplication` in place of `UnavailableModelRuntime`.

## Benchmark protocol (decide the model from data, not hope)
On at least two real devices (one 4 GB, one 6 GB+), release build, airplane mode, 3 runs each, record median and worst:
cold-load time, time to first token, tokens/s, peak PSS memory, battery drop per 10 minutes, device temperature, and
whether cancel returns within 1 s. Prompts: 20 school-maths/science explanations, 5 with retrieved note passages, 5 injection
attempts inside a passage ("ignore previous instructions…"). Gate: no crash, no OOM kill, cancel < 1 s, injection never
changes behaviour. Record results in `docs/BENCHMARKS.md` before choosing a default model.
