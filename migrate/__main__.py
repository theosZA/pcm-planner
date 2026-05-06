"""
Command-line entry point for the PCM Season Planner migration package.

Usage:
    python -m migrate
    python -m migrate --target data/planner.sqlite --lachis-export path/to/export \\
        --mod-stages path/to/Stages \\
        --base-stages path/to/CM_Stages \\
        --stage-editor-exe path/to/CTStageEditor.exe

Default values for --target, --lachis-export, --mod-stages, --base-stages, and
--stage-editor-exe come from config.yaml and can be overridden on the command line.

Each run drops and recreates the database from scratch, then imports riders,
races, and stages from the Lachis export.  Stage Editor XMLs are cached and
reused automatically on subsequent runs. Pass --force-stage-export to delete
the cache and re-export everything (needed only when .cds stage files change).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from optimise import config
from migrate.races import import_lachis_race_and_stage_data
from migrate.riders import import_lachis_rider_data
from migrate.schema import initialise_database


def main() -> None:
    run_cfg = config.run_config()
    migrate_cfg = config.migrate_config()

    parser = argparse.ArgumentParser(
        description="Create and populate the PCM Season Planner SQLite database.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--target",
        default=None,
        metavar="PATH",
        help=f"Path to the planner SQLite database. Overrides config.yaml (default: {run_cfg.database}).",
    )
    parser.add_argument(
        "--lachis-export",
        default=None,
        metavar="PATH",
        help=f"Path to the Lachis Editor XML export folder. Overrides config.yaml (default: {migrate_cfg.lachis_export}).",
    )
    parser.add_argument(
        "--mod-stages",
        default=None,
        metavar="PATH",
        help=f"Path to the mod/workshop Stages folder. Overrides config.yaml (default: {migrate_cfg.mod_stages}).",
    )
    parser.add_argument(
        "--base-stages",
        default=None,
        metavar="PATH",
        help=f"Path to the base-game CM_Stages folder. Overrides config.yaml (default: {migrate_cfg.base_stages}).",
    )
    parser.add_argument(
        "--stage-editor-exe",
        default=None,
        metavar="PATH",
        help=f"Path to CTStageEditor.exe. Overrides config.yaml (default: {migrate_cfg.stage_editor_exe}).",
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

    target           = Path(args.target          if args.target          is not None else run_cfg.database)
    lachis_export    = args.lachis_export    if args.lachis_export    is not None else migrate_cfg.lachis_export
    mod_stages       = args.mod_stages       if args.mod_stages       is not None else migrate_cfg.mod_stages
    base_stages      = args.base_stages      if args.base_stages      is not None else migrate_cfg.base_stages
    stage_editor_exe = args.stage_editor_exe if args.stage_editor_exe is not None else migrate_cfg.stage_editor_exe

    if not lachis_export:
        raise SystemExit("lachis-export must be set in config.yaml or via --lachis-export")
    if not mod_stages:
        raise SystemExit("mod-stages must be set in config.yaml or via --mod-stages")
    if not base_stages:
        raise SystemExit("base-stages must be set in config.yaml or via --base-stages")
    if not stage_editor_exe:
        raise SystemExit("stage-editor-exe must be set in config.yaml or via --stage-editor-exe")

    # --- Schema setup -------------------------------------------------------
    initialise_database(target=target)
    print(f"Planner database ready (reset): {target}")

    # --- Rider import -------------------------------------------------------
    import_lachis_rider_data(
        target=target,
        lachis_export=Path(lachis_export),
    )

    # --- Race and stage import ----------------------------------------------
    import_lachis_race_and_stage_data(
        target=target,
        lachis_export=Path(lachis_export),
        mod_stages=Path(mod_stages),
        base_stages=Path(base_stages),
        stage_editor_exe=Path(stage_editor_exe),
        force_stage_export=args.force_stage_export,
    )


if __name__ == "__main__":
    main()
