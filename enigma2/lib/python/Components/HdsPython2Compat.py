# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Numele vechi din Python 2 pentru pluginurile traduse la incarcare (0.7.4, Components/HdsPython2Traducere.py).

Traducatorul pune un singur rand in fisierele traduse care folosesc unul din numele de aici:
    from Components.HdsPython2Compat import *  # HDSatelit: tradus din Python 2
Numele intra numai in acele fisiere; Python-ul celorlalte pluginuri si al imaginii ramane neatins (nimic pus in
builtins, niciun modul schimbat).

Ce e aici: ce nu repara traducerea (cmp, file, coerce, impartirea intreaga a lui Python 2) si, ca rezerva, numele pe
care traducerea le schimba de obicei (unicode, basestring, long, xrange ...), pentru locurile unde nu le vede (de
pilda un nume luat cu getattr sau pus intr-un dictionar)."""
import functools
import io
import sys

__all__ = ['cmp', 'file', 'coerce', 'unicode', 'basestring', 'long', 'xrange', 'unichr', 'raw_input', 'reduce',
	'execfile', 'reload', 'intern', 'apply', 'buffer', 'hds_py2_div', 'hds_py2_idiv']


def cmp(a, b):
	"""cmp din Python 2: -1, 0 sau 1"""
	return (a > b) - (a < b)


def file(name, mode='r', buffering=-1):
	"""file() din Python 2 = open(); citirea in mod text nu cade pe octetii care nu sunt UTF-8 (Python 2 citea octeti)"""
	if 'b' in mode:
		return open(name, mode, buffering)
	return open(name, mode, buffering, encoding='utf-8', errors='surrogateescape')


def coerce(a, b):
	t = type(a + b)
	return t(a), t(b)


unicode = str
basestring = (str, bytes)
long = int
xrange = range
unichr = chr
raw_input = input
reduce = functools.reduce
intern = sys.intern


def apply(func, args=(), kwargs=None):
	return func(*args, **(kwargs or {}))


def buffer(obj, offset=0, size=None):
	m = memoryview(obj)
	return m[offset:] if size is None else m[offset:offset + size]


def execfile(filename, globals=None, locals=None):
	if globals is None:
		globals = sys._getframe(1).f_globals
	if locals is None:
		locals = globals
	with io.open(filename, 'rb') as f:
		cod = compile(f.read(), filename, 'exec')
	exec(cod, globals, locals)


def reload(module):
	import importlib
	return importlib.reload(module)


def _intreg(x):
	# bool e si el int in Python 2 (True / 2 == 0)
	return isinstance(x, int)


def hds_py2_div(a, b):
	"""a / b ca in Python 2: impartire intreaga (rotunjita in jos) cand amandoua sunt numere intregi, altfel
	impartirea obisnuita. Traducatorul scrie a / b asa numai in fisierele fara `from __future__ import division`."""
	if _intreg(a) and _intreg(b):
		return a // b
	return a / b


def hds_py2_idiv(a, b):
	"""a /= b ca in Python 2 (vezi hds_py2_div)"""
	if _intreg(a) and _intreg(b):
		a //= b
		return a
	a /= b
	return a
