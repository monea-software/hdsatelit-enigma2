# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsLamedbSalvare.py: lista de canale (/etc/enigma2/lamedb) se scrie si la intrarea in standby, nu numai la iesirea
# curata a interfetei.
#
# De ce: pentru fiecare canal vazut, enigma2 tine minte in memorie PID-urile din PMT (imagine, sunet, PCR, teletext,
# tipul imaginii) si CAID-urile (randurile "c:" si "C:" din lamedb). La urmatorul zap pe acel canal decodorul porneste
# din ele, fara sa astepte PAT si PMT (lib/dvb/pmt.cpp, channelStateChanged). Fisierul se scria numai la iesirea curata
# (main/enigma.cpp, ~eMain) si dupa o cautare (eDVBDB::flush): dupa o cadere, o repornire facuta de paznic sau o taiere
# de curent se pierdea tot ce se invatase de la ultima iesire curata, iar primul zap pe fiecare canal astepta din nou
# PAT si PMT.
# Cum:
# - la intrarea in standby (config.misc.standbyCounter), dupa INTARZIERE_S secunde, numai daca receptorul e tot in
#   standby (trezit intre timp: se lasa pe urmatorul standby);
# - enigma2 scrie lista din memorie intai in /tmp (eDVBDB.saveServicelist(cale): in memorie, nu pe eMMC); daca e la fel
#   cu lamedb-ul de pe disc, nu se scrie nimic pe disc;
# - se scrie numai cand transponderele si serviciile (cheile si numele) sunt aceleasi in memorie si pe disc, iar
#   diferentele sunt numai in randurile de date (PID-urile tinute minte, CAID-urile, steagurile, furnizorul). Altfel
#   cineva a schimbat fisierul pe disc fara sa-l fi reincarcat inca (un import, o lista scrisa in fundal inaintea
#   reincarcarii) si memoria l-ar strica: se lasa ca pana acum, pentru iesirea curata;
# - dintre randurile de date, numai PID-urile tinute minte (jetoanele "c:") hotarasc scrierea. Lista CAID-urilor ("C:")
#   se schimba singura fara niciun PID nou: la incarcare ordinea ei se intoarce (db.cpp o pune cu push_front, deci
#   primul standby dupa fiecare pornire a interfetei ar rescrie tot fisierul), iar lungimea ei trece de la cea din PMT
#   la cea din SDT si inapoi. Cand difera numai CAID-urile, steagurile sau furnizorul nu se scrie ("fara PID-uri noi");
#   cand difera PID-urile se scrie toata lista din memorie, deci si celelalte intra atunci;
# - scrierea: lamedb.nou langa lamedb, fsync, apoi os.replace peste lamedb (fisierul e intreg sau cel vechi);
# - saveServicelist opreste enigma2 (eFatal) cand nu poate deschide fisierul, deci inainte se verifica locul liber si se
#   deschide fisierul din /tmp de aici; lista din memorie trebuie sa se termine cu randul de sfarsit al formatului.
# Modulul nu importa nimic din enigma la incarcare (probele de pe PC).

import os

CALE = "/etc/enigma2/lamedb"
TEMPORAR = "/tmp/hds-lamedb-memorie"
INTARZIERE_S = 5
ANTET = b"eDVB services /4/"
SFARSIT = b"end\nHave a lot of bugs!"
REZERVA_OCTETI = 1024 * 1024

_stare = {"standby": False, "ceas": None}


def _jurnal(text):
	print("[HdsLamedbSalvare] %s" % text)


def desparte(date):
	"""(transpondere, servicii) dintr-un lamedb in formatul 4 (octeti): transpondere = multimea cheilor, servicii =
	{cheie: nume}. None daca nu se intelege (alt format, fisier taiat)."""
	rez = _parcurge(date)
	if rez is None:
		return None
	tp, sv = rez
	return tp, dict((cheie, nume) for cheie, (nume, _date) in sv.items())


def pid_uri(date):
	"""{cheia serviciului: multimea jetoanelor "c:" (PID-urile tinute minte)} dintr-un lamedb in formatul 4 (octeti).
	None daca nu se intelege. Restul randului de date ("C:", "f:", "p:") nu intra."""
	rez = _parcurge(date)
	if rez is None:
		return None
	return dict((cheie, _pid(rand)) for cheie, (_nume, rand) in rez[1].items())


def _parcurge(date):
	"""(multimea cheilor transponderelor, {cheia serviciului: (nume, randul de date)}); None daca nu se intelege."""
	randuri = date.replace(b"\r", b"").split(b"\n")
	if not randuri or randuri[0].strip() != ANTET or len(randuri) < 2 or randuri[1] != b"transponders":
		return None
	n = len(randuri)
	i = 2
	tp = set()
	while i < n and randuri[i] != b"end":
		tp.add(randuri[i])
		i += 1
		while i < n and randuri[i] != b"/":
			i += 1
		if i >= n:
			return None
		i += 1
	if i + 1 >= n or randuri[i + 1] != b"services":
		return None
	i += 2
	sv = {}
	while i < n and randuri[i] != b"end":
		if i + 2 >= n:
			return None
		sv[randuri[i]] = (randuri[i + 1], randuri[i + 2])
		i += 3
	if i >= n:
		return None
	return tp, sv


def compara(disc, memorie):
	"""Ce s-ar schimba pe disc: "la fel" (aceiasi octeti), "date" (PID-uri tinute minte noi sau schimbate, deci se
	scrie), "fara PID-uri noi" (difera numai CAID-urile, ordinea lor, steagurile sau furnizorul: nu se scrie),
	"structura" (alte transpondere, alte servicii sau alte nume: nu se scrie), "nu se intelege"."""
	if disc == memorie:
		return "la fel"
	a = _parcurge(disc)
	b = _parcurge(memorie)
	if a is None or b is None:
		return "nu se intelege"
	if a[0] != b[0] or len(a[1]) != len(b[1]):
		return "structura"
	pid_nou = False
	for cheie, (nume, rand) in a[1].items():
		alt = b[1].get(cheie)
		if alt is None or alt[0] != nume:
			return "structura"
		if not pid_nou and alt[1] != rand and _pid(alt[1]) != _pid(rand):
			pid_nou = True
	return "date" if pid_nou else "fara PID-uri noi"


def _pid(rand):
	"""Jetoanele "c:" ale unui rand de date (PID-urile tinute minte), ca multime."""
	return frozenset(j for j in rand.split(b",") if j.startswith(b"c:"))


def _loc_liber(dosar):
	"""Octetii liberi din dosar; None cand nu se pot afla (atunci hotaraste deschiderea fisierului de mai jos)."""
	try:
		st = os.statvfs(dosar)
		return st.f_bavail * st.f_frsize
	except (OSError, AttributeError):
		return None


def _scrie_sigur(cale, date):
	"""cale.nou, fsync, os.replace peste cale; dosarul cu fsync daca se poate. Arunca la eroare (cale.nou sters)."""
	nou = cale + ".nou"
	try:
		with open(nou, "wb") as f:
			f.write(date)
			f.flush()
			os.fsync(f.fileno())
		os.replace(nou, cale)
	except Exception:
		try:
			os.remove(nou)
		except OSError:
			pass
		raise
	try:
		fd = os.open(os.path.dirname(cale) or ".", os.O_RDONLY)
		try:
			os.fsync(fd)
		finally:
			os.close(fd)
	except (OSError, AttributeError):
		pass


def salveaza(db=None, cale=CALE, temporar=TEMPORAR):
	"""Lista din memorie pe disc, daca s-au schimbat PID-urile tinute minte si numai randurile de date. -> "scris",
	"la fel", "fara PID-uri noi" sau motivul pentru care nu s-a scris. Nu arunca."""
	try:
		if db is None:
			from enigma import eDVBDB
			db = eDVBDB.getInstance()
		if db is None:
			return "fara lista"
		try:
			marime = os.path.getsize(cale)
		except OSError:
			return "fara lamedb pe disc"
		nevoie = 2 * marime + REZERVA_OCTETI
		for dosar in (os.path.dirname(temporar) or ".", os.path.dirname(cale) or "."):
			liber = _loc_liber(dosar)
			if liber is not None and liber < nevoie:
				return "loc putin"
		# fopen-ul din saveServicelist nu are voie sa cada (eFatal): fisierul se face intai de aici
		with open(temporar, "wb"):
			pass
		try:
			db.saveServicelist(temporar)
			with open(temporar, "rb") as f:
				memorie = f.read()
		finally:
			try:
				os.remove(temporar)
			except OSError:
				pass
		if not memorie.startswith(ANTET) or not memorie.rstrip(b"\n").endswith(SFARSIT):
			return "lista din memorie neterminata"
		with open(cale, "rb") as f:
			disc = f.read()
		fel = compara(disc, memorie)
		if fel != "date":
			return fel
		_scrie_sigur(cale, memorie)
		return "scris"
	except Exception as e:
		return "eroare: %r" % (e,)


def _laCeas():
	try:
		from Screens import Standby
		if getattr(Standby, "inStandby", None) is None:
			_jurnal("receptorul s-a trezit, lista ramane pentru urmatorul standby")
			return
	except Exception:
		pass
	_jurnal("lista de canale la standby: %s" % salveaza())


def _laStandby(element=None):
	# config.misc.standbyCounter creste la fiecare intrare in standby; scrierea vine dupa INTARZIERE_S secunde, cand
	# standby-ul s-a incheiat (serviciul oprit, ecranul stins)
	ceas = _stare.get("ceas")
	if ceas is None:
		_laCeas()
		return
	ceas.start(INTARZIERE_S * 1000, True)


def porneste():
	"""Scrierea listei de canale la intrarea in standby. Chemata o data, din mytest.py."""
	try:
		from enigma import eTimer
		if _stare["ceas"] is None:
			ceas = eTimer()
			ceas.callback.append(_laCeas)
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
