"""
11_presubmission_check.py
==========================
RSL: Aplicaciones de ML para el Control de pH en la Industria Azucarera:
     Tendencias, Brechas y Direcciones Futuras
Verificador automatico pre-envio al journal

Ejecuta todos los checks antes de someter el paper.
Evita desk rejection por causas tecnicas prevenibles.

Checks incluidos:
  A. Estructura LaTeX   — archivos pH_azucar_*.tex requeridos
  B. Figuras            — todas las referencias \\includegraphics resueltas
  C. Bibliografia       — claves citadas presentes en pH_azucar.bib
  D. Pipeline datos     — artefactos generados por scripts 00-09
  E. PRISMA             — numeros internamente consistentes (verificados desde RIS)
  F. Metricas cribado   — sensibilidad, precision, F1
  G. Corpus final       — estudios incluidos y sus metadatos
  H. Longitud paper     — conteo de palabras estimado vs. limites de journals
  I. Dataset Zenodo     — dataset sintetico de clarificacion/encalado pH
  J. Journals objetivo  — checklist de requisitos editoriales

Numeros reales del pipeline (verificados desde archivos RIS 2026-04-02):
  Scopus: Q1=6 + Q2=2 + Q3=25 = 33
  WoS:    Q1=0 + Q2=1 + Q3=15 = 16
  IEEE:   Q1=4 + Q2=0 + Q3=9  = 13
  Bruto: 62 | Duplicados: 19 | Unicos: 43
  Excl tipo/anio: 23 | Prefiltrado: 20
  Excl cuartil: 5 | Q1-Q4: 15
  Excl L0/L1/L2: 15 | Eval LLM: 0 | Corpus actual: 0
  ESTADO: re-busqueda con queries v3 pendiente

Corpus confirmado (decision_manual == INCLUIR):
  [1] Palacio-Morales et al. (2021) — NMPC+Fuzzy pH jugo azucar (pendiente corpus completo)

Uso:
  python 11_presubmission_check.py

Salida:
  - Reporte en consola con OK / WARN / ERROR
  - 11.presubmission_report.txt
"""

import os
import re
import sys
from datetime import datetime
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = _SCRIPT_DIR.parent if _SCRIPT_DIR.name == "02_scripts" else _SCRIPT_DIR

# Rutas definidas siempre inline para este script (no depender de paths.py externo)
# Si existe un paths.py de un pipeline anterior, sus rutas pueden ser incorrectas.
class _P:
    # Carpetas principales
    raw          = ROOT / "01_raw_data"
    filtered     = ROOT / "03_filtered_data"
    bibliometria = ROOT / "05_bibliometria"
    prisma_dir   = ROOT / "06_prisma"
    zenodo       = ROOT / "07_dataset_zenodo"
    latex_output = ROOT / "08_latex_output"
    figures      = latex_output / "figures"
    bibliography = latex_output / "bibliography"

    # LaTeX
    bib_file = bibliography / "pH_azucar.bib"
    main_tex = latex_output / "pH_azucar_main.tex"
    main_pdf = latex_output / "pH_azucar_main.pdf"

    # Datos brutos
    scimago_xlsx  = raw / "scimagojr_2024.xlsx"
    fusion_unique = raw / "fusion_export.ris"

    # Pipeline filtrado
    prefiltrado_ris  = filtered / "1.prefiltrado.ris"
    q1q4_ris         = filtered / "3.filtrado_quartiles.ris"
    ollama_xlsx      = filtered / "4.filtrado_ollama.xlsx"
    ollama_ris       = filtered / "4.filtrado_ollama.ris"
    ollama_log       = filtered / "4.filtrado_ollama.log"
    notebooklm_txt   = filtered / "6.corpus_notebooklm.txt"
    tabla4_xlsx      = filtered / "6.tabla4_estructura.xlsx"

    # Bibliometria
    clusters_xlsx    = bibliometria / "7.clusters_tematicos.xlsx"
    fig_coocurrencia = bibliometria / "7.coocurrencia_keywords.png"

    # PRISMA
    fig_prisma_png = prisma_dir / "8.diagrama_prisma_2020.png"
    fig_prisma_svg = prisma_dir / "8.diagrama_prisma_2020.svg"

    # Dataset Zenodo (seccion pH clarificacion)
    zenodo_csv    = zenodo / "sugar_ph_clarification_dcs_synthetic.csv"
    zenodo_xlsx   = zenodo / "sugar_ph_clarification_dcs_synthetic.xlsx"
    zenodo_meta   = zenodo / "dataset_metadata.json"
    zenodo_readme = zenodo / "README.md"

    # Figuras LaTeX
    fig1_prisma = figures / "REPORTE_PRISMA.png"
    fig2_cooc   = figures / "vos_pH_q1.png"

    # Reporte
    presubmission_rpt = ROOT / "11.presubmission_report.txt"

P = _P()


# ==============================================================================
# NUMEROS REALES DEL PIPELINE (verificados desde archivos RIS 2026-04-02)
# Actualizar tras re-busqueda con queries v3
# ==============================================================================

PRISMA_REAL = {
    # Conteos por base y query (verificados contando ER  - en cada RIS)
    "S1": 6,   "S2": 2,   "S3": 25,  "SCOPUS": 33,
    "W1": 0,   "W2": 1,   "W3": 15,  "WOS":    16,
    "I1": 4,   "I2": 0,   "I3": 9,   "IEEE":   13,
    # Pipeline
    "bruto"         : 62,   # fusion_export_all.ris (Scopus+WoS+IEEE)
    "duplicados"    : 19,   # 62 - 43
    "unicos"        : 43,   # fusion_export.ris
    "excl_tipo_anio": 23,   # excluidos por tipo doc + fuera 2015-2026
    "prefiltrado"   : 20,   # 1_prefiltrado.ris
    "excl_cuartil"  : 5,    # excluidos por no tener cuartil SJR asignado
    "q1q4"          : 15,   # 3_filtrado_quartiles.ris (Q1-Q4)
    "excl_local"    : 15,   # filtro L0/L1/L2 (100% excluido — queries v3 pendiente)
    "eval_llm"      : 0,    # evaluados por LLM (ninguno paso el filtro local)
    "incl_llm"      : 0,    # LLM -> INCLUIR AUTO
    "excl_llm"      : 0,    # LLM -> EXCLUIR AUTO
    "corpus_final"  : 0,    # pendiente re-busqueda con queries v3
    # Nota: tras re-busqueda actualizar todos los valores
}

# Metricas del cribado (pendiente re-busqueda con queries v3)
METRICAS_CRIBADO = {
    "sensibilidad" : None,   # pendiente
    "precision"    : None,   # pendiente
    "f1"           : None,   # pendiente
    "reduccion"    : None,   # pendiente
    "vp": 0, "vn": 0, "fp": 0, "fn": 0,
    "whitelist_dois": [
        "10.3390/pr9122283",           # Palacio-Morales 2021 — corpus confirmado
        "10.1016/j.cjche.2015.01.009", # Zou 2015 — candidato relevante
        "10.3390/en18051232",          # Al-Najari 2025 — candidato relevante
    ],
    "estado": "pendiente_re_busqueda_v3",
}

# Corpus final — actualizar tras re-busqueda con queries v3
CORPUS_FINAL = [
    {
        "ref"    : "Palacio-Morales et al. (2021)",
        "doi"    : "10.3390/pr9122283",
        "clave"  : "palacio2021nmpc",
        "metodo" : "NMPC + Takagi-Sugeno Fuzzy + Pattern Search",
        "revista": "Processes",
        "cuartil": "Q2",
        "pais"   : "Colombia",
        "trl"    : "4-5",
        "nota"   : "Candidato confirmado manualmente. Corpus pendiente de re-busqueda v3.",
    },
    # AGREGAR estudios adicionales tras ejecutar queries v3 y cribado:
    # {
    #     "ref"    : "Autores (año)",
    #     "doi"    : "10.xxxx/xxxx",
    #     "clave"  : "clavebibtex",
    #     "metodo" : "Tecnica ML aplicada",
    #     "revista": "Nombre revista",
    #     "cuartil": "Q1/Q2/Q3/Q4",
    #     "pais"   : "Pais",
    #     "trl"    : "N",
    #     "nota"   : "",
    # },
]

# Journals objetivo para RSL sobre ML + control de pH + industria azucarera
JOURNAL_TARGETS = [
    {
        "nombre"         : "Journal of Process Control",
        "cuartil"        : "Q1",
        "limite_palabras": 9000,
        "limite_figuras" : 12,
        "limite_tablas"  : 8,
        "formato"        : "Elsevier — elsarticle.cls",
        "url"            : "https://www.journals.elsevier.com/journal-of-process-control",
        "notas"          : "Foco en control avanzado de procesos incluyendo pH. "
                           "Publica MPC, fuzzy, RL y revisiones sistematicas.",
    },
    {
        "nombre"         : "ISA Transactions",
        "cuartil"        : "Q1",
        "limite_palabras": 9000,
        "limite_figuras" : 12,
        "limite_tablas"  : 8,
        "formato"        : "Elsevier — elsarticle.cls",
        "url"            : "https://www.journals.elsevier.com/isa-transactions",
        "notas"          : "Publica control adaptativo de pH (Chen 2019, corpus). "
                           "Alta relevancia para instrumentacion y control industrial de pH.",
    },
    {
        "nombre"         : "Computers and Chemical Engineering",
        "cuartil"        : "Q1",
        "limite_palabras": 9000,
        "limite_figuras" : 12,
        "limite_tablas"  : 8,
        "formato"        : "Elsevier — elsarticle.cls",
        "url"            : "https://www.journals.elsevier.com/computers-and-chemical-engineering",
        "notas"          : "Publica Bardeeniz 2025 (corpus). RSL y ML para control "
                           "de pH en procesos quimicos e industriales.",
    },
    {
        "nombre"         : "Control Engineering Practice",
        "cuartil"        : "Q1",
        "limite_palabras": 8000,
        "limite_figuras" : 10,
        "limite_tablas"  : 6,
        "formato"        : "Elsevier — elsarticle.cls",
        "url"            : "https://www.journals.elsevier.com/control-engineering-practice",
        "notas"          : "Alta relevancia para implementacion de MPC, RL y fuzzy "
                           "en control de pH a escala industrial.",
    },
    {
        "nombre"         : "Processes",
        "cuartil"        : "Q2",
        "limite_palabras": 8000,
        "limite_figuras" : 12,
        "limite_tablas"  : 8,
        "formato"        : "MDPI — mdpi.cls",
        "url"            : "https://www.mdpi.com/journal/processes",
        "notas"          : "Publica Palacio-Morales 2021 (corpus principal). "
                           "Acceso abierto. Acepta RSL y menos competencia que Q1.",
    },
    {
        "nombre"         : "Sugar Tech",
        "cuartil"        : "Q2",
        "limite_palabras": 6000,
        "limite_figuras" : 8,
        "limite_tablas"  : 6,
        "formato"        : "Springer",
        "url"            : "https://link.springer.com/journal/12355",
        "notas"          : "Especializado en industria azucarera. Alta relevancia "
                           "tematica. Menor competencia. Ideal como primer envio.",
    },
]


# ==============================================================================
# UTILIDADES
# ==============================================================================

def _contar_entradas_ris(path: Path) -> int:
    if not path.exists():
        return -1
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read().count("ER  -")


def _kb(path: Path) -> str:
    if path.exists():
        return f"{path.stat().st_size / 1024:.1f} KB"
    return "—"


# ==============================================================================
# CHECKS
# ==============================================================================

def check_archivos_latex() -> list[tuple[str, str, str]]:
    """A. Verifica archivos pH_azucar_*.tex del paper."""
    requeridos = [
        (P.main_tex,
         "Archivo principal LaTeX (pH_azucar_main.tex)"),
        (P.latex_output / "pH_azucar_00_config.tex",
         "Configuracion de paquetes"),
        (P.latex_output / "pH_azucar_01_titulo.tex",
         "Titulo, autores, filiaciones"),
        (P.latex_output / "pH_azucar_02_abstract.tex",
         "Abstract / Resumen"),
        (P.latex_output / "pH_azucar_03_introduccion.tex",
         "Introduccion y preguntas de investigacion"),
        (P.latex_output / "pH_azucar_04_metodologia.tex",
         "Metodologia PRISMA"),
        (P.latex_output / "pH_azucar_05_resultados.tex",
         "Resultados"),
        (P.latex_output / "pH_azucar_06_discusion.tex",
         "Discusion y brechas"),
        (P.latex_output / "pH_azucar_07_conclusiones.tex",
         "Conclusiones"),
        (P.bib_file,
         "pH_azucar.bib"),
    ]
    out = []
    for path, desc in requeridos:
        if path.exists():
            out.append(("OK", "LaTeX",
                        f"{desc}: {path.name}  ({_kb(path)})"))
        else:
            out.append(("ERROR", "LaTeX",
                        f"FALTA — {desc}: {path.name}"))
    return out


def check_figuras() -> list[tuple[str, str, str]]:
    """B. Verifica referencias \\includegraphics en pH_azucar_*.tex."""
    out = []
    tex_files = sorted(P.latex_output.glob("pH_azucar_*.tex"))
    if not tex_files:
        return [("WARN", "Figuras",
                 "No se encontraron archivos pH_azucar_*.tex en 08_latex_output/")]
    for tex in tex_files:
        try:
            contenido = tex.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for m in re.findall(r'\\includegraphics(?:\[.*?\])?\{([^}]+)\}', contenido):
            candidatos = [
                P.figures / m,
                P.figures / (m + ".pdf"),
                P.figures / (m + ".png"),
                P.figures / (m + ".svg"),
                P.latex_output / m,
            ]
            if any(c.exists() for c in candidatos):
                out.append(("OK", "Figuras",
                            f"{tex.name}: \\includegraphics{{{m}}}"))
            else:
                out.append(("ERROR", "Figuras",
                            f"FALTA figura — {tex.name}: {m}"
                            f"  (ejecutar 07_bibliometria_python.py"
                            f" y 08_reporte_prisma.py)"))
    if not out:
        out.append(("WARN", "Figuras",
                    "No se encontraron referencias \\includegraphics en pH_azucar_*.tex"))
    return out


def check_bibliografia() -> list[tuple[str, str, str]]:
    """C. Verifica claves citadas en pH_azucar_*.tex vs. entradas en pH_azucar.bib."""
    out = []
    if not P.bib_file.exists():
        return [("ERROR", "Bib",
                 f"FALTA: {P.bib_file}  (ejecutar 10_exportar_latex.py)")]

    bib_txt    = P.bib_file.read_text(encoding="utf-8", errors="replace")
    claves_bib = set(re.findall(r'@\w+\{([^,\s]+)\s*,', bib_txt))
    n_ent      = len(claves_bib)
    out.append(("OK" if n_ent >= 8 else "WARN", "Bib",
                f"{n_ent} entradas en pH_azucar.bib"))

    citadas: set[str] = set()
    for tex in P.latex_output.glob("pH_azucar_*.tex"):
        try:
            txt = tex.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for grupo in re.findall(
            r'\\(?:parencite|textcite|cite(?:p|t|alp|alt)?)(?:\[.*?\])*\{([^}]+)\}',
            txt
        ):
            for c in grupo.split(","):
                c = c.strip()
                if c:
                    citadas.add(c)

    # Verificar claves del corpus confirmado
    for estudio in CORPUS_FINAL:
        clave = estudio["clave"]
        if clave in claves_bib:
            out.append(("OK", "Bib",
                        f"Corpus en .bib: {clave} ({estudio['ref']})"))
        else:
            out.append(("WARN", "Bib",
                        f"Corpus pendiente en .bib: {clave} ({estudio['ref']}) "
                        f"— agregar tras corpus completo"))

    no_enc = sorted(citadas - claves_bib)
    for c in no_enc:
        out.append(("ERROR", "Bib",
                    f"Clave citada no en .bib: cite{{{c}}}"))

    no_usadas = claves_bib - citadas
    if no_usadas and citadas:
        out.append(("WARN", "Bib",
                    f"{len(no_usadas)} entradas en .bib no citadas en .tex: "
                    f"{', '.join(sorted(no_usadas)[:4])}"
                    f"{'...' if len(no_usadas) > 4 else ''}"))

    if not no_enc:
        out.append(("OK", "Bib",
                    f"Todas las claves citadas ({len(citadas)}) estan en el .bib"))
    return out


def check_pipeline_datos() -> list[tuple[str, str, str]]:
    """D. Verifica artefactos del pipeline scripts 00-09."""
    checks = [
        # Script 00 — queries y exportaciones RIS
        (P.raw / "scopus_export_1.ris",  "00  scopus_export_1.ris (v3)",         True),
        (P.raw / "scopus_export_2.ris",  "00  scopus_export_2.ris (v3)",         True),
        (P.raw / "scopus_export_3.ris",  "00  scopus_export_3.ris (v3)",         True),
        (P.raw / "wos_export_1.ris",     "00  wos_export_1.ris (v3)",            True),
        (P.raw / "wos_export_2.ris",     "00  wos_export_2.ris (v3)",            True),
        (P.raw / "wos_export_3.ris",     "00  wos_export_3.ris (v3)",            True),
        (P.raw / "ieee_export_1.ris",    "00  ieee_export_1.ris (v3)",           True),
        (P.raw / "ieee_export_2.ris",    "00  ieee_export_2.ris (v3)",           True),
        (P.raw / "ieee_export_3.ris",    "00  ieee_export_3.ris (v3)",           True),
        (P.raw / "fusion_export_all.ris","00  fusion_export_all.ris (62 reg.)",  True),
        (P.fusion_unique,                "00  fusion_export.ris (43 unicos)",     True),
        # Scripts 01-03
        (P.prefiltrado_ris,              "01  1_prefiltrado.ris (20 reg.)",       True),
        (P.filtered / "2_fusionado_con_cuartiles.ris",
                                         "02  2_fusionado_con_cuartiles.ris",     True),
        (P.q1q4_ris,                     "03  3_filtrado_quartiles.ris (15 Q1-Q4)",  True),
        # Script 04 — cribado Ollama
        (P.ollama_xlsx,                  "04  4.filtrado_ollama.xlsx",            True),
        (P.ollama_ris,                   "04  4.filtrado_ollama.ris",             True),
        (P.ollama_log,                   "04  4.filtrado_ollama.log",             False),
        # Script 06 — NotebookLM
        (P.notebooklm_txt,               "06  6.corpus_notebooklm.txt",          False),
        (P.tabla4_xlsx,                  "06  6.tabla4_estructura.xlsx",         False),
        # Script 07 — bibliometria
        (P.clusters_xlsx,                "07  7.clusters_tematicos.xlsx",         True),
        (P.fig_coocurrencia,             "07  7.coocurrencia_keywords.png",        True),
        # Script 08 — PRISMA
        (P.fig_prisma_png,               "08  8.diagrama_prisma_2020.png",         True),
        # Script 09 — dataset sintetico pH
        (P.zenodo_csv,                   "09  sugar_ph_clarification_dcs_synthetic.csv", True),
        (P.zenodo_xlsx,                  "09  sugar_ph_clarification_dcs_synthetic.xlsx", True),
        (P.zenodo_meta,                  "09  dataset_metadata.json",              True),
        (P.zenodo_readme,                "09  README.md (Zenodo)",                 True),
        # Script 10 — figuras LaTeX
        (P.fig1_prisma,                  "10  figures/REPORTE_PRISMA.png",         True),
        (P.fig2_cooc,                    "10  figures/vos_pH_q1.png",              True),
    ]
    out = []
    for path, desc, requerido in checks:
        if path.exists():
            out.append(("OK", "Pipeline", f"{desc}  ({_kb(path)})"))
        elif requerido:
            out.append(("ERROR", "Pipeline", f"FALTA — {desc}"))
        else:
            out.append(("WARN", "Pipeline", f"Opcional no generado — {desc}"))
    return out


def check_prisma_consistencia() -> list[tuple[str, str, str]]:
    """E. Verifica consistencia interna de los numeros PRISMA."""
    out = []
    n   = PRISMA_REAL

    checks_eq = [
        ("Bruto = Scopus + WoS + IEEE",
         n["SCOPUS"] + n["WOS"] + n["IEEE"],   n["bruto"]),
        ("Unicos = Bruto - Duplicados",
         n["bruto"] - n["duplicados"],          n["unicos"]),
        ("Prefiltrado = Unicos - Excl_tipo_anio",
         n["unicos"] - n["excl_tipo_anio"],     n["prefiltrado"]),
        ("Q1Q4 = Prefiltrado - Excl_cuartil",
         n["prefiltrado"] - n["excl_cuartil"],  n["q1q4"]),
        ("Eval_LLM = Q1Q4 - Excl_local",
         n["q1q4"] - n["excl_local"],           n["eval_llm"]),
        ("Eval_LLM = Incl_LLM + Excl_LLM",
         n["incl_llm"] + n["excl_llm"],         n["eval_llm"]),
    ]

    for desc, calculado, esperado in checks_eq:
        if calculado == esperado:
            out.append(("OK", "PRISMA",
                        f"{desc}: {calculado} = {esperado}"))
        else:
            out.append(("ERROR", "PRISMA",
                        f"Inconsistencia — {desc}: calculado={calculado} esperado={esperado}"))

    # Corpus <= Incl_LLM solo si hay resultados
    if n["incl_llm"] == 0 and n["corpus_final"] == 0:
        out.append(("WARN", "PRISMA",
                    "Corpus final = 0 — pendiente re-busqueda con queries v3"))
    elif n["corpus_final"] <= n["incl_llm"]:
        out.append(("OK", "PRISMA",
                    f"Corpus final ({n['corpus_final']}) <= Incl LLM ({n['incl_llm']})"))
    else:
        out.append(("ERROR", "PRISMA",
                    f"Corpus final ({n['corpus_final']}) > Incl LLM ({n['incl_llm']}) — imposible"))

    # Verificar conteos reales desde archivos RIS
    out.append(("─", "PRISMA", "Verificacion desde archivos RIS:"))
    ris_checks = [
        (P.raw / "fusion_export_all.ris",  n["bruto"],       "fusion_export_all.ris"),
        (P.fusion_unique,                  n["unicos"],      "fusion_export.ris"),
        (P.prefiltrado_ris,                n["prefiltrado"], "1_prefiltrado.ris"),
        (P.q1q4_ris,                       n["q1q4"],        "3_filtrado_quartiles.ris"),
        (P.ollama_ris,                     n["incl_llm"],    "4.filtrado_ollama.ris"),
    ]
    for path, esperado, nombre in ris_checks:
        real = _contar_entradas_ris(path)
        if real == -1:
            out.append(("WARN", "PRISMA",
                        f"  {nombre}: archivo no encontrado"))
        elif real == esperado:
            out.append(("OK", "PRISMA",
                        f"  {nombre}: {real} entradas (correcto)"))
        else:
            out.append(("ERROR", "PRISMA",
                        f"  {nombre}: {real} entradas, esperadas {esperado}"))

    return out


def check_metricas_cribado() -> list[tuple[str, str, str]]:
    """F. Verifica metricas del cribado semantico LLM."""
    out = []
    m = METRICAS_CRIBADO
    n = PRISMA_REAL

    out.append(("─", "Metricas",
                f"Estado: {m['estado']}"))
    out.append(("─", "Metricas",
                f"Evaluados por LLM: {n['eval_llm']}  "
                f"(VP={m['vp']}, VN={m['vn']}, FP={m['fp']}, FN={m['fn']})"))

    if m["sensibilidad"] is None:
        out.append(("WARN", "Metricas",
                    "Sensibilidad: pendiente — re-ejecutar 04_filtrado_ollama.py "
                    "con queries v3"))
        out.append(("WARN", "Metricas",
                    "Precision: pendiente — re-ejecutar 04_filtrado_ollama.py"))
        out.append(("WARN", "Metricas",
                    "F1: pendiente"))
        out.append(("WARN", "Metricas",
                    "Reduccion carga manual: pendiente"))
    else:
        mark = "OK" if m["sensibilidad"] == 100.0 else "WARN"
        out.append((mark, "Metricas",
                    f"Sensibilidad: {m['sensibilidad']:.1f}%  (FN={m['fn']})"))
        mark = "OK" if m["precision"] >= 80.0 else "WARN"
        out.append((mark, "Metricas",
                    f"Precision: {m['precision']:.1f}%  (objetivo > 80 %)"))
        out.append(("OK", "Metricas",
                    f"F1: {m['f1']:.1f}%"))
        out.append(("OK", "Metricas",
                    f"Reduccion carga manual: {m['reduccion']:.1f}%"))

    # DOI Whitelist
    out.append(("OK", "Metricas",
                f"DOI Whitelist: {len(m['whitelist_dois'])} papers pre-validados"))
    for doi in m["whitelist_dois"]:
        out.append(("OK", "Metricas", f"  -> {doi}"))

    # Leer metricas del Excel si existe
    if P.ollama_xlsx.exists():
        try:
            import pandas as pd
            df_m = pd.read_excel(P.ollama_xlsx, sheet_name="Metricas")
            def _get(k):
                row = df_m[df_m.iloc[:, 0].astype(str).str.contains(
                    k, case=False, na=False)]
                return row.iloc[0, 1] if not row.empty else None
            modelo = _get("Modelo")
            total  = _get("Total procesados")
            incl   = _get("^INCLUIR$")
            if modelo:
                out.append(("OK", "Metricas",
                            f"Modelo LLM (Excel): {modelo}"))
            if total is not None:
                out.append(("OK" if int(total) == n["q1q4"] else "WARN",
                            "Metricas",
                            f"Total procesados Excel: {total} (esperado {n['q1q4']})"))
            if incl is not None:
                out.append(("OK" if int(incl) == n["incl_llm"] else "WARN",
                            "Metricas",
                            f"INCLUIR en Excel: {incl} (esperado {n['incl_llm']})"))
        except Exception as e:
            out.append(("WARN", "Metricas",
                        f"No se pudo leer hoja Metricas del Excel: {e}"))
    else:
        out.append(("WARN", "Metricas",
                    f"Excel Ollama no encontrado: {P.ollama_xlsx}"))

    out.append(("WARN", "Metricas",
                "Kappa de Cohen: pendiente — requiere corpus completo"))
    out.append(("─", "Metricas",
                "  -> Protocolo: six-shot + filtro L1 relajado + umbral >= 75%"))
    return out


def check_corpus_final() -> list[tuple[str, str, str]]:
    """G. Verifica datos del corpus final."""
    n = PRISMA_REAL
    out = [("─", "Corpus",
            f"Corpus final: {len(CORPUS_FINAL)} estudios confirmados "
            f"| Pipeline total (decision_manual): {n['corpus_final']}")]

    if n["corpus_final"] == 0:
        out.append(("WARN", "Corpus",
                    "Corpus = 0 — pendiente re-busqueda con queries v3"))
        out.append(("─", "Corpus",
                    "Queries v3 incluyen: alkalinization, ANFIS, NMPC, "
                    "sugar juice pH, pattern search, self-tuning"))

    for i, est in enumerate(CORPUS_FINAL, 1):
        out.append(("─", "Corpus",
                    f"  [{i}] {est['ref']} — {est['metodo']}"))
        out.append(("─", "Corpus",
                    f"       {est['revista']} ({est['cuartil']}) "
                    f"| TRL {est['trl']} | {est['pais']}"))
        out.append(("─", "Corpus", f"       DOI: {est['doi']}"))
        if est.get("nota"):
            out.append(("WARN" if "pendiente" in est["nota"].lower() else "─",
                        "Corpus", f"       Nota: {est['nota']}"))

    # Verificar tabla4 en Excel
    if P.tabla4_xlsx.exists():
        try:
            import pandas as pd
            # Try both possible sheet names
            xf = pd.ExcelFile(P.tabla4_xlsx)
            hojas = xf.sheet_names
            hoja = "Tabla4_pH" if "Tabla4_pH" in hojas else hojas[0]
            df_t4 = pd.read_excel(P.tabla4_xlsx, sheet_name=hoja)
            n_filas   = len(df_t4)
            cols_vacias = df_t4.select_dtypes(include="object").apply(
                lambda c: c.replace("", None).isna().all()
            ).sum()
            out.append(("OK" if n_filas >= 1 else "WARN", "Corpus",
                        f"Tabla 4 ({hoja}): {n_filas} filas"))
            if cols_vacias > 8:
                out.append(("WARN", "Corpus",
                            f"Tabla 4: {cols_vacias} columnas vacias "
                            f"— completar con NotebookLM tras corpus completo"))
            else:
                out.append(("OK", "Corpus", "Tabla 4: columnas completadas"))
        except Exception as e:
            out.append(("WARN", "Corpus",
                        f"No se pudo leer 6.tabla4_estructura.xlsx: {e}"))
    else:
        out.append(("WARN", "Corpus",
                    "6.tabla4_estructura.xlsx no encontrado "
                    "— ejecutar 06_preparar_notebooklm.py"))
    return out


def check_longitud_paper() -> list[tuple[str, str, str]]:
    """H. Estima longitud del paper contando palabras en los .tex."""
    out            = []
    total_palabras = 0
    total_tablas   = 0
    total_figuras  = 0

    cuerpo = [
        "pH_azucar_02_abstract.tex",
        "pH_azucar_03_introduccion.tex",
        "pH_azucar_04_metodologia.tex",
        "pH_azucar_05_resultados.tex",
        "pH_azucar_06_discusion.tex",
        "pH_azucar_07_conclusiones.tex",
    ]
    for nombre in cuerpo:
        path = P.latex_output / nombre
        if not path.exists():
            out.append(("WARN", "Longitud",
                        f"Archivo no encontrado: {nombre}"))
            continue
        contenido = path.read_text(encoding="utf-8", errors="replace")
        limpio = re.sub(r'\\[a-zA-Z]+\{[^}]*\}', ' ', contenido)
        limpio = re.sub(r'\\[a-zA-Z]+',           ' ', limpio)
        limpio = re.sub(r'[%{}\[\]_^$]',          ' ', limpio)
        n_palabras    = len(limpio.split())
        total_palabras += n_palabras
        total_tablas  += contenido.count(r'\begin{table')
        total_tablas  += contenido.count(r'\begin{longtblr')
        total_figuras += contenido.count(r'\begin{figure')
        out.append(("─", "Longitud",
                    f"  {nombre}: ~{n_palabras:,} palabras"))

    mark_palabras = ("OK"   if total_palabras >= 4000 else
                     "WARN" if total_palabras >= 2000 else "ERROR")
    out.append((mark_palabras, "Longitud",
                f"Palabras totales estimadas (cuerpo): ~{total_palabras:,}"))
    out.append(("OK" if total_tablas >= 2 else "WARN", "Longitud",
                f"Tablas en el paper: {total_tablas}"))
    out.append(("OK" if total_figuras >= 2 else "WARN", "Longitud",
                f"Figuras en el paper: {total_figuras}"))

    out.append(("─", "Longitud", "Comparacion con limites de journals objetivo:"))
    for j in JOURNAL_TARGETS:
        excede = total_palabras > j["limite_palabras"]
        out.append(("WARN" if excede else "OK", "Longitud",
                    f"  {j['nombre']} ({j['cuartil']}): "
                    f"limite {j['limite_palabras']:,} — "
                    f"{'EXCEDE' if excede else 'OK'}"))
    return out


def check_dataset_zenodo() -> list[tuple[str, str, str]]:
    """I. Verifica el dataset sintetico de clarificacion/encalado de pH."""
    out = []
    checks_zen = [
        (P.zenodo_csv,    "sugar_ph_clarification_dcs_synthetic.csv",  True),
        (P.zenodo_xlsx,   "sugar_ph_clarification_dcs_synthetic.xlsx", True),
        (P.zenodo_meta,   "dataset_metadata.json",                     True),
        (P.zenodo_readme, "README.md",                                 True),
        (P.zenodo / "ZENODO_UPLOAD_CHECKLIST.txt",
                          "ZENODO_UPLOAD_CHECKLIST.txt",               False),
    ]
    for path, nombre, req in checks_zen:
        if path.exists():
            out.append(("OK", "Zenodo", f"{nombre}  ({_kb(path)})"))
        elif req:
            out.append(("ERROR", "Zenodo",
                        f"FALTA — {nombre}  (ejecutar 09_dataset_sintetico_zenodo.py)"))
        else:
            out.append(("WARN", "Zenodo",
                        f"Opcional no encontrado — {nombre}"))

    # Verificar columnas clave del CSV (variables de pH clarificacion)
    if P.zenodo_csv.exists():
        try:
            import pandas as pd
            df_zen = pd.read_csv(P.zenodo_csv, nrows=5)
            cols   = list(df_zen.columns)
            n_cols = len(cols)
            out.append(("OK" if n_cols >= 25 else "WARN", "Zenodo",
                        f"CSV: {n_cols} columnas (esperado >= 25)"))
            cols_req_pH = [
                "ph_clarificado",       # TARGET principal
                "ph_entrada",           # input clave
                "dosis_cal_gm3",        # variable manipulada
                "ph_post_encalado",     # estado intermedio
                "error_pH",             # desviacion del setpoint
            ]
            for col_req in cols_req_pH:
                if col_req in cols:
                    out.append(("OK", "Zenodo",
                                f"  Columna pH presente: {col_req}"))
                else:
                    out.append(("ERROR", "Zenodo",
                                f"  Columna pH FALTA: {col_req}"))
        except Exception as e:
            out.append(("WARN", "Zenodo", f"No se pudo leer CSV: {e}"))

    # Verificar DOI Zenodo en titulo
    if P.main_tex.exists():
        main_txt = P.main_tex.read_text(encoding="utf-8", errors="replace")
        if "zenodo.XXXXXXX" in main_txt or "XXXXXXX" in main_txt:
            out.append(("WARN", "Zenodo",
                        "DOI de Zenodo pendiente en pH_azucar_01_titulo.tex "
                        "— actualizar tras publicar el deposito"))
        else:
            out.append(("OK", "Zenodo",
                        "DOI de Zenodo actualizado en pH_azucar_01_titulo.tex"))

    out.append(("WARN", "Zenodo",
                "Verificar: subir zenodo_package/ a https://zenodo.org/deposit/new"))
    return out


def check_journals() -> list[tuple[str, str, str]]:
    """J. Checklist de requisitos editoriales por journal objetivo."""
    out = [("─", "Journals",
            "Journals objetivo para RSL de ML + control de pH en industria azucarera:")]
    for j in JOURNAL_TARGETS:
        out.append(("─", "Journals",
                    f"  {j['nombre']} ({j['cuartil']})"
                    f"  — limite: {j['limite_palabras']:,} palabras, "
                    f"{j['limite_figuras']} figs, {j['limite_tablas']} tabs"))
        out.append(("─", "Journals", f"    {j['notas']}"))
        out.append(("─", "Journals", f"    URL: {j['url']}"))

    out.append(("WARN", "Journals",
                "Revisar scope, author guidelines y cover letter antes de someter"))
    out.append(("WARN", "Journals",
                "Justificar corpus pequeno en introduccion: tema muy nicho, "
                "literatura escasa -> valida la necesidad de la RSL"))
    out.append(("WARN", "Journals",
                "Verificar que las queries v3 esten documentadas en Supplementary Material"))
    return out


# ==============================================================================
# MAIN
# ==============================================================================

def main():
    print("=" * 70)
    print("  PRE-SUBMISSION CHECK — RSL ML PARA pH EN INDUSTRIA AZUCARERA")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Raiz del proyecto: {ROOT}")
    print("=" * 70)

    secciones = [
        ("A. Estructura LaTeX",  check_archivos_latex),
        ("B. Figuras",           check_figuras),
        ("C. Bibliografia",      check_bibliografia),
        ("D. Pipeline datos",    check_pipeline_datos),
        ("E. PRISMA",            check_prisma_consistencia),
        ("F. Metricas cribado",  check_metricas_cribado),
        ("G. Corpus final",      check_corpus_final),
        ("H. Longitud paper",    check_longitud_paper),
        ("I. Dataset Zenodo",    check_dataset_zenodo),
        ("J. Journals objetivo", check_journals),
    ]

    todos = []
    for titulo, fn in secciones:
        print(f"\n  {'─' * 60}")
        print(f"  {titulo}")
        print(f"  {'─' * 60}")
        resultados = fn()
        for mark, cat, msg in resultados:
            if mark == "─":
                print(f"  {msg}")
            elif mark == "OK":
                print(f"  [OK]   [{cat:10}] {msg}")
            elif mark == "WARN":
                print(f"  [WARN] [{cat:10}] {msg}")
            elif mark == "ERROR":
                print(f"  [ERR]  [{cat:10}] {msg}")
            else:
                print(f"  [{mark}]  [{cat:10}] {msg}")
        todos.extend(resultados)

    n_ok   = sum(1 for m, _, _ in todos if m == "OK")
    n_warn = sum(1 for m, _, _ in todos if m == "WARN")
    n_err  = sum(1 for m, _, _ in todos if m == "ERROR")

    resumen = (
        f"\n{'=' * 70}\n"
        f"  RESUMEN FINAL — RSL ML PARA pH EN INDUSTRIA AZUCARERA\n"
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"{'=' * 70}\n"
        f"  [OK]   : {n_ok}\n"
        f"  [WARN] : {n_warn}\n"
        f"  [ERR]  : {n_err}\n"
        f"\n"
        f"  NUMEROS PRISMA VERIFICADOS (2026-04-02):\n"
        f"    Bruto  : {PRISMA_REAL['bruto']}  "
        f"(Scopus={PRISMA_REAL['SCOPUS']} | WoS={PRISMA_REAL['WOS']} | "
        f"IEEE={PRISMA_REAL['IEEE']})\n"
        f"    Unicos : {PRISMA_REAL['unicos']}  "
        f"Prefiltrado: {PRISMA_REAL['prefiltrado']}  "
        f"Q1-Q4: {PRISMA_REAL['q1q4']}\n"
        f"    Excl L0/L1/L2: {PRISMA_REAL['excl_local']}  "
        f"Eval LLM: {PRISMA_REAL['eval_llm']}  "
        f"Corpus actual: {PRISMA_REAL['corpus_final']}\n"
        f"\n"
        f"  ESTADO DEL CORPUS:\n"
        f"    Candidato confirmado: Palacio-Morales et al. (2021)\n"
        f"    DOI: 10.3390/pr9122283\n"
        f"    Re-busqueda con queries v3 PENDIENTE\n"
        f"\n"
    )

    if n_err == 0 and n_warn == 0:
        resumen += "  El paper esta listo para compilar y someter.\n"
    elif n_err == 0:
        resumen += "  Revisar los avisos [WARN] antes de someter.\n"
    else:
        resumen += "  Resolver todos los errores [ERR] antes de compilar.\n"

    resumen += (
        f"\n  PROXIMOS PASOS:\n"
        f"  1. Re-ejecutar busquedas con queries v3 (alkalinization, ANFIS, NMPC).\n"
        f"  2. Re-ejecutar: python 04_filtrado_ollama.py\n"
        f"  3. Agregar papers a decision_manual en 4.filtrado_ollama.xlsx.\n"
        f"  4. Ejecutar scripts 05 al 10 con corpus actualizado.\n"
        f"  5. Resolver errores [ERR] listados arriba.\n"
        f"  6. Compilar el paper:\n"
        f"     cd 08_latex_output\n"
        f"     latexmk -pdf -biber pH_azucar_main.tex\n"
        f"  7. Revisar pH_azucar_main.pdf generado.\n"
        f"  8. Publicar dataset en Zenodo y actualizar DOI.\n"
        f"  9. Preparar cover letter y someter al journal.\n"
        f"{'=' * 70}\n"
    )

    print(resumen)

    rpt = ROOT / "11.presubmission_report.txt"
    rpt.write_text(resumen, encoding="utf-8")
    print(f"  Reporte guardado: {rpt}")


if __name__ == "__main__":
    main()
