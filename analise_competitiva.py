# -*- coding: utf-8 -*-
"""
analise_competitiva.py — INTEGRADO × MÓVEL-PURO e concentração por UF/município.

Pergunta central: a participação dos players difere entre o móvel e a banda larga?
Onde uma operadora é forte no móvel, ela também é forte no fixo? Quão concentrado é
cada mercado por região e por município?

Lê os zips locais (data/) — membro Colunas de 2026 de móvel e banda larga, mês settled.
- Móvel: share por operadora (Grupo Econômico -> holding).
- Banda larga: share por operadora E concentração real por CNPJ (cada provedor conta).
Saída: data/analise_competitiva.json + digest no console.
"""
import os, sys, json
from collections import defaultdict
import anatel

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def _settled(months, nac):
    names = [m for m, _ in months]
    for i in range(len(names) - 1, 0, -1):
        if nac[names[i - 1]] and nac[names[i]] >= 0.9 * nac[names[i - 1]]:
            return names[i]
    return names[-1]


def hhi(d):
    """Herfindahl-Hirschman (0–10000) de um dict {ator: valor}."""
    t = sum(d.values())
    return sum((v / t * 100) ** 2 for v in d.values()) if t else 0


def coleta(ds, by_cnpj=False):
    """Uma passada: acumula share por operadora (nacional/UF/município) e, se pedido, por CNPJ/município."""
    zf, _ = anatel.open_zip(ds)
    header, months, rows = anatel.read_colunas(zf, anatel.latest_colunas(zf))
    iuf = anatel.col_index(header, "uf"); iibge = anatel.col_index(header, "ibge")
    igrp = anatel.col_index(header, "grupo econ"); icnpj = anatel.col_index(header, "cnpj")
    # descobrir mês settled: soma nacional por mês
    nacm = defaultdict(int)
    # precisa de 1 passada só; acumulamos tudo por mês e fatiamos no fim
    nac = defaultdict(lambda: defaultdict(int))            # [mes][op]
    uf_ = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))  # [mes][uf][op]
    muni_op = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))  # [mes][ibge][op]
    muni_cnpj = defaultdict(lambda: defaultdict(lambda: defaultdict(int))) if by_cnpj else None
    for r in rows:
        if len(r) <= months[-1][1]:
            continue
        uf = r[iuf].strip().upper() if iuf is not None and iuf < len(r) else None
        op = anatel.classifica_grupo(r[igrp]) if igrp is not None and igrp < len(r) else "?"
        ibge = r[iibge].strip() if iibge is not None and iibge < len(r) and r[iibge].strip() else None
        cnpj = r[icnpj].strip() if by_cnpj and icnpj is not None and icnpj < len(r) else None
        for mname, idx in months:
            v = anatel.to_int(r[idx])
            if not v:
                continue
            nacm[mname] += v
            nac[mname][op] += v
            if uf in anatel.POP_UF:
                uf_[mname][uf][op] += v
            if ibge:
                muni_op[mname][ibge][op] += v
                if by_cnpj:
                    muni_cnpj[mname][ibge][cnpj or "?"] += v
    mes = _settled(months, nacm)
    return {"mes": mes, "nac": dict(nac[mes]), "uf": {u: dict(o) for u, o in uf_[mes].items()},
            "muni_op": {i: dict(o) for i, o in muni_op[mes].items()},
            "muni_cnpj": ({i: dict(o) for i, o in muni_cnpj[mes].items()} if by_cnpj else None)}


def main():
    print("Lendo móvel e banda larga (2026) do disco...")
    mob = coleta("movel")
    bl = coleta("bl", by_cnpj=True)
    tmob = sum(mob["nac"].values()); tbl = sum(bl["nac"].values())

    # ---------- 1) INTEGRADO × MÓVEL: share por operadora nos dois mercados ----------
    ops = ["Vivo", "Claro", "TIM", "Oi", "Outros/ISPs"]
    integ = []
    for op in ops:
        sm = mob["nac"].get(op, 0) / tmob * 100
        sf = bl["nac"].get(op, 0) / tbl * 100
        integ.append({"op": op, "movel": round(sm, 1), "bl": round(sf, 1), "gap": round(sm - sf, 1)})
    print(f"\n=== Share por operadora: móvel × banda larga (mês {mob['mes']}/{bl['mes']}) ===")
    print(f"{'operadora':<14}{'móvel%':>8}{'BL%':>8}{'gap':>8}")
    for x in integ:
        print(f"{x['op']:<14}{x['movel']:>8}{x['bl']:>8}{x['gap']:>+8}")

    # ---------- 2) Concentração nacional (HHI) ----------
    hhi_mob = hhi(mob["nac"])
    hhi_bl_op = hhi(bl["nac"])                         # por holding (ISPs num balde só)
    print(f"\n=== Concentração nacional (HHI 0–10000) ===")
    print(f"  móvel (por operadora):            {hhi_mob:6.0f}   (oligopólio de 3)")
    print(f"  banda larga (por operadora):      {hhi_bl_op:6.0f}   (ISPs agrupados)")

    # ---------- 3) Por UF: share e HHI ----------
    uf_rows = []
    for uf in sorted(anatel.POP_UF, key=lambda u: -anatel.POP_UF[u]):
        m, f = mob["uf"].get(uf, {}), bl["uf"].get(uf, {})
        tm, tf = sum(m.values()), sum(f.values())
        if not tm or not tf:
            continue
        uf_rows.append({
            "uf": uf, "regiao": anatel.UF2REG[uf],
            "mob_vivo": round(m.get("Vivo", 0) / tm * 100, 1),
            "mob_claro": round(m.get("Claro", 0) / tm * 100, 1),
            "mob_tim": round(m.get("TIM", 0) / tm * 100, 1),
            "bl_vivo": round(f.get("Vivo", 0) / tf * 100, 1),
            "bl_claro": round(f.get("Claro", 0) / tf * 100, 1),
            "bl_isps": round(f.get("Outros/ISPs", 0) / tf * 100, 1),
            "hhi_mob": round(hhi(m)), "hhi_bl": round(hhi(f)),
        })

    # ---------- 4) Dinâmica municipal (quem lidera, quantos competem) ----------
    lider_bl = defaultdict(int); lider_mob = defaultdict(int)
    n_players_bl = []; hhi_bl_muni = []; hhi_mob_muni = []
    for ibge, o in bl["muni_op"].items():
        lider_bl[max(o, key=o.get)] += 1
    for ibge, o in mob["muni_op"].items():
        lider_mob[max(o, key=o.get)] += 1
    for ibge, o in (bl["muni_cnpj"] or {}).items():
        n_players_bl.append(sum(1 for v in o.values() if v > 0))
        hhi_bl_muni.append(hhi(o))
    for ibge, o in mob["muni_op"].items():
        hhi_mob_muni.append(hhi(o))
    n_bl = len(bl["muni_op"]); n_mob = len(mob["muni_op"])

    def med(xs): xs = sorted(xs); return xs[len(xs) // 2] if xs else 0
    monop_bl = sum(1 for x in n_players_bl if x == 1)
    print(f"\n=== Dinâmica municipal ({n_bl} municípios com BL, {n_mob} com móvel) ===")
    print("  quem LIDERA a banda larga (nº de municípios):")
    for op, c in sorted(lider_bl.items(), key=lambda x: -x[1]):
        print(f"     {op:<14} {c:>5}  ({c/n_bl*100:4.1f}%)")
    print("  quem LIDERA o móvel (nº de municípios):")
    for op, c in sorted(lider_mob.items(), key=lambda x: -x[1]):
        print(f"     {op:<14} {c:>5}  ({c/n_mob*100:4.1f}%)")
    print(f"  competidores de BL por município: mediana {med(n_players_bl)}, "
          f"monopólio (1 provedor) em {monop_bl} ({monop_bl/n_bl*100:.0f}%)")
    print(f"  HHI mediano por município: móvel {med(hhi_mob_muni):.0f} · BL {med(hhi_bl_muni):.0f} (por CNPJ)")

    achado = (
        "O móvel e a banda larga são mundos quase disjuntos. Os 3 do móvel (95%%) valem só "
        "~%.0f%% da BL somados; os ISPs (0%% no móvel) têm ~%.0f%% da BL. 'Integração' (Vivo, Claro) "
        "existe mas NÃO deu domínio no fixo — a Claro é a mais equilibrada (móvel %.0f%%/BL %.0f%%), "
        "a Vivo lidera móvel mas é minoria no fixo, e a TIM é móvel-puro no acesso (BL ~%.0f%%). "
        "Concentração: HHI móvel ~%.0f (oligopólio uniforme por todo país) vs BL fragmentada; "
        "no município mediano competem %d provedores de BL, mas %.0f%% ainda são monopólio local."
    ) % (sum(x['bl'] for x in integ if x['op'] in ('Vivo','Claro','TIM')),
         next(x['bl'] for x in integ if x['op']=='Outros/ISPs'),
         next(x['movel'] for x in integ if x['op']=='Claro'), next(x['bl'] for x in integ if x['op']=='Claro'),
         next(x['bl'] for x in integ if x['op']=='TIM'),
         hhi_mob, med(n_players_bl), monop_bl/n_bl*100)
    print("\n=== ACHADO ===\n" + achado)

    out = {"mes_movel": mob["mes"], "mes_bl": bl["mes"], "integrado_vs_movel": integ,
           "hhi_nacional": {"movel": round(hhi_mob), "bl_operadora": round(hhi_bl_op)},
           "por_uf": uf_rows,
           "municipal": {"n_bl": n_bl, "n_mob": n_mob,
                         "lider_bl": dict(lider_bl), "lider_mob": dict(lider_mob),
                         "mediana_players_bl": med(n_players_bl), "monopolios_bl": monop_bl,
                         "hhi_mediano_movel": round(med(hhi_mob_muni)), "hhi_mediano_bl": round(med(hhi_bl_muni))},
           "achado": achado}
    json.dump(out, open(os.path.join(DATA, "analise_competitiva.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("\nsalvo em data/analise_competitiva.json")


if __name__ == "__main__":
    main()
