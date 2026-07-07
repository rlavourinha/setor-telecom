# -*- coding: utf-8 -*-
"""
monitor.py — acompanhamento mensal LEVE do setor de telecom (Dados Abertos da Anatel).

Padrão do monitor de insiders da CVM: lê dado aberto -> detecta DELTA vs a última
leitura -> imprime digest. Sem backfill. Transferência mínima (~20 KB) graças à
extração parcial de zip via HTTP Range (ver anatel.HttpRangeFile).

Uso:
  python monitor.py            totais dos 4 serviços + delta (leve, ~20 KB)
  python monitor.py --share    + market share por operadora e tecnologia (~15 MB)
  python monitor.py --demo     amostra offline (não toca a rede)

Para inteligência granular por município/UF (share regional, correlação fixa×móvel),
use  analise_regional.py  — é um estudo pesado, separado do acompanhamento mensal.
"""
import os, sys, json, io, csv, datetime
import anatel

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "state")
os.makedirs(STATE, exist_ok=True)

INDICADORES = {  # dataset -> rótulo
    "movel": "Telefonia móvel (SMP)",
    "bl":    "Banda larga fixa (SCM)",
    "fixo":  "Telefonia fixa (STFC)",
    "tv":    "TV por assinatura (SeAC)",
}
MESES = {1:"jan",2:"fev",3:"mar",4:"abr",5:"mai",6:"jun",7:"jul",8:"ago",9:"set",10:"out",11:"nov",12:"dez"}


def _parse_total(csv_text):
    """CSV 'Ano;Mês;[categoria;]Acessos' -> {(ano,mes): {'total':n,'por_categoria':{...}}}."""
    rows = list(csv.reader(io.StringIO(csv_text), delimiter=";"))
    if len(rows) < 2:
        return {}
    header = [h.strip().lower() for h in rows[0]]
    i_ano = next((i for i, h in enumerate(header) if h.startswith("ano")), 0)
    i_mes = next((i for i, h in enumerate(header) if h.startswith("m")), 1)
    i_qtd = next((i for i, h in enumerate(header) if "acesso" in h), len(header) - 1)
    i_cat = next((i for i in range(len(header)) if i not in (i_ano, i_mes, i_qtd)), None)
    serie = {}
    for r in rows[1:]:
        if len(r) <= i_qtd:
            continue
        try:
            ano, mes = int(r[i_ano]), int(r[i_mes])
        except ValueError:
            continue
        qtd = anatel.to_int(r[i_qtd])
        node = serie.setdefault((ano, mes), {"total": 0, "por_categoria": {}})
        node["total"] += qtd
        if i_cat is not None and i_cat < len(r) and r[i_cat].strip():
            cat = r[i_cat].strip()
            node["por_categoria"][cat] = node["por_categoria"].get(cat, 0) + qtd
    return serie


def collect():
    snap = {"lido_em": datetime.date.today().isoformat(), "indicadores": {}}
    kb = 0
    for ds, label in INDICADORES.items():
        try:
            zf, hrf = anatel.open_zip(ds)
            tot = anatel.member_total(zf)
            serie = _parse_total(zf.read(tot).decode("utf-8-sig"))
            kb += hrf.bytes_fetched / 1024
            ultimo = max(serie)
            prev = max((k for k in serie if k < ultimo), default=None)
            no = serie[ultimo]
            snap["indicadores"][ds] = {
                "label": label,
                "competencia": {"ano": ultimo[0], "mes": ultimo[1]},
                "total": no["total"], "por_categoria": no["por_categoria"],
                "mom": (no["total"] - serie[prev]["total"]) if prev else None,
            }
        except Exception as e:
            snap["indicadores"][ds] = {"label": label, "erro": str(e)}
    snap["_kb_baixados"] = round(kb, 1)
    return snap


def share(datasets=("movel", "bl")):
    """
    Market share por Grupo Econômico + mix por tecnologia, no mês mais settled.
    Usa o membro Colunas mais recente (transfere alguns MB por dataset).
    """
    out = {}
    for ds in datasets:
        zf, hrf = anatel.open_zip(ds)
        member = anatel.latest_colunas(zf)
        header, months, rows = anatel.read_colunas(zf, member)
        i_grp = anatel.col_index(header, "grupo econ")
        i_tec = anatel.col_index(header, "tecnologia")  # BL: FTTH/HFC/...; móvel: 2G/3G/...
        i_ger = anatel.col_index(header, "tecnologia gera")  # móvel: geração (2G..5G)
        i_tech = i_ger if (ds == "movel" and i_ger is not None) else i_tec
        # acumula todas as colunas mensais para escolher o mês settled depois
        por_grp = {m: {} for m, _ in months}
        por_tec = {m: {} for m, _ in months}
        tot_mes = {m: 0 for m, _ in months}
        for r in rows:
            if len(r) <= months[-1][1]:
                continue
            grp = r[i_grp].strip() if i_grp is not None and i_grp < len(r) else "?"
            tec = r[i_tech].strip() if i_tech is not None and i_tech < len(r) else "?"
            for m, idx in months:
                v = anatel.to_int(r[idx])
                if not v:
                    continue
                tot_mes[m] += v
                por_grp[m][grp] = por_grp[m].get(grp, 0) + v
                por_tec[m][tec] = por_tec[m].get(tec, 0) + v
        mes = _settled_month(months, tot_mes)
        out[ds] = {"mes": mes, "total": tot_mes[mes],
                   "por_grupo": por_grp[mes], "por_tecnologia": por_tec[mes],
                   "_mb": round(hrf.bytes_fetched / 1e6, 1)}
    return out


def _settled_month(months, tot_mes):
    """Último mês cujo total não é um degrau (dado preliminar). Heurística ≥90% do anterior."""
    names = [m for m, _ in months]
    for i in range(len(names) - 1, 0, -1):
        cur, prev = tot_mes[names[i]], tot_mes[names[i - 1]]
        if prev and cur >= 0.9 * prev:
            return names[i]
    return names[-1]


def _load_prev():
    p = os.path.join(STATE, "last_snapshot.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def _save(snap):
    json.dump(snap, open(os.path.join(STATE, "last_snapshot.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)


def _fmt(n):
    return f"{n:,}".replace(",", ".") if isinstance(n, int) else str(n)


def digest(cur, prev):
    print(f"\n=== Digest telecom — lido em {cur['lido_em']} ===")
    print(f"(transferido da Anatel: {cur.get('_kb_baixados',0)} KB p/ os {len(INDICADORES)} indicadores)\n")
    pind = (prev or {}).get("indicadores", {})
    for ds, d in cur["indicadores"].items():
        if "erro" in d:
            print(f"[{d['label']}]  ! {d['erro']}"); continue
        comp = d["competencia"]
        print(f"[{d['label']}]  {MESES.get(comp['mes'], comp['mes'])}/{comp['ano']}")
        print(f"   total: {_fmt(d['total'])}", end="")
        if d.get("mom") is not None:
            print(f"   (m/m {'+' if d['mom']>=0 else ''}{_fmt(d['mom'])})", end="")
        pv = pind.get(ds, {})
        if pv.get("competencia") and pv["competencia"] != comp:
            dv = d["total"] - pv.get("total", 0)
            print(f"   [novo mês vs leitura anterior: {'+' if dv>=0 else ''}{_fmt(dv)}]", end="")
        print()
        for cat, v in sorted(d.get("por_categoria", {}).items(), key=lambda x: -x[1]):
            print(f"      {cat:<14} {_fmt(v)}")
        print()
    print("nota: a competência mais recente da Anatel costuma vir PRELIMINAR "
          "(consolidação incompleta);\n      quedas m/m muito grandes tendem a se corrigir na leitura seguinte.")


# nomes reais dos holdings na base da Anatel -> marca comercial (resto fica como está)
FRIENDLY = {"TELEFONICA": "Vivo", "TELECOM AMERICAS": "Claro", "TELECOM ITALIA": "TIM"}


def digest_share(sh):
    print("\n=== Market share (Grupo Econômico) + mix por tecnologia ===")
    rot = {"movel": "Móvel (SMP)", "bl": "Banda larga (SCM)"}
    for ds, d in sh.items():
        print(f"\n[{rot.get(ds, ds)}]  {d['mes']}  ·  total {_fmt(d['total'])}  ·  {d['_mb']} MB transf")
        print("   por operadora:")
        for g, v in sorted(d["por_grupo"].items(), key=lambda x: -x[1])[:8]:
            nome = FRIENDLY.get(g, g)
            print(f"      {nome:<28} {v/d['total']*100:5.1f}%   {_fmt(v)}")
        print("   por tecnologia:")
        for t, v in sorted(d["por_tecnologia"].items(), key=lambda x: -x[1])[:6]:
            print(f"      {t:<28} {v/d['total']*100:5.1f}%")


def _demo():
    return {"lido_em": datetime.date.today().isoformat(), "_kb_baixados": 0.0, "indicadores": {
        "movel": {"label": "Telefonia móvel (SMP)", "competencia": {"ano": 2026, "mes": 5},
                  "total": 276_364_518, "mom": 1_825_777,
                  "por_categoria": {"Pós-pago": 182_718_953, "Pré-pago": 93_645_565}},
        "bl": {"label": "Banda larga fixa (SCM)", "competencia": {"ano": 2026, "mes": 5},
               "total": 55_440_609, "mom": 120_000, "por_categoria": {}},
        "fixo": {"label": "Telefonia fixa (STFC)", "competencia": {"ano": 2026, "mes": 5},
                 "total": 18_003_967, "mom": -150_000, "por_categoria": {"Autorização": 17_954_222, "Concessão": 49_745}},
        "tv": {"label": "TV por assinatura (SeAC)", "competencia": {"ano": 2026, "mes": 5},
               "total": 7_156_176, "mom": -92_592, "por_categoria": {}},
    }}


def main():
    demo = "--demo" in sys.argv
    prev = _load_prev()
    cur = _demo() if demo else collect()
    digest(cur, prev)
    if "--share" in sys.argv and not demo:
        digest_share(share())
    if not demo:
        _save(cur)
        print("\nsnapshot salvo em state/last_snapshot.json")


if __name__ == "__main__":
    main()
