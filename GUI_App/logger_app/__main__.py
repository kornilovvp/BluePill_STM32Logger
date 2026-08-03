"""Точка входа: python -m logger_app [--sim] [--port COMx]."""

import argparse

from .app import App


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="logger_app",
        description="SLogger - 4-channel logger (2 analog + 2 digital, 10 kHz)",
    )
    parser.add_argument("--sim",  action="store_true",
                        help="simulator mode (no hardware needed)")
    parser.add_argument("--port", default=None,
                        help="device COM port (e.g. COM11)")

    App(parser.parse_args()).run()


if __name__ == "__main__":
    main()
