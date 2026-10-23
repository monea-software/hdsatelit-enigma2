# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsWlan.py: logica ecranelor Wi-Fi (Screens/WlanSetup.py), aceeasi pe televizor si in interfata web
# (Plugins/Extensions/HdsWebControl/retea_web.py, pagina /retea):
# - textele securitatii, ale motivelor de refuz al parolei si ale starii legaturii (securityText, reasonText, stateText),
#   randurile ecranului "WiFi status" (statusLines) si reteaua la care e legata placa acum (connectedSsid);
# - ConectareWlan: conectarea la o retea (inainte in WlanConnectScreen): setarile vechi tinute minte, blocul retelei
#   scris in wpa_supplicant.conf, placa pornita din nou, asteptarea legaturii (30 s) si a adresei IP (20 s) si, la esec
#   sau la renuntare, setarile vechi puse inapoi. Ecranul si pagina web primesc textul de aratat (`show`) si sfarsitul
#   (`finished(result)`); parola sta numai pana se face blocul retelei, nu se scrie in jurnal si nu se arata.
# Comenzile le dau WlanControl (wpa_cli, wpa_supplicant) si iNetwork (ifdown / ifup), fara shell, pe consola enigma2.
#
# Modulul nu importa nimic din enigma2 la incarcare (WlanControl, eTimer si iNetwork se iau la folosire), ca probele de
# pe PC sa-l incarce cu module false.

import os

from Components import WlanTools

INTERFACES_FILE = "/etc/network/interfaces"
ASSOCIATE_TIMEOUT = 30
ADDRESS_TIMEOUT = 20
POLL_MS = 1000


def securityText(security):
	return {
		WlanTools.SECURITY_OPEN: _("Open"),
		WlanTools.SECURITY_OWE: _("Open, encrypted"),
		WlanTools.SECURITY_WEP: _("WEP, not supported"),
		WlanTools.SECURITY_WPA: "WPA",
		WlanTools.SECURITY_WPA2: "WPA2",
		WlanTools.SECURITY_WPA2_WPA3: "WPA2/WPA3",
		WlanTools.SECURITY_WPA3: "WPA3",
		WlanTools.SECURITY_ENTERPRISE: _("Enterprise, not supported"),
	}.get(security, security)


def reasonText(reason):
	return {
		"This kind of network security is not supported": _("This kind of network security is not supported"),
		"The password may only contain letters, digits and the usual signs": _("The password may only contain letters, digits and the usual signs"),
		"The password must have at least 8 characters": _("The password must have at least 8 characters"),
		"The password may have at most 63 characters": _("The password may have at most 63 characters"),
		"For WPA3 the password may not contain quotes or backslashes": _("For WPA3 the password may not contain quotes or backslashes"),
	}.get(reason, reason)


def stateText(state):
	return {
		"COMPLETED": _("connected"),
		"SCANNING": _("searching"),
		"ASSOCIATING": _("connecting"),
		"ASSOCIATED": _("connecting"),
		"AUTHENTICATING": _("connecting"),
		"4WAY_HANDSHAKE": _("checking the password"),
		"GROUP_HANDSHAKE": _("checking the password"),
		"DISCONNECTED": _("not connected"),
		"INACTIVE": _("not connected"),
		"INTERFACE_DISABLED": _("adapter switched off"),
	}.get(state, state or _("unknown"))


# securitatile pe care le poate avea o retea ascunsa, in ordinea alegerii de pe televizor
HIDDEN_SECURITY = (WlanTools.SECURITY_WPA2, WlanTools.SECURITY_WPA2_WPA3, WlanTools.SECURITY_WPA3, WlanTools.SECURITY_WPA,
	WlanTools.SECURITY_OPEN)


def connectedSsid(status):
	"""SSID-ul (octeti) retelei la care e legata placa, sau None (din wpa_cli status)."""
	if status.get("wpa_state") == "COMPLETED":
		return WlanTools.decodeSsid(status.get("ssid", ""))
	return None


def nivelProc(iface, cale="/proc/net/wireless"):
	"""Puterea semnalului (dBm) din /proc/net/wireless, pentru placile care nu raspund la signal_poll; None altfel."""
	return WlanTools.procWirelessLevel(iface, cale)


def statusLines(status, values, nivel=None):
	"""Randurile ecranului "WiFi status" din wpa_cli status si signal_poll. `nivel`: dBm din /proc/net/wireless (nivelProc),
	folosit cand signal_poll nu da RSSI (unele drivere raspund FAIL): puterea semnalului se vede si atunci."""
	lines = []
	if status.get("ssid"):
		lines.append(_("Network: %s") % WlanTools.ssidName(WlanTools.decodeSsid(status["ssid"])))
	lines.append(_("State: %s") % stateText(status.get("wpa_state", "")))
	rssi = values.get("RSSI", "")
	if not rssi.lstrip("-").isdigit() and nivel is not None and status.get("wpa_state") == "COMPLETED":
		rssi = str(int(nivel))
	if rssi.lstrip("-").isdigit():
		lines.append(_("Signal: %s dBm (%d%%)") % (rssi, WlanTools.signalPercent(int(rssi))))
	if values.get("LINKSPEED"):
		lines.append(_("Speed: %s Mbit/s") % values["LINKSPEED"])
	frequency = status.get("freq") or values.get("FREQUENCY") or ""
	if frequency.isdigit() and WlanTools.band(int(frequency)):
		lines.append(_("Band: %s GHz") % WlanTools.band(int(frequency)))
	if status.get("key_mgmt"):
		lines.append(_("Security: %s") % status["key_mgmt"])
	if status.get("ip_address"):
		lines.append(_("IP address: %s") % status["ip_address"])
	return lines


def readBytes(path):
	try:
		with open(path, "rb") as f:
			return f.read()
	except (IOError, OSError):
		return None


def writeBack(path, data, private):
	"""puts a file back exactly as it was (None = it did not exist); True on success"""
	try:
		if data is None:
			if os.path.exists(path):
				os.unlink(path)
			return True
		tmp = path + ".tmp"
		fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600 if private else 0o644)
		try:
			rest = data
			while rest:
				rest = rest[os.write(fd, rest):]
			os.fsync(fd)
		finally:
			os.close(fd)
		os.replace(tmp, path)
		return True
	except (IOError, OSError) as err:
		print("[WlanSetup] restoring %s failed: %s" % (path, err.strerror or err))
		return False


class ConectareWlan(object):
	"""Conectarea placii `iface` la reteaua `ssid` (octeti). `show(text)` primeste fiecare text de aratat, `finished(result)`
	sfarsitul (True conectat, False nu; setarile vechi sunt atunci inapoi). `running` e True cat se lucreaza, `result`
	e None pana la sfarsit. Pentru probe: `network` (iNetwork), `control` (fabrica WlanControl), `timer` (fabrica eTimer),
	`interfaces` (calea lui /etc/network/interfaces)."""

	def __init__(self, iface, ssid, security, password, hidden=False, show=None, finished=None, network=None,
			control=None, timer=None, interfaces=None):
		if control is None:
			from Components.WlanControl import WlanControl as control
		if timer is None:
			from enigma import eTimer as timer
		self.iface = iface
		self.ssid = ssid
		self.name = WlanTools.ssidName(ssid)
		self.security = security
		self.password = password
		self.hidden = hidden
		self.show = show or (lambda text: None)
		self.finished = finished or (lambda result: None)
		self.network = network
		self.interfaces = interfaces or INTERFACES_FILE
		self.result = None
		self.running = False
		self.closed = False
		self.pending = False
		self.phase = ""
		self.seconds = 0
		self.reason = ""
		self.text = ""
		self.address = ""
		self.backup = {}
		self.oldUp = self.oldDhcp = self.oldConfigStrings = None
		self.control = control(iface)
		self.timer = timer()
		self.timer.callback.append(self.poll)

	def net(self):
		if self.network is None:
			from Components.Network import iNetwork
			self.network = iNetwork
		return self.network

	def setText(self, text):
		self.text = text
		self.show(text)

	def stop(self):
		"""Ecranul s-a inchis (sau pagina web a pornit alta conectare): nimic nu mai continua."""
		self.closed = True
		self.timer.stop()
		self.control.stop()

	def begin(self):
		net = self.net()
		self.running = True
		self.setText(_("Saving the settings for %s...") % self.name)
		self.oldUp = net.getAdapterAttribute(self.iface, "up")
		self.oldDhcp = net.getAdapterAttribute(self.iface, "dhcp")
		self.oldConfigStrings = net.getAdapterAttribute(self.iface, "configStrings")
		for path in (WlanTools.SUPPLICANT_CONF, self.interfaces):
			self.backup[path] = readBytes(path)
		password, self.password = self.password, None
		try:
			block = WlanTools.networkBlock(self.ssid, self.security, password, self.hidden)
		except ValueError as err:
			self.fail(reasonText(str(err)), restore=False)
			return
		del password
		old = self.backup[WlanTools.SUPPLICANT_CONF]
		text = WlanTools.updateConf(old.decode("utf-8", "replace") if old else "", self.ssid, block)
		if not WlanTools.writeConfAtomic(WlanTools.SUPPLICANT_CONF, text):
			self.fail(_("The WiFi settings could not be saved."), restore=False)
			return
		driver = WlanTools.getWlanDriver(self.iface) or "nl80211"
		net.setAdapterAttribute(self.iface, "up", True)
		if self.oldDhcp is None:
			net.setAdapterAttribute(self.iface, "dhcp", True)
		net.setAdapterAttribute(self.iface, "configStrings", WlanTools.interfaceLines(driver))
		try:
			net.writeNetworkConfig()
		except (IOError, OSError):
			self.fail(_("The network settings could not be saved."))
			return
		self.setText(_("Starting WiFi on %s...") % self.iface)
		# a supplicant started for scanning must go before ifup starts the one from the settings
		net.deactivateInterface(self.iface, self.deactivated)

	def deactivated(self, ok=True):
		if self.closed or not self.running:
			return
		self.net().activateInterface(self.iface, self.activated)

	def activated(self, ok=True):
		if self.closed or not self.running:
			return
		self.phase = "associate"
		self.seconds = 0
		self.timer.start(POLL_MS, False)

	def poll(self):
		if self.pending:
			return
		self.seconds += 1
		self.pending = True
		self.control.status(self.gotStatus)

	def gotStatus(self, status):
		self.pending = False
		if self.closed or not self.running:
			return
		state = status.get("wpa_state", "")
		if self.phase == "associate":
			if state == "COMPLETED":
				self.phase = "address"
				self.seconds = 0
			elif self.seconds >= ASSOCIATE_TIMEOUT:
				self.fail(_("Could not connect to %s. Check the password and the signal.") % self.name)
				return
			else:
				self.setText(_("Connecting to %s (%d s)...") % (self.name, self.seconds))
				return
		address = status.get("ip_address")
		if address and state == "COMPLETED":
			self.succeed(address)
		elif self.seconds >= ADDRESS_TIMEOUT:
			self.fail(_("Connected to %s, but no IP address was received.") % self.name)
		else:
			self.setText(_("Connected to %s, waiting for an IP address (%d s)...") % (self.name, self.seconds))

	def succeed(self, address):
		self.running = False
		self.timer.stop()
		self.result = True
		self.address = address
		self.net().getInterfaces()
		self.setText(_("Connected to %s.\nIP address: %s") % (self.name, address))
		self.finished(True)

	def cancel(self):
		"""Rosu cat se lucreaza: setarile vechi inapoi."""
		if self.running:
			self.fail(_("Cancelled."))

	def fail(self, reason, restore=True):
		self.running = False
		self.timer.stop()
		self.reason = reason
		if not restore:
			self.finishFailed()
			return
		self.setText(reason + "\n" + _("Restoring the previous settings..."))
		ok = True
		for path, data in self.backup.items():
			ok = writeBack(path, data, path == WlanTools.SUPPLICANT_CONF) and ok
		self.restoreAttribute("up", self.oldUp)
		self.restoreAttribute("dhcp", self.oldDhcp)
		self.restoreAttribute("configStrings", self.oldConfigStrings)
		if not ok:
			self.reason += "\n" + _("The previous settings could not be written back completely.")
		self.net().deactivateInterface(self.iface, self.restoredDown)

	def restoreAttribute(self, name, value):
		if value is None:
			self.net().removeAdapterAttribute(self.iface, name)
		else:
			self.net().setAdapterAttribute(self.iface, name, value)

	def restoredDown(self, ok=True):
		if self.closed:
			return
		if self.oldUp is True:
			self.net().activateInterface(self.iface, self.restoredUp)
		else:
			self.restoredUp()

	def restoredUp(self, ok=True):
		if self.closed:
			return
		self.finishFailed(_("The previous settings are back."))

	def finishFailed(self, extra=""):
		self.result = False
		self.setText(self.reason + ("\n" + extra if extra else ""))
		self.finished(False)
