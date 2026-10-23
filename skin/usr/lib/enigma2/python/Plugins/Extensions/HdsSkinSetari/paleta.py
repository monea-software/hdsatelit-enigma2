# -*- coding: utf-8 -*-
# Copyright (C) 2026 Monea Software pentru HD Satelit (https://hdsatelit.com, contact@moneasoftware.com)
# Licenta: GNU GPL versiunea 2. HDS-MARCA: skin HDSatelit, Monea Software pentru HD Satelit, 2026
#
# Paletele skinului HDSatelit: rolurile de culoare, derivarea unei palete din cateva culori de baza,
# contrastul (formula WCAG, panoul translucid peste video alb si peste video negru), scrierea sigura
# a blocului <colors> din skin.xml si fisierul cu alegerea utilizatorului.
# Fara importuri din enigma: acelasi cod ruleaza pe PC (tools\fa_palete.py, teste) si pe receptor.
# Merge pe Python 2.7 si 3.x.
from __future__ import division

import io
import os
import re

SKIN_XML = "/usr/share/enigma2/HDSatelit/skin.xml"
CONF = "/etc/enigma2/hdsatelit-culori.conf"
ORIGINAL = "/etc/enigma2/hdsatelit-culori-original.txt"
PALETE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "palete.txt")
ID_IMPLICIT = "implicit"
CITIRE_INCEPUT = 65536

# ---------------------------------------------------------------- rolurile
# (nume, valoare implicita #AARRGGBB, fel): fel "panou" = alfa reglabila; "strat" = alfa din paleta; "culoare" = opac
# Toate 36 sunt exact blocul <colors> din skin.xml, in aceeasi ordine. Ultimele 6 erau culori scrise direct
# in skin.xml (windowstyle, inregistrare in grilele EPG) si au devenit nume, ca rescrierea blocului sa le schimbe si pe ele.
ROLURI = (
	("transparent", 0xFF000000, "fix"),
	("black", 0x00000000, "fix"),
	("white", 0x00FFFFFF, "fix"),
	("hdsPanel", 0x2610162A, "panou"),
	("hdsPanelSolid", 0x0010162A, "panou"),
	("hdsPanelDialog", 0x0D10162A, "panou"),
	("hdsPanelSoft", 0x6610162A, "panou"),
	("hdsDim", 0x59000000, "strat"),
	("hdsLine", 0x99FFFFFF, "strat"),
	("hdsDivider", 0xD9FFFFFF, "strat"),
	("hdsText", 0x00F2F4F8, "culoare"),
	("hdsText2", 0x00C9D2E3, "culoare"),
	("hdsLabel", 0x00AEB9CC, "culoare"),
	("hdsBrand", 0x00374EA1, "culoare"),
	("hdsBrandLight", 0x009FB4FF, "culoare"),
	("hdsAmber", 0x00F5B83D, "culoare"),
	("hdsGood", 0x004FD18B, "culoare"),
	("hdsWarn", 0x00F1C40F, "culoare"),
	("hdsBad", 0x00FF6B5E, "culoare"),
	("hdsTrack", 0x002A3350, "culoare"),
	("hdsCell", 0x00282D3F, "culoare"),
	("hdsCellNow", 0x00404555, "culoare"),
	("hdsDisabled", 0x00667085, "culoare"),
	("key_red", 0x00E5484D, "culoare"),
	("key_green", 0x0046B06A, "culoare"),
	("key_yellow", 0x00E8B93A, "culoare"),
	("key_blue", 0x003D7BE0, "culoare"),
	("key_text", 0x00F2F4F8, "culoare"),
	("key_back", 0x002A3350, "culoare"),
	("hdsSelText", 0x00FFFFFF, "culoare"),
	("hdsMarked", 0x00F5B83D, "culoare"),
	("hdsMarkedText", 0x0010162A, "culoare"),
	("hdsMarkedSel", 0x00C98F1E, "culoare"),
	("hdsRec", 0x00B83A32, "culoare"),
	("hdsRecSel", 0x00D9483F, "culoare"),
	# 0.3.0 (marunte-030): fundalul ecranului radio pe tot ecranul (Screens/HdsEcranRadio.py), fix: aceeasi valoare ca
	# HdsRadioDesen.FUNDAL, panza barelor, deci nu se schimba cu paleta (altfel barele ar sta intr-un dreptunghi)
	("hdsRadioBack", 0x000A0F1A, "fix"),
)
NUME_ROLURI = tuple([r[0] for r in ROLURI])
FEL = dict([(r[0], r[2]) for r in ROLURI])
IMPLICIT = dict([(r[0], r[1]) for r in ROLURI])
# rolurile pe care utilizatorul le poate schimba de mana (fara transparent/black/white)
EDITABILE = tuple([r[0] for r in ROLURI if r[2] != "fix"])
COMENTARIU_CELULE = "celulele grilelor EPG: opace (umplerea listei scrie alfa in cadru, nu amesteca; cu alfa se vede TV-ul prin grila)"

# transparenta panourilor cu text: design.md 3, minim 80% opacitate sub text
ALFA_PANOU = ((0x33, 80), (0x26, 85), (0x1A, 90), (0x0D, 95), (0x00, 100))
ALFA_IMPLICIT = 0x26
# pagina tehnica (a doua bara): 0 = manual, doar cu stanga / dreapta (implicit din 24.09.2026); altfel secundele de rotire
PAGINA_SECUNDE = (0, 4, 5, 6, 7, 8, 10, 12, 15, 20)
PAGINA_IMPLICIT = 0
# panoul de dinainte de 24.09.2026 scria `pagina=7` (implicitul de atunci) in orice .conf salvat, si cand nu alesese
# nimeni timpul; deci `pagina=7` se citeste ca implicit. Alegerea se scrie acum ca `rotire=` (citit si de HdsCommon.py).
PAGINA_VECHE_IMPLICIT = 7
# afisajul detaliat (a doua bara, pagina tehnica): "tot" = pe tot ecranul (implicit din 24.09.2026), "fereastra" = sus,
# 1776x624, ca inainte. Se aplica schimband numele ecranelor in skin.xml (schimba_afisaj), vezi mai jos.
AFISAJE = ("tot", "fereastra")
AFISAJ_IMPLICIT = "tot"

# pragurile de contrast (design.md 3 si 6.2): (rol text, rol fundal, prag)
# fundal "PANOU" = hdsPanel translucid peste video alb si peste video negru, minimul celor doua
PRAGURI = (
	("hdsText", "PANOU", 7.0),
	("hdsText2", "PANOU", 4.5),
	("hdsLabel", "PANOU", 4.5),
	("hdsBrandLight", "PANOU", 4.5),
	("hdsAmber", "PANOU", 4.5),
	("hdsGood", "PANOU", 4.5),
	("hdsWarn", "PANOU", 4.5),
	("hdsBad", "PANOU", 3.0),
	("hdsSelText", "hdsBrand", 4.5),
	("white", "hdsBrand", 4.5),  # skin.xml si imaginile pun text alb pe selectie
	("hdsText", "hdsCellNow", 4.5),
	("hdsText2", "hdsCell", 4.5),
	("key_text", "key_back", 4.5),
	("hdsMarkedText", "hdsMarked", 4.5),
)


# ---------------------------------------------------------------- culori
def _rot(x):
	"""Rotunjire la fel pe Python 2 si 3 (round din py3 rotunjeste .5 la par)."""
	return int(x + 0.5) if x >= 0 else -int(-x + 0.5)


def argb(a, r, g, b):
	return ((int(a) & 255) << 24) | ((int(r) & 255) << 16) | ((int(g) & 255) << 8) | (int(b) & 255)


def parti(v):
	return (v >> 24) & 255, (v >> 16) & 255, (v >> 8) & 255, v & 255


def hexa(v):
	return "#%08X" % (int(v) & 0xFFFFFFFF)


_RE_CULOARE = re.compile(r"^#?([0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})$")


def citeste_culoare(s):
	"""'#AARRGGBB', '#RRGGBB', 'AARRGGBB' sau 'RRGGBB' -> int; None daca nu e valida."""
	try:
		m = _RE_CULOARE.match(s.strip())
	except Exception:
		return None
	if not m:
		return None
	h = m.group(1)
	if len(h) == 6:
		h = "00" + h
	return int(h, 16)


def _lin(c):
	c = c / 255.0
	if c <= 0.03928:
		return c / 12.92
	return ((c + 0.055) / 1.055) ** 2.4


def luminanta(r, g, b):
	return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def raport(c1, c2):
	"""Contrastul WCAG intre doua culori opace (int, alfa ignorata)."""
	_, r1, g1, b1 = parti(c1)
	_, r2, g2, b2 = parti(c2)
	l1 = luminanta(r1, g1, b1)
	l2 = luminanta(r2, g2, b2)
	if l1 < l2:
		l1, l2 = l2, l1
	return (l1 + 0.05) / (l2 + 0.05)


def peste(panou, video):
	"""Panoul (alfa enigma2: 00 opac, FF transparent) amestecat peste o culoare opaca, ca in enigma2."""
	a, r, g, b = parti(panou)
	_, vr, vg, vb = parti(video)
	o = (255 - a) / 255.0
	return argb(0, _rot(r * o + vr * (1 - o)), _rot(g * o + vg * (1 - o)), _rot(b * o + vb * (1 - o)))


def contrast_panou(culoare, panou):
	"""Minimul contrastului peste video alb si peste video negru."""
	return min(raport(culoare, peste(panou, 0x00FFFFFF)), raport(culoare, peste(panou, 0x00000000)))


def verifica(pal):
	"""Lista (text, fundal, raport, prag) pentru fiecare regula; ok = toate peste prag."""
	rez = []
	for text, fundal, prag in PRAGURI:
		if fundal == "PANOU":
			r = contrast_panou(pal[text], pal["hdsPanel"])
		else:
			r = raport(pal[text], pal[fundal])
		rez.append((text, fundal, r, prag))
	return rez


def cade(pal):
	"""Regulile care nu trec pragul."""
	return [x for x in verifica(pal) if x[2] + 1e-9 < x[3]]


# ---------------------------------------------------------------- HSL, fara colorsys (rotunjire identica pe py2 si py3)
def hsl_rgb(h, s, l):
	h = (h % 360) / 360.0
	if s <= 0:
		v = int(_rot(l * 255))
		return v, v, v
	q = l * (1 + s) if l < 0.5 else l + s - l * s
	p = 2 * l - q

	def canal(t):
		if t < 0:
			t += 1
		if t > 1:
			t -= 1
		if t < 1 / 6.0:
			return p + (q - p) * 6 * t
		if t < 0.5:
			return q
		if t < 2 / 3.0:
			return p + (q - p) * (2 / 3.0 - t) * 6
		return p

	return (int(_rot(canal(h + 1 / 3.0) * 255)), int(_rot(canal(h) * 255)), int(_rot(canal(h - 1 / 3.0) * 255)))


def hsl(h, s, l, a=0):
	r, g, b = hsl_rgb(h, max(0.0, min(1.0, s)), max(0.0, min(1.0, l)))
	return argb(a, r, g, b)


def amesteca(c1, c2, t, a=0):
	"""c1 spre c2 cu fractia t (0 = c1), alfa a."""
	_, r1, g1, b1 = parti(c1)
	_, r2, g2, b2 = parti(c2)
	return argb(a, _rot(r1 + (r2 - r1) * t), _rot(g1 + (g2 - g1) * t), _rot(b1 + (b2 - b1) * t))


def cu_alfa(c, a):
	return (int(c) & 0x00FFFFFF) | ((int(a) & 255) << 24)


# ---------------------------------------------------------------- derivarea
# Culorile de baza ale unei palete (ordinea din palete.txt):
BAZA = ("mod", "panou", "text", "brand", "brandL", "amber", "good", "warn", "bad", "taste")
TASTE = {
	"n": (0x00E5484D, 0x0046B06A, 0x00E8B93A, 0x003D7BE0),  # obisnuite (cele de azi)
	"d": (0x00D55E00, 0x00009E73, 0x00F0E442, 0x000072B2),  # Okabe-Ito, sigure la daltonism
	"l": (0x00C62828, 0x002E7D32, 0x00B8860B, 0x001565C0),  # pentru panou luminos
}


def _ajusteaza(c, fundal_fn, prag, spre):
	"""Muta culoarea c spre `spre` (alb sau negru) in pasi mici pana trece pragul; cel mult 12 pasi."""
	for i in range(13):
		if fundal_fn(c) >= prag:
			return c
		c = amesteca(c, spre, 0.12)
	return c


def deriva(baza, alfa=ALFA_IMPLICIT):
	"""Paleta intreaga (dict rol -> int) din culorile de baza. Deterministic."""
	mod = baza["mod"]  # "d" intunecat, "l" luminos
	panou = baza["panou"] & 0x00FFFFFF
	text = baza["text"] & 0x00FFFFFF
	luminos = mod == "l"
	spre_text = 0x00000000 if luminos else 0x00FFFFFF
	p = dict(IMPLICIT)
	p["hdsPanel"] = cu_alfa(panou, alfa)
	p["hdsPanelSolid"] = cu_alfa(panou, 0x00)
	p["hdsPanelDialog"] = cu_alfa(panou, 0x0D)
	p["hdsPanelSoft"] = cu_alfa(panou, 0x66)
	p["hdsDim"] = 0x59000000
	p["hdsLine"] = 0xB3000000 if luminos else 0x99FFFFFF
	p["hdsDivider"] = 0xE0000000 if luminos else 0xD9FFFFFF
	pan = p["hdsPanel"]

	def pe_panou(c):
		return contrast_panou(c, pan)

	p["hdsText"] = _ajusteaza(text, pe_panou, 7.0, spre_text)
	p["hdsText2"] = _ajusteaza(amesteca(text, panou, 0.17), pe_panou, 4.8, spre_text)
	p["hdsLabel"] = _ajusteaza(amesteca(text, panou, 0.27), pe_panou, 4.8, spre_text)
	for rol, cheie, prag in (("hdsBrandLight", "brandL", 4.8), ("hdsAmber", "amber", 4.8), ("hdsGood", "good", 4.8),
			("hdsWarn", "warn", 4.8), ("hdsBad", "bad", 3.2)):
		p[rol] = _ajusteaza(baza[cheie] & 0x00FFFFFF, pe_panou, prag, spre_text)
	brand = baza["brand"] & 0x00FFFFFF
	# bara de selectie: textul ALB trebuie sa se citeasca pe ea (skin.xml si ecranele imaginii pun text alb pe
	# selectie, nu hdsSelText); brandul se inchide in pasi mici pana ajunge la 4,8:1
	for i in range(16):
		if raport(0x00FFFFFF, brand) >= 4.8:
			break
		brand = amesteca(brand, 0x00000000, 0.08)
	alb_pe = raport(0x00FFFFFF, brand)
	negru_pe = raport(0x00101010, brand)
	p["hdsBrand"] = brand
	p["hdsSelText"] = 0x00FFFFFF if alb_pe >= negru_pe else 0x00101010
	p["hdsTrack"] = amesteca(panou, text, 0.12)
	p["hdsCell"] = amesteca(panou, text, 0.09)
	p["hdsCellNow"] = amesteca(panou, text, 0.19)
	p["hdsDisabled"] = amesteca(panou, text, 0.40)
	# textul pe celule: celula mai spre panou daca nu trece
	for i in range(6):
		if raport(p["hdsText"], p["hdsCellNow"]) >= 4.8:
			break
		p["hdsCellNow"] = amesteca(p["hdsCellNow"], panou, 0.3)
	for i in range(6):
		if raport(p["hdsText2"], p["hdsCell"]) >= 4.8:
			break
		p["hdsCell"] = amesteca(p["hdsCell"], panou, 0.3)
	kr, kg, ky, kb = TASTE.get(baza.get("taste", "n"), TASTE["n"])
	p["key_red"], p["key_green"], p["key_yellow"], p["key_blue"] = kr, kg, ky, kb
	p["key_text"] = p["hdsText"]
	p["key_back"] = p["hdsTrack"]
	p["hdsMarked"] = p["hdsAmber"]
	p["hdsMarkedText"] = 0x00101010 if raport(0x00101010, p["hdsMarked"]) >= raport(0x00FFFFFF, p["hdsMarked"]) else 0x00FFFFFF
	p["hdsMarkedSel"] = amesteca(p["hdsMarked"], 0x00000000, 0.18)
	p["hdsRec"] = amesteca(p["hdsBad"], 0x00000000, 0.28)
	p["hdsRecSel"] = amesteca(p["hdsBad"], 0x00000000, 0.12)
	return p


def implicita(alfa=ALFA_IMPLICIT):
	p = dict(IMPLICIT)
	p["hdsPanel"] = cu_alfa(p["hdsPanel"], alfa)
	return p


# ---------------------------------------------------------------- palete.txt
# Format: un rand pe paleta, campuri separate prin "|":
#   id|familie|mod|panou|text|brand|brandL|amber|good|warn|bad|taste   (culorile RRGGBB, fara #)
# Randurile care incep cu "#" sunt comentarii.
def citeste_palete(cale=None):
	"""Lista de (id, familie, baza). Randurile stricate se sar. Paleta implicita e mereu prima."""
	cale = cale or PALETE
	rez = [(ID_IMPLICIT, "implicit", None)]
	vazute = set([ID_IMPLICIT])
	try:
		with io.open(cale, "r", encoding="utf-8") as f:
			for rand in f:
				rand = rand.strip()
				if not rand or rand.startswith("#"):
					continue
				c = rand.split("|")
				if len(c) != 12 or c[0] in vazute or c[2] not in ("d", "l"):
					continue
				culori = [citeste_culoare(x) for x in c[3:11]]
				if None in culori:
					continue
				baza = {"mod": c[2], "taste": c[11] if c[11] in TASTE else "n"}
				for k, v in zip(BAZA[1:9], culori):
					baza[k] = v
				rez.append((c[0], c[1], baza))
				vazute.add(c[0])
	except Exception:
		pass
	return rez


def rand_paleta(pid, familie, baza):
	return "|".join([pid, familie, baza["mod"]] + ["%06X" % (baza[k] & 0xFFFFFF) for k in BAZA[1:9]] + [baza.get("taste", "n")])


def paleta_dupa_id(pid, palete=None, alfa=ALFA_IMPLICIT):
	if pid == ID_IMPLICIT or not pid:
		return implicita(alfa)
	for x in (palete if palete is not None else citeste_palete()):
		if x[0] == pid and x[2] is not None:
			return deriva(x[2], alfa)
	return None


# ---------------------------------------------------------------- alegerea utilizatorului (.conf)
def conf_implicit():
	return {"paleta": ID_IMPLICIT, "alfa": ALFA_IMPLICIT, "pagina": PAGINA_IMPLICIT, "afisaj": AFISAJ_IMPLICIT, "roluri": {}}


def citeste_conf(cale=None):
	cale = cale or CONF
	c = conf_implicit()
	rotire = False
	try:
		with io.open(cale, "r", encoding="utf-8") as f:
			for rand in f:
				rand = rand.strip()
				if not rand or rand.startswith("#") or "=" not in rand:
					continue
				k, v = rand.split("=", 1)
				k = k.strip()
				v = v.strip()
				if k == "paleta":
					if re.match(r"^[a-z0-9-]{1,40}$", v):
						c["paleta"] = v
				elif k == "alfa":
					try:
						a = int(v, 16)
						if a in [x[0] for x in ALFA_PANOU]:
							c["alfa"] = a
					except ValueError:
						pass
				elif k == "afisaj":
					if v in AFISAJE:
						c["afisaj"] = v
				elif k in ("rotire", "pagina"):
					# `rotire=` are prioritate; `pagina=` (scris inainte de 24.09.2026) doar cand lipseste
					try:
						n = int(v)
					except ValueError:
						continue
					if k == "pagina" and n == PAGINA_VECHE_IMPLICIT:
						n = PAGINA_IMPLICIT
					if n in PAGINA_SECUNDE and (k == "rotire" or not rotire):
						c["pagina"] = n
						rotire = rotire or k == "rotire"
				elif k in EDITABILE:
					val = citeste_culoare(v)
					if val is not None:
						c["roluri"][k] = val
	except Exception:
		pass
	return c


def text_conf(c):
	randuri = ["# HDSatelit: culorile alese in HdsSkinSetari. Se poate sterge: skinul revine la culorile implicite.",
		"paleta=%s" % c["paleta"], "alfa=%02X" % c["alfa"], "rotire=%d" % c["pagina"], "afisaj=%s" % c.get("afisaj", AFISAJ_IMPLICIT)]
	for rol in EDITABILE:
		if rol in c["roluri"]:
			randuri.append("%s=%s" % (rol, hexa(c["roluri"][rol])))
	return "\n".join(randuri) + "\n"


def paleta_din_conf(c, palete=None):
	"""Paleta finala: paleta aleasa (sau implicita daca id-ul nu mai exista) + culorile puse de mana."""
	p = paleta_dupa_id(c["paleta"], palete, c["alfa"])
	if p is None:
		p = implicita(c["alfa"])
	for rol, v in c["roluri"].items():
		if rol in p:
			p[rol] = v
	return p


def amprenta(pal):
	"""Suma scurta a culorilor, scrisa in semnul din <colors>: pornirea stie daca skin.xml e la zi."""
	s = 0
	for i, rol in enumerate(NUME_ROLURI):
		s = (s * 31 + (pal[rol] & 0xFFFFFFFF) + i) % 4294967291
	return "%08x" % s


# ---------------------------------------------------------------- blocul <colors>
_RE_SEMN = re.compile(br"<!-- hds-paleta: ([a-z0-9-]{1,40}) ([0-9a-f]{8}) -->")


def bloc_culori(pal, pid, nl="\n"):
	"""Textul blocului, de la <colors> la </colors> inclusiv (bytes utf-8)."""
	r = ["<colors>", "\t\t<!-- hds-paleta: %s %s -->" % (pid, amprenta(pal))]
	for rol in NUME_ROLURI:
		if rol == "hdsCell":
			r.append("\t\t<!-- %s -->" % COMENTARIU_CELULE)
		r.append('\t\t<color name="%s" value="%s" />' % (rol, hexa(pal[rol])))
	r.append("\t</colors>")
	return nl.join(r).encode("utf-8")


def gaseste_bloc(date):
	"""(inceput, sfarsit) al blocului <colors>...</colors> in octeti; None daca nu e exact unul."""
	if date.count(b"<colors>") != 1 or date.count(b"</colors>") != 1:
		return None
	i = date.find(b"<colors>")
	j = date.find(b"</colors>")
	if j < i:
		return None
	return i, j + len(b"</colors>")


def valideaza_bloc(bloc):
	"""Blocul trebuie sa fie XML bun, cu toate rolurile si valori valide. Intoarce mesajul de eroare sau None."""
	try:
		import xml.etree.ElementTree as ET
		rad = ET.fromstring(b"<skin>" + bloc + b"</skin>")
	except Exception as e:
		return "xml: %s" % e
	nume = {}
	for c in rad.findall("colors/color"):
		n = c.attrib.get("name")
		v = c.attrib.get("value", "")
		if not n or not re.match(r"^#[0-9A-F]{8}$", v):
			return "culoare gresita: %s=%s" % (n, v)
		nume[n] = v
	lipsa = [r for r in NUME_ROLURI if r not in nume]
	if lipsa:
		return "lipsesc: %s" % ",".join(lipsa)
	return None


def semn_din_skin(cale=None):
	"""(id, amprenta) din primii 64 kB ai skin.xml; (None, None) daca nu are semn (pachet nou) sau nu se poate citi."""
	cale = cale or SKIN_XML
	try:
		with open(cale, "rb") as f:
			m = _RE_SEMN.search(f.read(CITIRE_INCEPUT))
		if m:
			return m.group(1).decode("ascii"), m.group(2).decode("ascii")
	except Exception:
		pass
	return None, None


class EroareScriere(Exception):
	pass


def _scrie_atomic(cale, date):
	tmp = cale + ".hds-nou"
	try:
		with open(tmp, "wb") as f:
			f.write(date)
			f.flush()
			try:
				os.fsync(f.fileno())
			except Exception:
				pass
		with open(tmp, "rb") as f:
			if f.read() != date:
				raise EroareScriere("citire inapoi diferita")
		if os.name == "nt" and os.path.exists(cale):
			os.remove(cale)  # doar la probele pe PC: pe Windows rename nu inlocuieste; pe receptor (Linux) rename e atomic
		os.rename(tmp, cale)
	except Exception:
		try:
			os.remove(tmp)
		except Exception:
			pass
		raise


def scrie_skin(pal, pid, cale=None, original=None):
	"""Inlocuieste blocul <colors> din skin.xml. Nu atinge alt octet. Ridica EroareScriere cu motivul."""
	cale = cale or SKIN_XML
	original = ORIGINAL if original is None else original
	try:
		with open(cale, "rb") as f:
			date = f.read()
	except Exception as e:
		raise EroareScriere("nu pot citi skin.xml: %s" % e)
	poz = gaseste_bloc(date)
	if poz is None:
		raise EroareScriere("skin.xml nu are exact un bloc <colors>")
	i, j = poz
	nl = "\r\n" if b"\r\n" in date[:i + 200] else "\n"
	bloc = bloc_culori(pal, pid, nl)
	err = valideaza_bloc(bloc)
	if err:
		raise EroareScriere("bloc invalid: %s" % err)
	nou = date[:i] + bloc + date[j:]
	# fondurile dalelor (meniul cu dale) au culorile paletei: se scriu odata cu blocul, iar cand blocul e deja la zi
	# numai cele care lipsesc; o greseala aici nu opreste paleta
	try:
		scrie_dale(pal, os.path.dirname(cale), doar_lipsa=(nou == date))
	except Exception:
		pass
	if nou == date:
		return False
	# textul original al blocului, o singura data (cativa kB), ca sa se poata compara la nevoie
	if original and not os.path.exists(original) and _RE_SEMN.search(date[i:j]) is None:
		try:
			_scrie_atomic(original, date[i:j])
		except Exception:
			pass
	try:
		_scrie_atomic(cale, nou)
	except EroareScriere:
		raise
	except Exception as e:
		raise EroareScriere("nu pot scrie in %s: %s" % (os.path.dirname(cale), e))
	return True


def scrie_conf(c, cale=None):
	cale = cale or CONF
	try:
		_scrie_atomic(cale, text_conf(c).encode("utf-8"))
	except Exception as e:
		raise EroareScriere("nu pot scrie %s: %s" % (cale, e))


def skin_la_zi(conf=None, cale=None, conf_cale=None):
	"""True daca skin.xml are deja culorile din .conf (sau nu exista .conf si skinul e pe implicit)."""
	c = conf if conf is not None else citeste_conf(conf_cale)
	pid, amp = semn_din_skin(cale)
	if pid is None:
		return c["paleta"] == ID_IMPLICIT and c["alfa"] == ALFA_IMPLICIT and not c["roluri"]
	return amp == amprenta(paleta_din_conf(c))


# ---------------------------------------------------------------- fondurile dalelor (meniul cu dale)
# Meniul cu dale (Screens/Menu.py, Components/HdsDale.py) deseneaza fiecare dala peste o imagine: cartonasul (dala
# normala: putin mai deschis decat panoul, chenar de 1 px hdsTrack) sau dala aleasa (culoarea marcii, chenar hdsBrandLight
# de 4 px, stralucire moale in jur), cu colturi rotunjite. Imaginile au stralucirea in jur (si cea normala, goala), ca
# amandoua sa stea in acelasi loc al sablonului. Se scriu in HDSatelit/meniu/dala/<stare>-<procent>.png pentru fiecare
# treapta a marimii textului; cifrele sunt cele din Components/HdsDale.py (geometrie()), copiate aici ca modulul sa
# ramana fara importuri din imagine (proba test_meniu_dale.py le compara). PNG scris cu zlib si struct (PIL nu e pe
# receptor); numai colturile se socotesc pixel cu pixel, randurile din mijloc se repeta.
DALA_LATIME = 544
DALA_RAZA = 12
# (procentul, inaltimea dalei, stralucirea in jur)
DALA_TREPTE = ((100, 224, 16), (105, 228, 14), (110, 232, 14), (115, 236, 12), (120, 240, 10), (125, 244, 10),
	(130, 248, 8))
DALA_STRALUCIRE = 0.55  # alfa stralucirii langa dala (scade spre 0 la marginea imaginii)


def _png(latime, inaltime, randuri, nivel=6):
	"""PNG RGBA pe 8 biti din randurile date (bytes de latime * 4)."""
	import struct
	import zlib

	def bucata(tip, date):
		c = struct.pack(">I", len(date)) + tip + date
		return c + struct.pack(">I", zlib.crc32(tip + date) & 0xFFFFFFFF)
	brut = b"".join(b"\x00" + r for r in randuri)
	return (b"\x89PNG\r\n\x1a\n" + bucata(b"IHDR", struct.pack(">IIBBBBB", latime, inaltime, 8, 6, 0, 0, 0)) +
		bucata(b"IDAT", zlib.compress(brut, nivel)) + bucata(b"IEND", b""))


def _rgb(c):
	return (c >> 16) & 255, (c >> 8) & 255, c & 255


def _pixel_dala(x, y, w, h, g, fond, chenar, gros, lumina):
	"""(r, g, b, a) al pixelului x, y din imaginea unei dale w x h cu stralucirea g in jur."""
	import math
	px, py = x + 0.5 - g, y + 0.5 - g
	r = DALA_RAZA
	ax = abs(px - w / 2.0) - (w / 2.0 - r)
	ay = abs(py - h / 2.0) - (h / 2.0 - r)
	afara = math.hypot(max(ax, 0.0), max(ay, 0.0))
	d = afara + min(max(ax, ay), 0.0) - r       # distanta la marginea dalei (negativa inauntru)
	acop = max(0.0, min(1.0, 0.5 - d))          # cat din pixel e dala
	inter = max(0.0, min(1.0, 0.5 - (d + gros)))  # cat din pixel e in interiorul chenarului
	sr = sg = sb = 0.0
	for (cr, cg, cb), parte in ((_rgb(fond), inter), (_rgb(chenar), acop - inter)):
		sr += cr * parte
		sg += cg * parte
		sb += cb * parte
	alfa = acop
	if lumina is not None and g > 0 and d > 0 and d < g:
		la = DALA_STRALUCIRE * (1.0 - d / float(g)) ** 2 * (1.0 - acop)
		lr, lg, lb = _rgb(lumina)
		sr += lr * la
		sg += lg * la
		sb += lb * la
		alfa += la
	if alfa <= 0:
		return 0, 0, 0, 0
	return int(sr / alfa + 0.5), int(sg / alfa + 0.5), int(sb / alfa + 0.5), min(255, int(alfa * 255 + 0.5))


def png_dala(pal, aleasa, inaltime, stralucire):
	"""Octetii PNG ai fondului unei dale (normala sau aleasa) cu culorile paletei `pal`."""
	panou, text = pal["hdsPanelSolid"] & 0xFFFFFF, pal["hdsText"] & 0xFFFFFF
	if aleasa:
		fond, chenar, gros, lumina = pal["hdsBrand"] & 0xFFFFFF, pal["hdsBrandLight"] & 0xFFFFFF, 4, pal["hdsBrandLight"] & 0xFFFFFF
	else:
		fond, chenar, gros, lumina = amesteca(panou, text, 0.06) & 0xFFFFFF, pal["hdsTrack"] & 0xFFFFFF, 1, None
	w, h, g = DALA_LATIME, inaltime, stralucire
	W, H = w + 2 * g, h + 2 * g
	colt = g + DALA_RAZA + 2                 # pixelii din fiecare capat de rand care se socotesc unul cate unul
	cache = {}

	def rand(y):
		# randurile dintre colturi (dala si stralucirea de langa ea) sunt la fel: se socotesc o data
		cheie = y if (y < colt or y >= H - colt) else -1
		if cheie in cache:
			return cache[cheie]
		st = bytearray()
		for x in range(colt):
			st.extend(_pixel_dala(x, y, w, h, g, fond, chenar, gros, lumina))
		mijloc = bytearray(_pixel_dala(W // 2, y, w, h, g, fond, chenar, gros, lumina)) * (W - 2 * colt)
		dr = bytearray()
		for x in range(colt - 1, -1, -1):
			dr.extend(st[4 * x:4 * x + 4])
		r = bytes(st + mijloc + dr)
		cache[cheie] = r
		return r
	return _png(W, H, [rand(y) for y in range(H)])


def cale_dala(dosar, stare, procent):
	return os.path.join(dosar, "meniu", "dala", "%s-%d.png" % (stare, procent))


def scrie_dale(pal, dosar=None, doar_lipsa=False):
	"""Fondurile dalelor cu culorile paletei `pal`, in <dosar>/meniu/dala (dosarul lui skin.xml). Cu doar_lipsa numai
	cele care lipsesc. Intoarce cate au fost scrise."""
	dosar = dosar or os.path.dirname(SKIN_XML)
	d = os.path.join(dosar, "meniu", "dala")
	if not os.path.isdir(d):
		os.makedirs(d)
	scrise = 0
	for procent, inaltime, stralucire in DALA_TREPTE:
		for stare, aleasa in (("normala", False), ("aleasa", True)):
			cale = cale_dala(dosar, stare, procent)
			if doar_lipsa and os.path.exists(cale):
				continue
			date = png_dala(pal, aleasa, inaltime, stralucire)
			try:
				with open(cale, "rb") as f:
					if f.read() == date:
						continue
			except (IOError, OSError):
				pass
			_scrie_atomic(cale, date)
			scrise += 1
	return scrise


# ---------------------------------------------------------------- afisajul detaliat: tot ecranul sau fereastra (24.09.2026)
# In skin.xml stau doua ecrane pentru a doua bara: cel pe tot ecranul (1776x1000) si fereastra de sus (1776x624).
# Imaginea deschide ecranul numit „SecondInfoBar”; celalalt poarta un nume pe care nu il cere nimeni
# (HdsSecondInfoBarTotEcranul / HdsSecondInfoBarFereastra). Alegerea schimba doar numele din aceste doua etichete
# <screen ...> si marimea variantelor de nume ale altor imagini (SecondInfoBarECM, SecondInfoBarSimple), care iau
# continutul prin <panel name="SecondInfoBar" />. Niciun alt octet nu se schimba. Recunoasterea e dupa marime,
# nu dupa nume, deci merge si pe un skin.xml schimbat de mana intre timp.
_RX_AFISAJ = re.compile(br'<screen name="(SecondInfoBar|HdsSecondInfoBarFereastra|HdsSecondInfoBarTotEcranul|SecondInfoBarECM|SecondInfoBarSimple)" position="72,40" size="1776,(624|1000)"')
CITIRE_AFISAJ = 262144
_NUME_AFISAJ = {
	("tot", b"1000"): b"SecondInfoBar", ("tot", b"624"): b"HdsSecondInfoBarFereastra",
	("fereastra", b"1000"): b"HdsSecondInfoBarTotEcranul", ("fereastra", b"624"): b"SecondInfoBar",
}


def afisaj_din_skin(date):
	""""tot" / "fereastra" dupa marimea ecranului numit SecondInfoBar; None daca nu se recunoaste (skin vechi)."""
	for m in _RX_AFISAJ.finditer(date):
		if m.group(1) == b"SecondInfoBar":
			return "tot" if m.group(2) == b"1000" else "fereastra"
	return None


def schimba_afisaj(date, alegere):
	"""Octetii skin.xml cu afisajul ales. Ridica EroareScriere daca skinul nu are exact cele doua ecrane."""
	if alegere not in AFISAJE:
		raise EroareScriere("afisaj necunoscut: %s" % alegere)
	marimi = {}
	for m in _RX_AFISAJ.finditer(date):
		if m.group(1) in (b"SecondInfoBarECM", b"SecondInfoBarSimple"):
			continue
		marimi[m.group(2)] = marimi.get(m.group(2), 0) + 1
	if marimi != {b"624": 1, b"1000": 1}:
		raise EroareScriere("skin.xml nu are cele doua ecrane ale paginii tehnice")
	marime_aleasa = b"1000" if alegere == "tot" else b"624"

	def inlocuieste(m):
		nume, marime = m.group(1), m.group(2)
		if nume in (b"SecondInfoBarECM", b"SecondInfoBarSimple"):
			return b'<screen name="%s" position="72,40" size="1776,%s"' % (nume, marime_aleasa)
		return b'<screen name="%s" position="72,40" size="1776,%s"' % (_NUME_AFISAJ[(alegere, marime)], marime)
	nou = _RX_AFISAJ.sub(inlocuieste, date)
	if afisaj_din_skin(nou) != alegere or _bloc_culori_neschimbat(date, nou) is False:
		raise EroareScriere("schimbarea afisajului nu a iesit")
	return nou


def _bloc_culori_neschimbat(a, b):
	pa, pb = gaseste_bloc(a), gaseste_bloc(b)
	if pa is None or pb is None:
		return None
	return a[pa[0]:pa[1]] == b[pb[0]:pb[1]]


def cale_pro(cale=None):
	"""skin_pro.xml (ecranele temei Pro a imaginii HDSatelit, lotul skin-pro-tv) din dosarul lui skin.xml. Are si el
	cele doua forme ale paginii tehnice, deci afisajul ales se pune in amandoua fisierele."""
	return os.path.join(os.path.dirname(cale or SKIN_XML), "skin_pro.xml")


def afisaj_la_zi(conf=None, cale=None, conf_cale=None):
	"""True daca skin.xml (si skin_pro.xml, cand exista) au deja afisajul din .conf (sau skinul nu stie de el: skin
	vechi, nimic de facut)."""
	c = conf if conf is not None else citeste_conf(conf_cale)
	dorit = c.get("afisaj", AFISAJ_IMPLICIT)
	try:
		with open(cale or SKIN_XML, "rb") as f:
			acum = afisaj_din_skin(f.read(CITIRE_AFISAJ))
	except Exception:
		return True
	if not (acum is None or acum == dorit):
		return False
	try:
		with open(cale_pro(cale), "rb") as f:
			acum_pro = afisaj_din_skin(f.read())
	except Exception:
		return True
	return acum_pro is None or acum_pro == dorit


def _scrie_afisaj_in(alegere, cale, nume):
	try:
		with open(cale, "rb") as f:
			date = f.read()
	except Exception as e:
		raise EroareScriere("nu pot citi %s: %s" % (nume, e))
	if afisaj_din_skin(date) is None:
		return False
	nou = schimba_afisaj(date, alegere)
	if nou == date:
		return False
	try:
		_scrie_atomic(cale, nou)
	except Exception as e:
		raise EroareScriere("nu pot scrie in %s: %s" % (os.path.dirname(cale), e))
	return True


def scrie_afisaj(alegere, cale=None):
	"""Pune afisajul ales in skin.xml si in skin_pro.xml, daca exista (scriere atomica). True daca s-a schimbat ceva."""
	cale = cale or SKIN_XML
	schimbat = _scrie_afisaj_in(alegere, cale, "skin.xml")
	pro = cale_pro(cale)
	if os.path.exists(pro):
		schimbat = _scrie_afisaj_in(alegere, pro, "skin_pro.xml") or schimbat
	return schimbat
