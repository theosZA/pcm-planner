# PCM Season Planner

A companion planning tool for **Pro Cycling Manager 2024** season scheduling. It reads your career save via [Lachis Editor](https://github.com/LachisSpaces/LachisEditor), imports your team's riders and race calendar, runs an optimiser to assign riders to races, and displays the result as an interactive web calendar.

The goal is to produce better race assignments than PCM's built-in scheduler.

![Team Calendar](images/team-calendar.png)

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.10+ | For the migration and optimiser |
| .NET 9 SDK | For the web app |
| [Lachis Editor](https://github.com/LachisSpaces/LachisEditor) | To export your PCM career save |
| PCM 2024 Tool (`CTStageEditor.exe`) | Included with the PCM 2024 Tool install |
| PCM base-game `CM_Stages` folder | Part of your PCM installation |
| Mod/workshop `Stages` folder | Only needed if you use mods |

---

## Getting started

### 1. Configure `config.yaml`

Open `config.yaml` at the workspace root and fill in the paths under the `migrate` section to match your local installation:

```yaml
migrate:
  lachis_export: C:\path\to\LachisEditor\Data\Career_1
  mod_stages: C:\path\to\workshop\Stages
  base_stages: C:\path\to\PCM2024\CM_Stages
  stage_editor_exe: C:\path\to\PCM2024 Tool\CTStageEditor.exe
```

The `run` section controls the optimiser:

```yaml
run:
  database: data/planner.sqlite   # path to the SQLite database
  time_limit: 30                  # solver time cap in seconds; null for no limit
```

All other config sections (`race_day_penalties`, `squad_compositions`) have sensible defaults and rarely need changing.

### 2. Verify squad compositions

Open `config.yaml` and check the `squad_compositions` section. Every `(profile, squad_size)` combination present in your race calendar needs a matching entry defining the role breakdown.

For example, a 7-rider sprint race entry looks like:

```yaml
sprint:
  7:
    sprint_lead: 1
    sprint_leadout: 2
    domestique: 3
    free: 1
```

The valid profiles are `sprint`, `climbing`, `time_trial`, and `stage_race`. If a combination is missing the optimiser will report it during its pre-solve checks.

### 3. Run the migration

Export your PCM career from Lachis Editor, then run:

```
python -m migrate
```

This reads your Lachis export, resolves stage files, invokes `CTStageEditor.exe` to export per-stage metadata, and writes everything to `data/planner.sqlite`. Stage exports are cached — subsequent runs are fast. Pass `--force-stage-export` to invalidate the cache if your `.cds` stage files have changed.

### 4. Run the optimiser

```
python -m optimise
```

The solver assigns each rider to a role in each race, maximising total terrain-and-role suitability. Results are written back to the database.

Both commands read all settings from `config.yaml` by default. Any value can be overridden on the command line — run with `--help` to see available options.

### 5. View the plan

```bat
cd pcm-planner
dotnet run
```

Open `http://localhost:5000` in your browser. The home page shows the full-team season calendar. Click any rider or race for details.

---

## The web app

The Blazor Server app at `http://localhost:5000` visualises the latest optimisation result.

**Home** — A scrollable full-team season calendar (one row per rider, day-accurate race blocks, colour-coded by race class) followed by a chronological race list.

**Race detail** — Squad profile, assigned riders with their roles, and (for stage races) a stage list showing terrain and type.

**Rider detail** — Age, full stat table, a per-rider month-by-month calendar, a role-breakdown summary, and the rider's full race list.

The sidebar lists all roster riders with their total assigned race days. The header shows season-level stats (race count, rider count, average race days per rider).

Race blocks are colour-coded using their PCM colour, e.g. Grand Tours get their brand colours (yellow/pink/orange) Hovering a block shows a tooltip with the race name, dates, and stage count.

---

## How the optimiser works

Each race is automatically classified into a **squad profile** based on its stage terrain:

| Profile | Assigned when |
|---|---|
| `time_trial` | The race is a single time trial or team time trial |
| `sprint` | Single-day classic, Flat or Hilly terrain |
| `climbing` | Single-day classic, Mountain terrain |
| `stage_race` | Any multi-stage race |

The profile and squad size determine the role breakdown (from `squad_compositions` in `config.yaml`). The solver then scores every rider–race–role triple by combining a terrain suitability score (matching rider stats to stage profiles) with a role fitness score (e.g. a `sprint_lead` role rewards Sprint and Acceleration). It maximises total score subject to these hard constraints:

- Each role slot in every race is filled the correct number of times.
- No rider fills more than one role in any given race.
- No rider is assigned to overlapping races.
- No rider is assigned more than 100 race days.
- For national championship races, only riders whose nationality matches the host country may be assigned, and all eligible riders in the squad must be sent (up to squad capacity).

And score is penalized for falling outside the 60- to 70-day target workload. The workload ranges, penalty weights, and the absolute maximum number of race days allowed are configured under `race_day_penalties` in `config.yaml`.

---

## Technical reference

### `migrate` package

Populates the planner database from a Lachis Editor XML export. Reads team, rider, race, and stage data; resolves `.cds`/`.cdx` stage files; invokes `CTStageEditor.exe` for per-stage metadata; caches results. Each run drops and recreates the database from scratch.

The player team and in-game date are detected automatically from the export.

**CLI** (all path arguments default to values from `config.yaml`):
```
--target PATH           Output SQLite database path.
--lachis-export PATH    Lachis Editor XML export folder.
--mod-stages PATH       Mod/workshop Stages folder (takes priority over base game).
--base-stages PATH      Base-game CM_Stages folder.
--stage-editor-exe PATH Path to CTStageEditor.exe.
--force-stage-export    Re-export all stage metadata (only needed if .cds files changed).
```

**Modules:** `schema.py` (DDL), `parsing.py` (XML helpers), `teams.py`, `riders.py`, `races.py`, `stage_files.py` (CDS/CDX resolution and Stage Editor invocation), `__main__.py` (CLI).

---

### `optimise` package

Loads the planner database, classifies races, builds a scoring matrix, and solves a CP-SAT assignment model via Google OR-Tools.

**CLI:**
```
--database PATH      Path to the planner SQLite database.
--time-limit SECS    Optional solver wall-clock cap. Omit for proven optimality.
```

**Role scoring formulas:**

| Role | Stat formula |
|---|---|
| `domestique` | `flat÷2 + hill÷2` |
| `free` | `baroudeur÷2 + stamina÷2` |
| `sprint_lead` | `sprint×2÷3 + acceleration÷3` |
| `sprint_leadout` | `sprint` |
| `climbing_lead` | `stamina÷2 + mountain÷6 + medium_mountain÷6 + hill÷6` |
| `climbing_domestique` | `mountain÷3 + medium_mountain÷3 + hill÷3` |
| `time_trial` | `time_trial×4÷5 + resistance÷5` |

**Modules:** `model.py` (data classes and enums), `db.py` (load/save), `scoring.py` (terrain and role scoring), `constraints.py` (pre-solve checks), `solver.py` (CP-SAT model), `config.py` (YAML config loader), `__main__.py` (CLI).

---

### `pcm-planner` web app

Blazor Server app. Reads directly from `data/planner.sqlite` via `RosterService`. No separate API layer.

**Key files:** `Data/RosterService.cs` (all DB queries), `Data/CalendarHelpers.cs` (race colouring and tooltips), `Components/Shared/TeamCalendar.razor`, `Components/Shared/RiderCalendar.razor`.

The database path is set in `appsettings.json` under `DatabasePath` (default: `..\data\planner.sqlite`).

---

## What's not yet built

- Writeback to PCM save files
- Manual race assignment overrides
- Season objectives, fitness peaks and recovery time
- Stage race overall optimization; right now it's just scored per stage

