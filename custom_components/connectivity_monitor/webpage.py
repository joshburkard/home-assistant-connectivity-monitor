"""HTTP content and verified TLS certificate checks for webpage targets."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import logging
import socket
import ssl
from time import monotonic
from typing import Any

import aiohttp
from yarl import URL

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_CERTIFICATE_WARNING_DAYS,
    CONF_EXPECTED_TEXT,
    CONF_URL,
    DEFAULT_CERTIFICATE_WARNING_DAYS,
)

_LOGGER = logging.getLogger(__name__)
_MAX_BODY_BYTES = 2 * 1024 * 1024


def validate_webpage_url(value: str) -> str:
    """Accept absolute HTTP(S) URLs without embedded credentials or fragments."""
    url = URL(value.strip())
    if (
        url.scheme not in ("http", "https")
        or not url.host
        or url.user is not None
        or url.password is not None
        or url.fragment
        or not url.port
    ):
        raise ValueError("Invalid webpage URL")
    if url.raw_path == "/":
        url = url.with_path("/", keep_query=True)
    return str(url)


class WebPageProbe:
    """Check a webpage without storing response bodies or bypassing TLS validation."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the probe."""
        self.hass = hass

    async def _async_certificate_expiry(self, url: URL) -> datetime:
        """Inspect a certificate using a verified TLS handshake with SNI."""
        context = await self.hass.async_add_executor_job(ssl.create_default_context)
        async with asyncio.timeout(10):
            _, writer = await asyncio.open_connection(
                url.host, url.port, ssl=context, server_hostname=url.host
            )
            try:
                ssl_object = writer.get_extra_info("ssl_object")
                certificate = ssl_object.getpeercert()
                return datetime.fromtimestamp(
                    ssl.cert_time_to_seconds(certificate["notAfter"]), UTC
                )
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except ssl.SSLError as err:
                    # Some servers send data during shutdown after a verified handshake.
                    if getattr(err, "reason", None) != "APPLICATION_DATA_AFTER_CLOSE_NOTIFY":
                        raise
                    _LOGGER.debug("Webpage TLS shutdown returned data after close notify")

    async def _async_resolve(self, url: URL) -> list[str]:
        """Resolve the configured hostname using the same system DNS as HTTP."""
        async with asyncio.timeout(5):
            addresses = await asyncio.get_running_loop().getaddrinfo(
                url.host, url.port, type=socket.SOCK_STREAM
            )
        return sorted({address[4][0] for address in addresses})

    async def _async_content_status(
        self, response: aiohttp.ClientResponse, expected_text: str
    ) -> tuple[bool | None, str | None]:
        """Check bounded response content without affecting HTTP or TLS results."""
        try:
            body = bytearray()
            async for chunk in response.content.iter_chunked(65536):
                body.extend(chunk)
                if len(body) > _MAX_BODY_BYTES:
                    _LOGGER.debug("Webpage content exceeds the content-check size limit")
                    return None, "content_too_large"
            return expected_text in body.decode(response.charset or "utf-8"), None
        except (UnicodeError, LookupError) as err:
            _LOGGER.debug("Webpage content decoding failed (%s)", type(err).__name__)
            return None, "content_decode_failed"
        except (aiohttp.ClientError, OSError, TimeoutError) as err:
            _LOGGER.debug("Webpage content reading failed (%s)", type(err).__name__)
            return None, "content_read_failed"

    async def async_update_target(self, target: dict) -> dict[str, Any]:
        """Return individual checks and combined health for one polling cycle."""
        result: dict[str, Any] = {
            "connected": False,
            "dns_resolved": False,
            "resolved_ips": [],
            "dns_error": None,
            "http_available": False,
            "http_status": None,
            "http_error": None,
            "text_found": None,
            "content_error": None,
            "certificate_valid": None,
            "certificate_error": None,
            "certificate_expiring_soon": None,
            "certificate_expires_at": None,
            "certificate_days_remaining": None,
            "latency": None,
            "error": None,
        }
        url = URL(validate_webpage_url(target[CONF_URL]))
        expected_text = target.get(CONF_EXPECTED_TEXT, "")
        https_urls = {url.origin()} if url.scheme == "https" else set()
        try:
            result["resolved_ips"] = await self._async_resolve(url)
            result["dns_resolved"] = bool(result["resolved_ips"])
            if not result["dns_resolved"]:
                result["dns_error"] = "dns_failed"
                _LOGGER.debug("Webpage DNS lookup returned no addresses")
        except (OSError, TimeoutError) as err:
            result["dns_error"] = (
                "dns_timeout" if isinstance(err, TimeoutError) else "dns_failed"
            )
            _LOGGER.debug("Webpage DNS lookup failed (%s)", type(err).__name__)

        started = monotonic()
        try:
            session = async_get_clientsession(self.hass)
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=15),
                max_redirects=10,
            ) as response:
                result["http_status"] = response.status
                result["http_available"] = 200 <= response.status < 300
                https_urls.update(
                    hop.url.origin()
                    for hop in (*response.history, response)
                    if hop.url.scheme == "https"
                )
                if expected_text:
                    result["text_found"], result["content_error"] = (
                        await self._async_content_status(response, expected_text)
                    )
        except (aiohttp.ClientSSLError, ssl.SSLError):
            result["http_error"] = "http_tls_failed"
            _LOGGER.debug("Webpage HTTP TLS connection failed")
        except (aiohttp.ClientError, OSError, TimeoutError, ValueError) as err:
            result["http_error"] = (
                "timeout" if isinstance(err, TimeoutError) else "request_failed"
            )
            _LOGGER.debug("Webpage HTTP request failed (%s)", type(err).__name__)
        result["latency"] = round((monotonic() - started) * 1000, 2)

        # Certificate checks remain independent of HTTP status and content failures.
        if https_urls:
            checks = await asyncio.gather(
                *(self._async_certificate_expiry(hop) for hop in https_urls),
                return_exceptions=True,
            )
            expiries: list[datetime] = []
            for check in checks:
                if isinstance(check, ssl.SSLCertVerificationError):
                    result["certificate_valid"] = False
                    result["certificate_error"] = "certificate_invalid"
                    _LOGGER.debug("Webpage certificate verification failed")
                elif isinstance(check, Exception):
                    if result["certificate_error"] is None:
                        result["certificate_error"] = "certificate_check_failed"
                    _LOGGER.debug(
                        "Webpage certificate check failed (%s)", type(check).__name__
                    )
                elif isinstance(check, datetime):
                    expiries.append(check)
                else:
                    raise TypeError("Unexpected certificate check result")
            if not result["certificate_error"]:
                expires_at = min(expiries)
                seconds_remaining = (expires_at - datetime.now(UTC)).total_seconds()
                warning_days = target.get(
                    CONF_CERTIFICATE_WARNING_DAYS, DEFAULT_CERTIFICATE_WARNING_DAYS
                )
                result.update(
                    certificate_valid=seconds_remaining > 0,
                    certificate_expiring_soon=seconds_remaining <= warning_days * 86400,
                    certificate_expires_at=expires_at.isoformat(),
                    certificate_days_remaining=round(seconds_remaining / 86400, 2),
                )
        failures = []
        if not result["dns_resolved"]:
            failures.append(result["dns_error"])
        if not result["http_available"]:
            failures.append(result["http_error"] or "http_status")
        if expected_text and result["text_found"] is not True:
            failures.append(result["content_error"] or "text_missing")
        if https_urls:
            if result["certificate_error"]:
                failures.append(result["certificate_error"])
            elif result["certificate_valid"] is not True:
                failures.append("certificate_invalid")
            elif result["certificate_expiring_soon"]:
                failures.append("certificate_expiring")
        result["errors"] = failures
        result["error"] = failures[0] if failures else None
        result["connected"] = not failures
        return result
