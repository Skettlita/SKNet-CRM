import importlib.util
from pathlib import Path


def test_scheduler_limits_overlap_and_cycles_fairly(monkeypatch):
    directory = Path(__file__).resolve().parents[1] / "monitoring" / "collector"
    monkeypatch.syspath_prepend(str(directory))
    spec = importlib.util.spec_from_file_location("sknet_scheduler", directory / "scheduler.py")
    scheduler = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scheduler)

    targets = [
        {"id": "running", "ip": "192.168.5.1", "revision": 1},
        {"id": "same-ip", "ip": "192.168.5.1", "revision": 1},
        {"id": "scheduled", "ip": "192.168.5.5", "revision": 1},
        {"id": "never", "ip": "192.168.5.6", "revision": 1},
        {"id": "duplicate", "ip": "192.168.5.6", "revision": 1},
    ]
    running = {"running": (None, "192.168.5.1")}
    due = {"scheduled": (1, 10)}
    assert [item["id"] for item in scheduler.ready_targets(targets, running, due, 15, 2)] == ["never"]
    assert [item["id"] for item in scheduler.ready_targets(targets, running, due, 15, 3)] == ["never", "scheduled"]
    assert [item["id"] for item in scheduler.ready_targets(targets, running, due, 5, 3)] == ["never"]
