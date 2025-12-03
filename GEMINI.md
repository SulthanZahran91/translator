# GEMINI.md - Document Translator

This document provides a comprehensive overview of the Document Translator application, designed to give context for AI-driven development.

## 1. Project Overview

Document Translator is a full-stack web application designed for high-fidelity translation of Korean documents (.docx and .pdf) into English. It is built to handle large files, maintain formatting, and ensure terminological consistency through a sophisticated, multi-tiered glossary system.

The application features a clear separation between its backend API and frontend client:

*   **Backend**: A Python-based API using **FastAPI** that manages document processing, translation orchestration, user authentication, and job management.
*   **Frontend**: A **React** single-page application (SPA) built with **Vite** and **TypeScript** that provides a user interface for uploading documents, monitoring translation progress, and managing glossaries.

## 2. Architecture

The system is designed with a service-oriented architecture, featuring a decoupled frontend, a backend API, and a worker process for handling long-running translation tasks.

### Backend Architecture

*   **Framework**: FastAPI (Asynchronous)
*   **Entrypoint**: `backend/api/main.py`
*   **Core Logic**: The translation process is a sophisticated pipeline orchestrated in the `backend/translation/` directory. It involves:
    1.  **Ingestion**: Documents are converted into a common `docx` format and then parsed into an Intermediate Representation (IR) that preserves formatting (`backend/translation/ingestion/`).
    2.  **Chunking**: The document's text is split into manageable, context-aware chunks for the LLM, while respecting sentence and paragraph boundaries (`backend/translation/chunking/`).
    3.  **Translation**: A central `Orchestrator` sends chunks sequentially to an LLM, managing a "rolling glossary" to ensure consistency (`backend/translation/orchestrator.py`).
    4.  **Reconstruction**: The translated text is re-inserted into the IR, preserving the original document's exact structure and styling (`backend/translation/reconstruction/`).
    5.  **Export**: The final document is generated in the desired output format (`backend/translation/export/`).
*   **Database**: **SQLAlchemy** with an async driver (`aiosqlite`) is used for the database, with models defined in `backend/models/`. The planned production database is PostgreSQL.
*   **Configuration**: Application settings are managed via Pydantic Settings in `backend/core/config.py` and can be customized with a `.env` file.

### Frontend Architecture

*   **Framework**: React (using Vite)
*   **Language**: TypeScript
*   **Entrypoint**: `frontend/src/main.tsx` initializes the app, with `frontend/src/App.tsx` defining the core routing.
*   **State Management**:
    *   **Server State**: **TanStack Query** (`@tanstack/react-query`) is used for fetching, caching, and managing data from the backend API.
    *   **Client State**: **Zustand** is used for managing global client-side state, particularly for authentication (`frontend/src/stores/authStore.ts`).
*   **Routing**: **React Router** is used for all client-side routing, with protected routes to secure parts of the application.
*   **Styling**: **Tailwind CSS** is used for styling, with custom components built on top.
*   **API Interaction**: **Axios** is used as the HTTP client for communicating with the backend API. The client is configured in `frontend/src/api/client.ts`.

## 3. Key Dependencies

### Backend (`backend/pyproject.toml`)
- **Web Framework**: `fastapi`, `uvicorn`
- **Database**: `sqlalchemy[asyncio]`, `aiosqlite`
- **Data Validation**: `pydantic`, `pydantic-settings`
- **Authentication**: `passlib[bcrypt]`, `python-jose[cryptography]`
- **Document Processing**: `python-docx`, `pdf2docx`
- **LLM Interaction**: `openai`, `tiktoken`

### Frontend (`frontend/package.json`)
- **Framework**: `react`, `react-dom`
- **Build Tool**: `vite`
- **Routing**: `react-router-dom`
- **Server State**: `@tanstack/react-query`
- **Client State**: `zustand`
- **HTTP Client**: `axios`
- **Styling**: `tailwindcss`
- **Form Handling**: `react-hook-form`, `zod`

## 4. Development Setup & Running

Refer to the `README.md` for detailed, step-by-step instructions.

### Backend Quickstart

1.  **Navigate to backend**: `cd backend`
2.  **Install dependencies**: `uv sync`
3.  **Run dev server**: `uv run uvicorn api.main:app --reload`
    *   The API will be live at `http://localhost:8000`.
    *   API docs (Swagger UI) are at `http://localhost:8000/docs`.

### Frontend Quickstart

1.  **Navigate to frontend**: `cd frontend`
2.  **Install dependencies**: `npm install` (or `bun install`)
3.  **Run dev server**: `npm run dev`
    *   The web application will be live at `http://localhost:5173`.

## 5. Building and Code Standards

### Building for Production

*   **Frontend**: `npm run build`
*   **Backend**: The backend is a Python application and doesn't require a "build" step in the same way the frontend does. It can be deployed using a production-grade ASGI server like Uvicorn with Gunicorn.

### Linting and Formatting

*   **Backend**: The project uses **Ruff** for linting.
    *   Run linter: `ruff check .`
*   **Frontend**: The project uses **ESLint**.
    *   Run linter: `npm run lint`

The project has established conventions that should be followed. Analyze the surrounding code before making changes.
