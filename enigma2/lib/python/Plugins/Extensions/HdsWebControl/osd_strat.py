# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# osd_strat.py: stratul grafic al receptorului (meniurile, bara de informatii, subtitrarea, ghidul, tot ce deseneaza
# enigma2 pe ecran) pentru browser, ca strat separat, cu transparenta, peste imaginea live (GET /api/tv-osd, tv_web.py).
#
# DE UNDE: /dev/fb0 (hifb), numai citire. Marimea din /sys/class/graphics/fb0 (mode, stride, bits_per_pixel) si pagina
# afisata din pan (enigma2 poate avea doua pagini, gFBDC::flip). Pixelii: 32 de biti, octetii B, G, R, A; alfa 0 unde
# se vede imaginea canalului. Python-ul imaginii nu are mmap, deci citirea e cu os.pread, rand cu rand.
#
# CAT COSTA (masurat pe Amiko Viper 4K V20, cu meniul principal deschis, timp de procesor):
#   citirea paginii intregi (8 MB) 57-81 ms; crc32 pe 8 MB 32 ms; un rand din 8 (135 de randuri) + crc32 11 ms;
#   deflate BGRA 960x540 29 ms (44 KB), 1920x1080 110 ms (134 KB); schimbarea culorilor BGRA->RGBA pentru PNG ar mai
#   costa 39 ms la 960x540 si 154 ms la 1920x1080, de aceea browserul primeste BGRA brut (comprimat gzip) si il
#   deseneaza el pe un canvas. `grab -o -p` (unealta de captura) costa 1,1 s pe cadru, `-r 960` 0,45 s.
#   Din nou pe 0.3.40 (codarea intreaga, mediana din 5): 960x540 129 ms (citire 36, crc 19, un pixel din
#   doi + deflate 76; 43 KB), 1920x1080 248 ms (citire 64, crc 35, deflate 143; 132 KB). zlib Z_RLE si Z_HUFFMAN_ONLY
#   sunt mai lente si mai mari; citirea dintr-o bucata castiga numai ~7 ms.
#
# MARIMEA: pagina cere stratul la latimea pe care il arata (latimea casetei x devicePixelRatio). Peste jumatate din
# latimea framebufferului se trimite toata latimea (pas 1, 1920x1080 pe receptorul de proba), iar browserul il micsoreaza el, cu
# netezire: textul ramane clar ca pe televizor. Pasul 2 (un pixel din doi) numai pentru ecranele mici (cel mult 960 de
# pixeli pe receptorul de proba), unde 1920 nu s-ar vedea. Mai multi clienti: cea mai mare latime ceruta in ultimele PAS_MARE_S
# secunde, pentru toti (un singur cadru verificat si codat, deci procesorul nu se dubleaza). Cu bugetul de mai jos,
# o animatie (lista derulata cu o tasta la 0,4 s, masurat 12 s) ia ~21-22% dintr-un nucleu si la 960 si la 1920; la
# 1920 vin ~0,7 cadre noi pe secunda fata de ~1,0 la 960. Cu lista deschisa si nemiscata, verificarile iau 5% (960)
# si 8% (1920) dintr-un nucleu.
#
# SEMNUL "S-A SCHIMBAT": randurile trimise (toate la pas 1; unul din doi la pas 2) se impart in FAZE grupe (randul i
# intra in faza i % FAZE). O verificare citeste o singura faza (un rand din 8 al celor trimise) si ii compara crc32 cu
# cel de la ultima codare; fazele se rotesc. Orice schimbare mai inalta de FAZE randuri se vede la prima verificare,
# una mai mica in cel mult FAZE verificari. Abia la o schimbare se citesc toate randurile si se codeaza cadrul.
#
# PROCESORUL: o verificare cel mult o data la INTERVAL_MIN_S, oricati clienti ar cere. Dupa o codare de E secunde,
# urmatoarea verificare vine dupa cel putin FACTOR_BUGET * E: cand ceva se misca fara oprire (o animatie), codarea ia
# cel mult 1 / (1 + FACTOR_BUGET) dintr-un nucleu. Munca ruleaza pe un fir separat (tv_web), nu pe firul enigma2; os.pread,
# zlib.crc32 si compresia elibereaza GIL-ul.
#
# FEREASTRA IMAGINII: unele ecrane micsoreaza imaginea canalului intr-o fereastra (listele de canale ale skinului, cu
# render="Pig"; HbbTV). lib/gui/evideo.cpp o scrie in /proc/stb/vmpeg/0/dst_left|top|width|height (hex, in coordonate
# 720x576; 0 0 0 0 = ecran intreg). Raspunsul stratului o duce paginii (antetul x-hds-video, procente din ecran), iar
# player.js pune imaginea din browser in acelasi loc, sub strat. Citirea costa 0,18 ms (4 noduri cu os.read, masurat pe
# Amiko Viper 4K V20). Cand fereastra s-a schimbat, stratul se verifica la cererea urmatoare fara sa astepte
# INTERVAL_MIN_S sau bugetul codarii: ecranul care a micsorat imaginea s-a desenat si el.
#
# Fisierul nu importa nimic din enigma2: probele de pe PC dau un framebuffer fals (un fisier sau o clasa).

import array
import binascii
import os
import threading
import time
import zlib

def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (probele de pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text

FAZE = 8
INTERVAL_MIN_S = 0.25
FACTOR_BUGET = 3.0
NIVEL_ZLIB = 1
LATIME_IMPLICITA = 960
PAS_MARE_S = 10.0            # dupa o cerere la toata latimea, toti clientii primesc toata latimea atatea secunde
CALE_FB = "/dev/fb0"
CALE_SYS = "/sys/class/graphics/fb0"
CALE_VMPEG = "/proc/stb/vmpeg/0"


def _citesteText(cale):
	try:
		with open(cale, encoding="utf-8") as f:
			return f.read(128).strip()
	except (IOError, OSError):
		return ""


def geometrieDinSys(cale_sys=CALE_SYS):
	"""(latime, inaltime, stride, biti, y_pagina) din /sys, sau None. `mode` arata ca 'U:1920x1080p-0'."""
	mod = _citesteText(os.path.join(cale_sys, "mode"))
	l = h = 0
	try:
		parte = mod.split(":", 1)[-1]
		l_text, rest = parte.split("x", 1)
		h_text = ""
		for c in rest:
			if not c.isdigit():
				break
			h_text += c
		l, h = int(l_text), int(h_text)
	except (ValueError, IndexError):
		l = h = 0
	if l <= 0 or h <= 0:
		virt = _citesteText(os.path.join(cale_sys, "virtual_size"))
		try:
			l, hv = [int(x) for x in virt.split(",")[:2]]
			h = hv // 2 if hv >= 2 * 576 else hv
		except (ValueError, IndexError):
			return None
	try:
		stride = int(_citesteText(os.path.join(cale_sys, "stride")) or "0")
		biti = int(_citesteText(os.path.join(cale_sys, "bits_per_pixel")) or "0")
	except ValueError:
		return None
	y = 0
	pan = _citesteText(os.path.join(cale_sys, "pan"))
	try:
		y = int(pan.split(",")[1])
	except (ValueError, IndexError):
		y = 0
	if l <= 0 or h <= 0 or stride < l * 4:
		return None
	return (l, h, stride, biti, y)


def fereastraDin720(x, y, l, h):
	"""(x, y, l, h) din 720x576 (dst_*) -> (x, y, l, h) in procente din ecran, cu doua zecimale; ecranul intreg (0 0 0 0,
	o latime sau o inaltime zero) = (0, 0, 100, 100). Dreptunghiul se taie la marginile ecranului."""
	if l <= 0 or h <= 0:
		return (0.0, 0.0, 100.0, 100.0)
	x0 = min(max(x, 0), 720)
	y0 = min(max(y, 0), 576)
	x1 = min(x0 + l, 720)
	y1 = min(y0 + h, 576)
	if x1 <= x0 or y1 <= y0:
		return (0.0, 0.0, 100.0, 100.0)
	return (round(x0 * 100.0 / 720, 2), round(y0 * 100.0 / 576, 2), round((x1 - x0) * 100.0 / 720, 2),
		round((y1 - y0) * 100.0 / 576, 2))


def fereastraVideo(cale=CALE_VMPEG):
	"""Fereastra imaginii pe televizor (decodorul 0), in procente (fereastraDin720), sau None cand nodurile lipsesc (PC,
	emulatorul, alt driver). Un nod gol sau care nu e numar hex = 0 (ecranul intreg)."""
	v = []
	for nume in ("dst_left", "dst_top", "dst_width", "dst_height"):
		try:
			fd = os.open(os.path.join(cale, nume), os.O_RDONLY)
		except OSError:
			return None
		try:
			text = os.read(fd, 32)
		except OSError:
			text = b""
		finally:
			os.close(fd)
		try:
			v.append(int(text.strip() or b"0", 16))
		except ValueError:
			v.append(0)
	return fereastraDin720(*v)


def textFereastra(f):
	"""Textul antetului x-hds-video: "x,y,l,h" in procente, fara zerourile de la coada ("61.25,13.37,33.33,33.33",
	ecranul intreg "0,0,100,100")."""
	return ",".join(("%.2f" % n).rstrip("0").rstrip(".") for n in f)


def _adauga(semn, crc_rand):
	"""Semnul unei faze: crc32 peste crc32-urile randurilor ei, in ordine (fiecare rand se trece o singura data prin
	crc32, si la verificare, si la codare)."""
	return zlib.crc32(crc_rand.to_bytes(4, "little"), semn)


class Framebuffer(object):
	"""Citirea /dev/fb0 deschis numai pentru citire. Probele dau alta cale si alta geometrie."""

	def __init__(self, cale=CALE_FB, cale_sys=CALE_SYS, geometrie=None):
		self._cale = cale
		self._cale_sys = cale_sys
		self._geometrie = geometrie
		self._fd = None

	def geometrie(self):
		if self._geometrie is not None:
			return self._geometrie()
		return geometrieDinSys(self._cale_sys)

	def rand(self, y_abs, stride, octeti):
		if self._fd is None:
			self._fd = os.open(self._cale, os.O_RDONLY)
		return os.pread(self._fd, octeti, y_abs * stride)

	def inchide(self):
		fd, self._fd = self._fd, None
		if fd is not None:
			try:
				os.close(fd)
			except OSError:
				pass


class _Stare(object):
	"""Ce stie stratul pentru un pas (1 = toata latimea, 2 = jumatate)."""

	def __init__(self):
		self.cheie = None            # (l, h, stride, y_pagina): alta cheie = cadrul se citeste din nou
		self.crc = [None] * FAZE     # crc32 al fiecarei faze la ultima codare
		self.faza = 0
		self.gen = 0
		self.date = None             # cadrul comprimat (gzip)
		self.marime = (0, 0)
		self.gol = True              # tot cadrul e transparent
		self.urmatoarea = 0.0        # nicio verificare inainte de acest moment (ceasul monoton)
		self.ultima_codare_s = 0.0
		self.grabit = False          # fereastra imaginii s-a schimbat: verificarea nu asteapta `urmatoarea`


class Strat(object):
	"""Cadrele stratului, cerute din firele separate ale rutei. Un singur lacat: o verificare odata."""

	def __init__(self, fb=None, ceas=time.monotonic, semn=None, fereastra=None):
		self.fb = fb or Framebuffer()
		self._fereastra = fereastra or fereastraVideo
		self._fereastra_vazuta = None
		self._mare_pana = 0.0            # pana atunci (ceasul monoton) toti primesc toata latimea (pasPentru)
		self._ceas = ceas
		self._semn = semn or binascii.hexlify(os.urandom(4)).decode("ascii")
		self._lacat = threading.Lock()
		self._stari = {}
		self.verificari = 0
		self.codari = 0

	def fereastra(self):
		"""Fereastra imaginii de acum (procente) sau None. Cand difera de cea de la cererea de dinainte, fiecare pas se
		verifica la cererea asta (grabit), nu dupa INTERVAL_MIN_S: lista de canale s-a deschis sau s-a inchis, deci si
		stratul s-a schimbat. Pe firul enigma2; doar o atribuire, fara lacat."""
		try:
			f = self._fereastra()
		except Exception:
			f = None
		if f != self._fereastra_vazuta:
			self._fereastra_vazuta = f
			for st in list(self._stari.values()):
				st.grabit = True
		return f

	@staticmethod
	def pas(latime_ceruta, latime_fb):
		"""1 sau 2: jumatate de latime numai cand clientul arata stratul pe cel mult jumatate din latimea lui (si stratul
		e mare); altfel toata latimea, pe care browserul o micsoreaza cu netezire (textul ramane clar)."""
		try:
			latime_ceruta = int(latime_ceruta)
		except (TypeError, ValueError):
			latime_ceruta = LATIME_IMPLICITA
		if latime_fb >= 1280 and latime_ceruta * 2 <= latime_fb:
			return 2
		return 1

	def pasPentru(self, latime_ceruta, latime_fb):
		"""Pasul trimis acestui client: pas(), dar dupa o cerere la toata latimea toti primesc toata latimea inca
		PAS_MARE_S secunde (cea mai mare latime ceruta de curand): un singur cadru se verifica si se codeaza."""
		p = self.pas(latime_ceruta, latime_fb)
		acum = self._ceas()
		if p == 1:
			self._mare_pana = acum + PAS_MARE_S
		elif acum < self._mare_pana:
			p = 1
		return p

	def etag(self, pas, st):
		return '"%s-%d-%d"' % (self._semn, pas, st.gen)

	def dinMemorie(self, latime_ceruta, etag_client=None, latime_fb=None):
		"""Pe firul enigma2, fara sa citeasca nimic: raspunsul gata facut daca nu e vremea unei verificari (sau daca
		alta verificare e in lucru si exista un cadru), altfel None (atunci se cheama cadru() pe un fir)."""
		if latime_fb is None:
			g = self.fb.geometrie()
			if g is None:
				return None
			latime_fb = g[0]
		p = self.pasPentru(latime_ceruta, latime_fb)
		st = self._stari.get(p)
		if st is None or st.date is None:
			return None
		if (self._ceas() < st.urmatoarea and not st.grabit) or self._lacat.locked():
			return self._raspuns(p, st, etag_client)
		return None

	def cadru(self, latime_ceruta, etag_client=None):
		"""Pe un fir separat: verifica (si la schimbare codeaza) apoi da raspunsul. -> dict cu 'cod' (200, 304, 503),
		'etag', 'date', 'marime', 'gol'."""
		with self._lacat:
			g = self.fb.geometrie()
			if g is None:
				return {"cod": 503, "mesaj": _t("Stratul grafic nu se poate citi pe acest receptor.")}
			l, h, stride, biti, y0 = g
			if biti != 32:
				return {"cod": 503, "mesaj": _t("Stratul grafic nu are 32 de biti pe pixel (%d).") % biti}
			p = self.pasPentru(latime_ceruta, l)
			st = self._stari.setdefault(p, _Stare())
			acum = self._ceas()
			if st.date is None or acum >= st.urmatoarea or st.grabit:
				st.grabit = False
				self._verifica(st, p, g, acum)
			return self._raspuns(p, st, etag_client)

	def _raspuns(self, p, st, etag_client):
		e = self.etag(p, st)
		if etag_client and etag_client.strip() == e:
			return {"cod": 304, "etag": e}
		return {"cod": 200, "etag": e, "date": st.date, "marime": st.marime, "gol": st.gol}

	# ------------------------------------------------------------ citirea
	@staticmethod
	def _randuri(h, p):
		return list(range(0, h, p))

	def _crcFaza(self, g, p, k):
		l, h, stride, _b, y0 = g
		octeti = l * 4
		c = 0
		ys = self._randuri(h, p)
		for i in range(k, len(ys), FAZE):
			c = _adauga(c, zlib.crc32(self.fb.rand(y0 + ys[i], stride, octeti)))
		return c

	def _verifica(self, st, p, g, acum):
		self.verificari += 1
		l, h, stride, _b, y0 = g
		cheie = (l, h, stride, y0)
		if st.date is not None and st.cheie == cheie:
			k = st.faza
			st.faza = (k + 1) % FAZE
			if self._crcFaza(g, p, k) == st.crc[k]:
				st.urmatoarea = acum + INTERVAL_MIN_S
				return
		inceput = self._ceas()
		self._codeaza(st, p, g)
		st.cheie = cheie
		durata = max(0.0, self._ceas() - inceput)
		st.ultima_codare_s = durata
		st.urmatoarea = self._ceas() + max(INTERVAL_MIN_S, FACTOR_BUGET * durata)

	def _codeaza(self, st, p, g):
		l, h, stride, _b, y0 = g
		octeti = l * 4
		ys = self._randuri(h, p)
		crc = [0] * FAZE
		bucati = []
		crc_gol = zlib.crc32(bytes(octeti))
		goale = 0
		for i, y in enumerate(ys):
			r = self.fb.rand(y0 + y, stride, octeti)
			if len(r) < octeti:
				r = r + bytes(octeti - len(r))
			c = zlib.crc32(r)
			if c == crc_gol:
				goale += 1
			crc[i % FAZE] = _adauga(crc[i % FAZE], c)
			bucati.append(r)
		if st.date is not None and crc == st.crc and st.marime == (len(range(0, l, p)), len(ys)):
			return  # schimbarea a fost numai in coloanele care nu se trimit: acelasi cadru
		self.codari += 1
		brut = b"".join(bucati)
		latime = l
		if p > 1:
			# un pixel din p pe orizontala: array e cea mai iute cale fara numpy (masurat: 31 ms fata de 50 ms cu
			# memoryview pe randuri, la 960x540)
			px = array.array("I")
			px.frombytes(brut)
			brut = px[::p].tobytes()
			latime = len(range(0, l, p))
		# toate randurile goale (zero, cum curata enigma2): nimic desenat, browserul doar sterge stratul
		st.gol = goale == len(ys)
		c = zlib.compressobj(NIVEL_ZLIB, zlib.DEFLATED, 31)
		st.date = c.compress(brut) + c.flush()
		st.marime = (latime, len(ys))
		st.crc = crc
		st.gen += 1


_STRAT = []


def strat():
	if not _STRAT:
		_STRAT.append(Strat())
	return _STRAT[0]
