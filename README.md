# TCR Agent

## Developer Setup

### Prerequisites
Before starting, install **`uv`**, which is used to manage the Python environment and dependencies.

Installation guide: https://docs.astral.sh/uv/

---

### Backend Setup

1. Navigate to the server directory:

```bash
cd server
uv sync
```
2. Start the backend server:

```bash
uv run uvicorn main:app --reload --port 3001
```

The backend will run at: `http://localhost:3001`

### Frontend Setup

Navigate to the frontend app directory:
```bash
cd app
```

Install dependencies:
```bash
npm install
```

Start the development server:
```bash 
npm run dev
```

The frontend will run at the URL printed in the terminal (commonly `http://localhost:5173`).

## Project Structure
```bash
.
├── data/     # Data files (not included in this repository)
├── server/   # FastAPI backend
└── app/      # React based Frontend web application
```

## Development Notes
- Backend framework: **FastAPI**
- ASGI server: **Uvicorn**
- Python environment and dependency management: **uv**
- Frontend runs with a development server that supports hot reload.
- Start the backend first, then run the frontend to ensure API requests work correctly.

> [!IMPORTANT]
> **MacOS** may block `localhost`, you may need to use `127.0.0.1` instead, which could require you to change the vite proxy.   