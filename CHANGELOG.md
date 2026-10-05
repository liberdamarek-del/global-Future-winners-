# CHANGELOG (§49)

Formát: Datum · Verze · Soubor/modul · Změna · Důvod · Test · Výsledek

---

## 2026-10-05 · v0.7.0 — Hlavní stránka = žebříček TOP 20 (14 dní, 1 měsíc, 6 měsíců) + model na 1 měsíc

Důvod: uživatel 2026-10-05 — na webu je moc informací. Hlavní část má být jednoduchý žebříček „Vítězové do 14 dnů /
do 1 měsíce / do 6 měsíců“ (TOP 10–20, jakýkoli sektor a země, první = nejsilnější kandidát). Detaily až po
rozkliknutí firmy, nic se nemaže. Zpráva: [docs/SIGNALS_2026-10-05.md](docs/SIGNALS_2026-10-05.md), kapitola 7.

| Soubor/modul | Změna |
|---|---|
| `signals/model.py`, `signals/panel.py` | Model **SIGNAL_1M** (+10 % / −10 % za 20 obchodních dní, ±20 %, obor za 20 dní); `SPECS`, `view()`, mezera 33 dní mezi obdobími; konfigurace SIGNAL_14D beze změny (test `a1b0f2e61e6c56cc`) |
| `signals/run.py` | Oba modely v jednom běhu (panel jednou); žebříček TOP 20 podle pravidla vybraného na validaci + 5 nejslabších; pořadí, horizont, prahy a **potenciál** (horní pětina 40 analogií) na kartě |
| `signals/card.py`, `signals/store.py` | Analogie podle horizontu; prahy z karty při vyhodnocení; `history()` = historie hodnocení firmy; skóre podle horizontu; duplicitní karty a záznamy registru se nezapisují |
| `discovery/engine.py`, `discovery/store.py` | Rakety na 6 měsíců: TOP 20 pro web, do ledgeru dál jen TOP 10 (`ROCKET_LEDGER_TOP`) |
| `site.py` | Nový dokument `stav/zebricek` (h14, h1m, h6m: TOP 20 + test modelu + historie); `stav/signaly` obsahuje oba modely |
| `web/index.html` | Hlavní stránka: záložky 14 dní / 1 měsíc / 6 měsíců (volba se pamatuje), TOP 20 s šancí na růst a potenciálem, detail po rozkliknutí; ostatní sekce sbalené v „Další analýzy“ |
| `cli.py` | `signals` počítá oba modely; nové nákupy insiderů z openinsider po 14denních oknech od posledního data SEC |
| `tests/unit/test_signals.py` | + zmrazená konfigurace 14D, pohled 1M a oddělená období, pravidlo řazení (12 testů) |

**Zamčený test SIGNAL_1M** (pokus č. 1, 36 456 vzorků, 4 556 nezávislých):
- AUC: +10 % 0,64, −10 % 0,74, ±20 % 0,84, obor 0,53.
- Horní desetina +0,02 % nad týdnem (šum 48 %) → směr nepotvrzen.
- Dolní desetina −4,0 % (t −3,7).

**Pravidlo řazení (validace, ne test):** „šance na růst, jen když růst > pokles“.
- 14 dní: TOP 20 dosáhlo +5 % v 33,8 % případů (základ 23,8 %), −5 % v 26,5 % (základ 24,2 %).
- 1 měsíc: +10 % ve 25,2 % (základ 16,6 %), −10 % ve 24,1 % (základ 18,1 %).
- Průměrný výnos proti týdnu ≈ 0 → žebříček = vyšší šance na velký růst, ne jistota.

**Chyby nalezené během práce:**
- Řazení podle „růst − pokles“ vybíralo klidné akcie, které se skoro nehýbou.
- Kalibrace je v horním pásmu plochá → horní firmy mají stejnou šanci na růst. Mezi nimi rozhoduje menší riziko poklesu
  (ověřené pravidlo). Pokus řadit podle surového skóre (běhy #7 a #8) vybral nejrozkolísanější akcie a nebyl ověřený
  na validaci → vrácen (test `test_ranking_rule_from_validation`). Karty z těch běhů zůstávají (append-only).
- Web: u každé firmy je vedle šance na růst i riziko poklesu (u 6 měsíců propadu), takže je pořadí vidět.
- Potenciál z pásma byl pro všechny stejný → nově z analogií každé firmy.

## 2026-10-05 · v0.6.0 — Signály na 14 dní: pravděpodobnosti místo ceny, režim trhu, NEVÍM, zamčený test

Důvod: návrh uživatele 2026-10-05 (14 bodů: nepředpovídat cenu, mechanismus událost → akcie, překvapení, co je v ceně,
novost a kvalita informací, režim trhu, „nevím“, relativní síla, kapitálový tok, analogie, TRAIN/VALIDATION/LOCKED
TEST/LIVE, nezávislé případy, nové skórování). Zpráva: [docs/SIGNALS_2026-10-05.md](docs/SIGNALS_2026-10-05.md).

| Soubor/modul | Změna | Bod |
|---|---|---|
| `signals/regime.py` | 5 režimů trhu (S&P 500, VIX, 10letý výnos — Yahoo zdarma), sezóna výsledků; `market_view` po nezávislých dvoutýdnech | 7, 13 |
| `signals/extra.py` | Překvapení ve výsledcích (SEC XBRL, stejný kvartál loni), reakce trhu na výsledky, mispricing, drift, reakce na 8-K; insideři, buyback, 13G, akumulace objemu | 3, 4, 10 |
| `signals/panel.py` | Týdenní panel US akcií (obrat ≥ 1 mil. USD, cena ≥ 2 USD): cíle +5 % / −5 % / ±10 % / lépe než obor, výnosy 1–120 dní | 1, 9, 11 |
| `signals/model.py` | Protokol TRAIN / VALIDATION / LOCKED TEST / POST / LIVE, globální + režimové modely, meta-model, monotónní kalibrace, pásma, nezávislé případy, t přes týdny | 7, 12, 13 |
| `signals/card.py` | Důvěra 0–100 s penalizacemi, RŮST / POKLES / NEVÍM (relativně i k dnešnímu trhu), analogie (k-NN), skóre složek | 8, 11, 14 |
| `signals/news.py` | Kvalita zdroje 0–100, shlukování přepisů do příběhů, novost za 7 dní | 5, 6 |
| `signals/mechanism.py` | Graf 3 řetězců (AI → elektřina, ropa, stavba), znak „obory proti proudu“, test proti 300 náhodným dvojicím | 2 |
| `signals/store.py`, `migrations/0006_signals.sql` | `model_evaluations` (zamčený test jednou na konfiguraci — hlídá i DB), `signal_runs`, `signal_forecasts`, `signal_outcomes` (append-only) | 12 |
| `smartmoney/current.py` | Oprava: openinsider po 10. stránce vrací stejnou stránku → duplicity se vyřazují, delší období po 14denních oknech | chyba dat |
| `cli.py`, `site.py`, `web/index.html` | `signals`, dokument `stav/signaly`, sekce „Signály na 14 dní“ | 14 |

**Chyby nalezené během práce:**
- *Znaky celého trhu* (VIX, sazby, S&P 500) v modelu akcií dávaly „tisíce vzorků“ z několika epizod. Dnes kvůli
  rostoucím sazbám (vzorec hlavně z roku 2022) označily 45 % akcií za POKLES. Proto jsou z modelu akcií vyřazené
  a trh se hodnotí zvlášť (bod 13).
- *Rozhodnutí* se měří i proti dnešní průměrné akcii, aby plošný posun nevytvořil stovky stejných signálů.
- *openinsider* opakoval stránky (stejné nákupy až 31×). Běh byl zastaven před jakýmkoli zápisem a opraven.

**Výsledky (zamčený test 2025-07-18 … 2026-03-27, 38 579 vzorků, 4 818 nezávislých, pokus č. 1):**
- AUC: +5 % 0,60, −5 % 0,69, ±10 % 0,83, lépe než obor 0,53.
- RŮST 396× → +0,6 % nad týdnem (šum 65 %).
- POKLES 5 468× → −0,9 % (šum 10 %; ve validaci −2,2 %, po testu −3,6 %).
- Dnes: 0× RŮST, 193× POKLES, 3 480× NEVÍM.
- Trh: NEVÍM (108 dvoutýdnů, žádný režim statisticky odlišný).
- Mechanismy a mispricing: nepotvrzeny.

**Test:** `python -m pytest` — 106 testů (9 nových pro signály). **Výsledek:** 106/106 prošlo.

---

## 2026-10-05 · v0.5.0 — Smart money: insideři, politici (Pelosi), velké podíly, buybacky

Důvod: pokyn uživatele 2026-10-05 „PROVEĎ HISTORICKOU A AKTUÁLNÍ ANALÝZU SMART MONEY A VELKÝCH NÁKUPŮ AKCIÍ“.
Zpráva: [docs/SMART_MONEY_2026-10-05.md](docs/SMART_MONEY_2026-10-05.md).

| Soubor/modul | Změna | Důvod |
|---|---|---|
| `smartmoney/sources.py` | SEC Insider Transactions Data Sets (Form 3/4/5, příznak 10b5-1, prodeje kupujících), Sněmovna PTR (PDF → text), Senát eFD | primární data |
| `smartmoney/analysis.py`, `events.py`, `groups.py` | Typy AKTIVNÍ / AUTOMATICKÝ / PASIVNÍ / NEJASNÉ; event study od dne po zveřejnění (1 t–12 m, max/min, S&P, kontrola ze stejného oboru, t přes měsíce); aktivní − pasivní ve stejném měsíci; CSV „každý případ“ | zadání §2–§3, §8 |
| `smartmoney/score.py` | SMART MONEY SCORE 0–100 (učení 2021–24, test 2025–26), předchozí úspěšnost nakupujícího bez look-ahead | zadání §6 |
| `smartmoney/current.py`, `report.py`, `store.py` | Aktuální nákupy (openinsider) → ověření v originálním Form 4 → TOP 10 s verdiktem VYSOKÁ/STŘEDNÍ/NÍZKÁ → ledger | zadání §7, §10 |
| `migrations/0005_smart_money.sql` | `predictions.strategy` (ROCKET_6M / SMART_MONEY), `smart_money_runs` (append-only) | evidence běhů |
| `sources/sec.py` | 13G ve formulářích, roční zpětné odkupy z XBRL frames | buybacky, podíly |
| `site.py`, `web/index.html` | Sekce „Smart money“ (závěr, 10 signálů, historie, politici a Pelosi, test skóre), filtr v Výsledcích; dokument `stav/smartmoney` | web |
| `cli.py` | `smart-money [--no-download]` | týdenní běh |
| `lessons` | SM-ESPP-FLIP-WIX | chyba nalezená během analýzy |

**Chyby nalezené a opravené během analýzy:**
- *WIX (běh #1):* kód P ve Form 4 byl zaměstnanecký nákup se slevou 32 % a prodej druhý den → nově NEJASNÉ (hned prodáno)
  / PASIVNÍ (sleva > 12 %); historická data SEC stažena znovu i s prodeji kupujících (347 takových případů).
- *Kontrolní skupina:* vybírala se ze sdíleného generátoru náhody → výsledek malé skupiny (Pelosi) závisel na počtu
  ostatních událostí. Nově pevný výběr pro každou akcii a den (běh #3).

**Hlavní výsledky (běh #3, ceny do 2026-10-02):** aktivní nákup insidera − pasivní transakce za 6 m: učení 2021–24
+2,1 % (t 2,91), test 2025–26 −4,1 % (t −2,9);
po propadu 30 %+ v učení silná výhoda, v testu záporná; politici bez výhody; Pelosi statisticky neprokázaná; 13D záporné;
buybacky bez efektu. **Opakovatelný vzorec nepotvrzen** → žádný signál VYSOKÁ. V ledgeru 12 predikcí SMART_MONEY
(#18–#29, WATCH 6 m: 10 z běhu #1 včetně neplatné WIX, AVBC a ELAN z běhu #2; běh #3 vybral stejných 10 firem).

**Test:** `python -m pytest` — 97 testů (8 nových pro smart money). **Výsledek:** 97/97 prošlo. **E-mail:** 2026-10-05 celkem 133 dotazů (www.sec.gov, data.sec.gov).

---

## 2026-10-04 · v0.4.1 — týdenní zlepšení: stabilita modelu raket, reverse splity, čerstvost ceny, méně dotazů s e-mailem

Důvod: sobotní rutina „objevování + zlepšování“ (běh objevování #3, 2026-10-04; data k závěru 2026-10-02).

| Soubor/modul | Změna | Důvod |
|---|---|---|
| `discovery/rocket.py` | Test stability (walk-forward): stejné řazení, učení jen na starších datech, test 2024-H1 a 2025-H1; vzorkuje se i pololetí mezi učením a testem | plán P2.2 z auditu |
| `discovery/winners.py`, `study.py` | Neupravené reverse splity (cena ×5/×10/×20 přes noc s propadem objemu) se před analýzou zpětně upraví — 26 z 12 774 řad (DHY +897 %, WCT +478 % nebyly rakety) | nově nalezená chyba dat |
| `data_quality.py` | M4: závěrečná cena z dřívějšího dne bez další obchodní seance (pátek → víkend) = FRESH, ne DATA STALE | audit M4 |
| `sources/sec.py` | Starý kvartál, pro který SEC vrátí 404, se už znovu nestahuje (dřív ~20 zbytečných dotazů s e-mailem týdně) | méně použití e-mailu |
| `web/index.html` | Tabulka „Drží výhoda i v jiných obdobích?“ | zobrazení stability |
| `lessons` | CHYBA-DAT-REVERSE-SPLIT, MECH-REVERSE-MERGER (AEMD), OVERENI-RAKETY-2026-10-03 (8338.T, MLX.AX, DSV.TO) | ruční ověření se zdroji |

**Stabilita modelu raket (horní 1 % podle „raketa − propad“, data mimo učení):**

| Test | Všechny akcie: raketa / propad / medián | Horní 1 %: raketa / propad / medián |
|---|---|---|
| 2024-01 až 2024-06 | 9,9 % / 12,6 % / +2,3 % | 23,9 % / 21,8 % / −5,2 % |
| 2025-01 až 2025-06 | 17,6 % / 10,9 % / +8,0 % | 37,0 % / 23,5 % / +20,5 % |
| 2025-07 až 2026-04 | 16,7 % / 16,0 % / +1,8 % | 25,1 % / 17,6 % / +0,3 % |

Šance na raketu je ve všech třech obdobích 1,5–2,4× vyšší než u průměrné akcie; směr (medián) jen v jednom ze tří.
Běh #3 nezapsal nové predikce raket (stejná data jako běh #2, stejných 10 firem už predikci má).

**Test:** `python -m pytest` — 89 testů. **Výsledek:** 89/89 prošlo.

---

## 2026-10-03 · v0.4.0 — Audit, vlastní predikce raket na 6 měsíců, SEC + klinické studie, evidence e-mailu

Důvod: pokyn uživatele 2026-10-03 — projít celý kód (stav, chyby se závažností, plán, diagnostika), zjednodušit web,
samostatně předpovídat firmy s růstem desítek až stovek procent za ~6 měsíců, využít všechny dostupné zdroje,
smí se použít e-mail (ale s evidencí, kolikrát a kde), kód průběžně zlepšovat.

| Soubor/modul | Změna | Důvod |
|---|---|---|
| `docs/AUDIT_2026-10-03.md` | Audit všech modulů: stav, 2× CRITICAL, 5× HIGH, 9× MEDIUM, 6× LOW, plán, diagnostika | pokyn uživatele |
| `migrations/0004_email_rockets.sql` | `email_usage` (nemazatelná, jen navyšovaná evidence), u predikcí cíl / šance na propad / základní četnost | §53, rozhodnutí uživatele |
| `contact.py` | E-mail jen pro www.sec.gov a data.sec.gov, každý pokus se před odesláním zapíše; e-mail mimo git | rozhodnutí uživatele 2026-10-03 |
| `sources/sec.py` | SEC EDGAR: XBRL frames (tržby, zisk, akcie, hotovost), full-index (8-K, 10-Q/K, emise, 13D s datem podání) | fundamenty §5 |
| `sources/clinicaltrials.py` | ClinicalTrials.gov: 18 540 studií fáze 2/3, párování sponzorů s kotovanými firmami | biotech katalyzátory |
| `discovery/fundamentals.py` | Znaky k danému dni bez look-ahead (hodnota kvartálu až od podání 10-Q/10-K) | §41 |
| `discovery/rocket.py` | Model raket na 6 měsíců: panel 352 tis. vzorků, WoE + logistická regrese, test mimo vzorek, 5 řazení, test „bez fundamentů“ | pokyn uživatele |
| `discovery/store.py` | `record_rockets`: predikce raket do ledgeru (cíl +50 %, šance, propad, základní četnost), čerstvá cena, TOO LATE filtr, automatické katalyzátory z klinických studií | §42 |
| `update.py` | **C1** predikce mimo energetický vesmír se vyhodnotí; **C2** rakety podle cíle (HIT/MISS/zatím nerozhodnuto) | audit |
| `discovery/cache.py` | **H2** chyba stahování už nesmaže uloženou historii | audit |
| `site.py`, `web/index.html` | **H1** limit 170 kB kvůli zvětšení na serveru; web 12 → 6 sekcí, rakety nahoře, vítězové jen TOP 10, evidence e-mailu | audit, pokyn uživatele |
| `diag.py`, `cli.py` | `diag`, `email`, `sources`; `status --days 45` | audit (diagnostika) |
| `catalysts.py`, `universe.py`, `model.py`, `yahoo.py`, `config.py`, `news.py`, `engine.py` | M1, M2, L1, L2, L6 | audit |
| `CLAUDE.md` | Nová pravidla e-mailu, diagnostika v denní úloze, sobotní krok „zlepšování“ | pokyn uživatele |

**Výsledek modelu raket (test 2025-07 až 2026-04, 100 205 pozorování):** +50 % do 6 měsíců u 16,7 % všech akcií;
horní 1 % podle „raketa minus propad“ 25,1 % (propad 17,6 % vs 16,0 %, medián +0,3 % vs +1,8 %). Mírná výhoda
v četnosti raket, ne jistá výhoda ve směru → predikce WATCH se šancí na raketu i propad. SEC + studie: AUC 0,7325 vs 0,7307.

**Poznámka k ledgeru:** běh objevování #2 (2026-10-03) spustil kód v0.4.0 ještě před zvýšením čísla verze — jeho
predikce mají `model_version = 0.3.0`. Ledger je append-only, zůstávají tak.

**Test:** `python -m pytest` — 86 testů (unit 78, integrační 7, end-to-end 1). **Výsledek:** 86/86 prošlo.

---

## 2026-10-02 · v0.3.0 — Global Growth Pattern, Winners & Emerging Sector Engine

Důvod: druhé zadání uživatele (docs/MASTER_PROMPT_GROWTH_ENGINE.md) + pokyn „projdi tisíce firem, najdi akcie, které
udělaly desítky procent za týden až 6 měsíců, zjisti co tomu předcházelo a jestli se to dalo předpokládat“.

| Soubor/modul | Změna | Důvod |
|---|---|---|
| `docs/MASTER_PROMPT_GROWTH_ENGINE.md` | Doslovně uložené zadání modulu | §56 |
| `discovery/listings.py` | Globální seznam: Nasdaq screener (USA), JPX xlsx (celé Japonsko), ASX CSV, 24 indexů z Wikipedie → 13 110 firem | §3, jen zdarma |
| `discovery/cache.py`, `download.py` | Kompaktní cache (zlib/array), obnovitelné stahování 5 let cen, 3 dotazy/s | §46 |
| `discovery/winners.py` | Rakety (týden/měsíc/3 m/6 m), zrcadlové propady, vítězové 3/6/12/24 m, fáze TOO LATE | §2, §38 |
| `discovery/features.py`, `study.py` | 17 znaků k T0 bez look-ahead, kontrolní skupina 1:5, lift, logistická regrese, test na celé populaci s kontrolou směru, asymetrie raketa − propad, sektorové vlny, skupiny společného pohybu, vyřazení chybných dat | §6–§14, §41 |
| `discovery/news.py` | Příčiny z titulků Google News (EN s filtrem relevance, JP podle kódu akcie), 14 kategorií, cache | §6, §15 |
| `discovery/engine.py`, `store.py` | Běh, známé případy (percentil 5 dní před raketou), nová IPO, velikostní skupiny; zápis do `discovery_runs`; kandidáti do ledgeru JEN se směrovou výhodou | §42–§47, §55 |
| `migrations/0003_discovery.sql` | `discovery_runs` (append-only), `predictions.source`, `discovery_run_id` | §53 |
| `update.py` | Vyhodnocení predikcí po 7/14/30/90/180/365 dnech | §42 |
| `model.py` | Energetický model jen nad firmami hodnotového řetězce | oddělení modulů |
| `web/index.html`, `site.py` | Sekce Globální objevy, Před raketou, Co předcházelo raketám, Vítězové a sektory, nová IPO; dokument `stav/objevy` | §55 |

**Výsledek prvního běhu:** 12 158 firem z 61 zemí, 374 oborů, 18 653 týdenních raket (≥ +30 %), 829 titulků.
Rakety jsou z cen a objemů předvídatelné jen co do velikosti pohybu, ne směru (viz lekce POUCENI-RAKETY-VOLATILITA)
→ do ledgeru zapsáno 0 kandidátů. Ručně ověřeny 2 mechanismy (ABVX klinická data, SBET krypto treasury).

**Test:** `python -m pytest` — 77 testů (unit 69, integrační 7, end-to-end 1). **Výsledek:** 77/77 prošlo.

---

## 2026-10-02 · v0.2.0 — AI → elektřina radar, bezplatná data, samoučící model, denní web

Důvod: zadání uživatele 2026-10-02 (jen bezplatné zdroje, XTB není podmínka, fokus na energii pro AI, jádro, fúzi
a dohody Google; denně aktualizovaný web se starými predikcemi, jejich vyhodnocením a samoučícím modelem).

| Soubor/modul | Změna | Důvod |
|---|---|---|
| `migrations/0002_energy_radar.sql` | Tabulky chain_nodes, company_chain, relationships (append-only), price_bars, sec_*, model_versions, model_runs; benchmark u predikcí a vyhodnocení; zrušen trigger `predictions_xtb_gate` | §24, §25, §53, §58; rozhodnutí uživatele o XTB |
| `config.py`, `ledger.py` | `REQUIRE_XTB_FOR_BUY = False`; vyhodnocení s nadvýnosem vůči S&P 500 | rozhodnutí uživatele; měřitelná predikce |
| `sources/yahoo.py`, `ingest.py` | Bezplatné ceny/objemy/kurzy z Yahoo chart API | jen bezplatné zdroje |
| `universe.py` | 46 firem, 11 článků řetězce, 22 dohod Big Tech a 8 katalyzátorů se zdroji; API pro denní výzkum | výzkum 2026-10-02 |
| `model.py` | 9 faktorů, učení vah z IC (bez look-ahead), kalibrace, test mimo vzorek, verzování vah | §55, §58, §59 |
| `update.py`, `site.py`, `cli.py update` | Denní běh se stavem kroků a daty pro web | §54 |
| `web/index.html` | Webový přehled (artifact, db dokumenty `stav/*`) | zadání uživatele |
| `CLAUDE.md` | Denní úloha a rozhodnutí uživatele | §56 |

**Poznámka k ledgeru:** prvních 5 predikcí (2026-10-02) vzniklo při ostrém běhu během vývoje v0.2.0, ještě před
zvýšením čísla verze — mají `model_version = 0.1.0`, ale počítala je verze vah modelu 1. Ledger je append-only, proto
zůstávají tak, jak byly zapsány.

**Test:** `python -m pytest` — 65 testů (unit 58, integrační 6, end-to-end 1). **Výsledek:** 65/65 prošlo.
Ostrý běh: 53/53 symbolů staženo, model v1, 5 predikcí, data webu ověřena čtením na úrovni `view`.

---

## 2026-10-02 · v0.1.0 — Fáze 1: databáze + projektový stav

| Soubor/modul | Změna | Důvod |
|---|---|---|
| `docs/MASTER_PROMPT.md` | Doslovně uložená specifikace projektu | §56, §71: zadání nesmí žít jen v chatu |
| `stockradar/migrations/0001_initial.sql` | Schéma: companies, listings, xtb_checks, catalysts, predictions, prediction_outcomes, status_changes, lessons, snapshots | §62 Fáze 1 |
| — | DB triggery: ledger, vyhodnocení, historie verdiktů, poučení a snapshoty jsou append-only | §29, §30, §34, §53 |
| — | DB trigger `predictions_xtb_gate`: spekulativní BUY / MAIN PICK jen s XTB kontrolou = ANO | §5, poučení XSPRAY |
| — | CHECK: přesné datum katalyzátoru jen u VERIFIED se zdrojem; odhad = okno | §10, §32 |
| — | Firmy nelze smazat; listing_status + historie tickerů | §60 survivorship bias |
| `stockradar/ledger.py` | Zápis predikcí a vyhodnocení; zákaz BUY na proběhlém/probíhajícím katalyzátoru; look-ahead kontrola; FRESH/STALE cena; XTB kontrola max. 30 dní stará | §2, §5, §19, §28, §52, §59, poučení RARE |
| `stockradar/companies.py`, `catalysts.py`, `lessons.py`, `snapshots.py`, `data_quality.py` | Doménové moduly | §10, §30, §31, §34, §52, §53 |
| `stockradar/state_io.py` | `state/*.jsonl` v gitu jako zdroj pravdy, DB je obnovitelná pracovní kopie | §56 |
| `stockradar/cli.py` | Příkazy init / status / ledger / lessons / snapshot / export / restore / seed-lessons | §54 (základ) |
| `state/` | Založeno 9 učebních případů z §31 + počáteční snapshot; žádné vymyšlené predikce | §31, §71 |

**Test:** `python -m pytest` — 53 testů (unit 48, integrační 4, end-to-end 1).
**Výsledek:** 53/53 prošlo.
