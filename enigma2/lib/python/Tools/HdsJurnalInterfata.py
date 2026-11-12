# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com & hdsatelit.com
# SPDX-License-Identifier: GPL-2.0-only

"""Jurnal mic al iesirii interfetei, cu parolele ascunse inainte sa ajunga pe disc.

Eduard, 12.11.2026 19:17 si 19:19 („eu am spus sa fie tot, tot, tot”; „FARA PAROLE, ATAT”): jurnalul de pe receptor
pastreaza tot (randurile modulelor de acces, ECM, utilizatorii, adresele, MAC-urile, caile), numai parolele devin ***
(Components/HdsAsistentaControl.mascheazaParole). Inainte treceau aici si curata() din HdsBetaTester si
faraDatePersonale() din HdsDiagnostic; ele raman la plecare, pe drumurile care ies din receptor (pachetele testerilor,
codurile QR, rapoartele de pe forum), deci ce iese public nu se schimba.

Costul ramane mic si cand un plugin scrie mult (raportul 388460, 0.7.3: firul lua 16% dintr-un nucleu pe SF8008 cat
JediMakerXtream isi reimprospata buchetele). Fiecare rand trece prin filtrul parolelor (pana la 12.11.2026 erau patru
filtre, ~70-90 us pe rand pe PC, de cateva ori mai mult pe receptor), deci:
- rezultatul filtrelor se tine minte pentru randurile care se repeta (68-88% din randurile jurnalelor reale);
- filtrele au un buget de timp (in medie BUGET_PROCENT dintr-un nucleu, cu o rafala de BUGET_RAFALA secunde). Peste el,
  randurile obisnuite se numara si se sar, iar in locul lor se scrie „N randuri sarite”; randurile de eroare (si blocul
  Traceback) trec in continuare prin toate filtrele, cu o rezerva proprie (BUGET_REZERVA), ca nici ele sa nu poata
  tine firul ocupat la nesfarsit.
"""

import atexit
import os
import re
import stat
import threading
import time
from functools import lru_cache


CALE_JURNAL = "/home/root/logs/hds-interfata.log"
MAX_OCTETI = 2 * 1024 * 1024
MAX_RAND = 16 * 1024
GRUP_OCTETI = 64 * 1024
INTERVAL = 5.0
# Bugetul filtrelor: cat timp de filtrare se aduna pe secunda (0.03 = 3% dintr-un nucleu), cat se poate strange cand
# jurnalul e linistit (o rafala: pornirea, un zap, o scanare scurta) si cat mai pot lua, peste el, randurile de eroare.
# Rafala de 3 s: pe receptor (Viper 4K V20, acelasi cip ca SF8008) un rand costa ~3,6 ms, de 40-50 de ori cel de pe PC
# (masurat pe .122: modulul vechi lua 36,5% dintr-un nucleu la 100 de randuri pe secunda). Reluate cu filtrele de 50 de
# ori mai scumpe, jurnalele reale (si cu o pornire) trec cu 3 s fara niciun rand sarit; cu 2 s sareau 12-280 de randuri.
BUGET_PROCENT = 0.03
BUGET_RAFALA = 3.0
BUGET_REZERVA = 0.5
# Rezultatul filtrelor tinut minte: atatea randuri, numai cele scurte (un rand de 16 KiB nu ocupa memoria).
CACHE_RANDURI = 1024
CACHE_LUNGIME = 512
# Un bloc Traceback se pastreaza pana la primul rand neindentat, dar nu mai mult de atatea randuri.
BLOC_MAXIM = 200
_CITIRE = 64 * 1024
# Asteptarea dintre citiri cand teava e goala: 0,25 s de obicei. Dupa o citire mare (un val: peste un sfert de teava),
# citirile se fac la 20 ms cat tine valul (si inca 0,5 s dupa), altfel teava de 64 KiB se umple in asteptare si
# scriitorii pierd randuri, si pe cele de eroare. Valul tine cat vin macar 4 KiB intre doua citiri (~200 KiB/s); cateva
# randuri rare dupa el nu il tin pornit, deci in mers obisnuit (cativa KiB pe secunda) ramane 0,25 s.
PAUZA = 0.25
VAL_OCTETI = 16 * 1024
VAL_TINE = 4 * 1024
VAL_PAUZA = 0.02
VAL_ASTEPTARI = 25
_ACTIV = None
_LACAT = threading.Lock()
_CONTROALE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|[\x00-\x08\x0b-\x1f\x7f]")
# Inceputul unei stive: Traceback-ul Python si firele scrise de faulthandler („Current thread 0x... (most recent call
# first):”).
_STIVA = b"most recent call"
# Cuvintele de eroare: aceleasi ca in HdsBetaTester._CUVINTE_EROARE (cine alege jurnalele de trimis), plus stiva.
_EROARE_REZERVA = r"eroare|esec|eșec|error|fail|cazut|căzut|blocat|timeout|traceback|exception"
TEXT_SARITE = "[HdsJurnalInterfata] %d randuri sarite (prea multe pe secunda, erorile raman)"


def _cuvinteEroare():
	"""Cuvintele de eroare ca octeti cu litere mici. Cautarea se face pe octeti, inainte de filtre, si trebuie sa coste
	foarte putin: pe textul cu litere mici (bytes.lower) cu find pe fiecare cuvant, de ~15 ori mai repede decat o
	expresie cu re.I (masurat pe PC: 4,5 ms/MiB fata de 65 ms/MiB)."""
	cuvinte = _EROARE_REZERVA.split("|")
	try:
		from Components.HdsBetaTester import _CUVINTE_EROARE
		alese = _CUVINTE_EROARE.pattern.split("|")
		# numai daca expresia e o simpla insiruire de cuvinte (altfel lista de mai sus)
		if alese and all(c and re.escape(c) == c for c in alese):
			cuvinte = alese
	except Exception:
		pass
	return tuple(sorted(set(c.lower().encode("utf-8") for c in cuvinte) | {_STIVA}))


class Jurnal:

	def __init__(self, cale=CALE_JURNAL, maxim=MAX_OCTETI,
			interval=INTERVAL, grup=GRUP_OCTETI, procent=BUGET_PROCENT,
			rafala=BUGET_RAFALA, rezerva=BUGET_REZERVA, ceas=None, procesor=None):
		# Fara filtrul parolelor nu se pastreaza niciun text brut (importul cade, jurnalul nu porneste).
		from Components.HdsAsistentaControl import mascheazaParole
		self._filtre = (mascheazaParole,)
		self._cuvinte = _cuvinteEroare()
		self._eroare = re.compile(b"|".join(re.escape(c) for c in self._cuvinte))
		# Filtrele sunt functii pure: acelasi rand da acelasi rezultat. O exceptie nu se tine minte.
		self._filtreazaCache = lru_cache(maxsize=CACHE_RANDURI)(self._filtreaza)
		self.cale = cale
		self.maxim = max(64, min(MAX_OCTETI, int(maxim)))
		self.grup = max(64, min(self.maxim, int(grup)))
		self.interval = max(0.01, float(interval))
		self.procent = max(0.001, float(procent))
		self.rafala = max(0.001, float(rafala))
		self.rezerva = max(0.0, float(rezerva))
		# Bugetul creste cu timpul trecut (ceas) si scade cu timpul de procesor al firului cat filtreaza (procesor). Nu
		# cu timpul trecut: cat firul asteapta GIL-ul dupa firul interfetei, nu consuma nimic din nucleu.
		self._ceas = ceas or time.monotonic
		self._procesor = procesor or getattr(time, "thread_time", None) or time.perf_counter
		self._buget = self.rafala
		self._ultim_buget = self._ceas()
		self._sarite = 0
		self._sarite_de_la = None
		self._bloc = 0
		self._ora_sec = None
		self._ora = ""
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
		acum = int(time.time())
		if acum != self._ora_sec:
			self._ora_sec = acum
			self._ora = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(acum))
		for rand in text.splitlines():
			date = (self._ora + " " + rand + "\n").encode("utf-8", "replace")
			if len(date) > self.grup:
				# Taierea se face numai dupa mascare si la granita UTF-8.
				date = date[:self.grup - 1].decode("utf-8", "ignore").encode("utf-8") + b"\n"
			if len(self._grup) + len(date) > self.grup:
				self.goleste()
			self._grup.extend(date)
			if len(self._grup) >= self.grup:
				self.goleste()

	def _filtreaza(self, text):
		# self._filtre se citeste la fiecare chemare (probele il schimba dupa pornire)
		for filtru in self._filtre:
			text = filtru(text)
		return text

	def _reumple(self):
		acum = self._ceas()
		if acum > self._ultim_buget:
			self._buget = min(self.rafala, self._buget + (acum - self._ultim_buget) * self.procent)
		self._ultim_buget = acum

	def _faraBuget(self):
		"""Bugetul randurilor obisnuite e gol (cele de eroare mai au rezerva)."""
		self._reumple()
		return self._buget <= 0

	def _scrieSarite(self):
		if self._sarite:
			n = self._sarite
			self._sarite = 0
			self._sarite_de_la = None
			self._adauga(TEXT_SARITE % n)

	def _sare(self, n=1):
		if not self._sarite:
			self._sarite_de_la = time.monotonic()
		self._sarite += n

	def _deStiva(self, rand):
		"""Randul e dintr-o stiva (Traceback, faulthandler): inceputul ei, randurile indentate de dupa si primul rand
		neindentat, care o inchide (tipul exceptiei, „ValueError: ...”). Starea se tine la fiecare rand, si cand bugetul
		ajunge, ca o stiva inceputa sa se pastreze intreaga daca bugetul se termina la jumatatea ei."""
		if self._bloc:
			if rand[:1] in (b" ", b"\t"):
				self._bloc -= 1
				return True
			self._bloc = BLOC_MAXIM if _STIVA in rand else 0
			return True
		if _STIVA in rand:
			self._bloc = BLOC_MAXIM
			return True
		return False

	def _randIntreg(self):
		if self._prea_lung:
			self._adauga("[HdsJurnalInterfata] rand prea lung omis")
		else:
			de_eroare = self._deStiva(self._rand)
			self._reumple()
			if not de_eroare and self._buget <= 0:
				# cuvintele de eroare se cauta numai cand bugetul obisnuit s-a terminat
				de_eroare = self._eroare.search(self._rand.lower()) is not None
			if self._buget > (-self.rezerva if de_eroare else 0):
				self._scrieSarite()
				inceput = self._procesor()
				text = _CONTROALE.sub("", self._rand.decode("utf-8", "replace"))
				try:
					if len(text) <= CACHE_LUNGIME:
						text = self._filtreazaCache(text)
					else:
						text = self._filtreaza(text)
					if text:
						self._adauga(text)
				except Exception:
					# O eroare de filtru nu permite salvarea randului brut.
					pass
				self._buget -= max(0.0, self._procesor() - inceput)
			else:
				self._sare()
		self._rand.clear()
		self._prea_lung = False

	def _litereMici(self, date):
		return date.lower()

	def _primaEroare(self, jos, urm, inceput, sfarsit):
		"""Pozitia primului cuvant de eroare din jos[inceput:sfarsit] (bucata cu litere mici), sau -1. `urm` tine pentru
		fiecare cuvant urmatoarea lui pozitie (-1: nu mai apare pana la sfarsit), ca bucata sa se cerceteze o singura data
		si cand fiecare rand are un cuvant de eroare (fara asta, fiecare rand ar cauta din nou tot restul bucatii)."""
		prima = -1
		for c in self._cuvinte:
			p = urm.get(c)
			if p is None or 0 <= p < inceput:
				p = urm[c] = jos.find(c, inceput, sfarsit)
			if p >= 0 and (prima < 0 or p < prima):
				prima = p
		return prima

	def primeste(self, date):
		"""Bucati de octeti; un rand prea lung se omite pana la capat."""
		inceput = 0
		jos = urm = None
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
			if inceput < len(date) and not self._bloc and self._faraBuget():
				# Fara buget: randurile complete pana la primul cuvant de eroare se sar dintr-o singura cautare.
				ultim = date.rfind(b"\n", inceput)
				if ultim >= inceput:
					if self._buget <= -self.rezerva:
						# nici randurile de eroare nu mai au loc: toate randurile complete se numara, fara cautare
						p = -1
					else:
						if jos is None:
							jos, urm = self._litereMici(date), {}
						p = self._primaEroare(jos, urm, inceput, ultim + 1)
					sari = ultim + 1 if p < 0 else date.rfind(b"\n", inceput, p) + 1
					if sari > inceput:
						self._sare(date.count(b"\n", inceput, sari))
						inceput = sari

	def verifica(self):
		# Un val lung de randuri sarite se spune macar o data la INTERVAL, nu abia la sfarsitul lui.
		if self._sarite and time.monotonic() - self._sarite_de_la >= self.interval:
			self._scrieSarite()
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
		self._scrieSarite()
		self.goleste()


class _Captura:

	def __init__(self, jurnal, citire, salvate):
		self.jurnal = jurnal
		self.citire = citire
		self.salvate = salvate
		self.stop = threading.Event()
		self._val = 0
		self.fir = threading.Thread(target=self._ruleaza, name="HdsJurnalInterfata", daemon=True)

	def _citeste(self):
		try:
			date = os.read(self.citire, _CITIRE)
			if date:
				self.jurnal.primeste(date)
			return len(date)
		except (OSError, ValueError):
			return 0

	def _pauza(self, primit):
		"""Cat se asteapta dupa o citire de `primit` octeti (0: se citeste din nou imediat)."""
		if primit:
			if primit >= VAL_OCTETI or (self._val and primit >= VAL_TINE):
				self._val = VAL_ASTEPTARI
			return 0
		if self._val:
			self._val -= 1
			return VAL_PAUZA
		return PAUZA

	def _ruleaza(self):
		try:
			while not self.stop.is_set():
				primit = self._citeste()
				self.jurnal.verifica()
				pauza = self._pauza(primit)
				if pauza:
					self.stop.wait(pauza)
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
