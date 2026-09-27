"""The look of w8_headroom/fig_headroom_geomean.png, shared by the motivation figures: boxed axes,
dotted horizontal grid, no tick marks, black-outlined bars in the user's palette, a boxed legend
across the top, and a dashed rule before the average group. Text is ~1.5 pt larger than W8's.
"""
from pathlib import Path

import numpy as np

import anish_style as st

st.use()
from anish_style import plt  # noqa: E402

C_YEL, C_ORANGE, C_LIME, C_TEAL, C_PINK, C_NAVY = "#fff700", "#eb6f44", "#7ac141", "#1b7188", "#b02467", "#302f8d"
C_GREY = "#d9d9d9"
FS_TICK, FS_LABEL, FS_LEGEND, FS_VALUE = 10, 11, 9.5, 8
DARK = {C_NAVY, C_PINK, C_TEAL}


def frame(ax, xlabel=None, ylabel=None):
    for side in ("top", "right"):
        ax.spines[side].set_visible(True)
    for sp in ax.spines.values():
        sp.set_color("black"); sp.set_linewidth(0.7)
    ax.grid(axis="y", color="#808080", lw=0.5, ls=(0, (1, 2)), zorder=0); ax.set_axisbelow(True)
    ax.tick_params(axis="both", length=0, labelsize=FS_TICK)
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=FS_LABEL)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=FS_LABEL)


def legend(ax, ncol, handles=None, labels=None):
    kw = dict(frameon=True, fancybox=False, edgecolor="black", framealpha=1, fontsize=FS_LEGEND, loc="lower left",
              mode="expand", bbox_to_anchor=(0, 1.02, 1, 0.2), ncol=ncol, handlelength=1.4, columnspacing=0.8,
              borderpad=0.5)
    lg = ax.legend(handles, labels, **kw) if handles else ax.legend(**kw)
    lg.get_frame().set_linewidth(0.6)


def grouped(ax, groups, series, avg=True, fmt="{:.1f}", label_all=False, ymax=None, log=False):
    """series: [(label, colour, value per group)]; the last group is the average when avg."""
    n = len(series); bw = 0.8 / n; x = np.arange(len(groups), dtype=float)
    top = max(np.nanmax(np.asarray(v, float)) for _, _, v in series)
    for j, (lab, col, v) in enumerate(series):
        v = np.asarray(v, float); xs = x + (j - (n - 1) / 2) * bw
        ax.bar(xs, v, bw, color=col, edgecolor="black", lw=0.5, label=lab, zorder=3)
        for i in (range(len(groups)) if label_all else ([len(groups) - 1] if avg else [])):
            if np.isfinite(v[i]):
                y = v[i] * 1.08 if log else v[i] + (ymax or top) * 0.015
                ax.text(xs[i], y, fmt.format(v[i]), ha="center", va="bottom", fontsize=FS_VALUE, rotation=90, zorder=4)
    if avg:
        ax.axvline(x[-1] - 0.5, color="black", lw=0.6, ls="--", zorder=2)
    ax.set_xlim(x[0] - 0.5, x[-1] + 0.5)
    ax.set_xticks(x); ax.set_xticklabels(groups, fontsize=FS_TICK)
    if log:
        ax.set_yscale("log")
    else:
        ax.set_ylim(0, ymax or top * 1.2)
    return top


def stacked(ax, groups, parts, avg=True, label_min=7):
    """parts: [(label, colour, fraction per group)], each group summing to 1: 100% stacks, labelled."""
    x = np.arange(len(groups), dtype=float); bottom = np.zeros(len(groups))
    for lab, col, v in parts:
        v = 100 * np.asarray(v, float)
        ax.bar(x, v, 0.62, bottom=bottom, color=col, edgecolor="black", lw=0.5, label=lab, zorder=3)
        for xi, b, vi in zip(x, bottom, v):
            if vi >= label_min:
                ax.text(xi, b + vi / 2, f"{vi:.0f}", ha="center", va="center", fontsize=FS_VALUE, zorder=4,
                        color="white" if col in DARK else "black")
        bottom += v
    if avg:
        ax.axvline(x[-1] - 0.5, color="black", lw=0.6, ls="--", zorder=2)
    ax.set_xlim(x[0] - 0.5, x[-1] + 0.5); ax.set_ylim(0, 100)
    ax.set_xticks(x); ax.set_xticklabels(groups, fontsize=FS_TICK)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:g}%"))


def overlaps(fig):
    """pairs of visible, non-empty text labels whose drawn boxes intersect"""
    import matplotlib.text as mt
    fig.canvas.draw(); r = fig.canvas.get_renderer()
    ts = [t for t in fig.findobj(mt.Text) if t.get_visible() and t.get_text().strip()]
    bb = [t.get_window_extent(r).expanded(0.98, 0.9) for t in ts]
    return [(ts[i].get_text(), ts[j].get_text()) for i in range(len(ts)) for j in range(i + 1, len(ts))
            if bb[i].overlaps(bb[j])]


def save(fig, path: Path, caption: str):
    bad = overlaps(fig)
    if bad:
        print(f"OVERLAP in {Path(path).name}: {bad[:6]}")
    st.save(fig, path)
    Path(str(path) + ".png.txt").write_text(" ".join(caption.split()) + "\n")
