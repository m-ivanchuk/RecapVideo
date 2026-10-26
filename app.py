"""
Веб-интерфейс для анализа видео плейтестов через Gemini Agentic Video Understanding
и сводного кросс-анализа (Мета-рекапа) всех отчётов по проектам игр.
Каждая папка в reports/ (например, reports/superweird) — это проект игры.
Запуск: streamlit run app.py
"""

import os
from datetime import datetime
from pathlib import Path
import streamlit as st
from dotenv import load_dotenv

from analyzer import VideoAnalyzer, AnalysisResult
from meta_analyzer import MetaAnalyzer
from projects import ProjectManager, Project
from prompts import PRESETS, build_analysis_prompt
from youtube_meta import fetch_youtube_metadata

# Загружаем переменные окружения и инициализируем проекты
load_dotenv()
ProjectManager.init()

st.set_page_config(
    page_title="Game Playtest Intelligence Hub (Gemini Agentic)",
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
        color: #888888;
        font-size: 1.05rem;
        margin-bottom: 1.2rem;
    }
    .project-badge {
        display: inline-block;
        background-color: #2b303c;
        color: #64b5f6;
        padding: 5px 14px;
        border-radius: 12px;
        font-size: 0.95rem;
        font-weight: 600;
        margin-bottom: 15px;
    }
    .channel-tag {
        display: inline-block;
        background-color: #3b2d54;
        color: #d1b3ff;
        padding: 2px 8px;
        border-radius: 6px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    .views-tag {
        display: inline-block;
        background-color: #1e3a2f;
        color: #69f0ae;
        padding: 2px 8px;
        border-radius: 6px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 48px;
        white-space: pre-wrap;
        font-weight: 600;
        font-size: 1rem;
        border-radius: 6px 6px 0px 0px;
        padding-top: 10px;
        padding-bottom: 10px;
    }
    .stButton>button {
        width: 100%;
        height: 3rem;
        font-size: 1.05rem;
        font-weight: bold;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# --- Боковая панель: Папки проектов в reports/ и Настройки ---
with st.sidebar:
    st.header("🎮 Проекты (Игры)")

    projects = ProjectManager.list_projects()
    project_names = [p.name for p in projects]

    # Индекс текущего выбранного проекта
    if "current_project_name" not in st.session_state or st.session_state["current_project_name"] not in project_names:
        st.session_state["current_project_name"] = "superweird" if "superweird" in project_names else project_names[0]

    current_idx = project_names.index(st.session_state["current_project_name"]) if st.session_state["current_project_name"] in project_names else 0

    selected_proj_idx = st.selectbox(
        "Текущая игра (папка в reports/):",
        options=range(len(projects)),
        format_func=lambda i: f"📁 {projects[i].name}",
        index=current_idx
    )
    active_project = projects[selected_proj_idx]
    st.session_state["current_project_name"] = active_project.name

    # Создание новой папки проекта
    with st.expander("➕ Новая игра (создать папку в reports/)"):
        with st.form("new_project_form", clear_on_submit=True):
            new_folder_name = st.text_input("Имя папки (игры):", placeholder="Например: Superweird или CyberDungeon")
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
        help="Получите ключ в Google AI Studio (aistudio.google.com)"
    )

    selected_model = st.selectbox(
        "Модель Gemini",
        options=VideoAnalyzer.SUPPORTED_MODELS,
        index=0,
        help="gemini-3.5-flash оптимальна для Free Tier; gemini-3.8-flash — флагман с глубоким рассуждением."
    )

    st.caption("ℹ️ *Совет:* Если у вас Free Tier без биллинга, используйте `gemini-3.5-flash`.")


# --- Основная область ---
st.markdown('<div class="main-header">🎮 Game Playtest Intelligence Hub</div>', unsafe_allow_html=True)
st.markdown(
    f'<div class="sub-header">Анализ игровых видео через <b>Gemini Agentic Video Understanding</b> и выявление системных проблем геймдизайна</div>',
    unsafe_allow_html=True
)

st.markdown(
    f'<div class="project-badge">📁 Активный проект: <b>{active_project.name}</b> (путь: reports/{active_project.name}/)</div>',
    unsafe_allow_html=True
)

# Вкладки
tab_meta, tab_video, tab_reports = st.tabs([
    "🧠 Сводный Мета-рекап (Кросс-анализ всех отчётов)",
    "📹 Анализ видео (Новый рекап)",
    "📁 Отчёты проекта"
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
        with st.expander("📋 Выберите отчёты для включения в сводный анализ (по умолчанию выбраны все)", expanded=True):
            for r in existing_reports:
                ch_name = r.get("channel_name") or "Канал"
                views_str = r.get("views") or ""
                views_badge = f" | 👀 {views_str}" if views_str else ""
                title_str = r.get("video_title") or r["filename"]

                label = f"📺 **{ch_name}**: «{title_str}»{views_badge} ({r['created_at']})"
                cb = st.checkbox(
                    label,
                    value=True,
                    key=f"rep_cb_{r['filename']}"
                )
                if cb:
                    selected_reports_files.append(r)

        c_ctx, c_q = st.columns([1, 1])
        with c_ctx:
            game_context_meta = st.text_area(
                "Краткий контекст игры (необязательно):",
                placeholder="Например: гибрид автоматизации, тетриса и рогалика. Игрок строит цепочки снабжения для хламоботов.",
                height=90,
                key="meta_game_ctx"
            )
        with c_q:
            focus_question = st.text_area(
                "Особый вопрос для сводки (необязательно):",
                placeholder="Например: На что чаще всего жаловались в обучении? Почему игроки путались в логистике тайлов?",
                height=90,
                key="meta_focus_q"
            )

        run_meta_btn = st.button("🚀 Запустить сводный кросс-анализ всех отчётов", type="primary", key="run_meta_btn")

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
                            reports_payload.append({
                                "filename": rep["filename"],
                                "content": f.read()
                            })
                    except Exception as e:
                        st.warning(f"Не удалось прочитать {rep['filename']}: {e}")

                with st.spinner(f"🧠 Gemini синтезирует данные из {len(reports_payload)} плейтестов, ищет повторяющиеся боли и строит бэклог..."):
                    try:
                        meta_analyzer = MetaAnalyzer(api_key=api_key_input, model=selected_model)
                        meta_res = meta_analyzer.analyze_reports(
                            project=active_project,
                            reports_data=reports_payload,
                            focus_question=focus_question
                        )

                        # Сохраняем сводный отчет в папку reports/<project>/
                        saved_path = ProjectManager.save_meta_recap(
                            project_name=active_project.name,
                            content=meta_res.content
                        )

                        st.session_state["latest_meta_recap"] = meta_res.content
                        st.session_state["latest_meta_file"] = saved_path.name
                        st.success(f"✅ Сводный мета-анализ по {len(reports_payload)} плейтестам построен и сохранен в reports/{active_project.name}/{saved_path.name}!")

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
                key="download_meta_btn"
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

    with col_input:
        youtube_url = st.text_input(
            "🔗 Ссылка на YouTube видео плейтеста:",
            placeholder="https://www.youtube.com/watch?v=... или https://youtu.be/...",
            key="video_url_input"
        )

        preset_options = list(PRESETS.keys())
        preset_labels = [PRESETS[k]["title"] for k in preset_options]
        selected_preset_index = st.selectbox(
            "📋 Критерии анализа (Пресет):",
            options=range(len(preset_options)),
            format_func=lambda i: preset_labels[i],
            key="preset_select"
        )
        chosen_preset_key = preset_options[selected_preset_index]
        st.caption(PRESETS[chosen_preset_key]["description"])

        with st.expander("🛠 Контекст игры (необязательно)"):
            game_context = st.text_area(
                "Контекст для модели:",
                placeholder=f"Игра: {active_project.name}. Опишите правила, жанр и задачи плейтеста...",
                height=90,
                key="context_input"
            )

        with st.expander("❓ Специфические вопросы разработчика (по одному на строку)"):
            custom_questions_text = st.text_area(
                "Ваши вопросы:",
                placeholder="Понял ли игрок механику крафта?\nЗаметил ли подсказку у алтаря?\nКакая была реакция на первого босса?",
                height=110,
                key="questions_input"
            )

        run_video_btn = st.button("🚀 Начать анализ видео", type="primary", key="run_video_btn")

    with col_preview:
        video_id = VideoAnalyzer.extract_youtube_video_id(youtube_url) if youtube_url else None
        if video_id:
            st.video(f"https://www.youtube.com/watch?v={video_id}")
            # Подгружаем метаданные видео прямо в интерфейс
            yt_meta = fetch_youtube_metadata(youtube_url)
            st.markdown(
                f"**{yt_meta.get('title')}**  \n"
                f"<span class='channel-tag'>📺 {yt_meta.get('channel_name')}</span> &nbsp; "
                f"<span class='views-tag'>👀 {yt_meta.get('views_formatted')} просмотров</span>",
                unsafe_allow_html=True
            )
        else:
            st.info("📺 Вставьте ссылку на YouTube видео, чтобы здесь появился плеер для сверки с таймкодами.")

    # Логика запуска анализа видео
    if run_video_btn:
        if not youtube_url:
            st.error("Пожалуйста, укажите ссылку на YouTube видео.")
        elif not api_key_input:
            st.error("Пожалуйста, укажите GEMINI_API_KEY в боковой панели или файле .env.")
        else:
            custom_questions = [
                q.strip() for q in custom_questions_text.split("\n") if q.strip()
            ]

            prompt = build_analysis_prompt(
                preset_key=chosen_preset_key,
                custom_questions=custom_questions,
                game_context=game_context
            )

            with st.spinner("🤖 Gemini выполняет Agentic Video Understanding... Модель изучает транскрипт, ищет затыки и реакции игрока..."):
                try:
                    analyzer = VideoAnalyzer(api_key=api_key_input, model=selected_model)
                    result = analyzer.analyze(video_url=youtube_url, prompt=prompt)

                    # Формируем заголовок с названием канала и статами просмотров
                    meta = result.video_meta or fetch_youtube_metadata(result.video_url)
                    v_title = meta.get("title", "Видео")
                    ch_name = meta.get("channel_name", "Канал")
                    ch_url = meta.get("channel_url", "")
                    views_str = meta.get("views_formatted", "—")

                    header_lines = [
                        "# 🎮 Отчет UX-анализа плейтеста\n",
                        f"- **Видео**: [{v_title}]({result.video_url})",
                        f"- **Канал**: [{ch_name}]({ch_url})" if ch_url else f"- **Канал**: {ch_name}",
                        f"- **Просмотры**: {views_str} просмотров",
                        f"- **Дата анализа**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                        f"- **Модель**: {result.model}",
                    ]
                    if result.total_tokens:
                        header_lines.append(f"- **Использовано токенов**: {result.total_tokens:,}")
                    header_lines.append("\n---\n")

                    full_report_text = "\n".join(header_lines) + "\n" + result.output_text

                    # Сохраняем отчет в проект reports/<active_project.name>/
                    clean_vid = VideoAnalyzer.extract_youtube_video_id(youtube_url) or "video"
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"recap_{clean_vid}_{ts}.md"

                    ProjectManager.save_report(
                        project_name=active_project.name,
                        filename=filename,
                        content=full_report_text
                    )

                    st.session_state["last_video_report"] = full_report_text
                    st.session_state["last_video_meta"] = {
                        "video_url": result.video_url,
                        "title": v_title,
                        "channel_name": ch_name,
                        "views": views_str,
                        "model": result.model,
                        "tokens": result.total_tokens,
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    st.success(f"✅ Анализ завершён и сохранён в `reports/{active_project.name}/{filename}`!")

                except Exception as e:
                    st.error(str(e))

    # Вывод последнего готового отчета
    if "last_video_report" in st.session_state:
        st.markdown("---")
        st.subheader("📊 Результаты анализа видео")
        meta = st.session_state.get("last_video_meta", {})

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Канал", meta.get("channel_name", "—"))
        with c2:
            st.metric("Просмотры", meta.get("views", "—"))
        with c3:
            st.metric("Использовано токенов", f"{meta.get('tokens', 0):,}" if meta.get("tokens") else "—")
        with c4:
            st.metric("Модель", meta.get("model", selected_model))

        st.download_button(
            label="📥 Скачать отчёт (Markdown .md)",
            data=st.session_state["last_video_report"],
            file_name="playtest_recap.md",
            mime="text/markdown",
            key="download_last_video_btn"
        )
        st.markdown(st.session_state["last_video_report"])


# ==========================================
# ВКЛАДКА 3: БАЗА ОТЧЁТОВ ПРОЕКТА
# ==========================================
with tab_reports:
    st.subheader(f"📁 Все отчёты плейтестов: reports/{active_project.name}/")

    proj_reports = ProjectManager.list_reports(active_project.name)
    if not proj_reports:
        st.info(f"В папке `reports/{active_project.name}/` пока нет отчётов. Создайте первый на вкладке '📹 Анализ видео'!")
    else:
        st.write(f"Всего отчётов: **{len(proj_reports)}**")

        for rep in proj_reports:
            ch_name = rep.get("channel_name") or "Канал"
            views_str = rep.get("views") or ""
            views_label = f" | 👀 {views_str}" if views_str else ""
            title_str = rep.get("video_title") or rep["filename"]

            with st.expander(f"📝 {ch_name}: «{title_str}»{views_label} ({rep['created_at']} | {rep['size_kb']} KB)"):
                with open(rep["path"], "r", encoding="utf-8") as rf:
                    content = rf.read()

                st.download_button(
                    label=f"📥 Скачать {rep['filename']}",
                    data=content,
                    file_name=rep["filename"],
                    mime="text/markdown",
                    key=f"dl_file_{rep['filename']}"
                )

                st.markdown(content)
