"""Kör hela backtesten och skriver results/*.csv + results/summary.md.

    python backtest/fetch_data.py        # en gång
    python backtest/measure_spreads.py   # en gång (≈30 min)
    python backtest/run_backtest.py

Perioder: år 1 (in-sample, används för att välja strategi) och år 2 (out-of-sample,
används för att bedöma den). Val sker på median-Sharpe år 1 per nivå; år 2 redovisas
oförändrat.
"""

import json
import os

import pandas as pd

from common import DATA_DIR, RESULTS_DIR, TIERS, data_path  # först: lägger repo-roten på sys.path
import config  # noqa: E402
import engine  # noqa: E402
from strategies import SINGLE_STRATEGIES, TIER_STRATEGIES

WARMUP = 1200  # timmar (50 dygn), så att SMA1200 m.fl. är definierade från start
CASH_BUFFER = 0.9  # i överlevnadskörningen: max 90 % investerat, resten täcker compute
BURN = {"opus": 0.008864, "fable": 0.02941}  # USD per varv, uppmätt i logs/ 2026-09-29


def load():
    opens, closes = {}, {}
    for pairs in TIERS.values():
        for p in pairs:
            d = pd.read_csv(data_path(p))
            d.index = pd.to_datetime(d.ts, unit="ms", utc=True)
            opens[p], closes[p] = d.open, d.close
    return pd.DataFrame(opens).ffill(), pd.DataFrame(closes).ffill()


def normalized(strategy):
    def f(c):
        w = strategy(c)
        s = w.sum(axis=1).clip(lower=1.0)
        return w.div(s, axis=0)
    f.__name__ = strategy.__name__
    return f


def fmt_pct(x):
    return f"{x * 100:+.1f} %"


def main():
    opens, closes = load()
    with open(os.path.join(DATA_DIR, "kraken_spreads.json")) as f:
        spreads = {p: v["mean_spread"] for p, v in json.load(f)["pairs"].items()}

    t0 = closes.index[WARMUP]
    split = t0 + (closes.index[-1] - t0) / 2
    periods = {"ar1": (t0, split), "ar2": (split, None), "hela": (t0, None)}

    rows = []

    def record(tier, scope, strat, period, stats, stress=False):
        rows.append({"tier": tier, "scope": scope, "strategy": strat.__name__,
                     "period": period, "stress": stress, **stats})

    for tier, pairs in TIERS.items():
        for p in pairs:
            for strat in SINGLE_STRATEGIES:
                for per, (a, b) in periods.items():
                    _, st = engine.run(opens[[p]], closes[[p]], strat, spreads, start=a, end=b, warmup=WARMUP)
                    record(tier, p, strat, per, st)
                _, st = engine.run(opens[[p]], closes[[p]], strat, spreads, start=t0, warmup=WARMUP, slippage_mult=2)
                record(tier, p, strat, "hela", st, stress=True)
        if len(pairs) > 1:
            for strat in TIER_STRATEGIES:
                s = normalized(strat)
                for per, (a, b) in periods.items():
                    _, st = engine.run(opens[pairs], closes[pairs], s, spreads, start=a, end=b, warmup=WARMUP)
                    record(tier, "portfölj", s, per, st)

    df = pd.DataFrame(rows)
    os.makedirs(RESULTS_DIR, exist_ok=True)
    df.to_csv(os.path.join(RESULTS_DIR, "all_runs.csv"), index=False)

    # ---- överlevnad med compute-kostnad ----
    surv = []
    for agent, burn in BURN.items():
        for tier, pairs in TIERS.items():
            for p in pairs:
                for strat in SINGLE_STRATEGIES:
                    eq, st = engine.run(opens[[p]], closes[[p]], strat, spreads, start=t0, warmup=WARMUP, burn=burn,
                                           max_exposure=CASH_BUFFER)
                    life = ((st["died"] or eq.index[-1]) - t0).days
                    surv.append({"agent": agent, "tier": tier, "pair": p, "strategy": strat.__name__,
                                 "days_alive": life, "died": st["died"] is not None, "final": st["final"]})
    pd.DataFrame(surv).to_csv(os.path.join(RESULTS_DIR, "survival.csv"), index=False)

    with open(os.path.join(RESULTS_DIR, "meta.json"), "w") as f:
        json.dump({"start": str(t0), "split": str(split), "end": str(closes.index[-1]),
                   "fee": config.TAKER_FEE, "spreads": spreads, "burn": BURN}, f, indent=2)
    print(f"klar: {len(df)} körningar, perioder {t0} / {split} / {closes.index[-1]}")


if __name__ == "__main__":
    main()
