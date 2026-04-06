# Yanzeo SR3308 — RCP Protocol Reference

Byte-level reference for the Yanzeo SR3308 (and related ADReader SDK devices:
SR3410, SR79X) protocol, known internally as "Pdr2 Reader Control Protocol"
or "RCP".

This was recovered by **statically decompiling** `ADRcp.dll`, `ADSio.dll`,
`ADDevice.dll`, and `RFIDDemo.exe` from the vendor SDK. The vendor DLLs are
**not** loaded at runtime — they were only read for interop documentation.

---

## Connection: USB HID (primary)

The SR3308 (VID=`04D8`, PID=`033F`) connects via **USB HID**, not serial.
The RCP protocol runs inside HID reports using length-prefixed framing:

**TX (host → reader):**
```
Byte 0:     0x00          (HID report ID)
Byte 1:     length        (number of RCP frame bytes that follow)
Byte 2..:   RCP frame     (see Frame Format below)
Remaining:  0x00 padding  (pad to 64 bytes total)
```

**RX (reader → host):**
```
Byte 0:     length        (number of valid bytes that follow)
Byte 1..:   RCP frame(s)  (valid data — parse only this many bytes)
Remaining:  stale buffer  (IGNORE — leftover from previous reports)
```

> **Important:** Only parse `length` bytes from RX reports. The trailing bytes
> are stale device buffer contents, not valid RCP data.

### Serial fallback

If connected via physical RS-232 (not USB), the serial settings are:
- Baud: **57600** (default; the reader also supports 9600/19200/38400/115200)
- 8 data bits, no parity, 1 stop bit (8N1)
- Flow control: none
- RCP frames are sent/received directly (no HID length-prefix wrapping)

---

## Frame format

Every TX and RX frame follows the same fixed layout. Total frame length is
`7 + payload_len` bytes.

```
Offset:  0    1    2    3    4    5    6 .. 6+N-1   6+N
Field:   PRE  ADRL ADRH CODE TYPE LEN  PAYLOAD(N)   CHK
```

| Field | Width | Description |
|-------|-------|-------------|
| `PRE` | 1 B | Preamble. **`0x7C`** on commands the host sends; **`0xCC`** on responses from the reader. |
| `ADR` | 2 B, little-endian | Reader address. Host uses `0xFFFF` (broadcast). Reader echoes its own address in responses. |
| `CODE` | 1 B | Command opcode (see tables below). |
| `TYPE` | 1 B | Message type (CMD/SET/GET for host, OK/ERR/DATA/AUTO for reader). |
| `LEN` | 1 B | Payload length in bytes. Max 255. |
| `PAYLOAD` | LEN bytes | Command- or response-specific data. |
| `CHK` | 1 B | Checksum — two's-complement negation of the byte sum of every preceding byte in the frame: `chk = (-sum(frame_without_chk)) & 0xFF` |

**Checksum in Python:**
```python
def checksum(frame_without_chk: bytes) -> int:
    return (-sum(frame_without_chk)) & 0xFF
```

Verification: `(sum(full_frame) & 0xFF) == 0`.

---

## Message type (TYPE field)

**Host → Reader (commands):**
| Hex | Name | Meaning |
|-----|------|---------|
| `0x00` | `RCP_MSG_CMD` | Execute command |
| `0x31` | `RCP_MSG_SET` | Set a parameter |
| `0x32` | `RCP_MSG_GET` | Get a parameter |
| `0x21` | `RCP_MSG_SENIOR_SET` | Advanced set |
| `0x22` | `RCP_MSG_SENIOR_GET` | Advanced get |

**Reader → Host (responses):** mask the TYPE byte with `& 0x7F` to get the response code:
| Hex (masked) | Name | Meaning |
|-----|------|---------|
| `0x00` | `RCP_MSG_OK` | Success (no data) |
| `0x01` | `RCP_MSG_ERR` | Failure |
| `0x02` | `RCP_MSG_NOTI` / data | Response carrying result data |
| `0x05` | `RCP_MSG_AUTO` | Unsolicited auto-push (reader pushed without being asked) |

---

## Command opcodes (CODE field)

Full list pulled from `RcpBase` constants in the decompiled `ADRcp.dll`. The
ones we actually use for wuzu-scanner are **bolded**.

### Inventory & tag access (Gen2 Class-C)
| Hex | Name | Purpose |
|-----|------|---------|
| **`0x20`** | **`RCP_CMD_READ_C_UII`** | **Inventory — read tag EPCs** |
| `0x21` | `RCP_CMD_READ_C_DT` | Read tag memory bank |
| `0x22` | `RCP_CMD_WRITE_C_DT` | Write tag memory bank |
| `0x26` | `RCP_CMD_LOCK_C` | Lock tag |
| `0x28` | `RCP_CMD_KILL_RECOM_C` | Kill tag |
| `0x2A` | `RCP_CMD_SECRET_C_DT` | Encrypted data access |
| `0x2C` | `RCP_CMD_GET_ACCESS_EPC_MATCH` | Get EPC selection filter |
| `0x2D` | `RCP_CMD_SET_ACCESS_EPC_MATCH` | Set EPC selection filter |

### RF / radio config
| Hex | Name | Purpose |
|-----|------|---------|
| `0x50` | `RCP_CMD_GET_TX_PWR` | Get TX power (dBm) |
| **`0x51`** | **`RCP_CMD_SET_TX_PWR`** | **Set TX power (dBm)** |
| `0x52` | `RCP_CMD_GET_REGION` | Get region (US/EU/CN/…) |
| `0x53` | `RCP_CMD_SET_REGION` | Set region |
| `0x54` | `RCP_CMD_GET_CH` | Get channel |
| `0x55` | `RCP_CMD_SET_CH` | Set channel |
| `0x56` | `RCP_CMD_GET_HOPPING_TBL` | Get hopping table |
| `0x57` | `RCP_CMD_SET_HOPPING_TBL` | Set hopping table |
| `0x58` | `RCP_CMD_GET_MODULATION` | Get modulation |
| `0x59` | `RCP_CMD_SET_MODULATION` | Set modulation |

### Reader config / device info
| Hex | Name | Purpose |
|-----|------|---------|
| **`0x81`** | **`RCP_CMD_PARA`** | **Base params (output mode, work mode)** |
| **`0x82`** | **`RCP_CMD_INFO`** | **Device info (ASCII string, ≥34 B)** |
| `0x83` | `RCP_CMD_ANT` | Antenna config |
| `0x84` | `RCP_CMD_EPT` | Tag encryption method |
| `0x85` | `RCP_CMD_ADDR` | Protocol address |
| `0x86` | `RCP_CMD_UART` | UART baud rate |
| `0x87` | `RCP_CMD_OUTCARD` | Output mode |
| `0xBC` | **`RCP_CMD_SOUND`** | **Beeper** |
| **`0xBD`** | **`RCP_CMD_USB`** | **USB enumeration mode (HID/KBD/CDC)** |
| `0xD0` | `RCP_CMD_RESET` | Reset system |
| `0xD2` | `RCP_CMD_UPDATE_FLASH` | Update registry |
| `0xD6` | `RCP_CMD_GET_GPIO` | Get GPIO mode |
| `0xD7` | `RCP_CMD_SET_GPIO` | Set GPIO mode |

### Auto-read control
| Hex | Name | Purpose |
|-----|------|---------|
| `0x32` | `RCP_CMD_STRT_AUTO_READ_EX` | Start auto-read |
| `0x33` | `RCP_CMD_STOP_AUTO_READ_EX` | Stop auto-read |
| `0x34` | `RCP_CMD_CTRL_AUTO_READ` | Pause/resume auto-read |

---

## Command payloads

### `RCP_CMD_INFO` (0x82) GET
- **TX payload:** empty (LEN=0)
- **RX payload:** ASCII string, ≥34 bytes, contains model/class/version. Example contains substring `"V2.1.5"` etc. Parse with `payload.decode('ascii', errors='replace')`.

### `RCP_CMD_PARA` (0x81) GET
- **TX payload:** empty
- **RX payload:** `[outputmode, workmode, …]` (27 bytes typical)
  - `outputmode`: controls physical data format (NOT USB enumeration):
    `0x01`=RS232, `0x02`=RS485, `0x03`=TCPIP, `0x04`=CANBUS, `0x05`=Syris, `0x06`=Wiegand26, `0x07`=Wiegand34
  - `workmode`: `0x00` = auto-read (reader pushes tags), `0x01` = command-read (host polls)

### `RCP_CMD_PARA` (0x81) SET
- **TX payload:** `[outputmode, workmode]`
- **For wuzu-scanner integration, send:** `[0x01, 0x01]` (RS232 format + command-polled mode)
- **RX payload:** empty, response TYPE `0x00` = OK

### `RCP_CMD_USB` (0xBD) GET — read USB enumeration mode
- **TX payload:** empty
- **RX payload:** `[mode, 0x00, 0x00]` (3 bytes)
  - `mode`: `0x00` = HID+KBD, `0x01` = HID+KBD+CDC, `0x02` = HID-only

### `RCP_CMD_USB` (0xBD) SET — change USB enumeration mode
- **TX payload:** `[mode]`
  - `0x00` = **HID+KBD** — command channel + keyboard (default from factory)
  - `0x01` = **HID+KBD+CDC** — command + keyboard + CDC serial port
  - `0x02` = **HID-only** — command channel only, NO keyboard (**use this**)
- **RX payload:** empty, TYPE `0x00` = OK
- **After SET:** device re-enumerates on USB (disconnects and reconnects). Persists in EEPROM.
- **For wuzu-scanner:** always set mode `0x02` to prevent the reader from injecting keystrokes.
  This is a hidden feature discovered by decompiling `ADDevice.dll` and `RFIDDemo.exe` — it is
  behind a "CDCMODE" config flag in the vendor app.

### `RCP_CMD_GET_TX_PWR` (0x50) GET
- **TX payload:** empty
- **RX payload:** `[power_dBm]` — single byte, 0..30 dBm

### `RCP_CMD_SET_TX_PWR` (0x51) SET
- **TX payload:** `[power_dBm]` — single byte, 0..30
- **RX payload:** empty, TYPE `0x00` = OK

### `RCP_CMD_READ_C_UII` (0x20) CMD — inventory
- **TX payload:** empty (single round of inventory)
- **RX:** zero or more tag frames (TYPE `0x02` data, one tag per frame) **followed by** a summary/terminator frame with TYPE `0x00` OK. Tag frame payload layout described below.

### `RCP_CMD_SOUND` (0xBC) CMD — beep
- **TX payload:** `[active_time, silent_time, times]` — each in units of 100 ms
  - e.g. `[0x02, 0x01, 0x02]` → beep 200ms, pause 100ms, repeat 2 times
- **RX payload:** empty, TYPE `0x00` = OK

### `RCP_CMD_RESET` (0xD0) CMD
- **TX payload:** empty
- **RX payload:** empty, TYPE `0x00` = OK (reader then reboots)

---

## Inventory tag-record format

When the reader responds to `RCP_CMD_READ_C_UII`, each detected tag is returned
as its **own** frame with `CODE=0x20`, `TYPE=0x02` (data), and a payload that
describes one tag. After all tag frames, the reader sends a terminating frame
with `TYPE=0x00` (OK). Parsing logic mirrors `RcpBase.ParsePacket` in the
decompiled source.

**Payload layout (the contents of one tag frame's PAYLOAD):**

```
If LEN is even: RSSI = payload[-1]; effective length = LEN - 1 (drop trailing RSSI)

byte 0:  bits 7..5 = tag-type nibble
         bits 4..0 = antenna id (0..31)
byte 1:  if == 0x00, skip 2 bytes (reserved, varies by firmware)
next 2:  PC bytes (EPC Gen2 Protocol-Control word)
next N:  EPC itself, where N = (PC[0] >> 3) * 2
trailing: optional CRC (mode 'I') or extra tag data — ignore for basic inventory
```

**Python parser:**
```python
def parse_tag_record(payload: bytes) -> dict:
    length = len(payload)
    rssi = None
    if length % 2 == 0:
        rssi = payload[-1]
        length -= 1
    p = payload[:length]
    i = 0
    antenna = p[i] & 0x1F
    tag_type = (p[i] & 0xE0) | 2
    i += 1
    if i < len(p) and p[i] == 0x00:
        i += 2  # skip reserved
    pc = p[i:i+2]
    epc_len = (pc[0] >> 3) * 2
    epc = p[i+2 : i+2+epc_len]
    return {
        "antenna": antenna,
        "tag_type": tag_type,
        "pc": pc.hex().upper(),
        "epc": epc.hex().upper(),
        "epc_bytes": bytes(epc),
        "epc_len": epc_len,
        "rssi": rssi,
    }
```

---

## RX reassembly

The reader may concatenate multiple frames in a single serial read, and pad
with idle bytes. Mirror the `RcpBase.ReciveBytePkt` algorithm:

1. Accumulate bytes into a rolling buffer.
2. Scan the buffer for the RX preamble `0xCC`.
3. When found, need at least 7 bytes available.
4. Read `LEN = buf[5]`; full frame is `7 + LEN` bytes.
5. If buffer doesn't yet hold that many bytes, wait for more.
6. Once full frame is in, validate checksum: `(sum(full_frame) & 0xFF) == 0`.
7. On success: hand the frame to the parser, remove it from the buffer, loop.
8. On bad checksum: drop the leading `0xCC` byte and re-scan (resync).

---

## Verified example hex traces

Every line below is a TX frame with a verified checksum:

```
INFO GET              (7B): 7C FF FF 82 32 00 D2
PARA GET              (7B): 7C FF FF 81 32 00 D3
PARA SET ser+cmd      (9B): 7C FF FF 81 31 02 01 01 D0
GET_TX_PWR GET        (7B): 7C FF FF 50 32 00 04
SET_TX_PWR SET 20dBm  (8B): 7C FF FF 51 31 01 14 EF
INVENTORY CMD         (7B): 7C FF FF 20 00 00 66
SOUND beep 200/100/2x (10B): 7C FF FF BC 00 03 02 01 02 C2
USB GET               (7B): 7C FF FF BD 32 00 97
USB SET HID-only      (8B): 7C FF FF BD 31 01 02 95
RESET CMD             (7B): 7C FF FF D0 00 00 B6
```

---

## Frame build/parse reference (Python)

```python
PREAMBLE_TX = 0x7C
PREAMBLE_RX = 0xCC
ADDR_BROADCAST = 0xFFFF

def build_frame(code: int, msg_type: int, payload: bytes = b"",
                addr: int = ADDR_BROADCAST) -> bytes:
    header = bytes([
        PREAMBLE_TX,
        addr & 0xFF, (addr >> 8) & 0xFF,
        code, msg_type, len(payload),
    ])
    body = header + payload
    chk = (-sum(body)) & 0xFF
    return body + bytes([chk])

def verify_checksum(frame: bytes) -> bool:
    return (sum(frame) & 0xFF) == 0

def parse_frame(frame: bytes) -> dict:
    if len(frame) < 7 or frame[0] != PREAMBLE_RX:
        raise ValueError("bad preamble")
    length = frame[5]
    if len(frame) != 7 + length:
        raise ValueError(f"length mismatch: got {len(frame)}, want {7+length}")
    if not verify_checksum(frame):
        raise ValueError("bad checksum")
    return {
        "preamble": frame[0],
        "addr": frame[1] | (frame[2] << 8),
        "code": frame[3],
        "type": frame[4],
        "type_masked": frame[4] & 0x7F,
        "len": length,
        "payload": bytes(frame[6:6+length]),
        "checksum": frame[6+length],
    }
```

---

## Re-decompile if needed

If you ever need to inspect the DLL source again:

```bash
# one-time setup (requires .NET SDK)
dotnet tool install -g ilspycmd

# decompile
ilspycmd "Yanzeo-SR3308-Series-VS-Demo-SDK/packages/ADReader.Rcp.1.0.2-beta4/lib/net48/ADRcp.dll" \
    -o decompiled/
```

Relevant classes in the output: `ProtocolPacket` (frame build/parse, checksum),
`RcpBase` (opcode constants, RX reassembly in `ReciveBytePkt`, tag record
parser `ParsePacket`), `TagInfo` (tag record data model).
