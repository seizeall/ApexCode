from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.web.app import create_app


def test_web_serves_workbench_without_workspace_sidebar(tmp_path: Path) -> None:
    (tmp_path / "demo.py").write_text("print('ok')", encoding="utf-8")
    client = TestClient(create_app(Settings(workspace=tmp_path)))
    page = client.get("/")
    assert page.status_code == 200
    assert "ApexCode" in page.text
    assert 'class="inspector panel"' not in page.text
    assert 'id="file-tree"' not in page.text
    assert 'id="run-log"' not in page.text
    assert "运行记录" not in page.text
    assert 'id="details-drawer"' in page.text
    assert 'id="process-panel"' in page.text
    assert 'id="upload-file-button"' in page.text
    assert 'id="upload-project-button"' in page.text
    assert 'id="api-settings"' in page.text
    assert 'id="preview-launch"' in page.text
    assert 'id="preview-frame"' in page.text
    assert 'id="live-progress"' in page.text
    assert 'id="api-base-url"' in page.text
    composer_start = page.text.index('id="composer"')
    assert page.text.index('id="upload-file-button"') > composer_start
    assert page.text.index('id="upload-project-button"') > composer_start
    assert page.text.index('id="new-session"') < composer_start
    assert "不展示逐字内部思维链" in page.text
    assert "message-meta" in (Path("app/web/static/app.js").read_text(encoding="utf-8"))
    assert "markdownToHtml" in Path("app/web/static/app.js").read_text(encoding="utf-8")
    assert "markdown-table" in Path("app/web/static/styles.css").read_text(encoding="utf-8")
    tree = client.get("/api/workspace/tree")
    assert tree.status_code == 200
    assert tree.json()["entries"][0]["name"] == "demo.py"


def test_preview_finds_build_output_and_serves_assets_safely(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<h1>root</h1>", encoding="utf-8")
    internal = tmp_path / "app" / "web" / "static"
    internal.mkdir(parents=True)
    (internal / "index.html").write_text("<h1>workbench</h1>", encoding="utf-8")
    site = tmp_path / "website"
    (site / "dist").mkdir(parents=True)
    (site / "index.html").write_text("<h1>source</h1>", encoding="utf-8")
    (site / "dist" / "index.html").write_text('<link rel="stylesheet" href="app.css"><h1>built</h1>', encoding="utf-8")
    (site / "dist" / "app.css").write_text("body { color: green; }", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=not-for-preview", encoding="utf-8")
    client = TestClient(create_app(Settings(workspace=tmp_path)))

    candidates = client.get("/api/preview/candidates").json()["candidates"]
    assert candidates[0]["path"] == "website/dist/index.html"
    assert "app/web/static/index.html" not in {item["path"] for item in candidates}
    assert client.get(candidates[0]["url"]).text.endswith("<h1>built</h1>")
    assert client.get("/preview/website/dist/app.css").text == "body { color: green; }"
    assert client.get("/preview/.env").status_code == 404


def test_preview_origin_cannot_access_agent_api(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<h1>preview</h1>", encoding="utf-8")
    client = TestClient(create_app(Settings(workspace=tmp_path)))
    assert client.get("/preview/index.html", headers={"host": "localhost:8000"}).status_code == 200
    assert client.get("/api/config", headers={"host": "localhost:8000"}).status_code == 403


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


def test_session_can_be_renamed_and_deleted(tmp_path: Path) -> None:
    client = TestClient(create_app(Settings(workspace=tmp_path, session_file=tmp_path / "sessions.json")))
    session_id = client.post("/api/sessions").json()["session_id"]
    renamed = client.patch(f"/api/sessions/{session_id}", json={"name": "登录问题修复"})
    assert renamed.status_code == 200
    listed = client.get("/api/sessions").json()["sessions"]
    assert listed[0]["title"] == "登录问题修复"
    deleted = client.delete(f"/api/sessions/{session_id}")
    assert deleted.status_code == 200
    assert client.get(f"/api/sessions/{session_id}/history").status_code == 404


def test_session_can_be_named_when_created(tmp_path: Path) -> None:
    client = TestClient(create_app(Settings(workspace=tmp_path, session_file=tmp_path / "sessions.json")))
    response = client.post("/api/sessions", json={"name": "新功能开发"})
    assert response.status_code == 200
    session_id = response.json()["session_id"]
    item = next(item for item in client.get("/api/sessions").json()["sessions"] if item["session_id"] == session_id)
    assert item["title"] == "新功能开发" and item["name"] == "新功能开发"


def test_session_name_is_validated(tmp_path: Path) -> None:
    client = TestClient(create_app(Settings(workspace=tmp_path, session_file=tmp_path / "sessions.json")))
    assert client.post("/api/sessions", json={"name": " "}).status_code == 200
    assert client.post("/api/sessions", json={"name": "x" * 81}).status_code == 400


def test_workspace_upload_preserves_relative_paths(tmp_path: Path) -> None:
    client = TestClient(create_app(Settings(workspace=tmp_path, session_file=tmp_path / "sessions.json")))
    response = client.post(
        "/api/workspace/upload",
        files=[("files", ("main.py", b"print('ok')", "text/x-python"))],
        data={"paths": "demo/main.py"},
    )
    assert response.status_code == 200
    assert (tmp_path / "demo" / "main.py").read_text(encoding="utf-8") == "print('ok')"


def test_workspace_upload_rejects_escape(tmp_path: Path) -> None:
    client = TestClient(create_app(Settings(workspace=tmp_path, session_file=tmp_path / "sessions.json")))
    response = client.post(
        "/api/workspace/upload",
        files=[("files", ("secret.txt", b"no", "text/plain"))],
        data={"paths": "../secret.txt"},
    )
    assert response.status_code == 400


def test_workspace_upload_uses_dedicated_upload_limits(tmp_path: Path) -> None:
    client = TestClient(create_app(Settings(workspace=tmp_path, max_file_bytes=4, max_upload_file_bytes=8, max_upload_total_bytes=12)))
    config = client.get("/api/config").json()["upload_limits"]
    assert config == {"max_files": 200, "max_file_bytes": 8, "max_total_bytes": 12}
    accepted = client.post("/api/workspace/upload", files=[("files", ("image.png", b"12345678", "image/png"))])
    assert accepted.status_code == 200
    rejected = client.post("/api/workspace/upload", files=[("files", ("large.png", b"123456789", "image/png"))])
    assert rejected.status_code == 413


def test_api_config_can_be_saved_without_exposing_key(tmp_path: Path) -> None:
    config_file = tmp_path / ".env"
    client = TestClient(create_app(Settings(workspace=tmp_path, config_file=config_file)))
    target_workspace = tmp_path / "site-project"
    response = client.post("/api/config", json={"base_url": "https://gateway.example/v1/", "api_key": "secret-test-key", "model": "tool-model", "workspace": str(target_workspace)})
    assert response.status_code == 200
    assert response.json() == {"configured": True, "base_url": "https://gateway.example/v1", "model": "tool-model", "workspace": str(target_workspace)}
    public_config = client.get("/api/config").json()
    assert public_config["configured"] is True
    assert "api_key" not in public_config and "secret-test-key" not in str(public_config)
    saved = config_file.read_text(encoding="utf-8")
    assert "CODING_AGENT_API_KEY='secret-test-key'" in saved
    from dotenv import dotenv_values
    assert dotenv_values(config_file)["CODING_AGENT_WORKSPACE"] == str(target_workspace)
    assert target_workspace.is_dir()
    uploaded = client.post(
        "/api/workspace/upload",
        files=[("files", ("index.html", b"<h1>site</h1>", "text/html"))],
        data={"paths": "website/index.html"},
    )
    assert uploaded.status_code == 200
    assert (target_workspace / "website" / "index.html").read_text(encoding="utf-8") == "<h1>site</h1>"
    assert not (tmp_path / "website" / "index.html").exists()


def test_api_config_requires_valid_url_and_initial_key(tmp_path: Path) -> None:
    client = TestClient(create_app(Settings(workspace=tmp_path, config_file=tmp_path / ".env")))
    valid_workspace = str(tmp_path / "workspace")
    assert client.post("/api/config", json={"base_url": "not-a-url", "api_key": "key", "model": "model", "workspace": valid_workspace}).status_code == 422
    assert client.post("/api/config", json={"base_url": "https://example.test/v1", "api_key": "", "model": "model", "workspace": valid_workspace}).status_code == 400
    assert client.post("/api/config", json={"base_url": "https://example.test/v1", "api_key": "key", "model": "model", "workspace": "relative/path"}).status_code == 400


def test_session_name_is_persisted_in_metadata(tmp_path: Path) -> None:
    from app.session_store import SessionStore
    import asyncio

    store = SessionStore(tmp_path / "sessions.json")
    asyncio.run(store.save("session-1", []))
    asyncio.run(store.rename("session-1", "保留名称"))
    assert asyncio.run(store.metadata())["session-1"] == "保留名称"
    asyncio.run(store.delete("session-1"))
    assert "session-1" not in asyncio.run(store.metadata())
