# Session changes (gap-closing pass)

Integrated into the main tree and verified here with `./gradlew clean :app:testDebugUnitTest :app:lintDebug
:app:assembleDebug` (212 JVM tests, 0 failures; lint and APK assembly pass).

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
10. Timed tests (spec §3.4/§3.5): Library offers Quick 20, Medium 35 and Long 50 questions. The timer is
    chosen from the mode (60 s/question), questions are deterministic four-option “choose the best answer”
    items built from imported notes, and there are no fill-in-the-blank or free-text items. Each result saves
    obtained marks, percentage, time taken and timeout state; Progress lists the history with the marks change
    from the previous test of the same mode. A single note can start a shorter Quick test.
11. Study-set added state (spec §8): every subject shows “X of Y added”; added sets show a check mark and a
    minus action (remove after confirmation), unadded sets show “+ Add”. “Add all” is disabled when the whole
    subject is present. Removing a set deletes only that note and its passages; other notes and test results
    stay.
12. Database v5: `test_results` table with an additive 4→5 migration and a v4→v5 upgrade test; test results
    are included in JSON export and wiped by delete-all-data.
13. Diagnostics export (P1.2, partial): Settings can save `ashura-diagnostics.json` containing measured
    runtime counters and device/RAM/storage metadata. It contains no learner text and has an exact-key test.
    p50/p95, battery drain, thermal status and peak-RAM sampling still need a real device run.
14. Home screen (P4.6/§3.2): continue card, Ask/Learn/Import/Review tiles, three recent items, model and
    offline status, privacy line. Import now shares one MIME list with Library and switches to Library so
    progress is visible. Device layout and TalkBack remain unverified.
15. Library (P4.7/§3.4): split into Material / Study sets / Tests; Material filters All/Recent/Documents/Notes;
    tapping an item opens a detail dialog with format, size, date, index state, test, edit, re-index and
    delete. Removed the long single scroll. Device layout and TalkBack remain unverified.
16. Tutor phases (§3.3): “Searching your notes…” then “Writing the answer…” in the streaming bubble, cleared
    on success/error/cancel. Progress (§3.5): practised/due/tests counts and qualitative mastery bands instead
    of mastery/evidence percentages. Device layout and TalkBack remain unverified.
17. Model-unavailable banner in Tutor with a Set up action (§3.3); typing dots render statically when system
    animations are off (§3.6). Device behaviour remains unverified.
18. Home model-status line gains a Set up action that opens Settings when no model is ready.
19. Progress: a due topic now has a Review action that starts the topic and opens Tutor.
20. Launch: brand screen shortened to 900 ms and made skippable by tapping; added a “Tap to continue” hint.
21. Lesson: a Practice action in the top bar starts the first practice question without scrolling.

Tests added: `ChoiceQuizBuilderTest`, `TestSessionTest`, `TestModeTest`, `TestHistoryTest`,
`DataControlsTest`, plus the v4→v5 migration case. `ImportStatusTest`, `MistakeExplainerTest`,
`GenerationLimitsTest`, `ConfidenceLabelTest` and `HintLadderTest` remain.

Not done: active-test persistence across process death, edit message, semantic search, OCR confidence/region
selection, programming sandbox, everything hardware-dependent.
22. Tutor: conversation memory, sanitized answers (no prompt placeholders or hidden reasoning), Unicode maths
    rendering, question/answer/conversation copy, longer derivations, and same-note test distractors.
23. Tutor: a Continue action resumes a truncated derivation from the replayed conversation.
24. Tutor: Try again recovery, stored-history rewind on regenerate/retry, and correct retry of a Continue turn.
25. Tutor: citations beyond the retrieved-note count are stripped from model answers.
26. Tutor: citation cleaning no longer removes array indexes such as `a[1]`.
