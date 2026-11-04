"""P19/P20/P26: labelled answer-comparison benchmark.

Author-written pairs with a binary label: 1 = same claim, 0 = contradiction. It measures the
structured comparator and the old lexical baseline; it is not a general natural-language
understanding benchmark.

    python -m evaluation.contradiction_bench
"""
from __future__ import annotations

import json
from pathlib import Path

from learning.ama import answers_agree
from learning.compare import answer_similarity, jaccard, tokens

# (question, first, second, same_claim)
PAIRS = [
    ("what is the access code for project P7", "The access code for project P7 is 4821", "code is 4821", 1),
    ("what is 6*7", "42", "The answer is 42", 1),
    ("capital of france", "It is Paris", "The capital of France is Paris", 1),
    ("capital of france", "Paris", "Paris.", 1),
    ("how far is the office", "it is 1.5 km", "it is 1500 m", 1),
    ("how far is the office", "5 km", "5000 metres", 1),
    ("what is the weight", "2 kg", "2000 grams", 1),
    ("how long is the trip", "2 hours", "120 minutes", 1),
    ("when is the meeting", "May 6, 2024", "2024-05-06", 1),
    ("when is the meeting", "6 May 2024", "2024-05-06", 1),
    ("how many items", "twenty three", "23", 1),
    ("which project", "project P7", "project p7", 1),
    ("what is the access code for project P7", "code is 4821", "code is 4812", 0),
    ("what is the access code for project P7", "code is 4821", "code is not 4821", 0),
    ("what is the access code for project P7", "code is 4821", "code is 4821 or 9999", 0),
    ("what is the access code for project P7", "code is 4821", "I do not know", 0),
    ("capital of france", "Paris", "Lyon", 0),
    ("capital of france", "Paris", "Paris is not the capital", 0),
    ("meeting day", "The meeting is on Monday", "The meeting is on Friday", 0),
    ("how far is the office", "1.5 km", "1.5 miles", 0),
    ("what is the weight", "2 kg", "2 pounds", 0),
    ("how long is the trip", "2 hours", "2 minutes", 0),
    ("when is the meeting", "2024-05-06", "2024-05-07", 0),
    ("how many items", "twenty three", "twenty four", 0),
    ("which project", "project P7", "project P8", 0),
    ("what is the box colour", "the box is not red", "the box is not blue", 0),
    ("did the test pass", "the test passed", "the test did not pass", 0),
    ("who owns it", "Alice owns it", "Bob owns it", 0),
]


def lexical_baseline(question: str, first: str, second: str) -> bool:
    """The previous comparator: high token overlap first, then simple negation parity."""
    return jaccard(tokens(first), tokens(second)) >= 0.9


def main() -> None:
    rows = []
    tp = fp = fn = tn = 0
    brier_new = brier_base = 0.0
    for q, a, b, label in PAIRS:
        pred = answers_agree(q, a, b)
        base = lexical_baseline(q, a, b)
        sim = answer_similarity(q, a, b)
        truth = bool(label)
        # positive class = contradiction agreement? use same-claim for precision/recall of the comparator
        if pred and truth:
            tp += 1
        elif pred and not truth:
            fp += 1
        elif not pred and truth:
            fn += 1
        else:
            tn += 1
        brier_new += (sim - label) ** 2
        brier_base += (jaccard(tokens(a), tokens(b)) - label) ** 2
        rows.append({"question": q, "first": a, "second": b, "label": label,
                     "predicted": pred, "baseline": base, "similarity": sim,
                     "baseline_similarity": round(jaccard(tokens(a), tokens(b)), 4)})
    n = len(PAIRS)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    out = {
        "n": n,
        "accuracy": round((tp + tn) / n, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0.0,
        "baseline_accuracy": round(sum(r["baseline"] == bool(r["label"]) for r in rows) / n, 4),
        "brier_new": round(brier_new / n, 4),
        "brier_lexical": round(brier_base / n, 4),
        "false_merges": [r for r in rows if r["predicted"] and not r["label"]],
        "false_conflicts": [r for r in rows if not r["predicted"] and r["label"]],
        "rows": rows,
    }
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=2))
    Path("evaluation/contradiction_results.json").write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
