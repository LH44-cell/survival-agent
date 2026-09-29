"""Simulator som följer exakt samma spelregler som agenterna:

* beslut varannan timme (RUNS_PER_DAY = 12), signal på stängningskursen,
  fyllning på nästa timmes öppningskurs
* högst en trade per varv, köp högst MAX_TRADE_FRACTION av eget kapital,
  inget under MIN_TRADE_USD
* avgift per sida (standard TAKER_FEE, kan sättas med fee=)
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
        rebalance_band=REBALANCE_BAND, partial_liquidation=False, fee=None, signals=None,
        liquidation_margin=0.0, min_order=None):
    """opens/closes: DataFrame (index = timme, kolumn = par). Returnerar (equity_series, stats).
    burn = compute-kostnad i USD som dras från kassan varje varv (0 = ren handelsbacktest).
    max_exposure skalar ned målvikterna så att en kassabuffert för compute-kostnaden finns kvar.
    partial_liquidation=False säljer hela innehav när kassan går minus (agent.py före PR #4);
    True säljer bara underskottet + liquidation_margin (minst MIN_TRADE_USD) från största innehavet.
    fee = avgift per sida (standard config.TAKER_FEE).
    signals = förberäknade målvikter (samma form som closes); annars räknas strategy(closes).
    min_order = minsta ordervärde i USD, ett tal eller dict par -> USD (standard MIN_TRADE_USD).
    stats["blocked"] räknar varv där en önskad trade stoppades av minsta ordervärde.
    Indikatorerna är kausala, så att räkna dem på hela serien ger samma värden som t.o.m. varje t."""
    fee = config.TAKER_FEE if fee is None else fee
    pairs = list(closes.columns)
    n = len(pairs)
    idx = closes.index
    lo = idx.searchsorted(start) if start is not None else 0
    hi = idx.searchsorted(end) if end is not None else len(idx)
    lo = max(lo, warmup)
    half = np.array([spreads[p] * slippage_mult / 2 for p in pairs])
    C = closes.to_numpy(dtype=float)
    O = opens[pairs].to_numpy(dtype=float)
    if signals is None:
        signals = strategy(closes.iloc[:hi])
    W = signals[pairs].to_numpy(dtype=float) * max_exposure
    max_frac = config.MAX_TRADE_FRACTION
    if min_order is None:
        min_order = config.MIN_TRADE_USD
    minv = np.array([min_order[p] if isinstance(min_order, dict) else min_order for p in pairs], dtype=float)
    blocked = 0

    cash, pos = float(start_equity), np.zeros(n)
    trades, costs = 0, 0.0
    in_mkt_cycles = cycles = 0
    died = None
    eq_i, eq_v = [], []

    for i in range(lo, hi - 1, CYCLE_HOURS):
        px_mark = C[i]
        if burn:
            cash -= burn
            order = np.argsort(-pos * px_mark) if partial_liquidation else range(n)
            for q in order:
                if cash >= 0:
                    break
                if pos[q] > 0:
                    px = O[i + 1, q] * (1 - half[q])
                    net = px * (1 - fee)
                    base = pos[q]
                    if partial_liquidation:
                        base = min(pos[q], max(-cash + liquidation_margin, minv[q]) / net)
                        if (pos[q] - base) * px < minv[q]:
                            base = pos[q]
                    cash += base * net
                    pos[q] -= base
                    trades += 1
        vals = pos * px_mark
        equity = cash + vals.sum()
        if equity <= 0:
            died = idx[i]
            eq_i.append(i)
            eq_v.append(0.0)
            break
        eq_i.append(i)
        eq_v.append(equity)
        cycles += 1
        if (vals > minv).any():
            in_mkt_cycles += 1

        target = W[i]
        devs = target * equity - vals
        p = int(np.argmax(np.abs(devs)))
        dev = devs[p]
        if abs(dev) < max(minv[p], rebalance_band * equity):
            # en helt stängd position ska alltid kunna säljas ut även om den är liten
            if not (target[p] == 0 and vals[p] >= minv[p]):
                if abs(dev) >= rebalance_band * equity and abs(dev) >= config.MIN_TRADE_USD:
                    blocked += 1  # önskad trade, men under minsta ordervärde
                continue
            dev = -vals[p]

        fill_open = O[i + 1, p]
        if dev > 0:  # köp
            amt = min(dev, equity * max_frac, cash)
            if amt < minv[p]:
                if min(dev, equity * max_frac) >= minv[p] or amt >= config.MIN_TRADE_USD:
                    blocked += 1
                continue
            px = fill_open * (1 + half[p])
            f = amt * fee
            pos[p] += (amt - f) / px
            cash -= amt
            costs += f + (amt - f) * (px / fill_open - 1)
        else:  # sälj
            base = pos[p] if target[p] == 0 else min(pos[p], -dev / px_mark[p])
            if base * fill_open < minv[p]:
                blocked += 1
                continue
            px = fill_open * (1 - half[p])
            gross = base * px
            f = gross * fee
            cash += gross - f
            pos[p] -= base
            if pos[p] * px < 1e-9:
                pos[p] = 0.0
            costs += f + base * (fill_open - px)
        trades += 1

    if died is None:
        eq_i.append(hi - 1)
        eq_v.append(cash + (pos * C[hi - 1]).sum())
    eq = pd.Series(eq_v, index=idx[eq_i])
    stats = summarize(eq, start_equity, trades, costs, in_mkt_cycles / max(cycles, 1))
    stats["died"] = died
    stats["blocked"] = blocked
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
