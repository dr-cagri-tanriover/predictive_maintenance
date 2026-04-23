"""
UART frame format and codec: pack, parse, and stream-decode frames for a UART link.

Wire format (all multibyte integers are little-endian on the wire):

    SOF1    (1 B)  0xA5
    SOF2    (1 B)  0x5A
    TYPE    (1 B)  application-defined message type
    SRC     (1 B)  source node / endpoint ID
    SEQ     (1 B)  sequence number (application-managed rollover)
    LEN     (1 B)  payload length N (0..255)
    PAYLOAD (N B)  opaque bytes for the application
    CRC16   (2 B)  CRC over bytes [TYPE .. last PAYLOAD byte], LE on wire

CRC algorithm (document this on both ends of the link):

    Polynomial 0x1021, initial value 0xFFFF, no input/output reflection,
    no final XOR (CRC-16/CCITT-FALSE style). If your peer uses a different
    variant, change ``crc16()`` below to match.

Usage — sending (application -> UART driver):

    from uart_frames import build_frame, crc16

    payload = b"\x01\x02\x03"
    frame = build_frame(
        msg_type=0x10,
        src_id=0x01,
        seq=0x07,
        payload=payload,
    )
    uart.write(frame)  # however your transport exposes ``write``

Usage — receiving (UART driver -> application), stream-safe:

    from uart_frames import FrameDecoder

    dec = FrameDecoder()
    while True:
        chunk = uart.read()  # or readinto, irq buffer drain, etc.
        if not chunk:
            continue
        for frame in dec.feed(chunk):
            # frame is a dict: type, src, seq, payload (bytes)
            handle_message(frame["type"], frame["src"], frame["seq"], frame["payload"])

If you prefer a pull API, call ``dec.feed(b"")`` only when you have data; the
decoder keeps leftover bytes between calls.

Threading: ``FrameDecoder`` is not synchronized; use one instance per UART or
guard calls with a lock.
"""

__all__ = [
    "SOF1",
    "SOF2",
    "crc16",
    "build_frame",
    "parse_frame_bytes",
    "FrameDecoder",
]

# --- Frame layout constants -------------------------------------------------

SOF1 = 0xA5
SOF2 = 0x5A

_HDR_AFTER_SOF = 4  # TYPE, SRC, SEQ, LEN
_CRC_LEN = 2
_MAX_PAYLOAD = 255  # LEN field is one byte
_MIN_FRAME = 2 + _HDR_AFTER_SOF + _CRC_LEN  # SOF + header + CRC, zero payload


# --- CRC16 (CCITT-FALSE). Adjust to match the far end if needed. ------------

_CRC16_POLY = 0x1021
_CRC16_INIT = 0xFFFF


def crc16(data):
    """Compute CRC-16 over *data* (bytes or bytearray)."""
    crc = _CRC16_INIT
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ _CRC16_POLY
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc


def build_frame(msg_type, src_id, seq = 0x00, payload=b"0x00"):
    """
    Pack one complete frame for transmission.

    ``payload`` must be 0..255 bytes (``LEN`` is a single byte on the wire).
    Returns a new ``bytes`` object ready for ``uart.write``.
    """
    if not isinstance(payload, (bytes, bytearray)):
        raise TypeError("payload must be bytes or bytearray")
    ln = len(payload)
    if ln > _MAX_PAYLOAD:
        raise ValueError("payload too long for LEN field")

    body = bytes(
        (
            msg_type & 0xFF,
            src_id & 0xFF,
            seq & 0xFF,
            ln & 0xFF,
        )
    ) + bytes(payload)

    c = crc16(body)
    crc_le = bytes((c & 0xFF, (c >> 8) & 0xFF))
    return bytes((SOF1, SOF2)) + body + crc_le


def parse_frame_bytes(frame_bytes):
    """
    Parse a *complete* frame (including SOF and CRC) without scanning.

    Returns dict with keys type, src, seq, payload, or raises ValueError.
    Useful for tests and when you already know buffer boundaries.
    """
    if len(frame_bytes) < _MIN_FRAME:
        raise ValueError("frame too short")
    if frame_bytes[0] != SOF1 or frame_bytes[1] != SOF2:
        raise ValueError("bad SOF")
    ln = frame_bytes[5]
    expected = 2 + _HDR_AFTER_SOF + ln + _CRC_LEN
    if len(frame_bytes) != expected:
        raise ValueError("length mismatch")
    body = frame_bytes[2 : 2 + _HDR_AFTER_SOF + ln]
    crc_wire = frame_bytes[2 + _HDR_AFTER_SOF + ln] | (
        frame_bytes[2 + _HDR_AFTER_SOF + ln + 1] << 8
    )
    if crc16(body) != crc_wire:
        raise ValueError("CRC mismatch")
    return {
        "type": body[0],
        "src": body[1],
        "seq": body[2],
        "payload": bytes(body[4:]),
    }


# --- Stream decoder: SOF lock + integrity check ------------------------------


def _bytearray_drop_prefix(buf, n):
    """
    Remove the first *n* bytes from *buf* in place.

    MicroPython's ``bytearray`` does not support ``del buf[:n]``; assignment
    ``buf[:] = buf[n:]`` works on CPython and MicroPython.
    """
    if n <= 0:
        return
    ln = len(buf)
    if n >= ln:
        buf[:] = b""  # replacement for buf.clear()
    else:
        buf[:] = buf[n:]


class FrameDecoder:
    """
    Incrementally consume arbitrary UART chunks, emit complete validated frames.

    Resynchronisation: after a bad CRC or malformed length, the decoder drops
    the false start (starting from the byte after the first SOF) and resumes
    searching for ``SOF1`` (0xA5) followed by ``SOF2`` (0x5A). If you expect
    large binary payloads, consider lowering ``max_payload`` so random data
    cannot spoof plausible lengths.
    """

    def __init__(self, max_payload=None):
        self._max_payload = max_payload if max_payload is not None else _MAX_PAYLOAD
        self._buf = bytearray()

    def reset(self):
        """Clear internal buffer (e.g. after UART error / baud change)."""
        self._buf[:] = b""  # replacement for self._buf.clear()

    def feed(self, data):
        """
        Push incoming UART *data* (bytes-like). Yields dicts for each good frame.

        Each yielded dict: ``type``, ``src``, ``seq``, ``payload`` (as ``bytes``,
        copied so you can safely mutate or retain it across feeds).
        """
        # Append new UART bytes; older tail from prior ``feed`` calls stays in _buf.
        if data:
            self._buf.extend(data)

        # Try to extract as many complete frames as the buffer currently holds.
        while True:
            n = len(self._buf)
            i = 0
            # Scan for the first SOF1 (0xA5) immediately followed by SOF2 (0x5A).
            while i < n:
                b0 = self._buf[i]
                if b0 == SOF1 and (i + 1) < n and self._buf[i + 1] == SOF2:
                    # Drop any noise before this sync pair so _buf[0:2] is SOF.
                    if i:
                        _bytearray_drop_prefix(self._buf, i)
                    break
                i += 1
            else:
                # No SOF1+SOF2 pair anywhere in _buf (scan exhausted index i).
                if n and self._buf[-1] == SOF1:
                    # Keep the trailing SOF1: the next ``feed`` may append SOF2 as the new last byte.
                    _bytearray_drop_prefix(self._buf, len(self._buf) - 1)
                else:
                    # No trailing SOF1 to “bridge” to the next chunk; nothing here can start a frame.
                    self._buf[:] = b""  # replacement for self._buf.clear()
                return

            # _buf layout: [0]=SOF1, [1]=SOF2, [2]=TYPE, [3]=SRC, [4]=SEQ, [5]=LEN, then payload + CRC.
            if len(self._buf) < (2 + _HDR_AFTER_SOF):
                return  # need full TYPE/SRC/SEQ/LEN before we know payload length

            ln = self._buf[5]  # LEN: payload byte count (0..255 on wire)
            if ln > self._max_payload:
                # Length policy violation: drop SOF and re-scan (may be false sync in noise).
                _bytearray_drop_prefix(self._buf, 2)
                continue

            total = 2 + _HDR_AFTER_SOF + ln + _CRC_LEN  # whole frame size in bytes
            if len(self._buf) < total:
                return  # wait for payload + CRC16

            # TYPE..PAYLOAD is what the CRC covers; CRC is stored little-endian after payload.
            # Copy slices before mutating the buffer (MicroPython: no del buf[:n] on bytearray).
            body = self._buf[2 : 6 + ln]
            crc_wire = self._buf[6 + ln] | (self._buf[6 + ln + 1] << 8)
            _bytearray_drop_prefix(self._buf, total)  # consume this frame from the stream buffer

            if crc16(body) != crc_wire:
                continue  # corrupt frame: discarded; outer loop hunts next SOF

            yield {
                "type": int(body[0]),
                "src": int(body[1]),
                "seq": int(body[2]),
                "payload": bytes(body[4:]),
            }


if __name__ == "__main__":
    # Run:  python uart_frames.py   (from this directory, or with utilities on PYTHONPATH)
    _payload = b"\x01\x02\x03"
    _frame = build_frame(msg_type=0x10, src_id=0x01, seq=0xAA, payload=_payload)
    _parsed = parse_frame_bytes(_frame)
    assert _parsed["type"] == 0x10 and _parsed["src"] == 0x01 and _parsed["seq"] == 0xAA
    assert _parsed["payload"] == _payload

    _dec = FrameDecoder()
    _parts = (_frame[:5], _frame[5:])
    _got = []
    for _p in _parts:
        _got.extend(_dec.feed(_p))
    assert len(_got) == 1 and _got[0]["payload"] == _payload

    print("uart_frames self-test: ok")

