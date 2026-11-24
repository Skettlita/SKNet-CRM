# SKNet · CRM y monitoreo para ISP

La fundación DEV incluye una API FastAPI, PostgreSQL 17 con migraciones Alembic, un frontend React y Vite basado en el diseño aprobado y un provisioner que comprueba el acceso a Docker. El entorno DEV incorpora además autenticación, registro ISP y gestión de usuarios y permisos. El panel SaaS incluye empresas, planes versionados, suscripciones, soporte, auditoría y un dashboard con datos de PostgreSQL.

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

Abre [Login ISP](http://127.0.0.1:5173/login) o [Login SaaS](http://127.0.0.1:5173/admin/login). Si cambiaste `WEB_PORT`, ajusta el puerto también en la URL de verificación. El frontend reenvía `/api` al backend y PostgreSQL permanece en una red privada. El provisioner comprueba Docker y procesa las solicitudes de conectividad en segundo plano.

`WEB_BIND` define la interfaz en la que DEV publica el frontend. Usa `127.0.0.1` para acceso local o `0.0.0.0` para una prueba desde la LAN. Para acceder desde otro equipo, ajusta `SKNET_ORIGIN` a la URL exacta con la IP o nombre del host y el puerto. `SKNET_UDP_BIND` y `SKNET_WG_ENDPOINT` configuran los collectors por separado.

## Crear el primer administrador SaaS

Con DEV en marcha, ejecuta este comando en una terminal interactiva. Pide nombre completo, usuario, correo y confirmación de la contraseña de al menos 12 caracteres.

```sh
docker compose --env-file .env.dev -f compose.yaml -f compose.dev.yaml exec backend python -m app.cli create-admin
```

Entra en [Login SaaS](http://127.0.0.1:5173/admin/login) con el usuario o el correo. La CLI solo admite la creación inicial. Crea el resto del personal desde **Administración → Usuarios**, con un rol que el operador esté autorizado a asignar.

## Comprobación manual

1. En el panel SaaS, abre **Administración → Configuración**. El registro público está apagado al inicializar la base. Habilítalo y guarda. También puedes registrar una empresa desde **Plataforma → Empresas → Nueva empresa**, aunque el registro público esté apagado.
2. Abre [Registrar empresa](http://127.0.0.1:5173/signup) y completa el formulario. Entra en [Login ISP](http://127.0.0.1:5173/login) con la cuenta creada. El administrador entra a `/app`. La cuenta ISP no inicia sesión en `/admin/login`.
3. En la empresa, crea un rol con **Ver el panel** y **Listar usuarios** desde **Roles y permisos**. Crea un empleado desde **Usuarios** y selecciona ese rol. La contraseña temporal se muestra al crearlo y vence en 24 h.
4. En una ventana privada, entra como empleado y cambia la contraseña temporal. Comprueba que puede listar usuarios de su empresa y que las acciones de edición, alta y administración de roles quedan ocultas.
5. Usa el menú de usuario para cambiar preferencias o cerrar sesión. Para comprobar persistencia, reinicia DEV y vuelve a entrar. El plan de prueba, las empresas, los roles y los usuarios permanecen en PostgreSQL.

El plan TRIAL inicial cuesta Bs 0, sin vencimiento ni límite de usuarios. Los cambios al precio, duración, límites o funcionalidades se guardan como una nueva versión. El registro público y el alta administrativa usan la versión elegida en Configuración. El precio configura las condiciones del plan, sin generar cobros en esta fase.

## Verificación de la administración SaaS

1. En **Plataforma → Planes**, crea un plan con moneda, precio por periodo, duración y límites. Habilita **Usuarios y permisos** y **Soporte de SKNet** según corresponda. Edita sus condiciones y consulta las dos versiones. Los módulos futuros se identifican como no disponibles.
2. En **Administración → Configuración**, selecciona la versión del plan predeterminado y guarda. Con el registro público apagado, comprueba que [Signup](http://127.0.0.1:5173/signup) está cerrado y que **Empresas → Nueva empresa** sigue disponible. Al habilitarlo, Signup muestra las condiciones y aplica la versión elegida.
3. En **Empresas**, busca por nombre o NIT, filtra por estado y abre una ficha. Consulta usuarios y utilización con los permisos respectivos. Suspende y reactiva una empresa de prueba. La suspensión bloquea el acceso ISP y conserva la suscripción, el estado de conectividad y los registros.
4. En **Suscripciones**, abre la asignación inicial, cambia plan o vigencia y consulta el historial. Para iniciar una nueva asignación, cancela primero la anterior. Un límite inferior impide nuevas altas que lo superen, con los registros ya existentes disponibles.
5. Desde el [panel ISP](http://127.0.0.1:5173/app), abre **Contactar SKNet** y envía una solicitud. En el panel SaaS, abre **Administración → Soporte**, filtra, asigna un responsable y responde. Comprueba el historial y que una nota interna aparece solo en SaaS.
6. Abre **Dashboard** y **Auditoría** con el operador autorizado. Los indicadores se calculan a partir de los registros existentes. La auditoría permite consultar cambios de empresa, cuenta, rol, plan, suscripción, configuración y soporte.

## Verificación del CRM empresarial

1. En el [panel ISP](http://127.0.0.1:5173/app), abre **CRM → Clientes → Registrar cliente**. Guarda un cliente sin servicio y verifica su código automático.
2. Crea un **Plan de Internet** y registra otro cliente con **Registrar un servicio contratado**. Elige el plan, comprueba el precio y la moneda, modifica el importe y elige si el sitio usa la dirección del cliente. Registra un servicio existente como activo y un alta nueva como pendiente. Verifica los resultados en las pestañas **Sitios** y **Servicios** de cada ficha.
3. Desde **Sitios** y **Servicios**, agrega otro sitio y otro servicio al mismo cliente. Prueba las pestañas de categorías del catálogo, busca por código o cliente y verifica que el selector de servicios solo muestre sitios del cliente que elegiste.
4. En **Red → Dispositivos**, registra un equipo de infraestructura en un sitio propio, asígnale capacidad **Servidor PPPoE** y selecciónalo como router de acceso de dos servicios PPPoE. Registra un equipo final en el sitio de un abonado y prueba la asociación opcional al servicio. Comprueba que ambos tipos conservan su IP de gestión y sus opciones de monitoreo.
5. Entra con un usuario que solo pueda crear clientes y verifica que el formulario carezca de la opción de contratar un servicio. Para un plan SaaS personalizado, habilita **CRM** y, si corresponde, **Configuración ICMP** en la versión asignada a la empresa.

El límite de clientes se aplica al total registrado. El límite de dispositivos se aplica a los equipos activos reservados para monitoreo o habilitados. Los equipos de inventario lógico que no solicitan monitoreo no consumen ese cupo.

Consulta las reglas del alta integrada, las capacidades de routers de acceso y el tratamiento de datos anteriores en [CRM.md](docs/CRM.md).

## Recuperación

- Desde **Usuarios**, un administrador con permiso puede restablecer otra cuenta de su ámbito. La contraseña temporal es de un solo uso y el cambio es obligatorio. Para un administrador ISP que perdió acceso, el operador autorizado usa **Recuperar acceso ISP** después de verificar su identidad y registrar el motivo.
- Para recuperación de emergencia SaaS, ejecuta `docker compose --env-file .env.dev -f compose.yaml -f compose.dev.yaml exec backend python -m app.cli reset-admin`. El comando solicita el identificador y entrega una contraseña temporal. Las sesiones previas quedan invalidadas.
- Para habilitar recuperación ISP y verificación de correo en DEV, configura `SKNET_SMTP_HOST`, `SKNET_SMTP_FROM` y, si aplica, `SKNET_SMTP_PORT`, `SKNET_SMTP_USER` y `SKNET_SMTP_PASSWORD` en `.env.dev`. Se usa STARTTLS por defecto y TLS directo en el puerto 465. Usa `SKNET_ORIGIN` con la URL real desde la que se abre la app. Recrea el backend con el comando de arranque. El perfil permite solicitar verificación cuando el transporte está configurado.

## Migrar, consultar y detener

El backend aplica `alembic upgrade head` antes de arrancar. En DEV, al incorporar una migración, reinicia el backend para aplicarla. Alembic es la única vía de inicialización y actualización del esquema.

```sh
docker compose --env-file .env.dev -f compose.yaml -f compose.dev.yaml restart backend
docker compose --env-file .env.dev -f compose.yaml -f compose.dev.yaml exec backend alembic current
docker compose --env-file .env.dev -f compose.yaml -f compose.dev.yaml logs --tail 80 backend
docker compose --env-file .env.dev -f compose.yaml -f compose.dev.yaml stop
```

El volumen PostgreSQL conserva los datos. La contraseña de `.env.dev` se usa al inicializar el volumen. Si necesitas rotarla después, actualiza la credencial en PostgreSQL y su configuración de forma coordinada. El esquema de [referencia](database/reference/schema.sql) sirve para diseño y revisión.

## Verificar el provisioner en DEV

Construye la imagen del collector en el mismo Docker Engine donde corre DEV. El provisioner reutiliza esta imagen para todos los ISP.

```sh
docker build -t sknet-collector:dev monitoring/collector
docker compose --env-file .env.dev -f compose.yaml -f compose.dev.yaml up -d --build --wait
docker compose --env-file .env.dev -f compose.yaml -f compose.dev.yaml exec provisioner python -m provisioner --check
docker compose --env-file .env.dev -f compose.yaml -f compose.dev.yaml logs --tail 80 provisioner
docker ps --filter label=sknet.installation=sknet-dev
```

1. Una cuenta ISP con la funcionalidad `CONNECTIVITY` y permisos de lectura y escritura abre **Red → Conectividad → Conectar mi red**. Ingresa una o más redes privadas CIDR y pulsa **Generar script**. El progreso se actualiza automáticamente.
2. En **Infraestructura** del panel SaaS, consulta **Collectors**, **Conectividad VPN**, **Recursos de red**, **Trabajos de aprovisionamiento**, **Estado del sistema** y **Tickets automáticos**. Un segundo envío de la misma empresa debe mostrar el mismo collector. Un segundo ISP puede declarar los mismos CIDR y debe recibir otra reserva.
3. Con la NAT simulada de DEV, el panel ofrece **Consultar vista previa** marcada **NO EJECUTAR**. Sirve para verificar IP, clave pública y puerto asignados. Si una red de Docker cubre el pool completo, elige un CIDR libre mediante `SKNET_DOCKER_POOL` en `.env.dev` antes de reservar recursos y vuelve a levantar el backend. Inventaría las redes Docker y las redes de tránsito por separado.

### Conectar un MikroTik en una instalación con RouterOS habilitado

Tras una validación real de Docker, WireGuard y NAT, la misma pantalla ofrece **Consultar script**, **Copiar** y **Descargar .rsc**. Revisa la plantilla con la persona responsable del router y ejecútala en RouterOS 7. Limita el acceso a ICMP de la IP de túnel de SKNet y el forwarding y retorno a los CIDR de gestión autorizados. Pega únicamente la **clave pública** que imprime el router. La VPN se muestra conectada después de un handshake reciente y una respuesta ICMP desde la IP del MikroTik en el túnel. Usa **Actualizar clave pública o redes** para cambiar el router o las redes.

Consulta las condiciones pendientes para Ubuntu TEST en [PROVISIONING.md](docs/PROVISIONING.md).

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

Para incluir las pruebas de migración, autenticación y aislamiento, configura `SKNET_TEST_DATABASE_URL` en la sesión con la URL de un servidor **PostgreSQL 17 aislado para pruebas**, un usuario con permiso `CREATEDB` y una base de mantenimiento como `postgres`. La suite crea y elimina únicamente sus bases temporales con nombre propio. Sin esa variable solo se prueban las respuestas HTTP de salud.

## Entornos y referencia

`compose.yaml` se combina con `compose.dev.yaml`, `compose.test.yaml` o `compose.prod.yaml`. Cada overlay define un nombre de proyecto, redes y volúmenes independientes por proyecto y un puerto web distinto. Usa un archivo de variables separado por ambiente. TEST y PROD quedan preparados para validación posterior. Consulta [entornos](docs/ENVIRONMENTS.md) y [estado de implementación](docs/IMPLEMENTATION_STATUS.md).

La interfaz de referencia está en `references/v0-prototype/`. Las decisiones de diseño, arquitectura y alcance se documentan en `docs/`. El panel ISP incorpora CRM, conectividad WireGuard y configuración ICMP. El scheduler de monitoreo de dispositivos queda para una fase posterior.
