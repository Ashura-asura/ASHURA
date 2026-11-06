# Testing guide

Tests are source files only and have not been executed here.

Unit test coverage: arithmetic, division by zero, honest no-model fallback, and blank input.
Extend with malformed expressions, overflow, locale decimals, timeout, cancellation, context bounds,
repository transactions, Room migration, and persistence.

Instrumentation smoke test: activity launch. Add Compose navigation, keyboard/insets, process
recreation, document import, low-memory lifecycle, and database tests.

Manual checks: airplane mode; arithmetic and non-arithmetic prompts; rotation with keyboard open;
background/resume; cold-start and RAM measurement on 4GB hardware; verify no network calls.
