# -*- coding: utf-8 -*-
"""
movel_uf_op.py — de onde veio o crescimento de cada operadora, por UF, arco longo 2010->2026.

Rastreia Vivo/Claro/TIM/Oi/Outros. Dois regimes:
  PRÉ-OI  (2010->2021): a Oi viva, declinando — quem roubava dela e onde (por UF).
  PÓS-OI  (2022->2026): era de 3, crescimento orgânico (partilha da Oi já embutida em 2022).

Métrica = market-share (% do móvel) por UF. Fontes:
  - 2010-2018: membro histórico (Modalidade_Colunas, tem UF+Grupo, sem Tipo de Produto) -> total.
  - 2019+:     membros por semestre -> HUMANO (ex-M2M/maquininhas). Máquina pré-2019 era pequena.
Saída: data/movel_uf_op.json + resumos.
"""
import os, sys, re, json
from collections import defaultdict
import anatel

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
HIST = "Acessos_Telefonia_Movel_200902-2018_Modalidade_Colunas.csv"
SEM = re.compile(r"_20\d\d_[12]S_Colunas\.csv$")
OPS = ["Vivo", "Claro", "TIM", "Oi", "Outros"]
# NACIONAL: dez de cada ano (arco anual). UF: só snapshots p/ heatmaps pré/pós Oi.
ALVO_HIST = [f"{y}-12" for y in range(2010, 2019)]              # 2010..2018 (histórico)
ALVO_SEM = [f"{y}-12" for y in range(2019, 2026)]              # 2019..2025 (+ último 2026)
UF_SNAP = ["2014-12", "2021-12", "2022-12"]                    # + último 2026 (add em runtime)


def eh_maquina(p):
    p = (p or "").upper(); return "M2M" in p or "PONTO_DE_SERVICO" in p


def op5(g):
    o = anatel.classifica_grupo(g)
    return o if o in ("Vivo", "Claro", "TIM", "Oi") else "Outros"


def main():
    zf, _ = anatel.open_zip("movel")
    natm = defaultdict(lambda: defaultdict(int))               # [mes][op]  (arco anual)
    ufm = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))  # [mes][uf][op]  (snapshots)

    # ---- histórico 2010-2018 (total; sem Tipo de Produto) ----
    h, months, rows = anatel.read_colunas(zf, HIST)
    igrp = anatel.col_index(h, "grupo econ"); iuf = anatel.col_index(h, "uf")
    midx = {m: i for m, i in months}
    cols = [(m, midx[m]) for m in ALVO_HIST if m in midx]
    for r in rows:
        if not cols or len(r) <= max(i for _, i in cols): continue
        op = op5(r[igrp]) if igrp < len(r) else "Outros"
        u = r[iuf].strip().upper() if iuf < len(r) else "?"
        for m, i in cols:
            v = anatel.to_int(r[i])
            if not v: continue
            natm[m][op] += v
            if m in UF_SNAP: ufm[m][u][op] += v
    print("histórico lido (2010..2018)")

    # ---- 2019+ (humano) ----
    membros = sorted(n for n in zf.namelist() if SEM.search(n))
    ult2026 = None
    for mem in membros:
        yr = re.search(r"_(20\d\d)_", mem).group(1)
        h, months, rows = anatel.read_colunas(zf, mem)
        iprod = anatel.col_index(h, "tipo de produto"); igrp = anatel.col_index(h, "grupo econ")
        iuf = anatel.col_index(h, "uf"); midx = {m: i for m, i in months}
        want = set(m for m in ALVO_SEM if m in midx)
        if yr == "2026": ult2026 = months[-1][0]; want.add(ult2026)
        if not want: continue
        cols = [(m, midx[m]) for m in want]
        ufset = set(UF_SNAP) | ({ult2026} if ult2026 else set())
        for r in rows:
            if len(r) <= max(i for _, i in cols): continue
            if eh_maquina(r[iprod] if iprod < len(r) else ""): continue
            op = op5(r[igrp]) if igrp < len(r) else "Outros"
            u = r[iuf].strip().upper() if iuf < len(r) else "?"
            for m, i in cols:
                v = anatel.to_int(r[i])
                if not v: continue
                natm[m][op] += v
                if m in ufset: ufm[m][u][op] += v
        print(f"  lido {mem.split('_Colunas')[0][-7:]}")

    # arco nacional anual (share %)
    nat_annual = {}
    for m in sorted(natm):
        tot = sum(natm[m].values())
        nat_annual[m[:4]] = {o: round(natm[m].get(o, 0)/tot*100, 1) for o in OPS}
    anos = sorted(nat_annual)
    print("\nNACIONAL — market-share (%) ano a ano:")
    print(f"{'ano':<6}" + "".join(f"{o:>8}" for o in OPS))
    for y in anos:
        print(f"{y:<6}" + "".join(f"{nat_annual[y][o]:>8.1f}" for o in OPS))

    # share por UF nos snapshots (2014, 2021, 2022, 2026)
    m26 = ult2026
    SNAPS = {"2014": "2014-12", "2021": "2021-12", "2022": "2022-12", "2026": m26}
    sh = {}
    for lab, mm in SNAPS.items():
        out = {}
        for u in ufm[mm]:
            if u not in anatel.POP_UF: continue
            tot = sum(ufm[mm][u].values())
            if tot: out[u] = {o: round(ufm[mm][u].get(o, 0)/tot*100, 1) for o in OPS}
        sh[lab] = out

    # PRÉ-OI: onde a Oi caiu (2014->2021) e quem pegou (variação de share p.p.)
    print("\nPRÉ-OI 2014->2021 — queda da Oi por UF e quem mais ganhou (p.p. de share):")
    linhas = []
    for u in sorted(sh.get("2014", {})):
        if u not in sh.get("2021", {}): continue
        doi = round(sh["2021"][u]["Oi"] - sh["2014"][u]["Oi"], 1)
        ganhos = {o: round(sh["2021"][u][o] - sh["2014"][u][o], 1) for o in ["Vivo","Claro","TIM"]}
        venc = max(ganhos, key=ganhos.get)
        linhas.append((u, sh["2014"][u]["Oi"], sh["2021"][u]["Oi"], doi, venc, ganhos[venc]))
    for u, o14, o21, doi, vc, g in sorted(linhas, key=lambda x: x[3]):
        print(f"   {u}  Oi {o14:5.1f}->{o21:5.1f} ({doi:+5.1f})   quem pegou: {vc} ({g:+.1f})")

    # PÓS-OI: 2022->2026 variação de share por operadora por UF
    print("\nPÓS-OI 2022->2026 — variação de share (p.p.) por UF:  V / C / T / Outros")
    for u in sorted(sh.get("2022", {})):
        if u not in sh.get("2026", {}): continue
        d = {o: round(sh["2026"][u][o] - sh["2022"][u][o], 1) for o in OPS}
        print(f"   {u}  V{d['Vivo']:+5.1f} C{d['Claro']:+5.1f} T{d['TIM']:+5.1f} O{d['Outros']:+5.1f}")

    json.dump({"anos": anos, "ult2026": ult2026, "nacional_anual": nat_annual, "share_uf_snap": sh},
              open(os.path.join(DATA, "movel_uf_op.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\nsalvo em data/movel_uf_op.json")


if __name__ == "__main__":
    main()
