# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsFavorite.py: un canal pus in Favorite (sau in alt buchet al omului) si scos de acolo dintr-o apasare. Aceleasi
# functii (adauga, scoate, comuta, pune) pentru lista de canale (tasta FAV, Screens/ChannelSelection.py), canalul vazut
# (FAV tinut apasat pe bara, Screens/InfoBar.py) si pagina web a canalelor (steluta de pe fiecare rand,
# Plugins/Extensions/HdsWebControl/canale_web.py).
#
# Favorite = userbouquet.favourites.tv pentru canalele TV si userbouquet.favourites.radio pentru posturile de radio,
# aceleasi fisiere ca radacina listei cu „mai multe buchete” oprit (ChannelSelection.recallBouquetMode). Un canal e in
# buchet daca o intrare din buchet are aceeasi cheie (HdsIndexCanale.cheie_din_ref: DVB fara tipul serviciului,
# fluxurile dupa adresa), deci si cand tipul serviciului din buchet e altul decat al canalului din lista. La scoatere se
# da nucleului intrarea gasita, asa cum e scrisa in buchet: eBouquet::removeService cauta exact referinta.
# Adaugarea pune canalul la coada buchetului, ca „adauga in buchet” din meniul listei (ChannelSelectionEdit.
# addServiceToBouquet), iar flushChanges scrie fisierul pe loc: dupa repornire canalul e tot acolo.
# Un buchet de Favorite lipsa il face nucleul la reloadBouquets (lib/dvb/db.cpp: userbouquet.favourites.* gol si
# randul lui in bouquets.*), fara sa atinga alte buchete; se cere numai cand buchetul chiar lipseste.
#
# Dupa fiecare schimbare se anunta ascultatorii (asculta): lista de canale a barii se reimprospateaza cand sta chiar pe
# buchetul schimbat (o schimbare facuta din web sau de pe bara), iar pagina web isi uita listele.
#
# Nimic din enigma2 la incarcare: legatura cu nucleul e in clasa Nucleu (importurile in metode), iar probele de pe PC
# dau alt furnizor (parametrul F al fiecarei functii).

import os
import re

TV = "tv"
RADIO = "radio"
ADAUGAT = "adaugat"
SCOS = "scos"

MARCAJ = 64              # eServiceReference.isMarker
DOSAR = 1                # eServiceReference.isDirectory
TIPURI_RADIO = (2, 10)   # tipurile de serviciu radio (ChannelSelection.service_types_radio)
DIRECTOR = "/etc/enigma2"
# buchetele DAB+ / DVB-T2 din satelit le face si le tine cautarea lor (Hds/DabT2), iar „Last Scanned” il rescrie
# fiecare scanare (proba din emulator: era a doua intrare in alegerea buchetului): nu sunt buchete de ales aici
BUCHETE_STRAINE = ("userbouquet.hds_dab.radio", "userbouquet.hds_t2.tv", "userbouquet.LastScanned.tv",
	"userbouquet.LastScanned.radio")

_FISIER = re.compile(r'FROM BOUQUET "([A-Za-z0-9_.\-]{1,120})"')
_CONTROL = re.compile(u"[\u0000-\u001f\u007f-\u009f]")


def _t(text):
	"""Traducerea enigma2 (_ din builtins), sau textul insusi (pe PC, fara traduceri)."""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _jurnal(text):
	print("[HdsFavorite] %s" % _CONTROL.sub("?", str(text)))


# ---------------------------------------------------------------- referintele

def fisier_favorite(tip):
	return "userbouquet.favourites.%s" % (RADIO if tip == RADIO else TV)


def ref_buchet(fisier):
	"""Referinta dosarului unui buchet, aceeasi ca randul lui din bouquets.tv / bouquets.radio."""
	return '1:7:%d:0:0:0:0:0:0:0:FROM BOUQUET "%s" ORDER BY bouquet' % (2 if fisier.endswith(".radio") else 1, fisier)


def ref_favorite(tip):
	return ref_buchet(fisier_favorite(tip))


def fisier_din_ref(ref):
	"""Fisierul buchetului din referinta (sau calea) unui buchet, ori None."""
	m = _FISIER.search(ref or "")
	return m.group(1) if m else None


def e_favorite(fisier):
	return fisier in (fisier_favorite(TV), fisier_favorite(RADIO))


def _campuri(ref):
	"""(tip, steaguri, [8 campuri], cale) din textul unei referinte, sau None."""
	parti = (ref or "").split(":")
	if len(parti) < 10:
		return None
	try:
		return int(parti[0]), int(parti[1]), [int(p or "0", 16) for p in parti[2:10]], (parti[10] if len(parti) > 10 else "")
	except ValueError:
		return None


def steaguri(ref):
	c = _campuri(ref)
	return c[1] if c else 0


def se_poate(ref):
	"""Un canal (sau post) care poate sta intr-un buchet: referinta buna, nu dosar, nu marcaj, nu un fisier (o
	inregistrare, un film) si nu o referinta goala."""
	c = _campuri(ref)
	if c is None:
		return False
	tip, st, date, cale = c
	if st & (MARCAJ | DOSAR):
		return False
	if cale.startswith("/"):
		return False
	if not cale and not any(date[1:]):
		return False
	return True


def tip_canal(ref):
	"""TV sau RADIO dupa referinta (canalul de pe bara): DVB cu tip de serviciu radio = RADIO (si posturile DAB+ din
	satelit, care au tipul 2), restul TV."""
	c = _campuri(ref)
	if c is not None and c[0] == 1 and c[2][0] in TIPURI_RADIO:
		return RADIO
	return TV


def cheie(ref):
	"""Cheia de potrivire (aceeasi ca in lista web si in cautare); fara ea, referinta fara nume."""
	try:
		from Components.HdsIndexCanale import cheie_din_ref
		k = cheie_din_ref(ref)
	except ImportError:
		k = None
	if k:
		return k
	c = _campuri(ref)
	if c is None:
		return ref
	return ":".join((ref or "").split(":")[:11])


def fara_mod(nume):
	"""Numele buchetului fara „ (TV)” / „ (Radio)” (ChannelSelection.removeModeStr)."""
	for coada in (" (TV)", " (Radio)"):
		if nume.endswith(coada):
			return nume[:-len(coada)]
	return nume


# ---------------------------------------------------------------- nucleul (numai pe receptor)

class Nucleu(object):
	"""Buchetele prin eServiceCenter / eDVBDB."""

	def continut(self, ref_b):
		"""[(referinta, nume)] in ordinea din buchet; [] pentru un buchet necunoscut."""
		from enigma import eServiceCenter, eServiceReference
		lista = eServiceCenter.getInstance().list(eServiceReference(ref_b))
		if lista is None:
			return []
		return lista.getContent("SN", False) or []

	def _editare(self, ref_b):
		from enigma import eServiceCenter, eServiceReference
		lista = eServiceCenter.getInstance().list(eServiceReference(ref_b))
		return lista.startEdit() if lista is not None else None

	def exista(self, ref_b):
		"""Nucleul cunoaste buchetul (startEdit merge numai pe un buchet incarcat, eDVBServiceList::startEdit)."""
		return self._editare(ref_b) is not None

	def adauga(self, ref_b, ref):
		from enigma import eServiceReference
		m = self._editare(ref_b)
		if m is None or m.addService(eServiceReference(ref)):
			return False
		m.flushChanges()
		return True

	def scoate(self, ref_b, ref):
		from enigma import eServiceReference
		m = self._editare(ref_b)
		if m is None or m.removeService(eServiceReference(ref)):
			return False
		m.flushChanges()
		return True

	def reincarca(self):
		from enigma import eDVBDB
		eDVBDB.getInstance().reloadBouquets()

	def multibuchet(self):
		from Components.config import config
		return bool(config.usage.multibouquet.value)

	def nume(self, ref_b):
		from enigma import eServiceCenter, eServiceReference
		r = eServiceReference(ref_b)
		info = eServiceCenter.getInstance().info(r)
		return (info.getName(r) if info else "") or ""

	def semnatura(self, fisier):
		try:
			st = os.stat(os.path.join(DIRECTOR, fisier))
			return (st.st_mtime_ns, st.st_size)
		except OSError:
			return None


_NUCLEU = []


def _f(F=None):
	if F is not None:
		return F
	if not _NUCLEU:
		_NUCLEU.append(Nucleu())
	return _NUCLEU[0]


# ---------------------------------------------------------------- ce e in buchet

_MEMORIE = {}     # fisier -> (semnatura, versiune, {cheie: referinta din buchet})
_VERSIUNE = [0]   # creste la fiecare schimbare facuta aici (o semnatura de fisier poate ramane aceeasi)


def _harta(ref_b, F):
	"""{cheie: referinta asa cum e scrisa in buchet} (numai canale), din memorie cat timp fisierul si versiunea raman."""
	fisier = fisier_din_ref(ref_b)
	sem = F.semnatura(fisier) if fisier else None
	vechi = _MEMORIE.get(fisier)
	if fisier and vechi is not None and sem is not None and vechi[0] == sem and vechi[1] == _VERSIUNE[0]:
		return vechi[2]
	harta = {}
	for r, _n in F.continut(ref_b) or []:
		if steaguri(r) & (MARCAJ | DOSAR):
			continue
		harta.setdefault(cheie(r), r)
	if fisier:
		_MEMORIE[fisier] = (sem, _VERSIUNE[0], harta)
	return harta


def uita():
	_MEMORIE.clear()
	_VERSIUNE[0] += 1


def gaseste(ref, ref_b, F=None):
	"""Intrarea din buchet a canalului (referinta asa cum e scrisa acolo), sau None."""
	return _harta(ref_b, _f(F)).get(cheie(ref))


def este_in(ref, ref_b=None, tip=None, F=None):
	if ref_b is None:
		ref_b = ref_favorite(tip or tip_canal(ref))
	return gaseste(ref, ref_b, F) is not None


def chei(ref_b, F=None):
	"""Cheile canalelor din buchet (lista web: steluta plina)."""
	return set(_harta(ref_b, _f(F)))


def nume_buchet(ref_b, F=None):
	"""Numele aratat omului: „Favorite” (tradus) pentru Favorite, altfel numele buchetului fara „ (TV)”."""
	fisier = fisier_din_ref(ref_b) or ""
	if e_favorite(fisier):
		return _t("Favourites")
	try:
		nume = fara_mod(_f(F).nume(ref_b) or "")
	except Exception as e:
		_jurnal("numele buchetului %s: %s" % (fisier, e))
		nume = ""
	return nume or fisier


def buchete_proprii(tip, F=None):
	"""[(ref_buchet, nume)] in care omul poate pune un canal din lista `tip`: Favorite intai, apoi celelalte buchete
	din bouquets.<tip>, numai cu „mai multe buchete” pornit (oprit, lista arata numai Favorite). Fara buchetele DAB+ /
	DVB-T2 din satelit si fara „Last Scanned” (BUCHETE_STRAINE)."""
	F = _f(F)
	fav = ref_favorite(tip)
	rez = [(fav, nume_buchet(fav, F))]
	if not F.multibuchet():
		return rez
	radacina = ref_buchet("bouquets.%s" % (RADIO if tip == RADIO else TV))
	for r, n in F.continut(radacina) or []:
		fisier = fisier_din_ref(r)
		if not (steaguri(r) & DOSAR) or not fisier or e_favorite(fisier) or fisier in BUCHETE_STRAINE:
			continue
		if fisier.endswith(".tv") != (tip != RADIO):
			continue
		rb = ref_buchet(fisier)
		rez.append((rb, fara_mod(n or "") or nume_buchet(rb, F)))
	return rez


# ---------------------------------------------------------------- schimbarile

class Rezultat(object):
	"""ok: s-a facut (sau era deja asa); fapta: ADAUGAT / SCOS / None (nimic facut); canal, buchet: numele aratate;
	fisier: buchetul atins; ref: intrarea pusa sau scoasa."""
	__slots__ = ("ok", "fapta", "canal", "buchet", "fisier", "ref", "eroare")

	def __init__(self, ok, fapta=None, canal="", buchet="", fisier=None, ref=None, eroare=""):
		self.ok = ok
		self.fapta = fapta
		self.canal = canal
		self.buchet = buchet
		self.fisier = fisier
		self.ref = ref
		self.eroare = eroare

	@property
	def in_buchet(self):
		return self.ok and self.fapta == ADAUGAT

	def mesaj(self):
		if not self.ok:
			return self.eroare or _t("Buchetul nu s-a putut schimba.")
		date = {"canal": self.canal, "buchet": self.buchet}
		if self.fapta == ADAUGAT:
			return _t("Adăugat în %(buchet)s: %(canal)s") % date
		return _t("Scos din %(buchet)s: %(canal)s") % date


def intrebare_scoatere(canal, ref_b, F=None):
	return _t("Scoți %(canal)s din %(buchet)s?") % {"canal": canal, "buchet": nume_buchet(ref_b, F)}


def _pregateste(ref, ref_b, tip, F):
	"""(ref_b, eroare): buchetul tinta, facut daca e Favorite si lipseste."""
	if not se_poate(ref):
		return None, _t("Canalul acesta nu se poate pune în buchete.")
	if ref_b is None:
		ref_b = ref_favorite(tip or tip_canal(ref))
	if F.exista(ref_b):
		return ref_b, None
	fisier = fisier_din_ref(ref_b)
	if not e_favorite(fisier or ""):
		return None, _t("Buchetul nu mai există. Deschide din nou lista.")
	_jurnal("%s lipseste: buchetele se reincarca, nucleul il face" % fisier)
	F.reincarca()
	uita()
	if not F.exista(ref_b):
		return None, _t("Buchetul nu s-a putut schimba.")
	return ref_b, None


def adauga(ref, ref_b=None, tip=None, nume="", F=None):
	"""Canalul la coada buchetului (Favorite, daca ref_b lipseste). Era deja acolo: ok, fara schimbare."""
	F = _f(F)
	ref_b, eroare = _pregateste(ref, ref_b, tip, F)
	if eroare:
		return Rezultat(False, eroare=eroare, canal=nume)
	fisier = fisier_din_ref(ref_b)
	numeb = nume_buchet(ref_b, F)
	gasit = gaseste(ref, ref_b, F)
	if gasit is not None:
		return Rezultat(True, ADAUGAT, nume, numeb, fisier, gasit)
	if not F.adauga(ref_b, ref):
		_jurnal("nu s-a putut adauga %s in %s" % (ref, fisier))
		return Rezultat(False, canal=nume, buchet=numeb, fisier=fisier)
	uita()
	_jurnal("%s: adaugat in %s" % (nume or ref, fisier))
	_anunta(fisier, None)
	return Rezultat(True, ADAUGAT, nume, numeb, fisier, ref)


def scoate(ref, ref_b=None, tip=None, nume="", F=None):
	"""Intrarea canalului scoasa din buchet (Favorite, daca ref_b lipseste). Nu era acolo: ok, fara schimbare."""
	F = _f(F)
	ref_b, eroare = _pregateste(ref, ref_b, tip, F)
	if eroare:
		return Rezultat(False, eroare=eroare, canal=nume)
	fisier = fisier_din_ref(ref_b)
	numeb = nume_buchet(ref_b, F)
	gasit = gaseste(ref, ref_b, F)
	if gasit is None:
		return Rezultat(True, SCOS, nume, numeb, fisier, None)
	if not F.scoate(ref_b, gasit):
		_jurnal("nu s-a putut scoate %s din %s" % (gasit, fisier))
		return Rezultat(False, canal=nume, buchet=numeb, fisier=fisier)
	uita()
	_jurnal("%s: scos din %s" % (nume or ref, fisier))
	_anunta(fisier, gasit)
	return Rezultat(True, SCOS, nume, numeb, fisier, gasit)


def comuta(ref, ref_b=None, tip=None, nume="", F=None):
	"""Nu e in buchet: il pune; e: il scoate."""
	if se_poate(ref) and este_in(ref, ref_b, tip, F):
		return scoate(ref, ref_b, tip, nume, F)
	return adauga(ref, ref_b, tip, nume, F)


def pune(ref, vrea, ref_b=None, tip=None, nume="", F=None):
	"""Starea ceruta (pagina web: steluta): vrea True = in buchet, False = scos. Starea deja buna nu schimba nimic."""
	if vrea:
		return adauga(ref, ref_b, tip, nume, F)
	return scoate(ref, ref_b, tip, nume, F)


# ---------------------------------------------------------------- ascultatorii (lista barii, pagina web)

_ASCULTATORI = []


def asculta(functie):
	"""functie(fisier, scos) dupa fiecare schimbare facuta aici: fisierul buchetului schimbat si intrarea scoasa
	(None la adaugare)."""
	if functie not in _ASCULTATORI:
		_ASCULTATORI.append(functie)


def nu_mai_asculta(functie):
	try:
		_ASCULTATORI.remove(functie)
	except ValueError:
		pass


def _anunta(fisier, scos):
	for f in list(_ASCULTATORI):
		try:
			f(fisier, scos)
		except Exception as e:
			_jurnal("un ascultator a cazut: %s" % e)
