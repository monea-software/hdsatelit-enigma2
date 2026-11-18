#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# hds-wifi-reporneste.py: porneste din nou cipul unei placi Wi-Fi USB, ca la scoaterea si bagarea stickului (0.7.7).
#
# De ce (asistenta 906594, Octagon SF8008 V3, Wi-Fi intern Realtek RTL8822CU, driverul 88x2cu; 15.11 si 10.11.2026):
# cadrele catre router au ramas dintr-odata fara confirmare (dump_mgntframe_and_wait_ack_timeout), driverul a declarat
# legatura pierduta, apoi 12 minute (pe 10.11, 2 ore) a cautat la 10 s fara sa mai auda routerul. wpa_supplicant cauta tot
# timpul, deci nu el lipsea. „Repornire retea” facea numai ifdown/ifup: driverul inchidea si deschidea interfata cu cipul
# lasat pornit (netdev_close/_netdev_open cu bup=1, hw_init_completed=_TRUE: firmware-ul nu se reincarca). Numai repornirea
# receptorului (initializarea completa a cipului) l-a legat imediat. Economia de energie era deja oprita in driver
# (rtw_init_pwrctrl_priv: IPS_mode=0, LPS_mode=0), deci nu ea e cauza.
#
# Ce face, pentru placa data (numai placi USB; altfel iese cu 3 si nu atinge nimic):
#   1. (fara --fara-ifupdown) ifdown placa; wpa_supplicant ramas pe ea se opreste (wpa_cli terminate, apoi pidfile-ul);
#   2. placa jos (ip link), apoi driverul se dezleaga de interfata USB si se leaga din nou (sysfs unbind/bind): driverul
#      face iesirea completa (cipul oprit) si pornirea completa (firmware-ul incarcat din nou la deschidere). Cu --usb:
#      resetul portului USB (ioctl USBDEVFS_RESET pe /dev/bus/usb/BBB/DDD; nucleul dezleaga si leaga singur driverele
#      placii), iar daca nu se poate, dezlegarea/legarea;
#   3. asteapta interfata din nou (dupa calea placii in sysfs, nu dupa nume); daca nucleul i-a dat alt nume, ii pune numele
#      vechi inapoi;
#   4. (fara --fara-ifupdown) ifup placa: wpa_supplicant porneste din nou din /etc/network/interfaces.
# „Repornire retea” (Components/Network.py restartNetwork, acelasi pe televizor si in pagina web) il cheama cu
# --fara-ifupdown intre `networking stop` si `networking start`; paznicul Wi-Fi (Components/HdsPazaWifi.py) il cheama
# intreg cand placa sta fara legatura. Un lacat (LACAT) tine o singura repornire odata. Un rand merge in jurnalul nucleului
# (/dev/kmsg, „hds-wifi:”), langa randurile driverului, si pe iesire. Fara adrese MAC, fara numele retelelor.
# Coduri: 0 bine; 2 placa nu exista; 3 placa nu e USB; 4 alta repornire nu s-a terminat; 5 interfata nu s-a intors;
# 6 sysfs a refuzat dezlegarea sau legarea; 1 argumente gresite.

import os
import subprocess
import sys
import time

SYS_NET = "/sys/class/net"
SYS_DRIVERE_USB = "/sys/bus/usb/drivers"
DEV_USB = "/dev/bus/usb"
CTRL_WPA = "/var/run/wpa_supplicant"
PID_WPA = "/var/run/wpa_supplicant.%s.pid"
LACAT = "/var/run/hds-wifi-reporneste.lock"
KMSG = "/dev/kmsg"
USBDEVFS_RESET = 0x5514          # _IO('U', 20), linux/usbdevice_fs.h
TERMEN_LACAT_S = 60.0
TERMEN_DISPARE_S = 10.0
TERMEN_REVINE_S = 30.0
TERMEN_IFDOWN_S = 30
TERMEN_IFUP_S = 60
TERMEN_CLI_S = 10

BINE, LIPSA, NU_USB, OCUPAT, NU_REVINE, SYSFS = 0, 2, 3, 4, 5, 6


class Sistem(object):
	"""Fisierele si comenzile, pe receptor. Probele de pe PC dau o radacina falsa (un dosar) si comenzi false."""

	def __init__(self, radacina=""):
		self.radacina = radacina

	def cale(self, c):
		return self.radacina + c

	def exista(self, c):
		return os.path.exists(self.cale(c))

	def citeste(self, c):
		try:
			with open(self.cale(c)) as f:
				return f.read().strip()
		except (IOError, OSError):
			return ""

	def scrie(self, c, text):
		with open(self.cale(c), "w") as f:
			f.write(text)

	def realpath(self, c):
		"""Calea reala, fara radacina (probele: legaturile din dosarul fals duc tot in el)."""
		r = os.path.realpath(self.cale(c))
		if self.radacina and r.startswith(os.path.realpath(self.radacina)):
			r = r[len(os.path.realpath(self.radacina)):] or "/"
		return r.replace("\\", "/")

	def listdir(self, c):
		try:
			return sorted(os.listdir(self.cale(c)))
		except OSError:
			return []

	def cmd(self, argv, termen):
		"""Codul unei comenzi date ca lista (fara shell); 127 cand programul lipseste, 124 la termen."""
		try:
			return subprocess.run(list(argv), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=termen).returncode
		except FileNotFoundError:
			return 127
		except subprocess.TimeoutExpired:
			return 124
		except OSError:
			return 126

	def ceas(self):
		return time.monotonic()

	def dormi(self, s):
		time.sleep(s)

	def omoara(self, pid, semnal):
		os.kill(pid, semnal)

	def reset_usb(self, nod):
		import fcntl
		fd = os.open(self.cale(nod), os.O_WRONLY)
		try:
			fcntl.ioctl(fd, USBDEVFS_RESET, 0)
		finally:
			os.close(fd)

	def lacat(self, termen):
		"""Lacatul (flock) tinut cat traieste procesul; None daca altul il tine mai mult de `termen` secunde."""
		import fcntl
		try:
			fd = os.open(self.cale(LACAT), os.O_RDWR | os.O_CREAT, 0o644)
		except OSError:
			return -1  # fara /var/run scriibil: fara lacat, dar repornirea merge
		sfarsit = self.ceas() + termen
		while True:
			try:
				fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
				return fd
			except OSError:
				if self.ceas() >= sfarsit:
					os.close(fd)
					return None
				self.dormi(0.5)

	def jurnal(self, text):
		try:
			with open(self.cale(KMSG), "w") as f:
				f.write("<6>hds-wifi: %s\n" % text)
		except (IOError, OSError):
			pass


def placa_usb(s, iface):
	"""{"dev": calea interfetei USB in sysfs, "intf": numele ei (1-2:1.2), "driver": numele driverului, "usb": calea
	placii USB (1-2), "nod": /dev/bus/usb/BBB/DDD sau ""} pentru o placa Wi-Fi USB; None daca placa lipseste; {} daca
	nu e USB (sau nu are driver legat)."""
	if not iface or "/" in iface or iface.startswith("."):
		return None
	if not s.exista(SYS_NET + "/" + iface):
		return None
	dev = s.realpath(SYS_NET + "/" + iface + "/device")
	intf = os.path.basename(dev)
	if os.path.basename(s.realpath(dev + "/subsystem")) != "usb" or ":" not in intf:
		return {}
	if not s.exista(dev + "/driver"):
		return {}
	driver = os.path.basename(s.realpath(dev + "/driver"))
	usb = os.path.dirname(dev)
	nod = ""
	bus, num = s.citeste(usb + "/busnum"), s.citeste(usb + "/devnum")
	if bus.isdigit() and num.isdigit():
		nod = "%s/%03d/%03d" % (DEV_USB, int(bus), int(num))
	return {"dev": dev, "intf": intf, "driver": driver, "usb": usb, "nod": nod}


def interfata(s, dev):
	"""Numele interfetei de retea a placii (din <dev>/net), sau None cat nu exista."""
	nume = [n for n in s.listdir(dev + "/net") if not n.startswith(".")]
	return nume[0] if nume else None


def opreste_supplicant(s, iface):
	"""wpa_supplicant ramas pe placa: intai rugat (wpa_cli terminate), apoi oprit dupa pidfile (numai daca procesul e
	chiar wpa_supplicant)."""
	if s.exista(CTRL_WPA + "/" + iface):
		s.cmd(("wpa_cli", "-p", CTRL_WPA, "-i", iface, "terminate"), TERMEN_CLI_S)
	pid = s.citeste(PID_WPA % iface)
	if not pid.isdigit():
		return
	for semnal in (15, 9):
		if s.citeste("/proc/%s/comm" % pid) != "wpa_supplicant":
			return
		try:
			s.omoara(int(pid), semnal)
		except OSError:
			return
		sfarsit = s.ceas() + 3.0
		while s.ceas() < sfarsit and s.citeste("/proc/%s/comm" % pid) == "wpa_supplicant":
			s.dormi(0.2)


def asteapta(s, conditie, termen, pas=0.2):
	sfarsit = s.ceas() + termen
	while True:
		r = conditie()
		if r or s.ceas() >= sfarsit:
			return r
		s.dormi(pas)


def dezleaga_leaga(s, p):
	"""unbind, asteptarea plecarii interfetei, bind. "" daca sysfs a primit amandoua scrierile; "unbind" daca a refuzat
	dezlegarea (nimic nu s-a schimbat); "bind" daca a refuzat de doua ori legarea (placa a ramas fara driver)."""
	sofer = SYS_DRIVERE_USB + "/" + p["driver"]
	try:
		s.scrie(sofer + "/unbind", p["intf"])
	except (IOError, OSError):
		return "unbind"
	asteapta(s, lambda: interfata(s, p["dev"]) is None, TERMEN_DISPARE_S)
	for _incercare in (1, 2):
		try:
			s.scrie(sofer + "/bind", p["intf"])
			return ""
		except (IOError, OSError):
			s.dormi(1.0)
	return "bind"


def reporneste(iface, usb=False, ifupdown=True, s=None):
	"""(cod, text) dupa repornirea cipului placii `iface`."""
	s = s or Sistem()
	p = placa_usb(s, iface)
	if p is None:
		return LIPSA, "%s nu exista" % iface
	if not p:
		return NU_USB, "%s nu e o placa USB: nu se reporneste" % iface
	fd = s.lacat(TERMEN_LACAT_S)
	if fd is None:
		return OCUPAT, "%s: alta repornire a placii Wi-Fi nu s-a terminat" % iface
	t0 = s.ceas()
	if ifupdown:
		s.cmd(("ifdown", iface), TERMEN_IFDOWN_S)
	opreste_supplicant(s, iface)
	s.cmd(("ip", "link", "set", iface, "down"), TERMEN_CLI_S)
	fel = "dezlegare/legare"
	refuz = None
	if usb and p["nod"] and s.exista(p["nod"]):
		try:
			s.reset_usb(p["nod"])
			fel = "reset USB"
			refuz = ""
		except (IOError, OSError):
			refuz = None
	if refuz is None:
		refuz = dezleaga_leaga(s, p)
	if refuz:
		text = "%s: sysfs a refuzat %s (driver %s)" % (iface, "dezlegarea" if refuz == "unbind" else "legarea", p["driver"])
		s.jurnal(text)
		if ifupdown and refuz == "unbind":
			s.cmd(("ifup", iface), TERMEN_IFUP_S)  # nimic schimbat: placa pornita inapoi, ca inainte
		return SYSFS, text
	nume = asteapta(s, lambda: interfata(s, p["dev"]), TERMEN_REVINE_S)
	if nume is None:
		text = "%s: interfata nu s-a intors in %d s dupa %s (driver %s)" % (iface, TERMEN_REVINE_S, fel, p["driver"])
		s.jurnal(text)
		return NU_REVINE, text
	if nume != iface:
		s.cmd(("ip", "link", "set", nume, "name", iface), TERMEN_CLI_S)
	durata = s.ceas() - t0
	if ifupdown:
		s.cmd(("ifup", iface), TERMEN_IFUP_S)
	text = "%s: cipul pornit din nou (%s, driver %s), interfata inapoi dupa %.1f s" % (iface, fel, p["driver"], durata)
	s.jurnal(text)
	return BINE, text


def main(argv):
	usb = "--usb" in argv
	ifupdown = "--fara-ifupdown" not in argv
	rest = [a for a in argv if a not in ("--usb", "--fara-ifupdown")]
	if len(rest) != 1 or rest[0].startswith("-"):
		sys.stderr.write("Utilizare: hds-wifi-reporneste.py [--usb] [--fara-ifupdown] PLACA\n")
		return 1
	cod, text = reporneste(rest[0], usb=usb, ifupdown=ifupdown)
	print(text)
	return cod


if __name__ == "__main__":
	sys.exit(main(sys.argv[1:]))
