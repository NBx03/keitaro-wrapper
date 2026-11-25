import logging
import time
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class KeitaroError(Exception):
    """Base error for Keitaro Admin API interactions."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class KeitaroNotFoundError(KeitaroError):
    """Raised when a requested resource is not found in Keitaro (404)."""


class KeitaroBadRequestError(KeitaroError):
    """Raised when Keitaro rejects the request payload or parameters (400/422)."""


class KeitaroClient:
    """Synchronous HTTP client for the Keitaro Admin API."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        admin_url: str | None = None,
        user_agent: str = "keitaro-wrapper/0.1",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        resolved_base = (base_url if base_url is not None else settings.KEITARO_BASE_URL).strip()
        resolved_key = (api_key if api_key is not None else settings.KEITARO_API_KEY).strip()
        resolved_admin = (
            admin_url if admin_url is not None else settings.KEITARO_ADMIN_URL
        ).strip()

        if not resolved_base:
            raise KeitaroError("KEITARO_BASE_URL is not configured")
        if not resolved_key:
            raise KeitaroError("KEITARO_API_KEY is not configured")

        self.base_url = resolved_base.rstrip("/")
        if resolved_admin:
            self.admin_url = resolved_admin.rstrip("/")
        elif self.base_url.endswith("/admin_api/v1"):
            self.admin_url = self.base_url.removesuffix("/admin_api/v1") + "/admin"
        else:
            self.admin_url = self.base_url

        self._client = httpx.Client(
            base_url=self.base_url,
            headers={
                "Api-Key": resolved_key,
                "Accept": "application/json",
                "User-Agent": user_agent,
            },
            timeout=httpx.Timeout(30.0, connect=15.0),
            transport=transport or httpx.HTTPTransport(retries=4),
        )

    def __enter__(self) -> "KeitaroClient":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying httpx client."""
        self._client.close()

    def build_admin_campaign_url(self, keitaro_id: int) -> str:
        """Build the direct Keitaro admin UI URL for a campaign."""
        return f"{self.admin_url}/#!/campaign.editor/{keitaro_id}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        start = time.monotonic()
        try:
            response = self._client.request(method, path, params=params, json=json_body)
        except httpx.HTTPError as exc:
            elapsed_ms = (time.monotonic() - start) * 1000
            logger.warning(
                "Keitaro %s %s failed after %.1fms: %s",
                method,
                path,
                elapsed_ms,
                exc,
            )
            raise KeitaroError(f"Keitaro request failed: {exc}") from exc

        elapsed_ms = (time.monotonic() - start) * 1000
        if response.is_success:
            logger.info(
                "Keitaro %s %s -> %s (%.1fms)",
                method,
                path,
                response.status_code,
                elapsed_ms,
            )
            if not response.content:
                return None
            return response.json()

        detail = self._extract_error_detail(response)
        logger.warning(
            "Keitaro %s %s -> %s (%.1fms): %s",
            method,
            path,
            response.status_code,
            elapsed_ms,
            detail,
        )
        if response.status_code == 404:
            raise KeitaroNotFoundError(detail, status_code=404)
        if response.status_code in (400, 422):
            raise KeitaroBadRequestError(detail, status_code=response.status_code)
        raise KeitaroError(detail, status_code=response.status_code)

    @staticmethod
    def _extract_error_detail(response: httpx.Response) -> str:
        try:
            data = response.json()
        except ValueError:
            text = response.text.strip()
            return text or f"HTTP {response.status_code}"

        if isinstance(data, dict):
            for key in ("message", "detail", "error", "title"):
                val = data.get(key)
                if val:
                    return f"HTTP {response.status_code}: {val}"
        return f"HTTP {response.status_code}: {data}"

    def list_domains(self) -> list[dict[str, Any]]:
        """Fetch all available domains."""
        return list(self._request("GET", "/domains") or [])

    def list_groups(self, group_type: str = "campaigns") -> list[dict[str, Any]]:
        """Fetch campaign groups."""
        return list(self._request("GET", "/groups", params={"type": group_type}) or [])

    def list_traffic_sources(self) -> list[dict[str, Any]]:
        """Fetch all traffic sources."""
        return list(self._request("GET", "/traffic_sources") or [])

    def list_offers(self) -> list[dict[str, Any]]:
        """Fetch the full read-only offer catalog."""
        return list(self._request("GET", "/offers") or [])

    def get_offer(self, offer_id: int) -> dict[str, Any]:
        """Fetch a single offer by ID."""
        return dict(self._request("GET", f"/offers/{offer_id}"))

    def list_campaigns(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """Fetch campaigns from Keitaro."""
        return list(
            self._request("GET", "/campaigns", params={"limit": limit, "offset": offset}) or []
        )

    def get_campaign(self, campaign_id: int) -> dict[str, Any]:
        """Fetch a single campaign by Keitaro ID."""
        return dict(self._request("GET", f"/campaigns/{campaign_id}"))

    def create_campaign(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a new campaign in Keitaro."""
        return dict(self._request("POST", "/campaigns", json_body=payload))

    def list_streams(self, campaign_id: int) -> list[dict[str, Any]]:
        """Fetch all streams for a campaign ordered by position."""
        return list(self._request("GET", f"/campaigns/{campaign_id}/streams") or [])

    def create_stream(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a stream in Keitaro."""
        return dict(self._request("POST", "/streams", json_body=payload))

    def update_stream(self, stream_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        """Update an existing stream in Keitaro."""
        return dict(self._request("PUT", f"/streams/{stream_id}", json_body=payload))
