"""EXP-004: Titans-inspired adaptive memory vs FTS5 vs no memory.   python -m experiments.adaptive_memory.run

Tasks: key = a question, value = a short payload (code). Memory returns a vector; it is decoded by
nearest-neighbour among a codebook (all test payloads + 1000 distractors).
 * exact   : same question text that was written
 * related : UNSEEN paraphrases of the question (different wording, same entity token)
 * interference: learn task A, then unrelated task B, re-test A
LIMITATIONS: synthetic data written by the author; key features are bags of tokens, so "related" here
means lexical overlap on the entity token - the memory has no semantic generalisation to test.
"""
from __future__ import annotations

import json
import random
import statistics
import time

import numpy as np

from memory.adaptive_memory import AdaptiveMemory, AMemConfig
from memory.database import Database
from memory.fts import FTS5Index

A_Q = "what is the access code for project P{i}"
A_PARA = ["project P{i} access code?", "tell me the code of the P{i} project", "access code P{i}"]
B_Q = "when is the birthday of person Q{i}"
B_PARA = ["person Q{i} birthday?", "tell me the birthday of Q{i}", "birthday Q{i} person"]


def make_task(rng, kind: str, n: int):
    if kind == "B":
        q, para = B_Q, B_PARA
    else:                                      # "C" reuses A's wording with different entity tokens
        q, para = (A_Q, A_PARA) if kind == "A" else (A_Q.replace("P{i}", "Z{i}"), [t.replace("P{i}", "Z{i}") for t in A_PARA])
    pay = (lambda: f"m{rng.randint(100, 999)}") if kind == "B" else (lambda: str(rng.randint(1000, 9999)))
    seen, facts = set(), []
    for i in range(n):
        p = pay()
        while p in seen:
            p = pay()
        seen.add(p)
        facts.append((q.format(i=i), [t.format(i=i) for t in para], p))
    return facts


def codebook(rng, facts, kind: str, n_distract=1000):
    cb = {p for _, _, p in facts}
    gen = (lambda: f"m{rng.randint(100, 999)}") if kind == "B" else (lambda: str(rng.randint(1000, 9999)))
    tries = 0
    while len(cb) < len(facts) + n_distract and tries < 100000:
        cb.add(gen()); tries += 1
    return sorted(cb)


def acc_memory(mem: AdaptiveMemory, items, cb, V) -> float:
    ok = sum(mem.recall(q, cb, V)[0] == truth for q, truth in items)
    return ok / len(items)


def fts_acc(facts, items) -> float:
    db = Database(); idx = FTS5Index(db); pay = {}
    for k, (q, _, p) in enumerate(facts):
        idx.add(str(k), q); pay[str(k)] = p
    ok = 0
    for q, truth in items:
        hits = idx.search(q, limit=1)
        ok += bool(hits) and pay[hits[0][0]] == truth
    return ok / len(items)


def train(mem, facts, rng, passes=1):
    order = list(range(len(facts))); rng.shuffle(order)
    t0 = time.perf_counter()
    for i in order:
        mem.write(facts[i][0], facts[i][2], passes)
    return (time.perf_counter() - t0) * 1000 / len(facts)


def one(seed, cfg, n, passes=1):
    rng = random.Random(seed)
    facts = make_task(rng, "A", n)
    cb = codebook(rng, facts, "A")
    mem = AdaptiveMemory(cfg); V = mem.candidate_matrix(cb)
    w_ms = train(mem, facts, rng, passes)
    exact = [(q, p) for q, _, p in facts]
    related = [(pq, p) for _, ps, p in facts for pq in ps]
    t0 = time.perf_counter(); acc_e = acc_memory(mem, exact, cb, V)
    r_ms = (time.perf_counter() - t0) * 1000 / len(exact)
    return {"exact": acc_e, "related": acc_memory(mem, related, cb, V),
            "fts_exact": fts_acc(facts, exact), "fts_related": fts_acc(facts, related),
            "chance": 1 / len(cb), "write_ms": w_ms, "read_ms": r_ms, "params": mem.param_count}


def avg(rows):
    return {k: statistics.mean(r[k] for r in rows) for k in rows[0]}


def interference(seed, cfg, n=100, second="B"):
    rng = random.Random(seed)
    A, B = make_task(rng, "A", n), make_task(rng, second, n)
    cbA, cbB = codebook(rng, A, "A"), codebook(rng, B, second)
    mem = AdaptiveMemory(cfg); VA, VB = mem.candidate_matrix(cbA), mem.candidate_matrix(cbB)
    train(mem, A, rng)
    tA = [(q, p) for q, _, p in A]; tB = [(q, p) for q, _, p in B]
    rA = [(pq, p) for _, ps, p in A for pq in ps]
    before = acc_memory(mem, tA, cbA, VA), acc_memory(mem, rA, cbA, VA)
    train(mem, B, rng)
    after = acc_memory(mem, tA, cbA, VA), acc_memory(mem, rA, cbA, VA)
    b_acc = acc_memory(mem, tB, cbB, VB)
    mem.reset()
    reset_acc = acc_memory(mem, tA, cbA, VA)
    return {"A_exact_before": before[0], "A_exact_after_B": after[0], "A_related_before": before[1],
            "A_related_after_B": after[1], "B_exact": b_acc, "A_after_reset": reset_acc}


VARIANTS = {   # lr is filled in from validation tuning
    "plain delta (no idf)": dict(idf=False),
    "+idf": dict(),
    "+idf +momentum .5": dict(momentum=0.5),
    "+idf +decay .01": dict(decay=0.01),
    "+idf +gate .1": dict(surprise_gate=0.1),
}

GRID = [0.1, 0.2, 0.3, 0.6, 1.0]


def tune(kw, n=100, passes=1):
    """Pick lr per variant on a held-out validation seed (never on reported seeds)."""
    return max(GRID, key=lambda lr: one(100, AMemConfig(lr=lr, **kw), n, passes)["related"])


if __name__ == "__main__":
    SEEDS = [1, 2, 3]
    out = {"lr": {}}
    print("== A. variants, dim 256, N=100 facts, single pass (lr tuned per variant on validation seed 100) ==")
    print(f"{'variant':<22}{'lr':>5}{'exact':>7}{'related':>9}{'write ms':>10}{'read ms':>9}")
    out["variants"], lrs = {}, {}
    for name, kw in VARIANTS.items():
        lrs[name] = tune(kw)
        r = avg([one(s, AMemConfig(lr=lrs[name], **kw), 100) for s in SEEDS]); out["variants"][name] = r
        print(f"{name:<22}{lrs[name]:>5}{r['exact']:>7.3f}{r['related']:>9.3f}{r['write_ms']:>10.3f}{r['read_ms']:>9.3f}")
    lr3 = tune({}, passes=3)
    r = avg([one(s, AMemConfig(lr=lr3), 100, passes=3) for s in SEEDS]); out["variants"]["+idf, 3 passes"] = r
    print(f"{'+idf, 3 passes':<22}{lr3:>5}{r['exact']:>7.3f}{r['related']:>9.3f}{r['write_ms']:>10.3f}{r['read_ms']:>9.3f}")
    f = out["variants"]["+idf"]
    print(f"{'FTS5 baseline':<22}{'':>5}{f['fts_exact']:>7.3f}{f['fts_related']:>9.3f}      (chance = {f['chance']:.4f})\n")
    out["lr"] = lrs; best = lrs["+idf"]

    print("== B. capacity: related-accuracy vs facts stored (+idf, lr tuned at N=100 per dim) ==")
    out["capacity"] = {}
    ns = [100, 200, 400, 800, 1600]
    print(f"{'dim':>5}{'params':>9}{'lr':>5}" + "".join(f"{'N='+str(n):>9}" for n in ns) + f"{'FTS5@1600':>11}")
    for d in (128, 256, 512):
        lr_d = max(GRID, key=lambda lr: one(100, AMemConfig(dim_k=d, dim_v=d, lr=lr), 100)["related"])
        row = {n: avg([one(s, AMemConfig(dim_k=d, dim_v=d, lr=lr_d), n) for s in SEEDS]) for n in ns}
        out["capacity"][d] = {n: row[n]["related"] for n in ns}
        print(f"{d:>5}{d*d:>9}{lr_d:>5}" + "".join(f"{row[n]['related']:>9.3f}" for n in ns) + f"{row[1600]['fts_related']:>11.3f}")

    print("\n== C. interference: learn A (100 facts), then a second task (100 facts), re-test A ==")
    print(f"{'variant / 2nd task':<30}{'A before':>9}{'A after':>9}{'Arel bef':>9}{'Arel aft':>9}{'2nd exact':>10}{'A@reset':>9}")
    out["interference"] = {}
    for second, label in (("B", "unrelated wording"), ("C", "SAME wording, new entities")):
        for name in ["+idf", "+idf +momentum .5", "+idf +decay .01"]:
            r = avg([interference(s, AMemConfig(lr=lrs[name], **VARIANTS[name]), second=second) for s in SEEDS])
            out["interference"][f"{name} | {second}"] = r
            print(f"{(name+' | '+second):<30}{r['A_exact_before']:>9.3f}{r['A_exact_after_B']:>9.3f}{r['A_related_before']:>9.3f}"
                  f"{r['A_related_after_B']:>9.3f}{r['B_exact']:>10.3f}{r['A_after_reset']:>9.4f}")
        print(f"   ({second} = {label})")
    json.dump(out, open("experiments/adaptive_memory/results.json", "w"), indent=2, default=float)
