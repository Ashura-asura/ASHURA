# Implementation roadmap

1. **Owner validation:** open in Android Studio, sync, run tests, install on target device, inspect startup/navigation/RAM.
2. **Offline learning core:** versioned curriculum graph, prerequisites, lessons, examples, hints, practice, rubrics, misconception models, deterministic assessment and explainable feedback.
3. **Library:** Storage Access Framework, PDF text, DOCX paragraphs/tables, XLSX sheets/cells/formulas, PPTX slides/notes, batched OCR with confidence/correction, provenance, actual FTS5 migration.
4. **Local model:** benchmark runtime/model on target hardware; optional user-controlled download and integrity checks; one model at a time; cancellation/unload/thermal controls; deterministic tools first.
5. **Online research:** optional replaceable search provider, citations, dates/domains, source conflict handling; preserve offline operation.
6. **Speech/languages/tools:** benchmark offline speech, Nepali/English and mixed-language tests, simulations, code help. Disable execution until OS-level sandbox exists.

Release gates: unit/integration/instrumentation/migration/parser/privacy tests; accessibility/font scaling; cold start, peak RAM, battery, thermal, cancellation; no offline-mode network traffic; no upgrade data loss.
