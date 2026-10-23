# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsDecodare.py: inregistrarile "Decodează mai târziu" (logica comuna pentru televizor si interfata web).
#
# O inregistrare marcata asa nu se da modulului de acces conditionat: pachetele ajung pe disc criptate, neschimbate,
# impreuna cu PID-urile ECM din PMT, EIT si TDT (lib/service/servicedvbrecord.cpp, setDecodareMaiTarziu). Langa fisier
# se scrie <inregistrare>.ts.hdsdecodare (randuri cheie=valoare, ASCII): versiune, stare (criptat pana la decodare),
# ecm=pastrat, serviciu, program, pmt_pid, caid (sistemele), ecm_pid (perechi PID:CAID), pid_inregistrate,
# pe_televizor_la_pornire (1: acelasi serviciu era pe televizor la pornire, deci driverul a legat cheia lui si de
# canalele inregistrarii: o parte din fisier poate fi deja clara). Programul de decodare il citeste si il pune la zi.
#
# ASCUNS PANA LA PROGRAMUL DE DECODARE: alegerea (fereastra inregistrarii, setarea generala, pagina web, /api/timeradd),
# semnul din lista filmelor si mesajul de la pornire apar si se aplica numai daca pe receptor exista programul de
# decodare (CALE_PROGRAM); fara el totul se poarta ca inainte, iar un temporizator marcat se inregistreaza decriptat.
# Inregistrarea pornita de mana (REC, Screens/InfoBarGenerics.py) ramane mereu "Decriptează acum".
#
# Fisierul nu importa nimic din enigma2 la incarcare (probele de pe PC il incarca direct).

import os

# programul de decodare (lotul lui il pune aici); fara el alegerea nu exista
CALE_PROGRAM = "/usr/bin/hds-decodare"
# fisierul alaturat al inregistrarii (lib/service/servicedvbrecord.cpp, scrieDecodare)
SUFIX = ".hdsdecodare"
# starea scrisa la inregistrare; programul de decodare o schimba in STARE_DECODAT (sau sterge fisierul) la sfarsit
STARE_CRIPTAT = "criptat"
STARE_DECODAT = "decodat"
# valorile alegerii (config.recording.hds_decodare, timers.xml, pagina web, /api/timeradd)
ACUM = "acum"
MAI_TARZIU = "maitarziu"
# cel mult atatia octeti se citesc din fisierul alaturat
MAX_FISIER = 8192


def N_(text):
	"""Marcheaza textul pentru xgettext; traducerea se face la folosire."""
	return text


def _(text):
	try:
		import builtins
		return builtins.__dict__.get("_", lambda s: s)(text)
	except Exception:
		return text


TXT_RAND = N_("Decriptarea")
TXT_ACUM = N_("Decriptează acum")
TXT_MAI_TARZIU = N_("Decodează mai târziu")
TXT_AJUTOR = N_("Decriptează acum: înregistrarea se decriptează cât se înregistrează, ca până acum. Decodează mai "
	"târziu: se salvează criptată, cu tot ce trebuie pentru decodare, iar receptorul o decodează mai târziu, când e în "
	"așteptare. Contează numai la canalele criptate.")
TXT_SEMN = N_("Se decodează mai târziu")
TXT_PORNIRE = N_("Înregistrarea aceasta e încă criptată: se decodează mai târziu, când receptorul e în așteptare. O "
	"poți porni după decodare.")


def exista(cale=None):
	"""Programul de decodare e pe receptor (un fisier executabil)."""
	return os.access(cale or CALE_PROGRAM, os.X_OK) and os.path.isfile(cale or CALE_PROGRAM)


def alegeri():
	"""[(valoare, textul tradus)] pentru alegerea din fereastra inregistrarii si din setari."""
	return [(ACUM, _(TXT_ACUM)), (MAI_TARZIU, _(TXT_MAI_TARZIU))]


def implicit(config=None):
	"""Alegerea unui temporizator nou: True numai cu programul de decodare si setarea generala pe "mai tarziu"."""
	if not exista():
		return False
	try:
		if config is None:
			from Components.config import config
		return config.recording.hds_decodare.value == MAI_TARZIU
	except (AttributeError, KeyError, ImportError):
		return False


def seAplica(t):
	"""Temporizatorul `t` se inregistreaza criptat: marcat, nu doar comutare, programul de decodare exista."""
	return bool(getattr(t, "hdsDecodareMaiTarziu", False)) and not getattr(t, "justplay", False) and exista()


def dinCerere(text):
	"""Valoarea venita din web sau din aplicatii: True (mai tarziu), False (acum) sau None (lipsa ori necunoscuta)."""
	text = (text or "").strip().lower()
	if text in (MAI_TARZIU, "mai_tarziu", "1"):
		return True
	if text in (ACUM, "0"):
		return False
	return None


def text(mai_tarziu):
	return MAI_TARZIU if mai_tarziu else ACUM


def caleDisc(cale):
	"""Calea unui serviciu (textul UTF-8 dat de enigma2) ca nume de fisier pentru Python (enigma2 ruleaza cu locale-ul
	C: un nume cu diacritice trece prin octetii lui), ca Screens/MovieSelection.caleDisc."""
	try:
		return os.fsdecode(cale.encode("utf-8", "surrogateescape"))
	except (UnicodeError, AttributeError):
		return cale


def fisierAlaturat(cale_ts):
	return cale_ts + SUFIX


def citeste(cale_ts):
	"""{cheie: valoare} din fisierul alaturat al inregistrarii, sau None daca lipseste ori nu se poate citi."""
	try:
		with open(fisierAlaturat(cale_ts), "rb") as f:
			date = f.read(MAX_FISIER)
	except (OSError, IOError, TypeError, ValueError):
		return None
	rez = {}
	for rand in date.decode("ascii", "replace").splitlines():
		rand = rand.strip()
		if not rand or rand.startswith("#") or "=" not in rand:
			continue
		cheie, valoare = rand.split("=", 1)
		rez[cheie.strip()] = valoare.strip()
	return rez


def deDecodat(cale_ts):
	"""Inregistrarea `cale_ts` asteapta decodarea: programul exista, fisierul alaturat exista si starea nu e "decodat".
	Fara program: False (totul ca inainte)."""
	if not cale_ts or not exista():
		return False
	date = citeste(cale_ts)
	return date is not None and date.get("stare", STARE_CRIPTAT) != STARE_DECODAT


def peTelevizor(ref_televizor, ref_inregistrare):
	"""Acelasi serviciu (referintele comparate fara nume si cale) e pe televizor."""
	def cheie(ref):
		if ref is None:
			return None
		try:
			text_ref = ref.toCompareString() if hasattr(ref, "toCompareString") else str(ref)
		except Exception:
			return None
		parti = text_ref.split(":")
		return ":".join(x.upper() for x in parti[:10]) if len(parti) >= 10 else None
	a, b = cheie(ref_televizor), cheie(ref_inregistrare)
	return a is not None and a == b


def aplica(serviciu_inregistrare, pe_televizor=False):
	"""Marcheaza inregistrarea (iRecordableService.setDecodareMaiTarziu): True daca serviciul a primit semnul."""
	pune = getattr(serviciu_inregistrare, "setDecodareMaiTarziu", None)
	if pune is None:
		return False
	try:
		return pune(True, bool(pe_televizor)) == 0
	except Exception as eroare:
		print("[HdsDecodare] setDecodareMaiTarziu: %s" % eroare)
		return False
