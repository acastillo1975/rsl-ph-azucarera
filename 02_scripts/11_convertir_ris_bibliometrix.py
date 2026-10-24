#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
11_convertir_ris_bibliometrix.py
================================
Script UNICO que toma un RIS fusionado (Scopus + WoS/IEEE + cuartiles de
journal) y produce lo necesario para analizarlo en bibliometrix / Biblioshiny:

    1. Un BibTeX (.bib) limpio y homogeneizado  <-- salida principal, cargable
       en Biblioshiny con Database = Scopus.
    2. (Opcional) El RIS limpio intermedio, con --ris.
    3. Un Excel con el mapeo revista -> cuartil -> SJR, para cruzarlo despues.
    4. Un log narrativo (consola + archivo) que describe cada paso.

POR QUE BIBTEX Y NO RIS:
    bibliometrix NO soporta RIS para la fuente Scopus. Solo acepta Scopus en
    BibTeX (.bib) o CSV. Cargar un RIS da "Number of Documents 0" y el error
    "objeto 'M' no encontrado". Por eso la salida principal es .bib.
    Fuente: vignette oficial de bibliometrix y codigo de convert2df
    (allowed_formats: api, bibtex, csv, endnote, excel, plaintext, pubmed --
    no incluye 'ris').

USO:
    python3 11_convertir_ris_bibliometrix.py ENTRADA.ris [opciones]
    python3 11_convertir_ris_bibliometrix.py -i ENTRADA.ris [opciones]

    La entrada admite tres formas equivalentes:
        script.py archivo.ris          (posicional)
        script.py -i archivo.ris       (bandera corta)
        script.py --input archivo.ris  (bandera larga)

    Opciones:
        -o, --output SALIDA.bib   BibTeX de salida (por defecto: *_biblio.bib)
        --ris [RIS_LIMPIO.ris]    Ademas, guardar el RIS limpio intermedio
        -x, --xlsx  MAPEO.xlsx    Excel de cuartiles (por defecto: cuartiles_mapeo.xlsx)
        -l, --log   ARCHIVO.log   Archivo de log (por defecto: conversion.log)
        -v, --verbose             Detalle registro por registro en consola

EJEMPLO:
    python3 11_convertir_ris_bibliometrix.py -i 3_filtrado_quartiles.ris \\
        -o 3_filtrado_quartiles_biblio.bib \\
        --ris 3_filtrado_quartiles_LIMPIO.ris \\
        -x cuartiles_mapeo.xlsx -l conversion.log -v

TRANSFORMACIONES (todas verificables sobre el archivo de entrada):
    - Cuartil y SJR viven en etiquetas N1 no estandar: se extraen a columnas
      propias (Excel) y a campos personalizados del .bib (sjr_quartile, sjr).
    - SJR en formato europeo mal exportado: '0,587' -> 0.587 ; '1928' -> 1.928
      (los valores sin coma empiezan en 1000+, coherente con SJR real 1.x-3.x).
    - Registros no-Scopus (WoS/IEEE): ISSN sin guion ni sufijo; titulo de
      revista en MAYUSCULAS convertido a Title Case, protegiendo siglas
      conocidas (lista blanca ACRONIMOS_REVISTA).
    - Registros sin AU: se inserta 'AU  - [No author name available]'.
    - Se descarta cualquier bloque ER huerfano (sin TY) residual de la fusion.

LIMITACION CONOCIDA: la deteccion de siglas de revista es por lista blanca; no
hay forma 100% fiable por reglas de distinguir una sigla de una palabra comun en
mayusculas. Para un merge posterior use el ISSN como llave (deterministico), no
el nombre de revista. La validacion aqui es estructural: NO se ejecuta convert2df
(no requiere R); confirme el conteo de documentos al importar en Biblioshiny.
"""

import argparse
import csv
import logging
import re
import sys
from pathlib import Path

try:
    import openpyxl
except ImportError:
    sys.stderr.write(
        "ERROR: falta el paquete 'openpyxl'. Instalelo con:\n"
        "    pip install openpyxl\n"
    )
    sys.exit(1)


# --------------------------------------------------------------------------- #
# Constantes
# --------------------------------------------------------------------------- #
# Siglas de revistas que deben conservarse en mayusculas. Ampliable.
ACRONIMOS_REVISTA = {
    "LWT", "PLOS", "IEEE", "ACS", "RSC", "AIP", "ASME", "AIAA", "IET",
    "IFAC", "SPE", "MDPI", "PLOS ONE", "AICHE", "JMLR", "NPJ",
}

# Tipo de documento RIS/Scopus -> tipo de entrada BibTeX
TIPO_ENTRADA = {
    "JOUR": "ARTICLE",
    "CONF": "CONFERENCE",
    "CPAPER": "CONFERENCE",
    "CHAP": "INCOLLECTION",
    "BOOK": "BOOK",
    "RPRT": "TECHREPORT",
}


# --------------------------------------------------------------------------- #
# Logger narrativo
# --------------------------------------------------------------------------- #
def configurar_logger(ruta_log: Path, verboso: bool) -> logging.Logger:
    logger = logging.getLogger("convertir_ris")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s [%(levelname)-7s] %(message)s",
                            datefmt="%H:%M:%S")
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG if verboso else logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    fh = logging.FileHandler(ruta_log, mode="w", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    return logger


# --------------------------------------------------------------------------- #
# Utilidades de transformacion
# --------------------------------------------------------------------------- #
def normalizar_sjr(val: str, logger: logging.Logger):
    """'0,587'->0.587 ; '1928'->1.928 ; None si no se puede parsear."""
    val = val.strip()
    if "," in val:
        try:
            return round(float(val.replace(",", ".")), 3)
        except ValueError:
            logger.warning("      SJR con coma no parseable: %r", val)
            return None
    if val.isdigit():
        if len(val) >= 4:  # 1928 -> 1.928
            return round(float(val[0] + "." + val[1:]), 3)
        try:
            return float(val)
        except ValueError:
            return None
    logger.warning("      SJR con formato inesperado: %r", val)
    return None


def a_title_case_revista(titulo: str) -> str:
    """Pasa un titulo de revista en MAYUSCULAS a Title Case, protegiendo siglas.

    - Solo actua si el titulo viene mayormente en mayusculas (>=80% de letras).
    - Un titulo de una sola palabra en mayusculas se deja intacto (probable sigla).
    - Palabras en la lista blanca ACRONIMOS_REVISTA se conservan en mayusculas.
    """
    letras = [c for c in titulo if c.isalpha()]
    if not letras:
        return titulo
    ratio_mayus = sum(1 for c in letras if c.isupper()) / len(letras)
    palabras = titulo.split()
    if ratio_mayus < 0.8:
        return titulo
    if len(palabras) == 1:
        return titulo
    menores = {"of", "and", "the", "for", "in", "on", "to", "a", "an", "with",
               "de", "la", "el", "&"}
    salida = []
    for i, w in enumerate(palabras):
        limpio = "".join(c for c in w if c.isalnum()).upper()
        if limpio in ACRONIMOS_REVISTA:
            salida.append(w)
            continue
        wl = w.lower()
        if i != 0 and wl in menores:
            salida.append(wl)
        else:
            salida.append(wl[:1].upper() + wl[1:])
    return " ".join(salida)


def separar_registros(texto: str):
    """Divide el texto RIS en bloques con TY..ER (descarta ER huerfanos)."""
    bloques, buffer = [], []
    for linea in texto.split("\n"):
        buffer.append(linea)
        if linea.startswith("ER  -"):
            bloque = "\n".join(buffer)
            if "TY  -" in bloque:
                bloques.append(bloque)
            buffer = []
    return bloques


def escapar_bibtex(texto: str) -> str:
    """Protege llaves sueltas que romperian el parseo BibTeX."""
    return texto.replace("{", "(").replace("}", ")")


def clave_cita(campos, usadas):
    """Clave de cita unica ApellidoAnioN; salta prefijos de una sola letra."""
    autor = campos.get("AU", ["Anon"])[0].strip()
    tokens = [t for t in re.split(r"[ ,]+", autor) if t]
    apellido = "Anon"
    for t in tokens:
        limpio = re.sub(r"[^A-Za-z]", "", t)
        if len(limpio) >= 2:
            apellido = limpio
            break
    anio = campos.get("PY", ["0000"])[0][:4] or "0000"
    base = f"{apellido}{anio}"
    clave, n = base, 1
    while clave in usadas:
        n += 1
        clave = f"{base}_{n}"
    usadas.add(clave)
    return clave


def entrada_bibtex(campos, clave):
    """Construye una entrada BibTeX estilo Scopus a partir de un dict de campos."""
    tipo = TIPO_ENTRADA.get(campos.get("TY", ["JOUR"])[0], "ARTICLE")
    lineas = [f"@{tipo}{{{clave},"]

    def add(nombre, valor, forzar=False):
        # forzar=True escribe el campo aunque este vacio, para que bibliometrix
        # NO obtenga un vector de longitud 0 (causa del error "0, 168").
        if valor or forzar:
            valor = re.sub(r"\s*\n\s*", " ", (valor or "")).strip()
            lineas.append(f"  {nombre}={{{escapar_bibtex(valor)}}},")

    if "AU" in campos:
        add("author", " and ".join(campos["AU"]))
    add("title", campos.get("TI", [""])[0])
    add("year", campos.get("PY", [""])[0][:4])
    add("journal", campos.get("T2", [""])[0])
    add("volume", campos.get("VL", [""])[0])
    add("number", campos.get("IS", [""])[0])
    sp = campos.get("SP", [""])[0]
    ep = campos.get("EP", [""])[0]
    if sp and ep:
        add("pages", f"{sp}--{ep}")
    elif sp:
        add("pages", sp)
    add("doi", campos.get("DO", [""])[0])
    add("abstract", campos.get("AB", [""])[0])
    # Palabras clave. bibliometrix arma DE desde author_keywords e ID desde
    # keywords/index_terms: ambos deben existir en TODAS las entradas.
    kws = "; ".join(campos["KW"]) if "KW" in campos else ""
    add("author_keywords", kws, forzar=True)
    add("keywords", kws, forzar=True)          # ID (index keywords)
    # Afiliacion. El parser Scopus usa 'affiliations' (nuevo) y 'affiliation'
    # (clasico). Se incluyen ambos, siempre presentes.
    afil = "; ".join(campos["AD"]) if "AD" in campos else ""
    add("affiliations", afil, forzar=True)
    add("affiliation", afil, forzar=True)
    # Campos que scopus2df referencia y que, si faltan, dan vector de longitud 0.
    add("correspondence_address", "", forzar=True)   # RP
    add("references", "", forzar=True)               # CR (referencias citadas)
    add("note", "cited By 0", forzar=True)           # TC (times cited)
    add("publisher", campos.get("PB", [""])[0])
    add("issn", campos.get("SN", [""])[0])
    add("language", campos.get("LA", [""])[0])
    add("abbrev_source_title", campos.get("J2", [""])[0])
    add("url", campos.get("UR", [""])[0])
    add("document_type", campos.get("M3", ["Article"])[0] or "Article", forzar=True)
    add("sjr_quartile", campos.get("_QUARTILE", [""])[0])
    if campos.get("_SJR"):
        add("sjr", campos["_SJR"][0])
    add("source", "Scopus")
    lineas.append("}")
    return "\n".join(lineas)


# Columnas EXACTAS que espera el parser CSV de Scopus de bibliometrix.
COLUMNAS_CSV_SCOPUS = [
    "Authors", "Author full names", "Author(s) ID", "Title", "Year",
    "Source title", "Volume", "Issue", "Page start", "Page end", "Cited by",
    "DOI", "Link", "Affiliations", "Authors with affiliations", "Abstract",
    "Author Keywords", "Index Keywords", "Publisher", "ISSN",
    "Language of Original Document", "Abbreviated Source Title",
    "Document Type", "Source", "EID",
]


def fila_csv_scopus(campos, idx):
    """Construye una fila (dict) en el formato CSV de exportacion de Scopus."""
    au = "; ".join(campos.get("AU", []))
    kw = "; ".join(campos.get("KW", []))
    ad = "; ".join(campos.get("AD", []))
    return {
        "Authors": au,
        "Author full names": au,
        "Author(s) ID": "",
        "Title": campos.get("TI", [""])[0],
        "Year": campos.get("PY", [""])[0][:4],
        "Source title": campos.get("T2", [""])[0],
        "Volume": campos.get("VL", [""])[0],
        "Issue": campos.get("IS", [""])[0],
        "Page start": campos.get("SP", [""])[0],
        "Page end": campos.get("EP", [""])[0],
        "Cited by": "0",
        "DOI": campos.get("DO", [""])[0],
        "Link": campos.get("UR", [""])[0],
        "Affiliations": ad,
        "Authors with affiliations": ad,
        "Abstract": campos.get("AB", [""])[0],
        "Author Keywords": kw,
        "Index Keywords": kw,
        "Publisher": campos.get("PB", [""])[0],
        "ISSN": campos.get("SN", [""])[0],
        "Language of Original Document": campos.get("LA", [""])[0],
        "Abbreviated Source Title": campos.get("J2", [""])[0],
        "Document Type": campos.get("M3", ["Article"])[0] or "Article",
        "Source": "Scopus",
        "EID": f"2-s2.0-{idx:011d}",
    }
def procesar(entrada: Path, salida_csv: Path, salida_bib, ris_limpio, xlsx: Path,
             logger: logging.Logger):
    logger.info("=" * 68)
    logger.info("CONVERSION RIS -> CSV/BibTeX PARA BIBLIOMETRIX")
    logger.info("=" * 68)
    logger.info("Leyendo el archivo de entrada: %s", entrada)

    datos = entrada.read_bytes()
    if datos.startswith(b"\xef\xbb\xbf"):
        logger.debug("  Se detecto un BOM UTF-8 al inicio; se retira.")
        datos = datos[3:]
    texto = datos.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    logger.info("  Archivo leido: %d caracteres.", len(texto))

    logger.info("Separando en registros bibliograficos...")
    registros = separar_registros(texto)
    logger.info("  Se identificaron %d registros validos (con TY y ER).",
                len(registros))

    filas_mapeo = []
    registros_limpios = []   # bloques RIS limpios (para --ris)
    entradas_bib = []        # entradas BibTeX
    filas_csv = []           # filas CSV estilo Scopus (salida principal)
    usadas = set()

    n_wos = n_titlecase = n_issn = n_au = 0
    n_sin_cuartil = n_sin_sjr = 0

    logger.info("Procesando y transformando cada registro...")
    for idx, rec in enumerate(registros, 1):
        lineas = [l for l in rec.split("\n") if l.strip() != ""]
        campos = {}          # tag -> lista de valores (para BibTeX y Excel)
        nuevas_ris = []      # lineas del RIS limpio
        titulo = revista = issn = None
        cuartil = sjr_val = None
        es_scopus = "DB  - Scopus" in rec
        tiene_au = any(l.startswith("AU  -") for l in lineas)

        for l in lineas:
            if l.startswith("ER  -"):
                continue  # se re-inserta uno unico al final
            mtag = re.match(r"^([A-Z][A-Z0-9])  - ?(.*)$", l)
            if not mtag:
                nuevas_ris.append(l)
                continue
            tag, val = mtag.group(1), mtag.group(2).strip()

            mq = re.match(r"^SJR Best Quartile:\s*(Q\d)\s*$", val) if tag == "N1" else None
            ms = re.match(r"^SJR:\s*(.+?)\s*$", val) if tag == "N1" else None

            if mq:
                cuartil = mq.group(1)
                continue  # se consolida al final
            if ms:
                sjr_val = normalizar_sjr(ms.group(1), logger)
                continue
            if tag == "SN":
                bruto = re.sub(r"\(ISSN\)", "", val).strip()
                limpio = bruto.replace("-", "").strip()
                if limpio != bruto:
                    n_issn += 1
                    logger.debug("  [reg %d] ISSN: %r -> %r", idx, bruto, limpio)
                issn = limpio
                campos.setdefault("SN", []).append(limpio)
                nuevas_ris.append(f"SN  - {limpio}")
                continue
            if tag == "T2":
                conv = a_title_case_revista(val)
                if conv != val:
                    n_titlecase += 1
                    logger.debug("  [reg %d] Revista: %r -> %r", idx, val, conv)
                revista = conv
                campos.setdefault("T2", []).append(conv)
                nuevas_ris.append(f"T2  - {conv}")
                continue
            if tag == "TI":
                titulo = val
            campos.setdefault(tag, []).append(val)
            nuevas_ris.append(l)

        if not tiene_au:
            nuevas_ris.append("AU  - [No author name available]")
            campos.setdefault("AU", []).append("[No author name available]")
            n_au += 1
            logger.debug("  [reg %d] Sin autor: placeholder insertado. %.55s",
                         idx, titulo or "(sin titulo)")

        # consolidar cuartil/SJR en RIS limpio y en campos para BibTeX
        if cuartil:
            nuevas_ris.append(f"N1  - SJR Best Quartile: {cuartil}")
            campos["_QUARTILE"] = [cuartil]
        else:
            n_sin_cuartil += 1
        if sjr_val is not None:
            nuevas_ris.append(f"N1  - SJR: {sjr_val:.3f}")
            campos["_SJR"] = [f"{sjr_val:.3f}"]
        else:
            n_sin_sjr += 1

        if not es_scopus:
            n_wos += 1

        nuevas_ris.append("ER  - ")
        registros_limpios.append("\n".join(nuevas_ris))

        clave = clave_cita(campos, usadas)
        entradas_bib.append(entrada_bibtex(campos, clave))
        filas_csv.append(fila_csv_scopus(campos, idx))

        filas_mapeo.append({
            "n": idx, "clave": clave,
            "titulo": titulo or "", "revista": revista or "",
            "issn": issn or "", "cuartil": cuartil or "",
            "sjr": sjr_val if sjr_val is not None else "",
            "fuente": "Scopus" if es_scopus else "WoS/IEEE",
            "sin_autor": "SI" if not tiene_au else "",
        })

    logger.info("  Transformacion completada.")

    # -------- Escribir CSV estilo Scopus (SALIDA PRINCIPAL) --------
    logger.info("Escribiendo el CSV estilo Scopus en: %s", salida_csv)
    with salida_csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS_CSV_SCOPUS)
        w.writeheader()
        w.writerows(filas_csv)
    # Verificacion: releer el CSV y confirmar que las filas se recuperan intactas
    with salida_csv.open(encoding="utf-8-sig") as f:
        releidas = sum(1 for _ in csv.DictReader(f))
    logger.info("  CSV escrito: %d filas, %d columnas. Relectura: %d filas %s",
                len(filas_csv), len(COLUMNAS_CSV_SCOPUS), releidas,
                "OK" if releidas == len(filas_csv) else "DESAJUSTE!")
    if releidas != len(filas_csv):
        logger.warning("  ATENCION: el CSV no se relee con el mismo numero de "
                        "filas; posible campo mal escapado.")

    # -------- Escribir BibTeX (salida alternativa, solo si se pide) --------
    if salida_bib is not None:
        logger.info("Escribiendo el BibTeX (alternativa) en: %s", salida_bib)
        salida_bib.write_text("\n\n".join(entradas_bib) + "\n", encoding="utf-8")
        contenido = salida_bib.read_text(encoding="utf-8")
        balance = contenido.count("{") == contenido.count("}")
        logger.info("  BibTeX escrito: %d entradas, %d bytes. Llaves balanceadas: %s",
                    len(entradas_bib), salida_bib.stat().st_size, balance)
        if not balance:
            logger.warning("  ATENCION: llaves { } desbalanceadas; revise el .bib.")

    # -------- Escribir RIS limpio (opcional) --------
    if ris_limpio is not None:
        logger.info("Escribiendo el RIS limpio en: %s", ris_limpio)
        ris_txt = ("\n\n".join(registros_limpios) + "\n").replace("\n", "\r\n")
        ris_limpio.write_bytes(ris_txt.encode("utf-8"))
        logger.info("  RIS limpio escrito: %d registros.", len(registros_limpios))

    # -------- Escribir Excel de cuartiles --------
    logger.info("Escribiendo el mapeo de cuartiles en: %s", xlsx)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "cuartiles"
    ws.append(["N", "Clave BibTeX", "Titulo articulo", "Revista", "ISSN",
               "Cuartil SJR", "SJR", "Fuente", "Sin autor original"])
    for r in filas_mapeo:
        ws.append([r["n"], r["clave"], r["titulo"], r["revista"], r["issn"],
                   r["cuartil"], r["sjr"], r["fuente"], r["sin_autor"]])
    for col, ancho in zip("ABCDEFGHI", [5, 16, 55, 42, 13, 11, 8, 11, 16]):
        ws.column_dimensions[col].width = ancho
    wb.save(xlsx)
    logger.info("  Excel escrito con %d filas.", len(filas_mapeo))

    # -------- Resumen --------
    dist = {}
    for r in filas_mapeo:
        k = r["cuartil"] or "(sin cuartil)"
        dist[k] = dist.get(k, 0) + 1
    logger.info("=" * 68)
    logger.info("RESUMEN")
    logger.info("=" * 68)
    logger.info("Registros convertidos ............... %d", len(entradas_bib))
    logger.info("Entradas BibTeX escritas ............ %d", len(entradas_bib))
    logger.info("Registros no-Scopus (WoS/IEEE) ...... %d", n_wos)
    logger.info("ISSN normalizados (sin guion) ....... %d", n_issn)
    logger.info("Revistas pasadas a Title Case ....... %d", n_titlecase)
    logger.info("Autores placeholder insertados ...... %d", n_au)
    logger.info("Registros sin cuartil ............... %d", n_sin_cuartil)
    logger.info("Registros sin SJR ................... %d", n_sin_sjr)
    logger.info("Distribucion de cuartiles ........... %s",
                ", ".join(f"{k}={v}" for k, v in sorted(dist.items())))
    logger.info("=" * 68)
    logger.info("LISTO. Cargue el CSV en Biblioshiny con Database = Scopus.")
    logger.info("  Salida principal (recomendada): %s", salida_csv.name)
    if salida_bib is not None:
        logger.info("  Alternativa BibTeX generada  : %s", salida_bib.name)
    else:
        logger.info("  (Para generar tambien un .bib alternativo, use --bib)")
    logger.info("Confirme que 'Number of Documents' = %d al importar.",
                len(filas_csv))
    logger.info("=" * 68)


def main():
    parser = argparse.ArgumentParser(
        description="Convierte un RIS fusionado (Scopus+WoS+cuartiles) a CSV "
                    "estilo Scopus (y BibTeX) para bibliometrix, con Excel de "
                    "cuartiles y log narrativo.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Entrada equivalente: 'script.py a.ris', '-i a.ris' o '--input a.ris'.",
    )
    parser.add_argument("entrada_pos", type=Path, nargs="?", default=None,
                        metavar="entrada", help="Archivo RIS de entrada.")
    parser.add_argument("-i", "--input", type=Path, dest="input", default=None,
                        help="Archivo RIS de entrada (equivalente al posicional).")
    parser.add_argument("-o", "--output", type=Path, dest="output", default=None,
                        help="CSV estilo Scopus de salida, la salida PRINCIPAL "
                             "(por defecto: *_biblio.csv).")
    parser.add_argument("--bib", type=Path, default=None,
                        help="BibTeX de salida alternativo "
                             "(por defecto: *_biblio.bib).")
    parser.add_argument("--ris", type=Path, nargs="?", const="__auto__",
                        default=None,
                        help="Ademas, guardar el RIS limpio intermedio "
                             "(ruta opcional; por defecto *_LIMPIO.ris).")
    parser.add_argument("-x", "--xlsx", type=Path, default=None,
                        help="Excel de cuartiles (por defecto: cuartiles_mapeo.xlsx).")
    parser.add_argument("-l", "--log", type=Path, default=None,
                        help="Archivo de log (por defecto: conversion.log).")
    parser.add_argument("-v", "--verbose", "--verboso", action="store_true",
                        help="Detalle registro por registro en consola.")
    args = parser.parse_args()

    entrada = args.input or args.entrada_pos
    if entrada is None:
        parser.error("falta el archivo de entrada. Uselo como posicional "
                     "(script.py archivo.ris) o con -i/--input archivo.ris")
    if args.input and args.entrada_pos and args.input != args.entrada_pos:
        parser.error(f"dos entradas distintas: posicional={args.entrada_pos} "
                     f"y --input={args.input}. Use solo una.")
    if not entrada.exists():
        sys.stderr.write(f"ERROR: no existe el archivo de entrada: {entrada}\n")
        sys.exit(1)

    salida_csv = args.output or entrada.with_name(entrada.stem + "_biblio.csv")
    # Las salidas secundarias se ubican JUNTO AL CSV de salida (no junto a la
    # entrada, que puede estar en una carpeta de solo lectura).
    base = salida_csv.parent
    salida_bib = args.bib  # None salvo que se pida explicitamente con --bib
    xlsx = args.xlsx or base / "cuartiles_mapeo.xlsx"
    log = args.log or base / "conversion.log"
    ris_limpio = None
    if args.ris is not None:
        ris_limpio = (entrada.with_name(entrada.stem + "_LIMPIO.ris")
                      if str(args.ris) == "__auto__" else args.ris)

    logger = configurar_logger(log, args.verbose)
    try:
        procesar(entrada, salida_csv, salida_bib, ris_limpio, xlsx, logger)
    except Exception as exc:  # noqa: BLE001
        logger.exception("FALLO INESPERADO: %s", exc)
        sys.exit(2)


if __name__ == "__main__":
    main()
