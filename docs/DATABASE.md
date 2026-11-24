# SKNet — modelo consolidado de base de datos

Referencia técnica para Codex. PostgreSQL 17; 78 tablas en nueve schemas, a partir del modelo anterior de 67 tablas. El DDL no sustituye implementación de API, migraciones, seguridad ni pruebas de integración. "Definitivo" significa base de diseño acordada para comenzar, no modelo inmutable ni validado para producción. Monitoring avanzado (SNMP, etc.) necesitará migraciones futuras.

| Schema | Tablas |
|---|---:|
| core | 9 |
| platform | 16 |
| platform_billing | 5 |
| crm | 21 |
| billing | 6 |
| inventory | 6 |
| connectivity | 8 |
| monitoring | 6 |
| audit | 1 |

DDL y diagramas en database/reference/. Reglas vigentes en docs/MONITORING.md, PROVISIONING.md, AUTH.md, MVP.md.

## Inicialización y verificación

La revisión `0001_schema` crea el esquema de referencia de 78 tablas, `0002_catalog` carga el plan TRIAL y `0003_access` agrega el catálogo de acceso, el control de intentos y los campos de recuperación y preferencias. El esquema ejecutable tiene 79 tablas. La revisión `0004_platform` añade condiciones versionadas, fechas en el historial de suscripciones, permisos de plataforma, el catálogo de soporte y dos índices. Alembic aplica las revisiones pendientes al arrancar el backend. `schema.sql` conserva el DDL de referencia.

```sh
docker compose --env-file .env.dev -f compose.yaml -f compose.dev.yaml exec backend alembic current
```

La suite de integración comprueba las revisiones en bases temporales de PostgreSQL 17. Consulta [el README](../README.md) para ejecutar la suite y [el estado](IMPLEMENTATION_STATUS.md) para los resultados registrados.

## Reglas y decisiones
- Una instalación comparte una base PostgreSQL y cuatro servicios base. Cada ISP con monitoreo tiene un collector Docker aislado; los collectors no acceden a PostgreSQL. Laptop y VM no comparten datos, volúmenes ni secretos.
- core.users representa identidad con account_scope ISP o SAAS. Username y email únicos sin distinguir mayúsculas dentro de cada ámbito; username no admite @; una membresía por cuenta ISP en V1. core.memberships y platform.staff tienen FK de ámbito para impedir mezclas. Roles y permisos independientes por ámbito. Los logins /login y /admin/login son distintos; /signup crea empresas exclusivamente si platform.settings.public_signup_enabled está habilitado (propuesta: apagado por defecto hasta que el admin lo habilite). No hay rol propietario. El primer administrador SaaS se crea con CLI interactiva, no con credenciales seed; CLI local de emergencia para recuperar admin. No incluir registro público SaaS. No desactivar al último admin de cada ámbito empresarial/plataforma. Permisos granulares y plan se validan en cada operación; no permitir autoescalación; frontend oculta opciones no autorizadas.
- Contraseñas con Argon2id, tokens de sesión/recuperación/collector aleatorios con hash almacenado, expiración y revocación; nunca registrar secretos en auditoría. Reset por correo cuando SMTP esté configurado; en laboratorio reset autorizado con contraseña temporal y cambio obligatorio; revocar sesiones previas, auditar. Recuperación sin revelar si existe una cuenta. Cookies HttpOnly, SameSite y Secure bajo HTTPS, CSRF si aplica, limitación de intentos; MFA para producción administrativa. Los procedimientos y permisos no los ejecuta el DDL.
- company_id y FKs compuestas protegen relaciones; no sustituyen controles de autorización. Implementar consultas acotadas a tenant, pruebas de IDOR y roles de BD de mínimo privilegio; considerar RLS antes de producción. No conceder acceso a tablas o vistas completas a usuarios empresariales. Revisar coherencia de relaciones adicionales como actor de plataforma, ticket/alerta/incident y asignación actual del collector en servicios de aplicación.
- Plan TRIAL gratuito sin vencimiento, límites configurables; versiones de plan preservan condiciones históricas. NULL en límites/duración significa sin límite comercial, no capacidad infinita de infraestructura. features.implemented empieza false y se habilita mediante migraciones cuando se entrega cada capacidad; acceso efectivo requiere implementación + plan + permiso. No se crean usuarios ni empresas ficticias por defecto.
- CRM: cliente → sitios → servicios → equipos. Un nodo/intermedio puede existir sin servicio. IP de gestión única en crm.devices por collector vigente, no global. IP de servicio es informativa; puede ser dinámica; service_ip_observed_at señala vigencia. No almacenar credenciales PPPoE sin requisito posterior. La relación access_router_id apunta a dispositivo del mismo ISP. Collector se asigna al habilitar monitoreo; cambiar IP/perfil/collector incrementa revisión. El modelo V1 admite IPv4 para monitoreo/VPN.
- Inventario: producto != activo físico != dispositivo lógico. Activo puede ser de empresa o cliente. Mantener trazabilidad de ubicación y movimientos; coherencia entre sitio del activo y dispositivo y stock no negativo requieren operaciones transaccionales. No duplicar serial de activo cuando dispositivo está vinculado, usarlo como fuente; serial del dispositivo solo para equipos sin activo. No incluir depreciación contable en esta etapa.
- Contratos guardan metadatos y referencia a documentos privados. Tickets tienen muchas OT; cierre normal solo tras resolución verificada y OT finalizadas/canceladas; cancelación justificada; reapertura con historial. Verificar transiciones, actores y permisos en backend.
- Billing y platform_billing separados. Cargo mensual único por servicio/suscripción y periodo normalizado, pagos parciales y asignaciones, comprobantes internos, ajustes auditados. Propuesta de reglas futuras: día 29–31 se ajusta al último día del mes; vencimiento inclusivo (moroso desde día siguiente); no recalcular deuda histórica al modificar ciclo/plan. Primer mes y cobro durante suspensión siguen pendientes; decidir antes de implementar automatización. Validar sumas con bloqueo en transacción; no permitir sobreaplicación, incluir créditos sin aplicar al estado de cuenta integral; vistas actuales muestran saldos de cargos. No eliminar operaciones financieras. Comprobantes internos no sustituyen facturas fiscales.
- Connectivity: reglas detalladas en PROVISIONING.md. Recursos únicos por instalación y reserva vigente; validación de solapamiento/host y reconciliación en provisioner. No almacenar claves privadas ni tokens planos. No hardcodear IPs del laboratorio en aplicación ni crear pools automáticamente sin validar .env.
- Monitoring: reglas en MONITORING.md. Estado actual separado de mediciones, incidentes y alertas. Heartbeat vive en connectivity.collectors; no tabla global duplicada. La falta de visibilidad no equivale a caída del dispositivo. Retención y concurrencia configurable; medir carga. SNMP queda fuera del esquema operativo inicial.
- Auditoría automática desde servicios de negocio; antes/después redactados; mantener históricos. No implementar borrado físico de entidades con historial por defecto. No cargar datos de v0 en base real.

## Cambios de cierre
ICMP: cinco paquetes, pérdida superior a 30% cuenta como fallo, RTT superior a 200 ms degrada, umbrales configurables. Tickets automáticos con origin SYSTEM, fault_key deduplicada y actor de sistema en historial; edge_rule_tag identifica reglas NAT propias. Tres entornos DEV/TEST/PROD independientes. La suite verificó las migraciones en PostgreSQL 17. La coherencia de actores y la concurrencia de los servicios se verificarán al implementar cada módulo. No duplicar DDL y Alembic.

## Reglas operativas de plataforma

- La versión predeterminada para altas se selecciona explícitamente en Configuración. Editar un plan crea una nueva versión comercial y conserva las anteriores. Desactivar el plan bloquea nuevas asignaciones y no invalida las existentes. El operador debe cambiar primero el plan predeterminado si pretende desactivarlo.
- El campo histórico `monthly_price` representa el precio del periodo indicado por `billing_period` (mensual o anual). La duración comercial se calcula en días mediante `trial_days`, con NULL para vigencia indefinida. El código TRIAL determina el estado inicial de prueba. Las demás altas empiezan en ACTIVE. Los parámetros comerciales no generan cobros.
- Suscripciones TRIAL, ACTIVE o GRACE dentro de su ventana dan acceso a las funcionalidades implementadas que contiene su versión. El índice parcial existente conserva una sola suscripción no cancelada por empresa. Se fiscalizan los máximos de usuarios activos, clientes registrados y dispositivos activos con monitoreo configurado o habilitado.
- `core.companies.status=INACTIVE` representa suspensión administrativa. Bloquea el acceso ISP y revoca sus sesiones y enlaces pendientes. Conservar la suscripción y las filas de negocio permite reactivar sin reconstruir información. La conectividad se consulta de forma independiente y distingue ausencia de collector de falta de datos recientes.
- Los tickets de SKNet se almacenan exclusivamente en `platform.support_*`. El rol ISP accede con SAAS_SUPPORT y permisos de su empresa. La auditoría y el historial no incluyen el cuerpo de las respuestas. Las notas internas de soporte son visibles en SaaS.
## CRM e ICMP en la Fase 4

- La revisión `0005_enterprise` agrega campos sobre las tablas existentes, un índice por empresa para IP de gestión reservada sin collector, un índice de actividad y permisos ISP. Mantiene las relaciones compuestas y el índice por collector para equipos ya asignados.
- La IPv4 de gestión se guarda en `crm.devices.ip_address`. Dos empresas pueden reservar la misma IP. Sin collector, la reserva se controla entre dispositivos activos con intención de monitoreo de la misma empresa. Con collector, se conserva la regla de unicidad del modelo. Los equipos sin monitoreo ni collector pueden existir sin IP.
- `monitoring_requested` representa la intención de monitoreo y consume el cupo cuando el dispositivo está activo. `monitoring_enabled` conserva su significado operativo y requiere un collector. La fase solo prepara `ICMP_CONFIG`. El código comercial ICMP sigue sin implementación operativa.

## Fase 5

- `0006_connectivity` añade redes deseadas, diagnóstico, estado del contenedor, revisión aplicada e indicador de simulación al collector. Añade lease temporal y código de error a los trabajos, dirección de bind a las reservas e inventario observado a los pools.
- La funcionalidad `CONNECTIVITY` controla el acceso ISP. Se reutilizan el índice de un collector vigente por empresa, las asignaciones únicas de red y puerto, las credenciales con hash y la deduplicación de tickets activos. Los roles de conectividad tienen permisos de lectura y escritura separados en ambos ámbitos.

## Fase 4.1

- `0007_crm_workflow` agrega `crm.commercial_counters` para asignar códigos por empresa y entidad. El contador se incrementa mediante un UPSERT en la transacción del alta. Las restricciones únicas siguen asociadas a la empresa.
- La categoría del sitio se valida junto al tipo. Un sitio puede referenciar una dirección ya registrada del mismo cliente mediante una FK compuesta. El equipo final deriva su cliente del sitio y la FK existente asegura que su servicio opcional use ese mismo sitio. Las capacidades se guardan en los equipos de infraestructura y la situación de instalación inicial se guarda en el servicio. [Reglas y migración de registros anteriores](CRM.md).
- `crm.services.service_ip` y su fecha de observación registran la dirección informativa del servicio. El precio y moneda quedan registrados en el contrato comercial del servicio. Los cambios administrativos se registran en el historial; la suspensión o baja de un cliente conserva sus servicios y sus dispositivos.
- Los sitios de tipo CLIENT_SITE pertenecen a un cliente. Los demás tipos se usan para infraestructura propia. Si un dispositivo pertenece a un sitio de cliente, su cliente se deriva de ese sitio. La vinculación al servicio es opcional y debe coincidir con el sitio.
