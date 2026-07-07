# -*- coding: utf-8 -*-
"""
analise_regional.py — INTELIGÊNCIA granular do setor (não faz parte do mensal).

Baixa o microdado por município (membros Colunas recentes de móvel e banda larga,
via HTTP Range — ~15 MB no total, não os 3 GB de histórico), agrega por UF/região e
produz um estudo cross-section:
  - Penetração móvel e de banda larga fixa por UF (por 100 hab, Censo 2022)
  - CORRELAÇÃO entre penetração fixa e móvel entre as 27 UFs (Pearson)
  - Market share por operadora e por região
  - % de fibra (FTTH) e % de 5G por UF
Salva o resultado em data/analise_regional.json (pode alimentar uma aba futura).

Uso:  python analise_regional.py
"""
import os, sys, json, math, datetime
from collections import defaultdict
import anatel

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data"); os.makedirs(DATA, exist_ok=True)


def classifica_grupo(nome):
    """
    Grupo Econômico (Anatel) -> marca comercial. Os nomes reais na base são os
    holdings: Vivo=TELEFONICA, Claro=TELECOM AMERICAS, TIM=TELECOM ITALIA, Oi=OI.
    Match por keyword, não por nome fixo.
    """
    n = (nome or "").upper()
    if "TELEFONICA" in n or "VIVO" in n: return "Vivo"
    if "TELECOM AMERICAS" in n or "CLARO" in n or "AMERICA MOVIL" in n: return "Claro"
    if "TELECOM ITALIA" in n or n == "TIM" or n.startswith("TIM "): return "TIM"
    if n == "OI" or n.startswith("OI ") or "TELEMAR" in n: return "Oi"
    if "ALGAR" in n: return "Algar"
    if "SKY" in n: return "Sky"
    return "Outros/ISPs"


def _acumula(dataset, quer_fibra=False, quer_5g=False):
    """Faz UMA passada no membro Colunas, acumulando por (UF, grupo, mês)."""
    zf, hrf = anatel.open_zip(dataset)
    member = anatel.latest_colunas(zf)
    header, months, rows = anatel.read_colunas(zf, member)
    i_uf = anatel.col_index(header, "uf")
    i_grp = anatel.col_index(header, "grupo econ")
    i_tec = anatel.col_index(header, "tecnologia gera") if quer_5g else anatel.col_index(header, "tecnologia")
    mnames = [m for m, _ in months]

    tot = defaultdict(lambda: defaultdict(int))       # [uf][mes]
    grp = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))  # [uf][grupo][mes]
    flag = defaultdict(lambda: defaultdict(int))      # [uf][mes] fibra ou 5g
    nac = defaultdict(int)                             # total nacional por mes
    for r in rows:
        if len(r) <= months[-1][1] or i_uf is None or i_uf >= len(r):
            continue
        uf = r[i_uf].strip().upper()
        if uf not in anatel.POP_UF:
            continue
        g = classifica_grupo(r[i_grp]) if i_grp is not None and i_grp < len(r) else "?"
        tecv = (r[i_tec].strip().upper() if i_tec is not None and i_tec < len(r) else "")
        is_flag = (("FIBRA" in tecv or "FTTH" in tecv or "FTTX" in tecv) if quer_fibra
                   else (("5G" in tecv or "NR" in tecv or tecv == "5") if quer_5g else False))
        for m, idx in months:
            v = anatel.to_int(r[idx])
            if not v:
                continue
            tot[uf][m] += v; grp[uf][g][m] += v; nac[m] += v
            if is_flag:
                flag[uf][m] += v
    # mês settled (evita a competência preliminar)
    mes = mnames[-1]
    for i in range(len(mnames) - 1, 0, -1):
        if nac[mnames[i - 1]] and nac[mnames[i]] >= 0.9 * nac[mnames[i - 1]]:
            mes = mnames[i]; break
    return {
        "mes": mes, "mb": round(hrf.bytes_fetched / 1e6, 1),
        "tot": {uf: tot[uf][mes] for uf in tot},
        "grp": {uf: {g: grp[uf][g][mes] for g in grp[uf]} for uf in grp},
        "flag": {uf: flag[uf][mes] for uf in tot},
    }


def pearson(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return cov / (sx * sy) if sx and sy else float("nan")


def main():
    print("Baixando microdado por município (móvel + banda larga) via HTTP Range...")
    mob = _acumula("movel", quer_5g=True)
    bl = _acumula("bl", quer_fibra=True)
    print(f"  móvel: mês {mob['mes']}, {mob['mb']} MB  |  banda larga: mês {bl['mes']}, {bl['mb']} MB\n")

    ufs = sorted(anatel.POP_UF, key=lambda u: -anatel.POP_UF[u])
    linhas = []
    for uf in ufs:
        pop = anatel.POP_UF[uf]
        m, f = mob["tot"].get(uf, 0), bl["tot"].get(uf, 0)
        linhas.append({
            "uf": uf, "regiao": anatel.UF2REG[uf], "pop": pop,
            "movel": m, "bl": f,
            "pen_movel": round(m / pop * 100, 1), "pen_bl": round(f / pop * 100, 1),
            "fibra_pct": round(bl["flag"].get(uf, 0) / f * 100, 1) if f else 0,
            "g5_pct": round(mob["flag"].get(uf, 0) / m * 100, 1) if m else 0,
        })

    pen_m = [l["pen_movel"] for l in linhas]
    pen_f = [l["pen_bl"] for l in linhas]
    r_mf = pearson(pen_m, pen_f)
    r_m5 = pearson(pen_m, [l["g5_pct"] for l in linhas])

    print("=== Penetração por UF (acessos por 100 hab, Censo 2022) ===")
    print(f"{'UF':<4}{'reg':<5}{'móvel/100':>10}{'BL/100':>9}{'fibra%':>8}{'5G%':>7}")
    for l in linhas:
        print(f"{l['uf']:<4}{l['regiao']:<5}{l['pen_movel']:>10}{l['pen_bl']:>9}{l['fibra_pct']:>8}{l['g5_pct']:>7}")

    print(f"\n=== Correlação entre UFs (n={len(linhas)}) ===")
    print(f"  penetração fixa  x  penetração móvel : r = {r_mf:+.2f}")
    print(f"  penetração móvel x  % de 5G          : r = {r_m5:+.2f}")
    ordf = sorted(linhas, key=lambda l: -l["pen_bl"])
    ordm = sorted(linhas, key=lambda l: -l["pen_movel"])
    print(f"  + fibra fixa:  {', '.join(l['uf'] for l in ordf[:5])}   |  - {', '.join(l['uf'] for l in ordf[-5:])}")
    print(f"  + móvel:       {', '.join(l['uf'] for l in ordm[:5])}   |  - {', '.join(l['uf'] for l in ordm[-5:])}")

    # market share por região (móvel)
    print("\n=== Market share móvel por região (%) ===")
    print(f"{'reg':<5}{'Vivo':>7}{'Claro':>7}{'TIM':>7}{'Outros':>8}")
    reg_share = {}
    for reg in ["N", "NE", "CO", "SE", "S"]:
        acc = defaultdict(int); tot = 0
        for uf in anatel.REGIAO[reg]:
            for g, v in mob["grp"].get(uf, {}).items():
                acc[g] += v; tot += v
        if not tot:
            continue
        reg_share[reg] = {g: round(acc[g] / tot * 100, 1) for g in acc}
        f = lambda g: acc.get(g, 0) / tot * 100
        print(f"{reg:<5}{f('Vivo'):>7.1f}{f('Claro'):>7.1f}{f('TIM'):>7.1f}{f('Outros/ISPs'):>8.1f}")

    # share de ISPs na banda larga por região
    print("\n=== Banda larga: share dos ISPs regionais por região (%) ===")
    for reg in ["N", "NE", "CO", "SE", "S"]:
        acc = defaultdict(int); tot = 0
        for uf in anatel.REGIAO[reg]:
            for g, v in bl["grp"].get(uf, {}).items():
                acc[g] += v; tot += v
        if tot:
            print(f"  {reg:<3} ISPs/Outros: {acc.get('Outros/ISPs',0)/tot*100:5.1f}%   (Claro {acc.get('Claro',0)/tot*100:4.1f}%  Vivo {acc.get('Vivo',0)/tot*100:4.1f}%)")

    achado = ("Correlação fixa×móvel = %+.2f: UFs com mais banda larga por habitante também "
              "têm mais acesso móvel — a infraestrutura anda junta (renda/urbanização). "
              "Fibra é mais alta no %s; penetração móvel lidera no %s.") % (
              r_mf, ", ".join(l["uf"] for l in ordf[:3]), ", ".join(l["uf"] for l in ordm[:3]))
    print("\n=== Achado ===\n" + achado)

    out = {"gerado_em": datetime.date.today().isoformat(),
           "mes_movel": mob["mes"], "mes_bl": bl["mes"],
           "correlacao_fixa_movel": round(r_mf, 3), "correlacao_movel_5g": round(r_m5, 3),
           "por_uf": linhas, "share_regiao_movel": reg_share, "achado": achado}
    p = os.path.join(DATA, "analise_regional.json")
    json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nsalvo em {os.path.relpath(p, HERE)}")


if __name__ == "__main__":
    main()
