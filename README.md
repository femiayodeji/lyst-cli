# lyst

A web API that lets you query your database using plain English. Ask a question, get SQL + results + a summary — no SQL writing required.

Powered by LLMs (via [LiteLLM](https://github.com/BerriAI/litellm)) and [SQLAlchemy](https://www.sqlalchemy.org/), lyst connects to your database, reads its schema, and generates accurate queries from natural language.

## Features

- **Plain English to SQL** — ask questions in natural language, get SQL queries and results
- **Multi-provider LLM support** — works with Gemini, Anthropic, OpenAI, Groq, and any LiteLLM-compatible provider
- **Database agnostic** — connects to PostgreSQL, MySQL, SQLite, and any SQLAlchemy-supported database
- **Auto schema introspection** — reads your database schema for accurate query generation
- **Conversation context** — multi-turn conversations with full history  
- **Session management** — organize conversations into named sessions
- **Streaming responses** — real-time streaming for interactive experience
- **Markdown formatting** — responses rendered with full markdown support

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager
- A Google Gemini API key (get one at [Google AI Studio](https://aistudio.google.com/apikey))

## Setup

1. **Clone and install**
	```bash
	git clone <repo-url>
	cd lyst
	uv sync
	```

2. **Configure environment variables**
	
	Create a `.env` file in the project root:
	```env
	LYST_LLM_API_KEY=your-gemini-api-key
	LYST_DB_CONNECTION=postgresql://user:pass@localhost/mydb
	```

3. **Start the server**
	```bash
	uvicorn app.api:app --reload
	```

The API will be available at `http://localhost:8000` with interactive docs at `/docs`.

## Configuration

All configuration is done via environment variables in your `.env` file:

| Variable | Description | Default |
|----------|-------------|---------|
| `LYST_LLM_API_KEY` | Your LLM provider API key | (required) |
| `LYST_DB_CONNECTION` | Database connection string | (required) |
| `LYST_LLM_PROVIDER` | LLM provider name | `gemini` |
| `LYST_LLM_MODEL` | Model to use | `gemini/gemini-2.0-flash` |
| `LYST_LLM_BASE_URL` | Optional custom base URL | (provider-specific) |
| `LYST_STREAM` | Enable streaming responses | `true` |

### Provider Examples

**Gemini** (default):
```env
LYST_LLM_PROVIDER=gemini
LYST_LLM_MODEL=gemini/gemini-2.0-flash
LYST_LLM_API_KEY=your-gemini-api-key
```

**Anthropic**:
```env
LYST_LLM_PROVIDER=anthropic
LYST_LLM_MODEL=anthropic/claude-3-5-sonnet-20241022
LYST_LLM_BASE_URL=https://api.anthropic.com
LYST_LLM_API_KEY=your-anthropic-api-key
```

**OpenAI**:
```env
LYST_LLM_PROVIDER=openai
LYST_LLM_MODEL=openai/gpt-4o
LYST_LLM_BASE_URL=https://api.openai.com/v1
LYST_LLM_API_KEY=your-openai-api-key
```

**Groq**:
```env
LYST_LLM_PROVIDER=groq
LYST_LLM_MODEL=groq/llama-3.3-70b-versatile
LYST_LLM_BASE_URL=https://api.groq.com/openai/v1
LYST_LLM_API_KEY=your-groq-api-key
```

## API Endpoints

All configuration is read from environment variables. The API is used for querying and managing conversations.

| Method | Endpoint                         | Description                              |
|--------|----------------------------------|------------------------------------------|
| GET    | `/health`                        | Health check and configuration status    |
| GET    | `/config`                        | View current configuration (from .env)   |
| GET    | `/schema`                        | Get database schema info                 |
| POST   | `/schema/load`                   | Load and cache database schema           |
| POST   | `/agent (or `/agent/stream`)     | Send a message to the agent              |
| POST   | `/execute-sql`                   | Execute raw SQL query                    |
| GET    | `/sessions`                      | List all conversation sessions           |
| POST   | `/sessions`                      | Create a new session                     |
| GET    | `/sessions/{id}`                 | Get session details and messages         |
| PUT    | `/sessions/{id}/activate`        | Switch to a session                      |
| DELETE | `/sessions/{id}`                 | Delete a session                         |
| GET    | `/history`                       | Get conversation history                 |
| PUT    | `/history`                       | Save message history                     |
| DELETE | `/history`                       | Clear conversation history               |

## Usage

**Query example:**

```bash
curl -X POST http://localhost:8000/agent/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "Show total sales by month"}'
```

**Response (streaming):**

```
data: {"type":"status","content":"Querying database..."}
data: {"type":"sql","content":"SELECT DATE_TRUNC('month', created_at) as month, SUM(amount) as total FROM sales GROUP BY month ORDER BY month"}
data: {"type":"result","columns":["month","total"],"rows":[["2024-01",50000],["2024-02",42000]],"success":true}
data: {"type":"message_complete","content":"Sales by month show January with $50,000 and February with $42,000."}
data: {"type":"done"}
```

**To continue a conversation**, pass the returned message history:

```bash
curl -X POST http://localhost:8000/agent/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "What about last year?", "history": [...history from previous query...]}'
```

### Web UI

The web interface at `http://localhost:8000` provides:

- **Interactive chat** — ask questions about your database in natural language
- **Multi-session support** — organize conversations into named sessions
- **Streaming results** — see query execution and results in real-time
- **SQL display** — view generated SQL queries alongside results
- **Response rendering** — markdown-formatted assistant responses with syntax highlighting

## License

MIT
