"""
10_exportar_latex.py  (v3)
==========================
RSL: Aplicaciones de ML para el Control de pH en la Industria Azucarera

Sincroniza artefactos del pipeline -> 07_latex_output/ y prepara todo
para redaccion IMRD del paper.

Tareas:
  1. Verifica artefactos del pipeline (scripts 00-09)
  2. Copia figuras -> 07_latex_output/figures/
       PRISMA       : figures/REPORTE_PRISMA.png/.pdf/.svg
       Co-ocurrencia: figures/vos_pH_q1.png/.pdf
  3. Convierte PNG -> PDF (Pillow)
  4. Verifica referencias \\includegraphics en 01_title.tex..06_appendices.tex
  5. Actualiza bibliography/pHazucar.bib de forma NO destructiva: anade
     entradas metodologicas faltantes y detecta candidatos de corpus nuevos
     por DOI desde el Excel del script 04 (decision_manual == 'INCLUIR'),
     escribiendolos en un .bib de staging para revision manual (nunca
     sobrescribe entradas ya curadas a mano)
  6. Genera fragmentos .tex para IMRD con numeros del pipeline
  7. Reporte de pre-compilacion en --output

Uso:
  python 09_exportar_latex.py
  python 09_exportar_latex.py --output ..\07_latex_output
  python 09_exportar_latex.py --log-level DEBUG
"""

import os
import re
import sys
import shutil
import argparse
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("export_latex")


# ── LOGGING ───────────────────────────────────────────────────────────────────
def configurar_logging(output_folder: str, log_level: str) -> str:
    os.makedirs(output_folder, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(output_folder, f"export_latex_{timestamp}.log")

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


# ── RUTAS DEL PROYECTO ────────────────────────────────────────────────────────
class Paths:
    def __init__(self, root: Path):
        self.root = root

        # Carpetas (alineadas con tu layout real)
        self.query_design = root / "00_query_design"
        self.raw          = root / "01_raw_data"         # fusion vive aqui
        self.filtered     = root / "03_filtered_data"    # 1./2./3./4. viven aqui
        self.corpus       = root / "04_corpus_final"
        self.bibliometria = root / "05_bibliometria"
        self.prisma_dir   = root / "06_prisma"
        self.latex_output = root / "07_latex_output"
        self.figures      = self.latex_output / "figures"
        self.bibliography = self.latex_output / "bibliography"
        self.snippets     = self.latex_output / "snippets"

        # LaTeX
        # NOTA (2026-09): la fuente de verdad citada por 00_config.tex es
        # "pHazucar.bib" (sin guion bajo), curada a mano con 43 entradas.
        # El nombre "pH_azucar.bib" (con guion bajo) fue un archivo generado
        # por versiones previas de este script que quedo huerfano (nunca
        # referenciado por \addbibresource) y con una clave inconsistente
        # (murugesan2020computer vs. murugesan2020computeraided). Se corrige
        # aqui para que el script escriba siempre sobre la fuente real.
        self.bib_file = self.bibliography / "pHazucar.bib"
        self.bib_file_legacy_huerfano = self.bibliography / "pH_azucar.bib"

        # Script 00: queries
        self.queries_scopus = self.query_design / "queries_scopus.txt"
        self.queries_wos    = self.query_design / "queries_wos.txt"
        self.queries_ieee   = self.query_design / "queries_ieee.txt"

        # Script 00: datos brutos
        self.scopus_1 = self.raw / "scopus_export_1.ris"
        self.scopus_2 = self.raw / "scopus_export_2.ris"
        self.scopus_3 = self.raw / "scopus_export_3.ris"
        self.wos_1    = self.raw / "wos_export_1.ris"
        self.wos_2    = self.raw / "wos_export_2.ris"
        self.wos_3    = self.raw / "wos_export_3.ris"
        self.ieee_1   = self.raw / "ieee_export_1.ris"
        self.ieee_2   = self.raw / "ieee_export_2.ris"
        self.ieee_3   = self.raw / "ieee_export_3.ris"

        # Fusion (en 01_raw_data segun tu layout)
        self.fusion_all    = self.raw / "fusion_export_all.ris"
        self.fusion_unique = self.raw / "fusion_export.ris"

        # Pipeline (en 03_filtered_data)
        self.prefiltrado_ris = self.filtered / "1.prefiltrado.ris"
        self.cuartiles_ris   = self.filtered / "2.fusionado_con_cuartiles.ris"
        self.q1q4_ris        = self.filtered / "3.filtrado_quartiles.ris"
        self.ollama_ris      = self.filtered / "4.filtrado_ollama.ris"
        self.ollama_xlsx     = self.filtered / "4.filtrado_ollama.xlsx"

        # Script 06: NotebookLM
        self.notebooklm_txt = self.filtered / "6.corpus_notebooklm.txt"
        self.tabla4_xlsx    = self.filtered / "6.tabla4_estructura.xlsx"

        # Script 07: bibliometria
        self.clusters_xlsx    = self.bibliometria / "7.clusters_tematicos.xlsx"
        self.cooc_edges_csv   = self.bibliometria / "7.coocurrencia_edges.csv"
        self.fig_coocurrencia = self.bibliometria / "7.coocurrencia_keywords.png"

        # Script 08: PRISMA
        self.fig_prisma_png = self.prisma_dir / "8.diagrama_prisma_2020.png"
        self.fig_prisma_svg = self.prisma_dir / "8.diagrama_prisma_2020.svg"

        # Figuras destino
        self.fig1_prisma     = self.figures / "REPORTE_PRISMA.png"
        self.fig1_prisma_pdf = self.figures / "REPORTE_PRISMA.pdf"
        self.fig1_prisma_svg = self.figures / "REPORTE_PRISMA.svg"
        self.fig2_cooc       = self.figures / "vos_pH_q1.png"
        self.fig2_cooc_pdf   = self.figures / "vos_pH_q1.pdf"


# ── ENTRADAS .BIB METODOLOGICAS (hardcodeadas) ────────────────────────────────
BIB_METODOLOGICAS: dict[str, str] = {
    "page2021prisma": """\
@article{page2021prisma,
  author    = {Page, Matthew J. and McKenzie, Joanne E.
               and Bossuyt, Patrick M. and Boutron, Isabelle
               and Hoffmann, Tammy C. and Mulrow, Cynthia D.
               and Shamseer, Larissa and Tetzlaff, Jennifer M.
               and Akl, Elie A. and Brennan, Sue E. and others},
  title     = {The {PRISMA} 2020 Statement: An Updated Guideline
               for Reporting Systematic Reviews},
  journal   = {BMJ},
  volume    = {372},
  pages     = {n71},
  year      = {2021},
  doi       = {10.1136/bmj.n71},
}""",

    "ARIA2017959": """\
@article{ARIA2017959,
  author  = {Aria, Massimo and Cuccurullo, Corrado},
  title   = {bibliometrix: An {R}-tool for comprehensive science
             mapping analysis},
  journal = {Journal of Informetrics},
  volume  = {11},
  number  = {4},
  pages   = {959--975},
  year    = {2017},
  doi     = {10.1016/j.joi.2017.08.007},
}""",

    "vanecksoftware2010": """\
@misc{vanecksoftware2010,
  author       = {van Eck, Nees Jan and Waltman, Ludo},
  title        = {{VOSviewer}: Visualizing Scientific Landscapes},
  year         = {2010},
  howpublished = {\\url{https://www.vosviewer.com}},
  note         = {Version 1.6.19},
}""",

    "rein2007cane": """\
@book{rein2007cane,
  author    = {Rein, Peter},
  title     = {Cane Sugar Engineering},
  publisher = {Bartens},
  address   = {Berlin},
  year      = {2007},
  isbn      = {3870401109},
  note      = {Parametros operacionales de clarificacion: pH 6.8-7.2,
               dosis de cal 200-800 g/m3, temperatura 88-105 C},
}""",

    "shinskey1996process": """\
@book{shinskey1996process,
  author    = {Shinskey, Francis G.},
  title     = {Process Control Systems: Application, Design, and Tuning},
  edition   = {4},
  publisher = {McGraw-Hill},
  address   = {New York},
  year      = {1996},
}""",

    "garcia1989model": """\
@article{garcia1989model,
  author  = {Garc{\\'{i}}a, Carlos E. and Prett, David M. and Morari, Manfred},
  title   = {Model predictive control: Theory and practice -- A survey},
  journal = {Automatica},
  volume  = {25}, number  = {3}, pages   = {335--348},
  year    = {1989}, doi = {10.1016/0005-1098(89)90002-2},
}""",

    "landis1977kappa": """\
@article{landis1977kappa,
  author  = {Landis, J. Richard and Koch, Gary G.},
  title   = {The Measurement of Observer Agreement for Categorical Data},
  journal = {Biometrics},
  volume  = {33}, number  = {1}, pages   = {159--174},
  year    = {1977}, doi = {10.2307/2529310},
}""",
}


# ── GENERACION DE BIBTEX DESDE EL EXCEL ───────────────────────────────────────
def slugify_clave(autor: str, anio: str, titulo: str) -> str:
    """Genera clave BibTeX tipo 'palacio2021nmpc' desde autor/año/título."""
    primer_autor = re.split(r"[,;]", autor)[0].strip() if autor else "anon"
    apellido = re.sub(r"[^a-zA-Z]", "", primer_autor.split()[0]).lower()
    if not apellido:
        apellido = "anon"
    # Primera palabra significativa del título (>3 letras)
    palabras = re.findall(r"[a-zA-Z]{4,}", titulo or "")
    stopwords = {"the", "and", "for", "with", "from", "using", "based",
                 "into", "applied", "application", "study", "analysis"}
    palabra_clave = next((p.lower() for p in palabras if p.lower() not in stopwords), "")
    palabra_clave = palabra_clave[:8]
    anio_clean = re.sub(r"[^\d]", "", str(anio))[:4] or "nodate"
    base = f"{apellido}{anio_clean}{palabra_clave}".strip()
    return base or "ref"


def escapar_bibtex(s: str) -> str:
    """Escapa caracteres conflictivos en valores BibTeX."""
    if not s:
        return ""
    s = str(s).strip()
    # Llaves desbalanceadas: balancear
    s = s.replace("\\", "\\textbackslash{}")
    s = s.replace("&", "\\&").replace("%", "\\%").replace("$", "\\$")
    s = s.replace("#", "\\#").replace("_", "\\_")
    return s


def normalizar_autores_bibtex(au_str: str) -> str:
    """Convierte 'Smith, J.; Doe, J.' o lista a 'Smith, J. and Doe, J.'"""
    if not au_str:
        return ""
    s = str(au_str)
    # Si parece lista Python
    if s.startswith("[") and s.endswith("]"):
        try:
            import ast
            parsed = ast.literal_eval(s)
            if isinstance(parsed, list):
                s = "; ".join(str(x) for x in parsed)
        except Exception:
            pass
    autores = [a.strip() for a in re.split(r"[;]", s) if a.strip()]
    return " and ".join(autores)


def generar_bibtex_desde_excel(xlsx_path: Path) -> tuple[dict[str, str], list[str]]:
    """
    Lee 4.filtrado_ollama.xlsx hoja 'Clasificacion', filtra
    decision_manual=='INCLUIR' y genera entradas BibTeX.
    Retorna (dict_de_entradas, lista_de_advertencias).
    """
    if not xlsx_path.exists() or xlsx_path.is_dir():
        return {}, [f"Excel no encontrado: {xlsx_path}"]

    try:
        import pandas as pd
    except ImportError:
        return {}, ["pandas no instalado: pip install pandas openpyxl"]

    try:
        df = pd.read_excel(xlsx_path, sheet_name="Clasificacion")
    except Exception as e:
        return {}, [f"Error leyendo Excel: {e}"]

    if "decision_manual" not in df.columns:
        return {}, ["La hoja 'Clasificacion' no tiene columna 'decision_manual'."
                    " Agregala con 'INCLUIR'/'EXCLUIR' antes de re-ejecutar."]

    df_incl = df[df["decision_manual"].astype(str).str.upper().str.strip() == "INCLUIR"]
    if df_incl.empty:
        return {}, ["Ningun articulo con decision_manual=INCLUIR. "
                    "Revisa el Excel y marca al menos un paper."]

    entries: dict[str, str] = {}
    warnings: list[str] = []
    claves_usadas: set[str] = set()

    for _, row in df_incl.iterrows():
        au  = normalizar_autores_bibtex(row.get("AU", ""))
        py  = str(row.get("PY", "")).strip()
        ti  = str(row.get("TI", "")).strip()
        t2  = str(row.get("T2", "")).strip()
        doi = str(row.get("DO", "")).strip()
        vol = str(row.get("VL", "")).strip()
        iss = str(row.get("IS", "")).strip()
        sp  = str(row.get("SP", "")).strip()
        ep  = str(row.get("EP", "")).strip()
        pb  = str(row.get("PB", "")).strip()

        if not au or not ti:
            warnings.append(f"Skip: fila sin AU o TI (DOI={doi or '?'})")
            continue

        # Generar clave única
        clave_base = slugify_clave(au, py, ti)
        clave = clave_base
        n = 1
        while clave in claves_usadas:
            n += 1
            clave = f"{clave_base}{chr(96+n)}"  # 'a','b','c'...
        claves_usadas.add(clave)

        # Construir entrada
        campos = []
        campos.append(f"  author    = {{{au}}}")
        campos.append(f"  title     = {{{escapar_bibtex(ti)}}}")
        if t2:  campos.append(f"  journal   = {{{escapar_bibtex(t2)}}}")
        if py:  campos.append(f"  year      = {{{py}}}")
        if vol: campos.append(f"  volume    = {{{vol}}}")
        if iss: campos.append(f"  number    = {{{iss}}}")
        if sp and ep: campos.append(f"  pages     = {{{sp}--{ep}}}")
        elif sp:      campos.append(f"  pages     = {{{sp}}}")
        if doi: campos.append(f"  doi       = {{{doi}}}")
        if pb:  campos.append(f"  publisher = {{{escapar_bibtex(pb)}}}")
        campos.append(f"  note      = {{Corpus RSL pH azucar -- decision_manual=INCLUIR}}")

        tipo = "article" if t2 else "misc"
        entry = f"@{tipo}{{{clave},\n" + ",\n".join(campos) + "\n}"
        entries[clave] = entry

    return entries, warnings


# ── COPIA Y CONVERSION DE FIGURAS ─────────────────────────────────────────────
def png_a_pdf(origen: Path, destino: Path) -> bool:
    try:
        from PIL import Image
    except ImportError:
        logger.warning("Pillow no instalado: pip install pillow")
        return False
    try:
        img = Image.open(str(origen))
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")
        dpi = img.info.get("dpi", (300, 300))
        img.save(str(destino), "PDF", resolution=dpi[0])
        return True
    except Exception as e:
        logger.warning(f"{origen.name} -> PDF: {e}")
        return False


def copiar_figuras(P: Paths) -> list[str]:
    copias = [
        (P.fig_prisma_png,   P.fig1_prisma,
         "08_PRISMA -> figures/REPORTE_PRISMA.png"),
        (P.fig_prisma_png,   P.fig1_prisma_pdf,
         "08_PRISMA -> figures/REPORTE_PRISMA.pdf [PNG->PDF]"),
        (P.fig_prisma_svg,   P.fig1_prisma_svg,
         "08_PRISMA -> figures/REPORTE_PRISMA.svg"),
        (P.fig_coocurrencia, P.fig2_cooc,
         "07_Bibliometria -> figures/vos_pH_q1.png"),
        (P.fig_coocurrencia, P.fig2_cooc_pdf,
         "07_Bibliometria -> figures/vos_pH_q1.pdf [PNG->PDF]"),
    ]
    errores = []
    for origen, destino, desc in copias:
        if not origen.exists():
            logger.warning(f"  [--] {desc}  (origen no existe: {origen})")
            errores.append(str(origen))
            continue
        destino.parent.mkdir(parents=True, exist_ok=True)
        es_conv = destino.suffix.lower() == ".pdf" and origen.suffix.lower() == ".png"
        if es_conv:
            ok = png_a_pdf(origen, destino)
            if ok:
                kb = destino.stat().st_size // 1024
                logger.info(f"  [OK] {desc}  ({kb} KB)")
            else:
                shutil.copy2(str(origen), str(destino))
                logger.info(f"  [FB] {desc}  (copia directa)")
        else:
            shutil.copy2(str(origen), str(destino))
            kb = destino.stat().st_size // 1024
            logger.info(f"  [OK] {desc}  ({kb} KB)")
    return errores


# ── VERIFICACIONES ────────────────────────────────────────────────────────────
def verificar_pipeline(P: Paths) -> list[tuple[str, str, Path, bool]]:
    checks = [
        ("00", "Queries Scopus (queries_scopus.txt)",          P.queries_scopus),
        ("00", "Queries WoS (queries_wos.txt)",                P.queries_wos),
        ("00", "Queries IEEE (queries_ieee.txt)",              P.queries_ieee),
        ("00", "Scopus 1 (scopus_export_1.ris)",               P.scopus_1),
        ("00", "Scopus 2 (scopus_export_2.ris)",               P.scopus_2),
        ("00", "Scopus 3 (scopus_export_3.ris)",               P.scopus_3),
        ("00", "WoS 1 (wos_export_1.ris)",                     P.wos_1),
        ("00", "WoS 2 (wos_export_2.ris)",                     P.wos_2),
        ("00", "WoS 3 (wos_export_3.ris)",                     P.wos_3),
        ("00", "IEEE 1 (ieee_export_1.ris)",                   P.ieee_1),
        ("00", "IEEE 2 (ieee_export_2.ris)",                   P.ieee_2),
        ("00", "IEEE 3 (ieee_export_3.ris)",                   P.ieee_3),
        ("00", "Fusion (fusion_export.ris en 01_raw_data)",    P.fusion_unique),
        ("01", "Prefiltrado (1.prefiltrado.ris)",              P.prefiltrado_ris),
        ("02", "Con cuartiles (2.fusionado_con_cuartiles.ris)",P.cuartiles_ris),
        ("03", "Q1-Q4 (3.filtrado_quartiles.ris)",              P.q1q4_ris),
        ("04", "Ollama Excel (4.filtrado_ollama.xlsx)",        P.ollama_xlsx),
        ("04", "Ollama RIS (4.filtrado_ollama.ris)",           P.ollama_ris),
        ("06", "Corpus NotebookLM (6.corpus_notebooklm.txt)",  P.notebooklm_txt),
        ("06", "Tabla 4 (6.tabla4_estructura.xlsx)",           P.tabla4_xlsx),
        ("07", "Clusters (7.clusters_tematicos.xlsx)",         P.clusters_xlsx),
        ("07", "Figura co-ocurrencia",                         P.fig_coocurrencia),
        ("08", "PRISMA PNG (8.diagrama_prisma_2020.png)",      P.fig_prisma_png),
    ]
    return [(s, d, r, r.exists()) for s, d, r in checks]


# NOTA (2026-09): el layout real de este proyecto NO usa el patron
# "pH_azucar_*.tex" (ese nombre nunca existio en 07_latex_output; el
# glob correspondiente siempre devolvia 0 archivos y por eso el reporte
# de exportacion reportaba engañosamente "0 problemas" en verificaciones
# que en realidad nunca se ejecutaban). Los archivos reales del cuerpo
# del manuscrito son estos, en orden de \input en SRL_pH.tex:
ARCHIVOS_TEX_MANUSCRITO = [
    "01_title.tex", "02_abstract.tex", "03_introduction.tex",
    "04_body.tex", "05_references.tex", "06_appendices.tex",
]


def _archivos_tex_manuscrito(P: Paths) -> list[Path]:
    return [P.latex_output / n for n in ARCHIVOS_TEX_MANUSCRITO
            if (P.latex_output / n).exists()]


def verificar_includegraphics(P: Paths) -> list[str]:
    faltantes = []
    for tex in _archivos_tex_manuscrito(P):
        texto = tex.read_text(encoding="utf-8", errors="replace")
        for ref in re.findall(r'\\includegraphics(?:\[.*?\])?\{([^}]+)\}', texto):
            candidatos = [
                P.figures / ref,
                P.figures / (ref + ".pdf"),
                P.figures / (ref + ".png"),
                P.figures / (ref + ".svg"),
            ]
            if not any(c.exists() for c in candidatos):
                faltantes.append(f"{tex.name}: \\includegraphics{{{ref}}}")
    return faltantes


def _quitar_comentarios_latex(texto: str) -> str:
    """Elimina comentarios LaTeX ('%' hasta fin de linea, sin contar '\\%'
    escapado) para que un salto de linea comentado dentro de un argumento
    de \\parencite{a,%\\nb} no se confunda con parte de una clave BibTeX."""
    return re.sub(r'(?<!\\)%[^\n]*', '', texto)


def claves_citadas(P: Paths) -> set[str]:
    claves = set()
    for tex in _archivos_tex_manuscrito(P):
        texto = _quitar_comentarios_latex(
            tex.read_text(encoding="utf-8", errors="replace")
        )
        for grupo in re.findall(
            r'\\(?:parencite|textcite|cite(?:p|t|alp|alt)?)(?:\[.*?\])*\{([^}]+)\}',
            texto
        ):
            for c in grupo.split(","):
                c = re.sub(r'\s+', '', c)  # tolera saltos de linea/espacios
                if c:
                    claves.add(c)
    return claves


def _dois_y_claves_existentes(bib_path: Path) -> tuple[set[str], set[str]]:
    """Extrae (DOIs, claves) ya presentes en un .bib existente, para no
    proponer como 'nuevas' entradas de corpus que un humano ya curo a mano
    (posiblemente con una clave distinta a la que generaria slugify_clave)."""
    if not bib_path.exists():
        return set(), set()
    texto = bib_path.read_text(encoding="utf-8", errors="replace")
    dois = {m.lower() for m in re.findall(r'doi\s*=\s*\{([^}]+)\}', texto, re.I)}
    claves = set(re.findall(r'@\w+\{\s*([^,\s]+)\s*,', texto))
    return dois, claves


def generar_bib(P: Paths) -> tuple[int, int, list[str], list[str]]:
    """
    Actualiza la bibliografia SIN sobrescribir destructivamente la fuente de
    verdad curada a mano (P.bib_file, referenciada por \\addbibresource en
    00_config.tex):
      - Las entradas metodologicas hardcodeadas (BIB_METODOLOGICAS) se
        anaden solo si su clave no existe ya en el .bib real.
      - Las entradas de corpus generadas desde el Excel se comparan por DOI
        contra el .bib real: si el DOI ya esta presente (fue incorporado a
        mano, posiblemente con una clave distinta a la que produce
        slugify_clave), NO se duplican ni se sobrescriben.
      - Las entradas de corpus con DOI nuevo (estudios recien incluidos en
        una corrida futura que aun no estan en el .bib real) se escriben en
        un archivo de STAGING aparte para revision manual antes de
        incorporarlas, nunca se anaden automaticamente al .bib real.
    Retorna (n_corpus_nuevas_staging, n_metodologicas_anadidas, advertencias_excel,
             claves_no_resueltas).
    """
    P.bibliography.mkdir(parents=True, exist_ok=True)

    # 0. Elimina el archivo huerfano de corridas previas (pH_azucar.bib, con
    #    guion bajo) si aun existe: nunca fue referenciado por 00_config.tex
    #    y traia una clave inconsistente (murugesan2020computer).
    legacy = getattr(P, "bib_file_legacy_huerfano", None)
    if legacy and legacy.exists():
        legacy.unlink()
        logger.info(f"Eliminado archivo .bib huerfano de corridas previas: {legacy.name}")

    dois_existentes, claves_existentes = _dois_y_claves_existentes(P.bib_file)

    # 1. Generar entradas candidatas del corpus desde Excel
    entries_corpus, warns = generar_bibtex_desde_excel(P.ollama_xlsx)
    for w in warns:
        logger.warning(w)

    def _doi_de_entry(entry: str) -> str:
        m = re.search(r'doi\s*=\s*\{([^}]+)\}', entry, re.I)
        return m.group(1).strip().lower() if m else ""

    entries_corpus_nuevas = {
        clave: entry for clave, entry in entries_corpus.items()
        if _doi_de_entry(entry) not in dois_existentes
    }
    n_ya_en_bib = len(entries_corpus) - len(entries_corpus_nuevas)
    if n_ya_en_bib:
        logger.info(f"{n_ya_en_bib} entrada(s) de corpus ya presentes en "
                     f"{P.bib_file.name} por DOI (no se duplican).")

    # 2. Entradas metodologicas: solo las que faltan en el .bib real
    metod_faltantes = {
        clave: entry for clave, entry in BIB_METODOLOGICAS.items()
        if clave not in claves_existentes
    }

    # 3. Si hay entradas de corpus nuevas por DOI, escribirlas en un archivo
    #    de STAGING separado (nunca se tocan las 43+ entradas curadas).
    staging_path = P.bibliography / "pHazucar_STAGING_nuevas_entradas.bib"
    if entries_corpus_nuevas:
        cabecera_staging = [
            "% STAGING -- entradas de corpus detectadas por DOI nuevo que",
            "% AUN NO estan en bibliography/pHazucar.bib (la fuente real).",
            f"% Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "% Revisar y pegar manualmente en pHazucar.bib; verificar/renombrar",
            "% la clave generada por slugify_clave() antes de citarla en el .tex.",
            "",
        ]
        cuerpo = []
        for clave, entry in entries_corpus_nuevas.items():
            cuerpo.append(entry)
            cuerpo.append("")
        staging_path.write_text("\n".join(cabecera_staging + cuerpo), encoding="utf-8")
        logger.warning(f"{len(entries_corpus_nuevas)} entrada(s) de corpus NUEVAS "
                        f"(DOI no encontrado en {P.bib_file.name}) escritas en "
                        f"{staging_path.name} para revision manual.")
    elif staging_path.exists():
        staging_path.unlink()

    # 4. Anadir SOLO las entradas metodologicas faltantes al .bib real,
    #    preservando el resto del archivo tal cual (append, no overwrite).
    if metod_faltantes:
        bloque = ["", "% === Anadido automaticamente por 09_exportar_latex.py "
                       f"({datetime.now().strftime('%Y-%m-%d %H:%M')}) ===", ""]
        for clave, entry in metod_faltantes.items():
            bloque.append(entry)
            bloque.append("")
        with P.bib_file.open("a", encoding="utf-8") as f:
            f.write("\n".join(bloque))
        logger.info(f"{len(metod_faltantes)} entrada(s) metodologica(s) anadida(s) "
                    f"a {P.bib_file.name}: {sorted(metod_faltantes.keys())}")
    else:
        logger.info(f"Sin cambios en {P.bib_file.name}: todas las entradas "
                     "metodologicas ya estaban presentes.")

    # 5. Verificar claves citadas en los .tex reales del proyecto contra el
    #    .bib real (incluyendo lo recien anadido).
    _, claves_finales = _dois_y_claves_existentes(P.bib_file)
    citadas = claves_citadas(P)
    no_resueltas = sorted(citadas - claves_finales) if citadas else []
    if no_resueltas:
        logger.warning(f"Claves citadas en .tex pero NO en el .bib: {no_resueltas}")

    return len(entries_corpus_nuevas), len(metod_faltantes), warns, no_resueltas


# ── GENERACION DE FRAGMENTOS IMRD ─────────────────────────────────────────────
def contar_ris(path: Path) -> int:
    if not path.exists() or path.is_dir():
        return -1
    return path.read_text(encoding="utf-8", errors="replace").count("ER  -")


def generar_snippets_imrd(P: Paths) -> list[str]:
    """
    Genera fragmentos .tex listos para \\input{} con numeros del pipeline.
    """
    P.snippets.mkdir(parents=True, exist_ok=True)
    generados = []

    # ── Conteos del pipeline ─────────────────────────────────────────────
    s = [contar_ris(x) for x in (P.scopus_1, P.scopus_2, P.scopus_3)]
    w = [contar_ris(x) for x in (P.wos_1, P.wos_2, P.wos_3)]
    i = [contar_ris(x) for x in (P.ieee_1, P.ieee_2, P.ieee_3)]
    n_scopus = sum(x for x in s if x > 0)
    n_wos    = sum(x for x in w if x > 0)
    n_ieee   = sum(x for x in i if x > 0)
    n_bruto  = n_scopus + n_wos + n_ieee
    n_all    = contar_ris(P.fusion_all)
    n_fus    = contar_ris(P.fusion_unique)
    n_pre    = contar_ris(P.prefiltrado_ris)
    n_q1     = contar_ris(P.q1q4_ris)

    n_dup    = max(0, n_all - n_fus) if n_all > 0 and n_fus > 0 else 0
    n_excl_tipo = max(0, n_fus - n_pre) if n_fus > 0 and n_pre > 0 else 0
    n_excl_q    = max(0, n_pre - n_q1) if n_pre > 0 and n_q1 > 0 else 0

    # Excel: corpus y metricas
    n_corpus, n_eval_llm, n_excl_local = 0, 0, 0
    try:
        import pandas as pd
        if P.ollama_xlsx.exists():
            df = pd.read_excel(P.ollama_xlsx, sheet_name="Clasificacion")
            if "decision_manual" in df.columns:
                n_corpus = int((df["decision_manual"].astype(str).str.upper()
                                .str.strip() == "INCLUIR").sum())
            if "nivel_certeza" in df.columns:
                nv = df["nivel_certeza"].value_counts()
                n_excl_local = int(nv.get("LOCAL", 0))
                n_eval_llm = max(0, n_q1 - n_excl_local) if n_q1 > 0 else 0
    except Exception:
        pass

    # ── Snippet: numeros PRISMA para \input{} ────────────────────────────
    prisma_tex = P.snippets / "imrd_prisma_numbers.tex"
    prisma_tex.write_text(
        f"% Generado automaticamente por 10_exportar_latex.py\n"
        f"% Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"\\newcommand{{\\NScopus}}{{{n_scopus}}}\n"
        f"\\newcommand{{\\NWoS}}{{{n_wos}}}\n"
        f"\\newcommand{{\\NIEEE}}{{{n_ieee}}}\n"
        f"\\newcommand{{\\NBruto}}{{{n_bruto}}}\n"
        f"\\newcommand{{\\NDuplicados}}{{{n_dup}}}\n"
        f"\\newcommand{{\\NUnicos}}{{{n_fus}}}\n"
        f"\\newcommand{{\\NExclTipo}}{{{n_excl_tipo}}}\n"
        f"\\newcommand{{\\NPrefiltrado}}{{{n_pre}}}\n"
        f"\\newcommand{{\\NExclCuartil}}{{{n_excl_q}}}\n"
        f"\\newcommand{{\\NQcuartil}}{{{n_q1}}}\n"
        f"\\newcommand{{\\NExclLocal}}{{{n_excl_local}}}\n"
        f"\\newcommand{{\\NEvalLLM}}{{{n_eval_llm}}}\n"
        f"\\newcommand{{\\NCorpus}}{{{n_corpus}}}\n",
        encoding="utf-8",
    )
    generados.append(str(prisma_tex))
    logger.info(f"Snippet PRISMA: {prisma_tex}")
    logger.info(f"  Usar en cualquier .tex: \\input{{snippets/imrd_prisma_numbers.tex}}")
    logger.info(f"  Y luego macros: \\NBruto, \\NUnicos, \\NQcuartil, \\NCorpus, etc.")

    # ── Snippet: parrafo metodologico listo ──────────────────────────────
    metodo_tex = P.snippets / "imrd_methods_paragraph.tex"
    metodo_tex.write_text(
        f"% Parrafo metodologico generado automaticamente.\n"
        f"% Edita el texto libremente; los numeros usan macros de imrd_prisma_numbers.tex.\n\n"
        f"La busqueda sistematica se ejecuto en Scopus, Web of Science e IEEE Xplore "
        f"siguiendo la directriz PRISMA 2020 \\parencite{{page2021prisma}}. "
        f"Se identificaron \\NBruto{{}} registros brutos "
        f"(\\NScopus{{}} en Scopus, \\NWoS{{}} en Web of Science, \\NIEEE{{}} en IEEE Xplore). "
        f"Tras eliminar \\NDuplicados{{}} duplicados por DOI normalizado, quedaron "
        f"\\NUnicos{{}} registros unicos. El prefiltrado por tipo de documento (articulos y "
        f"revisiones) y rango temporal (2015--2026) excluyo \\NExclTipo{{}} registros, "
        f"dejando \\NPrefiltrado{{}} candidatos. La integracion con el ranking SCImago "
        f"(cuartiles Q1--Q4) redujo el conjunto a \\NQcuartil{{}} articulos. Un filtro local en tres niveles "
        f"(L0/L1/L2) descarto \\NExclLocal{{}} registros sin invocar al modelo de lenguaje. "
        f"Los \\NEvalLLM{{}} restantes fueron evaluados por Llama3 (T=0, protocolo six-shot) "
        f"con umbral de inclusion automatica de 75\\,\\% de confianza. Tras revision manual "
        f"del texto completo, el corpus final quedo conformado por \\NCorpus{{}} estudios.",
        encoding="utf-8",
    )
    generados.append(str(metodo_tex))
    logger.info(f"Snippet Metodologia: {metodo_tex}")

    # ── Snippet: tablas de bibliometria ──────────────────────────────────
    try:
        import pandas as pd
        if P.clusters_xlsx.exists():
            df_rev = pd.read_excel(P.clusters_xlsx, sheet_name="Top_Revistas").head(10)
            df_au  = pd.read_excel(P.clusters_xlsx, sheet_name="Top_Autores").head(10)

            tabla_rev = P.snippets / "imrd_top_revistas.tex"
            with tabla_rev.open("w", encoding="utf-8") as f:
                f.write("% Top 10 revistas del corpus\n")
                f.write("\\begin{tabular}{lrl}\n\\toprule\n")
                f.write("Revista & N & Cuartil \\\\\n\\midrule\n")
                for _, row in df_rev.iterrows():
                    t2 = str(row.get("T2", ""))[:55].replace("&", "\\&")
                    n  = row.get("N_articulos", "")
                    q  = row.get("Cuartil_predominante", "")
                    f.write(f"{t2} & {n} & {q} \\\\\n")
                f.write("\\bottomrule\n\\end{tabular}\n")
            generados.append(str(tabla_rev))
            logger.info(f"Snippet tabla revistas: {tabla_rev}")

            tabla_au = P.snippets / "imrd_top_autores.tex"
            with tabla_au.open("w", encoding="utf-8") as f:
                f.write("% Top 10 autores del corpus\n")
                f.write("\\begin{tabular}{lrl}\n\\toprule\n")
                f.write("Autor & N & Anios \\\\\n\\midrule\n")
                for _, row in df_au.iterrows():
                    au = str(row.get("AU_ppal", ""))[:40].replace("&", "\\&")
                    n  = row.get("N_articulos", "")
                    ay = str(row.get("Anios", ""))[:30]
                    f.write(f"{au} & {n} & {ay} \\\\\n")
                f.write("\\bottomrule\n\\end{tabular}\n")
            generados.append(str(tabla_au))
            logger.info(f"Snippet tabla autores: {tabla_au}")
    except Exception as e:
        logger.warning(f"No se pudieron generar tablas bibliometricas: {e}")

    return generados


# ── CLI ───────────────────────────────────────────────────────────────────────
def parsear_args():
    p = argparse.ArgumentParser(
        description="Exporta artefactos del pipeline a 07_latex_output/ y prepara IMRD.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    script_dir = Path(__file__).resolve().parent
    default_root = script_dir.parent if script_dir.name == "02_scripts" else script_dir
    p.add_argument("--root", default=str(default_root),
                   help="Raiz del proyecto (donde estan 01_raw_data, 03_filtered_data, etc.)")
    p.add_argument("--output", "-o", default="output",
                   help="Carpeta de salida (reporte y log de ejecucion).")
    p.add_argument("--log-level", "-l", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                   help="Nivel de verbosidad.")
    p.add_argument("--skip-bib", action="store_true",
                   help="No actualizar bibliography/pHazucar.bib.")
    p.add_argument("--skip-snippets", action="store_true",
                   help="No regenerar fragmentos IMRD en snippets/.")
    return p.parse_args()


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    args = parsear_args()
    log_path = configurar_logging(args.output, args.log_level)

    root = Path(args.root).resolve()
    P = Paths(root)

    logger.info("=" * 65)
    logger.info("EXPORTAR A LaTeX — RSL pH EN INDUSTRIA AZUCARERA (v3)")
    logger.info("=" * 65)
    logger.info(f"Raiz del proyecto: {root}")
    logger.info(f"LaTeX output     : {P.latex_output}")
    logger.info(f"Figures          : {P.figures}")
    logger.info(f"Snippets IMRD    : {P.snippets}")
    logger.info(f"Bib              : {P.bib_file}")
    logger.info(f"Output (log)     : {args.output}")
    logger.info(f"Log file         : {log_path}")

    P.figures.mkdir(parents=True, exist_ok=True)
    P.bibliography.mkdir(parents=True, exist_ok=True)
    P.snippets.mkdir(parents=True, exist_ok=True)

    # 1. Estado del pipeline
    logger.info("[1] Estado del pipeline (scripts 00-09):")
    checks = verificar_pipeline(P)
    prev = ""
    for script, desc, ruta, existe in checks:
        if script != prev:
            logger.info(f"  --- Script {script} ---")
            prev = script
        estado = "OK" if existe else "--"
        logger.info(f"  [{estado}] {desc}")
        if not existe:
            logger.debug(f"       Ruta esperada: {ruta}")
    n_ok = sum(1 for *_, e in checks if e)
    logger.info(f"Pipeline: {n_ok}/{len(checks)} artefactos presentes")

    # 2. Copiar figuras
    logger.info("[2] Copiando figuras -> 07_latex_output/figures/")
    errores_fig = copiar_figuras(P)

    # 3. Actualizar .bib (no destructivo)
    if not args.skip_bib:
        logger.info(f"[3] Actualizando {P.bib_file.name} (no destructivo) "
                    "+ detectando candidatos de corpus nuevos por DOI...")
        n_corpus, n_metod, warns, no_resueltas = generar_bib(P)
        logger.info(f"  Corpus nuevos (staging): {n_corpus} entradas")
        logger.info(f"  Metodologicas anadidas : {n_metod} entradas")
        if no_resueltas:
            logger.warning(f"  Claves citadas no resueltas: {no_resueltas}")
    else:
        logger.info("[3] Saltando actualizacion de .bib (--skip-bib).")
        n_corpus = n_metod = 0
        no_resueltas, warns = [], []

    # 4. Verificar \includegraphics
    logger.info("[4] Verificando referencias \\includegraphics en "
                "01_title.tex..06_appendices.tex")
    faltantes_fig = verificar_includegraphics(P)
    if not faltantes_fig:
        logger.info("  Todas las referencias \\includegraphics resueltas (o no hay .tex aun).")
    else:
        for f in faltantes_fig:
            logger.warning(f"  [--] {f}")

    # 5. Snippets IMRD
    if not args.skip_snippets:
        logger.info("[5] Generando fragmentos IMRD para \\input{}...")
        snippets = generar_snippets_imrd(P)
        logger.info(f"  {len(snippets)} fragmentos generados en {P.snippets}")
    else:
        logger.info("[5] Saltando generacion de snippets (--skip-snippets).")
        snippets = []

    # 6. Reporte final
    reporte_path = Path(args.output) / "09.exportacion_latex_report.txt"
    n_problemas = len(errores_fig) + len(faltantes_fig) + len(no_resueltas)

    reporte = [
        "=" * 65,
        f"REPORTE LaTeX — RSL pH EN INDUSTRIA AZUCARERA",
        f"{datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "=" * 65,
        "",
        f"Pipeline: {n_ok}/{len(checks)} artefactos presentes",
        f"Figuras copiadas: {5 - len(errores_fig)}/5",
        f"{P.bib_file.name}: {n_metod} entrada(s) metodologica(s) anadida(s); "
        f"{n_corpus} candidato(s) de corpus nuevo en staging",
        f"\\includegraphics faltantes: {len(faltantes_fig)}",
        f"Claves citadas no resueltas: {len(no_resueltas)}",
        f"Snippets IMRD: {len(snippets)} fragmentos",
        "",
        f"PROBLEMAS TOTALES: {n_problemas}",
        "",
    ]
    if n_problemas == 0:
        reporte += [
            "✓ Listo para compilar.",
            "",
            "COMPILAR (recomendado):",
            "  cd 07_latex_output",
            "  latexmk -pdf -pdflatex=\"pdflatex -interaction=nonstopmode\" SRL_pH.tex",
            "",
            "COMPILAR (manual):",
            "  cd 07_latex_output",
            "  pdflatex SRL_pH.tex",
            "  biber SRL_pH",
            "  pdflatex SRL_pH.tex",
            "  pdflatex SRL_pH.tex",
        ]
    else:
        reporte += [
            "Resolver los problemas listados arriba antes de compilar.",
        ]
    reporte += [
        "",
        "USO DE LOS SNIPPETS EN EL .tex DEL PAPER (IMRD):",
        "  En el preamble:",
        "    \\input{snippets/imrd_prisma_numbers.tex}",
        "",
        "  En la seccion Metodologia (M de IMRD):",
        "    \\input{snippets/imrd_methods_paragraph.tex}",
        "",
        "  En Resultados, usar las macros directamente:",
        "    La busqueda identifico \\NBruto{} registros, de los cuales \\NCorpus{}",
        "    fueron incluidos en el corpus final.",
        "",
        "  Tablas listas (en Resultados):",
        "    \\begin{table}\\centering",
        "      \\input{snippets/imrd_top_revistas.tex}",
        "      \\caption{Top 10 revistas del corpus.}",
        "    \\end{table}",
        "",
        "=" * 65,
    ]
    reporte_path.parent.mkdir(parents=True, exist_ok=True)
    reporte_path.write_text("\n".join(reporte), encoding="utf-8")
    logger.info(f"Reporte guardado: {reporte_path}")
    logger.info("=" * 65)
    logger.info("COMPLETADO. Siguiente paso: redactar el paper en LaTeX.")
    logger.info("=" * 65)


if __name__ == "__main__":
    main()