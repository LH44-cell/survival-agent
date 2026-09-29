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
    "opus": {
        "model": "claude-opus-5-5",
        "price_in": 4.00,
        "price_out": 20.00,
    },
    "fable": {
        "model": "claude-fable-5-1",
        "price_in": 10.00,
        "price_out": 50.00,
    },
}

RUNS_PER_DAY = 12             # används bara för att beräkna "förväntad livslängd"
OHLCV_TIMEFRAME = "1h"
OHLCV_BARS = 48
