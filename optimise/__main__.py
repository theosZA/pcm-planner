"""
Command-line entry point for the PCM Season Planner optimiser.

Usage:
    python -m optimise
    python -m optimise --database data/planner.sqlite --time-limit 60

Loads data, runs feasibility checks, then solves the CP-SAT model.
Default values for --database and --time-limit come from config.yaml.

Exit code 0 = all checks passed. Exit code 1 = one or more checks failed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from optimise import config, db, scoring, solver, validation


def main() -> None:
    run_cfg = config.run_config()

    parser = argparse.ArgumentParser(
        description="PCM Season Planner optimiser.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--database",
        default=None,
        metavar="PATH",
        help=f"Path to the planner SQLite database. Overrides config.yaml (default: {run_cfg.database}).",
    )
    parser.add_argument(
        "--time-limit",
        type=float,
        default=None,
        metavar="SECONDS",
        help=f"Maximum solver wall-clock time in seconds. Overrides config.yaml (default: {run_cfg.time_limit}).",
    )
    args = parser.parse_args()

    database = args.database if args.database is not None else run_cfg.database
    time_limit = args.time_limit if args.time_limit is not None else run_cfg.time_limit

    penalties = config.race_day_penalties()

    conn = db.connect(Path(database))
    data = db.load_planner_data(conn)

    matrix = scoring.build_scoring_matrix(data)
    race_profiles = scoring.build_race_profiles(data)

    race_map = {r.id: r for r in data.races}
    compositions: dict[int, dict] = {}
    squad_comps = config.squad_compositions()
    for race_id, (profile, _stage_value) in race_profiles.items():
        race = race_map[race_id]
        composition = squad_comps.get((profile, race.rider_capacity))
        if composition is not None:
            compositions[race_id] = composition

    # --- Validation checks ----------------------------------------------------
    print("Validation:")
    results = validation.run_all_checks(data, race_profiles, penalties)
    for result in results:
        print(f"  {result}")

    if not all(r.passed for r in results):
        sys.exit(1)

    # --- CP-SAT solve ---------------------------------------------------------
    print()
    time_limit_msg = f"{time_limit} seconds" if time_limit is not None else "none"
    print(f"Solving…  (time limit: {time_limit_msg})")
    result = solver.solve(data, matrix, compositions, time_limit=time_limit, penalties=penalties)
    print(f"  Status:      {result.status}")
    print(f"  Objective:   {result.objective_value:,}  (scores minus race-day penalties)")
    print(f"  Assignments: {result.total_assignments}  "
          f"({len(data.riders)} riders × {len(data.races)} races)")
    print()

    # --- Per-rider assignment summary -----------------------------------------
    race_days_map = {r.id: r.race_days for r in data.races}
    p = penalties

    print(f"  {'Rider':<30} {'Days':>4}  Zone")
    print(f"  {'-' * 30} {'----':>4}  ----")
    for rider in sorted(data.riders, key=lambda r: r.display_name):
        days = sum(
            race_days_map[race_id]
            for rid, race_id in result.race_assignments
            if rid == rider.id
        )
        if days < p.target_min:
            zone = f"under  ({days - p.target_min:+d} vs target)"
        elif days <= p.target_max:
            zone = "OK"
        elif days <= p.upper_warning:
            zone = f"above  ({days - p.target_max:+d} vs target)"
        else:
            zone = f"WARN   ({days - p.upper_warning:+d} vs warning)"
        print(f"  {rider.display_name:<30} {days:>4}  {zone}")

    # --- Persist to database --------------------------------------------------
    run_id = db.save_result(conn, result, args.time_limit, race_profiles)
    print()
    print(f"Assignments saved to database (optimise_run.id = {run_id}).")


if __name__ == "__main__":
    main()
