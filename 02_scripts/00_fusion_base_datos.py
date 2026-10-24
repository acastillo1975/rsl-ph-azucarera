"""
00_fusion_base_datos.py
==========================
Fusión multi-fuente + deduplicación robusta
Uso:
  python 00_fusion_base_datos.py
  python 00_fusion_base_datos.py --input ..\01_raw_data --output ..\01_raw_data
  python 00_fusion_base_datos.py --input 01_raw_data --output 01_raw_data --fuzzy 95
  python 00_fusion_base_datos.py --log-level DEBUG
  python 00_fusion_base_datos.py --sources Scopus:01_raw_data/scopus_export_1.ris \
                                           WoS:01_raw_data/wos_export_1.ris

"""

import os
import re
import csv
import sys
import argparse
import logging
from datetime import datetime
from collections import defaultdict

try:
    from rapidfuzz import fuzz
    FUZZY_AVAILABLE = True
except ImportError:
    FUZZY_AVAILABLE = False

# ── FUENTES POR DEFECTO ───────────────────────────────────────────────────────
DEFAULT_SOURCES = [
    {"path": "scopus_export_1.ris", "db": "Scopus"},
    {"path": "scopus_export_2.ris", "db": "Scopus"},
    {"path": "scopus_export_3.ris", "db": "Scopus"},
    {"path": "wos_export_1.ris",    "db": "WoS"},
    {"path": "wos_export_2.ris",    "db": "WoS"},
    {"path": "wos_export_3.ris",    "db": "WoS"},
    {"path": "ieee_export_1.ris",   "db": "IEEE Xplore"},
    {"path": "ieee_export_2.ris",   "db": "IEEE Xplore"},
    {"path": "ieee_export_3.ris",   "db": "IEEE Xplore"},
]

logger = logging.getLogger("fusion_rsl")


# ── LOGGING ───────────────────────────────────────────────────────────────────
def configurar_logging(output_folder: str, log_level: str) -> str:
    """Configura logger con salida a consola y archivo con timestamp.
    Retorna el path del archivo log."""
    os.makedirs(output_folder, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(output_folder, f"fusion_{timestamp}.log")

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


# ── NORMALIZACIÓN ─────────────────────────────────────────────────────────────
def normalizar_doi(doi_raw: str) -> str:
    if not doi_raw:
        return ""
    doi = str(doi_raw).strip().lower()
    doi = re.sub(r"^https?://doi\.org/", "", doi)
    doi = re.sub(r"\s+", "", doi)
    return doi


def normalizar_titulo(titulo: str) -> str:
    t = str(titulo).strip().lower()
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


# ── PARSEO RIS ────────────────────────────────────────────────────────────────
def procesar_ris(filepath: str, db_name: str) -> list[dict]:
    if not os.path.exists(filepath):
        logger.warning(f"No se encontró {filepath} — omitiendo.")
        return []

    entradas = []
    lineas_actuales = []
    with open(filepath, "r", encoding="utf-8-sig") as f:
        for linea in f:
            linea = linea.replace("\ufeff", "")
            if linea.strip() == "ER  -":
                lineas_actuales.append(linea)
                entradas.append(_parsear_entrada(lineas_actuales, db_name))
                lineas_actuales = []
            else:
                lineas_actuales.append(linea)
    logger.debug(f"{filepath}: {len(entradas)} entradas parseadas.")
    return entradas


def _parsear_entrada(lineas: list[str], db_name: str) -> dict:
    campos = {"_lineas": lineas, "_db": db_name,
              "TI": "", "AU": "", "PY": "", "DO": "", "T2": ""}
    for linea in lineas:
        if linea.startswith("TI  - "):
            campos["TI"] = linea[6:].strip()
        elif linea.startswith("AU  - ") and not campos["AU"]:
            campos["AU"] = linea[6:].strip()
        elif linea.startswith("PY  - "):
            campos["PY"] = linea[6:].strip()
        elif linea.startswith("DO  - "):
            campos["DO"] = normalizar_doi(linea[6:].strip())
        elif linea.startswith("T2  - "):
            campos["T2"] = linea[6:].strip()
    return campos


# ── DEDUPLICACIÓN ─────────────────────────────────────────────────────────────
def deduplicar(todas: list[dict], fuzzy_threshold: int) -> tuple[list[dict], list[dict]]:
    unicos, duplicados = [], []
    doi_visto = {}
    titulos_normalizados = []

    for entrada in todas:
        doi = entrada["DO"]
        titulo_norm = normalizar_titulo(entrada["TI"])

        if doi:
            if doi in doi_visto:
                entrada["_dup_motivo"] = f"DOI duplicado: {doi}"
                duplicados.append(entrada)
                logger.debug(f"DUP[DOI] {entrada['TI'][:60]}")
                continue
            doi_visto[doi] = len(unicos)
        elif FUZZY_AVAILABLE and titulo_norm:
            es_dup = False
            for t_existente in titulos_normalizados:
                ratio = fuzz.ratio(titulo_norm, t_existente)
                if ratio >= fuzzy_threshold:
                    entrada["_dup_motivo"] = f"Título similar ({ratio}%): '{t_existente[:60]}'"
                    duplicados.append(entrada)
                    logger.debug(f"DUP[FUZZY {ratio}%] {entrada['TI'][:60]}")
                    es_dup = True
                    break
            if es_dup:
                continue

        unicos.append(entrada)
        titulos_normalizados.append(titulo_norm)

    return unicos, duplicados


# ── EXPORTACIÓN ───────────────────────────────────────────────────────────────
def escribir_ris(entradas: list[dict], filepath: str) -> None:
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        for entrada in entradas:
            f.writelines(entrada["_lineas"])
            f.write("\n\n")
    logger.info(f"Escrito: {filepath} ({len(entradas)} registros)")


def exportar_reporte(todas, unicos, duplicados, filepath):
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    conteo = defaultdict(int)
    for e in todas:
        conteo[e["_db"]] += 1

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["REPORTE DE FUSIÓN — RSL EVAPORACIÓN AZUCARERA"])
        w.writerow([])
        w.writerow(["Fuente", "Total"])
        for db, n in sorted(conteo.items()):
            w.writerow([db, n])
        w.writerow(["TOTAL CON DUPLICADOS", len(todas)])
        w.writerow(["TOTAL ÚNICOS", len(unicos)])
        w.writerow(["DUPLICADOS ELIMINADOS", len(duplicados)])
        w.writerow([])
        w.writerow(["DETALLE DUPLICADOS"])
        w.writerow(["Título", "Año", "DOI", "Fuente", "Motivo"])
        for d in duplicados:
            w.writerow([d["TI"][:80], d["PY"], d["DO"], d["_db"], d.get("_dup_motivo", "")])

    logger.info(f"Reporte exportado: {filepath}")


# ── CLI ───────────────────────────────────────────────────────────────────────
def parsear_args():
    p = argparse.ArgumentParser(
        description="Fusión y deduplicación de exports RIS (Scopus / WoS / IEEE).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--input", "-i", default="01_raw_data",
                   help="Carpeta con los archivos .ris de entrada.")
    p.add_argument("--output", "-o", default="output",
                   help="Carpeta donde se escriben RIS fusionados, reporte CSV y log.")
    p.add_argument("--fuzzy", "-f", type=int, default=95,
                   help="Umbral %% similitud fuzzy en título (0-100).")
    p.add_argument("--log-level", "-l", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                   help="Nivel de verbosidad del log.")
    p.add_argument("--sources", "-s", nargs="+", default=None,
                   metavar="DB:PATH",
                   help="Sobrescribe las fuentes por defecto. "
                        "Formato: Scopus:ruta/archivo.ris (paths absolutos o relativos a --input).")
    return p.parse_args()


def resolver_sources(args) -> list[dict]:
    if args.sources:
        out = []
        for s in args.sources:
            if ":" not in s:
                logger.error(f"Fuente mal formada (esperado DB:PATH): {s}")
                continue
            db, path = s.split(":", 1)
            if not os.path.isabs(path):
                path = os.path.join(args.input, path) if not path.startswith(args.input) else path
            out.append({"db": db.strip(), "path": path.strip()})
        return out
    # Default: prefija los nombres con la carpeta input
    return [{"db": s["db"], "path": os.path.join(args.input, s["path"])}
            for s in DEFAULT_SOURCES]


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    args = parsear_args()
    log_path = configurar_logging(args.output, args.log_level)

    logger.info("=" * 65)
    logger.info("FUSIÓN MULTI-FUENTE + DEDUPLICACIÓN — EVAPORACIÓN AZUCARERA")
    logger.info("=" * 65)
    logger.info(f"Input folder : {args.input}")
    logger.info(f"Output folder: {args.output}")
    logger.info(f"Fuzzy thr.   : {args.fuzzy}%  | rapidfuzz disponible: {FUZZY_AVAILABLE}")
    logger.info(f"Log file     : {log_path}")

    if not FUZZY_AVAILABLE:
        logger.warning("rapidfuzz no instalado (pip install rapidfuzz). Dedup solo por DOI.")

    sources = resolver_sources(args)
    todas = []
    for src in sources:
        entradas = procesar_ris(src["path"], src["db"])
        todas.extend(entradas)
        logger.info(f"  {src['db']:15} | {os.path.basename(src['path']):35} | {len(entradas):4} registros")

    logger.info(f"Total con duplicados: {len(todas)}")

    out_all    = os.path.join(args.output, "fusion_export_all.ris")
    out_unique = os.path.join(args.output, "fusion_export.ris")
    out_report = os.path.join(args.output, "00_fusion_report.csv")

    escribir_ris(todas, out_all)
    unicos, duplicados = deduplicar(todas, args.fuzzy)
    logger.info(f"Duplicados eliminados: {len(duplicados)}")
    logger.info(f"Total únicos         : {len(unicos)}")

    escribir_ris(unicos, out_unique)
    exportar_reporte(todas, unicos, duplicados, out_report)

    logger.info("=" * 65)
    logger.info("COMPLETADO → siguiente: python 01_prefiltrado_basico.py")
    logger.info("=" * 65)


if __name__ == "__main__":
    main()