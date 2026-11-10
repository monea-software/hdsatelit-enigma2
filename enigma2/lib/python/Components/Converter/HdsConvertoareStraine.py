# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsConvertoareStraine.py: convertoarele cerute de temele externe. Modulul nu se incarca deloc cat nu se deschide un ecran dintr-o
# tema externa care cere unul dintre ele; ecranele imaginii primesc convertoarele imaginii, neschimbate.
#
# Cele cu tipuri in plus (au numele convertorului imaginii si deriva din el; le da skin.py, readSourceWidget, numai ecranelor din tema):
#   ServiceInfo, EventName, EventTime, ClockToText, ServiceName, FrontendInfo, ConditionalShowHide, TemplatedMultiContent, RdsInfo, MovieInfo,
#   TunerInfo.
# Cele pe care imaginea nu le are, cu numele din XML. Nu sunt fisiere proprii in Components/Converter, ca un pachet de tema care aduce un
# fisier cu acelasi nume sa se instaleze fara conflict si sa ramana al lui (Components/HdsTemaExterna.py le arata importului numai cand
# nu exista fisierul): ClientsStreaming, CpuUsage, CryptoInfo, EventInfo, ExtendedServiceInfo, HddState, LayoutInfo, MovieReference,
# PliExtraInfo, RotorPosition, ServiceName2, ServiceOrbitalPosition, StreamInfo, TransponderInfo, VAudioInfo, VNetSpeedInfo, VServiceInfo.
#
# Datele vin din ce are imaginea (HdsCommon, HdsInfo, ghidul); o valoare pe care nu o stim ramane goala, nu se inventeaza.
import time

from enigma import iServiceInformation, iPlayableService
from Components.Converter.Converter import Converter
from Components.Converter.Poll import Poll
from Components.Element import cached
from Components.Converter.ServiceInfo import ServiceInfo as _ServiceInfo
from Components.Converter.EventName import EventName as _EventName
from Components.Converter.EventTime import EventTime as _EventTime
from Components.Converter.ClockToText import ClockToText as _ClockToText
from Components.Converter.ServiceName import ServiceName as _ServiceName
from Components.Converter.ConditionalShowHide import ConditionalShowHide as _ConditionalShowHide
from Components.Converter.FrontendInfo import FrontendInfo as _FrontendInfo
from Components.Converter.RdsInfo import RdsInfo as _RdsInfo
from Components.Converter.MovieInfo import MovieInfo as _MovieInfo
from Components.Converter.TunerInfo import TunerInfo as _TunerInfo
from Components.Converter.StringList import StringList
from Components.Converter.TemplatedMultiContent import TemplatedMultiContent as _TemplatedMultiContent

try:
	from Components.Converter import HdsCommon as C
except Exception:
	C = None

_LAT = (3, 4, 7, 8, 0xB, 0xC, 0xF, 0x10)  # sAspect pentru imaginea lata (ca IsWidescreen al imaginii)
_EV_VIDEO = (iPlayableService.evVideoSizeChanged, iPlayableService.evUpdatedInfo)
_EV_INFO = (iPlayableService.evUpdatedInfo,)
_EV_TOATE = tuple(getattr(iPlayableService, n) for n in ("evStart", "evEnd", "evUpdatedInfo", "evVideoSizeChanged") if hasattr(iPlayableService, n))


def _inaltime(info):
	return info.getInfo(iServiceInformation.sVideoHeight)


def _descriereSunet(service):
	"""Descrierea pistei de sunet ascultate acum (pistele nu spun mai mult de atat), sau ""."""
	try:
		audio = service.audioTracks()
		if not audio or audio.getNumberOfTracks() <= 0:
			return ""
		i = audio.getCurrentTrack()
		return audio.getTrackInfo(i if i >= 0 else 0).getDescription() or ""
	except Exception:
		return ""


def _gama(info):
	s = getattr(iServiceInformation, "sGamma", None)
	return info.getInfo(s) if s is not None else -1


def _esteFlux(info):
	try:
		return info.getInfoString(iServiceInformation.sServiceref).split(":")[0] in ("4097", "5001", "5002", "8193")
	except Exception:
		return False


def _subtitrari(service):
	try:
		s = service.subtitle()
		return bool(s and s.getSubtitleList())
	except Exception:
		return False


def _sunetLa(service):
	try:
		a = service.audioTracks()
		return bool(a and a.getNumberOfTracks() > 1)
	except Exception:
		return False


def _cuvantInCodec(info, *cuvinte):
	if C is None:
		return False
	try:
		t = str(C.video_codec_name(info) if hasattr(C, "video_codec_name") else "").upper()
	except Exception:
		return False
	return any(c in t for c in cuvinte)


def _codecVideo(info):
	return info.getInfo(iServiceInformation.sVideoType)


# tipurile in plus: functia (service, info) -> boolean, si evenimentele
_BOOL = {
	"IsStereo": (lambda s, i: "stereo" in _descriereSunet(s).lower(), _EV_INFO),
	"IsAudioStereo": (lambda s, i: "stereo" in _descriereSunet(s).lower(), _EV_INFO),
	"IsAudio20": (lambda s, i: "2.0" in _descriereSunet(s) or "stereo" in _descriereSunet(s).lower(), _EV_INFO),
	"IsAudio51": (lambda s, i: "5.1" in _descriereSunet(s), _EV_INFO),
	"IsAudio71": (lambda s, i: "7.1" in _descriereSunet(s), _EV_INFO),
	"IsMPEG1LayerII": (lambda s, i: "MPEG" in _descriereSunet(s).upper(), _EV_INFO),
	"IsNotWidescreen": (lambda s, i: i.getInfo(iServiceInformation.sAspect) not in _LAT, _EV_VIDEO),
	"IsStream": (lambda s, i: _esteFlux(i), _EV_INFO),
	"IsIPStream": (lambda s, i: _esteFlux(i), _EV_INFO),
	"IsDAB": (lambda s, i: False, _EV_INFO),
	"IsSoftCSA": (lambda s, i: False, _EV_INFO),
	"HasTeletext": (lambda s, i: i.getInfo(iServiceInformation.sTXTPID) > 0, _EV_INFO),
	"AudioTracksAvailable": (lambda s, i: _sunetLa(s), _EV_INFO),
	"SubtitlesAvailable": (lambda s, i: _subtitrari(s), _EV_INFO),
	"Is1080": (lambda s, i: 800 < _inaltime(i) < 1500, _EV_VIDEO),
	"Is720": (lambda s, i: 600 < _inaltime(i) <= 800, _EV_VIDEO),
	"Is576": (lambda s, i: 500 < _inaltime(i) <= 600, _EV_VIDEO),
	"Is480": (lambda s, i: 0 < _inaltime(i) <= 500, _EV_VIDEO),
	"IsSD": (lambda s, i: 0 < _inaltime(i) < 720, _EV_VIDEO),
	"IsHD": (lambda s, i: 720 <= _inaltime(i) < 1500, _EV_VIDEO),
	"Is4K": (lambda s, i: _inaltime(i) >= 1500, _EV_VIDEO),
	"IsSDAndWidescreen": (lambda s, i: 0 < _inaltime(i) < 720 and i.getInfo(iServiceInformation.sAspect) in _LAT, _EV_VIDEO),
	"IsSDAndNotWidescreen": (lambda s, i: 0 < _inaltime(i) < 720 and i.getInfo(iServiceInformation.sAspect) not in _LAT, _EV_VIDEO),
	"IsHDHDR": (lambda s, i: _gama(i) > 0 and 720 <= _inaltime(i), _EV_VIDEO),
	"IsVideoMPEG2": (lambda s, i: _codecVideo(i) == 0, _EV_VIDEO),
	"IsVideoAVC": (lambda s, i: _codecVideo(i) == 1, _EV_VIDEO),
	"IsVideoHEVC": (lambda s, i: _codecVideo(i) in (6, 7), _EV_VIDEO),
}


def _areHbbtv(s, i):
	s_ait = getattr(iServiceInformation, "sAITPID", None)
	if s_ait is not None:
		return i.getInfo(s_ait) > 0
	s_url = getattr(iServiceInformation, "sHBBTVUrl", None)
	return bool(s_url is not None and i.getInfoString(s_url))


_BOOL["HasHBBTV"] = (_areHbbtv, (iPlayableService.evUpdatedInfo, getattr(iPlayableService, "evHBBTVInfo", iPlayableService.evUpdatedInfo)))


def _textVideo(s, i):
	w, h = i.getInfo(iServiceInformation.sVideoWidth), _inaltime(i)
	return "%dx%d" % (w, h) if w > 0 and h > 0 else ""


# tipurile in plus care dau text
_TEXT = {
	"VideoInfo": (_textVideo, _EV_VIDEO),
	"AudioCodecIcon": (lambda s, i: _descriereSunet(s), _EV_INFO),
}


class ServiceInfo(_ServiceInfo):
	def __init__(self, type):
		self.hdsBool = _BOOL.get(type)
		self.hdsText = _TEXT.get(type)
		if self.hdsBool or self.hdsText:
			Converter.__init__(self, type)
			self.type = -1
			self.interesting_events = (self.hdsBool or self.hdsText)[1]
		else:
			_ServiceInfo.__init__(self, type)

	@cached
	def getBoolean(self):
		if self.hdsText:
			return bool(self.getText())
		if not self.hdsBool:
			return _ServiceInfo.getBoolean(self)
		service = self.source.service
		info = service and service.info()
		if not info:
			return False
		try:
			return bool(self.hdsBool[0](service, info))
		except Exception:
			return False

	boolean = property(getBoolean)

	@cached
	def getText(self):
		if self.hdsBool:
			return ""
		if not self.hdsText:
			return _ServiceInfo.getText(self)
		service = self.source.service
		info = service and service.info()
		if not info:
			return ""
		try:
			return self.hdsText[0](service, info)
		except Exception:
			return ""

	text = property(getText)

	@cached
	def getValue(self):
		if self.hdsBool or self.hdsText:
			return -1
		return _ServiceInfo.getValue(self)

	value = property(getValue)


# ------------------------------------------------------------------ ghidul: emisiunile de acum si urmatoarele

def referintaCanal(source):
	"""Referinta (text) a canalului sursei, sau None: cel redat (session.Event_Now, CurrentService) sau cel ales intr-o lista."""
	try:
		nav = getattr(source, "navcore", None)
		if nav is not None:
			r = nav.getCurrentlyPlayingServiceReference()
			return r.toString() if r else None
		ref = getattr(source, "service", None)
		if ref is None:
			return None
		if hasattr(ref, "toString"):
			return ref.toString()
		info = ref.info()
		return info and info.getInfoString(iServiceInformation.sServiceref)
	except Exception:
		return None


def emisiuni(source, cate=3):
	"""[(inceput, durata, titlu, scurt, lung)] din ghid, de acum inainte; [] cand ghidul nu stie."""
	ref = referintaCanal(source)
	if not ref:
		return []
	try:
		from enigma import eEPGCache
		return (eEPGCache.getInstance().lookupEvent(["BDTSE", (ref, 0, -1, 24 * 60)]) or [])[:cate]
	except Exception:
		return []


def _ora(t):
	return time.strftime("%H:%M", time.localtime(t))


def _interval(inceput, durata):
	return "%s - %s" % (_ora(inceput), _ora(inceput + durata))


_NUME_DUPA = {"NextName": (1, 2), "NameNext": (1, 2), "NextNameOnly": (1, 2), "NextDescription": (1, 3), "ThirdName": (2, 2), "ThirdNameOnly": (2, 2),
	"ThirdDescription": (2, 3), "NowName": (0, 2), "NameNow": (0, 2)}


class EventName(_EventName):
	def __init__(self, type):
		_EventName.__init__(self, type)
		self.hdsPdc = type == "Pdc"
		self.hdsDupa = _NUME_DUPA.get(type)
		self.hdsGen = type in ("Genre", "GenreList")
		self.hdsVarsta = type in ("Rating", "SmallRating", "RatingTextAndColor")
		self.hdsScurt = type == "ShortDescription"
		self.hdsCampuri = None
		parti = [p for p in (type or "").split(",")]
		if len(parti) > 1 and all(p.strip().isupper() for p in parti[1:]):
			self.hdsCampuri = (parti[0], [p.strip() for p in parti[1:]])

	def _gen(self, ev):
		try:
			g = ev.getGenreData()
			if g is None:
				return ""
			from Components.Converter import HdsCommon
			f = getattr(HdsCommon, "genre_text", None)
			return f(g) if f else ""
		except Exception:
			return ""

	def _varsta(self, ev):
		try:
			d = ev.getParentalData()
			v = d.getRating() if d is not None else 0
			return "%d+" % (v + 3) if 0 < v <= 15 else ""
		except Exception:
			return ""

	def _camp(self, nume, ev):
		if ev is None:
			return ""
		if nume == "NAME":
			return ev.getEventName() or ""
		if nume == "TIMERANGE":
			return _interval(ev.getBeginTime(), ev.getDuration())
		if nume == "DURATION":
			return "%d min" % (ev.getDuration() // 60)
		if nume == "GENRE":
			return self._gen(ev)
		if nume == "RATING":
			return self._varsta(ev)
		return ""

	@cached
	def getText(self):
		ev = self.source.event
		if self.hdsDupa:
			l = emisiuni(self.source)
			i, camp = self.hdsDupa
			return (l[i][camp] or "") if len(l) > i else ""
		if self.hdsCampuri:
			sep, campuri = self.hdsCampuri
			return sep.join(x for x in (self._camp(c, ev) for c in campuri) if x)
		if ev is None:
			return ""
		if self.hdsGen:
			return self._gen(ev)
		if self.hdsVarsta:
			return self._varsta(ev)
		if self.hdsScurt:
			return ev.getShortDescription() or ""
		return _EventName.getText(self)

	text = property(getText)

	# EventName inaintea lui ConditionalShowHide: adevarat cand emisiunea are textul cerut; la Pdc, cand are cod PDC
	@cached
	def getBoolean(self):
		if self.hdsPdc:
			ev = self.source.event
			f = getattr(ev, "getPdcPil", None) if ev is not None else None
			try:
				return bool(f and f())
			except Exception:
				return False
		return bool(self.getText())

	boolean = property(getBoolean)


class EventInfo(EventName):
	"""Numele cerut de unele teme pentru aceleasi date; Times da intervalul emisiunii."""

	def __init__(self, type):
		a = (type or "").split(",")[0].strip()
		EventName.__init__(self, {"Times": ",TIMERANGE", "Name": "Name", "ServiceName": "Name"}.get(a, a))


_ALTE_ORE = {"NextStartTime": (1, "s"), "NextEndTime": (1, "e"), "ThirdStartTime": (2, "s"), "ThirdEndTime": (2, "e"), "Times": (0, "t"), "NextTimes": (1, "t")}


class EventTime(_EventTime):
	def __init__(self, type):
		self.hdsOre = _ALTE_ORE.get(type)
		self.hdsTrecut = type == "Elapsed"
		if self.hdsOre or self.hdsTrecut:
			Converter.__init__(self, type)
			Poll.__init__(self)
			self.type = self.STARTTIME
			self.poll_interval = 60 * 1000
			self.poll_enabled = True
		else:
			_EventTime.__init__(self, type)

	@cached
	def getTime(self):
		if self.hdsTrecut:
			ev = self.source.event
			return max(0, int(time.time()) - ev.getBeginTime()) if ev is not None else None
		if self.hdsOre:
			i, fel = self.hdsOre
			if i == 0:
				ev = self.source.event
				if ev is None:
					return None
				b, d = ev.getBeginTime(), ev.getDuration()
			else:
				l = emisiuni(self.source)
				if len(l) <= i or not l[i][0]:
					return None
				b, d = l[i][0], l[i][1]
			return b if fel == "s" else b + d if fel == "e" else (b, b + d)
		return _EventTime.getTime(self)

	time = property(getTime)


class ClockToText(_ClockToText):
	"""Si intervalul (doua ore, de la EventTime Times) si formele Full, ShortDate, AsLengthHours."""

	def __init__(self, type):
		baza = (type or "").split(";")[0].split(",")[0].strip()
		self.hdsFel = baza if baza in ("Full", "ShortDate", "LongFullDate", "AsLengthHours") else None
		_ClockToText.__init__(self, baza if baza.find("Format") == -1 else type)

	@cached
	def getText(self):
		t = getattr(self.source, "time", None)
		if t is None:
			# legat direct de o emisiune: ora ei de inceput
			ev = getattr(self.source, "event", None)
			t = ev.getBeginTime() if ev is not None else None
		if t is None:
			return ""
		if not hasattr(self.source, "time"):
			return _ora(t)
		if isinstance(t, tuple):
			return "%s - %s" % (_ora(t[0]), _ora(t[1]))
		if self.hdsFel == "AsLengthHours":
			return "%d:%02d" % (t // 3600, t // 60 % 60)
		if self.hdsFel == "Full":
			return time.strftime("%a %d %b %H:%M", time.localtime(t))
		if self.hdsFel == "ShortDate":
			return time.strftime("%d.%m", time.localtime(t))
		if self.hdsFel == "LongFullDate":
			return time.strftime("%A %d %B %Y", time.localtime(t))
		return _ClockToText.getText(self)

	text = property(getText)


# ------------------------------------------------------------------ canalul

def numarCanal(source):
	try:
		from Components.Converter.HdsInfo import numar_canal
		sref = referintaCanal(source)
		n = numar_canal(source, sref) if sref else 0
		return str(n) if n > 0 else ""
	except Exception:
		return ""


def transponder(source):
	"""Datele transponderului sursei (dictionarul sTransponderData), sau {}."""
	try:
		from enigma import eServiceCenter, eServiceReference
		serviciu = getattr(source, "service", None)
		if serviciu is None:
			return {}
		if isinstance(serviciu, eServiceReference):
			if serviciu.flags & (eServiceReference.isDirectory | eServiceReference.isMarker):
				return {}
			info = eServiceCenter.getInstance().info(serviciu)
			tp = info and info.getInfoObject(serviciu, iServiceInformation.sTransponderData)
		else:
			info = serviciu.info()
			tp = info and info.getInfoObject(iServiceInformation.sTransponderData)
			if not tp:
				fe = serviciu.frontendInfo()
				tp = fe and fe.getAll(True)
		return tp if isinstance(tp, dict) else {}
	except Exception:
		return {}


def _pozitie(tp):
	if C is None or not tp:
		return ""
	try:
		fel = C.tp_kind(tp)
		if fel == "s":
			return C.orbital(C.ival(tp, "orbital_position"))
		if fel == "c":
			return C.tr("rec_cable")
		if fel == "t":
			return C.tr("rec_terr")
		if fel == "a":
			return u"ATSC"
	except Exception:
		pass
	return ""


def _randTransponder(tp):
	if C is None or not tp:
		return ""
	try:
		return C.tp_line(tp, C.tp_kind(tp), short=True)
	except Exception:
		return ""


class ServiceName(_ServiceName):
	"""NameOnly, All, Channel, StreamUrl si listele de campuri ("x,NUMBER,NAME,ORBPOS,PROVIDER", cu despartitorul inainte)."""

	def __init__(self, type):
		self.hdsCampuri = None
		parti = (type or "").split(",")
		if len(parti) > 1 and all(p.strip().isupper() for p in parti[1:]):
			self.hdsCampuri = (parti[0], [p.strip() for p in parti[1:]])
			type = "Name"
		self.hdsFlux = type == "StreamUrl"
		_ServiceName.__init__(self, type)

	def _camp(self, nume):
		tp = None
		if nume == "NAME":
			return _ServiceName.getText(self)
		if nume == "NUMBER":
			return numarCanal(self.source)
		if nume == "ORBPOS":
			tp = transponder(self.source)
			return _pozitie(tp)
		if nume == "TUNERSYSTEM":
			tp = transponder(self.source)
			return (C.sat_system(tp) if C is not None and tp and C.tp_kind(tp) == "s" else "") or ""
		if nume == "PROVIDER":
			self.type = self.PROVIDER
			try:
				return _ServiceName.getText(self)
			finally:
				self.type = self.NAME
		return ""

	@cached
	def getText(self):
		if self.hdsCampuri:
			sep, campuri = self.hdsCampuri
			return sep.join(x for x in (self._camp(c) for c in campuri) if x and x != "N/A")
		if self.hdsFlux:
			r = referintaCanal(self.source) or ""
			return r.split(":", 10)[10] if r.count(":") >= 10 and r.split(":")[0] in ("4097", "5001", "5002", "8193") else ""
		return _ServiceName.getText(self)

	text = property(getText)


class ServiceName2(_ServiceName):
	"""Numele canalului si datele transponderului, ca text: Name, Provider, Reference, Number, OrbitalPos, TransponderInfo sau un sablon
	cu %N nume, %n numar, %P furnizor, %R referinta, %S pozitia, %F frecventa, %p polarizarea, %Y simbolurile, %f FEC, %M modulatia, %s sistemul."""

	def __init__(self, type):
		self.hdsArgument = (type or "").strip()
		_ServiceName.__init__(self, self.hdsArgument if self.hdsArgument in ("Provider", "Reference") else "Name")

	def _literal(self, l, tp):
		if l == "N":
			return _ServiceName.getText(self)
		if l == "n":
			return numarCanal(self.source)
		if l == "R":
			return referintaCanal(self.source) or ""
		if l == "S":
			return _pozitie(tp)
		if C is None or not tp:
			return ""
		fel = C.tp_kind(tp)
		try:
			if l == "F":
				return C.freq_short(tp, fel)
			if l == "Y":
				return C.symbol_rate(tp) or ""
			if l == "f":
				return C.fec_text(tp, fel) or ""
			if l == "s":
				return C.sat_system(tp) if fel == "s" else ""
			if l == "M":
				return C.SAT_MOD.get(C.ival(tp, "modulation"), u"") if fel == "s" else C.CAB_MOD.get(C.ival(tp, "modulation"), u"") if fel == "c" else ""
			if l == "p":
				return {0: "H", 1: "V", 2: "L", 3: "R"}.get(C.ival(tp, "polarization"), "") if fel == "s" else ""
		except Exception:
			pass
		return ""

	@cached
	def getText(self):
		a = self.hdsArgument
		if a in ("Provider", "Reference"):
			return _ServiceName.getText(self)
		if a == "Number":
			return numarCanal(self.source)
		tp = transponder(self.source) if a not in ("", "Name") else None
		if a in ("OrbitalPos", "Satellite"):
			return _pozitie(tp)
		if a in ("TpansponderInfo", "TransponderInfo"):
			return _randTransponder(tp)
		if "%" not in a:
			return _ServiceName.getText(self)
		rez = []
		i = 0
		while i < len(a):
			if a[i] == "%" and i + 1 < len(a):
				rez.append(self._literal(a[i + 1], tp))
				i += 2
			else:
				rez.append(a[i])
				i += 1
		return " ".join("".join(rez).split())

	text = property(getText)

	def changed(self, what):
		Converter.changed(self, what)


class ExtendedServiceInfo(_ServiceName):
	def __init__(self, type):
		self.hdsNumar = (type or "").strip() == "ServiceNumber"
		_ServiceName.__init__(self, "Name")

	@cached
	def getText(self):
		return numarCanal(self.source) if self.hdsNumar else _ServiceName.getText(self)

	text = property(getText)


class MovieReference(Converter, object):
	"""Referinta canalului de pe care s-a inregistrat filmul ales (pentru sigla din lista filmelor)."""

	def __init__(self, arg):
		Converter.__init__(self, arg)

	@cached
	def getText(self):
		try:
			serviciu = self.source.service
			info = self.source.info
			if serviciu is None or info is None:
				return ""
			return info.getInfoString(serviciu, iServiceInformation.sServiceref) or ""
		except Exception:
			return ""

	text = property(getText)


class TransponderInfo(Converter, object):
	"""Randul transponderului ("19,2°E 11494 H SR 22000 DVB-S2 8PSK"), al canalului redat sau ales; nimic la un dosar sau buchet."""

	def __init__(self, arg):
		Converter.__init__(self, arg)

	@cached
	def getText(self):
		return _randTransponder(transponder(self.source))

	text = property(getText)

	@cached
	def getBoolean(self):
		return bool(self.getText())

	boolean = property(getBoolean)

	def changed(self, what):
		if what[0] != self.CHANGED_SPECIFIC or what[1] in _EV_TOATE:
			Converter.changed(self, what)


class ServiceOrbitalPosition(Converter, object):
	"""Locul de unde vine canalul: pozitia satelitului, la cablu si terestru felul, in limba receptorului; la un flux, nimic."""

	def __init__(self, arg):
		Converter.__init__(self, arg)

	@cached
	def getText(self):
		return _pozitie(transponder(self.source))

	text = property(getText)

	def changed(self, what):
		if what[0] != self.CHANGED_SPECIFIC or what[1] in _EV_TOATE:
			Converter.changed(self, what)


class RotorPosition(Poll, Converter, object):
	"""Pozitia la care a ajuns ultima data motorul antenei; nimic fara motor."""

	def __init__(self, arg):
		Converter.__init__(self, arg)
		Poll.__init__(self)
		self.poll_interval = 1000
		self.poll_enabled = True

	@cached
	def getText(self):
		if C is None:
			return ""
		try:
			pos, _misca = C.rotor_position()
			return "" if pos is None or pos < 0 or pos > 3600 else C.orbital(pos)
		except Exception:
			return ""

	text = property(getText)

	@cached
	def getBoolean(self):
		return bool(self.getText())

	boolean = property(getBoolean)


def _clienti():
	import sys
	modul = sys.modules.get("Components.HdsTransmisie")
	manageri = getattr(modul, "_MANAGER", None) if modul is not None else None
	if not manageri:
		return []
	rez = []
	try:
		for s in manageri[0].vii():
			nume = getattr(s, "browser", "") or getattr(s, "adresa", "") or ""
			if nume and nume not in rez:
				rez.append(nume)
	except Exception:
		return []
	return rez


class ClientsStreaming(Poll, Converter, object):
	"""Cine primeste acum un canal prin receptor (transmisia in retea a imaginii); fara transmisie, nimic."""

	def __init__(self, arg):
		Converter.__init__(self, arg)
		Poll.__init__(self)
		self.poll_interval = 5000
		self.poll_enabled = True

	@cached
	def getText(self):
		return ", ".join(_clienti())

	text = property(getText)

	@cached
	def getBoolean(self):
		return bool(_clienti())

	boolean = property(getBoolean)


class CryptoInfo(Poll, Converter, object):
	"""Cum se decodeaza canalul redat: sistemul, CAID-ul, timpul, din ce stie imaginea dupa ultima decodare; nimic pe un canal necriptat."""

	def __init__(self, arg):
		Converter.__init__(self, arg)
		Poll.__init__(self)
		self.poll_interval = 2000
		self.poll_enabled = True

	def _criptat(self):
		try:
			service = self.source.service
			info = service and service.info()
			return bool(info and info.getInfo(iServiceInformation.sIsCrypted) == 1)
		except Exception:
			return False

	@cached
	def getText(self):
		if C is None or not self._criptat():
			return ""
		try:
			d = C.ecm_info()
			caid = d.get("caid", -1)
			if caid <= 0 or not 0.0 <= time.time() - d.get("mtime", 0.0) <= C.ECM_FRESH_S:
				return ""
			parti = [u"%s: %s" % (C.tr("ecm_system"), C.ecm_system_name(caid, d)), u"CAID %04X" % caid]
			if d.get("ms", -1) >= 0:
				parti.append(u"%d ms" % d["ms"])
			return C.join(parti)
		except Exception:
			return ""

	text = property(getText)

	@cached
	def getBoolean(self):
		return self._criptat()

	boolean = property(getBoolean)


class HddState(Poll, Converter, object):
	"""boolean: un disc din receptor se invarte acum; text gol (temele il folosesc ca semn)."""

	def __init__(self, arg):
		Converter.__init__(self, arg)
		Poll.__init__(self)
		self.poll_interval = 10000
		self.poll_enabled = True

	@cached
	def getBoolean(self):
		try:
			from Components.Harddisk import harddiskmanager
			return any(not disc.isSleeping() for _n, disc in harddiskmanager.HDDList())
		except Exception:
			return False

	boolean = property(getBoolean)

	@cached
	def getText(self):
		return ""

	text = property(getText)


class VAudioInfo(Converter, object):
	"""Sunetul canalului redat: descrierea pistei ascultate."""

	def __init__(self, arg):
		Converter.__init__(self, arg)

	@cached
	def getText(self):
		service = getattr(self.source, "service", None)
		return _descriereSunet(service) if service else ""

	text = property(getText)

	@cached
	def getBoolean(self):
		return bool(self.getText())

	boolean = property(getBoolean)


class VServiceInfo(ServiceInfo):
	pass


class StreamInfo(Converter, object):
	"""Felul serviciului: Stream pentru un flux, altfel gol; boolean: e flux."""

	def __init__(self, arg):
		Converter.__init__(self, arg)

	def _flux(self):
		try:
			service = self.source.service
			info = service and service.info()
			return bool(info and _esteFlux(info))
		except Exception:
			return False

	@cached
	def getText(self):
		return "Stream" if self._flux() else ""

	text = property(getText)

	@cached
	def getBoolean(self):
		return self._flux()

	boolean = property(getBoolean)


class RdsInfo(_RdsInfo):
	"""Textul radio si piesa numai cand emisiunea nu are nume (RadioTextIfNoEvent, RtpTextIfNoEvent)."""

	def __init__(self, type):
		self.hdsFaraEmisiune = type in ("RadioTextIfNoEvent", "RtpTextIfNoEvent")
		_RdsInfo.__init__(self, {"RadioTextIfNoEvent": "RadioText", "RtpTextIfNoEvent": "RtpText"}.get(type, type))

	@cached
	def getText(self):
		if self.hdsFaraEmisiune:
			try:
				service = self.source.navcore.getCurrentService()
				info = service and service.info()
				if info and info.getEvent(0):
					return ""
			except Exception:
				pass
		return _RdsInfo.getText(self)

	text = property(getText)


class MovieInfo(_MovieInfo):
	"""RecordServiceRef, Reference, Name, FullDescription si listele de campuri nu le are convertorul imaginii."""

	def __init__(self, type):
		a = (type or "").split(",")[0].strip()
		self.hdsFel = a if a in ("RecordServiceRef", "Reference", "Name", "FullDescription") else None
		self.hdsCampuri = ("," in (type or "") and not self.hdsFel) and type or None
		if self.hdsFel or self.hdsCampuri:
			Converter.__init__(self, type)
			self.type = self.MOVIE_REC_SERVICE_NAME
		else:
			_MovieInfo.__init__(self, type)

	@cached
	def getText(self):
		if not (self.hdsFel or self.hdsCampuri):
			return _MovieInfo.getText(self)
		service = self.source.service
		info = self.source.info
		if not (info and service):
			return ""
		try:
			if self.hdsFel in ("RecordServiceRef", "Reference"):
				return info.getInfoString(service, iServiceInformation.sServiceref) or ""
			if self.hdsFel == "Name":
				return info.getName(service) or ""
			if self.hdsFel == "FullDescription":
				ev = self.source.event
				return (ev.getExtendedDescription() or ev.getShortDescription() or "") if ev else ""
		except Exception:
			return ""
		# "x,RECSERVICE,...": numai numele canalului de pe care s-a inregistrat, pe care il stim sigur
		return _MovieInfo.getText(self)

	text = property(getText)


class TunerInfo(_TunerInfo):
	"""TunerAvailable: cati tuneri are receptorul."""

	def __init__(self, type):
		self.hdsTuneri = type == "TunerAvailable"
		_TunerInfo.__init__(self, "TunerUseMask" if self.hdsTuneri else type)

	def _numar(self):
		try:
			from Components.NimManager import nimmanager
			return len(nimmanager.nim_slots)
		except Exception:
			return 0

	@cached
	def getBoolean(self):
		return self._numar() > 0 if self.hdsTuneri else _TunerInfo.getBoolean(self)

	boolean = property(getBoolean)

	@cached
	def getText(self):
		return str(self._numar()) if self.hdsTuneri else _TunerInfo.getText(self)

	text = property(getText)


class VNetSpeedInfo(Poll, Converter, object):
	"""Viteza retelei, din /proc/net/dev: RC primita, TM trimisa, pe interfata cu cel mai mult trafic."""

	def __init__(self, arg):
		Converter.__init__(self, arg)
		Poll.__init__(self)
		self.poll_interval = 2000
		self.poll_enabled = True
		self.fel = 0 if "RC" in (arg or "") else 8
		self.ultim = None

	def _octeti(self):
		maxim = 0
		try:
			with open("/proc/net/dev") as f:
				for r in f.readlines()[2:]:
					nume, _s, date = r.partition(":")
					if nume.strip() != "lo":
						maxim = max(maxim, int(date.split()[self.fel]))
		except (IOError, OSError, ValueError, IndexError):
			return None
		return maxim

	@cached
	def getText(self):
		acum, n = time.time(), self._octeti()
		vechi, self.ultim = self.ultim, (acum, n)
		if n is None or vechi is None or acum <= vechi[0] or vechi[1] is None or n < vechi[1]:
			return ""
		b = (n - vechi[1]) / (acum - vechi[0])
		return "%.1f MB/s" % (b / 1048576.0) if b >= 1048576 else "%d KB/s" % (b / 1024)

	text = property(getText)


class CpuUsage(Poll, Converter, object):
	"""Procesorul folosit, din /proc/stat; in text, $0 ia locul procentului."""

	def __init__(self, arg):
		Converter.__init__(self, arg)
		Poll.__init__(self)
		self.poll_interval = 2000
		self.poll_enabled = True
		self.sablon = arg if "$0" in (arg or "") else "$0 %"
		self.ultim = None

	def _procent(self):
		try:
			with open("/proc/stat") as f:
				p = [int(x) for x in f.readline().split()[1:8]]
		except (IOError, OSError, ValueError):
			return None
		total, liber = sum(p), p[3]
		vechi, self.ultim = self.ultim, (total, liber)
		if vechi is None or total <= vechi[0]:
			return None
		return 100 * (total - vechi[0] - (liber - vechi[1])) // (total - vechi[0])

	@cached
	def getText(self):
		v = self._procent()
		return self.sablon.replace("$0", str(v)) if v is not None else ""

	text = property(getText)


class LayoutInfo(Poll, Converter, object):
	"""Memoria, din /proc/meminfo: MemTotal, MemFree, SwapTotal, SwapFree."""

	def __init__(self, arg):
		Converter.__init__(self, arg)
		Poll.__init__(self)
		self.poll_interval = 5000
		self.poll_enabled = True
		self.camp = (arg or "").split(",")[0].strip()

	@cached
	def getText(self):
		try:
			with open("/proc/meminfo") as f:
				for r in f:
					if r.startswith(self.camp + ":"):
						return "%d MB" % (int(r.split()[1]) // 1024)
		except (IOError, OSError, ValueError, IndexError):
			pass
		return ""

	text = property(getText)


class PliExtraInfo(Poll, Converter, object):
	"""Numele il cer in XML temele instalate de om, pe bara de informatii. Datele tehnice ale canalului redat, din convertorul imaginii
	(aceleasi texte ca in barele imaginii, in limba receptorului). Un argument pe care nu il stim nu arata nimic. codec_data: numele
	codecurilor dupa sVideoType, pentru fisierele aduse de teme care il citesc."""

	codec_data = {-1: "N/A", 0: "MPEG2", 1: "AVC", 2: "H263", 3: "VC1", 4: "MPEG4-VC", 5: "VC1-SM", 6: "MPEG1", 7: "HEVC", 8: "VP8", 9: "VP9", 10: "XVID", 11: "N/A 11",
		12: "N/A 12", 13: "DIVX 3.11", 14: "DIVX 4", 15: "DIVX 5", 16: "AVS", 17: "N/A 17", 18: "VP6", 19: "N/A 19", 20: "N/A 20", 21: "SPARK"}

	TIPURI = {
		"VideoCodec": "VideoCodec", "Frequency": "Frequency", "Polarization": "Polarization", "SymbolRate": "SymbolRate", "Fec": "Fec",
		"Modulation": "Modulation", "OrbitalPosition": "OrbitalPosition", "TunerSystem": "System", "TunerType": "ReceptionType",
		"ProviderName": "Provider", "PIDInfo": "Pids", "TransponderInfo": "TechLeft", "CryptoNameCaid": "CryptoBar", "CryptoInfo": "CryptoBar",
		"CryptoSpecial": "CryptoBar", "ResolutionString": "ResolutionString", "All": "All", "ServiceInfo": "ServiceInfo", "CryptoBar": "CryptoBar",
	}

	def __new__(cls, arg):
		from Components.Converter.HdsInfoTehnice import HdsInfoTehnice
		nume = str(arg or "").split(",")[0].strip()
		return HdsInfoTehnice(cls.TIPURI.get(nume, arg))


class ConditionalShowHide(_ConditionalShowHide):
	# Intre un convertor cu text sau valoare si un Label / Progress: textul, valoarea si intervalul vin de la convertorul
	# de dinainte. Numai dupa ce un element de dupa le-a cerut (hdsTrece) primeste si schimbarile, ca sa le citeasca iar.
	hdsTrece = False

	def changed(self, what):
		_ConditionalShowHide.changed(self, what)
		if self.hdsTrece:
			Converter.changed(self, what)

	@property
	def text(self):
		self.hdsTrece = True
		return getattr(self.source, "text", "")

	@property
	def value(self):
		self.hdsTrece = True
		return getattr(self.source, "value", 0)

	@property
	def range(self):
		self.hdsTrece = True
		return getattr(self.source, "range", 0)

	@property
	def boolean(self):
		return self.calcVisibility()


class FrontendInfo(_FrontendInfo):
	"""boolean si pentru semnal (SNR, AGC: adevarat cand se stie valoarea), text gol la lock si tipul STRING (tunerul folosit)."""

	def __init__(self, type):
		nume = (type or "").split(",")[0].strip()
		self.hdsTuner = nume in ("STRING", "USE_TUNERS_STRING")
		_FrontendInfo.__init__(self, "NUMBER" if self.hdsTuner else {"SNRStream": "SNR", "Lock": "LOCK"}.get(nume, type))

	@cached
	def getText(self):
		if self.hdsTuner:
			n = self.source.slot_number
			return "" if n is None or n < 0 else "Tuner %s" % chr(65 + n)
		if self.type in (self.LOCK, self.SLOT_NUMBER):
			return ""
		return _FrontendInfo.getText(self)

	text = property(getText)

	@cached
	def getBool(self):
		if self.type in (self.LOCK, self.BER):
			return _FrontendInfo.getBool(self)
		if self.type == self.AGC:
			return self.source.agc is not None
		if self.type in (self.SNR, self.SNRdB):
			return self.source.snr is not None
		return self.source.slot_number is not None

	boolean = property(getBool)


class _FactorSkin(float):
	"""f din sabloanele temelor: inmultit sau impartit cu un numar da un numar intreg (trunchiat)"""
	def __mul__(self, alt):
		return int(float(self) * alt) if isinstance(alt, (int, float)) else NotImplemented
	__rmul__ = __mul__

	def __rtruediv__(self, alt):
		return int(alt / float(self)) if isinstance(alt, (int, float)) else NotImplemented


_NUME_BT = ("BT_SCALE", "BT_KEEP_ASPECT_RATIO", "BT_HALIGN_LEFT", "BT_HALIGN_CENTER", "BT_HALIGN_RIGHT", "BT_VALIGN_TOP",
	"BT_VALIGN_CENTER", "BT_VALIGN_BOTTOM", "BT_ALIGN_CENTER", "RT_ELLIPSIS", "RT_BLEND")


class TemplatedMultiContent(_TemplatedMultiContent):
	"""Sablonul cu numele lui TemplatedMultiContent al imaginii, plus f (factorul temei: "pos=(15*f, 13*f)", "itemHeight": 55*f;
	f*N da un numar intreg, ca pozitiile listei), BT_*, RT_ELLIPSIS si RT_BLEND. Inaltimea si sablonul implicit se pot da numai
	in "templates": {"default": (inaltime, [...])}."""

	def __init__(self, args):
		StringList.__init__(self, args)
		import enigma
		from enigma import eListboxPythonMultiContent, gFont, RT_HALIGN_LEFT, RT_HALIGN_CENTER, RT_HALIGN_RIGHT, \
			RT_VALIGN_TOP, RT_VALIGN_CENTER, RT_VALIGN_BOTTOM, RT_WRAP
		from Components.MultiContent import MultiContentEntryText, MultiContentEntryPixmap, \
			MultiContentEntryPixmapAlphaTest, MultiContentEntryPixmapAlphaBlend, MultiContentTemplateColor, \
			MultiContentEntryProgress
		l = dict(locals())
		for nume in ("self", "args", "enigma"):
			del l[nume]
		for nume in _NUME_BT:
			l.setdefault(nume, getattr(enigma, nume, 0))
		try:
			from skin import _Tema
			l.setdefault("f", _FactorSkin(_Tema().factorSkin()))
		except Exception:
			l.setdefault("f", _FactorSkin(1.0))

		self.active_style = None
		self.template = sablonCurat(eval(args, {}, l))


def sablonCurat(sablon):
	"""Dictionarul sablonului, cu "template" si "itemHeight" puse din "templates" cand lipsesc. ValueError, cu ce lipseste, cand
	nu se poate face o lista din el."""
	if not isinstance(sablon, dict):
		raise ValueError("sablonul nu e un dictionar")
	if "fonts" not in sablon:
		raise ValueError("sablonul nu are fonts")
	sabloane = sablon.get("templates")
	if "template" not in sablon:
		if not sabloane or "default" not in sabloane:
			raise ValueError("sablonul nu are template si nici templates default")
		implicit = sabloane["default"]
		if not isinstance(implicit, (tuple, list)) or len(implicit) < 2:
			raise ValueError("templates default nu e (inaltime, [...])")
		sablon["template"] = implicit[1]
		sablon.setdefault("itemHeight", implicit[0])
	if "itemHeight" not in sablon:
		if sabloane and "default" in sabloane:
			sablon["itemHeight"] = sabloane["default"][0]
		else:
			raise ValueError("sablonul nu are itemHeight")
	return sablon
