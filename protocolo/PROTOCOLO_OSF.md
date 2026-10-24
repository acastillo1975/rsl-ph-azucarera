# Protocolo de revisión de alcance (registro retrospectivo)

**Título:** Aprendizaje automático y control avanzado para la regulación del pH en la industria azucarera: una revisión de alcance y análisis bibliométrico
**Autores:** Abraham Castillo (ORCID 0000-0001-6033-617X); D. Barreto (ORCID 0000-0002-0134-1291). Escuela de Posgrado, Universidad Nacional de Ingeniería, Lima, Perú.
**Tipo de estudio:** revisión de alcance (PRISMA-ScR) con componente bibliométrico.
**Repositorio de código y datos:** https://github.com/acastillo1975/rsl-ph-azucarera
**English version:** `PROTOCOL_OSF_en.md` (same content and figures).

## 0. Declaración de registro retrospectivo

Este protocolo se registra **después** de ejecutar la búsqueda bibliográfica (22 de junio de 2026) y después de un cribado preliminar sobre revistas Q1–Q2. Documenta el diseño, los criterios y las consultas tal como se aplicaron; **no es una preespecificación independiente**. Las desviaciones respecto del diseño inicial se detallan en la sección 9. La fecha de este registro es la que consta en OSF.

## 1. Objetivo

Cartografiar la extensión, la naturaleza y el nivel de madurez de la evidencia sobre aprendizaje automático (AA), control avanzado y sensores virtuales aplicados a la regulación del pH en la clarificación y el encalado del jugo azucarero, e identificar vacíos que orienten una agenda de investigación.

## 2. Marco PICOC y preguntas de investigación

- **Población:** procesos de clarificación y encalado de jugo de caña o remolacha.
- **Intervención:** técnicas de AA, control avanzado o sensores virtuales.
- **Comparación:** PID, dosificación manual o lazo abierto.
- **Resultados:** desempeño del control de pH y evidencia de modelado.
- **Contexto:** revistas indexadas en SJR, cualquier cuartil, 2015–2026.

| | Pregunta |
|---|---|
| **RQ1** | ¿Cómo se ha modelado y estimado la dinámica del pH en la clarificación azucarera mediante sensores virtuales, identificación de sistemas y modelos *data-driven*? |
| **RQ2** | ¿Qué estrategias de control avanzado (MPC/NMPC, lógica difusa, metaheurísticas) se han aplicado al lazo de pH y cómo se comparan con el control PID convencional? |
| **RQ3** | ¿Qué técnicas de aprendizaje automático, aprendizaje por refuerzo y modelos híbridos se han empleado, y qué barreras limitan su adopción industrial? |

## 3. Criterios de elegibilidad

**Inclusión**
1. Artículos de revista originales publicados entre 2015 y 2026 (incluye *early access* con año editorial 2026).
2. Revista con cuartil en SCImago Journal Rank 2024 (criterio *best quartile*), Q1–Q4.
3. Aplicación de al menos una técnica de AA, de control avanzado (todo esquema distinto de un PID de ganancia fija: MPC/NMPC, difuso o neuro-difuso, adaptativo) o de sensor virtual al pH de la clarificación o el encalado del jugo; se admite la identificación o sintonía de controladores con metaheurísticas o AA.
4. Reporte de al menos una métrica cuantitativa de desempeño.

**Exclusión**
1. Actas de congreso, capítulos y series de libros.
2. Fuera del rango temporal.
3. Revista sin cuartil SJR en SCImago 2024.
4. Procesos ajenos al lazo de pH de la clarificación azucarera (fermentación alcohólica, aguas residuales, jugos de fruta, farmacéutica, extracción mineral, análisis sensorial).
5. pH tratado solo como descriptor químico o variable de entrada, sin objetivo de predicción, estimación o control.

## 4. Fuentes y estrategia de búsqueda

- **Bases:** Scopus, Web of Science, IEEE Xplore (nueve consultas booleanas, tres por base, una por pregunta de investigación) y una consulta combinada adaptada para SciELO y LILACS.
- **Fecha de ejecución:** 22 de junio de 2026. **Ventana temporal:** 2015–2026.
- **Cadenas completas:** carpeta `00_query_design/` del repositorio (`queries_scopus.txt`, `queries_wos.txt`, `queries_ieee.txt`, `queries_TODAS_LAS_BASES.txt`) y Apéndice A del manuscrito.
- **Cláusulas `AND NOT`:** se usaron para excluir dominios ruidosos detectados en una búsqueda piloto (*wastewater*, *bioethanol*, *fermentation broth*, *pharmaceutical*, *soil*, *blood*, *wine*, *dairy*, *bioreactor*). No se ejecutó una búsqueda de control sin ellas ni rastreo sistemático de citas.
- **Resultados:** Scopus 312; WoS 188; IEEE Xplore 41 (total 541). SciELO y LILACS: 0 resultados.

## 5. Proceso de selección

1. Deduplicación por DOI y por coincidencia aproximada de títulos (umbral ≥ 95 %, `rapidfuzz`): 541 → 353 registros únicos.
2. Prefiltrado por tipo de documento (48 excluidos) y año (66 excluidos): 239.
3. Asignación de cuartil SJR 2024 y filtro Q1–Q4 (9 sin cuartil excluidos): 230.
4. **Cribado doble por título y resumen**, independiente y ciego, por dos revisores humanos sobre los 230 registros. Desacuerdos: consenso; si persisten, tercer revisor.
5. Lectura a texto completo de los candidatos.
6. Chequeo secundario con un filtro léxico local y un modelo de lenguaje local (Llama 3 8B, T = 0, vía Ollama); **no** sustituye el juicio humano.

Fiabilidad: κ de Cohen inter-humano como métrica primaria, con concordancia observada, PABAK e intervalos de Wilson al 95 %.

## 6. Extracción de datos y riesgo de sesgo

Matriz de extracción con metadatos, técnica de modelado y control, variables manipuladas y controlada, perturbaciones, origen de los datos, nivel de validación (simulación, banco, planta piloto, planta industrial), métricas reportadas y nivel TRL (NASA). Riesgo de sesgo con una herramienta *ad hoc* de cinco dominios. Síntesis narrativa.

## 7. Análisis bibliométrico

Red de co-ocurrencia de palabras clave del corpus Q1–Q4 (*bibliometrix*, VOSviewer; detección de comunidades por el método de Louvain) y verificación léxica independiente de los conceptos núcleo sobre los 353 registros únicos.

## 8. Análisis de sensibilidad

(i) Caracterización de los registros *in-domain* excluidos por criterios formales (revistas sin cuartil, actas y capítulos); (ii) auditoría del filtro léxico local; (iii) efecto de la fuga de información en el *prompt* del modelo de lenguaje.

## 9. Desviaciones respecto del diseño inicial

| Fecha | Cambio | Motivo | Conocimiento de resultados |
|---|---|---|---|
| 13 ago 2026 | Umbral de cuartil SJR ampliado de Q1–Q2 a Q1–Q4 | La búsqueda no había restringido por cuartil; en un dominio de nicho un umbral alto puede descartar evidencia *in-domain* | **Sí**: un cribado preliminar sobre Q1–Q2 había identificado un único estudio |
| (anterior al cribado definitivo) | Ventana temporal extendida hasta 2026 | Incorporar publicaciones *early access* | No |

Fuente potencial de sesgo declarada y acotada con el análisis de sensibilidad (sección 8).

## 10. Datos, código y materiales

Toda la documentación (cadenas de búsqueda, decisiones de cribado de ambos revisores, matriz de confusión, scripts, *prompt* y resumen SHA-256 del modelo) está en https://github.com/acastillo1975/rsl-ph-azucarera.
