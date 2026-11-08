# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Pluginurile cer vechiul imp pentru surse si cod compilat. Incarcarea foloseste
# importlib, cu numele, rezultatele si constantele interfetei vechi.

import _imp
import importlib
from importlib import machinery, util
import os
import sys
import tokenize
from types import ModuleType


SEARCH_ERROR = 0
PY_SOURCE = 1
PY_COMPILED = 2
C_EXTENSION = 3
PKG_DIRECTORY = 5
C_BUILTIN = 6
PY_FROZEN = 7

__all__ = [
	"SEARCH_ERROR", "PY_SOURCE", "PY_COMPILED", "C_EXTENSION", "PKG_DIRECTORY",
	"C_BUILTIN", "PY_FROZEN", "load_source", "load_compiled", "load_dynamic",
	"load_module", "load_package", "find_module", "reload", "new_module",
	"get_suffixes", "get_magic", "get_tag", "cache_from_source", "source_from_cache",
	"acquire_lock", "release_lock", "lock_held", "is_builtin", "is_frozen",
	"init_builtin", "init_frozen", "NullImporter",
]

_LIPSA = object()


class _SourceLoader(machinery.SourceFileLoader):
	def __init__(self, name, path, file=None):
		super().__init__(name, path)
		self._file = file

	def get_code(self, fullname):
		if self._file is None:
			return super().get_code(fullname)
		# Un fisier primit are prioritate fata de copia de pe disc si de cache.
		fisier, self._file = self._file, None
		return self.source_to_code(fisier.read(), self.path)


class _CompiledLoader(machinery.SourcelessFileLoader):
	def __init__(self, name, path, file=None):
		super().__init__(name, path)
		self._file = file

	def get_data(self, path):
		if self._file is None:
			return super().get_data(path)
		fisier, self._file = self._file, None
		return fisier.read()


def _executa(spec):
	if spec is None or spec.loader is None:
		raise ImportError("Nu exista incarcator pentru modul")
	nume = spec.name
	precedent = sys.modules.get(nume, _LIPSA)
	try:
		if isinstance(precedent, ModuleType):
			modul = precedent
		else:
			modul = util.module_from_spec(spec)
		# Reincarcarea pastreaza dictionarul si referintele la acelasi obiect.
		modul.__name__ = nume
		modul.__loader__ = spec.loader
		modul.__package__ = spec.parent
		modul.__spec__ = spec
		if spec.has_location:
			modul.__file__ = spec.origin
			modul.__cached__ = spec.cached
		if spec.submodule_search_locations is not None:
			modul.__path__ = spec.submodule_search_locations
		sys.modules[nume] = modul
		spec.loader.exec_module(modul)
		return sys.modules[nume]
	except BaseException:
		# Se reface intrarea; efectele codului deja executat nu se pot anula.
		if precedent is _LIPSA:
			sys.modules.pop(nume, None)
		else:
			sys.modules[nume] = precedent
		raise


def _din_fisier(name, pathname, tip, file=None, dosar_pachet=None):
	cale = os.fsdecode(os.fspath(pathname))
	if tip == PY_SOURCE:
		incarcator = _SourceLoader(name, cale, file)
	elif tip == PY_COMPILED:
		incarcator = _CompiledLoader(name, cale, file)
	else:
		incarcator = machinery.ExtensionFileLoader(name, cale)
	if dosar_pachet is None:
		spec = util.spec_from_file_location(name, cale, loader=incarcator)
	else:
		spec = util.spec_from_file_location(name, cale, loader=incarcator,
			submodule_search_locations=[dosar_pachet])
	return _executa(spec)


def load_source(name, pathname, file=None):
	return _din_fisier(name, pathname, PY_SOURCE, file)


def load_compiled(name, pathname, file=None):
	# Validarea formatului si a versiunii .pyc ramane la importlib.
	return _din_fisier(name, pathname, PY_COMPILED, file)


def load_dynamic(name, pathname, file=None):
	# Argumentul file este ignorat de interfata veche pentru extensii native.
	return _din_fisier(name, pathname, C_EXTENSION)


def _initializator(path):
	for sufix, mod, tip in get_suffixes():
		cale = os.path.join(path, "__init__" + sufix)
		if os.path.isfile(cale):
			return cale, tip
	return None


def load_package(name, path):
	cale = os.fsdecode(os.fspath(path))
	if os.path.isdir(cale):
		gasit = _initializator(cale)
		if gasit is None:
			raise ImportError("Pachet fara __init__: %s" % cale, name=name)
		fisier, tip = gasit
		dosar = cale
	else:
		fisier = cale
		dosar = os.path.dirname(cale)
		tip = next((tip for sufix, mod, tip in get_suffixes()
			if cale.endswith(sufix)), None)
		if tip is None:
			raise ImportError("Tip necunoscut pentru pachet: %s" % cale, name=name)
	return _din_fisier(name, fisier, tip, dosar_pachet=dosar)


def load_module(name, file, pathname, description):
	sufix, mod, tip = description
	if mod and (not mod.startswith(("r", "U")) or "+" in mod):
		raise ValueError("Mod invalid de deschidere: %r" % mod)
	if tip in (PY_SOURCE, PY_COMPILED) and file is None:
		raise ValueError("Este necesar un fisier deschis pentru acest tip de modul")
	if tip == PY_SOURCE:
		return load_source(name, pathname, file)
	if tip == PY_COMPILED:
		return load_compiled(name, pathname, file)
	if tip == C_EXTENSION:
		return load_dynamic(name, pathname, file)
	if tip == PKG_DIRECTORY:
		return load_package(name, pathname)
	if tip == C_BUILTIN:
		return init_builtin(name)
	if tip == PY_FROZEN:
		return init_frozen(name)
	raise ImportError("Tip necunoscut pentru modul: %r" % tip, name=name)


def find_module(name, path=None):
	if not isinstance(name, str):
		raise TypeError("Numele modulului trebuie sa fie text")
	if path is not None and not isinstance(path, list):
		raise TypeError("Calea trebuie sa fie o lista sau None")
	if not name or "." in name or "/" in name or "\\" in name:
		raise ImportError("Numele trebuie sa fie al unui singur modul", name=name)
	if path is None:
		if is_builtin(name):
			return None, None, ("", "", C_BUILTIN)
		if is_frozen(name):
			return None, None, ("", "", PY_FROZEN)
		path = sys.path
	for dosar in path:
		if not isinstance(dosar, str):
			raise TypeError("Fiecare cale trebuie sa fie text")
		pachet = os.path.join(dosar, name)
		if os.path.isdir(pachet) and _initializator(pachet) is not None:
			return None, pachet, ("", "", PKG_DIRECTORY)
		for descriere in get_suffixes():
			sufix, mod, tip = descriere
			cale = pachet + sufix
			if os.path.isfile(cale):
				fisier = tokenize.open(cale) if tip == PY_SOURCE else open(cale, mod)
				return fisier, cale, descriere
	raise ImportError("Modul negasit: %s" % name, name=name)


def reload(module):
	if not isinstance(module, ModuleType):
		raise TypeError("Argumentul trebuie sa fie un modul")
	spec = getattr(module, "__spec__", None)
	nume = spec.name if spec is not None else module.__name__
	if sys.modules.get(nume) is not module:
		raise ImportError("Modulul nu este in sys.modules", name=nume)
	if spec is not None and isinstance(spec.loader,
		(_SourceLoader, _CompiledLoader, machinery.ExtensionFileLoader)):
		# Sursele incarcate prin cale pot fi in afara lui sys.path.
		return _executa(spec)
	return importlib.reload(module)


def new_module(name):
	return ModuleType(name)


def get_suffixes():
	return ([(sufix, "rb", C_EXTENSION) for sufix in machinery.EXTENSION_SUFFIXES]
		+ [(sufix, "r", PY_SOURCE) for sufix in machinery.SOURCE_SUFFIXES]
		+ [(sufix, "rb", PY_COMPILED) for sufix in machinery.BYTECODE_SUFFIXES])


def get_magic():
	return util.MAGIC_NUMBER


def get_tag():
	return sys.implementation.cache_tag


def cache_from_source(path, debug_override=None):
	if debug_override is None:
		return util.cache_from_source(path)
	return util.cache_from_source(path, optimization="" if debug_override else "1")


def source_from_cache(path):
	return util.source_from_cache(path)


# Blocarea si identificarea modulelor interne apartin interpretorului CPython.
acquire_lock = _imp.acquire_lock
release_lock = _imp.release_lock
lock_held = _imp.lock_held
is_builtin = _imp.is_builtin
is_frozen = _imp.is_frozen


def init_builtin(name):
	spec = machinery.BuiltinImporter.find_spec(name)
	return None if spec is None else _executa(spec)


def init_frozen(name):
	spec = machinery.FrozenImporter.find_spec(name)
	return None if spec is None else _executa(spec)


class NullImporter:
	def __init__(self, path_string):
		cale = os.fspath(path_string)
		if not cale or os.path.isdir(cale):
			raise ImportError("Calea nu este acceptata de NullImporter")

	def find_module(self, fullname, path=None):
		return None

	def find_spec(self, fullname, target=None):
		# importlib actual cauta aceasta metoda pentru o intrare din sys.path.
		return None
