# CHANGELOG (§49)

Formát: Datum · Verze · Soubor/modul · Změna · Důvod · Test · Výsledek

---

## 2026-10-29 · v0.17.5 — Záchranný snímek Nasdaq i z večerního `update`

Důvod: ranní rutina výzkumu (deník raket) se 29. 10. spustila ve 13:48 UTC = 9:48 v New Yorku, kdy už trh obchodoval;
snímek screeneru se během obchodování nebere, a závěr 28. 10. by v deníku chyběl natrvalo (1denní pohyby by se pak
počítaly přes 2 dny). Rutina je plánovaná na 13:13 UTC, do otevření má jen 17 minut a spouští se se zpožděním.

| Soubor/modul | Změna | Test |
|---|---|---|
| `discovery/diary.py` | `safety_snapshot(main, cache)` — oprava starších snímků + `take_snapshot` s referencí z Yahoo (uloží se pod dnem, ze kterého ceny opravdu jsou); chyba sítě vrátí CHYBA, běh nezastaví | `test_moves.py::test_safety_snapshot_from_evening_update_fills_missed_morning` |
| `cli.py` (`update`) | po vyhodnocení výzkumu zavolá `safety_snapshot`; řádek „Snímek Nasdaq“ ve výpisu, `snimek` v deníku běhů | celý `pytest` |

Výsledek: 226 testů prošlo. Ráno (deník) a večer (update) se tak snímek pokusí vzít dvakrát; druhý pokus je „UŽ JE“.

## 2026-10-28 · v0.17.4 — Blokace zdrojů nezmizí z přehledu po 50 dalších bězích

Důvod: denní radar 28. 10. — `python -m stockradar system` přestal ukazovat Senát USA jako BLOKOVÁNO, ačkoli poslední
běh smart money (24. 10.) dostal HTTP 403. Stav se hledal jen v posledních 50 záznamech deníku běhů a denní běhy
(`rakety --pricina`, `research`, `update`) ho odsunuly. Totéž hrozilo u XTB.

| Soubor/modul | Změna | Test |
|---|---|---|
| `hub/registry.py` | `_last_with(conn, klíč)` — poslední běh, jehož souhrn klíč obsahuje, bez limitu 50; používají ho `senate_blocked` a `xtb_blocked` | `test_smartmoney.py::test_senate_block_is_reported_not_fatal` (60 pozdějších běhů jiného příkazu; na staré verzi padá) |

Výsledek: přehled zdrojů znovu ukazuje Senát BLOKOVÁNO (od 2026-10-24T09:14, HTTP 403); 225 testů prošlo.

## 2026-10-26 · v0.17.3 — Experiment N-13: otisk běhu a srovnání souběhu GitHub × Claude

Důvod: týdenní experiment (návrh N-13 z 24. 10.) — uživatel po týdnu souběhu rozhoduje o přepnutí na GitHub, ale běhy se
24. 10. lišily (predikce raket 8 × 4, vyhodnocené karty 0 × 25 — příčina opravena ve v0.17.2) a nebyla kritéria.

| Soubor/modul | Změna | Test |
|---|---|---|
| `provoz.py` (nový) | `fingerprint` — konečný stav běhu (všechny predikce, vyhodnocení, vyhodnocené karty, TOP 10 žebříčků, den dat, verze, chybné kroky, e-mail za den); `compare` — kritéria N-13 předem (shoda deterministických částí, překryv TOP 10 ≥ 0,6 nebo jiný den dat, bez chyb); `report_md` | `test_provoz.py` (4) |
| `cli.py` | `python -m stockradar otisk [--ven soubor]`; `python -m stockradar porovnani` (jen čte větev provoz-zprava; zpráva `docs/provoz/srovnani_DEN.md`; deník běhů) | celý `pytest` |
| `.github/workflows/radar-denni.yml`, `radar-tyden.yml` | krok diagnostiky uloží `zprava/otisk.json` do zprávy běhu | celý `pytest` |

Vyhodnocení po 5 obchodních dnech se stejným dnem dat; o přepnutí rozhoduje uživatel. GitHub ve stínu začíná ze state/
po večerní rutině Claude, proto se srovnává konečný stav, ne „dnes nově“. E-mail v otisku GitHubu obsahuje i řádky Claude
ze state/ (rozdíl ≈ vlastní použití GitHubu).

## 2026-10-25 · v0.17.2 — Ceny se stáhnou znovu, když chybí poslední závěr (ne až po 6 dnech)

Důvod: souběh GitHub × Claude 24. 10. — týdenní běh na GitHubu stáhl ceny jen 4 z 13 281 symbolů („Ke stažení: 4“),
protože cache obnovená ze zkušebního běhu 23. 10. ráno byla podle `fetched_at` mladší než 6 dní. Ceny pak končily
22. 10. → GitHub nevyhodnotil 25 karet z 9. 10. (potřebují závěr 23. 10.) a jeho žebříčky se lišily od našich
(report `docs/agent_vyzkum/reporty/2026-10-25.md`). Stejné riziko měl i kontejner Claude po každém stažení mimo plán.

| Soubor/modul | Změna | Test |
|---|---|---|
| `discovery/download.py` | `pending_symbols`: ke stažení i řady stažené před závěrkou poslední ukončené seance v New Yorku (16:15 místního času, `last_session_close`); pokračování po výpadku sítě dál nestahuje znovu to, co už je po závěrce | `test_sources.py::test_prices_fetched_before_last_session_close_are_refetched` |

## 2026-10-24 · v0.17.1 — Kvalita dat: kotva okna deníku, rozbité řady u modelu raket, fondy u smart money, výpadek Senátu

Důvod: 21. 10. deník zapsal STFS jako raketu +51 % za 21 dní jen proto, že okno začínalo jednodenním propadem
(3,62 → 2,90 → 3,66 USD); proti okolním dnům to bylo +19 až +21 % (report `docs/agent_vyzkum/reporty/2026-10-21.md`).

| Soubor/modul | Změna | Test |
|---|---|---|
| `discovery/diary.py` | `anchor()`: okna 5 / 10 / 21 dní kotví na mediánu závěrů dne i − k a dnů kolem něj (jeden výkyv nerozhoduje); okno 1 den dál proti včerejšku. Platí pro živý deník i historickou studii (sdílené `detect_at`) | `test_diary.py::test_one_day_dip_in_the_window_anchor_is_not_a_rocket` |
| `discovery/moves.py` | `STUDY_VERSION` 3 → 4: historická studie se s novým pravidlem přepočítá | celý `pytest` |
| `smartmoney/sources.py`, `cli.py`, `hub/registry.py` | Senát (efdsearch.senate.gov) vrátil 24. 10. HTTP 403 a shodil celý běh smart money → `fetch_senate` vrátí BLOKOVÁNO (blokace se neobchází), běh pokračuje s dříve staženými hlášeními; stav se zapíše do deníku a `system` ho ukáže u zdrojů | `test_smartmoney.py::test_senate_block_is_reported_not_fatal` |
| `smartmoney/report.py` | aktuální signály vynechají uzavřené fondy (`is_fund`, jako deník u DHY): 24. 10. byl mezi 10 signály PNI (komunální fond, banka jako dealer koupila a týž den prodávala) → predikce #68 zůstává v knize | `test_smartmoney.py::test_closed_end_fund_is_not_a_smart_money_signal` |
| `discovery/rocket.py` | `broken_recent`: dnešní kandidáti raket bez řad s propadem a návratem nebo neupraveným zpětným splitem za 130 dní (kontroly deníku). 24. 10. tak vznikly predikce #62 DLXY a #63 FRGT („volatilita“ 35 a 140 % denně) — zůstávají v knize. Vyřadí 41 z 12 351 řad (0,3 %); učení a test modelu se nemění | `test_rocket.py::test_broken_price_series_is_not_a_rocket_candidate` |

Pravidlo je definice měření (kvalita dat), ne model. **Dopad:** na stejných datech (800 náhodných akcií, ~2 roky) o 3,3 %
méně dnů s raketou a o 4,9 % méně s propadem; historická studie v4 má 11 137 raket a 13 679 propadů (v3: 12 321 a 15 173 —
rozdíl zahrnuje i posun období o týden a nová data). Závěry studie se nemění (po raketě medián −7 % proti trhu za 20 dní,
dál pokračuje 40 %). Už zapsané epizody se nemění (append-only).

## 2026-10-23 · v0.17.0 — Proč se akcie a sektory hýbou: propady, podání u SEC, co následovalo, přehled trhu

Důvod: zadání uživatele 23. 10. 2026 — nekupovat akcie, které udělaly +100 %, ale analyzovat, **proč** vyletěly (nebo
spadly), co následuje po pohybu a proč se hýbal celý sektor; nejdřív projít kód a nic nestavět dvakrát. Inventura: raketový
deník (`diary.py`) sledoval jen rakety 5 / 10 / 21 dní, příčina byla jen AUTO z titulků (44 ze 75 raket žádnou neměly; kde ji
měly a příčina je ručně ověřená, souhlasila v 6 z 10), co
následovalo, se neměřilo, propady ani jednodenní skoky chyběly, deník nebyl na webu a denní pohled na sektory neexistoval
(objevování má jen 6měsíční sektorové vlny a `summarize_causes` jen „udrželo se po 3 měsících“ u týdenních raket z historie).
Proto se rozšiřuje existující deník a jeho tabulka, žádný paralelní modul pro rakety.

| Soubor/modul | Změna | Test |
|---|---|---|
| `migrations/0012_pohyby.sql` (schéma v12) | `rocket_events` + `direction` (+1 raketa / −1 propad, staré záznamy +1), `move_1d`, `rel_volume`; nové append-only tabulky `move_sec`, `move_outcomes`, `move_studies`, `market_days` | `test_moves.py` |
| `state_io.py` | nové tabulky ve `state/`; obnova staršího exportu bez nových sloupců vezme výchozí hodnotu z migrace (dřív by spadla na NOT NULL) | `test_moves.py::test_web_doc_and_old_state_restore` |
| `discovery/diary.py` | jedna funkce `detect_at` pro živý deník i historii; okna 1 / 5 / 10 / 21 dní (raketa +25 / +30 / +40 / +50 %), propady zrcadlově v logaritmech (−20 / −23 / −29 / −33 %, stejně jako zrcadlové propady v objevování); epizoda = firma + směr; objem dne proti běžnému; pořadí podle síly v logaritmech. **Oprava chyby z v0.13.0:** epizoda končila po 21 kalendářních dnech, ale měsíční okno (21 obchodních ≈ 30 kalendářních dní) ten samý skok obsahuje ještě týden poté → stejná raketa by se zapsala podruhé; nově je to stejný příběh, dokud všechna splněná okna začínají před koncem předchozí epizody (`same_story`; v živých datech od 13. 10. se to ještě nestihlo projevit) | `test_diary.py`, `test_moves.py::test_monthly_window_does_not_record_the_same_jump_twice` |
| `discovery/news.py` | nové kódy LEGAL (žaloba, vyšetřování, short report, oprava účetnictví) a DELISTING (bankrot, going concern, upozornění burzy); FDA/EARNINGS/CLINICAL/FINANCING i se slovy propadů (CRL, miss, profit warning, offering priced…) a vysvětlující slovesa propadů (plunge, tumble, sink…) | `test_moves.py`, ruční kontrola titulků |
| `sources/sec.py` | `fetch_submissions` + `recent_filings` (EDGAR submissions API, pole ověřena 2026-10-23) — jen u velkých pohybů, 1 dotaz na pohyb, evidováno v `email_usage` | `test_moves.py::test_attach_sec_one_request_per_move` |
| `discovery/moves.py` (nový) | (1) podání u SEC v okně pohybu s čísly bodů 8-K (2.02 výsledky, 1.01 smlouva, 3.02 prodej akcií, 3.01 burza, 4.02 oprava účetnictví…) → příčina „SEC: typ podání“ (obsah se nečte); (2) výsledek 5 / 20 / 60 obchodních dní po pohybu proti S&P 500; (3) historická studie 5 let se stejnými pravidly — co obvykle následovalo podle směru, jednodenního skoku, objemu, velikosti firmy a podání u SEC (jednou týdně; popis, ne předpověď; survivorship bias uveden); pořadí důvěry příčiny OVĚŘENO > SEC > AUTO; shoda AUTO a SEC s ověřenými příčinami | `test_moves.py` (11) |
| `discovery/market_day.py` (nový) | denní přehled trhu a sektorů ze snímku Nasdaq: pohyb trhu, sektorů a oborů vážený hodnotou (firmy nad 300 mil. USD), šíře, kdo pohyb táhl (podíl 3 firem), výrazné pohyby komodit a dolaru (z ≥ 2) s vazbou z kauzálního radaru (hypotéza), pohyby z deníku v oboru, titulky o tahounech 2 oborů (AUTO, nejvýš 2 dotazy) | `test_moves.py::test_market_day_explains_sector_move` |
| `cli.py rakety` | snímek → rakety i propady → AUTO u 30 nejsilnějších (dřív 10) → podání u SEC (nejvýš 60 dotazů za běh) → výsledky → přehled trhu → historie (týdně); `--bez-sec`, `--bez-historie`, `--historie-znovu`; píše `stav_pohyby.json` | `test_cli.py` |
| `site.py`, `web/index.html` | nový dokument `stav/pohyby` a sekce „Proč se akcie a sektory hýbou“ (první v Další analýzy): trh a sektory dne, obory s vysvětlením, rakety / propady (10 + Zobrazit všech) s příčinou a odkazem na podání SEC, co následovalo, historie 5 let, živé výsledky a spolehlivost příčin | `test_moves.py`, kontrola v Chromiu |
| `hub/evidence.py`, `hub/integrate.py`, `hub/registry.py` | centrum zná propady a příčinu ze SEC (kontext, směr 0); otisk vstupů i s `move_sec` | `test_diary.py::test_hub_shows_rockets_as_context_but_not_data_errors` |
| `tools/github_beh.py` | stránka publikuje i `stav_pohyby.json`; oznámení na telefon: trh dne a největší raketa / propad s příčinou | `test_github_provoz.py` |

**Opravy z prvního týdenního běhu na GitHubu (23. 10., běh 39899471371):**

| Soubor/modul | Změna | Test |
|---|---|---|
| `cli.py` (nový příkaz `ceny`), `radar-tyden.yml` | databáze ze state/ nemá ceny (price_bars nejsou ve state/) → objevování nezapsalo kandidáty ani predikce raket, smart money nezapsalo signály („Chybí cena S&P 500“) a signály spadly; nyní se po založení databáze stáhnou ceny sledovaných firem, S&P 500 a kurzů (`ceny`, v dalších jobech `--jen-kdyz-chybi`) | `test_cli.py::test_signals_without_spy_are_blocked` |
| `cli.py signals`, `signals/regime.py` | bez cen S&P 500 hlásí BLOKOVÁNO a nic nezapíše (dřív `IndexError` v `market_view`); `market_view` bez SPY vrací NEOVĚŘENO | `test_smartmoney.py::test_market_view_without_spy_is_unverified` |
| `smartmoney/sources.py` | SEC přesunula čtvrtletní sady Form 3/4/5 od 2026Q2 do složky `datastandardsinnovation` (ověřeno na stránce SEC 2026-10-23) → nejdřív nová složka, při 404 stará (dřív 2026Q2 a Q3 chyběly) | `test_smartmoney.py::test_insider_zip_tries_new_sec_folder_then_old` |
| `radar-tyden.yml` | `pdftotext` (poppler-utils) pro výkazy Sněmovny — na GitHubu chyběl (Sněmovna VYPNUTO) | běh na GitHubu |

**Výsledek:** 212 testů prošlo lokálně. Z prvního týdenního běhu ověřeno: stažení 13 097 řad z Yahoo (~73 min), SEC (835 tis.
podání v indexu), ClinicalTrials.gov, Senát (305 výkazů) a **xtb.com z GitHubu funguje** (63 dotazů, 0 chyb — ze serveru Claude
je od 11. 10. blokované).

**Zkušební denní běh na GitHubu se skutečnými daty (23. 10., běh 39911979271) — co ukázal a co se hned opravilo:**

| Zjištění | Oprava | Test |
|---|---|---|
| Přehled trhu za „22. 10.“ ukazoval trh +0,59 % a technologie +1,3 %, ale S&P 500 ten den padl o 1,2 % (Nasdaq −2,6 %; ABC News / AP). Snímek byl ve skutečnosti z 21. 10. (S&P +0,6 %): screener Nasdaq vydá závěr dne D až ráno D+1, takže večerní běh na GitHubu zapisoval ceny z předchozího dne pod dnešní datum (rutina Claude ve 14:13 je měla správně) | `diary.reference_closes` + `data_day`: snímek se uloží pod dnem, na který jeho ceny sedí podle závěrů z Yahoo (`price_bars`); nesedí-li na žádný, neuloží se (NEOVĚŘENO); `repair_snapshots` přejmenuje nebo smaže starší snímky se špatným dnem; přehled trhu se nezapíše, když se celý trh od S&P 500 téhož dne liší o víc než 1 p. b. Večerní běh na GitHubu tak má deník a přehled za předchozí obchodní den | `test_moves.py::test_snapshot_is_stored_under_the_day_its_prices_are_from`, `::test_market_day_refuses_snapshot_that_disagrees_with_sp500` |
| FRGT „+558 % za týden“ s objemem 0,1× běžného — ve skutečnosti zpětný split 1:10 od 19. 10. 2026 (finviz), který Yahoo neupravil a stávající detektor nepoznal (poměr nebyl přesně násobkem) | `diary.unadjusted_split`: skok ≥ 2,9× za den, po kterém se obchoduje pod polovinu běžného počtu kusů = chyba dat, ne raketa (v den splitu bývá objem vysoký, proto rozhoduje medián od skoku dál; živě do dneška, historie 5 dní dopředu; studie verze 3). První verze s objemem jen v den skoku FRGT nepoznala (druhý zkušební běh) | `test_moves.py::test_reverse_split_with_low_volume_is_not_a_rocket` |
| DKI „−98 % za měsíc“ — DarkIris měla zpětný split 1:50 k 22. 10. 2026 (pluang.com) a Yahoo ho zjevně upravil jen u části dnů | `merge_series`: když snímek Nasdaq a Yahoo za týž den nesedí o víc než 25 %, řada se přeskočí jako split / chyba dat; na webu varování u pohybu, v jehož okně je 8-K bod 3.03 / 5.03 (změna práv akcionářů / stanov = často zpětný split) | `test_diary.py::test_merge_series_rejects_split_and_stale_data` |
| První běh zachytil všechny propady posledního měsíce najednou (201 propadů, 27 raket, 206 nových epizod) — jednorázové dohnání, v dalších dnech jen nové | — (v režimu `stin` se dohnání opakuje každý večer, protože GitHub nic neukládá) | — |
| Podání u SEC: 60 dotazů, 60 zapsáno, 0 chyb (čeká 221) — e-mail dnes 60× jen data.sec.gov | limit 60 za běh ponechán | — |

Třetí zkušební běh (39913941561) po opravách: snímek uložen pod 21. 10. (přehled trhu +0,59 % = S&P 500 21. 10. +0,6 %),
FRGT ani DKI už mezi pohyby nejsou (vyřazeno kvůli splitu / chybě dat 21 řad místo 15), podání u SEC 60 / 60 bez chyby.
E-mail pro SEC při třech zkouškách: 3 × 60 dotazů na data.sec.gov.

Historická studie na skutečných datech (12 235 raket a 15 142 propadů, 11/2021–10/2026, popis, ne předpověď):
po raketě byl medián výnosu proti S&P 500 −2,3 % po 5, −6,9 % po 20 a −15,0 % po 60 obchodních dnech (dál nahoru šlo
jen 42 / 40 / 37 %); nejhůř rakety s emisí akcií (−29,5 % po 60 dnech) a malé firmy pod 300 mil. USD (−30,7 %), nejlíp
velké firmy (−1,6 %) a rakety s výsledky 10-Q/10-K (−9,3 %). Je to v souladu se známým „efektem MAX“ (akcie s extrémním
denním růstem pak v průměru zaostávají; Bali, Cakici a Whitelaw 2011), ale seznam firem je dnešní (survivorship bias) a pohyby se shlukují v čase.

## 2026-10-23 · v0.16.0 — Provoz na GitHubu bez Claude (Actions + Pages)

Důvod: rozhodnutí uživatele 23. 10. 2026 — radar má běžet sám na serveru zdarma, denně se aktualizovat a učit a stránka se
má otevřít v obyčejném prohlížeči (jako FXBOT). Části s AI (ruční ověřování zpráv, zlepšování kódu, výzkum agenta) se
vypouštějí; týden souběhu s rutinami Claude; e-mail pro SEC v secretu GitHubu. Modely, ledger a centrum se nemění.

| Soubor/modul | Změna | Test |
|---|---|---|
| `.github/workflows/radar-denni.yml` (nový) | po–pá 22:47 Praha: `init` ze state/, `update`, `causal`, `rakety`, `diag`, `email`; stránka na GitHub Pages; cache `data/market_cache.db`; zpráva o běhu ve větvi `provoz-zprava` | běh na GitHubu |
| `.github/workflows/radar-tyden.yml` (nový) | sobota 9:41 Praha: `discover --universe --download` → `smart-money` + `funds` → `signals`, `update`, `causal`, `diag`, pytest (3 joby po ≤ 6 h, DB mezi nimi jako artefakt) | běh na GitHubu |
| `.github/workflows/radar-testy.yml` (nový) | `python -m pytest` při každé změně | — |
| `tools/github_beh.py` (nový, nástroj provozu mimo balíček) | klíče běhů (večer od 21:30, sobota od 9:00 Praha), režim `provoz/github.json` (stin / ostry), sestavení stránky (odmítne data s e-mailovou adresou), kontrola v Chrome, souhrn a oznámení přes ntfy | `test_github_provoz.py` (15) |
| `web/index.html` | mimo claude.ai načte `stav_*.json` a `provoz.json` vedle sebe a ukáže varování, když je po termínu další aktualizace; v Claude beze změny | kontrola v Chromiu na skutečných datech |
| `cli.py` `cmd_causal` | prázdná cache bez cen akcií (nový server): příkaz skončí kódem 1 s hlášením BLOKOVÁNO dřív, než se zapíše test řetězců, karty a predikce (dřív `ValueError: ordinal must be >= 1` na GitHubu, ale až po `record_study`) | `test_cli.py::test_causal_without_stock_prices_is_blocked` |
| `provoz/github.json`, `requirements-provoz.txt`, `docs/GITHUB_PROVOZ.md` (nové) | režim stin; pytest a playwright jen pro testy a kontrolu stránky | — |

**Výsledek:** stránka z dnešních dat (10 dokumentů z artefaktu) prošla kontrolou v Chromiu včetně šířky telefonu. První denní
běh na GitHubu (23. 10.): testy prošly, `update` OK (Yahoo 99/99, model v16), snímek Nasdaq OK (6 630 akcií), `causal` padal na
prázdné cache (opraveno výše; cache se naplní prvním sobotním objevováním), stránka prošla kontrolou. xtb.com, SEC, Senát a
stahování 13 000 firem z GitHubu NEOVĚŘENO do prvního týdenního běhu.

## 2026-10-20 · v0.15.2 — Kauzální radar: zprávy o komoditě jen v tržním nebo výrobním smyslu

Důvod: denní radar 20. 10. — platina dostala stav PŘÍLEŽITOST jen ze zpráv (5 nových příběhů, scénář „narušení
nabídky“). Titulky byly o kontejnerové lodi „HMM Platinum“, o požáru lodi plující do Jižní Afriky (počítán jako zpráva
z výrobní země) a o dostihovém koni „Platinum Attack“ — o kovu ani jeden.

| Soubor/modul | Změna | Test |
|---|---|---|
| `causal/events.py` | `relevant()`: příběh se do zprávového pulsu počítá, jen když titulek (bez názvu zdroje za „ - “) zmiňuje komoditu a zároveň tržní, výrobní nebo pracovní kontext (cena, trh, důl, těžba, nabídka, export, clo, úroda, sklizeň, rafinerie, závod, stávka, pracovníci…); dopravní a makro uzly kontext nepotřebují, přeprava bere i „ship/vessel“. Puls ukazuje i počet a ukázky vyřazených titulků (`mimo_tema_7d`, `mimo_tema_ukazky`) | `test_causal.py::test_news_pulse_ignores_headlines_where_commodity_word_is_a_name` |

**Výsledek (běh #22):** platina 0 relevantních příběhů (dřív 5) → žádná příležitost; radar dnes 15 karet, 0 příležitostí.
Kontrola vyřazených titulků: správně pryč např. bodnutí v kukuřičném bludišti, šlechtění pšenice, požár stáje; slova
stávka/pracovníci a „ship“ u přepravy doplněna po první kontrole (stávka v dole Escondida, útok na loď v Černém moři se
jinak ztrácely) — seznam slov je tedy upravený podle dnešních titulků, ne předem. Predikce #35 z běhu #20 (platina →
drahé kovy ↑) zůstává v knize beze změny (append-only) a vyhodnotí se normálně.

## 2026-10-19 · v0.15.1 — Experiment N-5: živá kalibrace karet a pokrytí intervalu (statický × ACI)

Důvod: denní výzkum agenta (směr S2, návrh N-5, týdenní experiment) — 17. 10. se poprvé vyhodnotily živé karty;
pravděpodobnosti na webu se dosud proti skutečnosti neměřily.

| Soubor/modul | Změna | Test |
|---|---|---|
| `signals/calibration.py` (nový) | Brier a dovednost proti základní četnosti, kterou běh znal předem (`zaklad.up5`); tabulka spolehlivosti po 10 p. b.; pokrytí intervalu q20–q80 (cíl 60 %) statické × ACI (Gibbs & Candès, krok 0,005 předem; kvantil jen z dřívějších týdnů) — jen měření, karty se nemění | `test_calibration.py` (2) |
| `cli.py` | příkaz `python -m stockradar kalibrace`; souhrn i na konci `signals` | celý `pytest` |
| `site.py` | dokument `stav/signaly` má u modelu `kalibrace_ziva` | celý `pytest` |

**Start (1 týden, 65 karet 14 dní z 5. 10.):** předpověď P(+5 %) v průměru 0,30, skutečně 0,15; Brier 0,154 proti
0,136 u základní četnosti (dovednost −0,13); interval q20–q80 pokryl 43 % (cíl 60 %). Jediný týden v klesajícím trhu —
vyhodnocení až po 8 a 16 týdnech (kritérium v N-5).

## 2026-10-17 · v0.15.0 — Ruční výzkum se vyhodnocuje proti cenám (zpětná vazba pro roli VÝZKUM)

Důvod: týdenní zlepšení z `docs/ARCHITEKTURA_2026-10-07.md` (kap. 6, „ruční výzkum se zatím nevyhodnocuje proti cenám“).
Role „Ruční výzkum se zdrojem“ byla vždy NEOVĚŘENO bez možnosti se ověřit; směrové záznamy (např. riziko u 8 rafinerií
z 6. 10., horizont 120 dní) by po horizontu zůstaly bez výsledku.

| Soubor/modul | Změna | Test |
|---|---|---|
| `migrations/0011_research_outcomes.sql` | kniha `research_outcomes` (append-only): výnos akcie a S&P 500 (SPY) od prvního obchodního dne od zveřejnění do konce horizontu, nadvýnos ve směru výzkumu, HIT/MISS | `test_hub.py::test_research_is_scored_against_sp500_after_its_horizon` |
| `hub/feedback.py` | `evaluate_research` (jen firmy se směrem ±1, jednou na záznam, čeká, dokud ceny nedosahují konce horizontu); role VYZKUM bere živé výsledky stejným pravidlem jako ostatní (≥ 30 v ≥ 6 týdnech); metrika ukazuje, kolik je vyhodnoceno a kdy končí první horizont | dtto |
| `cli.py` (`update`) | krok „Vyhodnocení výzkumu“ po denní aktualizaci | celý `pytest` |
| `hub/integrate.py`, `state_io.py` | otisk centra a export `state/` zahrnují `research_outcomes` | celý `pytest` |
| `causal/commodities.py`, `causal/radar.py`, `web/index.html` | ověřené podíly výrobců z primárních zdrojů (`VERIFIED_PRODUCERS`): hliník a železná ruda — USGS Mineral Commodity Summaries 2026; kukuřice a pšenice — USDA FAS World Agricultural Production (říjen 2026); cukr — USDA FAS Sugar (květen 2026); prasata — USDA FAS Livestock and Poultry (9. 10. 2026); karta ukazuje stav OVĚŘENO se zdrojem a podíly; do seznamů doplněny země s podílem ≥ 3 % (železná ruda Írán, kukuřice Indie a EU, pšenice Pákistán, cukr USA, Pákistán a Rusko, prasata Vietnam a Rusko) | `test_causal.py::test_verified_producer_shares_have_primary_source` |
| `sources/yahoo.py` | měna USX (komoditní futures v amerických centech) = dílčí jednotka USD → objevování už nezkouší neexistující kurz `USX=X` (HTTP 404 v každém běhu) | `test_sources.py::test_us_cent_quotes_need_no_fx_download` |

**Stav:** 8 směrových záznamů o firmách (rafinerie ↓ z 6. 10.; záznamy bez směru a o komoditách se nepočítají); první horizont
končí 2027-02-03 → do té doby role VÝZKUM zůstává NEOVĚŘENO, ale už ví, kdy a jak se ověří.

## 2026-10-16 · v0.14.4 — Raketový deník: chyba dat „propad a návrat“; registr testů + vyhodnocení modelů

Důvod: denní výzkum agenta 2026-10-16 — největší nová „raketa“ VWAV (+964 % za 21 dní) byla chyba dat: zpětný split
1:20 (8-K 18. 9. 2026), který Yahoo upravilo jen u části dnů (9,06 → 0,53 → 0,38 → 7,32 USD). Detektor splitu to
nepoznal, protože neupravené dny měly obrovský objem. Registr testů (N-1) ještě neměl vyhodnocení modelů.

| Soubor/modul | Změna | Test |
|---|---|---|
| `discovery/diary.py` | `glitch`: pád aspoň 5× za den a návrat do 5 dnů aspoň na 30 % původní ceny = chyba dat → řada se v deníku přeskočí (z 5 938 řad zasáhne 4: VWAV, BURU, HLSQ, WHLR) | `test_diary.py::test_partly_adjusted_split_is_a_data_error_not_a_rocket` |
| `hub/multitest.py` | `model_evaluation_rows`: všechny t z `model_evaluations` (u opakovaného vyhodnocení jen poslední, bez zdvojení už evidovaných) | `test_multitest.py::test_model_evaluation_rows_keep_latest_rerun_and_skip_registered` |
| `docs/testy_hypotez.jsonl` | +111 testů (celkem 592) | `test_multitest.py::test_registry_file_is_valid` |

**Výsledek:** přísné pravidlo beze změny závěru — varování 1 m (q 0,038) a 6 m (q 0,017) procházejí, nákup insiderů
(q 0,22) a fondy 13F (q 0,56) ne. Váhy se nemění (N-1 jen zapisuje).

## 2026-10-15 · v0.14.3 — Kauzální radar: zprávy potvrzují scénář „narušení nabídky“ jen u hlavních výrobců

Důvod: denní rutina 2026-10-15 — 15 zpráv o náletu na zlatý důl na hranici Súdánu a Egypta (72 mrtvých) spustilo
scénář „zlato ↑ → těžaři zlata ↑“ (skóre 50, nejvyšší příležitost dne), i když Súdán mezi hlavními výrobci zlata v grafu
není a cena zlata za 4 týdny klesla o 4,8 %. Scénář je „narušení nabídky → cena roste“, takže má smysl jen tam, kde
zprávy zmiňují hlavní výrobní zemi.

| Soubor/modul | Změna | Test |
|---|---|---|
| `causal/events.py` | `news_pulse` počítá `u_vyrobcu_7d` = nové příběhy, jejichž titulek zmiňuje hlavní výrobní zemi komodity (seznam NEOVĚŘENO) | `test_causal.py::test_news_confirm_supply_scenario_only_at_major_producers` |
| `causal/radar.py` | zprávy bez vazby na výrobce = karta „SLEDOVAT (zprávy netýkají hlavních výrobců)“, bez příležitosti a predikce; starší data bez počtu jako dřív | dtto |

**Výsledek (běh #16):** zlato a benzín → SLEDOVAT; měď (stávky v Chile: Escondida, Centinela — 10 zpráv u výrobců) a
pšenice dál PŘÍLEŽITOST. Běh #15 (před opravou) zapsal 2 kauzální predikce — obě u mědi (#33 → metal mining ↑, #34 → other metals ↑); pro zlato predikce nevznikla.

## 2026-10-15 · v0.14.2 — Registr testů doplněn o celou studii smart money (experiment N-1)

Důvod: denní výzkum agenta (směr S1) — registr měl jen 13 testů E1–E4, korekce na mnohonásobné testování byla mírnější,
než měla být. Pravidlo dané předem: zapsat KAŽDOU t-statistiku studie smart money, bez výběru podle výsledku.

| Soubor/modul | Změna | Test |
|---|---|---|
| `hub/multitest.py` | `smart_money_rows(result, run_id, datum)`: všechny skupiny s `t` / `t_mesice` jako řádky registru (průzkumné, `predem = False`) | `test_multitest.py::test_smart_money_rows_take_every_group_with_t` |
| `docs/testy_hypotez.jsonl` | +468 testů ze `smart_money_runs #4` (celkem 481) | `test_multitest.py::test_registry_file_is_valid` |
| `docs/VYZKUM.md`, `docs/agent_vyzkum/*` | výsledek, 4 nová zjištění, návrhy N-6 a N-7, report 2026-10-15 | `test_agent_research.py` |

**Výsledek:** přísné pravidlo (t ≥ 3 a q (BY) ≤ 0,10) dál splňují varování 1 m (q 0,052) a 6 m (q 0,023); **nákup
insiderů už ne** (q 0,24, dříve 0,046). Váhy rolí se nemění (N-1 jen zapisuje do 2027-01-06).

## 2026-10-14 · v0.14.1 — Kauzální radar: firmy jen s vlastní citlivostí na komoditu; příkazy odolné vůči zavřené rouře

Důvod: denní rutina 2026-10-14 — karta DRYBULK (sazby lodní přepravy sypkých nákladů ↓) ukazovala jako firmy oboru
„marine transportation“ General Dynamics, Royal Caribbean a Viking (Nasdaq je řadí do stejného oboru). Firmy se
vybíraly jen podle velikosti, ne podle toho, zda se s komoditou opravdu hýbou → v centru 15 rozporů, z toho většina
falešných (výletní lodě, offshore služby). Druhá chyba: `python -m stockradar hub | head -1` zapsal do deníku běhů
CHYBU (BrokenPipeError), i když výpočet proběhl (stejně 2026-10-13 u `rakety`).

| Soubor/modul | Změna | Test |
|---|---|---|
| `causal/exposure.py` | týdenní řady i pro jednotlivé akcie (výnos nad mediánem trhu); `firm_beta` = vlastní beta a t akcie na komoditu za 78 týdnů do daného týdne (stejný výpočet jako u oborů, bez pohledu do budoucnosti) | `test_causal.py` |
| `causal/radar.py` | `firms(..., sens, sign)`: projde jen firma se stejným znakem bety jako obor a \|t\| ≥ 2; u příležitosti pole `firmy_pravidlo`; prázdný seznam, když žádná firma neprošla | `test_causal.py::test_radar_lists_only_firms_with_own_sensitivity_to_the_commodity` |
| `causal/memo.py` | `CALC_VERSION` 2 (jednorázový přepočet paměti výpočtů) | — |
| `hub/evidence.py`, `hub/integrate.py` | důkaz radaru s ověřenými firmami (`jen_vybrane`) dostanou jen tyto firmy, ne celý obor; starší běhy beze změny | `test_hub.py::test_causal_industry_evidence_reaches_only_firms_with_own_sensitivity` |
| `cli.py` | `QuietPipe`: po zavření roury se další výstup tiše zahodí, příkaz doběhne a deník zapíše skutečný výsledek | `test_cli_pipe.py` (2) |
| `web/index.html` | u příležitosti bez firem text „žádná firma oboru nemá vlastní prokázanou citlivost“; pravidlo v nápovědě | — |

**Výsledek (běh radaru #14, data k 2026-10-09):** DRYBULK → FRO (t 2,4), SBLK (t 3,6), CDLR (t 2,5); dolar → NEM, AEM,
B a SCCO, RIO, FCX (všechny t ≤ −2,2); kukuřice → maso: žádná firma neprošla. Test řetězců a citlivost oborů beze změny
(stejné výsledky učení / validace / testu). Centrum: rozpory 15 → 6 (zbývají SBLK, FRO a rafinerie DINO, MPC, DK, VLO).
Predikce v ledgeru i kauzální predikce (na úrovni oboru) se nemění.

## 2026-10-14 · v0.14.0 — Experiment N-1: registr testů hypotéz a přísné pravidlo (t ≥ 3, Benjamini–Yekutieli)

Důvod: denní výzkum agenta (docs/agent_vyzkum, návrh N-1): role se ověřují při t ≥ 2, ale testů děláme desítky →
riziko falešných objevů (Harvey–Liu–Zhu: hranice t > 3; Benjamini–Yekutieli: FDR i při závislých testech).

| Soubor/modul | Změna | Test |
|---|---|---|
| `docs/testy_hypotez.jsonl` (nový) | registr všech testů hypotéz (zatím 13 z E1–E4; studie smart money a varianty modelů doplnit) | `test_multitest.py::test_registry_file_is_valid` |
| `hub/multitest.py` (nový) | p-hodnoty, q-hodnoty BH a BY; přísné pravidlo = t ≥ 3 a q (BY) ≤ 0,10 v rodině testů + rolí | `test_multitest.py` (3) |
| `hub/feedback.py`, `cli.py` (`system`), `site.py`, `web/index.html` | u každé role pole `prisne` a sloupec „Přísně“ — jen se zapisuje, o váze dál rozhoduje stávající pravidlo (experiment do 2027-01-06) | celý `pytest` |

**Start experimentu:** přísně prošly varování 1 měsíc (t 3,68), varování 6 měsíců (t 3,98) a nákup insiderů (t 3,05);
neprošla role „fondy 13F u malých firem“ (t 2,56).

## 2026-10-13 · v0.13.0 — Raketový deník (rakety za 5 / 10 / 21 dní + ověřené příčiny)

Důvod: zadání uživatele 2026-10-13 („když najdeš rakety za týden, 14 dní nebo měsíc — analyzuješ proč a zanášíš to do
modelu?“). Dosud se příčiny určovaly jen automaticky z titulků jednou týdně a do modelu se nedostávaly.

| Soubor/modul | Změna | Test |
|---|---|---|
| `discovery/diary.py` (nový) | Denní snímek Nasdaq screeneru (1 dotaz, jen po závěru obchodování, svátek se pozná podle shodných cen) + týdenní ceny Yahoo → rakety ≥ +30 % / 5, ≥ +40 % / 10, ≥ +50 % / 21 obchodních dní (likvidní, ≥ 1 USD); kontrola kvality dat (`study.anomalous`), dorovnání zpětných splitů (`winners.adjust_reverse_splits`), vyřazení fondů, kontrola návaznosti snímku na Yahoo; epizoda = firma v 21 dnech; AUTO příčina z titulků | `test_diary.py` (7) |
| `migrations/0010_rocket_diary.sql` | `rocket_events` a `rocket_causes` (append-only; příčina jen s https zdrojem a datem) | `test_diary.py` |
| `cli.py` (`rakety`) | detekce + zápis ověřené příčiny (`--pricina ID --kod … --url … --datum …`, `--neovereno`) | celý `pytest` |
| `hub/*`, `state_io.py`, `web/index.html` | rakety jako kontext v centru (chyby dat se nezobrazují), modul „Raketový deník“ v registru (čerstvost podle snímku), export do `state/` | `test_diary.py::test_hub_shows_rockets_as_context_but_not_data_errors` |

**První běh (data do 2026-10-12):** 5 938 řad, 286 fondů a 13 vadných řad vyřazeno, 48 epizod zapsáno před opravou
filtrů — 2 z nich (NFE chyba dat, DHY zpětný split 1:10) otevřeně označeny jako CHYBA_DAT. Ověřeno z primárního zdroje
(SEC 8-K): KOD (fáze 3 DAYBREAK, klinická data) a PDSB (PIPE vedené Nant Capital, nový velký investor); SVRN, NCPL,
MEDS jen NEOVĚŘENO.

## 2026-10-12 · v0.12.2 — Oprava: firmy ze žebříčků vždy v přehledu centra

Důvod: denní běh 2026-10-12 našel, že první firmy žebříčků (KMX, MPC, ACDC, DINO) chyběly v dokumentu `stav/prehled`,
takže po rozkliknutí na webu nebyl vidět postoj centra. Zkracování dokumentu (v0.12.0, rezerva 20 %) ubíralo firmy se
slabými důkazy včetně firem ze žebříčků.

| Soubor/modul | Změna | Test |
|---|---|---|
| `site.py` (`build_prehled_doc`) | Firmy, které web ukazuje (role `…:vyber`, signály smart money), se nezkracují; ostatní od nejslabších. Když by ani to nestačilo, platí tvrdý limit dokumentu | `test_site_limits.py::test_prehled_trimming_keeps_firms_shown_on_web` |

## 2026-10-11 · v0.12.1 — Web: nejvýš 10 firem v každé sekci

Důvod: rozhodnutí uživatele 2026-10-11 („zkrať každou sekci aspoň o pět firem, minimum je 10“). Zvoleno 10: model
v horním pásmu firmy přesně nerozliší a výběr („vyber“) zatím není ověřený — kratší seznam je přehlednější.

| Soubor/modul | Změna | Test |
|---|---|---|
| `site.py` (`WEB_TOP = 10`) | Žebříčky 14 dní, 1 měsíc, 6 měsíců (všechny i velké firmy), rakety v žebříčku, „nejvyšší riziko pádu“, události, signály smart money, politici a obchody Pelosi: 20 / 12 → 10. Modely, ledger, centrum a vyhodnocení dál pracují s TOP 20 (měření se nemění) | `test_site_limits.py` |
| `web/index.html` | Karty raket: 10 nejnovějších běžících (20 → 10); výsledky predikcí a celý energetický řetězec: prvních 10 + tlačítko „Zobrazit všech“ (historie zůstává veřejná); změny postoje 20 → 10 | vykreslení v prohlížeči s daty: všechny sekce ≤ 10, tlačítko 10 → 46 |

## 2026-10-11 · v0.12.0 — Nový modul: nejsilnější sázky fondů (SEC 13F, výzkum E4)

Důvod: autonomní výzkum nového bezplatného typu informace ([docs/VYZKUM.md](docs/VYZKUM.md), E4). Hypotéza a protokol
zapsány a commitnuty PŘED stažením dat; párování zkontrolováno na jménech PŘED pohledem na výnosy.

| Soubor/modul | Změna | Test |
|---|---|---|
| `sources/sec13f.py` (nový) | SEC Form 13F Data Sets (22 čtvrtletí, ~90 MB/sada) zredukované na pozice správců s 20–500 akciemi (bez opcí, bez dodatků, jen včas podané), konsenzus vah nezávislý na jednotkách; CUSIP → symbol ze souborů SEC Fails-to-Deliver; hotové sady se nestahují znovu, zip se maže | `test_sec13f.py` (7) |
| `discovery/bestideas.py` (nový) | Nejsilnější sázka správce = největší (váha − běžná váha) mezi 20 největšími pozicemi; vyřazení fondů, znovu přidělených tickerů a chybných CUSIP správců (kontrola jména); studie událostí (G1/G2/G3, poloviny, Newey-West); aktuální sázky na malé firmy | `test_sec13f.py` |
| `migrations/0009_funds.sql`, `cli.py` (`funds`), `state_io.py` | Tabulka `fund_runs` (append-only); příkaz `funds` (bez nové sady přeskočí, deník) | celý `pytest` |
| `hub/evidence.py`, `hub/feedback.py`, `hub/registry.py`, `hub/integrate.py`, `diag.py` | Důkazy `FONDY_13F` (sázky na malé firmy, strop váhy 0,5), role `FONDY_13F:sazka` (t = menší z obyčejného a Newey-West), modul „fondy“ a zdroj „SEC 13F“ v registru, otisk centra a diagnostika znají `fund_runs`, poučení #21 | `test_hub.py::test_funds_role_uses_conservative_t_and_evidence_is_capped` |
| `contact.py` | Přerušený přenos velkého souboru (`IncompleteRead`) se opakuje (dřív spadl celý běh); každý pokus se dál eviduje | `test_sources.py::test_interrupted_transfer_is_retried_and_counted` |
| `site.py` | Dokument `stav/prehled` drží rezervu 20 % pod limitem (ubírají se nejslabší firmy): 169 kB → 135 kB | `diag` |
| `web/index.html` | Název modulu „Fondy 13F“ v důkazním řetězci | kontrola syntaxe |

**Výsledek E4:** POTVRZENO podle předem daného pravidla (+0,9 % za 6 m nad podobnými akciemi, t 3,4, Newey-West 3,1),
ale malé a od 2024 slabší (t 1,1); šance na +40 % není vyšší než u všech akcií. Malé firmy +1,9 % (t 2,7).

## 2026-10-11 · v0.11.1 — Výzkum E3: federální zakázky USA (nový bezplatný zdroj USAspending.gov)

Důvod: autonomní výzkum nového typu informace (deník [docs/VYZKUM.md](docs/VYZKUM.md), E3).

| Soubor/modul | Změna | Test |
|---|---|---|
| `sources/usaspending.py` (nový) | Transakce federálních zakázek (zdarma, bez klíče, 1 dotaz/s): po měsících ≥ 10 mil. USD a cíleně pro menší firmy ≥ 1 mil. USD; částka transakce = známá v den akce (ne „Award Amount“ s pozdějším navýšením); hotové měsíce/firmy se znovu nestahují | `test_contracts.py::test_fetch_month_pages_until_amount_falls_below_limit` |
| `discovery/contracts.py` (nový) | Studie událostí (z `smartmoney/events.py`): nová zakázka / tržní hodnota k danému dni → výnos 6 m proti kontrole ze stejného oboru; přesná shoda jména příjemce, jedna událost na firmu a měsíc | `test_contracts.py` (4) |
| `lessons` (#20) | POUCENI-ZAKAZKY-SHODA-JMEN: hlavní hypotéza má jen 6 případů (NEOVĚŘENO); volné párování jmen vyrobilo falešný výsledek (+62 % → +4,5 %) | ostrý běh 874 událostí |

**Výsledek:** NEOVĚŘENO. Zakázka ≥ 10 % hodnoty firmy jen 6× za 5,7 roku; žádná skupina nemá stabilní výhodu (velké
firmy +1,9 % nad kontrolou, t 1,3, v letech 2024+ jen +0,2 %). Zakázky se do modelu ani centra nezapojují.

## 2026-10-11 · v0.11.0 — Autonomní výzkum: experiment spojení rolí, nezávislý test raket, radar z denních cen

Důvod: zadání uživatele 2026-10-11 (autonomní režim: hypotézy, experimenty, učení z výsledků). Deník:
[docs/VYZKUM.md](docs/VYZKUM.md).

| Soubor/modul | Změna | Test |
|---|---|---|
| `signals/combo.py` (nový) | Experiment E1: nákup insiderů × varování SIGNAL_6M, předem daná pravidla, výběr na validaci, zamčený test jednou (INSIDER_X_6M). Výsledek: filtr snižuje riziko −25 % (6 % proti 14 %), ale i šanci na +40 % (5 % proti 12 %); výnos bez výhody | ostrý běh, `model_evaluations` |
| `discovery/rocket.py` | Pravidlo řazení raket se vybírá na validačních pololetích před testem (dřív z 5 variant přímo na testu → test nebyl nezávislý); walk-forward hodnotí všechna řazení | `test_rocket.py::test_ranking_is_chosen_on_validation_folds_not_on_test` |
| `causal/exposure.py`, `causal/radar.py`, `cli.py` | Šok komodity z denních cen k dni běhu (`daily_shock`), ne jen k poslednímu dni cen akcií; karta nese `sok_k_datu` a `obory_k_datu` | `test_causal.py::test_daily_shock_sees_moves_after_last_stock_day` |
| `lessons` (#18), `hub/integrate.py` | Poučení POUCENI-KOMBINACE-INSIDER-6M se v centru ukazuje u signálů smart money | ostrý běh `hub --firma ACDC` |

## 2026-10-11 · v0.10.1 — Včasné vyhodnocení predikcí, výpadek xtb.com, menší dokument žebříčku

Důvod: chyby nalezené v denních a týdenních bězích 2026-10-09 až 2026-10-11 (zlepšení týdne).

| Soubor/modul | Změna | Test |
|---|---|---|
| `update.py` | Denní závěr je použitelný od 16:15 newyorského času (letní 20:15 UTC, zimní 21:15 UTC) místo pevných 21:00 UTC. Večerní rutina (20:47 UTC v létě) dřív dnešní závěr nikdy neviděla → každé vyhodnocení se zpozdilo o obchodní den (9. 10.: 0 vyhodnocených místo 6) | `test_update_pipeline.py::test_bar_close_time_follows_new_york_daylight_saving` |
| `sources/xtb.py` | xtb.com od 2026-10-11 odmítá dotazy z našeho serveru (firewall F5, HTTP 403). Když web nejde, použije se poslední známé ověření i starší než 30 dní (s datem); firma nikdy neověřená do žebříčku nejde. Bez toho by se žebříčky po vypršení cache (~5. 11.) vyprázdnily | `test_xtb.py` |
| `cli.py`, `hub/registry.py` | `signals`, `discover` a `causal` zapisují do deníku, zda byl xtb.com dostupný; registr pak ukáže zdroj „xtb.com“ jako BLOKOVÁNO | `test_hub.py::test_registry_marks_xtb_blocked_from_journal` |
| `site.py` | U karty v žebříčku jen nejnovější titulek (odkazy Google News mají ~300 znaků): `stav/zebricek` 144 kB → 124 kB (limit 170 kB) | celý `pytest` (136) |

**Výsledek týdne (data k 2026-10-09):** objevování #6 (12 173 firem, 61 zemí, 5 predikcí raket WATCH), smart money #4
(10 signálů, 4 do ledgeru), signály #18–#20 (zamčené testy jen načteny), první vyhodnocení ledgeru: +7 dní 4 HIT / 2 MISS
vůči S&P 500 (energetické predikce z 2. 10.).

## 2026-10-07 · v0.10.0 — Propojený systém: centrum důkazů, zpětná vazba, pohled na firmu, registr a deník

Důvod: zadání uživatele 2026-10-07 — systém má fungovat jako propojená síť specializovaných částí, které si předávají
kontext, kontrolují se a učí se ze zpětné vazby; udržovat paměť (co, proč, výsledek, chyby, co je ověřené), neopakovat
výpočty bez důvodu, stavy HOTOVO/OVĚŘENO, ROZPRACOVÁNO, BLOKOVÁNO, NEOVĚŘENO, CHYBA. Zpráva:
[docs/ARCHITEKTURA_2026-10-07.md](docs/ARCHITEKTURA_2026-10-07.md).

| Soubor/modul | Změna |
|---|---|
| `migrations/0008_hub.sql` | `research_evidence` (ruční výzkum se zdrojem a platností), `system_runs` (deník běhů), `hub_runs` (paměť centra); vše append-only |
| `hub/evidence.py` (nový) | Výstupy všech modulů v jednom jazyce (entita, modul, role, směr, horizont, zdroj, den dat, stav); `add_research` |
| `hub/feedback.py` (nový) | Spolehlivost 14 rolí ze zamčených testů a živých výsledků ze tří knih; stav OVĚŘENO / NEOVĚŘENO / CHYBA, váha 0–1; `signal_role` jediné místo pro roli karty |
| `hub/integrate.py` (nový) | Pohled na firmu: PŘÍLEŽITOST / RIZIKO / ROZPOR / NEVÍM, váhy podle spolehlivosti a čerstvosti, rozpory, poučení (`LESSON_RULES`), pořadí ve všech modelech, kontroly, změny postoje; zápis do paměti jen při změně vstupů |
| `hub/registry.py` (nový) | Registr 10 modulů a 9 zdrojů se stavy, deník běhů, ochrana proti přepočtu signálů |
| `causal/memo.py` (nový), `causal/chains.py` | Týdenní řady a citlivosti podle otisku dat, sdílené `causal` i `signals` (56 s → 0,5 s, výsledek shodný) |
| `cli.py` | Deník všech příkazů, které mění data (i při chybě); centrum se obnoví samo po `update`, `discover`, `smart-money`, `signals`, `causal`, `research`; nové `hub [--firma]`, `system`, `research`; `signals --force`; opraven pád `--help` (znak % v nápovědě) |
| `diag.py` | Kontrola čerstvosti centra a stavu modulů (selhaný běh v deníku = CHYBA) |
| `site.py`, `web/index.html`, `web/dashboard.json` | Dokument `stav/prehled`; v detailu firmy „Propojený pohled ze všech modulů“; sekce „Stav systému a propojení modulů“; upozornění při selhání modulu |
| `tests/unit/test_hub.py` (nový) | 10 testů: role, spolehlivost ze zamčeného testu, výzkum (validace, append-only, platnost), rozpor + poučení + kontroly, čerstvost a verdikt modulu, paměť jen při změně, deník a stavy modulů, otisk výpočtů, ochrana proti přepočtu |

**Výsledek prvního běhu (data k 2026-10-02):** 151 firem, 307 důkazů. Ověřené mimo vzorek jsou jen 3 role: varování
na 1 měsíc (t 3,7) a 6 měsíců (t 4,0) a aktivní nákup insiderů (t 2,7). Výběry do žebříčků ověřené nejsou. Rozpor u 7 firem:
rafinerie DINO, MPC, VLO, DK (žebříček ↑ × výzkum G7 ↓) a těžaři ASM, HBM, LAC (výběr ↑ × silný dolar ↓).
Zapsán ruční výzkum #1–#8 (G7 uvolňuje až 100 mil. barelů ropy a nafty → tlak na marže rafinérií, zdroj StockTitan
2026-10-06). Zpětná vazba z živých predikcí: zatím 0 vyhodnocených, 236 čeká, první 2026-10-09.

**Chyby nalezené celkovou kontrolou:** pád `--help`; centrum na čisté instalaci (chybějící tabulka `xtb_offer`);
rozpor „ověřená role“ × verdikt smart money NÍZKÁ; opakovaná poučení zvětšovala dokument webu; vnořené rozbalení na webu
přebíralo styl řádku žebříčku; široké tabulky na mobilu. Vše opraveno.

## 2026-10-06 · v0.9.0 — Kauzální radar (událost → komodita → obory → firmy) a model na 6 měsíců (+40 %)

Důvod: zadání uživatele 2026-10-06 „GLOBAL CAUSAL IMPACT ENGINE“ a cíl „najít další Microsoft — firmu, která může za půl
roku vyrůst o ~40 %“. Zpráva: [docs/CAUSAL_2026-10-06.md](docs/CAUSAL_2026-10-06.md).

| Soubor/modul | Změna |
|---|---|
| `causal/commodities.py` | 27 komodit a uzlů (ropa, plyn, kovy, uran, obilí, kakao, káva…), výrobní země (NEOVĚŘENO), řetězce dopadů na obory 1.–3. řádu se směrem a důvodem |
| `causal/data.py` | Ceny komodit z Yahoo (futures, zdarma) do cache; 26 staženo, cukr Yahoo nevrací |
| `causal/exposure.py` | Týdenní výnosy oborů nad trhem, citlivost (beta, t) obor × komodita jen z minulých 78 týdnů, šok (z-skóre) |
| `causal/chains.py` | Historický test šok → obory za 1–26 týdnů, „už v ceně“, logika 1. a 2.–3. řádu, placebo; kauzální vítr jako znak |
| `causal/events.py` | GDACS (katastrofy) a Google News (zprávy o narušení); GDELT z našeho serveru blokován (HTTP 429) |
| `causal/radar.py`, `causal/store.py` | Karty událostí: fakta → řetězec → „v ceně?“ → scénáře z historie → firmy (XTB); příležitost jen při shodě dat a logiky; predikce a vyhodnocení (append-only) |
| `migrations/0007_causal.sql` | `causal_runs`, `causal_forecasts`, `causal_outcomes` |
| `signals/panel.py`, `model.py`, `run.py`, `card.py` | Model **SIGNAL_6M**: +40 % / −25 % za 126 obchodních dní; znaky „základna“ a kauzální vítr; půlroční mezery; konzervativní t; řazení podle šance na +40 % (validace); velké firmy zvlášť; POKLES se mezi vítěze nedává. Otisky 14D a 1M beze změny |
| `cli.py` | `causal` (radar + test řetězců); `signals` stahuje ceny komodit a počítá i 6 měsíců |
| `site.py`, `web/index.html` | Dokumenty `stav/zebricek6m` a `stav/kauzalni`; záložka „Události“; přepínač „Všechny / Velké firmy“; seznam nejvyššího rizika pádu |
| `tests/unit/test_causal.py`, `test_signals.py` | +9 testů (graf, bez pohledu do budoucnosti, nalezení vloženého zpoždění, události, karta, záznam, 6M cíle a období) |

**Výsledky:**

- **Vzorec uživatele** (velká firma po propadu, do strany u supportu), 1 412 případů: medián za 3 měsíce +1,5 % (všechny
  velké firmy +2,1 %) → bez výhody. U Microsoftu rozhodly výsledky 30. 7. (+15,5 % za den).
- **Řetězce komodit** (zamčený test, 53 šoků, 950 vazeb): v ceně do 4 týdnů +2,9 % (t 3,8). Potom za 13 týdnů +0,9 %
  (t 0,5) → trh započítá rychle. Logika 2.–3. řádu měla opačný směr (t −2,4).
- **SIGNAL_6M** (zamčený test, 38 579 vzorků):
  - AUC +40 % 0,68, −25 % 0,75.
  - Dolní desetina: −25 % v 57 % případů, medián −35 % (t −4,0) → silné varování před pádem.
  - Horní desetina: bez výhody (+40 % v 9,8 %, základ 13,6 %).

**Chyby nalezené během práce:**
- Radar v prvních bězích ukazoval náhodné vazby („železná ruda → farmacie“) → příležitost jen při shodě dat a logiky.
- Samotná výstraha GDACS ve výrobní zemi → jen „sledovat“.
- Google News ignoroval časové okno → filtr podle data a základ pozornosti z vlastní historie.
- Na mobilu přebíjely styly atribut `hidden` → opraveno.

## 2026-10-05 · v0.8.0 — Žebříček jen z akcií, které nabízí XTB

Důvod: uživatel 2026-10-05 — jeho broker (XTB) nenabízí např. australské a japonské akcie. Chce, aby se dostupnost
ověřila dřív, než se firma dostane do žebříčku.

| Soubor/modul | Změna |
|---|---|
| `sources/xtb.py` (nový) | Ověření na xtb.com/cz (veřejné vyhledávání nástrojů, bez e-mailu). Převod symbolů Yahoo → XTB (VST → VST.US, RR.L → RR.UK…). Stavy AKCIE / CFD / NE. Když XTB firmu pod domácím symbolem nemá nebo jde o burzu mimo nabídku XTB, hledá se podle jména firmy (CRH → CRH.UK, Frontline → FRO.NO, Tsakos → TEN1.US, Lasertec → 6K8.DE). Cache `xtb_offer` na 30 dní, po 5 chybách sítě stop |
| `signals/run.py` | `pick_tradable`: model seřadí všechny akcie, do TOP 20 jdou první z nabídky XTB. Karta nese `xtb` a `poradi_celkem`, běh celé pořadí `poradi_vse` a souhrn kontroly |
| `discovery/rocket.py`, `engine.py` | Druhý seznam `kandidati_xtb` (TOP 20 z nabídky XTB, vlastní limit 3 na obor); `kandidati` (ledger TOP 10) beze změny |
| `site.py`, `web/index.html` | Žebříček z XTB seznamů; u firmy štítek „XTB VST.US“, v detailu datum ověření a pořadí v modelu bez ohledu na XTB; poznámka, kolik firem se přeskočilo |
| `cli.py` | `signals` a `discover` ověřují XTB a vypíší počet dotazů na xtb.com |
| `tests/unit/test_xtb.py` | Převod symbolů, akcie / CFD / jiná burza, hledání podle jména, cache a výpadek sítě, výběr TOP 20, jedna firma = jeden řádek (6 testů) |

**Výsledek 2026-10-05 (signály běhy #13–#14, objevování #5):**
- 14 dní: prověřeno 21 firem, vyřazena 1 (Evolus). CRH a Amrize jsou na XTB jen na domácí burze (CRH.UK, AMRZ.CH).
- 1 měsíc: prověřeno 21, vyřazena 1 (Franklin BSP Realty); Frontline jako FRO.NO.
- 6 měsíců: XTB nabízí 20 firem z prvních 151 v pořadí modelu, po sloučení dvou kotací Hudbay (HBM.TO, HBM) 19.
  Prvních 5 modelu (PDI.AX, MLX.AX, PNR.AX, 8338.T, 4DX.AX) XTB nenabízí.
- Dotazy na xtb.com: signály 42 + 32, objevování 64 (celkem 138), žádná chyba. E-mail se pro XTB nepoužívá.
- Chyba nalezená během práce: dvě kotace jedné firmy vedly na stejný symbol XTB → `unique_listing` (test).

Co se nemění: modely, zamčené testy, pravidlo řazení, ledger (měří se model, ne broker). XTB dál NENÍ podmínkou
predikcí v ledgeru (rozhodnutí 2026-10-02 platí pro ledger, žebříček je nově jen z nabídky XTB).

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
