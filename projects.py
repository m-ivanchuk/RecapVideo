"""
Модуль управления проектами на основе папок внутри reports/.
Каждая папка внутри reports/ (например, reports/superweird) — это отдельный проект/игра.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
from typing import Any, Dict, List, Optional


@dataclass
class Project:
    name: str        # Имя папки, например 'superweird'
    path: Path       # Путь к папке reports/superweird

    @property
    def display_name(self) -> str:
        return self.name


class ProjectManager:
    """Управляет проектами игр на основе структуры папок в reports/."""

    BASE_DIR = Path("reports")

    @classmethod
    def init(cls):
        """Гарантирует существование папки reports/."""
        cls.BASE_DIR.mkdir(exist_ok=True)

    @classmethod
    def list_projects(cls) -> List[Project]:
        """
        Возвращает список всех проектов (папок внутри reports/).
        Если папок нет, но в корне reports/ есть файлы, добавляет 'Общие'.
        """
        cls.init()
        projects = []
        for item in sorted(cls.BASE_DIR.iterdir()):
            if item.is_dir() and not item.name.startswith("."):
                projects.append(Project(name=item.name, path=item))

        # Если папок пока нет, создаем дефолтную 'default'
        if not projects:
            default_path = cls.BASE_DIR / "superweird"
            default_path.mkdir(exist_ok=True)
            projects.append(Project(name="superweird", path=default_path))

        return projects

    @classmethod
    def get_project(cls, name: str) -> Optional[Project]:
        """Получает проект по имени папки."""
        path = cls.BASE_DIR / name
        if path.is_dir():
            return Project(name=name, path=path)
        return None

    @classmethod
    def create_project(cls, name: str) -> Project:
        """Создает новую папку проекта внутри reports/."""
        clean_name = name.strip()
        path = cls.BASE_DIR / clean_name
        path.mkdir(parents=True, exist_ok=True)
        return Project(name=clean_name, path=path)

    @classmethod
    def list_reports(cls, project_name: str) -> List[Dict[str, Any]]:
        """
        Возвращает список отчетов по видео (файлы recap_*.md) из папки reports/<project_name>.
        """
        proj = cls.get_project(project_name)
        if not proj:
            return []

        reports = []
        for file in sorted(proj.path.glob("*.md"), reverse=True):
            if file.name.startswith("meta_recap_"):
                continue  # Пропускаем сводные мета-отчеты

            video_url = ""
            video_title = ""
            channel_name = ""
            channel_url = ""
            views_str = ""

            try:
                with open(file, "r", encoding="utf-8") as f:
                    for _ in range(25):  # Читаем только первые 25 строк шапки
                        line = f.readline()
                        if not line:
                            break
                        if "**Видео**:" in line:
                            # [Title](URL) or plain URL
                            m = re.search(r"\[(.*?)\]\((https?://.*?)\)", line)
                            if m:
                                video_title = m.group(1)
                                video_url = m.group(2)
                            else:
                                video_url = line.split(":", 1)[1].strip()
                        elif "**Канал**:" in line:
                            m = re.search(r"\[(.*?)\]\((https?://.*?)\)", line)
                            if m:
                                channel_name = m.group(1)
                                channel_url = m.group(2)
                            else:
                                channel_name = line.split(":", 1)[1].strip()
                        elif "**Просмотры**:" in line:
                            views_str = line.split(":", 1)[1].strip()
            except Exception:
                pass

            reports.append({
                "filename": file.name,
                "path": str(file),
                "created_at": datetime.fromtimestamp(file.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "size_kb": round(file.stat().st_size / 1024, 1),
                "video_url": video_url,
                "video_title": video_title or file.name,
                "channel_name": channel_name or "Неизвестный канал",
                "channel_url": channel_url,
                "views": views_str
            })

        return reports

    @classmethod
    def list_meta_recaps(cls, project_name: str) -> List[Dict[str, Any]]:
        """
        Возвращает список сохранённых сводных мета-отчётов (meta_recap_*.md).
        """
        proj = cls.get_project(project_name)
        if not proj:
            return []

        recaps = []
        for file in sorted(proj.path.glob("meta_recap_*.md"), reverse=True):
            recaps.append({
                "filename": file.name,
                "path": str(file),
                "created_at": datetime.fromtimestamp(file.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "size_kb": round(file.stat().st_size / 1024, 1),
            })

        return recaps

    @classmethod
    def save_report(cls, project_name: str, filename: str, content: str) -> Path:
        """Сохраняет отчет по отдельному видео в папку reports/<project_name>/."""
        proj = cls.get_project(project_name)
        if not proj:
            proj = cls.create_project(project_name)

        path = proj.path / filename
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        return path

    @classmethod
    def save_meta_recap(cls, project_name: str, content: str) -> Path:
        """Сохраняет сводный мета-рекап в папку reports/<project_name>/."""
        proj = cls.get_project(project_name)
        if not proj:
            proj = cls.create_project(project_name)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"meta_recap_{ts}.md"
        path = proj.path / filename

        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        return path
