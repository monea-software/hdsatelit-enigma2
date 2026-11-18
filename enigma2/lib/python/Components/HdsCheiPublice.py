# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsCheiPublice.py: cheile publice ale omului (fisierul SoftCam.Key) aduse dintr-o apasare, ca la ceilalti manageri de module
# (0.7.7). In ecranul modulelor de acces (Screens/CamSetup.py) un rand la coada listei si in pagina web /acces-conditionat
# (HdsWebControl/acces_conditionat_web.py) un card: OK (sau butonul) descarca fisierul de la adresa din setare, il pune unde il
# citesc modulele instalate si reporneste modulul care ruleaza, ca sa citeasca cheile noi.
#
# Reguli:
#   - nimic nu se aduce singur: numai la apasarea omului; pachetele si fisierele de inceput ale imaginii nu au nicio cheie;
#   - adresa e o setare a omului (televizor: Galben pe rand; web: campul din card), gol = ADRESA_FABRICA; tinuta, cu data si
#     rezultatul ultimei aduceri, in FISIER_STARE (nicio cheie in el: numai adresa, data, cate chei, caile);
#   - fisierul descarcat se verifica numai ca forma (marime, text, nu o pagina web, cateva randuri cu forma unei chei) si se
#     scrie neschimbat; daca nu trece, nu se atinge niciun fisier (o pagina de eroare nu ia locul cheilor bune);
#   - unde: pentru fiecare modul instalat (si cel pornit de alt program), ordinea in care isi cauta modulul cheile: dosarul
#     configurarii lui, apoi DOSARE_COMUNE (ca modulele din feedul nostru; ale altor autori se uita in dosarul configurarii si
#     in /var/keys). Primul SoftCam.Key gasit (numele cu orice litere, ca pe disc; calea fara legaturi) se inlocuieste pe loc;
#     numai cand nu e niciunul, fisierul se face in dosarul configurarii (sau in primul dosar comun). Modulele al caror program
#     nu are cuvantul SoftCam.Key in el (nu citesc chei) se sar;
#   - fisierul omului nu se pierde, oricate aduceri ar urma: langa el raman numeCopie(nume) = cel de dinainte de PRIMA aducere
#     (facut o singura data, niciodata rescris) si numeCopie(nume, "inainte") = cel de dinainte de aducerea de acum, numai cand
#     nu e exact ce a scris aducerea de dinainte (semnul ei, sha256, tinut in FISIER_STARE): omul (sau modulul) l-a schimbat
#     intre aduceri. Copiile se fac din fisierul intreg, pe bucati, si se termina tot in .key (raman inchise pentru asistenta,
#     ca SoftCam.Key); fisierele se scriu dintr-o bucata (fisier nou langa el, apoi os.replace);
#   - modulul care ruleaza si al carui fisier s-a schimbat se reporneste prin scriptul lui (HdsModuleAcces.Operatie, ca Galben);
#     modulul pornit de alt program nu se atinge (textul spune ca il reporneste omul din programul acela);
#   - descarcarea, cautarea locurilor si scrierea merg pe un fir (HdsImportSurse.Lucrare); pe firul enigma2 nu se citeste
#     niciun fisier la reimprospatarea ecranului: starea se citeste o data si se tine in memorie.
# Nu importa nimic din enigma la incarcare (probele de pe PC); `sistem`, `descarca`, `lucrare` si `operatie` se dau la probe.
import hashlib
import json
import os
import posixpath
import re
import shutil
import socket
import ssl
import time

try:
	from urllib.request import Request, build_opener, HTTPHandler, HTTPSHandler
	from urllib.error import HTTPError, URLError
except ImportError:  # pragma: no cover
	Request = build_opener = HTTPHandler = HTTPSHandler = HTTPError = URLError = None

NUME = "SoftCam.Key"
# adresa publica folosita de managerii de module ai altora pentru acelasi lucru; numai valoarea din fabrica a setarii
ADRESA_FABRICA = "https://raw.githubusercontent.com/MOHAMED19OS/SoftCam_Emu/main/SoftCam.Key"
FISIER_STARE = "/etc/enigma2/hdsatelit/chei-publice.json"
# dupa dosarul configurarii, ca modulele din feedul nostru (peticul softcam-key-locuri al retetelor)
DOSARE_COMUNE = ("/etc/tuxbox/config", "/usr/keys", "/var/keys")
ADRESA_MAXIM = 512
OCTETI_MAXIM = 4 * 1024 * 1024
TERMEN_S = 20
TERMEN_TOTAL_S = 60
MINIM_CHEI = 3
PROGRAM_MAXIM = 64 * 1024 * 1024
AGENT = "Enigma2 HD Satelit"

MOTIVE = ("adresa", "nu_raspunde", "certificat", "prea_mare", "nu_e_text", "fara_chei", "scriere")
# un rand de cheie: tipul (o litera), identificatorul (hex), numele cheii, valoarea (hex); comentariul dupa ; sau # e voie
_RAND_CHEIE = re.compile(r"^\s*[A-Za-z]\s+[0-9A-Fa-f]{1,16}\s+[A-Za-z0-9]{1,16}\s+[0-9A-Fa-f]{2,}(?:\s|;|#|$)")
_ADRESA = re.compile(r"^https?://[^\s/?#@]+(?::[0-9]{1,5})?(?:[/?#][^\s]*)?$", re.IGNORECASE)

_stare = {"lucrare": None, "incarcata": False, "adresa": "", "cand": 0, "chei": 0, "fisiere": [], "semn": "", "text": "",
	"ok": False, "mesaj_cand": 0}
_SEMN = re.compile(r"^[0-9a-f]{64}$")
_ascultatori = []


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


def ngettext(unu, multe, n):
	"""Pluralul tradus (Components/HdsPlural: formele din Plural-Forms ale limbii, forma pentru 1 si fara cifra); numele e cel
	stiut de xgettext."""
	try:
		try:
			from Components import HdsPlural as P
		except ImportError:
			import HdsPlural as P
		return P.ngettext(unu, multe, n)
	except Exception:
		return unu if n == 1 else multe


def _jurnal(text):
	print("[HdsCheiPublice] %s" % text)


class EroareChei(Exception):
	def __init__(self, motiv, cale=""):
		Exception.__init__(self, motiv)
		self.motiv = motiv
		self.cale = cale


# ---------------------------------------------------------------- adresa si starea

def adresaBuna(adresa):
	"""Adresa curatata (http:// sau https://, fara spatii, cel mult ADRESA_MAXIM), sau None."""
	a = (adresa or "").strip()
	if not a or len(a) > ADRESA_MAXIM or not _ADRESA.match(a):
		return None
	return a


def _caleStare(sistem=None):
	return sistem.cale(FISIER_STARE) if sistem is not None else FISIER_STARE


def incarca(sistem=None, fortat=False):
	"""Starea din FISIER_STARE, citita o singura data (sau cu `fortat`); fara fisier, valorile goale."""
	if _stare["incarcata"] and not fortat:
		return _stare
	_stare["incarcata"] = True
	try:
		with open(_caleStare(sistem), "rb") as f:
			d = json.loads(f.read(65536).decode("utf-8"))
	except (OSError, IOError, ValueError):
		d = {}
	if not isinstance(d, dict):
		d = {}
	adresa = d.get("adresa") if isinstance(d.get("adresa"), str) else ""
	_stare["adresa"] = adresaBuna(adresa) or ""
	_stare["cand"] = int(d.get("cand") or 0) if isinstance(d.get("cand"), (int, float)) else 0
	_stare["chei"] = int(d.get("chei") or 0) if isinstance(d.get("chei"), (int, float)) else 0
	fisiere = d.get("fisiere") if isinstance(d.get("fisiere"), list) else []
	_stare["fisiere"] = [f for f in fisiere if isinstance(f, str) and f.startswith("/")][:16]
	semn = d.get("semn") if isinstance(d.get("semn"), str) else ""
	_stare["semn"] = semn if _SEMN.match(semn) else ""
	return _stare


def _salveaza(sistem=None):
	cale = _caleStare(sistem)
	d = {"adresa": _stare["adresa"], "cand": _stare["cand"], "chei": _stare["chei"], "fisiere": _stare["fisiere"],
		"semn": _stare["semn"]}
	try:
		os.makedirs(os.path.dirname(cale), exist_ok=True)
		nou = cale + ".nou"
		with open(nou, "w") as f:
			json.dump(d, f)
		os.replace(nou, cale)
	except (OSError, IOError) as e:
		_jurnal("starea nu s-a scris: %s" % e)


def adresa(sistem=None):
	"""Adresa de unde se aduc cheile: cea pusa de om, altfel ADRESA_FABRICA."""
	return incarca(sistem)["adresa"] or ADRESA_FABRICA


def puneAdresa(text, sistem=None):
	"""Adresa noua a omului; gol (sau chiar ADRESA_FABRICA) = adresa din fabrica. -> (bun, mesaj)."""
	incarca(sistem)
	t = (text or "").strip()
	if not t or t == ADRESA_FABRICA:
		_stare["adresa"] = ""
		_salveaza(sistem)
		return True, _("Adresa din fabrică e pusă la loc.")
	a = adresaBuna(t)
	if a is None:
		return False, _textAdresaRea()
	_stare["adresa"] = a
	_salveaza(sistem)
	return True, _("Adresa nouă e salvată.")


# ---------------------------------------------------------------- textele (aceleasi pe televizor si in web)

def textChei(n):
	"""Numarul de chei cu forma de plural a limbii (in romana: o cheie, 5 chei, 22 chei)."""
	return ngettext("%d cheie", "%d chei", n) % n


def textData(cand):
	return time.strftime("%d.%m.%Y %H:%M", time.localtime(cand))


def textRand():
	"""Randul din ecranul modulelor, cu data ultimei aduceri (numai din memorie)."""
	s = incarca()
	t = _("Adu cheile publice (SoftCam.Key)")
	if s["cand"]:
		return t + "  (" + _("ultima dată %s") % textData(s["cand"]) + ")"
	return t + "  (" + _("încă neaduse") + ")"


def tasteRand():
	"""(Verde, Galben) pe randul cheilor din ecranul modulelor"""
	return _("Adu cheile"), _("Schimbă adresa")


def tastatura():
	"""(titlul, textul de inceput) al tastaturii de pe televizor (Galben pe randul cheilor)"""
	return _("Adresa cheilor publice (gol = adresa din fabrică)"), adresa()


def dinTastatura(text):
	"""Textul scris de om cu tastatura de pe televizor: adresa noua (gol = cea din fabrica). -> (bun, mesaj)"""
	return puneAdresa(text)


def textUltima():
	s = incarca()
	if not s["cand"]:
		return _("Cheile publice nu au fost aduse încă.")
	return _("Ultima aducere: %s, %s.") % (textData(s["cand"]), textChei(s["chei"]))


def _textCe():
	return _("Se aduce fișierul SoftCam.Key de la adresa de mai jos și se pune unde îl citesc modulele instalate; modulul "
		"care rulează e repornit, ca să citească cheile noi.")


def _textAdresaRea():
	return _("Adresa nu e bună: trebuie să înceapă cu http:// sau https:// și să nu aibă spații.")


def randuriDetalii():
	"""Detaliile randului din ecranul modulelor."""
	s = incarca()
	r = ["OK: " + _textCe(), _("Adresa: %s") % adresa(), _("Galben") + ": " + tasteRand()[1], "", textUltima()]
	if s["cand"] and s["fisiere"]:
		r.append(_("În: %s") % ", ".join(s["fisiere"]))
		r.append(_("Fișierul de dinainte de prima aducere rămâne lângă el, ca %s; cel schimbat între aduceri, ca %s.") % (
			numeCopie(NUME), numeCopie(NUME, "inainte")))
	return r


def texteWeb():
	"""Textele cardului din pagina web, traduse pe receptor (aceleasi msgid ca pe televizor, unde se poate)."""
	return {"titlu": _("Cheile publice (SoftCam.Key)"), "buton": _("Adu cheile publice (SoftCam.Key)"),
		"nota": _textCe() + " " + _("Nimic nu se aduce singur, numai când apeși."),
		"eticheta_adresa": (_("Adresa: %s") % "").strip(), "salveaza": _("Salvează"), "nota_adresa": tastatura()[0]}


def textMotiv(motiv, cale=""):
	if motiv == "adresa":
		return _textAdresaRea()
	t = {
		"nu_raspunde": _("adresa nu răspunde (internetul receptorului sau adresa)"),
		"certificat": _("certificatul site-ului nu e bun"),
		"scriere": _("nu s-a putut scrie %s") % cale,
	}.get(motiv) or _("la adresă nu e un fișier de chei (poate adresa e greșită)")
	return _("Cheile publice nu s-au putut aduce: %s.") % t


# ---------------------------------------------------------------- descarcarea si verificarea

def descarca(adr, maxim=OCTETI_MAXIM, termen=TERMEN_S, total=TERMEN_TOTAL_S):
	"""GET cu margine la marime si la timp -> octetii. Arunca EroareChei."""
	if adresaBuna(adr) is None:
		raise EroareChei("adresa")
	cerere = Request(adr, headers={"User-Agent": AGENT, "Accept": "*/*", "Accept-Encoding": "identity"})
	deschizator = build_opener(HTTPHandler(), HTTPSHandler(context=ssl.create_default_context()))
	inceput = time.time()
	try:
		raspuns = deschizator.open(cerere, timeout=termen)
		try:
			bucati, n = [], 0
			while True:
				b = raspuns.read(65536)
				if not b:
					break
				n += len(b)
				if n > maxim:
					raise EroareChei("prea_mare")
				if time.time() - inceput > total:
					raise EroareChei("nu_raspunde")
				bucati.append(b)
			return b"".join(bucati)
		finally:
			raspuns.close()
	except EroareChei:
		raise
	except HTTPError as e:
		_jurnal("raspunsul %d" % e.code)
		e.close()
		raise EroareChei("nu_raspunde")
	except URLError as e:
		motiv = getattr(e, "reason", None)
		_jurnal("legatura: %s" % type(motiv).__name__)
		raise EroareChei("certificat" if isinstance(motiv, ssl.SSLError) else "nu_raspunde")
	except (socket.timeout, socket.error, ssl.SSLError, ValueError, OSError) as e:
		_jurnal("legatura: %s" % type(e).__name__)
		raise EroareChei("nu_raspunde")


def numarChei(octeti):
	"""Cate randuri cu forma unei chei are fisierul; arunca EroareChei cand nu e un fisier de chei. Valorile nu se scriu
	nicaieri (nici in jurnal)."""
	if not octeti or len(octeti) > OCTETI_MAXIM:
		raise EroareChei("prea_mare" if octeti else "fara_chei")
	if b"\x00" in octeti:
		raise EroareChei("nu_e_text")
	try:
		text = octeti.decode("utf-8-sig")
	except UnicodeDecodeError:
		text = octeti.decode("latin-1")
	mic = text.lower()
	if "<html" in mic or "<!doctype" in mic or "<body" in mic:
		raise EroareChei("nu_e_text")
	n = sum(1 for r in text.splitlines() if _RAND_CHEIE.match(r))
	if n < MINIM_CHEI:
		raise EroareChei("fara_chei")
	return n


# ---------------------------------------------------------------- unde le citesc modulele

def numeCopie(nume, fel="bak"):
	"""SoftCam.Key -> SoftCam.bak.Key (sau SoftCam.<fel>.Key): tot .key la coada, deci ramane inchis pentru asistenta."""
	baza, punct, ext = nume.rpartition(".")
	return (baza + "." + fel + "." + ext) if punct and baza else nume + "." + fel


def _h():
	try:
		from Components import HdsModuleAcces as H
	except ImportError:  # probe pe PC
		import HdsModuleAcces as H
	return H


def _programe(sistem, fel, sufix):
	try:
		try:
			from Components import HdsModulNepornit as N
		except ImportError:  # probe pe PC
			import HdsModulNepornit as N
		return N.programe(sistem, fel, sufix)
	except Exception as e:
		_jurnal("programele lui %s: %r" % (sufix, e))
		return []


def citesteChei(sistem, programe):
	"""True cand primul program care exista are in el cuvantul SoftCam.Key (modulul citeste chei), False cand nu il are, None
	cand niciunul nu se poate citi. Numai citire, pe bucati."""
	ac = NUME.encode("ascii")
	for p in programe:
		try:
			with open(sistem.cale(p), "rb") as f:
				rest, citit = b"", 0
				while citit < PROGRAM_MAXIM:
					b = f.read(1024 * 1024)
					if not b:
						return False
					citit += len(b)
					if ac in rest + b:
						return True
					rest = b[-len(ac):]
				return False
		except (OSError, IOError):
			continue
	return None


def _fisierInDosar(sistem, dosar):
	"""Calea fara legaturi a lui SoftCam.Key (numele cu orice litere) din `dosar` (deja fara legaturi), sau None."""
	try:
		nume = sistem.listeaza(dosar)
	except (OSError, IOError, ValueError):
		return None
	for n in sorted(nume):
		if n.lower() == NUME.lower():
			cale = sistem.tinta(posixpath.join(dosar, n))
			if os.path.isfile(sistem.cale(cale)):
				return cale
	return None


def tintaModul(sistem, dosar):
	"""Fisierul pe care il citeste un modul cu dosarul de configurare `dosar` ("" = necunoscut): primul SoftCam.Key din dosar si
	din DOSARE_COMUNE, calea fara legaturi; altfel cel nou din dosar (sau din primul dosar comun care exista). -> (cale, exista)"""
	dosare = []
	for d in ([dosar.rstrip("/")] if dosar and dosar.startswith("/") else []) + list(DOSARE_COMUNE):
		d = sistem.tinta(d)
		if d not in dosare:
			dosare.append(d)
	for d in dosare:
		cale = _fisierInDosar(sistem, d)
		if cale:
			return cale, True
	for d in dosare:
		if os.path.isdir(sistem.cale(d)):
			return posixpath.join(d, NUME), False
	return posixpath.join(DOSARE_COMUNE[0], NUME), False


def tinte(sistem=None, H=None):
	"""[{cale, exista, module: [{fel, sufix, pids, citeste, alt}]}]: fisierele de scris, cu modulele care le citesc. Pe fir."""
	H = H or _h()
	sistem = sistem or H.SistemAcces()
	stari = [H.citeste(sistem, fel) for fel in H.feluri(sistem)]
	dosare = dict(((d["fel"], d["sufix"]), d["dosar"]) for d in H.dosare_configurare(sistem, stari))
	module = []
	for st in stari:
		for e in st.emulatoare:
			programe = []
			for pid in e.pids:
				try:
					programe.append(sistem.legatura("/proc/%d/exe" % pid).replace(" (deleted)", ""))
				except (OSError, IOError, ValueError):
					pass
			programe += _programe(sistem, st.fel, e.sufix)
			module.append({"fel": st.fel, "sufix": e.sufix, "pids": list(e.pids), "alt": False,
				"dosar": dosare.get((st.fel, e.sufix)) or "", "citeste": citesteChei(sistem, programe)})
	try:
		for a in H.pornite_de_alt_program(sistem, stari, descriptori=False):
			dosar, programe = "", []
			for pid in a["pids"]:
				try:
					argumente = sistem.citeste("/proc/%d/cmdline" % pid, 8192).split("\0")[1:]
					dosar = dosar or (H.dosar_configurare_web(argumente) or "")
					programe.append(sistem.legatura("/proc/%d/exe" % pid).replace(" (deleted)", ""))
				except (OSError, IOError, ValueError):
					continue
			module.append({"fel": "", "sufix": a["nume"], "pids": list(a["pids"]), "alt": True, "dosar": dosar,
				"citeste": citesteChei(sistem, programe)})
	except Exception as e:
		_jurnal("modulele pornite de alt program: %r" % (e,))
	rez = []
	for m in module:
		if m["citeste"] is False:
			continue
		cale, exista = tintaModul(sistem, m.pop("dosar"))
		t = [x for x in rez if x["cale"] == cale]
		if t:
			t[0]["module"].append(m)
		else:
			rez.append({"cale": cale, "exista": exista, "module": [m]})
	if not rez:
		cale, exista = tintaModul(sistem, "")
		rez.append({"cale": cale, "exista": exista, "module": []})
	return rez


def _semnFisier(c):
	h = hashlib.sha256()
	with open(c, "rb") as f:
		for b in iter(lambda: f.read(1024 * 1024), b""):
			h.update(b)
	return h.hexdigest()


def _copiaza(sursa, tinta):
	"""Copia intreaga a lui `sursa`, dintr-o bucata (fisier ascuns langa `tinta`, terminat tot in .key, apoi os.replace)."""
	dosar, nume = os.path.split(tinta)
	nou = os.path.join(dosar, "." + nume)
	shutil.copyfile(sursa, nou)
	os.replace(nou, tinta)


def _scrie(sistem, cale, octeti, semn_vechi=""):
	"""Fisierul `cale` (de pe receptor) cu octetii noi, dintr-o bucata. Inainte: copia de dinainte de prima aducere (numai cand
	nu exista) sau, cand fisierul nu e exact ce a scris aducerea de dinainte (`semn_vechi`), copia lui de acum. -> True cand
	s-a schimbat ceva. Arunca EroareChei("scriere")."""
	c = sistem.cale(cale)
	dosar, nume = os.path.split(c)
	try:
		exista = os.path.isfile(c)
		semn = _semnFisier(c) if exista else ""
		if semn == hashlib.sha256(octeti).hexdigest():
			return False
		os.makedirs(dosar, exist_ok=True)
		mod = (os.stat(c).st_mode & 0o7777) if exista else 0o644
		if exista:
			inceput = os.path.join(dosar, numeCopie(nume))
			if not os.path.lexists(inceput):
				_copiaza(c, inceput)
			elif semn != semn_vechi:
				_copiaza(c, os.path.join(dosar, numeCopie(nume, "inainte")))
		nou = os.path.join(dosar, "." + numeCopie(nume, "nou"))
		with open(nou, "wb") as f:
			f.write(octeti)
			f.flush()
			os.fsync(f.fileno())
		os.chmod(nou, mod)
		os.replace(nou, c)
		return True
	except (OSError, IOError) as e:
		_jurnal("scrierea in %s: %s" % (cale, e))
		raise EroareChei("scriere", cale)


def aduce(adr, sistem=None, H=None, citire=None, semn_vechi=""):
	"""Lucrul de pe fir: descarca, verifica, afla unde, scrie. -> {ok, chei, fisiere, schimbate, reporniri, alte, motiv, cale}.
	`citire(adresa)` = descarcarea (probele dau una falsa)."""
	H = H or _h()
	sistem = sistem or H.SistemAcces()
	try:
		octeti = (citire or descarca)(adr)
		n = numarChei(octeti)
		lista = tinte(sistem, H)
		schimbate = []
		for t in lista:
			if _scrie(sistem, t["cale"], octeti, semn_vechi):
				schimbate.append(t["cale"])
	except EroareChei as e:
		return {"ok": False, "motiv": e.motiv, "cale": e.cale}
	reporniri, alte = [], []
	for t in lista:
		if t["cale"] not in schimbate:
			continue
		for m in t["module"]:
			if not m["pids"] or m["citeste"] is not True:
				continue
			if m["alt"]:
				alte.append(m["sufix"])
			elif (m["fel"], m["sufix"]) not in reporniri:
				reporniri.append((m["fel"], m["sufix"]))
	return {"ok": True, "chei": n, "fisiere": [t["cale"] for t in lista], "schimbate": schimbate, "reporniri": reporniri,
		"alte": alte, "semn": hashlib.sha256(octeti).hexdigest()}


# ---------------------------------------------------------------- pe receptor: lucrarea

def inLucru():
	return _stare["lucrare"] is not None


def asculta(f):
	if f not in _ascultatori:
		_ascultatori.append(f)


def lasa(f):
	if f in _ascultatori:
		_ascultatori.remove(f)


def _anunta(text, ok, gata):
	_stare["text"], _stare["ok"], _stare["mesaj_cand"] = text, ok, int(time.time())
	if gata:
		_stare["lucrare"] = None
		_jurnal("gata (%s): %s" % ("bun" if ok else "nu", text))
	for f in list(_ascultatori):
		try:
			f(text, ok, gata)
		except Exception as e:
			_jurnal("ascultator: %r" % (e,))


def stareWeb():
	"""Pentru pagina web: {in_lucru, ok, mesaj, adresa, adresa_fabrica, ultima, fisiere, texte}."""
	s = incarca()
	return {"in_lucru": inLucru(), "ok": bool(s["ok"]), "mesaj": s["text"], "adresa": adresa(),
		"adresa_fabrica": ADRESA_FABRICA, "ultima": textUltima() + ((" " + _("În: %s") % ", ".join(s["fisiere"])) if
			s["cand"] and s["fisiere"] else ""), "cand": s["cand"], "fisiere": list(s["fisiere"]),
		"texte": texteWeb()}


def _textGata(r):
	if r["schimbate"]:
		t = _("Cheile publice sunt aduse: %s.") % textChei(r["chei"])
	else:
		t = _("Cheile publice sunt deja la zi (%s).") % textChei(r["chei"])
	for nume in r["alte"]:
		t += " " + _("%s, pornit de alt program, citește cheile noi după ce îl repornești din programul acela.") % nume
	return t


def porneste(sistem=None, lucrare=None, operatie=None, citire=None, H=None):
	"""La cererea omului (OK pe rand, Verde, butonul din web): aduce cheile pe un fir, apoi reporneste modulele care ruleaza si
	al caror fisier s-a schimbat. False cand merge deja o aducere. Mersul vine la ascultatori si in stareWeb."""
	if inLucru():
		return False
	incarca(sistem)
	H = H or _h()
	if lucrare is None:
		from Components.HdsImportSurse import Lucrare as lucrare
	operatie = operatie or H.Operatie
	adr, semn_vechi = adresa(sistem), _stare["semn"]
	_stare["lucrare"] = True
	_anunta(_("Se aduc cheile publice..."), False, False)

	def reporneste(r, ramase, text):
		if not ramase:
			_anunta(text, True, True)
			return
		fel, sufix = ramase[0]
		if H.in_curs() is not None:
			_anunta(text + " " + _("Repornește %s, ca să citească cheile noi.") % sufix, True, True)
			return

		def dupa(rez):
			if rez.get("ok"):
				t = text + " " + _("%s a fost repornit, ca să citească cheile noi.") % sufix
			else:
				t = text + " " + _("Repornește %s, ca să citească cheile noi.") % sufix
			reporneste(r, ramase[1:], t)
		try:
			_anunta(text + " " + _("Se repornește %s...") % sufix, False, False)
			o = operatie("reporneste", fel=fel, sufix=sufix, la_final=dupa)
			_stare["operatie"] = o
			o.porneste()
		except Exception as e:
			_jurnal("repornirea lui %s: %r" % (sufix, e))
			reporneste(r, ramase[1:], text + " " + _("Repornește %s, ca să citească cheile noi.") % sufix)

	def gata(r, eroare):
		if eroare or not r:
			_anunta(textMotiv("nu_raspunde") if not eroare else _("Cheile publice nu s-au putut aduce: %s.") % eroare,
				False, True)
			return
		if not r.get("ok"):
			_anunta(textMotiv(r.get("motiv"), r.get("cale") or ""), False, True)
			return
		_stare["cand"], _stare["chei"], _stare["fisiere"] = int(time.time()), r["chei"], list(r["fisiere"])
		_stare["semn"] = r.get("semn") or ""
		_salveaza(sistem)
		reporneste(r, list(r["reporniri"]), _textGata(r))

	obiect = lucrare(lambda: aduce(adr, sistem, H, citire, semn_vechi), gata)
	if _stare["lucrare"] is True:
		_stare["lucrare"] = obiect   # tinut in viata pana la sfarsit (eTimer-ul lucrarii)
	return True
