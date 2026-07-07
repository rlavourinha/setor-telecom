# -*- coding: utf-8 -*-
"""
anatel.py — utilitários de acesso aos Dados Abertos da Anatel (Painéis / Acessos).

Compartilhado por monitor.py (acompanhamento mensal leve) e analise_regional.py
(inteligência granular por município/UF). Só biblioteca padrão.

Ideia central: os zips da Anatel são gigantes (móvel 3,1 GB), mas contêm membros
pequenos e úteis:
  - "..._Total.csv"    -> série mensal agregada (Ano;Mês;[categoria;]Acessos)
  - "..._Colunas.csv"  -> microdado por prestadora/município, pivotado (1 coluna/mês)
`HttpRangeFile` deixa o zipfile ler SÓ os bytes de que precisa (diretório central +
membro-alvo), via HTTP Range — poucos KB/MB em vez do zip inteiro.
"""
import io, re, csv, zipfile, urllib.request

BASE = "https://www.anatel.gov.br/dadosabertos/paineis_de_dados/acessos"
UA = {"User-Agent": "telecom-monitor/1.0"}

ZIPS = {
    "movel": "acessos_telefonia_movel.zip",
    "bl":    "acessos_banda_larga_fixa.zip",
    "fixo":  "acessos_telefonia_fixa.zip",
    "tv":    "acessos_tv_por_assinatura.zip",
}

# Censo IBGE 2022 — população por UF (para densidade/penetração).
POP_UF = {
    "AC": 830018, "AL": 3127683, "AP": 733759, "AM": 3941613, "BA": 14141626,
    "CE": 8794957, "DF": 2817068, "ES": 3833712, "GO": 7056495, "MA": 6776699,
    "MT": 3658649, "MS": 2757013, "MG": 20538718, "PA": 8121025, "PB": 3974687,
    "PR": 11444380, "PE": 9058931, "PI": 3271199, "RJ": 16054524, "RN": 3302729,
    "RS": 10882965, "RO": 1581196, "RR": 636707, "SC": 7610361, "SP": 44411238,
    "SE": 2210004, "TO": 1511460,
}
REGIAO = {
    "N":  ["AC", "AP", "AM", "PA", "RO", "RR", "TO"],
    "NE": ["AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"],
    "CO": ["DF", "GO", "MT", "MS"],
    "SE": ["ES", "MG", "RJ", "SP"],
    "S":  ["PR", "RS", "SC"],
}
UF2REG = {uf: reg for reg, ufs in REGIAO.items() for uf in ufs}


class HttpRangeFile(io.RawIOBase):
    """Arquivo seekable sobre HTTP Range — puxa só os bytes solicitados."""
    def __init__(self, url):
        self.url = url; self.pos = 0; self.bytes_fetched = 0
        req = urllib.request.Request(url, method="HEAD", headers=UA)
        with urllib.request.urlopen(req, timeout=60) as r:
            self.size = int(r.headers["Content-Length"])
    def seekable(self): return True
    def readable(self): return True
    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else (self.pos + off if whence == 1 else self.size + off)
        return self.pos
    def tell(self): return self.pos
    def read(self, n=-1):
        if n is None or n < 0: n = self.size - self.pos
        if n == 0 or self.pos >= self.size: return b""
        end = min(self.pos + n, self.size) - 1
        req = urllib.request.Request(self.url, headers={**UA, "Range": f"bytes={self.pos}-{end}"})
        with urllib.request.urlopen(req, timeout=300) as r:
            data = r.read()
        self.pos += len(data); self.bytes_fetched += len(data)
        return data


import os
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


class _LocalFile:
    """Espelha a interface de HttpRangeFile (.bytes_fetched) para zip em disco."""
    def __init__(self, path):
        self.path = path; self.bytes_fetched = 0
        self.size = os.path.getsize(path)


def open_zip(dataset):
    """
    Abre o zip do dataset ('movel'|'bl'|'fixo'|'tv'). Se o arquivo existir em data/,
    lê do DISCO (offline, rápido); senão, via HTTP Range. Retorna (ZipFile, fonte).
    """
    local = os.path.join(DATA_DIR, ZIPS[dataset])
    if os.path.exists(local):
        return zipfile.ZipFile(local), _LocalFile(local)
    hrf = HttpRangeFile(f"{BASE}/{ZIPS[dataset]}")
    return zipfile.ZipFile(hrf), hrf


def member_total(zf):
    """Nome do membro '..._Total.csv' (série agregada)."""
    return next((n for n in zf.namelist() if n.endswith("_Total.csv")), None)


def latest_colunas(zf, exclude=("Modalidade", "Tecnologia_Colunas", "Concessionarias")):
    """
    Nome do membro '..._Colunas.csv' mais recente (microdado por município).
    Ignora recortes especiais (modalidade/tecnologia históricos e concessionárias).
    Escolhe pelo nome (que ordena cronologicamente).
    """
    cands = [n for n in zf.namelist() if "Colunas" in n and not any(x in n for x in exclude)]
    return sorted(cands)[-1] if cands else None


_MONTH = re.compile(r"^\d{4}-\d{2}$")


def read_colunas(zf, member):
    """
    Lê um membro Colunas. Retorna (header, month_cols, rows) onde:
      header     = lista de nomes de coluna
      month_cols = lista de (nome_mes, indice) das colunas mensais
      rows       = gerador de listas (uma por linha de dados)
    Streaming — não carrega o CSV inteiro na memória.
    """
    fp = io.TextIOWrapper(zf.open(member), encoding="utf-8-sig", newline="")
    reader = csv.reader(fp, delimiter=";")
    header = next(reader)
    month_cols = [(h, i) for i, h in enumerate(header) if _MONTH.match(h)]
    return header, month_cols, reader


def col_index(header, *cands):
    """Índice da 1ª coluna cujo nome (lower) contém um dos candidatos."""
    low = [h.strip().lower() for h in header]
    for c in cands:
        for i, h in enumerate(low):
            if c in h:
                return i
    return None


import unicodedata

def _sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def classifica_grupo(nome):
    """
    Grupo Econômico (Anatel) -> marca comercial. Nomes reais na base são os holdings:
    Vivo=TELEFONICA, Claro=TELECOM AMERICAS, TIM=TELECOM ITALIA, Oi=OI. Keyword, não fixo.
    Normaliza acentos: a Anatel usou 'TELEFÔNICA' (com Ô) até ~2021 e 'TELEFONICA' depois.
    """
    n = _sem_acento((nome or "").upper())
    if "TELEFONICA" in n or "VIVO" in n: return "Vivo"
    if "TELECOM AMERICAS" in n or "CLARO" in n or "AMERICA MOVIL" in n: return "Claro"
    if "TELECOM ITALIA" in n or n == "TIM" or n.startswith("TIM "): return "TIM"
    if n == "OI" or n.startswith("OI ") or "TELEMAR" in n: return "Oi"
    if "ALGAR" in n: return "Algar"
    if "SKY" in n: return "Sky"
    return "Outros/ISPs"


def to_int(s):
    s = (s or "").strip()
    if not s:
        return 0
    try:
        return int(float(s.replace(".", "").replace(",", ".")))
    except ValueError:
        return 0
