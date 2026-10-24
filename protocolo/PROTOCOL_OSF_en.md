# Scoping review protocol (retrospective registration)

**Title:** Machine Learning and Advanced Control for pH Regulation in the Sugar Industry: A Scoping Review and Bibliometric Analysis
**Authors:** Abraham Castillo (ORCID 0000-0001-6033-617X); D. Barreto (ORCID 0000-0002-0134-1291). Graduate School, Universidad Nacional de Ingeniería, Lima, Peru.
**Study type:** scoping review (PRISMA-ScR) with a bibliometric component.
**Code and data repository:** https://github.com/acastillo1975/rsl-ph-azucarera
**Spanish version:** `PROTOCOLO_OSF.md` (the manuscript is written in Spanish; this file is a translation with identical content and figures).

## 0. Statement of retrospective registration

This protocol is registered **after** the literature search was run (22 June 2026) and after a preliminary screening of Q1–Q2 journals. It documents the design, criteria and queries as they were applied; it is **not an independent pre-specification**. Deviations from the initial design are detailed in section 9. The registration date is the one recorded by OSF.

## 1. Objective

To map the extent, nature and maturity level of the evidence on machine learning (ML), advanced control and virtual sensors applied to pH regulation in sugar-juice clarification and liming, and to identify gaps that can guide a research agenda.

## 2. PICOC framework and research questions

- **Population:** clarification and liming processes of sugarcane or sugar-beet juice.
- **Intervention:** ML techniques, advanced control or virtual sensors.
- **Comparison:** PID, manual dosing or open loop.
- **Outcomes:** pH control performance and modelling evidence.
- **Context:** journals indexed in SJR, any quartile, 2015–2026.

| | Question |
|---|---|
| **RQ1** | How has pH dynamics in sugar clarification been modelled and estimated through virtual sensors, system identification and data-driven models? |
| **RQ2** | Which advanced control strategies (MPC/NMPC, fuzzy logic, metaheuristics) have been applied to the pH loop, and how do they compare with conventional PID control? |
| **RQ3** | Which machine-learning, reinforcement-learning and hybrid techniques have been used, and what barriers limit their industrial adoption? |

## 3. Eligibility criteria

**Inclusion**
1. Original journal articles published between 2015 and 2026 (including early-access records with a 2026 editorial year).
2. Journal with a quartile in SCImago Journal Rank 2024 (best-quartile criterion), Q1–Q4.
3. Application of at least one ML technique, advanced control scheme (any scheme other than a fixed-gain PID: MPC/NMPC, fuzzy or neuro-fuzzy, adaptive) or virtual sensor to the pH of juice clarification or liming; identification or tuning of controllers with metaheuristics or ML is admitted.
4. Report of at least one quantitative performance metric.

**Exclusion**
1. Conference proceedings, book chapters and book series.
2. Outside the time window.
3. Journal without an SJR quartile in SCImago 2024.
4. Processes unrelated to the pH loop of sugar clarification (alcoholic fermentation, wastewater, fruit juices, pharmaceuticals, mineral extraction, sensory analysis).
5. pH treated only as a chemical descriptor or input variable, with no goal of prediction, estimation or control.

## 4. Information sources and search strategy

- **Databases:** Scopus, Web of Science, IEEE Xplore (nine Boolean queries, three per database, one per research question) and one combined query adapted for SciELO and LILACS.
- **Date run:** 22 June 2026. **Time window:** 2015–2026.
- **Full search strings:** `00_query_design/` folder of the repository (`queries_scopus.txt`, `queries_wos.txt`, `queries_ieee.txt`, `queries_TODAS_LAS_BASES.txt`) and Appendix A of the manuscript.
- **`AND NOT` clauses:** used to exclude noisy domains detected in a pilot search (wastewater, bioethanol, fermentation broth, pharmaceutical, soil, blood, wine, dairy, bioreactor). No control search without them and no systematic citation chasing were carried out.
- **Results:** Scopus 312; WoS 188; IEEE Xplore 41 (total 541). SciELO and LILACS: 0 results.

## 5. Selection process

1. De-duplication by DOI and fuzzy title matching (threshold ≥ 95%, `rapidfuzz`): 541 → 353 unique records.
2. Pre-filtering by document type (48 excluded) and year (66 excluded): 239.
3. SJR 2024 quartile assignment and Q1–Q4 filter (9 without quartile excluded): 230.
4. **Double title-and-abstract screening**, independent and blinded, by two human reviewers on all 230 records. Disagreements: consensus; if persistent, a third reviewer.
5. Full-text reading of candidates.
6. Secondary check with a local lexical filter and a local language model (Llama 3 8B, T = 0, via Ollama); it does **not** replace human judgement.

Reliability: inter-rater Cohen's κ as the primary metric, with observed agreement, PABAK and 95% Wilson intervals.

## 6. Data extraction and risk of bias

Extraction matrix with metadata, modelling and control technique, manipulated and controlled variables, disturbances, data origin, validation level (simulation, test bench, pilot plant, industrial plant), reported metrics and NASA TRL. Risk of bias with an ad hoc five-domain tool. Narrative synthesis.

## 7. Bibliometric analysis

Keyword co-occurrence network of the Q1–Q4 corpus (bibliometrix, VOSviewer; Louvain community detection) and independent lexical verification of the core concepts on the 353 unique records.

## 8. Sensitivity analyses

(i) Characterisation of in-domain records excluded by formal criteria (journals without a quartile, proceedings and chapters); (ii) audit of the local lexical filter; (iii) effect of information leakage in the language-model prompt.

## 9. Deviations from the initial design

| Date | Change | Reason | Knowledge of results |
|---|---|---|---|
| 13 Aug 2026 | SJR quartile threshold widened from Q1–Q2 to Q1–Q4 | The search had not been restricted by quartile; in a niche domain a high threshold can discard in-domain evidence | **Yes**: a preliminary screening of Q1–Q2 had identified a single study |
| (before final screening) | Time window extended to 2026 | To include early-access publications | No |

Potential source of bias, declared and bounded by the sensitivity analysis (section 8).

## 10. Data, code and materials

All documentation (search strings, both reviewers' screening decisions, confusion matrix, scripts, prompt and model SHA-256 digest) is at https://github.com/acastillo1975/rsl-ph-azucarera.
