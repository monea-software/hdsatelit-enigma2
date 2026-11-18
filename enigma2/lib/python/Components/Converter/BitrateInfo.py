# -*- coding: utf-8 -*-
# Luat din sursele GPL-2.0 ale unui enigma2 public (commitul 73ab10edaeee, 15.11.2026), fisierul
# lib/python/Components/Converter/BitrateInfo.py, cu pragul separat pentru sunet din alta ramura GPL-2.0 a aceluiasi fisier.
# Licenta GPL-2.0 (ca enigma2). Adus in imaginea HD Satelit (TPF, 15.11.2026) pentru temele care il cer (2 teme din feeduri).
#
# Schimbat pentru imaginea HD Satelit: pe canalele DVB (satelit, cablu, terestru) debitul il masoara serviciul pe demux
# (iServiceInformation.sVideoBitrate / sAudioBitrate, lib/service/servicedvb.cpp getLiveBitrate, BRT 15.11.2026), numai cat
# timp convertorul e pe ecran: se opreste singur la 5 s dupa ce nu mai intreaba nimeni. Unde serviciul nu le masoara
# (fluxurile de internet, fisierele, timeshift: -1) convertorul ia debitul pe care il spune fluxul (sTagBitrate: la video
# cand fluxul are imagine, altfel la sunet). O valoare pe care nu o stim ramane goala (textul "" si boolean False), nu "0 kbit/s".
#
# BitrateInfo converter: exposes the current video / audio bitrate of the playing service.
#
# This converter polls the values every second:
#   - a negative value means "nothing to measure (yet)" and is ignored
#   - readings below MIN_VALID_KBPS are dropped as gaps in the data
#   - the last 10 valid readings are averaged
#   - the last feasible value stays on screen until a new valid one arrives
#     (it only becomes 0 on a new zap)
#
# One measurement is shared by all widgets using this converter.
#
# Usage in a skin:
#   <widget source="session.CurrentService" render="Label" ...>
#       <convert type="BitrateInfo">Video</convert>
#   </widget>
#
# Types: Video      -> "12345 kbit/s"
#        Audio      -> "256 kbit/s"
#        Both       -> "V: 12345 kbit/s  A: 256 kbit/s"
#        VideoValue -> "12345"        (no unit)
#        AudioValue -> "256"

from enigma import eTimer, iServiceInformation

import NavigationInstance
from Components.Converter.Converter import Converter
from Components.Element import cached

# readings below this (kbit/s) are treated as gaps in the data, not as the real rate; separate limits for (video, audio):
# one limit of 100 hid every audio stream below 100 kbit/s (normal for HE-AAC and low-rate AAC)
MIN_VALID_KBPS = (100, 8)

# masurarea din serviciu (kbit/s; None numai pe un enigma2 fara ele, de pilda o imagine mai veche cu acest fisier)
_S_VIDEO = getattr(iServiceInformation, "sVideoBitrate", None)
_S_AUDIO = getattr(iServiceInformation, "sAudioBitrate", None)
_S_TAG = getattr(iServiceInformation, "sTagBitrate", None)
_S_INALTIME = getattr(iServiceInformation, "sVideoHeight", None)


def _citeste(info, cheie):
	if cheie is None:
		return -1
	try:
		v = info.getInfo(cheie)
	except Exception:
		return -1
	return v if isinstance(v, int) else -1


def debite(info):
	"""(video, sunet) in kbit/s din ce spune serviciul; -1 = nu se stie."""
	v = _citeste(info, _S_VIDEO)
	a = _citeste(info, _S_AUDIO)
	# <= 0: un player strain (de pilda ServiceApp) poate raspunde 0 la cheile pe care nu le cunoaste; pe DVB sTagBitrate e -1,
	# deci prima fereastra a masurarii (0) ramane 0
	if v <= 0 and a <= 0:
		# debitul spus de flux (GStreamer da biti pe secunda) e al intregului flux: la un flux cu imagine il punem la video,
		# la unul numai cu sunet (radio) la sunet; celalalt ramane necunoscut
		t = _citeste(info, _S_TAG)
		if t > 0:
			t = t // 1000 if t >= 1000 else t
			if _citeste(info, _S_INALTIME) > 0:
				v = t
			else:
				a = t
	return v, a


class BitrateEngine:
	def __init__(self):
		self.users = []
		self.running = False
		self.sref = None
		self.pollHist = [[], []]
		self.vcur = 0
		self.acur = 0
		self.pollTimer = eTimer()
		self.pollTimer.callback.append(self.pollService)

	def attach(self, user):
		if user not in self.users:
			self.users.append(user)

	def detach(self, user):
		if user in self.users:
			self.users.remove(user)
		if not self.users:
			self.stop()

	def notify(self):
		for user in self.users[:]:
			user.refresh()

	def getService(self):
		nav = NavigationInstance.instance
		return nav and nav.getCurrentService()

	def update(self):
		# called whenever the service or its info changed: restart when the service differs
		if not self.users:
			return
		service = self.getService()
		if not service:
			self.stop()
			return
		info = service.info()
		sref = info and info.getInfoString(iServiceInformation.sServiceref)
		if self.running and sref == self.sref:
			return
		self.stop()
		self.sref = sref
		self.running = True
		self.pollHist = [[], []]
		self.pollTimer.start(1000, False)

	def stop(self):
		self.pollTimer.stop()
		self.running = False
		self.sref = None
		if self.vcur or self.acur:
			self.vcur = self.acur = 0
			self.notify()

	def pollService(self):
		service = self.getService()
		info = service and service.info()
		if not info:
			return
		v, a = debite(info)
		if v < 0 and a < 0:
			return
		smooth = []
		for idx, val in enumerate((v, a)):
			hist = self.pollHist[idx]
			if val >= MIN_VALID_KBPS[idx]:
				hist.append(val)
				del hist[:-10]
			smooth.append(sum(hist) // len(hist) if hist else 0)
		if smooth != [self.vcur, self.acur]:
			self.vcur, self.acur = smooth
			self.notify()


engine = BitrateEngine()


class BitrateInfo(Converter):
	VIDEO = 0
	AUDIO = 1
	BOTH = 2
	VIDEO_VALUE = 3
	AUDIO_VALUE = 4

	def __init__(self, type):
		Converter.__init__(self, type)
		self.type = {
			"Video": self.VIDEO,
			"Audio": self.AUDIO,
			"VideoValue": self.VIDEO_VALUE,
			"AudioValue": self.AUDIO_VALUE,
		}.get(type, self.BOTH)

	def refresh(self):
		Converter.changed(self, (self.CHANGED_POLL,))

	@cached
	def getText(self):
		video, audio = engine.vcur, engine.acur
		if self.type == self.VIDEO:
			return "%d kbit/s" % video if video > 0 else ""
		if self.type == self.AUDIO:
			return "%d kbit/s" % audio if audio > 0 else ""
		if self.type == self.VIDEO_VALUE:
			return "%d" % video if video > 0 else ""
		if self.type == self.AUDIO_VALUE:
			return "%d" % audio if audio > 0 else ""
		parti = []
		if video > 0:
			parti.append("V: %d kbit/s" % video)
		if audio > 0:
			parti.append("A: %d kbit/s" % audio)
		return "  ".join(parti)

	text = property(getText)

	@cached
	def getBoolean(self):
		video, audio = engine.vcur, engine.acur
		if self.type in (self.VIDEO, self.VIDEO_VALUE):
			return video > 0
		elif self.type in (self.AUDIO, self.AUDIO_VALUE):
			return audio > 0
		else:
			return video > 0 or audio > 0

	boolean = property(getBoolean)

	def changed(self, what):
		if what[0] == self.CHANGED_CLEAR:
			engine.detach(self)
		elif what[0] != self.CHANGED_POLL and not self.suspended:
			engine.attach(self)
			engine.update()
		Converter.changed(self, what)

	def doSuspend(self, suspended):
		if suspended:
			engine.detach(self)
		else:
			engine.attach(self)
			engine.update()

	def destroy(self):
		engine.detach(self)
		Converter.destroy(self)
