# BrainSim failure log

Short entries for the first BrainSim experiment. These are engineering findings, not claims that
the overall direction is impossible.

**F-BS-001 — Token-keyed fast memory causes severe cross-task interference (BS-EXP-001).**
A memory keyed only by the current token raised unseen-rule accuracy from 0.095 to 0.775, but when
the same memory was left active on previously learned rules, old-rule accuracy fell from 0.956 to
0.309 (drop 0.647). The key does not identify which hidden rule produced the observation. Fix:
task-scoped reset (used in the measured operating mode) or a context/gate mechanism. Pair keys
reduce but do not eliminate the problem (F-BS-002).

**F-BS-002 — Pair keys still exceed the 2% retention tolerance (BS-EXP-001).**
Keying by `(previous token, current token)` reduced old-rule interference to a 0.053 drop (0.903 vs
0.956), but the 2% tolerance was still not met while the new-rule memory stayed active. A pair from
one permutation can occur in another, and the first position uses a self-pair. Fix: reset at task
boundaries now; later compare learned gates, task IDs, or hidden-state keys under the same
protocol.

**F-BS-003 — Fast memory cannot predict unobserved transitions (BS-EXP-001).**
Study covers 12 of 16 transitions, and token memory reaches 0.775 (= 12/16 plus a small model
fallback). Pair memory reaches 0.686 because pair coverage is about 0.65. The matrix is a lookup,
not a rule-inference mechanism. Do not claim generalisation to unseen transitions without a new
task and a new baseline.

**F-BS-004 — A larger recurrent core gives no accuracy gain on this task (BS-EXP-001).**
Hidden 128 (206k parameters) and hidden 384 (1.8M parameters) both scored 0.956 on training-rule
validation and about 0.09 frozen on unseen rules. The 384 model is 8.7× larger and slower to train.
The task is simple enough that capacity is not the bottleneck. Do not scale the model before
adding tasks that require it.

**F-BS-005 — Training time on the laptop is highly variable (BS-EXP-001).**
The same 384-parameter configuration took 31.9–97.6 s for 30 epochs across seeds, and 128 took
14.0–24.0 s in the recorded run (earlier runs were 8.6–10.5 s). Use medians and repeated runs;
do not compare algorithms by a single wall-clock measurement.
