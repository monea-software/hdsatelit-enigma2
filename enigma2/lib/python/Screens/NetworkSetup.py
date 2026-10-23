# Modificat de moneasoftware.com si hdsatelit.com, 2026
from .Screen import Screen
from Screens.MessageBox import MessageBox
from Screens.InputBox import InputBox
from Screens.Standby import *
from Screens.VirtualKeyBoard import VirtualKeyBoard
from Screens.HelpMenu import HelpableScreen
from Components.Network import iNetwork
# the logic of these screens is shared with the web interface (/retea, /dns): Components/HdsRetea.py
from Components import HdsRetea
from Components.Sources.StaticText import StaticText
from Components.Sources.Boolean import Boolean
from Components.Sources.List import List
from Components.HdsCursorLista import pune_randurile
from Components.Label import Label,MultiColorLabel
from Components.Pixmap import Pixmap,MultiPixmap
from Components.MenuList import MenuList
from Components.config import config, ConfigYesNo, ConfigIP, NoSave, ConfigText, ConfigPassword, ConfigSelection, getConfigListEntry, ConfigNothing, ConfigBoolean
from Components.ConfigList import ConfigListScreen
from Components.PluginComponent import plugins
from Components.MultiContent import MultiContentEntryText, MultiContentEntryPixmapAlphaTest
from Components.ActionMap import ActionMap, NumberActionMap, HelpableActionMap
from Tools.Directories import resolveFilename, SCOPE_PLUGINS, SCOPE_CURRENT_SKIN
from Tools.LoadPixmap import LoadPixmap
from Plugins.Plugin import PluginDescriptor
from enigma import eTimer, ePoint, eSize, RT_HALIGN_LEFT, eListboxPythonMultiContent, gFont
from os import path as os_path, system as os_system, unlink
from re import compile as re_compile, search as re_search


class NetworkAdapterSelection(Screen,HelpableScreen):
	def __init__(self, session):
		Screen.__init__(self, session)
		HelpableScreen.__init__(self)
		
		self.wlan_errortext = _("No working wireless network adapter found.\nPlease verify that you have attached a compatible WLAN device and your network is configured correctly.")
		self.lan_errortext = _("No working local network adapter found.\nPlease verify that you have attached a network cable and your network is configured correctly.")
		self.oktext = _("Press OK on your remote control to continue.")
		self.edittext = _("Press OK to edit the settings.")
		self.defaulttext = _("Press yellow to set this interface as default interface.")
		self.restartLanRef = None
		
		self["key_red"] = StaticText(_("Close"))
		self["key_green"] = StaticText(_("Select"))
		self["key_yellow"] = StaticText("")
		self["key_blue"] = StaticText("")
		self["introduction"] = StaticText(self.edittext)
		
		self["OkCancelActions"] = HelpableActionMap(self, "OkCancelActions",
			{
			"cancel": (self.close, _("exit network interface list")),
			"ok": (self.okbuttonClick, _("select interface")),
			})

		self["ColorActions"] = HelpableActionMap(self, "ColorActions",
			{
			"red": (self.close, _("exit network interface list")),
			"green": (self.okbuttonClick, _("select interface")),
			"blue": (self.openNetworkWizard, _("Use the Networkwizard to configure selected network adapter")),
			})
		
		self["DefaultInterfaceAction"] = HelpableActionMap(self, "ColorActions",
			{
			"yellow": (self.setDefaultInterface, [_("Set interface as default Interface"),_("* Only available if more than one interface is active.")] ),
			})

		self.adapters = [(iNetwork.getFriendlyAdapterName(x),x) for x in HdsRetea.adaptoare(iNetwork)]

		self.list = []
		self["list"] = List(self.list)
		self.updateList()

		# starea placilor (cablul bagat sau scos, Wi-Fi legat, adresa, pe unde trece internetul) se vede pe loc: lista
		# se reface cand se schimba ceva, citind numai fisierele nucleului
		self.stareTimer = eTimer()
		self.stareTimer.callback.append(self.refaStarea)
		self.stareTimer.start(2000, False)

		if len(self.adapters) == 1:
			self.onFirstExecBegin.append(self.okbuttonClick)
		self.onClose.append(self.cleanup)

	def stari(self):
		return [(x[1], HdsRetea.stareAdaptor(x[1], iNetwork.getAdapterAttribute(x[1], "ip"),
			wifi=iNetwork.isWirelessInterface(x[1]))) for x in self.adapters]

	def refaStarea(self):
		if self.stari() != getattr(self, "stariVazute", None):
			self.updateList()

	def buildInterfaceList(self,iface,name,default,active ):
		divpng = LoadPixmap(cached=True, path=resolveFilename(SCOPE_CURRENT_SKIN, "skin_default/div-h.png"))
		defaultpng = None
		activepng = None
		description = None
		interfacepng = None

		# pictograma si randul de sub nume arata starea adevarata a placii (HdsRetea.stareAdaptor): bifa verde = pornita,
		# legata (cablu bagat / Wi-Fi legat) si cu adresa; X rosu = oprita; fara semn = pornita, dar fara legatura
		st = HdsRetea.stareAdaptor(iface, iNetwork.getAdapterAttribute(iface, "ip"), wifi=iNetwork.isWirelessInterface(iface))
		fel = HdsRetea.pictogramaStare(st)
		baza = "network_wireless" if st["wifi"] else "network_wired"
		sufix = {"activa": "-active", "oprita": "-inactive"}.get(fel, "")
		interfacepng = LoadPixmap(resolveFilename(SCOPE_CURRENT_SKIN, "skin_default/icons/%s%s.png" % (baza, sufix)))
		active = st["activa"]

		num_configured_if = len(iNetwork.getConfiguredAdapters())
		if num_configured_if >= 2:
			if default is True:
				defaultpng = LoadPixmap(cached=True, path=resolveFilename(SCOPE_CURRENT_SKIN, "skin_default/buttons/button_blue.png"))
			elif default is False:
				defaultpng = LoadPixmap(cached=True, path=resolveFilename(SCOPE_CURRENT_SKIN, "skin_default/buttons/button_blue_off.png"))
		if active is True:
			activepng = LoadPixmap(cached=True, path=resolveFilename(SCOPE_CURRENT_SKIN, "skin_default/icons/lock_on.png"))
		elif active is False:
			activepng = LoadPixmap(cached=True, path=resolveFilename(SCOPE_CURRENT_SKIN, "skin_default/icons/lock_error.png"))
		
		description = HdsRetea.textStare(st)

		return((iface, name, description, interfacepng, defaultpng, activepng, divpng))	

	def updateList(self):
		self.list = []
		default_gw = None
		num_configured_if = len(iNetwork.getConfiguredAdapters())
		if num_configured_if >= 2:
			self["key_yellow"].setText(_("Default"))
			self["introduction"].setText(self.defaulttext)
			self["DefaultInterfaceAction"].setEnabled(True)
		else:
			self["key_yellow"].setText("")
			self["introduction"].setText(self.edittext)
			self["DefaultInterfaceAction"].setEnabled(False)

		default_gw = HdsRetea.placaImplicita(iNetwork)

		self.stariVazute = self.stari()
		for x in self.adapters:
			if x[1] == default_gw:
				default_int = True
			else:
				default_int = False
			if iNetwork.getAdapterAttribute(x[1], 'up') is True:
				active_int = True
			else:
				active_int = False
			self.list.append(self.buildInterfaceList(x[1],_(x[0]),default_int,active_int ))
		
		if os_path.exists(resolveFilename(SCOPE_PLUGINS, "SystemPlugins/NetworkWizard/networkwizard.xml")):
			self["key_blue"].setText(_("NetworkWizard"))
		# dupa setarile placii (OK) sau repornirea retelei cursorul ramane pe placa lui (cheia: numele placii)
		pune_randurile(self["list"], self.list, cheie=0)

	def setDefaultInterface(self):
		selection = self["list"].getCurrent()
		if selection is not None and HdsRetea.alegePlacaImplicita(selection[0], iNetwork):
			self.restartLan()

	def okbuttonClick(self):
		selection = self["list"].getCurrent()
		if selection is not None:
			self.session.openWithCallback(self.AdapterSetupClosed, AdapterSetupConfiguration, selection[0])

	def AdapterSetupClosed(self, *ret):
		if len(self.adapters) == 1:
			self.close()
		else:
			self.updateList()

	def cleanup(self):
		self.stareTimer.stop()
		iNetwork.stopLinkStateConsole()
		iNetwork.stopRestartConsole()
		iNetwork.stopGetInterfacesConsole()

	def restartLan(self):
		HdsRetea.reporneste(self.getInterfacesDataAvail, iNetwork)
		self.restartLanRef = self.session.openWithCallback(self.restartfinishedCB, MessageBox, _("Please wait while we configure your network..."), type = MessageBox.TYPE_INFO, enable_input = False)

	def getInterfacesDataAvail(self, data):
		if data is True:
			self.restartLanRef.close(True)

	def restartfinishedCB(self,data):
		if data is True:
			self.updateList()
			self.session.open(MessageBox, _("Finished configuring your network"), type = MessageBox.TYPE_INFO, timeout = 10, default = False)

	def openNetworkWizard(self):
		if os_path.exists(resolveFilename(SCOPE_PLUGINS, "SystemPlugins/NetworkWizard/networkwizard.xml")):
			try:
				from Plugins.SystemPlugins.NetworkWizard.NetworkWizard import NetworkWizard
			except ImportError:
				self.session.open(MessageBox, _("The NetworkWizard extension is not installed!\nPlease install it."), type = MessageBox.TYPE_INFO,timeout = 10 )
			else:
				selection = self["list"].getCurrent()
				if selection is not None:
					self.session.openWithCallback(self.AdapterSetupClosed, NetworkWizard, selection[0])


class NameserverSetup(Screen, ConfigListScreen, HelpableScreen):
	def __init__(self, session):
		Screen.__init__(self, session)
		HelpableScreen.__init__(self)
		self.backupNameserverList = iNetwork.getNameserverList()[:]
		print("backup-list:", self.backupNameserverList)
		
		self["key_red"] = StaticText(_("Cancel"))
		self["key_green"] = StaticText(_("Add"))
		self["key_yellow"] = StaticText(_("Delete"))

		self["introduction"] = StaticText(_("Press OK to activate the settings."))
		self.createConfig()

		self["OkCancelActions"] = HelpableActionMap(self, "OkCancelActions",
			{
			"cancel": (self.cancel, _("exit nameserver configuration")),
			"ok": (self.ok, _("activate current configuration")),
			})

		self["ColorActions"] = HelpableActionMap(self, "ColorActions",
			{
			"red": (self.cancel, _("exit nameserver configuration")),
			"green": (self.add, _("add a nameserver entry")),
			"yellow": (self.remove, _("remove a nameserver entry")),
			})

		self["actions"] = NumberActionMap(["SetupActions"],
		{
			"ok": self.ok,
		}, -2)

		self.list = []
		ConfigListScreen.__init__(self, self.list)
		self.createSetup()
		
	def createConfig(self):
		self.nameservers = iNetwork.getNameserverList()
		self.nameserverEntries = [ NoSave(ConfigIP(default=nameserver)) for nameserver in self.nameservers]

	def createSetup(self):
		self.list = []

		i = 1
		for x in self.nameserverEntries:
			self.list.append(getConfigListEntry(_("Nameserver %d") % (i), x))
			i += 1

		self["config"].list = self.list
		self["config"].l.setList(self.list)

	def ok(self):
		HdsRetea.scrieDns([nameserver.value for nameserver in self.nameserverEntries], iNetwork)
		self.close()

	def run(self):
		self.ok()

	def cancel(self):
		iNetwork.clearNameservers()
		print("backup-list:", self.backupNameserverList)
		for nameserver in self.backupNameserverList:
			iNetwork.addNameserver(nameserver)
		self.close()

	def add(self):
		iNetwork.addNameserver([0,0,0,0])
		self.createConfig()
		self.createSetup()

	def remove(self):
		print("currentIndex:", self["config"].getCurrentIndex())
		index = self["config"].getCurrentIndex()
		if index < len(self.nameservers):
			iNetwork.removeNameserver(self.nameservers[index])
			self.createConfig()
			self.createSetup()


class AdapterSetup(Screen, ConfigListScreen, HelpableScreen):
	def __init__(self, session, networkinfo, essid=None):
		Screen.__init__(self, session)
		HelpableScreen.__init__(self)
		self.session = session
		if isinstance(networkinfo, (list, tuple)):
			self.iface = networkinfo[0]
			self.essid = networkinfo[1]
		else:
			self.iface = networkinfo
			self.essid = essid
			
		self.extended = None
		self.applyConfigRef = None
		self.finished_cb = None
		self.oktext = _("Press OK on your remote control to continue.")
		self.oldInterfaceState = iNetwork.getAdapterAttribute(self.iface, "up")

		self.createConfig()

		self["OkCancelActions"] = HelpableActionMap(self, "OkCancelActions",
			{
			"cancel": (self.keyCancel, _("exit network adapter configuration")),
			"ok": (self.keySave, _("activate network adapter configuration")),
			})

		self["ColorActions"] = HelpableActionMap(self, "ColorActions",
			{
			"red": (self.keyCancel, _("exit network adapter configuration")),
			"green": (self.keySave, _("activate network adapter configuration")),
			"blue": (self.KeyBlue, _("open nameserver configuration")),
			})

		self["actions"] = NumberActionMap(["SetupActions"],
		{
			"ok": self.keySave,
		}, -2)

		self.list = []
		ConfigListScreen.__init__(self, self.list,session = self.session)
		self.createSetup()
		# valorile de la deschidere, apoi cele salvate: intrebarea de la iesire apare numai cand ceva s-a schimbat si nu
		# s-a salvat (randurile NoSave raman "schimbate" si dupa salvare, deci isChanged() nu ajunge)
		self.valoriSalvate = self.valori()
		self.onLayoutFinish.append(self.layoutFinished)
		self.onClose.append(self.cleanup)

		self["DNS1text"] = StaticText(_("Primary DNS"))
		self["DNS2text"] = StaticText(_("Secondary DNS"))
		self["DNS1"] = StaticText()
		self["DNS2"] = StaticText()
		self["introduction"] = StaticText(_("Current settings:"))

		self["IPtext"] = StaticText(_("IP Address"))
		self["Netmasktext"] = StaticText(_("Netmask"))
		self["Gatewaytext"] = StaticText(_("Gateway"))

		self["IP"] = StaticText()
		self["Mask"] = StaticText()
		self["Gateway"] = StaticText()

		self["Adaptertext"] = StaticText(_("Network:"))
		self["Adapter"] = StaticText()
		self["introduction2"] = StaticText(_("Verde sau OK: salvează setările și le pornește. Roșu: ieși fără să salvezi."))
		self["key_red"] = StaticText(_("Cancel"))
		self["key_green"] = StaticText(_("Salvează"))
		self["key_blue"] = StaticText(_("Edit DNS"))

		self["VKeyIcon"] = Boolean(False)
		self["HelpWindow"] = Pixmap()
		self["HelpWindow"].hide()
		
	def layoutFinished(self):
		self["DNS1"].setText(self.primaryDNS.getText())
		self["DNS2"].setText(self.secondaryDNS.getText())
		if self.ipConfigEntry.getText() is not None:
			if self.ipConfigEntry.getText() == "0.0.0.0":
				self["IP"].setText(_("N/A"))
			else:	
				self["IP"].setText(self.ipConfigEntry.getText())
		else:
			self["IP"].setText(_("N/A"))
		if self.netmaskConfigEntry.getText() is not None:
			if self.netmaskConfigEntry.getText() == "0.0.0.0":
					self["Mask"].setText(_("N/A"))
			else:	
				self["Mask"].setText(self.netmaskConfigEntry.getText())
		else:
			self["Mask"].setText(_("N/A"))
		if iNetwork.getAdapterAttribute(self.iface, "gateway"):
			if self.gatewayConfigEntry.getText() == "0.0.0.0":
				self["Gatewaytext"].setText(_("Gateway"))
				self["Gateway"].setText(_("N/A"))
			else:
				self["Gatewaytext"].setText(_("Gateway"))
				self["Gateway"].setText(self.gatewayConfigEntry.getText())
		else:
			self["Gateway"].setText("")
			self["Gatewaytext"].setText("")
		self["Adapter"].setText(iNetwork.getFriendlyAdapterName(self.iface))

	def createConfig(self):
		self.InterfaceEntry = None
		self.dhcpEntry = None
		self.gatewayEntry = None
		self.hiddenSSID = None
		self.wlanSSID = None
		self.encryption = None
		self.encryptionType = None
		self.encryptionKey = None
		self.encryptionlist = None
		self.weplist = None
		self.wsconfig = None
		self.default = None

		if iNetwork.isWirelessInterface(self.iface):
			try:
				from Plugins.SystemPlugins.WirelessLan.Wlan import wpaSupplicant
				self.ws = wpaSupplicant()
			except ImportError:
				self.ws = None
			self.encryptionlist = []
			self.encryptionlist.append(("Unencrypted", _("Unencrypted")))
			self.encryptionlist.append(("WEP", _("WEP")))
			self.encryptionlist.append(("WPA", _("WPA")))
			self.encryptionlist.append(("WPA/WPA2", _("WPA or WPA2")))
			self.encryptionlist.append(("WPA2", _("WPA2")))
			self.weplist = []
			self.weplist.append("ASCII")
			self.weplist.append("HEX")

			# the WiFi fields come from the WiFi plugin; without it only the IP settings are shown
			if self.ws is not None and "wlan" in config.plugins.content.items:
				self.wsconfig = self.ws.loadConfig(self.iface)
				if self.essid is None:
					self.essid = self.wsconfig['ssid']

				config.plugins.wlan.hiddenessid = NoSave(ConfigYesNo(default = self.wsconfig['hiddenessid']))
				config.plugins.wlan.essid = NoSave(ConfigText(default = self.essid, visible_width = 50, fixed_size = False))
				config.plugins.wlan.encryption = NoSave(ConfigSelection(self.encryptionlist, default = self.wsconfig['encryption'] ))
				config.plugins.wlan.wepkeytype = NoSave(ConfigSelection(self.weplist, default = self.wsconfig['wepkeytype'] ))
				config.plugins.wlan.psk = NoSave(ConfigPassword(default = self.wsconfig['key'], visible_width = 50, fixed_size = False))

		self.activateInterfaceEntry = NoSave(ConfigYesNo(default=iNetwork.getAdapterAttribute(self.iface, "up") or False))
		self.dhcpConfigEntry = NoSave(ConfigYesNo(default=iNetwork.getAdapterAttribute(self.iface, "dhcp") or False))
		# "or [0,0,0,0]" era in afara parantezei ConfigIP(...),
		# deci se aplica pe obiectul NoSave(ConfigIP(...)) (mereu adevarat, un obiect), nu pe valoarea
		# "ip" -- daca getAdapterAttribute intoarce None, ConfigIP(default=None) primea None direct.
		self.ipConfigEntry = NoSave(ConfigIP(default=iNetwork.getAdapterAttribute(self.iface, "ip") or [0,0,0,0]))
		self.netmaskConfigEntry = NoSave(ConfigIP(default=iNetwork.getAdapterAttribute(self.iface, "netmask") or [255,0,0,0]))
		if iNetwork.getAdapterAttribute(self.iface, "gateway"):
			self.dhcpdefault=True
		else:
			self.dhcpdefault=False
		self.hasGatewayConfigEntry = NoSave(ConfigYesNo(default=self.dhcpdefault or False))
		self.gatewayConfigEntry = NoSave(ConfigIP(default=iNetwork.getAdapterAttribute(self.iface, "gateway") or [0,0,0,0]))
		nameserver = (iNetwork.getNameserverList() + [[0,0,0,0]] * 2)[0:2]
		self.primaryDNS = NoSave(ConfigIP(default=nameserver[0]))
		self.secondaryDNS = NoSave(ConfigIP(default=nameserver[1]))

	def createSetup(self):
		self.list = []
		self.InterfaceEntry = getConfigListEntry(_("Use Interface"), self.activateInterfaceEntry)

		self.list.append(self.InterfaceEntry)
		if self.activateInterfaceEntry.value:
			self.dhcpEntry = getConfigListEntry(_("Use DHCP"), self.dhcpConfigEntry)
			self.list.append(self.dhcpEntry)
			if not self.dhcpConfigEntry.value:
				self.list.append(getConfigListEntry(_('IP Address'), self.ipConfigEntry))
				self.list.append(getConfigListEntry(_('Netmask'), self.netmaskConfigEntry))
				self.gatewayEntry = getConfigListEntry(_('Use a gateway'), self.hasGatewayConfigEntry)
				self.list.append(self.gatewayEntry)
				if self.hasGatewayConfigEntry.value:
					self.list.append(getConfigListEntry(_('Gateway'), self.gatewayConfigEntry))

			self.extended = None
			self.configStrings = None
			for p in plugins.getPlugins(PluginDescriptor.WHERE_NETWORKSETUP):
				callFnc = p.fnc["ifaceSupported"](self.iface)
				if callFnc is not None:
					if "WlanPluginEntry" in p.fnc: # internally used only for WLAN Plugin
						self.extended = callFnc
						if "configStrings" in p.fnc:
							self.configStrings = p.fnc["configStrings"]

						self.hiddenSSID = getConfigListEntry(_("Hidden network"), config.plugins.wlan.hiddenessid)
						self.list.append(self.hiddenSSID)
						self.wlanSSID = getConfigListEntry(_("Networkname (SSID)"), config.plugins.wlan.essid)
						self.list.append(self.wlanSSID)
						self.encryption = getConfigListEntry(_("Encryption"), config.plugins.wlan.encryption)
						self.list.append(self.encryption)						

						self.encryptionType = getConfigListEntry(_("Encryption Keytype"), config.plugins.wlan.wepkeytype)
						self.encryptionKey = getConfigListEntry(_("Encryption Key"), config.plugins.wlan.psk)
						
						if config.plugins.wlan.encryption.value != "Unencrypted":
							if config.plugins.wlan.encryption.value == 'WEP':
								self.list.append(self.encryptionType)
							self.list.append(self.encryptionKey)
		self["config"].list = self.list
		self["config"].l.setList(self.list)

	def KeyBlue(self):
		self.session.openWithCallback(self.NameserverSetupClosed, NameserverSetup)

	def newConfig(self):
		if self["config"].getCurrent() == self.InterfaceEntry:
			self.createSetup()
		if self["config"].getCurrent() == self.dhcpEntry:
			self.createSetup()
		if self["config"].getCurrent() == self.gatewayEntry:
			self.createSetup()
		if iNetwork.isWirelessInterface(self.iface):
			if self["config"].getCurrent() == self.encryption:
				self.createSetup()

	def keyLeft(self):
		ConfigListScreen.keyLeft(self)
		self.newConfig()

	def keyRight(self):
		ConfigListScreen.keyRight(self)
		self.newConfig()
	
	def valori(self):
		"""Randurile vazute acum (eticheta si valoarea): ce s-ar salva."""
		rez = []
		for x in self.list:
			try:
				rez.append((x[0], str(x[1].value)))
			except Exception:
				rez.append((x[0], None))
		return tuple(rez)

	def schimbat(self):
		return self.valori() != self.valoriSalvate

	def keySave(self):
		self.hideInputHelp()
		if self.schimbat():
			self.session.openWithCallback(self.keySaveConfirm, MessageBox, (_("Are you sure you want to activate this network configuration?\n\n") + self.oktext ) )
		else:
			if self.finished_cb:
				self.finished_cb()
			else:
				self.close('cancel')

	def keySaveConfirm(self, ret = False):
		if (ret == True):
			if HdsRetea.trebuieOpritaAlta(self.iface, iNetwork):
				self.session.openWithCallback(self.secondIfaceFoundCB, MessageBox, _("A second configured interface has been found.\n\nDo you want to disable the second network interface?"), default = True)
			else:
				self.applyConfig(True)
		else:
			self.keyCancel()

	def secondIfaceFoundCB(self,data):
		if data is False:
			self.applyConfig(True)
		else:
			HdsRetea.opresteCelelalte(self.iface, self.deactivateSecondInterfaceCB, iNetwork)

	def deactivateSecondInterfaceCB(self, data):
		if data is True:
			self.applyConfig(True)

	def applyConfig(self, ret = False):
		if (ret == True):
			self.applyConfigRef = None

			def wlanLines():
				if (self.extended is not None and self.configStrings is not None):
					iNetwork.setAdapterAttribute(self.iface, "configStrings", self.configStrings(self.iface))
					self.ws.writeConfig(self.iface)

			gateway = self.gatewayConfigEntry.value if self.hasGatewayConfigEntry.value else None
			HdsRetea.aplicaPlaca(self.iface, self.activateInterfaceEntry.value, self.dhcpConfigEntry.value,
				self.ipConfigEntry.value, self.netmaskConfigEntry.value, gateway, self.oldInterfaceState,
				self.getInterfacesDataAvail, iNetwork, extra=wlanLines)
			self.applyConfigRef = self.session.openWithCallback(self.applyConfigfinishedCB, MessageBox, _("Please wait for activation of your network configuration..."), type = MessageBox.TYPE_INFO, enable_input = False)
		else:
			self.keyCancel()

	def getInterfacesDataAvail(self, data):
		if data is True:
			self.applyConfigRef.close(True)

	def applyConfigfinishedCB(self,data):
		if data is True:
			# salvat: de acum nimic nu mai e "nesalvat"; semnul "Salvat" pe ecran, apoi ecranul se inchide oricum se
			# raspunde la mesaj (OK, Iesire sau timpul trecut)
			self.valoriSalvate = self.valori()
			self["key_green"].setText(_("Salvat"))
			text = _("Salvat. Setările rețelei sunt pornite acum.")
			if self.finished_cb:
				self.session.openWithCallback(lambda x : self.finished_cb(), MessageBox, text, type = MessageBox.TYPE_INFO, timeout = 5)
			else:
				self.session.openWithCallback(self.ConfigfinishedCB, MessageBox, text, type = MessageBox.TYPE_INFO, timeout = 5)

	def ConfigfinishedCB(self,data):
		self.close('ok')

	def keyCancelConfirm(self, result):
		if not result:
			return
		if self.oldInterfaceState is False:
			iNetwork.deactivateInterface(self.iface,self.keyCancelCB)
		else:
			self.close('cancel')

	def keyCancel(self):
		self.hideInputHelp()
		if self.schimbat():
			self.session.openWithCallback(self.keyCancelConfirm, MessageBox, _("Really close without saving settings?"))
		else:
			self.close('cancel')

	def keyCancelCB(self,data):
		if data is not None:
			if data is True:
				self.close('cancel')

	def runAsync(self, finished_cb):
		self.finished_cb = finished_cb
		self.keySave()

	def NameserverSetupClosed(self, *ret):
		iNetwork.loadNameserverConfig()
		nameserver = (iNetwork.getNameserverList() + [[0,0,0,0]] * 2)[0:2]
		self.primaryDNS = NoSave(ConfigIP(default=nameserver[0]))
		self.secondaryDNS = NoSave(ConfigIP(default=nameserver[1]))
		self.createSetup()
		self.layoutFinished()

	def cleanup(self):
		iNetwork.stopLinkStateConsole()
		
	def hideInputHelp(self):
		current = self["config"].getCurrent()
		if current == self.wlanSSID:
			if current[1].help_window.instance is not None:
				current[1].help_window.instance.hide()
		elif current == self.encryptionKey and config.plugins.wlan.encryption.value != "Unencrypted":
			if current[1].help_window.instance is not None:
				current[1].help_window.instance.hide()


class AdapterSetupConfiguration(Screen, HelpableScreen):
	def __init__(self, session,iface):
		Screen.__init__(self, session)
		HelpableScreen.__init__(self)
		self.session = session
		self.iface = iface
		self.restartLanRef = None
		self.LinkState = None
		self.mainmenu = self.genMainMenu()
		self["menulist"] = MenuList(self.mainmenu)
		self["key_red"] = StaticText(_("Close"))
		self["description"] = StaticText()
		self["IFtext"] = StaticText()
		self["IF"] = StaticText()
		self["Statustext"] = StaticText()
		self["statuspic"] = MultiPixmap()
		self["statuspic"].hide()
		
		self.oktext = _("Press OK on your remote control to continue.")
		self.reboottext = _("Your receiver will restart after pressing OK on your remote control.")
		self.errortext = _("No working wireless network interface found.\n Please verify that you have attached a compatible WLAN device or enable your local network interface.")
		self.missingwlanplugintxt = _("The wireless LAN plugin is not installed!\nPlease install it.")
		
		self["WizardActions"] = HelpableActionMap(self, "WizardActions",
			{
			"up": (self.up, _("move up to previous entry")),
			"down": (self.down, _("move down to next entry")),
			"left": (self.left, _("move up to first entry")),
			"right": (self.right, _("move down to last entry")),
			})
		
		self["OkCancelActions"] = HelpableActionMap(self, "OkCancelActions",
			{
			"cancel": (self.close, _("exit networkadapter setup menu")),
			"ok": (self.ok, _("select menu entry")),
			})

		self["ColorActions"] = HelpableActionMap(self, "ColorActions",
			{
			"red": (self.close, _("exit networkadapter setup menu")),	
			})

		self["actions"] = NumberActionMap(["WizardActions","ShortcutActions"],
		{
			"ok": self.ok,
			"back": self.close,
			"up": self.up,
			"down": self.down,
			"red": self.close,
			"left": self.left,
			"right": self.right,
		}, -2)
		
		self.updateStatusbar()
		self.onLayoutFinish.append(self.layoutFinished)
		self.onClose.append(self.cleanup)


	def queryWirelessDevice(self,iface):
		try:
			from pythonwifi.iwlibs import Wireless
			import errno
		except ImportError:
			return False
		else:
			try:
				ifobj = Wireless(iface) # a Wireless NIC Object
				wlanresponse = ifobj.getAPaddr()
			except IOError as xxx_todo_changeme:
				(error_no, error_str) = xxx_todo_changeme.args
				if error_no in (errno.EOPNOTSUPP, errno.ENODEV, errno.EPERM):
					return False
				else:
					print("error: ",error_no,error_str)
					return True
			else:
				return True

	def ok(self):
		self.cleanup()
		if self["menulist"].getCurrent()[1] == 'edit':
			if iNetwork.isWirelessInterface(self.iface):
				try:
					from Plugins.SystemPlugins.WirelessLan.plugin import WlanScan
				except ImportError:
					# without WiFi support the IP settings can still be changed
					self.session.openWithCallback(self.AdapterSetupClosed, AdapterSetup,self.iface)
				else:
					if self.queryWirelessDevice(self.iface):
						self.session.openWithCallback(self.AdapterSetupClosed, AdapterSetup,self.iface)
					else:
						self.showErrorMessage()	# Display Wlan not available Message
			else:
				self.session.openWithCallback(self.AdapterSetupClosed, AdapterSetup,self.iface)
		if self["menulist"].getCurrent()[1] == 'test':
			self.session.open(NetworkAdapterTest,self.iface)
		if self["menulist"].getCurrent()[1] == 'dns':
			self.session.open(NameserverSetup)
		if self["menulist"].getCurrent()[1] == 'scanwlan':
			try:
				from Plugins.SystemPlugins.WirelessLan.plugin import WlanScan
			except ImportError:
				self.session.open(MessageBox, self.missingwlanplugintxt, type = MessageBox.TYPE_INFO,timeout = 10 )
			else:
				if self.queryWirelessDevice(self.iface):
					self.session.openWithCallback(self.WlanScanClosed, WlanScan, self.iface)
				else:
					self.showErrorMessage()	# Display Wlan not available Message
		if self["menulist"].getCurrent()[1] == 'wlanstatus':
			try:
				from Plugins.SystemPlugins.WirelessLan.plugin import WlanStatus
			except ImportError:
				self.session.open(MessageBox, self.missingwlanplugintxt, type = MessageBox.TYPE_INFO,timeout = 10 )
			else:
				if self.queryWirelessDevice(self.iface):
					self.session.openWithCallback(self.WlanStatusClosed, WlanStatus,self.iface)
				else:
					self.showErrorMessage()	# Display Wlan not available Message
		if self["menulist"].getCurrent()[1] == 'hdswlanscan':
			self.openWlan("WlanScanScreen", self.AdapterSetupClosed)
		if self["menulist"].getCurrent()[1] == 'hdswlanstatus':
			self.openWlan("WlanStatusScreen", self.AdapterSetupClosed)
		if self["menulist"].getCurrent()[1] == 'hdswificanale':
			try:
				from Screens.HdsUnelteRetea import HdsWifiCanaleScreen
				self.session.open(HdsWifiCanaleScreen, self.iface)
			except Exception:
				from traceback import print_exc
				print_exc()
				self.session.open(MessageBox, _("The WiFi screen could not be opened."), type = MessageBox.TYPE_ERROR, timeout = 10)
		if self["menulist"].getCurrent()[1] == 'lanrestart':
			self.session.openWithCallback(self.restartLan, MessageBox, (_("Are you sure you want to restart your network interfaces?\n\n") + self.oktext ) )
		if self["menulist"].getCurrent()[1] == 'openwizard':
			try:
				from Plugins.SystemPlugins.NetworkWizard.NetworkWizard import NetworkWizard
			except ImportError:
				self.session.open(MessageBox, _("The NetworkWizard extension is not installed!\nPlease install it."), type = MessageBox.TYPE_INFO, timeout = 10)
			else:
				self.session.openWithCallback(self.AdapterSetupClosed, NetworkWizard, self.iface)
		if self["menulist"].getCurrent()[1][0] == 'extendedSetup':
			self.extended = self["menulist"].getCurrent()[1][2]
			self.extended(self.session, self.iface)
	
	def up(self):
		self["menulist"].up()
		self.loadDescription()

	def down(self):
		self["menulist"].down()
		self.loadDescription()

	def left(self):
		self["menulist"].pageUp()
		self.loadDescription()

	def right(self):
		self["menulist"].pageDown()
		self.loadDescription()

	def layoutFinished(self):
		idx = 0
		self["menulist"].moveToIndex(idx)
		self.loadDescription()

	def loadDescription(self):
		if self["menulist"].getCurrent()[1] == 'edit':
			self["description"].setText(_("Edit the network configuration of your receiver.\n" ) + self.oktext )
		if self["menulist"].getCurrent()[1] == 'test':
			self["description"].setText(_("Test the network configuration of your receiver.\n" ) + self.oktext )
		if self["menulist"].getCurrent()[1] == 'dns':
			self["description"].setText(_("Edit the Nameserver configuration of your receiver.\n" ) + self.oktext )
		if self["menulist"].getCurrent()[1] == 'scanwlan':
			self["description"].setText(_("Scan your network for wireless access points and connect to them using your selected wireless device.\n" ) + self.oktext )
		if self["menulist"].getCurrent()[1] == 'wlanstatus':
			self["description"].setText(_("Shows the state of your wireless LAN connection.\n" ) + self.oktext )
		if self["menulist"].getCurrent()[1] == 'hdswlanscan':
			self["description"].setText(_("Find WiFi networks and connect to one of them.\n") + self.oktext)
		if self["menulist"].getCurrent()[1] == 'hdswlanstatus':
			self["description"].setText(_("Show the state of the WiFi connection.\n") + self.oktext)
		if self["menulist"].getCurrent()[1] == 'hdswificanale':
			self["description"].setText(_("Câte rețele Wi-Fi sunt pe fiecare canal și ce canal e cel mai liber pentru router.") + "\n" + self.oktext)
		if self["menulist"].getCurrent()[1] == 'lanrestart':
			self["description"].setText(_("Restart your network connection and interfaces.\n" ) + self.oktext )
		if self["menulist"].getCurrent()[1] == 'openwizard':
			self["description"].setText(_("Use the Networkwizard to configure your Network\n" ) + self.oktext )
		if self["menulist"].getCurrent()[1][0] == 'extendedSetup':
			self["description"].setText(_(self["menulist"].getCurrent()[1][1]) + self.oktext )
		
	def updateStatusbar(self, data = None):
		self.mainmenu = self.genMainMenu()
		self["menulist"].l.setList(self.mainmenu)
		self["IFtext"].setText(_("Network:"))
		self["IF"].setText(iNetwork.getFriendlyAdapterName(self.iface))
		self["Statustext"].setText(_("Link:"))
		
		if iNetwork.isWirelessInterface(self.iface):
			try:
				from Plugins.SystemPlugins.WirelessLan.Wlan import iStatus
			except ImportError:
				self.wlanStatusbar()
			else:
				iStatus.getDataForInterface(self.iface,self.getInfoCB)
		else:
			iNetwork.getLinkState(self.iface,self.dataAvail)

	def doNothing(self):
		pass

	def hasWlanDriver(self):
		try:
			from Components import WlanTools
			return WlanTools.getWlanDriver(self.iface) is not None
		except Exception:
			return False

	def openWlan(self, name, callback):
		# a WiFi screen that cannot be built must not take the network menu down
		try:
			from Screens import WlanSetup
			self.session.openWithCallback(callback, getattr(WlanSetup, name), self.iface)
		except Exception:
			from traceback import print_exc
			print_exc()
			self.session.open(MessageBox, _("The WiFi screen could not be opened."), type = MessageBox.TYPE_ERROR, timeout = 10)

	def wlanStatusbar(self):
		# link icon from wpa_supplicant: connected or not
		try:
			from Components.WlanControl import WlanControl
			if getattr(self, "wlanControl", None) is None:
				self.wlanControl = WlanControl(self.iface)
				self.onClose.append(self.wlanControl.stop)
		except Exception:
			self["statuspic"].setPixmapNum(1)
			self["statuspic"].show()
			return

		def done(status):
			self["statuspic"].setPixmapNum(0 if status.get("wpa_state") == "COMPLETED" else 1)
			self["statuspic"].show()
		self.wlanControl.status(done)

	def genMainMenu(self):
		menu = []
		menu.append((_("Adapter settings"), "edit"))
		menu.append((_("Nameserver settings"), "dns"))
		menu.append((_("Network test"), "test"))
		menu.append((_("Restart network"), "lanrestart"))
		# WiFi screens of the image, when the adapter is a WiFi adapter
		if self.hasWlanDriver():
			menu.append((_("WiFi networks"), "hdswlanscan"))
			if iNetwork.getAdapterAttribute(self.iface, "up"):
				menu.append((_("WiFi status"), "hdswlanstatus"))
			# HDSatelit 0.4.4: how busy the WiFi channels are (Screens/HdsUnelteRetea.py), for this adapter
			menu.append((_("Cât de aglomerat e Wi-Fi-ul"), "hdswificanale"))

		self.extended = None
		self.extendedSetup = None		
		for p in plugins.getPlugins(PluginDescriptor.WHERE_NETWORKSETUP):
			callFnc = p.fnc["ifaceSupported"](self.iface)
			if callFnc is not None:
				self.extended = callFnc
				if "WlanPluginEntry" in p.fnc: # internally used only for WLAN Plugin
					menu.append((_("Scan Wireless Networks"), "scanwlan"))
					if iNetwork.getAdapterAttribute(self.iface, "up"):
						menu.append((_("Show WLAN Status"), "wlanstatus"))
				else:
					if "menuEntryName" in p.fnc:
						menuEntryName = p.fnc["menuEntryName"](self.iface)
					else:
						menuEntryName = _('Extended Setup...')
					if "menuEntryDescription" in p.fnc:
						menuEntryDescription = p.fnc["menuEntryDescription"](self.iface)
					else:
						menuEntryDescription = _('Extended Networksetup Plugin...')
					self.extendedSetup = ('extendedSetup',menuEntryDescription, self.extended)
					menu.append((menuEntryName,self.extendedSetup))					
			
		if os_path.exists(resolveFilename(SCOPE_PLUGINS, "SystemPlugins/NetworkWizard/networkwizard.xml")):
			menu.append((_("NetworkWizard"), "openwizard"))

		return menu

	def AdapterSetupClosed(self, *ret):
		if ret is not None and len(ret):
			if ret[0] == 'ok' and (iNetwork.isWirelessInterface(self.iface) and iNetwork.getAdapterAttribute(self.iface, "up") is True):
				try:
					from Plugins.SystemPlugins.WirelessLan.plugin import WlanStatus
				except ImportError:
					self.updateStatusbar()
				else:	
					if self.queryWirelessDevice(self.iface):
						self.session.openWithCallback(self.WlanStatusClosed, WlanStatus,self.iface)
					else:
						self.showErrorMessage()	# Display Wlan not available Message
			else:
				self.updateStatusbar()
		else:
			self.updateStatusbar()

	def WlanStatusClosed(self, *ret):
		if ret is not None and len(ret):
			from Plugins.SystemPlugins.WirelessLan.Wlan import iStatus
			iStatus.stopWlanConsole()
			self.updateStatusbar()

	def WlanScanClosed(self,*ret):
		if ret[0] is not None:
			self.session.openWithCallback(self.AdapterSetupClosed, AdapterSetup, self.iface,ret[0])
		else:
			from Plugins.SystemPlugins.WirelessLan.Wlan import iStatus
			iStatus.stopWlanConsole()
			self.updateStatusbar()
			
	def restartLan(self, ret = False):
		if (ret == True):
			HdsRetea.reporneste(self.getInterfacesDataAvail, iNetwork)
			self.restartLanRef = self.session.openWithCallback(self.restartfinishedCB, MessageBox, _("Please wait while your network is restarting..."), type = MessageBox.TYPE_INFO, enable_input = False)

	def getInterfacesDataAvail(self, data):
		if data is True:
			self.restartLanRef.close(True)

	def restartfinishedCB(self,data):
		if data is True:
			self.updateStatusbar()
			self.session.open(MessageBox, _("Finished restarting your network"), type = MessageBox.TYPE_INFO, timeout = 10, default = False)

	def dataAvail(self,data):
		self.LinkState = HdsRetea.legaturaEthtool(data)
		if self.LinkState == True:
			iNetwork.checkNetworkState(self.checkNetworkCB)
		else:
			self["statuspic"].setPixmapNum(1)
			self["statuspic"].show()			

	def showErrorMessage(self):
		self.session.open(MessageBox, self.errortext, type = MessageBox.TYPE_INFO,timeout = 10 )
		
	def cleanup(self):
		iNetwork.stopLinkStateConsole()
		iNetwork.stopDeactivateInterfaceConsole()
		iNetwork.stopActivateInterfaceConsole()
		iNetwork.stopPingConsole()
		try:
			from Plugins.SystemPlugins.WirelessLan.Wlan import iStatus
		except ImportError:
			pass
		else:
			iStatus.stopWlanConsole()

	def getInfoCB(self,data,status):
		self.LinkState = None
		if data is not None:
			if data is True:
				if status is not None:
					if status[self.iface]["essid"] == "off" or status[self.iface]["accesspoint"] == "Not-Associated" or status[self.iface]["accesspoint"] == False:
						self.LinkState = False
						self["statuspic"].setPixmapNum(1)
						self["statuspic"].show()
					else:
						self.LinkState = True
						iNetwork.checkNetworkState(self.checkNetworkCB)

	def checkNetworkCB(self,data):
		if iNetwork.getAdapterAttribute(self.iface, "up") is True:
			if self.LinkState is True:
				if data <= 2:
					self["statuspic"].setPixmapNum(0)
				else:
					self["statuspic"].setPixmapNum(1)
				self["statuspic"].show()	
			else:
				self["statuspic"].setPixmapNum(1)
				self["statuspic"].show()
		else:
			self["statuspic"].setPixmapNum(1)
			self["statuspic"].show()


class NetworkAdapterTest(Screen):	
	def __init__(self, session,iface):
		Screen.__init__(self, session)
		self.iface = iface
		self.oldInterfaceState = iNetwork.getAdapterAttribute(self.iface, "up")
		self.setLabels()
		self.onClose.append(self.cleanup)
		self.onHide.append(self.cleanup)
		
		self["updown_actions"] = NumberActionMap(["WizardActions","ShortcutActions"],
		{
			"ok": self.KeyOK,
			"blue": self.KeyOK,
			"up": lambda: self.updownhandler('up'),
			"down": lambda: self.updownhandler('down'),
		
		}, -2)
		
		self["shortcuts"] = ActionMap(["ShortcutActions","WizardActions"],
		{
			"red": self.cancel,
			"back": self.cancel,
		}, -2)
		self["infoshortcuts"] = ActionMap(["ShortcutActions","WizardActions"],
		{
			"red": self.closeInfo,
			"back": self.closeInfo,
		}, -2)
		self["shortcutsgreen"] = ActionMap(["ShortcutActions"],
		{
			"green": self.KeyGreen,
		}, -2)
		self["shortcutsgreen_restart"] = ActionMap(["ShortcutActions"],
		{
			"green": self.KeyGreenRestart,
		}, -2)
		self["shortcutsyellow"] = ActionMap(["ShortcutActions"],
		{
			"yellow": self.KeyYellow,
		}, -2)
		
		self["shortcutsgreen_restart"].setEnabled(False)
		self["updown_actions"].setEnabled(False)
		self["infoshortcuts"].setEnabled(False)
		self.onClose.append(self.delTimer)	
		self.onLayoutFinish.append(self.layoutFinished)
		self.steptimer = False
		self.nextstep = 0
		self.activebutton = 0
		self.nextStepTimer = eTimer()
		self.nextStepTimer.callback.append(self.nextStepTimerFire)

	def cancel(self):
		if self.oldInterfaceState is False:
			iNetwork.setAdapterAttribute(self.iface, "up", self.oldInterfaceState)
			iNetwork.deactivateInterface(self.iface)
		self.close()

	def closeInfo(self):
		self["shortcuts"].setEnabled(True)		
		self["infoshortcuts"].setEnabled(False)
		self["InfoText"].hide()
		self["InfoTextBorder"].hide()
		self["key_red"].setText(_("Close"))

	def delTimer(self):
		del self.steptimer
		del self.nextStepTimer

	def nextStepTimerFire(self):
		self.nextStepTimer.stop()
		self.steptimer = False
		self.runTest()

	def updownhandler(self,direction):
		if direction == 'up':
			if self.activebutton >=2:
				self.activebutton -= 1
			else:
				self.activebutton = 6
			self.setActiveButton(self.activebutton)
		if direction == 'down':
			if self.activebutton <=5:
				self.activebutton += 1
			else:
				self.activebutton = 1
			self.setActiveButton(self.activebutton)

	def setActiveButton(self,button):
		if button == 1:
			self["EditSettingsButton"].setPixmapNum(0)
			self["EditSettings_Text"].setForegroundColorNum(0)
			self["NetworkInfo"].setPixmapNum(0)
			self["NetworkInfo_Text"].setForegroundColorNum(1)
			self["AdapterInfo"].setPixmapNum(1) 		  # active
			self["AdapterInfo_Text"].setForegroundColorNum(2) # active
		if button == 2:
			self["AdapterInfo_Text"].setForegroundColorNum(1)
			self["AdapterInfo"].setPixmapNum(0)
			self["DhcpInfo"].setPixmapNum(0)
			self["DhcpInfo_Text"].setForegroundColorNum(1)
			self["NetworkInfo"].setPixmapNum(1) 		  # active
			self["NetworkInfo_Text"].setForegroundColorNum(2) # active
		if button == 3:
			self["NetworkInfo"].setPixmapNum(0)
			self["NetworkInfo_Text"].setForegroundColorNum(1)
			self["IPInfo"].setPixmapNum(0)
			self["IPInfo_Text"].setForegroundColorNum(1)
			self["DhcpInfo"].setPixmapNum(1) 		  # active
			self["DhcpInfo_Text"].setForegroundColorNum(2) 	  # active
		if button == 4:
			self["DhcpInfo"].setPixmapNum(0)
			self["DhcpInfo_Text"].setForegroundColorNum(1)
			self["DNSInfo"].setPixmapNum(0)
			self["DNSInfo_Text"].setForegroundColorNum(1)
			self["IPInfo"].setPixmapNum(1)			# active
			self["IPInfo_Text"].setForegroundColorNum(2)	# active		
		if button == 5:
			self["IPInfo"].setPixmapNum(0)
			self["IPInfo_Text"].setForegroundColorNum(1)
			self["EditSettingsButton"].setPixmapNum(0)
			self["EditSettings_Text"].setForegroundColorNum(0)
			self["DNSInfo"].setPixmapNum(1)			# active
			self["DNSInfo_Text"].setForegroundColorNum(2)	# active
		if button == 6:
			self["DNSInfo"].setPixmapNum(0)
			self["DNSInfo_Text"].setForegroundColorNum(1)
			self["EditSettingsButton"].setPixmapNum(1) 	   # active
			self["EditSettings_Text"].setForegroundColorNum(2) # active
			self["AdapterInfo"].setPixmapNum(0)
			self["AdapterInfo_Text"].setForegroundColorNum(1)
			
	def runTest(self):
		next = self.nextstep
		if next == 0:
			self.doStep1()
		elif next == 1:
			self.doStep2()
		elif next == 2:
			self.doStep3()
		elif next == 3:
			self.doStep4()
		elif next == 4:
			self.doStep5()
		elif next == 5:
			self.doStep6()
		self.nextstep += 1

	def doStep1(self):
		self.steptimer = True
		self.nextStepTimer.start(3000)
		self["key_yellow"].setText(_("Stop test"))

	def doStep2(self):
		self["Adapter"].setText(iNetwork.getFriendlyAdapterName(self.iface))
		self["Adapter"].setForegroundColorNum(2)
		self["Adaptertext"].setForegroundColorNum(1)
		self["AdapterInfo_Text"].setForegroundColorNum(1)
		self["AdapterInfo_OK"].show()
		self.steptimer = True
		self.nextStepTimer.start(3000)

	def doStep3(self):
		self["Networktext"].setForegroundColorNum(1)
		self["Network"].setText(_("Please wait..."))
		self.getLinkState(self.iface)
		self["NetworkInfo_Text"].setForegroundColorNum(1)
		self.steptimer = True
		self.nextStepTimer.start(3000)

	def doStep4(self):
		self["Dhcptext"].setForegroundColorNum(1)
		if iNetwork.getAdapterAttribute(self.iface, 'dhcp') is True:
			self["Dhcp"].setForegroundColorNum(2)
			self["Dhcp"].setText(_("enabled"))
			self["DhcpInfo_Check"].setPixmapNum(0)
		else:
			self["Dhcp"].setForegroundColorNum(1)
			self["Dhcp"].setText(_("disabled"))
			self["DhcpInfo_Check"].setPixmapNum(1)
		self["DhcpInfo_Check"].show()
		self["DhcpInfo_Text"].setForegroundColorNum(1)
		self.steptimer = True
		self.nextStepTimer.start(3000)

	def doStep5(self):
		self["IPtext"].setForegroundColorNum(1)
		self["IP"].setText(_("Please wait..."))
		iNetwork.checkNetworkState(self.NetworkStatedataAvail)

	def doStep6(self):
		self.steptimer = False
		self.nextStepTimer.stop()
		self["DNStext"].setForegroundColorNum(1)
		self["DNS"].setText(_("Please wait..."))
		iNetwork.checkDNSLookup(self.DNSLookupdataAvail)

	def KeyGreen(self):
		self["shortcutsgreen"].setEnabled(False)
		self["shortcutsyellow"].setEnabled(True)
		self["updown_actions"].setEnabled(False)
		self["key_yellow"].setText("")
		self["key_green"].setText("")
		self.steptimer = True
		self.nextStepTimer.start(1000)

	def KeyGreenRestart(self):
		self.nextstep = 0
		self.layoutFinished()
		self["Adapter"].setText((""))
		self["Network"].setText((""))
		self["Dhcp"].setText((""))
		self["IP"].setText((""))
		self["DNS"].setText((""))
		self["AdapterInfo_Text"].setForegroundColorNum(0)
		self["NetworkInfo_Text"].setForegroundColorNum(0)
		self["DhcpInfo_Text"].setForegroundColorNum(0)
		self["IPInfo_Text"].setForegroundColorNum(0)
		self["DNSInfo_Text"].setForegroundColorNum(0)
		self["shortcutsgreen_restart"].setEnabled(False)
		self["shortcutsgreen"].setEnabled(False)
		self["shortcutsyellow"].setEnabled(True)
		self["updown_actions"].setEnabled(False)
		self["key_yellow"].setText("")
		self["key_green"].setText("")
		self.steptimer = True
		self.nextStepTimer.start(1000)

	def KeyOK(self):
		self["infoshortcuts"].setEnabled(True)
		self["shortcuts"].setEnabled(False)
		if self.activebutton == 1: # Adapter Check
			self["InfoText"].setText(_("This test detects your configured LAN-Adapter."))
			self["InfoTextBorder"].show()
			self["InfoText"].show()
			self["key_red"].setText(_("Back"))
		if self.activebutton == 2: #LAN Check
			self["InfoText"].setText(_("This test checks whether a network cable is connected to your LAN-Adapter.\nIf you get a \"disconnected\" message:\n- verify that a network cable is attached\n- verify that the cable is not broken"))
			self["InfoTextBorder"].show()
			self["InfoText"].show()
			self["key_red"].setText(_("Back"))
		if self.activebutton == 3: #DHCP Check
			self["InfoText"].setText(_("This test checks whether your LAN Adapter is set up for automatic IP Address configuration with DHCP.\nIf you get a \"disabled\" message:\n - then your LAN Adapter is configured for manual IP Setup\n- verify thay you have entered correct IP informations in the AdapterSetup dialog.\nIf you get an \"enabeld\" message:\n-verify that you have a configured and working DHCP Server in your network."))
			self["InfoTextBorder"].show()
			self["InfoText"].show()
			self["key_red"].setText(_("Back"))
		if self.activebutton == 4: # IP Check
			self["InfoText"].setText(_("This test checks whether a valid IP Address is found for your LAN Adapter.\nIf you get a \"unconfirmed\" message:\n- no valid IP Address was found\n- please check your DHCP, cabling and adapter setup"))
			self["InfoTextBorder"].show()
			self["InfoText"].show()
			self["key_red"].setText(_("Back"))
		if self.activebutton == 5: # DNS Check
			self["InfoText"].setText(_("This test checks for configured Nameservers.\nIf you get a \"unconfirmed\" message:\n- please check your DHCP, cabling and Adapter setup\n- if you configured your Nameservers manually please verify your entries in the \"Nameserver\" Configuration"))
			self["InfoTextBorder"].show()
			self["InfoText"].show()
			self["key_red"].setText(_("Back"))
		if self.activebutton == 6: # Edit Settings
			self.session.open(AdapterSetup,self.iface)

	def KeyYellow(self):
		self.nextstep = 0
		self["shortcutsgreen_restart"].setEnabled(True)
		self["shortcutsgreen"].setEnabled(False)
		self["shortcutsyellow"].setEnabled(False)
		self["key_green"].setText(_("Restart test"))
		self["key_yellow"].setText("")
		self.steptimer = False
		self.nextStepTimer.stop()

	def layoutFinished(self):
		self.setTitle(_("Network test: ") + iNetwork.getFriendlyAdapterName(self.iface) )
		self["shortcutsyellow"].setEnabled(False)
		self["AdapterInfo_OK"].hide()
		self["NetworkInfo_Check"].hide()
		self["DhcpInfo_Check"].hide()
		self["IPInfo_Check"].hide()
		self["DNSInfo_Check"].hide()
		self["EditSettings_Text"].hide()
		self["EditSettingsButton"].hide()
		self["InfoText"].hide()
		self["InfoTextBorder"].hide()
		self["key_yellow"].setText("")

	def setLabels(self):
		self["Adaptertext"] = MultiColorLabel(_("LAN Adapter"))
		self["Adapter"] = MultiColorLabel()
		self["AdapterInfo"] = MultiPixmap()
		self["AdapterInfo_Text"] = MultiColorLabel(_("Show Info"))
		self["AdapterInfo_OK"] = Pixmap()
		
		if self.iface in iNetwork.wlan_interfaces:
			self["Networktext"] = MultiColorLabel(_("Wireless Network"))
		else:
			self["Networktext"] = MultiColorLabel(_("Local Network"))
		
		self["Network"] = MultiColorLabel()
		self["NetworkInfo"] = MultiPixmap()
		self["NetworkInfo_Text"] = MultiColorLabel(_("Show Info"))
		self["NetworkInfo_Check"] = MultiPixmap()
		
		self["Dhcptext"] = MultiColorLabel(_("DHCP"))
		self["Dhcp"] = MultiColorLabel()
		self["DhcpInfo"] = MultiPixmap()
		self["DhcpInfo_Text"] = MultiColorLabel(_("Show Info"))
		self["DhcpInfo_Check"] = MultiPixmap()
		
		self["IPtext"] = MultiColorLabel(_("IP Address"))
		self["IP"] = MultiColorLabel()
		self["IPInfo"] = MultiPixmap()
		self["IPInfo_Text"] = MultiColorLabel(_("Show Info"))
		self["IPInfo_Check"] = MultiPixmap()
		
		self["DNStext"] = MultiColorLabel(_("Nameserver"))
		self["DNS"] = MultiColorLabel()
		self["DNSInfo"] = MultiPixmap()
		self["DNSInfo_Text"] = MultiColorLabel(_("Show Info"))
		self["DNSInfo_Check"] = MultiPixmap()
		
		self["EditSettings_Text"] = MultiColorLabel(_("Edit settings"))
		self["EditSettingsButton"] = MultiPixmap()
		
		self["key_red"] = StaticText(_("Close"))
		self["key_green"] = StaticText(_("Start test"))
		self["key_yellow"] = StaticText(_("Stop test"))
		
		self["InfoTextBorder"] = Pixmap()
		self["InfoText"] = Label()

	def getLinkState(self,iface):
		if iface in iNetwork.wlan_interfaces:
			try:
				from Plugins.SystemPlugins.WirelessLan.Wlan import iStatus
			except:
				# the image has no WirelessLan plugin: the WiFi link comes from wpa_supplicant, like the status bar of
				# the adapter menu and the network test of the web page /retea (before, WiFi was always "disconnected")
				self.wlanLinkState(iface)
			else:
				iStatus.getDataForInterface(self.iface,self.getInfoCB)
		else:
			iNetwork.getLinkState(iface,self.LinkStatedataAvail)

	def wlanLinkState(self, iface):
		try:
			from Components.WlanControl import WlanControl
			if getattr(self, "wlanControl", None) is None:
				self.wlanControl = WlanControl(iface)
				self.onClose.append(self.wlanControl.stop)
		except Exception:
			self.showLinkState(False)
			return
		self.wlanControl.status(lambda status: self.showLinkState(status.get("wpa_state") == "COMPLETED"))

	def showLinkState(self, connected):
		if connected:
			self["Network"].setForegroundColorNum(2)
			self["Network"].setText(_("connected"))
			self["NetworkInfo_Check"].setPixmapNum(0)
		else:
			self["Network"].setForegroundColorNum(1)
			self["Network"].setText(_("disconnected"))
			self["NetworkInfo_Check"].setPixmapNum(1)
		self["NetworkInfo_Check"].show()

	def LinkStatedataAvail(self,data):
		self.showLinkState(HdsRetea.legaturaEthtool(data) is True)

	def NetworkStatedataAvail(self,data):
		if HdsRetea.confirmat(data):
			self["IP"].setForegroundColorNum(2)
			self["IP"].setText(_("confirmed"))
			self["IPInfo_Check"].setPixmapNum(0)
		else:
			self["IP"].setForegroundColorNum(1)
			self["IP"].setText(_("unconfirmed"))
			self["IPInfo_Check"].setPixmapNum(1)
		self["IPInfo_Check"].show()
		self["IPInfo_Text"].setForegroundColorNum(1)		
		self.steptimer = True
		self.nextStepTimer.start(3000)		
		
	def DNSLookupdataAvail(self,data):
		if HdsRetea.confirmat(data):
			self["DNS"].setForegroundColorNum(2)
			self["DNS"].setText(_("confirmed"))
			self["DNSInfo_Check"].setPixmapNum(0)
		else:
			self["DNS"].setForegroundColorNum(1)
			self["DNS"].setText(_("unconfirmed"))
			self["DNSInfo_Check"].setPixmapNum(1)
		self["DNSInfo_Check"].show()
		self["DNSInfo_Text"].setForegroundColorNum(1)
		self["EditSettings_Text"].show()
		self["EditSettingsButton"].setPixmapNum(1)
		self["EditSettings_Text"].setForegroundColorNum(2) # active
		self["EditSettingsButton"].show()
		self["key_yellow"].setText("")
		self["key_green"].setText(_("Restart test"))
		self["shortcutsgreen"].setEnabled(False)
		self["shortcutsgreen_restart"].setEnabled(True)
		self["shortcutsyellow"].setEnabled(False)
		self["updown_actions"].setEnabled(True)
		self.activebutton = 6

	def getInfoCB(self,data,status):
		if data is not None:
			if data is True:
				if status is not None:
					if status[self.iface]["essid"] == "off" or status[self.iface]["accesspoint"] == "Not-Associated" or status[self.iface]["accesspoint"] == False:
						self["Network"].setForegroundColorNum(1)
						self["Network"].setText(_("disconnected"))
						self["NetworkInfo_Check"].setPixmapNum(1)
						self["NetworkInfo_Check"].show()
					else:
						self["Network"].setForegroundColorNum(2)
						self["Network"].setText(_("connected"))
						self["NetworkInfo_Check"].setPixmapNum(0)
						self["NetworkInfo_Check"].show()
						
	def cleanup(self):
		iNetwork.stopLinkStateConsole()
		iNetwork.stopDNSConsole()
		try:
			from Plugins.SystemPlugins.WirelessLan.Wlan import iStatus
		except ImportError:
			pass
		else:
			iStatus.stopWlanConsole()

