# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com & hdsatelit.com
# SPDX-License-Identifier: GPL-2.0-only
"""The receiver sound in a Bluetooth headset or speaker (A2DP), shared by the TV screen and the web: films and IPTV
through alsasink (servicemp3.cpp), TV channels and satellite radio through the equalizer engine (Components/HdsEgalizator.py,
dispozitivBluetooth), which decodes the channel sound itself where the board gives no copy of it (HiSilicon).

Off by default; with the option off nothing is installed, started or written. When a headset is chosen:
bluez5 and bluez-alsa are installed once (opkg, on a worker thread), the bluealsa daemon is started only
while the option is on (its boot link is removed after the install), the headset is paired, trusted and
connected, and FISIER gets the ALSA device of the headset. servicemp3 reads FISIER once when a film starts:
with it the sound goes to alsasink on that device, without it to dvbaudiosink as before. On the models with
/proc/stb/audio/btaudio the node is switched on and off as well (and btaudio_delay, ms * 90 in hex).
When the headset disconnects, FISIER is removed and bluealsa stopped; a slow retry connects it again.
"""
import builtins
import os
import re
import shutil
import subprocess
import threading
import time

FISIER = "/var/run/hds-bt-sunet"
NOD = "/proc/stb/audio/btaudio"
NOD_INTARZIERE = "/proc/stb/audio/btaudio_delay"
ADAPTOARE = "/sys/class/bluetooth"
BLUEALSA = "/usr/bin/bluealsa"
BLUEALSA_INIT = "/etc/init.d/bluealsa"
BLUETOOTH_INIT = "/etc/init.d/bluetooth"
PACHETE = ("bluez5", "bluez-alsa")
A2DP_SINK = "0000110b-"
VERIFICARE = 5  # seconds between the checks of a connected headset
REINCERCARE = 30  # seconds between the attempts to connect it again

_DEVICE = re.compile(r"^Device ((?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}) (.+)$", re.M)
_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def _(text):
	return getattr(builtins, "_", lambda s: s)(text)


def N_(text):
	return text


def initConfig():
	from Components.config import config
	if "hds_bt_sunet" in config.content.items:
		return config.hds_bt_sunet
	from Components.config import ConfigSubsection, ConfigYesNo, ConfigText, ConfigInteger
	config.hds_bt_sunet = ConfigSubsection()
	c = config.hds_bt_sunet
	c.pornit = ConfigYesNo(default=False)
	c.adresa = ConfigText(default="", fixed_size=False)
	c.nume = ConfigText(default="", fixed_size=False)
	# only on the models with btaudio_delay: the picture waits this many ms for the headset
	c.intarziere = ConfigInteger(default=0)
	return c


def _salveaza(c):
	for element in (c.pornit, c.adresa, c.nume, c.intarziere):
		element.save()
	from Components.config import configfile
	configfile.save()


def poate():
	"""True when the receiver has a Bluetooth adapter: only then the option is shown."""
	try:
		return any(n.startswith("hci") for n in os.listdir(ADAPTOARE))
	except OSError:
		return False


def areNod():
	return os.path.exists(NOD)


def dispozitivAlsa(adresa):
	return "bluealsa:DEV=%s,PROFILE=a2dp" % adresa.upper()


def _bluetoothctl(args, timeout=8, agent=False):
	from Components.HdsBluetooth import _run
	return _run(args, timeout=timeout, agent=agent)


def _comanda(argv, timeout=60):
	try:
		p = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
			timeout=timeout)
	except (OSError, subprocess.TimeoutExpired) as e:
		return 1, str(e)
	return p.returncode, p.stdout.decode("utf-8", "replace")


def _opkgOcupat():
	from Components.HdsActualizari import opkg_ocupat
	return opkg_ocupat()


def _fir(functie, *args):
	threading.Thread(target=functie, args=args, daemon=True).start()


INTARZIERE_MAX = 300      # ms, ca potrivirea TV a egalizatorului (POTRIVIRE_TV_MAX)
INTARZIERE_PAS = 20


def _egalizator():
	"""Canalele TV si radioul din satelit merg in casca prin motorul egalizatorului (Components/HdsEgalizator.py,
	dispozitivBluetooth): el afla ca s-a schimbat casca."""
	try:
		from Components import HdsEgalizator
		HdsEgalizator.laBluetooth()
	except Exception as e:
		print("[HdsBluetoothSunet] egalizatorul: %s" % e)


def _scrie(cale, text):
	try:
		with open(cale, "w") as f:
			f.write(text)
		return True
	except (IOError, OSError):
		return False


class Sunet:
	def __init__(self, run=None, comanda=None, ocupat=None, fir=None, setari=None, dormi=None):
		self.run = run or _bluetoothctl
		self.comanda = comanda or _comanda
		self.ocupat = ocupat or _opkgOcupat
		self.fir = fir or _fir
		self.setari = setari or initConfig
		self.dormi = dormi or time.sleep
		self.lock = threading.Lock()
		self.busy = False
		self.message = ""
		self.rows = []
		self.legat = False
		self.paznic = None  # threading.Event of the running watcher, set to stop it
		self.lucru = threading.RLock()  # one link change at a time (worker and watcher)

	# ------------------------------------------------------------ state for the screen and the web

	def stare(self):
		c = self.setari()
		with self.lock:
			return {"result": True, "pornit": bool(c.pornit.value),
				"adresa": c.adresa.value if c.pornit.value else "", "nume": c.nume.value if c.pornit.value else "",
				"legat": self.legat, "ocupat": self.busy, "message": self.message,
				"intarziere": int(c.intarziere.value),
				"dispozitive": [dict(r) for r in self.rows]}

	def eticheta(self):
		"""The text of the option row: the chosen headset or No."""
		c = self.setari()
		ales = c.nume.value or c.adresa.value if c.pornit.value else ""
		return _("Sunetul receptorului în cască Bluetooth: %s") % (ales or _("Nu"))

	def urmatorul(self):
		"""The address after the chosen one in No -> headsets -> No (one key on the remote)."""
		c = self.setari()
		lista = [""] + [r["id"] for r in self.rows]
		acum = c.adresa.value if c.pornit.value else ""
		i = lista.index(acum) if acum in lista else 0
		return lista[(i + 1) % len(lista)]

	# ------------------------------------------------------------ commands (UI thread)

	def citeste(self):
		return self._incepe(self._citeste, _("Se caută căștile și boxele asociate..."))

	def alege(self, adresa):
		"""adresa "" = No. Saved here, on the caller's thread; the work goes to a worker thread."""
		adresa = (adresa or "").strip()
		with self.lock:
			if self.busy:
				return {"result": False, "message": _("Bluetooth lucrează acum. Așteaptă să termine.")}
		c = self.setari()
		self._opresteSupraveghere()
		if not adresa:
			c.pornit.value = False
			_salveaza(c)
			return self._incepe(self._dezactiveaza, _("Sunetul merge iar pe ieșirea obișnuită a receptorului."))
		nume = next((r["nume"] for r in self.rows if r["id"] == adresa), "")
		c.pornit.value = True
		c.adresa.value = adresa
		c.nume.value = nume
		_salveaza(c)
		return self._incepe(self._activeaza, _("Se leagă casca..."), adresa)

	def intarziere(self, ms):
		"""The headset delay in ms (+ = sound later), -300..300; 0 from the factory: the equalizer engine already keeps
		the sound in step with the picture using the delay that ALSA (bluealsa) reports for the headset."""
		c = self.setari()
		c.intarziere.value = max(-INTARZIERE_MAX, min(INTARZIERE_MAX, int(ms)))
		_salveaza(c)
		if c.pornit.value and self.legat:
			self._scrieNod(True)
			try:
				from Components import HdsEgalizator
				HdsEgalizator.laIntarziereBluetooth()
			except Exception as e:
				print("[HdsBluetoothSunet] egalizatorul: %s" % e)
		return {"result": True, "intarziere": int(c.intarziere.value)}

	def porneste(self):
		"""At start (and when the screen or the page opens): nothing at all while the option is No."""
		c = self.setari()
		# while a choice is at work (install, link) its own watcher starts at the end; a second one would race it
		if not c.pornit.value or not c.adresa.value or self.paznic is not None or self.busy:
			return False
		if not os.path.exists(BLUEALSA):
			with self.lock:
				self.message = _("Pachetul pentru sunetul Bluetooth lipsește. Alege din nou casca.")
			return False
		self._pornesteSupraveghere(c.adresa.value, 0.0)
		return True

	def _incepe(self, functie, mesaj, *args):
		with self.lock:
			if self.busy:
				return {"result": False, "message": _("Bluetooth lucrează acum. Așteaptă să termine.")}
			self.busy = True
			self.message = mesaj
		try:
			self.fir(self._lucreaza, functie, args)
		except Exception:
			with self.lock:
				self.busy = False
				self.message = _("Bluetooth nu a putut porni. Încearcă din nou.")
			return {"result": False, "message": self.message}
		return {"result": True}

	def _lucreaza(self, functie, args):
		mesaj = None
		try:
			mesaj = functie(*args)
		finally:
			with self.lock:
				if mesaj is not None:
					self.message = mesaj
				self.busy = False

	# ------------------------------------------------------------ work (worker thread)

	def _cere(self, args, timeout=8, agent=False):
		code, output = self.run(args, timeout=timeout, agent=agent)
		output = _ANSI.sub("", output or "")
		if code != 0 or re.search(r"^(?:Failed\b|No default controller\b|Invalid command\b)|^Device [^\n]+ not available$", output, re.I | re.M):
			raise RuntimeError("bluez")
		return output

	def _citeste(self):
		try:
			self._lista()
		except Exception:
			return _("Bluetooth nu răspunde. Încearcă din nou.")
		if not self.rows:
			return _("Nu am găsit nicio cască sau boxă. Pune-o în modul de asociere și caută din nou.")
		return ""

	def _lista(self):
		output = self._cere(["devices"])
		rows = []
		for address, name in _DEVICE.findall(output):
			try:
				info = self._cere(["info", address], timeout=3)
			except (RuntimeError, OSError, subprocess.TimeoutExpired):
				continue
			if A2DP_SINK not in info.lower():
				continue
			rows.append({"id": address, "nume": " ".join(_ANSI.sub("", name).split()) or address,
				"asociata": "Paired: yes" in info, "conectata": "Connected: yes" in info})
		with self.lock:
			self.rows = rows

	def _instaleaza(self):
		if os.path.exists(BLUEALSA):
			return True
		with self.lock:
			self.message = _("Se aduce pachetul pentru sunetul Bluetooth...")
		for incercare in range(2):
			for _secunda in range(120):
				if not self.ocupat():
					break
				self.dormi(1)
			if incercare:
				self.comanda(["opkg"] + _argumenteUpdate(), timeout=180)
			code, _text = self.comanda(["opkg", "install"] + list(PACHETE), timeout=600)
			if code == 0 and os.path.exists(BLUEALSA):
				# the package starts bluealsa at every boot; here it runs only while the option is on
				self.comanda(["update-rc.d", "-f", "bluealsa", "remove"], timeout=30)
				return True
		return False

	def _pornesteStiva(self):
		if self.comanda(["pidof", "bluetoothd"], timeout=10)[0] != 0:
			self.comanda([BLUETOOTH_INIT, "start"], timeout=30)
		return self.comanda([BLUEALSA_INIT, "start"], timeout=30)[0] == 0

	def _flux(self, adresa):
		"""True when BlueZ has the A2DP transport of the headset (made only with bluealsa running): a link alone
		(the headset connected itself while bluealsa was stopped) carries no sound. None when bluetoothctl has no
		transport menu; then Connected is all there is."""
		code, output = self.run(["transport.list"], timeout=5)
		output = _ANSI.sub("", output or "")
		if re.search(r"Invalid command|Unknown command|Invalid argument", output, re.I):
			return None
		return code == 0 and ("DEV_" + adresa.upper().replace(":", "_")) in output.upper()

	def _conectat(self, adresa):
		try:
			if "Connected: yes" not in self._cere(["info", adresa], timeout=3):
				return False
			return self._flux(adresa) is not False
		except Exception:
			return False

	def _leaga(self, adresa):
		"""Pair, trust and connect (always, after bluealsa started: an old link has no A2DP stream); True when the
		A2DP transport of the headset exists."""
		info = self._cere(["info", adresa], timeout=3)
		if "Paired: yes" not in info:
			self._cere(["pair", adresa], timeout=35, agent=True)
		self._cere(["trust", adresa])
		# an already connected headset answers Failed (AlreadyConnected) here; the transport below decides
		self.run(["connect", adresa], timeout=15)
		for _incercare in range(5):
			if self._conectat(adresa):
				return True
			self.dormi(1)
		return False

	def _scrieNod(self, pornit):
		if not areNod():
			return
		_scrie(NOD, "on" if pornit else "off")
		if os.path.exists(NOD_INTARZIERE):
			ms = self.setari().intarziere.value if pornit else 0
			_scrie(NOD_INTARZIERE, format(int(ms) * 90, "x"))

	def _pune(self, adresa):
		self._scrieNod(True)
		d = dispozitivAlsa(adresa)
		try:
			with open(FISIER) as f:
				acelasi = f.read().strip() == d
		except (IOError, OSError):
			acelasi = False
		self.legat = True
		if not acelasi:
			# numai la o casca noua: motorul egalizatorului reporneste sesiunea spre ea (paznicul nu taie sunetul la fiecare tura)
			_scrie(FISIER, d)
			_egalizator()

	def _curata(self):
		"""Back to the usual output: no file, no daemon, node off."""
		try:
			os.unlink(FISIER)
			_egalizator()
		except OSError:
			pass
		self._scrieNod(False)
		if os.path.exists(BLUEALSA_INIT):
			self.comanda([BLUEALSA_INIT, "stop"], timeout=30)
		self.legat = False

	def _incearca(self, adresa, gata=None):
		"""One attempt: daemon, link, file. On failure (or when the option went off meanwhile) everything is
		stopped again."""
		with self.lucru:
			# a watcher stopped while it waited here must not undo the work of the newer one (no _curata)
			if gata is not None and gata.is_set():
				return False
			try:
				if self._pornesteStiva() and self._leaga(adresa) and not (gata is not None and gata.is_set()):
					self._pune(adresa)
					return True
			except Exception:
				pass
			self._curata()
			return False

	def _mesajLegat(self):
		if areNod():
			return _("Casca este legată. Sunetul receptorului merge în cască.")
		try:
			from Components.HdsEgalizator import cascaPrinMotor
			prinMotor = cascaPrinMotor()
		except Exception:
			prinMotor = False
		if prinMotor:
			return _("Casca este legată. Sunetul receptorului merge în cască, cu o mică întârziere.")
		return _("Casca este legată. Merg numai filmele și IPTV, nu canalele TV, iar sunetul vine cu o mică întârziere.")

	def _activeaza(self, adresa):
		if not self._instaleaza():
			self._curata()
			return _("Pachetul pentru sunetul Bluetooth nu a putut fi adus. Verifică internetul și încearcă din nou.")
		with self.lock:
			self.message = _("Se leagă casca...")
		ok = self._incearca(adresa)
		self._pornesteSupraveghere(adresa, time.monotonic())
		if ok:
			return self._mesajLegat()
		return _("Casca nu răspunde. Pornește-o lângă receptor; receptorul se leagă singur când o găsește.")

	def _dezactiveaza(self):
		with self.lucru:
			self._curata()
		return _("Sunetul merge iar pe ieșirea obișnuită a receptorului.")

	# ------------------------------------------------------------ watcher (its own thread, only while on)

	def _pornesteSupraveghere(self, adresa, ultima):
		self._opresteSupraveghere()
		gata = threading.Event()
		self.paznic = gata
		self.fir(self._supravegheaza, adresa, gata, ultima)

	def _opresteSupraveghere(self):
		if self.paznic is not None:
			self.paznic.set()
			self.paznic = None

	def _supravegheaza(self, adresa, gata, ultima):
		while not gata.is_set():
			ultima = self._verificaOData(adresa, ultima, gata)
			gata.wait(VERIFICARE)

	def _verificaOData(self, adresa, ultima, gata=None, acum=None):
		"""One step of the watcher; returns the time of the last connection attempt."""
		acum = time.monotonic() if acum is None else acum
		if gata is not None and gata.is_set():
			return ultima
		if self.legat:
			if not self._conectat(adresa):
				with self.lucru:
					self._curata()
				with self.lock:
					self.message = _("Casca s-a deconectat. Sunetul merge iar pe ieșirea obișnuită a receptorului.")
			return ultima
		if ultima and acum - ultima < REINCERCARE:
			return ultima
		if self._incearca(adresa, gata):
			with self.lock:
				self.message = self._mesajLegat()
		return acum


sunet = Sunet()


def porneste():
	return sunet.porneste()


def _argumenteUpdate(rad="/"):
	"""OPK1 (0.8.0): ['update'], or ['-f', <conf>, 'update'] when a dead foreign source is skipped (HdsSurseOpkg)"""
	try:
		try:
			from Components import HdsSurseOpkg
		except ImportError:
			import HdsSurseOpkg
		return HdsSurseOpkg.argumente_update(rad)
	except Exception as e:
		print("[HdsSurseOpkg] %r" % (e,))
		return ["update"]
