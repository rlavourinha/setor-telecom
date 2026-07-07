# -*- coding: utf-8 -*-
"""
mapa_dados.py — dados por UF para os mapas + correlações fixo×pós CORRIGIDAS (sem M2M).

Filtra a base móvel a LINHAS HUMANAS (Tipo de Produto VOZ+DADOS/VOZ), excluindo M2M e
PONTO_DE_SERVICO (maquininhas de cartão) — que inflavam o 'pós' por motivo não-domiciliar.
Emite data/mapa_uf.json (líder móvel, shares, penetrações, fibra%) e imprime as correlações.
"""
import os, sys, json, math
from collections import defaultdict
import anatel

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
HUMANO = {"VOZ+DADOS", "VOZ"}   # exclui M2M, PONTO_DE_SERVICO, DADOS (só-dados)


def settled(months, nac):
    n = [m for m, _ in months]
    for i in range(len(n) - 1, 0, -1):
        if nac[n[i - 1]] and nac[n[i]] >= 0.9 * nac[n[i - 1]]:
            return n[i]
    return n[-1]


def pearson(xs, ys):
    n = len(xs); mx = sum(xs) / n; my = sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs)); sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return cov / (sx * sy) if sx and sy else float("nan")


# ---- MÓVEL (humano) por UF ----
zf, _ = anatel.open_zip("movel"); h, months, rows = anatel.read_colunas(zf, anatel.latest_colunas(zf))
iuf = anatel.col_index(h, "uf"); imod = anatel.col_index(h, "modalidade")
iprod = anatel.col_index(h, "tipo de produto"); igrp = anatel.col_index(h, "grupo econ")
nac = defaultdict(int)
mob_op = defaultdict(lambda: defaultdict(int)); pos = defaultdict(int); pre = defaultdict(int)
for r in rows:
    if len(r) <= months[-1][1] or iuf >= len(r): continue
    prod = r[iprod].strip().upper() if iprod is not None and iprod < len(r) else ""
    if prod not in HUMANO: continue
    uf = r[iuf].strip().upper()
    op = anatel.classifica_grupo(r[igrp]) if igrp is not None and igrp < len(r) else "?"
    mod = anatel._sem_acento(r[imod].strip().upper()) if imod is not None and imod < len(r) else ""
    for m, idx in months:
        v = anatel.to_int(r[idx])
        if not v: continue
        nac[m] += v
        if uf in anatel.POP_UF:
            mob_op[m][uf, op] += v
            if "POS" in mod: pos[(uf, m)] += v
            else: pre[(uf, m)] += v
mesM = settled(months, nac)

# ---- BANDA LARGA por UF ----
zf, _ = anatel.open_zip("bl"); h, months, rows = anatel.read_colunas(zf, anatel.latest_colunas(zf))
iuf = anatel.col_index(h, "uf"); igrp = anatel.col_index(h, "grupo econ"); itec = anatel.col_index(h, "tecnologia")
nacb = defaultdict(int); bl_op = defaultdict(lambda: defaultdict(int)); fib = defaultdict(int); blt = defaultdict(int)
for r in rows:
    if len(r) <= months[-1][1] or iuf >= len(r): continue
    uf = r[iuf].strip().upper(); op = anatel.classifica_grupo(r[igrp]) if igrp is not None and igrp < len(r) else "?"
    tec = anatel._sem_acento(r[itec].strip().upper()) if itec is not None and itec < len(r) else ""
    isf = ("FIBRA" in tec or "FTTH" in tec or "FTTX" in tec)
    for m, idx in months:
        v = anatel.to_int(r[idx])
        if not v: continue
        nacb[m] += v
        if uf in anatel.POP_UF:
            bl_op[m][uf, op] += v; blt[(uf, m)] += v
            if isf: fib[(uf, m)] += v
mesB = settled(months, nacb)

# ---- monta por UF ----
out = {}
for uf in anatel.POP_UF:
    pop = anatel.POP_UF[uf]
    mops = {op: mob_op[mesM].get((uf, op), 0) for op in ["Vivo", "Claro", "TIM", "Algar", "Outros/ISPs"]}
    tm = sum(mops.values())
    bops = {op: bl_op[mesB].get((uf, op), 0) for op in ["Vivo", "Claro", "TIM", "Oi", "Algar", "Sky", "Outros/ISPs"]}
    tb = blt[(uf, mesB)]
    pv, pr = pos[(uf, mesM)], pre[(uf, mesM)]
    out[uf] = {
        "regiao": anatel.UF2REG[uf], "pop": pop,
        "lider_mob": max(mops, key=mops.get),
        "mob_share": {k: round(v / tm * 100, 1) for k, v in mops.items() if v},
        "lider_bl": max(bops, key=bops.get),
        "bl_isp_pct": round(bops["Outros/ISPs"] / tb * 100, 1) if tb else 0,
        "pen_pos_hum": round(pv / pop * 100, 1), "pen_pre": round(pr / pop * 100, 1),
        "pen_bl": round(tb / pop * 100, 1),
        "fibra_pct": round(fib[(uf, mesB)] / tb * 100, 1) if tb else 0,
        "pos_share_hum": round(pv / (pv + pr) * 100, 1) if (pv + pr) else 0,
    }

ufs = list(out)
def col(k): return [out[u][k] for u in ufs]
r_pos = pearson(col("pen_bl"), col("pen_pos_hum"))
r_pre = pearson(col("pen_bl"), col("pen_pre"))
r_mix = pearson(col("pen_bl"), col("pos_share_hum"))
r_fibmix = pearson(col("fibra_pct"), col("pos_share_hum"))

TP = sum(pos[(u, mesM)] for u in anatel.POP_UF); TPRE = sum(pre[(u, mesM)] for u in anatel.POP_UF)
print(f"meses: móvel {mesM} | BL {mesB}")
print(f"\nBase móvel HUMANA (VOZ+DADOS/VOZ): pós {TP/1e6:.1f}mi · pré {TPRE/1e6:.1f}mi · pós = {TP/(TP+TPRE)*100:.1f}%")
print("(vs 66% quando M2M+maquininhas entram no pós — a correção que você pediu)\n")
print("Correlação entre UFs — penetração de banda larga fixa vs:")
print(f"  pós-pago HUMANO : r = {r_pos:+.2f}")
print(f"  pré-pago        : r = {r_pre:+.2f}")
print(f"  % pós (humano)  : r = {r_mix:+.2f}")
print(f"  [fibra% × %pós] : r = {r_fibmix:+.2f}")
print("\nLíder móvel por UF (humano):")
from collections import Counter
print("  ", dict(Counter(out[u]["lider_mob"] for u in ufs)))

json.dump({"mes_mob": mesM, "mes_bl": mesB,
           "pos_hum_share_nac": round(TP/(TP+TPRE)*100,1),
           "corr": {"bl_pos": round(r_pos,2), "bl_pre": round(r_pre,2), "bl_posmix": round(r_mix,2),
                    "fibra_posmix": round(r_fibmix,2)},
           "uf": out}, open(os.path.join(DATA, "mapa_uf.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("\nsalvo em data/mapa_uf.json")
