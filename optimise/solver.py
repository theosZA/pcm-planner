"""
CP-SAT optimisation model for the PCM Season Planner.

Builds and solves a CP-SAT model where each (rider, race, role) triple has a
boolean decision variable representing whether that rider fills that role in
that race.

The objective is to maximise the total score — the sum of each boolean
multiplied by the pre-calculated terrain-suitability score for the
(rider, race) pair.

Public API
----------
SolveResult  — dataclass returned by solve()
solve(data, matrix, compositions)  → SolveResult"""
# Note: scores from scoring.py are already integers, so no scaling is needed.

from __future__ import annotations

from dataclasses import dataclass, field

from ortools.sat.python import cp_model

from optimise.model import PlannerData, Race, RaceClass, RaceDayPenalties, Rider, RiderRole


def find_overlapping_pairs(races: list[Race]) -> list[tuple[Race, Race]]:
    """Return all (a, b) race pairs whose date ranges overlap (inclusive).

    A pair overlaps when either race's start date falls within the other's
    [start_date, end_date] range.  Races with no dates are excluded.

    Pairs where both races are national championships (or NC ITTs) for
    different countries are excluded: the nationality eligibility constraint
    already makes it impossible for any rider to be assigned to both, so the
    overlap constraint would be redundant.
    """
    _nat_champ_classes = {RaceClass.NATIONAL_CHAMPIONSHIP, RaceClass.NATIONAL_CHAMPIONSHIP_ITT}

    def is_nat_champ(race: Race) -> bool:
        return race.race_class in _nat_champ_classes

    pairs: list[tuple[Race, Race]] = []
    for i in range(len(races)):
        a = races[i]
        if not a.start_date or not a.end_date:
            continue
        for j in range(i + 1, len(races)):
            b = races[j]
            if not b.start_date or not b.end_date:
                continue
            if is_nat_champ(a) and is_nat_champ(b) and a.country != b.country:
                continue
            if b.start_date <= a.end_date and a.start_date <= b.end_date:
                pairs.append((a, b))
    return pairs


@dataclass
class SolveResult:
    """Outcome of a CP-SAT solve call."""

    status: str                                 # "OPTIMAL", "FEASIBLE", "INFEASIBLE", …
    objective_value: int                        # sum of integer rider-race scores
    assigned: dict[tuple[int, int, RiderRole], bool] = field(default_factory=dict)
    # assigned[(rider.id, race.id, role)] = True/False

    @property
    def race_assignments(self) -> set[tuple[int, int]]:
        """Set of (rider_id, race_id) pairs where any role was assigned."""
        return {(rider_id, race_id) for (rider_id, race_id, _), v in self.assigned.items() if v}

    @property
    def total_assignments(self) -> int:
        return len(self.race_assignments)


def solve(
    data: PlannerData,
    matrix: dict[tuple[int, int], int],
    compositions: dict[int, dict[RiderRole, int]],
    time_limit: float | None = None,
    penalties: RaceDayPenalties | None = None,
) -> SolveResult:
    """Build and solve the CP-SAT model.

    Parameters
    ----------
    data:
        Full planning data (riders, races, stages).
    matrix:
        Pre-calculated integer score for each (rider.id, race.id) pair, as
        returned by ``scoring.build_scoring_matrix(data)``.
    compositions:
        Role breakdown for each race: ``{race_id: {role: count}}``, as
        resolved from ``SQUAD_COMPOSITIONS``.
    penalties:
        Race-day band penalty config.  If None, default values are used.

    Returns
    -------
    SolveResult with the solver status, objective value, and assignment dict.
    """
    if penalties is None:
        penalties = RaceDayPenalties()

    model = cp_model.CpModel()

    # --- Decision variables: one boolean per (rider, race, role) triple -------
    role_assigned: dict[tuple[int, int, RiderRole], cp_model.IntVar] = {}
    for rider in data.riders:
        for race in data.races:
            if race.id not in compositions:
                continue
            for role in compositions[race.id]:
                role_assigned[(rider.id, race.id, role)] = model.new_bool_var(
                    f"role_r{rider.id}_race{race.id}_{role.value}"
                )

    # --- Objective: maximise sum of score × role booleans, minus penalties ----
    # Each role var for (rider, race, role) uses the role-specific terrain score.
    objective_terms = []
    for rider in data.riders:
        for race in data.races:
            if race.id not in compositions:
                continue
            for role in compositions[race.id]:
                coeff = matrix.get((rider.id, race.id, role), 0)
                if coeff:
                    objective_terms.append(coeff * role_assigned[(rider.id, race.id, role)])

    # Piecewise-linear race-day penalties, modelled with auxiliary IntVars.
    # For rider with total_days d:
    #   under_min  = max(0, target_min − d)          → under_min_penalty/day
    #   above_warn = max(0, d − upper_warning)        → above_warning_penalty/day
    #   above_tgt  = max(0, min(d, upper_warning) − target_max)
    #              = max(0, d − above_warn − target_max)  → above_target_penalty/day
    p = penalties
    for rider in data.riders:
        total_days = sum(
            race.race_days * role_assigned[(rider.id, race.id, role)]
            for race in data.races
            if race.id in compositions
            for role in compositions[race.id]
        )

        under_min = model.new_int_var(0, p.target_min, f"under_min_r{rider.id}")
        model.add_max_equality(under_min, [0, p.target_min - total_days])

        above_warn = model.new_int_var(
            0, p.absolute_max - p.upper_warning, f"above_warn_r{rider.id}"
        )
        model.add_max_equality(above_warn, [0, total_days - p.upper_warning])

        above_tgt = model.new_int_var(
            0, p.upper_warning - p.target_max, f"above_tgt_r{rider.id}"
        )
        model.add_max_equality(above_tgt, [0, total_days - above_warn - p.target_max])

        if p.under_min_penalty_per_day:
            objective_terms.append(-p.under_min_penalty_per_day * under_min)
        if p.above_target_penalty_per_day:
            objective_terms.append(-p.above_target_penalty_per_day * above_tgt)
        if p.above_warning_penalty_per_day:
            objective_terms.append(-p.above_warning_penalty_per_day * above_warn)

    model.maximize(sum(objective_terms))

    # --- Constraints ----------------------------------------------------------

    # Each rider can fill at most one role per race.
    for rider in data.riders:
        for race in data.races:
            if race.id not in compositions:
                continue
            model.add(
                sum(role_assigned[(rider.id, race.id, role)] for role in compositions[race.id])
                <= 1
            )

    # Each role slot in a race has a capacity limit from the squad composition.
    for race in data.races:
        if race.id not in compositions:
            continue
        for role, capacity in compositions[race.id].items():
            model.add(
                sum(role_assigned[(rider.id, race.id, role)] for rider in data.riders)
                <= capacity
            )

    # Each rider can race at most absolute_max days across the whole season.
    for rider in data.riders:
        model.add(
            sum(
                race.race_days * role_assigned[(rider.id, race.id, role)]
                for race in data.races
                if race.id in compositions
                for role in compositions[race.id]
            )
            <= penalties.absolute_max
        )

    # National championship races: only riders whose country matches the race
    # country may be assigned.  Races without a country set are unrestricted.
    # Additionally, we must assign as many eligible riders as possible —
    # i.e. exactly min(rider_capacity, eligible_rider_count).
    _nat_champ_classes = {RaceClass.NATIONAL_CHAMPIONSHIP, RaceClass.NATIONAL_CHAMPIONSHIP_ITT}
    for race in data.races:
        if race.race_class not in _nat_champ_classes or not race.country:
            continue
        if race.id not in compositions:
            continue
        for rider in data.riders:
            if rider.country != race.country:
                model.add(
                    sum(
                        role_assigned[(rider.id, race.id, role)]
                        for role in compositions[race.id]
                    )
                    == 0
                )
        eligible_count = sum(1 for rider in data.riders if rider.country == race.country)
        required = min(race.rider_capacity, eligible_count)
        model.add(
            sum(
                role_assigned[(rider.id, race.id, role)]
                for rider in data.riders
                for role in compositions[race.id]
            )
            == required
        )

    # A rider can't be assigned to two races that overlap in dates.
    overlapping_pairs = find_overlapping_pairs(data.races)
    print(f"  Overlapping race pairs: {len(overlapping_pairs)}")

    for rider in data.riders:
        for a, b in overlapping_pairs:
            a_vars = [role_assigned[(rider.id, a.id, role)] for role in compositions.get(a.id, {})]
            b_vars = [role_assigned[(rider.id, b.id, role)] for role in compositions.get(b.id, {})]
            if a_vars and b_vars:
                model.add(sum(a_vars) + sum(b_vars) <= 1)

    # --- Solve ----------------------------------------------------------------
    solver = cp_model.CpSolver()
    if time_limit is not None:
        solver.parameters.max_time_in_seconds = time_limit
    status_code = solver.solve(model)
    status = solver.status_name(status_code)

    result_assigned: dict[tuple[int, int, RiderRole], bool] = {}
    if status_code in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for key, var in role_assigned.items():
            result_assigned[key] = bool(solver.value(var))
        objective = int(solver.objective_value)
    else:
        objective = 0

    return SolveResult(
        status=status,
        objective_value=objective,
        assigned=result_assigned,
    )
