# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com si hdsatelit.com
# SPDX-License-Identifier: GPL-2.0-only
"""Completarile receptorului, din feedul semnat: limba aleasa, ajutorul si recunoasterea textului.

Pune la loc limba si ajutorul pierdute dupa restaurare sau actualizare si aduce ce nu sta in imagine: o limba din cele
din feed (imaginea mica, de la 0.7.4: 15 limbi in imagine, celelalte in feed) si recunoasterea textului (hds-ocr), cand
traducerea subtitrarilor din imagine o cere. Totul din feedul semnat al bazei (stare.json, indexurile semnate, sumele
pachetelor), cu dependintele luate din indexuri, fara nicio intrebare. Reguli:
- se reincearca numai cand lipseste reteaua, opkg e ocupat sau merge o actualizare: la 10 s in primele 3 minute dupa
  pornire sau dupa o alegere a omului, apoi la 5 minute;
- un pachet care nu e in feedul semnat, alta baza sau lipsa locului inseamna "gata pana la pornirea urmatoare", ca
  receptoarele sa nu intrebe serverul la nesfarsit;
- un mesaj mic la inceput (numai cand chiar se instaleaza ceva) si unul la sfarsit.
Fara internet (pasul 4d, 12.11.2026): de pe pagina imaginii omul descarca fisierul hdsatelit-<baza>-<model>-completari.zip
(o bucata din feedul semnat al bazei: stare.json, stare.json.sig, <arh>/Packages intregi si ipk-urile modelului: limbile,
recunoasterea textului, driverele), il copiaza pe stick asa cum e (sau dezarhivat) si baga stickul. Regula: intai
serverul; cand receptorul n-are retea sau serverul nu raspunde (retea fara internet in spatele routerului), fisierul de pe
stick, citit cu aceeasi verificare (semnatura, indexurile semnate, sumele), numai cu alt cititor (SursaStick). Se cauta la
fiecare incercare a ceasului si la fiecare stick bagat (Plugins/SystemPlugins/Hotplug hotplugNotifier, "1"); un fisier
citit o data nu se mai citeste pana la bagarea unui stick. Driverul unui stick Wi-Fi bagat il ia de aici
Components/HdsDriverLipsa (instaleazaDinStick), numai pe al lui, nu toate driverele din fisier."""

import os
import re
import time
import zipfile

CALE = "etc/enigma2/hds-limba-restaurare.json"
PREFIX_PO = "enigma2-hdsatelit-po-"
AJUTOR = "hdsatelit-ajutor"
# recunoasterea textului: programul (cu tesseract si leptonica, ca dependinte) si modelele celor 8 limbi
OCR = ("hds-ocr", "hds-ocr-modele")
BINAR_OCR = "usr/bin/hds-ocr"
_LIMBA = re.compile(r"^[a-z]{2,3}(?:_[A-Za-z0-9-]{1,12})?\Z")
_PACHET = re.compile(
	r"^(?:enigma2-hdsatelit-po-|hdsatelit-ajutor-)[a-z]{2,3}"
	r"(?:-[a-z0-9]{2,8})?\Z")
REINCERCARE_MS = 5 * 60 * 1000
# dupa pornire (cand limba aleasa n-are catalog) sau dupa o alegere: incercari dese, omul tocmai asteapta
REPEDE_MS = 10 * 1000
REPEDE_S = 180
PRIMA_MS = 60 * 1000
# locul pe radacina: indexurile nu au Installed-Size, deci un pachet desfacut se socoteste de 3 ori cat fisierul lui
LOC_FACTOR = 3
LOC_REZERVA = 32 * 1024 * 1024
DURATA_MESAJ_MS = 8000
# fisierul de completari de pe stick (pasul 4d): zip-ul asa cum e descarcat (numele lui poate primi " (1)" de la browser)
# sau dosarul dezarhivat, direct pe stick sau intr-un dosar cu numele zip-ului ("Extrage tot" din Windows)
DOSAR_STICK = "hdsatelit-completari"
_ZIP_STICK = re.compile(r"^hdsatelit-.*completari.*\.zip\Z", re.I)
_DOSAR_DESCARCAT = re.compile(r"^hdsatelit-.*completari", re.I)
# montarile de retea din /media nu se citesc (pot fi lente sau cazute)
MEDIA_SARITE = ("net", "autofs")
_REL = re.compile(r"^[A-Za-z0-9+._~-]+\Z")
# "1" din hotplugNotifier vine inainte de montare (Hotplug: MOUNT_WAIT_MS); o a doua privire pentru stickurile lente
STICK_ASTEPTARE_MS = 10 * 1000
STICK_A_DOUA_MS = 15 * 1000

# pachetele refuzate pana la pornirea urmatoare (nu sunt in feedul semnat, alta baza, fara loc, opkg le-a refuzat)
_FINALE = set()
# cererile din memorie: OCR cerut de traducerea subtitrarilor (HdsOcrSubtitrari.puneLegatura)
_CERERI = {"ocr": False}
_SESIUNE = [None]
# fisierele de pe stick citite deja, (cale, marime, mtime): nu se mai citesc pana la bagarea unui stick
_FOLOSITE = set()
_STICK = {"ceas": None, "a_doua": False, "legatura": None}


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _modul(nume):
	try:
		return __import__("Components." + nume, fromlist=[nume])
	except ImportError:
		return __import__(nume)


def _actualizari():
	return _modul("HdsActualizari")


def _r():
	return _modul("HdsReinstalare")


def _c(rad, rel):
	return os.path.join(rad or "/", *rel.split("/"))


def _cod(limba):
	return "pt-br" if limba == "pt_BR" else limba.split("_", 1)[0]


def _catalog(rad, limba):
	cod = _cod(limba)
	return _c(rad, "usr/share/enigma2/po/%s/LC_MESSAGES/enigma2.mo" % ("pt_BR" if cod == "pt-br" else cod))


def verifica(date):
	if not isinstance(date, dict) or not isinstance(date.get("limba"), str) \
			or not _LIMBA.fullmatch(date["limba"]):
		raise ValueError("limba nu are un cod bun")
	pachete = date.get("pachete")
	if not isinstance(pachete, list) or len(pachete) > 120 or any(
			not isinstance(n, str) or (n != AJUTOR and not _PACHET.fullmatch(n))
			for n in pachete):
		raise ValueError("lista pachetelor limbii nu e buna")
	return {"limba": date["limba"], "pachete": sorted(set(pachete))}


def citeste(rad="/"):
	try:
		return verifica(_r()._citeste_json(_c(rad, CALE)))
	except ValueError:
		return None


def _limba(rad, text=None):
	if text is None:
		try:
			with open(_c(rad, "etc/enigma2/settings"), encoding="utf-8") as f:
				text = f.read(1024 * 1024)
		except OSError:
			text = ""
	for rand in reversed(text.splitlines()):
		cheie, egal, valoare = rand.partition("=")
		if egal and cheie == "config.osd.language" and _LIMBA.fullmatch(valoare):
			return valoare
	return "ro_RO"


def _instalate(rad):
	A = _actualizari()
	inst = set(A.instalate(rad))
	P = _modul("HdsParteaDoua")
	conf = P.citesteConf(rad)
	if conf and P.radacinaNand(rad) and P.esteMontat(rad, conf):
		cale = _c(rad, P.montare(conf).lstrip("/") + "/var/lib/opkg/status")
		inst.update(s["package"] for s in A.P.citeste_strofe(cale)
			if s.get("status", "").split()[-1:] == ["installed"])
	return inst


def stare(rad="/", text_setari=None):
	pachete = [n for n in _instalate(rad) if n == AJUTOR or _PACHET.fullmatch(n)]
	# O copie facuta fara retea pastreaza si cererile neindeplinite.
	pachete += (citeste(rad) or {}).get("pachete", [])
	return verifica({"limba": _limba(rad, text_setari), "pachete": pachete})


def pregateste(rad, date):
	date = verifica(date)
	if citeste(rad) != date:
		_r()._scrie_json(_c(rad, CALE), date)
	return date


def pastreaza(rad="/", limba=None):
	"""Inainte de actualizare: nu pierde cererile inca neindeplinite."""
	date = stare(rad)
	if limba is not None:
		date["limba"] = limba
	return pregateste(rad, date)


def _peStick(rad):
	"""Vu+ Solo SE cu partea a doua: memoria interna (NAND) nu primeste decat limbile, si acelea pe stick"""
	P = _modul("HdsParteaDoua")
	return bool(P.citesteConf(rad) and P.radacinaNand(rad))


def lipsa(rad="/", limba=None, ocr=False):
	"""Pachetele care lipsesc: limba aleasa fara catalog, ajutorul pe care omul il avea si, cand ocr e adevarat
	(traducerea subtitrarilor din imagine o cere), recunoasterea textului."""
	date = citeste(rad)
	limba = limba or _limba(rad)
	if not _LIMBA.fullmatch(limba):
		return []
	cod = _cod(limba)
	inst = _instalate(rad)
	po = PREFIX_PO + cod
	rez = [po] if po not in inst and not os.path.isfile(_catalog(rad, limba)) else []
	# Ajutorul pe limbi se cere numai daca omul il avea deja.
	for n in (date or {}).get("pachete", []):
		if n in (AJUTOR, AJUTOR + "-" + cod) and n not in inst:
			rez.append(n)
	if ocr and not os.access(_c(rad, BINAR_OCR), os.X_OK) and not _peStick(rad):
		rez += [n for n in OCR if n not in inst]
	return sorted(set(rez))


def _oricare(nume):
	return True


# ---------------------------------------------------------------- fisierul de completari de pe stick (fara internet)

def _cheie(cale):
	try:
		st = os.stat(cale)
	except OSError:
		return None
	return (cale, st.st_size, int(st.st_mtime))


def _caleCheie(sursa):
	fel, cale = sursa
	return cale if fel == "zip" else os.path.join(cale, "stare.json")


def candidatiStick(rad="/", toate=False):
	"""[(fel, cale)], fel "zip" sau "dosar": fisierele de completari de pe stickurile si discurile din /media (zip-ul,
	dosarul hdsatelit-completari dezarhivat, direct sau intr-un dosar cu numele zip-ului); fara cele citite deja
	(toate=True: si ele). Numai listari de dosare, fara citiri: merge si pe firul interfetei."""
	rez = []
	media = _c(rad, "media")
	try:
		puncte = sorted(os.listdir(media))
	except OSError:
		return rez
	for p in puncte:
		if p in MEDIA_SARITE:
			continue
		d = os.path.join(media, p)
		try:
			nume = sorted(os.listdir(d))
		except OSError:
			continue
		for n in nume:
			cale = os.path.join(d, n)
			if _ZIP_STICK.match(n) and os.path.isfile(cale):
				rez.append(("zip", cale))
			elif n == DOSAR_STICK and os.path.isfile(os.path.join(cale, "stare.json")):
				rez.append(("dosar", cale))
			elif _DOSAR_DESCARCAT.match(n) and os.path.isfile(os.path.join(cale, DOSAR_STICK, "stare.json")):
				rez.append(("dosar", os.path.join(cale, DOSAR_STICK)))
	if not toate:
		rez = [x for x in rez if _cheie(_caleCheie(x)) not in _FOLOSITE]
	return rez


class SursaStick(object):
	"""Cititorul fisierului de completari, in locul lui urlopen (HdsActualizari._cere, descarca_stare, descarca_pachete,
	HdsParteaDoua.feedSemnat): adresa din feedul bazei (public sau proba) -> fisierul din zip sau din dosar. Ce lipseste
	da OSError, ca o cerere cazuta; o cale cu ".." sau semne straine e refuzata. Zip-ul ramane deschis pana la inchide()."""

	def __init__(self, fel, cale, baza, adresa_feed):
		self.fel, self.cale = fel, cale
		self.zip = None
		self.prefix = ""
		self.prefixe = tuple("%s/%s/%s/" % (adresa_feed, canal, baza) for canal in ("public", "proba"))
		if fel == "zip":
			self.zip = zipfile.ZipFile(cale)
			stari = [n for n in self.zip.namelist() if n == "stare.json" or n.endswith("/stare.json")]
			if not stari:
				self.inchide()
				raise OSError("stare.json lipsește din fișier")
			ales = min(stari, key=lambda n: (n.count("/"), n))
			self.prefix = ales[:-len("stare.json")]

	def cheie(self):
		return _cheie(_caleCheie((self.fel, self.cale)))

	def deschide(self, cerere, timeout=None):
		adresa = getattr(cerere, "full_url", cerere)
		rel = next((adresa[len(p):] for p in self.prefixe if adresa.startswith(p)), None)
		if rel is None or any(not _REL.match(x) or x in (".", "..") for x in rel.split("/")):
			raise OSError("adresă din afara completărilor")
		if self.zip is not None:
			try:
				return self.zip.open(self.prefix + rel)
			except KeyError:
				raise OSError("lipsește din fișier: %s" % rel)
		return open(os.path.join(self.cale, *rel.split("/")), "rb")

	def inchide(self):
		if self.zip is not None:
			try:
				self.zip.close()
			except Exception:
				pass
			self.zip = None


def _desfacut(strofa, marime):
	try:
		return int(strofa.get("installed-size") or 0) or LOC_FACTOR * marime
	except (TypeError, ValueError):
		return LOC_FACTOR * marime


def _instaleaza(rad, pachete, sursa=None):
	"""Aceeasi semnatura si aceleasi fisiere verificate ca la actualizari, cu dependintele din indexurile semnate.
	Intoarce {"puse": [...], "finale": [...] (nu se mai incearca pana la pornirea urmatoare), "amanat": True cand
	merita reincercat (fara retea, opkg ocupat), "loc": (trebuie, liber) in octeti cand n-a incaput, "stick": motivul
	cand fisierul de pe stick nu s-a putut folosi}.
	sursa=(fel, cale) din candidatiStick: fisierul de completari de pe stick in locul serverului (fara credentiale, oricare
	ar fi canalul receptorului: fisierul e facut din feedul public). Un fisier stricat, nesemnat, al altui receptor sau fara
	pachetul cerut nu face nimic final: pachetele asteapta internetul sau alt stick."""
	rez = {"puse": [], "finale": [], "amanat": False, "loc": None, "stick": None}

	def final(nume):
		rez["finale"] = sorted(set(rez["finale"]) | set(nume))
		return rez

	def amanat():
		rez["amanat"] = True
		return rez

	def stick_rau(motiv):
		rez["stick"] = str(motiv) or "?"
		print("[HdsLimbaRestaurare] fisierul de pe stick nu se foloseste: %s" % rez["stick"])
		return amanat()

	def refuzat(motiv):
		return stick_rau(motiv) if sursa is not None else final(pachete)

	A = _actualizari()
	P = _modul("HdsParteaDoua")
	pc = A.P.citeste_configurarea(rad)
	if sursa is None:
		canal, surse, baza = A.canalul(rad, pc)
		if canal not in ("public", "proba") or not surse \
				or baza != A.baza_receptorului(rad):
			return final(pachete)
	else:
		canal, surse, baza = "public", [], A.baza_receptorului(rad)
		if not baza:
			return stick_rau("baza receptorului nu se știe")
	conf = P.citesteConf(rad)
	pe_stick = conf and P.radacinaNand(rad) and P.idLegat(rad)
	lacat = P.ocupaOperatia(rad)
	if lacat is None:
		return amanat()
	dosar = _c(rad, "tmp/hds-limba-restaurare")
	stick = None
	try:
		adresa = A.adresa_stare(canal, baza).rsplit("/", 1)[0]
		deschide = None
		if sursa is not None:
			try:
				stick = SursaStick(sursa[0], sursa[1], baza, A.ADRESA_FEED)
			except (OSError, zipfile.BadZipFile, ValueError) as e:
				_FOLOSITE.add(_cheie(_caleCheie(sursa)))
				return stick_rau(e)
			_FOLOSITE.add(stick.cheie())
			deschide = stick.deschide
		limbi = [n for n in pachete if n.startswith(PREFIX_PO)]
		if pe_stick and limbi:
			# Nu dubleaza in memoria interna limbile destinate stickului.
			ok, _mesaj = P.actualizeazaContinut(rad, lacat=lacat, cerute=limbi, deschide=deschide)
			if not ok:
				return stick_rau(_mesaj) if stick else amanat()
			pachete = [n for n in pachete if n not in limbi]
			rez["puse"] = sorted(set(limbi) & _instalate(rad))
			if not pachete:
				return rez
		credentiale = A.citeste_netrc(rad) if canal == "proba" else None
		server, eroare = A.descarca_stare(adresa + "/stare.json", credentiale, deschide=deschide)
		if eroare:
			return stick_rau(server.get("eroare") or eroare) if stick else amanat()
		if server.get("baza") != baza or server.get("imagine_noua") \
				or server.get("canal", canal) != canal or \
				A.P.compara_versiuni(server.get("imagine_minima", ""), baza) > 0:
			return refuzat("fișierul e pentru altă versiune (%s), receptorul are %s" % (server.get("baza"), baza))
		if stick:
			# arhitecturile din fisier; feedSemnat le pastreaza numai pe ale receptorului (arch.conf)
			surse = [("", "", arh) for arh in sorted(server.get("indexuri") or {})]
		try:
			feed = P.feedSemnat(A, adresa, server, surse, pc, credentiale, deschide)
		except (OSError, ValueError) as e:
			return stick_rau(e) if stick else amanat()
		absente = [n for n in pachete if n not in feed]
		if stick:
			# ce nu e in fisier asteapta internetul (nu e final)
			rez["amanat"] = bool(absente)
		else:
			final(absente)
		pachete = [n for n in pachete if n in feed]
		if not pachete:
			if stick:
				rez["stick"] = "fișierul nu are pachetele cerute"
			return rez
		inst = dict(A.instalate(rad, pc))
		for virtual, furnizori in A.furnizate(rad, pc).items():
			if virtual not in inst and furnizori:
				inst[virtual] = furnizori[0][0] or inst.get(furnizori[0][1], "")
		try:
			plan = P.planContinut(feed, inst, pachete, A, permise=_oricare)
		except ValueError as e:
			return refuzat(e)
		if not plan:
			return rez
		intrari, eroare = A.pachete_semnate({"stare": server},
			{"server": server, "pachete": plan})
		if eroare or A.pachete_straine(intrari, pc.arhitecturi):
			return refuzat(eroare or "pachete pentru alt model")
		nevoie = sum(_desfacut(feed.get(x["nume"]) or {}, x["marime"]) for x in intrari) + LOC_REZERVA
		liber = A.loc_liber(rad or "/")
		if liber is not None and liber < nevoie:
			rez["loc"] = (nevoie, liber)
			return final(pachete)
		cai, eroare = A.descarca_pachete(intrari, adresa, credentiale, dosar, deschide)
		if eroare:
			if stick:
				return stick_rau(eroare[1])
			if eroare[0] == "descarcare":
				return amanat()
			return final(pachete)
		comanda = _r()._opkg(rad, None)
		if not comanda:
			return final(pachete)
		if A.opkg_ocupat(rad) or _actualizare_in_lucru(A):
			return amanat()
		_r()._ruleaza(comanda + ["install"] + cai, 600)
		dupa = _instalate(rad)
		rez["puse"] = sorted(set(rez["puse"]) | (set(pachete) & dupa))
		# ce n-a pus opkg (alt pachet ar scrie peste fisierele lui, o dependinta refuzata) nu se reia la 5 minute
		return final([n for n in pachete if n not in dupa])
	finally:
		A.goleste_dosarul(dosar)
		P.elibereazaOperatia(lacat)
		if stick is not None:
			stick.inchide()


def _actualizare_in_lucru(A):
	actualizare = getattr(A, "actualizari", None)
	return actualizare is not None and (
		actualizare.faza != "liber" or actualizare.repornire)


def lucreaza(rad="/", limba=None, ocr=False):
	"""Intai serverul; fara retea sau cand serverul nu raspunde, fisierul de completari de pe stick (daca e unul necitit)."""
	cerute = [n for n in lipsa(rad, limba, ocr) if n not in _FINALE]
	if not cerute:
		return {"stare": "gata", "puse": [], "cerute": []}
	A = _actualizari()
	if A.opkg_ocupat(rad) or _actualizare_in_lucru(A):
		return {"stare": "amanat", "puse": [], "cerute": cerute}
	rez = None
	puse = []
	if not A.fara_retea(rad):
		rez = _instaleaza(rad, cerute)
		_FINALE.update(rez["finale"])
		puse = list(rez["puse"])
	if rez is None or rez["amanat"]:
		for sursa in candidatiStick(rad):
			ramase = [n for n in cerute if n not in _FINALE and n not in puse]
			if not ramase:
				break
			r = _instaleaza(rad, ramase, sursa)
			_FINALE.update(r["finale"])
			puse += r["puse"]
			r["sursa"] = "stick"
			rez = r
			if not r["stick"]:
				break
	if rez is None:
		return {"stare": "amanat", "puse": [], "cerute": cerute}
	return {"stare": "amanat" if rez["amanat"] else "gata", "puse": sorted(set(puse)), "cerute": cerute,
		"finale": rez["finale"], "loc": rez["loc"], "sursa": rez.get("sursa", "retea"), "stick": rez.get("stick")}


def instaleazaDinStick(pachete, rad="/"):
	"""Components/HdsDriverLipsa: driverul stickului Wi-Fi bagat (pachetul din harta si firmware-ul lui), din fisierul de
	completari de pe stick, cand nu vine din feedul online. Numai pachetele date, cu inchiderea lor din indexul semnat
	al fisierului (nu toate driverele din el). Pe fir separat. Intoarce rezultatul lui _instaleaza si "gasit"."""
	rez = {"puse": [], "finale": [], "amanat": False, "loc": None, "stick": None, "gasit": False}
	for sursa in candidatiStick(rad, toate=True):
		rez = _instaleaza(rad, list(pachete), sursa)
		rez["gasit"] = True
		if rez["puse"] or not rez["stick"]:
			break
	return rez


def _aleasa():
	from Components.config import config
	return config.osd.language.value


def _activeaza():
	from Components.Language import language
	aleasa = _aleasa()
	language.getLanguageList()
	if aleasa in language.lang and language.getActiveLanguage() != aleasa:
		language.activateLanguage(aleasa)


def _ocrCerut():
	"""Firul interfetei: recunoasterea textului e ceruta de traducerea subtitrarilor din imagine (sau de "Mărirea
	subtitrărilor DVB" = OCR, ori de valoarea ei salvata intr-o copie pusa pe o imagine fara OCR)."""
	if _CERERI["ocr"]:
		return True
	try:
		from Components import HdsOcrSubtitrari
		if HdsOcrSubtitrari.esteOcrPornit():
			return True
	except Exception:
		pass
	try:
		from Components.HdsSubtitrariAspect import initConfig
		return initConfig().hds_marire_dvb.saved_value == "ocr"
	except Exception:
		return False


def numeLimba(cod):
	"""Numele limbii ca in lista "Limba meniurilor", in limba in care sunt meniurile acum"""
	try:
		from Components.Language import language
		from Components.language_cache import LANG_TEXT
		date = language.toate.get(cod)
		cheie = "%s_%s" % (date[1], date[2]) if date else cod
		return LANG_TEXT.get(language.getLanguage(), {}).get(cheie) or (date[0] if date else cod)
	except Exception:
		return cod


def textSeDescarca(nume):
	"""Mesajul dupa alegerea unei limbi din feed (meniu, asistent, web)"""
	return _t("Limba %s se descarcă și se instalează singură când receptorul are internet. "
		"Până atunci meniurile sunt în engleză.") % nume


def _parti(limba, cerute):
	parti = []
	if any(n.startswith(PREFIX_PO) for n in cerute):
		parti.append(_t("limba %s") % numeLimba(limba))
	if any(n in OCR for n in cerute):
		parti.append(_t("recunoașterea textului pentru subtitrări"))
	return parti


def _mesaj(text):
	s = _SESIUNE[0]
	if s is None or not text:
		return
	try:
		from Screens import HdsAnuntRetea
		HdsAnuntRetea.arata(s, text, "", DURATA_MESAJ_MS)
	except Exception as e:
		print("[HdsLimbaRestaurare] mesaj: %r" % (e,))


def _probabilLipsa(limba, ocr, rad="/"):
	"""Firul interfetei, fara opkg: ce pare sa lipseasca (catalogul limbii, programul OCR), afara de cele refuzate"""
	rez = []
	if limba and _LIMBA.fullmatch(limba) and not os.path.isfile(_catalog(rad, limba)) \
			and PREFIX_PO + _cod(limba) not in _FINALE:
		rez.append(PREFIX_PO + _cod(limba))
	if ocr and not os.access(_c(rad, BINAR_OCR), os.X_OK) and not (set(OCR) & _FINALE):
		rez += list(OCR)
	return rez


class _Ceas:
	def __init__(self, repede=False):
		from enigma import eTimer
		self.lucrare = None
		self.din_nou = False
		self.anuntat = None
		self.stick_anuntat = None
		self.repede_pana = time.time() + REPEDE_S if repede else 0
		self.ceas = eTimer()
		try:
			self.legatura = self.ceas.timeout.connect(self.verifica)
		except AttributeError:
			self.ceas.callback.append(self.verifica)
		self.ceas.start(REPEDE_MS if repede else PRIMA_MS, True)

	def grabeste(self):
		"""o alegere a omului: incearca acum, apoi des, 3 minute; o lucrare in curs se reia imediat dupa ea"""
		self.repede_pana = time.time() + REPEDE_S
		# o cerere noua (alta limba, OCR, stick bagat): fisierul de pe stick se citeste din nou
		_FOLOSITE.clear()
		if self.lucrare is not None:
			self.din_nou = True
			return
		self.ceas.stop()
		self.verifica()

	def verifica(self):
		from Components.HdsImportSurse import Lucrare
		if self.lucrare is not None:
			return
		aleasa = _aleasa()
		ocr = _ocrCerut()
		self._anunta(aleasa, ocr)
		self.lucrare = Lucrare(lambda: lucreaza(limba=aleasa, ocr=ocr), self.gata)

	def _anunta(self, aleasa, ocr):
		"""Anuntul de inceput, o singura data, numai cand ceva lipseste si receptorul are retea"""
		try:
			cerute = _probabilLipsa(aleasa, ocr)
			# fara sesiune (OCR cerut din legaNucleul inainte de porneste) anuntul asteapta incercarea urmatoare
			if not cerute or _SESIUNE[0] is None:
				return
			if _actualizari().fara_retea("/"):
				# fara retea: numai cand e un fisier de completari necitit pe stick, o data pe stick
				stickuri = tuple(candidatiStick())
				if stickuri and stickuri != self.stick_anuntat:
					self.stick_anuntat = stickuri
					self.anuntat = _parti(aleasa, cerute)
					_mesaj(_t("Am găsit completările pe stick. Se instalează."))
				return
			parti = _parti(aleasa, cerute)
			if parti and self.anuntat != parti:
				self.anuntat = parti
				_mesaj(_t("Se instalează completările receptorului: %s.") % ", ".join(parti))
		except Exception as e:
			print("[HdsLimbaRestaurare] anunt: %r" % (e,))

	def gata(self, rez, eroare):
		self.lucrare = None
		if eroare:
			print("[HdsLimbaRestaurare] reincerc: %s" % type(eroare).__name__)
		# Callbackul este pe firul interfetei, dupa lucrul din fundal.
		try:
			_activeaza()
			self._dupa(rez or {})
		finally:
			if self.din_nou:
				self.din_nou = False
				self.ceas.start(100, True)
			elif eroare or not rez or rez.get("stare") == "amanat":
				self.ceas.start(REPEDE_MS if time.time() < self.repede_pana else REINCERCARE_MS, True)

	def _dupa(self, rez):
		puse = rez.get("puse") or []
		if set(OCR) & set(puse):
			try:
				from Components import HdsOcrSubtitrari
				HdsOcrSubtitrari.dupaInstalare()
			except Exception as e:
				print("[HdsLimbaRestaurare] OCR dupa instalare: %r" % (e,))
		if rez.get("sursa") == "stick" and rez.get("stick") and not puse and self.anuntat is not None:
			# fisierul de pe stick e stricat, nesemnat, al altui model sau al altei versiuni: o data pe stick
			self.anuntat = None
			_mesaj(_t("Fișierul cu completările de pe stick nu se potrivește cu acest receptor (alt model sau altă "
				"versiune) sau este stricat. Descarcă-l din nou de pe pagina imaginii."))
			return
		if self.anuntat is None or (rez.get("stare") == "amanat" and not puse):
			return
		self.anuntat = None
		if rez.get("loc"):
			trebuie, liber = rez["loc"]
			_mesaj(_t("Completările receptorului nu încap: trebuie %d MB liberi, sunt %d MB.") % (
				trebuie // 1048576 + 1, liber // 1048576))
		elif puse:
			_mesaj(_t("Completările receptorului sunt instalate."))
		elif rez.get("finale"):
			_mesaj(_t("Completările receptorului nu se pot instala acum. Receptorul încearcă din nou la următoarea "
				"pornire."))


_CEAS = []


def porneste(session=None, rezultat_copie=None):
	if rezultat_copie and rezultat_copie.get("repornire") == "ceruta":
		return
	if session is not None:
		_SESIUNE[0] = session
	aleasa = _aleasa()
	pastreaza(limba=aleasa)
	_legaHotplug()
	if not _CEAS:
		# limba aleasa fara catalog (actualizare din meniu pe o baza veche, copie pusa pe imaginea mica): des, de la inceput
		_CEAS.append(_Ceas(repede=not os.path.isfile(_catalog("/", aleasa))))


def cereAcum(session=None, spus=False):
	"""Omul a ales o limba fara catalog (meniu, asistent, web): se incearca pe loc, fara intrebare. Firul interfetei.
	spus=True: omul a citit deja ca limba se descarca (meniul si web-ul o spun), deci fara al doilea anunt la inceput;
	mesajul de la sfarsit ramane."""
	if session is not None:
		_SESIUNE[0] = session
	aleasa = _aleasa()
	_FINALE.discard(PREFIX_PO + _cod(aleasa))
	if not _CEAS:
		_CEAS.append(_Ceas(repede=True))
	if spus:
		_CEAS[0].anuntat = _parti(aleasa, [PREFIX_PO + _cod(aleasa)])
	_CEAS[0].grabeste()


def cereOcr():
	"""Traducerea subtitrarilor din imagine cere recunoasterea textului, care lipseste (HdsOcrSubtitrari.puneLegatura,
	la fiecare schimbare de setare si la pornire). O singura cerere; un refuz ramane pana la pornirea urmatoare."""
	if _CERERI["ocr"] or set(OCR) & _FINALE:
		return False
	_CERERI["ocr"] = True
	_porneste_sau_grabeste()
	return True


def _porneste_sau_grabeste():
	if not _CEAS:
		_CEAS.append(_Ceas(repede=True))
	_CEAS[0].grabeste()


# ---------------------------------------------------------------- stickul bagat (fisierul de completari)

def _legaHotplug():
	"""ascultatorul stickurilor (Plugins/SystemPlugins/Hotplug hotplugNotifier), o singura data"""
	try:
		from Plugins.SystemPlugins.Hotplug.plugin import hotplugNotifier
	except Exception as e:
		print("[HdsLimbaRestaurare] hotplug: %r" % (e,))
		return
	if laStick not in hotplugNotifier:
		hotplugNotifier.append(laStick)


def laStick(device, stare):
	"""hotplugNotifier: "1" = stick sau disc bagat, inainte de montare; mai multe partitii = o singura privire"""
	if stare != "1":
		return
	# un stick bagat din nou se citeste din nou
	_FOLOSITE.clear()
	_STICK["a_doua"] = True
	_intarzieStick(STICK_ASTEPTARE_MS)


def _intarzieStick(ms):
	from enigma import eTimer
	if _STICK["ceas"] is None:
		_STICK["ceas"] = eTimer()
		try:
			_STICK["legatura"] = _STICK["ceas"].timeout.connect(stickMontat)
		except AttributeError:
			_STICK["ceas"].callback.append(stickMontat)
	_STICK["ceas"].start(ms, True)


def stickMontat():
	"""dupa montare: daca stickul are fisierul de completari, limba (si ce mai lipseste) si driverul stickului Wi-Fi"""
	gasit = bool(candidatiStick())
	if not gasit and _STICK["a_doua"]:
		_STICK["a_doua"] = False
		_intarzieStick(STICK_A_DOUA_MS)
		return
	_STICK["a_doua"] = False
	if not gasit:
		return
	try:
		# ce s-a refuzat mai devreme din feedul online (de pilda limba nepublicata inca) poate veni de pe stick
		_FINALE.discard(PREFIX_PO + _cod(_aleasa()))
		_FINALE.difference_update(OCR)
		_porneste_sau_grabeste()
	except Exception as e:
		print("[HdsLimbaRestaurare] stick: %r" % (e,))
	try:
		from Components import HdsDriverLipsa
		HdsDriverLipsa.stickNou()
	except Exception as e:
		print("[HdsLimbaRestaurare] driverul de pe stick: %r" % (e,))
