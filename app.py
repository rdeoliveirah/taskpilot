from __future__ import annotations

import html
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
import streamlit as st


DATA_FILE = Path("taskpilot_data.json")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
GEMINI_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_OPENROUTER_MODEL = "openai/gpt-4o-mini"
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"


def load_data() -> dict:
    """Load local app data, creating a simple default structure when needed."""
    if not DATA_FILE.exists():
        return {"tasks": [], "notes": []}

    try:
        with DATA_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError):
        st.warning("Could not read saved data. Starting with an empty workspace.")
        return {"tasks": [], "notes": []}

    data.setdefault("tasks", [])
    data.setdefault("notes", [])
    return data


def save_data(data: dict) -> None:
    with DATA_FILE.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)


def demo_data() -> dict:
    today = date.today()
    return {
        "tasks": [
            {
                "title": "Prepare client presentation",
                "deadline": (today + timedelta(days=1)).isoformat(),
                "estimated_time": 2.5,
                "importance": 5,
            },
            {
                "title": "Review research notes",
                "deadline": (today + timedelta(days=3)).isoformat(),
                "estimated_time": 1.5,
                "importance": 4,
            },
            {
                "title": "Submit weekly progress update",
                "deadline": today.isoformat(),
                "estimated_time": 0.75,
                "importance": 3,
            },
            {
                "title": "Plan next sprint tasks",
                "deadline": (today + timedelta(days=7)).isoformat(),
                "estimated_time": 2.0,
                "importance": 4,
            },
        ],
        "notes": [
            {
                "text": "Keep mornings for deep work and batch admin tasks after lunch.",
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
        ],
    }


def load_demo_workspace(data: dict) -> None:
    sample = demo_data()
    data["tasks"] = sample["tasks"]
    data["notes"] = sample["notes"]
    save_data(data)
    st.session_state.ai_response = ""
    st.success("Demo workspace loaded.")
    st.rerun()


def days_until(deadline: str) -> int:
    deadline_date = datetime.strptime(deadline, "%Y-%m-%d").date()
    return (deadline_date - date.today()).days


def urgency_points(days_left: int) -> int:
    if days_left < 0:
        return 6
    if days_left == 0:
        return 5
    if days_left <= 2:
        return 4
    if days_left <= 7:
        return 3
    if days_left <= 14:
        return 2
    return 1


def priority_score(task: dict) -> int:
    days_left = days_until(task["deadline"])
    return (int(task["importance"]) * 2) + urgency_points(days_left)


def deadline_status(days_left: int) -> str:
    if days_left < 0:
        return "Overdue"
    if days_left == 0:
        return "Due today"
    if days_left <= 2:
        return "Urgent"
    if days_left <= 7:
        return "This week"
    return "Upcoming"


def status_class(status: str) -> str:
    return status.lower().replace(" ", "-")


def task_rows(tasks: list[dict]) -> list[dict]:
    rows = []
    for task in tasks:
        days_left = days_until(task["deadline"])
        rows.append(
            {
                "Title": task["title"],
                "Deadline": task["deadline"],
                "Status": deadline_status(days_left),
                "Days Left": days_left,
                "Estimated Hours": float(task["estimated_time"]),
                "Importance": int(task["importance"]),
                "Priority Score": priority_score(task),
            }
        )
    return sorted(rows, key=lambda row: row["Priority Score"], reverse=True)


def suggested_daily_plan(tasks: list[dict]) -> list[str]:
    if not tasks:
        return ["Add a task to generate a daily plan."]

    sorted_tasks = sorted(tasks, key=priority_score, reverse=True)
    plan = []
    remaining_hours = 6.0

    for task in sorted_tasks:
        estimate = float(task["estimated_time"])
        days_left = days_until(task["deadline"])
        deadline_text = "overdue" if days_left < 0 else f"due in {days_left} day(s)"

        if remaining_hours <= 0:
            plan.append(f"Later: {task['title']} ({estimate:g}h, {deadline_text})")
            continue

        planned_time = min(estimate, remaining_hours)
        plan.append(f"Work on {task['title']} for {planned_time:g}h ({deadline_text}).")
        remaining_hours -= planned_time

    return plan


def urgent_task_count(tasks: list[dict]) -> int:
    return sum(1 for task in tasks if days_until(task["deadline"]) <= 2)


def total_estimated_hours(tasks: list[dict]) -> float:
    return sum(float(task["estimated_time"]) for task in tasks)


def top_priority_task(tasks: list[dict]) -> str:
    if not tasks:
        return "Ready for your first task"
    return task_rows(tasks)[0]["Title"]


def format_tasks_for_ai(tasks: list[dict]) -> str:
    if not tasks:
        return "No tasks have been added yet."

    lines = []
    for task in task_rows(tasks):
        lines.append(
            "- "
            f"{task['Title']} | deadline: {task['Deadline']} | status: {task['Status']} | "
            f"days left: {task['Days Left']} | estimated hours: {task['Estimated Hours']} | "
            f"importance: {task['Importance']}/5 | local priority score: {task['Priority Score']}"
        )
    return "\n".join(lines)


def format_notes_for_ai(notes: list[dict]) -> str:
    if not notes:
        return "No notes have been saved yet."

    return "\n".join(
        f"- {note['created_at']}: {note['text']}" for note in notes[-5:]
    )


def build_ai_prompt(tasks: list[dict], notes: list[dict], request_type: str) -> str:
    local_plan = "\n".join(f"- {item}" for item in suggested_daily_plan(tasks))
    return f"""
You are TaskPilot, a practical productivity assistant for students and professionals.
Today is {date.today().isoformat()}.

User request:
{request_type}

Tasks:
{format_tasks_for_ai(tasks)}

Recent notes:
{format_notes_for_ai(notes)}

Local rule-based plan:
{local_plan}

Respond in plain Markdown with concise, actionable advice. Use these headings:
1. Priority Recommendations
2. Daily Schedule
3. Productivity Suggestions

Keep the response friendly, realistic, and easy for a beginner to understand.
"""


def call_openrouter(api_key: str, model: str, prompt: str) -> str:
    """Call OpenRouter's chat completions endpoint and return the assistant text."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/",
        "X-Title": "TaskPilot",
    }
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are a concise productivity coach. Do not invent tasks.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
        "max_tokens": 900,
    }

    response = requests.post(
        OPENROUTER_URL,
        headers=headers,
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    result = response.json()
    return result["choices"][0]["message"]["content"].strip()


def call_gemini(api_key: str, model: str, prompt: str) -> str:
    """Call Gemini's generateContent endpoint and return the assistant text."""
    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "system_instruction": {
            "parts": [
                {
                    "text": "You are a concise productivity coach. Do not invent tasks.",
                }
            ]
        },
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt,
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 900,
        },
    }

    response = requests.post(
        GEMINI_URL_TEMPLATE.format(model=model),
        headers=headers,
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    result = response.json()
    return result["candidates"][0]["content"]["parts"][0]["text"].strip()


def call_ai_provider(provider: str, api_key: str, model: str, prompt: str) -> str:
    if provider == "OpenRouter":
        return call_openrouter(api_key, model, prompt)
    if provider == "Google Gemini":
        return call_gemini(api_key, model, prompt)
    raise ValueError(f"Unsupported AI provider: {provider}")


def generate_ai_response(
    provider: str,
    api_key: str,
    model: str,
    tasks: list[dict],
    notes: list[dict],
    request_type: str,
) -> None:
    if not api_key:
        st.error(f"Enter your {provider} API key in the sidebar first.")
        return

    if not tasks:
        st.info("Add at least one task before asking the AI assistant for recommendations.")
        return

    prompt = build_ai_prompt(tasks, notes, request_type)
    try:
        with st.spinner(f"Asking {provider} for recommendations..."):
            st.session_state.ai_response = call_ai_provider(provider, api_key, model, prompt)
    except requests.HTTPError as error:
        status_code = error.response.status_code if error.response is not None else "unknown"
        st.error(
            f"{provider} request failed with status {status_code}. "
            "Check your API key, model name, provider access, and available credits or quota."
        )
    except requests.RequestException:
        st.error(f"Could not reach {provider}. Check your internet connection and try again.")
    except (KeyError, IndexError, ValueError):
        st.error(f"{provider} returned an unexpected response format. Try another model or provider.")


def metric_card(label: str, value: str, detail: str) -> None:
    st.markdown(
        f"""
        <div class="metric-card">
            <p>{html.escape(label)}</p>
            <h3>{html.escape(value)}</h3>
            <span>{html.escape(detail)}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def empty_state(title: str, body: str, action: str) -> None:
    st.markdown(
        f"""
        <div class="empty-state">
            <div class="empty-orbit"></div>
            <h3>{html.escape(title)}</h3>
            <p>{html.escape(body)}</p>
            <span>{html.escape(action)}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def show_task_cards(tasks: list[dict], limit: int | None = None) -> None:
    rows = task_rows(tasks)
    if limit is not None:
        rows = rows[:limit]

    for task in rows:
        status = task["Status"]
        title = html.escape(task["Title"])
        deadline = html.escape(task["Deadline"])
        css_class = status_class(status)
        st.markdown(
            f"""
            <div class="task-card">
                <div class="task-card-top">
                    <div>
                        <h4>{title}</h4>
                        <p>Deadline {deadline} / {task['Days Left']} day(s) left</p>
                    </div>
                    <span class="status-pill {css_class}">{html.escape(status)}</span>
                </div>
                <div class="task-meta-grid">
                    <div><span>Priority</span><strong>{task['Priority Score']}</strong></div>
                    <div><span>Importance</span><strong>{task['Importance']}/5</strong></div>
                    <div><span>Estimate</span><strong>{task['Estimated Hours']:g}h</strong></div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def show_task_table(tasks: list[dict]) -> None:
    st.dataframe(
        task_rows(tasks),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Title": st.column_config.TextColumn("Task", width="large"),
            "Deadline": st.column_config.DateColumn("Deadline"),
            "Status": st.column_config.TextColumn("Status"),
            "Days Left": st.column_config.NumberColumn("Days Left", format="%d"),
            "Estimated Hours": st.column_config.NumberColumn("Hours", format="%.2f"),
            "Importance": st.column_config.ProgressColumn(
                "Importance",
                min_value=1,
                max_value=5,
                format="%d/5",
            ),
            "Priority Score": st.column_config.NumberColumn("Priority", format="%d"),
        },
    )


def page_header(eyebrow: str, title: str, subtitle: str) -> None:
    st.markdown(
        f"""
        <section class="hero-panel">
            <div>
                <span class="eyebrow">{html.escape(eyebrow)}</span>
                <h1>{html.escape(title)}</h1>
                <p>{html.escape(subtitle)}</p>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_footer() -> None:
    st.markdown(
        """
        <footer class="footer">
            <span>TaskPilot</span>
            <span>Local-first planning with optional OpenRouter or Gemini intelligence.</span>
        </footer>
        """,
        unsafe_allow_html=True,
    )


st.set_page_config(page_title="TaskPilot", layout="wide", initial_sidebar_state="expanded")

data = load_data()

st.markdown(
    """
    <style>
    :root {
        --bg: #080b12;
        --panel: #101624;
        --panel-soft: #151d2f;
        --line: rgba(148, 163, 184, 0.18);
        --text: #eef2ff;
        --muted: #96a3b8;
        --accent: #38bdf8;
        --accent-2: #a78bfa;
        --success: #34d399;
        --warning: #fbbf24;
        --danger: #fb7185;
    }

    html, body, [class*="css"] {
        font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }

    .stApp {
        background:
            radial-gradient(circle at top left, rgba(56, 189, 248, 0.16), transparent 28rem),
            radial-gradient(circle at top right, rgba(167, 139, 250, 0.14), transparent 30rem),
            linear-gradient(135deg, #080b12 0%, #0d1320 48%, #090d16 100%);
        color: var(--text);
    }

    .block-container {
        max-width: 1180px;
        padding-top: 2rem;
        padding-bottom: 2rem;
    }

    section[data-testid="stSidebar"] {
        background: rgba(10, 15, 25, 0.96);
        border-right: 1px solid var(--line);
    }

    section[data-testid="stSidebar"] * {
        color: var(--text);
    }

    h1, h2, h3, h4 {
        letter-spacing: 0;
    }

    div[data-testid="stButton"] button {
        border-radius: 8px;
        border: 1px solid rgba(56, 189, 248, 0.28);
        background: linear-gradient(135deg, rgba(56, 189, 248, 0.95), rgba(167, 139, 250, 0.94));
        color: #07111f;
        font-weight: 800;
        transition: transform 160ms ease, box-shadow 160ms ease, border-color 160ms ease;
        box-shadow: 0 16px 34px rgba(56, 189, 248, 0.17);
    }

    div[data-testid="stButton"] button:hover {
        transform: translateY(-1px);
        border-color: rgba(255, 255, 255, 0.55);
        box-shadow: 0 20px 44px rgba(167, 139, 250, 0.22);
    }

    div[data-testid="stTextInput"] input,
    div[data-testid="stTextArea"] textarea,
    div[data-testid="stNumberInput"] input {
        border-radius: 8px;
        border: 1px solid var(--line);
        background: rgba(15, 23, 42, 0.92);
        color: var(--text);
    }

    .hero-panel {
        position: relative;
        overflow: hidden;
        border: 1px solid var(--line);
        border-radius: 8px;
        padding: 2rem;
        margin-bottom: 1.5rem;
        background:
            linear-gradient(135deg, rgba(15, 23, 42, 0.94), rgba(17, 24, 39, 0.78)),
            radial-gradient(circle at 88% 20%, rgba(56, 189, 248, 0.22), transparent 18rem);
        box-shadow: 0 24px 80px rgba(0, 0, 0, 0.32);
        animation: fadeUp 420ms ease both;
    }

    .hero-panel h1 {
        margin: 0.4rem 0 0.65rem;
        font-size: clamp(2.2rem, 5vw, 4.2rem);
        line-height: 1;
        font-weight: 800;
    }

    .hero-panel p {
        max-width: 720px;
        color: var(--muted);
        font-size: 1.05rem;
        margin: 0;
    }

    .eyebrow {
        display: inline-flex;
        padding: 0.35rem 0.65rem;
        border-radius: 999px;
        background: rgba(56, 189, 248, 0.12);
        color: #bae6fd;
        border: 1px solid rgba(56, 189, 248, 0.22);
        font-weight: 700;
        font-size: 0.78rem;
        text-transform: uppercase;
        letter-spacing: 0.08rem;
    }

    .metric-card,
    .task-card,
    .empty-state,
    .insight-card,
    .footer {
        border: 1px solid var(--line);
        background: linear-gradient(180deg, rgba(16, 22, 36, 0.94), rgba(12, 18, 31, 0.92));
        border-radius: 8px;
        box-shadow: 0 18px 60px rgba(0, 0, 0, 0.24);
        animation: fadeUp 420ms ease both;
    }

    .metric-card {
        padding: 1.15rem;
        min-height: 142px;
    }

    .metric-card p {
        color: var(--muted);
        margin: 0 0 0.75rem;
        font-size: 0.84rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.07rem;
    }

    .metric-card h3 {
        margin: 0;
        font-size: 2.2rem;
        font-weight: 800;
    }

    .metric-card span {
        display: block;
        margin-top: 0.8rem;
        color: #cbd5e1;
        font-size: 0.92rem;
    }

    .task-card {
        padding: 1rem;
        margin-bottom: 0.9rem;
        transition: transform 160ms ease, border-color 160ms ease, background 160ms ease;
    }

    .task-card:hover {
        transform: translateY(-2px);
        border-color: rgba(56, 189, 248, 0.38);
        background: linear-gradient(180deg, rgba(21, 29, 47, 0.98), rgba(12, 18, 31, 0.95));
    }

    .task-card-top {
        display: flex;
        gap: 1rem;
        align-items: flex-start;
        justify-content: space-between;
    }

    .task-card h4 {
        margin: 0;
        font-size: 1rem;
        font-weight: 750;
    }

    .task-card p {
        margin: 0.45rem 0 0;
        color: var(--muted);
        font-size: 0.9rem;
    }

    .status-pill {
        white-space: nowrap;
        border-radius: 999px;
        padding: 0.35rem 0.6rem;
        font-size: 0.75rem;
        font-weight: 800;
        border: 1px solid rgba(148, 163, 184, 0.2);
        background: rgba(148, 163, 184, 0.12);
        color: #dbeafe;
    }

    .overdue, .due-today {
        background: rgba(251, 113, 133, 0.16);
        color: #fecdd3;
        border-color: rgba(251, 113, 133, 0.32);
    }

    .urgent {
        background: rgba(251, 191, 36, 0.14);
        color: #fde68a;
        border-color: rgba(251, 191, 36, 0.3);
    }

    .this-week {
        background: rgba(56, 189, 248, 0.14);
        color: #bae6fd;
        border-color: rgba(56, 189, 248, 0.3);
    }

    .upcoming {
        background: rgba(52, 211, 153, 0.13);
        color: #bbf7d0;
        border-color: rgba(52, 211, 153, 0.28);
    }

    .task-meta-grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 0.75rem;
        margin-top: 1rem;
    }

    .task-meta-grid div {
        border-radius: 8px;
        background: rgba(2, 6, 23, 0.35);
        border: 1px solid rgba(148, 163, 184, 0.1);
        padding: 0.75rem;
    }

    .task-meta-grid span {
        display: block;
        color: var(--muted);
        font-size: 0.75rem;
        margin-bottom: 0.2rem;
    }

    .task-meta-grid strong {
        color: var(--text);
        font-size: 1.05rem;
    }

    .empty-state {
        padding: 2rem;
        text-align: center;
        min-height: 260px;
    }

    .empty-orbit {
        width: 84px;
        height: 84px;
        margin: 0 auto 1.1rem;
        border-radius: 999px;
        background:
            radial-gradient(circle at 35% 35%, #e0f2fe, #38bdf8 36%, transparent 37%),
            conic-gradient(from 45deg, rgba(56, 189, 248, 0.15), rgba(167, 139, 250, 0.8), rgba(52, 211, 153, 0.55), rgba(56, 189, 248, 0.15));
        animation: pulseGlow 2.8s ease-in-out infinite;
    }

    .empty-state h3 {
        margin: 0 0 0.6rem;
        font-size: 1.35rem;
    }

    .empty-state p {
        color: var(--muted);
        max-width: 560px;
        margin: 0 auto 1rem;
    }

    .empty-state span {
        color: #bae6fd;
        font-weight: 700;
    }

    .insight-card {
        padding: 1rem;
        min-height: 140px;
    }

    .insight-card h4 {
        margin: 0 0 0.45rem;
        font-size: 1rem;
    }

    .insight-card p {
        margin: 0;
        color: var(--muted);
        font-size: 0.92rem;
    }

    .footer {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        margin-top: 2rem;
        padding: 1rem;
        color: var(--muted);
        font-size: 0.9rem;
    }

    .footer span:first-child {
        color: var(--text);
        font-weight: 800;
    }

    div[data-testid="stDataFrame"] {
        border: 1px solid var(--line);
        border-radius: 8px;
        overflow: hidden;
    }

    @keyframes fadeUp {
        from {
            opacity: 0;
            transform: translateY(10px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }

    @keyframes pulseGlow {
        0%, 100% {
            transform: scale(1);
            filter: drop-shadow(0 0 18px rgba(56, 189, 248, 0.25));
        }
        50% {
            transform: scale(1.04);
            filter: drop-shadow(0 0 30px rgba(167, 139, 250, 0.36));
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.sidebar.markdown("## TaskPilot")
st.sidebar.caption("AI productivity operating system")
section = st.sidebar.radio(
    "Navigation",
    [
        "[D] Dashboard",
        "[+] Add Task",
        "[AI] AI Assistant",
        "[N] Notes",
        "[P] Daily Plan",
    ],
)

st.sidebar.divider()
if st.sidebar.button("Load demo data"):
    load_demo_workspace(data)

st.sidebar.divider()
st.sidebar.subheader("AI Provider")
ai_provider = st.sidebar.selectbox(
    "Provider",
    ["OpenRouter", "Google Gemini"],
)
default_model = DEFAULT_OPENROUTER_MODEL if ai_provider == "OpenRouter" else DEFAULT_GEMINI_MODEL
provider_api_key = st.sidebar.text_input(
    f"{ai_provider} API key",
    type="password",
    help="Used only for this browser session. It is not saved to taskpilot_data.json.",
)
provider_model = st.sidebar.text_input(
    f"{ai_provider} model",
    value=default_model,
    help="Use a model name your selected provider account can access.",
)
st.sidebar.caption("AI requests send task and note text to the selected provider only when you click generate. API keys are session-only.")

page_header(
    "AI productivity assistant",
    "TaskPilot",
    "A modern local-first workspace for prioritizing tasks, shaping daily focus, and turning plans into action.",
)

if section == "[D] Dashboard":
    total_tasks = len(data["tasks"])
    urgent_tasks = urgent_task_count(data["tasks"])
    estimated_hours = total_estimated_hours(data["tasks"])

    metric_columns = st.columns(4)
    with metric_columns[0]:
        metric_card("Total tasks", str(total_tasks), "Tracked in your local workspace")
    with metric_columns[1]:
        metric_card("Urgent", str(urgent_tasks), "Due today, overdue, or inside 48 hours")
    with metric_columns[2]:
        metric_card("Estimated", f"{estimated_hours:g}h", "Planned workload across tasks")
    with metric_columns[3]:
        metric_card("Top focus", top_priority_task(data["tasks"]), "Highest local priority")

    st.markdown("### Command Center")
    if data["tasks"]:
        left, right = st.columns([1.2, 1])
        with left:
            st.markdown("#### Priority Queue")
            show_task_cards(data["tasks"], limit=4)
        with right:
            st.markdown("#### Today Preview")
            for number, item in enumerate(suggested_daily_plan(data["tasks"])[:3], start=1):
                st.markdown(
                    f"""
                    <div class="insight-card">
                        <h4>Step {number}</h4>
                        <p>{html.escape(item)}</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            if st.button("Clear all tasks"):
                data["tasks"] = []
                save_data(data)
                st.rerun()
    else:
        left, right = st.columns([1.25, 1])
        with left:
            empty_state(
                "Your command center is ready.",
                "Start from scratch or load the demo workspace to see how TaskPilot organizes priorities, schedules, and notes.",
                "Use the sidebar demo button or create your first task.",
            )
        with right:
            st.markdown(
                """
                <div class="insight-card">
                    <h4>What appears here?</h4>
                    <p>Priority cards, urgent work, estimated effort, and a daily focus preview populate the moment you add tasks.</p>
                </div>
                <div class="insight-card">
                    <h4>Portfolio-ready flow</h4>
                    <p>The app works without an API key, then unlocks OpenRouter or Gemini recommendations when you want AI planning.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("Load demo workspace", type="primary"):
                load_demo_workspace(data)

elif section == "[+] Add Task":
    st.markdown("### Create a Task")
    st.write("Capture the work, estimate the effort, and TaskPilot will calculate the priority signal.")

    form_col, preview_col = st.columns([1, 1])
    with form_col:
        with st.form("task_form", clear_on_submit=True):
            title = st.text_input("Task title", placeholder="Example: Draft product launch brief")
            deadline = st.date_input("Deadline", min_value=date.today())
            estimated_time = st.number_input(
                "Estimated time (hours)",
                min_value=0.25,
                max_value=24.0,
                value=1.0,
                step=0.25,
            )
            importance = st.slider("Importance", min_value=1, max_value=5, value=3)
            submitted = st.form_submit_button("Add task")

        if submitted:
            if title.strip():
                data["tasks"].append(
                    {
                        "title": title.strip(),
                        "deadline": deadline.isoformat(),
                        "estimated_time": estimated_time,
                        "importance": importance,
                    }
                )
                save_data(data)
                st.success("Task added.")
                st.rerun()
            else:
                st.error("Please enter a task title.")

    with preview_col:
        st.markdown("#### Current Priority Queue")
        if data["tasks"]:
            show_task_cards(data["tasks"], limit=3)
        else:
            empty_state(
                "No tasks yet.",
                "Add one task and the priority queue will start ranking your work automatically.",
                "A deadline plus importance score is enough to begin.",
            )

elif section == "[AI] AI Assistant":
    st.markdown("### AI Assistant")
    st.write("Use OpenRouter or Google Gemini to turn your local task list into recommendations, a schedule, and practical next steps.")

    if data["tasks"]:
        request_type = st.selectbox(
            "What should TaskPilot generate?",
            [
                "Full productivity review",
                "Task prioritization recommendations",
                "Daily schedule",
                "Productivity suggestions",
            ],
        )

        if st.button(f"Generate with {ai_provider}", type="primary"):
            generate_ai_response(
                ai_provider,
                provider_api_key,
                provider_model.strip() or default_model,
                data["tasks"],
                data["notes"],
                request_type,
            )

        if st.session_state.get("ai_response"):
            st.markdown("#### AI Output")
            st.markdown(st.session_state.ai_response)
        else:
            empty_state(
                "Ready for AI planning.",
                f"Add your {ai_provider} API key in the sidebar, choose a generation mode, and TaskPilot will analyze your local workspace.",
                "Your API key is not saved to the JSON file.",
            )
    else:
        empty_state(
            "Add tasks before asking the assistant.",
            "The AI assistant needs at least one task so it can give grounded recommendations instead of generic advice.",
            "Load demo data to preview the experience instantly.",
        )

elif section == "[N] Notes":
    st.markdown("### Notes Workspace")
    st.write("Save short reminders, project thoughts, or planning constraints for future AI context.")

    note_col, saved_col = st.columns([0.95, 1.05])
    with note_col:
        with st.form("note_form", clear_on_submit=True):
            note = st.text_area("Short note", placeholder="Example: Keep Friday afternoon free for review.")
            note_submitted = st.form_submit_button("Save note")

        if note_submitted:
            if note.strip():
                data["notes"].append(
                    {
                        "text": note.strip(),
                        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    }
                )
                save_data(data)
                st.success("Note saved.")
                st.rerun()
            else:
                st.error("Please write a note before saving.")

    with saved_col:
        st.markdown("#### Saved Notes")
        if data["notes"]:
            for saved_note in reversed(data["notes"]):
                st.markdown(
                    f"""
                    <div class="task-card">
                        <div class="task-card-top">
                            <div>
                                <h4>{html.escape(saved_note['created_at'])}</h4>
                                <p>{html.escape(saved_note['text'])}</p>
                            </div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            if st.button("Clear all notes"):
                data["notes"] = []
                save_data(data)
                st.rerun()
        else:
            empty_state(
                "No notes saved yet.",
                "Use notes for constraints, reminders, meeting context, or study details you want near your tasks.",
                "Recent notes are included in AI prompts.",
            )

elif section == "[P] Daily Plan":
    st.markdown("### Daily Plan")
    st.write("Start with a local plan, then generate a richer AI schedule when needed.")

    if data["tasks"]:
        plan_col, task_col = st.columns([0.95, 1.05])
        with plan_col:
            for number, item in enumerate(suggested_daily_plan(data["tasks"]), start=1):
                st.markdown(
                    f"""
                    <div class="insight-card">
                        <h4>Step {number}</h4>
                        <p>{html.escape(item)}</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            if st.button(f"Generate AI schedule with {ai_provider}"):
                generate_ai_response(
                    ai_provider,
                    provider_api_key,
                    provider_model.strip() or default_model,
                    data["tasks"],
                    data["notes"],
                    "Daily schedule",
                )

            if st.session_state.get("ai_response"):
                st.markdown("#### AI Schedule")
                st.markdown(st.session_state.ai_response)

        with task_col:
            st.markdown("#### Reference Tasks")
            show_task_cards(data["tasks"])
            with st.expander("Show table view"):
                show_task_table(data["tasks"])
    else:
        empty_state(
            "No plan yet.",
            "Add tasks or load demo data to generate a local daily plan and an AI-powered schedule.",
            "The plan appears here as soon as tasks exist.",
        )

render_footer()
