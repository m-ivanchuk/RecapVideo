"""
Модуль управления навыками (Skills / Presets) для агентского анализа видео в Gemini.
Поддерживает системные пресеты и загрузку/сохранение пользовательских скиллов из папки skills/*.json.
"""

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class Skill:
    """Модель навыка (скилла) для анализа видео."""

    id: str
    title: str
    description: str
    system_role: str
    prompt_focus: str
    category: str = "custom"
    rules: List[str] = field(default_factory=list)
    is_builtin: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def extract_criteria_sections(self) -> List[str]:
        """
        Извлекает ключевые разделы и параметры отсмотра из prompt_focus.
        Например:
        - "1. 🚀 Первое впечатление и онбординг (FTUE)"
        - "2. ⚠️ Точки трения, затыки и фрустрация (UX Friction)"
        """
        lines = self.prompt_focus.strip().split("\n")
        sections = []
        for line in lines:
            line_str = line.strip()
            # Ищем нумерованные пункты верхнего уровня (1., 2., 1)) или заголовки markdown (##, ###)
            if re.match(r"^(\d+[\.\)]|#{1,3})\s+", line_str):
                clean = re.sub(r"^(#+\s*|\d+[\.\)]\s*)", "", line_str).rstrip(":")
                sections.append(clean)
            elif line_str.startswith("- ") and len(sections) == 0 and len(line_str) > 5:
                clean = line_str[2:].rstrip(":")
                sections.append(clean)

        if not sections:
            # Fallback: берем непустые верхние строки (до 5 штук)
            non_empty = [
                l.strip().lstrip("•-* ").rstrip(":")
                for l in lines
                if l.strip() and not l.startswith("   ") and len(l.strip()) > 3
            ]
            sections = non_empty[:5]

        return sections

    @classmethod
    def from_dict(cls, data: Dict[str, Any], is_builtin: bool = False) -> "Skill":
        # Санитизация ID
        raw_id = data.get("id") or data.get("name") or "custom_skill"
        clean_id = re.sub(r"[^a-zA-Z0-9_-]", "_", raw_id).lower()

        rules = data.get("rules", [])
        if isinstance(rules, str):
            rules = [r.strip("- ") for r in rules.split("\n") if r.strip()]

        return cls(
            id=clean_id,
            title=data.get("title", "Пользовательский скилл"),
            description=data.get("description", "Кастомный пресет анализа"),
            category=data.get("category", "custom"),
            system_role=data.get(
                "system_role",
                "Ты — ведущий эксперт по видеоанализу с использованием Agentic Video Understanding.",
            ),
            prompt_focus=data.get("prompt_focus", ""),
            rules=rules,
            is_builtin=is_builtin,
        )


class SkillManager:
    """Менеджер для загрузки, сохранения и формирования промптов скиллов."""

    SKILLS_DIR = Path("skills")

    BUILTIN_SKILLS: Dict[str, Skill] = {
        "full_ux_audit": Skill(
            id="full_ux_audit",
            title="🎯 Полный UX & Геймдизайн аудит",
            description="Комплексный разбор геймплея: туториал, онбординг, точки трения, понятность интерфейса, баланс, баги и эмоции.",
            category="gamedev",
            is_builtin=True,
            system_role=(
                "ТЫ — ВЕДУЩИЙ ИССЛЕДОВАТЕЛЬ ИГРОВОГО ОПЫТА (Senior Game UX Researcher & Game Designer).\n"
                "Твоя задача — внимательно изучить прикрепленное геймплейное видео плейтеста игры с помощью агентского анализа видео (Agentic Video Understanding).\n"
                "ДИНАМИЧЕСКИ исследуй ключевые моменты таймлайна, сопоставляй происходящее на экране со звуком, комментариями и эмоциями игрока."
            ),
            rules=[
                "ВСЕГДА указывай точные таймкоды в формате [MM:SS] или [HH:MM:SS] для каждого замечания, бага или момента фрустрации.",
                "Обращай внимание на микро-реакции игрока: вращение камерой в растерянности, повторные нажатия кнопок, зависания на месте, вздохи, интонации голоса.",
                "Разделяй факты (что произошло на экране) и интерпретацию (почему дизайн вызвал эту проблему).",
                "Все рекомендации должны быть практическими и выполнимыми для команды разработчиков игры.",
            ],
            prompt_focus="""
Выполни комплексный и глубокий UX / Game Design аудит плейтеста по видео.
Твоя цель — выявить все проблемы игрового опыта, найти места где игрок застрял или запутался, и дать четкие геймдизайнерские рекомендации по улучшению.

Проанализируй видео по следующим блокам с точными таймкодами [MM:SS] или [HH:MM:SS]:

1. 🚀 Первое впечатление и онбординг (FTUE):
   - Понял ли игрок базовую цель игры, управление и правила?
   - Читал ли он всплывающие подсказки или туториалы, или скипал их?
   - Сформировалась ли правильная ментальная модель механик?

2. ⚠️ Точки трения, затыки и фрустрация (UX Friction):
   - В каких конкретно моментах игрок терялся, блуждал по локации, не понимал куда идти или что делать?
   - Какие вербальные реакции игрока (вздохи, ругательства, вопросы вслух: «куда идти?», «что это значит?», раздражение)?
   - Были ли повторяющиеся смерти или тупики из-за неочевидных правил?

3. 🖥 Читаемость интерфейса (UI/HUD & Feedback):
   - Замечал ли игрок важные индикаторы (здоровье, патроны, квесты, мини-карту, маркеры)?
   - Были ли элементы интерфейса, которые игрок искал и не мог найти?
   - Насколько понятна обратная связь игры на действия игрока (хитбоксы, попадания, получение урона)?

4. 🎮 Геймплейный цикл, баланс и пейсинг (Pacing & Balance):
   - Темп игры: где было скучно/затянуто, а где слишком резкий спайк сложности?
   - Читаемость атак врагов и анимаций: успевал ли игрок реагировать?
   - Использовал ли игрок весь арсенал способностей/оружия или спамил одну кнопку?

5. 🐛 Баги, глитчи и технические проблемы:
   - Замеченные баги геометрии, застревания, сбои анимаций, рассинхроны звука, баги UI.

6. 🌟 Что сработало отлично (Fun Factors & Highlights):
   - Моменты искреннего восторга, смеха, похвалы или удовлетворения игрока.

7. 🛠 Приоритетный план улучшений (Action Items):
   - Таблица рекомендаций с категориями:
     - [P0 Критично]: ломает прохождение или вызывает дроп игры.
     - [P1 Важно]: существенное трение, требует доработки дизайна/навигации.
     - [P2 Полишинг]: минорные улучшения качества жизни (QoL).
""".strip(),
        ),
        "ftue_onboarding": Skill(
            id="ftue_onboarding",
            title="👶 FTUE & Онбординг (Первые шаги и обучение)",
            description="Фокус на обучении, когнитивной нагрузке, понятности механик и первых 15-30 минутах игры.",
            category="gamedev",
            is_builtin=True,
            system_role="ТЫ — СПЕЦИАЛИСТ ПО ОНБОРДИНГУ И ОБУЧЕНИЮ ИГРОКОВ (FTUE Specialist).",
            rules=[
                "ВСЕГДА указывай точные таймкоды [MM:SS] или [HH:MM:SS] для каждого наблюдения.",
                "Фиксируй моменты замешательства, пропущенные инструкции и мисс-инпуты.",
            ],
            prompt_focus="""
Сфокусируйся на анализе онбординга (First Time User Experience) и обучения.
Таймкоды [MM:SS] обязательны для каждого наблюдения!

1. Обучение управлению:
   - Было ли игроку интуитивно понятно базовое управление?
   - Были ли мисс-инпуты (нажатия не тех клавиш, путаница в кнопках)?
2. Понятность целей и задач:
   - Понимал ли игрок, ЗАЧЕМ он выполняет текущее действие?
   - Заметил ли он ключевые подсказки туториала?
3. Когнитивная нагрузка:
   - Не было ли вывалено слишком много текста за раз?
   - Смог ли игрок применить только что полученные знания на практике?
4. Момент удержания / First Aha! Moment:
   - Случился ли момент, когда игрок понял «фишку» игры и увлекся?
5. Конкретные рекомендации по улучшению первых 15 минут игры.
""".strip(),
        ),
        "friction_and_chokepoints": Skill(
            id="friction_and_chokepoints",
            title="🛑 Поиск затыков и фрустрации (Chokepoints)",
            description="Поиск мест, где игрок застрял, блуждал в локации, не заметил проход или выражал раздражение.",
            category="gamedev",
            is_builtin=True,
            system_role="ТЫ — ЛЕВЕЛ-ДИЗАЙНЕР И UX-АУДИТОР ПО НАВИГАЦИИ (Level Designer & Navigation Auditor).",
            rules=[
                "Для каждого затыка обязательно указывай точный таймкод [MM:SS].",
                "Предлагай конкретные решения по левел-дизайну (свет, ориентиры, указатели).",
            ],
            prompt_focus="""
Сфокусируйся на поиске «затыков», плохой навигации и моментов фрустрации.
Для каждого момента укажи точный таймкод [MM:SS], опиши что произошло и почему игрок застрял.

1. Навигационные тупики (Level Design & Signposting):
   - Моменты, когда игрок бегал кругами, не понимая, где выход или нужная дверь.
   - Недостаток визуальных ориентиров (свет, цвет, направляющие линии).
2. Загадки и цели:
   - Моменты, когда игрок не понимал условие решения задачи/пазла.
3. Вербальные и поведенческие признаки раздражения:
   - Таймкоды вздохов, жалоб, саркастических комментариев или попыток выйти/перезагрузиться.
4. Конкретные решения: что добавить в локацию (свет, метку, убрать ложный путь), чтобы убрать трение.
""".strip(),
        ),
        "combat_and_mechanics": Skill(
            id="combat_and_mechanics",
            title="⚔️ Боевка, управление и баланс (Combat)",
            description="Читаемость врагов, ощущение от ударов (game feel), баланс сложности и тактическое разнообразие.",
            category="gamedev",
            is_builtin=True,
            system_role="ТЫ — ВЕДУЩИЙ КОМБАТ-ДИЗАЙНЕР (Lead Combat Designer & System Balance Specialist).",
            rules=[
                "Обязательно приводи таймкоды [MM:SS] боев и атак врагов.",
                "Анализируй тайминги, телеграфирование атак и обратную связь.",
            ],
            prompt_focus="""
Сфокусируйся на анализе боевой системы, механик и баланса игры по видео.
Обязательно приводи таймкоды [MM:SS] боев!

1. Читаемость врагов и атак (Telegraphing):
   - Успевал ли игрок понимать, какую атаку готовит противник?
   - Были ли «нечестные» удары из слепой зоны или без предупреждения?
2. Game Feel и обратная связь (Impact & Feedback):
   - Чувствуется ли вес ударов, хитстоп, звуковой и визуальный отклик?
3. Баланс сложности:
   - Враги ощущаются опасными или «губками для урона» (damage sponges)?
   - Возникали ли ситуации бессилия (stunlock, бесконечный нокдаун)?
4. Поведение игрока:
   - Использовал ли игрок тактическое разнообразие или нашел одну абьюзивную стратегию?
5. Рекомендации по полишингу боевки и параметров баланса.
""".strip(),
        ),
        "custom_only": Skill(
            id="custom_only",
            title="✍️ Только собственные вопросы пользователя",
            description="Анализ строго по вашему индивидуальному списку вопросов и гипотез.",
            category="general",
            is_builtin=True,
            system_role="ТЫ — ВЕДУЩИЙ АНАЛИТИК ВИДЕОКОНТЕНТА (Senior Video Understanding Specialist).",
            rules=[
                "Отвечай на предоставленные вопросы максимально подробно с точными таймкодами [MM:SS].",
                "Опирайся на происходящее на экране, аудиодорожку и динамику сцены.",
            ],
            prompt_focus="Ответь на предоставленные вопросы максимально подробно, опираясь на визуальный ряд и звук. Для каждого вывода приводи точные таймкоды [MM:SS] из видео!",
        ),
    }

    @classmethod
    def init(cls):
        """Создает директорию skills/, если она отсутствует."""
        cls.SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def list_skills(cls) -> List[Skill]:
        """Возвращает список всех доступных навыков (встроенных и пользовательских)."""
        cls.init()
        skills = list(cls.BUILTIN_SKILLS.values())

        # Загружаем кастомные скиллы из папки skills/*.json
        for path in sorted(cls.SKILLS_DIR.glob("*.json")):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                skill = Skill.from_dict(data, is_builtin=False)
                # Если переопределяет ID, заменяем или добавляем
                existing_idx = next((i for i, s in enumerate(skills) if s.id == skill.id), None)
                if existing_idx is not None and not skills[existing_idx].is_builtin:
                    skills[existing_idx] = skill
                else:
                    skills.append(skill)
            except Exception as e:
                print(f"Ошибка загрузки скилла из {path.name}: {e}")

        return skills

    @classmethod
    def get_skill(cls, skill_id: str) -> Skill:
        """Возвращает скилл по идентификатору или дефолтный full_ux_audit."""
        skills = cls.list_skills()
        for s in skills:
            if s.id == skill_id:
                return s
        return cls.BUILTIN_SKILLS["full_ux_audit"]

    @classmethod
    def save_skill(cls, skill: Skill) -> Path:
        """Сохраняет пользовательский скилл в файл skills/{id}.json."""
        cls.init()
        clean_id = re.sub(r"[^a-zA-Z0-9_-]", "_", skill.id).lower()
        path = cls.SKILLS_DIR / f"{clean_id}.json"

        data = skill.to_dict()
        data["is_builtin"] = False

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return path

    @classmethod
    def delete_skill(cls, skill_id: str) -> bool:
        """Удаляет пользовательский скилл."""
        cls.init()
        path = cls.SKILLS_DIR / f"{skill_id}.json"
        if path.exists():
            path.unlink()
            return True
        return False

    @classmethod
    def parse_from_json(cls, json_text: str) -> Skill:
        """Парсит JSON-строку в объект Skill без сохранения на диск."""
        cleaned = re.sub(r"^```(?:json)?\s*", "", json_text.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r"\s*```$", "", cleaned.strip(), flags=re.MULTILINE)
        data = json.loads(cleaned)
        return Skill.from_dict(data, is_builtin=False)

    @classmethod
    def import_from_json(cls, json_text: str) -> Skill:
        """Импортирует и сохраняет скилл из JSON-строки."""
        skill = cls.parse_from_json(json_text)
        cls.save_skill(skill)
        return skill

    @classmethod
    def generate_skill_with_ai(
        cls,
        client: Any,
        model: str,
        topic_description: str,
        knowledge_base_text: Optional[str] = None,
        attached_parts: Optional[List[Any]] = None,
    ) -> Skill:
        """
        Генерирует новый навык (Skill) с помощью Gemini API на основе текстового описания
        и опциональной базы знаний (регламент, методология, экспорт из NotebookLM, PDF/TXT).
        """
        meta_prompt = f"""
Ты — ведущий инженер промптов для мультимодальных систем анализа видео (Gemini Agentic Video Understanding).
Твоя задача — создать специализированный навык (Skill / Preset) для инструмента RecapVideo в формате строгого JSON.

ПОЛЬЗОВАТЕЛЬСКИЙ ЗАПРОС И ТЕМА ДЛЯ СКИЛЛА:
{topic_description.strip()}
"""
        if knowledge_base_text and knowledge_base_text.strip():
            meta_prompt += f"""
=== МАТЕРИАЛЫ БАЗЫ ЗНАНИЙ / РЕГЛАМЕНТ / ЭКСПОРТ ИЗ NOTEBOOKLM ===
{knowledge_base_text.strip()}
===============================================================
"""

        meta_prompt += """
ТРЕБОВАНИЯ К СТРУКТУРЕ JSON-ОБЪЕКТА:
{
  "id": "латинский_id_в_snake_case (например: cinematic_noir_audit, webinar_retention)",
  "title": "Эмодзи + Название навыка на русском языке",
  "description": "Краткое пояснение (1-2 предложения)",
  "category": "одна из категорий: cinema | gamedev | marketing | education | sports | interview | general",
  "system_role": "ТЫ — [ВЕДУЩИЙ ЭКСПЕРТ В ЭТОЙ ОБЛАСТИ]. Твоя цель — провести детальный экспертный аудит прикрепленного видео с помощью агентского анализа видео (Agentic Video Understanding). ДИНАМИЧЕСКИ исследуй ключевые моменты таймлайна, сопоставляй происходящее на экране со звуком и речью.",
  "rules": [
    "ВСЕГДА указывай точные таймкоды в формате [MM:SS] или [HH:MM:SS] для каждого замечания, ошибки или сильного момента.",
    "Разделяй объективные факты (что конкретно видно/слышно) и экспертную критику.",
    "Давай только практические, выполнимые рекомендации."
  ],
  "prompt_focus": "Четко структурированные блоки критериев отсмотра видео (от 4 до 6 пронумерованных разделов: '1. ...\\n2. ...') и финальный блок с таблицей рекомендаций Action Items с таймкодами [MM:SS]."
}

ПРАВИЛА:
1. Выводи СТРОГО валидный JSON-объект. Без markdown кавычек, без вступительного и заключительного текста.
2. В prompt_focus обязательно используй нумерацию разделов (1. ..., 2. ..., 3. ...), чтобы интерфейс мог извлечь список параметров отсмотра.
3. Если предоставлены материалы базы знаний, опирайся на их правила, термины и критерии.
"""
        contents: List[Any] = []
        if attached_parts:
            contents.extend(attached_parts)
        contents.append(meta_prompt)

        # Вызов Gemini API
        try:
            from google.genai import types
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.4
            )
        except Exception:
            config = None

        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )

        resp_text = response.text or ""
        return cls.parse_from_json(resp_text)


    @classmethod
    def build_prompt(
        cls,
        skill: Skill,
        custom_questions: Optional[List[str]] = None,
        context: Optional[str] = None,
    ) -> str:
        """
        Формирует итоговый промпт для модели Gemini на основе выбранного скилла.
        """
        parts = [
            skill.system_role.strip(),
            "",
            "ВАЖНЫЕ ПРАВИЛА АНАЛИЗА:",
        ]

        # Добавляем стандартные и специфические правила скилла
        default_rules = [
            "ВСЕГДА указывай точные таймкоды в формате [MM:SS] или [HH:MM:SS] для каждого замечания, ошибки или ключевого момента.",
            "Разделяй объективные факты (что произошло на видео и аудио) и профессиональную интерпретацию.",
        ]
        all_rules = list(dict.fromkeys(default_rules + skill.rules))
        for i, rule in enumerate(all_rules, start=1):
            parts.append(f"{i}. {rule}")

        parts.append("")

        if context and context.strip():
            parts.extend([
                "=== ДОПОЛНИТЕЛЬНЫЙ КОНТЕКСТ ОТ ПОЛЬЗОВАТЕЛЯ ===",
                context.strip(),
                "",
            ])

        parts.extend([
            "=== КРИТЕРИИ И СТРУКТУРА АНАЛИЗА ===",
            skill.prompt_focus.strip(),
            "",
        ])

        if custom_questions:
            valid_q = [q.strip() for q in custom_questions if q.strip()]
            if valid_q:
                parts.extend([
                    "=== СПЕЦИФИЧЕСКИЕ ВОПРОСЫ ПОЛЬЗОВАТЕЛЯ ===",
                    "Ответь на каждый из следующих вопросов детально, опираясь на видео и аудио:",
                ])
                for idx, q in enumerate(valid_q, start=1):
                    parts.append(f"{idx}. {q}")
                parts.append("")

        parts.append(
            "Начинай сразу с детального, структурированного отчета. Обязательно используй заголовки, списки, выделения и таймкоды."
        )

        return "\n".join(parts)
