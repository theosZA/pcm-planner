"""
Command-line entry point for the PCM Season Planner optimiser.

Usage:
    python -m optimise --database data/planner.sqlite

Loads data, runs feasibility checks, then solves the CP-SAT model.

Exit code 0 = all checks passed. Exit code 1 = one or more checks failed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from optimise import constraints, db, scoring, solver


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
    parser.add_argument(
        "--time-limit",
        type=float,
        default=None,
        metavar="SECONDS",
        help="Maximum solver wall-clock time in seconds. Omit for no limit.",
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

    # --- Scoring matrix -------------------------------------------------------
    matrix = scoring.build_scoring_matrix(data)
    print(f"Rider-race scores computed: {len(matrix)} pairs "
          f"({len(data.riders)} riders × {len(data.races)} races)")
    print()

    # --- Validation checks ----------------------------------------------------
    print("Validation:")
    results = constraints.run_all_checks(data)
    for result in results:
        print(f"  {result}")

    if not all(r.passed for r in results):
        sys.exit(1)

    # --- CP-SAT solve ---------------------------------------------------------
    print()
    time_limit_msg = f"{args.time_limit}s" if args.time_limit is not None else "none"
    print(f"Solving…  (time limit: {time_limit_msg})")
    result = solver.solve(data, matrix, time_limit=args.time_limit)
    print(f"  Status:      {result.status}")
    print(f"  Objective:   {result.objective_value:,}  (sum of rider-race scores)")
    print(f"  Assignments: {result.total_assignments}  "
          f"({len(data.riders)} riders × {len(data.races)} races)")
    print()

    # --- Per-rider assignment summary -----------------------------------------
    race_days_map = {r.id: r.race_days for r in data.races}
    MAX_DAYS = 75

    print(f"  {'Rider':<30} {'Race days':>9}  {'/ 75':>4}")
    print(f"  {'-' * 30} {'---------':>9}  {'----':>4}")
    for rider in sorted(data.riders, key=lambda r: r.display_name):
        days = sum(
            race_days_map[race_id]
            for (rid, race_id), assigned_flag in result.assigned.items()
            if rid == rider.id and assigned_flag
        )
        bar = "#" * min(days, MAX_DAYS) + ("!" * (days - MAX_DAYS) if days > MAX_DAYS else "")
        print(f"  {rider.display_name:<30} {days:>9}  {bar}")

    # --- Persist to database --------------------------------------------------
    run_id = db.save_result(conn, result, args.time_limit)
    print()
    print(f"Assignments saved to database (optimise_run.id = {run_id}).")


if __name__ == "__main__":
    main()
