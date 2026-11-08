# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Jurnal HDMI si recuperare limitata dupa conectare. Numai citirile merg in fundal.

Ceasul Enigma2 preia loturi complete, fara asteptare. Un lot blocat nu produce
alte fire. Setarile si navigarea se ating numai pe firul Enigma2.
"""
import re
import time

from Components import HdsJurnal, HdsStareOsd

try:
	_
except NameError:
	from gettext import gettext as _

PAUZA_S = 5
STABILIZARE_S = 2.0
PROBA_MAX_S = 2.0
LIMITA_ORA = 3
DISTANTA_S = 60.0

_ultimMod = [None]
_paza = [None]
_control = [None]
_sesiune = [None]


def textMod(valori, ok, atins):
	parti = []
	for k in sorted(valori):
		v = valori[k]
		if v in (None, ""):
			continue
		parti.append("%s=%s" % (k, _("da") if v is True else (_("nu") if v is False else v)))
	rez = _("primit") if ok else (_("modul refuzat de driver") if atins is False else _("o setare refuzată de driver"))
	return _("aplicat %s | %s") % (" ".join(parti) if parti else "-", rez)


def modAplicat(valori, ok, atins):
	try:
		text = textMod(valori or {}, ok, atins)
		if text != _ultimMod[0]:
			_ultimMod[0] = text
			(HdsJurnal.info if ok else HdsJurnal.avert)("hdmi", "mod", text)
		pornestePaza()
	except Exception:
		pass


def leagaSesiune(sesiune):
	_sesiune[0] = sesiune


def _context():
	from Components import VideoOutput as V
	return V.hdmiRecoveryContext(getattr(_sesiune[0], "nav", None), sesiune=_sesiune[0])


def _reaplica(context):
	from Components import VideoOutput as V
	return V.reapplyHdmi(getattr(_sesiune[0], "nav", None), asteptat=context, sesiune=_sesiune[0])


def _jurnal(nivel, modul, text):
	(HdsJurnal.info if nivel == "info" else HdsJurnal.avert)("hdmi", modul, text)


def _format(text):
	"""Formatul efectiv din disp1 sau un nume Enigma2, fara a confunda 50 cu 60 Hz."""
	from Components.HdsHdmiDate import mod_tv
	t = (text or "").split("/", 1)[0].strip()
	m = re.fullmatch(r"(\d+)\s*[*xX]\s*(\d+)_([0-9]+)", t)
	if m:
		return int(m[1]), int(m[2]), "p", int(m[3])
	return mod_tv(t)


def compara(proba, context):
	"""Coerenta campurilor expuse; nu constituie o masurare a claritatii televizorului."""
	for nod, ales in context.get("rate_asteptate", {}).items():
		valoare = (proba.get("moduri") or {}).get(nod)
		if not valoare:
			return None, _("fișierele de rată nu se pot verifica")
		if valoare != ales:
			return False, _("fișierele de rată diferă de setarea aleasă")
	mod = _format(proba.get("disp"))
	asteptate = {_format(m) for m in context.get("moduri_asteptate", (context.get("mod"),))}
	if mod is None or None in asteptate or not asteptate:
		return None, _("formatul nu se poate compara")
	if mod not in asteptate:
		return False, _("formatul efectiv diferă de cel ales")
	gp0 = proba.get("gp0")
	if gp0 is None:
		return None, _("geometria GP0 lipsește")
	if tuple(gp0) != (0, 0, mod[0], mod[1]):
		return False, _("geometria GP0 diferă de ieșirea aleasă")
	# 4:2:2 exista in captura clara. 4:2:0 nu este singur o dovada de defect.
	culoare = (proba.get("out_color") or "").upper().replace(" ", "")
	if culoare not in ("RGB", "RGB444", "YCBCR444", "YCBCR422"):
		return None, _("claritatea nu se poate deduce din culoarea raportată")
	tmds = (proba.get("tmds") or "").upper().replace(" ", "")
	if not tmds.startswith("HDMI"):
		return None, _("starea TMDS nu se poate compara")
	if mod[1] >= 2160 and mod[3] >= 50 and not tmds.startswith("HDMI2"):
		return None, _("legătura 4K este încă neconfirmată")
	return True, _("starea expusă este coerentă")


class Paza:
	def __init__(self, cititor=None, context=None, reaplica=None, jurnal=None, ceas=None):
		self.cititor = cititor if cititor is not None else HdsStareOsd.Cititor()
		self.context = context or _context
		self.reaplica = reaplica or _reaplica
		self.jurnal = jurnal or _jurnal
		self.ceas = ceas or time.monotonic
		self.anterioara = None
		self.asteptare = None
		self.dupa = None
		self.incercari = []
		self.ecouPana = 0.0
		self.identificator = 0
		self.lentSpus = False
		self.necunoscutSpus = False

	def _contextSigur(self):
		try:
			return self.context()
		except Exception:
			return {"permis": False, "motiv": _("starea receptorului nu se poate verifica")}

	def _stare(self, proba, faza, identificator=None):
		context = self._contextSigur()
		self.jurnal("info", "stare-osd", _("id=%s faza=%s ales=%s după_canal=%s %s") % (
			self.identificator if identificator is None else identificator, faza, context.get("mod") or "-",
			_("da") if context.get("rate_by_channel") else _("nu"), HdsStareOsd.textStare(proba)))

	def _decizie(self, text):
		self.jurnal("info", "reaplicare", _("id=%d %s") % (self.identificator, text))

	def _proaspata(self, proba, acum):
		inceput, sfarsit = proba.get("inceput"), proba.get("sfarsit")
		return bool(proba.get("proaspat") and inceput is not None and sfarsit is not None
			and 0 <= sfarsit - inceput <= PROBA_MAX_S and 0 <= acum - inceput <= PROBA_MAX_S)

	def primeste(self, proba):
		acum = self.ceas()
		if not isinstance(proba, dict):
			self.asteptare = None
			self.anterioara = None
			return
		proaspata = self._proaspata(proba, acum)
		proba = dict(proba, proaspat=proaspata)
		HdsStareOsd.actualizeaza(proba)
		if not proaspata:
			if not self.lentSpus:
				self._stare(proba, _("citire-veche"))
			self.lentSpus = True
			self.asteptare = None
			self.anterioara = None
			if self.dupa is not None:
				self._stare(proba, _("după-reaplicare-citire-veche"), self.dupa[1])
				self.dupa = None
			return
		self.lentSpus = False
		conectat = proba.get("conectat")
		if conectat is None:
			self.asteptare = None
			self.anterioara = None
			if not self.necunoscutSpus:
				self._stare(proba, _("conectare-necunoscută"))
			self.necunoscutSpus = True
			if self.dupa is not None:
				self._stare(proba, _("după-reaplicare-stare-necunoscută"), self.dupa[1])
				self.dupa = None
			return
		self.necunoscutSpus = False
		veche = self.anterioara
		self.anterioara = proba
		if veche is None:
			self._stare(proba, _("referință"))
			return
		evenimente = proba.get("evenimente", {})
		anterioare = veche.get("evenimente", {})
		reset = any(k in anterioare and v < anterioare[k] for k, v in evenimente.items())
		contor = not reset and any(k in anterioare and evenimente.get(k, 0) > anterioare[k]
			for k in ("HPD", "RsenCon"))
		front = conectat and (veche.get("conectat") is False or
			(veche.get("rsen") is False and proba.get("rsen") is True) or contor)
		if not conectat:
			if veche.get("conectat"):
				self._stare(proba, _("deconectare"))
			self.asteptare = None
		if front:
			self.identificator += 1
			self._stare(proba, _("conectare"))
			self.asteptare = None
			if acum < self.ecouPana:
				self._decizie(_("fereastră de protecție după reaplicare; numai diagnostic"))
			else:
				context = self._contextSigur()
				if context.get("permis"):
					self.asteptare = (acum, context.get("identitate"))
				else:
					self._decizie(context.get("motiv") or _("recuperare oprită pentru protejarea redării"))
		# Dupa reaplicare citim un lot nou; fronturile ei nu rearmeaza recuperarea.
		if self.dupa is not None and proba["inceput"] >= self.dupa[0] + STABILIZARE_S:
			inceputDupa, identificator, tinta = self.dupa
			self._stare(proba, _("după-reaplicare"), identificator)
			bun, motiv = compara(proba, tinta)
			self.jurnal("info", "reaplicare", _("id=%d verificare=%s; claritatea necesită probă vizuală") % (
				identificator, motiv if conectat and proba.get("complet") else _("stare incompletă sau deconectată")))
			self.dupa = None
		if self.asteptare is None or proba["inceput"] - self.asteptare[0] < STABILIZARE_S:
			return
		inceputAsteptare, identitate = self.asteptare
		self.asteptare = None  # consumat inainte de orice scriere, inclusiv refuz sau exceptie
		self._stare(proba, _("înainte-reaplicare"))
		context = self._contextSigur()
		if context.get("identitate") != identitate:
			self._decizie(_("setarea video s-a schimbat; încercare anulată"))
			return
		if not proba.get("msp") or not proba.get("complet") or proba.get("rsen") is False:
			self._decizie(_("probă incompletă; fără reaplicare"))
			return
		if any(not (proba.get("moduri") or {}).get(nod) for nod in context.get("rate_asteptate", {})):
			self._decizie(_("fișierele de rată nu se pot verifica; fără reaplicare"))
			return
		mod = _format(context.get("mod"))
		if mod is None or mod[1] != 2160:
			self._decizie(_("modul ales nu este 4K; fără reaplicare"))
			return
		if not context.get("permis"):
			self._decizie(context.get("motiv") or _("recuperare amânată pentru protejarea redării"))
			return
		bun, motiv = compara(proba, context)
		if bun is True:
			self._decizie(_("%s; fără reaplicare") % motiv)
			return
		self.incercari = [t for t in self.incercari if 0 <= acum - t < 3600]
		if len(self.incercari) >= LIMITA_ORA or (self.incercari and acum - self.incercari[-1] < DISTANTA_S):
			self._decizie(_("limită de protecție: cel mult trei încercări pe oră, la minimum 60 s"))
			return
		self.incercari.append(acum)
		self.ecouPana = acum + DISTANTA_S
		self.dupa = (acum, self.identificator, context)
		try:
			rezultat = self.reaplica(context) or {}
		except Exception:
			rezultat = {}
		self._decizie(_("motiv=%s scris=%s restart_cerut=%s; aștept proba efectivă") % (
			motiv, _("da") if rezultat.get("scris") else _("nu"),
			_("da") if rezultat.get("restart_cerut") else _("nu")))

	def pas(self):
		proba = self.cititor.preia()
		if proba is not None:
			self.primeste(proba)
			if not self.asteptare and not self.dupa:
				return PAUZA_S * 1000
		expirat = self.cititor.expirat(self.ceas())
		if expirat:
			self.asteptare = None
			self.anterioara = None
			if not self.lentSpus:
				self.jurnal("avert", "stare-osd", _("citire HDMI întârziată; fără reaplicare și fără alt fir de citire"))
				self.lentSpus = True
			if self.dupa is not None:
				veche = HdsStareOsd.ultima() or {}
				veche["proaspat"] = False
				self._stare(veche, _("după-reaplicare-citire-indisponibilă"), self.dupa[1])
				self.dupa = None
		self.cititor.porneste()
		return PAUZA_S * 1000 if expirat else 200


def _verifica():
	control = _control[0]
	if control is None:
		return
	interval = PAUZA_S * 1000
	try:
		interval = control.pas()
	except Exception:
		control.asteptare = None
		control.dupa = None
		control.anterioara = None
		try:
			_jurnal("avert", "stare-osd", _("paza HDMI nu a putut prelua proba; următoarea verificare rămâne programată"))
		except Exception:
			pass
	finally:
		_paza[0].start(interval, True)


def pornestePaza():
	if _paza[0] is not None:
		return
	try:
		from enigma import eTimer
	except ImportError:
		_paza[0] = False
		return
	_control[0] = Paza()
	t = eTimer()
	t.callback.append(_verifica)
	_paza[0] = t
	_verifica()
