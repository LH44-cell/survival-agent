"""Simulerar playbooken i strategy.md så som agenten ska följa den:
BTC/ETH/SOL, målvikt 30 % av eget kapital per par när trenden är upp
(pris > 50-dagars SMA + 3 %), sälj hela innehavet när pris < SMA - 3 %,
ingen ombalansering däremellan. Med och utan compute-kostnad.
Skriver results/playbook.csv.

    python backtest/playbook.py
"""

import json
import os

import pandas as pd

from common import DATA_DIR, RESULTS_DIR, TIERS
import engine  # noqa: E402
from run_backtest import BURN, WARMUP, load  # noqa: E402
from strategies import cash, trend_sma  # noqa: E402

PAIRS = TIERS["bas"]
WEIGHT = 0.30
NO_REBALANCE = 0.25  # justera bara när avvikelsen är > 25 % av eget kapital, dvs i praktiken in/ut


def playbook(c):
    return trend_sma(1200, band=0.03)(c) * WEIGHT


def main():
    opens, closes = load()
    spreads = {p: v["mean_spread"] for p, v in
               json.load(open(os.path.join(DATA_DIR, "kraken_spreads.json")))["pairs"].items()}
    o, c = opens[PAIRS], closes[PAIRS]
    t0 = c.index[WARMUP]
    split = t0 + (c.index[-1] - t0) / 2
    rows = []
    for label, strat in (("playbook", playbook), ("cash", cash)):
        for per, (a, b) in {"ar1": (t0, split), "ar2": (split, None), "hela": (t0, None)}.items():
            for agent, burn in {"ingen": 0.0, **BURN}.items():
                for mult, partial in ((1, False), (2, False), (1, True)):
                    if (mult == 2 and (burn or label == "cash")) or (partial and not burn):
                        continue
                    eq, st = engine.run(o, c, strat, spreads, start=a, end=b, warmup=WARMUP, burn=burn,
                                        slippage_mult=mult, rebalance_band=NO_REBALANCE,
                                        partial_liquidation=partial)
                    days = ((st["died"] or eq.index[-1]) - eq.index[0]).days
                    rows.append({"strategy": label, "period": per, "burn": agent, "spread_mult": mult,
                                 "partial_liquidation": partial,
                                 "ret": st["ret"], "maxdd": st["maxdd"], "trades": st["trades"],
                                 "costs": st["costs"], "exposure": st["exposure"], "days_alive": days,
                                 "died": str(st["died"]) if st["died"] is not None else ""})
                    print(f"{label:9} {per:5} burn={agent:6} spread×{mult} {'delsälj' if partial else 'helsälj'} ret {st['ret']:+.1%} "
                          f"DD {st['maxdd']:+.1%} trades {st['trades']} kostn {st['costs']:.2f} "
                          f"exp {st['exposure']:.0%} dagar {days}{' DÖD' if st['died'] is not None else ''}")
    pd.DataFrame(rows).to_csv(os.path.join(RESULTS_DIR, "playbook.csv"), index=False)



def rolling_survival(step_days=14):
    """Överlevnad från många startdatum: agenter lever bara månader, så ett enda startdatum
    säger mest om just den marknadsfasen. Skriver results/playbook_rolling.csv."""
    opens, closes = load()
    spreads = {p: v["mean_spread"] for p, v in
               json.load(open(os.path.join(DATA_DIR, "kraken_spreads.json")))["pairs"].items()}
    o, c = opens[PAIRS], closes[PAIRS]
    rows = []
    for agent, burn in BURN.items():
        horizon = pd.Timedelta(days=int(20 / (burn * 12)) + 60)  # kassalivslängd + marginal
        start = c.index[WARMUP]
        while start + horizon <= c.index[-1]:
            end = start + horizon
            for partial in (False, True):
                eq, st = engine.run(o, c, playbook, spreads, start=start, end=end, warmup=WARMUP, burn=burn,
                                    rebalance_band=NO_REBALANCE, partial_liquidation=partial)
                days = ((st["died"] or eq.index[-1]) - eq.index[0]).total_seconds() / 86400
                rows.append({"agent": agent, "start": str(start)[:10], "partial_liquidation": partial,
                             "days_alive": days, "trades": st["trades"]})
            start += pd.Timedelta(days=step_days)
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(RESULTS_DIR, "playbook_rolling.csv"), index=False)
    cash_days = {a: 20 / (b * 12) for a, b in BURN.items()}
    for (agent, partial), g in df.groupby(["agent", "partial_liquidation"]):
        d = g.days_alive - cash_days[agent]
        print(f"{agent:6} {'delsälj' if partial else 'helsälj'}: {len(g)} starter, kassa {cash_days[agent]:.0f} d, "
              f"playbook median {g.days_alive.median():.0f} d (min {g.days_alive.min():.0f}, max {g.days_alive.max():.0f}), "
              f"längre än kassa i {(d > 0).mean():.0%}, medianskillnad {d.median():+.0f} d")


if __name__ == "__main__":
    main()
    rolling_survival()
