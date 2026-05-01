"""
Command-line entry point for the PCM Season Planner optimiser.

Usage:
    python -m optimise --database data/planner.sqlite

Currently performs a planning dry run: loads the data from the planner database,
prints a season summary (riders, races, race days), and runs feasibility checks.
No optimisation is performed yet.

Exit code 0 = all checks passed. Exit code 1 = one or more checks failed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from optimise import constraints, db


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PCM Season Planner optimiser.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--database",
        required=True,
        help="Path to the planner SQLite database (produced by python -m migrate).",
    )

    args = parser.parse_args()

    conn = db.connect(Path(args.database))
    data = db.load_planner_data(conn)

    # --- Season summary -------------------------------------------------------
    print(f"Team:   {data.player_team_name}  (player: {data.player_name})")
    print(f"Riders: {len(data.riders)}")
    print()

    print(f"Races:  {len(data.races)}")
    if data.races:
        total_unique_stage_days = sum(r.race_days for r in data.races)
        print(f"  Stage days across all races: {total_unique_stage_days}")
        print(f"  Rider-days demanded (× squad sizes): {data.total_race_days_demanded}")
        print(f"  Rider-days available (75 × {len(data.riders)} riders): {data.total_rider_days_available}")
        print()

        col_name = 42
        print(
            f"  {'Race':<{col_name}} {'Level':<12} {'Days':>4}  {'Squad':>5}  Dates"
        )
        print(
            f"  {'-' * col_name} {'-' * 12} {'----':>4}  {'-----':>5}  -----"
        )
        for race in data.races:
            if race.start_date and race.end_date:
                dates = f"{race.start_date} – {race.end_date}"
            else:
                dates = "dates unknown"
            print(
                f"  {race.name:<{col_name}} {race.level:<12} "
                f"{race.race_days:>4}  {race.rider_capacity:>5}  {dates}"
            )

    print()

    # --- Validation checks ----------------------------------------------------
    print("Validation:")
    results = constraints.run_all_checks(data)
    for result in results:
        print(f"  {result}")

    if not all(r.passed for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
