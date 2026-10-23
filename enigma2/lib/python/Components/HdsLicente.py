# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsLicente.py: lista licentelor din imagine, citita pentru ecranul „Licențe” (Screens/HdsLicente.py) si pentru pagina
# web /licente (Plugins/Extensions/HdsWebControl/licente_web.py). O singura logica si aceleasi texte in amandoua.
#
# Datele le face construirea (clasa hds-licente din stratul imaginii): /usr/share/hdsatelit/licente/lista.json (un rand
# pe reteta, componentele din pachetele fabricantului, fonturile, listele de canale, pachetele din imagine, build-ul,
# adresa sursei) si texte/<id>.gz (fiecare text de licenta o data; id = primii 16 hexa din sha256 al textului).
#
# Starea listei (proba la rulare):
#   - „lipsa”: nu exista lista.json (o imagine facuta fara clasa hds-licente);
#   - „stricata”: lista.json nu se poate citi sau are alt format;
#   - „veche”: lista e a altui build decat cel din /etc/image-version (enigma2 actualizat dupa construire) sau in
#     /var/lib/opkg/status sunt pachete instalate dupa construire; acestea apar si in lista, la sfarsit, cu licenta
#     scrisa in pachetul lor (/var/lib/opkg/info/<pachet>.control), fara text. Un modul de acces instalat de om apare
#     fara numele pachetului ("Modul de acces"), cu versiunea si licenta lui: imaginea nu arata nume de module de acces.
#     Modulul se recunoaste dupa forma, fara niciun nume scris aici: categoria din numele pachetului
#     (Components/HdsPachete.py, categorie_din_nume) sau un script al felurilor modulelor pus de pachet in /etc/init.d
#     (Components/HdsInterfeteCam.py, feluri_din_nume si e_script_modul), ca la gestiunea modulelor;
#   - „buna”: altfel.
#
# FIRUL: lista.json (cam 80 KB) si starea pachetelor (130 KB de status si fisierele control ale pachetelor noi) se
# citesc pe un fir; cereStare() intoarce ultimul rezultat, fara sa astepte, iar listaTinuta() da lista citita de fir
# (pe firul enigma2 numai un stat()). Lista se tine pana i se schimba data sau marimea; starea se citeste din nou cand
# se schimba data sau marimea lui status, a lui /etc/image-version sau a listei (trei stat() pe firul enigma2), deci un
# pachet instalat sau scos se vede la urmatoarea deschidere. Textele de licenta se despacheteaza la cerere, cate unul:
# cel aratat (textePentru() nu citeste nimic, partiText() citeste un singur text).
#
# Modulul nu importa nimic din enigma2 la incarcare: probele de pe PC dau caile lor.

import gzip
import io
import json
import os
import re
import threading
import time
import zlib

DOSAR = "/usr/share/hdsatelit/licente"
NUME_LISTA = "lista.json"
DOSAR_TEXTE = "texte"
IMAGE_VERSION = "/etc/image-version"
OPKG_STATUS = "/var/lib/opkg/status"
OPKG_INFO = "/var/lib/opkg/info"
# dosarul scripturilor de pornire, in care pachetele modulelor de acces pun scripturile felului lor
DOSAR_SCRIPTURI = "/etc/init.d"
# forma categoriei modulelor de acces in numele pachetului (enigma2-plugin-<categorie>-<nume>), aceeasi ca
# TIPAR_CATEGORIE_ACCES din Components/HdsPachete.py, pentru cand modulul acela nu se poate incarca (probele de pe PC)
_FORMA_ACCES = re.compile(r"^enigma2-plugin-[a-z]+cams-")
# cat se citeste cel mult din lista fisierelor unui pachet (info/<pachet>.list)
MAX_LISTA_PACHET = 1024 * 1024
FORMAT = 1
# adresa codului sursa cand lista lipseste (altfel cea scrisa in lista la construire, HDS_SURSA_ADRESA)
SURSA_IMPLICITA = "https://hdsatelit.com/codul-sursa/"

MAX_LISTA = 4 * 1024 * 1024
MAX_TEXT = 512 * 1024
MAX_STATUS = 4 * 1024 * 1024
# cate randuri are cel mult o parte din textul unei licente pe ecran: ScrollLabel tine cel mult ~64 de pagini, iar
# setText trece textul prin filtrul de surogate pe firul enigma2 (o parte mai mica, o felie mai scurta)
RANDURI_PARTE = 300
# starea pachetelor se citeste din nou si fara schimbare in fisiere, dupa atatea secunde (fisierele control ale
# pachetelor noi nu au stat in cheie)
VARSTA_STARE = 600.0
# limitele de dinainte ale numelui si versiunii pe randul listei, nefolosite: randul arata textul intreg si, cand nu
# incape, deruleaza (lib/gui/elabel.h)
MAX_NUME_RAND = 40
MAX_VERSIUNE_RAND = 18
# expresia licentei pe randul listei; una mai lunga se inlocuieste cu numele clasei (expresia intreaga e sub lista)
MAX_LICENTA_RAND = 34
# cate nume de pachete se scriu sub lista (restul se numara)
MAX_PACHETE_RAND = 3

ID_TEXT = re.compile(r"[0-9a-f]{16}\Z")
NUME_PACHET = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+._-]{0,127}$")
# un hash hexa lung intr-un nume de fisier de licenta (de exemplu comiterea sursei): nu spune nimic omului
HASH_IN_NUME = re.compile(r"[-_.]?[0-9a-f]{20,}[-_.]?")

STARE_BUNA = "buna"
STARE_LIPSA = "lipsa"
STARE_STRICATA = "stricata"
STARE_VECHE = "veche"
# lista nu a fost inca citita de fir (ecranul si pagina arata „Se citește...”)
STARE_CITESTE = "se_citeste"

CLASE = ("fara", "permisiva", "binar", "copyleft-slab", "copyleft", "necunoscuta", "inchisa")

# retetele facute de noi, pentru listele facute inainte de semnul al_nostru din lista.json
RETETE_NOASTRE = ("enigma2-hdsatelit", "hds-navigator", "hds-ocr", "hdsatelit-bootlogo", "hdsatelit-netguard",
	"hdsatelit-skin", "hdsatelit-watchdog")
RETETA_ENIGMA2 = "enigma2-hdsatelit"
# identificatorii de licenta aratati omului cu un cuvant (datele din lista raman neschimbate)
LICENTE_INCHISE = ("CLOSED", "Proprietary")

# limbile imaginii: textele componentelor, fonturilor si listelor sunt in toate
LIMBI = ("cs", "de", "en", "es", "fr", "hu", "it", "nl", "pl", "pt", "ro", "ru", "tr")


def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele din tabel se traduc la folosire."""
	return text


# numele scurt al clasei, pe randul listei si in pagina web
NUME_CLASA = {
	"fara": N_("liberă, fără condiții"),
	"permisiva": N_("liberă"),
	"binar": N_("numai binar"),
	"copyleft-slab": N_("LGPL sau MPL"),
	"copyleft": N_("GPL"),
	"necunoscuta": N_("necunoscută"),
	"inchisa": N_("închisă"),
}

# ce inseamna clasa, in cuvinte simple
CE_INSEAMNA = {
	"fara": N_("Se poate folosi și da mai departe fără nicio condiție."),
	"permisiva": N_("Se poate folosi și da mai departe, cu textul licenței și numele autorilor."),
	"binar": N_("Se dă numai ca program gata făcut, așa cum l-a dat autorul."),
	"copyleft-slab": N_("Codul sursă al bibliotecii se dă mai departe, la adresa codului sursă."),
	"copyleft": N_("Codul sursă se dă mai departe, la adresa codului sursă."),
	"necunoscuta": N_("Licența nu e în lista cunoscută."),
	"inchisa": N_("Program închis, fără cod sursă public."),
}

FEL_RETETA = "reteta"
FEL_COMPONENTA = "componenta"
FEL_FONT = "font"
FEL_LISTA = "lista"
FEL_PACHET = "pachet"


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _jurnal(text):
	print("[HdsLicente] %s" % text)


def limba():
	"""Codul limbii interfetei (una din LIMBI), „en” pentru o limba fara texte, „ro” daca nu se poate afla."""
	try:
		from Components.Language import language
		cod = str(language.getLanguage() or "").split("_")[0].lower()
	except Exception:
		return "ro"
	return cod if cod in LIMBI else "en"


def textAutor():
	"""Randul de sus care spune al cui e imaginea."""
	return _t("Imaginea HDSatelit: Monea Software pentru HD Satelit.")


# ------------------------------------------------------------------ lista.json

_lista = {"cheie": None, "date": None, "eroare": None}
_lacat_lista = threading.Lock()


def citesteLista(dosar=DOSAR):
	"""(date, eroare): lista din <dosar>/lista.json, tinuta pana i se schimba data sau marimea.
	eroare = None | STARE_LIPSA | STARE_STRICATA."""
	cale = os.path.join(dosar, NUME_LISTA)
	try:
		st = os.stat(cale)
	except OSError:
		return None, STARE_LIPSA
	cheie = (cale, st.st_mtime, st.st_size)
	with _lacat_lista:
		if _lista["cheie"] == cheie:
			return _lista["date"], _lista["eroare"]
	date, eroare = None, None
	if st.st_size > MAX_LISTA:
		eroare = STARE_STRICATA
	else:
		try:
			with io.open(cale, "r", encoding="utf-8") as f:
				date = json.load(f)
			if not isinstance(date, dict) or date.get("format") != FORMAT or not isinstance(date.get("retete"), list):
				date, eroare = None, STARE_STRICATA
		except (IOError, OSError, ValueError) as e:
			_jurnal("lista nu se poate citi: %s" % e)
			date, eroare = None, STARE_STRICATA
	with _lacat_lista:
		_lista.update(cheie=cheie, date=date, eroare=eroare)
	return date, eroare


def listaTinuta(dosar=DOSAR):
	"""(date, eroare, gata) fara sa citeasca fisierul: gata = False cat timp firul nu a citit lista sau daca lista s-a
	schimbat de atunci (date si eroare sunt atunci None). Pe firul enigma2 face numai un stat()."""
	cale = os.path.join(dosar, NUME_LISTA)
	try:
		st = os.stat(cale)
	except OSError:
		return None, STARE_LIPSA, True
	cheie = (cale, st.st_mtime, st.st_size)
	with _lacat_lista:
		if _lista["cheie"] == cheie:
			return _lista["date"], _lista["eroare"], True
	return None, None, False


def uitaLista():
	with _lacat_lista:
		_lista.update(cheie=None, date=None, eroare=None)


# ------------------------------------------------------------------ starea: build-ul si pachetele de acum

def buildAcum(cale=IMAGE_VERSION):
	"""version= din /etc/image-version, sau ""."""
	try:
		with io.open(cale, "r", encoding="utf-8", errors="replace") as f:
			for rand in f:
				if rand.startswith("version="):
					return rand.strip().split("=", 1)[1]
	except (IOError, OSError):
		pass
	return ""


def pacheteInstalate(cale=OPKG_STATUS):
	"""{pachet: versiune} pentru pachetele cu „Status: install ... installed” din status-ul opkg, sau None."""
	try:
		if os.path.getsize(cale) > MAX_STATUS:
			return None
		with io.open(cale, "r", encoding="utf-8", errors="replace") as f:
			text = f.read()
	except (IOError, OSError):
		return None
	rez = {}
	for bloc in text.split("\n\n"):
		pachet = versiune = stare = None
		for rand in bloc.split("\n"):
			if rand.startswith("Package:"):
				pachet = rand[8:].strip()
			elif rand.startswith("Version:"):
				versiune = rand[8:].strip()
			elif rand.startswith("Status:"):
				stare = rand[7:].split()
		if pachet and stare and stare[-1] == "installed":
			rez[pachet] = versiune or ""
	return rez


def licentaPachet(pachet, dosar=OPKG_INFO):
	"""campul License: din fisierul control al pachetului instalat, sau ""."""
	if not NUME_PACHET.match(pachet or ""):
		return ""
	try:
		with io.open(os.path.join(dosar, pachet + ".control"), "r", encoding="utf-8", errors="replace") as f:
			for rand in f:
				if rand.startswith("License:"):
					return rand[8:].strip()
	except (IOError, OSError):
		pass
	return ""


def _felurileAcces(scripturi):
	"""Felurile modulelor de acces din dosarul scripturilor (Components/HdsInterfeteCam.py, feluri_din_nume), sau []
	cand dosarul nu se citeste sau modulul acela nu se poate incarca."""
	try:
		nume = os.listdir(scripturi)
	except OSError:
		return []
	try:
		from Components.HdsInterfeteCam import feluri_din_nume
	except Exception:
		return []

	def legatura(n):
		cale = os.path.join(scripturi, n)
		try:
			return os.readlink(cale) if os.path.islink(cale) else None
		except OSError:
			return None
	try:
		return feluri_din_nume(nume, legatura)
	except Exception as e:
		_jurnal("felurile modulelor: %s" % e)
		return []


def esteModulAcces(pachet, info=OPKG_INFO, feluri=None):
	"""Un pachet al unui modul de acces: dupa categoria din nume (Components/HdsPachete.py, categorie_din_nume) sau
	dupa un script al unui fel de modul (feluri, din _felurileAcces) pus de el in DOSAR_SCRIPTURI (lista fisierelor lui
	din info/<pachet>.list are caile receptorului). Fara niciun nume de modul in cod."""
	pachet = pachet or ""
	try:
		from Components.HdsPachete import categorie_din_nume
		if categorie_din_nume(pachet) == "acces":
			return True
	except Exception:
		if _FORMA_ACCES.match(pachet):
			return True
	if not feluri or not NUME_PACHET.match(pachet):
		return False
	try:
		from Components.HdsInterfeteCam import e_script_modul
	except Exception:
		return False
	try:
		with io.open(os.path.join(info, pachet + ".list"), "r", encoding="utf-8", errors="replace") as f:
			text = f.read(MAX_LISTA_PACHET)
	except (IOError, OSError):
		return False
	for rand in text.split("\n"):
		cale = rand.split("\t", 1)[0].strip()
		if cale.rsplit("/", 1)[0] == DOSAR_SCRIPTURI and e_script_modul(cale.rsplit("/", 1)[-1], feluri):
			return True
	return False


def stare(lista, eroare, build, instalate, info=OPKG_INFO, scripturi=DOSAR_SCRIPTURI):
	"""{"stare", "build_lista", "build_acum", "pachete_noi": [{"nume", "versiune", "licenta", "acces"}]}.
	instalate = {pachet: versiune} de acum, sau None (necitit): atunci pachetele nu se compara. acces = pachetul e al
	unui modul de acces (esteModulAcces): pe ecran si in pagina web apare fara numele lui."""
	rez = {"stare": STARE_BUNA, "build_lista": "", "build_acum": build or "", "pachete_noi": []}
	if eroare or lista is None:
		rez["stare"] = eroare or STARE_LIPSA
		return rez
	rez["build_lista"] = lista.get("build") or ""
	if build and rez["build_lista"] != build:
		rez["stare"] = STARE_VECHE
	if instalate is not None:
		la_construire = set(lista.get("instalate") or [])
		noi = sorted(set(instalate) - la_construire)
		feluri = _felurileAcces(scripturi) if noi else []
		for pachet in noi:
			rez["pachete_noi"].append({"nume": pachet, "versiune": instalate[pachet],
				"licenta": licentaPachet(pachet, info), "acces": esteModulAcces(pachet, info, feluri)})
		if rez["pachete_noi"]:
			rez["stare"] = STARE_VECHE
	return rez


def _semn(cale):
	"""(data, marimea) unui fisier, sau None daca lipseste: se schimba cand fisierul e scris din nou"""
	try:
		st = os.stat(cale)
	except OSError:
		return None
	return (st.st_mtime, st.st_size)


class _Cititor(object):
	"""Citirea starii (build-ul, status-ul opkg, licentele pachetelor noi) pe un fir; un singur fir deodata. Rezultatul
	se tine cat timp status, /etc/image-version si lista.json au aceeasi data si marime (cel mult VARSTA_STARE)."""

	def __init__(self):
		self.lacat = threading.Lock()
		self.fir = None
		self.rezultat = None
		self.cand = 0.0
		self.cai = None
		self.semne = None

	def cere(self, dosar, image_version, status, info, din_nou=False):
		cai = (dosar, image_version, status, info)
		semne = (_semn(status), _semn(image_version), _semn(os.path.join(dosar, NUME_LISTA)))
		with self.lacat:
			proaspat = (self.rezultat is not None and self.cai == cai and self.semne == semne
				and time.time() - self.cand < VARSTA_STARE)
			if proaspat and not din_nou:
				return self.rezultat, False
			if self.fir is None:
				self.fir = threading.Thread(target=self._citeste, args=cai + (semne,), name="HdsLicente")
				self.fir.daemon = True
				self.fir.start()
			return (self.rezultat if self.cai == cai else None), True

	def _citeste(self, dosar, image_version, status, info, semne):
		try:
			lista, eroare = citesteLista(dosar)
			rez = stare(lista, eroare, buildAcum(image_version), pacheteInstalate(status), info)
		except Exception as e:
			_jurnal("starea nu se poate citi: %s" % e)
			rez = {"stare": STARE_STRICATA, "build_lista": "", "build_acum": "", "pachete_noi": []}
		with self.lacat:
			self.rezultat = rez
			self.cand = time.time()
			self.cai = (dosar, image_version, status, info)
			self.semne = semne
			self.fir = None


_cititor = _Cititor()


def cereStare(din_nou=False, dosar=DOSAR, image_version=IMAGE_VERSION, status=OPKG_STATUS, info=OPKG_INFO):
	"""(stare sau None, se_citeste): ultima stare citita; porneste citirea pe fir daca fisierele s-au schimbat, daca
	lipseste sau se cere din nou. None cat timp nu s-a terminat prima citire."""
	return _cititor.cere(dosar, image_version, status, info, din_nou)


# ------------------------------------------------------------------ randurile listei

def _scurtat(text, cat):
	text = text or ""
	return text if len(text) <= cat else text[:cat - 3].rstrip() + "..."


def licentaOm(expresie):
	"""Expresia de licenta cu CLOSED si Proprietary scrise „închisă” si Commercial „comercială” (pe ecran si in pagina;
	datele raman neschimbate)."""
	def cuvant(m):
		atom = m.group(0)
		if atom in LICENTE_INCHISE or atom.startswith("Proprietary"):
			return _t("închisă")
		if atom.startswith("Commercial"):
			return _t("comercială")
		return atom
	return re.sub(r"[^\s()&|;]+", cuvant, expresie or "")


def _licentaRand(expresie, clasa):
	"""Licenta pe randul listei: expresia pentru om, sau numele clasei cand expresia e lunga. Un pachet instalat dupa
	construire nu are clasa (licenta e cea scrisa in pachet): expresia lui ramane intreaga (randul deruleaza)."""
	text = licentaOm(expresie)
	if len(text) <= MAX_LICENTA_RAND:
		return text
	if clasa not in NUME_CLASA or clasa == "necunoscuta":
		return text
	return _t(NUME_CLASA[clasa])


def _scurt(nume, versiune, licenta, clasa, cu_prefix=""):
	stanga = ("%s%s %s" % (cu_prefix, nume or "", versiune or "")).strip()
	return "%s  ·  %s" % (stanga, _licentaRand(licenta, clasa))


def _textLimba(valoare, lb):
	if isinstance(valoare, dict):
		return valoare.get(lb) or valoare.get("en") or valoare.get("ro") or ""
	return valoare or ""


def _alNostru(r):
	if "al_nostru" in r:
		return bool(r.get("al_nostru"))
	return (r.get("nume") or "") in RETETE_NOASTRE


def _textePereche(r):
	return [t for t in r.get("texte") or [] if isinstance(t, list) and len(t) == 2]


def _randuriPachete(pachete_noi):
	"""Randurile pachetelor instalate dupa construire. Un modul de acces (acces=True) apare ca "Modul de acces", fara
	numele pachetului si nici in id (id-ul ajunge in legaturile paginii web), cu versiunea si licenta lui."""
	rez = []
	module = 0
	for p in pachete_noi or []:
		licenta = p.get("licenta") or ""
		detaliu = _t("Instalat după construirea imaginii. Licența e cea scrisă în pachet, fără textul ei.")
		if licenta:
			explicatie = _t("Pachetul a fost instalat după construirea imaginii. Licența scrisă în el: %s.") % licenta
		else:
			detaliu += " " + _t("Pachetul nu scrie ce licență are.")
			explicatie = _t("Pachetul a fost instalat după construirea imaginii și nu scrie ce licență are.")
		if p.get("acces"):
			module += 1
			nume, id_rand = _t("Modul de acces"), "p:modul-acces-%d" % module
		else:
			nume, id_rand = p["nume"], "p:%s" % p["nume"]
		rez.append({
			"id": id_rand, "fel": FEL_PACHET, "nume": nume, "versiune": p.get("versiune") or "",
			"licenta": licenta, "licenta_om": licenta or _t("nescrisă în pachet"), "clasa": "", "texte": [],
			"scurt": _scurt(nume, p.get("versiune") or "", licenta or _t("nescrisă în pachet"), ""),
			"detaliu": detaliu, "explicatie": explicatie,
		})
	return rez


def randuri(lista, pachete_noi=None, lb=None):
	"""Randurile ecranului si ale paginii web: modelele OCR descarcate, retetele (alfabetic), componentele din pachetele
	fabricantului, fonturile, listele de canale si, la sfarsit, pachetele instalate dupa construire (_randuriPachete).
	Fiecare rand: id, fel, nume, versiune, licenta (expresia intreaga), licenta_om (aceeasi, cu cuvinte in loc de
	CLOSED), clasa, scurt (textul randului din lista), detaliu (randul de sub lista), texte ([nume, id]), explicatie (ce
	arata OK cand nu are texte)."""
	lb = lb or limba()
	rez = []
	# modelele OCR descarcate dupa construire (Components/HdsOcrModele.py): Apache-2.0, textele retetei hds-ocr-modele
	texte_modele = []
	for r in (lista or {}).get("retete") or []:
		if r.get("nume") == "hds-ocr-modele":
			texte_modele = _textePereche(r)
	try:
		from Components.HdsOcrModele import licenteDescarcate
		descarcate = licenteDescarcate()
	except Exception:
		descarcate = []
	for m in descarcate:
		nume = "hds-ocr-modele-%s" % m["model"]
		detaliu = _t("Modelul OCR pentru %s, descărcat după construirea imaginii. Licența: %s.") % (m["nume"], m["licenta"])
		rez.append({"id": "o:%s" % m["model"], "fel": FEL_PACHET, "nume": nume, "versiune": m["commit"][:8],
			"licenta": m["licenta"], "licenta_om": m["licenta"], "clasa": "permisiva", "texte": texte_modele,
			"scurt": _scurt(nume, m["commit"][:8], m["licenta"], "permisiva"), "detaliu": detaliu,
			"explicatie": "" if texte_modele else detaliu})
	if not lista:
		return rez + _randuriPachete(pachete_noi)
	fonturi_pe_reteta = {}
	for f in lista.get("fonturi") or []:
		if f.get("reteta"):
			fonturi_pe_reteta.setdefault(f["reteta"], []).append(f.get("nume") or "")
	for r in lista.get("retete") or []:
		clasa = r.get("clasa") if r.get("clasa") in CLASE else "necunoscuta"
		licenta = " ; ".join(r.get("licente") or [])
		pachete = r.get("pachete") or []
		nume = r.get("nume") or ""
		if _alNostru(r):
			if nume == RETETA_ENIGMA2:
				cine = _t("Interfața receptorului: enigma2, schimbat de Monea Software pentru HD Satelit.")
			else:
				cine = _t("Făcut de Monea Software pentru HD Satelit.")
			if clasa == "inchisa":
				ce_inseamna = _t("Făcut de Monea Software pentru HD Satelit, fără cod sursă public.")
			else:
				ce_inseamna = "%s %s" % (_t(CE_INSEAMNA[clasa]), cine)
		else:
			ce_inseamna = _t(CE_INSEAMNA[clasa])
		detaliu = "%s %s. %s" % (_t("Licența:"), licentaOm(licenta) or "-", ce_inseamna)
		for font in fonturi_pe_reteta.get(nume, []):
			detaliu += " " + _t("Fontul și licența lui sunt la rândul „Font: %s”.") % font
		if pachete and pachete != [nume]:
			if len(pachete) <= MAX_PACHETE_RAND:
				detaliu += " " + _t("Pachete: %s.") % ", ".join(pachete)
			else:
				detaliu += " " + _t("Pachete: %d (primele: %s).") % (len(pachete),
					", ".join(pachete[:MAX_PACHETE_RAND]))
		rez.append({
			"id": "r:%s" % nume, "fel": FEL_RETETA, "nume": nume, "versiune": r.get("versiune") or "",
			"licenta": licenta, "licenta_om": licentaOm(licenta), "clasa": clasa, "texte": _textePereche(r),
			"scurt": _scurt(nume, r.get("versiune") or "", licenta, clasa),
			"detaliu": detaliu, "explicatie": "" if _textePereche(r) else detaliu,
		})
	for fel, grup, prefix in ((FEL_COMPONENTA, "componente", "c"), (FEL_FONT, "fonturi", "f"),
			(FEL_LISTA, "liste", "l")):
		for i, c in enumerate(lista.get(grup) or []):
			clasa = c.get("clasa") if c.get("clasa") in CLASE else "necunoscuta"
			ce = _textLimba(c.get("ce"), lb)
			licenta = c.get("licenta") or ""
			detaliu = "%s %s %s." % (ce, _t("Licența:"), licentaOm(licenta) or "-")
			if fel == FEL_FONT:
				if c.get("fisier"):
					detaliu += " " + c["fisier"]
				explicatie = "%s\n\n%s %s\n%s %s" % (ce, _t("Licența:"), licentaOm(licenta) or "-", _t("Fișierul:"),
					c.get("fisier") or "-")
				scurt = _scurt(c.get("nume") or "", "", licenta, clasa, _t("Font:") + " ")
			else:
				if c.get("pachet"):
					detaliu += " " + _t("În pachetul %s.") % c["pachet"]
				explicatie = "%s\n\n%s %s\n%s %s\n%s %s" % (ce, _t("Licența:"), licentaOm(licenta) or "-",
					_t("Fișierul:"), c.get("fisier") or "-", _t("Pachetul:"), c.get("pachet") or "-")
				if fel == FEL_COMPONENTA and c.get("pachet"):
					scurt = "%s  (%s)" % (_scurt(c.get("nume") or "", "", licenta, clasa), _t("în pachetul fabricantului"))
				elif fel == FEL_COMPONENTA:
					# aduse de imagine, nu de fabricant (mpegts.js, decodorul wasm al paginii TV in browser)
					scurt = _scurt(c.get("nume") or "", "", licenta, clasa)
				else:
					scurt = _scurt(c.get("nume") or "", "", licenta, clasa, _t("Listă:") + " ")
			if clasa == "inchisa":
				explicatie += "\n\n" + _t("Program închis, dat fără textul unei licențe.")
			rez.append({
				"id": "%s:%d" % (prefix, i), "fel": fel, "nume": c.get("nume") or "", "versiune": "",
				"licenta": licenta, "licenta_om": licentaOm(licenta), "clasa": clasa, "texte": _textePereche(c),
				"scurt": scurt, "detaliu": detaliu, "explicatie": explicatie,
			})
	return rez + _randuriPachete(pachete_noi)


def cauta(randuri_lista, id_rand):
	for r in randuri_lista:
		if r["id"] == id_rand:
			return r
	return None


# ------------------------------------------------------------------ textele

def citesteText(id_text, dosar=DOSAR):
	"""Textul de licenta <id_text> (str), sau None daca id-ul nu e bun, lipseste, e prea mare sau e stricat.
	id-ul se verifica strict (16 hexa, nimic dupa), deci calea ramane in dosarul textelor."""
	if not isinstance(id_text, str) or not ID_TEXT.match(id_text):
		return None
	cale = os.path.join(dosar, DOSAR_TEXTE, id_text + ".gz")
	try:
		with gzip.open(cale, "rb") as g:
			octeti = g.read(MAX_TEXT + 1)
	except (IOError, OSError, EOFError, ValueError, zlib.error):
		return None
	if len(octeti) > MAX_TEXT:
		return None
	for codare in ("utf-8", "latin-1"):
		try:
			text = octeti.decode(codare)
			break
		except UnicodeDecodeError:
			continue
	return text.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n").replace("\t", "    ")


def numeText(nume):
	"""numele unui text pentru om: textele generice SPDX (generic_GPL-2.0-only) poarta numele licentei, iar un hash
	hexa lung din nume (comiterea sursei) se scoate"""
	nume = nume or ""
	if nume.startswith("generic_"):
		nume = nume[8:]
	curat = " ".join(HASH_IN_NUME.sub(" ", nume).split())
	return curat or nume


def textePentru(rand):
	"""[(nume pentru om, id)] textele unui rand, fara sa citeasca vreunul."""
	return [(numeText(n), i) for n, i in _textePereche(rand)]


def bucati(text):
	"""Textul impartit in parti de cel mult RANDURI_PARTE randuri (cel putin o parte)."""
	randuri_text = text.split("\n")
	parti_text = ["\n".join(randuri_text[i:i + RANDURI_PARTE]).strip("\n")
		for i in range(0, len(randuri_text), RANDURI_PARTE)]
	return parti_text or [""]


def partiText(id_text, dosar=DOSAR):
	"""Partile unui singur text (citit acum), sau [explicatia] daca textul lipseste din imagine."""
	text = citesteText(id_text, dosar)
	if text is None:
		return [_t("Textul acestei licențe lipsește din imagine.")]
	return bucati(text)


def explicatieFaraText(rand):
	"""Ce se arata la OK pe un rand fara texte de licenta (acelasi text pe televizor si in pagina web)."""
	if rand.get("explicatie"):
		return rand["explicatie"]
	if rand.get("fel") == FEL_PACHET:
		if rand.get("licenta"):
			return _t("Pachetul a fost instalat după construirea imaginii. Licența scrisă în el: %s.") % rand["licenta"]
		return _t("Pachetul a fost instalat după construirea imaginii și nu scrie ce licență are.")
	if rand.get("clasa") == "inchisa":
		return _t("Program închis, dat fără textul unei licențe.")
	return _t("Textul acestei licențe lipsește din imagine.")


def parti(rand, dosar=DOSAR):
	"""Toate partile textelor unui rand: [(eticheta, text)] (probele de pe PC; ecranul citeste numai textul aratat).
	Un rand fara texte da o singura parte cu explicatia."""
	rez = []
	for nume, id_text in textePentru(rand):
		bucatile = partiText(id_text, dosar)
		for j, bucata in enumerate(bucatile):
			rez.append((nume if len(bucatile) == 1 else "%s (%d/%d)" % (nume, j + 1, len(bucatile)), bucata))
	if not rez:
		rez.append(("", explicatieFaraText(rand)))
	return rez


def linieParte(nume, k, n, j=0, m=1):
	"""Linia de sus a textului: care text (k din n), numele lui si partea (j din m) cand textul e impartit."""
	if m > 1:
		nume = "%s (%d/%d)" % (nume, j + 1, m)
	if n > 1:
		return _t("Textul %d din %d: %s") % (k + 1, n, nume)
	return nume


# ------------------------------------------------------------------ textele de sus

def numeBuild(build):
	"""build-ul din /etc/image-version (0, cifrele versiunii, apoi anul, luna, ziua, ora si minutul comiterii) pe
	intelesul omului: versiunea cu puncte si data "zi.luna.an ora:minut"; altfel neschimbat. Cifrele versiunii sunt
	una pe parte (16 cifre in tot) sau, cand o parte trece de 9, doua pe fiecare parte (19 cifre, 0.3.10)."""
	m = re.match(r"^0(\d)(\d)(\d)(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})$", build or "") or \
		re.match(r"^0(\d{2})(\d{2})(\d{2})(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})$", build or "")
	if not m:
		return build or "-"
	v = m.groups()
	return "%d.%d.%d (%s.%s.%s %s:%s)" % (int(v[0]), int(v[1]), int(v[2]), v[5], v[4], v[3], v[6], v[7])


def texteSus(lista, st, lb=None):
	"""(text, detaliu): starea listei in cuvinte simple (cel mult doua randuri si la literele cele mai mari; la o lista
	veche numai ce s-a schimbat) si adresa codului sursa (un rand)."""
	if st is not None and st.get("stare") == STARE_CITESTE:
		return _t("Se citește lista licențelor..."), ""
	if lista is None:
		text = _t("Lista licențelor lipsește din această imagine.")
		if st is not None and st.get("stare") == STARE_STRICATA:
			text = _t("Lista licențelor din această imagine nu se poate citi.")
		return text, _t("Codul sursă și licențele: %s") % SURSA_IMPLICITA
	if st is not None and st.get("stare") == STARE_VECHE:
		parti_text = []
		if st.get("build_acum") and st.get("build_lista") != st.get("build_acum"):
			parti_text.append(_t("Lista e de la %s, receptorul are %s.") % (numeBuild(st.get("build_lista")),
				numeBuild(st.get("build_acum"))))
		noi = len(st.get("pachete_noi") or [])
		if noi:
			parti_text.append(_t("Pachete instalate după construire: %d, la sfârșitul listei.") % noi)
		text = " ".join(parti_text) or _t("Programele din imagine și licențele lor.")
	else:
		# componentele fabricantului: cele cu pachet (fara mpegts.js si decodorul wasm, aduse de imagine)
		text = _t("Programele din imagine și licențele lor. Programe: %d, componente ale fabricantului: %d, fonturi: %d.") % (
			len(lista.get("retete") or []), len([c for c in lista.get("componente") or [] if c.get("pachet")]),
			len(lista.get("fonturi") or []))
	adresa = lista.get("sursa") or SURSA_IMPLICITA
	detaliu = _t("Codul sursă al versiunii %s: %s") % (lista.get("versiune") or "-", adresa)
	return text, detaliu


def randFaraLista():
	"""Randul din lista cand lista licentelor lipseste sau e stricata: unde sunt licentele."""
	return _t("Licențele programelor din imagine sunt și la adresa de mai sus.")
