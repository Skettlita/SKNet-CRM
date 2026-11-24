from pathlib import Path
import signal
import stat
import subprocess
import sys
import time


def main():
    children = []
    stopping = False

    def stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        for directory, app in (("sknet-worker", "worker"), ("sknet-collector", "agent")):
            path = Path("/run") / directory / "api.sock"
            try:
                if not stat.S_ISSOCK(path.lstat().st_mode):
                    raise RuntimeError("La ruta API interna está ocupada.")
                path.unlink()
            except FileNotFoundError:
                pass
            children.append(subprocess.Popen(["uvicorn", f"app.connectivity.private:{app}", "--uds",
                                              str(path), "--no-access-log"]))
        children.append(subprocess.Popen(sys.argv[1:]))
        while not stopping:
            for child in children:
                status = child.poll()
                if status is not None:
                    return status or 1
            time.sleep(0.5)
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=7)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
    return 0


if __name__ == "__main__":
    sys.exit(main())
