# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Lista licentelor din imagine, facuta la construire (clasa hds-licente, pasul de dupa license_create_manifest).

Intrari (toate scrise de OpenEmbedded inainte de pas):
  - license.manifest: pentru fiecare pachet instalat, numele original, versiunea, reteta si expresia de licenta;
  - dosarul licentelor (LICENSE_DIRECTORY, deploy/licenses/<arhitectura>/<reteta>/): textele copiate de do_populate_lic
    din LIC_FILES_CHKSUM si textele generice SPDX (generic_<licenta>);
  - pachetele din radacina, cu numele lor din imagine (libc6) si numele original din license.manifest (glibc);
  - radacina imaginii: /etc/image-version (versiunea care se va vedea pe receptor) si fisierele din componente.json;
  - componente.json de langa acest fisier: componentele din interiorul pachetelor inchise si fonturile, cu texte
    neutre in cele 13 limbi ale imaginii; o componenta intra in lista numai daca fisierul ei exista in radacina;
    textele de licenta ale unei componente sau ale unui font: cele exacte din imagine (texte_in_imagine), altfel
    textul SPDX din licentele comune ale OE (spdx);
    retetele noastre (ale_noastre) primesc in lista semnul al_nostru, iar un font poate numi reteta care il pune.

Iesiri, in <radacina>/usr/share/hdsatelit/licente:
  - lista.json: versiunea, build-ul (version= din /etc/image-version), adresa sursei, un rand pe reteta (versiunea,
    licentele, clasa, pachetele din imagine, textele), componentele, fonturile, listele de canale, pachetele din
    imagine si rezumatul;
  - texte/<id>.gz: fiecare text o singura data (id = primii 16 hexa din sha256 al textului), gzip fara nume si fara
    data in antet, ca doua construiri din aceleasi date sa dea aceiasi octeti.

verifica() e proba care cade: lista lipsa, format necunoscut, alta versiune sau alt build decat imaginea, pachete in
plus sau in minus fata de radacina si de license.manifest, texte lipsa sau schimbate, o licenta pe care clasele de mai
jos nu o recunosc, o reteta libera fara niciun text.

Clasele sunt aceleasi ca in unealta de inventar din depozitul de lucru (licente/inventar_licente.py); o proba pe PC
compara cele doua pe toate expresiile din license.manifest.

Numai biblioteca standard Python 3; ruleaza in bitbake (fara importuri din bb) si pe PC, din linia de comanda."""
import argparse
import fnmatch
import gzip
import hashlib
import io
import json
import os
import re
import sys

FORMAT = 1
DOSAR_LISTA = "usr/share/hdsatelit/licente"
NUME_LISTA = "lista.json"
DOSAR_TEXTE = "texte"
# un text de licenta mai mare de atat nu e text de licenta (un fisier sursa intreg pus in LIC_FILES_CHKSUM)
MAX_TEXT = 512 * 1024

CLASE = ("fara", "permisiva", "binar", "copyleft-slab", "copyleft", "necunoscuta", "inchisa")
RANG = dict((c, i) for i, c in enumerate(CLASE))

# licente fara nicio conditie la redistribuire
FARA = set(["PD", "CC0-1.0", "Unlicense", "0BSD", "MIT-0"])
PERMISIVE = set([
	"MIT", "ISC", "Zlib", "zlib", "curl", "Libpng", "libpng-2.0", "bzip2-1.0.6", "hdparm", "FTL", "IJG", "X11",
	"NTP", "HPND", "BSL-1.0", "WTFPL", "OpenSSL", "SSLeay", "Unicode-TOU", "Unicode-DFS-2016", "Unicode-3.0",
	"Info-ZIP", "Spencer-86", "Beerware", "bzip2", "MIT-CMU", "PostgreSQL", "TCL", "Vim", "Sleepycat", "ICU",
	# fonturile DejaVu (ttf-dejavu din meta-oe, navigatorul web): LICENSE = "BitstreamVera", fara cratima din SPDX
	"BitstreamVera",
])
PREFIXE_PERMISIVE = ("MIT", "BSD-", "Apache-", "PSF-", "Python-", "ZPL-", "AFL-", "OFL-", "Artistic-", "Unicode-",
	"CC-BY-", "OLDAP-", "Bitstream-", "MPL-2.0-no-copyleft", "HPND-")
PREFIXE_SLABE = ("LGPL-", "MPL-", "EPL-", "CDDL-", "GFDL-", "EUPL-", "CPL-")
# licentele Microsoft cu copyleft pe fisier (sursa se da sub aceeasi licenta): socotite ca LGPL/MPL, deci sursa lor
# se pastreaza la construire
SLABE = set(["MS-PL", "MS-RL"])
PREFIXE_COPYLEFT = ("GPL-", "AGPL-")

# fisiere din dosarul unei retete care nu sunt texte de licenta: datele retetei si inlocuitorii pusi de OE pentru
# licentele inchise
FISIERE_FARA_TEXT = ("recipeinfo", "LICENSE-CLOSE", "generic_CLOSED", "generic_Proprietary")


def clasa_licenta(lic):
	"""clasa unui singur identificator de licenta"""
	lic = lic.strip()
	if lic in ("CLOSED", "Proprietary") or lic.startswith("Proprietary") or lic.startswith("Commercial"):
		return "inchisa"
	if lic.startswith("Firmware") or lic.startswith("LICENCE.") or lic.startswith("LicenseRef-Firmware"):
		return "binar"
	if lic in FARA:
		return "fara"
	if lic.startswith(PREFIXE_COPYLEFT):
		return "copyleft"
	if (lic.startswith(PREFIXE_SLABE) and not lic.startswith("MPL-2.0-no-copyleft")) or lic in SLABE:
		return "copyleft-slab"
	if lic in PERMISIVE or lic.startswith(PREFIXE_PERMISIVE):
		return "permisiva"
	return "necunoscuta"


def _atomi(expresie):
	return re.findall(r"[()&|]|[^\s()&|]+", expresie)


class _Parser(object):
	"""expr := termen ('|' termen)* ; termen := factor ('&' factor)* ; factor := '(' expr ')' | ID
	La & se aplica toate licentele (clasa cea mai grea), la | se poate alege (clasa cea mai usoara)."""

	def __init__(self, expresie):
		self.atomi = _atomi(expresie)
		self.poz = 0

	def _urm(self):
		return self.atomi[self.poz] if self.poz < len(self.atomi) else None

	def expr(self):
		variante = [self.termen()]
		while self._urm() == "|":
			self.poz += 1
			variante.append(self.termen())
		return min(variante, key=lambda v: RANG[v[0]])

	def termen(self):
		clasa, ids = self.factor()
		while self._urm() == "&":
			self.poz += 1
			c2, ids2 = self.factor()
			if RANG[c2] > RANG[clasa]:
				clasa = c2
			ids = ids + [i for i in ids2 if i not in ids]
		return clasa, ids

	def factor(self):
		a = self._urm()
		if a is None:
			raise ValueError("expresie de licenta neterminata")
		if a == "(":
			self.poz += 1
			rez = self.expr()
			if self._urm() != ")":
				raise ValueError("paranteza neinchisa")
			self.poz += 1
			return rez
		if a in (")", "&", "|"):
			raise ValueError("semn neasteptat: %s" % a)
		self.poz += 1
		return clasa_licenta(a), [a]


def evalueaza(expresie):
	"""(clasa, licentele care se aplica) pentru o expresie SPDX din license.manifest"""
	p = _Parser(expresie)
	rez = p.expr()
	if p.poz != len(p.atomi):
		raise ValueError("rest necitit in expresia %r" % expresie)
	return rez


def citeste_license_manifest(cale):
	"""lista de dictionare {pachet, versiune, reteta, licenta}, in ordinea din fisier (numai blocurile de pachet)"""
	with io.open(cale, "r", encoding="utf-8") as f:
		text = f.read()
	pachete = []
	for bloc in re.split(r"\n\s*\n", text):
		campuri = {}
		for rand in bloc.strip().split("\n"):
			if ":" in rand:
				k, v = rand.split(":", 1)
				campuri[k.strip()] = v.strip()
		if "PACKAGE NAME" in campuri:
			pachete.append({
				"pachet": campuri["PACKAGE NAME"],
				"versiune": campuri.get("PACKAGE VERSION", ""),
				"reteta": campuri.get("RECIPE NAME", campuri["PACKAGE NAME"]),
				"licenta": campuri.get("LICENSE", ""),
			})
	return pachete


def citeste_instalate(cale):
	"""{nume in imagine: nume original} dintr-un fisier: manifestul imaginii (nume arhitectura versiune) sau perechi
	(nume_in_imagine nume_original). Numele fara pereche raman neschimbate."""
	rez = {}
	with io.open(cale, "r", encoding="utf-8") as f:
		for rand in f:
			parti = rand.split()
			if not parti or parti[0].startswith("#"):
				continue
			rez[parti[0]] = parti[0]
	return rez


def citeste_perechi(cale):
	rez = {}
	with io.open(cale, "r", encoding="utf-8") as f:
		for rand in f:
			parti = rand.split()
			if len(parti) == 2:
				rez[parti[0]] = parti[1]
	return rez


def id_text(octeti):
	return hashlib.sha256(octeti).hexdigest()[:16]


def gzip_stabil(octeti):
	"""gzip fara nume de fisier si cu data 0 in antet: aceiasi octeti la fiecare construire"""
	iesire = io.BytesIO()
	with gzip.GzipFile(filename="", mode="wb", fileobj=iesire, compresslevel=9, mtime=0) as g:
		g.write(octeti)
	return iesire.getvalue()


def dosar_reteta(licente_dir, reteta, arhitecturi):
	"""dosarul cu licentele retetei, cautat in ordinea arhitecturilor (ca license_image.bbclass), apoi in celelalte"""
	cautate = list(arhitecturi)
	try:
		for d in sorted(os.listdir(licente_dir)):
			if d not in cautate:
				cautate.append(d)
	except OSError:
		return None
	for arh in cautate:
		dosar = os.path.join(licente_dir, arh, reteta)
		if os.path.isdir(dosar):
			return dosar
	return None


def texte_reteta(dosar):
	"""[(nume, octeti)]: intai fisierele sursei (COPYING, LICENSE, antete), apoi textele generice SPDX"""
	if not dosar:
		return []
	proprii = []
	generice = []
	for nume in sorted(os.listdir(dosar)):
		if nume in FISIERE_FARA_TEXT:
			continue
		cale = os.path.join(dosar, nume)
		if not os.path.isfile(cale):
			continue
		with open(cale, "rb") as f:
			octeti = f.read(MAX_TEXT + 1)
		if not octeti.strip() or len(octeti) > MAX_TEXT:
			continue
		(generice if nume.startswith("generic_") else proprii).append((nume, octeti))
	return proprii + generice


# limbile imaginii (po/*.po): textele componentelor si ale fonturilor sunt in toate
LIMBI = ("cs", "de", "en", "es", "fr", "hu", "it", "nl", "pl", "pt", "ro", "ru", "tr")


def _text_limba(valoare):
	"""{"ro": ..., "en": ..., "de": ...} (numai limbile imaginii) sau un singur text (acelasi in toate limbile)"""
	if isinstance(valoare, dict):
		return dict((k, v) for k, v in valoare.items() if k in LIMBI and v)
	if valoare:
		return dict((k, valoare) for k in LIMBI)
	return {}


def _exista_in_radacina(radacina, modele):
	"""True daca macar un model (cale absoluta cu * ? [ ] in numele fisierului sau in dosare) are un fisier in
	<radacina>"""
	for model in modele:
		dosar, nume = os.path.split(model.strip("/"))
		if any(c in dosar for c in "*?["):
			# dosar cu model (lib/modules/*/extra): se cauta sub partea fara model
			prefix = re.split(r"[*?\[]", dosar, 1)[0]
			parinte = prefix.rsplit("/", 1)[0] if "/" in prefix else ""
			for curent, _dosare, fisiere in os.walk(os.path.join(radacina, parinte)):
				rel = os.path.relpath(curent, radacina).replace(os.sep, "/")
				if fnmatch.fnmatch(rel, dosar) and fnmatch.filter(fisiere, nume):
					return True
			continue
		try:
			if fnmatch.filter(os.listdir(os.path.join(radacina, dosar)), nume):
				return True
		except OSError:
			continue
	return False


def _text_comun(licente_comune, spdx, texte):
	"""textul SPDX din dosarul licentelor comune ale OE (meta/files/common-licenses), pus in <texte>"""
	if not licente_comune or not spdx:
		return None
	cale = os.path.join(licente_comune, spdx)
	if not os.path.isfile(cale):
		return None
	with open(cale, "rb") as f:
		octeti = f.read(MAX_TEXT + 1)
	if not octeti.strip() or len(octeti) > MAX_TEXT:
		return None
	i = id_text(octeti)
	texte[i] = octeti
	return ["generic_%s" % spdx, i]


def _texte_expresie(licente_comune, intrare, texte):
	"""textele SPDX ale unei componente sau liste: intai cel scris in „spdx” (un nume sau o lista), apoi al fiecarei alte
	licente din expresie (la „A & B” se aplica amandoua, deci trebuie amandoua textele); fara cele inchise, care nu au
	text"""
	ids = intrare.get("spdx") or []
	if not isinstance(ids, list):
		ids = [ids]
	for atom in _atomi(intrare.get("licenta") or ""):
		if atom not in "()&|" and atom not in ids and clasa_licenta(atom) not in ("inchisa", "necunoscuta"):
			ids.append(atom)
	rez = []
	for spdx in ids:
		t = _text_comun(licente_comune, spdx, texte)
		if t and t[1] not in [x[1] for x in rez]:
			rez.append(t)
	return rez


def _text_din_radacina(radacina, cale_rel, texte):
	cale = os.path.join(radacina, cale_rel.lstrip("/"))
	if not os.path.isfile(cale):
		return None
	with open(cale, "rb") as f:
		octeti = f.read(MAX_TEXT + 1)
	if not octeti.strip() or len(octeti) > MAX_TEXT:
		return None
	i = id_text(octeti)
	texte[i] = octeti
	return [os.path.basename(cale_rel), i]


def _clasa_intrare(intrare, erori):
	"""clasa unei componente sau a unui font: cea scrisa in date, altfel cea a licentei"""
	clasa = intrare.get("clasa")
	if not clasa:
		try:
			clasa = evalueaza(intrare["licenta"])[0] if intrare.get("licenta") else "necunoscuta"
		except ValueError:
			clasa = "necunoscuta"
	if clasa not in CLASE or clasa == "necunoscuta":
		erori.append("%s: clasa licentei %r nu se stie (de scris „clasa” in componente.json)" % (intrare.get("nume"),
			intrare.get("licenta")))
		clasa = "necunoscuta"
	return clasa


# pachete pe care OpenEmbedded le scoate din radacina dupa license.manifest (rootfs.py, _uninstall_unneeded):
# run-postinsts, cand nu mai e niciun postinst amanat
SCOASE_DUPA_MANIFEST = ("run-postinsts",)


def construieste(license_manifest, licente_dir, arhitecturi, instalate, radacina, date=None, licente_comune=None,
		versiune="", imagine="", masina="", adresa="", scoase=SCOASE_DUPA_MANIFEST):
	"""(lista, texte, erori): lista gata de scris in lista.json, {id: octeti} si erorile care opresc construirea.
	instalate = {nume in imagine: nume original}, citite din radacina asa cum ramane (dupa _uninstall_unneeded);
	scoase = pachetele din license.manifest care pot lipsi din radacina (nu intra in lista)."""
	erori = []
	date_comp = {}
	if date:
		with io.open(date, "r", encoding="utf-8") as f:
			date_comp = json.load(f)
	ale_noastre = set(date_comp.get("ale_noastre") or [])
	originale = {}
	for nume_imagine, original in instalate.items():
		originale.setdefault(original, []).append(nume_imagine)
	pachete = []
	for p in citeste_license_manifest(license_manifest):
		if p["pachet"] in originale:
			pachete.append(p)
		elif p["pachet"] not in scoase:
			erori.append("pachetul %s e in license.manifest, dar nu in imagine" % p["pachet"])

	texte = {}
	retete = {}
	for p in pachete:
		try:
			clasa, ids = evalueaza(p["licenta"]) if p["licenta"] else ("necunoscuta", [])
		except ValueError as e:
			erori.append("%s: expresia de licenta %r nu se poate citi (%s)" % (p["pachet"], p["licenta"], e))
			clasa, ids = "necunoscuta", []
		r = retete.get(p["reteta"])
		if r is None:
			r = retete[p["reteta"]] = {"nume": p["reteta"], "versiune": p["versiune"], "licente": [],
				"clasa": clasa, "pachete": [], "texte": []}
		if p["pachet"] == p["reteta"]:
			r["versiune"] = p["versiune"]
		for nume_imagine in sorted(originale.get(p["pachet"], [])):
			if nume_imagine not in r["pachete"]:
				r["pachete"].append(nume_imagine)
		if p["licenta"] and p["licenta"] not in r["licente"]:
			r["licente"].append(p["licenta"])
		if RANG[clasa] > RANG[r["clasa"]]:
			r["clasa"] = clasa
		for i in ids:
			if clasa_licenta(i) == "necunoscuta":
				erori.append("%s: licenta %s nu e in nicio clasa (de adaugat in lista_licente.py)" % (p["reteta"], i))

	in_manifest = set(p["pachet"] for p in pachete)
	for nume_imagine, original in sorted(instalate.items()):
		if original not in in_manifest:
			erori.append("pachetul %s (%s) e in imagine, dar nu in license.manifest" % (nume_imagine, original))

	lista_retete = []
	for nume in sorted(retete):
		r = retete[nume]
		dosar = dosar_reteta(licente_dir, nume, arhitecturi)
		for nume_fisier, octeti in texte_reteta(dosar):
			i = id_text(octeti)
			texte[i] = octeti
			# acelasi text sub doua nume (fisierul din sursa si textul generic facut din el, NO_GENERIC_LICENSE) apare o
			# singura data, cu numele din sursa (acela vine intai)
			if i not in [t[1] for t in r["texte"]]:
				r["texte"].append([nume_fisier, i])
		if not r["texte"] and r["clasa"] not in ("inchisa", "fara"):
			erori.append("reteta %s (%s) nu are niciun text de licenta in %s" % (nume, " ; ".join(r["licente"]),
				licente_dir))
		if nume in ale_noastre:
			r["al_nostru"] = True
		lista_retete.append(r)

	componente = []
	fonturi = []
	for c in date_comp.get("componente", []):
		pachet = c.get("pachet")
		if pachet and pachet not in originale and pachet not in instalate:
			continue
		if c.get("cai") and not _exista_in_radacina(radacina, c["cai"]):
			continue
		# textele exacte din imagine (texte_in_imagine, ca la fonturi: de exemplu licentele de langa decodorul wasm al
		# paginii TV in browser) intai; textele SPDX ale OE numai cand lipsesc (sau cu spdx_mereu)
		texte_c = []
		for cale_text in c.get("texte_in_imagine") or []:
			t = _text_din_radacina(radacina, cale_text, texte)
			if t and t not in texte_c:
				texte_c.append(t)
		if not texte_c or c.get("spdx_mereu"):
			for t in _texte_expresie(licente_comune, c, texte):
				if t not in texte_c:
					texte_c.append(t)
		intrare = {"nume": c["nume"], "pachet": pachet or "", "fisier": c.get("fisier", ""),
			"licenta": c.get("licenta", ""), "clasa": _clasa_intrare(c, erori), "ce": _text_limba(c.get("ce")),
			"texte": texte_c}
		componente.append(intrare)
	for f in date_comp.get("fonturi", []):
		if not f.get("cai") or not _exista_in_radacina(radacina, f["cai"]):
			continue
		intrare = {"nume": f["nume"], "fisier": f.get("fisier", ""), "licenta": f.get("licenta", ""),
			"clasa": _clasa_intrare(f, erori), "ce": _text_limba(f.get("ce")), "texte": []}
		if f.get("reteta"):
			intrare["reteta"] = f["reteta"]
		for cale_text in f.get("texte_in_imagine") or []:
			t = _text_din_radacina(radacina, cale_text, texte)
			if t and t not in intrare["texte"]:
				intrare["texte"].append(t)
		# spdx_mereu: fisierul din imagine nu e textul licentei (de exemplu numai numele ei), deci textul SPDX se pune
		# si langa el
		if not intrare["texte"] or f.get("spdx_mereu"):
			t = _text_comun(licente_comune, f.get("spdx"), texte)
			if t and t not in intrare["texte"]:
				intrare["texte"].append(t)
		fonturi.append(intrare)
	# listele de canale (datele din pachete, cu sursa lor): ca o componenta, cu textul SPDX al licentei
	liste = []
	for c in date_comp.get("liste", []):
		pachet = c.get("pachet")
		if pachet and pachet not in originale and pachet not in instalate:
			continue
		if c.get("cai") and not _exista_in_radacina(radacina, c["cai"]):
			continue
		intrare = {"nume": c["nume"], "pachet": pachet or "", "fisier": c.get("fisier", ""),
			"licenta": c.get("licenta", ""), "clasa": _clasa_intrare(c, erori), "ce": _text_limba(c.get("ce")),
			"texte": _texte_expresie(licente_comune, c, texte)}
		liste.append(intrare)

	build = citeste_build(radacina)
	pe_clase = dict((c, 0) for c in CLASE)
	for r in lista_retete:
		pe_clase[r["clasa"]] += 1
	lista = {
		"format": FORMAT,
		"imagine": imagine,
		"versiune": versiune,
		"build": build,
		"masina": masina,
		"sursa": adresa,
		"retete": lista_retete,
		"componente": componente,
		"fonturi": fonturi,
		"liste": liste,
		"instalate": sorted(instalate),
		"redenumite": dict((n, o) for n, o in sorted(instalate.items()) if n != o),
		"texte": dict((i, len(o)) for i, o in texte.items()),
		"rezumat": {"retete": len(lista_retete), "pachete": len(instalate), "pe_clase": pe_clase,
			"texte": len(texte), "octeti_texte": sum(len(o) for o in texte.values())},
	}
	if not build:
		erori.append("/etc/image-version lipseste din radacina sau nu are version=")
	return lista, texte, erori


def citeste_build(radacina):
	"""valoarea version= din /etc/image-version (ce arata receptorul), sau ""."""
	try:
		with io.open(os.path.join(radacina, "etc", "image-version"), "r", encoding="utf-8") as f:
			for rand in f:
				if rand.startswith("version="):
					return rand.strip().split("=", 1)[1]
	except (IOError, OSError):
		pass
	return ""


def _scrie_atomic(cale, octeti):
	nou = cale + ".nou"
	with open(nou, "wb") as f:
		f.write(octeti)
	os.replace(nou, cale)


def text_json(lista):
	return (json.dumps(lista, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def scrie(lista, texte, iesire):
	"""scrie lista.json si texte/<id>.gz in <iesire>; sterge textele ramase de la o rulare veche"""
	dosar_texte = os.path.join(iesire, DOSAR_TEXTE)
	if not os.path.isdir(dosar_texte):
		os.makedirs(dosar_texte)
	pastrate = set()
	for i in sorted(texte):
		nume = "%s.gz" % i
		_scrie_atomic(os.path.join(dosar_texte, nume), gzip_stabil(texte[i]))
		pastrate.add(nume)
	for nume in os.listdir(dosar_texte):
		if nume not in pastrate:
			os.remove(os.path.join(dosar_texte, nume))
	_scrie_atomic(os.path.join(iesire, NUME_LISTA), text_json(lista))
	marime = sum(os.path.getsize(os.path.join(dosar_texte, n)) for n in pastrate)
	marime += os.path.getsize(os.path.join(iesire, NUME_LISTA))
	return marime


def verifica(radacina, license_manifest=None, instalate=None, versiune=None, scoase=SCOASE_DUPA_MANIFEST, dosar=None):
	"""erorile listei din <radacina>: lipsa, format, alta versiune sau alt build decat /etc/image-version, pachete in
	plus sau in minus (fata de <instalate> si de license.manifest), texte lipsa sau schimbate, clase necunoscute.
	Lista goala = lista buna."""
	erori = []
	dosar = dosar or os.path.join(radacina, DOSAR_LISTA)
	cale = os.path.join(dosar, NUME_LISTA)
	if not os.path.isfile(cale):
		return ["lista licentelor lipseste: /%s/%s" % (DOSAR_LISTA, NUME_LISTA)]
	try:
		with io.open(cale, "r", encoding="utf-8") as f:
			lista = json.load(f)
	except (IOError, OSError, ValueError) as e:
		return ["lista licentelor nu se poate citi: %s" % e]
	if not isinstance(lista, dict) or lista.get("format") != FORMAT:
		return ["lista licentelor are alt format decat %d" % FORMAT]
	if versiune is not None and lista.get("versiune") != versiune:
		erori.append("lista e pentru versiunea %r, imaginea e %r" % (lista.get("versiune"), versiune))
	build = citeste_build(radacina)
	if lista.get("build") != build:
		erori.append("lista e pentru build-ul %r, /etc/image-version spune %r" % (lista.get("build"), build))
	in_lista = set()
	for r in lista.get("retete", []):
		in_lista.update(r.get("pachete", []))
		if r.get("clasa") not in CLASE or r.get("clasa") == "necunoscuta":
			erori.append("reteta %s are clasa %r" % (r.get("nume"), r.get("clasa")))
	if set(lista.get("instalate", [])) != in_lista:
		erori.append("pachetele din lista nu se potrivesc cu randurile retetelor")
	if instalate is not None:
		plus = sorted(set(instalate) - in_lista)
		minus = sorted(in_lista - set(instalate))
		if plus:
			erori.append("pachete din imagine care lipsesc din lista: %s" % ", ".join(plus[:20]))
		if minus:
			erori.append("pachete din lista care nu mai sunt in imagine: %s" % ", ".join(minus[:20]))
	if license_manifest is not None:
		redenumite = lista.get("redenumite") or {}
		originale = set(redenumite.get(n, n) for n in in_lista)
		manifest = set(p["pachet"] for p in citeste_license_manifest(license_manifest))
		lipsa = sorted(manifest - originale - set(scoase))
		plus = sorted(originale - manifest)
		if lipsa:
			erori.append("pachete din license.manifest care lipsesc din lista: %s" % ", ".join(lipsa[:20]))
		if plus:
			erori.append("pachete din lista care nu sunt in license.manifest: %s" % ", ".join(plus[:20]))
	folosite = set()
	for grup in ("retete", "componente", "fonturi", "liste"):
		for r in lista.get(grup, []):
			for _nume, i in r.get("texte", []):
				folosite.add(i)
	for i in sorted(folosite | set(lista.get("texte", {}))):
		cale_text = os.path.join(dosar, DOSAR_TEXTE, "%s.gz" % i)
		try:
			with gzip.open(cale_text, "rb") as g:
				octeti = g.read()
		except (IOError, OSError, EOFError) as e:
			erori.append("textul %s lipseste sau e stricat (%s)" % (i, e))
			continue
		if id_text(octeti) != i:
			erori.append("textul %s nu mai are continutul din lista" % i)
	return erori


def main(argv=None):
	ap = argparse.ArgumentParser(description="Lista licentelor din imaginea HDSatelit")
	sub = ap.add_subparsers(dest="comanda")
	fa = sub.add_parser("fa", help="face lista in <radacina>/%s" % DOSAR_LISTA)
	fa.add_argument("--license-manifest", required=True)
	fa.add_argument("--licente-dir", required=True)
	fa.add_argument("--arhitecturi", default="", help="dosarele din licente-dir, in ordinea cautarii, cu virgula")
	fa.add_argument("--instalate", required=True, help="manifestul imaginii (nume arhitectura versiune)")
	fa.add_argument("--perechi", help="perechi „nume_in_imagine nume_original” pentru pachetele redenumite")
	fa.add_argument("--radacina", required=True)
	fa.add_argument("--iesire", help="alt dosar decat <radacina>/%s" % DOSAR_LISTA)
	fa.add_argument("--date")
	fa.add_argument("--licente-comune")
	fa.add_argument("--versiune", default="")
	fa.add_argument("--imagine", default="hdsatelit")
	fa.add_argument("--masina", default="")
	fa.add_argument("--adresa", default="")
	ve = sub.add_parser("verifica", help="proba listei din <radacina>")
	ve.add_argument("--radacina", required=True)
	ve.add_argument("--license-manifest")
	ve.add_argument("--instalate")
	ve.add_argument("--versiune")
	ve.add_argument("--dosar", help="alt dosar al listei decat <radacina>/%s" % DOSAR_LISTA)
	a = ap.parse_args(argv)
	if a.comanda == "fa":
		instalate = citeste_instalate(a.instalate)
		if a.perechi:
			for nume, original in citeste_perechi(a.perechi).items():
				if nume in instalate:
					instalate[nume] = original
		lista, texte, erori = construieste(a.license_manifest, a.licente_dir,
			[x for x in a.arhitecturi.split(",") if x], instalate, a.radacina, a.date, a.licente_comune,
			a.versiune, a.imagine, a.masina, a.adresa)
		iesire = a.iesire or os.path.join(a.radacina, DOSAR_LISTA)
		marime = scrie(lista, texte, iesire)
		rz = lista["rezumat"]
		sys.stdout.write("retete %d, pachete %d, texte %d (%d octeti), in imagine %d octeti\n" % (
			rz["retete"], rz["pachete"], rz["texte"], rz["octeti_texte"], marime))
		for e in erori:
			sys.stdout.write("EROARE: %s\n" % e)
		return 2 if erori else 0
	if a.comanda == "verifica":
		instalate = citeste_instalate(a.instalate) if a.instalate else None
		erori = verifica(a.radacina, a.license_manifest, instalate, a.versiune, dosar=a.dosar)
		for e in erori:
			sys.stdout.write("EROARE: %s\n" % e)
		if not erori:
			sys.stdout.write("lista licentelor e buna\n")
		return 2 if erori else 0
	ap.print_help()
	return 1


if __name__ == "__main__":
	sys.exit(main())
