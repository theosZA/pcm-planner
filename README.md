# PCM Season Planner

A companion planning tool for **Pro Cycling Manager 2024** season scheduling.

The goal of this project is to help create better team race calendars than PCM's built-in automated planner, while still preserving the fun strategic decisions: choosing Grand Tour squads, assigning key riders to major objectives, and shaping the season around the team's strengths.

---

## Current status

The data import pipeline and the initial optimiser are complete.

The `migrate` package can:

- Read the active in-game date and player team automatically from the Lachis export (no manual configuration needed).
- Create the local planner SQLite database schema from scratch, or reset and rebuild it.
- Import all teams, and import riders and rider stats for the player's team.
- Calculate exact rider ages as of the in-game date.
- Import all races the player's team is entered in, along with their race class, race type, and stage schedules.
- Resolve stage variant names to real `.cds` files (following CDX redirect chains across mod and base-game Stages folders).
- Invoke `CTStageEditor.exe` to export per-stage metadata XML (length, elevation, terrain type, surface difficulty, etc.).
- Cache previously exported stage metadata — re-runs are fast because stage files almost never change.
- Store everything in a clean local SQLite database ready for the optimiser.

The `optimise` package can:

- Load riders, races, and stage terrain data from the planner database.
- Classify each race into a **squad profile** (sprint, climbing, time trial, or stage race) based on its stage terrain data.
- Resolve the **squad composition** for each race from a config file that maps (profile, squad size) → role breakdown.
- Pre-calculate a terrain-and-role-suitability score for every rider × race × role triple.
- Solve a CP-SAT optimisation model (Google OR-Tools) that assigns each rider to a specific role in each race, maximising total score subject to hard constraints.
- Save every solve result — status, objective, the full rider–race–role assignment, and per-race squad profile metadata — to the database.
- Print a season summary, validation checks, squad compositions, and a per-rider race-days summary to the console.

The `pcm-planner` Blazor Server web app can:

- Show a full-team calendar on the home page: a scrollable grid with one row per rider, day-accurate race blocks across the whole season, month headers, and alternating row shading.
- Show a per-rider calendar on each rider page: a month-by-month horizontal bar view with the rider's races highlighted against the full season span, with weekend shading.
- Colour-code race blocks by race class (Grand Tour yellow/pink/orange, Monument by base-game colour, etc.) with automatic light/dark text contrast.
- Show a tooltip on every race block with the race level, name, dates, and stage count.
- Display all races from the latest optimisation run in a chronological table, with links to race detail pages.
- Show a race detail page listing the assigned riders and, for multi-stage races, each stage's terrain and type (ITT/TTT).
- Show a rider detail page with age, full stat table, a per-rider calendar, and the assigned race list.
- List every roster rider in the sidebar navigation with their total assigned race days.
- Show a season summary header (season year, race count, rider count, average race days per rider).
- Read everything directly from the planner SQLite database via `RosterService` (no separate API layer).

What is not yet built: writeback to PCM save files.

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

## The `optimise` package

### What it does

The `optimise` package reads the planner database and assigns riders to races using a CP-SAT integer programming model (Google OR-Tools).

### Squad profiles and role-based scoring

Before solving, every race is classified into one of four **squad profiles**:

| Profile | When assigned |
|---|---|
| `time_trial` | The race has a time trial or team time trial stage |
| `sprint` | Single-day classic with Flat or Hill terrain |
| `climbing` | Single-day classic with Medium Mountain or Mountain terrain |
| `stage_race` | Any multi-stage race |

The profile and the race's squad size together determine the **squad composition**: how many riders fill each role. Compositions are configured in `optimise/squad_config.py`:

```python
# Keys:   (SquadProfile, rider_capacity)
# Values: {RiderRole: count}  — must sum to rider_capacity
SQUAD_COMPOSITIONS: dict[tuple[SquadProfile, int], dict[RiderRole, int]] = {
    (SquadProfile.SPRINT, 7): {
        RiderRole.SPRINT_LEAD:    1,
        RiderRole.SPRINT_LEADOUT: 2,
        RiderRole.DOMESTIQUE:     3,
        RiderRole.FREE:           1,
    },
    # ... add entries for every (profile, size) combination in your calendar
}
```

Scoring is now per (rider, race, role) triple. Each stage contributes a **terrain stat** (as before) plus a **role-fitness stat** that rewards the right kind of rider for each role:

| Role | Stat formula |
|---|---|
| `domestique` | `flat÷2 + hill÷2` |
| `free` | `baroudeur÷2 + stamina÷2` |
| `sprint_lead` | `sprint×2÷3 + acceleration÷3` |
| `sprint_leadout` | `sprint` |
| `climbing_lead` | `stamina÷2 + mountain÷6 + medium_mountain÷6 + hill÷6` |
| `climbing_domestique` | `mountain÷3 + medium_mountain÷3 + hill÷3` |
| `time_trial` | `time_trial×4÷5 + resistance÷5` |

The solver assigns each rider to **exactly one role** per race they attend, subject to role-capacity limits from the squad composition.

Hard constraints currently enforced:

| Constraint | Detail |
|---|---|
| Role capacity | Each role slot in a race is filled at most as many times as the composition allows |
| One role per rider per race | A rider may fill at most one role in any given race |
| Season cap | No rider may exceed 75 race days |
| No overlap | A rider cannot be assigned to two races whose date ranges intersect |

National championship races are excluded from optimisation (they are heavily overlapping single-day events that the scheduler handles separately).

Each solve result is written to the database (`optimise_run`, `optimise_race`, and `optimise_assignment` tables). `optimise_race` stores the squad profile and stage-value multiplier for each race. `optimise_assignment` stores the assigned rider, race, and role so results are fully queryable.

### Prerequisites

- Python 3.10+
- OR-Tools: `pip install ortools` (or install via the venv — already done if you used `scripts\optimise.bat`)
- A populated planner database (run `scripts\migrate.bat` first)

### Running the optimiser

```bat
scripts\optimise.bat
```

Or run directly:

```bat
.venv\Scripts\python.exe -m optimise --database data\planner.sqlite
```

Add `--time-limit 30` to cap the solver at 30 seconds and get a fast feasible result. Without a limit the solver runs until it proves optimality (may take several minutes for large calendars).

### CLI reference

```
--database PATH      Path to the planner SQLite database.
--time-limit SECS    Optional solver wall-clock cap in seconds. Omit for no limit.
```

### Package layout

```
optimise/
  __init__.py       Package marker.
  model.py          Data classes: Rider, Race, Stage, PlannerData.
                    Enums: RaceClass, SquadProfile, RiderRole.
  db.py             DB access: load_planner_data() + save_result() (writes run, race, and assignment rows).
  scoring.py        Terrain → stat mapping; role-fitness formulas; build_scoring_matrix() returns
                    dict[(rider_id, race_id, RiderRole), int]; classify_squad_profile(); build_race_profiles().
  squad_config.py   SQUAD_COMPOSITIONS config: maps (SquadProfile, squad_size) → {RiderRole: count}.
  constraints.py    Pre-solve feasibility checks (rider count, race data, aggregate days, squad compositions).
  solver.py         CP-SAT model: (rider, race, role) variables, objective, constraints, solve().
  __main__.py       CLI entry point — run with python -m optimise.
```

---

## The `pcm-planner` web app

A Blazor Server application that visualises the latest optimisation result from the planner database.

### Pages

| Page | Route | Description |
|---|---|---|
| Home | `/` | Full-team calendar grid followed by a chronological race list. |
| Race detail | `/race/{id}` | Squad profile, stage value, assigned riders with their roles, and (for multi-stage races) a stage list showing terrain and type (ITT/TTT). |
| Rider detail | `/rider/{id}` | Rider age, full stat table, per-rider calendar, a role-breakdown summary table (role → total days), and the full assigned race list with role per race. |

The sidebar navigation lists every roster rider with their total assigned race days. A header bar shows the season year, race count, rider count, and average race days per rider.

Rider roles are displayed throughout the app. On the race detail page each assigned rider is shown with their role in parentheses. On the rider detail page a role-breakdown table summarises total days per role across the season, and the race list includes a Role column. Role strings are formatted from snake_case to title case by `RosterHelpers.FormatRole`.

### Calendars

The **team calendar** (`TeamCalendar`) is a CSS-grid layout spanning from 1 January to the end of the last race month. Each row is a rider; each column is one day. Month headers alternate between two background tints. Rider names are in a sticky-ish left panel; the day grid scrolls horizontally on narrow viewports.

The **rider calendar** (`RiderCalendar`) breaks the season into one row per month, with day-of-month labels and weekend column shading. Only months that contain at least one team race are shown, so the view is never padded with empty months.

Both calendars share the same race-block styling and colouring logic (`CalendarHelpers`): race class drives the background colour (Grand Tours get fixed brand colours; other races use their PCM `calendar_color` value), and perceived brightness determines whether the label text is dark or white. Hovering a block shows a tooltip with race level, name, date range, and stage count.

### Prerequisites

- .NET 9 SDK
- A populated `data/planner.sqlite` database (produced by `migrate` and `optimise`)

### Running the web app

```bat
cd pcm-planner
dotnet run
```

The app defaults to `http://localhost:5000`. The database path is configured in `appsettings.json` under `DatabasePath` (default: `..\data\planner.sqlite`).

### Project layout

```
pcm-planner/
  Program.cs                   Application entry point and DI registration.
  Data/
    RosterService.cs           All DB queries; returns typed records to Razor components.
                               Key records: RaceDetail (includes StageValue, SquadProfile, List<RaceRider> with Role),
                               RiderAssignedRace (includes Role), RiderCalendarEntry.
    RosterHelpers.cs           FormatRole(): converts snake_case role strings to Title Case.
    CalendarHelpers.cs         Shared calendar utilities: race colouring, tooltips, labels.
  Components/
    Layout/
      MainLayout.razor         Shell layout with sidebar and header.
      NavMenu.razor            Sidebar — rider list with race day counts.
      SeasonSummary.razor      Header bar — season stats summary.
    Pages/
      Home.razor               Team calendar + race list (route: /).
      Race.razor               Race detail: squad profile, stage value, riders with roles,
                               and stage list (route: /race/{id}).
      Rider.razor              Rider detail: stat table, calendar, role-breakdown summary,
                               and race list with role column (route: /rider/{id}).
    Shared/
      TeamCalendar.razor       Full-team season calendar grid (one row per rider).
      RiderCalendar.razor      Per-rider month-by-month bar calendar.
```

---


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
* ~~A Python optimisation script to assign riders to races.~~ ✓ Done (`optimise/` package)
* ~~A local SQLite database storing imported data and optimisation results.~~ ✓ Done
* ~~A Razor web app for viewing the generated plan.~~ ✓ Done (`pcm-planner/` Blazor Server app)

The initial optimiser will answer only one question:

```text
Which role does rider X fill in race Y?
```

It will not yet handle race objectives, fitness peaks, training camps, or manual UI-based edits.

## Initial optimisation rules

The first optimisation model will be intentionally basic.

Hard constraints:

* Each race must have the right number of riders filling each role (per the squad composition).
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
4. ~~Run a simple optimiser.~~ ✓
5. ~~Save optimisation results.~~ ✓
6. ~~View the plan in the web app.~~ ✓
7. ~~Improve the UI.~~ ✓
8. Iterate on optimisation quality.

The guiding principle is to keep each step small enough that we can tell whether it worked.

