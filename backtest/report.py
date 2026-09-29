"""Sammanställer results/all_runs.csv + survival.csv till results/summary.md.

    python backtest/report.py
"""

import json
import os

import pandas as pd

from common import DATA_DIR, RESULTS_DIR, TIERS

TIER_NAMES = {"bas": "Bas", "mellan": "Mellan", "hogvolatil": "Högvolatil"}


def pct(x):
    return f"{x * 100:+.1f} %"


def table(df, cols, headers):
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(f(r[c]) if callable(f) else str(r[c]) for c, f in cols) + " |")
    return "\n".join(lines)


def main():
    df = pd.read_csv(os.path.join(RESULTS_DIR, "all_runs.csv"))
    surv = pd.read_csv(os.path.join(RESULTS_DIR, "survival.csv"))
    meta = json.load(open(os.path.join(RESULTS_DIR, "meta.json")))
    sources = json.load(open(os.path.join(DATA_DIR, "sources.json")))
    spreads = json.load(open(os.path.join(DATA_DIR, "kraken_spreads.json")))

    single = df[(df.scope != "portfölj") & ~df.stress]
    stress = df[(df.scope != "portfölj") & df.stress]
    out = ["# Backtest – genererad sammanfattning\n",
           f"Period: {meta['start'][:10]} → {meta['end'][:10]}, delning år 1 / år 2 vid {meta['split'][:10]}.\n"]

    out.append("## Datakällor och spread\n")
    rows = []
    for tier, pairs in TIERS.items():
        for p in pairs:
            s, sp = sources[p], spreads["pairs"][p]
            rows.append({"tier": TIER_NAMES[tier], "pair": p, "src": s["source"], "bars": s["bars"],
                         "mean": sp["mean_spread"] * 1e4, "median": sp["median_spread"] * 1e4,
                         "rt": (sp["mean_spread"] + 2 * meta["fee"]) * 100})
    out.append(table(pd.DataFrame(rows),
                     [("tier", str), ("pair", str), ("src", str), ("bars", str),
                      ("mean", lambda x: f"{x:.2f}"), ("median", lambda x: f"{x:.2f}"), ("rt", lambda x: f"{x:.2f} %")],
                     ["Nivå", "Par", "Källa", "Timstaplar", "Spread medel (bps)", "Spread median (bps)",
                      "Tur-retur-kostnad"]))
    out.append(f"\nSpread uppmätt {spreads['measured_from']} → {spreads['measured_to']}, "
               f"{spreads['samples']} ögonblicksbilder.\n")

    # ---- per nivå: median över nivåns par ----
    selected = {}
    for tier, pairs in TIERS.items():
        t = single[single.tier == tier]
        agg = []
        for strat, g in t.groupby("strategy"):
            y1, y2, full = (g[g.period == k].set_index("scope") for k in ("ar1", "ar2", "hela"))
            st = stress[(stress.tier == tier) & (stress.strategy == strat)]
            agg.append({"strategy": strat,
                        "y1": y1.ret.median(), "y1_sharpe": y1.sharpe.median(),
                        "y2": y2.ret.median(), "y2_pos": int((y2.ret > 0).sum()),
                        "full": full.ret.median(), "dd": full.maxdd.median(),
                        "trades": full.trades.median(), "costs": full.costs.median(),
                        "stress": st.ret.median()})
        agg = pd.DataFrame(agg).sort_values("y1_sharpe", ascending=False)
        best = agg.iloc[0].strategy
        selected[tier] = best
        n = len(pairs)
        out.append(f"## {TIER_NAMES[tier]} ({', '.join(pairs)}) – median över paren\n")
        out.append(table(agg,
                         [("strategy", str), ("y1", pct), ("y1_sharpe", lambda x: f"{x:.2f}"), ("y2", pct),
                          ("y2_pos", lambda x: f"{x}/{n}"), ("full", pct), ("dd", pct),
                          ("trades", lambda x: f"{x:.0f}"), ("costs", lambda x: f"{x:.2f}"), ("stress", pct)],
                         ["Strategi", "År 1", "Sharpe år 1", "År 2 (OOS)", "Par + år 2", "Hela", "Max DD",
                          "Trades", "Kostnad USD", "Hela, 2× spread"]))
        out.append(f"\nVald på år 1 (högst median-Sharpe): **{best}**\n")

        port = df[(df.tier == tier) & (df.scope == "portfölj")]
        if len(port):
            p = port.pivot_table(index="strategy", columns="period", values=["ret", "maxdd", "trades"])
            prow = []
            for strat in p.index:
                prow.append({"strategy": strat, "y1": p.loc[strat, ("ret", "ar1")], "y2": p.loc[strat, ("ret", "ar2")],
                             "full": p.loc[strat, ("ret", "hela")], "dd": p.loc[strat, ("maxdd", "hela")],
                             "trades": p.loc[strat, ("trades", "hela")]})
            out.append("Portfölj över hela nivån:\n")
            out.append(table(pd.DataFrame(prow),
                             [("strategy", str), ("y1", pct), ("y2", pct), ("full", pct), ("dd", pct),
                              ("trades", lambda x: f"{x:.0f}")],
                             ["Strategi", "År 1", "År 2", "Hela", "Max DD", "Trades"]))
            out.append("")

    # ---- per par ----
    out.append("## Per par (hela perioden, samt år 2)\n")
    rows = []
    for tier, pairs in TIERS.items():
        for p in pairs:
            g = single[single.scope == p]
            full, y2 = g[g.period == "hela"].set_index("strategy"), g[g.period == "ar2"].set_index("strategy")
            best = full.drop(index=["cash"]).ret.idxmax()
            sel = selected[tier]
            rows.append({"tier": TIER_NAMES[tier], "pair": p,
                         "bh": full.loc["buy_hold", "ret"], "bh_dd": full.loc["buy_hold", "maxdd"],
                         "sel": sel, "sel_full": full.loc[sel, "ret"], "sel_y2": y2.loc[sel, "ret"],
                         "slow": full.loc["trend_sma1200_b3", "ret"], "slow_y2": y2.loc["trend_sma1200_b3", "ret"],
                         "best": best, "best_ret": full.loc[best, "ret"]})
    out.append(table(pd.DataFrame(rows),
                     [("tier", str), ("pair", str), ("bh", pct), ("bh_dd", pct), ("sel", str), ("sel_full", pct),
                      ("sel_y2", pct), ("slow", pct), ("slow_y2", pct), ("best", str), ("best_ret", pct)],
                     ["Nivå", "Par", "Köp&behåll", "K&B max DD", "Nivåns val", "Val hela", "Val år 2",
                      "SMA1200 hela", "SMA1200 år 2", "Bästa i efterhand", "Bästa avk."]))

    # ---- överlevnad ----
    out.append("\n## Överlevnad med compute-kostnad (hela perioden, 90 % max investerat)\n")
    s = surv.pivot_table(index=["agent", "strategy"], values="days_alive", aggfunc=["median", "min", "max"])
    s.columns = ["median", "min", "max"]
    s = s.reset_index()
    out.append(table(s, [("agent", str), ("strategy", str), ("median", lambda x: f"{x:.0f}"),
                         ("min", lambda x: f"{x:.0f}"), ("max", lambda x: f"{x:.0f}")],
                     ["Agent", "Strategi", "Dagar i livet (median över par)", "Min", "Max"]))
    out.append(f"\nCompute per varv: {meta['burn']}\n")

    with open(os.path.join(RESULTS_DIR, "summary.md"), "w") as f:
        f.write("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
