# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Alocarea tastelor barei. Lista si salvarea sunt comune cu pagina web.

from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.ConfigList import ConfigListScreen
from Components.config import config, configfile, getConfigListEntry, ConfigNothing
from Components.Sources.StaticText import StaticText
from Components import HdsTasteRapide


class HdsButtonSetup(Screen, ConfigListScreen):
	skin = """
	<screen name="HdsButtonSetup" resolution="1920,1080"
		position="center,center" size="1200,790">
		<widget name="config" position="30,25" size="1140,546"
			scrollbarMode="showOnDemand" font="Regular;24"
			secondfont="Regular;20" itemHeight="42" />
		<widget source="ghid" render="Label" position="30,590"
			size="1140,110" font="Regular;22" />
		<widget source="key_red" render="Label" position="30,725"
			size="275,40" font="Regular;22" halign="center"
			valign="center" backgroundColor="#9f1313" transparent="0" />
		<widget source="key_green" render="Label" position="320,725"
			size="275,40" font="Regular;22" halign="center"
			valign="center" backgroundColor="#1f771f" transparent="0" />
		<widget source="key_yellow" render="Label" position="610,725"
			size="275,40" font="Regular;22" halign="center"
			valign="center" backgroundColor="#a08000" transparent="0" />
		<widget source="key_blue" render="Label" position="900,725"
			size="275,40" font="Regular;22" halign="center"
			valign="center" backgroundColor="#245da8" transparent="0" />
	</screen>
	"""

	def __init__(self, session):
		Screen.__init__(self, session)
		ConfigListScreen.__init__(self, [], session=session)
		self.setTitle(_("Butoane colorate și taste rapide"))
		HdsTasteRapide.actualizeaza_alegeri(config)
		HdsTasteRapide.initConfigProfil(config)
		self["ghid"] = StaticText(_(
			"Alege tasta cu SUS/JOS și funcția cu OK sau STÂNGA/DREAPTA.") + " " +
			HdsTasteRapide.text_tasta("", HdsTasteRapide.ASEZARE_AJUTOR))
		self["key_red"] = StaticText(_("Cancel"))
		self["key_green"] = StaticText(_("Save"))
		self["key_yellow"] = StaticText(_("Valori implicite"))
		self["key_blue"] = StaticText(_("Profilurile mele"))
		self["actiuni"] = ActionMap(
			["OkCancelActions", "ColorActions"], {
				"ok": self.keyOK,
				"cancel": self.anuleaza,
				"red": self.anuleaza,
				"green": self.salveaza,
				"yellow": self.implicite,
				"blue": self.profiluri,
			}, -2)
		self._initiale = [(element, element.value) for _text, element in self._randuri()]
		self._salvate_initial = {id(el): el.saved_value for el, _v in self._initiale}
		self._profil_lucru = False
		self._profil_inchis = False
		if hasattr(self, "onClose"):
			self.onClose.append(self._profil_inchide)
		self._profiluri_actiune = ConfigNothing()
		self._salvare_profil_actiune = ConfigNothing()
		# randul care deschide alegerea randurilor de pe ALBASTRU (HdsListaAlbastra, mai jos)
		self._lista_albastra_actiune = ConfigNothing()
		self.reface_lista()

	def _randuri(self):
		# textele traduse la afisare (text_tasta): listele se fac la import, uneori inainte de limba aleasa
		t = HdsTasteRapide.text_tasta
		return [(t(k, text), getattr(config.usage, k)) for k, _v, text in HdsTasteRapide.PROFIL_SETARI] + [
			(t(k, text), getattr(config.hds_buttons, k)) for k, text in HdsTasteRapide.SCURTE + HdsTasteRapide.BUTOANE]

	def reface_lista(self):
		self.list = [getConfigListEntry(text, element) for text, element in self._randuri()]
		self.list[1:1] = [getConfigListEntry(_("Profilurile mele"), self._profiluri_actiune),
			getConfigListEntry(_("Salvează ca profil"), self._salvare_profil_actiune),
			getConfigListEntry(_("Lista butonului albastru"), self._lista_albastra_actiune)]
		self["config"].list = self.list

	def keyOK(self):
		if HdsTasteRapide.profil_ocupat() or self._profil_lucru:
			return
		from Screens.ChoiceBox import ChoiceBox
		curent = self["config"].getCurrent()
		if curent is None:
			return
		text, element = curent[:2]
		# ASI7 (22.11.2026, asistenta 125948): fara return la fereastra deschisa. ePython::call ia orice raspuns care nu
		# e numar drept "tasta nefolosita" si trimite OK mai departe la config_actions (prio -1), care cheama iar
		# keyOK: Lista butonului albastru se deschidea de doua ori. Cu None, ActionMap da 1 si OK se opreste aici.
		if element is self._profiluri_actiune:
			self.profiluri()
			return
		if element is self._salvare_profil_actiune:
			self._profil_ales((text, "salveaza"))
			return
		if element is self._lista_albastra_actiune:
			self.session.open(HdsListaAlbastra)
			return
		if not hasattr(element, "choices"):
			return ConfigListScreen.keyOK(self)
		lista = [(element.description[v], v) for v in element.choices]
		pozitie = list(element.choices).index(element.value)

		def ales(raspuns):
			if raspuns is not None:
				element.value = raspuns[1]
				self["config"].invalidate(curent)

		# Fara cifre sau culori care ar alege din greseala o functie.
		self.session.openWithCallback(ales, ChoiceBox, title=text,
			list=lista, keys=[""] * len(lista), selection=pozitie)

	def implicite(self):
		if HdsTasteRapide.profil_ocupat() or self._profil_lucru:
			return
		for k, v in HdsTasteRapide.VALORI_IMPLICITE.items():
			getattr(config.hds_buttons, k).value = v
		for k, v, _text in HdsTasteRapide.PROFIL_SETARI:
			getattr(config.usage, k).value = v
		self.reface_lista()

	def _mesaj_profil(self, text, eroare=False):
		from Screens.MessageBox import MessageBox
		self.session.open(MessageBox, text, type=MessageBox.TYPE_ERROR if eroare else MessageBox.TYPE_INFO, timeout=8)

	def _profil_inchide(self):
		self._profil_inchis = True

	def keyLeft(self):
		if not HdsTasteRapide.profil_ocupat() and not self._profil_lucru:
			return ConfigListScreen.keyLeft(self)

	def keyRight(self):
		if not HdsTasteRapide.profil_ocupat() and not self._profil_lucru:
			return ConfigListScreen.keyRight(self)

	def _lucru_profil(self, actiune, gata, **date):
		if self._profil_inchis or self._profil_lucru:
			return
		self._profil_lucru = True
		def terminat(rez):
			self._profil_lucru = False
			if not self._profil_inchis:
				return gata(rez)
		def esec(f):
			self._profil_lucru = False
			if not self._profil_inchis:
				e = f.value
				if isinstance(e, (ValueError, HdsTasteRapide.EroareSalvareTaste)):
					mesaj = str(e)
				else:
					mesaj = (_("Nu pot confirma salvarea tastelor pe disc.") if actiune == "aplica" else
						_("Nu pot salva profilurile. Fișierul tău a rămas neatins."))
				self._mesaj_profil(mesaj, True)
			return None
		return HdsTasteRapide.operatie_profil(actiune, config, configfile, **date).addCallback(terminat).addErrback(esec)

	def profiluri(self):
		from Screens.ChoiceBox import ChoiceBox
		def gata(lista):
			randuri = [(_("Salvează ca profil"), "salveaza")]
			randuri += [(HdsTasteRapide.text_tasta("", text), "baza", v)
				for v, text in HdsTasteRapide.ALEGERI_PROFIL["hds_asezare_taste"]]
			randuri += [(x["profile"]["name"], "aplica", x["id"]) for x in lista]
			if lista:
				randuri += [(_("Redenumește profilul"), "redenumeste"), (_("Șterge profilul"), "sterge")]
			self.session.openWithCallback(self._profil_ales, ChoiceBox, title=_("Profilurile mele"),
				list=randuri, keys=[""] * len(randuri))
		return self._lucru_profil("lista", gata)

	def _profil_ales(self, ales):
		if ales is None or self._profil_inchis or self._profil_lucru or HdsTasteRapide.profil_ocupat():
			return
		from Screens.VirtualKeyBoard import VirtualKeyBoard
		from Screens.ChoiceBox import ChoiceBox
		actiune = ales[1]
		if actiune == "salveaza":
			self.session.openWithCallback(self._salveaza_profil, VirtualKeyBoard, title=_("Numele profilului (poți lăsa gol)"), text="")
		elif actiune in ("sterge", "redenumeste"):
			def gata(profiluri):
				lista = [(x["profile"]["name"], actiune, x["id"]) for x in profiluri]
				def ales_propriu(x):
					if x is None or self._profil_inchis:
						return
					if actiune == "sterge":
						self._schimba_profil("sterge", x[2])
					else:
						self.session.openWithCallback(lambda nume: self._schimba_profil("redenumeste", x[2], nume),
							VirtualKeyBoard, title=_("Numele profilului"), text=x[0])
				self.session.openWithCallback(ales_propriu, ChoiceBox, title=ales[0], list=lista, keys=[""] * len(lista))
			return self._lucru_profil("lista", gata)
		elif actiune == "baza":
			config.usage.hds_asezare_taste.value = ales[2]
			self.reface_lista()
		elif actiune == "aplica":
			def gata(sarite):
				self._initiale = [(el, el.value) for _text, el in self._randuri()]
				self._salvate_initial = {id(el): el.saved_value for el, _v in self._initiale}
				self.reface_lista()
				self._mesaj_profil(_("Profil aplicat. Setări sărite pentru taste sau funcții care lipsesc: %d.") % sarite)
			return self._lucru_profil("aplica", gata, ident=ales[2])

	def _salveaza_profil(self, nume):
		if nume is not None:
			return self._lucru_profil("salveaza", lambda x: self._mesaj_profil(_("Profil salvat: %s") % x["profile"]["name"]), nume=nume)

	def _schimba_profil(self, actiune, ident, nume=""):
		if nume is not None:
			return self._lucru_profil(actiune, lambda _x: self.profiluri(), ident=ident, nume=nume)

	def salveaza(self):
		if HdsTasteRapide.profil_ocupat() or self._profil_lucru:
			return
		HdsTasteRapide.salveaza(config)
		for k, _v, _text in HdsTasteRapide.PROFIL_SETARI:
			getattr(config.usage, k).save()
		configfile.save()
		self.close(True)

	def anuleaza(self):
		if HdsTasteRapide.profil_ocupat():
			return
		self._profil_inchide()
		for element, valoare in self._initiale:
			# Profilul aplicat din web cat ecranul era deschis ramane salvat.
			if element.saved_value != self._salvate_initial.get(id(element)):
				element.cancel()
			else:
				element.value = valoare
		self.close(False)


class HdsListaAlbastra(Screen):
	"""Ce apare in lista butonului ALBASTRU (Lista extensiilor) si in ce ordine (cererea lui tamiciav7, LinuxSat
	22.11.2026). Sus, bifate, randurile listei, in ordinea lor; dedesubt tot ce se mai poate pune: scurtaturile gata
	(actualizarea softului, informatiile de sistem, procesorul, repornirea retelei, testul de viteza), functiile tastelor,
	meniurile si pluginurile. OK pune sau scoate randul, GALBEN si ALBASTRU il muta, ROSU pune lista din fabrica. Totul se
	salveaza pe loc (Components/HdsTasteRapide.schimba_albastru, aceeasi ca pagina web /lista-albastra)."""

	skin = """
	<screen name="HdsListaAlbastra" resolution="1920,1080"
		position="center,center" size="1200,860">
		<widget name="lista" position="30,25" size="1140,630"
			scrollbarMode="showOnDemand" />
		<widget source="ghid" render="Label" position="30,670"
			size="1140,110" font="Regular;22" />
		<widget source="key_red" render="Label" position="30,795"
			size="360,40" font="Regular;22" halign="center"
			valign="center" backgroundColor="#9f1313" transparent="0" />
		<widget source="key_yellow" render="Label" position="420,795"
			size="360,40" font="Regular;22" halign="center"
			valign="center" backgroundColor="#a08000" transparent="0" />
		<widget source="key_blue" render="Label" position="810,795"
			size="360,40" font="Regular;22" halign="center"
			valign="center" backgroundColor="#245da8" transparent="0" />
	</screen>
	"""

	def __init__(self, session):
		Screen.__init__(self, session)
		from Components.SelectionList import SelectionList
		self.setTitle(_("Lista butonului albastru"))
		self["lista"] = SelectionList([])
		self["ghid"] = StaticText(_(
			"Rândurile bifate, de sus, sunt cele de pe butonul albastru, în ordinea lor. OK pune sau scoate rândul, "
			"GALBEN și ALBASTRU îl mută. Se salvează singur."))
		self["key_red"] = StaticText(_("Lista din fabrică"))
		self["key_yellow"] = StaticText(_("Mută sus"))
		self["key_blue"] = StaticText(_("Mută jos"))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions"], {
			"ok": self.comuta,
			"cancel": self.close,
			"red": self.fabrica,
			"yellow": lambda: self.muta("sus"),
			"blue": lambda: self.muta("jos"),
		}, -2)
		self.catalog = None
		self.randuri = []
		self.onLayoutFinish.append(self.umple)

	def umple(self):
		try:
			self.catalog = HdsTasteRapide.catalog_albastru(config)
		except Exception as e:
			print("[HdsListaAlbastra] catalogul: %s" % e)
			self.catalog = []
		self._arata(HdsTasteRapide.stare_albastru(config, self.catalog))

	def _arata(self, st, ales=None, index=None):
		from Components.SelectionList import SelectionEntryComponent
		dupa_id = dict((x["id"], x) for x in st["catalog"])
		self.randuri = [(dupa_id.get(i) or {"id": i, "nume": _("Indisponibil acum"), "grupa": ""}, True) for i in st["lista"]]
		self.randuri += [(x, False) for x in st["catalog"] if x["id"] not in st["lista"]]
		self["lista"].setList([SelectionEntryComponent(
			"%s  ·  %s" % (x["nume"], x["grupa"]) if x["grupa"] else x["nume"], x["id"], n, bifat)
			for n, (x, bifat) in enumerate(self.randuri)])
		if ales is not None:
			for n, (x, _b) in enumerate(self.randuri):
				if x["id"] == ales:
					index = n
					break
		if index is not None and self.randuri:
			self["lista"].moveToIndex(max(0, min(index, len(self.randuri) - 1)))

	def _curent(self):
		# dupa pozitia cursorului in randurile ecranului (nu dupa ce intoarce lista desenata)
		i = self["lista"].getSelectedIndex()
		if i is None or not 0 <= i < len(self.randuri):
			return None
		return self.randuri[i][0]["id"]

	def _schimba(self, actiune, ident=""):
		try:
			return HdsTasteRapide.schimba_albastru(actiune, ident, config, configfile, catalog=self.catalog)
		except Exception as e:
			print("[HdsListaAlbastra] %s %s: %s" % (actiune, ident, e))
			return None

	def comuta(self):
		ident = self._curent()
		if ident:
			# cursorul ramane pe loc, ca omul sa poata bifa mai multe randuri din catalog unul dupa altul
			index = self["lista"].getSelectedIndex()
			st = self._schimba("comuta", ident)
			if st is not None:
				self._arata(st, index=index)

	def muta(self, sens):
		ident = self._curent()
		if ident:
			st = self._schimba(sens, ident)
			if st is not None:
				self._arata(st, ales=ident)

	def fabrica(self):
		st = self._schimba("fabrica")
		if st is not None:
			self._arata(st, index=0)
