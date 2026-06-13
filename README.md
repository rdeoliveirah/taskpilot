# TaskPilot

TaskPilot is a simple AI-style productivity assistant prototype for students and professionals. It helps users add tasks, calculate priorities, build a suggested daily plan, and save short notes locally.

## Features

- Add tasks with a title, deadline, estimated time, and importance from 1 to 5
- View all tasks in a clean table
- Automatically calculate a priority score using deadline urgency and importance
- Generate a suggested daily plan based on the highest-priority tasks
- Save short notes
- Store all data locally in a JSON file

## Setup

1. Create and activate a virtual environment:

```bash
python -m venv .venv
.venv\Scripts\activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run the app:

```bash
streamlit run app.py
```

The app saves data in `taskpilot_data.json`, which is created automatically.

## How Priority Works

TaskPilot gives each task a priority score based on:

- Importance: higher importance increases the score
- Deadline urgency: tasks due sooner get extra points

The daily plan uses this score to suggest what to work on first.

## Future Improvements

- Mark tasks as complete
- Edit or delete individual tasks and notes
- Add calendar views
- Add categories or tags
- Use an AI API to generate smarter plans and study/work suggestions
