import importlib.util
from pathlib import Path
from urllib.parse import unquote

import pytest


module_path = Path(__file__).resolve().parents[1] / "provisioner" / "providers" / "edge.py"
spec = importlib.util.spec_from_file_location("sknet_edge", module_path)
edge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(edge)


RESOURCE = {"bind": "10.90.0.254", "port": 51821, "tag": "SKNet:dev-collector"}
FORWARD = {"chain": "forward", "protocol": "udp", "dst-address": "10.90.0.254/32",
           "dst-port": "51820-51919", "connection-nat-state": "dstnat", "action": "accept", "comment": "WG forward"}
EXTERNAL = {"chain": "dstnat", "protocol": "udp", "dst-address": "192.0.2.1", "dst-port": "51820",
            "action": "dst-nat", ".id": "*7", "comment": "External workload"}


@pytest.fixture
def router():
    instance = object.__new__(edge.RouterOS)
    instance.host = RESOURCE["bind"]
    instance.wan = "192.0.2.1"
    instance.forward_tag = "WG forward"
    rules = [EXTERNAL.copy()]
    filters = [FORWARD.copy()]
    mutations = []

    def fake_call(path, method="GET", fields=None):
        if path == "/ip/firewall/filter":
            return list(filters)
        if method == "GET":
            return list(rules)
        if method == "PUT":
            rules.append({**fields, ".id": "*8"})
        elif method == "DELETE":
            rules[:] = [rule for rule in rules if rule[".id"] != unquote(path.split("/")[-1])]
        mutations.append(method)
    instance.call = fake_call
    return instance, rules, filters, mutations


def test_routeros_uses_only_verified_tagged_rule(router):
    instance, rules, _, mutations = router
    assert instance.occupied(51820, 51822) == [51820]
    instance.ensure(RESOURCE)
    instance.ensure(RESOURCE)
    instance.verify(RESOURCE)
    assert mutations == ["PUT"]
    assert rules[1]["to-addresses"] == RESOURCE["bind"] and rules[1]["to-ports"] == str(RESOURCE["port"])
    instance.remove(RESOURCE)
    instance.remove(RESOURCE)
    assert rules == [EXTERNAL] and mutations == ["PUT", "DELETE"]


def test_routeros_rejects_collisions_firewall_and_modified_rule(router):
    instance, rules, filters, mutations = router
    with pytest.raises(ValueError, match="overlaps"):
        instance.ensure(RESOURCE | {"port": 51820})
    filters.insert(0, {"chain": "forward", "protocol": "udp", "action": "drop"})
    with pytest.raises(ValueError, match="forward"):
        instance.ensure(RESOURCE)
    assert mutations == []
    filters.pop(0)
    instance.ensure(RESOURCE)
    rules[-1]["to-ports"] = "51822"
    with pytest.raises(ValueError, match="differs"):
        instance.remove(RESOURCE)
    assert mutations == ["PUT"] and len(rules) == 2
