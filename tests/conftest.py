import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import pytest  # noqa: E402

from base_conhecimento import carregar  # noqa: E402

DATA_REF = "2025-11-01"


@pytest.fixture(scope="session")
def base():
    return carregar()


@pytest.fixture(scope="session")
def data_ref():
    return DATA_REF
