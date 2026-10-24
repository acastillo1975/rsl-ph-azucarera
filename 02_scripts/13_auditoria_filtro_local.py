"""
13_auditoria_filtro_local.py
============================
Auditoria de sensibilidad del filtro lexico local (L0/L1/L2) de
04_filtrado_ollama.py. En la corrida productiva el filtro resolvio 201/230
registros (87.4 %) sin invocar al LLM. Este script re-examina esos 201 con un
criterio MAS LAXO e independiente (sin las stopwords L0 y sin exigir terminos
de IA): selecciona los que mencionan a la vez pH/neutralizacion/encalado y
vocabulario de proceso azucarero, y los vuelca a un CSV para lectura humana de
titulo y resumen frente a los criterios de elegibilidad.

Salida: 03_filtered_data/13.auditoria_filtro_local.csv
Uso:    python 13_auditoria_filtro_local.py
"""

import os
import re

import pandas as pd

AQUI = os.path.dirname(os.path.abspath(__file__))
DATOS = os.path.join(AQUI, "..", "03_filtered_data")

RE_PH = re.compile(r"\bph\b|neutrali[sz]|alkalini[sz]|liming|\blime\b|defecation|sulfitation|carbonatation|acid-base")
RE_PROC = re.compile(
    r"sugar mill|sugar factor|sugar industr|sugar process|juice clarif|clarifier|clarification|"
    r"cane juice|sugar juice|raw juice|mixed juice|sugar refin|sugar beet juice|sugarcane juice|"
    r"cane sugar|beet sugar"
)
RE_CTRL = re.compile(
    r"control|controller|\bpid\b|soft sensor|virtual sensor|identification|reinforcement|"
    r"setpoint|set-point|regulat|dosing|dosage|real-time|online|predictive control|\bmpc\b"
)


def main():
    df = pd.read_excel(os.path.join(DATOS, "4.filtrado_ollama.xlsx"))
    loc = df[df["nivel_certeza"] == "LOCAL"].copy()
    loc["X"] = loc.apply(
        lambda r: " ".join(str(r[c]) for c in ("TI", "AB", "KW") if pd.notna(r[c])).lower(), axis=1
    )
    solapa = loc["X"].str.contains(RE_PH) & loc["X"].str.contains(RE_PROC)
    ctrl = loc["X"].str.contains(RE_CTRL)
    sel = loc[solapa].copy()
    sel["con_vocab_control"] = ctrl[solapa].values
    print(f"Excluidos por filtro local: {len(loc)}")
    print(f"Con solapamiento lexico pH + proceso azucarero: {len(sel)}")
    print(f"  de ellos con vocabulario de control/estimacion: {int(sel['con_vocab_control'].sum())}")
    sel[["PY", "TI", "T2", "DO", "con_vocab_control", "AB"]].to_csv(
        os.path.join(DATOS, "13.auditoria_filtro_local.csv"), index=False, encoding="utf-8-sig"
    )


if __name__ == "__main__":
    main()
