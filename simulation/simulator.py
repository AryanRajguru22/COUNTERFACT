"""Counterfactual simulator. Owner: Goyal.

A deterministic minute-step model of the connection pool. It is pure: no I/O, no LLM, no randomness.
`seed` is recorded on the result but nothing in the model is stochastic, so every seed gives the same series.

Each minute t:
1. `replay` gives the effective params after `param_changes` and the intervention actions.
2. Available connections = pool_size - batch_conns * batch_conn_duty (never below 0).
3. Offered load in erlangs = demand_rps * (1 + retry_load) * conn_hold_ms / 1000, by Little's law.
4. The pool is an M/M/c queue whose waiters give up after timeout_ms. Its closed form gives the share of
   attempts that time out and the mean wait. In heavy overload the timeout share tends to the fluid
   1 - available / offered; near full utilisation it stays smooth instead of jumping.
5. error_rate is the share of attempts that time out (each one is a 5xx).
6. retry_max counts retries after the first attempt. A retry lands back in the same queue and times out
   with the same probability f, so the retry load is f + f^2 + ... + f^retry_max extra attempts per
   request. Failures in minute t feed the retry load of minute t + 1, so a storm builds over minutes.
"""

from __future__ import annotations

import math

from contracts.models import Intervention, SimSeries, SimulationResult, SystemModel
from simulation.replay import replay

# Calibration (INC-2041): the batch job keeps about a quarter of its connections checked out on average, which
# reproduces the observed 22 breach minutes and ~38% peak. A `batch_conn_duty` param overrides it.
BATCH_CONN_DUTY = 0.26


def simulate(model: SystemModel, interventions: list[Intervention], seed: int = 0) -> SimulationResult:
    timeline = replay(model, [i.action for i in interventions])
    error_rate, pool_wait_ms, inflight = [], [], []
    retry_load = 0.0
    for params, demand in zip(timeline, model.exogenous.demand_rps):
        hold_s = float(params["conn_hold_ms"]) / 1000
        timeout_s = float(params["timeout_ms"]) / 1000
        duty = float(params.get("batch_conn_duty", BATCH_CONN_DUTY))
        available = max(float(params["pool_size"]) - float(params["batch_conns"]) * duty, 0.0)
        attempts_rps = demand * (1 + retry_load)

        timed_out, wait_s = _pool(available, attempts_rps * hold_s, hold_s, timeout_s)
        error_rate.append(timed_out)
        pool_wait_ms.append(wait_s * 1000)
        # Little's law: attempts waiting for or holding a connection.
        inflight.append(attempts_rps * (wait_s + (1 - timed_out) * hold_s))
        retry_load = sum(timed_out ** n for n in range(1, int(params["retry_max"]) + 1))

    breach_minutes = sum(1 for e in error_rate if e > model.slo.max_error_rate)
    return SimulationResult(
        intervention_ids=[i.id for i in interventions],
        seed=seed,
        series=SimSeries(error_rate=error_rate, pool_wait_ms=pool_wait_ms, inflight=inflight),
        peak_error_rate=max(error_rate, default=0.0),
        breach_minutes=breach_minutes,
        prevented=breach_minutes <= model.slo.max_breach_minutes,
    )


def _pool(available: float, offered: float, hold_s: float, timeout_s: float) -> tuple[float, float]:
    """(share of attempts that time out, mean wait in seconds) for a fractional number of connections."""
    if hold_s <= 0 or offered <= 0:
        return 0.0, 0.0
    patience = timeout_s / hold_s
    whole = math.floor(available)
    share = available - whole
    timed_out, wait = _mmc_timeout(whole, offered, patience)
    if share:
        timed_out_up, wait_up = _mmc_timeout(whole + 1, offered, patience)
        timed_out += share * (timed_out_up - timed_out)
        wait += share * (wait_up - wait)
    return timed_out, wait * hold_s


def _mmc_timeout(c: int, a: float, x: float) -> tuple[float, float]:
    """M/M/c with deterministic patience x: (timeout probability, mean wait), times in units of the hold time.

    With every connection busy, the virtual wait has density a * p * exp(-(c - a) * u) below the patience x,
    where p is the probability that exactly c - 1 connections are busy. Arrivals that would wait longer
    than x leave, so (c - a) may be negative. The k < 0 branch is the same formula scaled by
    exp((c - a) * x) so that it never overflows.
    """
    if c <= 0:
        return 1.0, x
    below = sum(math.exp(n * math.log(a) - math.lgamma(n + 1)) for n in range(c))  # sum of a^n / n!, n < c
    edge = math.exp((c - 1) * math.log(a) - math.lgamma(c))  # a^(c-1) / (c-1)!
    k = c - a
    if abs(k * x) < 1e-6:
        p = edge / (below + edge * a * (x + 1 / c))
        p_late, waited = p, p * a * x * x / 2
    elif k > 0:
        late = math.exp(-k * x)
        p = edge / (below + edge * a * ((1 - late) / k + late / c))
        p_late, waited = p * late, p * a * (1 - late * (1 + k * x)) / k ** 2
    else:
        early = math.exp(k * x)
        p_late = edge / (below * early + edge * a * ((early - 1) / k + 1 / c))
        waited = a * p_late * (early - 1 - k * x) / k ** 2
    timed_out = a / c * p_late
    return timed_out, waited + x * timed_out
