"""
02_fusion_scimago_scopus.py
==============================
ESTRATEGIAS DE MERGE (en orden de prioridad):
  1. ISSN primario normalizado     (campo SN)
  2. Todos los ISSNs del campo SN  (WoS puede poner varios)
  3. ISSN desde campo J2           (WoS a veces lo pone ahí)
  4. Título de revista normalizado (fallback)
  5. J2 como título alternativo

Uso:
  python 02_fusion_scimago_scopus.py
  python .\02_fusion_scimago_scopus.py `
    --input   ..\03_filtered_data\1.prefiltrado.ris `
    --scimago ..\01_raw_data\scimagojr_2024.xlsx `
    --output  ..\03_filtered_data
  python 02_fusion_scimago_scopus.py --log-level DEBUG
"""

import os
import re
import sys
import argparse
import logging
from datetime import datetime
from collections import Counter
import pandas as pd

logger = logging.getLogger("fusion_scimago")

FIELD_TO_TAG = {
    'Reference Type': 'TY', 'Title': 'TI', 'Secondary Title': 'T2',
    'Year': 'PY', 'Start Page': 'SP', 'End Page': 'EP', 'DOI': 'DO',
    'URLs': 'UR', 'Author Address': 'AD', 'Abstract': 'AB',
    'Keywords': 'KW', 'Publisher': 'PB', 'ISSN': 'SN', 'Language': 'LA',
    'Alternate Title': 'J2', 'Type of Work': 'M3', 'Name of Database': 'DB',
    'Notes': 'N1', 'Volume': 'VL', 'Number': 'IS', 'Custom 2': 'C2',
    'Short Title': 'ST', 'Author': 'AU', 'Secondary Author': 'A2',
    'Tertiary Author': 'A3', 'Editor': 'ED', 'Series Title': 'SE',
    'Translator': 'TR', 'Label': 'LB', 'Research Notes': 'RN',
    'Access Date': 'Y2', 'Database Provider': 'DP',
}


# ── LOGGING ───────────────────────────────────────────────────────────────────
def configurar_logging(output_folder: str, log_level: str) -> str:
    os.makedirs(output_folder, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(output_folder, f"fusion_scimago_{timestamp}.log")

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


# ── PARSERS ───────────────────────────────────────────────────────────────────
def leer_ris(filepath):
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
                    ex = entrada_actual[clave]
                    entrada_actual[clave] = (ex if isinstance(ex, list) else [ex]) + [valor]
                else:
                    entrada_actual[clave] = valor
    logger.debug(f"{filepath}: {len(entradas)} entradas parseadas.")
    return pd.DataFrame(entradas)


def norm_issn(raw) -> str:
    if not raw or (isinstance(raw, float) and pd.isna(raw)):
        return ""
    s = str(raw).strip().upper()
    s = re.sub(r"[^0-9X]", "", s)
    return s if len(s) in (7, 8) else ""


def extraer_todos_issn(campo_sn) -> list[str]:
    if not campo_sn or (isinstance(campo_sn, float) and pd.isna(campo_sn)):
        return []
    s = str(campo_sn)
    candidatos = re.findall(r'[0-9]{4}[-\s]?[0-9]{3}[0-9Xx]', s)
    result = []
    for c in candidatos:
        n = norm_issn(c)
        if n and n not in result:
            result.append(n)
    return result


def norm_titulo_revista(titulo) -> str:
    if not titulo or (isinstance(titulo, float) and pd.isna(titulo)):
        return ""
    s = str(titulo).upper().strip()
    s = re.sub(r'\s*\([^)]*\)\s*$', '', s)
    s = re.sub(r'^(THE|A|AN)\s+', '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


# ── SCIMAGO PREP ──────────────────────────────────────────────────────────────
def preparar_scimago(df_sci: pd.DataFrame) -> tuple[pd.DataFrame, list[str], list[str]]:
    df_sci.columns = [c.strip().lower() for c in df_sci.columns]

    sjr_cols = [c for c in ['sjr', 'sjr best quartile', 'h index'] if c in df_sci.columns]
    issn_cols = [c for c in df_sci.columns if 'issn' in c]
    logger.info(f"Columnas SCImago — ISSN: {issn_cols} | SJR: {sjr_cols}")

    df_sci['issn_norm']  = df_sci[issn_cols[0]].apply(norm_issn) if issn_cols else ""
    df_sci['eissn_norm'] = df_sci[issn_cols[1]].apply(norm_issn) if len(issn_cols) > 1 else ""

    if 'title' in df_sci.columns:
        df_sci['t2_norm'] = df_sci['title'].apply(norm_titulo_revista)

    return df_sci, sjr_cols, issn_cols


def construir_lookup_issn(df_sci: pd.DataFrame, sjr_cols: list) -> tuple:
    lookup_con_q = {}
    issns_sin_q  = set()

    for _, row in df_sci.iterrows():
        datos = {c: row.get(c) for c in sjr_cols}
        tiene_q = pd.notna(datos.get("sjr best quartile"))

        todos_issns = set()
        for col in ["issn_norm", "eissn_norm"]:
            v = row.get(col, "")
            if v:
                todos_issns.add(v)

        issn_raw = row.get("issn", "")
        if issn_raw:
            for parte in re.split(r"[;,\s]+", str(issn_raw)):
                n = norm_issn(parte.strip())
                if n:
                    todos_issns.add(n)

        for issn in todos_issns:
            if tiene_q:
                if issn not in lookup_con_q:
                    lookup_con_q[issn] = datos
            else:
                issns_sin_q.add(issn)

    return lookup_con_q, issns_sin_q


def construir_lookup_titulo(df_sci: pd.DataFrame, sjr_cols: list) -> dict:
    lookup = {}
    if 't2_norm' not in df_sci.columns:
        return lookup
    for _, row in df_sci.iterrows():
        datos = {c: row.get(c) for c in sjr_cols}
        if pd.isna(datos.get('sjr best quartile', float('nan'))):
            continue
        t = row.get('t2_norm', "")
        if t and t not in lookup:
            lookup[t] = datos
    return lookup


def asignar_cuartil_fila(row, lookup_issn, lookup_titulo, sjr_cols, issns_sin_q=None):
    issns = extraer_todos_issn(row.get('SN', ''))
    for issn in issns:
        if issn in lookup_issn:
            return lookup_issn[issn], f"ISSN:{issn}"

    issns_j2 = extraer_todos_issn(row.get('J2', ''))
    for issn in issns_j2:
        if issn in lookup_issn:
            return lookup_issn[issn], f"ISSN_J2:{issn}"

    t2 = norm_titulo_revista(row.get("T2", ""))
    if t2 and t2 in lookup_titulo:
        return lookup_titulo[t2], f"TITULO:{t2[:40]}"

    j2 = norm_titulo_revista(row.get("J2", ""))
    if j2 and j2 in lookup_titulo:
        return lookup_titulo[j2], f"J2_TITULO:{j2[:40]}"

    if issns_sin_q:
        for issn in issns:
            if issn in issns_sin_q:
                return {c: None for c in sjr_cols}, f"SIN_CUARTIL:{issn}"

    return {c: None for c in sjr_cols}, "SIN_MATCH_TOTAL"


# ── EXPORTACIONES ─────────────────────────────────────────────────────────────
def exportar_excel(df, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    df.to_excel(path, index=False)
    logger.info(f"Excel exportado: {path} ({len(df)} registros)")


def exportar_ris(df, path, sjr_cols):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        for _, row in df.iterrows():
            notas = []
            sjr_val = row.get('sjr')
            q_val   = row.get('sjr best quartile')
            if pd.notna(sjr_val):
                notas.append(f"SJR: {sjr_val}")
            if pd.notna(q_val):
                notas.append(f"SJR Best Quartile: {q_val}")

            for _, tag in FIELD_TO_TAG.items():
                if tag == 'N1':
                    for nota in notas:
                        f.write(f"N1  - {nota}\n")
                    continue
                value = row.get(tag)
                if isinstance(value, list):
                    for item in value:
                        if pd.notna(item) and str(item).strip():
                            f.write(f"{tag}  - {item}\n")
                elif pd.notna(value) and str(value).strip():
                    f.write(f"{tag}  - {value}\n")
            f.write("ER  - \n\n")
    logger.info(f"RIS exportado: {path} ({len(df)} registros)")


# ── CLI ───────────────────────────────────────────────────────────────────────
def parsear_args():
    p = argparse.ArgumentParser(
        description="Fusión RIS prefiltrado + SCImago (asignación de cuartiles Q1-Q4).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--input", "-i", default="output/1.prefiltrado.ris",
                   help="RIS prefiltrado de entrada (salida del script 01).")
    p.add_argument("--scimago", "-s", default="01_raw_data/scimagojr_2024.xlsx",
                   help="Excel de SCImago con ranking de revistas.")
    p.add_argument("--output", "-o", default="output",
                   help="Carpeta de salida (Excel, RIS, sin_match.xlsx y log).")
    p.add_argument("--log-level", "-l", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                   help="Nivel de verbosidad.")
    return p.parse_args()


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    args = parsear_args()
    log_path = configurar_logging(args.output, args.log_level)

    excel_out      = os.path.join(args.output, "2.fusionado_con_cuartiles.xlsx")
    ris_out        = os.path.join(args.output, "2.fusionado_con_cuartiles.ris")
    sin_match_xlsx = os.path.join(args.output, "2b.sin_match_scimago.xlsx")

    logger.info("=" * 60)
    logger.info("FUSIÓN RIS + SCIMAGO — MULTI-ESTRATEGIA (5 métodos)")
    logger.info("Compatible: Scopus + WoS + IEEE Xplore")
    logger.info("=" * 60)
    logger.info(f"Input RIS    : {args.input}")
    logger.info(f"SCImago xlsx : {args.scimago}")
    logger.info(f"Output folder: {args.output}")
    logger.info(f"Log file     : {log_path}")

    try:
        df_ris = leer_ris(args.input)
    except (FileNotFoundError, IsADirectoryError) as e:
        logger.error(str(e))
        sys.exit(1)

    total = len(df_ris)
    logger.info(f"Registros RIS de entrada: {total}")
    if total == 0:
        logger.warning("RIS de entrada vacío. Revisa la salida del script 01.")

    if 'DB' in df_ris.columns:
        logger.info("Bases de datos en el RIS:")
        for db, n in df_ris['DB'].value_counts().items():
            logger.info(f"  {str(db):35} : {n}")

    if not os.path.exists(args.scimago):
        logger.error(f"No se encontró el Excel SCImago: {args.scimago}")
        sys.exit(1)

    logger.info(f"Cargando SCImago: {args.scimago}")
    df_sci = pd.read_excel(args.scimago)
    logger.info(f"Registros SCImago: {len(df_sci):,}")

    df_sci, sjr_cols, _ = preparar_scimago(df_sci)

    lookup_issn, issns_sin_q = construir_lookup_issn(df_sci, sjr_cols)
    lookup_titulo = construir_lookup_titulo(df_sci, sjr_cols)
    logger.info(f"Lookup ISSN  : {len(lookup_issn):,} entradas")
    logger.info(f"Lookup título: {len(lookup_titulo):,} entradas")

    logger.info("Asignando cuartiles...")
    metodos_usados = []
    for col in sjr_cols:
        df_ris[col] = None

    for idx, row in df_ris.iterrows():
        datos, metodo = asignar_cuartil_fila(
            row, lookup_issn, lookup_titulo, sjr_cols, issns_sin_q
        )
        for col in sjr_cols:
            df_ris.at[idx, col] = datos.get(col)
        metodos_usados.append(metodo)

    df_ris['_merge_metodo'] = metodos_usados

    # ── Reporte ───────────────────────────────────────────────────────────
    def categoria(m):
        if m.startswith("ISSN:"):       return "ISSN"
        if m.startswith("ISSN_J2"):     return "ISSN_J2"
        if m.startswith("TITULO"):      return "TITULO"
        if m.startswith("J2_TITULO"):   return "J2_TITULO"
        if m.startswith("SIN_CUARTIL"): return "SIN_CUARTIL"
        return "SIN_MATCH_TOTAL"

    conteo = Counter(categoria(m) for m in metodos_usados)
    sin_match_categorias = {"SIN_CUARTIL", "SIN_MATCH_TOTAL"}
    con_cuartil = sum(1 for m in metodos_usados if categoria(m) not in sin_match_categorias)
    sin_cuartil = total - con_cuartil

    logger.info("─" * 60)
    logger.info("COBERTURA DEL MERGE")
    logger.info("─" * 60)
    pct_con = (100 * con_cuartil / total) if total else 0.0
    pct_sin = (100 * sin_cuartil / total) if total else 0.0
    logger.info(f"Con cuartil asignado  : {con_cuartil} / {total} ({pct_con:.1f}%)")
    logger.info(f"Sin cuartil (no match): {sin_cuartil} ({pct_sin:.1f}%)")
    logger.info("Método usado:")
    for metodo, n in sorted(conteo.items(), key=lambda x: -x[1]):
        logger.info(f"  {metodo:15} : {n}")

    # ── Sin match — diagnóstico y export ──────────────────────────────────
    mask_sin = pd.Series(
        [categoria(m) in sin_match_categorias for m in metodos_usados],
        index=df_ris.index,
    )
    cols_sin_match = [c for c in ['TI', 'T2', 'J2', 'SN', 'DB', 'PY', '_merge_metodo']
                      if c in df_ris.columns]
    df_sin = df_ris[mask_sin][cols_sin_match].copy()

    n_sin_cuartil_scimago = conteo.get("SIN_CUARTIL", 0)
    n_sin_match_total     = conteo.get("SIN_MATCH_TOTAL", 0)

    if sin_cuartil > 0:
        logger.warning(f"{sin_cuartil} artículos sin cuartil asignado:")
        logger.warning(f"  CASO B — Revista en SCImago pero sin cuartil : {n_sin_cuartil_scimago}")
        logger.warning(f"  CASO A — Revista no encontrada en SCImago    : {n_sin_match_total}")

        for caso, prefijo in [("CASO B — En SCImago, sin cuartil", "SIN_CUARTIL"),
                              ("CASO A — No encontrada en SCImago", "SIN_MATCH_TOTAL")]:
            idx_caso = [i for i, m in zip(df_ris.index, metodos_usados)
                        if m.startswith(prefijo)]
            if idx_caso:
                logger.info(caso + ":")
                for idx in idx_caso[:5]:
                    r = df_ris.loc[idx]
                    issns = extraer_todos_issn(str(r.get("SN", "")))
                    logger.info(f"  • {str(r.get('T2',''))[:50]}")
                    logger.info(f"    ISSN: {issns if issns else 'sin ISSN'}")
                if len(idx_caso) > 5:
                    logger.info(f"  ... y {len(idx_caso)-5} más")

        logger.info("ACCIONES RECOMENDADAS:")
        if n_sin_cuartil_scimago > 0:
            logger.info("  CASO B: revista en SCImago sin cuartil este año.")
            logger.info("          → Verificar en scimagojr.com en otro año / agregar manual.")
        if n_sin_match_total > 0:
            logger.info("  CASO A: revista NO está en scimagojr_2024.xlsx.")
            logger.info("          → Verificar ISSN exacto; puede ser revista nueva.")

        df_sin.to_excel(sin_match_xlsx, index=False)
        logger.info(f"Detalle sin match exportado: {sin_match_xlsx}")

    # ── Export final ──────────────────────────────────────────────────────
    df_export = df_ris.drop(columns=['_merge_metodo'], errors='ignore')
    exportar_excel(df_export, excel_out)
    exportar_ris(df_export, ris_out, sjr_cols)

    logger.info(f"Registros RIS de salida: {len(df_export)}")
    logger.info("=" * 60)
    logger.info("COMPLETADO")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
