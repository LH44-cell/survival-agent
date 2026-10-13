# Backtest med olika avgiftsnivåer

Körd 2026-09-29. Samma data, strategier, nivåer av par, walk-forward (år 1 / år 2) och
agentregler som i [BACKTEST.md](BACKTEST.md). Bara avgiften per sida varierar. Spreaden är
fortfarande den uppmätta Kraken-spreaden (0,01–3,5 bps), eftersom den ska hållas lika. Den är ändå
försumbar jämfört med avgifterna. Skript: `backtest/fees.py`, `backtest/capital.py`,
`backtest/venue_check.py`. Rådata: `backtest/results/fees_*.csv`, `capital.csv`, `data/venues.json`.

| Scenario | Avgift per sida | Tur-retur inkl. spread (BTC / SUI) |
|---|---|---|
| Kraken marknadsorder (dagens `TAKER_FEE`) | 0,40 % | 0,80 % / 0,83 % |
| Kraken limitorder | 0,25 % | 0,50 % / 0,53 % |
| MiCA-licensierad börs (Bybit EU, OKX) | 0,10 % | 0,20 % / 0,23 % |
| Hyperliquid spot, taker | 0,07 % | 0,14 % / 0,17 % |
| Hyperliquid spot, maker | 0,04 % | 0,08 % / 0,11 % |

Handelskörningen gjordes dessutom vid 0,20 %, 0,15 %, 0,05 %, 0,02 % och 0 % för att hitta
brytpunkterna. Överlevnaden simuleras på samma sätt som i BACKTEST.md: startdatum var 14:e dag,
compute dras varje varv (Opus 0,008864 USD, Fable 0,02941 USD) och likvideringen är den rättade från
PR #4 (säljer bara underskottet + 0,10 USD).

Motorn i `backtest/engine.py` skrevs om till numpy för att klara cirka 38 000 körningar. Den ger
identiska resultat mot den gamla (största avvikelse 7·10⁻¹⁷). Nya parametrar är `fee`, förberäknade
signaler och `min_order`. Standardvärdena ändrar inget tidigare resultat.

## Kort svar

1. **Snabba strategier börjar inte överleva på någon avgiftsnivå.** Trend på 4–8 dygn,
   SMA-korsning 1/5 dygn, utbrott på 2 dygn och daglig momentumrotation förlorar pengar **även vid
   0 % avgift**. Avgifterna står för 40–75 % av förlusten vid 0,40 %, resten är signaler som inte
   fungerar i den här datan. RSI-dip går plus över hela perioden från cirka 0,15–0,20 % avgift, men
   förlorar år 2 på *varje* avgiftsnivå, även vid 0 %.
2. **Nej, inte robust.** Några strategier har positiv median mot kassa för Opus (basnivåns
   trendregel +6 till +11 dagar, RSI-dip på SUI/mellan +9 till +21 dagar). Men det gäller bara starter
   under första halvåret 2025. Senare starter ger kortare liv än kassa, och ungefär hälften av alla
   starter slår kassa. Skillnaden mellan avgiftsnivåerna är 1–2 dagar för de långsamma reglerna. För
   Fable ligger allt inom ±2 dagar från kassa.
3. **Nej, rekommendationen ändras inte.** Lägre avgift lyfter alla långsamma trendresultat ungefär
   lika mycket och ändrar inte rangordningen. Basnivån (BTC, ETH, SOL) är fortfarande det robusta
   valet. Mellannivån behåller drawdowns runt −50 %. Hyperliquids minsta ordervärde (10 USD) gör det
   dessutom ännu viktigare med få par.

**Rekommendation:** byt inte börs i papperläget nu. Se [sista avsnittet](#rekommendation-byta-börs-i-papperläget).

## 1. När slutar snabba strategier dö på avgifterna?

Median över alla åtta par, hela perioden (2024-11-18 → 2026-09-29), utan compute:

| Strategi | 0,40 % | 0,25 % | 0,20 % | 0,15 % | 0,10 % | 0,07 % | 0,04 % | 0 % |
|---|---|---|---|---|---|---|---|---|
| trend SMA 4 dygn | −72,0 % | −60,8 % | −56,6 % | −52,1 % | −46,4 % | −42,7 % | −38,1 % | −32,7 % |
| trend SMA 8 dygn | −60,1 % | −49,4 % | −45,2 % | −38,9 % | −33,7 % | −30,6 % | −27,4 % | −22,9 % |
| SMA-korsning 1d/5d | −70,8 % | −61,8 % | −58,5 % | −55,0 % | −51,0 % | −48,6 % | −45,6 % | −40,9 % |
| utbrott 2d/1d | −74,1 % | −61,1 % | −55,7 % | −49,4 % | −41,0 % | −34,8 % | −28,6 % | −19,3 % |
| RSI-dip | −10,2 % | −3,0 % | −0,5 % | +2,1 % | +4,8 % | +6,4 % | +8,0 % | +10,3 % |
| *jämförelse:* trend SMA 50d | +5,1 % | +9,2 % | +10,6 % | +12,0 % | +13,4 % | +14,3 % | +15,1 % | +16,3 % |
| *jämförelse:* köp och behåll | −31,8 % | −31,7 % | −31,6 % | −31,6 % | −31,6 % | −31,5 % | −31,5 % | −31,5 % |

Samma strategier uppdelade på år 1 och år 2 (out-of-sample), median över åtta par:

| Strategi | År 1, 0,40 % | År 1, 0,07 % | År 1, 0 % | År 2, 0,40 % | År 2, 0,07 % | År 2, 0 % |
|---|---|---|---|---|---|---|
| trend SMA 4 dygn | −50,4 % | −22,2 % | −14,8 % | −49,1 % | −29,2 % | −23,9 % |
| trend SMA 8 dygn | −39,3 % | −14,9 % | −9,6 % | −38,7 % | −21,3 % | −16,1 % |
| SMA-korsning 1d/5d | −46,7 % | −26,2 % | −20,9 % | −51,9 % | −33,0 % | −28,1 % |
| utbrott 2d/1d | −51,7 % | −21,0 % | −12,0 % | −54,6 % | −23,4 % | −14,5 % |
| RSI-dip | +12,6 % | +22,8 % | +25,0 % | −30,5 % | −24,5 % | −23,2 % |

Momentumrotationen varje dygn (portfölj per nivå) följer samma mönster. På mellannivån vänder hela
perioden till plus från 0,10 % (+2,1 %), men bara tack vare år 1 (+49 %). År 2 är −37 % vid 0,10 %
och −33 % vid 0 %.

Tolkning:

- **Avgiften är inte hela problemet.** Vid Krakens 0,40 % kostar snabb trend 7–12 USD i avgifter på
  20 USD (median per par). Vid Hyperliquid taker sjunker det till 2–4 USD, men strategierna förlorar
  fortfarande 30–50 %. Resten är whipsaw: köp efter uppgång, sälj efter nedgång, upprepa. Med
  timdata och beslut varannan timme finns ingen kant att tjäna in avgiften på.
- **Den enda brytpunkten som finns är RSI-dip vid cirka 0,2 %.** Den ser bra ut år 1 och tappar
  23–31 % år 2 oavsett avgift, positiv på bara 2 av 8 par år 2. Det är en strategi som fungerade i en
  viss marknadsfas, inte en som räddas av låga avgifter.
- Enskilda par kan vända vid mycket låga avgifter (utbrott 2d/1d på SUI blir positivt vid ≤ 0,02 %).
  Med åtta par och fem strategier är det vad slumpen ger.

## 2. Slår någon strategi kassa i livslängd, med compute?

Ren kassa ger Opus 188 dagar och Fable 57 dagar, oberoende av avgift. Tabellen visar medianen av
(dagar i livet − kassans dagar) över par och startdatum. Opus: 27 starter (2024-11-18 → 2025-11-17).
Fable: 36 starter (2024-11-18 → 2026-03-23).

**Opus**

| Strategi | 0,40 % | 0,25 % | 0,10 % | 0,07 % | 0,04 % |
|---|---|---|---|---|---|
| bas: playbook (trend SMA 50d, 30 %/par) | +6,2 | +6,6 | +7,4 | +7,5 | +7,6 |
| bas: trend SMA 50d, 1/3 per par | +9,1 | +9,6 | +10,4 | +10,5 | +10,6 |
| bas: momentumrotation varje dygn | −1,1 | +7,1 | +16,3 | +18,0 | +20,1 |
| mellan: trend SMA 50d, 1/4 per par | −11,8 | −11,1 | −10,1 | −9,9 | −9,8 |
| mellan: momentum 30d, veckovis | +11,7 | +13,1 | +13,8 | +13,8 | +14,0 |
| enskilt par, RSI-dip, SUI | +17,1 | +18,6 | +20,3 | +20,7 | +20,7 |
| enskilt par, RSI-dip, mellan (median) | +9,2 | +10,9 | +12,4 | +12,8 | +13,2 |
| enskilt par, trend SMA 8 dygn, bas (median) | −22,2 | −18,9 | −13,9 | −13,2 | −12,5 |
| köp och behåll, bas | −24,7 | −25,0 | −24,0 | −23,9 | −23,4 |

**Fable:** allt ligger mellan −6 och +2 dagar mot kassa, oavsett avgift. Bäst är RSI-dip på SUI
(+1,4 till +1,9 dagar). Fable lever för kort (57 dagar) för att någon strategi ska hinna betyda något.

Det här ser ut som ett ja, men håller inte för en närmare titt:

- **Allt positivt kommer från tidiga starter.** Playbooken ger +19 dagar för starter före maj 2025
  och −8 dagar för senare starter (Kraken-avgift). Bara 52 % av starterna slår kassa, spridningen är
  −31 till +52 dagar. Momentumrotationen på basnivån: +39 tidigt, −11 sent vid 0,07 %. RSI-dip: +15
  tidigt, +5 sent.
- **Opus starter täcker bara år 1.** En Opus-start behöver cirka 308 dagar framåt, så sista starten är
  2025-11-17. Överlevnadssimuleringen är därför nästan helt in-sample, alltså samma period där RSI-dip
  och momentum såg bra ut. För Fable, vars starter går in i 2026, försvinner fördelen.
- **Samma analys gav −5 dagar för playbooken i BACKTEST.md.** Där var horisonten kortare, vilket gav
  fler sena starter (31 i stället för 27). Att tecknet vänder när man byter ut några startdatum visar
  hur tunt det är.
- **Avgiften betyder lite för överlevnaden.** Playbooken betalar 1,62 USD i avgifter på 22 månader
  hos Kraken och 0,30 USD hos Hyperliquid (taker). Skillnaden på 1,32 USD är 12 dagars Opus-compute
  på 22 månader, alltså cirka 3–4 dagar under ett 188-dagarsliv. Det stämmer med tabellen:
  +6,2 → +7,5.

Svaret är nej. Ingen avgiftsnivå gör att någon strategi robust ger längre liv än kassa. De
strategier som ser bäst ut gör det i samma marknadsfas som de valdes i. Compute-kostnaden är
fortfarande hela spelet: 20 USD, cirka +10 % om året i bästa fall, mot 39 USD om året för Opus.

## 3. Ändras rekommendationen om par?

Trendregeln (SMA 50d, lika vikt), hela perioden, samt max drawdown:

| Kombination | 0,40 % | 0,25 % | 0,10 % | 0,07 % | 0,04 % | Max DD vid 0,07 % |
|---|---|---|---|---|---|---|
| BTC + ETH | +46,1 % | +50,6 % | +56,5 % | +56,0 % | +57,3 % | −33,5 % |
| **bas (BTC, ETH, SOL)** | **+23,3 %** | **+27,1 %** | **+31,0 %** | **+31,8 %** | **+32,6 %** | **−33,9 %** |
| bas + LINK + XRP | +44,2 % | +49,8 % | +55,7 % | +56,9 % | +58,1 % | −36,3 % |
| mellan | +14,4 % | +19,8 % | +23,5 % | +24,7 % | +25,8 % | −50,8 % |
| bas + mellan | +20,0 % | +25,0 % | +30,2 % | +31,3 % | +32,3 % | −39,3 % |
| alla 8 | +19,3 % | +26,3 % | +31,1 % | +32,2 % | +33,3 % | −39,5 % |

Snabb trend (SMA 8d, lika vikt) är negativ över hela perioden i varje kombination och på varje avgiftsnivå, från
−2 % (bas + LINK + XRP, 0,04 %) till −63 % (mellan, 0,40 %).

- **Rangordningen är densamma på alla avgiftsnivåer.** Lägre avgift ger 9–14 procentenheter mer
  över 22 månader för varje kombination, mest för dem med flest par (fler trades). Alla åtta par
  kommer ikapp basnivån i avkastning vid ≤ 0,10 %, men med drawdown på −40 % i stället för −34 %.
- **Mellannivån är fortfarande sämst.** Drawdown runt −50 % oavsett avgift, och parametrarna är lika
  instabila som tidigare.
- **BTC + ETH och bas + LINK + XRP** ser fortfarande bäst ut. De är fortfarande utvalda i efterhand,
  samma förbehåll som i BACKTEST.md.
- **Lägre avgift talar snarare för *färre* par, inte fler.** På Hyperliquid är minsta ordervärde
  10 USD. Med fler par blir varje position mindre och hamnar oftare under gränsen (se nedan).

Rekommendationen står kvar: **BTC, ETH, SOL.**

## Hyperliquid: par, minsta ordervärde, likviditet

**Kunde inte kontrolleras live.** Miljöns nätverkspolicy nekar `api.hyperliquid.xyz` (403 vid
CONNECT), liksom `api.bybit.com` och `www.okx.com`. `backtest/venue_check.py` är skrivet för att göra
jämförelsen via ccxt:s publika endpoints (listade par, minsta order, 24h-volym, spread, djup inom
±0,5 %). Kör det när värdena är öppnade:

```bash
python backtest/venue_check.py --venues kraken hyperliquid
```

Det som följer om Hyperliquid kommer från deras dokumentation (inte verifierat i dag) och ska läsas
som antaganden:

- **Spot kvoteras i USDC, inte USD.** BTC, ETH och SOL finns som överbryggade tokens (UBTC, UETH,
  USOL). Om DOGE, AVAX, LINK, XRP och SUI finns som *spot* är osäkert. De finns som perpetuals, men
  det är en annan produkt (belåning, funding) som agenterna inte får använda.
- **Minsta ordervärde 10 USD** per order, både köp och sälj.
- **Likviditet:** spotböckerna för de överbryggade tokens är tunnare än Krakens. Det spelar ingen
  roll för ordrar på några dollar, men går inte att kvantifiera härifrån.

Som jämförelse har Kraken (uppmätt 2026-09-29, `data/venues.json`):

| Par | 24h-volym | Spread | Djup ±0,5 % | Minsta order (`ordermin` × pris) |
|---|---|---|---|---|
| BTC/USD | 202 M USD | 0,01 bps | 7,8 M USD | 4,20 USD |
| ETH/USD | 99 M USD | 0,04 bps | 3,3 M USD | 2,72 USD |
| SOL/USD | 38 M USD | 0,84 bps | 4,0 M USD | **7,16 USD** |
| DOGE/USD | 6 M USD | 1,09 bps | 0,6 M USD | 4,75 USD |
| AVAX/USD | 13 M USD | 0,87 bps | 0,4 M USD | 5,78 USD |
| LINK/USD | 32 M USD | 2,00 bps | 0,5 M USD | **8,43 USD** |
| XRP/USD | 68 M USD | 0,93 bps | 1,0 M USD | 2,49 USD |
| SUI/USD | 22 M USD | 3,43 bps | 0,4 M USD | 5,82 USD |

### Minsta ordervärde är redan ett problem på Kraken

`config.MIN_TRADE_USD = 1.0` stämmer inte med Kraken. Kraken har en minsta ordervolym per par
(`ordermin`) som motsvarar 2,50–8,40 USD i dag. Med 20 USD och högst 30 % per köp (6 USD) går
**SOL och LINK inte att köpa alls i live-läge**. Den rättade likvideringen säljer minst 1 USD, vilket
också ligger under `ordermin` för alla par. Papperläget kontrollerar inget av detta, så
papperresultaten är något för optimistiska jämfört med vad som går att göra live. Ingen kod ändras i
den här omgången, men det bör fixas innan `PAPER_MODE = False`.

### Hur stort startkapital behövs?

Basnivån, hela perioden, utan compute, med verkliga minsta order: Kraken per par enligt tabellen,
Hyperliquid 10 USD. "Fritt" betyder samma körning utan minsta order.

| Startkapital | Kraken playbook | Kraken trades | Hyperliquid playbook | Hyperliquid trades |
|---|---|---|---|---|
| 20 USD | +22,0 % (fritt +23,8 %) | 45 av 65, SOL köps aldrig | **±0 % (fritt +32,1 %)** | **0 av 65**, 6 USD < 10 USD |
| 35 USD | +23,8 % | 65 av 65 | **−21,2 %** | 16 av 65, positioner fastnar |
| 50 USD | +23,8 % | 65 av 65 | +32,1 % | 65 av 65 |
| 100 USD | +23,8 % | 65 av 65 | +32,1 % | 65 av 65 |

Med 35 USD på Hyperliquid blir det sämre än att inte handla alls. Efter en nedgång är positionen
under 10 USD och kan varken säljas eller fyllas på, så agenten sitter fast i en fallande position.

Praktiskt minimum:

- **Kraken:** cirka **35 USD** för playbooken (30 % ≥ SOL:s 7,16 USD även efter en viss nedgång).
  Säkrare med **50 USD** så att tvångsförsäljningar också klarar `ordermin`.
- **Hyperliquid:** minst **50 USD**, i praktiken **100 USD**. 30 % av kapitalet ska ligga över
  10 USD även efter en drawdown på 35–50 % och efter att compute ätit av kassan.

Större kapital ändrar också experimentet. Med 100 USD i stället för 20 lever Opus cirka 940 dagar på
ren kassa i stället för 188, och Fable cirka 280 i stället för 57. Då blir handelsresultatet en
större del av överlevnaden.

## Rekommendation: byta börs i papperläget?

**Nej, stanna på Kraken i papperläget.** Motivering:

1. **Vinsten är liten.** Med playbooken, som agenterna nu har, ger Hyperliquid +32 % i stället för
   +24 % över 22 månader. Det är cirka 1,60 USD på 20 USD, eller 3–4 dagar av ett Opus-liv. Den
   lägre avgiften räddar inte de snabba strategierna, så den öppnar inga nya möjligheter.
2. **Med 20 USD går det inte att handla på Hyperliquid.** 30 % av 20 USD är 6 USD, under minsta
   ordern på 10 USD. Ett papperläge med Hyperliquids avgift men utan dess minsta order vore en
   simulering av något som inte finns. Med minsta ordern på plats skulle agenterna inte kunna handla
   alls.
3. **Experimentet har redan börjat.** Agenterna har fått "fees about 0.4%" i systemprompten och en
   playbook kalibrerad på 0,40 %. Att byta avgift nu gör första och andra halvan av körningen
   ojämförbara.
4. **Hyperliquid är en annan sorts plats.** On-chain, USDC i stället för USD, egen plånbok, inte
   MiCA-licensierad och ingen SEPA-insättning. Det ändrar steg 3 i README (riktiga pengar) mer än det
   ändrar papperläget.

Om ni ändå vill ha lägre avgift är ordningen:

- **Samma börs, limitorder (0,25 %):** den minsta ändringen. Ingen ny minsta order, samma priser,
  +27 % i stället för +24 % för playbooken. Kräver att `broker.py` lägger limitorder som kan bli
  ofyllda. Det är en kodändring, inte bara en avgiftsparameter, och ingår inte här.
- **MiCA-licensierad börs (0,10 %):** ger nästan hela avgiftsvinsten (+31 %). Den är reglerad i EU
  och har EUR-insättning. Värd att utreda inför riktiga pengar, men minsta ordervärden och vilka par
  som finns kunde inte kontrolleras härifrån, eftersom Bybit och OKX blockeras av nätverkspolicyn.
- **Hyperliquid:** bara om startkapitalet höjs till minst 100 USD, och då som ett nytt experiment,
  inte ett byte mitt i det pågående.

Det som påverkar livslängden mer än börsen:

- compute-kostnaden per varv
- startkapitalet
- att agenterna inte överhandlar

Före live-läge bör `MIN_TRADE_USD` ersättas med Krakens `ordermin` per par och kapitalet höjas till
minst 35–50 USD.

## Begränsningar

- Samma två år och samma björnfas i år 2 som i BACKTEST.md.
- Spreaden hålls på Krakens nivå för alla scenarier ("allt annat lika"). Maker-scenariona (Kraken
  limit, Hyperliquid maker) räknar dessutom med att alla limitorder fylls. I verkligheten fylls de
  inte alltid, så de är övre gränser.
- Överlevnaden för Opus bygger på starter under 2024-11 → 2025-11 och är nästan helt in-sample.
- Uppgifterna om Hyperliquid, Bybit och OKX är inte verifierade live (nätverkspolicy).
- Kapitalanalysen gäller basnivån utan compute. Minsta order för Kraken bygger på dagens priser.
  `ordermin` är i basvaluta, så USD-värdet rör sig med priset.

## Återskapa

```bash
pip install -r backtest/requirements.txt
python backtest/fetch_data.py && python backtest/measure_spreads.py   # om data saknas
python backtest/venue_check.py    # Kraken (+ Hyperliquid om värden är nåbar) → data/venues.json
python backtest/fees.py           # ~3 min på 4 kärnor → results/fees_*.csv
python backtest/capital.py        # → results/capital.csv
```
