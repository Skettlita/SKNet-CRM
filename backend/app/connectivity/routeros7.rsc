# SKNet / RouterOS 7. Revisa los nombres y los permisos antes de aplicar.
# El router genera su clave privada local. Comparte únicamente public-key.
# Permite ICMP de @SERVER_IP@ hacia @CLIENT_IP@ y forward solo hacia redes de gestión autorizadas.
# Verifica las rutas de retorno de esas redes. Ajusta tu firewall local bajo tu política vigente.
# Si el router utiliza un Allowed Address existente incompatible, revisa manualmente antes de reutilizarlo.
{
:local wgName "@LABEL@"
:local tag "SKNet @LABEL@"
:local wg [/interface/wireguard find where name=$wgName]
:if ([:len $wg] = 0) do={
    /interface/wireguard add name=$wgName mtu=@MTU@ comment=$tag
    :set wg [/interface/wireguard find where name=$wgName]
}
:if ([/interface/wireguard get $wg comment] != $tag) do={ :error "La interfaz ya existe y pertenece a otra configuracion" }
:local addr [/ip/address find where address="@CLIENT_IP@"]
:if ([:len $addr] = 0) do={ /ip/address add address="@CLIENT_IP@" interface=$wgName comment=$tag } else={
    :if ([:len $addr] != 1) do={ :error "Direccion duplicada; revisar manualmente" }
    :if ([/ip/address get $addr interface] != $wgName || [/ip/address get $addr comment] != $tag) do={ :error "Direccion en uso" }
}
:local peer [/interface/wireguard/peers find where comment=$tag]
:if ([:len $peer] = 0) do={
    /interface/wireguard/peers add interface=$wgName public-key="@PUBLIC_KEY@" endpoint-address="@ENDPOINT@" endpoint-port=@PORT@ allowed-address="@SERVER_IP@" persistent-keepalive=@KEEPALIVE@s comment=$tag
} else={
    :if ([:len $peer] != 1) do={ :error "Peer duplicado; revisar manualmente" }
    :if ([/interface/wireguard/peers get $peer interface] != $wgName || [/interface/wireguard/peers get $peer public-key] != "@PUBLIC_KEY@") do={ :error "Peer en conflicto; revisar manualmente" }
}
:put [/interface/wireguard get $wg public-key]
}
