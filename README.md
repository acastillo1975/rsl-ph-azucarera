# Aprendizaje automático y control avanzado para la regulación del pH en la industria azucarera

Revisión de alcance (PRISMA-ScR) y análisis bibliométrico. Repositorio con las consultas, los datos, el *pipeline* de cribado y el manuscrito en LaTeX.

**Autores:** Abraham Castillo, D. Barreto (Escuela de Posgrado, Universidad Nacional de Ingeniería, Lima, Perú).
**Búsqueda ejecutada:** 22 de junio de 2026 (Scopus, Web of Science, IEEE Xplore; SciELO y LILACS sin resultados). Ventana 2015–2026.

## Embudo

541 registros → 353 únicos → 239 tras prefiltrado → 230 con cuartil SJR (Q1–Q4) → 2 estudios incluidos.
Cribado doble, independiente, de los 230 registros por los dos autores (κ inter-humano en el manuscrito, Apéndice D).

## Estructura

| Carpeta | Contenido |
|---|---|
| `00_query_design/` | Cadenas booleanas por base (Scopus, WoS, IEEE Xplore) |
| `01_raw_data/` | Exportaciones RIS originales de las bases |
| `02_scripts/` | *Pipeline* en Python (numerados en orden de ejecución) |
| `03_filtered_data/` | Salidas de cada etapa de filtrado, cribado (`4.filtrado_ollama.xlsx`), κ, auditorías y sensibilidad |
| `05_bibliometria/` | Matrices y figuras bibliométricas, auditoría conceptual |
| `06_prisma/` | Diagrama PRISMA 2020 |
| `09 otras_industrias/` | Evidencia contextual de otras industrias |
| `07_latex_output/` | Manuscrito (`SRL_pH.tex`, secciones `00`–`06`, tablas, figuras, bibliografía) |

## Reproducir

```
pip install -r requirements.txt
python 02_scripts/05_kappa_cohen.py --input 03_filtered_data/4.filtrado_ollama.xlsx --output 03_filtered_data --col-ollama decision_revisor1 --col-manual decision_revisor2
```

El cribado con modelo de lenguaje local (`04_filtrado_ollama.py`, `04b_sensibilidad_prompt.py`) requiere [Ollama](https://ollama.com) con `llama3:latest`; el resumen SHA-256 del modelo y el *prompt* están en el Apéndice B del manuscrito. La clasificación por cuartil usa SCImago Journal Rank 2024 (`scimagojr_2024.xlsx`, descargable de scimagojr.com; no se incluye aquí).

## Compilar el manuscrito

```
cd 07_latex_output
pdflatex SRL_pH.tex && biber SRL_pH && pdflatex SRL_pH.tex && pdflatex SRL_pH.tex
```

Los PDF de los artículos incluidos no se redistribuyen por derechos de autor; las referencias completas están en `07_latex_output/bibliography/pHazucar.bib`.
