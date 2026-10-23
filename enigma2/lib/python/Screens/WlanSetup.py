# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# WiFi screens for HDSatelit Image: network list, connection with revert, status.
# Every command runs through WlanControl or iNetwork without blocking;
# the password lives only until the config block is built and is never printed or shown in a message.
from enigma import eTimer
from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Screens.ChoiceBox import ChoiceBox
from Screens.VirtualKeyBoard import VirtualKeyBoard
from Components.ActionMap import ActionMap
from Components.MenuList import MenuList
from Components.Sources.StaticText import StaticText
from Components.Network import iNetwork
from Components import WlanTools
from Components import HdsWlan
from Components.WlanControl import WlanControl
from Tools.BoundFunction import boundFunction
from Tools.ScaledSkin import scaledSkin

STATUS_REFRESH_MS = 2000

# the texts, the status lines and the connection itself are shared with the web interface (/retea):
# Components/HdsWlan.py
securityText = HdsWlan.securityText
reasonText = HdsWlan.reasonText
stateText = HdsWlan.stateText


class WlanScanScreen(Screen):
	SKIN = """
		<screen name="WlanScanScreen" position="center,center" size="1100,620" title="WiFi">
			<widget name="list" position="30,20" size="1040,480" font="Regular;30" itemHeight="48" scrollbarMode="showOnDemand" />
			<widget source="status" render="Label" position="30,510" size="1040,40" font="Regular;26" transparent="1" />
			<widget source="key_red" render="Label" position="30,565" size="250,40" font="Regular;26" foregroundColor="#ff5050" transparent="1" />
			<widget source="key_green" render="Label" position="290,565" size="250,40" font="Regular;26" foregroundColor="#50d050" transparent="1" />
			<widget source="key_yellow" render="Label" position="550,565" size="250,40" font="Regular;26" foregroundColor="#e0d040" transparent="1" />
			<widget source="key_blue" render="Label" position="810,565" size="260,40" font="Regular;26" foregroundColor="#5090ff" transparent="1" />
		</screen>"""

	def __init__(self, session, iface):
		Screen.__init__(self, session)
		self.skin = scaledSkin(self.SKIN)
		self.skinName = ["WlanScanScreen"]
		self.iface = iface
		self.networks = []
		self.control = WlanControl(iface)
		self["list"] = MenuList([])
		self["status"] = StaticText(_("Searching for networks..."))
		self["key_red"] = StaticText(_("Close"))
		self["key_green"] = StaticText(_("Connect"))
		self["key_yellow"] = StaticText(_("Search again"))
		self["key_blue"] = StaticText(_("Hidden network"))
		self["actions"] = ActionMap(["OkCancelActions", "ColorActions"],
			{
				"ok": self.connect,
				"cancel": self.close,
				"red": self.close,
				"green": self.connect,
				"yellow": self.rescan,
				"blue": self.hiddenNetwork,
			}, -1)
		self.onLayoutFinish.append(self.layoutFinished)
		self.onClose.append(self.control.stop)

	def layoutFinished(self):
		self.setTitle(_("WiFi networks"))
		self.rescan()

	def rescan(self):
		self["status"].setText(_("Searching for networks..."))
		self.control.ensureSupplicant(self.supplicantReady)

	def supplicantReady(self, ok):
		if not ok:
			self["status"].setText(_("The WiFi adapter could not be started."))
			return
		self.control.scan(self.scanned)

	def scanned(self, networks):
		if networks is None:
			self["status"].setText(_("Searching failed. Press yellow to try again."))
			return
		self.networks = networks
		self.control.status(self.showList)

	def showList(self, status):
		connected = HdsWlan.connectedSsid(status)
		entries = []
		for network in self.networks:
			mark = "* " if network["ssid"] == connected else ""
			bands = "/".join(network["bands"])
			line = "%s%s   %s   %d%%%s" % (mark, network["name"], securityText(network["security"]), network["percent"],
				"   %s GHz" % bands if bands else "")
			entries.append((line, network))
		self["list"].setList(entries)
		if entries:
			self["status"].setText(_("Networks found: %d") % len(entries))
		else:
			self["status"].setText(_("No networks found. Press yellow to try again."))

	def connect(self):
		current = self["list"].getCurrent()
		if current is None:
			return
		network = current[1]
		self.askPassword(network["ssid"], network["security"], False)

	def hiddenNetwork(self):
		self.session.openWithCallback(self.hiddenName, VirtualKeyBoard, title=_("Name of the hidden network"), text="")

	def hiddenName(self, name):
		if not name:
			return
		ssid = name.encode("utf-8")
		if len(ssid) > 32:
			self.session.open(MessageBox, _("A network name may have at most 32 bytes."), MessageBox.TYPE_ERROR, timeout=10)
			return
		choices = [(securityText(x), x) for x in HdsWlan.HIDDEN_SECURITY]
		self.session.openWithCallback(boundFunction(self.hiddenSecurity, ssid), ChoiceBox,
			title=_("Security of the hidden network"), list=choices)

	def hiddenSecurity(self, ssid, choice):
		if choice:
			self.askPassword(ssid, choice[1], True)

	def askPassword(self, ssid, security, hidden):
		if security not in WlanTools.SUPPORTED_SECURITY:
			self.session.open(MessageBox, reasonText("This kind of network security is not supported"), MessageBox.TYPE_ERROR, timeout=10)
			return
		if security in (WlanTools.SECURITY_OPEN, WlanTools.SECURITY_OWE):
			self.startConnect(ssid, security, "", hidden)
			return
		self.session.openWithCallback(boundFunction(self.passwordEntered, ssid, security, hidden), VirtualKeyBoard,
			title=_("Password for %s") % WlanTools.ssidName(ssid), text="")

	def passwordEntered(self, ssid, security, hidden, password):
		if password is None:
			return
		reason = WlanTools.checkPassword(security, password)
		if reason:
			self.session.open(MessageBox, reasonText(reason), MessageBox.TYPE_ERROR, timeout=10)
			return
		self.startConnect(ssid, security, password, hidden)

	def startConnect(self, ssid, security, password, hidden):
		self.control.stop()
		self.control = WlanControl(self.iface)
		self.session.openWithCallback(self.connectDone, WlanConnectScreen, self.iface, ssid, security, password, hidden)

	def connectDone(self, result=None):
		if result:
			self.close(True)
		else:
			self.rescan()


class WlanConnectScreen(Screen):
	SKIN = """
		<screen name="WlanConnectScreen" position="center,center" size="1000,300" title="WiFi">
			<widget source="text" render="Label" position="30,20" size="940,200" font="Regular;30" valign="center" transparent="1" />
			<widget source="key_red" render="Label" position="30,245" size="400,40" font="Regular;26" foregroundColor="#ff5050" transparent="1" />
		</screen>"""

	def __init__(self, session, iface, ssid, security, password, hidden=False):
		Screen.__init__(self, session)
		self.skin = scaledSkin(self.SKIN)
		self.skinName = ["WlanConnectScreen"]
		self.iface = iface
		self["text"] = StaticText("")
		self["key_red"] = StaticText(_("Cancel"))
		self.connection = HdsWlan.ConectareWlan(iface, ssid, security, password, hidden,
			show=self["text"].setText, finished=self.connectionFinished)
		self["actions"] = ActionMap(["OkCancelActions", "ColorActions"],
			{
				"ok": self.keyOk,
				"cancel": self.keyCancel,
				"red": self.keyCancel,
			}, -1)
		self.onLayoutFinish.append(self.begin)
		self.onClose.append(self.cleanup)

	def cleanup(self):
		self.connection.stop()

	def begin(self):
		self.setTitle(_("WiFi connection"))
		self.connection.begin()

	def connectionFinished(self, result):
		self["key_red"].setText(_("Close"))

	def keyOk(self):
		if self.connection.result is not None:
			self.close(self.connection.result)

	def keyCancel(self):
		if self.connection.running:
			self.connection.cancel()
		elif self.connection.result is not None:
			self.close(self.connection.result)


class WlanStatusScreen(Screen):
	SKIN = """
		<screen name="WlanStatusScreen" position="center,center" size="1000,460" title="WiFi">
			<widget source="info" render="Label" position="30,20" size="940,370" font="Regular;30" transparent="1" />
			<widget source="key_red" render="Label" position="30,405" size="400,40" font="Regular;26" foregroundColor="#ff5050" transparent="1" />
		</screen>"""

	def __init__(self, session, iface):
		Screen.__init__(self, session)
		self.skin = scaledSkin(self.SKIN)
		self.skinName = ["WlanStatusScreen"]
		self.iface = iface
		self.pending = False
		self.control = WlanControl(iface)
		self.timer = eTimer()
		self.timer.callback.append(self.refresh)
		self["info"] = StaticText(_("Reading the WiFi state..."))
		self["key_red"] = StaticText(_("Close"))
		self["actions"] = ActionMap(["OkCancelActions", "ColorActions"],
			{
				"ok": self.close,
				"cancel": self.close,
				"red": self.close,
			}, -1)
		self.onLayoutFinish.append(self.layoutFinished)
		self.onClose.append(self.cleanup)

	def layoutFinished(self):
		self.setTitle(_("WiFi status"))
		self.refresh()
		self.timer.start(STATUS_REFRESH_MS, False)

	def cleanup(self):
		self.timer.stop()
		self.control.stop()

	def refresh(self):
		if self.pending:
			return
		self.pending = True
		self.control.status(self.gotStatus)

	def gotStatus(self, status):
		if not status:
			self.pending = False
			self["info"].setText(_("WiFi is not active on %s.") % self.iface)
			return
		self.control.signal(boundFunction(self.showStatus, status))

	def showStatus(self, status, values):
		self.pending = False
		# the signal also from /proc/net/wireless, for drivers that do not answer signal_poll
		self["info"].setText("\n".join(HdsWlan.statusLines(status, values, HdsWlan.nivelProc(self.iface))))
