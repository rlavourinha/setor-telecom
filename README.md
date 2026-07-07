# Setor de Telecomunicações Brasileiro — estudo + dashboard

Mapa de referência do setor de telecom brasileiro, no molde dos estudos de setor
elétrico e de saúde: **entender o sistema → benchmark internacional → empresas
listadas → monitor de dados**. Dashboard HTML autocontido (SVG inline, sem CDN de JS).

## Estrutura

```
index.html               dashboard autocontido (11 abas). Abrir direto no navegador.
anatel.py                lib de acesso (HTTP Range OU disco + parsers + classificador)
monitor.py               acompanhamento mensal LEVE (totais + share) — coleta → delta → digest
analise_regional.py      INTELIGÊNCIA do mês atual por UF (correlação fixa×móvel)
analise_competitiva.py   INTEGRADO × móvel-puro + concentração (HHI) por UF/município
mapa_dados.py            líder móvel/UF (linhas HUMANAS, sem M2M) + correlação fixo×pós -> mapas
mun_maps.py              por MUNICÍPIO: penetração pós/pré/fibra + líder pré/pós/BL + isp_intel.json
pospago_evol.py          dinâmica do pós-pago no tempo (gap do líder, efeito pós-Oi)
historico_municipal.py   HISTÓRICO completo por município/UF (lê os zips baixados)
data/                    (runtime) zips da Anatel + históricos gerados (fora do git)
state/                   (runtime) último snapshot consolidado p/ cálculo de delta
assets/                  (reservado)
```

## As abas

| # | Aba | O que cobre |
|---|-----|-------------|
| 00 | Visão geral | Os 3 mercados (móvel · fibra · legados) + as teses do estudo |
| 01 | Contexto histórico | Telebras → privatização 1998 → consolidação → colapso da Oi → 5G |
| 02 | Instituições & marco | Anatel, LGT (1997), Lei das Teles (2019), serviços/outorgas, Fust/Funttel |
| 03 | Mercado móvel | Acessos, mix pré/pós, market share, 5G, velocidade |
| 04 | Banda larga & fibra | FTTH vs legado, o domínio dos ISPs regionais, rede neutra (V.tal) |
| 05 | Fixo & TV paga | Declínio de STFC e SeAC |
| 06 | Regulação econômica | Leilão 5G (obrigação > caixa), Brasil vs Europa, fair share |
| 07 | Empresas | Vivo, TIM, Oi, Brisanet, Desktop, Unifique, V.tal — fundamentos |
| 08 | Internacional | Preço/GB, velocidade, % fibra, ARPU, 3-vs-4 operadoras |
| 09 | Acompanhamento | Indicadores vivos + a rotina de coleta |
| 10 | Agenda regulatória | IPO da V.tal, M&A, fair share, PGMU, desfecho da Oi |

## Rodar

```bash
# ver o dashboard: basta abrir index.html no navegador
# (ou servir estático: python -m http.server 8777 --directory .)

python monitor.py            # totais dos 4 serviços + delta (leve, ~20 KB)
python monitor.py --share    # + market share por operadora e tecnologia (~15 MB)
python monitor.py --demo     # amostra offline (não toca a rede)

python analise_regional.py   # estudo granular do MÊS atual: penetração/UF, correlação
                             # fixa×móvel, share por região, %fibra e %5G (~15 MB via Range)

# histórico completo por município (baixa os 4 zips ~4,3 GB p/ data/ e digere localmente):
curl -o data/acessos_telefonia_movel.zip \
  https://www.anatel.gov.br/dadosabertos/paineis_de_dados/acessos/acessos_telefonia_movel.zip
# (idem banda_larga_fixa / telefonia_fixa / tv_por_assinatura)
python historico_municipal.py   # -> historico_nacional.json, historico_uf.csv,
                                 #    historico_municipal.csv (5.571 municípios, 2007→2026)
python analise_competitiva.py   # -> integrado×móvel, HHI por UF/município, quem lidera
                                 #    cada mercado -> data/analise_competitiva.json
```

### Dado local vs HTTP Range

`anatel.open_zip()` usa o zip em `data/` se existir (offline, rápido); senão cai para
HTTP Range. Então: o **acompanhamento mensal** e a **análise do mês** rodam com ~15 MB
via Range (sem baixar nada); o **histórico municipal** precisa dos zips completos em
`data/`. Ambos leem os mesmos membros — a extração via Range é byte-a-byte idêntica ao
disco (reconciliação: soma dos municípios = total oficial da Anatel, ao dígito).

**Granularidade real da Anatel** (limite do dado, não do método): banda larga tem
município desde **2007**; móvel só desde **2019** (UF em 2009–2018, nacional antes).
O classificador de operadora mapeia os holdings atuais (Vivo=Telefónica, Claro=Telecom
Americas, TIM=Telecom Italia) — marcas legadas pré-consolidação caem em "Outros".

### Como o monitor puxa dado real sem baixar 4 GB

Os pacotes de Dados Abertos da Anatel são gigantes (móvel **3,1 GB**, banda larga
**~1 GB**), mas cada zip contém um pequeno `..._Total.csv` com a série mensal
agregada. O `monitor.py` usa `HttpRangeFile` — um arquivo *seekable* sobre
**HTTP Range** — para deixar o `zipfile` do Python ler só o diretório central (fim do
arquivo) + o membro alvo. Resultado: **~20 KB transferidos** para os 4 indicadores,
em vez de 4,3 GB. Sem dependências externas.

Saída (exemplo real, mai/2026): móvel 276,4 mi (pós 66%), banda larga 55,4 mi,
STFC 18,0 mi, TV 7,2 mi — com variação mês a mês e delta vs a última leitura salva.

> **Nota:** a competência mais recente da Anatel costuma vir *preliminar*
> (consolidação incompleta) — quedas m/m muito grandes se corrigem na leitura
> seguinte. O digest avisa isso.

## Convenções (herdadas dos outros estudos, NÃO QUEBRAR)

- **Sem dependências externas no HTML.** Gráficos são SVG inline; nada de Chart.js/CDN.
  Fontes via Google Fonts com fallback de sistema.
- **Séries nunca empilhadas.** Cada tecnologia/operadora é uma linha independente
  (esconder dado empilhando é proibido). Sempre a série mais longa disponível.
- **Chip de versão** no cabeçalho (`v1.0 · data`). **Selo "novo"** auto-reversível
  por `data-since` + `HIGHLIGHT` no script do rodapé. **Chips `data-asof`** envelhecem
  em âmbar após ~2 meses da data da versão.
- **Fontes primárias.** Anatel (Dados Abertos/Painéis), CVM (ITR/DFP), RI das
  companhias, ITU/OECD/GSMA/Ookla. Raciocínio de primeiros princípios, sem sell-side.

## Fontes principais

- **Anatel** — Dados Abertos / Painéis · **Teleco** (consolida Anatel) · **Conexis Brasil Digital**
- **CVM** (ITR/DFP) e **RI** de Vivo, TIM, Brisanet, Desktop, Unifique, Oi, V.tal
- **ITU · OECD Broadband Portal · GSMA · Ookla Speedtest Global Index · Cable.co.uk**

## Próximos passos (não implementados)

- **Share por operadora e tecnologia** no monitor: além do `..._Total.csv`, cada zip
  traz um `..._Colunas.csv` (pivotado por Grupo Econômico / Tecnologia / mês). Extrair
  esse membro via `HttpRangeFile` daria market share móvel e fibra-vs-legado ao vivo
  (transfere mais — dezenas de MB — então deixar opt-in via flag).
- Deep-dive por empresa (aba dedicada por ticker, como o dossiê da CVM).
- Alerta (e-mail/Slack) disparado pelo delta mensal.
- Baixar a série Anatel completa (Base dos Dados) para homogeneizar 2010→2026 numa
  única definição (a quebra com/sem M2M em 2021 está sinalizada nos gráficos).
