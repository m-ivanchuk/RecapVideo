"""
Модуль для извлечения и скачивания видеофайлов из Google Drive.
Поддерживает стандартные ссылки просмотра и расшаренные ссылки Google Drive,
а также корректно обрабатывает скачивание файлов большого размера (>100MB)
с подтверждением антивирусного предупреждения Google.
"""

import os
import re
import urllib.parse
from pathlib import Path
from typing import Callable, Optional, Tuple

import requests


class GoogleDriveDownloader:
    """Утилита для скачивания файлов из Google Drive."""

    CACHE_DIR = Path("reports/.cache")

    @staticmethod
    def extract_file_id(url: str) -> Optional[str]:
        """
        Извлекает ID файла из ссылок Google Drive различных форматов:
        - https://drive.google.com/file/d/FILE_ID/view?usp=sharing
        - https://drive.google.com/open?id=FILE_ID
        - https://drive.google.com/uc?id=FILE_ID
        - https://docs.google.com/file/d/FILE_ID/edit
        """
        if not url:
            return None

        patterns = [
            r"/file/d/([a-zA-Z0-9_-]{25,})",
            r"[?&]id=([a-zA-Z0-9_-]{25,})",
            r"/open\?id=([a-zA-Z0-9_-]{25,})",
            r"/uc\?id=([a-zA-Z0-9_-]{25,})",
            r"/document/d/([a-zA-Z0-9_-]{25,})",
            r"/presentation/d/([a-zA-Z0-9_-]{25,})",
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        # Если передали сам ID
        if re.match(r"^[a-zA-Z0-9_-]{25,}$", url.strip()):
            return url.strip()

        return None

    @staticmethod
    def is_gdrive_url(url: str) -> bool:
        """Проверяет, является ли ссылка ссылкой на Google Drive."""
        if not url:
            return False
        clean = url.strip().lower()
        return ("drive.google.com" in clean or "docs.google.com" in clean) and (
            GoogleDriveDownloader.extract_file_id(url) is not None
        )

    @classmethod
    def get_confirm_token(cls, response: requests.Response) -> Optional[str]:
        """Извлекает токен подтверждения скачивания для больших файлов."""
        for key, value in response.cookies.items():
            if key.startswith("download_warning"):
                return value

        # Проверяем HTML на наличие формы подтверждения или параметров confirm/uuid
        text = response.text
        match_confirm = re.search(r'name="confirm"\s+value="([^"]+)"', text)
        if match_confirm:
            return match_confirm.group(1)

        match_link = re.search(r'href="[^"]*confirm=([a-zA-Z0-9_-]+)', text)
        if match_link:
            return match_link.group(1)

        return None

    @classmethod
    def extract_filename_from_headers(
        cls, response: requests.Response, default: str
    ) -> str:
        """Извлекает имя файла из Content-Disposition заголовка ответа."""
        cd = response.headers.get("content-disposition", "")
        if "filename*=" in cd:
            match = re.search(r"filename\*=UTF-8''([^;]+)", cd)
            if match:
                return urllib.parse.unquote(match.group(1).strip('"\''))
        if "filename=" in cd:
            match = re.search(r'filename="?([^";]+)"?', cd)
            if match:
                return match.group(1).strip('"\'')
        return default

    @classmethod
    def download_file(
        cls,
        url_or_id: str,
        output_dir: Optional[Path] = None,
        custom_filename: Optional[str] = None,
        progress_callback: Optional[Callable[[int, Optional[int]], None]] = None,
    ) -> Tuple[Path, str]:
        """
        Скачивает видеофайл из Google Drive.
        :param url_or_id: Ссылка Google Drive или ID файла.
        :param output_dir: Папка для сохранения (по умолчанию reports/.cache).
        :param custom_filename: Принудительное имя файла.
        :param progress_callback: Функция обратного вызова (скачано байт, всего байт).
        :return: Кортеж (абсолютный путь к скачанному файлу, имя файла).
        """
        file_id = cls.extract_file_id(url_or_id)
        if not file_id:
            raise ValueError(f"Не удалось распознать Google Drive ID из '{url_or_id}'.")

        target_dir = output_dir or cls.CACHE_DIR
        target_dir.mkdir(parents=True, exist_ok=True)

        session = requests.Session()
        download_url = "https://drive.google.com/uc"

        # Шаг 1: первичный запрос
        response = session.get(
            download_url,
            params={"id": file_id, "export": "download"},
            stream=True,
            timeout=30,
        )

        token = cls.get_confirm_token(response)
        params = {"id": file_id, "export": "download"}

        # Шаг 2: если файл большой, отправляем подтверждение
        if token:
            params["confirm"] = token
            response = session.get(
                download_url,
                params=params,
                stream=True,
                timeout=60,
            )

        # Проверка на ошибки доступа
        content_type = response.headers.get("content-type", "").lower()
        if "text/html" in content_type and response.status_code == 200:
            # Если вернулась HTML страница вместо файла, проверяем сообщение об ошибке
            html_text = response.text
            if "Virus scan warning" in html_text or "download-form" in html_text:
                # Попробуем альтернативную форму drive.usercontent.google.com
                form_action_match = re.search(r'<form\s+id="download-form"\s+action="([^"]+)"', html_text)
                if form_action_match:
                    action_url = form_action_match.group(1)
                    inputs = dict(re.findall(r'<input\s+type="hidden"\s+name="([^"]+)"\s+value="([^"]*)"', html_text))
                    response = session.get(action_url, params=inputs, stream=True, timeout=60)
            elif "Google Drive - Access denied" in html_text or "Доступ запрещен" in html_text:
                raise PermissionError(
                    "❌ Доступ к файлу в Google Drive запрещён. "
                    "Убедитесь, что в настройках доступа к видео выбрано 'Все, у кого есть ссылка' (Viewer)."
                )

        if response.status_code != 200:
            raise RuntimeError(
                f"Ошибка при скачивании из Google Drive (HTTP {response.status_code}): {response.reason}"
            )

        # Определяем итоговое имя файла
        filename = custom_filename or cls.extract_filename_from_headers(
            response, default=f"gdrive_{file_id}.mp4"
        )
        if not any(filename.lower().endswith(ext) for ext in [".mp4", ".mov", ".avi", ".mkv", ".webm"]):
            filename += ".mp4"

        dest_path = target_dir / filename

        # Шаг 3: стриминг файла на диск
        total_size = response.headers.get("content-length")
        total_bytes = int(total_size) if total_size and total_size.isdigit() else None

        downloaded_bytes = 0
        chunk_size = 1024 * 1024  # 1 MB

        with open(dest_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded_bytes += len(chunk)
                    if progress_callback:
                        progress_callback(downloaded_bytes, total_bytes)

        if dest_path.stat().st_size == 0:
            dest_path.unlink(missing_ok=True)
            raise RuntimeError("Скачанный из Google Drive файл пуст. Проверьте права доступа к ссылке.")

        return dest_path, filename
