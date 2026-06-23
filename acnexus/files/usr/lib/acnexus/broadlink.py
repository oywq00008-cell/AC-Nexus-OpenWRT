"""AC-Nexus 精简博联库 — 仅保留 RM 系列红外遥控器支持
从 python-broadlink 提取，删除 alarm/climate/cover/hub/light/switch/sensor
只保留 RM mini/pro/mini3/mini4/pro4 的发现/认证/发码功能
"""
import socket
import threading
import random
import time
import struct
from typing import Optional, List, Tuple, Union

from pyaes.aes import AESModeOfOperationCBC

# ═══════════════ Constants ═══════════════
DEFAULT_BCAST_ADDR = "255.255.255.255"
DEFAULT_PORT = 80
DEFAULT_RETRY_INTVL = 1
DEFAULT_TIMEOUT = 10

# ═══════════════ Datetime pack ═══════════════
import datetime as dt


def _pack_datetime(datetime: dt.datetime) -> bytes:
    """Pack timestamp for Broadlink hello packet."""
    data = bytearray(12)
    utcoffset = int(datetime.utcoffset().total_seconds() / 3600)
    data[:0x04] = utcoffset.to_bytes(4, "little", signed=True)
    data[0x04:0x06] = datetime.year.to_bytes(2, "little")
    data[0x06] = datetime.minute
    data[0x07] = datetime.hour
    data[0x08] = int(datetime.strftime("%y"))
    data[0x09] = datetime.isoweekday()
    data[0x0A] = datetime.day
    data[0x0B] = datetime.month
    return data


def _now() -> dt.datetime:
    """Return current datetime with timezone info."""
    tz_info = dt.timezone(dt.timedelta(seconds=-time.timezone))
    return dt.datetime.now(tz_info)


# ═══════════════ Exceptions ═══════════════
class BroadlinkException(Exception):
    def __init__(self, *args):
        super().__init__(*args)
        if len(args) >= 2:
            self.errno = args[0]
            self.strerror = ": ".join(str(a) for a in args[1:])
        elif len(args) == 1:
            self.errno = None
            self.strerror = str(args[0])
        else:
            self.errno = None
            self.strerror = ""

    def __str__(self):
        if self.errno is not None:
            return "[Errno %s] %s" % (self.errno, self.strerror)
        return self.strerror


class NetworkTimeoutError(BroadlinkException):
    """Network timeout."""


class DataValidationError(BroadlinkException):
    """Data validation error."""


class AuthenticationError(BroadlinkException):
    """Authentication error."""


class AuthorizationError(BroadlinkException):
    """Authorization error."""


class CommandNotSupportedError(BroadlinkException):
    """Command not supported."""


_BROADLINK_ERRORS = {
    -1: ("Authentication failed", AuthenticationError),
    -2: ("You have been logged out", BroadlinkException),
    -3: ("The device is offline", BroadlinkException),
    -4: ("Command not supported", CommandNotSupportedError),
    -5: ("The device storage is full", BroadlinkException),
    -6: ("Structure is abnormal", BroadlinkException),
    -7: ("Control key is expired", AuthorizationError),
    -8: ("Send error", BroadlinkException),
    -9: ("Write error", BroadlinkException),
    -10: ("Read error", BroadlinkException),
    -11: ("SSID could not be found in AP configuration", BroadlinkException),
    -2040: ("Device information is not intact", DataValidationError),
    -4000: ("Network timeout", NetworkTimeoutError),
    -4007: ("Received data packet length error", DataValidationError),
    -4008: ("Received data packet check error", DataValidationError),
}


def _check_error(error: bytes) -> None:
    """Raise exception if error code is non-zero."""
    code = struct.unpack("h", error)[0]
    if code:
        msg, exc_cls = _BROADLINK_ERRORS.get(code, ("Unknown error", BroadlinkException))
        raise exc_cls(code, msg)


# ═══════════════ pyaes CBC wrapper ═══════════════
class _PyaesCBC:
    def __init__(self, key: bytes, iv: bytes):
        self._key = key
        self._iv = iv

    def encryptor(self):
        return _PyaesCBCContext(self._key, self._iv, encrypt=True)

    def decryptor(self):
        return _PyaesCBCContext(self._key, self._iv, encrypt=False)


class _PyaesCBCContext:
    def __init__(self, key: bytes, iv: bytes, encrypt: bool):
        self._aes = AESModeOfOperationCBC(key, iv=iv)
        self._encrypt = encrypt
        self._buf = b''

    def update(self, data: bytes) -> bytes:
        self._buf += data
        result = b''
        while len(self._buf) >= 16:
            block = self._buf[:16]
            self._buf = self._buf[16:]
            if self._encrypt:
                result += self._aes.encrypt(block)
            else:
                result += self._aes.decrypt(block)
        return result

    def finalize(self) -> bytes:
        if self._encrypt:
            if len(self._buf) == 0:
                return b''
            pad = 16 - (len(self._buf) % 16)
            self._buf += bytes([pad]) * pad
            result = b''
            for i in range(0, len(self._buf), 16):
                result += self._aes.encrypt(self._buf[i:i + 16])
            return result
        else:
            result = b''
            for i in range(0, len(self._buf), 16):
                result += self._aes.decrypt(self._buf[i:i + 16])
            if result:
                pad = result[-1]
                if 1 <= pad <= 16:
                    result = result[:-pad]
            return result


# ═══════════════ UDP scan ═══════════════
_HelloResponse = Tuple[int, Tuple[str, int], bytes, str, bool]


def _scan(
    timeout: int = DEFAULT_TIMEOUT,
    local_ip_address: Optional[str] = None,
    discover_ip_address: str = DEFAULT_BCAST_ADDR,
    discover_ip_port: int = DEFAULT_PORT,
):
    """UDP broadcast scan, yields (devtype, host, mac, name, is_locked)."""
    conn = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    conn.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    conn.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    if local_ip_address:
        conn.bind((local_ip_address, 0))
        port = conn.getsockname()[1]
    else:
        local_ip_address = "0.0.0.0"
        port = 0

    packet = bytearray(0x30)
    packet[0x08:0x14] = _pack_datetime(_now())
    packet[0x18:0x1C] = socket.inet_aton(local_ip_address)[::-1]
    packet[0x1C:0x1E] = port.to_bytes(2, "little")
    packet[0x26] = 6
    checksum = sum(packet, 0xBEAF) & 0xFFFF
    packet[0x20:0x22] = checksum.to_bytes(2, "little")

    start_time = time.time()
    discovered = []
    try:
        while (time.time() - start_time) < timeout:
            time_left = timeout - (time.time() - start_time)
            conn.settimeout(min(DEFAULT_RETRY_INTVL, time_left))
            conn.sendto(packet, (discover_ip_address, discover_ip_port))
            while True:
                try:
                    resp, host = conn.recvfrom(1024)
                except socket.timeout:
                    break
                devtype = resp[0x34] | resp[0x35] << 8
                mac = resp[0x3A:0x40][::-1]
                if (host, mac, devtype) in discovered:
                    continue
                discovered.append((host, mac, devtype))
                name = resp[0x40:].split(b"\x00")[0].decode()
                is_locked = bool(resp[0x7F])
                yield devtype, host, mac, name, is_locked
    finally:
        conn.close()


# ═══════════════ Device base class ═══════════════
class Device:
    """Broadlink RM device — handles auth and encrypted communication."""

    __INIT_KEY = "097628343fe99e23765c1513accf8b02"
    __INIT_VECT = "562e17996d093d28ddb3ba695a2e6f58"

    def __init__(
        self,
        host: Tuple[str, int],
        mac: Union[bytes, str],
        devtype: int,
        timeout: int = DEFAULT_TIMEOUT,
        name: str = "",
        model: str = "",
        is_locked: bool = False,
    ):
        self.host = host
        self.mac = bytes.fromhex(mac) if isinstance(mac, str) else mac
        self.devtype = devtype
        self.timeout = timeout
        self.name = name
        self.model = model
        self.is_locked = is_locked
        self._is_old_firmware = devtype in _OLD_FMT_TYPES  # old rmmini/rmpro use different packet format
        self.count = random.randint(0x8000, 0xFFFF)
        self.iv = bytes.fromhex(self.__INIT_VECT)
        self.id = 0
        self.lock = threading.Lock()
        self._update_aes(bytes.fromhex(self.__INIT_KEY))

    def __repr__(self):
        return "Device(%s, mac=%s, devtype=%s)" % (self.host, self.mac.hex(), hex(self.devtype))

    def __str__(self):
        return "%s (%s:%s / %s)" % (
            self.name or "Unknown",
            self.host[0], self.host[1],
            ":".join(format(x, "02X") for x in self.mac),
        )

    def _update_aes(self, key: bytes):
        self.aes = _PyaesCBC(bytes(key), self.iv)

    def _encrypt(self, payload: bytes) -> bytes:
        enc = self.aes.encryptor()
        return enc.update(bytes(payload)) + enc.finalize()

    def _decrypt(self, payload: bytes) -> bytes:
        dec = self.aes.decryptor()
        return dec.update(bytes(payload)) + dec.finalize()

    def auth(self) -> bool:
        """Authenticate with the device (AES handshake)."""
        self.id = 0
        self._update_aes(bytes.fromhex(self.__INIT_KEY))

        packet = bytearray(0x50)
        packet[0x04:0x14] = [0x31] * 16
        packet[0x1E] = 0x01
        packet[0x2D] = 0x01
        packet[0x30:0x36] = "Test 1".encode()

        response = self._send_packet(0x65, packet)
        _check_error(response[0x22:0x24])
        payload = self._decrypt(response[0x38:])

        self.id = int.from_bytes(payload[:0x4], "little")
        self._update_aes(payload[0x04:0x14])
        return True

    def _send_packet(self, packet_type: int, payload: bytes) -> bytes:
        """Send encrypted packet to device, return response."""
        self.count = ((self.count + 1) | 0x8000) & 0xFFFF
        packet = bytearray(0x38)
        packet[0x00:0x08] = bytes.fromhex("5aa5aa555aa5aa55")
        packet[0x24:0x26] = self.devtype.to_bytes(2, "little")
        packet[0x26:0x28] = packet_type.to_bytes(2, "little")
        packet[0x28:0x2A] = self.count.to_bytes(2, "little")
        packet[0x2A:0x30] = self.mac[::-1]
        packet[0x30:0x34] = self.id.to_bytes(4, "little")

        p_checksum = sum(payload, 0xBEAF) & 0xFFFF
        packet[0x34:0x36] = p_checksum.to_bytes(2, "little")

        padding = (16 - len(payload)) % 16
        payload = self._encrypt(payload + bytes(padding))
        packet.extend(payload)

        checksum = sum(packet, 0xBEAF) & 0xFFFF
        packet[0x20:0x22] = checksum.to_bytes(2, "little")

        with self.lock and socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as conn:
            timeout = self.timeout
            start_time = time.time()
            while True:
                time_left = timeout - (time.time() - start_time)
                conn.settimeout(min(DEFAULT_RETRY_INTVL, time_left))
                conn.sendto(packet, self.host)
                try:
                    resp = conn.recvfrom(2048)[0]
                    break
                except socket.timeout as err:
                    if (time.time() - start_time) > timeout:
                        raise NetworkTimeoutError(
                            -4000, "Network timeout",
                            "No response received within %ss" % timeout,
                        ) from err

        if len(resp) < 0x30:
            raise DataValidationError(
                -4007, "Received data packet length error",
                "Expected >=48 bytes, got %d" % len(resp),
            )

        nom_checksum = int.from_bytes(resp[0x20:0x22], "little")
        real_checksum = sum(resp, 0xBEAF) - sum(resp[0x20:0x22]) & 0xFFFF
        if nom_checksum != real_checksum:
            raise DataValidationError(
                -4008, "Received data packet check error",
                "Expected %04X, got %04X" % (nom_checksum, real_checksum),
            )

        return resp

    def _rm_send(self, command: int, data: bytes = b"") -> bytes:
        """Send RM command. Auto-detects old vs new firmware packet format."""
        if self._is_old_firmware:
            # Old format (rmmini, rmpro): struct.pack("<I", command) + data
            packet = struct.pack("<I", command) + data
            resp = self._send_packet(0x6A, packet)
            _check_error(resp[0x22:0x24])
            payload = self._decrypt(resp[0x38:])
            return payload[0x4:]
        else:
            # New format (rmminib, rm4mini, rm4pro): struct.pack("<HI", len+4, command) + data
            packet = struct.pack("<HI", len(data) + 4, command) + data
            resp = self._send_packet(0x6A, packet)
            _check_error(resp[0x22:0x24])
            payload = self._decrypt(resp[0x38:])
            p_len = struct.unpack("<H", payload[:0x2])[0]
            return payload[0x6:p_len + 2]

    def send_data(self, data: bytes) -> None:
        """Send IR code data to the device."""
        self._rm_send(0x2, data)


# ═══════════════ pulse conversion ═══════════════
def pulses_to_data(pulses: List[int], tick: float = 32.84) -> bytes:
    """Convert microsecond pulse durations to Broadlink IR packet bytes."""
    result = bytearray(4)
    result[0x00] = 0x26
    for pulse in pulses:
        div, mod = divmod(int(pulse // tick), 256)
        if div:
            result.append(0)
            result.append(div)
        result.append(mod)
    data_len = len(result) - 4
    result[0x02] = data_len & 0xFF
    result[0x03] = data_len >> 8
    return result


# ═══════════════ Public API ═══════════════
# Old firmware format (rmmini + rmpro): struct.pack("<I", command)
_OLD_FMT_TYPES = {
    0x2712, 0x272A, 0x2737, 0x273D, 0x277C, 0x2783, 0x2787, 0x278B,
    0x278F, 0x2797, 0x279D, 0x27A1, 0x27A6, 0x27A9, 0x27B7, 0x27C2,
    0x27C3, 0x27C7, 0x27CC, 0x27CD, 0x27D0, 0x27D1, 0x27D3, 0x27DC,
    0x27DE,
}
# New firmware format (rmminib + rm4mini + rm4pro): struct.pack("<HI", len+4, command)
_NEW_FMT_TYPES = {
    0x51DA, 0x5209, 0x520B, 0x520C, 0x520D, 0x5211, 0x5212,
    0x5213, 0x5216, 0x5218, 0x521C, 0x5F36, 0x6026, 0x6070, 0x610E,
    0x610F, 0x6184, 0x61A2, 0x62BC, 0x62BE, 0x6364, 0x648D, 0x649B,
    0x6507, 0x6508, 0x6539, 0x653A, 0x653C,
}

_RM_MODELS = {
    0x2737: "RM mini 3", 0x278F: "RM mini", 0x27B7: "RM mini 3",
    0x27C2: "RM mini 3", 0x27C7: "RM mini 3", 0x27CC: "RM mini 3",
    0x27CD: "RM mini 3", 0x27D0: "RM mini 3", 0x27D1: "RM mini 3",
    0x27D3: "RM mini 3", 0x27DC: "RM mini 3", 0x27DE: "RM mini 3",
    0x2712: "RM pro", 0x272A: "RM pro", 0x273D: "RM pro",
    0x277C: "RM home", 0x2783: "RM home", 0x2787: "RM pro",
    0x278B: "RM plus", 0x2797: "RM pro+", 0x279D: "RM pro+",
    0x27A1: "RM plus", 0x27A6: "RM plus", 0x27A9: "RM pro+",
    0x27C3: "RM pro+", 0x5F36: "RM mini 3", 0x6507: "RM mini 3",
    0x6508: "RM mini 3", 0x51DA: "RM4 mini", 0x5209: "RM4 TV mate",
    0x520C: "RM4 mini", 0x520D: "RM4C mini", 0x5211: "RM4C mate",
    0x5212: "RM4 TV mate", 0x5216: "RM4 mini", 0x521C: "RM4 mini",
    0x6070: "RM4C mini", 0x610E: "RM4 mini", 0x610F: "RM4C mini",
    0x62BC: "RM4 mini", 0x62BE: "RM4C mini", 0x6364: "RM4S",
    0x648D: "RM4 mini", 0x6539: "RM4C mini", 0x653A: "RM4 mini",
    0x520B: "RM4 pro", 0x5213: "RM4 pro", 0x5218: "RM4C pro",
    0x6026: "RM4 pro", 0x6184: "RM4C pro", 0x61A2: "RM4 pro",
    0x649B: "RM4 pro", 0x653C: "RM4 pro",
}


def discover(
    timeout: int = DEFAULT_TIMEOUT,
    local_ip_address: Optional[str] = None,
    discover_ip_address: str = DEFAULT_BCAST_ADDR,
    discover_ip_port: int = DEFAULT_PORT,
) -> List[Device]:
    """Discover Broadlink RM devices on the local network."""
    results = []
    for devtype, host, mac, name, is_locked in _scan(
        timeout, local_ip_address, discover_ip_address, discover_ip_port,
    ):
        if devtype not in _OLD_FMT_TYPES and devtype not in _NEW_FMT_TYPES:
            continue  # skip non-RM devices (sockets, sensors, etc.)
        model = _RM_MODELS.get(devtype, "RM device")
        dev = Device(
            host, mac, devtype, timeout=timeout,
            name=name or model, model=model, is_locked=is_locked,
        )
        dev._is_old_firmware = devtype in _OLD_FMT_TYPES
        results.append(dev)
    return results


def hello(
    ip_address: str,
    port: int = DEFAULT_PORT,
    timeout: int = DEFAULT_TIMEOUT,
) -> Device:
    """Direct connect to a known Broadlink RM device by IP."""
    try:
        return next(iter(discover(
            timeout=timeout,
            discover_ip_address=ip_address,
            discover_ip_port=port,
        )))
    except StopIteration:
        raise NetworkTimeoutError(
            -4000, "Network timeout",
            "No response from %s:%d within %ds" % (ip_address, port, timeout),
        )
