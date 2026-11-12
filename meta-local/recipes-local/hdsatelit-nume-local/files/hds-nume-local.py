#!/usr/bin/python3
# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only

"""Publica numele local dupa aparitia retelei. Lipsurile temporare nu opresc serviciul."""

import json
import os
import re
import select
import shutil
import signal
import socket
import struct
import subprocess
import sys
import time

RADACINA = "/var/run"
PAUZA = 2
REINCERCARE = 10
JURNAL_RAR = 300


def citeste(cale):
	try:
		with open(cale, encoding="utf-8") as f:
			return f.read(8192)
	except OSError:
		return ""


def inceput(pid):
	try:
		date = citeste("/proc/%d/stat" % int(pid)).rsplit(")", 1)[1].split()
		return date[19] if date[0] not in ("Z", "X") else ""
	except (ValueError, IndexError, TypeError):
		return ""


def scrie(cale, text):
	with open(cale + ".nou", "w", encoding="utf-8") as f:
		f.write(text)
	os.replace(cale + ".nou", cale)


def sterge(cale):
	try:
		os.unlink(cale)
	except FileNotFoundError:
		pass


def jurnal(text):
	try:
		import syslog
		syslog.syslog(syslog.LOG_NOTICE, "hds-nume-local: " + text)
	except ImportError:
		print("hds-nume-local: " + text, flush=True)


def adresa_retea():
	"""Ruta implicita cu metrica mica, apoi reteaua locala chiar fara router."""
	import fcntl
	rute = []
	for linie in citeste("/proc/net/route").splitlines()[1:]:
		p = linie.split()
		try:
			if p[1] == "00000000" and int(p[3], 16) & 1:
				rute.append((int(p[6]), p[0]))
		except (IndexError, ValueError):
			continue
	placi = [p for _, p in sorted(rute)]
	placi += [p for _, p in socket.if_nameindex() if p not in placi]
	with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
		for placa in placi:
			if placa.startswith(("lo", "tun", "tap", "wg", "ppp", "docker", "veth")):
				continue
			try:
				if not int(citeste("/sys/class/net/%s/flags" % placa).strip(), 16) & 1:
					continue
			except ValueError:
				continue
			if citeste("/sys/class/net/%s/carrier" % placa).strip() == "0":
				continue
			try:
				date = struct.pack("256s", placa.encode("ascii")[:15])
				ip = socket.inet_ntoa(fcntl.ioctl(s.fileno(), 0x8915, date)[20:24])
				if not ip.startswith(("0.", "127.", "169.254.")):
					return placa, ip
			except (OSError, UnicodeError):
				continue
	return "", ""


class Serviciu:
	def __init__(self, radacina=RADACINA):
		self.radacina = radacina
		self.proc = None
		self.placa = self.ip = self.nume = self.rest = ""
		self.numar = 1
		self.urmatoarea = 0
		self.note = {}
		self.t_lansare = 0

	def cale(self, sufix):
		return os.path.join(self.radacina, "hds-nume-local." + sufix)

	def noteaza(self, text, acum):
		if text not in self.note or acum - self.note[text] >= JURNAL_RAR:
			jurnal(text)
			if len(self.note) >= 32:
				self.note.clear()
			self.note[text] = acum

	def publica_starea(self, acum):
		pid = self.proc.pid if self.proc is not None else 0
		stare = {"pid": os.getpid(), "inceput": inceput(os.getpid()),
			"publicator": pid, "inceput_publicator": inceput(pid),
			"nume": self.nume, "adresa": self.ip, "placa": self.placa, "actualizat": acum}
		scrie(self.cale("stare"), json.dumps(stare))
		if self.nume:
			scrie(self.cale("nume"), self.nume[:-6] + "\n")
		else:
			sterge(self.cale("nume"))

	def opreste_publicarea(self):
		self.nume = self.rest = ""
		sterge(self.cale("nume"))
		if self.proc is not None:
			try:
				self.proc.terminate()
				self.proc.wait(timeout=2)
			except subprocess.TimeoutExpired:
				self.proc.kill()
				self.proc.wait(timeout=2)
			except ProcessLookupError:
				pass
			finally:
				self.proc.stderr.close()
				self.proc = None

	def mesaje(self):
		bucati = []
		while select.select([self.proc.stderr], [], [], 0)[0]:
			date = os.read(self.proc.stderr.fileno(), 4096)
			if not date:
				break
			bucati.append(date.decode("utf-8", "replace"))
		linii = (self.rest + "".join(bucati)).split("\n")
		self.rest = linii.pop()[-4096:]
		return linii

	def pas(self, acum):
		placa, ip = adresa_retea()
		if (placa, ip) != (self.placa, self.ip):
			self.opreste_publicarea()
			self.placa, self.ip = placa, ip
			self.urmatoarea = 0
		if not ip:
			self.noteaza("Astept o placa de retea cu adresa IPv4.", acum)
		elif self.proc is None and acum >= self.urmatoarea:
			utilitar = shutil.which("avahi-publish-address") or shutil.which("avahi-publish")
			if not utilitar:
				self.noteaza("Lipseste avahi-publish. Astept instalarea dependentei.", acum)
			else:
				nume = "hdsatelit%s.local" % ("-%d" % self.numar if self.numar > 1 else "")
				env = dict(os.environ, LC_ALL="C")
				try:
					self.proc = subprocess.Popen([utilitar, "-a", "-R", "-v", nume, ip],
						stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
						stderr=subprocess.PIPE, env=env)
					self.t_lansare = acum
					self.noteaza("Astept confirmarea avahi pentru %s pe %s (%s)." %
						(nume, placa, ip), acum)
				except OSError as eroare:
					self.noteaza("Nu pot porni avahi-publish: %s. Reincerc." % eroare, acum)
			self.urmatoarea = acum + REINCERCARE
		if self.proc is not None:
			for mesaj in self.mesaje():
				confirmat = re.fullmatch(r"Established under name '(hdsatelit(?:-[0-9]+)?\.local)'", mesaj)
				if confirmat:
					self.nume = confirmat.group(1)
					self.noteaza("Numele %s este publicat pentru %s." % (self.nume, ip), acum)
				elif "Name collision" in mesaj:
					self.numar = self.numar + 1 if self.numar < 99 else 1
					self.noteaza("Numele este folosit de alt aparat. Incerc alt nume.", acum)
					self.opreste_publicarea()
					self.urmatoarea = acum + REINCERCARE
					break
				elif mesaj.strip():
					if any(x in mesaj.lower() for x in ("failed", "failure", "disconnected",
						"waiting for daemon", "host name conflict")):
						self.nume = ""
					self.noteaza("Avahi: %s. Reincerc daca publicarea nu reuseste." % mesaj[:240], acum)
			if self.proc is not None and (self.proc.poll() is not None or
				(not self.nume and acum - self.t_lansare >= 30)):
				self.noteaza("Publicarea nu este activa. Verifica avahi, D-Bus si portul UDP 5353. Reincerc.", acum)
				self.opreste_publicarea()
				self.urmatoarea = acum + REINCERCARE
		self.publica_starea(acum)


def proces_serviciu():
	try:
		pid = int(citeste(os.path.join(RADACINA, "hds-nume-local.pid")).strip())
		stare = json.loads(citeste(os.path.join(RADACINA, "hds-nume-local.identitate")))
		if pid > 1 and pid == stare["pid"] and stare["inceput"] and inceput(pid) == stare["inceput"]:
			return pid
	except (ValueError, KeyError, TypeError):
		pass
	return None


def ruleaza():
	import fcntl
	import threading
	os.makedirs(RADACINA, exist_ok=True)
	with open(os.path.join(RADACINA, "hds-nume-local.lock"), "w") as blocare:
		try:
			fcntl.flock(blocare, fcntl.LOCK_EX | fcntl.LOCK_NB)
		except BlockingIOError:
			return 0
		serviciu = Serviciu()
		trezeste = threading.Event()
		gata = [False]
		def semnal(numar, cadru):
			if numar != signal.SIGHUP:
				gata[0] = True
			trezeste.set()
		for numar in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
			signal.signal(numar, semnal)
		scrie(serviciu.cale("identitate"), json.dumps({"pid": os.getpid(), "inceput": inceput(os.getpid())}))
		scrie(serviciu.cale("pid"), "%d\n" % os.getpid())
		try:
			while not gata[0]:
				try:
					serviciu.pas(time.monotonic())
				except (OSError, ValueError) as eroare:
					serviciu.opreste_publicarea()
					sterge(serviciu.cale("stare"))
					serviciu.noteaza("Astept reluarea publicarii: %s" % eroare, time.monotonic())
				trezeste.wait(PAUZA)
				trezeste.clear()
		finally:
			serviciu.opreste_publicarea()
			sterge(serviciu.cale("stare"))
			sterge(serviciu.cale("pid"))
			sterge(serviciu.cale("identitate"))
	return 0


def main(comanda):
	if comanda == "run":
		return ruleaza()
	if comanda not in ("start", "stop", "status", "restart", "reload"):
		print("Folosire: hds-nume-local start|stop|status|restart|reload")
		return 2
	pid = proces_serviciu()
	if comanda == "status":
		print("hds-nume-local: %s" % ("pornit" if pid else "oprit"))
		return 0 if pid else 3
	if comanda in ("stop", "restart") and pid:
		os.kill(pid, signal.SIGTERM)
		for _ in range(30):
			if proces_serviciu() != pid:
				break
			time.sleep(0.1)
		else:
			jurnal("Oprirea inca nu s-a terminat.")
			return 1
		pid = None
	if comanda in ("start", "reload", "restart"):
		if pid:
			os.kill(pid, signal.SIGHUP)
		else:
			copil = subprocess.Popen([sys.executable, os.path.abspath(__file__), "run"],
				stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
				stderr=subprocess.DEVNULL, start_new_session=True)
			for _ in range(20):
				if proces_serviciu():
					return 0
				if copil.poll() is not None:
					break
				time.sleep(0.05)
			jurnal("Serviciul nu a confirmat pornirea.")
			return 1
	return 0


if __name__ == "__main__":
	sys.exit(main(sys.argv[1] if len(sys.argv) == 2 else ""))
