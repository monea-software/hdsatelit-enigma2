# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsMozaic.py: mozaicul, adica toate canalele TV ale transponderului canalului de acum pe ecran deodata, pe 2, 4 sau 9
# celule, cu pagini (cererea lui Eduard din 01.11.2026 12:57 si precizarea din 14.11.2026 21:06: o tasta cand esti pe
# canal deschide mozaicul cu toate canalele de pe transponderul lui; de acolo treci pe 2, 4 sau 9, fiecare cu pagini).
#
# Cum se vad celulele (toate canalele unui transponder vin pe acelasi tuner, deci mozaicul nu ocupa alt tuner):
# - celula aleasa e VIE, cu sunet: decodorul 0 (canalul principal) cu fereastra video mutata pe celula;
# - a doua imagine vie, unde placa are a doua fereastra video (/proc/stb/vmpeg/1, PiP): pe 2 sta pe cealalta celula
#   (amandoua vii); pe 4 si 9 trece pe rand prin celelalte celule ale paginii, cate PE_CELULA_S, si lasa in urma o poza;
# - celelalte celule arata ultima poza a canalului (dosarul pozelor din Components/HdsUltimaImagine.py, aceeasi cheie,
#   deci pozele facute aici folosesc si la schimbarea canalului, si invers), cu numele canalului si emisiunea de acum;
# - pe placile cu o singura fereastra video, decodorul 0 face la deschidere o runda prin canalele paginii fara poza,
#   apoi revine pe celula aleasa (orice tasta opreste runda).
# Pozele: decodorul 0 cu grab -v; a doua fereastra din captura compusa (grab fara -v; pe HiSilicon "composed DISP
# snapshot" contine si fereastra PiP, masurat pe Octagon SF8008 14.11.2026; grab -i 1 acolo da tot decodorul 0),
# decupata cu PIL pe un fir. Fara PIL: fara poza, celula ramane cu numele si emisiunea. Decodarea pe procesor nu e o
# cale: FFmpeg-ul imaginii nu are decodoare video (recipes-local/ffmpeg).
#
# Partea de sus (pana la "efecte") nu importa nimic din enigma: o probeaza teste/test_moz_*.py pe PC.

import os

ASEZARI = {2: (2, 1), 4: (2, 2), 9: (3, 3)}   # celule pe pagina -> (coloane, randuri)
ALEGERI = (2, 4, 9)
IMPLICIT = 9
PE_CELULA_S = 5.0        # cat sta a doua imagine vie pe o celula inainte de poza (pe HiSilicon grab nu e sigur mai
                         # devreme de ~5 s dupa pornirea unui canal: STADIU-K2C, paza capturilor PAUZA_ZAP_S)
RUNDA_UNU_S = 5.0        # pe placile cu un decodor: cat sta decodorul 0 pe un canal in runda de la deschidere
LATIME_COMPUS = 960      # latimea capturii compuse din care se decupeaza celula
CALITATE = 70
MIN_OCTETI = 2500        # ca HdsUltimaImagine: o poza mai mica e ecran negru sau canal nedecriptat
TIPURI_TV = ("1", "11", "16", "19", "1F", "20", "86", "C3")   # tipurile din service_types_tv, hex ca in referinta
SERVICE_TYPES_TV = ("(type == 1) || (type == 17) || (type == 22) || (type == 25) || (type == 31) || (type == 32) || "
	"(type == 134) || (type == 195)")

# geometria la 1920x1080 (se scaleaza dupa ecranul interfetei)
BAZA_L, BAZA_H = 1920, 1080
SUS = 84          # titlul si pagina
JOS = 64          # bara tastelor
MARGINE = 48
SPATIU = 18
ETICHETA = 64     # sub imagine: numarul si numele, apoi emisiunea
CHENAR = 4


def asezareEfectiva(aleasa, n):
	"""-> 2, 4 sau 9: asezarea aleasa, dar cea mai mica in care incap toate canalele cand sunt mai putine
	(3 canale cu 9 aleasa -> 4); n = numarul canalelor."""
	try:
		aleasa = int(aleasa)
	except (TypeError, ValueError):
		aleasa = IMPLICIT
	if aleasa not in ALEGERI:
		aleasa = IMPLICIT
	nevoie = max(1, min(int(n or 0), aleasa))
	for a in ALEGERI:
		if a >= nevoie:
			return a
	return ALEGERI[-1]


def coloaneRanduri(pe_pagina):
	return ASEZARI.get(pe_pagina, ASEZARI[IMPLICIT])


def pagini(n, pe_pagina):
	return max(1, (int(n or 0) + pe_pagina - 1) // pe_pagina)


def paginaIndexului(i, pe_pagina):
	return max(0, int(i)) // pe_pagina


def celulelePaginii(pagina, pe_pagina, n):
	"""indicii canalelor de pe pagina (cel mult pe_pagina)"""
	inceput = pagina * pe_pagina
	return list(range(inceput, min(n, inceput + pe_pagina)))


def muta(i, directie, n, pe_pagina):
	"""Noua celula aleasa dupa o sageata. stanga/dreapta: canalul de dinainte/urmator, si peste pagina (de pe ultimul
	canal pe primul); sus/jos: randul de deasupra/dedesubt, cu trecere pe pagina vecina."""
	if n <= 0:
		return 0
	coloane = coloaneRanduri(pe_pagina)[0]
	i = min(max(0, int(i)), n - 1)
	if directie == "dreapta":
		return (i + 1) % n
	if directie == "stanga":
		return (i - 1) % n
	randuri = coloaneRanduri(pe_pagina)[1]
	if randuri == 1 and directie in ("sus", "jos"):
		# pe 1x2 nu sunt randuri: sus/jos = pagina vecina
		return paginaVecina(i, 1 if directie == "jos" else -1, n, pe_pagina)
	if directie == "jos":
		j = i + coloane
		if j < n:
			return j
		# sub ultimul rand: ultima celula daca e pe alta pagina sau pe acelasi rand mai in stanga, altfel sus pe prima pagina
		if paginaIndexului(n - 1, pe_pagina) != paginaIndexului(i, pe_pagina) or (n - 1) // coloane > i // coloane:
			return n - 1
		return i % coloane
	if directie == "sus":
		j = i - coloane
		return j if j >= 0 else n - 1
	return i


def paginaVecina(i, pas, n, pe_pagina):
	"""P+ (pas 1) / P- (pas -1): acelasi loc pe pagina urmatoare/anterioara (circular); pe o pagina mai scurta, ultima celula"""
	if n <= 0:
		return 0
	total = pagini(n, pe_pagina)
	p = (paginaIndexului(i, pe_pagina) + pas) % total
	return min(p * pe_pagina + (i % pe_pagina), n - 1)


def urmatoareaDeVizitat(celule, vii, ultima):
	"""Celula (indicele canalului) pe care merge a doua imagine vie dupa `ultima`: pe rand, prin celulele paginii care
	nu sunt deja vii; None cand nu e niciuna."""
	ramase = [c for c in celule if c not in vii]
	if not ramase:
		return None
	if ultima is None:
		return ramase[0]
	for c in ramase:
		if c > ultima:
			return c
	return ramase[0]


def _scala(v, f):
	return int(round(v * f))


def geometrie(latime, inaltime, pe_pagina):
	"""-> lista de pe_pagina celule, fiecare dict cu "video" (x, y, l, h; 16:9, centrata), "eticheta" (sub imagine) si
	"chenar" (imaginea si eticheta, cu marginea selectiei), in pixelii ecranului interfetei."""
	coloane, randuri = coloaneRanduri(pe_pagina)
	f = float(latime) / BAZA_L
	fy = float(inaltime) / BAZA_H
	sus, jos, margine, spatiu = _scala(SUS, fy), _scala(JOS, fy), _scala(MARGINE, f), _scala(SPATIU, f)
	eticheta, chenar = _scala(ETICHETA, fy), max(2, _scala(CHENAR, f))
	zona_l = latime - 2 * margine
	zona_h = inaltime - sus - jos
	cel_l = (zona_l - (coloane - 1) * spatiu) // coloane
	cel_h = (zona_h - (randuri - 1) * spatiu) // randuri
	vid_l = min(cel_l - 2 * chenar, int((cel_h - eticheta - 2 * chenar) * 16 / 9))
	vid_l -= vid_l % 2
	vid_h = int(vid_l * 9 / 16)
	vid_h -= vid_h % 2
	# grila centrata pe ecran
	tot_l = coloane * cel_l + (coloane - 1) * spatiu
	tot_h = randuri * cel_h + (randuri - 1) * spatiu
	x0 = (latime - tot_l) // 2
	y0 = sus + (zona_h - tot_h) // 2
	rez = []
	for k in range(pe_pagina):
		c, r = k % coloane, k // coloane
		cx = x0 + c * (cel_l + spatiu)
		cy = y0 + r * (cel_h + spatiu)
		bloc_h = vid_h + eticheta
		vx = cx + (cel_l - vid_l) // 2
		vy = cy + (cel_h - bloc_h) // 2
		rez.append({
			"video": (vx, vy, vid_l, vid_h),
			"eticheta": (vx, vy + vid_h, vid_l, eticheta),
			"chenar": (vx - chenar, vy - chenar, vid_l + 2 * chenar, bloc_h + 2 * chenar),
		})
	return rez


def dreptunghiDecupare(video, latime_ecran, latime_captura=LATIME_COMPUS):
	"""dreptunghiul celulei in captura compusa (latimea latime_captura): (stanga, sus, dreapta, jos) pentru PIL"""
	f = float(latime_captura) / max(1, latime_ecran)
	x, y, l, h = video
	return (int(x * f), int(y * f), int((x + l) * f), int((y + h) * f))


def interogareTransponder(namespace, tsid, onid):
	"""referinta listei cu canalele TV ale transponderului (aceeasi forma ca "Transponder curent" din ChannelSelection)"""
	return "1:7:1:0:0:0:0:0:0:0:(channelID == %08x%04x%04x) && %s ORDER BY name" % (
		namespace & 0xffffffff, tsid & 0xffff, onid & 0xffff, SERVICE_TYPES_TV)


def campuriTransponder(ref_text):
	"""(namespace, tsid, onid) din referinta unui canal DVB (campurile 7, 5, 6, hex), sau None (fisier, IPTV, gol)"""
	campuri = (ref_text or "").split(":")
	if len(campuri) < 10 or campuri[0] != "1":
		return None
	if len(campuri) > 10 and campuri[10].strip():
		return None   # fisier sau flux din retea
	try:
		ns, tsid, onid = int(campuri[6], 16), int(campuri[4], 16), int(campuri[5], 16)
	except ValueError:
		return None
	if ns == 0 and tsid == 0 and onid == 0:
		return None
	return ns, tsid, onid


def eTv(ref_text):
	campuri = (ref_text or "").split(":")
	return len(campuri) > 2 and campuri[2].upper() in TIPURI_TV


def curata(ref_text):
	"""referinta fara nume (primele 10 campuri + ':'), cum o asteapta playService si web-ul"""
	campuri = (ref_text or "").split(":")
	return ":".join(campuri[:10]) + ":" if len(campuri) >= 10 else ref_text


def metodaPozeiDoi(exista=os.path.exists):
	"""cum se ia poza celei de-a doua ferestre video: "compus" (HiSilicon: captura compusa a afisajului, cu fereastra PiP
	la locul ei, decupata; grab -i e ignorat acolo, masurat pe SF8008 si citit in sursa aio-grab: getvideo_hisi nu
	foloseste indicele) sau None (Broadcom si restul: captura completa pune numai decodorul 0 peste OSD; getvideo2 citeste
	/dev/dvb/adapter0/video1 cu -i 1 pe cipurile 7376/7444/7252S/7278, dar neprobat pe un Vu+, deci nefolosit). Fara
	metoda, pozele vin numai din decodorul 0 (runda de la deschidere)."""
	return "compus" if exista("/proc/msp") or exista("/proc/hisi") else None


def aDouaFereastra(numar_decodoare, exista=os.path.exists):
	"""True cand placa poate arata a doua imagine vie: un al doilea decodor si fereastra lui (/proc/stb/vmpeg/1).
	Pe SF8008 sunt 5 dispozitive video, dar numai 2 ferestre, deci niciodata setTarget(2+)."""
	return (numar_decodoare or 1) > 1 and exista("/proc/stb/vmpeg/1")


def fereastraDoiActiva(text):
	"""HiSilicon: True cand /proc/msp/win0101 spune ca a doua fereastra arata imagine ("Enable : True"). Pe Octagon SF8008
	(14.11.2026) ea a ramas "Enable: False" cu PiP pornit: atunci nu se face captura (ar iesi un dreptunghi negru)."""
	for rand in (text or "").splitlines():
		if rand.strip().startswith("Enable"):
			return rand.split("|")[0].split(":", 1)[-1].strip().lower() == "true"
	return False


# ---------------------------------------------------------------- setarea (fara UsageConfig: se face la cerere)

def initConfig():
	from Components.config import config, ConfigSelection, ConfigSubsection
	if not hasattr(config.usage, "hds_mozaic_asezare"):
		config.usage.hds_mozaic_asezare = ConfigSelection(default=str(IMPLICIT),
			choices=[(str(a), str(a)) for a in ALEGERI])
	return config.usage.hds_mozaic_asezare


def asezareAleasa():
	try:
		return int(initConfig().value)
	except Exception:
		return IMPLICIT


def tineMinteAsezarea(a):
	if a not in ALEGERI:
		return
	c = initConfig()
	c.value = str(a)
	c.save()
	try:
		from Components.config import configfile
		configfile.save()
	except Exception:
		pass


# ---------------------------------------------------------------- efecte (pe receptor)

def canaleTransponder(ref_text):
	"""[(referinta curata, nume)] ale canalelor TV de pe transponderul canalului ref_text, in ordinea numelui"""
	tp = campuriTransponder(ref_text)
	if tp is None:
		return []
	from enigma import eServiceCenter, eServiceReference
	lista = eServiceCenter.getInstance().list(eServiceReference(interogareTransponder(*tp)))
	if lista is None:
		return []
	rez, vazute = [], set()
	for ref, nume in (lista.getContent("SN", True) or []):
		r = curata(ref)
		if r in vazute or not eTv(r):
			continue
		vazute.add(r)
		rez.append((r, (nume or "").replace("\x86", "").replace("\x87", "")))
	return rez


def criptat(ref_text):
	"""True cand lamedb stie canalul criptat, sau cand nu se poate afla. A doua fereastra porneste NUMAI canale necriptate:
	pe Octagon (Sky, 14.11.2026), un al doilea canal criptat a luat decriptarea si imaginea cu sunet s-a facut neagra."""
	try:
		from enigma import eDVBDB, eServiceReference
		return bool(eDVBDB.getInstance().isCrypted(eServiceReference(ref_text)))
	except Exception:
		return True


def aDouaFereastraArata(cale="/proc/msp/win0101"):
	"""pe HiSilicon: a doua fereastra are imagine acum? (pe celelalte placi: True, nu se poate citi)"""
	if not os.path.exists(cale):
		return True
	try:
		with open(cale) as f:
			return fereastraDoiActiva(f.read(2048))
	except OSError:
		return True


def emisiuneaDeAcum(ref_text):
	try:
		from enigma import eEPGCache, eServiceReference
		ev = eEPGCache.getInstance().lookupEventTime(eServiceReference(ref_text), -1)
		return ev.getEventName() if ev else ""
	except Exception:
		return ""


def calePoza(ref_text):
	"""calea pozei canalului in dosarul comun cu HdsUltimaImagine, sau None"""
	from Components import HdsUltimaImagine as U
	k = U.cheie(ref_text)
	return U.calePoza(k) if k else None


def pozaExista(ref_text):
	cale = calePoza(ref_text)
	try:
		return bool(cale) and os.path.getsize(cale) >= MIN_OCTETI
	except OSError:
		return False


def _pastreaza(tmp, ref_text):
	"""muta poza temporara la locul canalului daca nu e aproape goala; curatenia dosarului ca HdsUltimaImagine"""
	from Components import HdsUltimaImagine as U
	cale = calePoza(ref_text)
	try:
		if cale and os.path.getsize(tmp) >= MIN_OCTETI:
			os.replace(tmp, cale)
			try:
				intrari = [(n, os.path.getsize(os.path.join(U.DOSAR, n)), os.path.getmtime(os.path.join(U.DOSAR, n)))
					for n in os.listdir(U.DOSAR) if n.endswith(".jpg") and not n.startswith(".")]
				for n in U.deSters(intrari):
					os.remove(os.path.join(U.DOSAR, n))
			except OSError:
				pass
			return True
	except OSError:
		pass
	try:
		os.remove(tmp)
	except OSError:
		pass
	return False


def pozaDecodor0(ref_text, timp_max=8):
	"""pe un fir: grab -v (decodorul 0, canalul cu sunet) -> poza canalului; True daca s-a pastrat"""
	import subprocess
	from Components import HdsUltimaImagine as U
	os.makedirs(U.DOSAR, exist_ok=True)
	tmp = os.path.join(U.DOSAR, ".moz0.jpg")
	try:
		subprocess.run(["grab", "-v", "-q", "-j", str(U.CALITATE), "-r", str(U.LATIME), tmp],
			stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timp_max)
	except Exception:
		return False
	return _pastreaza(tmp, ref_text)


def pozaFereastraDoi(ref_text, video, latime_ecran, metoda=None, timp_max=8):
	"""pe un fir: poza celei de-a doua ferestre video (dreptunghiul `video` in pixelii interfetei); True daca s-a pastrat"""
	import subprocess
	from Components import HdsUltimaImagine as U
	os.makedirs(U.DOSAR, exist_ok=True)
	tmp = os.path.join(U.DOSAR, ".moz1.jpg")
	metoda = metoda or metodaPozeiDoi()
	if metoda is None:
		return False
	try:
		if metoda == "dispozitiv":
			subprocess.run(["grab", "-v", "-i", "1", "-q", "-j", str(U.CALITATE), "-r", str(U.LATIME), tmp],
				stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timp_max)
		else:
			compus = os.path.join(U.DOSAR, ".moz-compus.jpg")
			subprocess.run(["grab", "-q", "-j", "90", "-r", str(LATIME_COMPUS), compus],
				stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timp_max)
			try:
				from PIL import Image
			except ImportError:
				return False
			try:
				with Image.open(compus) as im:
					im.crop(dreptunghiDecupare(video, latime_ecran)).convert("RGB").save(tmp, "JPEG", quality=CALITATE)
			finally:
				try:
					os.remove(compus)
				except OSError:
					pass
	except Exception:
		return False
	return _pastreaza(tmp, ref_text)
