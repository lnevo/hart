#!/usr/bin/env python3
"""Build canonical car roster SoR and export to OperationsCarRoster.xml."""

from build_merged_car_roster import main as build_main
from car_paths import CardPipelineError
from export_operations_roster import export_roster


def main() -> None:
    """Build the merged roster, then export it; CardPipelineError when the export has nothing to read."""
    build_main()
    export_roster()


if __name__ == "__main__":
    try:
        main()
    except CardPipelineError as exc:
        raise SystemExit(str(exc)) from exc
