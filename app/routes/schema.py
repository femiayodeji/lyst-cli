from fastapi import APIRouter, Depends, HTTPException, Query

from app.db.engine import get_schema, get_db_type
from app.db.schema import cached_schema, cached_db_type
from app.state import AppState, get_state

router = APIRouter()


@router.get("/schema")
def get_database_schema(state: AppState = Depends(get_state)):
    try:
        return {"db_schema": get_schema(state), "db_type": get_db_type(state)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get schema: {e}")


@router.post("/schema/load")
def load_schema(
    force: bool = Query(False, description="Clear cache and reload from the database"),
    state: AppState = Depends(get_state),
):
    try:
        if force:
            state.clear_schema_cache()
        schema = cached_schema(state)
        db_type = cached_db_type(state)
        return {
            "message": "Schema loaded",
            "db_type": db_type,
            "tables_count": schema.count("Table:"),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load schema: {e}")
