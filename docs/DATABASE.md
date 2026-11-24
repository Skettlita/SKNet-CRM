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

La revisión `0001_schema` crea el esquema de referencia de 78 tablas, `0002_catalog` carga el plan TRIAL y `0003_access` agrega el catálogo de acceso, el control de intentos y los campos de recuperación y preferencias. El esquema ejecutable de la fase 2 tiene 79 tablas. Alembic aplica las revisiones pendientes al arrancar el backend. `schema.sql` conserva el DDL de referencia.

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
