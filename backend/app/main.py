from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.auth.routes import admin, isp
from app.platform.routes import admin as platform_admin, isp as platform_isp
from app.db import create_database_engine, create_session_factory


class Health(BaseModel):
    status: Literal["ok", "unavailable"]
    database: Literal["ok", "unavailable"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = create_database_engine()
    try:
        yield {"database": create_session_factory(engine)}
    finally:
        engine.dispose()


app = FastAPI(title="SKNet API", version="0.3.0", lifespan=lifespan)
app.include_router(isp)
app.include_router(admin)
app.include_router(platform_admin)
app.include_router(platform_isp)


@app.middleware("http")
async def private_responses(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(("/api/v1/isp/", "/api/v1/admin/")):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(RequestValidationError)
def invalid_input(request: Request, error: RequestValidationError):
    errors = error.errors()
    if any(item["type"] == "value_error" and item["msg"].endswith("contraseñas no coinciden.") for item in errors):
        message = "Las contraseñas no coinciden."
    else:
        fields = {
            "name": "nombre", "username": "usuario", "email": "correo", "company": "empresa",
            "phone": "teléfono", "tax_id": "NIT", "password": "contraseña",
            "confirm_password": "confirmación de contraseña", "identifier": "usuario o correo",
            "monthly_price": "precio mensual", "max_users": "límite de usuarios",
            "trial_days": "duración de la prueba",
        }
        labels = [fields[item["loc"][-1]] for item in errors if item["loc"] and item["loc"][-1] in fields]
        message = "Revisa estos campos: " + ", ".join(dict.fromkeys(labels)) + "." if labels else "Revisa los datos ingresados."
    return JSONResponse(status_code=422, content={"detail": message})


@app.get("/api/v1/health", response_model=Health, responses={503: {"model": Health}})
def health(request: Request, response: Response) -> Health:
    response.headers["Cache-Control"] = "no-store"
    try:
        with request.state.database() as session:
            session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        response.status_code = 503
        return Health(status="unavailable", database="unavailable")
    return Health(status="ok", database="ok")
