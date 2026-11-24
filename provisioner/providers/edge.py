import base64
import ipaddress
import json
import os
import ssl
from pathlib import Path
from typing import Protocol
from urllib.request import HTTPSHandler, HTTPRedirectHandler, Request, build_opener
from urllib.parse import quote, urlsplit


class Edge(Protocol):
    def occupied(self, first, last): ...
    def ensure(self, resource): ...
    def verify(self, resource): ...
    def remove(self, resource): ...


class Simulation:
    def occupied(self, first, last):
        return []

    def ensure(self, resource):
        if not resource["tag"] or not 1 <= resource["port"] <= 65535:
            raise ValueError("Invalid mock NAT assignment")

    def remove(self, resource):
        self.ensure(resource)

    def verify(self, resource):
        self.ensure(resource)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def port_matches(spec, port):
    if not spec:
        return True
    if spec.startswith("!"):
        return True
    for item in spec.split(","):
        try:
            parts = [int(part) for part in item.split("-")]
            if parts[0] <= port <= parts[-1]:
                return True
        except ValueError:
            return True
    return False


class RouterOS:
    nat = "/ip/firewall/nat"

    def __init__(self):
        self.endpoint = os.environ["SKNET_ROUTEROS_URL"].rstrip("/")
        url = urlsplit(self.endpoint)
        if url.scheme != "https" or not url.hostname or url.username or url.password or url.path or url.query or url.fragment:
            raise ValueError("RouterOS requires an HTTPS origin")
        self.wan = str(ipaddress.IPv4Address(os.environ["SKNET_ROUTEROS_WAN"]))
        self.host = str(ipaddress.IPv4Address(os.environ["SKNET_ROUTEROS_TARGET"]))
        self.forward_tag = os.environ["SKNET_ROUTEROS_FORWARD_TAG"]
        username = os.environ["SKNET_ROUTEROS_USER"]
        secret = Path(os.environ["SKNET_ROUTEROS_PASSWORD_FILE"]).read_text().rstrip("\r\n")
        self.authorization = "Basic " + base64.b64encode(f"{username}:{secret}".encode()).decode()
        context = ssl.create_default_context(cafile=os.getenv("SKNET_ROUTEROS_CA_FILE"))
        self.client = build_opener(HTTPSHandler(context=context), NoRedirect())

    def call(self, path, method="GET", fields=None):
        request = Request(self.endpoint + "/rest" + path,
                          json.dumps(fields).encode() if fields is not None else None,
                          {"Authorization": self.authorization, "Content-Type": "application/json"}, method=method)
        with self.client.open(request, timeout=8) as response:
            payload = response.read(2_000_001)
        if len(payload) > 2_000_000:
            raise ValueError("RouterOS response exceeds limit")
        return json.loads(payload) if payload else None

    def expected(self, resource):
        if resource["bind"] != self.host:
            raise ValueError("Host publishing address does not match the NAT target")
        return {"chain": "dstnat", "action": "dst-nat", "protocol": "udp", "dst-address": self.wan,
                "dst-port": str(resource["port"]), "to-addresses": self.host, "to-ports": str(resource["port"]),
                "comment": resource["tag"]}

    @staticmethod
    def same(rule, expected):
        for key, value in expected.items():
            actual = rule.get(key, "")
            if key in {"dst-address", "to-addresses"}:
                actual = actual.removesuffix("/32")
            if actual != value:
                return False
        return True

    def owned(self, rules, expected):
        tagged = [rule for rule in rules if rule.get("comment") == expected["comment"]]
        if len(tagged) > 1 or (tagged and not self.same(tagged[0], expected)):
            raise ValueError("Existing tagged rule differs from the stored allocation")
        return tagged[0] if tagged else None

    @staticmethod
    def may_match(rule, address, port):
        if rule.get("disabled") == "true" or rule.get("protocol") not in (None, "", "udp", "17"):
            return False
        dst = rule.get("dst-address")
        if dst:
            try:
                if ipaddress.IPv4Address(address) not in ipaddress.IPv4Network(dst, strict=False):
                    return False
            except ValueError:
                pass
        return port_matches(rule.get("dst-port"), port)

    def verify_forward(self, port):
        for rule in self.call("/ip/firewall/filter"):
            if rule.get("chain") != "forward" or not self.may_match(rule, self.host, port):
                continue
            if (rule.get("comment") == self.forward_tag and rule.get("action") == "accept"
                    and rule.get("protocol") in {"udp", "17"}
                    and rule.get("dst-address", "").removesuffix("/32") == self.host
                    and rule.get("connection-nat-state") == "dstnat" and rule.get("dst-port")):
                return
            states = rule.get("connection-state", "").split(",")
            if rule.get("action") in {"drop", "reject", "jump"} and (states == [""] or "new" in states or any("!" in s for s in states)):
                break
        raise ValueError("A compatible forward rule could not be verified")

    def occupied(self, first, last):
        rules = [rule for rule in self.call(self.nat) if rule.get("chain") == "dstnat"]
        return [port for port in range(first, last + 1) if any(self.may_match(rule, self.wan, port) for rule in rules)]

    def ensure(self, resource):
        expected = self.expected(resource)
        self.verify_forward(resource["port"])
        rules = self.call(self.nat)
        owned = self.owned(rules, expected)
        for rule in rules:
            if rule is owned:
                break
            if rule.get("chain") == "dstnat" and self.may_match(rule, self.wan, resource["port"]):
                raise ValueError("Existing NAT rule overlaps this assignment")
        if not owned:
            self.call(self.nat, "PUT", expected)
        self.verify(resource)

    def verify(self, resource):
        expected = self.expected(resource)
        self.verify_forward(resource["port"])
        rules = self.call(self.nat)
        verified = self.owned(rules, expected)
        if not verified or verified.get("disabled") == "true":
            raise ValueError("NAT rule could not be verified")
        for rule in rules[:rules.index(verified)]:
            if rule.get("chain") == "dstnat" and self.may_match(rule, self.wan, resource["port"]):
                raise ValueError("An earlier NAT rule overlaps the verified assignment")

    def remove(self, resource):
        expected = self.expected(resource)
        owned = self.owned(self.call(self.nat), expected)
        if owned:
            self.call(self.nat + "/" + quote(owned[".id"], safe=""), "DELETE")
        if self.owned(self.call(self.nat), expected):
            raise ValueError("NAT rule still exists")
