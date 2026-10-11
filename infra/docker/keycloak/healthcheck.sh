#!/usr/bin/env bash
# Keycloak readiness for the compose healthcheck.
#
# The Keycloak image ships no curl and no coreutils, so this speaks HTTP with
# bash's own /dev/tcp: ask the management interface (port 9000, enabled by
# default since Keycloak 26) for /health/ready and require a 200 on the status
# line. Anything else — connection refused while the server is still coming
# up, a non-200 from a partially booted broker — fails the check.
exec 3<>/dev/tcp/127.0.0.1/9000 || exit 1
printf 'GET /health/ready HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n' >&3
status=''
IFS= read -r -t 5 status <&3 || exit 1
[[ "$status" == *200* ]]
