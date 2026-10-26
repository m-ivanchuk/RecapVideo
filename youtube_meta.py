"""
Модуль для извлечения метаданных видео YouTube:
- Название видео
- Название канала и ссылка на канал
- Количество просмотров
- Превью (thumbnail)
Без необходимости в сторонних API-ключах.
"""

import json
import re
import urllib.request
from typing import Any, Dict, Optional


def format_views(views: Optional[int]) -> str:
    """Форматирует число просмотров в читаемый вид (например: '21 100')."""
    if views is None:
        return "Не определено"
    return f"{views:,}".replace(",", " ")


def fetch_youtube_metadata(url: str) -> Dict[str, Any]:
    """
    Извлекает название, автора/канал, ссылку на канал и количество просмотров.
    """
    meta: Dict[str, Any] = {
        "title": "YouTube Video",
        "channel_name": "Неизвестный канал",
        "channel_url": "",
        "views": None,
        "views_formatted": "—",
        "thumbnail_url": ""
    }

    clean_url = url.strip()

    # 1. Запрос oEmbed для получения названия, канала и ссылки на автора
    oe_url = f"https://www.youtube.com/oembed?url={clean_url}&format=json"
    try:
        req = urllib.request.Request(
            oe_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            meta["title"] = data.get("title", meta["title"])
            meta["channel_name"] = data.get("author_name", meta["channel_name"])
            meta["channel_url"] = data.get("author_url", "")
            meta["thumbnail_url"] = data.get("thumbnail_url", "")
    except Exception:
        pass

    # 2. Запрос HTML страницы для извлечения счетчика просмотров
    try:
        req_page = urllib.request.Request(
            clean_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9"
            }
        )
        with urllib.request.urlopen(req_page, timeout=4) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
            vm = re.search(r'\"viewCount\":\s*\"(\d+)\"', html)
            if vm:
                v_num = int(vm.group(1))
                meta["views"] = v_num
                meta["views_formatted"] = format_views(v_num)
    except Exception:
        pass

    return meta
