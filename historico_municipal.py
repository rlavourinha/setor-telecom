# -*- coding: utf-8 -*-
"""
historico_municipal.py — INTELIGÊNCIA HISTÓRICA por município (estudo pesado, one-off).

Lê os zips COMPLETOS baixados em data/ (via anatel.open_zip, que prefere o disco) e
monta a evolução histórica por município/UF a partir dos membros 'Colunas' (pivotados
por mês). Foca móvel + banda larga — os dois mercados com dinâmica municipal relevante.

Granularidade REAL da Anatel (não do método):
  - Banda larga: município desde 2007
  - Móvel:       município desde 2019; só UF em 2009–2018; nacional antes
(Os membros 'Colunas' reconciliam 100% com o total oficial — ver reconciliação no chat.)

Saídas em data/:
  historico_nacional.json   série mensal nacional (total, %fibra/%5G, share por operadora)
  historico_uf.csv          UF × mês × métricas (tidy)
  historico_municipal.csv   município × ano (estoque de fim de ano): móvel, BL, BL fibra

Uso:  python historico_municipal.py     (precisa dos zips em data/ — rode o download antes)
"""
import os, sys, csv, json
from collections import defaultdict
import anatel

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

# membros Colunas a usar por dataset (evita a dupla contagem Modalidade×Tecnologia no móvel)
def _membros(zf, ds):
    nomes = [n for n in zf.namelist() if "Colunas" in n and "Densidade" not in n]
    if ds == "movel":
        # Modalidade (histórico UF/nacional) + per-semestre (município). NUNCA a Tecnologia (dupla).
        nomes = [n for n in nomes if "Tecnologia_Colunas" not in n]
    return sorted(nomes)


def _flag_cols(header, ds):
    """(idx_col_flag, teste). Móvel: 5G pela geração; BL: fibra pela tecnologia."""
    if ds == "movel":
        i = anatel.col_index(header, "tecnologia gera")
        return i, (lambda v: ("5G" in v or "NR" in v or v == "5"))
    i = anatel.col_index(header, "tecnologia")
    return i, (lambda v: ("FIBRA" in v or "FTTH" in v or "FTTX" in v))


def processar(ds, nac, uf_, muni_meta, muni_ey):
    zf, src = anatel.open_zip(ds)
    fonte = "disco" if src.__class__.__name__ == "_LocalFile" else "rede"
    membros = _membros(zf, ds)
    print(f"\n[{ds}] {len(membros)} membros Colunas ({fonte})")
    for mem in membros:
        header, months, rows = anatel.read_colunas(zf, mem)
        iuf = anatel.col_index(header, "uf")
        iibge = anatel.col_index(header, "ibge")
        igrp = anatel.col_index(header, "grupo econ")
        iflag, testa = _flag_cols(header, ds)
        n = 0
        for r in rows:
            if len(r) <= months[-1][1]:
                continue
            uf = r[iuf].strip().upper() if iuf is not None and iuf < len(r) else None
            op = anatel.classifica_grupo(r[igrp]) if igrp is not None and igrp < len(r) else "?"
            ibge = r[iibge].strip() if iibge is not None and iibge < len(r) and r[iibge].strip() else None
            flg = bool(iflag is not None and iflag < len(r) and testa(r[iflag].strip().upper()))
            for mname, idx in months:
                v = anatel.to_int(r[idx])
                if not v:
                    continue
                ano = int(mname[:4]); mes = int(mname[5:7])
                # nacional
                d = nac[mname]; d["tot"] += v; d["ops"][op] += v
                if flg: d["flag"] += v
                # por UF
                if uf and uf in anatel.POP_UF:
                    e = uf_[(uf, mname)]; e["tot"] += v; e["ops"][op] += v
                    if flg: e["flag"] += v
                # município — estoque de fim de ano (mês mais recente do ano)
                if ibge:
                    if ibge not in muni_meta and uf:
                        muni_meta[ibge] = uf
                    key = (ibge, ano); cur = muni_ey.get(key)
                    fv = v if flg else 0
                    if cur is None or mes > cur[0]:
                        muni_ey[key] = [mes, v, fv]
                    elif mes == cur[0]:
                        cur[1] += v; cur[2] += fv
            n += 1
        print(f"   {mem.split('_Colunas')[0].split('_')[-1] or mem[:30]:<16} {n:>8} linhas | {months[0][0]}..{months[-1][0]}")


def main():
    faltando = [ds for ds in ("movel", "bl") if not os.path.exists(os.path.join(DATA, anatel.ZIPS[ds]))]
    if faltando:
        print("! Zips ausentes em data/:", faltando, "\n  Baixe os arquivos completos primeiro.")
        # segue mesmo assim: anatel.open_zip cai para HTTP Range se faltar o arquivo local

    # estruturas por dataset
    res = {}
    muni_meta = {}                       # ibge -> uf
    muni_ey = {"movel": {}, "bl": {}}    # (ibge,ano) -> [best_mes, tot, flag]
    for ds in ("movel", "bl"):
        nac = defaultdict(lambda: {"tot": 0, "flag": 0, "ops": defaultdict(int)})
        uf_ = defaultdict(lambda: {"tot": 0, "flag": 0, "ops": defaultdict(int)})
        processar(ds, nac, uf_, muni_meta, muni_ey[ds])
        res[ds] = {"nac": nac, "uf": uf_}

    # ---------- saídas ----------
    # 1) nacional json (série mensal)
    nacout = {}
    for ds in ("movel", "bl"):
        nacout[ds] = {}
        for m, d in sorted(res[ds]["nac"].items()):
            row = {"total": d["tot"], "flag": d["flag"],
                   "flag_pct": round(d["flag"] / d["tot"] * 100, 1) if d["tot"] else 0,
                   "ops": {k: v for k, v in sorted(d["ops"].items(), key=lambda x: -x[1])}}
            nacout[ds][m] = row
    json.dump({"gerado_por": "historico_municipal.py",
               "flag_movel": "5G", "flag_bl": "fibra (FTTH)", "series": nacout},
              open(os.path.join(DATA, "historico_nacional.json"), "w", encoding="utf-8"),
              ensure_ascii=False)

    # 2) UF x mês (tidy csv)
    with open(os.path.join(DATA, "historico_uf.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["dataset", "uf", "anomes", "total", "flag", "Vivo", "Claro", "TIM", "Oi", "Outros/ISPs"])
        for ds in ("movel", "bl"):
            for (uf, m), d in sorted(res[ds]["uf"].items()):
                o = d["ops"]
                w.writerow([ds, uf, m, d["tot"], d["flag"],
                            o.get("Vivo", 0), o.get("Claro", 0), o.get("TIM", 0),
                            o.get("Oi", 0), o.get("Outros/ISPs", 0)])

    # 3) município x ano (estoque de fim de ano)
    anos = sorted({a for ds in ("movel", "bl") for (_, a) in muni_ey[ds]})
    with open(os.path.join(DATA, "historico_municipal.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ibge", "uf", "ano", "movel", "bl", "bl_fibra"])
        ibges = sorted({ib for ds in ("movel", "bl") for (ib, _) in muni_ey[ds]})
        for ib in ibges:
            for a in anos:
                mv = muni_ey["movel"].get((ib, a))
                bl = muni_ey["bl"].get((ib, a))
                if not mv and not bl:
                    continue
                w.writerow([ib, muni_meta.get(ib, ""), a,
                            mv[1] if mv else "", bl[1] if bl else "", bl[2] if bl else ""])

    # ---------- resumo ----------
    print("\n=== RESUMO DO HISTÓRICO ===")
    for ds in ("movel", "bl"):
        ms = sorted(res[ds]["nac"])
        prim, ult = ms[0], ms[-1]
        print(f"[{ds}] {prim} → {ult}  ({len(ms)} meses)")
        for m in (prim, ult):
            d = res[ds]["nac"][m]
            top = sorted(d["ops"].items(), key=lambda x: -x[1])[:3]
            share = ", ".join(f"{k} {v/d['tot']*100:.0f}%" for k, v in top)
            fl = "5G" if ds == "movel" else "fibra"
            print(f"    {m}: {d['tot']:,} acessos".replace(",", ".") +
                  f" | {fl} {d['flag']/d['tot']*100:.1f}% | {share}")
    nmun = len({ib for ds in ('movel', 'bl') for (ib, _) in muni_ey[ds]})
    print(f"\nmunicípios cobertos: {nmun}  |  anos: {anos[0]}–{anos[-1]}")
    print("saídas: data/historico_nacional.json · data/historico_uf.csv · data/historico_municipal.csv")


if __name__ == "__main__":
    main()
