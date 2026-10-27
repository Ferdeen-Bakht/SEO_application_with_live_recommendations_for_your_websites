"""Client for the local ASP.NET Core demonstration site."""
import httpx
from seo_lab.config import DOTNET_BASE_URL, DOTNET_API_KEY


def get_pages(base_url: str = DOTNET_BASE_URL) -> list[dict]:
    with httpx.Client(timeout=10) as client:
        r = client.get(f"{base_url.rstrip('/')}/api/pages")
        r.raise_for_status()
        return r.json()


def get_page(slug: str, base_url: str = DOTNET_BASE_URL) -> dict:
    with httpx.Client(timeout=10) as client:
        r = client.get(f"{base_url.rstrip('/')}/api/pages/{slug}")
        r.raise_for_status()
        return r.json()


def publish_page_seo(slug: str, payload: dict, base_url: str = DOTNET_BASE_URL) -> dict:
    headers = {"X-SEO-API-Key": DOTNET_API_KEY}
    with httpx.Client(timeout=15) as client:
        r = client.patch(
            f"{base_url.rstrip('/')}/api/pages/{slug}/seo",
            json=payload,
            headers=headers,
        )
        r.raise_for_status()
        return r.json()
