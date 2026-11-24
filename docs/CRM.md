# CRM empresarial

## Alta del abonado

En **CRM → Clientes → Registrar cliente**, completa los datos de la persona o empresa. La dirección inicial se guarda en **Contactos y direcciones** de su ficha. Para contratar un servicio en el mismo formulario, activa **Registrar un servicio contratado**, elige el plan, revisa o edita el precio y la moneda, define el acceso y selecciona el sitio y la situación inicial.

El sitio puede usar una referencia a la dirección del cliente. Si corriges esa dirección desde la ficha, el sitio refleja el cambio. Usa una dirección propia del sitio cuando la instalación tenga otra ubicación. El cliente puede tener varios sitios y varios servicios. Las pestañas de su ficha enlazan a los sitios, servicios y equipos asociados.

- **Nueva instalación** y **Pendiente de definir** crean el servicio en estado pendiente.
- **Servicio existente, previamente instalado** registra el servicio activo y deja constancia de la primera activación registrada en SKNet. La fecha de contratación se conserva por separado.
- El alta integrada verifica `clients.create`, y exige `sites.create` y `services.create` cuando incluye un servicio. Registrar un servicio activo también exige `services.status`. El plan debe incluir CRM. El formulario usa `internet_plans.read` para mostrar los planes disponibles.

La operación crea cliente, dirección, sitio, servicio, códigos e historial en una sola transacción. Después del alta, modifica los datos de cliente desde **Clientes**, las condiciones de contratación desde **Servicios**, los planes desde **Planes de Internet** y las ubicaciones desde **Sitios**.

## Sitios y dispositivos

**Sitios** separa ubicaciones de clientes, infraestructura de red e instalaciones propias. El listado permite buscar por nombre, código o cliente, filtrar por tipo y estado, ordenar y paginar en el servidor. Los servicios solo admiten sitios de su cliente.

Un **equipo de infraestructura** se ubica en un sitio de red o una instalación propia y puede tener capacidades de servidor PPPoE, servidor DHCP, router de acceso o distribución de red. Un **equipo final** se vincula a un cliente a través de uno de sus sitios y puede enlazarse a un servicio del mismo cliente y sitio. El rol topológico y la propiedad física del activo son independientes de la categoría funcional. La IP del servicio se registra en la contratación y la IPv4 de gestión en el dispositivo.

Un mismo equipo puede ser router de acceso para varios servicios. El selector muestra equipos de infraestructura activos en sitios activos, con capacidad **Servidor PPPoE** para PPPoE, **Servidor DHCP** para DHCP y **Router de acceso** para IP estática u otra modalidad. El campo es opcional. El backend aplica el mismo criterio a las nuevas asignaciones y cambios de modalidad.

## Migración y códigos

`0007_crm_workflow` conserva los UUID y los códigos existentes de clientes. Asigna códigos a sitios, servicios y dispositivos anteriores por fecha de alta e identificador dentro de cada empresa. Las altas usan contadores transaccionales separados por empresa y entidad, con restricciones de unicidad y códigos de solo lectura en el CRM.

- `CLIENT_SITE` pasa a **Sitios de clientes → Otro**. `NODE` pasa a **Infraestructura de red → Otro**. La clasificación genérica evita suponer si el sitio era un domicilio o si el nodo era principal o de distribución.
- `TOWER` conserva su tipo en infraestructura de red. `OFFICE`, `WAREHOUSE` y `WORKSHOP` quedan en instalaciones propias como oficina administrativa, almacén y taller. `OTHER` sin cliente queda en **Instalaciones propias → Otro**.
- Los equipos existentes se clasifican por su sitio. Sus roles, identificadores, servicios y activos se conservan. Si un equipo propio ya figuraba como router de acceso, se le asigna la capacidad correspondiente a las modalidades de sus servicios existentes. Las asociaciones históricas que hoy no serían elegibles se conservan hasta que un operador las corrija en su módulo.
- En servicios anteriores se conserva el estado y la fecha de activación. La situación inicial queda **Pendiente de definir** cuando falta esa información histórica.

Las órdenes de instalación, la asignación de técnicos y la activación automática de PPPoE o DHCP pertenecen a fases posteriores.
