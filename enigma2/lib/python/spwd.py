# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""
Python 3.13 standard library replacement for removed 'spwd' module (PEP 594).
Reads /etc/shadow.
"""
from collections import namedtuple

struct_spwd = namedtuple('struct_spwd', [
    'sp_namp', 'sp_pwdp', 'sp_lstchg', 'sp_min', 'sp_max',
    'sp_warn', 'sp_inact', 'sp_expire', 'sp_flag'
])

def _parse_entry(line):
    parts = line.strip().split(':')
    if len(parts) < 2:
        return None
    def _int_or_none(val):
        try:
            return int(val) if val != '' else None
        except ValueError:
            return None
    return struct_spwd(
        sp_namp=parts[0],
        sp_pwdp=parts[1],
        sp_lstchg=_int_or_none(parts[2]) if len(parts) > 2 else None,
        sp_min=_int_or_none(parts[3]) if len(parts) > 3 else None,
        sp_max=_int_or_none(parts[4]) if len(parts) > 4 else None,
        sp_warn=_int_or_none(parts[5]) if len(parts) > 5 else None,
        sp_inact=_int_or_none(parts[6]) if len(parts) > 6 else None,
        sp_expire=_int_or_none(parts[7]) if len(parts) > 7 else None,
        sp_flag=_int_or_none(parts[8]) if len(parts) > 8 else None,
    )

def getspall():
    entries = []
    try:
        with open('/etc/shadow', 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                entry = _parse_entry(line)
                if entry:
                    entries.append(entry)
    except OSError as e:
        raise PermissionError(f"Permission denied: '/etc/shadow'") from e
    return entries

def getspnam(name):
    try:
        with open('/etc/shadow', 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                parts = line.strip().split(':')
                if parts and parts[0] == name:
                    return _parse_entry(line)
    except OSError as e:
        raise PermissionError(f"Permission denied: '/etc/shadow'") from e
    raise KeyError(f"getspnam(): name not found: {name}")

__all__ = ['getspnam', 'getspall', 'struct_spwd']
