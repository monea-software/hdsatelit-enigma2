# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsListaSetari.py (0.7.5, LCS): setarile aspectului listei de canale, adunate intr-un singur ecran, Setări listă de
# canale (data/setup.xml, cheia hds_lista_canale), deschis din meniul listei (MENU in lista de canale > Setări), din
# Meniu > Setări > Interfață și aspect si din web (/setari?id=hds_lista_canale). Cererile: Ozgur (Vu+ Solo SE, e-mailul
# 6323: totul despre aspectul listei la vedere, marimea siglelor, sistemul de acces, tipul serviciului, fonturile separate,
# bara, coloanele), tfrc (LinuxSat 164126: numerele ascunse, procentul in loc de bara, sigla pentru canalele fara sigla),
# orion_bilo (peretele LinuxSat 7480: canalul de pornire).
#
# Setarile de pana acum (siglele, semnele, randurile pe pagina, marimea textului, bara de progres si pozitia ei, aspectul
# listei) raman in config.usage si in ecranul OSD Preferences; ecranul nou le arata si pe ele (aceleasi elemente).
# Aici sunt numai cele noi, puse pe config.usage la importul modulului (Components/ServiceList.py il importa, deci
# exista inainte de orice ecran de setari si de pagina web):
#   hds_lista_numere          numerele canalelor (Da din fabrica); Nu: coloana numarului dispare si numele incepe la margine
#   hds_lista_marime_nume     marimea numelui canalului, separat (Ca textul listei = Mărimea textului în lista de canale)
#   hds_lista_marime_info     marimea descrierii (emisiunea si semnele)
#   hds_lista_marime_bara     marimea barei de progres (latimea si inaltimea)
#   hds_lista_progres_forma   bara sau procentul emisiunii (nucleul: setProgressPercent; fara el ramane bara)
#   hds_lista_sigla_implicita sigla pentru canalele fara sigla, ca numele sa stea in rand cu celelalte
#   hds_lista_marime_sigle    marimea siglelor din lista (nucleul: setPiconScale)
#   hds_lista_criptare        $ sau sistemul de acces al canalului codat (Viaccess, Nagravision...; nucleul: markCaSystem)
#   hds_lista_tip             tipul serviciului in dreapta randului: SD, HD, UHD, Radio, Date (nucleul: markServiceType)
#   hds_lista_coloane         emisiunea pe o coloana a ei, la aceeasi distanta pe toate randurile (nucleul: setInfoColumn)
#   hds_pornire_canal         canalul ales pentru pornire (config.usage.hds_pornire = "canal"; InfoBarGenerics)
# Ce cere nucleul nou (lib/service/listboxservice.cpp) se cere cu hasattr: pe un nucleu vechi setarea nu face nimic, nu cade.
# Fisierul se poate incarca si pe PC (probele): enigma se importa numai in functii.

import re
import sys
import time

from Components.config import config, ConfigSelection, ConfigYesNo, ConfigText


def N_(text):
	"""Marcaj pentru xgettext; ConfigSelection traduce alegerile la afisare."""
	return text


# marimea fata de textul listei: "text" = ca Mărimea textului în lista de canale, altfel pasi de 10% (-3 = 70%, +5 = 150%)
_PASI = (-3, -2, -1, 1, 2, 3, 4, 5)
ALEGERI_MARIME = [("text", N_("Ca textul listei"))] + [(str(n), "%+d" % n) for n in _PASI]
# marimea siglelor, procent din locul lor de acum (inaltimea randului, cel mult 96 de puncte latime)
MARIMI_SIGLE = (("mica", N_("Mică"), 70), ("tema", N_("După temă"), 100), ("mare", N_("Mare"), 130),
	("foarte_mare", N_("Foarte mare"), 160))
PROCENT_SIGLE = dict((k, p) for k, _t, p in MARIMI_SIGLE)
# coloana emisiunii: unde incepe, procent din latimea randului dupa numar
COLOANA_PROCENT = 45

c = config.usage
if not hasattr(c, "hds_lista_numere"):
	c.hds_lista_numere = ConfigYesNo(default=True)
	c.hds_lista_marime_nume = ConfigSelection(default="text", choices=ALEGERI_MARIME)
	c.hds_lista_marime_info = ConfigSelection(default="text", choices=ALEGERI_MARIME)
	c.hds_lista_marime_bara = ConfigSelection(default="text", choices=ALEGERI_MARIME)
	c.hds_lista_progres_forma = ConfigSelection(default="bara", choices=[
		("bara", N_("Bară")), ("procent", N_("Procent (de pildă 45%)"))])
	c.hds_lista_sigla_implicita = ConfigYesNo(default=False)
	c.hds_lista_marime_sigle = ConfigSelection(default="tema", choices=[(k, t) for k, t, _p in MARIMI_SIGLE])
	c.hds_lista_criptare = ConfigSelection(default="semn", choices=[
		("semn", N_("Semnul „$”")), ("sistem", N_("Sistemul de acces (Viaccess, Nagravision...)"))])
	c.hds_lista_tip = ConfigYesNo(default=False)
	c.hds_lista_coloane = ConfigYesNo(default=False)
	c.hds_pornire_canal = ConfigText(default="")
# 0.7.7 (LST, tamiciav7, LinuxSat 164182 #970755): randul „Current Transponder” (Transponder curent), primul in lista
# buchetelor si in „Sateliți” (Screens/ChannelSelection.hdsArataTransponderul); Nu: randul nu se mai arata, tasta rapida
# „Current Transponder” merge mai departe. Separat de blocul de mai sus, ca sa fie pus si cand blocul exista deja.
if not hasattr(c, "hds_lista_transponder"):
	c.hds_lista_transponder = ConfigYesNo(default=True)
# 0.7.7 (OBU): "Afișează IPTV și alte liste în Buchete". Da (din fabrica, ca in 0.7.4): lista buchetelor (FAV) are si
# dosarul IPTV, dosarele locurilor adaugate de extensii (amandoua sunt si in "Sateliți") si randurile Toate canalele, După
# satelit, După furnizor (si pe pastilele capului listei si pe tastele colorate). Nu: numai buchetele, cum a cerut un tester
# (forumul 768 #2186). Citita de Screens/ChannelSelection.hdsArataDosareleInBuchete si de pagina web /canale (canale_web).
if not hasattr(c, "hds_lista_dosare_buchete"):
	c.hds_lista_dosare_buchete = ConfigYesNo(default=True)
# 0.7.8 (NUM1, tamiciav7, LinuxSat 232449 #501006, Octagon SF8008 0.7.7): "Cifrele duc la numarul canalului". Nu (din
# fabrica, ca pana acum): in lista de canale cifrele sar la prima litera a tastei, ca tastatura unui telefon. Da: cifrele
# duc cursorul la canalul cu acel numar (2, apoi 3 = 23), in buchetul lui (Screens/ChannelSelection.hdsCifraCanal).
# Lista unei retele de cablu duce mereu la numarul operatorului. In web: /setari?id=hds_lista_canale.
if not hasattr(c, "hds_lista_cifre_numar"):
	c.hds_lista_cifre_numar = ConfigYesNo(default=False)


def _varianteSchimbate(el):
	# Numai lantul DVB: rezerva DVB-I isi pastreaza proba si revenirea.
	m = sys.modules.get("Components.HdsDvbIRezerva")
	if m is not None:
		if not el.value:
			m.opresteVariantele()
		m.actualizeazaCeas()


# Variantele DVB: Nu fara valoare salvata.
# True salvat explicit ramane Da. Variantele manuale raman disponibile.
# Acelasi rand setup.xml este folosit si in web.
if not hasattr(c, "hds_variante_singure"):
	c.hds_variante_singure = ConfigYesNo(default=False)
	c.hds_variante_singure.addNotifier(_varianteSchimbate, initial_call=False)


class ConfigRezervaDvbI(ConfigYesNo):
	"""Aceeasi alegere ca in DVB-I, fara o a doua copie in settings."""

	def __init__(self):
		self._alegere = None
		self._initializare = True
		ConfigYesNo.__init__(self, default=True)
		self._initializare = False

	def getValue(self):
		if self._alegere is not None:
			return self._alegere
		try:
			from Components import HdsSalvareLista as S
			return S.valoareRezerva()
		except ImportError:
			return True

	def setValue(self, value):
		if self._initializare:
			return
		vechi = self.getValue()
		self._alegere = bool(value)
		if vechi != self._alegere:
			self.changed()
			self._anunta()

	value = property(getValue, setValue)

	def _anunta(self):
		m = sys.modules.get("Components.HdsDvbIRezerva")
		if m is not None:
			m.rezervaSchimbata(self.value)

	def load(self):
		self._alegere = None
		self.saved_value = None
		self._anunta()

	def cancel(self):
		self.load()
		self.changed()

	def isChanged(self):
		if self._alegere is None:
			return False
		from Components import HdsSalvareLista as S
		return self._alegere != S.valoareRezerva()

	def save(self):
		# La fel ca ConfigElement: numai pregatire in memorie.
		# HdsSalvareLista confirma dupa scrierea si recitirea din fundal.
		self.saved_value = None
		if not self.isChanged():
			self._alegere = None



if not hasattr(c, "hds_dvbi_rezerva"):
	c.hds_dvbi_rezerva = ConfigRezervaDvbI()
# 0.7.7 (SRF, tfrc LinuxSat 164118 #970941): "Calitatea semnalului in bara canalului": dB (din fabrica, ca de la LCF
# incoace) sau procente (ca inainte). O citesc bara intai (Components/Converter/HdsSignal QualityDb / SnrDb) si pagina de
# start din web (HdsCommon.snr_db_serviciu), prin HdsCommon.semnal_in_db, la fiecare tic. In setup.xml in Setări listă de
# canale si in OSD Preferences (langa randul ECM din bara canalului), deci si in web la /setari.
if not hasattr(c, "hds_semnal_unitate"):
	c.hds_semnal_unitate = ConfigSelection(default="db", choices=[("db", N_("dB")), ("procent", N_("Procente (%)"))])
del c


def nucleu_nou():
	"""Nucleul listei din 0.7.5 (setProgressPercent, setPiconScale, setInfoColumn, setServiceTypeLabels)."""
	try:
		from enigma import eListboxServiceContent
		return all(hasattr(eListboxServiceContent, n) for n in ("setProgressPercent", "setPiconScale", "setInfoColumn",
			"setServiceTypeLabels"))
	except ImportError:
		return False


# randurile ecranului care cer nucleul nou (requires="HdsListaNucleu" in data/setup.xml) se arata numai cu el
try:
	from Components.SystemInfo import SystemInfo
	SystemInfo["HdsListaNucleu"] = nucleu_nou()
except ImportError:
	pass


def procent_marime(valoare, procent_text):
	"""Procentul unei marimi separate: "text" -> cel al textului listei, altfel 100 + 10 * pas (70..150)."""
	if valoare in (None, "", "text"):
		return procent_text
	try:
		return min(150, max(70, 100 + 10 * int(valoare)))
	except (TypeError, ValueError):
		return procent_text


def lista_deschisa():
	"""Componenta listei de canale a barei (Components/ServiceList), None cand nu e facuta inca."""
	try:
		from Screens.InfoBar import InfoBar
		ecran = InfoBar.instance and InfoBar.instance.servicelist
		lista = getattr(ecran, "servicelist", None)
		if lista is not None and lista.instance is not None:
			return lista
	except Exception as e:
		print("[HdsListaSetari] lista: %s" % e)
	return None


def reface(configElement=None):
	"""Lista deschisa o data (ecranul ramane in memorie) se potriveste pe loc: marimile, numerele, semnele, siglele."""
	lista = lista_deschisa()
	if lista is None:
		return
	try:
		lista.setMode(lista.mode)
		if hasattr(lista, "hdsSemne"):
			lista.hdsSemne()
		if hasattr(lista.l, "invalidatePicons"):
			lista.l.invalidatePicons()
		if lista.instance is not None:
			lista.instance.invalidate()
	except Exception as e:
		print("[HdsListaSetari] reface: %s" % e)


for _nume in ("hds_lista_numere", "hds_lista_marime_nume", "hds_lista_marime_info", "hds_lista_marime_bara",
		"hds_lista_progres_forma", "hds_lista_sigla_implicita", "hds_lista_marime_sigle", "hds_lista_criptare",
		"hds_lista_tip", "hds_lista_coloane"):
	getattr(config.usage, _nume).addNotifier(reface, initial_call=False)


def reface_transponderul(configElement=None):
	"""0.7.7 (LST): „Afișează Transponder curent” schimbata pe TV sau in web: randul apare sau dispare pe loc in lista
	deschisa (Screens/ChannelSelection.hdsRefaRandulTransponderului), nu abia la urmatoarea umplere."""
	try:
		from Screens.InfoBar import InfoBar
		ecran = InfoBar.instance and InfoBar.instance.servicelist
		refa = getattr(ecran, "hdsRefaRandulTransponderului", None)
		if refa is not None:
			refa()
	except Exception as e:
		print("[HdsListaSetari] randul transponderului: %s" % e)


config.usage.hds_lista_transponder.addNotifier(reface_transponderul, initial_call=False)
# 0.7.7 (OBU): aceeasi refacere pe loc a listei buchetelor deschise cand se schimba dosarele din ea
config.usage.hds_lista_dosare_buchete.addNotifier(reface_transponderul, initial_call=False)


# ---------------------------------------------------------------- sigla pentru canalele fara sigla

TIPURI_RADIO = ("2", "a", "A")
_implicite = {}


def _fisier_sigla(fel):
	"""Sigla lipsei pentru lista: intai cea a temei (picon_lista_<fel>.png), apoi cea a imaginii (skin_default)."""
	if fel in _implicite:
		return _implicite[fel]
	cale = ""
	try:
		from Tools.Directories import resolveFilename, fileExists, SCOPE_CURRENT_SKIN, SCOPE_SKIN_IMAGE
		for scop, nume in ((SCOPE_CURRENT_SKIN, "picon_lista_%s.png" % fel),
				(SCOPE_SKIN_IMAGE, "skin_default/picon_lista_%s.png" % fel)):
			tmp = resolveFilename(scop, nume)
			if fileExists(tmp):
				cale = tmp
				break
	except Exception as e:
		print("[HdsListaSetari] sigla implicita: %s" % e)
	_implicite[fel] = cale
	return cale


def sigla_implicita(sref):
	"""Calea siglei lipsei pentru randul `sref` (text), "" cand setarea e oprita."""
	try:
		if not config.usage.hds_lista_sigla_implicita.value:
			return ""
	except AttributeError:
		return ""
	campuri = (sref or "").split(":")
	fel = "radio" if len(campuri) > 2 and campuri[2] in TIPURI_RADIO else "tv"
	return _fisier_sigla(fel)


# ---------------------------------------------------------------- canalul de pornire

def fara_nume(ref_text):
	"""Referinta fara numele pus la coada (toString() da :Nume cand canalul din buchet are #DESCRIPTION): primele 11
	campuri, ca acelasi canal sa fie acelasi din orice lista, pe televizor si in web."""
	return ":".join((ref_text or "").split(":")[:11])


def canal_pornire():
	"""Referinta (text) a canalului ales pentru pornire, "" cand pornirea nu e pe un canal ales."""
	try:
		if config.usage.hds_pornire.value != "canal":
			return ""
		return config.usage.hds_pornire_canal.value or ""
	except AttributeError:
		return ""


def e_canal_pornire(ref_text):
	return bool(ref_text) and fara_nume(canal_pornire()) == fara_nume(ref_text)


def alege_canal_pornire(ref_text):
	"""Receptorul porneste de acum pe canalul `ref_text`; "" = inapoi la ultimul canal urmarit. -> True cand s-a schimbat
	canalul. 0.7.6 (LPN, TODO 15.11 08:58 (MLW)): un canal cu adresa (internet) se tine intreg, cu numele din lista de la
	coada (nu are alt nume: servicemp3 da gol pentru o adresa); un canal DVB tot fara nume, fiindca nucleul da numele din
	referinta si pentru un canal sters (eStaticServiceDVBInformation::getName), iar pornirea si randul de stare il recunosc
	ca disparut numai fara nume. Canalul se compara tot fara nume (fara_nume)."""
	ref_text = ref_text or ""
	if not _cale(ref_text):
		ref_text = fara_nume(ref_text)
	_NUME_BUCHETE.clear()
	try:
		u = config.usage
		if ref_text:
			if u.hds_pornire.value == "canal" and fara_nume(u.hds_pornire_canal.value) == fara_nume(ref_text):
				# acelasi canal: se pune numai numele din lista, cand il are (canalul de pornire ramane acelasi)
				if u.hds_pornire_canal.value != ref_text and nume_din_referinta(ref_text):
					u.hds_pornire_canal.value = ref_text
					u.hds_pornire_canal.save()
				return False
			u.hds_pornire_canal.value = ref_text
			u.hds_pornire_canal.save()
			u.hds_pornire.value = "canal"
		else:
			if u.hds_pornire.value != "canal" and not u.hds_pornire_canal.value:
				return False
			u.hds_pornire_canal.value = ""
			u.hds_pornire_canal.save()
			if u.hds_pornire.value == "canal":
				u.hds_pornire.value = "last"
		u.hds_pornire.save()
		return True
	except Exception as e:
		print("[HdsListaSetari] canalul de pornire: %s" % e)
		return False


# ---------------------------------------------------------------- numele canalului de pornire (MLW)
# MLW (0.7.5, TODO 15.11 05:05 de la LCS): randul What to show at startup arata si numele canalului ales cand pornirea e
# pe Un canal ales: starea setarii (atributul hdsStare al lui config.usage.hds_pornire, pus de Screens/InfoBarGenerics.py
# langa setare), pe care Screens/Setup.py o scrie deasupra ajutorului si o reciteste cat ecranul e deschis, iar web-ul
# (setari_web, /setari?id=usage si ?id=hds_lista_canale) o arata deasupra randurilor. Alegerea ramane Un canal ales
# (tradusa ca pana acum); numele vine din lista receptorului, deci nu se tine in setari.

def _tr(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _decodeaza(text):
	"""O parte din referinta scrisa de eServiceReference::toString (encode: ':', '%' si semnele sub 32 ca %xx), inapoi."""
	return re.sub(r"%([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), text or "")


def _cale(ref_text):
	"""Adresa (al 11-lea camp) din referinta, "" la un canal DVB."""
	return ((ref_text or "").split(":") + [""] * 11)[10]


def nume_din_referinta(ref_text):
	"""Numele pus la coada referintei (campul de dupa adresa: lista il pune din #DESCRIPTION), "" cand nu are."""
	parti = (ref_text or "").split(":")
	return _decodeaza(":".join(parti[11:])).strip() if len(parti) > 11 else ""


# LPN (0.7.6, TODO 15.11 08:58 de la MLW): un canal de internet (4097, 5001, 5002: adresa in referinta) nu are nume in afara
# buchetului: eStaticServiceMP3Info::getName da gol pentru o adresa "://" (sau capatul caii). Numele se cauta in buchetele
# omului dupa referinta fara nume, cum il arata lista. Tinut minte NUME_BUCHETE_S secunde: Screens/Setup.py reciteste starea
# la 3 s, iar un buchet de internet are zeci de mii de randuri. Cheia: referinta fara nume -> (ora, numele).
_NUME_BUCHETE = {}
NUME_BUCHETE_S = 60
RADACINI_BUCHETE = ('1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "bouquets.tv" ORDER BY bouquet',
	'1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "bouquets.radio" ORDER BY bouquet')
BUCHETE_MAX = 2000
DOSAR_BUCHETE = "/etc/enigma2"
_FISIER_BUCHET = re.compile(r'FROM BOUQUET "([^"/]+)"')


def _e_lenes(fisier):
	"""Grupele de internet ale surselor noastre pe care nucleul le citeste abia la deschidere (lib/dvb/db.cpp isLazyBouquet):
	o lista ceruta aici le-ar tine in memorie pe toate; ele se cauta direct in fisier."""
	return fisier.startswith("subbouquet.hdsiptv_") or fisier == "userbouquet.hdsiptv.tv"


def _cheie_text(ref_text):
	"""Referinta fara nume, ca sa se potriveasca si cu un fisier scris de alta unealta (hex mare, %3A in loc de %3a)."""
	parti = (ref_text or "").split(":")[:11]
	if len(parti) < 11:
		return ""
	return ":".join([p.lower() for p in parti[:10]] + [_decodeaza(parti[10])])


def _nume_din_fisier(fisier, cheie):
	"""Numele canalului `cheie` (_cheie_text) dintr-un fisier de buchet: #DESCRIPTION de dupa #SERVICE, altfel numele din
	referinta. -> (numele, referintele sub-buchetelor din fisier, de cautat dupa el)."""
	try:
		with open("%s/%s" % (DOSAR_BUCHETE, fisier), "rb") as f:
			continut = f.read().decode("utf-8", "replace")
	except (IOError, OSError):
		return "", []
	gasit, nume, sub = False, "", []
	for rand in continut.splitlines():
		if gasit:
			if rand.startswith("#DESCRIPTION"):
				nume = rand[14:] if rand[12:13] == ":" else rand[13:]
			break
		if not rand.startswith("#SERVICE"):
			continue
		ref = (rand[10:] if rand[8:9] == ":" else rand[9:]).strip()
		parti = ref.split(":")
		try:
			steaguri = int(parti[1])
		except (IndexError, ValueError):
			steaguri = 0
		if steaguri & 1:
			sub.append(ref)
		elif _cheie_text(ref) == cheie:
			gasit = True
			nume = nume_din_referinta(ref)
	return (nume.strip() if gasit else ""), sub


def nume_din_buchete(ref_text, acum=None):
	"""Numele canalului `ref_text` din buchetele omului (primul buchet care il are cu nume), "" cand nu e in niciunul.
	O singura lista din C++ pe buchet (getContent "S": referintele ca text, cu numele la coada), apoi sub-buchetele; grupele
	citite la deschidere (_e_lenes) direct din fisier."""
	cheie = fara_nume(ref_text)
	if not cheie:
		return ""
	acum = time.time() if acum is None else acum
	tinut = _NUME_BUCHETE.get(cheie)
	if tinut is not None and 0 <= acum - tinut[0] < NUME_BUCHETE_S:
		return tinut[1]
	nume = ""
	try:
		from enigma import eServiceCenter, eServiceReference
		centru = eServiceCenter.getInstance()
		de_vazut = [eServiceReference(r) for r in RADACINI_BUCHETE]
		vazute = set()
		cheie_t = _cheie_text(cheie)
		tip = cheie.split(":", 1)[0]
		while de_vazut and not nume and len(vazute) < BUCHETE_MAX:
			buchet = de_vazut.pop(0)
			text_b = buchet.toString()
			if text_b in vazute:
				continue
			vazute.add(text_b)
			fisier = _FISIER_BUCHET.search(text_b)
			if fisier is not None and _e_lenes(fisier.group(1)):
				nume, sub = _nume_din_fisier(fisier.group(1), cheie_t)
				de_vazut.extend(eServiceReference(r) for r in sub)
				continue
			lista = centru.list(buchet)
			texte = lista.getContent("S", False) if lista is not None else None
			for t in texte or ():
				parti = t.split(":")
				if len(parti) < 11:
					continue
				try:
					steaguri = int(parti[1])
				except ValueError:
					steaguri = 0
				if steaguri & 1:            # dosar (buchet, sub-buchet): se cauta si in el, dupa cel de acum
					de_vazut.append(eServiceReference(t))
				elif ":".join(parti[:11]) == cheie or (parti[0] == tip and _cheie_text(t) == cheie_t):
					nume = nume_din_referinta(t)
					if nume:
						break
	except Exception as e:
		print("[HdsListaSetari] numele canalului de pornire din buchete: %s" % e)
		nume = ""
	_NUME_BUCHETE[cheie] = (acum, nume)
	return nume


def nume_canal(ref_text):
	"""Numele canalului cu referinta `ref_text` din lista receptorului, "" cand nu se gaseste. 0.7.6 (LPN): la un canal cu
	adresa (internet) intai numele tinut in referinta (pus din lista la alegere), apoi numele din buchetele omului; apoi (si
	la un canal DVB, numai din lista receptorului: gol pentru un canal sters) numele dat de nucleu."""
	if not ref_text:
		return ""
	nume = ""
	if _cale(ref_text):
		nume = nume_din_referinta(ref_text) or nume_din_buchete(ref_text)
	else:
		ref_text = fara_nume(ref_text)
	if not nume:
		try:
			from enigma import eServiceCenter, eServiceReference
			ref = eServiceReference(ref_text)
			info = eServiceCenter.getInstance().info(ref)
			nume = info.getName(ref) if info is not None else ""
		except Exception as e:
			print("[HdsListaSetari] numele canalului de pornire: %s" % e)
			nume = ""
	# semnele de evidentiere din numele canalelor (0x86 / 0x87) nu se arata
	return (nume or "").replace("\x86", "").replace("\x87", "").strip()


def stare_pornire():
	"""Randurile de stare ale setarii What to show at startup: canalul ales, cand pornirea e pe Un canal ales; altfel []."""
	try:
		u = config.usage
		if u.hds_pornire.value != "canal":
			return []
		ref_text = u.hds_pornire_canal.value or ""
	except AttributeError:
		return []
	if not ref_text:
		return [_tr(N_("Niciun canal de pornire ales încă: în lista de canale, MENU pe canal > Pornește pe acest canal. Până atunci "
			"receptorul pornește pe ultimul canal urmărit."))]
	nume = nume_canal(ref_text)
	if not nume:
		return [_tr(N_("Canalul de pornire nu se mai găsește în lista de canale: receptorul pornește pe ultimul canal urmărit."))]
	return [_tr(N_("Canalul de pornire: %s")) % nume]
