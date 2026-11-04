"""P22/P24/P25: adaptive-memory stress tests versus FTS5.

Questions:
  * partial cues: how much of the key can be missing before recall fails?
  * noisy recall: do distractor tokens in the query break it?
  * capacity: how does accuracy scale with the number of facts?
  * long-run interference: thousands of writes across task switches and contradictory updates.
  * IDF: does down-weighting common tokens matter? (P25)

Synthetic, author-written, single model size; NOT evidence of semantic understanding.

    python -m experiments.adaptive_memory.stress
"""
from __future__ import annotations

import json
import random
import statistics
import time
from pathlib import Path

from experiments.adaptive_memory.run import (acc_memory, codebook, fts_acc, make_task)
from memory.adaptive_memory import AdaptiveMemory, AMemConfig

SEEDS = [1, 2, 3]
DIM = 256


def _facts(seed: int, n: int):
    rng = random.Random(seed)
    facts = make_task(rng, "A", n)
    return facts, codebook(rng, facts, "A")


def partial_cue(seed: int, fraction: float) -> dict:
    facts, cb = _facts(seed, 100)
    mem = AdaptiveMemory(AMemConfig(dim_k=DIM, dim_v=DIM))
    for q, _, v in facts:
        mem.write(q, v)
    V = mem.candidate_matrix(cb)
    items = []
    for q, _, v in facts:
        toks = q.split()
        entity = next((t for t in toks if t.lower().startswith("p") and t[1:].isdigit()), toks[-1])
        others = [t for t in toks if t != entity]
        keep = round(len(others) * fraction)
        items.append((" ".join([entity] + others[:keep]), v))
    exact = [(q, v) for q, _, v in facts]
    return {"cue_fraction": fraction,
            "partial_acc": round(acc_memory(mem, items, cb, V), 4),
            "full_acc": round(acc_memory(mem, exact, cb, V), 4)}


def noisy(seed: int, distractors: int) -> dict:
    facts, cb = _facts(seed, 100)
    mem = AdaptiveMemory(AMemConfig(dim_k=DIM, dim_v=DIM))
    for q, _, v in facts:
        mem.write(q, v)
    V = mem.candidate_matrix(cb)
    rng = random.Random(seed + 100)
    vocab = "alpha beta gamma delta epsilon zeta theta noise filler".split()
    items = [(q + " " + " ".join(rng.choices(vocab, k=distractors)), v) for q, _, v in facts]
    return {"distractors": distractors, "accuracy": round(acc_memory(mem, items, cb, V), 4)}


def capacity(seed: int, n: int) -> dict:
    facts, cb = _facts(seed, n)
    mem = AdaptiveMemory(AMemConfig(dim_k=DIM, dim_v=DIM, idf=True))
    t0 = time.perf_counter()
    for q, _, v in facts:
        mem.write(q, v)
    write_ms = (time.perf_counter() - t0) * 1000 / n
    V = mem.candidate_matrix(cb)
    exact = [(q, v) for q, _, v in facts]
    related = [(pq, v) for _, ps, v in facts for pq in ps]
    return {"facts": n, "exact": round(acc_memory(mem, exact, cb, V), 4),
            "related": round(acc_memory(mem, related, cb, V), 4),
            "fts_exact": round(fts_acc(facts, exact), 4),
            "fts_related": round(fts_acc(facts, related), 4),
            "write_ms": round(write_ms, 4), "params": mem.param_count}


def idf_comparison(seed: int) -> dict:
    facts, cb = _facts(seed, 100)
    out = {}
    for use_idf in (False, True):
        mem = AdaptiveMemory(AMemConfig(dim_k=DIM, dim_v=DIM, idf=use_idf))
        for q, _, v in facts:
            mem.write(q, v)
        V = mem.candidate_matrix(cb)
        out["idf" if use_idf else "no_idf"] = round(
            acc_memory(mem, [(q, v) for q, _, v in facts], cb, V), 4)
    return out


def long_run(seed: int, rounds: int = 8, per_round: int = 250) -> dict:
    rng = random.Random(seed)
    tasks = {k: make_task(rng, k, per_round) for k in ("A", "B", "C")}
    books = {k: codebook(rng, tasks[k], k, n_distract=200) for k in tasks}
    mem = AdaptiveMemory(AMemConfig(dim_k=128, dim_v=128, idf=True))
    V = {k: mem.candidate_matrix(books[k]) for k in tasks}
    history = []
    for r in range(rounds):
        kind = "ABC"[r % 3]
        for q, _, v in tasks[kind]:
            mem.write(q, v)
        row = {"round": r + 1, "task": kind}
        for k in tasks:
            heldout = [(q, v) for q, _, v in tasks[k]]
            row[f"{k}_exact"] = round(acc_memory(mem, heldout, books[k], V[k]), 4)
        history.append(row)
    # contradictory updates: direct writes, to show why a gate is required
    contradict = tasks["A"][:100]
    wrong = []
    for q, _, v in contradict:
        alt = str(int(v) + 1) if v.isdigit() else v + "x"
        mem.write(q, alt)
        wrong.append(alt)
    overwritten = sum(mem.recall(q, books["A"], V["A"])[0] == w
                      for (q, _, _), w in zip(contradict, wrong)) / len(contradict)
    return {"rounds": history, "contradictory_writes": len(contradict),
            "old_answer_overwritten": round(overwritten, 4)}


if __name__ == "__main__":
    out = {"experiment": "P22/P24/P25", "dim": DIM, "seeds": SEEDS, "results": {}}
    out["results"]["partial_cue"] = [
        {k: round(statistics.mean(x[k] for x in rows), 4) if isinstance(rows[0][k], float) else rows[0][k]
         for k in rows[0]}
        for f, rows in ((f, [partial_cue(s, f) for s in SEEDS]) for f in (1.0, 0.75, 0.5, 0.35, 0.25))]
    out["results"]["noisy"] = [
        {k: round(statistics.mean(x[k] for x in rows), 4) if isinstance(rows[0][k], float) else rows[0][k]
         for k in rows[0]}
        for d, rows in ((d, [noisy(s, d) for s in SEEDS]) for d in (0, 2, 5, 10))]
    out["results"]["capacity"] = [
        {k: round(statistics.mean(x[k] for x in rows), 4) if isinstance(rows[0][k], float) else rows[0][k]
         for k in rows[0]}
        for n, rows in ((n, [capacity(s, n) for s in SEEDS]) for n in (50, 100, 200, 400))]
    out["results"]["idf"] = {
        k: round(statistics.mean(idf_comparison(s)[k] for s in SEEDS), 4) for k in ("no_idf", "idf")
    }
    out["results"]["long_run"] = long_run(1)
    print(json.dumps(out, indent=2))
    Path("experiments/adaptive_memory/stress.json").write_text(json.dumps(out, indent=2))
