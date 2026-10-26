#!/usr/bin/env python3
"""
Консольная утилита (CLI) для анализа видео плейтестов и сводного мета-анализа по проектам.
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
from meta_analyzer import MetaAnalyzer
from projects import ProjectManager
from prompts import PRESETS, build_analysis_prompt
from youtube_meta import fetch_youtube_metadata

console = Console()


def interactive_mode():
    """Интерактивный мастер запуска анализа."""
    console.print(
        Panel.fit(
            "[bold cyan]🎮 Game UX & Playtest Video Recap Tool[/bold cyan]\n"
            "[dim]Powered by Gemini Agentic Video Understanding[/dim]",
            border_style="cyan"
        )
    )

    projects = ProjectManager.list_projects()
    proj_names = [p.name for p in projects]

    console.print(f"\n[bold]Существующие проекты (папки в reports/):[/bold] {', '.join(proj_names)}")
    project_name = Prompt.ask(
        "Выберите проект или введите новое имя игры",
        default=proj_names[0] if proj_names else "superweird"
    )

    action = Prompt.ask(
        "\nЧто вы хотите сделать?",
        choices=["1", "2"],
        default="1",
        show_choices=False
    )
    # 1: Анализ нового видео, 2: Сводный мета-рекап всех отчетов проекта

    if action == "2":
        return {
            "mode": "meta",
            "project": project_name,
            "focus_question": Prompt.ask("Особый вопрос для мета-анализа (Enter для пропуска)", default=""),
            "model": "gemini-3.5-flash"
        }

    # 1. Запрос ссылки на видео
    while True:
        url = Prompt.ask("\n[bold yellow]Введите ссылку на YouTube-видео плейтеста[/bold yellow]").strip()
        if not url:
            console.print("[red]Ссылка не может быть пустой![/red]")
            continue
        video_id = VideoAnalyzer.extract_youtube_video_id(url)
        if not video_id:
            if not Confirm.ask("[yellow]Не удалось определить стандартный YouTube ID. Продолжить с этой ссылкой?[/yellow]"):
                continue
        break

    # 2. Выбор пресета критериев
    console.print("\n[bold]Выберите фокус анализа:[/bold]")
    preset_keys = list(PRESETS.keys())
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("#", style="dim", width=4)
    table.add_column("Пресет", style="cyan")
    table.add_column("Описание", style="white")

    for i, key in enumerate(preset_keys, 1):
        preset = PRESETS[key]
        table.add_row(str(i), preset["title"], preset["description"])

    console.print(table)

    preset_choice = Prompt.ask(
        "Номер пресета",
        choices=[str(i) for i in range(1, len(preset_keys) + 1)],
        default="1"
    )
    chosen_preset = preset_keys[int(preset_choice) - 1]

    # 3. Контекст игры
    game_context = Prompt.ask(
        "\n[bold]Краткий контекст игры[/bold] (жанр, ключевые механики или Enter для пропуска)",
        default=""
    )

    # 4. Дополнительные вопросы
    custom_questions = []
    console.print("\n[bold]Специфические вопросы для плейтеста[/bold]:")
    while True:
        q = Prompt.ask(f"Вопрос #{len(custom_questions) + 1} (Enter чтобы закончить)", default="").strip()
        if not q:
            break
        custom_questions.append(q)

    # 5. Выбор модели
    model = Prompt.ask(
        "\n[bold]Модель Gemini[/bold]",
        choices=VideoAnalyzer.SUPPORTED_MODELS,
        default="gemini-3.5-flash"
    )

    return {
        "mode": "video",
        "url": url,
        "project": project_name,
        "preset": chosen_preset,
        "game_context": game_context,
        "custom_questions": custom_questions,
        "model": model,
        "output": None
    }


def main():
    parser = argparse.ArgumentParser(
        description="Game Playtest Video Recap & Meta-Analysis via Gemini Agentic Video Understanding."
    )
    parser.add_argument("--url", "-u", type=str, help="Ссылка на видео YouTube.")
    parser.add_argument("--project", "-P", type=str, default="superweird", help="Папка проекта в reports/.")
    parser.add_argument(
        "--preset",
        "-p",
        choices=list(PRESETS.keys()),
        default="full_ux_audit",
        help="Пресет критериев для анализа."
    )
    parser.add_argument("--questions", "-q", nargs="+", help="Список кастомных вопросов разработчика к видео.")
    parser.add_argument("--context", "-c", type=str, default="", help="Контекст об игре.")
    parser.add_argument("--model", "-m", choices=VideoAnalyzer.SUPPORTED_MODELS, default="gemini-3.5-flash")
    parser.add_argument("--meta", action="store_true", help="Запустить сводный мета-анализ всех отчётов проекта.")
    parser.add_argument("--interactive", "-i", action="store_true", help="Запуск в интерактивном режиме.")

    args = parser.parse_args()

    if not os.getenv("GEMINI_API_KEY"):
        console.print("\n[bold red]⚠️ Ошибка: Переменная GEMINI_API_KEY не задана в .env![/bold red]\n")
        sys.exit(1)

    if args.interactive or (not args.url and not args.meta):
        params = interactive_mode()
        if params.get("mode") == "meta":
            args.meta = True
            args.project = params["project"]
            focus_q = params.get("focus_question", "")
        else:
            args.url = params["url"]
            args.project = params["project"]
            args.preset = params["preset"]
            args.context = params["game_context"]
            args.questions = params["custom_questions"]
            args.model = params["model"]
            focus_q = ""
    else:
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
                reports_payload.append({
                    "filename": rep["filename"],
                    "content": f.read()
                })

        meta_analyzer = MetaAnalyzer(model=args.model)
        proj_obj = ProjectManager.get_project(args.project) or ProjectManager.create_project(args.project)

        with console.status(f"[bold green]Gemini синтезирует {len(reports_payload)} плейтестов...[/bold green]", spinner="dots"):
            res = meta_analyzer.analyze_reports(
                project=proj_obj,
                reports_data=reports_payload,
                focus_question=focus_q
            )

        saved = ProjectManager.save_meta_recap(args.project, res.content)
        console.print("\n" + "=" * 80 + "\n")
        console.print(Panel(Markdown(res.content), title=f"🧠 Сводный UX-аудит: {args.project}", border_style="magenta"))
        console.print(f"\n[bold green]✅ Сводный отчет сохранен в:[/bold green] [cyan]{saved}[/cyan]")
        return

    # РЕЖИМ 2: АНАЛИЗ ОТДЕЛЬНОГО ВИДЕО
    console.print(f"\n[cyan]Получение метаданных YouTube видео [bold]{args.url}[/bold]...[/cyan]")
    yt_meta = fetch_youtube_metadata(args.url)
    console.print(f"• Канал: [bold magenta]{yt_meta.get('channel_name')}[/bold magenta]")
    console.print(f"• Просмотры: [bold green]{yt_meta.get('views_formatted')}[/bold green]")
    console.print(f"• Название: {yt_meta.get('title')}")

    prompt = build_analysis_prompt(
        preset_key=args.preset,
        custom_questions=args.questions or [],
        game_context=args.context
    )

    try:
        analyzer = VideoAnalyzer(model=args.model)
        with console.status(
            "[bold green]Gemini выполняет Agentic Video Understanding... Сканирует таймлайн и речь игрока...[/bold green]",
            spinner="dots"
        ):
            result = analyzer.analyze(video_url=args.url, prompt=prompt)

    except Exception as e:
        console.print(f"\n[bold red]Ошибка:[/bold red] {e}")
        sys.exit(1)

    # Формируем заголовок с каналом и просмотрами
    header_lines = [
        "# 🎮 Отчет UX-анализа плейтеста\n",
        f"- **Видео**: [{yt_meta.get('title')}]({result.video_url})",
        f"- **Канал**: [{yt_meta.get('channel_name')}]({yt_meta.get('channel_url')})" if yt_meta.get('channel_url') else f"- **Канал**: {yt_meta.get('channel_name')}",
        f"- **Просмотры**: {yt_meta.get('views_formatted')} просмотров",
        f"- **Дата анализа**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- **Модель**: {result.model}",
    ]
    if result.total_tokens:
        header_lines.append(f"- **Использовано токенов**: {result.total_tokens:,}")
    header_lines.append("\n---\n")

    full_report = "\n".join(header_lines) + "\n" + result.output_text

    console.print("\n" + "=" * 80 + "\n")
    console.print(Panel(Markdown(full_report), title="📊 Отчет плейтеста", border_style="green"))

    # Сохраняем в reports/<project>/
    clean_vid = VideoAnalyzer.extract_youtube_video_id(args.url) or "video"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"recap_{clean_vid}_{ts}.md"
    saved_path = ProjectManager.save_report(args.project, filename, full_report)

    console.print(f"\n[bold green]✅ Отчет успешно сохранен в проект:[/bold green] [cyan]{saved_path}[/cyan]")


if __name__ == "__main__":
    main()
