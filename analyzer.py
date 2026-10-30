"""
Модуль взаимодействия с Gemini API для агентского анализа видео (Agentic Video Understanding).
Поддерживает три источника видео:
1. YouTube (прямой стриминг по ссылке)
2. Локальные видеофайлы (MP4, MOV, MKV, WebM, AVI через Gemini File API)
3. Google Drive (автоматическое скачивание и загрузка через Gemini File API)
"""

import mimetypes
import os
from pathlib import Path
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional
from dotenv import load_dotenv

from drive_downloader import GoogleDriveDownloader
from youtube_meta import fetch_youtube_metadata

# Загружаем переменные окружения из .env файла
load_dotenv()

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None


@dataclass
class AnalysisResult:
    """Результат выполнения анализа видео."""

    output_text: str
    model: str
    video_url: str
    source_type: str = "youtube"  # 'youtube' | 'local' | 'gdrive'
    video_meta: Optional[Dict[str, Any]] = None
    total_tokens: Optional[int] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    interaction_id: Optional[str] = None


class VideoAnalyzer:
    """
    Класс для выполнения агентского анализа видео через Gemini Interactions API и File API.
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
        if not url:
            return None
        patterns = [
            r"(?:v=|\/)([0-9A-Za-z_-]{11}).*",
            r"youtu\.be\/([0-9A-Za-z_-]{11})",
            r"youtube\.com\/shorts\/([0-9A-Za-z_-]{11})",
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    @staticmethod
    def normalize_youtube_url(url: str) -> str:
        """Приводит ссылку к каноническому виду https://www.youtube.com/watch?v=VIDEO_ID."""
        video_id = VideoAnalyzer.extract_youtube_video_id(url)
        if video_id:
            return f"https://www.youtube.com/watch?v={video_id}"
        return url.strip()

    @staticmethod
    def detect_source_type(video_source: str) -> str:
        """Определяет тип источника видео: 'youtube', 'gdrive' или 'local'."""
        clean = video_source.strip()
        if GoogleDriveDownloader.is_gdrive_url(clean):
            return "gdrive"
        if VideoAnalyzer.extract_youtube_video_id(clean) or "youtube.com" in clean or "youtu.be" in clean:
            return "youtube"
        return "local"

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
        """Заменяет текстовые таймкоды вида [MM:SS] на кликабельные ссылки YouTube."""
        video_id = VideoAnalyzer.extract_youtube_video_id(youtube_url)
        if not video_id:
            return markdown_text

        def replace_match(match: re.Match) -> str:
            ts_str = match.group(1)
            seconds = VideoAnalyzer.timestamp_to_seconds(ts_str)
            link = f"https://www.youtube.com/watch?v={video_id}&t={seconds}s"
            return f"[[{ts_str}]]({link})"

        pattern = r"(?<!\]\()\[(\d{1,2}:\d{2}(?::\d{2})?)\](?!\()"
        return re.sub(pattern, replace_match, markdown_text)

    def upload_to_gemini_file_api(
        self,
        file_path: Path,
        display_name: Optional[str] = None,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> Any:
        """
        Загружает локальный видеофайл на серверы Google через Gemini File API
        и ожидает завершения препроцессинга (перехода в статус ACTIVE).
        """
        if not file_path.exists():
            raise FileNotFoundError(f"Файл '{file_path}' не найден на диске.")

        size_mb = file_path.stat().st_size / (1024 * 1024)
        if progress_callback:
            progress_callback(
                f"📤 Загрузка файла '{file_path.name}' ({size_mb:.1f} MB) в Gemini File API..."
            )

        # Определение MIME-типа
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if not mime_type or not mime_type.startswith("video/"):
            ext = file_path.suffix.lower()
            mime_map = {
                ".mp4": "video/mp4",
                ".mov": "video/quicktime",
                ".mkv": "video/x-matroska",
                ".webm": "video/webm",
                ".avi": "video/x-msvideo",
            }
            mime_type = mime_map.get(ext, "video/mp4")

        # Загрузка через File API
        upload_config = types.UploadFileConfig(
            display_name=display_name or file_path.name,
            mime_type=mime_type,
        )
        file_ref = self.client.files.upload(file=str(file_path), config=upload_config)

        if progress_callback:
            progress_callback("⏳ Серверы Google выполняют препроцессинг видео (Agentic Video Indexing)...")

        # Ожидание готовности файла (статус ACTIVE)
        poll_interval = 3
        max_wait_seconds = 600  # 10 минут максимум
        elapsed = 0

        while file_ref.state.name == "PROCESSING":
            time.sleep(poll_interval)
            elapsed += poll_interval
            file_ref = self.client.files.get(name=file_ref.name)
            if progress_callback and elapsed % 6 == 0:
                progress_callback(f"⏳ Препроцессинг видео продолжается ({elapsed} сек)...")
            if elapsed > max_wait_seconds:
                raise TimeoutError("Время ожидания препроцессинга видео в Gemini превышено (10 минут).")

        if file_ref.state.name != "ACTIVE":
            err_details = getattr(file_ref, "error", "")
            raise RuntimeError(
                f"❌ Ошибка обработки видео в Gemini File API: статус '{file_ref.state.name}'. {err_details}"
            )

        if progress_callback:
            progress_callback("✅ Видео готово к анализу!")

        return file_ref

    def analyze(
        self,
        video_source: str,
        prompt: str,
        source_type: Optional[str] = None,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> AnalysisResult:
        """
        Запуск агентского анализа видео (YouTube, Google Drive или локальный файл).
        :param video_source: Ссылка на видео (YouTube / Google Drive) или путь к локальному файлу.
        :param prompt: Текст сформированного промпта со скиллом и правилами.
        :param source_type: Принудительный тип источника ('youtube', 'gdrive', 'local') или None для автодетекта.
        :param progress_callback: Функция уведомления о промежуточном статусе.
        :return: AnalysisResult с текстом отчета и метаданными.
        """
        stype = source_type or self.detect_source_type(video_source)
        video_file_ref = None

        try:
            if stype == "youtube":
                clean_url = self.normalize_youtube_url(video_source)
                video_metadata = fetch_youtube_metadata(clean_url)
                video_uri = clean_url

            elif stype == "gdrive":
                clean_url = video_source.strip()
                if progress_callback:
                    progress_callback("☁️ Подключение к Google Drive и скачивание файла...")

                local_path, filename = GoogleDriveDownloader.download_file(clean_url)
                size_mb = round(local_path.stat().st_size / (1024 * 1024), 1)

                video_metadata = {
                    "title": filename,
                    "channel_name": "Google Drive",
                    "channel_url": clean_url,
                    "views_formatted": f"Файл {size_mb} MB",
                    "local_path": str(local_path),
                }

                video_file_ref = self.upload_to_gemini_file_api(
                    local_path, display_name=filename, progress_callback=progress_callback
                )
                video_uri = video_file_ref.uri

            elif stype == "local":
                local_path = Path(video_source.strip())
                if not local_path.exists():
                    raise FileNotFoundError(f"Локальный файл '{video_source}' не существует.")

                clean_url = str(local_path.resolve())
                size_mb = round(local_path.stat().st_size / (1024 * 1024), 1)

                video_metadata = {
                    "title": local_path.name,
                    "channel_name": "Локальное видео",
                    "channel_url": "",
                    "views_formatted": f"Файл {size_mb} MB",
                    "local_path": clean_url,
                }

                video_file_ref = self.upload_to_gemini_file_api(
                    local_path, display_name=local_path.name, progress_callback=progress_callback
                )
                video_uri = video_file_ref.uri

            else:
                raise ValueError(f"Неизвестный тип источника видео: {stype}")

            if progress_callback:
                progress_callback("🤖 Gemini запускает Agentic Video Understanding...")

            # Вызов Interactions API с Agentic Video Understanding
            try:
                interaction = self.client.interactions.create(
                    model=self.model,
                    input=[
                        {
                            "type": "video",
                            "uri": video_uri,
                            "processing": "agentic",  # Включает агентскую динамическую навигацию по видео
                        },
                        {
                            "type": "text",
                            "text": prompt,
                        },
                    ],
                )

                # Извлекаем текст ответа
                output_text = getattr(interaction, "output_text", None)
                if not output_text and hasattr(interaction, "outputs") and interaction.outputs:
                    output_text = "".join(
                        [o.text for o in interaction.outputs if hasattr(o, "text") and o.text]
                    )
                interaction_id = getattr(interaction, "id", None)
                usage = getattr(interaction, "usage", None)

            except Exception as interaction_err:
                # Если Interactions API отклонил файл из File API, используем надёжный fallback: generate_content
                if video_file_ref:
                    if progress_callback:
                        progress_callback("🤖 Выполнение анализа видео через Gemini Multimodal Engine...")
                    response = self.client.models.generate_content(
                        model=self.model,
                        contents=[video_file_ref, prompt],
                    )
                    output_text = response.text or ""
                    interaction_id = None
                    usage = getattr(response, "usage_metadata", None)
                else:
                    raise interaction_err

            if not output_text:
                output_text = "Не удалось извлечь текстовый ответ из модели."

            # Обогащаем таймкоды для YouTube кликабельными ссылками
            if stype == "youtube":
                enriched_text = self.enrich_markdown_with_clickable_timestamps(output_text, clean_url)
            else:
                enriched_text = output_text

            # Сбор статистики использования токенов
            total_tokens = getattr(usage, "total_tokens", None) if usage else None
            input_tokens = getattr(usage, "prompt_token_count", None) or getattr(usage, "input_tokens", None) if usage else None
            output_tokens = getattr(usage, "candidates_token_count", None) or getattr(usage, "output_tokens", None) if usage else None

            return AnalysisResult(
                output_text=enriched_text,
                model=self.model,
                video_url=clean_url,
                source_type=stype,
                video_meta=video_metadata,
                total_tokens=total_tokens,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                interaction_id=interaction_id,
            )

        except Exception as e:
            err_msg = str(e)
            if "API_KEY" in err_msg.upper() or "API key not valid" in err_msg:
                raise RuntimeError("🔑 Ошибка авторизации: неверный API-ключ Gemini.") from e
            elif "429" in err_msg or "too_many_requests" in err_msg.lower() or "quota" in err_msg.lower():
                raise RuntimeError(
                    "⚠️ Превышена квота запросов (429 Rate Limit / Quota Exceeded).\n\n"
                    "Причина: аккаунт сейчас работает на бесплатном тарифе (Free Tier) в Google AI Studio, "
                    "где установлены лимиты на частоту видео-запросов.\n\n"
                    "Как исправить:\n"
                    "1. В Google AI Studio (aistudio.google.com) привяжите платежный аккаунт (Pay-as-you-go). "
                    "Анализ видео с Agentic Understanding стоит доли цента.\n"
                    "2. Либо подождите 1–2 минуты, пока сбросится минутная квота."
                ) from e
            elif "503" in err_msg or "high demand" in err_msg.lower() or "unavailable" in err_msg.lower():
                raise RuntimeError(
                    "⏳ Модель сейчас испытывает пиковую нагрузку (503 Service Unavailable).\n"
                    "Попробуйте повторить запрос через минуту или выбрать другую модель в настройках."
                ) from e
            elif "404" in err_msg or "not found" in err_msg.lower():
                raise RuntimeError(f"❌ Видео '{video_source}' не найдено или является приватным.") from e
            else:
                raise RuntimeError(f"❌ Ошибка при анализе видео через Gemini API: {err_msg}") from e
