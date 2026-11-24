import argparse
import sys
from getpass import getpass
from uuid import UUID

from fastapi import HTTPException
from pydantic import ValidationError

from app.auth.accounts import issue_temporary
from app.auth.onboarding import bootstrap_admin
from app.auth.routes import write_operation
from app.auth.schemas import Identity, PasswordPair
from app.auth.security import hasher, identity_active
from app.auth.store import IAM, SAAS, find_identity, person_permissions
from app.db import create_database_engine, create_session_factory


def create_admin(db) -> UUID:
    identity = Identity(
        name=input("Nombre completo: "),
        username=input("Usuario: "),
        email=input("Correo: "),
    )
    secret = PasswordPair(password=getpass("Contraseña: "), confirm_password=getpass("Confirmar contraseña: "))
    password_hash = hasher.hash(secret.password)
    with write_operation(db):
        return bootstrap_admin(db, identity, password_hash)


def reset_admin(db) -> str:
    identifier = input("Usuario o correo SaaS: ").strip()
    with write_operation(db):
        user = find_identity(db, SAAS, identifier)
        if not identity_active(user) or not IAM.issubset(person_permissions(db, SAAS, user["person_id"])):
            raise HTTPException(404, "Administrador SaaS activo no encontrado.")
        return issue_temporary(db, user, actor=None, reason="Recuperación local de emergencia por CLI")


def main() -> int:
    parser = argparse.ArgumentParser(description="Administración local de SKNet")
    parser.add_argument("command", choices=["create-admin", "reset-admin"])
    command = parser.parse_args().command
    if not sys.stdin.isatty():
        print("Usa una terminal interactiva.", file=sys.stderr)
        return 1
    engine = create_database_engine()
    try:
        with create_session_factory(engine)() as db:
            if command == "create-admin":
                create_admin(db)
                print("Administrador SaaS creado.")
            else:
                temporary = reset_admin(db)
                print("Contraseña temporal de un solo uso. Vence en 24 horas.")
                print(temporary)
    except HTTPException as error:
        print(error.detail, file=sys.stderr)
        return 1
    except (ValidationError, EOFError, KeyboardInterrupt):
        print("Operación cancelada o datos inválidos. Verifica usuario, correo y contraseña de al menos 12 caracteres.",
              file=sys.stderr)
        return 1
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
