# -*- coding: utf-8 -*-
"""
movel_evol.py — MOVIMENTOS COMPETITIVOS no móvel (linhas humanas, 2021->2026).

Share humano (VOZ+DADOS) por operadora no tempo, adições líquidas ano a ano (quem ganha
assinante) e variação de share por UF (2022 pós-partilha -> 2026). Foco: quem cresce, o
gap do líder abre ou fecha, e onde cada player avança. Saída: data/movel_evol.json.
"""
import os, sys, re, json
from collections import defaultdict
import anatel

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
HUMANO = {"VOZ+DADOS", "VOZ"}
SEM = re.compile(r"_20(2[1-6])_[12]S_Colunas\.csv$")   # 2021+ (base humana limpa)
OPS = ["Vivo", "Claro", "TIM", "Oi"]


def main():
    zf, _ = anatel.open_zip("movel")
    membros = sorted(n for n in zf.namelist() if SEM.search(n))
    nac = defaultdict(lambda: defaultdict(int))          # [anomes][op] subs humanas
    uf = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))  # [anomes][uf][op]
    for mem in membros:
        h, months, rows = anatel.read_colunas(zf, mem)
        iprod = anatel.col_index(h, "tipo de produto"); igrp = anatel.col_index(h, "grupo econ"); iuf = anatel.col_index(h, "uf")
        for r in rows:
            if len(r) <= months[-1][1]: continue
            if (r[iprod].strip().upper() if iprod < len(r) else "") not in HUMANO: continue
            op = anatel.classifica_grupo(r[igrp]) if igrp < len(r) else "?"
            u = r[iuf].strip().upper() if iuf < len(r) else ""
            for m, idx in months:
                v = anatel.to_int(r[idx])
                if not v: continue
                nac[m][op] += v
                if u in anatel.POP_UF: uf[m][u][op] += v
        print(f"  lido {mem.split('_Colunas')[0][-7:]}")

    # dezembro de cada ano (2026 = último)
    ycol = {}
    for m in sorted(nac): ycol[m[:4]] = m
    anos = sorted(ycol)

    serie = []
    prev = None
    print("\nMÓVEL humano — subs (mi) e share por operadora, + adições líquidas a/a:")
    print(f"{'ano':<6}{'Vivo':>18}{'Claro':>18}{'TIM':>18}")
    for y in anos:
        m = ycol[y]; d = nac[m]; tot = sum(d[o] for o in OPS)
        sh = {o: round(d[o]/tot*100, 1) for o in OPS}
        row = {"ano": y, "mes": m, "subs": {o: d[o] for o in OPS}, "share": sh}
        if prev:
            row["adds"] = {o: d[o] - prev[o] for o in OPS}     # adições líquidas vs ano anterior
        serie.append(row)
        def cell(o): return f"{d[o]/1e6:.1f}mi({sh[o]}%)"
        print(f"{y:<6}{cell('Vivo'):>18}{cell('Claro'):>18}{cell('TIM'):>18}")
        prev = {o: d[o] for o in OPS}

    print("\nAdições líquidas (mi) por ano — quem ganhou assinante humano:")
    print(f"{'ano':<6}{'Vivo':>10}{'Claro':>10}{'TIM':>10}")
    for r in serie:
        if "adds" not in r: continue
        print(f"{r['ano']:<6}" + "".join(f"{r['adds'][o]/1e6:>+10.2f}" for o in ["Vivo","Claro","TIM"]))

    # variação de share por UF 2022 -> 2026 (organic, pós-partilha)
    m0 = ycol.get("2022"); m1 = ycol.get("2026")
    uf_delta = {}
    if m0 and m1:
        for u in anatel.POP_UF:
            d0, d1 = uf[m0][u], uf[m1][u]; t0 = sum(d0[o] for o in OPS); t1 = sum(d1[o] for o in OPS)
            if not t0 or not t1: continue
            deltas = {o: round(d1[o]/t1*100 - d0[o]/t0*100, 1) for o in OPS}
            ganhador = max(["Vivo","Claro","TIM"], key=lambda o: deltas[o])
            uf_delta[u] = {"delta": deltas, "ganhou_share": ganhador}
    from collections import Counter
    print("\nQuem GANHOU share em mais UFs (2022->2026):", dict(Counter(v["ganhou_share"] for v in uf_delta.values())))

    json.dump({"anos": anos, "serie": serie, "uf_delta": uf_delta,
               "obs": "linhas humanas VOZ+DADOS; 2021 é a última foto com a Oi viva"},
              open(os.path.join(DATA, "movel_evol.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\nsalvo em data/movel_evol.json")


if __name__ == "__main__":
    main()
