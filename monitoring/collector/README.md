# Collector

El collector Python sobre Alpine obtiene su configuración y envía heartbeat, estado del túnel y diagnósticos mediante REST autenticado sobre un socket Unix. Persiste la identidad y levanta `wg0` automáticamente. El ICMP de esta fase comprueba la IP WireGuard del router. La recepción de mediciones queda reservada para una fase posterior.

```sh
docker build -t sknet-collector:dev monitoring/collector
```

El provisioner crea los contenedores con sus redes y credenciales individuales. Los pasos de verificación están en [README.md](../../README.md).
