"""Compara as medições de várias versões (CSVs gerados por coupling.py).

Gera uma tabela Markdown com Ca, Ce, I, A e D de cada componente por versão e um
gráfico A × I com as versões sobrepostas.

Uso:
    uv run python metrics/compare.py v1-coupled v2-decoupled main
"""

import argparse
import csv
from pathlib import Path

RESULTS = Path(__file__).parent / "results"
MARKERS = ["o", "s", "^", "D"]
COLORS = ["#c62828", "#f9a825", "#2e7d32", "#1565c0"]


def load(name: str, results: Path) -> dict[str, dict]:
    with open(results / f"{name}.csv", encoding="utf-8") as file:
        return {
            row["component"]: {k: (float(v) if k in "iad" else int(v) if k in ("ca", "ce") else v)
                               for k, v in row.items()}
            for row in csv.DictReader(file)
        }


def in_pain_zone(row: dict) -> bool:
    return row["a"] < 0.5 and row["i"] < 0.5 and row["d"] >= 0.5


def table(versions: list[str], data: dict[str, dict[str, dict]]) -> str:
    components = sorted({c for rows in data.values() for c in rows})
    header = "| componente | " + " | ".join(f"{v} (Ca / Ce / I / A / D)" for v in versions) + " |"
    lines = [header, "|" + "---|" * (len(versions) + 1)]
    for component in components:
        cells = []
        for version in versions:
            row = data[version].get(component)
            if row is None:
                cells.append("—")
            else:
                mark = " **dor**" if in_pain_zone(row) else ""
                cells.append(f"{row['ca']} / {row['ce']} / {row['i']:.2f} / {row['a']:.2f} / {row['d']:.2f}{mark}")
        lines.append(f"| `{component}` | " + " | ".join(cells) + " |")
    totals = [sum(in_pain_zone(r) for r in data[v].values()) for v in versions]
    lines.append("| **componentes na zona de dor** | " + " | ".join(str(t) for t in totals) + " |")
    return "\n".join(lines)


def plot(versions: list[str], data: dict[str, dict[str, dict]], path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(9, 8))
    ax.plot([0, 1], [1, 0], color="#2e7d32", linestyle="--", label="Main Sequence (A + I = 1)")
    ax.fill_between([0, 0.5], 0, 0.5, color="#c62828", alpha=0.08, label="Zona de dor")
    ax.fill_between([0.5, 1], 0.5, 1, color="#f9a825", alpha=0.08, label="Zona de inutilidade")
    for n, version in enumerate(versions):
        rows = data[version].values()
        ax.scatter([r["i"] for r in rows], [r["a"] for r in rows], marker=MARKERS[n % len(MARKERS)],
                   color=COLORS[n % len(COLORS)], s=70, alpha=0.75, edgecolors="black", label=version)
    ax.set_xlim(-0.05, 1.05)
    ax.set_ylim(-0.05, 1.05)
    ax.set_xlabel("Instabilidade (I): estável → instável")
    ax.set_ylabel("Abstração (A): concreto → abstrato")
    ax.set_title("A × I por versão")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("versions", nargs="+", help="nomes dos CSVs em metrics/results, na ordem da evolução")
    parser.add_argument("--results", type=Path, default=RESULTS)
    args = parser.parse_args()

    data = {version: load(version, args.results) for version in args.versions}
    markdown = "# Acoplamento por versão\n\n" + table(args.versions, data) + "\n"
    (args.results / "comparison.md").write_text(markdown, encoding="utf-8")
    plot(args.versions, data, args.results / "comparison.png")
    print(markdown)


if __name__ == "__main__":
    main()
