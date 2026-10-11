# Výzkumný deník (autonomní režim od 2026-10-11)

Zadání uživatele 2026-10-11: samostatně zkoumat, vytvářet hypotézy, experimentovat a učit se z výsledků; hlavní cíl =
najít firmy s šancí na desítky až stovky procent za ~6 měsíců. Každý experiment: hypotéza **předem**, postup, výsledek,
verdikt (POTVRZENO / NEPOTVRZENO / NEOVĚŘENO), poučení. Neúspěchy se zapisují stejně jako úspěchy.

Hranice: jen bezplatné zdroje; žádné obcházení blokací (xtb.com, GDELT); do veřejných diskusí se nepíše (nejsou
nástroje ani účty a vystupovalo by se za uživatele); zamčené testy jen jednou na konfiguraci.

---

## E1 · 2026-10-11 · Spojení dvou ověřených rolí: nákup insiderů × varování modelu 6 m

- **Hypotéza:** aktivní nákup insiderů (ověřeno: +2,8 % proti podobným akciím za 6 m) u firmy, kterou SIGNAL_6M neřadí
  mezi nejslabší, dá vyšší šanci na +40 % a menší riziko −25 % než nákup insiderů bez filtru.
- **Postup:** `stockradar/signals/combo.py`; model SIGNAL_6M naučený jen na TRAIN; 4 předem daná pravidla (R0 bez filtru,
  R10, R30, R50 = percentil směrového skóre v témže týdnu); výběr na validaci; zamčený test jednou
  (`model_evaluations`, INSIDER_X_6M, konfigurace `6a8a133a4b73180d`).
- **Výsledek (zamčený test 2025-07…2026-03, 2 463 nákupů, 1 353 nezávislých):**

| Skupina | +40 % | −25 % | Výnos nad průměrem týdne |
|---|---|---|---|
| Všechny akcie | 13,6 % | 17,8 % | – |
| R0 všechny nákupy insiderů | 11,5 % | 14,3 % | +2,0 % (t 0,4) |
| **R50 vybrané na validaci** | **5,0 %** | **6,0 %** | −0,8 % (t −0,3) |
| Nákup u nejslabší desetiny modelu | 19,9 % | 44,8 % | +0,6 % (t −0,05) |

- **Verdikt:** NEPOTVRZENO jako výběr vítězů. POTVRZENO jako snížení rizika (na validaci i testu), ale za cenu stejně
  nižší šance na růst a bez lepšího výnosu.
- **Poučení:** modely poznají rozkolísanost, ne směr. Spojení modulů vybírá klidnější akcie, ne vítěze. Zapsáno jako
  poučení `POUCENI-KOMBINACE-INSIDER-6M` (centrum ho ukazuje u signálů smart money).

## E2 · 2026-10-11 · Koš nejrozkolísanějších kandidátů (rakety) vs trh

- **Hypotéza:** když modely poznají rozkolísanost, ne směr, mohl by mít KOŠ TOP N raket díky šikmému rozdělení vyšší
  průměrný výnos než trh, i když u jednotlivé firmy směr neznáme.
- **Postup:** model raket naučený do 2024-12-31; řazení vybrané nově na validaci (viz oprava níže); pro každý den
  testu (2025-07…, 20 kohort po 14 dnech) koš TOP 10 / 20 / 50 proti průměru všech akcií téhož dne, 6 m; t přes kohorty
  s korekcí na překryv (13×). Průzkum na období, které už bylo dřív použito k hodnocení modelu → nejde o zamčený test.
- **Výsledek:**

| Koš | Průměr 6 m | Trh | Rozdíl (t) | Rakety +50 % | Propady −33 % | Koš porazil trh |
|---|---|---|---|---|---|---|
| TOP 10 | +1,1 % | +6,7 % | −5,6 % (−0,3) | 39,5 % | 60,0 % | 40 % kohort |
| TOP 20 | +2,4 % | +6,7 % | −4,3 % (−0,4) | 40,8 % | 58,0 % | 25 % kohort |
| TOP 50 | +3,5 % | +6,7 % | −3,2 % (−0,3) | 41,5 % | 54,4 % | 30 % kohort |

- **Ověření výběru řazení (validace):** „raketa“ měla na obou validačních pololetích nejlepší (rakety − propady):
  2024 H1 +0,04 (horní 1 %: průměr +29 %), 2025 H1 +0,24 (průměr +66 %); „asymetrie“ +0,03 a +0,12.
  Stejné řazení v testu: rakety 40 %, propady 54–60 %, výnos pod trhem.
- **Verdikt:** NEPOTVRZENO. Koš raket v testu trh neporazil. Výhoda raket **závisí na režimu trhu** (v horkém 1. pololetí
  2025 velká, potom záporná) — není stabilní.
- **Poučení:** dřívější lepší čísla raket („asymetrie“, test +25 % raket / 18 % propadů) byla zčásti dána výběrem řazení
  přímo na testu (opraveno). Rakety jsou loterie s režimovou závislostí, ne vítězové. Zapsáno `POUCENI-RAKETY-REZIM`.

## E3 · 2026-10-11 · Velká federální zakázka USA → výnos za 6 měsíců (nový typ informace)

- **Hypotéza (předem):** nová zakázka (Mod 0) v hodnotě ≥ 10 % tržní hodnoty firmy → výnos za 6 m lepší než kontrolní
  skupina (5 akcií ze stejného oboru s podobným obratem). POTVRZENO jen při t ≥ 2 a stejném znaménku v obou polovinách.
- **Data:** USAspending.gov (zdarma, bez klíče), transakce zakázek — částka známá v den akce (součet „Award Amount“
  obsahuje i pozdější navýšení → nepoužito). Vstup až ≥ 7 dní po akci (měří se pokračování, ne reakce na oznámení).
  Tržní hodnota z akcií ze SEC známých k danému dni. Studie událostí z `smartmoney/events.py` (žádný nový duplicitní výpočet).
- **Krok 1 (všechny transakce ≥ 10 mil. USD, 2021-01…2026-09):** 53 921 transakcí, 20 181 nových zakázek, spárováno 98
  příjemců (2 479 zakázek) — téměř jen velké firmy. Skupina ≥ 10 % hodnoty firmy: **jen 5 případů** → nelze vyhodnotit;
  5–10 %: 8 případů, +7 % nad kontrolou (t 1,6); velké firmy (< 2 %, 1 556 případů): −1,6 % (t −0,6).
- **Mezistav:** NEOVĚŘENO (málo dat). Krok 2: cílené stažení zakázek ≥ 1 mil. USD pro 923 menších firem (20 mil.–5 mld.
  USD) z oborů s vládními zakázkami (obrana, letectví a vesmír, IT služby, stavby, elektronika, biotech/BARDA).

## Zvážené, ale odložené hypotézy

| Hypotéza | Proč odloženo (2026-10-11) |
|---|---|
| Spin-offy (SEC 10-12B) po prvním měsíci obchodování porážejí obor | cenová data obsahují jen dnes obchodované firmy (zkreslení přeživších), ~150 případů za 5 let, literatura rozporná (2010–2019 spin-offy zaostávaly o −2,7 % ročně, jiné studie +8 % proti oboru) → výsledek by nebyl spolehlivý |

## Opravy nalezené při průzkumu (2026-10-11)

| Nález | Dopad | Oprava |
|---|---|---|
| Model raket vybíral pravidlo řazení (z 5) přímo na testovacích datech | test nebyl nezávislý; výsledky raket mohly vypadat lepší | výběr na validačních pololetích před testem (`rocket.choose_ranking`), test jen měří |
| Kauzální radar počítal šok komodity jen k poslednímu dni cen akcií (týdenní stažení) | pohyby komodit během týdne radar neviděl, karty se opakovaly | šok z denních cen k dni běhu (`exposure.daily_shock`); citlivost a „v ceně“ dál k datu cen akcií |
| Vyhodnocení predikcí čekalo na 21:00 UTC | večerní běh v létě dnešní závěr neviděl | závěrka New York 16:15 místního času (v0.10.1) |
| xtb.com blokuje server (HTTP 403) | žebříčky by se po 30 dnech vyprázdnily | poslední známé ověření s datem; registr ukazuje BLOKOVÁNO (v0.10.1) |
