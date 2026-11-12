# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Ecranul „Nu ai internet? Trimite prin cod QR” (TODO 1860 b; Eduard 29.10.2026 16:22-16:26), deschis din meniul Beta
# tester numai cand receptorul nu ajunge la serverul nostru (HdsBetaTester.serverFaraRaspuns). In stanga rapoartele,
# numite dupa problema omului (Components/HdsQrRapoarte.TITLURI): primul e codul general, mereu UN cod; in dreapta codul
# raportului ales. Un raport specific prea mare e o secventa scurta (cel mult 4 coduri) care se schimba singura la 2 s;
# pagina de pe telefon le citeste pe toate cu camera. OK mareste codul pe tot ecranul (si inapoi). Codurile se fac pe un
# fir (citirea jurnalelor si codul QR, care pe receptor dureaza cam o secunda), ca interfata sa nu stea.
# Perechea web: pagina /beta-tester, cardul „Receptorul nu ajunge la serverul nostru” (betatester_web.py), cu cate un
# link pe raport, care pe telefon trimite raportul intreg dintr-o atingere.
import threading

from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.Button import Button
from Components.Label import Label
from Components.MenuList import MenuList
from Components.Sources.CanvasSource import CanvasSource
from Components import HdsQrRapoarte as R
from Screens.HdsBetaTester import _rezerva, _cuCulori

SECVENTA_MS = 2000
VERIFICA_MS = 200

CORP_QR = """
		<widget name="lista" position="32,104" size="760,560" font="HdsRegular;30" itemHeight="70" foregroundColor="hdsText" backgroundColor="hdsPanelDialog" backgroundColorSelected="hdsBrand" transparent="1" scrollbarMode="showNever" zPosition="2" />
		<widget name="text" position="32,688" size="760,224" font="HdsRegular;28" foregroundColor="hdsText2" backgroundColor="hdsPanelDialog" transparent="1" valign="top" zPosition="2" />
		<widget source="qr" render="Canvas" position="904,104" size="808,808" zPosition="3" />
		<widget source="qr_mare" render="Canvas" position="388,0" size="1000,1000" zPosition="5" />"""


class HdsQrRapoarte(Screen):
	skin = _rezerva("HdsQrRapoarte", "Trimite prin cod QR", CORP_QR, ("key_red", "key_green"))

	def __init__(self, session):
		Screen.__init__(self, session)
		self.setTitle(_("Trimite prin cod QR"))
		self["lista"] = MenuList([R.titlu(f) for f in R.FELURI])
		self["text"] = Label("")
		self["qr"] = CanvasSource()
		self["qr_mare"] = CanvasSource()
		self["key_red"] = Button(_("Înapoi"))
		self["key_green"] = Button(_("Mărește"))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], _cuCulori({
			"cancel": self.inapoi,
			"red": self.inapoi,
			"ok": self.mareste,
			"green": self.mareste,
			"up": self.sus,
			"down": self.jos,
			"left": self.sus,
			"right": self.jos,
		}), -2)
		self.mare = False
		self.cache = {}          # fel -> [(adresa, matrice)]
		self.lucru = {}          # fel -> fir in lucru
		self.pas = 0
		self.fel_aratat = None
		from enigma import eTimer
		self.ceas = eTimer()
		self.ceas.callback.append(self._tic)
		self.ceasSecventa = eTimer()
		self.ceasSecventa.callback.append(self._urmatorul)
		self.onLayoutFinish.append(self._porneste)
		self.onClose.append(self._opreste)

	# ------------------------------------------------------------ codurile, pe un fir

	def _fel(self):
		i = self["lista"].getSelectedIndex() or 0
		return R.FELURI[max(0, min(i, len(R.FELURI) - 1))]

	def _fa(self, fel):
		if fel in self.cache or fel in self.lucru:
			return
		rez = {}

		def lucru():
			try:
				from Components.HdsQr import matrice
				rez["coduri"] = [(a, matrice(a)) for a in R.coduri(fel)]
			except Exception as e:
				print("[HdsQrRapoarte] %s: %s" % (fel, e))
				rez["coduri"] = []
		t = threading.Thread(target=lucru, name="hds-qr-raport")
		t.daemon = True
		t.rez = rez
		self.lucru[fel] = t
		t.start()

	def _porneste(self):
		self._arataMare(False)
		self._fa(self._fel())
		self.ceas.start(VERIFICA_MS, False)
		self._reface()

	def _opreste(self):
		self.ceas.stop()
		self.ceasSecventa.stop()

	def _tic(self):
		for fel, t in list(self.lucru.items()):
			if not t.is_alive():
				del self.lucru[fel]
				self.cache[fel] = t.rez.get("coduri") or []
				if fel == self._fel():
					self.pas = 0
					self._reface()
		if not self.lucru:
			# dupa cel ales, pe rand si celelalte (ca alegerea sa fie pe loc); cu toate gata, ceasul se opreste
			for f in R.FELURI:
				if f not in self.cache:
					self._fa(f)
					break
			else:
				self.ceas.stop()

	# ------------------------------------------------------------ desenul

	def _canvas(self):
		return "qr_mare" if self.mare else "qr"

	def _deseneaza(self, matrice_):
		nume = self._canvas()
		c = self[nume]
		latime = inaltime = 0
		for r in getattr(self, "renderer", []) or []:
			if getattr(r, "source", None) is c and r.instance is not None:
				latime, inaltime = r.instance.size().width(), r.instance.size().height()
		if not latime:
			return
		n = len(matrice_)
		margine = 4
		pas = min(latime, inaltime) // (n + 2 * margine)
		c.clear()
		c.fill(0, 0, latime, inaltime, 0x00FFFFFF)
		if pas > 0:
			x0 = (latime - pas * n) // 2
			y0 = (inaltime - pas * n) // 2
			for y in range(n):
				x = 0
				while x < n:
					if matrice_[y][x]:
						inceput = x
						while x < n and matrice_[y][x]:
							x += 1
						c.fill(x0 + inceput * pas, y0 + y * pas, (x - inceput) * pas, pas, 0x00000000)
					else:
						x += 1
		c.flush()

	def _reface(self):
		fel = self._fel()
		coduri = self.cache.get(fel)
		self.ceasSecventa.stop()
		if coduri is None:
			self["text"].setText(_("Se pregătește codul..."))
			return
		if not coduri:
			self["text"].setText(_("Codul nu s-a putut face.") + " " + _("Încearcă din nou."))
			return
		self.pas %= len(coduri)
		adresa, m = coduri[self.pas]
		self._deseneaza(m)
		cheie = ""
		try:
			import base64
			import zlib
			d = "".join(a.rsplit(".", 1)[1] for a, _m in coduri)
			text = zlib.decompress(base64.urlsafe_b64decode(d + "=" * (-len(d) % 4)), -15).decode("utf-8", "replace")
			for r in text.splitlines():
				if r.startswith("cod="):
					cheie = r[4:]
					break
		except Exception:
			cheie = ""
		randuri = [_(R.INDEMN)]
		if len(coduri) > 1:
			randuri.append(_("Codul %d din %d: se schimbă singur; ține telefonul spre ecran până le citește pe toate.")
				% (self.pas + 1, len(coduri)))
			self.ceasSecventa.start(SECVENTA_MS, True)
		if cheie:
			randuri.append(_("Codul raportului: %s") % cheie)
		self["text"].setText("\n".join(randuri))

	def _urmatorul(self):
		self.pas += 1
		self._reface()

	def _arataMare(self, mare):
		self.mare = mare
		for nume in ("lista", "text"):
			(self[nume].hide if mare else self[nume].show)()
		for r in getattr(self, "renderer", []) or []:
			if getattr(r, "source", None) is self["qr_mare"] and r.instance is not None:
				(r.instance.show if mare else r.instance.hide)()
			if getattr(r, "source", None) is self["qr"] and r.instance is not None:
				(r.instance.hide if mare else r.instance.show)()

	# ------------------------------------------------------------ tastele

	def mareste(self):
		self._arataMare(not self.mare)
		self._reface()

	def inapoi(self):
		if self.mare:
			self.mareste()
			return
		self.close()

	def sus(self):
		if self.mare:
			return
		self["lista"].up()
		self.pas = 0
		self._fa(self._fel())
		self._reface()

	def jos(self):
		if self.mare:
			return
		self["lista"].down()
		self.pas = 0
		self._fa(self._fel())
		self._reface()
