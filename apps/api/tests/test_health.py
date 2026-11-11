from app.main import create_app


async def test_liveness(anon):
    r = await anon.get("/health/live")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


async def test_readiness_ok(anon):
    r = await anon.get("/health/ready")
    assert r.status_code == 200
    assert r.json()["checks"]["database"] == "ok"


async def test_readiness_failure_leaks_nothing(anon, monkeypatch):
    import app.main as main

    def broken():
        raise OSError("connection refused to postgresql://user:secret@db")

    monkeypatch.setattr(main, "get_engine", broken)
    r = await anon.get("/health/ready")
    assert r.status_code == 503
    assert "secret" not in r.text and "postgresql" not in r.text


async def test_correlation_id_echoed(anon):
    r = await anon.get("/health/live", headers={"X-Request-ID": "abc12345-req"})
    assert r.headers["x-request-id"] == "abc12345-req"
    r = await anon.get("/health/live", headers={"X-Request-ID": "bad id with spaces"})
    assert r.headers["x-request-id"] != "bad id with spaces"


def test_openapi_documents_core_endpoints():
    paths = create_app().openapi()["paths"]
    for p in [
        "/api/v1/auth/login",
        "/api/v1/auth/logout",
        "/api/v1/users/me",
        "/api/v1/patients",
        "/api/v1/patients/{patient_id}",
        "/api/v1/patients/{patient_id}/encounters",
        "/api/v1/encounters/{encounter_id}",
        "/api/v1/encounters/{encounter_id}/intake-sessions",
        "/api/v1/intake-sessions/{session_id}/answers",
        "/api/v1/encounters/{encounter_id}/documents",
        "/api/v1/documents/{document_id}/process",
        "/api/v1/encounters/{encounter_id}/summaries/generate",
        "/api/v1/summaries/{summary_id}/approve",
        "/api/v1/dashboard/overview",
    ]:
        assert p in paths, p


async def test_access_log_omits_query_strings(anon, capsys):
    from app.core.logging import configure_logging

    configure_logging()
    await anon.get("/health/live?q=SyntheticPatientName")
    out = capsys.readouterr().out + capsys.readouterr().err
    assert "/health/live" in out and "SyntheticPatientName" not in out
