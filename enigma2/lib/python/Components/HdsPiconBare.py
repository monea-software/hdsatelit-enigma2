# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsPiconBare.py: locul siglei canalului pe ecranele care il fac numai cand e nevoie (bara de informatii, a doua bara,
# in ambele teme) si setarea "Siglele canalelor (piconuri)" (config.usage.hds_piconuri, Components/UsageConfig.py).
#
# In skin, widgetul siglei (render="Picon") spune in atributul vecini ce elemente ale ecranului isi fac loc pentru ea:
#   <widget source="session.CurrentService" render="Picon" position="24,32" size="150,90" ...
#           vecini="24,18,120,56=198,120|152,18,756,56=326,582">
# Regula "x,y,l,i=x2,l2": elementele ecranului (cu sursa, cu nume sau etichete fixe din skin) cu position="x,y" si
# size="l,i" in skin stau, cat se vede o sigla adevarata (setarea pornita si sigla gasita pentru canal), la x2 cu
# latimea l2; altfel raman la locul lor din skin (fara loc gol in stanga). Randul si inaltimea raman (si ce a potrivit
# Components/HdsMarireText pe verticala). Numerele sunt ale skinului; se inmultesc cu scara ecranului ca in skin.py.
#
# Mutarea se aduna cu cea a pictogramei internetului (Components/HdsPictogramaBare): un element mutat de amandoua (numele
# emisiunii pe bara Clasic) ia locul dat de pictograma (aratata sau ascunsa) plus deplasarea siglei. Ambele module
# pun elementul in acelasi loc, oricare se aplica ultimul.
#
# aseaza(ecran) se cheama din Components/GUISkin.py la asezarea fiecarui ecran al televizorului; renderer-ul Picon cheama
# schimbat(r) cand sigla lui apare sau dispare (la schimbarea canalului) si se inregistreaza la creare
# (inregistreaza), ca la schimbarea setarii toate siglele deschise sa se arate sau sa se ascunda pe loc. Fisierul nu
# importa nimic din enigma2 la incarcare, ca probele de pe PC sa-l foloseasca cu ecrane false.

import sys
import weakref

_siglele = []         # weakref.ref la renderer-ele Picon create
_legat = [False]      # notificarea setarii pusa o data


def _jurnal(text):
	print("[HdsPiconBare] %s" % text)


def reguli(text):
	"""Atributul vecini -> [(x, y, l, i, x2, l2)]; o regula stricata se sare (si se spune in jurnal)."""
	rez = []
	for parte in str(text or "").split("|"):
		parte = parte.replace(" ", "")
		if not parte:
			continue
		try:
			stanga, dreapta = parte.split("=")
			x, y, l, i = [int(v) for v in stanga.split(",")]
			x2, l2 = [int(v) for v in dreapta.split(",")]
			rez.append((x, y, l, i, x2, l2))
		except ValueError:
			_jurnal("regula stricata: %r" % parte)
	return rez


def _e_sigla(o):
	return type(o).__name__ == "Picon" and bool(getattr(o, "vecini", ""))


def _obiecte(ecran):
	try:
		from Components.HdsPictogramaBare import _obiecte as obiecte
		return obiecte(ecran)
	except Exception:
		return []


def _numere(text):
	try:
		a, b = [int(v) for v in str(text).replace(" ", "").split(",")]
		return a, b
	except (ValueError, TypeError):
		return None


def _scara(ecran):
	try:
		(nx, dx), _y = ecran.scale
		if int(dx) > 0:
			return int(nx), int(dx)
	except Exception:
		pass
	return 1, 1


def plan(ecran):
	"""{id(element): (element, renderer-ul siglei, (x, l) din skin, (dx, dl) cu sigla)} pentru regulile siglelor
	ecranului, in pixelii ecranului; {} cand ecranul n-are sigla cu reguli."""
	sigle = [r for r in (getattr(ecran, "renderer", None) or []) if _e_sigla(r)]
	if not sigle:
		return {}
	n, d = _scara(ecran)
	rez = {}
	for o in _obiecte(ecran):
		if type(o).__name__ == "Picon":
			continue
		try:
			a = dict(o.skinAttributes)
		except (TypeError, ValueError):
			continue
		poz, mar = _numere(a.get("position")), _numere(a.get("size"))
		if poz is None or mar is None:
			continue
		for r in sigle:
			gasit = False
			for x, y, l, i, x2, l2 in reguli(r.vecini):
				if poz == (x, y) and mar == (l, i):
					rez[id(o)] = (o, r, (x * n // d, l * n // d), ((x2 - x) * n // d, (l2 - l) * n // d))
					gasit = True
					break
			if gasit:
				break
	return rez


def decalaj(ecran, o):
	"""(dx, dl) al elementului `o` acum: deplasarea data de sigla lui cand ea se vede, altfel (0, 0)."""
	p = getattr(ecran, "_hdsPiconVecini", None)
	if not p:
		return 0, 0
	e = p.get(id(o))
	if e is None or e[0] is not o or not getattr(e[1], "hdsAre", False):
		return 0, 0
	return e[3]


def _baza(ecran, o, x, l):
	"""Locul elementului fara sigla: cel dat de pictograma internetului, daca o are ca vecin, altfel cel din skin."""
	for el, cu, fara in getattr(ecran, "_hdsPictogramaVecini", None) or []:
		if el is o:
			try:
				from Components.HdsPictogramaBare import aratata
				return cu if aratata() else fara
			except Exception:
				return cu
	return x, l


def aplica(ecran):
	"""Vecinii siglelor ecranului la locul lor: mutati cat sigla lor se vede, la locul din skin altfel."""
	p = getattr(ecran, "_hdsPiconVecini", None)
	if not p or getattr(ecran, "instance", None) is None:
		return
	from enigma import ePoint, eSize
	for o, r, (x0, l0), (dx, dl) in list(p.values()):
		inst = getattr(o, "instance", None)
		if inst is None:
			continue
		x, l = _baza(ecran, o, x0, l0)
		if getattr(r, "hdsAre", False):
			x, l = x + dx, l + dl
		try:
			poz, mar = inst.position(), inst.size()
			if poz.x() != x:
				inst.move(ePoint(x, poz.y()))
			if mar.width() != l:
				inst.resize(eSize(l, mar.height()))
		except Exception as e:
			_jurnal("mutarea: %s" % e)


def aseaza(ecran):
	"""Din Components/GUISkin.py, dupa atributele skinului: planul vecinilor (o data pe ecran), fiecare sigla cu reguli
	stie ecranul ei (referinta slaba) si vecinii se pun dupa starea de acum a siglelor."""
	if getattr(ecran, "_hdsPiconVecini", None) is None:
		ecran._hdsPiconVecini = plan(ecran)
		if ecran._hdsPiconVecini:
			ref = weakref.ref(ecran)
			for r in getattr(ecran, "renderer", None) or []:
				if _e_sigla(r):
					r._hdsEcran = ref
	if ecran._hdsPiconVecini:
		aplica(ecran)


def schimbat(r):
	"""Din renderer-ul Picon: sigla lui a aparut sau a disparut; vecinii ei se muta pe loc."""
	ref = getattr(r, "_hdsEcran", None)
	ecran = ref() if ref is not None else None
	if ecran is not None:
		aplica(ecran)


def inregistreaza(r):
	"""Din renderer-ul Picon, la creare: tinut minte (referinta slaba) pentru schimbarea setarii."""
	_siglele.append(weakref.ref(r))
	if len(_siglele) > 64:
		_siglele[:] = [x for x in _siglele if x() is not None]
	_leaga()


def _leaga():
	if _legat[0]:
		return
	try:
		m = sys.modules["Components.config"]
		m.config.usage.hds_piconuri.addNotifier(_schimbata, initial_call=False)
		_legat[0] = True
	except Exception:
		# setarea nu exista inca (renderer creat inaintea ei): se incearca la urmatorul
		pass


def sigle_vii():
	vii = []
	for ref in list(_siglele):
		r = ref()
		if r is None or getattr(r, "instance", None) is None or getattr(r, "source", None) is None:
			if r is None:
				_siglele.remove(ref)
			continue
		vii.append(r)
	return vii


def _schimbata(_cfg=None):
	"""Setarea s-a schimbat: fiecare sigla deschisa (si cele ale ecranelor create o data si ascunse) se cauta din nou
	sau se ascunde, iar vecinii ei se muta odata cu ea (schimbat)."""
	for r in sigle_vii():
		try:
			r.changed((r.CHANGED_ALL,))
		except Exception as e:
			_jurnal("sigla %s: %s" % (type(r).__name__, e))
