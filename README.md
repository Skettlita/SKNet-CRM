# SKNet · CRM y monitoreo para ISP

La fundación DEV incluye una API FastAPI, PostgreSQL 17 con migraciones Alembic, un frontend React y Vite basado en el diseño aprobado y un provisioner que comprueba el acceso a Docker. El dashboard inicial muestra el estado de la API y PostgreSQL.

## Requisitos

- Windows con Docker Desktop configurado para contenedores Linux, o Ubuntu con Docker Engine y el complemento Compose v2.
- Git para trabajar con el código. Para compilar o probar fuera de contenedores se necesitan Node.js 24, Python 3.13 y PostgreSQL 17.
- Puerto local 5173 disponible o un valor distinto para `WEB_PORT` en `.env.dev`.

## Arranque DEV

**Windows PowerShell**, desde la raíz del proyecto.

```powershell
if (!(Test-Path .env.dev)) {
  $seed = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
  (Get-Content .env.dev.example) -replace '^POSTGRES_PASSWORD=$', "POSTGRES_PASSWORD=$seed" |
    Set-Content -Encoding ascii .env.dev
}
docker compose --env-file .env.dev -f compose.yaml -f compose.dev.yaml up -d --build --wait
docker compose --env-file .env.dev -f compose.yaml -f compose.dev.yaml ps
Invoke-RestMethod http://127.0.0.1:5173/api/v1/health
```

**Ubuntu**, desde la raíz del proyecto.

```bash
if [ ! -f .env.dev ]; then
  umask 077
  sed "s/^POSTGRES_PASSWORD=$/POSTGRES_PASSWORD=$(openssl rand -hex 32)/" .env.dev.example > .env.dev
fi
docker compose --env-file .env.dev -f compose.yaml -f compose.dev.yaml up -d --build --wait
docker compose --env-file .env.dev -f compose.yaml -f compose.dev.yaml ps
curl --fail http://127.0.0.1:5173/api/v1/health
```

Abre [Dashboard DEV](http://127.0.0.1:5173/). Si cambiaste `WEB_PORT`, ajusta el puerto también en la URL de verificación. El frontend reenvía `/api` al backend y PostgreSQL permanece en una red privada. El provisioner comprueba Docker mediante el socket y espera la fase de aprovisionamiento.

## Migrar, consultar y detener

El backend aplica `alembic upgrade head` antes de arrancar. En DEV, al incorporar una migración, reinicia el backend para aplicarla. Alembic es la única vía de inicialización y actualización del esquema.

```sh
docker compose --env-file .env.dev -f compose.yaml -f compose.dev.yaml restart backend
docker compose --env-file .env.dev -f compose.yaml -f compose.dev.yaml exec backend alembic current
docker compose --env-file .env.dev -f compose.yaml -f compose.dev.yaml logs --tail 80 backend
docker compose --env-file .env.dev -f compose.yaml -f compose.dev.yaml stop
```

El volumen PostgreSQL conserva los datos. La contraseña de `.env.dev` se usa al inicializar el volumen. Si necesitas rotarla después, actualiza la credencial en PostgreSQL y su configuración de forma coordinada. El esquema de [referencia](database/reference/schema.sql) sirve para diseño y revisión.

## Pruebas locales

```sh
npm --prefix frontend ci
npm --prefix frontend run build
python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
# Ubuntu
.venv/bin/python -m pip install -r backend/requirements-dev.txt
.venv/bin/python -m pytest
```

Para incluir las pruebas de migración, configura `SKNET_TEST_DATABASE_URL` en la sesión con la URL de un servidor **PostgreSQL 17 aislado para pruebas**, un usuario con permiso `CREATEDB` y una base de mantenimiento como `postgres`. La suite crea y elimina únicamente sus bases temporales con nombre propio. Sin esa variable solo se prueban las respuestas HTTP de salud.

## Entornos y referencia

`compose.yaml` se combina con `compose.dev.yaml`, `compose.test.yaml` o `compose.prod.yaml`. Cada overlay define un nombre de proyecto, redes y volúmenes independientes por proyecto y un puerto web distinto. Usa un archivo de variables separado por ambiente. TEST y PROD quedan preparados para validación posterior. Consulta [entornos](docs/ENVIRONMENTS.md) y [estado de implementación](docs/IMPLEMENTATION_STATUS.md).

La interfaz de referencia está en `references/v0-prototype/`. Las decisiones de diseño, arquitectura y alcance se documentan en `docs/`. La siguiente fase incorpora identidad SaaS e ISP, sesiones, registro y permisos.
