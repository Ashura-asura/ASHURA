"""End-to-end verified-correction loop (Phase 3, P07/P75).

    verified correction -> CAGE attribution -> bounded update proposal
                        -> temporary fast update -> DREAM candidate -> NGR -> promote/rollback

The loop refuses to start without an independently verified correction. CAGE never turns an
ordinary model error into a label (P08), and NGR is the only path to a stable checkpoint. A
rejected candidate stays in `checkpoints/candidates`; the stable pointer is unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from learning.cage import CAGE
from learning.corrections import Correction
from learning.dream import DREAM, DreamConfig
from learning.replay import ReplayBuffer, ReplayItem
from plasticity.gated_update import GatedUpdater
from plasticity.slow_weights import CheckpointStore


@dataclass
class LoopResult:
    stage: str                       # refused_* | fast_update_only | candidate_rejected | promoted
    promoted: bool
    correction: dict
    reasons: list[str] = field(default_factory=list)
    attribution: dict | None = None
    decision: dict | None = None
    proposal: dict | None = None
    update: dict | None = None
    dream: dict | None = None

    @property
    def completed(self) -> bool:
        return self.promoted


def _verifiers(expected: str | None) -> dict:
    """Only an exact independently checked value is a verifier for this loop."""
    if expected is None:
        return {}
    check = lambda out, e=expected: str(out).strip() == str(e).strip()  # noqa: E731
    return {"arithmetic": check, "language": check}


def run_verified_correction(correction: Correction, trace, *,
                            cage: CAGE | None = None,
                            updater: GatedUpdater | None = None,
                            buffer: ReplayBuffer | None = None,
                            store: CheckpointStore | None = None,
                            policy=None,
                            cfg: DreamConfig | None = None,
                            verifiers: dict | None = None) -> LoopResult:
    """Run the full loop, or stop at the first stage that cannot justify an update."""
    cage = cage or CAGE()
    result = LoopResult("refused_unverified", False, correction.as_dict())

    if not correction.verified:
        result.reasons.append("correction is not independently verified; it is stored as a user "
                              "assertion and cannot produce a training signal")
        return result
    if trace is None:
        result.stage = "refused_no_trace"
        result.reasons.append("no execution trace to attribute; a verified fact alone does not "
                              "identify a failing component")
        return result

    # 1. attribution + authorisation
    expected = correction.expected or correction.value
    attr = cage.attribute(trace, expected=expected,
                          verifiers=verifiers if verifiers is not None else _verifiers(expected))
    result.attribution = {"module": attr.module, "confidence": attr.confidence,
                          "reason": attr.reason, "eligible": list(attr.eligible)}
    decision = cage.authorise(attr, verified=True, delta_norm=0.0)
    result.decision = {"allowed": decision.allowed, "reasons": list(decision.reasons)}
    if not decision.allowed:
        result.stage = "refused_policy"
        result.reasons.extend(decision.reasons)
        return result

    proposal = cage.propose(attr, decision, verified=True, key=correction.key,
                            value=correction.value, source=correction.method)
    if proposal is None:
        result.stage = "refused_no_proposal"
        result.reasons.append("CAGE produced no verified, attributed update proposal")
        return result
    result.proposal = {"module": proposal.module, "key": proposal.key,
                       "value": proposal.value, "source": proposal.source}

    # 2. bounded fast update (temporary, resettable)
    if updater is not None:
        outcome = updater.apply(decision, proposal)
        result.update = {"applied": outcome.applied, "reason": outcome.reason,
                         "delta_before": outcome.delta_norm_before,
                         "delta_after": outcome.delta_norm_after}
        if not outcome.applied:
            result.stage = "refused_update"
            result.reasons.append(outcome.reason)
            return result

    if buffer is None or store is None or cfg is None:
        result.stage = "fast_update_only"
        result.reasons.append("no candidate buffer/store supplied; only the temporary fast update ran")
        return result

    # 3. candidate training from verified data, then NGR
    item = ReplayItem(id=f"correction:{correction.key}", key=correction.key,
                      value=correction.value, category=cfg.target, verified=True,
                      source=correction.method)
    try:
        buffer.add(item)
    except ValueError as e:                       # e.g. the same fingerprint is already held out
        result.stage = "refused_replay"
        result.reasons.append(f"replay buffer rejected the verified item: {e}")
        return result
    try:
        dream = DREAM(buffer, store, policy, cfg).run()
    except ValueError as e:                       # insufficient verified data / no held-out set
        result.stage = "candidate_skipped"
        result.reasons.append(f"DREAM refused to train or evaluate: {e}")
        return result
    result.dream = {"candidate": dream.candidate, "scores": dream.scores,
                    "stable": dream.stable_scores, "train_n": dream.train_n,
                    "ngr": dream.ngr.reasons, "promoted": dream.promoted}
    result.promoted = dream.promoted
    result.stage = "promoted" if dream.promoted else "candidate_rejected"
    result.reasons.extend(dream.ngr.reasons)
    if not dream.promoted:
        result.reasons.append("stable checkpoint unchanged; candidate retained for inspection")
    return result
