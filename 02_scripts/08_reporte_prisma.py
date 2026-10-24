"""
08_reporte_prisma.py
================================
RSL: Aplicaciones de ML para el Control de pH en la Industria Azucarera

Genera el diagrama PRISMA 2020 con los numeros REALES del pipeline,
extraidos automaticamente de los archivos RIS y el Excel del cribado Ollama.

Calcula matriz de confusion manual-vs-Ollama desde el Excel:
  - VP: ambos INCLUIR
  - FP: Ollama INCLUIR, manual EXCLUIR (falsos positivos del LLM)
  - FN: Ollama EXCLUIR, manual INCLUIR (rescatados manualmente)
  - VN: ambos EXCLUIR

SALIDAS (en --output):
  8.diagrama_prisma_2020.png   (configurable dpi)
  8.diagrama_prisma_2020.svg
  prisma_YYYYMMDD_HHMMSS.log

Uso:
  python 08_reporte_prisma.py
  python 08_reporte_prisma.py --raw-dir ..\01_raw_data `
                              --processed-dir ..\01_raw_data `
                              --filtered-dir ..\03_filtered_data `
                              --output ..\06_prisma
  python 08_reporte_prisma.py --dpi 600 --log-level DEBUG
"""

import os
import sys
import argparse
import logging
from datetime import datetime
from dataclasses import dataclass

import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

matplotlib.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size"  : 9,
})

logger = logging.getLogger("prisma")


# ── LOGGING ───────────────────────────────────────────────────────────────────
def configurar_logging(output_folder: str, log_level: str) -> str:
    os.makedirs(output_folder, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(output_folder, f"prisma_{timestamp}.log")

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


# ── NUMEROS DEL PIPELINE ──────────────────────────────────────────────────────
@dataclass
class PrismaNumbers:
    # Snapshot verificado 2026-04-02 — se sobrescriben si los archivos existen
    S1: int = 6;  S2: int = 2;  S3: int = 25
    W1: int = 0;  W2: int = 1;  W3: int = 15
    I1: int = 4;  I2: int = 0;  I3: int = 9

    DUPLICADOS:      int = 19
    UNICOS:          int = 43
    EXCL_TIPO_ANIO:  int = 23
    PREFILTRADO:     int = 20
    EXCL_CUARTIL:    int = 5
    Q1Q4:            int = 15

    EXCL_L0:   int = 15
    EVAL_LLM:  int = 0
    INCL_LLM:  int = 0
    EXCL_LLM:  int = 0
    REVISAR:   int = 0
    INCIERTO:  int = 0

    CORPUS_FINAL:      int = 0
    EXCL_MANUAL:       int = 0   # FP del LLM rechazados manualmente
    RESCATADOS_MANUAL: int = 0   # FN del LLM rescatados manualmente

    VP: int = 0
    FP: int = 0
    FN: int = 0
    VN: int = 0

    SENSIB:    str = "N/A (pendiente)"
    PRECISION: str = "N/A (pendiente)"
    F1:        str = "N/A (pendiente)"
    KAPPA:     str = "N/A (pendiente)"
    MODELO:    str = "Llama3:latest (T=0, six-shot, L1-relajado)"

    @property
    def SCOPUS(self) -> int:      return self.S1 + self.S2 + self.S3
    @property
    def WOS(self) -> int:         return self.W1 + self.W2 + self.W3
    @property
    def IEEE(self) -> int:        return self.I1 + self.I2 + self.I3
    @property
    def TOTAL_BRUTO(self) -> int: return self.SCOPUS + self.WOS + self.IEEE
    @property
    def REDUCCION(self) -> str:
        return f"{100*(1 - self.INCL_LLM/self.Q1Q4):.1f} %" if self.Q1Q4 > 0 else "N/A"


# ── LECTURA DE ARCHIVOS ───────────────────────────────────────────────────────
def contar_ris(path: str) -> int:
    """Cuenta entradas (`ER  -`) en un RIS. Devuelve -1 si no existe."""
    if not path or not os.path.exists(path) or os.path.isdir(path):
        return -1
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read().count("ER  -")


def leer_metricas_excel(path: str) -> dict:
    """Lee hojas 'Metricas' y 'Clasificacion' del Excel del script 04."""
    if not path or not os.path.exists(path) or os.path.isdir(path):
        return {}
    try:
        df_m  = pd.read_excel(path, sheet_name="Metricas")
        df_cl = pd.read_excel(path, sheet_name="Clasificacion")
    except Exception as e:
        logger.warning(f"No se pudo leer el Excel de Ollama '{path}': {e}")
        return {}

    metricas = {row["Metrica"]: row["Valor"] for _, row in df_m.iterrows()}
    if "nivel_certeza" in df_cl.columns:
        metricas["_nivel"] = df_cl["nivel_certeza"].value_counts().to_dict()
    else:
        metricas["_nivel"] = {}
    if {"nivel_certeza", "decision_ollama"}.issubset(df_cl.columns):
        metricas["_dec_niv"] = df_cl.groupby(
            ["nivel_certeza", "decision_ollama"]
        ).size().to_dict()
    else:
        metricas["_dec_niv"] = {}
    if "decision_manual" in df_cl.columns:
        metricas["_dm"] = df_cl["decision_manual"].value_counts().to_dict()
    else:
        metricas["_dm"] = {}
    return metricas


def actualizar_numeros(nums: PrismaNumbers, paths: dict) -> None:
    """Sobrescribe los conteos con los reales si los archivos existen."""
    logger.info("Verificando numeros desde archivos del pipeline...")
    cambios = 0

    # ── Conteos por query ────────────────────────────────────────────────
    mapping = [
        ("scopus_1", "S1"), ("scopus_2", "S2"), ("scopus_3", "S3"),
        ("wos_1",    "W1"), ("wos_2",    "W2"), ("wos_3",    "W3"),
        ("ieee_1",   "I1"), ("ieee_2",   "I2"), ("ieee_3",   "I3"),
    ]
    for key, attr in mapping:
        n = contar_ris(paths.get(key, ""))
        if n >= 0 and n != getattr(nums, attr):
            logger.info(f"  {key}: {getattr(nums, attr)} -> {n}")
            setattr(nums, attr, n)
            cambios += 1

    # ── Pipeline counts ──────────────────────────────────────────────────
    n_all = contar_ris(paths.get("fusion_all", ""))
    n_fus = contar_ris(paths.get("fusion", ""))
    n_pre = contar_ris(paths.get("prefiltrado", ""))
    n_fq  = contar_ris(paths.get("filtrado_q", ""))

    if n_all >= 0 and n_all != nums.TOTAL_BRUTO:
        logger.warning(
            f"  fusion_all observado={n_all} vs derivado={nums.TOTAL_BRUTO} "
            "(posible diferencia entre queries y fusion)."
        )

    for key, attr, current, observed in [
        ("fusion",      "UNICOS",      nums.UNICOS,      n_fus),
        ("prefiltrado", "PREFILTRADO", nums.PREFILTRADO, n_pre),
        ("filtrado_q",  "Q1Q4",        nums.Q1Q4,        n_fq),
    ]:
        if observed >= 0 and observed != current:
            logger.info(f"  {key}: {current} -> {observed}")
            setattr(nums, attr, observed)
            cambios += 1

    # ── Recalcular exclusiones derivadas ─────────────────────────────────
    if n_fus >= 0 and n_all >= 0 and n_all >= n_fus:
        nuevo_dup = n_all - n_fus
        if nuevo_dup != nums.DUPLICADOS:
            logger.info(f"  DUPLICADOS: {nums.DUPLICADOS} -> {nuevo_dup}")
            nums.DUPLICADOS = nuevo_dup
            cambios += 1

    if n_fus >= 0 and n_pre >= 0 and n_fus >= n_pre:
        nuevo_excl = n_fus - n_pre
        if nuevo_excl != nums.EXCL_TIPO_ANIO:
            logger.info(f"  EXCL_TIPO_ANIO: {nums.EXCL_TIPO_ANIO} -> {nuevo_excl}")
            nums.EXCL_TIPO_ANIO = nuevo_excl
            cambios += 1

    if n_pre >= 0 and n_fq >= 0 and n_pre >= n_fq:
        nuevo_excl_q = n_pre - n_fq
        if nuevo_excl_q != nums.EXCL_CUARTIL:
            logger.info(f"  EXCL_CUARTIL: {nums.EXCL_CUARTIL} -> {nuevo_excl_q}")
            nums.EXCL_CUARTIL = nuevo_excl_q
            cambios += 1

    # ── Metricas del Excel de Ollama ─────────────────────────────────────
    m = leer_metricas_excel(paths.get("xlsx_ollama", ""))
    if m:
        niv     = m.get("_nivel", {})
        dec_niv = m.get("_dec_niv", {})
        dm      = m.get("_dm", {})

        n_local  = niv.get("LOCAL", nums.EXCL_L0)
        n_auto_i = dec_niv.get(("AUTO", "INCLUIR"), nums.INCL_LLM)
        n_auto_e = dec_niv.get(("AUTO", "EXCLUIR"), nums.EXCL_LLM)
        n_rev    = niv.get("REVISAR",  nums.REVISAR)
        n_inc    = niv.get("INCIERTO", nums.INCIERTO)
        n_dm_i   = dm.get("INCLUIR", nums.CORPUS_FINAL)

        for attr, nuevo in [
            ("EXCL_L0",      n_local),
            ("INCL_LLM",     n_auto_i),
            ("EXCL_LLM",     n_auto_e),
            ("REVISAR",      n_rev),
            ("INCIERTO",     n_inc),
            ("CORPUS_FINAL", n_dm_i),
        ]:
            if nuevo != getattr(nums, attr):
                logger.info(f"  {attr}: {getattr(nums, attr)} -> {nuevo}")
                setattr(nums, attr, nuevo)
                cambios += 1

        eval_llm = nums.Q1Q4 - nums.EXCL_L0
        if eval_llm != nums.EVAL_LLM:
            nums.EVAL_LLM = max(0, eval_llm)
            cambios += 1

        # ── Matriz de confusion manual vs Ollama ─────────────────────────
        path_xlsx = paths.get("xlsx_ollama", "")
        try:
            df_cl = pd.read_excel(path_xlsx, sheet_name="Clasificacion")
        except Exception:
            df_cl = None

        if df_cl is not None and "decision_manual" in df_cl.columns:
            df_rev = df_cl[df_cl["decision_manual"].notna()].copy()
            if len(df_rev):
                y_oll = df_rev["decision_ollama"].astype(str).str.upper().str.strip()
                y_man = df_rev["decision_manual"].astype(str).str.upper().str.strip()

                vp = int(((y_man == "INCLUIR") & (y_oll == "INCLUIR")).sum())
                fp = int(((y_man == "EXCLUIR") & (y_oll == "INCLUIR")).sum())
                fn = int(((y_man == "INCLUIR") & (y_oll == "EXCLUIR")).sum())
                vn = int(((y_man == "EXCLUIR") & (y_oll == "EXCLUIR")).sum())

                nums.VP = vp
                nums.FP = fp
                nums.FN = fn
                nums.VN = vn
                nums.EXCL_MANUAL       = fp   # FP del LLM rechazados
                nums.RESCATADOS_MANUAL = fn   # FN del LLM rescatados

                sens = vp / (vp + fn) if (vp + fn) else 0.0
                prec = vp / (vp + fp) if (vp + fp) else 0.0
                f1   = (2 * prec * sens / (prec + sens)) if (prec + sens) else 0.0

                nums.SENSIB    = f"{sens:.1%}"
                nums.PRECISION = f"{prec:.1%}"
                nums.F1        = f"{f1:.1%}"

                logger.info(f"Matriz confusion (manual vs Ollama, {len(df_rev)} revisados):")
                logger.info(f"  VP={vp}  FP={fp}  FN={fn}  VN={vn}")
                logger.info(f"  Sensibilidad={nums.SENSIB}  "
                            f"Precision={nums.PRECISION}  F1={nums.F1}")

    if cambios == 0:
        logger.info("Todos los numeros coinciden con los valores verificados.")
    else:
        logger.info(f"{cambios} valores actualizados desde archivos.")


# ── COLORES ───────────────────────────────────────────────────────────────────
C_MAIN    = "#E6F1FB"
C_EXCL    = "#FAECE7"
C_FINAL   = "#E1F5EE"
C_RESCATE = "#FFF4CC"   # ambar suave para rescatados
C_TEXT    = "#2C2C2A"
C_BRD     = "#B4B2A9"
C_ARW     = "#73726C"
C_HEAD    = "#1A5276"


# ── DIBUJO ────────────────────────────────────────────────────────────────────
def caja(ax, x, y, w, h, txt, color=C_MAIN, fs=8.0, bold=False):
    ax.add_patch(FancyBboxPatch(
        (x - w / 2, y - h / 2), w, h,
        boxstyle="round,pad=0.025",
        facecolor=color, edgecolor=C_BRD, linewidth=0.9, zorder=2,
    ))
    weight = "bold" if bold else "normal"
    ax.text(x, y, txt, ha="center", va="center",
            fontsize=fs, color=C_TEXT, fontweight=weight,
            multialignment="center", zorder=3)


def flecha(ax, x1, y1, x2, y2):
    ax.annotate(
        "", xy=(x2, y2), xytext=(x1, y1),
        arrowprops=dict(arrowstyle="-|>", color=C_ARW, lw=1.0),
        zorder=4,
    )


def etiqueta_fase(ax, x, y, txt):
    ax.text(x, y, txt, va="center", ha="center",
            fontsize=7.5, fontweight="bold", color=C_HEAD,
            rotation=90, zorder=3)


def generar_diagrama(n: PrismaNumbers, out_png: str, out_svg: str, dpi: int) -> None:
    os.makedirs(os.path.dirname(out_png) or ".", exist_ok=True)

    fig, ax = plt.subplots(figsize=(15, 22))
    ax.set_xlim(0, 15)
    ax.set_ylim(0, 22)
    ax.axis("off")
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    ax.text(7.5, 21.5,
            "PRISMA 2020 — RSL: Aplicaciones de ML para el Control de pH\n"
            "en la Industria Azucarera",
            ha="center", va="center", fontsize=12, fontweight="bold",
            color=C_TEXT)
    ax.text(7.5, 21.0,
            "Scopus + Web of Science + IEEE Xplore | 2015-2026 | Q1-Q4 (SJR)",
            ha="center", va="center", fontsize=9, color="#555550")

    XL, XR, XM = 4.0, 11.5, 7.5
    W_BOX, W_EXC = 6.0, 5.8

    # ── FASE 1: IDENTIFICACION ───────────────────────────────────────────
    etiqueta_fase(ax, 0.4, 19.3, "IDENTIFICACION")

    caja(ax, XL, 19.3, W_BOX, 1.1,
         f"Registros identificados en bases de datos\n"
         f"Scopus:      {n.SCOPUS}  (S1={n.S1} | S2={n.S2} | S3={n.S3})\n"
         f"WoS:         {n.WOS}    (W1={n.W1} | W2={n.W2} | W3={n.W3})\n"
         f"IEEE Xplore: {n.IEEE}    (I1={n.I1} | I2={n.I2} | I3={n.I3})\n"
         f"Total bruto (9 consultas, 3 angulos): {n.TOTAL_BRUTO}",
         fs=7.8)

    caja(ax, XR, 19.3, W_EXC, 0.75,
         f"Duplicados eliminados por DOI\nn = {n.DUPLICADOS}",
         color=C_EXCL, fs=8.2)

    caja(ax, XL, 18.0, W_BOX, 0.65,
         f"Registros unicos tras deduplicacion\nn = {n.UNICOS}",
         fs=8.5)

    flecha(ax, XL, 18.73, XL, 18.33)
    flecha(ax, XL + W_BOX/2, 19.3, XR - W_EXC/2, 19.3)

    # ── FASE 2: PREFILTRADO ──────────────────────────────────────────────
    etiqueta_fase(ax, 0.4, 17.1, "PREFILTRADO")

    caja(ax, XL, 17.1, W_BOX, 0.65,
         f"Evaluados por tipo de documento y ano\nn = {n.UNICOS}",
         fs=8.5)

    caja(ax, XR, 17.1, W_EXC, 0.85,
         f"Excluidos por tipo de documento y ano\n"
         f"Congresos, no journals, fuera 2015-2026\n"
         f"Total excluidos: {n.EXCL_TIPO_ANIO}",
         color=C_EXCL, fs=7.8)

    caja(ax, XL, 15.9, W_BOX, 0.65,
         f"Registros tras prefiltrado\nn = {n.PREFILTRADO}  (articulos originales, 2015-2026)",
         fs=8.5)

    flecha(ax, XL, 17.67, XL, 17.43)
    flecha(ax, XL, 16.77, XL, 16.23)
    flecha(ax, XL + W_BOX/2, 17.1, XR - W_EXC/2, 17.1)

    # ── FASE 3: ELEGIBILIDAD SJR ─────────────────────────────────────────
    etiqueta_fase(ax, 0.4, 15.1, "ELEGIBILIDAD\nSJR")

    caja(ax, XL, 15.1, W_BOX, 0.65,
         f"Integracion con SCImago (SJR)\nn = {n.PREFILTRADO}",
         fs=8.5)

    caja(ax, XR, 15.1, W_EXC, 0.85,
         f"Excluidos por ausencia de cuartil SJR\n"
         f"Sin cuartil SCImago asignado: {n.EXCL_CUARTIL}\n"
         f"Total excluidos: {n.EXCL_CUARTIL}",
         color=C_EXCL, fs=7.8)

    caja(ax, XL, 13.9, W_BOX, 0.75,
         f"Articulos Q1-Q4 para cribado semantico\n"
         f"n = {n.Q1Q4}  (filtro SRCTYPE(j) + cuartil SJR asignado)  |  Total: {n.Q1Q4}",
         fs=8.5)

    flecha(ax, XL, 15.57, XL, 15.43)
    flecha(ax, XL, 14.77, XL, 14.28)
    flecha(ax, XL + W_BOX/2, 15.1, XR - W_EXC/2, 15.1)

    # ── FASE 4: FILTRO LOCAL ─────────────────────────────────────────────
    etiqueta_fase(ax, 0.4, 13.0, "FILTRO\nLOCAL\nL0/L1/L2")

    caja(ax, XL, 13.0, W_BOX, 1.0,
         f"Filtro local 3 niveles (sin costo LLM) | n = {n.Q1Q4}\n"
         f"L0: Stopwords exclusion fuerte (procesos no azucareros,\n"
         f"    mineria, farmaceutica, ADN/ARN, jugos de fruta, etc.)\n"
         f"L1: Al menos 1 termino de proceso de pH industria azucarera\n"
         f"L2: Al menos 1 termino de IA / optimizacion",
         fs=7.5)

    caja(ax, XR, 13.0, W_EXC, 0.75,
         f"Excluidos por filtro local (sin LLM)\n"
         f"n = {n.EXCL_L0}   (L0+L1+L2 combinados)\n"
         f"Ahorro: {n.EXCL_L0} llamadas a Ollama evitadas",
         color=C_EXCL, fs=7.8)

    caja(ax, XL, 11.7, W_BOX, 0.65,
         f"Articulos para evaluacion por Llama3-Ollama\nn = {n.EVAL_LLM}",
         fs=8.5)

    flecha(ax, XL, 13.5, XL, 13.5)
    flecha(ax, XL, 12.5, XL, 12.03)
    flecha(ax, XL + W_BOX/2, 13.0, XR - W_EXC/2, 13.0)

    # ── FASE 5: CRIBADO LLM ──────────────────────────────────────────────
    etiqueta_fase(ax, 0.4, 10.8, "CRIBADO\nLLM\n(Llama3)")

    caja(ax, XL, 10.8, W_BOX, 1.0,
         f"Cribado semantico Llama3-Ollama | n = {n.EVAL_LLM}\n"
         f"Protocolo: Six-shot + filtro L1 relajado\n"
         f"Umbral automatico: >= 75% confianza\n"
         f"Temperatura: 0 (determinista)",
         fs=7.5)

    caja(ax, XR, 10.8, W_EXC, 0.85,
         f"Excluidos por Llama3 (automatico)\n"
         f"n = {n.EXCL_LLM}  (confianza >= 75%, decision=EXCLUIR)\n"
         f"+ Revision manual: {n.REVISAR} REVISAR | {n.INCIERTO} INCIERTO",
         color=C_EXCL, fs=7.8)

    caja(ax, XL, 9.5, W_BOX, 0.65,
         f"Candidatos para revision de texto completo\n"
         f"n = {n.INCL_LLM}  (LLM -> INCLUIR automatico)",
         fs=8.5)

    flecha(ax, XL, 11.3, XL, 9.83)
    flecha(ax, XL + W_BOX/2, 10.8, XR - W_EXC/2, 10.8)

    # ── FASE 6: LECTURA COMPLETA ─────────────────────────────────────────
    etiqueta_fase(ax, 0.4, 8.65, "LECTURA\nCOMPLETA\n+ REVISION")

    caja(ax, XL, 8.65, W_BOX, 1.0,
         f"Revision texto completo por revisor experto\n"
         f"Candidatos del LLM: {n.INCL_LLM}\n"
         f"+ Rescatados manualmente: {n.RESCATADOS_MANUAL}\n"
         f"= Total revisados: {n.INCL_LLM + n.RESCATADOS_MANUAL}\n"
         f"Confirmacion final via decision_manual",
         fs=7.5)

    # Caja derecha: dos sub-cajas verticales para FP y FN
    caja(ax, XR, 8.95, W_EXC, 0.55,
         f"Falsos positivos del LLM rechazados (FP)\n"
         f"n = {n.FP}  |  Precision LLM = {n.PRECISION}",
         color=C_EXCL, fs=7.5)

    caja(ax, XR, 8.30, W_EXC, 0.55,
         f"Rescatados manualmente (FN del LLM)\n"
         f"n = {n.FN}  |  Sensibilidad LLM = {n.SENSIB}",
         color=C_RESCATE, fs=7.5)

    flecha(ax, XL, 9.83, XL, 9.15)
    flecha(ax, XL, 8.15, XL, 7.5)
    flecha(ax, XL + W_BOX/2, 8.95, XR - W_EXC/2, 8.95)
    flecha(ax, XL + W_BOX/2, 8.30, XR - W_EXC/2, 8.30)

    # ── CORPUS FINAL ─────────────────────────────────────────────────────
    etiqueta_fase(ax, 0.4, 7.0, "CORPUS\nFINAL")

    caja(ax, XL, 7.0, W_BOX, 1.0,
         f"CORPUS FINAL DE LA RSL\n"
         f"n = {n.CORPUS_FINAL}\n"
         f"Criterios: Q1-Q4 | 2015-2026 | ML + pH industria azucarera\n"
         f"Seleccion: decision_manual == INCLUIR",
         color=C_FINAL, fs=9.0, bold=True)

    # ── Metricas ─────────────────────────────────────────────────────────
    n_rev = n.VP + n.FP + n.FN + n.VN
    metricas_txt = (
        f"METRICAS DEL PROTOCOLO DE CRIBADO SEMANTICO  "
        f"(n revisados manualmente = {n_rev})\n"
        f"Matriz: VP={n.VP}  FP={n.FP}  FN={n.FN}  VN={n.VN}\n"
        f"Sensibilidad: {n.SENSIB}  |  Precision: {n.PRECISION}  |  "
        f"F1: {n.F1}  |  Reduccion carga manual: {n.REDUCCION}\n"
        f"Kappa de Cohen: {n.KAPPA}   (calcular con 05_kappa_cohen.py)\n"
        f"Protocolo: {n.MODELO} + filtro L0/L1/L2 + umbral >= 75%\n"
        f"Scopus ({n.SCOPUS}) + WoS ({n.WOS}) + IEEE ({n.IEEE}) | 9 consultas | 3 angulos"
    )
    ax.text(XM, 4.1, metricas_txt,
            ha="center", va="center", fontsize=7.8,
            color=C_TEXT, multialignment="center",
            bbox=dict(boxstyle="round,pad=0.5", facecolor=C_MAIN,
                      edgecolor=C_BRD, linewidth=0.9))

    # ── Leyenda ──────────────────────────────────────────────────────────
    legend_items = [
        (1.7,   C_MAIN,    "Incluidos / Procesados"),
        (5.6,   C_EXCL,    "Excluidos"),
        (9.5,   C_RESCATE, "Rescatados (FN del LLM)"),
        (13.3,  C_FINAL,   "Corpus final"),
    ]
    for xp, col, lbl in legend_items:
        ax.add_patch(FancyBboxPatch(
            (xp - 1.55, 2.85), 3.1, 0.45,
            boxstyle="round,pad=0.02",
            facecolor=col, edgecolor=C_BRD, lw=0.8, zorder=2,
        ))
        ax.text(xp, 3.08, lbl, ha="center", va="center",
                fontsize=7.5, color=C_TEXT, zorder=3)

    ax.text(XM, 2.4,
            "Elaboracion propia. Adaptado de PRISMA 2020 (Page et al., 2021).\n"
            "Pipeline: 00_fusion -> 01_prefiltrado -> 02_quartiles -> "
            "03_filtrado_q -> 04_ollama.",
            ha="center", va="center", fontsize=7.5,
            color="#888880", style="italic")

    plt.tight_layout(pad=0.5)
    fig.savefig(out_png, dpi=dpi, bbox_inches="tight", facecolor="white")
    fig.savefig(out_svg, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    logger.info(f"PNG ({dpi} dpi): {out_png}")
    logger.info(f"SVG          : {out_svg}")


# ── REPORTE ───────────────────────────────────────────────────────────────────
def imprimir_reporte(n: PrismaNumbers) -> None:
    logger.info("=" * 65)
    logger.info("RESUMEN PIPELINE RSL pH EN INDUSTRIA AZUCARERA")
    logger.info("=" * 65)
    logger.info(f"Bruto (9 queries) : {n.TOTAL_BRUTO}")
    logger.info(f"  Scopus  (3 queries): {n.SCOPUS} (S1={n.S1}|S2={n.S2}|S3={n.S3})")
    logger.info(f"  WoS     (3 queries): {n.WOS}    (W1={n.W1}|W2={n.W2}|W3={n.W3})")
    logger.info(f"  IEEE    (3 queries): {n.IEEE}    (I1={n.I1}|I2={n.I2}|I3={n.I3})")
    logger.info(f"Duplicados DOI    : -{n.DUPLICADOS}")
    logger.info(f"Unicos            : {n.UNICOS}")
    logger.info(f"Excl. tipo+ano    : -{n.EXCL_TIPO_ANIO}")
    logger.info(f"Prefiltrado       : {n.PREFILTRADO}")
    logger.info(f"Excl. cuartil     : -{n.EXCL_CUARTIL}")
    logger.info(f"Q1-Q4             : {n.Q1Q4}")
    logger.info(f"Excl. filtro local: -{n.EXCL_L0}")
    logger.info(f"Eval. LLM         : {n.EVAL_LLM}")
    logger.info(f"Incl. automatico  : {n.INCL_LLM}")
    logger.info(f"Excl. LLM auto    : -{n.EXCL_LLM}")
    logger.info(f"Rescatados (FN)   : +{n.RESCATADOS_MANUAL}")
    logger.info(f"FP rechazados     : -{n.EXCL_MANUAL}")
    logger.info(f"CORPUS FINAL      : {n.CORPUS_FINAL}")
    logger.info("Metricas (manual vs Ollama):")
    logger.info(f"  VP={n.VP}  FP={n.FP}  FN={n.FN}  VN={n.VN}")
    logger.info(f"  Sensibilidad: {n.SENSIB}")
    logger.info(f"  Precision   : {n.PRECISION}")
    logger.info(f"  F1          : {n.F1}")
    logger.info(f"  Reduccion   : {n.REDUCCION}")
    logger.info("=" * 65)
    if n.CORPUS_FINAL == 0:
        logger.warning("CORPUS_FINAL = 0. Revisar:")
        logger.warning("  1. Que el Excel 4.filtrado_ollama.xlsx tenga decision_manual=INCLUIR")
        logger.warning("  2. Que el script 04 haya corrido con queries actualizadas")
    else:
        logger.info(f"{n.CORPUS_FINAL} estudios en el corpus final")
    logger.info("SIGUIENTE PASO: python 05_kappa_cohen.py")
    logger.info("=" * 65)


# ── CLI ───────────────────────────────────────────────────────────────────────
def parsear_args():
    p = argparse.ArgumentParser(
        description="Diagrama PRISMA 2020 a partir de los archivos del pipeline RSL.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--raw-dir", default="01_raw_data",
                   help="Carpeta con scopus_export_*, wos_export_*, ieee_export_*.ris")
    p.add_argument("--processed-dir", default="output",
                   help="Carpeta con fusion_export.ris y fusion_export_all.ris")
    p.add_argument("--filtered-dir", default="output",
                   help="Carpeta con 1.prefiltrado.ris, 2.fusionado_con_cuartiles.ris, "
                        "3.filtrado_quartiles.ris y 4.filtrado_ollama.xlsx")
    p.add_argument("--output", "-o", default="output",
                   help="Carpeta de salida (PNG, SVG y log).")
    p.add_argument("--dpi", type=int, default=300,
                   help="Resolucion de la figura PNG.")
    p.add_argument("--log-level", "-l", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                   help="Nivel de verbosidad.")
    return p.parse_args()


def construir_paths(args) -> dict:
    """Construye el diccionario de rutas a partir de los directorios CLI."""
    r, p, f = args.raw_dir, args.processed_dir, args.filtered_dir
    return {
        "scopus_1"    : os.path.join(r, "scopus_export_1.ris"),
        "scopus_2"    : os.path.join(r, "scopus_export_2.ris"),
        "scopus_3"    : os.path.join(r, "scopus_export_3.ris"),
        "wos_1"       : os.path.join(r, "wos_export_1.ris"),
        "wos_2"       : os.path.join(r, "wos_export_2.ris"),
        "wos_3"       : os.path.join(r, "wos_export_3.ris"),
        "ieee_1"      : os.path.join(r, "ieee_export_1.ris"),
        "ieee_2"      : os.path.join(r, "ieee_export_2.ris"),
        "ieee_3"      : os.path.join(r, "ieee_export_3.ris"),
        "fusion_all"  : os.path.join(p, "fusion_export_all.ris"),
        "fusion"      : os.path.join(p, "fusion_export.ris"),
        "prefiltrado" : os.path.join(f, "1.prefiltrado.ris"),
        "fusionado_q" : os.path.join(f, "2.fusionado_con_cuartiles.ris"),
        "filtrado_q"  : os.path.join(f, "3.filtrado_quartiles.ris"),
        "xlsx_ollama" : os.path.join(f, "4.filtrado_ollama.xlsx"),
    }


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    args = parsear_args()
    log_path = configurar_logging(args.output, args.log_level)

    out_png = os.path.join(args.output, "8.diagrama_prisma_2020.png")
    out_svg = os.path.join(args.output, "8.diagrama_prisma_2020.svg")

    logger.info("=" * 65)
    logger.info("PRISMA 2020 — RSL pH EN INDUSTRIA AZUCARERA")
    logger.info("=" * 65)
    logger.info(f"Raw dir       : {args.raw_dir}")
    logger.info(f"Processed dir : {args.processed_dir}")
    logger.info(f"Filtered dir  : {args.filtered_dir}")
    logger.info(f"Output folder : {args.output}")
    logger.info(f"DPI           : {args.dpi}")
    logger.info(f"Log file      : {log_path}")

    paths = construir_paths(args)
    nums = PrismaNumbers()

    logger.info("[1] Verificando numeros desde archivos del pipeline...")
    actualizar_numeros(nums, paths)

    logger.info("[2] Generando diagrama PRISMA 2020...")
    generar_diagrama(nums, out_png, out_svg, args.dpi)

    imprimir_reporte(nums)


if __name__ == "__main__":
    main()