# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsEpgSalvare.py: unde se pastreaza ghidul (EPG) intre porniri si cand se scrie.
#
# Cauza, citita pe receptor: config.misc.epgcache_filename era „/hdd/epg.dat”, adica pe stickul sau discul montat in
# /media/hdd. Fara el (receptoarele fara disc: /media e in memorie si /media/hdd nu exista) eEPGCache::save din
# lib/dvb/epgcache.cpp nu putea scrie, deci ghidul se pierdea la fiecare repornire a interfetei. Cu stick, load()
# stergea fisierul cum il citea: cat merge interfata nu exista epg.dat nicaieri, iar o oprire necurata (cadere, paznicul,
# init 4, curent taiat) pierdea tot ghidul.
# Acum:
# - CALE (/home/root/epg.dat), pe memoria interna, mereu acolo. Nu in /etc/enigma2: copia setarilor
#   (Components/HdsCopieSetari.py) ia tot dosarul, deci si cativa MB de ghid. O cale aleasa de om in settings ramane;
# - la pornire, cand calea nu are fisier, un ghid ramas pe calea veche (CALE_VECHE, de la versiunea dinainte) se muta
#   pe ea (muta_vechiul), altfel ghidul s-ar pierde o data, la repornirea de dupa actualizare;
# - scrierea si citirea fisierului (C++): in <cale>.nou si rename peste el, cu fsync; citirea nu-l mai sterge;
# - cand se scrie: la iesirea interfetei (ca pana acum: repornire, oprire, repornirea receptorului din meniu), la
#   intrarea in standby si o data la SALVARE_ORE ore (eEPGCache.requestSave, pe firul ghidului). Nu la fiecare minut:
#   o scriere are cativa MB (masurat pe receptor: 602112 o si 6873088 o).
# 0.7.5 (EPS, 13.11.2026): LOCUL ALES DE OM. Setarea „Unde se păstrează ghidul TV” (config.misc.hds_epg_loc, in setup.xml
# usage, deci si in web la /setari?id=usage): „intern” (CALE, implicit) sau punctul de montare al unui stick sau disc din /media
# (<montare>/epg.dat). Cauza cererii: EPGImport-ul cu „Path DB EPG” scrie alegerea numai in config.plugins.epgimport.pathdb, pe
# care nu-l citeste nimeni, si opreste /home in alegere; config.misc.epgcache_filename nu se schimba niciodata. Acum:
# - la Salvare (Setup, web) ghidul se muta: copie sigura (.nou, fsync, replace) pe locul nou, setCacheFile, requestSave, cel
#   vechi sters; un disc nemontat, numai citire sau fara MIN_LIBER nu primeste ghidul;
# - stickul ales lipseste (la pornire sau scos din mers): ghidul se pastreaza in CALE, un mesaj scurt o data; alegerea ramane
#   salvata (in lista: „nu e conectat acum”); la pornire mesajul vine abia dupa AMANARE_S, numai daca discul tot lipseste
#   (un disc montat cu cateva secunde dupa interfata nu da mesaj); stickul revine: ghidul se citeste de pe el
#   (eEPGCache.load), nu se scrie peste el, iar copia ramasa in CALE se sterge (un stick revenit fara ghid primeste ghidul,
#   ca la alegere);
# - locul liber al discului numara si ghidul deja scris acolo (se inlocuieste);
# - o schimbare facuta de un plugin (config.misc.epgcache_filename, config.plugins.epgimport.pathdb, config.misc.epgcachepath
#   din compatibilitatea OE-Alliance) se trece in setarea noastra: sub /media = discul acela, orice altceva = memoria interna;
#   valorile implicite ale pluginurilor (/etc/enigma2/epg.dat) nu muta nimic (numai schimbarile, nu prima citire);
# - calea efectiva se pune (si se salveaza) in config.misc.epgcache_filename si in setarile pluginurilor, ca ele sa vada locul adevarat.
# Modulul nu importa nimic din enigma la incarcare (probele de pe PC: teste/test_reparatii_tv_0320.py, teste/test_epg_loc_075.py).

import os
import shutil
import threading

_oprire = threading.Event()
_cache_vazut = False
_iesire_legata = False
_la_oprire = []


def inchis():
	"""Semnal Python, citibil si de lucratori fara a atinge obiectele enigma2."""
	return _oprire.is_set()


def _opreste():
	# Fara join, disc sau asteptarea lucratorilor pe calea de iesire.
	if inchis():
		return
	_oprire.set()
	for f in tuple(_la_oprire):
		try:
			f()
		except Exception as e:
			print("[HdsEpgSalvare] oprirea: %s" % type(e).__name__)


def _leaga_iesirea():
	global _iesire_legata
	if _iesire_legata:
		return
	import atexit
	atexit.register(_opreste)
	try:
		from twisted.internet import reactor
		reactor.addSystemEventTrigger("before", "shutdown", _opreste)
	except ImportError:
		pass
	_iesire_legata = True

CALE = "/home/root/epg.dat"
CALE_VECHE = "/hdd/epg.dat"
SALVARE_ORE = 6
INTERN = "intern"
MEDIA = "/media"
NUME_FISIER = "epg.dat"
MIN_LIBER = 16 * 1024 * 1024
MONTARI = "/proc/mounts"
AMANARE_S = 30  # la pornire, mesajul „discul nu este conectat” numai daca lipseste si dupa atatea secunde
FARA_DISC = ("tmpfs", "devtmpfs", "autofs", "proc", "sysfs", "squashfs", "overlay", "ramfs")

_stare = {"ceas": None, "standby": False, "cale": None, "scriu": False, "anuntat": None, "legat_disc": False,
	"legat_pluginuri": False, "verificare": None, "amanare": None}


def _jurnal(text):
	print("[HdsEpgSalvare] %s" % text)


def muta_vechiul(cale, vechi=CALE_VECHE):
	"""Ghidul scris de versiunea dinainte pe calea veche se muta pe `cale`, o singura data: numai cand `cale` nu are
	fisier si cea veche are. Copia se face in <cale>.nou, cu fsync, si se muta peste (os.replace), apoi cel vechi se
	sterge. -> True daca s-a mutat. Nu arunca: pornirea nu depinde de el."""
	try:
		if not cale or os.path.realpath(cale) == os.path.realpath(vechi):
			return False
		if os.path.exists(cale) or not os.path.isfile(vechi):
			return False
		dosar = os.path.dirname(cale)
		if dosar and not os.path.isdir(dosar):
			return False
		nou = cale + ".nou"
		shutil.copyfile(vechi, nou)
		with open(nou, "rb+") as f:
			os.fsync(f.fileno())
		os.replace(nou, cale)
		try:
			os.remove(vechi)
		except OSError as e:
			_jurnal("cel vechi ramane: %s" % e)
		_jurnal("ghidul mutat de pe %s pe %s" % (vechi, cale))
		return True
	except Exception as e:
		_jurnal("mutarea ghidului vechi: %r" % (e,))
		try:
			os.remove(cale + ".nou")
		except OSError:
			pass
		return False


def salveaza():
	"""Cere firului ghidului sa scrie fisierul acum (lib/dvb/epgcache.cpp, Message::save). -> True daca s-a cerut;
	False fara fir pornit (ora inca nevalida) sau cu un enigma fara requestSave."""
	try:
		cache = _cache()
		cere = getattr(cache, "requestSave", None)
		if cere is None:
			return False
		return bool(cere())
	except Exception as e:
		_jurnal("salvarea: %r" % (e,))
		return False


# ---------------------------------------------------------------- locul ales de om (0.7.5)

def _t(text):
	try:
		return _(text)  # noqa: F821 (gettext din enigma2)
	except Exception:
		return text


def montari(fisier=None):
	"""Discurile montate sub /media, din /proc/mounts: [(punct, numai_citire)], fara /media insusi si fara sistemele din
	memorie. Un disc montat de doua ori apare o data (primul punct)."""
	rez = []
	vazute = set()
	try:
		with open(fisier or MONTARI) as f:
			randuri = f.read().splitlines()
	except (IOError, OSError):
		return rez
	for rand in randuri:
		parti = rand.split()
		if len(parti) < 4:
			continue
		dispozitiv, punct, fel, optiuni = parti[0], parti[1].replace("\\040", " "), parti[2], parti[3]
		if fel in FARA_DISC or not punct.startswith(MEDIA + "/") or dispozitiv in vazute:
			continue
		vazute.add(dispozitiv)
		rez.append((punct.rstrip("/"), "ro" in optiuni.split(",")))
	return rez


def _punct_pentru(cale, lista=None):
	"""Punctul de montare din /media care tine `cale` (cel mai lung), sau None."""
	if lista is None:
		lista = montari()
	bun = None
	for punct, _ro in lista:
		if cale == punct or cale.startswith(punct + "/"):
			if bun is None or len(punct) > len(bun):
				bun = punct
	return bun


def loc_din_cale(cale):
	"""Calea scrisa de un plugin -> alegerea noastra: sub /media = discul (montat sau nu), altfel memoria interna."""
	if not cale:
		return INTERN
	cale = str(cale).strip()
	try:
		dosar = os.path.dirname(cale) if cale.endswith(".dat") else cale
		if os.path.exists(dosar):
			dosar = os.path.realpath(dosar)  # /hdd -> /media/hdd
	except Exception:
		dosar = cale
	dosar = dosar.rstrip("/")
	if not dosar.startswith(MEDIA + "/"):
		return INTERN
	punct = _punct_pentru(dosar)
	if punct:
		return punct
	return MEDIA + "/" + dosar[len(MEDIA) + 1:].split("/")[0]  # /media/usb, chiar daca acum lipseste


def problema_loc(loc, lista=None):
	"""None daca ghidul se poate tine pe `loc`, altfel motivul: "lipsa", "numai_citire" sau "plin"."""
	if loc == INTERN:
		return None
	if lista is None:
		lista = montari()
	ro = dict(lista).get(loc)
	if ro is None:
		return "lipsa"
	if ro or not os.access(loc, os.W_OK):
		return "numai_citire"
	try:
		st = os.statvfs(loc)
		liber = st.f_bavail * st.f_frsize
		try:
			liber += os.path.getsize(os.path.join(loc, NUME_FISIER))  # ghidul de acolo se inlocuieste, locul lui e liber
		except OSError:
			pass
		if liber < MIN_LIBER:
			return "plin"
	except (OSError, AttributeError):
		pass
	return None


def cale_pentru(loc, lista=None):
	"""-> (calea fisierului, problema): pe disc numai cand se poate scrie acolo, altfel CALE si motivul."""
	problema = problema_loc(loc, lista)
	if loc == INTERN or problema:
		return CALE, problema
	return os.path.join(loc, NUME_FISIER), None


def _nume_disc(punct, cu_nume=True):
	if not cu_nume:
		return punct
	try:
		from Components.Harddisk import harddiskmanager
		for p in harddiskmanager.getMountedPartitions():
			if (p.mountpoint or "").rstrip("/") == punct and p.description:
				return "%s (%s)" % (p.description, punct)
	except Exception:
		pass
	return punct


def alegeri(pastrat=None, lista=None, cu_nume=True):
	"""Alegerile setarii: memoria interna, fiecare disc montat (cu numele lui) si cel ales, chiar daca lipseste acum.
	cu_nume=False: fara Components.Harddisk (la pornire, inainte sa fie incarcat; numele vin la _leaga)."""
	if lista is None:
		lista = montari()
	rez = [(INTERN, _t("Memoria internă"))]
	puncte = [p for p, _ro in lista]
	for punct in puncte:
		rez.append((punct, _nume_disc(punct, cu_nume)))
	if pastrat and pastrat != INTERN and pastrat not in puncte and pastrat.startswith(MEDIA + "/"):
		rez.append((pastrat, _t("%s (nu e conectat acum)") % pastrat))
	return rez


def _copiaza_sigur(sursa, tinta):
	"""sursa -> tinta prin <tinta>.nou, fsync si replace. -> True daca tinta are acum copia."""
	nou = tinta + ".nou"
	try:
		if not sursa or not os.path.isfile(sursa) or os.path.realpath(sursa) == os.path.realpath(tinta):
			return False
		shutil.copyfile(sursa, nou)
		with open(nou, "rb+") as f:
			os.fsync(f.fileno())
		os.replace(nou, tinta)
		return True
	except Exception as e:
		_jurnal("copia ghidului %s -> %s: %r" % (sursa, tinta, e))
		try:
			os.remove(nou)
		except OSError:
			pass
		return False


def fisier_citibil(cale):
	"""Antetul pe care il cere eEPGCache::load (ordinea octetilor si ENIGMA_EPG_V7), citit fara a schimba fisierul."""
	try:
		with open(cale, "rb") as f:
			cap = f.read(17)
		return len(cap) == 17 and cap[4:] == b"ENIGMA_EPG_V7" and int.from_bytes(cap[:4], "little") == 0x98765432
	except (IOError, OSError):
		return False


def _cache():
	global _cache_vazut
	if inchis() or threading.current_thread() is not threading.main_thread():
		return None
	_leaga_iesirea()
	try:
		from enigma import eEPGCache
		cache = eEPGCache.getInstance()
	except Exception:
		return None
	if cache is not None:
		_cache_vazut = True
	elif _cache_vazut:
		_opreste()
	return cache


def _anunta(problema):
	if problema == "lipsa":
		text = _t("Discul ales pentru ghidul TV nu este conectat. Ghidul se păstrează în memoria internă până îl conectezi din nou.")
	else:
		text = _t("Pe discul ales pentru ghidul TV nu se poate scrie. Ghidul se păstrează în memoria internă.")
	_jurnal("anunt: %s" % problema)
	try:
		from Tools import Notifications
		from Screens.MessageBox import MessageBox
		Notifications.AddPopup(text, MessageBox.TYPE_INFO, 10, "HdsEpgSalvare")
	except Exception as e:
		_jurnal("mesajul: %r" % (e,))


def _oglindeste(cale):
	"""Calea efectiva, vazuta de pluginuri: config.misc.epgcache_filename, pathdb si epgcachepath, puse si salvate (ecranul
	pluginului arata locul adevarat, iar o anulare acolo nu muta ghidul). Fara notificarile noastre (_stare["scriu"])."""
	try:
		from Components.config import config
	except Exception:
		return
	_stare["scriu"] = True
	try:
		el = getattr(config.misc, "epgcache_filename", None)
		if el is not None and (el.value != cale or el.saved_value != cale):
			el.value = cale
			el.save()
		el = getattr(getattr(getattr(config, "plugins", None), "epgimport", None), "pathdb", None)
		if el is not None and el.value != cale:
			el.value = cale
			el.save()
		el = getattr(config.misc, "epgcachepath", None)
		dosar = os.path.dirname(cale) + "/"
		if el is not None and el.value != dosar and el.value.rstrip("/") != os.path.dirname(cale):
			el.value = dosar
			el.save()
	except Exception as e:
		_jurnal("oglinda: %r" % (e,))
	finally:
		_stare["scriu"] = False


def _amana_anuntul():
	"""-> True daca verificarea de dupa AMANARE_S a pornit (ea anunta, daca discul tot lipseste)."""
	try:
		from enigma import eTimer
		if _stare["amanare"] is None:
			t = eTimer()
			t.callback.append(_verifica)
			_stare["amanare"] = t
		_stare["amanare"].start(AMANARE_S * 1000, True)
		return True
	except Exception as e:
		_jurnal("amanarea mesajului: %r" % (e,))
		return False


def _sterge_ramas(tinta):
	"""Ghidul e pe disc si se citeste de acolo: copia ramasa in memoria interna (scrisa cat a lipsit discul) se sterge,
	ca flash-ul sa nu tina degeaba un ghid vechi. Numai cand pe disc e un ghid bun."""
	if tinta == CALE or not os.path.isfile(CALE) or not fisier_citibil(tinta):
		return
	try:
		os.remove(CALE)
		_jurnal("ghidul ramas in memoria interna sters (ghidul e pe %s)" % tinta)
	except OSError as e:
		_jurnal("ghidul ramas in memoria interna: %s" % e)


def aplica(motiv="auto"):
	"""Pune ghidul pe locul ales (config.misc.hds_epg_loc), daca se poate, altfel pe CALE. motiv: "alegere" (omul a
	salvat: ghidul din memorie se muta acolo) sau "auto" (pornire, disc pus sau scos, ceas, standby). -> calea efectiva."""
	cache = _cache()
	if inchis() or threading.current_thread() is not threading.main_thread():
		return _stare["cale"]
	try:
		from Components.config import config
		loc = config.misc.hds_epg_loc.value
	except Exception:
		loc = INTERN
	tinta, problema = cale_pentru(loc)
	actuala = _stare["cale"]
	_oglindeste(tinta)
	if problema:
		if _stare["anuntat"] != loc:
			# la pornire un stick sau un disc se poate monta cu cateva secunde dupa interfata (hotplug): mesajul abia dupa
			# AMANARE_S, numai daca lipseste si atunci (_verifica); cand apare, _la_disc il ia fara niciun mesaj
			if not (actuala is None and problema == "lipsa" and _amana_anuntul()):
				_stare["anuntat"] = loc
				_anunta(problema)
	else:
		_stare["anuntat"] = None
	if tinta == actuala:
		return tinta
	if actuala is None:
		# pornirea: ghidul ramas pe /hdd/epg.dat (versiunile vechi) sau in memoria interna inainte de a alege discul
		muta_vechiul(tinta, CALE_VECHE)
		if tinta != CALE:
			muta_vechiul(tinta, CALE)
			_sterge_ramas(tinta)
		if cache is not None:
			cache.setCacheFile(tinta)
		_jurnal("ghidul: %s" % tinta)
	elif motiv == "alegere" or (tinta != CALE and not fisier_citibil(tinta)):
		# omul a ales alt loc, sau discul ales a revenit fara ghid pe el: ghidul trece acolo (copia, apoi cel din memorie)
		mutat = _copiaza_sigur(actuala, tinta)
		if cache is not None:
			cache.setCacheFile(tinta)
			cache.requestSave()
		if mutat:
			try:
				os.remove(actuala)
			except OSError as e:
				_jurnal("cel vechi ramane: %s" % e)
		_jurnal("ghidul mutat pe %s (%s)" % (tinta, "ales de om" if motiv == "alegere" else "discul a revenit"))
	elif tinta != CALE:
		# discul ales a revenit: ghidul lui e cel bun (cel din memorie are numai ce s-a strans cat a lipsit)
		if cache is not None:
			cache.setCacheFile(tinta)
			# eEPGCache::loadLater se numeste load in Python (lib/python/enigma_python.i: %rename(load))
			cerere = getattr(cache, "load", None) or getattr(cache, "loadLater", None)
			if cerere is not None:
				cerere()
			else:
				_jurnal("fara load in enigma: ghidul stickului nu se poate citi din nou")
		_jurnal("discul a revenit, ghidul citit de pe %s" % tinta)
		_sterge_ramas(tinta)
	else:
		# discul ales lipseste (sau nu se poate scrie pe el): ghidul din memorie se scrie in CALE
		if cache is not None:
			cache.setCacheFile(tinta)
			cache.requestSave()
		_jurnal("ghidul scris pe %s (%s)" % (tinta, problema))
	_stare["cale"] = tinta
	return tinta


def _reimprospateaza():
	try:
		from Components.config import config
		el = config.misc.hds_epg_loc
		pastrat = el.value if el.value != INTERN else el.saved_value
		el.setChoices(alegeri(pastrat), default=INTERN)
		if pastrat and el.value != pastrat:
			el.value = pastrat
	except Exception as e:
		_jurnal("alegerile: %r" % (e,))


def _cand_salveaza(el):
	if _stare["scriu"]:
		return
	aplica("alegere")


def creeaza_setarea(cale_ghid=None):
	"""Din mytest.py, imediat dupa config.misc.epgcache_filename si inainte de pluginuri: setarea locului, alegerea salvata
	pastrata cand discul lipseste, trecerea unei cai vechi alese de om in setare si calea efectiva in epgcache_filename."""
	from Components.config import config, ConfigSelection

	class AlegereLocGhid(ConfigSelection):
		# mutarea se face la Salvare (Verde pe televizor, „Salvează” in web), nu la fiecare apasare stanga/dreapta
		def save(self):
			ConfigSelection.save(self)
			_cand_salveaza(self)

	el = AlegereLocGhid(default=INTERN, choices=alegeri(cu_nume=False))
	# salvata si cand e „intern”: fara valoare salvata = setarea n-a existat inca (numai atunci se ia calea veche)
	el.save_forced = True
	config.misc.hds_epg_loc = el
	salvat = el.saved_value
	if salvat and el.value != salvat:
		el.setChoices(alegeri(salvat, cu_nume=False), default=INTERN)
		el.value = salvat
	if not salvat and cale_ghid is not None:
		vechi = cale_ghid.value
		if vechi and vechi not in (CALE, CALE_VECHE):
			loc = loc_din_cale(vechi)
			if loc != INTERN:
				el.setChoices(alegeri(loc, cu_nume=False), default=INTERN)
				el.value = loc
				ConfigSelection.save(el)
				_jurnal("calea aleasa inainte (%s) trece in setare: %s" % (vechi, loc))
	if cale_ghid is not None:
		# locul il tine setarea noastra; epgcache_filename arata calea efectiva. ConfigText nu anunta la .value = ..., deci
		# schimbarea unui plugin se vede la save() (si o anulare il pune la loc, pe calea efectiva salvata de _oglindeste)
		cale_ghid.callNotifiersOnSaveAndCancel = True
	_oglindeste(cale_pentru(el.value)[0])
	return el


def la_calea_ghidului(el):
	"""Notificatorul config.misc.epgcache_filename (mytest.setEPGCachePath). Prima chemare: ghidul pe locul ales. Apoi:
	un plugin a schimbat calea -> trece in setarea noastra si ghidul se muta."""
	if _stare["scriu"]:
		return
	if _stare["cale"] is None:
		aplica()
		return
	_din_plugin(el.value)


def _din_plugin(cale):
	if _stare["scriu"] or not cale:
		return
	try:
		from Components.config import config
		setarea = config.misc.hds_epg_loc
	except Exception:
		return
	if _stare["cale"] and str(cale).strip() == _stare["cale"]:
		# calea efectiva, pusa de noi in setarile pluginurilor (_oglindeste): o salvare sau o anulare acolo nu e o alegere
		# (altfel, cu stickul ales lipsa, CALE ar parea „memoria interna” si alegerea stickului s-ar pierde)
		_oglindeste(_stare["cale"])
		return
	loc = loc_din_cale(cale)
	_jurnal("locul ghidului schimbat dintr-un plugin: %s -> %s" % (cale, loc))
	if loc != setarea.value:
		setarea.setChoices(alegeri(loc), default=INTERN)
		setarea.value = loc
		setarea.save()  # muta ghidul (aplica("alegere"))
	else:
		_oglindeste(cale_pentru(loc)[0])


def _la_pathdb(el):
	_din_plugin(el.value)


def _la_epgcachepath(el):
	_din_plugin(os.path.join(el.value or "", NUME_FISIER))


def _verifica():
	"""Locul din nou (disc pus sau scos, ceas, standby), numai dupa ce pornirea a pus ghidul (la_calea_ghidului); nu
	cade: scrierea ghidului de dupa el nu depinde de el."""
	if _stare["cale"] is None:
		return
	try:
		aplica()
	except Exception as e:
		_jurnal("verificarea locului: %r" % (e,))


def _la_disc(*argumente):
	# discurile se monteaza si se scot pe firul lor: se verifica acum si inca o data peste 3 s
	if inchis():
		return
	if threading.current_thread() is not threading.main_thread():
		try:
			from twisted.internet import reactor
			reactor.callFromThread(_la_disc, *argumente)
		except ImportError:
			pass
		return
	_cache()
	if inchis():
		return
	_reimprospateaza()
	_verifica()
	try:
		from enigma import eTimer
		if _stare["verificare"] is None:
			t = eTimer()
			t.callback.append(lambda: (_reimprospateaza(), _verifica()))
			_stare["verificare"] = t
		_stare["verificare"].start(3000, True)
	except Exception:
		pass


def _leaga():
	"""Dupa citirea pluginurilor: discurile puse sau scoase si setarile de loc ale pluginurilor (numai schimbarile)."""
	if not _stare["legat_disc"]:
		try:
			from Components.Harddisk import harddiskmanager
			harddiskmanager.on_partition_list_change.append(_la_disc)
			_stare["legat_disc"] = True
		except Exception as e:
			_jurnal("discurile: %r" % (e,))
	if not _stare["legat_pluginuri"]:
		try:
			from Components.config import config
			# ConfigText/ConfigDirectory nu anunta la .value = ...: pluginul care salveaza (Verde) anunta prin save()
			el = getattr(getattr(getattr(config, "plugins", None), "epgimport", None), "pathdb", None)
			if el is not None:
				el.callNotifiersOnSaveAndCancel = True
				el.addNotifier(_la_pathdb, initial_call=False)
			el = getattr(config.misc, "epgcachepath", None)
			if el is not None:
				el.callNotifiersOnSaveAndCancel = True
				el.addNotifier(_la_epgcachepath, initial_call=False)
			_stare["legat_pluginuri"] = True
		except Exception as e:
			_jurnal("pluginurile: %r" % (e,))
	_reimprospateaza()
	_oglindeste(_stare["cale"] or cale_pentru(INTERN)[0])


def _laCeas():
	_verifica()
	if salveaza():
		_jurnal("ghidul se scrie (o data la %d ore)" % SALVARE_ORE)


def _laStandby(element=None):
	# config.misc.standbyCounter creste la fiecare intrare in standby: atunci se scrie ghidul (dupa standby curentul se
	# taie des din priza); intai locul (un stick scos fara sa stim)
	_verifica()
	if salveaza():
		_jurnal("ghidul se scrie (standby)")


def porneste():
	"""Scrierea rara a ghidului: o data la SALVARE_ORE ore si la intrarea in standby; discurile si pluginurile (_leaga).
	Chemata o data, din mytest.py, dupa citirea pluginurilor."""
	_cache()
	if inchis() or threading.current_thread() is not threading.main_thread():
		return
	try:
		from enigma import eTimer
		if _stare["ceas"] is None:
			ceas = eTimer()
			ceas.callback.append(_laCeas)
			ceas.start(SALVARE_ORE * 3600 * 1000, False)
			_stare["ceas"] = ceas
	except Exception as e:
		_jurnal("ceasul: %r" % (e,))
	try:
		from Components.config import config
		if not _stare["standby"]:
			config.misc.standbyCounter.addNotifier(_laStandby, initial_call=False)
			_stare["standby"] = True
	except Exception as e:
		_jurnal("standby: %r" % (e,))
	_leaga()
