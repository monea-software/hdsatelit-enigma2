# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsImagineOnline: fereastra scurta pentru o versiune noua. Apare singura pe ecranul obisnuit (Components/HdsImagineOnline,
# Verificare) sau din Meniu > Setari > Software, cu aceeasi logica ca pagina web /imagine-online. Spune versiunile cu datele
# lor si are doua taste: VERDE (sau OK) „Da, actualizează”, ROSU „Nu acum”. O singura apasare: restul e al receptorului,
# iar fereastra arata numai unde a ajuns. In timpul lucrului ROSU opreste (fisierul inceput ramane pe stick), EXIT numai
# inchide fereastra. Fara stick spune o singura fraza si ramane deschisa, ca omul sa apese din nou. Din meniu, ALBASTRU
# schimba ce se pune singur in standby, iar GALBEN, cand un plugin a dat imagini ale altor echipe, deschide lista lor
# (HdsImagineOnlineStraine): fiecare cu starea „Neverificată”, iar la OK avertismentul, cu „Nu” ales. Skinul e scris aici, ca
# sa arate la fel in orice tema.

from enigma import eTimer, getDesktop
from Components.ActionMap import ActionMap
from Components.Button import Button
from Components.Label import Label
from Components.MenuList import MenuList
from Screens.Screen import Screen

try:
	from Components import HdsImagineOnline as IO
except ImportError:  # in pachetul-punte, modulul sta langa acest fisier
	from . import HdsImagineOnline as IO

PAUZA_TASTE_MS = 1500
REIMPROSPATARE_MS = 500
T_TITLU = "Imagine nouă de pe internet"


def skinFereastra(latime, inaltime):
	def x(v):
		return int(round(v * latime / 1920.0))

	def y(v):
		return int(round(v * inaltime / 1080.0))
	valori = {"fl": x(1200), "fh": y(500), "m": x(40), "cl": x(1120), "ty": y(30), "th": y(190), "py": y(228), "ph": y(172),
		"f": y(34), "fp": y(28), "by": y(410), "bl": x(265), "bh": y(56), "bf": y(26), "b2": x(325), "b3": x(610), "b4": x(895)}
	return """
	<screen name="HdsImagineOnline" position="center,center" size="%(fl)d,%(fh)d" title="Imagine nouă de pe internet">
		<widget name="text" position="%(m)d,%(ty)d" size="%(cl)d,%(th)d" font="Regular;%(f)d" halign="left" valign="top" />
		<widget name="pas" position="%(m)d,%(py)d" size="%(cl)d,%(ph)d" font="Regular;%(fp)d" halign="left" valign="top" />
		<widget name="key_green" position="%(m)d,%(by)d" size="%(bl)d,%(bh)d" zPosition="1" font="Regular;%(bf)d" halign="center" valign="center" backgroundColor="#1f771f" transparent="0" />
		<widget name="key_red" position="%(b2)d,%(by)d" size="%(bl)d,%(bh)d" zPosition="1" font="Regular;%(bf)d" halign="center" valign="center" backgroundColor="#9f1313" transparent="0" />
		<widget name="key_yellow" position="%(b3)d,%(by)d" size="%(bl)d,%(bh)d" zPosition="1" font="Regular;%(bf)d" halign="center" valign="center" backgroundColor="#a08000" transparent="0" />
		<widget name="key_blue" position="%(b4)d,%(by)d" size="%(bl)d,%(bh)d" zPosition="1" font="Regular;%(bf)d" halign="center" valign="center" backgroundColor="#16427a" transparent="0" />
	</screen>
	""" % valori


class HdsImagineOnline(Screen):
	def __init__(self, session, oferta=None):
		try:
			marime = getDesktop(0).size()
			self.skin = skinFereastra(marime.width(), marime.height())
		except Exception:
			self.skin = skinFereastra(1920, 1080)
		Screen.__init__(self, session)
		self.setTitle(_(T_TITLU))
		self.io = IO.imagine_online
		self._inchis = False
		self.io.session = session
		self.oferta = oferta
		self.din_meniu = oferta is None
		self.mesaj = ""
		self.lucrez_feed = False
		self.taste_oprite = not self.din_meniu
		self["text"] = Label("")
		self["pas"] = Label("")
		self["key_green"] = Button("")
		self["key_red"] = Button("")
		self["key_yellow"] = Button("")
		self["key_blue"] = Button("")
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions"], {
			"ok": self.da,
			"green": self.da,
			"red": self.nu,
			"yellow": self.straine,
			"blue": self.standby,
			"cancel": self.close,
		}, -2)
		self.ceas = eTimer()
		self.ceas_taste = eTimer()
		try:
			self._l1 = self.ceas.timeout.connect(self._arata)
			self._l2 = self.ceas_taste.timeout.connect(self._porneste_tastele)
		except AttributeError:
			self.ceas.callback.append(self._arata)
			self.ceas_taste.callback.append(self._porneste_tastele)
		self.onLayoutFinish.append(self._prima)
		self.onClose.append(self._inchide)

	def _inchide(self):
		self._inchis = True
		self.ceas.stop()
		self.ceas_taste.stop()

	def _prima(self):
		if self.taste_oprite:
			# fereastra apare singura: o tasta apasata chiar atunci, pentru altceva, nu porneste nimic
			self.ceas_taste.start(PAUZA_TASTE_MS, True)
		if self.din_meniu and not self.io.ocupat():
			self.io.cauta(self._dupa_cautare)
		self.ceas.start(REIMPROSPATARE_MS, False)
		self._arata()

	def _porneste_tastele(self):
		if getattr(self, "_inchis", True):
			return
		self.taste_oprite = False

	def _dupa_cautare(self):
		if getattr(self, "_inchis", True):
			return
		self.oferta = self.io.oferta
		self._arata()

	def _buton(self, nume, text):
		self[nume].setText(text)
		if text:
			self[nume].show()
		else:
			self[nume].hide()

	def _loc_strain(self):
		o = self.oferta
		return bool(o) and o.get("fel") == "imagine" and not IO.citeste_tinta().get("bun")

	def _text_stare(self):
		r = self.io.rezultat
		return _({IO.LA_ZI: IO.T_LA_ZI, IO.FARA_RETEA: IO.T_FARA_RETEA, IO.FARA_RASPUNS: IO.T_FARA_SERVER,
			IO.NESEMNATA: IO.T_NESEMNATA, IO.EROARE: IO.T_FARA_SERVER}.get(r, IO.P_CAUT))

	def _arata(self):
		if getattr(self, "_inchis", True):
			return
		io = self.io
		if self.din_meniu and not self.oferta and io.faza == "liber":
			self.oferta = io.oferta
		if self.lucrez_feed:
			return self._arata_feed()
		text, pas, verde, rosu = "", "", "", ""
		o = self.oferta
		if io.faza == "scriu":
			text = io.pas
		elif io.faza in ("lucrez", "astept"):
			text = io.text_lucrare(o)
			pas, rosu = io.pas, _("Oprește")
		elif io.faza == "caut":
			text = io.pas
		elif self.din_meniu and not o:
			text = self._text_stare()
			pas = io.mesaj
			rosu = _("Close")
		elif o:
			if self._loc_strain():
				text = _(IO.T_LOC_STRAIN)
				rosu = _("Close")
			else:
				text = io.text_oferta(o)
				pas = self.mesaj or io.mesaj
				verde, rosu = _(IO.T_DA), _(IO.T_NU)
		else:
			text = self._text_stare()
			rosu = _("Close")
		meniu = self.din_meniu and io.faza == "liber"
		self._buton("key_yellow", _(IO.T_ALTE) if meniu and IO.imagini_straine() else "")
		if meniu and not pas:
			pas = self._text_standby()
		self["text"].setText(text)
		self["pas"].setText(pas)
		self._buton("key_green", verde)
		self._buton("key_red", rosu)
		self._buton("key_blue", _("Schimbă") if meniu else "")

	def _arata_feed(self):
		A = IO._modul("HdsActualizari").actualizari
		self["pas"].setText(A.pas or A.mesaj or "")
		self._buton("key_green", "")
		self._buton("key_red", _("Close") if not A.rapid else "")
		self._buton("key_yellow", "")
		self._buton("key_blue", "")

	def _text_standby(self):
		v = IO.config_imagine().standby.value
		return "%s: %s" % (_(IO.T_STANDBY), _(dict(IO.VALORI_STANDBY).get(v, "")))

	def da(self):
		if self.taste_oprite or self.lucrez_feed or self.io.ocupat() or not self.oferta or self._loc_strain():
			return
		if self.oferta.get("fel") == "feed":
			if IO.porneste_feed(self.session):
				self.lucrez_feed = True
			else:
				self.mesaj = _("Așteaptă să se termine operația de acum.")
			return self._arata()
		self.mesaj = ""
		if IO.semn_oferta(self.oferta) != IO.semn_oferta(self.io.oferta):
			self.oferta = self.io.oferta
			return self._arata()
		self.io.porneste(versiune=self.oferta.get("versiune"), oferta=IO.semn_oferta(self.oferta))
		self._arata()

	def nu(self):
		if self.taste_oprite:
			return
		if self.io.faza in ("lucrez", "astept"):
			self.io.opreste()
			return self._arata()
		if self.io.faza == "scriu":
			return
		self.close()

	def straine(self):
		if self.din_meniu and self.io.faza == "liber" and IO.imagini_straine():
			self.session.open(HdsImagineOnlineStraine)

	def standby(self):
		if not self.din_meniu or self.io.faza != "liber":
			return
		valori = [v for v, _t in IO.VALORI_STANDBY]
		acum = IO.config_imagine().standby.value
		IO.seteaza_standby(valori[(valori.index(acum) + 1) % len(valori)] if acum in valori else valori[0])
		self._arata()


def skinStraine(latime, inaltime):
	def x(v):
		return int(round(v * latime / 1920.0))

	def y(v):
		return int(round(v * inaltime / 1080.0))
	valori = {"fl": x(1200), "fh": y(700), "m": x(40), "cl": x(1120), "ly": y(25), "lh": y(490), "ih": y(56), "f": y(30), "ny": y(525),
		"nh": y(80), "fn": y(24), "by": y(620), "bl": x(265), "bh": y(56), "bf": y(26), "b2": x(325)}
	return """
	<screen name="HdsImagineOnlineStraine" position="center,center" size="%(fl)d,%(fh)d" title="Alte imagini">
		<widget name="lista" position="%(m)d,%(ly)d" size="%(cl)d,%(lh)d" font="Regular;%(f)d" itemHeight="%(ih)d" scrollbarMode="showOnDemand" />
		<widget name="nota" position="%(m)d,%(ny)d" size="%(cl)d,%(nh)d" font="Regular;%(fn)d" halign="left" valign="top" />
		<widget name="key_green" position="%(m)d,%(by)d" size="%(bl)d,%(bh)d" zPosition="1" font="Regular;%(bf)d" halign="center" valign="center" backgroundColor="#1f771f" transparent="0" />
		<widget name="key_red" position="%(b2)d,%(by)d" size="%(bl)d,%(bh)d" zPosition="1" font="Regular;%(bf)d" halign="center" valign="center" backgroundColor="#9f1313" transparent="0" />
	</screen>
	""" % valori


class HdsImagineOnlineStraine(Screen):
	"""Imaginile date de pluginuri (Components/HdsImagineOnline.inregistreaza_imagini), pe sectiuni, fiecare cu starea ei. OK sau
	VERDE: avertismentul, cu „Nu” ales; la Da porneste lucrarea, iar fereastra de dedesubt arata unde a ajuns."""

	def __init__(self, session):
		try:
			marime = getDesktop(0).size()
			self.skin = skinStraine(marime.width(), marime.height())
		except Exception:
			self.skin = skinStraine(1920, 1080)
		Screen.__init__(self, session)
		self.setTitle(_(IO.T_ALTE))
		self.io = IO.imagine_online
		self.randuri = []
		randuri, sectiune = [], None
		for x in IO.imagini_straine():
			if x["sectiune"] != sectiune:
				sectiune = x["sectiune"]
				randuri.append(sectiune)
				self.randuri.append(None)
			randuri.append("   %s  ·  %s" % (_(IO.T_NEVERIFICATA), IO.numele_strainei(x)))
			self.randuri.append(x)
		self["lista"] = MenuList(randuri)
		self["nota"] = Label("")
		self["key_green"] = Button(_(IO.T_INSTALEAZA))
		self["key_red"] = Button(_("Close"))
		self.onLayoutFinish.append(self._prima)
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions"], {
			"ok": self.alege,
			"green": self.alege,
			"red": self.close,
			"cancel": self.close,
		}, -2)

	def _prima(self):
		# primul rand e titlul sectiunii
		self["lista"].moveToIndex(1)

	def alege(self):
		i = self["lista"].getSelectionIndex()
		x = self.randuri[i] if 0 <= i < len(self.randuri) else None
		if x is None:
			return
		from Screens.HdsPazaModel import HdsPazaModelIntrebare
		self.session.openWithCallback(lambda raspuns, ales=dict(x): self._dupa_avertisment(raspuns, ales),
			HdsPazaModelIntrebare, IO.text_avertisment_strain(x),
			_(IO.T_STRAINA_TITLU), da=_(IO.T_STRAINA_DA), implicit_da=False, randuri_mesaj=9, randuri_tehnic=3)

	def _dupa_avertisment(self, raspuns, ales):
		if not raspuns or not getattr(self, "io", None):
			return
		if self.io.porneste_straina(ales["id"], confirmat=True):
			return self.close()
		self["nota"].setText(self.io.mesaj)
