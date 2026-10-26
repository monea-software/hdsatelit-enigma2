# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Ecranele din "Informatii despre sistem": Despre imagine, Receptor si procesor, Tunere, Memorie, Discuri si stocare,
# Retea. Fiecare populate() scrie textul ecranului in self["text"] (singurul lucru pe care il atinge, ca pagina web
# /informatii sa-l poata chema pe un obiect fals); textul are forma din Components/HdsInformatiiTabel.py (sectiuni,
# randuri eticheta / valoare), iar ecranul de pe televizor il arata ca tabel pe doua coloane, ca Informatii HDMI.
# Tasta ALBASTRU arata textul brut, acelasi text. Sus, Jos, Stanga, Dreapta, CH+ si CH- dau pagina, in tabel si in textul
# brut, iar randul de jos spune pagina. Randurile tabelului incep cu randul insusi, nu cu None: lista din C++
# (lib/gui/elistbox.cpp, lib/gui/elistboxcontent.cpp) muta pagina numai pe randuri selectabile si socoteste neselectabil
# un rand care incepe cu None, deci tabelul ramanea pe prima pagina (de exemplu „Despre imagine”). Textele prea lungi
# pentru celula lor se rup pe mai multe randuri (HdsInformatiiTabel.rupt), ca in textul brut, in loc sa fie scurtate.

import os
import re
import socket
import struct
from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.ScrollLabel import ScrollLabel
from Components.About import about
from Components import HdsRecuperare
from Components.NimManager import nimmanager
from Components.Harddisk import harddiskmanager


def _get_iface_ip(ifname):
	try:
		import fcntl
		s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		return socket.inet_ntoa(fcntl.ioctl(
			s.fileno(),
			0x8915, # SIOCGIFADDR
			struct.pack('256s', ifname[:15].encode('utf-8'))
		)[20:24])
	except Exception:
		return ""

def _get_iface_netmask(ifname):
	try:
		import fcntl
		s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		return socket.inet_ntoa(fcntl.ioctl(
			s.fileno(),
			0x891b, # SIOCGIFNETMASK
			struct.pack('256s', ifname[:15].encode('utf-8'))
		)[20:24])
	except Exception:
		return ""

def _get_default_gateway():
	try:
		with open("/proc/net/route", "r") as f:
			for line in f.readlines()[1:]:
				fields = line.strip().split()
				if len(fields) >= 3 and fields[1] == "00000000":
					iface = fields[0]
					gw_int = int(fields[2], 16)
					gw_ip = socket.inet_ntoa(struct.pack("<L", gw_int))
					return iface, gw_ip
	except Exception:
		pass
	return "", ""

def _get_dns_servers():
	ns = []
	try:
		with open("/etc/resolv.conf", "r") as f:
			for line in f:
				line = line.strip()
				if line.startswith("nameserver"):
					parts = line.split()
					if len(parts) >= 2 and parts[1] not in ns:
						ns.append(parts[1])
	except Exception:
		pass
	return ns


def _rand(eticheta, valoare, prefix="  "):
	"""Un rand eticheta / valoare in forma citita de Components/HdsInformatiiTabel.py (si aliniat in textul brut); o
	eticheta mai lunga decat coloana (o traducere) primeste tot doua spatii dupa „:”, ca sa nu se lipeasca de valoare."""
	return "%s%s%s" % (prefix, (eticheta + ":").ljust(max(26, len(eticheta) + 3)), valoare)


def _mb(mb):
	"""MB intregi sub 1 GB, peste in GB cu o zecimala si virgula, ca in restul imaginii."""
	if mb < 1024:
		return _("%d MB") % mb
	return (_("%.1f GB") % (mb / 1024.0)).replace(".", ",")


def _dinTotal(folosit, total):
	"""„1,2 GB din 3,6 GB (33%)”."""
	if total <= 0:
		return _mb(folosit)
	return _("%(folosit)s din %(total)s (%(procent)d%%)") % {"folosit": _mb(folosit), "total": _mb(total),
		"procent": int(folosit * 100 / total)}


# culorile tabelului: din skinul HDSatelit, altfel aceleasi ca numere (0xRRGGBB)
_CULORI = {"titlu": ("hdsBrandLight", 0x9FB4FF), "eticheta": ("hdsLabel", 0xAEB9CC), "valoare": ("hdsText", 0xF2F4F8),
	"sina": ("hdsTrack", 0x2A3350), "umplere": ("hdsBrandLight", 0x9FB4FF), "linie": ("hdsTrack", 0x2A3350)}


def _culoare(cheie):
	nume, implicit = _CULORI[cheie]
	try:
		import skin
		c = skin.colorNames.get(nume)
		if c is not None:
			v = c.argb()
			return v & 0xFFFFFF if (v >> 24) == 0 else v
	except Exception:
		pass
	return implicit


class _TextBrut(ScrollLabel):
	"""Textul brut al ecranului (ALBASTRU); fiecare setText (si improspatarea vie a procesorului) redeseneaza tabelul."""

	def __init__(self, laSchimbare):
		ScrollLabel.__init__(self, "")
		self.laSchimbare = laSchimbare
		self.ultim = ""

	def setText(self, text):
		self.ultim = text
		ScrollLabel.setText(self, text)
		try:
			self.laSchimbare(text)
		except Exception as e:
			print("[Information] tabelul: %r" % (e,))


class InformationBase(Screen):
	COLOANE = 2     # 1: tabelul pe toata latimea (randurile lungi, ca functiile din Despre)
	# rezerva pe 1280 (cotele de 1920 x 2/3), culorile skinului HDSatelit scrise ca numere
	SKIN_REZERVA = """
	<screen name="HdsInformatiiTabel" position="48,27" size="1184,666" backgroundColor="#0D10162A" flags="wfNoBorder" title="Informații despre sistem">
		<eLabel position="0,0" size="1184,1" backgroundColor="#99FFFFFF" zPosition="1" />
		<widget source="Title" render="Label" position="21,12" size="1024,37" font="Bold;27" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" transparent="1" valign="center" noWrap="1" zPosition="1" />
		<widget source="global.CurrentTime" render="Label" position="1056,12" size="107,37" font="Bold;27" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" transparent="1" halign="right" valign="center" zPosition="1">
			<convert type="ClockToText">Format:%H:%M</convert>
		</widget>
		<eLabel position="21,59" size="1141,1" backgroundColor="#D9FFFFFF" zPosition="1" />
		<widget name="coloana1" position="21,69" size="560,504" itemHeight="28" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" transparent="1" selectionDisabled="1" scrollbarMode="showNever" zPosition="2" />
		<widget name="despartitor" position="591,69" size="1,504" backgroundColor="#D9FFFFFF" zPosition="1" />
		<widget name="coloana2" position="603,69" size="560,504" itemHeight="28" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" transparent="1" selectionDisabled="1" scrollbarMode="showNever" zPosition="2" />
		<widget name="text" position="21,69" size="1141,504" font="Regular;19" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" transparent="1" scrollbarMode="showOnDemand" zPosition="3" />
		<widget name="HintText" position="21,579" size="1141,29" font="Regular;17" foregroundColor="#00AEB9CC" backgroundColor="#0D10162A" transparent="1" valign="center" noWrap="1" zPosition="2" />
		<eLabel position="21,616" size="1141,1" backgroundColor="#D9FFFFFF" zPosition="1" />
		<eLabel position="21,629" size="4,21" backgroundColor="#00E5484D" zPosition="1" />
		<widget name="key_red" position="32,624" size="269,32" font="Regular;19" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" transparent="1" valign="center" noWrap="1" zPosition="1" />
		<eLabel position="877,629" size="4,21" backgroundColor="#003D7BE0" zPosition="1" />
		<widget name="key_blue" position="888,624" size="269,32" font="Regular;19" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" transparent="1" valign="center" noWrap="1" zPosition="1" />
	</screen>"""

	def __init__(self, session, title=None):
		from Tools.ScaledSkin import scaledSkin
		from Components.MenuList import MenuList
		from enigma import eListboxPythonMultiContent
		self.skin = scaledSkin(self.SKIN_REZERVA)
		Screen.__init__(self, session)
		self.skinName = [self.__class__.__name__, "HdsInformatiiTabel"]
		self.setTitle(title or _("Informații"))
		self.brutVizibil = False
		self.latimi = [0, 0]
		self.perPagina = 0
		self.randuriDesenate = [None, None]
		self.masura = {}
		self["coloana1"] = MenuList([], content=eListboxPythonMultiContent)
		self["coloana2"] = MenuList([], content=eListboxPythonMultiContent)
		self["despartitor"] = Label("")
		self["text"] = _TextBrut(self._deseneaza)
		self["key_red"] = Label(_("Închide"))
		self["key_blue"] = Label(_("Text brut"))
		self["HintText"] = Label(_("Albastru: textul brut, apoi înapoi la tabel."))
		directii = {"up": self.sus, "down": self.jos, "left": self.sus, "right": self.jos}
		for s in ("up", "down", "left", "right"):
			directii[s + "Repeated"] = directii[s]
			directii[s + "Up"] = self._nimic
		self["actions"] = ActionMap(["OkCancelActions", "DirectionActions", "ColorActions"], dict(directii, **{
			"cancel": self.close,
			"ok": self.close,
			"red": self.close,
			"blue": self.comuta,
		}), -1)
		# CH+ si CH- (si |<< >>|) dau si ele pagina: contextul listei de canale, ca la Actualizare software; tastele
		# colorate din el merg la aceleasi functii (altfel jurnalul scrie "unknown action" la fiecare)
		self["pagini"] = ActionMap(["ChannelSelectBaseActions"], {
			"nextBouquet": self.sus,
			"prevBouquet": self.jos,
			"prevMarker": self.sus,
			"nextMarker": self.jos,
			"showAllServices": self.close,
			"showSatellites": self._nimic,
			"showProviders": self._nimic,
			"showFavourites": self.comuta,
		}, -1)
		# PAGE+ si PAGE-, HOME si END ajungeau numai la listele din C++
		# (ListboxActions, context nativ, lib/gui/elistbox.cpp): mutau numai prima coloana vazuta, nu textul brut, iar
		# randul de jos ramanea pe pagina veche. Prinse aici, cu contextul Python HdsPaginiActions (data/keymap.xml),
		# inaintea listelor.
		self["listaTaste"] = ActionMap(["HdsPaginiActions"], {
			"pageUp": self.sus,
			"pageDown": self.jos,
			"moveTop": self.inceput,
			"moveEnd": self.sfarsit,
		}, -1)
		self.onLayoutFinish.append(self._pregateste)

	def _nimic(self):
		pass

	def _pregateste(self):
		from enigma import getDesktop
		try:
			f = getDesktop(0).size().width() / 1920.0
		except Exception:
			f = 1.0

		def font(alias, nume, marime, inaltime):
			try:
				import skin
				if alias in skin.fonts:
					v = skin.fonts[alias]
					return skin.parseFont(alias, ((1, 1), (1, 1))), v[2] or int(inaltime * f)
			except Exception:
				pass
			# fara alias (alt skin): fontul pus din cod, cu Marimea textului si fontul HD Satelit
			from Components import HdsMarireText as MT
			return MT.fontCod(nume, int(marime * f)), MT.inaltimeCod(int(inaltime * f))

		self.fontTitlu, self.inaltime = font("HdsHdmiTitlu", "Bold", 28, 42)
		self.fontEticheta, _h = font("HdsHdmiEticheta", "Regular", 26, 42)
		self.fontValoare, _h = font("HdsHdmiValoare", "Regular", 28, 42)
		# fontul si marimea de acum (cu marimea textului aplicata de skin.parseFont) ale fiecarui font al listei, pentru
		# masurarea textelor (HdsInformatiiTabel.scurtat); fara ele, marimea cea mai mare (130%), ca nimic sa nu fie taiat
		for i, (g, nume, marime) in enumerate(((self.fontTitlu, "HdsBold", 28), (self.fontEticheta, "HdsCond", 26),
				(self.fontValoare, "HdsCond", 28))):
			try:
				self.masura[i] = (g.family, int(g.pointSize))
			except Exception:
				self.masura[i] = (nume, int(marime * f * 1.3))
		self.c = dict((k, _culoare(k)) for k in _CULORI)
		for i in range(2):
			lista = self["coloana%d" % (i + 1)]
			lista.l.setFont(0, self.fontTitlu)
			lista.l.setFont(1, self.fontEticheta)
			lista.l.setFont(2, self.fontValoare)
			lista.l.setItemHeight(self.inaltime)
			lista.selectionEnabled(False)
			try:
				self.latimi[i] = lista.instance.size().width()
			except Exception:
				self.latimi[i] = int(840 * f)
		# randurile unei pagini: inaltimea listei / inaltimea randului (atatea muta eListbox la o pagina)
		try:
			self.perPagina = max(1, self["coloana1"].instance.size().height() // self.inaltime)
		except Exception:
			self.perPagina = max(1, int(756 * f) // self.inaltime)
		if self.COLOANE == 1:
			try:
				from enigma import eSize
				c1, c2 = self["coloana1"].instance, self["coloana2"].instance
				lat = c2.position().x() + c2.size().width() - c1.position().x()
				c1.resize(eSize(lat, c1.size().height()))
				self.latimi[0] = lat
			except Exception as e:
				print("[Information] o coloana: %r" % (e,))
			self["coloana2"].hide()
			self["despartitor"].hide()
		self["text"].hide()
		self.populate()
		self._arataPagina()

	def populate(self):
		pass

	def _deseneaza(self, text):
		if not self.latimi[0]:
			return
		from Components import HdsInformatiiTabel as T
		coloane = T.coloane(T.sectiuni(text), self.COLOANE)
		for i in range(2):
			col = self._incapute(coloane[i] if i < len(coloane) else [], self.latimi[i])
			# pe pagini: titlul sectiunii sus pe o pagina care incepe in mijlocul ei, niciun titlu singur jos
			col = T.pe_pagini(col, self.perPagina)
			if col == self.randuriDesenate[i]:
				continue
			self.randuriDesenate[i] = col
			lista = self["coloana%d" % (i + 1)]
			try:
				idx = lista.getSelectionIndex() or 0
			except Exception:
				idx = 0
			lista.setList([self._intrare(r, self.latimi[i]) for r in col])
			if idx and col:
				lista.moveToIndex(min(idx, len(col) - 1))
		self._arataPagina()

	def _intrare(self, r, w):
		# primul element e randul insusi, nu None: eListbox muta pagina numai pe randuri selectabile (antetul fisierului);
		# selectia nu se vede (selectionEnabled(False))
		from Components.MultiContent import MultiContentEntryText
		from Components import HdsInformatiiTabel as T
		from enigma import RT_HALIGN_LEFT, RT_VALIGN_CENTER
		c, h = self.c, self.inaltime
		if r[0] == "gol":
			return [r]
		if r[0] in ("titlu", "titlu_sus", "subtitlu"):
			# "titlu_sus": randurile de deasupra ale unui titlu rupt (_incapute), fara linia de sub titlu
			culoare = c["valoare"] if r[0] == "subtitlu" else c["titlu"]
			intrare = [r, MultiContentEntryText(pos=(0, 0), size=(w, h), font=2 if r[0] == "subtitlu" else 0,
				flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER, text=self._s(r[1], w, 2 if r[0] == "subtitlu" else 0), color=culoare,
				color_sel=culoare)]
			if r[0] == "titlu":
				linie = max(2, h // 20)
				intrare.append(MultiContentEntryText(pos=(0, h - 2 * linie), size=(w, linie), font=0, text="",
					backcolor=c["linie"], backcolor_sel=c["linie"]))
			return intrare
		if r[0] == "urmare":
			# continuarea unui text rupt (_incapute), putin mai la dreapta
			x = T.retras(h)
			return [r, MultiContentEntryText(pos=(x, 0), size=(w - x, h), font=2, flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER,
				text=self._s(r[1], w - x, 2), color=c["valoare"], color_sel=c["valoare"])]
		# eticheta: 44% din coloana; pe toata latimea (o coloana, peste 1100 de puncte la 1920) 30%
		le = T.latime_eticheta(w, h)
		if r[0] == "bara":
			procent = max(0, min(100, int(r[1])))
			gros = max(6, h // 5)
			y = (h - gros) // 2
			plin = int((w - le) * procent / 100)
			return [r,
				MultiContentEntryText(pos=(le, y), size=(w - le, gros), font=0, text="", backcolor=c["sina"], backcolor_sel=c["sina"]),
				MultiContentEntryText(pos=(le, y), size=(max(1, plin), gros), font=0, text="", backcolor=c["umplere"], backcolor_sel=c["umplere"])]
		_t, eticheta, valoare = r
		if not valoare:
			return [r, MultiContentEntryText(pos=(0, 0), size=(w, h), font=2, flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER,
				text=self._s(eticheta, w, 2), color=c["valoare"], color_sel=c["valoare"])]
		return [r,
			MultiContentEntryText(pos=(0, 0), size=(le - 8, h), font=1, flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER,
				text=self._s(eticheta, le - 8, 1), color=c["eticheta"], color_sel=c["eticheta"]),
			MultiContentEntryText(pos=(le, 0), size=(w - le, h), font=2, flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER,
				text=self._s(valoare, w - le, 2), color=c["valoare"], color_sel=c["valoare"])]

	def _s(self, text, latime, font):
		"""Textul unei celule, intreg: titlurile, etichetele si valorile prea lungi sunt rupte pe mai multe randuri de
		_incapute, deci nu mai e nimic de scurtat cu "..."."""
		return text

	def _incapute(self, col, w):
		"""Randurile unei coloane cu textele prea lungi rupte pe mai multe randuri, ca in textul brut: un rand fara
		valoare continua dedesubt, putin mai la dreapta ("urmare"); eticheta si valoarea continua fiecare sub ea (sub
		cea mai scurta locul ramane gol); un titlu continua pe randul urmator (linia ramane sub ultimul rand). Fiecare
		text cu masurile fontului lui (0 titlu, 1 eticheta, 2 valoare), ca in _intrare."""
		from Components import HdsInformatiiTabel as T
		if w <= 0:
			return col
		nume, marime = self.masura.get(2, ("HdsCond", 36))
		f_titlu = self.masura.get(0, ("HdsCond", 36))
		f_eticheta = self.masura.get(1, ("HdsCond", 36))
		x = T.retras(self.inaltime)
		le = T.latime_eticheta(w, self.inaltime)
		rez = []
		for r in col:
			if r[0] in ("titlu", "subtitlu") and len(r) == 2 and r[1]:
				rez.extend(T.rupt_titlu(r[0], r[1], w, f_titlu if r[0] == "titlu" else (nume, marime)))
				continue
			if r[0] != "rand":
				rez.append(r)
				continue
			_t, eticheta, valoare = r
			if not valoare:
				bucati = T.rupt(eticheta, w, nume, marime, w - x)
				rez.append(("rand", bucati[0], ""))
				rez.extend(("urmare", b) for b in bucati[1:])
				continue
			for e, v in T.rupt_pereche(eticheta, valoare, le - 8, w - le, f_eticheta, (nume, marime)):
				rez.append(("rand", e, v))
		return rez

	def _pagina(self):
		"""(pagina, pagini) a ce se vede. In tabel: Sus si Jos muta cursorul listelor cu cate o pagina intreaga, deci
		pagina e cursorul / randurile unei pagini (coloana cea mai lunga). In textul brut: locul textului."""
		if self.brutVizibil:
			t = self["text"]
			try:
				if t.pages and t.pageHeight > 0:
					return min(t.pages, int(-t.long_text.position().y() // t.pageHeight) + 1), t.pages
			except Exception:
				pass
			return 1, 1
		n = max(1, self.perPagina)
		pagina, pagini = 1, 1
		for i in range(max(1, self.COLOANE)):
			randuri = len(self.randuriDesenate[i] or [])
			pagini = max(pagini, (randuri + n - 1) // n)
			try:
				pagina = max(pagina, (self["coloana%d" % (i + 1)].getSelectionIndex() or 0) // n + 1)
			except Exception:
				pass
		return min(pagina, pagini), pagini

	def _arataPagina(self):
		pagina, pagini = self._pagina()
		if pagini > 1:
			text = _("Sus, Jos, CH+ și CH-: altă pagină (%s). Albastru: textul brut, apoi înapoi la tabel.") % (
				_("page %d of %d") % (pagina, pagini))
		else:
			text = _("Albastru: textul brut, apoi înapoi la tabel.")
		self["HintText"].setText(text)

	def comuta(self):
		self.brutVizibil = not self.brutVizibil
		if self.brutVizibil:
			self["coloana1"].hide()
			self["coloana2"].hide()
			self["text"].show()
			self["key_blue"].setText(_("Tabel"))
		else:
			self["text"].hide()
			self["coloana1"].show()
			if self.COLOANE > 1:
				self["coloana2"].show()
			self["key_blue"].setText(_("Text brut"))
		self._arataPagina()

	def sus(self):
		if self.brutVizibil:
			self["text"].pageUp()
		else:
			self["coloana1"].pageUp()
			self["coloana2"].pageUp()
		self._arataPagina()

	def jos(self):
		if self.brutVizibil:
			self["text"].pageDown()
		else:
			self["coloana1"].pageDown()
			self["coloana2"].pageDown()
		self._arataPagina()

	def inceput(self):
		"""HOME: prima pagina, in tabel (amandoua coloanele) si in textul brut."""
		if self.brutVizibil:
			self["text"].firstPage()
		else:
			for i in range(2):
				self["coloana%d" % (i + 1)].moveToIndex(0)
		self._arataPagina()

	def sfarsit(self):
		"""END: ultima pagina; in tabel fiecare coloana la ultimul ei rand (pagina e a celei mai lungi)."""
		if self.brutVizibil:
			self["text"].lastPage()
		else:
			for i in range(2):
				randuri = len(self.randuriDesenate[i] or [])
				if randuri:
					self["coloana%d" % (i + 1)].moveToIndex(randuri - 1)
		self._arataPagina()


class HdsAbout(InformationBase):
	COLOANE = 1

	def __init__(self, session):
		InformationBase.__init__(self, session, _("Despre imagine"))

	def populate(self):
		def rand(eticheta, valoare):
			# coloana etichetei are 25 de semne; una mai lunga (in alta limba) primeste cel putin doua spatii dupa ":"
			return " • %s%s" % ((eticheta + ":").ljust(max(25, len(eticheta) + 3)), valoare)
		l = []
		l.append(_("Imaginea HD Satelit") + ":")
		l.append(rand(_("Versiune HD Satelit"), about.getImageVersionString()))
		# versiunea de sus (din /etc/image-version) e si a actualizarilor prin pachete (0.3.2); imaginea de baza, scrisa
		# de pe stick (Components/HdsActualizari.py, /etc/hdsatelit-model), apare ca detaliu numai cand difera de ea
		try:
			from Components import HdsActualizari
			baza = HdsActualizari.baza_pentru_despre()
			if baza:
				l.append(" • %s%s" % ((_("Imaginea de bază") + ":").ljust(24), baza))
		except Exception as e:
			print("[Information] imaginea de baza: %r" % (e,))
		l.append(rand(_("Nucleu Enigma2"), about.getEnigmaVersionString()))
		l.append(rand(_("Nucleu Linux"), about.getKernelVersionString()))
		l.append(rand(_("Timp funcționare"), about.getUptimeString()))
		# baza de pornire a canalelor (Components/HdsBazaPornire.py): versiunea venita cu imaginea si, cand e mai noua,
		# cea luata de pe stb.hdsatelit.com; pagina web /informatii/despre ia acest text. O eroare aici nu goleste ecranul.
		try:
			from Components import HdsBazaPornire
			# rand_baza, nu rand: numele functiei rand() de mai sus, folosita si dupa bucla (cu rand suprascris de un text,
			# rand(...) dadea TypeError si tot ecranul ramanea gol)
			for rand_baza in HdsBazaPornire.texte_despre(_):
				eticheta, sep, valoare = rand_baza.partition(": ")
				# eticheta e mai lunga decat coloana (27 de semne): cel putin doua spatii dupa ":", altfel randul iese lipit
				# si tabelul (HdsInformatiiTabel) nu-l desparte in eticheta / valoare (integrarea 0.2.9, vazut in emulator)
				l.append(" • %s%s" % ((eticheta + ":").ljust(max(24, len(eticheta) + 3)), valoare) if sep else " • " + rand_baza)
		except Exception as e:
			print("[Information] baza de pornire: %r" % (e,))
		l.append(" • %s%s" % ((_("Făcută de") + ":").ljust(24), "Monea Software, HD Satelit (https://hdsatelit.com)"))
		l.append("")
		l.append(_("Receptor și procesor:"))
		l.append(rand(_("Dispozitiv"), about.getReceiverName()))
		chipset = about.getChipset()
		if chipset:
			l.append(" • %s%s" % ((_("Cip principal") + ":").ljust(24), chipset))
		l.append(rand(_("Arhitectură"), os.uname().machine))
		l.append("")
		# functiile principale ale receptorului, aceeasi lista ca pe pagina 2 a asistentului (Components/HdsFunctii.py),
		# si contactul HD Satelit; ca restul ecranului, o eroare aici nu goleste tot ecranul
		try:
			from Components import HdsFunctii
			l.append(HdsFunctii.titlu(_) + ":")
			# grupele cu un spatiu in fata, functiile cu "  • "; fara randuri goale intre grupe
			functii = HdsFunctii.text(rand="  • ", titluri_mari=False, intre="", traducere=_)
			l.append(" " + functii.replace("\n", "\n "))
			l.append("")
			l.append(_(HdsFunctii.CONTACT_TITLU) + ":")
			for rand_contact in HdsFunctii.randuriContact(_):
				l.append(" • " + rand_contact)
		except Exception as e:
			print("[Information] functiile receptorului: %r" % (e,))
		l.append("")
		# lista initiala de transpondere vine din pachetul tuxbox-common (cod deschis, nu e compilata de noi); sursa e
		# scrisa aici vizibil, fara nume de comunitati sau situri straine; licenta pachetului e in ecranul Licente
		l.append(_("Sursa listei de canale:"))
		# etichetele de aici au 25 si 26 de semne cu „:”, mai mult decat coloana (24): cel putin doua spatii dupa „:”,
		# altfel randul iese lipit („Transponderele de pornire:pachetul...”) si tabelul nu-l desparte (vazut in emulator)
		for eticheta, valoare in ((_("Transponderele de pornire"),
				_("pachetul tuxbox-common (cod deschis, date tehnice publice); licența e la Licențe")),
				(_("Codul sursă și licențele"), "https://hdsatelit.com/codul-sursa/")):
			l.append(" • %s%s" % ((eticheta + ":").ljust(max(24, len(eticheta) + 3)), valoare))
		l.append("")
		# originea codului si nota despre marci, ca in README.md al imaginii; pagina web /informatii/despre ia acest text
		l.append(_("Originea codului:"))
		for rand_text in (_("Pornește din codul enigma2 publicat de Dream Multimedia (starea din 14 septembrie 2011), "
				"derivat sub licența GPLv2."),
				_("„Enigma” și „Dreambox” sunt mărci ale Dream Property GmbH; celelalte nume de produse aparțin "
				"deținătorilor lor."),
				_("Imaginea HD Satelit e un proiect independent, fără legătură cu Dream Multimedia, cu fabricantul "
				"receptorului sau cu alte echipe de imagini.")):
			l.append(" • " + rand_text)
		self["text"].setText("\n".join(l))


class HdsReceiverInfo(InformationBase):
	def __init__(self, session):
		InformationBase.__init__(self, session, _("Receptor și procesor"))
		# randurile procesorului, rescrise la 2 s numai cat ecranul se vede (Components/HdsProcesor.py)
		try:
			from Components import HdsProcesor
			self.procesorVii = HdsProcesor.InformatiiVii(self)
		except Exception as e:
			print("[Information] procesorul: %r" % (e,))

	def populate(self):
		cpu_model, cpu_cores = about.getCPUInfo()
		ram_total, ram_avail = about.getRAMInfo()
		ram_used = max(ram_total - ram_avail, 0)

		l = []
		l.append(_("Receptorul:"))
		l.append(_rand(_("Model"), about.getReceiverName()))
		chipset = about.getChipset()
		if chipset:
			l.append(_rand(_("Cip principal"), chipset))
		l.append(_rand(_("Arhitectură"), os.uname().machine))
		l.append(_rand(_("Procesor"), cpu_model))
		l.append(_rand(_("Nuclee"), "%d" % cpu_cores))

		# frecventa de acum, numai daca modulul procesorului lipseste (altfel o scrie el, vie)
		freq_str = ""
		for freq_path in (
			"/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq",
			"/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_cur_freq"
		):
			if os.path.isfile(freq_path):
				try:
					with open(freq_path, "r") as f:
						khz = int(f.read().strip())
						freq_str = "%d MHz" % (khz // 1000)
						break
				except Exception:
					pass
		try:
			from Components import HdsProcesor as procesor
		except Exception as e:
			procesor = None
			print("[Information] procesorul: %r" % (e,))
		if procesor is None and freq_str:
			l.append(_rand(_("Frecvența de acum"), freq_str))
		l.append("")
		l.append(_("Procesorul acum:"))
		inainte, l = l, []

		l.append("")
		l.append(_("Memoria RAM:"))
		l.append(_rand(_("Folosită"), _dinTotal(ram_used, ram_total)))
		l.append(_rand(_("Disponibilă"), _mb(ram_avail)))
		l.append("")
		l.append(_("Sistemul:"))
		l.append(_rand(_("Nucleu Linux"), about.getKernelVersionString()))
		l.append(_rand(_("Timp de funcționare"), about.getUptimeString()))

		try:
			with open("/proc/loadavg", "r") as f:
				load_parts = f.read().strip().split()
			if len(load_parts) >= 3:
				l.append(_rand(_("Încărcare (1, 5, 15 min)"), "%s · %s · %s" % (load_parts[0], load_parts[1], load_parts[2])))
				if procesor is not None:
					l.append("  • %s" % procesor.textNotaIncarcare())
			if len(load_parts) >= 4:
				active, _sep, totale = load_parts[3].partition("/")
				l.append(_rand(_("Procese"), _("%(active)s active din %(totale)s") % {"active": active, "totale": totale}))
		except Exception:
			pass

		# dosarul de recuperare de pe stick, calculat ca showiframe (fara citirea memoriei interne); ca restul
		# ecranului, o eroare aici nu goleste tot ecranul
		try:
			if HdsRecuperare.seAplica():
				recuperare = HdsRecuperare.randuriInformatii(HdsRecuperare.calculeaza())
				l.append("")
				l.extend(recuperare)
			elif HdsRecuperare.esteV10():
				l.append("")
				l.extend(HdsRecuperare.randuriV10())
		except Exception:
			pass

		text = None
		if procesor is not None:
			try:
				text = procesor.textEcranInformatii(self, inainte, l)
			except Exception as e:
				print("[Information] procesorul: %r" % (e,))
		self["text"].setText(text if text is not None else "\n".join(inainte + l))


def _modTuner(nim_obj):
	"""Cum e folosit tunerul, cu numele alegerii din Setari tuner (ConfigSelection.getText, tradus: "simplu",
	"activat"...), nu valoarea interna; fara setare, valoarea, iar fara ea "neconfigurat"."""
	try:
		from Components.config import config
		text = config.Nims[nim_obj.slot].configMode.getText()
		if text:
			return text
	except Exception:
		pass
	return str(getattr(nim_obj, "config_mode", "") or _("neconfigurat"))


def primesteTuner(nim_obj):
	"""Randul "Poate primi" din Tunere (si pagina web /informatii/tunere, din acelasi populate): ce semnale primeste
	tunerul, numai dupa ce stie NimManager: tipul (DVB-S2, DVB-C/T ...), "Type: DVB-S2X" si multistream din
	/proc/bus/nim_sockets, "T2" din numele tunerului de cablu si terestru, modurile unui tuner cu mai multe feluri. None
	pentru un tuner gol sau nesuportat. Inainte randul cauta o functie care nu exista (canBeCompatibleWith), deci nu
	aparea niciodata; T2-MI nu e al tunerului (il desface receptorul din fluxul de satelit), deci nu se scrie aici."""
	tip = getattr(nim_obj, "type", None)
	try:
		if not tip or not nim_obj.isSupported():
			return None
	except Exception:
		return None
	t2 = "T2" in str(getattr(nim_obj, "description", "") or "")
	tipuri = [tip]
	try:
		if nim_obj.isMultiType():
			tipuri += [t for t in nim_obj.getMultiTypeList().values() if t]
	except Exception:
		pass
	semnale = []
	for t in tipuri:
		if t in ("DVB-S", "DVB-S2"):
			bucati = ["DVB-S"]
			if t == "DVB-S2":
				bucati.append("DVB-S2")
				if getattr(nim_obj, "s2x", False):
					bucati.append("DVB-S2X")
		elif t in ("DVB-T", "DVB-T2"):
			bucati = ["DVB-T"] + (["DVB-T2"] if t2 or t == "DVB-T2" else [])
		elif t in ("DVB-C/T", "DVB-C/T2"):
			bucati = ["DVB-C", "DVB-T"] + (["DVB-T2"] if t2 or t == "DVB-C/T2" else [])
		elif t == "DVB-C":
			bucati = ["DVB-C"]
		else:
			bucati = [str(t)]
		for b in bucati:
			if b not in semnale:
				semnale.append(b)
	try:
		if nim_obj.isMultistream():
			semnale.append("multistream")
	except Exception:
		pass
	return ", ".join(semnale) or None


class HdsTunerInfo(InformationBase):
	def __init__(self, session):
		InformationBase.__init__(self, session, _("Tunere"))

	def populate(self):
		l = []
		nims = nimmanager.nimList()
		if not nims:
			l.append(_("Tunere:"))
			l.append("  • " + _("Niciun tuner găsit pe acest receptor."))
		for idx, nim_desc in enumerate(nims):
			l.append(_("Tunerul %s:") % chr(65 + idx))
			descriere = nim_desc.split(": ", 1)[-1] if ": " in nim_desc else nim_desc
			l.append(_rand(_("Model"), descriere))
			nim_obj = nimmanager.nim_slots[idx] if idx < len(nimmanager.nim_slots) else None
			if nim_obj:
				l.append(_rand(_("Semnal"), getattr(nim_obj, "friendly_type", "DVB")))
				l.append(_rand(_("Folosit ca"), _modTuner(nim_obj)))
				primeste = primesteTuner(nim_obj)
				if primeste:
					l.append(_rand(_("Poate primi"), primeste))
			l.append("")
		l.append(_("Antena:"))
		# ecranul nu spune unde sta in meniu, ca o mutare in menu.xml sa nu-l faca gresit
		l.append("  • " + _("Configurarea antenei (DiSEqC, USALS, Unicable) se face în ecranul „Setări tuner”."))
		self["text"].setText("\n".join(l))


class HdsMemoryInfo(InformationBase):
	def __init__(self, session):
		InformationBase.__init__(self, session, _("Memorie"))

	def populate(self):
		l = []
		mem = {}
		try:
			with open("/proc/meminfo", "r") as f:
				for line in f:
					parts = line.strip().split(":")
					if len(parts) == 2:
						k = parts[0].strip()
						v_parts = parts[1].strip().split()
						if v_parts and v_parts[0].isdigit():
							mem[k] = int(v_parts[0]) // 1024 # MB
		except Exception as e:
			l.append(_("Memoria:"))
			l.append("  • " + _("Memoria nu s-a putut citi: %s") % str(e))

		if mem:
			total = mem.get("MemTotal", 0)
			free = mem.get("MemFree", 0)
			buffers = mem.get("Buffers", 0)
			cached = mem.get("Cached", 0)
			available = mem.get("MemAvailable", free + buffers + cached)
			used = max(total - available, 0)

			l.append(_("Memoria RAM:"))
			l.append(_rand(_("Folosită"), _dinTotal(used, total)))
			l.append(_rand(_("Disponibilă"), _mb(available)))
			l.append(_rand(_("Liberă de tot"), _mb(free)))
			l.append(_rand(_("Tampoane și cache"), _mb(buffers + cached)))
			l.append("  • " + _("Cache-ul se golește singur când un program are nevoie de memorie."))
			l.append("")

			swap_total = mem.get("SwapTotal", 0)
			swap_free = mem.get("SwapFree", 0)
			swap_used = max(swap_total - swap_free, 0)

			l.append(_("Fișierul de swap:"))
			if swap_total > 0:
				l.append(_rand(_("Folosit"), _dinTotal(swap_used, swap_total)))
				l.append(_rand(_("Liber"), _mb(swap_free)))
			else:
				l.append("  • " + _("Fără swap: memoria RAM ajunge."))

		# memoria decodorului (cea mai mare bucata libera din vmalloc, Components/HdsMemorieDriver.py): numai informatie,
		# aceeasi valoare ca in ecranul si pagina paznicului; receptorul o elibereaza singur, in standby
		try:
			from Components import HdsMemorieDriver
			dec = HdsMemorieDriver.stare()
		except Exception as e:
			print("[HdsMemoryInfo] memoria decodorului: %r" % (e,))
			dec = None
		if dec and dec.get("liber_kb", -1) >= 0:
			if l:
				l.append("")
			l.append(_("Memoria decodorului:"))
			l.append(_rand(_("Cea mai mare bucată liberă"), _mb(dec["liber_kb"] // 1024)))
			l.append(_rand(_("Prag"), _mb(dec["prag_kb"] // 1024)))
			# 0.6.1: ultima repornire facuta de receptor pentru aceasta memorie (in standby sau pentru un film care nu
			# pornea): diagnosticul sta aici, nu intr-un mesaj pe televizor
			try:
				ultima = HdsMemorieDriver.textUltimaEliberare()
			except Exception as e:
				print("[HdsMemoryInfo] ultima eliberare: %r" % (e,))
				ultima = ""
			if ultima:
				l.append(_rand(_("Ultima eliberare"), ultima))
			if dec.get("eliberare"):
				l.append("  • " + dec["eliberare"])

		self["text"].setText("\n".join(l))


# Sisteme de fisiere care stau in memorie sau sunt numai puncte de legatura: nu sunt discuri si nu intra in lista
# (pe Viper 4K V20 /media e un tmpfs de 64 KB).
_FS_FARA_DISC = ("tmpfs", "ramfs", "devtmpfs", "autofs", "overlay", "squashfs", "proc", "sysfs", "devpts", "cgroup",
	"cgroup2", "debugfs", "configfs", "securityfs", "pstore", "fusectl", "tracefs", "bpf", "mqueue", "hugetlbfs")


# felul sistemului de fisiere din /proc/mounts pe intelesul omului: un stick NTFS e montat de ntfs-3g prin FUSE si
# apare ca „fuseblk”
_NUME_FS = {"fuseblk": "NTFS", "ntfs": "NTFS", "ntfs3": "NTFS", "vfat": "FAT", "exfat": "exFAT"}


def _numeSistemFisiere(fs):
	return _NUME_FS.get(fs, fs)


def _marime(mb):
	"""MB intregi sub 1 GB, peste in GB cu o zecimala si virgula, ca in restul imaginii."""
	if mb is None or mb < 0:
		return _("necunoscut")
	if mb < 1024:
		return _("%d MB") % mb
	return (_("%.1f GB") % (mb / 1024.0)).replace(".", ",")


def _marimeDisc(mb_zecimal):
	"""Capacitatea scrisa pe disc (1 GB = 1000 MB, ca Harddisk.diskSize)."""
	if mb_zecimal < 1000:
		return _("%d MB") % mb_zecimal
	return (_("%.1f GB") % (mb_zecimal / 1000.0)).replace(".", ",")


def _ocupare(total, folosit):
	"""„1,2 GB din 3,6 GB (33%)”; fara total cunoscut, numai ce s-a folosit."""
	if not total or total <= 0:
		return _marime(folosit)
	return _("%(folosit)s din %(total)s (%(procent)d%%)") % {"folosit": _marime(folosit), "total": _marime(total),
		"procent": int(folosit * 100 / total)}


def _numeDisc(hdd):
	"""„SanDisk Ultra” din „SanDisk(Ultra)” (Harddisk.model lipeste producatorul de model); „ATA” nu spune nimic."""
	try:
		text = hdd.model().strip()
	except Exception:
		text = ""
	m = re.match(r"^(.*?)\s*\((.*)\)$", text)
	if m:
		text = " ".join(x for x in (m.group(1).strip(), m.group(2).strip()) if x and x.upper() != "ATA")
	return text or hdd.device


# unde se monteaza discurile si stickurile: si /run/media (stickul pus de sistem, de pilda "/run/media/HD SATELIT-sda1",
# cu legatura /media/hdd spre el)
_LOCURI_MONTARE = ("/media/", "/mnt/", "/storage/", "/run/media/")


def _legaturiMedia(dosar="/media"):
	"""{calea reala: legatura} pentru legaturile din /media (de pilda /run/media/HD SATELIT-sda1 -> /media/hdd)"""
	rez = {}
	try:
		for nume in sorted(os.listdir(dosar)):
			cale = os.path.join(dosar, nume)
			if os.path.islink(cale):
				rez.setdefault(os.path.realpath(cale), cale)
	except OSError:
		pass
	return rez


def _monturiDiscuri(mounts="/proc/mounts", media="/media"):
	"""(punct de montare, dispozitiv, sistem de fisiere) pentru discurile si stickurile montate sub /media, /mnt,
	/storage si /run/media, fara dublete; un loc din /run/media cu legatura in /media se arata cu legatura (calea pe
	care o vede omul in rest). /proc/mounts scrie spatiile din cale ca \040: decodate (unescapeMountPath), altfel statvfs
	lucreaza pe o cale care nu exista."""
	try:
		from Components.Harddisk import unescapeMountPath
	except ImportError:
		def unescapeMountPath(t):
			return re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), t)
	legaturi = _legaturiMedia(media)
	gasite = []
	vazute = set()
	try:
		with open(mounts, "r", encoding="utf-8", errors="surrogateescape") as f:
			for linie in f:
				parti = linie.split()
				if len(parti) < 3:
					continue
				dev, mnt, fs = parti[0], unescapeMountPath(parti[1]), parti[2]
				if fs in _FS_FARA_DISC or mnt in vazute:
					continue
				if mnt.startswith(_LOCURI_MONTARE):
					vazute.add(mnt)
					gasite.append((legaturi.get(mnt, mnt), dev, fs))
	except (IOError, OSError):
		pass
	return gasite


def _discuriSys(sys_block="/sys/block"):
	"""[(dispozitiv, nume, marime in MB zecimali, e stick)] pentru discurile USB si SATA din /sys/block (sd*), cand
	harddiskmanager nu le are (stickul montat de sistem, nu de enigma2)"""
	rez = []
	try:
		nume_dispozitive = sorted(os.listdir(sys_block))
	except OSError:
		return rez
	for d in nume_dispozitive:
		if not re.match(r"^sd[a-z]+$", d):
			continue
		baza = os.path.join(sys_block, d)

		def citeste(rel):
			try:
				with open(os.path.join(baza, rel), encoding="utf-8", errors="replace") as f:
					return f.read().strip()
			except (IOError, OSError):
				return ""
		try:
			mb = int(citeste("size") or 0) * 512 // 1000000
		except ValueError:
			mb = 0
		nume = " ".join(x for x in (citeste("device/vendor"), citeste("device/model")) if x) or d
		rez.append(("/dev/" + d, nume, mb, citeste("removable") == "1"))
	return rez


class HdsStorageInfo(InformationBase):
	"""Memoria interna, discurile montate si discurile conectate. populate() scrie numai self["text"]: pagina web
	/informatii/stocare (informatii_web.py) o cheama pe un obiect care are numai cheia "text"."""
	def __init__(self, session):
		InformationBase.__init__(self, session, _("Discuri și stocare"))

	def populate(self):
		l = []
		tot, free, used = about.getStorageInfo("/")
		l.append(_("Memoria internă a receptorului"))
		if tot > 0:
			l.append("  " + _("Ocupat: %s") % _ocupare(tot, used))
			l.append("  " + _("Liber: %s") % _marime(free))
		else:
			l.append("  " + _("Spațiul nu s-a putut citi."))
		l.append("")

		l.append(_("Discuri și stickuri montate"))
		monturi = _monturiDiscuri()
		if not monturi:
			l.append("  " + _("Niciun disc sau stick montat."))
		for mnt, dev, fs in monturi:
			l.append("  %s  (%s, %s)" % (mnt, dev, _numeSistemFisiere(fs)))
			m_tot, m_free, m_used = about.getStorageInfo(mnt)
			if m_tot > 0:
				l.append("    " + _("Ocupat: %s") % _ocupare(m_tot, m_used) + ", " + _("liber: %s") % _marime(m_free))
			else:
				l.append("    " + _("Spațiul nu s-a putut citi."))
		l.append("")

		l.append(_("Discuri și stickuri conectate"))
		discuri = list(getattr(harddiskmanager, "hdd", []))
		# fara discuri in harddiskmanager (stickul montat de sistem, in /run/media): cele din /sys/block, cu locul lor
		sys_discuri = [] if discuri else _discuriSys()
		if not discuri and not sys_discuri:
			l.append("  " + _("Niciun disc sau stick conectat."))
		for dev, nume, marime, _stick in sys_discuri:
			l.append(("  %s: %s" % (nume, _marimeDisc(marime))) if marime > 0 else ("  %s" % nume))
			puncte = sorted(set(mnt for mnt, d, _fs in monturi if d.startswith(dev)))
			l.append("    " + (_("Montat în: %s") % ", ".join(puncte) if puncte else _("Nemontat.")))
		try:
			partitii = harddiskmanager.getMountedPartitions()
		except Exception:
			partitii = []
		for hdd in discuri:
			nume = _numeDisc(hdd)
			marime = hdd.diskSize()
			l.append(("  %s: %s" % (nume, _marimeDisc(marime))) if marime > 0 else ("  %s" % nume))
			puncte = sorted(set(p.mountpoint.rstrip("/") for p in partitii
				if p.device and p.mountpoint and p.device.startswith(hdd.device)))
			if puncte:
				l.append("    " + _("Montat în: %s") % ", ".join(puncte))
			else:
				l.append("    " + _("Nemontat."))

		self["text"].setText("\n".join(l))


class HdsNetworkInfo(InformationBase):
	def __init__(self, session):
		InformationBase.__init__(self, session, _("Rețea"))

	def populate(self):
		l = []
		gw_iface, gw_ip = _get_default_gateway()
		dns_servers = _get_dns_servers()

		net_dir = "/sys/class/net"
		if os.path.isdir(net_dir):
			for iface in sorted(os.listdir(net_dir)):
				if iface == "lo":
					continue
				if iface == gw_iface:
					l.append(_("Interfața %s (folosită acum):") % iface)
				else:
					l.append(_("Interfața %s:") % iface)

				state_path = os.path.join(net_dir, iface, "operstate")
				if os.path.isfile(state_path):
					try:
						with open(state_path, "r") as f:
							state = f.read().strip()
						l.append(_rand(_("Legătura"), _("conectată") if state == "up" else _("deconectată")))
					except Exception:
						pass

				speed_path = os.path.join(net_dir, iface, "speed")
				if os.path.isfile(speed_path):
					try:
						with open(speed_path, "r") as f:
							speed_val = f.read().strip()
						if speed_val and speed_val != "-1":
							l.append(_rand(_("Viteza"), _("%s Mbit/s") % speed_val))
					except Exception:
						pass

				ip_addr = _get_iface_ip(iface)
				netmask = _get_iface_netmask(iface)
				if ip_addr:
					l.append(_rand(_("Adresa IPv4"), ip_addr))
				if netmask:
					l.append(_rand(_("Masca de rețea"), netmask))

				mac_path = os.path.join(net_dir, iface, "address")
				if os.path.isfile(mac_path):
					try:
						with open(mac_path, "r") as f:
							l.append(_rand(_("Adresa MAC"), f.read().strip().upper()))
					except Exception:
						pass
				l.append("")

		l.append(_("Ieșirea spre internet:"))
		if gw_ip:
			l.append(_rand(_("Poarta (routerul)"), _("%(adresa)s, prin %(interfata)s") % {"adresa": gw_ip, "interfata": gw_iface}))
		else:
			l.append(_rand(_("Poarta (routerul)"), _("nu e setată")))
		if dns_servers:
			l.append(_rand(_("Servere DNS"), ", ".join(dns_servers)))
		else:
			l.append(_rand(_("Servere DNS"), _("niciunul setat")))

		self["text"].setText("\n".join(l))
