"""
Team import and lookup functions for the PCM Season Planner migration.

Functions:
- import_teams(): reads DYN_team.xml and upserts all teams into the planner DB.
- mark_player_team(): sets the player column on the player's own team row.
- get_local_team_id(): maps a source_team_id to the planner's internal team PK.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from migrate.parsing import parse_xml_rows, clean_text, to_int


def import_teams(conn: sqlite3.Connection, lachis_export: Path) -> int:
    """Upsert all teams from DYN_team.xml into the team table.

    Returns the number of rows processed (not just new inserts — existing rows
    are updated in place via ON CONFLICT).
    """
    team_xml = lachis_export / "DYN_team.xml"
    count = 0

    for row in parse_xml_rows(team_xml, "DYN_team"):
        source_team_id = to_int(row.get("IDteam"))
        if source_team_id is None:
            continue

        name = clean_text(row.get("gene_sz_name"))
        short_name = clean_text(row.get("gene_sz_shortname"))
        abbreviation = clean_text(row.get("abbreviation"))
        jersey_abbreviation = clean_text(row.get("jersey_sz_abbreviation"))

        if not name:
            name = short_name or abbreviation or f"Team {source_team_id}"

        conn.execute(
            """
            INSERT INTO team (
                source_team_id,
                name,
                short_name,
                abbreviation,
                jersey_abbreviation
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(source_team_id) DO UPDATE SET
                name = excluded.name,
                short_name = excluded.short_name,
                abbreviation = excluded.abbreviation,
                jersey_abbreviation = excluded.jersey_abbreviation;
            """,
            (source_team_id, name, short_name, abbreviation, jersey_abbreviation),
        )
        count += 1

    return count


def mark_player_team(
    conn: sqlite3.Connection,
    source_team_id: int,
    player_name: str,
) -> None:
    """Set the player column on the player's own team row.

    All other team rows have player = NULL. This single row being non-NULL is
    how the planner identifies the player's team.
    """
    conn.execute(
        "UPDATE team SET player = ? WHERE source_team_id = ?;",
        (player_name, source_team_id),
    )


def get_local_team_id(
    conn: sqlite3.Connection,
    team_id: Optional[int],
    team_name: Optional[str],
) -> Optional[int]:
    """Resolve a team ID or name to a source_team_id that exists in the team table.

    - If team_id is given, it is verified against the DB and returned directly.
    - If team_name is given, the name/short_name/abbreviation columns are searched
      case-insensitively. Exact matches take priority over partial matches.
    - If neither is given, returns None (meaning no team filter is applied).

    Raises ValueError if the lookup is ambiguous or yields no results.
    """
    if team_id is not None:
        row = conn.execute(
            "SELECT source_team_id FROM team WHERE source_team_id = ?;",
            (team_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"No team found with source_team_id={team_id}")
        return int(row[0])

    if not team_name:
        return None

    search = team_name.strip().casefold()

    rows = conn.execute(
        "SELECT source_team_id, name, short_name, abbreviation FROM team;"
    ).fetchall()

    exact_matches: list[int] = []
    partial_matches: list[tuple[int, str]] = []

    for source_team_id, name, short_name, abbreviation in rows:
        values = [clean_text(name), clean_text(short_name), clean_text(abbreviation)]
        folded_values = [v.casefold() for v in values if v]

        if search in folded_values:
            exact_matches.append(int(source_team_id))
            continue

        if any(search in v for v in folded_values):
            label = " / ".join(v for v in values if v)
            partial_matches.append((int(source_team_id), label))

    if len(exact_matches) == 1:
        return exact_matches[0]
    if len(exact_matches) > 1:
        raise ValueError(
            f"Multiple exact team matches found for {team_name!r}: {exact_matches}"
        )
    if len(partial_matches) == 1:
        return partial_matches[0][0]
    if len(partial_matches) > 1:
        details = "\n".join(
            f"  {sid}: {label}" for sid, label in partial_matches
        )
        raise ValueError(
            f"Multiple partial team matches found for {team_name!r}:\n{details}\n"
            "Use --team-id instead."
        )

def get_local_team_id(
    conn: sqlite3.Connection,
    source_team_id: Optional[int],
) -> Optional[int]:
    """Return the planner's internal team PK for a given source_team_id, or None."""
    if source_team_id is None:
        return None

    row = conn.execute(
        "SELECT id FROM team WHERE source_team_id = ?;",
        (source_team_id,),
    ).fetchone()

    return int(row[0]) if row else None
