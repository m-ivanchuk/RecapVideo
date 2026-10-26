"""
Модуль взаимодействия с Gemini API для агентского анализа видео (Agentic Video Understanding).
"""

import os
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional
from dotenv import load_dotenv

from youtube_meta import fetch_youtube_metadata

# Загружаем переменные окружения из .env файла
load_dotenv()

try:
    from google import genai
except ImportError:
    genai = None


@dataclass
class AnalysisResult:
    """Результат выполнения анализа видео."""
    output_text: str
    model: str
    video_url: str
    video_meta: Optional[Dict[str, Any]] = None
    total_tokens: Optional[int] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    interaction_id: Optional[str] = None


class VideoAnalyzer:
    """
    Класс для выполнения агентского анализа видео геймплея через Gemini Interactions API.
    """

    SUPPORTED_MODELS = [
        "gemini-3.5-flash",
        "gemini-3.8-flash",
        "gemini-3.7-flash",
        "gemini-3.6-flash",
    ]

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-3.8-flash"):
        """
        Инициализация клиента Gemini.
        :param api_key: Ключ Gemini API. Если None, берется из GEMINI_API_KEY.
        :param model: Имя модели (по умолчанию gemini-3.8-flash).
        """
        if genai is None:
            raise ImportError(
                "Пакет 'google-genai' не установлен. Установите его: pip install google-genai"
            )

        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Не найден ключ GEMINI_API_KEY. Укажите его в файле .env или передайте в конструктор."
            )

        self.model = model
        self.client = genai.Client(api_key=self.api_key)

    @staticmethod
    def extract_youtube_video_id(url: str) -> Optional[str]:
        """
        Извлекает ID видео из различных форматов ссылок YouTube:
        - https://www.youtube.com/watch?v=VIDEO_ID
        - https://youtu.be/VIDEO_ID
        - https://www.youtube.com/shorts/VIDEO_ID
        - https://m.youtube.com/watch?v=VIDEO_ID
        """
        patterns = [
            r"(?:v=|\/)([0-9A-Za-z_-]{11}).*",
            r"youtu\.be\/([0-9A-Za-z_-]{11})",
            r"youtube\.com\/shorts\/([0-9A-Za-z_-]{11})"
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    @staticmethod
    def normalize_youtube_url(url: str) -> str:
        """
        Приводит ссылку к каноническому виду https://www.youtube.com/watch?v=VIDEO_ID
        """
        video_id = VideoAnalyzer.extract_youtube_video_id(url)
        if video_id:
            return f"https://www.youtube.com/watch?v={video_id}"
        return url.strip()

    @staticmethod
    def timestamp_to_seconds(ts: str) -> int:
        """Конвертирует строку таймкода 'MM:SS' или 'HH:MM:SS' в секунды."""
        parts = [int(p) for p in ts.split(":")]
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        elif len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        return 0

    @staticmethod
    def enrich_markdown_with_clickable_timestamps(markdown_text: str, youtube_url: str) -> str:
        """
        Заменяет текстовые таймкоды вида [MM:SS] или [HH:MM:SS] на кликабельные ссылки YouTube.
        """
        video_id = VideoAnalyzer.extract_youtube_video_id(youtube_url)
        if not video_id:
            return markdown_text

        def replace_match(match: re.Match) -> str:
            ts_str = match.group(1)
            seconds = VideoAnalyzer.timestamp_to_seconds(ts_str)
            link = f"https://www.youtube.com/watch?v={video_id}&t={seconds}s"
            return f"[[{ts_str}]]({link})"

        # Ищем таймкоды вроде [04:15] или [01:23:45], исключая уже существующие markdown ссылки
        pattern = r"(?<!\]\()\[(\d{1,2}:\d{2}(?::\d{2})?)\](?!\()"
        return re.sub(pattern, replace_match, markdown_text)

    def analyze(self, video_url: str, prompt: str) -> AnalysisResult:
        """
        Запуск агентского анализа видео.
        :param video_url: Ссылка на видео (YouTube).
        :param prompt: Текст промпта с инструкциями и критериями.
        :return: AnalysisResult с текстом отчета и метаданными.
        """
        clean_url = self.normalize_youtube_url(video_url)
        video_metadata = fetch_youtube_metadata(clean_url)

        try:
            # Вызов Interactions API с Agentic Video Understanding
            interaction = self.client.interactions.create(
                model=self.model,
                input=[
                    {
                        "type": "video",
                        "uri": clean_url,
                        "processing": "agentic"  # Включает агентскую динамическую навигацию по видео
                    },
                    {
                        "type": "text",
                        "text": prompt
                    }
                ]
            )

            # Извлекаем текст ответа
            output_text = getattr(interaction, "output_text", None)
            if not output_text and hasattr(interaction, "outputs") and interaction.outputs:
                # Fallback если output_text не заполнен
                output_text = "".join([o.text for o in interaction.outputs if hasattr(o, "text") and o.text])

            if not output_text:
                output_text = "Не удалось извлечь текстовый ответ из модели."

            # Обогащаем таймкоды кликабельными ссылками на YouTube
            enriched_text = self.enrich_markdown_with_clickable_timestamps(output_text, clean_url)

            # Сбор статистики использования токенов
            usage = getattr(interaction, "usage", None)
            total_tokens = getattr(usage, "total_tokens", None) if usage else None
            input_tokens = getattr(usage, "input_tokens", None) if usage else None
            output_tokens = getattr(usage, "output_tokens", None) if usage else None

            return AnalysisResult(
                output_text=enriched_text,
                model=self.model,
                video_url=clean_url,
                video_meta=video_metadata,
                total_tokens=total_tokens,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                interaction_id=getattr(interaction, "id", None)
            )

        except Exception as e:
            err_msg = str(e)
            if "API_KEY" in err_msg.upper() or "API key not valid" in err_msg:
                raise RuntimeError("🔑 Ошибка авторизации: неверный API-ключ Gemini.") from e
            elif "429" in err_msg or "too_many_requests" in err_msg.lower() or "quota" in err_msg.lower():
                raise RuntimeError(
                    "⚠️ Превышена квота запросов (429 Rate Limit / Quota Exceeded).\n\n"
                    "Причина: аккаунт сейчас работает на бесплатном тарифе (Free Tier) в Google AI Studio, "
                    "где установлены жесткие лимиты на тяжелые видео-запросы.\n\n"
                    "Как исправить:\n"
                    "1. В Google AI Studio (aistudio.google.com) в левом нижнем углу нажмите 'Set up billing' "
                    "и привяжите платежный аккаунт (Pay-as-you-go). Анализ видео с Agentic Understanding стоит копейки (доли цента).\n"
                    "2. Либо подождите 1–2 минуты, пока сбросится минутная квота (RPM/TPM)."
                ) from e
            elif "503" in err_msg or "high demand" in err_msg.lower() or "unavailable" in err_msg.lower():
                raise RuntimeError(
                    "⏳ Модель сейчас испытывает пиковую нагрузку (503 Service Unavailable).\n\n"
                    "На бесплатном тарифе запросы имеют низкий приоритет при нагрузке на серверы Google. "
                    "Попробуйте выбрать модель 'gemini-3.5-flash' в настройках или привязать биллинг в Google AI Studio."
                ) from e
            elif "404" in err_msg or "not found" in err_msg.lower():
                raise RuntimeError(f"❌ Видео по ссылке '{video_url}' не найдено или является приватным.") from e
            else:
                raise RuntimeError(f"❌ Ошибка при анализе видео через Gemini API: {err_msg}") from e
