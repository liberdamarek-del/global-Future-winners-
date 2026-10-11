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

## Opravy nalezené při průzkumu (2026-10-11)

| Nález | Dopad | Oprava |
|---|---|---|
| Model raket vybíral pravidlo řazení (z 5) přímo na testovacích datech | test nebyl nezávislý; výsledky raket mohly vypadat lepší | výběr na validačních pololetích před testem (`rocket.choose_ranking`), test jen měří |
| Kauzální radar počítal šok komodity jen k poslednímu dni cen akcií (týdenní stažení) | pohyby komodit během týdne radar neviděl, karty se opakovaly | šok z denních cen k dni běhu (`exposure.daily_shock`); citlivost a „v ceně“ dál k datu cen akcií |
| Vyhodnocení predikcí čekalo na 21:00 UTC | večerní běh v létě dnešní závěr neviděl | závěrka New York 16:15 místního času (v0.10.1) |
| xtb.com blokuje server (HTTP 403) | žebříčky by se po 30 dnech vyprázdnily | poslední známé ověření s datem; registr ukazuje BLOKOVÁNO (v0.10.1) |
