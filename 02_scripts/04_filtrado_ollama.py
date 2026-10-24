"""
04_filtrado_ollama.py
================================
Pipeline de cribado semantico con Ollama para la RSL sobre
APLICACIONES DE ML PARA EL CONTROL DE pH EN LA INDUSTRIA AZUCARERA.

Genera archivos:
  - Excel con 2 hojas: Clasificacion | Metricas
  - RIS con articulos INCLUIR (decision automatica)
  - Log con timestamp en /output (consola + archivo)

Niveles de certeza:
  AUTO     -> conf >= CONFIDENCE_THRESHOLD_AUTO
  REVISAR  -> CONFIDENCE_THRESHOLD_HUMAN <= conf < CONFIDENCE_THRESHOLD_AUTO
  INCIERTO -> conf < CONFIDENCE_THRESHOLD_HUMAN (forzado a EXCLUIR)
  LOCAL    -> excluido por filtro local sin llamar al LLM

Uso:
  python 04_filtrado_ollama.py
  python 04_filtrado_ollama.py --input ..\03_filtered_data\3.filtrado_quartiles.ris --output ..\03_filtered_data
  python 04_filtrado_ollama.py --test
  python 04_filtrado_ollama.py --dry-run
  python 04_filtrado_ollama.py --model llama3.1:8b --log-level DEBUG
"""

import os
import sys
import json
import re
import time
import logging
import argparse
from datetime import datetime

import pandas as pd
import ollama


# ==============================================================================
# CONSTANTES DE NEGOCIO (no se exponen por CLI)
# ==============================================================================

OLLAMA_MODEL               = "llama3"
MAX_RETRIES                = 3
TEMPERATURE                = 0
SLEEP_BETWEEN_CALLS        = 0.5
CONFIDENCE_THRESHOLD_AUTO  = 75
CONFIDENCE_THRESHOLD_HUMAN = 55

PRECISION_OBJETIVO = "> 80 %"
PROTOCOLO          = "Six-shot + three-level local filter relajado (pH sugar)"
OLLAMA_TAG         = "Ollama-five-shot-pH"

MODELOS_PREFERIDOS = [
    "llama3", "llama3:latest", "llama3:8b",
    "llama3.1", "llama3.1:8b", "llama3.1:latest",
    "llama3.2", "llama3.2:3b", "llama3.2:latest",
    "mistral", "mistral:latest", "mistral:7b",
    "mixtral", "gemma2", "gemma2:9b",
    "phi3", "qwen2", "deepseek-r1",
]

logger = logging.getLogger("filtrado_ollama")


# ==============================================================================
# LOGGING
# ==============================================================================

def configurar_logging(output_folder: str, log_level: str) -> str:
    os.makedirs(output_folder, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(output_folder, f"filtrado_ollama_{timestamp}.log")

    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    logger.handlers.clear()

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return log_path


# ==============================================================================
# FILTRO LOCAL TRES NIVELES (L0 / L1 / L2)
# ==============================================================================

STOPWORDS_EXCLUSION_L0 = [
    "blood pH", "urine pH", "gastric pH", "physiological pH",
    "cell culture pH", "plasma pH", "serum pH",
    "blood acid-base", "arterial pH", "venous pH",
    "wastewater pH", "effluent pH", "drinking water pH",
    "groundwater pH", "river pH", "lake pH",
    "water treatment pH", "acid mine drainage",
    "desalination pH", "membrane pH",
    "pharmaceutical pH", "drug pH", "tablet pH",
    "bioreactor pH control ferment", "fermentation broth pH",
    "anaerobic digestion pH", "biogas pH",
    "microbial pH", "yeast pH", "bacterial pH",
    "cell culture pH", "bioprocess pH",
    "wine pH", "beer pH", "dairy pH", "milk pH",
    "yogurt pH", "cheese pH", "fruit juice pH",
    "orange juice pH", "tomato pH", "olive oil pH",
    "electroplating pH", "leaching pH", "hydrometallurgy pH",
    "ore processing pH", "soil pH",
    "massecuite", "pan boiling", "vacuum pan",
    "crystal size distribution", "sugar crystalliz",
    "supersaturation sucrose", "crystal growth sugar",
    "sugar centrifug", "molasses exhaustion",
    "remote sensing cane", "satellite cane field",
    "ndvi cane", "crop yield cane", "evapotranspiration cane",
    "ethanol fermentation", "bioethanol production",
    "fermentable sugar", "enzymatic hydrolysis bagasse",
    "bioethanol from sugarcane", "sugarcane fermentation",
    "shelf life", "shelf-life", "natural preservative",
    "sensory evaluation", "sensory analysis",
    "physicochemical and sensory", "phenolic bio-access",
    "cold plasma processing", "jam preparation",
    "essential oil extract", "supercritical co2",
    "dna extract", "rna extract", "protein extract",
    "adsorption of dyes", "activated carbon adsorb",
    "chromium adsorption", "dye removal adsorb",
    "magnetization parameter", "circuit board",
    "machining",
]

REQUIRED_PH_TERMS_L1 = [
    "ph control", "ph monitor", "ph predict", "ph estim",
    "ph optim", "ph measur", "ph adjust", "ph regulat",
    "ph neutral", "ph sensor", "ph probe", "juice ph",
    "ph level", "ph value", "ph setpoint",
    "acidity control", "alkalinity control", "alkalinization",
    "alkalisation", "lime dosage", "lime addition",
    "calcium hydroxide", "milk of lime", "liming",
    "defecation", "sulfitation", "carbonatation",
    "juice clarif", "sugar clarif",
    "acidity", "alkalinity", "acid-base",
]

REQUIRED_SUGAR_TERMS_L1 = [
    "sugar mill", "sugar factory", "sugar industry", "sugar juice",
    "sugar cane", "sugar beet", "sugar process", "sugar clarif",
    "sugarcane", "cane juice", "cane sugar",
    "juice clarif", "juice alkalin",
    "beet sugar", "beet factory",
    "sucrose", "bagasse", "molasses",
    " sugar ",
]

REQUIRED_AI_TERMS_L2 = [
    "machine learning", "artificial intelligence", "deep learning",
    "neural network", "neural net", "artificial neural",
    "random forest", "gradient boosting", "xgboost", "lightgbm",
    "support vector", "decision tree", "ensemble learn",
    "extreme learning", "kelm", "elm machine",
    "lstm", "long short-term memory", "gru", "recurrent neural",
    "convolutional neural", "cnn", "transformer model",
    "attention mechanism", "autoencoder",
    "model predictive control", "mpc control",
    "reinforcement learning", "deep reinforcement",
    "ddpg", "ppo agent", "dqn agent", "actor-critic",
    "proximal policy", "q-learning", "multi-agent",
    "soft sensor", "virtual sensor", "data-driven model",
    "data driven", "physics-informed", "pinn model",
    "digital twin", "grey-box model", "hybrid model",
    "optimization", "optimisation", "genetic algorithm",
    "particle swarm", "ant colony", "differential evolution",
    "bayesian optim", "gaussian process",
    "predictive model", "prediction model", "regression model",
    "anomaly detection", "fault detection", "predictive maintenance",
    "process monitoring", "statistical process",
    "shap analysis", "explainable", "interpretable model",
    "feature importance",
    "computer vision", "nir spectroscop",
    "real time optim", "rto method",
]


def contiene_palabras_clave(texto: str) -> tuple[bool, str]:
    T = texto.lower()
    for bad in STOPWORDS_EXCLUSION_L0:
        if bad.lower() in T:
            return False, f"Stopword L0: '{bad}'"
    tiene_ph    = any(t in T for t in REQUIRED_PH_TERMS_L1)
    tiene_sugar = any(t in T for t in REQUIRED_SUGAR_TERMS_L1)
    if not tiene_ph:
        return False, "Sin terminos de pH/acidez/encalado (L1-pH)"
    if not tiene_sugar:
        return False, "Sin terminos de industria azucarera (L1-sugar)"
    if not any(t in T for t in REQUIRED_AI_TERMS_L2):
        return False, "Sin terminos de IA / ML (L2)"
    return True, ""


# ==============================================================================
# FIVE-SHOT EXAMPLES
# ==============================================================================

FIVE_SHOT_EXAMPLES = """
=== EJEMPLOS DE REFERENCIA (six-shot) ===

EJEMPLO 1 - INCLUIR (positivo: ANN para prediccion de pH en clarificacion azucarera)
Titulo: "Artificial neural network for real-time pH prediction in sugarcane juice
         clarification: lime dosage optimization in a Brazilian sugar mill"
Resumen: "A multilayer perceptron trained on 24 months of DCS data predicts
         clarified juice pH from lime flow rate, raw juice flow, temperature and
         Brix. MAE=0.04 pH units. Reduces lime overconsumption by 18%."
Keywords: ANN; pH prediction; juice clarification; lime dosage; sugar mill; machine learning
Decision correcta: INCLUIR   Confianza: 97
Justificacion: Aplica ANN directamente a la prediccion de pH en la clarificacion del
              jugo azucarero con datos DCS reales. Cumple criterios A (ANN), B (prediccion)
              y C (control de pH en industria azucarera).

EJEMPLO 2 - INCLUIR (positivo: LSTM + soft sensor para pH en linea)
Titulo: "LSTM-based soft sensor for online pH estimation in sugar cane juice
         purification without physical pH probe"
Resumen: "An LSTM model estimates juice pH from conductivity, temperature, turbidity,
         Brix and lime flow using 18 months of plant data. R2=0.96, RMSE=0.05.
         Validated across two crushing seasons in a South African sugar factory."
Keywords: LSTM; soft sensor; pH estimation; juice purification; sugar factory; DCS
Decision correcta: INCLUIR   Confianza: 96
Justificacion: Construye sensor virtual de pH para la purificacion del jugo azucarero
              usando LSTM con variables DCS. Cumple los tres criterios de inclusion.

EJEMPLO 3 - INCLUIR (positivo: NMPC+fuzzy para pH en alcalinizacion de jugo azucarero)
Titulo: "Optimization based on pattern search algorithm applied to pH non-linear control:
         Application to alkalinization process of sugar juice"
Resumen: "A Takagi-Sugeno fuzzy inference model combined with a non-linear model predictive
         controller (NMPC) tuned via pattern search optimization (PSM) controls pH in the
         alkalinization of sugar juice. Steady-state error reduced vs. other algorithms."
Keywords: pH control; alkalinization; sugar juice; NMPC; fuzzy; pattern search; nonlinear
Decision correcta: INCLUIR   Confianza: 95
Justificacion: Aplica NMPC + logica difusa directamente al control de pH en la
              alcalinizacion del jugo de azucar (etapa de clarificacion). Cumple A, B y C.

EJEMPLO 4 - EXCLUIR (negativo: pH en biorreactor de bioetanol de cana)
Titulo: "Machine learning control of fermentation pH for bioethanol production
         from sugarcane bagasse"
Resumen: "Random forest and gradient boosting optimize pH in bioethanol fermentation
         reactors using sugarcane bagasse as feedstock. RMSE=0.03 pH units."
Keywords: machine learning; pH control; fermentation; bioethanol; sugarcane bagasse
Decision correcta: EXCLUIR   Confianza: 96
Justificacion: El proceso es fermentacion para bioetanol, no purificacion/clarificacion
              del jugo azucarero. El bagaso es solo materia prima del biorreactor (X1).

EJEMPLO 5 - EXCLUIR (negativo: pH en cristalizacion, no clarificacion)
Titulo: "Neural network prediction of massecuite pH and crystal size in vacuum pan"
Resumen: "An ANN predicts pH and sucrose crystallization kinetics in vacuum pans
         using upstream clarified juice purity and Brix as inputs."
Keywords: neural network; pH; vacuum pan; sugar crystallization; massecuite
Decision correcta: EXCLUIR   Confianza: 91
Justificacion: El proceso objetivo principal es la cristalizacion en tachos de vacio.
              El pH es variable secundaria; la etapa no es clarificacion (X3/X4).

EJEMPLO 6 - EXCLUIR (negativo: pH en aguas residuales de fabrica azucarera)
Titulo: "Deep learning for pH prediction in sugar factory wastewater treatment"
Resumen: "CNN-LSTM models predict effluent pH in the wastewater treatment plant of
         a sugar mill. Data from sensors monitoring BOD, COD and suspended solids."
Keywords: deep learning; pH; wastewater; sugar mill; effluent; CNN-LSTM
Decision correcta: EXCLUIR   Confianza: 95
Justificacion: El proceso es tratamiento de aguas residuales de la fabrica, no
              clarificacion/purificacion del jugo azucarero (X2 — proceso auxiliar).

=== FIN DE EJEMPLOS ===
"""


def construir_prompt(titulo: str, resumen: str, keywords: str) -> str:
    return f"""Actua como revisor experto en una revision sistematica (RSL) sobre
APRENDIZAJE AUTOMATICO aplicado al CONTROL DE pH EN LA INDUSTRIA AZUCARERA
(clarificacion, encalado, sulfitacion, purificacion del jugo de cana y remolacha).

{FIVE_SHOT_EXAMPLES}

=== CRITERIOS DE DECISION ===

INCLUIR si el articulo cumple TODOS:
  A) Aplica tecnica de ML/IA: machine learning, deep learning, redes neuronales,
     soft sensors, reinforcement learning, MPC, LSTM, CNN, fuzzy logic,
     XGBoost, gemelos digitales, modelos data-driven, PINN, etc.
  B) La aplicacion es CONTROL, PREDICCION, ESTIMACION, MONITOREO u
     OPTIMIZACION del pH (o variables equivalentes: acidez, alcalinidad,
     dosis de cal, dosis de SO2) mediante ML/IA.
  C) El proceso objetivo PRINCIPAL es la INDUSTRIA AZUCARERA:
     clarificacion, encalado (liming), defecacion, sulfitacion, carbonatacion
     o purificacion del jugo de cana o remolacha azucarera.

EXCLUIR si se cumple CUALQUIERA:
  X1) pH en procesos NO azucareros: aguas residuales, farmaceutica, lacteos,
      vino, cerveza, biorreactores de bioetanol, digestores anaerobios.
  X2) pH en suelo, agua subterranea, rios o medio ambiente.
  X3) pH en procesos azucareros distintos a clarificacion/encalado/sulfitacion:
      cristalizacion, centrifugacion, evaporacion, fermentacion.
  X4) Azucar/pH en contexto multi-industria alimentaria; no focalizado en azucar.
  X5) ML marginal; pH es solo variable de entrada, no objetivo del modelo.
  X6) pH en tejidos biologicos, sangre, orina, cultivos celulares o farmacia.
  X7) Control de pH en tratamiento de efluentes de la fabrica azucarera.
  X8) pH en produccion de bioetanol o biocombustibles de cana.

Razona internamente en 4 pasos (NO los incluyas en la respuesta):
  Paso 1: El proceso objetivo PRINCIPAL involucra pH en clarificacion/encalado azucarero?
  Paso 2: Se aplica ML/IA como componente PRINCIPAL para controlar/predecir el pH?
  Paso 3: Aplica alguna condicion X1-X8?
  Paso 4: Determina decision y asigna confianza 0-100.

Responde UNICAMENTE con este JSON exacto, sin texto adicional ni markdown:

{{
  "decision": "INCLUIR" o "EXCLUIR",
  "confianza": numero entre 0 y 100,
  "justificacion": "Texto conciso maximo 2 oraciones con el criterio decisivo"
}}

=== ARTICULO A EVALUAR ===

Titulo: {titulo}
Resumen: {resumen}
Palabras clave: {keywords}
"""


def construir_prompt_simplificado(titulo: str, resumen: str) -> str:
    return (
        "Revisor RSL sobre ML aplicado al control de pH en la industria azucarera.\n\n"
        f"Titulo: {titulo}\n"
        f"Resumen: {resumen[:600]}\n\n"
        "Responde con UNA SOLA PALABRA: INCLUIR o EXCLUIR.\n"
        "No escribas nada mas."
    )


# ==============================================================================
# DETECCION AUTOMATICA DE MODELO
# ==============================================================================

def detectar_modelo(preferido: str = None) -> str:
    try:
        lista = ollama.list()
        raw = lista.models if hasattr(lista, "models") else lista.get("models", [])
        nombres = []
        for m in raw:
            if hasattr(m, "model"):   nombres.append(m.model)
            elif hasattr(m, "name"):  nombres.append(m.name)
            elif isinstance(m, dict): nombres.append(m.get("model", m.get("name", "")))
        nombres = [n for n in nombres if n]
        if not nombres:
            return preferido or OLLAMA_MODEL
        logger.info(f"Modelos disponibles: {nombres}")
        if preferido:
            base_pref = preferido.split(":")[0].lower()
            for disp in nombres:
                if disp == preferido or disp.split(":")[0].lower() == base_pref:
                    return disp
            logger.warning(f"Modelo '{preferido}' no disponible. Buscando fallback.")
        for pref in MODELOS_PREFERIDOS:
            base = pref.split(":")[0].lower()
            for disp in nombres:
                if disp == pref or disp.split(":")[0].lower() == base:
                    return disp
        return nombres[0]
    except Exception as e:
        logger.warning(f"No se pudo enumerar modelos Ollama: {e}")
        return preferido or OLLAMA_MODEL


# ==============================================================================
# LECTURA Y ESCRITURA RIS
# ==============================================================================

def leer_ris(filepath: str) -> pd.DataFrame:
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"No se encontró: {filepath}")
    if os.path.isdir(filepath):
        raise IsADirectoryError(f"--input debe ser un archivo .ris, no carpeta: {filepath}")

    entradas, actual = [], {}
    with open(filepath, "r", encoding="utf-8") as f:
        for linea in f:
            linea = linea.rstrip("\n").rstrip("\r")
            if linea.strip() == "ER  -":
                if actual:
                    entradas.append(actual)
                actual = {}
            elif "  -" in linea:
                partes = linea.split("  - ", 1)
                if len(partes) == 2:
                    clave, valor = partes[0].strip(), partes[1].strip()
                    if clave in actual:
                        if isinstance(actual[clave], list):
                            actual[clave].append(valor)
                        else:
                            actual[clave] = [actual[clave], valor]
                    else:
                        actual[clave] = valor
    if actual:
        entradas.append(actual)
    return pd.DataFrame(entradas)


def _val_ok(val) -> bool:
    if val is None:
        return False
    if isinstance(val, list):
        return any(str(v).strip() for v in val)
    try:
        import numpy as np
        if isinstance(val, (np.ndarray, pd.Series)):
            return bool(pd.notna(val).any()) and any(str(v).strip() for v in val)
    except Exception:
        pass
    try:
        return bool(pd.notna(val)) and bool(str(val).strip())
    except Exception:
        return False


FIELD_TO_TAG = {
    "Reference Type": "TY", "Title": "TI", "Secondary Title": "T2",
    "Year": "PY", "Start Page": "SP", "End Page": "EP",
    "DOI": "DO", "URLs": "UR", "Author Address": "AD",
    "Abstract": "AB", "Keywords": "KW", "Publisher": "PB",
    "ISSN": "SN", "Language": "LA", "Alternate Title": "J2",
    "Name of Database": "DB", "Notes": "N1", "Volume": "VL",
    "Number": "IS", "Author": "AU", "Label": "LB",
}


def escribir_ris(df_out: pd.DataFrame, filepath: str) -> None:
    cols_skip = {"decision_ollama", "justificacion_ollama",
                 "confianza_ollama", "nivel_certeza", "TY", "Reference Type"}
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        for _, row in df_out.iterrows():
            f.write("TY  - JOUR\n")
            for col in df_out.columns:
                if col in cols_skip:
                    continue
                val = row.get(col)
                if not _val_ok(val):
                    continue
                tag = FIELD_TO_TAG.get(col) or (col if len(col) <= 2 else None)
                if not tag:
                    continue
                if isinstance(val, list):
                    for v in val:
                        if str(v).strip():
                            f.write(f"{tag}  - {v}\n")
                else:
                    f.write(f"{tag}  - {val}\n")
            f.write("ER  - \n\n")


# ==============================================================================
# EXTRACCION JSON (cascada de estrategias)
# ==============================================================================

def _normalizar(texto: str) -> str:
    for orig, repl in {
        "\u201c": '"', "\u201d": '"', "\u2018": "'", "\u2019": "'",
        "\u00ab": '"', "\u00bb": '"', "\r\n": " ", "\r": " ",
    }.items():
        texto = texto.replace(orig, repl)
    return texto


def extraer_json(texto: str) -> dict | None:
    texto = _normalizar(texto)
    try:
        return json.loads(texto.strip())
    except Exception:
        pass
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", texto, re.DOTALL | re.IGNORECASE)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    m = re.search(r"\{[^{}]*\}", texto, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except Exception:
            pass
    start = texto.find("{")
    if start != -1:
        depth, end = 0, -1
        for i, ch in enumerate(texto[start:], start):
            depth += (ch == "{") - (ch == "}")
            if depth == 0:
                end = i
                break
        if end != -1:
            try:
                return json.loads(texto[start:end + 1])
            except Exception:
                pass
    dm = re.search(r'"decision"\s*:\s*"(INCLUIR|EXCLUIR)"', texto, re.IGNORECASE)
    cm = re.search(r'"confianza"\s*:\s*(\d+)', texto)
    jm = re.search(r'"justificacion"\s*:\s*"([^"]*)"', texto)
    if dm and cm:
        return {"decision": dm.group(1).upper(), "confianza": int(cm.group(1)),
                "justificacion": jm.group(1) if jm else "Extraido por regex"}
    up = texto.upper()
    if "INCLUIR" in up and "EXCLUIR" not in up:
        return {"decision": "INCLUIR", "confianza": 58,
                "justificacion": "Inferido por presencia de INCLUIR"}
    if "EXCLUIR" in up and "INCLUIR" not in up:
        return {"decision": "EXCLUIR", "confianza": 58,
                "justificacion": "Inferido por presencia de EXCLUIR"}
    return None


# ==============================================================================
# LLAMADA A OLLAMA CON REINTENTOS
# ==============================================================================

def llamar_ollama(prompt: str, modelo: str) -> dict | None:
    for intento in range(1, MAX_RETRIES + 1):
        try:
            resp = ollama.chat(
                model=modelo,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": TEMPERATURE},
            )
            resultado = extraer_json(resp.message.content)
            if resultado and "decision" in resultado:
                return resultado
            logger.warning(
                f"Intento {intento}: JSON no extraido. "
                f"Respuesta: {resp.message.content[:150]}"
            )
        except Exception as e:
            logger.error(f"Intento {intento}: Error Ollama: {e}")
        if intento < MAX_RETRIES:
            time.sleep(2)

    logger.warning("Usando prompt simplificado de ultimo recurso...")
    try:
        tit = prompt.split("Titulo:")[-1].split("\n")[0].strip()[:200]
        res = prompt.split("Resumen:")[-1].split("Palabras")[0].strip()[:400]
        resp = ollama.chat(
            model=modelo,
            messages=[{"role": "user", "content":
                       construir_prompt_simplificado(tit, res)}],
            options={"temperature": 0},
        )
        dec = "INCLUIR" if "INCLUIR" in resp.message.content.upper() else "EXCLUIR"
        return {"decision": dec, "confianza": 55,
                "justificacion": "Decision simplificada (prompt de rescate)"}
    except Exception as e:
        logger.error(f"Error en prompt simplificado: {e}")
        return None


# ==============================================================================
# MODO PRUEBA
# ==============================================================================

EJEMPLOS_TEST = [
    {
        "titulo": "ANN for real-time pH prediction in sugarcane juice clarification with lime dosage optimization",
        "resumen": "A multilayer perceptron trained on DCS data predicts clarified juice pH from lime flow, raw juice flow, temperature and Brix. MAE=0.04 pH units. Reduces lime overconsumption by 18%.",
        "keywords": "ANN; pH prediction; juice clarification; lime dosage; sugar mill; machine learning",
        "esperado": "INCLUIR", "conf_min": 85,
    },
    {
        "titulo": "Optimization based on pattern search applied to pH non-linear control: alkalinization of sugar juice",
        "resumen": "Takagi-Sugeno fuzzy inference model combined with NMPC tuned via pattern search (PSM) controls pH in the alkalinization of sugar juice. Steady-state error reduced vs. other algorithms.",
        "keywords": "pH control; alkalinization; sugar juice; NMPC; fuzzy; pattern search",
        "esperado": "INCLUIR", "conf_min": 80,
    },
    {
        "titulo": "LSTM-based soft sensor for online pH estimation in sugarcane juice purification",
        "resumen": "LSTM estimates juice pH from conductivity, temperature, turbidity, Brix and lime flow. R2=0.96, RMSE=0.05. Validated across two crushing seasons.",
        "keywords": "LSTM; soft sensor; pH; juice purification; sugar factory; DCS",
        "esperado": "INCLUIR", "conf_min": 85,
    },
    {
        "titulo": "Machine learning control of fermentation pH for bioethanol from sugarcane bagasse",
        "resumen": "Random forest optimizes pH in bioethanol fermentation reactors using sugarcane bagasse. RMSE=0.03 pH units.",
        "keywords": "machine learning; pH; fermentation; bioethanol; sugarcane bagasse",
        "esperado": "EXCLUIR", "conf_min": 85,
    },
    {
        "titulo": "Neural network prediction of pH in sugar factory wastewater treatment",
        "resumen": "CNN-LSTM predicts effluent pH in the wastewater treatment plant of a sugar mill from BOD, COD and suspended solids.",
        "keywords": "neural network; pH; wastewater; sugar mill; effluent",
        "esperado": "EXCLUIR", "conf_min": 80,
    },
    {
        "titulo": "Deep learning for pH across food industries: sugarcane clarification, wine, dairy",
        "resumen": "CNN-LSTM predicts pH across four food industries. Sugarcane clarification is one of four cases without focused optimization.",
        "keywords": "deep learning; pH; sugarcane; wine; dairy; CNN-LSTM; food",
        "esperado": "EXCLUIR", "conf_min": 75,
    },
]


def modo_prueba(modelo: str) -> None:
    logger.info("=" * 68)
    logger.info(f"MODO DE PRUEBA  |  Modelo: {modelo}")
    logger.info("=" * 68)
    correctos = 0
    n = len(EJEMPLOS_TEST)
    for i, ej in enumerate(EJEMPLOS_TEST, 1):
        logger.info(f"Ejemplo {i}/{n}: {ej['titulo'][:70]}...")
        res = llamar_ollama(
            construir_prompt(ej["titulo"], ej["resumen"], ej["keywords"]), modelo
        )
        if not res:
            logger.error("  ERROR: Sin respuesta.")
            continue
        dec, conf = res.get("decision", "?").upper(), int(res.get("confianza", 0))
        ok = dec == ej["esperado"]
        correctos += ok
        logger.info(f"  {'OK' if ok else 'FALLO'} | Esperada: {ej['esperado']} | "
                    f"Obtenida: {dec} | Conf: {conf}% (min: {ej['conf_min']}%)")
        logger.info(f"  {res.get('justificacion','')[:90]}")
    logger.info(f"Resultado: {correctos}/{n} | "
                f"{'APTO' if correctos >= n - 1 else 'MARGINAL'}")
    logger.info("=" * 68)


# ==============================================================================
# CLI
# ==============================================================================

def parsear_args():
    p = argparse.ArgumentParser(
        description="Filtrado Ollama RSL pH Industria Azucarera.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--input", "-i", default="output/3.filtrado_quartiles.ris",
                   help="RIS de entrada (salida del script 03).")
    p.add_argument("--output", "-o", default="output",
                   help="Carpeta de salida (Excel, RIS, log).")
    p.add_argument("--model", "-m", default=None,
                   help="Modelo Ollama a usar. Si no existe, cae a fallback automatico.")
    p.add_argument("--log-level", "-l", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                   help="Nivel de verbosidad.")
    p.add_argument("--test", action="store_true",
                   help="Calibracion con ejemplos five-shot (no procesa el RIS).")
    p.add_argument("--dry-run", action="store_true",
                   help="Solo filtro local L0/L1/L2 sin llamar a Ollama.")
    return p.parse_args()


# ==============================================================================
# PIPELINE PRINCIPAL
# ==============================================================================

def main():
    args = parsear_args()
    log_path = configurar_logging(args.output, args.log_level)

    excel_out = os.path.join(args.output, "4.filtrado_ollama.xlsx")
    ris_out   = os.path.join(args.output, "4.filtrado_ollama.ris")

    logger.info("=" * 68)
    logger.info("FILTRADO OLLAMA FIVE-SHOT — RSL pH INDUSTRIA AZUCARERA")
    logger.info(f"Objetivo: precision {PRECISION_OBJETIVO}  |  Sensibilidad: 100%")
    logger.info("=" * 68)
    logger.info(f"Input RIS    : {args.input}")
    logger.info(f"Output folder: {args.output}")
    logger.info(f"Log file     : {log_path}")
    logger.info(f"Dry-run      : {args.dry_run}")
    logger.info(f"Test mode    : {args.test}")

    modelo = detectar_modelo(args.model)
    logger.info(f"Modelo en uso: {modelo}")

    if args.test:
        modo_prueba(modelo)
        return

    try:
        df = leer_ris(args.input)
    except (FileNotFoundError, IsADirectoryError) as e:
        logger.error(str(e))
        logger.error("Ejecuta primero el script 03 o ajusta --input.")
        sys.exit(1)

    total = len(df)
    logger.info(f"Total articulos cargados: {total}")
    if total == 0:
        logger.warning("RIS de entrada vacio.")
        return

    col_ti = next((c for c in df.columns if c in ["TI", "Title"]),    None)
    col_ab = next((c for c in df.columns if c in ["AB", "Abstract"]), None)
    col_kw = next((c for c in df.columns if c in ["KW", "Keywords"]), None)
    col_n1 = next((c for c in df.columns if c in ["N1", "Notes"]),    None)

    if not col_ti or not col_ab:
        logger.error("No se encontraron columnas TI o AB en el RIS.")
        sys.exit(1)

    df["decision_ollama"]      = ""
    df["justificacion_ollama"] = ""
    df["confianza_ollama"]     = 0
    df["nivel_certeza"]        = ""

    cnt = {"incluir_auto": 0, "excluir_auto": 0,
           "revisar": 0, "incierto": 0, "local": 0, "errores": 0}

    for idx in range(total):
        row      = df.iloc[idx]
        titulo   = str(row.get(col_ti, "")).strip()
        resumen  = str(row.get(col_ab, "")).strip()
        keywords = str(row.get(col_kw, "")).strip() if col_kw else ""
        n1_orig  = str(row.get(col_n1, "")).strip() if col_n1 else ""
        texto    = f"{titulo} {resumen} {keywords}"

        pasa, motivo = contiene_palabras_clave(texto)

        if not pasa:
            decision, confianza, nivel = "EXCLUIR", 99, "LOCAL"
            justif = f"Filtro local: {motivo}"
            cnt["local"] += 1
            logger.info(f"[{idx+1}/{total}] EXCLUIR (LOCAL) | {titulo[:80]}")

        elif args.dry_run:
            decision, confianza, nivel = "DRY-RUN", 0, "LOCAL"
            justif = "Modo dry-run"
            logger.info(f"[{idx+1}/{total}] DRY-RUN | {titulo[:80]}")

        else:
            resultado = llamar_ollama(
                construir_prompt(titulo, resumen, keywords), modelo
            )

            if not resultado:
                decision, confianza, nivel = "EXCLUIR", 0, "INCIERTO"
                justif = "Error: sin respuesta del LLM"
                cnt["errores"] += 1
                logger.error(f"[{idx+1}/{total}] ERROR | {titulo[:80]}")
            else:
                decision  = resultado.get("decision", "EXCLUIR").upper()
                confianza = int(resultado.get("confianza", 0))
                justif    = resultado.get("justificacion", "")

                if confianza < CONFIDENCE_THRESHOLD_HUMAN:
                    logger.warning(f"  CONFIANZA MUY BAJA ({confianza}%) — forzado a EXCLUIR")
                    decision = "EXCLUIR"
                    nivel    = "INCIERTO"
                    cnt["incierto"] += 1
                elif confianza < CONFIDENCE_THRESHOLD_AUTO:
                    nivel = "REVISAR"
                    cnt["revisar"] += 1
                else:
                    nivel = "AUTO"
                    cnt["incluir_auto" if decision == "INCLUIR" else "excluir_auto"] += 1

                logger.info(
                    f"[{idx+1}/{total}] {decision} [{nivel}, conf={confianza}%] | "
                    f"{titulo[:80]}"
                )
                logger.debug(f"  Justif: {justif[:140]}")

            time.sleep(SLEEP_BETWEEN_CALLS)

        # Anotar N1
        anotacion = f"{OLLAMA_TAG}: {justif} [conf={confianza}%, nivel={nivel}]"
        n1_nuevo  = f"{n1_orig} | {anotacion}" if n1_orig else anotacion
        if col_n1:
            df.at[df.index[idx], col_n1] = n1_nuevo

        df.at[df.index[idx], "decision_ollama"]      = decision
        df.at[df.index[idx], "justificacion_ollama"] = justif
        df.at[df.index[idx], "confianza_ollama"]     = confianza
        df.at[df.index[idx], "nivel_certeza"]        = nivel

    logger.info(f"Excluidos por filtro local (sin LLM): {cnt['local']} / {total}")

    # ── Excel con 2 hojas ────────────────────────────────────────────────
    incluir_total  = cnt["incluir_auto"]
    excluir_total  = total - incluir_total
    revisar_total  = cnt["revisar"]
    incierto_total = cnt["incierto"]
    tasa           = round(incluir_total / total * 100, 1) if total > 0 else 0.0

    os.makedirs(args.output, exist_ok=True)
    with pd.ExcelWriter(excel_out, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Clasificacion", index=False)
        pd.DataFrame({
            "Metrica": [
                "Total procesados", "INCLUIR", "EXCLUIR", "ERROR",
                (f"INCLUIR para revision manual "
                 f"(confianza {CONFIDENCE_THRESHOLD_HUMAN}"
                 f"-{CONFIDENCE_THRESHOLD_AUTO - 1}%)"),
                f"INCIERTO (confianza < {CONFIDENCE_THRESHOLD_HUMAN}%)",
                "Tasa inclusion (%)", "Modelo", "Temperatura",
                "Umbral confianza auto (%)", "Umbral confianza revision (%)",
                "Protocolo", "Precision objetivo",
            ],
            "Valor": [
                total, incluir_total, excluir_total, cnt["errores"],
                revisar_total, incierto_total, tasa,
                modelo, TEMPERATURE,
                CONFIDENCE_THRESHOLD_AUTO, CONFIDENCE_THRESHOLD_HUMAN,
                PROTOCOLO, PRECISION_OBJETIVO,
            ],
        }).to_excel(writer, sheet_name="Metricas", index=False)
    logger.info(f"Excel exportado: {excel_out}")

    # ── RIS solo con INCLUIR AUTO ────────────────────────────────────────
    mask    = (df["decision_ollama"] == "INCLUIR") & (df["nivel_certeza"] == "AUTO")
    df_incl = df[mask].copy()
    if len(df_incl) > 0:
        escribir_ris(df_incl, ris_out)
        logger.info(f"RIS exportado: {ris_out} ({len(df_incl)} INCLUIR AUTO)")
    else:
        logger.warning("RIS no generado: sin articulos INCLUIR automaticos.")

    # ── Reporte final ────────────────────────────────────────────────────
    logger.info("=" * 68)
    logger.info("REPORTE FINAL")
    logger.info("=" * 68)
    logger.info(f"Total procesados        : {total}")
    logger.info(f"INCLUIDOS (automaticos) : {incluir_total}")
    logger.info(f"EXCLUIDOS               : {excluir_total}")
    logger.info(f"ERRORES                 : {cnt['errores']}")
    logger.info(f"A REVISAR MANUALMENTE   : {revisar_total}")
    logger.info(f"INCIERTOS (< {CONFIDENCE_THRESHOLD_HUMAN}% conf): {incierto_total}")
    logger.info(f"Tasa de inclusion       : {tasa} %")
    logger.info("=" * 68)
    logger.info("Pipeline completado.")


if __name__ == "__main__":
    main()