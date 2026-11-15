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
	"""Receptorul porneste de acum pe canalul `ref_text`; "" = inapoi la ultimul canal urmarit. -> True cand s-a schimbat."""
	ref_text = fara_nume(ref_text)
	try:
		u = config.usage
		if ref_text:
			if u.hds_pornire.value == "canal" and u.hds_pornire_canal.value == ref_text:
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


def nume_canal(ref_text):
	"""Numele canalului cu referinta `ref_text` din lista receptorului, "" cand nu se gaseste."""
	if not ref_text:
		return ""
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
		return [_tr("Niciun canal de pornire ales încă: în lista de canale, MENU pe canal > Pornește pe acest canal. Până atunci "
			"receptorul pornește pe ultimul canal urmărit.")]
	nume = nume_canal(ref_text)
	if not nume:
		return [_tr("Canalul de pornire nu se mai găsește în lista de canale: receptorul pornește pe ultimul canal urmărit.")]
	return [_tr("Canalul de pornire: %s") % nume]
