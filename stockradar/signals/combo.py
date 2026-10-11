"""Experiment 2026-10-11: spojení dvou OVĚŘENÝCH rolí — aktivní nákup insiderů × varování modelu na 6 měsíců.

Hypotéza (stanovená předem, před pohledem na výsledky): aktivní nákup insiderů (ins_n30 ≥ 1; role ověřená studií
událostí: +2,8 % proti podobným akciím za 6 m) u firmy, kterou model SIGNAL_6M NEřadí mezi nejslabší (dolní část
podle směrového skóre v témže týdnu; role ověřená zamčeným testem, t −4,0), dává vyšší šanci na +40 % a menší riziko
−25 % než nákup insiderů bez filtru.

Protokol (stejný jako u signálů, `signals/model.py`):
- model SIGNAL_6M naučený jen na TRAIN, meta-model a kalibrace na VALIDATION (shodně s `run_model`),
- pravidla jsou předem daná (RULES); výběr jen na VALIDACI: nejvyšší (P(+40 %) − P(−25 %)) při ≥ MIN_INDEP nezávislých
  případech, a jen když je lepší než R0 (jinak platí R0 = filtr nepomáhá),
- ZAMČENÝ TEST jednou pro konfiguraci (`model_evaluations`, model INSIDER_X_6M); znovu se jen načte.
Výsledek je statistika, ne doporučení.
"""

import hashlib
import json
import time

from stockradar import __version__
from stockradar.discovery import study
from stockradar.signals import model as M
from stockradar.signals import panel as P
from stockradar.signals import store
from stockradar.discovery.fundamentals import Fundamentals
from stockradar.signals.extra import Extra, Spy
from stockradar.signals.regime import Regime, load_series
from stockradar.signals.run import _day, build_causal, calibrate_model, fit_stage, meta_choice

NAME = "INSIDER_X_6M"
BASE_MODEL = "SIGNAL_6M"
# pravidlo → minimální percentil směrového skóre modelu v témže týdnu (0 = bez filtru)
RULES = {"R0_vsechny_nakupy": 0.0, "R10_bez_dolni_desetiny": 0.10, "R30_bez_dolnich_30": 0.30, "R50_horni_polovina": 0.50}
MIN_INDEP = 30


def config_hash(base_cfg: str) -> str:
    spec = {"rules": RULES, "base": base_cfg, "event": "ins_n30>=1", "min_indep": MIN_INDEP,
            "select": "max(up5-down5) na validaci, jen když > R0"}
    return hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:16]


def week_percentiles(pv, rows: list[int], preds: list[dict]) -> dict[int, float]:
    """Řádek → percentil směrového skóre (růst − pokles) mezi VŠEMI akciemi téhož týdne (0 = nejslabší)."""
    by_week: dict[int, list[tuple[float, int]]] = {}
    for k, p in zip(rows, preds):
        by_week.setdefault(M.week(pv.day[k]), []).append((p["dir"], k))
    out = {}
    for items in by_week.values():
        items.sort()
        n = len(items)
        for i, (_, k) in enumerate(items):
            out[k] = i / max(n - 1, 1)
    return out


def evaluate_rules(pv, rows: list[int], pct: dict[int, float]) -> dict:
    """Metriky každého pravidla (podíl +40 %, −25 %, výnos nad oborem proti průměru týdne všech akcií, t přes týdny)
    + kontrolní skupina „nákup insiderů u nejslabší desetiny“ (měla by být horší, jestli varování platí i tady)."""
    events = [k for k in rows if pv.cols["ins_n30"][k] >= 1]
    out = {"akcii_vzorku": len(rows), "nakupu_vzorku": len(events), "vsechny_akcie": M._bucket(pv, rows, rows)}
    for name, lo in RULES.items():
        out[name] = M._bucket(pv, [k for k in events if pct[k] >= lo], rows)
    out["kontrola_nakup_u_nejslabsi_desetiny"] = M._bucket(pv, [k for k in events if pct[k] < 0.10], rows)
    for name in list(RULES) + ["kontrola_nakup_u_nejslabsi_desetiny"]:
        b = out[name]
        if b.get("up5") is not None:
            b["rust_minus_pokles"] = round(b["up5"] - b["down5"], 4)
    return out


def select_rule(val: dict) -> tuple[str, str]:
    base = val["R0_vsechny_nakupy"].get("rust_minus_pokles")
    ok = [(v["rust_minus_pokles"], n) for n, v in val.items() if n in RULES and v.get("n_indep", 0) >= MIN_INDEP
          and v.get("rust_minus_pokles") is not None]
    if not ok or base is None:
        return "R0_vsechny_nakupy", "málo případů — žádné pravidlo nelze vybrat"
    best = max(ok)
    if best[1] == "R0_vsechny_nakupy" or best[0] <= base:
        return "R0_vsechny_nakupy", "žádný filtr nebyl na validaci lepší než samotný nákup insiderů"
    return best[1], f"na validaci nejvyšší P(+40 %) − P(−25 %): {best[0]:+.3f} proti R0 {base:+.3f}"


def run(cache_conn, main_conn, *, workers: int = 4, log=print) -> dict:
    t0 = time.time()
    lg = lambda m: log(f"[{round(time.time() - t0)} s] {m}")
    data = study.load_data(cache_conn)
    us = {s for s in data.secs if P.is_us(s)}
    fund = Fundamentals(cache_conn, us)
    spy = load_series(main_conn, "SPY")
    extra = Extra(cache_conn, fund, Spy(spy.days, spy.values), lambda s: data.secs[s].prep.bars if s in data.secs else None)
    regime = Regime.from_db(main_conn)
    causal = build_causal(cache_conn, data, log=lg)
    panel = P.build(data, fund, extra, regime, shares=M.share_for, log=lg, causal=causal)
    spec = M.SPECS[BASE_MODEL]
    pv = M.view(panel, BASE_MODEL)
    feats = M.features_of(BASE_MODEL)
    base_cfg = M.config_hash(feats, BASE_MODEL)
    cfg = config_hash(base_cfg)
    split = {"TRAIN": [], "VALIDATION": [], "LOCKED_TEST": []}
    for k in range(len(pv)):
        if pv.y["up5"][k] < 0:
            continue
        s = M.split_of(pv.day[k], spec["gap"], spec.get("post", True))
        if s in split:
            split[s].append(k)
    tr, va, te = split["TRAIN"], split["VALIDATION"], split["LOCKED_TEST"]
    lg(f"{BASE_MODEL} (konfigurace {base_cfg}): TRAIN {len(tr)}, VALIDATION {len(va)}, TEST {len(te)}")
    glob1, reg1 = fit_stage(pv, tr, feats, workers=workers, log=lg)
    choice, _ = meta_choice(pv, va, glob1, reg1)
    sm1 = M.SignalModel(feats, glob1, reg1, choice)
    va_preds = calibrate_model(pv, sm1, va)
    val = evaluate_rules(pv, va, week_percentiles(pv, va, va_preds))
    chosen, why = select_rule(val)
    val["_vybrano"], val["_proc"] = chosen, why
    store.record_eval(main_conn, NAME, cfg, "VALIDATION", (_day(M.VAL[0]), _day(M.VAL[1])),
                      {"vzorku": val["nakupu_vzorku"], "nezavislych": val[chosen].get("n_indep", 0), **val})
    lg(f"Validace: vybráno {chosen} ({why})")
    locked = store.locked_result(main_conn, NAME, cfg)
    if locked is None:
        te_preds = [sm1.predict(pv.row(k), M.regime_class(pv.regime[k])) for k in te]
        test = evaluate_rules(pv, te, week_percentiles(pv, te, te_preds))
        test["_vybrano"] = chosen
        store.record_eval(main_conn, NAME, cfg, "LOCKED_TEST", (_day(M.TEST[0]), _day(M.TEST[1])),
                          {"vzorku": test["nakupu_vzorku"], "nezavislych": test[chosen].get("n_indep", 0), **test})
        test["_stav"] = "vyhodnoceno poprvé"
    else:
        test = locked
        test["_stav"] = f"načteno z registru ({locked['_vyhodnoceno']}) — znovu se nepočítá"
    lg(f"Zamčený test: {test['_stav']}")
    return {"konfigurace": cfg, "zakladni_model": base_cfg, "pravidla": RULES, "validace": val, "zamceny_test": test,
            "vybrano": chosen, "proc": why, "pokusu": store.locked_attempts(main_conn, NAME), "verze": __version__}


def summary(res: dict) -> list[str]:
    """Čitelný souhrn: pro validaci i test řádek za pravidlo."""
    lines = []
    for part in ("validace", "zamceny_test"):
        r = res[part]
        lines.append(f"{part}: nákupů {r['nakupu_vzorku']} z {r['akcii_vzorku']} vzorků")
        base = r["vsechny_akcie"]
        lines.append(f"  všechny akcie       +40 % {base['up5']:.3f}  −25 % {base['down5']:.3f}")
        for name in list(RULES) + ["kontrola_nakup_u_nejslabsi_desetiny"]:
            b = r[name]
            if b.get("up5") is None:
                lines.append(f"  {name:<36} málo dat (n {b.get('n')})")
                continue
            mark = " ← vybráno na validaci" if name == res["vybrano"] else ""
            lines.append(f"  {name:<36} n {b['n']:>6} (nezáv. {b['n_indep']:>4})  +40 % {b['up5']:.3f}  −25 % {b['down5']:.3f}"
                         f"  medián {b['vynos_median']:+.3f}  nad týdnem {b['nad_tydnem']:+.4f} (t {b['t']}){mark}")
    return lines


def main():
    from stockradar.config import db_path
    from stockradar.db import open_db
    from stockradar.discovery import cache as dcache
    res = run(dcache.connect(), open_db(db_path()))
    print("\n".join(summary(res)))
    print(json.dumps({k: res[k] for k in ("konfigurace", "vybrano", "proc", "pokusu")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
