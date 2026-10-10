#!/bin/sh
# Samba decoy: foreground smbd + rsyslog feeding the shared audit volume.
# Runtime writable state comes from tmpfs mounts (compose); the rootfs stays
# read-only. rsyslog must start first so /dev/log exists for smbd.
set -eu
touch /decoy-logs/samba-audit.log
rsyslogd
exec smbd -F -S
