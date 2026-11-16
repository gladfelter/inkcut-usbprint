# -*- coding: utf-8 -*-
"""
Copyright (c) 2026

Distributed under the terms of the GPL v3 License.

The full license is in the file LICENSE, distributed with this software.

USB Print Interface transport for Inkcut -- entry point.

Inkcut loads external plugins from the ``inkcut.plugin`` entry point group and
calls ``load()`` on each, expecting a *factory*: either a ``PluginManifest``
subclass or a function that returns a ``PluginManifest`` instance.  It then
instantiates whatever it got:

    plugins.append(entry_point.load())   # the factory
    ...
    w.register(Manifest())               # called with no arguments

So the object named here must be callable with no arguments and return a
manifest instance.  A ``.enaml`` module can only be imported inside an
``enaml.imports()`` context, so the entry point names the helper below rather
than the manifest class itself.
"""


def manifest_factory():
    """Return a manifest instance, importing it under ``enaml.imports()``.

    See the module docstring for why this indirection exists.
    """
    import enaml

    with enaml.imports():
        from .manifest import UsbPrintManifest

    return UsbPrintManifest()
