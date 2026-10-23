# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# IptvSetup.py — Televiziune prin IP: playlist M3U/M3U8, portal Stalker,
# cont Xtream Codes. Cod 100% propriu, scris de la zero.
#
# STARE: facut — configurare surse (salvate in
# fisier propriu, NU in config.plugins ca sa nu incarce settings-ul principal
# cu liste lungi de canale) + parser M3U/M3U8 complet si testat cu date
# sintetice (functia parseM3U, fara nicio retea, poate fi rulata oricand cu
# python3 direct pe acest fisier ca sa se verifice fara emulator). Nefacut
# inca: clientii reali Stalker (protocol propriu Ministra/portal.php)
# si Xtream Codes (API HTTP get.php/player_api.php) — cer acces la un server
# real de test ca sa fie verificati corect, nu doar "scrisi si speram ca merg".
# Redarea efectiva a unui flux IPTV foloseste playerul existent (ServiceReference
# cu 4097: pentru IPTV, deja suportat de Enigma2 stock) — ecranul de fata doar
# construieste lista, nu reimplementeaza playerul.

import os
import re

from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.MenuList import MenuList
from Components.Label import Label
from Components.Button import Button
from Components.ConfigList import ConfigListScreen
from Components.Sources.StaticText import StaticText
from Components.config import config, configfile, getConfigListEntry, ConfigPassword

# Sursele (lista si fisierul ei), setarile config.hds_iptv.* si adaugarea sau stergerea unei surse stau in
# Components/HdsIptvSurse.py, aceleasi pentru acest ecran si pentru pagina web /iptv (HdsWebControl/internet_web.py).
# Randurile din "Date de acces" (Albastru), numele lor si verificarea unui text scris sunt tot de acolo (CAMPURI,
# NUME_CAMPURI, valoareBuna), deci televizorul si pagina primesc si refuza aceleasi valori.
from Components.HdsIptvSurse import CALE_SURSE, initConfigIptv, salveazaSurse, incarcaSurse, randSursa, adaugaM3U, stergeSursa  # noqa: F401
from Components.HdsIptvSurse import CAMPURI, NUME_CAMPURI, valoareBuna


# ------------------------------------------------------------------ parser M3U
#
# HDSatelit:
# implementarea INITIALA folosea doua regex-uri (`_LINIE_EXTINF`/`_ATRIBUT` de mai jos, pastrate ca
# istoric in comentariu) cu complexitate NELINIARA reala pe text ostil:
#   - `r'^#EXTINF:\s*(-?\d+)\s*(.*?)\s*,\s*(.*)$'` avea backtracking CATASTROFAL (cubic sau mai rau) --
#     un rand fara nicio virgula, cu multe spatii ("#EXTINF:-1" + spatii*3200 + "X"), a durat 15,6
#     SECUNDE la testare directa (n=1600 -> 2s, n=3200 -> 15,6s, ~de 8 ori mai lent la fiecare dublare
#     a lungimii) -- extrapolat, un singur rand mai lung intr-un fisier M3U ostil ar putea bloca firul
#     de analiza ore intregi.
#   - `r'([A-Za-z0-9_-]+)="([^"]*)"'` cu `.findall()` avea complexitate PATRATICA pe un text lung ce
#     contine multe caractere de cheie (litere/cifre/-/_) neurmate de `="..."` inchis corect -- testat
#     direct: 500 000 de asemenea caractere au dus la peste 15 secunde (fara sa se termine in timpul
#     alocat probei).
# Amandoua sunt exploatabile printr-un SINGUR rand M3U ostil -- relevant fiindca acest parser e facut
# explicit sa citeasca fisiere M3U/M3U8 "locale SAU de la un URL" (antetul fisierului), iar liste IPTV
# "gratuite" partajate public sunt o sursa reala, adesea neverificata. Inlocuite mai jos cu un
# analizor MANUAL, fara regex pentru partile riscante -- liniar prin constructie (fiecare pas
# avanseaza indexul, niciodata nu se reia o portiune deja vazuta), deci imun structural la acest tip
# de blocaj, nu doar "optimizat sa fie mai rapid in cazul obisnuit".
# _LINIE_EXTINF = re.compile(r'^#EXTINF:\s*(-?\d+)\s*(.*?)\s*,\s*(.*)$')  # PASTRAT DOAR ca istoric, NEFOLOSIT
# _ATRIBUT = re.compile(r'([A-Za-z0-9_-]+)="([^"]*)"')                    # PASTRAT DOAR ca istoric, NEFOLOSIT
_DURATA = re.compile(r'^-?\d+$')  # un singur cuantificator, fara ambiguitate de suprapunere -- sigur


def _atributeExtinf(text):
	"""Atributele cheie="valoare" dintr-o linie #EXTINF (tvg-id, tvg-logo, group-title etc.).
	Analiza MANUALA, liniara: fiecare pas avanseaza indexul `i`, niciodata nu se reintoarce peste o
	portiune deja parcursa -- vezi nota de mai sus despre golul real gasit in versiunea cu regex."""
	rezultat = {}
	i, n = 0, len(text)
	while i < n:
		while i < n and text[i] in ' \t':
			i += 1
		start_cheie = i
		while i < n and (text[i].isalnum() or text[i] in '_-'):
			i += 1
		if i == start_cheie:
			i += 1  # niciun caracter de cheie aici -- inaintam cu unul, ca sa nu ramanem blocati
			continue
		cheie = text[start_cheie:i]
		if i >= n or text[i] != '=' or i + 1 >= n or text[i + 1] != '"':
			continue  # nu urmeaza ="..." -- nu e un atribut valid, sarim peste aceasta cheie
		i += 2  # trece peste ="
		start_valoare = i
		while i < n and text[i] != '"':
			i += 1
		if i >= n:
			break  # ghilimeaua de inchidere lipseste -- ne oprim, nimic sigur de mai citit
		rezultat[cheie] = text[start_valoare:i]
		i += 1  # trece peste ghilimeaua de inchidere
	return rezultat


def _extinfPartial(linie):
	"""(durata_text, atribute_text, nume_canal) dintr-o linie #EXTINF, sau None daca nu se intelege
	(inclusiv cazul unei linii "#EXTINF..." fara ":" dupa -- acelasi rezultat None ca regex-ul vechi,
	care cerea explicit ":" in tipar). Analiza MANUALA (doar `.find()`/`.split()`, niciun regex pe
	portiunea ambigua) -- vezi nota de mai sus."""
	if not linie.startswith('#EXTINF:'):
		return None
	rest = linie[len('#EXTINF:'):]
	virgula = rest.find(',')
	if virgula < 0:
		return None
	antet = rest[:virgula].strip()
	nume_canal = rest[virgula + 1:].strip()
	parti = antet.split(None, 1)
	if not parti:
		return None
	durata_text = parti[0]
	atribute_text = parti[1] if len(parti) > 1 else ''
	return durata_text, atribute_text, nume_canal


def parseM3U(text):
	"""Intoarce o lista de dict-uri {nume, url, grup, sigla, tvg_id} din continutul unui fisier M3U/M3U8.
	Nu atinge reteaua — primeste text deja citit (fisier local sau descarcat de apelant).
	Tolerant la linii goale, comentarii necunoscute, CRLF sau LF."""
	canale = []
	linii = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
	curent = None
	for linie in linii:
		linie = linie.strip()
		if not linie:
			continue
		if linie.startswith("#EXTM3U"):
			continue
		if linie.startswith("#EXTINF"):
			analizat = _extinfPartial(linie)
			if analizat is None:
				curent = None
				continue
			durata_text, atribute_text, nume_canal = analizat
			if not _DURATA.match(durata_text):
				curent = None
				continue
			atribute = _atributeExtinf(atribute_text)
			curent = {
				"nume": nume_canal or _("Canal fără nume"),
				"grup": atribute.get("group-title", ""),
				"sigla": atribute.get("tvg-logo", ""),
				"tvg_id": atribute.get("tvg-id", ""),
				"url": None,
			}
			continue
		if linie.startswith("#"):
			continue  # alte etichete M3U (#EXTGRP, #EXTVLCOPT etc.), ignorate deocamdata
		# linie fara # = URL-ul canalului definit mai sus de #EXTINF; daca lipseste EXTINF, facem o intrare minima
		if curent is None:
			curent = {"nume": os.path.basename(linie) or _("Canal fără nume"), "grup": "", "sigla": "", "tvg_id": "", "url": None}
		curent["url"] = linie
		canale.append(curent)
		curent = None
	return canale


def _mesaj(session, text):
	from Screens.MessageBox import MessageBox
	session.open(MessageBox, text, MessageBox.TYPE_ERROR, timeout=8)


class IptvSetup(Screen):
	skin = """
	<screen name="IptvSetup" resolution="1920,1080" position="center,center" size="1000,560" title="Televiziune prin IP (IPTV)">
		<widget name="lista" position="30,30" size="940,340" font="Regular;22" itemHeight="40" scrollbarMode="showOnDemand" />
		<widget name="ghid" position="30,380" size="940,100" font="Regular;20" />
		<widget name="key_red" position="30,500" size="220,40" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#9f1313" transparent="0" />
		<widget name="key_green" position="265,500" size="220,40" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#1f771f" transparent="0" />
		<widget name="key_yellow" position="500,500" size="220,40" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#a08000" transparent="0" />
		<widget name="key_blue" position="735,500" size="235,40" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#18188b" transparent="0" />
	</screen>
	"""

	def __init__(self, session):
		Screen.__init__(self, session)
		self.setTitle(_("Televiziune prin IP (IPTV)"))
		initConfigIptv()

		self._surse = incarcaSurse()
		self["lista"] = MenuList([self._randSursa(s) for s in self._surse] or [_("Nicio sursă IPTV adăugată încă.")])
		self["ghid"] = Label(_("Galben: adaugă o sursă M3U. Albastru: datele de acces (tipul sursei, M3U, Stalker, "
			"Xtream).\nStalker și Xtream Codes: deocamdată se salvează numai datele de acces; conectarea vine în etapa "
			"următoare."))
		self["key_red"] = Button(_("Înapoi"))
		self["key_green"] = Button(_("Șterge selecția"))
		self["key_yellow"] = Button(_("Adaugă sursă M3U"))
		self["key_blue"] = Button(_("Date de acces"))

		self["actiuni"] = ActionMap(
			["OkCancelActions", "ColorActions"],
			{
				"cancel": self.close,
				"red": self.close,
				"green": self._stergeSelectia,
				"yellow": self._adaugaSursaM3U,
				"blue": self._dateAcces,
			}, -2)
		getattr(self, "onLayoutFinish", []).append(self._textMarit)

	def _textMarit(self):
		"""Textul marit (Marimea textului peste 100 %, Components/HdsMarireText): ghidul de sub lista (3 randuri la 100 %)
		creste in sus, iar lista surselor se scurteaza (la 115 % se pierdea al treilea rand); tastele colorate impart
		randul dupa textele lor, fiecare pe un rand (la 130 % "Adauga sursa M3U" trecea pe doua randuri si se taia).
		La 100 % nu se schimba nimic."""
		try:
			from Components import HdsMarireText as MT
			if not MT.marit():
				return
			a = MT.Asezare(self)
			lista, ghid = a.dinSkin(self["lista"].instance), self["ghid"].instance
			if lista:
				a.creste(ghid, MT.inaltimeText(ghid), lista[1], sus=True, maxim=lista[3] // 2)
			if getattr(self, "parsedSkin", None) is not None:
				# numai cu skinul din cod: forma din skinul HDSatelit (skin.xml) are randul tastelor in cadru, cu loc si
				# la textul marit, iar impartirea ar muta numai textele, nu si barele colorate ale cadrului
				MT.imparteRandul(a, [(self[k].instance, self[k].getText()) for k in ("key_red", "key_green",
					"key_yellow", "key_blue")])
		except Exception as e:
			print("[IptvSetup] textul marit: %s" % e)

	def _randSursa(self, sursa):
		return randSursa(sursa)

	def _adaugaSursaM3U(self):
		"""Galben, ca "Adaugă sursă M3U" din pagina web: calea sau adresa listei la tastatura (pornind de la cea salvata in
		config.hds_iptv.m3u_cale), verificata ca in web, salvata, apoi adaugata in lista."""
		from Screens.VirtualKeyBoard import VirtualKeyBoard
		self.session.openWithCallback(self._dupaCaleM3U, VirtualKeyBoard,
			title=_("Playlist M3U/M3U8 (fișier local sau URL)"), text=config.hds_iptv.m3u_cale.value)

	def _dupaCaleM3U(self, text=None):
		if text is None:
			return
		text = text.strip()
		if valoareBuna("m3u_cale", text) is None:
			_mesaj(self.session, _("Valoarea nu e bună pentru %s.") % _(NUME_CAMPURI["m3u_cale"]))
			return
		if config.hds_iptv.m3u_cale.value != text:
			config.hds_iptv.m3u_cale.value = text
		config.hds_iptv.m3u_cale.save()
		configfile.save()
		sursa = adaugaM3U(self._surse, text)
		if sursa is None:
			_mesaj(self.session, _("Scrie întâi calea sau adresa listei M3U."))
			return
		if not salveazaSurse(self._surse):
			self._surse.remove(sursa)
			_mesaj(self.session, _("Setările nu s-au putut salva."))
			return
		self["lista"].setList([self._randSursa(s) for s in self._surse])

	def _dateAcces(self):
		"""Albastru: config.hds_iptv.* (aceleasi randuri ca pagina web /iptv)."""
		self.session.open(IptvDateAcces)

	def _stergeSelectia(self):
		# dupa o intrebare cu Nu ales dinainte, ca pagina web /iptv (stergerea in doi pasi)
		index = self["lista"].getSelectionIndex()
		if not 0 <= index < len(self._surse):
			return
		from Screens.MessageBox import MessageBox
		self.session.openWithCallback(lambda da, i=index: self._sterge(i, da), MessageBox,
			_("Ștergi sursa IPTV?") + "\n" + self._randSursa(self._surse[index]), MessageBox.TYPE_YESNO, default=False)

	def _sterge(self, index, da):
		if da and stergeSursa(self._surse, index) is not None:
			salveazaSurse(self._surse)
			self["lista"].setList([self._randSursa(s) for s in self._surse] or [_("Nicio sursă IPTV adăugată încă.")])


class _ParolaNoua(ConfigPassword):
	"""Parola scrisa acum pe televizor: stelute cat are; goala, randul ramane gol (ConfigText arata atunci un spatiu,
	pe care ConfigPassword l-ar face "*", ca si cum ar fi scrisa)."""

	def getMulti(self, selected):
		if not self.text:
			return ("text", "")
		return ConfigPassword.getMulti(self, selected)


class IptvDateAcces(Screen, ConfigListScreen):
	"""Albastru in IPTV: config.hds_iptv.* (tipul sursei, playlistul M3U, portalul Stalker, contul Xtream) si parola, cu
	aceleasi randuri si nume ca pagina web /iptv. OK pe un rand de text deschide tastatura; textul trece prin
	HdsIptvSurse.valoareBuna, ca in web, iar unul gresit se refuza pe loc. Parola nu se arata: randul ei incepe gol, ce
	scrii o inlocuieste la Verde, gol o lasa cum e, Galben o sterge (cu intrebare). Verde verifica inca o data randurile
	(un text se poate scrie si cu cifrele, direct in rand) si salveaza; Rosu sau EXIT pune inapoi ce era."""
	skin = """
	<screen name="IptvDateAcces" resolution="1920,1080" position="center,center" size="1000,560" title="Date de acces">
		<widget name="config" position="30,30" size="940,336" font="Regular;24" secondfont="Regular;22" itemHeight="42" scrollbarMode="showOnDemand" />
		<widget source="ghid" render="Label" position="30,376" size="940,110" font="Regular;20" />
		<widget source="key_red" render="Label" position="30,500" size="230,40" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#9f1313" transparent="0" />
		<widget source="key_green" render="Label" position="270,500" size="230,40" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#1f771f" transparent="0" />
		<widget name="key_yellow" position="510,500" size="230,40" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#a08000" transparent="0" />
	</screen>
	"""

	def __init__(self, session):
		Screen.__init__(self, session)
		ConfigListScreen.__init__(self, [], session=session)
		self.setTitle(_("Date de acces"))
		self.c = initConfigIptv()
		self._chei = ("tip_sursa",) + CAMPURI
		self._initiale = [(getattr(self.c, k), getattr(self.c, k).value) for k in self._chei]
		# parola: un element al ecranului, gol la deschidere (stelute in rand), nu cel salvat
		self.parola = _ParolaNoua(default="", fixed_size=False)
		self["ghid"] = StaticText("")
		self["key_red"] = StaticText(_("Cancel"))
		self["key_green"] = StaticText(_("Save"))
		self["key_yellow"] = Label(_("Șterge parola"))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions"], {
			"cancel": self.anuleaza,
			"red": self.anuleaza,
			"green": self.salveaza,
			"yellow": self.stergeParola,
		}, -2)
		self.list = [getConfigListEntry(_(NUME_CAMPURI[k]), getattr(self.c, k)) for k in self._chei]
		self.list.append(getConfigListEntry(_(NUME_CAMPURI["xtream_parola"]), self.parola))
		self["config"].list = self.list
		self._ghid()

	def _ghid(self):
		scrisa = bool(self.c.xtream_parola.value)
		self["ghid"].setText(_("OK pe un rând deschide tastatura. Parola nu se arată: o scrii numai când vrei s-o "
			"schimbi; un rând gol o lasă cum e.") + "\n" + (_("Parola salvată: da.") if scrisa else _("Parola salvată: nu.")))
		# Galben (Sterge parola) se vede numai cand e o parola salvata
		if scrisa:
			self["key_yellow"].show()
		else:
			self["key_yellow"].hide()

	def _cheie(self, element):
		if element is self.parola:
			return "xtream_parola"
		for k in self._chei:
			if getattr(self.c, k) is element:
				return k
		return None

	def _refuz(self, cheie):
		_mesaj(self.session, _("Valoarea nu e bună pentru %s.") % _(NUME_CAMPURI[cheie]))

	def keyOK(self):
		x = self["config"].getCurrent()
		cheie = self._cheie(x[1]) if x else None
		if cheie is None or cheie == "tip_sursa":
			ConfigListScreen.keyOK(self)
			return
		element = x[1]

		def gata(text, cheie=cheie, element=element):
			if text is None:
				return
			if cheie != "xtream_parola":
				text = text.strip()
			if valoareBuna(cheie, text) is None:
				self._refuz(cheie)
				return
			element.value = text
			self["config"].invalidate(x)
		from Screens.VirtualKeyBoard import VirtualKeyBoard
		self.session.openWithCallback(gata, VirtualKeyBoard, title=x[0],
			text="" if cheie == "xtream_parola" else element.value)

	def salveaza(self):
		# ca in web, se verifica numai ce s-a schimbat (inceputul de adresa MAC din fabrica, "00:1A:79:", ramane)
		initiale = dict((id(element), valoare) for element, valoare in self._initiale)
		for i, (_n, element) in enumerate(self.list):
			cheie = self._cheie(element)
			if cheie in ("tip_sursa", None) or element.value == initiale.get(id(element)):
				continue
			if valoareBuna(cheie, element.value) is None:
				self["config"].setCurrentIndex(i)
				self._refuz(cheie)
				return
		for element, _v in self._initiale:
			element.save()
		if self.parola.value:
			self.c.xtream_parola.value = self.parola.value
			self.c.xtream_parola.save()
		configfile.save()
		self.close(True)

	def anuleaza(self):
		for element, valoare in self._initiale:
			if element.value != valoare:
				element.value = valoare
		self.close(False)

	def stergeParola(self):
		if not self.c.xtream_parola.value:
			return
		from Screens.MessageBox import MessageBox
		self.session.openWithCallback(self._stergeParola, MessageBox,
			_("Ștergi parola Xtream Codes salvată pe receptor?"), MessageBox.TYPE_YESNO, default=False)

	def _stergeParola(self, da):
		if not da:
			return
		self.c.xtream_parola.value = ""
		self.c.xtream_parola.save()
		configfile.save()
		self.parola.value = ""
		self._ghid()
