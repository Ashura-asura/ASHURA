PRAGMA foreign_keys = ON;

-- Episodic memory: what happened (spec 5.1.B)
CREATE TABLE IF NOT EXISTS experiences (
    id                  TEXT PRIMARY KEY,
    ts                  REAL NOT NULL,
    input               TEXT NOT NULL,
    output              TEXT NOT NULL,
    task_category       TEXT NOT NULL DEFAULT 'general',
    source              TEXT NOT NULL DEFAULT 'interaction',
    verification_status TEXT NOT NULL DEFAULT 'unverified',
    verification_method TEXT NOT NULL DEFAULT '',
    reliability         REAL NOT NULL DEFAULT 0.2,
    outcome             TEXT NOT NULL DEFAULT 'unknown',
    content_hash        TEXT NOT NULL,
    repeat_count        INTEGER NOT NULL DEFAULT 1,
    related_ids         TEXT NOT NULL DEFAULT '[]',
    input_norm          TEXT NOT NULL DEFAULT ''   -- normalised input, indexed for conflict lookups
);
CREATE INDEX IF NOT EXISTS idx_exp_category ON experiences(task_category);
CREATE INDEX IF NOT EXISTS idx_exp_status   ON experiences(verification_status);
CREATE INDEX IF NOT EXISTS idx_exp_hash     ON experiences(content_hash);
CREATE INDEX IF NOT EXISTS idx_exp_ts       ON experiences(ts);

-- Semantic memory: reliable information (spec 5.1.C). Only reliable facts land here.
CREATE TABLE IF NOT EXISTS facts (
    id            TEXT PRIMARY KEY,
    text          TEXT NOT NULL,
    source_exp_id TEXT REFERENCES experiences(id) ON DELETE SET NULL,
    reliability   REAL NOT NULL,
    ts            REAL NOT NULL
);

-- Full-text index (FTS5). memory_id is stored but not tokenised.
CREATE VIRTUAL TABLE IF NOT EXISTS fts_index USING fts5(
    memory_id UNINDEXED,
    text,
    tokenize = 'porter unicode61'
);

-- Every AMA decision and its reason (spec 6.2 step 10)
CREATE TABLE IF NOT EXISTS admission_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        REAL NOT NULL,
    exp_id    TEXT,
    decision  TEXT NOT NULL,
    score     REAL,
    features  TEXT NOT NULL,
    reason    TEXT NOT NULL
);

-- Queue of verified experiences awaiting DREAM / neural memory (spec 6.3)
CREATE TABLE IF NOT EXISTS dream_queue (
    exp_id TEXT PRIMARY KEY REFERENCES experiences(id) ON DELETE CASCADE,
    queue  TEXT NOT NULL,        -- 'dream' | 'neural_memory'
    ts     REAL NOT NULL
);

-- Deletion integrity (spec Phase 1: "deleted correctly"). Enforced in the database so that no code
-- path, including raw SQL, can leave a deleted experience searchable or quoted as a fact.
-- BEFORE DELETE so the facts are removed before the ON DELETE SET NULL action would orphan them.
CREATE TRIGGER IF NOT EXISTS trg_exp_delete_facts BEFORE DELETE ON experiences
BEGIN
    DELETE FROM facts WHERE source_exp_id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_exp_delete_fts AFTER DELETE ON experiences
BEGIN
    DELETE FROM fts_index WHERE memory_id = OLD.id;
END;
