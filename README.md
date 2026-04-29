# PCM Season Planner

A companion planning tool for **Pro Cycling Manager 2024** season scheduling.

The goal of this project is to help create better team race calendars than PCM's built-in automated planner, while still preserving the fun strategic decisions: choosing Grand Tour squads, assigning key riders to major objectives, and shaping the season around the team's strengths.

The project will start small: import riders and fixed race entries from a Lachis Editor exported database, run a basic optimisation to assign riders to races, save the generated plan into a local SQLite database, and view the results in a simple web app.

## Project goals

The long-term goal is a semi-automated season planning tool that can:

- Read PCM save/export data through Lachis Editor exports.
- Import the team's riders, rider stats, entered races, race dates, and stage profiles.
- Store the imported data in a clean local planner database.
- Optimise rider-race allocations using configurable constraints and scoring rules.
- Respect manually fixed race allocations.
- Eventually support rider roles, race profiles, objectives, fitness planning, and training camps.
- Provide a readable calendar-style view of the planned season.

The first version will be deliberately simple. It will focus on proving the end-to-end pipeline:

Lachis export → local SQLite planner DB → optimiser → saved assignments → web viewer

## Phase 1 scope

Phase 1 is focused on a minimal working version.

It will include:

* A helper script to inspect/probe the Lachis exported database.
* A Python script to initialise our own local SQLite database.
* A Python migration script to import core data from the Lachis export.
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

## Planned project structure

```text
pcm-season-planner/
  README.md
  .gitignore

  docs/
    phase-1-plan.md

  scripts/
    inspect_lachis_db.py
    init_planner_db.py
    import_lachis_to_planner_db.py
    optimise_assignments.py

  src/
    planner/

  web/
    PlannerWeb/

  data/
    .gitkeep
```

## Main components

### Lachis database inspection

The first helper script will inspect the Lachis Editor exported database and list available tables and columns.

This allows us to identify where PCM stores:

* riders
* teams
* rider stats
* races
* stages
* race dates
* race abbreviations
* race categories/levels
* team race entries
* stage profile types
* stage distances

### Local planner database

The project will use its own SQLite database rather than working directly against the Lachis export.

This keeps the planner model clean and gives us a stable structure to build on even if PCM/Lachis table names differ between versions or databases.

Initial tables will include:

* `rider`
* `rider_stat`
* `race`
* `stage`

Later tables will store generated plans and rider-race assignments.

### Data migration scripts

Python scripts will migrate selected data from the Lachis export into the local planner database.

Initially this will include:

* riders on our team
* current rider stats
* races entered by our team
* race level/category
* race dates
* rider capacity per race
* race abbreviation, where available
* stage type and distance

One-day races will be treated as races with one stage.

### Optimisation script

The optimisation script will read from the local SQLite database, build a simple assignment model, solve it, and eventually save the generated plan back into the database.

The first version will optimise only rider-race assignment. Later versions will add:

* existing PCM allocations as fixed assignments
* race value coefficients
* rider roles
* race profiles
* role-based scoring
* race-day target penalties
* more detailed scoring formulas

### Razor web app

A Razor web app will provide a read-only view of the generated plan.

The first views will show:

* all riders and their allocated race days
* rider detail pages
* race detail pages
* assigned riders per race
* stage breakdowns

Later, the web app will include a calendar/grid view showing race blocks across the season, using colours broadly consistent with PCM's race level colours.

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

1. Inspect the source database.
2. Create the empty local database.
3. Import basic data.
4. Run a simple optimiser.
5. Save optimisation results.
6. View the plan in the web app.
7. Improve the UI.
8. Iterate on optimisation quality.

The guiding principle is to keep each step small enough that we can tell whether it worked.
