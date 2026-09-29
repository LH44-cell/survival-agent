# Backtest – vilka par och vilken strategi agenterna bör få

Körd 2026-09-29 i Claude Code-miljön. Allt går att återskapa med skripten i `backtest/`
(se [Återskapa](#återskapa)). Genererade tabeller med alla siffror: `backtest/results/summary.md`,
rådata i `backtest/results/*.csv`.

## Sammanfattning

1. **Ge agenterna basnivån: BTC/USD, ETH/USD, SOL/USD** (oförändrat i `config.py`). Lägg inte till
   mellannivån (DOGE, AVAX, LINK, XRP) eller SUI. De ökar drawdown och antal trades utan att
   förbättra resultatet stabilt.
2. **Enda strategin som höll båda åren är ett långsamt trendfilter**: äg ett par (30 % av eget
   kapital) när priset ligger mer än 3 % över sitt 50-dagars glidande medelvärde (SMA), sälj allt när
   det ligger mer än 3 % under. På basnivån gav det **+13,5 % år 1 och +9,0 % år 2** (köp-och-behåll:
   +9,6 % och −29,7 %), max drawdown −36 % och cirka 65 trades på 22 månader. Regeln är positiv båda
   åren för alla sex testade grannparametrar (SMA 30–60 dagar, band 2–5 %).
3. **Allt som handlar dagligen eller oftare dör på avgifterna.** Med 0,4 % taker-avgift per sida
   förlorade snabba regler (SMA 4–8 dygn, 2-dygnsutbrott, SMA-korsning 1/5 dygn) 50–80 % av kapitalet.
   Kostnaderna blev 8–14 USD på 20 USD startkapital.
4. **Walk-forward-valet misslyckades i alla tre nivåerna.** Strategin med bäst Sharpe år 1 förlorade
   år 2 i varje nivå (bas: köp-och-behåll −31,6 %, mellan: SMA-korsning 7/30 dygn −12,9 %, SUI: RSI-dip
   −42,5 %). Två år och en enda björnfas räcker inte för att optimera fram något. Trendregeln
   rekommenderas för att den är billig i avgifter och stabil över parametrar, inte för att den vann ett
   urval.
5. **Compute-kostnaden dominerar.** Med dagens kostnad per varv lever Opus 188 dagar och Fable 57 dagar
   på ren kassa. Ingen strategi förlänger det nämnvärt. Den långsamma trendregeln ger i median 5 dagar
   *kortare* liv än ren kassa för Opus med den rättade `liquidate_if_needed` (16 dagar kortare med
   den gamla, som sålde hela innehav). Playbookens värde är att den hindrar agenten från att överhandla,
   vilket i backtesten kostade 25–40 dagar jämfört med ren kassa.

## Upplägg

| | |
|---|---|
| Data | 2 år timstaplar (OHLCV), 2024-09-29 → 2026-09-29, 17 520 staplar per par |
| Utvärderingsperiod | 2024-11-18 → 2026-09-29 (första 50 dygnen går åt till att bygga upp SMA:erna) |
| År 1 / år 2 | 2024-11-18 → 2025-10-24 (in-sample) / 2025-10-24 → 2026-09-29 (out-of-sample) |
| Beslut | varannan timme (som `RUNS_PER_DAY = 12`), signal på timstängning, fyllning på nästa timmes öppning |
| Agentens hårda regler | max 30 % av eget kapital per köp, en trade per varv, minst 1 USD, bara spot, ingen belåning |
| Avgift | 0,40 % taker per sida (`TAKER_FEE`) |
| Slippage | uppmätt genomsnittlig Kraken-spread per par, halva spreaden per sida (en hel spread per tur-retur). Stresstest med dubbel spread |
| Startkapital | 20 USD |
| Compute | Opus 0,008864 USD/varv, Fable 0,02941 USD/varv (första varvet i `logs/`) |

### Datakällor per par

Bitstamp var primär källa och Coinbase Exchange fallback. **Bitstamp hade full 2-årshistorik för
alla åtta par**, så Coinbase-fallbacken behövde aldrig användas. Täckningen var 100 % (inga saknade
timmar). Källan per par sparas i `backtest/data/sources.json`.

| Nivå | Par | Källa | Timstaplar | Nollvolymstimmar | Årlig volatilitet |
|---|---|---|---|---|---|
| Bas | BTC/USD | Bitstamp | 17 520 | 0,0 % | 45 % |
| Bas | ETH/USD | Bitstamp | 17 520 | 0,0 % | 66 % |
| Bas | SOL/USD | Bitstamp | 17 520 | 0,0 % | 78 % |
| Mellan | DOGE/USD | Bitstamp | 17 520 | 0,0 % | 91 % |
| Mellan | AVAX/USD | Bitstamp | 17 520 | 0,2 % | 88 % |
| Mellan | LINK/USD | Bitstamp | 17 520 | 0,8 % | 89 % |
| Mellan | XRP/USD | Bitstamp | 17 520 | 0,0 % | 85 % |
| Högvolatil | SUI/USD | Bitstamp | 17 520 | 1,2 % | 104 % |

Priserna kommer från Bitstamp medan agenterna handlar på Kraken. För så likvida USD-par är skillnaden i
timstängning försumbar jämfört med avgiften, men den finns.

### Val av högvolatilt par: SUI/USD

Kandidaterna (alla med 2 års historik på Bitstamp och handel på Kraken) jämfördes på
Kraken-volym per dygn den 2026-09-29: **SUI 22,9 M USD**, PEPE 2,4 M, BONK 1,8 M, INJ 1,8 M, FET 1,6 M,
SHIB 1,0 M, WIF 0,6 M. SUI hade klart högst volym och högst realiserad volatilitet i universumet
(104 % per år). Det är just den kombinationen som efterfrågades.

### Spread från Krakens orderbok

60 ögonblicksbilder av toppen av orderboken, var 30:e sekund, 2026-09-29 09:21–09:51 UTC
(`backtest/measure_spreads.py`, resultat i `backtest/data/kraken_spreads.json`).

| Par | Spread medel | Spread median | Tur-retur inkl. avgift |
|---|---|---|---|
| BTC/USD | 0,01 bps | 0,01 bps | 0,80 % |
| ETH/USD | 0,09 bps | 0,04 bps | 0,80 % |
| SOL/USD | 0,88 bps | 0,84 bps | 0,81 % |
| DOGE/USD | 1,01 bps | 0,76 bps | 0,81 % |
| AVAX/USD | 2,97 bps | 2,63 bps | 0,83 % |
| LINK/USD | 2,98 bps | 2,64 bps | 0,83 % |
| XRP/USD | 0,51 bps | 0,46 bps | 0,81 % |
| SUI/USD | 3,45 bps | 3,44 bps | 0,83 % |

Spreaden är liten i förhållande till avgiften på 0,4 % per sida. Dubbel spread ändrar inget resultat
med mer än 1,7 procentenheter, och de flesta med under 0,5. Mätningen gjordes under 30 minuter en lugn tisdagsförmiddag. I stressade
marknader är spreaden bredare, men för ordrar på några dollar spelar djupet i boken ingen roll.

## Resultat per nivå

Median över nivåns par, varje par handlat separat med hela kapitalet. "År 2" är out-of-sample.
Kostnad = avgift + spread i USD. Alla strategier finns i `backtest/strategies.py`. Kortfattat:
`trend_smaN` = äg när priset är över SMA(N timmar) ± band. `cross_a_b` = snabb SMA över långsam.
`donchian_a_b` = köp på a-timmars högsta, sälj på b-timmars lägsta. `rsi_dip` = köp RSI < 30, sälj RSI > 55.

### Bas – BTC, ETH, SOL

| Strategi | År 1 | År 2 | Hela | Max DD | Trades | Kostnad USD |
|---|---|---|---|---|---|---|
| köp och behåll | +22,0 % | −31,6 % | −12,5 % | −68,7 % | 4 | 0,08 |
| donchian 20d/10d | +17,0 % | −8,7 % | +6,8 % | −40,7 % | 74 | 2,38 |
| trend SMA 50d, band 3 % | −6,6 % | +11,7 % | −2,6 % | −38,6 % | 54 | 1,66 |
| trend SMA 17d, band 3 % | +7,9 % | −7,8 % | −4,4 % | −50,5 % | 119 | 3,44 |
| SMA-korsning 7d/30d | −9,9 % | +7,0 % | −17,2 % | −47,7 % | 65 | 2,44 |
| RSI-dip | +9,2 % | −38,6 % | −32,9 % | −50,5 % | 125 | 3,93 |
| trend SMA 8d | −38,2 % | −34,7 % | −59,4 % | −71,5 % | 395 | 7,66 |
| donchian 2d/1d | −55,3 % | −56,3 % | −78,9 % | −80,3 % | 674 | 10,33 |
| **portfölj: trend SMA 50d, 1/3 per par** | **+13,1 %** | **+9,0 %** | **+23,3 %** | **−36,1 %** | 72 | – |
| portfölj: köp och behåll 1/3 per par | +9,6 % | −29,7 % | −20,8 % | −62,8 % | 13 | – |

Per par med trendregeln (hela perioden): BTC −2,6 %, ETH +117,2 %, SOL −14,5 %. Som enskilda par är
utfallet spretigt, men som portfölj jämnas det ut. Portföljen är positiv år 1 och år 2 för varje
testad parameteruppsättning:

| Portfölj bas | SMA 30d | SMA 40d | SMA 50d b2 | SMA 50d b3 | SMA 50d b5 | SMA 60d |
|---|---|---|---|---|---|---|
| År 1 | +10,8 % | +22,8 % | +12,0 % | +13,1 % | +10,1 % | +8,9 % |
| År 2 | +20,5 % | +14,7 % | +6,6 % | +9,0 % | +6,0 % | +14,5 % |
| Max DD | −30,7 % | −32,6 % | −36,4 % | −36,1 % | −39,0 % | −33,3 % |

### Mellan – DOGE, AVAX, LINK, XRP

| Strategi | År 1 | År 2 | Hela | Max DD | Trades | Kostnad USD |
|---|---|---|---|---|---|---|
| köp och behåll | −11,1 % | −40,8 % | −31,1 % | −81,2 % | 4 | 0,08 |
| SMA-korsning 7d/30d (år 1-vinnare) | +30,1 % | −12,9 % | +3,1 % | −59,2 % | 72 | 2,68 |
| donchian 20d/10d | +26,7 % | −9,2 % | +10,5 % | −52,1 % | 72 | 2,65 |
| trend SMA 50d, band 3 % | +12,4 % | +1,6 % | +3,6 % | −62,9 % | 76 | 2,46 |
| RSI-dip | +14,3 % | −9,7 % | +7,6 % | −35,5 % | 118 | 4,08 |
| trend SMA 8d | −17,2 % | −48,4 % | −51,0 % | −80,6 % | 382 | 9,98 |
| donchian 2d/1d | −35,8 % | −55,4 % | −70,2 % | −80,8 % | 664 | 13,93 |
| portfölj: trend SMA 50d, 1/4 per par | +10,0 % | +4,1 % | +14,4 % | −54,6 % | 140 | – |
| portfölj: momentum 30d, veckovis | +38,4 % | +12,5 % | +54,2 % | −52,7 % | 49 | – |
| portfölj: köp och behåll 1/4 per par | +2,4 % | −37,6 % | −33,7 % | −76,1 % | 15 | – |

Den långsamma trendregeln är instabil här. Med SMA 30 dagar blir år 2 −12,7 % och med SMA 60 dagar
blir år 1 −29,8 %. Momentumrotationen såg bra ut, men samma regel gav −40,5 % år 1 på basnivån, så
det är sannolikt tur och inte en egenskap. Drawdowns på 50–60 % med 20 USD i kapital är inte
överlevnadsbara i praktiken.

### Högvolatil – SUI

| Strategi | År 1 | År 2 | Hela | Max DD | Trades | Kostnad USD |
|---|---|---|---|---|---|---|
| köp och behåll | −33,4 % | −54,1 % | −69,2 % | −87,9 % | 4 | 0,08 |
| RSI-dip (år 1-vinnare) | +102,7 % | −42,5 % | +16,6 % | −56,6 % | 119 | 6,35 |
| trend SMA 50d, band 3 % | +9,4 % | +3,1 % | +12,8 % | −59,5 % | 74 | 2,67 |
| donchian 20d/10d | −47,8 % | +3,7 % | −46,5 % | −61,6 % | 70 | 1,44 |
| trend SMA 8d | −72,7 % | −41,4 % | −83,8 % | −84,3 % | 338 | 4,85 |

SUI ger störst utslag åt båda hållen. RSI-dip dubblade kapitalet år 1 och tappade 42 % år 2. Ett par
är för tunt underlag för att lita på något resultat. Att lägga till SUI i en trendportfölj med alla
åtta par sänkte avkastningen (+19,3 % mot +23,3 % för bas) och ökade drawdown (−42 % mot −36 %).

### Parkombinationer (trend SMA 50d, lika vikt)

| Kombination | År 1 | År 2 | Hela | Max DD | Trades |
|---|---|---|---|---|---|
| BTC + ETH | +23,4 % | +18,4 % | +46,1 % | −35,4 % | 65 |
| **bas (BTC, ETH, SOL)** | **+13,1 %** | **+9,0 %** | **+23,3 %** | **−36,1 %** | 72 |
| bas + LINK + XRP | +27,8 % | +12,8 % | +44,2 % | −38,8 % | 137 |
| mellan | +10,0 % | +4,1 % | +14,4 % | −54,6 % | 140 |
| bas + mellan | +12,2 % | +7,0 % | +20,0 % | −42,7 % | 197 |
| alla 8 | +13,9 % | +4,9 % | +19,3 % | −42,0 % | 225 |

BTC + ETH och bas + LINK + XRP ser bättre ut. Men de paren valdes ut *efter* att vi sett vilka som
gick bra, så jämförelsen är inte rättvis. Basnivån definierades i förväg och håller för alla parametrar.

## Överlevnad med compute-kostnad

Compute-kostnaden dras från kassan varje varv. Om kassan blir negativ säljs innehav, som i `agent.py`.

| | Opus | Fable |
|---|---|---|
| Ren kassa (ingen handel) | 188 dagar | 57 dagar |
| Playbook bas, gammal likvidering (säljer hela innehav), median över 31/41 startdatum | 172 dagar | 54 dagar |
| Playbook bas, rättad likvidering (säljer bara underskottet) | 183 dagar (157–240) | 56 dagar (50–66) |
| Snabba strategier (SMA 8d, donchian 2d/1d, korsning 1d/5d), median över par | 147–162 dagar | 53–57 dagar |
| Extra prompt-kostnad för playbook + SMA-rader (≈ 200 tokens, uppskattat) | −15 dagar | −4 dagar |

Överlevnaden simuleras från startdatum var 14:e dag, eftersom en agent bara lever några månader och
ett enda startdatum mest mäter just den marknadsfasen (`backtest/results/playbook_rolling.csv`).

Slutsatsen är obekväm men tydlig. Med 20 USD i kapital ger den bästa handelsregeln kanske 2–3 USD per
år, medan Opus kostar cirka 39 USD per år att köra och Fable cirka 129 USD. **Ingen handelsstrategi
kan betala för tänkandet.** Det som faktiskt påverkar livslängden:

- **Compute-kostnaden per varv**: modell, promptlängd och antal varv per dygn. Varje extra 100 tokens
  i systemprompten kostar Opus cirka 8 dagars liv.
- **Att inte överhandla.** Det är den största risk agenten själv styr över.
- **`liquidate_if_needed` i `agent.py`** sålde tidigare *hela* första innehavet när kassan gick minus
  med några cent. En investerad agent hamnade då i en avgiftsspiral: sälj allt, köp tillbaka, upprepa.
  Fable gjorde 396 trades i stället för 20. **Rättat i samma PR:** funktionen säljer nu bara
  underskottet plus `LIQUIDATION_MARGIN_USD` (0,10 USD), minst 1 USD, från största innehavet. Det ger
  Opus i median 11 dagar längre liv. Backtesten (`engine.run(partial_liquidation=True)`) modellerar
  underskottet med minst 1 USD utan marginalen. Skillnaden är försumbar, eftersom minsta ordern på
  1 USD redan täcker många varv.

## Rekommendation

- **Par:** BTC/USD, ETH/USD, SOL/USD (basnivån, redan i `config.PAIRS`). Mellannivån och SUI
  rekommenderas inte. De har större drawdowns (50–60 %), ger fler trades och parametrarna är instabila.
- **Strategi:** långsamt trendfilter med 50-dagars SMA och 3 % band, 30 % av eget kapital per par,
  minst 10 % kassa, ingen ombalansering. Reglerna står i `strategy.md` och läggs sist i systemprompten
  (`agent.py: system_prompt()`). Agenten får 50-dagars-SMA:n per par i marknadsdatan
  (`broker.fetch_market`, dagliga Kraken-staplar, dagens pågående dygn exkluderat). Den dagliga SMA:n
  ger samma signal som den timbaserade SMA1200 i backtesten 99,7–99,9 % av tiden.
- **Förväntan:** cirka +10 % per år före compute, drawdowns på 25–35 %, ungefär en trade per 10 dagar.
  De flesta varv ska bli hold.

Playbooken är inget sätt att överleva längre än ren kassa. Den är ett räcke mot det som dödar agenter
snabbast: att handla ofta. Vill du maximera livslängden rent mekaniskt är det billigare att inte ha
den alls och låta agenten hålla kassa. Då mäter experimentet dock inte längre handel.

## Begränsningar

- Två år med en tydlig upp-och-ned-cykel. År 2 är en björnfas där köp-och-behåll förlorade på alla
  åtta par. Trendregeln gynnas av sådana perioder. I en sidledes marknad utan trend förlorar den
  långsamt på avgifter.
- Priser från Bitstamp, handel på Kraken.
- Spreaden mättes under 30 minuter, inte över hela perioden.
- Compute-kostnaden kommer från agenternas första varv. Längre historik i prompten gör den högre över tid.
- Agenten är en språkmodell som ska *följa* reglerna. Backtesten visar vad reglerna ger, inte att
  modellen följer dem.

## Återskapa

```bash
pip install -r backtest/requirements.txt
python backtest/fetch_data.py          # 2 år timdata, Bitstamp → Coinbase-fallback  (~2 min)
python backtest/measure_spreads.py     # Kraken-spread, 60 × 30 s                     (~30 min)
python backtest/run_backtest.py        # alla strategier × par × perioder + överlevnad (~6 min)
python backtest/robustness.py          # grannparametrar och parkombinationer         (~2 min)
python backtest/playbook.py            # playbooken exakt som i strategy.md           (~3 min)
python backtest/report.py              # results/summary.md
```

Rådata (`backtest/data/*.csv`) committas inte. `sources.json` och `kraken_spreads.json` committas,
så att resultaten kan knytas till exakt de källor och spreadvärden som användes.
