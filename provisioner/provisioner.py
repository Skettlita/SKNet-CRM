import argparse
import logging
import time

import docker

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Provisioner SKNet")
    parser.add_argument("--check", action="store_true", help="Comprobar Docker y salir.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    client = docker.from_env(timeout=4)
    try:
        client.ping()
        if args.check:
            return

        logger.info("Docker disponible. Aprovisionamiento pendiente de la fase 4.")
        while True:
            time.sleep(30)
            client.ping()
    finally:
        client.close()


if __name__ == "__main__":
    main()
