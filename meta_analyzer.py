"""
Модуль агрегации и мета-анализа всех отчётов плейтестов по конкретному проекту (игре).
"""

import os
from dataclasses import dataclass
from typing import Dict, List, Optional
from dotenv import load_dotenv

load_dotenv()

try:
    from google import genai
except ImportError:
    genai = None

from projects import Project


@dataclass
class MetaAnalysisResult:
    content: str
    model: str
    reports_count: int
    project_name: str


class MetaAnalyzer:
    """Анализирует массив отдельных плейтест-отчетов для выявления общих закономерностей."""

    DEFAULT_MODEL = "gemini-3.5-flash"

    def __init__(self, api_key: Optional[str] = None, model: str = DEFAULT_MODEL):
        if genai is None:
            raise ImportError("Пакет 'google-genai' не установлен.")

        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("Не найден GEMINI_API_KEY.")

        self.model = model
        self.client = genai.Client(api_key=self.api_key)

    @staticmethod
    def build_meta_prompt(
        project: Project,
        reports_data: List[Dict[str, str]],
        game_context: Optional[str] = None,
        focus_question: Optional[str] = None
    ) -> str:
        """Формирует промпт для мета-синтеза всех отчётов."""
        parts = [
            "ТЫ — ГЛАВНЫЙ ГЕЙМДИЗАЙНЕР И ДИРЕКТОР ПО UX (Head of Game UX & Creative Director).",
            f"Перед тобой сводка {len(reports_data)} независимых плейтестов и видео-обзоров игры '{project.name}'.",
        ]

        if game_context and game_context.strip():
            parts.extend([
                f"• Контекст игры от разработчика: {game_context.strip()}"
            ])

        parts.extend([
            "",
            "ТВОЯ ЗАДАЧА — провести глубокий МЕТА-АНАЛИЗ и кросс-сессионный синтез.",
            "Не просто пересказывай каждый отчет по отдельности, а ВЫЯВИ СИСТЕМНЫЕ ЗАКОНОМЕРНОСТИ:",
            "какие проблемы повторяются из раза в раз у разных игроков, где системные дыры в геймдизайне,",
            "и что нужно исправлять в самую первую очередь.",
            "",
            "СТРУКТУРА ТВОЕГО СВОДНОГО ОТЧЁТА:",
            "",
            "1. 🚨 ТОП ПОВТОРЯЮЩИХСЯ ПРОБЛЕМ (Главные боли игроков):",
            "   - Проблемы, с которыми столкнулись 2+ или большинство игроков.",
            "   - Опиши паттерн: в чём именно сходство их затруднений?",
            "   - Почему текущий дизайн провоцирует эту ошибку у разных людей?",
            "",
            "2. 🗺 ТЕПЛОВАЯ КАРТА ЗАТЫКОВ (Chokepoints Heatmap):",
            "   - В каких конкретно местах/уровнях/моментах игры чаще всего падает темп, игроки теряются или начинают раздражаться?",
            "   - Есть ли критическая точка, где игроки близки к тому, чтобы бросить игру (Drop-off point)?",
            "",
            "3. 💎 ЯДРО УДОВОЛЬСТВИЯ (Что нельзя ломать):",
            "   - Что вызвало стабильно позитивный отклик у большинства тестировщиков?",
            "   - Сильные стороны игры, которые нужно развивать и беречь при патчах.",
            "",
            "4. ⚖️ МАТРИЦА ПРИОРИТЕТОВ (Impact vs Frequency):",
            "   - [P0 БЛОКЕРЫ - Чинить немедленно]: проблемы с высокой частотой и высоким негативным влиянием на удержание.",
            "   - [P1 ВАЖНО - Дизайн и Навигация]: частые шероховатости, требующие ребаланса или доработки ориентиров (свет, маркеры).",
            "   - [P2 ПОЛИШИНГ - Качество жизни (QoL)]: редкие или минорные замечания по UI/удобству.",
            "",
            "5. 🛠 БЭКЛОГ ЗАДАЧ ДЛЯ КОМАНДЫ (Actionable Dev Backlog):",
            "   - Оформи в виде таблицы с колонками: [Приоритет | Отдел (Геймдизайн/Левелдизайн/UI/Код) | Суть проблемы | Предлагаемое решение]",
        ])

        if focus_question and focus_question.strip():
            parts.extend([
                "",
                "=== ОСОБЫЙ ФОКУС ОТ РАЗРАБОТЧИКА ===",
                f"Обрати особое внимание на следующий вопрос: {focus_question.strip()}",
                ""
            ])

        parts.append("\n=== ОТЧЁТЫ ПЛЕЙТЕСТОВ ДЛЯ АНАЛИЗА ===")
        for i, rep in enumerate(reports_data, 1):
            parts.append(f"\n--- [ОТЧЁТ #{i}: {rep['filename']}] ---")
            parts.append(rep["content"].strip())

        return "\n".join(parts)

    def analyze_reports(
        self,
        project: Project,
        reports_data: List[Dict[str, str]],
        focus_question: Optional[str] = None
    ) -> MetaAnalysisResult:
        """Запускает синтез всех отчётов через Gemini."""
        if not reports_data:
            raise ValueError("Список отчётов для анализа пуст.")

        prompt = self.build_meta_prompt(
            project=project,
            reports_data=reports_data,
            focus_question=focus_question
        )

        try:
            # Для мета-анализа текста большого объема используем generate_content или interactions
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt
            )

            text = response.text or "Не удалось сгенерировать ответ."
            return MetaAnalysisResult(
                content=text,
                model=self.model,
                reports_count=len(reports_data),
                project_name=project.name
            )

        except Exception as e:
            err = str(e)
            if "429" in err or "quota" in err.lower():
                raise RuntimeError("Превышена квота запросов (429 RateLimit). Подождите 1 минуту или подключите биллинг.") from e
            elif "503" in err or "unavailable" in err.lower():
                raise RuntimeError("Модель перегружена (503). Попробуйте модель gemini-3.5-flash.") from e
            else:
                raise RuntimeError(f"Ошибка при мета-анализе: {err}") from e
