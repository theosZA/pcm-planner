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
from optimise.model import RaceDayPenalties, RiderRole
from optimise.squad_config import SQUAD_COMPOSITIONS


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

    rdp = parser.add_argument_group(
        "race-day penalties",
        "Penalty config that shapes per-rider race-day totals in the objective.",
    )
    rdp.add_argument("--target-min",            type=int, default=60,  metavar="DAYS",  help="Target minimum race days (default: 60).")
    rdp.add_argument("--target-max",            type=int, default=70,  metavar="DAYS",  help="Target maximum race days (default: 70).")
    rdp.add_argument("--upper-warning",         type=int, default=75,  metavar="DAYS",  help="Warning threshold above target (default: 75).")
    rdp.add_argument("--absolute-max",          type=int, default=100, metavar="DAYS",  help="Hard cap on race days (default: 100).")
    rdp.add_argument("--under-min-penalty",     type=int, default=20,  metavar="PTS",   help="Penalty per day under target-min (default: 20).")
    rdp.add_argument("--above-target-penalty",  type=int, default=30,  metavar="PTS",   help="Penalty per day above target-max up to upper-warning (default: 30).")
    rdp.add_argument("--above-warning-penalty", type=int, default=200, metavar="PTS",   help="Penalty per day above upper-warning (default: 200).")

    args = parser.parse_args()

    penalties = RaceDayPenalties(
        target_min=args.target_min,
        target_max=args.target_max,
        upper_warning=args.upper_warning,
        absolute_max=args.absolute_max,
        under_min_penalty_per_day=args.under_min_penalty,
        above_target_penalty_per_day=args.above_target_penalty,
        above_warning_penalty_per_day=args.above_warning_penalty,
    )

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
    print("Squad compositions:")
    col_name = 42
    for race_id, (profile, _stage_value) in race_profiles.items():
        race = race_map[race_id]
        composition = SQUAD_COMPOSITIONS.get((profile, race.rider_capacity))
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
    results = constraints.run_all_checks(data, race_profiles)
    for result in results:
        print(f"  {result}")

    if not all(r.passed for r in results):
        sys.exit(1)

    # --- CP-SAT solve ---------------------------------------------------------
    print()
    time_limit_msg = f"{args.time_limit}s" if args.time_limit is not None else "none"
    print(f"Solving…  (time limit: {time_limit_msg})")
    result = solver.solve(data, matrix, compositions, time_limit=args.time_limit, penalties=penalties)
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
