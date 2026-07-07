# -*- coding: utf-8 -*-
"""
anatel_publish.py — atualiza AUTOMATICAMENTE os KPIs mensais 1:1 com o _Total da Anatel
e republica o dashboard (commit + push). Chamado pelo anatel_watch.py quando sai mês novo.

ESCOPO SEGURO (reconciliado em 7/jul/2026): só os indicadores que batem byte a byte com o
_Total.csv da Anatel, usando o PENÚLTIMO mês (o último costuma vir preliminar):
   - Acessos móveis (com M2M)  -> _Total 'movel' (Pós+Pré)
   - Telefonia fixa (STFC)     -> _Total 'fixo'  (Autorização+Concessão)
Cada troca usa âncora ÚNICA e é verificada (tem de casar exatamente 1 vez); se não casar,
PULA e registra — nunca reescreve às cegas.

FICAM DE FORA (nuance de escopo / fonte Teleco) e vão para state/REVISAR_<mes>.md:
   - TV paga (6,1 mi = Teleco 'assinantes', ≠ 7,2 mi de 'acessos' do _Total)
   - Banda larga (dois KPIs com % de fibra diferentes — âncora ambígua)
   - Pós-pago % (dez/25, referência anual estável ~66%)
   - 266 mi 'ativos' (trimestral 2T25) · 5G 58,1 mi (dez/25) · velocidades Ookla · fibra Vivo

Uso:
   python anatel_publish.py           # atualiza, commita e dá push
   python anatel_publish.py --dry     # só mostra o que mudaria, sem escrever/commitar
"""
import os, sys, io, re, csv, zipfile, subprocess, datetime
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import anatel
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

INDEX = os.path.join(HERE, "index.html")
STATE = os.path.join(HERE, "state"); os.makedirs(STATE, exist_ok=True)
MES = {1:"jan",2:"fev",3:"mar",4:"abr",5:"mai",6:"jun",7:"jul",8:"ago",9:"set",10:"out",11:"nov",12:"dez"}
DRY = "--dry" in sys.argv


def serie_total(ds):
    """{(ano,mes): total} lendo o _Total.csv ao vivo."""
    hrf = anatel.HttpRangeFile(f"{anatel.BASE}/{anatel.ZIPS[ds]}")
    zf = zipfile.ZipFile(hrf)
    rows = list(csv.reader(io.StringIO(zf.read(anatel.member_total(zf)).decode("utf-8-sig")), delimiter=";"))
    h = [x.strip().lower() for x in rows[0]]
    ia = next(i for i,x in enumerate(h) if x.startswith("ano"))
    im = next(i for i,x in enumerate(h) if x.startswith("m"))
    iq = next((i for i,x in enumerate(h) if "acesso" in x), len(h)-1)
    agg = {}
    for r in rows[1:]:
        try: k=(int(r[ia]), int(r[im]))
        except Exception: continue
        agg[k] = agg.get(k,0) + anatel.to_int(r[iq])
    return agg


def settled(agg):
    """Penúltimo mês (o último é preliminar). Retorna (mes, total)."""
    ms = sorted(agg)
    m = ms[-2] if len(ms) >= 2 else ms[-1]
    return m, agg[m]


def mi(n):  # 276364518 -> "276,4"
    return f"{n/1e6:.1f}".replace(".", ",")


def asof(m):  # (2026,5) -> "mai/26"
    return f"{MES[m[1]]}/{str(m[0])[2:]}"


def patch_kpi(html, label_regex, novo_valor, novo_asof, nome):
    """Troca valor+data-asof de um KPI ancorado no texto do label. Verifica casamento único."""
    pat = re.compile(
        r'(<div class="v">)[0-9.,]+(<span class="u">mi</span></div><div class="l" data-asof=")[^"]*(">'
        + label_regex + r')')
    hits = pat.findall(html)
    if len(hits) != 1:
        print(f"  [PULA] {nome}: âncora casou {len(hits)}x (esperado 1) — não altero."); return html, False
    old = pat.search(html).group(0)
    new = pat.sub(rf'\g<1>{novo_valor}\g<2>{novo_asof}\g<3>', html, count=1)
    if new == html:
        print(f"  [ok, sem mudança] {nome}: já em {novo_valor} ({novo_asof})"); return html, False
    print(f"  [ATUALIZA] {nome}: -> {novo_valor} mi ({novo_asof})")
    return new, True


def main():
    print(f"=== anatel_publish {'(DRY-RUN)' if DRY else ''} — {datetime.date.today().isoformat()} ===")
    mov = serie_total("movel"); fix = serie_total("fixo")
    mmov, vmov = settled(mov); mfix, vfix = settled(fix)
    print(f"móvel settled: {asof(mmov)} = {mi(vmov)} mi | fixo settled: {asof(mfix)} = {mi(vfix)} mi")

    html = io.open(INDEX, encoding="utf-8").read()
    changed = False
    html, c1 = patch_kpi(html, r'Acessos móveis \(com M2M\)', mi(vmov), asof(mmov), "Móvel (com M2M)"); changed |= c1
    html, c2 = patch_kpi(html, r'Acessos de telefonia fixa \(STFC\)', mi(vfix), asof(mfix), "Fixo (STFC)"); changed |= c2

    mes_lbl = asof(mmov)
    revisar = os.path.join(STATE, f"REVISAR_{mmov[0]}-{mmov[1]:02d}.md")
    io.open(revisar, "w", encoding="utf-8").write(
        f"# Revisar manualmente — dados {mes_lbl}\n\n"
        f"Auto-publicados (1:1 com _Total): Móvel {mi(vmov)} mi, Fixo {mi(vfix)} mi.\n\n"
        f"Conferir/atualizar à mão (fonte Teleco ou nuance de escopo):\n"
        f"- TV paga (assinantes Teleco ≠ acessos _Total)\n"
        f"- Banda larga fixa (2 KPIs, % de fibra)\n"
        f"- Pós-pago % · 5G · 'ativos' trimestral · velocidades Ookla · fibra Vivo\n")

    if DRY:
        print(f"\n(DRY) mudaria index.html? {'SIM' if changed else 'não'}. REVISAR em {revisar}"); return

    if not changed:
        print("nada a atualizar (KPIs já no mês settled). Sem commit."); return

    io.open(INDEX, "w", encoding="utf-8").write(html)
    try:
        env = dict(os.environ)
        run = lambda *a: subprocess.run(a, cwd=HERE, check=True, capture_output=True, text=True)
        run("git", "-c", "user.name=rlavourinha", "-c", "user.email=rafael2102@gmail.com",
            "add", "index.html")
        run("git", "-c", "user.name=rlavourinha", "-c", "user.email=rafael2102@gmail.com",
            "commit", "-m", f"data: refresh automatico dos KPIs mensais ({mes_lbl}) — movel/fixo 1:1 Anatel")
        run("git", "push", "origin", "main")
        print(f"*** PUBLICADO: KPIs móvel/fixo -> {mes_lbl}, push feito. Ver {revisar} p/ os manuais. ***")
    except subprocess.CalledProcessError as e:
        print(f"[ERRO git] {e.stderr or e}"); sys.exit(1)


if __name__ == "__main__":
    main()
