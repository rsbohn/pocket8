# SPDX-License-Identifier: Apache-2.0
"""A small TNFS client for CircuitPython.

    import socketpool, wifi
    from tnfs_cp import Client
    fh = Client(socketpool.SocketPool(wifi.radio), "192.0.2.148")
    fh.mount("/")
    print(fh.listdir("/dev"))
    fh.umount()

`pool` only needs AF_INET, SOCK_DGRAM and socket(), so CPython's `socket`
module works in its place; that is how test_shell.py runs this on a PC.
"""

import random
import struct

PORT = 16384
CHUNK = 512

ENOENT = 0x02
EOF = 0x21
NO_SESSION = 0xFF


class TnfsError(Exception):
    def __init__(self, cmd, status):
        super().__init__("command 0x%02x failed with status 0x%02x" % (cmd, status))
        self.cmd = cmd
        self.status = status


class Client:
    def __init__(self, pool, host, port=PORT, timeout=1.0, retries=5):
        self.addr = (host, port)
        self.sock = pool.socket(pool.AF_INET, pool.SOCK_DGRAM)
        self.sock.settimeout(timeout)
        self.retries = retries
        self.sid = 0
        self.seq = random.randrange(256)
        self.buf = bytearray(CHUNK + 64)

    def call(self, cmd, body=b"", ok=(0,)):
        self.seq = (self.seq + 1) & 0xFF
        packet = struct.pack("<HBB", self.sid, self.seq, cmd) + body
        buf = self.buf
        for _ in range(self.retries):
            self.sock.sendto(packet, self.addr)
            try:
                while True:
                    n, _ = self.sock.recvfrom_into(buf)
                    if n >= 5 and buf[2] == self.seq and buf[3] == cmd:
                        break
            except OSError:  # timed out: send again
                continue
            status = buf[4]
            if status not in ok:
                raise TnfsError(cmd, status)
            return buf[0] | buf[1] << 8, status, bytes(buf[5:n])
        raise OSError("no reply from %s to command 0x%02x" % (self.addr[0], cmd))

    def mount(self, path="/"):
        self.sid = 0
        sid, _, data = self.call(0x00, b"\x02\x01" + path.encode() + b"\x00\x00\x00")
        self.sid = sid
        return data

    def umount(self):
        self.call(0x01)
        self.sid = 0

    def close_socket(self):
        self.sock.close()

    def listdir(self, path="/"):
        _, _, data = self.call(0x10, path.encode() + b"\x00")
        h = bytes((data[0],))
        names = []
        try:
            while True:
                _, status, data = self.call(0x11, h, ok=(0, EOF))
                if status == EOF:
                    break
                names.append(data.rstrip(b"\x00").decode())
        finally:
            self.call(0x12, h)
        return names

    def stat(self, path):
        _, _, data = self.call(0x24, path.encode() + b"\x00")
        mode, _, _, size = struct.unpack("<HHHI", data[:10])
        return mode, size

    def open(self, path, flags=0x0001):
        _, _, data = self.call(0x29, struct.pack("<HH", flags, 0o644) + path.encode() + b"\x00")
        return data[0]

    def read(self, fd, n=CHUNK):
        _, status, data = self.call(0x21, struct.pack("<BH", fd, n), ok=(0, EOF))
        if status == EOF:
            return b""
        count = struct.unpack("<H", data[:2])[0]
        return data[2:2 + count]

    def write(self, fd, data):
        _, _, reply = self.call(0x22, struct.pack("<BH", fd, len(data)) + data)
        return struct.unpack("<H", reply[:2])[0]

    def close(self, fd):
        self.call(0x23, bytes((fd,)))

    # conveniences

    def cat(self, path, limit=None):
        """Read a whole file, or its first `limit` bytes."""
        fd = self.open(path)
        out = bytearray()
        try:
            while limit is None or len(out) < limit:
                want = CHUNK if limit is None else min(CHUNK, limit - len(out))
                chunk = self.read(fd, want)
                if not chunk:
                    break
                out += chunk
        finally:
            self.close(fd)
        return bytes(out)

    def put(self, path, data):
        fd = self.open(path, 0x0002)
        try:
            for i in range(0, len(data), CHUNK):
                self.write(fd, data[i:i + CHUNK])
        except Exception:
            try:
                self.close(fd)
            except Exception:
                pass
            raise
        self.close(fd)  # text files are applied here; EINVAL comes from this call
