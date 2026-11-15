# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Ecranul Despre film: afisul, titlul, anul, genul, durata, notele, descrierea, regia si actorii filmului din ghid sau
dintr-o inregistrare. Se deschide din ecranul de informatii al emisiunii (INFO): tasta albastra unde e libera (lista
inregistrarilor), TEXT peste tot. Logica si cererile: Components/HdsDespreFilm.py; pagina web: /despre-film."""
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.Pixmap import Pixmap
from Components.ScrollLabel import ScrollLabel
from Screens.Screen import Screen
from Components import HdsDespreFilm as D


class HdsDespreFilm(Screen):
	skin = """
	<screen name="HdsDespreFilm" resolution="1920,1080" position="center,center" size="1500,820" title="Despre film">
		<widget name="afis" position="40,40" size="300,450" alphatest="blend" scale="1" />
		<widget name="titlu" position="380,36" size="1080,60" font="Regular;42" noWrap="1" />
		<widget name="detalii" position="380,104" size="1080,40" font="Regular;26" foregroundColor="#b0b8c8" noWrap="1" />
		<widget name="note" position="380,152" size="1080,40" font="Regular;28" foregroundColor="#f5c518" noWrap="1" />
		<widget name="text" position="380,210" size="1080,520" font="Regular;28" />
		<widget name="stare" position="40,510" size="300,220" font="Regular;24" foregroundColor="#b0b8c8" />
		<widget name="key_red" position="40,750" size="300,46" font="Regular;24" halign="center" valign="center" backgroundColor="#9f1313" />
		<widget name="key_green" position="360,750" size="300,46" font="Regular;24" halign="center" valign="center" backgroundColor="#1f771f" />
		<widget name="key_yellow" position="680,750" size="300,46" font="Regular;24" halign="center" valign="center" backgroundColor="#a08500" />
	</screen>
	"""

	def __init__(self, session, event=None, info=None):
		Screen.__init__(self, session)
		self.setTitle(_("Despre film"))
		self._info = info if info is not None else D.dinEveniment(event)
		self._candidati = []
		self._afis = ""
		self["afis"] = Pixmap()
		self["titlu"] = Label((self._info or {}).get("titlu") or "")
		self["detalii"] = Label("")
		self["note"] = Label("")
		self["text"] = ScrollLabel("")
		self["stare"] = Label(_("Caut filmul în Wikidata și Wikipedia..."))
		self["key_red"] = Label(_("Înapoi"))
		self["key_green"] = Label("")
		# Galben: cheia TMDB a omului (a doua sursa, numai cu cheia lui; Components/HdsDespreFilm.py, partea TMDB)
		self["key_yellow"] = Label(_("Cheia TMDB"))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], {
			"cancel": self.close,
			"ok": self.close,
			"red": self.close,
			"green": self._altFilm,
			"yellow": self._cheieTmdb,
			"up": self["text"].pageUp,
			"down": self["text"].pageDown,
			"left": self["text"].pageUp,
			"right": self["text"].pageDown,
		}, -1)
		self._cautare = D.Cautare(self._rezultat)
		self._cautareAfis = D.Cautare(self._afisGata)
		self._cautareCheie = D.Cautare(self._cheiePusa)
		self.onClose.append(self._inchis)
		self.onLayoutFinish.append(self._porneste)

	def _porneste(self):
		self["afis"].hide()
		if not self._info:
			self["stare"].setText(_("Emisiunea nu are titlu în ghid."))
			return
		self._cautare.porneste(D.cauta, self._info, D.limbaMeniului())

	def _inchis(self):
		self._cautare.opreste()
		self._cautareAfis.opreste()
		self._cautareCheie.opreste()

	def _rezultat(self, rez):
		stare = rez.get("stare")
		if stare == "alege":
			self._candidati = rez.get("candidati") or []
			self._alege()
			return
		if stare != "gata":
			self["stare"].setText(rez.get("mesaj") or _("Filmul nu s-a găsit."))
			self["text"].setText(_("Datele vin din Wikidata și Wikipedia, după titlul și anul din ghid. Unele emisiuni nu sunt filme sau nu au încă pagină."))
			return
		if rez.get("candidati") and not self._candidati:
			self._candidati = rez["candidati"]
		self._arata(rez["fisa"])

	def _alege(self):
		from Screens.ChoiceBox import ChoiceBox
		lista = [(D.textCandidat(c), c) for c in self._candidati]
		self["stare"].setText(_("Nu e sigur care film este. Alege din listă."))
		self["key_green"].setText(_("Alt film") if len(self._candidati) > 1 else "")
		self.session.openWithCallback(self._ales, ChoiceBox, title=_("Care film?"), list=lista)

	def _ales(self, ales):
		if not ales:
			if not self["text"].getText():
				self["stare"].setText(_("Niciun film ales. Verde: lista din nou."))
			return
		self["stare"].setText(_("Aduc fișa filmului..."))
		self._cautare.porneste(D.deschide, ales[1], D.limbaMeniului())

	def _altFilm(self):
		if len(self._candidati) > 1:
			self._alege()

	def _arata(self, f):
		self["titlu"].setText(f.get("titlu") or "")
		self["detalii"].setText(D.randDetalii(f))
		self["note"].setText(D.randNote(f))
		self["text"].setText(D.textLung(f))
		self["stare"].setText("")
		self["key_green"].setText(_("Alt film") if len(self._candidati) > 1 else "")
		self["afis"].hide()
		if f.get("afis_adresa"):
			self._cautareAfis.porneste(D.aduAfis, f["afis_adresa"])

	def _afisGata(self, cale):
		if not cale or not isinstance(cale, str):
			return
		from Tools.LoadPixmap import LoadPixmap
		try:
			px = LoadPixmap(cale)
		except Exception:
			px = None
		if px is not None and self["afis"].instance:
			self["afis"].instance.setPixmap(px)
			self["afis"].show()

	def _cheieTmdb(self):
		"""Galben: tastatura pentru cheia TMDB (goala = sterge cheia). Starea de acum scrisa in titlul tastaturii, fara cheie."""
		from Screens.VirtualKeyBoard import VirtualKeyBoard
		stare = D.stareCheieTmdb()
		titlu = u"%s\n%s" % (stare["text"], _("Lipește sau scrie cheia API sau tokenul de citire; gol = șterge cheia."))
		self.session.openWithCallback(self._cheieScrisa, VirtualKeyBoard, title=titlu, text=u"")

	def _cheieScrisa(self, text):
		if text is None:
			return
		if not D.curataCheieTmdb(text) and not D.stareCheieTmdb()["pusa"]:
			return
		self["stare"].setText(_("Verific cheia la TMDB..."))
		self._cautareCheie.porneste(D.pastreazaCheieTmdb, text)

	def _cheiePusa(self, rez):
		ok, mesaj = rez if isinstance(rez, tuple) else (False, (rez or {}).get("mesaj") or u"")
		self["stare"].setText(mesaj)
		if ok and self._info:
			# fisa din nou, cu sau fara TMDB (memoria fiselor s-a golit odata cu cheia)
			self._cautare.porneste(D.cauta, self._info, D.limbaMeniului())


def deschide(session, event=None, info=None):
	session.open(HdsDespreFilm, event=event, info=info)
