# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""O proba completa a iesirii si un cititor de fundal fara asteptare in interfata."""

import copy
import os
import re
import threading
import time

from Components.HdsHdmiDate import Perechi, evenimente

try:
	_
except NameError:
	from gettext import gettext as _


TIMP_LOT = 2.0
VARSTA_MAXIMA = 15.0
MAX_OCTETI = 65536
MODURI = ('videomode', 'videomode_50hz', 'videomode_60hz', 'videomode_24hz')
EVENIMENTE = ('HPD', 'RsenCon', 'UnHPD', 'RsenDis')
_ULTIMA = None
_LACAT_CACHE = threading.Lock()


def _text(radacina, relativ):
	try:
		with open(os.path.join(radacina or '/', relativ), 'rb') as fisier:
			return fisier.read(MAX_OCTETI).decode('utf-8', 'replace')
	except (OSError, IOError, UnicodeError):
		return None


def _da(valoare):
	valoare = (valoare or '').strip().upper()
	if valoare in ('YES', 'Y', 'TRUE', '1', 'ON', 'ENABLE', 'ENABLED', 'CONNECTED'):
		return True
	if valoare in ('NO', 'N', 'FALSE', '0', 'OFF', 'DISABLE', 'DISABLED', 'DISCONNECTED'):
		return False
	return None


def _dinSectiune(perechi, cheie, sectiune):
	# val() permite si o alta sectiune; aici conteaza strict sursa valorii.
	for nume, valoare in perechi.din_sectiune(sectiune):
		if nume.strip().lower() == cheie.lower():
			return valoare.strip() or None
	return None


def _legatura(text):
	perechi = Perechi(text)
	contori = evenimente(text)
	return {
		'conectat': _da(_dinSectiune(perechi, 'HotPlug', 'HWStatus')),
		'rsen': _da(_dinSectiune(perechi, 'Rsen', 'HWStatus')),
		'evenimente': dict((cheie, contori[cheie]) for cheie in EVENIMENTE if cheie in contori),
	}


def _gp0(text):
	"""Dreptunghiul Output al GP0; dreptunghiurile altor straturi se ignora."""
	if not text:
		return None
	sectiune = None
	for rand in text.splitlines():
		grup = re.search(r'\bGP\s*([0-9]+)\b', rand, re.I)
		if grup:
			sectiune = int(grup.group(1))
		elif re.match(r'^\s*[-=]{3,}.*\b(?:GFX|HD|SD|LAYER)\s*[0-9]+\b', rand, re.I):
			sectiune = None
		if sectiune != 0:
			continue
		valoare = re.search(r'\bOutput(?:Rect)?(?:\s*\([^)]*\))?\s*[:=]\s*(.*)', rand, re.I)
		if valoare:
			numere = re.findall(r'(?<![\w.])-?\d+(?![\w.])', valoare.group(1))
			if len(numere) == 4:
				return tuple(int(numar) for numar in numere)
	return None


def _gol(inceput=None):
	return {
		'conectat': None, 'rsen': None, 'evenimente': {},
		'disp': None, 'out_color': None, 'tmds': None, 'gp0': None,
		'moduri': dict((nume, None) for nume in MODURI),
		'msp': False, 'complet': False, 'proaspat': False,
		'inceput': inceput, 'sfarsit': None,
	}


def citeste(radacina='/'):
	"""Citeste numai nodurile necesare; campurile absente raman necunoscute."""
	inceput = time.monotonic()
	proba = _gol(inceput)
	proba['msp'] = os.path.isdir(os.path.join(radacina or '/', 'proc/msp'))
	if proba['msp']:
		hdmi = _text(radacina, 'proc/msp/hdmi0')
		prima = _legatura(hdmi)
		proba.update(prima)
		proba['legatura_inceput'] = prima
		perechi = Perechi(hdmi)
		proba['out_color'] = _dinSectiune(perechi, 'OutColorSpace', 'APPAttr')
		proba['tmds'] = _dinSectiune(perechi, 'TMDSMode', 'HWStatus')
		disp = Perechi(_text(radacina, 'proc/msp/disp1'), una_pe_rand=True)
		if 'HDMI0' not in (disp.val('Interface') or '').upper():
			disp = Perechi(_text(radacina, 'proc/msp/disp0'), una_pe_rand=True)
		if 'HDMI0' in (disp.val('Interface') or '').upper():
			proba['disp'] = disp.val('Formt/DispMode') or disp.val('Formt') or disp.val('DispMode') or None
		proba['gp0'] = _gp0(_text(radacina, 'proc/msp/hifb0'))
	else:
		for nod in ('proc/stb/hdmi/hotplug', 'proc/stb/hdmi/connected', 'proc/stb/video/hdmi_hotplug'):
			proba['conectat'] = _da(_text(radacina, nod))
			if proba['conectat'] is not None:
				break
	for nume in MODURI:
		valoare = _text(radacina, 'proc/stb/video/' + nume)
		proba['moduri'][nume] = valoare.strip() if valoare is not None else None
	if proba['msp']:
		ultima_legatura = _legatura(_text(radacina, 'proc/msp/hdmi0'))
		proba['legatura_sfarsit'] = ultima_legatura
		proba['tranzitie'] = prima != ultima_legatura
		proba.update(ultima_legatura)
		proba['complet'] = bool(proba['disp'] and proba['out_color'] and proba['tmds']
			and proba['gp0'] is not None and proba['conectat'] is not None
			and proba['rsen'] is not None and not proba['tranzitie'])
	else:
		proba['complet'] = proba['conectat'] is not None and bool(proba['moduri']['videomode'])
	proba['sfarsit'] = time.monotonic()
	proba['proaspat'] = proba['sfarsit'] - inceput <= TIMP_LOT
	return proba


class Cititor(object):
	"""Un singur lot activ, inclusiv cand o citire ramane blocata in driver."""

	def __init__(self, citire=citeste):
		self._citire = citire
		self._lacat = threading.Lock()
		self._fir = None
		self._inceput = None
		self._rezultat = None

	def porneste(self):
		with self._lacat:
			if self._fir is not None and self._fir.is_alive():
				return False
			if self._rezultat is not None:
				return False
			self._inceput = time.monotonic()
			self._fir = threading.Thread(target=self._citeste, name='HdsStareOsd')
			self._fir.daemon = True
			self._fir.start()
		return True

	def _citeste(self):
		try:
			proba = self._citire()
			proba = copy.deepcopy(proba) if isinstance(proba, dict) else _gol(self._inceput)
		except Exception:
			proba = _gol(self._inceput)
		sfarsit = time.monotonic()
		if proba.get('inceput') is None:
			proba['inceput'] = self._inceput
		if proba.get('sfarsit') is None:
			proba['sfarsit'] = sfarsit
		if sfarsit - self._inceput > TIMP_LOT:
			proba['proaspat'] = False
		with self._lacat:
			self._rezultat = proba

	def preia(self):
		with self._lacat:
			proba, self._rezultat = self._rezultat, None
		return proba

	def expirat(self, acum):
		with self._lacat:
			return bool(self._fir is not None and self._fir.is_alive() and self._rezultat is None
				and acum - self._inceput > TIMP_LOT)


def actualizeaza(proba):
	"""Publica o copie a lotului terminat, fara citiri suplimentare."""
	global _ULTIMA
	if not isinstance(proba, dict):
		return
	with _LACAT_CACHE:
		_ULTIMA = copy.deepcopy(proba)


def ultima():
	"""Copia ultimei probe sau None; varsta se masoara de la sfarsitul lotului."""
	with _LACAT_CACHE:
		proba = copy.deepcopy(_ULTIMA)
	if proba is not None:
		sfarsit = proba.get('sfarsit')
		proba['varsta'] = max(0.0, time.monotonic() - sfarsit) if sfarsit is not None else None
		if proba['varsta'] is None or proba['varsta'] > VARSTA_MAXIMA:
			proba['proaspat'] = False
	return proba


def textStare(proba):
	"""Rand compact pentru compararea iesirii inainte si dupa o schimbare."""
	if not proba:
		return _('Starea ieșirii nu este disponibilă')
	necunoscut = _('necunoscut')
	moduri = proba.get('moduri') or {}
	gp0 = proba.get('gp0')
	contori = proba.get('evenimente') or {}
	legatura = {True: _('da'), False: _('nu'), None: necunoscut}
	return _('mod %(mod)s | disp %(disp)s | OutColorSpace %(culoare)s | TMDS %(tmds)s | GP0 Output %(gp0)s | rate 50:%(hz50)s 60:%(hz60)s 24:%(hz24)s | hpd %(hpd)s | rsen %(rsen)s | proaspat %(proaspat)s complet %(complet)s tranzitie %(tranzitie)s | HPD %(HPD)s UnHPD %(UnHPD)s RsenCon %(RsenCon)s RsenDis %(RsenDis)s') % {
		'mod': moduri.get('videomode') or necunoscut,
		'disp': proba.get('disp') or necunoscut,
		'culoare': proba.get('out_color') or necunoscut,
		'tmds': proba.get('tmds') or necunoscut,
		'gp0': ','.join(str(n) for n in gp0) if gp0 is not None else necunoscut,
		'hz50': moduri.get('videomode_50hz') or necunoscut,
		'hz60': moduri.get('videomode_60hz') or necunoscut,
		'hz24': moduri.get('videomode_24hz') or necunoscut,
		'hpd': legatura.get(proba.get('conectat'), necunoscut),
		'rsen': legatura.get(proba.get('rsen'), necunoscut),
		'proaspat': legatura.get(proba.get('proaspat'), necunoscut),
		'complet': legatura.get(proba.get('complet'), necunoscut),
		'tranzitie': legatura.get(proba.get('tranzitie'), necunoscut),
		'HPD': contori.get('HPD', necunoscut),
		'UnHPD': contori.get('UnHPD', necunoscut),
		'RsenCon': contori.get('RsenCon', necunoscut),
		'RsenDis': contori.get('RsenDis', necunoscut),
	}
