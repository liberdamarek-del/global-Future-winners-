# Pokyny pro každou novou session (§56, §63, §71)

Projekt: Global Future Winners / Stock Radar. Specifikace: `docs/MASTER_PROMPT.md`. Uživatel komunikuje česky.

## Na začátku každé session — nejdřív stav, pak práce

1. Přečti `PROJECT_STATE.md` (zdroj pravdy) a podle potřeby `ROADMAP.md`, `CHANGELOG.md`.
2. Spusť `python -m stockradar init && python -m stockradar status` a `python -m stockradar ledger`.
3. Pokud stav nejde načíst, řekni to uživateli otevřeně. Nikdy si nevymýšlej předchozí výsledky.

## Pravidla práce s daty

- Do DB zapisuj jen ověřené údaje se zdrojem a časovou značkou. Neověřené = `NEOVERENO`.
- Datum katalyzátoru: přesné jen `VERIFIED` se zdrojem; jinak `ESTIMATED`/`UNCERTAIN` s oknem.
- Před každým `SPEC_BUY` / MAIN PICK zapiš XTB kontrolu (`record_xtb_check`) — DB jinak predikci odmítne.
- Historické predikce se nikdy nemění. Nový názor = nová predikce nebo `change_status` s důvodem.
- Po změnách přes Python API spusť `python -m stockradar export` a commitni `state/`.
- Příkazy „AKTUALIZACE“, „NAJDI RAKETU NA 14 DNÍ“, „NAJDI DALŠÍ NVIDIA“, „NAJDI DALŠÍ CAPR“ jsou definovány v §73–§76.

## Pravidla vývoje

- Před novým modulem zkontroluj, zda podobná funkce už neexistuje (§64).
- Schéma se mění jen novou migrací `stockradar/migrations/NNNN_*.sql`; existující migrace nepřepisuj.
- Po změně: `python -m pytest`, aktualizuj `PROJECT_STATE.md` a `CHANGELOG.md`, zvyš `__version__`.
- Moduly ve stavu HOTOVO nepřepisuj bez důvodu, testu a záznamu v CHANGELOG (§65).
