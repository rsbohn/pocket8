# pocket8

A pocket PDP-8: a PDP-8 emulator with a working front panel, built on an
Adafruit Feather ESP32-S2 TFT and a MAX3421E USB Host FeatherWing, running
CircuitPython.

The TFT is the panel: two four-digit seven-segment readouts — PC on top, the
word at PC (or the number being typed) below — plus a run light, green while
running, red when stopped. A USB keyboard works the panel.

> All in my head, right in my hand. Octal is a cherry on top.

## Hardware

- Feather ESP32-S2 TFT
- MAX3421E USB Host FeatherWing (USB keyboard in)
- USB-C power

DEC reached the same shape in 1974: the PDP-8/A replaced its toggle switches
with an octal keypad and a 7-segment LED display. This one shows PC and data
at the same time.

## Files

- `pocket8.py` — the board program: panel display, keyboard, machine control
- `p8cpu.py` — the PDP-8 CPU core, pure Python, runs anywhere
- `p8run.py` — runner with a teletype console (desktop CPython or the board)
- `p8tape.py` — paper-tape devices, including a TNFS tape library
- `bin2rom.py`, `make_roms.py` — ROM image tools
- `test_p8cpu.py` — CPU test suite, 14 test groups
- ROM images: `focal69.rom`, `focal69-fastreader.rom`, `hello.rom`, `irqecho.rom`

## Front panel keys

| key | action |
| --- | ------ |
| `0`–`7` | enter an octal digit (four kept; a fifth pushes the oldest out) |
| `Enter` | load PC from the entered number |
| `[` / `]` | step PC back / forward |
| `D` | deposit the entered number at PC, then advance PC |
| `E` | examine: print the word at PC to the serial console |
| `Space` | run / stop, starting from the current PC |
| `,` | load `/sys.rom` into memory |
| `S` | save 128 words starting at PC to `/sys.rom` |

`S` fails while the board is plugged into a computer — the filesystem is
read-only to the program then. No single-step, no AC/link display, no switch
register. One key at a time; modifier keys are ignored.

Anything typed at the serial console while a program runs goes to the
PDP-8's teletype; paper-tape devices and FOCAL loading live in `p8run`.

## Try it on a desktop

```sh
python3 test_p8cpu.py
python3 -c "import p8run; p8run.run('focal69.rom')"
```

The tests cover the CPU core including a real FOCAL-69 session. The runner
gives you FOCAL at the teletype prompt: try `TYPE 2+2`.

## Status

First programs ran on the hardware on 2026-11-14, both toggled in from the
panel: a single HLT (7402), then a five-pass ISZ loop that halts with 0005 on
the display — it counted its own passes.

## License

MIT — see `LICENSE`.
