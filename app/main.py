from dotenv import load_dotenv
load_dotenv()

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.state import AppState
from app.routes import config as config_routes
from app.routes import schema as schema_routes
from app.routes import agent as agent_routes
from app.routes import sessions as session_routes

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.app_state = AppState()
    yield


app = FastAPI(
    title="lyst",
    description="Query your database using natural language",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Routers ----
app.include_router(config_routes.router)
app.include_router(schema_routes.router)
app.include_router(agent_routes.router)
app.include_router(session_routes.router)


# ---- Static files ----
@app.get("/")
def serve_index():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


static_path = Path(__file__).parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=static_path), name="static")
