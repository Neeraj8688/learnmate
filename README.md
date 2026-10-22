# LearnMate — AI-Powered Study Assistant

> Learn from your own notes with AI-powered answers, relevant source references, and a simple study-focused interface.

LearnMate is a full-stack study assistant that uses a React frontend, FastAPI backend, and Google Gemini to answer questions using relevant content from study materials. When available, answers include source details such as the document name and page number.

## Demo

<p align="center">
  <a href="https://drive.google.com/file/d/15UKMxMPX4TwChuaApLWG7UxfhQS9dnOD/view?usp=sharing">
    <img src="sample_notes/Screenshot%202026-10-22%20115748.png" alt="LearnMate application demo" width="900"/>
  </a>
</p>

<p align="center"><b>Click the screenshot to watch the demo video.</b></p>

## Features

- **AI study assistant** — Ask questions in natural language.
- **Context-based answers** — Uses relevant content from configured study materials.
- **Source references** — Shows source information when available.
- **Formatted responses** — Presents answers with readable Markdown formatting.
- **REST API** — FastAPI backend with interactive Swagger documentation.
- **Docker support** — Run the frontend and backend with Docker Compose.

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React, Vite, JavaScript |
| Backend | Python, FastAPI |
| AI | Google Gemini API |
| API documentation | FastAPI / OpenAPI (Swagger UI) |
| Local development | Docker, Docker Compose |
| Deployment configuration | Vercel (frontend), Render (backend) |

## Project Structure

```text
learnmate/
├── backend/                 # FastAPI backend
├── frontend/                # React + Vite frontend
├── sample_notes/            # Sample study materials and demo screenshot
├── scripts/                 # Helper scripts
├── tests/                   # Automated tests
├── .env.example             # Example environment configuration
├── .gitignore
├── Caddyfile
├── docker-compose.yml
├── docker-compose.prod.yml
├── render.yaml
├── DEPLOY.md
└── README.md
```

## Run Locally with Docker

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- A Google Gemini API key

### 1. Clone the repository

```bash
git clone https://github.com/Neeraj8688/learnmate.git
cd learnmate
```

### 2. Configure environment variables

Create a local `.env` file from the example.

**Windows PowerShell**
```powershell
Copy-Item .env.example .env
```

**macOS / Linux**
```bash
cp .env.example .env
```

Add your Gemini API key to `.env` using the variable name expected by `.env.example`:

```env
GEMINI_API_KEY=your_gemini_api_key
```

Keep your real `.env` file private. Never commit API keys, passwords, or other secrets to GitHub.

### 3. Build and start

```bash
docker compose up --build -d
```

Open the application and API documentation:

- **Frontend:** http://localhost:5173
- **Backend API docs:** http://localhost:8000/docs

### 4. Stop the application

```bash
docker compose down
```

To check running containers or inspect backend logs:

```bash
docker compose ps
docker compose logs --tail=100 backend
```

## How It Works

```text
Student question
      │
      ▼
React + Vite frontend
      │
      ▼
FastAPI backend
      │
      ▼
Retrieve relevant study content
      │
      ▼
Google Gemini generates an answer
      │
      ▼
Answer with source references, when available
```

## Deployment

Deployment configuration is provided for a Vercel frontend and a Render backend. See [`DEPLOY.md`](DEPLOY.md) for deployment details. Configure the frontend to use the deployed backend URL and set the Gemini API key as a private backend environment variable.

## Author

**Neeraj Kumar B**  
B.Tech — Computer Science & Engineering (AI & ML)

- GitHub: [Neeraj8688](https://github.com/Neeraj8688)
- LinkedIn: [Bevara Neeraj Kumar](https://www.linkedin.com/in/bevara-neeraj-kum)

---

If you find LearnMate useful, consider giving the repository a ⭐.