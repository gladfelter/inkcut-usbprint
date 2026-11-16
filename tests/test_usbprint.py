# -*- coding: utf-8 -*-
"""
Copyright (c) 2026

Distributed under the terms of the GPL v3 License.

The full license is in the file LICENSE, distributed with this software.

The transport is exercised against a fake OS layer, in the same style as
``inkcut/tests/test_printer.py``: every ctypes call is replaced, so the tests run
on any platform without a cutter attached.  The Windows paths are guarded by
``WINDOWS`` inside ``plugin.py``, so importing the module on Linux is safe.
"""
import asyncio

import pytest

from inkcut.device.protocols.hpgl import HPGLProtocol

from inkcut_usbprint import plugin

FAKE_INTERFACE = (
    '\\\\?\\usb#vid_0483&pid_5750#skycut_bf54'
    '#{28d78fad-5a12-11d1-ae5b-0000f803a8c2}'
)


class FakeKernel32(object):
    """ Records handles closed by the transport. """

    def __init__(self):
        self.closed = []

    def CloseHandle(self, handle):
        self.closed.append(handle)
        return True


@pytest.fixture
def os_layer(monkeypatch):
    """ Replace every OS call the transport makes and record what it did. """
    state = {
        'interfaces': [FAKE_INTERFACE],
        'opened': [],
        'written': [],
    }
    kernel32 = FakeKernel32()

    monkeypatch.setattr(plugin, 'list_usbprint_interfaces',
                        lambda: list(state['interfaces']))

    def fake_open(path):
        state['opened'].append(path)
        return ('handle', path)

    def fake_write(handle, data):
        state['written'].append((handle, bytes(data)))
        return len(data)

    monkeypatch.setattr(plugin, 'open_interface', fake_open)
    monkeypatch.setattr(plugin, 'write_interface', fake_write)
    #: ``_kernel32`` only exists on Windows; create it where it does not.
    monkeypatch.setattr(plugin, '_kernel32', kernel32, raising=False)

    state['kernel32'] = kernel32
    return state


def make_transport(device_path=None):
    """ A transport with an HPGL protocol, as Inkcut would assemble it. """
    protocol = HPGLProtocol(scale=1)
    config = plugin.UsbPrintConfig()
    if device_path is not None:
        config.device_path = device_path
    return plugin.UsbPrintTransport(protocol=protocol, config=config), protocol


async def test_connect_writes_init_then_moves_then_disconnects(os_layer):
    """ The full lifecycle a cut goes through. """
    transport, protocol = make_transport(FAKE_INTERFACE)

    await asyncio.wait_for(transport.connect(), 5)
    assert transport.connected
    assert os_layer['opened'] == [FAKE_INTERFACE]

    #: connect() lets the protocol emit its own init sequence
    assert os_layer['written'][0][1] == b'IN;'

    await asyncio.wait_for(protocol.move(3, 2, 1), 5)
    assert os_layer['written'][-1][1] == b'PD3,2;'

    await asyncio.wait_for(transport.disconnect(), 5)
    assert not transport.connected
    assert os_layer['kernel32'].closed == [('handle', FAKE_INTERFACE)]


async def test_connect_falls_back_to_first_interface(os_layer):
    """ An empty device_path must not fail while exactly one interface exists. """
    transport, _ = make_transport(device_path='')

    await asyncio.wait_for(transport.connect(), 5)

    assert os_layer['opened'] == [FAKE_INTERFACE]
    #: The fallback is recorded, so a second interface appearing later does not
    #: silently change which machine is driven.
    assert transport.config.device_path == FAKE_INTERFACE


async def test_connect_without_any_interface_raises(os_layer):
    """ A disconnected machine must produce a readable error, not a crash. """
    os_layer['interfaces'] = []
    transport, _ = make_transport()

    with pytest.raises(IOError) as excinfo:
        await asyncio.wait_for(transport.connect(), 5)

    assert 'No USBPRINT interface' in str(excinfo.value)
    assert os_layer['opened'] == []


async def test_write_before_connect_raises(os_layer):
    transport, _ = make_transport(FAKE_INTERFACE)

    with pytest.raises(IOError):
        await asyncio.wait_for(transport.write(b'IN;'), 5)


async def test_disconnect_without_connect_is_safe(os_layer):
    transport, _ = make_transport(FAKE_INTERFACE)

    await asyncio.wait_for(transport.disconnect(), 5)

    assert not transport.connected
    assert os_layer['kernel32'].closed == []


def test_zero_length_write_is_a_noop():
    """ A zero length WriteFile returns error 1450 on a device handle.

    The guard is in the real function, so this runs without any mocking - and
    without touching ctypes, since it returns before calling WriteFile.
    """
    assert plugin.write_interface(object(), b'') == 0


def test_interfaces_are_empty_off_windows(monkeypatch):
    """ Importing on Linux/macOS must be inert rather than crash. """
    monkeypatch.setattr(plugin, 'WINDOWS', False)

    assert plugin.list_usbprint_interfaces() == []
