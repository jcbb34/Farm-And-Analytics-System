"""Check migration graph and rollback definitions without connecting to SQL Server."""

import ast
from pathlib import Path


VERSIONS = Path(__file__).resolve().parents[1] / "migrations" / "versions"


def assigned_value(tree, name):
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            return ast.literal_eval(node.value)
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id == name:
            return ast.literal_eval(node.value)
    raise ValueError(f"Missing {name}.")


def validate():
    parents_by_revision = {}
    documented_data_only_rollbacks = []
    files = sorted(VERSIONS.glob("*.py"))
    if not files:
        raise ValueError("No migration scripts found.")

    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        revision = assigned_value(tree, "revision")
        prior = assigned_value(tree, "down_revision")
        if not isinstance(revision, str) or revision in parents_by_revision:
            raise ValueError(f"Missing or duplicate revision in {path.name}.")
        parents = () if prior is None else (prior,) if isinstance(prior, str) else tuple(prior)
        parents_by_revision[revision] = parents

        for name in ("upgrade", "downgrade"):
            definitions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
            if len(definitions) != 1:
                raise ValueError(f"{path.name} must define one {name} function.")
            function = definitions[0]
            actions = [node for node in function.body if not (
                isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)
            )]
            if not actions or all(isinstance(node, ast.Pass) for node in actions):
                if name != "downgrade" or not ast.get_docstring(function):
                    raise ValueError(f"{path.name} has an undocumented empty {name}.")
                documented_data_only_rollbacks.append(revision)

    referenced = {parent for parents in parents_by_revision.values() for parent in parents}
    missing = referenced - parents_by_revision.keys()
    heads = set(parents_by_revision) - referenced
    if missing or len(heads) != 1:
        raise ValueError(f"Migration graph has missing parents {sorted(missing)} or heads {sorted(heads)}.")

    for revision in parents_by_revision:
        visited = set()
        stack = [revision]
        while stack:
            current = stack.pop()
            if current in visited:
                raise ValueError(f"Cycle in migration ancestry of {revision}.")
            visited.add(current)
            stack.extend(parents_by_revision[current])

    print(f"Checked {len(files)} migrations: one head {next(iter(heads))}; upgrade/downgrade defined.")
    if documented_data_only_rollbacks:
        print("Data-only rollback intentionally preserves records:", ", ".join(documented_data_only_rollbacks))


if __name__ == "__main__":
    validate()
