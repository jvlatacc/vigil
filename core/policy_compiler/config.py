"""Maturity thresholds for the JIT policy compiler: runtime-config keys and defaults.

The values are DB-first runtime-config keys (``core.platform.runtime_config``,
resolved from the ``ai_operations.settings`` row, then the env var named in
``ENV_FALLBACKS``, then the defaults here) so the console can retune a running
deployment without redeploying. These are the spec's shipped defaults.
"""

from __future__ import annotations

# Minimum completed runs resolving one archetype in the window before the
# maturity job may compile a policy from it.
MIN_RUNS_KEY = "policy_compiler_min_runs"
MIN_RUNS_DEFAULT = 10

# Share of those runs that must close consistently (same closure category, no
# analyst reopen or override).
MIN_CONSISTENCY_KEY = "policy_compiler_min_consistency"
MIN_CONSISTENCY_DEFAULT = 0.90

# Evidence window in days.
WINDOW_DAYS_KEY = "policy_compiler_window_days"
WINDOW_DAYS_DEFAULT = 30

# Shadow/active disagreements with the eventual LLM or analyst result that
# trip the drift auto-brake (active -> suspended).
DRIFT_LIMIT_KEY = "policy_compiler_drift_limit"
DRIFT_LIMIT_DEFAULT = 3
