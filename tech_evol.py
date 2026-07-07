# -*- coding: utf-8 -*-
"""
tech_evol.py — evolução das TECNOLOGIAS: gerações móveis (2G->5G) e acesso fixo (cobre->fibra).

Móvel: share por 'Tecnologia Geração' por ano (per-semestre 2019+ e o histórico 2009-2018).
Fixo:  share por tecnologia (Fibra/Cabo/xDSL/Rádio-FWA/Satélite) por ano (Colunas anuais da BL).
Saída: data/tech_evol.json (séries nacionais por ano) + digest.
"""
import os, sys, re, json
from collections import defaultdict
import anatel

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def ger(g):
    g = anatel._sem_acento((g or "").upper())
    if "5" in g or "NR" in g: return "5G"
    if "4" in g or "LTE" in g: return "4G"
    if "3" in g: return "3G"
    if "2" in g: return "2G"
    return "Outros"


def tec_fixa(t):
    t = anatel._sem_acento((t or "").upper())
    if "FIBRA" in t or "FTTH" in t or "FTTX" in t or "FTTB" in t: return "Fibra"
    if "HFC" in t or "CABO" in t: return "Cabo (HFC)"
    if "DSL" in t: return "xDSL (cobre)"
    if "FWA" in t or "RADIO" in t or "WI-FI" in t or "WIFI" in t or "WIMAX" in t: return "Rádio/FWA"
    if "VSAT" in t or "SATEL" in t: return "Satélite"
    return "Outros"


def serie_movel():
    zf, _ = anatel.open_zip("movel")
    # per-semestre (2019+, tem Tecnologia Geração) + histórico de tecnologia (2009-2018)
    membros = [n for n in zf.namelist() if re.search(r"_20\d\d_[12]S_Colunas\.csv$", n)]
    membros += [n for n in zf.namelist() if "200902-2018_Tecnologia_Colunas" in n]
    mes_ger = defaultdict(lambda: defaultdict(int))
    for mem in sorted(membros):
        h, months, rows = anatel.read_colunas(zf, mem)
        ig = anatel.col_index(h, "tecnologia gera")
        if ig is None: continue
        for r in rows:
            if len(r) <= months[-1][1] or ig >= len(r): continue
            g = ger(r[ig])
            for m, idx in months:
                v = anatel.to_int(r[idx])
                if v: mes_ger[m][g] += v
    return mes_ger


def serie_fixa():
    zf, _ = anatel.open_zip("bl")
    membros = [n for n in zf.namelist() if "Colunas" in n and "Densidade" not in n]
    mes_tec = defaultdict(lambda: defaultdict(int))
    for mem in sorted(membros):
        h, months, rows = anatel.read_colunas(zf, mem)
        it = anatel.col_index(h, "tecnologia")
        if it is None: continue
        for r in rows:
            if len(r) <= months[-1][1] or it >= len(r): continue
            t = tec_fixa(r[it])
            for m, idx in months:
                v = anatel.to_int(r[idx])
                if v: mes_tec[m][t] += v
    return mes_tec


def anual(mes_dic, cats):
    yc = {}
    for m in sorted(mes_dic): yc[m[:4]] = m
    out = []
    for y in sorted(yc):
        d = mes_dic[yc[y]]; tot = sum(d.values())
        if not tot: continue
        out.append({"ano": y, "share": {c: round(d.get(c, 0)/tot*100, 1) for c in cats}, "total": tot})
    return out


def main():
    print("móvel: gerações...")
    mg = serie_movel(); mov = anual(mg, ["2G", "3G", "4G", "5G"])
    print("fixo: tecnologias...")
    fx = serie_fixa(); fix = anual(fx, ["Fibra", "Cabo (HFC)", "xDSL (cobre)", "Rádio/FWA", "Satélite"])

    print("\nMÓVEL — share por geração (%):")
    print(f"{'ano':<6}{'2G':>7}{'3G':>7}{'4G':>7}{'5G':>7}")
    for r in mov:
        s = r["share"]; print(f"{r['ano']:<6}{s['2G']:>7}{s['3G']:>7}{s['4G']:>7}{s['5G']:>7}")
    print("\nFIXO — share por tecnologia (%):")
    print(f"{'ano':<6}{'Fibra':>7}{'Cabo':>7}{'xDSL':>7}{'FWA':>7}{'Sat':>7}")
    for r in fix:
        s = r["share"]; print(f"{r['ano']:<6}{s['Fibra']:>7}{s['Cabo (HFC)']:>7}{s['xDSL (cobre)']:>7}{s['Rádio/FWA']:>7}{s['Satélite']:>7}")

    json.dump({"movel_geracao": mov, "fixo_tecnologia": fix},
              open(os.path.join(DATA, "tech_evol.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\nsalvo em data/tech_evol.json")


if __name__ == "__main__":
    main()
