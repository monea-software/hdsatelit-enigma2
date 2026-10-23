# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsFunctii - lista UNICA a functiilor principale ale receptorului si contactul HD Satelit.
#
# Pagina 2 a asistentului de pornire: 20-30 de functii principale, grupate, scurte si adevarate, fara reparatiile de
# erori; aceeasi lista in "Despre imagine" si pe web. La Despre, si adresa contact@hdsatelit.com pentru intrebari si
# pentru alte modele de receptoare.
#
# O singura lista, folosita de:
#   - Screens/HdsStartWizard.py, pagina 2 (titlul() in FeatureTitle, text() in FeatureText);
#   - Screens/Information.py, HdsAbout ("Despre imagine"), cu randuriContact();
#   - interfata web, /informatii/despre: HdsWebControl/informatii_web.py ia textul chiar din HdsAbout.populate, deci
#     aceeasi lista si acelasi contact, fara cod separat.
#
# Fiecare functie are dovada:
#   - cod=      fisierele sau dosarele din depozitul imaginii care o fac (trebuie sa existe);
#   - versiune= si cuvant=: intrarea din "Ce e nou" (data/jurnal-versiuni.json) a versiunii, in romana, care contine
#     cuvantul; proba teste/test_asistent_despre_028.py le verifica pe toate.
#
# Starea pe receptor sta intr-un singur loc, ca la meniu (Components/HdsStareMeniu.py): atributul stare= al intrarii din
# data/menu.xml. O functie cu meniu= ia starea cea mai rea dintre intrarile ei, la fiecare afisare:
#   "netestat"  functia apare cu semnul "(netestat)", tradus ca in meniu;
#   "in-lucru"  functia nu apare deloc (pe pagina nu se promite nimic).
# Cand semnul se scoate din menu.xml dupa proba pe receptor, el dispare si de aici, fara alta schimbare. O functie fara
# intrare de meniu are starea in probat= (True numai cu proba scrisa pe receptor; altfel "(netestat)").
#
# Nimic din enigma2 la incarcare: modulul se foloseste si din probele de pe PC. Textele se traduc la afisare (_ pus de
# Components/Language.py), deci asistentul le arata in limba aleasa chiar atunci.

import os as _os
import xml.etree.ElementTree as _ET


def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele se traduc la afisare."""
	return text


def _(text):
	"""Traducerea receptorului (builtins._ pus de Components/Language.py); pe PC, textul asa cum e."""
	try:
		import builtins
		f = builtins.__dict__.get("_")
	except Exception:
		f = None
	if f is None or f is _:
		return text
	return f(text)


CONTACT = "contact@hdsatelit.com"
SIT = "https://hdsatelit.com"

TITLU = N_("Funcțiile principale ale receptorului")


class Functie(object):
	__slots__ = ("text", "meniu", "cod", "versiune", "cuvant", "probat")

	def __init__(self, text, meniu=(), cod=(), versiune="", cuvant="", probat=False):
		self.text = text
		self.meniu = tuple(meniu)
		self.cod = tuple(cod)
		self.versiune = versiune
		self.cuvant = cuvant
		self.probat = probat


# (titlul grupei, functiile ei). Textele: romana simpla, "tu", fiecare cate un rand scurt; "receptorul", nu "imaginea".
# probat= conteaza numai fara meniu=; fiecare functie are o proba scrisa pe receptor.
GRUPE = (
	(N_("Canale și recepție"), (
		Functie(N_("Radiourile DAB+ din satelit: le cauți și le asculți ca pe orice post de radio."),
			meniu=("hds_satelit_dab",), cod=("lib/python/Screens/ScanerSatelit.py", "lib/python/Hds/DabT2/dab"),
			versiune="0.2.1", cuvant="DAB+ din satelit se aud"),
		Functie(N_("Canalele DVB-T2 din satelit: le cauți și le vezi ca pe orice canal."),
			meniu=("hds_satelit_dvbt2",), cod=("lib/python/Screens/ScanerSatelit.py", "lib/python/Hds/DabT2/t2"),
			versiune="0.2.2", cuvant="DVB-T2 prin satelit"),
		Functie(N_("Scanare detaliată: fiecare canal pornit pe rând, cu rezoluția, codarea și pistele."),
			meniu=("hds_culegere_canale",), cod=("lib/python/Screens/HdsCulegereTotala.py",
			"lib/python/Components/HdsCulegereTotala.py"), versiune="0.2.2", cuvant="Scanare detaliată"),
		Functie(N_("Căutare de canale după nume, limba sunetului sau a subtitrării, teletext sau HbbTV."),
			cod=("lib/python/Screens/HdsCautareCanale.py", "lib/python/Components/HdsPisteCanale.py"),
			versiune="0.1.4", cuvant="după limbile pistelor", probat=True),
		Functie(N_("Favorite dintr-o apăsare: tasta FAV pune canalul în Favorite sau îl scoate."),
			cod=("lib/python/Components/HdsFavorite.py",), versiune="0.2.7", cuvant="Favorite dintr-o apăsare"),
		Functie(N_("Configurare LNB cu probă de semnal: setările noi rămân numai după ce confirmi."),
			meniu=("hds_antena_lnb",), cod=("lib/python/Screens/ConfigLNB.py", "lib/python/Components/HdsLnbAplicare.py"),
			versiune="0.1.2", cuvant="Configurare LNB"),
		Functie(N_("Rotirea antenei desenată pe ecran: sateliții pe arc, plecarea, ținta și raza."),
			meniu=("hds_antena_rotire",), cod=("lib/python/Screens/HdsDishMotor.py",), versiune="0.1.3",
			cuvant="Rotirea antenei e desenată"),
	)),
	(N_("Subtitrări și traducere"), (
		Functie(N_("Traducerea automată a subtitrărilor în limba ta: teletext, DVB și fișiere."),
			meniu=("hds_traducere_subtitrari",), cod=("lib/python/Components/HdsTraducereSubtitrari.py",
			"lib/python/Screens/HdsTraducereSubtitrari.py"), versiune="0.1.8", cuvant="se pot traduce automat"),
		Functie(N_("Ghidul de programe și bara de jos, traduse automat în limba ta."),
			meniu=("hds_traducere_subtitrari",), cod=("lib/python/Components/HdsTraducereEpg.py",),
			versiune="0.1.9", cuvant="Tradu EPG"),
		Functie(N_("Subtitrările DVB mărite la mărimea ecranului, cu margini clare."),
			cod=("lib/gui/esubtitle.cpp", "lib/gdi/gpixmap.cpp"), versiune="0.1.3", cuvant="Subtitrările DVB se măresc",
			probat=True),
		Functie(N_("Subtitrările DVB citite ca text, ca să poată fi traduse și scrise cu literele tale."),
			meniu=("hds_subtitrari_aspect",), cod=("lib/python/Components/HdsOcrSubtitrari.py",), versiune="0.1.6",
			cuvant="Subtitrările DVB citite ca text"),
		Functie(N_("Aspectul subtitrărilor: mărimea, culoarea, conturul, umbra și fundalul."),
			meniu=("hds_subtitrari_aspect",), cod=("lib/python/Screens/HdsSubtitrariAspect.py",), versiune="0.1.3",
			cuvant="Aspectul subtitrărilor"),
	)),
	(N_("Navigator web și HbbTV"), (
		# 0.2.8: HbbTV e oprit din fabrica (config.plugins.hdsnavigator.hbbtv, randul "HbbTV
		# (aplicatiile canalelor)" din Setari navigator web), deci randul spune de unde se porneste
		Functie(N_("HbbTV, aplicațiile canalelor la tasta ROȘIE: îl pornești din Setări navigator web."),
			cod=("lib/python/Components/HdsHbbtv.py", "lib/python/Components/HdsHbbtvPornire.py",
			"lib/python/Plugins/Extensions/HdsNavigator/setari.py"), versiune="0.2.6",
			cuvant="tasta ROȘIE pornește aplicația", probat=True),
		Functie(N_("Navigator web pe televizor, cu telecomanda: indicator ca un mouse și tastatură pe ecran."),
			meniu=("hds_navigator_web",), cod=("lib/python/Screens/HdsNavigatorWeb.py",
			"lib/python/Plugins/Extensions/HdsNavigator"), versiune="0.2.6", cuvant="Navigatorul web e acum în receptor"),
	)),
	(N_("Telefon și interfața web"), (
		Functie(N_("Interfață web proprie: fiecare ecran al receptorului are pereche în browser."),
			meniu=("hds_webcontrol_setup",), cod=("lib/python/Plugins/Extensions/HdsWebControl/plugin.py",
			"lib/python/Plugins/Extensions/HdsWebControl/meniu_web.py"), versiune="0.1.4", cuvant="pereche în interfața web"),
		Functie(N_("Browserul intră numai cu un cod de șase cifre arătat pe televizor."),
			meniu=("hds_webcontrol_setup",), cod=("lib/python/Plugins/Extensions/HdsWebControl/asociere.py",
			"lib/python/Screens/HdsCodAsociere.py"), versiune="0.1.0", cuvant="cod de șase cifre"),
		Functie(N_("Aplicațiile de telefon pentru receptoare: telecomandă, canale, ghid și înregistrări."),
			cod=("lib/python/Plugins/Extensions/HdsWebControl/aplicatii_web.py",), versiune="0.2.4",
			cuvant="Aplicațiile de telefon pentru receptoare", probat=True),
		Functie(N_("Înregistrările se văd și pe telefon, chiar și cât se înregistrează."),
			cod=("lib/python/Plugins/Extensions/HdsWebControl/aplicatii_web.py",), versiune="0.2.5",
			cuvant="Înregistrările se văd și pe telefon"),
	)),
	(N_("Radio și afișaj"), (
		Functie(N_("Ecranul radio pe tot ecranul: piesa, textul radio, bare de sunet și egalizator."),
			meniu=("hds_ecran_radio", "hds_egalizator"), cod=("lib/python/Screens/HdsEcranRadio.py",
			"lib/python/Screens/HdsEgalizator.py"), versiune="0.1.5", cuvant="Ecranul radio pe tot ecranul"),
		Functie(N_("Afișajul din față arată pe rând ora, canalul, semnalul și peste o sută de alte date."),
			meniu=("hds_afisaj",), cod=("lib/python/Screens/HdsAfisaj.py", "lib/python/Components/HdsAfisajDate.py"),
			versiune="0.1.6", cuvant="peste o sută de alte date"),
	)),
	(N_("Setări și siguranță"), (
		Functie(N_("Caută setări: scrii câteva litere cu cifrele telecomenzii și ajungi la setare."),
			meniu=("hds_cauta_setari",), cod=("lib/python/Screens/HdsCautaSetari.py",
			"lib/python/Components/HdsCautaSetari.py"), versiune="0.2.4", cuvant="Caută setări"),
		Functie(N_("Copia setărilor pe stick, pusă singură la loc după o actualizare."),
			meniu=("hds_copie_setari",), cod=("lib/python/Components/HdsCopieSetari.py",
			"lib/python/Screens/HdsCopieSetari.py"), versiune="0.2.2", cuvant="pune singură copia la loc"),
		Functie(N_("Mod sigur: după opriri neașteptate repetate, receptorul pornește fără extensii."),
			meniu=("hds_mod_sigur",), cod=("lib/python/Screens/HdsModSigur.py", "lib/python/Components/HdsModSigur.py"),
			versiune="0.1.6", cuvant="pornește în mod sigur"),
		Functie(N_("Telecomenzi: proba tastelor pe telecomanda desenată și o telecomandă USB asociată."),
			meniu=("hds_telecomenzi",), cod=("lib/python/Screens/HdsTelecomenzi.py",), versiune="0.1.2",
			cuvant="Utilitar pentru telecomenzi"),
		Functie(N_("Meniurile traduse complet în 13 limbi."),
			meniu=("language_setup",), cod=("po/ro.po", "po/de.po", "po/tr.po"), versiune="0.1.0",
			cuvant="tradusă în treisprezece limbi"),
	)),
)

# contactul de la Despre: intrebarile si alte modele de receptoare, cu conditiile; fara nume
CONTACT_TITLU = N_("Contact")
CONTACT_INTREBARI = N_("Pentru întrebări: %s")
CONTACT_SIT = N_("Situl: %s")
CONTACT_ALTE_RECEPTOARE = N_("Vrei HD Satelit și pe alt model de receptor? Scrie-ne la %s. Avem nevoie de receptor, "
	"dat gratuit și definitiv, și de driverele și tot ce mai trebuie de la producător.")


# ------------------------------------------------------------------ starea din menu.xml

CALE_MENIU = None          # probele pun aici un menu.xml; pe receptor resolveFilename(SCOPE_SKIN, "menu.xml")
_CACHE = {}
_GRAD = {None: 0, "netestat": 1, "in-lucru": 2}


def caleMeniu():
	if CALE_MENIU:
		return CALE_MENIU
	try:
		from Tools.Directories import resolveFilename, SCOPE_SKIN
		return resolveFilename(SCOPE_SKIN, "menu.xml")
	except Exception:
		return "/usr/share/enigma2/menu.xml"


def stariMeniu(cale=None):
	"""{entryID: stare} pentru toate intrarile din menu.xml (stare None = fara semn), sau None daca fisierul nu se
	poate citi. Citit o data si din nou numai cand se schimba fisierul."""
	from Components import HdsStareMeniu
	cale = cale or caleMeniu()
	try:
		semn = _os.path.getmtime(cale)
	except OSError:
		return None
	vechi = _CACHE.get(cale)
	if vechi is not None and vechi[0] == semn:
		return vechi[1]
	try:
		radacina = _ET.parse(cale).getroot()
	except Exception as eroare:
		print("[HdsFunctii] nu pot citi %s: %s" % (cale, eroare))
		_CACHE[cale] = (semn, None)
		return None
	stari = {}
	for nod in radacina.iter():
		if nod.tag in ("item", "menu") and nod.get("entryID"):
			stari[nod.get("entryID")] = HdsStareMeniu.stare(nod)
	_CACHE[cale] = (semn, stari)
	return stari


def stareFunctie(f, stari):
	"""None (gata, probata pe receptor), "netestat" sau "in-lucru". Cu meniu=: starea cea mai rea dintre intrari; o
	intrare care lipseste din meniu sau un meniu care nu se poate citi dau "netestat" (nu se afirma ce nu se vede)."""
	if not f.meniu:
		return None if f.probat else "netestat"
	rea = None
	for intrare in f.meniu:
		if stari is None or intrare not in stari:
			s = "netestat"
		else:
			s = stari[intrare]
		if _GRAD.get(s, 1) > _GRAD.get(rea, 0):
			rea = s
	return rea


# ------------------------------------------------------------------ textele

def _limba():
	try:
		from Components.Language import language
		return language.getActiveLanguage() or ""
	except Exception:
		return ""


def majuscule(text, limba=None):
	"""Titlu cu majuscule; in turca "i" devine "İ", nu "I"."""
	if limba is None:
		limba = _limba()
	if limba.startswith("tr"):
		text = text.replace("i", "İ")
	return text.upper()


def grupe(traducere=None, stari=None, cale_meniu=None):
	"""[(titlul grupei tradus, [functia tradusa, cu semnul starii, ...]), ...]; functiile "in-lucru" lipsesc, iar o
	grupa ramasa goala nu apare."""
	from Components import HdsStareMeniu
	tr = traducere or _
	if stari is None:
		stari = stariMeniu(cale_meniu)
	rez = []
	for titlu, functii in GRUPE:
		randuri = []
		for f in functii:
			s = stareFunctie(f, stari)
			if s == "in-lucru":
				continue
			randuri.append(HdsStareMeniu.cuSemn(tr(f.text), s, tr))
		if randuri:
			rez.append((tr(titlu), randuri))
	return rez


def titlu(traducere=None):
	return (traducere or _)(TITLU)


def text(rand="  - ", titluri_mari=True, intre="\n", traducere=None, stari=None, cale_meniu=None, limba=None):
	"""Lista ca text, grupa cu grupa: titlul grupei (cu majuscule pe televizor), apoi cate un rand pe functie cu
	prefixul `rand`; grupele despartite de `intre` (un rand gol). Fara acolade: textul nu trece prin .format()."""
	bucati = []
	for t, randuri in grupe(traducere, stari, cale_meniu):
		cap = majuscule(t, limba) if titluri_mari else t
		bucati.append("\n".join([cap] + [rand + r for r in randuri]))
	return (intre + "\n").join(bucati) if intre else "\n".join(bucati)


def randuriContact(traducere=None):
	"""Randurile contactului, traduse: intrebarile, situl, alte modele de receptoare."""
	tr = traducere or _
	return [
		tr(CONTACT_INTREBARI) % CONTACT,
		tr(CONTACT_SIT) % SIT,
		tr(CONTACT_ALTE_RECEPTOARE) % CONTACT,
	]


def toateTextele():
	"""Toate textele de tradus ale modulului (pentru probe si pentru scriptul traducerilor)."""
	texte = [TITLU]
	for t, functii in GRUPE:
		texte.append(t)
		texte.extend(f.text for f in functii)
	texte.extend([CONTACT_TITLU, CONTACT_INTREBARI, CONTACT_SIT, CONTACT_ALTE_RECEPTOARE])
	return texte
