"""
03_filtrado_quartiles.py
===========================
RSL: Filtrado por cuartiles SCImago (Q1-Q4 por defecto).

Doble estrategia de detección de cuartil:
  1. Columna explícita 'sjr best quartile' (salida del script 02)
  2. Regex en campo N1 (fallback con versiones antiguas del script 02)

Uso:
  python 03_filtrado_quartiles.py
  python 03_filtrado_quartiles.py --input ..\03_filtered_data\2.fusionado_con_cuartiles.ris \
                                  --output ..\03_filtered_data
  python 03_filtrado_quartiles.py --quartiles Q1 Q2 Q3 --log-level DEBUG
"""

import os
import re
import sys
import argparse
import logging
from datetime import datetime
import pandas as pd

logger = logging.getLogger("filtrado_q")

FIELD_TO_TAG = {
    'Reference Type': 'TY', 'Title': 'TI', 'Secondary Title': 'T2',
    'Year': 'PY', 'Start Page': 'SP', 'End Page': 'EP', 'DOI': 'DO',
    'URLs': 'UR', 'Author Address': 'AD', 'Abstract': 'AB',
    'Keywords': 'KW', 'Publisher': 'PB', 'ISSN': 'SN', 'Language': 'LA',
    'Alternate Title': 'J2', 'Type of Work': 'M3', 'Name of Database': 'DB',
    'Notes': 'N1', 'Volume': 'VL', 'Number': 'IS', 'Custom 7': 'C7',
    'Custom 2': 'C2', 'Short Title': 'ST', 'Author': 'AU',
    'Secondary Author': 'A2', 'Tertiary Author': 'A3', 'Editor': 'ED',
    'Series Title': 'SE', 'Translator': 'TR', 'Label': 'LB',
    'Research Notes': 'RN', 'Access Date': 'Y2', 'Database Provider': 'DP',
}


# ── LOGGING ───────────────────────────────────────────────────────────────────
def configurar_logging(output_folder: str, log_level: str) -> str:
    os.makedirs(output_folder, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(output_folder, f"filtrado_quartiles_{timestamp}.log")

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


# ── PARSER RIS ────────────────────────────────────────────────────────────────
def leer_ris(filepath: str) -> pd.DataFrame:
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"No se encontró: {filepath}")
    if os.path.isdir(filepath):
        raise IsADirectoryError(f"--input debe ser un archivo .ris, no carpeta: {filepath}")

    entradas, entrada_actual = [], {}
    with open(filepath, 'r', encoding='utf-8') as f:
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


# ── DETECCIÓN DE CUARTIL ──────────────────────────────────────────────────────
def extraer_cuartil_de_n1(n1_val) -> str:
    if not n1_val or (isinstance(n1_val, float) and pd.isna(n1_val)):
        return ''
    texto = " ".join(n1_val) if isinstance(n1_val, list) else str(n1_val)
    m = re.search(r'SJR Best Quartile:\s*(Q[1-4])', texto, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    m2 = re.search(r'\b(Q[1-4])\b', texto, re.IGNORECASE)
    if m2:
        return m2.group(1).upper()
    return ''


def determinar_cuartil(row: pd.Series) -> tuple[str, str]:
    for col_name in ['sjr_best_quartile', 'sjr best quartile', 'SJR Best Quartile']:
        if col_name in row.index:
            val = row.get(col_name)
            if pd.notna(val) and str(val).strip():
                q = str(val).strip().upper()
                if re.match(r'^Q[1-4]$', q):
                    return q, 'columna_explicita'

    q = extraer_cuartil_de_n1(row.get('N1', ''))
    if q:
        return q, 'regex_N1'

    return '', 'sin_cuartil'


def filtrar_por_cuartil(df: pd.DataFrame, cuartiles_validos: set) -> tuple:
    cuartiles, metodos = [], []
    for _, row in df.iterrows():
        q, metodo = determinar_cuartil(row)
        cuartiles.append(q)
        metodos.append(metodo)

    df = df.copy()
    df['_cuartil_detectado'] = cuartiles
    df['_metodo_deteccion']  = metodos

    logger.info("Distribución de cuartiles detectados:")
    for q, n in sorted(df['_cuartil_detectado'].value_counts().items()):
        label = q if q else '(sin cuartil)'
        logger.info(f"  {label:15} : {n}")

    logger.info("Método de detección usado:")
    for m, n in df['_metodo_deteccion'].value_counts().items():
        logger.info(f"  {m:20} : {n}")

    mask_valido = df['_cuartil_detectado'].isin(cuartiles_validos)
    mask_sin_q  = df['_cuartil_detectado'] == ''
    mask_excl_q = ~mask_valido & ~mask_sin_q

    return df[mask_valido].copy(), df[mask_excl_q].copy(), df[mask_sin_q].copy()


# ── EXPORTACIONES ─────────────────────────────────────────────────────────────
def exportar_log_excluidos(df_excl, df_sin_q, ruta, cuartiles_validos):
    filas = []
    for _, row in df_excl.iterrows():
        q = row.get('_cuartil_detectado', '?')
        filas.append({
            'titulo'           : str(row.get('TI', ''))[:100],
            'anio'             : str(row.get('PY', '')),
            'revista'          : str(row.get('T2', ''))[:60],
            'doi'              : str(row.get('DO', '')),
            'cuartil_detectado': q,
            'metodo_deteccion' : row.get('_metodo_deteccion', ''),
            'motivo_exclusion' : f"Cuartil {q} — fuera de {'/'.join(sorted(cuartiles_validos))}",
            'etapa'            : 'Filtrado cuartiles',
        })
    for _, row in df_sin_q.iterrows():
        filas.append({
            'titulo'           : str(row.get('TI', ''))[:100],
            'anio'             : str(row.get('PY', '')),
            'revista'          : str(row.get('T2', ''))[:60],
            'doi'              : str(row.get('DO', '')),
            'cuartil_detectado': '',
            'metodo_deteccion' : row.get('_metodo_deteccion', ''),
            'motivo_exclusion' : 'Sin cuartil SCImago asignado (revista no encontrada en SCImago)',
            'etapa'            : 'Filtrado cuartiles',
        })

    if filas:
        os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
        pd.DataFrame(filas).to_csv(ruta, index=False, encoding='utf-8')
        logger.info(f"Log de excluidos: {ruta} ({len(filas)} registros)")
    else:
        logger.info("Sin exclusiones registradas.")


def guardar_excel(df: pd.DataFrame, ruta: str) -> None:
    os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
    df_export = df.drop(
        columns=[c for c in ['_cuartil_detectado', '_metodo_deteccion'] if c in df.columns],
        errors='ignore',
    )
    df_export.to_excel(ruta, index=False)
    logger.info(f"Excel exportado: {ruta} ({len(df_export)} registros)")


def exportar_ris(df: pd.DataFrame, ruta: str) -> None:
    os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
    with open(ruta, 'w', encoding='utf-8') as f:
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


# ── CLI ───────────────────────────────────────────────────────────────────────
def parsear_args():
    p = argparse.ArgumentParser(
        description="Filtrado por cuartiles SCImago (Q1-Q4 por defecto).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--input", "-i", default="output/2.fusionado_con_cuartiles.ris",
                   help="RIS con cuartiles asignados (salida del script 02).")
    p.add_argument("--output", "-o", default="output",
                   help="Carpeta de salida (Excel, RIS, log CSV y log de ejecución).")
    p.add_argument("--quartiles", "-q", nargs="+", default=["Q1", "Q2", "Q3", "Q4"],
                   choices=["Q1", "Q2", "Q3", "Q4"],
                   help="Cuartiles aceptados.")
    p.add_argument("--log-level", "-l", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                   help="Nivel de verbosidad.")
    return p.parse_args()


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    args = parsear_args()
    log_path = configurar_logging(args.output, args.log_level)

    excel_out     = os.path.join(args.output, "3.filtrado_quartiles.xlsx")
    ris_out       = os.path.join(args.output, "3.filtrado_quartiles.ris")
    log_excluidos = os.path.join(args.output, "3.excluidos_cuartil.csv")
    sin_match_out = os.path.join(args.output, "3.sin_cuartil_asignado.xlsx")

    cuartiles_validos = {q.upper() for q in args.quartiles}

    logger.info("=" * 60)
    logger.info("FILTRADO POR CUARTIL — DOBLE ESTRATEGIA (columna + regex N1)")
    logger.info("=" * 60)
    logger.info(f"Input RIS         : {args.input}")
    logger.info(f"Output folder     : {args.output}")
    logger.info(f"Cuartiles válidos : {sorted(cuartiles_validos)}")
    logger.info(f"Log file          : {log_path}")

    try:
        df = leer_ris(args.input)
    except (FileNotFoundError, IsADirectoryError) as e:
        logger.error(str(e))
        sys.exit(1)

    total_inicial = len(df)
    logger.info(f"Registros de entrada: {total_inicial}")
    if total_inicial == 0:
        logger.warning("RIS de entrada vacío. Revisa la salida del script 02.")

    cols_explicitas = [c for c in df.columns
                       if 'quartile' in str(c).lower() or 'cuartil' in str(c).lower()]
    if cols_explicitas:
        logger.info(f"Columnas de cuartil detectadas: {cols_explicitas}")
        logger.info("Modo: columna explícita (script 02 nuevo)")
    else:
        logger.info("Modo: regex en N1 (fallback)")

    df_validos, df_excl_cuart, df_sin_cuartil = filtrar_por_cuartil(df, cuartiles_validos)

    n_validos     = len(df_validos)
    n_excl_cuart  = len(df_excl_cuart)
    n_sin_cuartil = len(df_sin_cuartil)

    logger.info("─" * 60)
    logger.info("RESULTADOS")
    logger.info("─" * 60)
    logger.info(f"Aceptados ({'/'.join(sorted(cuartiles_validos))}) : {n_validos}")
    logger.info(f"Excluidos por cuartil fuera de rango : {n_excl_cuart}")
    logger.info(f"Sin cuartil asignado                 : {n_sin_cuartil}")
    logger.info(f"Total                                : {n_validos + n_excl_cuart + n_sin_cuartil}")

    if n_sin_cuartil > 0:
        logger.warning(f"{n_sin_cuartil} artículos sin cuartil SCImago.")
        logger.warning(f"Revisar manualmente: {sin_match_out}")
        cols_export = [c for c in ['TI', 'T2', 'SN', 'PY', 'DO'] if c in df_sin_cuartil.columns]
        df_sin_cuartil[cols_export].to_excel(sin_match_out, index=False)

    guardar_excel(df_validos, excel_out)
    exportar_ris(df_validos, ris_out)
    exportar_log_excluidos(df_excl_cuart, df_sin_cuartil, log_excluidos, cuartiles_validos)

    logger.info("─" * 60)
    logger.info("NÚMEROS PARA DIAGRAMA PRISMA 2020")
    logger.info("─" * 60)
    logger.info(f"Entrada (tras prefiltrado)    : {total_inicial}")
    logger.info(f"Excluidos por cuartil         : {n_excl_cuart}")
    logger.info(f"Excluidos sin cuartil SCImago : {n_sin_cuartil}")
    logger.info(f"Aceptados para cribado        : {n_validos}")
    logger.info(f"Log de exclusiones            : {log_excluidos}")
    logger.info("=" * 60)
    logger.info("COMPLETADO")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()