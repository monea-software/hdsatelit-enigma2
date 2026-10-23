# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsEpgSalvare.py: unde se pastreaza ghidul (EPG) intre porniri si cand se scrie.
#
# Cauza, citita pe receptor: config.misc.epgcache_filename era „/hdd/epg.dat”, adica pe stickul sau discul montat in
# /media/hdd. Fara el (receptoarele fara disc: /media e in memorie si /media/hdd nu exista) eEPGCache::save din
# lib/dvb/epgcache.cpp nu putea scrie, deci ghidul se pierdea la fiecare repornire a interfetei. Cu stick, load()
# stergea fisierul cum il citea: cat merge interfata nu exista epg.dat nicaieri, iar o oprire necurata (cadere, paznicul,
# init 4, curent taiat) pierdea tot ghidul.
# Acum:
# - CALE (/home/root/epg.dat), pe memoria interna, mereu acolo. Nu in /etc/enigma2: copia setarilor
#   (Components/HdsCopieSetari.py) ia tot dosarul, deci si cativa MB de ghid. O cale aleasa de om in settings ramane;
# - la pornire, cand calea nu are fisier, un ghid ramas pe calea veche (CALE_VECHE, de la versiunea dinainte) se muta
#   pe ea (muta_vechiul), altfel ghidul s-ar pierde o data, la repornirea de dupa actualizare;
# - scrierea si citirea fisierului (C++): in <cale>.nou si rename peste el, cu fsync; citirea nu-l mai sterge;
# - cand se scrie: la iesirea interfetei (ca pana acum: repornire, oprire, repornirea receptorului din meniu), la
#   intrarea in standby si o data la SALVARE_ORE ore (eEPGCache.requestSave, pe firul ghidului). Nu la fiecare minut:
#   o scriere are cativa MB (masurat pe receptor: 602112 o si 6873088 o).
# Modulul nu importa nimic din enigma la incarcare (probele de pe PC: teste/test_reparatii_tv_0320.py).

import os
import shutil

CALE = "/home/root/epg.dat"
CALE_VECHE = "/hdd/epg.dat"
SALVARE_ORE = 6

_stare = {"ceas": None, "standby": False}


def _jurnal(text):
	print("[HdsEpgSalvare] %s" % text)


def muta_vechiul(cale, vechi=CALE_VECHE):
	"""Ghidul scris de versiunea dinainte pe calea veche se muta pe `cale`, o singura data: numai cand `cale` nu are
	fisier si cea veche are. Copia se face in <cale>.nou, cu fsync, si se muta peste (os.replace), apoi cel vechi se
	sterge. -> True daca s-a mutat. Nu arunca: pornirea nu depinde de el."""
	try:
		if not cale or os.path.realpath(cale) == os.path.realpath(vechi):
			return False
		if os.path.exists(cale) or not os.path.isfile(vechi):
			return False
		dosar = os.path.dirname(cale)
		if dosar and not os.path.isdir(dosar):
			return False
		nou = cale + ".nou"
		shutil.copyfile(vechi, nou)
		with open(nou, "rb+") as f:
			os.fsync(f.fileno())
		os.replace(nou, cale)
		try:
			os.remove(vechi)
		except OSError as e:
			_jurnal("cel vechi ramane: %s" % e)
		_jurnal("ghidul mutat de pe %s pe %s" % (vechi, cale))
		return True
	except Exception as e:
		_jurnal("mutarea ghidului vechi: %r" % (e,))
		try:
			os.remove(cale + ".nou")
		except OSError:
			pass
		return False


def salveaza():
	"""Cere firului ghidului sa scrie fisierul acum (lib/dvb/epgcache.cpp, Message::save). -> True daca s-a cerut;
	False fara fir pornit (ora inca nevalida) sau cu un enigma fara requestSave."""
	try:
		from enigma import eEPGCache
		cache = eEPGCache.getInstance()
		cere = getattr(cache, "requestSave", None)
		if cere is None:
			return False
		return bool(cere())
	except Exception as e:
		_jurnal("salvarea: %r" % (e,))
		return False


def _laCeas():
	if salveaza():
		_jurnal("ghidul se scrie (o data la %d ore)" % SALVARE_ORE)


def _laStandby(element=None):
	# config.misc.standbyCounter creste la fiecare intrare in standby: atunci se scrie ghidul (dupa standby curentul se
	# taie des din priza)
	if salveaza():
		_jurnal("ghidul se scrie (standby)")


def porneste():
	"""Scrierea rara a ghidului: o data la SALVARE_ORE ore si la intrarea in standby. Chemata o data, din mytest.py."""
	try:
		from enigma import eTimer
		if _stare["ceas"] is None:
			ceas = eTimer()
			ceas.callback.append(_laCeas)
			ceas.start(SALVARE_ORE * 3600 * 1000, False)
			_stare["ceas"] = ceas
	except Exception as e:
		_jurnal("ceasul: %r" % (e,))
	try:
		from Components.config import config
		if not _stare["standby"]:
			config.misc.standbyCounter.addNotifier(_laStandby, initial_call=False)
			_stare["standby"] = True
	except Exception as e:
		_jurnal("standby: %r" % (e,))
