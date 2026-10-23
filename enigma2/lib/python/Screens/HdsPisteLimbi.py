# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsPisteLimbi (ecranul) - „Limba sunetului și a subtitrărilor": cate 3 preferinte ordonate pentru sunet
# si pentru subtitrare, „Fără subtitrări niciodată", si stergerea alegerilor de mana tinute minte pe canale.
#
# Cate 3 preferinte pentru sunet si pentru subtitrare, ca omul sa-si aleaga alta ordine, inclusiv „fara subtitrari
# niciodata”; alegerea de mana se tine minte pe canal, iar din setari se poate sterge pentru canalul care merge sau
# pentru toate.
#
# ACEST ECRAN NU STIE CUM SE ALEGE O PISTA: preferintele (config.hds_piste), alegerea si memoria sunt in
# Components/HdsPisteLimbi.py, aceeasi sursa pentru interfata web.
# Dupa Salvare, preferintele se aplica pe loc pe canalul care merge (reaplicaAcum), nu abia la zaparea urmatoare.
#
# Randurile subtitrarii se ascund cand „Fără subtitrări niciodată" e Da (nu mai conteaza), si reapar la Nu.
# Salvarea si anularea merg pe toate cele 8 setari, si pe cele ascunse (saveAll din ConfigListScreen ar lua
# doar randurile vazute). A 8-a, „Tradu automat din orice subtitrare disponibilă”, conteaza numai cu
# traducerea subtitrarilor pornita (Components/HdsPisteLimbi.py, alegeSubtitrareTradusa); textul de sub lista spune
# starea traducerii (textTraducere).
#
# Skinul HDSatelit nu se atinge: ecranul isi poarta skinul aici, ca celelalte ecrane proprii, si incape si
# la 1280x720, si la 1920x1080.

from __future__ import absolute_import

from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Components.ActionMap import ActionMap
from Components.ConfigList import ConfigListScreen
from Components.config import configfile, getConfigListEntry
from Components.Sources.StaticText import StaticText

from Components import HdsPisteLimbi as pl


class HdsPisteLimbi(Screen, ConfigListScreen):
	skin = """
	<screen name="HdsPisteLimbi" resolution="1920,1080" position="center,center" size="1000,700" title="Limba sunetului și a subtitrărilor">
		<widget name="config" position="30,16" size="940,336" scrollbarMode="showOnDemand" font="Regular;24" secondfont="Regular;16" itemHeight="42" />
		<widget source="ajutor" render="Label" position="30,360" size="940,176" font="Regular;19" />
		<widget source="memorie" render="Label" position="30,540" size="940,84" font="Regular;19" foregroundColor="#a08000" />
		<widget source="key_red" render="Label" position="30,637" size="220,45" zPosition="1" font="Regular;21" halign="center" valign="center" backgroundColor="#9f1313" transparent="0" />
		<widget source="key_green" render="Label" position="265,637" size="220,45" zPosition="1" font="Regular;21" halign="center" valign="center" backgroundColor="#1f771f" transparent="0" />
		<widget source="key_yellow" render="Label" position="500,637" size="220,45" zPosition="1" font="Regular;19" halign="center" valign="center" backgroundColor="#a08000" transparent="0" />
		<widget source="key_blue" render="Label" position="735,637" size="235,45" zPosition="1" font="Regular;19" halign="center" valign="center" backgroundColor="#18188b" transparent="0" />
	</screen>
	"""

	def __init__(self, session):
		Screen.__init__(self, session)
		self.setTitle(_("Limba sunetului și a subtitrărilor"))
		self.setari = pl.initConfig()
		ConfigListScreen.__init__(self, [], session=session, on_change=self._schimbat)
		self._toate = [self.setari.audio1, self.setari.audio2, self.setari.audio3, self.setari.fara_subtitrari,
			self.setari.sub1, self.setari.sub2, self.setari.sub3, self.setari.tradu_orice]
		self._niciodata = self.setari.fara_subtitrari.value

		ajutor = _("La fiecare canal pornește prima alegere care există pe canal. Dacă nu există "
			"subtitrare în limbile alese, nu pornește nicio subtitrare. Limba receptorului acum: %s.\n"
			"Ce alegi de mână pe un canal, din ecranul sunetului sau al subtitrărilor, se ține minte pentru "
			"canalul acela și are întâietate față de aceste alegeri.") % pl.numeLimba(pl.limbaReceptor())
		self._ajutor = ajutor
		self["ajutor"] = StaticText(ajutor + u"\n" + pl.textTraducere())
		self["memorie"] = StaticText(u"")
		self["key_red"] = StaticText(_("Cancel"))
		self["key_green"] = StaticText(_("Save"))
		self["key_yellow"] = StaticText(_("Uită canalul acesta"))
		self["key_blue"] = StaticText(_("Uită toate canalele"))

		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions"], {
			"ok": self.lista,
			"cancel": self.anuleaza,
			"red": self.anuleaza,
			"green": self.salveaza,
			"yellow": self.uitaCanal,
			"blue": self.intreabaUitaToate,
		}, -2)

		self._faLista()
		self._arataMemoria()
		getattr(self, "onLayoutFinish", []).append(self._textMarit)

	def _eticheta(self, nume):
		sursa = self.get(nume)
		for r in getattr(self, "renderer", ()):
			if getattr(r, "source", None) is sursa and getattr(r, "instance", None) is not None:
				return r.instance
		return None

	def _textMarit(self):
		"""Textul marit (Marimea textului peste 100 %, Components/HdsMarireText): ajutorul si randul portocaliu al
		canalului de acum (memoria) se pun unul sub altul, fiecare cat ii cere textul, pana deasupra tastelor; cand nu
		incap, fontul lor scade cu cate un pixel (nu sub marimea de la 100 %). La 130 % ultimul rand al ajutorului ajungea
		sub textul portocaliu. Se cheama din nou cand se schimba ajutorul sau memoria. La 100 % nu se schimba nimic."""
		try:
			from Components import HdsMarireText as MT
			if not MT.marit() or getattr(self, "instance", None) is None:
				return
			if getattr(self, "_asezare", None) is None:
				self._asezare = MT.Asezare(self)
			ajutor, memorie = self._eticheta("ajutor"), self._eticheta("memorie")
			tasta = self._eticheta("key_red")
			sk = self._asezare.dinSkin(tasta) if tasta is not None else None
			if ajutor is None or memorie is None or sk is None:
				return
			MT.potrivesteStiva(self._asezare, [(ajutor, lambda: MT.inaltimeText(ajutor)),
				(memorie, lambda: MT.inaltimeText(memorie))], sk[1] - 4, (ajutor, memorie))
		except Exception as e:
			print("[HdsPisteLimbi] textul marit: %s" % e)

	# ------------------------------------------------------------------ lista
	def _faLista(self):
		lista = [
			getConfigListEntry(_("Sunet, prima alegere"), self.setari.audio1),
			getConfigListEntry(_("Sunet, a doua alegere"), self.setari.audio2),
			getConfigListEntry(_("Sunet, a treia alegere"), self.setari.audio3),
			getConfigListEntry(_("Fără subtitrări niciodată"), self.setari.fara_subtitrari),
		]
		if not self.setari.fara_subtitrari.value:
			lista += [
				getConfigListEntry(_("Subtitrare, prima alegere"), self.setari.sub1),
				getConfigListEntry(_("Subtitrare, a doua alegere"), self.setari.sub2),
				getConfigListEntry(_("Subtitrare, a treia alegere"), self.setari.sub3),
				getConfigListEntry(_("Tradu automat din orice subtitrare disponibilă"), self.setari.tradu_orice),
			]
		self["config"].list = lista
		self["config"].l.setList(lista)

	def _schimbat(self):
		# chemat de ConfigListScreen dupa stanga/dreapta: randurile subtitrarii apar sau dispar dupa „niciodata"; fraza
		# traducerii urmeaza „Tradu automat din orice subtitrare disponibilă”
		self["ajutor"].setText(self._ajutor + u"\n" + pl.textTraducere())
		self._textMarit()
		if self.setari.fara_subtitrari.value != self._niciodata:
			self._niciodata = self.setari.fara_subtitrari.value
			index = self["config"].getCurrentIndex()
			self._faLista()
			self["config"].setCurrentIndex(min(index, len(self["config"].list) - 1))

	def lista(self):
		"""OK: la Da/Nu schimba valoarea; la o preferinta deschide lista tuturor alegerilor (cele 33 se
		parcurg greu cu stanga/dreapta)."""
		rand = self["config"].getCurrent()
		if rand is None or len(rand) < 2:
			return
		element = rand[1]
		if element is self.setari.fara_subtitrari or element is self.setari.tradu_orice:
			element.value = not element.value
			self["config"].invalidateCurrent()
			self._schimbat()
			return
		alegeri = [(_(descriere), valoare) for valoare, descriere in element.choices.choices]
		valori = [valoare for descriere, valoare in alegeri]
		curenta = valori.index(element.value) if element.value in valori else 0
		from Screens.ChoiceBox import ChoiceBox
		self._inLista = element
		self.session.openWithCallback(self._alesDinLista, ChoiceBox, title=rand[0], list=alegeri, selection=curenta)

	def _alesDinLista(self, ales):
		element = getattr(self, "_inLista", None)
		self._inLista = None
		if ales is None or element is None:
			return
		element.value = ales[1]
		self["config"].invalidateCurrent()

	# ------------------------------------------------------------------ memoria pe canale
	def _arataMemoria(self, mesaj=None):
		randuri = []
		if mesaj:
			randuri.append(mesaj)
		try:
			stare = pl.stareCanal(self.session)
			numar = pl.numarAlegeri()
		except Exception as e:
			print("[HdsPisteLimbi] memoria alegerilor: %s" % e)
			stare, numar = {"cheie": None, "memorat": {}}, 0
		memorat = stare.get("memorat") or {}
		parteDeMana = stare.get("parte") == pl.PARTE_DE_MANA
		if stare.get("cheie") is None:
			randuri.append(_("Pe ce merge acum nu se țin minte alegeri (nu e un canal)."))
		elif memorat or parteDeMana:
			parti = []
			if "a" in memorat:
				parti.append(_("sunetul ales de mână"))
			if parteDeMana:
				parti.append(_("partea sunetului (stânga, stereo sau dreapta) aleasă de mână"))
			if memorat.get("s") == pl.OPRIT:
				parti.append(_("subtitrarea oprită de mână"))
			elif "s" in memorat:
				parti.append(_("subtitrarea aleasă de mână"))
			randuri.append(_("Pe canalul acesta se ține minte: %s.") % u", ".join(parti))
		else:
			randuri.append(_("Pe canalul acesta nu se ține minte nimic, merg alegerile de mai sus."))
		if numar:
			randuri.append(_("Canale cu alegeri ținute minte: %d.") % numar)
		else:
			randuri.append(_("Niciun canal nu are alegeri ținute minte."))
		self["memorie"].setText(u"\n".join(randuri[-3:]))
		self._textMarit()

	def uitaCanal(self):
		if pl.stareCanal(self.session).get("cheie") is None:
			self._arataMemoria()             # randul „nu e un canal" spune deja de ce nu se uita nimic
			return
		sterse = pl.uitaAlegeri(self.session)
		if sterse:
			pl.reaplicaAcum(self.session)
			self._arataMemoria(_("Alegerile de pe canalul acesta au fost uitate."))
		else:
			self._arataMemoria(_("Pe canalul acesta nu era nimic de uitat."))

	def intreabaUitaToate(self):
		numar = pl.numarAlegeri()
		if not numar:
			self._arataMemoria(_("Nu era nimic de uitat."))
			return
		self.session.openWithCallback(self._uitaToate, MessageBox,
			_("Uiți alegerile de mână de pe toate canalele (%d)? De acum merg alegerile de mai sus.") % numar,
			MessageBox.TYPE_YESNO, default=False)

	def _uitaToate(self, raspuns):
		if not raspuns:
			return
		sterse = pl.uitaAlegeri(toate=True)
		print("[HdsPisteLimbi] alegeri uitate pe %d canale" % sterse)
		pl.reaplicaAcum(self.session)
		self._arataMemoria(_("Alegerile de pe toate canalele au fost uitate."))

	# ------------------------------------------------------------------ salvare / anulare
	def salveaza(self):
		for element in self._toate:
			element.save()
		configfile.save()
		pl.reaplicaAcum(self.session)
		self.close(True)

	def anuleaza(self):
		for element in self._toate:
			element.cancel()
		self.close(False)
