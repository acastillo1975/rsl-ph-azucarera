"""
07_bibliometria_python.py
=====================================
RSL: Aplicaciones de ML para el Control de pH en la Industria Azucarera
Pipeline bibliometrico 100% Python — sin VOSviewer ni bibliometrix (R)

Funciones:
  1. Lee el RIS del corpus Q1-Q4 multi-base (3.filtrado_quartiles.ris).
  2. Normaliza y consolida palabras clave (sinonimos, variantes ortograficas).
  3. Filtra ruido bibliografico (keywords de indexacion no relevantes).
  4. Construye la matriz de co-ocurrencia (umbral configurable).
  5. Detecta clusteres tematicos con Louvain (fallback: greedy modularity).
  6. Genera figura de red de co-ocurrencia (300 dpi).
  7. Exporta tablas de clusters, frecuencias y distribucion temporal.
  8. Imprime reporte bibliometrico.

Uso:
  python 07_bibliometria_python.py
  python 07_bibliometria_python.py --input ..\03_filtered_data\3.filtrado_quartiles.ris --output ..\05_bibliometria
  python 07_bibliometria_python.py --min-cooc 3 --max-nodes 80 --dpi 600 --log-level DEBUG
"""

import os
import re
import sys
import argparse
import logging
import collections
import itertools
from datetime import datetime

import pandas as pd
import networkx as nx
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

try:
    import community as community_louvain
    LOUVAIN_AVAILABLE = True
except ImportError:
    LOUVAIN_AVAILABLE = False

matplotlib.rcParams.update({
    "font.family"        : "DejaVu Sans",
    "font.size"          : 9,
    "axes.spines.top"    : False,
    "axes.spines.right"  : False,
    "axes.spines.left"   : False,
    "axes.spines.bottom" : False,
})

logger = logging.getLogger("bibliometria")


# ── LOGGING ───────────────────────────────────────────────────────────────────
def configurar_logging(output_folder: str, log_level: str) -> str:
    os.makedirs(output_folder, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(output_folder, f"bibliometria_{timestamp}.log")

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


# ── COLORES Y NOMBRES DE CLUSTERS ─────────────────────────────────────────────
COLORES_CLUSTER = {
    0: "#D85A30",   # rojo-coral
    1: "#1D9E75",   # verde
    2: "#378ADD",   # azul
    3: "#EF9F27",   # ambar
}
NOMBRES_CLUSTER = {
    0: "Prediccion ML para pH clarificacion (Cluster 1)",
    1: "Control avanzado pH MPC/RL/fuzzy (Cluster 2)",
    2: "Sensores virtuales pH azucarero (Cluster 3)",
    3: "Otros terminos relevantes",
}


# ── NORMALIZACION DE KEYWORDS ─────────────────────────────────────────────────
SINONIMOS: dict[str, str] = {
    # pH y variantes
    "ph control": "pH control", "ph monitoring": "pH control",
    "ph prediction": "pH prediction", "ph estimation": "pH prediction",
    "ph measurement": "pH control", "ph adjustment": "pH control",
    "ph correction": "pH control", "ph regulation": "pH control",
    "ph optimization": "pH control",
    "acidity control": "acidity/alkalinity control",
    "alkalinity control": "acidity/alkalinity control",
    "juice acidity": "acidity/alkalinity control",
    "acid-base control": "acidity/alkalinity control",
    # Encalado / proceso
    "lime dosage": "lime dosage", "lime addition": "lime dosage",
    "lime feeding": "lime dosage", "milk of lime": "lime dosage",
    "calcium hydroxide": "lime dosage", "liming control": "lime dosage",
    "lime requirement": "lime dosage",
    "defecation control": "defecation/liming",
    "liming process": "defecation/liming",
    "defecation": "defecation/liming",
    "sulfitation": "sulfitation/carbonatation",
    "carbonatation": "sulfitation/carbonatation",
    "so2 dosage": "sulfitation/carbonatation",
    # Clarificacion
    "juice clarification": "juice clarification",
    "cane juice clarification": "juice clarification",
    "sugar clarification": "juice clarification",
    "juice purification": "juice clarification",
    "clarification efficiency": "juice clarification",
    "mud separation": "juice clarification",
    "clarifier": "juice clarification",
    # Industria azucarera
    "sugar mill": "sugar industry", "sugar factory": "sugar industry",
    "sugar industry": "sugar industry",
    "sugarcane processing": "sugar industry",
    "sugar cane": "sugarcane", "saccharum officinarum": "sugarcane",
    "sugar beet": "sugar beet", "beet sugar": "sugar beet",
    "beet factory": "sugar beet",
    # Variables de jugo
    "sugarcane juice": "juice quality", "cane juice": "juice quality",
    "raw juice": "juice quality", "mixed juice": "juice quality",
    "clarified juice": "juice quality", "juice purity": "juice quality",
    "turbidity": "juice quality", "color removal": "juice quality",
    "sucrose degradation": "juice quality", "inversion losses": "juice quality",
    # Machine learning
    "machine-learning": "machine learning", "ml": "machine learning",
    "supervised learning": "machine learning",
    # Redes neuronales
    "neural networks": "neural network",
    "artificial neural networks": "neural network",
    "ann": "neural network", "multilayer perceptron": "neural network",
    "mlp": "neural network",
    # Deep learning
    "deep neural network": "deep learning",
    # LSTM
    "long short-term memory": "LSTM", "lstm networks": "LSTM",
    "recurrent neural network": "LSTM/RNN", "rnn": "LSTM/RNN",
    # CNN
    "convolutional neural network": "CNN",
    "convolutional neural networks": "CNN",
    # Random forest / ensemble
    "random forests": "random forest", "xgboost": "gradient boosting",
    "lightgbm": "gradient boosting",
    "gradient boosting machines": "gradient boosting",
    # Support vector
    "support vector machine": "support vector",
    "support vector regression": "support vector",
    "svm": "support vector", "svr": "support vector",
    # Fuzzy
    "fuzzy logic": "fuzzy logic", "neuro-fuzzy": "fuzzy logic",
    "fuzzy control": "fuzzy logic",
    # Control avanzado
    "model predictive control": "model predictive control",
    "mpc": "model predictive control",
    "reinforcement learning": "reinforcement learning",
    "deep reinforcement learning": "reinforcement learning",
    "ddpg": "reinforcement learning",
    "adaptive control": "adaptive control",
    "intelligent control": "adaptive control",
    "pid tuning": "PID/adaptive control",
    "optimal control": "PID/adaptive control",
    # Sensores virtuales
    "soft sensors": "soft sensor", "virtual sensor": "soft sensor",
    "virtual sensors": "soft sensor", "inferential sensor": "soft sensor",
    "online estimation": "soft sensor",
    "real-time estimation": "soft sensor",
    "data-driven model": "data-driven", "data driven": "data-driven",
    # Gemelo digital / PINN
    "digital twin": "digital twin",
    "physics-informed neural network": "PINN",
    "physics informed neural networks": "PINN",
    # Optimizacion
    "process optimization": "process optimization",
    "process optimisation": "process optimization",
    "real-time optimization": "process optimization",
    "genetic algorithms": "genetic algorithm",
    "particle swarm optimization": "particle swarm",
    "pso": "particle swarm",
    # Prediccion / regresion
    "prediction model": "prediction", "predictive model": "prediction",
    "regression analysis": "regression",
    "gaussian process": "Gaussian process",
    # Transfer learning
    "transfer learning": "transfer learning",
    "fine tuning": "transfer learning",
    # Sensores
    "ph sensor": "pH sensor", "ph probe": "pH sensor",
    "online ph": "pH sensor", "real-time ph": "pH sensor",
    # Energia / eficiencia
    "energy consumption": "energy efficiency",
    "power consumption": "energy efficiency",
    "process efficiency": "energy efficiency",
}

STOPWORDS_BIBLIOMETRICAS: set[str] = {
    "blood ph", "urine ph", "gastric ph", "physiological ph",
    "blood acid-base", "arterial ph", "plasma ph",
    "enzyme activity", "enzyme inactivation", "polyphenols",
    "phenolic compounds", "flavonoids", "ascorbic acid", "vitamin c",
    "microbiology", "microbial", "yeast", "bacteria",
    "chemistry", "biochemistry", "chemical composition",
    "temperature", "glucose", "fructose",
    "ph", "acidity",
    "article", "nonhuman", "controlled study", "human",
    "male", "female", "adult",
    "china", "brazil", "india", "cuba", "australia",
    "remote sensing", "satellite imagery", "ndvi",
    "soil", "irrigation", "crop yield", "climate change",
    "plant disease", "photosynthesis",
    "wine", "beer", "dairy", "milk", "yogurt",
    "fruit juice", "orange juice", "olive oil",
    "wastewater", "effluent", "drinking water", "groundwater",
    "bioethanol", "fermentation broth", "anaerobic digestion",
    "pharmaceutical", "drug", "tablet",
    "mean square error", "errors", "data reduction",
    "data acquisition", "learning systems", "information theory",
    "massecuite", "crystallization", "centrifuge", "vacuum pan",
}


def normalizar_kw(kw: str) -> str | None:
    kw = kw.lower().strip()
    kw = re.sub(r"[;,]+$", "", kw).strip()
    if len(kw) <= 2:
        return None
    kw = SINONIMOS.get(kw, kw)
    if kw in STOPWORDS_BIBLIOMETRICAS:
        return None
    if re.fullmatch(r"[\d\s]+", kw):
        return None
    return kw


# ── LECTURA DEL RIS ───────────────────────────────────────────────────────────
def leer_ris(filepath: str) -> list[dict]:
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"No se encontro: {filepath}")
    if os.path.isdir(filepath):
        raise IsADirectoryError(f"--input debe ser un archivo .ris, no carpeta: {filepath}")

    entradas, actual = [], {}
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        for linea in f:
            linea = linea.rstrip("\n").rstrip("\r")
            if linea.strip() == "ER  -":
                if actual:
                    entradas.append(actual)
                actual = {}
            elif "  -" in linea:
                partes = linea.split("  - ", 1)
                if len(partes) == 2:
                    tag, val = partes[0].strip(), partes[1].strip()
                    if tag in ("KW", "AU", "AD", "N1"):
                        if tag in actual:
                            if isinstance(actual[tag], list):
                                actual[tag].append(val)
                            else:
                                actual[tag] = [actual[tag], val]
                        else:
                            actual[tag] = [val]
                    else:
                        actual[tag] = val
    if actual:
        entradas.append(actual)
    logger.info(f"Entradas leidas del RIS: {len(entradas)}")
    return entradas


def extraer_keywords_por_entrada(entradas: list[dict]) -> list[list[str]]:
    resultado = []
    total_raw, total_norm = 0, 0
    for e in entradas:
        kws_raw = e.get("KW", [])
        if isinstance(kws_raw, str):
            kws_raw = [kws_raw]
        kws_norm = []
        for kw in kws_raw:
            total_raw += 1
            norm = normalizar_kw(kw)
            if norm:
                kws_norm.append(norm)
                total_norm += 1
        kws_norm = list(dict.fromkeys(kws_norm))
        resultado.append(kws_norm)
    logger.info(f"KW brutas totales         : {total_raw}")
    logger.info(f"KW normalizadas (sin ruido): {total_norm}")
    return resultado


def extraer_metadata(entradas: list[dict]) -> pd.DataFrame:
    filas = []
    for e in entradas:
        n1 = e.get("N1", [])
        if isinstance(n1, str):
            n1 = [n1]
        n1_str = " | ".join(n1)
        cuartil = ""
        m = re.search(r"SJR Best Quartile:\s*(Q\d)", n1_str)
        if m:
            cuartil = m.group(1)
        sjr = ""
        m2 = re.search(r"SJR:\s*([\d,\.]+)", n1_str)
        if m2:
            sjr = m2.group(1)
        autores = e.get("AU", [])
        if isinstance(autores, list):
            primer_au = autores[0].split(",")[0].strip() if autores else ""
        else:
            primer_au = str(autores).split(",")[0].strip()
        filas.append({
            "TI"     : e.get("TI", ""),
            "AU_ppal": primer_au,
            "PY"     : e.get("PY", ""),
            "T2"     : e.get("T2", ""),
            "DO"     : e.get("DO", ""),
            "DB"     : e.get("DB", ""),
            "Cuartil": cuartil,
            "SJR"    : sjr,
            "VL"     : e.get("VL", ""),
        })
    return pd.DataFrame(filas)


# ── RED DE CO-OCURRENCIA ──────────────────────────────────────────────────────
def construir_red(todos_kw: list[list[str]], min_cooc: int, max_nodos: int):
    freq = collections.Counter()
    for kws in todos_kw:
        freq.update(kws)

    kw_validas = {k for k, v in freq.items() if v >= min_cooc}
    logger.info(f"Keywords unicas (post-normalizacion): {len(freq)}")
    logger.info(f"Con >= {min_cooc} ocurrencias: {len(kw_validas)}")

    if len(kw_validas) > max_nodos:
        top = {k for k, _ in freq.most_common(max_nodos)}
        kw_validas = kw_validas & top
        logger.info(f"Limitado a top-{max_nodos}: {len(kw_validas)} nodos")

    cooc = collections.Counter()
    for kws in todos_kw:
        kws_f = list(dict.fromkeys([k for k in kws if k in kw_validas]))
        for par in itertools.combinations(sorted(kws_f), 2):
            cooc[par] += 1

    G = nx.Graph()
    for kw in kw_validas:
        G.add_node(kw, freq=freq[kw])
    for (u, v), peso in cooc.items():
        G.add_edge(u, v, weight=peso)

    isolated = list(nx.isolates(G))
    G.remove_nodes_from(isolated)
    if isolated:
        logger.info(f"Nodos aislados removidos: {len(isolated)}")

    logger.info(f"Nodos finales : {G.number_of_nodes()}")
    logger.info(f"Aristas finales: {G.number_of_edges()}")
    return G, freq


# ── DETECCION DE CLUSTERES ────────────────────────────────────────────────────
def detectar_clusteres(G: nx.Graph) -> dict:
    if G.number_of_nodes() == 0:
        return {}
    if LOUVAIN_AVAILABLE:
        partition = community_louvain.best_partition(G, random_state=42)
        n_comm = len(set(partition.values()))
        logger.info(f"Comunidades (Louvain): {n_comm}")
    else:
        comms = list(nx.algorithms.community.greedy_modularity_communities(G))
        partition = {n: i for i, c in enumerate(comms) for n in c}
        logger.info(f"Comunidades (greedy): {len(comms)}")
    return partition


# ── VISUALIZACION ─────────────────────────────────────────────────────────────
def visualizar_red(G: nx.Graph, freq: dict, partition: dict,
                   output_path: str, min_cooc: int, fig_size: tuple, dpi: int) -> None:
    if G.number_of_nodes() == 0:
        logger.warning("Grafo vacio — sin figura generada.")
        return

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    pos = nx.spring_layout(G, k=2.8, iterations=100, seed=42)

    fig, ax = plt.subplots(figsize=fig_size, facecolor="white")
    ax.set_facecolor("white")

    max_freq = max(freq.get(n, 1) for n in G.nodes()) or 1
    node_sizes = [
        max(50, min(900, 50 + 850 * (freq.get(n, 1) / max_freq)))
        for n in G.nodes()
    ]

    n_clusters = max(partition.values()) + 1 if partition else 1
    cols = [COLORES_CLUSTER.get(i, "#888780") for i in range(n_clusters)]
    node_colors = [cols[partition.get(n, 0) % len(cols)] for n in G.nodes()]

    pesos = [G[u][v].get("weight", 1) for u, v in G.edges()]
    max_p = max(pesos) if pesos else 1
    widths = [max(0.3, 2.8 * w / max_p) for w in pesos]
    alphas = [max(0.12, 0.65 * w / max_p) for w in pesos]

    for (u, v), width, alpha in zip(G.edges(), widths, alphas):
        ax.plot([pos[u][0], pos[v][0]], [pos[u][1], pos[v][1]],
                color="#B4B2A9", linewidth=width, alpha=alpha, zorder=1)

    nx.draw_networkx_nodes(G, pos, ax=ax, node_size=node_sizes,
                           node_color=node_colors, alpha=0.88,
                           linewidths=0.6, edgecolors="white")

    n_labels = min(50, G.number_of_nodes())
    freq_sorted = sorted(
        [(n, freq.get(n, 0)) for n in G.nodes()],
        key=lambda x: x[1], reverse=True
    )
    min_f_label = freq_sorted[min(n_labels - 1, len(freq_sorted) - 1)][1]
    labels = {n: n for n in G.nodes() if freq.get(n, 0) >= min_f_label}
    nx.draw_networkx_labels(G, pos, labels, ax=ax,
                            font_size=7.5, font_color="#2A2A28")

    parches = []
    for cid in sorted(set(partition.values())):
        color  = COLORES_CLUSTER.get(cid, "#888780")
        nombre = NOMBRES_CLUSTER.get(cid, f"Cluster {cid}")
        parches.append(mpatches.Patch(color=color, label=nombre))
    ax.legend(handles=parches, loc="lower left", fontsize=8.5,
              frameon=True, framealpha=0.92, edgecolor="#D3D1C7")

    algo = "Louvain" if LOUVAIN_AVAILABLE else "Greedy modularity"
    ax.text(
        0.99, 0.01,
        f"n={G.number_of_nodes()} terminos | umbral >= {min_cooc} "
        f"co-ocurrencias\nAlgoritmo: {algo} | "
        f"Corpus: Scopus + WoS + IEEE Xplore (2015-2026)",
        transform=ax.transAxes, fontsize=7, ha="right", va="bottom",
        color="#888780",
    )

    ax.set_title(
        "Mapa de co-ocurrencia de palabras clave\n"
        "RSL: Control de pH en la Industria Azucarera con IA",
        fontsize=10, fontweight="bold", color="#2A2A28", pad=12,
    )

    ax.axis("off")
    plt.tight_layout()
    plt.savefig(output_path, dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close()
    logger.info(f"Figura exportada ({dpi} dpi): {output_path}")


# ── EXPORTACION DE TABLAS ─────────────────────────────────────────────────────
def exportar_tablas(G: nx.Graph, freq: dict, partition: dict,
                    df_meta: pd.DataFrame,
                    out_xlsx: str, out_csv: str) -> None:
    os.makedirs(os.path.dirname(out_xlsx) or ".", exist_ok=True)

    filas_c = []
    for nodo in G.nodes():
        cid = partition.get(nodo, -1)
        filas_c.append({
            "Termino"        : nodo,
            "Frecuencia"     : freq.get(nodo, 0),
            "Cluster_ID"     : cid,
            "Cluster_Nombre" : NOMBRES_CLUSTER.get(cid, f"Cluster {cid}"),
            "Grado"          : G.degree(nodo),
            "Grado_ponderado": round(sum(
                G[nodo][v].get("weight", 1) for v in G.neighbors(nodo)), 2),
        })
    df_c = pd.DataFrame(filas_c).sort_values(
        ["Cluster_ID", "Frecuencia"], ascending=[True, False]
    )

    filas_e = []
    for u, v, data in G.edges(data=True):
        filas_e.append({
            "Termino_1"     : u,
            "Termino_2"     : v,
            "Coocurrencias" : data.get("weight", 1),
            "Cluster_T1"    : partition.get(u, -1),
            "Cluster_T2"    : partition.get(v, -1),
            "Mismo_cluster" : partition.get(u, -1) == partition.get(v, -1),
        })
    df_e = pd.DataFrame(filas_e).sort_values("Coocurrencias", ascending=False)

    resumen = df_c.groupby("Cluster_Nombre").agg(
        N_terminos  =("Termino",    "count"),
        Freq_total  =("Frecuencia", "sum"),
        Top_terminos=("Termino",    lambda x: ", ".join(x.head(6))),
    ).reset_index()

    df_py = df_meta.groupby("PY").agg(
        N_articulos=("TI", "count")
    ).reset_index().rename(columns={"PY": "Anio"})

    df_db = df_meta.groupby("DB").agg(
        N_articulos=("TI", "count")
    ).reset_index().rename(columns={"DB": "Base_de_datos"})

    df_q = df_meta.groupby("Cuartil").agg(
        N_articulos=("TI", "count")
    ).reset_index()

    df_au = df_meta.groupby("AU_ppal").agg(
        N_articulos=("TI", "count"),
        Anios=("PY", lambda x: ", ".join(sorted(set(x)))),
    ).reset_index().sort_values("N_articulos", ascending=False)

    df_rev = df_meta.groupby("T2").agg(
        N_articulos=("TI", "count"),
        Cuartil_predominante=("Cuartil", lambda x: x.mode()[0] if len(x) > 0 else ""),
    ).reset_index().sort_values("N_articulos", ascending=False)

    with pd.ExcelWriter(out_xlsx, engine="openpyxl") as writer:
        df_c.to_excel(writer, sheet_name="Clusters_Terminos", index=False)
        df_e.to_excel(writer, sheet_name="Coocurrencias", index=False)
        resumen.to_excel(writer, sheet_name="Resumen_Clusters", index=False)
        df_py.to_excel(writer, sheet_name="Distribucion_Temporal", index=False)
        df_db.to_excel(writer, sheet_name="Por_Base_Datos", index=False)
        df_q.to_excel(writer, sheet_name="Por_Cuartil", index=False)
        df_au.to_excel(writer, sheet_name="Top_Autores", index=False)
        df_rev.to_excel(writer, sheet_name="Top_Revistas", index=False)

    df_e.to_csv(out_csv, index=False, encoding="utf-8")

    logger.info(f"Clusters exportados: {out_xlsx}")
    logger.info("  Hojas: Clusters_Terminos | Coocurrencias | Resumen_Clusters")
    logger.info("         Distribucion_Temporal | Por_Base_Datos | Por_Cuartil")
    logger.info("         Top_Autores | Top_Revistas")
    logger.info(f"Aristas CSV: {out_csv}")


# ── REPORTE ───────────────────────────────────────────────────────────────────
def imprimir_reporte(G: nx.Graph, freq: dict, partition: dict,
                     df_meta: pd.DataFrame) -> None:
    logger.info("=" * 65)
    logger.info("REPORTE BIBLIOMETRICO — RSL CONTROL DE pH EN AZUCAR CON IA")
    logger.info("=" * 65)

    n = len(df_meta)
    logger.info(f"Total articulos Q1-Q4 (corpus bibliometrico): {n}")

    py_dist = df_meta["PY"].value_counts().sort_index()
    logger.info("Distribucion temporal:")
    for anio, cnt in py_dist.items():
        barra = "=" * cnt
        logger.info(f"  {anio}: {barra} ({cnt})")

    db_dist = df_meta["DB"].value_counts()
    logger.info("Por base de datos:")
    for db, cnt in db_dist.items():
        logger.info(f"  {db}: {cnt}")

    q_dist = df_meta["Cuartil"].value_counts()
    logger.info("Por cuartil SJR:")
    for q, cnt in q_dist.items():
        logger.info(f"  {q}: {cnt}")

    logger.info("Top 5 revistas:")
    rev_top = df_meta["T2"].value_counts().head(5)
    for rev, cnt in rev_top.items():
        logger.info(f"  {cnt}  {rev}")

    logger.info("Top 5 autores por productividad:")
    au_top = df_meta["AU_ppal"].value_counts().head(5)
    for au, cnt in au_top.items():
        logger.info(f"  {cnt}  {au}")

    logger.info("Red de co-ocurrencia:")
    logger.info(f"  Nodos  : {G.number_of_nodes()}")
    logger.info(f"  Aristas: {G.number_of_edges()}")
    if G.number_of_nodes() > 0:
        logger.info(f"  Densidad: {nx.density(G):.4f}")

    logger.info("Top keywords por cluster:")
    for cid in sorted(set(partition.values())):
        nombre = NOMBRES_CLUSTER.get(cid, f"Cluster {cid}")
        nodos_c = [n for n, c in partition.items() if c == cid]
        top_c = sorted(nodos_c, key=lambda n: freq.get(n, 0), reverse=True)[:6]
        logger.info(f"  [{nombre}]")
        logger.info(f"  -> {', '.join(top_c)}")

    logger.info("=" * 65)


# ── CLI ───────────────────────────────────────────────────────────────────────
def parsear_args():
    p = argparse.ArgumentParser(
        description="Bibliometria de co-ocurrencia de keywords (RSL pH industria azucarera).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--input", "-i", default="output/3.filtrado_quartiles.ris",
                   help="RIS de entrada (salida del script 03).")
    p.add_argument("--output", "-o", default="output",
                   help="Carpeta de salida (figura, Excel, CSV y log).")
    p.add_argument("--min-cooc", type=int, default=2,
                   help="Umbral minimo de co-ocurrencias para incluir un termino.")
    p.add_argument("--max-nodes", type=int, default=120,
                   help="Maximo de nodos en la red (limita a top-N por frecuencia).")
    p.add_argument("--dpi", type=int, default=300,
                   help="Resolucion de la figura PNG.")
    p.add_argument("--fig-width",  type=float, default=14.0,
                   help="Ancho de la figura (pulgadas).")
    p.add_argument("--fig-height", type=float, default=10.0,
                   help="Alto de la figura (pulgadas).")
    p.add_argument("--log-level", "-l", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                   help="Nivel de verbosidad.")
    return p.parse_args()


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    args = parsear_args()
    log_path = configurar_logging(args.output, args.log_level)

    output_fig      = os.path.join(args.output, "7.coocurrencia_keywords.png")
    output_clusters = os.path.join(args.output, "7.clusters_tematicos.xlsx")
    output_edges    = os.path.join(args.output, "7.coocurrencia_edges.csv")

    logger.info("=" * 65)
    logger.info("BIBLIOMETRIA — CO-OCURRENCIA DE KEYWORDS")
    logger.info("RSL Control de pH en la Industria Azucarera con IA (multi-base)")
    logger.info("=" * 65)
    logger.info(f"Input RIS    : {args.input}")
    logger.info(f"Output folder: {args.output}")
    logger.info(f"Min cooc.    : {args.min_cooc}  |  Max nodes: {args.max_nodes}")
    logger.info(f"Figura       : {args.fig_width}x{args.fig_height} pulgadas @ {args.dpi} dpi")
    logger.info(f"Log file     : {log_path}")
    if not LOUVAIN_AVAILABLE:
        logger.warning("python-louvain no instalado. Usando greedy modularity "
                       "(pip install python-louvain).")

    os.makedirs(args.output, exist_ok=True)

    # 1. Leer RIS
    logger.info("[1] Leyendo RIS...")
    try:
        entradas = leer_ris(args.input)
    except (FileNotFoundError, IsADirectoryError) as e:
        logger.error(str(e))
        sys.exit(1)
    if not entradas:
        logger.error("RIS sin entradas. Abortando.")
        sys.exit(1)

    # 2. Keywords y metadata
    logger.info("[2] Normalizando keywords...")
    todos_kw = extraer_keywords_por_entrada(entradas)
    df_meta  = extraer_metadata(entradas)

    # 3. Red
    logger.info(f"[3] Construyendo red (umbral >= {args.min_cooc} co-ocurrencias)...")
    G, freq = construir_red(todos_kw, args.min_cooc, args.max_nodes)

    # 4. Clusters
    logger.info("[4] Detectando clusteres tematicos...")
    partition = detectar_clusteres(G)

    # 5. Figura
    logger.info("[5] Generando figura...")
    visualizar_red(G, freq, partition, output_fig,
                   args.min_cooc, (args.fig_width, args.fig_height), args.dpi)

    # 6. Tablas
    logger.info("[6] Exportando tablas bibliometricas...")
    exportar_tablas(G, freq, partition, df_meta, output_clusters, output_edges)

    # 7. Reporte
    imprimir_reporte(G, freq, partition, df_meta)

    logger.info(f"FIGURA: {output_fig}")
    logger.info("-> Copiar a 08_latex_output/figures/ para incluir en el paper")
    logger.info("SIGUIENTE PASO: python 08_reporte_prisma.py")
    logger.info("=" * 65)


if __name__ == "__main__":
    main()