"""Train and evaluate the experimental neural addition specialist; exact arithmetic stays primary."""
from __future__ import annotations
import argparse, json, time
from pathlib import Path
from .neural_expert import AdditionExpertConfig, NeuralAdditionExpert

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--samples", type=int, default=50000)
    p.add_argument("--min", type=int, default=-1000)
    p.add_argument("--max", type=int, default=1000)
    p.add_argument("--checkpoint", default="checkpoints/neural_arithmetic/addition.npz")
    p.add_argument("--test-samples", type=int, default=5000)
    args = p.parse_args()
    cfg = AdditionExpertConfig(seed=args.seed, a_min=args.min, a_max=args.max,
                               b_min=args.min, b_max=args.max)
    expert = NeuralAdditionExpert(); started = time.perf_counter()
    expert.train(cfg, n=args.samples)
    train_s = time.perf_counter() - started
    import numpy as np
    rng = np.random.default_rng(args.seed + 1)
    a = rng.integers(args.min, args.max + 1, size=args.test_samples)
    b = rng.integers(args.min, args.max + 1, size=args.test_samples)
    pred = np.rint(expert.w[0] * a + expert.w[1] * b + expert.bias).astype(np.int64)
    truth = a + b
    report = {"task": "integer addition", "seed": args.seed, "train_samples": args.samples,
        "test_samples": args.test_samples, "range": [args.min, args.max],
        "exact_match": float(np.mean(pred == truth)), "mae": float(np.mean(np.abs(pred-truth))),
        "weights": expert.w.tolist(), "bias": expert.bias, "train_seconds": train_s,
        "warning": "experimental candidate only; ASHURA exact arithmetic remains authoritative"}
    expert.save(args.checkpoint)
    out = Path(args.checkpoint).with_suffix(".metrics.json")
    out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))

if __name__ == "__main__": main()
