# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsReleuVideo.py (0.8.0, YTL0): adresele de pagini video puse in lista de canale (YouTube, Twitch, Dailymotion)
# pornesc direct. Un canal 4097/5001/5002 a carui adresa e pagina (https://www.youtube.com/watch?v=..., youtu.be/...,
# youtube.com/live/..., twitch.tv/<canal>, dailymotion.com/video/..., dai.ly/...) sau forma releului folosita de alte
# imagini (http://127.0.0.1:8088/<adresa paginii>, la fel pe :88, si YT-DLP://<adresa>) nu mai da ecran negru: inainte
# de redare, pe firul resolverelor de zap (Navigation._pluginuriChannelZap, fara serviciu pornit permanent), yt-dlp scoate
# adresa fluxului si playerul o primeste pe ea.
#
# yt-dlp nu e in imagine (e mare): pachetul python3-yt-dlp vine din feedul extern, cu yt-dlp-ejs si quickjs pentru
# YouTube. Cand lipseste, primul canal de felul acesta il instaleaza o data pe un fir al lui, iar zap-ul spune pe loc sa
# incerci peste un minut. yt-dlp ruleaza ca proces separat (python3 -m yt_dlp -j), nu in enigma2: memoria lui (~60 MB
# masurati pe SF8008) se elibereaza dupa, iar la un zap pe alt canal procesul se opreste pe loc. Daca adresa nu se poate
# scoate (pagina nu are flux, transmisiunea nu e pornita), pe ecran apare un mesaj scurt cu motivul, in loc de ecran negru.
#
# Formatul: un flux cu sunet si imagine pe care il poate reda receptorul (H.264 intai, apoi HLS, apoi 18 = 360p MP4); numai
# daca nu exista niciunul, imaginea H.264 fara sunet. YTDLPWrapper cere "b/bv*+ba/bv*", care la filmele YouTube fara format
# cu sunet si imagine da numai imaginea (AV1 2160p pe SF8008: playerul nu porneste).

import re
import subprocess
import threading
import time

try:
	from urllib.parse import unquote
except ImportError:  # pragma: no cover
	from urllib import unquote

FORMAT = "b[vcodec^=avc1]/b[protocol^=m3u8]/18/b/bv*[vcodec^=avc1][height<=1080]"
PYTHON = "python3"      # interpretorul procesului yt-dlp (probele de pe PC dau altul)
TERMEN_S = 180          # cat poate dura scoaterea adresei (provocarea JS a YouTube pe procesoarele receptoarelor)
PACHET_YTDLP = "python3-yt-dlp"

# adresele paginilor recunoscute (fara schema, dupa www./m.)
_SITURI = re.compile(
	r"^(?:www\.|m\.|music\.)?(?:"
	r"youtube\.com/(?:watch\?|live/|shorts/|embed/|channel/[^/]+/live|@[^/]+/live|c/[^/]+/live)"
	r"|youtu\.be/"
	r"|(?:www\.)?twitch\.tv/[A-Za-z0-9_]"
	r"|(?:www\.)?dailymotion\.com/(?:video|embed/video|live)/"
	r"|dai\.ly/"
	r")", re.I)
# releele locale ale altor imagini: http://127.0.0.1:8088/<adresa>, :88, localhost; si prefixul pluginului YTDLPWrapper
_RELEU = re.compile(r"^https?://(?:127\.0\.0\.1|localhost)(?::(?:8088|88))/+(?:\?url=)?", re.I)
_PREFIXE = ("yt-dlp://", "ytdlp://")

# instalarea lui yt-dlp: o singura data, pe un fir al ei (opkg poate dura minute); cat merge, zap-ul raspunde pe loc cu
# T_SE_INSTALEAZA; un esec se tine minte REINCERCARE_S, apoi se poate incerca iar (internetul a revenit, opkg s-a eliberat)
REINCERCARE_S = 60
_instalare = {"fir": None, "esuat_la": None}
_lacat = threading.Lock()


def N_(text):
	return text


T_LIPSA = N_("Canalul are nevoie de yt-dlp, care nu s-a putut instala din feed. Verifică internetul și încearcă din nou.")
T_SE_INSTALEAZA = N_("Pentru acest canal se instalează yt-dlp din feed, o singură dată. Încearcă din nou peste un minut.")
T_FARA_FLUX = N_("Pagina nu are un flux pe care să-l pot porni acum (transmisiunea poate fi oprită).")
T_EROARE = N_("Nu am putut porni linkul: %s")


def adresaPagina(cale):
	"""Adresa paginii video din calea unui serviciu (codata ca in lamedb/buchete: %3a pentru :), sau None. Recunoaste
	adresa directa a paginii, forma releului altor imagini (127.0.0.1:8088/<adresa>, :88) si prefixul YT-DLP://."""
	if not cale or not isinstance(cale, str):
		return None
	a = cale.strip()
	if "%3a" in a.lower():
		a = unquote(a)
	for _ in range(2):
		m = _RELEU.match(a)
		if m:
			a = unquote(a[m.end():])
		low = a.lower()
		for p in _PREFIXE:
			if low.startswith(p):
				a = a[len(p):]
				low = a.lower()
	if not re.match(r"^https?://", a, re.I):
		if _SITURI.match(a):
			a = "https://" + a
		else:
			return None
	rest = re.sub(r"^https?://", "", a, flags=re.I)
	return a if _SITURI.match(rest) else None


def esteLink(cale):
	return adresaPagina(cale) is not None


def _instaleaza(porneste):
	"""Pe firul instalarii: opkg install python3-yt-dlp (cu opkg update si a doua incercare daca prima cade)."""
	print("[HdsReleuVideo] yt-dlp lipseste: il instalez din feed (%s)" % PACHET_YTDLP)
	try:
		r = porneste(["opkg", "install", PACHET_YTDLP], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
		ok = r.returncode == 0
		if not ok:
			porneste(["opkg"] + _argumenteUpdate(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
			r = porneste(["opkg", "install", PACHET_YTDLP], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
			ok = r.returncode == 0
	except Exception as e:
		print("[HdsReleuVideo] instalarea yt-dlp: %s" % e)
		ok = False
	with _lacat:
		_instalare["fir"] = None
		_instalare["esuat_la"] = None if ok else time.time()
	print("[HdsReleuVideo] instalarea yt-dlp: %s" % ("gata" if ok else "nu a mers"))


def _areYtDlp():
	try:
		from importlib.util import find_spec
		import importlib
		importlib.invalidate_caches()
		return find_spec("yt_dlp") is not None
	except (ImportError, ValueError):
		return False


def _yt_dlp(instaleaza=True, porneste=subprocess.run, asteapta=False):
	"""(True, None) cand yt-dlp e instalat, altfel (None, textul pentru om). Daca lipseste, porneste o data instalarea pe
	firul ei si raspunde pe loc (T_SE_INSTALEAZA); asteapta=True asteapta firul (probele)."""
	if _areYtDlp():
		return True, None
	if not instaleaza:
		return None, T_LIPSA
	with _lacat:
		fir = _instalare["fir"]
		esuat = _instalare["esuat_la"]
		if fir is None:
			if esuat is not None and time.time() - esuat < REINCERCARE_S:
				return None, T_LIPSA
			fir = threading.Thread(target=_instaleaza, args=(porneste,), name="HdsReleuVideoOpkg", daemon=True)
			_instalare["fir"] = fir
			fir.start()
	if not asteapta:
		return None, T_SE_INSTALEAZA
	fir.join()
	return (True, None) if _areYtDlp() else (None, T_LIPSA)


def extrageProces(pagina, anulat=None, termen=TERMEN_S):
	"""Informatia yt-dlp (dict) dintr-un proces separat: python3 -m yt_dlp -j. anulat(): True opreste procesul (alt canal
	ales). Arunca RuntimeError cu ultima linie de eroare a lui yt-dlp."""
	import json
	p = subprocess.Popen([PYTHON, "-m", "yt_dlp", "-j", "--no-warnings", "--no-playlist", "--no-color", "-f", FORMAT,
		pagina], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	inceput = time.time()
	try:
		while True:
			try:
				iesire, erori = p.communicate(timeout=1)
				break
			except subprocess.TimeoutExpired:
				if (anulat is not None and anulat()) or time.time() - inceput > termen:
					p.kill()
					p.communicate()
					raise RuntimeError("oprit" if anulat is not None and anulat() else "timp depasit")
	finally:
		if p.poll() is None:
			p.kill()
	if p.returncode != 0:
		linii = [l for l in erori.decode("utf-8", "replace").splitlines() if l.strip()]
		raise RuntimeError(linii[-1] if linii else "cod %d" % p.returncode)
	linii = [l for l in iesire.decode("utf-8", "replace").splitlines() if l.startswith("{")]
	return json.loads(linii[-1]) if linii else None


def adresaFlux(pagina, extrage=None, anulat=None):
	"""(adresa fluxului, None) sau (None, textul pentru om). extrage(pagina) -> dict se poate da (probele de pe PC);
	altfel procesul yt-dlp (extrageProces)."""
	if extrage is None:
		gata, eroare = _yt_dlp()
		if not gata:
			return None, eroare
		extrage = lambda pg: extrageProces(pg, anulat)
	try:
		info = extrage(pagina)
	except Exception as e:
		text = str(e).replace("\n", " ").strip()
		text = re.sub(r"\x1b\[[0-9;]*m", "", text)
		return None, (T_EROARE, text[:200] or e.__class__.__name__)
	if not isinstance(info, dict):
		return None, T_FARA_FLUX
	if info.get("_type") == "playlist" and info.get("entries"):
		info = next((x for x in info["entries"] if isinstance(x, dict)), info)
	url = info.get("url")
	antete = info.get("http_headers") or {}
	if not url:
		cerute = info.get("requested_formats") or []
		if cerute and isinstance(cerute[0], dict):
			url = cerute[0].get("url")
			antete = cerute[0].get("http_headers") or antete
	if info.get("acodec") == "none" or not url:
		# fara flux cu sunet si imagine (filmele YouTube de azi): lista HLS principala a paginii, care are si sunetul
		# (playerul alege singur varianta); altfel ramane imaginea fara sunet
		for f in info.get("formats") or []:
			if isinstance(f, dict) and str(f.get("protocol", "")).startswith("m3u8") and f.get("manifest_url"):
				url = f["manifest_url"]
				antete = f.get("http_headers") or antete
				break
	if not url or not isinstance(url, str):
		return None, T_FARA_FLUX
	agent = antete.get("User-Agent") if isinstance(antete, dict) else None
	if agent and "#" not in url:
		# GStreamer (servicemp3) ia antetul User-Agent dupa # din adresa, ca la celelalte canale IPTV
		url = "%s#User-Agent=%s" % (url, agent)
	return url, None


def _mesaj(text):
	"""Mesajul pentru om pe receptor, de pe firul principal."""
	try:
		from twisted.internet import reactor

		def arata():
			try:
				from Tools import Notifications
				from Screens.MessageBox import MessageBox
				Notifications.AddPopup(text, MessageBox.TYPE_ERROR, 8, "HdsReleuVideo")
			except Exception as e:
				print("[HdsReleuVideo] mesaj: %s" % e)
		reactor.callFromThread(arata)
	except Exception as e:
		print("[HdsReleuVideo] mesaj: %s" % e)


def zap(session=None, service=None, **kwargs):
	"""Resolverul de zap al imaginii (aceeasi forma ca WHERE_CHANNEL_ZAP): (adresa fluxului, eroare) sau (None, None)
	cand serviciul nu e o pagina video. Ruleaza pe firul resolverelor."""
	try:
		cale = service.getPath() if service is not None else ""
	except Exception:
		return None, None
	pagina = adresaPagina(cale)
	if pagina is None:
		return None, None
	print("[HdsReleuVideo] pagina video in lista de canale: scot fluxul")

	def anulat():
		try:
			service.getPath()      # cererea anulata (alt canal ales intre timp) arunca aici
			return False
		except Exception:
			return True
	inceput = time.time()
	url, eroare = adresaFlux(pagina, anulat=anulat)
	print("[HdsReleuVideo] %s dupa %.1f s" % ("flux gasit" if url else "fara flux", time.time() - inceput))
	if url:
		return url, None
	try:
		_t = _          # traducerea enigma2 (builtins)
	except NameError:
		_t = lambda s: s
	if isinstance(eroare, tuple):
		text = _t(eroare[0]) % eroare[1]
	else:
		text = _t(eroare or T_FARA_FLUX)
	if anulat():
		return None, text      # alt canal ales intre timp: fara mesaj pentru canalul vechi
	_mesaj(text)
	return None, text


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
