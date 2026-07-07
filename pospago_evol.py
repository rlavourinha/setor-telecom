# -*- coding: utf-8 -*-
"""
pospago_evol.py — dinâmica competitiva do PÓS-PAGO no tempo (2019->2026).

Share do pós-pago HUMANO (VOZ+DADOS) por operadora, mês a mês, a partir dos membros
Colunas por semestre do móvel. Foco: o gap do líder aumenta ou diminui? O que mudou
com a saída da Oi (partilha em abr/2022)? Saída: data/pospago_evol.json + digest.
"""
import os, sys, re, json
from collections import defaultdict
import anatel

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
HUMANO = {"VOZ+DADOS", "VOZ"}
SEM = re.compile(r"_20\d\d_[12]S_Colunas\.csv$")   # membros por semestre (2019+)


def main():
    zf, _ = anatel.open_zip("movel")
    membros = sorted(n for n in zf.namelist() if SEM.search(n))
    pos = defaultdict(lambda: defaultdict(int))   # [anomes][op]
    pre = defaultdict(lambda: defaultdict(int))
    for mem in membros:
        h, months, rows = anatel.read_colunas(zf, mem)
        imod = anatel.col_index(h, "modalidade"); iprod = anatel.col_index(h, "tipo de produto")
        igrp = anatel.col_index(h, "grupo econ")
        for r in rows:
            if len(r) <= months[-1][1]: continue
            if (r[iprod].strip().upper() if iprod < len(r) else "") not in HUMANO: continue
            op = anatel.classifica_grupo(r[igrp]) if igrp < len(r) else "?"
            ehpos = "POS" in anatel._sem_acento(r[imod].strip().upper() if imod < len(r) else "")
            for m, idx in months:
                v = anatel.to_int(r[idx])
                if not v: continue
                (pos if ehpos else pre)[m][op] += v
        print(f"  lido {mem.split('_Colunas')[0][-7:]}")

    def share(dic, m):
        t = sum(dic[m].values())
        return {op: round(dic[m].get(op, 0)/t*100, 1) for op in ["Vivo", "Claro", "TIM", "Oi"]} if t else {}

    # dezembro de cada ano (2026 = último mês disponível)
    anos = {}
    for m in sorted(pos):
        anos.setdefault(m[:4], m)      # primeiro guarda; sobrescreve p/ pegar o maior mês
        if m > anos[m[:4]]: anos[m[:4]] = m
    for y in sorted(pos, key=lambda x: x):
        pass
    ycol = {}
    for m in sorted(pos):
        ycol[m[:4]] = m               # fica com o maior mês do ano (dez, ou último de 2026)

    serie = []
    print("\nPÓS-PAGO humano — share por operadora + gap do líder:")
    print(f"{'ano':<6}{'Vivo':>7}{'Claro':>7}{'TIM':>7}{'Oi':>6}{'gap V-2º':>10}")
    for y in sorted(ycol):
        m = ycol[y]; s = share(pos, m)
        outros = [s.get('Claro', 0), s.get('TIM', 0), s.get('Oi', 0)]
        gap = round(s.get('Vivo', 0) - max(outros), 1)
        serie.append({"ano": y, "mes": m, "share": s, "gap_lider": gap})
        print(f"{y:<6}{s.get('Vivo',0):>7}{s.get('Claro',0):>7}{s.get('TIM',0):>7}{s.get('Oi',0):>6}{gap:>10}")

    # comparação pré (só o share atual, p/ contraste)
    matual = max(pre)
    print(f"\nPRÉ-pago share atual ({matual}): {share(pre, matual)}")

    json.dump({"campos": "share pós-pago humano por operadora (dez/ano)", "serie": serie,
               "pre_atual": share(pre, matual)},
              open(os.path.join(DATA, "pospago_evol.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\nsalvo em data/pospago_evol.json")


if __name__ == "__main__":
    main()
