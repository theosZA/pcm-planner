"""
Database schema and setup for the PCM Season Planner SQLite database.

Responsibilities:
- DROP_SQL / SCHEMA_SQL: complete SQL DDL for all planner tables and indexes.
- initialise_database(): creates or optionally resets the planner database.
- insert_import_run(): records a new import session for audit purposes.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional


DROP_SQL = """
PRAGMA foreign_keys = OFF;

DROP TABLE IF EXISTS optimise_assignment;
DROP TABLE IF EXISTS optimise_race;
DROP TABLE IF EXISTS optimise_run;
DROP TABLE IF EXISTS stage;
DROP TABLE IF EXISTS team_race_entry;
DROP TABLE IF EXISTS race;
DROP TABLE IF EXISTS race_type;
DROP TABLE IF EXISTS race_class;
DROP TABLE IF EXISTS rider_stat;
DROP TABLE IF EXISTS rider;
DROP TABLE IF EXISTS team;
DROP TABLE IF EXISTS import_run;
DROP TABLE IF EXISTS schema_version;

PRAGMA foreign_keys = ON;
"""


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_version (
    id INTEGER PRIMARY KEY,
    version INTEGER NOT NULL,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    description TEXT
);

CREATE TABLE IF NOT EXISTS import_run (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    lachis_export_path TEXT,
    mod_stages_path TEXT,
    base_stages_path TEXT,
    stage_editor_path TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS team (
    id INTEGER PRIMARY KEY,
    source_team_id INTEGER NOT NULL UNIQUE,

    name TEXT NOT NULL,
    short_name TEXT,
    abbreviation TEXT,
    jersey_abbreviation TEXT,
    player TEXT
);

CREATE TABLE IF NOT EXISTS rider (
    id INTEGER PRIMARY KEY,
    source_rider_id INTEGER NOT NULL UNIQUE,

    team_id INTEGER,
    source_team_id INTEGER,

    first_name TEXT,
    last_name TEXT,
    display_name TEXT NOT NULL,

    birthdate_raw INTEGER,
    age INTEGER,

    FOREIGN KEY (team_id) REFERENCES team(id)
);

CREATE TABLE IF NOT EXISTS rider_stat (
    rider_id INTEGER PRIMARY KEY,

    flat INTEGER,
    hill INTEGER,
    medium_mountain INTEGER,
    mountain INTEGER,

    time_trial INTEGER,
    prologue INTEGER,
    cobble INTEGER,

    sprint INTEGER,
    acceleration INTEGER,

    stamina INTEGER,
    resistance INTEGER,
    recovery INTEGER,
    baroudeur INTEGER,

    FOREIGN KEY (rider_id) REFERENCES rider(id)
);

CREATE TABLE IF NOT EXISTS race_class (
    id INTEGER PRIMARY KEY,
    source_race_class_id INTEGER NOT NULL UNIQUE,

    constant_key TEXT,
    min_riders INTEGER,
    max_riders INTEGER,
    calendar_color TEXT,
    is_stage_race INTEGER,
    sort_order INTEGER,
    material_icon TEXT
);

CREATE TABLE IF NOT EXISTS race_type (
    id INTEGER PRIMARY KEY,
    source_race_type_id INTEGER NOT NULL UNIQUE,

    constant_key TEXT,

    mountain_weight INTEGER,
    hill_weight INTEGER,
    recovery_weight INTEGER,
    itt_weight INTEGER,
    cobble_weight INTEGER,
    sprint_weight INTEGER,
    flat_weight INTEGER,
    prologue_weight INTEGER,
    medium_mountain_weight INTEGER
);

CREATE TABLE IF NOT EXISTS race (
    id INTEGER PRIMARY KEY,
    source_race_id INTEGER NOT NULL UNIQUE,

    name TEXT NOT NULL,
    abbreviation TEXT,
    constant_key TEXT,
    filename TEXT,
    classification_xml TEXT,
    current_variant TEXT,

    source_race_class_id INTEGER,
    source_race_type_id INTEGER,
    race_class_id INTEGER,
    race_type_id INTEGER,

    source_first_stage_id INTEGER,
    source_last_stage_id INTEGER,
    number_stages_declared INTEGER,

    start_date TEXT,
    end_date TEXT,
    race_days INTEGER,

    rider_capacity INTEGER,
    level TEXT,

    race_class_constant TEXT,
    race_type_constant TEXT,
    calendar_color TEXT,
    is_stage_race INTEGER,

    selected INTEGER,

    FOREIGN KEY (race_class_id) REFERENCES race_class(id),
    FOREIGN KEY (race_type_id) REFERENCES race_type(id)
);

CREATE TABLE IF NOT EXISTS team_race_entry (
    id INTEGER PRIMARY KEY,
    source_team_race_id INTEGER NOT NULL UNIQUE,

    team_id INTEGER,
    race_id INTEGER,

    source_team_id INTEGER NOT NULL,
    source_race_id INTEGER NOT NULL,

    invitation_state_id INTEGER,
    roster_raw TEXT,

    FOREIGN KEY (team_id) REFERENCES team(id),
    FOREIGN KEY (race_id) REFERENCES race(id)
);

CREATE TABLE IF NOT EXISTS stage (
    id INTEGER PRIMARY KEY,
    source_stage_id INTEGER NOT NULL UNIQUE,

    race_id INTEGER,
    source_race_id INTEGER NOT NULL,

    stage_number INTEGER NOT NULL,
    stage_day INTEGER,
    stage_month INTEGER,
    computed_date_raw INTEGER,
    stage_date TEXT,

    selected INTEGER,
    constant_key TEXT,
    variant TEXT NOT NULL,

    resolved_variant TEXT,
    cds_source TEXT,
    cds_path TEXT,
    cdx_path TEXT,
    stage_metadata_source TEXT,
    stage_metadata_xml_path TEXT,

    stage_name TEXT,
    region_id INTEGER,
    region_name TEXT,

    stage_type TEXT,
    relief TEXT,

    race_length_km REAL,
    spline_length_km REAL,

    elevation_total_m REAL,
    elevation_second_half_m REAL,
    elevation_last_20km_m REAL,
    elevation_last_3km_m REAL,
    elevation_last_1km_m REAL,

    uphill_sprint REAL,
    time_gap INTEGER,
    gene_f_mountain REAL,

    altitude_max_m REAL,
    altitude_start_line_m REAL,
    altitude_finish_line_m REAL,

    max_local_slope REAL,

    cumulated_pavement_km REAL,
    cumulated_dirt_road_km REAL,
    cumulated_climbing_km REAL,

    cobblestone_difficulty_ratio REAL,
    cobblestone_difficulty_type INTEGER,
    dirt_road_difficulty_ratio REAL,
    dirt_road_difficulty_type INTEGER,

    last_summit_position_km REAL,
    last_summit_ascension_length_before_km REAL,
    last_summit_ascension_slope_before REAL,
    last_summit_ascension_denivele_before_m REAL,

    wind_force INTEGER,

    sprint_count INTEGER,
    pavement_count INTEGER,
    dirt_road_count INTEGER,

    FOREIGN KEY (race_id) REFERENCES race(id)
);

CREATE INDEX IF NOT EXISTS idx_rider_team_id
    ON rider(team_id);

CREATE INDEX IF NOT EXISTS idx_race_dates
    ON race(start_date, end_date);

CREATE INDEX IF NOT EXISTS idx_race_class
    ON race(race_class_id);

CREATE INDEX IF NOT EXISTS idx_race_type
    ON race(race_type_id);

CREATE INDEX IF NOT EXISTS idx_team_race_entry_team
    ON team_race_entry(team_id);

CREATE INDEX IF NOT EXISTS idx_team_race_entry_race
    ON team_race_entry(race_id);

CREATE INDEX IF NOT EXISTS idx_stage_race
    ON stage(race_id);

CREATE INDEX IF NOT EXISTS idx_stage_date
    ON stage(stage_date);

CREATE INDEX IF NOT EXISTS idx_stage_variant
    ON stage(variant);

CREATE TABLE IF NOT EXISTS optimise_run (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    solver_status TEXT NOT NULL,
    objective_value INTEGER NOT NULL,
    time_limit_seconds REAL  -- NULL means no limit was set
);

CREATE TABLE IF NOT EXISTS optimise_race (
    id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL,
    race_id INTEGER NOT NULL,
    squad_profile TEXT NOT NULL,
    stage_value INTEGER NOT NULL,
    FOREIGN KEY (run_id) REFERENCES optimise_run(id),
    FOREIGN KEY (race_id) REFERENCES race(id),
    UNIQUE (run_id, race_id)
);

CREATE TABLE IF NOT EXISTS optimise_assignment (
    id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL,
    rider_id INTEGER NOT NULL,
    race_id INTEGER NOT NULL,
    rider_role TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES optimise_run(id),
    FOREIGN KEY (rider_id) REFERENCES rider(id),
    FOREIGN KEY (race_id) REFERENCES race(id),
    UNIQUE (run_id, rider_id, race_id)
);

CREATE INDEX IF NOT EXISTS idx_optimise_assignment_run
    ON optimise_assignment(run_id);

CREATE INDEX IF NOT EXISTS idx_optimise_assignment_rider
    ON optimise_assignment(rider_id);
"""


def initialise_database(target: Path, reset: bool) -> None:
    """Create (or optionally reset) the planner SQLite database and apply the schema.

    If reset is True, all existing planner tables are dropped before the schema
    is recreated. This is a destructive operation — use only for a clean rebuild.
    Creates the parent directory of target if it does not already exist.
    """
    target.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(target) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")

        if reset:
            conn.executescript(DROP_SQL)

        conn.executescript(SCHEMA_SQL)

        conn.execute(
            """
            INSERT INTO schema_version (version, description)
            SELECT ?, ?
            WHERE NOT EXISTS (
                SELECT 1 FROM schema_version WHERE version = ?
            );
            """,
            (1, "Initial empty planner schema", 1),
        )

        conn.commit()


def insert_import_run(
    conn: sqlite3.Connection,
    lachis_export: Path,
    notes: str,
    mod_stages_path: Optional[Path] = None,
    base_stages_path: Optional[Path] = None,
    stage_editor_path: Optional[Path] = None,
) -> int:
    """Insert a new import_run row and return its auto-generated ID.

    The import_run table acts as an audit log — each run records the source
    paths used and any descriptive notes. The stage-related paths are optional
    and are only populated during the race/stage import phase.
    """
    cursor = conn.execute(
        """
        INSERT INTO import_run (
            lachis_export_path,
            mod_stages_path,
            base_stages_path,
            stage_editor_path,
            notes
        )
        VALUES (?, ?, ?, ?, ?);
        """,
        (
            str(lachis_export),
            str(mod_stages_path) if mod_stages_path is not None else None,
            str(base_stages_path) if base_stages_path is not None else None,
            str(stage_editor_path) if stage_editor_path is not None else None,
            notes,
        ),
    )
    return int(cursor.lastrowid)
