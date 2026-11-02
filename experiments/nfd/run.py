"""EXP-003: NFD routing vs always-run fixed pipeline.  python -m experiments.nfd.run

Costs are the registry's PLACEHOLDER estimates (not measured on the target laptop), so the
latency/RAM columns show module-selection behaviour only. Routing overhead is real wall-clock.
"""
import statistics

from brain.controller import Controller, default_registry
from brain.need_field import NeedField, Task, always_all
from foundation.language_model import EchoModel

PROMPTS = [
    ("hello", "chat"), ("how are you today", "chat"), ("tell me a joke", "chat"), ("what is the capital of France", "chat"),
    ("what is 12*7?", "arith"), ("calculate 1000 - 387", "arith"), ("what is 144 divided by 12", "arith"), ("2^10", "arith"),
    ("what did I tell you about project P12?", "memory"), ("do you remember my access code", "memory"),
    ("what is in this picture", "image"), ("read the text in this photo", "image"),
    ("explain step by step why the sky is blue", "reason"), ("compare tabs and spaces", "reason"),
]
NEEDED = {"chat": {"language"}, "arith": {"arithmetic", "verification"}, "memory": {"exact_retrieval", "language"},
          "image": {"ocr", "language"}, "reason": {"reasoning", "language"}}

if __name__ == "__main__":
    reg = default_registry()
    nfd = NeedField(reg)
    base = always_all(reg)
    sel_n, over, miss_avail, extra = [], [], 0, 0
    for text, kind in PROMPTS:
        has_img = kind == "image"
        d = nfd.select(Task(text, has_image=has_img))
        over.append(0)
        import time
        s = time.perf_counter()
        for _ in range(200): nfd.select(Task(text, has_image=has_img))
        over[-1] = (time.perf_counter() - s) / 200 * 1000
        sel_n.append(len(d.selected))
        avail_needed = {m for m in NEEDED[kind] if reg.get(m).available}
        miss_avail += len(avail_needed - set(d.selected))
        extra += len(set(d.selected) - NEEDED[kind])
    print(f"always-all modules per request : {len(base.selected)}  (est {base.est_latency_ms:.0f} ms, {base.est_ram_mb:.0f} MB)")
    print(f"NFD mean modules per request   : {statistics.mean(sel_n):.2f}")
    print(f"required+available modules missed: {miss_avail}   unneeded modules activated: {extra}")
    print(f"NFD routing overhead           : mean {statistics.mean(over):.3f} ms, max {max(over):.3f} ms")
    print("note: 'always-all' only includes AVAILABLE modules (language, exact_retrieval, arithmetic, verification)")
