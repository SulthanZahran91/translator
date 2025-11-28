# Doc Translator

A full-stack application for translating documents (PDF, DOCX) from Korean to English using Large Language Models (LLM).

## Features

-   **Document Upload**: Supports PDF and DOCX formats.
-   **Automated Translation**: Uses LLMs for high-quality Korean-to-English translation.
-   **Glossary Support**: Maintain consistency with custom glossaries.
-   **Job Management**: Track translation progress and download results.
-   **Authentication**: Secure user access.

## Tech Stack

### Backend
-   **Language**: Python 3.11+
-   **Package Manager**: uv
-   **Framework**: FastAPI
-   **Database**: SQLite (via SQLAlchemy + aiosqlite)
-   **LLM Integration**: OpenAI Client (Compatible with OpenAI API and local LLM servers)
-   **Document Processing**: `python-docx`, `pdf2docx`
-   **Authentication**: JWT (python-jose, passlib)

### Frontend
-   **Framework**: React (Vite)
-   **Language**: TypeScript
-   **Styling**: Tailwind CSS
-   **State Management**: Zustand, React Query (@tanstack/react-query)
-   **Form Handling**: React Hook Form + Zod
-   **HTTP Client**: Axios

## Prerequisites

-   Python 3.11 or higher
-   [uv](https://github.com/astral-sh/uv) (for backend package management)
-   Node.js v18 or higher
-   Git

## Setup & Installation

### 1. Clone the repository

```bash
git clone <repository-url>
cd doc-translator
```

### 2. Backend Setup

The backend uses `uv` for dependency management.

```bash
cd backend
uv sync
```

This will create a virtual environment at `backend/.venv` and install all dependencies.

### 3. Frontend Setup

```bash
cd frontend
npm install
# or if you use bun
# bun install
```

## Configuration

### Backend Configuration

The backend uses environment variables for configuration. You can create a `.env` file in the `backend` directory or the root directory, or rely on defaults for local development.

Key configuration options (default values shown):

```ini
APP_NAME=Document Translator
DEBUG=False
SECRET_KEY=change-this-in-production-use-a-real-secret-key

# LLM Settings (Defaults for local LLM)
LLM_API_URL=http://localhost:8000/v1
LLM_API_KEY=not-needed-for-local
LLM_MODEL=exaone

# Database
DATABASE_URL=sqlite+aiosqlite:///./storage/db/translator.db

# Storage
STORAGE_PATH=./storage
```

See `backend/core/config.py` for all available options.

## Running the Application

### Start the Backend

Run the following command from the `backend` directory:

```bash
# Using uv to run the application (automatically uses the virtual environment)
uv run uvicorn api.main:app --reload
```

The API will be available at `http://localhost:8000`.
-   API Documentation: `http://localhost:8000/docs`

### Start the Frontend

Run the following command from the `frontend` directory:

```bash
cd frontend
npm run dev
```

The application will be available at `http://localhost:5173`.
