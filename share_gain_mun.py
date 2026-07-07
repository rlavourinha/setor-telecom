# -*- coding: utf-8 -*-
"""
share_gain_mun.py — quem GANHOU share do móvel em cada município (2022 -> 2026).

Compara o share humano (VOZ+DADOS) por operadora entre 2022-12 (pós-partilha da Oi) e
2026-05, por município, e marca quem mais subiu. Saída: data/share_gain.json
  { ibge: [ganhador(0=Vivo 1=Claro 2=TIM -1=n/d), dClaro, dVivo, dTim] }
Requer base mínima nos dois períodos p/ reduzir ruído de municípios minúsculos.
"""
import os, sys, json
from collections import defaultdict
import anatel

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
HUM = {"VOZ+DADOS", "VOZ"}; OPS = ["Vivo", "Claro", "TIM"]
MIN = 500   # base mínima de linhas humanas nos dois períodos


def por_mun(membro, alvo):
    """{ibge: {op: subs}} no mês 'alvo' (humano)."""
    zf, _ = anatel.open_zip("movel"); h, months, rows = anatel.read_colunas(zf, membro)
    idx = dict(months)[alvo]
    iibge = anatel.col_index(h, "ibge"); iprod = anatel.col_index(h, "tipo de produto"); igrp = anatel.col_index(h, "grupo econ")
    out = defaultdict(lambda: defaultdict(int))
    for r in rows:
        if len(r) <= idx or iibge >= len(r): continue
        ib = r[iibge].strip()
        if not ib or (r[iprod].strip().upper() if iprod < len(r) else "") not in HUM: continue
        v = anatel.to_int(r[idx])
        if v: out[ib][anatel.classifica_grupo(r[igrp]) if igrp < len(r) else "?"] += v
    return out


def main():
    zf, _ = anatel.open_zip("movel")
    m22 = next(n for n in zf.namelist() if "2022_2S_Colunas" in n)
    m26 = next(n for n in zf.namelist() if "2026_1S_Colunas" in n)
    print("lendo 2022-12 e 2026-05 por município...")
    a = por_mun(m22, "2022-12"); b = por_mun(m26, "2026-05")

    out = {}; win = defaultdict(int); LID = {"Vivo": 0, "Claro": 1, "TIM": 2}
    for ib in set(a) & set(b):
        ta = sum(a[ib][o] for o in OPS); tb = sum(b[ib][o] for o in OPS)
        if ta < MIN or tb < MIN: continue
        d = {o: round(b[ib][o]/tb*100 - a[ib][o]/ta*100, 1) for o in OPS}
        g = max(OPS, key=lambda o: d[o])
        out[ib] = [LID[g], d["Claro"], d["Vivo"], d["TIM"]]
        win[g] += 1

    print("Municípios cobertos:", len(out))
    tot = sum(win.values())
    print("Quem GANHOU mais share (nº municípios):")
    for o, c in sorted(win.items(), key=lambda x: -x[1]):
        print(f"   {o:<6} {c:5d}  ({c/tot*100:.0f}%)")
    json.dump({"periodo": "2022-12 -> 2026-05", "campos": ["ganhou(0V1C2T)", "dClaro", "dVivo", "dTim"], "d": out},
              open(os.path.join(DATA, "share_gain.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("salvo em data/share_gain.json (%d KB)" % (os.path.getsize(os.path.join(DATA, "share_gain.json"))//1024))


if __name__ == "__main__":
    main()
