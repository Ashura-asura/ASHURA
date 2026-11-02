"""Step 3: FTS5 retrieval latency vs corpus size.  python -m evaluation.retrieval_bench"""
import os, random, tempfile, time

from memory.database import Database
from memory.fts import FTS5Index
from .latency import percentile

WORDS = [f"w{i}" for i in range(5000)]


def bench(n: int, queries: int = 200, seed: int = 0) -> dict:
    rng = random.Random(seed)
    path = os.path.join(tempfile.mkdtemp(), "b.db")
    db = Database(path); idx = FTS5Index(db)
    rows = [(f"id{i}", " ".join(rng.choices(WORDS, k=30))) for i in range(n)]
    db.conn.executemany("INSERT INTO fts_index(memory_id, text) VALUES (?,?)", rows); db.conn.commit()
    lat = []
    for _ in range(queries):
        q = " ".join(rng.choices(WORDS, k=4))
        s = time.perf_counter(); idx.search(q, limit=5); lat.append((time.perf_counter() - s) * 1000)
    db.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    r = {"rows": n, "p50_ms": percentile(lat, 50), "p95_ms": percentile(lat, 95), "db_mb": os.path.getsize(path) / 1e6}
    db.close(); return r


if __name__ == "__main__":
    print(f"{'rows':>8} {'p50 ms':>8} {'p95 ms':>8} {'db MB':>8}")
    for n in (1_000, 10_000, 50_000, 200_000):
        r = bench(n); print(f"{r['rows']:>8} {r['p50_ms']:>8.3f} {r['p95_ms']:>8.3f} {r['db_mb']:>8.1f}")
