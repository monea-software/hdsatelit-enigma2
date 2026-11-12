# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsAnimatiiFerestre.py: animatia ferestrelor (HDSatelit 0.7.4): setarea si alegerea ecranelor care o primesc.
#
# Desenul: pe receptoarele a caror placa video stie animatii (/proc/stb/fb/animation_*: unele Vu+ si Gigablue) le face placa,
# ca in OE-Alliance; pe celelalte (SF8008, Viper 4K si restul) le deseneaza enigma2 (lib/gdi/hdsanimatie.h,
# lib/gui/ewidgetdesktop.cpp). Ambele drumuri trec prin aceleasi doua functii, setAnimation_current si setAnimation_speed
# (main/enigma.cpp), pe care le cheama si pluginul AnimationSetup din OE-Alliance; de aceea setarea foloseste chiar cheile
# lui: config.misc.window_animation_default (0 oprita, 1 aparitie treptata, 7 alunecare scurta, 2 marire usoara: numerele
# placii, simplefade, slidedrop, simplezoom) si config.misc.window_animation_speed (viteza AnimationSetup: 27 rapida ~150 ms,
# 20 normala 200 ms, 16 lenta 250 ms). Randurile: Setari > Interfata > OSD Preferences (data/setup.xml, „usage”); in web,
# aceeasi pagina /setari?id=usage.
#
# Ce ecrane: numai cele deschise modal din alt ecran (Session.open, mytest.py), deci meniurile, setarile, listele, mesajele
# cu intrebare. NU: primul ecran si ecranele de dinainte de bara canalului (pornirea, asistentul), bara canalului si
# playerul (la zap nicio intarziere), lista de canale si ghidul (se deschid si se inchid la fiecare schimbare de canal),
# ecranele cu imagine video in ele (PiP, previzualizarea), ecranele care cer singure fara animatie (tema: animationMode="off",
# animationPaused="1"; pluginurile: setAnimationMode(0); clasa: hdsFaraAnimatie = True). Ferestrele aratate fara
# Session.open (volumul, mesajele scurte, subtitrarile, bara la zap) nu au animatie niciodata. O tasta apasata in timpul
# animatiei o termina imediat (main/enigma.cpp).
#
# Din fabrica: pornita (aparitie treptata, normala) pe receptoarele ARM; oprita pe cele mips (Vu+ Solo SE, Duo2 si celelalte:
# procesor mai slab, nemasurat). Masurarile: STADIU-AN-ANIMATII-FERESTRE.md (hdsatelit-unelte).

import os

from Components.config import ConfigSelection, config

try:
	from enigma import setAnimation_current, setAnimation_speed, getDesktop, eVideoWidget
except ImportError:		# probele de pe PC fara enigma
	setAnimation_current = setAnimation_speed = getDesktop = None
	eVideoWidget = None

# numele claselor (si ale celor mostenite) care nu primesc animatie
FARA_ANIMATIE = frozenset((
	"InfoBar", "MoviePlayer", "InfoBarShowHide",		# bara canalului si playerul: nicio intarziere la zap
	"ChannelSelectionBase", "EPGSelection", "GraphMultiEPG", "NumberZap",	# se deschid la fiecare schimbare de canal
	"Standby", "StandbyScreen", "TryQuitMainloop",		# ecranul se stinge sau interfata reporneste
	"Wizard", "WizardLanguage",				# pornirea
	"PictureInPicture", "PiPSetup", "SubtitleDisplay", "Volume", "Toast",
))

FELURI = [("0", _("Oprită")), ("1", _("Apariție treptată")), ("7", _("Alunecare scurtă")), ("2", _("Mărire ușoară"))]
VITEZE = [("27", _("Rapidă")), ("20", _("Normală")), ("16", _("Lentă"))]


def _mips():
	try:
		return os.uname()[4].startswith("mips")
	except Exception:
		return False


def felImplicit():
	return "0" if _mips() else "1"


def _aplica(*_):
	if setAnimation_current is None:
		return
	try:
		setAnimation_speed(int(config.misc.window_animation_speed.value))
		setAnimation_current(int(config.misc.window_animation_default.value))
	except Exception as eroare:
		print("[HdsAnimatiiFerestre] %r" % eroare)


def initConfig():
	if not hasattr(config.misc, "window_animation_default"):
		config.misc.window_animation_default = ConfigSelection(default=felImplicit(), choices=FELURI)
	if not hasattr(config.misc, "window_animation_speed"):
		config.misc.window_animation_speed = ConfigSelection(default="20", choices=VITEZE)
	config.misc.window_animation_speed.addNotifier(_aplica, initial_call=False)
	config.misc.window_animation_default.addNotifier(_aplica, initial_call=True)


def dupaInchidere():
	"""Session.processDelay, la sfarsit (ecranul de dedesubt e aratat, callback-ul a rulat): desenul merge mai departe"""
	if getDesktop is not None:
		try:
			getDesktop(0).hdsAnimatieElibereaza()
		except Exception as eroare:
			print("[HdsAnimatiiFerestre] %r" % eroare)


def _clase(ecran):
	return set(c.__name__ for c in type(ecran).__mro__)


def _atributSkin(ecran, nume):
	for (atribut, valoare) in getattr(ecran, "skinAttributes", None) or ():
		if atribut == nume:
			return valoare
	return None


def _areVideo(ecran):
	if eVideoWidget is None:
		return False
	try:
		elemente = list(ecran.values()) + list(getattr(ecran, "renderer", None) or [])
	except Exception:
		return False
	for e in elemente:
		if isinstance(getattr(e, "instance", None), eVideoWidget):
			return True
	return False


def potrivit(session, ecran):
	"""True = ecranul deschis acum cu Session.open poate avea animatie (vezi lista din capul fisierului)"""
	if not session.dialog_stack:
		return False		# primul ecran (bara canalului) sau ecranele pornirii, deschise inainte de ea
	try:
		from Screens.InfoBar import InfoBar
		if InfoBar.instance is None:
			return False
	except Exception:
		return False
	if getattr(ecran, "hdsFaraAnimatie", False):
		return False
	if _clase(ecran) & FARA_ANIMATIE:
		return False
	if (_atributSkin(ecran, "animationPaused") or "").strip() in ("1", "on"):
		return False
	if _areVideo(ecran):
		return False
	return True


def _faraPas():
	if getDesktop is not None:
		getDesktop(0).hdsAnimatieFaraPas()


def laDeschidere(session, ecran):
	"""Session.open si execDialog, dupa ce ecranul a fost facut si inainte sa fie aratat: animatia lui (0x11) sau nimic (0;
	atunci nici ecranul de dedesubt nu porneste animatia, cand se ascunde)"""
	instanta = getattr(ecran, "instance", None)
	if instanta is None or not hasattr(instanta, "setAnimationMode"):
		return
	try:
		ales = instanta.getAnimationMode()		# -1 = nici tema, nici pluginul n-au ales
		if not potrivit(session, ecran):
			instanta.setAnimationMode(0)
			ales = 0
		elif ales < 0:
			instanta.setAnimationMode(0x11)
			ales = 0x11
		if not (ales & 0x01):
			_faraPas()
	except Exception as eroare:
		print("[HdsAnimatiiFerestre] %r" % eroare)


def laInchidere(session, ecran):
	"""Session.close, inainte ca ecranul sa fie ascuns: schimbarea care urmeaza e o inchidere; desenul asteapta pana ce
	processDelay arata ecranul de dedesubt (dupaInchidere), ca inchiderea sa fie un singur pas"""
	instanta = getattr(ecran, "instance", None)
	if instanta is None or getDesktop is None or not hasattr(instanta, "getAnimationMode"):
		return
	try:
		mod = instanta.getAnimationMode()
		if mod > 0 and (mod & 0x10):
			getDesktop(0).hdsAnimatieTine()		# numai la o inchidere cu animatie: lista, ghidul se sting pe loc
			getDesktop(0).hdsAnimatieInchidere()
		else:
			_faraPas()		# ecranul inchis n-are animatie: nici cel de dedesubt, cand reapare
	except Exception as eroare:
		print("[HdsAnimatiiFerestre] %r" % eroare)
