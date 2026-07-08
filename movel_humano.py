# -*- coding: utf-8 -*-
"""
movel_humano.py — evolução das LINHAS MÓVEIS HUMANAS (VOZ+DADOS, ex-M2M/maquininhas).

Total de linhas humanas por ano + market-share por operadora (Vivo/Claro/TIM/Outros),
a partir dos membros Colunas por semestre (2019->2026). Humano = Tipo de Produto em
{VOZ+DADOS, VOZ} — exclui M2M, PONTO_DE_SERVICO (maquininhas) e DADOS-puro.
Saída: data/movel_humano.json + digest.
"""
import os, sys, re, json
from collections import defaultdict
import anatel

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
HUMANO = {"VOZ+DADOS", "VOZ"}
SEM = re.compile(r"_20\d\d_[12]S_Colunas\.csv$")


def grupo4(g):
    op = anatel.classifica_grupo(g)
    return op if op in ("Vivo", "Claro", "TIM") else "Outros"


def main():
    zf, _ = anatel.open_zip("movel")
    membros = sorted(n for n in zf.namelist() if SEM.search(n))
    mes_op = defaultdict(lambda: defaultdict(int))   # [anomes][op] = linhas humanas
    for mem in membros:
        h, months, rows = anatel.read_colunas(zf, mem)
        iprod = anatel.col_index(h, "tipo de produto"); igrp = anatel.col_index(h, "grupo econ")
        if iprod is None or igrp is None: continue
        for r in rows:
            if len(r) <= months[-1][1]: continue
            if (r[iprod].strip().upper() if iprod < len(r) else "") not in HUMANO: continue
            op = grupo4(r[igrp]) if igrp < len(r) else "Outros"
            for m, idx in months:
                v = anatel.to_int(r[idx])
                if v: mes_op[m][op] += v
        print(f"  lido {mem.split('_Colunas')[0][-7:]}")

    # snapshot anual = maior mês de cada ano
    ycol = {}
    for m in sorted(mes_op): ycol[m[:4]] = m
    OPS = ["Vivo", "Claro", "TIM", "Outros"]
    serie = []
    print(f"\nLINHAS HUMANAS (VOZ+DADOS) — total e share:")
    print(f"{'ano':<6}{'total(mi)':>11}{'Vivo':>7}{'Claro':>7}{'TIM':>7}{'Outros':>8}")
    for y in sorted(ycol):
        m = ycol[y]; d = mes_op[m]; tot = sum(d.values())
        if not tot: continue
        share = {op: round(d.get(op, 0)/tot*100, 1) for op in OPS}
        serie.append({"ano": y, "mes": m, "total_mi": round(tot/1e6, 1),
                      "linhas": {op: d.get(op, 0) for op in OPS}, "share": share})
        print(f"{y:<6}{tot/1e6:>11.1f}{share['Vivo']:>7}{share['Claro']:>7}{share['TIM']:>7}{share['Outros']:>8}")

    json.dump({"campos": "linhas móveis humanas (VOZ+DADOS) por ano — total_mi + share por operadora",
               "serie": serie},
              open(os.path.join(DATA, "movel_humano.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\nsalvo em data/movel_humano.json")


if __name__ == "__main__":
    main()
