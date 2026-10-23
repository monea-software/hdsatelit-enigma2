# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsTraducereTexte - traducerea textelor din teletext si din paginile HbbTV, prin serviciul de traducere al
# subtitrarilor (Components/HdsTraducereSubtitrari.py: acelasi lant de servicii, aceleasi chei, aceeasi limba a
# traducerii, din fabrica limba meniului), cu masinaria traducerii ghidului (Components/HdsTraducereEpg.TraducatorEpg:
# memoria in RAM si pe un mediu extern, un singur fir de cereri, trecerea la rezerve, contorul, trezirea firului enigma2).
#
# DOUA INSTANTE, fiecare cu poarta, memoria, fisierul si contorul ei:
#   "teletext"  setarea "Tradu teletextul" (config.hds_traducere.teletext): paginile aratate de Screens/HdsTeletext.py,
#               prin Components/HdsTraducereTeletext.py; memoria <mediu>/hdsatelit/traducere-teletext.json
#   "hbbtv"     setarea "Tradu HbbTV" (config.hds_traducere.hbbtv): textele vazute ale paginilor HbbTV, trimise de
#               scriptul din pagina (Plugins/Extensions/HdsNavigator/hds-hbbtv.js) la
#               HdsWebControl/traducere_hbbtv_web.py; memoria <mediu>/hdsatelit/traducere-hbbtv.json
# Amandoua oprite din fabrica: fiecare cerere consuma din cota serviciului. Ca "Tradu EPG", lucreaza si cand traducerea
# subtitrarilor e oprita; fara un serviciu cu campurile complete (cheia) nu pleaca nimic si textul ramane original.
#
# CERERILE: traduceri(texte) cere toate textele lipsa deodata (o pagina de teletext, un lot de noduri HbbTV), intr-o
# singura punere in coada: cu cine dat (ecranul teletextului), ce ceruse inainte acelasi cine si n-a plecat inca (pagina
# de dinainte, rasfoita repede) nu mai pleaca. Textul deja in limba tinta (dupa toate textele grupului, limbaProbabila),
# fara litere sau intors neschimbat de serviciu nu se mai cere. Fara retea sau la o eroare: serviciul asteapta, se trece
# la rezerva, textul ramane original; nimic pe ecran, eroarea in contor.
#
# API: instanta(fel), activ(fel), poartaDeschisa(fel), traduceri(fel, texte, cine=None, cere=True) -> (lista, stare),
#   stare(fel), setariSchimbate(element=None), ascultaSchimbarile(functie)

from __future__ import absolute_import

import weakref

from Components import HdsTraducereSubtitrari as T
from Components import HdsTraducereEpg as E

FELURI = ("teletext", "hbbtv")
SETARE = {"teletext": "teletext", "hbbtv": "hbbtv"}
FISIER = {"teletext": "traducere-teletext.json", "hbbtv": "traducere-hbbtv.json"}
ETICHETA = {"teletext": "teletextului", "hbbtv": "HbbTV"}
MAX_TEXTE = 400               # textele unei chemari (o pagina de teletext are cel mult cateva zeci)
COADA = {"teletext": 120, "hbbtv": 400}     # textele care pot astepta un fir (paginile HbbTV au multe)

STARE_TRADUS, STARE_LUCRU, STARE_OPRIT, STARE_DEJA = E.STARE_TRADUS, E.STARE_LUCRU, E.STARE_OPRIT, E.STARE_DEJA


def _jurnal(text):
	print("[HdsTraducereTexte] %s" % text)


def _element(s, fel):
	try:
		return getattr(s, SETARE[fel])
	except (KeyError, AttributeError):
		return None


def poartaDeschisa(fel, s=None):
	"""setarea felului ("teletext" sau "hbbtv") e pornita"""
	try:
		e = _element(s or T.initConfig(), fel)
		return bool(e is not None and e.value)
	except Exception:
		return False


class TraducatorTexte(E.TraducatorEpg):
	"""TraducatorEpg cu poarta, fisierul memoriei si felul textelor ale teletextului sau ale HbbTV"""

	def __init__(self, fel, **kw):
		if fel not in FELURI:
			raise ValueError(fel)
		self.FEL = fel
		self.NUME_FISIER = FISIER[fel]
		self.ETICHETA = ETICHETA[fel]
		self.MAX_COADA = COADA[fel]
		E.TraducatorEpg.__init__(self, **kw)

	def _poartaDeschisa(self, bara=False):
		return poartaDeschisa(self.FEL)

	def _esteComutator(self, element):
		if element is None:
			return False
		try:
			return element is _element(T.initConfig(), self.FEL)
		except Exception:
			return False

	def traduceri(self, texte, cine=None, cere=True):
		"""texte (o pagina, un lot de noduri) -> (lista, stare). lista[i]: traducerea textului i din memorie, textul
		insusi cand nu are ce traduce (fara litere, deja in limba tinta, intors neschimbat), None cand inca nu e.
		stare: STARE_TRADUS (toate gata, macar una schimbata), STARE_LUCRU (lipsesc unele: au plecat la tradus, daca
		cere), STARE_DEJA (nimic de schimbat), STARE_OPRIT (setarea oprita sau niciun serviciu complet: lista = textele)."""
		texte = list(texte)[:MAX_TEXTE]
		if not texte:
			return [], STARE_DEJA
		lant = self._lantAcum()
		if not lant:
			return list(texte), STARE_OPRIT
		self._incarcaDisc()
		tinta = lant[0]["tinta"]
		norm = [E.normalizeaza(t).replace(u"\n", u" ") for t in texte]
		tot = u" ".join(n for n in norm if n)
		if not E.areLitere(tot):
			return list(texte), STARE_DEJA
		if E.limbaProbabila(tot) == tinta:
			if tot not in self._deja and len(self._deja) < 5000:
				self._deja.add(tot)
				self.contor["deja_in_limba"] += 1
			return list(texte), STARE_DEJA
		rez = []
		lipsa = []
		schimbat = False
		for t, n in zip(texte, norm):
			if not n or not E.areLitere(n):
				rez.append(t)
				continue
			traduse = []
			lipseste = False
			for b, dupa in E.bucati(n):
				v = self._dinMemorie(lant, tinta, E.amprenta(b))
				if v is None:
					lipseste = True
					if b not in lipsa:
						lipsa.append(b)
				else:
					traduse.append((v or b) + dupa)
			if lipseste:
				rez.append(None)
				continue
			r = u"".join(traduse).strip()
			if r != n:
				schimbat = True
				rez.append(r)
			else:
				rez.append(t)
		if cine is not None:
			self._afisori[id(cine)] = cine
		if lipsa:
			if cere and not self._asteaptaDiscul():		# cat se citeste fisierul, textele pot fi acolo
				self._lant_fir = lant
				self._cere(lipsa, tinta, cine, inlocuieste=cine is not None)
			return rez, STARE_LUCRU
		return rez, (STARE_TRADUS if schimbat else STARE_DEJA)

	def stare(self):
		"""ca la ghid, cu pornit = setarea acestui fel"""
		st = E.TraducatorEpg.stare(self)
		for k in ("bara", "bara_activ", "traducere_pornita"):
			st.pop(k, None)
		st["fel"] = self.FEL
		st["pornit"] = poartaDeschisa(self.FEL)
		return st


_INSTANTE = {}
_ASCULTATORI = []


def instanta(fel):
	t = _INSTANTE.get(fel)
	if t is None:
		t = _INSTANTE[fel] = TraducatorTexte(fel)
	return t


def activ(fel):
	"""setarea pornita si un serviciu cu campurile complete"""
	try:
		return instanta(fel).activ()
	except Exception:
		return False


def traduceri(fel, texte, cine=None, cere=True):
	"""ca TraducatorTexte.traduceri; nu arunca (la o eroare: textele, STARE_OPRIT)"""
	try:
		return instanta(fel).traduceri(texte, cine, cere)
	except Exception as e:
		_jurnal("traduceri %s: %s" % (fel, e.__class__.__name__))
		return list(texte), STARE_OPRIT


def stare(fel):
	return instanta(fel).stare()


def ascultaSchimbarile(functie):
	"""functie(element) chemata la orice setare a traducerii schimbata (paginile asezate ale teletextului se uita,
	aplicatia HbbTV primeste setarea noua); o metoda se tine minte slab (obiectul ei poate pleca)"""
	try:
		ref = weakref.WeakMethod(functie)
	except TypeError:
		ref = (lambda f: (lambda: f))(functie)
	for r in _ASCULTATORI:
		if r() == functie:
			return
	_ASCULTATORI.append(ref)


def setariSchimbate(element=None):
	"""din HdsTraducereSubtitrari._laSchimbare: lantul se recalculeaza; un comutator redeseneaza ce era tradus"""
	for t in list(_INSTANTE.values()):
		try:
			t.setariSchimbate(element)
		except Exception as e:
			_jurnal("setarile %s: %s" % (t.FEL, e.__class__.__name__))
	for r in list(_ASCULTATORI):
		f = r()
		if f is None:
			_ASCULTATORI.remove(r)
			continue
		try:
			f(element)
		except Exception as e:
			_jurnal("schimbarea setarilor: %s" % e.__class__.__name__)
