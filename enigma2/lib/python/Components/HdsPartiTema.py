# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsPartiTema.py: o tema straina cu parti la alegere (dosarul allScreens/, cu previzualizarile in preview/preview_skin_*.png) primeste
# singura pluginul de setari pentru care e scrisa: AtileHD (enigma2-plugin-extensions-atilehd, GPL-2.0, din Enigma2-ul OE-Alliance,
# reteta in feedul extern, agentul ATL). 0.7.6, NCP, TODO 15.11 10:27 (NCH).
#
# De ce: tema Nacht 7.0 (rapoartele 223310, 639656, 357083) tine sigla 'ncht', vremea de pe bara si posterul numai in partile ei la
# alegere. Omul le alege cu pluginul de setari al temei, care leaga fisierele alese in <tema>/mySkin (mySkin -> mySkin_off); imaginea
# citeste deja <tema>/mySkin/skin_*.xml (skin.partiTema, din 0.7.4). Fara plugin, omul nu avea de unde alege, deci nici sigla, nici vremea.
# De la NCH (acelasi lot) ecranele temei raman ale ei si fara parti; de aici, alegerea partilor exista pe receptor fara nimic de facut.
#
# Cand: dupa ce interfata a mers PROBA_S secunde cu tema (Plugins/SystemPlugins/SkinSelector/plugin.py, _pornireReusita), deci si cand
# tema e aleasa din pagina web (/skin), si cand omul o avea dinainte de actualizare. Cum: coada din Components/HdsModuleLipsa.py
# (cerePachet: numai din feedul HD Satelit, o incercare pe sesiune, pachetul lipsa din feed tinut minte o zi, fara opkg update la fiecare
# pornire), in liniste. Dupa instalare, pluginul intra in liste fara repornire, iar omul afla o singura data, pe tema, unde alege partile
# (Meniu > Setari > Sistem si dispozitive > Setup - <tema>; AtileHD isi pune singur intrarea acolo, cu id-ul de meniu "system").
#
# Ce NU face (regula 1f): nu face o a doua alegere a partilor in Teme sau in pagina web si nu scrie singur mySkin. Pluginul temei are
# previzualizarile si comutatoarele autorului; doua locuri pentru acelasi lucru ar fi mai greu pentru om. Temele care isi aduc singure
# pluginul (Nacht 8.x: skin_styles/ si NachtTool in aceeasi arhiva) nu au allScreens/, deci nu primesc nimic de aici.
# Nu importa nimic din enigma la incarcare (probele de pe PC); RADACINA pune un dosar in fata cailor de sistem, numai la probe. Nu arunca.
import json
import os

RADACINA = ""
PACHET = "enigma2-plugin-extensions-atilehd"
DOSAR_PLUGIN = "/usr/lib/enigma2/python/Plugins/Extensions/AtileHD"
DOSAR_SKINURI = "/usr/share/enigma2"
DOSAR_PARTI = "allScreens"
SKIN_IMAGINE = "HDSatelit/skin.xml"
# temele pe care le anuntase deja (o singura data pe tema, si dupa repornire)
ANUNTATE_FISIER = "/etc/enigma2/hds-parti-tema.json"
DURATA_MESAJ_MS = 15000


def N_(text):
	return text


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _jurnal(text):
	print("[HdsPartiTema] %s" % text)


def _c(cale):
	return RADACINA + cale if RADACINA else cale


def numeTema(valoare):
	"""dosarul temei din config.skin.primary_skin ("Nacht/skin.xml" -> "Nacht"); None pentru tema imaginii si valorile ciudate"""
	valoare = valoare or ""
	if not valoare.endswith("/skin.xml") or valoare == SKIN_IMAGINE:
		return None
	nume = valoare[:-len("/skin.xml")]
	if not nume or "/" in nume or "\\" in nume or nume.startswith("."):
		return None
	return nume


def areParti(dosar_tema):
	"""tema are parti la alegere in forma pluginului AtileHD: allScreens/skin_*.xml, sau allScreens/<parte>/<parte>_*.xml"""
	dosar = os.path.join(dosar_tema, DOSAR_PARTI)
	try:
		intrari = os.listdir(dosar)
	except OSError:
		return False
	for n in intrari:
		cale = os.path.join(dosar, n)
		if n.endswith(".xml") and os.path.isfile(cale):
			return True
		if os.path.isdir(cale):
			try:
				if any(x.endswith(".xml") for x in os.listdir(cale)):
					return True
			except OSError:
				pass
	return False


def pluginInstalat():
	d = _c(DOSAR_PLUGIN)
	return os.path.isfile(os.path.join(d, "plugin.py")) or os.path.isfile(os.path.join(d, "plugin.pyc"))


def deCerut(valoare):
	"""numele temei cand trebuie cerut pluginul de setari (tema straina cu allScreens, pluginul lipsa), altfel None"""
	nume = numeTema(valoare)
	if nume is None or pluginInstalat():
		return None
	return nume if areParti(os.path.join(_c(DOSAR_SKINURI), nume)) else None


def _citesteAnuntate():
	try:
		with open(_c(ANUNTATE_FISIER), encoding="utf-8") as f:
			d = json.load(f)
		return [x for x in d.get("anuntate", []) if isinstance(x, str)] if isinstance(d, dict) else []
	except (OSError, ValueError):
		return []


def _scrieAnuntate(lista):
	cale = _c(ANUNTATE_FISIER)
	try:
		with open(cale + ".nou", "w", encoding="utf-8") as f:
			json.dump({"anuntate": lista[-50:]}, f, ensure_ascii=False)
		os.replace(cale + ".nou", cale)
	except OSError as e:
		_jurnal("%s: %s" % (cale, e))


def textGata(nume):
	# intrarea din meniu cu textul pluginului ("Setup - %s"), tradus la fel ca in meniu
	return _t("Tema %s are părți la alegere, de pildă sigla și vremea pe bară. Le alegi din Meniu > Setări > Sistem și dispozitive > %s.") % (
		nume, _t("Setup - %s") % nume)


def activeazaPlugin(session, plugins=None):
	"""pluginul instalat acum intra in liste (si in meniu) fara repornirea interfetei"""
	try:
		if plugins is None:
			from Components.PluginComponent import plugins
		cai = [c for c in getattr(plugins, "amanateToate", {}) if (c or "").rstrip("/").endswith("/Extensions/AtileHD")]
		if cai and hasattr(plugins, "activeazaAcum"):
			return plugins.activeazaAcum(cai, session)
	except Exception as e:
		_jurnal("pornirea pluginului: %r" % (e,))
	return []


def _mesaj(session, text):
	"""True numai cand mesajul s-a aratat"""
	if session is None:
		return False
	try:
		from Screens import HdsAnuntRetea
		HdsAnuntRetea.arata(session, text, "", DURATA_MESAJ_MS)
		return True
	except Exception as e:
		_jurnal("mesaj: %r" % (e,))
		return False


def _sesiune(session=None):
	if session is not None:
		return session
	try:
		from Components import HdsModuleLipsa
		return HdsModuleLipsa._stare.get("sesiune")
	except Exception:
		return None


def anunta(nume, session=None):
	"""o singura data pe tema: unde se aleg partile; tinut minte numai dupa ce mesajul s-a aratat (fara sesiune: data viitoare)"""
	anuntate = _citesteAnuntate()
	if nume in anuntate:
		return False
	if not _mesaj(_sesiune(session), textGata(nume)):
		return False
	anuntate.append(nume)
	_scrieAnuntate(anuntate)
	return True


def dupaInstalare(nume, reusit, session=None, plugins=None):
	"""sfarsitul instalarii (din HdsModuleLipsa): pluginul pornit acum si mesajul, o singura data pe tema; n-a mers: numai jurnal
	(tema merge si fara parti; se reincearca la o pornire viitoare)"""
	if not reusit:
		_jurnal("pluginul de setari pentru %s nu s-a instalat; tema merge fara parti" % nume)
		return
	session = _sesiune(session)
	activeazaPlugin(session, plugins)
	anunta(nume, session)


# AS140 (0.8.0): tema straina care cere sursa session.OAWeather sau convertoarele OAWeather (MERCUS-FHD, Vu+ Uno 4K, 23.11.2026):
# fara pluginul OAWeather ecranele ei cadeau pe aspectul de rezerva ("stil amestecat"). Pluginul e in feedul extern; vine singur,
# in liniste, prin aceeasi coada; sursa lui apare la urmatoarea pornire a interfetei.
PACHET_VREME = "enigma2-plugin-extensions-oaweather"
DOSAR_VREME = "/usr/lib/enigma2/python/Plugins/Extensions/OAWeather"
SEMN_VREME = b"OAWeather"
MAX_XML_VREME = 8 * 1024 * 1024


def cereVremea(dosar_tema):
	"""fisierele .xml din radacina temei (si din mySkin/) pomenesc OAWeather"""
	for sub in ("", "mySkin"):
		d = os.path.join(dosar_tema, sub)
		try:
			nume = sorted(os.listdir(d))
		except OSError:
			continue
		for n in nume:
			cale = os.path.join(d, n)
			if not n.endswith(".xml") or not os.path.isfile(cale):
				continue
			try:
				if os.path.getsize(cale) > MAX_XML_VREME:
					continue
				with open(cale, "rb") as f:
					if SEMN_VREME in f.read():
						return True
			except (IOError, OSError):
				continue
	return False


def vremeaInstalata():
	d = _c(DOSAR_VREME)
	return os.path.isfile(os.path.join(d, "plugin.py")) or os.path.isfile(os.path.join(d, "plugin.pyc"))


def dupaPornireVremea(valoare, M=None):
	"""tema a pornit bine: pluginul OAWeather pus in coada, daca tema il cere si lipseste. Intoarce pachetul cerut sau None."""
	try:
		nume = numeTema(valoare)
		if nume is None or vremeaInstalata() or not cereVremea(os.path.join(_c(DOSAR_SKINURI), nume)):
			return None
		if M is None:
			from Components import HdsModuleLipsa as M

		def dupa(reusit):
			_jurnal("OAWeather pentru %s: %s" % (nume, "instalat, sursa vine la urmatoarea pornire a interfetei" if reusit
				else "nu s-a instalat"))
		return M.cerePachet(PACHET_VREME, "tema-vreme:" + nume, nume, dupa=dupa)
	except Exception as e:
		_jurnal("dupaPornireVremea: %r" % (e,))
		return None


def dupaPornire(valoare, M=None):
	"""tema a pornit bine: pluginul de setari pus in coada, daca tema il cere si lipseste. Intoarce pachetul cerut sau None.
	Cu pluginul deja pe receptor (de pilda adus de alta tema): numai mesajul, o singura data pe tema. OAWeather, daca tema il
	cere (dupaPornireVremea), separat."""
	dupaPornireVremea(valoare, M)
	try:
		nume = deCerut(valoare)
		if nume is None:
			alta = numeTema(valoare)
			if alta is not None and pluginInstalat() and areParti(os.path.join(_c(DOSAR_SKINURI), alta)):
				anunta(alta)
			return None
		if M is None:
			from Components import HdsModuleLipsa as M
		return M.cerePachet(PACHET, "tema:" + nume, nume, dupa=lambda reusit: dupaInstalare(nume, reusit))
	except Exception as e:
		_jurnal("dupaPornire: %r" % (e,))
		return None
