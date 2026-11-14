# SPDX-License-Identifier: MIT
"""Paper tapes that are files on TNFS servers.

A tape is named "host:/path", for example "grumpy:/squares.fc". Hosts come
from HOSTS below, or from TNFS_HOSTS in settings.toml
("grumpy=192.0.2.59 funhouse=192.0.2.148"); an IP address also works.

Text tapes (the default) are translated between Unix text files and what
PDP-8 software expects: on reading, each newline becomes a carriage return
and the top bit is set; on punching, the top bit, carriage returns, nulls
and rubouts are dropped. Binary tapes (.bin, .rim, .pt) pass through as is.
"""

import os

from tnfs_cp import Client, CHUNK

HOSTS = {"grumpy": "192.0.2.59", "funhouse": "192.0.2.148"}

O_RDONLY, O_WRONLY, O_CREAT, O_TRUNC = 0x0001, 0x0002, 0x0100, 0x0200
BINARY = (".bin", ".rim", ".pt")


def hosts():
    table = dict(HOSTS)
    for item in (os.getenv("TNFS_HOSTS") or "").split():
        if "=" in item:
            name, addr = item.split("=", 1)
            table[name.lower()] = addr
    return table


def parse(spec):
    """Split "host:/path" into (address, path)."""
    if ":" not in spec:
        raise ValueError('a tape is named "host:/path"')
    host, path = spec.split(":", 1)
    if not path.startswith("/"):
        path = "/" + path
    return hosts().get(host.lower(), host), path


def is_text(path, text):
    if text is not None:
        return text
    return not path.lower().endswith(BINARY)


class Reader:
    """Call it for the next byte of the tape; None when the tape runs out."""

    def __init__(self, client, path, text=True):
        self.client = client
        self.text = text
        self.fd = client.open(path, O_RDONLY)
        self.buf = b""
        self.pos = 0

    def __call__(self):
        while True:
            if self.pos >= len(self.buf):
                if self.fd is None:
                    return None
                self.buf = self.client.read(self.fd, CHUNK)
                self.pos = 0
                if not self.buf:
                    self.close()
                    return None
            b = self.buf[self.pos]
            self.pos += 1
            if not self.text:
                return b
            if b == 13:  # CRLF files: the LF that follows becomes the CR
                continue
            return (13 if b == 10 else b & 0x7F) | 0x80

    def close(self):
        if self.fd is not None:
            fd, self.fd = self.fd, None
            self.client.close(fd)


class Punch:
    """Call it with each byte punched. flush() sends what is buffered."""

    def __init__(self, client, path, text=True):
        self.client = client
        self.text = text
        self.fd = client.open(path, O_WRONLY | O_CREAT | O_TRUNC)
        self.buf = bytearray()

    def __call__(self, b):
        if self.text:
            b &= 0x7F
            if b in (0, 13, 127):
                return
        self.buf.append(b)
        if len(self.buf) >= CHUNK:
            self.flush()

    def write(self, s):
        """Take printed text, so a Punch can also record the teletype."""
        for ch in s:
            self(ord(ch))

    def flush(self):
        if self.fd is not None and self.buf:
            data, self.buf = bytes(self.buf), bytearray()
            self.client.write(self.fd, data)

    def close(self):
        if self.fd is not None:
            self.flush()
            fd, self.fd = self.fd, None
            self.client.close(fd)


class Library:
    """Opens tapes, keeping one mounted TNFS session per server."""

    def __init__(self, pool):
        self.pool = pool
        self.clients = {}

    def client(self, addr):
        c = self.clients.get(addr)
        if c is None:
            c = Client(self.pool, addr)
            c.mount("/")
            self.clients[addr] = c
        return c

    def reader(self, spec, text=None):
        addr, path = parse(spec)
        return Reader(self.client(addr), path, is_text(path, text))

    def punch(self, spec, text=None):
        addr, path = parse(spec)
        return Punch(self.client(addr), path, is_text(path, text))

    def listdir(self, spec):
        addr, path = parse(spec)
        return sorted(n for n in self.client(addr).listdir(path) if n not in (".", ".."))

    def close(self):
        for c in self.clients.values():
            try:
                c.umount()
            except Exception:
                pass
            c.close_socket()
        self.clients = {}
