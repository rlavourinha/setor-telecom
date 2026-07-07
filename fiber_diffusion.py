# -*- coding: utf-8 -*-
"""
fiber_diffusion.py — a onda da fibra: ano em que a fibra virou MAIORIA em cada município.

Lê data/historico_municipal.csv (bl, bl_fibra por município por ano, 2007->2026) e acha,
para cada município, o 1º ano em que a fibra passou de 50% da banda larga local (com base
mínima p/ reduzir ruído). Saída: data/fiber_arrival.json = {ibge: ano} (-1 = ainda não).
Também imprime a curva de difusão (nº de municípios "fibrados" por ano) e a mediana por região.
"""
import os, sys, csv, json
from collections import defaultdict
import anatel

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
MIN_BL = 50   # base mínima de banda larga p/ considerar o município


def main():
    # ibge -> {ano: (bl, fibra)}
    serie = defaultdict(dict); uf_de = {}
    with open(os.path.join(DATA, "historico_municipal.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            ib = r["ibge"]; uf_de[ib] = r["uf"]
            bl = int(r["bl"] or 0); fib = int(r["bl_fibra"] or 0)
            serie[ib][int(r["ano"])] = (bl, fib)

    arrival = {}
    for ib, ys in serie.items():
        ano_cross = -1
        for ano in sorted(ys):
            bl, fib = ys[ano]
            if bl >= MIN_BL and fib >= 0.5 * bl:
                ano_cross = ano; break
        arrival[ib] = ano_cross

    # curva de difusão: nº de municípios com fibra-maioria acumulado por ano
    anos = range(2010, 2027)
    cross = [v for v in arrival.values() if v > 0]
    print("Difusão da fibra — municípios em que a fibra virou MAIORIA (acumulado):")
    for y in anos:
        n = sum(1 for v in cross if v <= y)
        print(f"  {y}: {n:5d} municípios ({n/5570*100:4.0f}%)")
    nunca = sum(1 for v in arrival.values() if v < 0)
    print(f"  ainda não (fibra <50% ou base insuficiente): {nunca}")

    # mediana do ano de chegada por região
    import statistics as st
    reg = defaultdict(list)
    for ib, v in arrival.items():
        if v > 0 and uf_de.get(ib) in anatel.UF2REG: reg[anatel.UF2REG[uf_de[ib]]].append(v)
    print("\nAno MEDIANO em que a fibra virou maioria, por região:")
    for r in ["N", "NE", "CO", "SE", "S"]:
        if reg[r]: print(f"  {r}: {int(st.median(reg[r]))}  (n={len(reg[r])})")

    json.dump({"campo": "ano em que a fibra passou 50% da BL (-1=ainda não)", "d": arrival},
              open(os.path.join(DATA, "fiber_arrival.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("\nsalvo em data/fiber_arrival.json")


if __name__ == "__main__":
    main()
