"""CLI entry point: flag off exits 0 with the reason; flag on runs the daemon.

The process environment is touched exactly here (the ``noqa: ENV001`` line);
everything downstream takes an :class:`EdgeConfig`.
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Mapping


def main(argv: list[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    env = os.environ if env is None else env  # noqa: ENV001 CLI entry, like Medic's

    # Imported here so `python -m services.edge --help`-class entry stays cheap
    # and the module graph stays import-clean (no side effects).
    from services.edge.app.config import ConfigError, EdgeConfig, is_enabled

    if not is_enabled(env):
        print(
            "Edge daemon disabled: set VIGIL_EDGE_ENABLED=true to enable "
            "(services/edge, Local Autonomy Mesh)."
        )
        return 0

    try:
        config = EdgeConfig.from_env(env)
    except ConfigError as exc:
        print(f"Edge daemon config error: {exc}", file=sys.stderr)
        return 2

    problems = config.validate()
    if problems:
        for problem in problems:
            print(f"Edge daemon config error: {problem}", file=sys.stderr)
        return 2

    from services.edge.app.daemon import EdgeDaemon

    asyncio.run(EdgeDaemon(config).run())
    return 0
