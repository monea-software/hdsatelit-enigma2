# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsEcm.py: ce spune camul care decripteaza acum, pentru a doua bara (pagina accesului) si caseta din bara de jos.
#
# Camul care decripteaza scrie in FISIER ce a decriptat ultima oara. Fisierul se desface generic, rand cu rand
# („cheie: valoare”, plus randul de titlu „===== <sistem> ECM on CaID 0x.., pid 0x.. =====”), fara numele vreunui cam
# in cod: CAID-ul, PID-ul ECM, furnizorul, sistemul, timpul ECM, protocolul, pasii (hops) si daca raspunsul a venit
# local sau prin retea. Numele cititorului, adresele, porturile si cuvintele de control nu se pastreaza deloc. Fisierul
# se reciteste numai cand i s-au schimbat data sau marimea, cel mult o data pe secunda.
#
# Numele camului, in ordine: din alegerea facuta in gestiunea modulelor (legatura /etc/init.d/<fel> spre scriptul
# <fel>.<nume>; felurile se afla dupa forma, ca in Components/HdsInterfeteCam.py, fara nume scrise in cod), cu
# descrierea scriptului cand o are (antetul LSB sau DESC=), altfel <nume>, ca Components/HdsModuleAcces.py; altfel
# numele procesului care tine socketul camului (/tmp/camd.socket: inodul din /proc/net/unix, cautat printre legaturile
# /proc/<pid>/fd, apoi /proc/<pid>/comm), cautat pe un fir separat si tinut TINUT_PROCES_S; altfel ce scrie camul
# despre el in fisierul lui (o cheie "emu", "emulator" sau un cuvant terminat in "cam", TIPAR_CHEIE_NUME); altfel gol.
#
# Modulul e numai al imaginii: skinul (convertoarele din Components/Converter, care merg si pe alte imagini) il cere
# prin HdsCommon.ecm_info / access_module_name si, fara el, nu arata nimic din cam. Nu importa nimic din enigma2.

import os
import re
import threading
import time

FISIER = "/tmp/ecm.info"
MAXIM = 4096
DOSAR_SCRIPTURI = "/etc/init.d"
SUFIX_GOL = "None"
# felurile modulelor (aceeasi regula ca HdsInterfeteCam.feluri_din_nume, scrisa si aici ca modulul sa mearga singur):
# un nume N cu locul gol N.None sau cu legatura N spre un script N.<x>; felul terminat in "cam" primul
TIPAR_FEL_PRINCIPAL = re.compile(r"cam$", re.I)
_NUME_FEL = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,31}$")
NUME_MAXIM = 40
# protocoale ale cititoarelor legate direct de receptor (raspuns local, nu prin retea)
PROTOCOALE_LOCALE = ("internal", "emu", "constcw", "mouse", "smargo", "smartreader", "sc8in1", "pcsc", "sci", "card",
	"local", "cache")

SOCKET = "/tmp/camd.socket"
NET_UNIX = "/proc/net/unix"
PROC = "/proc"
TINUT_PROCES_S = 60.0
MAX_PROCESE = 400
# cheile din fisierul camului care spun numele camului (primul cuvant): "emu", "emulator" sau un cuvant terminat in
# "cam" (si "cam" insusi)
TIPAR_CHEIE_NUME = re.compile(r"^(?:[a-z]*cam|emu|emulator)$")

_TITLU = re.compile(r"^=+\s*(.*?)\s*ECM on CaID\s*0x([0-9A-Fa-f]+),\s*pid\s*0x([0-9A-Fa-f]+)", re.I)
_stare = {"t": -1000.0, "sig": None, "val": {}}
_nume = {"t": -1000.0, "val": ""}
_proces = {"t": -1000.0, "val": "", "merge": False}


def _curat(s, n=30):
	t = "".join(c if (c >= " " and c != "\x7f") else " " for c in str(s))
	return " ".join(t.split())[:n]


def _hex(v):
	try:
		return int(str(v).strip().split()[0].rstrip(",;"), 16)
	except Exception:
		return -1


def _cuvant(v, n=20):
	"""Primul cuvant, numai cu litere, cifre si . _ + - (fara adrese, fara porturi)."""
	p = str(v).strip().split()
	t = "".join(c for c in (p[0] if p else "") if c.isalnum() or c in "._+-")[:n]
	return "" if (not t or t.replace(".", "").isdigit()) else t


def _local(v):
	t = str(v).strip().lower()
	return t in ("local", "localhost", "127.0.0.1", "::1", "emu", "card") or t.startswith("/dev/")


def desface(text):
	"""Randurile fisierului -> {caid, pid, prov, prov_name, system, ms, protocol, local, hops}; cheile lipsa nu se pun.
	Randurile cu cititorul, adresa, portul sau cuvintele de control nu lasa nimic in rezultat."""
	d = {}
	for rand in str(text or "").splitlines()[:48]:
		rand = rand.strip()
		if not rand:
			continue
		m = _TITLU.match(rand)
		if m:
			d["caid"] = int(m.group(2), 16) & 0xFFFF
			d["pid"] = int(m.group(3), 16)
			if m.group(1):
				d["system"] = _curat(m.group(1))
			continue
		if ":" not in rand:
			continue
		k, v = rand.split(":", 1)
		k = k.strip().lower()
		v = v.strip()
		if k == "caid":
			c = _hex(v)
			if c > 0:
				d["caid"] = c & 0xFFFF
		elif k in ("pid", "ecm pid"):
			p = _hex(v)
			if 0 < p < 0x1FFF:
				d["pid"] = p
		elif k in ("prov", "provid", "provider id"):
			p = _hex(v)
			if p >= 0:
				d["prov"] = p
		elif k == "provider":
			p = _hex(v) if v.lower().startswith("0x") else -1
			if p >= 0:
				d["prov"] = p
			elif v:
				d["prov_name"] = _curat(v)
		elif k == "system":
			if v:
				d["system"] = _curat(v)
		elif k in ("ecm time", "ecmtime"):
			try:
				x = float(v.split()[0].replace(",", "."))
				d["ms"] = int(round(x * 1000)) if (x < 20 and "ms" not in v.lower()) else int(round(x))
			except Exception:
				pass
		elif k == "msec":
			try:
				d["ms"] = int(v.split()[0])
			except Exception:
				pass
		elif k in ("protocol", "using"):
			t = _cuvant(v)
			if t:
				d["protocol"] = t
				if t.lower() in PROTOCOALE_LOCALE and "local" not in d:
					d["local"] = True
		elif k == "source":
			low = v.lower()
			primul = low.split()[0] if low.split() else ""
			d["local"] = primul not in ("net", "network", "remote")
			m2 = re.search(r"\(\s*([A-Za-z0-9._+-]+)", v)
			if m2 and m2.group(1).lower() != "at":
				d.setdefault("protocol", _cuvant(m2.group(1)) or primul)
			elif primul:
				d.setdefault("protocol", _cuvant(primul))
		elif k in ("from", "address"):
			d["local"] = _local(v)
		elif k == "hops":
			try:
				d["hops"] = int(v.split()[0])
			except Exception:
				pass
		elif TIPAR_CHEIE_NUME.match(k):
			t = _cuvant(v, NUME_MAXIM)
			if t:
				d["cam"] = t
	return d


def stare(cale=None, acum=None):
	"""Fisierul desfacut, plus `mtime`; {} cand lipseste. Recitit numai la schimbare, cel mult o data pe secunda."""
	cale = cale or FISIER
	acum = time.time() if acum is None else acum
	if 0.0 <= acum - _stare["t"] < 1.0 and _stare.get("cale") == cale:
		return _stare["val"]
	_stare["t"] = acum
	_stare["cale"] = cale
	try:
		st = os.stat(cale)
	except Exception:
		_stare["sig"] = None
		_stare["val"] = {}
		return {}
	sig = (st.st_mtime, st.st_size)
	if sig != _stare["sig"]:
		try:
			with open(cale, "rb") as f:
				text = f.read(MAXIM).decode("utf-8", "replace")
		except Exception:
			text = ""
		val = desface(text)
		val["mtime"] = float(st.st_mtime)
		_stare["sig"] = sig
		_stare["val"] = val
	return _stare["val"]


def _descriere(cale):
	try:
		with open(cale, "rb") as f:
			text = f.read(8192).decode("utf-8", "replace")
	except Exception:
		return ""
	for cheie in ("Short-Description", "Description"):
		m = re.search(r"^#\s*" + cheie + r":\s*(.+)$", text, re.M)
		if m and m.group(1).strip():
			return m.group(1).strip()
	m = re.search(r"^\s*DESC=([\"']?)([^\"'\n]+)\1", text, re.M)
	return m.group(2).strip() if m else ""


def feluri(nume, legatura):
	"""Felurile modulelor din numele aflate in dosarul scripturilor, in ordinea de cautare (regula din
	HdsInterfeteCam.feluri_din_nume). `legatura(n)`: tinta legaturii n sau None."""
	toate = set(nume)
	candidati = set()
	for n in toate:
		c = n.split(".", 1)[0]       # prefixul unui script N.<x> sau legatura N insasi
		if _NUME_FEL.match(c):
			candidati.add(c)
	rez = []
	for c in candidati:
		if c + "." + SUFIX_GOL in toate:
			rez.append(c)
			continue
		t = legatura(c)
		if t:
			b = os.path.basename(t)
			if b.startswith(c + ".") and len(b) > len(c) + 1:
				rez.append(c)
	rez.sort(key=lambda f: (not TIPAR_FEL_PRINCIPAL.search(f), f.lower(), f))
	return rez


def _feluri_din_dosar(dosar, legatura, listeaza):
	try:
		nume = listeaza(dosar)
	except Exception:
		return []

	def tinta(n):
		try:
			return legatura(os.path.join(dosar, n))
		except Exception:
			return None
	return feluri(nume, tinta)


def _din_alegere(dosar, legatura, listeaza=os.listdir):
	for fel in _feluri_din_dosar(dosar, legatura, listeaza):
		try:
			tinta = os.path.basename(legatura(os.path.join(dosar, fel)))
		except Exception:
			continue
		if not tinta.startswith(fel + "."):
			continue
		sufix = tinta[len(fel) + 1:]
		if not sufix or sufix == SUFIX_GOL:
			continue
		return _curat(_descriere(os.path.join(dosar, tinta)) or sufix, NUME_MAXIM)
	return ""


def nume_cam(dosar=None, legatura=None, acum=None, proces=None, fisier=None, listeaza=None):
	"""Numele camului: alegerea din gestiunea modulelor, altfel procesul socketului camului, altfel ce scrie camul in
	fisierul lui; gol cand nu se afla nimic. Tinut 10 s. `proces`, `fisier` si `listeaza` (functii) se dau in probe."""
	acum = time.time() if acum is None else acum
	proba = dosar is not None or legatura is not None
	if not proba and 0.0 <= acum - _nume["t"] < 10.0:
		return _nume["val"]
	val = _din_alegere(dosar or DOSAR_SCRIPTURI, legatura or os.readlink, listeaza or os.listdir)
	asteapta = False
	if not val:
		if proces is not None:
			val = _curat(proces() or "", NUME_MAXIM)
		elif not proba:
			val = _nume_din_proces(acum)
			asteapta = _proces["merge"]
	if not val:
		try:
			d = fisier() if fisier is not None else ({} if proba else stare())
			val = _curat(d.get("cam") or "", NUME_MAXIM)
		except Exception:
			val = ""
	if not proba and not asteapta:
		# cat cauta firul, raspunsul gol nu se tine minte: urmatoarea chemare ia numele gasit
		_nume["t"] = acum
		_nume["val"] = val
	return val


# ---------------------------------------------------------------- procesul care tine socketul camului


def inoduri_socket(text, cale=SOCKET):
	"""Inodurile socketurilor unix legate de `cale`, din textul /proc/net/unix (coloana 7 = inodul, 8 = calea)."""
	rez = set()
	for rand in str(text or "").splitlines()[1:]:
		p = rand.split()
		if len(p) >= 8 and p[7] == cale:
			try:
				rez.add(int(p[6]))
			except ValueError:
				pass
	return rez


def proces_socket(cale=SOCKET, proc=PROC, citeste=None, listeaza=None, legatura=None):
	"""Numele (comm) procesului care tine deschis socketul unix `cale`, sau "". Numai citiri din /proc; o cautare
	trece prin legaturile fd ale fiecarui proces, deci se face pe un fir, nu pe firul enigma2."""
	citeste = citeste or _citeste_mic
	listeaza = listeaza or os.listdir
	legatura = legatura or os.readlink
	inoduri = inoduri_socket(citeste(os.path.join(proc, "net", "unix")), cale)
	if not inoduri:
		return ""
	cautate = set("socket:[%d]" % i for i in inoduri)
	try:
		pids = [x for x in listeaza(proc) if x.isdigit()][:MAX_PROCESE]
	except Exception:
		return ""
	for pid in pids:
		dfd = os.path.join(proc, pid, "fd")
		try:
			fds = listeaza(dfd)
		except Exception:
			continue
		for fd in fds:
			try:
				if legatura(os.path.join(dfd, fd)) in cautate:
					return _cuvant(citeste(os.path.join(proc, pid, "comm")), NUME_MAXIM)
			except Exception:
				continue
	return ""


def _citeste_mic(cale):
	try:
		with open(cale, "rb") as f:
			return f.read(65536).decode("utf-8", "replace")
	except Exception:
		return ""


def _nume_din_proces(acum):
	"""Numele procesului socketului camului, din memoria de TINUT_PROCES_S; cand memoria e veche, cautarea porneste pe
	un fir si numele vine la o chemare urmatoare. Fara socket: gol, fara cautare."""
	if _proces["merge"] or 0.0 <= acum - _proces["t"] < TINUT_PROCES_S:
		return _proces["val"]
	if not os.path.exists(SOCKET):
		_proces["t"] = acum
		_proces["val"] = ""
		return ""
	_proces["merge"] = True

	def lucru():
		try:
			val = _curat(proces_socket() or "", NUME_MAXIM)
		except Exception:
			val = ""
		_proces["val"] = val
		_proces["t"] = time.time()
		_proces["merge"] = False
	try:
		fir = threading.Thread(target=lucru, name="HdsEcmProces")
		fir.daemon = True
		fir.start()
	except Exception:
		_proces["merge"] = False
	return _proces["val"]
