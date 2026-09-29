# Survival Agent – AI-agenter som måste tradea för att överleva

Två Claude-modeller (Haiku 4.5 och Fable 5.1) får 20 USD var. Varje timme fattar de ett
handelsbeslut på riktiga Kraken-priser, och kostnaden för deras eget tänkande dras från
plånboken. Når eget kapital noll stängs de av för gott. Modellerna vet inte att det är simulerat.

## Filer
| Fil | Vad |
|---|---|
| `config.py` | Alla inställningar: läge, kapital, par, riskgränser, modeller och tokenpriser |
| `agent.py` | Ett varv i agentens liv (prompt → beslut → risk → exekvering → kostnad → spara) |
| `broker.py` | Prisdata + PaperBroker (simulering) / KrakenBroker (riktiga ordrar) |
| `risk.py` | Hårda regler i kod. `KILL_SWITCH`-fil i mappen stoppar all handel |
| `status.py` | Snabb översikt över alla agenter |
| `tax_export.py` | K4-underlag (genomsnittsmetoden, SEK via ECB) från riktiga trades |
| `.github/workflows/agent.yml` | Kör allt varje timme på GitHub Actions |
| `state/` | Agenternas tillstånd (plånbok, trades, historik) – committas automatiskt |
| `logs/` | En rad per varv med beslut, resonemang, kostnad, marknadsögonblick |

## Steg 1 – lokalt, papperläge (5 min)
```bash
pip install -r requirements.txt
cp .env.example .env            # lägg in SURVIVAL_API_KEY
export $(cat .env | xargs)      # eller sätt variabeln på annat sätt
python agent.py --agent haiku
python agent.py --agent fable
python status.py
```
Kolla `logs/haiku.jsonl` och läs resonemangen. Kör några varv för hand innan du automatiserar.

**Viktigt:** uppdatera `price_in`/`price_out` i `config.py` för Fable 5.1 mot Anthropics prislista
– de är platshållare. Compute-kostnaden är hela poängen med experimentet, så den måste stämma.

## Steg 2 – kör i molnet (GitHub Actions)
1. Skapa ett **privat** repo och pusha mappen.
2. Settings → Secrets and variables → Actions → lägg till `SURVIVAL_API_KEY`
   (Kraken-nycklarna behövs först i steg 3).
3. Settings → Actions → General → Workflow permissions → *Read and write permissions*.
4. Actions-fliken → `survival-agents` → *Run workflow* för att testa manuellt.
Därefter körs det varje timme. Din dator kan vara avstängd. Varje varv committar `state/` och `logs/`.

GitHub pausar schemalagda workflows i repon utan aktivitet i 60 dagar – bot-committarna räknas som aktivitet, så det löser sig självt.

## Steg 3 – riktiga pengar (när papperläget sett vettigt ut i minst en vecka)
1. Konto på Kraken, verifiera, sätt in euro via SEPA (gratis) och växla till USD, eller
   byt `QUOTE = "EUR"` och `PAIRS` till `/EUR`-par i `config.py`.
2. Sätt in **endast** det belopp agenten ska ha. Kontot är agentens hela värld.
3. Kraken → Settings → API → skapa nyckel med **enbart** "Query Funds" och "Create & Modify Orders".
   Inga uttagsrättigheter. Ingen IP-begränsning (GitHubs IP-adresser varierar).
4. Lägg `KRAKEN_API_KEY` / `KRAKEN_API_SECRET` som GitHub Secrets.
5. Sätt `PAPER_MODE = False`. Starta gärna om med tomt `state/` så papperhistoriken inte blandas.
6. `KrakenBroker` är skriven mot ccxt:s Kraken-API men inte testad mot riktiga pengar. Kör ett par varv
   med ett par dollar och verifiera fyllningarna i Kraken-gränssnittet innan du litar på den.

## Skatt
Varje riktig trade sparas med tidsstämpel, pris, mängd och avgift. Vid årsskiftet:
```bash
python tax_export.py --year 2026
```
ger `k4_2026.csv` med avyttringar, försäljningspris, omkostnadsbelopp (genomsnittsmetoden) och
vinst/förlust i SEK. Byte krypto→krypto räknas som avyttring; här handlar agenten bara mot
USD/EUR så varje sälj är en avyttring. Papperstrades ignoreras. Kontrollera mot Skatteverkets
vägledning – detta är ett underlag, inte rådgivning.

## Nödstopp
Lägg en tom fil som heter `KILL_SWITCH` i repot (och pusha) – riskfiltret nekar då alla trades.
Agenterna fortsätter dock betala compute, så de dör så småningom. Ta bort workflow-filen för att stoppa helt.

## Idéer för senare
- Fler modeller i `AGENTS` (Sonnet som mellansteg) – de körs parallellt automatiskt.
- Ge agenten ett minnesfält den själv får skriva till mellan varv.
- Variera `RUNS_PER_DAY`/cron-frekvens: hur ofta lönar det sig att tänka?
- Lägg in nyhetsrubriker i prompten och se om beteendet ändras.
