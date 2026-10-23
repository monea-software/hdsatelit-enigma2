# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# intrare_cam.py: intrarea in interfata web a modulului de acces conditionat, pe televizor, fara parola tastata
# (din 0.2.8): asa cum portul interfetei se afla pe receptor, tot pe receptor se afla si
# utilizatorul si parola ei.
#
# Cand pagina modulului cere utilizator si parola (cererea de autentificare a navigatorului, de la gazda interfetei,
# prima data), ecranul navigatorului (ecrane.py) ia de aici utilizatorul si parola interfetei web, citite chiar pe
# receptor, si le da navigatorului pe intrarea lui standard (lansator.Navigator.autentificare: base64, pe teava, nu pe
# linia de comanda). Daca nu se gasesc sau nu merg (a doua cerere a paginii), omul le scrie in tastatura, ca inainte.
#
# De unde: procesul care asculta pe portul interfetei (Components/HdsInterfeteCam: /proc/net/tcp si tcp6, legate de
# proces prin inode-uri), dosarul lui de configurare din linia lui de comanda (/proc/<pid>/cmdline, optiunile din
# OPTIUNI_DOSAR), fisierul numit dupa proces (NUME_FISIER) si, in el, numai sectiunea interfetei web si cele doua chei
# din FORMATE. Formatele cunoscute sunt date, nu nume de module: in fisierul acesta nu se scrie numele niciunui modul,
# niciun port si nicio cale a vreunuia.
#
# Ce NU face: nu citeste nimic altceva din configurare (alte sectiuni, cititoare, linii, servere), nu scrie nimic, nu
# tine datele (se citesc la fiecare cerere si se dau mai departe pe loc), nu le scrie in niciun jurnal, nu le pune pe
# linia de comanda a vreunui proces si nu le trimite in interfata web. Navigatorul le trimite numai gazdei interfetei
# (lansatorul porneste in modul cam cu --numai-gazda), care e chiar modulul care le are.
#
# Modulul nu importa enigma2: probele de pe PC dau un sistem fals (ca la Components/HdsInterfeteCam.Sistem).

import os
import posixpath
import re

# optiunile cu care un modul primeste dosarul de configurare pe linia de comanda („-c DOSAR”, „--config-dir DOSAR”,
# „--config-dir=DOSAR”)
OPTIUNI_DOSAR = ("-c", "--config-dir")
# fisierul principal de configurare: numele procesului (sau al executabilului, sau partea lui de dinainte de - _ .)
# urmat de acest sufix
SUFIX_FISIER = ".conf"
# formatele cunoscute ale sectiunii interfetei web: sectiunea [<nume>] cu randuri „cheie = valoare”
FORMATE = (
	{"sectiune": "webif", "utilizator": "httpuser", "parola": "httppwd"},
)

FISIER_MAXIM = 256 * 1024   # octeti cititi cel mult din fisierul de configurare
CMDLINE_MAXIM = 8192
VALOARE_MAXIMA = 128        # semne; o valoare mai lunga nu e o parola de interfata web
_NUME_BUN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")


def _jurnal(text):
	# NICIODATA utilizatorul, parola, calea sau continutul fisierului: numai ce s-a intamplat
	print("[HdsNavigator] intrarea in interfata camului: %s" % text)


def _sistem(sistem):
	if sistem is not None:
		return sistem
	try:
		from Components import HdsInterfeteCam as C
	except ImportError:  # probe pe PC: modulul incarcat singur
		import HdsInterfeteCam as C
	return C.Sistem()


def _descoperire():
	try:
		from Components import HdsInterfeteCam as C
	except ImportError:
		import HdsInterfeteCam as C
	return C


def procese_pe_port(port, sistem=None):
	"""Procesele (HdsInterfeteCam.Proces) care asculta pe `port` (TCP, orice adresa), fara procesul in care rulam
	(enigma2) si fara pid 1; in ordinea pid-urilor."""
	C = _descoperire()
	sistem = _sistem(sistem)
	inode = set(i for i, (_adresa, p) in C.porturi_in_ascultare(sistem).items() if p == port)
	if not inode:
		return []
	rez = []
	for pid, p in sorted(C.citeste_procese(sistem).items()):
		if pid == getattr(sistem, "pid_propriu", None):
			continue
		if p.socketuri & inode:
			rez.append(p)
	return rez


def dosar_configurare(argumente):
	"""Dosarul de configurare din argumentele unui proces (fara argv[0]), sau None. Numai o cale absoluta, fara
	semne de control."""
	dosar = None
	for i, a in enumerate(argumente):
		for o in OPTIUNI_DOSAR:
			if a == o and i + 1 < len(argumente):
				dosar = argumente[i + 1]
			elif o.startswith("--") and a.startswith(o + "="):
				dosar = a[len(o) + 1:]
	if not dosar or not dosar.startswith("/") or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in dosar):
		return None
	return posixpath.normpath(dosar)


def argumente_proces(pid, sistem=None):
	"""argv al procesului, fara argv[0] ([] cand nu se poate citi)."""
	sistem = _sistem(sistem)
	try:
		text = sistem.citeste("/proc/%d/cmdline" % pid, CMDLINE_MAXIM)
	except (OSError, IOError):
		return []
	parti = text.split("\0")
	return [x for x in parti[1:] if x]


def nume_fisiere(proces):
	"""Numele posibile ale fisierului de configurare, dupa numele procesului si al executabilului (in aceasta ordine,
	fara dubluri)."""
	nume = []
	for n in (proces.comm, posixpath.basename(proces.exe or "")):
		for x in (n, re.split(r"[-_.]", n or "")[0]):
			if x and _NUME_BUN.match(x) and x not in nume:
				nume.append(x)
	return [x + SUFIX_FISIER for x in nume]


def _valoare_buna(v):
	return v is not None and len(v) <= VALOARE_MAXIMA and not any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in v)


def din_text(text, formate=FORMATE):
	"""(utilizator, parola) din textul unui fisier de configurare, numai din sectiunea interfetei web a unui format
	cunoscut; None cand nu e niciuna sau cand amandoua sunt goale (interfata fara parola). Restul fisierului nu se
	pastreaza nicaieri."""
	for f in formate:
		sectiune = None
		gasit = {}
		for rand in text.splitlines():
			r = rand.strip()
			if not r or r[0] in "#;":
				continue
			if r.startswith("[") and r.endswith("]"):
				sectiune = r[1:-1].strip().lower()
				continue
			if sectiune != f["sectiune"] or "=" not in r:
				continue
			cheie, valoare = r.split("=", 1)
			cheie = cheie.strip().lower()
			if cheie in (f["utilizator"], f["parola"]) and cheie not in gasit:
				gasit[cheie] = valoare.strip()
		if not gasit:
			continue
		u, p = gasit.get(f["utilizator"], ""), gasit.get(f["parola"], "")
		if not (_valoare_buna(u) and _valoare_buna(p)):
			return None
		if not u and not p:
			return None
		return u, p
	return None


def date_intrare(port, sistem=None):
	"""(utilizator, parola) pentru interfata web de pe `port`, citite din configurarea modulului care asculta acolo;
	None cand nu se afla (fara proces, fara dosar pe linia de comanda, fara fisier, fara sectiunea interfetei web,
	interfata fara parola). Nu arunca exceptii."""
	try:
		port = int(port)
	except (TypeError, ValueError):
		return None
	if not 0 < port < 65536:
		return None
	try:
		sistem = _sistem(sistem)
		procese = procese_pe_port(port, sistem)
	except Exception as e:
		_jurnal("procesul de pe port nu s-a putut afla (%s)" % e.__class__.__name__)
		return None
	if not procese:
		_jurnal("niciun proces nu asculta pe portul interfetei")
		return None
	try:
		return _din_procese(procese, sistem)
	except Exception as e:
		# orice neprevazut: tastatura, ca inainte (cererea paginii nu ramane fara raspuns)
		_jurnal("datele nu s-au putut citi (%s); se cer in tastatura" % e.__class__.__name__)
		return None


def _din_procese(procese, sistem):
	for p in procese:
		dosar = dosar_configurare(argumente_proces(p.pid, sistem))
		if dosar is None:
			continue
		for nume in nume_fisiere(p):
			cale = posixpath.join(dosar, nume)
			try:
				if not os.path.isfile(sistem.cale(cale)):
					continue
				text = sistem.citeste(cale, FISIER_MAXIM)
			except (OSError, IOError, ValueError):
				continue
			try:
				rez = din_text(text)
			finally:
				text = None
			if rez is not None:
				_jurnal("date gasite pe receptor")
				return rez
	_jurnal("datele nu s-au gasit; se cer in tastatura")
	return None
