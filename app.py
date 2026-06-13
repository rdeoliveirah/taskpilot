from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import streamlit as st


DATA_FILE = Path("taskpilot_data.json")


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


def task_rows(tasks: list[dict]) -> list[dict]:
    rows = []
    for task in tasks:
        days_left = days_until(task["deadline"])
        rows.append(
            {
                "Title": task["title"],
                "Deadline": task["deadline"],
                "Days Left": days_left,
                "Estimated Time": f"{task['estimated_time']} hours",
                "Importance": task["importance"],
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


st.set_page_config(page_title="TaskPilot", layout="wide")

data = load_data()

st.title("TaskPilot")
st.caption("A simple AI-style productivity assistant for tasks, priorities, plans, and notes.")

task_tab, plan_tab, notes_tab = st.tabs(["Tasks", "Daily Plan", "Notes"])

with task_tab:
    st.subheader("Add a Task")

    with st.form("task_form", clear_on_submit=True):
        title = st.text_input("Task title")
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

    st.subheader("All Tasks")
    if data["tasks"]:
        st.dataframe(task_rows(data["tasks"]), use_container_width=True, hide_index=True)

        if st.button("Clear all tasks"):
            data["tasks"] = []
            save_data(data)
            st.rerun()
    else:
        st.info("No tasks yet. Add your first task above.")

with plan_tab:
    st.subheader("Suggested Daily Plan")
    st.write("TaskPilot prioritizes higher-importance work and closer deadlines first.")

    for item in suggested_daily_plan(data["tasks"]):
        st.write(f"- {item}")

with notes_tab:
    st.subheader("Save a Note")

    with st.form("note_form", clear_on_submit=True):
        note = st.text_area("Short note")
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

    st.subheader("Saved Notes")
    if data["notes"]:
        for saved_note in reversed(data["notes"]):
            st.markdown(f"**{saved_note['created_at']}**")
            st.write(saved_note["text"])
            st.divider()

        if st.button("Clear all notes"):
            data["notes"] = []
            save_data(data)
            st.rerun()
    else:
        st.info("No notes saved yet.")
