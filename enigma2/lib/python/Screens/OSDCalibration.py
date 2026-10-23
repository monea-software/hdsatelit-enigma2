# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# OSDCalibration: "Marginile ecranului" (overscan). Pe tot ecranul: cadrul de proba (patru linii groase, latura aleasa
# in chihlimbar), zona in care stau ferestrele meniului (linie subtire) si, la mijloc, fereastra cu latura aleasa,
# marginile, ajutorul si tastele. OK alege latura (toate, sus, dreapta, jos, stanga), sagetile o muta, Verde salveaza,
# Galben pune marginile din fabrica (0), Rosu renunta si pune inapoi ce era.
# Logica (marginile, limitele, scrierea in driver) e in Components/HdsMargini.py, aceeasi cu pagina web /margini-ecran.
# Cand receptorul are driverul (/proc/stb/fb/dst_apply), afisajul se micsoreaza pe loc si cadrul se deseneaza la
# marginea ecranului (il muta driverul); fara driver (alte receptoare, emulatorul) cadrul se deseneaza intre margini,
# ca sa se vada unde ar ajunge.
#
# Skinul: HdsMarginiEcran din skin.xml; pe alt skin, rezerva de mai jos, scrisa pe 1280 si scalata la ecran.

from enigma import ePoint, eSize, gRGB, getDesktop

from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components import HdsMargini as M
from Tools.ScaledSkin import scaledSkin


def initConfigOSDCalibration():
	M.initConfig()


def aplicaCalibrarea():
	"""Marginile salvate, scrise in driver (daca receptorul il are)."""
	latime, inaltime = M.marimeEcran()
	return M.aplica(M.citeste(latime, inaltime), latime, inaltime)


def InitOSDCalibration():
	"""Chemata o data la pornire, din mytest.py: pune marginile salvate; cu toate 0 nu scrie nimic."""
	M.initConfig()
	latime, inaltime = M.marimeEcran()
	M.aplica(M.citeste(latime, inaltime), latime, inaltime, la_pornire=True)


# Rezerva pe 1280 (cotele de 1920 x 2/3), culorile skinului HDSatelit scrise ca numere.
SKIN_REZERVA = """
<screen name="HdsMarginiEcran" position="0,0" size="1280,720" backgroundColor="#0010162A" flags="wfNoBorder" title="Marginile ecranului">
	<eLabel position="48,27" size="1184,1" backgroundColor="#009FB4FF" zPosition="1" />
	<eLabel position="48,692" size="1184,1" backgroundColor="#009FB4FF" zPosition="1" />
	<eLabel position="48,27" size="1,666" backgroundColor="#009FB4FF" zPosition="1" />
	<eLabel position="1231,27" size="1,666" backgroundColor="#009FB4FF" zPosition="1" />
	<widget name="zona_text" position="59,32" size="533,24" font="Regular;16" foregroundColor="#009FB4FF" backgroundColor="#0010162A" transparent="1" valign="center" noWrap="1" zPosition="1" />
	<widget name="linie_sus" position="0,0" size="1280,4" backgroundColor="#00F2F4F8" zPosition="3" />
	<widget name="linie_dreapta" position="1276,0" size="4,720" backgroundColor="#00F2F4F8" zPosition="3" />
	<widget name="linie_jos" position="0,716" size="1280,4" backgroundColor="#00F2F4F8" zPosition="3" />
	<widget name="linie_stanga" position="0,0" size="4,720" backgroundColor="#00F2F4F8" zPosition="3" />
	<eLabel position="273,147" size="734,427" backgroundColor="#00282D3F" zPosition="2" />
	<eLabel position="273,147" size="734,1" backgroundColor="#99FFFFFF" zPosition="3" />
	<widget source="Title" render="Label" position="295,157" size="691,37" font="Bold;24" foregroundColor="#00F2F4F8" backgroundColor="#00282D3F" transparent="1" valign="center" noWrap="1" zPosition="3" />
	<eLabel position="295,200" size="691,1" backgroundColor="#D9FFFFFF" zPosition="3" />
	<widget name="latura" position="295,211" size="691,32" font="Bold;21" foregroundColor="#00F5B83D" backgroundColor="#00282D3F" transparent="1" valign="center" noWrap="1" zPosition="3" />
	<widget name="valori" position="295,245" size="691,29" font="Regular;19" foregroundColor="#00F2F4F8" backgroundColor="#00282D3F" transparent="1" valign="center" noWrap="1" zPosition="3" />
	<widget name="ajutor" position="295,280" size="691,176" font="Regular;19" foregroundColor="#00C9D2E3" backgroundColor="#00282D3F" transparent="1" zPosition="3" />
	<widget name="stare" position="295,461" size="691,27" font="Regular;16" foregroundColor="#00AEB9CC" backgroundColor="#00282D3F" transparent="1" valign="center" noWrap="1" zPosition="3" />
	<eLabel position="295,496" size="691,1" backgroundColor="#D9FFFFFF" zPosition="3" />
	<eLabel position="295,515" size="4,21" backgroundColor="#00E5484D" zPosition="3" />
	<widget name="key_red" position="305,509" size="213,32" font="Regular;19" foregroundColor="#00F2F4F8" backgroundColor="#00282D3F" transparent="1" valign="center" noWrap="1" zPosition="3" />
	<eLabel position="529,515" size="4,21" backgroundColor="#0046B06A" zPosition="3" />
	<widget name="key_green" position="540,509" size="213,32" font="Regular;19" foregroundColor="#00F2F4F8" backgroundColor="#00282D3F" transparent="1" valign="center" noWrap="1" zPosition="3" />
	<eLabel position="764,515" size="4,21" backgroundColor="#00E8B93A" zPosition="3" />
	<widget name="key_yellow" position="775,509" size="213,32" font="Regular;19" foregroundColor="#00F2F4F8" backgroundColor="#00282D3F" transparent="1" valign="center" noWrap="1" zPosition="3" />
</screen>"""

# culorile cadrului: din skinul HDSatelit, altfel aceleasi ca numere (0xRRGGBB, opac)
CULOARE_ALEASA = ("hdsAmber", 0xF5B83D)
CULOARE_LATURA = ("hdsText", 0xF2F4F8)
GROSIME = 6      # la 1920


def _culoare(nume, implicit):
	try:
		import skin
		c = skin.colorNames.get(nume)
		if c is not None:
			return c
	except Exception:
		pass
	return gRGB(implicit)


class OSDCalibration(Screen):
	"""Marginile ecranului: OK alege latura, sagetile o muta, Verde salveaza, Galben = din fabrica, Rosu renunta."""

	def __init__(self, session):
		self.skin = scaledSkin(SKIN_REZERVA)
		Screen.__init__(self, session)
		self.skinName = ["HdsMarginiEcran"]
		self.setTitle(_("Screen Margins / Overscan"))
		self.latime, self.inaltime = M.marimeEcran()
		self.inainte = M.citeste(self.latime, self.inaltime)
		self.margini = dict(self.inainte)
		self.latura = M.TOATE
		self.driver = M.areDriver()

		for l in M.LATURI:
			self["linie_" + l] = Label("")
		self["zona_text"] = Label(_("Aici stau ferestrele meniului"))
		self["latura"] = Label("")
		self["valori"] = Label("")
		self["ajutor"] = Label(_("OK alege latura: toate, sus, dreapta, jos sau stânga. Săgeata spre margine duce latura "
			"aleasă spre marginea ecranului, săgeata opusă o aduce spre mijloc. La toate laturile, Sus și Dreapta măresc "
			"cadrul, Jos și Stânga îl micșorează. Potrivește cadrul până se vede întreg pe televizor."))
		self["stare"] = Label(_(M.stare(latime=self.latime, inaltime=self.inaltime)["nota"]))
		self["key_red"] = Label(_("Renunță"))
		self["key_green"] = Label(_("Salvează"))
		self["key_yellow"] = Label(_("Înapoi la implicite"))

		directii = {}
		for sageata in ("up", "down", "left", "right"):
			directii[sageata] = (lambda s=sageata: self.sageata(s))
			directii[sageata + "Repeated"] = (lambda s=sageata: self.sageata(s))
			directii[sageata + "Up"] = self.nimic      # ridicarea tastei: legata, ca jurnalul sa nu scrie "unknown action"
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], dict(directii, **{
			"ok": self.alegeLatura,
			"cancel": self.renunta,
			"red": self.renunta,
			"green": self.salveaza,
			"yellow": self.implicite,
		}), -1)
		self.onLayoutFinish.append(self.pregateste)

	def pregateste(self):
		try:
			self.instance.move(ePoint(0, 0))
			self.instance.resize(eSize(self.latime, self.inaltime))
		except Exception as e:
			print("[OSDCalibration] marimea ecranului: %s" % e)
		self._stareMarita()
		self.arata()

	def _stareMarita(self):
		"""Textul marit (Marimea textului peste 100 %): nota de stare e un singur rand; de la 125 % iese din caseta
		("...unde ar ajunge margi"). Fontul ramane la marimea aleasa, iar textul care nu incape deruleaza
		(lib/gui/elabel.h, eDerulare): nimic de facut aici."""
		return

	def arata(self):
		f = self.latime / 1920.0
		t = max(2, int(round(GROSIME * f)))
		if self.driver:
			x, y, w, h = 0, 0, self.latime, self.inaltime
		else:
			x, y, w, h = M.dreptunghi(self.margini, self.latime, self.inaltime)
		pozitii = {
			"sus": (x, y, w, t),
			"jos": (x, y + h - t, w, t),
			"stanga": (x, y, t, h),
			"dreapta": (x + w - t, y, t, h),
		}
		aleasa = _culoare(*CULOARE_ALEASA)
		obisnuita = _culoare(*CULOARE_LATURA)
		for l, (lx, ly, lw, lh) in pozitii.items():
			inst = self["linie_" + l].instance
			if inst is None:
				continue
			inst.move(ePoint(lx, ly))
			inst.resize(eSize(lw, lh))
			inst.setBackgroundColor(aleasa if self.latura in (M.TOATE, l) else obisnuita)
			inst.invalidate()
		nume = _(M.NUME[self.latura])
		if self.latura == M.TOATE:
			self["latura"].setText(nume)
		else:
			self["latura"].setText("%s: %d px" % (nume, self.margini[self.latura]))
		self["valori"].setText(M.textValori(self.margini, _))

	def nimic(self):
		pass

	def alegeLatura(self):
		self.latura = M.urmatoarea(self.latura)
		self.arata()

	def sageata(self, sageata):
		delta = M.delta_sageata(self.latura, sageata)
		if not delta:
			return
		noi = M.muta(self.margini, self.latura, delta, self.latime, self.inaltime)
		if noi != self.margini:
			self.margini = noi
			M.aplica(self.margini, self.latime, self.inaltime)
			self.arata()

	def implicite(self):
		self.margini = M.implicite()
		M.aplica(self.margini, self.latime, self.inaltime)
		self.arata()

	def salveaza(self):
		M.pune(self.margini, self.latime, self.inaltime, salveaza=True)
		M.aplica(self.margini, self.latime, self.inaltime)
		self.close(True)

	def renunta(self):
		M.aplica(self.inainte, self.latime, self.inaltime)
		self.close(False)
