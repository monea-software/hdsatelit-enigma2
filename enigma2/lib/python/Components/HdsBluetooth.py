# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com & hdsatelit.com
# SPDX-License-Identifier: GPL-2.0-only
"""BlueZ input pairing, shared by TV and web. No device addresses leave this module."""
import builtins
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import threading
import time

_ADDRESS = r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}"
_PRIVATE_ADDRESS = re.compile(r"(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}")
_DEVICE = re.compile(r"^Device (" + _ADDRESS + r") (.+)$", re.M)
_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_PROMPT = r"(?:^|[\r\n])(?:\[[^\r\n]*\]#[ \t]*)?"
_HID = ("00001124-", "00001812-")


def _(text):
	return getattr(builtins, "_", lambda s: s)(text)


def _clean(text):
	text = _PRIVATE_ADDRESS.sub("", _ANSI.sub("", str(text)))
	return " ".join(text.split())[:80]


def _input(info):
	return any(uuid in info.lower() for uuid in _HID) or bool(re.search(r"Icon: input-", info))


def _pair(program, args, timeout, env):
	# BlueZ skips --agent registration when pair is a command-line argument.
	if len(args) != 2 or args[0] != "pair" or not re.fullmatch(_ADDRESS, args[1]):
		raise ValueError("pair")
	deadline = time.monotonic() + timeout
	condition = threading.Condition()
	state = {"registered": False, "paired": False, "sent": False,
		"failed": False, "closed": False}
	# Interactive bluetoothctl reads and writes history. Keep it out of user files.
	with tempfile.TemporaryDirectory(prefix="hds-bluetooth-") as cache:
		env = dict(env, XDG_CACHE_HOME=cache)
		p = subprocess.Popen([program, "--agent", "NoInputNoOutput"],
			stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
		reader = None
		try:
			def read():
				text = ""
				try:
					while True:
						chunk = p.stdout.readline(4096)
						if not chunk:
							break
						text = (text + _ANSI.sub("", chunk.decode("utf-8", "replace")))[-8192:]
						with condition:
							state["registered"] |= bool(re.search(_PROMPT + r"Agent registered(?:\r?\n|$)", text))
							state["paired"] |= state["sent"] and bool(re.search(_PROMPT + r"Pairing successful(?:\r?\n|$)", text))
							state["failed"] |= bool(re.search(_PROMPT + r"(?:Failed\b|No default controller\b|Invalid command\b|Device [^\r\n]+ not available\b)", text, re.I))
							condition.notify_all()
				except (OSError, ValueError):
					with condition:
						state["failed"] = True
				finally:
					with condition:
						state["closed"] = True
						condition.notify_all()

			def wait(key):
				with condition:
					condition.wait_for(lambda: state[key] or state["failed"] or state["closed"],
						timeout=max(0, deadline - time.monotonic()))
					if state["failed"] or (state["closed"] and not state[key]):
						raise RuntimeError("bluez")
					if not state[key]:
						raise subprocess.TimeoutExpired(program, timeout)

			reader = threading.Thread(target=read, daemon=True)
			reader.start()
			wait("registered")
			with condition:
				state["sent"] = True
				p.stdin.write(("pair " + args[1] + "\n").encode("ascii"))
				p.stdin.flush()
			wait("paired")
			return 0, "Pairing successful"
		finally:
			if p.poll() is None:
				try:
					p.terminate()
				except ProcessLookupError:
					pass  # The client exited between poll and terminate.
				try:
					p.wait(timeout=1)
				except subprocess.TimeoutExpired:
					p.kill()
					p.wait()
			if reader is not None and reader.ident is not None:
				reader.join(timeout=1)
			p.stdin.close()
			p.stdout.close()


def _run(args, timeout=8, agent=False):
	program = shutil.which("bluetoothctl")
	if not program:
		raise RuntimeError("missing")
	env = dict(os.environ, LC_ALL="C", LANG="C")
	if agent:
		return _pair(program, args, timeout, env)
	cmd = [program, "--timeout", str(timeout)] + list(args)
	# No shell, no output in the journal, and a hard limit independent of BlueZ.
	p = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
		stderr=subprocess.STDOUT, timeout=timeout + 3, env=env)
	return p.returncode, _ANSI.sub("", p.stdout.decode("utf-8", "replace"))


class Manager:
	def __init__(self, run=None):
		self.run = run or _run
		self.lock = threading.Lock()
		self.busy = False
		self.devices = {}
		self.rows = []
		self.message = ""
		self.ready = False

	def stare(self):
		with self.lock:
			return {"result": True, "ocupat": self.busy, "message": self.message,
				"gata": self.ready, "dispozitive": [dict(r) for r in self.rows]}

	def porneste(self, actiune, ident=""):
		with self.lock:
			if self.busy:
				return {"result": False, "message": _("Bluetooth lucrează acum. Așteaptă să termine.")}
			if actiune not in ("citeste", "cauta", "asociaza"):
				return {"result": False, "message": _("Comandă Bluetooth necunoscută.")}
			address = self.devices.get(ident)
			if actiune == "asociaza" and not address:
				return {"result": False, "message": _("Telecomanda nu mai este în listă. Caută din nou.")}
			self.busy = True
			self.message = _("Se caută telecomenzi, cel mult 20 de secunde...") if actiune == "cauta" else _("Se verifică legătura Bluetooth...")
		try:
			threading.Thread(target=self._lucreaza, args=(actiune, address), daemon=True).start()
		except Exception:
			with self.lock:
				self.busy = False
				self.message = _("Bluetooth nu a putut porni. Încearcă din nou.")
			return {"result": False, "message": self.message}
		return {"result": True}

	def _cere(self, args, timeout=8, agent=False):
		code, output = self.run(args, timeout=timeout, agent=agent)
		if code != 0 or re.search(r"^(?:Failed\b|No default controller\b|Invalid command\b)|^Device [^\n]+ not available$", output, re.I | re.M):
			raise RuntimeError("bluez")
		return output

	def _lista(self):
		output = self._cere(["devices"])
		devices, rows = {}, []
		with self.lock:
			old = {v: k for k, v in self.devices.items()}
		for address, name in _DEVICE.findall(output)[:32]:
			try:
				info = self._cere(["info", address], timeout=3)
			except (RuntimeError, OSError, subprocess.TimeoutExpired):
				continue  # A device can disappear while the scan results are read.
			# Some LE remotes publish their HID service only after pairing.
			if not _input(info) and ("UUID:" in info or "Paired: yes" in info):
				continue
			ident = old.get(address) or secrets.token_hex(12)
			devices[ident] = address
			rows.append({"id": ident, "nume": _clean(name) or _("Telecomandă Bluetooth"),
				"asociata": bool(re.search(r"Paired: yes", info)),
				"conectata": bool(re.search(r"Connected: yes", info))})
		with self.lock:
			self.devices, self.rows = devices, rows
			self.ready = True

	def _lucreaza(self, actiune, address):
		try:
			if actiune == "cauta":
				self._cere(["power", "on"])
				# The discovery session belongs to this short lived client only.
				self._cere(["scan", "on"], timeout=20)
			elif actiune == "asociaza":
				info = self._cere(["info", address], timeout=3)
				if not re.search(r"Paired: yes", info):
					self._cere(["pair", address], timeout=35, agent=True)
					info = self._cere(["info", address], timeout=3)
					if not re.search(r"Paired: yes", info):
						raise RuntimeError("pair")
				if not _input(info):
					raise RuntimeError("not_input")
				self._cere(["trust", address])
				if not re.search(r"Connected: yes", info):
					self._cere(["connect", address], timeout=15)
				info = self._cere(["info", address], timeout=3)
				if not re.search(r"Connected: yes", info):
					raise RuntimeError("connect")
			self._lista()
			if actiune == "asociaza":
				message = _("Telecomanda este asociată și conectată.")
			elif self.rows:
				message = _("Alege telecomanda pentru asociere.")
			else:
				message = _("Nu am găsit nicio telecomandă. Pune telecomanda în modul de asociere și pornește căutarea.")
		except Exception:
			message = _("Bluetooth nu răspunde sau asocierea nu a reușit. Pune telecomanda în modul de asociere și caută din nou.")
		finally:
			with self.lock:
				self.message = message
				self.busy = False


manager = Manager()
