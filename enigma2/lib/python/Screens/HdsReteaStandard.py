# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsReteaStandard.py (0.7.4): ecranele de retea cu numele familiei noi a standardului OE-Alliance, pentru temele care au
# NUMAI forma noua (in corpusul de 300 de pachete: doua teme de azi). Celelalte teme (90 de pachete) au ecranele
# clasice (NetworkAdapterSelection...) si le deseneaza ca pana acum; tema HD Satelit la fel.
#
# Nimic nou pentru om: aceleasi date si aceleasi taste ca lista clasica a placilor (Screens/NetworkSetup.py, din care
# NetworkOverview mosteneste tot: citirea placilor, starea pe loc, OK = setarile placii, galben = placa implicita, albastru =
# asistentul retelei), numai aspectul temei alese. Perechea din web e aceeasi pagina /retea (aceleasi functii, HdsRetea).
#
# Contractul ecranului (documentatia standardului, network/screen-contracts): sursele adapterList si savedList (List cu
# indexNames; randul 0 e antetul, desenat cu primul <rowtemplate>), savedLabel, key_red..key_blue, key_menu, key_info.
from os import path as os_path

from enigma import gRGB

from Components.Sources.List import List
from Components.Sources.StaticText import StaticText
from Components.Network import iNetwork
from Components import HdsRetea
from Components.HdsCursorLista import pune_randurile
from Tools.Directories import resolveFilename, SCOPE_PLUGINS
from Screens.NetworkSetup import NetworkAdapterSelection, AdapterSetupConfiguration

# coloanele randului, ca in standard; ultima coloana (13) e a noastra: numele placii, pentru taste
INDEX_PLACI = {"Reserved_for_rowTemplate": 0, "AdapterGlyph": 1, "AdapterName": 2, "AdapterType": 3, "StatusText": 4,
	"StatusColor": 5, "StatusColorSelected": 6, "MAC": 7, "IPAddress": 8, "Gateway": 9, "Speed": 10, "InternetGlyph": 11,
	"ConnectionText": 12}
PLACA = 13
INDEX_SALVATE = {"Reserved_for_rowTemplate": 0, "SSID": 1, "BSSID": 2, "Frequency": 3, "Channel": 4, "Encryption": 5,
	"StatusText": 6, "StatusGlyph": 7, "StatusColor": 8, "StatusColorSelected": 9}
ANTET, RAND = 0, 1

# culorile starii (verde legat, rosu fara legatura, gri oprit/salvat), ca in standard
VERDE = gRGB(0x0000CC00).argb()
ROSU = gRGB(0x00CC0000).argb()
GRI = gRGB(0x00808080).argb()


def temaCere(nou, clasic):
	"""True cand tema straina aleasa are ecranul `nou` si nu are ecranul `clasic` (cu tema HD Satelit: False)"""
	try:
		import skin
		if not getattr(skin, "dosareSkinStraine", None):
			return False
		return skin.lookupScreenTema(nou, skin.GUI_SKIN_ID)[0] is not None and \
			skin.lookupScreenTema(clasic, skin.GUI_SKIN_ID)[0] is None
	except Exception:
		return False


class HdsListaPlaci(object):
	"""„Network Connection Setup” din meniu (menu.xml cere o clasa): NetworkOverview cand tema aleasa il cere, altfel lista
	clasica a placilor, cu aceleasi argumente. __new__ intoarce chiar ecranul ales (deci __init__ de aici nu ruleaza)."""
	def __new__(cls, session, *args, **kwargs):
		if temaCere("NetworkOverview", "NetworkAdapterSelection"):
			return NetworkOverview(session)
		return NetworkAdapterSelection(session, *args, **kwargs)


def _citeste(cale):
	try:
		with open(cale) as f:
			return f.read().strip()
	except (IOError, OSError):
		return ""


def vitezaPlacii(placa, radacina=""):
	"""„1000 Mbit/s” din /sys/class/net/<placa>/speed (numai cablul legat; Wi-Fi si placile oprite: "")"""
	v = _citeste(radacina + HdsRetea.SYS_NET + placa + "/speed")
	try:
		n = int(v)
	except ValueError:
		return ""
	return "%d Mbit/s" % n if n > 0 else ""


def criptare(bloc):
	"""criptarea unei retele salvate, din key_mgmt al blocului ei din wpa_supplicant.conf"""
	for rand in bloc.splitlines():
		r = rand.strip().replace(" ", "")
		if r.startswith("key_mgmt="):
			v = r[9:]
			if v == "NONE":
				return _("deschisă")
			if "SAE" in v and "WPA-PSK" in v:
				return "WPA2/WPA3"
			if "SAE" in v:
				return "WPA3"
			if "WPA-PSK" in v:
				return "WPA2"
			return v
	return "WPA2"


def randPlaca(placa, nume, st, mac="", poarta="", viteza=""):
	"""randul unei placi in adapterList (forma standardului), din starea HdsRetea.stareAdaptor"""
	if not st["pornita"]:
		culoare = GRI
	elif st["activa"] or st["legatura"]:
		culoare = VERDE
	else:
		culoare = ROSU
	fel = _("Wi-Fi") if st["wifi"] else _("Cablu")
	legatura = _("internetul trece pe aici") if st["internet"] else ""
	return (RAND, "", nume, fel, HdsRetea.textStare(st).split(" · ")[0], culoare, culoare, mac or "", st["ip"] or "",
		poarta or "", viteza, "", legatura, placa)


def antetPlaci():
	return (ANTET, "", _("Placă"), "", _("Stare"), None, None, "MAC", _("Adresă IP"), _("Poartă"), _("Viteză"), "", "", None)


def antetSalvate():
	return (ANTET, "SSID", "BSSID", _("Frecvență"), _("Canal"), _("Criptare"), _("Stare"), "", None, None)


def reteleSalvate(cale=None):
	"""randurile savedList: retelele Wi-Fi salvate (numele si criptarea; fara parole), in ordinea din fisier"""
	from Components import WlanTools
	text = _citeste(cale or WlanTools.SUPPLICANT_CONF)
	if not text:
		return []
	rez = []
	vazute = set()
	for ssid, bloc in WlanTools.parseConf(text)[1]:
		if ssid is None or ssid in vazute or WlanTools.isWildcardBlock(ssid, bloc):
			continue
		vazute.add(ssid)
		rez.append((RAND, WlanTools.ssidName(ssid), "", "", "", criptare(bloc), _("Salvată"), "", GRI, GRI))
	return rez


def _continut(sursa):
	"""continutul listei desenate a unei surse (prin convertor), sau None"""
	for c in getattr(sursa, "downstream_elements", ()):
		if getattr(c, "content", None) is not None:
			return c.content
	return None


def _instanta(sursa):
	for c in getattr(sursa, "downstream_elements", ()):
		for r in getattr(c, "downstream_elements", ()):
			if getattr(r, "instance", None) is not None:
				return r.instance
	return None


class NetworkOverview(NetworkAdapterSelection):
	"""lista placilor sub numele si contractul standardului; tastele si datele sunt ale listei clasice"""
	# rezerva, folosita numai daca tema nu are ecranul (meniul il deschide doar cand tema il are)
	skin = """<screen name="NetworkOverview" position="center,center" size="1100,540" title="Network Overview" resolution="1280,720">
		<widget source="adapterList" render="Listbox" position="10,10" size="1080,250">
			<template name="Default" fonts="Regular;24,Regular;20" itemHeight="50">
				<rowtemplate>
					<text index="AdapterName" position="0,0" size="300,50" font="1" verticalAlignment="center" />
					<text index="StatusText" position="300,0" size="300,50" font="1" verticalAlignment="center" />
					<text index="IPAddress" position="600,0" size="240,50" font="1" verticalAlignment="center" />
					<text index="Speed" position="840,0" size="240,50" font="1" verticalAlignment="center" />
				</rowtemplate>
				<rowtemplate>
					<text index="AdapterName" position="0,0" size="300,30" font="0" />
					<text index="AdapterType" position="0,30" size="300,20" font="1" />
					<text index="StatusText" position="300,0" size="300,50" font="1" verticalAlignment="center" foregroundColor="+StatusColor" />
					<text index="IPAddress" position="600,0" size="240,50" font="1" verticalAlignment="center" />
					<text index="Speed" position="840,0" size="240,50" font="1" verticalAlignment="center" />
				</rowtemplate>
			</template>
		</widget>
		<widget source="savedLabel" render="Label" position="10,270" size="1080,25" font="Regular;20" />
		<widget source="savedList" render="Listbox" position="10,305" size="1080,175">
			<template name="Default" fonts="Regular;22" itemHeight="35">
				<rowtemplate><text index="SSID" position="0,0" size="500,35" font="0" /><text index="Encryption" position="500,0" size="300,35" font="0" /></rowtemplate>
				<rowtemplate><text index="SSID" position="0,0" size="500,35" font="0" /><text index="Encryption" position="500,0" size="300,35" font="0" /></rowtemplate>
			</template>
		</widget>
		<widget source="key_red" render="Label" position="10,e-50" size="180,40" font="Regular;20" halign="center" valign="center" backgroundColor="#9f1313" />
		<widget source="key_green" render="Label" position="200,e-50" size="180,40" font="Regular;20" halign="center" valign="center" backgroundColor="#1f771f" />
		<widget source="key_yellow" render="Label" position="390,e-50" size="180,40" font="Regular;20" halign="center" valign="center" backgroundColor="#a08000" />
		<widget source="key_blue" render="Label" position="580,e-50" size="180,40" font="Regular;20" halign="center" valign="center" backgroundColor="#18188b" />
	</screen>"""

	def __init__(self, session):
		NetworkAdapterSelection.__init__(self, session)
		self.skinName = ["NetworkOverview"]
		# lista clasica nu e in contract: o tema care n-o are ar fi respinsa (skin.py, motivRezervaTema: „lista ecranului
		# lipseste din tema”); randurile ei le face updateList de mai jos in adapterList
		del self["list"]
		self["savedLabel"] = StaticText("")
		self["key_menu"] = StaticText("")
		self["key_info"] = StaticText("")
		self["adapterList"] = List([], indexNames=INDEX_PLACI)
		self["savedList"] = List([], indexNames=INDEX_SALVATE)
		self.onLayoutFinish.append(self.hdsDupaAsezare)
		self.updateList()

	def hdsDupaAsezare(self):
		# antetul (randul 0) nu se poate alege; lista retelelor salvate e numai de citit (tastele raman la placi)
		continut = _continut(self["adapterList"])
		if continut is not None and hasattr(continut, "setSelectableFunc"):
			continut.setSelectableFunc(lambda *rand: bool(rand) and rand[0] != ANTET)
		if self["adapterList"].count() > 1 and not self.hdsPlacaAleasa():
			self["adapterList"].index = 1
		inst = _instanta(self["savedList"])
		if inst is not None:
			if hasattr(inst, "allowNativeKeys"):
				inst.allowNativeKeys(False)
			inst.setSelectionEnable(False)

	def updateList(self):
		if "adapterList" not in self:
			return   # chemata o data din constructorul listei clasice, inainte de sursele noastre
		# tastele, ca in lista clasica (NetworkSetup.NetworkAdapterSelection.updateList)
		if len(iNetwork.getConfiguredAdapters()) >= 2:
			self["key_yellow"].setText(_("Default"))
			self["introduction"].setText(self.defaulttext)
			self["DefaultInterfaceAction"].setEnabled(True)
		else:
			self["key_yellow"].setText("")
			self["introduction"].setText(self.edittext)
			self["DefaultInterfaceAction"].setEnabled(False)
		if os_path.exists(resolveFilename(SCOPE_PLUGINS, "SystemPlugins/NetworkWizard/networkwizard.xml")):
			self["key_blue"].setText(_("NetworkWizard"))
		self.stariVazute = self.stari()
		randuri = [antetPlaci()]
		for nume, placa in self.adapters:
			st = HdsRetea.stareAdaptor(placa, iNetwork.getAdapterAttribute(placa, "ip"), wifi=iNetwork.isWirelessInterface(placa))
			randuri.append(randPlaca(placa, _(nume), st, iNetwork.getAdapterAttribute(placa, "mac"),
				self.hdsPoarta(placa), vitezaPlacii(placa)))
		# dupa setarile placii sau repornirea retelei cursorul ramane pe placa lui (cheia: numele placii, coloana 13)
		pune_randurile(self["adapterList"], randuri, cheie=PLACA)
		salvate = reteleSalvate() if any(iNetwork.isWirelessInterface(p) for _n, p in self.adapters) else []
		self["savedLabel"].setText(_("Rețele Wi-Fi salvate") if salvate else "")
		pune_randurile(self["savedList"], [antetSalvate()] + salvate if salvate else [], cheie=1)

	@staticmethod
	def hdsPoarta(placa):
		g = iNetwork.getAdapterAttribute(placa, "gateway")
		if isinstance(g, (list, tuple)):
			return ".".join(str(int(x)) for x in g) if len(g) == 4 and any(g) else ""
		return g or ""

	def hdsPlacaAleasa(self):
		r = self["adapterList"].getCurrent() if "adapterList" in self else None
		return r[PLACA] if r and r[0] == RAND else None

	# tastele listei clasice, cu placa aleasa din adapterList
	def okbuttonClick(self):
		if self.citesteAdaptoare:
			return
		placa = self.hdsPlacaAleasa()
		if placa is not None:
			self.session.openWithCallback(self.AdapterSetupClosed, AdapterSetupConfiguration, placa)

	def setDefaultInterface(self):
		placa = self.hdsPlacaAleasa()
		if placa is not None and HdsRetea.alegePlacaImplicita(placa, iNetwork):
			self.restartLan()

	def openNetworkWizard(self):
		placa = self.hdsPlacaAleasa()
		if placa is None:
			return
		try:
			from Plugins.SystemPlugins.NetworkWizard.NetworkWizard import NetworkWizard
		except ImportError:
			return
		self.session.openWithCallback(self.AdapterSetupClosed, NetworkWizard, placa)
