r"""
Copyright (c) 2026

Distributed under the terms of the GPL v3 License.

The full license is in the file LICENSE, distributed with this software.

USBPRINT transport
------------------

Talks to cutters that enumerate as USB printer class, without a print queue and
without any vendor driver. Windows exposes such a device through the USBPRINT
device interface GUID; SetupAPI gives the interface path and CreateFile opens a
handle that accepts raw writes.

This exists because some cutters (e.g. Monoprice MakerCraft / SKYCUT) are only
driven by their vendor application, which reaches the device directly and never
installs a printer queue or a COM port. Neither InkCut's Printer transport (no
queue to attach to) nor Serial Port (no COM port) can reach them.

Verified against a Monoprice MakerCraft Craft Cutter Desktop:
    \\?\usb#vid_0483&pid_5750#skycut_bf54#{28d78fad-5a12-11d1-ae5b-0000f803a8c2}
WriteFile of HPGL on that handle moves the carriage.

Limitations:
  * The device advertises a bidirectional interface (Class 07 / SubClass 01 /
    Prot 02), but reads are not implemented here. The HPGL protocol never reads,
    so this does not affect cutting. Status polling is a TODO.
  * Reads and writes are synchronous. A cut is written in one go at the end of
    the job, which is how the HPGL protocol already behaves.
"""
import ctypes
import ctypes.wintypes as w
import sys
import traceback

from atom.api import Str, List, Instance, Value
from inkcut.core.api import Model, log
from inkcut.device.plugin import DeviceTransport

WINDOWS = sys.platform == "win32"

#: GUID_DEVINTERFACE_USBPRINT
USBPRINT_GUID = "28d78fad-5a12-11d1-ae5b-0000f803a8c2"

DIGCF_PRESENT = 0x02
DIGCF_DEVICEINTERFACE = 0x10
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

if WINDOWS:  # pragma: no cover - Windows only

    class _GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", ctypes.c_ulong),
            ("Data2", ctypes.c_ushort),
            ("Data3", ctypes.c_ushort),
            ("Data4", ctypes.c_ubyte * 8),
        ]

        def __init__(self, text):
            super().__init__()
            a, b, c, d, e = text.split("-")
            self.Data1 = int(a, 16)
            self.Data2 = int(b, 16)
            self.Data3 = int(c, 16)
            for i, byte in enumerate(bytes.fromhex(d + e)):
                self.Data4[i] = byte

    class _DEVICE_INTERFACE_DATA(ctypes.Structure):
        _fields_ = [
            ("cbSize", w.DWORD),
            ("InterfaceClassGuid", _GUID),
            ("Flags", w.DWORD),
            ("Reserved", ctypes.c_void_p),
        ]

    class _DEVICE_INTERFACE_DETAIL(ctypes.Structure):
        _fields_ = [("cbSize", w.DWORD), ("DevicePath", ctypes.c_wchar * 1)]

    _setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    _setupapi.SetupDiGetClassDevsW.argtypes = [
        ctypes.POINTER(_GUID), w.LPCWSTR, w.HWND, w.DWORD]
    _setupapi.SetupDiGetClassDevsW.restype = w.HANDLE
    _setupapi.SetupDiEnumDeviceInterfaces.argtypes = [
        w.HANDLE, ctypes.c_void_p, ctypes.POINTER(_GUID), w.DWORD,
        ctypes.POINTER(_DEVICE_INTERFACE_DATA)]
    _setupapi.SetupDiEnumDeviceInterfaces.restype = w.BOOL
    _setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [
        w.HANDLE, ctypes.POINTER(_DEVICE_INTERFACE_DATA), ctypes.c_void_p,
        w.DWORD, ctypes.POINTER(w.DWORD), ctypes.c_void_p]
    _setupapi.SetupDiGetDeviceInterfaceDetailW.restype = w.BOOL
    _setupapi.SetupDiDestroyDeviceInfoList.argtypes = [w.HANDLE]

    _kernel32.CreateFileW.argtypes = [
        w.LPCWSTR, w.DWORD, w.DWORD, ctypes.c_void_p, w.DWORD, w.DWORD, w.HANDLE]
    _kernel32.CreateFileW.restype = w.HANDLE
    _kernel32.WriteFile.argtypes = [
        w.HANDLE, w.LPCVOID, w.DWORD, ctypes.POINTER(w.DWORD), ctypes.c_void_p]
    _kernel32.WriteFile.restype = w.BOOL
    _kernel32.CloseHandle.argtypes = [w.HANDLE]


def list_usbprint_interfaces():
    """Return the device-interface paths of every present USBPRINT device."""
    if not WINDOWS:
        return []
    paths = []
    guid = _GUID(USBPRINT_GUID)
    hdev = _setupapi.SetupDiGetClassDevsW(
        ctypes.byref(guid), None, None,
        DIGCF_PRESENT | DIGCF_DEVICEINTERFACE)
    if hdev in (None, INVALID_HANDLE_VALUE):
        log.debug("usbprint | SetupDiGetClassDevs failed: {}".format(
            ctypes.get_last_error()))
        return []
    try:
        index = 0
        while True:
            did = _DEVICE_INTERFACE_DATA()
            did.cbSize = ctypes.sizeof(_DEVICE_INTERFACE_DATA)
            if not _setupapi.SetupDiEnumDeviceInterfaces(
                    hdev, None, ctypes.byref(guid), index, ctypes.byref(did)):
                break
            needed = w.DWORD(0)
            _setupapi.SetupDiGetDeviceInterfaceDetailW(
                hdev, ctypes.byref(did), None, 0, ctypes.byref(needed), None)
            buf = ctypes.create_string_buffer(needed.value)
            ctypes.cast(buf, ctypes.POINTER(
                _DEVICE_INTERFACE_DETAIL)).contents.cbSize = ctypes.sizeof(
                    _DEVICE_INTERFACE_DETAIL)
            if _setupapi.SetupDiGetDeviceInterfaceDetailW(
                    hdev, ctypes.byref(did), buf, needed.value,
                    ctypes.byref(needed), None):
                paths.append(ctypes.wstring_at(
                    ctypes.addressof(buf)
                    + _DEVICE_INTERFACE_DETAIL.DevicePath.offset))
            index += 1
    finally:
        _setupapi.SetupDiDestroyDeviceInfoList(hdev)
    return paths


def open_interface(path):
    """Open a USBPRINT interface path for raw read/write."""
    handle = _kernel32.CreateFileW(
        path, GENERIC_READ | GENERIC_WRITE, 0, None, OPEN_EXISTING, 0, None)
    if handle in (None, INVALID_HANDLE_VALUE):
        raise IOError("Cannot open {} (error {})".format(
            path, ctypes.get_last_error()))
    return handle


def write_interface(handle, data):
    """Write raw bytes to an open USBPRINT handle."""
    buf = bytes(data)
    if not buf:
        # A zero-length WriteFile returns ERROR_NO_SYSTEM_RESOURCES (1450) on a
        # device handle; treat it as the no-op it is.
        return 0
    written = w.DWORD(0)
    if not _kernel32.WriteFile(handle, buf, len(buf), ctypes.byref(written), None):
        raise IOError("WriteFile failed (error {})".format(
            ctypes.get_last_error()))
    return written.value


class UsbPrintConfig(Model):

    #: Selected interface path
    device_path = Str().tag(config=True)

    #: Available interface paths
    paths = List()

    def _default_paths(self):
        return list_usbprint_interfaces()

    def refresh(self):
        self.paths = list_usbprint_interfaces()


class UsbPrintTransport(DeviceTransport):

    #: Default config
    config = Instance(UsbPrintConfig, ()).tag(config=True)

    #: The open handle
    connection = Value()

    #: Current path
    device_path = Str()

    async def connect(self):
        config = self.config
        if not config.paths:
            config.refresh()
        path = config.device_path
        if not path and config.paths:
            path = config.paths[0]
            config.device_path = path
        if not path:
            raise IOError("No USBPRINT interface found. Is the machine "
                          "connected and powered on?")
        self.device_path = path
        try:
            self.connection = open_interface(path)
            log.debug("-- {} | opened".format(path))
            # Set the flag the job runner waits on, then let the protocol emit
            # its own init sequence. connection_made only exists on some
            # protocols (it was removed from HPGL), so call it defensively.
            self.connected = True
            connection_made = getattr(self.protocol, "connection_made", None)
            if connection_made is not None:
                connection_made()
            await self.protocol.init()
        except Exception:
            log.error("{} | {}".format(path, traceback.format_exc()))
            raise

    async def write(self, data):
        if not self.connection:
            raise IOError("{} is not opened".format(self.device_path))
        if hasattr(data, "encode"):
            data = data.encode()
        log.debug("-> {} | {}".format(self.device_path, data))
        self.last_write = data
        write_interface(self.connection, data)

    async def read(self, size=None):
        # The interface is bidirectional but reads are not implemented; the
        # HPGL protocol never reads so this is not on the cutting path.
        return b""

    async def disconnect(self):
        if self.connection:
            log.debug("-- {} | closed by request".format(self.device_path))
            _kernel32.CloseHandle(self.connection)
            self.connection = None
        self.connected = False

    def __repr__(self):
        return self.device_path
