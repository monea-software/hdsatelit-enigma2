# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsFonturi: ecranul de pe televizor pentru fonturile Google, descarcate de om direct pe receptor.
#
# Ce face: lista celor ~1800 de familii libere de pe fonts.google.com (fara nicio cheie
# de acces), cautare dupa nume, marimea adevarata a fisierului, licenta, descarcare cu
# bara de progres care NU blocheaza interfata (fir separat + eTimer), previzualizare cu
# text romanesc cu diacritice, lista fonturilor descarcate si stergere.
#
# Tot ce tine de retea, verificare si inregistrare sta in Components/HdsFonturiGoogle.py,
# acelasi modul folosit si de interfata web -- o singura sursa de adevar.
#
# SIGURANTA: niciun fisier descarcat nu ajunge la addFont inainte sa treaca verificatorul
# din modul. addFont pe un fisier care nu e font face eFatal si opreste receptorul
# (lib/gdi/font.cpp:133).
#
# Skinul: HdsFonturi din skin.xml (cadrul HdsCadru1776, titlul si ceasul in placa, tastele colorate jos); pe alt skin,
# rezerva de mai jos, scrisa pe 1280 in acelasi desen si scalata la ecran (Tools/ScaledSkin). Bara de progres se vede
# numai cat se descarca.

from __future__ import absolute_import

import threading

from enigma import eTimer, gFont

from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Screens.VirtualKeyBoard import VirtualKeyBoard
from Components.ActionMap import ActionMap
from Components.Button import Button
from Components.Label import Label
from Components.MenuList import MenuList
from Components.ProgressBar import ProgressBar

from Components import HdsFonturiGoogle as fonturi
from Tools.ScaledSkin import scaledSkin


TEXT_PROBA = "Ana are mere: ăâîșț ĂÂÎȘȚ 0123456789"


def _modSigur():
	"""True cand interfata a pornit in modul sigur (Components/HdsModSigur)."""
	try:
		from Components import HdsModSigur
		return HdsModSigur.activ()
	except Exception:
		return False


class HdsFonturi(Screen):
	"""Fonturi Google descărcate direct de pe receptor."""

	# rezerva pe 1280 (cotele de 1920 x 2/3), culorile skinului HDSatelit scrise ca numere
	SKIN_REZERVA = """
	<screen name="HdsFonturi" position="48,27" size="1184,666" backgroundColor="#0D10162A" flags="wfNoBorder" title="Fonturi Google">
		<eLabel position="0,0" size="1184,1" backgroundColor="#99FFFFFF" zPosition="1" />
		<widget source="Title" render="Label" position="21,12" size="1024,37" font="Bold;27" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" transparent="1" valign="center" noWrap="1" zPosition="1" />
		<widget source="global.CurrentTime" render="Label" position="1056,12" size="107,37" font="Bold;27" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" transparent="1" halign="right" valign="center" zPosition="1">
			<convert type="ClockToText">Format:%H:%M</convert>
		</widget>
		<eLabel position="21,59" size="1141,1" backgroundColor="#D9FFFFFF" zPosition="1" />
		<widget name="cautare" position="21,69" size="733,29" font="Bold;20" foregroundColor="#00F5B83D" backgroundColor="#0D10162A" transparent="1" valign="center" noWrap="1" zPosition="1" />
		<widget name="numar" position="763,69" size="400,29" font="Regular;17" foregroundColor="#00AEB9CC" backgroundColor="#0D10162A" transparent="1" halign="right" valign="center" noWrap="1" zPosition="1" />
		<widget name="lista" position="21,107" size="667,360" itemHeight="36" textOffset="11,0" font="Regular;19" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" backgroundColorSelected="#00374EA1" foregroundColorSelected="#00FFFFFF" transparent="1" scrollbarMode="showOnDemand" zPosition="2" />
		<eLabel position="699,107" size="1,360" backgroundColor="#D9FFFFFF" zPosition="1" />
		<widget name="detalii" position="709,107" size="453,280" font="Regular;17" foregroundColor="#00C9D2E3" backgroundColor="#0D10162A" transparent="1" zPosition="1" />
		<widget name="previzualizare" position="709,392" size="453,75" font="Regular;20" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" transparent="1" valign="center" zPosition="1" />
		<widget name="progres" position="21,475" size="1141,8" foregroundColor="#009FB4FF" backgroundColor="#002A3350" zPosition="2" />
		<widget name="stare" position="21,491" size="1141,117" font="Regular;19" foregroundColor="#00C9D2E3" backgroundColor="#0D10162A" transparent="1" zPosition="1" />
		<eLabel position="21,616" size="1141,1" backgroundColor="#D9FFFFFF" zPosition="1" />
		<eLabel position="21,629" size="4,21" backgroundColor="#00E5484D" zPosition="1" />
		<widget name="buton_rosu" position="32,624" size="269,32" font="Regular;19" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" transparent="1" halign="left" valign="center" zPosition="1" />
		<eLabel position="307,629" size="4,21" backgroundColor="#0046B06A" zPosition="1" />
		<widget name="buton_verde" position="317,624" size="269,32" font="Regular;19" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" transparent="1" halign="left" valign="center" zPosition="1" />
		<eLabel position="592,629" size="4,21" backgroundColor="#00E8B93A" zPosition="1" />
		<widget name="buton_galben" position="603,624" size="269,32" font="Regular;19" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" transparent="1" halign="left" valign="center" zPosition="1" />
		<eLabel position="877,629" size="4,21" backgroundColor="#003D7BE0" zPosition="1" />
		<widget name="buton_albastru" position="888,624" size="269,32" font="Regular;19" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" transparent="1" halign="left" valign="center" zPosition="1" />
	</screen>"""

	def __init__(self, session):
		self.skin = scaledSkin(self.SKIN_REZERVA)
		Screen.__init__(self, session)
		self.skinName = ["HdsFonturi"]
		self.setTitle(_("Fonturi Google"))

		self._inchis = False
		self._toate = []
		self._filtrate = []
		self._cautare = ""
		self._modul = "toate"          # "toate" sau "descarcate"
		self._descarcate = []
		self._lucreaza = False
		self._rezultat = None          # pus de fir, citit de ceas
		self._progres = (0, 0)
		self._anulat = False

		self["cautare"] = Label(_("Caută: (toate)"))
		self["numar"] = Label("")
		self["lista"] = MenuList([])
		self["detalii"] = Label(_("Se citește lista de la Google..."))
		self["previzualizare"] = Label("")
		self["progres"] = ProgressBar()
		self["stare"] = Label("")
		self["buton_rosu"] = Button(_("Închide"))
		self["buton_verde"] = Button(_("Descarcă"))
		self["buton_galben"] = Button(_("Caută"))
		self["buton_albastru"] = Button(_("Descărcate"))

		self["tastatura"] = ActionMap(
			["ColorActions", "OkCancelActions", "DirectionActions", "MenuActions"],
			{
				"red": self.inchide,
				"cancel": self.inchide,
				"green": self.actiuneVerde,
				"yellow": self.deschideCautarea,
				"blue": self.comutaModul,
				"ok": self.actiuneVerde,
				"menu": self.stergeSelectat,
			}, -1)

		self._ceas = eTimer()
		try:
			self._ceas.callback.append(self._bate)
		except AttributeError:
			self._ceas_conn = self._ceas.timeout.connect(self._bate)

		self["lista"].onSelectionChanged.append(self._aratasDetalii)
		self.onLayoutFinish.append(self._porneste)
		self.onClose.append(self._laInchidere)

	# ------------------------------------------------------------------ viata ecranului

	def _laInchidere(self):
		# Firul de descarcare poate veni mai tarziu; steagul il face inofensiv, la fel ca
		# in HdsDvbI (KeyError pe un widget al unui ecran deja inchis).
		self._inchis = True
		self._anulat = True
		self._ceas.stop()

	def inchide(self):
		if self._lucreaza:
			self._anulat = True
			self["stare"].setText(_("Se anulează descărcarea..."))
			return
		self.close()

	def _porneste(self):
		self._descarcate = fonturi.fonturiDescarcate()
		unde = _("mediu extern (rezistă la actualizarea imaginii)") if fonturi.peMediuExtern() \
			else _("memoria receptorului (o actualizare de imagine le șterge)")
		self["stare"].setText(_("Fonturile se pun în: %s\nSe citește lista de la Google...") % unde)
		self._porneste_fir(self._firLista)

	def _porneste_fir(self, functie):
		self["progres"].show()
		self._lucreaza = True
		self._rezultat = None
		self._progres = (0, 0)
		fir = threading.Thread(target=functie)
		fir.daemon = True
		fir.start()
		self._ceas.start(200, False)

	def _bate(self):
		"""Singurul loc care atinge widgeturile in timpul unei descarcari: firul enigma2."""
		if self._inchis:
			return
		descarcat, total = self._progres
		if total:
			self["progres"].setValue(int(descarcat * 100 / total))
			self["stare"].setText(_("Se descarcă: %s din %s") % (
				fonturi.marimeText(descarcat), fonturi.marimeText(total)))
		elif descarcat:
			self["stare"].setText(_("Se descarcă: %s") % fonturi.marimeText(descarcat))
		rezultat = self._rezultat
		if rezultat is None:
			return
		self._ceas.stop()
		self._lucreaza = False
		self._rezultat = None
		self["progres"].setValue(0)
		self["progres"].hide()
		fel = rezultat[0]
		if fel == "lista":
			self._gataLista(rezultat[1], rezultat[2])
		elif fel == "descarcare":
			self._gataDescarcare(rezultat[1], rezultat[2], rezultat[3])

	# ------------------------------------------------------------------ lista

	def _firLista(self):
		try:
			lista, eroare = fonturi.listaFamilii()
		except Exception as e:       # nimic nu are voie sa scape dintr-un fir
			lista, eroare = [], str(e)
		self._rezultat = ("lista", lista, eroare)

	def _gataLista(self, lista, eroare):
		self._toate = lista
		if eroare and not lista:
			self["stare"].setText(_("Lista nu s-a putut citi: %s") % eroare)
		else:
			self["stare"].setText(_("Lista e gata. Galben = caută, Verde = descarcă, Albastru = fonturile descărcate."))
		self._reconstruieste()

	def _reconstruieste(self):
		self._descarcate = fonturi.fonturiDescarcate()
		aliasuri = set(f["alias"] for f in self._descarcate)
		if self._modul == "descarcate":
			self._filtrate = []
			intrari = []
			for font in self._descarcate:
				# starea in cuvinte, la sfarsitul randului (fontul interfetei nu are semnele bifa/cruce U+2713/U+2717)
				intrari.append("%s · %s · %s%s" % (
					font["familie"][:30], fonturi.marimeText(font["octeti"]),
					"".join(font["diacritice"]) or _("fără diacritice"), "" if font["bun"] else " · " + _("stricat")))
			if not intrari:
				intrari = [_("(niciun font descărcat încă)")]
			self["lista"].setList(intrari)
			self["numar"].setText(_("%d descărcate") % len(self._descarcate))
			self["cautare"].setText(_("Fonturi descărcate"))
			self["buton_verde"].setText(_("Previzualizare"))
			self["buton_albastru"].setText(_("Toate"))
		else:
			self._filtrate = fonturi.cauta(self._toate, self._cautare)
			intrari = []
			for familie in self._filtrate:
				descarcat = fonturi.aliasFamilie(familie["familie"]) in aliasuri
				diac = "ăâîșț" if "latin-ext" in familie["subseturi"] else "-"
				intrari.append("%s · %s · %s · %s%s" % (
					familie["familie"][:30], familie["categorie"][:12],
					diac, fonturi.marimeText(familie["marime"]), " · " + _("descărcat") if descarcat else ""))
			if not intrari:
				intrari = [_("(niciun font nu se potrivește)")]
			self["lista"].setList(intrari)
			self["numar"].setText(_("%d din %d familii") % (len(self._filtrate), len(self._toate)))
			self["cautare"].setText(_("Caută: %s") % (self._cautare or _("(toate)")))
			self["buton_verde"].setText(_("Descarcă"))
			self["buton_albastru"].setText(_("Descărcate"))
		self._aratasDetalii()

	def _selectat(self):
		index = self["lista"].getSelectionIndex()
		sursa = self._descarcate if self._modul == "descarcate" else self._filtrate
		if index is None or index < 0 or index >= len(sursa):
			return None
		return sursa[index]

	def _aratasDetalii(self):
		if self._inchis:
			return
		ales = self._selectat()
		if not ales:
			self["detalii"].setText("")
			self["previzualizare"].setText("")
			return
		if self._modul == "descarcate":
			linii = [
				_("Familia: %s") % ales["familie"],
				_("Nume în skin: %s") % ales["alias"],
				_("Fișier: %s") % ales["cale"],
				_("Mărime: %s") % fonturi.marimeText(ales["octeti"]),
				_("Diacritice românești: %s") % ("".join(ales["diacritice"]) or _("lipsesc")),
				_("Verificare: %s") % ales["motiv"],
				_("Locul: %s") % (_("mediu extern") if ales["extern"] else _("memoria receptorului")),
				"",
				_("În skin se scrie: font=\"%s;24\"") % ales["alias"],
				"",
				_("MENIU = șterge fontul."),
			]
			self["detalii"].setText("\n".join(linii))
			self._detaliiMarite()
			self._previzualizeaza(ales["alias"] if ales["bun"] else None)
		else:
			alias = fonturi.aliasFamilie(ales["familie"])
			descarcat = any(f["alias"] == alias for f in self._descarcate)
			linii = [
				_("Familia: %s") % ales["familie"],
				_("Nume în skin: %s") % alias,
				_("Categorie: %s") % ales["categorie"],
				_("Greutăți: %s") % (", ".join(ales["greutati"][:8]) or "?"),
				_("Font variabil: %s") % (_("da") if ales["variabil"] else _("nu")),
				_("Alfabete: %s") % ", ".join(ales["subseturi"][:4]),
				_("Diacritice românești (ș, ț): %s") % (
					_("da, are latin-ext") if "latin-ext" in ales["subseturi"] else _("probabil NU, nu are latin-ext")),
				_("Familia întreagă: %s (se descarcă doar literele necesare)") % fonturi.marimeText(ales["marime"]),
				_("Desenat de: %s") % (", ".join(ales["desenatori"][:2]) or "?"),
				"",
				_("Deja descărcat.") if descarcat else _("VERDE = descarcă și verifică."),
			]
			self["detalii"].setText("\n".join(linii))
			self._detaliiMarite()
			self._previzualizeaza(alias if descarcat else None)

	def _detaliiMarite(self):
		"""Textul marit (Marimea textului peste 100 %, Components/HdsMarireText): detaliile (11 randuri la 100 %) cresc in
		jos peste previzualizare, care se strange (ramane de cel putin 60 px), iar cand tot nu incap, fontul lor scade cu
		cate un pixel (nu sub marimea de la 100 %); la 115 % se pierdea ultimul rand ("VERDE = descarca si verifica").
		La 100 % nu se schimba nimic."""
		try:
			from Components import HdsMarireText as MT
			if not MT.marit():
				return
			det, prev = self["detalii"].instance, self["previzualizare"].instance
			if getattr(self, "_asezare", None) is None:
				self._asezare = MT.Asezare(self)
				self._marimeDetalii = MT.marimeFont(det)
			a = self._asezare
			skD, skP = a.dinSkin(det), a.dinSkin(prev)
			if not skD or not skP:
				return
			MT.puneMarime(det, self._marimeDetalii)
			d = a.creste(det, MT.inaltimeText(det), skP[1] + skP[3], maxim=max(0, skP[3] - 60))
			MT.potrivesteFont(det, skD[3] + d, self._marimeDetalii)
		except Exception as e:
			print("[HdsFonturi] textul marit: %s" % e)

	def _previzualizeaza(self, alias):
		"""Textul de probă cu fontul ales. Un font se poate arăta doar după ce e pe receptor
		(FreeType desenează dintr-un fișier, nu dintr-o listă); înainte de descărcare
		ecranul spune în schimb dacă familia are latin-ext, adică ș și ț."""
		# Fontul se pune INAINTE de text: `setText` redeseneaza imediat cu fontul curent, iar
		# daca acela e un alias al unui font tocmai scos din folosinta, desenarea ar cere din
		# nou fisierul de pe disc (font.cpp:85 FTC_Face_Requester) si ar cadea in
		# eFatal("no current_face") (font.cpp:505).
		# Un font descarcat e al lui enigma2 numai daca s-a inregistrat (HdsFonturiGoogle); in modul sigur
		# (Components/HdsModSigur) fonturile descarcate nu se inregistreaza deloc. gFont pe un alias neinregistrat
		# scrie un avertisment in jurnal (font.cpp) si nu deseneaza nimic: atunci numai textul care spune de ce.
		neincarcat = bool(alias) and alias not in fonturi.aliasuriInregistrate()
		if neincarcat:
			alias = None
		try:
			self["previzualizare"].instance.setFont(gFont(alias or "Regular", 30 if alias else 22))
		except Exception:
			pass
		if alias:
			text = TEXT_PROBA
		elif neincarcat:
			text = _("Mod sigur: fontul nu e încărcat acum.") if _modSigur() else _("Fontul nu e încărcat acum.")
		else:
			text = _("(previzualizarea se vede după descărcare)")
		self["previzualizare"].setText(text)

	# ------------------------------------------------------------------ butoane

	def comutaModul(self):
		if self._lucreaza:
			return
		self._modul = "toate" if self._modul == "descarcate" else "descarcate"
		self._reconstruieste()

	def deschideCautarea(self):
		if self._lucreaza or self._modul == "descarcate":
			return
		self.session.openWithCallback(self._cautareGata, VirtualKeyBoard,
			title=_("Numele fontului"), text=self._cautare)

	def _cautareGata(self, text):
		if text is None:
			return
		self._cautare = text.strip()
		self._reconstruieste()

	def actiuneVerde(self):
		if self._lucreaza:
			return
		ales = self._selectat()
		if not ales:
			return
		if self._modul == "descarcate":
			self._previzualizeaza(ales["alias"] if ales["bun"] else None)
			return
		self._cereDescarcarea(ales, False)

	def _cereDescarcarea(self, familie, confirma_mare):
		self._familie_aleasa = familie
		self._confirma_mare = confirma_mare
		self._anulat = False
		self["stare"].setText(_("Se caută licența și fișierul pentru „%s”...") % familie["familie"])
		self._porneste_fir(self._firDescarcare)

	def _firDescarcare(self):
		familie = self._familie_aleasa

		def progres(descarcat, total):
			self._progres = (descarcat, total)

		def opreste():
			return self._anulat or self._inchis

		try:
			bun, mesaj, cale = fonturi.descarca(
				familie["familie"], familie["subseturi"], progres, opreste, self._confirma_mare)
		except Exception as e:
			bun, mesaj, cale = False, str(e), None
		self._rezultat = ("descarcare", bun, mesaj, cale)

	def _gataDescarcare(self, bun, mesaj, cale=None):
		# Inregistrarea se face AICI, pe firul principal: `getFaceID` (font.cpp:105) parcurge
		# lista de fonturi fara lacat, deci `addFont` nu are ce cauta pe firul de descarcare.
		if bun and cale:
			reusit, mesaj_reg = fonturi.inregistreazaUnFont(cale, self._familie_aleasa["familie"])
			if not reusit:
				bun, mesaj = False, mesaj_reg
		self["stare"].setText(mesaj)
		if not bun and _("Confirmă descărcarea mare") in mesaj:
			self.session.openWithCallback(
				self._raspunsMare, MessageBox,
				mesaj + "\n\n" + _("Fonturile mari umplu memoria receptorului. Descarci totuși?"),
				MessageBox.TYPE_YESNO, default=False)
			return
		self._reconstruieste()

	def _raspunsMare(self, da):
		if da:
			self._cereDescarcarea(self._familie_aleasa, True)

	# ------------------------------------------------------------------ stergere

	def stergeSelectat(self):
		if self._lucreaza or self._modul != "descarcate":
			return
		ales = self._selectat()
		if not ales:
			return
		self._de_sters = ales
		self.session.openWithCallback(
			self._confirmaStergerea, MessageBox,
			_("Ștergi fontul „%s”?\nUn skin care îl folosește va rămâne fără el.") % ales["familie"],
			MessageBox.TYPE_YESNO, default=False)

	def _confirmaStergerea(self, da):
		if not da:
			return
		self._previzualizeaza(None)   # scoate fontul sters de pe previzualizare INAINTE de stergere
		bun, mesaj = fonturi.stergeFont(self._de_sters["alias"])
		self["stare"].setText(mesaj)
		self._reconstruieste()
