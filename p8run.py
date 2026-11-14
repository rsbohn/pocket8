# SPDX-License-Identifier: MIT
"""Run a PDP-8 program with the teletype on the serial console. No display or
USB keyboard needed. From the CircuitPython REPL:

    import p8run
    m = p8run.run("/focal69.rom")    # starts at 0200; Ctrl-C stops, m.run() continues
"""

import sys

import p8cpu


def load(filename, memory):
    """Load a .rom file: lines of "ADDR: WORD WORD ...", all octal."""
    with open(filename, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line[0] in "/#" or ":" not in line:
                continue
            addr_str, data_str = line.split(":", 1)
            addr = int(addr_str.strip(), 8)
            for i, word in enumerate(data_str.split()):
                memory[(addr + i) & 0o7777] = int(word, 8) & 0o7777


def new_state(start=0o200):
    return {"pc": start, "ac": 0, "link": 0, "mq": 0, "sr": 0, "ie": 0,
            "neo_r": 0, "neo_g": 0, "neo_b": 0, "neo_user_control": False}


def console():
    """Return a function that gives the next character typed at the serial
    console, or None if there is none waiting.

    sys.stdin turns Return (CR) into LF, and PDP-8 software needs the CR, so
    this reads the USB serial port directly where it can.
    """
    try:
        import usb_cdc
        port = usb_cdc.console
    except ImportError:
        port = None
    if port is not None:
        def get():
            if port.in_waiting:
                return chr(port.read(1)[0])
            return None
    else:
        import supervisor

        def get():
            if supervisor.runtime.serial_bytes_available:
                ch = sys.stdin.read(1)
                return "\r" if ch == "\n" else ch
            return None
    return get


class Machine:
    """A PDP-8 with a teletype on the serial console and paper tapes on TNFS.

        m = p8run.Machine("/focal69.rom")
        m.reader("grumpy:/squares.fc")     # put a tape in the reader
        m.run()                            # Ctrl-C comes back here, state kept
        m.capture("grumpy:/listing.txt")   # record what the teletype prints
        m.run()                            # carry on where it stopped
        m.capture(None)                    # stop recording and close the file
    """

    def __init__(self, rom=None, start=0o200, pool=None):
        self.memory = [0] * 4096
        if rom:
            load(rom, self.memory)
        self.state = new_state(start)
        self.eot_hold = 20000  # instructions to hold typed keys after a tape runs out
        self.tape = p8cpu.PaperTape()
        self.tty = p8cpu.Teletype(self._print)
        self._capture = None
        self._pool = pool
        self._library = None

    def load(self, filename):
        """Load another .rom file on top of memory, e.g. a patch."""
        load(filename, self.memory)

    def _print(self, ch):
        sys.stdout.write(ch)
        if self._capture is not None:
            self._capture.write(ch)

    def library(self):
        if self._library is None:
            import p8tape
            pool = self._pool
            if pool is None:
                import socketpool
                import wifi
                pool = socketpool.SocketPool(wifi.radio)
            self._library = p8tape.Library(pool)
        return self._library

    def reader(self, spec, text=None):
        """Put the tape "host:/path" in the high-speed reader; None takes it out."""
        if self.tape.source is not None:
            self.tape.source.close()
        self.tape.source = self.library().reader(spec, text) if spec else None

    def punch(self, spec, text=None):
        """Send the high-speed punch to "host:/path"; None closes the file."""
        if self.tape.sink is not None:
            self.tape.sink.close()
        self.tape.sink = self.library().punch(spec, text) if spec else None

    def capture(self, spec):
        """Record everything the teletype prints in "host:/path"; None stops."""
        if self._capture is not None:
            self._capture.close()
        self._capture = self.library().punch(spec, True) if spec else None

    def dir(self, spec):
        """List a directory, e.g. m.dir("grumpy:/")."""
        for name in self.library().listdir(spec):
            print(name)

    def flush(self):
        for out in (self.tape.sink, self._capture):
            if out is not None:
                out.flush()

    def close(self):
        """Close the tapes and leave the servers."""
        self.reader(None)
        self.punch(None)
        self.capture(None)
        if self._library is not None:
            self._library.close()
            self._library = None

    def run(self, batch=200):
        """Run until HLT or Ctrl-C. Call again to continue."""
        step, state, memory, tty, tape = p8cpu.step, self.state, self.memory, self.tty, self.tape
        read_key = console()
        hold = 0
        try:
            while True:
                if tape.ran_out:
                    # The program is still waiting on the empty reader, and a key
                    # typed now would be taken as an error. Keep keys back a moment.
                    tape.ran_out = False
                    hold = self.eot_hold
                if hold > 0:
                    hold -= batch
                elif not tty.kbd_flag:
                    ch = read_key()
                    if ch:
                        tty.key(ch)
                for _ in range(batch):
                    if step(state, memory, None, tty, tape):
                        print("\nHALTED at %04o, AC %04o" % (state["pc"], state["ac"]))
                        self.flush()
                        return
        except KeyboardInterrupt:
            print("\nStopped at %04o. run() continues." % state["pc"])
        except OSError as e:  # includes a TNFS server that stopped answering
            print("\n?tape: %s. Stopped at %04o." % (e, state["pc"]))
        self.flush()


def run(filename, start=0o200):
    """Load a ROM and run it. Returns the Machine, so the REPL can carry on with it."""
    m = Machine(filename, start)
    m.run()
    return m
