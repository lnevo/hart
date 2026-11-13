#!/usr/bin/env bash
# Moved to tools/hosts/sync_hart_package.sh (ADR-007 amendment 2026-11-12). This wrapper
# keeps the old command working.
# main_guard follows: ../../tools/hosts/sync_hart_package.sh
exec "$(cd "$(dirname "$0")/../.." && pwd)/tools/hosts/sync_hart_package.sh" "$@"
