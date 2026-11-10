# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-only
# Compozitii native din poze. Numai literele sunt rasterizate aici.

import hashlib
import io
import json
import os
import tempfile
from collections import OrderedDict
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

MARIMI = ((400, 240), (480, 320), (800, 480))
T, S, C, G, R = "#DCE9F4", "#A5B9CE", "#42DDE5", "#F2BD68", "#FF7D8D"
_CADRE = OrderedDict()
_TEMP = None
_LIVE = None


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError):
		return text


def dosar():
	proiect = os.environ.get("HDS_IMAGINE")
	if proiect:
		return os.path.join(proiect, "HDSatelit", "afisaj-color")
	return "/usr/share/enigma2/HDSatelit/afisaj-color"


@lru_cache(maxsize=3)
def manifest(marime):
	with open(os.path.join(dosar(), "orbita", "%dx%d" % marime,
			"manifest.json"), encoding="utf-8") as f:
		return json.load(f)["screens"]


@lru_cache(maxsize=48)
def font(familie, marime):
	if familie in ("arab", "arab_mixt"):
		proiect = os.environ.get("HDS_IMAGINE")
		nume = "DejaVuSansMono-Bold.ttf" if familie == "arab_mixt" else "ae_AlMateen.ttf"
		cale = os.path.join(proiect, "data", "fonts", nume) if proiect else (
			os.path.join("/usr/share/fonts", nume))
		return ImageFont.truetype(cale, int(marime))
	nume = "NotoSansCondensed-SemiBold.ttf" if familie == "condensed" else "NotoSans-SemiBold.ttf"
	return ImageFont.truetype(os.path.join(dosar(), "fonturi", nume), int(marime))


def _familie(text, familie):
	# Fontul arab instalat are glifele si tabelele de legare a literelor.
	if any("\u0600" <= c <= "\u06ff" for c in str(text)):
		# Titlul EPG poate avea alt alfabet decat eticheta tradusa.
		if any(c.isalpha() and not "\u0600" <= c <= "\u06ff" for c in str(text)):
			return "arab_mixt"
		return "arab"
	return familie


@lru_cache(maxsize=96)
def _marimeText(text, familie, size, latime, inaltime):
	# Numai etichetele se adapteaza; cifrele raman la marimea nativa.
	def incape(marime):
		f = font(familie, marime)
		b = f.getbbox(text)
		return _incape(text, f, latime) and b[3] - b[1] <= inaltime
	jos, sus = 1, int(size)
	if incape(sus):
		return sus
	while jos < sus:
		mijloc = (jos + sus + 1) // 2
		if incape(mijloc):
			jos = mijloc
		else:
			sus = mijloc - 1
	return jos


def poza(cale):
	st = os.stat(cale)
	return _poza(cale, st.st_mtime_ns, st.st_size)


@lru_cache(maxsize=48)
def _poza(cale, versiune, marime):
	with Image.open(cale) as im:
		return im.convert("RGBA")


def _grupe(ecran):
	grupe = OrderedDict()
	for t in ecran["text"]:
		grupe.setdefault(tuple(t["box"]), []).append(t)
	return list(grupe.values())


def _incape(text, f, latime):
	b = f.getbbox(text)
	return max(f.getlength(text), b[2]) - min(0, b[0]) <= latime


def _scurt(text, f, latime):
	if _incape(text, f, latime):
		return text
	parti = text.split()
	while len(parti) > 1:
		parti.pop()
		scurt = " ".join(parti) + "…"
		if _incape(scurt, f, latime):
			return scurt
	while text and not _incape(text + "…", f, latime):
		text = text[:-1]
	return text.rstrip() + "…" if text else ""


class Compozitie:
	def __init__(self, scena, marime, sablon):
		self.s, self.marime = scena, marime
		self.e = manifest(marime)[sablon]
		self.root = os.path.join(dosar(), "orbita", "%dx%d" % marime)
		fond = self.e["background"]
		if scena.get("pagina") in ("canal", "schimbare_canal"):
			if not scena.get("canal", {}).get("sigla"):
				fond = self.e.get("background_no_picon", fond)
		self.im = poza(os.path.join(self.root, fond)).copy()
		self.d = ImageDraw.Draw(self.im)
		self.grupe = _grupe(self.e)
		self.audit = []

	def text(self, text, box, size, familie="sans", color=T,
			align="left", baseline=None, linii=1, principal=False):
		text = " ".join(str(text or "").split()).replace("\u2212", "-")
		if not text:
			return True
		if any("\u0600" <= c <= "\u06ff" for c in text):
			# Unitatea isi pastreaza ordinea literelor in textul de la dreapta.
			for unitate in ("°C", "°F"):
				text = text.replace(unitate, "\u2066" + unitate + "\u2069")
		x, y, w, h = [int(round(v)) for v in box]
		familie = _familie(text, familie)
		f = font(familie, size)
		pas = int(size * 1.25)
		if principal and not _incape(text, f, w):
			return False
		randuri = []
		for _i in range(linii - 1):
			if _incape(text, f, w):
				break
			cuvinte, linie = text.split(), ""
			while cuvinte and _incape((linie + " " + cuvinte[0]).strip(), f, w):
				linie = (linie + " " + cuvinte.pop(0)).strip()
			if not linie:
				break
			randuri.append(linie)
			text = " ".join(cuvinte)
		randuri.append(text if principal else _scurt(text, f, w))
		while len(randuri) > 1 and (len(randuri) - 1) * pas + size > h:
			ultim = randuri.pop()
			randuri[-1] = _scurt(randuri[-1] + " " + ultim, f, w)
		for i, linie in enumerate(randuri):
			b = self.d.textbbox((0, 0), linie, font=f, anchor="ls")
			lat, inalt = b[2] - b[0], b[3] - b[1]
			if principal and inalt > h:
				return False
			stanga = x + (w - lat) / 2 if align == "center" else x
			if align in ("right", "end"):
				stanga = x + w - lat
			baza = baseline if baseline is not None else y + (h - inalt) / 2 - b[1]
			if len(randuri) > 1:
				baza = y - b[1] + i * pas
			baza = min(y + h - b[3], max(y - b[1], baza))
			px, py = int(round(stanga - b[0])), int(round(baza))
			ink = self.d.textbbox((px, py), linie, font=f, anchor="ls")
			self.audit.append(dict(text=linie, box=[x, y, w, h], ink=list(ink), principal=principal))
			if principal and (":" in linie or "%" in linie):
				for j, litera in enumerate(linie):
					culoare = C if litera == ":" else G if litera == "%" else color
					self.d.text((px + f.getlength(linie[:j]), py), litera,
						font=f, fill=culoare, anchor="ls")
			else:
				self.d.text((px, py), linie, font=f, fill=color, anchor="ls")
		return True

	def grup(self, i, text, **kw):
		if i >= len(self.grupe):
			return False
		t = self.grupe[i][0]
		args = dict(box=t["box"], size=t["size"], familie=t["font"],
			color=t["color"], align=t["align"], baseline=t["baseline"])
		args.update(kw)
		if i == 0 and args["size"] < 60 and (self.s.get("mut") or self.s.get("inregistrari")):
			box = list(args["box"])
			stanga, _mut, _fs, _m, _sus = self._locStari()
			box[2] = min(box[2], max(1, stanga - box[0] - _m))
			args["box"] = box
		return self.text(text, **args)

	def art(self, a, x=None, y=None, flip=False):
		if a.get("in_background"):
			return
		im = poza(os.path.join(self.root, a["file"]))
		if flip:
			im = im.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
		x = a["box"][0] if x is None else x
		y = a["box"][1] if y is None else y
		self.im.alpha_composite(im, (round(x), round(y)))

	def icoane(self):
		for a in self.e["artwork"]:
			if a["role"] == "icon":
				self.art(a, flip=self.s.get("antena", {}).get("directie") == "vest"
					and a.get("native_box", a["box"])[2] > 50)

	def imagine(self, cale, box, mareste=True):
		if not cale:
			return False
		if cale.startswith("afisaj-color/"):
			cale = os.path.join(os.path.dirname(dosar()), cale)
		try:
			im = poza(cale)
		except (OSError, ValueError):
			return False
		x, y, w, h = [round(v) for v in box]
		k = min(w / im.width, h / im.height)
		if not mareste:
			k = min(k, 1)
		im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.Resampling.LANCZOS)
		self.im.alpha_composite(im, (x + (w - im.width) // 2, y + (h - im.height) // 2))
		return True

	def bara(self):
		p = self.s.get("progres")
		if not self.s.get("bara", True) or p is None:
			return
		p = max(0, min(1, p))
		ordine = {"progress-track": 0, "progress-fill": 1,
			"progress-overlay": 2, "progress-cap": 3}
		for a in sorted(self.e["artwork"], key=lambda a: ordine.get(a["role"], 9)):
			role = a["role"]
			if role in ("progress-track", "progress-overlay"):
				self.art(a)
			elif role == "progress-fill" and p > 0:
				im = poza(os.path.join(self.root, a["file"]))
				cx, cy, w, h = a["content_box"]
				# Taiem fotografia barei, fara a intinde gradientul.
				im = im.crop((0, 0, min(im.width, round(cx + w * p)), im.height))
				self.im.alpha_composite(im, (round(a["box"][0]), round(a["box"][1])))
			elif role == "progress-cap" and p > 0:
				b = a.get("data_box")
				if b:
					cx = a["content_box"][0]
					cw = a["content_box"][2]
					self.art(a, x=b[0] + b[2] * p - cw / 2 - cx)

	def _locStari(self):
		w, h = self.marime
		m, fs, sus = {400: (12, 14, 12), 480: (16, 16, 16), 800: (32, 24, 24)}[w]
		n = self.s.get("inregistrari", 0)
		stanga = w - m - (fs * 4.6 if n else 0)
		mut = None
		if self.s.get("mut") and self.s["pagina"] != "volum":
			text = _("MUT")
			familie = _familie(text, "sans")
			latime = min(w * .30, max(fs * 3.2, font(familie, fs).getlength(text) + 2))
			x = stanga - (fs * .3 if n else 0) - latime
			marime = _marimeText(text, familie, fs, latime, fs * 1.5)
			mut = (text, (x, sus, latime, fs * 1.5), marime)
			stanga = x
		return stanga, mut, fs, m, sus


	def stari(self):
		w, h = self.marime
		_stanga, mut, fs, m, sus = self._locStari()
		n = self.s.get("inregistrari", 0)
		if n:
			self.text("REC" + (" %d" % n if n > 1 else ""),
				(w - m - fs * 4.6, sus, fs * 4.6, fs * 1.5), fs, color=R, align="right")
		if mut:
			self.text(mut[0], mut[1], mut[2], color=S, align="right")


def _temperature(t):
	return str(t or "").replace("°C", "").replace("°F", "").replace("K", "").replace("\u2212", "-")


def _sablon(s, w):
	p = s.get("pagina", "generic")
	if p == "canal":
		c = s.get("canal", {})
		if len(c.get("numar", "")) >= (4 if w == 400 else 5):
			return "03-canal-cinci-cifre"
		if not c.get("emisiune") or not c["emisiune"].get("titlu"):
			return "03-canal-fara-epg"
		return "03-canal"
	if p == "volum":
		return "05-volum-mut" if s.get("mut") else "05-volum"
	if p == "actualizare":
		return "09-actualizare-fara-procent" if s.get("progres") is None else "09-actualizare"
	return {"ceas": "01-ceas", "ceas_vreme": "02-ceas-vreme",
		"vreme": "04-vreme", "asteptare": "08-asteptare", "personaj": "00-personaj",
		"inregistrare": "07-inregistrare", "inregistrare_esuata": "07-inregistrare-esuata",
		"lipsa_semnal": "07-lipsa-semnal", "antena": "09-antena",
		"schimbare_canal": "06-schimbare-canal"}.get(p, "01-ceas")


def _weather_icon(c, cod, box, original=""):
	# Folosim simbolul starii reale, niciodata prognoza dintr-un exemplu.
	k = None
	if cod in (1, 2):
		k = "partial"
	elif cod == 3:
		k = "nori"
	elif cod in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82):
		k = "ploaie"
	elif cod in (71, 73, 75, 77, 85, 86):
		k = "zapada"
	path = os.path.join(c.root, "vreme-" + k + ".png") if k else ""
	if path and os.path.isfile(path) and c.imagine(path, box, mareste=False):
		return
	if original:
		if os.environ.get("HDS_IMAGINE") and original.startswith("/usr/share/enigma2/"):
			original = os.path.join(os.environ["HDS_IMAGINE"], "data",
				original[len("/usr/share/enigma2/"):])
		c.imagine(original, box)


def _vreme(c):
	s, w = c.s, c.marime[0]
	v = s.get("vreme", {})
	c.grup(0, v.get("oras") or _("Vremea"))
	unitate = "K" if v.get("temperatura_text", "").endswith("K") else (
		"°F" if v.get("temperatura_text", "").endswith("F") else "°C")
	c.grup(1, (_("Ultima citire") if v.get("veche") else _("Azi")) + ", " + unitate)
	locuri = {400: ((12, 80, 240, 120), (12, 204, 20, 20), [(276, 76, 32, 32), (276, 176, 32, 32)]),
		480: ((16, 104, 248, 120), (16, 240, 64, 64), [(300, 108, 40, 40), (300, 236, 40, 40)]),
		800: ((32, 144, 416, 192), (32, 352, 88, 88), [(664, 96, 72, 72), (664, 296, 72, 72)])}[w]
	if not c.grup(2, _temperature(v.get("temperatura_text")), principal=True):
		_weather_icon(c, v.get("cod"), locuri[0], v.get("pictograma"))
		detail = " ".join(dict.fromkeys((v.get("temperatura_text", ""), s.get("detaliu", ""))))
	else:
		detail = s.get("detaliu", "")
	if not v.get("disponibila"):
		detail = _("Fără date")
	args = dict(linii=2, color=G if v.get("veche") else S)
	if v.get("veche"):
		args["size"] = {400: 16, 480: 20, 800: 28}[w]
	if w == 400:
		args["box"] = (36, 204, 216, 24)
	c.grup(3, detail, **args)
	if locuri[1] and v.get("disponibila"):
		_weather_icon(c, v.get("cod"), locuri[1], v.get("pictograma"))
	zile = v.get("zile", [])
	for i in range(2):
		z = zile[i + 1] if len(zile) > i + 1 else {}
		eticheta = z.get("eticheta", _("Fără date"))
		if w == 800 and not z.get("data"):
			c.grup(4 + 2 * i, eticheta, box=(496, 96 + i * 200, 256, 40))
		else:
			t = c.grupe[4 + 2 * i][0]
			size = _marimeText(eticheta, _familie(eticheta, t["font"]),
				t["size"], t["box"][2], t["box"][3])
			c.grup(4 + 2 * i, eticheta, size=size)
		mini, maxi = _temperature(z.get("min_text")), _temperature(z.get("max_text"))
		val = maxi if w == 400 else " / ".join(a for a in (mini, maxi) if a)
		if val:
			c.grup(5 + 2 * i, val, align="right" if w == 400 else "center")
		elif z.get("data"):
			b = c.grupe[5 + 2 * i][0]["box"]
			text = _("Fără date")
			familie = _familie(text, "sans")
			# Cuvintele incap intregi pe doua randuri; temperaturile nu se micsoreaza.
			size = min(_marimeText(cuvant, familie,
				{400: 14, 480: 16, 800: 24}[w], b[2], b[3])
				for cuvant in text.split())
			c.text(text, b, size, linii=2)
		_weather_icon(c, z.get("cod"), locuri[2][i], z.get("pictograma"))


def randeaza(scena, marime=(480, 320), audit=None):
	marime = tuple(marime)
	if marime not in MARIMI:
		raise ValueError("Rezolutie fara compozitie nativa: %s" % (marime,))
	s = scena
	w, h = marime
	if s.get("stins"):
		return Image.new("RGB", marime, "black")
	c = Compozitie(s, marime, _sablon(s, w))
	p = s.get("pagina", "generic")
	if p in ("ceas", "ceas_vreme", "asteptare"):
		gi = 1 if p in ("ceas", "asteptare") else 0
		if p == "ceas":
			c.icoane()
			c.grup(0, "HD Satelit", box=(c.grupe[0][0]["run_box"][0],
				c.grupe[0][0]["box"][1], w * .65, c.grupe[0][0]["box"][3]))
		c.grup(gi, s.get("valoare") or s.get("ceas", "--:--"), principal=True, align="center")
		data = " · ".join(x for x in (s.get("ziua"), s.get("data")) if x)
		if p == "asteptare":
			data = s.get("detaliu") or data
		elif p == "ceas_vreme":
			data = s.get("data", "")
			parti = data.split()
			if len(parti) >= 3 and parti[-1].isdigit():
				data = " ".join(parti[:-1])
		if s.get("perioada"):
			data = s["perioada"] + " · " + data
		c.grup(gi + 1, data)
		if p == "ceas_vreme":
			v = s.get("vreme", {})
			temperatura = v.get("temperatura_text", "")
			unitate = "K" if temperatura.endswith("K") else "°F" if temperatura.endswith("F") else "°"
			gi_temp = 3 if w == 400 else 2
			t = c.grupe[gi_temp][0]
			f = font(t["font"], t["size"])
			text_temp = _temperature(temperatura) + unitate
			localitate = v.get("oras", "")
			if not _incape(text_temp, f, t["box"][2]):
				text_temp = _temperature(temperatura)
				localitate += " · " + unitate
			if _incape(text_temp, f, t["box"][2]):
				c.grup(gi_temp, text_temp, align="right", principal=True)
			else:
				localitate = temperatura + " · " + v.get("oras", "")
			c.grup(2 if w == 400 else 3, localitate)
			box = {400: (260, 168, 40, 40), 480: (312, 192, 56, 56), 800: (544, 264, 80, 80)}[w]
			_weather_icon(c, v.get("cod"), box, v.get("pictograma"))
	elif p == "canal":
		ch = s.get("canal", {})
		long = len(ch.get("numar", "")) >= (4 if w == 400 else 5)
		c.grup(0, ch.get("nume", ""))
		c.grup(2 if long else 1, ch.get("numar", ""), principal=True)
		pg = 1 if long else 2
		pb = c.grupe[pg][0]["box"]
		are_sigla = False
		if not long or not (s.get("mut") or s.get("inregistrari")):
			are_sigla = c.imagine(ch.get("sigla"), pb)
		if not are_sigla and not long:
			c.grup(pg, ch.get("nume", ""), linii=2, size={400: 20, 480: 24, 800: 36}[w])
		e = ch.get("emisiune") or {}
		c.grup(3, e.get("titlu") or _("Program indisponibil"))
		n = ch.get("urmatoarea") or {}
		urm = ""
		if n.get("titlu"):
			urm = _("Urmează") + " " + n.get("interval", "").split(" - ")[0] + " · " + n["titlu"]
		# La 400, singurul rand de jos da prioritate programului urmator.
		c.grup(4, urm if w == 400 and urm else e.get("interval", ""))
		if w != 400 and urm:
			c.grup(5, urm)
		if e.get("titlu"):
			c.bara()
	elif p == "vreme":
		_vreme(c)
	elif p == "volum":
		c.icoane()
		c.grup(0, _("Volum"))
		valoare = s.get("valoare", "")
		args = {}
		if s.get("mut"):
			t = c.grupe[1][0]
			familie = _familie(valoare, t["font"])
			args["size"] = _marimeText(valoare, familie, t["size"],
				t["box"][2], t["box"][3])
		c.grup(1, valoare, principal=True, **args)
		c.grup(2, (_("Sunet oprit") + " · " + str(s.get("volum", "")))
			if s.get("mut") else _("Nivelul volumului"))
		c.bara()
	elif p == "schimbare_canal":
		ch = s.get("canal", {})
		c.grup(0, _("Canal"))
		c.grup(1, s.get("valoare", ""), principal=True, align="center")
		if ch.get("confirmat"):
			c.imagine(ch.get("sigla"), c.grupe[2][0]["box"])
			c.grup(3, ch.get("nume", ""), linii=2)
	elif p == "personaj":
		b = next(a for a in c.e["artwork"] if a["role"] == "character")
		if not c.imagine(s.get("imagine"), b["data_box"]):
			c.art(b)
	elif p == "inregistrare":
		c.icoane()
		n = s.get("inregistrari", 0)
		c.grup(0, (_("Înregistrări active: %d") % n) if n > 1 else _("Înregistrare"))
		c.grup(1, "REC", principal=True)
		c.grup(2, s.get("canal", {}).get("nume") or s.get("detaliu", ""))
		c.grup(3, s.get("durata", ""))
	elif p in ("inregistrare_esuata", "lipsa_semnal"):
		c.icoane()
		g = 2 if p == "inregistrare_esuata" else 1
		c.grup(0, _("Înregistrare") if p == "inregistrare_esuata" else s.get("canal", {}).get("nume", ""))
		c.grup(g, _("Înregistrarea a eșuat") if p == "inregistrare_esuata" else _("Lipsă semnal"))
		c.grup(g + 1, s.get("detaliu", "") if p == "inregistrare_esuata" else _("Verifică antena și cablul"))
	elif p in ("actualizare", "antena"):
		c.icoane()
		first = c.grupe[0][0]
		box = list(first["box"])
		offset = {400: 30, 480: 36, 800: 48}[w]
		box[0] += offset
		box[2] -= offset
		c.grup(0, s.get("titlu", ""), box=box)
		if p == "actualizare" and s.get("progres") is not None:
			c.grup(1, str(round(s["progres"] * 100)) + "%", principal=True, align="center")
			c.grup(len(c.grupe) - 1, s.get("detaliu") or _("Nu opri receptorul"))
			c.bara()
		else:
			text = s.get("detaliu") or _("Nu opri receptorul")
			if p == "antena":
				d = s.get("antena", {}).get("directie")
				text = " · ".join(t for t in ((_('Spre vest') if d == "vest" else _("Spre est") if d == "est" else ""),
					s.get("valoare", ""), s.get("detaliu", "")) if t)
			c.grup(1, text)
	elif p == "picon":
		m = {400: 12, 480: 16, 800: 32}[w]
		c.imagine(s.get("imagine"), (m, h * .18, w - 2 * m, h * .62))
		if s.get("picon_mode") != "singur":
			c.text(s.get("titlu", ""), (m, m, w - 2 * m, h * .12), {400: 20, 480: 24, 800: 36}[w])
			c.grup(2, s.get("ceas", "--:--"), align="center")
	else:
		c.grup(0, s.get("titlu", ""))
		c.text(s.get("valoare", ""), {400: (12, 55, 376, 132),
			480: (16, 72, 448, 160), 800: (32, 96, 736, 248)}[w],
			{400: 30, 480: 40, 800: 64}[w], linii=3, align="center")
	c.stari()
	if audit is not None:
		audit.extend(c.audit)
	return c.im.convert("RGB")


def cadru(scena, marime=(480, 320)):
	"""PNG in memorie si un fisier temporar pentru incarcatorul nativ Enigma2."""
	global _TEMP
	marime = tuple(marime)
	imagine = scena.get("imagine") or scena.get("canal", {}).get("sigla", "")
	versiune = None
	if imagine and os.path.isfile(imagine):
		st = os.stat(imagine)
		versiune = (st.st_mtime_ns, st.st_size)
	cheie = json.dumps([marime, scena, versiune], sort_keys=True, ensure_ascii=False, default=str)
	if cheie in _CADRE:
		_CADRE.move_to_end(cheie)
		return _CADRE[cheie]
	im = randeaza(scena, marime)
	b = io.BytesIO()
	im.save(b, format="PNG", compress_level=1)
	date = b.getvalue()
	hash_ = hashlib.sha256(date).hexdigest()
	if _TEMP is None:
		_TEMP = tempfile.TemporaryDirectory(prefix="hds-afisaj-")
	cale = os.path.join(_TEMP.name, hash_ + ".png")
	if not os.path.exists(cale):
		with open(cale, "wb") as f:
			f.write(date)
	rez = (date, cale, hash_)
	_CADRE[cheie] = rez
	while len(_CADRE) > 8:
		_v, vechi = _CADRE.popitem(last=False)
		if vechi[1] != _LIVE and not any(c[1] == vechi[1] for c in _CADRE.values()):
			try:
				os.unlink(vechi[1])
			except OSError:
				pass
	return rez


def pastreaza(cale):
	"""Cadrul LCD ramane disponibil cand meniul cere multe previzualizari."""
	global _LIVE
	vechi, _LIVE = _LIVE, cale
	if vechi and vechi != cale and not any(c[1] == vechi for c in _CADRE.values()):
		try:
			os.unlink(vechi)
		except OSError:
			pass
