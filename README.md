# A.L.F.R.E.D.

**Adaptive Learning Framework for Responsive Executive Decisions**

ALFRED is a personal AI desktop assistant inspired by Tony Stark's JARVIS. Built with Python, FastAPI, React, and local AI models, ALFRED aims to become a centralized productivity hub capable of understanding natural language and performing everyday computer tasks.

Unlike traditional assistants, ALFRED is designed to integrate multiple productivity tools into a single interface, allowing workflows to span files, calendars, email, projects, and documents.

---

# Features

## Natural Language Commands

ALFRED accepts conversational commands and routes them to the appropriate tool or service.

Examples:

```text
Show me today's calendar

Create an event tomorrow at 3pm called Team Meeting

Open my portfolio project

Search Downloads for resume

What do I have this week?
```

---

## File Management

Currently supported:

- Search files and folders
- Browse Desktop, Downloads, and Documents
- Open files and folders
- Preview available files
- Safe read-only access to user files

Current permissions:

- Read files
- Read folders
- Open files

Future permissions: 

- Delete files  
- Move files 
- Rename files
- Modify files

File editing functionality will be added in a future release.

---

## Project Launcher

Quickly launch development projects from a single command.

Current capabilities:

- Browse project directories
- View project folders
- Launch projects in VS Code
- Navigate project structures

---

## Google Calendar Integration

ALFRED is connected directly to Google Calendar.

Current features:

- Create events
- Edit existing events
- Daily schedule preview
- Tomorrow preview
- Weekly schedule summary
- Top 3 upcoming events dashboard
- Natural language event creation

Examples:

```text
Create an event tomorrow at 6pm called Dinner

What's on my calendar today?

Plan my week

Show tomorrow's schedule
```

---

# Current Architecture

```
React + TypeScript Frontend
            │
            ▼
      FastAPI Backend
            │
            ▼
Natural Language Processor
(Currently migrating to Ollama)
            │
            ▼
Tool Router
    ├── File Manager
    ├── Project Launcher
    ├── Calendar
    └── Future Integrations
```

---

# Project Structure

```
app/
│
├── backend/
│   ├── main.py
│   │
│   ├── calendar_tools/
│   │   ├── calendar_intent.py
│   │   ├── calendar_routes.py
│   │   ├── calendar_service.py
│   │   └── planning_service.py
│   │
│   ├── tools/
│   │   ├── file_manager.py
│   │   └── project_launcher.py
│   │
│   └── ai/
│       └── (Ollama integration)
│
└── frontend/
    ├── React
    ├── TypeScript
    └── Vite
```

---

# Important Files

### `main.py`

Main FastAPI application.

Responsible for:

- API routes
- Command handling
- Tool routing
- Backend startup

---

### `calendar_intent.py`

Parses natural language calendar requests.

Examples:

- Create event
- Update event
- Daily schedule
- Weekly planning

---

### `calendar_routes.py`

REST API endpoints for calendar functionality.

---

### `calendar_service.py`

Communicates with the Google Calendar API.

Handles:

- Creating events
- Updating events
- Reading events
- Authentication

---

### `planning_service.py`

Generates higher-level planning views.

Examples:

- Weekly summaries
- Tomorrow overview
- Event analysis

---

### `file_manager.py`

Responsible for safe file access.

Current capabilities:

- File search
- Folder search
- Open files
- Read directory contents

---

### `project_launcher.py`

Discovers development projects and launches them in VS Code.

---

# Technology Stack

## Backend

- Python
- FastAPI

## Frontend

- React
- TypeScript
- Vite

## AI

- Ollama
- Local LLMs

## Integrations

- Google Calendar API

---

# Future Features

## Productivity Integrations

Planned support for:

- Gmail
- Google Docs
- Google Sheets
- Notes
- Tasks

---

## Connected Workflows

One of ALFRED's primary goals is connecting multiple tools together.

Examples:

- Read an email → summarize it → create a calendar event
- Read meeting notes → generate tasks
- Search documents → create reminders
- Summarize files → draft an email
- Generate schedules from project deadlines

Instead of isolated commands, ALFRED will support intelligent multi-step workflows.

---

## Voice Assistant

Future voice capabilities include:

- Text-to-speech responses
- Voice dictation
- Wake-word activation ("Hey Alfred")
- Hands-free interaction

---

## Desktop Integration

Planned improvements:

- Global keyboard shortcut
- Background system tray application
- Faster startup
- Launch on boot

---

## AI Improvements

Future work includes:

- Better natural language understanding
- Multi-step reasoning
- Long-term memory
- Context-aware conversations
- Smarter command routing
- Improved tool selection

---

# Roadmap

### Phase 1

- Desktop interface
- Backend API
- Command routing

### Phase 2

- File management
- Project launcher

### Phase 3

- Google Calendar integration

### Phase 4

- Ollama integration
- Local language model

### Phase 5

- Gmail
- Google Docs
- Google Sheets
- Notes

### Phase 6

- Connected agent workflows

### Phase 7

- Voice assistant

### Phase 8

- Long-term memory
- Fully agentic productivity assistant

---

# Inspiration

Inspired by fictional AI assistants including:

- JARVIS
- FRIDAY
- EDITH

The goal isn't to recreate science fiction, but to build a practical desktop AI assistant that makes everyday workflows faster, smarter, and more connected.

---

# Author

**Kaylee Henry**

Computer Science @ Georgia Tech