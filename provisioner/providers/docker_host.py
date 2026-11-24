import io
import ipaddress
import json
import os
import tarfile

import docker
from docker.errors import NotFound


class DockerHost:
    def __init__(self, client):
        self.client = client
        self.image = os.getenv("SKNET_COLLECTOR_IMAGE", "sknet-collector:dev")
        self.api_volume = os.environ["SKNET_COLLECTOR_API_VOLUME"]
        self.socket_directory = "/run/sknet-collector"

    def inventory(self):
        networks = set()
        ports = set()
        for network in self.client.networks.list():
            for item in network.attrs.get("IPAM", {}).get("Config") or []:
                subnet = ipaddress.ip_network(item["Subnet"])
                if subnet.version == 4:
                    networks.add(str(subnet))
        for container in self.client.containers.list(all=True):
            for key, addresses in (container.attrs["HostConfig"].get("PortBindings") or {}).items():
                if key.endswith("/udp"):
                    ports.update(int(address["HostPort"]) for address in addresses or [] if address.get("HostPort"))
        return {"networks": sorted(networks), "ports": sorted(ports)}

    @staticmethod
    def labels(resource):
        return {"sknet.installation": resource["installation"], "sknet.company": resource["company"],
                "sknet.collector": resource["id"]}

    @staticmethod
    def optional(collection, name):
        try:
            return collection.get(name)
        except NotFound:
            return None

    def owned(self, resource, collection, name):
        item = self.optional(collection, name)
        if item:
            labels = item.attrs.get("Labels") or item.attrs.get("Config", {}).get("Labels") or {}
            if any(labels.get(key) != value for key, value in self.labels(resource).items()):
                raise ValueError("Resource name is owned by another workload")
        return item

    def ensure_network(self, resource):
        name = resource["network_name"]
        subnet = ipaddress.IPv4Network(resource["docker_subnet"])
        existing = self.owned(resource, self.client.networks, name)
        if existing:
            config = existing.attrs["IPAM"]["Config"]
            if (existing.attrs["Driver"] != "bridge" or len(config) != 1
                    or config[0]["Subnet"] != str(subnet) or config[0]["Gateway"] != str(subnet[1])
                    or existing.attrs["Options"].get("com.docker.network.bridge.enable_icc") != "false"):
                raise ValueError("Network settings do not match the allocation")
            if any(endpoint["Name"] != resource["name"] for endpoint in (existing.attrs["Containers"] or {}).values()):
                raise ValueError("Collector network has an unexpected endpoint")
            return
        ipam = docker.types.IPAMConfig(pool_configs=[docker.types.IPAMPool(subnet=str(subnet), gateway=str(subnet[1]))])
        self.client.networks.create(name, driver="bridge", ipam=ipam, labels=self.labels(resource),
                                    options={"com.docker.network.bridge.enable_icc": "false"})

    def ensure_container(self, resource, identity, *, restart=False):
        name = resource["name"]
        volume_name = name + "-data"
        network = resource["network_name"]
        address = str(ipaddress.IPv4Network(resource["docker_subnet"])[2])
        port = f"{resource['internal_port']}/udp"
        if not self.owned(resource, self.client.volumes, volume_name):
            self.client.volumes.create(name=volume_name, labels=self.labels(resource))
        container = self.owned(resource, self.client.containers, name)
        if not container:
            api = self.client.api
            config = api.create_networking_config({network: api.create_endpoint_config(ipv4_address=address)})
            container = self.client.containers.create(
                self.image, name=name, network=network, networking_config=config,
                labels=self.labels(resource), ports={port: (resource["bind"], resource["port"])},
                cap_drop=["ALL"], cap_add=["NET_ADMIN", "NET_RAW"],
                security_opt=["no-new-privileges"], read_only=True,
                tmpfs={"/tmp": "rw,noexec,nosuid,size=4m"},
                restart_policy={"Name": "unless-stopped"},
                volumes={
                    volume_name: {"bind": "/state", "mode": "rw"},
                    self.api_volume: {"bind": self.socket_directory, "mode": "ro"},
                },
            )
        host = container.attrs["HostConfig"]
        mounts = {(mount.get("Name"), mount["Destination"], mount["RW"]) for mount in container.attrs["Mounts"]}
        endpoints = container.attrs["NetworkSettings"]["Networks"]
        if (host["Privileged"] or set(host["CapDrop"] or []) != {"ALL"} or set(host["CapAdd"] or []) != {"NET_ADMIN", "NET_RAW"}
                or host["NetworkMode"] != network
                or host["PortBindings"] != {port: [{"HostIp": resource["bind"], "HostPort": str(resource["port"])}]}
                or mounts != {(volume_name, "/state", True), (self.api_volume, self.socket_directory, False)}
                or set(endpoints) - {network}
                or (network in endpoints and endpoints[network].get("IPAddress") not in ("", address))):
            raise ValueError("Existing collector does not match its isolated runtime configuration")
        if restart and container.status == "running":
            container.stop(timeout=5)
            container.reload()
        if container.status != "running":
            payload = json.dumps(identity).encode()
            archive = io.BytesIO()
            with tarfile.open(fileobj=archive, mode="w") as tar:
                entry = tarfile.TarInfo("identity.json")
                entry.mode = 0o600
                entry.size = len(payload)
                tar.addfile(entry, io.BytesIO(payload))
            container.put_archive("/state", archive.getvalue())
            container.start()
        return container

    def retire(self, resource, *, remove):
        container = self.owned(resource, self.client.containers, resource["name"])
        if container:
            container.stop(timeout=8)
            if remove:
                container.remove(v=False)
        if remove:
            network = self.owned(resource, self.client.networks, resource["network_name"])
            if network:
                network.remove()
            if (self.optional(self.client.containers, resource["name"])
                    or self.optional(self.client.networks, resource["network_name"])):
                raise ValueError("Resources still exist")
