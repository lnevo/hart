#!/usr/bin/env python3
"""Build canonical car roster SoR and export to OperationsCarRoster.xml."""

from build_merged_car_roster import main as build_main
from export_operations_roster import main as export_main


def main() -> None:
    build_main()
    export_main()


if __name__ == "__main__":
    main()
