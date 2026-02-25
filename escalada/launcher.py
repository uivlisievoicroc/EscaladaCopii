"""Production launcher for Escalada API + SPA with safe port fallback."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import socket
from dataclasses import dataclass

import uvicorn

from escalada import runtime_paths, runtime_state


@dataclass
class ReservedPort:
    socket: socket.socket
    port: int
    primary_busy: bool


def _build_logger() -> logging.Logger:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    return logging.getLogger("escalada.launcher")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Escalada server with port fallback.")
    parser.add_argument("--host", default=os.getenv("ESCALADA_BIND_HOST", "0.0.0.0"))
    parser.add_argument(
        "--port-min",
        type=int,
        default=int(os.getenv("ESCALADA_PORT_MIN", "8000")),
        help="Minimum port (inclusive). Default: 8000",
    )
    parser.add_argument(
        "--port-max",
        type=int,
        default=int(os.getenv("ESCALADA_PORT_MAX", "8100")),
        help="Maximum port (inclusive). Default: 8100",
    )
    parser.add_argument("--log-level", default=os.getenv("ESCALADA_LOG_LEVEL", "info"))
    return parser.parse_args()


def _reserve_port(host: str, port_min: int, port_max: int) -> ReservedPort:
    primary_busy = False
    for port in range(port_min, port_max + 1):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
            sock.listen(2048)
            sock.set_inheritable(True)
            return ReservedPort(socket=sock, port=port, primary_busy=primary_busy)
        except OSError:
            sock.close()
            if port == port_min:
                primary_busy = True
            continue

    raise RuntimeError(f"No free ports available in range {port_min}..{port_max}")


def main() -> None:
    args = _parse_args()
    if args.port_min > args.port_max:
        raise ValueError("--port-min must be <= --port-max")

    logger = _build_logger()
    paths = runtime_paths.configure_runtime_environment(logger)

    reserved = _reserve_port(args.host, args.port_min, args.port_max)
    selected_port = reserved.port
    bind_host = args.host

    if args.port_min == 8000 and reserved.primary_busy and selected_port != 8000:
        logger.warning("Port 8000 busy -> using %s", selected_port)
    else:
        logger.info("Using port %s", selected_port)

    base_url = f"http://{bind_host}:{selected_port}"
    runtime_state.set_runtime(host=bind_host, port=selected_port, base_url=base_url)
    os.environ["ESCALADA_RUNTIME_HOST"] = bind_host
    os.environ["ESCALADA_RUNTIME_PORT"] = str(selected_port)

    logger.info("Runtime paths: %s", paths)
    logger.info("Starting Escalada server on %s", base_url)

    config = uvicorn.Config(
        "escalada.main:app",
        host=bind_host,
        port=selected_port,
        workers=1,
        log_level=args.log_level,
    )
    server = uvicorn.Server(config)

    try:
        asyncio.run(server.serve(sockets=[reserved.socket]))
    finally:
        try:
            reserved.socket.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()

