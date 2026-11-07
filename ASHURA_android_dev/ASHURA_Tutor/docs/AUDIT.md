# Deep audit — ASHURA Tutor (Android)

Scope: all code written in checkpoints 1–3 + UI review + final checkpoint. Method: static review; execution of the real
migration/FTS SQL against SQLite 3.45; fuzzing and stress tests on a JVM (kotlinc 2.0.21). **A later integration checkpoint
(see the last section) compiled and unit-tested the Android project with Gradle.** Device execution remains open (O1, O4).

## Evidence gathered
| Check | Result |
|---|---|
| Pure unit tests (JUnit API shimmed) | 72 passing (69 + 3 runtime-contract) |
| Evaluator fuzz: 300 000 random strings + 100 000 structured expressions + 20 adversarial cases | 0 exceptions, worst case 13 ms |
| Answer checker fuzz: 200 000 random inputs + 23 hostile answers (100 kB digits, `1/0`, NaN, `1e999`, NULs…) | 0 exceptions, ≤ 8 ms |
| Query builder fuzz: 100 000 random Unicode strings; 7 hostile FTS strings run through real FTS5 | 0 exceptions / 0 SQL errors |
| Text import at the 2 MB cap (spaces, newlines, one long token, dense `. `, Devanagari prose) | all ≤ 150 ms after fix |
| Migrations 1→2→3→4 executed on SQLite and compared with the schema derived from the Room entities (columns, types, nullability, defaults, FKs, indexes) | 0 mismatches over 9 entities |
| FTS behaviour on SQLite: ranking, OR questions, Devanagari prefix, trigger sync, cascade delete, `integrity-check` | all correct |
| JSON export parsed by a strict parser (Python `json`) incl. control chars, U+2028, emoji, Devanagari | valid |

## Findings fixed in this pass
| # | Sev | Finding | Fix |
|---|---|---|---|
| F1 | High | `TextChunker.normalize` used regexes that are quadratic on whitespace runs: 31 s for 160 k spaces, hours at the 2 MB cap → a crafted or accidental file freezes import | Rewritten as a linear scan; regression tests (2 MB in 82 ms) |
| F2 | Med | Devanagari/Arabic-Indic digits (१५) were unreadable as answers and in the calculator | `DigitNormalizer` applied to checker, evaluator, converter, router |
| F3 | Med | "Delete all data" during an in-flight question could write to erased rows and show an error | Pending jobs cancelled first |
| F4 | Med | Mastery gaming: retry-until-correct counted as independent success; each repeated wrong try cut mastery again | First wrong lowers mastery once; success after a failed try counts as assisted |
| F5 | Low | Unit-converter regex ran on unbounded text | 120-char guard |
| F6 | Low | No explicit Android 12+ data-extraction rules | Rules exclude everything from cloud backup and device transfer |

## Open findings (not fixed here)
| # | Sev | Finding | Recommendation |
|---|---|---|---|
| O1 | **High** | ~4 000 lines of Android code (Compose, Room DAOs, ViewModel, SAF) have never been compiled or run | Gradle `assembleDebug testDebugUnitTest lintDebug` now passes (139 tests); **running on a device is still unverified** |
| O2 | Med | No Room schema JSON committed, so `MigrationTestHelper` tests cannot exist yet (SQL itself is verified) | Resolved in a later checkpoint: schemas 1–4 committed and `MigrationTest` runs |
| O3 | Med | Database and export file are unencrypted at rest (Android sandbox + disk encryption only) | Decide threat model; SQLCipher or Keystore-wrapped key if notes are sensitive |
| O4 | Med | No real model runtime; tutoring beyond curriculum/notes is a scaffold | Runtime integrated (LiteRT-LM 0.19.1, pinned catalog, verified download/import). Device load, latency and memory benchmarks remain |
| O5 | Med | All UI strings hard-coded English; no Nepali | Addressed: `values-ne` exists; native-speaker review still required |
| O6 | Low | Keyword-only retrieval; paraphrases miss; generated answers are not checked against sources | Add embeddings later; add support check |
| O7 | Low | Lists use `Column.forEach`; fine for tens of items | `LazyColumn` |
| O8 | Low | Cloze quiz quality is modest (one key term per sentence; multi-word answers collapse spaces) | Add multiple-choice distractors from the same note |
| O9 | Low | Release build unsigned, default launcher icon, no CI secrets | Before any store upload |
| O10 | Info | Chunk/item FTS5 are external-content tables keyed by implicit `rowid` of TEXT-PK tables; stable in tests incl. `VACUUM`, but SQLite does not guarantee it | If VACUUM is ever introduced, follow with FTS `'rebuild'` |
| O11 | Info | Content is a 4-topic seed pack | Author and test-verify more topics (same pattern) |

## Security / privacy review
No `INTERNET` permission, no network code, no analytics, no secrets in the repo. Imported text is untrusted: stored, searched,
rendered as plain text, delimited and control-token-stripped in prompts; FTS input is quoted per token (verified against
real FTS5). File reads are streamed with a hard size cap; stored URIs are not kept. Backup disabled. Logging records exception
objects only, never user text. Remaining exposure: O3.

## Runtime integration checkpoint (v0.3.0)
| Check | Result |
|---|---|
| Toolchain | Kotlin 2.4.0, AGP 8.13.2, Gradle 8.14.4, KSP 2.3.13, Room 2.8.5, compile/target SDK 35, minSdk 26 |
| Build | `:app:assembleDebug` succeeds; `:app:compileDebugKotlin` succeeds |
| Unit tests | 115/115 passing on the JVM, including catalog pinning, prompt-parts, and LiteRT-LM refusal paths |
| Static checks | `lintDebug` runs with `abortOnError = true` |
| Runtime | LiteRT-LM 0.19.1, single mutex-guarded engine, CPU backend, one model slot, app-scoped manager |
| Model supply chain | HTTPS-only, exact revision + size + SHA-256, `.part` + atomic rename, 1 GB reserve, one-model enforcement |
| Packaging | Only `arm64-v8a` and `x86_64`; weights are never bundled; R8 keep rules for LiteRT-LM JNI |

New residual risks:
- The two pinned model URLs and hashes were taken from published repository metadata but have **not** been re-downloaded and
  re-hashed in this environment. Verify both artifacts once on a real device before a public release.
- Loading, generation, cancellation under load, peak memory and thermal behaviour are unmeasured on hardware.
- The GPU backend is not exercised; CPU is the default.
- The debug APK is ~65 MB (native AAR), above GitHub's 50 MB guidance. Prefer release artifacts outside Git history later.

## Streaming and learning-UX checkpoint (v0.4.0)
| Check | Result |
|---|---|
| Build | `:app:assembleDebug`, `:app:lintDebug`, `:app:testDebugUnitTest` succeed |
| Unit tests | 139/139 passing, adding `StructuredAnswerTest`, `StreamingTest`, `LearnerProfileStoreTest` and direct/Socratic prompt tests |
| Streaming | Native deltas go through `channelFlow`; deterministic tools stay single-shot; model failure degrades to the offline scaffold; no delta is emitted after `Complete` |
| Structured output | Markers are parsed tolerantly; unrecognised output is preserved as plain text; steps are capped at 8 |
| Profile | Level/style/language persist locally; unknown enum names and unsupported language codes fall back to safe defaults |
| Diagnostics | Load/first-token/generation timings, approximate tokens/s, heap and free storage are measured, explicitly labelled approximate where needed |
| Privacy | Profile is a plain SharedPreferences file on device; no account, sync or upload path was added |

New residual risks:
- Streaming cadence, cancellation latency and the final-answer replacement have not been observed on hardware.
- Token counts are estimated from characters because the current LiteRT-LM API does not expose them; treat tokens/s as indicative.
- A small model may ignore the requested `ANSWER`/`STEPS`/`CHECK` structure; the parser then shows plain text rather than inventing sections.
- Socratic mode is prompt-enforced, not guarantee-enforced; a model can still reveal the answer.


## Document, chat and study-pack checkpoint (v0.5.0)
| Check | Result |
|---|---|
| Build | `:app:assembleDebug`, `:app:lintDebug`, `:app:testDebugUnitTest` succeed |
| Unit tests | 151/151 passing, adding `DocumentQuizTest`, `PdfTextExtractorTest`, `StudyPackRepositoryTest` and PDF/image cases in `TextChunkerTest` |
| Model lifecycle | No automatic unload remains; startup `autoLoadInstalled()` loads a verified model, explicit unload only |
| Chat | Streaming bubbles, stop, mode/citation footnotes, pinned composer, empty-state suggestions; legacy answer fields retained for compatibility |
| Import | Text/Markdown, PDF (embedded text), PNG/JPEG/WebP (OCR), DOCX/XLSX/PPTX (in-memory OOXML); per-format caps and page/slide/sheet markers |
| Provenance | Section labels flow into `PassageRef`, `GroundingPolicy` citations and quiz prompts; chunking starts a new chunk at every marker |
| Quiz | Up to 20 mixed items: ≤12 cloze, ≤6 definitions, explanation prompts; deterministic, deduplicated, section-aware; self-assessed model answers shown after rating |
| Study packs | 10 subjects × 20 notes = 200 Markdown assets; manifest with source URL, CC BY-SA 4.0, size and SHA-256; checksum verified before import |
| Privacy | Study notes are bundled; no runtime download, account, sync or upload path was added |

New residual risks:
- The 200 Wikipedia extracts are lead-section summaries; some are short (≈550–800 characters) and will yield fewer than 20 unique questions. The UI reports the actual count rather than padding with invented items.
- OCR quality, model residency, chat IME/scroll behaviour and PDF/PPTX extraction quality are untested on hardware.
- The debug APK is now ~99 MB, above GitHub's 50 MB guidance, because ML Kit's bundled OCR models ship inside it. Prefer a release artifact or split ABI/OCR bundles for distribution later.
- The study-pack content is CC BY-SA 4.0, not the application licence; redistribution must preserve attribution and share-alike terms (see `assets/study_sets/LICENSE.md`).
