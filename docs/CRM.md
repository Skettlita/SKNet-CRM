# CRM empresarial

## Alta del abonado

En **CRM → Clientes → Registrar cliente**, completa los datos de la persona o empresa. La dirección inicial se guarda en **Contactos y direcciones** de su ficha. Para contratar un servicio en el mismo formulario, activa **Registrar un servicio contratado**, elige el plan, revisa el precio y la moneda, define el acceso y selecciona el estado administrativo inicial.

Al usar la dirección del cliente, el sitio toma automáticamente su código comercial como nombre y referencia la misma dirección y ciudad. Si corriges la dirección desde la ficha, el sitio refleja el cambio. Una ubicación adicional admite un nombre y una dirección propios. Las coordenadas son opcionales. Las pestañas de la ficha enlazan a sitios, servicios y equipos.

- **Pendiente de activación** registra el servicio sin una activación administrativa.
- **Activo** registra la primera activación administrativa en SKNet. Se conserva por separado la fecha de contratación.
- El alta integrada verifica `clients.create`, y exige `sites.create` y `services.create` cuando incluye un servicio. Registrar un servicio activo también exige `services.status`. El plan debe incluir CRM. El formulario usa `internet_plans.read` para mostrar los planes disponibles.

La operación registra cliente, dirección, sitio, servicio, códigos e historial en una transacción. Si se selecciona un equipo de stock, la misma transacción lo vincula al cliente, sitio y servicio con estado **Asignado**. Las órdenes de instalación se crean voluntariamente desde la ficha del servicio pendiente.

## Sitios y dispositivos

**Sitios** separa ubicaciones de clientes, infraestructura de red e instalaciones propias. El listado permite buscar por nombre, código o cliente, filtrar por tipo y estado, ordenar y paginar en el servidor. Los servicios solo admiten sitios de su cliente.

Un **equipo de infraestructura** se ubica en un sitio de red o una instalación propia y puede tener capacidades de servidor PPPoE, servidor DHCP, router de acceso o distribución de red. Un **equipo final** se vincula a un cliente a través de uno de sus sitios y puede enlazarse a un servicio del mismo cliente y sitio. El rol topológico y la propiedad física del activo son independientes de la categoría funcional. La IP del servicio se registra en la contratación y la IPv4 de gestión en el dispositivo.

Un mismo equipo puede ser router de acceso para varios servicios. El selector muestra equipos de infraestructura instalados y activos en sitios activos, con capacidad **Servidor PPPoE** para PPPoE, **Servidor DHCP** para DHCP y **Router de acceso** para IP estática u otra modalidad. El campo es opcional. El backend aplica el mismo criterio a las nuevas asignaciones y cambios de modalidad.

## Inventario

En **Inventario → Catálogos**, registra tipos, fabricantes y modelos. Cada modelo pertenece a un tipo y fabricante de su empresa. Desactivar un registro conserva sus referencias. El sistema protege la eliminación de catálogos en uso.

En **Inventario → Stock de equipos**, cada lote admite de 1 a 200 unidades de un modelo y categoría. Todas reciben su propio código `DSP` y comienzan disponibles, sin sitio, servicio ni IP. El resumen agrupa por modelo y muestra los estados. Haz clic en el nombre de un modelo para ver sus unidades y entrar a sus fichas. El alta de clientes y las fichas CRM permiten asignar por modelo o unidad. Si dos operadores seleccionan la misma unidad, se confirma una única asignación.

La API ISP ofrece `GET/POST /api/v1/isp/inventory/catalog/{types|manufacturers|models}`, `PUT/DELETE /api/v1/isp/inventory/catalog/{sección}/{id}`, `GET /api/v1/isp/inventory/stock` y `/stock/units`, y `POST /api/v1/isp/inventory/stock/batches` y `/stock/assign`. Los roles delegados necesitan permiso de inventario para consultar catálogos. La asignación exige también escritura de dispositivos.

## Migración y códigos

`0007_crm_workflow` conserva los UUID y los códigos existentes de clientes. Asigna códigos a sitios, servicios y dispositivos anteriores por fecha de alta e identificador dentro de cada empresa. Las altas usan contadores transaccionales separados por empresa y entidad, con restricciones de unicidad y códigos de solo lectura en el CRM.

- `CLIENT_SITE` pasa a **Sitios de clientes → Otro**. `NODE` pasa a **Infraestructura de red → Otro**. La clasificación genérica evita suponer si el sitio era un domicilio o si el nodo era principal o de distribución.
- `TOWER` conserva su tipo en infraestructura de red. `OFFICE`, `WAREHOUSE` y `WORKSHOP` quedan en instalaciones propias como oficina administrativa, almacén y taller. `OTHER` sin cliente queda en **Instalaciones propias → Otro**.
- Los equipos existentes se clasifican por su sitio. Sus roles, identificadores, servicios y activos se conservan. Si un equipo propio ya figuraba como router de acceso, se le asigna la capacidad correspondiente a las modalidades de sus servicios existentes. Las asociaciones históricas que hoy no serían elegibles se conservan hasta que un operador las corrija en su módulo.
- En servicios anteriores se conserva el estado y la fecha de activación. La situación inicial queda **Pendiente de definir** cuando falta esa información histórica.

## Asignaciones e instalaciones

Un equipo disponible puede registrarse sin ubicación ni IP. Desde la ficha del cliente o sitio, abre **Dispositivos → Asignar equipo disponible**. El equipo puede pasar a asignado, instalado o mantenimiento. Para desasignar o trasladar un equipo, edita su situación y ubicación en su ficha. Los cambios se consultan en **Asignaciones**. Archivar un equipo lo retira de la operación y conserva su historial.

La IPv4 de gestión puede quedar sin configurar, registrarse como independiente o heredarse del servicio asociado. Una IP heredada desaparece si el servicio deja de tener IPv4. Cambiarla invalida la revisión anterior y la información histórica conserva el destino de cada muestra.

La ficha de un servicio pendiente conserva la opción **Crear instalación**. En la ficha de la orden es posible programar, asignar técnicos, registrar equipos, cancelar o completar la instalación. La finalización conserva el flujo de verificación manual y puede activar el servicio y solicitar monitoreo según permisos.

Archivar excluye el registro de las listas operativas y conserva su historial. Desactivar un equipo suspende su uso administrativo. Retirar un equipo termina su operación y su monitoreo. **Eliminar** exige confirmación, motivo y permiso. Se pueden eliminar altas erróneas de servicios con solo el estado inicial automático y equipos de stock sin uso. El sistema devuelve las dependencias que bloquean una eliminación. La auditoría y los contadores de códigos se conservan.
