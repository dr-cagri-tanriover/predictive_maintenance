"""
Async serial orchestrator template for Raspberry Pi 3 Model B+ (CPython 3.x).

What this file gives you:
- A synchronous bootstrap section before the event loop starts (CLI args,
  optional ``pi3_serial_config.json``, or ``PM_UART_PORT`` / ``PM_UART_BAUD``).
- An async initialization phase.
- One RX task to process incoming serial bytes/frames.
- One TX task to send queued messages as framed packets.
- An optional interactive stdin menu (disable with ``--no-menu``).
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
import metadata_handler as mh
import utilities.uart_primitives as up

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
    - Interactive menu task reads stdin and dispatches placeholder actions.
    """

    def __init__(self, cfg: SerialConfig):
        self.cfg = cfg
        self._serial: Optional[serial.Serial] = None
        self._decoder = FrameDecoder()
        self._tx_queue: asyncio.Queue[dict] = asyncio.Queue()
        self._shutdown = asyncio.Event()
        self._tasks: list[asyncio.Task] = []
        self._seq = 0
        self._metadata: dict = {
            'minRunId': 0,
            'maxRunId': 0,
            'currentRunId': 0,
            'currentRunDict': {}
        }  # metadata related to available data collection runs

    async def initialize(self) -> None:
        """
        Async initialization phase (runs before background loops start).

        Add your startup actions here:
        - handshake / ping with peer
        - load runtime config
        - initialize any files/sensors/logging
        """

        # Get the run metadata for the run ID
        self._metadata['minRunId'], self._metadata['maxRunId'] = mh.get_minMax_runs()

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

        print(f"Pi3 B+ online !")

        #await self._send_startup_message()

    # async def _send_startup_message(self) -> None:
    #     """Example startup TX message. Replace with your real protocol init."""
    #     await self.enqueue_tx(msg_type=0x01, src_id=0x10, payload=b"pi3-online")

    async def start(self, *, interactive_menu: bool = True) -> None:
        """Start RX/TX background tasks and wait until shutdown is requested."""
        if self._serial is None:
            raise RuntimeError("Call initialize() before start().")

        self._tasks = [
            asyncio.create_task(self._rx_loop(), name="uart-rx-loop"),
            asyncio.create_task(self._tx_loop(), name="uart-tx-loop"),
            #asyncio.create_task(self._heartbeat_loop(), name="heartbeat-loop"),
        ]

        if interactive_menu:
            self._tasks.append(
                asyncio.create_task(
                    self._interactive_menu_loop(), name="interactive-menu"
                )
            )

        await self._shutdown.wait()  # wait for the shutdown event to be set. This is a blocking call.

    async def _interactive_menu_loop(self) -> None:
        """
        Simple stdin menu; runs in parallel with RX/TX.

        ``input()`` runs in a worker thread so blocking stdin does not stall
        the asyncio event loop.
        """
        while not self._shutdown.is_set():
            print(
                "\n--- Pi3 menu ---\n"
                "  1) Show connection status\n"
                "  2) Select run ID/number\n"
                "  3) Set waveform seq on Pi Zero\n"
                "  4) Get waveform seq from Pi Zero\n"
                "  5) Set brake seq on Pi Zero\n"
                "  6) Get brake seq from Pi Zero\n"
                "  7) Set PWM freq on Pi Zero\n"
                "  8) Get PWM freq from Pi Zero\n"
                "  9) Start capture on Pi Zero\n"
                "  10) Stop capture on Pi Zero\n"
                "  0) Exit (or quit)\n"
                "-----------------"
            )
            try:
                raw = await asyncio.to_thread(input, "Choice> ")
            except EOFError:
                print("(EOF)")
                self._shutdown.set()
                break

            choice = (raw or "").strip().lower()
            if choice in ("0", "q", "quit", "exit"):
                print("Exiting.")
                self._shutdown.set()
                break
            if choice == "1":
                await self.menu_action_show_status()
            elif choice == "2":
                await self.menu_action_enter_run_id()
            elif choice == "3":
                await self.menu_action_set_waveform()
            elif choice == "4":
                await self.menu_action_get_waveform()
            elif choice == "5":
                await self.menu_action_set_brake()
            elif choice == "6":
                await self.menu_action_get_brake()
            elif choice == "7":
                await self.menu_action_set_pwm_freq()
            elif choice == "8":
                await self.menu_action_get_pwm_freq()
            elif choice == "9":
                await self.menu_action_start_capture()
            elif choice == "10":
                await self.menu_action_stop_capture()
            else:
                print(f"Unknown choice: {choice!r}. Try 1–4 or 0.")

    async def menu_prompt_int(
        self,
        prompt: str,
        *,
        min_value: Optional[int] = None,
        max_value: Optional[int] = None,
    ) -> Optional[int]:
        """
        Read an integer from stdin without blocking the event loop.

        Returns ``None`` if the user enters nothing, ``c``/``cancel`` (case
        insensitive), input is not a valid integer, or value is outside bounds.
        """
        try:
            raw = await asyncio.to_thread(input, prompt)
        except EOFError:
            print("(EOF)")
            return None

        line = (raw or "").strip()
        if not line or line.lower() in ("c", "cancel"):
            return None

        try:
            value = int(line, 10)
        except ValueError:
            print(f"Not a valid integer: {line!r}")
            return None

        if min_value is None:
            min_value = self._metadata['minRunId']
        if max_value is None:
            max_value = self._metadata['maxRunId']
            if max_value == 0:
                print("No run metadata available!")
                return None

        if value < min_value:
            print(f"Value must be >= {min_value}, got {value}.")
            return None
        if value > max_value:
            print(f"Value must be <= {max_value}, got {value}.")
            return None

        return value

    ###########################################################
    # MENU ACTION DEFINITIONS START HERE
    ###########################################################

    async def menu_action_show_status(self) -> None:
        """Placeholder: print orchestrator state; replace with real status logic."""
        open_ = bool(self._serial and self._serial.is_open)
        print(
            f"Pi3 serial port={self.cfg.port!r}\n"
            f"Pi3 baudrate={self.cfg.baudrate}\n"
            f"serial_open={open_}\n"
            f"tx_queue_size≈{self._tx_queue.qsize()}\n"
        )

    async def menu_action_enter_run_id(self) -> None:
        """
        Menu entry 4: prompt for a run ID integer, then dispatch to hooks.

        Adjust ``min_value`` / ``max_value`` or replace ``menu_prompt_int`` with
        your own parser (e.g. zero-padded run codes).
        """
        self._metadata['currentRunId'] = await self.menu_prompt_int(
            "Run ID (integer, blank or 'c' to cancel)> "
        )

        if self._metadata['currentRunId'] is None:
            print("No run ID selected.")
            return

        await self.on_run_id_entered()  # reads collection metadata using self._metadata['currentRunId']
        # await self.after_run_id_entered()

    async def on_run_id_entered(self) -> None:
        """Hook: validate or resolve *run_id* (metadata path, DB key, etc.)."""
        self._metadata['currentRunDict'] = mh.get_run_metadata(self._metadata['currentRunId'])
        print(f"Read collection metadata for run_id={self._metadata['currentRunId']}")

    async def after_run_id_entered(self) -> None:
        """Hook: trigger side effects (UART notify, start collection, …)."""
        print(f"Valid run_id={self._metadata['currentRunId']}")

    async def menu_action_set_waveform(self) -> None:
        """Set the waveform sequence to use on the Pi Zero."""

        if len(self._metadata['currentRunDict']) == 0:
            print(f"Set valid run ID first. run_id={self._metadata['currentRunId']}")
            return

        # Get waveform parameters and create the payload for serial transmission.
        # payload will be binary after encoding.
        payload = json.dumps(self._metadata['currentRunDict']['(duty, duration)'], separators=(',', ':')).encode('utf-8')

        # Queue the SET_WAVEFORM_SEQ message to the Pi Zero
        await self.enqueue_tx(
            msg_type=up.MessageType.SET_WAVEFORM_SEQ,
            src_id=up.SourceId.RPI3_BPLUS,
            payload=payload
        )
        print(f"Waveform sequence sent to Pi Zero for run_id={self._metadata['currentRunId']}")

    async def menu_action_get_waveform(self) -> None:
        """Get the waveform sequence in use on the Pi Zero."""

        # Queue the GET_WAVEFORM_SEQ message to the Pi Zero
        await self.enqueue_tx(
            msg_type=up.MessageType.GET_WAVEFORM_SEQ,
            src_id=up.SourceId.RPI3_BPLUS,
            payload=b"0x00"   # unused as the command requires no arguments.
        )
        print(f"Reading waveform sequence from Pi Zero")

    async def menu_action_set_brake(self) -> None:
        """Set the brake sequence to use on the Pi Zero."""

        if len(self._metadata['currentRunDict']) == 0:
            print(f"Set valid run ID first. run_id={self._metadata['currentRunId']}")
            return

        # Get brake sequence parameters and create the payload for serial transmission.
        # payload will be binary after encoding.
        payload = json.dumps(self._metadata['currentRunDict']['(level, duration)'], separators=(',', ':')).encode('utf-8')

        # Queue the SET_WAVEFORM_SEQ message to the Pi Zero
        await self.enqueue_tx(
            msg_type=up.MessageType.SET_BRAKE_SEQ,
            src_id=up.SourceId.RPI3_BPLUS,
            payload=payload
        )
        print(f"Brake sequence sent to Pi Zero for run_id={self._metadata['currentRunId']}")

    async def menu_action_get_brake(self) -> None:
        """Get the brake sequence in use on the Pi Zero."""

        # Queue the GET_WAVEFORM_SEQ message to the Pi Zero
        await self.enqueue_tx(
            msg_type=up.MessageType.GET_BRAKE_SEQ,
            src_id=up.SourceId.RPI3_BPLUS,
            payload=b"0x00"   # unused as the command requires no arguments.
        )
        print(f"Reading brake sequence from Pi Zero")

    async def menu_action_set_pwm_freq(self) -> None:
        """Set the PWM frequency to use on the Pi Zero."""

        if len(self._metadata['currentRunDict']) == 0:
            print(f"Set valid run ID first. run_id={self._metadata['currentRunId']}")
            return

        # Get brake sequence parameters and create the payload for serial transmission.
        # payload will be binary after encoding.
        payload = str(self._metadata['currentRunDict']['pwm_freq_hz']).encode('utf-8')  # pwm is an int object

        # Queue the SET_PWM_FREQ message to the Pi Zero
        await self.enqueue_tx(
            msg_type=up.MessageType.SET_PWM_FREQ,
            src_id=up.SourceId.RPI3_BPLUS,
            payload=payload
        )
        print(f"PWM frequency in Hz sent to Pi Zero for run_id={self._metadata['currentRunId']}")

    async def menu_action_get_pwm_freq(self) -> None:
        """Get the PWM frequency in use on the Pi Zero."""

        # Queue the GET_WAVEFORM_SEQ message to the Pi Zero
        await self.enqueue_tx(
            msg_type=up.MessageType.GET_PWM_FREQ,
            src_id=up.SourceId.RPI3_BPLUS,
            payload=b"0x00"   # unused as the command requires no arguments.
        )
        print(f"Reading PWM frequency from Pi Zero")

    async def menu_action_start_capture(self) -> None:
        """Start the data capture on the Pi Zero."""
        await self.enqueue_tx(
            msg_type=up.MessageType.START_CAPTURE,
            src_id=up.SourceId.RPI3_BPLUS,
            payload=b"0x00"   # unused as the command requires no arguments.
        )
        print(f"Starting data capture on Pi Zero")

    async def menu_action_stop_capture(self) -> None:
        """Stop the data capture on the Pi Zero."""
        await self.enqueue_tx(
            msg_type=up.MessageType.STOP_CAPTURE,
            src_id=up.SourceId.RPI3_BPLUS,
            payload=b"0x00"   # unused as the command requires no arguments.
        )
        print(f"Stopping data capture on Pi Zero")

   ###########################################################
   # MENU ACTION DEFINITIONS END HERE
   ###########################################################

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
    parser.add_argument(
        "--no-menu",
        action="store_true",
        help="Do not start the interactive stdin menu (headless / scripted runs).",
    )
    return parser.parse_args(argv)


async def run(cfg: SerialConfig, *, interactive_menu: bool = True) -> None:
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
        await orch.start(interactive_menu=interactive_menu)
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
        asyncio.run(run(_cfg, interactive_menu=not _args.no_menu))
    except KeyboardInterrupt:
        pass
    finally:
        print(f"orchestrator exited after {time.time() - t0:.2f}s")
