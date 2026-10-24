"""
05_kappa_cohen.py
=================
RSL: Aplicaciones de ML para el Control de pH en la Industria Azucarera

Calcula el kappa de Cohen entre el cribado Ollama y la revisión manual.
Genera tabla de concordancia lista para incluir en el paper.

Flujo previo:
  1. Abre la salida del script 04 (4.filtrado_ollama.xlsx) → hoja "Clasificacion"
  2. Agrega columna "decision_manual" con INCLUIR/EXCLUIR para los
     artículos revisados manualmente
  3. Ejecuta este script

Uso:
  python 05_kappa_cohen.py
  python 05_kappa_cohen.py --input ..\03_filtered_data\4.filtrado_ollama.xlsx --output ..\03_filtered_data
  python 05_kappa_cohen.py --precision-target 0.80 --log-level DEBUG
"""

import os
import sys
import argparse
import logging
from datetime import datetime

import pandas as pd
from sklearn.metrics import cohen_kappa_score, confusion_matrix

logger = logging.getLogger("kappa_cohen")


# ── LOGGING ───────────────────────────────────────────────────────────────────
def configurar_logging(output_folder: str, log_level: str) -> str:
    os.makedirs(output_folder, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(output_folder, f"kappa_cohen_{timestamp}.log")

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


# ── INTERPRETACION KAPPA (Landis & Koch 1977) ─────────────────────────────────
def interpretar_kappa(k: float) -> str:
    if k >= 0.81: return "Casi perfecta (>= 0.81)"
    if k >= 0.61: return "Sustancial (0.61–0.80)"
    if k >= 0.41: return "Moderada (0.41–0.60)"
    if k >= 0.21: return "Aceptable (0.21–0.40)"
    return "Leve (< 0.21)"


# ── CLI ───────────────────────────────────────────────────────────────────────
def parsear_args():
    p = argparse.ArgumentParser(
        description="Kappa de Cohen entre cribado Ollama y revisión manual.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--input", "-i", default="output/4.filtrado_ollama.xlsx",
                   help="Excel con hoja 'Clasificacion' (salida del script 04 + columna decision_manual).")
    p.add_argument("--output", "-o", default="output",
                   help="Carpeta de salida (Excel de métricas y log).")
    p.add_argument("--sheet", "-s", default="Clasificacion",
                   help="Nombre de la hoja con las decisiones.")
    p.add_argument("--col-ollama", default="decision_ollama",
                   help="Nombre de la columna con la decisión del LLM.")
    p.add_argument("--col-manual", default="decision_manual",
                   help="Nombre de la columna con la decisión manual.")
    p.add_argument("--precision-target", type=float, default=0.50,
                   help="Precisión mínima objetivo (0-1).")
    p.add_argument("--log-level", "-l", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                   help="Nivel de verbosidad.")
    return p.parse_args()


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    args = parsear_args()
    log_path = configurar_logging(args.output, args.log_level)

    excel_out = os.path.join(args.output, "5.kappa_cohen.xlsx")

    logger.info("=" * 60)
    logger.info("KAPPA DE COHEN — RSL pH INDUSTRIA AZUCARERA")
    logger.info("=" * 60)
    logger.info(f"Input Excel     : {args.input}")
    logger.info(f"Hoja            : {args.sheet}")
    logger.info(f"Col. Ollama     : {args.col_ollama}")
    logger.info(f"Col. manual     : {args.col_manual}")
    logger.info(f"Precision target: {args.precision_target:.0%}")
    logger.info(f"Output folder   : {args.output}")
    logger.info(f"Log file        : {log_path}")

    # ── Validación de entrada ────────────────────────────────────────────
    if not os.path.exists(args.input):
        logger.error(f"No se encontró el Excel: {args.input}")
        logger.error("Ejecuta primero el script 04 o ajusta --input.")
        sys.exit(1)
    if os.path.isdir(args.input):
        logger.error(f"--input debe ser un archivo .xlsx, no carpeta: {args.input}")
        sys.exit(1)

    try:
        df = pd.read_excel(args.input, sheet_name=args.sheet)
    except ValueError as e:
        logger.error(f"No se pudo leer la hoja '{args.sheet}': {e}")
        sys.exit(1)

    logger.info(f"Total filas cargadas: {len(df)}")

    # Validar columnas
    faltantes = [c for c in (args.col_ollama, args.col_manual) if c not in df.columns]
    if faltantes:
        logger.error(f"Columnas faltantes en la hoja '{args.sheet}': {faltantes}")
        logger.error(f"Columnas disponibles: {list(df.columns)}")
        sys.exit(1)

    df_rev = df[df[args.col_manual].notna()].copy()
    logger.info(f"Artículos con revisión manual: {len(df_rev)}")

    if df_rev.empty:
        logger.warning(f"La columna '{args.col_manual}' está vacía en todas las filas.")
        logger.warning("Agrega decisiones manuales (INCLUIR/EXCLUIR) y vuelve a ejecutar.")
        sys.exit(0)

    # ── Cálculo de métricas ──────────────────────────────────────────────
    y_ollama = df_rev[args.col_ollama].astype(str).str.upper().str.strip()
    y_manual = df_rev[args.col_manual].astype(str).str.upper().str.strip()

    # Filtrar etiquetas no válidas
    validas = {"INCLUIR", "EXCLUIR"}
    mask_valida = y_ollama.isin(validas) & y_manual.isin(validas)
    descartadas = (~mask_valida).sum()
    if descartadas:
        logger.warning(f"{descartadas} filas con etiquetas no válidas descartadas "
                       f"(solo se aceptan INCLUIR/EXCLUIR).")
        y_ollama = y_ollama[mask_valida]
        y_manual = y_manual[mask_valida]
        df_rev   = df_rev[mask_valida].copy()

    if len(df_rev) == 0:
        logger.error("Sin filas con etiquetas válidas tras filtrar. Abortando.")
        sys.exit(1)

    kappa = cohen_kappa_score(y_manual, y_ollama)
    cm = confusion_matrix(y_manual, y_ollama, labels=["INCLUIR", "EXCLUIR"])
    vp, fn = int(cm[0, 0]), int(cm[0, 1])
    fp, vn = int(cm[1, 0]), int(cm[1, 1])

    sensibilidad = vp / (vp + fn) if (vp + fn) > 0 else 0.0
    precision    = vp / (vp + fp) if (vp + fp) > 0 else 0.0
    f1 = (2 * precision * sensibilidad / (precision + sensibilidad)
          if (precision + sensibilidad) > 0 else 0.0)
    reduccion = 100 * (1 - (vp + fp) / len(df)) if len(df) > 0 else 0.0

    # ── Reporte ──────────────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("MÉTRICAS — LISTAS PARA EL PAPER")
    logger.info("=" * 60)
    logger.info(f"Kappa de Cohen          : {kappa:.3f}")
    logger.info(f"Interpretación          : {interpretar_kappa(kappa)}")
    logger.info(f"Sensibilidad (recall)   : {sensibilidad:.1%}")
    logger.info(f"Precisión               : {precision:.1%}")
    logger.info(f"F1-score                : {f1:.1%}")
    logger.info(f"Reducción carga manual  : {reduccion:.1f}%")
    logger.info("Matriz de confusión:")
    logger.info(f"  {'':20} Ollama INCLUIR  Ollama EXCLUIR")
    logger.info(f"  {'Manual INCLUIR':20} {vp:^15} {fn:^15}  (VP={vp}, FN={fn})")
    logger.info(f"  {'Manual EXCLUIR':20} {fp:^15} {vn:^15}  (FP={fp}, VN={vn})")
    logger.info("=" * 60)

    if precision >= args.precision_target:
        logger.info(f"Objetivo de precisión >= {args.precision_target:.0%} ALCANZADO ({precision:.1%})")
    else:
        logger.warning(f"Precisión {precision:.1%} < objetivo {args.precision_target:.0%} "
                       "— revisar filtro local y ejemplos few-shot.")

    # ── Exportar Excel ───────────────────────────────────────────────────
    objetivo_str = f"Precision >= {args.precision_target:.0%}"
    metricas = pd.DataFrame({
        "Métrica": [
            "Kappa de Cohen", "Interpretación kappa",
            "Sensibilidad (recall)", "Precisión", "F1-score",
            "Reducción carga manual (%)",
            "VP (Verdaderos Positivos)", "VN (Verdaderos Negativos)",
            "FP (Falsos Positivos)", "FN (Falsos Negativos)",
            "Total revisados manualmente",
            objetivo_str,
        ],
        "Valor": [
            round(kappa, 3), interpretar_kappa(kappa),
            f"{sensibilidad:.1%}", f"{precision:.1%}", f"{f1:.1%}",
            f"{reduccion:.1f}%",
            vp, vn, fp, fn, len(df_rev),
            "ALCANZADO" if precision >= args.precision_target else "NO ALCANZADO",
        ],
    })

    cm_df = pd.DataFrame(
        cm,
        index=["Manual: INCLUIR", "Manual: EXCLUIR"],
        columns=["Ollama: INCLUIR", "Ollama: EXCLUIR"],
    )

    cols_detalle = [c for c in ["TI", args.col_ollama, args.col_manual,
                                "confianza_ollama", "justificacion_ollama"]
                    if c in df_rev.columns]

    with pd.ExcelWriter(excel_out, engine="openpyxl") as writer:
        metricas.to_excel(writer, sheet_name="Metricas_Kappa", index=False)
        cm_df.to_excel(writer, sheet_name="Matriz_Confusion")
        df_rev[cols_detalle].to_excel(writer, sheet_name="Detalle", index=False)

    logger.info(f"Excel exportado: {excel_out}")
    logger.info("=" * 60)
    logger.info("COMPLETADO -> siguiente: python 06_preparar_notebooklm.py")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()