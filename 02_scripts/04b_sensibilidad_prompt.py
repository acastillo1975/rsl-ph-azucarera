"""
04b_sensibilidad_prompt.py
==========================
Analisis de sensibilidad del chequeo con LLM (tertiary check) frente a la
FUGA DE INFORMACION detectada en el prompt de produccion: el Ejemplo 3 de
FIVE_SHOT_EXAMPLES en 04_filtrado_ollama.py reproduce el titulo, el resumen y
las palabras clave del estudio incluido Palacio-Morales et al. (2021).

El script NO modifica los resultados originales. Sobre los registros que en la
corrida productiva llegaron al LLM (nivel AUTO / INCIERTO; los LOCAL se
resuelven por reglas lexicas y no dependen del prompt) ejecuta dos corridas:

  A) prompt ORIGINAL            -> mide la reproducibilidad run-to-run (T=0)
  B) prompt CORREGIDO (sin fuga) -> Ejemplo 3 sustituido por un positivo
                                    sintetico de otra familia metodologica

y compara ambas con la decision productiva. Salida: 03_filtered_data/
4b.sensibilidad_prompt.xlsx + log.

Uso:  python 04b_sensibilidad_prompt.py
"""

import importlib.util
import logging
import os
import sys
import time
from datetime import datetime

import pandas as pd

AQUI = os.path.dirname(os.path.abspath(__file__))
DATOS = os.path.join(AQUI, "..", "03_filtered_data")
XLSX_PROD = os.path.join(DATOS, "4.filtrado_ollama.xlsx")
XLSX_OUT = os.path.join(DATOS, "4b.sensibilidad_prompt.xlsx")

spec = importlib.util.spec_from_file_location(
    "filtrado", os.path.join(AQUI, "04_filtrado_ollama.py")
)
filtrado = importlib.util.module_from_spec(spec)
spec.loader.exec_module(filtrado)

EJEMPLO_3_ORIGINAL = filtrado.FIVE_SHOT_EXAMPLES[
    filtrado.FIVE_SHOT_EXAMPLES.index("EJEMPLO 3"):
    filtrado.FIVE_SHOT_EXAMPLES.index("EJEMPLO 4")
]

# Positivo SINTETICO (no corresponde a ninguna publicacion): otra familia
# metodologica (ANFIS + gain scheduling) para no replicar el estudio incluido.
EJEMPLO_3_CORREGIDO = """EJEMPLO 3 - INCLUIR (positivo sintetico: ANFIS con gain scheduling para pH en encalado)
Titulo: "Gain-scheduled adaptive neuro-fuzzy controller for pH regulation in the
         liming stage of cane juice clarification"
Resumen: "An adaptive neuro-fuzzy inference system schedules the controller gain
         along the titration curve of cane juice and regulates pH in the liming
         tank against raw-juice flow and acidity disturbances. Compared with a
         fixed-gain PI controller in a plant-data-based simulation."
Keywords: pH control; liming; cane juice; ANFIS; gain scheduling; clarification
Decision correcta: INCLUIR   Confianza: 95
Justificacion: Aplica control neuro-difuso al pH del encalado del jugo de cana
              (clarificacion). Cumple A, B y C.

"""

PROMPT_ORIGINAL = filtrado.FIVE_SHOT_EXAMPLES
PROMPT_CORREGIDO = PROMPT_ORIGINAL.replace(EJEMPLO_3_ORIGINAL, EJEMPLO_3_CORREGIDO)
assert PROMPT_CORREGIDO != PROMPT_ORIGINAL, "No se pudo sustituir el Ejemplo 3"


def correr(df: pd.DataFrame, ejemplos: str, etiqueta: str, modelo: str) -> list[dict]:
    filtrado.FIVE_SHOT_EXAMPLES = ejemplos
    out = []
    for n, (_, r) in enumerate(df.iterrows(), 1):
        titulo = str(r.get("TI", "")).strip()
        resumen = str(r.get("AB", "")).strip()
        kw = str(r.get("KW", "")).strip()
        res = filtrado.llamar_ollama(
            filtrado.construir_prompt(titulo, resumen, kw), modelo
        )
        dec = (res or {}).get("decision", "ERROR").upper()
        conf = int((res or {}).get("confianza", 0))
        logging.info(f"[{etiqueta} {n}/{len(df)}] {dec} conf={conf}% | {titulo[:70]}")
        out.append({"decision": dec, "confianza": conf,
                    "justificacion": (res or {}).get("justificacion", "")})
        time.sleep(filtrado.SLEEP_BETWEEN_CALLS)
    return out


def main():
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(
                os.path.join(DATOS, f"sensibilidad_prompt_{datetime.now():%Y%m%d_%H%M%S}.log"),
                encoding="utf-8"),
        ],
    )
    df = pd.read_excel(XLSX_PROD)
    llm = df[df["nivel_certeza"].isin(["AUTO", "INCIERTO"])].copy()
    logging.info(f"Registros que llegaron al LLM en produccion: {len(llm)}")
    modelo = filtrado.detectar_modelo("llama3:latest")
    logging.info(f"Modelo: {modelo}  T={filtrado.TEMPERATURE}")

    a = correr(llm, PROMPT_ORIGINAL, "A-original", modelo)
    b = correr(llm, PROMPT_CORREGIDO, "B-sin-fuga", modelo)

    res = pd.DataFrame({
        "TI": llm["TI"].values, "PY": llm["PY"].values, "DO": llm["DO"].values,
        "decision_produccion": llm["decision_ollama"].values,
        "conf_produccion": llm["confianza_ollama"].values,
        "decision_A_original": [x["decision"] for x in a],
        "conf_A_original": [x["confianza"] for x in a],
        "decision_B_sin_fuga": [x["decision"] for x in b],
        "conf_B_sin_fuga": [x["confianza"] for x in b],
        "just_B": [x["justificacion"] for x in b],
    })
    res["A_igual_produccion"] = res["decision_A_original"] == res["decision_produccion"]
    res["B_igual_produccion"] = res["decision_B_sin_fuga"] == res["decision_produccion"]
    res.to_excel(XLSX_OUT, index=False)

    logging.info("=" * 60)
    logging.info(f"A (prompt original) coincide con produccion : "
                 f"{res.A_igual_produccion.sum()}/{len(res)}")
    logging.info(f"B (prompt sin fuga) coincide con produccion : "
                 f"{res.B_igual_produccion.sum()}/{len(res)}")
    logging.info(f"INCLUIR en B: {int((res.decision_B_sin_fuga == 'INCLUIR').sum())}")
    logging.info(f"Salida: {XLSX_OUT}")


if __name__ == "__main__":
    main()
