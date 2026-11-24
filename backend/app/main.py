from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Request, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db import create_database_engine, create_session_factory


class Health(BaseModel):
    status: Literal["ok", "unavailable"]
    database: Literal["ok", "unavailable"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = create_database_engine()
    app.state.database = create_session_factory(engine)
    try:
        yield
    finally:
        engine.dispose()


app = FastAPI(title="SKNet API", version="0.1.0", lifespan=lifespan)


@app.get("/api/v1/health", response_model=Health, responses={503: {"model": Health}})
def health(request: Request, response: Response) -> Health:
    response.headers["Cache-Control"] = "no-store"
    try:
        with request.app.state.database() as session:
            session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        response.status_code = 503
        return Health(status="unavailable", database="unavailable")
    return Health(status="ok", database="ok")
