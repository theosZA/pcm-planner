"""
Constraint checking and feasibility validation for the PCM Season Planner optimiser.

Currently contains aggregate-level checks. As the optimiser grows, this module
will expand to include:
- Per-rider maximum race-day enforcement (75-day cap).
- Per-race minimum/maximum squad size constraints.
- Race overlap detection (a rider cannot be in two concurrent races).
- Mandatory assignment constraints (e.g. team leader must attend Grand Tours).

CheckResult
    Named container for the outcome of a single check, with a human-readable message.

run_all_checks()
    Runs all defined checks in order and returns the full list of results.
    Returns non-empty even if data is missing, so the caller always gets feedback.
"""

from __future__ import annotations

from dataclasses import dataclass

from optimise.model import PlannerData, RiderRole, SquadProfile
from optimise.squad_config import SQUAD_COMPOSITIONS


@dataclass
class CheckResult:
    """Outcome of a single validation check."""

    passed: bool
    message: str

    def __str__(self) -> str:
        label = "OK  " if self.passed else "FAIL"
        return f"[{label}] {self.message}"


def check_riders_present(data: PlannerData) -> CheckResult:
    """Fail if the squad has no riders — the rider migration may not have run."""
    if data.riders:
        return CheckResult(True, f"{len(data.riders)} rider(s) loaded.")
    return CheckResult(False, "No riders found. Run the migration first.")


def check_races_present(data: PlannerData) -> CheckResult:
    """Fail if no races are loaded — the race/stage migration may not have run."""
    if data.races:
        return CheckResult(True, f"{len(data.races)} race(s) loaded.")
    return CheckResult(False, "No races found. Run the migration first.")


def check_races_have_stage_data(data: PlannerData) -> CheckResult:
    """Fail if any races are missing stage data or squad size information.

    race_days = 0 means no stages were imported for that race.
    rider_capacity = 0 means the race class (with squad size info) was not found.
    Both conditions leave the race unusable by the optimiser.
    """
    missing_stages = [r for r in data.races if r.race_days == 0]
    missing_capacity = [r for r in data.races if r.rider_capacity == 0]

    issues: list[str] = []
    if missing_stages:
        names = ", ".join(r.abbreviation or r.name for r in missing_stages)
        issues.append(f"{len(missing_stages)} race(s) with no stage data: {names}")
    if missing_capacity:
        names = ", ".join(r.abbreviation or r.name for r in missing_capacity)
        issues.append(f"{len(missing_capacity)} race(s) with unknown squad size: {names}")

    if issues:
        return CheckResult(False, "; ".join(issues))
    return CheckResult(True, "All races have stage data and squad size information.")


def check_aggregate_feasibility(data: PlannerData) -> CheckResult:
    """Check that total rider-days demanded does not exceed total rider-days available.

    This is a necessary (not sufficient) condition for a valid assignment to exist.
    It confirms there is enough aggregate squad capacity before considering race
    overlaps and per-rider limits.

    Calculation:
        demanded  = Σ (race_days × rider_capacity) for all races
        available = 75 × number of riders
    """
    demanded = data.total_race_days_demanded
    available = data.total_rider_days_available

    if demanded <= available:
        return CheckResult(
            True,
            f"Aggregate feasibility OK — {demanded} rider-days demanded "
            f"vs {available} available "
            f"(75 × {len(data.riders)} riders). "
            f"{available - demanded} rider-days of slack.",
        )

    return CheckResult(
        False,
        f"Aggregate feasibility FAILED — {demanded} rider-days demanded "
        f"exceeds {available} available "
        f"(75 × {len(data.riders)} riders) "
        f"by {demanded - available} rider-days.",
    )


def check_races_have_squad_composition(
    data: PlannerData,
    race_profiles: dict[int, tuple[SquadProfile, int]],
) -> CheckResult:
    """Fail if any race lacks a squad composition for its (profile, capacity) pair.

    Races without a composition cannot be included in the solve, so this check
    catches missing config entries before the solver runs.
    """
    missing: list[str] = []
    for race in data.races:
        if race.rider_capacity == 0:
            continue  # already caught by check_races_have_stage_data
        profile, _ = race_profiles.get(race.id, (None, None))
        if profile is None:
            continue
        if (profile, race.rider_capacity) not in SQUAD_COMPOSITIONS:
            missing.append(
                f"{race.abbreviation or race.name} "
                f"({profile.value}, {race.rider_capacity} riders)"
            )

    if missing:
        return CheckResult(
            False,
            f"{len(missing)} race(s) missing a squad composition: {', '.join(missing)}",
        )
    return CheckResult(True, "All races have a squad composition defined.")


def run_all_checks(
    data: PlannerData,
    race_profiles: dict[int, tuple[SquadProfile, int]] | None = None,
) -> list[CheckResult]:
    """Run all validation checks in order and return the full list of results."""
    checks = [
        check_riders_present(data),
        check_races_present(data),
        check_races_have_stage_data(data),
        check_aggregate_feasibility(data),
    ]
    if race_profiles is not None:
        checks.append(check_races_have_squad_composition(data, race_profiles))
    return checks
