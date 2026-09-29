"""Exekveringslager. PaperBroker simulerar fyllningar på riktiga priser,
KrakenBroker skickar riktiga ordrar. Resten av systemet ser ingen skillnad."""

import os
import time
import ccxt
import config


def market_client():
    """Publik klient för prisdata – kräver ingen API-nyckel."""
    return ccxt.kraken({"enableRateLimit": True})


def fetch_market(client):
    """Hämtar ticker + senaste OHLCV-staplar för alla par."""
    market = {}
    for pair in config.PAIRS:
        t = client.fetch_ticker(pair)
        bars = client.fetch_ohlcv(pair, config.OHLCV_TIMEFRAME, limit=config.OHLCV_BARS)
        closes = [b[4] for b in bars]
        market[pair] = {
            "bid": t["bid"],
            "ask": t["ask"],
            "last": t["last"],
            "change_24h_pct": t.get("percentage"),
            "high_24h": t.get("high"),
            "low_24h": t.get("low"),
            "closes": closes,
        }
    return market


class PaperBroker:
    """Simulerar fyllningar med avgift + slippage. Rör aldrig riktiga pengar."""

    def __init__(self, market):
        self.market = market

    def buy(self, pair, quote_amount):
        px = self.market[pair]["ask"] * (1 + config.PAPER_SLIPPAGE)
        fee = quote_amount * config.TAKER_FEE
        base_amount = (quote_amount - fee) / px
        return {"pair": pair, "side": "buy", "price": px, "base": base_amount,
                "quote": quote_amount, "fee": fee, "ts": time.time(), "paper": True}

    def sell(self, pair, base_amount):
        px = self.market[pair]["bid"] * (1 - config.PAPER_SLIPPAGE)
        gross = base_amount * px
        fee = gross * config.TAKER_FEE
        return {"pair": pair, "side": "sell", "price": px, "base": base_amount,
                "quote": gross - fee, "fee": fee, "ts": time.time(), "paper": True}


class KrakenBroker:
    """Riktiga ordrar. API-nyckeln ska ENDAST ha rättigheten 'Create & modify orders'
    (plus 'Query funds'). Aldrig uttag. Detta lager är inte testat mot riktiga pengar –
    kör med ett par dollar först."""

    def __init__(self, market):
        self.market = market
        self.client = ccxt.kraken({
            "apiKey": os.environ["KRAKEN_API_KEY"],
            "secret": os.environ["KRAKEN_API_SECRET"],
            "enableRateLimit": True,
        })

    def buy(self, pair, quote_amount):
        base_amount = quote_amount / self.market[pair]["ask"]
        order = self.client.create_order(pair, "market", "buy", base_amount)
        return self._normalize(order, pair, "buy")

    def sell(self, pair, base_amount):
        order = self.client.create_order(pair, "market", "sell", base_amount)
        return self._normalize(order, pair, "sell")

    def _normalize(self, order, pair, side):
        # Kraken fyller marknadsordrar direkt; hämta slutlig info
        o = self.client.fetch_order(order["id"], pair)
        fee = (o.get("fee") or {}).get("cost", 0.0) or 0.0
        return {"pair": pair, "side": side, "price": o.get("average") or o.get("price"),
                "base": o.get("filled"), "quote": o.get("cost"), "fee": fee,
                "ts": time.time(), "paper": False, "order_id": o.get("id")}
