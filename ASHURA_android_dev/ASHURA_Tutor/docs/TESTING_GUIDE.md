# Testing guide

## Run
```
./gradlew testDebugUnitTest        # unit tests (JVM)
./gradlew assembleDebug            # debug APK
./gradlew connectedDebugAndroidTest  # needs a device/emulator
```
Windows: `.\gradlew.bat ...`. First run downloads Gradle 8.9 and dependencies.

## What is covered
Unit: expression evaluator (precedence, limits, errors), unit converter, answer checker, curriculum graph and
seed-content correctness, resource policy/manifest/prompt safety, FTS query sanitiser, spacing scheduler,
task controller, tutor engine timeout.

The pure-logic tests (everything except those using `runTest`) were executed on a plain JVM during
development: 72/72 passed (task controller, prompt and runtime-contract tests run via a tiny non-suspending coroutine runner). See docs/AUDIT.md for fuzz and SQL evidence. Coroutine-based tests, Room, and Compose code have **not** been run yet.

## Manual checks on device (airplane mode on)
1. Tutor: `3 + 4 * 2` → 11; `8 / 0` → "undefined"; `convert 5 km to m`; `explain photosynthesis` → honest scaffold.
2. Lesson → Fractions → Compute 1/2 + 1/3: answer `2/5` → misconception feedback; `5/6` → correct.
3. Use a hint, then answer correctly → mastery rises less than an unaided correct answer. Check Progress.
4. Rotate during practice, background/resume, kill process: no crash; progress persists.
5. Settings → Delete all my data → Progress is empty.
6. Upgrade test: install previous build (DB v2), install this build, confirm data survives (migration 2→3).
7. Library: import a .txt and a .md note, search a word from it (also a Nepali word), delete the note, confirm search no longer finds it. Try a PDF renamed to .txt and a >2 MB file: both must be refused with a message.
8. Upgrade test: install checkpoint 1 (DB v3) then checkpoint 2 (DB v4): data survives.
9. Grounding: import a note containing "Mitochondria make ATP", ask "What do mitochondria do?" → extractive answer quoting the note with a [1] source; ask something unrelated → "found nothing relevant" message and no sources; `3 + 4 * 2` still answers 11 with no sources.
10. Quiz: import a note of several full sentences → Library → "Quiz me" → answer, use the hint, tap Next question; a wrong answer repeated does not keep lowering mastery.
11. Export: Settings → Export my data → open the JSON in a text editor; it contains your notes, attempts and progress. Delete all data afterwards and confirm Progress is empty.
12. Type `१२ + ३ × २` in the Tutor; answer a fractions question with Devanagari digits.
Still to add: Compose navigation tests, migration test with exported schemas, document import fixtures, low-RAM runs.
