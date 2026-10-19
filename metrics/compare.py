"""Compara as medições de várias versões (CSVs gerados por coupling.py).

Gera uma tabela Markdown com Ca, Ce, I, A e D de cada componente por versão e um
gráfico com um mapa A × I por versão, lado a lado.

Uso:
    uv run python metrics/compare.py v1-coupled v2-decoupled main
"""

import argparse
import csv
from pathlib import Path

RESULTS = Path(__file__).parent / "results"


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
    """Um painel por versão, lado a lado e com os mesmos eixos, para comparar ponto a ponto."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from coupling import draw_map

    fig, axes = plt.subplots(1, len(versions), figsize=(8 * len(versions), 8), squeeze=False)
    for ax, version in zip(axes[0], versions):
        rows = list(data[version].values())
        pain = sum(in_pain_zone(row) for row in rows)
        draw_map(ax, rows, f"{version}: {pain} na zona de dor")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
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
