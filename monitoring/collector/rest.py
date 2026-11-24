import http.client
import json
import socket


class UnixConnection(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__("localhost", timeout=10)
        self.path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.path)


class ApiError(Exception):
    def __init__(self, status):
        self.status = status
        super().__init__(f"HTTP {status}")


def request(path, base, endpoint, data=None, *, method=None, token=None):
    connection = UnixConnection(path)
    try:
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        connection.request(method or ("GET" if data is None else "POST"), base + endpoint,
                           None if data is None else json.dumps(data), headers)
        response = connection.getresponse()
        payload = response.read()
        if response.status >= 400:
            raise ApiError(response.status)
        return json.loads(payload)
    finally:
        connection.close()
