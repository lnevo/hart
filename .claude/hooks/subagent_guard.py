#!/usr/bin/env python3
"""Block subagent shell commands that publish, touch hosts, or act on the railroad.

Runs as a PreToolUse hook from .claude/agents/*.md, so the main session is not
affected. Matches where a command starts, so searching for these names still works.
This is a guardrail against mistakes, not a security boundary.
"""
import json
import re
import sys

BLOCKED = re.compile(
    r"^\s*(\S+=\S*\s+)*(sudo\s+)?((ba|z)?sh\s+|python3?\s+|\S*python3?\s+)?(\S*/)?("
    r"deploy_hartrailroad\.sh|sync_hart_package\.sh|flash_nano\.py|serial_to_mqtt\.py|run_serial_mqtt"
    r"|mosquitto_pub|ssh|scp|rsync|make\s+deploy\S*"
    r"|git\s+(-C\s+\S+\s+)?(commit|push|merge|rebase|reset|stash|switch|checkout|restore|clean)"
    r")\b"
)


def main() -> int:
    command = json.load(sys.stdin).get("tool_input", {}).get("command", "")
    for part in re.split(r"&&|\|\||[;|\n]", command):
        if BLOCKED.search(part):
            print(f"Blocked for subagents: {part.strip()}. Report it to the main session instead.", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
