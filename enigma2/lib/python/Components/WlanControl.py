# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# WiFi control for HDSatelit Image: runs wpa_cli and wpa_supplicant without blocking the screen.
# Commands run without a shell (argument lists) and are not written
# to the log; passwords never appear here, they only go into the config file through WlanTools.
import os

from enigma import eTimer
from Components.Console import Console
from Components import WlanTools

WPA_CLI = "wpa_cli"
WPA_SUPPLICANT = "wpa_supplicant"
SCAN_WAIT_MS = 4000
BUSY_RETRY_MS = 2000
BUSY_RETRIES = 3
START_WAIT_MS = 1500


class WlanControl:
	def __init__(self, iface, conf=WlanTools.SUPPLICANT_CONF, ctrl=WlanTools.CTRL_INTERFACE):
		self.iface = iface
		self.conf = conf
		self.ctrl = ctrl
		self.console = Console()
		self.timers = []
		self.stopped = False

	# --- plumbing

	def later(self, ms, fnc):
		timer = eTimer()
		timer.callback.append(self.guarded(fnc))
		timer.start(ms, True)
		self.timers.append(timer)

	def guarded(self, fnc):
		# callbacks that arrive after the screen closed are dropped
		def call(*args):
			if not self.stopped:
				fnc(*args)
		return call

	def execute(self, args, callback):
		"""args[0] is the program (searched in PATH); callback(retval, output)"""
		cmd = (args[0],) + tuple(args)
		self.console.ePopen(cmd, self.finished, self.guarded(callback), log=False)

	def finished(self, data, retval, callback):
		callback(retval, data or "")

	def cli(self, args, callback):
		self.execute((WPA_CLI, "-p", self.ctrl, "-i", self.iface) + tuple(args), callback)

	def stop(self):
		self.stopped = True
		for timer in self.timers:
			timer.stop()
		self.timers = []
		self.console.killAll()

	# --- supplicant

	def isRunning(self):
		return os.path.exists(os.path.join(self.ctrl, self.iface))

	def ensureSupplicant(self, callback):
		"""starts wpa_supplicant for scanning if nothing runs on the interface; callback(ok)"""
		if self.isRunning():
			# a supplicant already running (ifup) may still hold the block matching any network: the file is cleaned
			# and the supplicant reads it again (reconfigure), so it no longer joins open networks of the neighbours
			if self.dropWildcards():
				self.reconfigure(lambda ok: callback(True))
				return
			callback(True)
			return
		driver = WlanTools.getWlanDriver(self.iface)
		if driver is None:
			callback(False)
			return
		if not os.path.exists(self.conf):
			if not WlanTools.writeConfAtomic(self.conf, "ctrl_interface=%s\nupdate_config=0\n" % self.ctrl):
				callback(False)
				return
		else:
			self.dropWildcards()
		drivers = "nl80211,wext" if driver == "nl80211" else "wext"

		def linkUp(retval, output):
			self.execute((WPA_SUPPLICANT, "-B", "-i", self.iface, "-D", drivers, "-c", self.conf,
				"-P", "/var/run/wpa_supplicant.%s.pid" % self.iface), started)

		def started(retval, output):
			if retval != 0:
				print("[WlanControl] wpa_supplicant did not start on %s (%s)" % (self.iface, retval))
				callback(False)
				return
			self.later(START_WAIT_MS, lambda: callback(self.isRunning()))

		self.execute(("ip", "link", "set", self.iface, "up"), linkUp)

	def dropWildcards(self):
		"""the default file of the wpa-supplicant package has a block without ssid (key_mgmt=NONE): the supplicant
		started for searching would join any open network in range; such blocks go before it starts. Returns how many
		blocks were dropped."""
		try:
			with open(self.conf, "r", encoding="utf-8", errors="replace") as f:
				text = f.read()
		except (IOError, OSError):
			return 0
		text, dropped = WlanTools.cleanConf(text)
		if dropped:
			print("[WlanControl] %d network block(s) matching any network removed from %s" % (dropped, self.conf))
			if not WlanTools.writeConfAtomic(self.conf, text):
				return 0
		return dropped

	# --- scan and status

	def scan(self, callback, retries=BUSY_RETRIES, raw=False):
		"""callback(networks) with the list from WlanTools.parseScanResults, or None if scanning failed; with raw=True
		callback(text) with the scan_results text itself (one row for each access point, for the channel tool)"""
		def requested(retval, output):
			answer = output.strip()
			if answer == "OK":
				self.later(SCAN_WAIT_MS, lambda: self.cli(("scan_results",), results))
			elif answer == "FAIL-BUSY" and retries > 0:
				self.later(BUSY_RETRY_MS, lambda: self.scan(callback, retries - 1, raw))
			else:
				print("[WlanControl] scan on %s refused: %s" % (self.iface, answer or retval))
				callback(None)

		def results(retval, output):
			if retval != 0:
				callback(None)
			elif raw:
				callback(output)
			else:
				callback(WlanTools.parseScanResults(output))

		self.cli(("scan",), requested)

	def status(self, callback):
		"""callback(dict from wpa_cli status), empty dict when the supplicant does not answer"""
		self.cli(("status",), lambda retval, output: callback(WlanTools.parseStatus(output) if retval == 0 else {}))

	def signal(self, callback):
		"""callback(dict with RSSI, LINKSPEED, FREQUENCY); empty on drivers that do not report it"""
		def done(retval, output):
			values = WlanTools.parseStatus(output) if retval == 0 and not output.startswith("FAIL") else {}
			callback(values)
		self.cli(("signal_poll",), done)

	def capabilities(self, callback):
		"""callback(set of key management methods, for example {"WPA-PSK", "SAE"})"""
		def done(retval, output):
			callback(set(output.split()) if retval == 0 and not output.startswith("FAIL") else set())
		self.cli(("get_capability", "key_mgmt"), done)

	def reconfigure(self, callback):
		"""the supplicant reads the config file again; callback(ok)"""
		self.cli(("reconfigure",), lambda retval, output: callback(retval == 0 and output.strip() == "OK"))

	def terminate(self, callback):
		self.cli(("terminate",), lambda retval, output: callback(retval == 0))
