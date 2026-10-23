# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsInformatiiTabel: ecranele "Informatii despre sistem" (Screens/Information.py) ca tabele, din textul pe care il
# scrie populate() al fiecarui ecran (acelasi text e "textul brut" de pe tasta ALBASTRU si din pagina web). Folosit de
# ecranul de pe televizor (doua coloane, ca Informatii HDMI) si de pagina web /informatii
# (HdsWebControl/informatii_tabel_web.py), deci amandoua arata aceleasi randuri. Ecranele de pe televizor rup textele
# lungi pe mai multe randuri (rupt) si le deruleaza pe pagini; pagina web le rupe singura.
#
# Forma textului (o scrie populate()):
#   "Titlu:"                    la inceputul randului: o sectiune noua
#   " Subtitlu"                 un singur spatiu, fara ":" si fara "•": un subtitlu in sectiune (grupele de functii)
#   "  Eticheta:   valoare"     cu spatii in fata: un rand eticheta / valoare (desparte primul ": "); cu "•", numai
#                               cand valoarea e aliniata (cel putin doua spatii dupa ":")
#   "  • text"                  un rand fara valoare (si "  • propozitie: cu doua puncte")
#   "-----" si randurile goale se sar. O valoare cu un procent la sfarsit, "(33%)" sau "33%", la etichetele de ocupare
#   primeste si o bara (procentul).
import re

_LINIE = re.compile(r"^[-=\s]+$")
_PROCENT = re.compile(r"\(?(\d{1,3})\s?%\)?\s*$")
_BARA_VECHE = re.compile(r"\[[#\-]+\]\s*(\d{1,3})%")


def _procent(valoare, eticheta):
	m = _BARA_VECHE.search(valoare)
	if m:
		return int(m.group(1))
	if not re.search(r"(?i)(folosit|ocupat|utiliz|used)", eticheta + " " + valoare):
		return None
	m = _PROCENT.search(valoare)
	if m and 0 <= int(m.group(1)) <= 100:
		return int(m.group(1))
	return None


def sectiuni(text):
	"""[{"titlu": text, "randuri": [{"eticheta", "valoare", "bara"} | {"subtitlu"}]}] din textul unui ecran."""
	rez = []
	curenta = None
	for linie in (text or "").replace("\r", "").split("\n"):
		if not linie.strip() or _LINIE.match(linie):
			continue
		spatii = len(linie) - len(linie.lstrip(" "))
		curat = linie.strip()
		if spatii == 0:
			curenta = {"titlu": curat[:-1].strip() if curat.endswith(":") else curat, "randuri": []}
			rez.append(curenta)
			continue
		if curenta is None:
			curenta = {"titlu": "", "randuri": []}
			rez.append(curenta)
		marcat = curat.startswith("•")
		if marcat:
			curat = curat[1:].strip()
		if spatii == 1 and not marcat and ": " not in curat:
			curenta["randuri"].append({"subtitlu": curat.rstrip(":")})
			continue
		# un rand cu "•" se desparte numai cand valoarea e aliniata (doua spatii dupa ":"); altfel e o propozitie
		# ("• Numarul mare nu inseamna...: ...", functiile receptorului) si ramane intreaga
		if ": " in curat and (not marcat or re.search(r":\s{2,}", curat)):
			eticheta, valoare = curat.split(": ", 1)
			eticheta, valoare = eticheta.strip(), valoare.strip()
			m = _BARA_VECHE.search(valoare)
			bara = _procent(valoare, eticheta)
			if m:
				valoare = "%d%%" % bara
			curenta["randuri"].append({"eticheta": eticheta, "valoare": valoare, "bara": bara})
		else:
			curenta["randuri"].append({"eticheta": curat.rstrip(":"), "valoare": "", "bara": None})
	return [s for s in rez if s["randuri"] or s["titlu"]]


def randuri(sect):
	"""Sectiunile ca lista plata pentru o lista desenata: ("titlu", t), ("subtitlu", t), ("rand", e, v),
	("bara", procent)."""
	rez = []
	for s in sect:
		if rez:
			rez.append(("gol",))
		if s["titlu"]:
			rez.append(("titlu", s["titlu"]))
		for r in s["randuri"]:
			if "subtitlu" in r:
				rez.append(("subtitlu", r["subtitlu"]))
				continue
			rez.append(("rand", r["eticheta"], r["valoare"]))
			if r.get("bara") is not None:
				rez.append(("bara", r["bara"]))
	return rez


def coloane(sect, n=2):
	"""Randurile impartite pe `n` coloane, la granita unei sectiuni, cat mai egal."""
	plat = randuri(sect)
	if n <= 1 or not plat:
		return [plat]
	inceputuri = [i for i, r in enumerate(plat) if r[0] == "titlu"] or [0]
	tinta = len(plat) / float(n)
	taieturi = []
	for k in range(1, n):
		cel = min(inceputuri, key=lambda i: abs(i - tinta * k)) if inceputuri else 0
		if cel > (taieturi[-1] if taieturi else 0):
			taieturi.append(cel)
	rez, start = [], 0
	for t in taieturi:
		col = plat[start:t]
		while col and col[-1][0] == "gol":
			col.pop()
		rez.append(col)
		start = t
	rez.append(plat[start:])
	while len(rez) < n:
		rez.append([])
	return rez



# Celulele tabelului de pe televizor (Screens/Information.py) au latimi fixe, iar enigma2 al nostru nu are RT_ELLIPSIS
# (lib/gdi/grc.h: numai RT_WRAP, care intr-un rand de lista cu inaltime fixa nu arata al doilea rand): un text mai lung
# decat celula era taiat la margine, fara semn (de exemplu „HiSilicon Hi3798MV200
# (15000 DMII” la 115% si 130% din marimea textului). Textul se masoara cu latimile literelor fontului
# (Components/HdsLatimeText, tabelele facute din .ttf) la marimea de acum, cu marimea textului aplicata, si cand nu
# incape se scurteaza cu „…” la capat. Textul intreg ramane in textul brut (ALBASTRU) si in pagina web /informatii.
# Numele vechi de fonturi din skin („Regular”, „Bold”, „Fixed”) sunt aceleasi fisiere ca HdsRegular, HdsBold, HdsCond.
FAMILII = {"Regular": "HdsRegular", "RegularHD": "HdsRegular", "Bold": "HdsBold", "Fixed": "HdsCond"}
_LT = []


def _latimeText():
	if not _LT:
		try:
			from Components import HdsLatimeText as L
		except ImportError:
			import importlib.util
			import os
			cale = os.path.join(os.path.dirname(os.path.abspath(__file__)), "HdsLatimeText.py")
			spec = importlib.util.spec_from_file_location("HdsLatimeText", cale)
			L = importlib.util.module_from_spec(spec)
			spec.loader.exec_module(L)
		_LT.append(L)
	return _LT[0]


def marja(latime):
	"""Cativa pixeli lasati liberi la dreapta celulei: suma avansurilor poate iesi cu putin sub textul asezat."""
	return max(4, latime // 50)


def scurtat(text, latime, font="HdsCond", marime=28):
	"""Textul unei celule de `latime` puncte: intreg cand incape (cu marja), altfel scurtat cu „…” la capat."""
	if not text or latime <= 0:
		return text
	return _latimeText().scurteaza(text, max(1, latime - marja(latime)), FAMILII.get(font, font), int(marime))


# Textele lungi pe mai multe randuri (de exemplu ecranul „Despre imagine”: randul de contact si functiile lungi se
# vedeau numai pana la „…”, intregi doar in textul brut). Ecranele de pe televizor (Screens/Information.py,
# Screens/HdsHdmiInfo.py) rup un rand prea lung in mai multe randuri ale listei, cu aceleasi masuri ca scurtat(), deci
# fiecare bucata incape in celula ei si nu mai e scurtata; scurtat() ramane numai pentru titluri si etichete.

def rupt(text, latime, font="HdsCond", marime=28, latime_urmare=None):
	"""Textul pe randuri care incap: primul in `latime` puncte, urmatoarele in `latime_urmare` (implicit tot
	`latime`), fiecare cu marja lui. Se rupe la spatii; un cuvant mai lung decat un rand intreg (o adresa) se rupe
	intre litere. Intoarce cel putin un rand."""
	if not text or latime <= 0:
		return [text]
	L = _latimeText()
	familie, m = FAMILII.get(font, font), int(marime)
	urmare = latime if latime_urmare is None or latime_urmare <= 0 else latime_urmare

	def loc(lat):
		return max(1, lat - marja(lat))

	rez = []
	lat = latime
	rand = ""
	for cuvant in text.split(" "):
		incercare = cuvant if not rand else rand + " " + cuvant
		if L.latime(incercare, familie, m) <= loc(lat):
			rand = incercare
			continue
		if rand:
			rez.append(rand)
			lat = urmare
			rand = ""
		while cuvant and L.latime(cuvant, familie, m) > loc(lat):
			k = max(1, len(cuvant) - 1)
			while k > 1 and L.latime(cuvant[:k], familie, m) > loc(lat):
				k -= 1
			rez.append(cuvant[:k])
			cuvant = cuvant[k:]
			lat = urmare
		rand = cuvant
	if rand or not rez:
		rez.append(rand)
	return rez


def rupt_pereche(eticheta, valoare, latime_eticheta, latime_valoare, font_eticheta, font_valoare):
	"""Eticheta si valoarea unui rand de tabel, fiecare rupta pe randurile ei (rupt, cu fontul ei: (familie, marime)),
	puse alaturi: [(eticheta, valoare)], cel putin una; sub cea mai scurta locul ramane gol. Asa nici eticheta nu mai
	are nevoie de "..."."""
	et = rupt(eticheta, latime_eticheta, *font_eticheta) if eticheta else [eticheta]
	va = rupt(valoare, latime_valoare, *font_valoare) if valoare else [valoare]
	n = max(len(et), len(va))
	et = list(et) + [""] * (n - len(et))
	va = list(va) + [""] * (n - len(va))
	return list(zip(et, va))


def rupt_titlu(tip, text, latime, font):
	"""Un titlu (tip "titlu") rupt pe randuri: toate in afara de ultimul au tipul "titlu_sus" (fara linia de sub
	titlu), ultimul pastreaza tipul, deci linia ramane sub ultimul rand. Alte tipuri (subtitlu) raman cu tipul lor."""
	bucati = rupt(text, latime, *font)
	if tip != "titlu":
		return [(tip, b) for b in bucati]
	return [("titlu_sus", b) for b in bucati[:-1]] + [(tip, bucati[-1])]


def pe_pagini(randuri_col, n):
	"""Randurile unei coloane asezate pe pagini de `n` randuri (cate muta lista la o pagina): un titlu (cu randurile
	lui de sus, "titlu_sus") nu ramane la capatul unei pagini fara niciun rand dupa el (trece pe pagina urmatoare,
	cu randuri goale in locul lui), o pagina nu incepe cu un rand gol, iar o pagina care incepe in mijlocul unei
	sectiuni are sus, din nou, titlul sectiunii (altfel randurile de acolo nu spun de unde sunt). Cu o singura pagina
	randurile raman cum sunt."""
	if n < 3 or len(randuri_col) <= n:
		return list(randuri_col)
	rez, titlu, j = [], [], 0
	while j < len(randuri_col):
		r = randuri_col[j]
		if r[0] in ("titlu_sus", "titlu"):
			k = j
			while k < len(randuri_col) and randuri_col[k][0] == "titlu_sus":
				k += 1
			bloc = list(randuri_col[j:k + 1])
			loc = n - len(rez) % n
			if len(rez) % n and loc < len(bloc) + 1:
				rez.extend([("gol",)] * loc)
			rez.extend(bloc)
			titlu = bloc if len(bloc) < n - 1 else []
			j = k + 1
			continue
		if rez and len(rez) % n == 0:
			if r[0] == "gol":
				j += 1
				continue
			if titlu:
				rez.extend(titlu)
		rez.append(r)
		j += 1
	return rez


def latime_eticheta(latime, inaltime=42):
	"""Latimea etichetei intr-un rand eticheta / valoare de `latime` puncte: 44% din coloana; pe toata latimea (o
	coloana, peste 1100 de puncte la randuri de 42) 30%."""
	return int(latime * 0.30) if latime > int(1100 * inaltime / 42.0) else int(latime * 0.44)


def retras(inaltime=42):
	"""Cat de la dreapta incepe continuarea unui text rupt (jumatate de rand), ca sa se vada ca nu e un rand nou."""
	return max(8, int(inaltime) // 2)
