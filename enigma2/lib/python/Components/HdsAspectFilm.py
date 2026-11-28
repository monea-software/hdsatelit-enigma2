# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsAspectFilm.py (0.8.0): the picture of wide films with square pixels on Broadcom, for every player.
# ASP9 (dfc8f4900) made it for Filme si seriale (Screens/HdsFilmeSeriale.HdsVodPlayer); AIP0 moved it here, unchanged, so the
# 4097/5001/5002 services started from the channel list (IPTV, files) get it too: leagaNavigatie(nav) puts a listener on the
# events of the navigation (start, new info, new video size, end). One shared AspectFilm (comun()) for both, so the window and
# the policy to put back are kept in one place.

# ---- the picture of wide films on Broadcom (0.8.0, Vu+ Solo4K)
# A film with square pixels (1280x534, 720x302, 1920x1080) played by servicemp3 is told with aspect 1 (iswidescreen false) and the
# Broadcom driver puts it in a 4:3 box: stretched up and down. No policy (policy, policy2, the 4:3 programmes row) changes that;
# measured on the receiver of the man: the video window (/proc/stb/vmpeg/0/dst_*, 720x576, hex) set to the real ratio of the
# picture with policy "bestfit" shows it right. So while such a film plays, the window gets the real ratio; on another service and
# when the player closes, the whole screen and the policy from before come back. Only where the driver has the window and "bestfit"
# and is not HiSilicon (there the policy2 row of the video settings does the job); nothing written anywhere else.
def aspectFereastra(latime, inaltime, aspect):
	"""(left, top, width, height) in 720x576 for a picture at least 14:9 told with aspect < 2, or None (whole screen)"""
	try:
		latime, inaltime, aspect = int(latime), int(inaltime), int(aspect)
	except (TypeError, ValueError):
		return None
	if latime <= 0 or inaltime <= 0 or aspect >= 2 or latime * 9 < inaltime * 14:
		return None
	if latime * 9 >= inaltime * 16:
		h = 576 * 16 * inaltime // (9 * latime)
		return (0, (576 - h) // 2, 720, h)
	w = 720 * 9 * latime // (16 * inaltime)
	return ((720 - w) // 2, 0, w, 576)


class AspectFilm(object):
	"""Keeps the video window on the real ratio of a wide film (aspectFereastra) and puts back what was there. rad: a test root."""

	def __init__(self, rad="/"):
		self.rad = rad or "/"
		self.ultim = None
		self.politica0 = None
		self.merge = None

	def _cale(self, rel):
		import os
		return os.path.join(self.rad, rel)

	def _citeste(self, rel):
		try:
			with open(self._cale(rel)) as f:
				return f.read().strip()
		except Exception:
			return ""

	def _scrie(self, rel, valoare):
		try:
			with open(self._cale(rel), "w") as f:
				f.write(valoare)
		except Exception as e:
			print("[HdsAspectFilm] aspect %s: %s" % (rel, type(e).__name__))

	def poate(self):
		if self.merge is None:
			import os
			# the same marks as SystemInfo["HiSilicon"], read under rad
			hisi = any(os.path.exists(self._cale(c)) for c in ("proc/hisi", "proc/msp", "usr/bin/hihalt", "usr/lib/hisilicon"))
			self.merge = not hisi and os.path.exists(self._cale("proc/stb/vmpeg/0/dst_left")) \
				and "bestfit" in self._citeste("proc/stb/video/policy_choices").split()
		return self.merge

	def _pune(self, fereastra, politica):
		for nume, v in zip(("left", "top", "width", "height"), fereastra):
			self._scrie("proc/stb/vmpeg/0/dst_" + nume, "%08x" % v)
		self._scrie("proc/stb/vmpeg/0/dst_apply", "1")
		if politica:
			self._scrie("proc/stb/video/policy", politica)

	def pas(self, film, latime, inaltime, aspect):
		"""film: the service is a 4097 one; called on every tick, writes only when the window has to change"""
		stare = aspectFereastra(latime, inaltime, aspect) if film and self.poate() else None
		if stare == self.ultim:
			return
		if stare is None:
			self.laSfarsit()
			return
		if self.ultim is None:
			self.politica0 = self._citeste("proc/stb/video/policy")
		self._pune(stare, "bestfit")
		print("[HdsAspectFilm] aspect %sx%s (%s): window %s" % (latime, inaltime, aspect, stare))
		self.ultim = stare

	def reaplica(self):
		"""back from a window over the film (the aspect key, Video settings): a policy chosen there replaced bestfit; it becomes
		the one put back at the end, and the window is written again"""
		if self.ultim is not None:
			p = self._citeste("proc/stb/video/policy")
			if p and p != "bestfit":
				self.politica0 = p
			self._pune(self.ultim, "bestfit")

	def laSfarsit(self):
		if self.ultim is not None:
			self._pune((0, 0, 0, 0), self.politica0)
			print("[HdsAspectFilm] aspect: whole screen, policy %s" % self.politica0)
		self.ultim = None

	def verifica(self):
		"""AIP0: while the window is ours, put it back when something else wrote over it (the picture of a channel list
		closed: the full screen; a policy chosen in the video settings becomes the one put back at the end)."""
		if self.ultim is None:
			return
		acum = tuple(self._citeste("proc/stb/vmpeg/0/dst_" + n) for n in ("left", "top", "width", "height"))
		p = self._citeste("proc/stb/video/policy")
		if acum == tuple("%08x" % v for v in self.ultim) and p == "bestfit":
			return
		if p and p != "bestfit":
			self.politica0 = p
		self._pune(self.ultim, "bestfit")
		print("[HdsAspectFilm] aspect: window written again %s" % (self.ultim,))


_comun = []


def comun():
	"""The one AspectFilm of the image (the film player and the channel list share it)."""
	if not _comun:
		_comun.append(AspectFilm())
	return _comun[0]


TIPURI = (4097, 5001, 5002)
# the screens over which the window may be written: the player bars; a channel list with its picture (Pig) or another
# screen uses decoder 0's window for itself, so then nothing is written and the 1 s check puts it back after
ECRANE = ("InfoBar", "MoviePlayer", "HdsVodPlayer")
VERIFICARE_MS = 1000
_ceas = []


def _ecranLiber():
	"""True when a player bar (or nothing known) is in front, False under a channel list with picture or another screen."""
	import sys
	ib = getattr(sys.modules.get("Screens.InfoBar"), "InfoBar", None)
	inst = getattr(ib, "instance", None)
	sesiune = getattr(inst, "session", None)
	if sesiune is None:
		return True
	d = getattr(sesiune, "current_dialog", None)
	return d is None or any(c.__name__ in ECRANE for c in type(d).__mro__)


def _hbbtv(ref):
	"""The film of an HbbTV application (HdsHbbtvPornire plays it as a 4097 named "HbbTV" in the window the page asks)."""
	try:
		return ref.getName() == "HbbTV"
	except Exception:
		return False


def pasNavigatie(nav, aspect=None, ecranLiber=None):
	"""The window for what plays now: a 4097/5001/5002 service with its size and aspect, else the whole screen."""
	a = aspect or comun()
	liber = ecranLiber or _ecranLiber
	try:
		from enigma import iServiceInformation
		ref = nav.getCurrentlyPlayingServiceReference()
		s = nav.getCurrentService()
		info = s and s.info()
		if ref is None or ref.type not in TIPURI or not info or _hbbtv(ref) or not a.poate():
			_opresteCeas()
			a.pas(False, 0, 0, 0)
			return
		_pornesteCeas(nav)
		if not liber():
			return
		a.pas(True, info.getInfo(iServiceInformation.sVideoWidth), info.getInfo(iServiceInformation.sVideoHeight),
			info.getInfo(iServiceInformation.sAspect))
		a.verifica()
	except Exception as e:
		print("[HdsAspectFilm] %s" % type(e).__name__)


def _pornesteCeas(nav):
	try:
		if not _ceas:
			from enigma import eTimer
			t = eTimer()
			t.callback.append(lambda: pasNavigatie(nav))
			_ceas.append(t)
		if not _ceas[0].isActive():
			_ceas[0].start(VERIFICARE_MS, False)
	except Exception as e:
		print("[HdsAspectFilm] ceas: %s" % type(e).__name__)


def _opresteCeas():
	if _ceas:
		try:
			_ceas[0].stop()
		except Exception:
			pass


def leagaNavigatie(nav):
	"""Listener on nav.event: on start, new info, new video size and end of a service the window is set again; while such a
	service plays, a 1 s check (only /proc reads) puts the window back after a channel list with picture or the settings."""
	try:
		from enigma import iPlayableService as P
	except ImportError:
		return
	ev = tuple(e for e in (getattr(P, n, None) for n in ("evStart", "evUpdatedInfo", "evVideoSizeChanged", "evEnd"))
		if e is not None)

	def laEveniment(i):
		if i in ev:
			pasNavigatie(nav)
	nav.event.append(laEveniment)
	return laEveniment
