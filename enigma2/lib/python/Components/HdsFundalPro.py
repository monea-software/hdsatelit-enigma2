# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsFundalPro: fundalurile tematice puse PESTE tema Pro (Eduard 04.11 21:15 si 08.11 10:42: nu o a treia tema, ci poze
# decupate pentru capul si legenda ferestrelor, cartonase, bara de informatii, selectie si taste; "Pro, cum e acum, fara
# fundal" ramane; cateva teme in imagine, restul descarcate de pe serverul nostru, fiecare separat). Logica comuna a ecranului
# "Fundalul temei Pro" (Screens/HdsFundalPro.py) si a sectiunii de pe pagina web /tema-tv (HdsWebControl/tema_tv_web.py).
#
# - Setarea: config.skin.fundal_pro (ConfigText, "" = Pro fara fundal), facuta in skin.py (se citeste la pornire).
# - O tema = un dosar <id>/ cu tema.json (id, nume pe limbi, versiune), previzualizare.jpg si piesele cu numele fixe din PIESE
#   (PNG cu transparenta, la marimea exacta). Temele din imagine: DOSAR_IMAGINE (pachetul hdsatelit-skin); cele descarcate:
#   DOSAR_DESCARCATE (raman la actualizari).
# - Aplicarea face dosarul activ (DOSAR_ACTIV): copiile pieselor, selectia colorata cu culoarea paletei (piesele "masca"),
#   stare.json; totul scris intr-un dosar nou si mutat dintr-o data. skin.py incarca HDSatelit/skin_pro_fundal.xml (scris de
#   receptor/skin/tools/fa_skin_pro_fundal.py din skin_pro.xml, cu caile spre DOSAR_ACTIV) inaintea lui skin_pro.xml numai
#   cand fundalDeIncarcat() gaseste toate piesele; altfel ramane Pro curat. Schimbarea se vede dupa repornirea interfetei.
# - Serverul: CATALOG (+ .sig, semnat cu cheile HD Satelit din Components/HdsSemnatura.py, scopul SCOP_CATALOG). Catalogul
#   are pentru fiecare piesa url relativ, marime si sha256; piesele se descarca una cate una, se verifica (marime, sha256, PNG
#   sau JPEG adevarat, marimea in pixeli) si dosarul temei se muta dintr-o data. Fara arhive.
#
# Modulul nu importa nimic din enigma2 la incarcare (probele de pe PC dau config, caile si cererile):
# teste/test_tpr_fundaluri_tema_075.py.

import hashlib
import json
import os
import re
import shutil
import struct
import tempfile
import time

DOSAR_SKIN = "/usr/share/enigma2/HDSatelit"
DOSAR_IMAGINE = DOSAR_SKIN + "/fundaluri-pro"
DOSAR_DESCARCATE = "/etc/enigma2/hdsatelit/fundaluri-pro"
DOSAR_ACTIV = "/etc/enigma2/hdsatelit/fundal-pro/activ"
FISIER_FUNDAL = "skin_pro_fundal.xml"
TEMA_FUNDAL_FISIER = "HDSatelit/" + FISIER_FUNDAL
CATALOG = "https://stb.hdsatelit.com/feed/fundaluri-pro/catalog.json"
SCOP_CATALOG = "fundaluri-pro.json"
FARA = ""
FORMAT = 1

# piesele: nume -> (latime, inaltime, fel). "blend": poza asa cum e (amestec cu fundalul ferestrei); "masca": poza alb-gri
# colorata la aplicare cu culoarea selectiei din paleta, cu alfa taiat la 0/255 (motorul o pune cu BT_ALPHATEST); "fix": poza
# colorata asa cum e (tastele colorate). Locurile lor in ecrane: tools/fa_skin_pro_fundal.py din stratul skinului.
PIESE = {
	"cap_1776": (1776, 88, "blend"), "jos_1776": (1776, 76, "blend"),
	"cap_1240": (1240, 88, "blend"), "jos_1240": (1240, 76, "blend"),
	"cap_1000": (1000, 88, "blend"), "jos_1000": (1000, 76, "blend"),
	"card_stanga": (1088, 816, "blend"), "card_dreapta": (640, 816, "blend"),
	"bara_stare": (880, 84, "blend"), "bara_ceas": (536, 84, "blend"), "bara_jos": (1728, 254, "blend"),
	"selectie_meniu": (1056, 66, "masca"), "selectie_setari": (1056, 60, "masca"),
	"tasta_red": (24, 24, "fix"), "tasta_green": (24, 24, "fix"), "tasta_yellow": (24, 24, "fix"), "tasta_blue": (24, 24, "fix"),
}
PREVIZUALIZARE = "previzualizare.jpg"
MARIME_PREVIZUALIZARE = (640, 360)
# culoarea selectiei cand paleta nu se poate citi (hdsBrand din paleta implicita a skinului)
CULOARE_IMPLICITA = (0x37, 0x4E, 0xA1)

MAX_CATALOG = 512 * 1024
MAX_SEMNATURA = 8 * 1024
MAX_PIESA = 3 * 1024 * 1024
MAX_PREVIZUALIZARE = 256 * 1024
MAX_TEME = 200
LOC_MINIM = 8 * 1024 * 1024
TIMP = 15

_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}\Z")
_SHA = re.compile(r"^[0-9a-f]{64}\Z")
# caile pieselor in catalog: relative, sub dosarul catalogului, fara .. si fara alta gazda
_URL = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}/[a-z0-9_]{1,32}\.(png|jpg)\Z")
_PNG = b"\x89PNG\r\n\x1a\n"


def N_(text):
	return text


TEXT_FARA = N_("Pro, cum e acum, fără fundal")
TEXT_DESCRIERE = N_("Poze peste tema Pro: capul și legenda ferestrelor, meniul, setările, bara de informații, selecția și tastele colorate. Culorile alese în Setări skin rămân.")
TEXT_NU_PRO = N_("Fundalurile se pun peste tema Pro: alegerea unui fundal pune și tema Pro.")
TEXT_ALT_SKIN = N_("Fundalurile sunt ale temei Pro din skinul HDSatelit; skinul ales acum este altul.")
TEXT_FARA_RETEA = N_("Lista de pe server nu se poate citi acum. Temele din receptor se pot alege.")
TEXT_NESEMNAT = N_("Lista de pe server nu e semnată de HD Satelit; nu se descarcă nimic.")
TEXT_DESCARCARE_GRESITA = N_("Tema nu s-a putut descărca întreagă; nu s-a schimbat nimic.")
TEXT_LOC = N_("Nu e destul loc în memoria receptorului pentru tema aleasă.")
TEXT_APLICATA = N_("Fundalul se vede după repornirea interfeței.")
TEXT_DEJA = N_("Fundalul este deja aplicat.")
TEXT_PIESE_LIPSA = N_("Tema aleasă nu are toate pozele; rămâne tema Pro fără fundal.")


def _t(traducere, text):
	try:
		return traducere(text) if traducere else text
	except Exception:
		return text


def _config(config=None):
	if config is not None:
		return config
	from Components.config import config as c
	return c


def valid(id_):
	return bool(id_) and bool(_ID.match(id_))


# ---------------------------------------------------------------- pozele
def marimePng(date):
	"""(latime, inaltime) dintr-un PNG (antetul IHDR), None daca nu e PNG"""
	if len(date) < 24 or date[:8] != _PNG or date[12:16] != b"IHDR":
		return None
	return struct.unpack(">II", date[16:24])


def esteJpeg(date):
	return len(date) > 4 and date[:3] == b"\xff\xd8\xff"


def _citeste(cale, limita):
	with open(cale, "rb") as f:
		return f.read(limita + 1)


def piesaBuna(nume, date):
	"""PNG adevarat la marimea exacta a piesei"""
	w, h, _fel = PIESE[nume]
	return marimePng(date) == (w, h)


# ---------------------------------------------------------------- temele de pe receptor
def citesteTema(dosar):
	"""tema.json si piesele unui dosar; None daca lipseste ceva sau o piesa nu are marimea ei"""
	try:
		with open(os.path.join(dosar, "tema.json"), "rb") as f:
			d = json.loads(f.read(64 * 1024).decode("utf-8"))
	except (OSError, IOError, ValueError):
		return None
	if not isinstance(d, dict):
		return None
	id_ = d.get("id")
	if not valid(id_) or os.path.basename(os.path.normpath(dosar)) != id_:
		return None
	for nume in PIESE:
		try:
			if not piesaBuna(nume, _citeste(os.path.join(dosar, nume + ".png"), 32)):
				return None
		except (OSError, IOError):
			return None
	nume = d.get("nume") if isinstance(d.get("nume"), dict) else {}
	prev = os.path.join(dosar, PREVIZUALIZARE)
	return {"id": id_, "nume": dict((k, v) for k, v in nume.items() if isinstance(v, str)),
		"versiune": str(d.get("versiune", "1"))[:16], "dosar": dosar,
		"previzualizare": prev if os.path.isfile(prev) else ""}


def temeLocale(dosare=None):
	"""temele din imagine, apoi cele descarcate (o tema descarcata cu acelasi id o inlocuieste pe cea din imagine)"""
	gasite = {}
	ordine = []
	for sursa, dosar in (dosare or (("imagine", DOSAR_IMAGINE), ("descarcata", DOSAR_DESCARCATE))):
		try:
			nume = sorted(os.listdir(dosar))
		except OSError:
			continue
		for n in nume:
			t = citesteTema(os.path.join(dosar, n))
			if t is None:
				continue
			t["sursa"] = sursa
			if t["id"] not in gasite:
				ordine.append(t["id"])
			gasite[t["id"]] = t
	return [gasite[i] for i in ordine]


def numeTema(tema, limba="ro"):
	n = tema.get("nume") or {}
	return n.get(limba) or n.get((limba or "")[:2]) or n.get("en") or n.get("ro") or tema.get("id", "")


def limbaInterfetei():
	try:
		from Components.Language import language
		return language.getLanguage()[:2]
	except Exception:
		return "ro"


# ---------------------------------------------------------------- catalogul de pe server
def _cere(url, limita, timp=TIMP):
	"""octetii de la url (numai https, cel mult `limita`); OSError la orice esec"""
	if not url.startswith("https://stb.hdsatelit.com/"):
		raise OSError("adresa nepermisa")
	from urllib.request import HTTPRedirectHandler, Request, build_opener

	class _FaraRedirectionare(HTTPRedirectHandler):
		def redirect_request(self, *a, **k):
			return None
	r = build_opener(_FaraRedirectionare).open(Request(url, headers={"User-Agent": "hdsatelit-receptor/1"}), timeout=timp)
	try:
		date = r.read(limita + 1)
	finally:
		r.close()
	if len(date) > limita:
		raise OSError("prea mare")
	return date


def _verificaSemnatura(date, sig):
	from Components import HdsSemnatura
	return HdsSemnatura.verifica(date, sig, SCOP_CATALOG)


def _fisierCatalog(d):
	"""o intrare a catalogului (url, marime, sha256) sau None"""
	if not isinstance(d, dict):
		return None
	url, marime, sha = d.get("url"), d.get("marime"), d.get("sha256")
	if not isinstance(url, str) or not _URL.match(url) or not isinstance(marime, int) or not isinstance(sha, str):
		return None
	if marime <= 0 or marime > MAX_PIESA or not _SHA.match(sha):
		return None
	return {"url": url, "marime": marime, "sha256": sha}


def citesteCatalog(date):
	"""temele valide dintr-un catalog deja verificat (lista de dictionare); intrarile stricate se sar"""
	d = json.loads(date.decode("utf-8"))
	if not isinstance(d, dict) or d.get("format") != FORMAT or not isinstance(d.get("teme"), list):
		raise ValueError("forma catalogului")
	teme = []
	for t in d["teme"][:MAX_TEME]:
		if not isinstance(t, dict) or not valid(t.get("id")):
			continue
		piese = t.get("piese")
		if not isinstance(piese, dict) or set(piese) != set(PIESE):
			continue
		f = dict((n, _fisierCatalog(piese[n])) for n in PIESE)
		if None in f.values() or any(not v["url"].startswith(t["id"] + "/") for v in f.values()):
			continue
		prev = _fisierCatalog(t.get("previzualizare"))
		if prev is not None and (prev["marime"] > MAX_PREVIZUALIZARE or not prev["url"].endswith(".jpg")):
			prev = None
		nume = t.get("nume") if isinstance(t.get("nume"), dict) else {}
		teme.append({"id": t["id"], "versiune": str(t.get("versiune", "1"))[:16],
			"nume": dict((k, v[:60]) for k, v in nume.items() if isinstance(k, str) and isinstance(v, str)),
			"piese": f, "previzualizare": prev, "sursa": "server"})
	return teme


def catalog(cere=None, verifica=None, adresa=CATALOG):
	"""(teme, motiv): temele de pe server; motiv "" cand lista e semnata si citita, "retea" sau "nesemnat" altfel"""
	cere = cere or _cere
	verifica = verifica or _verificaSemnatura
	try:
		date = cere(adresa, MAX_CATALOG)
		sig = cere(adresa + ".sig", MAX_SEMNATURA).decode("ascii", "replace")
	except Exception as e:
		print("[HdsFundalPro] catalogul: %s" % e)
		return [], "retea"
	try:
		bun = verifica(date, sig)[0]
	except Exception as e:
		print("[HdsFundalPro] semnatura catalogului: %s" % e)
		bun = False
	if not bun:
		return [], "nesemnat"
	try:
		return citesteCatalog(date), ""
	except (ValueError, UnicodeError) as e:
		print("[HdsFundalPro] catalogul stricat: %s" % e)
		return [], "nesemnat"


def locLiber(dosar):
	try:
		s = os.statvfs(dosar)
		return s.f_bavail * s.f_frsize
	except OSError:
		return 0


def descarca(tema, cere=None, dosar=DOSAR_DESCARCATE, adresa=CATALOG, liber=None):
	"""(bun, motiv): piesele temei din catalog, verificate, intr-un dosar nou mutat dintr-o data in dosar/<id>.
	motiv: "", "loc", "descarcare"."""
	cere = cere or _cere
	baza = adresa.rsplit("/", 1)[0] + "/"
	id_ = tema["id"]
	try:
		os.makedirs(dosar)
	except OSError:
		pass
	nevoie = sum(f["marime"] for f in tema["piese"].values()) + LOC_MINIM
	if (liber or locLiber)(dosar) < nevoie:
		return False, "loc"
	lucru = tempfile.mkdtemp(prefix=".%s-" % id_, dir=dosar)
	try:
		for nume, f in sorted(tema["piese"].items()):
			date = cere(baza + f["url"], f["marime"])
			if len(date) != f["marime"] or hashlib.sha256(date).hexdigest() != f["sha256"] or not piesaBuna(nume, date):
				raise ValueError("piesa %s nu se potriveste" % nume)
			with open(os.path.join(lucru, nume + ".png"), "wb") as o:
				o.write(date)
		p = tema.get("previzualizare")
		if p:
			try:
				date = cere(baza + p["url"], p["marime"])
				if hashlib.sha256(date).hexdigest() == p["sha256"] and esteJpeg(date):
					with open(os.path.join(lucru, PREVIZUALIZARE), "wb") as o:
						o.write(date)
			except Exception as e:
				print("[HdsFundalPro] previzualizarea %s: %s" % (id_, e))
		with open(os.path.join(lucru, "tema.json"), "w") as o:
			json.dump({"id": id_, "nume": tema.get("nume", {}), "versiune": tema.get("versiune", "1")}, o, ensure_ascii=False)
		tinta = os.path.join(dosar, id_)
		vechi = None
		if os.path.isdir(tinta):
			vechi = tinta + ".vechi"
			shutil.rmtree(vechi, ignore_errors=True)
			os.rename(tinta, vechi)
		os.rename(lucru, tinta)
		lucru = None
		if vechi:
			shutil.rmtree(vechi, ignore_errors=True)
		return True, ""
	except Exception as e:
		print("[HdsFundalPro] descarcarea %s: %s" % (id_, e))
		return False, "descarcare"
	finally:
		if lucru:
			shutil.rmtree(lucru, ignore_errors=True)


# ---------------------------------------------------------------- aplicarea
def culoareSelectie():
	"""(r, g, b) al culorii hdsBrand din paleta skinului incarcat (fundalul randului ales din liste)"""
	try:
		import skin
		c = skin.colors.get("hdsBrand")
		v = c.argb() if c is not None else None
		if v is not None:
			return ((v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF)
	except Exception:
		pass
	return CULOARE_IMPLICITA


def coloreaza(sursa, tinta, culoare):
	"""masca alb-gri -> culoarea paletei (luminozitatea inmulteste culoarea), alfa taiat la 0/255 (BT_ALPHATEST)"""
	from PIL import Image
	im = Image.open(sursa).convert("RGBA")
	r, g, b, a = im.split()
	lum = Image.merge("RGB", (r, g, b)).convert("L")
	canale = [lum.point(lambda v, c=c: v * c // 255) for c in culoare]
	alfa = a.point(lambda v: 255 if v >= 128 else 0)
	Image.merge("RGBA", canale + [alfa]).save(tinta, "PNG")


def faActiv(tema, culoare, activ=DOSAR_ACTIV):
	"""dosarul activ al temei: copiile pieselor (mastile colorate), stare.json; mutat dintr-o data"""
	parinte = os.path.dirname(activ)
	try:
		os.makedirs(parinte)
	except OSError:
		pass
	lucru = tempfile.mkdtemp(prefix=".activ-", dir=parinte)
	try:
		for nume, (_w, _h, fel) in PIESE.items():
			src = os.path.join(tema["dosar"], nume + ".png")
			dst = os.path.join(lucru, nume + ".png")
			if fel == "masca":
				coloreaza(src, dst, culoare)
			else:
				shutil.copyfile(src, dst)
		with open(os.path.join(lucru, "stare.json"), "w") as o:
			json.dump({"tema": tema["id"], "versiune": tema.get("versiune", "1"), "culoare": "#%02X%02X%02X" % tuple(culoare),
				"cand": int(time.time())}, o)
		vechi = activ + ".vechi"
		shutil.rmtree(vechi, ignore_errors=True)
		if os.path.isdir(activ):
			os.rename(activ, vechi)
		os.rename(lucru, activ)
		lucru = None
		shutil.rmtree(vechi, ignore_errors=True)
	finally:
		if lucru:
			shutil.rmtree(lucru, ignore_errors=True)


def stareActiv(activ=DOSAR_ACTIV):
	try:
		with open(os.path.join(activ, "stare.json")) as f:
			d = json.load(f)
		return d if isinstance(d, dict) else {}
	except (OSError, IOError, ValueError):
		return {}


def fundalDeIncarcat(ales, mediu=None, activ=DOSAR_ACTIV):
	"""True cand skin.py incarca skin_pro_fundal.xml: un fundal ales, nu e modul sigur, dosarul activ e al lui si are toate
	piesele (o poza lipsa ar opri ecranul la construire)"""
	mediu = os.environ if mediu is None else mediu
	if not valid(ales) or mediu.get("HDS_MOD_SIGUR") == "1":
		return False
	if stareActiv(activ).get("tema") != ales:
		return False
	return all(os.path.isfile(os.path.join(activ, n + ".png")) for n in PIESE)


def curataActiv(ales, activ=DOSAR_ACTIV):
	"""la pornire (skin.py, inainte de incarcarea temei): fara fundal ales, dosarul activ ramas de la "Pro fara fundal" se
	sterge. True cand a sters ceva."""
	if valid(ales) or not os.path.isdir(activ):
		return False
	shutil.rmtree(activ, ignore_errors=True)
	return True


def ales(config=None):
	try:
		v = _config(config).skin.fundal_pro.value
	except Exception:
		return FARA
	return v if valid(v) else FARA


def _salveaza(config, configfile):
	c = _config(config)
	c.skin.fundal_pro.save()
	if configfile is None:
		from Components.config import configfile as cf
		configfile = cf
	configfile.save()


def aplica(id_, config=None, configfile=None, teme=None, culoare=None, activ=DOSAR_ACTIV, traducere=None, temaTv=None):
	"""(bun, mesaj, repornire): pune fundalul `id_` ("" = Pro fara fundal). Alegerea unui fundal pune si tema Pro
	(HdsTemaTv.seteaza) cand tema aleasa e alta. repornire = interfata trebuie repornita ca sa se vada."""
	c = _config(config)
	from Components import HdsTemaTv as T
	temaTv = temaTv or T
	if not temaTv.skinImaginii(c):
		return False, _t(traducere, TEXT_ALT_SKIN), False
	if id_ == FARA:
		if ales(c) == FARA:
			return True, _t(traducere, TEXT_DEJA), False
		# dosarul activ NU se sterge acum: skin_pro_fundal.xml e inca incarcat si un ecran deschis inainte de repornire ar
		# cere pozele lui (SkinError); il sterge curataActiv la urmatoarea pornire, cand setarea e goala
		c.skin.fundal_pro.value = FARA
		_salveaza(c, configfile)
		return True, _t(traducere, TEXT_APLICATA), True
	teme = temeLocale() if teme is None else teme
	tema = next((t for t in teme if t["id"] == id_ and t.get("dosar")), None)
	if tema is None or citesteTema(tema["dosar"]) is None:
		return False, _t(traducere, TEXT_PIESE_LIPSA), False
	if ales(c) == id_ and temaTv.aleasa(c) == "pro" and fundalDeIncarcat(id_, {}, activ) \
			and stareActiv(activ).get("versiune") == tema.get("versiune", "1"):
		return True, _t(traducere, TEXT_DEJA), False
	try:
		faActiv(tema, culoare or culoareSelectie(), activ)
	except Exception as e:
		print("[HdsFundalPro] aplicarea %s: %s" % (id_, e))
		return False, _t(traducere, TEXT_PIESE_LIPSA), False
	if temaTv.aleasa(c) != "pro":
		bun, mesaj, _schimbata = temaTv.seteaza("pro", config=c, configfile=configfile, traducere=traducere)
		if not bun:
			return False, mesaj, False
	c.skin.fundal_pro.value = id_
	_salveaza(c, configfile)
	return True, _t(traducere, TEXT_APLICATA), True


def stare(config=None, teme=None, server=None, motiv="", limba=None, traducere=None):
	"""lista pentru ecran si web: primul rand "Pro fara fundal", apoi temele din receptor, apoi cele de pe server care nu sunt
	descarcate (sau au alta versiune)"""
	c = _config(config)
	limba = limba or limbaInterfetei()
	teme = temeLocale() if teme is None else teme
	a = ales(c)
	randuri = [{"id": FARA, "nume": _t(traducere, TEXT_FARA), "sursa": "imagine", "aleasa": a == FARA, "previzualizare": ""}]
	locale = dict((t["id"], t) for t in teme)
	for t in teme:
		randuri.append({"id": t["id"], "nume": numeTema(t, limba), "sursa": t["sursa"], "aleasa": a == t["id"],
			"previzualizare": t.get("previzualizare", "")})
	for t in server or []:
		l = locale.get(t["id"])
		if l is not None and l.get("versiune") == t.get("versiune"):
			continue
		randuri.append({"id": t["id"], "nume": numeTema(t, limba), "sursa": "server", "aleasa": False,
			"previzualizare": t.get("previzualizare_locala", ""), "tema_server": t})
	try:
		tema_tv = c.skin.tema_tv.value
	except Exception:
		tema_tv = "clasic"
	nota = _t(traducere, TEXT_NU_PRO) if tema_tv != "pro" else ""
	if motiv == "retea":
		nota = _t(traducere, TEXT_FARA_RETEA)
	elif motiv == "nesemnat":
		nota = _t(traducere, TEXT_NESEMNAT)
	return {"ales": a, "randuri": randuri, "nota": nota, "descriere": _t(traducere, TEXT_DESCRIERE)}


def alege(rand, config=None, configfile=None, cere=None, traducere=None, dosar=DOSAR_DESCARCATE, activ=DOSAR_ACTIV,
		culoare=None, temaTv=None, liber=None):
	"""Pasul omului: un rand din stare()["randuri"]. Tema de pe server se descarca intai, apoi se aplica.
	(bun, mesaj, repornire). Se cheama pe un fir de lucru (descarcarea poate dura)."""
	if rand.get("sursa") == "server":
		bun, motiv = descarca(rand["tema_server"], cere=cere, dosar=dosar, liber=liber)
		if not bun:
			return False, _t(traducere, TEXT_LOC if motiv == "loc" else TEXT_DESCARCARE_GRESITA), False
		teme = temeLocale((("descarcata", dosar),))
	else:
		teme = None
	return aplica(rand["id"], config=config, configfile=configfile, teme=teme, culoare=culoare, activ=activ,
		traducere=traducere, temaTv=temaTv)


# ---------------------------------------------------------------- lucrul pe fir (ecranul si pagina web)
# Catalogul de pe server se tine minte TIMP_CATALOG secunde si se citeste pe un fir (firul interfetei nu asteapta reteaua);
# previzualizarile temelor de pe server se descarca langa el, in DOSAR_PREV_SERVER (verificate cu sha256 din catalog).
# Alegerea unui rand: descarcarea pe fir, apoi aplicarea si repornirea interfetei pe firul principal (configul si ecranele
# nu se ating din alt fir). Firele se pornesc cu _thread (ca in HdsPython2Traducere/FRD: fara threading.Thread.start, care
# poate astepta un lacat al interpretorului) si nu tin pornirea sau oprirea interfetei.
import threading

DOSAR_PREV_SERVER = "/tmp/hds-fundaluri-pro"
# /tmp e in RAM: cel mult atatea previzualizari (40 x 256 KB = 10 MB in cel mai rau caz)
MAX_PREV_SERVER = 40
TIMP_CATALOG = 600
_LACAT = threading.Lock()
_SERVER = {"teme": [], "motiv": "", "cand": 0, "citeste": False}
_LUCRU = {"id": None, "lucreaza": False, "bun": None, "mesaj": "", "repornire": False}


def _fir(functie):
	import _thread
	_thread.start_new_thread(functie, ())


def _peFirPrincipal(functie):
	try:
		from twisted.internet import reactor
		reactor.callFromThread(functie)
	except Exception as e:
		print("[HdsFundalPro] firul principal: %s" % e)


def previzualizariServer(teme, cere=None, dosar=DOSAR_PREV_SERVER, adresa=CATALOG):
	"""previzualizarile temelor de pe server, in dosar/<id>.jpg (t["previzualizare_locala"])"""
	cere = cere or _cere
	baza = adresa.rsplit("/", 1)[0] + "/"
	try:
		os.makedirs(dosar)
	except OSError:
		pass
	for t in teme[:MAX_PREV_SERVER]:
		p = t.get("previzualizare")
		if not p:
			continue
		cale = os.path.join(dosar, t["id"] + ".jpg")
		try:
			if not os.path.isfile(cale) or hashlib.sha256(_citeste(cale, MAX_PREVIZUALIZARE)).hexdigest() != p["sha256"]:
				date = cere(baza + p["url"], p["marime"])
				if hashlib.sha256(date).hexdigest() != p["sha256"] or not esteJpeg(date):
					continue
				with open(cale + ".tmp", "wb") as o:
					o.write(date)
				os.rename(cale + ".tmp", cale)
			t["previzualizare_locala"] = cale
		except Exception as e:
			print("[HdsFundalPro] previzualizarea %s: %s" % (t["id"], e))


def server():
	"""(teme, motiv, se_citeste) din memorie"""
	with _LACAT:
		return list(_SERVER["teme"]), _SERVER["motiv"], _SERVER["citeste"]


def citesteServer(forteaza=False, cere=None, verifica=None, fir=None, cand=None):
	"""porneste citirea catalogului pe un fir, daca nu e proaspat sau deja in lucru; True cand a pornit-o"""
	acum = time.time() if cand is None else cand
	with _LACAT:
		if _SERVER["citeste"] or (not forteaza and _SERVER["cand"] and acum - _SERVER["cand"] < TIMP_CATALOG):
			return False
		_SERVER["citeste"] = True

	def lucreaza():
		teme, motiv = [], "retea"
		try:
			teme, motiv = catalog(cere=cere, verifica=verifica)
			previzualizariServer(teme, cere=cere)
		finally:
			with _LACAT:
				_SERVER.update(teme=teme, motiv=motiv, cand=time.time(), citeste=False)
	(fir or _fir)(lucreaza)
	return True


def stareLucru():
	with _LACAT:
		return dict(_LUCRU)


def porneste(id_, sesiune=None, config=None, configfile=None, traducere=None, fir=None, peFirPrincipal=None, **cai):
	"""Pasul omului, din ecran sau din web: alege randul `id_` ("" = fara fundal). Tema de pe server se descarca pe un fir;
	aplicarea si repornirea interfetei (TryQuitMainloop 3, cand e nevoie) se fac pe firul principal. False daca alt lucru e
	in curs sau randul nu exista."""
	teme, motiv, _c = server()
	rand = next((r for r in stare(config=config, server=teme, motiv=motiv, traducere=traducere,
		teme=cai.get("teme"))["randuri"] if r["id"] == id_), None)
	if rand is None:
		return False
	with _LACAT:
		if _LUCRU["lucreaza"]:
			return False
		_LUCRU.update(id=id_, lucreaza=True, bun=None, mesaj="", repornire=False)

	def termina(bun, mesaj, repornire):
		with _LACAT:
			_LUCRU.update(lucreaza=False, bun=bun, mesaj=mesaj, repornire=repornire)
		if bun and repornire and sesiune is not None:
			try:
				from Screens.Standby import TryQuitMainloop
				sesiune.open(TryQuitMainloop, 3)
			except Exception as e:
				print("[HdsFundalPro] repornirea: %s" % e)

	def aplicaPrincipal(teme_aplicare):
		try:
			bun, mesaj, rep = aplica(id_, config=config, configfile=configfile, teme=teme_aplicare, traducere=traducere,
				activ=cai.get("activ", DOSAR_ACTIV), culoare=cai.get("culoare"), temaTv=cai.get("temaTv"))
		except Exception as e:
			print("[HdsFundalPro] aplicarea: %s" % e)
			bun, mesaj, rep = False, _t(traducere, TEXT_PIESE_LIPSA), False
		termina(bun, mesaj, rep)

	def lucreaza():
		teme_aplicare = cai.get("teme")
		try:
			if rand.get("sursa") == "server":
				dosar = cai.get("dosar", DOSAR_DESCARCATE)
				bun, m = descarca(rand["tema_server"], cere=cai.get("cere"), dosar=dosar, liber=cai.get("liber"))
				if not bun:
					termina(False, _t(traducere, TEXT_LOC if m == "loc" else TEXT_DESCARCARE_GRESITA), False)
					return
				teme_aplicare = temeLocale((("descarcata", dosar),))
		except Exception as e:
			print("[HdsFundalPro] lucrul: %s" % e)
			termina(False, _t(traducere, TEXT_DESCARCARE_GRESITA), False)
			return
		(peFirPrincipal or _peFirPrincipal)(lambda: aplicaPrincipal(teme_aplicare))
	(fir or _fir)(lucreaza)
	return True
