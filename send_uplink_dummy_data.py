#!/usr/bin/env python3
"""Continuously send dummy Arm and Rover data matching uplink input formats."""

from __future__ import annotations

import argparse
import math
import queue
import signal
import struct
import sys
import threading
from dataclasses import dataclass
from collections.abc import Callable, Iterable, Sequence

import serial
from serial.tools import list_ports

ARM_PACKET_BODY_FORMAT = "<2sBB7H3H3hBhHH"
ARM_PACKET_FORMAT = f"{ARM_PACKET_BODY_FORMAT}H"
ARM_PACKET_SIZE = struct.calcsize(ARM_PACKET_FORMAT)
DEFAULT_ROVER_CAN_IDS = (0x120, 0x121, 0x122, 0x123)


@dataclass
class SenderConfig:
    name: str
    port: str
    interval: float
    payload_factory: Callable[[int], bytes]
    sent_count: int = 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Send dummy Arm and/or Rover serial data that matches the uplink firmware "
            "input validation rules."
        )
    )
    parser.add_argument(
        "--arm-port",
        help="Serial port connected to uplink USART2 (Arm input)",
    )
    parser.add_argument(
        "--rover-port",
        help="Serial port connected to uplink USART1 (Rover input)",
    )
    parser.add_argument(
        "-b",
        "--baudrate",
        type=int,
        default=115200,
        help="Baud rate for both ports (default: 115200)",
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
        "--startup-delay",
        type=float,
        default=2.0,
        help="Seconds to wait after opening each port before writing (default: 2.0)",
    )
    parser.add_argument(
        "--dtr",
        choices=("on", "off", "keep"),
        default="keep",
        help="Set DTR after opening each port (default: keep)",
    )
    parser.add_argument(
        "--rts",
        choices=("on", "off", "keep"),
        default="keep",
        help="Set RTS after opening each port (default: keep)",
    )
    parser.add_argument(
        "--arm-interval",
        type=float,
        default=0.1,
        help="Seconds between Arm packets (default: 0.1)",
    )
    parser.add_argument(
        "--rover-interval",
        type=float,
        default=0.1,
        help="Seconds between Rover batches (default: 0.1)",
    )
    parser.add_argument(
        "--rover-can-ids",
        nargs="+",
        type=parse_can_id,
        default=list(DEFAULT_ROVER_CAN_IDS),
        help=(
            "11-bit CAN IDs for Rover text frames. Accepts decimal or 0x-prefixed hex "
            "(default: 0x120 0x121 0x122 0x123)."
        ),
    )
    parser.add_argument(
        "--send-mode",
        choices=("parallel", "alternate"),
        default="parallel",
        help=(
            "How to send enabled streams. "
            "'parallel' starts one sender per port, 'alternate' sends Arm and Rover in turn "
            "(default: parallel)"
        ),
    )
    parser.add_argument(
        "--status-every",
        type=int,
        default=10,
        help="Print a status line every N writes per sender. 0 disables periodic logs (default: 10)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List detected serial ports and exit",
    )
    return parser


def parse_can_id(raw_value: str) -> int:
    try:
        value = int(raw_value, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid CAN ID {raw_value!r}. Use decimal or 0x-prefixed hexadecimal."
        ) from exc
    if not 0 <= value <= 0x7FF:
        raise argparse.ArgumentTypeError(
            f"CAN ID {raw_value!r} is out of range. Expected 0x000 to 0x7FF."
        )
    return value


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


def crc16_ccitt_false(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def clamp_u16(value: int) -> int:
    return max(0, min(0xFFFF, value))


def clamp_i16(value: int) -> int:
    return max(-0x8000, min(0x7FFF, value))


def build_arm_packet(sample_index: int) -> bytes:
    phase = sample_index * 0.15
    seq = sample_index & 0xFF
    flags = ((sample_index // 20) & 0x03) | 0x10
    current = tuple(
        clamp_u16(int(900 + 150 * math.sin(phase + axis * 0.35) + axis * 40))
        for axis in range(7)
    )
    angle = tuple(
        clamp_u16(int((sample_index * (29 + axis * 9) + axis * 750) % 3600))
        for axis in range(3)
    )
    velocity = tuple(
        clamp_i16(int(240 * math.sin(phase * 1.4 + axis * 0.8)))
        for axis in range(3)
    )
    control_byte = 0x20 | (sample_index & 0x0F)
    base_rel_mm_j0 = clamp_i16(int(600 * math.sin(phase * 0.5)))
    auto_flags = 0x0001 | (0x0004 if (sample_index // 15) % 2 else 0x0000)
    fault_code = 0x0000

    packet_without_crc = struct.pack(
        ARM_PACKET_BODY_FORMAT,
        b"AC",
        seq,
        flags,
        *current,
        *angle,
        *velocity,
        control_byte,
        base_rel_mm_j0,
        auto_flags,
        fault_code,
    )
    crc = crc16_ccitt_false(packet_without_crc)
    packet = packet_without_crc + struct.pack("<H", crc)
    if len(packet) != ARM_PACKET_SIZE:
        raise AssertionError(f"Expected {ARM_PACKET_SIZE} bytes, got {len(packet)} bytes.")
    return packet


def build_rover_batch(sample_index: int, can_ids: Sequence[int]) -> bytes:
    lines = []
    for offset, can_id in enumerate(can_ids):
        value = clamp_i16(
            int(1800 * math.sin(sample_index * 0.28 + offset * 0.65) + offset * 120)
        )
        lines.append(f"0x{can_id:03X},{value}\r\n")
    return "".join(lines).encode("ascii")


def format_status(name: str, payload: bytes) -> str:
    if name == "Arm":
        seq = payload[2]
        crc = int.from_bytes(payload[-2:], "little")
        return f"seq={seq} bytes={len(payload)} crc=0x{crc:04X}"

    first_line = payload.decode("ascii").splitlines()[0]
    line_count = payload.count(b"\n")
    return f"lines={line_count} bytes={len(payload)} first={first_line}"


def open_serial_port(args: argparse.Namespace, port: str) -> serial.Serial:
    stopbits = {
        1: serial.STOPBITS_ONE,
        1.5: serial.STOPBITS_ONE_POINT_FIVE,
        2: serial.STOPBITS_TWO,
    }[args.stopbits]
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
    return ser


def sender_loop(
    args: argparse.Namespace,
    sender: SenderConfig,
    stop_event: threading.Event,
    errors: queue.SimpleQueue[str],
) -> None:
    ser: serial.Serial | None = None
    try:
        ser = open_serial_port(args, sender.port)
        print(
            f"{sender.name}: writing to {sender.port} at {args.baudrate} baud every "
            f"{sender.interval:.3f}s.",
            file=sys.stderr,
            flush=True,
        )
        if args.startup_delay > 0:
            print(
                f"{sender.name}: waiting {args.startup_delay:.1f}s after opening the port.",
                file=sys.stderr,
                flush=True,
            )
            if stop_event.wait(args.startup_delay):
                return

        while not stop_event.is_set():
            payload = sender.payload_factory(sender.sent_count)
            ser.write(payload)
            ser.flush()
            sender.sent_count += 1

            if args.status_every > 0 and sender.sent_count % args.status_every == 0:
                print(
                    f"{sender.name}: sent {sender.sent_count} writes "
                    f"({format_status(sender.name, payload)})",
                    file=sys.stderr,
                    flush=True,
                )

            if sender.interval > 0 and stop_event.wait(sender.interval):
                break
    except Exception as exc:
        errors.put(f"{sender.name} sender failed on {sender.port}: {exc}")
        stop_event.set()
    finally:
        if ser is not None:
            ser.close()
            print(f"{sender.name}: serial port closed.", file=sys.stderr, flush=True)


def alternate_loop(
    args: argparse.Namespace,
    senders: Sequence[SenderConfig],
    stop_event: threading.Event,
) -> int:
    ports: list[tuple[SenderConfig, serial.Serial]] = []
    try:
        for sender in senders:
            ser = open_serial_port(args, sender.port)
            ports.append((sender, ser))
            print(
                f"{sender.name}: opened {sender.port} at {args.baudrate} baud for alternating send.",
                file=sys.stderr,
                flush=True,
            )

        if args.startup_delay > 0:
            print(
                f"Alternate mode: waiting {args.startup_delay:.1f}s after opening ports.",
                file=sys.stderr,
                flush=True,
            )
            if stop_event.wait(args.startup_delay):
                return 0

        while not stop_event.is_set():
            for sender, ser in ports:
                if stop_event.is_set():
                    break

                payload = sender.payload_factory(sender.sent_count)
                ser.write(payload)
                ser.flush()
                sender.sent_count += 1

                if args.status_every > 0 and sender.sent_count % args.status_every == 0:
                    print(
                        f"{sender.name}: sent {sender.sent_count} writes "
                        f"({format_status(sender.name, payload)})",
                        file=sys.stderr,
                        flush=True,
                    )

                if sender.interval > 0 and stop_event.wait(sender.interval):
                    break
    except Exception as exc:
        print(f"Alternate sender failed: {exc}", file=sys.stderr)
        return 1
    finally:
        for sender, ser in ports:
            ser.close()
            print(f"{sender.name}: serial port closed.", file=sys.stderr, flush=True)

    return 0


def build_senders(args: argparse.Namespace) -> list[SenderConfig]:
    senders: list[SenderConfig] = []
    if args.arm_port:
        senders.append(
            SenderConfig(
                name="Arm",
                port=args.arm_port,
                interval=args.arm_interval,
                payload_factory=build_arm_packet,
            )
        )
    if args.rover_port:
        senders.append(
            SenderConfig(
                name="Rover",
                port=args.rover_port,
                interval=args.rover_interval,
                payload_factory=lambda sample_index: build_rover_batch(
                    sample_index, args.rover_can_ids
                ),
            )
        )
    return senders


def validate_args(args: argparse.Namespace) -> None:
    if args.list:
        return
    if not args.arm_port and not args.rover_port:
        raise SystemExit("Specify at least one of --arm-port or --rover-port.")
    if args.arm_port and args.rover_port and args.arm_port == args.rover_port:
        raise SystemExit("--arm-port and --rover-port must be different ports.")
    if args.arm_interval < 0:
        raise SystemExit("--arm-interval must be 0 or greater.")
    if args.rover_interval < 0:
        raise SystemExit("--rover-interval must be 0 or greater.")
    if args.timeout <= 0:
        raise SystemExit("--timeout must be greater than 0.")
    if args.startup_delay < 0:
        raise SystemExit("--startup-delay must be 0 or greater.")
    if args.status_every < 0:
        raise SystemExit("--status-every must be 0 or greater.")
    if not args.rover_can_ids:
        raise SystemExit("Specify at least one CAN ID with --rover-can-ids.")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    validate_args(args)

    if args.list:
        return list_detected_ports()

    stop_event = threading.Event()
    errors: queue.SimpleQueue[str] = queue.SimpleQueue()
    threads: list[threading.Thread] = []

    def handle_signal(_signum: int, _frame: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    senders = build_senders(args)
    if args.send_mode == "alternate":
        return alternate_loop(args, senders, stop_event)

    for sender in senders:
        thread_name = f"{sender.name.lower()}-sender"
        threads.append(
            threading.Thread(
                target=sender_loop,
                name=thread_name,
                args=(args, sender, stop_event, errors),
            )
        )

    for thread in threads:
        thread.start()

    try:
        while any(thread.is_alive() for thread in threads):
            for thread in threads:
                thread.join(timeout=0.2)
            try:
                error_message = errors.get_nowait()
            except queue.Empty:
                continue
            print(error_message, file=sys.stderr)
            return 1
    finally:
        stop_event.set()
        for thread in threads:
            thread.join()

    try:
        error_message = errors.get_nowait()
    except queue.Empty:
        return 0
    print(error_message, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
