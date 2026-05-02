"""
Race, stage, and team-race-entry import for the PCM Season Planner migration.

This module handles the second, more complex import phase: pulling in all races
the player's team is entered in, the stage schedules for those races, and the
Stage Editor metadata for each selected stage.

Functions (called in order by the orchestrator):
- import_race_classes(): upserts STA_race_class rows (e.g. Grand Tour, WorldTour).
- import_race_types(): upserts STA_race_type rows (terrain-weight profiles).
- import_team_race_entries(): reads DYN_team_race.xml for the player's team and
  records which races they are entered in.
- import_races_for_team_entries(): upserts the STA_race rows for those races,
  joining in class/type information.
- import_selected_stages_for_races(): upserts only the selected STA_stage rows
  for the imported races.
- update_race_dates_and_days(): derives start_date / end_date / race_days on
  each race row from its imported stages.
- import_lachis_race_and_stage_data(): top-level orchestrator that opens the DB
  connection and calls the above functions in sequence, then updates stage rows
  with Stage Editor XML metadata.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from migrate.parsing import (
    clean_text,
    clean_variant_name,
    normalise_level_from_race_class,
    parse_xml_rows,
    read_player_team,
    to_bool_int,
    to_int,
    to_iso_date,
)
from migrate.schema import insert_import_run
from migrate.stage_files import update_stages_with_stage_editor_metadata
from migrate.teams import get_local_team_id


def import_race_classes(conn: sqlite3.Connection, lachis_export: Path) -> int:
    """Upsert all race classes from STA_race_class.xml.

    Race classes encode the competition tier (Grand Tour, WorldTour, Pro, etc.)
    along with squad-size limits, calendar colour, and whether a race is a stage
    race or a one-day event.

    Returns the number of rows processed.
    """
    count = 0
    for row in parse_xml_rows(lachis_export / "STA_race_class.xml", "STA_race_class"):
        source_id = to_int(row.get("IDrace_class"))
        if source_id is None:
            continue

        conn.execute(
            """
            INSERT INTO race_class (
                source_race_class_id, constant_key,
                min_riders, max_riders,
                calendar_color, is_stage_race, sort_order, material_icon
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_race_class_id) DO UPDATE SET
                constant_key = excluded.constant_key,
                min_riders = excluded.min_riders,
                max_riders = excluded.max_riders,
                calendar_color = excluded.calendar_color,
                is_stage_race = excluded.is_stage_race,
                sort_order = excluded.sort_order,
                material_icon = excluded.material_icon;
            """,
            (
                source_id,
                clean_text(row.get("CONSTANT")),
                to_int(row.get("gene_i_min_riders")),
                to_int(row.get("gene_i_max_riders")),
                clean_text(row.get("gene_sz_calendar_color")),
                to_bool_int(row.get("gene_b_is_stagerace")),
                to_int(row.get("gene_i_sort_order")),
                clean_text(row.get("gene_sz_material")),
            ),
        )
        count += 1

    return count


def import_race_types(conn: sqlite3.Connection, lachis_export: Path) -> int:
    """Upsert all race types from STA_race_type.xml.

    Race types hold terrain-weight coefficients (mountain, hill, sprint, TT,
    cobble, etc.) used by PCM's race model. Stored for future optimiser use.

    Returns the number of rows processed.
    """
    count = 0
    for row in parse_xml_rows(lachis_export / "STA_race_type.xml", "STA_race_type"):
        source_id = to_int(row.get("IDrace_type"))
        if source_id is None:
            continue

        conn.execute(
            """
            INSERT INTO race_type (
                source_race_type_id, constant_key,
                mountain_weight, hill_weight, recovery_weight,
                itt_weight, cobble_weight, sprint_weight,
                flat_weight, prologue_weight, medium_mountain_weight
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_race_type_id) DO UPDATE SET
                constant_key = excluded.constant_key,
                mountain_weight = excluded.mountain_weight,
                hill_weight = excluded.hill_weight,
                recovery_weight = excluded.recovery_weight,
                itt_weight = excluded.itt_weight,
                cobble_weight = excluded.cobble_weight,
                sprint_weight = excluded.sprint_weight,
                flat_weight = excluded.flat_weight,
                prologue_weight = excluded.prologue_weight,
                medium_mountain_weight = excluded.medium_mountain_weight;
            """,
            (
                source_id,
                clean_text(row.get("CONSTANT")),
                to_int(row.get("mo_weight")),
                to_int(row.get("val_weight")),
                to_int(row.get("rec_weight")),
                to_int(row.get("itt_weight")),
                to_int(row.get("pav_weight")),
                to_int(row.get("sp_weight")),
                to_int(row.get("pl_weight")),
                to_int(row.get("prl_weight")),
                to_int(row.get("mm_weight")),
            ),
        )
        count += 1

    return count


def import_team_race_entries(
    conn: sqlite3.Connection,
    lachis_export: Path,
    source_team_id: int,
) -> tuple[int, set[int]]:
    """Import DYN_team_race rows for the player's team.

    Filters DYN_team_race.xml to only the rows belonging to source_team_id,
    recording each race entry and collecting the set of source_race_ids so the
    caller knows which races to import next.

    Returns (rows_imported, race_ids_entered).
    """
    count = 0
    race_ids: set[int] = set()
    local_team_id = get_local_team_id(conn, source_team_id)

    for row in parse_xml_rows(lachis_export / "DYN_team_race.xml", "DYN_team_race"):
        if to_int(row.get("fkIDteam")) != source_team_id:
            continue

        source_team_race_id = to_int(row.get("IDteam_race"))
        source_race_id = to_int(row.get("fkIDrace"))
        if source_team_race_id is None or source_race_id is None:
            continue

        race_ids.add(source_race_id)

        conn.execute(
            """
            INSERT INTO team_race_entry (
                source_team_race_id, team_id, race_id,
                source_team_id, source_race_id,
                invitation_state_id, roster_raw
            )
            VALUES (?, ?, NULL, ?, ?, ?, ?)
            ON CONFLICT(source_team_race_id) DO UPDATE SET
                team_id = excluded.team_id,
                source_team_id = excluded.source_team_id,
                source_race_id = excluded.source_race_id,
                invitation_state_id = excluded.invitation_state_id,
                roster_raw = excluded.roster_raw;
            """,
            (
                source_team_race_id,
                local_team_id,
                source_team_id,
                source_race_id,
                to_int(row.get("fkIDinvitation_state")),
                clean_text(row.get("gene_ilist_roster")),
            ),
        )
        count += 1

    return count, race_ids


def import_races_for_team_entries(
    conn: sqlite3.Connection,
    lachis_export: Path,
    race_ids: set[int],
) -> int:
    """Upsert STA_race rows for the races in race_ids.

    Joins in race_class and race_type information (already imported) to denormalise
    useful fields (rider_capacity, calendar_color, is_stage_race, level) onto the
    race row for convenient querying. Also backfills the race_id FK on
    team_race_entry rows once races are inserted.

    Returns the number of race rows processed.
    """
    count = 0

    for row in parse_xml_rows(lachis_export / "STA_race.xml", "STA_race"):
        source_race_id = to_int(row.get("IDrace"))
        if source_race_id is None or source_race_id not in race_ids:
            continue

        source_race_class_id = to_int(row.get("fkIDrace_class"))
        source_race_type_id = to_int(row.get("fkIDrace_type"))

        race_class_row = conn.execute(
            """
            SELECT id, constant_key, max_riders, calendar_color, is_stage_race
            FROM race_class
            WHERE source_race_class_id = ?;
            """,
            (source_race_class_id,),
        ).fetchone()

        race_type_row = conn.execute(
            "SELECT id, constant_key FROM race_type WHERE source_race_type_id = ?;",
            (source_race_type_id,),
        ).fetchone()

        race_class_id = race_class_row[0] if race_class_row else None
        race_class_constant = race_class_row[1] if race_class_row else ""
        rider_capacity = race_class_row[2] if race_class_row else None
        calendar_color = race_class_row[3] if race_class_row else ""
        is_stage_race = race_class_row[4] if race_class_row else None

        race_type_id = race_type_row[0] if race_type_row else None
        race_type_constant = race_type_row[1] if race_type_row else ""

        conn.execute(
            """
            INSERT INTO race (
                source_race_id, name, abbreviation, constant_key, filename,
                classification_xml, current_variant,
                source_race_class_id, source_race_type_id, race_class_id, race_type_id,
                source_first_stage_id, source_last_stage_id, number_stages_declared,
                rider_capacity, level,
                race_class_constant, race_type_constant, calendar_color, is_stage_race,
                selected
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_race_id) DO UPDATE SET
                name = excluded.name,
                abbreviation = excluded.abbreviation,
                constant_key = excluded.constant_key,
                filename = excluded.filename,
                classification_xml = excluded.classification_xml,
                current_variant = excluded.current_variant,
                source_race_class_id = excluded.source_race_class_id,
                source_race_type_id = excluded.source_race_type_id,
                race_class_id = excluded.race_class_id,
                race_type_id = excluded.race_type_id,
                source_first_stage_id = excluded.source_first_stage_id,
                source_last_stage_id = excluded.source_last_stage_id,
                number_stages_declared = excluded.number_stages_declared,
                rider_capacity = excluded.rider_capacity,
                level = excluded.level,
                race_class_constant = excluded.race_class_constant,
                race_type_constant = excluded.race_type_constant,
                calendar_color = excluded.calendar_color,
                is_stage_race = excluded.is_stage_race,
                selected = excluded.selected;
            """,
            (
                source_race_id,
                clean_text(row.get("gene_sz_race_name")),
                clean_text(row.get("gene_sz_abbreviation")),
                clean_text(row.get("CONSTANT")),
                clean_text(row.get("gene_sz_filename")),
                clean_text(row.get("gene_sz_classification_xml")),
                clean_text(row.get("gene_sz_currentvariant")),
                source_race_class_id,
                source_race_type_id,
                race_class_id,
                race_type_id,
                to_int(row.get("fkIDfirst_stage")),
                to_int(row.get("fkIDlast_stage")),
                to_int(row.get("gene_i_number_stages")),
                rider_capacity,
                normalise_level_from_race_class(race_class_constant),
                race_class_constant,
                race_type_constant,
                calendar_color,
                is_stage_race,
                to_bool_int(row.get("gene_b_selected")),
            ),
        )
        count += 1

    # Backfill race_id FK on team_race_entry now that races exist.
    conn.execute(
        """
        UPDATE team_race_entry
        SET race_id = (
            SELECT race.id
            FROM race
            WHERE race.source_race_id = team_race_entry.source_race_id
        )
        WHERE race_id IS NULL;
        """
    )

    return count


def import_selected_stages_for_races(
    conn: sqlite3.Connection,
    lachis_export: Path,
    race_ids: set[int],
) -> tuple[int, list[dict[str, object]]]:
    """Upsert only the selected (gene_b_selected = 1) stages for the given races.

    Returns (stages_imported, stage_rows) where stage_rows is a list of minimal
    dicts containing source_stage_id and variant — enough to drive stage file
    resolution and Stage Editor export in the next step.
    """
    count = 0
    stage_rows_for_resolution: list[dict[str, object]] = []

    for row in parse_xml_rows(lachis_export / "STA_stage.xml", "STA_stage"):
        source_race_id = to_int(row.get("fkIDrace"))
        if source_race_id is None or source_race_id not in race_ids:
            continue

        if to_bool_int(row.get("gene_b_selected")) != 1:
            continue

        source_stage_id = to_int(row.get("IDstage"))
        if source_stage_id is None:
            continue

        race_row = conn.execute(
            "SELECT id FROM race WHERE source_race_id = ?;",
            (source_race_id,),
        ).fetchone()
        if race_row is None:
            continue

        local_race_id = int(race_row[0])
        variant = clean_variant_name(row.get("gene_sz_variant"))

        conn.execute(
            """
            INSERT INTO stage (
                source_stage_id, race_id, source_race_id,
                stage_number, stage_day, stage_month,
                computed_date_raw, stage_date,
                selected, constant_key, variant
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_stage_id) DO UPDATE SET
                race_id = excluded.race_id,
                source_race_id = excluded.source_race_id,
                stage_number = excluded.stage_number,
                stage_day = excluded.stage_day,
                stage_month = excluded.stage_month,
                computed_date_raw = excluded.computed_date_raw,
                stage_date = excluded.stage_date,
                selected = excluded.selected,
                constant_key = excluded.constant_key,
                variant = excluded.variant;
            """,
            (
                source_stage_id,
                local_race_id,
                source_race_id,
                to_int(row.get("gene_i_stage_number")),
                to_int(row.get("gene_i_day")),
                to_int(row.get("gene_i_month")),
                to_int(row.get("gene_i_computed_date")),
                to_iso_date(row.get("gene_i_computed_date")),
                1,
                clean_text(row.get("CONSTANT")),
                variant,
            ),
        )

        stage_rows_for_resolution.append(
            {"source_stage_id": source_stage_id, "variant": variant}
        )
        count += 1

    return count, stage_rows_for_resolution


def apply_race_rules_overrides(
    conn: sqlite3.Connection,
    lachis_export: Path,
    race_ids: set[int],
) -> int:
    """Apply per-race rider-capacity overrides from STA_race_rules.xml.

    STA_race_rules rows carry gene_i_max_riders / gene_i_min_riders that
    supersede the class-level defaults already written onto the race row.
    Only races in race_ids are updated.

    Returns the number of race rows updated.
    """
    count = 0
    for row in parse_xml_rows(lachis_export / "STA_race_rules.xml", "STA_race_rules"):
        source_race_id = to_int(row.get("fkIDrace"))
        if source_race_id is None or source_race_id not in race_ids:
            continue

        max_riders = to_int(row.get("gene_i_max_riders"))
        if max_riders is None:
            continue

        cursor = conn.execute(
            "UPDATE race SET rider_capacity = ? WHERE source_race_id = ?;",
            (max_riders, source_race_id),
        )
        count += cursor.rowcount

    return count


def update_race_dates_and_days(conn: sqlite3.Connection) -> None:
    """Derive start_date, end_date, and race_days on each race from its stage rows.

    Only updates races that have at least one imported stage.
    """
    conn.execute(
        """
        UPDATE race
        SET
            start_date = (
                SELECT MIN(stage.stage_date)
                FROM stage
                WHERE stage.race_id = race.id
            ),
            end_date = (
                SELECT MAX(stage.stage_date)
                FROM stage
                WHERE stage.race_id = race.id
            ),
            race_days = (
                SELECT COUNT(*)
                FROM stage
                WHERE stage.race_id = race.id
            )
        WHERE EXISTS (
            SELECT 1 FROM stage WHERE stage.race_id = race.id
        );
        """
    )


def import_lachis_race_and_stage_data(
    target: Path,
    lachis_export: Path,
    mod_stages: Path,
    base_stages: Path,
    stage_editor_exe: Path,
    force_stage_export: bool = False,
) -> None:
    """Import races, team entries, stages, and Stage Editor metadata in one transaction.

    Reads the player's team from GAM_user.xml, then orchestrates the full
    race/stage import pipeline:
      1. Race classes and race types (reference data).
      2. Team race entries (which races the player's team is entered in).
      3. Race rows for those entries.
      4. Selected stage rows for those races.
      5. Stage Editor XML metadata for each resolved stage file.
      6. Race date/day counts derived from imported stages.

    If force_stage_export is True, existing cached Stage Editor XMLs are deleted
    and all stages are re-exported. Leave False (default) to reuse cached XMLs.
    """
    source_team_id, player_name = read_player_team(lachis_export)
    print(f"Player: {player_name!r} — team source_id: {source_team_id}")

    with sqlite3.connect(target) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")

        insert_import_run(
            conn=conn,
            lachis_export=lachis_export,
            notes="Import races, stages, and Stage Editor metadata",
            mod_stages_path=mod_stages,
            base_stages_path=base_stages,
            stage_editor_path=stage_editor_exe,
        )

        race_classes_imported = import_race_classes(conn, lachis_export)
        race_types_imported = import_race_types(conn, lachis_export)

        team_race_entries_imported, race_ids = import_team_race_entries(
            conn=conn,
            lachis_export=lachis_export,
            source_team_id=source_team_id,
        )

        races_imported = import_races_for_team_entries(
            conn=conn,
            lachis_export=lachis_export,
            race_ids=race_ids,
        )

        race_rules_overridden = apply_race_rules_overrides(
            conn=conn,
            lachis_export=lachis_export,
            race_ids=race_ids,
        )

        stages_imported, stage_rows = import_selected_stages_for_races(
            conn=conn,
            lachis_export=lachis_export,
            race_ids=race_ids,
        )

        stages_updated, missing_stage_files, missing_exported_xml = (
            update_stages_with_stage_editor_metadata(
                conn=conn,
                stage_rows=stage_rows,
                mod_stages=mod_stages,
                base_stages=base_stages,
                stage_editor_exe=stage_editor_exe,
                force_export=force_stage_export,
            )
        )

        update_race_dates_and_days(conn)

        conn.commit()

    print(f"Race classes imported: {race_classes_imported}")
    print(f"Race types imported: {race_types_imported}")
    print(f"Team race entries imported: {team_race_entries_imported}")
    print(f"Team-entered races imported: {races_imported}")
    print(f"Race rules overrides applied: {race_rules_overridden}")
    print(f"Selected stages imported: {stages_imported}")
    print(f"Stages updated with Stage Editor XML metadata: {stages_updated}")
    print(f"Missing stage files: {missing_stage_files}")
    print(f"Missing exported stage XML files: {missing_exported_xml}")
