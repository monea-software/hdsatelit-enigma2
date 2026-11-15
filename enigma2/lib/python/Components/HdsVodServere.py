# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Filme si seriale (VOD): serverele media de acasa, Emby si Jellyfin, in acelasi ecran ca filmele furnizorului IPTV.

Jellyfin s-a desprins din Emby (2018) si a pastrat API-ul, deci o singura clasa le serveste pe amandoua; unde rutele noi ale
Jellyfin (10.9+) difera, se incearca intai ruta noua, apoi cea veche.
- Serverul se gaseste singur in retea: amandoua raspund pe UDP 7359 la 'who is EmbyServer?' / 'who is JellyfinServer?' cu adresa
  si numele lor; omul scrie numai utilizatorul si parola (o singura data, aici sau in pagina web).
- Datele serverului stau in /etc/enigma2/hds_iptv (dosar 0700, fisier 0600, ca si conturile IPTV). Parola si jetonul nu ies din
  modul: nici in pagina web, nici in jurnal, nici in referinta filmului (redarea trece prin releul local, HdsIptvAdrese /media/,
  care pune jetonul in antet).
- Randurile: 'Continuă de unde ai rămas' (pozitia tinuta pe server: continua si pe telefon sau pe alt televizor), 'Adăugate recent'
  (Latest), apoi bibliotecile serverului; pagina filmului cu pistele audio si subtitrarile serverului; serialele pe sezoane.
- Pozitia se trimite inapoi serverului (Sessions/Playing, Progress la 30 s, Stopped), pe un fir separat.
- Subtitrarile externe ale serverului (fisiere .srt langa film, pe server) se descarca la deschiderea paginii filmului in /tmp, langa
  o cale virtuala data lui HdsSubtitrariFilm (inregistreazaRetea): limba preferata o alege apoi singur, ca la orice film.
- Transcodarea (0.7.5, EMT): receptorul spune serverului ce decodeaza placa lui (DeviceProfile, pe familie: HiSilicon, Broadcom 4K
  ca Vu+ 4K, Broadcom 1080p pe MIPS ca Solo SE) prin PlaybackInfo. Fisierul pe care placa il decodeaza merge direct (/stream
  static, ca pana acum); altfel serverul il transforma (HLS, master.m3u8, H.264 + AC-3/AAC), iar releul trece listele si segmentele
  cu jetonul in antet. La iesire transcodarea se opreste pe server (Stopped + DELETE /Videos/ActiveEncodings), ca serverul sa nu
  ramana incarcat. Server vechi fara PlaybackInfo: aceeasi hotarare facuta aici, din pistele filmului.
"""
import hashlib
import json
import os
import re
import socket
import threading
import time
import uuid

from Components import HdsVod as V
from Components import HdsIptvSurse as I

FELURI = ("emby", "jellyfin")
NUME_FEL = {"emby": "Emby", "jellyfin": "Jellyfin"}
PORT_DESCOPERIRE = 7359
INTREBARE = {"emby": b"who is EmbyServer?", "jellyfin": b"who is JellyfinServer?"}
FISIER = "servere-media.json"
TERMEN_S = 10
MAX_RAND = 1000
MAX_SERVERE = 8
MAX_SUBTITRARI = 3
DOSAR_SUB = "/tmp/hds-vod-sub"
TICK = 10000000                  # 1 s = 10.000.000 tick-uri (100 ns)
VERSIUNE = "0.7.5"
_ID = re.compile(r"^[0-9A-Za-z]{1,40}$")
_SID = re.compile(r"^[0-9a-f]{8}$")


def N_(text):
	return text


E_LOGARE = N_("Serverul nu a primit utilizatorul sau parola. Scrie-le din nou în Filme și seriale > MENU > Schimbă utilizatorul sau parola.")
E_SERVER = N_("Serverul nu răspunde. Verifică dacă este pornit și în aceeași rețea.")
E_ADRESA = N_("Adresa serverului nu este bună (de exemplu http://192.168.1.10:8096).")
T_CONTINUA = N_("Continuă de unde ai rămas")


class EroareServer(V.C.EroareIptv):
	"""mesaj = unul dintre textele E_*; ecranul il arata (HdsVod.lucreaza prinde EroareIptv)."""

	def __init__(self, mesaj, cod=0):
		V.C.EroareIptv.__init__(self, mesaj, cod=cod)


# ------------------------------------------------------------------ fisierul serverelor

def _cale():
	return os.path.join(I.DOSAR, FISIER)


def citeste():
	"""Lista serverelor (cu parola si jetonul: numai pentru acest modul)."""
	try:
		with open(_cale(), encoding="utf-8") as f:
			d = json.load(f)
	except (IOError, OSError, ValueError):
		return []
	return [s for s in d if isinstance(s, dict) and s.get("fel") in FELURI and _SID.match(s.get("id") or "")][:MAX_SERVERE] \
		if isinstance(d, list) else []


def _scrieToate(lista):
	I._asiguraDosar()
	I._scrie(_cale(), json.dumps(lista, ensure_ascii=False, indent=1).encode("utf-8"), 0o600)


def publice():
	"""Fara parola si jeton: pentru ecran si pagina web."""
	return [{"id": s["id"], "fel": s["fel"], "nume": s.get("nume") or NUME_FEL[s["fel"]], "adresa": s.get("adresa", ""),
		"utilizator": s.get("utilizator", ""), "are_parola": bool(s.get("parola"))} for s in citeste()]


def idServer(fel, adresa, utilizator):
	return hashlib.sha1(("%s|%s|%s" % (fel, adresa.rstrip("/").lower(), utilizator)).encode("utf-8")).hexdigest()[:8]


def adresaBuna(adresa):
	"""'192.168.1.10' -> 'http://192.168.1.10:8096'; None daca nu se poate folosi."""
	a = (adresa or "").strip().rstrip("/")
	if not a:
		return None
	if not re.match(r"(?i)^https?://", a):
		a = "http://" + a
	m = re.match(r"(?i)^(https?)://([A-Za-z0-9.\-]{1,253}|\[[0-9A-Fa-f:]{2,45}\])(:\d{1,5})?(/[A-Za-z0-9._~\-/]{0,100})?$", a)
	if not m:
		return None
	if not m.group(3):
		a = "%s://%s:%s%s" % (m.group(1).lower(), m.group(2), "8920" if m.group(1).lower() == "https" else "8096", m.group(4) or "")
	return a


def adauga(fel, adresa, utilizator, parola, cerere=None):
	"""Logarea la server; daca merge, serverul se tine minte. -> (ok, mesaj, id)."""
	if fel not in FELURI:
		return False, E_ADRESA, ""
	a = adresaBuna(adresa)
	if not a:
		return False, E_ADRESA, ""
	s = {"fel": fel, "adresa": a, "utilizator": (utilizator or "").strip()[:100], "parola": (parola or "")[:200]}
	s["id"] = idServer(fel, a, s["utilizator"])
	srv = SursaServer(s, cerere=cerere)
	try:
		srv.logare()
	except EroareServer as e:
		return False, e.mesaj, ""
	lista = [x for x in citeste() if x["id"] != s["id"]]
	lista.insert(0, srv.s)
	_scrieToate(lista[:MAX_SERVERE])
	return True, "", s["id"]


def scoate(sid):
	lista = citeste()
	ramase = [x for x in lista if x["id"] != sid]
	if len(ramase) == len(lista):
		return False
	_scrieToate(ramase)
	try:
		from Components import HdsIptvAdrese as A
		A.ALTE_SURSE.pop(sid, None)
	except ImportError:
		pass
	return True


def _salveazaJeton(s):
	lista = citeste()
	for x in lista:
		if x["id"] == s["id"]:
			x.update(jeton=s.get("jeton", ""), uid=s.get("uid", ""), nume=s.get("nume", ""))
	_scrieToate(lista)


# ------------------------------------------------------------------ cautarea in retea

def descopera(termen=2.0, felurile=FELURI, adrese=("255.255.255.255",)):
	"""Serverele din retea care raspund la intrebarea UDP -> [{"fel", "nume", "adresa", "server_id"}]. Pe firul de lucru."""
	gasite, socluri = {}, []
	try:
		for fel in felurile:
			so = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
			so.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
			so.settimeout(0.2)
			for a in adrese:
				try:
					so.sendto(INTREBARE[fel], (a, PORT_DESCOPERIRE))
				except OSError:
					pass
			socluri.append((fel, so))
		sfarsit = time.monotonic() + termen
		while time.monotonic() < sfarsit:
			for fel, so in socluri:
				try:
					date, _de_la = so.recvfrom(4096)
				except (socket.timeout, OSError):
					continue
				r = raspunsDescoperire(date, fel)
				if r:
					gasite.setdefault((r["server_id"] or r["adresa"]), r)
	finally:
		for _f, so in socluri:
			so.close()
	return list(gasite.values())


def raspunsDescoperire(date, fel):
	"""{"Address": "http://192.168.1.10:8096", "Id": "...", "Name": "..."} -> dict curat sau None."""
	try:
		d = json.loads(date.decode("utf-8", "replace"))
	except ValueError:
		return None
	if not isinstance(d, dict):
		return None
	a = adresaBuna(d.get("Address") or "")
	if not a:
		return None
	return {"fel": fel, "nume": V._text(d.get("Name"), 60) or NUME_FEL[fel], "adresa": a, "server_id": V._text(d.get("Id"), 64)}


# ------------------------------------------------------------------ cererile HTTP

def _cerereRetea(metoda, adresa, antete, corp, termen=TERMEN_S):
	"""-> (cod, octeti). Fara exceptii cu adresa in text (pot avea date de acces): numai felul erorii."""
	from urllib.request import Request, urlopen
	from urllib.error import HTTPError
	r = Request(adresa, data=corp, headers=antete, method=metoda)
	try:
		with urlopen(r, timeout=termen) as f:
			return f.status, f.read(16 * 1024 * 1024)
	except HTTPError as e:
		return e.code, b""
	except Exception as e:
		raise EroareServer(E_SERVER, type(e).__name__)


def _dispozitiv():
	"""Id-ul receptorului pentru server (acelasi la fiecare pornire)."""
	for c in ("/sys/class/net/eth0/address", "/etc/machine-id"):
		try:
			with open(c) as f:
				t = f.read().strip()
			if t:
				return hashlib.sha1(("hds-vod|" + t).encode("utf-8")).hexdigest()[:24]
		except (IOError, OSError):
			pass
	return "hdsatelit-" + uuid.uuid5(uuid.NAMESPACE_DNS, socket.gethostname()).hex[:16]


def _model():
	try:
		with open("/proc/stb/info/boxtype") as f:
			return "HD Satelit " + f.read().strip()[:30]
	except (IOError, OSError):
		return "HD Satelit"


def _ticks(v):
	try:
		return int(v) // TICK
	except (TypeError, ValueError):
		return 0


def _data(v):
	m = re.match(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})", str(v or ""))
	if not m:
		return 0
	import calendar
	return calendar.timegm(tuple(int(x) for x in m.groups()) + (0, 0, 0))


def _limba(cod):
	return V._text(cod, 8).upper()


# ------------------------------------------------------------------ ce decodeaza placa (profilul trimis serverului)

# Familiile de placi. Numai ce stim sigur: HEVC (si pe 10 biti) si 4K pe HiSilicon si pe Broadcom 4K; pe receptoarele MIPS
# (Broadcom 1080p, ca Vu+ Solo SE) fara HEVC si cel mult 1920x1080. H.264 pe 10 biti (Hi10P) nu il decodeaza nicio placa.
# Ce nu e in liste (AV1, VP9, VC-1, TrueHD, DTS, FLAC, Opus, Vorbis) il transforma serverul: mai bine un film transcodat
# decat unul fara imagine sau fara sunet.
HISILICON, BCM_4K, BCM_1080 = "hisilicon", "bcm4k", "bcm1080"
FAMILIE = None                   # None = aflata la prima redare; probele o pun de mana
VIDEO_DIRECT = {HISILICON: "h264,hevc,mpeg2video,mpeg4", BCM_4K: "h264,hevc,mpeg2video,mpeg4", BCM_1080: "h264,mpeg2video,mpeg4"}
AUDIO_DIRECT = "aac,mp3,mp2,ac3,eac3"
CONTAINERE_DIRECT = "mkv,mp4,m4v,mov,ts,mpegts,m2ts,avi"
MARGINI = {HISILICON: (4096, 2304), BCM_4K: (4096, 2304), BCM_1080: (1920, 1080)}
BITI = {"h264": 8, "hevc": 10}
DEBIT = {HISILICON: 120000000, BCM_4K: 120000000, BCM_1080: 40000000}   # reteaua de acasa
VIDEO_TRANSCODARE = "h264"
AUDIO_TRANSCODARE = "ac3,aac,mp3"   # AC-3 intai: 5.1 ramane 5.1
CANALE_TRANSCODARE = 6
DEBIT_SUNET = 640000
_familie = {"v": None}


def familie():
	if FAMILIE:
		return FAMILIE
	if _familie["v"] is None:
		f = BCM_4K
		try:
			from Components.HdsEcranNegru import hisilicon
			hisi = hisilicon()
		except Exception:
			hisi = os.path.isdir("/proc/hisi/msp")
		if hisi:
			f = HISILICON
		else:
			try:
				arh = os.uname().machine.lower()
			except (AttributeError, OSError):
				arh = ""
			if arh.startswith(("mips", "sh4")):
				f = BCM_1080
		_familie["v"] = f
	return _familie["v"]


def _conditie(proprietate, valoare):
	return {"Condition": "LessThanEqual", "Property": proprietate, "Value": str(valoare), "IsRequired": False}


def profilDispozitiv(fam=None):
	"""DeviceProfile (aceeasi forma la Emby si Jellyfin): ce reda placa direct, cum vrea transcodarea, subtitrarile fara ardere."""
	fam = fam or familie()
	lat, ina = MARGINI[fam]
	video = VIDEO_DIRECT[fam]
	marime = [_conditie("Width", lat), _conditie("Height", ina)]
	codec = [{"Type": "Video", "Codec": c, "Conditions": marime + ([_conditie("VideoBitDepth", BITI[c])] if c in BITI else [])}
		for c in video.split(",")]
	return {
		"Name": "HD Satelit (%s)" % fam,
		"MaxStreamingBitrate": DEBIT[fam], "MaxStaticBitrate": DEBIT[fam], "MusicStreamingTranscodingBitrate": 192000,
		"DirectPlayProfiles": [{"Type": "Video", "Container": CONTAINERE_DIRECT, "VideoCodec": video, "AudioCodec": AUDIO_DIRECT}],
		"TranscodingProfiles": [{"Type": "Video", "Container": "ts", "Protocol": "hls", "Context": "Streaming",
			"VideoCodec": VIDEO_TRANSCODARE, "AudioCodec": AUDIO_TRANSCODARE, "MaxAudioChannels": str(CANALE_TRANSCODARE),
			"MinSegments": 1, "BreakOnNonKeyFrames": True, "CopyTimestamps": False}],
		"ContainerProfiles": [],
		"CodecProfiles": codec,
		"SubtitleProfiles": [{"Format": f, "Method": "Embed"} for f in ("srt", "subrip", "ass", "ssa", "pgssub", "dvbsub")] +
			[{"Format": f, "Method": "External"} for f in ("srt", "subrip", "ass", "ssa", "vtt")],
		"ResponseProfiles": [],
	}


def _numar(v):
	try:
		return int(v or 0)
	except (TypeError, ValueError):
		return 0


def potrivire(sursa_media, fam=None):
	"""(imaginea merge direct, sunetul merge direct, containerul merge direct) pentru o MediaSource a serverului."""
	fam = fam or familie()
	sursa_media = sursa_media if isinstance(sursa_media, dict) else {}
	piste = [p for p in (sursa_media.get("MediaStreams") or []) if isinstance(p, dict)]
	containere = [c.strip() for c in str(sursa_media.get("Container") or "").lower().split(",") if c.strip()]
	cont = any(c in CONTAINERE_DIRECT.split(",") for c in containere)
	lat, ina = MARGINI[fam]
	video = next((p for p in piste if p.get("Type") == "Video"), None)
	img = True
	if video is not None:
		c = str(video.get("Codec") or "").lower()
		img = c in VIDEO_DIRECT[fam].split(",") and _numar(video.get("Width")) <= lat and _numar(video.get("Height")) <= ina \
			and _numar(video.get("BitDepth")) <= BITI.get(c, 8)
	sunete = [p for p in piste if p.get("Type") == "Audio"]
	audio = next((p for p in sunete if p.get("IsDefault")), sunete[0] if sunete else None)
	sun = audio is None or str(audio.get("Codec") or "").lower() in AUDIO_DIRECT.split(",")
	return img, sun, cont


# ------------------------------------------------------------------ sursa

class SursaServer(V.Sursa):
	continuaPeServer = True
	cu_recente_locale = True

	def __init__(self, s, cerere=None):
		V.Sursa.__init__(self, s)
		self.fel = s["fel"]
		self.grupa = s["fel"]
		self.nume = V._text(s.get("nume"), 60) or NUME_FEL[self.fel]
		self.adresa = s["adresa"].rstrip("/")
		self._cerere = cerere or _cerereRetea
		self._lacat = threading.Lock()
		self._pozitii = {}            # cheie -> secunde (de la server)
		self._sesiuni = {}            # cheie -> PlaySessionId
		self._redari = {}             # cheie -> hotararea redarii (metoda, adresa, sesiune, sursa media), o data pe redare
		self._lacatRedare = threading.Lock()
		self._coada = []
		self._fir = None

	# -------------------------------------------------- legatura

	def _autorizare(self, cu_jeton=True):
		t = 'MediaBrowser Client="HD Satelit", Device="%s", DeviceId="%s", Version="%s"' % (_model(), _dispozitiv(), VERSIUNE)
		if cu_jeton and self.s.get("jeton"):
			t += ', Token="%s"' % self.s["jeton"]
		return t

	def antete(self, cu_jeton=True):
		a = {"Accept": "application/json", "Authorization": self._autorizare(cu_jeton),
			"X-Emby-Authorization": self._autorizare(cu_jeton)}
		if cu_jeton and self.s.get("jeton"):
			a["X-Emby-Token"] = self.s["jeton"]
			a["X-MediaBrowser-Token"] = self.s["jeton"]
		return a

	def logare(self):
		corp = json.dumps({"Username": self.s.get("utilizator", ""), "Pw": self.s.get("parola", "")}).encode("utf-8")
		a = dict(self.antete(False), **{"Content-Type": "application/json"})
		cod, date = self._cerere("POST", self.adresa + "/Users/AuthenticateByName", a, corp)
		if cod in (401, 403):
			raise EroareServer(E_LOGARE, cod)
		if cod != 200:
			raise EroareServer(E_SERVER, cod)
		try:
			d = json.loads(date.decode("utf-8"))
			self.s["jeton"] = str(d["AccessToken"])
			self.s["uid"] = str(d["User"]["Id"])
		except (ValueError, KeyError, TypeError):
			raise EroareServer(E_SERVER, "raspuns")
		self.s["nume"] = self.s.get("nume") or NUME_FEL[self.fel]
		return True

	def _json(self, metoda, cale, corp=None, reincearca=True):
		if not self.s.get("jeton"):
			self.logare()
			_salveazaJeton(self.s)
		a = self.antete()
		if corp is not None:
			a["Content-Type"] = "application/json"
		cod, date = self._cerere(metoda, self.adresa + cale, a, None if corp is None else json.dumps(corp).encode("utf-8"))
		if cod == 401 and reincearca and self.s.get("parola"):
			self.s["jeton"] = ""
			return self._json(metoda, cale, corp, False)
		if cod in (401, 403):
			raise EroareServer(E_LOGARE, cod)
		if cod == 404:
			raise EroareServer(V.E_LIPSA, 404)
		if cod not in (200, 204):
			raise EroareServer(E_SERVER, cod)
		if not date:
			return {}
		try:
			return json.loads(date.decode("utf-8"))
		except ValueError:
			raise EroareServer(E_SERVER, "raspuns")

	def _get(self, *cai):
		"""Prima ruta care exista (Jellyfin 10.9+ are rute noi; cele vechi raman la Emby)."""
		ultima = None
		for c in cai:
			try:
				return self._json("GET", c)
			except EroareServer as e:
				if e.cod != 404:
					raise
				ultima = e
		raise ultima

	def _q(self, **p):
		from urllib.parse import urlencode
		return urlencode(dict((k, v) for k, v in p.items() if v not in (None, "")))

	def _items(self, **p):
		u = self.s.get("uid", "")
		if self.fel == "jellyfin":
			return self._get("/Items?" + self._q(userId=u, **p), "/Users/%s/Items?%s" % (u, self._q(**p)))
		return self._get("/Users/%s/Items?%s" % (u, self._q(**p)))

	# -------------------------------------------------- forma comuna (V.Sursa)

	def idBun(self, x):
		return bool(_ID.match(x or ""))

	CAMPURI = "Overview,Genres,People,ProductionYear,DateCreated,CommunityRating,OfficialRating,RunTimeTicks,MediaSources,MediaStreams"

	def _poza(self, iid, fel="Primary", latime=342):
		if not iid:
			return ""
		cale = "/Items/%s/Images/%s%s" % (iid, fel, "/0" if fel == "Backdrop" else "")
		return "%s%s?maxWidth=%d&quality=85" % (self.adresa, cale, latime)

	def _titlu(self, it, tip):
		if not isinstance(it, dict) or not self.idBun(str(it.get("Id") or "")):
			return None
		fel = it.get("Type")
		iid = str(it["Id"])
		ud = it.get("UserData") if isinstance(it.get("UserData"), dict) else {}
		if fel == "Episode":
			# un episod in 'Continuă' se arata ca serialul lui, cu episodul ales
			sid = str(it.get("SeriesId") or "")
			if not self.idBun(sid):
				return None
			poz = _ticks(ud.get("PlaybackPositionTicks"))
			if poz:
				self._pozitii["e" + iid] = poz
			return {"id": sid, "cheie": "", "tip": V.SERIALE, "nume": V._text(it.get("SeriesName"), 200) or V._text(it.get("Name"), 200),
				"poza": self._poza(sid), "nota": "", "an": "", "adaugat": _data(it.get("DateCreated")), "episod": "e" + iid,
				"sub": "S%s E%s" % (it.get("ParentIndexNumber") or "?", it.get("IndexNumber") or "?")}
		t = {"id": iid, "cheie": "v" + iid if fel != "Series" else "", "nume": V._text(it.get("Name"), 200),
			"poza": self._poza(iid), "nota": V._nota(it.get("CommunityRating")), "an": str(it.get("ProductionYear") or ""),
			"adaugat": _data(it.get("DateCreated"))}
		poz = _ticks(ud.get("PlaybackPositionTicks"))
		if poz and fel != "Series":
			self._pozitii["v" + iid] = poz
			lung = _ticks(it.get("RunTimeTicks"))
			if lung:
				t["sub"] = V._tradus(N_("mai sunt %s")) % V.textDurata(max(0, lung - poz))
		return t if t["nume"] else None

	def _lista(self, d, tip):
		items = d.get("Items") if isinstance(d, dict) else d
		rez = []
		for it in items if isinstance(items, list) else []:
			t = self._titlu(it, tip)
			if t:
				rez.append(t)
				if len(rez) >= MAX_RAND:
					break
		return rez

	def _tipuri(self, tip):
		return "Movie" if tip == V.FILME else "Series"

	def categorii(self, tip):
		if not self.s.get("jeton") or not self.s.get("uid"):
			self.logare()
			_salveazaJeton(self.s)
		u = self.s["uid"]
		if self.fel == "jellyfin":
			d = self._get("/UserViews?" + self._q(userId=u), "/Users/%s/Views" % u)
		else:
			d = self._get("/Users/%s/Views" % u)
		dorite = ("movies", "homevideos", "mixed", "") if tip == V.FILME else ("tvshows", "mixed", "")
		rez = [("continua", V._tradus(T_CONTINUA))]
		for v in (d.get("Items") if isinstance(d, dict) else None) or []:
			if isinstance(v, dict) and self.idBun(str(v.get("Id") or "")) and (v.get("CollectionType") or "") in dorite:
				rez.append((str(v["Id"]), V._text(v.get("Name"), 80) or "?"))
		return rez

	def rand(self, tip, categorie):
		if categorie == "continua":
			if tip == V.FILME:
				d = self._items(Filters="IsResumable", IncludeItemTypes="Movie", Recursive="true", SortBy="DatePlayed",
					SortOrder="Descending", Limit=50, Fields=self.CAMPURI, EnableTotalRecordCount="false")
			else:
				d = self._get("/Shows/NextUp?" + self._q(UserId=self.s.get("uid", ""), Limit=50, Fields="DateCreated"))
			return self._lista(d, tip)
		d = self._items(ParentId=categorie, IncludeItemTypes=self._tipuri(tip), Recursive="true", SortBy="SortName",
			SortOrder="Ascending", Limit=MAX_RAND, Fields="ProductionYear,DateCreated,CommunityRating,RunTimeTicks",
			ImageTypeLimit=1, EnableTotalRecordCount="false")
		return self._lista(d, tip)

	def recente(self, tip):
		u = self.s.get("uid", "")
		p = self._q(IncludeItemTypes=self._tipuri(tip), Limit=V.MAX_RECENTE, Fields="ProductionYear,DateCreated,CommunityRating")
		if self.fel == "jellyfin":
			d = self._get("/Items/Latest?" + p + "&" + self._q(userId=u), "/Users/%s/Items/Latest?%s" % (u, p))
		else:
			d = self._get("/Users/%s/Items/Latest?%s" % (u, p))
		return self._lista(d, tip)

	def toate(self, tip):
		start = 0
		while start < 20000:
			d = self._items(IncludeItemTypes=self._tipuri(tip), Recursive="true", SortBy="SortName", StartIndex=start, Limit=500,
				Fields="ProductionYear,DateCreated,CommunityRating", EnableTotalRecordCount="false")
			lista = self._lista(d, tip)
			for t in lista:
				yield t
			if len(lista) < 500:
				return
			start += 500

	def cautaServer(self, tip, text):
		text = (text or "").strip()
		if not text:
			return []
		d = self._items(SearchTerm=text[:80], IncludeItemTypes=self._tipuri(tip), Recursive="true", Limit=V.MAX_CAUTARE,
			Fields="ProductionYear,DateCreated,CommunityRating")
		return self._lista(d, tip)

	def _item(self, iid):
		u = self.s.get("uid", "")
		p = self._q(Fields=self.CAMPURI)
		if self.fel == "jellyfin":
			return self._get("/Items/%s?%s&%s" % (iid, self._q(userId=u), p), "/Users/%s/Items/%s?%s" % (u, iid, p))
		return self._get("/Users/%s/Items/%s?%s" % (u, iid, p))

	def detalii(self, tip, titlu_id):
		it = self._item(titlu_id)
		if not isinstance(it, dict) or not it.get("Id"):
			raise V.C.EroareIptv(V.E_LIPSA)
		oameni = it.get("People") if isinstance(it.get("People"), list) else []
		regia = [V._text(p.get("Name"), 60) for p in oameni if isinstance(p, dict) and p.get("Type") == "Director"][:3]
		actori = [V._text(p.get("Name"), 60) for p in oameni if isinstance(p, dict) and p.get("Type") == "Actor"][:8]
		iid = str(it["Id"])
		rez = {"id": iid, "tip": tip, "nume": V._text(it.get("Name"), 200), "descriere": V._text(it.get("Overview"), 1500),
			"gen": ", ".join(V._text(g, 30) for g in (it.get("Genres") or [])[:4] if g), "tara": "", "regia": ", ".join(regia),
			"actori": ", ".join(actori), "nota": V._nota(it.get("CommunityRating")), "an": str(it.get("ProductionYear") or ""),
			"poster": self._poza(iid), "fundal": self._poza(iid, "Backdrop", 1280) if it.get("BackdropImageTags") else "",
			"trailer": "", "varsta": V._text(it.get("OfficialRating"), 10), "durata": _ticks(it.get("RunTimeTicks"))}
		if tip == V.FILME:
			rez["cheie"] = "v" + iid
			ud = it.get("UserData") if isinstance(it.get("UserData"), dict) else {}
			if _ticks(ud.get("PlaybackPositionTicks")):
				self._pozitii["v" + iid] = _ticks(ud.get("PlaybackPositionTicks"))
			rez.update(self._piste(it))
			self._subtitrari(iid, rez["nume"], it)
			return rez
		u = self.s.get("uid", "")
		d = self._get("/Shows/%s/Episodes?%s" % (iid, self._q(UserId=u, Fields="Overview,RunTimeTicks")))
		sezoane = {}
		for e in (d.get("Items") if isinstance(d, dict) else None) or []:
			if not isinstance(e, dict) or not self.idBun(str(e.get("Id") or "")):
				continue
			eid = str(e["Id"])
			ud = e.get("UserData") if isinstance(e.get("UserData"), dict) else {}
			if _ticks(ud.get("PlaybackPositionTicks")):
				self._pozitii["e" + eid] = _ticks(ud.get("PlaybackPositionTicks"))
			nr = e.get("ParentIndexNumber") if e.get("ParentIndexNumber") is not None else 0
			sezoane.setdefault(int(nr), []).append({"id": eid, "cheie": "e" + eid, "numar": str(e.get("IndexNumber") or ""),
				"nume": V._text(e.get("Name"), 200) or eid, "descriere": V._text(e.get("Overview"), 600),
				"durata": _ticks(e.get("RunTimeTicks")), "poza": self._poza(eid, "Primary", 400)})
		rez["sezoane"] = [{"numar": str(n), "episoade": sezoane[n][:V.MAX_EPISOADE]} for n in sorted(sezoane)][:V.MAX_SEZOANE]
		return rez

	def _piste(self, it):
		surse = it.get("MediaSources") if isinstance(it.get("MediaSources"), list) else []
		piste = (surse[0].get("MediaStreams") if surse and isinstance(surse[0], dict) else None) or it.get("MediaStreams") or []
		video, audio, sub = "", [], []
		for p in piste if isinstance(piste, list) else []:
			if not isinstance(p, dict):
				continue
			if p.get("Type") == "Video" and not video:
				h = p.get("Height") or 0
				parti = ["4K" if h >= 2000 else "1080p" if h >= 1000 else "720p" if h >= 700 else ("%dp" % h if h else "")]
				parti.append(V._text(p.get("Codec"), 10).upper())
				if p.get("VideoRange") == "HDR" or "HDR" in str(p.get("VideoRangeType") or ""):
					parti.append(V._text(p.get("VideoRangeType"), 12) or "HDR")
				video = " ".join(x for x in parti if x)
			elif p.get("Type") == "Audio":
				canale = {6: "5.1", 8: "7.1", 2: "2.0", 1: "1.0"}.get(p.get("Channels") or 0, "")
				t = " ".join(x for x in (_limba(p.get("Language")), canale, V._text(p.get("Codec"), 10).upper()) if x)
				if t and t not in audio:
					audio.append(t)
			elif p.get("Type") == "Subtitle":
				l = _limba(p.get("Language")) or V._text(p.get("DisplayTitle"), 20)
				if l and l not in sub:
					sub.append(l)
		return {"video": video, "audio": ", ".join(audio[:4]), "subtitrari_server": sub}

	# -------------------------------------------------- redarea

	def _cheieBuna(self, cheie):
		return bool(cheie) and cheie[0] in "ve" and self.idBun(cheie[1:])

	def referinta(self, cheie):
		if not self._cheieBuna(cheie):
			return None
		from Components import HdsIptvAdrese as A
		A.ALTE_SURSE[self.id] = self
		A.porneste()
		cale = "http://127.0.0.1:%d/media/%s/%s" % (I.PORT, self.id, cheie)
		self._legaSubtitrari(cheie, cale)
		sid, tsid, onid, ns = I.numereCanal(self.id, cheie)
		return "4097:0:1:%X:%X:%X:%X:0:0:0:%s:" % (sid, tsid, onid, ns, cale.replace(":", "%3a"))

	def adresaFlux(self, cheie):
		"""Releul (HdsIptvAdrese), pe firul lui: adresa fluxului, fara jeton (jetonul merge in antet). Direct cand placa decodeaza
		fisierul, altfel lista HLS a transcodarii serverului (releul rescrie listele si trece segmentele)."""
		if not self._cheieBuna(cheie):
			return None
		return self.redare(cheie)["adresa"]

	def anteteFlux(self, cheie):
		a = self.antete()
		a.pop("Accept", None)
		return a

	def _sesiune(self, cheie):
		with self._lacat:
			r = self._redari.get(cheie)
			if r is not None:
				return r["sesiune"]
			if cheie not in self._sesiuni:
				self._sesiuni[cheie] = uuid.uuid4().hex
			return self._sesiuni[cheie]

	# -------------------------------------------------- direct sau prin transcodarea serverului

	def redare(self, cheie):
		"""Hotararea redarii, o data pe redare (tinuta pana la oprire): {"metoda": DirectPlay/DirectStream/Transcode,
		"adresa", "sesiune": PlaySessionId, "sursa": MediaSourceId}. Pe firul releului; cererile la server nu tin lacatul pozitiei."""
		with self._lacatRedare:
			r = self._redari.get(cheie)
			if r is None:
				r = self._hotaraste(cheie)
				with self._lacat:
					self._redari[cheie] = r
			return r

	def _redareStiuta(self, cheie):
		"""Hotararea, daca releul a luat-o (asteapta una in lucru), fara s-o ia: pozitia nu porneste o transcodare."""
		with self._lacatRedare:
			return self._redari.get(cheie)

	def _static(self, iid, msid, sesiune):
		return "%s/Videos/%s/stream?%s" % (self.adresa, iid, self._q(static="true", MediaSourceId=msid, DeviceId=_dispozitiv(),
			PlaySessionId=sesiune))

	def _faraCheie(self, cale):
		"""TranscodingUrl al serverului (relativ, cu api_key) -> adresa pe serverul nostru, fara jeton (jetonul merge in antet).
		O adresa catre alt server nu se urmeaza: jetonul n-are ce cauta acolo."""
		from urllib.parse import urlsplit, parse_qsl, urlencode
		u = urlsplit(str(cale or "").strip())
		origine = "/".join(self.adresa.split("/")[:3])
		if u.scheme or u.netloc:
			if ("%s://%s" % (u.scheme, u.netloc)).lower() != origine.lower():
				return None
			baza = origine
		elif u.path.startswith("/"):
			baza = self.adresa
		else:
			return None
		q = [(k, v) for k, v in parse_qsl(u.query, keep_blank_values=True) if k.lower() not in ("api_key", "apikey")]
		a = baza + u.path + ("?" + urlencode(q) if q else "")
		return I.fluxBun(a)

	def _playbackInfo(self, iid, fam):
		u = self.s.get("uid", "")
		corp = {"DeviceProfile": profilDispozitiv(fam), "UserId": u, "MaxStreamingBitrate": DEBIT[fam], "IsPlayback": True,
			"AutoOpenLiveStream": False, "EnableDirectPlay": True, "EnableDirectStream": True, "EnableTranscoding": True,
			"AllowVideoStreamCopy": True, "AllowAudioStreamCopy": True, "DeviceId": _dispozitiv()}
		return self._json("POST", "/Items/%s/PlaybackInfo?%s" % (iid, self._q(UserId=u, MaxStreamingBitrate=DEBIT[fam],
			IsPlayback="true", AutoOpenLiveStream="false")), corp)

	def _master(self, iid, msid, sesiune, fam, img, sun):
		"""Adresa HLS a transcodarii facuta de noi (server fara PlaybackInfo): imaginea sau sunetul compatibile se copiaza."""
		lat, ina = MARGINI[fam]
		return "%s/Videos/%s/master.m3u8?%s" % (self.adresa, iid, self._q(MediaSourceId=msid, DeviceId=_dispozitiv(),
			PlaySessionId=sesiune, VideoCodec=VIDEO_TRANSCODARE, AudioCodec=AUDIO_TRANSCODARE, MaxStreamingBitrate=DEBIT[fam],
			VideoBitrate=DEBIT[fam] - DEBIT_SUNET, AudioBitrate=DEBIT_SUNET, TranscodingMaxAudioChannels=CANALE_TRANSCODARE,
			MaxWidth=lat, MaxHeight=ina, SegmentContainer="ts", MinSegments=1, BreakOnNonKeyFrames="True",
			AllowVideoStreamCopy="true" if img else "false", AllowAudioStreamCopy="true" if sun else "false"))

	def _hotaraste(self, cheie):
		iid = cheie[1:]
		fam = familie()
		try:
			d = self._playbackInfo(iid, fam)
		except EroareServer as e:
			print("[HdsVodServere] PlaybackInfo: %s" % (e.cod,))
			d = None
		if isinstance(d, dict) and isinstance(d.get("MediaSources"), list) and d["MediaSources"]:
			surse = [m for m in d["MediaSources"] if isinstance(m, dict)]
			ms = next((m for m in surse if str(m.get("Id") or "") == iid), surse[0] if surse else {})
			msid = str(ms.get("Id") or "")
			msid = msid if self.idBun(msid) else iid
			sesiune = V._text(d.get("PlaySessionId"), 64)
			sesiune = sesiune if _ID.match(sesiune) else uuid.uuid4().hex
			if ms.get("SupportsDirectPlay"):
				return {"metoda": "DirectPlay", "sursa": msid, "sesiune": sesiune, "adresa": self._static(iid, msid, sesiune)}
			# altfel lista HLS a serverului (el copiaza ce se poate: numai containerul sau numai sunetul schimbat); DirectStream
			# la Emby inseamna containerul schimbat de server, deci fisierul static numai cand nu exista transcodare
			a = self._faraCheie(ms.get("TranscodingUrl")) if ms.get("TranscodingUrl") else None
			if a:
				return {"metoda": "Transcode", "sursa": msid, "sesiune": sesiune, "adresa": a}
			if ms.get("SupportsDirectStream"):
				if not potrivire(ms, fam)[2] and ms.get("SupportsTranscoding", True):
					# container fara demultiplexor in imagine (MPG, VOB, WMV): pistele copiate intr-o lista HLS, fara transformare
					return {"metoda": "Transcode", "sursa": msid, "sesiune": sesiune, "adresa": self._master(iid, msid, sesiune, fam, True, True)}
				return {"metoda": "DirectStream", "sursa": msid, "sesiune": sesiune, "adresa": self._static(iid, msid, sesiune)}
		if isinstance(d, dict) and d.get("ErrorCode"):
			# serverul a refuzat (transcodarea oprita pentru acest utilizator, debit): o adresa facuta de noi ar fi refuzata la fel
			print("[HdsVodServere] PlaybackInfo refuzat: %s" % V._text(d.get("ErrorCode"), 40))
			s = uuid.uuid4().hex
			return {"metoda": "DirectPlay", "sursa": iid, "sesiune": s, "adresa": self._static(iid, iid, s), "refuz": True}
		# server fara PlaybackInfo (sau raspuns fara surse): aceeasi hotarare din pistele filmului
		s = uuid.uuid4().hex
		try:
			it = self._item(iid)
			surse = [m for m in (it.get("MediaSources") or []) if isinstance(m, dict)] if isinstance(it, dict) else []
		except EroareServer:
			surse = []
		if surse:
			ms = next((m for m in surse if str(m.get("Id") or "") == iid), surse[0])
			msid = str(ms.get("Id") or "")
			msid = msid if self.idBun(msid) else iid
			img, sun, cont = potrivire(ms, fam)
			if not (img and sun and cont):
				return {"metoda": "Transcode", "sursa": msid, "sesiune": s, "adresa": self._master(iid, msid, s, fam, img, sun)}
			return {"metoda": "DirectPlay", "sursa": msid, "sesiune": s, "adresa": self._static(iid, msid, s)}
		return {"metoda": "DirectPlay", "sursa": iid, "sesiune": s, "adresa": self._static(iid, iid, s)}

	def redareInchisa(self, cheie):
		"""Playerul s-a inchis inainte sa anunte inceputul (iesire in primele secunde): transcodarea se opreste pe server, fara
		Stopped (un Stopped cu pozitia 0 ar sterge de pe server locul de unde continua filmul)."""
		if not self._cheieBuna(cheie):
			return
		self._puneInCoada(cheie, None, "inchis")

	def _opresteTranscodarea(self, r):
		"""Serverul opreste ffmpeg-ul acestei redari (DeviceId + PlaySessionId), ca sa nu ramana incarcat dupa iesire."""
		self._json("DELETE", "/Videos/ActiveEncodings?" + self._q(DeviceId=_dispozitiv(), PlaySessionId=r.get("sesiune", "")))

	def pozitieServer(self, cheie):
		return self._pozitii.get(cheie)

	def progres(self, cheie, pozitie, durata, fel):
		"""Pozitia trimisa serverului, pe firul acestei surse (playerul nu asteapta reteaua)."""
		if not self._cheieBuna(cheie) or fel not in ("start", "progres", "oprit"):
			return
		if pozitie is not None:
			self._pozitii[cheie] = int(pozitie)
		self._puneInCoada(cheie, pozitie, fel)

	def _puneInCoada(self, cheie, pozitie, fel):
		with self._lacat:
			self._coada.append((cheie, int(pozitie or 0), fel))
			del self._coada[:-20]
			if self._fir is None:
				self._fir = threading.Thread(target=self._trimite, name="HdsVodServere")
				self._fir.daemon = True
				self._fir.start()

	def corpProgres(self, cheie, pozitie, fel, r=None):
		iid = cheie[1:]
		corp = {"ItemId": iid, "MediaSourceId": (r or {}).get("sursa") or iid, "PlaySessionId": self._sesiune(cheie),
			"PositionTicks": int(pozitie) * TICK, "CanSeek": True, "IsPaused": False, "IsMuted": False,
			"PlayMethod": (r or {}).get("metoda") or "DirectStream"}
		if fel == "progres":
			corp["EventName"] = "TimeUpdate"
		return corp

	CAI_PROGRES = {"start": "/Sessions/Playing", "progres": "/Sessions/Playing/Progress", "oprit": "/Sessions/Playing/Stopped"}

	def _trimite(self):
		while True:
			with self._lacat:
				if not self._coada:
					self._fir = None
					return
				cheie, pozitie, fel = self._coada.pop(0)
			r = self._redareStiuta(cheie)
			if fel in self.CAI_PROGRES:
				try:
					self._json("POST", self.CAI_PROGRES[fel], self.corpProgres(cheie, pozitie, fel, r))
				except Exception as e:
					print("[HdsVodServere] pozitia (%s): %s" % (fel, type(e).__name__))
			if fel in ("oprit", "inchis"):
				if r is not None and r.get("metoda") == "Transcode":
					try:
						self._opresteTranscodarea(r)
					except Exception as e:
						print("[HdsVodServere] oprirea transcodarii: %s" % type(e).__name__)
				with self._lacatRedare:
					with self._lacat:
						self._sesiuni.pop(cheie, None)
						if self._redari.get(cheie) is r:
							self._redari.pop(cheie, None)

	# -------------------------------------------------- subtitrarile serverului

	def _subtitrari(self, iid, nume, it):
		"""Pe firul de lucru (pagina filmului): subtitrarile externe ale serverului, in limbile preferate intai, in /tmp."""
		surse = it.get("MediaSources") if isinstance(it.get("MediaSources"), list) else []
		piste = (surse[0].get("MediaStreams") if surse and isinstance(surse[0], dict) else None) or []
		msid = str((surse[0] or {}).get("Id") or iid) if surse else iid
		externe = [p for p in piste if isinstance(p, dict) and p.get("Type") == "Subtitle" and p.get("IsExternal")
			and str(p.get("Codec") or "srt").lower() in ("srt", "subrip", "ass", "ssa", "vtt", "webvtt")]
		if not externe or not self.idBun(msid):
			return []
		pref = [x.upper() for x in _limbiPreferate()]
		externe.sort(key=lambda p: pref.index(_limba(p.get("Language"))[:3]) if _limba(p.get("Language"))[:3] in pref else 99)
		dosar = os.path.join(DOSAR_SUB, iid)
		baza = re.sub(r"[^\w .\-]", "", nume, flags=re.U).strip()[:80] or iid
		scrise = []
		for p in externe[:MAX_SUBTITRARI]:
			try:
				index = int(p.get("Index"))
			except (TypeError, ValueError):
				continue
			try:
				cod, date = self._cerere("GET", "%s/Videos/%s/%s/Subtitles/%d/Stream.srt" % (self.adresa, iid, msid, index),
					self.antete(), None)
			except EroareServer:
				continue
			if cod != 200 or not date or len(date) > 4 * 1024 * 1024:
				continue
			limba = (V._text(p.get("Language"), 8) or "und").lower()
			try:
				os.makedirs(dosar, exist_ok=True)
				cale = os.path.join(dosar, "%s.%s%s.srt" % (baza, limba, "" if index == 0 else ".%d" % index))
				with open(cale, "wb") as f:
					f.write(date)
				scrise.append(cale)
			except (IOError, OSError):
				pass
		with self._lacat:
			self._subt = getattr(self, "_subt", {})
			self._subt["v" + iid] = (os.path.join(dosar, baza + ".mkv"), scrise)
		return scrise

	def _legaSubtitrari(self, cheie, cale):
		v = getattr(self, "_subt", {}).get(cheie)
		if not v or not v[1]:
			return
		try:
			from Components import HdsSubtitrariFilm
			HdsSubtitrariFilm.inregistreazaRetea(cale, v[0])
		except ImportError:
			pass


def _limbiPreferate():
	"""Limbile subtitrarilor (preferintele receptorului, apoi limba meniului), coduri de 3 litere sau 2."""
	rez = []
	try:
		from Components.config import config
		for n in ("subtitle_autoselect1", "subtitle_autoselect2", "subtitle_autoselect3"):
			v = getattr(config.autolanguage, n, None)
			if v is not None and v.value and v.value != "---":
				rez.extend(x for x in str(v.value).split() if x)
		rez.append(config.osd.language.value.split("_")[0])
	except Exception:
		rez.append("ro")
	return rez


_obiecte = {}


def surse():
	"""Serverele tinute minte, ca surse (acelasi obiect cat timp datele nu se schimba: pozitiile si sesiunile raman)."""
	rez = []
	for s in citeste():
		o = _obiecte.get(s["id"])
		if o is None or o.s.get("adresa") != s.get("adresa") or o.s.get("parola") != s.get("parola"):
			o = _obiecte[s["id"]] = SursaServer(s)
		rez.append(o)
		try:
			from Components import HdsIptvAdrese as A
			A.ALTE_SURSE[o.id] = o
		except ImportError:
			pass
	return rez
