# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsDosareInregistrari.py: dosarele inregistrarilor ("Recording Locations"). O singura logica pentru ecranul de pe
# televizor (Screens/RecordPaths.py, RecordPathsSettings; entryID RecordPaths) si pentru pagina web
# /locuri-inregistrari (Plugins/Extensions/HdsWebControl/disc_web.py).
#
# Randurile ecranului (dupa config.usage.setup_level, ca pe televizor):
#   - Expert: "Default movie location" (config.usage.default_path), "Timer record location" (timer_path), "Instant
#     record location" (instantrec_path); altfel numai "Movie location" (default_path);
#   - mereu "Timeshift location" (timeshift_path).
# Alegerile fiecarui rand: dosarele tinute minte (config.movielist.videodirs, la timeshift
# config.usage.allowed_timeshift_paths) plus valoarea de acum; la temporizator si la inregistrarea imediata, inainte, si
# cele trei stiluri <Default movie location>, <Current movielist location>, <Last timer location>.
# Un dosar nou se alege navigand (Screens/LocationBox.py, MovieLocationBox si TimeshiftLocationBox): radacina e lista
# discurilor montate (harddiskmanager.getMountedPartitions, ca FileList), fara dosarele sistemului (DOSARE_OPRITE,
# aceleasi ca inhibitDirs din LocationBox); dosarul ales se adauga in lista tinuta minte (autoAdd). La timeshift, sub
# MIN_LIBER_TIMESHIFT_MB liberi se cere o confirmare (minFree din TimeshiftLocationBox, aceeasi limita ca in
# servicedvb.cpp). Un dosar in care nu se poate scrie nu se pune (checkReadWriteDir). Salvarea: valorile puse in
# config.usage.* si save() fiecare (RecordPathsSettings.save).
# Din meniul navigatorului (editDir): dosar nou in dosarul de acum (numai un nume, fara cale), stergerea unui dosar gol
# si scoaterea unui dosar din lista tinuta minte, ambele dupa o intrebare.
#
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau setarile, discurile si navigatorul lor.

import os

# Screens/LocationBox.py: inhibitDirs din MovieLocationBox si TimeshiftLocationBox (testul le compara)
DOSARE_OPRITE = ("/bin", "/boot", "/dev", "/etc", "/lib", "/proc", "/sbin", "/sys", "/usr", "/var")
# TimeshiftLocationBox: minFree (MB, 1 MB = 1000000 octeti, ca LocationBox.select)
MIN_LIBER_TIMESHIFT_MB = 1024

RAND_IMPLICIT = "implicit"
RAND_TEMPORIZATOR = "temporizator"
RAND_IMEDIAT = "imediat"
RAND_TIMESHIFT = "timeshift"
RANDURI = (RAND_IMPLICIT, RAND_TEMPORIZATOR, RAND_IMEDIAT, RAND_TIMESHIFT)


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_), fara efect: textele se traduc la folosire."""
	return text


STILURI = (
	("<default>", N_("<Default movie location>")),
	("<current>", N_("<Current movielist location>")),
	("<timer>", N_("<Last timer location>")),
)
CHEI_STILURI = tuple(k for k, _t in STILURI)


def _config(config=None):
	if config is None:
		from Components.config import config
	return config


def stiluri():
	"""Stilurile ca alegeri ConfigSelection: (cheie, text tradus)."""
	return [(k, _(t)) for k, t in STILURI]


def expert(config=None):
	return _config(config).usage.setup_level.index >= 2


# ------------------------------------------------------------------ alegerile (RecordPathsSettings.initConfigList)

def alegeriImplicit(config=None, valoare=None):
	"""Dosarele tinute minte, plus valoarea de acum a locului implicit, daca lipseste din ele."""
	config = _config(config)
	tmp = config.movielist.videodirs.value
	valoare = config.usage.default_path.value if valoare is None else valoare
	if valoare not in tmp:
		tmp = tmp[:]
		tmp.append(valoare)
	return tmp


def alegeriCuStiluri(valoare, config=None):
	"""Pentru temporizator si inregistrarea imediata: stilurile, apoi dosarele tinute minte (si valoarea de acum)."""
	config = _config(config)
	tmp = config.movielist.videodirs.value
	if valoare not in tmp and valoare not in CHEI_STILURI:
		tmp = tmp[:]
		tmp.append(valoare)
	return stiluri() + tmp


def alegeriTimeshift(valoare, config=None):
	"""Dosarele permise pentru timeshift, plus valoarea de acum."""
	config = _config(config)
	tmp = config.usage.allowed_timeshift_paths.value
	if valoare not in tmp:
		tmp = tmp[:]
		tmp.append(valoare)
	return tmp


def _setare(rand, config):
	u = config.usage
	return {RAND_IMPLICIT: u.default_path, RAND_TEMPORIZATOR: u.timer_path, RAND_IMEDIAT: u.instantrec_path,
		RAND_TIMESHIFT: u.timeshift_path}[rand]


def alegeri(rand, valoare, config=None):
	if rand == RAND_IMPLICIT:
		return alegeriImplicit(config, valoare)
	if rand == RAND_TIMESHIFT:
		return alegeriTimeshift(valoare, config)
	return alegeriCuStiluri(valoare, config)


def randuriVazute(config=None):
	"""Randurile ecranului, in ordine, dupa nivelul utilizatorului."""
	if expert(config):
		return (RAND_IMPLICIT, RAND_TEMPORIZATOR, RAND_IMEDIAT, RAND_TIMESHIFT)
	return (RAND_IMPLICIT, RAND_TIMESHIFT)


def eticheta(rand, config=None):
	"""Textul randului pe televizor."""
	if rand == RAND_IMPLICIT:
		return _("Default movie location") if expert(config) else _("Movie location")
	return {RAND_TEMPORIZATOR: _("Timer record location"), RAND_IMEDIAT: _("Instant record location"),
		RAND_TIMESHIFT: _("Timeshift location")}[rand]


def titluAlegere(rand, config=None):
	"""Textul de sus al ecranului de alegere a dosarului (LocationBox), pentru acel rand."""
	if rand == RAND_IMPLICIT:
		return eticheta(rand, config)
	return {RAND_TEMPORIZATOR: _("Initial location in new timers"),
		RAND_IMEDIAT: _("Location for instant recordings"),
		RAND_TIMESHIFT: _("Where to save temporary timeshift recordings?")}[rand]


def textAlegere(alegere):
	"""(cheie, text) pentru o alegere: stilurile au textul lor, dosarele se arata ca atare."""
	if isinstance(alegere, tuple):
		return alegere[0], alegere[1]
	return alegere, alegere


def randuri(config=None):
	"""[{cheie, text, valoare, alegeri: [[cheie, text]], titlu_alegere}] pentru ecran si pagina."""
	config = _config(config)
	rez = []
	for rand in randuriVazute(config):
		valoare = _setare(rand, config).value
		rez.append({
			"cheie": rand,
			"text": eticheta(rand, config),
			"valoare": valoare,
			"alegeri": [list(textAlegere(a)) for a in alegeri(rand, valoare, config)],
			"titlu_alegere": titluAlegere(rand, config),
		})
	return rez


# ------------------------------------------------------------------ verificarea si salvarea

def poateScrie(valoare):
	"""RecordPathsSettings.checkReadWriteDir: un stil sau un dosar in care se poate scrie (fileExists(x, "w"))."""
	if valoare in CHEI_STILURI:
		return True
	try:
		return bool(valoare) and os.access(valoare, os.W_OK)
	except (OSError, TypeError, ValueError):
		return False


def textNuSePoateScrie(dosar):
	return _("The directory %s is not writable.\nMake sure you select a writable directory instead.") % dosar


def salveaza(implicit, temporizator, imediat, timeshift, config=None):
	"""RecordPathsSettings.save: cele patru valori puse si salvate (save() fiecare)."""
	u = _config(config).usage
	u.default_path.value = implicit
	u.timer_path.value = temporizator
	u.instantrec_path.value = imediat
	u.timeshift_path.value = timeshift
	u.default_path.save()
	u.timer_path.save()
	u.instantrec_path.save()
	u.timeshift_path.save()


def valori(config=None):
	u = _config(config).usage
	return {RAND_IMPLICIT: u.default_path.value, RAND_TEMPORIZATOR: u.timer_path.value,
		RAND_IMEDIAT: u.instantrec_path.value, RAND_TIMESHIFT: u.timeshift_path.value}


def listaTinuta(rand, config=None):
	"""Lista tinuta minte a randului (bookmarks in LocationBox): videodirs, la timeshift allowed_timeshift_paths."""
	config = _config(config)
	return config.usage.allowed_timeshift_paths if rand == RAND_TIMESHIFT else config.movielist.videodirs


def adaugaInLista(element, dosar):
	"""LocationBox.selectConfirmed cu autoAdd: dosarul ales intra in lista, ordonata, si lista se salveaza."""
	semne = element.value[:]
	if dosar not in semne:
		semne.append(dosar)
		semne.sort()
	if semne != element.value:
		element.value = semne
		element.save()


def scoateDinLista(element, dosar):
	"""Scoaterea unui dosar din lista tinuta minte (LocationBox.removeBookmark, apoi salvarea listei)."""
	semne = [x for x in element.value if x != dosar]
	if semne != element.value:
		element.value = semne
		element.save()
		return True
	return False


# ------------------------------------------------------------------ navigarea (LocationBox, FileList)

def dosarOprit(cale):
	"""FileList.inParentDirs(cale, inhibitDirs): calea reala incepe cu unul dintre dosarele sistemului."""
	real = os.path.realpath(cale)
	return any(real.startswith(p) for p in DOSARE_OPRITE)


def _cuBara(cale):
	return os.path.join(cale, "")


def radacini(hm=None, navigator=None, ordine=None, tabel=None):
	"""Discurile montate, ca prima pagina a navigatorului (FileList.changeDir(None)): [{cale, nume, fel}], cele
	detasabile primele, memoria interna ultima."""
	if hm is None:
		from Components.Harddisk import harddiskmanager as hm
	if navigator is None:
		from Components import HdsNavigator as navigator
	if ordine is None:
		from Components.FileList import STORAGE_ORDER as ordine
	tabel = navigator.readMountTable() if tabel is None else tabel
	discuri = []
	for p in hm.getMountedPartitions():
		if not p.mountpoint:
			continue
		cale = _cuBara(p.mountpoint)
		if dosarOprit(cale):
			continue
		fel = navigator.deviceKind(cale, p.device, tabel)
		nume = navigator.deviceName(cale, p.description, p.device, fel, tabel)
		discuri.append((ordine.get(fel, 9), len(discuri), {"cale": cale, "nume": nume, "fel": fel}))
	discuri.sort(key=lambda d: d[:2])
	return [d[2] for d in discuri]


def _sub(cale, baza):
	cale, baza = os.path.realpath(cale), os.path.realpath(baza)
	return cale == baza or cale.startswith(baza.rstrip(os.sep) + os.sep)


def dosarPermis(cale, radacini_=None, **k):
	"""Calea (cu separatorul la sfarsit) daca e un dosar la care se ajunge navigand: sub unul dintre discurile montate
	(si dupa legaturi), nu un dosar al sistemului, fara "..", fara caractere de control; altfel None."""
	if not cale or not os.path.isabs(cale) or any(c in cale for c in "\x00\r\n"):
		return None
	if ".." in cale.replace("\\", "/").split("/"):
		return None
	cale = _cuBara(os.path.normpath(cale))
	if not os.path.isdir(cale) or dosarOprit(cale):
		return None
	for r in (radacini(**k) if radacini_ is None else radacini_):
		if cale.startswith(r["cale"]) and _sub(cale, r["cale"]):
			return cale
	return None


def cheieSortare(nume):
	try:
		from Components.FileList import sortKey
		return sortKey(nume)
	except Exception:
		return nume.casefold()


def dosare(cale, radacini_):
	"""Dosarele din `cale` (fara fisiere), ca FileList cu showFiles=False: [{cale, nume}], fara cele ale sistemului, si
	parintele: o cale, sau None cand parintele e lista discurilor (din radacina unui disc)."""
	try:
		nume = os.listdir(cale)
	except OSError:
		nume = []
	rez = []
	for n in sorted(nume, key=cheieSortare):
		c = os.path.join(cale, n, "")
		if os.path.isdir(c) and not dosarOprit(c):
			rez.append({"cale": c, "nume": n})
	parinte = None
	if not any(r["cale"] == cale for r in radacini_):
		p = _cuBara(os.path.dirname(cale.rstrip(os.sep)) or os.sep)
		if p != cale and any(p.startswith(r["cale"]) for r in radacini_):
			parinte = p
	return {"dosare": rez, "parinte": parinte}


def liberMB(cale):
	try:
		s = os.statvfs(cale)
		return (s.f_bavail * s.f_bsize) // 1000000
	except (OSError, AttributeError):
		return None


def destulLocTimeshift(cale):
	"""TimeshiftLocationBox.select: fara intrebare numai cu mai mult de MIN_LIBER_TIMESHIFT_MB liberi."""
	liber = liberMB(cale)
	return liber is not None and liber > MIN_LIBER_TIMESHIFT_MB


def faDosar(parinte, nume, esteNumeBun=None):
	"""LocationBox.createDirCallback: un singur nume nou in dosarul de acum. (True, cale) sau (False, motivul)."""
	if esteNumeBun is None:
		from Components.HdsNavigator import isSafeName as esteNumeBun
	if not esteNumeBun(nume):
		try:
			from Components.HdsNavigator import unsafeNameMessage
			return False, unsafeNameMessage()
		except ImportError:
			return False, _("The name cannot contain / or \\, cannot start with a dot and must fit in 255 characters.")
	cale = os.path.join(parinte, nume)
	if os.path.exists(cale):
		return False, _("The path %s already exists.") % cale
	try:
		os.mkdir(cale)
	except OSError:
		return False, _("Creating directory %s failed.") % cale
	return True, _cuBara(cale)


def stergeDosar(cale, config=None):
	"""LocationBox.removeDirCallback: numai un dosar gol (rmdir); scos si din lista dosarelor tinute minte."""
	try:
		os.rmdir(cale)
	except OSError:
		return False, _("Removing directory %s failed. (Maybe not empty.)") % cale
	try:
		scoateDinLista(_config(config).movielist.videodirs, cale)
	except Exception as eroare:
		print("[HdsDosareInregistrari] lista dosarelor: %s" % eroare)
	return True, ""
