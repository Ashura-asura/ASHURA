# Session changes (gap-closing pass)

Integrated into the main tree and verified here with `./gradlew :app:testDebugUnitTest :app:lintDebug
:app:assembleDebug` (173 JVM tests, 0 failures; lint and APK assembly pass).

1. Honest confidence labels (spec §12): `domain/ConfidenceLabel.kt`, shown under every tutor answer (EN + NE strings).
   Wording deliberately says individual claims are not checked: claim-level verification (§12.4) is still missing.
2. Clear chat history (spec §15.3): DAO deleteAll, `TutorRepository.clearChatHistory`,
   `TutorViewModel.clearChatHistory`, Settings button + confirm dialog. Notes, progress and attempts are kept.
3. Hint ladder / stuck detection (spec §3.3): `domain/assessment/HintLadder.kt`, wired into PracticeScreen as a
   nudge; guaranteed path to the worked solution.
4. Direct-answer override: `HintLadder.asksForDirectAnswer` is now wired into the Socratic chat style, so “just
   tell me” gives a direct explanation for that answer without changing the saved style preference.

Tests added: `ConfidenceLabelTest`, `HintLadderTest`.

Still not done: explain-my-mistake, import status UI, original-file storage, and the rest of the audit.
