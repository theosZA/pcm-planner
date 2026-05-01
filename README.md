# PCM Season Planner

A companion planning tool for **Pro Cycling Manager 2024** season scheduling.

The goal of this project is to help create better team race calendars than PCM's built-in automated planner, while still preserving the fun strategic decisions: choosing Grand Tour squads, assigning key riders to major objectives, and shaping the season around the team's strengths.

---

## Current status

The data import pipeline is complete. The `migrate` package can:

- Read the active in-game date and player team automatically from the Lachis export (no manual configuration needed).
- Create the local planner SQLite database schema from scratch, or reset and rebuild it.
- Import all teams, and import riders and rider stats for the player's team.
- Calculate exact rider ages as of the in-game date.
- Import all races the player's team is entered in, along with their race class, race type, and stage schedules.
- Resolve stage variant names to real `.cds` files (following CDX redirect chains across mod and base-game Stages folders).
- Invoke `CTStageEditor.exe` to export per-stage metadata XML (length, elevation, terrain type, surface difficulty, etc.).
- Cache previously exported stage metadata — re-runs are fast because stage files almost never change.
- Store everything in a clean local SQLite database ready for the optimiser.

What is not yet built: the optimiser, the web viewer, and writeback to PCM save files.

---

## The `migrate` package

### What it does

The `migrate` package populates the local planner SQLite database from a [Lachis Editor](https://www.lachistudios.com/) XML export.

It reads:

| Source file | What is extracted |
|---|---|
| `GAM_config.xml` | Current in-game date |
| `GAM_user.xml` | Player's team ID and display name |
| `DYN_team.xml` | All teams |
| `DYN_cyclist.xml` | Riders and stats (player's team only) |
| `DYN_team_race.xml` | Races the player's team is entered in |
| `STA_race_class.xml` | Race class definitions (tier, squad sizes, stage race flag) |
| `STA_race_type.xml` | Race type terrain-weight profiles |
| `STA_race.xml` | Race names, dates, variant, class/type links |
| `STA_stage.xml` | Stage schedules (selected stages only) |
| `.cds` / `.cdx` files | Stage file resolution via CDX fallback chains |
| Stage Editor XMLs | Per-stage metadata (elevation, length, surface, terrain) |

### Prerequisites

- Python 3.10+
- A Lachis Editor XML export of your PCM career save
- The PCM base-game `CM_Stages` folder
- Your mod/workshop `Stages` folder (if applicable)
- `CTStageEditor.exe` from the PCM 2024 Tool install

### Running the migration

Edit `scripts/migrate.bat` to point at your local paths, then run it from the project root:

```bat
scripts\migrate.bat
```

Or run directly:

```bat
python -m migrate ^
  --target data\planner.sqlite ^
  --lachis-export C:\path\to\LachisEditor\Data\Career_1 ^
  --reset ^
  --import-races-and-stages ^
  --mod-stages "C:\path\to\workshop\Stages" ^
  --base-stages "C:\path\to\PCM2024\CM_Stages" ^
  --stage-editor-exe "C:\path\to\PCM2024 Tool\CTStageEditor.exe"
```

### CLI reference

```
--target PATH             Path to the planner SQLite database to create or update.
--reset                   Drop all tables and recreate from scratch. Destructive.
--lachis-export PATH      Path to the Lachis Editor XML export folder.
--import-races-and-stages Import races, stages, and Stage Editor metadata.
--mod-stages PATH         Mod/workshop Stages folder (searched before base game).
--base-stages PATH        Base-game CM_Stages folder.
--stage-editor-exe PATH   Path to CTStageEditor.exe.
--force-stage-export      Delete cached Stage Editor XMLs and re-export everything.
                          Only needed if .cds stage files have actually changed.
```

The player's team and the current in-game date are read automatically from the export — no manual configuration is required.

Stage metadata export is the slowest step (CTStageEditor must open for each batch). On subsequent runs the cached XMLs are reused, so only newly resolved stages are exported.

### Package layout

```
migrate/
  __init__.py       Package entry point and usage docs.
  schema.py         SQL DDL for all tables and indexes, plus db setup functions.
  parsing.py        XML streaming helpers, type coercion, and domain converters.
                    Also reads GAM_config.xml (game date) and GAM_user.xml (player team).
  teams.py          Team import (DYN_team.xml) and team-ID lookup utilities.
  riders.py         Rider and rider-stat import (DYN_cyclist.xml).
  stage_files.py    CDX/CDS stage file resolution, Stage Editor export, metadata parsing.
  races.py          Race class/type/entry/race/stage import. Orchestrates the full
                    race-and-stage pipeline.
  __main__.py       CLI entry point — run with python -m migrate.
```

---

## Project goals

The long-term goal is a semi-automated season planning tool that can:

- Read PCM save/export data through Lachis Editor exports.
- Import the team's riders, rider stats, entered races, race dates, and stage profiles.
- Store the imported data in a clean local planner database.
- Optimise rider-race allocations using configurable constraints and scoring rules.
- Respect manually fixed race allocations.
- Eventually support rider roles, race profiles, objectives, fitness planning, and training camps.
- Provide a readable calendar-style view of the planned season.

---

## Phase 1 scope

Phase 1 is focused on a minimal working version.

It will include:

* ~~A helper script to inspect/probe the Lachis exported database.~~ ✓ Done (`scripts/inspect_*.py`, `scripts/probe_cds_file.py`)
* ~~A Python script to initialise our own local SQLite database.~~ ✓ Done (`migrate/schema.py`)
* ~~A Python migration script to import core data from the Lachis export.~~ ✓ Done (`migrate/` package)
* A Python optimisation script to assign riders to races.
* A local SQLite database storing imported data and optimisation results.
* A Razor web app for viewing the generated plan.

The initial optimiser will answer only one question:

```text
Is rider X competing in race Y?
```

It will not yet handle rider roles, race objectives, fitness peaks, training camps, or manual UI-based edits.

## Initial optimisation rules

The first optimisation model will be intentionally basic.

Hard constraints:

* Each race must have exactly the required number of riders.
* No rider may exceed 75 race days.
* A rider cannot be assigned to overlapping races.
* Race overlaps are calculated using full race start/end dates, not individual stage dates.

Initial scoring:

* Flat stages use the rider's Flat stat.
* Hilly stages use the rider's Hill stat.
* Medium mountain stages use the rider's Medium Mountain stat.
* Mountain stages use the rider's Mountain stat.
* Time trial and cobble-specific scoring will be ignored at first.

This should be enough to verify that the optimiser is making sensible basic assignments, such as selecting strong hill riders for hilly races and balanced riders for stage races.

## Out of scope for the first version

The first version will not handle:

* adding or removing races from the calendar
* rider roles
* race objectives
* fitness peaks
* training camps or recon
* minimum race-day targets
* detailed fatigue modelling
* time trial-specific scoring
* cobbles-specific scoring
* sprint train logic
* campaign coherence
* save-file writeback
* human-readable optimisation explanations

These will be added incrementally after the basic pipeline is working.

## Development approach

This project will be built in small, testable steps.

Each step should be easy to validate before moving on:

1. ~~Inspect the source database.~~ ✓
2. ~~Create the empty local database.~~ ✓
3. ~~Import basic data.~~ ✓
4. Run a simple optimiser.
5. Save optimisation results.
6. View the plan in the web app.
7. Improve the UI.
8. Iterate on optimisation quality.

The guiding principle is to keep each step small enough that we can tell whether it worked.

