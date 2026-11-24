# Monitoring — reglas técnicas V1 (acordadas)

## Alcance y configuración
Solo ICMP IPv4; no SNMP, PPPoE discovery, DHCP discovery, NetFlow ni correlación topológica todavía. Usar la IP de gestión manual, alcanzable vía el collector correspondiente. La IP del servicio es informativa y puede cambiar. Una respuesta ICMP no demuestra que el servicio de Internet contratado funcione correctamente.

| Parámetro | Predeterminado | Perfil de demo opcional |
|---|---|---|
| Intervalo entre inicios de checks | 30 s | 10 s |
| Paquetes por check | 5 | 5 |
| Timeout por respuesta | 2000 ms | 2000 ms |
| Checks consecutivos fallidos para DOWN | 3 | 2 |
| Checks consecutivos aceptables para recuperar | 2 | 1 |
| Umbral de latencia alta (RTT medio) | 200 ms | 200 ms |
| Tolerancia de pérdida para fallo | 30% (estrictamente superior cuenta como fallo) | 30% |
| Umbral de degradación por pérdida | 0% | 0% |
| Heartbeat independiente de checks | 10 s | 10 s |
| Heartbeat vencido | 30 s | 30 s |
| Comprobación activa de VPN | 10 s | 10 s |
| Fallos de prueba VPN para desconexión | 3 | 3 |
| Refresco del dashboard | 5 s | 5 s |
| Retención histórica | Según plan; propuesta 30 días operativos cuando no haya política definida | Igual |

Los parámetros son configurables dentro de los límites del plan y de los límites de seguridad del servidor. No iniciar checks superpuestos para el mismo dispositivo: si un check excede el intervalo, saltar el turno atrasado. Limitar concurrencia (propuesta inicial: 10 checks simultáneos por collector), validar timeout y duración máxima, y medir carga antes de aumentarla. No utilizar shell con entradas del usuario. El heartbeat debe continuar incluso si falla la VPN.

## Resultados y estados
- REACHABLE: uno o más paquetes recibidos. RTT promedio de respuestas válidas en ms; pérdida = 100*(enviados-recibidos)/enviados. Resultado bruto REACHABLE no implica éxito: pérdida > tolerancia cuenta como check fallido incluso con respuestas. Si pérdida <= tolerancia, cuenta como éxito; DEGRADED si pérdida > umbral de advertencia o RTT medio > 200 ms (configurable), UP en otro caso. Con 5 paquetes: 0 pérdidas UP salvo latencia alta, 1 pérdida DEGRADED, 2–5 pérdidas check fallido.
- NO_REPLY: ningún paquete recibido, tras ejecutar una prueba válida con VPN saludable; RTT NULL y pérdida 100. Un ICMP destino inaccesible del router para ese destino puede contar como ausencia de respuesta, no como fallo del túnel por sí solo.
- ERROR: ping no pudo ejecutarse, error de permisos, configuración o procesamiento; métricas NULL. No computar como fallo del dispositivo.
- SKIPPED_VPN: sin visibilidad por túnel no utilizable; métricas NULL. No computar como fallo del dispositivo.

DOWN significa falla según política, no necesariamente apagado físico. Durante una racha fallida menor al umbral conservar estado confirmado y mostrar resultado reciente y contador. El backend conserva el estado confirmado UNKNOWN/UP/DEGRADED/DOWN y los contadores. Al alcanzar N fallos consecutivos válidos, confirma DOWN y abre un incidente si no existe; recupera después de M checks válidos aceptables (pérdida <= tolerancia y al menos una respuesta), a UP o DEGRADED según el resultado. Un check válido del tipo contrario reinicia el contador opuesto. Una interrupción de visibilidad invalida la racha; no contar errores o muestras omitidas como éxitos o fallos. Tras recuperarse la visibilidad, volver a comprobar; no cerrar incidentes automáticamente.

Estado mostrado (precedencia): DISABLED si equipo/perfil deshabilitado o retirado; STALE si collector sin heartbeat fresco; UNREACHABLE si conectividad confirmada caída; UNKNOWN si no hay mediciones válidas de la configuración vigente; STALE si las mediciones válidas dejan de actualizarse (propuesta: máximo de 3 intervalos o 30 s); en otro caso estado confirmado. Si el túnel todavía no fue probado, mostrar UNKNOWN y no inferir DOWN. Mostrar estado anterior y fecha cuando no hay visibilidad. Un fallo de comando debe quedar visible como error técnico.

## Conectividad
La salud de WireGuard se evalúa con handshake como evidencia auxiliar y ping activo a la IP de túnel del MikroTik, que debe responder según la configuración/firewall pactada. Un handshake antiguo por sí solo no demuestra caída. Si la prueba de túnel falla repetidamente, marcar conectividad desconectada/inaccesible (no afirmar que el router está apagado). Durante la comprobación de pérdida de visibilidad, suspender confirmaciones de caídas de dispositivos hasta validar la conectividad. Crear un evento por transición de VPN, no uno por ping. Si se pierde el collector, mostrar STALE y conservar los estados de los equipos.

## Persistencia y API
- GET /api/v1/collector/config: equipos habilitados y configuración vigente, con IDs y revisiones.
- POST /api/v1/collector/heartbeat: señal de vida.
- POST /api/v1/collector/connectivity: estado de túnel y prueba activa.
- POST /api/v1/collector/diagnostics: diagnóstico de conectividad o de configuración WireGuard.
- POST /api/v1/collector/results: lote de checks con UUID de medición generado en collector, device_id, revisión, timestamp UTC, resultado y métricas.

En la fase 5, `config` entrega la configuración del túnel y `results` valida la credencial y responde 501. El scheduler de dispositivos y la recepción de mediciones se incorporan en la fase de monitoreo.
- Token por collector; el backend deduce empresa e identidad desde el token y comprueba asignación de cada dispositivo. Nunca confiar en company_id remitido por el cliente.
- Guardar en icmp_checks; actualizar device_status e incidents en una transacción, bloqueando estado por dispositivo. Idempotencia por (collector_id,measurement_id). Reenvíos duplicados no modifican contadores ni crean incidentes adicionales. Resultados antiguos o de revisión distinta no modifican el estado actual; pueden conservarse como histórico si son válidos y autorizados. Incrementar config_revision del dispositivo cuando cambie IP, collector o perfil; invalidar contadores/estado actual. Cerrar incidentes por cambio de configuración o retiro con motivo no equivalente a recuperación.
- Fecha de inicio del incidente: primer fallo de la racha que confirma DOWN; detected_at: confirmación. Fin: confirmación de recuperación; no inferir duración exacta durante períodos sin visibilidad. Registrar transiciones en status_events. Alertas internas de transición, sin repetir cada check; notificaciones externas después.
- Si backend cae, collector usa última configuración válida y cola local persistente acotada (propuesta: máximo 10 000 checks, 24 h; notificar descartes). Reintentos con backoff; no detener ICMP. Al volver API, enviar pendientes en orden; el backend evita regresiones y duplicados. Las credenciales revocadas no pueden seguir entregando resultados. La retención elimina mediciones antiguas por empresa, no borra incidentes/auditoría automáticamente.

## Soporte automático
Collector detenido o heartbeat vencido persistente (30 s por defecto): registrar STALE, intentar reconciliación/reinicio con límites y abrir o actualizar ticket SaaS por empresa + tipo/recurso; no duplicar. Recuperar visibilidad no cierra incidentes de equipos automáticamente. VPN caída genera evento y diagnóstico, no atribuir causa al ISP o a SKNet sin evidencia. Si se confirma fallo de infraestructura SKNet, ticket automático. Cierre de soporte con verificación; no simular que existe un ticket si BD/API inaccesible: reconciliar cuando vuelva.
