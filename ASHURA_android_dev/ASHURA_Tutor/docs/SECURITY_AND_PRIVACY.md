# Security and privacy baseline

- No account, ads, analytics, or mandatory backend is included.
- Android backup and device-transfer extraction are disabled for all app data.
- Local study data stays on-device unless the user invokes the explicit JSON export.
- Imported content is untrusted input and cannot change tutor policy or tool permissions.
- Do not render imported HTML as trusted executable content.
- Never run generated code with application process permissions.
- The app is offline by default. The only network operation is a user-initiated model download from the HTTPS URL pinned in
  `ModelCatalog`; questions, notes, progress and prompts are never transmitted.
- `INTERNET` and `ACCESS_NETWORK_STATE` exist solely for that download. `ModelManager` is the only class that opens a
  connection, and it refuses non-HTTPS URLs, an offline device, an active second install, or insufficient storage.
- Every model artifact is pinned by exact revision, byte size and SHA-256. Downloads stream to `.part`, are hashed while
  writing, checked against the catalog, then atomically renamed. A mismatch is deleted and reported, never loaded.
- SAF imports are accepted only when the file's size and SHA-256 match a catalog entry, so a renamed or tampered file cannot
  become a "model".
- Model weights are never committed to the APK or repository. Device-only benchmarks and residual risks are tracked in
  `docs/AUDIT.md` and `docs/RUNTIME_INTEGRATION.md`.
- Logging records exception objects only, never user text. Prompts delimit and control-token-strip imported evidence.
- Implement user-facing delete-all-data before public release (already present) and keep the release keystore outside the
  repository (`keystore.properties` or `ASHURA_KEYSTORE_*` environment variables).
