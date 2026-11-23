# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsDreamboxIon.py: setarea "Memoria ecranului si accelerarea (Dreambox)" (ION1, forum 529).
#
# Numai pe Dreambox DM7080, DM820, DM900, DM920 si DM520 (configure.ac: HAVE_DREAMBOX_ION). Partea din C++
# (lib/gdi/fb.cpp) hotaraste la pornirea interfetei, dupa fisierul /etc/enigma2/hds-dreambox-ion:
#   - mereu, cu sau fara fisier (FBD5): daca memoria ecranului de la pornire e mai mica decat doua pagini
#     1920x1080, C++ o cere driverului inainte de singura mapare (prima pornire a interfetei dupa pornirea
#     receptorului nu se mai opreste);
#   - fara fisier (din fabrica): nimic altceva;
#   - cu fisier: ia memoria motorului 2D din /dev/ion si opreste curat interfata daca driverul muta memoria
#     ecranului; orice esec lasa purtarea de fara fisier;
#   - semnul /etc/enigma2/hds-dreambox-ion.pornire se scrie la pornire si se sterge de aici dupa 2 minute de
#     interfata vie (sau de C++ la iesirea curata); gasit la pornirea urmatoare = pornirea cu optiunea nu a
#     trait, iar C++ sterge singur fisierul setarii (fara bucla de reporniri pe un receptor la care nu se uita
#     nimeni);
#   - starea pornirii in /tmp/hds-dreambox-ion.stare: "pornit"/"oprit", un cod si detalii (jurnalul si asistenta).
# Randul se arata numai unde C++ a scris starea (SystemInfo["HdsDreamboxIon"]), deci numai pe aceste Dreambox-uri.
# Perechea web: randul e in ecranul "usage" din setup.xml, deci apare singur la /setari?id=usage (setari_web.py).
# Schimbarea se vede la urmatoarea pornire a interfetei.
#
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC il folosesc direct.

import os

FISIER_PORNIT = '/etc/enigma2/hds-dreambox-ion'
FISIER_SEMN = '/etc/enigma2/hds-dreambox-ion.pornire'
FISIER_STARE = '/tmp/hds-dreambox-ion.stare'
FEREASTRA_MS = 2 * 60 * 1000


def pornita_in_setari():
	"""True daca la urmatoarea pornire a interfetei calea noua are voie sa porneasca. Implicit: False."""
	return os.path.exists(FISIER_PORNIT)


def seteaza(pornita):
	"""Pune (pornita=True) sau scoate fisierul setarii. Pornirea scoate intai semnul vechi (alegerea omului porneste de
	la capat), apoi scrie fisierul atomic: intr-un fisier alaturat, golit pe disc, mutat peste nume; o scriere cazuta nu
	lasa niciodata fisierul setarii (pentru C++ simpla lui existenta inseamna Da). Intoarce True numai daca pe disc a
	ramas exact alegerea ceruta."""
	nou = FISIER_PORNIT + '.nou'
	try:
		if pornita:
			if os.path.exists(FISIER_SEMN):
				os.remove(FISIER_SEMN)
			if not os.path.exists(FISIER_PORNIT):
				with open(nou, 'w') as f:
					f.write('1\n')
					f.flush()
					os.fsync(f.fileno())
				os.rename(nou, FISIER_PORNIT)
		elif os.path.exists(FISIER_PORNIT):
			os.remove(FISIER_PORNIT)
	except Exception as eroare:
		print('[HdsDreamboxIon] nu pot schimba %s: %s' % (FISIER_PORNIT, eroare))
	try:
		if os.path.exists(nou):
			os.remove(nou)
	except Exception as eroare:
		print('[HdsDreamboxIon] nu pot sterge %s: %s' % (nou, eroare))
	return pornita_in_setari() == bool(pornita)


def stare(cale=None):
	"""Ce a hotarat interfata la pornire: {'stare': 'pornit'|'oprit'|None, 'cod', 'detalii'}."""
	try:
		with open(cale or FISIER_STARE) as f:
			randuri = f.read(1000).split('\n')
	except Exception:
		return {'stare': None, 'cod': '', 'detalii': ''}
	cuvant = randuri[0].strip() if randuri else ''
	cod = randuri[1].strip() if len(randuri) > 1 else ''
	detalii = randuri[2].strip() if len(randuri) > 2 else ''
	if cuvant not in ('pornit', 'oprit'):
		return {'stare': None, 'cod': cod, 'detalii': detalii}
	return {'stare': cuvant, 'cod': cod, 'detalii': detalii}


def disponibila(cale=None):
	"""True numai unde C++ (construit cu HAVE_DREAMBOX_ION) a scris starea la pornire."""
	return stare(cale)['stare'] is not None


def inchideFereastra():
	"""Interfata a trait 2 minute cu optiunea pornita: semnul se sterge, pornirea a mers."""
	try:
		if os.path.exists(FISIER_SEMN):
			os.remove(FISIER_SEMN)
		return True
	except Exception as eroare:
		print('[HdsDreamboxIon] nu pot sterge %s: %s' % (FISIER_SEMN, eroare))
		return False


_fereastra = []
TEXT_NESALVAT = 'Nu s-a putut salva setarea. Verifică spațiul liber și încearcă din nou.'


def _din_web():
	"""True cand salvarea vine din pagina web de setari (setari_web.seteaza): acolo un OSError din save() e prins,
	setarea se pune la loc si pagina spune ca nu s-a salvat. Pe televizor (ConfigListScreen.saveAll) un OSError ar
	opri interfata, deci acolo se arata un mesaj."""
	import sys
	f = sys._getframe(1)
	while f is not None:
		if f.f_code.co_filename.replace('\\', '/').endswith('/setari_web.py'):
			return True
		f = f.f_back
	return False


def _esec():
	"""Salvarea pe disc a cazut: in web OSError (raspunsul spune ca nu s-a salvat), altfel un mesaj pe televizor."""
	if _din_web():
		raise OSError(TEXT_NESALVAT)
	try:
		from Tools.Notifications import AddPopup
		from Screens.MessageBox import MessageBox
		AddPopup(_(TEXT_NESALVAT), MessageBox.TYPE_ERROR, 10, 'HdsDreamboxIon')  # noqa: F821
	except Exception as eroare:
		print('[HdsDreamboxIon] mesajul: %s' % eroare)


def salveaza(element, salveaza_valoarea):
	"""save() al setarii: fisierul de pe disc e adevarul. Daca valoarea aleasa difera de fisier, se scrie fisierul; daca
	scrierea cade, valoarea revine la ce e pe disc (si se salveaza asa), apoi esecul ajunge la om (_esec)."""
	ok = True
	if bool(element.value) != pornita_in_setari():
		ok = seteaza(bool(element.value))
		if not ok:
			element.value = pornita_in_setari()
	salveaza_valoarea()
	if not ok:
		_esec()


def pornesteFereastra():
	"""Daca C++ a scris semnul la aceasta pornire, il sterge dupa 2 minute (un ceas al buclei principale)."""
	del _fereastra[:]
	if not os.path.exists(FISIER_SEMN):
		return False
	try:
		from enigma import eTimer
		ceas = eTimer()
		ceas.callback.append(inchideFereastra)
		ceas.start(FEREASTRA_MS, True)
		_fereastra.append(ceas)
		return True
	except Exception as eroare:
		print('[HdsDreamboxIon] fereastra de 2 minute: %s' % eroare)
		return False


def initConfig():
	"""Din InitUsageConfig: config.usage.hds_dreambox_ion urmeaza fisierul (implicit Nu); salvarea din ecranul de setari
	sau din web pune ori scoate fisierul (salveaza). SystemInfo["HdsDreamboxIon"] arata randul numai pe Dreambox-urile
	cu aceasta cale."""
	from Components.config import config, ConfigYesNo

	class ConfigDreamboxIon(ConfigYesNo):
		def save(self):
			salveaza(self, lambda: ConfigYesNo.save(self))

	element = ConfigDreamboxIon(default=False)
	config.usage.hds_dreambox_ion = element
	element.value = pornita_in_setari()
	element.save()
	try:
		from Components.SystemInfo import SystemInfo
		SystemInfo["HdsDreamboxIon"] = disponibila()
	except Exception as eroare:
		print('[HdsDreamboxIon] SystemInfo: %s' % eroare)
	pornesteFereastra()
