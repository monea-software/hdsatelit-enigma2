# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsLcdTv (0.8.0): imaginea TV pe afisajul color, pentru receptoarele al caror driver
# nu are /proc/stb/lcd/live_enable sau /proc/stb/fb/sd_detach (Dreambox DM900/DM920).
# Alegerea vine din setarea afisajului „Imaginea de pe televizor” (HdsAfisajColor.IesireLive scrie
# /etc/enigma2/hdslcdtv: 0 = nu, 1 = numai imaginea, 3 = imaginea cu OSD).
# Porneste lcdtv.py (grab -> /tmp/lcdtv.raw) si scrie cadrul pe fd-ul afisajului luat cu eDBoxLCD.lock().
# Numai pe afisajul Dream (colorformat BGR_565_LE, fara live_enable): pe celelalte receptoare pluginul nu porneste nimic.
# Costa procesor (~9 % pe DM900 la 2 cadre pe secunda), de aceea alegerea e „Nu” din fabrica.
import os, subprocess
from enigma import eTimer, eDBoxLCD
from Plugins.Plugin import PluginDescriptor
import Screens.Standby

AICI = os.path.dirname(__file__)
ALEGERE = "/etc/enigma2/hdslcdtv"


def citeste():
	try:
		with open(ALEGERE) as f:
			return f.read(8).strip()
	except OSError:
		return "0"


def omoaraRamase():
	# buclele ramase de la o interfata anterioara (enigma2 repornit nu-si omoara copiii)
	for p in os.listdir("/proc"):
		if p.isdigit() and int(p) != os.getpid():
			try:
				with open("/proc/%s/cmdline" % p, "rb") as f:
					if b"HdsLcdTv/lcdtv.py" in f.read():
						os.kill(int(p), 9)
			except Exception:
				pass


class LcdTv(object):
	def __init__(self):
		omoaraRamase()
		self.proc = None
		self.mod = None
		self.fd = -1
		self.mtime = 0
		self.timer = eTimer()
		self.timer.callback.append(self.pas)
		self.timer.start(400, False)

	def porneste(self, mod):
		if self.proc is not None and (self.proc.poll() is not None or self.mod != mod):
			self.opresteBucla()
		if self.proc is None:
			self.mod = mod
			self.proc = subprocess.Popen(["python3", os.path.join(AICI, "lcdtv.py"), "0.4", mod],
				stdout=open("/tmp/lcdtv.log", "a"), stderr=subprocess.STDOUT)
		if self.fd < 0:
			self.fd = eDBoxLCD.getInstance().lock()

	def opresteBucla(self):
		if self.proc is not None:
			try:
				self.proc.kill(); self.proc.wait()
			except Exception:
				pass
			self.proc = None

	def opreste(self):
		self.opresteBucla()
		if self.fd >= 0:
			eDBoxLCD.getInstance().unlock()
			self.fd = -1
			eDBoxLCD.getInstance().update()

	def pas(self):
		mod = citeste()
		if mod not in ("1", "3") or Screens.Standby.inStandby:
			self.opreste(); return
		self.porneste(mod)
		if self.fd < 0:
			return
		try:
			m = os.stat("/tmp/lcdtv.raw").st_mtime
			if m != self.mtime:
				self.mtime = m
				with open("/tmp/lcdtv.raw", "rb") as f:
					os.write(self.fd, f.read())
		except Exception:
			pass

lcdtv = None

def sessionstart(reason, **kw):
	global lcdtv
	if reason == 0 and lcdtv is None:
		lcdtv = LcdTv()

def afisajDream(radacina="/proc/stb/lcd"):
	"""Afisajul color Dream fara imagine live in driver (DM900/DM920): colorformat BGR_565_LE si niciun live_enable."""
	try:
		with open(os.path.join(radacina, "colorformat")) as f:
			format = f.read(32).strip()
	except OSError:
		return False
	return format == "BGR_565_LE" and not os.path.exists(os.path.join(radacina, "live_enable"))


def Plugins(**kw):
	if not afisajDream():
		return []
	return [PluginDescriptor(where=PluginDescriptor.WHERE_SESSIONSTART, fnc=sessionstart)]
