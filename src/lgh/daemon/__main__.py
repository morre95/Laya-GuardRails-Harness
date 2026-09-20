from __future__ import annotations

import argparse

from lgh.daemon.server import serve


def main() -> None:
    parser = argparse.ArgumentParser(prog="lgh-daemon")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--device",
        default="cpu",
        help="torch device (cpu, cuda). 'gpu' is an alias for cuda.",
    )
    parser.add_argument("--no-preload", action="store_true")
    args = parser.parse_args()
    serve(host=args.host, port=args.port, preload=not args.no_preload, device=args.device)


if __name__ == "__main__":
    main()
