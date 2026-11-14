# SPDX-FileCopyrightText: 2024
# SPDX-License-Identifier: MIT

# PDP-8 CPU Emulator

def calc_ea(inst, pc, memory):
    """Calculate effective address. `pc` is the address after the instruction."""
    addr = inst & 0o177
    if inst & 0o200:  # current page: the page the instruction itself is on
        addr |= (pc - 1) & 0o7600
    if inst & 0o400:  # indirect
        if 0o10 <= addr <= 0o17:  # auto-index: increment the pointer first
            memory[addr] = (memory[addr] + 1) & 0o7777
        addr = memory[addr] & 0o7777
    return addr

class Teletype:
    """Console teletype: keyboard on device 03, printer on device 04.

    `write` is called with each printed character. Call key() when a
    character arrives; it waits in the buffer until the program reads it.
    """

    def __init__(self, write, upper=True):
        self.write = write
        self.upper = upper  # an ASR-33 has no lower case, and DEC software expects none
        self.reset()

    def reset(self):
        self.kbd_flag = self.tty_flag = 0
        self.kbd_buf = 0

    def key(self, ch):
        c = ord(ch) & 0x7F
        if self.upper and 0x61 <= c <= 0x7A:
            c -= 0x20
        self.kbd_buf = c | 0o200  # 8-bit ASCII, top bit set, as the software expects
        self.kbd_flag = 1

    def keyboard(self, fn, ac):
        """KCF 6030, KSF 6031, KCC 6032, KRS 6034, KRB 6036. Returns (ac, skip)."""
        skip = bool(fn & 1 and self.kbd_flag)
        if fn == 0 or fn & 2:
            self.kbd_flag = 0
        if fn & 2:
            ac = 0
        if fn & 4:
            ac |= self.kbd_buf
        return ac, skip

    def printer(self, fn, ac):
        """SPF 6040, TSF 6041, TCF 6042, TPC 6044, TSK 6045, TLS 6046. Returns skip."""
        if fn == 0:
            self.tty_flag = 1
            return False
        if fn == 5:
            return bool(self.kbd_flag or self.tty_flag)
        skip = bool(fn & 1 and self.tty_flag)
        if fn & 2:
            self.tty_flag = 0
        if fn & 4:
            c = ac & 0x7F
            if c and c != 0x7F:  # nulls and rubouts are tape padding, not text
                self.write(chr(c))
            self.tty_flag = 1  # printing is instant, so the printer is ready again
        return skip


class PaperTape:
    """High-speed paper tape: reader on device 01, punch on device 02.

    `source()` returns the next byte of the tape in the reader, or None when
    the tape has run out. `sink(byte)` receives each byte punched.
    """

    def __init__(self, source=None, sink=None):
        self.source = source
        self.sink = sink
        self.rdr_buf = 0
        self.ran_out = False
        self.reset()

    def reset(self):
        self.rdr_flag = self.pun_flag = 0

    def reader(self, fn, ac):
        """RSF 6011, RRB 6012, RFC 6014 (and RRB RFC 6016). Returns (ac, skip)."""
        skip = bool(fn & 1 and self.rdr_flag)
        if fn & 2:
            ac |= self.rdr_buf
            self.rdr_flag = 0
        if fn & 4:  # fetch the next character; the flag rises when it is in
            self.rdr_flag = 0
            b = self.source() if self.source is not None else None
            if b is not None:
                self.rdr_buf = b & 0o377
                self.rdr_flag = 1
            else:
                self.ran_out = True  # for whoever is watching the reader
        return ac, skip

    def punch(self, fn, ac):
        """PSF 6021, PCF 6022, PPC 6024, PLS 6026. Returns skip."""
        skip = bool(fn & 1 and self.pun_flag)
        if fn & 2:
            self.pun_flag = 0
        if fn & 4:
            if self.sink is not None:
                self.sink(ac & 0o377)
            self.pun_flag = 1
        return skip


def step(cpu_state, memory, pixel=None, tty=None, tape=None):
    """Take a pending interrupt, then fetch and execute one instruction.

    cpu_state['ie'] is 0 with interrupts off, 1 for the one instruction after
    ION (so "ION; JMP I 0" can return first), and 2 with interrupts on.
    Returns True if halted.
    """
    ie = cpu_state.get('ie', 0)
    pc = cpu_state['pc']
    if ie == 2 and ((tty is not None and (tty.kbd_flag or tty.tty_flag)) or
                    (tape is not None and (tape.rdr_flag or tape.pun_flag))):
        memory[0] = pc
        pc = 1
        cpu_state['ie'] = ie = 0
    cpu_state['pc'] = (pc + 1) & 0o7777
    halted = execute(memory[pc], cpu_state, memory, pixel, tty, tape)
    if ie == 1 and cpu_state.get('ie') == 1:
        cpu_state['ie'] = 2
    return halted


def execute(inst, cpu_state, memory, pixel=None, tty=None, tape=None):
    """
    Execute a single PDP-8 instruction.

    Args:
        inst: 12-bit instruction
        cpu_state: dict with keys 'pc', 'ac', 'link', 'neo_r', 'neo_g', 'neo_b', 'neo_user_control'
            and optionally 'mq' (multiplier quotient) and 'sr' (switch register)
        memory: 4096-word memory array
        pixel: Optional NeoPixel object for IOT device 0o70
        tty: Optional Teletype for IOT devices 0o03 and 0o04; interrupts
            (device 0) use cpu_state['ie'], see step()
        tape: Optional PaperTape for IOT devices 0o01 and 0o02

    Returns:
        True if halted, False otherwise
    """
    pc = cpu_state['pc']
    ac = cpu_state['ac']
    link = cpu_state['link']

    op = (inst >> 9) & 0o7

    if op <= 0o5:
        addr = calc_ea(inst, pc, memory)
        if op == 0:  # AND
            ac &= memory[addr]
        elif op == 1:  # TAD: a carry out of bit 0 complements the link
            ac += memory[addr]
            if ac > 0o7777:
                ac &= 0o7777
                link ^= 1
        elif op == 2:  # ISZ
            memory[addr] = (memory[addr] + 1) & 0o7777
            if memory[addr] == 0:
                pc = (pc + 1) & 0o7777
        elif op == 3:  # DCA
            memory[addr], ac = ac, 0
        elif op == 4:  # JMS
            memory[addr], pc = pc, (addr + 1) & 0o7777
        elif op == 5:  # JMP
            pc = addr

    elif op == 0o6:  # IOT
        dev, fn = (inst >> 3) & 0o77, inst & 0o7
        if dev == 0:  # interrupt system
            if fn == 1:  # ION: on after the next instruction
                cpu_state['ie'] = cpu_state.get('ie', 0) or 1
            elif fn == 2:  # IOF
                cpu_state['ie'] = 0
            elif fn == 0:  # SKON: skip if on, and turn off
                if cpu_state.get('ie', 0):
                    pc = (pc + 1) & 0o7777
                cpu_state['ie'] = 0
            elif fn == 3:  # SRQ: skip if a device is requesting an interrupt
                if ((tty is not None and (tty.kbd_flag or tty.tty_flag)) or
                        (tape is not None and (tape.rdr_flag or tape.pun_flag))):
                    pc = (pc + 1) & 0o7777
            elif fn == 7:  # CAF: clear AC, link and all device flags
                ac = link = 0
                cpu_state['ie'] = 0
                if tty is not None:
                    tty.reset()
                if tape is not None:
                    tape.reset()
        elif dev == 0o01 and tape is not None:  # high-speed reader
            ac, skip = tape.reader(fn, ac)
            if skip:
                pc = (pc + 1) & 0o7777
        elif dev == 0o02 and tape is not None:  # high-speed punch
            if tape.punch(fn, ac):
                pc = (pc + 1) & 0o7777
        elif dev == 0o03 and tty is not None:  # keyboard
            ac, skip = tty.keyboard(fn, ac)
            if skip:
                pc = (pc + 1) & 0o7777
        elif dev == 0o04 and tty is not None:  # printer
            if tty.printer(fn, ac):
                pc = (pc + 1) & 0o7777
        elif dev == 0o70 and pixel:  # NeoPixel device
            cpu_state['neo_user_control'] = True
            if fn == 1:
                cpu_state['neo_r'] = ac & 0o377
            elif fn == 2:
                cpu_state['neo_g'] = ac & 0o377
            elif fn == 3:
                cpu_state['neo_b'] = ac & 0o377
            elif fn == 4:
                cpu_state['neo_r'] = cpu_state['neo_g'] = cpu_state['neo_b'] = 0
            pixel[0] = (cpu_state['neo_r'], cpu_state['neo_g'], cpu_state['neo_b'])

    elif (inst & 0o400) == 0:  # Group 1, in the order the hardware does it
        if inst & 0o200: ac = 0  # CLA
        if inst & 0o100: link = 0  # CLL
        if inst & 0o040: ac ^= 0o7777  # CMA
        if inst & 0o020: link ^= 1  # CML
        if inst & 0o001:  # IAC
            ac = (ac + 1) & 0o7777
            if ac == 0:
                link ^= 1
        if inst & 0o014:  # rotates go through the link, once or (0o002) twice
            v = (link << 12) | ac
            for _ in range(2 if inst & 0o002 else 1):
                if inst & 0o010:  # RAR / RTR
                    v = (v >> 1) | ((v & 1) << 12)
                if inst & 0o004:  # RAL / RTL
                    v = ((v << 1) | (v >> 12)) & 0o17777
            link, ac = v >> 12, v & 0o7777
        elif inst & 0o002:  # BSW: swap the two halves of AC
            ac = ((ac & 0o77) << 6) | (ac >> 6)

    elif (inst & 0o001) == 0:  # Group 2
        skip = False
        if inst & 0o100 and ac & 0o4000: skip = True  # SMA
        if inst & 0o040 and ac == 0: skip = True  # SZA
        if inst & 0o020 and link != 0: skip = True  # SNL
        if inst & 0o010: skip = not skip  # Reverse: SPA, SNA, SZL, or SKP alone
        if skip: pc = (pc + 1) & 0o7777
        if inst & 0o200: ac = 0  # CLA
        if inst & 0o004: ac |= cpu_state.get('sr', 0) & 0o7777  # OSR
        if inst & 0o002:  # HLT
            cpu_state['pc'] = pc
            cpu_state['ac'] = ac
            cpu_state['link'] = link
            return True

    else:  # Group 3: MQ register
        mq = cpu_state.get('mq', 0)
        if inst & 0o200: ac = 0  # CLA
        if (inst & 0o120) == 0o120:  # MQA MQL together: swap
            ac, mq = mq, ac
        elif inst & 0o100:  # MQA
            ac |= mq
        elif inst & 0o020:  # MQL
            mq, ac = ac, 0
        cpu_state['mq'] = mq

    cpu_state['pc'] = pc
    cpu_state['ac'] = ac
    cpu_state['link'] = link
    return False
