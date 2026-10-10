#!/bin/sh
# OpenCanary decoy: --dev is upstream's foreground mode (twistd -noy) — the
# container-equivalent of a well-behaved PID 1. Privileges drop to nobody
# after startup (--uid/--gid); port 8080 is unprivileged, so binding works.
set -u
exec opencanaryd --dev --uid=nobody --gid=nogroup
