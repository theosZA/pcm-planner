"""
Rider × race scoring for the PCM Season Planner optimiser.

A race score is the sum of the rider's relevant stat across every stage in the
race, using these terrain → stat mappings:

    stage_type          → stat used
    ──────────────────────────────
    TimeTrial           → time_trial   (regardless of relief)
    TeamTimeTrial       → time_trial   (regardless of relief)
    Normal + Flat       → flat
    Normal + Hill       → hill
    Normal + Mountain   → mountain
    Normal + MedMtn     → medium_mountain

Because rider stats are integers, the score is an integer too.  No averaging
is performed here — stage-count and rider-count scaling will be added later.
Stages with missing or unrecognised terrain are skipped (score contribution 0).

Public API
----------
build_scoring_matrix(data)  →  dict[(rider_id, race_id), int]
score_rider_for_race(rider, stages)  →  int
"""

from __future__ import annotations

from collections import defaultdict
from typing import Optional

from optimise.model import PlannerData, Race, RaceClass, Rider, SquadProfile, Stage

# Map (stage_type, relief) → Rider attribute name.
# TimeTrial/TeamTimeTrial always map to "time_trial" regardless of relief.
_TT_TYPES = frozenset({"TimeTrial", "TeamTimeTrial"})

_RELIEF_STAT: dict[str, str] = {
    "Flat": "flat",
    "Hill": "hill",
    "Medium Mountain": "medium_mountain",
    "Mountain": "mountain",
}

# UCI points for winning the race (or a stage, for stage races), keyed by
# RaceClass enum member.  Used as a score multiplier so prestige is reflected
# in the objective.  Unmapped/unknown race classes default to 1.
RACE_LEVEL_MULTIPLIER: dict[RaceClass, int] = {
    RaceClass.WORLD_CHAMPIONSHIP:        90,
    RaceClass.WORLD_CHAMPIONSHIP_ITT:    45,
    RaceClass.EUROPEAN_CHAMPIONSHIP:     25,
    RaceClass.EUROPEAN_CHAMPIONSHIP_ITT: 7,
    RaceClass.NATIONAL_CHAMPIONSHIP:     10,
    RaceClass.NATIONAL_CHAMPIONSHIP_ITT: 5,
    RaceClass.TOUR_DE_FRANCE:            21,
    RaceClass.OTHER_GRAND_TOUR:          11,
    RaceClass.MONUMENT:                  80,
    RaceClass.WORLD_TOUR_CLASSIC_A:      50,
    RaceClass.WORLD_TOUR_CLASSIC_B:      40,
    RaceClass.WORLD_TOUR_CLASSIC_C:      30,
    RaceClass.WORLD_TOUR_STAGE_RACE_A:   6,
    RaceClass.WORLD_TOUR_STAGE_RACE_B:   5,
    RaceClass.WORLD_TOUR_STAGE_RACE_C:   4,
    RaceClass.CONTINENTAL_2_PRO:         3,
    RaceClass.CONTINENTAL_2_1:           2,
    RaceClass.CONTINENTAL_2_2:           1,
    RaceClass.CONTINENTAL_1_PRO:         20,
    RaceClass.CONTINENTAL_1_1:           12,
    RaceClass.CONTINENTAL_1_2:           4,
    RaceClass.U23_NATIONS_CUP:           5,
    RaceClass.CONTINENTAL_1_2_U23:       3,
    RaceClass.CONTINENTAL_2_2_U23:       1,
}


def _stage_stat_name(stage: Stage) -> Optional[str]:
    """Return the Rider attribute name that best describes the stage demands.

    Returns None if the terrain data is missing or unrecognised.
    """
    if stage.stage_type in _TT_TYPES:
        return "time_trial"
    if stage.relief in _RELIEF_STAT:
        return _RELIEF_STAT[stage.relief]
    return None


def score_rider_for_race(
    rider: Rider,
    stages: list[Stage],
    level_multiplier: int = 1,
) -> int:
    """Return the integer score for *rider* across the terrain of *stages*.

    The score is the sum of the rider's relevant stat for each stage that has
    recognisable terrain data, multiplied by *level_multiplier* (the race
    prestige weight derived from ``RACE_LEVEL_MULTIPLIER``).  Stages with
    missing or unrecognised terrain contribute 0.  Returns 0 if there are no
    scorable stages.
    """
    total = 0
    for stage in stages:
        stat_name = _stage_stat_name(stage)
        if stat_name is None:
            continue
        total += getattr(rider, stat_name, None) or 0
    return total * level_multiplier


def classify_squad_profile(race: Race, stages: list[Stage]) -> SquadProfile:
    """Return the squad profile for *race*.

    Multi-stage races always use ``SquadProfile.STAGE_RACE``.  For single-stage classics:

    - Any TT or team TT stage → ``SquadProfile.TIME_TRIAL``
    - Flat or Hill relief     → ``SquadProfile.SPRINT``
    - Medium Mountain or Mountain relief → ``SquadProfile.CLIMBING``

    Falls back to ``SquadProfile.SPRINT`` when terrain data is absent.
    """
    if race.is_stage_race:
        return SquadProfile.STAGE_RACE
    for stage in stages:
        if stage.stage_type in _TT_TYPES:
            return SquadProfile.TIME_TRIAL
    for stage in stages:
        if stage.relief in {"Flat", "Hill"}:
            return SquadProfile.SPRINT
        if stage.relief in {"Medium Mountain", "Mountain"}:
            return SquadProfile.CLIMBING
    return SquadProfile.SPRINT


def build_race_profiles(data: PlannerData) -> dict[int, tuple[SquadProfile, int]]:
    """Return ``{race_id: (squad_profile, stage_value)}`` for every race in *data*.

    ``stage_value`` is the per-stage prestige multiplier from
    ``RACE_LEVEL_MULTIPLIER`` (defaults to 1 for unmapped levels).
    """
    race_ids = {r.id for r in data.races}
    stages_by_race: dict[int, list[Stage]] = defaultdict(list)
    for stage in data.stages:
        if stage.race_id in race_ids:
            stages_by_race[stage.race_id].append(stage)

    return {
        race.id: (
            classify_squad_profile(race, stages_by_race.get(race.id, [])),
            RACE_LEVEL_MULTIPLIER.get(race.race_class, 1),
        )
        for race in data.races
    }


def build_scoring_matrix(data: PlannerData) -> dict[tuple[int, int], int]:
    """Return rider × race scores for all (rider, race) pairs in *data*.

    Keys are ``(rider.id, race.id)``; values are integer sums of rider stats
    across each stage's relevant terrain stat.

    Only races that appear in ``data.races`` are included (i.e., races the
    player's team is actively entered in, already filtered by invitation state).
    """
    race_ids = {r.id for r in data.races}

    # Group stages by race_id, ignoring stages from races not in the race list.
    stages_by_race: dict[int, list[Stage]] = defaultdict(list)
    for stage in data.stages:
        if stage.race_id in race_ids:
            stages_by_race[stage.race_id].append(stage)

    matrix: dict[tuple[int, int], int] = {}
    for rider in data.riders:
        for race in data.races:
            stages = stages_by_race.get(race.id, [])
            multiplier = RACE_LEVEL_MULTIPLIER.get(race.race_class, 1)
            matrix[(rider.id, race.id)] = score_rider_for_race(rider, stages, multiplier)

    return matrix
