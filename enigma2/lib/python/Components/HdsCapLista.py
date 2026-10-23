# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsCapLista.py: capul listei de canale (fila „TV | Radio”, randul grupelor listei si randul „Caută canal…”) si
# tastele care ajung la el, ca listele de canale sa se poata folosi numai cu sagetile si OK.
#
# Randurile, de sus in jos: FILA, GRUPE, CAUTA, apoi lista. SUS de pe primul canal urca pe CAUTA, apoi pe GRUPE, apoi
# pe FILA; JOS coboara inapoi pana in lista. Pe FILA, STANGA, DREAPTA si OK trec pe lista cealalta. Pe GRUPE, STANGA si
# DREAPTA muta cursorul intre pastilele grupelor (GRUPE_LISTEI: toate canalele, sateliti, furnizori, favorite si meniul
# listei), iar OK deschide grupa de sub cursor; OK pe grupa in care e deja lista, dintr-un dosar al ei (un satelit, un
# furnizor, un buchet), urca inapoi in grupa. Pe CAUTA, OK deschide cautarea. Repetarile sagetilor (tasta tinuta) nu
# intra in cap: tinuta apasat, sageata ramane a listei (derulare, trecerea de la primul la ultimul canal), iar in cap
# nu comuta fila si nu muta cursorul de mai multe ori.
#
# OK tinut apasat, oriunde in lista = cautarea. Apasarea scurta lucreaza la eliberarea tastei: la apasare nu se stie
# inca daca va fi scurta sau lunga (flagLong vine dupa cateva repetari, main/enigma.cpp).
#
# Tot aici: felul unui canal dupa referinta lui (felul(...)), pentru panoul din dreapta al listei.
#
# Nimic din enigma2 in fisier: starea si hotararile se probeaza pe PC; Screens/ChannelSelection.py le leaga de ecran.

LISTA = None
CAUTA = "cauta"
GRUPE = "grupe"
FILA = "fila"

# pastilele randului GRUPE, in ordine: numele metodei listei (Screens/ChannelSelection.py, aceleasi ca tastele colorate
# rosu, verde, galben, albastru) si, la urma, meniul listei (ca tasta MENU)
GRUPE_LISTEI = ("showAllServices", "showSatellites", "showProviders", "showFavourites", "meniu")
MENIU = len(GRUPE_LISTEI) - 1

# ce are de facut ecranul dupa o tasta
TRECE = "trece"          # tasta nu e a capului: o primeste lista (ActionMap intoarce 0)
NIMIC = "nimic"          # tasta e a capului, dar nu schimba nimic
MUTAT = "mutat"          # focusul s-a mutat (capul se redeseneaza)
COMUTA = "comuta"        # trecerea pe lista cealalta (TV <-> Radio)
CAUTARE = "cautare"      # deschide cautarea de canale
OK_LISTA = "ok_lista"    # OK obisnuit in lista (pornirea canalului, intrarea in dosar, marcarea in editare)
GRUPA = "grupa"          # OK pe o pastila a randului GRUPE (Cap.grupa spune care)

# tipurile de serviciu DVB (eServiceReference data[0]) ale listelor TV si radio (Screens/ChannelSelection.py,
# service_types_tv si service_types_radio)
TIPURI_TV = frozenset((1, 17, 22, 25, 31, 32, 134, 195))
TIPURI_RADIO = frozenset((2, 10))
REF_DVB = 1
DOSAR_SAU_MARCAJ = 1 | 64  # eServiceReference.isDirectory | isMarker


# posturile DAB+ / DVB-T2 din satelit: fluxuri de la releele locale ale imaginii (Hds/DabT2/buchete.py); releul DAB+
# asculta pe 8898 (Hds/DabT2/profil.py), referintele vechi pe 8888 raman posturi DAB+
CAI_FLUXURI = (("dab", "127.0.0.1:8898/dab/"), ("dab", "127.0.0.1:8888/dab/"), ("t2", "127.0.0.1:8889/t2/"))

# eticheta felului, la fel in toate limbile: in dreapta randului din lista de canale (lib/service/listboxservice.cpp,
# setPathLabel), in bara de informatii si in cautare
ETICHETE_FEL = {"dab": "DAB+", "t2": "DVB-T2"}
ETICHETE_CAI = tuple((marcaj, ETICHETE_FEL[fel]) for fel, marcaj in CAI_FLUXURI)


# buchetele DAB+ / DVB-T2 din satelit (Hds/DabT2/profil.py): marcajele lor sunt capete de ansamblu („MUX DAB+: DR
# Deutschland”), aratate fara iconita marcajului (o agrafa, skin_default/icons/marker.png); vezi ServiceList.setRoot
BUCHETE_CAPETE = ("userbouquet.hds_dab.radio", "userbouquet.hds_t2.tv")


def buchet_cu_capete(cale_radacina):
	"""Calea radacinii listei (FROM BOUQUET "userbouquet...." ORDER BY bouquet) e a unui buchet DAB+ / DVB-T2 din
	satelit."""
	return bool(cale_radacina) and any('"%s"' % b in cale_radacina for b in BUCHETE_CAPETE)


def fel_flux(cale):
	"""'dab' / 't2' pentru calea (sau referinta ca text) unui post DAB+ / DVB-T2 din satelit, altfel None."""
	if not cale:
		return None
	c = cale.replace("%3a", ":").replace("%3A", ":")
	for fel, marcaj in CAI_FLUXURI:
		if marcaj in c:
			return fel
	return None


def felul(tip_ref, steaguri, tip_serviciu, cale=""):
	"""Felul canalului dupa referinta: "tv", "radio", "flux" (orice referinta care nu e DVB: flux de internet,
	fisier), "date" (un serviciu DVB de alt tip), "dab" / "t2" (un post DAB+ / DVB-T2 din satelit, dupa cale) sau None
	pentru un dosar sau un marcaj."""
	if steaguri & DOSAR_SAU_MARCAJ:
		return None
	fel = fel_flux(cale)
	if fel:
		return fel
	if tip_ref != REF_DVB:
		return "flux"
	if tip_serviciu in TIPURI_RADIO:
		return "radio"
	if tip_serviciu in TIPURI_TV:
		return "tv"
	return "date"


def e_radio(tip_ref, tip_serviciu):
	return tip_ref == REF_DVB and tip_serviciu in TIPURI_RADIO


class Cap(object):
	"""Focusul capului si apasarea tastei OK. `activ` (la fiecare tasta): capul se vede pe ecran si lista nu e in
	mutare sau editare; cand nu e activ, focusul se intoarce in lista si orice sageata trece la ea."""

	def __init__(self):
		self.focus = LISTA
		self.okApasat = False
		self.okLung = False
		self.grupa = 0          # pastila randului GRUPE sub cursor (indice in GRUPE_LISTEI)
		self.grupe = len(GRUPE_LISTEI)   # cate pastile are ecranul (alegerea simpla a canalului nu are meniu)

	def inLista(self):
		self.focus = LISTA

	def _verifica(self, activ):
		"""-> True daca s-a mutat focusul din cap in lista (capul s-a stins intre timp)."""
		if not activ and self.focus is not LISTA:
			self.focus = LISTA
			return True
		return False

	def _peGrupe(self, grupaCurenta):
		"""Focusul intra pe GRUPE, cu cursorul pe grupa in care e lista acum (OK urca atunci din dosar)."""
		self.focus = GRUPE
		if grupaCurenta is not None and 0 <= grupaCurenta < self.grupe:
			self.grupa = grupaCurenta
		self.grupa = min(self.grupa, self.grupe - 1)

	def sus(self, activ, laInceput, grupaCurenta=None):
		"""SUS apasat (nu repetat). laInceput: cursorul listei e pe primul rand (sau lista e goala). grupaCurenta:
		indicele grupei listei de acum in GRUPE_LISTEI, sau None."""
		if self._verifica(activ):
			return MUTAT
		if not activ:
			return TRECE
		if self.focus is LISTA:
			if laInceput:
				self.focus = CAUTA
				return MUTAT
			return TRECE
		if self.focus == CAUTA:
			self._peGrupe(grupaCurenta)
			return MUTAT
		if self.focus == GRUPE:
			self.focus = FILA
			return MUTAT
		return NIMIC

	def jos(self, activ, grupaCurenta=None):
		if self._verifica(activ):
			return MUTAT
		if not activ or self.focus is LISTA:
			return TRECE
		if self.focus == FILA:
			self._peGrupe(grupaCurenta)
		elif self.focus == GRUPE:
			self.focus = CAUTA
		else:
			self.focus = LISTA
		return MUTAT

	def lateral(self, activ, pas=1):
		"""STANGA (pas -1) sau DREAPTA (pas 1) apasate (nu repetate)."""
		if self._verifica(activ):
			return MUTAT
		if not activ or self.focus is LISTA:
			return TRECE
		if self.focus == FILA:
			return COMUTA
		if self.focus == GRUPE:
			grupa = self.grupa + (1 if pas > 0 else -1)
			if 0 <= grupa < self.grupe:
				self.grupa = grupa
				return MUTAT
		return NIMIC

	def repetat(self, activ):
		"""Orice sageata tinuta apasat: a listei cat focusul e in ea; in cap nu face nimic."""
		if self._verifica(activ):
			return MUTAT
		if not activ or self.focus is LISTA:
			return TRECE
		return NIMIC

	def okApasare(self):
		self.okApasat = True
		self.okLung = False

	def okTinut(self, poateCauta):
		"""OK tinut apasat. poateCauta: lista nu e in mutare sau editare."""
		if not self.okApasat or self.okLung or not poateCauta:
			return NIMIC
		self.okLung = True
		return CAUTARE

	def okEliberare(self, activ):
		"""OK eliberat: fapta apasarii scurte, sau nimic dupa o apasare lunga (sau o eliberare fara apasarea ei)."""
		apasat, lung = self.okApasat, self.okLung
		self.okApasat = False
		self.okLung = False
		if not apasat or lung:
			return NIMIC
		return self.ok(activ)

	def ok(self, activ):
		"""Fapta tastei OK dupa focus (si pentru ENTER de la o tastatura, care nu trece prin apasare si eliberare)."""
		self._verifica(activ)
		if self.focus == CAUTA:
			return CAUTARE
		if self.focus == GRUPE:
			return GRUPA
		if self.focus == FILA:
			return COMUTA
		return OK_LISTA
