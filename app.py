"""
Веб-интерфейс для анализа видео плейтестов через Gemini Agentic Video Understanding
и сводного кросс-анализа (Мета-рекапа) всех отчётов по проектам.
Поддерживает источники: YouTube, локальные видеофайлы (MP4, MOV, MKV и др.) и Google Drive.
Включает конструктор пользовательских скиллов (Skills / Presets) для анализа любого контента.
Запуск: streamlit run app.py
"""

import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
import streamlit as st
from dotenv import load_dotenv

from analyzer import VideoAnalyzer, AnalysisResult
from drive_downloader import GoogleDriveDownloader
from meta_analyzer import MetaAnalyzer
from projects import ProjectManager, Project
from skills import Skill, SkillManager
from youtube_meta import fetch_youtube_metadata

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

# Загружаем переменные окружения и инициализируем проекты и скиллы
load_dotenv()
ProjectManager.init()
SkillManager.init()

st.set_page_config(
    page_title="Game & Video Intelligence Hub (Gemini Agentic)",
    page_icon="🎮",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS для аккуратного UI
st.markdown(
    """
    <style>
    .main-header {
        font-size: 2.1rem;
        font-weight: 700;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #888;
        margin-bottom: 1.2rem;
    }
    .project-badge {
        display: inline-block;
        padding: 0.35rem 0.8rem;
        border-radius: 8px;
        background-color: #2b313e;
        color: #e0e0e0;
        font-weight: 500;
        font-size: 0.95rem;
        margin-bottom: 1rem;
    }
    .channel-tag {
        background-color: #ff4b4b20;
        color: #ff4b4b;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    .views-tag {
        background-color: #4b8bff20;
        color: #4b8bff;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    .skill-card {
        border: 1px solid #333;
        border-radius: 8px;
        padding: 12px;
        margin-bottom: 10px;
        background-color: #1e222a;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- Боковая панель: Папки проектов в reports/ и Настройки ---
with st.sidebar:
    st.header("🎮 Проекты (Игры)")

    projects = ProjectManager.list_projects()
    project_names = [p.name for p in projects]

    # Индекс текущего выбранного проекта
    if (
        "current_project_name" not in st.session_state
        or st.session_state["current_project_name"] not in project_names
    ):
        st.session_state["current_project_name"] = (
            "superweird" if "superweird" in project_names else project_names[0]
        )

    current_idx = (
        project_names.index(st.session_state["current_project_name"])
        if st.session_state["current_project_name"] in project_names
        else 0
    )

    selected_proj_idx = st.selectbox(
        "Текущая игра (папка в reports/):",
        options=range(len(projects)),
        format_func=lambda i: f"📁 {projects[i].name}",
        index=current_idx,
    )
    active_project = projects[selected_proj_idx]
    st.session_state["current_project_name"] = active_project.name

    # Создание новой папки проекта
    with st.expander("➕ Новая игра (создать папку в reports/)"):
        with st.form("new_project_form", clear_on_submit=True):
            new_folder_name = st.text_input(
                "Имя папки (игры):", placeholder="Например: Superweird или CyberDungeon"
            )
            create_btn = st.form_submit_button("Создать папку")

            if create_btn:
                if not new_folder_name.strip():
                    st.error("Укажите имя папки!")
                else:
                    new_proj = ProjectManager.create_project(new_folder_name.strip())
                    st.session_state["current_project_name"] = new_proj.name
                    st.success(f"Папка 'reports/{new_proj.name}' создана!")
                    st.rerun()

    st.markdown("---")
    st.header("⚙️ Конфигурация API")

    env_api_key = os.getenv("GEMINI_API_KEY", "")
    api_key_input = st.text_input(
        "Gemini API Key",
        value=env_api_key,
        type="password",
        help="Ключ для работы с Gemini Interactions API и File API.",
    )

    selected_model = st.selectbox(
        "Модель анализа:",
        options=VideoAnalyzer.SUPPORTED_MODELS,
        index=0,
        help="gemini-3.5-flash оптимальна для Free Tier квот. gemini-3.8-flash — максимальная детализация.",
    )

    st.caption("ℹ️ *Совет:* Если у вас Free Tier без биллинга, используйте `gemini-3.5-flash`.")


# --- Основная область ---
st.markdown('<div class="main-header">🎮 Game & Video Intelligence Hub</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-header">Анализ видео через <b>Gemini Agentic Video Understanding</b> (YouTube, локальные файлы, Google Drive) и конструктор скиллов</div>',
    unsafe_allow_html=True,
)

st.markdown(
    f'<div class="project-badge">📁 Активный проект: <b>{active_project.name}</b> (путь: reports/{active_project.name}/)</div>',
    unsafe_allow_html=True,
)

# Вкладки
tab_meta, tab_video, tab_skills, tab_reports = st.tabs([
    "🧠 Сводный Мета-рекап (Кросс-анализ)",
    "📹 Анализ видео",
    "🛠 Конструктор скиллов (Пресеты)",
    "📁 Отчёты проекта",
])


# ==========================================
# ВКЛАДКА 1: СВОДНЫЙ МЕТА-РЕКАП (КРОСС-АНАЛИЗ)
# ==========================================
with tab_meta:
    st.subheader(f"🧠 Сводный UX-синтез плейтестов игры «{active_project.name}»")
    st.markdown(
        """
        Мета-рекап объединяет данные **всех плейтестов этой игры**, сопоставляет реакции игроков и выявляет:
        - 🚨 **Повторяющиеся затыки** (проблемы, с которыми столкнулись 2+ игрока).
        - 🗺 **Карту точек отвала (Chokepoints)**, где чаще всего проседает темп или дропают игру.
        - 💎 **Ядро удовольствия** — что игроки стабильно хвалят и что ни в коем случае нельзя ломать при патчах.
        - ⚖️ **Матрицу «Частота vs Импакт»** и конкретный бэклог задач для разработчиков.
        """
    )

    existing_reports = ProjectManager.list_reports(active_project.name)

    if not existing_reports:
        st.warning(
            f"В папке `reports/{active_project.name}/` пока нет отчётов. "
            "Перейдите на вкладку '📹 Анализ видео' и проанализируйте летсплеи или плейтесты игроков."
        )
    else:
        st.write(f"Найдено доступных отчётов по игре: **{len(existing_reports)}**")

        # Выбор отчетов для анализа
        selected_reports_files = []
        with st.expander(
            "📋 Выберите отчёты для включения в сводный анализ (по умолчанию выбраны все)",
            expanded=True,
        ):
            for r in existing_reports:
                ch_name = r.get("channel_name") or "Канал"
                views_str = r.get("views") or ""
                views_badge = f" | 👀 {views_str}" if views_str else ""
                title_str = r.get("video_title") or r["filename"]

                label = f"📺 **{ch_name}**: «{title_str}»{views_badge} ({r['created_at']})"
                cb = st.checkbox(label, value=True, key=f"rep_cb_{r['filename']}")
                if cb:
                    selected_reports_files.append(r)

        c_ctx, c_q = st.columns([1, 1])
        with c_ctx:
            game_context_meta = st.text_area(
                "Краткий контекст игры (необязательно):",
                placeholder="Например: гибрид автоматизации, тетриса и рогалика. Игрок строит цепочки снабжения для хламоботов.",
                height=90,
                key="meta_game_ctx",
            )
        with c_q:
            focus_question = st.text_area(
                "Особый вопрос для сводки (необязательно):",
                placeholder="Например: На что чаще всего жаловались в обучении? Почему игроки путались в логистике тайлов?",
                height=90,
                key="meta_focus_q",
            )

        run_meta_btn = st.button(
            "🚀 Запустить сводный кросс-анализ всех отчётов",
            type="primary",
            key="run_meta_btn",
        )

        if run_meta_btn:
            if not selected_reports_files:
                st.error("Выберите хотя бы один отчёт для анализа.")
            elif not api_key_input:
                st.error("Пожалуйста, укажите GEMINI_API_KEY в боковой панели.")
            else:
                reports_payload = []
                for rep in selected_reports_files:
                    try:
                        with open(rep["path"], "r", encoding="utf-8") as f:
                            reports_payload.append(
                                {"filename": rep["filename"], "content": f.read()}
                            )
                    except Exception as e:
                        st.warning(f"Не удалось прочитать {rep['filename']}: {e}")

                with st.spinner(
                    f"🧠 Gemini синтезирует данные из {len(reports_payload)} плейтестов, ищет повторяющиеся боли и строит бэклог..."
                ):
                    try:
                        meta_analyzer = MetaAnalyzer(
                            api_key=api_key_input, model=selected_model
                        )
                        meta_res = meta_analyzer.analyze_reports(
                            project=active_project,
                            reports_data=reports_payload,
                            focus_question=focus_question,
                        )

                        # Сохраняем сводный отчет в папку reports/<project>/
                        saved_path = ProjectManager.save_meta_recap(
                            project_name=active_project.name, content=meta_res.content
                        )

                        st.session_state["latest_meta_recap"] = meta_res.content
                        st.session_state["latest_meta_file"] = saved_path.name
                        st.success(
                            f"✅ Сводный мета-анализ по {len(reports_payload)} плейтестам построен и сохранен в reports/{active_project.name}/{saved_path.name}!"
                        )

                    except Exception as e:
                        st.error(str(e))

        # Отображение готового мета-рекапа
        if "latest_meta_recap" in st.session_state:
            st.markdown("---")
            st.subheader(f"📊 Сводный аудит игры: {active_project.name}")

            st.download_button(
                label="📥 Скачать сводный отчёт (Markdown .md)",
                data=st.session_state["latest_meta_recap"],
                file_name=st.session_state.get("latest_meta_file", "meta_recap.md"),
                mime="text/markdown",
                key="download_meta_btn",
            )

            st.markdown(st.session_state["latest_meta_recap"])

        # Список ранее сохранённых мета-рекапов
        saved_recaps = ProjectManager.list_meta_recaps(active_project.name)
        if saved_recaps:
            st.markdown("---")
            st.markdown("### 📚 Ранее сгенерированные мета-рекапы этого проекта")
            for sr in saved_recaps:
                with st.expander(f"📄 {sr['filename']} от {sr['created_at']}"):
                    with open(sr["path"], "r", encoding="utf-8") as srf:
                        rc_text = srf.read()
                    st.markdown(rc_text)


# ==========================================
# ВКЛАДКА 2: АНАЛИЗ ОТДЕЛЬНОГО ВИДЕО
# ==========================================
with tab_video:
    col_input, col_preview = st.columns([1.1, 0.9])

    # Переменные для итогового источника видео
    target_video_source = ""
    target_source_type = "youtube"
    preview_local_file = None

    with col_input:
        source_mode = st.radio(
            "Источник видеоматериала:",
            options=["📺 YouTube ссылка", "📁 Локальный видеофайл", "☁️ Google Drive"],
            horizontal=True,
            key="source_mode_radio",
        )

        if source_mode == "📺 YouTube ссылка":
            target_source_type = "youtube"
            youtube_url = st.text_input(
                "🔗 Ссылка на YouTube видео:",
                placeholder="https://www.youtube.com/watch?v=... или https://youtu.be/...",
                key="yt_url_input",
            )
            target_video_source = youtube_url.strip()

        elif source_mode == "📁 Локальный видеофайл":
            target_source_type = "local"
            local_select_type = st.radio(
                "Способ указания локального файла:",
                options=["Загрузить через браузер (до 2 ГБ)", "Указать путь к файлу на диске"],
                horizontal=True,
                key="local_select_type",
            )

            if local_select_type == "Загрузить через браузер (до 2 ГБ)":
                uploaded_file = st.file_uploader(
                    "Выберите видеозапись (MP4, MOV, MKV, WebM, AVI):",
                    type=["mp4", "mov", "mkv", "webm", "avi"],
                    key="local_file_uploader",
                )
                if uploaded_file is not None:
                    # Сохраняем загруженный файл в кэш reports/.cache/
                    cache_dir = Path("reports/.cache")
                    cache_dir.mkdir(parents=True, exist_ok=True)
                    saved_path = cache_dir / uploaded_file.name
                    with open(saved_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                    target_video_source = str(saved_path)
                    preview_local_file = str(saved_path)
                    st.success(f"Файл сохранен: `{uploaded_file.name}` ({round(uploaded_file.size / (1024*1024), 1)} MB)")
            else:
                local_path_input = st.text_input(
                    "Абсолютный или относительный путь к видеофайлу на компьютере:",
                    placeholder="/Users/username/Videos/gameplay_session.mp4",
                    key="local_disk_path_input",
                )
                target_video_source = local_path_input.strip()
                if target_video_source and Path(target_video_source).exists():
                    preview_local_file = target_video_source

        elif source_mode == "☁️ Google Drive":
            target_source_type = "gdrive"
            gdrive_url_input = st.text_input(
                "🔗 Ссылка на видео в Google Drive:",
                placeholder="https://drive.google.com/file/d/.../view?usp=sharing",
                help="Убедитесь, что доступ к видео открыт: 'Все, у кого есть ссылка' (Просмотр).",
                key="gdrive_url_input",
            )
            target_video_source = gdrive_url_input.strip()

        st.markdown("---")

        # Выбор скилла / пресета из SkillManager
        available_skills = SkillManager.list_skills()
        skill_labels = [
            f"{s.title} {'[Встроенный]' if s.is_builtin else '[Свой скилл]'}"
            for s in available_skills
        ]

        selected_skill_index = st.selectbox(
            "📋 Навык / Пресет анализа (Skill):",
            options=range(len(available_skills)),
            format_func=lambda i: skill_labels[i],
            key="skill_select",
        )
        active_skill = available_skills[selected_skill_index]
        st.caption(f"ℹ️ {active_skill.description}")

        # Блок параметров отсмотра выбранного скилла
        criteria_list = (
            active_skill.extract_criteria_sections()
            if hasattr(active_skill, "extract_criteria_sections")
            else Skill.extract_criteria_sections(active_skill)
            if hasattr(Skill, "extract_criteria_sections")
            else []
        )
        if criteria_list:
            with st.container():
                st.markdown("##### 🔍 Параметры отсмотра видео:")
                for c in criteria_list:
                    st.markdown(f"• **{c}**")

        with st.expander("📄 Развернуть полный текст критериев скилла"):
            st.text_area(
                "Критерии анализа (Prompt Focus):",
                value=active_skill.prompt_focus,
                height=160,
                disabled=True,
                key=f"view_pf_{active_skill.id}",
            )

        with st.expander("🛠 Дополнительный контекст видео (необязательно)"):
            user_context = st.text_area(
                "Контекст для модели:",
                placeholder="Опишите контекст: правила игры, жанр, цель видео, специфику проекта...",
                height=90,
                key="context_input",
            )

        with st.expander("❓ Специфические вопросы для проверки (по одному на строку)"):
            custom_questions_text = st.text_area(
                "Ваши вопросы:",
                placeholder="Понял ли игрок механику крафта?\nСоблюдается ли правило 180 градусов в диалоге?\nКакова была реакция на 05:20?",
                height=110,
                key="questions_input",
            )

        run_video_btn = st.button("🚀 Начать анализ видео", type="primary", key="run_video_btn")

    # Колонка предпросмотра видео
    with col_preview:
        if target_source_type == "youtube":
            video_id = (
                VideoAnalyzer.extract_youtube_video_id(target_video_source)
                if target_video_source
                else None
            )
            if video_id:
                st.video(f"https://www.youtube.com/watch?v={video_id}")
                yt_meta = fetch_youtube_metadata(target_video_source)
                st.markdown(
                    f"**{yt_meta.get('title')}**  \n"
                    f"<span class='channel-tag'>📺 {yt_meta.get('channel_name')}</span> &nbsp; "
                    f"<span class='views-tag'>👀 {yt_meta.get('views_formatted')} просмотров</span>",
                    unsafe_allow_html=True,
                )
            else:
                st.info("📺 Вставьте ссылку на YouTube видео, чтобы здесь появился плеер для сверки с таймкодами.")

        elif target_source_type == "local":
            if preview_local_file and Path(preview_local_file).exists():
                st.video(preview_local_file)
                fsize = round(Path(preview_local_file).stat().st_size / (1024 * 1024), 1)
                st.markdown(
                    f"**📁 {Path(preview_local_file).name}**  \n"
                    f"<span class='views-tag'>Размер: {fsize} MB</span>",
                    unsafe_allow_html=True,
                )
            else:
                st.info("📁 Выберите или укажите локальный видеофайл — встроенный плеер отобразит его здесь.")

        elif target_source_type == "gdrive":
            file_id = (
                GoogleDriveDownloader.extract_file_id(target_video_source)
                if target_video_source
                else None
            )
            if file_id:
                st.success(f"☁️ Распознан Google Drive ID: `{file_id}`")
                st.caption(
                    "При запуске анализа видео будет автоматически скачано и загружено в Gemini File API."
                )
            else:
                st.info("☁️ Вставьте ссылку на Google Drive (доступную для просмотра по ссылке).")

    # Логика запуска анализа видео
    if run_video_btn:
        if not target_video_source:
            st.error("Пожалуйста, укажите источник видеоматериала.")
        elif not api_key_input:
            st.error("Пожалуйста, укажите GEMINI_API_KEY в боковой панели или файле .env.")
        else:
            custom_questions = [
                q.strip() for q in custom_questions_text.split("\n") if q.strip()
            ]

            final_prompt = SkillManager.build_prompt(
                skill=active_skill,
                custom_questions=custom_questions,
                context=user_context,
            )

            with st.status("🚀 Подготовка и запуск анализа видео...", expanded=True) as status_box:
                try:
                    def update_status_msg(msg: str):
                        status_box.write(msg)

                    analyzer = VideoAnalyzer(api_key=api_key_input, model=selected_model)
                    result = analyzer.analyze(
                        video_source=target_video_source,
                        prompt=final_prompt,
                        source_type=target_source_type,
                        progress_callback=update_status_msg,
                    )

                    status_box.update(
                        label="✅ Анализ видео успешно завершён!",
                        state="complete",
                        expanded=False,
                    )

                    # Формируем заголовок отчёта
                    meta = result.video_meta or {}
                    v_title = meta.get("title", Path(target_video_source).name if target_source_type == "local" else "Видео")
                    ch_name = meta.get("channel_name", "Видеоматериал")
                    ch_url = meta.get("channel_url", "")
                    views_str = meta.get("views_formatted", "—")

                    header_lines = [
                        f"# 📊 Анализ видео: {v_title}\n",
                        f"- **Навык (Skill)**: {active_skill.title}",
                        f"- **Источник**: [{v_title}]({result.video_url})" if result.video_url.startswith("http") else f"- **Источник**: {v_title} ({ch_name})",
                        f"- **Канал / Хранилище**: [{ch_name}]({ch_url})" if ch_url else f"- **Канал / Хранилище**: {ch_name}",
                        f"- **Параметры**: {views_str}",
                        f"- **Дата анализа**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                        f"- **Модель**: {result.model}",
                    ]
                    if result.total_tokens:
                        header_lines.append(f"- **Использовано токенов**: {result.total_tokens:,}")
                    header_lines.append("\n---\n")

                    full_report_text = "\n".join(header_lines) + "\n" + result.output_text

                    # Сохраняем отчет в проект reports/<active_project.name>/
                    safe_vid_tag = (
                        VideoAnalyzer.extract_youtube_video_id(target_video_source)
                        or (GoogleDriveDownloader.extract_file_id(target_video_source) if target_source_type == "gdrive" else Path(target_video_source).stem)
                        or "video"
                    )
                    clean_tag = "".join(c for c in safe_vid_tag if c.isalnum() or c in "_-")[:30]
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"recap_{clean_tag}_{ts}.md"

                    ProjectManager.save_report(
                        project_name=active_project.name,
                        filename=filename,
                        content=full_report_text,
                    )

                    st.session_state["last_video_report"] = full_report_text
                    st.session_state["last_video_meta"] = {
                        "video_url": result.video_url,
                        "title": v_title,
                        "channel_name": ch_name,
                        "views": views_str,
                        "model": result.model,
                        "tokens": result.total_tokens,
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "skill": active_skill.title,
                    }
                    st.success(f"✅ Анализ сохранён в `reports/{active_project.name}/{filename}`!")

                except Exception as e:
                    status_box.update(label="❌ Ошибка при анализе", state="error", expanded=True)
                    st.error(str(e))

    # Вывод последнего готового отчета
    if "last_video_report" in st.session_state:
        st.markdown("---")
        st.subheader("📊 Результаты анализа видео")
        meta = st.session_state.get("last_video_meta", {})

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Источник", meta.get("channel_name", "—"))
        with c2:
            st.metric("Параметры", meta.get("views", "—"))
        with c3:
            st.metric("Токенов", f"{meta.get('tokens', 0):,}" if meta.get("tokens") else "—")
        with c4:
            st.metric("Скилл", meta.get("skill", active_skill.title))

        st.download_button(
            label="📥 Скачать отчёт (Markdown .md)",
            data=st.session_state["last_video_report"],
            file_name="video_recap.md",
            mime="text/markdown",
            key="download_last_video_btn",
        )
        st.markdown(st.session_state["last_video_report"])


# ==========================================
# ВКЛАДКА 3: КОНСТРУКТОР СКИЛЛОВ (ПРЕСЕТЫ)
# ==========================================
with tab_skills:
    st.subheader("🛠 Конструктор навыков анализа видео (Skills / Presets)")
    st.markdown(
        """
        Создавайте и настраивайте **собственные экспертные скиллы** для любого типа видео:
        от классического киномонтажа и анализа рекламы до разбора лекций и спортивной техники.
        """
    )

    skill_tab_ai, skill_tab_catalog, skill_tab_create, skill_tab_import, skill_tab_llm = st.tabs([
        "✨ ИИ-генератор скилла (Gemini)",
        "📋 Каталог активных скиллов",
        "✍️ Ручное создание скилла",
        "📥 Импорт из JSON",
        "🤖 Инструкция для внешних LLM",
    ])

    # 1. ИИ-Генератор скилла через Gemini
    with skill_tab_ai:
        st.markdown("##### 🪄 Создание скилла с помощью Gemini API")
        st.markdown(
            """
            Опишите своими словами область анализа (киномонтаж, лекции, стримы, рекламные ролики, фитнес).
            При необходимости прикрепите файлы документации, регламента или экспорт из **NotebookLM** (TXT, MD, PDF) — 
            Gemini сформирует экспертный пресет с чёткими параметрами отсмотра!
            """
        )

        ai_topic_desc = st.text_area(
            "💡 Опишите область или задачу для навыка:",
            placeholder="Например: Аудит обучающих лекций и вебинаров. Оценить понятность объяснения, визуализацию тезисов на слайдах, динамику речи лектора и моменты потери внимания аудитории.",
            height=110,
            key="ai_topic_desc_input",
        )

        c_file, c_manual = st.columns([1, 1])
        with c_file:
            ai_kb_files = st.file_uploader(
                "📎 Прикрепить базу знаний / экспорт NotebookLM (TXT, MD, PDF):",
                type=["txt", "md", "pdf"],
                accept_multiple_files=True,
                key="ai_kb_files_upload",
            )
        with c_manual:
            ai_kb_text = st.text_area(
                "Или вставьте текст регламента / заметок вручную (необязательно):",
                placeholder="Правила оценки, глоссарий терминов, критерии приёмки...",
                height=90,
                key="ai_kb_text_input",
            )

        gen_skill_btn = st.button("✨ Сгенерировать скилл через Gemini", type="primary", key="gen_skill_btn")

        if gen_skill_btn:
            if not api_key_input:
                st.error("Пожалуйста, укажите GEMINI_API_KEY в боковой панели!")
            elif not ai_topic_desc.strip():
                st.error("Пожалуйста, опишите задачу для навыка в текстовом поле!")
            else:
                with st.spinner("🤖 Gemini анализирует запрос и проектирует экспертный скилл..."):
                    try:
                        attached_parts = []
                        kb_texts = []
                        if ai_kb_text.strip():
                            kb_texts.append(ai_kb_text.strip())

                        if ai_kb_files:
                            for f in ai_kb_files:
                                fname = f.name.lower()
                                if fname.endswith(".pdf"):
                                    if types and hasattr(types.Part, "from_bytes"):
                                        attached_parts.append(
                                            types.Part.from_bytes(data=f.read(), mime_type="application/pdf")
                                        )
                                else:
                                    raw_text = f.read().decode("utf-8", errors="ignore")
                                    kb_texts.append(f"--- Документ: {f.name} ---\n{raw_text}")

                        client = genai.Client(api_key=api_key_input)
                        generated_skill = SkillManager.generate_skill_with_ai(
                            client=client,
                            model=selected_model,
                            topic_description=ai_topic_desc,
                            knowledge_base_text="\n\n".join(kb_texts) if kb_texts else None,
                            attached_parts=attached_parts if attached_parts else None,
                        )
                        st.session_state["preview_generated_skill"] = generated_skill
                        st.success(f"🎉 Скилл '{generated_skill.title}' успешно сгенерирован!")

                    except Exception as e:
                        st.error(f"Ошибка при генерации скилла через Gemini: {e}")

        # Предпросмотр сгенерированного скилла
        if "preview_generated_skill" in st.session_state:
            ps = st.session_state["preview_generated_skill"]
            st.markdown("---")
            st.subheader(f"Предпросмотр сгенерированного скилла: {ps.title}")
            st.info(f"**ID:** `{ps.id}` | **Категория:** `{ps.category}`\n\n**Описание:** {ps.description}")

            crit = ps.extract_criteria_sections()
            if crit:
                st.markdown("##### 🔍 Заложенные параметры отсмотра видео:")
                for c in crit:
                    st.markdown(f"• **{c}**")

            with st.expander("📄 Полный текст сгенерированных инструкций"):
                st.markdown(f"**Системная роль:**\n```\n{ps.system_role}\n```")
                st.markdown(f"**Критерии (Prompt Focus):**\n```\n{ps.prompt_focus}\n```")

            c_save, c_discard = st.columns([1, 4])
            with c_save:
                if st.button("💾 Добавить в библиотеку скиллов", type="primary", key="save_gen_skill_btn"):
                    SkillManager.save_skill(ps)
                    del st.session_state["preview_generated_skill"]
                    st.success(f"✅ Скилл '{ps.title}' успешно сохранён и добавлен на вкладку '📹 Анализ видео'!")
                    st.rerun()
            with c_discard:
                if st.button("❌ Сбросить", key="discard_gen_skill_btn"):
                    del st.session_state["preview_generated_skill"]
                    st.rerun()

    # 2. Каталог скиллов
    with skill_tab_catalog:
        all_skills = SkillManager.list_skills()
        st.write(f"Всего доступно навыков: **{len(all_skills)}**")

        for s in all_skills:
            badge = "🔒 Встроенный системный" if s.is_builtin else "🌟 Пользовательский (skills/)"
            category_icon = {
                "gamedev": "🎮 Геймдев",
                "cinema": "🎬 Кинематограф",
                "marketing": "📢 Маркетинг",
                "education": "🎓 Образование",
                "general": "🌐 Общий",
            }.get(s.category, f"🏷 {s.category}")

            with st.expander(f"{s.title} &nbsp; ({badge} | {category_icon})"):
                st.markdown(f"**Описание:** {s.description}")
                st.markdown(f"**Системная роль (Persona):**\n```\n{s.system_role}\n```")

                if s.rules:
                    st.markdown("**Правила анализа:**")
                    for r in s.rules:
                        st.markdown(f"- {r}")

                st.markdown("**Критерии и структура анализа:**")
                st.text_area("Фокус промпта:", value=s.prompt_focus, height=180, key=f"focus_view_{s.id}", disabled=True)

                if not s.is_builtin:
                    col_del, col_exp = st.columns([1, 4])
                    with col_del:
                        if st.button("🗑 Удалить скилл", key=f"del_btn_{s.id}"):
                            SkillManager.delete_skill(s.id)
                            st.success(f"Скилл '{s.title}' удалён!")
                            st.rerun()
                    with col_exp:
                        st.download_button(
                            label="📥 Экспорт в JSON",
                            data=json.dumps(s.to_dict(), ensure_ascii=False, indent=2),
                            file_name=f"{s.id}.json",
                            mime="application/json",
                            key=f"dl_skill_{s.id}",
                        )

    # 2. Создание нового скилла
    with skill_tab_create:
        st.markdown("##### Заполните параметры нового навыка:")
        with st.form("create_skill_form"):
            c_id, c_title = st.columns([1, 2])
            with c_id:
                new_id = st.text_input("ID скилла (латиница snake_case):", placeholder="sports_technique")
            with c_title:
                new_title = st.text_input("Название скилла (с эмодзи):", placeholder="🏋️ Анализ техники в фитнесе")

            new_desc = st.text_input("Краткое описание:", placeholder="Разбор траектории движений, ошибок в осанке и таймингов.")
            new_cat = st.selectbox("Категория:", ["gamedev", "cinema", "marketing", "education", "sports", "general"])

            new_role = st.text_area(
                "Системная роль модели (Persona):",
                value="ТЫ — ВЕДУЩИЙ ЭКСПЕРТ В ЭТОЙ ОБЛАСТИ.\nТвоя цель — провести детальный экспертный аудит видео с помощью Agentic Video Understanding.",
                height=90,
            )

            new_rules_text = st.text_area(
                "Правила (по одному на строку):",
                value="ВСЕГДА указывай точные таймкоды [MM:SS] для каждого замечания.\nРазделяй объективные факты и экспертную критику.",
                height=90,
            )

            new_focus = st.text_area(
                "Критерии и структура анализа (Prompt Focus):",
                placeholder="1. Первое впечатление...\n2. Ошибки и недочеты...\n3. Рекомендации с таймкодами...",
                height=200,
            )

            submit_create = st.form_submit_button("💾 Сохранить и зарегистрировать скилл", type="primary")

            if submit_create:
                if not new_id.strip() or not new_title.strip() or not new_focus.strip():
                    st.error("Пожалуйста, заполните ID, Название и Критерии анализа.")
                else:
                    rules_list = [r.strip("- ") for r in new_rules_text.split("\n") if r.strip()]
                    created_skill = Skill(
                        id=new_id.strip(),
                        title=new_title.strip(),
                        description=new_desc.strip(),
                        category=new_cat,
                        system_role=new_role.strip(),
                        rules=rules_list,
                        prompt_focus=new_focus.strip(),
                        is_builtin=False,
                    )
                    SkillManager.save_skill(created_skill)
                    st.success(f"🎉 Скилл '{created_skill.title}' успешно создан и готов к использованию!")
                    st.rerun()

    # 3. Быстрый импорт из JSON
    with skill_tab_import:
        st.markdown("##### Вставьте JSON-спецификацию скилла:")
        st.caption("Вы можете сгенерировать JSON через ChatGPT, Claude или Gemini с помощью инструкции на соседней вкладке.")

        import_json_text = st.text_area(
            "JSON скилла:",
            placeholder='{\n  "id": "podcast_interview_review",\n  "title": "🎙 Аудит подкастов и интервью",\n  ...\n}',
            height=250,
            key="import_json_input",
        )

        if st.button("📥 Импортировать скилл", type="primary", key="import_skill_btn"):
            if not import_json_text.strip():
                st.error("Вставьте текст JSON.")
            else:
                try:
                    imp_skill = SkillManager.import_from_json(import_json_text)
                    st.success(f"✅ Скилл '{imp_skill.title}' успешно импортирован в skills/{imp_skill.id}.json!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Ошибка при валидации JSON: {e}")

    # 4. Инструкция для LLM
    with skill_tab_llm:
        st.markdown("##### 🤖 Как быстро создать скилл с помощью любой нейросети")
        st.markdown(
            """
            Скопируйте мета-промпт ниже, вставьте его в **ChatGPT**, **Claude** или **Gemini**,
            укажите свою задачу (например, *«Анализ стримов по Dota 2»* или *«Разбор лекций по физике»*).
            Полученный от нейросети JSON вставьте на вкладку **«Импорт из JSON»**.
            """
        )

        meta_prompt_text = """Ты — ведущий инженер промптов для мультимодальных систем анализа видео (Gemini Agentic Video Understanding).
Твоя задача — создать специализированный навык (Skill / Preset) для инструмента RecapVideo в формате строгого JSON.

Моя тема/задача для анализа видео:
[УКАЖИТЕ ВАШУ ТЕМУ ЗДЕСЬ, например: «Анализ киномонтажа по правилам Голливуда» или «Анализ рекламных Shorts»]

Сформируй ответ ТОЛЬКО в виде одного блока JSON по следующей схеме:

{
  "id": "латинский_id_в_snake_case",
  "title": "Эмодзи + Название навыка на русском языке",
  "description": "Краткое описание (1-2 предложения)",
  "category": "одна из категорий: cinema | gamedev | marketing | education | sports | general",
  "system_role": "ТЫ — ВЕДУЩИЙ ЭКСПЕРТ В ЭТОЙ ОБЛАСТИ. Твоя цель — провести детальный экспертный аудит прикрепленного видео с помощью агентского анализа видео (Agentic Video Understanding). ДИНАМИЧЕСКИ исследуй ключевые моменты таймлайна, сопоставляй происходящее на экране со звуком и речью.",
  "rules": [
    "ВСЕГДА указывай точные таймкоды в формате [MM:SS] или [HH:MM:SS] для каждого замечания, ошибки или сильного момента.",
    "Разделяй объективные факты (что видно/слышно) и экспертную критику.",
    "Давай только практические, выполнимые рекомендации."
  ],
  "prompt_focus": "Четко структурированные блоки критериев анализа (от 4 до 6 разделов) и финальный раздел с таблицей рекомендаций с таймкодами."
}"""

        st.code(meta_prompt_text, language="text")
        st.info("Полная документация также доступна в файле `SKILL_SPECIFICATION.md` в корне проекта.")


# ==========================================
# ВКЛАДКА 4: БАЗА ОТЧЁТОВ ПРОЕКТА
# ==========================================
with tab_reports:
    st.subheader(f"📁 Все отчёты плейтестов: reports/{active_project.name}/")

    proj_reports = ProjectManager.list_reports(active_project.name)
    if not proj_reports:
        st.info(
            f"В папке `reports/{active_project.name}/` пока нет отчётов. Создайте первый на вкладке '📹 Анализ видео'!"
        )
    else:
        st.write(f"Всего отчётов: **{len(proj_reports)}**")

        for rep in proj_reports:
            ch_name = rep.get("channel_name") or "Канал"
            views_str = rep.get("views") or ""
            views_label = f" | 👀 {views_str}" if views_str else ""
            title_str = rep.get("video_title") or rep["filename"]

            with st.expander(
                f"📝 {ch_name}: «{title_str}»{views_label} ({rep['created_at']} | {rep['size_kb']} KB)"
            ):
                with open(rep["path"], "r", encoding="utf-8") as rf:
                    content = rf.read()

                st.download_button(
                    label=f"📥 Скачать {rep['filename']}",
                    data=content,
                    file_name=rep["filename"],
                    mime="text/markdown",
                    key=f"dl_file_{rep['filename']}",
                )

                st.markdown(content)
