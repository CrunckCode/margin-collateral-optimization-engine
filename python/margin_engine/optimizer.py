"""Linear program: cheapest eligible collateral that covers each counterparty's initial margin."""
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import linprog

from . import config as C


@dataclass
class Allocation:
    success: bool
    message: str
    cost: float
    table: pd.DataFrame
    shadow_price_a: float
    shadow_price_b: float
    requirement: dict


def optimize(inventory, im_a, im_b):
    """Minimize sum(opportunity cost * market value posted) subject to post-haircut coverage of each IM."""
    n = len(inventory)
    cost = inventory[C.OPP_COST_COL].to_numpy() / 1e4
    keep = 1.0 - inventory[C.HAIRCUT_COL].to_numpy()
    mv = inventory[C.MARKET_VALUE_COL].to_numpy()

    c = np.concatenate([cost, cost])
    a_ub = [np.concatenate([-keep, np.zeros(n)]), np.concatenate([np.zeros(n), -keep])]
    b_ub = [-im_a, -im_b]
    for i in range(n):
        row = np.zeros(2 * n)
        row[i] = row[n + i] = 1.0
        a_ub.append(row)
        b_ub.append(mv[i])

    bounds = [(0, mv[i] if inventory[C.ELIG_A_COL].iloc[i] else 0) for i in range(n)]
    bounds += [(0, mv[i] if inventory[C.ELIG_B_COL].iloc[i] else 0) for i in range(n)]
    res = linprog(c, A_ub=np.array(a_ub), b_ub=np.array(b_ub), bounds=bounds, method="highs")

    requirement = {"A": im_a, "B": im_b}
    if not res.success:
        empty = inventory[[C.ASSET_COL]].copy()
        return Allocation(False, res.message, float("nan"), empty, float("nan"), float("nan"), requirement)

    table = inventory[[C.ASSET_COL, C.MARKET_VALUE_COL, C.HAIRCUT_COL, C.OPP_COST_COL]].copy()
    table["to_A"] = res.x[:n]
    table["to_B"] = res.x[n:]
    table["posted"] = table["to_A"] + table["to_B"]
    table["annual_cost"] = table["posted"] * table[C.OPP_COST_COL] / 1e4
    marginals = res.ineqlin.marginals
    return Allocation(True, res.message, float(res.fun), table, float(-marginals[0]), float(-marginals[1]), requirement)


def naive_cash_cost(im_a, im_b, cash_opp_cost_bps=None):
    """Post exactly the IM in cash (0 percent haircut) and pay the funding rate on it."""
    bps = C.CASH_OPPORTUNITY_COST_BPS if cash_opp_cost_bps is None else cash_opp_cost_bps
    return (im_a + im_b) * bps / 1e4


def cheapest_first_greedy(inventory, im, eligible_col):
    """Benchmark: fill one counterparty with the lowest cost-per-unit-of-coverage asset first (ignores sharing)."""
    inv = inventory.copy()
    inv["unit_cost"] = inv[C.OPP_COST_COL] / (1.0 - inv[C.HAIRCUT_COL])
    need, cost = im, 0.0
    for _, row in inv[inv[eligible_col]].sort_values("unit_cost").iterrows():
        take_cov = min(need, row[C.POST_VALUE_COL])
        cost += take_cov / (1.0 - row[C.HAIRCUT_COL]) * row[C.OPP_COST_COL] / 1e4
        need -= take_cov
        if need <= 1e-9:
            break
    return cost, need
