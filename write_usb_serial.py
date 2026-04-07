#!/usr/bin/env python3
"""Write repeated serial data to a USB serial device."""

from __future__ import annotations

import argparse
import signal
import sys
import time
from typing import Iterable

import serial
from serial.tools import list_ports


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Write repeated USB serial data on macOS or Windows."
    )
    parser.add_argument(
        "-p",
        "--port",
        help="Serial port path, for example /dev/cu.usbmodem12301 or COM3",
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
        help="Write timeout in seconds (default: 1.0)",
    )
    parser.add_argument(
        "--encoding",
        default="utf-8",
        help="Text encoding for input data (default: utf-8)",
    )
    parser.add_argument(
        "--message",
        default="Hello from pyserial",
        help="Text payload to send repeatedly (default: Hello from pyserial)",
    )
    parser.add_argument(
        "--append-newline",
        action="store_true",
        help="Append a newline to each message",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Seconds to wait between writes (default: 1.0)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=0,
        help="Number of times to send the message. 0 means forever (default: 0)",
    )
    parser.add_argument(
        "--startup-delay",
        type=float,
        default=2.0,
        help="Seconds to wait after opening the port before writing (default: 2.0)",
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


def build_payload(args: argparse.Namespace) -> bytes:
    message = args.message
    if args.append_newline:
        message += "\n"
    return message.encode(args.encoding)


def write_loop(args: argparse.Namespace) -> int:
    if args.interval < 0:
        raise SystemExit("--interval must be 0 or greater.")
    if args.count < 0:
        raise SystemExit("--count must be 0 or greater.")

    port = resolve_port(args.port)
    stopbits = {
        1: serial.STOPBITS_ONE,
        1.5: serial.STOPBITS_ONE_POINT_FIVE,
        2: serial.STOPBITS_TWO,
    }[args.stopbits]
    payload = build_payload(args)
    ser = serial.Serial(
        port=port,
        baudrate=args.baudrate,
        bytesize=args.bytesize,
        parity=args.parity,
        stopbits=stopbits,
        write_timeout=args.timeout,
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

    count_text = "forever" if args.count == 0 else f"{args.count} times"
    print(
        f"Writing to {port} at {args.baudrate} baud, {count_text}. Press Ctrl+C to stop.",
        file=sys.stderr,
    )
    if args.startup_delay > 0:
        print(
            f"Waiting {args.startup_delay:.1f}s after opening the port.",
            file=sys.stderr,
        )
        time.sleep(args.startup_delay)

    writes_done = 0
    try:
        while not should_stop and (args.count == 0 or writes_done < args.count):
            ser.write(payload)
            ser.flush()
            writes_done += 1
            print(
                f"[{writes_done}] sent {len(payload)} bytes: {payload.hex(' ')}",
                file=sys.stderr,
                flush=True,
            )
            if args.interval > 0 and (args.count == 0 or writes_done < args.count):
                time.sleep(args.interval)
    finally:
        ser.close()
        print("\nSerial port closed.", file=sys.stderr)
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.list:
        return list_detected_ports()

    return write_loop(args)


if __name__ == "__main__":
    raise SystemExit(main())
