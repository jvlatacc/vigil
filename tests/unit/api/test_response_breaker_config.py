"""The breaker surface reads honestly and resets by permission.

The status endpoint reports the stored state or fails loudly — never "open"
when the row may be tripped. The reset endpoint opens a trip under the
signed-in operator's name, and returns an armed breaker untouched: no write,
no second OPENED log, no new audit row.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from core.response.breaker import (
    STATE_OPEN,
    STATE_TRIPPED,
    BreakerCounts,
    ResponseConfig,
    tripped_state,
)
from core.time import utcnow
from services.api.routers.config import get_response_breaker, reset_response_breaker

pytestmark = pytest.mark.unit

ROUTER = "services.api.routers.config"


def _tripped():
    counts = BreakerCounts(
        volume_hour=10, distinct_targets_hour=8, failures=0, attempts=0
    )
    return tripped_state(
        counts,
        "response.breaker_volume_threshold=10 met (10)",
        ResponseConfig(),
        utcnow(),
    )


def _user():
    return SimpleNamespace(user_id="user-1")


class TestGetResponseBreaker:
    def test_a_tripped_state_is_reported_with_its_reason(self):
        state = _tripped()
        with patch(f"{ROUTER}.read_breaker_state", return_value=state):
            response = get_response_breaker()
        assert response.state == STATE_TRIPPED
        assert response.reason == "response.breaker_volume_threshold=10 met (10)"
        assert response.tripped_at == state.tripped_at

    def test_a_failed_read_is_an_error_not_open(self):
        with patch(f"{ROUTER}.read_breaker_state", side_effect=RuntimeError("db down")):
            with pytest.raises(HTTPException) as err:
                get_response_breaker()
        assert err.value.status_code == 503


class TestResetResponseBreaker:
    def test_a_reset_opens_the_trip_under_the_operator_name(self):
        state = _tripped()
        stamped = MagicMock()
        written = {}

        def _write(opened, config_service):
            written["state"] = opened
            written["service"] = config_service
            return True

        with (
            patch(f"{ROUTER}.read_breaker_state", return_value=state),
            patch(f"{ROUTER}._for_user", return_value=stamped),
            patch(f"{ROUTER}.write_breaker_state", side_effect=_write),
        ):
            response = reset_response_breaker(current_user=_user())
        assert response.state == STATE_OPEN
        assert written["state"].reset_by == "user-1"
        assert written["service"] is stamped

    def test_an_armed_breaker_is_returned_without_a_write(self):
        state = SimpleNamespace(
            state=STATE_OPEN,
            reason=None,
            tripped_at=None,
            counts={},
            auto_resume_at=None,
            reset_at=None,
            reset_by=None,
        )
        with (
            patch(f"{ROUTER}.read_breaker_state", return_value=state),
            patch(f"{ROUTER}.write_breaker_state") as write,
        ):
            response = reset_response_breaker(current_user=_user())
        assert response.state == STATE_OPEN
        write.assert_not_called()

    def test_a_failed_write_is_an_error_and_the_trip_stays(self):
        state = _tripped()
        with (
            patch(f"{ROUTER}.read_breaker_state", return_value=state),
            patch(f"{ROUTER}._for_user", return_value=MagicMock()),
            patch(f"{ROUTER}.write_breaker_state", return_value=False),
        ):
            with pytest.raises(HTTPException) as err:
                reset_response_breaker(current_user=_user())
        assert err.value.status_code == 503
