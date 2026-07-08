# -*- coding: utf-8 -*-
"""
movel_humano.py — LINHAS MÓVEIS HUMANAS (ex-máquina) no tempo, nacional + por UF.

Definição CONSISTENTE 2019->2026 (a taxonomia de 'Tipo de Produto' mudou em 2021):
  humano = total - (M2M* + PONTO_DE_SERVICO)   [inclui VOZ+DADOS, DADOS, VOZ, OCIOSO]
Isso conserta a quebra 2019-2020 (quando o smartphone humano vinha em 'DADOS', não
'VOZ+DADOS', e ainda não havia 'PONTO_DE_SERVICO'/maquininhas).

Saída: data/movel_humano.json com:
  - nacional: por ano {total_mi, humano_mi, share por operadora (Vivo/Claro/TIM/Outros)}
  - por_uf:   por ano {humano, densidade humana /100 hab} (usa anatel.POP_UF, Censo 2022)
"""
import os, sys, re, json
from collections import defaultdict
import anatel

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
SEM = re.compile(r"_20\d\d_[12]S_Colunas\.csv$")


def eh_maquina(prod):
    p = (prod or "").upper()
    return "M2M" in p or "PONTO_DE_SERVICO" in p or "PONTO DE SERVICO" in p


def grupo4(g):
    op = anatel.classifica_grupo(g)
    return op if op in ("Vivo", "Claro", "TIM") else "Outros"


def main():
    zf, _ = anatel.open_zip("movel")
    membros = sorted(n for n in zf.namelist() if SEM.search(n))
    nat = defaultdict(lambda: {"total": 0, "humano": 0, "op": defaultdict(int)})  # [anomes]
    uf = defaultdict(lambda: defaultdict(int))   # [anomes][uf] = humano
    for mem in membros:
        h, months, rows = anatel.read_colunas(zf, mem)
        iprod = anatel.col_index(h, "tipo de produto"); igrp = anatel.col_index(h, "grupo econ")
        iuf = anatel.col_index(h, "uf")
        for r in rows:
            if len(r) <= months[-1][1]: continue
            prod = r[iprod].strip() if iprod is not None and iprod < len(r) else ""
            maq = eh_maquina(prod)
            op = grupo4(r[igrp]) if igrp is not None and igrp < len(r) else "Outros"
            u = r[iuf].strip().upper() if iuf is not None and iuf < len(r) else "?"
            for m, idx in months:
                v = anatel.to_int(r[idx])
                if not v: continue
                nat[m]["total"] += v
                if not maq:
                    nat[m]["humano"] += v
                    nat[m]["op"][op] += v
                    uf[m][u] += v
        print(f"  lido {mem.split('_Colunas')[0][-7:]}")

    # snapshot anual = maior mês de cada ano
    ycol = {}
    for m in sorted(nat): ycol[m[:4]] = m
    OPS = ["Vivo", "Claro", "TIM", "Outros"]

    serie = []
    print(f"\nNACIONAL — total vs humano + share humano:")
    print(f"{'ano':<6}{'total':>9}{'humano':>9}{'Vivo':>7}{'Claro':>7}{'TIM':>7}{'Outros':>8}")
    for y in sorted(ycol):
        m = ycol[y]; d = nat[m]; hum = d["humano"]
        sh = {o: round(d["op"].get(o, 0)/hum*100, 1) for o in OPS} if hum else {}
        serie.append({"ano": y, "mes": m, "total_mi": round(d["total"]/1e6, 1),
                      "humano_mi": round(hum/1e6, 1), "share": sh})
        print(f"{y:<6}{d['total']/1e6:>9.1f}{hum/1e6:>9.1f}{sh.get('Vivo',0):>7}{sh.get('Claro',0):>7}{sh.get('TIM',0):>7}{sh.get('Outros',0):>8}")

    # por UF: densidade humana /100 hab, 2019 vs último ano
    uf_out = {}
    anos_uf = sorted(ycol)
    for y in anos_uf:
        m = ycol[y]
        for u, v in uf[m].items():
            if u in anatel.POP_UF:
                uf_out.setdefault(u, {})[y] = {"humano": v, "dens": round(v/anatel.POP_UF[u]*100, 1)}
    y0, y1 = anos_uf[0], anos_uf[-1]
    print(f"\nPOR UF — densidade humana /100 hab ({y0} -> {y1}), ordenado pelo avanço:")
    linhas = []
    for u in uf_out:
        d0 = uf_out[u].get(y0, {}).get("dens"); d1 = uf_out[u].get(y1, {}).get("dens")
        if d0 and d1: linhas.append((u, d0, d1, round(d1-d0, 1)))
    for u, d0, d1, dd in sorted(linhas, key=lambda x: -x[3]):
        print(f"   {u}  {d0:6.1f} -> {d1:6.1f}   (avanço {dd:+.1f})")

    json.dump({"def": "humano = total - (M2M + PONTO_DE_SERVICO)",
               "nacional": serie, "por_uf": uf_out, "anos": anos_uf},
              open(os.path.join(DATA, "movel_humano.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\nsalvo em data/movel_humano.json")


if __name__ == "__main__":
    main()
