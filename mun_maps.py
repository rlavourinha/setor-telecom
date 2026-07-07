# -*- coding: utf-8 -*-
"""
mun_maps.py — dados por MUNICÍPIO para os mapas coropléticos.

Campos por ibge (d[ibge]):
  0 pos/100    pós-pago humano por 100 hab
  1 pre/100    pré-pago por 100 hab
  2 fibra/100  fibra (FTTH) por 100 hab
  3 lider_pos  líder do PÓS-pago (0=Vivo 1=Claro 2=TIM, -1 n/d)
  4 lider_pre  líder do PRÉ-pago  (idem)
  5 isp%       participação dos ISPs (Outros) na banda larga
  6 bl_grp     grupo líder na banda larga (código; ver GCODE)

População derivada da densidade da Anatel (ex-M2M -> numerador = linhas humanas).
Também emite data/isp_intel.json (grupos de ISP: subs, #UFs, municípios liderados).
"""
import os, sys, io, csv, json, zipfile
from collections import defaultdict
import anatel

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
HUMANO = {"VOZ+DADOS", "VOZ"}
ANO, MES = "2026", "5"
LID = {"Vivo": 0, "Claro": 1, "TIM": 2}

INC = {"TELEFONICA": "Vivo", "TELECOM AMERICAS": "Claro", "TELECOM ITALIA": "TIM", "OI": "Oi"}
def lab(g):
    u = anatel._sem_acento((g or "").strip().upper())
    return INC.get(u, (g or "").strip().title())

# grupos com cor própria no mapa de líder de BL; resto -> 0 (ISP local)
GCODE = {"Claro":1,"Vivo":2,"Oi":3,"Brisanet":4,"Brasil Tecpar":5,"Giga Mais Fibra":6,
         "Vero":7,"Desktop":8,"Unifique":9,"Alares":10,"Sky":11,"Ligga Telecom":12}


def densidade_por_municipio():
    z = zipfile.ZipFile(os.path.join(DATA, "acessos_telefonia_movel.zip"))
    nome = [n for n in z.namelist() if "Densidade" in n and n.endswith(".csv")][0]
    d5, d4 = {}, {}
    with z.open(nome) as fp:
        rd = csv.reader(io.TextIOWrapper(fp, encoding="latin-1"), delimiter=";")
        h = [c.strip().lower() for c in next(rd)]
        iibge = next(i for i, c in enumerate(h) if "ibge" in c)
        idens = next(i for i, c in enumerate(h) if c.startswith("densidade"))
        iniv = next(i for i, c in enumerate(h) if "vel geogr" in c)
        for r in rd:
            if len(r) <= max(iibge, idens, iniv): continue
            if "unic" not in anatel._sem_acento(r[iniv].lower()): continue
            val = r[idens].strip().replace(".", "").replace(",", ".")
            if not val: continue
            try: dv = float(val)
            except ValueError: continue
            if r[0] == ANO and r[1] == MES: d5[r[iibge].strip()] = dv
            elif r[0] == ANO and r[1] == "4": d4[r[iibge].strip()] = dv
    for ib, v in d4.items(): d5.setdefault(ib, v)
    return d5


def le_movel():
    zf, _ = anatel.open_zip("movel"); h, months, rows = anatel.read_colunas(zf, anatel.latest_colunas(zf))
    idx = dict(months)[f"{ANO}-{int(MES):02d}"]
    iibge = anatel.col_index(h, "ibge"); imod = anatel.col_index(h, "modalidade")
    iprod = anatel.col_index(h, "tipo de produto"); igrp = anatel.col_index(h, "grupo econ")
    hum = defaultdict(int); pos = defaultdict(int); pre = defaultdict(int)
    posop = defaultdict(lambda: defaultdict(int)); preop = defaultdict(lambda: defaultdict(int))
    for r in rows:
        if len(r) <= idx or iibge >= len(r): continue
        ib = r[iibge].strip()
        if not ib or (r[iprod].strip().upper() if iprod < len(r) else "") not in HUMANO: continue
        v = anatel.to_int(r[idx])
        if not v: continue
        hum[ib] += v
        op = anatel.classifica_grupo(r[igrp]) if igrp < len(r) else "?"
        if "POS" in anatel._sem_acento(r[imod].strip().upper() if imod < len(r) else ""):
            pos[ib] += v; posop[ib][op] += v
        else:
            pre[ib] += v; preop[ib][op] += v
    return hum, pos, pre, posop, preop


def le_bl():
    zf, _ = anatel.open_zip("bl"); h, months, rows = anatel.read_colunas(zf, anatel.latest_colunas(zf))
    idx = dict(months)[f"{ANO}-{int(MES):02d}"]
    iibge = anatel.col_index(h, "ibge"); itec = anatel.col_index(h, "tecnologia")
    igrp = anatel.col_index(h, "grupo econ"); iuf = anatel.col_index(h, "uf")
    tot = defaultdict(int); fib = defaultdict(int); grp = defaultdict(lambda: defaultdict(int))
    gtot = defaultdict(int); guf = defaultdict(set)               # p/ isp_intel
    for r in rows:
        if len(r) <= idx or iibge >= len(r): continue
        ib = r[iibge].strip()
        if not ib: continue
        v = anatel.to_int(r[idx])
        if not v: continue
        g = lab(r[igrp]) if igrp < len(r) else "?"
        tot[ib] += v; grp[ib][g] += v; gtot[g] += v
        if iuf < len(r) and r[iuf].strip().upper() in anatel.POP_UF: guf[g].add(r[iuf].strip().upper())
        tec = anatel._sem_acento(r[itec].strip().upper()) if itec < len(r) else ""
        if "FIBRA" in tec or "FTTH" in tec or "FTTX" in tec: fib[ib] += v
    return tot, fib, grp, gtot, guf


def main():
    print("lendo densidade, móvel e banda larga (mês %s/%s)..." % (MES, ANO))
    dens = densidade_por_municipio()
    hum, pos, pre, posop, preop = le_movel()
    btot, fib, bgrp, gtot, guf = le_bl()

    pop = {ib: hum[ib] / dens[ib] * 100 for ib in dens if dens[ib] > 0 and hum.get(ib)}

    def lider(opd):
        c = {k: opd.get(k, 0) for k in LID}
        return LID[max(c, key=c.get)] if sum(c.values()) else -1

    out = {}; lead_grp = defaultdict(int)
    for ib, p in pop.items():
        if p <= 0: continue
        topg = max(bgrp[ib], key=bgrp[ib].get) if bgrp.get(ib) else "?"
        lead_grp[topg] += 1
        out[ib] = [round(pos.get(ib, 0)/p*100, 1), round(pre.get(ib, 0)/p*100, 1), round(fib.get(ib, 0)/p*100, 1),
                   lider(posop.get(ib, {})), lider(preop.get(ib, {})),
                   round(bgrp[ib].get("Outros", 0)/btot[ib]*100, 1) if btot.get(ib) else -1,
                   GCODE.get(topg, 0)]

    # ---- validação ----
    from collections import Counter
    import statistics as st
    print(f"\nmunicípios: {len(out)} | pop {sum(pop.values())/1e6:.0f}mi | SP {pop.get('3550308',0)/1e6:.2f}mi (Censo 11,45)")
    nm = len(out)
    for i, nome in [(3, "pós"), (4, "pré")]:
        c = Counter(v[i] for v in out.values() if v[i] >= 0)
        m = {["Vivo", "Claro", "TIM"][k]: f"{v}({v/nm*100:.0f}%)" for k, v in c.most_common()}
        print(f"  líder {nome}: {m}")

    # ---- ISP intel ----
    NAO_ISP = {"Vivo", "Claro", "Oi", "TIM", "Algar (Ctbc Telecom)", "Sky", "Hughes", "Hispamar", "Bt", "Outros"}
    intel = []
    for g, v in sorted(gtot.items(), key=lambda x: -x[1]):
        if g in NAO_ISP or v < 100000: continue
        intel.append({"grupo": g, "subs": v, "ufs": len(guf[g]), "lidera_mun": lead_grp.get(g, 0)})
    print("\nISPs (subs, #UFs, municípios liderados):")
    for x in intel[:10]:
        print(f"  {x['subs']/1e6:5.2f}mi UFs={x['ufs']:2d} lidera={x['lidera_mun']:4d}  {x['grupo']}")

    json.dump({"mes": f"{ANO}-{int(MES):02d}",
               "campos": ["pos/100", "pre/100", "fibra/100", "lider_pos", "lider_pre", "isp%", "bl_grp"],
               "gcode": GCODE, "d": out},
              open(os.path.join(DATA, "mun_maps.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    json.dump({"mes": f"{ANO}-{int(MES):02d}", "isps": intel,
               "outros_lidera": lead_grp.get("Outros", 0), "total_mun": nm},
              open(os.path.join(DATA, "isp_intel.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\nsalvo: mun_maps.json (%dKB) + isp_intel.json" % (os.path.getsize(os.path.join(DATA, "mun_maps.json"))//1024))


if __name__ == "__main__":
    main()
