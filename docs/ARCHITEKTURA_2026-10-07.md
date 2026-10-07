# Architektura systému — audit a návrh propojení (2026-10-07, v0.10.0)

Zadání uživatele 2026-10-07: systém se nemá chovat jako sada nezávislých skriptů, ale jako propojená síť
specializovaných částí, které si předávají kontext, kontrolují se a učí se ze zpětné vazby.
Postup: POZOROVAT → POCHOPIT → PROPOJIT → ANALYZOVAT → NAVRHNOUT → IMPLEMENTOVAT → OTESTOVAT → VYHODNOTIT.

## 1. Pozorování: co systém dnes je

### Specializované části

| Část | Moduly | Úkol | Výstup (paměť) |
|---|---|---|---|
| Zdroje dat | `sources/*`, `discovery/download`, `ingest` | Yahoo, SEC EDGAR, ClinicalTrials.gov, GDACS, Google News, xtb.com | `market_cache.db` (ceny ~13 000 firem, SEC, studie, XTB), `price_bars` |
| Energetický radar | `universe`, `model`, `update`, `ledger` | 46 firem řetězce AI → elektřina, faktorový model, denní predikce | `model_runs`, `predictions`, `prediction_outcomes` |
| Objevování | `discovery/*` | vítězové, rakety, příčiny, model raket 6 m | `discovery_runs`, `predictions` (rakety) |
| Smart money | `smartmoney/*` | insideři, politici, 13D/G, buybacky | `smart_money_runs`, `predictions` (WATCH) |
| Signály | `signals/*` | modely 14 dní / 1 měsíc / 6 měsíců, zamčené testy | `signal_runs`, `signal_forecasts`, `signal_outcomes`, `model_evaluations` |
| Kauzální radar | `causal/*` | komodity → obory → firmy, události | `causal_runs`, `causal_forecasts`, `causal_outcomes` |
| Dostupnost | `sources/xtb` | nabídka brokera | `xtb_offer` |
| Výstup | `site`, `web/index.html`, `diag` | web, diagnostika | `data/web/stav_*.json` |

### Existující vazby (dobře)

- Signály čtou smart money (nákupy insiderů, skóre), katalyzátory (`catalysts`), fundamenty SEC a kauzální vítr.
- Žebříčky čtou XTB.
- Zamčené testy jsou v jednom registru (`model_evaluations`).

## 2. Analýza: slepá místa

| # | Slabina | Dopad |
|---|---|---|
| S1 | **Tři oddělené knihy predikcí** (`predictions`, `signal_forecasts`, `causal_forecasts`), každá se vyhodnocuje zvlášť | výsledky nikde nemění důvěru v modul; zpětná vazba nevzniká |
| S2 | **Firma nemá jeden pohled** | HF Sinclair je 1. mezi velkými firmami na 6 m, ale riziko z výzkumu (G7 uvolňuje zásoby → nižší marže rafinerií) zůstalo jen v chatu |
| S3 | **Ruční výzkum nemá kam do paměti** | ověřené zprávy bez vazby na katalyzátor nebo dohodu se ztratí |
| S4 | **Poučení (17) nikdo nečte** | např. SM-ESPP-FLIP-WIX nebo POUCENI-RAKETY-VOLATILITA neovlivní další rozhodnutí |
| S5 | **Opakované výpočty** | týdenní řady a citlivost oborů (~45 s) se počítají v `signals` i `causal`, přitom ceny akcií se mění jen jednou týdně |
| S6 | **Stav systému jen v ručním textu** (PROJECT_STATE.md) | chybí strojový deník (co, proč, výsledek, chyba) a stavy modulů HOTOVO/OVĚŘENO, ROZPRACOVÁNO, BLOKOVÁNO, NEOVĚŘENO, CHYBA |
| S7 | **Sebekontrola jen lokálně** (zamčené testy, XTB, POKLES mezi vítězi) | chybí kontrola napříč moduly: rozpory, stáří dat k horizontu, chybějící pokrytí |

## 3. Návrh: propojený systém

```
 ZDROJE ─► SPECIALIZOVANÉ ČÁSTI ─► CENTRUM DŮKAZŮ ─► INTEGRACE (pohled na firmu) ─► ROZHODNUTÍ / WEB
                ▲                       │                  ▲
                │                       ▼                  │
                └──── ZPĚTNÁ VAZBA ◄── VÝSLEDKY PREDIKCÍ ◄──┘    REGISTR + DENÍK (paměť systému)
```

1. **Centrum důkazů** (`hub/evidence.py`): každá část mluví jedním jazykem.
   - Důkaz = entita (firma / obor / komodita), modul, druh (příležitost, riziko, katalyzátor, kontext, poučení,
     dostupnost), směr, horizont, pravděpodobnost a základ, stav (OVĚŘENO / NEOVĚŘENO / AUTO), zdroj, datum dat.
   - Důkazy se odvozují z uložených výstupů modulů. Moduly se zamčenými testy se nemění.
   - Ruční výzkum se ukládá jako trvalý důkaz se zdrojem a platností (`research_evidence`, append-only).
2. **Zpětná vazba** (`hub/feedback.py`): spolehlivost každé role modulu (např. „6 m — varování před pádem“).
   - Zdroje: zamčené testy a vyhodnocené živé predikce ze všech tří knih.
   - Stav OVĚŘENO (t ≥ 2 správným směrem), CHYBA (t ≤ −2, tedy horší než náhoda) nebo NEOVĚŘENO.
   - Váha důvěry 0–1. Bez dat je blízko 0, takže neověřená role je vidět, ale neváží.
   - Živé výsledky s aspoň 30 případy mají přednost před testem.
3. **Integrace** (`hub/integrate.py`): pohled na firmu ze všech modulů.
   - Důkazy se váží spolehlivostí.
   - Hledají se rozpory (jeden modul růst, jiný riziko), stará data k horizontu, chybějící pokrytí a poučení.
   - Výsledek: PŘÍLEŽITOST / RIZIKO / ROZPOR / NEVÍM a čitelný důkazní řetězec.
   - Nejde o nový prediktivní model, jen o průhledné spojení ověřených částí.
4. **Registr a deník** (`hub/registry.py`, `system_runs`):
   - každý příkaz se zapíše (co, s jakými parametry, kdy, výsledek, chyba);
   - registr zná závislosti modulů, čerstvost vstupů a výstupů a stavy 5 kategorií;
   - `python -m stockradar system` ukazuje celý systém.
5. **Méně opakování**: týdenní řady a citlivost oborů se ukládají podle otisku vstupů. `causal` a `signals` je sdílejí
   a znovu je počítají jen při změně dat.

## 4. Plán a stav

| Krok | Stav |
|---|---|
| Mapa, slabiny, návrh (tento dokument) | HOTOVO |
| Centrum důkazů + výzkum + deník (migrace 0008) | HOTOVO (testy) |
| Zpětná vazba (spolehlivost rolí) | HOTOVO pro testy; živé výsledky ROZPRACOVÁNO (první vyhodnocení 2026-10-09) |
| Integrace + sebekontrola + web | HOTOVO (testy, vykreslení desktop/mobil) |
| Registr + příkaz `system` + cache výpočtů + ochrana proti přepočtu | HOTOVO (testy, ostrý běh) |
| Celková kontrola | HOTOVO, viz kap. 6 |

## 5. Implementace (v0.10.0)

```
 update ─┐   discover ─┐   smart-money ─┐   signals ─┐   causal ─┐   research ─┐
         ▼             ▼                ▼            ▼           ▼             ▼
   model_runs   discovery_runs   smart_money_runs  signal_runs  causal_runs  research_evidence   (+ ledger, katalyzátory,
         └─────────────┴────────────────┴──────┬─────┴───────────┴─────────────┘                  poučení, XTB)
                                               ▼
                       hub/evidence.py — DŮKAZY (entita, modul, role, směr, horizont, zdroj, stav)
                                               ▼
   model_evaluations + 3 knihy výsledků ─► hub/feedback.py — SPOLEHLIVOST ROLE (OVĚŘENO / NEOVĚŘENO / CHYBA, váha)
                                               ▼
                       hub/integrate.py — POHLED NA FIRMU + ROZPORY + POUČENÍ + KONTROLY
                                               ▼
                 hub_runs (paměť, jen při změně vstupů) · stav/prehled (web) · `hub --firma`
   hub/registry.py — moduly, zdroje, stavy, deník `system_runs` · `python -m stockradar system` · `diag`
```

| Část | Co dělá |
|---|---|
| `hub/evidence.py` | 9 sběračů čte poslední uložené výstupy (signály 14 d / 1 m / 6 m včetně celého pořadí 3 673 akcií, rakety, smart money, kauzální příležitosti, energetický TOP 5, ledger, katalyzátory, výzkum, XTB). `add_research` ukládá ruční výzkum (URL povinná, platnost, append-only). Smart money předává i vlastní verdikt modulu (NÍZKÁ → neověřeno, STŘEDNÍ → poloviční váha). |
| `hub/feedback.py` | 14 rolí. Jediná funkce `signal_role` určuje roli karty pro důkazy i pro vyhodnocení živých karet. Zdroje: zamčené testy z registru `model_evaluations`, test raket, studie smart money, test energetiky, živé výsledky ze `signal_outcomes`, `causal_outcomes`, `prediction_outcomes` (t přes týdny; přednost od 30 případů v 6 týdnech). |
| `hub/integrate.py` | Pohled na firmu včetně oborových důkazů (kauzální radar přes obor firmy). Váha = spolehlivost role × čerstvost (data starší než čtvrtina horizontu → polovina). Postoj, rozpory, poučení podle pravidel (`LESSON_RULES`), pořadí ve všech modelech, kontroly. Otisk vstupů → do `hub_runs` jen při změně. Změny postoje proti minulému běhu. |
| `hub/registry.py` | 10 modulů (příkaz, kadence, vstupy, role) a 9 zdrojů; 5 stavů; deník běhů; `signals_unchanged` (ochrana proti přepočtu). |
| `causal/memo.py` | Týdenní řady a citlivosti podle otisku dat (ceny akcií + komodity do posledního dne akcií); sdílí `causal` i `signals`. |
| `cli.py` | Každý příkaz, který mění data nebo kontroluje systém, se zapíše do deníku (i při chybě). Po `update`, `discover`, `smart-money`, `signals`, `causal`, `research` se centrum obnoví samo. Nové příkazy `hub [--firma]`, `system`, `research`; `signals --force`. |
| `diag.py` | Nově kontroluje, že centrum je novější než výstupy modulů, a stav modulů z registru (selhaný běh = CHYBA). |
| Web | V detailu každé firmy „Propojený pohled ze všech modulů“ (postoj, důkazy se spolehlivostí, rozpory, kontroly, poučení, pořadí). Sekce „Stav systému a propojení modulů“ (spolehlivost rolí, moduly, kontroly a změny, zdroje, deník). Upozornění nahoře, když modul selže. |

### Co centrum ukázalo hned při prvním běhu (data k 2026-10-02, 151 firem, 307 důkazů)

| Zjištění | Detail |
|---|---|
| Ověřené role mimo vzorek jsou jen 3 | varování 1 měsíc (t 3,7), varování 6 měsíců (t 4,0), aktivní nákup insiderů (t 2,7 proti podobným akciím; proti S&P 500 −1,7 %) |
| Výběry do žebříčků nejsou ověřené | 14 dní t 1,1; 1 měsíc t −0,7; 6 měsíců t 0,2; rakety: víc raket, ale i propadů; energetika TOP 5 porazilo S&P 500 v 47 % |
| 7 rozporů | DINO, MPC, VLO, DK (žebříčky 1 m / 6 m ↑ × výzkum G7 ↓ marže rafinérií); ASM, HBM, LAC (výběr ↑ × kauzální radar: silný dolar → těžaři kovů ↓) |
| Smart money | 6 z 10 dnešních signálů má vlastní verdikt modulu NÍZKÁ → centrum je nebere jako ověřené, i když role „aktivní nákup“ celkově ověřená je; 4 mají STŘEDNÍ → poloviční váha |
| Zpětná vazba | 0 vyhodnocených predikcí ve všech třech knihách; 236 čeká; první vyhodnocení 2026-10-09 → modul „Vyhodnocení predikcí“ = ROZPRACOVÁNO |
| Zdroje | BLOKOVÁNO: cukr (Yahoo nevrací data), GDELT (HTTP 429); SEC Form 4 čtvrtletní sady končí 2026Q1 (čerstvé nákupy z openinsider) |

## 6. Celková kontrola (2026-10-07)

| Oblast | Výsledek |
|---|---|
| Testy | `python -m pytest`: 134 prošlo (nově 10 v `tests/unit/test_hub.py`) |
| Regrese modelů | Kód modelů a pravidla řazení se nezměnily; otisky konfigurací 14D/1M/6M beze změny; zamčené testy se znovu nespouštěly |
| Integrace | `hub`, `system`, `research`, `diag` na ostré DB; čistá instalace (`init` → `diag` → `hub` → `system`) bez chyb |
| Datové toky | Každý modul → důkazy → spolehlivost → pohled → web; ledger, katalyzátory, poučení a výzkum se poprvé čtou při rozhodování |
| Kvalita dat | Důkaz nese den dat, zdroj a stav; stará data se označí a mají poloviční váhu; prošlý výzkum se nepočítá |
| Výkon | `causal`: načtení 12 000 řad a výpočet řad ~56 s → z paměti 0,5 s (výsledek testu řetězců shodný); `signals` bez nových dat se přeskočí (dřív vzniklo 17 běhů nad stejnými daty k 2026-10-02); centrum ~0,2 s |
| Duplicity | Role karty určuje jediná funkce pro důkazy i vyhodnocení; výzkum má vlastní tabulku (dřív neměl kam); nové moduly nekopírují existující výpočty, jen čtou uložené výstupy |
| Web | Dokument `stav/prehled` 120 kB (limit 170 kB; poučení uložena jednou místo u každé firmy); bez chyb JS; mobil 390 px bez vodorovného posunu |
| Nalezené a opravené chyby | `--help` padal na znaku „%“ v nápovědě `signals`; centrum padalo na čisté instalaci (tabulka `xtb_offer` vzniká až při první kontrole); rozpor „ověřená role“ × verdikt smart money NÍZKÁ; vnořené rozbalovací prvky na webu přebíraly styl řádku žebříčku; široké tabulky na mobilu |
| Zůstává NEOVĚŘENO | Váhy důvěry jsou průhledné pravidlo (t / 4), ne naučený model. Ruční výzkum se zatím nevyhodnocuje proti cenám. Živá zpětná vazba začne 2026-10-09 a spolehlivé bude až po ~6 týdnech. |
