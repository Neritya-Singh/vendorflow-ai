"""Deploy readiness (Render): client IPs, throttling and cookies behind the platform proxy,
and a health check that needs no secrets. OFFLINE."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.services import ServiceProvider
from tests.test_v2_api import ADMIN_PASSWORD, settings

ROOT = Path(__file__).resolve().parents[1]


def app_client(monkeypatch, trust_proxy: bool, **overrides) -> TestClient:
    monkeypatch.setenv("TRUST_PROXY", "1" if trust_proxy else "")
    s = settings(**overrides)
    return TestClient(create_app(s, ServiceProvider(s)))


def wrong_login(client, headers):
    return client.post("/api/admin/session", json={"password": "wrong-password"}, headers=headers)


def test_spoofed_left_most_forwarded_for_cannot_dodge_the_login_lockout(monkeypatch):
    client = app_client(monkeypatch, trust_proxy=True)
    # The proxy appends the real address; the client controls everything to its left.
    codes = [wrong_login(client, {"X-Forwarded-For": f"10.9.9.{i}, 203.0.113.7"}).status_code for i in range(6)]
    assert codes[:4] == [401] * 4 and codes[-1] == 429


def test_cloudflare_client_ip_separates_real_clients(monkeypatch):
    client = app_client(monkeypatch, trust_proxy=True)
    for _ in range(5):
        wrong_login(client, {"CF-Connecting-IP": "198.51.100.1", "X-Forwarded-For": "172.70.0.1"})
    assert wrong_login(client, {"CF-Connecting-IP": "198.51.100.1", "X-Forwarded-For": "172.70.0.1"}).status_code == 429
    # Another visitor behind the same Cloudflare edge is not locked out.
    other = client.post("/api/admin/session", json={"password": ADMIN_PASSWORD},
                        headers={"CF-Connecting-IP": "198.51.100.2", "X-Forwarded-For": "172.70.0.1"})
    assert other.status_code == 200


def test_forwarded_headers_are_ignored_without_trust_proxy(monkeypatch):
    client = app_client(monkeypatch, trust_proxy=False)
    for i in range(5):
        wrong_login(client, {"CF-Connecting-IP": f"198.51.100.{i}", "X-Forwarded-For": f"10.0.0.{i}"})
    assert wrong_login(client, {"CF-Connecting-IP": "198.51.100.99"}).status_code == 429


def test_garbage_forwarded_values_fall_back_to_the_peer(monkeypatch):
    client = app_client(monkeypatch, trust_proxy=True)
    for i in range(5):
        wrong_login(client, {"CF-Connecting-IP": f"not-an-ip-{i}", "X-Forwarded-For": f"also-not-{i}"})
    assert wrong_login(client, {"X-Forwarded-For": "nonsense"}).status_code == 429


def test_admin_cookie_is_secure_httponly_strict_by_default(monkeypatch):
    client = app_client(monkeypatch, trust_proxy=True, cookie_secure=True)
    response = client.post("/api/admin/session", json={"password": ADMIN_PASSWORD})
    cookie = response.headers["set-cookie"].lower()
    assert response.status_code == 200
    assert "secure" in cookie and "httponly" in cookie and "samesite=strict" in cookie and "path=/api" in cookie


def test_health_needs_no_secrets(tmp_path):
    """Starts the real settings loader in a copy of the server code with NO .env and an
    empty environment, as in the container before secrets are configured."""
    for part in ("backend", "vendorflow"):  # a real copy: the loader looks for .env beside the code
        shutil.copytree(ROOT / part, tmp_path / part, ignore=shutil.ignore_patterns("__pycache__"))
    assert not (tmp_path / ".env").exists()
    script = ("from fastapi.testclient import TestClient\n"
              "from backend.main import create_app\n"
              "r = TestClient(create_app()).get('/api/health')\n"
              "print(r.status_code, r.json())\n")
    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(tmp_path)}
    out = subprocess.run([sys.executable, "-c", script], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-2000:]
    assert out.stdout.startswith("200 "), out.stdout
    assert "'status': 'ok'" in out.stdout and "'gemini_configured': False" in out.stdout
    assert "'supabase_configured': False" in out.stdout and "'admin_configured': False" in out.stdout


@pytest.mark.parametrize("line", ["--no-proxy-headers", "${PORT:-8000}", "tesseract-ocr", "npm run build"])
def test_dockerfile_contract(line):
    assert line in (ROOT / "Dockerfile").read_text()
