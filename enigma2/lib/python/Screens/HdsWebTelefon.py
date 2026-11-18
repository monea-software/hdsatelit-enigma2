# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# "Interfata web pe telefon": un cod QR mare cu adresa simpla a interfetei web (http://<IP>/), aceeasi de fiecare data,
# deci telefonul o poate scana oricand si omul o poate pune la favorite, plus adresele de scris de mana: http://<IP> si
# numele .local, numai cand avahi il publica acum.
#
# De ce: numele hdsatelit.local nu se deschide pe orice telefon (Android fara rezolvarea .local in sistem, VPN, date
# mobile) si nici cand receptorul e pornit in alta imagine. Codul are adresa IP, deci telefonul nu mai are nevoie de nume
# si omul nu scrie nimic. Se deschide cu tasta galbena din Meniu > Informatii > Retea (Screens/Information.py,
# HdsNetworkInfo), ecranul in care omul cauta adresa receptorului.
#
# In reteaua de acasa interfata web nu cere nimic (fara cod, fara jeton, fara parola), deci codul nu are nimic in plus
# fata de adresa. Numai cand omul si-a pus singur parola si a bifat interfata web, pagina cere parola lui, o data.
#
# Perechea din web: chiar interfata web. Adresele de mai sus apar si in /informatii/retea (acelasi text ca ecranul Retea).

from enigma import getDesktop

from Screens.Screen import Screen
from Components.ActionMap import ActionMap
from Components.Sources.StaticText import StaticText
from Components.Sources.CanvasSource import CanvasSource

DESTINATIE = "/"
FUNDAL_PANOU = 0x10141a22		# culoarea panoului (#10141a22), pentru locul codului cand nu e cod


def _scala(latime, inaltime):
	x = lambda v: int(round(v * latime / 1920.0))
	y = lambda v: int(round(v * inaltime / 1080.0))
	f = lambda v: max(12, int(round(v * inaltime / 1080.0)))
	return x, y, f


def _skin(latime, inaltime):
	x, y, f = _scala(latime, inaltime)
	panou = "#10141a22"
	q = y(620)
	return """
	<screen name="HdsWebTelefon" position="0,0" size="%(l)d,%(h)d" flags="wfNoBorder" backgroundColor="#ff000000" title="Interfața web pe telefon">
		<eLabel position="%(px)d,%(py)d" size="%(pl)d,%(ph)d" backgroundColor="%(panou)s" zPosition="1" />
		<widget source="Title" render="Label" position="%(cx)d,%(ty)d" size="%(cl)d,%(th)d" font="Regular;%(tf)d" foregroundColor="#00ffffff" backgroundColor="%(panou)s" transparent="1" valign="center" zPosition="2" />
		<widget source="qr" render="Canvas" position="%(cx)d,%(qy)d" size="%(q)d,%(q)d" zPosition="2" />
		<widget source="pasi" render="Label" position="%(rx)d,%(qy)d" size="%(rl)d,%(pph)d" font="Regular;%(pf)d" foregroundColor="#00e8eef4" backgroundColor="%(panou)s" transparent="1" valign="top" zPosition="2" />
		<widget source="stare" render="Label" position="%(rx)d,%(sy)d" size="%(rl)d,%(sh)d" font="Regular;%(sf)d" foregroundColor="#00f5d76e" backgroundColor="%(panou)s" transparent="1" valign="top" zPosition="2" />
		<widget source="adresa" render="Label" position="%(cx)d,%(ay)d" size="%(cl)d,%(ah)d" font="Regular;%(af)d" foregroundColor="#00ffffff" backgroundColor="%(panou)s" transparent="1" valign="top" zPosition="2" />
		<widget source="jos" render="Label" position="%(cx)d,%(jy)d" size="%(cl)d,%(jh)d" font="Regular;%(jf)d" foregroundColor="#00a8b4c0" backgroundColor="%(panou)s" transparent="1" valign="center" zPosition="2" />
	</screen>""" % {
		"l": latime, "h": inaltime, "panou": panou,
		"px": x(120), "py": y(40), "pl": x(1680), "ph": y(1000),
		"cx": x(170), "cl": x(1580), "ty": y(56), "th": y(64), "tf": f(38),
		"q": q, "qy": y(140), "rx": x(170) + q + x(60), "rl": x(1750) - (x(170) + q + x(60)),
		"pph": y(300), "pf": f(29), "sy": y(450), "sh": y(320), "sf": f(30),
		"ay": y(785), "ah": y(140), "af": f(28), "jy": y(950), "jh": y(50), "jf": f(22),
	}


def adresaWeb():
	"""http://<IP receptor>[:port] (HdsWebControl.adresaWeb), sau None fara retea"""
	try:
		from Plugins.Extensions.HdsWebControl.plugin import adresaWeb as adresa
		return adresa()
	except Exception as e:
		print("[HdsWebTelefon] adresa interfetei web: %r" % (e,))
		return None


def numeLocal():
	"""Numele .local publicat ACUM de avahi (hdsatelit.local, hdsatelit2.local), sau "" (nescris pe ecran: un nume care
	nu raspunde l-ar trimite pe om exact unde nu merge)"""
	try:
		from Components.HdsComutareRetea import nume_local_confirmat
		return nume_local_confirmat()
	except Exception as e:
		print("[HdsWebTelefon] numele .local: %r" % (e,))
		return ""


def textCod(baza):
	"""Ce scrie in codul QR: adresa simpla a interfetei, http://<IP>[:port]/, fara nimic in plus (buna de favorite)."""
	return baza + DESTINATIE


def adreseScrise(baza, nume):
	"""Textul de sub cod: adresa IP intai (merge pe orice telefon din casa), apoi numele .local cand e publicat."""
	if nume:
		gazda = baza.split("//", 1)[-1]
		port = gazda[gazda.index(":"):] if ":" in gazda else u""
		return _("Sau scrie în browser: %s\nsau %s") % (baza, "http://" + nume + port)
	return _("Deschide în browser adresa %s.") % baza


def deseneazaQr(ecran, sursa, text, fundal=FUNDAL_PANOU):
	"""Codul QR al textului pe CanvasSource-ul `sursa` (marimea din widget), sau locul gol. -> True daca s-a desenat"""
	c = ecran[sursa]
	latime = inaltime = 0
	for r in getattr(ecran, "renderer", []) or []:
		if getattr(r, "source", None) is c and r.instance is not None:
			latime, inaltime = r.instance.size().width(), r.instance.size().height()
	if not latime:
		return False
	try:
		if text:
			from Components.HdsQr import deseneaza
			deseneaza(c, text, latime, inaltime)
		else:
			c.clear()
			c.fill(0, 0, latime, inaltime, fundal)
		c.flush()
		return True
	except Exception as e:
		print("[HdsWebTelefon] codul QR: %r" % (e,))
		return False


class HdsWebTelefon(Screen):
	"""Codul QR cu adresa interfetei web (aceeasi de fiecare data) si adresele scrise dedesubt."""

	def __init__(self, session):
		marime = getDesktop(0).size()
		self.skin = _skin(marime.width(), marime.height())
		Screen.__init__(self, session)
		self.setTitle(_("Interfața web pe telefon"))
		self["qr"] = CanvasSource()
		self["pasi"] = StaticText(_("Scanează codul cu camera telefonului, în aceeași rețea cu receptorul. Se deschide "
			"interfața web, deja conectată, fără să scrii adresa."))
		self["stare"] = StaticText(u"")
		self["adresa"] = StaticText(u"")
		self["jos"] = StaticText(_("OK sau Ieșire închide."))
		self["actiuni"] = ActionMap(["OkCancelActions"], {"ok": self.close, "cancel": self.close}, -1)
		self.onLayoutFinish.append(self._arata)

	def _arata(self):
		baza = adresaWeb()
		if not baza:
			deseneazaQr(self, "qr", u"")
			self["stare"].setText(_("Receptorul nu are legătură în rețea, deci pagina nu se poate deschide nici pe "
				"telefon."))
			self["adresa"].setText(u"")
			return
		deseneazaQr(self, "qr", textCod(baza))
		self["stare"].setText(u"")
		self["adresa"].setText(adreseScrise(baza, numeLocal()))
