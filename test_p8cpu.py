"""Tests for p8cpu.py. Run on a PC: python test_p8cpu.py"""

import p8cpu


def machine(words, at=0o200, ac=0, link=0, **extra):
    mem = [0] * 4096
    for i, w in enumerate(words):
        mem[at + i] = w
    st = {'pc': at, 'ac': ac, 'link': link, 'neo_r': 0, 'neo_g': 0, 'neo_b': 0,
          'neo_user_control': False}
    st.update(extra)
    return mem, st


def step(mem, st):
    """Fetch and execute the way pocket8.py does: increment PC, then execute."""
    inst = mem[st['pc']]
    st['pc'] = (st['pc'] + 1) & 0o7777
    return p8cpu.execute(inst, st, mem)


def one(inst, ac=0, link=0, **extra):
    mem, st = machine([inst], ac=ac, link=link, **extra)
    step(mem, st)
    return st


def run(mem, st, limit=100000):
    for n in range(limit):
        if step(mem, st):
            return n + 1
    raise AssertionError("did not halt")


def check(name, got, want):
    if got != want:
        raise AssertionError("%s: got %s, want %s" % (name, got, want))


def al(st):
    return "%d %04o" % (st['link'], st['ac'])


def test_tad():
    mem, st = machine([0o1205, 0, 0, 0, 0, 0o0003], ac=0o0002, link=1)
    step(mem, st)
    check("TAD does not add the link", al(st), "1 0005")
    mem, st = machine([0o1205, 0, 0, 0, 0, 0o0001], ac=0o7777, link=0)
    step(mem, st)
    check("TAD carry sets the link", al(st), "1 0000")
    mem, st = machine([0o1205, 0, 0, 0, 0, 0o0001], ac=0o7777, link=1)
    step(mem, st)
    check("TAD carry complements the link", al(st), "0 0000")


def test_rotates():
    check("RAL", al(one(0o7004, ac=0o4001, link=0)), "1 0002")
    check("RAL link in", al(one(0o7004, ac=0o0001, link=1)), "0 0003")
    check("RTL", al(one(0o7006, ac=0o6001, link=0)), "1 0005")
    check("RAR", al(one(0o7010, ac=0o0001, link=0)), "1 0000")
    check("RAR link in", al(one(0o7010, ac=0o0002, link=1)), "0 4001")
    check("RTR", al(one(0o7012, ac=0o0003, link=0)), "1 4000")
    check("BSW", al(one(0o7002, ac=0o1234, link=1)), "1 3412")
    check("NOP", al(one(0o7000, ac=0o1234, link=1)), "1 1234")


def test_group1_order():
    check("CLA CLL", al(one(0o7300, ac=0o1234, link=1)), "0 0000")
    check("CMA", al(one(0o7040, ac=0o1234)), "0 6543")
    check("CML", al(one(0o7020, link=0)), "1 0000")
    check("IAC", al(one(0o7001, ac=0o7777, link=0)), "1 0000")
    check("CIA", al(one(0o7041, ac=0o0001)), "0 7777")
    check("CLA IAC (constant 1)", al(one(0o7201, ac=0o1234)), "0 0001")
    check("STA (constant -1)", al(one(0o7240, ac=0o1234)), "0 7777")
    # IAC happens before the rotate: these load constants 2 and 4
    check("CLA CLL IAC RAL", al(one(0o7305, ac=0o1234, link=1)), "0 0002")
    check("CLA CLL IAC RTL", al(one(0o7307, ac=0o1234, link=1)), "0 0004")
    check("CLA CLL CML RAR (constant 4000)", al(one(0o7330, ac=0o1234)), "0 4000")


def test_group2():
    def skipped(inst, ac=0, link=0):
        return one(inst, ac=ac, link=link)['pc'] == 0o202
    check("SMA skips", skipped(0o7500, ac=0o4000), True)
    check("SMA no skip", skipped(0o7500, ac=0o3777), False)
    check("SZA skips", skipped(0o7440, ac=0), True)
    check("SNL skips", skipped(0o7420, link=1), True)
    check("SPA skips", skipped(0o7510, ac=0o3777), True)
    check("SNA skips", skipped(0o7450, ac=1), True)
    check("SZL skips", skipped(0o7430, link=0), True)
    check("SKP", skipped(0o7410), True)
    check("SMA SZA either", skipped(0o7540, ac=0), True)
    check("SPA SNA both needed", skipped(0o7550, ac=0), False)
    check("SZA CLA tests before clearing", skipped(0o7640, ac=5), False)
    check("OSR", al(one(0o7404, ac=0o0700, sr=0o0007)), "0 0707")
    check("LAS", al(one(0o7604, ac=0o0700, sr=0o1234)), "0 1234")
    mem, st = machine([0o7402])
    check("HLT halts", step(mem, st), True)


def test_group3():
    st = one(0o7421, ac=0o1234)
    check("MQL", (st['ac'], st['mq']), (0, 0o1234))
    check("MQA", one(0o7501, ac=0o0700, mq=0o0007)['ac'], 0o0707)
    st = one(0o7521, ac=0o1111, mq=0o2222)
    check("SWP", (st['ac'], st['mq']), (0o2222, 0o1111))
    st = one(0o7621, ac=0o1111, mq=0o2222)
    check("CAM", (st['ac'], st['mq']), (0, 0))
    check("ACL", one(0o7701, ac=0o1111, mq=0o2222)['ac'], 0o2222)


def test_addressing():
    # last word of a page: a current-page reference stays on that page
    mem, st = machine([0o1377], at=0o377)
    mem[0o377] = 0o1377
    step(mem, st)
    check("current page at page end", st['ac'], 0o1377)
    # zero page
    mem, st = machine([0o1050])
    mem[0o050] = 0o0042
    step(mem, st)
    check("zero page", st['ac'], 0o0042)
    # indirect
    mem, st = machine([0o1450])
    mem[0o050] = 0o1000
    mem[0o1000] = 0o0123
    step(mem, st)
    check("indirect", st['ac'], 0o0123)
    # auto-index: pointer is incremented, then used
    mem, st = machine([0o1410, 0o1410])
    mem[0o010] = 0o0777
    mem[0o1000], mem[0o1001] = 0o0001, 0o0002
    step(mem, st)
    step(mem, st)
    check("auto-index", (st['ac'], mem[0o010]), (0o0003, 0o1001))
    # not auto-index when direct, or on another page's 10-17
    mem, st = machine([0o1010])
    mem[0o010] = 0o0005
    step(mem, st)
    check("direct 0010 untouched", (st['ac'], mem[0o010]), (0o0005, 0o0005))
    mem, st = machine([0o1610], at=0o400)
    mem[0o410] = 0o1000
    mem[0o1000] = 0o0007
    step(mem, st)
    check("indirect via 0410 is not auto-index", (st['ac'], mem[0o410]), (0o0007, 0o1000))


def test_jms_isz_dca():
    mem, st = machine([0o4210], at=0o200)
    step(mem, st)
    check("JMS", (mem[0o210], st['pc']), (0o201, 0o211))
    mem, st = machine([0o2205, 0, 0, 0, 0, 0o7777])
    step(mem, st)
    check("ISZ skips at zero", (mem[0o205], st['pc']), (0, 0o202))
    mem, st = machine([0o3205], ac=0o1234)
    step(mem, st)
    check("DCA", (mem[0o205], st['ac']), (0o1234, 0))


def test_program_multiply():
    """6 x 7 by repeated addition, with a subroutine call and an indirect return."""
    prog = [
        0o7300,  # 200  CLA CLL
        0o1220,  # 201  TAD 220     -count
        0o3222,  # 202  DCA 222     counter
        0o4210,  # 203  JMS 210     add once
        0o2222,  # 204  ISZ 222
        0o5203,  # 205  JMP 203
        0o1223,  # 206  TAD 223     load result
        0o7402,  # 207  HLT
        0o0000,  # 210  return address
        0o1223,  # 211  TAD 223
        0o1221,  # 212  TAD 221
        0o3223,  # 213  DCA 223
        0o5610,  # 214  JMP I 210
    ]
    mem, st = machine(prog)
    mem[0o220] = (-6) & 0o7777
    mem[0o221] = 7
    run(mem, st)
    check("6 x 7", st['ac'], 42)


def test_program_block_copy():
    """Copy 8 words with two auto-index pointers."""
    prog = [
        0o7300,  # 400  CLA CLL
        0o1410,  # 401  TAD I 10
        0o3411,  # 402  DCA I 11
        0o2020,  # 403  ISZ 20
        0o5201,  # 404  JMP 401 (current page)
        0o7402,  # 405  HLT
    ]
    mem, st = machine(prog, at=0o400)
    mem[0o010] = 0o1000 - 1
    mem[0o011] = 0o2000 - 1
    mem[0o020] = (-8) & 0o7777
    for i in range(8):
        mem[0o1000 + i] = 0o100 + i
    run(mem, st)
    check("block copy", mem[0o2000:0o2010], [0o100 + i for i in range(8)])


def tty_machine(rom):
    import p8run
    mem = [0] * 4096
    p8run.load(rom, mem)
    out = []
    return mem, p8run.new_state(), p8cpu.Teletype(out.append), out


def steps(mem, st, tty, n):
    for _ in range(n):
        if p8cpu.step(st, mem, None, tty):
            return True
    return False


def test_tty_iots():
    out = []
    tty = p8cpu.Teletype(out.append)
    mem, st = machine([0o6031, 0o6041, 0o6046, 0o6041, 0o7402, 0o6042, 0o6041, 0o7402], ac=0o301)
    check("KSF no key", (p8cpu.step(st, mem, None, tty), st['pc']), (False, 0o201))
    p8cpu.step(st, mem, None, tty)
    check("TSF before first print", st['pc'], 0o202)
    p8cpu.step(st, mem, None, tty)
    check("TLS prints", out, ["A"])
    p8cpu.step(st, mem, None, tty)
    check("TSF after print skips", st['pc'], 0o205)
    p8cpu.step(st, mem, None, tty)
    p8cpu.step(st, mem, None, tty)
    check("TCF clears the flag", st['pc'], 0o207)
    tty.key("a")
    check("key is upper-cased, top bit set", (tty.kbd_flag, tty.kbd_buf), (1, 0o301))
    st = {'pc': 0o201, 'ac': 0o7000, 'link': 0}
    p8cpu.execute(0o6034, st, mem, None, tty)
    check("KRS ORs and keeps the flag", (st['ac'], tty.kbd_flag), (0o7301, 1))
    p8cpu.execute(0o6031, st, mem, None, tty)
    check("KSF with key skips", st['pc'], 0o202)
    p8cpu.execute(0o6036, st, mem, None, tty)
    check("KRB reads and clears", (st['ac'], tty.kbd_flag), (0o301, 0))
    tty.printer(6, 0o200)
    tty.printer(6, 0o377)
    check("null and rubout are not printed", out, ["A"])


def test_tty_hello_and_echo():
    mem, st, tty, out = tty_machine("hello.rom")
    check("runs to the key wait", steps(mem, st, tty, 2000), False)
    check("greeting", "".join(out), "POCKET-8 TTY READY. TYPE; . HALTS\r\n")
    del out[:]
    for ch in "hi 8":
        tty.key(ch)
        steps(mem, st, tty, 50)
    check("echo", "".join(out), "HI 8")
    tty.key(".")
    check("dot halts", steps(mem, st, tty, 50), True)


def test_tty_interrupt_echo():
    mem, st, tty, out = tty_machine("irqecho.rom")
    steps(mem, st, tty, 100)
    check("idles with interrupts on", (st['pc'], st['ie'], out), (0o202, 2, []))
    tty.key("x")
    steps(mem, st, tty, 1)
    check("interrupt saves PC and turns interrupts off", (mem[0], st['ie']), (0o202, 0))
    steps(mem, st, tty, 100)
    check("echoed from the handler", "".join(out), "X")
    check("back in the idle loop", (st['pc'], st['ie'], tty.kbd_flag, tty.tty_flag), (0o202, 2, 0, 0))
    for ch in "yz":
        tty.key(ch)
        steps(mem, st, tty, 100)
    check("keeps going", "".join(out), "XYZ")


def test_ion_delay():
    # ION takes effect after the following instruction
    out = []
    tty = p8cpu.Teletype(out.append)
    mem, st = machine([0o6001, 0o7000, 0o7000, 0o7000])
    mem[1] = 0o7402
    tty.key("q")
    p8cpu.step(st, mem, None, tty)
    p8cpu.step(st, mem, None, tty)
    check("one more instruction runs", st['pc'], 0o202)
    p8cpu.step(st, mem, None, tty)
    check("then the interrupt is taken", (mem[0], st['pc']), (0o202, 0o002))


def test_focal69():
    """FOCAL,1969 computes and stores a program. Skipped if focal69.rom is absent."""
    import os
    if not os.path.exists("focal69.rom"):
        print("      (focal69.rom not here; skipped)")
        return
    mem, st, tty, out = tty_machine("focal69.rom")
    keys = list("TYPE 2+2\rT FSQT(2)\r1.1 FOR I=1,3; TYPE I*I, !\rGO\r")
    quiet = 0
    for _ in range(40000):
        check("FOCAL does not halt", steps(mem, st, tty, 200), False)
        quiet += 200
        if not tty.kbd_flag and quiet > 20000:  # type when FOCAL has gone quiet
            if not keys:
                break
            tty.key(keys.pop(0))
            quiet = 0
    text = "".join(out).replace("\r", "")
    for want in ("=    4.0000*", "=    1.4142*", "=    1.0000\n=    4.0000\n=    9.0000\n*"):
        check("FOCAL output has %r" % want, want in text, True)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok  ", t.__name__)
    print("%d test groups passed" % len(tests))
