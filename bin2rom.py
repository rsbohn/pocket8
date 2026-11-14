"""Convert a PDP-8 BIN-loader paper tape image to a .rom file. Run on a PC:

    python bin2rom.py focal69.bin focal69.rom

BIN format: leader/trailer frames of 0o200; a pair of frames makes a 12-bit
word (6 bits each); a first frame with bit 6 set makes the pair an origin;
frames with bits 6 and 7 both set select a memory field; the last word before
the trailer is the sum of all the other data frames.
"""

import sys


def parse_bin(data):
    """Return ({address: word}, checksum_ok). Field settings other than 0 are refused."""
    i = 0
    while i < len(data) and data[i] != 0o200:  # skip anything before the leader
        i += 1
    while i < len(data) and data[i] == 0o200:
        i += 1
    memory = {}
    addr = 0
    total = 0
    last = None  # (address, word, frame sum) of the latest data word: it may be the checksum
    while i < len(data) and data[i] != 0o200:
        b = data[i]
        if b & 0o300 == 0o300:  # field setting
            if b & 0o070:
                raise ValueError("tape loads into field %o; only field 0 is supported" % ((b >> 3) & 7))
            i += 1
            continue
        if i + 1 >= len(data):
            raise ValueError("tape ends in the middle of a word")
        b2 = data[i + 1]
        word = ((b & 0o77) << 6) | (b2 & 0o77)
        if last is not None:  # the previous word was data after all: store it
            memory[last[0]] = last[1]
            total += last[2]
            last = None
        if b & 0o100:
            addr = word
            total += b + b2
        else:
            last = (addr, word, b + b2)
            addr = (addr + 1) & 0o7777
        i += 2
    if last is None:
        raise ValueError("no checksum word found")
    return memory, (total & 0o7777) == last[1]


def write_rom(filename, memory):
    """Write runs of consecutive addresses, eight words to a line."""
    addrs = sorted(memory)
    with open(filename, "w", newline="\n") as f:
        i = 0
        while i < len(addrs):
            j = i
            while j + 1 < len(addrs) and addrs[j + 1] == addrs[j] + 1 and j + 1 - i < 8:
                j += 1
            f.write("%04o: %s\n" % (addrs[i], " ".join("%04o" % memory[a] for a in addrs[i:j + 1])))
            i = j + 1


if __name__ == "__main__":
    src, dst = sys.argv[1], sys.argv[2]
    with open(src, "rb") as f:
        mem, ok = parse_bin(f.read())
    if not ok:
        sys.exit("checksum mismatch in %s; nothing written" % src)
    write_rom(dst, mem)
    print("%s: %d words, %04o-%04o, checksum ok -> %s" % (src, len(mem), min(mem), max(mem), dst))
