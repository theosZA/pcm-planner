"""
Database access layer for the PCM Season Planner optimiser.

All SQL queries against the planner SQLite database live here. This module is
read-only — it never writes to or modifies the database.

Functions:
- connect(): open a connection to the planner database.
- load_planner_data(): load riders, races, and team metadata into a PlannerData
  instance ready for validation and optimisation.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from optimise.model import PlannerData, Race, Rider, Stage


def connect(db_path: Path) -> sqlite3.Connection:
    """Open a connection to the planner SQLite database.

    Uses sqlite3.Row as the row factory so columns can be accessed by name.
    Raises FileNotFoundError if the database file does not exist.
    """
    if not db_path.exists():
        raise FileNotFoundError(f"Planner database not found: {db_path}")

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


def _load_player_team(conn: sqlite3.Connection) -> tuple[str, str]:
    """Return (team_name, player_name) for the player's team.

    Raises ValueError if no player team exists in the database, which means the
    migration has not been run yet.
    """
    row = conn.execute(
        "SELECT name, player FROM team WHERE player IS NOT NULL LIMIT 1;"
    ).fetchone()

    if row is None:
        raise ValueError(
            "No player team found in the database. "
            "Run the migration (python -m migrate ...) first."
        )

    return str(row["name"]), str(row["player"])


def _load_riders(conn: sqlite3.Connection) -> list[Rider]:
    """Load all riders on the player's team, joined with their performance stats."""
    rows = conn.execute(
        """
        SELECT
            r.id,
            r.source_rider_id,
            r.display_name,
            rs.flat,
            rs.hill,
            rs.medium_mountain,
            rs.mountain,
            rs.time_trial,
            rs.prologue,
            rs.cobble,
            rs.sprint,
            rs.acceleration,
            rs.stamina,
            rs.resistance,
            rs.recovery,
            rs.baroudeur
        FROM rider r
        JOIN team t ON t.id = r.team_id
        LEFT JOIN rider_stat rs ON rs.rider_id = r.id
        WHERE t.player IS NOT NULL
        ORDER BY r.display_name;
        """
    ).fetchall()

    return [
        Rider(
            id=row["id"],
            source_rider_id=row["source_rider_id"],
            display_name=row["display_name"],
            flat=row["flat"],
            hill=row["hill"],
            medium_mountain=row["medium_mountain"],
            mountain=row["mountain"],
            time_trial=row["time_trial"],
            prologue=row["prologue"],
            cobble=row["cobble"],
            sprint=row["sprint"],
            acceleration=row["acceleration"],
            stamina=row["stamina"],
            resistance=row["resistance"],
            recovery=row["recovery"],
            baroudeur=row["baroudeur"],
        )
        for row in rows
    ]


def _load_races(conn: sqlite3.Connection) -> list[Race]:
    """Load races the player's team is actively entered in, ordered by start date.

    Only invitation states that represent an actual entry are included:
      1 — Mandatory
      3 — Entered (can withdraw)
      8 — National champs with at least one eligible rider

    Excluded states:
      6 — Not entered (invite requestable)
      11 — National/continental/world champs with no eligible riders yet

    Races are loaded regardless of whether stage data was successfully imported,
    so the validation layer can flag any with missing data (race_days = 0 or
    rider_capacity = 0).
    """
    rows = conn.execute(
        """
        SELECT
            race.id,
            race.source_race_id,
            race.name,
            COALESCE(race.abbreviation, '') AS abbreviation,
            COALESCE(race.level, 'unknown') AS level,
            race.start_date,
            race.end_date,
            COALESCE(race.race_days, 0) AS race_days,
            COALESCE(race.rider_capacity, 0) AS rider_capacity,
            COALESCE(race.is_stage_race, 0) AS is_stage_race,
            tre.invitation_state_id
        FROM race
        JOIN team_race_entry tre ON tre.race_id = race.id
        JOIN team t ON t.id = tre.team_id
        WHERE t.player IS NOT NULL
          AND tre.invitation_state_id IN (1, 3, 8)
        ORDER BY race.start_date, race.name;
        """
    ).fetchall()

    return [
        Race(
            id=row["id"],
            source_race_id=row["source_race_id"],
            name=row["name"],
            abbreviation=row["abbreviation"],
            level=row["level"],
            start_date=row["start_date"],
            end_date=row["end_date"],
            race_days=row["race_days"],
            rider_capacity=row["rider_capacity"],
            is_stage_race=bool(row["is_stage_race"]),
            invitation_state_id=row["invitation_state_id"],
        )
        for row in rows
    ]


def _load_stages(conn: sqlite3.Connection) -> list[Stage]:
    """Load stage terrain data for all races the player's team is entered in."""
    rows = conn.execute(
        """
        SELECT
            s.id,
            s.race_id,
            s.stage_type,
            s.relief
        FROM stage s
        JOIN race ON race.id = s.race_id
        JOIN team_race_entry tre ON tre.race_id = race.id
        JOIN team t ON t.id = tre.team_id
        WHERE t.player IS NOT NULL
          AND tre.invitation_state_id IN (1, 3, 8)
        ORDER BY s.race_id, s.stage_number;
        """
    ).fetchall()

    return [
        Stage(
            id=row["id"],
            race_id=row["race_id"],
            stage_type=row["stage_type"],
            relief=row["relief"],
        )
        for row in rows
    ]


def load_planner_data(conn: sqlite3.Connection) -> PlannerData:
    """Load all data needed for a planning run from the planner database.

    Returns a PlannerData instance containing riders, races, and team metadata.
    Raises ValueError if the database does not contain a populated player team.
    """
    team_name, player_name = _load_player_team(conn)
    riders = _load_riders(conn)
    races = _load_races(conn)
    stages = _load_stages(conn)

    return PlannerData(
        player_team_name=team_name,
        player_name=player_name,
        riders=riders,
        races=races,
        stages=stages,
    )
