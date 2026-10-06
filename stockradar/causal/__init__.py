"""Kauzální radar: SVĚT → UDÁLOST → KOMODITA / EKONOMIKA → OBORY → FIRMY → AKCIE.

Moduly:
- commodities  — komodity a obchodní uzly, logické řetězce dopadů 1.–4. řádu (hypotézy, testují se na historii)
- data         — ceny komodit (Yahoo futures, zdarma) do cache, týdenní řady
- exposure     — citlivost oborů na komodity jen z minulých dat (bez pohledu do budoucnosti)
- chains       — historický test: šok komodity → výnos exponovaných oborů za 1–26 týdnů (učení / validace / test)
- events       — události ve světě (GDACS, USGS, GDELT) → uzel grafu
- radar        — dnešní karty: událost → fakta → kauzální vztah → dopad → firmy → predikce (+ scénáře, „v ceně?“)
"""
