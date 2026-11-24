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

## Fase 2 · Autenticación y control de acceso DEV

- Se añadieron los módulos FastAPI de identidad, autenticación, administración de cuentas, registro y recuperación. La revisión aditiva `0003_access` conserva los datos existentes e incorpora intentos persistentes, preferencias, vencimiento y uso de contraseñas temporales, propósito de enlaces y catálogo de permisos por ámbito.
- ISP y SaaS usan cookies HttpOnly distintas, acotadas por ruta, con SameSite Strict. Las sesiones duran 12 horas, se verifican en PostgreSQL y se pueden revocar. Argon2id protege las contraseñas. Las escrituras comprueban el origen y las mutaciones de acceso se serializan con un bloqueo transaccional.
- Los permisos de gestión ISP exigen una cuenta activa, una empresa activa y una suscripción vigente que tenga la función ACCESS implementada. El límite de usuarios se aplica a las cuentas activas. Los permisos de roles se combinan y el operador solo puede asignar o administrar permisos que ya posee. No se puede dejar el ámbito sin una cuenta administrativa habilitada.
- El plan inicial es Bs 0 sin vencimiento. La edición versiona precio, duración y máximo de usuarios para altas posteriores. El alta crea las referencias predeterminadas, el primer administrador y la auditoría en una transacción. La aceptación de las condiciones de registro se registra con su versión. Los cobros corresponden a una fase posterior.
- Vite conserva la identidad de v0 en login, signup, perfiles y administración. El menú y las acciones se filtran a partir de permisos efectivos. Los datos de prueba se generaron exclusivamente en PostgreSQL temporal.
- La recuperación usa tokens con hash y TTL de 30 minutos cuando hay SMTP, contraseñas temporales de un solo uso de 24 horas, soporte ISP auditado y CLI SaaS. Sin SMTP se ofrece la vía administrativa. La entrega real de correo queda pendiente de un servidor SMTP configurado.

### Evidencia de la fase 2

| Comprobación | Resultado |
|---|---|
| `python -m pytest -q` con PostgreSQL 17.11 temporal | 8 pruebas aprobadas. Incluye CLI, login por usuario y correo, intentos, CSRF, roles, plan, revocación, último administrador, desactivación y aislamiento entre dos ISP. La recuperación comprobó la creación, el consumo y la revocación de enlaces con el transporte interceptado. Persiste la advertencia de Starlette/AnyIO de la fase 1. |
| `npm --prefix frontend run build` | TypeScript y Vite compilados. |
| Navegador con un backend real y PostgreSQL temporal | Se comprobó el formulario de registro, el login de ambos ámbitos, la matriz de permisos, los grupos plegables, el cierre de sesión SaaS y el listado de solo lectura sin botones de alta, edición o restablecimiento. La navegación directa a roles fue bloqueada y `/admin` redirigió al login SaaS sin sesión de ese ámbito. |
| Docker Compose DEV en Windows | Se aplicó `0003_access (head)` y se reiniciaron los cuatro servicios mediante `stop` y `up --wait`. Quedaron saludables, se conservaron los conteos y el registro público siguió apagado. DEV quedó listo para crear el primer administrador real. |
| Persistencia con datos de prueba | Al volver a iniciar el backend en la suite, se conservó la sesión y su plan. Al reiniciar físicamente el PostgreSQL temporal, la misma sesión siguió resolviendo la empresa y los permisos. |

## Fase 3 · Administración de plataforma SaaS en DEV

- **Empresas:** lista con búsqueda, filtros, orden y paginación. Alta administrativa conjunta con primer administrador, ficha editable, usuarios y uso de recursos según permiso. Suspensión y reactivación con auditoría, separadas de la conectividad y la suscripción. El alta conserva la regla de cero collectors.
- **Planes, suscripciones y registro:** catálogo editable con precio por periodo, moneda, vigencia, límites y funcionalidades. Los cambios comerciales crean versiones. Configuración elige la versión predeterminada. Signup usa esa versión solo cuando está habilitado y el alta administrativa está disponible en ambos casos. Los cambios de suscripción conservan los datos y registran fechas, estado y versión. El índice existente y la transacción impiden asignaciones simultáneas para una misma empresa.
- **Dashboard, soporte y auditoría:** métricas desde PostgreSQL y filtradas por permiso. Soporte SaaS independiente, con solicitudes ISP, asignación, respuestas, notas internas y cambios de estado. La auditoría es de consulta e incluye cambios de las entidades de plataforma. Las pantallas reutilizan el diseño v0 de SKNet.
- La revisión aditiva `0004_platform` conserva empresas, usuarios y suscripciones. Otorga los permisos nuevos a los roles que ya reunían todos los permisos del ámbito en la Fase 2. Los roles parciales reciben únicamente lo que un administrador autorizado les asigne.

### Evidencia de la fase 3

| Comprobación | Resultado |
|---|---|
| Suite de PostgreSQL 17.11 temporal | 12 pruebas aprobadas, incluidas las 8 anteriores. Verificó alta manual y pública, elección del plan predeterminado, versionado de planes, límites de usuarios, rechazo de módulos futuros, asignación concurrente, permisos y separación de ámbitos, soporte, auditoría, persistencia y dashboard. La prueba de migración desde `0003_access` conservó datos existentes y no amplió un rol parcial. |
| Navegador con PostgreSQL temporal | Se comprobó el dashboard con cantidades reales, la gráfica de distribución, la ficha de empresa y su utilización, la edición de un plan con versión nueva, el selector predeterminado y los historiales de suscripción, soporte y auditoría. |
| Docker Compose DEV en Windows | Cuatro servicios saludables y revisión `0004_platform (head)`. Antes y después se conservaron los conteos de empresas, usuarios y suscripciones. El endpoint health confirmó API y PostgreSQL disponibles. Los indicadores y la misma sesión se conservaron al reiniciar físicamente el clúster PostgreSQL temporal con datos. |
| Frontend | TypeScript y Vite compilados. El aviso por Vite se resolvió fijando 6.4.6. `npm audit` reportó 0 vulnerabilidades al ejecutar la comprobación. |

### Alcance siguiente

La plataforma calcula límites de clientes y dispositivos y muestra su utilización. La validación en sus futuros puntos de alta se incorpora junto al CRM y monitoreo. La recaudación, los tickets automáticos, el aprovisionamiento y el monitoreo siguen pendientes. En DEV, el dashboard distingue datos ausentes y capacidades todavía sin implementación.

## Fase 4 · CRM empresarial y dispositivos en DEV

- **CRM:** clientes naturales y jurídicos con contactos, direcciones, observaciones, notas e historial. Catálogo de planes de Internet separado de SaaS. Servicios con contratación, precio, moneda, acceso PPPoE/DHCP/estático u otro, IP informativa, MAC y router de acceso. Los cambios de estado son manuales y quedan en el historial.
- **Red:** sitios de cliente e infraestructura propia, dispositivos lógicos vinculados por sitio y servicio opcional, vista de infraestructura, estado administrativo y preparación ICMP. IPv4 de gestión independiente de la IP del servicio. La fase solo persiste el perfil y la intención de monitoreo. Los estados iniciales son UNKNOWN o DISABLED según la configuración.
- **Permisos y datos:** el backend verifica la empresa, el permiso y la funcionalidad del plan. Aplican el máximo de clientes registrados y el cupo para dispositivos activos con monitoreo solicitado o habilitado. La misma IP de gestión es válida en dos ISP. Se registran operaciones en auditoría sin contraseñas, cuerpos de notas ni usernames PPPoE.
- **Interfaz:** se conservó el diseño blanco y morado de SKNet, con tablas compactas, filtros y fichas por secciones. El dashboard ISP usa datos de su empresa y omite los indicadores sin permiso. Las pantallas distinguen ausencia de mediciones y módulos futuros.
- **Migración `0005_enterprise`:** ampliación de tablas existentes para los campos de CRM, preferencias operativas de dispositivo e índices, sin tablas nuevas. Los planes TRIAL reciben CRM y configuración ICMP. Los roles que ya reunían todos los permisos base de IAM ISP reciben los permisos nuevos. Los roles parciales conservan sus permisos hasta que se les asignen otros. El código ICMP operativo continúa sin habilitar.

### Evidencia de la fase 4

| Comprobación | Resultado |
|---|---|
| Suite de PostgreSQL 17.11 temporal | 16 pruebas aprobadas, incluidas las 12 anteriores. Se comprobó el alta y la edición de clientes y contactos, direcciones y notas, sitios propios y de clientes, servicios PPPoE/DHCP/estáticos, historial, dispositivos, configuración ICMP, reutilización de IP entre ISP, asociaciones cruzadas rechazadas, límites, permisos, auditoría y dashboard. La migración desde `0004_platform` conservó registros. Persiste el aviso de Starlette/AnyIO de las fases anteriores. |
| Build de frontend | TypeScript y Vite compilados. |
| Navegador y base temporal | Se verificaron la gráfica ISP, las secciones de la ficha, el alta de un abonado jurídico, los vínculos entre servicio y dispositivo, el intervalo ICMP editado, la separación de infraestructura propia y la ausencia de módulos e indicadores CRM para un lector sin permiso. |
| Docker Compose DEV en Windows | Cuatro servicios saludables y revisión `0005_enterprise (head)`. La comparación antes y después conservó los conteos de empresas, usuarios y CRM. DEV continuó sin collectors ni mediciones. |
| Persistencia después de reinicios | La suite volvió a iniciar el backend y pudo consultar el dispositivo. Se reinició físicamente PostgreSQL temporal y la misma sesión volvió a consultar el dashboard y el intervalo ICMP editado en navegador. |

El collector, el aprovisionamiento, las mediciones de red y los módulos posteriores quedan pendientes. Los planes personalizados requieren seleccionar CRM o ICMP_CONFIG y asignar la nueva versión a la empresa, según corresponda.

## Fase 5 · Provisioner, collectors y WireGuard en DEV

- El backend guarda trabajos, leases, reservas y diagnósticos en PostgreSQL. Las peticiones simultáneas de un ISP reutilizan su collector. El provisioner Python usa Docker SDK para crear una red `/30`, un collector Alpine y la publicación UDP. El túnel recibe una `/31`. Una reserva se libera solo después del retiro verificado de los recursos que la utilizan.
- El backend ofrece REST interno por sockets Unix distintos para provisioner y collectors. Cada collector tiene token revocable, clave privada persistente, red independiente y solo las capacidades `NET_ADMIN` y `NET_RAW`. El heartbeat predeterminado es de 10 s y vence a los 30 s. La comprobación VPN exige handshake reciente e ICMP a la IP WireGuard del peer.
- **ISP** cuenta con el asistente **Red → Conectividad**, seguimiento de trabajos, referencia de soporte, vista previa de RouterOS en DEV y configuración de clave pública y CIDR. El script descargable está condicionado a una infraestructura verificada en modo real. **SaaS** dispone de collectors, VPN, pools, trabajos, estado del provisioner y tickets deduplicados. La apariencia conserva los componentes del panel existente.
- **Migración `0006_connectivity`** aditiva, sin tablas nuevas. Añade datos de configuración, leasing, inventario y diagnóstico, y registra `CONNECTIVITY` y los permisos de ambos paneles. DEV conserva una empresa, dos usuarios, cero clientes CRM y cero collectors en su base habitual. Las empresas y collectors del ensayo se crearon en una instalación DEV aislada.

### Evidencia de la fase 5

| Comprobación | Resultado |
|---|---|
| PostgreSQL 17 temporal | 21 pruebas aprobadas, incluidas 16 de regresión. Cubren concurrencia, reservas `/30` y `/31`, selección y agotamiento UDP, tickets, permisos de plan, autenticación y rotación, leases, entrega condicionada del script y manejo de estados. Se mantiene el aviso de deprecación Starlette/AnyIO. |
| Docker Desktop y WSL2 | Se construyeron las imágenes y se aprovisionaron dos collectors. Se asignaron subredes y puertos distintos pese a redes remotas iguales. Se bloqueó ICMP directo entre collectors. Al reiniciar backend, provisioner y ambos collectors, se conservaron IDs, claves y reservas y volvió el heartbeat. Kernel comprobado `6.18.58.1-microsoft-standard-WSL2`. |
| WireGuard con peer Linux | En una red Docker temporal, se verificaron setup de la clave pública desde el backend, handshake real y ping por `wg0`. La conexión se mantuvo marcada como simulación por su adaptador NAT. |
| Adaptador de borde | DEV usó simulación. Un pool ocupado por una red Docker activó el manejo de agotamiento y los tickets. Se eligió un pool libre para el ensayo aislado y se reintentó con los mismos collectors. Las operaciones REST de RouterOS se cubren con respuestas en memoria, incluyendo regla propia, colisión, firewall y retiro. |
| Interfaz y build | TypeScript y Vite compilados. Edge verificó el asistente ISP, vista previa con etiqueta de simulación y pantallas SaaS de collectors, VPN, pools, trabajos, estado y soporte. |
| DEV habitual | Cuatro servicios saludables, migración `0006_connectivity (head)` y API con PostgreSQL disponible. |

### Límites y validaciones pendientes

- Se debe probar el flujo de extremo a extremo con RouterOS 7 y Ubuntu TEST, incluyendo TLS, permisos, DST-NAT, firewall, persistencia tras reiniciar Docker Engine y rutas privadas a ambos lados. El ensayo de WSL2 validó WireGuard dentro de Docker. La recepción desde una WAN y el tránsito por DST-NAT quedan pendientes. [Preparación de Ubuntu TEST](PROVISIONING.md#preparación-futura-para-ubuntu-test).
- Un puerto ocupado por un proceso que Docker no inventaría se detecta al publicar el puerto. El trabajo requiere reconciliación tras resolver el conflicto y conserva la reserva mientras el estado de infraestructura sea incierto. Las reglas de borde verificadas en memoria no cubren configuraciones específicas de GNS3 ni de hardware.
- El monitoreo de dispositivos queda fuera de esta fase. Los volúmenes de la prueba aislada se conservaron y sus contenedores de prueba se detuvieron.

## Fase 4.1 · Flujo operativo del CRM

- El alta del abonado permite crear cliente, dirección, sitio y servicio en una transacción. El precio y la moneda se recuperan del plan y se pueden modificar. Los servicios existentes se pueden registrar activos con el permiso correspondiente. Los nuevos o pendientes de definir conservan el estado pendiente.
- Los códigos comerciales se asignan con contadores separados por empresa y entidad. La migración `0007_crm_workflow` mantiene UUID y códigos anteriores, añade códigos a los registros que carecían de ellos, clasifica sitios y equipos y conserva las relaciones. Cuando el tipo anterior era ambiguo, el sitio recibe el tipo **Otro** en su categoría. Los detalles están en [CRM.md](CRM.md).
- El listado de sitios usa filtros, orden y paginación del backend. El equipo final pertenece al cliente a través de su sitio y el servicio es opcional. Los equipos de infraestructura conservan el rol topológico y declaran capacidades para que los servicios puedan filtrar routers de acceso activos por modalidad.
- El usuario verificó WireGuard, ICMP bidireccional y acceso a la red remota con un RB5009 antes de esta fase. Se conserva la parametrización del frontend mediante `WEB_BIND` y se documenta en el archivo de ejemplo. Las variables del entorno y las configuraciones de conectividad permanecen en DEV tal como estaban.

### Evidencia de la fase 4.1

| Comprobación | Resultado |
|---|---|
| PostgreSQL 17 temporal | 25 pruebas aprobadas, incluidas las 21 anteriores y las regresiones de conectividad. Se verificaron concurrencia para los cuatro códigos, reversión transaccional, permisos, relaciones cruzadas, filtros, paginación y preservación de datos. Continúa el aviso de deprecación de Starlette/AnyIO. |
| Frontend | TypeScript y Vite compilaron. Edge comprobó el alta simple e integrada, el precio recuperado y editado, el estado activo inicial, el filtrado de routers, pestañas de sitios, alta de un equipo final y opciones del formulario según permisos. |
| DEV existente | Se aplicó `0007_crm_workflow (head)`. Las columnas anteriores comparadas coincidieron para un cliente, un sitio y un dispositivo, así como para dos collectors históricos y sus reservas y túneles. El sitio anterior quedó como infraestructura de red de tipo Otro. Los cuatro servicios respondieron saludables. El collector vigente seguía enviando heartbeat y el túnel seguía reportando conexión. |

La prueba física del RB5009 corresponde al usuario y precede a esta fase. Las órdenes de instalación, la asignación de técnicos, el monitoreo automático y la automatización PPPoE/DHCP quedan pendientes.

## Fases 4.2 y 6 · CRM, instalaciones y monitoreo

| Etapa | Implementación y validación |
|---|---|
| A · CRM | Archivo, eliminación confirmada con comprobación de dependencias, filtros y auditoría. FastAPI indica los campos inválidos, React señala el error sin borrar valores. Prueba de CRM y compilación completadas por etapa. |
| B · Equipos | Alta sin sitio ni IP, asignación y traslado con historial, estado operativo y propiedad. La IP heredada se resuelve por referencia al servicio. Pasaron las pruebas de asignación y migración y compiló el frontend. |
| C · Instalaciones | El alta nueva puede crear la orden en la misma transacción. Incluye técnicos, programación, equipos, verificación, finalización y activación administrativa, con permisos separados. Pasaron las pruebas de orden, finalización, cancelación y migración, y compiló el frontend. |
| D · ICMP | Cada collector programa pings dentro de su túnel. El backend autentica al collector, valida IP, revisión y pertenencia, y registra muestras, estado e incidentes. En Docker Desktop se comprobó WireGuard real contra un peer Linux aislado. Se obtuvieron 5 respuestas de 5 con 0 % de pérdida y RTT medio de 1,062 ms en la corrida que completó el ciclo. La pérdida de respuesta del destino produjo DOWN y un único incidente. Al restaurar la IP se cerró ese incidente y la pérdida posterior del túnel produjo UNREACHABLE y un incidente VPN sin generar otro incidente de equipo. |
| E · Integración | Actualización HTTP de collectors, VPN, trabajos, pools, dashboard ISP, monitoreo e incidentes. Edge comprobó instalación, errores debajo de los campos, conservación de los valores, detalle ICMP y retiro automático del collector de QA sin recargar el documento. La reserva se liberó. |

DEV migró hasta `0011_icmp_monitoring` y conservó los identificadores de siete registros de CRM, dos collectors históricos, dos túneles y dos credenciales. Se reinició únicamente el backend para cargar las nuevas rutas privadas. El collector operativo conservó su contenedor y sus volúmenes. Los ensayos reales de esta fase usaron un peer Linux descartable de Docker Desktop. El RB5009 no intervino en el ensayo.

## Fase 7 · Estabilización del MVP

| Etapa | Implementación |
|---|---|
| A | Alta de cliente y servicio con estado administrativo, nombre automático del sitio a partir del código de cliente y selectores que consultan todas las páginas. Se conservan las órdenes existentes y la creación manual desde servicios pendientes. |
| B | Catálogos ISP, stock por modelo, generación transaccional de unidades `DSP` y asignación por modelo o unidad. La asignación conserva el estado administrativo del servicio. Los routers de acceso requieren instalación, sitio vigente y capacidad compatible. |
| C | Eliminación auditada de altas sin actividad histórica protegida, motivos de inelegibilidad ICMP, filtros de catálogo y gráficas con escala porcentual, períodos cortos y puntos aislados. Se mantiene el scheduler y la actualización periódica de incidentes. |
| D | Actualización individual confirmada por ID de imagen, verificación con heartbeat posterior, reversión con la versión anterior y reconciliación manual independiente del límite automático. El inventario identifica recursos residuales etiquetados y volúmenes conservados. |
| E | Migraciones aditivas `0012_device_catalogs` y `0013_collector_upgrades`. El overlay opcional de TEST prepara una red de gestión exclusiva para el provisioner, sockets privados y secretos RouterOS montados desde archivos. |

Pasaron 33 pruebas con PostgreSQL aislado, las comprobaciones posteriores de conectividad y residuos, y la compilación del frontend de producción. En Edge con QA se comprobó el registro de 20 unidades, el alta con sitio automático, servicio activo y asignación, el selector de sitios en dos líneas y el punto aislado en las gráficas de 24 h y 30 min con una muestra de prueba. En Docker QA se reemplazó un collector conservando su identidad, clave, token, configuración, volúmenes, red, IP, puerto y mediciones previas de prueba. Una imagen sin heartbeat provocó una reversión verificada. Se recreó el collector tras eliminar solo su contenedor QA y se ejecutó otra reconciliación dentro de la ventana de 15 minutos. Ambas conservaron la última imagen aprobada. Se validaron ambos perfiles de Compose de TEST sin desplegarlos.

DEV migró de `0011_icmp_monitoring` a `0013_collector_upgrades`. Se recargaron backend y provisioner. Se conservaron los registros CRM, collectors, túneles y credenciales comprobados. El collector operativo conservó su ID `35e02728c023`; el histórico pasó de 269 a 273 muestras durante la ventana de migración.

Quedan para Ubuntu/GNS3 los ensayos definitivos de caída/recuperación del dispositivo con la misma IP, caída del túnel y aislamiento entre redes remotas. Los comandos de reproducción y despliegue están en [Entornos](ENVIRONMENTS.md).

La imagen nueva sirve para futuros collectors. El collector DEV que ya estaba en marcha sigue usando su imagen anterior. Cambiar su imagen requiere una ventana autorizada. La verificación de carga y el despliegue Ubuntu quedan pendientes. [Reglas y verificación ICMP](MONITORING.md).

La suite final aprobó 30 pruebas y compiló TypeScript y Vite. Una comprobación adicional validó la eliminación de muestras vencidas, la conservación del incidente de dispositivo y el registro de un incidente por heartbeat vencido. El reinicio de PostgreSQL de QA conservó diez muestras, el incidente recuperado y la orden de prueba. Se mantiene el aviso de deprecación de Starlette/AnyIO.
