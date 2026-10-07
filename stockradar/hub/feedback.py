"""Zpětná vazba: jak spolehlivá je každá role modulu (např. „6 měsíců — varování před pádem“).

Zdroje (vždy mimo vzorek učení):
1. zamčené testy (`model_evaluations`, split LOCKED_TEST — jednou na konfiguraci), test modelu raket, studie
   událostí smart money, mimo-vzorkový test energetického modelu;
2. vyhodnocené ŽIVÉ predikce ze všech tří knih (`signal_outcomes`, `causal_outcomes`, `prediction_outcomes`).
   Mají přednost, jakmile je jich aspoň LIVE_MIN_N v aspoň LIVE_MIN_WEEKS různých týdnech.

Stav role: OVĚŘENO (t ≥ 2 správným směrem), CHYBA (t ≤ −2 = horší než náhoda), jinak NEOVĚŘENO.
Váha důvěry 0–1: OVĚŘENO min(1, t / 4); NEOVĚŘENO 0,1 (role je vidět, ale skoro neváží); CHYBA 0.
"""

import json
import math
import statistics
from datetime import date

LIVE_MIN_N, LIVE_MIN_WEEKS = 30, 6
W_UNVERIFIED = 0.1

ROLES = {
    "SIGNAL_14D:vyber": ("signaly", "14 dní — výběr do žebříčku", 1),
    "SIGNAL_14D:varovani": ("signaly", "14 dní — nejslabší akcie (varování)", -1),
    "SIGNAL_14D:pokles": ("signaly", "14 dní — rozhodnutí POKLES", -1),
    "SIGNAL_1M:vyber": ("signaly", "1 měsíc — výběr do žebříčku", 1),
    "SIGNAL_1M:varovani": ("signaly", "1 měsíc — nejslabší akcie (varování)", -1),
    "SIGNAL_1M:pokles": ("signaly", "1 měsíc — rozhodnutí POKLES", -1),
    "SIGNAL_6M:vyber": ("signaly", "6 měsíců — výběr (šance na +40 %)", 1),
    "SIGNAL_6M:varovani": ("signaly", "6 měsíců — nejslabší akcie (varování před pádem)", -1),
    "SIGNAL_6M:pokles": ("signaly", "6 měsíců — rozhodnutí POKLES", -1),
    "RAKETY_6M:vyber": ("objevovani", "Rakety do 6 měsíců (+50 %) — kandidáti", 1),
    "SMART_MONEY:nakup": ("smart_money", "Aktivní nákup insiderů (ověřeno ve Form 4)", 1),
    "KAUZALNI:prilezitost": ("kauzalni", "Šok komodity → obor (data i logika)", 0),
    "ENERGIE:vyber": ("energie", "Energetický radar — TOP 5", 1),
    "VYZKUM": ("vyzkum", "Ruční výzkum se zdrojem", 0),
}
SIGNAL_MODELS = ("SIGNAL_14D", "SIGNAL_1M", "SIGNAL_6M")
# predikce v ledgeru → role (strategie / zdroj)
LEDGER_ROLE = {"ROCKET_6M": "RAKETY_6M:vyber", "SMART_MONEY": "SMART_MONEY:nakup", "ENERGY_MODEL": "ENERGIE:vyber"}
HORIZON_DAYS = {"D0_14": 14, "D15_45": 30, "M6_PLUS": 180}


def signal_role(model: str, card: dict) -> str | None:
    """Jediné místo, které určuje roli signální karty (používá ho centrum důkazů i vyhodnocení živých karet).
    POKLES z výběru „nejslabších“ (bez pořadí v žebříčku) = varování (dolní desetina podle směru v zamčeném testu);
    POKLES jinde = rozhodnutí POKLES; ostatní karty v žebříčku = výběr."""
    ranked = card.get("poradi") or card.get("poradi_velke")
    if card.get("final") == "POKLES" or card.get("decision") == "POKLES":
        return f"{model}:pokles" if ranked else f"{model}:varovani"
    return f"{model}:vyber" if ranked else None


def judge(t: float | None, *, typ: str, metrika: str, n: int | None = None, efekt: float | None = None,
          stav: str | None = None) -> dict:
    """t je už otočené podle směru role (kladné = role měla pravdu)."""
    if stav is None:
        stav = "NEOVĚŘENO" if t is None else "OVĚŘENO" if t >= 2 else "CHYBA" if t <= -2 else "NEOVĚŘENO"
    vaha = round(min(1.0, t / 4), 2) if stav == "OVĚŘENO" and t is not None else 0.5 if stav == "OVĚŘENO" else \
        0.0 if stav == "CHYBA" else W_UNVERIFIED
    return {"stav": stav, "vaha": vaha, "t": None if t is None else round(t, 2), "n": n,
            "efekt": None if efekt is None else round(efekt, 4), "typ": typ, "metrika": metrika}


def weekly_t(values: list[tuple[int, float]]) -> tuple[float | None, int, int]:
    """t-statistika přes týdny (případy v jednom týdnu nejsou nezávislé): (t, případů, týdnů)."""
    by_week: dict[int, list[float]] = {}
    for wk, v in values:
        if v == v:
            by_week.setdefault(wk, []).append(v)
    means = [statistics.fmean(v) for v in by_week.values()]
    n = sum(len(v) for v in by_week.values())
    if len(means) < 3:
        return None, n, len(means)
    sd = statistics.stdev(means)
    if sd == 0:
        return None, n, len(means)
    return statistics.fmean(means) / (sd / math.sqrt(len(means))), n, len(means)


def _week(iso_day: str) -> int:
    d = date.fromisoformat(iso_day[:10])
    return d.toordinal() // 7


def _locked(conn, model: str) -> tuple[dict | None, str | None]:
    """Zamčený test konfigurace, kterou používá poslední běh modelu (registr `model_evaluations`)."""
    run = conn.execute("SELECT config_hash FROM signal_runs WHERE model_name = ? ORDER BY id DESC LIMIT 1", (model,)).fetchone()
    if run is None:
        return None, None
    r = conn.execute("SELECT metrics_json, evaluated_at FROM model_evaluations WHERE model_name = ? AND config_hash = ?"
                     " AND split = 'LOCKED_TEST' ORDER BY id DESC LIMIT 1", (model, run[0])).fetchone()
    return (json.loads(r[0]), r[1][:10]) if r else (None, None)


def _from_tests(conn) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for model in SIGNAL_MODELS:
        m, when = _locked(conn, model)
        if m is None:
            for kind in ("vyber", "varovani", "pokles"):
                out[f"{model}:{kind}"] = judge(None, typ="chybí", metrika="zamčený test zatím neproběhl")
            continue
        typ = f"zamčený test {when}"
        hd, dd = m.get("horni_desetina") or {}, m.get("dolni_desetina") or {}
        pk = (m.get("rozhodnuti") or {}).get("POKLES") or {}
        out[f"{model}:vyber"] = judge(hd.get("t"), typ=typ, n=hd.get("n_indep"), efekt=hd.get("nad_tydnem"),
                                      metrika="horní desetina modelu proti průměru týdne (výnos nad oborem)")
        out[f"{model}:varovani"] = judge(-dd["t"] if dd.get("t") is not None else None, typ=typ, n=dd.get("n_indep"),
                                         efekt=dd.get("nad_tydnem"), metrika="dolní desetina modelu proti průměru týdne")
        out[f"{model}:pokles"] = judge(-pk["t"] if pk.get("t") is not None else None, typ=typ, n=pk.get("n_indep"),
                                       efekt=pk.get("nad_tydnem"), metrika="akcie s rozhodnutím POKLES proti průměru týdne")
    # rakety: modul sám říká, zda má výhodu ve směru (víc raket A lepší medián), t-statistiku nepočítá
    r = conn.execute("SELECT result_json FROM discovery_runs ORDER BY id DESC LIMIT 1").fetchone()
    rk = (json.loads(r[0]).get("rakety_6m") or {}) if r else {}
    if rk.get("test"):
        top = (rk["test"].get(rk.get("razeni")) or {}).get("top1") or {}
        base = rk["test"].get("zaklad") or {}
        txt = (f"horní 1 %: raketa {_p(top.get('rakety'))} (běžně {_p(base.get('rakety'))}), propad {_p(top.get('propady'))}"
               f" (běžně {_p(base.get('propady'))}), medián {_p(top.get('median'), 1)} — "
               + ("výhoda ve směru" if rk.get("smerova_vyhoda") else "víc raket, ale i propadů: směr neověřen"))
        out["RAKETY_6M:vyber"] = judge(None, typ=f"test mimo vzorek {rk.get('test_obdobi', '')}", metrika=txt, n=top.get("n"),
                                       stav="OVĚŘENO" if rk.get("smerova_vyhoda") else "NEOVĚŘENO")
    else:
        out["RAKETY_6M:vyber"] = judge(None, typ="chybí", metrika="model raket zatím neběžel")
    # smart money: studie událostí (bez učení parametrů) — aktivní nákupy proti kontrolní skupině podobných akcií
    r = conn.execute("SELECT result_json FROM smart_money_runs ORDER BY id DESC LIMIT 1").fetchone()
    sm = json.loads(r[0]) if r else {}
    g = ((sm.get("insideri") or {}).get("Insider: AKTIVNÍ nákup (všechny)") or {}).get("6m") or {}
    if g:
        q = ((sm.get("skore") or {}).get("test_kvintily") or [{}])[-1]
        out["SMART_MONEY:nakup"] = judge(
            g.get("t_mesice"), typ="studie událostí 2021–2026 (bez učení)", n=g.get("mesicu"), efekt=g.get("nad_kontrolou_prumer"),
            metrika=f"aktivní nákupy za 6 m: proti podobným akciím {_p(g.get('nad_kontrolou_prumer'), 1)}, proti S&P 500 "
                    f"{_p(g.get('nad_spy_prumer'), 1)}; nejvyšší pětina skóre v testu {_p(q.get('nad_kontrolou_prumer'), 1)} → skóre navíc nepomáhá")
    else:
        out["SMART_MONEY:nakup"] = judge(None, typ="chybí", metrika="smart money zatím neběželo")
    # kauzální řetězce: pokračuje dopad po šoku ještě dál? (to, co radar nabízí jako příležitost)
    r = conn.execute("SELECT metrics_json, evaluated_at FROM model_evaluations WHERE model_name = 'CAUSAL_CHAINS'"
                     " AND split = 'LOCKED_TEST' ORDER BY id DESC LIMIT 1").fetchone()
    if r:
        m = json.loads(r[0])
        e4 = (m.get("empiricke") or {}).get("4t") or {}
        priced = (m.get("empiricke") or {}).get("uz_v_cene_4t") or {}
        out["KAUZALNI:prilezitost"] = judge(
            e4.get("t"), typ=f"zamčený test {r[1][:10]}", n=m.get("nezavislych"), efekt=e4.get("prumer"),
            metrika=f"obor po šoku dál za 4 týdny {_p(e4.get('prumer'), 1)}; ve stejných 4 týdnech už v ceně "
                    f"{_p(priced.get('prumer'), 1)} (t {priced.get('t')}) → užitek jen u čerstvých šoků")
    else:
        out["KAUZALNI:prilezitost"] = judge(None, typ="chybí", metrika="test řetězců zatím neproběhl")
    # energetický radar: mimo-vzorkový test posledního modelu (TOP 5 proti S&P 500)
    r = conn.execute("SELECT metrics_json FROM model_versions ORDER BY id DESC LIMIT 1").fetchone()
    oos = (json.loads(r[0]).get("_oos") or {}) if r else {}
    if oos.get("vzorku"):
        n_eff = max(1, oos["vzorku"] // 5)                       # 5 firem ze stejného dne nejsou nezávislé
        p = oos.get("top5_uspesnost") or 0.0
        z = (p - 0.5) / math.sqrt(0.25 / n_eff)
        out["ENERGIE:vyber"] = judge(z, typ=f"test mimo vzorek {oos.get('obdobi', '')}", n=n_eff,
                                     efekt=oos.get("top5_prumer_nad_spy"),
                                     metrika=f"TOP 5 porazilo S&P 500 v {_p(p)} případů (IC {oos.get('ic')})")
    else:
        out["ENERGIE:vyber"] = judge(None, typ="chybí", metrika="mimo-vzorkový test zatím není")
    out["VYZKUM"] = judge(None, typ="živé výsledky", metrika="ruční výzkum se zatím nevyhodnocuje proti cenám")
    return out


def _p(v, d: int = 0) -> str:
    """Podíl jako procenta česky; s desetinami i se znaménkem (výnosy), bez desetin bez znaménka (četnosti)."""
    if v is None:
        return "–"
    text = f"{v * 100:+.{d}f} %" if d else f"{v * 100:.0f} %"
    return text.replace(".", ",").replace("-", "−")


def live_outcomes(conn) -> dict[str, list[tuple[int, float]]]:
    """Role → [(týden predikce, výsledek ve směru role)] ze všech tří knih."""
    out: dict[str, list[tuple[int, float]]] = {}
    for f_made, model, card_json, ret, sec in conn.execute(
            "SELECT f.made_at, r.model_name, f.card_json, o.ret, o.sector_ret FROM signal_outcomes o"
            " JOIN signal_forecasts f ON f.id = o.forecast_id JOIN signal_runs r ON r.id = f.run_id"):
        role = signal_role(model, json.loads(card_json))
        if role and ret is not None and sec is not None:
            out.setdefault(role, []).append((_week(f_made), ROLES[role][2] * (ret - sec)))
    for made, direction, excess in conn.execute(
            "SELECT f.made_at, f.direction, o.industry_excess FROM causal_outcomes o JOIN causal_forecasts f ON f.id = o.forecast_id"):
        if excess is not None:
            out.setdefault("KAUZALNI:prilezitost", []).append((_week(made), direction * excess))
    for made, strategy, source, horizon, excess, ret in conn.execute(
            "SELECT p.made_at, p.strategy, p.source, p.horizon, o.excess_return_pct, o.return_pct FROM prediction_outcomes o"
            " JOIN predictions p ON p.id = o.prediction_id WHERE p.mode = 'LIVE' AND o.horizon_days = CASE p.horizon"
            " WHEN 'D0_14' THEN 14 WHEN 'D15_45' THEN 30 ELSE 180 END"):
        role = LEDGER_ROLE.get(strategy or "") or LEDGER_ROLE.get(source or "")
        v = excess if excess is not None else ret
        if role and v is not None:
            out.setdefault(role, []).append((_week(made), v / 100))
    return out


def reliability(conn) -> dict[str, dict]:
    """Role → stav, váha, t, n, metrika, typ důkazu; živé výsledky mají přednost, když je jich dost."""
    tests = _from_tests(conn)
    live = live_outcomes(conn)
    out = {}
    for role, (modul, nazev, smer) in ROLES.items():
        r = dict(tests.get(role) or judge(None, typ="chybí", metrika="–"))
        t, n, weeks = weekly_t(live.get(role, []))
        r["zive"] = {"n": n, "tydnu": weeks, "t": None if t is None else round(t, 2)}
        if n >= LIVE_MIN_N and weeks >= LIVE_MIN_WEEKS and t is not None:
            test_info = f"{r['typ']}: {r['stav']}"
            r = judge(t, typ=f"živé výsledky ({n} predikcí, {weeks} týdnů)", n=n,
                      metrika=f"výsledek ve směru role proti oboru / trhu; dřív {test_info}") | {"zive": r["zive"]}
        out[role] = {"role": role, "modul": modul, "nazev": nazev, "smer": smer} | r
    return out
