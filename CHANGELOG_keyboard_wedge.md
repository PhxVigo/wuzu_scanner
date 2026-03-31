# Keyboard Wedge UHF Scanner - Change Log

All changes made to add keyboard wedge UHF RFID scanner support.
Use this to manually revert if needed.

---

## config.toml

**Added line** (after `# UHF Reader settings`):
```toml
uhf_type = "serial"         # "serial" for UR-2000, "keyboard" for USB keyboard wedge scanner
```

To revert: delete that line. The app defaults to `"serial"` if the key is missing.

---

## wuzu_scanner.py

### 1. New class: `KeyboardWedgeBuffer` (inserted after `UHFReader`, before `DATABASE MANAGER` section)

Timing-based keystroke buffer that separates rapid scanner input from human typing.
- Buffers characters arriving < 100ms apart
- Enter + buffer >= 8 chars = scanner tag ID
- Shorter/slower input flushed back as normal keypresses
- Pending tags capped at 1, auto-discarded if not consumed

**To revert:** Delete the entire `KeyboardWedgeBuffer` class (from `class KeyboardWedgeBuffer:` through the `get_tags` method).

### 2. New class: `KeyboardWedgeUHF` (immediately after `KeyboardWedgeBuffer`)

Drop-in replacement for `UHFReader` when using a keyboard wedge scanner.
- `inventory()` returns tags from the wedge buffer
- `beep()` uses `winsound.Beep()` (Windows) or BEL char (Linux)
- `set_power()`, `get_reader_info()` are no-ops
- `self.ser = None` for compatibility

**To revert:** Delete the entire `KeyboardWedgeUHF` class.

### 3. Modified: `WuzuApp.__init__()` - reader selection

**Was:**
```python
self.nfc = NFCReader()
self.uhf = UHFReader(
    port=config.get('hardware', {}).get('uhf_port'),
    baud=config.get('hardware', {}).get('uhf_baudrate', 57600),
)
```

**Changed to:**
```python
self.nfc = NFCReader()
uhf_type = config.get('hardware', {}).get('uhf_type', 'serial')
if uhf_type == 'keyboard':
    self.uhf = KeyboardWedgeUHF()
else:
    self.uhf = UHFReader(
        port=config.get('hardware', {}).get('uhf_port'),
        baud=config.get('hardware', {}).get('uhf_baudrate', 57600),
    )
```

**To revert:** Replace the if/else block back to the original `self.uhf = UHFReader(...)` call.

### 4. Modified: `WuzuApp.beep()` - removed serial guard

**Was:**
```python
if self.uhf.ser:
    active, silent, times = beep_cfg
    self.uhf.beep(active, silent, times)
```

**Changed to:**
```python
active, silent, times = beep_cfg
self.uhf.beep(active, silent, times)
```

**To revert:** Add back the `if self.uhf.ser:` guard and indent the two lines beneath it.

### 5. Modified: `WuzuApp.run()` - main loop keystroke drain

**Was:**
```python
def run(self):
    print("Starting application...")
    time.sleep(2)
    self.terminal.clear()

    try:
        while True:
            time.sleep(self.config.get('timing', {}).get('nfc_poll_interval', 0.05))
            key = read_key()
            uid = self.nfc.poll_for_card()
            self.screen.handle(key, uid)
```

**Changed to:**
```python
def run(self):
    print("Starting application...")
    time.sleep(2)
    self.terminal.clear()
    is_wedge = isinstance(self.uhf, KeyboardWedgeUHF)

    try:
        while True:
            time.sleep(self.config.get('timing', {}).get('nfc_poll_interval', 0.05))

            if is_wedge:
                # Drain all available keystrokes through the wedge buffer
                user_key = None
                while True:
                    raw = read_key()
                    if raw is None:
                        # Check for timeout flush of buffered chars
                        flushed = self.uhf.wedge_buffer.process_key(None)
                        if flushed and user_key is None:
                            user_key = flushed
                        break
                    result = self.uhf.wedge_buffer.process_key(raw)
                    if result is not None and user_key is None:
                        user_key = result
                key = user_key
            else:
                key = read_key()

            uid = self.nfc.poll_for_card()
            self.screen.handle(key, uid)
```

**To revert:** Remove the `is_wedge` variable, the entire `if is_wedge:` block, and restore `key = read_key()`.

---

## detect_scanners.py

### 1. New function: `_read_char_nonblocking()`

Cross-platform non-blocking single-character read. Used by `prompt_scan()`.

**To revert:** Delete the function.

### 2. New function: `prompt_scan(label, timeout=15)`

Prompts "scan now or Escape to skip", captures keyboard input with timeout, returns the captured string.

**To revert:** Delete the function.

### 3. New function: `detect_keyboard_wedge()`

Calls `prompt_scan()` for keyboard wedge testing, prints captured ID and length.

**To revert:** Delete the function.

### 4. Modified: `read_current_config()`

**Added:** reads `uhf_type` from config alongside existing `uhf_port` and `uhf_baudrate`.

**To revert:** Remove the `uhf_type` key from the `values` dict and delete the regex block that reads it.

### 5. Modified: `update_config()`

**Added:** `uhf_type` parameter. If the key exists in the file, updates it; if missing, inserts it before `uhf_port`.

**To revert:** Remove the `uhf_type` parameter and its entire `if uhf_type is not None:` block.

### 6. Modified: `main()`

Complete rewrite of the detection flow:
- Serial UHF detection + scan verification prompt
- Keyboard wedge detection prompt
- NFC detection (unchanged)
- Summary showing both UHF types
- Config update offering choice between serial/keyboard if both found

**To revert:** Restore the original `main()` which only did `detect_uhf()`, `detect_nfc()`, summary, and a simple config update prompt. The original is preserved in git history.

---

## Quick full revert

If everything is committed, the fastest revert is:
```bash
git diff HEAD -- config.toml wuzu_scanner.py detect_scanners.py > wedge_changes.patch
git checkout HEAD -- config.toml wuzu_scanner.py detect_scanners.py
```

Or if committed:
```bash
git revert <commit-hash>
```
