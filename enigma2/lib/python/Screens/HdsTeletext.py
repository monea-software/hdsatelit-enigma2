# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsTeletext.py: vizualizatorul de teletext al imaginii, pe tasta TEXT din bara (Screens/InfoBar.py,
# hdsTeletextSauMesaj).
#
# Paginile le culege nucleul cat timp canalul merge (lib/dvb/hdsteletext.cpp), deci o pagina vazuta o data in carusel
# se arata pe loc. Desenul il face widgetul eHdsTeletextWidget (lib/gui/ehdsteletext.cpp), cu fontul din skin:
# "Teletext clasic" sau "Teletext neted" (mozaicul netezit; numele intern a ramas hd), cu optiunile oprite din fabrica:
# conturul literelor (numai la cele deschise la culoare), umbra literelor si, numai la neted, formele in relief.
# Paginile pot veni si dintr-o copie salvata (Components/HdsTeletextCopie.py), fara tuner.
#
# Tastele: cifrele (trei, pagina 100-899, se vad in antet cat le tastezi), SUS / JOS si CH+ / CH- pagina urmatoare /
# dinainte dintre cele primite, STANGA / DREAPTA subpaginile, OK tine subpagina (sau o lasa sa mearga singura),
# tastele colorate (FastText, altfel TOP, altfel -1 / +1 / +100 / pagina de pornire), INFO arata ce e ascuns, TEXT
# trece intre pe tot ecranul si peste imagine, AUDIO arata pagina de acum in original sau tradusa, MENU (clasic sau
# neted, conturul, umbra, relieful, traducerea, copiile, reimprospatarea), EXIT inchide (sau sterge cifrele tastate).
#
# TRADUCEREA (setarea "Tradu teletextul", oprita din fabrica; Components/HdsTraducereTeletext.py): pagina se arata intai
# originala; textul ei pleaca la tradus in fundal (desenul nu asteapta), iar cand vine traducerea ecranul e chemat
# (hdsTraducereEpg) si o pune: in pagina (randurile traduse peste celule, eHdsTeletextWidget.setTraducere) sau intr-un
# panou in dreapta, langa pagina micsorata (setarea "Teletextul tradus"). Un indiciu mic pe ecran spune starea si tasta
# AUDIO (originalul paginii de acum; alta pagina vine iar tradusa). Panoul si indiciul sunt o fereastra separata
# (PanouTraducere, cu skinul ei), deci merg pe orice skin. Un nucleu fara setTraducere arata traducerea in panou.
#
# Perechea in web: /teletext (Plugins/Extensions/HdsWebControl/teletext_web.py), din aceleasi module comune
# (Components/HdsTeletext.py, Components/HdsTeletextCopie.py).
from enigma import eHdsTeletextWidget, eHdsTeletext, eTimer, getDesktop, eSize, ePoint

from Components.ActionMap import ActionMap
from Components.GUIComponent import GUIComponent
from Components.Label import Label
from Components import HdsTeletext as T
from Components import HdsTeletextCopie as C
from Screens.Screen import Screen

MESAJ_MS = 2500
LATIME_CU_PANOU = 60    # cu traducerea in panou: pagina in stanga, pe atatea procente din latimea ecranului
MESAJ_LUNG_MS = 8000    # motivul unei reimprospatari esuate (doua randuri de citit)
CEAS_MS = 250
FAZA_MS = 500
LOC_COPIE = 0           # locul copiei de pe televizor in nucleu (eHdsTeletext.copie(0))


class PaginaTeletext(GUIComponent):
	"""Widgetul paginii (eHdsTeletextWidget): fontul din skin, felul, starea din antet si pagina."""
	GUI_WIDGET = eHdsTeletextWidget

	def __init__(self):
		GUIComponent.__init__(self)


def _setari():
	try:
		return C.setari()
	except Exception:
		return None


def _valoare(s, nume):
	"""Valoarea unei optiuni (False daca setarea lipseste)."""
	try:
		return bool(getattr(s, nume).value)
	except Exception:
		return False


def _salveaza(element):
	"""Setarea scrisa pe loc in /etc/enigma2/settings (ca formatul imaginii din bara), nu numai la oprire."""
	element.save()
	try:
		from Components.config import configfile
		configfile.save()
	except Exception as e:
		print("[HdsTeletext] setarile nu s-au scris:", e)


def _fontHds(nume):
	"""fontul HD Satelit cu rolul `nume` sub un skin strain (skin.fontHds); cu HDSatelit ales, `nume`"""
	try:
		import skin
		return skin.fontHds(nume)
	except Exception:
		return nume


# ---------------------------------------------------------------- traducerea paginii

def _setariTraducere():
	"""config.hds_traducere (Components/HdsTraducereSubtitrari.py), sau None"""
	try:
		from Components import HdsTraducereSubtitrari
		return HdsTraducereSubtitrari.initConfig()
	except Exception:
		return None


def _modTraducere():
	""""pagina" sau "panou" cand "Tradu teletextul" e pornita, altfel None"""
	s = _setariTraducere()
	try:
		if s is None or not s.teletext.value:
			return None
		return "panou" if s.teletext_mod.value == "panou" else "pagina"
	except Exception:
		return None


def _traducereTeletext():
	"""Components/HdsTraducereTeletext.py (traducerea comuna a paginilor), sau None"""
	try:
		from Components import HdsTraducereTeletext
		return HdsTraducereTeletext
	except Exception as e:
		print("[HdsTeletext] traducerea:", e)
		return None


def _octetiPagina(numar, subcod, nucleu):
	"""celulele paginii aratate (eHdsTeletext.pagina, fara antet), sau None"""
	n = nucleu if nucleu is not None else T.nucleu()
	if n is None:
		return None
	try:
		r = n.pagina(int(numar), int(subcod), "", 0)
	except Exception:
		return None
	return r[3] if r else None


class PanouTraducere(Screen):
	"""Panoul traducerii si indiciul, o fereastra deasupra teletextului (cu skinul ei; locul il da HdsTeletext). Skinul e
	scris pe 1920x1080 (resolution=): sub un skin cu alta rezolutie se micsoreaza odata cu ecranul, cu fonturile HD
	Satelit (skin.py, scaraEcran)."""
	skin = """<screen name="HdsTeletextTraducere" resolution="1920,1080" position="1180,60" size="700,960" flags="wfNoBorder" backgroundColor="transparent" zPosition="1">
		<widget name="panou" position="0,0" size="700,850" font="Regular;28" foregroundColor="#ffffff" backgroundColor="#14181f" valign="top" zPosition="1" />
		<widget name="indiciu" position="0,860" size="700,100" font="Regular;24" foregroundColor="#ffe9a8" backgroundColor="#14181f" halign="center" valign="center" zPosition="1" />
	</screen>"""

	def __init__(self, session):
		Screen.__init__(self, session)
		self["panou"] = Label("")
		self["indiciu"] = Label("")


class HdsTeletext(Screen):
	skin = """<screen name="HdsTeletext" position="0,0" size="1920,1080" flags="wfNoBorder" backgroundColor="transparent" title="Teletext">
		<widget name="pagina" position="0,0" size="1920,1080" font="Regular;40" zPosition="1" />
		<widget name="mesaj" position="560,496" size="800,88" font="Regular;36" halign="center" valign="center" foregroundColor="#ffffff" backgroundColor="#1a1d24" zPosition="2" />
	</screen>"""

	def __init__(self, session, pagina=None, copie=None):
		Screen.__init__(self, session)
		self.setTitle(_("Teletext"))
		self["pagina"] = PaginaTeletext()
		self["mesaj"] = Label("")
		self.copie = None           # informatiile copiei aratate (Components/HdsTeletextCopie.copia) sau None = direct
		self.nucleu = None          # None = canalul care merge; altfel eHdsTeletext.copie(LOC_COPIE)
		if copie:
			info = C.incarca(copie, LOC_COPIE)
			if info is not None:
				self.copie = info
				self.nucleu = eHdsTeletext.copie(LOC_COPIE)
		st = T.stare(self.nucleu)
		self.initiala = st["initiala"]
		self.numar = T.normalizeaza(pagina) or self.initiala
		self.subcod = -1
		self.tinut = False
		self.ascuns = False
		self.tastare = T.Tastare()
		self.gasita = False
		self.faza = 0
		self.tradus_original = False    # AUDIO: pagina de acum in original (alta pagina vine iar tradusa)
		self._trad_rez = None           # rezultatul traducerii aratat (Components/HdsTraducereTeletext.Rezultat)
		self._trad_pus = None           # rezultatul pus in nucleu (setTraducere)
		self._trad_forteaza = False     # a venit o traducere: pagina se cere din nou
		self._trad_panou = False        # pagina e micsorata pentru panou
		self._trad_dialog = None        # PanouTraducere
		self._trad_vazut = None         # (geometria, panoul, indiciul) aratate
		self._mesaj_x = None            # locul casetei de mesaj din skin (x), fara panou
		self.mesaj_temporar = ""
		self.mesaj_loc = None       # (pozitia, marimea) casetei de mesaj din skin; un mesaj lung o inalta cat ii trebuie
		self["actiuni"] = ActionMap(["NumberActions", "ColorActions", "DirectionActions", "OkCancelActions",
			"HdsTeletextActions"], {
			"1": lambda: self.cifra(1), "2": lambda: self.cifra(2), "3": lambda: self.cifra(3),
			"4": lambda: self.cifra(4), "5": lambda: self.cifra(5), "6": lambda: self.cifra(6),
			"7": lambda: self.cifra(7), "8": lambda: self.cifra(8), "9": lambda: self.cifra(9),
			"0": lambda: self.cifra(0),
			"red": lambda: self.culoare(0), "green": lambda: self.culoare(1),
			"yellow": lambda: self.culoare(2), "blue": lambda: self.culoare(3),
			"up": lambda: self.pas(1), "down": lambda: self.pas(-1),
			"left": lambda: self.subpagina(-1), "right": lambda: self.subpagina(1),
			"ok": self.tine, "cancel": self.iesire,
			"mod": self.schimbaMod, "ascuns": self.schimbaAscuns, "meniu": self.meniu,
			"paginaInainte": lambda: self.pas(1), "paginaInapoi": lambda: self.pas(-1),
			"traducere": self.schimbaTraducerea,
		}, -1)
		self.ceas = eTimer()
		self.ceas.callback.append(self.actualizeaza)
		self.ceas_faza = eTimer()
		self.ceas_faza.callback.append(self.schimbaFaza)
		self.ceas_mesaj = eTimer()
		self.ceas_mesaj.callback.append(self.mesajExpirat)
		self.onLayoutFinish.append(self.porneste)
		self.onClose.append(self.opreste)
		# panoul (fereastra lui, deasupra) pleaca odata cu teletextul cand se deschide un meniu peste el, apoi revine
		self.onHide.append(self._laAscundere)
		self.onShow.append(self._laAratare)

	# ---------------------------------------------------------------- pornire si oprire

	def porneste(self):
		w = self["pagina"].instance
		desktop = getDesktop(0).size()
		# pe orice skin pagina are tot ecranul: widgetul (si fereastra) cat desktopul
		self.instance.move(ePoint(0, 0))
		self.instance.resize(eSize(desktop.width(), desktop.height()))
		w.move(ePoint(0, 0))
		w.resize(eSize(desktop.width(), desktop.height()))
		s = _setari()
		w.setPeste(1 if s is not None and s.peste.value else 0)
		w.setHd(1 if s is not None and s.hd.value else 0)     # neted oprit din fabrica (0.3.0)
		# optiunile, oprite din fabrica
		for nume in ("contur", "umbra", "relief"):
			getattr(w, "set" + nume.capitalize())(1 if s is not None and _valoare(s, nume) else 0)
		w.setSursa(LOC_COPIE if self.nucleu is not None else -1)
		try:
			self._trad_dialog = self.session.instantiateDialog(PanouTraducere)
		except Exception as e:
			print("[HdsTeletext] panoul traducerii:", e)
			self._trad_dialog = None
		self.aratPagina()
		if self.copie is not None:
			self.anunta(_("Copia din %s") % C.data_text(self.copie.get("data")))
		self.ceas.start(CEAS_MS, False)
		self.ceas_faza.start(FAZA_MS, False)

	def opreste(self):
		T.PE_TELEVIZOR["numar"] = None
		T.PE_TELEVIZOR["subcod"] = -1
		self.ceas.stop()
		self.ceas_faza.stop()
		self.ceas_mesaj.stop()
		if self._trad_dialog is not None:
			try:
				self._trad_dialog.hide()
				self.session.deleteDialog(self._trad_dialog)
			except Exception as e:
				print("[HdsTeletext] panoul traducerii:", e)
			self._trad_dialog = None

	# ---------------------------------------------------------------- pagina

	def textStare(self):
		if self.tastare.in_curs:
			return T.text_stare(self.numar, self.tastare.cifre)
		text = T.text_stare(self.numar)
		w = self["pagina"].instance
		toate = T.subpagini(self.numar, self.nucleu)
		poz = T.subcod_text(w.subcodAratat() if w else -1, toate)
		if poz and len(text) + 1 + len(poz) <= 8:
			text += " " + poz
		return text

	def aratPagina(self):
		w = self["pagina"].instance
		if w is None:
			return
		w.setStare(self.textStare())
		self.gasita = bool(w.setPagina(self.numar, self.subcod if self.tinut else -1))
		if self.nucleu is None:
			T.PE_TELEVIZOR["numar"] = self.numar
			T.PE_TELEVIZOR["subcod"] = self.subcod if self.tinut else -1
		self.mesajPagina()
		self.traducePagina()

	def actualizeaza(self):
		w = self["pagina"].instance
		if w is None:
			return
		self.gasita = bool(w.actualizeaza())
		w.setStare(self.textStare())
		self.mesajPagina()
		self.traducePagina()

	# ---------------------------------------------------------------- traducerea

	def hdsTraducereEpg(self):
		"""traducatorul (Components/HdsTraducereTexte.py): au venit traduceri, sau setarea s-a schimbat"""
		self._trad_forteaza = True
		self.traducePagina()

	def _refCanal(self):
		if self.copie is not None:
			return self.copie.get("ref") or ""
		try:
			ref = self.session.nav.getCurrentlyPlayingServiceReference()
			return ref.toString() if ref is not None else ""
		except Exception:
			return ""

	def traducePagina(self):
		"""pagina aratata, tradusa daca setarea e pornita: textul ei pleaca in fundal, traducerea se pune cand vine"""
		w = self["pagina"].instance
		if w is None:
			return
		mod = _modTraducere()
		M = _traducereTeletext() if mod is not None else None
		if M is None or not T.are_teletext(self.nucleu):
			self._puneTraducerea(None, None)
			return
		if self.tradus_original:
			self._puneTraducerea(None, mod, original=True)
			return
		subcod = w.subcodAratat()
		octeti = _octetiPagina(self.numar, subcod, self.nucleu) if self.gasita and subcod >= 0 else None
		if octeti is None:
			self._puneTraducerea(None, mod)
			return
		forteaza, self._trad_forteaza = self._trad_forteaza, False
		try:
			rez = M.traducere().pagina(self._refCanal(), self.numar, subcod, octeti, cine=self, forteaza=forteaza)
		except Exception as e:
			print("[HdsTeletext] traducerea paginii %d: %s" % (self.numar, e))
			rez = None
		self._puneTraducerea(rez, mod)

	def _puneTraducerea(self, rez, mod, original=False):
		"""traducerea in nucleu (modul pagina) sau in panou, si indiciul; mod None = traducerea oprita"""
		w = self["pagina"].instance
		if w is None:
			return
		self._trad_rez = rez
		cu_nucleu = hasattr(w, "setTraducere")
		if mod == "pagina" and not cu_nucleu:
			mod = "panou"            # nucleu vechi: traducerea numai in panou
		M = _traducereTeletext()
		tradus = rez is not None and M is not None and rez.fel == M.FEL_TRADUS and not original
		if cu_nucleu:
			if mod == "pagina" and tradus:
				if self._trad_pus is not rez:
					w.setTraducere(self.numar, rez.amprenta, rez.litere, rez.culori)
					self._trad_pus = rez
			elif self._trad_pus is not None:
				w.stergeTraducere()
				self._trad_pus = None
		self._potrivestePagina(mod == "panou" and not original)
		if mod is None:
			self._arataDialog(None, None, None)
			return
		indiciu = self._textStare(rez, original)
		indiciu += u"\n" + (_("AUDIO: traducerea") if original else _("AUDIO: originalul"))
		if mod == "panou" and not original:
			if tradus:
				panou = u"\n".join(rez.panou)
			else:
				panou = self._textStare(rez, original)
			self._arataDialog("panou", panou, indiciu)
		else:
			self._arataDialog("pagina", None, indiciu)

	def _textStare(self, rez, original):
		M = _traducereTeletext()
		if original:
			return _("Pagina în original")
		if rez is None or M is None:
			return (_("Pagina %d se caută") % self.numar) if not self.gasita else _("Se traduce pagina…")
		if rez.fel == M.FEL_TRADUS:
			return _("Pagina tradusă")
		if rez.fel == M.FEL_LUCRU:
			return _("Se traduce pagina…")
		if rez.fel == M.FEL_DEJA:
			return _("Pagina e deja în limba ta")
		if rez.fel == M.FEL_GOL:
			return _("Pagina nu are text de tradus")
		return _("Traducerea nu are un serviciu gata: Meniu, Traducerea subtitrărilor")

	def _potrivestePagina(self, cu_panou):
		"""pagina pe tot ecranul sau micsorata in stanga, langa panou"""
		if cu_panou == self._trad_panou:
			return
		self._trad_panou = cu_panou
		w = self["pagina"].instance
		desktop = getDesktop(0).size()
		latime = desktop.width() * LATIME_CU_PANOU // 100 if cu_panou else desktop.width()
		w.resize(eSize(latime, desktop.height()))
		# mesajele raman in mijlocul paginii (nu sub panou)
		l = self["mesaj"].instance
		if l is not None:
			if self.mesaj_loc is None:
				self.mesaj_loc = (l.position(), l.size())
			poz, mar = self.mesaj_loc
			if self._mesaj_x is None:
				self._mesaj_x = poz.x()
			x = (latime - mar.width()) // 2 if cu_panou else self._mesaj_x
			self.mesaj_loc = (ePoint(x, poz.y()), mar)
			self.potrivesteMesajul()

	def _arataDialog(self, fel, panou, indiciu):
		"""fel: "panou" (panoul in dreapta, indiciul sub el), "pagina" (numai indiciul, langa pagina) sau None"""
		d = self._trad_dialog
		if d is None or d.instance is None:
			return
		if fel is None:
			if self._trad_vazut is not None:
				d.hide()
				self._trad_vazut = None
			return
		desktop = getDesktop(0).size()
		W, H = desktop.width(), desktop.height()
		w = self["pagina"].instance
		if fel == "panou":
			x = W * LATIME_CU_PANOU // 100 + W // 96
			y = H // 18
			loc = (x, y, W - x - W // 48, H - 2 * y)
		else:
			dreapta = w.paginaX() + w.paginaLatime()
			lat = max(W - dreapta - W // 48, W // 8)
			x = min(W - lat - W // 96, dreapta + W // 96)
			loc = (x, H - H // 6 - H // 36, lat, H // 6)
		vazut = (fel, loc, panou, indiciu)
		if vazut == self._trad_vazut:
			return
		x, y, lat, ina = loc
		ina_indiciu = H // 10 if fel == "panou" else ina
		cheie_geom = (fel, loc)
		if self._trad_vazut is None or self._trad_vazut[:2] != cheie_geom:
			d.instance.move(ePoint(x, y))
			d.instance.resize(eSize(lat, ina))
			p, i = d["panou"].instance, d["indiciu"].instance
			if fel == "panou":
				p.move(ePoint(0, 0))
				p.resize(eSize(lat, ina - ina_indiciu - H // 90))
				d["panou"].show()
			else:
				d["panou"].hide()
			i.move(ePoint(0, ina - ina_indiciu))
			i.resize(eSize(lat, ina_indiciu))
			# indiciul urmeaza Marimea textului (Components/HdsMarireText); panoul de deasupra isi alege singur litera
			# cea mai mare care incape (_scriePanou), neschimbat
			from Components import HdsMarireText as MT
			i.setFont(MT.fontCod(_fontHds("Regular"), max(14, H * (24 if fel == "panou" else 22) // 1080)))
		d["indiciu"].setText(indiciu or u"")
		if fel == "panou":
			self._scriePanou(d, panou or u"", ina - ina_indiciu - H // 90)
		self._trad_vazut = vazut
		if self.shown:
			d.show()

	def _laAscundere(self):
		if self._trad_dialog is not None and self._trad_vazut is not None:
			self._trad_dialog.hide()

	def _laAratare(self):
		if self._trad_dialog is not None and self._trad_vazut is not None:
			self._trad_dialog.show()

	def _scriePanou(self, d, text, inaltime):
		"""textul panoului, cu litera cea mai mare la care incape (de la 30 in jos, la 1080 de randuri)"""
		from enigma import gFont
		p = d["panou"].instance
		H = getDesktop(0).size().height()
		d["panou"].setText(text)
		familie = _fontHds("Regular")
		for marime in (30, 28, 26, 24, 22, 20, 18):
			p.setFont(gFont(familie, max(12, H * marime // 1080)))
			try:
				if p.calculateSize().height() <= inaltime:
					break
			except Exception:
				break

	def schimbaTraducerea(self):
		"""AUDIO: pagina de acum in original sau tradusa"""
		if _modTraducere() is None:
			self.anunta(_("Traducerea teletextului e oprită. O pornești din MENU."))
			return
		self.tradus_original = not self.tradus_original
		self.traducePagina()
		self.anunta(_("Pagina în original. AUDIO: traducerea.") if self.tradus_original else
			_("Pagina tradusă. AUDIO: originalul."))

	def schimbaSetareaTraducerii(self, nume):
		"""din MENU: "teletext" (pornita / oprita) sau "teletext_mod" (in pagina / in panou), scrise pe loc"""
		s = _setariTraducere()
		if s is None:
			return
		try:
			if nume == "teletext":
				s.teletext.value = not s.teletext.value
				_salveaza(s.teletext)
				self.anunta(_("Traducerea teletextului pornită") if s.teletext.value else _("Traducerea teletextului oprită"))
			else:
				s.teletext_mod.value = "pagina" if s.teletext_mod.value == "panou" else "panou"
				_salveaza(s.teletext_mod)
				self.anunta(_("Traducerea într-un panou") if s.teletext_mod.value == "panou" else _("Traducerea în pagină"))
		except Exception as e:
			print("[HdsTeletext] setarea traducerii:", e)
		self.tradus_original = False
		self.traducePagina()

	def schimbaFaza(self):
		w = self["pagina"].instance
		if w is not None and w.areIntermitente():
			self.faza ^= 1
			w.setFaza(self.faza)

	def mesajPagina(self):
		if self.mesaj_temporar:
			text = self.mesaj_temporar
		elif not T.are_teletext(self.nucleu):
			text = _("Canalul acesta nu are teletext.")
		elif not self.gasita and not self.tastare.in_curs:
			if self.nucleu is not None:
				text = _("Pagina %d nu e în copie") % self.numar
			else:
				text = _("Pagina %d se caută") % self.numar
		else:
			text = ""
		if self["mesaj"].getText() != text:
			self["mesaj"].setText(text)
			self.potrivesteMesajul()
		if text:
			self["mesaj"].show()
		else:
			self["mesaj"].hide()

	def potrivesteMesajul(self):
		"""Caseta mesajului din skin are loc de doua randuri; un mesaj lung (motivul unei reimprospatari esuate) o
		inalta cat ii trebuie (cel mult de 4 ori), ramanand centrata; un mesaj scurt o aduce inapoi."""
		l = self["mesaj"].instance
		if l is None:
			return
		if self.mesaj_loc is None:
			self.mesaj_loc = (l.position(), l.size())
		poz, mar = self.mesaj_loc
		try:
			l.resize(mar)
			nevoie = l.calculateSize().height() + 24
		except Exception:
			return
		h = max(mar.height(), min(nevoie, 4 * mar.height()))
		if h != mar.height():
			l.resize(eSize(mar.width(), h))
		l.move(ePoint(poz.x(), poz.y() - (h - mar.height()) // 2))

	def anunta(self, text, ms=MESAJ_MS):
		self.mesaj_temporar = text
		self.ceas_mesaj.start(ms, True)
		self.mesajPagina()

	def mesajExpirat(self):
		self.mesaj_temporar = ""
		self.mesajPagina()

	def mergiLa(self, numar):
		numar = T.normalizeaza(numar)
		if numar is None:
			return
		self.tastare.sterge()
		if numar != self.numar:
			self.tradus_original = False     # alta pagina: iar tradusa
			self._trad_pus = None             # nucleul uita traducerea paginii de dinainte (setPagina)
		self.numar = numar
		self.subcod = -1
		self.tinut = False
		self.aratPagina()

	# ---------------------------------------------------------------- tastele

	def cifra(self, cifra):
		numar = self.tastare.apasa(cifra)
		if numar is not None:
			self.mergiLa(numar)
		else:
			self.aratPagina()

	def pas(self, directie):
		self.mergiLa(T.vecina(self.numar, directie, T.pagini_existente(self.nucleu)))

	def culoare(self, index):
		w = self["pagina"].instance
		subcod = w.subcodAratat() if w is not None else -1
		tinta = T.taste_colorate(self.numar, subcod, self.nucleu, initiala=self.initiala)["tinte"][index]
		if tinta:
			self.mergiLa(tinta)

	def subpagina(self, directie):
		toate = T.subpagini(self.numar, self.nucleu)
		if len(toate) < 2:
			return
		w = self["pagina"].instance
		acum = w.subcodAratat() if w is not None else -1
		k = toate.index(acum) if acum in toate else 0
		self.subcod = toate[(k + directie) % len(toate)]
		self.tinut = True
		self.aratPagina()
		self.anunta(_("Subpagina %d din %d, ținută") % (toate.index(self.subcod) + 1, len(toate)))

	def tine(self):
		toate = T.subpagini(self.numar, self.nucleu)
		if self.tinut:
			self.tinut = False
			self.subcod = -1
			self.aratPagina()
			self.anunta(_("Subpaginile merg singure"))
			return
		w = self["pagina"].instance
		acum = w.subcodAratat() if w is not None else -1
		if acum < 0:
			return
		self.subcod = acum
		self.tinut = True
		self.aratPagina()
		if len(toate) > 1 and acum in toate:
			self.anunta(_("Subpagina %d din %d, ținută") % (toate.index(acum) + 1, len(toate)))
		else:
			self.anunta(_("Pagina ținută"))

	def schimbaAscuns(self):
		self.ascuns = not self.ascuns
		w = self["pagina"].instance
		if w is not None:
			w.setArataAscuns(1 if self.ascuns else 0)
		self.anunta(_("Se vede ce era ascuns") if self.ascuns else _("Ce era ascuns nu se mai vede"))

	def schimbaMod(self):
		w = self["pagina"].instance
		peste = 0 if (w is not None and w.getPeste()) else 1
		if w is not None:
			w.setPeste(peste)
		s = _setari()
		if s is not None:
			s.peste.value = bool(peste)
			_salveaza(s.peste)
		self.anunta(_("Teletextul peste imagine") if peste else _("Teletextul pe tot ecranul"))

	def schimbaHd(self):
		w = self["pagina"].instance
		hd = 0 if (w is not None and w.getHd()) else 1
		if w is not None:
			w.setHd(hd)
		s = _setari()
		if s is not None:
			s.hd.value = bool(hd)
			_salveaza(s.hd)
		self.anunta(_("Teletext neted") if hd else _("Teletext clasic"))

	def schimbaOptiune(self, nume):
		"""Conturul, umbra sau relieful: pornit / oprit, scris pe loc in setari si aratat pe pagina."""
		s = _setari()
		pornit = not _valoare(s, nume)
		if s is not None:
			getattr(s, nume).value = pornit
			_salveaza(getattr(s, nume))
		w = self["pagina"].instance
		if w is not None:
			getattr(w, "set" + nume.capitalize())(1 if pornit else 0)
		self.anunta({
			"contur": (_("Conturul literelor pornit"), _("Conturul literelor oprit")),
			"umbra": (_("Umbra literelor pornită"), _("Umbra literelor oprită")),
			"relief": (_("Formele în relief pornite"), _("Formele în relief oprite")),
		}[nume][0 if pornit else 1])

	# ---------------------------------------------------------------- MENU: clasic sau neted, optiunile, copiile

	def meniu(self):
		from Screens.ChoiceBox import ChoiceBox
		w = self["pagina"].instance
		hd = w is not None and w.getHd()
		s = _setari()
		automata = s is None or s.copie_automata.value
		lista = [(_("Teletext clasic") if hd else _("Teletext neted"), "hd")]
		lista.append((_("Contur litere: oprește") if _valoare(s, "contur") else _("Contur litere: pornește"), "contur"))
		lista.append((_("Umbra literelor: oprește") if _valoare(s, "umbra") else _("Umbra literelor: pornește"), "umbra"))
		if hd:
			# formele in relief se vad numai la teletextul neted
			lista.append((_("Forme în relief: oprește") if _valoare(s, "relief") else _("Forme în relief: pornește"),
				"relief"))
		mod_tr = _modTraducere()
		lista.append((_("Tradu teletextul: oprește") if mod_tr else _("Tradu teletextul: pornește"), "traducere"))
		if mod_tr:
			lista.append((_("Traducerea într-un panou") if mod_tr == "pagina" else _("Traducerea în pagină"),
				"traducere_mod"))
			lista.append((_("Pagina în original (AUDIO)") if not self.tradus_original else
				_("Pagina tradusă (AUDIO)"), "traducere_original"))
		if self.nucleu is not None:
			lista.append((_("Teletextul canalului de acum"), "direct"))
		lista.append((_("Copiile de teletext"), "copii"))
		if self.nucleu is None and T.are_teletext():
			lista.append((_("Salvează acum copia canalului"), "salveaza"))
		if self.copie is not None:
			lista.append((_("Reîmprospătează copia (zap pe canal, apoi înapoi)"), "reimprospateaza"))
		lista.append((_("Copia automată: oprește") if automata else _("Copia automată: pornește"), "automata"))
		self.session.openWithCallback(self.meniuAles, ChoiceBox, title=_("Teletext"), list=lista)

	def meniuAles(self, ales):
		if not ales:
			return
		fel = ales[1]
		if fel == "hd":
			self.schimbaHd()
		elif fel in ("contur", "umbra", "relief"):
			self.schimbaOptiune(fel)
		elif fel == "traducere":
			self.schimbaSetareaTraducerii("teletext")
		elif fel == "traducere_mod":
			self.schimbaSetareaTraducerii("teletext_mod")
		elif fel == "traducere_original":
			self.schimbaTraducerea()
		elif fel == "direct":
			self.sursa(None)
		elif fel == "copii":
			self.alegeCopie()
		elif fel == "salveaza":
			self.salveazaAcum()
		elif fel == "reimprospateaza":
			self.reimprospateaza()
		elif fel == "automata":
			s = _setari()
			if s is not None:
				s.copie_automata.value = not s.copie_automata.value
				_salveaza(s.copie_automata)
				self.anunta(_("Copia automată pornită") if s.copie_automata.value else _("Copia automată oprită"))

	def alegeCopie(self):
		from Screens.ChoiceBox import ChoiceBox
		lista = lista_copii()
		if not lista:
			self.anunta(_("Nu ai încă nicio copie de teletext."))
			return
		self.session.openWithCallback(self.copieAleasa, ChoiceBox, title=_("Copiile de teletext"), list=lista)

	def copieAleasa(self, ales):
		if ales:
			self.sursa(ales[1])

	def sursa(self, ref):
		"""Paginile din copia canalului `ref`, sau din canalul care merge (ref None)."""
		w = self["pagina"].instance
		if ref:
			info = C.incarca(ref, LOC_COPIE)
			if info is None:
				self.anunta(_("Copia nu se poate citi."))
				return
			self.copie = info
			self.nucleu = eHdsTeletext.copie(LOC_COPIE)
		else:
			self.copie = None
			self.nucleu = None
		if w is not None:
			w.setSursa(LOC_COPIE if self.nucleu is not None else -1)
		self.tradus_original = False
		self._trad_pus = None
		self.initiala = T.stare(self.nucleu)["initiala"]
		self.mergiLa(self.initiala)
		if self.copie is not None:
			self.anunta(_("Copia din %s") % C.data_text(self.copie.get("data")))
		else:
			self.anunta(_("Teletextul canalului de acum"))

	def salveazaAcum(self):
		u = C.urmaritor()
		ref, nume = (u._ref_acum() if u is not None else (None, ""))
		rez = C.salveaza(ref, nume) if ref and C.ref_salvabila(ref) else None
		if rez is None:
			self.anunta(_("Copia nu s-a putut salva."))
		else:
			self.anunta(_("Copia s-a salvat: %d de pagini") % rez["pagini"])

	def reimprospateaza(self):
		u = C.urmaritor()
		if u is None or self.copie is None:
			return
		ref = self.copie["ref"]
		if u.reimprospateaza(ref, self.reimprospatat):
			self.anunta(_("Se reîmprospătează copia: zap pe canal, o trecere a teletextului, apoi înapoi."))

	def reimprospatat(self, rez):
		if rez.get("ok"):
			self.sursa(rez["ref"])
			self.anunta(_("Copia e la zi"))
		elif rez.get("motiv") == C.MOTIV_INREGISTRARE:
			self.anunta(_("Acum se înregistrează, deci canalul nu se schimbă. Încearcă după înregistrare."))
		else:
			# ce s-a intamplat si cate pagini s-au strans (C.text_rezultat), altfel textul general
			self.anunta(C.text_rezultat(rez, _) or _("Copia nu s-a putut reîmprospăta."), MESAJ_LUNG_MS)

	def iesire(self):
		if self.tastare.in_curs:
			self.tastare.sterge()
			self.aratPagina()
			return
		self.close()


def lista_copii():
	"""Copiile pentru o lista de alegere: [(text, ref)]."""
	return [("%s  %s  (%d)" % (c.get("nume") or c["ref"], C.data_text(c.get("data")), c.get("pagini", 0)), c["ref"])
		for c in C.copii()]


def deschide(session):
	"""TEXT pe bara: deschide vizualizatorul. Pe un canal fara teletext, copiile salvate (daca sunt) sau un mesaj
	scurt. Fals = nucleul nu are teletextul (o imagine veche): bara spune mesajul ei de dinainte."""
	if not T.disponibil():
		return False
	if T.are_teletext():
		session.open(HdsTeletext)
		return True
	lista = lista_copii()
	if lista:
		from Screens.ChoiceBox import ChoiceBox

		def ales(rez):
			if rez:
				session.open(HdsTeletext, copie=rez[1])

		session.openWithCallback(ales, ChoiceBox, title=_("Canalul acesta nu are teletext. Alege o copie salvată:"),
			list=lista)
		return True
	from Screens.MessageBox import MessageBox
	session.open(MessageBox, _("Canalul acesta nu are teletext."), MessageBox.TYPE_INFO, timeout=4)
	return True
