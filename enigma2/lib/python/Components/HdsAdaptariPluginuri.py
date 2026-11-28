# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsAdaptariPluginuri.py: adaptari legate de un plugin extern anume, chemate de Components/PluginComponent.py numai dupa
# importul acelui plugin (0.8.0). Cu pluginul neinstalat nu se intampla nimic: modulul nici nu se importa.
#
# Tema FullHDGlass (pachetul autorului, pluginul ei de setari Plugins/Extensions/setupGlass17): pe imaginile pe care nu le
# recunoaste, patru setari ale ei rescriu fisiere ale imaginii (Screens/Menu.py inlocuit de meniul ei la tipul de meniu cu
# iconite, Screens/ChannelSelection.py la "2xOK", /usr/share/enigma2/encoding.conf la "user encoding", Screens/ServiceScan.py
# la "lista lunga" de la cautare). Pe imaginile OE-Alliance pe care le sustine autorul, aceleasi functii intorc False si sting
# setarea. Aici facem la fel: fisierele imaginii raman ale imaginii, tema si restul setarilor ei merg neschimbate.
# Functiile temei se cauta dupa nume; daca o versiune noua le redenumeste, jurnalul spune ce lipseste.
#
# Nu importa nimic din enigma2 la incarcare (probele de pe PC).

ETICHETA = "[HdsAdaptariPluginuri]"

# numele functiei din pluginul temei -> setarea pe care o stinge (None: nicio setare), ca ramura temei pentru imaginile sustinute
FULLHDGLASS_FARA_RESCRIERI = (
	("setMenuPyo", None),        # Screens/Menu.py
	("chnlSelPatch", 62),        # Screens/ChannelSelection.py
	("setEncodingUser", 59),     # /usr/share/enigma2/encoding.conf
	("chckFifo", 67),            # Screens/ServiceScan.py
)


def _jurnal(*text):
	print(ETICHETA, *text)


def _stinge(modul, numar):
	"""Setarea config.plugins.setupGlass17.par<numar> pusa pe False si salvata, ca in tema. Nu arunca."""
	try:
		from Components.config import config, configfile
		setare = getattr(config.plugins.setupGlass17, "par%d" % numar)
		if setare.value:
			setare.value = False
			setare.save()
			configfile.save()
	except Exception as exc:
		_jurnal("setupGlass17: setarea par%d:" % numar, exc)


def _inerta(modul, nume, numar):
	def faraRescriere(*args, **kwargs):
		_jurnal("setupGlass17: %s oprita (fisierul imaginii ramane neschimbat)" % nume)
		if numar is not None:
			_stinge(modul, numar)
		return False
	faraRescriere.hdsInerta = True
	faraRescriere.__name__ = nume
	return faraRescriere


def fullhdglass(modul):
	"""Pluginul de setari al temei FullHDGlass: functiile care rescriu fisiere ale imaginii devin inerte. Intoarce lista numelor
	care lipsesc din modul (gol: toate gasite). Nu arunca."""
	lipsa = []
	for nume, numar in FULLHDGLASS_FARA_RESCRIERI:
		f = getattr(modul, nume, None)
		if not callable(f):
			lipsa.append(nume)
			continue
		if getattr(f, "hdsInerta", False):
			continue
		try:
			setattr(modul, nume, _inerta(modul, nume, numar))
		except Exception as exc:
			_jurnal("setupGlass17:", nume, exc)
			lipsa.append(nume)
	# "2xOK" nu se mai ofera in ecranul ei de setari, ca pe imaginile sustinute
	if hasattr(modul, "E2OK"):
		try:
			modul.E2OK = False
		except Exception:
			pass
	if lipsa:
		_jurnal("setupGlass17: ATENTIE, nu gasesc %s: o versiune noua a temei poate rescrie fisiere ale imaginii" % ", ".join(lipsa))
	else:
		_jurnal("setupGlass17: setarile care rescriu fisiere ale imaginii sunt inerte")
	return lipsa


# s4aUpdater (liste de canale si OSCam, adus de AIO Panel; AS169 si AS172, ndairou, SF8008, 24.11.2026): autostart() deschide
# la pornirea sesiunii ecranul s4aUpdaterBoot, care n-are skin, n-are ActionMap si nu se inchide niciodata; sta nevazut peste
# InfoBar si ia toate tastele (MENU, EXIT nu mai merg). Treaba lui e numai sa ruleze comanda de pornire din main.cfg (primul
# rand "S:...:...:comanda"). Aici autostart face acelasi lucru fara ecran; comanda ruleaza ca in plugin (os.system, pe loc).
S4A_SEPARATOR = ":"


def _s4aComandaPornire(modul):
	"""Comanda de pornire din <pluginpath>/main.cfg, ca s4aUpdaterBoot.__init__; None daca primul rand nu e "S"."""
	import os
	cale = getattr(modul, "pluginpath", None)
	if not cale:
		return None
	separator = getattr(modul, "splitchar", S4A_SEPARATOR) or S4A_SEPARATOR
	try:
		with open(os.path.join(cale, "main.cfg"), "r") as f:
			rand = f.readline()
	except (IOError, OSError):
		return None
	parti = rand.split(separator, 3)
	if len(parti) < 2:
		return None
	comanda = parti[0].upper().rstrip()
	if not comanda.startswith("S") or len(parti) < 4:
		return None
	cmd = parti[3].rstrip()
	if not cmd:
		return None
	return os.path.join(cale, cmd) if os.path.exists(os.path.join(cale, cmd)) else cmd


def s4aupdater(modul):
	"""s4aUpdater: autostart fara ecranul s4aUpdaterBoot. Intoarce True daca a inlocuit autostart. Nu arunca."""
	original = getattr(modul, "autostart", None)
	if not callable(original) or getattr(original, "hdsFaraEcran", False):
		return False
	if not hasattr(modul, "s4aUpdaterBoot"):
		_jurnal("s4aUpdater: fara s4aUpdaterBoot, autostart ramane al pluginului")
		return False

	def autostart(reason, **kwargs):
		if reason == 0 and "session" in kwargs:
			try:
				modul.session = kwargs["session"]
			except Exception:
				pass
			cmd = _s4aComandaPornire(modul)
			if cmd:
				import os
				_jurnal("s4aUpdater: comanda de pornire din main.cfg, fara ecranul s4aUpdaterBoot:", cmd)
				os.system(cmd)
			return None
		return original(reason, **kwargs)
	autostart.hdsFaraEcran = True
	autostart.__name__ = "autostart"
	modul.autostart = autostart
	_jurnal("s4aUpdater: ecranul s4aUpdaterBoot nu se mai deschide la pornire (lua tastele)")
	return True


# (categoria, dosarul pluginului) -> adaptarea
ADAPTARI = {
	("Extensions", "setupGlass17"): fullhdglass,
	("Extensions", "s4aUpdater"): s4aupdater,
}


def dupaImport(categorie, nume, modul):
	"""Chemata din PluginComponent dupa importul pluginului categorie/nume. Nu arunca; intoarce modulul primit."""
	adaptare = ADAPTARI.get((categorie, nume))
	if adaptare is not None and modul is not None:
		try:
			adaptare(modul)
		except Exception as exc:
			_jurnal(categorie, nume, exc)
	return modul
