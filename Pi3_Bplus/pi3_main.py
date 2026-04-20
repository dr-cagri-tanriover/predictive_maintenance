"""
Async serial orchestrator template for Raspberry Pi 3 Model B+ (CPython 3.x).

What this file gives you:
- A synchronous bootstrap section before the event loop starts (CLI args,
  optional ``pi3_serial_config.json``, or ``PM_UART_PORT`` / ``PM_UART_BAUD``).
- An async initialization phase.
- One RX task to process incoming serial bytes/frames.
- One TX task to send queued messages as framed packets.
- Clean shutdown handling for Ctrl+C and task cancellation.

Dependencies:
- Python 3.x
- pyserial: `pip install pyserial`
"""

import argparse
import asyncio
import json
import os
import signal
import sys
import time
from dataclasses import dataclass
from typing import Optional

try:
    import serial
except ImportError as exc:  # pragma: no cover - bootstrap guard
    raise RuntimeError(
        "pyserial is required. Install with: pip install pyserial"
    ) from exc


_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_SERIAL_CONFIG = os.path.join(_DIR, "pi3_serial_config.json")
_REPO_ROOT = os.path.dirname(_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from utilities.uart_frames import FrameDecoder, build_frame


@dataclass
class SerialConfig:
    port: str = "/dev/serial0"  # update for your setup (e.g., /dev/ttyS0, /dev/ttyAMA0)
    baudrate: int = 921600  #115200
    timeout_sec: float = 0.05  # short timeout keeps blocking reads responsive
    write_timeout_sec: float = 0.2


class AsyncSerialOrchestrator:
    """
    Template orchestrator:
    - RX loop reads bytes from UART and decodes framed messages.
    - TX loop waits for app messages and writes framed packets.
    """

    def __init__(self, cfg: SerialConfig):
        self.cfg = cfg
        self._serial: Optional[serial.Serial] = None
        self._decoder = FrameDecoder()
        self._tx_queue: asyncio.Queue[dict] = asyncio.Queue()
        self._shutdown = asyncio.Event()
        self._tasks: list[asyncio.Task] = []
        self._seq = 0

    async def initialize(self) -> None:
        """
        Async initialization phase (runs before background loops start).

        Add your startup actions here:
        - handshake / ping with peer
        - load runtime config
        - initialize any files/sensors/logging
        """
        try:
            self._serial = serial.Serial(
                port=self.cfg.port,
                baudrate=self.cfg.baudrate,
                timeout=self.cfg.timeout_sec,
                write_timeout=self.cfg.write_timeout_sec,
            )
            
            if self._serial != None:
                print(f"Connected to serial port {self.cfg.port} at {self.cfg.baudrate} baud")
            
        except (OSError, serial.SerialException) as exc:
            raise RuntimeError(
                f"Could not open serial port {self.cfg.port!r}: {exc}"
            ) from exc
        await self._send_startup_message()

    async def _send_startup_message(self) -> None:
        """Example startup TX message. Replace with your real protocol init."""
        await self.enqueue_tx(msg_type=0x01, src_id=0x10, payload=b"pi3-online")

    async def start(self) -> None:
        """Start RX/TX background tasks and wait until shutdown is requested."""
        if self._serial is None:
            raise RuntimeError("Call initialize() before start().")

        self._tasks = [
            asyncio.create_task(self._rx_loop(), name="uart-rx-loop"),
            asyncio.create_task(self._tx_loop(), name="uart-tx-loop"),
            asyncio.create_task(self._heartbeat_loop(), name="heartbeat-loop"),
        ]

        await self._shutdown.wait()  # wait for the shutdown event to be set. This is a blocking call.

    async def stop(self) -> None:
        """Graceful shutdown: stop tasks and close serial."""
        self._shutdown.set()

        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        if self._serial and self._serial.is_open:
            self._serial.close()

    async def enqueue_tx(self, msg_type: int, src_id: int, payload: bytes) -> None:
        """Application API: queue a message to be framed and transmitted."""
        await self._tx_queue.put(
            {
                "msg_type": msg_type & 0xFF,
                "src_id": src_id & 0xFF,
                "payload": bytes(payload),
            }
        )

    async def _rx_loop(self) -> None:
        """Continuously read UART bytes and decode complete frames."""
        assert self._serial is not None

        try:
            while not self._shutdown.is_set():
                # Run blocking serial.read in a worker thread to keep asyncio responsive.
                chunk = await asyncio.to_thread(self._serial.read, 256)
                if not chunk:
                    await asyncio.sleep(0.002)
                    continue

                for frame in self._decoder.feed(chunk):
                    await self.handle_incoming_frame(frame)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[RX] loop error: {exc}")
            self._shutdown.set()

    async def _tx_loop(self) -> None:
        """Send queued outgoing messages as framed UART packets."""
        assert self._serial is not None

        try:
            while not self._shutdown.is_set():
                # Timeout lets us periodically check shutdown without blocking forever.
                try:
                    msg = await asyncio.wait_for(self._tx_queue.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    continue

                frame = build_frame(
                    msg_type=msg["msg_type"],
                    src_id=msg["src_id"],
                    seq=self._next_seq(),
                    payload=msg["payload"],
                )

                # Run blocking serial.write in a worker thread so that it does not block the event loop!
                await asyncio.to_thread(self._serial.write, frame)
                self._tx_queue.task_done()

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[TX] loop error: {exc}")
            self._shutdown.set()

    async def _heartbeat_loop(self) -> None:
        """
        Optional periodic sender (template).
        Remove if not needed, or replace with your scheduler/business logic.
        """
        try:
            while not self._shutdown.is_set():
                await asyncio.sleep(5.0)
                await self.enqueue_tx(msg_type=0x7E, src_id=0x10, payload=b"hb")
        except asyncio.CancelledError:
            raise

    async def handle_incoming_frame(self, frame: dict) -> None:
        """
        Application hook for decoded frames.
        Extend with routing by frame['type'], command handlers, logging, etc.
        """
        msg_type = frame["type"]
        src = frame["src"]
        seq = frame["seq"]
        payload = frame["payload"]
        print(f"[RX] type=0x{msg_type:02X} src=0x{src:02X} seq={seq} payload={payload!r}")

    def _next_seq(self) -> int:
        """Increment and wrap sequence number to 1 byte."""
        self._seq = (self._seq + 1) & 0xFF
        return self._seq


def bootstrap_config(
    *,
    port: Optional[str] = None,
    baudrate: Optional[int] = None,
    config_path: Optional[str] = None,
) -> SerialConfig:
    """
    Build ``SerialConfig`` before the asyncio loop starts.

    **Precedence (first wins):** ``port`` / ``baudrate`` arguments → JSON
    config file → ``PM_UART_PORT`` / ``PM_UART_BAUD`` → built-in defaults.

    **JSON config (no shell exports):** if ``config_path`` is omitted, a file
    named ``pi3_serial_config.json`` next to ``pi3_main.py`` is read when it
    exists. Example contents::

        {"port": "/dev/serial/by-id/usb-FTDI_...", "baudrate": 115200}

    ``baud`` is accepted as an alias for ``baudrate`` in JSON.

    Serial port (Linux):
    - Paths under ``/dev/serial/by-id/`` must match udev exactly (see
      ``ls -l /dev/serial/by-id/``).
    - User must be in group ``dialout`` (or equivalent) for USB UART access.
    """
    cfg_file = config_path if config_path is not None else _DEFAULT_SERIAL_CONFIG
    file_data: dict = {}
    if cfg_file and os.path.isfile(cfg_file):
        with open(cfg_file, encoding="utf-8") as f:
            file_data = json.load(f)

    raw_port = port if port is not None else file_data.get("port")
    if raw_port is None or (isinstance(raw_port, str) and not raw_port.strip()):
        raw_port = os.environ.get("PM_UART_PORT") or "/dev/serial0"
    raw_port = str(raw_port).strip()

    baud_src = baudrate
    if baud_src is None:
        if "baudrate" in file_data:
            baud_src = file_data["baudrate"]
        elif "baud" in file_data:
            baud_src = file_data["baud"]
    if baud_src is None:
        raw_baud = (os.environ.get("PM_UART_BAUD") or "115200").strip()
    else:
        raw_baud = str(baud_src).strip()

    try:
        baud = int(raw_baud)
    except ValueError as exc:
        raise RuntimeError(
            f"Invalid baud rate {raw_baud!r}; use an integer such as 115200."
        ) from exc
        
    return SerialConfig(port=raw_port, baudrate=baud)


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pi3 async UART orchestrator (see bootstrap_config precedence)."
    )
    parser.add_argument(
        "--port",
        default=None,
        help="Serial device path (overrides JSON config and PM_UART_PORT).",
    )
    parser.add_argument(
        "--baud",
        type=int,
        default=None,
        help="Baud rate (overrides JSON config and PM_UART_BAUD).",
    )
    parser.add_argument(
    
        "--config",
        default=None,
        metavar="PATH",
        help=(
            f"JSON file with keys port, baudrate (default if file exists: "
            f"{_DEFAULT_SERIAL_CONFIG})"
        ),
    )
    return parser.parse_args(argv)


async def run(cfg: SerialConfig) -> None:
    """Build orchestrator from *cfg*, initialize it, then run until interrupted."""
    orch = AsyncSerialOrchestrator(cfg)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):  # for handling Ctrl+C and SIGTERM signals to gracefully exit the program.
        try:
            loop.add_signal_handler(sig, orch._shutdown.set)
        except NotImplementedError:
            # Windows event loops may not support signal handlers.
            pass

    await orch.initialize()
    try:
        await orch.start()
    finally:
        await orch.stop()


if __name__ == "__main__":
    t0 = time.time()
    try:
        _args = parse_args()
        _cfg = bootstrap_config(
            port=_args.port,
            baudrate=_args.baud,
            config_path=_args.config,
        )
        asyncio.run(run(_cfg))
    except KeyboardInterrupt:
        pass
    finally:
        print(f"orchestrator exited after {time.time() - t0:.2f}s")
