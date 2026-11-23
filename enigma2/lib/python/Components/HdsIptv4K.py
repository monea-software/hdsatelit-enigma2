# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsIptv4K: ce trimit de fapt canalele de internet care au 4K, UHD, HDR (si altele de acelasi fel) in nume sau in grupa. Multe
# sunt 720p sau 1080p cu „4K” in nume. Din fiecare se citesc cateva secunde prin releul local, pe calea /proba/ (Components/
# HdsIptvAdrese.py: aceeasi conexiune unica a contului, fara sa atinga masuratorile canalului privit), cu
#   gst-launch-1.0 -v souphttpsrc location=<adresa locala> ! parsebin ! fakesink
# care da capurile parsate (latimea, inaltimea, cadrele, codecul, culoarea), fara decodor: merge si pentru HEVC Main 10, si nu
# arata nimic pe ecran.
#
# REGULI: un canal odata, cu pauza; niciodata cat omul se uita la un canal de internet (releul are un flux viu): cautarea se
# opreste singura si o ia de la capat data viitoare. Pornita din meniu (Screens/HdsIptv4K.py), din web (/iptv-4k) sau o data pe
# saptamana (HdsIptvLucru._zilnic, numai cu config.usage.hds_iptv_4k pe Da; Nu din fabrica, 14.11.2026). Setarea opreste numai
# cautarea din fundal: grupele si eticheta vin din rezultatele unei cautari pornite de om.
# REZULTATUL: hds_iptv/4k.json {"ora": cand s-a terminat ultima cautare intreaga, "canale": {"<sursa>/<cheie>": [latime, inaltime,
# codec, hdr, ora, ref, nume]}}. Din el: grupele „4K adevărat” si „HDR” din radacina IPTV (HdsIptvSurse.scrieBuchete, grupe()) si
# eticheta din lista de canale (eticheta(): „4K HDR10”, „de fapt 1080p”).
# PERECHILE (receptoarele Full HD, Components/HdsIptvFullHd.py): acelasi canal fara 4K in nume, din aceeasi grupa, se citeste si el, ca
# releul sa-l aduca in locul canalului 4K numai cand chiar trimite sub 4K (pe .129 |AR| WARNER BROS 1 trimitea tot 3840x2160). Rezultatele
# lor stau separat, in 4k.json la "perechi" (perechi()): nu intra in grupe, etichete si listele cautarii.
#
# Partea de sus nu importa nimic din enigma2: probele de pe PC o folosesc ca atare.

import glob
import json
import os
import re
import subprocess
import threading
import time

from Components import HdsIptvSurse as I
from Components import HdsIptvClient as C

CANDIDAT = re.compile(r"4K|UHD|2160|3840|HDR|8K|DOLBY ?VISION|\bDV\b", re.I)
ZILE_VALABIL = 7
SECUNDE_PROBA = 10
PAUZA_S = 2
LINISTE_S = 5            # releul a trimis ceva omului in ultimele atatea secunde: omul se uita, nu se verifica nimic
SCRIE_LA = 10            # rezultatele se scriu pe disc la atatea canale verificate (si la sfarsit)
PRIMELE_ESUATE = 10      # atatea canale la rand fara niciun raspuns la inceput: cautarea se opreste si se reia data viitoare
# dupa o cautare in care nimic n-a raspuns (cont expirat, server sau internet cazut), cea saptamanala se reia abia dupa atat (prima,
# a doua, apoi mereu a treia pauza), nu la fiecare pas al ceasului zilnic (60 s); pornita de om din meniu sau din web: oricand
PAUZE_DUPA_ESEC_S = (15 * 60, 3600, 3 * 3600)
LATIME_4K = 3200         # 3840x1600 (film lat) e tot 4K
GRUPA_4K = "4K adevărat"
GRUPA_HDR = "HDR"
FISIER_4K = I.PREFIX_GRUPA + "4k_adevarat.tv"
FISIER_HDR = I.PREFIX_GRUPA + "4k_hdr.tv"

_lacat = threading.Lock()
_fir = None
_opreste = False
_stare = {"lucreaza": False, "facute": 0, "total": 0, "gasite": 0, "hdr": 0, "mesaj": "", "inceput": 0}
_cache = (None, ({}, {}))
_esecuri = [0, 0.0]      # cautari la rand in care nimic n-a raspuns, si cand s-a terminat ultima (time.monotonic)


def _caleRezultate():
	return I._cale("4k.json")


# ------------------------------------------------------------------ ce se citeste din flux

_W = re.compile(r"width=\(int\)(\d+)")
_H = re.compile(r"height=\(int\)(\d+)")
_FR = re.compile(r"framerate=\(fraction\)(\d+)/(\d+)")
_COL = re.compile(r"colorimetry=\(string\)([a-z0-9:-]+)")
_VIDEO = re.compile(r"(video/x-h265|video/x-h264|video/mpeg|video/x-av1|video/x-vp9)[^\"\n]*width=\(int\)\d+[^\"\n]*")


def capuri(text):
	"""Din iesirea lui gst-launch -v: {"w", "h", "cod", "fps", "hdr"} sau None fara video."""
	m = _VIDEO.search(text or "")
	if not m:
		return None
	v = m.group(0)
	w, h = _W.search(v), _H.search(v)
	if not w or not h:
		return None
	cod = {"video/x-h265": "HEVC", "video/x-h264": "H.264", "video/mpeg": "MPEG", "video/x-av1": "AV1", "video/x-vp9": "VP9"}[m.group(1)]
	fr = _FR.search(v)
	fps = round(int(fr.group(1)) / float(fr.group(2)), 2) if fr and int(fr.group(2)) else 0
	col = (_COL.search(v).group(1) if _COL.search(v) else "").lower()
	hdr = ""
	if "dolby" in v.lower() or "dvhe" in v.lower():
		hdr = "Dolby Vision"
	elif "pq" in col or "smpte2084" in col:
		hdr = "HDR10"
	elif "hlg" in col or "arib-std-b67" in col:
		hdr = "HLG"
	return {"w": int(w.group(1)), "h": int(h.group(1)), "cod": cod, "fps": fps, "hdr": hdr}


def eticheta4k(r):
	"""Textul scurt pentru un rezultat [latime, inaltime, codec, hdr, ...]: „4K HDR10”, „4K”, „de fapt 1080p”, „”."""
	if not r or not r[0]:
		return ""
	w, h, hdr = r[0], r[1], r[3]
	if w >= LATIME_4K:
		return ("4K " + hdr) if hdr else "4K"
	inaltime = 1080 if h >= 1000 or w >= 1900 else 720 if h >= 700 or w >= 1200 else 576 if h >= 500 else h
	return (_t("de fapt %dp") % inaltime) + ((" " + hdr) if hdr else "")


def _t(text):
	try:
		return _(text)  # noqa: F821  (gettext pus de enigma2 in builtins)
	except NameError:
		return text


def N_(text):
	return text


N_("de fapt %dp")
N_("4K adevărat")  # GRUPA_4K, tradus in _tradus (marcat aici: GRUPA_4K e scrisa inaintea lui N_)


# ------------------------------------------------------------------ candidatii si rezultatele

def candidati(dosar=None):
	"""[(sid, cheie, ref, nume)] ale canalelor de internet cu 4K/UHD/HDR... in nume sau in grupa, fiecare o data, in ordinea listei."""
	rez, vazute = [], set()
	for f in sorted(glob.glob(os.path.join(dosar or I.DIRECTOR, I.PREFIX_GRUPA + "*.tv"))):
		if f.endswith((FISIER_4K, FISIER_HDR)):
			continue
		grupa, ref = "", None
		try:
			with open(f, encoding="utf-8", errors="replace") as fis:
				for r in fis:
					r = r.rstrip("\r\n")
					if r.startswith("#NAME "):
						grupa = r[6:]
					elif r.startswith("#SERVICE "):
						ref = r[9:]
					elif r.startswith("#DESCRIPTION ") and ref:
						nume = r[13:]
						sid, cheie = I.desparteCale(ref)
						if sid is not None and (CANDIDAT.search(nume) or CANDIDAT.search(grupa)) and (sid, cheie) not in vazute:
							vazute.add((sid, cheie))
							rez.append((sid, cheie, ref, nume))
						ref = None
		except (IOError, OSError):
			continue
	return rez


def candidatiPerechi(dosar=None):
	"""Pe receptoarele Full HD: [(sid, cheie, ref, nume)] ale canalelor fara 4K in nume care pot fi perechea unui canal cu 4K in nume din
	aceeasi grupa (Components/HdsIptvFullHd.perechiDeMasurat), fiecare o data. Pe celelalte receptoare: []."""
	try:
		from Components import HdsIptvFullHd as F
		if not F.placaFullHd():
			return []
	except Exception:
		return []
	rez, vazute = [], set()
	for f in sorted(glob.glob(os.path.join(dosar or I.DIRECTOR, I.PREFIX_GRUPA + "*.tv"))):
		if f.endswith((FISIER_4K, FISIER_HDR)):
			continue
		grupa, ref, intrari = "", None, []
		try:
			with open(f, encoding="utf-8", errors="replace") as fis:
				for r in fis:
					r = r.rstrip("\r\n")
					if r.startswith("#NAME "):
						grupa = r[6:]
					elif r.startswith("#SERVICE "):
						ref = r[9:]
					elif r.startswith("#DESCRIPTION ") and ref:
						sid, cheie = I.desparteCale(ref)
						if sid is not None:
							intrari.append(((sid, cheie), r[13:], grupa, ref))
						ref = None
		except (IOError, OSError):
			continue
		for x in F.perechiDeMasurat(intrari):
			if x[0] not in vazute:
				vazute.add(x[0])
				rez.append((x[0][0], x[0][1], x[3], x[1]))
	return rez


def _citesteDoc():
	"""(canale, perechi) din 4k.json, tinute minte dupa fisier."""
	global _cache
	try:
		st = os.stat(_caleRezultate())
		semn = (st.st_mtime, st.st_size)
	except OSError:
		return {}, {}
	if _cache[0] == semn:
		return _cache[1]
	try:
		with open(_caleRezultate(), encoding="utf-8") as f:
			d = json.load(f)
		d = d if isinstance(d, dict) else {}
	except (IOError, OSError, ValueError):
		d = {}
	canale, pp = d.get("canale"), d.get("perechi")
	rez = (canale if isinstance(canale, dict) else {}, pp if isinstance(pp, dict) else {})
	_cache = (semn, rez)
	return rez


def rezultate():
	"""{"<sursa>/<cheie>": [latime, inaltime, codec, hdr, ora, ref, nume]} (citit din nou cand se schimba fisierul)."""
	return _citesteDoc()[0]


def perechi():
	"""Ca rezultate(), pentru perechile citite pe receptoarele Full HD (vezi capul fisierului)."""
	return _citesteDoc()[1]


def _oraUltima():
	try:
		with open(_caleRezultate(), encoding="utf-8") as f:
			return int(json.load(f).get("ora") or 0)
	except (IOError, OSError, ValueError, AttributeError, TypeError):
		return 0


def _scrieRezultate(canale, ora=None, pp=None):
	global _cache
	d = {"ora": ora if ora is not None else _oraUltima(), "canale": canale, "perechi": pp if pp is not None else perechi()}
	with I._LACAT:
		I._asiguraDosar()
		I._scrie(_caleRezultate(), json.dumps(d, separators=(",", ":"), ensure_ascii=False).encode("utf-8"), 0o600)
	_cache = (None, ({}, {}))


def eticheta(cale):
	"""Eticheta din lista de canale a unui canal verificat, sau ""."""
	sid, cheie = I.desparteCale(cale)
	return eticheta4k(rezultate().get("%s/%s" % (sid, cheie))) if sid is not None else ""


def _tradus(text):
	"""Numele grupei in limba receptorului (in buchet se scrie asa; la schimbarea limbii, la urmatoarea refacere a
	listei IPTV). Fara catalog (probele de pe PC), textul insusi."""
	try:
		return _(text)
	except NameError:
		return text


def grupe():
	"""[(fisier, nume, [(ref, nume canal)])] pentru radacina IPTV: „4K adevărat” si „HDR”, numai cand au canale (dupa o cautare,
	pornita de om sau cea saptamanala; setarea hds_iptv_4k opreste numai cautarea din fundal)."""
	r4k, rhdr = [], []
	for k, v in sorted(rezultate().items(), key=lambda kv: (kv[1][6] if len(kv[1]) > 6 else "")):
		if len(v) < 7 or not v[5]:
			continue
		if v[0] >= LATIME_4K:
			r4k.append((v[5], v[6]))
		if v[3]:
			rhdr.append((v[5], v[6]))
	rez = []
	if r4k:
		rez.append((FISIER_4K, _tradus(GRUPA_4K), r4k))
	if rhdr:
		rez.append((FISIER_HDR, GRUPA_HDR, rhdr))
	return rez


# ------------------------------------------------------------------ verificarea

def omulSeUita():
	"""Omul se uita (sau tocmai porneste) un canal de internet: nu se verifica nimic. Adevarat cand o cerere a lui e deschisa in releu
	(si cat se conecteaza, inainte de primul octet: primul cadru poate veni si dupa 15 s) sau cand releul i-a trimis ceva de curand
	(la HLS segmentele vin cu cereri separate, la cateva secunde)."""
	try:
		from Components import HdsIptvAdrese as A
	except Exception:
		return False
	if getattr(A, "_deschise_omului", 0) > 0:
		return True
	m = A._masura
	return m is not None and time.monotonic() - m.ultim < (A.PAUZA_HLS_S if m.hls else LINISTE_S)


def adresaProba(sid, cheie):
	return "http://127.0.0.1:%d/proba/%s/%s" % (I.PORT, sid, cheie)


def citesteCanal(sid, cheie, secunde=SECUNDE_PROBA):
	"""Capurile unui canal (capuri()) sau None. gst-launch se opreste cum apar capurile video (de obicei in 2-4 s), cel mult
	dupa `secunde`: cu ~2.000 de candidati intr-un abonament mare, cautarea tine ore, nu zile."""
	import selectors
	cmd = ["gst-launch-1.0", "-v", "souphttpsrc", "location=" + adresaProba(sid, cheie), "!", "parsebin", "!", "fakesink"]
	try:
		p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
	except OSError:
		return None
	text, rez = b"", None
	limita = time.monotonic() + secunde
	sel = selectors.DefaultSelector()
	sel.register(p.stdout, selectors.EVENT_READ)
	try:
		while rez is None:
			ramas = limita - time.monotonic()
			if ramas <= 0 or not sel.select(ramas):
				break
			b = os.read(p.stdout.fileno(), 65536)
			if not b:
				break
			text = (text + b)[-262144:]
			if b"width=(int)" in b or b"width=(int)" in text[-70000:]:
				rez = capuri(text.decode("utf-8", "replace"))
	finally:
		sel.close()
		if p.poll() is None:
			p.kill()
		try:
			p.communicate(timeout=5)
		except Exception:
			pass
	return rez if rez is not None else capuri(text.decode("utf-8", "replace"))


def stare():
	with _lacat:
		return dict(_stare)


def deContinuat(acum=None):
	"""True cand o cautare n-a ajuns la capat: exista candidati necititi in ultimele ZILE_VALABIL zile, dar si unii cititi (oprita de
	om, de o pauza, de o repornire). Pornirea de mana o continua de acolo (porneste(tot=False)); altfel (nimic citit inca, sau tot
	citit de curand) o ia pe toate de la capat."""
	lista = candidati()
	if not lista:
		return False
	vechi = rezultate()
	acum = int(acum or time.time())
	citite = sum(1 for c in lista if 0 <= acum - int((vechi.get("%s/%s" % (c[0], c[1])) or [0, 0, 0, 0, 0])[4]) < ZILE_VALABIL * 86400)
	return 0 < citite < len(lista)


def porneste(tot=False, citeste=None, asteapta=time.sleep):
	"""Porneste cautarea pe un fir (o singura data). tot=True: si canalele verificate de curand. -> False daca deja merge sau e oprita."""
	global _fir, _opreste
	with _lacat:
		if _fir is not None:
			return False
		_opreste = False
		_stare.update({"lucreaza": True, "facute": 0, "total": 0, "gasite": 0, "hdr": 0, "mesaj": "", "inceput": int(time.time())})
		_fir = threading.Thread(target=_bucla, args=(tot, citeste or citesteCanal, asteapta), name="HdsIptv4K")
		_fir.daemon = True
		_fir.start()
	return True


def opreste():
	global _opreste
	_opreste = True


def deRulat(acum=None, ceas=time.monotonic):
	"""Cautarea saptamanala e datorata (functia pornita, surse, nicio cautare intreaga de ZILE_VALABIL zile, nu in pauza de dupa o
	cautare fara niciun raspuns)."""
	if not I.optiune("4k") or not I.areSurse():
		return False
	if _esecuri[0] and ceas() - _esecuri[1] < PAUZE_DUPA_ESEC_S[min(_esecuri[0], len(PAUZE_DUPA_ESEC_S)) - 1]:
		return False
	acum = acum or time.time()
	return not 0 <= acum - _oraUltima() < ZILE_VALABIL * 86400


T_OPRITA_PRIVIRE = N_("Oprită: te uiți la un canal de internet. Continuă data viitoare.")
T_GATA = N_("Gata.")
T_NU_RASPUNDE = C.E_NU_RASPUNDE      # acelasi text ca la redare, deja tradus


def _bucla(tot, citeste, asteapta):
	global _fir
	try:
		lista = candidati()
		# pe receptoarele Full HD si perechile fara 4K ale canalelor 4K, dupa ele; rezultatele lor separat (vezi capul fisierului)
		in_lista = set((c[0], c[1]) for c in lista)
		perechi_lista = [c for c in candidatiPerechi() if (c[0], c[1]) not in in_lista]
		de_pereche = set((c[0], c[1]) for c in perechi_lista)
		vechi = dict(rezultate())
		vechi_p = dict(perechi())

		def _vechi(c):
			return (vechi_p if (c[0], c[1]) in de_pereche else vechi).get("%s/%s" % (c[0], c[1]))
		acum = int(time.time())
		de_facut = [c for c in lista + perechi_lista if tot or acum - int((_vechi(c) or [0, 0, 0, 0, 0])[4]) >= ZILE_VALABIL * 86400]
		# cele care n-au dat nimic data trecuta, la coada: un sir de canale moarte nu opreste cautarea la PRIMELE_ESUATE
		de_facut.sort(key=lambda c: 1 if int((_vechi(c) or [1, 0, 0, 0, 1])[0]) == 0 else 0)
		with _lacat:
			_stare["total"] = len(de_facut)
		canale = dict((k, v) for k, v in vechi.items() if k.split("/")[0] in set(c[0] for c in lista))
		pp = dict((k, v) for k, v in vechi_p.items() if k.split("/")[0] in set(c[0] for c in lista + perechi_lista))
		intreaga = True
		intrerupta = False       # oprita de om sau pentru ca omul se uita: nu e o cautare fara raspuns
		reusite = 0
		for i, (sid, cheie, ref, nume) in enumerate(de_facut):
			if _opreste:
				intreaga, intrerupta = False, True
				break
			if omulSeUita():
				intreaga, intrerupta = False, True
				with _lacat:
					_stare["mesaj"] = T_OPRITA_PRIVIRE
				break
			c = citeste(sid, cheie)
			k = "%s/%s" % (sid, cheie)
			if omulSeUita():
				# omul a pornit un canal in timpul probei: proba s-a rupt, nu e un rezultat
				intreaga, intrerupta = False, True
				with _lacat:
					_stare["mesaj"] = T_OPRITA_PRIVIRE
				break
			# un canal care n-a dat nimic (mort, server cazut, internet cazut) ramane „nestiut”, cu ora 0: se incearca din nou data
			# viitoare, nu se socoteste verificat pe o saptamana
			tinta = pp if (sid, cheie) in de_pereche else canale
			if c:
				tinta[k] = [c["w"], c["h"], c["cod"], c["hdr"], int(time.time()), ref, nume]
			elif len(tinta.get(k) or ()) > 3 and tinta[k][0]:
				# a raspuns alta data: ramane ce s-a citit atunci (o proba cazuta nu-l scoate din „4K adevărat”), de reluat
				tinta[k] = list(tinta[k][:4]) + [0, ref, nume]
			else:
				tinta[k] = [0, 0, "", "", 0, ref, nume]
			if c:
				reusite += 1
			with _lacat:
				_stare["facute"] = i + 1
				_stare["gasite"] = sum(1 for v in canale.values() if v[0] >= LATIME_4K)
				_stare["hdr"] = sum(1 for v in canale.values() if v[3])
			if (i + 1) % SCRIE_LA == 0:
				_scrieRezultate(canale, pp=pp)
			if not reusite and i + 1 >= PRIMELE_ESUATE:
				# primele toate fara raspuns (cont expirat, server sau internet cazut): nu se ia lista la rand degeaba
				with _lacat:
					_stare["mesaj"] = T_NU_RASPUNDE
				break
			asteapta(PAUZA_S)
		if de_facut and not reusite and not intrerupta:
			intreaga = False      # nimic citit (internetul sau serverul cazut): cautarea saptamanala se reia, nu asteapta 7 zile
			_esecuri[0], _esecuri[1] = _esecuri[0] + 1, time.monotonic()    # dar dupa o pauza (deRulat)
		elif reusite:
			_esecuri[0] = 0
		_scrieRezultate(canale, int(time.time()) if intreaga else None, pp)
		with _lacat:
			if intreaga:
				_stare["mesaj"] = T_GATA
		try:
			from Components import HdsIptvLucru as L
			L.cere(L._REFACERE, True)   # grupele „4K adevărat” si „HDR” in radacina IPTV
		except Exception as e:
			print("[HdsIptv4K] buchetele: %s" % type(e).__name__)
	except Exception as e:
		print("[HdsIptv4K] cautarea: %s" % type(e).__name__)
	finally:
		with _lacat:
			_stare["lucreaza"] = False
			_fir = None
