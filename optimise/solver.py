"""
CP-SAT optimisation model for the PCM Season Planner.

Builds and solves a CP-SAT model where each (rider, race) pair has a boolean
decision variable representing whether that rider is selected for that race.

The objective is to maximise the total score — the sum of each boolean
multiplied by the pre-calculated terrain-suitability score for that pair.

At this stage NO constraints are added beyond the implicit [0, 1] domain of
each boolean, so the solver will (predictably) assign every rider to every
race.  Constraints will be layered on top in subsequent iterations.

Public API
----------
SolveResult  — dataclass returned by solve()
solve(data, matrix)  → SolveResult
"""
# Note: scores from scoring.py are already integers, so no scaling is needed.

from __future__ import annotations

from dataclasses import dataclass, field

from ortools.sat.python import cp_model

from optimise.model import PlannerData, Race, RaceDayPenalties, Rider


def find_overlapping_pairs(races: list[Race]) -> list[tuple[Race, Race]]:
    """Return all (a, b) race pairs whose date ranges overlap (inclusive).

    A pair overlaps when either race's start date falls within the other's
    [start_date, end_date] range.  Races with no dates are excluded.
    """
    pairs: list[tuple[Race, Race]] = []
    for i in range(len(races)):
        a = races[i]
        if not a.start_date or not a.end_date:
            continue
        for j in range(i + 1, len(races)):
            b = races[j]
            if not b.start_date or not b.end_date:
                continue
            if b.start_date <= a.end_date and a.start_date <= b.end_date:
                pairs.append((a, b))
    return pairs


@dataclass
class SolveResult:
    """Outcome of a CP-SAT solve call."""

    status: str                                 # "OPTIMAL", "FEASIBLE", "INFEASIBLE", …
    objective_value: int                        # sum of integer rider-race scores
    assigned: dict[tuple[int, int], bool] = field(default_factory=dict)
    # assigned[(rider.id, race.id)] = True/False

    @property
    def total_assignments(self) -> int:
        return sum(1 for v in self.assigned.values() if v)


def solve(
    data: PlannerData,
    matrix: dict[tuple[int, int], int],
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
    penalties:
        Race-day band penalty config.  If None, default values are used.

    Returns
    -------
    SolveResult with the solver status, objective value, and assignment dict.
    """
    if penalties is None:
        penalties = RaceDayPenalties()

    model = cp_model.CpModel()

    # --- Decision variables: one boolean per (rider, race) pair ---------------
    assigned: dict[tuple[int, int], cp_model.IntVar] = {}
    for rider in data.riders:
        for race in data.races:
            assigned[(rider.id, race.id)] = model.new_bool_var(
                f"assign_r{rider.id}_race{race.id}"
            )

    # --- Objective: maximise sum of score × boolean, minus race-day penalties --
    # Scores are already integers, so they can be used directly as coefficients.
    objective_terms = []
    for (rider_id, race_id), var in assigned.items():
        coeff = matrix.get((rider_id, race_id), 0)
        if coeff:
            objective_terms.append(coeff * var)

    # Piecewise-linear race-day penalties, modelled with auxiliary IntVars.
    # For rider with total_days d:
    #   under_min  = max(0, target_min − d)          → under_min_penalty/day
    #   above_warn = max(0, d − upper_warning)        → above_warning_penalty/day
    #   above_tgt  = max(0, min(d, upper_warning) − target_max)
    #              = max(0, d − above_warn − target_max)  → above_target_penalty/day
    p = penalties
    for rider in data.riders:
        total_days = sum(
            race.race_days * assigned[(rider.id, race.id)] for race in data.races
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

    # Each race gets at most rider_capacity riders.
    race_map = {r.id: r for r in data.races}
    for race in data.races:
        model.add(
            sum(assigned[(rider.id, race.id)] for rider in data.riders)
            <= race_map[race.id].rider_capacity
        )

    # Each rider can race at most absolute_max days across the whole season.
    for rider in data.riders:
        model.add(
            sum(race.race_days * assigned[(rider.id, race.id)] for race in data.races)
            <= penalties.absolute_max
        )

    # A rider can't be assigned to two races that overlap in dates.
    overlapping_pairs = find_overlapping_pairs(data.races)
    print(f"  Overlapping race pairs: {len(overlapping_pairs)}")

    for rider in data.riders:
        for a, b in overlapping_pairs:
            model.add(
                assigned[(rider.id, a.id)] + assigned[(rider.id, b.id)] <= 1
            )

    # --- Solve ----------------------------------------------------------------
    solver = cp_model.CpSolver()
    if time_limit is not None:
        solver.parameters.max_time_in_seconds = time_limit
    status_code = solver.solve(model)
    status = solver.status_name(status_code)

    result_assigned: dict[tuple[int, int], bool] = {}
    if status_code in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for (rider_id, race_id), var in assigned.items():
            result_assigned[(rider_id, race_id)] = bool(solver.value(var))
        objective = int(solver.objective_value)
    else:
        objective = 0

    return SolveResult(
        status=status,
        objective_value=objective,
        assigned=result_assigned,
    )
