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

from optimise import config, constraints, db, scoring, solver
from optimise.model import RiderRole


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

    # --- Season summary -------------------------------------------------------
    print(f"Team:   {data.player_team_name}  (player: {data.player_name})")
    print(f"Riders: {len(data.riders)}")
    print()

    print(f"Races:  {len(data.races)}")
    if data.races:
        total_unique_stage_days = sum(r.race_days for r in data.races)
        print(f"  Stage days across all races: {total_unique_stage_days}")
        print(f"  Rider-days demanded (× squad sizes): {data.total_race_days_demanded}")
        print(f"  Rider-days available ({penalties.absolute_max} × {len(data.riders)} riders): "
              f"{penalties.absolute_max * len(data.riders):,}")
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
    print(f"Rider-race-role scores computed: {len(matrix)} triples "
          f"({len(data.riders)} riders × {len(data.races)} races × {len(RiderRole)} roles)")
    print()

    race_profiles = scoring.build_race_profiles(data)

    # --- Squad compositions ---------------------------------------------------
    race_map = {r.id: r for r in data.races}
    compositions: dict[int, dict] = {}
    squad_comps = config.squad_compositions()
    print("Squad compositions:")
    col_name = 42
    for race_id, (profile, _stage_value) in race_profiles.items():
        race = race_map[race_id]
        composition = squad_comps.get((profile, race.rider_capacity))
        profile_label = profile.value
        if composition is None:
            roles_str = "(no composition defined)"
        else:
            compositions[race_id] = composition
            roles_str = "  ".join(
                f"{count}× {role.value}" for role, count in composition.items()
            )
        print(f"  {race.name:<{col_name}} [{profile_label}]  {roles_str}")
    print()

    # --- Validation checks ----------------------------------------------------
    print("Validation:")
    results = constraints.run_all_checks(data, race_profiles, penalties)
    for result in results:
        print(f"  {result}")

    if not all(r.passed for r in results):
        sys.exit(1)

    # --- CP-SAT solve ---------------------------------------------------------
    print()
    time_limit_msg = f"{time_limit}s" if time_limit is not None else "none"
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

    print(f"  Race-day bands: target {p.target_min}–{p.target_max}  "
          f"warning >{p.upper_warning}  cap {p.absolute_max}")
    print(f"  Penalties/day:  under-min {p.under_min_penalty_per_day}  "
          f"above-target {p.above_target_penalty_per_day}  "
          f"above-warning {p.above_warning_penalty_per_day}")
    print()
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
