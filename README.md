# Global Future Winners / Stock Radar

Systém pro hledání veřejně obchodovaných firem **před** zásadní fundamentální změnou, katalyzátorem
nebo nástupem megatrendu. Nehledá firmy, které už vyrostly.

- **Specifikace:** [docs/MASTER_PROMPT.md](docs/MASTER_PROMPT.md)
- **Aktuální stav projektu (zdroj pravdy):** [PROJECT_STATE.md](PROJECT_STATE.md)
- **Plán:** [ROADMAP.md](ROADMAP.md) · **Změny:** [CHANGELOG.md](CHANGELOG.md)

> Nejde o investiční doporučení. Výstupy jsou pravděpodobnostní scénáře s explicitním rizikem (§37).

## Rychlý start

Python 3.11+, bez externích závislostí.

```bash
python -m stockradar init       # pracovní DB v data/ se sestaví ze state/
python -m stockradar status     # radar, katalyzátory 0–14 dní, změny verdiktů, MAIN PICK
python -m stockradar ledger     # historický register predikcí (§28)
python -m stockradar lessons    # učební případy (§30, §31)
python -m stockradar snapshot --label "weekly"
python -m stockradar export     # DB -> state/ (pak commit)
python -m stockradar restore    # smaže DB a sestaví ji znovu ze state/

pip install -r requirements-dev.txt && python -m pytest
```

## Kde jsou data

| Místo | Co | V gitu |
|---|---|---|
| `state/*.jsonl` | **Zdroj pravdy**: firmy, listingy, XTB kontroly, katalyzátory, predikce, vyhodnocení, změny verdiktů, poučení, snapshoty | ano |
| `data/stockradar.db` | Pracovní SQLite kopie, kdykoli obnovitelná ze `state/` | ne |

Git historie `state/predictions.jsonl` zároveň dokládá, že se historické predikce nepřepisovaly (§29).

## Pravidla vynucená kódem (ne jen dokumentací)

| Pravidlo | Kde | Co se stane při porušení |
|---|---|---|
| §5 XTB před doporučením (poučení XSPRAY) | DB trigger + `ledger.py` | Spekulativní BUY / MAIN PICK bez XTB kontroly `ANO` (max. 30 dní staré) se nezapíše |
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
