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

## Kde jsou data

| Místo | Co | V gitu |
|---|---|---|
| `state/*.jsonl` | **Zdroj pravdy**: firmy, listingy, XTB kontroly, katalyzátory, predikce, vyhodnocení, změny verdiktů, poučení, snapshoty | ano |
| `data/stockradar.db` | Pracovní SQLite kopie, kdykoli obnovitelná ze `state/` | ne |
| `data/market_cache.db` | Cache globálního objevování: seznam ~13 000 firem a 5 let cen (zlib), kdykoli stažitelná znovu | ne |

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
