# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com & hdsatelit.com
# SPDX-License-Identifier: GPL-2.0-only

"""Jurnal mic al iesirii interfetei, curatat inainte sa ajunga pe disc."""

import atexit
import os
import re
import stat
import threading
import time


CALE_JURNAL = "/home/root/logs/hds-interfata.log"
MAX_OCTETI = 2 * 1024 * 1024
MAX_RAND = 16 * 1024
GRUP_OCTETI = 64 * 1024
INTERVAL = 5.0
_CITIRE = 8192
_ACTIV = None
_LACAT = threading.Lock()
_CONTROALE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|[\x00-\x08\x0b-\x1f\x7f]")


class Jurnal:

	def __init__(self, cale=CALE_JURNAL, maxim=MAX_OCTETI,
			interval=INTERVAL, grup=GRUP_OCTETI):
		# Fara toate filtrele nu se pastreaza niciun text brut.
		from Components.HdsAsistentaControl import mascheazaSecrete, mascheazaConturi
		from Components.HdsBetaTester import curata
		from Components.HdsDiagnostic import faraDatePersonale
		self._filtre = (mascheazaSecrete, mascheazaConturi, curata, faraDatePersonale)
		self.cale = cale
		self.maxim = max(64, min(MAX_OCTETI, int(maxim)))
		self.grup = max(64, min(self.maxim, int(grup)))
		self.interval = max(0.01, float(interval))
		self._rand = bytearray()
		self._prea_lung = False
		self._grup = bytearray()
		self._ultima_scriere = time.monotonic()
		os.makedirs(os.path.dirname(os.path.abspath(cale)), mode=0o700, exist_ok=True)
		for nume in (cale, cale + ".1", cale + ".2"):
			try:
				st = os.lstat(nume)
			except FileNotFoundError:
				continue
			if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
				raise OSError("jurnalul nu este un fisier obisnuit")
			if st.st_size > self.maxim:
				os.unlink(nume)
			else:
				os.chmod(nume, 0o600)
		fd = self._deschide()
		os.close(fd)
		self._ultima_scriere = time.monotonic()

	def _deschide(self):
		semne = (os.O_WRONLY | os.O_CREAT | os.O_APPEND
			| getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
		fd = os.open(self.cale, semne, 0o600)
		st = os.fstat(fd)
		if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
			os.close(fd)
			raise OSError("jurnalul nu este un fisier obisnuit")
		return fd

	def _adauga(self, text):
		ora = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
		for rand in text.splitlines():
			date = (ora + " " + rand + "\n").encode("utf-8", "replace")
			if len(date) > self.grup:
				# Taierea se face numai dupa mascare si la granita UTF-8.
				date = date[:self.grup - 1].decode("utf-8", "ignore").encode("utf-8") + b"\n"
			if len(self._grup) + len(date) > self.grup:
				self.goleste()
			self._grup.extend(date)
			if len(self._grup) >= self.grup:
				self.goleste()

	def _randIntreg(self):
		if self._prea_lung:
			self._adauga("[HdsJurnalInterfata] rand prea lung omis")
		else:
			text = _CONTROALE.sub("", self._rand.decode("utf-8", "replace"))
			try:
				for filtru in self._filtre:
					text = filtru(text)
				if text:
					self._adauga(text)
			except Exception:
				# O eroare de filtru nu permite salvarea randului brut.
				pass
		self._rand.clear()
		self._prea_lung = False

	def primeste(self, date):
		"""Bucati de octeti; un rand prea lung se omite pana la capat."""
		inceput = 0
		while inceput < len(date):
			sfarsit = date.find(b"\n", inceput)
			capat = len(date) if sfarsit < 0 else sfarsit
			if not self._prea_lung:
				if len(self._rand) + capat - inceput > MAX_RAND:
					self._rand.clear()
					self._prea_lung = True
				else:
					self._rand.extend(date[inceput:capat])
			if sfarsit < 0:
				break
			self._randIntreg()
			inceput = sfarsit + 1

	def verifica(self):
		if self._grup and time.monotonic() - self._ultima_scriere >= self.interval:
			self.goleste()

	def goleste(self):
		if not self._grup:
			return
		date = bytes(self._grup)
		self._grup.clear()
		self._ultima_scriere = time.monotonic()
		fd = None
		try:
			fd = self._deschide()
			if os.fstat(fd).st_size + len(date) > self.maxim:
				os.close(fd)
				fd = None
				if os.path.lexists(self.cale + ".1"):
					os.replace(self.cale + ".1", self.cale + ".2")
				os.replace(self.cale, self.cale + ".1")
				fd = self._deschide()
			pozitie = 0
			while pozitie < len(date):
				n = os.write(fd, date[pozitie:])
				if n <= 0:
					break
				pozitie += n
		except OSError:
			# Discul plin nu opreste citirea si nu mareste memoria.
			pass
		finally:
			if fd is not None:
				os.close(fd)

	def incheie(self):
		if self._rand or self._prea_lung:
			self._randIntreg()
		self.goleste()


class _Captura:

	def __init__(self, jurnal, citire, salvate):
		self.jurnal = jurnal
		self.citire = citire
		self.salvate = salvate
		self.stop = threading.Event()
		self.fir = threading.Thread(target=self._ruleaza, name="HdsJurnalInterfata", daemon=True)

	def _citeste(self):
		try:
			date = os.read(self.citire, _CITIRE)
			if date:
				self.jurnal.primeste(date)
			return bool(date)
		except (OSError, ValueError):
			return False

	def _ruleaza(self):
		try:
			while not self.stop.is_set():
				primit = self._citeste()
				self.jurnal.verifica()
				if not primit:
					self.stop.wait(0.25)
			# Oprirea nu asteapta dupa scriitori care continua sa vorbeasca.
			for _i in range(16):
				if not self._citeste():
					break
			self.jurnal.incheie()
		except Exception:
			# Descriptorul ramane deschis si daca firul nu mai poate lucra.
			# Scriitorii sunt neblocanti si nu primesc SIGPIPE.
			pass

	def opreste(self):
		if self.stop.is_set():
			return
		for tinta, vechi in zip((1, 2), self.salvate):
			try:
				os.dup2(vechi, tinta)
				os.close(vechi)
			except OSError:
				pass
		self.stop.set()
		self.fir.join(0.2)
		# Citirea ramane deschisa pana la iesirea procesului.


def porneste(cale=CALE_JURNAL):
	"""Abate stdout si stderr fara sa astepte scrierea pe disc."""
	global _ACTIV
	with _LACAT:
		if _ACTIV is not None:
			return _ACTIV
		citire = scriere = None
		salvate = []
		captura = None
		try:
			jurnal = Jurnal(cale)
			citire, scriere = os.pipe()
			os.set_blocking(citire, False)
			os.set_blocking(scriere, False)
			salvate.append(os.dup(1))
			salvate.append(os.dup(2))
			captura = _Captura(jurnal, citire, salvate)
			captura.fir.start()
			os.dup2(scriere, 1)
			os.dup2(scriere, 2)
			atexit.register(captura.opreste)
			_ACTIV = captura
			return captura
		except Exception:
			for tinta, vechi in zip((1, 2), salvate):
				try:
					os.dup2(vechi, tinta)
				except OSError:
					pass
			if captura is not None:
				captura.stop.set()
				if captura.fir.ident is not None:
					captura.fir.join(0.2)
			for fd in salvate:
				try:
					os.close(fd)
				except OSError:
					pass
			if citire is not None and (captura is None or not captura.fir.is_alive()):
				os.close(citire)
			return None
		finally:
			if scriere is not None:
				os.close(scriere)
