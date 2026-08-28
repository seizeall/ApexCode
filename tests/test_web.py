from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.web.app import create_app


def test_web_serves_workbench_and_workspace(tmp_path: Path) -> None:
    (tmp_path / "demo.py").write_text("print('ok')", encoding="utf-8")
    client = TestClient(create_app(Settings(workspace=tmp_path)))
    page = client.get("/")
    assert page.status_code == 200
    assert "ApexCode" in page.text
    assert 'id="run-log"' not in page.text
    assert "运行记录" not in page.text
    tree = client.get("/api/workspace/tree")
    assert tree.status_code == 200
    assert tree.json()["entries"][0]["name"] == "demo.py"


def test_web_rejects_unknown_mode(tmp_path: Path) -> None:
    client = TestClient(create_app(Settings(workspace=tmp_path)))
    session_id = client.post("/api/sessions").json()["session_id"]
    response = client.post(f"/api/sessions/{session_id}/messages", json={"prompt": "test", "mode": "unknown"})
    assert response.status_code == 400
