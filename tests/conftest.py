from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.main import create_app


async def mock_get_db() -> AsyncGenerator[AsyncSession, None]:
    mock_session = AsyncMock(spec=AsyncSession)

    mock_session.execute.return_value = MagicMock()

    yield mock_session


@pytest.fixture(scope="session")
def test_client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_db] = mock_get_db
    return TestClient(app)
