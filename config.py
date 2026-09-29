"""Central konfiguration. Ändra här, inte i agent.py."""

# Läge: True = simulerade fyllningar på riktiga priser. False = riktiga ordrar på Kraken.
PAPER_MODE = True

START_CAPITAL = 20.0          # USD, agentens hela värld
QUOTE = "USD"                 # byt till "EUR" om du sätter in euro via SEPA
PAIRS = ["BTC/USD", "ETH/USD", "SOL/USD"]

# Riskfilter (hårda gränser i kod, kan inte kringgås av modellen)
MAX_TRADE_FRACTION = 0.30     # max 30 % av eget kapital i en enskild trade
MIN_TRADE_USD = 1.0           # Krakens minsta ordervärde är ca 1 USD
MAX_TRADES_PER_RUN = 1
TAKER_FEE = 0.004             # Kraken Pro takeravgift 0,40 %
PAPER_SLIPPAGE = 0.0005       # 0,05 % extra slippage i simuleringen

# Fast "serverkostnad" per körning som dras utöver tokenkostnaden (USD). 0 = av.
FIXED_COST_PER_RUN = 0.0

# Agenter som körs. Priser i USD per miljon tokens (input, output).
# OBS: verifiera priserna mot https://www.anthropic.com/pricing innan start.
AGENTS = {
    "haiku": {
        "model": "claude-haiku-4-5-20251001",
        "price_in": 1.00,
        "price_out": 5.00,
    },
    "fable": {
        "model": "claude-fable-5-1",
        "price_in": 15.00,   # PLACEHOLDER – uppdatera
        "price_out": 75.00,  # PLACEHOLDER – uppdatera
    },
}

RUNS_PER_DAY = 24             # används bara för att beräkna "förväntad livslängd"
OHLCV_TIMEFRAME = "1h"
OHLCV_BARS = 48
