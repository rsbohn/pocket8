"""Write the demo ROMs. Run on a PC: python make_roms.py"""


def text(s):
    """A string as teletype words (top bit set), ending with 0."""
    return [ord(c) | 0o200 for c in s] + [0]


def write_rom(filename, blocks):
    with open(filename, "w", newline="\n") as f:
        for addr, words in blocks:
            for i in range(0, len(words), 8):
                f.write("%04o: %s\n" % (addr + i, " ".join("%04o" % w for w in words[i:i + 8])))


# Print a greeting, then echo keys by polling the flags. A "." halts.
HELLO = [
    (0o010, [0o0277]),
    (0o200, [
        0o7300,  # 200  CLA CLL
        0o6046,  # 201  TLS          raise the printer flag
        0o7300,  # 202  CLA CLL
        0o1410,  # 203  TAD I 10     next character
        0o7450,  # 204  SNA          zero ends the text
        0o5212,  # 205  JMP 212
        0o6041,  # 206  TSF
        0o5206,  # 207  JMP .-1
        0o6046,  # 210  TLS
        0o5202,  # 211  JMP 202
        0o6031,  # 212  KSF          wait for a key
        0o5212,  # 213  JMP .-1
        0o6036,  # 214  KRB
        0o3232,  # 215  DCA 232      save it
        0o1232,  # 216  TAD 232
        0o1233,  # 217  TAD 233      minus "."
        0o7450,  # 220  SNA
        0o7402,  # 221  HLT          it was "."
        0o7300,  # 222  CLA CLL
        0o1232,  # 223  TAD 232
        0o6041,  # 224  TSF
        0o5224,  # 225  JMP .-1
        0o6046,  # 226  TLS          echo
        0o5212,  # 227  JMP 212
    ]),
    (0o232, [0o0000, (-0o256) & 0o7777]),
    (0o300, text("POCKET-8 TTY READY. TYPE; . HALTS\r\n")),
]

# Echo keys from an interrupt handler while the main program idles.
IRQECHO = [
    (0o000, [0o0000, 0o5402, 0o0400]),   # return address; JMP I 2; handler address
    (0o200, [
        0o7300,  # 200  CLA CLL
        0o6001,  # 201  ION
        0o5202,  # 202  JMP .        idle
    ]),
    (0o400, [
        0o3020,  # 400  DCA 20       save AC
        0o6031,  # 401  KSF          a key?
        0o5206,  # 402  JMP 406
        0o6036,  # 403  KRB
        0o6046,  # 404  TLS          echo
        0o7200,  # 405  CLA
        0o6041,  # 406  TSF          printer done?
        0o7410,  # 407  SKP
        0o6042,  # 410  TCF          clear its flag
        0o1020,  # 411  TAD 20       restore AC
        0o6001,  # 412  ION
        0o5400,  # 413  JMP I 0
    ]),
]

if __name__ == "__main__":
    write_rom("hello.rom", HELLO)
    write_rom("irqecho.rom", IRQECHO)
    print("wrote hello.rom and irqecho.rom")
