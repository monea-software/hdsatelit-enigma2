# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# media_web.py: "Player media" si "Poze" in interfata web (HdsWebControl), perechea ecranelor din Meniu > Media de pe
# televizor.
#
# Orice ecran sau setare de pe receptor are pereche in interfata web.
#
# /player, perechea playerului de fisiere (Plugins/Extensions/MediaPlayer/plugin.py, MediaPlayer, numit in
# Screens/MediaPlayer.py; setarile in settings.py):
# - fisierele de pe receptor, cu navigarea prin dosare ca pe televizor: aceleasi discuri (fara memoria interna) si
#   aceleasi extensii (Components/HdsMedia.py). "Pornește pe televizor" = tasta verde pe acel rand (tot dosarul intra
#   in lista de redare, fisierul ales porneste primul), "Adaugă în listă" = OK pe rand (sau, la un dosar, "add
#   directory to playlist" din meniul playerului). Playerul se deschide pe televizor daca nu e deschis; cursorul
#   listei de pe televizor ajunge pe rand (MediaPlayer.hdsSelect), apoi se cheama metoda tastei.
# - un fisier din telefon sau calculator: se trimite pe un disc montat (niciodata /tmp sau memoria interna), in
#   bucati de cel mult MAX_BUCATA, in <disc>/hds-din-telefon/<nume>.part, redenumit la sfarsit; apoi "Pornește pe
#   televizor". O singura trimitere odata; anularea sterge .part.
# - ce merge in player: pauza, redare, oprire, salturi, urmatorul, anteriorul (tastele playerului), lista de redare
#   (pornire, scoatere, golire, amestecare), listele salvate (salvare, incarcare, stergere), ascunderea, inchiderea.
#   Filmele pornite din lista de filme se comanda din pagina /filme (filme_web.py), legata din pagina.
# - setarile playerului (config.mediaplayer: repeat, savePlaylistOnExit, saveDirOnExit, defaultDir), ca ecranul
#   "Edit settings" din meniul playerului, care pe televizor apare numai la nivelul de meniu intermediar sau expert.
# /poze, perechea vizualizatorului de poze (Plugins/Extensions/PicturePlayer/plugin.py, picshow, numit in
# Screens/PicturePlayer.py):
# - galeria in browser: dosarele cu poze de pe aceleasi discuri, cu aceleasi extensii; miniaturile le face browserul
#   din poza servita (nimic calculat pe receptor); poza mare in pagina, cu sageti si detaliile Exif (ca tasta INFO).
# - "Arată pe televizor" si "Prezentare pe televizor": vizualizarea mare de pe televizor (Pic_Full_View) pe aceeasi
#   poza, cu pozele dosarului, ca OK in picshow; prezentarea = tasta verde in ea (PlayPause); inainte, inapoi, inchide.
# - setarile config.pic.* (ecranul Pic_Setup, tasta albastra).
#
# Rute (poarta comuna a HdsJsonResource: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; ce schimba
# ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF al panoului):
#   GET  /api/media-player                          playerul de pe televizor, lista de redare, setarile, discurile
#                                                   pentru trimitere, trimiterea in curs
#   GET  /api/media-lista?fel=player|poze&dosar=    dosarele si fisierele unui dosar (fir separat); fara dosar, discurile
#   POST /api/media-porneste?cale=&fa=porneste|adauga   un fisier sau un dosar (cu / la sfarsit) in playerul de pe TV
#   POST /api/media-comanda?fa=..&index=&secunde=&nume=  tastele playerului (lista in comanda())
#   POST /api/media-seteaza?repeta=&salveaza_lista=&salveaza_dosar=&dosar_pornire=   setarile playerului
#   POST /api/media-urca?nume=&pozitie=&total=&disc=&id=   o bucata a fisierului, octeti bruti in corp
#                                                   (application/octet-stream, cel mult MAX_BUCATA; limita corpului
#                                                   pentru aceasta cale o pune _CerereHds din plugin.py)
#   POST /api/media-urca-anuleaza?id=               opreste trimiterea si sterge .part
#   POST /api/media-sterge?fel=fisier&cale=|fel=lista&nume=   in doi pasi (pas=intreaba, cod=, pas=renunta), numai
#                                                   din browserul conectat: un fisier al playerului, ca "delete file"
#                                                   din meniul playerului (cu fisierele lui, HdsMedia.fisiereDeSters;
#                                                   la nivelul Simplu numai cele trimise din telefon), sau o lista de
#                                                   redare salvata
#   GET  /api/poze                                  setarile pozelor si vizualizarea de pe televizor
#   POST /api/poze-seteaza?slidetime=&resize=&..    setarile pozelor
#   POST /api/poze-tv?fa=arata|prezentare|opreste|inainte|inapoi|inchide&cale=   vizualizarea de pe televizor
#   GET  /api/poze-fisier?cale=                     poza, pentru galerie (twisted.web.static.File, pe bucati)
#   GET  /api/poze-info?cale=                       detaliile Exif, ca tasta INFO
#   GET  /player, /poze                             paginile
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2. Comenzile catre ecranele de pe televizor sunt scurte (ca
# o tasta). Citirea unui dosar si scrierea unei bucati trimise ruleaza pe un fir separat (meniu_comun_web.peFir),
# raspunsul pleaca la sfarsit. Pozele se servesc cu twisted.web.static.File (citire pe bucati, fara sa tina firul).
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau sesiunea, ecranele, setarile si discurile.

import os
import time

MAX_BUCATA = 4 * 1024 * 1024
# bucata cand serverul primeste pentru cererile paginii numai corpul obisnuit (64 KB, plugin.MAX_CORP_CERERE): de
# exemplu pagina deschisa cu ?token= de la o adresa unde se cere codul (marimeBucata)
BUCATA_MICA = 60 * 1024
MAX_CALE = 1024
MAX_LISTA_REDARE = 1000
DOSAR_URCARI = "hds-din-telefon"
# loc lasat liber pe disc dupa un fisier trimis
REZERVA_OCTETI = 64 * 1024 * 1024
# o trimitere fara nicio bucata de atata timp e parasita: alta o poate inlocui (si .part ei se sterge)
TERMEN_PARASITA_S = 600
# anularea fara cheia trimiterii (alt browser, pagina reincarcata) merge dupa atata timp fara bucati
TERMEN_ANULARE_STRAINA_S = 30
# fisierele .part ramase din trimiteri vechi (receptor repornit) se sterg la o trimitere noua
TERMEN_PART_VECHI_S = 6 * 3600
TERMEN_SCRIERE_S = 60
TERMEN_LISTA_S = 20
MAX_LISTARI = 3
SALT_MAX_S = 6 * 3600
MAX_NUME_OCTETI = 200
MAX_FAT = 4 * 1024 * 1024 * 1024 - 1
# sistemele de fisiere din memorie: nu primesc fisiere
FS_MEMORIE = ("tmpfs", "ramfs", "devtmpfs", "rootfs", "squashfs", "ubifs", "jffs2", "overlay", "proc", "sysfs")
FS_FAT = ("vfat", "msdos", "fat")
# un disc pe acelasi dispozitiv cu una din aceste cai e memoria interna sau /tmp
CAI_MEMORIE = ("/", "/tmp")


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_), fara efect: textele se traduc la folosire."""
	return text


def _t(text):
	"""Traducerea enigma2; un text gol ramane gol."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


TXT_ALT_ECRAN = N_("Pe televizor este deschis alt ecran. Închide-l și încearcă încă o dată.")
TXT_NU_MERGE = N_("Receptorul nu a putut face asta acum.")
TXT_FACUT = N_("Gata.")
TXT_SALVAT = N_("Salvat.")
TXT_COMANDA = N_("Comanda nu există.")
TXT_SECUNDE = N_("Numărul de secunde nu este bun.")
TXT_NIMIC = N_("Nu s-a trimis nicio setare.")
TXT_LISTA_INCETA = N_("Discul nu a răspuns la timp. Încearcă încă o dată.")
TXT_ALEGERE = N_("Valoarea %s nu se poate alege pentru %s.")
TXT_FISIER_LIPSA = N_("Fișierul nu este pe un disc al receptorului sau playerul nu îl cunoaște.")
TXT_DOSAR_LIPSA = N_("Dosarul nu este pe un disc al receptorului.")
TXT_DOSAR_CITIRE = N_("Dosarul nu se poate citi.")
TXT_LISTARI = N_("Receptorul citește alte dosare. Încearcă din nou peste o clipă.")
TXT_PORNESTE = N_("Fișierul pornește pe televizor.")
TXT_DOSAR_PORNESTE = N_("Dosarul pornește pe televizor.")
TXT_ADAUGAT = N_("Adăugat în lista de redare.")
TXT_FARA_PLAYER = N_("Playerul nu este deschis pe televizor.")
TXT_NU_IN_LISTA = N_("Fișierul nu apare în lista playerului de pe televizor.")
TXT_INTRARE = N_("Intrarea nu mai este în lista de redare.")
TXT_NIVEL = N_("Pe televizor, asta se poate numai cu nivelul de meniu Intermediar sau Expert.")
TXT_NUME_RAU = "The name cannot contain / or \\, cannot start with a dot and must fit in 255 characters."
TXT_LISTA_SALVATA = N_("Lista de redare s-a salvat.")
TXT_LISTA_INCARCATA = N_("Lista de redare s-a încărcat.")
TXT_LISTA_LIPSA = N_("Lista salvată nu există.")
TXT_LISTA_STEARSA = N_("Lista salvată s-a șters.")
TXT_INTREABA_LISTA = N_("Ștergi lista salvată %s?")
TXT_INTREABA_FISIER = N_("Ștergi fișierul %s de pe receptor?")
TXT_DA_STERGE = N_("Da, șterge")
TXT_LISTA_DISC = N_("O listă de redare de pe disc nu se poate șterge din player, nici pe televizor.")
TXT_INSOTITE = N_("Se șterg odată cu el: %s.")
TXT_MERGE_ACUM = N_("Fișierul merge acum pe televizor. Oprește-l întâi.")
TXT_STERS = N_("Fișierul s-a șters.")
TXT_NU_STERS = N_("Fișierul nu s-a putut șterge.")
TXT_DOSAR_PORNIRE = N_("Dosarul de pornire se alege numai când playerul nu ține minte ultimul dosar.")
TXT_URCARE_ALTA = N_("Se trimite deja un fișier. Așteaptă să se termine sau anulează trimiterea.")
TXT_URCARE_NUME = N_("Numele fișierului nu e bun sau playerul nu cunoaște acest fel de fișier.")
TXT_URCARE_DISC = N_("Discul ales nu primește fișiere. Alege un stick sau un disc montat.")
TXT_URCARE_LOC = N_("Pe disc nu e destul loc: trebuie %s, sunt liberi %s.")
TXT_URCARE_FAT = N_("Discul are sistemul FAT: un fișier poate avea cel mult 4 GB.")
TXT_URCARE_ORDINE = N_("Bucata nu vine în ordine.")
TXT_URCARE_MARE = N_("Bucata e prea mare.")
TXT_URCARE_TOTAL = N_("Mărimea fișierului nu e bună.")
TXT_URCARE_NIMIC = N_("Nu se trimite niciun fișier acum.")
TXT_URCARE_SCRIERE = N_("Discul nu a putut scrie fișierul.")
TXT_URCARE_GATA = N_("Fișierul a ajuns pe receptor: %s.")
TXT_URCARE_ANULATA = N_("Trimiterea s-a anulat.")
TXT_URCARE_POST = N_("Fișierul se trimite cu POST.")
TXT_URCARE_OCUPAT = N_("Receptorul scrie încă bucata de dinainte. Încearcă din nou.")
TXT_POZA_LIPSA = N_("Poza nu este pe un disc al receptorului.")
TXT_POZA_TV = N_("Poza se arată pe televizor.")
TXT_PREZENTARE = N_("Prezentarea pornește pe televizor.")
TXT_PREZENTARE_OPRITA = N_("Prezentarea s-a oprit.")
TXT_FARA_VIZUALIZARE = N_("Pe televizor nu se arată nicio poză.")
TXT_POZA_INFO = N_("Detaliile pozei nu se pot citi.")

# (numele in cerere, setarea din config.mediaplayer, eticheta de pe televizor: MediaPlayerSettings.initConfigList)
SETARI_PLAYER = (
	("repeta", "repeat", "repeat playlist"),
	("salveaza_lista", "savePlaylistOnExit", "save playlist on exit"),
	("salveaza_dosar", "saveDirOnExit", "save last directory on exit"),
)
ETICHETA_DOSAR_PORNIRE = "start directory"
TXT_LISTA_DISPOZITIVE = "List of Storage Devices"
# (setarea din config.pic, eticheta de pe televizor: Pic_Setup.createSetup), in ordinea ecranului
SETARI_POZE = (
	("slidetime", "Slideshow Interval (sec.)"),
	("resize", "Scaling Mode"),
	("cache", "Cache Thumbnails"),
	("infoline", "show Infoline"),
	("framesize", "Frame size in full view"),
	("loop", "slide picture in loop"),
	("bgcolor", "backgroundcolor"),
	("textcolor", "textcolor"),
)
CHEI = ("fel", "dosar", "cale", "fa", "index", "secunde", "nume", "pozitie", "total", "disc", "id", "pas", "cod",
	"repeta", "salveaza_lista", "salveaza_dosar", "dosar_pornire") + tuple(x[0] for x in SETARI_POZE)


def _jurnal(text):
	print("[HdsWebControl] media: %s" % text)


def _hm():
	from Components import HdsMedia
	return HdsMedia


def _m():
	from . import meniu_comun_web
	return meniu_comun_web


def _afisat(text):
	"""Un nume de pe disc pentru pagina (octetii scapati de os.listdir citit ca UTF-8), ca in filme_web."""
	from .filme_web import _afisat as a
	return a(text)


def _caleDisc(cale):
	"""Calea venita de la pagina (text UTF-8) ca nume de fisier pentru Python, ca in filme_web."""
	from .filme_web import _caleDisc as c
	return c(cale)


def _radacini():
	"""Discurile din care se alege (Components/HdsMedia.radacini); probele de pe PC dau altele."""
	return _hm().radacini()


def _tabelMontari():
	from Components.HdsNavigator import readMountTable
	return readMountTable()


def _clase():
	"""Clasele ecranelor de pe televizor (probele de pe PC dau altele)."""
	from Plugins.Extensions.MediaPlayer.plugin import MediaPlayer
	from Plugins.Extensions.PicturePlayer.plugin import picshow, Pic_Thumb, Pic_Full_View
	from Screens.InfoBar import InfoBar
	return {"player": MediaPlayer, "infobar": InfoBar, "poze": (picshow, Pic_Thumb), "vizualizare": Pic_Full_View}


def _dosarListe():
	"""Dosarul listelor de redare salvate (ca save_playlist2 si load_playlist din player)."""
	from Tools.Directories import resolveFilename, SCOPE_PLAYLIST
	return resolveFilename(SCOPE_PLAYLIST)


def _config(cfg=None):
	if cfg is not None:
		return cfg
	from Components.config import config
	return config


def _setariPlayer(cfg=None):
	c = _config(cfg)
	if cfg is None:
		import Plugins.Extensions.MediaPlayer.settings  # noqa: F401  (config.mediaplayer exista numai dupa import)
	return c.mediaplayer


def _setariPoze(cfg=None):
	c = _config(cfg)
	if cfg is None:
		import Plugins.Extensions.PicturePlayer.plugin  # noqa: F401  (config.pic exista numai dupa import)
	return c.pic


def _nivel(cfg=None):
	"""Nivelul meniului de pe televizor (0 simplu, 1 intermediar, 2 expert)."""
	try:
		return int(_config(cfg).usage.setup_level.index)
	except Exception:
		return 2


def _f(F=None):
	if F is not None:
		return F
	from Components import HdsFilmRedare
	return HdsFilmRedare


def _raspuns(bun, text, *argumente):
	t = _t(text)
	if argumente:
		t = t % argumente
	return {"result": bool(bun), "message": t}


# ------------------------------------------------------------------------------------------- setarile (config.*)

def _alegeri(element):
	rez = []
	for x in element.choices.choices:
		if isinstance(x, tuple):
			rez.append([str(x[0]), _t(x[1]) if x[1] else str(x[0])])
		else:
			rez.append([str(x), str(x)])
	return rez


def descrieSetare(cheie, element, eticheta):
	"""Un rand de setari ca pe televizor: numar (cu limitele elementului), da/nu (textele elementului) sau alegere."""
	v = element.value
	rez = {"cheie": cheie, "eticheta": _t(eticheta)}
	if isinstance(v, bool):
		d = getattr(element, "descriptions", None) or {False: "no", True: "yes"}
		rez.update({"fel": "alegere", "valoare": "1" if v else "0", "alegeri": [["1", _t(d[True])], ["0", _t(d[False])]]})
	elif hasattr(element, "limits"):
		mic, mare = element.limits[0]
		rez.update({"fel": "numar", "valoare": str(v), "min": mic, "max": mare})
	elif hasattr(element, "choices"):
		rez.update({"fel": "alegere", "valoare": str(v), "alegeri": _alegeri(element)})
	else:
		rez.update({"fel": "text", "valoare": str(v if v is not None else "")})
	return rez


def valoareNoua(element, text):
	"""(True, valoare) daca `text` e o alegere a elementului (limitele unui numar, 0/1, alegerile), altfel (False, None)."""
	v = element.value
	text = str(text).strip()
	if isinstance(v, bool):
		if text in ("0", "1"):
			return True, text == "1"
		return False, None
	if hasattr(element, "limits"):
		try:
			n = int(text)
		except ValueError:
			return False, None
		mic, mare = element.limits[0]
		return (True, n) if mic <= n <= mare else (False, None)
	if hasattr(element, "choices"):
		for x in element.choices.choices:
			k = x[0] if isinstance(x, tuple) else x
			if str(k) == text:
				return True, k
	return False, None


def _salveaza(perechi):
	"""Ca ecranele de setari la Salveaza (save() pe fiecare rand), apoi fisierul de setari (meniu_comun_web)."""
	for element, valoare in perechi:
		if hasattr(element, "setValue") and not isinstance(valoare, (bool, int)):
			element.setValue(valoare)
		else:
			element.value = valoare
		element.save()
	_m().salveazaSetari()


# ------------------------------------------------------------------------------------------- televizorul

def _dialoguri(sesiune):
	"""Ferestrele deschise pe televizor: cea din fata, apoi cele de sub ea."""
	rez = []
	curent = getattr(sesiune, "current_dialog", None)
	if curent is not None:
		rez.append(curent)
	for x in getattr(sesiune, "dialog_stack", None) or []:
		rez.append(x[0] if isinstance(x, tuple) else x)
	return rez


def _gaseste(sesiune, clasa):
	for d in _dialoguri(sesiune):
		if isinstance(d, clasa):
			return d
	return None


def _numeRef(ref):
	try:
		nume = ref.getName()
	except Exception:
		nume = ""
	return nume or (ref.getPath() or "").rstrip("/").rsplit("/", 1)[-1]


def _redare(sesiune, mp, F=None):
	"""Ce merge in player: numele, pozitia, lungimea, starea barei (ca in filme_web), sau None."""
	try:
		ref = sesiune.nav.getCurrentlyPlayingServiceReference()
		serviciu = sesiune.nav.getCurrentService()
	except Exception:
		return None
	if ref is None or serviciu is None or not (ref.getPath() or ""):
		return None
	from .filme_web import _pts, textStare
	F = _f(F)
	cale = ref.getPath()
	pozitie = lungime = None
	try:
		seek = serviciu.seek()
	except Exception:
		seek = None
	if seek is not None:
		pozitie = _pts(seek.getPlayPosition())
		lungime = _pts(seek.getLength())
	semn = mp.seekstate[3] if getattr(mp, "seekstate", None) else ">"
	return {
		"nume": cale.rsplit("/", 1)[-1],
		"cale": cale,
		"pozitie": pozitie // 90000 if pozitie is not None else None,
		"lungime": lungime // 90000 if lungime is not None else None,
		"text_pozitie": F.textTimp(pozitie, lungime),
		"text_lungime": F.textTimp(lungime),
		"stare": textStare(semn),
		"pauza": (semn or "").strip() in ("||", "END"),
	}


def starePlayer(sesiune, clase, F=None):
	"""Playerul de pe televizor: deschis, in fata, lista de redare, ce merge."""
	mp = _gaseste(sesiune, clase["player"]) if sesiune is not None else None
	if mp is None:
		return {"deschis": False}
	refs = mp.playlist.getServiceRefList()
	return {
		"deschis": True,
		"in_fata": getattr(sesiune, "current_dialog", None) is mp,
		"ascuns": not getattr(mp, "shown", True),
		"lista": [{"nume": _numeRef(r), "cale": r.getPath()} for r in refs[:MAX_LISTA_REDARE]],
		"marime_lista": len(refs),
		"curent": mp.playlist.getCurrentIndex(),
		"redare": _redare(sesiune, mp, F),
	}


def _listeSalvate(dosar=None):
	if dosar is None:
		dosar = _dosarListe()
	try:
		return sorted(n for n in os.listdir(dosar) if os.path.isfile(os.path.join(dosar, n)))
	except OSError:
		return []


def _dosarStart(text, rad):
	"""Un dosar tinut minte de un ecran (text), daca e inca pe un disc al receptorului; altfel "" (lista discurilor)."""
	if not text or text in ("/", "/media/", "/media"):
		return ""
	x = _hm().caleSigura(_caleDisc(text.rstrip("/")), rad, dosar=True)
	return text.rstrip("/") + "/" if x is not None else ""


def _setariPlayerDescrise(sp):
	rez = [descrieSetare(cheie, getattr(sp, nume), eticheta) for cheie, nume, eticheta in SETARI_PLAYER]
	if not sp.saveDirOnExit.value:
		# ca pe televizor: dosarul de pornire apare numai cand playerul nu tine minte ultimul dosar
		d = sp.defaultDir.getValue() if hasattr(sp.defaultDir, "getValue") else sp.defaultDir.value
		rez.append({"cheie": "dosar_pornire", "eticheta": _t(ETICHETA_DOSAR_PORNIRE), "fel": "dosar", "valoare": d or "",
			"text_gol": _t(TXT_LISTA_DISPOZITIVE)})
	return rez


def stare(sesiune=None, cfg=None, clase=None, rad=None, F=None, dosar_liste=None):
	"""Pentru GET /api/media-player."""
	clase = clase or _clase()
	if rad is None:
		rad = _radacini()
	sp = _setariPlayer(cfg)
	d = sp.defaultDir.getValue() if hasattr(sp.defaultDir, "getValue") else sp.defaultDir.value
	hm = _hm()
	return {
		"result": True,
		"tv": starePlayer(sesiune, clase, F),
		"nivel": _nivel(cfg),
		"setari": _setariPlayerDescrise(sp),
		"dosar_start": _dosarStart(d or "", rad),
		"liste_salvate": _listeSalvate(dosar_liste),
		"discuri": discuriUrcare(rad),
		"urcare": _URCARE.stare(time.monotonic()),
		"bucata": MAX_BUCATA,
		"extensii": list(hm.EXTENSII_PLAYER),
		"extensii_urcare": [e for e in hm.EXTENSII_PLAYER if e not in hm.LISTE_REDARE],
	}


def _secunde(text, minim, maxim):
	try:
		n = int(str(text).strip())
	except (TypeError, ValueError):
		return None
	return n if minim <= n <= maxim else None


def _intreg(text):
	try:
		return int(str(text).strip())
	except (TypeError, ValueError):
		return None


def _playerInFata(sesiune, clase, deschide=False):
	"""(player, None) cu playerul din fata (deschis acum pe televizor, cu deschide=True, peste bara principala), sau
	(None, mesaj)."""
	curent = getattr(sesiune, "current_dialog", None)
	if isinstance(curent, clase["player"]):
		return curent, None
	if deschide and isinstance(curent, clase["infobar"]):
		return sesiune.open(clase["player"]), None
	if _gaseste(sesiune, clase["player"]) is None and not deschide:
		return None, TXT_FARA_PLAYER
	return None, TXT_ALT_ECRAN


def porneste(argumente, sesiune=None, clase=None, rad=None):
	"""POST /api/media-porneste: un fisier (sau un dosar, cu / la sfarsit) in playerul de pe televizor, ca tasta verde
	(fa=porneste) sau ca OK si "add directory to playlist" (fa=adauga)."""
	M = _m()
	refuz = M.ocupat(sesiune)
	if refuz:
		return {"result": False, "message": _t(refuz)}
	clase = clase or _clase()
	if rad is None:
		rad = _radacini()
	hm = _hm()
	fa = argumente.get("fa", "porneste") or "porneste"
	if fa not in ("porneste", "adauga"):
		return _raspuns(False, TXT_COMANDA)
	text = argumente.get("cale", "")
	dosar = text.endswith("/")
	if dosar:
		x = hm.caleSigura(_caleDisc(text.rstrip("/")), rad, dosar=True)
	else:
		x = hm.caleSigura(_caleDisc(text), rad, hm.EXTENSII_PLAYER)
	if x is None:
		return _raspuns(False, TXT_DOSAR_LIPSA if dosar else TXT_FISIER_LIPSA)
	mp, mesaj = _playerInFata(sesiune, clase, deschide=True)
	if mp is None:
		return _raspuns(False, mesaj)
	if not mp.hdsSelect(text):
		return _raspuns(False, TXT_NU_IN_LISTA)
	if fa == "porneste":
		mp.xplayEntry()
		return _raspuns(True, TXT_DOSAR_PORNESTE if dosar else TXT_PORNESTE)
	if dosar:
		mp.copyDirectory(mp.filelist.getSelection()[0])
	else:
		mp.ok()
	return _raspuns(True, TXT_ADAUGAT)


def comanda(argumente, sesiune=None, cfg=None, clase=None, dosar_liste=None):
	"""POST /api/media-comanda: tastele si meniul playerului de pe televizor.
	deschide (Meniu > Media > Media player), pauza / redare (galben), oprire (stop), urmatorul / anteriorul (next /
	previous), salt&secunde= (tastele de cifre), reda&index= (OK in lista de redare), scoate&index= (delete in lista),
	goleste, amesteca, ascunde, arata, inchide (exit), salveaza-lista&nume=, incarca-lista&nume=."""
	M = _m()
	refuz = M.ocupat(sesiune)
	if refuz:
		return {"result": False, "message": _t(refuz)}
	clase = clase or _clase()
	fa = argumente.get("fa", "")
	if fa == "deschide":
		mp, mesaj = _playerInFata(sesiune, clase, deschide=True)
		return _raspuns(mp is not None, TXT_FACUT if mp is not None else mesaj)
	mp, mesaj = _playerInFata(sesiune, clase)
	if mp is None:
		return _raspuns(False, mesaj)
	nivel = _nivel(cfg)
	try:
		if fa == "pauza":
			if mp.seekstate != mp.SEEK_STATE_PAUSE:
				mp.hdsPause()
		elif fa == "redare":
			# ca a doua apasare pe galben (pauseEntry): redare, apoi playerul se ascunde
			if mp.seekstate != mp.SEEK_STATE_PLAY:
				mp.unPauseService()
				mp.hide()
		elif fa == "oprire":
			mp.stopEntry()
		elif fa == "urmatorul":
			mp.nextMarkOrEntry()
		elif fa == "anteriorul":
			mp.previousMarkOrEntry()
		elif fa == "salt":
			s = _secunde(argumente.get("secunde"), -SALT_MAX_S, SALT_MAX_S)
			if not s:
				return _raspuns(False, TXT_SECUNDE)
			if sesiune.nav.getCurrentService() is None:
				return _raspuns(False, TXT_NU_MERGE)
			mp.doSeekRelative(s * 90000)
		elif fa in ("reda", "scoate"):
			i = _intreg(argumente.get("index"))
			if i is None or not mp.hdsSelectEntry(i):
				return _raspuns(False, TXT_INTRARE)
			if fa == "reda":
				mp.ok()
			else:
				mp.deletePlaylistEntry()
		elif fa == "goleste":
			mp.clear_playlist()
		elif fa == "amesteca":
			if nivel < 1:
				return _raspuns(False, TXT_NIVEL)
			mp.playlist.PlayListShuffle()
		elif fa == "ascunde":
			mp.hide()
		elif fa == "arata":
			mp.show()
		elif fa == "inchide":
			mp.exit()
		elif fa == "salveaza-lista":
			if nivel < 1:
				return _raspuns(False, TXT_NIVEL)
			nume = argumente.get("nume", "").strip()
			from Components.HdsNavigator import isSafeName
			if nume and not isSafeName(nume + ".e2pls"):
				return _raspuns(False, TXT_NUME_RAU)
			mp.save_playlist2(nume)
			return _raspuns(True, TXT_LISTA_SALVATA)
		elif fa == "incarca-lista":
			nume = argumente.get("nume", "")
			dosar = dosar_liste if dosar_liste is not None else _dosarListe()
			if not nume or nume not in _listeSalvate(dosar):
				return _raspuns(False, TXT_LISTA_LIPSA)
			mp.PlaylistSelected((nume, os.path.join(dosar, nume)))
			return _raspuns(True, TXT_LISTA_INCARCATA)
		else:
			return _raspuns(False, TXT_COMANDA)
	except Exception as e:
		_jurnal("comanda %s: %s" % (fa, e))
		return _raspuns(False, TXT_NU_MERGE)
	return _raspuns(True, TXT_FACUT)


def seteazaPlayer(argumente, sesiune=None, cfg=None, clase=None, rad=None):
	"""POST /api/media-seteaza: ca "Edit settings" din meniul playerului (numai la nivelul intermediar sau expert, ca pe
	televizor). O valoare straina nu schimba nimic."""
	if _nivel(cfg) < 1:
		return _raspuns(False, TXT_NIVEL)
	sp = _setariPlayer(cfg)
	noi = []
	tine_dosarul = bool(sp.saveDirOnExit.value)
	for cheie, nume, eticheta in SETARI_PLAYER:
		if cheie not in argumente:
			continue
		element = getattr(sp, nume)
		bun, valoare = valoareNoua(element, argumente[cheie])
		if not bun:
			return _raspuns(False, TXT_ALEGERE, argumente[cheie][:40], _t(eticheta))
		noi.append((element, valoare))
		if nume == "saveDirOnExit":
			tine_dosarul = valoare
	if "dosar_pornire" in argumente:
		if tine_dosarul:
			return _raspuns(False, TXT_DOSAR_PORNIRE)
		text = argumente["dosar_pornire"]
		if text:
			if rad is None:
				rad = _radacini()
			if _hm().caleSigura(_caleDisc(text.rstrip("/")), rad, dosar=True) is None:
				return _raspuns(False, TXT_DOSAR_LIPSA)
			text = text.rstrip("/") + "/"
		noi.append((sp.defaultDir, text))
	if not noi:
		return _raspuns(False, TXT_NIMIC)
	_salveaza(noi)
	# ca la inchiderea ecranului de setari (openWithCallback(self.applySettings, ...))
	if sesiune is not None:
		mp = _gaseste(sesiune, (clase or _clase())["player"])
		if mp is not None:
			try:
				mp.applySettings()
			except Exception as e:
				_jurnal("applySettings: %s" % e)
	return _raspuns(True, TXT_SALVAT)


# ------------------------------------------------------------------------------------------- lista unui dosar

def _drum(text, r):
	"""[{nume, cale}] de la disc la dosarul `text` (cu / la sfarsit)."""
	baza = r["cale"] if (text == r["cale"] + "/" or text.startswith(r["cale"] + "/")) else r["real"]
	rest = text[len(baza):]
	drum = [{"nume": r["nume"], "cale": baza + "/"}]
	acum = baza
	for parte in [x for x in rest.split("/") if x]:
		acum = acum + "/" + parte
		drum.append({"nume": parte, "cale": acum + "/"})
	return drum


def lista(argumente, rad):
	"""GET /api/media-lista: dosarele si fisierele unui dosar (fel=player sau poze: extensiile ecranului), cu marimea si
	data; fara dosar, discurile cu locul liber. Citeste discul: ruleaza pe firul listelor."""
	hm = _hm()
	from Components.HdsNavigator import spaceInfo
	extensii = hm.EXTENSII_POZE if argumente.get("fel") == "poze" else hm.EXTENSII_PLAYER
	dosar = argumente.get("dosar", "")
	if not dosar:
		discuri = []
		for r in rad:
			loc = spaceInfo(r["real"], r["fel"])
			discuri.append({"nume": r["nume"], "cale": r["cale"] + "/", "fel": r["fel"], "liber": loc[0] if loc else None,
				"total": loc[1] if loc else None})
		return {"result": True, "dosar": "", "drum": [], "parinte": None, "dosare": discuri, "fisiere": [], "discuri": True}
	text = dosar.rstrip("/") + "/"
	x = hm.caleSigura(_caleDisc(text.rstrip("/")), rad, dosar=True)
	if x is None:
		return _raspuns(False, TXT_DOSAR_LIPSA)
	r = hm.radacinaPentru(x[1], rad)
	citit = hm.listeazaDosar(_caleDisc(text), extensii, rad)
	if citit is None:
		return _raspuns(False, TXT_DOSAR_CITIRE)
	dosare, fisiere, taiat = citit
	la_disc = os.path.normcase(x[1]) == os.path.normcase(r["real"])
	urcari = os.path.basename(x[1]) == DOSAR_URCARI and os.path.normcase(os.path.dirname(x[1])) == os.path.normcase(r["real"])
	return {
		"result": True,
		"dosar": text,
		"drum": _drum(text, r),
		"parinte": "" if la_disc else text.rstrip("/").rsplit("/", 1)[0] + "/",
		"dosare": [{"nume": _afisat(n), "cale": text + _afisat(n) + "/"} for n, _c in dosare],
		"fisiere": [{"nume": _afisat(n), "cale": text + _afisat(n), "marime": m, "data": d,
			"lista": hm.extensie(n) in hm.LISTE_REDARE, "urcat": urcari} for n, _c, m, d in fisiere],
		"taiat": taiat,
	}


# ------------------------------------------------------------------------------------------- trimiterea din telefon

def _dispozitiv(cale):
	try:
		return os.stat(cale).st_dev
	except OSError:
		return None


def _fs(r, tabel):
	from Components.HdsNavigator import mountKey
	for cale in (r["cale"], r["real"]):
		x = tabel.get(mountKey(cale))
		if x:
			return x[1]
	return ""


def discuriUrcare(rad=None, tabel=None):
	"""Discurile care primesc un fisier din telefon: locale (nu din retea: locul liber nu se poate citi fara riscul de a
	bloca receptorul), nu din memorie (tmpfs, ramfs ...), nu pe dispozitivul memoriei interne sau al /tmp, cu drept de
	scriere si cu locul liber citit. [{id, nume, liber, total, fat}]"""
	from Components.HdsNavigator import spaceInfo
	if rad is None:
		rad = _radacini()
	if tabel is None:
		tabel = _tabelMontari()
	memorie = set(_dispozitiv(c) for c in CAI_MEMORIE)
	memorie.discard(None)
	rez = []
	for r in rad:
		if r["fel"] == "net":
			continue
		fs = _fs(r, tabel)
		if fs in FS_MEMORIE or _dispozitiv(r["real"]) in memorie or not os.access(r["real"], os.W_OK):
			continue
		loc = spaceInfo(r["real"], r["fel"])
		if loc is None:
			continue
		rez.append({"id": r["cale"], "nume": r["nume"], "real": r["real"], "liber": loc[0], "total": loc[1],
			"fat": fs in FS_FAT})
	return rez


def curataNume(nume, extensii):
	"""Numele fisierului trimis, fara cale, fara semne pe care un stick FAT nu le primeste, fara punct la inceput si la
	sfarsit, cel mult MAX_NUME_OCTETI octeti (terminatia ramane); None daca terminatia nu e a playerului."""
	from Components.HdsNavigator import isSafeName
	hm = _hm()
	nume = (nume or "").replace("\\", "/").rsplit("/", 1)[-1]
	nume = "".join(c for c in nume if ord(c) >= 32 and ord(c) != 127 and c not in '<>:"|?*')
	nume = " ".join(nume.split()).strip(". ")
	ext = hm.extensie(nume)
	if ext not in extensii:
		return None
	trunchi = nume[:-(len(ext) + 1)].rstrip(". ")
	while trunchi and len((trunchi + "." + ext).encode("utf-8")) > MAX_NUME_OCTETI:
		trunchi = trunchi[:-1].rstrip(". ")
	nume = (trunchi or "fisier") + "." + ext
	if not isSafeName(nume) or not isSafeName(nume + ".part"):
		return None
	return nume


def _numeLiber(dosar, nume):
	"""Numele final: `nume`, sau "nume (2).ext" ... daca exista deja (un fisier existent nu se inlocuieste)."""
	if not os.path.lexists(os.path.join(dosar, nume)):
		return nume
	trunchi, punct, ext = nume.rpartition(".")
	for n in range(2, 1000):
		alt = "%s (%d).%s" % (trunchi, n, ext)
		if not os.path.lexists(os.path.join(dosar, alt)):
			return alt
	return None


class _Urcare(object):
	"""Trimiterea in curs (una singura): cheia, numele, dosarul, .part, marimea, cat a sosit, ora ultimei bucati."""

	def __init__(self):
		self.d = None
		self.scrie = [False]

	def stare(self, acum):
		d = self.d
		if d is None:
			return None
		return {"nume": d["nume"], "disc": d["disc"], "primit": d["primit"], "total": d["total"],
			"parasita": acum - d["ultima"] > TERMEN_ANULARE_STRAINA_S}

	def _sterge(self, d):
		try:
			os.unlink(d["part"])
		except OSError:
			pass

	def anuleaza(self, cheie, acum):
		d = self.d
		if d is None:
			return _raspuns(False, TXT_URCARE_NIMIC)
		if cheie != d["id"] and acum - d["ultima"] <= TERMEN_ANULARE_STRAINA_S:
			return _raspuns(False, TXT_URCARE_ALTA)
		if self.scrie[0]:
			# bucata de acum se scrie inca: .part se sterge la sfarsitul ei (d["anulata"])
			d["anulata"] = True
		else:
			self._sterge(d)
		self.d = None
		return _raspuns(True, TXT_URCARE_ANULATA)

	def pregateste(self, a, lungime, acum, discuri):
		"""Verificarile de pe firul enigma2, inainte de scriere: (lucru pentru fir, None) sau (None, (raspuns, cod))."""
		hm = _hm()
		pozitie = _intreg(a.get("pozitie"))
		total = _intreg(a.get("total"))
		cheie = a.get("id", "")
		if self.scrie[0]:
			rez = _raspuns(False, TXT_URCARE_OCUPAT)
			rez["reincearca"] = True
			return None, (rez, 503)
		d = self.d
		if not cheie:
			# o trimitere noua
			if d is not None and acum - d["ultima"] <= TERMEN_PARASITA_S:
				return None, (_raspuns(False, TXT_URCARE_ALTA), 409)
			if pozitie != 0:
				return None, (_raspuns(False, TXT_URCARE_ORDINE), 409)
			if total is None or total <= 0 or lungime > total:
				return None, (_raspuns(False, TXT_URCARE_TOTAL), 400)
			nume = curataNume(a.get("nume", ""), [e for e in hm.EXTENSII_PLAYER if e not in hm.LISTE_REDARE])
			if nume is None:
				return None, (_raspuns(False, TXT_URCARE_NUME), 400)
			disc = None
			for x in discuri:
				if x["id"] == a.get("disc", ""):
					disc = x
			if disc is None:
				return None, (_raspuns(False, TXT_URCARE_DISC), 400)
			if disc["fat"] and total > MAX_FAT:
				return None, (_raspuns(False, TXT_URCARE_FAT), 400)
			if disc["liber"] - total < REZERVA_OCTETI:
				from Components.HdsNavigator import formatSize
				return None, (_raspuns(False, TXT_URCARE_LOC, formatSize(total + REZERVA_OCTETI), formatSize(disc["liber"])), 400)
			if d is not None:
				_jurnal("trimiterea parasita %s inlocuita" % d["nume"])
				self._sterge(d)
			import binascii
			dosar = os.path.join(disc["real"], DOSAR_URCARI)
			self.d = d = {"id": binascii.hexlify(os.urandom(8)).decode("ascii"), "nume": nume, "disc": disc["id"],
				"real": disc["real"], "dosar": dosar, "part": os.path.join(dosar, nume + ".part"), "total": total,
				"primit": 0, "ultima": acum, "noua": True}
		else:
			if d is None or cheie != d["id"]:
				return None, (_raspuns(False, TXT_URCARE_NIMIC), 409)
			if pozitie != d["primit"]:
				rez = _raspuns(False, TXT_URCARE_ORDINE)
				rez["primit"] = d["primit"]
				return None, (rez, 409)
			if lungime <= 0 or d["primit"] + lungime > d["total"]:
				return None, (_raspuns(False, TXT_URCARE_TOTAL), 400)
			d["noua"] = False
		d["ultima"] = acum
		return d, None

	def scrieBucata(self, d, octeti):
		"""Pe firul de scriere: bucata in .part (la sfarsitul a ce a sosit), apoi, la ultima, redenumirea. Corpul
		raspunsului."""
		try:
			if d["noua"]:
				os.makedirs(d["dosar"], exist_ok=True)
				# dosarul trebuie sa fie chiar pe disc (nu o legatura care duce in alta parte)
				real = os.path.realpath(d["dosar"])
				if os.path.islink(d["dosar"]) or os.path.normcase(os.path.dirname(real)) != os.path.normcase(d["real"]):
					raise OSError("dosarul %s nu e pe disc" % d["dosar"])
				self._curataPartVechi(d)
				fd = os.open(d["part"], os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
					| getattr(os, "O_BINARY", 0), 0o644)
			else:
				fd = os.open(d["part"], os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
			try:
				if os.fstat(fd).st_size != d["primit"]:
					raise OSError(".part are %d octeti, nu %d" % (os.fstat(fd).st_size, d["primit"]))
				os.lseek(fd, d["primit"], os.SEEK_SET)
				scris = 0
				while scris < len(octeti):
					scris += os.write(fd, octeti[scris:])
				if d["primit"] + scris >= d["total"]:
					os.fsync(fd)
			finally:
				os.close(fd)
		except OSError as e:
			_jurnal("trimiterea %s: %s" % (d["nume"], e))
			self._sterge(d)
			if self.d is d:
				self.d = None
			return _raspuns(False, TXT_URCARE_SCRIERE)
		if d.get("anulata"):
			self._sterge(d)
			return _raspuns(False, TXT_URCARE_ANULATA)
		d["primit"] += len(octeti)
		if d["primit"] < d["total"]:
			return {"result": True, "id": d["id"], "primit": d["primit"], "total": d["total"], "gata": False}
		# toata: .part devine fisierul, cu un nume care nu inlocuieste nimic
		final = _numeLiber(d["dosar"], d["nume"])
		try:
			if final is None:
				raise OSError("niciun nume liber pentru %s" % d["nume"])
			os.rename(d["part"], os.path.join(d["dosar"], final))
		except OSError as e:
			_jurnal("redenumirea %s: %s" % (d["nume"], e))
			self._sterge(d)
			if self.d is d:
				self.d = None
			return _raspuns(False, TXT_URCARE_SCRIERE)
		if self.d is d:
			self.d = None
		_jurnal("fisier primit: %s (%d octeti)" % (final, d["total"]))
		dosar_text = _afisat(d["dosar"])
		# calea in forma paginii: discul cu numele lui stabil (ca lista de pe televizor), nu locul real
		cale = d["disc"].rstrip("/") + "/" + DOSAR_URCARI + "/" + _afisat(final)
		rez = _raspuns(True, TXT_URCARE_GATA, _afisat(final))
		rez.update({"id": d["id"], "primit": d["primit"], "total": d["total"], "gata": True, "cale": cale,
			"dosar": d["disc"].rstrip("/") + "/" + DOSAR_URCARI + "/", "nume": _afisat(final), "loc": dosar_text})
		return rez

	def _curataPartVechi(self, d):
		acum = time.time()
		try:
			nume = os.listdir(d["dosar"])
		except OSError:
			return
		for n in nume:
			if not n.endswith(".part"):
				continue
			cale = os.path.join(d["dosar"], n)
			try:
				if cale != d["part"] and os.path.isfile(cale) and not os.path.islink(cale) and \
						acum - os.path.getmtime(cale) > TERMEN_PART_VECHI_S:
					os.unlink(cale)
			except OSError:
				pass


_URCARE = _Urcare()


# ------------------------------------------------------------------------------------------- stergerea (doi pasi)

def _urcat(real, rad):
	"""True pentru un fisier trimis din telefon: chiar in <disc>/hds-din-telefon."""
	dosar = os.path.dirname(real)
	r = _hm().radacinaPentru(real, rad)
	return r is not None and os.path.basename(dosar) == DOSAR_URCARI and \
		os.path.normcase(os.path.dirname(dosar)) == os.path.normcase(r["real"])


def _tintaStergere(argumente, rad, dosar_liste=None):
	"""(actiune, tinta, text pentru intrebare, cale pe disc, fisier trimis din telefon) sau (None, mesaj). Un fisier: cu
	una din extensiile playerului, pe un disc pe care il vede pagina (HdsMedia.caleSigura: fara . si .., calea reala
	sub disc, fara memoria interna si dosarele sistemului)."""
	hm = _hm()
	fel = argumente.get("fel", "")
	if fel == "lista":
		nume = argumente.get("nume", "")
		dosar = dosar_liste if dosar_liste is not None else _dosarListe()
		if not nume or nume not in _listeSalvate(dosar):
			return None, TXT_LISTA_LIPSA
		return ("media-sterge-lista", nume, nume, os.path.join(dosar, nume), False), None
	if fel == "fisier":
		text = argumente.get("cale", "")
		x = hm.caleSigura(_caleDisc(text), rad, hm.EXTENSII_PLAYER)
		if x is None:
			return None, TXT_FISIER_LIPSA
		real = x[1]
		if hm.extensie(real) in hm.LISTE_REDARE or hm.extensie(text) in hm.LISTE_REDARE:
			return None, TXT_LISTA_DISC
		return ("media-sterge-fisier", text, text.rsplit("/", 1)[-1], real, _urcat(real, rad)), None
	return None, TXT_COMANDA


def _stergeDePeDisc(real):
	"""Ca "delete file" pe televizor: fisierul si fisierele lui (HdsMedia.fisiereDeSters), prin eBackgroundFileEraser,
	ca lib/service (redenumite pe loc in .del, sterse apoi pe firul radierei: un film de cativa GB nu tine firul
	enigma2); fara enigma (probele de pe PC), cu os.remove. True daca fisierul nu mai e la locul lui."""
	try:
		from enigma import eBackgroundFileEraser
		radiera = eBackgroundFileEraser.getInstance()
	except (ImportError, AttributeError):
		radiera = None
	for cale in _hm().fisiereDeSters(real):
		try:
			if radiera is not None:
				radiera.erase(cale)
			else:
				os.remove(cale)
		except (OSError, TypeError, ValueError) as e:
			_jurnal("stergerea %s: %s" % (cale, e))
	return not os.path.lexists(real)


def sterge(argumente, request=None, sesiune=None, cfg=None, clase=None, rad=None, dosar_liste=None):
	"""POST /api/media-sterge: in doi pasi (meniu_comun_web), numai din browserul conectat: un fisier al playerului, ca
	"delete file" din meniul playerului (nivelul intermediar sau expert; un fisier trimis din telefon la orice nivel),
	sau o lista de redare salvata (ca "delete saved playlist", numai la nivelul intermediar sau expert)."""
	M = _m()
	if request is not None:
		refuz = M.numaiBrowser(request)
		if refuz:
			return {"result": False, "message": refuz}
	if rad is None:
		rad = _radacini()
	tinta, mesaj = _tintaStergere(argumente, rad, dosar_liste)
	if tinta is None:
		return _raspuns(False, mesaj)
	actiune, cheie, nume, cale, urcat = tinta
	if _nivel(cfg) < 1 and not urcat:
		return _raspuns(False, TXT_NIVEL)
	pas = argumente.get("pas", "")
	if pas == "renunta":
		M.uita(actiune, cheie)
		return {"result": True, "message": ""}
	if pas == "intreaba":
		if actiune == "media-sterge-lista":
			return M.raspunsIntrebare(actiune, cheie, _t(TXT_INTREABA_LISTA) % nume, _t(TXT_DA_STERGE))
		insotite = [_afisat(os.path.basename(c)) for c in _hm().fisiereDeSters(cale)[1:]]
		detalii = [_t(TXT_INSOTITE) % ", ".join(insotite)] if insotite else []
		return M.raspunsIntrebare(actiune, cheie, _t(TXT_INTREABA_FISIER) % nume, _t(TXT_DA_STERGE), detalii)
	if not M.verifica(actiune, cheie, argumente.get("cod", "")):
		return M.codGresit()
	if actiune == "media-sterge-lista":
		try:
			os.remove(cale)
		except OSError as e:
			_jurnal("stergerea listei %s: %s" % (nume, e))
			return _raspuns(False, TXT_NU_STERS)
		return _raspuns(True, TXT_LISTA_STEARSA)
	# fisierul: nu cat merge pe televizor; din lista playerului deschis iese, ca dupa "delete file" pe televizor
	try:
		ref = sesiune.nav.getCurrentlyPlayingServiceReference() if sesiune is not None else None
		acum = ref.getPath() if ref is not None else ""
	except Exception:
		acum = ""
	if acum and os.path.realpath(_caleDisc(acum)) == cale:
		return _raspuns(False, TXT_MERGE_ACUM)
	if not _stergeDePeDisc(cale):
		return _raspuns(False, TXT_NU_STERS)
	_jurnal("fisier sters din pagina: %s" % cale)
	if sesiune is not None:
		mp = _gaseste(sesiune, (clase or _clase())["player"])
		if mp is not None:
			try:
				_scoateDinPlayer(mp, cheie)
			except Exception as e:
				_jurnal("lista playerului dupa stergere: %s" % e)
	return _raspuns(True, TXT_STERS)


def _scoateDinPlayer(mp, cale):
	"""Ca removeListEntry din player: lista de fisiere se reciteste, intrarile fisierului ies din lista de redare."""
	if mp.filelist.getCurrentDirectory():
		mp.filelist.changeDir(mp.filelist.getCurrentDirectory())
	schimbat = False
	for i in range(len(mp.playlist) - 1, -1, -1):
		if mp.playlist.getServiceRefList()[i].getPath() == cale:
			mp.playlist.deleteFile(i)
			schimbat = True
	if schimbat:
		mp.playlist.updateList()
		if mp.currList == "playlist" and len(mp.playlist) == 0:
			mp.switchToFileList()


# ------------------------------------------------------------------------------------------- pozele

def starePozeTv(sesiune, clase):
	"""Vizualizarea mare de pe televizor (Pic_Full_View): deschisa, poza, numarul, prezentarea."""
	v = _gaseste(sesiune, clase["vizualizare"]) if sesiune is not None else None
	if v is None:
		return {"deschis": False}
	lista = getattr(v, "filelist", None) or []
	i = getattr(v, "lastindex", 0)
	poza = _afisat(lista[i]) if 0 <= i < len(lista) else ""
	try:
		prezentare = bool(v.slideTimer.isActive())
	except Exception:
		prezentare = False
	return {"deschis": True, "in_fata": getattr(sesiune, "current_dialog", None) is v, "poza": poza,
		"nume": os.path.basename(poza), "numar": i + 1, "total": len(lista), "prezentare": prezentare}


def starePoze(sesiune=None, cfg=None, clase=None, rad=None):
	"""Pentru GET /api/poze."""
	clase = clase or _clase()
	if rad is None:
		rad = _radacini()
	sp = _setariPoze(cfg)
	return {
		"result": True,
		"tv": starePozeTv(sesiune, clase),
		"setari": [descrieSetare(cheie, getattr(sp, cheie), eticheta) for cheie, eticheta in SETARI_POZE],
		"dosar_start": _dosarStart(getattr(sp.lastDir, "value", "") or "", rad),
		"extensii": list(_hm().EXTENSII_POZE),
	}


def seteazaPoze(argumente, cfg=None):
	"""POST /api/poze-seteaza: ca Pic_Setup (tasta albastra din Poze). O valoare straina nu schimba nimic."""
	sp = _setariPoze(cfg)
	noi = []
	for cheie, eticheta in SETARI_POZE:
		if cheie not in argumente:
			continue
		element = getattr(sp, cheie)
		bun, valoare = valoareNoua(element, argumente[cheie])
		if not bun:
			return _raspuns(False, TXT_ALEGERE, argumente[cheie][:40], _t(eticheta))
		noi.append((element, valoare))
	if not noi:
		return _raspuns(False, TXT_NIMIC)
	_salveaza(noi)
	return _raspuns(True, TXT_SALVAT)


def pozeTv(argumente, sesiune=None, clase=None, rad=None):
	"""POST /api/poze-tv: vizualizarea mare de pe televizor. arata&cale= (OK pe poza in picshow: pozele dosarului,
	de la aceasta), prezentare[&cale=] (si tasta verde: prezentarea), opreste (verde din nou), inainte / inapoi
	(dreapta / stanga), inchide (exit)."""
	M = _m()
	refuz = M.ocupat(sesiune)
	if refuz:
		return {"result": False, "message": _t(refuz)}
	clase = clase or _clase()
	hm = _hm()
	fa = argumente.get("fa", "")
	curent = getattr(sesiune, "current_dialog", None)
	v = _gaseste(sesiune, clase["vizualizare"])
	if fa in ("arata", "prezentare") and argumente.get("cale"):
		if rad is None:
			rad = _radacini()
		x = hm.caleSigura(_caleDisc(argumente["cale"]), rad, hm.EXTENSII_POZE)
		if x is None:
			return _raspuns(False, TXT_POZA_LIPSA)
		dosar = os.path.dirname(x[0])
		poze = hm.pozeDinDosar(dosar)
		nume = [os.path.basename(p) for p in poze]
		if os.path.basename(x[0]) not in nume:
			return _raspuns(False, TXT_POZA_LIPSA)
		randuri = [((p, False), None) for p in poze]
		index = nume.index(os.path.basename(x[0]))
		if v is not None and v is curent:
			v.hdsShow(randuri, index, dosar + "/")
		elif isinstance(curent, clase["infobar"]) or isinstance(curent, clase["poze"]):
			v = sesiune.open(clase["vizualizare"], randuri, index, dosar + "/")
		else:
			return _raspuns(False, TXT_ALT_ECRAN)
		if fa == "prezentare" and not v.slideTimer.isActive():
			v.PlayPause()
		return _raspuns(True, TXT_PREZENTARE if fa == "prezentare" else TXT_POZA_TV)
	if v is None:
		return _raspuns(False, TXT_FARA_VIZUALIZARE)
	if v is not curent:
		return _raspuns(False, TXT_ALT_ECRAN)
	if fa == "prezentare":
		if not v.slideTimer.isActive():
			v.PlayPause()
		return _raspuns(True, TXT_PREZENTARE)
	if fa == "opreste":
		if v.slideTimer.isActive():
			v.PlayPause()
		return _raspuns(True, TXT_PREZENTARE_OPRITA)
	if fa == "inainte":
		v.nextPic()
	elif fa == "inapoi":
		v.prevPic()
	elif fa == "inchide":
		v.Exit()
	else:
		return _raspuns(False, TXT_COMANDA)
	return _raspuns(True, TXT_FACUT)


def infoPoza(argumente, rad=None, citeste=None):
	"""GET /api/poze-info: detaliile Exif, ca tasta INFO (Pic_Exif): aceleasi etichete, numele fara dosar."""
	hm = _hm()
	if rad is None:
		rad = _radacini()
	x = hm.caleSigura(_caleDisc(argumente.get("cale", "")), rad, hm.EXTENSII_POZE)
	if x is None:
		return _raspuns(False, TXT_POZA_LIPSA)
	try:
		if citeste is None:
			from enigma import ePicLoad
			citeste = ePicLoad().getInfo
		valori = list(citeste(x[0]) or [])
	except Exception as e:
		_jurnal("exif %s: %s" % (x[0], e))
		return _raspuns(False, TXT_POZA_INFO)
	etichete = [_t("filename") + ":"] + list(hm.ETICHETE_EXIF)
	randuri = []
	for i, valoare in enumerate(valori[:len(etichete)]):
		valoare = _afisat(str(valoare))
		if i == 0:
			valoare = os.path.basename(valoare)
		randuri.append([etichete[i], valoare])
	return {"result": True, "randuri": randuri}


def trimiteFisier(request, real, tip):
	"""Poza de pe disc, cu twisted.web.static.File: citita pe bucati de conexiune, cu Content-Type dupa terminatie,
	Content-Length si intervale; cache scurt, nosniff."""
	from twisted.web import static
	f = static.File(real, defaultType="application/octet-stream")
	f.contentTypes = {"." + _hm().extensie(real): tip}
	f.contentEncodings = {}
	f.type = tip
	f.encoding = None
	request.setHeader(b"cache-control", b"private, max-age=300")
	request.setHeader(b"x-content-type-options", b"nosniff")
	return f.render(request)


# ------------------------------------------------------------------------------------------- rutele

def marimeBucata(request, P=None):
	"""Cat de mare poate fi o bucata trimisa de pagina care a facut `request`: MAX_BUCATA cand serverul primeste corpul
	mare pentru cererile ei (plugin.corpMareMedia: cookie-ul de sesiune, sau browserul intrat fara cod, dintr-o pagina a
	receptorului), altfel BUCATA_MICA, sub limita de 64 KB a celorlalte cereri. Fara plugin (probele de pe PC) ramane
	MAX_BUCATA."""
	if P is None:
		return MAX_BUCATA
	try:
		try:
			are_cookie = bool(request.getCookie(P.NUME_COOKIE.encode("ascii")))
		except Exception:
			are_cookie = False
		mare = P.corpMareMedia(are_cookie, P._adresaClient(request), P._acelasiOriginCerere(request))
		return MAX_BUCATA if mare else BUCATA_MICA
	except Exception as e:
		_jurnal("marimea bucatii: %s" % e)
		return MAX_BUCATA


def _plugin():
	try:
		from . import plugin as P
		return P
	except Exception:
		return None


def argumente(request):
	"""Argumentele cererii ca text scurt (numai cheile stiute, fara token)."""
	return _m().argumente(request, CHEI, MAX_CALE)


_LISTARI = [0]


def rute(baza, resource, sesiune=None, cfg=None, clase=None, radacini=None, peLoc=False, fabrica_ceas=None,
		trimite=None, dosar_liste=None, ceas=None, plugin=None):
	"""Resursele: ({nume: resursa de sub /api}, {nume: pagina}). `baza` e HdsJsonResource din plugin.py. Probele de pe
	PC dau sesiunea, setarile, clasele ecranelor, radacinile, peLoc=True (firele ruleaza pe loc), trimite (servirea
	unei poze) si ceas (time.monotonic)."""

	def _ses():
		if sesiune is not None:
			return sesiune() if callable(sesiune) else sesiune
		return _m().sesiune()

	def _rad():
		return radacini() if callable(radacini) else (radacini if radacini is not None else _radacini())

	def _acum():
		return ceas() if ceas is not None else time.monotonic()

	def _bucata(request):
		return marimeBucata(request, plugin if plugin is not None else _plugin())

	def _peFir(request, obiect, lucru, steag, termen):
		if peLoc:
			rez = lucru()
			return obiect._raspunde(request, rez[0], rez[1]) if isinstance(rez, tuple) else obiect._raspunde(request, rez)
		return _m().peFir(request, lucru, steag, termen, fabrica_ceas)

	class _Citeste(baza):
		lucru = None

		def render_GET(self, request):
			try:
				return self._raspunde(request, type(self).lucru(argumente(request)))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class _Schimba(baza):
		schimbaCeva = True
		lucru = None

		def render_POST(self, request):
			try:
				return self._raspunde(request, type(self).lucru(argumente(request)))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class StareResource(baza):
		"""GET /api/media-player: numai citire; "bucata" = cat poate trimite pagina intr-o cerere (marimeBucata)."""

		def render_GET(self, request):
			try:
				rez = stare(_ses(), cfg, clase, _rad(), dosar_liste=dosar_liste)
				rez["bucata"] = _bucata(request)
				return self._raspunde(request, rez)
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class ListaResource(baza):
		"""GET /api/media-lista: numai citire; discul se citeste pe un fir separat (cel mult MAX_LISTARI odata)."""

		def render_GET(self, request):
			try:
				a = argumente(request)
				rad = _rad()
				if _LISTARI[0] >= MAX_LISTARI:
					return self._eroare(request, _t(TXT_LISTARI), 503)
				_LISTARI[0] += 1

				pornit = [False]

				def lucru():
					pornit[0] = True
					try:
						return lista(a, rad)
					except Exception as e:
						_jurnal("lista: %s" % e)
						return _raspuns(False, TXT_DOSAR_CITIRE)
					finally:
						_LISTARI[0] -= 1
				try:
					return _peFir(request, self, lucru, [False], TERMEN_LISTA_S)
				except Exception:
					if not pornit[0]:
						_LISTARI[0] -= 1   # firul nu a pornit: locul lui se elibereaza aici
					raise
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class PornesteResource(_Schimba):
		lucru = staticmethod(lambda a: porneste(a, _ses(), clase, _rad()))

	class ComandaResource(_Schimba):
		def render_POST(self, request):
			try:
				s = _ses()
				rez = comanda(argumente(request), s, cfg, clase, dosar_liste)
				st = stare(s, cfg, clase, _rad(), dosar_liste=dosar_liste)
				st["bucata"] = _bucata(request)
				st.update(rez)
				return self._raspunde(request, st)
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class SeteazaResource(_Schimba):
		def render_POST(self, request):
			try:
				s = _ses()
				rez = seteazaPlayer(argumente(request), s, cfg, clase, _rad())
				st = stare(s, cfg, clase, _rad(), dosar_liste=dosar_liste)
				st["bucata"] = _bucata(request)
				st.update(rez)
				return self._raspunde(request, st)
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class UrcaResource(baza):
		"""POST /api/media-urca: o bucata, octeti bruti in corp. Verificarile pe firul enigma2, scrierea pe un fir."""
		schimbaCeva = True

		def render_GET(self, request):
			return self._eroare(request, _t(TXT_URCARE_POST), 405)

		def render_POST(self, request):
			try:
				try:
					request.content.seek(0)
					octeti = request.content.read(MAX_BUCATA + 1)
				except Exception as eroare:
					return self._eroare(request, "nu am putut citi bucata: %s" % eroare)
				if len(octeti) > MAX_BUCATA:
					return self._raspunde(request, _raspuns(False, TXT_URCARE_MARE), 413)
				a = argumente(request)
				discuri = discuriUrcare(_rad()) if not a.get("id") else []
				d, refuz = _URCARE.pregateste(a, len(octeti), _acum(), discuri)
				if refuz is not None:
					return self._raspunde(request, refuz[0], refuz[1])
				_URCARE.scrie[0] = True

				def lucru():
					try:
						return _URCARE.scrieBucata(d, octeti)
					finally:
						_URCARE.scrie[0] = False
				return _peFir(request, self, lucru, [False], TERMEN_SCRIERE_S)
			except Exception as eroare:
				_URCARE.scrie[0] = False
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class AnuleazaResource(_Schimba):
		lucru = staticmethod(lambda a: _URCARE.anuleaza(a.get("id", ""), _acum()))

	class StergeResource(_Schimba):
		def render_POST(self, request):
			try:
				return self._raspunde(request, sterge(argumente(request), request, _ses(), cfg, clase, _rad(), dosar_liste))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self._eroare(request, _t(TXT_URCARE_POST), 405)

	class PozeResource(_Citeste):
		"""GET /api/poze: numai citire."""
		lucru = staticmethod(lambda a: starePoze(_ses(), cfg, clase, _rad()))

	class PozeSeteazaResource(_Schimba):
		def render_POST(self, request):
			try:
				rez = seteazaPoze(argumente(request), cfg)
				st = starePoze(_ses(), cfg, clase, _rad())
				st.update(rez)
				return self._raspunde(request, st)
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class PozeTvResource(_Schimba):
		def render_POST(self, request):
			try:
				s = _ses()
				rez = pozeTv(argumente(request), s, clase, _rad())
				rez["tv"] = starePozeTv(s, clase or _clase())
				return self._raspunde(request, rez)
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class PozaFisierResource(baza):
		"""GET /api/poze-fisier: numai pozele de pe discuri, dupa paza de cale."""

		def render_GET(self, request):
			hm = _hm()
			a = argumente(request)
			x = hm.caleSigura(_caleDisc(a.get("cale", "")), _rad(), hm.EXTENSII_POZE)
			if x is None:
				return self._eroare(request, _t(TXT_POZA_LIPSA), 404)
			tip = hm.TIPURI_POZE[hm.extensie(x[1])]
			return (trimite or trimiteFisier)(request, x[1], tip)

	class PozaInfoResource(_Citeste):
		lucru = staticmethod(lambda a: infoPoza(a, _rad()))

	class PaginaPlayer(resource.Resource):
		"""GET /player: pagina "Player media"."""
		isLeaf = True

		def render_GET(self, request):
			return _m().pagina(request, pagina_player)

	class PaginaPoze(resource.Resource):
		"""GET /poze: pagina "Poze"."""
		isLeaf = True

		def render_GET(self, request):
			return _m().pagina(request, pagina_poze)

	api = {
		b"media-player": StareResource(),
		b"media-lista": ListaResource(),
		b"media-porneste": PornesteResource(),
		b"media-comanda": ComandaResource(),
		b"media-seteaza": SeteazaResource(),
		b"media-urca": UrcaResource(),
		b"media-urca-anuleaza": AnuleazaResource(),
		b"media-sterge": StergeResource(),
		b"poze": PozeResource(),
		b"poze-seteaza": PozeSeteazaResource(),
		b"poze-tv": PozeTvResource(),
		b"poze-fisier": PozaFisierResource(),
		b"poze-info": PozaInfoResource(),
	}
	return api, {b"player": PaginaPlayer(), b"poze": PaginaPoze()}


# ------------------------------------------------------------------------------------------- paginile

def pagina_player(stil, config_pagina):
	M = _m()
	return M.sablon(_traducePagina(PAGINA_PLAYER), stil, config_pagina, {"__DRUM_MENIU__": M.drumHtml("media_player"),
		"__SCRIPT_GALERIE__": _traducePagina(SCRIPT_LISTA, "js")})


def pagina_poze(stil, config_pagina):
	M = _m()
	return M.sablon(_traducePagina(PAGINA_POZE), stil, config_pagina, {"__DRUM_MENIU__": M.drumHtml("hds_poze"),
		"__SCRIPT_GALERIE__": _traducePagina(SCRIPT_LISTA, "js")})


# scriptul comun al celor doua pagini: navigarea prin dosare (drumul, dosarele), marimile, setarile
SCRIPT_LISTA = r"""
function el(tag, cls, text){ var e = document.createElement(tag); if(cls){ e.className = cls; } if(text !== undefined){ e.textContent = text; } return e; }
function buton(text, cls, la){ var b = el("button", cls || "", text); b.type = "button"; b.addEventListener("click", la); return b; }
function mesajIn(unde, text, eroare){ var m = $(unde); if(!m){ mesaj(text, eroare); return; } m.textContent = text || ""; m.classList.toggle("eroare", !!eroare); }
function marime(o){
  if(o === null || o === undefined){ return ""; }
  if(o >= 1073741824){ return (o / 1073741824).toFixed(1).replace(".", ",") + " GB"; }
  if(o >= 1048576){ return Math.max(1, Math.round(o / 1048576)) + " MB"; }
  return Math.max(1, Math.round(o / 1024)) + " kB";
}
function data(s){
  var d = new Date(s * 1000);
  function doua(n){ return (n < 10 ? "0" : "") + n; }
  return doua(d.getDate()) + "." + doua(d.getMonth() + 1) + "." + d.getFullYear() + " " + doua(d.getHours()) + ":" + doua(d.getMinutes());
}
function trimite(cale, valori, unde){
  var q = new URLSearchParams();
  Object.keys(valori).forEach(function(k){ q.set(k, valori[k]); });
  mesajIn(unde, "Se trimite...");
  return cerere(cale, "POST", q).then(function(d){ mesajIn(unde, d.message, !d.result); return d; })
    .catch(function(){ mesajIn(unde, "Receptorul nu răspunde.", true); return {result: false}; });
}
// navigarea prin dosare: fel = player sau poze; arata(d) primeste raspunsul /api/media-lista
function Navigator(fel, unde, arata){
  this.fel = fel; this.unde = unde; this.arata = arata; this.dosar = ""; this.date = null; this.cerere = 0;
}
Navigator.prototype.deschide = function(dosar){
  var n = this, nr = ++n.cerere;
  mesajIn(n.unde, "Se citește dosarul...");
  return cerere("/api/media-lista?fel=" + n.fel + "&dosar=" + encodeURIComponent(dosar || "")).then(function(d){
    if(nr !== n.cerere){ return; }
    if(!d.result){ mesajIn(n.unde, d.message || "Dosarul nu se poate citi.", true); if(dosar){ return n.deschide(""); } return; }
    mesajIn(n.unde, d.taiat ? "Dosarul are foarte multe fișiere: se arată numai o parte." : "");
    n.dosar = d.dosar; n.date = d; n.arata(d);
  }).catch(function(){ mesajIn(n.unde, "Receptorul nu răspunde.", true); });
};
function deseneazaDrum(cutie, d, nav){
  cutie.textContent = "";
  cutie.appendChild(buton("Discuri", d.dosar ? "" : "principal", function(){ nav.deschide(""); }));
  // numele care nu incape se deruleaza (hds-derulant, cadru_web.py): dosarul de acum mereu, celelalte cu mouse-ul sau
  // cu focusul
  (d.drum || []).forEach(function(p, i){
    cutie.appendChild(buton(p.nume, i === d.drum.length - 1 ? "principal hds-derulant" : "hds-derulant hds-derulant-rand",
      function(){ nav.deschide(p.cale); }));
  });
}
function rowSetare(s, la){
  var rand = el("div", "rand");
  var l = el("label", "", s.eticheta); l.setAttribute("for", "s_" + s.cheie);
  var camp;
  if(s.fel === "numar"){
    camp = el("input"); camp.type = "number"; camp.min = s.min; camp.max = s.max; camp.step = 1; camp.value = s.valoare; camp.inputMode = "numeric";
    var a = el("p", "ajutor nota", "Între " + s.min + " și " + s.max + "."); rand.appendChild(l); rand.appendChild(camp); rand.appendChild(a);
  } else {
    camp = el("select");
    (s.alegeri || []).forEach(function(x){ var o = el("option", "", x[1]); o.value = x[0]; camp.appendChild(o); });
    camp.value = s.valoare;
    rand.appendChild(l); rand.appendChild(camp);
  }
  camp.id = "s_" + s.cheie;
  camp.addEventListener("change", la);
  return rand;
}
"""

PAGINA_PLAYER = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Player media</title>
<style>__STIL_COMUN__
__STIL_PAGINI__
  .drum,.dosare{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 10px;}
  .drum button{max-width:100%;overflow:hidden;white-space:nowrap;}
  .fisier{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;align-items:center;padding:8px 0;border-bottom:1px solid var(--bordura);}
  .fisier:last-child{border-bottom:0;}
  .fisier .nume{margin:0;overflow-wrap:anywhere;}
  .fisier .detalii{margin:2px 0 0;font-size:.8rem;color:var(--text-slab);}
  .fisier .butoane{margin:0;justify-content:flex-end;}
  .acum .nume{font-size:1.05rem;font-weight:600;margin:0 0 4px;overflow-wrap:anywhere;}
  .bara{height:10px;border-radius:5px;background:var(--camp);border:1px solid var(--bordura);overflow:hidden;margin:6px 0 4px;}
  .bara div{height:100%;width:0;background:var(--accent);}
  .timp{display:flex;justify-content:space-between;font-size:.9rem;color:var(--text-slab);}
  .intrare.curenta .nume{font-weight:600;}
  .urcare{display:grid;grid-template-columns:minmax(0,1fr);gap:10px;}
  .urcare input[type=file]{width:100%;box-sizing:border-box;}
  .rand>*{min-width:0;}
  .rand.dosar span{overflow-wrap:anywhere;}
  .rand.dosar .butoane{grid-column:1 / -1;margin:0;}
  @media (max-width:560px){ .fisier{grid-template-columns:minmax(0,1fr);} .fisier .butoane{justify-content:flex-start;} }
</style>
</head>
<body>
<main>
<h1>Player media</h1>
<section class="card acum">
  <h2>Pe televizor</h2>
  <div id="tvInchis">
    <p class="nota">Playerul nu este deschis pe televizor. Alege mai jos un fișier și pornește-l, sau deschide playerul.</p>
    <div class="butoane"><button type="button" id="bDeschide">Deschide playerul pe televizor</button></div>
  </div>
  <div id="tvDeschis" class="ascuns">
    <p class="nume" id="acumNume"></p>
    <p class="nota" id="acumStare"></p>
    <div class="bara"><div id="progres"></div></div>
    <div class="timp"><span id="pozitie"></span><span id="lungime"></span></div>
    <div class="butoane">
      <button type="button" data-fa="anteriorul">Anteriorul</button>
      <button type="button" data-fa="salt" data-s="-10">-10 s</button>
      <button type="button" class="principal" id="bPauza">Pune pauză</button>
      <button type="button" data-fa="salt" data-s="10">+10 s</button>
      <button type="button" data-fa="urmatorul">Următorul</button>
      <button type="button" data-fa="oprire">Oprește</button>
    </div>
    <div class="butoane">
      <button type="button" id="bAscunde">Ascunde playerul</button>
      <button type="button" data-fa="inchide">Închide playerul</button>
    </div>
  </div>
  <p class="nota">Un film pornit din lista de filme se comandă din pagina <a href="/filme">Filmul de acum</a>, unde sunt și derularea și saltul la un loc anume.</p>
  <p class="mesaj" id="mesajTv"></p>
</section>
<section class="card">
  <h2>Fișierele de pe receptor</h2>
  <div class="drum" id="drum"></div>
  <div id="fisiere"></div>
  <p class="mesaj" id="mesajFisiere"></p>
</section>
<section class="card">
  <h2>Din telefon sau calculator</h2>
  <div class="urcare">
    <p class="nota" id="urcareExplicatie">Alege un fișier: se trimite pe receptor, apoi îl pornești pe televizor.</p>
    <div class="rand"><label for="disc">Discul pe care se pune</label><select id="disc"></select></div>
    <input type="file" id="fisier" aria-label="Fișierul de trimis">
    <div class="butoane">
      <button type="button" class="principal" id="bTrimite" disabled>Trimite pe receptor</button>
      <button type="button" class="rosu ascuns" id="bAnuleaza">Anulează</button>
    </div>
    <div class="ascuns" id="urcareProgres"><div class="bara"><div id="urcareBara"></div></div><p class="nota" id="urcareText"></p></div>
    <div class="butoane ascuns" id="urcareGata"><button type="button" class="principal" id="bPornesteUrcat">Pornește pe televizor</button></div>
  </div>
  <p class="mesaj" id="mesajUrcare"></p>
</section>
<section class="card ascuns" id="cardLista">
  <h2 id="titluLista">Lista de redare</h2>
  <div id="intrari"></div>
  <div class="butoane">
    <button type="button" data-fa="amesteca" class="nivel1">Amestecă</button>
    <button type="button" data-fa="goleste">Golește lista</button>
  </div>
  <div class="rand"><label for="listeSalvate">Liste salvate</label><select id="listeSalvate"></select></div>
  <div class="butoane">
    <button type="button" id="bIncarca">Încarcă lista</button>
    <button type="button" class="rosu nivel1" id="bStergeLista">Șterge lista salvată</button>
  </div>
  <div class="rand nivel1"><label for="numeLista">Salvează lista ca</label><input type="text" id="numeLista" maxlength="120" placeholder="gol: data de azi"></div>
  <div class="butoane nivel1"><button type="button" id="bSalveazaLista">Salvează lista</button></div>
  <p class="mesaj" id="mesajLista"></p>
</section>
<section class="card">
  <h2>Setările playerului</h2>
  <p class="nota ascuns" id="setariNivel">Pe televizor, setările playerului apar numai cu nivelul de meniu Intermediar sau Expert.</p>
  <div id="randuri"></div>
  <div class="butoane" id="setariButoane"><button type="button" class="principal" id="bSalveaza">Salvează</button></div>
  <p class="mesaj" id="mesajSetari"></p>
</section>
<p class="nota">Aceleași setări sunt pe televizor, în __DRUM_MENIU__ (în meniul playerului, tasta Menu), unde sunt și aceleași comenzi. Din pagină se văd numai stick-urile și discurile, nu memoria internă a receptorului.</p>
<p class="mesaj" id="mesaj"></p>
<div id="confirmare" class="card ascuns"></div>
</main>
<script>
__SCRIPT_COMUN__
__SCRIPT_GALERIE__
var DATE = null, NAV = null, SETARI_SCHIMBATE = false, DOSAR_PORNIRE = null, URC = null, URCAT = null, INCEPUT = false;
function comanda(fa, extra){
  var v = {fa: fa}; Object.keys(extra || {}).forEach(function(k){ v[k] = extra[k]; });
  return trimite("/api/media-comanda", v, "mesajTv").then(function(d){ if(d && d.tv){ arata(d); } return d; });
}
function arataTv(tv){
  $("tvInchis").classList.toggle("ascuns", !!tv.deschis);
  $("tvDeschis").classList.toggle("ascuns", !tv.deschis);
  $("cardLista").classList.toggle("ascuns", !tv.deschis);
  if(!tv.deschis){ return; }
  var r = tv.redare;
  $("acumNume").textContent = r ? r.nume : "Nu merge nimic acum.";
  $("acumStare").textContent = r ? r.stare : "";
  $("pozitie").textContent = r ? r.text_pozitie : "";
  $("lungime").textContent = r ? r.text_lungime : "";
  $("progres").style.width = (r && r.lungime && r.pozitie !== null) ? Math.min(100, Math.round(100 * r.pozitie / r.lungime)) + "%" : "0";
  $("bPauza").textContent = (r && r.pauza) ? "Redă" : "Pune pauză";
  $("bAscunde").textContent = tv.ascuns ? "Arată playerul" : "Ascunde playerul";
  $("titluLista").textContent = tv.marime_lista ? ("Lista de redare (" + tv.marime_lista + ")") : "Lista de redare este goală";
  var c = $("intrari"); c.textContent = "";
  (tv.lista || []).forEach(function(x, i){
    var rand = el("div", "fisier intrare" + (i === tv.curent ? " curenta" : ""));
    var st = el("div"); st.appendChild(el("p", "nume", (i === tv.curent ? "Acum: " : "") + x.nume)); rand.appendChild(st);
    var b = el("div", "butoane");
    b.appendChild(buton("Pornește", "", function(){ comanda("reda", {index: String(i)}); }));
    b.appendChild(buton("Scoate din listă", "", function(){ comanda("scoate", {index: String(i)}); }));
    rand.appendChild(b); c.appendChild(rand);
  });
}
function arataListe(d){
  var s = $("listeSalvate"), ales = s.value; s.textContent = "";
  (d.liste_salvate || []).forEach(function(n){ var o = el("option", "", n); o.value = n; s.appendChild(o); });
  if(ales){ s.value = ales; }
  $("bIncarca").disabled = !(d.liste_salvate || []).length;
  $("bStergeLista").disabled = !(d.liste_salvate || []).length;
  Array.prototype.forEach.call(document.querySelectorAll(".nivel1"), function(x){ x.classList.toggle("ascuns", d.nivel < 1); });
}
function arataSetari(d){
  $("setariNivel").classList.toggle("ascuns", d.nivel >= 1);
  $("randuri").classList.toggle("ascuns", d.nivel < 1);
  $("setariButoane").classList.toggle("ascuns", d.nivel < 1);
  var c = $("randuri"); c.textContent = "";
  DOSAR_PORNIRE = null;
  (d.setari || []).forEach(function(s){
    if(s.fel === "dosar"){
      var rand = el("div", "rand dosar");
      rand.appendChild(el("label", "", s.eticheta));
      var t = el("span", "", s.valoare || s.text_gol); t.id = "dosarPornire"; rand.appendChild(t);
      var b = el("div", "butoane");
      b.appendChild(buton("Dosarul deschis mai sus", "", function(){ if(!NAV.dosar){ mesajIn("mesajSetari", "Deschide întâi un dosar în lista de fișiere.", true); return; } DOSAR_PORNIRE = NAV.dosar; t.textContent = NAV.dosar; SETARI_SCHIMBATE = true; }));
      b.appendChild(buton(s.text_gol, "", function(){ DOSAR_PORNIRE = ""; t.textContent = s.text_gol; SETARI_SCHIMBATE = true; }));
      rand.appendChild(b); c.appendChild(rand);
      return;
    }
    c.appendChild(rowSetare(s, function(){ SETARI_SCHIMBATE = true; }));
  });
  SETARI_SCHIMBATE = false;
}
function arataDiscuri(d){
  var s = $("disc"), ales = s.value; s.textContent = "";
  (d.discuri || []).forEach(function(x){ var o = el("option", "", x.nume + " (" + marime(x.liber) + " libere)"); o.value = x.id; s.appendChild(o); });
  if(ales){ s.value = ales; }
  var are = (d.discuri || []).length > 0;
  if(!are){ $("urcareExplicatie").textContent = "Nu e niciun stick sau disc pe care să se poată pune un fișier. Pune un stick în receptor."; }
  else { $("urcareExplicatie").textContent = "Alege un fișier: se trimite pe receptor, în dosarul hds-din-telefon al discului, apoi îl pornești pe televizor."; }
  $("fisier").setAttribute("accept", (d.extensii_urcare || []).map(function(e){ return "." + e; }).join(","));
  $("bTrimite").disabled = !are || !!URC || !($("fisier").files && $("fisier").files[0]);
  var u = d.urcare;
  if(!URC && u){
    $("urcareProgres").classList.remove("ascuns");
    $("urcareText").textContent = "Se trimite alt fișier: " + u.nume + ", " + marime(u.primit) + " din " + marime(u.total) + ".";
    $("urcareBara").style.width = Math.round(100 * u.primit / Math.max(1, u.total)) + "%";
    $("bAnuleaza").classList.toggle("ascuns", !u.parasita);
  } else if(!URC){ $("urcareProgres").classList.add("ascuns"); $("bAnuleaza").classList.add("ascuns"); }
}
function arata(d){
  DATE = d;
  arataTv(d.tv || {});
  arataListe(d);
  arataDiscuri(d);
  var a = document.activeElement;
  if(!SETARI_SCHIMBATE && !(a && (a.tagName === "SELECT" || a.tagName === "INPUT") && $("randuri").contains(a))){ arataSetari(d); }
}
function citeste(){
  if(document.hidden){ return Promise.resolve(); }
  return cerere("/api/media-player").then(function(d){
    if(!d.result){ mesajIn("mesajTv", d.message || "Receptorul nu a putut citi playerul.", true); return; }
    arata(d);
    if(!INCEPUT){ INCEPUT = true; NAV.deschide(d.dosar_start || ""); }
  }).catch(function(){ mesajIn("mesajTv", "Receptorul nu răspunde. Verifică dacă este pornit și în aceeași rețea.", true); });
}
function porneste(cale, fa){
  return trimite("/api/media-porneste", {cale: cale, fa: fa}, "mesajFisiere").then(function(){ setTimeout(citeste, 800); });
}
function randFisier(f, d){
  var rand = el("div", "fisier");
  var st = el("div");
  st.appendChild(el("p", "nume", f.nume));
  st.appendChild(el("p", "detalii", marime(f.marime) + " · " + data(f.data)));
  rand.appendChild(st);
  var b = el("div", "butoane");
  if(!f.lista){ b.appendChild(buton("Pornește pe televizor", "principal", function(){ porneste(f.cale, "porneste"); })); }
  b.appendChild(buton(f.lista ? "Încarcă în listă" : "Adaugă în listă", "", function(){ porneste(f.cale, "adauga"); }));
  // ca "delete file" din meniul playerului de pe televizor (nivelul Intermediar sau Expert); un fisier trimis din telefon
  // la orice nivel; listele de redare de pe disc nu
  if(f.urcat || (!f.lista && DATE && DATE.nivel >= 1)){
    b.appendChild(buton("Șterge", "rosu", function(){
      cuConfirmare("/api/media-sterge", new URLSearchParams({fel: "fisier", cale: f.cale}), function(r){ mesajIn("mesajFisiere", r.message, !r.result); NAV.deschide(NAV.dosar); });
    }));
  }
  rand.appendChild(b);
  return rand;
}
function arataDosar(d){
  deseneazaDrum($("drum"), d, NAV);
  var c = $("fisiere"); c.textContent = "";
  if(d.discuri){
    if(!(d.dosare || []).length){ c.appendChild(el("p", "nota", "Nu e niciun stick sau disc la receptor.")); }
    d.dosare.forEach(function(x){
      var rand = el("div", "fisier"), st = el("div");
      st.appendChild(el("p", "nume", x.nume));
      if(x.total){ st.appendChild(el("p", "detalii", marime(x.liber) + " libere din " + marime(x.total))); }
      rand.appendChild(st);
      var b = el("div", "butoane"); b.appendChild(buton("Deschide", "principal", function(){ NAV.deschide(x.cale); }));
      rand.appendChild(b); c.appendChild(rand);
    });
    return;
  }
  if(d.parinte !== null){
    var sus = el("div", "butoane"); sus.appendChild(buton("Un dosar mai sus", "", function(){ NAV.deschide(d.parinte); })); c.appendChild(sus);
  }
  (d.dosare || []).forEach(function(x){
    var rand = el("div", "fisier"), st = el("div");
    st.appendChild(el("p", "nume", x.nume + "/")); rand.appendChild(st);
    var b = el("div", "butoane");
    b.appendChild(buton("Deschide", "", function(){ NAV.deschide(x.cale); }));
    b.appendChild(buton("Pornește tot dosarul", "", function(){ porneste(x.cale, "porneste"); }));
    b.appendChild(buton("Adaugă dosarul în listă", "", function(){ porneste(x.cale, "adauga"); }));
    rand.appendChild(b); c.appendChild(rand);
  });
  (d.fisiere || []).forEach(function(f){ c.appendChild(randFisier(f, d)); });
  if(!(d.dosare || []).length && !(d.fisiere || []).length){ c.appendChild(el("p", "nota", "Dosarul nu are fișiere pe care playerul le poate reda.")); }
}
// trimiterea unui fisier, in bucati (Blob.slice), una dupa alta
function progresUrcare(){
  var p = URC ? URC.pozitie : 0, t = URC ? URC.f.size : 1;
  $("urcareBara").style.width = Math.round(100 * p / Math.max(1, t)) + "%";
  $("urcareText").textContent = "Trimis " + marime(p) + " din " + marime(t) + ".";
}
function sfarsitUrcare(text, eroare){
  URC = null;
  $("bAnuleaza").classList.add("ascuns");
  $("bTrimite").disabled = !($("fisier").files && $("fisier").files[0]);
  mesajIn("mesajUrcare", text, eroare);
}
function bucata(){
  if(!URC || URC.oprit){ return; }
  var f = URC.f, p = URC.pozitie, sf = Math.min(f.size, p + URC.marime);
  var q = new URLSearchParams(); q.set("nume", f.name); q.set("pozitie", String(p)); q.set("total", String(f.size)); q.set("disc", URC.disc);
  if(URC.id){ q.set("id", URC.id); }
  var antete = {"Content-Type": "application/octet-stream"};
  if(CFG.csrf){ antete["X-HDS-CSRF"] = CFG.csrf; }
  fetch(adresa("/api/media-urca?" + q.toString()), {method: "POST", body: f.slice(p, sf), cache: "no-store", credentials: "same-origin", headers: antete})
    .then(function(r){
      if(r.status === 413){ return {result: false, message: "Receptorul nu primește bucăți atât de mari."}; }
      return r.json().catch(function(){ return {result: false, message: "Receptorul a răspuns neașteptat (HTTP " + r.status + ")."}; });
    }).then(function(d){
      if(!URC || URC.oprit){ return; }
      if(d.id){ URC.id = d.id; }
      if(!d.result){
        if(typeof d.primit === "number" && URC.id && URC.incercari < 5){ URC.incercari++; URC.pozitie = d.primit; bucata(); return; }
        if(d.reincearca && URC.incercari < 5){ URC.incercari++; setTimeout(bucata, 1000); return; }
        sfarsitUrcare(d.message || "Fișierul nu s-a putut trimite.", true); return;
      }
      URC.incercari = 0; URC.pozitie = d.primit; progresUrcare();
      if(d.gata){
        URCAT = d.cale; sfarsitUrcare(d.message, false);
        $("urcareGata").classList.remove("ascuns");
        $("fisier").value = ""; $("bTrimite").disabled = true;
        NAV.deschide(d.dosar);
        return;
      }
      bucata();
    }).catch(function(){
      if(URC && URC.incercari < 3){ URC.incercari++; setTimeout(bucata, 1500); return; }
      sfarsitUrcare("Receptorul nu răspunde. Trimiterea s-a oprit.", true);
    });
}
$("fisier").addEventListener("change", function(){
  var f = this.files && this.files[0];
  $("bTrimite").disabled = !f || !!URC || !$("disc").value;
  $("urcareGata").classList.add("ascuns");
  if(!f){ mesajIn("mesajUrcare", ""); return; }
  var disc = (DATE && DATE.discuri || []).filter(function(x){ return x.id === $("disc").value; })[0];
  if(disc && f.size > disc.liber){ mesajIn("mesajUrcare", "Fișierul are " + marime(f.size) + ", iar pe disc sunt liberi " + marime(disc.liber) + ".", true); return; }
  mesajIn("mesajUrcare", "Gata de trimis: " + f.name + ", " + marime(f.size) + ".");
});
$("bTrimite").addEventListener("click", function(){
  var f = $("fisier").files && $("fisier").files[0];
  if(!f || URC){ return; }
  URC = {f: f, disc: $("disc").value, pozitie: 0, id: "", incercari: 0, oprit: false, marime: (DATE && DATE.bucata) || 4194304};
  $("bTrimite").disabled = true; $("bAnuleaza").classList.remove("ascuns");
  $("urcareProgres").classList.remove("ascuns"); $("urcareGata").classList.add("ascuns");
  mesajIn("mesajUrcare", "Se trimite " + f.name + "...");
  progresUrcare(); bucata();
});
$("bAnuleaza").addEventListener("click", function(){
  var id = URC ? URC.id : "";
  if(URC){ URC.oprit = true; }
  var q = new URLSearchParams(); q.set("id", id);
  cerere("/api/media-urca-anuleaza", "POST", q).then(function(d){ sfarsitUrcare(d.message, !d.result); $("urcareProgres").classList.add("ascuns"); citeste(); })
    .catch(function(){ sfarsitUrcare("Receptorul nu răspunde.", true); });
});
$("bPornesteUrcat").addEventListener("click", function(){ if(URCAT){ porneste(URCAT, "porneste"); } });
$("bDeschide").addEventListener("click", function(){ comanda("deschide"); });
$("bPauza").addEventListener("click", function(){ var r = DATE && DATE.tv && DATE.tv.redare; comanda(r && r.pauza ? "redare" : "pauza"); });
$("bAscunde").addEventListener("click", function(){ comanda(DATE && DATE.tv && DATE.tv.ascuns ? "arata" : "ascunde"); });
Array.prototype.forEach.call(document.querySelectorAll("button[data-fa]"), function(b){
  b.addEventListener("click", function(){
    var extra = {};
    if(b.getAttribute("data-s")){ extra.secunde = b.getAttribute("data-s"); }
    comanda(b.getAttribute("data-fa"), extra);
  });
});
$("bIncarca").addEventListener("click", function(){ comanda("incarca-lista", {nume: $("listeSalvate").value}); });
$("bSalveazaLista").addEventListener("click", function(){ comanda("salveaza-lista", {nume: $("numeLista").value.trim()}).then(function(d){ if(d && d.result){ $("numeLista").value = ""; } }); });
$("bStergeLista").addEventListener("click", function(){
  cuConfirmare("/api/media-sterge", new URLSearchParams({fel: "lista", nume: $("listeSalvate").value}), function(r){ mesajIn("mesajLista", r.message, !r.result); citeste(); });
});
$("bSalveaza").addEventListener("click", function(){
  var v = {};
  (DATE && DATE.setari || []).forEach(function(s){ if(s.fel !== "dosar"){ var c = $("s_" + s.cheie); if(c){ v[s.cheie] = c.value; } } });
  if(DOSAR_PORNIRE !== null){ v.dosar_pornire = DOSAR_PORNIRE; }
  trimite("/api/media-seteaza", v, "mesajSetari").then(function(d){ if(d && d.setari){ SETARI_SCHIMBATE = false; arata(d); arataSetari(d); } });
});
NAV = new Navigator("player", "mesajFisiere", arataDosar);
citeste();
setInterval(citeste, 3000);
</script>
</body>
</html>
"""

PAGINA_POZE = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Poze</title>
<style>__STIL_COMUN__
__STIL_PAGINI__
  .drum,.dosare{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 10px;}
  .rand>*{min-width:0;}
  .drum button,.dosare button{max-width:100%;overflow:hidden;white-space:nowrap;}
  .grila{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:8px;}
  .miniatura{display:flex;flex-direction:column;align-items:stretch;padding:0;overflow:hidden;text-align:left;}
  .miniatura img{display:block;width:100%;aspect-ratio:1/1;object-fit:cover;background:var(--camp);}
  .miniatura span{display:block;padding:6px 8px;font-size:.8rem;overflow:hidden;white-space:nowrap;}
  .mare{position:fixed;top:0;right:0;bottom:0;left:0;z-index:1000;background:var(--fundal);display:flex;flex-direction:column;}
  .mare .sus{display:flex;align-items:center;gap:8px;padding:8px 12px;border-bottom:1px solid var(--bordura);}
  .mare .sus .nume{flex:1 1 auto;min-width:0;overflow:hidden;white-space:nowrap;margin:0;}
  .mare .poza{flex:1 1 auto;min-height:0;display:flex;align-items:center;justify-content:center;position:relative;padding:8px;}
  .mare .poza img{max-width:100%;max-height:100%;object-fit:contain;}
  .mare .sageata{position:absolute;top:50%;transform:translateY(-50%);min-width:48px;min-height:64px;font-size:1.4rem;}
  .mare .stanga{left:8px;}
  .mare .dreapta{right:8px;}
  .mare .jos{display:flex;flex-wrap:wrap;gap:8px;padding:10px 12px;justify-content:center;border-top:1px solid var(--bordura);}
  .mare .detalii{max-height:35vh;overflow:auto;padding:0 12px;}
  .mare .mesaj{padding:0 12px;margin:6px 0;}
</style>
</head>
<body>
<main>
<h1>Poze</h1>
<section class="card">
  <h2>Pe televizor</h2>
  <p class="nota" id="tvStare">Pe televizor nu se arată nicio poză. Alege o poză mai jos și apasă Arată pe televizor.</p>
  <div class="butoane ascuns" id="tvButoane">
    <button type="button" data-fa="inapoi">Poza de dinainte</button>
    <button type="button" class="principal" id="bPrezentare">Pornește prezentarea</button>
    <button type="button" data-fa="inainte">Poza următoare</button>
    <button type="button" data-fa="inchide">Închide pe televizor</button>
  </div>
  <p class="mesaj" id="mesajTv"></p>
</section>
<section class="card">
  <h2>Dosarele cu poze</h2>
  <div class="drum" id="drum"></div>
  <div class="dosare" id="dosare"></div>
  <div class="butoane ascuns" id="dosarButoane"><button type="button" id="bPrezentareDosar">Prezentare pe televizor din prima poză</button></div>
  <div class="grila" id="grila"></div>
  <p class="mesaj" id="mesajPoze"></p>
</section>
<section class="card">
  <h2>Setările pozelor</h2>
  <div id="randuri"></div>
  <div class="butoane"><button type="button" class="principal" id="bSalveaza">Salvează</button></div>
  <p class="mesaj" id="mesajSetari"></p>
</section>
<p class="nota">Aceleași setări sunt pe televizor, în __DRUM_MENIU__ (tasta albastră). Miniaturile le face browserul din poze; din pagină se văd numai stick-urile și discurile, nu memoria internă a receptorului.</p>
<p class="mesaj" id="mesaj"></p>
<div id="confirmare" class="card ascuns"></div>
</main>
<div class="mare ascuns" id="mare" role="dialog" aria-modal="true" aria-label="Poza mare">
  <div class="sus"><p class="nume hds-derulant" id="mareNume"></p><button type="button" id="bInchideMare">Închide</button></div>
  <div class="poza">
    <img id="mareImg" alt="">
    <button type="button" class="sageata stanga" id="bStanga" aria-label="Poza de dinainte">&lt;</button>
    <button type="button" class="sageata dreapta" id="bDreapta" aria-label="Poza următoare">&gt;</button>
  </div>
  <div class="detalii ascuns" id="mareDetalii"></div>
  <p class="mesaj" id="mesajMare"></p>
  <div class="jos">
    <button type="button" class="principal" id="bArataTv">Arată pe televizor</button>
    <button type="button" id="bPrezentareAici">Prezentare pe televizor de aici</button>
    <button type="button" id="bDetalii">Detalii</button>
  </div>
</div>
<script>
__SCRIPT_COMUN__
__SCRIPT_GALERIE__
var DATE = null, NAV = null, POZE = [], MARE = -1, SETARI_SCHIMBATE = false, INCEPUT = false, ATINS = null;
function pozaUrl(cale){ return adresa("/api/poze-fisier?cale=" + encodeURIComponent(cale)); }
function tv(fa, cale, unde){
  var v = {fa: fa}; if(cale){ v.cale = cale; }
  return trimite("/api/poze-tv", v, unde || "mesajTv").then(function(d){ if(d && d.tv){ arataTv(d.tv); } return d; });
}
function arataTv(t){
  $("tvButoane").classList.toggle("ascuns", !t.deschis);
  if(!t.deschis){ $("tvStare").textContent = "Pe televizor nu se arată nicio poză. Alege o poză mai jos și apasă Arată pe televizor."; return; }
  $("tvStare").textContent = "Pe televizor: " + t.nume + ", poza " + t.numar + " din " + t.total + (t.prezentare ? ", prezentarea merge." : ".");
  $("bPrezentare").textContent = t.prezentare ? "Oprește prezentarea" : "Pornește prezentarea";
}
function arataSetari(d){
  var c = $("randuri"); c.textContent = "";
  (d.setari || []).forEach(function(s){ c.appendChild(rowSetare(s, function(){ SETARI_SCHIMBATE = true; })); });
  SETARI_SCHIMBATE = false;
}
function arata(d){
  DATE = d;
  arataTv(d.tv || {});
  var a = document.activeElement;
  if(!SETARI_SCHIMBATE && !(a && (a.tagName === "SELECT" || a.tagName === "INPUT") && $("randuri").contains(a))){ arataSetari(d); }
}
function citeste(){
  if(document.hidden){ return Promise.resolve(); }
  return cerere("/api/poze").then(function(d){
    if(!d.result){ mesajIn("mesajTv", d.message || "Receptorul nu a putut citi starea.", true); return; }
    arata(d);
    if(!INCEPUT){ INCEPUT = true; NAV.deschide(d.dosar_start || ""); }
  }).catch(function(){ mesajIn("mesajTv", "Receptorul nu răspunde. Verifică dacă este pornit și în aceeași rețea.", true); });
}
function arataDosar(d){
  deseneazaDrum($("drum"), d, NAV);
  var ds = $("dosare"), g = $("grila"); ds.textContent = ""; g.textContent = "";
  POZE = d.fisiere || [];
  if(d.parinte !== null && !d.discuri){ ds.appendChild(buton("Un dosar mai sus", "", function(){ NAV.deschide(d.parinte); })); }
  (d.dosare || []).forEach(function(x){
    var text = x.nume + (x.total ? " (" + marime(x.liber) + " libere)" : "");
    ds.appendChild(buton(text, "hds-derulant hds-derulant-rand", function(){ NAV.deschide(x.cale); }));
  });
  $("dosarButoane").classList.toggle("ascuns", !POZE.length);
  POZE.forEach(function(f, i){
    var b = el("button", "miniatura hds-derulant-rand"); b.type = "button"; b.title = f.nume;
    var img = el("img"); img.loading = "lazy"; img.decoding = "async"; img.alt = f.nume; img.src = pozaUrl(f.cale);
    b.appendChild(img); b.appendChild(el("span", "hds-derulant", f.nume));
    b.addEventListener("click", function(){ deschideMare(i); });
    g.appendChild(b);
  });
  if(d.discuri && !(d.dosare || []).length){ mesajIn("mesajPoze", "Nu e niciun stick sau disc la receptor."); }
  else if(!d.discuri && !POZE.length && !(d.dosare || []).length){ mesajIn("mesajPoze", "Dosarul nu are poze."); }
}
function deschideMare(i){
  if(!POZE.length){ return; }
  MARE = (i + POZE.length) % POZE.length;
  var f = POZE[MARE];
  $("mareImg").src = pozaUrl(f.cale); $("mareImg").alt = f.nume;
  $("mareNume").textContent = f.nume + " (" + (MARE + 1) + " din " + POZE.length + ", " + marime(f.marime) + ")";
  $("mareDetalii").classList.add("ascuns"); $("mareDetalii").textContent = "";
  mesajIn("mesajMare", "");
  $("mare").classList.remove("ascuns");
  $("bInchideMare").focus();
}
function inchideMare(){ $("mare").classList.add("ascuns"); MARE = -1; }
function detalii(){
  if(MARE < 0){ return; }
  var c = $("mareDetalii");
  if(!c.classList.contains("ascuns")){ c.classList.add("ascuns"); return; }
  cerere("/api/poze-info?cale=" + encodeURIComponent(POZE[MARE].cale)).then(function(d){
    if(!d.result){ mesajIn("mesajMare", d.message, true); return; }
    c.textContent = "";
    var img = $("mareImg");
    var t = el("table"), tb = el("tbody");
    if(img.naturalWidth){ var r0 = el("tr"); r0.appendChild(el("th", "", "Mărimea în pixeli")); r0.appendChild(el("td", "", img.naturalWidth + " x " + img.naturalHeight)); tb.appendChild(r0); }
    (d.randuri || []).forEach(function(r){ var tr = el("tr"); tr.appendChild(el("th", "", r[0])); tr.appendChild(el("td", "", r[1])); tb.appendChild(tr); });
    t.appendChild(tb); c.appendChild(t); c.classList.remove("ascuns");
  }).catch(function(){ mesajIn("mesajMare", "Receptorul nu răspunde.", true); });
}
$("bStanga").addEventListener("click", function(){ deschideMare(MARE - 1); });
$("bDreapta").addEventListener("click", function(){ deschideMare(MARE + 1); });
$("bInchideMare").addEventListener("click", inchideMare);
$("bDetalii").addEventListener("click", detalii);
$("bArataTv").addEventListener("click", function(){ if(MARE >= 0){ tv("arata", POZE[MARE].cale, "mesajMare"); } });
$("bPrezentareAici").addEventListener("click", function(){ if(MARE >= 0){ tv("prezentare", POZE[MARE].cale, "mesajMare"); } });
$("bPrezentareDosar").addEventListener("click", function(){ if(POZE.length){ tv("prezentare", POZE[0].cale, "mesajPoze"); } });
$("bPrezentare").addEventListener("click", function(){ tv(DATE && DATE.tv && DATE.tv.prezentare ? "opreste" : "prezentare"); });
Array.prototype.forEach.call(document.querySelectorAll("#tvButoane button[data-fa]"), function(b){
  b.addEventListener("click", function(){ tv(b.getAttribute("data-fa")); });
});
document.addEventListener("keydown", function(e){
  if(MARE < 0){ return; }
  if(e.key === "ArrowLeft"){ deschideMare(MARE - 1); e.preventDefault(); }
  else if(e.key === "ArrowRight"){ deschideMare(MARE + 1); e.preventDefault(); }
  else if(e.key === "Escape"){ inchideMare(); e.preventDefault(); }
});
$("mare").addEventListener("touchstart", function(e){ if(e.touches.length === 1){ ATINS = e.touches[0].clientX; } }, {passive: true});
$("mare").addEventListener("touchend", function(e){
  if(ATINS === null || !e.changedTouches.length){ return; }
  var dx = e.changedTouches[0].clientX - ATINS; ATINS = null;
  if(Math.abs(dx) > 60){ deschideMare(MARE + (dx < 0 ? 1 : -1)); }
}, {passive: true});
$("bSalveaza").addEventListener("click", function(){
  var v = {};
  (DATE && DATE.setari || []).forEach(function(s){ var c = $("s_" + s.cheie); if(c){ v[s.cheie] = c.value; } });
  trimite("/api/poze-seteaza", v, "mesajSetari").then(function(d){ if(d && d.setari){ SETARI_SCHIMBATE = false; arata(d); arataSetari(d); } });
});
NAV = new Navigator("poze", "mesajPoze", arataDosar);
citeste();
setInterval(citeste, 4000);
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- traducerea paginilor
# Textele sabloanelor de mai sus, traduse la cerere in limba receptorului (traducere_pagini.py). Un text
# nou sau schimbat in sablon se scrie si aici (proba textelor paginilor web il cere).
TEXTE_PAGINA = {
	"html": (
		N_("Player media"),
		N_("Pe televizor"),
		N_("Playerul nu este deschis pe televizor. Alege mai jos un fișier și pornește-l, sau deschide "
			"playerul."),
		N_("Deschide playerul pe televizor"),
		N_("Anteriorul"),
		N_("Pune pauză"),
		N_("Următorul"),
		N_("Oprește"),
		N_("Ascunde playerul"),
		N_("Închide playerul"),
		N_("Un film pornit din lista de filme se comandă din pagina <a href=\"/filme\">Filmul de acum</a>, "
			"unde sunt și derularea și saltul la un loc anume."),
		N_("Fișierele de pe receptor"),
		N_("Din telefon sau calculator"),
		N_("Alege un fișier: se trimite pe receptor, apoi îl pornești pe televizor."),
		N_("Discul pe care se pune"),
		N_("Trimite pe receptor"),
		N_("Anulează"),
		N_("Pornește pe televizor"),
		N_("Lista de redare"),
		N_("Amestecă"),
		N_("Golește lista"),
		N_("Liste salvate"),
		N_("Încarcă lista"),
		N_("Șterge lista salvată"),
		N_("Salvează lista ca"),
		N_("Salvează lista"),
		N_("Setările playerului"),
		N_("Pe televizor, setările playerului apar numai cu nivelul de meniu Intermediar sau Expert."),
		N_("Salvează"),
		N_("Aceleași setări sunt pe televizor, în __DRUM_MENIU__ (în meniul playerului, tasta Menu), unde "
			"sunt și aceleași comenzi. Din pagină se văd numai stick-urile și discurile, nu memoria internă "
			"a receptorului."),
		N_("Fișierul de trimis"),
		N_("gol: data de azi"),
		N_("Poze"),
		N_("Pe televizor nu se arată nicio poză. Alege o poză mai jos și apasă Arată pe televizor."),
		N_("Poza de dinainte"),
		N_("Pornește prezentarea"),
		N_("Poza următoare"),
		N_("Închide pe televizor"),
		N_("Dosarele cu poze"),
		N_("Prezentare pe televizor din prima poză"),
		N_("Setările pozelor"),
		N_("Aceleași setări sunt pe televizor, în __DRUM_MENIU__ (tasta albastră). Miniaturile le face "
			"browserul din poze; din pagină se văd numai stick-urile și discurile, nu memoria internă a "
			"receptorului."),
		N_("Închide"),
		N_("Arată pe televizor"),
		N_("Prezentare pe televizor de aici"),
		N_("Detalii"),
		N_("Poza mare"),
	),
	"js": (
		N_("Se trimite..."),
		N_("Receptorul nu răspunde."),
		N_("Se citește dosarul..."),
		N_("Dosarul nu se poate citi."),
		N_("Dosarul are foarte multe fișiere: se arată numai o parte."),
		N_("Discuri"),
		N_("Între"),
		N_("și"),
		N_("Nu merge nimic acum."),
		N_("Redă"),
		N_("Pune pauză"),
		N_("Arată playerul"),
		N_("Ascunde playerul"),
		N_("Lista de redare ("),
		N_("Lista de redare este goală"),
		N_("Acum:"),
		N_("Pornește"),
		N_("Scoate din listă"),
		N_("Dosarul deschis mai sus"),
		N_("Deschide întâi un dosar în lista de fișiere."),
		N_("Nu e niciun stick sau disc pe care să se poată pune un fișier. Pune un stick în receptor."),
		N_("Alege un fișier: se trimite pe receptor, în dosarul hds-din-telefon al discului, apoi îl "
			"pornești pe televizor."),
		N_("Se trimite alt fișier:"),
		N_("din"),
		N_("Receptorul nu a putut citi playerul."),
		N_("Receptorul nu răspunde. Verifică dacă este pornit și în aceeași rețea."),
		N_("Pornește pe televizor"),
		N_("Încarcă în listă"),
		N_("Adaugă în listă"),
		N_("Șterge"),
		N_("Nu e niciun stick sau disc la receptor."),
		N_("libere din"),
		N_("Deschide"),
		N_("Un dosar mai sus"),
		N_("Pornește tot dosarul"),
		N_("Adaugă dosarul în listă"),
		N_("Dosarul nu are fișiere pe care playerul le poate reda."),
		N_("Trimis"),
		N_("Receptorul nu primește bucăți atât de mari."),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("Fișierul nu s-a putut trimite."),
		N_("Receptorul nu răspunde. Trimiterea s-a oprit."),
		N_("Fișierul are"),
		N_(", iar pe disc sunt liberi"),
		N_("Gata de trimis:"),
		N_("Se trimite"),
		N_("Pe televizor nu se arată nicio poză. Alege o poză mai jos și apasă Arată pe televizor."),
		N_("Pe televizor:"),
		N_(", poza"),
		N_(", prezentarea merge."),
		N_("Oprește prezentarea"),
		N_("Pornește prezentarea"),
		N_("Receptorul nu a putut citi starea."),
		N_("Dosarul nu are poze."),
		N_("Mărimea în pixeli"),
	),
}


def _traducePagina(sablon, fel="pagina"):
	"""Sablonul in limba receptorului; fara pachetul HdsWebControl (probele de pe PC), sablonul ca atare."""
	try:
		from .traducere_pagini import traduce
	except ImportError:
		return sablon
	return traduce(sablon, TEXTE_PAGINA, fel)
# ---------------------------------------------------------------- sfarsitul traducerii paginilor
