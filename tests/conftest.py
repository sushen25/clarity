from __future__ import annotations

import io
from pathlib import Path

import pytest

from app import create_app
from app.auth import bootstrap_admin


@pytest.fixture()
def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret-key-that-is-long-enough",
        "DATABASE_PATH": str(tmp_path / "app.db"),
        "STORAGE_ROOT": str(tmp_path / "storage"),
        "SESSION_COOKIE_SECURE": False,
        "BEDROCK_ENABLED": False,
        "REPORT_TEMPLATE": str(Path(__file__).parents[1] / "templates" / "adhd_report_template.docx"),
        "LIBREOFFICE_BIN": "soffice",
    })
    with app.app_context():
        bootstrap_admin("admin", "A-very-long-Test-Password-2026", "Dr Test Clinician", "PSY0000000001")
    return app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def authenticated(client):
    response = client.post("/api/auth/login", json={"username": "admin", "password": "A-very-long-Test-Password-2026"})
    assert response.status_code == 200
    return client, {"X-CSRF-Token": response.json["csrf_token"]}


@pytest.fixture()
def sample_txt():
    text = (
        "The patient described childhood difficulty sustaining attention and often forgot school materials.\n\n"
        "At home, their parent reported frequent distraction and difficulty completing multi-step tasks.\n\n"
        "At work, the patient reported missing deadlines, which caused significant occupational difficulty.\n\n"
        "Medical history was reviewed and hearing, vision, sleep, and current medication were discussed.\n\n"
        "Mental health history included anxiety. Differential considerations and co-occurring conditions were reviewed.\n\n"
        "Strengths include persistence, humour, and strong practical problem-solving."
    )
    return io.BytesIO(text.encode()), "transcript.txt"

