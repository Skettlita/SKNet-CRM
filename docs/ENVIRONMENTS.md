# Entornos y despliegue

DEV usa `develop` en la laptop. TEST usa `test` en Ubuntu y sirve para validar el laboratorio GNS3. PROD queda reservado para `main`. Cada entorno usa su propio proyecto Compose, base PostgreSQL, volúmenes, secretos, cuentas y recursos WireGuard. Los ensayos destructivos usan una instancia temporal de QA. Mantén los archivos `.env.dev`, `.env.test` y `.env.prod` fuera de Git.

## Aplicar cambios en DEV

En PowerShell, usa el `.env.dev` existente. El arranque del backend aplica migraciones y el siguiente comando permite hacerlo explícitamente sin detener PostgreSQL.

```powershell
docker compose -p sknet-dev --env-file .env.dev -f compose.yaml -f compose.dev.yaml exec backend alembic upgrade head
docker compose -p sknet-dev --env-file .env.dev -f compose.yaml -f compose.dev.yaml up -d --build --no-deps --wait backend frontend provisioner
docker compose -p sknet-dev --env-file .env.dev -f compose.yaml -f compose.dev.yaml exec backend alembic current
docker compose -p sknet-dev --env-file .env.dev -f compose.yaml -f compose.dev.yaml ps
```

La versión esperada es `0013_collector_upgrades`. Para preparar una nueva imagen del collector, constrúyela con la etiqueta definida en `SKNET_COLLECTOR_IMAGE` de DEV. Cambiar esa etiqueta deja la imagen como candidata y el panel SaaS permite pedir el cambio para un collector concreto en una ventana autorizada. Usa una instalación separada para probar reemplazo y reversión.

## Instalación inicial en Ubuntu TEST

Instala Docker Engine con el plugin `docker compose`. Copia `.env.test.example` a `.env.test` y completa la contraseña de PostgreSQL. Conserva `WEB_BIND=127.0.0.1` cuando el proxy HTTPS esté en la misma VM. El perfil base permite validar CRM, compilación y migraciones antes de habilitar la conectividad.

```sh
dc() { docker compose -p sknet-test --env-file .env.test -f compose.yaml -f compose.test.yaml "$@"; }
dc config --quiet
dc build
dc up -d --wait
dc exec -T backend alembic current
dc ps
curl -fsS http://127.0.0.1:8081/api/v1/health
```

Para habilitar WireGuard y RouterOS, completa adicionalmente los valores de `compose.test-routeros.yaml` que figuran en la plantilla. Elige los pools Docker y WireGuard, el intervalo UDP y la subred de administración sin solaparlos con rutas de GNS3, redes locales, otras instalaciones o redes autorizadas de los ISP. El destino NAT debe ser la IP de Ubuntu que recibe UDP. Configura el origen web HTTPS en `SKNET_ORIGIN` y conserva cookies seguras. Monta la CA emisora y el archivo de contraseña con permisos restringidos en el host. Aplica en Ubuntu la política de egreso que permita desde la subred de administración solo el HTTPS del router y, si corresponde, el DNS necesario. Verifica la política efectiva de Docker para tráfico publicado y reenviado. [Filtrado y firewall de Docker](https://docs.docker.com/engine/network/packet-filtering-firewalls/)

La red de gestión del overlay conecta únicamente al provisioner. PostgreSQL permanece en la red privada `data`, el backend expone sockets Unix a través de volúmenes y solo el provisioner monta el socket Docker. Docker crea una red propia por collector y publica únicamente el puerto UDP de su reserva.

```sh
dc() { docker compose -p sknet-test --env-file .env.test -f compose.yaml -f compose.test.yaml -f compose.test-routeros.yaml "$@"; }
dc config --quiet
docker build -t sknet-collector:test monitoring/collector
dc build
dc up -d --wait
dc exec -T backend alembic current
dc exec -T provisioner python -m provisioner --check
dc logs --tail 80 provisioner
docker ps --filter label=sknet.installation=sknet-test
```

Usa en el comando `docker build` la etiqueta configurada para TEST. Comprueba en el panel SaaS el estado de **Collectors**, **Trabajos** y **Recursos de red**. En el ISP, confirma el handshake y autoriza los destinos de prueba antes de activar ICMP. Los pasos del router, WireGuard y actualización controlada están en [Aprovisionamiento](PROVISIONING.md).

## Actualizar Ubuntu TEST

Conserva los volúmenes de PostgreSQL, del provisioner y de cada collector. Antes de actualizar, prepara una copia protegida de PostgreSQL y una copia controlada de los volúmenes que contienen claves y estado persistente. Verifica la restauración en un entorno aislado. Conserva una etiqueta local de respaldo para la imagen anterior del collector.

```sh
umask 077
dc exec -T postgres sh -c 'pg_dump -Fc -U "$POSTGRES_USER" "$POSTGRES_DB"' > sknet-test-pre-update.dump
dc build
dc run --rm --no-deps --entrypoint alembic backend upgrade head
dc up -d --no-deps --wait backend frontend provisioner
dc exec -T backend alembic current
```

El paso de migración aplica el esquema desde la imagen recién construida. Deja funcionar el collector con su contenedor actual hasta solicitar una actualización individual. Para una demostración sin Internet, conserva las imágenes base y de la aplicación antes de trasladar el laboratorio.
