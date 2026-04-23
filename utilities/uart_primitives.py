"""
Shared UART protocol symbols for the framed link (see ``uart_frames``).

The wire format uses 8-bit **TYPE** and **SRC** fields. This module is the
single place to name those values for every device (firmware, Pi, host tools).

**CPython and MicroPython:** symbols are plain ``int`` attributes on namespace
classes (no ``enum`` module). That avoids stdlib differences on small devices
while keeping the same import style on the Pi.

    from utilities.uart_primitives import MessageType, SourceId
    from utilities.uart_frames import build_frame

    frame = build_frame(
        msg_type=MessageType.PING,
        src_id=SourceId.RPI3_BPLUS,
        seq=0,
        payload=b"\x00",
    )

**Ranges (convention, adjust to your product):** reserve blocks so teams do not
collide, e.g. 0x00–0x0F system, 0x10–0x1F data plane, 0xF0–0xFF test/debug.

**Value → name:** use ``source_id_name()`` / ``message_type_name()``, or the
dicts ``SOURCE_ID_NAME`` / ``MESSAGE_TYPE_NAME`` (built from the classes above
so you do not maintain a second table). If two names share the same int, the
first definition wins.
"""

__all__ = [
    "MessageType",
    "SourceId",
    "SOURCE_ID_NAME",
    "MESSAGE_TYPE_NAME",
    "source_id_name",
    "message_type_name",
    "reverse_int_names",
]


def reverse_int_names(ns):
    """
    Map byte value (``int``) to the class attribute *name* for a namespace
    class of integer constants. Use for logs and debugging; unknown values are
    simply omitted from the result until you add a matching attribute.
    """
    out = {}
    for name, value in ns.__dict__.items():
        if name.startswith("_"):
            continue
        if isinstance(value, int) and not isinstance(value, bool):
            if value not in out:
                out[value] = name
    return out


# --- TYPE field (one byte) -------------------------------------------------


class MessageType:
    """
    Message type IDs for the TYPE field (use class attributes only; do not
    instantiate).
    """

    # Reserved / system (example block — document meaning per project)
    RESERVED_00 = 0x00
    #PING = 0x01  # example: pi3-online, discovery
 
    # RPI3_BPLUS messages [0x10-0x5F]
    SET_WAVEFORM_SEQ = 0x10  # Sends the waveform sequence for a run ID to the Pi Zero
    GET_WAVEFORM_SEQ = 0x20  # Requests the waveform sequence for a run ID from the Pi Zero

    SET_BRAKE_SEQ = 0x11  # Sends the brake sequence for a run ID to the Pi Zero
    GET_BRAKE_SEQ = 0x21  # Requests the brake sequence for a run ID from the Pi Zero

    SET_PWM_FREQ = 0x12  # Sends the PWM frequency for a run ID to the Pi Zero
    GET_PWM_FREQ = 0x22  # Requests the PWM frequency for a run ID from the Pi Zero

    START_CAPTURE = 0x50  # Starts the data capture for a run ID on the Pi Zero
    STOP_CAPTURE = 0x51  # Stops the data capture for a run ID on the Pi Zero

    #HEARTBEAT = 0x5F  # matches pi3_main heartbeat / lab traffic

    # RP2040_ZERO messages [0x60-0xBF]


    # PI_PICO messages [0xC0-0xFF]



# --- SRC field (one byte) --------------------------------------------------


class SourceId:
    """
    Node or logical source ID in the SRC field (use class attributes only).
    """
    UNKNOWN = 0x00
    RPI3_BPLUS = 0x11
    RP2040_ZERO = 0x21
    PI_PICO = 0x31


# Filled from the classes above (single source of truth).
MESSAGE_TYPE_NAME = reverse_int_names(MessageType)  # returns a dictionary of message type names and their corresponding values
SOURCE_ID_NAME = reverse_int_names(SourceId)  # returns a dictionary of source ID names and their corresponding values


def source_id_name(value):
    """``SourceId`` attribute name for *value* (0..255), or ``None`` if unknown."""
    return SOURCE_ID_NAME.get(int(value) & 0xFF)


def message_type_name(value):
    """``MessageType`` attribute name for *value* (0..255), or ``None`` if unknown."""
    return MESSAGE_TYPE_NAME.get(int(value) & 0xFF)


"""
Summary of UART messages and their payloads:
- SET_WAVEFORM_SEQ: Sends the waveform sequence for a run ID to the Pi Zero



- GET_WAVEFORM_SEQ: Requests the waveform sequence for a run ID from the Pi Zero
- SET_BRAKE_SEQ: Sends the brake sequence for a run ID to the Pi Zero
- GET_BRAKE_SEQ: Requests the brake sequence for a run ID from the Pi Zero
- SET_PWM_FREQ: Sends the PWM frequency for a run ID to the Pi Zero
- GET_PWM_FREQ: Requests the PWM frequency for a run ID from the Pi Zero
- START_CAPTURE: Starts the data capture for a run ID on the Pi Zero
- STOP_CAPTURE: Stops the data capture for a run ID on the Pi Zero


"""