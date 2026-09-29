"""Simulator som följer exakt samma spelregler som agenterna:

* beslut varannan timme (RUNS_PER_DAY = 12), signal på stängningskursen,
  fyllning på nästa timmes öppningskurs
* högst en trade per varv, köp högst MAX_TRADE_FRACTION av eget kapital,
  inget under MIN_TRADE_USD
* TAKER_FEE per sida
* slippage = halva den uppmätta genomsnittliga Kraken-spreaden per sida
  (köp på mitt + spread/2, sälj på mitt - spread/2), dvs en hel spread per tur-retur.
  slippage_mult skalar detta för stresstest.

En strategi är en funktion (closes: DataFrame upp till och med nu) -> dict par -> målvikt
(0..1, summa <= 1). Motorn flyttar portföljen mot målet, en trade per varv.
"""

import math

import numpy as np
import pandas as pd

import common  # noqa: F401  (lägger repo-roten på sys.path)
import config

CYCLE_HOURS = 24 // config.RUNS_PER_DAY
REBALANCE_BAND = 0.05  # handla inte om avvikelsen från målet är < 5 % av eget kapital


def run(opens, closes, strategy, spreads, start_equity=config.START_CAPITAL,
        slippage_mult=1.0, start=None, end=None, warmup=0, burn=0.0, max_exposure=1.0,
        rebalance_band=REBALANCE_BAND, partial_liquidation=False):
    """opens/closes: DataFrame (index = timme, kolumn = par). Returnerar (equity_series, stats).
    burn = compute-kostnad i USD som dras från kassan varje varv (0 = ren handelsbacktest).
    max_exposure skalar ned målvikterna så att en kassabuffert för compute-kostnaden finns kvar.
    partial_liquidation=False säljer hela innehav när kassan går minus (som agent.py gör i dag);
    True säljer bara det som behövs från största innehavet."""
    pairs = list(closes.columns)
    idx = closes.index
    lo = idx.searchsorted(start) if start is not None else 0
    hi = idx.searchsorted(end) if end is not None else len(idx)
    lo = max(lo, warmup)
    half = {p: spreads[p] * slippage_mult / 2 for p in pairs}

    cash, pos = float(start_equity), {p: 0.0 for p in pairs}
    trades, costs = 0, 0.0
    in_mkt_cycles = cycles = 0
    died = None
    eq_t, eq_v = [], []
    signals = strategy(closes.iloc[:hi])  # DataFrame med målvikter per timme, räknad kausalt

    for i in range(lo, hi - 1, CYCLE_HOURS):
        px_mark = closes.iloc[i]
        if burn:
            cash -= burn
            # samma som agent.liquidate_if_needed: sälj hela innehav tills kassan täcker
            for q in sorted(pairs, key=lambda k: -pos[k] * px_mark[k]) if partial_liquidation else pairs:
                if cash >= 0:
                    break
                if pos[q] > 0:
                    px = opens.iloc[i + 1][q] * (1 - half[q])
                    net = px * (1 - config.TAKER_FEE)
                    base = pos[q]
                    if partial_liquidation:
                        # minst MIN_TRADE_USD, annars bara underskottet
                        base = min(pos[q], max(-cash, config.MIN_TRADE_USD) / net)
                    cash += base * net
                    pos[q] -= base
                    trades += 1
        equity = cash + sum(pos[p] * px_mark[p] for p in pairs)
        if equity <= 0:
            died = idx[i]
            eq_t.append(idx[i])
            eq_v.append(0.0)
            break
        eq_t.append(idx[i])
        eq_v.append(equity)
        cycles += 1
        if any(pos[p] * px_mark[p] > config.MIN_TRADE_USD for p in pairs):
            in_mkt_cycles += 1

        target = signals.iloc[i] * max_exposure
        # största avvikelse från målet i USD
        devs = {p: target[p] * equity - pos[p] * px_mark[p] for p in pairs}
        p = max(devs, key=lambda k: abs(devs[k]))
        dev = devs[p]
        if abs(dev) < max(config.MIN_TRADE_USD, rebalance_band * equity):
            # en helt stängd position ska alltid kunna säljas ut även om den är liten
            if not (target[p] == 0 and pos[p] * px_mark[p] >= config.MIN_TRADE_USD):
                continue
            dev = -pos[p] * px_mark[p]

        fill_open = opens.iloc[i + 1][p]
        if dev > 0:  # köp
            amt = min(dev, equity * config.MAX_TRADE_FRACTION, cash)
            if amt < config.MIN_TRADE_USD:
                continue
            px = fill_open * (1 + half[p])
            fee = amt * config.TAKER_FEE
            pos[p] += (amt - fee) / px
            cash -= amt
            costs += fee + (amt - fee) * (px / fill_open - 1)
        else:  # sälj
            base = pos[p] if target[p] == 0 else min(pos[p], -dev / px_mark[p])
            if base * fill_open < config.MIN_TRADE_USD:
                continue
            px = fill_open * (1 - half[p])
            gross = base * px
            fee = gross * config.TAKER_FEE
            cash += gross - fee
            pos[p] -= base
            if pos[p] * px < 1e-9:
                pos[p] = 0.0
            costs += fee + base * (fill_open - px)
        trades += 1

    if died is None:
        final_px = closes.iloc[hi - 1]
        eq_t.append(idx[hi - 1])
        eq_v.append(cash + sum(pos[p] * final_px[p] for p in pairs))
    eq = pd.Series(eq_v, index=eq_t)
    stats = summarize(eq, start_equity, trades, costs, in_mkt_cycles / max(cycles, 1))
    stats["died"] = died
    return eq, stats


def summarize(eq, start_equity, trades, costs, exposure):
    rets = eq.pct_change().dropna()
    years = (eq.index[-1] - eq.index[0]).total_seconds() / (365 * 86400)
    per_year = config.RUNS_PER_DAY * 365
    sharpe = rets.mean() / rets.std() * math.sqrt(per_year) if rets.std() > 0 else 0.0
    dd = (eq / eq.cummax() - 1).min()
    return {
        "final": eq.iloc[-1],
        "ret": eq.iloc[-1] / start_equity - 1,
        "cagr": (eq.iloc[-1] / start_equity) ** (1 / years) - 1 if years > 0 else 0.0,
        "maxdd": dd,
        "sharpe": sharpe,
        "trades": trades,
        "costs": costs,
        "exposure": exposure,
    }


# ---------- indikatorer (kausala: värdet vid t använder bara data t.o.m. t) ----------

def sma(s, n):
    return s.rolling(n, min_periods=n).mean()


def rsi(s, n):
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)


def hysteresis(enter, exit_):
    """Tillståndsmaskin: 1 efter enter, 0 efter exit, annars behåll."""
    state = pd.Series(np.nan, index=enter.index)
    state[enter] = 1.0
    state[exit_ & ~enter] = 0.0
    return state.ffill().fillna(0.0)
