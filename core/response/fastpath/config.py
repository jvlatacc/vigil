"""Fast-path configuration, in one place.

Every comparison the fast-path policy makes reads a field here, so a config
change moves the whole tier rather than one branch. Defaults are inert: the
fast path is operator opt-in, and the pre-triage tier is a further opt-in on
top of the master switch.
"""

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class FastPathConfig(BaseSettings):
    """The fast-path switches, env-tunable with the ``FAST_PATH_`` prefix.

    Set-shaped fields read a JSON array from env, e.g.
    ``FAST_PATH_ALLOWED_ACTION_TYPES='["rate_limit"]'``.
    """

    model_config = SettingsConfigDict(
        env_prefix="FAST_PATH_",
        extra="ignore",
        case_sensitive=False,
    )

    # Master switch — operator opt-in; the CHANGELOG upgrade note records it.
    enabled: bool = False
    # T0 tier: source-native signals, before any LLM call. A further opt-in:
    # source severity arrives unconsumed from the source and alert text is
    # attacker-fenceable, so the strongest false-positive class acts here.
    pre_triage_enabled: bool = False
    # A speculative restriction's lifetime, and the hard ceiling an
    # adjudicator's "retain" may not exceed.
    default_ttl_seconds: int = 600
    max_ttl_seconds: int = 3600
    # One active restriction per target: a second speculative action for a
    # target that already holds one is refused, not stacked.
    max_speculative_per_target: int = 1
    # The T1 tier's confidence floor, aligned with the response domain's
    # review_threshold so the fast path fires no easier than the queue's
    # quick-review line.
    review_threshold: float = 0.85
    # The action types the policy may return; anything else is a refusal.
    allowed_action_types: frozenset[str] = frozenset(
        {"rate_limit", "tarpit", "session_pin", "latency_inject"}
    )
    # The subset with a real enforcement integration in v1 — the rest ride
    # the simulation adapter. Dispatch reads this; the policy does not.
    enforced_action_types: frozenset[str] = frozenset({"rate_limit"})
    # The slow track: enqueueing the adjudicate run after dispatch and the
    # daemon's verdict scan. Off by default, like the master switch — the
    # fast path is fully functional (TTL sweep as the fail-safe) without it.
    adjudication_enabled: bool = False

    @field_validator("default_ttl_seconds", "max_ttl_seconds")
    @classmethod
    def _ttl_is_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("a ttl must be at least one second")
        return value

    @model_validator(mode="after")
    def _default_ttl_within_ceiling(self) -> "FastPathConfig":
        if self.default_ttl_seconds > self.max_ttl_seconds:
            raise ValueError("default_ttl_seconds must not exceed max_ttl_seconds")
        return self
