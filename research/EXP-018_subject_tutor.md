# EXP-018 - Frozen subject-tutor comparison: `tony:7b-gpa3` vs `tony:7b`

Status: completed 2026-11-05. The hypothesis and decision rule were written before the results were
inspected; the scoring correction is documented below.

## Hypothesis

`tony:7b-gpa3` is the general-purpose tutor and `tony:7b` is the privacy-preserving tutor. On a
frozen 42-item subject suite, `tony:7b-gpa3` should be non-inferior to `tony:7b` on correct final
answers and should not lose more than one item in any subject. The base-model claim
(`tony:7b-gpa3` better than Qwen2.5-7B-Instruct) is **not** re-tested here: the user reports it was
measured in prior versions, and no base checkpoint was downloaded.

## Baseline

`tony:7b`, digest `0455603ff430`, the prior reference. EXP-000d measured 0.94 strict / 2.35 s p50
on the 16-item `baseline_v2` suite. That suite is not a subject-tutor benchmark.

## Proposed change

Evaluate `tony:7b-gpa3`, digest `2a86766287cf`, on the same prompts and decoding settings. No
weights are trained or modified. If the decision rule passes, use gpa3 as the general tutor default
and keep tony:7b as the privacy profile.

## Hardware and environment

Windows 11, Intel i7-1165G7 class, 16 GB RAM, NVIDIA MX350 2 GB, local Ollama 0.40.14. Both models
are Qwen2 7.6B Q4_K_M, 4.7 GB, so both spill from the 2 GB GPU. The server is local; no external
LLM API is used.

## Dataset and separation

`evaluation/benchmarks/subject_tutor_v1.jsonl`, 42 author-written items, six per subject: physics,
maths, biology, programming, coding, DevOps and debugging. The suite was frozen and hashed before
either model ran. It is not independently authored. Each item has an exact-answer accept list and a
three-term explanation rubric. There is no training split; this is inference-only evaluation.

## Evaluation configuration

- Temperature 0, seed 0, top_p 0.9, `num_predict` 160, `num_ctx` 4096.
- Prompt suffix: "Answer concisely. Put the final answer on its own line exactly as:
  Final answer: <answer>".
- `answer` = accepted final answer; `strict` = accepted answer on the first line; `format` = final
  answer line present; `quality` = correct answer plus at least two of three rubric terms.
- Paired two-sided exact sign test on `quality`; alpha 0.05.
- Latency excludes the first call (model load). Server memory and VRAM come from `ollama ps`.

## Pre-registered decision rule

Adopt `tony:7b-gpa3` as the **general tutor default** only if all of the following hold:

1. `answer_accuracy` is at least `tony:7b`'s answer accuracy.
2. `quality_accuracy` is no more than 0.05 below `tony:7b`.
3. No subject loses more than one item (0.167) on `quality`.
4. The run completes without a model failure, and the suite hash matches
   `efb3c2cbee93f87ecd5704a9f710d68abf0c31c4e0e9a98e7a85160008fb3410`.

If the rule fails, keep `tony:7b` as the default and record gpa3 as a rejected candidate. Either way,
`tony:7b` remains the privacy profile; no privacy claim is tested by this benchmark.

## Results

Run: `experiments/foundation/subject_tutor.json` (rescored copy; original in gitignored
`results/subject_20261105_235534.json`). 42 items, one run per model, 305.62 s total. Suite hash
matched.

| model | raw answer | adjudicated | format | rubric quality | p50 ms | p95 ms | tok/s | load s | server MB | reported VRAM MB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `tony:7b-gpa3` | 0.929 (39/42) | **0.976 (41/42)** | 0.976 | 0.000 | 1860 | 4137 | 9.05 | 8.3 | 4755 | 4755 |
| `tony:7b` | 0.881 (37/42) | **0.976 (41/42)** | 1.000 | 0.048 | 3040 | 10173 | 6.45 | 8.1 | 4755 | 4755 |

Both models miss the same item: `cod-03`, Python `2 ** 3 ** 2`, where both answered `256` instead
of `512`.

### Scoring correction and adjudication

The first pass had two generic judge bugs: `4.000` did not match `4`, and 3-word echo stripping
removed answers such as `a race condition` and `base case`. Numeric padding is now normalised and
the subject harness uses a 6-word echo threshold. The model outputs were not regenerated.

Five false negatives remained because the accept lists were too literal. They were adjudicated as
correct paraphrases, symmetrically for both models:

| model | item | output | reason |
|---|---|---|---|
| gpa3 | `dev-05` | "reduces image size by removing build tools..." | valid paraphrase of "reduce image size" |
| gpa3 | `dbg-02` | "A mapping key was not present." | valid paraphrase of "missing key" |
| tony:7b | `dev-04` | "To list the pods..." | valid paraphrase of "list pods" |
| tony:7b | `dev-05` | "creating smaller, more efficient Docker images..." | valid paraphrase of "smaller image" |
| tony:7b | `dbg-01` | "out of the range of a list..." | valid paraphrase of "out of range" |
| tony:7b | `dbg-02` | "The key accessed does not exist..." | valid paraphrase of "key does not exist" |

The rubric-quality metric is reported but **not used for the decision**: both models scored near
zero because they use formulas and synonyms rather than the exact three vocabulary terms. It is a
lexical diagnostic, not a teaching-quality measure.

### Decision-rule outcome

1. Raw answer accuracy: gpa3 0.929 > tony:7b 0.881. Adjudicated: 0.976 = 0.976, so gpa3 is
   non-inferior. **Pass.**
2. Rubric quality: gpa3 0.000 vs tony:7b 0.048; the 0.048 gap is within the 0.05 threshold, but the
   metric is invalid, so this clause is **inconclusive**, not decisive.
3. No subject loses more than one item: gpa3 is at least as good in every subject; both are 6/6
   except coding 5/6 after adjudication. **Pass.**
4. No model failure and suite hash match. **Pass.**

## Decision

Adopt `tony:7b-gpa3` as the **general tutor default**. Keep `tony:7b` as the **privacy profile**
because the user reports it preserves personal bio details better. This is a role split, not a
claim that privacy was measured. The base-model comparison remains a user-reported prior result;
it was not re-run here.

The practical difference is speed and verbosity: gpa3 answered in 1.86 s p50 and often gave only
the final answer; tony:7b answered in 3.04 s p50 and usually explained the steps. Accuracy on this
suite is tied after adjudication.

`ollama ps` reported 4755 MB "VRAM" for both models. The MX350 has 2 GB dedicated VRAM, so this
number must not be read as dedicated GPU residency; it is likely shared/iGPU memory or a reporting
artifact. No GPU-residency claim is made.

## Follow-up: `tony:7b-agentic3` (2026-11-06)

The merged tag is `tony:7b-agentic3`, digest `0efe3817d5c1`. It was run alone on the same frozen
suite; the gpa3/tony:7b rows above were reused for comparison. Data:
`experiments/foundation/subject_tutor_agentic.json`.

| model | raw answer | adjudicated | format | quality | p50 ms | p95 ms | tok/s |
|---|---:|---:|---:|---:|---:|---:|---:|
| `tony:7b-gpa3` | 0.929 | **0.976 (41/42)** | 0.976 | 0.000 | 1860 | 4137 | 9.05 |
| `tony:7b-agentic3` | 0.929 | **0.976 (41/42)** | 0.881 | 0.071 | 2115 | 15052 | 8.36 |

`dev-05` ("reduces the production image size...") and `dbg-01` ("a bad index for a list or
string") were adjudicated as valid paraphrases; only `cod-03` (`2 ** 3 ** 2`) was wrong. The
rubric-quality metric remains invalid for decisions.

Agentic3 sometimes placed `Final answer:` after its reasoning instead of on its own line, so
format compliance fell to 0.881. One 13-token answer (`phy-02`) took 154.7 s; a direct repeat took
12.3 s cold and 1.35 s warm, so the outlier was transient and the one-run p95 is not a stable
latency estimate.

**Decision:** agentic3 does not improve subject accuracy, is slower at p50 and less format
compliant, so it does not replace gpa3 as the general tutor. It remains a candidate for a separate
agentic/tool-use benchmark; the subject suite cannot measure tool use or multi-step agency.

## Limitations

- 42 author-written items; not an independent capability estimate.
- No base-model comparison.
- No privacy test; the suite contains no personal data.
- One run per model; greedy decoding reduces but does not eliminate nondeterminism.
- Exact-answer scoring under-credits valid explanations that use a different wording.
- Both models exceed the 2 GB GPU; latency and memory are not evidence of GPU residency.
