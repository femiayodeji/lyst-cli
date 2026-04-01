# lyst

A web API that lets you query your database using plain English. Ask a question, get SQL + results + a summary — no SQL writing required.

Powered by LLMs (via [LiteLLM](https://github.com/BerriAI/litellm)) and [SQLAlchemy](https://www.sqlalchemy.org/), lyst connects to your database, reads its schema, and generates accurate queries from natural language.

## Features

- **Plain English to SQL** — ask questions in natural language, get SQL queries and results
- **Quick Chat mode** — ask questions about your database without executing queries
- **Multi-provider LLM support** — works with Anthropic, OpenAI, and any LiteLLM-compatible provider
- **Database agnostic** — connects to PostgreSQL, MySQL, SQLite, and any SQLAlchemy-supported database
- **Auto schema introspection** — reads your database schema for accurate query generation
- **Conversation context** — pass history for follow-up questions
- **Streaming responses** — real-time streaming for both query and chat modes
- **Markdown formatting** — chat responses rendered with full markdown support

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager
- An API key for your LLM provider (e.g. `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`)

## Setup

1. **Clone and install**
	```bash
	git clone <repo-url>
	cd lyst
	uv sync
	```

2. **Set your LLM API key**
	```bash
	export LYST_LLM_API_KEY=sk-...
	```

3. **Start the server**
	```bash
	uvicorn app.api:app --reload
	```

The API will be available at `http://localhost:8000` with interactive docs at `/docs`.

## Configuration

Configure via the API endpoints or create `~/.config/lyst/config.json`:

```json
{
    "llm": {
        "provider": "anthropic",
        "model": "anthropic/claude-sonnet-4-20250514",
        "base_url": "https://api.anthropic.com",
        "stream": false
    },
    "db": {
        "connection": "postgresql://user:pass@localhost/mydb"
    }
}
```

## API Endpoints

| Method | Endpoint        | Description                           |
|--------|-----------------|---------------------------------------|
| GET    | `/health`       | Health check and config status        |
| GET    | `/config`       | Get current configuration             |
| PUT    | `/config`       | Update full configuration             |
| PUT    | `/config/llm`   | Update LLM configuration only         |
| PUT    | `/config/db`    | Update database configuration only    |
| GET    | `/schema`       | Get database schema                   |
| POST   | `/query`        | Ask a question in plain English       |
| POST   | `/query/stream` | Streaming version of `/query`         |
| POST   | `/chat`         | Quick chat about your database        |
| POST   | `/chat/stream`  | Streaming version of `/chat`          |
| GET    | `/history`      | Get persisted conversation history    |
| PUT    | `/history`      | Save conversation history             |
| DELETE | `/history`      | Clear conversation history            |

## Usage

**Query example:**

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Show total sales by month"}'
```

**Response:**

```json
{
  "sql": "SELECT DATE_TRUNC('month', created_at) as month, SUM(amount) as total FROM sales GROUP BY month ORDER BY month",
  "columns": ["month", "total"],
  "rows": [["2024-01", 50000], ["2024-02", 42000]],
  "summary": "Sales by month show January with $50,000 and February with $42,000.",
  "history": [...],
  "success": true
}
```

**Follow-up questions** — pass the returned `history` array:

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What about last year?", "history": [...]}'
```

### Chat Mode

Use chat mode to ask questions about your database schema, get help with the API, or discuss your data without executing queries:

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What tables do I have?"}'
```

**Response:**

```json
{
  "response": "Based on your database schema, you have the following tables:\n\n- **users** - stores user accounts...",
  "history": [...]
}
```

### Web UI

The built-in web interface at `http://localhost:8000` provides:

- **Mode toggle** — switch between Query mode (execute SQL) and Chat mode (discuss your data)
- **Streaming responses** — see results as they're generated
- **Markdown rendering** — chat responses display with formatted headings, lists, and code blocks

## License

MIT
