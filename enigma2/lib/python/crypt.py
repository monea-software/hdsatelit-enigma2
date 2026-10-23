# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""
Python 3.13 standard library replacement for removed 'crypt' module (PEP 594).
Uses system libcrypt.so via ctypes.
"""
try:
    import ctypes
except ImportError:
    ctypes = None

_lib = None
if ctypes is not None:
    for _name in ('libcrypt.so.2', 'libcrypt.so.1', 'libcrypt.so', 'libc.so.6'):
        try:
            _lib = ctypes.CDLL(_name)
            if hasattr(_lib, 'crypt'):
                break
        except OSError:
            pass

if _lib and hasattr(_lib, 'crypt'):
    _c_crypt = _lib.crypt
    _c_crypt.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    _c_crypt.restype = ctypes.c_char_p

    def crypt(word, salt=None):
        if salt is None:
            salt = ''
        w_b = word.encode('utf-8') if isinstance(word, str) else word
        s_b = salt.encode('utf-8') if isinstance(salt, str) else salt
        res = _c_crypt(w_b, s_b)
        return res.decode('utf-8') if res else None
else:
    def crypt(word, salt=None):
        return None

__all__ = ['crypt']
