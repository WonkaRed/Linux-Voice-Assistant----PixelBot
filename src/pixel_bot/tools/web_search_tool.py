"""
Web Search Tool - DuckDuckGo search for privacy.

Capabilities:
- Search the web for information
- Get instant answers
- Privacy-friendly (no tracking)
"""
import logging
from typing import Dict, Any

from .base_tool import BaseTool

logger = logging.getLogger(__name__)


class WebSearchTool(BaseTool):
    """Web search using DuckDuckGo."""

    def _get_name(self) -> str:
        return "web_search"

    def _get_description(self) -> str:
        return """Search the web using DuckDuckGo.
Use this when the user asks for information you don't know, like chain IDs, current prices, recent events, etc.
Returns top search results with titles and snippets."""

    def _get_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query"
                },
                "num_results": {
                    "type": "integer",
                    "description": "Number of results to return (default 3, max 5)"
                }
            },
            "required": ["query"]
        }

    def execute(self, **kwargs) -> str:
        """
        Execute web search.

        Args:
            query: Search query
            num_results: Number of results (default 3)

        Returns:
            str: Formatted search results
        """
        try:
            query = kwargs.get("query")
            num_results = kwargs.get("num_results", 3)

            if not query:
                return "No search query provided"

            # Limit results
            num_results = min(num_results, 5)

            logger.info(f"Web search: '{query}' (limit: {num_results})")

            # Try ddgs library (new version)
            try:
                from ddgs import DDGS

                with DDGS() as ddg:
                    results = list(ddg.text(query, max_results=num_results))

                if not results:
                    return f"No results found for '{query}'"

                # Format results
                output = f"Search results for '{query}':\n\n"

                for i, result in enumerate(results, 1):
                    title = result.get('title', 'No title')
                    snippet = result.get('body', 'No description')
                    link = result.get('href', '')

                    output += f"{i}. {title}\n"
                    output += f"   {snippet}\n"
                    if link:
                        output += f"   {link}\n"
                    output += "\n"

                return output.strip()

            except ImportError:
                logger.warning("duckduckgo_search not installed, using fallback")
                return self._fallback_search(query)

        except Exception as e:
            logger.error(f"Web search failed: {e}", exc_info=True)
            return f"Web search failed: {e}"

    def _fallback_search(self, query: str) -> str:
        """
        Fallback search using requests + BeautifulSoup.

        Args:
            query: Search query

        Returns:
            str: Search results
        """
        try:
            import requests
            from bs4 import BeautifulSoup
            import urllib.parse

            # DuckDuckGo HTML search
            url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"

            headers = {
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
            }

            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            results = []
            for result in soup.find_all('div', class_='result')[:3]:
                title_elem = result.find('a', class_='result__a')
                snippet_elem = result.find('a', class_='result__snippet')

                if title_elem:
                    title = title_elem.get_text(strip=True)
                    link = title_elem.get('href', '')
                    snippet = snippet_elem.get_text(strip=True) if snippet_elem else ''

                    results.append({
                        'title': title,
                        'snippet': snippet,
                        'link': link
                    })

            if not results:
                return f"No results found for '{query}'"

            # Format results
            output = f"Search results for '{query}':\n\n"

            for i, result in enumerate(results, 1):
                output += f"{i}. {result['title']}\n"
                if result['snippet']:
                    output += f"   {result['snippet']}\n"
                output += "\n"

            return output.strip()

        except Exception as e:
            logger.error(f"Fallback search failed: {e}")
            return f"Web search unavailable. Please install 'duckduckgo-search' package."
