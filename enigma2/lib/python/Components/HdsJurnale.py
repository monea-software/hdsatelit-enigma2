# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsJurnale.py: jurnalele sistemului si jurnalele de cadere. O singura logica pentru ecranele de pe televizor
# (Screens/LogManager.py: HdsLogManager, LogInfo, HdsLogManagerViewLog; Screens/HdsCrashlogAutoSubmit.py) si pentru
# paginile web /jurnale-sistem si /jurnale-cadere (Plugins/Extensions/HdsWebControl/jurnale_sistem_web.py).
#
# - initConfig(): config.logmanager (debugloglimit, daysloglimit), facute la prima folosire; pe televizor nu se schimba
#   din niciun ecran, ecranul "Informatii" le arata. initConfigCadere(): config.plugins.crashlogautosubmit
#   (sendAnonCrashlog, addNetwork), cu numele cerute de main/bsod.cpp, care le citeste direct din /etc/enigma2/settings.
#   Verificarea se face in config.content.items: ConfigSubsection.__getattr__ arunca KeyError, nu AttributeError.
# - listaJurnale(): fisierele din CALE_JURNALE, cele mai noi primele. citesteJurnal(): textul unui jurnal, cel mult
#   MARIME_MAX_AFISATA octeti de la sfarsit (ca pe televizor). stergeFisier(): stergerea, dupa intrebarea ecranului.
# - foldereCandidate(), cautaJurnaleCadere(): jurnalele enigma2_crash_*.log din CALE_PRINCIPALA (unde scrie bsod.cpp),
#   din orice dosar de sub /media si /run/media, din /home/root si din /tmp.
# - Pentru interfata web: caleJurnal(nume) si caleCadere(cale) dau calea numai pentru un fisier din lista de acum, fara
#   legaturi simbolice si fara cai in afara dosarelor de mai sus; faraSecrete() scoate randurile cu jetonul web sau cu
#   parole (aceeasi regula ca textul brut din modul sigur, Components/HdsModSigur.py).
#
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC il incarca fara receptor.

import os
import time

CALE_JURNALE = "/home/root/logs/"
# un jurnal mai mare se citeste numai pe ultima portiune
MARIME_MAX_AFISATA = 512 * 1024

# jurnalele de cadere: bsod.cpp scrie in CRASH_LOG_DIR = /home/root/logs (mytest.py la fel, hds-watchdog.py face dosarul)
CALE_PRINCIPALA = "/home/root/logs"
FOLDERE_DE_BAZA = ("/media", "/run/media")
FOLDERE_SUPLIMENTARE = ("/home/root", "/tmp")
PREFIX_CADERE = "enigma2_crash_"
SUFIX_CADERE = ".log"

LIMITA_DEPANARE_IMPLICITA = 5
ZILE_IMPLICITE = 14


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


# ------------------------------------------------------------------ setarile

def initConfig(config=None):
	"""config.logmanager: cate jurnale de depanare se pastreaza si dupa cate zile se sterg cele vechi."""
	if config is None:
		from Components.config import config
	if "logmanager" in config.content.items:
		return
	from Components.config import ConfigSubsection, ConfigNumber
	config.logmanager = ConfigSubsection()
	config.logmanager.debugloglimit = ConfigNumber(default=LIMITA_DEPANARE_IMPLICITA)
	config.logmanager.daysloglimit = ConfigNumber(default=ZILE_IMPLICITE)


def initConfigCadere(config=None):
	"""config.plugins.crashlogautosubmit: numele EXACTE cerute de bsod.cpp, nu se redenumesc."""
	if config is None:
		from Components.config import config
	if "crashlogautosubmit" in config.plugins.content.items:
		return
	from Components.config import ConfigSubsection, ConfigYesNo
	config.plugins.crashlogautosubmit = ConfigSubsection()
	config.plugins.crashlogautosubmit.sendAnonCrashlog = ConfigYesNo(default=True)
	config.plugins.crashlogautosubmit.addNetwork = ConfigYesNo(default=False)


def limite(config=None):
	"""(jurnale de depanare pastrate, zile) din config.logmanager, ca in ecranul "Informatii"."""
	if config is None:
		initConfig()
		from Components.config import config
	try:
		return int(config.logmanager.debugloglimit.value), int(config.logmanager.daysloglimit.value)
	except Exception:
		return LIMITA_DEPANARE_IMPLICITA, ZILE_IMPLICITE


# ------------------------------------------------------------------ jurnalele sistemului

def listaJurnale(dosar=None):
	"""[(mtime, nume, marime)] pentru fisierele din dosar, cele mai noi primele. Un dosar lipsa (emulator, receptor fara
	nimic scris inca) da lista goala."""
	dosar = dosar or CALE_JURNALE
	try:
		intrari = []
		for nume in os.listdir(dosar):
			cale = os.path.join(dosar, nume)
			if os.path.isfile(cale):
				intrari.append((os.path.getmtime(cale), nume, os.path.getsize(cale)))
		intrari.sort(reverse=True)
		return intrari
	except OSError:
		return []


def textRand(nume, marime, mtime):
	"""Randul din lista ecranului: numele, marimea in KB si data."""
	return "%s   (%.0f KB, %s)" % (nume, marime / 1024.0, time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime)))


def textData(mtime):
	return time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime))


def citesteJurnal(cale, limita=None):
	"""Textul unui jurnal; peste `limita` octeti numai ultima portiune, cu un semn la inceput (ca pe televizor)."""
	limita = MARIME_MAX_AFISATA if limita is None else limita
	try:
		marime = os.path.getsize(cale)
		with open(cale, "r", encoding="utf-8", errors="replace") as f:
			if marime > limita:
				f.seek(marime - limita)
				continut = _("[... începutul jurnalului e omis, fișier prea mare ...]\n") + f.read()
			else:
				continut = f.read()
	except OSError as eroare:
		continut = _("Nu am putut citi fișierul: %s") % eroare
	return continut or _("(jurnal gol)")


def stergeFisier(cale):
	"""Sterge fisierul (dupa intrebarea ecranului); True daca nu mai exista."""
	try:
		os.remove(cale)
	except OSError:
		pass
	return not os.path.lexists(cale)


def informatii(jurnale=None, config=None):
	"""(dosarul, cate fisiere, MB in total, jurnale de depanare pastrate, zile) pentru ecranul "Informatii"."""
	jurnale = listaJurnale() if jurnale is None else jurnale
	total = sum(marime for _m, _n, marime in jurnale)
	pastrate, zile = limite(config)
	return CALE_JURNALE, len(jurnale), total / (1024.0 * 1024.0), pastrate, zile


# ------------------------------------------------------------------ jurnalul sistemului si serviciile (0.6.7)

FISIER_SYSLOG = "/etc/syslog-startup.conf"


def rotireJurnal(cale=None):
	"""(fisierul, KB pe fisier, fisiere vechi) din /etc/syslog-startup.conf (busybox syslogd), sau None"""
	try:
		with open(cale or FISIER_SYSLOG, encoding="utf-8", errors="replace") as f:
			text = f.read(8192)
	except (OSError, IOError):
		return None
	v = {}
	for rand in text.splitlines():
		cheie, semn, rest = rand.partition("=")
		if semn and not cheie.strip().startswith("#"):
			v[cheie.strip()] = rest.split("#", 1)[0].strip()
	try:
		return v.get("LOGFILE", ""), int(v.get("ROTATESIZE", "0")), int(v.get("ROTATEGENS", "0"))
	except ValueError:
		return None


def textJurnalSistem(cale=None):
	"""Unde se pastreaza jurnalul sistemului, pe intelesul omului"""
	r = rotireJurnal(cale)
	if not r or not r[0]:
		return _("Jurnalul sistemului nu se păstrează pe disc în această imagine.")
	fisier, kb, vechi = r
	return _("%s, păstrat pe disc: %d fișiere vechi de câte %d KB; după o oprire necurată, copia lui în "
		"messages.cadere.") % (fisier, vechi, kb)


def randuriInformatii(cale_syslog=None, servicii=None):
	"""[(eticheta, textul)] in plus fata de informatii(): jurnalul sistemului si serviciile de sistem (starea
	paznicului, Components/HdsPaznic.stareServicii)"""
	if servicii is None:
		try:
			from Components import HdsPaznic
			servicii = HdsPaznic.stareServicii()["text"]
		except Exception:
			servicii = ""
	rez = [(_("Jurnalul sistemului"), textJurnalSistem(cale_syslog))]
	if servicii:
		rez.append((_("Serviciile de sistem"), servicii))
	return rez


# ------------------------------------------------------------------ jurnalele de cadere

def asiguraDirectorPrincipal():
	"""Face CALE_PRINCIPALA daca lipseste (la deschiderea ecranului); nu cade niciodata."""
	try:
		if not os.path.isdir(CALE_PRINCIPALA):
			os.makedirs(CALE_PRINCIPALA, exist_ok=True)
	except OSError:
		pass


def foldereCandidate():
	candidate = [CALE_PRINCIPALA]
	for baza in FOLDERE_DE_BAZA:
		try:
			for nume in os.listdir(baza):
				cale = os.path.join(baza, nume)
				if os.path.isdir(cale) and cale not in candidate:
					candidate.append(cale)
		except OSError:
			pass
	for cale in FOLDERE_SUPLIMENTARE:
		if cale not in candidate:
			candidate.append(cale)
	return candidate


def esteJurnalCadere(nume):
	return nume.startswith(PREFIX_CADERE) and nume.endswith(SUFIX_CADERE)


def cautaJurnaleCadere(foldere=None):
	"""[(cale, nume, marime, mtime)] pentru jurnalele enigma2_crash_*.log din toate dosarele candidate, cele mai noi
	primele. Un dosar care nu se poate citi nu opreste cautarea in celelalte."""
	gasite = []
	vazute = set()
	for folder in (foldereCandidate() if foldere is None else foldere):
		try:
			nume_fisiere = os.listdir(folder)
		except OSError:
			continue
		for nume in nume_fisiere:
			if not esteJurnalCadere(nume):
				continue
			cale = os.path.join(folder, nume)
			if cale in vazute:
				continue
			vazute.add(cale)
			try:
				stare = os.stat(cale)
			except OSError:
				continue
			gasite.append((cale, nume, stare.st_size, stare.st_mtime))
	gasite.sort(key=lambda t: t[3], reverse=True)
	return gasite


# ------------------------------------------------------------------ paza pentru interfata web

def _inauntru(cale, dosar):
	real = os.path.realpath(cale)
	baza = os.path.realpath(dosar)
	return real == baza or real.startswith(baza.rstrip(os.sep) + os.sep)


def caleJurnal(nume, dosar=None, jurnale=None):
	"""Calea jurnalului `nume` din CALE_JURNALE, numai daca e in lista de acum, nu e o legatura simbolica si ramane in
	dosar; altfel None."""
	dosar = dosar or CALE_JURNALE
	if not nume or "/" in nume or "\\" in nume or nume in (".", "..") or "\x00" in nume:
		return None
	jurnale = listaJurnale(dosar) if jurnale is None else jurnale
	if nume not in [n for _m, n, _s in jurnale]:
		return None
	cale = os.path.join(dosar, nume)
	if os.path.islink(cale) or not _inauntru(cale, dosar) or not os.path.isfile(cale):
		return None
	return cale


def caleCadere(cale, gasite=None):
	"""Calea unui jurnal de cadere, numai daca e in lista de acum (cautaJurnaleCadere), nu e o legatura simbolica si
	dosarul lui e unul dintre dosarele candidate; altfel None."""
	if not cale or "\x00" in cale or ".." in cale.replace(os.sep, "/").split("/"):
		return None
	gasite = cautaJurnaleCadere() if gasite is None else gasite
	if cale not in [g[0] for g in gasite]:
		return None
	dosar = os.path.dirname(cale)
	if os.path.islink(cale) or not os.path.isfile(cale) or not _inauntru(cale, dosar):
		return None
	if not esteJurnalCadere(os.path.basename(cale)):
		return None
	return cale


def faraSecrete(text):
	"""Fara randurile cu jetonul web, parole, coduri PIN, cheia Wi-Fi si alte chei (regula modului sigur)."""
	from Components.HdsModSigur import _faraSecrete
	return _faraSecrete(text)
