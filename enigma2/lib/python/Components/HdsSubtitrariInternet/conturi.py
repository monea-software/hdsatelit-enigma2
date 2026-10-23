# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# conturi.py: conturile si cheile surselor de subtitrari (numele si parola OpenSubtitles, cheia aplicatiei, cheile
# subs.ro si SubDL), tinute intr-un fisier separat, criptat cu o cheie legata de aparat.
#
# De ce asa: /etc/enigma2/settings ajunge in copiile de siguranta si pe forumuri; fisierul acesta nu e in settings, are
# drepturi 0600 si e criptat cu o cheie facuta din identitatea receptorului (adresa placii de retea si /etc/machine-id),
# deci o copie mutata pe alt receptor sau ajunsa pe internet nu mai da parola. Nu apara de cineva care are deja root pe
# acelasi receptor (el poate reface cheia): asta tine de parola root si de interfata web cu parola.
#
# Criptarea, numai cu modulele standard (hmac, hashlib): cheile de criptare si de verificare se deriva cu HMAC-SHA256
# din cheia aparatului; textul se amesteca (XOR) cu un sir facut din HMAC-SHA256(cheie, nonce || contor), iar la sfarsit
# HMAC-SHA256 peste nonce si textul criptat (criptare, apoi verificare). Nonce-ul e aleator (16 octeti) la fiecare
# scriere. Un fisier schimbat, stricat sau de pe alt aparat se citeste ca gol (omul scrie din nou datele).
#
# Nimic de aici nu scrie in jurnal valori: numai ce s-a intamplat („nu se poate citi”).

import base64
import hashlib
import hmac
import json
import os
import secrets

CALE = "/etc/enigma2/hdsatelit/subtitrari-conturi.bin"
VERSIUNE = 1
MAX_OCTETI = 64 * 1024
CAMPURI = ("os_utilizator", "os_parola", "os_cheie_aplicatie", "subsro_cheie", "subdl_cheie")
MAX_CAMP = 256
_SPUS = {}     # cale -> (marime, ora) a fisierului de conturi despre care jurnalul a spus deja ca nu se poate citi


def _citesteText(cale):
	try:
		with open(cale, "r", encoding="utf-8") as f:
			return f.read(512).strip()
	except (OSError, IOError):
		return ""


def identitateAparat(retea="/sys/class/net", masina="/etc/machine-id"):
	"""Adresa placii de retea prin cablu (eth0, altfel prima placa cu adresa) si /etc/machine-id."""
	mac = _citesteText(os.path.join(retea, "eth0", "address"))
	if not mac:
		try:
			for n in sorted(os.listdir(retea)):
				if n != "lo":
					mac = _citesteText(os.path.join(retea, n, "address"))
					if mac and mac != "00:00:00:00:00:00":
						break
		except OSError:
			mac = ""
	return "%s|%s" % (mac.lower(), _citesteText(masina))


def _chei(identitate):
	baza = hmac.new(b"hds-subtitrari-conturi-v1", identitate.encode("utf-8"), hashlib.sha256).digest()
	return (hmac.new(baza, b"criptare", hashlib.sha256).digest(), hmac.new(baza, b"verificare", hashlib.sha256).digest())


def _sir(cheie, nonce, lungime):
	iesire = bytearray()
	contor = 0
	while len(iesire) < lungime:
		iesire += hmac.new(cheie, nonce + contor.to_bytes(8, "big"), hashlib.sha256).digest()
		contor += 1
	return bytes(iesire[:lungime])


def cripteaza(date, identitate, nonce=None):
	"""dict -> octetii fisierului (JSON cu nonce, text criptat si verificare, in base64)."""
	k_c, k_v = _chei(identitate)
	nonce = nonce or secrets.token_bytes(16)
	text = json.dumps(date, ensure_ascii=False, sort_keys=True).encode("utf-8")
	criptat = bytes(a ^ b for a, b in zip(text, _sir(k_c, nonce, len(text))))
	semn = hmac.new(k_v, nonce + criptat, hashlib.sha256).digest()
	return json.dumps({"v": VERSIUNE, "n": base64.b64encode(nonce).decode("ascii"),
		"c": base64.b64encode(criptat).decode("ascii"), "s": base64.b64encode(semn).decode("ascii")}).encode("ascii")


def decripteaza(octeti, identitate):
	"""Octetii fisierului -> dict, sau None (stricat, schimbat sau de pe alt aparat)."""
	try:
		plic = json.loads(octeti.decode("ascii"))
		if plic.get("v") != VERSIUNE:
			return None
		nonce = base64.b64decode(plic["n"])
		criptat = base64.b64decode(plic["c"])
		semn = base64.b64decode(plic["s"])
	except (ValueError, KeyError, TypeError, AttributeError, UnicodeDecodeError):
		return None
	k_c, k_v = _chei(identitate)
	if not hmac.compare_digest(semn, hmac.new(k_v, nonce + criptat, hashlib.sha256).digest()):
		return None
	text = bytes(a ^ b for a, b in zip(criptat, _sir(k_c, nonce, len(criptat))))
	try:
		date = json.loads(text.decode("utf-8"))
	except (ValueError, UnicodeDecodeError):
		return None
	return date if isinstance(date, dict) else None


def _curat(date):
	rez = {}
	for k in CAMPURI:
		v = date.get(k) if isinstance(date, dict) else None
		if isinstance(v, str) and v.strip():
			rez[k] = v.strip()[:MAX_CAMP]
	return rez


class Conturi(object):
	"""Citirea si scrierea fisierului; `identitate` si `cale` se pot schimba (probele)."""

	def __init__(self, cale=CALE, identitate=None):
		self.cale = cale
		self._identitate = identitate

	def identitate(self):
		return self._identitate if self._identitate is not None else identitateAparat()

	def citeste(self):
		"""dict cu campurile din CAMPURI care exista; {} daca fisierul lipseste sau nu se poate citi. Un fisier care nu
		se poate citi se spune in jurnal o singura data (pentru aceeasi marime si ora a fisierului), nu la fiecare
		citire: pagina web cere starea la 1,5 s."""
		try:
			st = os.stat(self.cale)
			if st.st_size > MAX_OCTETI:
				return {}
			with open(self.cale, "rb") as f:
				octeti = f.read()
		except (OSError, IOError):
			return {}
		date = decripteaza(octeti, self.identitate())
		if date is None:
			semn = (self.cale, st.st_size, int(st.st_mtime))
			if _SPUS.get(self.cale) != semn:
				_SPUS[self.cale] = semn
				print("[HdsSubtitrariInternet] conturile nu se pot citi (fisier schimbat sau de pe alt receptor)")
			return {}
		return _curat(date)

	def scrie(self, date):
		"""Scrie campurile date (atomic, 0600). -> True/False."""
		octeti = cripteaza(_curat(date), self.identitate())
		nou = self.cale + ".nou"
		try:
			d = os.path.dirname(self.cale)
			if d and not os.path.isdir(d):
				os.makedirs(d)
			fd = os.open(nou, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
			try:
				if hasattr(os, "fchmod"):
					os.fchmod(fd, 0o600)
				rest = octeti
				while rest:
					rest = rest[os.write(fd, rest):]
				os.fsync(fd)
			finally:
				os.close(fd)
			os.replace(nou, self.cale)
			return True
		except (OSError, IOError) as e:
			print("[HdsSubtitrariInternet] conturile nu s-au scris: %s" % (e.strerror or e.__class__.__name__))
			try:
				os.unlink(nou)
			except OSError:
				pass
			return False

	def schimba(self, **campuri):
		"""Schimba unele campuri: o valoare goala sau None sterge campul; celelalte raman. -> True/False."""
		date = self.citeste()
		for k, v in campuri.items():
			if k not in CAMPURI:
				continue
			if v is None or not str(v).strip():
				date.pop(k, None)
			else:
				date[k] = str(v).strip()[:MAX_CAMP]
		return self.scrie(date)

	def stare(self, date=None):
		"""Pentru ecrane si web, fara valori secrete: {camp: True/False}, plus numele de utilizator (nu e secret).
		`date`: campurile deja citite (o singura citire a fisierului)."""
		date = self.citeste() if date is None else date
		rez = dict((k, k in date) for k in CAMPURI)
		rez["os_utilizator_text"] = date.get("os_utilizator", "")
		return rez
