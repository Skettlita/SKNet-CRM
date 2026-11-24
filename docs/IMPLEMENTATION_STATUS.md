# Estado de implementación

## Fase 1 · Fundación DEV

- Los dos ZIP se extrajeron en un workspace vacío. El código aprobado quedó en `references/v0-prototype/`. El export usa Next.js, incluye datos de demostración y no trae un archivo de licencia separado. Se conserva como referencia y se portan las piezas visuales al runtime Vite.
- El esquema de referencia combina DDL y catálogo. Alembic versionará ambos por separado para verificar la actualización con datos. Se mantienen las claves compuestas, los índices parciales y las vistas; los controles de acceso y reglas de negocio siguen pendientes en sus respectivas fases.
- Plan: configurar los cuatro servicios DEV, portar el layout y conectar el estado de la API, verificar la migración y el aislamiento básico de las relaciones, y documentar el arranque. TEST y PROD tendrán configuraciones separadas para su futura validación.

### Implementado

- Git local en `develop`, Compose base y overlays DEV, TEST y PROD con proyectos independientes. Dockerfiles para backend, frontend y provisioner. En DEV solo Vite se publica en loopback, PostgreSQL utiliza una red privada y el socket Docker se monta únicamente en el provisioner.
- FastAPI y SQLAlchemy con `GET /api/v1/health`. Devuelve HTTP 200 con una conexión disponible y 503 si falla la consulta, sin detalles internos. El backend aplica Alembic antes de servir.
- Migraciones `0001_schema` y `0002_catalog`. Se revisaron las claves compuestas por empresa, el ámbito de identidad, las dependencias entre esquemas, los índices parciales, las vistas y el catálogo. El DDL ejecutable se conserva dentro de las revisiones y Alembic ejecuta cada revisión en transacción. El esquema de referencia conserva su papel documental.
- React, TypeScript, Vite y Tailwind. Se adaptaron logo, sidebar plegable, topbar, tabla compacta, estados y botón basado en el componente shadcn del prototipo. El dashboard consume el endpoint real mediante un proxy del mismo origen. La barra lateral muestra el módulo disponible en esta fase.

### Validación realizada en Windows

| Comprobación | Resultado |
|---|---|
| `npm --prefix frontend run build` | TypeScript y build de Vite completados. |
| `python -m pytest -q` con un PostgreSQL 17.11 temporal | 4 pruebas aprobadas. Se comprobó HTTP 200 y 503, migración desde cero, segunda ejecución sin duplicación, 78 tablas, 9 esquemas, 5 vistas, TRIAL a Bs 0 sin vencimiento y registro apagado. Con datos en revisión 0001 se verificó su conservación y el rechazo de una referencia entre empresas. Starlette emitió una advertencia de deprecación por un alias de AnyIO. |
| `docker compose --env-file .env.dev -f compose.yaml -f compose.dev.yaml up --build -d --wait` | Los cuatro servicios quedaron saludables en Docker Desktop, con PostgreSQL 17.12 y `alembic current` en `0002_catalog (head)`. Se corrigió el chequeo del frontend DEV para usar Node en la imagen de Vite. |
| `GET http://127.0.0.1:5173/api/v1/health` | Respuesta `{"status":"ok","database":"ok"}` a través de Vite. |
| Dashboard en navegador | Revisados logo, tabla, menú plegable y botón Actualizar. La API y PostgreSQL mostraron Disponible. |
| `docker compose config --quiet` | Los overlays de TEST y PROD se validaron con valores de prueba en memoria. La ejecución correspondió a DEV. |

### Pendientes

- Ejecutar y verificar en Ubuntu cuando se disponga del entorno. TEST y PROD requieren validación de sus imágenes y operación antes de desplegar.
- La siguiente fase incorpora login separado para ISP y SaaS, signup configurable, sesiones, creación segura del primer administrador, roles y permisos. Mantener el diseño de v0 y probar el aislamiento en la API, además de las restricciones SQL ya verificadas.
- El provisioner verifica Docker. La conexión RouterOS, los collectors, el monitoreo y las gráficas con Recharts corresponden a las fases posteriores.
