# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsPictogramaBare.py: setarea "Arata pictograma internetului in bare" (config.usage.hds_internet_pictograma,
# Components/HdsStareRetea.initConfig) pe ecranele cu pictograma retelei (convertorul HdsReteaPictograma: bara de
# informatii, a doua bara, capul ferestrelor Pro, lista de canale Pro).
#
# Pictograma insasi o ascunde convertorul. Aici se muta vecinii ei, ca sa nu ramana loc gol: argumentul convertorului
# din skin spune, dupa "|", ce elemente ale ecranului si-au facut loc pentru pictograma si unde stau fara ea:
#   <convert type="HdsReteaPictograma">Pictograma|152,18,704,56=152,756|704,33,150,30=758,150</convert>
# Regula "x,y,l,i=x2,l2": elementele ecranului (cu sursa, cu nume sau etichete fixe din skin) cu position="x,y" si
# size="l,i" in skin stau, cat pictograma e ascunsa, la x2 cu latimea l2. Randul si inaltimea raman (si ce a potrivit
# Components/HdsMarireText pe verticala, cu textul marit). Numerele sunt ale skinului; se inmultesc cu scara ecranului
# ca in skin.py.
#
# aseaza(ecran) se cheama din Components/GUISkin.py la asezarea fiecarui ecran al televizorului; ecranele cu reguli se
# tin minte (referinte slabe) si se aseaza din nou cand setarea se schimba (bara, a doua bara si lista de canale sunt
# create o singura data). Fisierul nu importa nimic din enigma2 la incarcare, ca probele de pe PC sa-l foloseasca cu
# ecrane false.

import sys
import weakref

CONVERTOR = "HdsReteaPictograma"
_ecrane = []          # weakref.ref la ecranele cu reguli
_legat = [False]      # notificarea setarii pusa o data


def _jurnal(text):
	print("[HdsPictogramaBare] %s" % text)


def aratata():
	"""Setarea; fara modulul starii sau la orice citire nereusita: da (pictograma se vede, ca pana acum)."""
	try:
		from Components import HdsStareRetea
		return bool(HdsStareRetea.pictograma_aratata())
	except Exception:
		return True


def reguli(argument):
	"""Argumentul convertorului -> [(x, y, l, i, x2, l2)]; o regula stricata se sare (si se spune in jurnal)."""
	rez = []
	for parte in str(argument or "").split("|")[1:]:
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


def e_pictograma(r):
	"""Un element al ecranului (renderer) desenat de convertorul pictogramei, de felul Pictograma / Pictograma2x."""
	src = getattr(r, "source", None)
	if src is None or type(src).__name__ != CONVERTOR:
		return False
	tip = str(getattr(src, "converter_arguments", "") or "").split("|")[0].split(",")[0].strip()
	return tip != "Text"


def _obiecte(ecran):
	"""Elementele ecranului cu instanta si atributele din skin, fiecare o data: cu sursa, cu nume, etichetele fixe."""
	vazute = set()
	rez = []
	lista = list(getattr(ecran, "renderer", None) or []) + list(getattr(ecran, "additionalWidgets", None) or [])
	try:
		lista += [v for _k, v in list(ecran.items())]
	except Exception:
		pass
	for o in lista:
		inst = getattr(o, "instance", None)
		if inst is None or id(o) in vazute or not getattr(o, "skinAttributes", None):
			continue
		vazute.add(id(o))
		rez.append(o)
	return rez


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
	"""[(element, (x, l) cu pictograma, (x, l) fara pictograma)] pentru regulile pictogramelor ecranului, in pixelii
	ecranului; [] cand ecranul n-are pictograma sau reguli."""
	toate = []
	for r in getattr(ecran, "renderer", None) or []:
		if e_pictograma(r):
			toate += reguli(getattr(r.source, "converter_arguments", ""))
	if not toate:
		return []
	n, d = _scara(ecran)
	rez = []
	for o in _obiecte(ecran):
		if e_pictograma(o):
			continue
		try:
			a = dict(o.skinAttributes)
		except (TypeError, ValueError):
			continue
		poz, mar = _numere(a.get("position")), _numere(a.get("size"))
		if poz is None or mar is None:
			continue
		for x, y, l, i, x2, l2 in toate:
			if poz == (x, y) and mar == (l, i):
				rez.append((o, (x * n // d, l * n // d), (x2 * n // d, l2 * n // d)))
				break
	return rez


def _decalajSigla(ecran, o):
	try:
		from Components.HdsPiconBare import decalaj
		return decalaj(ecran, o)
	except Exception:
		return 0, 0


def aplica(ecran, arata=None):
	"""Vecinii pictogramelor ecranului la locul lor: cu pictograma (setarea pornita) sau fara ea."""
	p = getattr(ecran, "_hdsPictogramaVecini", None)
	if not p or getattr(ecran, "instance", None) is None:
		return
	if arata is None:
		arata = aratata()
	from enigma import ePoint, eSize
	for o, cu, fara in p:
		inst = getattr(o, "instance", None)
		if inst is None:
			continue
		x, l = cu if arata else fara
		# un vecin si al siglei canalului (Components/HdsPiconBare): plus deplasarea ei, cat sigla se vede
		dx, dl = _decalajSigla(ecran, o)
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
	"""Din Components/GUISkin.py, dupa atributele skinului: planul vecinilor (o data pe ecran), ecranul tinut minte si
	vecinii pusi dupa setare."""
	if getattr(ecran, "_hdsPictogramaVecini", None) is None:
		ecran._hdsPictogramaVecini = plan(ecran)
		if ecran._hdsPictogramaVecini:
			_ecrane.append(weakref.ref(ecran))
			_leaga()
	if ecran._hdsPictogramaVecini:
		aplica(ecran)


def _leaga():
	if _legat[0]:
		return
	try:
		m = sys.modules.get("Components.config")
		m.config.usage.hds_internet_pictograma.addNotifier(_schimbata, initial_call=False)
		_legat[0] = True
	except Exception as e:
		_jurnal("setarea nu se poate urmari: %s" % e)


def ecrane_vii():
	vii = []
	for ref in list(_ecrane):
		e = ref()
		if e is None or getattr(e, "instance", None) is None:
			_ecrane.remove(ref)
			continue
		vii.append(e)
	return vii


def _schimbata(_cfg=None):
	"""Setarea s-a schimbat: ecranele deschise (si cele create o data si ascunse) se aseaza din nou, iar pictogramele lor
	se arata sau se ascund pe loc (convertorul citeste setarea)."""
	arata = aratata()
	for e in ecrane_vii():
		try:
			aplica(e, arata)
			for r in getattr(e, "renderer", None) or []:
				if e_pictograma(r):
					r.source.changed((r.source.CHANGED_POLL,))
		except Exception as ex:
			_jurnal("ecranul %s: %s" % (e.__class__.__name__, ex))