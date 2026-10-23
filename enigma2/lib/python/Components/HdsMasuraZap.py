# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsMasuraZap.py: cat tine, pe firul enigma2, fiecare pas Python al unei schimbari de canal pe televizor.
#
# La fiecare Navigation.playService se masoara, timp de FEREASTRA_S secunde de la inceput:
# - pasii zap-ului: controlul parental, oprirea serviciului vechi (cu evEnd) si extensiile de zap, pnav.playService
#   (tot ce cheama sincron: evStart, acordul, evTunedIn, pornirea decodorului din PID-urile tinute minte, evUpdatedInfo)
#   si tot playService;
# - fiecare ascultator al evenimentelor serviciului: cei din Navigation.event (dispatchEvent) si, separat, cei din
#   ServiceEventTracker (ecranele), adunati pe eveniment.
# Dupa fereastra zap-ul se scrie intr-un rand in FISIER (in /tmp, adica in memorie; ultimele PASTRATE zap-uri), cu
# ascultatorii care au luat cel putin PRAG_MS. Asa se vede pe receptor, fara profilare si fara repornire, ce lucru Python
# sta intre tasta si pornirea decodorului.
# Ceasul: time.monotonic(); "t0" din rand se leaga de /proc/uptime (acelasi ceas cat nu e standby adanc), iar prin el de
# ceasul decodorului (/proc/msp/syncNN, Systime).
# Costul: doua citiri de ceas pe ascultator, numai in fereastra; scrierea, una pe zap, dupa fereastra (eTimer).
# Modulul nu importa nimic din enigma la incarcare (probele de pe PC).

import os
import time

FISIER = "/tmp/hds-zap-timpi.txt"
FEREASTRA_S = 3.0
PASTRATE = 120
PRAG_MS = 3.0
CEI_MAI_MULTI = 12

_ceas = time.monotonic


def _ms(s):
	return int(round(s * 1000.0))


def numeAscultator(f):
	"""Numele scurt al unei functii sau metode: modul:Clasa.metoda."""
	try:
		sine = getattr(f, "__self__", None)
		fn = getattr(f, "__func__", f)
		nume = getattr(fn, "__qualname__", None) or getattr(fn, "__name__", None) or type(f).__name__
		if sine is not None and not isinstance(sine, type):
			nume = "%s.%s" % (type(sine).__name__, getattr(fn, "__name__", nume))
		modul = (getattr(fn, "__module__", "") or "").rsplit(".", 1)[-1]
		return "%s:%s" % (modul, nume) if modul else nume
	except Exception:
		return "?"


_NUME_EV = {}


def numeEveniment(ev):
	if not _NUME_EV:
		try:
			from enigma import iPlayableService
			for n in dir(iPlayableService):
				if n.startswith("ev"):
					v = getattr(iPlayableService, n)
					if isinstance(v, int):
						_NUME_EV.setdefault(v, n)
		except Exception:
			pass
	return _NUME_EV.get(ev, "ev%s" % (ev,))


class Zap(object):
	"""Masuratoarea unui zap: pasii (nume, inceput, durata) si ascultatorii {(eveniment, functie): durata}."""

	def __init__(self, ref, t0):
		self.ref = ref
		self.t0 = t0
		self.pasi = []
		self.nav = {}          # (ev, f) -> secunde, ascultatorii din Navigation.event
		self.ecrane = {}       # (ev, f) -> secunde, ascultatorii din ServiceEventTracker
		self.ev_total = {}     # ev -> secunde, tot dispatchEvent-ul evenimentului
		self.ev_in = []        # (inceput, durata) ale fiecarui dispatchEvent, pentru Python-ul din pnav.playService

	def rand(self):
		"""Randul scris in FISIER."""
		parti = ["zap t0=%.3f ref=%s" % (self.t0, self.ref)]
		pasi = []
		for nume, inceput, durata in self.pasi:
			text = "%s %d" % (nume, _ms(durata))
			if nume == "pnav.playService":
				py = sum(d for i, d in self.ev_in if inceput <= i < inceput + durata)
				text += " (Python in el %d)" % _ms(py)
			pasi.append(text)
		parti.append(", ".join(pasi) or "-")
		parti.append(", ".join("%s %d" % (numeEveniment(ev), _ms(s)) for ev, s in sorted(self.ev_total.items(),
			key=lambda x: -x[1])) or "-")
		for eticheta, harta in (("nav", self.nav), ("ecrane", self.ecrane)):
			mari = sorted(((s, ev, f) for (ev, f), s in harta.items() if s * 1000.0 >= PRAG_MS), key=lambda x: -x[0])
			if mari:
				parti.append("%s: %s" % (eticheta, ", ".join("%s/%s %d" % (numeEveniment(ev), numeAscultator(f), _ms(s))
					for s, ev, f in mari[:CEI_MAI_MULTI])))
		return " | ".join(parti)


class Masura(object):
	def __init__(self, fisier=FISIER):
		self.fisier = fisier
		self.zap = None
		self.randuri = []
		self.timer = None

	def activ(self):
		z = self.zap
		return z is not None and _ceas() - z.t0 < FEREASTRA_S

	def incepe(self, ref):
		"""Un zap nou incepe acum (Navigation.playService); cel de dinainte, daca n-a fost scris, se scrie acum."""
		if self.zap is not None:
			self.scrie()
		self.zap = Zap(ref, _ceas())
		try:
			if self.timer is None:
				from enigma import eTimer
				self.timer = eTimer()
				self.timer.callback.append(self.scrie)
			self.timer.start(int(FEREASTRA_S * 1000) + 100, True)
		except Exception:
			self.timer = None

	def pas(self, nume, inceput, durata):
		if self.zap is not None:
			self.zap.pasi.append((nume, inceput, durata))

	def eveniment(self, ev, inceput, durata):
		z = self.zap
		if z is not None:
			z.ev_total[ev] = z.ev_total.get(ev, 0.0) + durata
			z.ev_in.append((inceput, durata))

	def ascultator(self, ev, f, durata, ecran=False):
		z = self.zap
		if z is not None:
			harta = z.ecrane if ecran else z.nav
			cheie = (ev, f)
			harta[cheie] = harta.get(cheie, 0.0) + durata

	def scrie(self):
		"""Zap-ul de acum intra in FISIER (ultimele PASTRATE randuri, scrise intregi: .nou si os.replace). Nu arunca."""
		z, self.zap = self.zap, None
		if z is None:
			return
		try:
			self.randuri.append(z.rand())
			del self.randuri[:-PASTRATE]
			nou = self.fisier + ".nou"
			with open(nou, "w", encoding="utf-8") as f:
				f.write("# timpii zap-urilor pe firul enigma2, ms (Components/HdsMasuraZap.py); cel mai nou la sfarsit\n")
				f.write("\n".join(self.randuri) + "\n")
			os.replace(nou, self.fisier)
		except Exception as e:
			print("[HdsMasuraZap] scrierea: %r" % (e,))


masura = Masura()
