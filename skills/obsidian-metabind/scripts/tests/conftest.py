from pathlib import Path
import sys

SCRIPTS_DIR = Path(__file__).resolve().parent.parent

FIXTURES = Path(__file__).resolve().parent / "fixtures"
TEST_VAULT = FIXTURES / "test_vault"


def _claim_flat_module_names() -> None:
    """Bind this skill's scripts/ ahead of any sibling skill's same-named modules.

    Skills import siblings flatly (`from refresh_docs import ...`) because their
    scripts run as `python3 path/to/script.py`. Python caches those by bare name,
    so in a whole-repo pytest run the first skill collected wins `refresh_docs`
    for every skill after it. pytest imports a directory's conftest immediately
    before that directory's test modules, so evicting here is enough — and it is
    symmetric, each skill reclaiming its own names as it is collected.
    """
    if str(SCRIPTS_DIR) in sys.path:
        sys.path.remove(str(SCRIPTS_DIR))
    sys.path.insert(0, str(SCRIPTS_DIR))

    for name, module in list(sys.modules.items()):
        origin = getattr(module, "__file__", None)
        if origin is None or "." in name:
            continue
        directory = Path(origin).parent
        if directory.name == "scripts" and directory != SCRIPTS_DIR:
            del sys.modules[name]


_claim_flat_module_names()
