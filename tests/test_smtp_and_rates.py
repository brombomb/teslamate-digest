import pytest
from unittest.mock import MagicMock, patch
from app.config import AppConfig, RatesSettings, SMTPSettings
from app.mailer import Mailer


def test_default_zip_code():
    rates = RatesSettings()
    assert rates.zip_code == "12345"


def test_smtp_settings_fields():
    smtp = SMTPSettings(
        enabled=True,
        host="mail.example.com",
        port=465,
        user="custom_user",
        password="secretpassword",
        sender_email="digest@example.com",
        sender_name="My Custom Digest",
        recipient_email="inbox@example.com",
        use_tls=False,
        use_ssl=True
    )
    assert smtp.sender_email == "digest@example.com"
    assert smtp.use_tls is False
    assert smtp.use_ssl is True
    assert smtp.port == 465

    # Check serialization / dump
    dump = smtp.model_dump()
    assert dump["sender_email"] == "digest@example.com"
    assert dump["use_tls"] is False
    assert dump["use_ssl"] is True


def test_mailer_sender_resolution():
    # Case 1: sender_email is explicitly set
    smtp1 = SMTPSettings(
        enabled=True,
        host="smtp.example.com",
        port=587,
        user="auth_user",
        password="app_password",
        sender_email="explicit_sender@domain.com",
        sender_name="TeslaMate Digest",
        recipient_email="recipient@example.com",
        use_tls=True,
        use_ssl=False
    )
    mailer1 = Mailer(smtp1)
    with patch("smtplib.SMTP") as mock_smtp:
        mock_server = MagicMock()
        mock_smtp.return_value = mock_server
        mailer1.send_email("Test Subject", "<p>Hello</p>")
        
        # Verify server called with correct From address
        args, _ = mock_server.sendmail.call_args
        assert args[0] == "explicit_sender@domain.com"
        assert args[1] == ["recipient@example.com"]

    # Case 2: sender_email is empty -> falls back to user
    smtp2 = SMTPSettings(
        enabled=True,
        host="smtp.example.com",
        port=587,
        user="fallback_user@gmail.com",
        password="app_password",
        sender_email="",
        sender_name="TeslaMate Digest",
        recipient_email="recipient@example.com",
        use_tls=True,
        use_ssl=False
    )
    mailer2 = Mailer(smtp2)
    with patch("smtplib.SMTP") as mock_smtp:
        mock_server = MagicMock()
        mock_smtp.return_value = mock_server
        mailer2.send_email("Test Subject", "<p>Hello</p>")
        
        args, _ = mock_server.sendmail.call_args
        assert args[0] == "fallback_user@gmail.com"
        assert args[1] == ["recipient@example.com"]


def test_mailer_verify_smtp_empty_host():
    smtp = SMTPSettings(host="")
    mailer = Mailer(smtp)
    res = mailer.verify_smtp()
    assert res["success"] is False
    assert "empty" in res["message"].lower()


def test_mailer_verify_smtp_success():
    smtp = SMTPSettings(
        host="smtp.gmail.com",
        port=587,
        user="test@gmail.com",
        password="secretpassword",
        use_tls=True,
        use_ssl=False
    )
    mailer = Mailer(smtp)
    with patch("smtplib.SMTP") as mock_smtp:
        mock_server = MagicMock()
        mock_smtp.return_value = mock_server
        res = mailer.verify_smtp()
        assert res["success"] is True
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("test@gmail.com", "secretpassword")
        mock_server.quit.assert_called_once()


def test_mailer_verify_smtp_ssl():
    smtp = SMTPSettings(
        host="smtp.gmail.com",
        port=465,
        user="test@gmail.com",
        password="secretpassword",
        use_tls=False,
        use_ssl=True
    )
    mailer = Mailer(smtp)
    with patch("smtplib.SMTP_SSL") as mock_smtp_ssl:
        mock_server = MagicMock()
        mock_smtp_ssl.return_value = mock_server
        res = mailer.verify_smtp()
        assert res["success"] is True
        mock_server.login.assert_called_once_with("test@gmail.com", "secretpassword")
        mock_server.quit.assert_called_once()


def test_api_verify_smtp_endpoint():
    from starlette.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    # Test empty host
    resp = client.post("/api/verify-smtp", json={"host": "", "port": 587})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "host is empty" in data["message"].lower()

    # Test mock success
    with patch("smtplib.SMTP") as mock_smtp:
        mock_server = MagicMock()
        mock_smtp.return_value = mock_server
        resp = client.post("/api/verify-smtp", json={
            "host": "smtp.mailgun.org",
            "port": 587,
            "user": "postmaster@mycorp.com",
            "password": "secretpassword",
            "use_tls": True,
            "use_ssl": False
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "successful" in data["message"].lower()

