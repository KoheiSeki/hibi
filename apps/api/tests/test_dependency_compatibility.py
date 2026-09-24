import arq
import asyncpg
import typesafe_sdk
from typesafe_sdk import AsyncTypeSafeClient, Choice, Noul, Score


def test_python_314_runtime_dependencies_import() -> None:
    assert arq.__version__
    assert asyncpg.__version__
    assert typesafe_sdk.__version__
    assert AsyncTypeSafeClient
    assert Choice
    assert Noul
    assert Score
