"""Focused tests for HTTP content checks and certificate health."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
import socket
import ssl
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
from aiohttp import web
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from freezegun import freeze_time
import pytest
from yarl import URL

from custom_components.connectivity_monitor.const import (
    CONF_CERTIFICATE_WARNING_DAYS,
    CONF_EXPECTED_TEXT,
    CONF_URL,
)
from custom_components.connectivity_monitor.webpage import (
    WebPageProbe,
    validate_webpage_url,
)


@pytest.fixture(autouse=True)
def mock_webpage_dns(request):
    """Keep unit checks offline; local-server tests exercise real resolution."""
    if request.node.name.startswith("test_real_"):
        yield
        return
    with patch(
        "custom_components.connectivity_monitor.webpage.WebPageProbe._async_resolve",
        AsyncMock(return_value=["192.0.2.1"]),
    ):
        yield


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com",
        "example.com",
        "https://",
        "https://user:password@example.com",
        "https://example.com:bad",
        "https://example.com#fragment",
    ],
)
def test_reject_invalid_urls(url: str) -> None:
    """Reject malformed URLs and embedded authentication."""
    with pytest.raises(ValueError):
        validate_webpage_url(url)


def test_normalize_equivalent_root_urls() -> None:
    """Treat an omitted root slash as the same target without losing its query."""
    assert validate_webpage_url("https://example.com?check=1") == (
        "https://example.com/?check=1"
    )
    assert validate_webpage_url(" https://EXAMPLE.com/ ") == "https://example.com/"


def _response(
    url: str = "http://example.com",
    status: int = 200,
    body: bytes = b"Service ready",
    history: tuple = (),
) -> MagicMock:
    response = MagicMock()
    response.url = URL(url)
    response.history = history
    response.status = status
    response.charset = "utf-8"
    response.content.iter_chunked.return_value.__aiter__.return_value = [body]
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=False)
    return response


@pytest.mark.parametrize(
    ("status", "text", "healthy", "found", "error"),
    [
        (200, "", True, None, None),
        (200, "ready", True, True, None),
        (200, "Ready", False, False, "text_missing"),
        (204, "", True, None, None),
        (404, "", False, None, "http_status"),
        (401, "", False, None, "http_status"),
        (500, "ready", False, True, "http_status"),
    ],
)
async def test_http_and_text_health(
    status: int, text: str, healthy: bool, found: bool | None, error: str | None
) -> None:
    """Combine status and optional case-sensitive text checks."""
    session = MagicMock()
    session.get.return_value = _response(status=status)
    probe = WebPageProbe(MagicMock())
    with patch(
        "custom_components.connectivity_monitor.webpage.async_get_clientsession",
        return_value=session,
    ):
        result = await probe.async_update_target(
            {CONF_URL: "http://example.com", CONF_EXPECTED_TEXT: text}
        )
    assert result["connected"] is healthy
    assert result["http_available"] is (200 <= status < 300)
    assert result["text_found"] is found
    assert result["certificate_valid"] is None
    assert result["error"] == error


@pytest.mark.parametrize(
    ("seconds", "warning_days", "healthy", "valid", "soon"),
    [
        (31 * 86400, 30, True, True, False),
        (30 * 86400, 30, False, True, True),
        (30 * 86400 + 1, 30, True, True, False),
        (1, 0, True, True, False),
        (0, 0, False, False, True),
        (-86400, 30, False, False, True),
    ],
)
async def test_certificate_threshold(
    seconds: int, warning_days: int, healthy: bool, valid: bool, soon: bool
) -> None:
    """Compare exact expiry timestamps, not rounded days, at the threshold."""
    now = datetime(2026, 11, 13, tzinfo=UTC)
    session = MagicMock()
    session.get.return_value = _response("https://example.com")
    probe = WebPageProbe(MagicMock())
    with (
        patch(
            "custom_components.connectivity_monitor.webpage.async_get_clientsession",
            return_value=session,
        ),
        patch.object(
            probe, "_async_certificate_expiry",
            AsyncMock(return_value=now + timedelta(seconds=seconds)),
        ),
        freeze_time(now),
    ):
        result = await probe.async_update_target({
            CONF_URL: "https://example.com",
            CONF_CERTIFICATE_WARNING_DAYS: warning_days,
        })
    assert result["connected"] is healthy
    assert result["certificate_valid"] is valid
    assert result["certificate_expiring_soon"] is soon
    assert result["certificate_days_remaining"] == round(seconds / 86400, 2)


async def test_redirect_checks_earliest_https_certificate() -> None:
    """An expiring HTTPS redirect cannot be hidden by its healthy destination."""
    session = MagicMock()
    session.get.return_value = _response(
        "https://destination.example.com",
        history=(_response("https://example.com"),),
    )
    now = datetime.now(UTC)

    async def expiry(url: URL) -> datetime:
        return now + timedelta(days=5 if url.host == "example.com" else 90)

    probe = WebPageProbe(MagicMock())
    with (
        patch(
            "custom_components.connectivity_monitor.webpage.async_get_clientsession",
            return_value=session,
        ),
        patch.object(probe, "_async_certificate_expiry", side_effect=expiry) as check,
    ):
        result = await probe.async_update_target({CONF_URL: "https://example.com"})
    assert result["http_available"] is True
    assert result["connected"] is False
    assert result["certificate_expiring_soon"] is True
    assert check.await_count == 2


@pytest.mark.parametrize(
    ("exception", "error", "certificate_valid"),
    [
        (TimeoutError(), "timeout", None),
        (aiohttp.ClientConnectionError(), "request_failed", None),
        (ssl.SSLCertVerificationError(), "http_tls_failed", False),
    ],
)
async def test_request_failures_are_explicit(
    exception: Exception, error: str, certificate_valid: bool | None
) -> None:
    """Requests and TLS failures produce unhealthy states with a reason."""
    session = MagicMock()
    session.get.side_effect = exception
    probe = WebPageProbe(MagicMock())
    with (
        patch(
            "custom_components.connectivity_monitor.webpage.async_get_clientsession",
            return_value=session,
        ),
        patch.object(
            probe, "_async_certificate_expiry", AsyncMock(side_effect=exception)
        ),
    ):
        result = await probe.async_update_target(
            {CONF_URL: "https://example.com"}
        )
    assert result["connected"] is False
    assert result["error"] == error
    assert result["certificate_valid"] is certificate_valid


async def test_dns_failure_does_not_hide_http_success() -> None:
    """An independent DNS failure does not overwrite the HTTP check result."""
    session = MagicMock()
    session.get.return_value = _response()
    probe = WebPageProbe(MagicMock())
    with (
        patch(
            "custom_components.connectivity_monitor.webpage.async_get_clientsession",
            return_value=session,
        ),
        patch.object(
            probe, "_async_resolve", AsyncMock(side_effect=socket.gaierror())
        ),
    ):
        result = await probe.async_update_target({CONF_URL: "http://example.com"})
    assert result["dns_resolved"] is False
    assert result["http_available"] is True
    assert result["connected"] is False
    assert result["error"] == "dns_failed"


async def test_content_failure_does_not_skip_certificate_check() -> None:
    """Unhealthy HTTP and missing text still expose a healthy certificate."""
    session = MagicMock()
    session.get.return_value = _response("https://example.com", status=500)
    probe = WebPageProbe(MagicMock())
    with (
        patch(
            "custom_components.connectivity_monitor.webpage.async_get_clientsession",
            return_value=session,
        ),
        patch.object(
            probe, "_async_certificate_expiry",
            AsyncMock(return_value=datetime.now(UTC) + timedelta(days=90)),
        ),
    ):
        result = await probe.async_update_target({
            CONF_URL: "https://example.com", CONF_EXPECTED_TEXT: "missing text",
        })
    assert result["connected"] is False
    assert result["text_found"] is False
    assert result["certificate_valid"] is True
    assert result["errors"] == ["http_status", "text_missing"]


async def test_oversized_content_fails_check() -> None:
    """Content exceeding the bound is not mistaken for a successful text check."""
    session = MagicMock()
    session.get.return_value = _response(body=b"x" * (2 * 1024 * 1024 + 1))
    with patch(
        "custom_components.connectivity_monitor.webpage.async_get_clientsession",
        return_value=session,
    ):
        result = await WebPageProbe(MagicMock()).async_update_target({
            CONF_URL: "http://example.com",
            CONF_EXPECTED_TEXT: "x",
        })
    assert result["connected"] is False
    assert result["error"] == "content_too_large"


@pytest.mark.parametrize(
    "shutdown_reason", [None, "APPLICATION_DATA_AFTER_CLOSE_NOTIFY", "BAD_RECORD_MAC"]
)
async def test_verified_tls_connection_is_closed(shutdown_reason: str | None) -> None:
    """Use SNI and a verification context, and close the inspection connection."""
    writer = MagicMock()
    writer.get_extra_info.return_value.getpeercert.return_value = {
        "notAfter": "Dec 31 23:59:59 2026 GMT",
    }
    writer.wait_closed = AsyncMock()
    if shutdown_reason:
        shutdown_error = ssl.SSLError(ssl.SSL_ERROR_SSL, "TLS shutdown failed")
        shutdown_error.reason = shutdown_reason
        writer.wait_closed.side_effect = shutdown_error
    context = ssl.create_default_context()
    hass = MagicMock()
    hass.async_add_executor_job = AsyncMock(return_value=context)
    with patch(
        "custom_components.connectivity_monitor.webpage.asyncio.open_connection",
        AsyncMock(return_value=(MagicMock(), writer)),
    ) as connect:
        if shutdown_reason == "BAD_RECORD_MAC":
            with pytest.raises(ssl.SSLError):
                await WebPageProbe(hass)._async_certificate_expiry(
                    URL("https://example.com:8443")
                )
            return
        expiry = await WebPageProbe(hass)._async_certificate_expiry(URL(
            "https://example.com:8443"
        ))
    assert expiry == datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC)
    connect.assert_awaited_once_with(
        "example.com", 8443, ssl=context, server_hostname="example.com"
    )
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname
    writer.close.assert_called_once()
    writer.wait_closed.assert_awaited_once()


@pytest.mark.parametrize("expired", [False, True])
@pytest.mark.usefixtures("socket_enabled")
async def test_real_https_page_and_certificate(tmp_path, expired: bool) -> None:
    """Exercise HTTP and verified certificate inspection against a local TLS server."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.now(UTC)
    expiry = now + timedelta(days=-1 if expired else 90)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=2))
        .not_valid_after(expiry)
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ip_address("127.0.0.1"))]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    cert_path = tmp_path / "certificate.pem"
    key_path = tmp_path / "key.pem"
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ))
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(cert_path, key_path)
    client_context = ssl.create_default_context(cafile=str(cert_path))
    app = web.Application()

    async def status(_request: web.Request) -> web.Response:
        return web.Response(text="Service ready")

    app.router.add_get("/status", status)
    runner = web.AppRunner(app)
    await runner.setup()
    loop = asyncio.get_running_loop()
    original_handler = loop.get_exception_handler()
    expected_handshake_resets: list[Exception] = []

    def handle_server_error(loop, context):
        error = context.get("exception")
        if (
            expired
            and context.get("message") == "Error on transport creation for incoming connection"
            and isinstance(error, ConnectionResetError)
        ):
            expected_handshake_resets.append(error)
        elif original_handler:
            original_handler(loop, context)
        else:
            loop.default_exception_handler(context)

    loop.set_exception_handler(handle_server_error)
    try:
        site = web.TCPSite(runner, "127.0.0.1", 0, ssl_context=server_context)
        await site.start()
        port = runner.addresses[0][1]
        hass = MagicMock()
        hass.async_add_executor_job = AsyncMock(return_value=client_context)
        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=client_context)
        ) as session:
            with patch(
                "custom_components.connectivity_monitor.webpage.async_get_clientsession",
                return_value=session,
            ):
                result = await WebPageProbe(hass).async_update_target({
                    CONF_URL: f"https://127.0.0.1:{port}/status",
                    CONF_EXPECTED_TEXT: "ready",
                })
        assert result["connected"] is not expired
        assert result["certificate_valid"] is not expired
        if expired:
            assert result["certificate_error"] == "certificate_invalid"
        else:
            assert result["http_status"] == 200
            assert result["text_found"] is True
            assert result["certificate_days_remaining"] == pytest.approx(90, abs=0.01)
    finally:
        await runner.cleanup()
        loop.set_exception_handler(original_handler)
