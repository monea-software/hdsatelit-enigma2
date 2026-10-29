#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# hds-rezerva-ecran.py: imaginea de pe televizor si pagina web ale caii de rezerva (tools/hds-rezerva.sh), cand
# enigma2 nu ajunge la interfata. Ruleaza numai in fereastra de rezerva, cu enigma2 oprit, cu python3 -I -S -B: numai
# modulele de baza (os, sys, struct, zlib, binascii, fcntl), fara Pillow, fara FreeType, fara enigma2.
#
# Intrarea: --date <date.txt> (randurile cheie=valoare scrise de hds-rezerva.sh), --dosar <dosarul din RAM>,
# --python <dosarul Python al enigma2> (pentru textele din Components/HdsDiagnostic.py, TEXTE_REZERVA, in cele 13
# limbi), --fb <dispozitivul fb>, --jurnal <hds-caderi.log>, optional --geometrie LxIxBPP (cand fb nu raspunde la
# ioctl, de pilda un fisier in probe) si --fara-fb.
# Iesirea: <dosar>/index.html si <dosar>/diagnostic.txt (pagina si textul de copiat; peste cele simple ale scriptului)
# si imaginea pe fb: fundal inchis, titlul, codul mare, fraza codului, rugamintea de poza, forumul si adresa de e-mail,
# adresa paginii, apoi randurile tehnice (ce a citit receptorul si ce asteapta software-ul).
#
# Literele: tabelul de mai jos, facut pe PC de tools/hds-rezerva-litere.py din DejaVuSansMono-Bold.ttf (licenta in
# /usr/share/fonts/DejaVuSansMono-Bold.license), celule de LITERE_LATIME x LITERE_INALTIME, 4 trepte de acoperire.
# Marite de 2 sau 3 ori pentru cod si adresa. O litera fara desen devine "?".
# Ecranul: geometria din FBIOGET_VSCREENINFO / FBIOGET_FSCREENINFO (si /sys/class/graphics/fb0/stride), pixelii dupa
# pozitiile culorilor date de driver (ARGB8888 pe HiSilicon; 16 biti merge si el), scrisi in pagina vazuta acum
# (yoffset), cu alfa plin. Totul se compune in memorie si se scrie o data.
# Nimic personal: numai campurile din date.txt (fara MAC, fara serie, fara jeton) si ultimele randuri din
# hds-caderi.log (texte fixe), curatate la ASCII si trecute prin faraAdrese (ca rz_filtru din hds-rezerva.sh): o
# adresa cu schema (si forma %3a//), un utilizator:parola@ si o adresa MAC devin un text fix.

import binascii
import os
import re
import struct
import sys
import zlib

LIMBI = ("ro", "en", "de", "fr", "es", "it", "hu", "cs", "pl", "pt", "nl", "ru", "tr")
FORUM = "https://stb.hdsatelit.com/forum/"
EMAIL = "contact@hdsatelit.com"

# textele de rezerva, cand Components/HdsDiagnostic.py lipseste sau nu are limba (celelalte limbi vin de acolo)
TEXTE = {
	"ro": {
		"titlu_E1": "Software pentru alt receptor",
		"titlu_E2": "Receptorul nu poate fi recunoscut",
		"titlu_E3": "Interfața nu pornește",
		"rugaminte": "Fă o poză acestui ecran și trimite-o pe forumul unde ai găsit software-ul sau la "
			"contact@hdsatelit.com.",
		"pagina": "Toate datele, de copiat, din calculator sau telefon:",
		"reincercare": "Interfața se încearcă din nou peste %d minute.",
		"coduri": "Coduri:",
		"E101": "Procesorul receptorului nu este cel pentru care e făcut software-ul.",
		"E102": "Driverul spune alt tip de placă decât cel pentru care e făcut software-ul.",
		"E103": "Eticheta din memoria receptorului spune alt tip de placă.",
		"E104": "Placa receptorului (antetul de fabrică) este alta.",
		"E105": "Partițiile din memoria receptorului sunt așezate altfel.",
		"E106": "Partiția nucleului sau a sistemului e în alt loc sau are altă mărime.",
		"E107": "Memoria internă are altă mărime decât la modelul pentru care e software-ul.",
		"E199": "O altă valoare a receptorului nu se potrivește.",
		"E201": "Procesorul nu s-a putut citi: driverul procesorului nu s-a încărcat.",
		"E202": "Tipul plăcii nu s-a putut citi: driverul plăcii nu s-a încărcat.",
		"E204": "Placa nu s-a putut citi din antetul de fabrică.",
		"E205": "Partițiile nu s-au putut citi din linia de pornire.",
		"E206": "Partiția nucleului sau a sistemului nu s-a găsit.",
		"E290": "Semnul receptorului din software este stricat.",
		"E291": "Verificarea de la pornire nu a dat niciun rezultat.",
		"E301": "Interfața a căzut de mai multe ori la pornire și a pornit în modul sigur.",
		"E303": "Interfața nu pornește deloc.",
		"E304": "Driverele receptorului lipsesc sau nu s-au încărcat.",
		"E305": "Interfața nu a apărut în 5 minute: s-a blocat la pornire.",
		"E302": "Interfața cade și în modul sigur.",
		"E309": "Interfața s-a oprit la pornire din alt motiv.",
	},
	"en": {
		"titlu_E1": "Software for another receiver",
		"titlu_E2": "The receiver cannot be recognised",
		"titlu_E3": "The interface does not start",
		"rugaminte": "Take a photo of this screen and send it to the forum where you found the software or to "
			"contact@hdsatelit.com.",
		"pagina": "All the data, to copy, from a computer or a phone:",
		"reincercare": "The interface is tried again in %d minutes.",
		"coduri": "Codes:",
		"E101": "The processor of the receiver is not the one the software is made for.",
		"E102": "The driver reports another board type than the one the software is made for.",
		"E103": "The label in the memory of the receiver names another board type.",
		"E104": "The board of the receiver (the factory header) is another one.",
		"E105": "The partitions in the memory of the receiver are laid out differently.",
		"E106": "The kernel or system partition is in another place or has another size.",
		"E107": "The internal memory has another size than on the model the software is made for.",
		"E199": "Another value of the receiver does not match.",
		"E201": "The processor could not be read: the processor driver did not load.",
		"E202": "The board type could not be read: the board driver did not load.",
		"E204": "The board could not be read from the factory header.",
		"E205": "The partitions could not be read from the boot line.",
		"E206": "The kernel or system partition was not found.",
		"E290": "The receiver mark in the software is damaged.",
		"E291": "The check at start gave no result.",
		"E301": "The interface crashed several times at start and started in safe mode.",
		"E303": "The interface does not start at all.",
		"E304": "The drivers of the receiver are missing or did not load.",
		"E305": "The interface did not appear in 5 minutes: it got stuck at start.",
		"E302": "The interface also crashes in safe mode.",
		"E309": "The interface stopped at start for another reason.",
	},
}

# randurile tehnice de pe ecran: (cheia din date.txt, eticheta, cheia valorii asteptate)
# (cele mai importante intai: pe 720p incap mai putine)
RANDURI_TEHNICE = (
	("cip", "cip", "asteptat_cip"),
	("boxtype", "boxtype", "asteptat_boxtype"),
	("hw", "hw", "asteptat_hw"),
	("lipsa", "lipsa", None),
	("module_lipsa", "module lipsa", None),
	("cauza", "cauza", None),
	("kernel", "kernel", None),
	("eticheta", "eticheta", None),
	("emmc", "emmc KiB", None),
)

CULORI = {
	"fundal": (16, 20, 28),
	"titlu": (255, 210, 90),
	"cod": (255, 112, 90),
	"text": (236, 240, 248),
	"adresa": (120, 200, 255),
	"gri": (150, 160, 176),
}


# ---------------------------------------------------------------- datele si textele

def citesteDate(cale):
	"""date.txt -> dict; cheile repetate (lipsa=) se aduna cu spatiu intre ele"""
	date = {}
	try:
		with open(cale, "rb") as f:
			for rand in f.read(65536).decode("utf-8", "replace").splitlines():
				if "=" not in rand:
					continue
				k, v = rand.split("=", 1)
				k = k.strip()
				if k == "cauza":
					v = textAscii(v)
				if k in date and v:
					date[k] = (date[k] + " " + v).strip()
				else:
					date[k] = v.strip()
	except (IOError, OSError):
		pass
	return date


_ADRESA = re.compile(r'[A-Za-z][A-Za-z0-9+.-]*(?:://|%3[aA]//)[^ "<>]*')
_UTILIZATOR = re.compile(r'[^ /@:"<>]+:[^ /@"<>]*@[^ "<>]+')
_MAC = re.compile(r'(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}')
_MAC_LIPIT = re.compile(r'((?:mac|ether|hwaddr|bdaddr)[ =:]*)[0-9A-Fa-f]{12}', re.I)


def faraAdrese(text):
	text = _ADRESA.sub("<adresa ascunsa>", text)
	text = _UTILIZATOR.sub("<adresa ascunsa>", text)
	text = _MAC.sub("<mac ascuns>", text)
	return _MAC_LIPIT.sub(r"\1<mac ascuns>", text)


def textAscii(text, maxim=200):
	return faraAdrese("".join(c for c in text if " " <= c <= "~"))[:maxim]


def texteDiagnostic(dosar_python):
	"""TEXTE_REZERVA din Components/HdsDiagnostic.py ({limba: {cheie: text}}), sau {} cand nu se poate citi"""
	if not dosar_python or not os.path.isdir(os.path.join(dosar_python, "Components")):
		return {}
	try:
		import builtins
		if not hasattr(builtins, "_"):
			builtins._ = lambda s: s
		sys.path.insert(0, dosar_python)
		from Components import HdsDiagnostic
		t = getattr(HdsDiagnostic, "TEXTE_REZERVA", None)
		return t if isinstance(t, dict) else {}
	except BaseException as e:
		print("textele din HdsDiagnostic nu se pot citi: %r" % (e,))
		return {}


def alegeLimba(date, texte_diag):
	limba = (date.get("limba") or "").split("_")[0].lower()
	if limba in TEXTE or limba in texte_diag:
		return limba
	return "en"


def texte(limba, texte_diag):
	"""textele limbii: ale noastre (romana sau engleza ca baza), peste ele cele din HdsDiagnostic"""
	t = dict(TEXTE["en"])
	t.update(TEXTE.get(limba, {}))
	for k, v in (texte_diag.get(limba) or {}).items():
		if isinstance(k, str) and isinstance(v, str) and v:
			t[k] = v
	return t


def grupa(cod):
	if cod.startswith("E1"):
		return "titlu_E1"
	if cod.startswith("E2"):
		return "titlu_E2"
	return "titlu_E3"


def frazaCod(cod, t):
	"""fraza codului; un cod necunoscut aici primeste fraza generala a grupei lui"""
	if t.get(cod):
		return t[cod]
	return t.get({"titlu_E1": "E199", "titlu_E2": "E291"}.get(grupa(cod), "E309"), "")


def reincercare(t, date):
	try:
		minute = max(1, (int(date.get("durata") or 300) + 59) // 60)
	except ValueError:
		minute = 5
	try:
		return t.get("reincercare", "") % minute
	except (TypeError, ValueError):
		return t.get("reincercare", "")


def adresa(date):
	ip = date.get("ip") or ""
	port = date.get("port") or "80"
	if not ip:
		return ""
	return "http://%s/" % ip if port == "80" else "http://%s:%s/" % (ip, port)


def randuriTehnice(date):
	r = []
	for k, eticheta, asteptat in RANDURI_TEHNICE:
		v = date.get(k)
		if not v:
			continue
		rand = "%s: %s" % (eticheta, v)
		if asteptat and date.get(asteptat) and date.get(asteptat) != v:
			rand += " (%s)" % date.get(asteptat)
		r.append(textAscii(rand, 160))
	if date.get("nepotriviri"):
		r.append("nepotriviri: " + textAscii(date["nepotriviri"], 120))
	model = date.get("model") or ""
	if model:
		r.append(textAscii("%s (%s) %s" % (model, date.get("masina", ""), date.get("imagine") or date.get("versiune", "")),
			160))
	return r


# ---------------------------------------------------------------- pagina

def _esc(text):
	return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def jurnalCaderi(cale, randuri=15):
	try:
		with open(cale, "rb") as f:
			f.seek(0, 2)
			marime = f.tell()
			f.seek(max(0, marime - 8192))
			text = f.read().decode("utf-8", "replace")
	except (IOError, OSError):
		return []
	return [textAscii(r, 200) for r in text.splitlines()[-randuri:]]


def textComplet(date, t, t_en, jurnal):
	cod = date.get("cod", "")
	coduri = (date.get("coduri") or cod).split()
	r = ["HD Satelit " + cod, t.get(grupa(cod), ""), ""]
	for c in coduri:
		r.append("%s: %s" % (c, frazaCod(c, t)))
	r += ["", t.get("rugaminte", "")]
	if t is not t_en:
		r += ["", t_en.get(grupa(cod), "")] + ["%s: %s" % (c, frazaCod(c, t_en)) for c in coduri] + [t_en.get("rugaminte", "")]
	r += ["", FORUM, EMAIL, ""]
	for k in sorted(date):
		r.append("%s=%s" % (k, date[k]))
	if jurnal:
		r += ["", "hds-caderi.log:"] + jurnal
	return "\n".join(r) + "\n"


def scriePagina(dosar, date, t, t_en, jurnal):
	cod = date.get("cod", "")
	coduri = (date.get("coduri") or cod).split()
	text = textComplet(date, t, t_en, jurnal)
	h = ['<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">',
		"<title>HD Satelit %s</title>" % _esc(cod),
		"<style>body{font-family:sans-serif;background:#10141c;color:#eef0f8;margin:16px;max-width:60em}"
		"h1{color:#ffd25a;font-size:1.4em}.cod{color:#ff705a;font-size:3em;font-weight:bold;margin:.2em 0}"
		"a{color:#78c8ff}td{padding:2px 8px;vertical-align:top;word-break:break-all}"
		"textarea{width:100%;height:16em;background:#0a0d12;color:#eef0f8}</style></head><body>",
		"<h1>%s</h1>" % _esc(t.get(grupa(cod), "")),
		'<p class="cod">%s</p>' % _esc(cod)]
	for c in coduri:
		h.append("<p><b>%s</b>: %s</p>" % (_esc(c), _esc(frazaCod(c, t))))
	h.append("<p>%s</p>" % _esc(t.get("rugaminte", "")))
	h.append('<p><a href="%s">%s</a> &nbsp; <a href="mailto:%s?subject=HD%%20Satelit%%20%s">%s</a></p>'
		% (FORUM, FORUM, EMAIL, _esc(cod), EMAIL))
	h.append("<p>%s</p>" % _esc(reincercare(t, date)))
	h.append("<table>")
	for k in sorted(date):
		h.append("<tr><td>%s</td><td>%s</td></tr>" % (_esc(k), _esc(date[k])))
	h.append("</table>")
	if jurnal:
		h.append("<h2>hds-caderi.log</h2><pre>%s</pre>" % _esc("\n".join(jurnal)))
	h.append("<p>%s</p><textarea readonly>%s</textarea>" % (_esc(t.get("pagina", "")), _esc(text)))
	h.append('<p><a href="/diagnostic.txt">diagnostic.txt</a></p></body></html>')
	for nume, continut in (("diagnostic.txt", text), ("index.html", "\n".join(h) + "\n")):
		cale = os.path.join(dosar, nume)
		with open(cale + ".nou", "w", encoding="utf-8") as f:
			f.write(continut)
		os.replace(cale + ".nou", cale)


# ---------------------------------------------------------------- literele

# LITERE-INCEPUT (facut de tools/hds-rezerva-litere.py din DejaVuSansMono-Bold.ttf; nu se scrie de mana)
LITERE_LATIME = 18
LITERE_INALTIME = 36
LITERE_INTERVALE = [(0x0020, 0x007E), (0x00A0, 0x00FF), (0x0100, 0x017F), (0x0218, 0x021B), (0x0400, 0x045F), (0x2013, 0x2014), (0x2018, 0x201E), (0x2026, 0x2026)]
LITERE_DATE = (
	"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"
	"Uu+T150o52v4XX9CzbjPYjJUtHBqgH/yBS7ChU8SMVL5+UT8ghaGU6/sxGSYWeBBn7mVpf7COb7K5fgOvnfIiQTfuAJ8s3eH4FUJ/9SCBqPyKfwA4c81"
	"RJBvWnFnngZ8G+ATxC5csRzlj2UpuPCAPbX5LNDWqPiots3E32Y/Y3MAq8iY/dknlRO2zLawLbHNlz1N/nhmUiBNEekzZSWfMyJNjUP2H2LOrFTIlL0/"
	"OvfXB5OLsPnqrE3BwrmG1PKKNb8ERPAKcfXpl9SCNMkvt1brBvzBio6I7fuNOS9EaXrTkig04jZniVFHagjHQeyPv82lDTvrGwQ+Ms95bbLJcbZ5s1lu"
	"nG0+OTYNqjJqxrdnDBP9s4s5O5jcLHCccxTU7L2DmIQEEBFMwwrqKsEsqKTNkPoEmUfnGHLcVQBKBm6hTVBbCuSkwSK4VCvhw3Dg3eZmyTCO8JFptqH/"
	"D1n7NEvky+RsMw+rhOp3DT8Zc54T9hPiYJT7ZmIee5tVjByPLawu3TWNHmmbuZFL0M01I6bzOnlj1HlO1sgbY27zOnljpG3eOHcfYg6crXJnUbF5uOnc"
	"WevkujHnOVmrp4w5z8k6PWXEbV6rp4y4zWv1lHG2ebOecoB5ezasdItfxoLQXRXckaIFU3lussCzX3OXHEIlnqerXE7dgXu5loEbhtd/OIFkPpny9izw"
	"V+alBeKxRGIfTMsrQc4akBC8HRJ87CMPuAtwAJYEn0QQCCezxoeC124JOjdwVbkLOn9+EF436twsa3jdmNu8jteNtM0b+cYh9o1DzM2ynEnsZlOWXf/A"
	"Ihc7u6Uq/XqK6LMpZFFOoFUCEIzmw0TxRtICUn35RPbcr1GkUNnAIJA2yO1VcW4vJ3/niH6+QwyUAHNUc73Y/965LEaVF6LnGv2Y2qx2nGqn3uoJNfwu"
	"zbbTTuAbH525P1vgB6+1sl5xkRmNrs09/EX33+bVlmhn3hJ9cjxuOveZ8bNjDu22OL77m1lEI3YW0uwfE5xIgrJ1124eECQYKQzNQ3nb5gul/ExOsuhk"
	"N20ePjdLIYwROqVP+43M0dn2e3iByCX51DMLvK1hekGLGUeeE7VcyumnOTTC+KUtzSljarPaU4njCBAGWvw7BCCw5ruLK9CjyydTPfIvwLIDwnja3Ffe"
	"GFeek37yxqja3FPeGBed+83d42tz7fw2dY2PI1R9S3noTjm5U9DYIrZ4SbHg1C0cDROpqHhMaBcSFrtaKbTm829kkfYqGdCOdLlcN6Y8J4pv8GTIs0mX"
	"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"
	"rYK+Ffw/ClAWiw=="
)
# LITERE-SFARSIT


class Litere(object):
	def __init__(self):
		self.lat = LITERE_LATIME
		self.inalt = LITERE_INALTIME
		date = zlib.decompress(binascii.a2b_base64("".join(LITERE_DATE)))
		pe_rand = (self.lat + 3) // 4
		pe_litera = pe_rand * self.inalt
		self.index = {}
		i = 0
		for a, b in LITERE_INTERVALE:
			for p in range(a, b + 1):
				self.index[p] = i
				i += 1
		self.date = date
		self.pe_rand = pe_rand
		self.pe_litera = pe_litera
		self.cache = {}

	def randuri(self, c, marire=1):
		"""randurile literei c, marite: o lista de inalt*marire siruri de octeti 0..3, fiecare de lat*marire"""
		cheie = (c, marire)
		r = self.cache.get(cheie)
		if r is not None:
			return r
		i = self.index.get(ord(c))
		if i is None:
			i = self.index.get(ord("?"), 0)
		baza = i * self.pe_litera
		r = []
		for y in range(self.inalt):
			o = self.date[baza + y * self.pe_rand: baza + (y + 1) * self.pe_rand]
			rand = bytes((o[x // 4] >> (2 * (x % 4))) & 3 for x in range(self.lat))
			if marire > 1:
				rand = bytes(v for v in rand for _ in range(marire))
				r.extend([rand] * marire)
			else:
				r.append(rand)
		self.cache[cheie] = r
		return r

	def are(self, c):
		return ord(c) in self.index


def potrivesteText(text, maxim):
	"""textul pe randuri de cel mult maxim semne, rupt la spatii"""
	cuvinte = text.split()
	randuri, rand = [], ""
	for c in cuvinte:
		while len(c) > maxim:
			if rand:
				randuri.append(rand)
				rand = ""
			randuri.append(c[:maxim])
			c = c[maxim:]
		if not rand:
			rand = c
		elif len(rand) + 1 + len(c) <= maxim:
			rand += " " + c
		else:
			randuri.append(rand)
			rand = c
	if rand:
		randuri.append(rand)
	return randuri


# ---------------------------------------------------------------- ecranul

FBIOGET_VSCREENINFO = 0x4600
FBIOGET_FSCREENINFO = 0x4602
FBIOBLANK = 0x4611


class Geometrie(object):
	def __init__(self, xres, yres, bpp, stride=0, xoff=0, yoff=0, culori=None):
		self.xres, self.yres, self.bpp = xres, yres, bpp
		self.octeti = bpp // 8
		self.stride = stride or xres * self.octeti
		self.xoff, self.yoff = xoff, yoff
		# (offset, lungime) pentru rosu, verde, albastru, alfa
		if culori is None:
			culori = ((11, 5), (5, 6), (0, 5), (0, 0)) if bpp == 16 else ((16, 8), (8, 8), (0, 8), (24, 8))
		self.culori = culori

	def pixel(self, rgb):
		v = 0
		for (off, lung), c in zip(self.culori, tuple(rgb) + (255,)):
			if lung:
				v |= (c >> (8 - lung)) << off
		return v

	def text(self):
		return "%dx%d %d biti, rand %d, pagina %d" % (self.xres, self.yres, self.bpp, self.stride, self.yoff)


def citesteGeometrie(fd, cale, rezerva):
	try:
		import fcntl
		var = bytearray(160)
		fcntl.ioctl(fd, FBIOGET_VSCREENINFO, var, True)
		c = struct.unpack_from("40I", bytes(var))
		xres, yres, xvirt, yvirt, xoff, yoff, bpp = c[0:7]
		culori = ((c[8], c[9]), (c[11], c[12]), (c[14], c[15]), (c[17], c[18]))
		stride = 0
		try:
			fix = bytearray(80)
			fcntl.ioctl(fd, FBIOGET_FSCREENINFO, fix, True)
			lung = struct.calcsize("L")
			off = 16 + lung + 4 * 4 + 2 * 3
			off += (-off) % 4
			stride = struct.unpack_from("I", bytes(fix), off)[0]
		except (IOError, OSError):
			pass
		try:
			nume = os.path.basename(os.path.realpath(cale))
			with open("/sys/class/graphics/%s/stride" % nume) as f:
				stride = int(f.read().strip()) or stride
		except (IOError, OSError, ValueError):
			pass
		if xres and yres and bpp in (16, 32):
			return Geometrie(xres, yres, bpp, stride, xoff, yoff, culori)
	except (ImportError, IOError, OSError, struct.error):
		pass
	return rezerva


def compune(geom, randuri_ecran, litere):
	"""imaginea intreaga (pagina vazuta), ca bytearray de stride*yres"""
	o = geom.octeti
	fundal = geom.pixel(CULORI["fundal"]).to_bytes(4, "little")[:o]
	rand_fundal = fundal * geom.xres + b"\0" * (geom.stride - geom.xres * o)
	img = bytearray(rand_fundal * geom.yres)
	marg_x = max(16, geom.xres // 24)
	y = max(16, geom.yres // 20)
	for text, marire, culoare in randuri_ecran:
		h = litere.inalt * marire
		if text is None:
			y += h // 2
			continue
		if y + h > geom.yres - 8:
			break
		maxim = (geom.xres - 2 * marg_x) // (litere.lat * marire)
		text = text[:maxim]
		# tabelele treptelor 0..3 -> octetul k al pixelului (fundal, doua amestecuri, culoarea)
		pixeli = []
		for v in range(4):
			c = tuple(CULORI["fundal"][i] + (culoare[i] - CULORI["fundal"][i]) * v // 3 for i in range(3))
			pixeli.append(geom.pixel(c).to_bytes(4, "little"))
		tabele = []
		for k in range(o):
			t = bytearray(256)
			for v in range(4):
				t[v] = pixeli[v][k]
			tabele.append(bytes(t))
		glife = [litere.randuri(c, marire) for c in text]
		for r in range(h):
			acoperire = b"".join(g[r] for g in glife)
			px = bytearray(len(acoperire) * o)
			for k in range(o):
				px[k::o] = acoperire.translate(tabele[k])
			inceput = (y + r) * geom.stride + marg_x * o
			img[inceput:inceput + len(px)] = px
		y += h + 4 * marire
	return img


def randuriEcran(date, t, litere, coloane):
	"""(text, marire, culoare) de sus in jos; None = o jumatate de rand liber"""
	cod = date.get("cod", "")
	coduri = (date.get("coduri") or cod).split()
	# o limba cu litere fara desen (nu e cazul celor 13) trece pe engleza, numai pe ecran
	r = [(t.get(grupa(cod), ""), 1, CULORI["titlu"]), (cod, 3, CULORI["cod"])]
	if len(coduri) > 1:
		r.append(("%s %s" % (t.get("coduri", ""), " ".join(coduri)), 1, CULORI["gri"]))
	for rand in potrivesteText(frazaCod(cod, t), coloane):
		r.append((rand, 1, CULORI["text"]))
	r.append((None, 1, None))
	for rand in potrivesteText(t.get("rugaminte", ""), coloane):
		r.append((rand, 1, CULORI["text"]))
	r.append((FORUM + "   " + EMAIL, 1, CULORI["adresa"]))
	a = adresa(date)
	if a:
		r.append((None, 1, None))
		for rand in potrivesteText(t.get("pagina", ""), coloane):
			r.append((rand, 1, CULORI["text"]))
		r.append((a, 2, CULORI["adresa"]))
	r.append((reincercare(t, date), 1, CULORI["gri"]))
	r.append((None, 1, None))
	for rand in randuriTehnice(date):
		r.append((rand, 1, CULORI["gri"]))
	return r


def deseneaza(cale_fb, date, t, t_en, geometrie_ceruta):
	litere = Litere()
	text_tot = "".join(v for v in t.values() if isinstance(v, str))
	if any(not litere.are(c) for c in text_tot if c >= " "):
		t = t_en
	fd = os.open(cale_fb, os.O_RDWR)
	try:
		geom = citesteGeometrie(fd, cale_fb, geometrie_ceruta)
		try:
			import fcntl
			fcntl.ioctl(fd, FBIOBLANK, 0)
		except (ImportError, IOError, OSError):
			pass
		coloane = (geom.xres - 2 * max(16, geom.xres // 24)) // litere.lat
		randuri = randuriEcran(date, t, litere, coloane)
		if geom.yres < 800:
			# 720p: codul de doua ori, nu de trei, fara randurile goale si fara randul reincercarii, ca sa incapa
			# randurile tehnice
			fara = reincercare(t, date)
			randuri = [(a, 2 if m == 3 else m, c) for a, m, c in randuri if a is not None and a != fara]
		img = compune(geom, randuri, litere)
		os.lseek(fd, geom.yoff * geom.stride + geom.xoff * geom.octeti, 0)
		scris = 0
		while scris < len(img):
			n = os.write(fd, img[scris:scris + 1048576])
			if n <= 0:
				break
			scris += n
		return geom, scris
	finally:
		os.close(fd)


# ---------------------------------------------------------------- pornirea

def argumente(argv):
	a = {"--date": "", "--dosar": "", "--python": "", "--fb": "", "--jurnal": "", "--geometrie": ""}
	fara_fb = False
	i = 0
	while i < len(argv):
		if argv[i] == "--fara-fb":
			fara_fb = True
		elif argv[i] in a and i + 1 < len(argv):
			a[argv[i]] = argv[i + 1]
			i += 1
		i += 1
	return a, fara_fb


def main(argv):
	a, fara_fb = argumente(argv)
	date = citesteDate(a["--date"])
	if not date.get("cod"):
		print("fara cod in %s" % a["--date"])
		return 1
	texte_diag = texteDiagnostic(a["--python"])
	limba = alegeLimba(date, texte_diag)
	t = texte(limba, texte_diag)
	t_en = texte("en", texte_diag) if limba != "en" else t
	jurnal = jurnalCaderi(a["--jurnal"]) if a["--jurnal"] else []
	if a["--dosar"]:
		try:
			scriePagina(a["--dosar"], date, t, t_en, jurnal)
			print("pagina scrisa (%s)" % limba)
		except (IOError, OSError) as e:
			print("pagina nu s-a scris: %s" % e)
	if fara_fb or not a["--fb"]:
		return 0
	if not os.path.exists(a["--fb"]):
		print("fara %s" % a["--fb"])
		return 0
	rezerva = Geometrie(1280, 720, 32)
	if a["--geometrie"]:
		try:
			l, i, b = (int(x) for x in a["--geometrie"].lower().split("x"))
			rezerva = Geometrie(l, i, b)
		except ValueError:
			pass
	try:
		geom, scris = deseneaza(a["--fb"], date, t, t_en, rezerva)
		print("imaginea pe %s: %s, %d octeti" % (a["--fb"], geom.text(), scris))
	except (IOError, OSError) as e:
		print("imaginea nu s-a desenat: %s" % e)
		return 1
	return 0


if __name__ == "__main__":
	sys.exit(main(sys.argv[1:]))
