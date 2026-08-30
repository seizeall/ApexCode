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
    assert 'id="details-drawer"' in page.text
    assert "不展示模型内部思考" in page.text
    assert "message-meta" in (Path("app/web/static/app.js").read_text(encoding="utf-8"))
    assert "markdownToHtml" in Path("app/web/static/app.js").read_text(encoding="utf-8")
    assert "markdown-table" in Path("app/web/static/styles.css").read_text(encoding="utf-8")
    tree = client.get("/api/workspace/tree")
    assert tree.status_code == 200
    assert tree.json()["entries"][0]["name"] == "demo.py"


def test_web_rejects_unknown_mode(tmp_path: Path) -> None:
    client = TestClient(create_app(Settings(workspace=tmp_path)))
    session_id = client.post("/api/sessions").json()["session_id"]
    response = client.post(f"/api/sessions/{session_id}/messages", json={"prompt": "test", "mode": "unknown"})
    assert response.status_code == 400


def test_web_exposes_cancel_endpoint(tmp_path: Path) -> None:
    client = TestClient(create_app(Settings(workspace=tmp_path)))
    session_id = client.post("/api/sessions").json()["session_id"]
    # A cancel request is accepted even while the model task is still queued.
    response = client.post(f"/api/sessions/{session_id}/messages", json={"prompt": "test", "mode": "plan"})
    run_id = response.json()["run_id"]
    assert client.post(f"/api/runs/{run_id}/cancel").status_code == 200
    # Drain the event stream so the background task has a chance to clean up.
    with client.stream("GET", f"/api/runs/{run_id}/events") as events:
        assert any('"type": "done"' in line for line in events.iter_lines())


def test_session_history_is_persisted(tmp_path: Path) -> None:
    from app.session_store import SessionStore

    store = SessionStore(tmp_path / "sessions.json")
    import asyncio
    asyncio.run(store.save("session-1", [{"role": "user", "content": "hello"}]))
    assert asyncio.run(store.get("session-1"))[0]["content"] == "hello"
