import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from margin_engine import analytics, config as C
from margin_engine.collateral import build_inventory
from margin_engine.optimizer import naive_cash_cost, optimize
from margin_engine.simm_style import aggregate, compute_im_v1, headline_im, structured_im

IM = headline_im()
NAMES = list(IM)
IM_A, IM_B = IM[NAMES[0]]["im"], IM[NAMES[1]]["im"]


def test_aggregate_two_classes_matches_hand_formula():
    got = aggregate({"a": 3.0, "b": 4.0}, 0.0)
    assert abs(got - 5.0) < 1e-12
    got = aggregate({"a": 3.0, "b": 4.0}, 1.0)
    assert abs(got - 7.0) < 1e-12


def test_im_is_between_root_sum_squares_and_simple_sum():
    deltas = {"equity": 1e6, "fx": 2e6, "rate": 3e6}
    im, weighted = compute_im_v1(deltas)
    v = list(weighted.values())
    assert np.sqrt(sum(x * x for x in v)) <= im <= sum(v)


def test_headline_total_im_matches_pinned_value():
    assert abs(IM_A + IM_B - C.EXPECTED_TOTAL_IM) < C.IM_TOLERANCE


def test_headline_costs_match_pinned_values():
    alloc = optimize(build_inventory(), IM_A, IM_B)
    assert alloc.success
    assert round(alloc.cost) == C.EXPECTED_OPTIMIZED_COST
    assert round(naive_cash_cost(IM_A, IM_B)) == C.EXPECTED_NAIVE_COST


def test_allocation_covers_each_im_after_haircuts():
    alloc = optimize(build_inventory(), IM_A, IM_B)
    keep = 1 - alloc.table[C.HAIRCUT_COL]
    assert (alloc.table["to_A"] * keep).sum() >= IM_A - 1
    assert (alloc.table["to_B"] * keep).sum() >= IM_B - 1


def test_allocation_respects_inventory_and_eligibility():
    inv = build_inventory()
    alloc = optimize(inv, IM_A, IM_B)
    assert (alloc.table["posted"] <= inv[C.MARKET_VALUE_COL] + 1e-6).all()
    inelig_b = inv[~inv[C.ELIG_B_COL]].index
    assert (alloc.table.loc[inelig_b, "to_B"] < 1e-6).all()
    inelig_a = inv[~inv[C.ELIG_A_COL]].index
    assert (alloc.table.loc[inelig_a, "to_A"] < 1e-6).all()


def test_optimizer_beats_random_feasible_allocations():
    inv = build_inventory()
    best = optimize(inv, IM_A, IM_B).cost
    rng = np.random.default_rng(7)
    keep = (1 - inv[C.HAIRCUT_COL]).to_numpy()
    mv = inv[C.MARKET_VALUE_COL].to_numpy()
    cost = inv[C.OPP_COST_COL].to_numpy() / 1e4
    tested = 0
    elig_a = inv[C.ELIG_A_COL].to_numpy()
    elig_b = inv[C.ELIG_B_COL].to_numpy()
    for _ in range(20000):
        post_a = np.zeros(len(inv))
        post_b = np.zeros(len(inv))
        post_a[elig_a] = rng.dirichlet(np.ones(elig_a.sum())) * IM_A * 1.02 / keep[elig_a]
        post_b[elig_b] = rng.dirichlet(np.ones(elig_b.sum())) * IM_B * 1.02 / keep[elig_b]
        if ((post_a + post_b) <= mv).all() and (post_a * keep).sum() >= IM_A and (post_b * keep).sum() >= IM_B:
            tested += 1
            assert ((post_a + post_b) * cost).sum() >= best - 1e-6
    assert tested > 100


def test_zero_cash_cost_bug_is_detectable():
    demo = analytics.cash_bug_demo(IM_A, IM_B)
    assert demo["cash_posted"] == C.COLLATERAL_ROWS[0]["market_value"]  # entire cash line is used first
    assert demo["cost"] < optimize(build_inventory(), IM_A, IM_B).cost  # a fake saving


def test_shadow_price_matches_marginal_asset_unit_cost():
    alloc = optimize(build_inventory(), IM_A, IM_B)
    assert abs(alloc.shadow_price_a - 0.0025 / 0.98) < 1e-9


def test_higher_haircuts_never_lower_cost():
    df = analytics.haircut_stress(IM_A, IM_B)
    assert df["optimized_cost"].is_monotonic_increasing


def test_infeasible_when_im_exceeds_eligible_inventory():
    alloc = optimize(build_inventory(), IM_A * 20, IM_B * 20)
    assert not alloc.success


def test_structured_cross_check_is_lower_than_headline():
    s = structured_im()
    assert sum(v["im"] for v in s.values()) < IM_A + IM_B
