"""
Command-line entry point for the PCM Season Planner migration package.

Usage:
    python -m migrate --help
    python -m migrate --target data/planner.sqlite --reset
    python -m migrate --target data/planner.sqlite --lachis-export path/to/export --team-id 441 --season-year 2033
    python -m migrate --target data/planner.sqlite --lachis-export path/to/export --team-id 441 --season-year 2033 \\
        --import-races-and-stages \\
        --mod-stages path/to/Stages \\
        --base-stages path/to/CM_Stages \\
        --stage-editor-exe path/to/CTStageEditor.exe

The --import-races-and-stages step is the slowest because it invokes
CTStageEditor.exe to export per-stage metadata XML files. Cached XMLs are
reused automatically on subsequent runs. Pass --force-stage-export to delete
the cache and re-export everything (needed only when .cds stage files change).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from migrate.races import import_lachis_race_and_stage_data
from migrate.riders import import_lachis_rider_data
from migrate.schema import initialise_database


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create and populate the PCM Season Planner SQLite database.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--target",
        required=True,
        help="Path to the local planner SQLite database to create or update.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop all existing planner tables before recreating the schema. "
             "WARNING: this permanently deletes all data in the database.",
    )
    parser.add_argument(
        "--lachis-export",
        help="Path to the Lachis Editor XML export folder. "
             "Required for all import operations.",
    )
    parser.add_argument(
        "--import-races-and-stages",
        action="store_true",
        help="Import team-entered races and selected stages, enriched with "
             "Stage Editor XML metadata. Requires --lachis-export, "
             "--mod-stages, --base-stages, and --stage-editor-exe.",
    )
    parser.add_argument(
        "--mod-stages",
        help="Path to the mod/workshop Stages folder, searched before the base game.",
    )
    parser.add_argument(
        "--base-stages",
        help="Path to the base-game CM_Stages folder.",
    )
    parser.add_argument(
        "--stage-editor-exe",
        help="Path to CTStageEditor.exe.",
    )
    parser.add_argument(
        "--force-stage-export",
        action="store_true",
        help="Delete cached Stage Editor XMLs and re-export all stage data. "
             "Only needed if the underlying .cds stage files have changed. "
             "Without this flag, previously exported XMLs are reused, making "
             "repeated runs significantly faster.",
    )

    args = parser.parse_args()
    target = Path(args.target)

    # --- Schema setup -------------------------------------------------------
    initialise_database(target=target, reset=args.reset)
    print(f"Planner database schema ready: {target}")
    if args.reset:
        print("Existing planner tables were dropped and recreated.")
    else:
        print("Existing tables were preserved if already present.")

    # --- Rider import -------------------------------------------------------
    if args.lachis_export:
        import_lachis_rider_data(
            target=target,
            lachis_export=Path(args.lachis_export),
        )
    else:
        print("No --lachis-export supplied; schema created only.")

    # --- Race and stage import ----------------------------------------------
    if args.import_races_and_stages:
        if not args.lachis_export:
            raise SystemExit("--import-races-and-stages requires --lachis-export")
        if not args.mod_stages:
            raise SystemExit("--import-races-and-stages requires --mod-stages")
        if not args.base_stages:
            raise SystemExit("--import-races-and-stages requires --base-stages")
        if not args.stage_editor_exe:
            raise SystemExit("--import-races-and-stages requires --stage-editor-exe")

        import_lachis_race_and_stage_data(
            target=target,
            lachis_export=Path(args.lachis_export),
            mod_stages=Path(args.mod_stages),
            base_stages=Path(args.base_stages),
            stage_editor_exe=Path(args.stage_editor_exe),
            force_stage_export=args.force_stage_export,
        )


if __name__ == "__main__":
    main()
