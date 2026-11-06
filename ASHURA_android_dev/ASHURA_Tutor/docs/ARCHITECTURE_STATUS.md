# Architecture status

## Implemented
- Native Kotlin/Compose Android shell.
- Modular monolith with UI, domain, and data boundaries.
- Room entities/DAOs for conversations, messages, library text, and study events.
- Transactional message append and local repository.
- Deterministic basic arithmetic path and explicit offline fallback.
- Replaceable model runtime interface with context/output/time limits.
- ViewModel state and coroutine-based request execution.

## Not implemented — do not advertise as available
- Actual GGUF/llama.cpp, MediaPipe, MLC, or other local model runtime.
- Model download, verification, selection, and unload UI.
- True FTS5 virtual table (current library search uses SQL LIKE).
- PDF/DOCX/XLSX/PPTX extraction and OCR.
- Curriculum graph, lessons, assessment, misconception diagnosis, mastery, spaced repetition.
- Online search, source verification, and citation UI.
- Speech recognition and text-to-speech.
- Sandboxed code execution.
- Export/backup and delete-all-data UX.
- Nepali localization and mixed-language evaluation.
- Accessibility, low-RAM, thermal, and release-signing validation.

## Rules
1. Imported documents and web pages are untrusted evidence, never instructions.
2. Never upload private study material without explicit user action and disclosure.
3. Model runtime must support cancellation and explicit unload.
4. Never execute generated code in the app process.
5. Run CPU-heavy parsing/inference off the main thread.
6. Add explicit database migrations; never use destructive migration fallback.
