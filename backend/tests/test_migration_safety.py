"""Static guards on the migration tree. The backend runs `alembic upgrade head`
on every start, so a second head or a model Alembic can't see is a failed or
destructive deploy. The live upgrade/check/downgrade cycle runs in CI's
backend-migrations job; these catch the same mistakes without a database."""

import ast
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_ENV = _BACKEND / "migrations" / "env.py"
_VERSIONS = _BACKEND / "migrations" / "versions"
_MODELS = _BACKEND / "app" / "models"


def _assigned(tree: ast.Module, name: str) -> object:
    for node in tree.body:
        if isinstance(node, ast.AnnAssign):
            targets, value = [node.target], node.value
        elif isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        else:
            continue
        if value is not None and any(
            isinstance(target, ast.Name) and target.id == name for target in targets
        ):
            return ast.literal_eval(value)
    raise AssertionError(f"{name} is not assigned")


def test_env_imports_every_model_module() -> None:
    tree = ast.parse(_ENV.read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "app.models"
        for alias in node.names
    }
    modules = {path.stem for path in _MODELS.glob("*.py") if path.stem != "__init__"}
    # A model module env.py doesn't import is invisible to autogenerate and to
    # `alembic check`, which would then propose dropping its tables.
    assert modules - imported == set()


def test_revisions_form_one_linear_chain() -> None:
    parents: dict[str, str | None] = {}
    for path in sorted(_VERSIONS.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        revision = _assigned(tree, "revision")
        down_revision = _assigned(tree, "down_revision")
        assert isinstance(revision, str), path.name
        assert down_revision is None or isinstance(down_revision, str), (
            f"{path.name}: merge revisions need a deliberate review"
        )
        assert _assigned(tree, "branch_labels") is None, path.name
        assert revision not in parents, f"duplicate revision {revision}"
        parents[revision] = down_revision

    roots = [rev for rev, parent in parents.items() if parent is None]
    assert len(roots) == 1
    assert all(parent in parents for parent in parents.values() if parent is not None)
    children = [parent for parent in parents.values() if parent is not None]
    assert len(children) == len(set(children)), "two revisions share a parent"
    heads = set(parents) - set(children)
    assert len(heads) == 1, f"multiple heads: {sorted(heads)}"
