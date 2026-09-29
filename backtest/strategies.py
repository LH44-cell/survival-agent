"""Regelbaserade strategier som en agent kan följa med den data den ser i prompten
(timstängningar, bid/ask, 24h-förändring). Varje strategi tar closes (DataFrame,
timindex, en kolumn per par) och returnerar målvikter med samma form.

Enkelpar-strategierna ger vikt 1 per kolumn och körs ett par i taget.
Nivå-strategierna (TIER_STRATEGIES) fördelar kapitalet över alla par i nivån.
"""

import pandas as pd

from engine import hysteresis, rsi, sma


def cash(c):
    return c * 0.0


def buy_hold(c):
    return c * 0.0 + 1.0


def trend_sma(n, band=0.01):
    """Lång när priset ligger > band över SMA(n timmar), ut när det faller > band under."""
    def f(c):
        out = {}
        for p in c:
            m = sma(c[p], n)
            out[p] = hysteresis(c[p] > m * (1 + band), c[p] < m * (1 - band))
        return pd.DataFrame(out)
    f.__name__ = f"trend_sma{n}" + (f"_b{band * 100:.0f}" if band != 0.01 else "")
    return f


def sma_cross(fast, slow):
    def f(c):
        return pd.DataFrame({p: (sma(c[p], fast) > sma(c[p], slow)).astype(float) for p in c})
    f.__name__ = f"cross_{fast}_{slow}"
    return f


def donchian(entry, exit_):
    """Köp på utbrott över högsta stängning senaste `entry` timmar, sälj under lägsta senaste `exit_`."""
    def f(c):
        out = {}
        for p in c:
            hi = c[p].rolling(entry).max().shift(1)
            lo = c[p].rolling(exit_).min().shift(1)
            out[p] = hysteresis(c[p] > hi, c[p] < lo)
        return pd.DataFrame(out)
    f.__name__ = f"donchian_{entry}_{exit_}"
    return f


def rsi_dip(n=28, lo=30, hi=55, trend_n=None):
    """Köp översålt (RSI < lo), sälj när RSI > hi. Med trend_n bara köp över SMA(trend_n)."""
    def f(c):
        out = {}
        for p in c:
            r = rsi(c[p], n)
            enter = r < lo
            if trend_n:
                enter &= c[p] > sma(c[p], trend_n)
            out[p] = hysteresis(enter, r > hi)
        return pd.DataFrame(out)
    f.__name__ = f"rsi_dip{'_trend' + str(trend_n) if trend_n else ''}"
    return f


def ew_trend(n, band=0.03):
    """Lika vikt 1/antal par, varje par bara när det ligger över SMA(n)."""
    single = trend_sma(n, band)

    def f(c):
        return single(c) / c.shape[1]
    f.__name__ = f"ew_trend_sma{n}"
    return f


def momentum_rotation(lookback=168, trend_n=400, every=24):
    """En gång per dygn: allt i paret med högst avkastning senaste `lookback` timmar,
    om den är positiv och paret ligger över SMA(trend_n). Annars kontanter."""
    def f(c):
        mom = c / c.shift(lookback) - 1
        ok = (mom > 0) & (c > c.apply(lambda s: sma(s, trend_n)))
        score = mom.where(ok)
        w = pd.DataFrame(0.0, index=c.index, columns=c.columns)
        best = score.fillna(float("-inf")).idxmax(axis=1)
        any_ok = ok.any(axis=1)
        for p in c:
            w[p] = ((best == p) & any_ok).astype(float)
        # uppdatera bara en gång per dygn, håll vikterna mellan
        keep = pd.Series(range(len(c)), index=c.index) % every == 0
        return w.where(keep, other=float("nan")).ffill().fillna(0.0)
    f.__name__ = f"momentum_{lookback}_{every}"
    return f


SINGLE_STRATEGIES = [
    cash,
    buy_hold,
    # snabba varianter (timmar–dagar)
    trend_sma(100),
    trend_sma(200),
    sma_cross(24, 120),
    donchian(48, 24),
    rsi_dip(),
    rsi_dip(trend_n=400),
    # långsamma varianter (veckor), bredare band för färre affärer
    trend_sma(400, band=0.03),
    trend_sma(1200, band=0.03),
    sma_cross(168, 720),
    donchian(480, 240),
]

TIER_STRATEGIES = [
    cash,
    buy_hold,   # lika vikt, köp och behåll
    ew_trend(200),
    ew_trend(1200),
    momentum_rotation(),
    momentum_rotation(lookback=720, trend_n=1200, every=168),
]
