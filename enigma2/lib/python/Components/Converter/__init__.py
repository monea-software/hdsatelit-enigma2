# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Numele de convertoare si randatoare pe care imaginea le da fara fisier propriu (clasele din HdsConvertoareStraine.py si
# Renderer/HdsRandatoareStraine.py: CryptoInfo, VAudioInfo, ChannelNumber, Cover...) se vad la import mereu, nu numai sub o
# tema externa: un plugin cu skin in cod sau cu "from Components.Converter.CryptoInfo import CryptoInfo" merge si sub tema
# HD Satelit, ca in imaginile OE-Alliance.
#
# Cautatorul sta la coada lui sys.meta_path: un fisier adevarat (al imaginii sau adus de o tema) trece mereu inainte, deci un
# pachet de tema care aduce acelasi nume se instaleaza fara conflict si ramane al lui. Raspunde numai pentru
# Components.Converter.<Nume> si Components.Renderer.<Nume>, numai cand modulul nostru are o clasa cu acel nume, scrisa in el
# si derivata din Converter / Renderer. Modulul cu clasele se incarca abia la primul nume care nu e fisier.
import sys

_MODULE = {"Components.Converter": "HdsConvertoareStraine", "Components.Renderer": "HdsRandatoareStraine"}
_BAZE = {"Components.Converter": ("Components.Converter.Converter", "Converter"), "Components.Renderer": ("Components.Renderer.Renderer", "Renderer")}
# pachetele al caror modul nu s-a putut incarca: nu se mai incearca (pluginurile intreaba des nume care nu exista)
_CAZUTE = set()


def clasaNoastra(pachet, nume):
	"""Clasa data de modulul nostru pentru pachet.nume, sau None (nume strain, ascuns sau modulul nu se poate incarca)."""
	modul = _MODULE.get(pachet)
	if modul is None or pachet in _CAZUTE or not nume or not nume[0].isalpha() or nume == modul or nume.startswith("Hds"):
		return None
	import importlib
	try:
		sursa = importlib.import_module(pachet + "." + modul)
		baza = getattr(importlib.import_module(_BAZE[pachet][0]), _BAZE[pachet][1])
	except Exception as e:
		_CAZUTE.add(pachet)
		print("[Components] %s.%s: %s (numele OE-Alliance fara fisier nu se mai cauta)" % (pachet, nume, e))
		return None
	clasa = sursa.__dict__.get(nume)
	if isinstance(clasa, type) and issubclass(clasa, baza) and clasa.__module__ == sursa.__name__:
		return clasa
	return None


class NumeOea(object):
	"""Cautatorul de la coada lui sys.meta_path (vezi antetul)."""

	@classmethod
	def find_spec(cls, name, path=None, target=None):
		pachet, _p, nume = name.rpartition(".")
		if pachet not in _MODULE or clasaNoastra(pachet, nume) is None:
			return None
		from importlib.machinery import ModuleSpec
		return ModuleSpec(name, cls)

	@classmethod
	def create_module(cls, spec):
		return None

	@classmethod
	def exec_module(cls, modul):
		pachet, _p, nume = modul.__name__.rpartition(".")
		clasa = clasaNoastra(pachet, nume)
		if clasa is None:
			raise ImportError("No module named %s" % modul.__name__)
		setattr(modul, nume, clasa)
		# numele de nivel de modul ale fisierului OE-Alliance, tinute de clasa noastra ca atribute (lotul TOT, 12.11.2026):
		# "from Components.Converter.PliExtraInfo import codec_data" (4 teme din feedurile OE-Alliance); o clasa poate cere si altele
		# prin _numeDeModul = ("nume", ...)
		for extra in ("codec_data",) + tuple(getattr(clasa, "_numeDeModul", ())):
			if extra in clasa.__dict__:
				setattr(modul, extra, clasa.__dict__[extra])


def porneste():
	if NumeOea not in sys.meta_path:
		sys.meta_path.append(NumeOea)


porneste()
