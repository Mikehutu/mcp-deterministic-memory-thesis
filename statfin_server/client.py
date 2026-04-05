import httpx
from typing import Any, Dict, List
from urllib.parse import urljoin
import structlog

logger = structlog.get_logger(__name__)

class StatFinClient:
    """Generic client for Statistics Finland PxWeb API."""
    
    BASE_URL = "https://pxdata.stat.fi/PXWeb/api/v1/en/StatFin/"

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    async def list_items(self, path: str = "") -> List[Dict[str, Any]]:
        """List tables and folders at a given path."""
        url = urljoin(self.BASE_URL, path)
        try:
            response = await self.client.get(url)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error("Failed to list items", path=path, error=str(e))
            raise

    async def get_table_metadata(self, table_path: str) -> Dict[str, Any]:
        """Get metadata for a specific table."""
        url = urljoin(self.BASE_URL, table_path)
        try:
            response = await self.client.get(url)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error("Failed to get metadata", table=table_path, error=str(e))
            raise

    async def fetch_data(self, table_path: str, query: Dict[str, Any]) -> Dict[str, Any]:
        """
        Fetch data from a table using a JSON query.
        Returns the raw JSON-stat2 response.
        """
        url = urljoin(self.BASE_URL, table_path)
        try:
            if "response" not in query:
                query["response"] = {"format": "json-stat2"}
            
            response = await self.client.post(url, json=query)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error("Failed to fetch data", table=table_path, error=str(e))
            raise
