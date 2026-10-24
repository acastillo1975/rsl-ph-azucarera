"""
06_preparar_notebooklm.py
=====================================
RSL: Aplicaciones de ML para el Control de pH en la Industria Azucarera

Lee el Excel de clasificacion Ollama, filtra por decision_manual == "INCLUIR"
(columna agregada por el investigador tras la revision manual), y genera un
documento estructurado listo para cargar en NotebookLM como fuente unica.

LOGICA DE SELECCION (en orden de prioridad):
  1. Si existe la columna "decision_manual" -> usa decision_manual == "INCLUIR"
  2. Si no existe "decision_manual"        -> usa decision_ollama  == "INCLUIR"

SALIDAS (en --output):
  6.corpus_notebooklm.txt   -> cargar en NotebookLM
  6.tabla4_estructura.xlsx  -> base para completar Tabla 4 del paper
  notebooklm_prep_YYYYMMDD_HHMMSS.log

Uso:
  python 06_preparar_notebooklm.py
python 06_preparar_notebooklm.py --input ..\03_filtered_data\4.filtrado_ollama.xlsx `
  --ris   ..\03_filtered_data\4.filtrado_ollama.ris `
  --pdf-folder ..\04_corpus_final\pdfs `
  python 06_preparar_notebooklm.py --log-level DEBUG
"""

import os
import re
import sys
import ast
import argparse
import logging
from datetime import datetime

import pandas as pd

try:
    import pdfplumber
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

# ── CONSTANTES DE NEGOCIO ─────────────────────────────────────────────────────
HOJA_CLASIFICACION  = "Clasificacion"
COL_DECISION_MANUAL = "decision_manual"
COL_DECISION_OLLAMA = "decision_ollama"
OLLAMA_TAG          = "Ollama-five-shot-pH"

logger = logging.getLogger("notebooklm_prep")


# ── LOGGING ───────────────────────────────────────────────────────────────────
def configurar_logging(output_folder: str, log_level: str) -> str:
    os.makedirs(output_folder, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(output_folder, f"notebooklm_prep_{timestamp}.log")

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


# ── PREGUNTAS RQ PARA NOTEBOOKLM ──────────────────────────────────────────────
RQS_EXTRACCION = [
    ("RQ1", "Que tecnica especifica de IA aplica este estudio al proceso de extraccion/molienda? "
            "(ELM, KELM, DDPG, CNN, PINN, MPC, soft sensor, etc.)"),
    ("RQ2-var", "Cuales son las variables de entrada del modelo? "
                "(velocidad de molino, presion hidraulica, imbibicion, humedad del bagazo, corriente, etc.)"),
    ("RQ2-out", "Cuales son las variables de salida / indicadores predichos? "
                "(eficiencia de extraccion, %pol, calidad del jugo, consumo energetico, etc.)"),
    ("RQ2-met", "Que metricas de rendimiento reporta el estudio? (R2, RMSE, MAE, MAPE, etc.)"),
    ("RQ3",     "Como se compara el modelo propuesto con la linea base convencional? "
                "(PID, control manual, regresion lineal, modelos estadisticos)"),
    ("RQ4",     "Que limitaciones o brechas senalan los autores para la implementacion "
                "en lazo cerrado durante una campana completa de zafra?"),
    ("TRL",     "En que nivel TRL (1-9) clasificarias este estudio y por que? "
                "(TRL4=laboratorio, TRL5=planta piloto, TRL6=entorno relevante, TRL7=demostracion)"),
    ("GEO",     "En que pais y que tipo de fabrica/instalacion fue validado el estudio?"),
    ("DATOS",   "De donde provienen los datos usados para entrenar/validar el modelo? "
                "(DCS industrial, SCADA, laboratorio, simulacion, datos historicos)"),
]


# ── LECTURA DEL CORPUS ────────────────────────────────────────────────────────
def leer_corpus(xlsx_path: str, ris_path: str) -> tuple[list[dict], str]:
    """
    Lee los articulos con decision INCLUIR.
    Prioriza decision_manual sobre decision_ollama.
    Retorna (lista_de_entradas, fuente_usada).
    """
    if os.path.exists(xlsx_path) and not os.path.isdir(xlsx_path):
        try:
            df = pd.read_excel(xlsx_path, sheet_name=HOJA_CLASIFICACION)
        except Exception as e:
            logger.error(f"Error leyendo Excel '{xlsx_path}' hoja '{HOJA_CLASIFICACION}': {e}")
            df = pd.DataFrame()

        if not df.empty:
            if COL_DECISION_MANUAL in df.columns:
                df_incl = df[df[COL_DECISION_MANUAL].astype(str).str.upper() == "INCLUIR"].copy()
                fuente  = f"Excel '{HOJA_CLASIFICACION}' -> columna '{COL_DECISION_MANUAL}'"
                logger.info(f"Columna '{COL_DECISION_MANUAL}' encontrada.")
                logger.info(f"Articulos con {COL_DECISION_MANUAL}=INCLUIR: {len(df_incl)}")

                if COL_DECISION_OLLAMA in df_incl.columns:
                    corr = df_incl[
                        df_incl[COL_DECISION_OLLAMA].astype(str).str.upper() != "INCLUIR"
                    ]
                    if len(corr) > 0:
                        logger.warning(f"{len(corr)} correcciones manuales (Ollama habia dicho EXCLUIR):")
                        for _, r in corr.iterrows():
                            logger.warning(f"  * {str(r.get('TI',''))[:70]}")
            else:
                if COL_DECISION_OLLAMA in df.columns:
                    df_incl = df[df[COL_DECISION_OLLAMA].astype(str).str.upper() == "INCLUIR"].copy()
                else:
                    df_incl = df.copy()
                fuente = f"Excel '{HOJA_CLASIFICACION}' -> '{COL_DECISION_OLLAMA}' (sin decision_manual)"
                logger.warning(f"Columna '{COL_DECISION_MANUAL}' no encontrada.")
                logger.info(f"Usando '{COL_DECISION_OLLAMA}': {len(df_incl)} articulos.")

            entradas = []
            for _, row in df_incl.iterrows():
                entrada = {col: row[col] for col in df_incl.columns if pd.notna(row[col])}
                entradas.append(entrada)
            return entradas, fuente

    # ── Respaldo: RIS ─────────────────────────────────────────────────────
    logger.warning(f"Excel no encontrado o vacio en {xlsx_path}. Intentando RIS...")
    if not os.path.exists(ris_path):
        logger.error(f"Tampoco existe {ris_path}")
        return [], "ninguna"

    entradas, actual = [], {}
    with open(ris_path, "r", encoding="utf-8") as f:
        for linea in f:
            linea = linea.rstrip("\n").rstrip("\r")
            if linea.strip() == "ER  -":
                if actual:
                    entradas.append(actual)
                actual = {}
            elif "  -" in linea:
                partes = linea.split("  - ", 1)
                if len(partes) == 2:
                    tag, val = partes[0].strip(), partes[1].strip()
                    if tag in actual:
                        prev = actual[tag]
                        actual[tag] = (prev if isinstance(prev, list) else [prev]) + [val]
                    else:
                        actual[tag] = val
    if actual:
        entradas.append(actual)
    return entradas, "RIS (todos los registros)"


# ── UTILIDADES ────────────────────────────────────────────────────────────────
def normalizar(val) -> str:
    if val is None:
        return ""
    if isinstance(val, list):
        return "; ".join(str(v) for v in val if v and str(v) not in ("nan", "None"))
    s = str(val).strip()
    if s in ("nan", "None", ""):
        return ""
    if s.startswith("[") and s.endswith("]"):
        try:
            parsed = ast.literal_eval(s)
            if isinstance(parsed, list):
                return "; ".join(str(v) for v in parsed if str(v) not in ("nan", "None"))
        except Exception:
            pass
    return s


def _extraer_re(texto: str, patron: str) -> str:
    m = re.search(patron, texto)
    return m.group(1).strip() if m else ""


def extraer_meta_n1(n1: str) -> dict:
    return {
        "cuartil"             : _extraer_re(n1, r"SJR Best Quartile:\s*(Q\d)"),
        "sjr"                 : _extraer_re(n1, r"SJR:\s*([\d,\.]+)"),
        "decision_ollama_tag" : _extraer_re(n1, rf"{OLLAMA_TAG}:\s*(\w+)"),
        "confianza"           : _extraer_re(n1, r"conf=(\d+)%"),
        "nivel"               : _extraer_re(n1, r"nivel=(\w+)"),
        "justificacion"       : _extraer_re(n1, rf"{OLLAMA_TAG}:\s*(.+?)\s*\[conf="),
    }


def extraer_texto_pdf(pdf_path: str) -> str:
    if not PDF_AVAILABLE:
        return "[pdfplumber no instalado - pip install pdfplumber]"
    try:
        paginas = []
        with pdfplumber.open(pdf_path) as pdf:
            for pag in pdf.pages:
                t = pag.extract_text()
                if t:
                    paginas.append(t)
        return "\n".join(paginas) if paginas else "[PDF sin texto extraible]"
    except Exception as e:
        return f"[Error al leer PDF: {e}]"


def buscar_pdf(doi: str, titulo: str, n: int, carpeta: str) -> str:
    if not PDF_AVAILABLE or not carpeta or not os.path.exists(carpeta):
        return f"[Sin PDF - coloca el archivo en {carpeta or '<carpeta no especificada>'}]"
    doi_clean = re.sub(r'[/:\\*?"<>|]', "_", doi)
    candidatos = [
        f"{doi_clean}.pdf",
        f"articulo_{n:02d}.pdf",
        f"{n:02d}_{doi_clean[:40]}.pdf",
        f"{n:02d}.pdf",
    ]
    for nombre in candidatos:
        ruta = os.path.join(carpeta, nombre)
        if os.path.exists(ruta):
            logger.info(f"[{n}] PDF encontrado: {nombre}")
            return extraer_texto_pdf(ruta)
    return f"[Sin PDF - coloca el archivo en {carpeta}]"


# ── CONSTRUCCION DE BLOQUE NOTEBOOKLM ─────────────────────────────────────────
def construir_bloque(n: int, entrada: dict, pdf_folder: str) -> str:
    titulo   = normalizar(entrada.get("TI", "Sin titulo"))
    autores  = normalizar(entrada.get("AU", ""))
    anio     = normalizar(entrada.get("PY", ""))
    revista  = normalizar(entrada.get("T2", ""))
    doi      = normalizar(entrada.get("DO", ""))
    abstract = normalizar(entrada.get("AB", ""))
    keywords = normalizar(entrada.get("KW", ""))
    n1       = normalizar(entrada.get("N1", ""))
    vol      = normalizar(entrada.get("VL", ""))
    num      = normalizar(entrada.get("IS", ""))
    sp       = normalizar(entrada.get("SP", ""))
    ep       = normalizar(entrada.get("EP", ""))
    db       = normalizar(entrada.get("DB", ""))

    dec_ollama = normalizar(entrada.get(COL_DECISION_OLLAMA, ""))
    dec_manual = normalizar(entrada.get(COL_DECISION_MANUAL, ""))
    justif_col = normalizar(entrada.get("justificacion_ollama", ""))
    conf_col   = normalizar(entrada.get("confianza_ollama", ""))
    nivel_col  = normalizar(entrada.get("nivel_certeza", ""))

    meta = extraer_meta_n1(n1)
    cuartil = meta["cuartil"] or _extraer_re(dec_ollama, r"Q\d")
    justif  = justif_col or meta["justificacion"]
    conf    = conf_col   or meta["confianza"]
    nivel   = nivel_col  or meta["nivel"]

    fue_corregido = (dec_manual.upper() == "INCLUIR" and dec_ollama.upper() != "INCLUIR")

    texto_pdf = buscar_pdf(doi, titulo, n, pdf_folder)

    paginas = f"{sp}-{ep}" if sp and ep else (sp if sp else "")

    sep, sep2 = "=" * 72, "-" * 50

    lineas = [
        sep,
        f"ARTICULO {n}: {titulo}",
        sep,
        "",
        "REFERENCIA COMPLETA:",
        f"  Autores  : {autores}",
        f"  Anio     : {anio}",
        f"  Revista  : {revista}",
        f"  Volumen  : {vol}{'  Numero: ' + num if num else ''}"
        f"{'  Paginas: ' + paginas if paginas else ''}",
        f"  DOI      : {doi}",
        f"  Base dat.: {db}",
        f"  Cuartil  : {cuartil if cuartil else 'Ver SJR'}",
        "",
        "CLASIFICACION DEL PIPELINE:",
        f"  decision_ollama : {dec_ollama if dec_ollama else meta['decision_ollama_tag']}",
        f"  decision_manual : {dec_manual if dec_manual else '(no revisado)'}",
        f"  Confianza Ollama: {conf}%  |  Nivel: {nivel}",
        f"  Justificacion   : {justif}",
    ]

    if fue_corregido:
        lineas += [
            "",
            "*** CORRECCION MANUAL: Ollama habia dicho EXCLUIR pero el revisor ***",
            "*** lo reclasifica como INCLUIR tras lectura del texto completo.  ***",
        ]

    lineas += [
        "",
        "ABSTRACT:",
        abstract,
        "",
        "PALABRAS CLAVE:",
        keywords,
        "",
        sep2,
        "PREGUNTAS GUIA PARA NotebookLM (RSL pH Industria Azucarera con IA)",
        sep2,
    ]

    for codigo, pregunta in RQS_EXTRACCION:
        lineas.append(f"[{codigo}] {pregunta}")

    lineas += [
        "",
        sep2,
        "TEXTO COMPLETO DEL PDF (para analisis profundo en NotebookLM):",
        sep2,
        texto_pdf,
        "",
    ]
    return "\n".join(lineas)


# ── ESTRUCTURA TABLA 4 ────────────────────────────────────────────────────────
def construir_fila_tabla4(n: int, entrada: dict) -> dict:
    n1      = normalizar(entrada.get("N1", ""))
    meta    = extraer_meta_n1(n1)
    autores = normalizar(entrada.get("AU", ""))
    anio    = normalizar(entrada.get("PY", ""))
    titulo  = normalizar(entrada.get("TI", ""))
    primer_autor = autores.split(";")[0].split(",")[0].strip() if autores else "?"
    ref_apa = f"{primer_autor} ({anio})"

    return {
        "N"                          : n,
        "Referencia_APA"             : ref_apa,
        "Autores"                    : autores,
        "Anio"                       : anio,
        "Titulo"                     : titulo[:120],
        "Revista"                    : normalizar(entrada.get("T2", "")),
        "DOI"                        : normalizar(entrada.get("DO", "")),
        "Cuartil_SJR"                : meta["cuartil"],
        "Base_datos"                 : normalizar(entrada.get("DB", "")),
        "decision_ollama"            : normalizar(entrada.get(COL_DECISION_OLLAMA, "")),
        "decision_manual"            : normalizar(entrada.get(COL_DECISION_MANUAL, "")),
        "Confianza_Ollama_%"         : normalizar(entrada.get("confianza_ollama", "")),
        "Nivel_certeza"              : normalizar(entrada.get("nivel_certeza", "")),
        "RQ1_Tecnica_IA"             : "",
        "RQ1_Familia_IA"             : "",
        "RQ1_Subtecnica"             : "",
        "RQ2_Variables_entrada"      : "",
        "RQ2_Variable_salida_ppal"   : "",
        "RQ2_Metrica_R2"             : "",
        "RQ2_Metrica_RMSE"           : "",
        "RQ2_Metrica_MAE"            : "",
        "RQ2_Metrica_MAPE_%"         : "",
        "RQ2_Fuente_datos"           : "",
        "RQ2_N_muestras"             : "",
        "RQ2_Horizonte_validacion"   : "",
        "RQ3_Baseline"               : "",
        "RQ3_Mejora_extraccion_%"    : "",
        "RQ3_Mejora_energia_%"       : "",
        "RQ3_Mejora_calidad"         : "",
        "RQ3_Resultado_cuantitativo" : "",
        "RQ4_Lazo_cerrado"           : "",
        "RQ4_Validacion_industrial"  : "",
        "RQ4_Brechas_senaladas"      : "",
        "TRL_estimado"               : "",
        "TRL_justificacion"          : "",
        "GEO_pais"                   : "",
        "GEO_tipo_instalacion"       : "",
        "Notas_revisor"              : "",
    }


# ── CLI ───────────────────────────────────────────────────────────────────────
def parsear_args():
    p = argparse.ArgumentParser(
        description="Prepara corpus estructurado para NotebookLM a partir del Excel del script 04.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--input", "-i", default="output/4.filtrado_ollama.xlsx",
                   help="Excel con hoja 'Clasificacion' (salida del script 04).")
    p.add_argument("--ris", default="output/4.filtrado_ollama.ris",
                   help="RIS de respaldo si el Excel no esta disponible.")
    p.add_argument("--pdf-folder", default="04_corpus_final/pdfs",
                   help="Carpeta con los PDFs a extraer (opcional).")
    p.add_argument("--output", "-o", default="output",
                   help="Carpeta de salida (TXT, Excel y log).")
    p.add_argument("--log-level", "-l", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                   help="Nivel de verbosidad.")
    return p.parse_args()


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    args = parsear_args()
    log_path = configurar_logging(args.output, args.log_level)

    output_txt   = os.path.join(args.output, "6.corpus_notebooklm.txt")
    output_excel = os.path.join(args.output, "6.tabla4_estructura.xlsx")

    logger.info("=" * 65)
    logger.info("PREPARANDO CORPUS PARA NotebookLM — RSL pH INDUSTRIA AZUCARERA")
    logger.info("=" * 65)
    logger.info(f"Input Excel   : {args.input}")
    logger.info(f"Input RIS     : {args.ris}")
    logger.info(f"PDF folder    : {args.pdf_folder}")
    logger.info(f"Output folder : {args.output}")
    logger.info(f"Log file      : {log_path}")
    if not PDF_AVAILABLE:
        logger.warning("pdfplumber no instalado. Sin extraccion de PDFs (pip install pdfplumber).")

    entradas, fuente = leer_corpus(args.input, args.ris)
    logger.info(f"Fuente usada: {fuente}")
    logger.info(f"Total articulos INCLUIR: {len(entradas)}")

    if not entradas:
        logger.error("No se encontraron articulos INCLUIR.")
        logger.error(f"Verifica que existe '{args.input}' con la hoja '{HOJA_CLASIFICACION}'")
        logger.error(f"y que la columna '{COL_DECISION_MANUAL}' tiene valores 'INCLUIR'.")
        sys.exit(1)

    os.makedirs(args.output, exist_ok=True)

    bloques, filas_t4 = [], []
    for n, entrada in enumerate(entradas, 1):
        titulo = normalizar(entrada.get("TI", f"Articulo {n}"))
        logger.info(f"[{n}/{len(entradas)}] {titulo[:70]}...")
        bloques.append(construir_bloque(n, entrada, args.pdf_folder))
        filas_t4.append(construir_fila_tabla4(n, entrada))

    cabecera = (
        "CORPUS FINAL RSL: CONTROL DE pH EN LA INDUSTRIA AZUCARERA MEDIANTE IA\n"
        f"Total articulos incluidos: {len(entradas)} "
        f"(seleccion: {COL_DECISION_MANUAL})\n"
        f"Fuente: {fuente}\n"
        "\n"
        "INSTRUCCION PARA NotebookLM:\n"
        "  Usa las PREGUNTAS GUIA [RQ1]-[GEO] al final de cada articulo.\n"
        "  Responde con el numero de articulo para facilitar la organizacion.\n"
        "  Copia las respuestas en el archivo 6.tabla4_estructura.xlsx.\n"
        "\n"
    )

    with open(output_txt, "w", encoding="utf-8") as f:
        f.write(cabecera)
        for bloque in bloques:
            f.write(bloque)
            f.write("\n\n")
    logger.info(f"Corpus NotebookLM exportado: {output_txt}")

    df_t4 = pd.DataFrame(filas_t4)
    instrucciones = {
        "Columna": [
            "RQ1_Tecnica_IA", "RQ1_Familia_IA", "RQ1_Subtecnica",
            "RQ2_Variables_entrada", "RQ2_Variable_salida_ppal",
            "RQ2_Metrica_R2", "RQ2_Metrica_RMSE", "RQ2_Metrica_MAE",
            "RQ2_Fuente_datos", "RQ2_N_muestras",
            "RQ3_Baseline", "RQ3_Mejora_extraccion_%",
            "RQ3_Resultado_cuantitativo",
            "RQ4_Lazo_cerrado", "RQ4_Validacion_industrial", "RQ4_Brechas_senaladas",
            "TRL_estimado", "GEO_pais",
        ],
        "Pregunta_NotebookLM": [
            "Que tecnica de IA aplica este estudio?",
            "A que familia pertenece? (ML clasico / Deep Learning / Optimizacion / Control avanzado)",
            "Cual es la subtecnica especifica? (DK-ELM, CNN-KELM, PINN, DDPG, MPC, etc.)",
            "Cuales son las variables de entrada del modelo?",
            "Cual es la variable de salida principal predicha?",
            "Que valor de R2 reporta? (numero)",
            "Que valor de RMSE reporta? (numero + unidad)",
            "Que valor de MAE reporta? (numero + unidad)",
            "De donde provienen los datos? (DCS/SCADA/lab/simulacion)",
            "Cuantas muestras/registros usa el dataset?",
            "Con que linea base compara el modelo? (PID, manual, regresion)",
            "Cuanta mejora en eficiencia de extraccion reporta? (%)",
            "Cual es el resultado cuantitativo principal?",
            "Opera en lazo cerrado? (Si / No / Parcial)",
            "Donde se valido? (planta real / piloto / laboratorio)",
            "Que brechas o limitaciones senalan los autores?",
            "Que nivel TRL estimarias? (1-9)",
            "En que pais se realizo el estudio?",
        ],
        "Valores_posibles": [
            "texto libre", "ML clasico / Deep Learning / Optimizacion / Control avanzado",
            "ELM / KELM / DK-ELM / CNN-KELM / PINN / DDPG / MPC / etc.",
            "texto libre (listar variables DCS)", "eficiencia extraccion / %pol / energia / calidad jugo",
            "0.00 a 1.00", "numero + unidad (ej: 0.31 %)", "numero + unidad",
            "DCS / SCADA / laboratorio / simulacion / historicos", "numero",
            "PID / manual / regresion lineal / estadistico",
            "numero (ej: 1.8, 3.2, etc.)", "texto libre",
            "Si / No / Parcial", "Planta real / Piloto / Laboratorio / Simulacion",
            "texto libre", "1 / 2 / 3 / 4 / 5 / 6 / 7 / 8 / 9",
            "pais (ej: China / Brasil / Cuba / India)",
        ],
    }

    with pd.ExcelWriter(output_excel, engine="openpyxl") as writer:
        df_t4.to_excel(writer, sheet_name="Tabla4_Extraccion", index=False)
        pd.DataFrame(instrucciones).to_excel(
            writer, sheet_name="Instrucciones_NotebookLM", index=False
        )
    logger.info(f"Estructura Tabla 4 exportada: {output_excel}")
    logger.info("  Hojas: 'Tabla4_Extraccion' | 'Instrucciones_NotebookLM'")

    # ── Resumen ──────────────────────────────────────────────────────────
    logger.info("=" * 65)
    logger.info("RESUMEN DEL CORPUS FINAL")
    logger.info("=" * 65)
    for n, e in enumerate(entradas, 1):
        titulo  = normalizar(e.get("TI", "?"))[:65]
        autores = normalizar(e.get("AU", "?")).split(";")[0].strip()
        anio    = normalizar(e.get("PY", "?"))
        doi     = normalizar(e.get("DO", "?"))
        n1      = normalizar(e.get("N1", ""))
        meta    = extraer_meta_n1(n1)
        dec_man = normalizar(e.get(COL_DECISION_MANUAL, "")).upper()
        dec_oll = normalizar(e.get(COL_DECISION_OLLAMA, "")).upper()
        corr    = " [CORRECCION MANUAL]" if dec_man == "INCLUIR" and dec_oll != "INCLUIR" else ""
        logger.info(f"[{n}] {autores} ({anio}) | {meta['cuartil'] or 'Q?'}{corr}")
        logger.info(f"     {titulo}")
        logger.info(f"     DOI: {doi}")

    logger.info("=" * 65)
    logger.info("INSTRUCCIONES NOTEBOOKLM")
    logger.info("=" * 65)
    logger.info("1. Ve a: https://notebooklm.google.com")
    logger.info("2. Crea un nuevo notebook")
    logger.info(f"3. Carga el archivo: {output_txt}")
    logger.info("Preguntas sugeridas:")
    logger.info('  -> "Por cada articulo: que tecnica de IA aplica y a que proceso?"')
    logger.info('  -> "Lista R2, RMSE y MAE de cada paper del corpus."')
    logger.info('  -> "Que variables de entrada usa cada modelo? (DCS, presion, velocidad)"')
    logger.info('  -> "Como mejora cada estudio la eficiencia frente al baseline?"')
    logger.info('  -> "En que nivel TRL (1-9) clasificarias cada estudio y por que?"')
    logger.info('  -> "Que brechas metodologicas senalan los autores para lazo cerrado?"')
    logger.info('  -> "En que pais y tipo de fabrica fue validado cada estudio?"')
    logger.info(f"4. Copia las respuestas a: {output_excel} (hoja Tabla4_Extraccion)")
    logger.info("=" * 65)
    logger.info("SIGUIENTE PASO: python 07_bibliometria_python.py")
    logger.info("=" * 65)


if __name__ == "__main__":
    main()