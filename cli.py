#!/usr/bin/env python3
"""
Консольная утилита (CLI) для анализа видео плейтестов и сводного мета-анализа по проектам.
Поддерживает YouTube, Google Drive и локальные видеофайлы, а также кастомные скиллы из skills/*.json.
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table

from analyzer import VideoAnalyzer
from drive_downloader import GoogleDriveDownloader
from meta_analyzer import MetaAnalyzer
from projects import ProjectManager
from skills import SkillManager
from youtube_meta import fetch_youtube_metadata

console = Console()


def interactive_mode():
    """Интерактивный мастер запуска анализа."""
    console.print(
        Panel.fit(
            "[bold cyan]🎮 Game & Video Recap Tool[/bold cyan]\n"
            "[dim]Powered by Gemini Agentic Video Understanding (YouTube, Local, Google Drive)[/dim]",
            border_style="cyan",
        )
    )

    projects = ProjectManager.list_projects()
    proj_names = [p.name for p in projects]

    console.print(f"\n[bold]Существующие проекты (папки в reports/):[/bold] {', '.join(proj_names)}")
    project_name = Prompt.ask(
        "Выберите проект или введите новое имя игры/темы",
        default=proj_names[0] if proj_names else "superweird",
    )

    action = Prompt.ask(
        "\nЧто вы хотите сделать?",
        choices=["1", "2"],
        default="1",
        show_choices=False,
    )
    # 1: Анализ нового видео, 2: Сводный мета-рекап всех отчетов проекта

    if action == "2":
        return {
            "mode": "meta",
            "project": project_name,
            "focus_question": Prompt.ask(
                "Особый вопрос для мета-анализа (Enter для пропуска)", default=""
            ),
            "model": "gemini-3.5-flash",
        }

    # 1. Запрос источника видео (YouTube, Google Drive или локальный файл)
    while True:
        source = Prompt.ask(
            "\n[bold yellow]Введите ссылку на YouTube, Google Drive или путь к локальному видеофайлу[/bold yellow]"
        ).strip()
        if not source:
            console.print("[red]Источник не может быть пустым![/red]")
            continue
        if source.startswith("http") or Path(source).exists():
            break
        if not Confirm.ask(f"[yellow]Файл '{source}' не найден на диске. Продолжить всё равно?[/yellow]"):
            continue
        break

    # 2. Выбор навыка / пресета из SkillManager
    console.print("\n[bold]Выберите навык (Skill / Пресет):[/bold]")
    all_skills = SkillManager.list_skills()
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("#", style="dim", width=4)
    table.add_column("Навык (Skill)", style="cyan")
    table.add_column("Тип", style="green", width=14)
    table.add_column("Описание", style="white")

    for i, s in enumerate(all_skills, 1):
        stype = "Встроенный" if s.is_builtin else "Свой скилл"
        table.add_row(str(i), s.title, stype, s.description)

    console.print(table)

    skill_choice = Prompt.ask(
        "Номер навыка",
        choices=[str(i) for i in range(1, len(all_skills) + 1)],
        default="1",
    )
    chosen_skill = all_skills[int(skill_choice) - 1]

    # 3. Контекст
    user_context = Prompt.ask(
        "\n[bold]Краткий контекст видео[/bold] (жанр, цель анализа или Enter для пропуска)",
        default="",
    )

    # 4. Дополнительные вопросы
    custom_questions = []
    console.print("\n[bold]Специфические вопросы для проверки[/bold]:")
    while True:
        q = Prompt.ask(
            f"Вопрос #{len(custom_questions) + 1} (Enter чтобы закончить)", default=""
        ).strip()
        if not q:
            break
        custom_questions.append(q)

    # 5. Выбор модели
    model = Prompt.ask(
        "\n[bold]Модель Gemini[/bold]",
        choices=VideoAnalyzer.SUPPORTED_MODELS,
        default="gemini-3.5-flash",
    )

    return {
        "mode": "video",
        "video": source,
        "project": project_name,
        "skill": chosen_skill,
        "context": user_context,
        "custom_questions": custom_questions,
        "model": model,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Video Recap & Meta-Analysis via Gemini Agentic Video Understanding."
    )
    parser.add_argument(
        "--video",
        "-v",
        "--url",
        "-u",
        dest="video",
        type=str,
        help="Ссылка на YouTube, Google Drive или путь к локальному файлу (MP4, MOV и др.).",
    )
    parser.add_argument(
        "--project", "-P", type=str, default="superweird", help="Папка проекта в reports/."
    )
    parser.add_argument(
        "--skill",
        "--preset",
        "-p",
        dest="skill_id",
        type=str,
        default="full_ux_audit",
        help="ID навыка/пресета (например, full_ux_audit, cinematic_editing, ad_hooks_retention).",
    )
    parser.add_argument(
        "--questions", "-q", nargs="+", help="Список кастомных вопросов разработчика к видео."
    )
    parser.add_argument("--context", "-c", type=str, default="", help="Контекст о видео.")
    parser.add_argument(
        "--model", "-m", choices=VideoAnalyzer.SUPPORTED_MODELS, default="gemini-3.5-flash"
    )
    parser.add_argument(
        "--meta", action="store_true", help="Запустить сводный мета-анализ всех отчётов проекта."
    )
    parser.add_argument(
        "--interactive", "-i", action="store_true", help="Запуск в интерактивном режиме."
    )

    args = parser.parse_args()

    if not os.getenv("GEMINI_API_KEY"):
        console.print("\n[bold red]⚠️ Ошибка: Переменная GEMINI_API_KEY не задана в .env![/bold red]\n")
        sys.exit(1)

    if args.interactive or (not args.video and not args.meta):
        params = interactive_mode()
        if params.get("mode") == "meta":
            args.meta = True
            args.project = params["project"]
            focus_q = params.get("focus_question", "")
        else:
            args.video = params["video"]
            args.project = params["project"]
            chosen_skill = params["skill"]
            args.context = params["context"]
            args.questions = params["custom_questions"]
            args.model = params["model"]
            focus_q = ""
    else:
        chosen_skill = SkillManager.get_skill(args.skill_id)
        focus_q = ""

    # РЕЖИМ 1: СВОДНЫЙ МЕТА-АНАЛИЗ ВСЕХ ОТЧЕТОВ ПРОЕКТА
    if args.meta:
        console.print(f"\n[cyan]Запуск сводного мета-анализа по проекту [bold]{args.project}[/bold]...[/cyan]")
        reports = ProjectManager.list_reports(args.project)
        if not reports:
            console.print(f"[red]В папке reports/{args.project}/ нет отчетов![/red]")
            sys.exit(1)

        reports_payload = []
        for rep in reports:
            with open(rep["path"], "r", encoding="utf-8") as f:
                reports_payload.append({"filename": rep["filename"], "content": f.read()})

        meta_analyzer = MetaAnalyzer(model=args.model)
        proj_obj = ProjectManager.get_project(args.project) or ProjectManager.create_project(args.project)

        with console.status(
            f"[bold green]Gemini синтезирует {len(reports_payload)} отчётов...[/bold green]",
            spinner="dots",
        ):
            res = meta_analyzer.analyze_reports(
                project=proj_obj,
                reports_data=reports_payload,
                focus_question=focus_q,
            )

        saved = ProjectManager.save_meta_recap(args.project, res.content)
        console.print("\n" + "=" * 80 + "\n")
        console.print(
            Panel(Markdown(res.content), title=f"🧠 Сводный аудит: {args.project}", border_style="magenta")
        )
        console.print(f"\n[bold green]✅ Сводный отчет сохранен в:[/bold green] [cyan]{saved}[/cyan]")
        return

    # РЕЖИМ 2: АНАЛИЗ ОТДЕЛЬНОГО ВИДЕО
    console.print(f"\n[cyan]Подготовка к анализу видео [bold]{args.video}[/bold]...[/cyan]")
    console.print(f"• Навык (Skill): [bold magenta]{chosen_skill.title}[/bold magenta]")
    console.print(f"• Модель: [bold green]{args.model}[/bold green]")

    prompt = SkillManager.build_prompt(
        skill=chosen_skill,
        custom_questions=args.questions or [],
        context=args.context,
    )

    try:
        analyzer = VideoAnalyzer(model=args.model)
        with console.status(
            "[bold green]Gemini выполняет анализ видео через Agentic Video Understanding...[/bold green]",
            spinner="dots",
        ):
            result = analyzer.analyze(
                video_source=args.video,
                prompt=prompt,
                progress_callback=lambda msg: console.print(f"[dim]{msg}[/dim]"),
            )

    except Exception as e:
        console.print(f"\n[bold red]Ошибка:[/bold red] {e}")
        sys.exit(1)

    # Формируем заголовок отчёта
    meta = result.video_meta or {}
    v_title = meta.get("title", Path(args.video).name)
    ch_name = meta.get("channel_name", "Видеоматериал")
    ch_url = meta.get("channel_url", "")
    views_str = meta.get("views_formatted", "—")

    header_lines = [
        f"# 📊 Анализ видео: {v_title}\n",
        f"- **Навык**: {chosen_skill.title}",
        f"- **Источник**: [{v_title}]({result.video_url})" if result.video_url.startswith("http") else f"- **Источник**: {v_title} ({ch_name})",
        f"- **Канал / Хранилище**: [{ch_name}]({ch_url})" if ch_url else f"- **Канал / Хранилище**: {ch_name}",
        f"- **Параметры**: {views_str}",
        f"- **Дата анализа**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- **Модель**: {result.model}",
    ]
    if result.total_tokens:
        header_lines.append(f"- **Использовано токенов**: {result.total_tokens:,}")
    header_lines.append("\n---\n")

    full_report = "\n".join(header_lines) + "\n" + result.output_text

    console.print("\n" + "=" * 80 + "\n")
    console.print(Panel(Markdown(full_report), title=f"📊 Отчет анализа: {v_title}", border_style="green"))

    # Сохраняем в reports/<project>/
    safe_tag = (
        VideoAnalyzer.extract_youtube_video_id(args.video)
        or (GoogleDriveDownloader.extract_file_id(args.video) if "drive.google.com" in args.video else Path(args.video).stem)
        or "video"
    )
    clean_tag = "".join(c for c in safe_tag if c.isalnum() or c in "_-")[:30]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"recap_{clean_tag}_{ts}.md"
    saved_path = ProjectManager.save_report(args.project, filename, full_report)

    console.print(f"\n[bold green]✅ Отчет успешно сохранен в проект:[/bold green] [cyan]{saved_path}[/cyan]")


if __name__ == "__main__":
    main()
