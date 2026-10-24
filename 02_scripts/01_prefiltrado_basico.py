"""
01_prefiltrado_basico.py
===========================
Pre-filtrado básico de datos RIS
Filtros aplicados:
  1. Tipo de documento: solo artículos de revista (JOUR/Article)
     Compatible con Scopus, WoS e IEEE Xplore
  2. Año de publicación: configurable (--year-start / --year-end)
  3. Exporta exclusion_log.csv con motivo por cada registro excluido
     → ese CSV se convierte directamente en el Apéndice A del paper (PRISMA)

Uso:
  python 01_prefiltrado_basico.py
  python 01_prefiltrado_basico.py --input ..\01_raw_data\fusion_export.ris --output ..\03_filtered_data
  python 01_prefiltrado_basico.py --year-start 2015 --year-end 2026 --log-level DEBUG

"""

import os
import sys
import argparse
import logging
from datetime import datetime
import pandas as pd

logger = logging.getLogger("prefiltrado_rsl")

# ── CONSTANTES DE NEGOCIO ─────────────────────────────────────────────────────
TIPOS_VALIDOS_TY = [
    "JOUR",            # Scopus, WoS estándar
    "Journal Article", # WoS texto completo
    "Article",         # Genérico RIS estándar
    "J",               # IEEE abreviado
]

TIPOS_EXCLUIDOS_TY = [
    "CONF", "CPAPER",            # Conferencias
    "BOOK", "CHAP", "EDBOOK",    # Libros y capítulos
    "THES", "DISS",              # Tesis
    "RPRT", "TECHREPORT", "STD", # Reportes y normas
    "NEWS", "ABST", "PAMP", "COMP", "DATA",
]

FIELD_TO_TAG = {
    "Reference Type": "TY", "Title": "TI", "Secondary Title": "T2",
    "Year": "PY", "Start Page": "SP", "End Page": "EP", "DOI": "DO",
    "URLs": "UR", "Author Address": "AD", "Abstract": "AB",
    "Keywords": "KW", "Publisher": "PB", "ISSN": "SN", "Language": "LA",
    "Alternate Title": "J2", "Type of Work": "M3", "Name of Database": "DB",
    "Notes": "N1", "Volume": "VL", "Number": "IS", "Custom 7": "C7",
    "Custom 2": "C2", "Short Title": "ST", "Author": "AU",
    "Secondary Author": "A2", "Tertiary Author": "A3", "Editor": "ED",
    "Series Title": "SE", "Translator": "TR", "Label": "LB",
    "Research Notes": "RN", "Access Date": "Y2", "Database Provider": "DP",
}


# ── LOGGING ───────────────────────────────────────────────────────────────────
def configurar_logging(output_folder: str, log_level: str) -> str:
    os.makedirs(output_folder, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(output_folder, f"prefiltrado_{timestamp}.log")

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


# ── LECTURA RIS ───────────────────────────────────────────────────────────────
def leer_ris(filepath: str) -> pd.DataFrame:
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"No se encontró: {filepath}")
    entradas, entrada_actual = [], {}
    with open(filepath, "r", encoding="utf-8") as f:
        for linea in f:
            if linea.strip() == "ER  -":
                entradas.append(entrada_actual)
                entrada_actual = {}
            elif "  -" in linea:
                clave, _, valor = linea.partition("  - ")
                clave, valor = clave.strip(), valor.strip()
                if clave in entrada_actual:
                    existing = entrada_actual[clave]
                    if isinstance(existing, list):
                        existing.append(valor)
                    else:
                        entrada_actual[clave] = [existing, valor]
                else:
                    entrada_actual[clave] = valor
    logger.debug(f"{filepath}: {len(entradas)} entradas parseadas.")
    return pd.DataFrame(entradas)


# ── EXPORTACIONES ─────────────────────────────────────────────────────────────
def exportar_ris(df: pd.DataFrame, ruta: str) -> None:
    os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        for _, row in df.iterrows():
            for _, tag in FIELD_TO_TAG.items():
                value = row.get(tag)
                if isinstance(value, list):
                    for item in value:
                        if pd.notna(item) and str(item).strip():
                            f.write(f"{tag}  - {item}\n")
                elif pd.notna(value) and str(value).strip():
                    f.write(f"{tag}  - {value}\n")
            f.write("ER  - \n\n")
    logger.info(f"RIS exportado: {ruta} ({len(df)} registros)")


def exportar_log(registros: list[dict], ruta: str) -> None:
    os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
    if not registros:
        logger.info("Sin exclusiones registradas.")
        return
    pd.DataFrame(registros).to_csv(ruta, index=False, encoding="utf-8")
    logger.info(f"Log de exclusiones: {ruta} ({len(registros)} registros)")


# ── CLI ───────────────────────────────────────────────────────────────────────
def parsear_args():
    p = argparse.ArgumentParser(
        description="Prefiltrado por tipo de documento y año (RSL evaporación azucarera).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--input", "-i", default="output/fusion_export.ris",
                   help="Ruta al archivo RIS fusionado (salida del script 00).")
    p.add_argument("--output", "-o", default="output",
                   help="Carpeta donde se escriben Excel, RIS filtrado, log CSV y log de ejecución.")
    p.add_argument("--year-start", type=int, default=2015,
                   help="Año mínimo de publicación (inclusivo).")
    p.add_argument("--year-end",   type=int, default=2026,
                   help="Año máximo de publicación (inclusivo).")
    p.add_argument("--log-level", "-l", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                   help="Nivel de verbosidad del log.")
    return p.parse_args()


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    args = parsear_args()
    log_path = configurar_logging(args.output, args.log_level)

    excel_out = os.path.join(args.output, "1.prefiltrado.xlsx")
    ris_out   = os.path.join(args.output, "1.prefiltrado.ris")
    csv_log   = os.path.join(args.output, "1.exclusion_log.csv")

    logger.info("=" * 60)
    logger.info("PREFILTRADO — RSL EVAPORACIÓN AZUCARERA")
    logger.info(f"Tipo de documento + Año ({args.year_start}–{args.year_end})")
    logger.info("=" * 60)
    logger.info(f"Input RIS    : {args.input}")
    logger.info(f"Output folder: {args.output}")
    logger.info(f"Log file     : {log_path}")

    try:
        df = leer_ris(args.input)
    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(1)

    total_inicial = len(df)
    logger.info(f"Total inicial: {total_inicial}")
    if total_inicial == 0:
        logger.warning("El RIS no contiene entradas. Revisa la salida del script 00.")

    registros_excluidos = []

    # ── Filtro 1: Tipo de documento ───────────────────────────────────────
    col_tipo = None
    if "TY" in df.columns:
        col_tipo = "TY"
    elif "M3" in df.columns:
        col_tipo = "M3"
        logger.info("Fallback: usando campo M3 para tipo de documento.")

    if col_tipo:
        tipos_encontrados = df[col_tipo].dropna().unique().tolist()
        logger.info(f"Tipos encontrados en {col_tipo}: {tipos_encontrados}")

        if "DB" in df.columns:
            logger.debug("Distribución por base de datos:")
            for db, grp in df.groupby("DB", dropna=False):
                tipos_db = grp[col_tipo].dropna().unique().tolist()
                logger.debug(f"  {str(db):35} → {tipos_db}")

        mask_excluir = df[col_tipo].isin(TIPOS_EXCLUIDOS_TY)
        excluidos_tipo = df[mask_excluir]

        for _, row in excluidos_tipo.iterrows():
            registros_excluidos.append({
                "titulo"          : str(row.get("TI", ""))[:100],
                "anio"            : str(row.get("PY", "")),
                "revista"         : str(row.get("T2", ""))[:60],
                "doi"             : str(row.get("DO", "")),
                "base_datos"      : str(row.get("DB", "desconocida")),
                "tipo_documento"  : str(row.get(col_tipo, "sin tipo")),
                "motivo_exclusion": f"Tipo excluido: '{row.get(col_tipo,'?')}' — no es artículo de revista",
                "etapa"           : "Prefiltrado - Tipo",
            })

        df = df[~mask_excluir].copy()
        logger.info(f"Excluidos por tipo: {len(excluidos_tipo)}")
    else:
        logger.warning("No se encontró campo TY ni M3.")
        excluidos_tipo = pd.DataFrame()

    total_tras_tipo = len(df)
    n_excl_tipo = total_inicial - total_tras_tipo

    # ── Filtro 2: Año ─────────────────────────────────────────────────────
    if "PY" in df.columns:
        años_validos = [str(y) for y in range(args.year_start, args.year_end + 1)]
        mask_año = df["PY"].astype(str).isin(años_validos)
        excluidos_año = df[~mask_año]
        for _, row in excluidos_año.iterrows():
            registros_excluidos.append({
                "titulo"          : str(row.get("TI", ""))[:100],
                "anio"            : str(row.get("PY", "")),
                "revista"         : str(row.get("T2", ""))[:60],
                "doi"             : str(row.get("DO", "")),
                "motivo_exclusion": f"Año fuera del rango {args.year_start}-{args.year_end}: '{row.get('PY','sin año')}'",
                "etapa"           : "Prefiltrado - Año",
            })
        df = df[mask_año].copy()
        logger.info(f"Excluidos por año: {len(excluidos_año)}")
    else:
        logger.warning("No se encontró columna PY (año).")

    total_tras_año = len(df)
    n_excl_año = total_tras_tipo - total_tras_año

    # ── Exportar ──────────────────────────────────────────────────────────
    os.makedirs(args.output, exist_ok=True)
    df.to_excel(excel_out, index=False)
    logger.info(f"Excel exportado: {excel_out} ({len(df)} registros)")
    exportar_ris(df, ris_out)
    exportar_log(registros_excluidos, csv_log)

    # ── Reporte PRISMA ────────────────────────────────────────────────────
    logger.info("─" * 60)
    logger.info("NÚMEROS PARA DIAGRAMA PRISMA 2020")
    logger.info("─" * 60)
    logger.info(f"Registros identificados (multi-base) : {total_inicial}")
    logger.info(f"Excluidos por tipo fuente            : {n_excl_tipo}")
    logger.info(f"Excluidos por año                    : {n_excl_año}")
    logger.info(f"Tras prefiltrado                     : {total_tras_año}")
    logger.info(f"Log de exclusiones                   : {csv_log}")
    logger.info("→ Usar LOG como Apéndice A del paper")
    logger.info("=" * 60)
    logger.info("COMPLETADO → siguiente: python 02_fusion_scimago_scopus.py")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()