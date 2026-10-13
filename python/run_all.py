"""Run the full pipeline: IM, optimization, scenarios, figures, CSV outputs."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from margin_engine import analytics, config as C
from margin_engine.collateral import build_inventory
from margin_engine.optimizer import cheapest_first_greedy, naive_cash_cost, optimize
from margin_engine.simm_style import headline_im, structured_im


def main():
    C.OUTPUT_DIR.mkdir(exist_ok=True)
    C.FIGURE_DIR.mkdir(exist_ok=True)
    plt.rcParams.update({"font.size": 10, "axes.grid": True, "grid.alpha": 0.3})

    im = headline_im()
    names = list(im)
    im_a, im_b = im[names[0]]["im"], im[names[1]]["im"]
    total_im = im_a + im_b
    inventory = build_inventory()
    alloc = optimize(inventory, im_a, im_b)
    naive = naive_cash_cost(im_a, im_b)
    greedy_a, _ = cheapest_first_greedy(inventory, im_a, C.ELIG_A_COL)
    greedy_b, _ = cheapest_first_greedy(inventory, im_b, C.ELIG_B_COL)
    struct = structured_im()

    summary = {
        "im_a": im_a, "im_b": im_b, "total_im": total_im,
        "naive_cost": naive, "optimized_cost": alloc.cost,
        "saving": naive - alloc.cost, "saving_pct": 1 - alloc.cost / naive,
        "shadow_price_a": alloc.shadow_price_a, "shadow_price_b": alloc.shadow_price_b,
        "greedy_independent_lower_bound": greedy_a + greedy_b,
        "structured_im_a": struct[names[0]]["im"], "structured_im_b": struct[names[1]]["im"],
        "structured_total_im": sum(v["im"] for v in struct.values()),
        "cash_bug": analytics.cash_bug_demo(im_a, im_b),
    }
    (C.OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2))
    alloc.table.to_csv(C.OUTPUT_DIR / "allocation.csv", index=False)
    analytics.funding_sweep(im_a, im_b).to_csv(C.OUTPUT_DIR / "scenario_funding_sweep.csv", index=False)
    analytics.haircut_stress(im_a, im_b).to_csv(C.OUTPUT_DIR / "scenario_haircut_stress.csv", index=False)
    analytics.im_scaling(im_a, im_b).to_csv(C.OUTPUT_DIR / "scenario_im_scaling.csv", index=False)
    analytics.treasury_scarcity(im_a, im_b).to_csv(C.OUTPUT_DIR / "scenario_treasury_scarcity.csv", index=False)
    analytics.eligibility_cases(im_a, im_b).to_csv(C.OUTPUT_DIR / "scenario_eligibility.csv", index=False)

    # Figure 1: IM by risk class
    fig, ax = plt.subplots(figsize=(7, 4))
    classes = ["equity", "fx", "rate"]
    width = 0.35
    for k, nm in enumerate(names):
        ax.bar([x + k * width for x in range(3)], [im[nm]["weighted"][c] / 1e6 for c in classes], width, label=nm)
    ax.set_xticks([x + width / 2 for x in range(3)])
    ax.set_xticklabels(classes)
    ax.set_ylabel("Weighted sensitivity (USD million)")
    ax.set_title("Risk-weighted sensitivities by class")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(C.FIGURE_DIR / "fig_im_by_class.png", dpi=180)
    plt.close(fig)

    # Figure 2: allocation
    t = alloc.table[alloc.table["posted"] > 1000]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(t[C.ASSET_COL], t["to_A"] / 1e6, label="To Counterparty A")
    ax.bar(t[C.ASSET_COL], t["to_B"] / 1e6, bottom=t["to_A"] / 1e6, label="To Counterparty B")
    ax.set_ylabel("Market value posted (USD million)")
    ax.set_title("Optimized collateral allocation")
    ax.legend(fontsize=8)
    plt.setp(ax.get_xticklabels(), rotation=15)
    fig.tight_layout()
    fig.savefig(C.FIGURE_DIR / "fig_allocation.png", dpi=180)
    plt.close(fig)

    # Figure 3: saving versus cash funding cost
    sweep = analytics.funding_sweep(im_a, im_b)
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(sweep["cash_cost_bps"], sweep["naive_cost"] / 1e3, marker="o", label="Cash-only")
    ax.plot(sweep["cash_cost_bps"], sweep["optimized_cost"] / 1e3, marker="o", label="Optimized")
    ax.set_xlabel("Cash funding cost (bps)")
    ax.set_ylabel("Annual opportunity cost (USD thousand)")
    ax.set_title("Cost of posting collateral versus the funding rate")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(C.FIGURE_DIR / "fig_funding_sweep.png", dpi=180)
    plt.close(fig)

    # Figure 4: IM scaling, cost and shadow price
    sc = analytics.im_scaling(im_a, im_b)
    ok = sc[sc["feasible"]]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(ok["total_im"] / 1e6, ok["optimized_cost"] / 1e3, marker="o")
    ax.set_xlabel("Total initial margin (USD million)")
    ax.set_ylabel("Optimized annual cost (USD thousand)")
    ax.set_title("Cost rises faster as cheap collateral runs out")
    fig.tight_layout()
    fig.savefig(C.FIGURE_DIR / "fig_im_scaling.png", dpi=180)
    plt.close(fig)

    print(json.dumps({k: v for k, v in summary.items() if k != "cash_bug"}, indent=2))
    print("cash bug demo:", summary["cash_bug"])
    assert abs(total_im - C.EXPECTED_TOTAL_IM) < C.IM_TOLERANCE, total_im
    assert round(naive) == C.EXPECTED_NAIVE_COST, naive
    assert round(alloc.cost) == C.EXPECTED_OPTIMIZED_COST, alloc.cost
    print("headline checks passed")


if __name__ == "__main__":
    main()
