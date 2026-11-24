from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app import main


@pytest.mark.parametrize(
    ("available", "code", "status"),
    [(True, 200, "ok"), (False, 503, "unavailable")],
)
def test_health_response(monkeypatch, available, code, status):
    engine = MagicMock()

    @contextmanager
    def session_factory():
        session = MagicMock()
        if not available:
            session.execute.side_effect = OperationalError("SELECT 1", None, Exception())
        yield session

    monkeypatch.setattr(main, "create_database_engine", lambda: engine)
    monkeypatch.setattr(main, "create_session_factory", lambda _: session_factory)

    with TestClient(main.app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == code
    assert response.json() == {"status": status, "database": status}
    assert response.headers["Cache-Control"] == "no-store"
    engine.dispose.assert_called_once()
