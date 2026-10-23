# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsCodAsociere.py: fereastra cu codul de asociere pe televizor. Codul trebuie sa se vada de la distanta, deci e
# foarte mare, in mijlocul ecranului, cu litere mari si asezare aerisita (o fraza intr-un MessageBox se citea greu).
#
# Continutul: titlul („Conectare browser” sau „Conectare telefon”), codul in trei grupe de cate doua cifre
# („12 34 56”), randul cu adresa aparatului care l-a cerut si „Dacă nu l-ai cerut tu, apasă EXIT.”.
# Fara bara de timp si fara numaratoare: codul e valabil o ora (asociere.DURATA_COD_S).
#
# Aceeasi fereastra pentru browser si pentru aplicatia de telefon. Se deschide:
# - prin Tools.Notifications (Plugins/Extensions/HdsWebControl/plugin.py, _arataCodPeTelevizor), ca sa apara peste
#   canal si, daca omul e intr-un meniu, dupa iesirea din el;
# - direct, din ecranul interfetei web (Screens/HdsWebControlSetup.py, Albastru, „Conectează un browser nou”); acolo
#   randul adresei spune unde se deschide pagina.
#
# Se inchide:
# - la OK sau EXIT: si ANULEAZA codul acelei ferestre (numai pe el, dupa id-ul cererii), ca un cod cerut de altcineva
#   sa nu mai poata fi folosit;
# - singura, fara sa anuleze nimic, cand codul ei nu mai e cel activ (aparatul s-a conectat, codul a fost inlocuit sau
#   anulat din alta parte): intreaba o data pe secunda (`activ`), iar plugin.py o inchide si imediat, la conectare;
# - singura la expirare (dupa o ora), cu mesajul scurt „A trecut o oră ...” (`laExpirare`, pus de plugin.py; ecranul
#   de setari il arata el, din rezultatul „expirat”).
#
# Skinul: blocul <screen name="HdsCodAsociere"> din skinul HDSatelit (1920x1080). Pentru alte skinuri, skinul de
# rezerva de mai jos, facut la deschidere dupa marimea ecranului (1920x1080 sau 1280x720), numai cu fontul
# „Regular” si culori scrise direct (orice skin le are).

import time

from enigma import eTimer, getDesktop, gFont

from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.Sources.StaticText import StaticText

TIP_APLICATIE = "aplicatie"

# Cifrele trec prin cache-ul de glife mici al FreeType (FTC_SBit, lib/gdi/font.cpp): o glifa mai inalta de 127 de pixeli
# deasupra liniei de baza nu se deseneaza deloc. La fonturile HDSatelit (cifrele au 1485/2048 din em) asta inseamna
# cel mult ~175 px; in emulator, la 190 casutele au ramas goale. Skinul cere 160; daca omul a marit literele
# (ecranul Fonturi, pana la 130 %), marimea cifrelor se coboara aici la MARIME_MAXIMA_COD.
MARIME_MAXIMA_COD = 165

# Codul expira in asociere.py cu cel mult o secunda inaintea ferestrei (plugin.py rotunjeste in sus secundele ramase):
# un cod care nu mai e activ in ultimele 2 secunde ale ferestrei a expirat, nu a fost folosit sau anulat.
TOLERANTA_EXPIRARE_S = 2.0

# ferestrele deschise acum (de obicei una): plugin.py le inchide pe toate cand se conecteaza un aparat
_deschise = []


def grupeCod(cod):
	"""'123456' -> ['12', '34', '56'] (trei casute pe ecran); aceeasi impartire ca asociere.codAfisat."""
	cod = str(cod or "")
	return [cod[i:i + 2] for i in range(0, len(cod), 2)]


def codAfisat(cod):
	"""'123456' -> '12 34 56'."""
	return " ".join(grupeCod(cod))


def inchideToate():
	"""Inchide ferestrele de cod deschise (aparatul s-a conectat), fara sa anuleze nimic."""
	for fereastra in list(_deschise):
		fereastra.inchide()


def marimeEfectiva(marime):
	"""Marimea cu care se deseneaza un font din skin, dupa marirea aleasa de om (skin._hds_scaleaza, 80-130 %)."""
	try:
		import skin
		return skin._hds_scaleaza(marime)
	except Exception:
		return marime


def skinRezerva(latime, inaltime):
	"""Skinul folosit cand skinul ales nu are blocul HdsCodAsociere: aceeasi asezare ca in skinul HDSatelit,
	socotita pentru ecranul de acum (1920x1080 sau 1280x720)."""
	def x(v):
		return int(round(v * latime / 1920.0))

	def y(v):
		return int(round(v * inaltime / 1080.0))

	pl, ph = x(1240), y(640)
	casuta_l, casuta_h, pas = x(330), y(250), x(370)
	x0 = (pl - (casuta_l * 3 + (pas - casuta_l) * 2)) // 2
	casute = []
	for i in range(3):
		casute.append('<eLabel position="%d,%d" size="%d,%d" backgroundColor="#00283450" zPosition="1" />'
			% (x0 + i * pas, y(150), casuta_l, casuta_h))
		casute.append('<widget source="cod%d" render="Label" position="%d,%d" size="%d,%d" font="Regular;%d" '
			'halign="center" valign="center" foregroundColor="#00ffffff" backgroundColor="#00283450" transparent="1" '
			'zPosition="2" />' % (i + 1, x0 + i * pas, y(150), casuta_l, casuta_h, y(160)))
	return """
	<screen name="HdsCodAsociere" position="center,center" size="%(pl)d,%(ph)d" flags="wfNoBorder" backgroundColor="#00101828" title="Conectare">
		<eLabel position="0,0" size="%(pl)d,%(linie)d" backgroundColor="#00ffffff" zPosition="1" />
		<widget source="titlu" render="Label" position="%(mx)d,%(ty)d" size="%(cl)d,%(th)d" font="Regular;%(tf)d" halign="center" valign="center" foregroundColor="#00f2f4f8" backgroundColor="#00101828" transparent="1" zPosition="1" />
		%(casute)s
		<widget source="adresa" render="Label" position="%(mx)d,%(ay)d" size="%(cl)d,%(ah)d" font="Regular;%(af)d" halign="center" valign="center" foregroundColor="#00c9d2e3" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget source="nota" render="Label" position="%(mx)d,%(ny)d" size="%(cl)d,%(nh)d" font="Regular;%(af)d" halign="center" valign="center" foregroundColor="#00f5b83d" backgroundColor="#00101828" transparent="1" zPosition="1" />
	</screen>""" % {
		"pl": pl, "ph": ph, "linie": max(1, y(2)),
		"mx": x(40), "cl": pl - 2 * x(40),
		"ty": y(40), "th": y(80), "tf": y(52),
		"casute": "\n\t\t".join(casute),
		"ay": y(430), "ah": y(70), "af": y(38),
		"ny": y(530), "nh": y(70),
	}


class HdsCodAsociere(Screen):
	"""cod: cele 6 cifre; tip: 'browser' sau 'aplicatie'; adresa: IP-ul aparatului care a cerut codul ("" din
	telecomanda); adresaWeb: unde se deschide pagina (numai din ecranul de setari); expira: time.monotonic() la care
	expira codul; activ(): True cat timp codul ferestrei e inca cel activ; anuleaza(): anuleaza codul (OK/EXIT);
	laExpirare(): chemat o data, dupa inchiderea la expirare."""

	def __init__(self, session, cod, tip="browser", adresa="", adresaWeb="", expira=None, activ=None, anuleaza=None,
			laExpirare=None):
		marime = getDesktop(0).size()
		self.skin = skinRezerva(marime.width(), marime.height())
		Screen.__init__(self, session)
		if tip == TIP_APLICATIE:
			titlu = _("Conectare telefon")
		else:
			titlu = _("Conectare browser")
		self.setTitle(titlu)
		self["titlu"] = StaticText(titlu)
		self["cod"] = StaticText(codAfisat(cod))
		grupe = (grupeCod(cod) + ["", "", ""])[:3]
		self["cod1"] = StaticText(grupe[0])
		self["cod2"] = StaticText(grupe[1])
		self["cod3"] = StaticText(grupe[2])
		if adresa:
			self["adresa"] = StaticText(_("Cerut de la %s") % adresa)
			nota = _("Dacă nu l-ai cerut tu, apasă EXIT.")
		elif adresaWeb:
			self["adresa"] = StaticText(_("Deschide în browser %s") % adresaWeb)
			nota = _("OK sau EXIT închide fereastra și anulează codul.")
		else:
			self["adresa"] = StaticText("")
			nota = _("Dacă nu l-ai cerut tu, apasă EXIT.")
		self["nota"] = StaticText(nota)
		self._expira = expira
		self._activ = activ
		self._anuleaza = anuleaza
		self._laExpirare = laExpirare
		self._inchisa = False
		self["actiuni"] = ActionMap(["OkCancelActions"], {
			"ok": self.apasat,
			"cancel": self.apasat,
		}, -1)
		self._ceas = eTimer()
		self._ceas.callback.append(self._verifica)
		self.onLayoutFinish.append(self._porneste)
		self.onClose.append(self._laInchidere)
		_deschise.append(self)

	def _porneste(self):
		self._limiteazaCifrele()
		# prima verificare imediat: fereastra poate fi scoasa din coada dupa ce a stat mult intr-un meniu
		self._ceas.start(50, True)

	def _limiteazaCifrele(self):
		"""Coboara fontul cifrelor la MARIME_MAXIMA_COD daca skinul si marirea aleasa de om il duc mai sus."""
		surse = [self[k] for k in ("cod", "cod1", "cod2", "cod3")]
		for r in getattr(self, "renderer", None) or []:
			if not any(getattr(r, "source", None) is s for s in surse) or getattr(r, "instance", None) is None:
				continue
			font = dict(getattr(r, "skinAttributes", None) or []).get("font", "")
			if ";" not in font:
				continue
			nume, marime = font.split(";", 1)
			try:
				marime = int(marime)
			except ValueError:
				continue
			if marimeEfectiva(marime) > MARIME_MAXIMA_COD:
				r.instance.setFont(gFont(nume, MARIME_MAXIMA_COD))

	def _verifica(self):
		if self._inchisa:
			return
		acum = time.monotonic()
		expirat = self._expira is not None and acum >= self._expira
		if not expirat and self._activ is not None:
			try:
				activ = self._activ()
			except Exception as eroare:
				print("[HdsCodAsociere] starea codului: %s" % eroare)
				activ = True
			if not activ:
				if self._expira is not None and acum >= self._expira - TOLERANTA_EXPIRARE_S:
					expirat = True  # codul a expirat in asociere.py cu o clipa inaintea ferestrei
				else:
					self.inchide()  # folosit (aparatul s-a conectat), anulat sau inlocuit
					return
		if expirat:
			if self.inchide("expirat") and self._laExpirare is not None:
				try:
					self._laExpirare()
				except Exception as eroare:
					print("[HdsCodAsociere] mesajul de expirare: %s" % eroare)
			return
		self._ceas.start(1000, True)

	def apasat(self):
		"""OK sau EXIT: inchide si anuleaza codul ferestrei (cine se uita la televizor nu l-a cerut, sau a terminat)."""
		if self._inchisa:
			return
		if self._anuleaza is not None:
			try:
				self._anuleaza()
			except Exception as eroare:
				print("[HdsCodAsociere] anularea codului: %s" % eroare)
		self.close("anulat")

	def inchide(self, rezultat=None):
		"""Inchidere fara anulare (conectare, cod inlocuit, expirare). Daca alt ecran a fost deschis peste fereastra
		(nu ar trebui), incearca din nou la secunda urmatoare. True daca a inchis."""
		if self._inchisa:
			return False
		if self.session is not None and self.session.current_dialog is not self:
			self._ceas.start(1000, True)
			return False
		self.close(rezultat)
		return True

	def close(self, *rezultat):
		# si cand o inchide Tools.Notifications.RemovePopup (plugin.py), ca ceasul sa nu mai incerce nimic
		self._inchisa = True
		self._ceas.stop()
		Screen.close(self, *rezultat)

	def _laInchidere(self):
		self._inchisa = True
		self._ceas.stop()
		if self in _deschise:
			_deschise.remove(self)
