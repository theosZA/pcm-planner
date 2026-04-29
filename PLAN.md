# PCM Season Planner — Phase 1 Implementation Plan

## Guiding principle

Phase 1 should create the smallest end-to-end system that can:

1. Inspect the Lachis Editor exported database so we understand its available tables and columns.
2. Import a fixed team calendar and riders from that Lachis export.
3. Store the imported data in our own SQLite schema.
4. Run a very simple global race-assignment optimisation.
5. Save the generated assignments back into our own SQLite database.
6. Display the result in a basic web UI.

The point of Phase 1 is not to produce a tactically sophisticated planner. The point is to create a validated pipeline that we can improve incrementally:

```text
Lachis export → local planner DB → optimiser → saved plan → readable UI
```

---

# Phase 1: Minimal End-to-End Planner

## Step 0 — Create repository and planning document

### Goal

Create the project shell and capture the implementation plan in version control.

### Tasks

* Create a GitHub repository.
* Clone it locally.
* Add a minimal `README.md`.
* Add this plan as a markdown document, for example:

  * `docs/phase-1-plan.md`
* Add a basic `.gitignore` for Python, SQLite databases, virtual environments, and local exports.

### Suggested initial structure

```text
pcm-season-planner/
  README.md
  .gitignore
  docs/
    phase-1-plan.md
  scripts/
  src/
  data/
    .gitkeep
```

### Validation

* Repository exists on GitHub.
* Local clone works.
* `README.md` and `docs/phase-1-plan.md` are committed.
* `data/` exists but does not commit local SQLite databases or Lachis exports.

### Definition of done

A clean repo exists and contains only project scaffolding and the Phase 1 plan.

---

## Step 1 — Inspect/probe the Lachis exported database

### Goal

Before creating our own SQLite schema, inspect the Lachis Editor exported database so we can see what source tables and columns are actually available.

This should happen before we finalise our own local schema. The goal is not to fully understand every PCM table yet, but to confirm enough structure to make sensible choices for the first local database tables.

### Script

```text
scripts/inspect_lachis_db.py
```

### Example command

```bash
python scripts/inspect_lachis_db.py --source path/to/lachis_export.sqlite
```

### Output

For each table:

```text
TABLE_NAME
  column_1
  column_2
  column_3
  ...
```

Optionally also output a few sample rows for likely tables.

### Things we are looking for

Likely source tables/columns for:

* riders
* teams
* current rider stats
* races
* race levels/categories
* race abbreviations
* stages
* team race entries
* race dates
* stage dates
* number of riders per team
* stage profile/parcours type
* stage distance

### Specific notes

* Races should already have an abbreviation somewhere in the source database. If available, we should import and use it for the UI.
* PCM 24 has a `medium mountain` rider stat. We should expect to import this as a real stat rather than deriving it from hill/mountain.
* Some older or imported parcours may not use a medium-mountain stage classification even if PCM 24 supports the medium-mountain rider stat. These older routes may classify such stages as either hill or mountain.
* In the long run, we may want our own parcours analysis rather than relying entirely on the assigned descriptor, especially because hilly races can range from versatile-sprinter-friendly to steep puncheur finishes to attritional short-climb races. This is out of scope for Phase 1, but we should keep the schema flexible enough to improve later.

### Validation

* We can run the script against the Lachis export.
* We can identify enough source tables to write the first mapped migration.
* We can confirm where rider stats, races, stages, race abbreviations, and team race entries likely live.

### Definition of done

We have enough source-table knowledge to create our first local planner schema and a basic mapping from Lachis/PCM columns to our local tables.

---

## Step 2 — Create empty local SQLite schema

### Goal

Create a Python script that initialises our own local SQLite database with basic planner tables, but no imported data yet.

### Script

```text
scripts/init_planner_db.py
```

### Input

None, except an output database path.

Example:

```bash
python scripts/init_planner_db.py --db data/planner.sqlite
```

### Initial tables

Use intentionally simple tables:

* `rider`
* `rider_stat`
* `race`
* `stage`

### Suggested schema

```sql
CREATE TABLE rider (
    id INTEGER PRIMARY KEY,
    source_rider_id INTEGER UNIQUE,
    first_name TEXT,
    last_name TEXT,
    display_name TEXT NOT NULL,
    age INTEGER,
    team_name TEXT
);

CREATE TABLE rider_stat (
    rider_id INTEGER PRIMARY KEY,
    flat INTEGER,
    hill INTEGER,
    medium_mountain INTEGER,
    mountain INTEGER,
    time_trial INTEGER,
    cobble INTEGER,
    sprint INTEGER,
    acceleration INTEGER,
    stamina INTEGER,
    resistance INTEGER,
    recovery INTEGER,
    FOREIGN KEY (rider_id) REFERENCES rider(id)
);

CREATE TABLE race (
    id INTEGER PRIMARY KEY,
    source_race_id INTEGER UNIQUE,
    name TEXT NOT NULL,
    abbreviation TEXT,
    level TEXT,
    start_date TEXT,
    end_date TEXT,
    rider_capacity INTEGER NOT NULL
);

CREATE TABLE stage (
    id INTEGER PRIMARY KEY,
    race_id INTEGER NOT NULL,
    source_stage_id INTEGER,
    stage_number INTEGER NOT NULL,
    stage_date TEXT,
    stage_type TEXT NOT NULL,
    distance_km REAL,
    FOREIGN KEY (race_id) REFERENCES race(id)
);
```

### Notes

* Treat one-day races as races with exactly one stage.
* Store `medium_mountain` as a first-class rider stat because PCM 24 includes it.
* Store stage type as the source-provided descriptor for now, even though we expect to improve parcours interpretation later.
* Dates should be stored as ISO text: `YYYY-MM-DD`.
* `level` can be a string for now: `grand_tour`, `world_tour`, `pro`, `1`, `2`, etc.
* `abbreviation` should be imported if available from the source database, because it will be useful for the calendar UI.

### Validation

Open `data/planner.sqlite` in an external SQLite viewer and confirm:

* Tables exist.
* Columns look correct.
* There is no data yet.

### Definition of done

Running the script creates a valid empty SQLite database with the base schema.

---

## Step 3 — Import from Lachis Editor exported DB

### Goal

Create a migration script that reads the Lachis Editor exported database and migrates only the basic data needed for the first optimiser.

### Script

```text
scripts/import_lachis_to_planner_db.py
```

### Example command

```bash
python scripts/import_lachis_to_planner_db.py \
  --source path/to/lachis_export.sqlite \
  --target data/planner.sqlite \
  --team "Your Team Name"
```

### Data to migrate

#### Riders

Only riders on our team.

Fields:

* source rider ID
* first name
* last name
* display name
* age
* team name

#### Rider stats

For now:

* flat
* hill
* medium mountain
* mountain
* time trial
* cobble
* sprint
* acceleration
* stamina
* resistance
* recovery

Medium mountain should be imported directly from the PCM 24 stat if the column is available.

#### Races

Only races currently assigned/entered by our team.

Fields:

* source race ID
* race name
* race abbreviation, if available
* race level/category
* start date
* end date
* number of riders per team

#### Stages

Every stage belonging to an imported race.

Fields:

* source stage ID
* stage number
* stage date
* stage type
* length in km

Stage types for Phase 1:

```text
flat
hill
medium_mountain
mountain
time_trial
cobble
unknown
```

One-day races should be imported as races with one stage.

### Validation

Open the populated SQLite database in an external viewer and check:

* Riders exist and are only from our team.
* Rider stats look plausible, including medium mountain.
* Only team-entered races were imported.
* Race abbreviations are imported where available.
* Stage counts make sense.
* One-day races have one stage.
* Grand Tours have the expected number of stages.
* Race dates and stage dates look plausible.
* Rider capacity is populated for each race.

### Definition of done

The planner database contains enough rider, race, and stage data to run a first optimisation.

---

## Step 4 — Create first optimisation script

### Goal

Create a separate Python optimisation script that assigns riders to races using a minimal global scoring model.

### Script

```text
scripts/optimise_assignments.py
```

### Example command

```bash
python scripts/optimise_assignments.py --db data/planner.sqlite
```

### Optimisation question

For each rider and race:

```text
Is rider X competing in race Y?
```

Decision variable:

```text
x[rider, race] ∈ {0, 1}
```

No roles yet.

### Hard constraints

#### Race capacity

Each race must have exactly the required number of riders.

```text
For each race Y:
  sum over riders X of x[X, Y] = capacity[Y]
```

#### Maximum rider race days

No rider may exceed 75 race days.

```text
For each rider X:
  sum over races Y of x[X, Y] × race_days[Y] <= 75
```

No minimum race-day constraint yet.

#### No overlapping race assignments

A rider cannot be assigned to more than one race on the same day.

For Phase 1, this should be based on the full race date interval, not individual stage dates:

```text
race interval = race start date through race end date, inclusive
```

This matters because stage races include rest days. A rider cannot ride another race just because there is a rest day during the Tour de France, Giro, Vuelta, or another stage race.

So for every pair of races whose date intervals overlap:

```text
For each rider X and overlapping races A/B:
  x[X, A] + x[X, B] <= 1
```

Implementation note:

* We only need to add overlap constraints for pairs of races whose date intervals actually overlap.
* Use `race.start_date` and `race.end_date`, not the dates of individual stages.
* Treat both endpoints as inclusive.

Date overlap test:

```text
race_a.start_date <= race_b.end_date
AND
race_b.start_date <= race_a.end_date
```

This may be the most complicated logic inside the minimal optimiser, but it should be included early so that the calendar view never has to handle impossible double-booked riders.

### Feasibility checks

Before running the optimiser, print basic feasibility diagnostics:

```text
Total required race-days = sum over races of capacity × race days
Maximum available race-days = number_of_riders × 75
```

If required race-days exceeds available race-days, the model is infeasible before optimisation even begins.

Also print overlap pressure diagnostics:

```text
Number of overlapping race pairs
Largest same-window rider demand, if easy to calculate
```

The second diagnostic can be added later if it is not trivial at first.

### Scoring function

For each rider on each stage:

```text
flat stage           → rider flat stat
hilly stage          → rider hill stat
medium mountain      → rider medium mountain stat
mountain stage       → rider mountain stat
```

Ignore time trial and cobble intricacies for now.

Initial options:

* Either give TT/cobble/unknown stages a score of `0`.
* Or map them to a simple fallback, for example:

  * `time_trial` → `flat`
  * `cobble` → `flat`
  * `unknown` → `flat`

For the strictest Phase 1 implementation, use only the four requested types and score the others as `0`.

### Race-rider score

Precompute:

```text
score[rider, race] = sum of rider's matching stat for each stage in race
```

Example:

```text
Race has:
  3 flat stages
  2 hilly stages
  1 mountain stage

Rider has:
  flat = 74
  hill = 77
  mountain = 70

score = 3×74 + 2×77 + 1×70
```

### Overall objective

Maximise:

```text
sum over riders and races of x[rider, race] × score[rider, race]
```

### Expected behaviour

Even this simple optimiser should show some sensible patterns:

* Hilly one-day races should favour riders with high hill stats.
* Mountain races should favour riders with high mountain stats.
* Medium-mountain stages should favour riders with high medium-mountain stats.
* Grand Tours should favour balanced riders because they contain many stage types.
* Riders with only one strong stat may be used more selectively.
* Riders should never be double-booked across overlapping race intervals.

### Diagnostic console output

For each rider:

```text
Rider name — total race days
  Race 1
  Race 2
  Race 3
```

Also print:

```text
Optimisation status
Objective score
Number of riders
Number of races
Number of overlapping race pairs
Total assigned race-days
Solve time
```

### Validation

* Script runs against the populated SQLite database.
* Every race has exactly the required number of riders.
* No rider exceeds 75 race days.
* No rider is assigned to overlapping races.
* Output looks plausibly optimised.
* Hilly/medium-mountain/mountain races appear to select appropriate riders.
* Grand Tours appear to select riders with broad stat strength.

### Definition of done

The optimiser produces a valid assignment plan in memory and prints enough diagnostics to confirm it is doing meaningful work.

---

## Step 5 — Save optimisation results to SQLite

### Goal

Update the optimiser so it writes the generated plan back into the local SQLite database.

### Schema extension

Add:

```sql
CREATE TABLE plan (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    objective_score INTEGER,
    solve_status TEXT,
    solve_seconds REAL
);

CREATE TABLE race_assignment (
    plan_id INTEGER NOT NULL,
    rider_id INTEGER NOT NULL,
    race_id INTEGER NOT NULL,
    rider_race_score INTEGER,
    PRIMARY KEY (plan_id, rider_id, race_id),
    FOREIGN KEY (plan_id) REFERENCES plan(id),
    FOREIGN KEY (rider_id) REFERENCES rider(id),
    FOREIGN KEY (race_id) REFERENCES race(id)
);
```

Optional but useful:

```sql
CREATE TABLE rider_plan_summary (
    plan_id INTEGER NOT NULL,
    rider_id INTEGER NOT NULL,
    race_days INTEGER NOT NULL,
    assigned_races INTEGER NOT NULL,
    total_score INTEGER NOT NULL,
    PRIMARY KEY (plan_id, rider_id),
    FOREIGN KEY (plan_id) REFERENCES plan(id),
    FOREIGN KEY (rider_id) REFERENCES rider(id)
);

CREATE TABLE race_plan_summary (
    plan_id INTEGER NOT NULL,
    race_id INTEGER NOT NULL,
    assigned_riders INTEGER NOT NULL,
    total_score INTEGER NOT NULL,
    PRIMARY KEY (plan_id, race_id),
    FOREIGN KEY (plan_id) REFERENCES plan(id),
    FOREIGN KEY (race_id) REFERENCES race(id)
);
```

### Script behaviour

The optimiser should:

1. Load riders, races, stages, and stats.
2. Build and solve the model.
3. Create a new `plan` row.
4. Insert selected assignments into `race_assignment`.
5. Insert summary rows if using summary tables.
6. Print only high-level diagnostics.

### Reduced console output

Keep:

```text
Optimisation status
Plan ID
Objective score
Solve time
Number of assignments
Total assigned race-days
```

Remove the full rider-by-rider assignment dump once database persistence is validated.

### Validation

Using an external SQLite viewer:

* A `plan` row exists.
* `race_assignment` contains assignments.
* Each race has exactly `rider_capacity` assignments.
* No rider exceeds 75 race days.
* No rider is assigned to overlapping race intervals.
* Assignment scores are stored.

### Definition of done

Optimisation results are persisted in SQLite and can be inspected without relying on console output.

---

## Step 6 — Create first visualization layer

### Goal

Create a basic web app that reads the SQLite database and shows a first useful view.

### Technology decision

Razor is a reasonable option if we want a .NET web app. Python alternatives would include Flask/FastAPI, but Razor has advantages if we prefer a strongly typed web layer and easy future UI structure.

For Phase 1, the web app should be read-only.

### Suggested app name

```text
web/PlannerWeb/
```

### First view

A single page:

```text
Riders
```

Columns:

* Rider name
* Age
* Total allocated race days
* Number of assigned races
* Total assignment score

### Data source

Read from the SQLite planner database.

For now, either:

* configure the SQLite path in app settings, or
* pass it as an environment variable.

### Validation

* Web app starts locally.
* It connects to `data/planner.sqlite`.
* It displays every rider.
* Race-day totals match the database.

### Definition of done

A read-only web page displays riders and their allocated race days from the latest optimisation plan.

---

## Step 7 — Add rider and race detail views

### Goal

Make the web app navigable enough to inspect the generated plan.

### Rider list enhancement

Clicking a rider opens:

```text
/riders/{id}
```

### Rider detail page

Show:

* Rider name
* Age
* Stats
* Total race days
* Assigned races

Assigned race columns:

* Race name
* Race abbreviation
* Level
* Start date
* End date
* Race days
* Assignment score

Each race name links to the race detail page.

### Race list or race links

Either add a race list page now, or rely on links from rider pages.

Race detail route:

```text
/races/{id}
```

### Race detail page

Show:

* Race name
* Race abbreviation
* Level
* Start date
* End date
* Rider capacity
* Stage-by-stage breakdown
* Assigned riders

Stage breakdown columns:

* Stage number
* Date
* Type
* Distance km

Assigned rider columns:

* Rider name
* Relevant stats
* Rider-race score
* Total race days in plan

### Validation

* Clicking a rider opens a correct rider page.
* Clicking a race opens a correct race page.
* Race page assignment counts match capacity.
* Stage breakdown matches imported data.

### Definition of done

The web app allows basic inspection from rider → races and race → riders.

---

## Step 8 — Calendar/grid visualization

### Goal

Improve the web app so the generated plan is visually readable as a racing calendar.

### Rider calendar grid

Create a calendar-like view with:

* riders as rows
* days/weeks/months as columns
* coloured blocks for assigned races

A stage race should appear as one continuous block spanning its start date through end date.

### Race block content

Block text:

```text
race abbreviation
```

Example:

```text
PN
Giro
TdF
PR
```

Use the imported abbreviation if available. If not, derive a fallback abbreviation from the race name.

### Race block colour

Colour should eventually match PCM's own calendar colours.

Initial remembered mapping:

```text
Giro d'Italia       → pink
Tour de France      → yellow
Vuelta a España     → red
World Tour races    → greyish purple
Pro races           → dark green
.1 and .2 races     → light green
unknown             → neutral grey
```

The exact RGB values can be taken later from colour picker samples on PCM screenshots.

For Phase 1, define these colour values in one central place so they can be easily adjusted later.

### Hover behaviour

Hovering over a block shows:

* full race name
* dates
* level
* assignment score

### Click behaviour

Clicking a block opens:

```text
/races/{id}
```

### Validation

* Race blocks appear on the correct dates.
* Stage races span from race start date to race end date.
* One-day races occupy one day.
* Colours match the configured race level mapping.
* Hover shows the correct full race name.
* Clicking a race block opens the race page.
* No rider should have overlapping blocks, because the optimiser should already prevent overlapping race assignments.

### Definition of done

The web app has a useful visual calendar/grid showing rider allocations across the season.

---

# Phase 1 Completion Criteria

Phase 1 is complete when:

1. The repo exists and contains the implementation plan.
2. We can inspect/probe the Lachis exported database before creating our own schema.
3. We can create an empty planner SQLite database.
4. We can import basic rider/race/stage data from a Lachis export.
5. We can run a minimal global optimiser.
6. The optimiser obeys:

   * exact race capacity
   * no rider over 75 race days
   * no overlapping race assignments per rider, using full race start/end intervals
7. The optimiser scores assignments using simple stage/stat matching.
8. Assignments are saved to the planner database.
9. A web app can display:

   * riders and allocated race days
   * rider detail pages
   * race detail pages
   * a basic calendar/grid view

---

# Explicitly out of scope for Phase 1

Do not add these yet:

* adding/removing races from the calendar
* rider roles
* manual locks or overrides
* race objectives
* fitness peaks
* training camps/recon
* minimum race-day constraints
* fatigue modelling beyond max race days
* sprint/leadout logic
* cobbles-specific scoring
* time-trial-specific scoring
* custom parcours analysis beyond imported stage descriptors
* save-file writeback
* human-readable assignment explanations
* multi-plan comparison
* campaign templates

---

# Phase 2: Provisional Optimisation Roadmap

Phase 2 is provisional and should be adjusted based on what we learn during Phase 1. The purpose of this roadmap is to show the intended progression from the trivial Phase 1 optimiser toward a more cycling-aware race planner.

The main Phase 2 direction is:

```text
fixed race allocation → fixed user/PCM assignments → race value → race profiles → rider roles → weighted role scoring → soft race-day targets → role/stage scoring formulas
```

Phase 2 should remain incremental. Each step should produce a visible, testable change before moving on.

---

## Phase 2 Step 1 — Import existing rider-race allocations

### Goal

Import any rider-race allocations already made inside PCM and treat those allocations as fixed constraints inside the optimiser.

This allows us to do initial high-level planning manually in PCM, then let the optimiser fill the remaining gaps while respecting those choices.

### Migration update

Extend the Lachis import script to read existing rider-race assignments from the exported database.

Fields to import:

* rider
* race
* assignment source, for example `pcm_existing`
* optional role, if PCM exposes one later, though we do not rely on this yet

### Local schema addition

```sql
CREATE TABLE fixed_race_assignment (
    rider_id INTEGER NOT NULL,
    race_id INTEGER NOT NULL,
    source TEXT NOT NULL,
    PRIMARY KEY (rider_id, race_id),
    FOREIGN KEY (rider_id) REFERENCES rider(id),
    FOREIGN KEY (race_id) REFERENCES race(id)
);
```

### Optimiser update

For each fixed imported allocation:

```text
x[rider, race] = 1
```

The optimiser must then fill the remaining slots around those fixed assignments.

### Validation

* Existing PCM allocations are visible in the local planner DB.
* The optimiser always preserves those assignments.
* If a fixed assignment makes the problem infeasible, the optimiser reports infeasibility clearly.
* Race capacity constraints still hold.
* Overlap constraints still hold.

### Definition of done

We can manually allocate selected riders in PCM, import the allocations, run the optimiser, and see that those allocations are respected.

---

## Phase 2 Step 2 — Add race value coefficients

### Goal

Include the importance/value of a race in the optimisation scoring.

The Phase 1 optimiser treats all stages equally. Phase 2 should begin distinguishing between a Tour de France stage, a monument, a WorldTour stage race, a Pro race, and a lower-tier race.

### Config file

Create or extend a scoring config file, for example:

```text
config/scoring.yaml
```

Example values:

```yaml
race_value:
  monument: 100
  grand_tour_stage: 50
  grand_tour: 50
  world_tour: 30
  pro: 15
  class_1: 8
  class_2: 5
  unknown: 10
```

Exact numbers are expected to change after testing.

### Scoring update

Instead of:

```text
stage_score = matching rider stat
```

use:

```text
stage_score = matching rider stat × race_value_coefficient
```

or, equivalently:

```text
rider_race_score = base_rider_race_score × race_value_coefficient
```

### Validation

* High-value races attract stronger riders.
* Low-value races still get filled, but not at the expense of major objectives.
* Monuments and Grand Tour stages should become visibly more competitive in assignment quality.

### Definition of done

Race importance is read from config and materially affects optimisation output.

---

## Phase 2 Step 3 — Add race profiles and rider roles

This is the big Phase 2 optimiser upgrade. It should be split into several small substeps.

---

## Phase 2 Step 3A — Assign a race profile to each race

### Goal

Classify each race into a simple race profile based on parcours and race type.

The profile represents the kind of squad we need to bring if we are trying to win or perform well.

For a one-day race, the profile describes the likely race-winning rider type.

For a stage race, the profile describes the squad shape needed to compete for GC, with stage wins and secondary jerseys as secondary considerations.

### Important simplification

At this stage, still ignore detailed Time Trial and Cobbles handling.

We can import those stage flags and keep them in the DB, but the first role-aware optimiser will not yet model them properly.

### One-day race profiles

Initial profiles:

```text
Sprint
Rolling
Climbing
```

Suggested mapping:

```text
flat stage                         → Sprint
hill stage                         → Rolling
medium_mountain or mountain stage  → Climbing
```

### Stage race profiles

Initial profiles:

```text
Flat
Mostly Flat with Hilly Decider
Mostly Hilly
Mostly Flat with Climbing Decider
Mixed with Climbing Decider
Mostly Climbing
Grand Tour
```

Names can be refined later. The priority is to create distinct enough categories that the role requirements differ meaningfully.

### Suggested first-pass logic

Use counts of stage types:

```text
flat_count
hill_count
medium_mountain_count
mountain_count
time_trial_count
cobble_count
```

Then assign a profile using simple rules.

Example:

```text
If race is a Grand Tour:
  Grand Tour
Else if one-day race and flat:
  Sprint
Else if one-day race and hill:
  Rolling
Else if one-day race and medium_mountain/mountain:
  Climbing
Else if stage race has no hill/medium_mountain/mountain stages:
  Flat
Else if stage race has mostly flat stages and at least one hill stage:
  Mostly Flat with Hilly Decider
Else if stage race has mostly hill stages and no mountain stages:
  Mostly Hilly
Else if stage race has mostly flat stages and at least one medium_mountain/mountain stage:
  Mostly Flat with Climbing Decider
Else if stage race has a broad mix including climbing stages:
  Mixed with Climbing Decider
Else if stage race is dominated by medium_mountain/mountain stages:
  Mostly Climbing
```

### Local schema addition

```sql
ALTER TABLE race ADD COLUMN profile TEXT;
```

Alternatively, use a separate table if we want profile generation to be plan/config-specific:

```sql
CREATE TABLE race_profile (
    race_id INTEGER PRIMARY KEY,
    profile TEXT NOT NULL,
    generated_by_config TEXT,
    FOREIGN KEY (race_id) REFERENCES race(id)
);
```

A separate table is more flexible later.

### Validation

* Every race receives a profile.
* Flat one-day races become `Sprint`.
* Hilly one-day races become `Rolling`.
* Medium-mountain/mountain one-day races become `Climbing`.
* Stage races are distributed among the stage-race profiles in a plausible way.
* Grand Tours can be identified separately.

### Definition of done

Race profiles are generated, stored, and visible in the database/UI.

---

## Phase 2 Step 3B — Add role requirements by race profile

### Goal

Define the set of rider roles required by each race profile for 6-, 7-, and 8-rider squads.

### Initial rider roles

Use the following starting set:

```text
Sprinter
Lead out
Puncheur
Flat domestique
Climbing domestique
Climbing super domestique / backup race leader
Climbing race leader
Free element / Baroudeur
```

Implementation note: use stable internal role keys, for example:

```text
sprinter
leadout
puncheur
flat_domestique
climbing_domestique
climbing_super_domestique
climbing_leader
baroudeur
```

Use `baroudeur` as the internal spelling for consistency.

### Config file

Create a role-demand config, for example:

```text
config/race_profiles.yaml
```

Example structure:

```yaml
profiles:
  Sprint:
    squad_sizes:
      6:
        sprinter: 1
        leadout: 1
        flat_domestique: 2
        baroudeur: 1
        puncheur: 1
      7:
        sprinter: 1
        leadout: 1
        flat_domestique: 3
        baroudeur: 1
        puncheur: 1
      8:
        sprinter: 1
        leadout: 1
        flat_domestique: 4
        baroudeur: 1
        puncheur: 1

  Rolling:
    squad_sizes:
      7:
        puncheur: 1
        sprinter: 1
        leadout: 1
        flat_domestique: 2
        climbing_domestique: 1
        baroudeur: 1

  Climbing:
    squad_sizes:
      7:
        climbing_leader: 1
        climbing_super_domestique: 1
        climbing_domestique: 3
        flat_domestique: 1
        baroudeur: 1
```

The exact distributions are expected to change after testing.

### Validation

* Every imported race can be mapped to a profile.
* Every profile has role requirements for the race's rider capacity.
* The sum of required roles equals the race capacity.
* If a profile/size combination is missing, the tool reports a config error before optimisation.

### Definition of done

Each race can be assigned an exact set of required roles based on profile and squad size.

---

## Phase 2 Step 3C — Optimise rider-race-role assignments

### Goal

Upgrade the optimisation question from:

```text
Is rider X competing in race Y?
```

to:

```text
Is rider X competing in race Y in role Z?
```

Decision variable:

```text
x[rider, race, role] ∈ {0, 1}
```

### Constraints

#### One role per rider per race

```text
For each rider X and race Y:
  sum over roles Z of x[X, Y, Z] <= 1
```

#### Race role requirements

For each race and role:

```text
sum over riders X of x[X, race, role] = required_count[race, role]
```

This replaces the simpler race-capacity constraint, because the role counts should sum to the capacity.

#### Race capacity check

Keep this as a validation check even if redundant:

```text
sum over riders and roles of x[X, race, role] = capacity[race]
```

#### Maximum/soft race days

Continue using the current race-day approach until Phase 2 Step 4 changes it.

#### No overlapping race assignments

Continue enforcing full race-interval overlap constraints:

```text
For each rider X and overlapping races A/B:
  assigned[X, A] + assigned[X, B] <= 1
```

where:

```text
assigned[X, race] = sum over roles Z of x[X, race, Z]
```

### Simple role-aware scoring

Keep the first role scoring deliberately simple.

For each rider/race/role:

```text
score = stage_stat_score + role_stat_score
```

Where:

```text
stage_stat_score = sum of matching stat across stages
```

and `role_stat_score` is a simple role-specific stat contribution.

Example starting role-stat mapping:

```text
sprinter                         → sprint
leadout                          → acceleration or sprint
puncheur                         → hill
flat_domestique                  → flat
climbing_domestique              → mountain or medium_mountain
climbing_super_domestique         → mountain
climbing_leader                  → mountain
baroudeur                        → stamina/resistance/fighter if available, otherwise hill/flat fallback
```

If `fighter` is not imported yet, use a fallback for `baroudeur` until that stat is added.

### Expected effect

We should start seeing more variety in assignments, especially in stage races and Grand Tours:

* not every slot goes to the highest generic parcours score
* sprint races reserve sprinter/leadout slots
* climbing races reserve leader/support slots
* weaker riders may appear in lower-value support roles

### Validation

* Every race has the exact required count for each role.
* A rider has no more than one role in a race.
* No rider is assigned to overlapping races.
* Assignments look more varied than Phase 1.
* Grand Tours and stage races start showing more realistic squad composition.

### Definition of done

The optimiser generates rider-race-role assignments that satisfy role requirements.

---

## Phase 2 Step 3D — Save role assignments to SQLite

### Goal

Persist the new role-aware optimisation results.

### Schema update

Extend `race_assignment`:

```sql
ALTER TABLE race_assignment ADD COLUMN role TEXT;
```

If starting fresh, prefer:

```sql
CREATE TABLE race_assignment (
    plan_id INTEGER NOT NULL,
    rider_id INTEGER NOT NULL,
    race_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    rider_race_score INTEGER,
    PRIMARY KEY (plan_id, rider_id, race_id),
    FOREIGN KEY (plan_id) REFERENCES plan(id),
    FOREIGN KEY (rider_id) REFERENCES rider(id),
    FOREIGN KEY (race_id) REFERENCES race(id)
);
```

Optional summary table:

```sql
CREATE TABLE rider_role_plan_summary (
    plan_id INTEGER NOT NULL,
    rider_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    race_days INTEGER NOT NULL,
    assigned_races INTEGER NOT NULL,
    total_score INTEGER NOT NULL,
    PRIMARY KEY (plan_id, rider_id, role),
    FOREIGN KEY (plan_id) REFERENCES plan(id),
    FOREIGN KEY (rider_id) REFERENCES rider(id)
);
```

### Validation

Using a SQLite viewer:

* Every saved assignment has a role.
* Each race's saved roles match the required role counts.
* Rider-role summary rows are correct if using the summary table.

### Definition of done

Role assignments are stored and inspectable in the database.

---

## Phase 2 Step 3E — Show role assignments in the web app

### Goal

Update the UI so the user can inspect role assignments.

### Race view update

Show assigned riders grouped or sorted by role.

Example:

```text
Sprinter
  Andrea Donati

Lead out
  Laurence Pithie

Flat domestique
  Rider A
  Rider B
```

### Rider view update

For each rider, show:

* assigned races
* assigned role in each race
* total days by role

Example:

```text
Role summary
  Sprinter: 32 days
  Lead out: 8 days
  Baroudeur: 14 days
```

### Optional chart

A pie chart or simple bar chart could show the rider's days by role.

For the first implementation, a table is sufficient. A chart can be added once the data is validated.

### Calendar view

Do not show role assignments directly in the calendar yet. The block can remain race abbreviation only.

### Validation

* Race pages show role assignments correctly.
* Rider pages show assigned role for each race.
* Rider days-by-role totals match the database.

### Definition of done

The web app makes role assignments visible and easy to inspect.

---

## Phase 2 Step 3F — Add role weightings by race profile

### Goal

Make role importance configurable and use it in scoring.

This helps solve a key problem: without role weighting, 6-, 7-, and 8-rider races can be unbalanced, and support roles may be valued too similarly to leader roles.

The race leader role should often be worth roughly as much as the rest of the team combined, depending on race profile.

Examples:

* Sprint race: `sprinter` is the highest-value role.
* Rolling race: `puncheur` may be the highest-value role.
* Climbing/stage race: `climbing_leader` is the highest-value role.
* Grand Tour: `climbing_leader` and `climbing_super_domestique` are highly valuable, but secondary roles still matter.

### Config update

Extend profile role config with weights.

Example:

```yaml
profiles:
  Sprint:
    squad_sizes:
      7:
        roles:
          sprinter:
            count: 1
            weight: 50
          leadout:
            count: 1
            weight: 15
          flat_domestique:
            count: 3
            weight: 8
          baroudeur:
            count: 1
            weight: 6
          puncheur:
            count: 1
            weight: 5
```

### Normalisation

After reading config, normalise role weights so the total race role weighting sums to 100.

Because CP-SAT uses integer coefficients, use integer-normalised weights.

Example approach:

```text
raw weights → scale to sum 100 → round to integers → adjust final role to ensure exact sum 100
```

When a role has multiple required riders, decide whether the weight applies:

Option A:

```text
weight is total weight for all riders in that role
```

Option B:

```text
weight is per-rider weight for that role
```

For clarity, prefer Option A in config:

```text
role_total_weight
```

Then divide by count to get per-slot weight.

### Scoring update

For each rider/race/role:

```text
weighted_score = base_role_assignment_score × per_slot_role_weight
```

Then apply race value coefficient as well.

### Expected effect

* Top riders should be distributed more sensibly among races.
* Star riders should be more likely to take leader roles rather than low-value support roles.
* Weaker riders should appear in major races when filling low-value support roles.
* 6-, 7-, and 8-rider races should be more comparable in total scoring.

### Validation

* Normalised role weights sum to 100 for each race.
* Required role counts still sum to race capacity.
* Star riders appear more often in high-value race-leader roles.
* Weaker riders can still appear in big races in lower-value roles.
* Changing role weights in config visibly changes optimisation output.

### Definition of done

Role weightings are config-driven, integer-normalised, and materially improve assignment distribution.

---

## Phase 2 Step 4 — Replace hard max race days with soft race-day scoring

### Goal

Drop the hard 75-race-day limit and replace it with a scoring modifier.

This allows the optimiser to make realistic trade-offs while strongly discouraging excessive workloads.

### Target behaviour

Aim for:

```text
Most riders: 60–70 race days
A few riders: 70–74 race days
No riders: above 75 race days, once penalties are tuned
```

This matches observed manual planning, where a reasonable allocation can keep most riders between 60 and 70 days with only a handful above 70.

### Scoring bands

Suggested first version:

```text
Below 60 days: mild penalty per missing day
60–70 days: no penalty
71–75 days: mild/moderate penalty per extra day
Above 75 days: heavy penalty per extra day
```

Example config:

```yaml
race_day_penalties:
  target_min: 60
  target_max: 70
  upper_warning: 75
  under_min_penalty_per_day: 20
  above_target_penalty_per_day: 30
  above_warning_penalty_per_day: 200
```

Exact values should be tuned on sample data.

### CP-SAT modelling

For each rider, compute:

```text
total_days[rider] = sum assigned race days
```

Then create penalty variables for:

```text
under_60
above_70
above_75
```

Add negative terms to the objective.

Important: Even though the hard cap is removed, we may temporarily keep an emergency hard upper bound such as 90 or 100 days to keep the model bounded and avoid absurd outputs during tuning.

### Validation

* Optimiser remains feasible.
* Race-day totals cluster around 60–70.
* A few riders can reach 70–74 if it improves the plan.
* No rider exceeds 75 after penalty tuning.
* If a rider does exceed 75 during tuning, the score/report makes the penalty obvious.

### Definition of done

Race-day balancing is handled through scoring rather than a hard 75-day constraint, and the output resembles a realistic hand-planned workload distribution.

---

## Phase 2 Step 5 — Add role/stage scoring formulas

### Goal

Replace the simple scoring model with configurable linear formulas for each race role on each stage profile.

Instead of:

```text
stage stat + role stat
```

use:

```text
weighted sum of rider stats based on role and stage type
```

### Formula structure

For each role and stage type, define a stat weighting.

Weights should normalise to 100 after reading from config.

Example:

```yaml
role_stage_formulas:
  sprinter:
    flat:
      sprint: 2
      acceleration: 1
      flat: 1
    hill:
      sprint: 1
      acceleration: 1
      hill: 1
      resistance: 1

  leadout:
    flat:
      acceleration: 2
      sprint: 1
      flat: 1
      resistance: 1

  climbing_leader:
    mountain:
      mountain: 3
      medium_mountain: 1
      recovery: 1
      resistance: 1
    medium_mountain:
      medium_mountain: 3
      mountain: 1
      hill: 1
      resistance: 1
```

The raw weights are easier to edit manually. The importer/loader should normalise them to integer weights summing to 100.

Example user-facing shorthand:

```text
Sprinter on Flat stage:
  2 Sprint + 1 Acceleration + 1 Flat
```

Normalised internal version:

```text
50 Sprint + 25 Acceleration + 25 Flat
```

### Scoring formula

For each rider, race, role:

```text
score = sum over stages of formula_score(rider, role, stage_type)
```

Then apply:

```text
role weight
race value coefficient
race-day penalty/bonus terms
```

### Expected effect

Assignments should become much more sensible.

Examples:

* Sprint leaders should have high sprint and acceleration.
* Leadout riders may have good sprint but slightly weaker acceleration/sprint than the actual sprinter, depending on formula tuning.
* Climbing leaders should favour mountain/medium-mountain/recovery/resistance.
* Climbing domestiques should be strong climbers but need not be the top GC rider.
* Flat domestiques should favour flat/stamina/resistance.
* Puncheurs should be strong on hills, acceleration, and resistance.

### Validation

* Formula weights normalise to 100 for every role/stage combination.
* Missing formulas fail loudly or use an explicitly configured fallback.
* Sprint allocations look more sensible.
* Leadout allocations look plausible.
* Climbing leaders and climbing support are differentiated.
* Changing formulas in config visibly changes optimisation output.

### Definition of done

The optimiser uses configurable role/stage stat formulas instead of the simple stat-matching model.

---

# Phase 2 Completion Criteria

Phase 2 is complete when:

1. Existing PCM rider-race allocations can be imported and fixed in the optimiser.
2. Race value coefficients influence assignment scoring.
3. Each race receives a profile.
4. Each race profile maps to required rider roles for the race's squad size.
5. The optimiser assigns rider-race-role combinations.
6. Role assignments are saved to the database.
7. Role assignments are visible in the web app.
8. Role weights are config-driven and normalised for scoring.
9. Race-day balancing uses soft scoring modifiers instead of a strict 75-day cap.
10. Role/stage scoring formulas are config-driven and normalised.

---

# Explicitly still out of scope after Phase 2

Even after Phase 2, we are not yet handling:

* detailed time-trial modelling
* detailed cobbles modelling
* cobbled race profiles
* team time trials
* prologues
* manual UI-based locks/overrides, beyond imported PCM assignments
* adding/removing races from the calendar
* fitness peaks
* race objectives
* training camps/recon
* campaign coherence
* sprint-train pairing logic beyond role formulas
* leader/domestique synergy bonuses
* save-file writeback
* human-readable justifications

These are likely Phase 3+ concerns.
