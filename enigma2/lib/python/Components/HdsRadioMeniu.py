# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Panoul radio online din meniul Pro: aceleasi date si acelasi analizor ca ecranul radio si pagina /radio.
Fara retea, decodor sau analizor separat; ceasul merge numai cat meniul care are panoul este in fata.
"""
import time
import sys


def origine_redare_radio(nav):
	"""Classify the caller, skipping forwarding methods installed on navigation."""
	cadru = sys._getframe(1)
	cauta = inceput = None
	try:
		while cadru is not None:
			if (cadru.f_globals.get("__name__") == "Navigation"
					and cadru.f_code.co_name == "playService" and cadru.f_locals.get("self") is nav):
				cadru = cadru.f_back
				break
			cadru = cadru.f_back
		wrapper = getattr(getattr(nav, "playService", None), "__code__", None)
		# Helpers inside a forwarding wrapper are transport too.
		cauta = inceput = cadru
		while cauta is not None:
			if cauta.f_locals.get("self") is nav or cauta.f_code is wrapper:
				inceput = cauta.f_back
			cauta = cauta.f_back
		cadru = inceput
		while cadru is not None:
			modul = cadru.f_globals.get("__name__", "")
			if modul.startswith("Plugins."):
				return not modul.startswith(("Plugins.Extensions.RadioOnline.", "Plugins.Extensions.HdsWebControl."))
			if modul == "RecordTimer" or modul.startswith("Screens."):
				return False
			cadru = cadru.f_back
		return False
	finally:
		del cadru, cauta, inceput


def bara_radio_proprietara(infobar):
	"""Disponibilitatea afisarii; un dialog deschis nu dovedeste cine a pornit redarea."""
	from Components.ServiceEventTracker import ServiceEventTracker
	stiva = ServiceEventTracker.InfoBarStack
	if stiva:
		varf = stiva[-1]
		if varf is not infobar and not (getattr(varf, "infobar", None) is infobar
				and not type(varf).__module__.startswith("Plugins.")):
			return False
	dialoguri = [getattr(infobar.session, "current_dialog", None)]
	dialoguri.extend(rand[0] for rand in (getattr(infobar.session, "dialog_stack", None) or []))
	for dialog in dialoguri:
		if dialog is not None and dialog is not infobar and type(dialog).__module__.startswith("Plugins."):
			# Our station selector delegates playback to the image and has no player.
			if type(dialog).__module__ != "Plugins.Extensions.RadioOnline.ecran_lista" or type(dialog).__name__ != "RadioOnline":
				return False
	return True


class LegaturaRadioLenesa(object):
	"""Tine proprietarul serviciului fara importuri radio, ferestre sau IO la pornire."""
	def __init__(self, infobar, prio=-1):
		from Components.ActionMap import ActionMap
		self.infobar = infobar
		self._leg = None
		self._inchisa = False
		self._strain = False
		self._semn = None
		self._incarca = False

		class Harta(ActionMap):
			def action(self, context, action):
				if action not in self.actions:
					return 0
				return ActionMap.action(self, context, action)

		actiuni = {"toggleShow": "okBara", "hide": "iesire", "zapUp": "zapAnterior",
			"zapDown": "zapUrmator", "switchChannelUp": "listaSus", "switchChannelDown": "listaJos",
			"openServiceList": "listaRadio", "yellow": "tastaGalbena", "green": "tastaVerde",
			"blue": "tastaAlbastra", "extensions": "faraExtensii", "audioSelection": "faraPisteAudio"}
		self._harta = Harta(["InfobarShowHideActions", "InfobarChannelSelection", "ColorActions",
			"InfobarExtensions", "InfobarAudioSelectionActions"],
			{a: self._actiune(n) for a, n in actiuni.items()}, prio=prio)
		self._harta.setEnabled(False)
		infobar["HdsRadioActions"] = self._harta
		# Direct nav events also see players which own an InfoBarBase.
		infobar.session.nav.event.append(self._eveniment)
		infobar.onExecBegin.append(self._revenire)
		infobar.onClose.append(self._inchide)

	def _actiune(self, nume):
		return lambda: getattr(self._leg, nume)() if self._leg is not None else 0

	@property
	def radio(self):
		return self._leg.radio if self._leg is not None else False

	def __getattr__(self, nume):
		if self._leg is not None:
			return getattr(self._leg, nume)
		if nume in ("vizibil", "in_odihna", "numai_sunet", "flux_cazut"):
			return False
		if nume in ("_zap", "_tastaColorata", "analiza", "dupaListaRadio", "okDinLista", "lista", "ascunde"):
			return lambda *a, **k: 0
		raise AttributeError(nume)

	def _semnServiciu(self):
		service = self.infobar.session.nav.getCurrentService()
		if service is None:
			return None
		ptr = getattr(service, "getPtrString", None)
		return ptr() if ptr is not None else service

	def _redareStraina(self):
		"""Use the request origin for synchronous starts and image continuations."""
		nav = self.infobar.session.nav
		cadru = sys._getframe(1)
		try:
			while cadru is not None:
				modul = cadru.f_globals.get("__name__", "")
				if (modul == "Navigation" and cadru.f_locals.get("self") is nav
						and cadru.f_code.co_name in ("playService", "_redaChannelZap")):
					origine = getattr(nav, "_hdsRadioOrigine", None)
					if origine is not None and origine[0] == getattr(nav, "hdsGeneratieZap", None):
						return origine[1]
					if cadru.f_code.co_name == "playService":
						return origine_redare_radio(nav)
				if modul == "Components.HdsStreamRelay" and cadru.f_locals.get("nav") is nav:
					origine = getattr(nav, "_hdsRadioOrigine", None)
					if origine is not None and origine[0] == getattr(nav, "hdsGeneratieZap", None):
						return origine[1]
				cadru = cadru.f_back
			# Native events outside a Python zap retain the conservative screen check.
			return not bara_radio_proprietara(self.infobar)
		finally:
			del cadru

	def proprietar(self):
		try:
			return (not self._inchisa and bara_radio_proprietara(self.infobar)
				and not (self._strain and self._semn == self._semnServiciu()))
		except Exception:
			return False

	def refRadioCurenta(self):
		"""Clasificarea barei, fara importarea modulelor ecranului radio."""
		try:
			from enigma import iServiceInformation
			nav = self.infobar.session.nav
			service = nav.getCurrentService()
			info = service.info() if service is not None else None
			text = info.getInfoString(iServiceInformation.sServiceref) if info is not None else ""
			if not text:
				ref = nav.getCurrentlyPlayingServiceReference()
				text = ref.toString() if ref is not None else ""
			campuri = text.split(":", 10)
			if len(campuri) < 3 or (len(campuri) > 10 and campuri[10].startswith("/")):
				return None
			if int(campuri[2], 16) in (2, 10):
				return text
			from Components.Converter import HdsCommon
			from Components.Converter.HdsInfo import HdsInfo
			sursa = type("SursaRadio", (), {})()
			sursa.service, sursa.serviceref = service, None
			if HdsInfo._radio_calc(None, HdsCommon.Reader(sursa, None)):
				return text
		except Exception:
			pass
		return None

	def _asigura(self):
		if self._leg is not None:
			return self._leg
		if self._inchisa or self._incarca or not self.proprietar():
			return None
		self._incarca = True
		try:
			self._leg = self.infobar.hdsIncarcaEcranRadio()
			if self._leg is not None:
				self._leg.legaHarta(self._harta)
		except Exception as e:
			print("[HdsRadio] incarcare la nevoie: %s" % type(e).__name__)
		finally:
			self._incarca = False
		return self._leg

	def _eveniment(self, eveniment):
		from enigma import iPlayableService
		if self._inchisa or eveniment != iPlayableService.evStart:
			return
		try:
			era_strain = self._strain
			self._semn = self._semnServiciu()
			self._strain = self._redareStraina()
			if self._strain:
				if self._leg is not None:
					self._leg.laStart()
				return
			if era_strain and self._leg is not None:
				# The native tracker ran before ownership changed, possibly on the same service.
				self._leg.laStart()
				return
			if self._leg is None and self.refRadioCurenta():
				leg = self._asigura()
				if leg is not None:
					leg.laStart()
		except Exception as e:
			print("[HdsRadio] legatura serviciului: %s" % type(e).__name__)

	def _revenire(self):
		if self._leg is None and self.proprietar() and self.refRadioCurenta():
			leg = self._asigura()
			if leg is not None:
				leg.laStart()
		elif self._leg is not None and self.proprietar():
			self._leg.dupaListaRadio()
			if self._leg.radio:
				self._leg.setariSchimbate()

	def faraBaraLaZap(self):
		if self._leg is None and self.proprietar() and self.refRadioCurenta():
			leg = self._asigura()
			if leg is not None:
				leg.laStart()
		return self._leg.faraBaraLaZap() if self._leg is not None else False

	def numaiSunet(self, da):
		leg = self._asigura() if da else self._leg
		if leg is not None:
			leg.numaiSunet(da)

	def _inchide(self):
		self._inchisa = True
		nav = self.infobar.session.nav
		if self._eveniment in nav.event:
			nav.event.remove(self._eveniment)
		if self._leg is not None:
			self._leg.inchide()
		self._harta.setEnabled(False)


def N_(text):
	return text


def _t(text):
	try:
		return _(text)
	except NameError:
		return text


def date_panou(d, RD=None):
	"""Date de afisat, pure si comune cu HdsWebControl. Nu se expune adresa fluxului."""
	if RD is None:
		from Components import HdsRadioDate as RD
	online = bool(d.get("radio") and d.get("adresa") and str(d.get("ref") or "").startswith("4097:"))
	debit = (d.get("sunet") or {}).get("debit") or 0
	aproximativ = (d.get("sunet") or {}).get("debit_masurat")
	return {"online": online, "titlu": _t(N_("Radio online")) if online else "",
		"debit": ((_t(N_("cam %d kbit/s")) if aproximativ else _t(N_("%d kbit/s"))) % debit) if debit else _t(N_("Debitul nu este disponibil")),
		"sunet": RD.text_sunet(d) if online else ""}


class PanouRadioMeniu(object):
	def __init__(self, ecran):
		from enigma import eTimer
		from Components.Label import Label
		from Components.Sources.Boolean import Boolean
		from Components.Sources.CanvasSource import CanvasSource
		self.ecran = ecran
		self.panza = None
		self.randat = False
		self.ref = None
		self.date = None
		self.citit_la = 0
		self.canvas = None
		self.activ = False
		ecran["radio_meniu_online"] = Boolean(False)
		for nume in ("titlu", "debit", "sunet", "mesaj"):
			ecran["radio_meniu_" + nume] = Label("")
		ecran["radio_meniu_bare"] = CanvasSource()
		self.ceas = eTimer()
		self.ceas.callback.append(self._pas)
		ecran.onLayoutFinish.append(self._aseaza)
		ecran.onShow.append(self._arata)
		ecran.onHide.append(self._ascunde)
		ecran.onClose.append(self._inchide)

	def _aseaza(self):
		from Components import HdsRadioDesen as DES
		e = self.ecran
		self.canvas = next((r for r in e.renderer if getattr(r, "source", None) is e["radio_meniu_bare"]
			and getattr(r, "instance", None) is not None), None)
		if self.canvas is None:
			return
		marime = self.canvas.instance.size()
		try:
			from skin import colorNames
			fond = colorNames["hdsPanelSolid"].argb() & 0xFFFFFF
		except Exception:
			fond = 0x10162A
		self.panza = DES.Panza(marime.width(), marime.height(), fel="bare", fundal=fond)
		DES.aplica(e["radio_meniu_bare"], self.panza.goleste())
		self._arata()

	def _arata(self):
		if self.canvas is None:
			return
		self.activ = True
		self.citit_la = 0
		self._pas()
		if self.activ:
			self.ceas.start(100)

	def _ascunde(self):
		self.activ = False
		self.ceas.stop()

	def _inchide(self):
		self._ascunde()
		self.ceas.callback.remove(self._pas)
		self.ecran = None

	def _vizibil(self, online):
		e = self.ecran
		if e["radio_meniu_online"].boolean != online:
			e["radio_meniu_online"].boolean = online
		for nume in ("titlu", "debit", "sunet", "mesaj"):
			(e["radio_meniu_" + nume].show if online else e["radio_meniu_" + nume].hide)()
		if self.canvas is not None:
			self.canvas.visible = online

	def _text(self, nume, text):
		eticheta = self.ecran["radio_meniu_" + nume]
		if eticheta.getText() != text:
			eticheta.setText(text)

	def _pas(self):
		if not self.activ or self.ecran is None:
			return
		try:
			self._actualizeaza()
		except Exception:
			# Nicio eroare a panoului radio nu trebuie sa strice navigarea in meniu.
			self._vizibil(False)
			self._ascunde()
			print("[HdsRadioMeniu] panoul nu se poate actualiza")

	def _actualizeaza(self):
		from Components import HdsRadioDate as RD, HdsRadioDesen as DES
		e = self.ecran
		acum = time.time()
		# The menu must not load the player just to look for an existing analyser.
		modul = sys.modules.get("Screens.HdsEcranRadio")
		leg = modul.legatura() if modul is not None else None
		if acum - self.citit_la >= 1:
			ref = RD.ref_curenta(e.session)[1]
			if not (ref.startswith("4097:") and RD.adresa_publica(ref)):
				# La un canal TV sau la radio din satelit meniul nu plateste citirea datelor postului.
				self.citit_la = acum
				self.date = self.ref = None
				if e["radio_meniu_online"].boolean or self.randat:
					DES.aplica(e["radio_meniu_bare"], self.panza.goleste())
					self.randat = False
				self._vizibil(False)
				return
			analiza = leg.analiza() if leg is not None else None
			if self.date is None or self.ref != ref:
				self.date = RD.date(e.session, 0, analiza, acum)
				self.ref = ref
			else:
				self.date = RD.rapid(self.date, e.session, analiza, acum)
			panou = date_panou(self.date, RD)
			self._vizibil(panou["online"])
			if panou["online"]:
				for nume in ("titlu", "debit", "sunet"):
					self._text(nume, panou[nume])
				if leg is not None:
					leg.cerereWeb()
			self.citit_la = acum
		if not e["radio_meniu_online"].boolean:
			return
		an = getattr(leg, "analizor", None) if leg is not None else None
		nivele = an.nivele(0.25) if an is not None else None
		if nivele:
			info = an.flux.info or {}
			DES.aplica(e["radio_meniu_bare"], self.panza.cadru(nivele, 24, acum, info.get("esantionare", 48000)))
			self._text("mesaj", "")
			self.randat = True
		else:
			if self.randat:
				DES.aplica(e["radio_meniu_bare"], self.panza.goleste())
				self.randat = False
			self._text("mesaj", RD.text_bare(leg.analiza() if leg is not None else None, "bare"))
