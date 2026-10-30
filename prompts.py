"""
Модуль для совместимости пресетов и промптов.
Делегирует управление навыками в skills.SkillManager, обеспечивая бесшовную интеграцию
как со встроенными геймдев-пресетами, так и с кастомными скиллами (киномонтаж, реклама и др.).
"""

from typing import Any, Dict, List, Optional
from skills import Skill, SkillManager


class PresetsProxy(dict):
    """
    Динамический словарь-прокси для словаря PRESETS.
    Автоматически синхронизируется со всеми скиллами из SkillManager (папка skills/*.json).
    """

    def __getitem__(self, key: str) -> Dict[str, str]:
        skill = SkillManager.get_skill(key)
        return {
            "title": skill.title,
            "description": skill.description,
            "prompt_focus": skill.prompt_focus,
        }

    def get(self, key: str, default: Any = None) -> Any:
        try:
            skill = SkillManager.get_skill(key)
            return {
                "title": skill.title,
                "description": skill.description,
                "prompt_focus": skill.prompt_focus,
            }
        except Exception:
            return default

    def keys(self):
        return [s.id for s in SkillManager.list_skills()]

    def items(self):
        return [(s.id, self[s.id]) for s in SkillManager.list_skills()]

    def values(self):
        return [self[s.id] for s in SkillManager.list_skills()]

    def __iter__(self):
        return iter(self.keys())

    def __len__(self):
        return len(SkillManager.list_skills())

    def __contains__(self, key: object) -> bool:
        return any(s.id == key for s in SkillManager.list_skills())


PRESETS: Dict[str, Dict[str, str]] = PresetsProxy()


def build_analysis_prompt(
    preset_key: str = "full_ux_audit",
    custom_questions: Optional[List[str]] = None,
    game_context: Optional[str] = None,
) -> str:
    """
    Формирует финальный промпт для модели Gemini с учётом выбранного скилла,
    контекста пользователя и кастомных вопросов.
    """
    skill = SkillManager.get_skill(preset_key)
    return SkillManager.build_prompt(
        skill=skill,
        custom_questions=custom_questions,
        context=game_context,
    )
