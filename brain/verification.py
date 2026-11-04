"""Three-state factual verification (Phase 1, P03/P04).

Verification is not a boolean. A verifier can confirm a claim, reject it, or be unable to
check it at all. Only ``VERIFIED`` may be treated as established fact or enter verified
learning queues; ``UNAVAILABLE`` must never be read as success.
"""
from __future__ import annotations

from enum import Enum


class Verification(str, Enum):
    VERIFIED = "verified"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"

    @classmethod
    def from_optional(cls, ok: bool | None) -> "Verification":
        """Map the legacy ``(True | False | None)`` verifier result to the strict three-state value."""
        if ok is True:
            return cls.VERIFIED
        if ok is False:
            return cls.FAILED
        return cls.UNAVAILABLE

    @property
    def legacy_bool(self) -> bool | None:
        """Compatibility view for ``Response.verified``: True / False / None."""
        if self is Verification.VERIFIED:
            return True
        if self is Verification.FAILED:
            return False
        return None

    @property
    def is_verified(self) -> bool:
        return self is Verification.VERIFIED
