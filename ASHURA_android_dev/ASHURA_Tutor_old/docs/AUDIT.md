# Deep audit — ASHURA Tutor (Android)

Scope: all code written in checkpoints 1–3 + UI review + final checkpoint. Method: static review; execution of the real
migration/FTS SQL against SQLite 3.45; fuzzing and stress tests on a JVM (kotlinc 2.0.21). **Not done:** compiling Android/Compose/Room,
running on a device — see Open O1.

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
| O1 | **High** | ~4 000 lines of Android code (Compose, Room DAOs, ViewModel, SAF) have never been compiled or run | `./gradlew assembleDebug testDebugUnitTest`; send me the output |
| O2 | Med | No Room schema JSON committed, so `MigrationTestHelper` tests cannot exist yet (SQL itself is verified) | Commit `app/schemas/*.json` after first build; add migration tests 1→4 |
| O3 | Med | Database and export file are unencrypted at rest (Android sandbox + disk encryption only) | Decide threat model; SQLCipher or Keystore-wrapped key if notes are sensitive |
| O4 | Med | No real model runtime; tutoring beyond curriculum/notes is a scaffold | Follow `RUNTIME_INTEGRATION.md`; benchmark on two devices |
| O5 | Med | All UI strings hard-coded English; no Nepali | Move to `strings.xml` + `values-ne`; native-speaker review |
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
