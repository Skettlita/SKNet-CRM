# MVP — criterios de aceptación

Estos son criterios acordados y comprobables, no resultados ejecutados. Un requisito se da por terminado únicamente si su prueba pasa. La presentación usa ICMP, no SNMP. El laboratorio anterior solo validó conectividad y aislamiento manual.

| ID | Prueba | Resultado esperado |
|---|---|---|
| A01 | Clonar código en laptop y VM, configurar .env diferentes y construir con Compose | Cuatro servicios base saludables; migraciones completadas; datos, claves y volúmenes independientes. |
| A02 | Inicializar BD vacía | Plan de prueba Bs 0 sin vencimiento; sin empresas ni contraseñas de ejemplo obligatorias. Crear primer admin SaaS por CLI segura. |
| A03 | Entrar con username o correo en /admin/login y /login | Ambos identificadores funcionan en su ámbito; credenciales de ISP no abren SaaS ni al contrario. No signup SaaS. |
| A04 | Activar signup público; registrar ISP1 e ISP2 | Crear empresa, admin ISP, rol, suscripción gratuita y auditoría de forma atómica; sin collector todavía. Desactivar signup y verificar rechazo del endpoint. |
| A05 | Crear otro plan y configurar límites/módulos | Las suscripciones apuntan a la versión correspondiente; acceso efectivo requiere plan y permiso. No modificar cargos históricos. |
| A06 | Crear empleado con rol de lectura | Sidebar, dashboard y botones se adaptan; API rechaza acciones no permitidas (403); no puede elevar sus privilegios. |
| A07 | Intentar acceder a datos de otra empresa por ID | Backend rechaza; FK compuesta rechaza referencias cruzadas. No exponer información en listados, métricas ni exportaciones. |
| A08 | Registrar cliente, sitio, plan de servicio y servicio PPPoE/DHCP/estático | Datos persistidos; IP del servicio separada de IP de gestión; no consultas automáticas de sesiones o leases. |
| A09 | Registrar nodo, intermedio y endpoint | Infraestructura sin cliente asociado válida; endpoint vinculado al servicio/sitio si corresponde; registro de dispositivos sin IP permitido sin monitoreo. |
| A10 | Pulsar Generar script para ISP1 y repetir simultáneamente la solicitud | Un solo collector, reserva vigente y regla NAT propia; nuevo contenedor aparece en Docker. No crear recursos al signup. |
| A11 | Solicitar monitoreo para ISP2 | Red /30, WG /31 y puerto únicos; mismas IP privadas remotas permitidas. 6 contenedores en total con 2 collectors. |
| A12 | Generar script, introducir clave inválida y después clave válida | Inválida rechazada; script contiene solo clave pública y parámetros de esa empresa; estado espera handshake hasta prueba real. |
| A13 | Ejecutar scripts MikroTik en GNS3 y permitir ICMP | Dos túneles conectados; cada collector alcanza su propia red; misma 192.168.1.254 válida para ambos. |
| A14 | Activar monitor de cuatro dispositivos | Checks periódicos, RTT, pérdida, última fecha y estados reales visibles; datos escritos en PostgreSQL. |
| A15 | Apagar PC1, mantener PC2 y ambas VPN | ISP1 PC1 DOWN tras umbral; ISP2 PC2 UP; un incidente para PC1. Recuperación tras umbral al encender. |
| A16 | Desconectar una VPN manteniendo collector activo | UNREACHABLE para equipos de esa red, evento VPN; no inventar caídas individuales; otra empresa sigue operativa. |
| A17 | Detener collector de ISP1 | STALE tras heartbeat vencido; conserva último estado conocido; ISP2 sigue funcionando; ticket SaaS automático sin duplicados. |
| A18 | Reiniciar collector y servicios base | WG se levanta automáticamente; datos, claves, reservas e historial conservados; sin duplicados. |
| A19 | Detener API brevemente y restaurar | Collector sigue midiendo con configuración válida; reenvía cola acotada; duplicados/atrasados no alteran estado vigente. |
| A20 | Intentar enviar resultados con token de otra empresa, revocado, o device_id no asignado | Rechazo sin escritura. |
| A21 | Simular pool agotado, puerto ocupado o fallo Docker | Mantenimiento visible al ISP, ticket SaaS deduplicado para agotamiento o fallo interno, CRM operativo; reintento/reconciliación o limpieza controlada. |
| A22 | Actualizar código y migraciones; repetir despliegue offline con imágenes listas | Mantiene registros y configuración, no depende de CDN ni descargas durante demo. |
| A23 | Revisar UI y repo público | Estilo v0/UISP blanco-morado, tablas compactas, login separado; sin selector falso ni datos ficticios como reales; secretos, .env, dumps y claves fuera de Git. |
| A24 | Restablecer credencial con método administrativo autorizado | Contraseña temporal de un uso/cambio obligatorio, sesiones antiguas revocadas, auditoría sin secretos. Último admin protegido. |

| A25 | Probar 5 paquetes, pérdida 20% y 40%, RTT 201 ms | 20% DEGRADED, 40% fallo que acumula umbral DOWN, RTT alto degrada sin declarar DOWN; recuperación según perfil. |
| A26 | Simular agotamiento de red/puerto y error API RouterOS; repetir solicitud | Ticket SaaS único por causa/empresa, no script listo, no afectar otra empresa. |
| A27 | Aprovisionar y retirar conexión real en TEST | NAT propia verificada, no duplicada; no tocar reglas ajenas, liberar reserva solo tras limpieza. |
| A28 | Migrar BD DEV y TEST con registros existentes | Datos persistentes, revisión Alembic correcta; PROD separado y no modificado. |

## Prioridad para la defensa
Primero lograr A01–A15, A16–A18 y A20/A23; mantener aislamiento y autenticación como obligatorios, no recortar seguridad para ganar tiempo. A19/A21/A22/A24 también forman parte del MVP técnico propuesto; si no se prueban antes de presentar, documentarlos como pendientes. Registrar evidencia de cada prueba (comando, captura, fecha, resultado); no confundir pruebas manuales previas con implementación de software.

## Fuera de la primera demostración
SNMP, API MikroTik de routers de clientes (no la NAT del borde SKNet), redundancia, Kubernetes, topología/correlación, NetFlow, notificaciones externas, automatización completa de billing, inventario y soporte avanzado. Mantener modelo de datos y módulos previstos; no simular resultados como reales. Los planes no pueden habilitar capacidades sin implementación. El diseño general de estos módulos no obliga a entregarlos en el primer MVP.
