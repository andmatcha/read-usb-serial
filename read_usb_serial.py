#!/usr/bin/env python3
"""Read serial data from a USB serial device and print it to the terminal."""

from __future__ import annotations

import argparse
import signal
import sys
from typing import Iterable

import serial
from serial.tools import list_ports


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read USB serial data on macOS and print it to stdout."
    )
    parser.add_argument(
        "-p",
        "--port",
        help="Serial port path, for example /dev/cu.usbmodem12301",
    )
    parser.add_argument(
        "-b",
        "--baudrate",
        type=int,
        default=9600,
        help="Baud rate (default: 9600)",
    )
    parser.add_argument(
        "--bytesize",
        type=int,
        choices=(5, 6, 7, 8),
        default=8,
        help="Data bits (default: 8)",
    )
    parser.add_argument(
        "--parity",
        choices=("N", "E", "O", "M", "S"),
        default="N",
        help="Parity: N/E/O/M/S (default: N)",
    )
    parser.add_argument(
        "--stopbits",
        type=float,
        choices=(1, 1.5, 2),
        default=1,
        help="Stop bits (default: 1)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=1.0,
        help="Read timeout in seconds (default: 1.0)",
    )
    parser.add_argument(
        "--encoding",
        default="utf-8",
        help="Text encoding for output (default: utf-8)",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Print raw bytes as hex instead of decoding as text",
    )
    parser.add_argument(
        "--startup-delay",
        type=float,
        default=2.0,
        help="Seconds to wait after opening the port before reading (default: 2.0)",
    )
    parser.add_argument(
        "--dtr",
        choices=("on", "off", "keep"),
        default="keep",
        help="Set DTR after opening the port (default: keep)",
    )
    parser.add_argument(
        "--rts",
        choices=("on", "off", "keep"),
        default="keep",
        help="Set RTS after opening the port (default: keep)",
    )
    parser.add_argument(
        "--idle-log-seconds",
        type=float,
        default=5.0,
        help="Emit a stderr message if no data arrives for this many seconds (default: 5.0)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List detected serial ports and exit",
    )
    return parser


def available_ports() -> list[list_ports.ListPortInfo]:
    return sorted(list_ports.comports(), key=lambda port: port.device)


def format_port_lines(ports: Iterable[list_ports.ListPortInfo]) -> list[str]:
    lines = []
    for port in ports:
        details = port.description or "Unknown device"
        if port.manufacturer:
            details = f"{details} / {port.manufacturer}"
        lines.append(f"{port.device}: {details}")
    return lines


def list_detected_ports() -> int:
    ports = available_ports()
    if not ports:
        print("No serial ports detected.")
        return 1

    print("Detected serial ports:")
    for line in format_port_lines(ports):
        print(f"  {line}")
    return 0


def resolve_port(port_arg: str | None) -> str:
    if port_arg:
        return port_arg

    ports = available_ports()
    if not ports:
        raise SystemExit(
            "No serial ports detected. Connect your USB serial device and rerun with --list."
        )
    if len(ports) > 1:
        choices = "\n".join(f"  {line}" for line in format_port_lines(ports))
        raise SystemExit(
            "Multiple serial ports detected. Specify one with --port.\n"
            f"{choices}"
        )
    return ports[0].device


def read_loop(args: argparse.Namespace) -> int:
    import time

    port = resolve_port(args.port)
    stopbits = {1: serial.STOPBITS_ONE, 1.5: serial.STOPBITS_ONE_POINT_FIVE, 2: serial.STOPBITS_TWO}[args.stopbits]
    ser = serial.Serial(
        port=port,
        baudrate=args.baudrate,
        bytesize=args.bytesize,
        parity=args.parity,
        stopbits=stopbits,
        timeout=args.timeout,
    )

    if args.dtr != "keep":
        ser.dtr = args.dtr == "on"
    if args.rts != "keep":
        ser.rts = args.rts == "on"

    should_stop = False

    def handle_signal(_signum: int, _frame: object) -> None:
        nonlocal should_stop
        should_stop = True

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    print(
        f"Reading from {port} at {args.baudrate} baud. "
        f"Press Ctrl+C to stop.",
        file=sys.stderr,
    )
    if args.startup_delay > 0:
        print(
            f"Waiting {args.startup_delay:.1f}s after opening the port.",
            file=sys.stderr,
        )
        time.sleep(args.startup_delay)

    last_data_at = time.monotonic()
    try:
        while not should_stop:
            chunk = ser.read(ser.in_waiting or 1)
            if not chunk:
                now = time.monotonic()
                if args.idle_log_seconds > 0 and now - last_data_at >= args.idle_log_seconds:
                    print(
                        "No serial data received yet. Check baudrate, port, wiring, "
                        "device settings, and whether the device needs a command before it transmits.",
                        file=sys.stderr,
                    )
                    last_data_at = now
                continue
            last_data_at = time.monotonic()
            if args.raw:
                print(chunk.hex(" "), flush=True)
                continue
            text = chunk.decode(args.encoding, errors="replace")
            print(text, end="", flush=True)
    finally:
        ser.close()
        print("\nSerial port closed.", file=sys.stderr)
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.list:
        return list_detected_ports()

    return read_loop(args)


if __name__ == "__main__":
    raise SystemExit(main())
