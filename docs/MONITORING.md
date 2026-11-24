# Monitoreo ICMP

El scheduler vive en cada collector y ejecuta pruebas IPv4 por `wg0`. Obtiene destinos y entrega lotes mediante REST autenticado sobre su socket Unix. La NAT puede estar simulada en DEV y el transporte WireGuard, los pings y los resultados siguen siendo reales. El provisioner administra infraestructura Docker y el backend aplica la política de estado.

## Destinos y configuración

Se requiere un equipo instalado, administrativamente habilitado, con perfil solicitado, IPv4 efectiva, sitio vigente, suscripción con `ICMP` y destino incluido en una red WireGuard autorizada. La IPv4 puede ser independiente o heredada por referencia al servicio. Las direcciones repetidas dentro de la empresa se rechazan al solicitar monitoreo y el backend distribuye como máximo un equipo por IP. Empresas distintas pueden usar la misma dirección. El cupo del plan limita la distribución y el perfil respeta el intervalo mínimo del plan.

El listado permite filtrar por cliente, sitio, tipo de catálogo, categoría, rol y estado técnico. Para equipos inelegibles, el listado y la ficha muestran causas como asignación pendiente, IP ausente, red sin autorización, collector no disponible o destino duplicado.

| Parámetro | Valor inicial |
|---|---|
| Intervalo de perfil | 30 s. Para el ensayo DEV se configuró 10 s. |
| Paquetes | 5 |
| Tiempo de espera | 2000 ms |
| Advertencia por RTT medio | Más de 200 ms |
| Advertencia por pérdida | Más de 0 % |
| Umbral de fallo por pérdida | 40 % inclusive. Los perfiles previamente guardados conservan sus valores. |
| Rachas | 3 fallos para confirmar caída, 2 comprobaciones aceptables para recuperar. |
| Concurrencia | 10 por collector. `SKNET_ICMP_CONCURRENCY` admite de 1 a 32 para nuevos contenedores. |
| Retención de muestras | Según la versión de plan asignada o `SKNET_ICMP_RETENTION_DAYS`, inicialmente 30 días. |

Con cinco paquetes, cuatro respuestas producen una muestra aceptable con advertencia, y tres respuestas producen una muestra fallida. El RTT elevado produce degradación si la pérdida sigue dentro de la tolerancia. Un error al ejecutar ping se registra como diagnóstico técnico y no cuenta como caída. El scheduler mantiene un solo check por equipo o IP, ordena los vencimientos y no ejecuta rondas atrasadas. El heartbeat y la comprobación del peer siguen un ciclo independiente. Cuando la API se interrumpe brevemente, el collector puede usar hasta 90 s la última lista válida si el ping local al peer sigue vigente. La cola persistente conserva hasta 10 000 muestras por 24 h y reintenta la entrega en lotes de 100.

## Estados, incidencias y disponibilidad

- **Disponible** y **Degradado** reflejan mediciones válidas. Una falla aislada puede mostrar degradación mientras se confirma el estado. Para confirmar **Caído** se exige la racha del perfil y una prueba satisfactoria del túnel posterior al comienzo de la racha.
- Una VPN desconectada produce **Inalcanzable**. La pérdida del heartbeat o de mediciones produce **Datos vencidos**. Un equipo sin IP o sin asignación se muestra como **Sin configurar**. **Sin datos** identifica falta de mediciones útiles en el contexto vigente y **Deshabilitado** indica monitoreo desactivado o equipo retirado.
- La primera pérdida de visibilidad bloquea nuevas confirmaciones individuales. La revisión del equipo y la época del transporte descartan rachas anteriores. Los resultados duplicados son idempotentes y los atrasados no revierten el estado más reciente. Una caída de VPN genera un incidente de transporte y conserva los incidentes individuales abiertos. Solo nuevas respuestas suficientes confirman la recuperación de un equipo. Un cambio de destino configura un cierre administrativo distinto de una recuperación.
- La disponibilidad histórica se calcula sobre comprobaciones aceptables entre las muestras válidas. Los intervalos sin cobertura suficiente se muestran por separado. No es una medición continua del SLA. La retención solo purga muestras y conserva el estado consolidado, los incidentes y la auditoría.
- Los fallos de infraestructura administrada del collector pueden abrir tickets SaaS mediante la reconciliación existente. Los incidentes de dispositivos o desconexiones de VPN permanecen en el ámbito del ISP salvo evidencia de un problema de plataforma.

La confirmación de caída registra el estado y el incidente en la misma transacción. El listado de incidentes consulta cambios cada cinco segundos mientras está abierto. Los filtros permanecen seleccionados durante la actualización.

Las gráficas ofrecen 30 min, 1 h, 24 h y 7 días con agrupaciones de 2, 5, 60 y 240 minutos, respectivamente. Las escalas de pérdida y disponibilidad abarcan de 0 a 100 %. Un intervalo sin muestras válidas deja un espacio en la serie y una sola agrupación válida aparece como un punto.

## API y comprobación

- `GET /api/v1/collector/config` obtiene WireGuard y `GET /api/v1/collector/targets` obtiene destinos y perfiles habilitados para el token.
- `POST /api/v1/collector/heartbeat`, `/connectivity` y `/diagnostics` registran señales de vida y evidencia del enlace.
- `POST /api/v1/collector/results` valida pertenencia, IP, revisión, contexto, conteos y UUID de medición. PostgreSQL conserva las muestras y sus resultados técnicos.
- `GET /api/v1/isp/monitoring/device-types` devuelve las opciones de catálogo. `GET /api/v1/isp/monitoring/devices` acepta `type_id` y expone `eligibility_reason`. `GET /api/v1/isp/monitoring/devices/{id}?period=30m` incluye las agrupaciones y muestras de los últimos 30 minutos.

Desde DEV, una vez construido el collector actualizado y aprovisionado en una conexión de prueba con rutas autorizadas, configura un equipo instalado y solicita monitoreo. Consulta **Red → Monitoreo** y **Red → Incidentes**. En la ficha, usa **Monitoreo** para consultar cobertura, latencia, pérdida e historial.

```sh
docker build -t sknet-collector:dev monitoring/collector
docker compose --env-file .env.dev -f compose.yaml -f compose.dev.yaml ps
docker ps --filter label=sknet.installation=sknet-dev
docker logs --tail 40 NOMBRE_DEL_COLLECTOR_DE_PRUEBA
docker compose --env-file .env.dev -f compose.yaml -f compose.dev.yaml exec postgres psql -U sknet_dev -d sknet_dev -c "SELECT checked_at,result,packets_sent,packets_received,latency_ms,packet_loss_pct,transport_healthy FROM monitoring.icmp_checks ORDER BY checked_at DESC LIMIT 10"
```

Construir una imagen conserva los contenedores existentes en su versión. La actualización de un collector ya operativo requiere una ventana autorizada. Las pruebas de fallos deben usar un peer y un destino descartables.
