# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsJurnal.py: jurnalele componentelor imaginii, aceeasi forma ca lib/base/hdsjurnal.h (C++).
#
# FISIERUL: /home/root/logs/hds-<componenta>.log (HDS_JURNAL_DIR il schimba: emulatorul, probele de pe PC), rotit la
# 256 KB in .log.1 si .log.2. HdsBetaTester.jurnalPermis() trimite orice hds-*.log din dosar.
# RANDUL: "AAAA-LL-ZZTHH:MM:SSZ [NIVEL] [modul] mesaj", ora in UTC; NIVEL: INFO, AVERT, EROARE.
#
# SCRIEREA: in enigma2 prin enigma.hdsJurnalScrie (firul C++ al jurnalelor: un singur scriitor si o singura rotatie pe
# fisier, pentru randurile din C++ si din Python); fara el (probele de pe PC, un enigma2 mai vechi) printr-un fir Python
# al acestui modul. Apelul nu asteapta discul in niciun caz.
#
# CONFIDENTIALITATEA:
# - curata(): un singur rand; adresele IPv4 si MAC intregi acoperite (192.168.x.x, a8:f2:1b:xx:xx:xx), adresele de
#   e-mail scoase, valoarea de dupa cheie=, parola=, jeton=, token=, key=, password=, psk=, secret=, ssid= devine ***.
# - canalul (numele, referinta serviciului, transponderul, SID-ul, PID-urile, codecul) intra NUMAI in randurile AVERT si
#   EROARE (un esec: ca sa se afle exact canalul care nu merge), prin argumentul canal=; un rand INFO il pierde oricum.
#   In mesaj nu se pun numele canalelor, titluri de emisiuni, nume de fisiere ale omului, nume de retele Wi-Fi.
#
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC il folosesc fara receptor.

import os
import re
import threading
import time

INFO = "INFO"
AVERT = "AVERT"
EROARE = "EROARE"
NIVELURI = (INFO, AVERT, EROARE)

DOSAR_IMPLICIT = "/home/root/logs"
ROTIRE_OCTETI = 256 * 1024
FISIERE_VECHI = 2
LUNGIME_MESAJ = 900
_NUME_BUN = re.compile(r"^[a-z0-9-]{1,32}$")


def dosar():
	return os.environ.get("HDS_JURNAL_DIR") or DOSAR_IMPLICIT


def cale(componenta, vechi=0):
	baza = os.path.join(dosar(), "hds-%s.log" % componenta)
	return "%s.%d" % (baza, vechi) if vechi else baza


# ------------------------------------------------------------------ curatarea

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_IPV4 = re.compile(r"(?<![\d.])(\d{1,3}\.\d{1,3})\.\d{1,3}\.\d{1,3}(?!\d|\.\d)")
_MAC = re.compile(r"(?<![0-9A-Fa-f:])([0-9A-Fa-f]{2}([:-])[0-9A-Fa-f]{2}\2[0-9A-Fa-f]{2})\2[0-9A-Fa-f]{2}\2[0-9A-Fa-f]{2}"
	r"\2[0-9A-Fa-f]{2}(?![0-9A-Fa-f:])")
_CHEIE = re.compile(r"(?<![A-Za-z0-9_])(password|passwd|parola|cheie|jeton|token|secret|essid|ssid|pass|psk|key)"
	r"(?![A-Za-z0-9_])([\"']?\s*[=:]\s*[\"']?)([^\s&,;\"')}\]]*)", re.IGNORECASE)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")


def _stele(m):
	return m.group(1) + m.group(2) + "*" * min(3, len(m.group(3)))


def curata(text):
	"""Textul pe un rand, fara IP si MAC intregi, fara e-mail, fara valorile cheilor (vezi sus)."""
	if text is None:
		return ""
	if isinstance(text, bytes):
		text = text.decode("utf-8", "replace")
	text = _CONTROL.sub(" ", "%s" % text)
	text = _IPV4.sub(r"\1.x.x", text)
	text = _MAC.sub(lambda m: m.group(1) + m.group(2) + m.group(2).join(("xx", "xx", "xx")), text)
	text = _EMAIL.sub("***@***", text)
	return _CHEIE.sub(_stele, text)


_CAMPURI_CANAL = ("nume", "ref", "poz", "tp", "sistem", "sid", "vpid", "apid", "codec", "tuner")


def textCanal(canal):
	"""Partea de canal a unui rand de esec: 'canal: nume="..." ref=... poz=...'. canal = dict (cheile din
	_CAMPURI_CANAL, in ordinea lor, apoi celelalte) sau text."""
	if not canal:
		return ""
	if not isinstance(canal, dict):
		return "canal: %s" % canal
	parti = []
	chei = [k for k in _CAMPURI_CANAL if k in canal] + sorted(k for k in canal if k not in _CAMPURI_CANAL)
	for k in chei:
		v = canal.get(k)
		if v is None or v == "":
			continue
		if k == "nume":
			parti.append('nume="%s"' % ("%s" % v).replace('"', "'"))
		else:
			parti.append("%s=%s" % (k, v))
	return ("canal: " + " ".join(parti)) if parti else ""


def formeaza(utc_s, nivel, modul, mesaj):
	t = time.gmtime(utc_s)
	return "%04d-%02d-%02dT%02d:%02d:%02dZ [%s] [%s] %s" % (t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min,
		t.tm_sec, nivel, modul, mesaj)


def _modulBun(modul):
	m = re.sub(r"[\s\[\]]", "-", "%s" % (modul or "-"))[:24]
	return m or "-"


# ------------------------------------------------------------------ scrierea

_scrieC = None   # enigma.hdsJurnalScrie, False daca nu exista
_fir = None
_coada = None
_lacat = threading.Lock()


def _scriitorC():
	global _scrieC
	if _scrieC is None:
		try:
			if os.environ.get("HDS_JURNAL_FARA_ENIGMA"):
				raise ImportError
			from enigma import hdsJurnalScrie
			_scrieC = hdsJurnalScrie
		except Exception:
			_scrieC = False
	return _scrieC


class _FirPython(threading.Thread):
	"""Scriitorul de rezerva (fara enigma2): aceeasi rotatie ca firul C++, fara fdatasync."""

	def __init__(self, coada):
		threading.Thread.__init__(self, name="HdsJurnal")
		self.daemon = True
		self.coada = coada
		self.pornite = set()

	def run(self):
		while True:
			componenta, rand = self.coada.get()
			try:
				self.scrie(componenta, rand)
			except Exception:
				pass
			self.coada.task_done()

	def scrie(self, componenta, rand):
		c = cale(componenta)
		try:
			os.makedirs(dosar(), exist_ok=True)
		except OSError:
			return
		try:
			marime = os.path.getsize(c)
		except OSError:
			marime = 0
		if marime >= ROTIRE_OCTETI:
			for v in range(FISIERE_VECHI, 1, -1):
				try:
					os.replace(cale(componenta, v - 1), cale(componenta, v))
				except OSError:
					pass
			try:
				os.replace(c, cale(componenta, 1))
			except OSError:
				pass
		with open(c, "a", encoding="utf-8") as f:
			if componenta not in self.pornite:
				self.pornite.add(componenta)
				f.write(formeaza(time.time(), INFO, "jurnal", "pornit: proces=python pid=%d" % os.getpid()) + "\n")
			f.write(rand + "\n")


def _inFirPython(componenta, rand):
	global _fir, _coada
	if not os.environ.get("HDS_JURNAL_DIR") and not os.path.isdir("/home/root"):
		return  # nu e receptorul (probele altor module pe PC): nimic scris
	with _lacat:
		if _fir is None:
			import queue
			_coada = queue.Queue(maxsize=10000)
			_fir = _FirPython(_coada)
			_fir.start()
	try:
		_coada.put_nowait((componenta, rand))
	except Exception:
		pass


def scrie(componenta, nivel, modul, mesaj, canal=None):
	"""Un rand in hds-<componenta>.log. canal (dict sau text) intra numai la AVERT si EROARE."""
	try:
		if not _NUME_BUN.match(componenta or ""):
			componenta = "diverse"
		if nivel not in NIVELURI:
			nivel = INFO
		text = "%s" % (mesaj if mesaj is not None else "")
		if canal and nivel != INFO:
			parte = textCanal(canal)
			if parte:
				text = "%s | %s" % (text, parte)
		text = curata(text)[:LUNGIME_MESAJ]
		modul = _modulBun(modul)
		c = _scriitorC()
		if c:
			c(componenta, nivel, modul, text)
		else:
			_inFirPython(componenta, formeaza(time.time(), nivel, modul, text))
	except Exception:
		pass


def info(componenta, modul, mesaj):
	scrie(componenta, INFO, modul, mesaj)


def avert(componenta, modul, mesaj, canal=None):
	scrie(componenta, AVERT, modul, mesaj, canal)


def eroare(componenta, modul, mesaj, canal=None):
	scrie(componenta, EROARE, modul, mesaj, canal)


def asteapta(timp_s=2.0):
	"""Pentru probe: asteapta pana cand firul Python a scris tot (cu firul C++ nu e nimic de asteptat aici)."""
	if _coada is None:
		return True
	capat = time.time() + timp_s
	while time.time() < capat:
		if _coada.unfinished_tasks == 0:
			return True
		time.sleep(0.01)
	return False


class Frana(object):
	"""Cel mult un rand la pauza_s pentru randurile care se pot repeta des; lasa() -> (scrie?, cate s-au sarit)."""

	def __init__(self, pauza_s):
		self.pauza_s = pauza_s
		self.ultim = None
		self.sarite = 0

	def lasa(self):
		acum = time.monotonic()
		if self.ultim is not None and acum - self.ultim < self.pauza_s:
			self.sarite += 1
			return False, self.sarite
		sarite, self.sarite, self.ultim = self.sarite, 0, acum
		return True, sarite


def cronometru():
	"""Ceasul monoton in ms (pentru timpii pasilor)."""
	return int(time.monotonic() * 1000)


def coada(componenta, randuri=40):
	"""Ultimele randuri ale jurnalului (din .log si, daca nu ajung, din .log.1): lista de texte."""
	rez = []
	for c in (cale(componenta), cale(componenta, 1)):
		try:
			with open(c, "rb") as f:
				f.seek(0, 2)
				n = f.tell()
				f.seek(max(0, n - 64 * 1024))
				bucati = f.read().decode("utf-8", "replace").splitlines()
		except (IOError, OSError):
			bucati = []
		rez = bucati + rez
		if len(rez) >= randuri:
			break
	return rez[-randuri:]


# ------------------------------------------------------------------ ajutoare pentru canal (numai la esecuri)

def canalDinReferinta(ref, nume=None):
	"""Datele canalului pentru un rand de esec, dintr-o referinta de serviciu (eServiceReference sau text)."""
	try:
		text = ref.toString() if hasattr(ref, "toString") else "%s" % ref
	except Exception:
		text = ""
	parti = text.split(":")
	canal = {"ref": text}
	if nume:
		canal["nume"] = nume
	try:
		if len(parti) > 6 and parti[0] == "1":
			canal["sid"] = "0x%x" % int(parti[3], 16)
			ns = int(parti[6], 16)
			poz = (ns >> 16) & 0xFFFF
			if poz in (0xEEEE, 0xFFFF):
				canal["poz"] = "terestru" if poz == 0xEEEE else "cablu"
			elif poz:
				canal["poz"] = ("%.1fE" % (poz / 10.0)) if poz <= 1800 else ("%.1fW" % ((3600 - poz) / 10.0))
	except (ValueError, IndexError):
		pass
	return canal
