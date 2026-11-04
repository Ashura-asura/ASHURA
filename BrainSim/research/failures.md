# BrainSim failure log

Short entries for the first BrainSim experiment. These are engineering findings, not claims that
the overall direction is impossible.

**F-BS-001 â€” Token-keyed fast memory causes severe cross-task interference (BS-EXP-001).**
A memory keyed only by the current token raised unseen-rule accuracy from 0.085 to 0.771, but when
the same memory was left active on previously learned rules, old-rule accuracy fell from 0.957 to
0.309 (drop 0.648). The key does not identify which hidden rule produced the observation. Fix:
task-scoped reset (used in the measured operating mode) or a context/gate mechanism. Pair keys
reduce but do not eliminate the problem (F-BS-002).

**F-BS-002 â€” Pair keys still exceed the 2% retention tolerance (BS-EXP-001).**
Keying by `(previous token, current token)` reduced old-rule interference to a 0.053 drop (0.904 vs
0.957), but the 2% tolerance was still not met while the new-rule memory stayed active. A pair from
one permutation can occur in another, and the first position uses a self-pair. Fix: reset at task
boundaries now; later compare learned gates, task IDs, or hidden-state keys under the same
protocol.

**F-BS-003 â€” Fast memory cannot predict unobserved transitions (BS-EXP-001).**
Study covers 12 of 16 transitions, and token memory reaches 0.775 (= 12/16 plus a small model
fallback). Pair memory reaches 0.686 because pair coverage is about 0.65. The matrix is a lookup,
not a rule-inference mechanism. Do not claim generalisation to unseen transitions without a new
task and a new baseline.

**F-BS-004 â€” A larger recurrent core gives no accuracy gain on this task (BS-EXP-001).**
Hidden 128 (206k parameters) and hidden 384 (1.8M parameters) both scored 0.957 on training-rule
validation and about 0.09 frozen on unseen rules. The 384 model is 8.7Ã— larger and slower to train.
The task is simple enough that capacity is not the bottleneck. Do not scale the model before
adding tasks that require it.

**F-BS-005 â€” Training time on the laptop is highly variable (BS-EXP-001).**
The same 384-parameter configuration took 31.9â€“97.6 s for 30 epochs across seeds, and 128 took
14.0â€“24.0 s in the recorded run (earlier runs were 8.6â€“10.5 s). Use medians and repeated runs;
do not compare algorithms by a single wall-clock measurement.


**F-BS-006 — B2 delayed copy is too easy and does not distinguish architectures (BS-EXP-002).**
Both the GRU and a parameter-matched fixed MLP reached 1.000 token and full-recall accuracy at
every delay, including 12–20, which were never trained. The fixed MLP trained 6–16× faster. The
task only requires copying the cue block; the delay length is irrelevant, so the MLP can read the
cues directly. This falsifies H-DELAY. It is not evidence that recurrence is useless; it is evidence
that this task cannot test the claim. Fix: variable cue counts, distractor content that must be
filtered, or a relational query whose answer depends on the delay.

**F-BS-007 — B3 gating is tautological about task identity (BS-EXP-003).**
Task-scoped memory retained old-rule accuracy at 1.000 while shared memory fell to 0.104, but the
task ID was supplied by the experiment and all writes were verified. The gate therefore proves
isolation when the boundary is already known; it does not detect boundaries, infer task identity,
or test surprise-gated admission. Do not describe it as solved interference control.


**F-BS-008 - Replay is a mitigation, not free retention (BS-EXP-004).**
Replay-augmented fine-tuning cut old-rule forgetting from 49.3 to 1.18 points and kept every seed
inside the 2% tolerance, but the replay arm saw extra old examples and took about 38% longer. The
buffer covers only the sequences it stores; retention on a different domain or on transitions
absent from the buffer was not tested. Do not describe replay as a guarantee.

**F-BS-009 - B5 is supervised imitation on a fully observed toy task (BS-EXP-005).**
The learned policy matched a finite-horizon DP oracle (5.574 vs 5.5745 total utility) with 0.0
infeasible actions, but the need and budget were inputs, the oracle was known, and training was
supervised cross-entropy, not reinforcement. Do not cite it as reinforcement learning, latent need
inference, or general resource management. The DP oracle is essential: a myopic greedy target
would have rewarded different actions.

**F-BS-010 - B6's 1.000 gated-memory score is full-coverage lookup (BS-EXP-006).**
Per-rule memory reached 1.000 token and full recall on held-out rules and retained 1.000 on a
revisit, while fast memory fell back to 0.083 after reset. However, eight study walks per rule
cover every transition of a 16-cycle, the task ID is supplied externally, and writes are verified.
The result measures retention of verified lookup entries, not rule induction, learned task
segmentation, or generalization to unobserved transitions. The fixed in-context MLP (0.327) also
beat the frozen GRU (0.083), so B6 does not support a recurrent advantage.

**F-BS-011 - The B6 fixed baseline is strong but not a rule learner (BS-EXP-006).**
The parameter-matched fixed MLP reached 0.327 token accuracy on held-out rules but 0.000 full
recall, versus 0.083 token and 0.000 full recall for the frozen GRU. It can match parts of the
study/test window without representing the unseen permutation. This is a useful upper bound on
in-context pattern matching, not evidence that the fixed model understands the rule.
