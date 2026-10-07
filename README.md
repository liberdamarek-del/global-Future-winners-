# Global Future Winners / Stock Radar

Systém pro hledání veřejně obchodovaných firem **před** zásadní fundamentální změnou, katalyzátorem
nebo nástupem megatrendu. Nehledá firmy, které už vyrostly.

- **Specifikace:** [docs/MASTER_PROMPT.md](docs/MASTER_PROMPT.md)
- **Aktuální stav projektu (zdroj pravdy):** [PROJECT_STATE.md](PROJECT_STATE.md)
- **Plán:** [ROADMAP.md](ROADMAP.md) · **Změny:** [CHANGELOG.md](CHANGELOG.md)

> Nejde o investiční doporučení. Výstupy jsou pravděpodobnostní scénáře s explicitním rizikem (§37).

## Webový přehled a denní běh

Web je artifact na claude.ai (adresa v [web/dashboard.json](web/dashboard.json)). Každý všední den večer
rutina spustí `python -m stockradar update`, krátký výzkum novinek a nahraje data do databáze stránky.

| Krok | Co dělá |
|---|---|
| Ceny | Yahoo Finance chart API (zdarma): 46 firem z USA, Evropy, Japonska, Koreje a Kanady + S&P 500 (SPY) + kurzy |
| Vyhodnocení | Každá predikce „za 30 dní lépe než S&P 500“ se po 7, 14 a 30 dnech označí HIT/MISS |
| Učení | 9 faktorů (trend, přepálení, objem, volatilita, velikost, dohoda s Big Tech, katalyzátor…); váhy podle toho, co historicky fungovalo |
| Predikce | TOP 5 se skóre ≥ 60 a šancí ≥ 50 %; MAIN PICK jen při skóre ≥ 70 a šanci ≥ 55 % |

## Hlavní obrazovka: žebříček a XTB

Záložky **Do 14 dní / Do 1 měsíce / Do 6 měsíců**, v každé TOP 20 firem seřazených modelem (dokument `stav/zebricek`).
Od v0.8.0 jsou v žebříčku **jen akcie, které nabízí XTB** (rozhodnutí uživatele 2026-10-05):

| Krok | Co dělá |
|---|---|
| Zdroj | veřejné vyhledávání nástrojů na xtb.com/cz (bez přihlášení, bez e-mailu) — `stockradar/sources/xtb.py` |
| Domácí burza | přesná shoda symbolu: VST → `VST.US`, RR.L → `RR.UK`, NKT.CO → `NKT.DK`; jen skutečná akcie, ne CFD |
| Jiná burza | když XTB firmu pod domácím symbolem nemá (nebo burzu nenabízí: Japonsko, Austrálie, Kanada, Korea…), hledá se podle jména firmy a bere se jen přesná shoda jména: CRH → `CRH.UK`, Frontline → `FRO.NO`, Lasertec → `6K8.DE` (EUR) |
| Pořadí | model seřadí všechny akcie; do TOP 20 jdou první firmy z nabídky XTB; celkové pořadí zůstává u firmy i v `poradi_vse` |
| Cache | `xtb_offer` v `data/market_cache.db`, platnost 30 dní; po 5 chybách sítě se dál nezkouší a firmy zůstanou neověřené (do žebříčku nejdou) |
| Ledger | beze změny: predikce raket (TOP 10) se zapisují podle modelu bez ohledu na brokera, aby šlo poctivě měřit model |

## Kauzální radar a model na 6 měsíců (v0.9.0)

Svět → událost → komodita → obory → firmy. Výsledky: [docs/CAUSAL_2026-10-06.md](docs/CAUSAL_2026-10-06.md).

```bash
python -m stockradar causal              # komodity (Yahoo), test řetězců, GDACS + zprávy, karty radaru, web stav/kauzalni
python -m stockradar signals             # 14 dní, 1 měsíc a 6 měsíců (+40 % / −25 %, velké firmy zvlášť)
```

| Krok | Co dělá |
|---|---|
| Komodity | 26 futures a ukazatelů zdarma (ropa, plyn, kovy, uran, obilí, kakao, káva, doprava, dolar) |
| Graf | komodita → výrobní země (NEOVĚŘENO) → obory 1.–3. řádu se směrem a důvodem |
| Citlivost | beta oboru na komoditu jen z minulých 78 týdnů; prokázaná vazba \|t\| ≥ 2 (bez logiky ≥ 3) |
| Test | šok komodity → obory za 1–26 týdnů vs náhodné dvojice; učení / validace / zamčený test |
| Radar | karta: fakta (zdroje) → řetězec → „v ceně?“ → scénáře z historie → firmy (XTB); příležitost jen při shodě dat a logiky |
| 6 měsíců | SIGNAL_6M: P(+40 %), P(−25 %), řazení podle šance na +40 %, riziko vždy vedle, POKLES mezi vítěze nepatří |

## Propojený systém: centrum, zpětná vazba, registr (v0.10.0)

Moduly nejsou slepé: každý předává důkazy do centra, které je váží spolehlivostí z testů a živých výsledků a hledá
rozpory. Zpráva: [docs/ARCHITEKTURA_2026-10-07.md](docs/ARCHITEKTURA_2026-10-07.md).

```bash
python -m stockradar system              # moduly, zdroje, spolehlivost rolí, deník běhů (HOTOVO/OVĚŘENO … CHYBA)
python -m stockradar hub --firma VLO     # pohled na firmu ze všech modulů: postoj, důkazy, rozpory, poučení, kontroly
python -m stockradar research --entita VLO --druh riziko --smer -1 --horizont 120 --datum 2026-10-06 \
    --zdroj "…" --url https://… --text "FAKT: … ÚSUDEK: …"   # ruční výzkum jako trvalý důkaz
```

| Část | Co dělá |
|---|---|
| Důkazy (`hub/evidence.py`) | signály, rakety, smart money, kauzální radar, energetika, ledger, katalyzátory, výzkum, XTB v jednom jazyce |
| Zpětná vazba (`hub/feedback.py`) | spolehlivost 14 rolí: OVĚŘENO (t ≥ 2), NEOVĚŘENO, CHYBA (t ≤ −2); živé výsledky mají přednost |
| Pohled na firmu (`hub/integrate.py`) | PŘÍLEŽITOST / RIZIKO / ROZPOR / NEVÍM, váhy, stará data, poučení z chyb, pořadí ve všech modelech |
| Registr a deník (`hub/registry.py`) | stav modulů a zdrojů, deník každého běhu (`system_runs`), ochrana proti zbytečnému přepočtu |
| Paměť výpočtů (`causal/memo.py`) | týdenní řady a citlivosti se při stejných datech nepočítají znovu (56 s → 0,5 s) |

## Rychlý start

Python 3.11+, bez externích závislostí.

```bash
python -m stockradar init       # pracovní DB v data/ se sestaví ze state/
python -m stockradar update     # denní běh: ceny (Yahoo), vyhodnocení, učení modelu, predikce, data pro web
python -m stockradar status     # radar, katalyzátory do 45 dní, změny verdiktů, MAIN PICK
python -m stockradar diag       # diagnostika: čerstvost dat, zpožděná vyhodnocení, web, e-mail (kód 1 = CHYBA)
python -m stockradar email      # kolikrát, kdy a kde byl použit e-mail uživatele (jen SEC EDGAR)
python -m stockradar sources    # obnoví SEC EDGAR + ClinicalTrials.gov
python -m stockradar ledger     # historický register predikcí (§28)
python -m stockradar lessons    # učební případy (§30, §31)
python -m stockradar snapshot --label "weekly"
python -m stockradar export     # DB -> state/ (pak commit)
python -m stockradar restore    # smaže DB a sestaví ji znovu ze state/

pip install -r requirements-dev.txt && python -m pytest
```

## Globální objevování vítězů (Growth Engine)

Specifikace: [docs/MASTER_PROMPT_GROWTH_ENGINE.md](docs/MASTER_PROMPT_GROWTH_ENGINE.md). Běží týdně (sobota) nebo ručně:

```bash
python -m stockradar discover --universe --download   # seznamy firem + 5 let cen (~13 000 firem, ~75 min)
python -m stockradar discover                         # analýza nad staženými daty + SEC + studie + predikce raket (~15 min)
python -m stockradar discover --no-sources            # bez obnovy SEC a ClinicalTrials.gov
python -m stockradar update                           # data pro web včetně stav/objevy
```

| Krok | Co dělá | Zdroj (zdarma) |
|---|---|---|
| Seznam firem | USA (všechny akcie), Japonsko (celá TSE), Austrálie (celá ASX), indexy Evropy, Kanady, Koreje, Hongkongu, Indie, Singapuru, Izraele, Brazílie | Nasdaq screener, JPX xlsx, ASX CSV, Wikipedie |
| Vítězové | 3/6/12/24 měsíců podle prahů §2; historické rakety ≥ +30 % za týden, ≥ +50 % za měsíc / 3 měsíce, ≥ +100 % za 6 měsíců | Yahoo chart API |
| Co předcházelo | 17 znaků v den T0 (dno před raketou) proti 5 kontrolním firmám ze stejného dne (lift) | — |
| Dalo se to předpokládat? | Model naučený na datech do 2025-04 oskóruje všechny akcie týden po týdnu v pozdějším období; přesnost vs základní četnost **a kontrola směru** (rakety vs propady) | — |
| Příčiny | Titulky zpráv v okně kolem rakety, automatická klasifikace (převzetí, FDA, výsledky, kontrakt, vláda, sektorová vlna, squeeze, krypto…) | Google News RSS |
| Sektory | Obory s nadprůměrným podílem vítězů (lift, z-skóre, nová IPO) + skupiny vítězů, kteří se pohybují spolu | — |
| Kandidáti | EARLY/DEVELOPING firmy s nejvyšším skóre, proč teď / proč ne / co by změnilo názor, čerstvé zprávy; horní 1 % jde do ledgeru jako WATCH | — |

Omezení: seznamy jsou dnešní (survivorship bias), fundamenty jen pro firmy podávající u SEC (USA), příčiny z titulků jsou AUTO.

## Smart money (insideři, politici, velké podíly, buybacky)

Výsledky a metodika: [docs/SMART_MONEY_2026-10-05.md](docs/SMART_MONEY_2026-10-05.md). Běží týdně po objevování nebo ručně:

```bash
python -m stockradar smart-money                 # stáhne SEC Form 4 sady, Sněmovnu, Senát, 13D/13G, buybacky; test + signály
python -m stockradar smart-money --no-download   # jen přepočet nad staženými daty
```

| Krok | Co dělá | Zdroj (zdarma) |
|---|---|---|
| Insideři | každý nákup/odměna/opce; typ AKTIVNÍ / AUTOMATICKÝ (10b5-1) / PASIVNÍ / NEJASNÉ (i „koupil a do 10 dní prodal“) | SEC Insider Transactions Data Sets |
| Politici | výkazy PTR Sněmovny (PDF) a Senátu (eFD), Pelosi zvlášť, srovnání s QQQ | disclosures-clerk.house.gov, efdsearch.senate.gov |
| Velké podíly, buybacky | nové 13D/13G; vyplacené odkupy za rok vůči kapitalizaci | SEC full-index, XBRL frames |
| Test | vstup den po zveřejnění; 1 t–12 m vs S&P 500 a kontrola ze stejného oboru; aktivní − pasivní ve stejném měsíci; učení 2021–24, test 2025–26 | Yahoo chart API |
| Skóre a signály | SMART MONEY SCORE 0–100, 10 aktuálních nákupů ověřených ve Form 4 → ledger (WATCH, 6 m) a web | openinsider.com (seznam) + sec.gov (ověření) |

Každý případ zvlášť: `data/smart_money_udalosti.csv` a `data/smart_money_politici.csv` (mimo git).

## Signály na 14 dní (pravděpodobnosti místo ceny)

Výsledky a metodika: [docs/SIGNALS_2026-10-05.md](docs/SIGNALS_2026-10-05.md). Běží týdně nebo ručně:

```bash
python -m stockradar signals               # panel, učení, validace, zamčený test (jen jednou), karty, vyhodnocení
python -m stockradar signals --no-news     # bez titulků Google News
```

| Krok | Co dělá |
|---|---|
| Cíle | P(+5 % za 10 obchodních dní), P(−5 %), P(lépe než obor), P(prudký pohyb ±10 %), očekávaný výnos z pásma |
| Znaky | technika a relativní síla vůči oboru, fundamenty SEC, překvapení ve výsledcích a reakce trhu (co už je v ceně), kapitálový tok (insideři, buyback, 13G, akumulace objemu), mechanismus „dodavatelský řetězec“ |
| Režim trhu | býčí klidný / volatilní / medvědí / šok / bez trendu; modely „klid“ a „stres“ + meta-model; vyhodnocení trhu zvlášť po nezávislých dvoutýdnech |
| Protokol | TRAIN → VALIDATION → LOCKED TEST (jednou na konfiguraci, registr `model_evaluations`) → POST → LIVE (`signal_forecasts`) |
| Důvěra | 0–100: málo nezávislých analogií, vzácný režim, nepřesná kalibrace, neshoda modelů, chybějící data, šance na šum → NEVÍM / NO-TRADE |

## Kde jsou data

| Místo | Co | V gitu |
|---|---|---|
| `state/*.jsonl` | **Zdroj pravdy**: firmy, listingy, XTB kontroly, katalyzátory, predikce, vyhodnocení, změny verdiktů, poučení, snapshoty | ano |
| `data/stockradar.db` | Pracovní SQLite kopie, kdykoli obnovitelná ze `state/` | ne |
| `data/market_cache.db` | Cache globálního objevování: seznam ~13 000 firem a 5 let cen (zlib), nabídka XTB (`xtb_offer`), kdykoli stažitelná znovu | ne |

Git historie `state/predictions.jsonl` zároveň dokládá, že se historické predikce nepřepisovaly (§29).

## Pravidla vynucená kódem (ne jen dokumentací)

| Pravidlo | Kde | Co se stane při porušení |
|---|---|---|
| §5 XTB (poučení XSPRAY) | `ledger.py`, volitelné | Od 2026-10-02 jen informativně (rozhodnutí uživatele); `REQUIRE_XTB_FOR_BUY = True` bránu zapne |
| §2 nehonit proběhlé katalyzátory (poučení RARE) | `ledger.py` | BUY na katalyzátoru `IN_PROGRESS` / `OCCURRED` / s uplynulým datem se nezapíše |
| §10 odhad ≠ fakt | DB CHECK + `catalysts.py` | Přesné datum jen s `VERIFIED` + zdrojem; odhad musí být okno od–do |
| §29 ledger se nepřepisuje | DB triggery | `UPDATE` / `DELETE` predikce skončí chybou |
| §34 MĚNÍM VERDIKT | `companies.change_status` | Změna bez důvodu se odmítne; každá změna se trvale zapíše |
| §52 DATA STALE | `ledger.py` | Cena starší než 4 h se u predikce označí `STALE` |
| §59 look-ahead bias | `ledger.py` | Predikce nesmí použít informaci zveřejněnou po svém vzniku; živá predikce nejde zpětně datovat |
| §60 survivorship bias | DB trigger | Firmy nelze smazat, jen změnit `listing_status` |

## Příklad: zápis kandidáta přes Python API

```python
from datetime import datetime, timezone
from stockradar.config import db_path
from stockradar.db import open_db
from stockradar.companies import add_company, add_listing, record_xtb_check, change_status
from stockradar.catalysts import add_catalyst
from stockradar.ledger import PredictionInput, Scores, record_prediction

conn = open_db(db_path())
cid = add_company(conn, "Example Bio", country="US", sector="Healthcare", industry="Biotech")
lid = add_listing(conn, cid, "EXBI", "NASDAQ", currency="USD", is_primary=True)

# §5: nejdřív XTB, potom doporučení
record_xtb_check(conn, lid, "ANO", instruments=["STOCK"], source="xStation – vyhledání 2026-10-02")

# §10: přesné datum jen s ověřeným zdrojem
cat = add_catalyst(conn, cid, "FDA_DECISION", "PDUFA pro lék X",
                   date_status="VERIFIED", event_date="2026-10-14", source="10-Q / tisková zpráva FDA")

print(change_status(conn, cid, "category", "A", reason="blízký PDUFA, runway 18 měsíců"))

record_prediction(conn, PredictionInput(
    listing_id=lid, horizon="D0_14", price=4.20, currency="USD",
    price_as_of=datetime(2026, 10, 2, 11, 30, tzinfo=timezone.utc), price_source="Nasdaq",
    market_cap=180e6, market_cap_currency="USD", catalyst_id=cat,
    category="A", verdict="SPEC_BUY", is_main_pick=True, rationale="…",
    probability_pct=55, bull_move_pct=120, base_move_pct=15, bear_move_pct=-60,
    key_risk="CRL kvůli CMC", scores=Scores(overall_setup=82, rocket=78),
))
```

Potom `python -m stockradar export` a commit `state/`.
Hodnoty výše jsou smyšlený příklad, nejsou to tržní data.
