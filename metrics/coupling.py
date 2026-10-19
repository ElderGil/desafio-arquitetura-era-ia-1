"""Mede acoplamento (Ca, Ce, I, A, D) por componente de um pacote Python.

Régua do requisito 3 do desafio, aplicada sem ajustes:

- componente: cada módulo .py do pacote, incluindo subpastas, exceto __init__.py,
  identificado pelo caminho com pontos relativo ao pacote (ex.: adapters.gateway);
- dependência: import relativo ou absoluto que resolve para outro componente;
  biblioteca externa e da biblioteca padrão não contam;
- Ca: quantos componentes importam este; Ce: quantos este importa;
- I = Ce / (Ce + Ca), ou 0 quando os dois são zero;
- A = classes abstratas (herdam de typing.Protocol ou abc.ABC) / total de classes
  do módulo, ou 0 sem classes;
- D = |A + I - 1|; I, A e D arredondados para 2 casas só na saída.

Uso:
    uv run python metrics/coupling.py app/helpdesk --name main
"""

import argparse
import ast
import csv
from dataclasses import dataclass
from pathlib import Path

ABSTRACT_BASES = {"Protocol", "typing.Protocol", "ABC", "abc.ABC"}


@dataclass
class Component:
    name: str
    path: Path
    depends_on: set[str]
    classes: int
    abstract_classes: int


def discover(package_dir: Path) -> dict[str, Path]:
    """Mapeia nome com pontos -> arquivo, para todo .py do pacote exceto __init__.py."""
    modules = {}
    for path in sorted(package_dir.rglob("*.py")):
        if path.name == "__init__.py":
            continue
        relative = path.relative_to(package_dir).with_suffix("")
        modules[".".join(relative.parts)] = path
    return modules


def _base_name(node: ast.expr) -> str:
    """Nome de uma classe base: Protocol, typing.Protocol, Protocol[T] -> Protocol."""
    if isinstance(node, ast.Subscript):
        return _base_name(node.value)
    if isinstance(node, ast.Attribute):
        return f"{_base_name(node.value)}.{node.attr}"
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _count_classes(tree: ast.Module) -> tuple[int, int]:
    classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    abstract = [c for c in classes if any(_base_name(b) in ABSTRACT_BASES for b in c.bases)]
    return len(classes), len(abstract)


def _resolve(parts: list[str], modules: dict[str, Path]) -> str | None:
    name = ".".join(parts)
    return name if name in modules else None


def _imports(name: str, tree: ast.Module, package: str, modules: dict[str, Path]) -> set[str]:
    """Componentes do pacote que este módulo importa."""
    own_package = name.split(".")[:-1]
    found = set()

    def add(parts: list[str]) -> None:
        target = _resolve(parts, modules)
        if target and target != name:
            found.add(target)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if parts[0] == package:
                    # import helpdesk.a.b resolve para o componente mais específico que existir
                    for end in range(len(parts), 1, -1):
                        if _resolve(parts[1:end], modules):
                            add(parts[1:end])
                            break
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                anchor = own_package[: len(own_package) - (node.level - 1)] if node.level > 1 else own_package
                if node.level - 1 > len(own_package):
                    continue
                base = anchor + (node.module.split(".") if node.module else [])
            elif node.module and node.module.split(".")[0] == package:
                base = node.module.split(".")[1:]
            else:
                continue
            # from .schemas import X -> schemas; from . import config -> config;
            # from .adapters import gateway -> adapters.gateway
            if base:
                add(base)
            for alias in node.names:
                add(base + [alias.name])
    return found


def analyze(package_dir: Path) -> dict[str, Component]:
    package_dir = package_dir.resolve()
    package = package_dir.name
    modules = discover(package_dir)
    components = {}
    for name, path in modules.items():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        classes, abstract = _count_classes(tree)
        components[name] = Component(name, path, _imports(name, tree, package, modules), classes, abstract)
    return components


def metrics(components: dict[str, Component]) -> list[dict]:
    rows = []
    for name in sorted(components):
        component = components[name]
        ce = len(component.depends_on)
        ca = sum(1 for other in components.values() if name in other.depends_on)
        i = ce / (ce + ca) if ce + ca else 0.0
        a = component.abstract_classes / component.classes if component.classes else 0.0
        d = abs(a + i - 1)
        rows.append({"component": name, "ca": ca, "ce": ce, "i": round(i, 2), "a": round(a, 2), "d": round(d, 2)})
    return rows


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["component", "ca", "ce", "i", "a", "d"])
        writer.writeheader()
        writer.writerows(rows)


def cycles(components: dict[str, Component]) -> list[list[str]]:
    """Ciclos de dependência: componentes fortemente conexos com mais de um membro (Tarjan)."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    found: list[list[str]] = []

    def visit(name: str) -> None:
        index[name] = low[name] = len(index)
        stack.append(name)
        on_stack.add(name)
        for target in sorted(components[name].depends_on):
            if target not in index:
                visit(target)
                low[name] = min(low[name], low[target])
            elif target in on_stack:
                low[name] = min(low[name], index[target])
        if low[name] == index[name]:
            group = []
            while True:
                member = stack.pop()
                on_stack.discard(member)
                group.append(member)
                if member == name:
                    break
            if len(group) > 1:
                found.append(sorted(group))

    for name in sorted(components):
        if name not in index:
            visit(name)
    return sorted(found)


def write_dependencies(components: dict[str, Component], rows: list[dict], title: str, path: Path) -> None:
    """Grafo de dependências em Mermaid (renderiza no GitHub) e lista de ciclos."""
    pain = {row["component"] for row in rows if in_pain_zone(row)}
    ids = {name: f"c{n}" for n, name in enumerate(sorted(components))}
    lines = [f"# Dependências entre componentes: {title}", "", "```mermaid", "graph LR"]
    for name in sorted(components):
        lines.append(f'    {ids[name]}["{name}"]')
    for name in sorted(components):
        for target in sorted(components[name].depends_on):
            lines.append(f"    {ids[name]} --> {ids[target]}")
    if pain:
        lines.append("    classDef dor fill:#ffcdd2,stroke:#c62828")
        lines.append("    class " + ",".join(ids[name] for name in sorted(pain)) + " dor")
    lines += ["```", "", "Em vermelho, os componentes na zona de dor (A < 0,5, I < 0,5 e D ≥ 0,5).", "", "## Ciclos", ""]
    found = cycles(components)
    lines += [f"- {' ↔ '.join(group)}" for group in found] if found else ["Nenhum ciclo de dependência."]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def in_pain_zone(row: dict) -> bool:
    """Critério de aceite da main: A < 0,5, I < 0,5 e D >= 0,5 ao mesmo tempo."""
    return row["a"] < 0.5 and row["i"] < 0.5 and row["d"] >= 0.5


def draw_map(ax, rows: list[dict], title: str) -> None:
    """Desenha o mapa A x I com Main Sequence, zonas e rótulos legíveis num eixo do matplotlib."""
    ax.plot([0, 1], [1, 0], color="#2e7d32", linestyle="--", linewidth=1.5, label="Main Sequence (A + I = 1)")
    ax.fill_between([0, 0.5], 0, 0.5, color="#c62828", alpha=0.10, label="Zona de dor")
    ax.fill_between([0.5, 1], 0.5, 1, color="#f9a825", alpha=0.12, label="Zona de inutilidade")

    # Componentes no mesmo ponto ganham um rótulo só, com os nomes empilhados. Pontos
    # vizinhos na mesma altura alternam o rótulo entre acima e abaixo, para não encavalar.
    points: dict[tuple[float, float], list[dict]] = {}
    for row in rows:
        points.setdefault((row["i"], row["a"]), []).append(row)
    previous: tuple[float, float] | None = None
    below = False
    for (i, a), group in sorted(points.items()):
        crowded = previous is not None and previous[1] == a and i - previous[0] < 0.25
        below = (not below) if crowded else False
        previous = (i, a)
        pain = in_pain_zone(group[0])
        ax.scatter(i, a, s=80 + 25 * max(r["ca"] for r in group), color="#c62828" if pain else "#1565c0",
                   alpha=0.9, edgecolors="black", zorder=3)
        lines = len(group)
        ax.annotate("\n".join(r["component"] for r in group), (i, a), textcoords="offset points",
                    xytext=(8, -14 * lines - 6 if below else 8), fontsize=10, color="black",
                    fontweight="bold" if pain else "normal", zorder=4,
                    bbox={"boxstyle": "round,pad=0.25", "facecolor": "white", "edgecolor": "#9e9e9e", "alpha": 0.95})
    ax.set_xlim(-0.05, 1.15)
    ax.set_ylim(-0.25, 1.05)
    ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_xlabel("Instabilidade (I): estável → instável", fontsize=11)
    ax.set_ylabel("Abstração (A): concreto → abstrato", fontsize=11)
    ax.set_title(title, fontsize=13)
    ax.legend(loc="upper right", fontsize=10)
    ax.grid(alpha=0.3)


def plot(rows: list[dict], title: str, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (ax, side) = plt.subplots(1, 2, figsize=(15, 8), gridspec_kw={"width_ratios": [3, 2]})
    draw_map(ax, rows, f"A × I por componente: {title}")

    # Tabela legível: texto preto em fundo branco; zona de dor em branco e negrito
    # sobre vermelho escuro, para o contraste não depender de cor clara.
    side.axis("off")
    cells = [[r["component"], r["ca"], r["ce"], f"{r['i']:.2f}", f"{r['a']:.2f}", f"{r['d']:.2f}"] for r in rows]
    table = side.table(cellText=cells, colLabels=["componente", "Ca", "Ce", "I", "A", "D"], loc="center",
                       cellLoc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(11)
    table.scale(1, 1.6)
    table.auto_set_column_width(list(range(6)))
    for column in range(6):
        header = table[0, column]
        header.set_facecolor("#37474f")
        header.get_text().set_color("white")
        header.get_text().set_fontweight("bold")
    for index, row in enumerate(rows, start=1):
        table[index, 0].get_text().set_horizontalalignment("left")
        if in_pain_zone(row):
            for column in range(6):
                table[index, column].set_facecolor("#b71c1c")
                table[index, column].get_text().set_color("white")
                table[index, column].get_text().set_fontweight("bold")
    side.set_title("Em vermelho: zona de dor (A < 0,5, I < 0,5 e D ≥ 0,5)", fontsize=10, color="#b71c1c")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=120)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("package", type=Path, help="pasta do pacote a medir (ex.: app/helpdesk)")
    parser.add_argument("--name", required=True, help="nome do resultado (ex.: v1-coupled)")
    parser.add_argument("--out", type=Path, default=Path(__file__).parent / "results")
    args = parser.parse_args()

    components = analyze(args.package)
    rows = metrics(components)
    write_csv(rows, args.out / f"{args.name}.csv")
    plot(rows, args.name, args.out / f"{args.name}.png")
    write_dependencies(components, rows, args.name, args.out / f"{args.name}-dependencies.md")
    for row in rows:
        flag = "  <- zona de dor" if in_pain_zone(row) else ""
        print(f"{row['component']:<24} Ca={row['ca']} Ce={row['ce']} I={row['i']:.2f} A={row['a']:.2f} D={row['d']:.2f}{flag}")


if __name__ == "__main__":
    main()
