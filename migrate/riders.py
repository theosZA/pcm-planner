"""
Rider and rider stat import for the PCM Season Planner migration.

Functions:
- import_riders_and_stats(): reads DYN_cyclist.xml and upserts rider rows and
  their associated rider_stat rows. Optionally filters to a single team.
- import_lachis_rider_data(): top-level orchestrator that opens a DB connection,
  imports teams, resolves the team filter, then imports riders and stats.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

import datetime

from migrate.parsing import (
    parse_xml_rows,
    clean_text,
    to_int,
    calculate_age_from_birthdate,
    read_game_date,
    read_player_team,
)
from migrate.schema import insert_import_run
from migrate.teams import import_teams, mark_player_team, get_local_team_id


def import_riders_and_stats(
    conn: sqlite3.Connection,
    lachis_export: Path,
    source_team_filter: Optional[int],
    game_date: Optional[datetime.date],
) -> tuple[int, int]:
    """Upsert riders and their stats from DYN_cyclist.xml.

    If source_team_filter is set, only riders belonging to that team are imported.
    Returns (riders_imported, stats_imported) — both counts are identical because
    every rider row has exactly one rider_stat row.
    """
    cyclist_xml = lachis_export / "DYN_cyclist.xml"
    riders_imported = 0
    stats_imported = 0

    for row in parse_xml_rows(cyclist_xml, "DYN_cyclist"):
        source_rider_id = to_int(row.get("IDcyclist"))
        if source_rider_id is None:
            continue

        source_team_id = to_int(row.get("fkIDteam"))
        if source_team_filter is not None and source_team_id != source_team_filter:
            continue

        local_team_id = get_local_team_id(conn, source_team_id)

        first_name = clean_text(row.get("gene_sz_firstname"))
        last_name = clean_text(row.get("gene_sz_lastname"))
        display_name = clean_text(row.get("gene_sz_firstlastname"))

        if not display_name:
            display_name = " ".join(p for p in [first_name, last_name] if p).strip()
        if not display_name:
            display_name = f"Rider {source_rider_id}"

        birthdate_raw = to_int(row.get("gene_i_birthdate"))
        age = calculate_age_from_birthdate(birthdate_raw, game_date)

        conn.execute(
            """
            INSERT INTO rider (
                source_rider_id, team_id, source_team_id,
                first_name, last_name, display_name,
                birthdate_raw, age
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_rider_id) DO UPDATE SET
                team_id = excluded.team_id,
                source_team_id = excluded.source_team_id,
                first_name = excluded.first_name,
                last_name = excluded.last_name,
                display_name = excluded.display_name,
                birthdate_raw = excluded.birthdate_raw,
                age = excluded.age;
            """,
            (
                source_rider_id, local_team_id, source_team_id,
                first_name, last_name, display_name,
                birthdate_raw, age,
            ),
        )

        rider_db_id_row = conn.execute(
            "SELECT id FROM rider WHERE source_rider_id = ?;",
            (source_rider_id,),
        ).fetchone()

        if rider_db_id_row is None:
            raise RuntimeError(f"Failed to retrieve inserted rider {source_rider_id}")

        rider_id = int(rider_db_id_row[0])

        conn.execute(
            """
            INSERT INTO rider_stat (
                rider_id,
                flat, hill, medium_mountain, mountain,
                time_trial, prologue, cobble,
                sprint, acceleration,
                stamina, resistance, recovery, baroudeur
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(rider_id) DO UPDATE SET
                flat = excluded.flat,
                hill = excluded.hill,
                medium_mountain = excluded.medium_mountain,
                mountain = excluded.mountain,
                time_trial = excluded.time_trial,
                prologue = excluded.prologue,
                cobble = excluded.cobble,
                sprint = excluded.sprint,
                acceleration = excluded.acceleration,
                stamina = excluded.stamina,
                resistance = excluded.resistance,
                recovery = excluded.recovery,
                baroudeur = excluded.baroudeur;
            """,
            (
                rider_id,
                to_int(row.get("charac_i_plain")),
                to_int(row.get("charac_i_hill")),
                to_int(row.get("charac_i_medium_mountain")),
                to_int(row.get("charac_i_mountain")),
                to_int(row.get("charac_i_timetrial")),
                to_int(row.get("charac_i_prologue")),
                to_int(row.get("charac_i_cobble")),
                to_int(row.get("charac_i_sprint")),
                to_int(row.get("charac_i_acceleration")),
                to_int(row.get("charac_i_endurance")),
                to_int(row.get("charac_i_resistance")),
                to_int(row.get("charac_i_recuperation")),
                to_int(row.get("charac_i_baroudeur")),
            ),
        )

        riders_imported += 1
        stats_imported += 1

    return riders_imported, stats_imported


def import_lachis_rider_data(
    target: Path,
    lachis_export: Path,
) -> None:
    """Import teams, riders, and rider stats from a Lachis XML export folder.

    Opens target, records an import_run entry, reads the in-game date from
    GAM_config.xml, reads the player's team from GAM_user.xml, imports all
    teams, marks the player's team, then imports riders from that team.
    Commits on success.

    Raises FileNotFoundError if lachis_export does not exist or is not a directory.
    """
    if not lachis_export.exists() or not lachis_export.is_dir():
        raise FileNotFoundError(f"Lachis export folder not found: {lachis_export}")

    game_date = read_game_date(lachis_export)
    print(f"Game date (from GAM_config.xml): {game_date}")

    source_team_id, player_name = read_player_team(lachis_export)
    print(f"Player: {player_name!r} — team source_id: {source_team_id}")

    with sqlite3.connect(target) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")

        import_run_id = insert_import_run(
            conn=conn,
            lachis_export=lachis_export,
            notes="Import teams, riders, and rider stats",
        )

        teams_imported = import_teams(conn, lachis_export)
        mark_player_team(conn, source_team_id, player_name)

        riders_imported, stats_imported = import_riders_and_stats(
            conn=conn,
            lachis_export=lachis_export,
            source_team_filter=source_team_id,
            game_date=game_date,
        )

        conn.commit()

    print(f"Import run ID: {import_run_id}")
    print(f"Teams imported: {teams_imported}")
    print(f"Riders imported for team {source_team_id} ({player_name!r}): {riders_imported}")
    print(f"Rider stat rows imported: {stats_imported}")
