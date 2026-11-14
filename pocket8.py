# SPDX-FileCopyrightText: 2024
# SPDX-License-Identifier: MIT

# PDP-8 Pocket Computer

import board
import time
import displayio
import vectorio
from adafruit_display_text import label
from adafruit_bitmap_font import bitmap_font
import max3421e
import usb.core
import neopixel
import p8cpu
import p8run
import sys

# Display setup
display = board.DISPLAY
font = bitmap_font.load_font("/fonts/SevenSeg-12.bdf")
splash = displayio.Group()

AMBER = 0xFFBF00

pc_label = label.Label(font, text="0000", color=AMBER, scale=2, x=50, y=35)
data_label = label.Label(font, text="0000", color=AMBER, scale=2, x=50, y=100)

# Status LED indicator (vectorio circle)
status_palette = displayio.Palette(2)
status_palette[0] = 0xFF0000  # Red (halted)
status_palette[1] = 0x00FF00  # Green (running)
status_led = vectorio.Circle(pixel_shader=status_palette, radius=5, x=220, y=10, color_index=0)

splash.append(status_led)
splash.append(pc_label)
splash.append(data_label)
display.root_group = splash

# NeoPixel setup
pixel = neopixel.NeoPixel(board.NEOPIXEL, 1, brightness=0.3)
pixel[0] = (0, 0, 0)

# USB Host setup
spi = board.SPI()
host_chip = max3421e.Max3421E(spi, chip_select=board.D10, irq=board.D9)

# Keyboard scancodes
OCTAL_KEYS = {0x27: 0, 0x1E: 1, 0x1F: 2, 0x20: 3, 0x21: 4, 0x22: 5, 0x23: 6, 0x24: 7}
KEY_ENTER, KEY_SPACE, KEY_D, KEY_E = 0x28, 0x2C, 0x07, 0x08
KEY_LBRACKET, KEY_RBRACKET = 0x2F, 0x30
KEY_COMMA, KEY_S = 0x36, 0x16  # Load and Save ROM

# PDP-8 state
memory = [0] * 4096
pc = ac = link = 0
running = halted = False
input_digits = []  # Use list to avoid string concatenation memory leaks
neo_r = neo_g = neo_b = 0
neo_user_control = False

def update_status_led():
    """Update status LED color: green when running, red when halted."""
    status_led.color_index = 1 if running else 0

def load_rom(filename, start_addr):
    """Load ROM file into memory starting at start_addr."""
    try:
        with open(filename, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or ':' not in line:
                    continue
                addr_str, data_str = line.split(':', 1)
                addr = int(addr_str.strip(), 8)
                words = data_str.strip().split()
                for i, word in enumerate(words):
                    memory[addr + i] = int(word, 8) & 0o7777
        print(f"Loaded {filename}")
        return True
    except Exception as e:
        print(f"Load error: {e}")
        return False

def save_rom(filename, start_addr, num_words):
    """Save ROM file from memory starting at start_addr."""
    try:
        with open(filename, 'w') as f:
            for i in range(0, num_words, 8):
                addr = (start_addr + i) & 0o7777
                f.write(f"{addr:04o}:")
                for j in range(8):
                    if i + j < num_words:
                        word = memory[(start_addr + i + j) & 0o7777]
                        f.write(f" {word:04o}")
                    else:
                        f.write(" 0000")
                f.write('\n')
        print(f"Saved {filename} ({num_words:04o} words from {start_addr:04o})")
        return True
    except Exception as e:
        print(f"Save error: {e}")
        return False

# CPU state dictionary for p8cpu module
cpu_state = {
    'pc': 0, 'ac': 0, 'link': 0,
    'neo_r': 0, 'neo_g': 0, 'neo_b': 0,
    'neo_user_control': False,
    'mq': 0, 'sr': 0, 'ie': 0
}

# Console teletype (devices 03 and 04) on the USB serial console
tty = p8cpu.Teletype(sys.stdout.write)
read_key = p8run.console()
BATCH = 200  # instructions per pass of the main loop while running

# Find keyboard
print("\n=== Pocket PDP-8 ===")
time.sleep(1)

keyboard = None
try:
    devices = list(usb.core.find(find_all=True))
    print(f"Found {len(devices)} device(s)")
    
    for dev in devices:
        keyboard = dev
        print(f"Keyboard: {dev.manufacturer} {dev.product}")
        break
        
except Exception as e:
    print(f"USB error: {e}")

hid_buf = bytearray(8)

if keyboard:
    try:
        keyboard.set_configuration()
        print("Ready!")
    except Exception as e:
        print(f"Config error: {e}")
        keyboard = None
else:
    print("NO KEYBOARD!")

last_key = 0
update_status_led()

while True:
    # Update display
    pc_label.text = f"{pc:04o}"
    if input_digits:
        input_str = ''.join(str(d) for d in input_digits)
        data_label.text = f"{int(input_str, 8) & 0o7777:04o}"
    else:
        data_label.text = f"{memory[pc]:04o}"
    
    # Update status LED
    update_status_led()
    
    # Execute instructions
    if running and not halted:
        # A key typed at the serial console goes to the teletype keyboard
        if not tty.kbd_flag:
            ch = read_key()
            if ch:
                tty.key(ch)
        for _ in range(BATCH):
            if p8cpu.step(cpu_state, memory, pixel, tty):
                halted = True
                running = False
                cpu_state['neo_user_control'] = False
                update_status_led()
                print(f"\nHALTED at {cpu_state['pc']:04o}")
                break
        # Sync local vars
        pc = cpu_state['pc']
        ac = cpu_state['ac']
        link = cpu_state['link']
    
    # Read keyboard
    if keyboard:
        try:
            keyboard.read(0x81, hid_buf, timeout=10)
            key = hid_buf[2]
            
            if key != 0 and key != last_key:
                last_key = key
                
                if key in OCTAL_KEYS:
                    input_digits.append(OCTAL_KEYS[key])
                    if len(input_digits) > 4:
                        input_digits.pop(0)
                    
                elif key == KEY_ENTER:
                    if input_digits:
                        input_str = ''.join(str(d) for d in input_digits)
                        pc = int(input_str, 8) & 0o7777
                        cpu_state['pc'] = pc
                        print(f"PC = {pc:04o}")
                        input_digits.clear()
                        halted = False
                        
                elif key == KEY_LBRACKET:
                    pc = (pc - 1) & 0o7777
                    cpu_state['pc'] = pc
                    input_digits.clear()
                    
                elif key == KEY_RBRACKET:
                    pc = (pc + 1) & 0o7777
                    cpu_state['pc'] = pc
                    input_digits.clear()
                    
                elif key == KEY_D:
                    if input_digits:
                        input_str = ''.join(str(d) for d in input_digits)
                        v = int(input_str, 8) & 0o7777
                        memory[pc] = v
                        print(f"DEPOSIT [{pc:04o}] = {v:04o}")
                        pc = (pc + 1) & 0o7777
                        cpu_state['pc'] = pc
                        input_digits.clear()
                        
                elif key == KEY_E:
                    print(f"EXAMINE [{pc:04o}] = {memory[pc]:04o}")
                    input_digits.clear()
                    
                elif key == KEY_COMMA:
                    load_rom('/sys.rom', 0)
                    input_digits.clear()
                    
                elif key == KEY_S:
                    save_rom('/sys.rom', pc, 0o200)
                    input_digits.clear()
                    
                elif key == KEY_SPACE:
                    running = not running
                    if running:
                        halted = False
                        cpu_state['neo_user_control'] = False
                        # Sync to cpu_state before running
                        cpu_state['pc'] = pc
                        cpu_state['ac'] = ac
                        cpu_state['link'] = link
                        print(f"RUN from {pc:04o}")
                    else:
                        cpu_state['neo_user_control'] = False
                        print(f"STOPPED at {pc:04o}")
                    update_status_led()
                    
            elif key == 0 and last_key != 0:
                last_key = 0
                
        except usb.core.USBTimeoutError:
            pass
        except Exception as e:
            print(f"Error: {e}")
    
    if not running:
        time.sleep(0.01)
