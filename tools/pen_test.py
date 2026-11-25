"""Visible pen-up test for the MakerCraft via the usbprint transport.

Stream:  IN;  FS40;  VS4;  <moves>  IN;

CRITICAL FORMAT RULE (verified on hardware, 2026-11-25):
    NO whitespace after the command letter.  ``PU2000,0;`` executes;
    ``PU 2000,0;`` is silently dropped by the SKYCUT firmware. InkCut's
    HPGL protocol never emits the space, which is why jobs through the
    app always worked while hand-written spaced commands did nothing.

Usage: python pen_test.py
All moves are pen-UP. 50 mm square at 40 units/mm.
"""
import ctypes
import time

from inkcut_usbprint.plugin import (
    list_usbprint_interfaces, open_interface, write_interface,
)

paths = list_usbprint_interfaces()
print("interfaces found: {}".format(len(paths)))
if not paths:
    raise SystemExit("no USBPRINT interface — is the cutter plugged in and on?")
path = paths[0]
print(path)

h = open_interface(path)
print("handle opened")


def step(label, data):
    n = write_interface(h, data.encode())
    status = "OK" if n == len(data) else "SHORT WRITE"
    print("{:14s} sent={:3d} delivered={:3d}  {}".format(
        label, len(data), n, status))
    return n


time.sleep(1)
step("IN", "IN;")
time.sleep(2)
step("FS40 (force)", "FS40;")
time.sleep(2)
step("VS4 (speed)", "VS4;")
time.sleep(2)
# 50 mm square at 40 units/mm = 2000 units, pen up throughout.
# No spaces — see the format rule in the module docstring.
for label, job in [
    ("PU right", "PU2000,0;"),
    ("PU up",    "PU2000,2000;"),
    ("PU left",  "PU0,2000;"),
    ("PU down",  "PU0,0;"),
]:
    step(label, job)
    time.sleep(2)
step("IN (finish)", "IN;")
ctypes.windll.kernel32.CloseHandle(h)
print("handle closed")
