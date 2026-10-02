# Pokyny pro každou novou session (§56, §63, §71)

Projekt: Global Future Winners / Stock Radar. Specifikace: `docs/MASTER_PROMPT.md` (radar katalyzátorů) a
`docs/MASTER_PROMPT_GROWTH_ENGINE.md` (globální objevování vítězů, vzorů a sektorů). Uživatel komunikuje česky.
Webový přehled: artifact v `web/dashboard.json` (stránka `web/index.html`, data v jeho db dokumentech `stav/*`).

## Na začátku každé session — nejdřív stav, pak práce

1. Přečti `PROJECT_STATE.md` (zdroj pravdy) a podle potřeby `ROADMAP.md`, `CHANGELOG.md`.
2. Spusť `python -m stockradar init && python -m stockradar status` a `python -m stockradar ledger`.
3. Pokud stav nejde načíst, řekni to uživateli otevřeně. Nikdy si nevymýšlej předchozí výsledky.

## Rozhodnutí uživatele (2026-10-02)

- Jen **bezplatné** zdroje dat. Placené API nepoužívat.
- **XTB není povinná podmínka** doporučení (stav se jen informativně zapisuje; `config.REQUIRE_XTB_FOR_BUY = False`).
- Fokus: řetězec AI → elektřina → jádro (SMR, palivo) → fúze → síť; dohody Google a dalších Big Tech; raketový potenciál.
- Web se aktualizuje denně, ukazuje staré predikce a jejich vyhodnocení; model se sám přeučuje podle výsledků.

## Denní úloha (rutina, po–pá večer)

1. `git pull origin ccr-07430f55-or3jhd`, pak `python -m stockradar init` a `python -m stockradar update`
   (ceny z Yahoo, vyhodnocení predikcí +7/+14/+30 dní, učení modelu, nové predikce, export `state/`, data pro web).
2. Krátký výzkum (WebSearch): novinky u firem s katalyzátorem do 45 dní; nové energetické dohody Google,
   Microsoft, Amazon, Meta; nová IPO v řetězci. Zapisuj JEN ověřené se zdrojem (URL) a datem:
   `stockradar.universe.add_relationship`, `add_tracked_company`, `stockradar.catalysts.add_catalyst`,
   proběhlé katalyzátory `set_catalyst_status(..., "OCCURRED")`. Odhad termínu = okno (ESTIMATED/UNCERTAIN).
   Když jsi něco zapsal, spusť `python -m stockradar update` znovu.
3. Web: `ArtifactData` `list` kolekce `stav` (kvůli `version`), pak `batch` se `set` pro každý soubor
   `data/web/stav_*.json` (aktualni, predikce, retezec, objevy) s `if_version` (URL v `web/dashboard.json`).
4. `git add state/ && git commit && git push -u origin ccr-07430f55-or3jhd`.
5. Uživateli česky 2–4 věty: nové predikce, nově vyhodnocené (HIT/MISS), změna vah modelu, důležitá novinka.
   Nikdy neobchoduj a nic neslibuj („určitě +100 %“ je zakázáno, §37).

## Globální objevování (Growth Engine, týdně v sobotu)

- `python -m stockradar discover --universe --download` — seznamy firem (Nasdaq screener, ASX, JPX, Wikipedie),
  5 let cen (Yahoo, ~13 000 firem, ~75 min), rakety, kontrolní skupina, test předvídatelnosti, příčiny z Google News,
  sektorové vlny, kandidáti → `discovery_runs` + ledger (WATCH, zdroj DISCOVERY). Potom `python -m stockradar update`
  (data pro web včetně `stav/objevy`) a zápis 4 dokumentů `stav/*` do artifactu.
- Příkazy uživatele (§62 Growth Engine): „NAJDI VÍTĚZE“, „NAJDI VZORY“, „NAJDI NOVÝ SEKTOR“, „NAJDI DALŠÍ VÍTĚZE“,
  „NAJDI SKRYTÉ VÍTĚZE“, „PROVEĎ GLOBAL DISCOVERY“, „NAJDI DALŠÍ NEBIUS“ — vycházej z posledního `discovery_runs`
  (nebo spusť nový běh) a doplň ruční výzkum se zdroji. Příčiny z titulků jsou AUTO, dokud je neověříš.
- Poctivost: vždy uváděj počty (firem, zemí, raket, titulků), základní četnost a kontrolu směru (rakety vs propady).

## Pravidla práce s daty

- Do DB zapisuj jen ověřené údaje se zdrojem a časovou značkou. Neověřené = `NEOVERENO`.
- Datum katalyzátoru: přesné jen `VERIFIED` se zdrojem; jinak `ESTIMATED`/`UNCERTAIN` s oknem.
- Historické predikce se nikdy nemění. Nový názor = nová predikce nebo `change_status` s důvodem.
- Po změnách přes Python API spusť `python -m stockradar export` a commitni `state/`.
- E-mail uživatele NIKAM neposílat (rozhodnutí 2026-10-02: „zatím nikam“, možná se později změní) — ani v hlavičkách
  HTTP dotazů. SEC EDGAR proto zůstává vypnutý (vyžaduje kontaktní e-mail v User-Agent).
- Příkazy „AKTUALIZACE“, „NAJDI RAKETU NA 14 DNÍ“, „NAJDI DALŠÍ NVIDIA“, „NAJDI DALŠÍ CAPR“ jsou definovány v §73–§76.

## Pravidla vývoje

- Před novým modulem zkontroluj, zda podobná funkce už neexistuje (§64).
- Schéma se mění jen novou migrací `stockradar/migrations/NNNN_*.sql`; existující migrace nepřepisuj.
- Po změně: `python -m pytest`, aktualizuj `PROJECT_STATE.md` a `CHANGELOG.md`, zvyš `__version__`.
- Moduly ve stavu HOTOVO nepřepisuj bez důvodu, testu a záznamu v CHANGELOG (§65).
- Změna stránky: uprav `web/index.html` a publikuj ho na URL z `web/dashboard.json` (stejná adresa).
