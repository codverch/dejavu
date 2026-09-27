"""Minimal, direct-labelled figure style for the start-up wave figures.

Modelled on the figures in Athalye et al. (Knox, OSDI'22): no chart junk, no legend boxes or
titles, lines labelled where they end, context drawn as quiet bands named in place, serif type
matching the paper body, one idea per graph.
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

FONTS = Path("/h/deepanjm/agentic-stuff/figscripts/fonts")
for f in FONTS.glob("*.ttf"):
    try:
        fm.fontManager.addfont(str(f))
    except Exception:  # noqa: BLE001
        pass

INK, MUTED, RULE = "#222222", "#6b6b6b", "#d9d9d9"
COLD, WARM = "#1f4e79", "#c55a11"          # cold pass, self-warm pass
# activity categories: muted qualitative, fixed by name across every figure
CAT_COLOUR = {
    "ld.so: relocation": "#b2182b", "ld.so: symbol lookup": "#ef8a62", "ld.so: load & map": "#fddbc7",
    "libc: string/memory ops": "#bababa", "codec / locale": "#e6ab02",
    "allocation": "#a6761d", "Python: GC": "#7570b3", "Python: type setup": "#1b9e77",
    "Python: unmarshal .pyc": "#66a61e", "Python: dict / hash / str": "#2166ac",
    "Python: bytecode eval": "#67a9cf", "Python: other interpreter": "#d1e5f0",
    "shell (bash/dash)": "#4d9221", "native tool's own code": "#c51b7d", "libc: regex": "#de77ae",
    "libc: stdio": "#f1b6da", "libc: other": "#e0e0e0", "other": "#f0f0f0", "private/unmapped code": "#ffffff",
}


def use():
    plt.rcParams.update({
        "font.family": "serif", "font.serif": ["Liberation Serif", "Times New Roman", "DejaVu Serif"],
        "font.size": 8, "axes.labelsize": 8.5, "xtick.labelsize": 7.5, "ytick.labelsize": 7.5,
        "text.color": INK, "axes.labelcolor": INK, "xtick.color": INK, "ytick.color": INK,
        "axes.edgecolor": INK, "axes.linewidth": 0.6, "axes.spines.top": False, "axes.spines.right": False,
        "xtick.major.width": 0.6, "ytick.major.width": 0.6, "xtick.major.size": 2.5, "ytick.major.size": 2.5,
        "xtick.direction": "out", "ytick.direction": "out", "axes.grid": False,
        "lines.linewidth": 1.0, "figure.dpi": 400, "savefig.dpi": 400, "savefig.bbox": "tight",
        "savefig.pad_inches": 0.03, "pdf.fonttype": 42,
    })


def save(fig, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path.with_suffix(".png"))
    plt.close(fig)
