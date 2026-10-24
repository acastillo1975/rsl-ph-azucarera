"""
12_auditoria_conceptual.py
==========================
Verificacion lexica INDEPENDIENTE del umbral de co-ocurrencia (>=2) usado en
la red de palabras clave. Barre titulo + resumen + palabras clave de los 353
registros unicos (todos los tipos, anios y cuartiles; antes de cualquier filtro
de elegibilidad) y cuenta, por concepto nucleo de las RQ, cuantos registros lo
mencionan solos y en co-presencia con (i) pH/neutralizacion y (ii) contexto de
proceso azucarero. Los registros con co-presencia triple se listan con su
destino en el embudo de cribado.

Salida: 05_bibliometria/12.auditoria_conceptual.xlsx
Uso:    python 12_auditoria_conceptual.py
"""

import os
import re

import pandas as pd

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.join(AQUI, "..")
RIS = os.path.join(RAIZ, "01_raw_data", "fusion_export.ris")
OLLAMA = os.path.join(RAIZ, "03_filtered_data", "4.filtrado_ollama.xlsx")
SALIDA = os.path.join(RAIZ, "05_bibliometria", "12.auditoria_conceptual.xlsx")

CONCEPTOS = {
    "Soft sensor / sensor virtual": r"soft[- ]sensor|virtual sensor|inferential sensor|inferential measurement",
    "MPC / NMPC": r"model[- ]predictive control|\bnmpc\b|\bmpc\b|predictive controller",
    "Aprendizaje por refuerzo": r"reinforcement learning|\bddpg\b|q-learning|actor-critic",
    "PID / PI": r"\bpid\b|proportional[- ]integral|\bpi controller\b",
    "Control difuso / neuro-difuso": r"fuzzy|neuro-fuzzy|\banfis\b|takagi",
    "Metaheuristicas": r"genetic algorithm|particle swarm|differential evolution|pattern search|evolutionary|state transition algorithm|metaheuristic",
    "Control adaptativo / gain scheduling": r"adaptive control|gain[- ]schedul|self-tuning",
    "Redes neuronales / ML": r"neural network|machine learning|deep learning|random forest|support vector|lstm",
    "Gemelo digital": r"digital twin",
}
RE_PH = re.compile(r"\bph\b|neutrali[sz]|alkalini[sz]|alkalinity|liming|defecation|sulfitation|carbonatation")
RE_AZ = re.compile(
    r"sugar ?cane|cane juice|sugar juice|sugar mill|sugar factor|sugar industr|sugar beet|"
    r"juice clarif|clarifier|raw juice|mixed juice|cane sugar|beet sugar|sugar refin|saccharum|\bsugar\b"
)
RE_AZ_PROCESO = re.compile(
    r"sugar mill|sugar factor|sugar industr|sugar process|juice clarif|clarifier|raw juice|"
    r"mixed juice|sugar juice|cane juice|sugar beet|sugar refin|alkalini[sz]ation of sugar|liming"
)


def leer_ris(path: str) -> pd.DataFrame:
    regs, cur = [], {}
    with open(path, encoding="utf-8") as f:
        for linea in f:
            linea = linea.rstrip("\r\n")
            if linea.strip() == "ER  -":
                if cur:
                    regs.append(cur)
                cur = {}
            elif len(linea) > 5 and linea[2:6] == "  - ":
                k, v = linea[:2], linea[6:].strip()
                cur[k] = f"{cur[k]} ; {v}" if k in cur else v
    if cur:
        regs.append(cur)
    return pd.DataFrame(regs)


def main():
    df = leer_ris(RIS)
    for c in ("TI", "AB", "KW", "PY", "TY", "DO", "T2"):
        if c not in df:
            df[c] = ""
    df["X"] = (df["TI"].fillna("") + " " + df["AB"].fillna("") + " "
               + df["KW"].fillna("")).str.lower()
    ph = df["X"].str.contains(RE_PH)
    az = df["X"].str.contains(RE_AZ_PROCESO)
    print(f"Registros unicos: {len(df)} | con pH: {ph.sum()} | con proceso azucarero: {az.sum()} "
          f"| pH y proceso azucarero: {(ph & az).sum()}")

    filas, triples = [], {}
    for nombre, patron in CONCEPTOS.items():
        m = df["X"].str.contains(patron)
        filas.append({
            "Concepto": nombre,
            "Registros que lo mencionan": int(m.sum()),
            "+ pH": int((m & ph).sum()),
            "+ proceso azucarero": int((m & az).sum()),
            "+ pH + proceso azucarero": int((m & ph & az).sum()),
        })
        for i in df.index[m & ph & az]:
            triples.setdefault(i, []).append(nombre)
    resumen = pd.DataFrame(filas)
    print(resumen.to_string(index=False))

    # Destino en el embudo
    ol = pd.read_excel(OLLAMA)
    destino = {str(r["DO"]).lower(): (r["nivel_certeza"], r["decision_manual"])
               for _, r in ol.iterrows() if pd.notna(r["DO"])}
    det = []
    for i, conceptos in triples.items():
        r = df.loc[i]
        do = str(r["DO"]).lower()
        if do in destino:
            fate = f"En corpus Q1-Q4; nivel {destino[do][0]}; decision final {destino[do][1]}"
        else:
            fate = "Excluido antes del cribado (tipo/anio/cuartil)"
        det.append({"Anio": r["PY"], "Tipo": r["TY"], "Titulo": r["TI"], "DOI": r["DO"],
                    "Conceptos": "; ".join(conceptos), "Destino": fate})
    detalle = pd.DataFrame(det).sort_values(["Destino", "Anio"])
    print(f"\nRegistros con co-presencia triple: {len(detalle)}")
    print(detalle["Destino"].value_counts().to_string())

    os.makedirs(os.path.dirname(SALIDA), exist_ok=True)
    with pd.ExcelWriter(SALIDA) as w:
        resumen.to_excel(w, "Resumen_conceptos", index=False)
        detalle.to_excel(w, "Co-presencia_triple", index=False)
    print(f"\nSalida: {SALIDA}")


if __name__ == "__main__":
    main()
