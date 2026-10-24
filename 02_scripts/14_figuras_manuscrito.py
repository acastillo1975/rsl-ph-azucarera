"""
14_figuras_manuscrito.py
========================
Figuras originales del manuscrito (vectoriales, PDF), regenerables:

  figures/produccion_anual.pdf  Producción anual del corpus adyacente Q1-Q4 (n=230).
  figures/mapa_evidencia.pdf    Mapa de evidencia in-domain: 2 estudios incluidos +
                                11 trabajos complementarios, por familia de método
                                y nivel de validación declarado.

Los conteos anuales provienen de 03_filtered_data/3.filtrado_quartiles.xlsx;
el mapa de evidencia se codifica a mano a partir de la lectura del texto completo
(estudios incluidos) y del resumen (trabajos complementarios): ver Apéndice F.

Uso: python 14_figuras_manuscrito.py
"""

import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.join(AQUI, "..")
FIG = os.path.join(RAIZ, "07_latex_output", "figures")

INK, MUTED, GRID = "#1f2933", "#6b7280", "#e5e7eb"
BLUE, GREY = "#2b6cb0", "#9aa5b1"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": MUTED,
    "axes.labelcolor": INK, "xtick.color": INK, "ytick.color": INK,
    "pdf.fonttype": 42,
})


def produccion_anual():
    df = pd.read_excel(os.path.join(RAIZ, "03_filtered_data", "3.filtrado_quartiles.xlsx"))
    cnt = df["PY"].astype(int).value_counts().sort_index()
    assert int(cnt.sum()) == 230, cnt.sum()
    fig, ax = plt.subplots(figsize=(6.4, 2.9))
    colores = [GREY if y == 2026 else BLUE for y in cnt.index]
    barras = ax.bar(cnt.index.astype(str), cnt.values, color=colores, width=0.72)
    for b, v in zip(barras, cnt.values):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.6, str(v), ha="center", va="bottom",
                fontsize=8, color=INK)
    ax.set_ylabel("Registros por año (n)")
    ax.set_xlabel("Año editorial (2026: publicaciones «early access»)")
    ax.set_ylim(0, cnt.max() * 1.18)
    ax.yaxis.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "produccion_anual.pdf"))
    plt.close(fig)


# Familias: D=neuro-difuso, M=MPC/NMPC, H=metaheuristicas, I=modelado/identificacion data-driven
# Validacion: S=simulacion, P=simulacion + datos de planta (identificacion), E=prototipo/experimental, N=no especificado
FILAS = [
    # etiqueta, grupo, familias, validacion
    ("Palacio-Morales et al. (2021)", "Incluido", "DMHI", "S"),
    ("Murugesan et al. (2020)", "Incluido", "HI", "P"),
    ("Sunori et al. (2016)", "Revista sin cuartil", "H", "S"),
    ("Wang (2017)", "Revista sin cuartil", "D", "E"),
    ("Rajalakshmi et al. (2022)", "Revista sin cuartil", "HI", "N"),
    ("Sunori et al. (2017)", "Acta / capítulo", "H", "S"),
    ("Rajalakshmi et al. (2018)", "Acta / capítulo", "HI", "N"),
    ("Sunori et al. (2020)", "Acta / capítulo", "DI", "S"),
    ("Jethi et al. (2021)", "Acta / capítulo", "M", "S"),
    ("Kalavathi Devi et al. (2021)", "Acta / capítulo", "", "E"),
    ("Sunori et al. (2022a)", "Acta / capítulo", "M", "S"),
    ("Sunori et al. (2022b)", "Acta / capítulo", "D", "S"),
    ("Sunori et al. (2022c)", "Acta / capítulo", "H", "S"),
]
COLS = [("D", "Neuro-\ndifuso"), ("M", "MPC /\nNMPC"), ("H", "Metaheu-\nrísticas"),
        ("I", "Modelado /\nidentificac.")]
VAL = {"S": ("Simulación", "o"), "P": ("Simulación + datos\nde planta (ident.)", "s"),
       "E": ("Prototipo /\nexperimental", "D"), "N": ("No especificado\nen el resumen", "x")}


def mapa_evidencia():
    n = len(FILAS)
    fig, ax = plt.subplots(figsize=(7.6, 5.4))
    xs = list(range(len(COLS) + 1))
    for i, (etiq, grupo, fam, val) in enumerate(FILAS):
        y = n - 1 - i
        if i % 2 == 0:
            ax.axhspan(y - 0.5, y + 0.5, color="#f3f4f6", zorder=0)
        for j, (clave, _) in enumerate(COLS):
            if clave in fam:
                ax.plot(j, y, "o", color=BLUE, markersize=8, zorder=3)
        nombre, marca = VAL[val]
        if marca == "x":
            ax.plot(len(COLS), y, "x", color=MUTED, markersize=8, markeredgewidth=1.6, zorder=3)
        else:
            ax.plot(len(COLS), y, marca, color=INK, markerfacecolor="white" if val == "S" else INK,
                    markersize=8, markeredgewidth=1.4, zorder=3)
    # separadores de grupo
    for corte in (2, 5):
        ax.axhline(n - corte - 0.5, color=MUTED, linewidth=0.8, linestyle=(0, (3, 3)))
    ax.set_yticks(range(n))
    ax.set_yticklabels([f[0] for f in FILAS][::-1], fontsize=8.5)
    ax.set_xticks(xs)
    ax.set_xticklabels([c[1] for c in COLS] + ["Validación\ndeclarada"], fontsize=8.5)
    ax.xaxis.tick_top()
    ax.set_xlim(-0.6, len(COLS) + 0.6)
    ax.set_ylim(-0.6, n - 0.4)
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    # etiquetas de grupo a la derecha
    ax.text(len(COLS) + 0.75, n - 1.5, "Incluidos\n(criterios completos)", va="center", fontsize=8, color=MUTED)
    ax.text(len(COLS) + 0.75, n - 4.0, "Revistas sin\ncuartil SJR", va="center", fontsize=8, color=MUTED)
    ax.text(len(COLS) + 0.75, n - 9.5, "Actas y capítulos\n(tipo excluido)", va="center", fontsize=8, color=MUTED)
    # leyenda de validación
    from matplotlib.lines import Line2D
    handles = [
        Line2D([], [], marker="o", color=INK, markerfacecolor="white", linestyle="", markersize=8, label=VAL["S"][0].replace("\n", " ")),
        Line2D([], [], marker="s", color=INK, linestyle="", markersize=8, label=VAL["P"][0].replace("\n", " ")),
        Line2D([], [], marker="D", color=INK, linestyle="", markersize=7, label=VAL["E"][0].replace("\n", " ")),
        Line2D([], [], marker="x", color=MUTED, linestyle="", markersize=8, markeredgewidth=1.6, label=VAL["N"][0].replace("\n", " ")),
    ]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.45, -0.02), ncol=2,
              frameon=False, fontsize=8, title="Marcador de la última columna", title_fontsize=8)
    fig.subplots_adjust(left=0.27, right=0.80, top=0.88, bottom=0.14)
    fig.savefig(os.path.join(FIG, "mapa_evidencia.pdf"))
    plt.close(fig)


if __name__ == "__main__":
    os.makedirs(FIG, exist_ok=True)
    produccion_anual()
    mapa_evidencia()
    print("Figuras generadas en", FIG)
