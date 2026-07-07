# -*- coding: utf-8 -*-
"""
anatel_watch.py — vigia mensal dos Dados Abertos da Anatel (rodado por Tarefa Agendada do Windows).

O que faz a cada execução (leve, ~20 KB de rede):
  1. Sonda AO VIVO o mês mais recente dos 4 serviços (móvel/BL/fixa/TV) via HTTP Range.
  2. Compara com o baseline salvo em state/watch_state.json.
  3. Se NÃO houver mês novo  -> só registra a checagem no log e sai.
     Se HOUVER mês novo      -> dispara:
        - grava relatório state/anatel_<AAAA-MM>.md (totais + variação m/m, dado correto 1:1);
        - anexa a state/CHANGELOG_ANATEL.md;
        - cria a flag state/NOVO_MES.flag (sinal p/ o publish revisado);
        - notificação Windows (best-effort);
        - atualiza o baseline e loga.

NÃO reescreve o index.html nem faz git push: os KPIs de destaque têm nuance de escopo
(TV/BL/fixa não são 1:1 com o _Total.csv), então o publish fica sob revisão de 1 clique.
Para rodar o publish revisado, abra o Claude e diga "saiu o mês novo, atualiza" — o relatório
e a flag já estarão prontos.
"""
import os, sys, io, csv, json, zipfile, datetime, traceback
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import anatel

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

STATE = os.path.join(HERE, "state"); os.makedirs(STATE, exist_ok=True)
WSTATE = os.path.join(STATE, "watch_state.json")
LOG = os.path.join(STATE, "watch.log")
MESES = {1:"jan",2:"fev",3:"mar",4:"abr",5:"mai",6:"jun",7:"jul",8:"ago",9:"set",10:"out",11:"nov",12:"dez"}
ROT = {"movel":"Telefonia móvel (SMP)","bl":"Banda larga fixa (SCM)","fixo":"Telefonia fixa (STFC)","tv":"TV por assinatura (SeAC)"}


def log(msg):
    line = f"{datetime.datetime.now().isoformat(timespec='seconds')}  {msg}"
    print(line)
    with io.open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def totals_live(ds):
    """Retorna {(ano,mes): total} lendo o _Total.csv AO VIVO (HTTP Range)."""
    hrf = anatel.HttpRangeFile(f"{anatel.BASE}/{anatel.ZIPS[ds]}")
    zf = zipfile.ZipFile(hrf)
    tot = anatel.member_total(zf)
    rows = list(csv.reader(io.StringIO(zf.read(tot).decode("utf-8-sig")), delimiter=";"))
    header = [h.strip().lower() for h in rows[0]]
    i_ano = next(i for i, h in enumerate(header) if h.startswith("ano"))
    i_mes = next(i for i, h in enumerate(header) if h.startswith("m"))
    i_qtd = next((i for i, h in enumerate(header) if "acesso" in h), len(header) - 1)
    agg = {}
    for r in rows[1:]:
        try: k = (int(r[i_ano]), int(r[i_mes]))
        except Exception: continue
        agg[k] = agg.get(k, 0) + anatel.to_int(r[i_qtd])
    return agg, round(hrf.bytes_fetched / 1024)


def mkey(m): return f"{m[0]:04d}-{m[1]:02d}"
def mlabel(m): return f"{MESES.get(m[1], m[1])}/{m[0]}"
def fmt(n): return f"{n:,}".replace(",", ".")


def notify_windows(title, body):
    """Notificação toast best-effort via PowerShell (sem módulos externos)."""
    try:
        import subprocess
        ps = (
            'Add-Type -AssemblyName System.Windows.Forms;'
            '$n=New-Object System.Windows.Forms.NotifyIcon;'
            '$n.Icon=[System.Drawing.SystemIcons]::Information;$n.Visible=$true;'
            f'$n.ShowBalloonTip(15000,{json.dumps(title)},{json.dumps(body)},'
            '[System.Windows.Forms.ToolTipIcon]::Info);Start-Sleep -Seconds 6;$n.Dispose()'
        )
        subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        log(f"  (toast falhou: {e})")


def main():
    st = {}
    if os.path.exists(WSTATE):
        try: st = json.load(io.open(WSTATE, encoding="utf-8"))
        except Exception: st = {}

    latest = {}; kb_total = 0; erros = 0
    for ds in ROT:
        try:
            agg, kb = totals_live(ds); kb_total += kb
            m = max(agg)
            prev = max((k for k in agg if k < m), default=None)
            latest[ds] = {"mes": m, "total": agg[m], "mom": (agg[m] - agg[prev]) if prev else None}
        except Exception as e:
            erros += 1; log(f"  ERRO em {ds}: {e}")

    if not latest:
        log(f"checagem FALHOU (nenhum serviço lido). {kb_total} KB."); return

    novo_mes = max(v["mes"] for v in latest.values())
    baseline = tuple(st.get("baseline_mes", [])) if st.get("baseline_mes") else None

    # primeira execução: só registra o baseline, não dispara
    if baseline is None:
        st["baseline_mes"] = list(novo_mes)
        st["primeira_checagem"] = datetime.date.today().isoformat()
        st["ultima_checagem"] = datetime.datetime.now().isoformat(timespec="seconds")
        json.dump(st, io.open(WSTATE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        log(f"baseline registrado: {mlabel(novo_mes)}. Sem disparo (1ª checagem). {kb_total} KB.")
        return

    st["ultima_checagem"] = datetime.datetime.now().isoformat(timespec="seconds")

    if novo_mes <= baseline:
        json.dump(st, io.open(WSTATE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        log(f"sem novidade — Anatel ainda em {mlabel(baseline)}. {kb_total} KB.")
        return

    # ---- DISPAROU: mês novo ----
    mk = mkey(novo_mes)
    rep = [f"# Anatel — novo mês: {mlabel(novo_mes)}",
           f"\nDetectado em {datetime.date.today().isoformat()} · transferido {kb_total} KB (leitura ao vivo).\n",
           "| Serviço | Competência | Total | Variação m/m |",
           "|---|---|---:|---:|"]
    for ds, lab in ROT.items():
        d = latest.get(ds)
        if not d: rep.append(f"| {lab} | — | erro | — |"); continue
        mom = "" if d["mom"] is None else ("+" if d["mom"] >= 0 else "") + fmt(d["mom"])
        rep.append(f"| {lab} | {mlabel(d['mes'])} | {fmt(d['total'])} | {mom} |")
    rep.append("\n**Próximo passo (publish revisado):** abrir o Claude e dizer "
               "\"saiu o mês novo da Anatel, atualiza\". Os KPIs de destaque (TV/BL/fixa têm nuance de "
               "escopo vs _Total) devem ser conferidos contra o Teleco antes de subir. Móvel é 1:1 com o _Total.")
    io.open(os.path.join(STATE, f"anatel_{mk}.md"), "w", encoding="utf-8").write("\n".join(rep))

    with io.open(os.path.join(STATE, "CHANGELOG_ANATEL.md"), "a", encoding="utf-8") as f:
        f.write(f"\n## {mlabel(novo_mes)} (detectado {datetime.date.today().isoformat()})\n")
        for ds, lab in ROT.items():
            d = latest.get(ds)
            if d: f.write(f"- {lab}: {fmt(d['total'])}"
                          + (f" (m/m {'+' if d['mom']>=0 else ''}{fmt(d['mom'])})\n" if d['mom'] is not None else "\n"))

    io.open(os.path.join(STATE, "NOVO_MES.flag"), "w", encoding="utf-8").write(
        f"{mlabel(novo_mes)} detectado em {datetime.date.today().isoformat()} — rodar publish revisado.\n")

    st["baseline_mes"] = list(novo_mes)
    st["ultimo_disparo"] = {"mes": mk, "em": datetime.date.today().isoformat()}
    json.dump(st, io.open(WSTATE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    log(f"*** DISPAROU: Anatel publicou {mlabel(novo_mes)}! Relatório em state/anatel_{mk}.md ***")
    # auto-publish dos KPIs seguros (móvel/fixo, 1:1 com o _Total) + git push
    try:
        import subprocess
        r = subprocess.run([sys.executable, os.path.join(HERE, "anatel_publish.py")],
                           cwd=HERE, capture_output=True, text=True, timeout=600)
        log("  [auto-publish] " + ((r.stdout or "").strip().replace("\n", " | ") or "(sem saída)"))
        if r.returncode != 0:
            log("  [auto-publish ERRO] " + ((r.stderr or "").strip()[:500]))
    except Exception as e:
        log(f"  [auto-publish falhou] {e}")
    notify_windows("Anatel: novo mês + dashboard atualizado",
                   f"{mlabel(novo_mes)}: KPIs móvel/fixo já no ar. Reveja os manuais (TV/BL) em state/REVISAR.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("EXCEÇÃO:\n" + traceback.format_exc())
        sys.exit(1)
