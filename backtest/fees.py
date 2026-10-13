"""Samma backtest som run_backtest.py/robustness.py/playbook.py men över flera avgiftsnivåer,
allt annat lika (Kraken-spread, agentens regler, walk-forward år 1 / år 2, compute-kostnad).

    python backtest/fees.py

Skriver results/fees_trading.csv (utan compute), results/fees_combos.csv (parkombinationer)
och results/fees_survival.csv.gz (överlevnad från rullande startdatum, Opus och Fable).
"""

import json
import os
from multiprocessing import Pool

import pandas as pd

from common import DATA_DIR, RESULTS_DIR, TIERS
import config  # noqa: E402
import engine  # noqa: E402
from robustness import COMBOS  # noqa: E402
from run_backtest import BURN, CASH_BUFFER, WARMUP, load, normalized  # noqa: E402
from strategies import SINGLE_STRATEGIES, TIER_STRATEGIES, buy_hold, ew_trend, trend_sma  # noqa: E402

# avgift per sida
SCENARIOS = {
    "kraken_market": 0.0040,
    "kraken_limit": 0.0025,
    "mica_cex": 0.0010,
    "hl_taker": 0.0007,
    "hl_maker": 0.0004,
}
# extra nivåer bara för handelskörningen, för att hitta brytpunkter
EXTRA_FEES = {"fee_0.20": 0.0020, "fee_0.15": 0.0015, "fee_0.05": 0.0005, "fee_0.02": 0.0002, "noll": 0.0}

STEP_DAYS = 14
LIQ_MARGIN = 0.10  # samma som config.LIQUIDATION_MARGIN_USD efter PR #4

_G = {}


def _init():
    _G["cfgs"] = configs()
    opens, closes = load()
    spreads = {p: v["mean_spread"] for p, v in
               json.load(open(os.path.join(DATA_DIR, "kraken_spreads.json")))["pairs"].items()}
    t0 = closes.index[WARMUP]
    split = t0 + (closes.index[-1] - t0) / 2
    _G.update(opens=opens, closes=closes, spreads=spreads, t0=t0, split=split,
              periods={"ar1": (t0, split), "ar2": (split, None), "hela": (t0, None)})


def playbook(c):
    return trend_sma(1200, band=0.03)(c) * 0.30


def configs():
    """(tier, scope, namn, par, strategi, max_exposure i överlevnad, rebalance_band)"""
    out = []
    for tier, pairs in TIERS.items():
        for p in pairs:
            for s in SINGLE_STRATEGIES:
                out.append((tier, p, s.__name__, [p], s, CASH_BUFFER, engine.REBALANCE_BAND))
        if len(pairs) > 1:
            for s in TIER_STRATEGIES:
                out.append((tier, "portfölj", s.__name__, pairs, normalized(s), CASH_BUFFER, engine.REBALANCE_BAND))
    out.append(("bas", "portfölj", "playbook", TIERS["bas"], playbook, 1.0, 0.25))
    return out


def _signals(pairs, strat):
    key = (tuple(pairs), strat.__name__, id(strat))
    if key not in _G.setdefault("sig", {}):
        _G["sig"][key] = strat(_G["closes"][pairs])
    return _G["sig"][key]


def trading_job(k):
    tier, scope, name, pairs, strat, _, band = _G["cfgs"][k]
    o, c = _G["opens"][pairs], _G["closes"][pairs]
    sig = _signals(pairs, strat)
    rows = []
    for scen, fee in {**SCENARIOS, **EXTRA_FEES}.items():
        for per, (a, b) in _G["periods"].items():
            _, st = engine.run(o, c, None, _G["spreads"], start=a, end=b, warmup=WARMUP, fee=fee,
                               signals=sig, rebalance_band=band)
            rows.append({"tier": tier, "scope": scope, "strategy": name, "scenario": scen, "fee": fee,
                         "period": per, **{k: v for k, v in st.items() if k != "died"}})
    return rows


def combo_job(item):
    name, pairs = item
    o, c = _G["opens"][pairs], _G["closes"][pairs]
    rows = []
    for label, strat in (("buy_hold", normalized(buy_hold)), ("ew_trend_sma1200", normalized(ew_trend(1200))),
                         ("ew_trend_sma200", normalized(ew_trend(200, 0.01)))):
        sig = strat(c)
        for scen, fee in SCENARIOS.items():
            for per, (a, b) in _G["periods"].items():
                _, st = engine.run(o, c, None, _G["spreads"], start=a, end=b, warmup=WARMUP, fee=fee, signals=sig)
                rows.append({"combo": name, "strategy": label, "scenario": scen, "fee": fee, "period": per,
                             **{k: v for k, v in st.items() if k != "died"}})
    return rows


def survival_job(k):
    tier, scope, name, pairs, strat, max_exp, band = _G["cfgs"][k]
    o, c = _G["opens"][pairs], _G["closes"][pairs]
    sig = _signals(pairs, strat)
    rows = []
    for agent, burn in BURN.items():
        cash_days = config.START_CAPITAL / (burn * config.RUNS_PER_DAY)
        horizon = pd.Timedelta(days=int(cash_days) + 120)
        start = _G["t0"]
        while start + horizon <= c.index[-1]:
            for scen, fee in SCENARIOS.items():
                eq, st = engine.run(o, c, None, _G["spreads"], start=start, end=start + horizon, warmup=WARMUP,
                                    fee=fee, signals=sig, burn=burn, max_exposure=max_exp, rebalance_band=band,
                                    partial_liquidation=True, liquidation_margin=LIQ_MARGIN)
                days = ((st["died"] or eq.index[-1]) - eq.index[0]).total_seconds() / 86400
                rows.append({"tier": tier, "scope": scope, "strategy": name, "agent": agent, "scenario": scen,
                             "fee": fee, "start": str(start)[:10], "days_alive": days,
                             "censored": st["died"] is None, "cash_days": cash_days, "trades": st["trades"]})
            start += pd.Timedelta(days=STEP_DAYS)
    return rows


def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    cfgs = range(len(configs()))  # strategierna är closures: skicka index, bygg om i varje process
    with Pool(os.cpu_count(), initializer=_init) as pool:
        trading = [r for rows in pool.map(trading_job, cfgs) for r in rows]
        pd.DataFrame(trading).to_csv(os.path.join(RESULTS_DIR, "fees_trading.csv"), index=False)
        print(f"handel: {len(trading)} körningar")
        combos = [r for rows in pool.map(combo_job, list(COMBOS.items())) for r in rows]
        pd.DataFrame(combos).to_csv(os.path.join(RESULTS_DIR, "fees_combos.csv"), index=False)
        print(f"kombinationer: {len(combos)} körningar")
        surv = [r for rows in pool.map(survival_job, cfgs, chunksize=1) for r in rows]
        pd.DataFrame(surv).to_csv(os.path.join(RESULTS_DIR, "fees_survival.csv.gz"), index=False)
        print(f"överlevnad: {len(surv)} körningar")


if __name__ == "__main__":
    main()
