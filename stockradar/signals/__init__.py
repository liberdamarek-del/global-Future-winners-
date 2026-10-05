"""Signální engine na 14 dní: místo „jaká bude cena“ několik samostatných pravděpodobností a míra důvěry.

regime.py     tržní režim (S&P 500, VIX, sazby, sezóna výsledků)
extra.py      překvapení ve výsledcích, reakce trhu, kapitálový tok (insideři, buyback, akumulace objemu)
panel.py      historický panel: znaky známé k danému dni + výsledky po 1–120 obchodních dnech
model.py      protokol TRAIN / VALIDATION / LOCKED TEST / LIVE, modely podle režimu, kalibrace, nezávislé případy
card.py       signální karta: P(růst), P(pokles), očekávaný pohyb, analogie, důvěra, NEVÍM / NO-TRADE
news.py       kvalita a novost informací (originál vs. přepisy)
mechanism.py  graf „událost → mechanismus → obor → firmy“ a test, zda obory předbíhají své dodavatele
store.py      append-only záznam běhů, karet a jejich vyhodnocení
"""
