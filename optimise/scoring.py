"""
Rider × race scoring for the PCM Season Planner optimiser.

A race score represents how well a rider's stats match the terrain demands of a
race, expressed as a 0–100 float.  It is computed by averaging the rider's
relevant stat over every stage in the race, using these mappings:

    stage_type          → stat used
    ──────────────────────────────
    TimeTrial           → time_trial   (regardless of relief)
    TeamTimeTrial       → time_trial   (regardless of relief)
    Normal + Flat       → flat
    Normal + Hill       → hill
    Normal + Mountain   → mountain
    Normal + MedMtn     → medium_mountain

If a stage has no terrain data, it is skipped (not counted in the average).
If a race has no stages, the score is 0.0; if the rider's stat is None it counts
as 0.

Public API
----------
build_scoring_matrix(data)  →  dict[(rider_id, race_id), float]
score_rider_for_race(rider, stages)  →  float
"""

from __future__ import annotations

from collections import defaultdict
from typing import Optional

from optimise.model import PlannerData, Rider, Stage

# Map (stage_type, relief) → Rider attribute name.
# TimeTrial/TeamTimeTrial always map to "time_trial" regardless of relief.
_TT_TYPES = frozenset({"TimeTrial", "TeamTimeTrial"})

_RELIEF_STAT: dict[str, str] = {
    "Flat": "flat",
    "Hill": "hill",
    "Medium Mountain": "medium_mountain",
    "Mountain": "mountain",
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


def score_rider_for_race(rider: Rider, stages: list[Stage]) -> float:
    """Compute a 0–100 score for how well *rider* suits the terrain of *stages*.

    The score is the mean of the rider's relevant stat across all stages that
    have recognisable terrain data.  Stages with unrecognised or missing terrain
    are excluded from both the numerator and denominator.  Returns 0.0 if there
    are no scorable stages.
    """
    total = 0
    count = 0
    for stage in stages:
        stat_name = _stage_stat_name(stage)
        if stat_name is None:
            continue
        stat_value = getattr(rider, stat_name, None) or 0
        total += stat_value
        count += 1

    return total / count if count else 0.0


def build_scoring_matrix(data: PlannerData) -> dict[tuple[int, int], float]:
    """Return rider × race scores for all (rider, race) pairs in *data*.

    Keys are ``(rider.id, race.id)``; values are 0–100 floats.

    Only races that appear in ``data.races`` are included (i.e., races the
    player's team is actively entered in, already filtered by invitation state).
    """
    race_ids = {r.id for r in data.races}

    # Group stages by race_id, ignoring stages from races not in the race list.
    stages_by_race: dict[int, list[Stage]] = defaultdict(list)
    for stage in data.stages:
        if stage.race_id in race_ids:
            stages_by_race[stage.race_id].append(stage)

    matrix: dict[tuple[int, int], float] = {}
    for rider in data.riders:
        for race in data.races:
            stages = stages_by_race.get(race.id, [])
            matrix[(rider.id, race.id)] = score_rider_for_race(rider, stages)

    return matrix
