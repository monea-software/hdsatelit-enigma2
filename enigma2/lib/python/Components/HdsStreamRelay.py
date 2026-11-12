# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsStreamRelay.py: Stream Relay (0.7.0). DE LA 12.11.2026 NUMAI LA CERERE SI NUMAI PE TELEVIZOR: receptorul descifreaza
# singur toate canalele (cele CSA-ALT / ICAM cu SoftCSA, Components/HdsSoftCsa.py), pe televizor si in fluxul catre
# browser si playerele externe; trecerea singura e oprita din fabrica, iar browserul si serverul de flux nu mai trimit
# niciun canal la releu. Lista omului (mai jos) ramane si se respecta pe televizor (cele ICAM tot direct, cu SoftCSA gata).
#
# Canalele alese de om se redau prin releul de flux: un serviciu de pe
# receptor care cere canalul serverului de flux al imaginii (Hds/DabT2/server8001.py, 127.0.0.1:8001), il decodeaza si
# il da mai departe pe portul lui (17999 din fabrica). Televizorul reda atunci fluxul releului, ca un canal (sursa
# eHdsFluxHttp a serviciului DVB, lib/service/hdsfluxhttp.h), cu teletextul, subtitrarile si pistele lui.
#
# LISTA: FISIER (/etc/enigma2/whitelist_streamrelay, numele obisnuit, pe care il citesc si pluginurile si interfetele
# web scrise pentru alte imagini), un canal pe rand, referinta fara nume si fara cale (1:0:19:283D:3FB:1:C00000:0:0:0:).
# Intra numai canalele DVB (tipul 1, fara cale, fara dosar si fara marcaj). Fisierul se citeste la prima cerere si din
# nou cand se schimba (marime, mtime, inod), se scrie dintr-o miscare (temporar + fsync + rename). Un fisier care nu se
# poate citi (alta eroare decat lipsa lui) nu se scrie niciodata peste: lista ramane cea din memorie, numai citire.
# Se pune si se scoate din meniul listei de canale (Adaugă la Stream Relay / Scoate din Stream Relay,
# Screens/ChannelSelection.py) si din lista de canale din web (canale_web.py, butonul de langa stea).
#
# SETARILE (config.misc.acces_streamrelay_*, Components/UsageConfig.py; Meniu > Acces condiționat > Stream Relay, in web
# /setari?id=hds_stream_relay): adresa releului (din ea se ia numai gazda), portul (17999) si intarzierea la trecerea de
# la un canal prin releu la altul (ms). Serverul de flux al imaginii asculta numai pe 127.0.0.1, deci releul trebuie sa
# ruleze pe receptor: o adresa din afara (alt aparat din retea) nu se foloseste, canalul porneste direct (un rand in
# jurnal). Exceptia (0.7.0): cu setarea "Fluxuri pentru alte aparate din rețeaua de acasă"
# (config.misc.hds_fluxuri_retea_acasa) pornita, serverul de flux primeste si adresele private, deci si un releu de pe
# alt aparat din reteaua de acasa (adresa privata, releuInRetea) se foloseste.
#
# IN BROWSER (TV in browser, "Vezi live", playerele externe VLC / Kodi): de la 12.11.2026 fluxul vine mereu de la tuner,
# descifrat de receptor (Components/HdsTransmisie.adresaReleu da None); pana atunci canalele din lista veneau de la releu.
#
# ZAP (cost zero fara lista si fara trecerea singura): legatura la Navigation.playServiceExtensions se pune numai cat lista
# are canale sau trecerea singura (mai jos) e pornita (la pornire: mytest.py, numai daca fisierul exista sau setarea e
# pornita; la schimbarea setarii: notificatorul din Components/UsageConfig.py). Pentru un canal din lista:
#  - daca nimic nu asculta la adresa releului (releul oprit), canalul porneste direct, ca fara Stream Relay, iar pe
#    televizor apare de ce (motivReleu, mai jos);
#  - altfel playerul primeste referinta releului (aceeasi, cu spatiul de nume + 1, ca serverul de flux, la care releul
#    cere canalul adevarat, sa nu ia redarea drept acelasi serviciu; calea http://<gazda>:<port>/<referinta>), iar
#    referinta din navigatie ramane cea a canalului: bara, ghidul, sigla si lista de canale vad canalul obisnuit;
#  - de la un canal prin releu la altul, playerul porneste dupa intarzierea din setari (releul elibereaza canalul vechi).
# Serverul de flux (Hds/DabT2/server8001.py) da oricui, si releului, fluxul inscris la modulul de acces ca orice flux,
# descifrat de receptor unde poate (12.11.2026; pana atunci un releu din retea primea fluxul criptat, cu PID-urile ECM).
#
# TRECEREA SINGURA (0.7.4, cererea de pe forum, subiectul 1025: canalele Sky Deutschland cu ICAM, CAID 098C / 098D,
# se decodeaza numai prin releu, iar omul le punea in lista unul cate unul). Setarea config.misc.hds_streamrelay_icam
# (Nu din fabrica de la 12.11.2026; Meniu > Acces condiționat > Stream Relay, in web /setari?id=hds_stream_relay) si sistemele ei,
# config.misc.hds_streamrelay_icam_caid ("098C,098D"; gol sau gresit = cele din fabrica). Un canal din afara listei
# trece singur prin releu cand:
#  - lamedb ii stie CAID-urile (C:xxxx, din scanare) si toate sunt din familia sistemelor alese (octetul de sus, 0x09 =
#    Videoguard): prin releu de la primul zap. lamedb se citeste o data, intr-o multime din memorie, si din nou cand se
#    schimba (verificat cel mult o data la VERIFICARE_AUTOMAT_S); la zap, o cautare in multime;
#  - altfel la redare: canalul porneste direct, iar cand PMT-ul arata (sCAIDs, la evUpdatedInfo, cel mult
#    FEREASTRA_ZAP_S dupa zap) un CAID ales si toate CAID-urile din familia aleasa, canalul se tine minte si porneste
#    din nou prin releu (din ceas, cu releul care asculta). Un raspuns "nu" nu incheie ascultarea: cu PID-urile tinute
#    minte, primul evUpdatedInfo vine inaintea PMT-ului, cu CAID-urile numai din lamedb. (Listele din fabrica si cele
#    din pachete nu au CAID-uri la canalele Sky; de aceea invatarea la redare e drumul de baza.)
#  - canalele cu alte sisteme alaturi (simulcrypt: HD+, ORF, Viaccess) nu trec singure: se pot vedea si direct (cartela
#    lor, CI), iar un canal care se vede direct nu se muta. Trecerea lor dupa ASTEAPTA_IMAGINE_MS fara imagine e scrisa
#    si probata pe PC, dar OPRITA (SIMULCRYPT_FARA_IMAGINE) pana la proba semnalului de imagine pe un Vu+ 4K.
# Canalele tinute minte si cele scoase de om stau in FISIER_AUTOMAT ("+cheie" / "-cheie", cheia scurta
# SID:TSID:ONID:NS, fara tipul serviciului); whitelist_streamrelay ramane numai lista omului (o citesc si pluginurile
# altora). Releul care nu raspunde: canalul automat porneste direct FARA mesaj (098C / 098D sunt si pe canale cu
# simulcrypt, la care omul fara releu nu trebuie deranjat). Meniul listei si butonul SR din web: aceleasi doua texte;
# "Scoate din Stream Relay" pe un canal automat il pune la exceptii, "Adaugă la Stream Relay" il scoate de acolo.
# Setarea oprita: totul ca inainte de 0.7.4 (lista singura; fisierul automat si lamedb nu se citesc).
#
# SOFTCSA (0.7.4, Components/HdsSoftCsa.py): cand nucleul poate descifra singur CSA-ALT (libdvbcsa si modulul de acces
# legat cu protocolul 3, „pmt_mode = 6” si „extended_cw_api = 1”), canalele CSA-ALT pornesc direct, nu prin releu: cele
# trecute singur (ICAM) si cele din lista care sunt ICAM (tinute minte, din lamedb cu sistemele alese, sau vazute CSA-ALT
# de nucleu de la pornire). Un modul care raspunde cu protocolul 3 nu da neaparat cuvintele CSA-ALT, deci releul se lasa
# deoparte de-a binelea numai dupa ce au venit cuvinte prin soclu (pe canal, sau de la modul pe legatura de acum). Pana
# atunci canalul porneste direct o data pe legatura, ca incercare: fara niciun cuvant in INCERCARE_SOFTCSA_S (si cu
# ECM-ul care nu spune „nu e CSA-ALT”), canalul porneste din nou prin releu, iar urmatoarele zapuri merg prin releu pana
# se leaga din nou modulul. Invatarea la redare nu mai muta canalul pe releu cand modulul a dat cuvinte. Un rand in jurnal
# la fiecare hotarare. Fara SoftCSA gata (modul vechi, modul fara protocolul 3), releul merge ca inainte.
#
# Pentru pluginurile scrise pentru alte imagini, Screens/InfoBarGenerics.streamrelay da acelasi obiect (releu()):
# checkService(ref) (din lista sau trecut singur), streamrelayChecker(ref) -> (ref, prin_releu), reload(),
# toggle(nav, ref), data (numai lista omului).
#
# DE CE NU RASPUNDE RELEUL (motivReleu, 0.7.1): pe receptor releul il da modulul de acces; cand nu raspunde, textul spune
# cauza vazuta de om, dupa modulele citite ca in ecranul „Module de acces condiționat” (Components/HdsModuleAcces.py,
# toate felurile, fara niciun nume de modul in cod): niciun modul ales; modulul ales nu ruleaza; modulul ruleaza, dar nu
# da releul pe port; altfel (releu pe alt aparat, citire cazuta) adresa si portul. La zap, un canal din lista cu releul
# care nu raspunde porneste direct, ca inainte, iar pe televizor apare o data motivul (mesaj scurt, care se inchide
# singur; acelasi motiv iar numai dupa REPETARE_MESAJ_S). STAREA (stare(), liniiStare()): cate canale are lista, de
# unde se adauga, daca releul raspunde si de ce nu; o arata ecranul setarilor Stream Relay (atributul hdsStare al
# setarilor, Screens/Setup.py), aceeasi pagina in web (setari_web.py) si pagina Acces condiționat din web
# (acces_conditionat_web.py).
#
# Partea de sus a fisierului nu importa nimic din enigma2 (probele de pe PC); legaturile cu enigma2 au importuri tarzii.

import errno
import os
import re
import socket
import threading
import time

FISIER = "/etc/enigma2/whitelist_streamrelay"
# trecerea singura (0.7.4): canalele tinute minte ("+cheie") si cele scoase de om ("-cheie"); lista de canale
FISIER_AUTOMAT = "/etc/enigma2/hds_streamrelay_automat"
LAMEDB = "/etc/enigma2/lamedb"
CAID_FABRICA = "098C,098D"          # Sky Deutschland (Videoguard V14 / V15), ICAM
VERIFICARE_AUTOMAT_S = 30.0         # cat de des se verifica la zap daca lamedb sau fisierul automat s-au schimbat
ASTEAPTA_IMAGINE_MS = 6000          # simulcrypt: cat se asteapta imaginea directa inainte de releu
# Simulcrypt (un CAID ales si alte sisteme alaturi: HD+, ORF, Viaccess) trecut singur dupa ASTEAPTA_IMAGINE_MS fara
# imagine. OPRIT: semnalul imaginii pe receptoarele fara contorul de cadre (evVideoSizeChanged, sVideoHeight) e socotit
# nesigur pe unele drivere (Components/HdsEcranNegru.py), iar un canal care se vede direct nu trebuie mutat. Se
# porneste (True) numai dupa proba pe un Vu+ 4K; atunci descrierea setarii din data/setup.xml se schimba si ea.
SIMULCRYPT_FARA_IMAGINE = False
FEREASTRA_ZAP_S = 20.0              # cat dupa zap se mai asculta PMT-ul canalului pornit direct
INCERCARE_SOFTCSA_S = 10            # SoftCSA gata, modulul fara niciun cuvant inca: cat se incearca un canal direct
MAX_LAMEDB_OCTETI = 32 * 1024 * 1024
_CHEIE_SCURTA = re.compile(r"^[0-9A-F]{1,8}:[0-9A-F]{1,8}:[0-9A-F]{1,8}:[0-9A-F]{1,8}$")
PORT_IMPLICIT = 17999
GAZDE_LOCALE = ("127.0.0.1", "localhost")
TERMEN_VERIFICARE_S = 0.3        # cat asteapta verificarea ca releul asculta (pe 127.0.0.1 raspunsul e pe loc)
MAX_CANALE = 2000
MAX_OCTETI = 256 * 1024
# steagurile referintei care nu sunt canale: dosar, coborare, marcaj (eServiceReference)
_FARA_CANAL = 1 | 2 | 64
# mesajul de pe televizor cand releul nu raspunde la zap: cat sta (s) si dupa cat se arata iar acelasi motiv (s)
TIMP_MESAJ_S = 8
REPETARE_MESAJ_S = 600


def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele se traduc la folosire."""
	return text


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi pe PC."""
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


def ngettext(unu, multe, n):
	"""Pluralul tradus (Components/HdsPlural.ngettext: o Forma, al carei % merge si cand forma pentru 1 n-are numarul,
	in romana „un canal”, „2 canale”); pe PC, forma romaneasca fara traducere."""
	try:
		from Components.HdsPlural import ngettext as plural
		return plural(unu, multe, n)
	except Exception:
		return unu if n == 1 else multe


# acelasi text ca HdsTransmisie.TEXT_RELEU_OPRIT (TV in browser): adresa si portul
TEXT_RELEU_OPRIT = N_("Stream Relay nu răspunde la %s:%d. Verifică adresa și portul din setările Stream Relay.")
TEXT_RELEU_FARA_MODUL = N_("Modulul de acces %s nu rulează, de aceea Stream Relay nu răspunde. Pornește-l din Meniu > Acces condiționat sau din pagina Module de acces condiționat.")
TEXT_RELEU_NICIUN_MODUL = N_("Niciun modul de acces nu e pornit, de aceea Stream Relay nu răspunde. Alege unul în Meniu > Acces condiționat.")
TEXT_RELEU_MODUL_FARA_RELEU = N_("Modulul de acces %s rulează, dar nu dă Stream Relay pe portul %d. Pornește Stream Relay în setările modulului sau pune portul lui în setările Stream Relay.")
TEXT_PORNESTE_DIRECT = N_("Canalul pornește fără Stream Relay.")
TEXT_RELEU_MERGE = N_("Stream Relay răspunde la %s:%d.")
TEXT_LISTA = N_("Lista Stream Relay: %s.")
TEXT_LISTA_GOALA = N_("Lista Stream Relay e goală, deci niciun canal nu trece prin releu.")
TEXT_DE_UNDE = N_("Canalele se adaugă din lista de canale (MENU pe canal > Adaugă la Stream Relay) sau din pagina Canale a interfeței web (butonul SR).")
TEXT_NUMAI_CITIRE = N_("Lista Stream Relay nu se poate citi; rămâne cea de dinainte.")
# trecerea singura (0.7.4): %s = sistemele ("098C, 098D"), apoi numarul canalelor (ngettext "%d canal" / "%d canale")
TEXT_AUTOMAT = N_("Canalele cu ICAM (%s) trec singure prin releu.")
TEXT_AUTOMAT_CANALE = N_("Trec singure prin releu: %s.")


def _jurnal(text):
	print("[HdsStreamRelay] %s" % text)


# ------------------------------------------------------------------ referintele (fara enigma2)

def cheie(ref):
	"""Cheia de lista a unui canal DVB: "1:<steaguri>:<8 campuri hex>:" (hex cu litere mari, fara zerouri in fata),
	sau None pentru ce nu poate intra in Stream Relay (alt tip, cale, dosar, marcaj, referinta stricata). `ref` e o
	eServiceReference sau textul ei."""
	if ref is None:
		return None
	text = ref if isinstance(ref, str) else ref.toString()
	parti = text.split(":")
	if len(parti) < 10:
		return None
	try:
		tip = int(parti[0])
		steaguri = int(parti[1])
		date = [int(x or "0", 16) for x in parti[2:10]]
	except ValueError:
		return None
	if tip != 1 or steaguri & _FARA_CANAL:
		return None
	if len(parti) > 10 and parti[10].strip():
		return None
	if not date[1]:  # fara numarul serviciului (SID) nu e un canal
		return None
	return "1:%d:%s:" % (steaguri, ":".join("%X" % x for x in date))


def gazdaDinAdresa(adresa):
	"""Gazda din adresa scrisa in setari ("http://127.0.0.1:17999", "127.0.0.1", "localhost:17999"); "" daca nu e."""
	a = (adresa or "").strip()
	if "://" in a:
		a = a.split("://", 1)[1]
	a = a.split("/", 1)[0]
	if a.startswith("["):
		return ""
	return a.rsplit(":", 1)[0] if ":" in a else a


def releuInRetea(gazda):
	"""Un releu de pe alt aparat din reteaua de acasa (adresa IPv4 privata), numai cu setarea "Fluxuri pentru alte aparate
	din rețeaua de acasă" pornita (Hds/DabT2/server8001.py: atunci serverul de flux il primeste)."""
	try:
		from Hds.DabT2 import server8001
		return server8001.retea_pornita() and server8001.adresa_privata(gazda)
	except Exception:
		return False


def releuPermis(gazda):
	"""Gazda releului se poate folosi: pe receptor (127.0.0.1, localhost) sau in reteaua de acasa permisa."""
	return gazda in GAZDE_LOCALE or releuInRetea(gazda)


def textReleu(cheie_canal, gazda, port, nume=""):
	"""Textul referintei redate prin releu pentru un canal din lista: spatiul de nume + 1 (camp 7), calea
	http://gazda:port/<cheie> (cu ':' scrise %3a, ca in orice referinta), apoi numele."""
	parti = cheie_canal.split(":")
	parti[6] = "%X" % ((int(parti[6], 16) + 1) & 0xFFFFFFFF)
	cale = "http://%s:%d/%s" % (gazda, port, cheie_canal)
	nume = (nume or "").replace(":", " ").replace("\n", " ")
	return "%s%s:%s" % (":".join(parti[:10]) + ":", cale.replace(":", "%3a"), nume)


# ------------------------------------------------------------------ trecerea singura (0.7.4, fara enigma2)

_CAID_MEMORIE = {}


def _caidBucati(text):
	caids = set()
	for bucata in re.split(r"[\s,;]+", (text or "").strip()):
		b = bucata.lower()
		if b.startswith("0x"):
			b = b[2:]
		if not 1 <= len(b) <= 4:
			continue
		try:
			v = int(b, 16)
		except ValueError:
			continue
		if v:
			caids.add(v)
	return caids


def caidDinText(text):
	"""Multimea CAID-urilor din textul setarii ("098C,098D", "98c 98d", "0x098C;0x098D"). Un text gol sau fara niciun cod
	bun da multimea din fabrica: o greseala de scriere nu opreste trecerea singura (pentru asta e setarea Da / Nu)."""
	text = text if isinstance(text, str) else ""
	m = _CAID_MEMORIE.get(text)
	if m is None:
		m = frozenset(_caidBucati(text) or _caidBucati(CAID_FABRICA))
		if len(_CAID_MEMORIE) > 16:
			_CAID_MEMORIE.clear()
		_CAID_MEMORIE[text] = m
	return m


def textCaid(caids):
	"""Sistemele pentru om: "098C, 098D"."""
	return ", ".join("%04X" % c for c in sorted(caids))


def cheieScurta(ref):
	"""Cheia trecerii singure, "SID:TSID:ONID:NS" (hex cu litere mari, fara zerouri in fata), din referinta sau din
	cheia de lista; None pentru ce nu poate intra in Stream Relay. Fara tipul serviciului si fara steaguri: canalul din
	lamedb, din alt buchet sau cu alt tip in referinta are aceeasi cheie."""
	k = cheie(ref)
	if not k:
		return None
	p = k.split(":")
	return "%s:%s:%s:%s" % (p[3], p[4], p[5], p[6])


def potrivireCaid(caids, alese):
	"""0: niciun CAID din `alese`; 1: are unul si toate CAID-urile canalului sunt din familiile lor (octetul de sus:
	098C, 098D, 09F0 = 0x09, Videoguard), deci canalul nu se vede altfel; 2: are unul, dar si sisteme din alta familie
	(simulcrypt: HD+ 18xx, ORF 06xx / 0Dxx, Viaccess 0500), deci se poate vedea si direct."""
	cs = set(int(c) & 0xFFFF for c in caids if c)
	if not cs or not (cs & alese):
		return 0
	familii = set(c >> 8 for c in alese)
	return 1 if all((c >> 8) in familii for c in cs) else 2


def citesteLamedb(cale, alese, maxim=MAX_LAMEDB_OCTETI):
	"""Cheile scurte ale canalelor din lamedb (formatul 3 / 4 scris de eDVBDB::saveServicelist) ale caror CAID-uri scrise
	("C:xxxx", din scanare) se potrivesc singure (potrivireCaid == 1). Numai citire; un fisier lipsa, prea mare sau
	stricat da multimea goala. Listele fara CAID-uri (cele din fabrica, cele din pachete) dau multimea goala: canalele
	lor se invata la redare."""
	try:
		if os.path.getsize(cale) > maxim:
			_jurnal("lamedb e prea mare, nu se citeste pentru trecerea singura")
			return frozenset()
		with open(cale, "r", encoding="utf-8", errors="replace") as f:
			text = f.read()
	except (IOError, OSError):
		return frozenset()
	if "\r" in text:
		text = text.replace("\r", "")
	i = text.find("\nservices\n")
	if i < 0:
		return frozenset()
	randuri = text[i + 10:].split("\n")
	rez = set()
	j, n = 0, len(randuri)
	while j + 2 < n:
		r, date = randuri[j], randuri[j + 2]
		if r.startswith("end"):
			break
		j += 3
		if "C:" not in date:
			continue
		caids = []
		for b in date.split(","):
			if b.startswith("C:"):
				try:
					caids.append(int(b[2:6], 16))
				except ValueError:
					pass
		if potrivireCaid(caids, alese) != 1:
			continue
		p = r.split(":")
		if len(p) < 4:
			continue
		try:
			sid, ns, tsid, onid = [int(x, 16) for x in p[:4]]
		except ValueError:
			continue
		if sid:
			rez.add("%X:%X:%X:%X" % (sid, tsid, onid, ns))
	return frozenset(rez)


# ------------------------------------------------------------------ de ce nu raspunde releul (0.7.1)

def _moduleAcces(H=None):
	"""Modulele de acces de pe receptor, ca in ecranul „Module de acces condiționat” (toate felurile):
	{"ruleaza": [sufixele celor care ruleaza], "alese": [sufixele celor alese care nu ruleaza]}, sau None cand nu se
	pot citi sau receptorul n-are niciun fel de module (nu se stie nimic despre ele). `H` e Components.HdsModuleAcces
	(probele dau unul fals)."""
	try:
		if H is None:
			from Components import HdsModuleAcces as H
		ruleaza, alese = [], []
		stari = H.feluri_de_aratat(H.SistemAcces())
		if not stari:
			return None
		for st in stari:
			for e in st.emulatoare:
				if e.pids:
					ruleaza.append(e.sufix)
				elif e.ales:
					alese.append(e.sufix)
		return {"ruleaza": ruleaza, "alese": alese}
	except Exception as e:
		_jurnal("modulele de acces nu se pot citi: %r" % (e,))
		return None


def motivReleu(gazda, port, H=None):
	"""Textul pentru releul care nu raspunde, cu cauza vazuta de om. Pe receptor (127.0.0.1) releul il da modulul de
	acces: niciun modul ales, modulul ales oprit, modulul care ruleaza fara releu pe port; altfel (alt aparat, citire
	cazuta) adresa si portul."""
	if gazda in ("127.0.0.1", "localhost", "::1"):
		m = _moduleAcces(H)
		if m is not None:
			if m["ruleaza"]:
				return _t(TEXT_RELEU_MODUL_FARA_RELEU) % (m["ruleaza"][0], port)
			if m["alese"]:
				return _t(TEXT_RELEU_FARA_MODUL) % m["alese"][0]
			return _t(TEXT_RELEU_NICIUN_MODUL)
	return _t(TEXT_RELEU_OPRIT) % (gazda, port)


def stare(r=None, H=None):
	"""Starea Stream Relay pentru ecranul setarilor si web: {"canale": numarul canalelor din lista, "numai_citire",
	"automat" (trecerea singura pornita), "automate" (cate canale trec singure acum: tinute minte sau stiute din lamedb,
	fara cele scoase de om), "gazda", "port", "permis" (adresa se foloseste), "asculta" (releul raspunde; None cand nu
	e niciun canal de trecut: nu se verifica), "motiv" (de ce nu raspunde, "" altfel), "linii": randurile pentru om}."""
	r = r or releu()
	H = H or getattr(r, "_module", None)
	chei = r.chei()
	pornit, alese = r.automat()
	automate = r.numarAutomate() if pornit else 0
	gazda, port, _intarziere = r.configurare()
	gazda = "127.0.0.1" if gazda == "localhost" else gazda
	rez = {"canale": len(chei), "numai_citire": r.numaiCitire, "automat": pornit, "automate": automate, "gazda": gazda,
		"port": port, "permis": gazda in GAZDE_LOCALE or releuInRetea(gazda), "asculta": None, "motiv": ""}
	linii = []
	if r.numaiCitire:
		linii.append(_t(TEXT_NUMAI_CITIRE))
	if chei:
		linii.append(_t(TEXT_LISTA) % (ngettext("%d canal", "%d canale", len(chei)) % len(chei)))
	if pornit:
		linii.append(_t(TEXT_AUTOMAT) % textCaid(alese))
		if automate:
			linii.append(_t(TEXT_AUTOMAT_CANALE) % (ngettext("%d canal", "%d canale", automate) % automate))
	if chei or automate:
		rez["asculta"] = r.asculta(gazda, port)
		if rez["asculta"]:
			linii.append(_t(TEXT_RELEU_MERGE) % (gazda, port))
		else:
			rez["motiv"] = motivReleu(gazda, port, H)
			linii.append(rez["motiv"])
	elif not pornit:
		linii.append(_t(TEXT_LISTA_GOALA))
	linii.append(_t(TEXT_DE_UNDE))
	rez["linii"] = linii
	return rez


# ultima stare ceruta de ecranul setarilor: (ora, randurile); ecranul o cere la fiecare rand ales si la 3 s, iar un releu
# pe alt aparat care nu raspunde ar tine firul enigma2 TERMEN_VERIFICARE_S la fiecare cerere
_STARE_RECENTA = [None, []]
STARE_RECENTA_S = 2.5


def liniiStare(ceas=time.time):
	"""Randurile starii pentru ecranul setarilor Stream Relay (atributul hdsStare al setarilor, Screens/Setup.py) si
	pagina lui web; aceleasi randuri cel mult STARE_RECENTA_S."""
	acum = ceas()
	cand, linii = _STARE_RECENTA
	if cand is not None and 0 <= acum - cand < STARE_RECENTA_S:
		return list(linii)
	try:
		linii = stare()["linii"]
	except Exception as e:
		_jurnal("starea: %r" % (e,))
		linii = []
	_STARE_RECENTA[0], _STARE_RECENTA[1] = acum, list(linii)
	return linii


def _anuntaPeTelevizor(text):
	try:
		from Tools import Notifications
		from Screens.MessageBox import MessageBox
		Notifications.AddPopup(text, MessageBox.TYPE_INFO, TIMP_MESAJ_S, "HdsStreamRelay")
	except Exception as e:
		_jurnal("mesajul de pe televizor: %r" % (e,))


# ------------------------------------------------------------------ lista

class Releu(object):
	"""Lista canalelor, trecerea singura si legatura la zap. Un singur obiect pe proces (releu())."""

	def __init__(self, fisier=FISIER, extensii=None, configurare=None, anunta=None, module=None, ceas=None,
			automat=None, fisier_automat=FISIER_AUTOMAT, lamedb=LAMEDB, monoton=None, softcsa=None):
		# trecerea singura (0.7.4): `automat` = (pornita, multimea CAID) pentru probe, altfel din config
		self._automatConf = automat
		# SoftCSA (0.7.4): (stare(), canalCsaAlt(ref)) pentru probe, altfel Components.HdsSoftCsa
		self._softcsa = softcsa
		self._incercareSoft = None      # (nav, cheie, legatura): canal pornit direct pe incercare
		self._softFaraCuvinte = None    # legatura modulului pe care incercarea n-a adus cuvinte
		self._ceasSoft = None
		self.fisierAutomat = fisier_automat
		self.lamedb = lamedb
		self._monoton = monoton or time.monotonic
		self._invatate = set()          # cheile scurte tinute minte la redare
		self._exceptii = set()          # cheile scurte scoase de om din trecerea singura
		self._amprentaAutomat = None
		self._cititAutomat = False
		self.automatNumaiCitire = False
		self._dinLamedb = frozenset()   # cheile scurte potrivite singure din lamedb
		self._lamedbPentru = None       # (amprenta lamedb, multimea CAID) pentru care e facuta _dinLamedb
		self._verificatAutomat = None   # ora (monoton) ultimei verificari a celor doua fisiere
		self._urmarit = None            # [nav, cheie, cheie scurta, ora zap-ului, fel]: canal pornit direct, ascultat
		self._areImagine = False        # a venit imagine de la zap-ul urmarit (evVideoSizeChanged si celelalte)
		self._ceasIcam = None
		self._navEv = None              # lista nav.event in care sta ascultatorul
		self.fisier = fisier
		self._extensii = extensii      # lista Navigation.playServiceExtensions (probele dau una a lor)
		self._configurare = configurare  # (gazda, port, intarziere_ms) pentru probe; altfel din config
		self._anunta = anunta or _anuntaPeTelevizor   # mesajul de pe televizor (probele dau o functie a lor)
		self._module = module          # Components.HdsModuleAcces (probele dau unul fals)
		self._ceasMesaj = ceas or time.time
		self._ultimulMesaj = (None, 0.0)  # (textul, ora) ultimului mesaj despre releul care nu raspunde
		self._chei = []
		self._amprenta = None
		self._citit = False
		self.numaiCitire = False
		self._lacat = threading.Lock()
		self._prinReleu = False         # serviciul pornit de ultimul zap a mers prin releu
		self._refReleu = None           # ... si cheia canalului lui (sesiunea 8001 a releului e pe transponderul lui)
		self._ceas = None
		self._asteapta = None           # (nav, playref, text releu) pentru pornirea dupa intarziere
		self._eliberare = None          # (nav, playref, cheia releului vechi, ora limita): pornire directa amanata
		self._ceasEliberare = None

	# ---- fisierul
	def _amprentaFisier(self):
		try:
			s = os.stat(self.fisier)
		except OSError as e:
			if e.errno in (errno.ENOENT, errno.ENOTDIR):
				return "lipseste"
			return None
		return (s.st_size, s.st_mtime_ns, s.st_ino)

	def _citeste(self, fortat=False):
		amprenta = self._amprentaFisier()
		if self._citit and not fortat and amprenta == self._amprenta:
			return
		if amprenta == "lipseste":
			self._chei, self._amprenta, self._citit, self.numaiCitire = [], amprenta, True, False
			return
		try:
			if amprenta is None or amprenta[0] > MAX_OCTETI:
				raise IOError("fisierul nu se poate citi sau e prea mare")
			with open(self.fisier, "r", encoding="utf-8", errors="replace") as f:
				randuri = f.read().splitlines()
		except (IOError, OSError) as e:
			# numai citire: nu se scrie peste un fisier necitit (lista din memorie ramane)
			_jurnal("lista nu se poate citi (%s): ramane cea de dinainte, fara scriere" % e)
			self.numaiCitire, self._citit = True, True
			self._amprenta = amprenta
			return
		chei = []
		vazute = set()
		for r in randuri:
			k = cheie(r.strip())
			if k and k not in vazute and len(chei) < MAX_CANALE:
				vazute.add(k)
				chei.append(k)
		self._chei, self._amprenta, self._citit, self.numaiCitire = chei, amprenta, True, False

	def _scrie(self, chei):
		if self.numaiCitire:
			return False
		nou = self.fisier + ".nou"
		try:
			if not chei:
				try:
					os.remove(self.fisier)
				except OSError as e:
					if e.errno != errno.ENOENT:
						raise
			else:
				with open(nou, "w", encoding="utf-8") as f:
					f.write("".join(k + "\n" for k in chei))
					f.flush()
					os.fsync(f.fileno())
				os.replace(nou, self.fisier)
		except (IOError, OSError) as e:
			_jurnal("lista nu s-a scris: %s" % e)
			try:
				os.remove(nou)
			except OSError:
				pass
			return False
		self._chei = list(chei)
		self._amprenta = self._amprentaFisier()
		return True

	# ---- citirea listei
	def chei(self):
		with self._lacat:
			self._citeste()
			return list(self._chei)

	@property
	def data(self):
		return self.chei()

	def getData(self):
		return self.chei()

	def checkService(self, ref):
		"""True daca canalul trece prin releu: din lista omului sau singur (trecerea singura, 0.7.4)."""
		k = cheie(ref)
		return bool(k) and self.fel(k) is not None

	def fel(self, k):
		"""Cum trece prin releu canalul cu cheia de lista `k`: "lista", "automat" sau None."""
		with self._lacat:
			self._citeste()
			if k in self._chei:
				return "lista"
			pornit, alese = self.automat()
			if pornit and self._automatFaraLacat(k, alese):
				return "automat"
		return None

	def reload(self):
		with self._lacat:
			self._citeste(fortat=True)
			self._verificatAutomat = None
			gol = not self._chei
		self.actualizeazaLegatura(gol)

	# ---- trecerea singura (0.7.4)
	def automat(self):
		"""(pornita, multimea CAID) din setari; (False, multime goala) fara ele (probele de pe PC, pornirea)."""
		if self._automatConf is not None:
			return self._automatConf
		try:
			from Components.config import config
			m = config.misc
			return bool(m.hds_streamrelay_icam.value), caidDinText(m.hds_streamrelay_icam_caid.value)
		except Exception:
			return False, frozenset()

	def _amprentaDe(self, cale):
		try:
			s = os.stat(cale)
		except OSError as e:
			return "lipseste" if e.errno in (errno.ENOENT, errno.ENOTDIR) else None
		return (s.st_size, s.st_mtime_ns, s.st_ino)

	def _improspateazaAutomat(self, alese, fortat=False):
		"""Fisierul automat si lamedb citite din nou numai cand s-au schimbat, verificate cel mult o data la
		VERIFICARE_AUTOMAT_S (si pe loc cand s-au schimbat sistemele alese). Sub lacat."""
		acum = self._monoton()
		if self._lamedbPentru is None or self._lamedbPentru[1] != alese:
			fortat = True
		if not fortat and self._verificatAutomat is not None and 0 <= acum - self._verificatAutomat < VERIFICARE_AUTOMAT_S:
			return
		self._verificatAutomat = acum
		self._citesteAutomat()
		amprenta = self._amprentaDe(self.lamedb)
		if self._lamedbPentru != (amprenta, alese):
			t = time.time()
			self._dinLamedb = citesteLamedb(self.lamedb, alese) if amprenta not in ("lipseste", None) else frozenset()
			self._lamedbPentru = (amprenta, alese)
			_jurnal("lamedb: %d canale cu %s trec singure (%.0f ms)" % (len(self._dinLamedb), textCaid(alese),
				(time.time() - t) * 1000))

	def _citesteAutomat(self):
		amprenta = self._amprentaDe(self.fisierAutomat)
		if self._cititAutomat and amprenta == self._amprentaAutomat:
			return
		if amprenta == "lipseste":
			self._invatate, self._exceptii, self._amprentaAutomat = set(), set(), amprenta
			self._cititAutomat, self.automatNumaiCitire = True, False
			return
		try:
			if amprenta is None or amprenta[0] > MAX_OCTETI:
				raise IOError("fisierul nu se poate citi sau e prea mare")
			with open(self.fisierAutomat, "r", encoding="utf-8", errors="replace") as f:
				randuri = f.read().splitlines()
		except (IOError, OSError) as e:
			# ca la lista: un fisier necitit nu se scrie niciodata peste
			_jurnal("canalele trecute singur nu se pot citi (%s): raman cele de dinainte, fara scriere" % e)
			self._cititAutomat, self.automatNumaiCitire, self._amprentaAutomat = True, True, amprenta
			return
		invatate, exceptii = set(), set()
		for r in randuri:
			r = r.strip().upper()
			if len(r) > 1 and r[0] in "+-" and _CHEIE_SCURTA.match(r[1:]):
				tinta = invatate if r[0] == "+" else exceptii
				if len(tinta) < MAX_CANALE:
					tinta.add(r[1:])
		self._invatate, self._exceptii, self._amprentaAutomat = invatate, exceptii, amprenta
		self._cititAutomat, self.automatNumaiCitire = True, False

	def _scrieAutomat(self, invatate, exceptii):
		"""Fisierul automat dintr-o miscare (temporar + fsync + rename); gol = sters. Sub lacat."""
		if self.automatNumaiCitire:
			return False
		nou = self.fisierAutomat + ".nou"
		try:
			if not invatate and not exceptii:
				try:
					os.remove(self.fisierAutomat)
				except OSError as e:
					if e.errno != errno.ENOENT:
						raise
			else:
				with open(nou, "w", encoding="utf-8") as f:
					f.write("# Stream Relay, trecerea singura: + canal tinut minte, - canal scos de om (SID:TSID:ONID:NS)\n")
					f.write("".join("+%s\n" % k for k in sorted(invatate)))
					f.write("".join("-%s\n" % k for k in sorted(exceptii)))
					f.flush()
					os.fsync(f.fileno())
				os.replace(nou, self.fisierAutomat)
		except (IOError, OSError) as e:
			_jurnal("canalele trecute singur nu s-au scris: %s" % e)
			try:
				os.remove(nou)
			except OSError:
				pass
			return False
		self._invatate, self._exceptii = set(invatate), set(exceptii)
		self._amprentaAutomat = self._amprentaDe(self.fisierAutomat)
		return True

	def _automatFaraLacat(self, k, alese):
		"""Canalul (cheia de lista) trece singur: tinut minte sau stiut din lamedb, si nescos de om. Sub lacat."""
		ks = cheieScurta(k)
		if not ks:
			return False
		self._improspateazaAutomat(alese)
		return ks not in self._exceptii and (ks in self._invatate or ks in self._dinLamedb)

	def numarAutomate(self):
		"""Cate canale trec singure acum (tinute minte sau din lamedb, fara cele scoase de om)."""
		pornit, alese = self.automat()
		if not pornit:
			return 0
		with self._lacat:
			self._improspateazaAutomat(alese)
			return len((self._invatate | self._dinLamedb) - self._exceptii)

	def instantaneu(self):
		"""Multimea canalelor care trec prin releu acum (lista + trecerea singura), pentru multe intrebari la rand (web:
		`cheie in instantaneu()`), fara sa verifice fisierele la fiecare canal."""
		with self._lacat:
			self._citeste()
			pornit, alese = self.automat()
			if pornit:
				self._improspateazaAutomat(alese)
				return _Instantaneu(self._chei, (self._invatate | self._dinLamedb) - self._exceptii)
			return _Instantaneu(self._chei, ())

	def _invata(self, ks):
		"""Canalul se tine minte (inainte de repornire, ca un alt evUpdatedInfo sa nu-l ia din nou). -> True daca trece."""
		with self._lacat:
			pornit, alese = self.automat()
			if not pornit:
				return False
			self._improspateazaAutomat(alese)
			if ks in self._exceptii:
				return False
			if ks in self._invatate:
				return True
			if len(self._invatate) >= MAX_CANALE:
				return False
			if not self._scrieAutomat(self._invatate | set([ks]), self._exceptii):
				self._invatate.add(ks)      # nu s-a scris: tinut minte cat ruleaza enigma2
			return True

	# ---- schimbarea listei
	def pune(self, ref, vrea):
		"""Canalul trece prin releu (vrea=True) sau nu mai trece. -> (reusit, trece_acum). Nu atinge redarea.
		Fara trecerea singura: pus in lista sau scos de acolo, ca pana in 0.7.4. Cu ea: vrea=False scoate canalul din
		lista si, daca ar trece tot singur, il pune la exceptii; vrea=True il scoate din exceptii si, daca tot nu trece,
		il pune in lista. Fisierul listei ramane numai al omului."""
		k = cheie(ref)
		if not k:
			return False, False
		with self._lacat:
			self._citeste()
			pornit, alese = self.automat()
			ks = cheieScurta(k)
			automat = pornit and self._automatFaraLacat(k, alese)
			in_lista = k in self._chei
			if vrea == (in_lista or automat):
				return True, vrea
			chei = list(self._chei)
			if vrea:
				if pornit and ks in self._exceptii:
					if not self._scrieAutomat(self._invatate, self._exceptii - set([ks])):
						return False, False
					automat = self._automatFaraLacat(k, alese)
				if not automat and not in_lista:
					if len(chei) >= MAX_CANALE:
						return False, False
					chei.append(k)
					if not self._scrie(chei):
						return False, False
			else:
				if in_lista:
					chei.remove(k)
					if not self._scrie(chei):
						return False, True
				if automat:
					if not self._scrieAutomat(self._invatate, self._exceptii | set([ks])):
						return False, True
			trece = k in self._chei or (pornit and self._automatFaraLacat(k, alese))
			gol = not self._chei
		self.actualizeazaLegatura(gol)
		return True, trece

	def toggle(self, nav, service):
		"""Pune sau scoate canalul; daca ruleaza acum pe televizor, il porneste din nou, ca schimbarea sa se vada."""
		ok, in_lista = self.pune(service, not self.checkService(service))
		if ok and nav is not None:
			try:
				acum = nav.getCurrentlyPlayingServiceReference()
				if acum is not None and cheie(acum) == cheie(service):
					nav.playService(acum, forceRestart=True)
			except Exception as e:
				_jurnal("canalul nu s-a pornit din nou: %s" % e)
		return ok, in_lista

	# ---- setarile
	def configurare(self):
		"""(gazda, port, intarziere_ms) din setari."""
		if self._configurare is not None:
			return self._configurare
		try:
			from Components.config import config
			m = config.misc
			gazda = gazdaDinAdresa(m.acces_streamrelay_url.value) or "127.0.0.1"
			port = int(m.acces_streamrelay_port.value or PORT_IMPLICIT)
			intarziere = max(0, int(m.acces_streamrelay_delay.value or 0))
		except Exception as e:
			_jurnal("setarile: %s" % e)
			return "127.0.0.1", PORT_IMPLICIT, 0
		if not 0 < port < 65536:
			port = PORT_IMPLICIT
		return gazda, port, min(intarziere, 5000)

	def asculta(self, gazda, port):
		"""True daca un program asculta la gazda:port (releul pornit)."""
		s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		s.settimeout(TERMEN_VERIFICARE_S)
		try:
			s.connect((gazda, port))
			return True
		except (OSError, socket.timeout):
			return False
		finally:
			s.close()

	def textRedare(self, ref, nume=None):
		"""Textul referintei releului pentru un canal care trece prin releu (din lista sau singur), sau None (nu trece,
		releul nu e pe receptor)."""
		k = cheie(ref)
		if not k or self.fel(k) is None:
			return None
		return self._textPentru(k, ref, nume)

	def _textPentru(self, k, ref, nume=None):
		gazda, port, _intarziere = self.configurare()
		if gazda not in GAZDE_LOCALE and not releuInRetea(gazda):
			_jurnal("adresa releului %s nu e pe receptor (nici in reteaua de acasa permisa): canalul porneste direct" % gazda)
			return None
		if nume is None:
			nume = _numeCanal(ref)
		return textReleu(k, "127.0.0.1" if gazda == "localhost" else gazda, port, nume)

	def streamrelayChecker(self, playref):
		"""Pentru pluginuri: (referinta releului, True) pentru un canal care trece prin releu (din lista sau singur), altfel
		(playref, False)."""
		text = self.textRedare(playref)
		if text is None:
			return playref, False
		from enigma import eServiceReference
		return eServiceReference(text), True

	# ---- legatura la zap
	def _lista(self):
		if self._extensii is not None:
			return self._extensii
		try:
			from Navigation import Navigation
		except Exception:
			return None
		return Navigation.playServiceExtensions

	def actualizeazaLegatura(self, gol=None):
		"""Legatura la zap numai cat lista are canale sau trecerea singura e pornita; ascultatorul PMT-ului numai cu
		trecerea singura pornita. Se cheama si de notificatorul setarii (Components/UsageConfig.py)."""
		lista = self._lista()
		if not isinstance(lista, list):
			return
		if gol is None:
			gol = not self.chei()
		pornit = self.automat()[0]
		if gol and not pornit:
			while laZap in lista:
				lista.remove(laZap)
			self._prinReleu = False
		elif laZap not in lista:
			lista.append(laZap)
		if not pornit:
			self._opresteUrmarirea()
			self._dezleagaAscultator()

	def _peZap(self, nav, playref):
		"""Extensia de zap: (playref, asincron) sau playref neschimbat."""
		vechi, self._prinReleu = self._prinReleu, False
		vechiRef, self._refReleu = self._refReleu, None
		self._asteapta = None
		self._eliberare = None
		self._opresteUrmarirea()
		k = cheie(playref)
		fel = self.fel(k) if k else None
		if fel is None:
			if k:
				self._urmaresteZap(nav, k)
			return self._direct(nav, playref, vechi, vechiRef)
		if self._directPrinSoftCsa(nav, k, fel, playref):
			return self._direct(nav, playref, vechi, vechiRef)
		text = self._textPentru(k, playref)
		if text is None:
			return self._direct(nav, playref, vechi, vechiRef)
		gazda, port, intarziere = self.configurare()
		if not self.asculta("127.0.0.1" if gazda == "localhost" else gazda, port):
			_jurnal("releul nu raspunde la %s:%d: canalul porneste direct" % (gazda, port))
			# canalele trecute singur pornesc direct fara mesaj (098C / 098D sunt si pe canale cu simulcrypt)
			if fel == "lista":
				self._mesajReleuOprit("127.0.0.1" if gazda == "localhost" else gazda, port)
			return self._direct(nav, playref, vechi, vechiRef)
		if vechi and intarziere > 0:
			self._asteapta = (nav, playref, text)
			self._pornesteCeas(intarziere)
			return playref, True
		if self._reda(nav, text):
			self._prinReleu, self._refReleu = True, k
			return playref, True
		return self._direct(nav, playref, vechi, vechiRef)

	def _direct(self, nav, playref, vechi, vechiRef):
		"""Canalul porneste direct (pe tuner). Daca zap-ul vine de pe un canal redat prin releu, sesiunea 8001 a releului
		inca tine tunerul cateva clipe: releul afla abia acum ca playerul a plecat si isi inchide cererea dupa aceea, iar
		serviciul nou ar gasi tunerul ocupat („Tunerul este ocupat”, .114 cu un singur tuner de satelit, 11.11.2026). Pe alt
		transponder, pornirea se amana pana cand sesiunea il lasa (verificat la ELIBERARE_PAS_MS, cel mult ELIBERARE_MAX_S),
		ca la plecarea de pe canalele DAB/T2 (Hds/DabT2/pornire.py). -> playref sau (playref, True) cand se amana."""
		if not vechi or not vechiRef or _acelasiTransponder(cheie(playref) or "", vechiRef):
			return playref
		if not _sesiuni8001(vechiRef):
			return playref
		# playerul a plecat deja de pe releu (stopService inainte de extensii): sesiunea veche nu mai are cui da fluxul,
		# deci se opreste pe loc; daca serverul tot o mai tine (alt client pe acelasi canal), se asteapta
		_opreste8001(vechiRef)
		if not _sesiuni8001(vechiRef):
			return playref
		_jurnal("astept ca releul sa lase tunerul (%s) inainte de %s" % (vechiRef, cheie(playref)))
		self._eliberare = (nav, playref, vechiRef, time.time() + ELIBERARE_MAX_S)
		if self._ceasEliberare is None:
			from enigma import eTimer
			self._ceasEliberare = eTimer()
			self._ceasEliberare.callback.append(self._pasEliberare)
		self._ceasEliberare.start(ELIBERARE_PAS_MS, True)
		return playref, True

	def _pasEliberare(self):
		e = self._eliberare
		if e is None:
			return
		nav, playref, vechiRef, pana = e
		try:
			acum = nav.getCurrentlyPlayingServiceReference()
		except Exception:
			acum = None
		if acum is None or cheie(acum) != cheie(playref):
			self._eliberare = None      # alt zap intre timp: el are grija de tuner
			return
		if _sesiuni8001(vechiRef) and time.time() < pana:
			self._ceasEliberare.start(ELIBERARE_PAS_MS, True)
			return
		self._eliberare = None
		_pornesteDirect(nav, playref)

	def _mesajReleuOprit(self, gazda, port):
		"""Pe televizor, de ce canalul din lista porneste fara releu (motivReleu); acelasi motiv se arata din nou numai
		dupa REPETARE_MESAJ_S, ca zap-urile prin lista sa nu-l aduca la fiecare canal. Nicio eroare nu opreste zap-ul."""
		try:
			motiv = motivReleu(gazda, port, self._module)
			acum = self._ceasMesaj()
			vechi, cand = self._ultimulMesaj
			if motiv == vechi and 0 <= acum - cand < REPETARE_MESAJ_S:
				return
			self._ultimulMesaj = (motiv, acum)
			self._anunta(motiv + " " + _t(TEXT_PORNESTE_DIRECT))
		except Exception as e:
			_jurnal("mesajul releului: %r" % (e,))

	def _reda(self, nav, text):
		from enigma import eServiceReference
		pnav = getattr(nav, "pnav", None)
		if pnav is None:
			return False
		rez = pnav.playService(eServiceReference(text))
		if rez:
			_jurnal("playerul nu porneste prin releu (%s): canalul porneste direct" % rez)
			return False
		return True

	def _pornesteCeas(self, ms):
		if self._ceas is None:
			from enigma import eTimer
			self._ceas = eTimer()
			self._ceas.callback.append(self._dupaIntarziere)
		self._ceas.start(ms, True)

	def _dupaIntarziere(self):
		a, self._asteapta = self._asteapta, None
		if a is None:
			return
		nav, playref, text = a
		# alt zap intre timp: nimic
		acum = nav.getCurrentlyPlayingServiceReference()
		if acum is None or cheie(acum) != cheie(playref):
			return
		if self._reda(nav, text):
			self._prinReleu, self._refReleu = True, cheie(playref)
		else:
			_pornesteDirect(nav, playref)

	# ---- SoftCSA (0.7.4): canalele CSA-ALT direct, fara releu
	def _softCsaStare(self):
		"""Starea din nucleu (Components/HdsSoftCsa.stare); {} cand citirea cade. Nicio eroare nu opreste zap-ul."""
		try:
			if self._softcsa is not None:
				return dict(self._softcsa[0]() or {})
			from Components import HdsSoftCsa
			return HdsSoftCsa.stare()
		except Exception as e:
			_jurnal("starea SoftCSA: %r" % (e,))
			return {}

	def _softCsaDovedit(self):
		"""Modulul a dat cuvinte de control prin soclu de la legare: canalele CSA-ALT nu mai au nevoie de releu."""
		s = self._softCsaStare()
		return bool(s.get("gata") and s.get("dovedit"))

	def _csaAltNucleu(self, ref):
		"""Ce stie nucleul despre canal: 2 au venit cuvinte, 1 CSA-ALT, 0 nu, -1 necunoscut."""
		try:
			if self._softcsa is not None:
				return int(self._softcsa[1](ref))
			from Components import HdsSoftCsa
			return HdsSoftCsa.canalCsaAlt(ref)
		except Exception:
			return -1

	def _esteIcam(self, k):
		"""Canalul din lista e ICAM: tinut minte de trecerea singura sau din lamedb cu sistemele alese (din fabrica
		098C, 098D cand setarea e oprita). Nu se uita la exceptiile omului: ele spun numai „nu singur”."""
		ks = cheieScurta(k)
		if not ks:
			return False
		pornit, alese = self.automat()
		if not alese:
			alese = caidDinText(CAID_FABRICA)
		with self._lacat:
			self._improspateazaAutomat(alese)
			return ks in self._invatate or ks in self._dinLamedb

	def _directPrinSoftCsa(self, nav, k, fel, playref):
		"""Zap-ul ocoleste releul: SoftCSA gata si canalul CSA-ALT (trecut singur, deci ICAM; din lista, numai daca e ICAM
		sau nucleul l-a vazut CSA-ALT), iar cuvintele au venit (pe canal sau de la modul) sau incercarea directa de pe
		legatura de acum n-a fost facuta inca. Un rand in jurnal."""
		s = self._softCsaStare()
		if not s.get("gata"):
			return False
		canal = self._csaAltNucleu(playref)
		if fel == "lista" and canal < 1 and not self._esteIcam(k):
			return False
		ks = cheieScurta(k) or k
		if canal == 2 or s.get("dovedit"):
			_jurnal("SoftCSA: canalul %s (%s) porneste direct, fara releu (%s)" % (ks, fel,
				"au venit cuvinte pentru el" if canal == 2 else "modulul da cuvintele CSA-ALT"))
			return True
		legatura = s.get("conexiune")
		if legatura == self._softFaraCuvinte:
			return False                # incercarea de pe legatura de acum n-a adus cuvinte: releul, ca inainte
		self._incercareSoft = (nav, k, legatura)
		if self._ceasSoft is None:
			from enigma import eTimer
			self._ceasSoft = eTimer()
			self._ceasSoft.callback.append(self._verificaIncercareSoft)
		self._ceasSoft.start(INCERCARE_SOFTCSA_S * 1000, True)
		_jurnal("SoftCSA: canalul %s (%s) porneste direct, incercare de %d s: modulul n-a dat inca niciun cuvant" % (ks,
			fel, INCERCARE_SOFTCSA_S))
		return True

	def _verificaIncercareSoft(self):
		"""Dupa INCERCARE_SOFTCSA_S de la pornirea directa pe incercare: fara niciun cuvant (nici pe canal, nici de la
		modul) si cu ECM-ul care nu spune „nu e CSA-ALT”, canalul porneste din nou prin releu, iar legatura se tine minte."""
		i, self._incercareSoft = self._incercareSoft, None
		if i is None:
			return
		nav, k, legatura = i
		acum = nav.getCurrentlyPlayingServiceReference()
		if acum is None or cheie(acum) != k or self._prinReleu or _timeshiftActiv(nav):
			return
		s = self._softCsaStare()
		canal = self._csaAltNucleu(acum)
		if s.get("dovedit") or canal in (0, 2) or s.get("conexiune") != legatura:
			return                      # cuvintele au venit, canalul nu e CSA-ALT (merge pe placa) sau alt modul legat
		self._softFaraCuvinte = legatura
		ks = cheieScurta(k) or k
		gazda, port, _intarziere = self.configurare()
		gazda = "127.0.0.1" if gazda == "localhost" else gazda
		if not releuPermis(gazda) or not self.asculta(gazda, port):
			_jurnal("SoftCSA: niciun cuvant CSA-ALT in %d s pe %s, iar releul nu raspunde: canalul ramane direct" % (
				INCERCARE_SOFTCSA_S, ks))
			return
		_jurnal("SoftCSA: niciun cuvant CSA-ALT in %d s pe %s: canalul trece prin releu" % (INCERCARE_SOFTCSA_S, ks))
		try:
			nav.playService(acum, checkParentalControl=False, forceRestart=True)
		except Exception as e:
			_jurnal("canalul nu s-a pornit din nou prin releu: %s" % e)

	# ---- trecerea singura: invatarea la redare (0.7.4)
	def _urmaresteZap(self, nav, k):
		"""Dupa un zap direct, cu trecerea singura pornita: ascultatorul afla din PMT CAID-urile canalului (o singura data
		pe zap, cel mult FEREASTRA_ZAP_S). Fara soclu si fara fisiere aici: zap-urile obisnuite nu costa nimic."""
		if not self.automat()[0]:
			return
		ks = cheieScurta(k)
		if not ks or ks in self._exceptii:
			return
		if self._softCsaDovedit():
			return                      # SoftCSA: canalul ICAM ramane direct, nu se muta pe releu
		if not self._leagaAscultator(nav):
			return
		self._areImagine = False
		self._urmarit = [nav, k, ks, self._monoton(), 0]

	def _opresteUrmarirea(self):
		self._urmarit = None
		if self._ceasIcam is not None:
			self._ceasIcam.stop()

	def _leagaAscultator(self, nav):
		ev = getattr(nav, "event", None)
		if not isinstance(ev, list):
			return False
		if self._navEv is not None and self._navEv is not ev:
			self._dezleagaAscultator()
		if self._laEveniment not in ev:
			ev.append(self._laEveniment)
		self._navEv = ev
		return True

	def _dezleagaAscultator(self):
		ev, self._navEv = self._navEv, None
		if ev is not None:
			while self._laEveniment in ev:
				ev.remove(self._laEveniment)

	def _laEveniment(self, ev):
		"""nav.event: imaginea venita si PMT-ul citit al canalului pornit direct. Repornirea nu se face de aici (lista
		evenimentelor se parcurge acum), ci din ceasul _hotaraste."""
		u = self._urmarit
		if u is None:
			return
		try:
			from enigma import iPlayableService as P
		except ImportError:
			return
		if ev in _evenimenteImagine(P):
			self._areImagine = True
			return
		if ev != P.evUpdatedInfo or u[4]:
			return
		nav, k, ks = u[0], u[1], u[2]
		if not 0 <= self._monoton() - u[3] < FEREASTRA_ZAP_S or cheie(nav.getCurrentlyPlayingServiceReference()) != k:
			self._urmarit = None
			return
		# Un raspuns "nu" nu incheie urmarirea (numai o hotarare sau sfarsitul ferestrei): cu PID-urile tinute minte,
		# primul evUpdatedInfo vine inaintea PMT-ului, cu CAID-urile numai din lamedb (lib/dvb/pmt.cpp, getProgramInfo:
		# programul din memorie), deci un canal Sky fara C: pare liber pana soseste PMT-ul adevarat.
		_criptat, caids, video = _caidServiciu(nav)
		if not caids:
			return
		pornit, alese = self.automat()
		potrivire = potrivireCaid(caids, alese) if pornit else 0
		if not potrivire or video <= 0:
			return                      # alt sistem sau radio (deocamdata): se mai asculta pana la sfarsitul ferestrei
		if potrivire == 2 and (not SIMULCRYPT_FARA_IMAGINE or self._areImagine):
			self._urmarit = None        # simulcrypt: ramane direct (sau se vede deja direct)
			return
		u[4] = potrivire
		self._pornesteCeasIcam(0 if potrivire == 1 else ASTEAPTA_IMAGINE_MS)

	def _pornesteCeasIcam(self, ms):
		if self._ceasIcam is None:
			from enigma import eTimer
			self._ceasIcam = eTimer()
			self._ceasIcam.callback.append(self._hotaraste)
		self._ceasIcam.start(ms, True)

	def _hotaraste(self):
		"""Canalul urmarit trece prin releu: tinut minte, apoi pornit din nou (Navigation.playService -> _peZap il vede
		acum ca automat). Nimic daca intre timp a venit imagine (simulcrypt), alt zap, timeshift, sau releul nu asculta."""
		u = self._urmarit
		if u is None or not u[4]:
			return                      # ceas ramas de la alt zap: urmarirea de acum n-a hotarat nimic
		self._urmarit = None
		nav, k, ks, _ora, potrivire = u
		if potrivire == 2 and (self._areImagine or _inaltimeVideo(nav) > 0):
			return
		acum = nav.getCurrentlyPlayingServiceReference()
		if acum is None or cheie(acum) != k or self._prinReleu or _timeshiftActiv(nav):
			return
		if self._softCsaDovedit():
			_jurnal("SoftCSA: canalul %s ramane direct, nu trece prin releu" % ks)
			return
		gazda, port, _intarziere = self.configurare()
		gazda = "127.0.0.1" if gazda == "localhost" else gazda
		if not releuPermis(gazda) or not self.asculta(gazda, port):
			return
		if not self._invata(ks):
			return
		_jurnal("canalul %s (%s) trece singur prin releu de acum" % (ks, "ICAM" if potrivire == 1 else "fara imagine directa"))
		try:
			# canalul ruleaza deja: fara a doua intrebare a codului pentru parinti
			nav.playService(acum, checkParentalControl=False, forceRestart=True)
		except Exception as e:
			_jurnal("canalul nu s-a pornit din nou prin releu: %s" % e)


class _Instantaneu(object):
	"""Canalele care trec prin releu la un moment dat (lista + trecerea singura), pentru `cheie in ...` fara fisiere."""

	def __init__(self, chei, automate):
		self._chei = frozenset(chei)
		self._automate = frozenset(automate)

	def __contains__(self, k):
		if k in self._chei:
			return True
		return bool(self._automate) and cheieScurta(k) in self._automate

	def __len__(self):
		return len(self._chei) + len(self._automate)


def _evenimenteImagine(P):
	"""Evenimentele care spun ca decodorul da imagine (ca in Components/HdsCulegereCanale.py)."""
	return tuple(x for x in (getattr(P, n, None) for n in ("evVideoSizeChanged", "evVideoProgressiveChanged",
		"evVideoFramerateChanged", "evVideoGammaChanged")) if x is not None)


def _caidServiciu(nav):
	"""(sIsCrypted, CAID-urile, PID-ul video) ale serviciului redat acum, din PMT; (-1, [], -1) cat nu se stiu."""
	try:
		from enigma import iServiceInformation as I
		s = nav.getCurrentService()
		info = s and s.info()
		if info is None:
			return -1, [], -1
		obiect = info.getInfoObject(I.sCAIDs)
		caids = [int(v) & 0xFFFF for v in obiect] if isinstance(obiect, (list, tuple)) else []
		return info.getInfo(I.sIsCrypted), [c for c in caids if c], info.getInfo(I.sVideoPID)
	except Exception as e:
		_jurnal("CAID-urile canalului: %r" % (e,))
		return -1, [], -1


def _inaltimeVideo(nav):
	"""Inaltimea imaginii din decodor (sVideoHeight), 0 cand nu se stie; a doua dovada de imagine, ca in
	Components/HdsEcranNegru.py pe receptoarele fara contorul de cadre."""
	try:
		from enigma import iServiceInformation as I
		s = nav.getCurrentService()
		info = s and s.info()
		return int(info.getInfo(I.sVideoHeight)) if info is not None else 0
	except Exception:
		return 0


def _timeshiftActiv(nav):
	try:
		s = nav.getCurrentService()
		ts = s and s.timeshift()
		return bool(ts and ts.isTimeshiftActive())
	except Exception:
		return False


ELIBERARE_PAS_MS = 100          # plecarea de pe un canal prin releu: cat de des se intreaba daca sesiunea 8001 a plecat
ELIBERARE_MAX_S = 3.0           # ... cel mult atat; apoi canalul porneste oricum


def _sesiuni8001(ref):
	"""Cate sesiuni ale serverului de flux al imaginii (Hds/DabT2/server8001.py) mai tin canalul `ref`; 0 cand nu se
	poate afla (fara server: nimic de asteptat)."""
	try:
		from Hds.DabT2 import server8001
		return int(server8001.sesiuni_deschise(ref) or 0)
	except Exception:
		return 0


def _opreste8001(ref):
	"""Sesiunile serverului de flux de pe canalul `ref` oprite pe loc (server8001.opreste_sesiunile). Nu arunca."""
	try:
		from Hds.DabT2 import server8001
		return server8001.opreste_sesiunile(ref)
	except Exception as e:
		_jurnal("oprirea sesiunii 8001 a releului: %r" % (e,))
		return 0


def _acelasiTransponder(a, b):
	"""Doua chei de canal DVB pe acelasi transponder (TSID, ONID, spatiul de nume): tunerul se imparte, nimic de asteptat."""
	pa, pb = str(a or "").split(":"), str(b or "").split(":")
	if len(pa) < 7 or len(pb) < 7:
		return False
	try:
		return all(int(pa[i] or "0", 16) == int(pb[i] or "0", 16) for i in (4, 5, 6))
	except ValueError:
		return False


def _pornesteDirect(nav, playref):
	"""Dupa o pornire prin releu cazuta: canalul direct, fara extensii (playerul de baza)."""
	try:
		nav.pnav.playService(playref)
	except Exception as e:
		_jurnal("canalul nu a pornit: %s" % e)


def _numeCanal(ref):
	try:
		from ServiceReference import ServiceReference
		return ServiceReference(ref).getServiceName() or ""
	except Exception:
		return ""


_RELEU = []


def releu():
	"""Obiectul unic al listei (facut la prima cerere)."""
	if not _RELEU:
		_RELEU.append(Releu())
	return _RELEU[0]


def laZap(nav, playref, event, infobar):
	"""Navigation.playServiceExtensions: pusa numai cat lista are canale sau trecerea singura e pornita."""
	return releu()._peZap(nav, playref)


def porneste():
	"""Din mytest.py, numai cand fisierul listei exista sau trecerea singura e pornita: legatura la zap."""
	releu().actualizeazaLegatura()


def setareSchimbata(_el=None):
	"""Notificatorul setarii trecerii singure (Components/UsageConfig.py): legatura la zap si ascultatorul se pun sau se
	scot pe loc; starea din ecranul setarilor se reface."""
	try:
		_STARE_RECENTA[0] = None
		releu().actualizeazaLegatura()
	except Exception as e:
		_jurnal("setarea trecerii singure: %r" % (e,))


def potrivit(ref):
	"""True daca `ref` e un canal care poate intra in Stream Relay (meniul listei, web)."""
	return cheie(ref) is not None
