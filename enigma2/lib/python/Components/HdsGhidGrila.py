# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsGhidGrila: logica ghidului TV grafic (grila canale x ore), aceeasi pentru ecranul de pe televizor
# (Screens/HdsGhidGrafic.py) si pentru pagina web (HdsWebControl/ghid_web.py, /ghid?vedere=grila). Scris de la zero
# (hotararea lui Eduard, 26.11.2026: ce era al pluginurilor Dream se rescrie, nimic copiat).
#
# Cum ramane rapid pe receptoarele slabe (ZGEMMA H8, Vu+ Solo SE):
#   - ghidul se citeste din cache-ul EPG al imaginii (eEPGCache) cu UN singur apel lookupEvent pentru toate canalele
#     cerute si o fereastra de timp (C++: startTimeQuery pe fiecare canal, numai emisiunile din fereastra);
#   - se cer numai canalele care se vad (o pagina de randuri) si o fereastra de doua ori cat se vede; pagina urmatoare
#     se citeste dupa desenare, din ceasul ecranului (citesteInAvans), nu pe un fir;
#   - ce s-a citit se tine minte (Memorie): o sageata in interiorul ferestrei nu cere nimic de la cache;
#   - blocurile unui rand se calculeaza din memorie la desenarea randului (blocuri), fara nicio cautare.
#
# Modulul nu importa nimic din enigma2 la incarcare: probele de pe PC dau un cache simulat (lookupEvent).

import time

PAS = 30 * 60                 # treapta riglei si a alinierii ferestrei: o jumatate de ora
VEDERE_IMPLICITA = 120 * 60   # cat se vede pe ecran: doua ore
ZI = 86400
ZILE = 7                      # cat de departe merge ghidul (cache-ul tine de obicei 7 zile)
MAX_RANDURI_MEMORIE = 400     # canalele tinute minte (cate o fereastra pe canal)
DURATA_MINIMA = 60            # o emisiune cu durata 0 din EIT se deseneaza ca un minut
FORMAT = "RIBDT"


def aliniaza(t, pas=PAS):
	"""Inceputul jumatatii de ora (dupa ceasul local) in care cade t: rigla incepe la :00 sau :30 si in tarile cu
	ora decalata cu 30 sau 45 de minute fata de UTC."""
	t = int(t)
	lt = time.localtime(t)
	sec = (lt.tm_min * 60 + lt.tm_sec) % pas
	return t - sec


def cheie(ref):
	"""Cheia unui canal: referinta fara numele de la coada (toCompareString), ca text."""
	if ref is None:
		return ""
	if not isinstance(ref, str):
		if hasattr(ref, "ref"):
			ref = ref.ref
		if hasattr(ref, "toCompareString"):
			return ref.toCompareString()
		ref = str(ref)
	return ref


def cheieDvb(ref):
	"""Serviciul fara felul lui, fara cale si nume: SID:TSID:ONID:spatiu (campurile 3-6), cu litere mari. Cautarea in ghid
	intoarce referinta canalului asa cum o tine cache-ul (de pilda fara calea releului de flux din buchet), deci randul
	se gaseste dupa ea."""
	campuri = cheie(ref).split(":")
	if len(campuri) < 7:
		return ""
	rez = ":".join(c.upper().lstrip("0") or "0" for c in campuri[3:7])
	return "" if rez == "0:0:0:0" else rez


def citeste(epg, refs, inceput, sfarsit):
	"""{ref: [(id, inceput, durata, titlu), ...]} pentru canalele date, emisiunile care se vad in [inceput, sfarsit).
	UN singur apel la cache pentru toate canalele. Canalele fara nimic primesc lista goala."""
	rez = dict((r, []) for r in refs)
	if not refs or epg is None:
		return rez
	minute = max(1, (int(sfarsit) - int(inceput) + 59) // 60)
	cerere = [FORMAT]
	cerere.extend((r, 0, int(inceput), minute) for r in refs)
	try:
		randuri = epg.lookupEvent(cerere) or []
	except Exception as e:
		print("[HdsGhidGrila] lookupEvent: %s" % e)
		return rez
	for rand in randuri:
		try:
			r, eid, b, d, t = rand
		except (TypeError, ValueError):
			continue
		if eid is None or b is None:
			continue
		lista = rez.get(r)
		if lista is None:
			# subserviciu trimis la canalul parinte: cheia lui, ca sa ajunga tot pe randul cerut
			lista = rez.setdefault(r, [])
		lista.append((int(eid), int(b), max(int(d or 0), 0), t or ""))
	for lista in rez.values():
		lista.sort(key=lambda x: x[1])
	return rez


class Memorie(object):
	"""Ce s-a citit din cache, pe canal: fereastra [a, b) si emisiunile ei. Numarul apelurilor e tinut pentru masurare."""

	def __init__(self, epg, maxim=MAX_RANDURI_MEMORIE):
		self.epg = epg
		self.maxim = maxim
		self.date = {}         # ref -> (a, b, emisiuni)
		self.ordine = []
		self.apeluri = 0       # cate apeluri lookupEvent (masurare)
		self.canale_cerute = 0

	def uita(self):
		self.date.clear()
		del self.ordine[:]

	def are(self, ref, a, b):
		e = self.date.get(ref)
		return e is not None and e[0] <= a and e[1] >= b

	def emisiuni(self, ref):
		e = self.date.get(ref)
		return e[2] if e is not None else None

	def acopera(self, ref):
		e = self.date.get(ref)
		return (e[0], e[1]) if e is not None else None

	def cere(self, refs, a, b, b_citire=None):
		"""Canalele care n-au [a, b) se citesc, intr-un singur apel, pe [a, b_citire) (mai departe decat se vede, ca
		mutarile urmatoare ale ferestrei sa nu mai ceara). Intoarce cate canale s-au cerut (0 = nimic din cache)."""
		lipsa = [r for r in refs if r and not self.are(r, a, b)]
		if not lipsa:
			return 0
		b_citire = max(b, b_citire or b)
		citite = citeste(self.epg, lipsa, a, b_citire)
		self.apeluri += 1
		self.canale_cerute += len(lipsa)
		for r in lipsa:
			self._pune(r, a, b_citire, citite.get(r, []))
		return len(lipsa)

	def extinde(self, ref, b_nou):
		"""Fereastra unui canal dusa mai departe, pana la b_nou (sageata dreapta dupa ultima emisiune citita)."""
		e = self.date.get(ref)
		if e is None or e[1] >= b_nou:
			return False
		a, b, vechi = e
		noi = citeste(self.epg, [ref], b, b_nou).get(ref, [])
		self.apeluri += 1
		self.canale_cerute += 1
		vazute = set(x[0] for x in vechi)
		lista = list(vechi) + [x for x in noi if x[0] not in vazute]
		lista.sort(key=lambda x: x[1])
		self.date[ref] = (a, b_nou, lista)
		return True

	def extindeInapoi(self, ref, a_nou):
		e = self.date.get(ref)
		if e is None or e[0] <= a_nou:
			return False
		a, b, vechi = e
		noi = citeste(self.epg, [ref], a_nou, a).get(ref, [])
		self.apeluri += 1
		self.canale_cerute += 1
		vazute = set(x[0] for x in vechi)
		lista = [x for x in noi if x[0] not in vazute] + list(vechi)
		lista.sort(key=lambda x: x[1])
		self.date[ref] = (a_nou, b, lista)
		return True

	def _pune(self, ref, a, b, lista):
		if ref not in self.date:
			self.ordine.append(ref)
			while len(self.ordine) > self.maxim:
				self.date.pop(self.ordine.pop(0), None)
		self.date[ref] = (a, b, lista)


def sfarsitul(ev):
	return ev[1] + max(ev[2], DURATA_MINIMA)


def vizibile(emisiuni, t0, t1):
	"""Emisiunile care se vad in [t0, t1), in ordine."""
	if not emisiuni:
		return []
	return [e for e in emisiuni if e[1] < t1 and sfarsitul(e) > t0]


def blocuri(emisiuni, t0, t1, x0, latime, spatiu=2, minim=3):
	"""[(x, latime, emisiune)] pentru randul care incepe la x0 si are `latime` pixeli pentru [t0, t1). Capetele taiate
	la marginea ferestrei; `spatiu` pixeli liberi intre blocuri; blocurile mai inguste de `minim` nu se deseneaza."""
	rez = []
	if latime <= 0 or t1 <= t0:
		return rez
	pe_sec = float(latime) / (t1 - t0)
	for e in vizibile(emisiuni, t0, t1):
		a = max(e[1], t0)
		b = min(sfarsitul(e), t1)
		x = x0 + int(round((a - t0) * pe_sec))
		xb = x0 + int(round((b - t0) * pe_sec))
		w = xb - x - (spatiu if b < t1 else 0)
		if w >= minim:
			rez.append((x, w, e))
	return rez


def xTimp(t, t0, t1, x0, latime):
	"""Pozitia pe orizontala a momentului t, sau None in afara ferestrei."""
	if t < t0 or t >= t1 or t1 <= t0:
		return None
	return x0 + int((t - t0) * float(latime) / (t1 - t0))


def laTimp(emisiuni, t):
	"""Indexul emisiunii care tine la momentul t; altfel prima care incepe dupa t; altfel ultima inainte; -1 fara."""
	if not emisiuni:
		return -1
	dupa = -1
	for i, e in enumerate(emisiuni):
		if e[1] <= t < sfarsitul(e):
			return i
		if e[1] > t and dupa < 0:
			dupa = i
	if dupa >= 0:
		return dupa
	return len(emisiuni) - 1


def indexDupaId(emisiuni, eid):
	if emisiuni:
		for i, e in enumerate(emisiuni):
			if e[0] == eid:
				return i
	return -1


def fereastraPentru(ev, t0, vedere, minim):
	"""Noul inceput al ferestrei ca emisiunea aleasa sa se vada: ramane t0 daca se vede deja; altfel fereastra se
	muta cu cate o jumatate de vedere (aliniata), nu mai devreme de `minim`."""
	t1 = t0 + vedere
	b = sfarsitul(ev)
	if ev[1] < t1 and b > t0:
		return t0
	jumatate = max(PAS, (vedere // 2) // PAS * PAS)
	if ev[1] >= t1:
		while ev[1] >= t0 + vedere:
			t0 += jumatate
	else:
		while b <= t0 and t0 - jumatate >= minim:
			t0 -= jumatate
		if b <= t0:
			t0 = minim
	return t0


def ore(t0, t1, pas=PAS):
	"""Marcajele riglei: [(t, "HH:MM")] din jumatate in jumatate de ora."""
	rez = []
	t = aliniaza(t0, pas)
	if t < t0:
		t += pas
	while t < t1:
		lt = time.localtime(t)
		rez.append((t, "%02d:%02d" % (lt.tm_hour, lt.tm_min)))
		t += pas
	return rez


def marcajeTemporizatoare(timere, refs_set=None):
	"""Din lista temporizatoarelor (RecordTimer.timer_list): {ref: [(inceput, sfarsit, eit, justplay)]}. Se face o data
	pe fereastra (si cand se schimba un temporizator), nu la fiecare bloc desenat."""
	rez = {}
	for t in timere or []:
		try:
			ref = cheie(t.service_ref)
			if refs_set is not None and ref not in refs_set:
				continue
			if getattr(t, "disabled", False):
				continue
			rez.setdefault(ref, []).append((int(t.begin), int(t.end), getattr(t, "eit", None),
				bool(getattr(t, "justplay", False))))
		except Exception:
			continue
	return rez


def felTemporizator(marcaje, ref, ev):
	"""'inregistrare', 'comutare' sau '' pentru o emisiune: acelasi eit, sau temporizatorul acopera mijlocul ei."""
	lista = marcaje.get(ref) if marcaje else None
	if not lista:
		return ""
	mijloc = ev[1] + max(ev[2], DURATA_MINIMA) // 2
	for b, e, eit, jp in lista:
		if (eit is not None and eit == ev[0]) or (b <= mijloc < e and b < sfarsitul(ev) and e > ev[1]):
			return "comutare" if jp else "inregistrare"
	return ""


def ziua(t, acum, numeZile, azi, maine):
	"""'Azi', 'Mâine' sau numele zilei, cu data: 'Joi 26.11'."""
	a = time.localtime(acum)
	b = time.localtime(t)
	import datetime
	d = (datetime.date(b.tm_year, b.tm_mon, b.tm_mday) - datetime.date(a.tm_year, a.tm_mon, a.tm_mday)).days
	if d == 0:
		nume = azi
	elif d == 1:
		nume = maine
	else:
		nume = numeZile[b.tm_wday]
	return "%s %d.%02d" % (nume, b.tm_mday, b.tm_mon)


def hhmm(t):
	lt = time.localtime(t)
	return "%02d:%02d" % (lt.tm_hour, lt.tm_min)
