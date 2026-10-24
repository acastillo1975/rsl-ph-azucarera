"""
00_generar_queries.py
======================================
RSL: Aplicaciones de Aprendizaje Automatico para el Control de pH
     en la Industria del Azucar: Tendencias, Brechas y Direcciones Futuras
FILTRO Q1: Solo publicaciones en revistas de primer cuartil (Q1).

VERSION DEFINITIVA: 3 RQs <-> 3 Queries (1 a 1)
  RQ1: Modelado y caracterizacion dinamica del pH
  RQ2: Control avanzado (NMPC, Fuzzy, metaheuristicas) vs PID
  RQ3: ML/RL/hibridos y barreras de adopcion industrial

Uso:
  python 00_generar_queries.py
  python 00_generar_queries.py --output ..\00_query_design
  python 00_generar_queries.py -o ..\00_query_design -m llama3.1:8b -l DEBUG
  python 00_generar_queries.py -o ..\00_query_design --respaldo
"""

import json, os, re, sys, time, argparse, logging
from datetime import datetime
import ollama

TEMPERATURE    = 0.05
MAX_RETRIES    = 4
NUM_PREDICT    = 8000
BASES_DE_DATOS = ["Scopus", "WoS", "IEEE"]

MODELOS_PREFERIDOS = [
    "llama3","llama3:latest","llama3:8b","llama3.1","llama3.1:8b","llama3.1:latest",
    "llama3.2","llama3.2:3b","llama3.2:latest","mistral","mistral:latest","mistral:7b",
    "mixtral","gemma2","gemma2:9b","phi3","phi3:medium","qwen2","deepseek-r1",
]

logger = logging.getLogger("query_gen")


# ==============================================================================
# LOGGING
# ==============================================================================

def configurar_logging(output_folder: str, log_level: str) -> str:
    os.makedirs(output_folder, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(output_folder, f"query_gen_{timestamp}.log")

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
# CONFIGURACION Q1
# ==============================================================================

Q1_CONFIG = {
    "scopus_suffix": "AND SRCTYPE(j) AND DOCTYPE(ar OR re) AND PUBYEAR > 2014",
    "wos_suffix":    "AND DT=(Article OR Review) AND PY=(2015-2026)",
    "ieee_suffix":   "",
    "scopus_q1_steps": (
        "PASO Q1 -- Scopus (post-busqueda):\n"
        "  1. La query ya incluye SRCTYPE(j) + DOCTYPE(ar OR re) + PUBYEAR > 2014.\n"
        "  2. Resultados -> 'Analyze search results' -> 'Source' -> revistas de interes.\n"
        "  3. Para Q1 exacto: cruzar fuentes con Scimago (sjr.scimagojr.com)\n"
        "     filtrando Quartile = Q1 en 'Chemical Engineering' o 'Food Science'.\n"
        "  4. Opcional: re-ejecutar con EXACTSRCTITLE() listando revistas Q1 confirmadas."
    ),
    "wos_q1_steps": (
        "PASO Q1 -- Web of Science (post-busqueda):\n"
        "  1. La query ya incluye DT=(Article OR Review) + PY=(2015-2026).\n"
        "  2. Resultados -> panel 'Refine Results' -> 'Journal Impact Factor Quartile' -> Q1.\n"
        "  3. Opcional: agregar SO=(lista de revistas Q1) directamente a la query."
    ),
    "ieee_q1_steps": (
        "PASO Q1 -- IEEE Xplore (post-busqueda):\n"
        "  1. Resultados -> 'Refine Results' -> 'Publication Type' -> 'Journals'.\n"
        "  2. Revistas IEEE relevantes Q1: IEEE Trans. Industrial Electronics,\n"
        "     IEEE Trans. Control Systems Technology, IEEE Trans. Industrial Informatics.\n"
        "  3. Tras exportar: cruzar ISSNs con JCR/Scimago para confirmar Q1 por anio."
    ),
    "revistas_q1_sugeridas": [
        "Computers and Chemical Engineering",
        "Journal of Food Engineering",
        "Control Engineering Practice",
        "Journal of Process Control",
        "Biosystems Engineering",
        "Food and Bioproducts Processing",
        "Industrial and Engineering Chemistry Research",
        "Applied Soft Computing",
        "Expert Systems with Applications",
        "Engineering Applications of Artificial Intelligence",
        "ISA Transactions",
        "Measurement",
        "Sensors",
        "IEEE Transactions on Industrial Electronics",
        "IEEE Transactions on Control Systems Technology",
        "IEEE Transactions on Industrial Informatics",
    ],
}


# ==============================================================================
# CONTEXTO DE LA RSL - 3 RQs <-> 3 QUERIES
# ==============================================================================

CONTEXTO_RSL = {
    "titulo_paper": (
        "Una Revision Sistematica de las Aplicaciones de Aprendizaje Automatico y Control Avanzado "
        "para el Modelado y Optimizacion del Control de pH en la Industria del Azucar: "
        "Tendencias, Brechas y Direcciones Futuras"
    ),
    "preguntas_investigacion": [
        "RQ1: Que tecnicas de modelado (data-driven, mecanisticas o hibridas) y que variables operacionales "
        "(flujo de cal, temperatura, flujo de jugo) se han utilizado para caracterizar la dinamica del pH "
        "en la clarificacion del jugo de cana y remolacha?",

        "RQ2: Que estrategias de control avanzado (NMPC, Logica Difusa, Optimizacion por Metaheuristicas) "
        "se han aplicado para regular el pH en el encalado, y como se desempenan en robustez y error en "
        "estado estacionario frente a metodos convencionales (PID)?",

        "RQ3: Que tecnicas emergentes de Machine Learning, Aprendizaje por Refuerzo y enfoques hibridos "
        "se estan explorando para el control de pH en la industria azucarera, y cuales son las principales "
        "barreras (falta de datos, coste computacional, desajuste modelo-planta) que limitan su adopcion industrial?",
    ],
    "dominio_principal": "Control de pH en clarificacion de jugo de cana/remolacha",

    "procesos_incluir": [
        "sugarcane juice clarification", "cane juice clarification", "sugar juice alkalinization",
        "sugar juice liming", "defecation process", "carbonatation", "sulfitation",
        "lime dosage", "lime addition", "milk of lime", "calcium hydroxide",
        "mixed juice", "clarified juice", "raw juice", "sugar syrup",
        "sugar mill", "sugar factory", "sugar industry", "sugarcane processing",
        "sugar beet", "beet sugar", "saccharum officinarum",
        "juice acidity", "alkalinity control", "ph setpoint",
    ],

    # Tecnicas agrupadas para que casen con las 3 RQs:
    #   Grupo RQ1 (Modelado)         -> identification, soft sensor, virtual sensor, data-driven
    #   Grupo RQ2 (Control avanzado) -> MPC, NMPC, fuzzy, takagi-sugeno, pattern search, PSO, GA, PID tuning
    #   Grupo RQ3 (ML/Hibrido)       -> ML, NN, DL, RF, SVM, XGBoost, LSTM, RL
    "tecnicas_incluir": {
        "grupo_modelado": ["identification", "soft sensor", "virtual sensor", "data-driven model", "LSTM", "neural network"],
        "grupo_control": ["model predictive control", "NMPC", "fuzzy logic", "takagi-sugeno", "pattern search", "particle swarm", "genetic algorithm", "PID tuning"],
        "grupo_ml": ["machine learning", "deep learning", "random forest", "XGBoost", "reinforcement learning", "ensemble"]
    },

    "exclusiones_explicitas": [
        "wastewater", "effluent", "cooling tower", "desulfurization", "flue gas",
        "bioreactor", "fermentation broth", "bioethanol", "biogas",
        "pharmaceutical", "blood", "soil", "groundwater", "drinking water",
        "wine", "beer", "dairy", "milk", "fruit juice", "olive oil",
        "electroplating", "pickling", "hydrometallurgy", "leaching",
    ],

    "periodo": "2015-2026",
    "num_queries": 3,
    "precision_objetivo": "> 85% | Foco: Clarificacion de jugo de cana/remolacha | Q1 journals",
    "terminos_adicionales_notebooklm": [],
}


# ==============================================================================
# SINTAXIS POR BASE
# ==============================================================================

SINTAXIS_INFO = {
    "Scopus": {
        "nombre_completo": "Scopus (Elsevier)",
        "operador_campo": "TITLE-ABS-KEY + SRCTYPE(j) + DOCTYPE(ar OR re) + PUBYEAR",
        "url_busqueda": "https://www.scopus.com/search/form.uri#advanced",
        "url_sjr": "https://www.scimagojr.com/journalrank.php",
        "formato_ejemplo": (
            'TITLE-ABS-KEY(\n'
            '  ("pH control" OR "acidity control" OR "lime dosage")\n'
            '  AND ("sugar mill" OR "sugarcane" OR "sugar beet")\n'
            '  AND ("machine learning" OR "neural network")\n'
            ')\n'
            'AND NOT TITLE-ABS-KEY("wastewater" OR "fermentation broth")\n'
            'AND SRCTYPE(j) AND DOCTYPE(ar OR re) AND PUBYEAR > 2014'
        ),
        "notas": [
            "TITLE-ABS-KEY busca en titulo, abstract y keywords simultaneamente.",
            "Frases multipalabra DEBEN ir entre comillas dobles.",
            "ESTRUCTURA PLANA obligatoria: NO anidar AND dentro de parentesis OR.",
            "  CORRECTO: AND \"pH\" AND (\"sugar mill\" OR \"sugarcane\" OR ...)",
            "  INCORRECTO: AND (\"pH\" AND (\"sugar mill\" OR \"sugarcane\" OR ...))",
            "SRCTYPE(j)         -> solo revistas (excluye conferencias, libros).",
            "DOCTYPE(ar OR re)  -> solo articulos y revisiones.",
            "PUBYEAR > 2014     -> publicaciones 2015 en adelante.",
            "Filtro Q1 post-busqueda: Analyze Results > Source > cruzar con SJR.",
            "Limite: 2,000 registros por exportacion.",
        ],
        "instrucciones_export": (
            "Scopus -> Advanced Search -> pegar query -> Search\n"
            "-> FILTRO Q1: Analyze Results > Source > cruzar fuentes con Scimago Q1\n"
            "-> Seleccionar todos -> Export -> RIS -> incluir todos los campos\n"
            "-> Guardar como scopus_export_N.ris en 01_raw_data/"
        ),
    },
    "WoS": {
        "nombre_completo": "Web of Science (Clarivate)",
        "operador_campo": "TS= + DT=(Article OR Review) + PY=(2015-2026)",
        "url_busqueda": "https://www.webofscience.com/wos/woscc/advanced-search",
        "url_jcr": "https://jcr.clarivate.com/",
        "formato_ejemplo": (
            'TS=(\n'
            '  ("pH control" OR "acidity control" OR "lime dosage")\n'
            '  AND ("sugar mill" OR "sugarcane" OR "sugar beet")\n'
            '  AND ("machine learning" OR "neural network")\n'
            ')\n'
            'NOT TS=("wastewater" OR "fermentation broth")\n'
            'AND DT=(Article OR Review) AND PY=(2015-2026)'
        ),
        "notas": [
            "TS= busca en Topic (titulo + abstract + keywords + keywords plus).",
            "NO usar TITLE-ABS-KEY (sintaxis de Scopus).",
            "ESTRUCTURA PLANA: \"pH\" como termino independiente, no anidado.",
            "DT=(Article OR Review) -> articulos de revista y revisiones solamente.",
            "PY=(2015-2026)         -> rango de anos.",
            "Filtro Q1 post-busqueda: Refine Results > JIF Quartile > Q1.",
            "Wildcards: sugar* cubre sugarcane, sugar mill, sugar beet, sugar factory.",
            "Limite: 1,000 registros por descarga directa.",
        ],
        "instrucciones_export": (
            "WoS -> Advanced Search -> pegar query -> Search\n"
            "-> FILTRO Q1: Refine Results > Journal Impact Factor Quartile > Q1\n"
            "-> Export -> BibTeX -> All Records (lotes de 1000)\n"
            "-> Abrir en Zotero -> Export Collection -> RIS\n"
            "-> Guardar como wos_export_N.ris en 01_raw_data/"
        ),
    },
    "IEEE": {
        "nombre_completo": "IEEE Xplore Digital Library",
        "operador_campo": "(sin operador de campo) + filtro Publication Type en interfaz",
        "url_busqueda": "https://ieeexplore.ieee.org/search/advanced",
        "formato_ejemplo": (
            '("pH control" OR "acidity control" OR "lime dosage")\n'
            'AND ("sugar mill" OR "sugarcane" OR "sugar beet")\n'
            'AND ("machine learning" OR "neural network")\n'
            'NOT ("wastewater" OR "fermentation broth")\n'
            '-- FILTRO Q1: Refine Results > Publication Type > Journals'
        ),
        "notas": [
            "IEEE usa busqueda en All Metadata (titulo + abstract + keywords).",
            "NO usa TITLE-ABS-KEY ni TS= -- operadores van directamente.",
            "Wildcards * NO funcionan en IEEE -- usar OR explicito.",
            "FILTRO Q1: Refine Results > Publication Type > Journals.",
            "Revistas IEEE Q1 relevantes: IEEE Trans. Industrial Electronics,",
            "  IEEE Trans. Control Systems Technology, IEEE Trans. Industrial Informatics.",
            "Tras exportar: cruzar ISSNs con JCR/Scimago para confirmar Q1 por anio.",
            "Limite: 2,000 registros.",
        ],
        "instrucciones_export": (
            "IEEE Xplore -> Advanced Search -> pegar query -> Search\n"
            "-> FILTRO Q1: Refine Results > Publication Type > Journals\n"
            "-> Select All -> Export -> RIS (EndNote) -> incluir Abstract\n"
            "-> Guardar como ieee_export_N.ris en 01_raw_data/"
        ),
    },
}


# ==============================================================================
# HELPER: aplicar sufijo Q1
# ==============================================================================

def aplicar_filtro_q1(query_texto: str, base: str) -> str:
    sufijo = {"Scopus": Q1_CONFIG["scopus_suffix"],
              "WoS":    Q1_CONFIG["wos_suffix"],
              "IEEE":   Q1_CONFIG["ieee_suffix"]}.get(base, "")
    if sufijo and sufijo not in query_texto:
        return query_texto.rstrip() + "\n" + sufijo
    return query_texto


# ==============================================================================
# PROMPT PARA OLLAMA
# ==============================================================================

def construir_prompt_triple(ctx: dict) -> str:
    return f"""You are a senior bibliometric search specialist for systematic literature reviews (SLR).
Generate 3 Boolean search queries for Scopus, WoS and IEEE for an SLR focused EXCLUSIVELY on the SUGAR INDUSTRY.
RESTRICTION: Only Q1 journal publications. The sugar domain anchor is MANDATORY in ALL queries.

THEMATIC COHERENCE: 1 query maps to 1 RQ. Sugar domain anchor identical across databases. Only SYNTAX differs.

RSL TOPIC: {ctx["titulo_paper"]}
PERIOD: {ctx["periodo"]}
PRECISION TARGET: {ctx["precision_objetivo"]}

RESEARCH QUESTIONS:
{chr(10).join("- " + rq for rq in ctx["preguntas_investigacion"])}

**MANDATORY SUGAR DOMAIN ANCHOR (MUST appear in ALL queries):**
("sugarcane juice" OR "cane juice" OR "sugar juice" OR "juice clarification" 
 OR "liming process" OR "alkalinization" OR "defecation" OR "milk of lime" 
 OR "sugar mill" OR "sugar factory" OR "sugar beet" OR "beet sugar")

MODELING & CONTROL TECHNIQUES (use combinations of these across the 3 angles):
{", ".join(ctx["tecnicas_incluir"])}

MANDATORY EXCLUSIONS (avoid these domains):
{", ".join(ctx["exclusiones_explicitas"])}

==============================
THEMATIC ANGLES (3 queries, SHARED anchor, 1-to-1 with RQs):
==============================

Q1 -> RQ1 -- MODELING & SOFT SENSORS:
  Combine sugar anchor + pH terms + ("soft sensor" OR "virtual sensor" OR "identification" OR "neural network" OR "LSTM" OR "data-driven")
  DO NOT force generic ML if fuzzy/MPC is the primary topic.

Q2 -> RQ2 -- ADVANCED CONTROL & OPTIMIZATION vs PID:
  **CRITICAL: DO NOT INCLUDE "machine learning" OR "artificial intelligence" IN THIS QUERY.**
  Use ONLY these terms: ("NMPC" OR "model predictive control" OR "fuzzy logic" OR "takagi-sugeno" OR "optimization" OR "pattern search" OR "genetic algorithm" OR "particle swarm" OR "PID tuning")
  This query MUST capture papers that use fuzzy control, NMPC, metaheuristics, without requiring ML keywords.

Q3 -> RQ3 -- ML, RL, HYBRID AI & ADOPTION BARRIERS:
  Combine sugar anchor + pH terms + ("machine learning" OR "random forest" OR "XGBoost" OR "reinforcement learning" OR "deep learning" OR "ensemble" OR "hybrid model")


CRITICAL INSTRUCTIONS (STRICT):
1. The Sugar Anchor MUST be the FIRST block.
2. FLAT AND structure: NEVER nest AND inside parentheses.
3. Do NOT use wastewater or cooling tower terms as main topics.
4. Scopus suffix: AND SRCTYPE(j) AND DOCTYPE(ar OR re) AND PUBYEAR > 2014.
5. WoS suffix: AND DT=(Article OR Review) AND PY=(2015-2026).
6. IEEE: No suffix, filter by Journals manually later.
7. **ABSOLUTELY FORBIDDEN**: You MUST NOT use "..." , "[...]" , "etc." or any ellipsis/placeholder in the query strings. You MUST write the ENTIRE Boolean query character by character.
8. You MUST write the complete query for ALL 3 queries (1, 2, and 3) for EACH database (Scopus, WoS, IEEE). Do not skip any.
9. The content must be identical across databases; only change TITLE-ABS-KEY to TS= and remove operators for IEEE.

Respond ONLY with valid JSON. No markdown.


JSON STRUCTURE:
{{
  "thematic_angles": [
    {{"angle": 1, "topic_es": "Modelado y sensores virtuales para pH en clarificacion", "focus": "Soft sensors, identification, LSTM, data-driven", "rq_cubierta": "RQ1"}},
    {{"angle": 2, "topic_es": "Control avanzado: NMPC, logica difusa, optimizacion (vs PID)", "focus": "NMPC, Fuzzy, Pattern Search, PSO, GA, PID tuning", "rq_cubierta": "RQ2"}},
    {{"angle": 3, "topic_es": "ML, RL y enfoques hibridos; barreras de adopcion", "focus": "ML, RL, Deep Learning, hybrid, adoption barriers", "rq_cubierta": "RQ3"}}
  ],
  "scopus": {{
    "queries": [
      {{"numero": 1, "query": "TITLE-ABS-KEY((sugar anchor) AND (pH terms) AND (soft sensor/identification terms)) AND NOT TITLE-ABS-KEY(exclusions) AND SRCTYPE(j) AND DOCTYPE(ar OR re) AND PUBYEAR > 2014", "especificidad": "alta", "terminos_clave": ["soft sensor","identification","neural network"], "descripcion_tematica": "...", "justificacion": "..."}},
      {{"numero": 2, "query": "TITLE-ABS-KEY((sugar anchor) AND (pH terms) AND (NMPC/fuzzy/optimization terms)) AND NOT TITLE-ABS-KEY(exclusions) AND SRCTYPE(j) AND DOCTYPE(ar OR re) AND PUBYEAR > 2014", "especificidad": "alta", "terminos_clave": ["NMPC","fuzzy","pattern search"], "descripcion_tematica": "...", "justificacion": "..."}},
      {{"numero": 3, "query": "TITLE-ABS-KEY((sugar anchor) AND (pH terms) AND (ML/hybrid terms)) AND NOT TITLE-ABS-KEY(exclusions) AND SRCTYPE(j) AND DOCTYPE(ar OR re) AND PUBYEAR > 2014", "especificidad": "alta", "terminos_clave": ["machine learning","reinforcement learning","deep learning"], "descripcion_tematica": "...", "justificacion": "..."}}
    ]
  }},
  "wos": {{
    "queries": [
      {{"numero": 1, "query": "TS=((sugar anchor) AND (pH terms) AND (soft sensor/identification terms)) NOT TS=(exclusions) AND DT=(Article OR Review) AND PY=(2015-2026)", ...}},
      ...
    ]
  }},
  "ieee": {{
    "queries": [
      {{"numero": 1, "query": "((sugar anchor) AND (pH terms) AND (soft sensor/identification terms)) NOT (exclusions)", ...}},
      ...
    ]
  }},
  "estrategia_global": "...",
  "advertencias": ["Asegurar que el ancla de azucar sea el termino mas restrictivo."],
  "precision_estimada": {{"scopus": "85-90%", "wos": "82-87%", "ieee": "80-85%", "justificacion": "Uso de ancla de proceso obligatoria + exclusiones agresivas."}}
}}"""


# ==============================================================================
# VERIFICACION OLLAMA
# ==============================================================================

def verificar_ollama() -> str | bool:
    try:
        lista_resp = ollama.list()
        if hasattr(lista_resp, "models"): raw = lista_resp.models
        elif isinstance(lista_resp, dict): raw = lista_resp.get("models", [])
        else: raw = list(lista_resp)
        nombres = []
        for m in raw:
            if hasattr(m, "model"): nombres.append(m.model)
            elif hasattr(m, "name"): nombres.append(m.name)
            elif isinstance(m, dict): nombres.append(m.get("model", m.get("name", "")))
        nombres = [n for n in nombres if n]
        if not nombres:
            logger.error("Sin modelos. Ejecuta: ollama pull llama3.2")
            return False
        logger.info(f"Modelos disponibles: {', '.join(nombres)}")
        for pref in MODELOS_PREFERIDOS:
            base_pref = pref.split(":")[0].lower()
            for disp in nombres:
                if disp == pref or disp.split(":")[0].lower() == base_pref:
                    logger.info(f"Modelo seleccionado: {disp}")
                    return disp
        logger.info(f"Fallback: {nombres[0]}")
        return nombres[0]
    except Exception as e:
        logger.error(f"Ollama: {e}. Ejecuta: ollama serve")
        return False


# ==============================================================================
# LLAMADA OLLAMA
# ==============================================================================

def llamar_ollama(prompt: str, modelo: str) -> str:
    temp = TEMPERATURE
    for i in range(1, MAX_RETRIES + 1):
        try:
            logger.info(f"Intento {i}/{MAX_RETRIES} (temp={temp:.2f})...")
            t0 = time.time()
            resp = ollama.chat(
                model=modelo,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": temp, "num_predict": NUM_PREDICT,
                         "top_p": 0.9, "repeat_penalty": 1.1},
            )
            texto = resp.message.content if hasattr(resp, "message") else resp["message"]["content"]
            logger.info(f"OK  {time.time()-t0:.1f}s  ({len(texto):,} chars)")
            return texto
        except Exception as e:
            logger.error(f"Error Ollama intento {i}: {e}")
            temp = max(0.0, temp - 0.02)
            if i < MAX_RETRIES:
                time.sleep(2 * i)
    return ""


# ==============================================================================
# PARSEO JSON
# ==============================================================================

def parsear_json(texto: str) -> dict | None:
    estrategias = [
        lambda t: json.loads(t.strip()),
        lambda t: json.loads(re.sub(r"```(?:json)?\s*|\s*```", "", t).strip()),
        lambda t: json.loads(re.search(r"\{[\s\S]*\}", t).group()),
        lambda t: json.loads(re.search(r"\{[\s\S]*\}\s*$", t).group()),
        lambda t: json.loads(t.replace("\u201c",'"').replace("\u201d",'"')
                              .replace("\u2018",'"').replace("\u2019",'"').strip()),
        lambda t: json.loads(_reparar_json_truncado(t)),
    ]
    for i, fn in enumerate(estrategias, 1):
        try:
            r = fn(texto)
            if i > 1:
                logger.info(f"JSON parseado con estrategia {i}/6")
            return r
        except Exception:
            continue
    return None


def _reparar_json_truncado(texto: str) -> str:
    m = re.search(r"\{", texto)
    if not m: return texto
    frag = texto[m.start():]
    stack, en_str, esc = [], False, False
    for ch in frag:
        if esc: esc = False; continue
        if ch == "\\" and en_str: esc = True; continue
        if ch == '"' and not esc: en_str = not en_str; continue
        if en_str: continue
        if ch in "{[": stack.append(ch)
        elif ch in "]}":
            if stack: stack.pop()
    return frag + "".join("}" if a=="{" else "]" for a in reversed(stack))


# ==============================================================================
# CORRECCION DE SINTAXIS
# ==============================================================================

FRASES_DOMINIO = [
    # pH
    "pH control","pH monitoring","pH prediction","pH optimization","pH measurement",
    "pH adjustment","pH correction","pH regulation","pH sensor","pH probe","pH setpoint",
    "juice pH","online pH measurement","real-time pH control","automatic pH control",
    "lime addition control","DCS pH","SCADA pH",
    # Sinonimos pH
    "acidity control","alkalinity control","juice acidity","acidity measurement",
    "acid-base control","lime dosage","lime addition","calcium hydroxide","milk of lime",
    "liming control","defecation control",
    # Azucar
    "sugar mill","sugar industry","sugar factory","sugarcane processing",
    "sugarcane juice","cane juice","raw juice","mixed juice","clarified juice",
    "juice clarification","cane juice clarification","sugar clarification",
    "liming process","defecation","sulfitation","carbonatation",
    "juice purification","mud separation","sugar beet","beet sugar",
    "sugar beet factory","saccharum",
    # ML/IA
    "machine learning","deep learning","neural network","artificial neural network",
    "random forest","gradient boosting","support vector machine","support vector regression",
    "decision tree","ensemble learning","regression model",
    "long short-term memory","convolutional neural network",
    "recurrent neural network","attention mechanism",
    "model predictive control","reinforcement learning","deep reinforcement learning",
    "digital twin","physics-informed neural network",
    "soft sensor","virtual sensor","inferential sensor",
    "online estimation","real-time estimation",
    "genetic algorithm","particle swarm optimization",
    "fuzzy logic","neuro-fuzzy","Gaussian process",
    "data-driven","predictive model","process optimization",
    "adaptive control","intelligent control","PID tuning","optimal control",
    "transfer learning","online learning",
    # Exclusiones
    "wastewater pH","water treatment pH","soil pH","blood pH","pharmaceutical pH",
    "drug pH","physiological pH","wine pH","beer pH","dairy pH","milk pH",
    "bioreactor pH","fermentation broth","anaerobic digestion pH","biogas pH",
]

Q1_TOKENS = [
    "SRCTYPE(j)","DOCTYPE(ar OR re)","PUBYEAR > 2014",
    "DT=(Article OR Review)","PY=(2015-2026)",
]


def _detectar_and_anidado(query_texto: str) -> list[str]:
    """Detecta patrones AND anidados dentro de parentesis que causan 0 resultados."""
    patron = re.compile(r'\(\s*"[^"]+"\s+AND\s+\(', re.IGNORECASE)
    return patron.findall(query_texto)


def _aplanar_and_anidado(query_texto: str) -> tuple[str, bool]:
    """
    Intenta corregir AND anidado: ("pH" AND ("sugar" OR ...))
    -> "pH" AND ("sugar" OR ...)
    """
    patron = re.compile(r'\(\s*("pH")\s+AND\s+(\([^)]+\))\s*\)', re.IGNORECASE)
    corregido = patron.sub(r'\1 AND \2', query_texto)
    fue_corregido = corregido != query_texto
    return corregido, fue_corregido


def corregir_query(query_texto: str, base: str) -> tuple[str, list[str]]:
    correcciones, corregido = [], query_texto

    # Proteger tokens Q1
    marcadores = {}
    for i, tok in enumerate(Q1_TOKENS):
        marca = f"__Q1T{i}__"
        if tok in corregido:
            corregido = corregido.replace(tok, marca)
            marcadores[marca] = tok

    # Comillas simples
    if "'" in corregido:
        corregido = corregido.replace("'", '"')
        correcciones.append("comillas simples -> dobles")

    # Comillas tipograficas
    for tip, rec in [("\u201c",'"'),("\u201d",'"'),("\u2018",'"'),("\u2019",'"')]:
        if tip in corregido:
            corregido = corregido.replace(tip, rec)
            correcciones.append("comilla tipografica -> doble recta")

    # Entrecomillar frases de dominio sin comillas
    if base in ("Scopus", "WoS"):
        for frase in sorted(FRASES_DOMINIO, key=len, reverse=True):
            patron = r'(?<!["\w])(' + re.escape(frase) + r')(?![\w"])'
            if re.search(patron, corregido, re.IGNORECASE):
                corregido = re.sub(patron, lambda m: f'"{m.group(1)}"',
                                   corregido, flags=re.IGNORECASE)
                correcciones.append(f'comillas: "{frase}"')

    # Remover operadores de campo en IEEE
    if base == "IEEE":
        if "TITLE-ABS-KEY" in corregido or "TS=" in corregido:
            corregido = corregido.replace("TITLE-ABS-KEY(","(").replace("TS=(","(")
            correcciones.append("TITLE-ABS-KEY/TS= removido para IEEE")

    # Detectar y corregir AND anidado
    anidados = _detectar_and_anidado(corregido)
    if anidados:
        corregido_flat, fue_corregido = _aplanar_and_anidado(corregido)
        if fue_corregido:
            corregido = corregido_flat
            correcciones.append("AND anidado aplanado automaticamente")
        else:
            correcciones.append(f"ADVERTENCIA: AND anidado detectado (correccion manual requerida): {anidados}")

    # Restaurar tokens Q1
    for marca, tok in marcadores.items():
        corregido = corregido.replace(marca, tok)

    # Asegurar sufijo Q1
    corregido = aplicar_filtro_q1(corregido, base)

    return corregido, correcciones


def corregir_comillas(resultado: dict, base: str) -> dict:
    base_key = base.lower()
    if base_key not in resultado: return resultado
    for q in resultado[base_key].get("queries", []):
        for clave in ("query","query_text","boolean_query","search_query"):
            if clave in q and q[clave]:
                corregido, corrs = corregir_query(q[clave], base)
                q[clave] = corregido
                if corrs: q["correcciones_aplicadas"] = corrs
                break
    return resultado


# ==============================================================================
# VALIDACION DE SINTAXIS
# ==============================================================================

def validar_sintaxis(query_texto: str, base: str) -> tuple[bool, list[str]]:
    if not query_texto or not query_texto.strip(): return False, ["Query vacia"]
    errores = []

    if "'" in query_texto:
        errores.append("Comillas simples -- usar dobles")

    # Parentesis sin contar tokens Q1
    q_clean = query_texto
    for t in Q1_TOKENS: q_clean = q_clean.replace(t, "")
    if q_clean.count("(") != q_clean.count(")"):
        errores.append(f"Parentesis desbalanceados: {q_clean.count('(')} vs {q_clean.count(')')}")

    if " AND " not in query_texto.upper() and " OR " not in query_texto.upper():
        errores.append("Sin operadores AND/OR")
    if " NOT " not in query_texto.upper() and "AND NOT" not in query_texto.upper():
        errores.append("Sin clausula NOT -- precision < 80%")

    # AND anidado
    anidados = _detectar_and_anidado(query_texto)
    if anidados:
        errores.append(f"AND anidado en parentesis (causa 0 resultados): {anidados}")

    # Validaciones por base
    if base == "Scopus":
        if "TITLE-ABS-KEY" not in query_texto:
            errores.append("Falta TITLE-ABS-KEY")
        if "TS=" in query_texto:
            errores.append("Contiene TS= (sintaxis WoS)")
        if "SRCTYPE(j)" not in query_texto:
            errores.append("Q1: falta SRCTYPE(j)")
        if "DOCTYPE(ar OR re)" not in query_texto:
            errores.append("Q1: falta DOCTYPE(ar OR re)")
        if "PUBYEAR > 2014" not in query_texto:
            errores.append("Q1: falta PUBYEAR > 2014")
    elif base == "WoS":
        if "TS=" not in query_texto:
            errores.append("Falta TS=")
        if "TITLE-ABS-KEY" in query_texto:
            errores.append("Contiene TITLE-ABS-KEY (sintaxis Scopus)")
        if "DT=(Article OR Review)" not in query_texto:
            errores.append("Q1: falta DT=(Article OR Review)")
        if "PY=(2015-2026)" not in query_texto:
            errores.append("Q1: falta PY=(2015-2026)")
    elif base == "IEEE":
        if "TITLE-ABS-KEY" in query_texto:
            errores.append("Contiene TITLE-ABS-KEY")
        if "TS=" in query_texto:
            errores.append("Contiene TS=")
        if re.search(r'\w\*', query_texto):
            errores.append("Wildcard * no soportado en IEEE")

    # Terminos obligatorios
    if "ph" not in query_texto.lower():
        if not any(t in query_texto.lower() for t in ["acidity","alkalinity","lime dosage","lime addition"]):
            errores.append("Sin terminos de pH ni sinonimos")
    if not any(t in query_texto.lower() for t in
               ["sugar","cane","sucrose","clarif","juice","liming","beet"]):
        errores.append("Sin terminos del dominio azucarero")
    if not any(t in query_texto.lower() for t in
               ["machine learning","neural network","deep learning","artificial intelligence",
                "reinforcement","soft sensor","virtual sensor","model predictive",
                "fuzzy","lstm","random forest","gradient boosting","data-driven"]):
        errores.append("Sin terminos de ML/IA")

    return len(errores) == 0, errores


# ==============================================================================
# EXPORTACION
# ==============================================================================

CLAVES_QUERY = ["query","query_text","boolean_query","search_query",
                "query_string","search_string","boolean_string"]


def exportar_todo(resultado: dict, modelo: str, output_folder: str) -> list[dict]:
    resultados_export = []
    for base in BASES_DE_DATOS:
        base_key  = base.lower()
        base_data = resultado.get(base_key, {})
        if not base_data:
            logger.warning(f"[{base}] Sin datos")
            resultados_export.append({"base": base, "validas": False, "txt": None})
            continue
        info = SINTAXIS_INFO[base]
        resultado = corregir_comillas(resultado, base)
        base_data = resultado.get(base_key, {})
        logger.info(f"[{base}] Exportando...")

        txt_path  = os.path.join(output_folder, f"queries_{base_key}.txt")
        json_path = os.path.join(output_folder, f"queries_{base_key}.json")

        lineas = [
            "=" * 72,
            f"QUERIES PARA: {info['nombre_completo']}  [v2 -- Q1 journals]",
            f"RSL  : {CONTEXTO_RSL['titulo_paper']}",
            f"Modelo: Ollama / {modelo}  |  Periodo: {CONTEXTO_RSL['periodo']}",
            f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"Precision objetivo: {CONTEXTO_RSL['precision_objetivo']}",
            "=" * 72, "",
            "*** FILTRO Q1 -- PUBLICACIONES DE PRIMER CUARTIL ***",
        ]

        if base == "Scopus":
            lineas.extend([Q1_CONFIG["scopus_q1_steps"], "",
                           "Revistas Q1 sugeridas:",
                           *[f"  - {r}" for r in Q1_CONFIG["revistas_q1_sugeridas"]], ""])
        elif base == "WoS":
            lineas.extend([Q1_CONFIG["wos_q1_steps"], "",
                           "Revistas Q1 sugeridas:",
                           *[f"  - {r}" for r in Q1_CONFIG["revistas_q1_sugeridas"]], ""])
        elif base == "IEEE":
            lineas.extend([Q1_CONFIG["ieee_q1_steps"], ""])

        lineas.extend([
            "=" * 72, "",
            "MAPEO 1-a-1 QUERY <-> RQ:",
            "  Q1 -> RQ1: Modelado y caracterizacion dinamica del pH",
            "  Q2 -> RQ2: Control avanzado (NMPC/Fuzzy/metaheuristicas) vs PID",
            "  Q3 -> RQ3: ML/RL/hibridos y barreras de adopcion",
            "",
            f"URL de busqueda: {info['url_busqueda']}",
            f"Operador de campo: {info['operador_campo']}", "",
            "NOTAS DE SINTAXIS:",
            *[f"  - {n}" for n in info["notas"]], "",
            "EJEMPLO DE FORMATO:",
            f"  {info['formato_ejemplo']}", "",
            "INSTRUCCIONES PARA EXPORTAR A RIS:",
            info["instrucciones_export"], "",
            "=" * 72, "",
        ])

        todas_validas = True
        for q_data in base_data.get("queries", []):
            num   = q_data.get("numero", "?")
            desc  = q_data.get("descripcion_tematica", "")
            terms = q_data.get("terminos_clave", [])
            just  = q_data.get("justificacion", "")
            espec = q_data.get("especificidad", "")
            corrs = q_data.get("correcciones_aplicadas", [])

            query_texto = ""
            for clave in CLAVES_QUERY:
                if clave in q_data and q_data[clave]:
                    query_texto = str(q_data[clave]); break

            query_texto = aplicar_filtro_q1(query_texto, base)
            valida, errores = validar_sintaxis(query_texto, base)
            if not valida: todas_validas = False
            estado = "VALIDA (Q1 v2)" if valida else f"REVISAR: {'; '.join(errores)}"

            lineas.extend([
                f"--- QUERY {num}: {desc} ---",
                f"Especificidad  : {espec} | Q1 journals",
                f"Terminos clave : {', '.join(terms)}",
                f"Justificacion  : {just}",
                f"Estado sintaxis: {estado}",
            ])
            if corrs: lineas.append(f"Correcciones   : {'; '.join(corrs)}")
            lineas.extend(["", "TEXTO PARA PEGAR EN LA INTERFAZ DE BUSQUEDA:",
                           "-"*40, query_texto, "-"*40, "", "="*72, ""])

        lineas.extend([
            "ESTRATEGIA GLOBAL:", resultado.get("estrategia_global",""), "",
            "ADVERTENCIAS / POSIBLES RUIDOS:",
            *[f"  - {a}" for a in resultado.get("advertencias",[])], "",
        ])
        prec = resultado.get("precision_estimada", {})
        if prec:
            lineas.extend([
                "PRECISION ESTIMADA (Q1 journals):",
                f"  Scopus : {prec.get('scopus','N/A')}",
                f"  WoS    : {prec.get('wos','N/A')}",
                f"  IEEE   : {prec.get('ieee','N/A')}",
                f"  Justif.: {prec.get('justificacion','')}","",
            ])
        lineas.extend([
            "RESULTADOS ESPERADOS (tema nicho -- normal y esperado):",
            "  Q1: 15-50 resultados por base",
            "  Q2: 5-20  resultados por base",
            "  Q3: 5-20  resultados por base",
            "  Total 3 bases: ~50-150 registros (manejable para cribado manual)",
            "  NOTA: Pocos resultados = hallazgo que valida la necesidad de esta RSL", "",
            "SIGUIENTE PASO:",
            f"  1. Ejecutar en: {info['url_busqueda']}",
            f"  2. Aplicar filtro Q1 segun instrucciones",
            f"  3. Exportar .ris -> 01_raw_data/ -> {base_key}_export_N.ris",
        ])

        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lineas))
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(base_data, f, ensure_ascii=False, indent=2)
        logger.info(f"  TXT : {txt_path}")
        logger.info(f"  JSON: {json_path}")
        logger.info(f"  Estado: {'OK (Q1 v2)' if todas_validas else 'REVISAR'}")
        resultados_export.append({"base": base, "validas": todas_validas, "txt": txt_path})
    return resultados_export


# ==============================================================================
# RESUMEN FINAL
# ==============================================================================

def generar_resumen_final(resultado: dict, resultados_export: list,
                          modelo: str, output_folder: str) -> None:
    resumen_path = os.path.join(output_folder, "queries_TODAS_LAS_BASES.txt")
    angulos  = resultado.get("thematic_angles", [])
    precision = resultado.get("precision_estimada", {})
    lineas = [
        "=" * 72,
        "RESUMEN COMPARATIVO v2 -- QUERIES Q1 PARA SCOPUS + WOS + IEEE",
        f"RSL    : {CONTEXTO_RSL['titulo_paper']}",
        f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Modelo : Ollama / {modelo}",
        f"Filtro : Solo publicaciones Q1 | Periodo: {CONTEXTO_RSL['periodo']}",
        "=" * 72, "",
        "MAPEO 1-a-1 QUERY <-> RQ:",
        "  Q1 -> RQ1: Modelado y caracterizacion dinamica del pH",
        "  Q2 -> RQ2: Control avanzado (NMPC/Fuzzy/metaheuristicas) vs PID",
        "  Q3 -> RQ3: ML/RL/hibridos y barreras de adopcion",
        "",
        "FILTROS Q1:",
        f"  Scopus -> {Q1_CONFIG['scopus_suffix']}",
        f"           + post-busqueda: Analyze Results > Source > Scimago Q1",
        f"  WoS    -> {Q1_CONFIG['wos_suffix']}",
        f"           + post-busqueda: Refine Results > JIF Quartile > Q1",
        f"  IEEE   -> Refine Results > Publication Type > Journals", "",
        "ANGULOS TEMATICOS:",
    ]
    for ang in angulos:
        lineas.append(f"  Q{ang.get('angle','?')}: {ang.get('topic_es','')} [{ang.get('rq_cubierta','')}]")
    lineas.extend(["", "ESTRATEGIA GLOBAL:", f"  {resultado.get('estrategia_global','')}", "",
                   "ADVERTENCIAS:"])
    for a in resultado.get("advertencias",[]): lineas.append(f"  - {a}")
    if precision:
        lineas.extend(["", "PRECISION ESTIMADA (Q1 journals):",
                       f"  Scopus : {precision.get('scopus','N/A')}",
                       f"  WoS    : {precision.get('wos','N/A')}",
                       f"  IEEE   : {precision.get('ieee','N/A')}",
                       f"  Justif.: {precision.get('justificacion','')}"])
    lineas.extend(["", "REVISTAS Q1 SUGERIDAS:",
                   *[f"  - {r}" for r in Q1_CONFIG["revistas_q1_sugeridas"]]])
    lineas.extend(["", "="*72, "QUERIES LADO A LADO", "="*72])
    for ang in angulos:
        num = ang.get("angle","?")
        lineas.extend(["", f"--- Q{num}: {ang.get('topic_es','')} ---", ""])
        for base in BASES_DE_DATOS:
            bd = resultado.get(base.lower(), {})
            qm = next((q for q in bd.get("queries",[])
                       if isinstance(q,dict) and q.get("numero")==num), None)
            if qm:
                qt = next((qm[c] for c in CLAVES_QUERY if c in qm and qm[c]), "")
                qt = aplicar_filtro_q1(qt, base)
                lineas.extend([f"  [{base}]", f"  {qt}", ""])
            else:
                lineas.extend([f"  [{base}] (no generada)", ""])
    lineas.extend(["", "="*72, "ARCHIVOS:"])
    for r in resultados_export:
        if r.get("txt"):
            lineas.append(f"  {'OK(Q1)' if r['validas'] else 'REVISAR'}  {r['base']:8} -> {r['txt']}")
    lineas.extend(["", "="*72, "SIGUIENTE PASO:", "",
        "1. Revisar queries en: queries_scopus.txt, queries_wos.txt, queries_ieee.txt",
        "2. Ejecutar en cada base de datos",
        "3. APLICAR FILTRO Q1 segun instrucciones de cada archivo",
        "4. Exportar .ris -> 01_raw_data/ -> ejecutar 00_fusion_base_datos.py",
        "5. Verificar precision > 80% en muestra aleatoria de 50 registros"])
    with open(resumen_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lineas))
    logger.info(f"Resumen: {resumen_path}")


# ==============================================================================
# QUERIES DE RESPALDO v2  (MODIFICADAS: se añadió "sugar juice" en el dominio)
# ==============================================================================

QUERIES_RESPALDO = {
    "Scopus": [
        {
            "numero": 1,
            "descripcion_tematica": "RQ1 - Modelado y caracterizacion dinamica del pH en clarificacion azucarera [Q1]",
            "query": (
                "TITLE-ABS-KEY(\n"
                '  ("pH control" OR "pH monitoring" OR "pH prediction" OR "pH optimization"\n'
                '   OR "pH regulation" OR "pH measurement" OR "pH adjustment" OR "pH correction"\n'
                '   OR "acidity control" OR "alkalinity control" OR "juice acidity"\n'
                '   OR "lime dosage" OR "lime addition" OR "calcium hydroxide" OR "milk of lime")\n'
                "  AND\n"
                '  ("sugar mill" OR "sugarcane" OR "cane juice" OR "sugar juice" OR "sugar industry"   # <--- AÑADIDO "sugar juice"\n'
                '   OR "juice clarification" OR "liming process" OR "defecation" OR "sulfitation"\n'
                '   OR "sugar beet" OR "beet sugar" OR "sugar factory" OR "saccharum")\n'
                "  AND\n"
                '  ("soft sensor" OR "virtual sensor" OR "inferential sensor"\n'
                '   OR "identification" OR "data-driven model" OR "data-driven"\n'
                '   OR "online estimation" OR "real-time estimation"\n'
                '   OR "neural network" OR "LSTM" OR "predictive model" OR "regression model")\n'
                ")\n"
                "AND NOT TITLE-ABS-KEY(\n"
                '  "wastewater" OR "water treatment" OR "soil pH" OR "blood pH"\n'
                '  OR "fermentation broth" OR "bioethanol" OR "pharmaceutical"\n'
                '  OR "bioreactor" OR "wine" OR "beer" OR "dairy" OR "groundwater"\n'
                ")\n"
                "AND SRCTYPE(j) AND DOCTYPE(ar OR re) AND PUBYEAR > 2014"
            ),
        },
        {
            "numero": 2,
            "descripcion_tematica": "RQ2 - Control avanzado (NMPC/Fuzzy/metaheuristicas) vs PID [Q1]",
            "query": (
                "TITLE-ABS-KEY(\n"
                '  ("model predictive control" OR "NMPC" OR "nonlinear MPC"\n'
                '   OR "fuzzy logic" OR "takagi-sugeno" OR "neuro-fuzzy"\n'
                '   OR "adaptive control" OR "intelligent control"\n'
                '   OR "PID tuning" OR "optimal control"\n'
                '   OR "pattern search" OR "particle swarm" OR "genetic algorithm"\n'
                '   OR "differential evolution" OR "bayesian optimization")\n'
                "  AND \"pH\"\n"
                '  AND ("sugar mill" OR "sugarcane" OR "cane juice" OR "sugar juice" OR "juice clarification"   # <--- AÑADIDO "sugar juice"\n'
                '       OR "liming process" OR "defecation" OR "sulfitation"\n'
                '       OR "sugar industry" OR "sugar beet" OR "sugar factory")\n'
                ")\n"
                "AND NOT TITLE-ABS-KEY(\n"
                '  "wastewater" OR "bioethanol" OR "fermentation broth" OR "pharmaceutical"\n'
                '  OR "soil" OR "blood" OR "wine" OR "dairy"\n'
                '  OR "desalination" OR "anaerobic digestion" OR "bioreactor"\n'
                ")\n"
                "AND SRCTYPE(j) AND DOCTYPE(ar OR re) AND PUBYEAR > 2014"
            ),
        },
        {
            "numero": 3,
            "descripcion_tematica": "RQ3 - ML/RL/hibridos y barreras de adopcion para pH en industria azucarera [Q1]",
            "query": (
                "TITLE-ABS-KEY(\n"
                '  ("machine learning" OR "deep learning" OR "neural network"\n'
                '   OR "artificial intelligence" OR "random forest" OR "gradient boosting"\n'
                '   OR "XGBoost" OR "lightGBM" OR "support vector"\n'
                '   OR "reinforcement learning" OR "deep reinforcement learning"\n'
                '   OR "DDPG" OR "PPO" OR "Q-learning"\n'
                '   OR "hybrid model" OR "grey-box model" OR "physics-informed"\n'
                '   OR "digital twin" OR "transfer learning")\n'
                "  AND \"pH\"\n"
                '  AND ("sugar" OR "sugarcane" OR "cane juice" OR "sugar juice" OR "clarification"   # <--- AÑADIDO "sugar juice"\n'
                '       OR "liming" OR "sugar mill" OR "sugar industry" OR "sugar beet"\n'
                '       OR "juice purification" OR "sugar factory" OR "defecation")\n'
                ")\n"
                "AND NOT TITLE-ABS-KEY(\n"
                '  "wastewater" OR "bioethanol" OR "pharmaceutical" OR "soil"\n'
                '  OR "blood" OR "bioreactor" OR "desalination"\n'
                '  OR "wine" OR "beer" OR "fermentation broth"\n'
                ")\n"
                "AND SRCTYPE(j) AND DOCTYPE(ar OR re) AND PUBYEAR > 2014"
            ),
        },
    ],
    "WoS": [
        {
            "numero": 1,
            "descripcion_tematica": "RQ1 - Modelado y caracterizacion dinamica del pH en clarificacion azucarera [Q1]",
            "query": (
                "TS=(\n"
                '  ("pH control" OR "pH monitoring" OR "pH prediction" OR "pH optimization"\n'
                '   OR "pH regulation" OR "pH measurement" OR "pH adjustment" OR "pH correction"\n'
                '   OR "acidity control" OR "alkalinity control" OR "juice acidity"\n'
                '   OR "lime dosage" OR "lime addition" OR "calcium hydroxide" OR "milk of lime")\n'
                "  AND\n"
                '  ("sugar mill" OR "sugarcane" OR "cane juice" OR "sugar juice" OR "sugar industry"   # <--- AÑADIDO "sugar juice"\n'
                '   OR "juice clarification" OR "liming process" OR "defecation" OR "sulfitation"\n'
                '   OR "sugar beet" OR "beet sugar" OR "sugar factory" OR "saccharum")\n'
                "  AND\n"
                '  ("soft sensor" OR "virtual sensor" OR "inferential sensor"\n'
                '   OR "identification" OR "data-driven model" OR "data-driven"\n'
                '   OR "online estimation" OR "real-time estimation"\n'
                '   OR "neural network" OR "LSTM" OR "predictive model" OR "regression model")\n'
                ")\n"
                "NOT TS=(\n"
                '  "wastewater" OR "water treatment" OR "soil pH" OR "blood pH"\n'
                '  OR "fermentation broth" OR "bioethanol" OR "pharmaceutical"\n'
                '  OR "bioreactor" OR "wine" OR "beer" OR "dairy" OR "groundwater"\n'
                ")\n"
                "AND DT=(Article OR Review) AND PY=(2015-2026)"
            ),
        },
        {
            "numero": 2,
            "descripcion_tematica": "RQ2 - Control avanzado (NMPC/Fuzzy/metaheuristicas) vs PID [Q1]",
            "query": (
                "TS=(\n"
                '  ("model predictive control" OR "NMPC" OR "nonlinear MPC"\n'
                '   OR "fuzzy logic" OR "takagi-sugeno" OR "neuro-fuzzy"\n'
                '   OR "adaptive control" OR "intelligent control"\n'
                '   OR "PID tuning" OR "optimal control"\n'
                '   OR "pattern search" OR "particle swarm" OR "genetic algorithm"\n'
                '   OR "differential evolution" OR "bayesian optimization")\n'
                "  AND \"pH\"\n"
                '  AND ("sugar mill" OR "sugarcane" OR "cane juice" OR "sugar juice" OR "juice clarification"   # <--- AÑADIDO "sugar juice"\n'
                '       OR "liming process" OR "defecation" OR "sulfitation"\n'
                '       OR "sugar industry" OR "sugar beet" OR "sugar factory")\n'
                ")\n"
                "NOT TS=(\n"
                '  "wastewater" OR "bioethanol" OR "fermentation broth" OR "pharmaceutical"\n'
                '  OR "soil" OR "blood" OR "wine" OR "dairy"\n'
                '  OR "desalination" OR "anaerobic digestion" OR "bioreactor"\n'
                ")\n"
                "AND DT=(Article OR Review) AND PY=(2015-2026)"
            ),
        },
        {
            "numero": 3,
            "descripcion_tematica": "RQ3 - ML/RL/hibridos y barreras de adopcion para pH en industria azucarera [Q1]",
            "query": (
                "TS=(\n"
                '  ("machine learning" OR "deep learning" OR "neural network"\n'
                '   OR "artificial intelligence" OR "random forest" OR "gradient boosting"\n'
                '   OR "XGBoost" OR "lightGBM" OR "support vector"\n'
                '   OR "reinforcement learning" OR "deep reinforcement learning"\n'
                '   OR "DDPG" OR "PPO" OR "Q-learning"\n'
                '   OR "hybrid model" OR "grey-box model" OR "physics-informed"\n'
                '   OR "digital twin" OR "transfer learning")\n'
                "  AND \"pH\"\n"
                '  AND ("sugar" OR "sugarcane" OR "cane juice" OR "sugar juice" OR "clarification"   # <--- AÑADIDO "sugar juice"\n'
                '       OR "liming" OR "sugar mill" OR "sugar industry" OR "sugar beet"\n'
                '       OR "juice purification" OR "sugar factory" OR "defecation")\n'
                ")\n"
                "NOT TS=(\n"
                '  "wastewater" OR "bioethanol" OR "pharmaceutical" OR "soil"\n'
                '  OR "blood" OR "bioreactor" OR "desalination"\n'
                '  OR "wine" OR "beer" OR "fermentation broth"\n'
                ")\n"
                "AND DT=(Article OR Review) AND PY=(2015-2026)"
            ),
        },
    ],
    "IEEE": [
        {
            "numero": 1,
            "descripcion_tematica": "RQ1 - Modelado y caracterizacion dinamica del pH en clarificacion azucarera [Q1]",
            "query": (
                '("pH control" OR "pH monitoring" OR "pH prediction" OR "pH optimization"\n'
                ' OR "pH regulation" OR "acidity control" OR "alkalinity control"\n'
                ' OR "lime dosage" OR "lime addition" OR "milk of lime")\n'
                "AND\n"
                '("sugar mill" OR "sugarcane" OR "cane juice" OR "sugar juice" OR "sugar industry"   # <--- AÑADIDO "sugar juice"\n'
                ' OR "juice clarification" OR "liming process" OR "sugar beet"\n'
                ' OR "sugar factory" OR "defecation" OR "sulfitation")\n'
                "AND\n"
                '("soft sensor" OR "virtual sensor" OR "identification"\n'
                ' OR "data-driven" OR "online estimation" OR "real-time estimation"\n'
                ' OR "neural network" OR "LSTM" OR "predictive model")\n'
                "NOT\n"
                '("wastewater" OR "water treatment" OR "soil pH" OR "blood pH"\n'
                ' OR "bioethanol" OR "pharmaceutical" OR "bioreactor" OR "wine" OR "beer")\n'
                "-- FILTRO Q1: Refine Results > Publication Type > Journals"
            ),
        },
        {
            "numero": 2,
            "descripcion_tematica": "RQ2 - Control avanzado (NMPC/Fuzzy/metaheuristicas) vs PID [Q1]",
            "query": (
                '("model predictive control" OR "NMPC" OR "nonlinear MPC"\n'
                ' OR "fuzzy logic" OR "takagi-sugeno" OR "neuro-fuzzy"\n'
                ' OR "adaptive control" OR "intelligent control"\n'
                ' OR "PID tuning" OR "optimal control"\n'
                ' OR "pattern search" OR "particle swarm" OR "genetic algorithm")\n'
                "AND \"pH\"\n"
                "AND\n"
                '("sugar mill" OR "sugarcane" OR "cane juice" OR "sugar juice" OR "juice clarification"   # <--- AÑADIDO "sugar juice"\n'
                ' OR "liming process" OR "defecation" OR "sugar industry"\n'
                ' OR "sugar beet" OR "sugar factory")\n'
                "NOT\n"
                '("wastewater" OR "bioethanol" OR "fermentation" OR "pharmaceutical"\n'
                ' OR "soil" OR "blood" OR "wine" OR "dairy" OR "desalination")\n'
                "-- FILTRO Q1: Refine Results > Publication Type > Journals"
            ),
        },
        {
            "numero": 3,
            "descripcion_tematica": "RQ3 - ML/RL/hibridos y barreras de adopcion para pH en industria azucarera [Q1]",
            "query": (
                '("machine learning" OR "deep learning" OR "neural network"\n'
                ' OR "artificial intelligence" OR "random forest" OR "gradient boosting"\n'
                ' OR "XGBoost" OR "support vector"\n'
                ' OR "reinforcement learning" OR "deep reinforcement learning"\n'
                ' OR "DDPG" OR "Q-learning"\n'
                ' OR "hybrid model" OR "digital twin" OR "transfer learning")\n'
                "AND \"pH\"\n"
                "AND\n"
                '("sugar" OR "sugarcane" OR "cane juice" OR "sugar juice" OR "clarification"   # <--- AÑADIDO "sugar juice"\n'
                ' OR "liming" OR "sugar mill" OR "sugar industry" OR "sugar beet"\n'
                ' OR "defecation" OR "sugar factory")\n'
                "NOT\n"
                '("wastewater" OR "bioethanol" OR "pharmaceutical" OR "soil"\n'
                ' OR "blood" OR "desalination" OR "wine" OR "beer")\n'
                "-- FILTRO Q1: Refine Results > Publication Type > Journals"
            ),
        },
    ],
}


def exportar_respaldo(modelo: str, output_folder: str) -> list[dict]:
    logger.info("Exportando queries de RESPALDO v2 (corregidas + ampliadas, Q1)...")
    r = {
        "thematic_angles": [
            {"angle": 1,
             "topic_es": "Modelado y sensores virtuales para pH en clarificacion (cana y remolacha)",
             "focus": "soft sensor, identification, data-driven, LSTM, online estimation",
             "rq_cubierta": "RQ1"},
            {"angle": 2,
             "topic_es": "Control avanzado: NMPC, logica difusa, metaheuristicas vs PID",
             "focus": "NMPC, Fuzzy, Pattern Search, PSO, GA, PID tuning",
             "rq_cubierta": "RQ2"},
            {"angle": 3,
             "topic_es": "ML, RL, hibridos y barreras de adopcion industrial",
             "focus": "ML, RL, Deep Learning, hybrid, digital twin, transfer learning",
             "rq_cubierta": "RQ3"},
        ],
        "estrategia_global": (
            "Mapeo 1-a-1 con las 3 RQs. Q1 cubre RQ1 (modelado/soft sensors), "
            "Q2 cubre RQ2 (control avanzado vs PID), Q3 cubre RQ3 (ML/RL/hibridos). "
            "Ancla azucarera obligatoria + estructura plana sin AND anidado. "
            "Filtros Q1 embebidos: SRCTYPE+DOCTYPE+PUBYEAR (Scopus), DT+PY (WoS), interfaz (IEEE)."
        ),
        "advertencias": [
            "AND anidado corregido en Q2/Q3 -- ya no causa 0 resultados",
            "sugar beet incluido -- cubre ~40% de produccion mundial de azucar",
            "acidity/alkalinity como sinonimos de pH -- captura papers sin 'pH' explicito",
            "Pocos resultados (~50-150 totales) es ESPERADO para este tema nicho",
            "Filtro Q1 final se confirma post-busqueda en Scimago (Scopus) o JCR (WoS)",
            "Se ha añadido 'sugar juice' al ancla de dominio para capturar el paper de Palacio-Morales et al. (Processes 2021)",
        ],
        "precision_estimada": {
            "scopus": "83-87% (Q1)",
            "wos":    "81-85% (Q1)",
            "ieee":   "86-91% (Q1)",
            "justificacion": "Triple AND plano + sinonimos ampliados + filtros Q1 embebidos",
        },
    }
    for base in BASES_DE_DATOS:
        r[base.lower()] = {"queries": QUERIES_RESPALDO[base]}
    return exportar_todo(r, modelo + " (RESPALDO-v2)", output_folder)


# ==============================================================================
# REPORTE FINAL EN CONSOLA
# ==============================================================================

def _reporte_consola(resultados_export: list, output_folder: str) -> None:
    logger.info("=" * 64)
    logger.info("RESULTADO FINAL (Q1 journals -- v2)")
    logger.info("=" * 64)
    ok = sum(1 for r in resultados_export if r["validas"])
    for r in resultados_export:
        estado = "OK(Q1)" if r["validas"] else "REVISAR"
        logger.info(f"  {estado}  {r['base']:10} -> {r.get('txt','(no generado)')}")
    logger.info(f"{ok}/{len(resultados_export)} bases con sintaxis valida")
    logger.info(f"Archivos en: {output_folder}/")
    logger.info("PROXIMOS PASOS:")
    logger.info("  1. Abre queries_TODAS_LAS_BASES.txt")
    logger.info("  2. Pega cada query en la interfaz correspondiente")
    logger.info("  3. SCOPUS: SRCTYPE(j)+DOCTYPE(ar OR re)+PUBYEAR > 2014 ya incluido")
    logger.info("     post-busqueda: Analyze Results > Source > Scimago Q1")
    logger.info("  4. WOS: DT=(Article OR Review)+PY=(2015-2026) ya incluido")
    logger.info("     post-busqueda: Refine Results > JIF Quartile > Q1")
    logger.info("  5. IEEE: Refine Results > Publication Type > Journals")
    logger.info("  6. Exportar .ris -> 01_raw_data/ -> python 00_fusion_base_datos.py")
    logger.info("NOTA: 50-150 resultados totales es NORMAL para este tema nicho.")
    logger.info("=" * 64)


# ==============================================================================
# CLI
# ==============================================================================

def parsear_args():
    p = argparse.ArgumentParser(
        description="Generador de queries Q1 (Scopus/WoS/IEEE) para RSL pH en azucar.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--output", "-o", default="output",
                   help="Carpeta donde se escriben las queries y el log de ejecucion.")
    p.add_argument("--model", "-m", default=None,
                   help="Modelo Ollama a usar (override del autodetect).")
    p.add_argument("--log-level", "-l", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                   help="Nivel de verbosidad.")
    p.add_argument("--respaldo", action="store_true",
                   help="No llama a Ollama; exporta directamente las queries de respaldo v2.")
    return p.parse_args()


# ==============================================================================
# MAIN
# ==============================================================================

def main():
    args = parsear_args()
    log_path = configurar_logging(args.output, args.log_level)

    logger.info("=" * 64)
    logger.info("GENERADOR DE QUERIES Q1 v2 -- RSL pH EN AZUCAR (3 RQs <-> 3 Queries)")
    logger.info(f"Bases: {', '.join(BASES_DE_DATOS)}")
    logger.info(f"Filtro: Q1 journals | Precision: {CONTEXTO_RSL['precision_objetivo']}")
    logger.info(f"Output folder: {args.output}")
    logger.info(f"Log file     : {log_path}")
    logger.info("=" * 64)

    os.makedirs(args.output, exist_ok=True)

    fallback = {
        **{"thematic_angles": [], "estrategia_global": "", "advertencias": []},
        **{b.lower(): {"queries": QUERIES_RESPALDO[b]} for b in BASES_DE_DATOS},
    }

    # Modo respaldo explicito -> no toca Ollama
    if args.respaldo:
        logger.info("Modo --respaldo: omitiendo Ollama.")
        re_ = exportar_respaldo("manual", args.output)
        generar_resumen_final(fallback, re_, "manual (respaldo-v2)", args.output)
        _reporte_consola(re_, args.output)
        return

    modelo = args.model or verificar_ollama()
    if not modelo:
        logger.warning("Ollama no disponible -- exportando RESPALDO v2.")
        re_ = exportar_respaldo("manual", args.output)
        generar_resumen_final(fallback, re_, "manual (respaldo-v2)", args.output)
        _reporte_consola(re_, args.output)
        return

    prompt = construir_prompt_triple(CONTEXTO_RSL)
    logger.info(f"Enviando prompt v2 a Ollama ({modelo})...")

    respuesta = llamar_ollama(prompt, modelo)
    if not respuesta:
        re_ = exportar_respaldo(modelo, args.output)
        generar_resumen_final(fallback, re_, modelo + " (respaldo-v2)", args.output)
        _reporte_consola(re_, args.output)
        return

    raw_path = os.path.join(args.output, "queries_raw_triple.txt")
    with open(raw_path, "w", encoding="utf-8") as f:
        f.write(respuesta)
    logger.info(f"Respuesta cruda guardada: {raw_path}")

    resultado = parsear_json(respuesta)
    if not resultado:
        logger.error(f"JSON no parseado -- usando RESPALDO. Revisa: {raw_path}")
        re_ = exportar_respaldo(modelo, args.output)
        generar_resumen_final(fallback, re_, modelo + " (respaldo-v2)", args.output)
        _reporte_consola(re_, args.output)
        return

    json_path = os.path.join(args.output, "queries_raw_triple.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)
    logger.info(f"JSON estructurado guardado: {json_path}")

    logger.info("Exportando con filtros Q1 v2...")
    re_ = exportar_todo(resultado, modelo, args.output)
    generar_resumen_final(resultado, re_, modelo, args.output)
    _reporte_consola(re_, args.output)


if __name__ == "__main__":
    main()