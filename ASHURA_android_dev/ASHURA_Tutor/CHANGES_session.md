# Session changes (gap-closing pass)

Integrated into the main tree and verified here with `./gradlew :app:testDebugUnitTest :app:lintDebug
:app:assembleDebug` (190 JVM tests, 0 failures; lint and APK assembly pass).

1. Honest confidence labels (spec §12): `domain/ConfidenceLabel.kt`, shown under every tutor answer (EN + NE strings).
   Wording deliberately says individual claims are not checked: claim-level verification (§12.4) is still missing.
2. Clear chat history (spec §15.3): DAO deleteAll, `TutorRepository.clearChatHistory`,
   `TutorViewModel.clearChatHistory`, Settings button + confirm dialog. Notes, progress and attempts are kept.
3. Hint ladder / stuck detection (spec §3.3): `domain/assessment/HintLadder.kt`, wired into PracticeScreen as a
   nudge; guaranteed path to the worked solution.
4. Chat history (ChatGPT/Claude-style): History button in the chat header lists saved conversations; tap to reopen,
   bin icon to delete one. New chats are titled from the first question. Reopened chats show text and answer type
   only (per-message citations are not stored).
5. "Just tell me the answer" now switches that one request from Socratic to direct
   (`HintLadder.asksForDirectAnswer` wired into `ask()`).
6. Explain my mistake (spec §3.4): `domain/assessment/MistakeExplainer.kt`; button after a wrong practice answer
   shows comparison, why (known misconception, sign slip, decimal slip, larger/smaller), method, next step.
   Deterministic only: it does not find the "first incorrect step" because working is not captured.
7. Regenerate: button on the latest tutor answer re-asks the last question. The old answer stays in stored history
   (the question is saved twice).
8. Library import status: each imported item shows character size, passage count and date added;
   `ImportStatus` and `ChunkDao.observeCounts` drive a “not indexed” state with a Re-index button
   (`TutorRepository.reindexLibraryItem`). Before the first database read the old character count is shown,
   so there is no false “not indexed” flash.
9. Full derivations: the answer budget is now 512 tokens / 120 s instead of 384 / 45 s, the direct prompt
   requires the whole derivation and forbids “the question is too long”, and derivation phrases switch
   Socratic mode to a direct answer.

Tests added: `ImportStatusTest`, `MistakeExplainerTest`, `GenerationLimitsTest`, `ConfidenceLabelTest`,
`HintLadderTest`.

Not done: edit message, semantic search, OCR confidence/region selection, programming sandbox, everything
hardware-dependent.
