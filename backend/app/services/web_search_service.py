import html
import logging
import os
import re
from urllib.parse import quote_plus
from xml.etree import ElementTree as ET

import httpx

logger = logging.getLogger(__name__)
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")


def _clean(value: str) -> str:
    value = html.unescape(value or "")
    return re.sub(r"<[^>]+>", "", value).strip()


def _rss_items(content: bytes, limit: int):
    root = ET.fromstring(content)
    items = []
    for item in root.findall(".//item")[:limit]:
        title = _clean(item.findtext("title"))
        link = _clean(item.findtext("link"))
        snippet = _clean(item.findtext("description"))
        published = _clean(item.findtext("pubDate"))
        if title and link:
            items.append({"title": title, "url": link, "snippet": snippet[:500], "published_at": published})
    return items


async def _tavily_search(query: str, limit: int = 6):
    if not TAVILY_API_KEY:
        return []
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.post(
                "https://api.tavily.com/search",
                headers={"Authorization": f"Bearer {TAVILY_API_KEY}", "Content-Type": "application/json"},
                json={"query": query, "max_results": limit, "search_depth": "basic", "include_answer": False},
            )
            response.raise_for_status()
            data = response.json()
        return [{
            "title": x.get("title", ""),
            "url": x.get("url", ""),
            "snippet": x.get("content", "")[:1000],
            "published_at": x.get("published_date", ""),
        } for x in data.get("results", []) if x.get("title") and x.get("url")]
    except Exception as exc:
        logger.warning("Tavily search failed: %s", exc)
        return []


async def _get(client, url: str):
    response = await client.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; QingpuSearch/1.0)"})
    response.raise_for_status()
    return response


async def search_web(query: str, limit: int = 6):
    """Tavily 主搜索源；公共 RSS 仅作为未配置 Key 时的备用。"""
    if TAVILY_API_KEY:
        return await _tavily_search(query, limit)

    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        google_url = "https://news.google.com/rss/search?q=" + quote_plus(query) + "&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
        try:
            response = await _get(client, google_url)
            results = _rss_items(response.content, limit)
            if results:
                return results
        except Exception as exc:
            logger.warning("Google News search failed: %s", exc)

        bing_url = f"https://www.bing.com/news/search?q={quote_plus(query)}&format=rss&setlang=zh-Hans"
        try:
            response = await _get(client, bing_url)
            if "xml" in response.headers.get("content-type", "") or response.content.lstrip().startswith(b"<?xml"):
                return _rss_items(response.content, limit)
        except Exception as exc:
            logger.warning("Bing search failed: %s", exc)
    return []
