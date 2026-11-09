"""Session-scoped admin sign-in throttling for the synthetic VendorFlow demo.

Five wrong passwords block another attempt in that Streamlit session for
15 minutes. A new browser session bypasses this; use a long random admin
secret and do not regard this as production-grade authentication.
"""
from __future__ import annotations

import math
import time
from collections.abc import MutableMapping
from typing import Any

_MAX_ATTEMPTS = 5
_LOCK_SECONDS = 15 * 60
_COUNT = "_vf_admin_bad_logins"
_UNTIL = "_vf_admin_login_locked_until"


def remaining_admin_lockout(state: MutableMapping[str, Any], *, now: float | None = None) -> int:
    current = time.monotonic() if now is None else now
    until = float(state.get(_UNTIL, 0) or 0)
    if until <= current:
        if until:
            state.pop(_UNTIL, None)
            state.pop(_COUNT, None)
        return 0
    return max(1, math.ceil(until - current))


def record_admin_login_failure(state: MutableMapping[str, Any], *, now: float | None = None) -> int:
    current = time.monotonic() if now is None else now
    existing_wait = remaining_admin_lockout(state, now=current)
    if existing_wait:
        return existing_wait
    attempts = int(state.get(_COUNT, 0) or 0) + 1
    if attempts >= _MAX_ATTEMPTS:
        state[_UNTIL] = current + _LOCK_SECONDS
        state[_COUNT] = 0
        return _LOCK_SECONDS
    state[_COUNT] = attempts
    return 0


def clear_admin_login_failures(state: MutableMapping[str, Any]) -> None:
    state.pop(_COUNT, None)
    state.pop(_UNTIL, None)
