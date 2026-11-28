# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Native YouTube for the receiver (0.8.0, YTN1): lists, search, channels, playlists and playback addresses from
YouTube's internal API (InnerTube, youtubei/v1), without a Google account and without an API key.

Written from scratch; the idea (native lists from InnerTube instead of the youtube.com/tv page) comes from SmartTube.
Measured before writing it:
- data (browse, search, next) answers anonymously; the ANDROID_VR client gives small, uniform answers
  (compactVideoRenderer, compactChannelRenderer, compactPlaylistRenderer, playlistVideoRenderer);
- playback: ANDROID (21.08.266, params 2AMB) and VISIONOS (with a visitorData) give direct stream URLs that need no
  signature/n deciphering and no poToken, valid for the whole film (ANDROID_VR and IOS stop after ~60 s); live: ANDROID
  gives an HLS master with muxed variants (picture and sound in one TS), which the image's hlsdemux plays.
- films go to the image's player as a small static MPD in /tmp (two DASH streams, H.264 + AAC, SegmentBase), the
  format already proven on the receivers for the feed plugin (YTB); live goes as the HLS variant URL.

The client table is data: a feed package can replace it (FISIER_CLIENTI) when YouTube closes a client, without a new
image. No enigma2 imports here: the PC tests use the module directly (the http function is injectable).
"""
import json
import os
import re
import threading
import time

try:
	from urllib.request import Request, urlopen
	from urllib.error import HTTPError, URLError
except ImportError:  # pragma: no cover
	from urllib2 import Request, urlopen, HTTPError, URLError

API = "https://www.youtube.com/youtubei/v1/%s?prettyPrint=false"
FISIER_CLIENTI = "/usr/share/enigma2/hds-youtube/clienti.json"      # optional override, from a feed package
FISIER_STARE = "/etc/enigma2/hds-youtube.json"                       # visitorData, search history, watched list
DOSAR_TMP = "/tmp/hds-youtube"                                       # MPD files and thumbnails
MPD = "hds-youtube-%s.mpd"
TERMEN_S = 15
VISITOR_MAX_S = 3 * 24 * 3600
MAX_ISTORIC = 20
MAX_VAZUTE = 60
MAX_POZE = 120                  # files in /tmp (RAM): ~15 KB each

# search filters (the "sp" parameter of the search page): live now, channels, playlists
FILTRE = {"film": "", "live": "EgJAAQ%3D%3D", "canal": "EgIQAg%3D%3D", "lista": "EgIQAw%3D%3D"}
FILA_VIDEOS = "EgZ2aWRlb3PyBgQKAjoA"

CLIENTI_IMPLICITI = {
	# data calls (browse/search/next): small answers, anonymous
	"date": {"clientName": "ANDROID_VR", "clientVersion": "1.65.10", "id": 28,
		"extra": {"deviceMake": "Oculus", "deviceModel": "Quest 3", "androidSdkVersion": 32, "osName": "Android",
			"osVersion": "12L"},
		"ua": "com.google.android.apps.youtube.vr.oculus/1.65.10 (Linux; U; Android 12L; eureka-user Build/SQ3A.220605.009.A1) gzip"},
	# player calls, tried in order; "vizitator": the call needs a visitorData (else LOGIN_REQUIRED)
	"redare": [
		{"clientName": "ANDROID", "clientVersion": "21.08.266", "id": 3, "params": "2AMB", "live": True,
			"extra": {"androidSdkVersion": 30, "osName": "Android", "osVersion": "11"},
			"ua": "com.google.android.youtube/21.08.266 (Linux; U; Android 11) gzip"},
		{"clientName": "VISIONOS", "clientVersion": "1.02", "id": 101, "vizitator": True, "live": False,
			"extra": {"deviceMake": "Apple", "deviceModel": "RealityDevice17,1", "osName": "visionOS",
				"osVersion": "26.5.23O471"},
			"ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 15_7_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0 Safari/605.1.15"},
	],
	# the topic pages (Music, Gaming, News, Sports, Live) answer anonymously only to the TV client, as shelves of
	# tiles (the way SmartTube builds them); the music page starts with the country's top 20 music videos (gl)
	"tv": {"clientName": "TVHTML5", "clientVersion": "7.20261120.10.00", "id": 7,
		"ua": "Mozilla/5.0 (ChromiumStylePlatform) Cobalt/25.lts.30.1034943-gold (unlike Gecko), Unknown_TV_Unknown_0/Unknown (Unknown, Unknown)"},
}

# the topic pages: (key, browseId). Measured without an account (0.8.0): these answer on TVHTML5; the old FEtrending and
# FEexplore pages and the short FE<topic> ids answer HTTP 400 on every client
RUBRICI = (("muzica", "FEtopics_music"), ("jocuri", "FEtopics_gaming"), ("stiri", "FEtopics_news"),
	("sport", "FEtopics_sports"), ("podcast", "FEtopics_podcasts"), ("live", "FEtopics_live"))

# the music charts of any country: YouTube Music's charts page (anonymous; the country in formData)
API_MUZICA = "https://music.youtube.com/youtubei/v1/%s?prettyPrint=false"
CLIENT_MUZICA = {"clientName": "WEB_REMIX", "clientVersion": "1.20261118.01.00", "id": 67,
	"ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"}


class EroareYouTube(Exception):
	"""text: a short reason for the person (already in the receiver's language when YouTube gave one)"""


# ---------------------------------------------------------------------------------------------------------------------
# small helpers

def text(o):
	"""InnerTube text: {"simpleText": ...} or {"runs": [{"text": ...}]}"""
	if not isinstance(o, dict):
		return o if isinstance(o, str) else ""
	if "simpleText" in o:
		return o.get("simpleText") or ""
	return "".join(r.get("text", "") for r in o.get("runs", []) if isinstance(r, dict))


def _poza(thumbs):
	"""the 320x180 thumbnail (mqdefault) when present: the largest up to 400 px wide"""
	lista = (thumbs or {}).get("thumbnails") or []
	alese = [t for t in lista if isinstance(t, dict) and t.get("url")]
	if not alese:
		return ""
	bune = [t for t in alese if int(t.get("width") or 0) <= 400] or alese
	t = max(bune, key=lambda x: int(x.get("width") or 0))
	u = t["url"]
	return "https:" + u if u.startswith("//") else u


def _live(r):
	for b in r.get("badges") or []:
		s = (b.get("metadataBadgeRenderer") or {}).get("style", "")
		if s == "BADGE_STYLE_TYPE_LIVE_NOW":
			return True
	for o in r.get("thumbnailOverlays") or []:
		if (o.get("thumbnailOverlayTimeStatusRenderer") or {}).get("style") == "LIVE":
			return True
	# the anonymous ANDROID_VR answer has no live badge: a film without a length that is not a premiere is live
	return "lengthText" not in r and "upcomingEventData" not in r and "lengthSeconds" not in r and "viewCountText" in r


def _autor(r):
	for k in ("longBylineText", "shortBylineText", "ownerText"):
		if k in r:
			runs = r[k].get("runs") or []
			cid = ""
			for x in runs:
				cid = ((x.get("navigationEndpoint") or {}).get("browseEndpoint") or {}).get("browseId", "") or cid
			return text(r[k]), cid
	return "", ""


def _film(r):
	vid = r.get("videoId")
	if not vid:
		return None
	autor, cid = _autor(r)
	live = _live(r)
	vizionari = text(r.get("shortViewCountText") or {}) or text(r.get("viewCountText") or {})
	return {"fel": "film", "id": vid, "titlu": text(r.get("title") or {}) or text(r.get("headline") or {}),
		"autor": autor, "autor_id": cid, "durata": "" if live else text(r.get("lengthText") or {}),
		"vizionari": vizionari, "data": text(r.get("publishedTimeText") or {}), "live": live,
		"poza": _poza(r.get("thumbnail"))}


def _canal(r):
	cid = r.get("channelId")
	if not cid:
		return None
	# the anonymous answer swaps the two counters on some layouts: keep whichever says "subscribers"
	info = [text(r.get(k) or {}) for k in ("videoCountText", "subscriberCountText")]
	return {"fel": "canal", "id": cid, "titlu": text(r.get("displayName") or {}) or text(r.get("title") or {}),
		"autor": "", "autor_id": cid, "durata": "", "vizionari": " ".join(x for x in info if x and not x.startswith("@")),
		"data": "", "live": False, "poza": _poza(r.get("thumbnail"))}


def _lista(r):
	pid = r.get("playlistId")
	if not pid:
		return None
	autor, cid = _autor(r)
	return {"fel": "lista", "id": pid, "titlu": text(r.get("title") or {}), "autor": autor, "autor_id": cid,
		"durata": text(r.get("videoCountShortText") or {}) or text(r.get("videoCountText") or {}), "vizionari": "",
		"data": "", "live": False, "poza": _poza(r.get("thumbnail"))}


RENDERERE = {
	"compactVideoRenderer": _film, "videoRenderer": _film, "gridVideoRenderer": _film,
	"playlistVideoRenderer": _film, "playlistPanelVideoRenderer": _film, "videoWithContextRenderer": _film,
	"compactChannelRenderer": _canal, "channelRenderer": _canal, "gridChannelRenderer": _canal,
	"compactPlaylistRenderer": _lista, "playlistRenderer": _lista, "gridPlaylistRenderer": _lista,
}


def elemente(raspuns):
	"""(items, continuation token) from any browse/search/next answer, in page order, without duplicates"""
	gasite, vazute, cont = [], set(), [None]

	def umbla(o):
		if isinstance(o, dict):
			for k, v in o.items():
				f = RENDERERE.get(k)
				if f is not None and isinstance(v, dict):
					e = f(v)
					if e and (e["fel"], e["id"]) not in vazute and e["titlu"]:
						vazute.add((e["fel"], e["id"]))
						gasite.append(e)
					continue
				if k == "nextContinuationData" and isinstance(v, dict) and v.get("continuation"):
					cont[0] = v["continuation"]
				elif k == "continuationCommand" and isinstance(v, dict) and v.get("token"):
					cont[0] = v["token"]
				umbla(v)
		elif isinstance(o, list):
			for v in o:
				umbla(v)

	umbla(raspuns)
	return gasite, cont[0]


def _linii_tile(md):
	"""the text lines of a tile ([[part, ...], ...], without the "•" separators) and whether a line says live now"""
	linii, live = [], False
	for l in md.get("lines") or []:
		parti = []
		for it in ((l.get("lineRenderer") or {}).get("items") or []):
			li = it.get("lineItemRenderer") or {}
			b = (li.get("badge") or {}).get("metadataBadgeRenderer") or {}
			if b.get("style") == "BADGE_STYLE_TYPE_LIVE_NOW":
				live = True
			t = text(li.get("text") or {}).strip()
			if t and t != u"•":
				parti.append(t)
		if parti:
			linii.append(parti)
	return linii, live


def _tile(v):
	"""a TV tile (tileRenderer): film, playlist or channel"""
	md = (v.get("metadata") or {}).get("tileMetadataRenderer") or {}
	titlu = text(md.get("title") or {})
	linii, live = _linii_tile(md)
	antet = (v.get("header") or {}).get("tileHeaderRenderer") or {}
	durata = ""
	for o in antet.get("thumbnailOverlays") or []:
		ts = o.get("thumbnailOverlayTimeStatusRenderer")
		if ts:
			if ts.get("style") == "LIVE":
				live = True
			else:
				durata = text(ts.get("text") or {})
	cmd = v.get("onSelectCommand") or {}
	fel = v.get("contentType", "")
	autor = linii[0][0] if linii else ""
	rest = [x for l in linii[1:] for x in l]
	if fel == "TILE_CONTENT_TYPE_CHANNEL":
		cid = ((cmd.get("browseEndpoint") or {}).get("browseId")) or v.get("contentId") or ""
		if not cid:
			return None
		return {"fel": "canal", "id": cid, "titlu": titlu, "autor": "", "autor_id": cid, "durata": "",
			"vizionari": " ".join(x for l in linii for x in l), "data": "", "live": False, "poza": _poza(antet.get("thumbnail"))}
	if fel == "TILE_CONTENT_TYPE_PLAYLIST":
		pid = v.get("contentId") or ((cmd.get("watchPlaylistEndpoint") or {}).get("playlistId")) or \
			((cmd.get("browseEndpoint") or {}).get("browseId")) or ""
		if pid.startswith("VL"):
			pid = pid[2:]
		if not pid:
			return None
		return {"fel": "lista", "id": pid, "titlu": titlu, "autor": autor, "autor_id": "", "durata": durata, "vizionari": "",
			"data": "", "live": False, "poza": _poza(antet.get("thumbnail"))}
	vid = ((cmd.get("watchEndpoint") or {}).get("videoId")) or ((cmd.get("reelWatchEndpoint") or {}).get("videoId")) or \
		(v.get("contentId") if fel in ("TILE_CONTENT_TYPE_VIDEO", "TILE_CONTENT_TYPE_SHORTS", "") else "")
	if not vid:
		return None
	# the small 320x180 thumbnail instead of the tile's 640x360 one: less to download and decode on a weak receiver
	return {"fel": "film", "id": vid, "titlu": titlu, "autor": autor, "autor_id": "", "durata": "" if live else durata,
		"vizionari": rest[0] if rest else "", "data": rest[1] if len(rest) > 1 else "", "live": live,
		"poza": "https://i.ytimg.com/vi/%s/mqdefault.jpg" % vid}


def _titlu_raft(v):
	h = (v.get("headerRenderer") or {}).get("shelfHeaderRenderer") or {}
	a = ((h.get("avatarLockup") or {}).get("avatarLockupRenderer") or {}).get("title")
	return text(a or h.get("title") or v.get("title") or {}).strip()


def elemente_tv(raspuns):
	"""(items, continuation token) of a TV topic page: a "raft" row (the shelf's title) before the tiles of each shelf;
	the continuation is the one of the section list (the next shelves), not those of the shelves themselves"""
	gasite, vazute, cont = [], set(), [None]

	def umbla(o):
		if isinstance(o, dict):
			for k, v in o.items():
				if not isinstance(v, (dict, list)):
					continue
				if k == "tileRenderer" and isinstance(v, dict):
					e = _tile(v)
					if e and e["titlu"] and (e["fel"], e["id"]) not in vazute:
						vazute.add((e["fel"], e["id"]))
						gasite.append(e)
					continue
				if k == "shelfRenderer" and isinstance(v, dict):
					t = _titlu_raft(v)
					if t:
						gasite.append({"fel": "raft", "id": "", "titlu": t, "autor": "", "autor_id": "", "durata": "",
							"vizionari": "", "data": "", "live": False, "poza": ""})
				if k in ("sectionListRenderer", "sectionListContinuation") and isinstance(v, dict):
					for c in v.get("continuations") or []:
						t = (c.get("nextContinuationData") or {}).get("continuation")
						if t:
							cont[0] = t
				umbla(v)
		elif isinstance(o, list):
			for v in o:
				umbla(v)

	umbla(raspuns)
	# a shelf whose tiles were all shown already (or were not films) leaves no empty title behind
	curat = [e for i, e in enumerate(gasite) if e["fel"] != "raft" or (i + 1 < len(gasite) and gasite[i + 1]["fel"] != "raft")]
	return curat, cont[0]


def elemente_topuri(raspuns):
	"""the chart playlists of a YouTube Music charts answer: a "raft" row per shelf, then its playlists (artists and
	other entries without a playlist are left out)"""
	gasite = []

	def umbla(o):
		if isinstance(o, dict):
			for k, v in o.items():
				if k == "musicCarouselShelfRenderer" and isinstance(v, dict):
					antet = (v.get("header") or {}).get("musicCarouselShelfBasicHeaderRenderer") or {}
					liste = []
					for it in v.get("contents") or []:
						m = it.get("musicTwoRowItemRenderer") if isinstance(it, dict) else None
						if not m:
							continue
						bid = ((m.get("navigationEndpoint") or {}).get("browseEndpoint") or {}).get("browseId", "")
						if not bid.startswith("VL"):
							continue
						liste.append({"fel": "lista", "id": bid[2:], "titlu": text(m.get("title") or {}), "autor": "YouTube",
							"autor_id": "", "durata": "", "vizionari": "", "data": "", "live": False,
							"poza": _poza((((m.get("thumbnailRenderer") or {}).get("musicThumbnailRenderer") or {}).get("thumbnail")))})
					if liste:
						gasite.append({"fel": "raft", "id": "", "titlu": text(antet.get("title") or {}), "autor": "", "autor_id": "",
							"durata": "", "vizionari": "", "data": "", "live": False, "poza": ""})
						gasite.extend(x for x in liste if x["titlu"])
					continue
				umbla(v)
		elif isinstance(o, list):
			for v in o:
				umbla(v)

	umbla(raspuns)
	return gasite


def http_implicit(url, date=None, antete=None, termen=TERMEN_S):
	"""POST (date given) or GET; the body as bytes; HTTPError keeps the answer body (InnerTube puts the reason there)"""
	import gzip
	cerere = Request(url, data=date, headers=dict(antete or {}))
	try:
		r = urlopen(cerere, timeout=termen)
		corp = r.read()
		if r.headers.get("Content-Encoding") == "gzip":
			corp = gzip.decompress(corp)
		return r.getcode(), corp
	except HTTPError as e:
		return e.code, e.read()


def _limba_tara(limba):
	"""("ro", "RO") from a receiver language like "ro_RO"; ("en", "US") when unknown"""
	m = re.match(r"^([a-z]{2,3})(?:[_-]([A-Za-z]{2}))?", limba or "")
	if not m:
		return "en", "US"
	return m.group(1), (m.group(2) or {"en": "US", "ro": "RO", "de": "DE", "it": "IT", "fr": "FR", "es": "ES", "tr": "TR",
		"pl": "PL", "hu": "HU", "ru": "RU", "uk": "UA", "el": "GR", "nl": "NL", "pt": "PT", "ar": "SA"}.get(m.group(1), "US")).upper()


# ---------------------------------------------------------------------------------------------------------------------

class Stare(object):
	"""the small persistent state: visitorData, search history, watched films; written rarely (flash)"""

	def __init__(self, fisier=FISIER_STARE):
		self.fisier = fisier
		self.lacat = threading.Lock()
		self.d = {"vizitator": "", "vizitator_t": 0, "cautari": [], "vazute": []}
		try:
			with open(fisier, "rb") as f:
				d = json.loads(f.read(256 * 1024).decode("utf-8"))
			if isinstance(d, dict):
				self.d.update(d)
		except (IOError, OSError, ValueError):
			pass

	def scrie(self):
		with self.lacat:
			try:
				tmp = self.fisier + ".tmp"
				with open(tmp, "w") as f:
					json.dump(self.d, f)
				os.replace(tmp, self.fisier)
			except (IOError, OSError) as e:
				print("[HdsYouTube] state not written: %s" % e)

	def vizitator(self):
		if self.d.get("vizitator") and time.time() - float(self.d.get("vizitator_t") or 0) < VISITOR_MAX_S:
			return self.d["vizitator"]
		return ""

	def pune_vizitator(self, v):
		if v and v != self.d.get("vizitator"):
			self.d["vizitator"], self.d["vizitator_t"] = v, int(time.time())
			self.scrie()

	def cautari(self):
		return list(self.d.get("cautari") or [])

	def adauga_cautare(self, t):
		t = (t or "").strip()
		if not t:
			return
		l = [x for x in self.cautari() if x.lower() != t.lower()]
		self.d["cautari"] = ([t] + l)[:MAX_ISTORIC]
		self.scrie()

	def sterge_cautari(self):
		self.d["cautari"] = []
		self.scrie()

	def vazute(self):
		return [e for e in (self.d.get("vazute") or []) if isinstance(e, dict) and e.get("id")]

	def adauga_vazut(self, e):
		if not e or e.get("fel") != "film":
			return
		mic = dict((k, e.get(k, "")) for k in ("fel", "id", "titlu", "autor", "autor_id", "durata", "poza"))
		mic["live"] = bool(e.get("live"))
		self.d["vazute"] = ([mic] + [x for x in self.vazute() if x.get("id") != mic["id"]])[:MAX_VAZUTE]
		self.scrie()


def clienti(fisier=FISIER_CLIENTI):
	"""the client table: the feed package's file when valid, else the built-in one"""
	try:
		with open(fisier, "rb") as f:
			d = json.loads(f.read(64 * 1024).decode("utf-8"))
		if isinstance(d, dict) and isinstance(d.get("date"), dict) and isinstance(d.get("redare"), list) and d["redare"]:
			if not isinstance(d.get("tv"), dict):
				d["tv"] = CLIENTI_IMPLICITI["tv"]      # an older feed file without the TV client
			return d
	except (IOError, OSError, ValueError):
		pass
	return CLIENTI_IMPLICITI


class YouTube(object):
	"""InnerTube without an account. limba: the receiver's language ("ro_RO"); http(url, data, headers) -> (code, bytes)"""

	def __init__(self, limba="en_US", http=None, stare=None, tabel=None, dosar_tmp=DOSAR_TMP):
		self.hl, self.gl = _limba_tara(limba)
		self.http = http or http_implicit
		self.stare = stare if stare is not None else Stare()
		self.tabel = tabel or clienti()
		self.dosar_tmp = dosar_tmp

	# --- transport ---------------------------------------------------------------------------------------------------
	def _cere(self, capat, client, corp, vizitator=None, gl=None):
		ctx = {"clientName": client["clientName"], "clientVersion": client["clientVersion"], "hl": self.hl,
			"gl": (gl or self.gl).upper()}
		ctx.update(client.get("extra") or {})
		if vizitator:
			ctx["visitorData"] = vizitator
		date = {"context": {"client": ctx}}
		date.update(corp)
		antete = {"Content-Type": "application/json", "User-Agent": client.get("ua", ""), "Accept-Encoding": "gzip",
			"X-Youtube-Client-Name": str(client.get("id", "")), "X-Youtube-Client-Version": client["clientVersion"],
			"Origin": "https://www.youtube.com"}
		if vizitator:
			antete["X-Goog-Visitor-Id"] = vizitator
		t0 = time.time()
		try:
			cod, raspuns = self.http(API % capat, json.dumps(date).encode("utf-8"), antete)
		except (URLError, IOError, OSError) as e:
			raise EroareYouTube("retea: %s" % getattr(e, "reason", e))
		t1 = time.time()
		try:
			j = json.loads(raspuns.decode("utf-8"))
		except (ValueError, UnicodeDecodeError, AttributeError):
			raise EroareYouTube("HTTP %s" % cod)
		if cod != 200 and not j.get("playabilityStatus"):
			mesaj = ((j.get("error") or {}).get("message") or "") if isinstance(j, dict) else ""
			raise EroareYouTube(mesaj or "HTTP %s" % cod)
		v = (j.get("responseContext") or {}).get("visitorData")
		if v and not self.stare.vizitator():
			# kept only when there is none: every answer carries one, and rewriting it on each call would write flash
			self.stare.pune_vizitator(v)
		print("[HdsYouTube] %s %s: %d B, network %.2f s, parse %.2f s" % (capat, client["clientName"], len(raspuns), t1 - t0,
			time.time() - t1))
		return j

	def _date(self, capat, corp):
		return elemente(self._cere(capat, self.tabel["date"], corp, self.stare.vizitator() or None))

	def vizitator(self, nou=False):
		"""an anonymous visitorData (any data answer carries one); cached on disk"""
		v = "" if nou else self.stare.vizitator()
		if not v:
			j = self._cere("browse", self.tabel["date"], {"browseId": "FEwhat_to_watch"})
			v = (j.get("responseContext") or {}).get("visitorData") or ""
			self.stare.pune_vizitator(v)
		return v

	# --- lists -------------------------------------------------------------------------------------------------------
	def acasa(self):
		"""the recommended films for the receiver's country (the anonymous home page)"""
		return self._date("browse", {"browseId": "FEwhat_to_watch"})

	def cauta(self, interogare, fel="film"):
		corp = {"query": interogare}
		if FILTRE.get(fel):
			corp["params"] = FILTRE[fel]
		return self._date("search", corp)

	def continua(self, capat, token):
		"""the next page of a list; capat: the endpoint of the first page ("browse", "search", "next"; "tv:<country>"
		for a topic page)"""
		if capat.startswith("tv:"):
			return elemente_tv(self._cere("browse", self._tv(), {"continuation": token}, self.stare.vizitator() or None,
				gl=capat[3:] or None))
		return self._date(capat, {"continuation": token})

	def _tv(self):
		return self.tabel.get("tv") or CLIENTI_IMPLICITI["tv"]

	def rubrica(self, browse_id, tara=None):
		"""a topic page (RUBRICI: music, gaming, news, sports, podcasts, live) as shelves: a "raft" row (the shelf's
		title) before its films. YouTube picks these by the receiver's internet address (gl changes nothing, measured
		for 0.8.0); the charts of a chosen country come from topuri()"""
		return elemente_tv(self._cere("browse", self._tv(), {"browseId": browse_id}, self.stare.vizitator() or None,
			gl=tara))

	def topuri(self, tara):
		"""the music charts of a country (YouTube Music, FEmusic_charts, anonymous): the playlists "Top 20 trending",
		"daily top music videos", "Top 100 music videos" (and genres for some countries), with their shelf titles, in the
		receiver's language; [] when the country has none"""
		c = self.tabel.get("muzica") or CLIENT_MUZICA
		corp = {"context": {"client": {"clientName": c["clientName"], "clientVersion": c["clientVersion"], "hl": self.hl,
			"gl": tara.upper()}}, "browseId": "FEmusic_charts", "formData": {"selectedValues": [tara.upper()]}}
		antete = {"Content-Type": "application/json", "User-Agent": c.get("ua", ""), "Accept-Encoding": "gzip",
			"Origin": "https://music.youtube.com", "X-Youtube-Client-Name": str(c.get("id", "")),
			"X-Youtube-Client-Version": c["clientVersion"]}
		t0 = time.time()
		try:
			cod, raspuns = self.http(API_MUZICA % "browse", json.dumps(corp).encode("utf-8"), antete)
			j = json.loads(raspuns.decode("utf-8"))
		except (URLError, IOError, OSError, ValueError, UnicodeDecodeError) as e:
			raise EroareYouTube("retea: %s" % getattr(e, "reason", e))
		if cod != 200:
			mesaj = ((j.get("error") or {}).get("message") or "") if isinstance(j, dict) else ""
			raise EroareYouTube(mesaj or "HTTP %s" % cod)
		print("[HdsYouTube] charts %s: %d B, %.2f s" % (tara, len(raspuns), time.time() - t0))
		return elemente_topuri(j)

	def muzica(self, tara):
		"""the Music rubric: the charts of the chosen country first, then the music page of the receiver's region; the
		continuation is the music page's"""
		try:
			sus = self.topuri(tara) if tara else []
		except EroareYouTube as e:
			print("[HdsYouTube] charts: %s" % e)
			sus = []
		jos, cont = self.rubrica("FEtopics_music", tara)
		return sus + jos, cont

	def canal(self, cid, toate=True):
		"""a channel's films (the Videos tab); toate=False: the channel's home page (shelves, playlists)"""
		corp = {"browseId": cid}
		if toate:
			corp["params"] = FILA_VIDEOS
		return self._date("browse", corp)

	def lista(self, pid):
		return self._date("browse", {"browseId": pid if pid.startswith("VL") else "VL" + pid})

	def inrudite(self, vid):
		e, cont = self._date("next", {"videoId": vid})
		return [x for x in e if x["id"] != vid], cont

	def urmeaza(self, vid):
		"""(details, related films) of a film from one "next" answer: details = {"data": the publishing text,
		"aprecieri": the likes, "urmatorul": YouTube's own "up next" film id (autoplay), "autor"}; for the player's
		bars and the next clip (YTN4)"""
		j = self._cere("next", self.tabel["date"], {"videoId": vid}, self.stare.vizitator() or None)
		e, _cont = elemente(j)
		return date_next(j), [x for x in e if x["id"] != vid and x["fel"] == "film"]

	def lista_tot(self, pid, maxim=200):
		"""all the films of a playlist (its pages one after another, at most `maxim`): for "play all" (YTN4)"""
		e, cont = self.lista(pid)
		filme = [x for x in e if x["fel"] == "film"]
		pagini = 0
		while cont and len(filme) < maxim and pagini < 10:
			e, cont = self.continua("browse", cont)
			vazute = set(x["id"] for x in filme)
			filme += [x for x in e if x["fel"] == "film" and x["id"] not in vazute]
			pagini += 1
		return filme[:maxim]

	# --- playback ----------------------------------------------------------------------------------------------------
	def _player(self, client, vid):
		corp = {"videoId": vid, "contentCheckOk": True, "racyCheckOk": True}
		if client.get("params"):
			corp["params"] = client["params"]
		viz = None
		if client.get("vizitator"):
			viz = self.vizitator()
		j = self._cere("player", client, corp, viz)
		ps = j.get("playabilityStatus") or {}
		if ps.get("status") == "LOGIN_REQUIRED" and client.get("vizitator"):
			# a stale visitorData looks like a bot to YouTube: one fresh one, once
			j = self._cere("player", client, corp, self.vizitator(nou=True))
		return j

	def redare(self, vid, inaltime=720, fps_max=30):
		"""what the image's player gets for a film or a live: {"fel": "mpd"|"hls"|"url", "adresa", "titlu", "live",
		"durata", "expira", "client"}. Raises EroareYouTube with YouTube's reason (or a short one) when nothing plays."""
		motive = []
		for client in self.tabel["redare"]:
			try:
				j = self._player(client, vid)
			except EroareYouTube as e:
				motive.append(str(e))
				continue
			ps = j.get("playabilityStatus") or {}
			if ps.get("status") != "OK":
				motive.append(ps.get("reason") or ps.get("status") or "?")
				continue
			sd = j.get("streamingData") or {}
			vd = j.get("videoDetails") or {}
			live = bool(vd.get("isLive"))
			baza = {"id": vid, "titlu": vd.get("title") or vid, "live": live, "durata": int(vd.get("lengthSeconds") or 0),
				"expira": int(time.time()) + int(sd.get("expiresInSeconds") or 21540), "client": client["clientName"]}
			baza.update(date_film(j))
			if live:
				if not client.get("live") or not sd.get("hlsManifestUrl"):
					motive.append("live")
					continue
				u = self._varianta_hls(sd["hlsManifestUrl"], client, inaltime)
				cale = self._scrie_hls(vid, u) if u else None
				if cale:
					baza.update({"fel": "hls", "adresa": cale, "url": u})
					return baza
				motive.append("hls")
				continue
			v, a = alege_formate(sd.get("adaptiveFormats") or [], inaltime, fps_max)
			if v and a:
				cale = self._scrie_mpd(vid, v, a)
				if cale:
					baza.update({"fel": "mpd", "adresa": cale, "inaltime": int(v.get("height") or 0),
						"video": info_format(v), "audio": info_format(a)})
					return baza
			if sd.get("hlsManifestUrl") and client.get("live"):
				# a live that has just ended (isPostLiveDvr, seen in 0.8.0 tests): its streams are live
				# segments without index ranges, so no MPD; the HLS list plays it from the beginning, like a live
				u = self._varianta_hls(sd["hlsManifestUrl"], client, inaltime)
				cale = self._scrie_hls(vid, u) if u else None
				if cale:
					baza.update({"fel": "hls", "adresa": cale, "url": u})
					return baza
			muxat = [f for f in sd.get("formats") or [] if f.get("url") and "avc1" in f.get("mimeType", "")]
			if muxat:
				f = max(muxat, key=lambda x: int(x.get("height") or 0))
				baza.update({"fel": "url", "adresa": f["url"], "inaltime": int(f.get("height") or 0),
					"video": info_format(f)})
				return baza
			motive.append("formate")
		raise EroareYouTube(motive[0] if motive else "?")

	def _varianta_hls(self, master, client, inaltime):
		"""the muxed HLS variant (picture and sound in one TS) with the largest height <= inaltime; the master's URL
		when the list cannot be read (hlsdemux then picks itself)"""
		try:
			cod, corp = self.http(master, None, {"User-Agent": client.get("ua", "")})
			if cod != 200:
				return master
			return varianta_hls(corp.decode("utf-8", "replace"), inaltime) or master
		except (URLError, IOError, OSError):
			return master

	def _scrie_hls(self, vid, u):
		"""a one-variant HLS master in /tmp pointing at the chosen variant: the receiver's player opened the
		googlevideo variant URL directly with souphttpsrc and stopped on "http source timeout" (seen on a ZGEMMA), while
		the same variant through a local master played; it also keeps the long URL out of the service reference"""
		return self._scrie(vid, ".m3u8", '#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=3000000,CODECS="avc1.4d401f,mp4a.40.2"\n%s\n' % u)

	def _scrie_mpd(self, vid, v, a):
		return self._scrie(vid, ".mpd", text_mpd(v, a))

	def _scrie(self, vid, extensie, continut):
		try:
			if not os.path.isdir(self.dosar_tmp):
				os.makedirs(self.dosar_tmp)
			sigur = "".join(c for c in str(vid) if c.isalnum() or c in "-_")[:32]
			nume = (MPD % sigur)[:-4] + extensie
			cale = os.path.join(self.dosar_tmp, nume)
			tmp = cale + ".tmp"
			with open(tmp, "w") as f:
				f.write(continut)
			os.replace(tmp, cale)
			for vechi in os.listdir(self.dosar_tmp):
				if vechi.startswith("hds-youtube-") and not vechi.startswith(nume) and \
						(vechi.endswith(".mpd") or vechi.endswith(".m3u8") or vechi.endswith(".cuts")):
					try:
						os.remove(os.path.join(self.dosar_tmp, vechi))
					except OSError:
						pass
			return cale
		except (IOError, OSError, KeyError, ValueError, TypeError) as e:
			print("[HdsYouTube] %s not written: %s" % (extensie, e))
			return None

	# --- thumbnails --------------------------------------------------------------------------------------------------
	def poza(self, e, url=None, http=None):
		"""the local file of an item's thumbnail (downloaded once to /tmp), or None. url: another address than the
		item's (the tiles take the 320x180 one, YTN3), kept in its own file; http: the transport (the tile downloader
		keeps its connections open)"""
		u = url or (e.get("poza") if isinstance(e, dict) else None)
		if not u:
			return None
		dosar = os.path.join(self.dosar_tmp, "poze")
		cale = os.path.join(dosar, "%s%s-%s.jpg" % ("d-" if url else "", e.get("fel", "x"),
			"".join(c for c in e.get("id", "") if c.isalnum() or c in "-_")[:40]))
		if os.path.exists(cale):
			return cale
		try:
			if not os.path.isdir(dosar):
				os.makedirs(dosar)
			cod, corp = (http or self.http)(u, None, {"User-Agent": "Mozilla/5.0"})
			if cod != 200 or not corp:
				return None
			with open(cale + ".tmp", "wb") as f:
				f.write(corp)
			os.replace(cale + ".tmp", cale)
			fisiere = os.listdir(dosar)
			if len(fisiere) > MAX_POZE:
				vechi = []
				for x in fisiere:
					try:
						vechi.append((os.path.getmtime(os.path.join(dosar, x)), x))
					except OSError:
						pass
				for _t, x in sorted(vechi)[:-MAX_POZE]:
					try:
						os.remove(os.path.join(dosar, x))
					except OSError:
						pass
			return cale
		except (URLError, IOError, OSError):
			return None


class Descarcator(object):
	"""the thumbnails of the tile grid (YTN3): `fire` threads, each with its HTTPS connections kept open (on a weak
	receiver the TLS handshake is most of a thumbnail's 0.3 s), downloading in the order of the last cere(); what was
	asked before and not started yet is dropped. The results are taken by the main loop with gata()."""

	def __init__(self, yt, fire=2):
		self.yt = yt
		self.fire = fire
		self.cond = threading.Condition()
		self.coada = []                 # [(url, item)] still to download, the first one first
		self.rezultate = []             # [(url, file or None)]
		self.inLucru = 0
		self.vie = True
		self.pornite = []

	def cere(self, lista):
		"""lista: [(url, item)] in order; replaces what was waiting"""
		with self.cond:
			self.coada = list(lista)
			if self.coada and len(self.pornite) < self.fire:
				for _i in range(self.fire - len(self.pornite)):
					f = threading.Thread(target=self._lucreaza, name="HdsYouTubePoze")
					f.daemon = True
					self.pornite.append(f)
					f.start()
			self.cond.notify_all()

	def ocupat(self):
		with self.cond:
			return bool(self.coada or self.inLucru or self.rezultate)

	def gata(self):
		with self.cond:
			r, self.rezultate = self.rezultate, []
		return r

	def opreste(self):
		with self.cond:
			self.vie = False
			self.coada = []
			self.cond.notify_all()

	def _lucreaza(self):
		legaturi = {}

		def http(url, date=None, antete=None, termen=10):
			return _ia_pastrat(legaturi, url, antete, termen)
		try:
			while True:
				with self.cond:
					while self.vie and not self.coada:
						self.cond.wait(30)
						if not self.coada and self.vie:
							# nothing asked for half a minute: the connections are closed until the next request
							for c in legaturi.values():
								try:
									c.close()
								except Exception:
									pass
							legaturi.clear()
					if not self.vie:
						return
					url, e = self.coada.pop(0)
					self.inLucru += 1
				cale = None
				try:
					cale = self.yt.poza(e, url, http)
				except Exception as x:
					print("[HdsYouTube] thumbnail: %s" % x)
				with self.cond:
					self.inLucru -= 1
					self.rezultate.append((url, cale))
		finally:
			for c in legaturi.values():
				try:
					c.close()
				except Exception:
					pass


def _ia_pastrat(legaturi, url, antete=None, termen=10):
	"""GET with a connection per host kept open between calls (one retry on a fresh one); (code, body)"""
	try:
		from http.client import HTTPSConnection, HTTPConnection, HTTPException
		from urllib.parse import urlsplit
	except ImportError:  # pragma: no cover
		return http_implicit(url, None, antete, termen)
	p = urlsplit(url)
	cale = p.path + ("?" + p.query if p.query else "")
	cheie = (p.scheme, p.netloc)
	for _incercare in (0, 1):
		c = legaturi.get(cheie)
		if c is None:
			c = (HTTPSConnection if p.scheme == "https" else HTTPConnection)(p.netloc, timeout=termen)
			legaturi[cheie] = c
		try:
			c.request("GET", cale, headers=dict(antete or {}))
			r = c.getresponse()
			corp = r.read()
			return r.status, corp
		except (HTTPException, IOError, OSError):
			try:
				c.close()
			except Exception:
				pass
			legaturi.pop(cheie, None)
	return 0, b""


def info_format(f):
	"""what the player's bars show of a stream: itag, codec, size, frame rate, bit rate, sound track name"""
	m = f.get("mimeType", "")
	codec = m.split('codecs="', 1)[1].split('"', 1)[0] if 'codecs="' in m else ""
	return {"itag": int(f.get("itag") or 0), "codec": codec, "latime": int(f.get("width") or 0),
		"inaltime": int(f.get("height") or 0), "fps": int(f.get("fps") or 0),
		"debit": int(f.get("averageBitrate") or f.get("bitrate") or 0), "marime": int(f.get("contentLength") or 0),
		"limba": ((f.get("audioTrack") or {}).get("displayName") or "")}


_CAPITOL = re.compile(u"^\\s*[\\(\\[]?((?:\\d{1,2}:)?\\d{1,2}:\\d{2})[\\)\\]]?\\s*[-–—:|.]*\\s*(.+?)\\s*$")


def capitole(descriere):
	"""the chapters written in a description ("0:00 Intro" lines; YouTube's own rule: the first at 0:00, at least
	three, in order): [(seconds, title)]"""
	rez = []
	for linie in (descriere or "").splitlines():
		m = _CAPITOL.match(linie)
		if not m:
			continue
		s = 0
		for parte in m.group(1).split(":"):
			s = s * 60 + int(parte)
		if rez and s <= rez[-1][0]:
			continue
		rez.append((s, m.group(2)[:80]))
	return rez if len(rez) >= 3 and rez[0][0] == 0 else []


def date_film(j):
	"""the film's own data from a player answer, for the player's bars (YTN4): channel, views, description, chapters,
	the subtitle tracks and the sound tracks YouTube offers"""
	vd = j.get("videoDetails") or {}
	piste = (((j.get("captions") or {}).get("playerCaptionsTracklistRenderer") or {}).get("captionTracks") or [])
	subtitrari = []
	for p in piste:
		if isinstance(p, dict) and p.get("baseUrl") and p.get("languageCode"):
			subtitrari.append({"limba": p["languageCode"], "nume": text(p.get("name") or {}) or p["languageCode"],
				"automate": p.get("kind") == "asr", "url": p["baseUrl"]})
	audio, vazute = [], set()
	for f in (j.get("streamingData") or {}).get("adaptiveFormats") or []:
		t = f.get("audioTrack") or {}
		if t.get("id") and t["id"] not in vazute:
			vazute.add(t["id"])
			audio.append({"id": t["id"], "nume": t.get("displayName") or t["id"], "implicita": bool(t.get("audioIsDefault"))})
	descriere = vd.get("shortDescription") or ""
	try:
		vizionari = int(vd.get("viewCount") or 0)
	except ValueError:
		vizionari = 0
	return {"autor": vd.get("author") or "", "autor_id": vd.get("channelId") or "", "vizionari_nr": vizionari,
		"descriere": descriere, "capitole": capitole(descriere), "subtitrari": subtitrari, "piste_audio": audio}


def date_next(j):
	"""from a "next" answer: the publishing text, the likes, the channel and YouTube's own next film (autoplay)"""
	rez = {"data": "", "aprecieri": "", "autor": "", "urmatorul": ""}

	def umbla(o):
		if isinstance(o, dict):
			for k, v in o.items():
				if k == "videoMetadataRenderer" and isinstance(v, dict):
					rez["data"] = rez["data"] or text(v.get("dateText") or {})
					lb = (v.get("likeButton") or {}).get("likeButtonRenderer") or {}
					rez["aprecieri"] = rez["aprecieri"] or text(lb.get("likeCountText") or {}) or str(lb.get("likeCount") or "")
					ow = (v.get("owner") or {}).get("videoOwnerRenderer") or {}
					rez["autor"] = rez["autor"] or text(ow.get("title") or {}).strip()
				elif k == "autoplayVideo" and isinstance(v, dict) and not rez["urmatorul"]:
					rez["urmatorul"] = (v.get("watchEndpoint") or {}).get("videoId") or ""
				umbla(v)
		elif isinstance(o, list):
			for v in o:
				umbla(v)
	umbla(j)
	return rez


def alege_formate(af, inaltime=720, fps_max=30):
	"""(video, audio) adaptiveFormats for the MPD: H.264 MP4 with index ranges, the largest height <= inaltime, frame rate
	<= fps_max first (60 fps only when the film has nothing slower); AAC MP4 audio: the default track, 140 (128k) first"""
	def bun(f, fel, codec):
		m = f.get("mimeType", "")
		return (m.startswith(fel + "/mp4") and codec in m and f.get("url") and
			"start" in (f.get("initRange") or {}) and "start" in (f.get("indexRange") or {}))
	video = [f for f in af if bun(f, "video", "avc1") and int(f.get("height") or 0) <= inaltime]
	audio = [f for f in af if bun(f, "audio", "mp4a")]
	if not video or not audio:
		return None, None
	incete = [f for f in video if int(f.get("fps") or 30) <= fps_max] or video
	v = max(incete, key=lambda f: (int(f.get("height") or 0), int(f.get("bitrate") or 0)))
	# several sound tracks on one film (an auto-dubbed language next to the original): the default one, not the
	# auto-dubbed one, not the dynamic-range-compressed copy
	def cheie(f):
		t = f.get("audioTrack") or {}
		return (t and not t.get("audioIsDefault"), bool(t.get("isAutoDubbed")), bool(f.get("isDrc")),
			int(f.get("itag") or 0) != 140, -int(f.get("bitrate") or 0))
	a = sorted(audio, key=cheie)[0]
	return v, a


def _xml(t):
	return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def text_mpd(v, a):
	"""a static on-demand MPD with one H.264 and one AAC representation (SegmentBase: the index ranges of each file)"""
	def rep(fel, f):
		m = f.get("mimeType", "")
		codecs = m.split('codecs="', 1)[1].split('"', 1)[0] if 'codecs="' in m else ""
		if fel == "video":
			extra = ' width="%d" height="%d" frameRate="%d"' % (int(f.get("width") or 0), int(f.get("height") or 0),
				int(f.get("fps") or 30))
		else:
			extra = ' audioSamplingRate="%d"' % int(f.get("audioSampleRate") or 44100)
		return ('<AdaptationSet mimeType="%s/mp4" segmentAlignment="true" startWithSAP="1">'
			'<Representation id="%s" codecs="%s" bandwidth="%d"%s><BaseURL>%s</BaseURL>'
			'<SegmentBase indexRange="%d-%d"><Initialization range="%d-%d"/></SegmentBase>'
			'</Representation></AdaptationSet>') % (fel, _xml(f.get("itag", fel)), _xml(codecs),
			int(f.get("bitrate") or 0), extra, _xml(f["url"]), int(f["indexRange"]["start"]), int(f["indexRange"]["end"]),
			int(f["initRange"]["start"]), int(f["initRange"]["end"]))
	durata = max(int(v.get("approxDurationMs") or 0), int(a.get("approxDurationMs") or 0)) / 1000.0
	return ('<?xml version="1.0" encoding="UTF-8"?>\n'
		'<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="static" '
		'profiles="urn:mpeg:dash:profile:isoff-on-demand:2011" minBufferTime="PT2S" '
		'mediaPresentationDuration="PT%.3fS"><Period>%s%s</Period></MPD>\n') % (durata, rep("video", v), rep("audio", a))


def varianta_hls(master, inaltime=720):
	"""the URL of the muxed variant (CODECS with both avc1 and mp4a, no separate AUDIO group) with the largest
	height <= inaltime; None when there is none"""
	linii = master.splitlines()
	bune = []
	for i, l in enumerate(linii):
		if not l.startswith("#EXT-X-STREAM-INF") or i + 1 >= len(linii):
			continue
		codecs = re.search(r'CODECS="([^"]*)"', l)
		codecs = codecs.group(1) if codecs else ""
		if "avc1" not in codecs or "mp4a" not in codecs or "AUDIO=" in l:
			continue
		rez = re.search(r"RESOLUTION=\d+x(\d+)", l)
		h = int(rez.group(1)) if rez else 0
		u = linii[i + 1].strip()
		if u and not u.startswith("#") and h <= inaltime:
			bune.append((h, u))
	return max(bune)[1] if bune else None


def referinta(r):
	"""the service reference string for the image's player (4097, gstreamer) of a redare() answer"""
	adresa = r["adresa"].replace(":", "%3a")
	titlu = (r.get("titlu") or "YouTube").replace(":", " ").replace("\n", " ")
	return "4097:0:1:0:0:0:0:0:0:0:%s:%s" % (adresa, titlu)
