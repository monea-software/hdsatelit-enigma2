# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsFisierSigur - paza unui fisier JSON de stare din /etc/enigma2 (masuratorile, pistele si accesul canalelor): un
# fisier care nu s-a putut citi nu e scris niciodata peste.
#
# Citirea da una din stari:
#   LIPSESTE (ENOENT, ENOTDIR): memorie goala, se scrie normal;
#   CITIT: se scrie normal;
#   NECITIT (orice alta eroare de citire: EIO, EACCES, EMFILE, ENOMEM): memorie goala, numai citire (nicio scriere pe
#     disc; ce se afla intre timp ramane in memorie); se citeste din nou dupa REINCERCARE_S, de cel mult
#     REINCERCARI_MAX ori, si la urmatoarea pornire; la o citire buna memoria se uneste peste fisier;
#   STRICAT (JSON rau, fisier taiat, forma gresita, v mai mic sau lipsa): inaintea primei scrieri fisierul se pune
#     deoparte ca <nume>.stricat-AAAALLZZ (legatura tare, altfel redenumire; raman cel mult MAX_STRICATE), abia apoi
#     se scrie; daca nu se poate pune deoparte: DEGRADAT;
#   V_MAI_MARE (scris de o versiune mai noua a imaginii), PREA_MARE, DEGRADAT: numai citire pana la urmatoarea pornire.
# Punerea deoparte se face abia la prima scriere, deci cine numai citeste nu atinge discul. Daca fisierul s-a schimbat
# de la ultima citire sau scriere (alta amprenta: marime, mtime, inod; si un fisier aparut dupa o citire LIPSESTE), nu
# se scrie si nu se pune deoparte ce nu s-a citit: se citeste din nou, iar memoria se uneste peste el. Copia abia pusa
# deoparte nu se sterge la curatenie (ziua din nume vine din ceasul receptorului, care poate fi in urma); o copie care
# e deja acelasi fisier cu cel viu (cadere intre punerea deoparte si inlocuire) se refoloseste.
# Scrierea ramane a fiecarui modul (temporar + fsync + os.replace, apoi scris()); aici e numai poarta dinaintea ei.
#
# Modul curat (fara enigma): probele pe PC in test_fisier_sigur.py
# si in testele celor trei module care il folosesc.

from __future__ import absolute_import

import errno
import json
import os
import time

REINCERCARE_S = 600
REINCERCARI_MAX = 3
MAX_STRICATE = 2

LIPSESTE = "lipseste"
CITIT = "citit"
NECITIT = "necitit"
STRICAT = "stricat"
DEGRADAT = "degradat"
V_MAI_MARE = "v-mai-mare"
PREA_MARE = "prea-mare"

SE_SCRIE = (LIPSESTE, CITIT)
NUMAI_CITIRE = (NECITIT, DEGRADAT, V_MAI_MARE, PREA_MARE)
_LIPSA = (errno.ENOENT, errno.ENOTDIR)


def _monoton():
	return time.monotonic()


def _zi(t):
	return time.strftime("%Y%m%d", time.localtime(t))


def _jurnal_implicit(text):
	print("[HdsFisierSigur] %s" % text)


class FisierJson(object):
	"""Citirea si poarta scrierii pentru un fisier JSON {"v": versiune, ...}. `monoton` masoara asteptarea dintre
	reincercari (nu sare cu ceasul receptorului), `ceas` da ziua din numele .stricat."""

	def __init__(self, cale, max_octeti, versiune, jurnal=None, monoton=None, ceas=None):
		self.cale = cale
		self.max_octeti = max_octeti
		self.versiune = versiune
		self._jurnal = jurnal or _jurnal_implicit
		self._monoton = monoton or _monoton
		self._ceas = ceas or time.time
		self.stare = None
		self.detaliu = ""
		self.pus_deoparte = None
		self._amprenta = None
		self._reincercari = 0
		self._ultima = None
		self._anuntat = None

	# ------------------------------------------------ citirea

	def citeste(self):
		"""-> obiectul (dict cu "v" egal cu versiunea) sau None; starea ramane in self.stare. Nu arunca."""
		self._amprenta = None
		self.detaliu = ""
		try:
			with open(self.cale, "rb") as f:
				st = os.fstat(f.fileno())
				self._amprenta = (st.st_size, st.st_mtime_ns, st.st_ino)
				if st.st_size > self.max_octeti:
					return self._iese(PREA_MARE, "%d octeti" % st.st_size)
				date = f.read(self.max_octeti + 1)
			if len(date) > self.max_octeti:
				return self._iese(PREA_MARE, "peste %d octeti" % self.max_octeti)
			obiect = json.loads(date.decode("utf-8"))
		except (IOError, OSError) as e:
			if getattr(e, "errno", None) in _LIPSA:
				return self._iese(LIPSESTE)
			return self._iese(NECITIT, "%s: %s" % (type(e).__name__, e))
		except MemoryError as e:
			return self._iese(NECITIT, "MemoryError: %s" % e)
		except (ValueError, RecursionError) as e:
			return self._iese(STRICAT, "%s: %s" % (type(e).__name__, e))
		if not isinstance(obiect, dict):
			return self._iese(STRICAT, "nu e un obiect")
		v = obiect.get("v")
		if isinstance(v, int) and not isinstance(v, bool) and v > self.versiune:
			return self._iese(V_MAI_MARE, "v=%d" % v)
		if v != self.versiune or isinstance(v, bool):
			return self._iese(STRICAT, "v=%r" % (v,))
		self.stare = CITIT
		return obiect

	def _iese(self, stare, detaliu=""):
		self.stare = stare
		self.detaliu = detaliu
		if stare == NECITIT:
			self._ultima = self._monoton()
		if stare == STRICAT:
			self._jurnal("%s stricat (%s): se pune deoparte inaintea primei scrieri" % (self.cale, detaliu))
		elif stare in NUMAI_CITIRE:
			self._jurnal("%s: numai citire, %s (%s)" % (self.cale, stare, detaliu))
		return None

	def stricat(self, detaliu):
		"""Pentru modul: fisierul s-a citit, dar forma lui nu e cea stiuta (de ex. "c" nu e un obiect)."""
		self._iese(STRICAT, detaliu)

	def numai_citire(self):
		return self.stare in NUMAI_CITIRE

	# ------------------------------------------------ reincercarea

	def la_timp(self):
		"""True (si o reincercare consumata) cand, dupa o citire nereusita, a venit timpul unei citiri noi."""
		if self.stare != NECITIT or self._reincercari >= REINCERCARI_MAX:
			return False
		acum = self._monoton()
		if self._ultima is not None and acum - self._ultima < REINCERCARE_S:
			return False
		self._reincercari += 1
		self._ultima = acum
		return True

	# ------------------------------------------------ poarta scrierii

	def poate_scrie(self, reciteste):
		"""Inaintea fiecarei scrieri. `reciteste()` e al modulului: citeste din nou (prin citeste()) si, numai daca starea
		devine CITIT, uneste memoria peste ce e pe disc. -> True daca se poate scrie acum."""
		if self.stare == NECITIT and self.la_timp():
			reciteste()
		if self.stare in (STRICAT, LIPSESTE, CITIT) and self._amprenta_acum() != self._amprenta:
			# fisierul s-a schimbat de la ultima citire sau scriere (aparut, inlocuit, pus la loc, disparut): ce e acum
			# pe disc nu s-a citit inca
			reciteste()
		if self.stare == STRICAT:
			if self._amprenta_acum() is None:
				self.stare, self.detaliu = LIPSESTE, ""
			elif self._pune_deoparte():
				self.stare, self.detaliu = CITIT, ""
			else:
				self.stare = DEGRADAT
		if self.stare in SE_SCRIE:
			self._anuntat = None
			return True
		if self._anuntat != (self.stare, self.detaliu):
			self._anuntat = (self.stare, self.detaliu)
			self._jurnal("%s nu se scrie: numai citire, %s (%s)" % (self.cale, self.stare, self.detaliu))
		return False

	def scris(self):
		"""Dupa fiecare scriere reusita a modulului (dupa os.replace): fisierul de pe disc e chiar memoria, deci amprenta
		lui devine cea stiuta; fara ea, urmatoarea scriere ar lua propriul fisier drept unul schimbat de altcineva."""
		self._amprenta = self._amprenta_acum()

	def _amprenta_acum(self):
		try:
			st = os.stat(self.cale)
		except (IOError, OSError):
			return None
		return (st.st_size, st.st_mtime_ns, st.st_ino)

	def _pune_deoparte(self):
		"""Fisierul rau devine si <nume>.stricat-AAAALLZZ, fara nicio scriere: intai o legatura tare (fisierul viu ramane
		pe loc pana il inlocuieste scrierea atomica), numai daca legatura nu se poate, o redenumire."""
		cale = self.cale
		deja = self._copia_existenta()
		if deja is not None:
			# o punere deoparte anterioara, urmata de o cadere inaintea inlocuirii: copia e chiar fisierul viu
			self.pus_deoparte = deja
			self._jurnal("%s e deja pus deoparte ca %s" % (cale, os.path.basename(deja)))
			return True
		nume = "%s.stricat-%s" % (cale, _zi(self._ceas()))
		tinta, n = nume, 1
		while os.path.lexists(tinta):
			n += 1
			tinta = "%s-%d" % (nume, n)
		try:
			os.link(cale, tinta)
		except (IOError, OSError, AttributeError, NotImplementedError) as e:
			self._jurnal("fara legatura pentru %s: %s; redenumesc" % (cale, e))
			try:
				os.rename(cale, tinta)
			except (IOError, OSError) as e2:
				self.detaliu = "nu s-a putut pune deoparte: %s" % e2
				self._jurnal("nu pot pune deoparte %s: %s" % (cale, e2))
				return False
			self._amprenta = None        # fisierul viu nu mai e pe loc
		self.pus_deoparte = tinta
		self._jurnal("%s pus deoparte ca %s" % (cale, os.path.basename(tinta)))
		self._curata_stricate(os.path.basename(tinta))
		return True

	def _stricate(self):
		"""-> (dosarul, numele copiilor .stricat ale fisierului); lista goala daca dosarul nu se poate citi."""
		dosar = os.path.dirname(self.cale) or "."
		inceput = os.path.basename(self.cale) + ".stricat-"
		try:
			return dosar, [x for x in os.listdir(dosar) if x.startswith(inceput)]
		except (IOError, OSError):
			return dosar, []

	def _copia_existenta(self):
		"""Calea copiei .stricat care e acelasi fisier (acelasi dispozitiv si inod) cu fisierul viu, sau None."""
		try:
			viu = os.stat(self.cale)
		except (IOError, OSError):
			return None
		dosar, stricate = self._stricate()
		for x in sorted(stricate):
			p = os.path.join(dosar, x)
			try:
				st = os.stat(p)
			except (IOError, OSError):
				continue
			if st.st_ino and (st.st_dev, st.st_ino) == (viu.st_dev, viu.st_ino):
				return p
		return None

	def _curata_stricate(self, abia_facuta):
		"""Raman cel mult MAX_STRICATE copii. Copia abia facuta nu se sterge niciodata: ziua din numele ei vine din ceasul
		receptorului, care poate fi in urma, deci ordinea dupa nume nu spune sigur ca e cea mai noua."""
		dosar, stricate = self._stricate()
		inceput = os.path.basename(self.cale) + ".stricat-"

		def ordine(x):
			parti = x[len(inceput):].split("-")
			return (parti[0], int(parti[1]) if len(parti) > 1 and parti[1].isdigit() else 1)
		celelalte = sorted((x for x in stricate if x != abia_facuta), key=ordine)
		de_pastrat = MAX_STRICATE - 1
		for x in celelalte[:-de_pastrat] if de_pastrat > 0 else celelalte:
			try:
				os.remove(os.path.join(dosar, x))
			except (IOError, OSError):
				pass


def uneste_peste(disc, memorie, maxim, uneste=None):
	"""Dupa o citire buna venita tarziu: intrarile de pe disc intai, apoi cele din memorie (mai noi, deci la coada si
	castigatoare pe aceeasi cheie; `uneste(vechi, nou)` pentru o unire pe campuri). Cele mai vechi pleaca peste maxim."""
	rez = dict(disc)
	for k, v in memorie.items():
		vechi = rez.pop(k, None)
		rez[k] = uneste(vechi, v) if (uneste is not None and vechi is not None) else v
	while len(rez) > maxim:
		del rez[next(iter(rez))]
	return rez
