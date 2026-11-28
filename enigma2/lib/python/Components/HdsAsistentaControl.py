# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsAsistentaControl.py: partea de control a Asistentei de la distanta (nivelul B, "Control complet"): textul ecranului
# deschis pe receptor (op "ecran"), tastele telecomenzii (op "taste") si scrierea intr-un camp de text (op "text"). Cu
# textul ecranului si cu tastele, echipa face prin meniuri orice ar face omul cu telecomanda.
#
# Echipa vede toate meniurile si toate valorile, in afara de parole: ele devin *** (text) sau se acopera (captura) inainte
# sa plece de pe receptor (pusa la loc in 0.8.0, Eduard 24.11.2026 11:39; 0.7.8 si 0.7.9 le trimiteau in clar).
# Asistenta nu opreste scrierea omului.
#
# TASTELE: orice tasta din data/keymap.xml (TASTE: numele romanesti si cele Linux, key_*; numai POWER lung nu),
# oricate pe cerere (ASP7, fara plafon), cu PAUZA_MS intre ele, trimise ca tastele adevarate ale telecomenzii (eRCMapper.inject cu
# dispozitivul nativ, ca in interfata web; fara el, harta de actiuni).
#
# FIRUL: interfata enigma2 nu e sigura intre fire; brokerul ruleaza pe firul sesiunii. Toate atingerile ecranului merg
# prin PeFir: cererea intra intr-o coada, firul enigma2 e trezit (reactor.callFromThread) si o face; ceasul semnului
# (Screens/HdsAsistentaSemn.Controler, o data pe secunda) goleste si el coada, ca plasa. Tastele pleaca una pe tic de
# eTimer, nu cu sleep pe firul enigma2. Modulul nu importa nimic din enigma2 la incarcare: probele de pe PC dau ecrane
# false (orice obiect cu aceleasi metode).

import os
import re
import threading
import time
import unicodedata
from functools import lru_cache
from urllib.parse import unquote, urlsplit

# lista alba a tastelor (numele din cerere -> codul Linux al tastei, ca telecomanda fizica si interfata web)
TASTE = {
	"0": 11, "1": 2, "2": 3, "3": 4, "4": 5, "5": 6, "6": 7, "7": 8, "8": 9, "9": 10,
	"sus": 103, "jos": 108, "stanga": 105, "dreapta": 106,
	"ok": 352, "exit": 174, "menu": 139, "info": 358, "epg": 365,
	"rosu": 398, "verde": 399, "galben": 400, "albastru": 401,
	"ch+": 402, "ch-": 403, "vol+": 115, "vol-": 114, "mute": 113,
	"text": 388, "help": 138, "audio": 392, "subt": 370, "tv": 377, "radio": 385, "fav": 364,
	"anterior": 412, "urmator": 407, "pauza": 119, "redare": 207, "stop": 128,
	"inapoi-rapid": 168, "inainte-rapid": 208, "timer": 359, "power": 116,
	# HIS1 (asistentele 725736 si 582951, 22.11): restul tastelor din data/keymap.xml, cu nume romanesti; istoricul
	# canalelor (historyBack / historyNext in InfobarChannelSelection) e pe KEY_BACK si KEY_FORWARD
	"istoric-inapoi": 158, "istoric-inainte": 159, "inregistrare": 167, "redare-pauza": 164, "pvr": 366,
	"video": 393, "lista": 395, "pagina-sus": 104, "pagina-jos": 109, "ultimul": 405, "context": 438, "mod": 373,
	"media": 226, "fisier": 144, "somn": 142, "acasa": 102, "sfarsit": 107, "melodia-anterioara": 165,
	"melodia-urmatoare": 163, "zoom": 372, "unghi": 371, "www": 150, "optiuni": 357, "sat": 381,
}
# HIS1: orice tasta din data/keymap.xml si dupa numele ei Linux (KEY_PREVIOUSSONG -> "key_previoussong"), ca orice
# telecomanda sa poata fi urmata exact (aceleasi coduri ca keyids.KEYIDS)
TASTE_LINUX = {
	"key_esc": 1, "key_1": 2, "key_2": 3, "key_3": 4, "key_4": 5, "key_5": 6, "key_6": 7, "key_7": 8, "key_8": 9,
	"key_9": 10, "key_0": 11, "key_backspace": 14, "key_tab": 15, "key_i": 23, "key_enter": 28, "key_space": 57,
	"key_f1": 59, "key_f2": 60, "key_f3": 61, "key_f4": 62, "key_f5": 63, "key_f6": 64, "key_f7": 65, "key_f8": 66,
	"key_f9": 67, "key_f10": 68, "key_f11": 87, "key_f12": 88, "key_sysrq": 99, "key_home": 102, "key_up": 103,
	"key_pageup": 104, "key_left": 105, "key_right": 106, "key_end": 107, "key_down": 108, "key_pagedown": 109,
	"key_insert": 110, "key_delete": 111, "key_mute": 113, "key_volumedown": 114, "key_volumeup": 115, "key_power": 116,
	"key_pause": 119, "key_stop": 128, "key_open": 134, "key_help": 138, "key_menu": 139, "key_setup": 141,
	"key_sleep": 142, "key_file": 144, "key_www": 150, "key_bookmarks": 156, "key_back": 158, "key_forward": 159,
	"key_ejectcd": 161, "key_nextsong": 163, "key_playpause": 164, "key_previoussong": 165, "key_record": 167,
	"key_rewind": 168, "key_homepage": 172, "key_exit": 174, "key_play": 207, "key_fastforward": 208, "key_search": 217,
	"key_media": 226, "key_switchvideomode": 227, "key_ok": 352, "key_option": 357, "key_info": 358, "key_time": 359,
	"key_archive": 361, "key_program": 362, "key_favorites": 364, "key_epg": 365, "key_pvr": 366, "key_subtitle": 370,
	"key_angle": 371, "key_zoom": 372, "key_mode": 373, "key_keyboard": 374, "key_screen": 375, "key_pc": 376,
	"key_tv": 377, "key_tv2": 378, "key_sat": 381, "key_radio": 385, "key_player": 387, "key_text": 388, "key_aux": 390,
	"key_mp3": 391, "key_audio": 392, "key_video": 393, "key_directory": 394, "key_list": 395, "key_red": 398,
	"key_green": 399, "key_yellow": 400, "key_blue": 401, "key_channelup": 402, "key_channeldown": 403, "key_last": 405,
	"key_ab": 406, "key_next": 407, "key_restart": 408, "key_previous": 412, "key_context_menu": 438, "key_ascii": 510,
}
TASTE.update(TASTE_LINUX)
# singura tasta oprita: POWER tinuta apasat (meniul de oprire / oprirea receptorului ar inchide asistenta)
TASTE_FARA_LUNG = ("power", "key_power")
# aceleasi taste sub alte nume (engleza, prescurtari)
ALIASURI = {
	"up": "sus", "down": "jos", "left": "stanga", "right": "dreapta", "back": "exit", "inapoi": "exit",
	"meniu": "menu", "red": "rosu", "green": "verde", "yellow": "galben", "blue": "albastru",
	"ttx": "text", "teletext": "text", "chplus": "ch+", "chminus": "ch-", "volplus": "vol+", "volminus": "vol-",
	"pause": "pauza", "play": "redare",
	"rec": "inregistrare", "record": "inregistrare", "playpause": "redare-pauza", "list": "lista",
	"pageup": "pagina-sus", "pgup": "pagina-sus", "pagedown": "pagina-jos", "pgdn": "pagina-jos",
	"ff": "inainte-rapid", "fastforward": "inainte-rapid", "rew": "inapoi-rapid", "rewind": "inapoi-rapid",
	"subtitle": "subt", "subtitrare": "subt", "previous": "anterior", "prev": "anterior", "next": "urmator",
	"history-back": "istoric-inapoi", "history-next": "istoric-inainte", "last": "ultimul", "pauza-redare": "redare-pauza",
}
# un pas fara tasta: asteapta ASTEAPTA_MS (de pilda dupa ce se deschide un ecran care se incarca greu)
ASTEAPTA = "asteapta"
ASTEAPTA_MS = 1200
# apasarea lunga: "ok:lung" (ca tasta tinuta)
SUFIX_LUNG = ":lung"
PAUZA_MS = 400
# dupa ultima tasta, cat se asteapta pana se citeste ecranul
LINISTE_MS = 900

# campurile de parola si de PIN (clasele elementelor de setari): valoarea lor se arata ca text (_valoare)
CAMPURI_PAROLA = ("ConfigPassword", "ConfigPIN")

# Curatarea secretelor din textele care PLEACA spre echipa (jurnalele, Tools/HdsJurnalInterfata.py; raportul de
# setari si tot textul brokerului, Components/HdsAsistentaBroker.mascheaza; recunoasterea randurilor secrete din
# /setari). Nu schimba ecranul omului. Numai iesirea spre echipa pierde valorile private.
# Cheile interne si etichetele secretelor, cu sau fara diacritice.
# Cuvintele din textul ghidului (0.7.5 ASM, TODO 15.11 03:14 (filtrul secretelor): descrierea emisiunii iesea acoperita
# in captura pentru echipa): key nu e secret in cuvintele englezesti care se termina asa (Monkey, Turkey, Hockey, Donkey,
# Jockey, Whiskey, Lackey, Hickey, Mickey) si nici cand il urmeaza alt cuvant cu majuscula (Key West, Key Largo); auth nu
# e secret in Author, Authority, Authentic; secret nu e secret dupa articol (The Secret). Raman secrete: key la sfarsitul
# etichetei sau lipit (key1, wifi.key0, config.hotkey, passkey, API key, Private hotkey), auth, auth_token, authorization,
# authentication, secret, client secret, secret_key.
_CHEIE_IN_CUVANT = r"(?<!mon)(?<!tur)(?<!hoc)(?<!don)(?<!joc)(?<!whis)(?<!lac)(?<!hic)(?<!mic)"
_SECRET = re.compile(r"(?i)(parol|password|passwd|passphrase|(?:^|[._\s])(?:pass|pwd|psk)(?:\b|[._])|token|(?<!the )secret|"
	r"jeton|chei[ae]|api[ _.-]?key|" + _CHEIE_IN_CUVANT + r"key(?:\b(?!\s+(?-i:[A-Z][a-z]))|[._0-9])|"
	r"(?:^|[._\s])pin(?:\b|[._0-9])|servicepin|setuppin|"
	r"auth(?!or(?:s|ed|ing|ess|ship|it(?:y|ies|ative))?\b|entic(?:ity|ally)?\b)|cookie|cod[ _.-]?(?:de[ _.-]?)?asociere|(?:^|[._\s])(?:biss|cw)(?:\b|[._0-9])|"
	r"control[ _.-]?word|cuvant[ _.-](?:de[ _.-])?control)")
# In text natural, numarul sau numele unei taste arata sensul lui key. Caile interne (remote.key, hotkey etc.)
# si cheile de acces raman secrete; un alt secret din acelasi text se verifica in continuare.
_CHEIE_TASTA = re.compile(r"(?i)(?<![\w.-])(?:hotkey|(?:[0-9]|red|green|yellow|blue|ok|exit|menu|info|epg|"
	r"power|volume|channel|up|down|left|right|arrow|function|keyboard|hot|remote(?:[ -]control)?|button)\s+key)\b(?![._0-9])")
_CONTEXT_CHEIE_ACCES = re.compile(r"(?i)\b(?:api|access|public|private|encryption|aes|rsa|ssh|wpa|wep|wi[ -]?fi|biss)\b")
# Frazele obisnuite din textul ghidului in care pass, cookie, cheia si pin nu sunt secrete (0.7.5 FIR, TODO 15.11 05:08
# (ASM, filtrul secretelor in text natural): "Mountain Pass:", "Fortune Cookie:", "Cheia succesului:" acopereau
# descrierea in captura pentru echipa si ieseau cu *** in textul ecranului). Ca la ASM, numai excluderi din liste
# stiute, nu o margine noua: pass dupa un cuvant al trecatorii sau al biletului (Mountain, Boarding, Season, Hall),
# cookie dupa felul prajiturii sau urmat de alt cuvant cu majuscula (Cookie Monster), cheia sau cheile urmate de un
# cuvant din povesti (succesului, fericirii, misterului), pin dupa lemn, ulei, padure, con (copacul), pin-up, bowling
# pin. Nu dupa terminatie (-ului, -ei): "Cheia retelei" e parola Wi-Fi. Raman secrete: pass, passkey, Wi-Fi pass,
# cookie, Cookie:, session cookie, cookies.txt, Cheie, Cheia API, Cheia retelei, PIN, Codul PIN, cod de pin. Se scot ca
# tastele, numai cand textul nu pomeneste o cheie de acces (_CONTEXT_CHEIE_ACCES); restul textului se verifica mai
# departe. Cuvintele romanesti fara diacritice: cheieSecreta le scoate inainte.
_TEXT_NATURAL = re.compile(r"(?i)\b(?:"
	r"(?:mountain|boarding|season|hall|free|day|bus|ski|backstage|press|fast|bike|weekly|monthly|annual|world|gold|"
	r"golden|silver|summer|winter)\s+pass(?:es)?\b|"
	r"(?:fortune|chocolate(?:\s+chip)?|chip|sugar|butter|oatmeal|ginger|christmas|cream|cracker)\s+cookies?\b|"
	r"(?-i:Cookies?)(?=\s+(?-i:[A-Z][a-z]))|"
	r"chei(?:a|le)\s+(?:succesului|fericirii|misterului|enigmei|vietii|victoriei|povestii|inimii|regatului|"
	r"imparatiei|cerului|raiului|orasului|castelului|comorii|destinului|adevarului|iubirii|libertatii|timpului|lumii|"
	r"visului|viselor)\b|"
	r"(?:lemn|ulei|padure|paduri|con|conuri|ace|sirop|miros|parfum|ramuri)\s+de\s+pin\b|"
	r"pin[ -]?up\b|(?:bowling|safety|rolling)\s+pins?\b)")
_URL_PAROLA = re.compile(r"(?i)([a-z][a-z0-9+.-]*://[^/\s:@]+:)[^\s/@]*(@)")
# adresa unui canal de la un furnizor are contul in cale: /live/<utilizator>/<parola>/<id>.ts (Components/HdsIptvClient.py)
_URL_CALE_CONT = re.compile(r"(?i)(://[^/\s]+/(?:live|movie|series|timeshift)/)[^/\s]+/[^/\s]+/")
_URL_PARAMETRU = re.compile(r"([?&;])([^=&#;\s]+)=([^&#;\s]*)")
_ATRIBUIRE = re.compile(r"^([^=:|\n]+)(\s*[=:|]\s*)(.*)$")
_SECRET_JURNAL = re.compile(r"(?i)(\b(?:password|passwd|passphrase|parol[ăa]|psk|token|(?<!the )secret|pwd|pass|pin|key|"
	r"api[ _.-]?key|chei[ae](?:[ _.-]?api)?|biss[0-9]*|cw|control[ _.-]?word|cuv[âa]nt[ _.-](?:de[ _.-])?control)\s*[=:]\s*)"
	r"(?:\"[^\"]*\"|'[^']*'|[^\s,;&]+)")
_BEARER = re.compile(r"(?i)(\bbearer\s+)[a-z0-9._~+/=-]+")
_VALOARE_CONT = re.compile(r"[^,;&]*")
_ANTET_SECRET = re.compile(r"(?i)(\b(?:authorization|(?:set-)?cookie)\s*[=:]\s*).*$")


# Fiecare regula de mai sus cere macar unul dintre semnele = : | sau cuvantul bearer (o adresa cu cont are "://"). Un
# text fara ele nu se poate schimba, deci nu mai trece prin cele sapte expresii (rapoartele 573125 si 891312:
# capturile pentru web verificau la fiecare schimbare de pe ecran toate randurile listelor mari ale AJPanel, iar firul
# principal statea ocupat cate doua minute).
_POATE_SECRET = re.compile(r"(?i)[=:|]|bearer")
_BETA_ID = re.compile(r"(?i)hds_beta\.(?:id|cod)\b")


def cheieSecreta(cheie):
	return _cheieSecreta(str(cheie))


@lru_cache(maxsize=4096)
def _cheieSecreta(cheie):
	text = "".join(c for c in unicodedata.normalize("NFKD", cheie) if not unicodedata.combining(c))
	if not _CONTEXT_CHEIE_ACCES.search(text):
		text = _TEXT_NATURAL.sub("", _CHEIE_TASTA.sub("", text))
	return bool(_SECRET.search(text) or _BETA_ID.search(text))


@lru_cache(maxsize=8192)
def _textCuSecret(text):
	"""Raspunsul pentru acelasi text se tine minte: listele se reverifica la fiecare schimbare de pe ecran."""
	return mascheazaSecrete(text) != text


def mascheazaSecrete(text):
	"""Textul ecranului pentru echipa: numai parolele devin *** (mascheazaParole)."""
	return mascheazaParole(text)

# Conturile din adresele salvate nu pleaca spre echipa, inclusiv forma din referintele de serviciu
# (http%3a//nume%3aparola@gazda), unde mascheazaSecrete nu ajunge.
_URL_CONT = re.compile(r"(?i)([a-z][a-z0-9+.-]*(?:://|%3a//))[^/\s@?#]*(@|%40)")
_URL_CALE_CONT_CODAT = re.compile(r"(?i)(%3a//[^/\s]+/(?:live|movie|series|timeshift)/)[^/\s]+/[^/\s]+/")
_URL_UTILIZATOR = re.compile(r"(?i)([?&;](?:user|username|usr|uname|login|utilizator)=)[^&#;\s]*")


def mascheazaConturi(text):
	"""Textul integral pentru echipa de asistenta."""
	return text or ""


# Eduard, 12.11.2026 19:19: „FARA PAROLE, ATAT”. Asistenta (Components/HdsAsistentaBroker.mascheaza) si jurnalul
# interfetei de pe receptor (Tools/HdsJurnalInterfata.py) ascund NUMAI parolele: numele de utilizator, gazdele, porturile,
# adresele MAC, randurile modulelor de acces si restul raman. Ce iese public (rapoartele de pe forum, pachetele testerilor,
# codurile QR) trece in continuare la plecare prin HdsBetaTester.curata si HdsDiagnostic.faraDatePersonale.
# Cheia unei parole: password, passwd, passphrase, pwd, parola (si lipite: httppwd, wpa_passphrase), pass si psk numai
# singure sau dupa . _ - (bypass, compass raman).
_CHEIE_PAROLA = r"(?:[a-z0-9_.-]*(?:password|passwd|passphrase|pwd|wep_key[0-9]?|parol[a-z\u0103\u00e2\u00ee\u0219\u021b]*)|(?:[a-z0-9_.-]*[._-])?(?:pass|psk))"
# un rand care e chiar o atribuire (setari, oscam.server, wpa_supplicant.conf, hostapd.conf): tot restul randului
_PAROLA_RAND = re.compile(r"(?im)^([ \t]*" + _CHEIE_PAROLA + r"[ \t]*[=:][ \t]*)\S.*$")
# in mijlocul unui rand (jurnale, JSON, adrese cu ?password=): o valoare, intre ghilimele sau pana la spatiu , ; &
_PAROLA_VALOARE = re.compile(r"(?i)(?<![\w.-])(" + _CHEIE_PAROLA + r"[\"']?[ \t]*[=:][ \t]*)(?:(\")[^\"]*\"|(')[^']*'|[^\s,;&\"'<>]+)")


def _stelutePastreazaGhilimele(m):
	g = m.group(2) or m.group(3) or ""
	return m.group(1) + g + "***" + g
# linia de comanda a unui proces (/proc/<pid>/cmdline): --password x, -pass x
_PAROLA_OPTIUNE = re.compile(r"(?i)(?<![\w-])(--?(?:password|passwd|pass|pwd|psk)[ \t]+)\S+")
# adresele cu cont: schema://nume:parola@gazda, forma codata din referintele de serviciu si nume:parola@gazda fara schema
_PAROLA_URL = re.compile(r"(?i)([a-z][a-z0-9+.-]*://[^/\s:@]+:)[^\s/@]*(@)")
_PAROLA_URL_CODAT = re.compile(r"(?i)(%3a//[^/\s:@%]+%3a)[^\s/@]*?(%40|@)")
_PAROLA_URL_GOL = re.compile(r"(?<![\w.:/%+-])([\w.+-]+:)[^\s/@:]+(@[\w-]+(?:\.[\w-]+)*)")
# adresa unui canal de la un furnizor: /live/<utilizator>/<parola>/<id>.ts (Components/HdsIptvClient.py)
_PAROLA_URL_CALE = re.compile(r"(?i)((?:://|%3a//)[^/\s]+/(?:live|movie|series|timeshift)/[^/\s]+/)[^/\s]+/")
# Adresele de flux IPTV (DSP 14.11.2026 22:41, asistenta 186908): aici utilizatorul si parola sunt contul liniei, deci
# se ascund amandoua, oriunde ar sta: /live/<u>/<p> si la sfarsitul adresei (randul ServiceApp "listDir(http://.../live/
# <u>/<p>) - error"), forma codata a referintei (%3a// si %3a%2f%2f), schema://u:p@, ?username=&password= (get.php,
# player_api.php), ?token=. In afara adreselor numele de utilizator ramane (Eduard, 12.11.2026 19:19).
_FLUX_CAPAT = r"[^/\s?#&)\]'\"<>,;:|]+"
_FLUX_CALE = re.compile(r"(?i)((?:://|%3a//)[^/\s]+/(?:live|movie|series|timeshift)/)" + _FLUX_CAPAT + r"/" + _FLUX_CAPAT)
# aceeasi cale fara schema si gazda, la inceput de rand sau dupa spatiu, ghilimele, paranteza, = , ; | (cererea
# "GET /live/<u>/<p>/101.ts" din jurnalul unui server, "/movie/<u>/<p>/5.mkv"): aici se cere si al treilea segment
# (id-ul), ca o cale obisnuita cu doua segmente (/live/stiri/azi.html) sa ramana cum e
_FLUX_CALE_FARA_SCHEMA = re.compile(r"(?im)((?:^|[\s\"'(\[=,;|])/(?:live|movie|series|timeshift)/)" + _FLUX_CAPAT + r"/" +
	_FLUX_CAPAT + r"(?=/[^/\s])")
_FLUX_CALE_CODAT = re.compile(r"(?i)(%3a%2f%2f(?:(?!%2f)[^\s/:])+(?:%2f(?:(?!%2f)[^\s/:])+)*?%2f(?:live|movie|series|timeshift)%2f)"
	r"(?:(?!%2f)[^\s/:&|])+%2f(?:(?!%2f)[^\s/:&|?#])+")
_FLUX_CONT = re.compile(r"(?i)([a-z][a-z0-9+.-]*://)[^/\s:@]+:[^\s/@]*@")
_FLUX_CONT_CODAT = re.compile(r"(?i)(%3a(?://|%2f%2f))(?:(?!%3a)[^/\s:@%]|%(?!3a)[0-9a-f]{2})+%3a(?:(?!%2f)[^\s/@])*?(%40|@)")
_FLUX_PARAMETRU = re.compile(r"(?i)([?&](?:username|user|usr|uname|login|password|passwd|pass|pwd|(?:[a-z0-9]+_)?token)=)[^&#\s'\"<>)|]*")
_FLUX_PARAMETRU_CODAT = re.compile(r"(?i)((?:%3f|%26)(?:username|user|usr|uname|login|password|passwd|pass|pwd|(?:[a-z0-9]+_)?token)%3d)"
	r"(?:(?!%26)[^&#\s'\"<>):|])*")
# randurile cititoarelor (CCcam.cfg, newcamd.list): C:/N:/L: gazda port utilizator PAROLA, F: utilizator PAROLA,
# CWS = gazda port utilizator PAROLA; gazda, portul si utilizatorul raman
_PAROLA_LINIE = re.compile(r"(?m)^([ \t]*(?:[CNL]:|CWS[ \t]*=)[ \t]*\S+[ \t]+\S+[ \t]+\S+[ \t]+)\S+")
_PAROLA_PRIETEN = re.compile(r"(?m)^([ \t]*F:[ \t]*\S+[ \t]+)\S+")
# antetul HTTP cu parola (Basic) sau cu jetonul care tine loc de parola
_PAROLA_ANTET = re.compile(r"(?im)(\bauthorization[ \t]*[=:][ \t]*)\S.*$")
# fara niciunul dintre aceste semne textul nu are parola (jurnalul interfetei: cate un rand, mii pe minut)
_POATE_PAROLA = re.compile(r"(?im):\d*:\d*:\d*:\d*:\d*:\d*:|:[0-9A-FX]{32}:|pass|pwd|psk|parol|wep_key|@|%40|authoriz|/(?:live|movie|series|timeshift)/|^\s*(?:[cnlf]:|cws)|"
	r"%2f(?:live|movie|series|timeshift)%2f|[?&](?:user(?:name)?|usr|uname|login|(?:[a-z0-9]+_)?token)=|"
	r"(?:%3f|%26)(?:user(?:name)?|usr|uname|login|(?:[a-z0-9]+_)?token)%3d|"
	r"kennwort|mot de passe|contrase|wachtw|has[lł]o|heslo|jelsz|lozink|geslo|salasan|adgangskode|senord|parool|slapta|[şs]ifre|"
	r"senha|lykil|парол|κωδικ|كلمة")
# aceleasi cuvinte, fara cele englezesti si romanesti (pe care le prind expresiile de sus)
_POATE_PAROLA_LIMBI = re.compile(r"(?i)kennwort|mot de passe|contrase|wachtw|has[lł]o|heslo|jelsz|lozink|geslo|salasan|"
	r"adgangskode|senord|passord|parool|slapta|[şs]ifre|senha|lykil|парол|κωδικ|كلمة|passw")
# mascheazaParole lucreaza un text mare pe bucati de atatia octeti (randuri intregi)
_BUCATA_MASCA = 64 * 1024
# Toate expresiile mastii raman intr-un rand (fara \n), afara de valoarea intre ghilimele a lui _PAROLA_VALOARE, care
# merge pana la ghilimeaua urmatoare. Daca o bucata se termina cu o asemenea valoare inca deschisa, pe tot textul ea
# s-ar fi inchis mai jos: atunci bucata se lipeste de urmatoarea (aceeasi cheie ca _PAROLA_VALOARE).
_PAROLA_VALOARE_DESCHISA = re.compile(r"(?i)(?<![\w.-])" + _CHEIE_PAROLA + r"[\"']?[ \t]*[=:][ \t]*(?:\"[^\"]*|'[^']*)\Z")


# O valoare opaca poate tine loc de parola indiferent de numele campului.
# Tiparul cauta valori, nu fragmente din chei precum "port" in "sport".
_VALOARE_OPACA = re.compile(r"(?<![a-zA-Z0-9_./%+~-])[a-zA-Z0-9_./%+~-]{20,}={0,2}(?![a-zA-Z0-9_./%+~=-])")
# Sarim si escaparile din afara sirurilor, fara a relua cautarea la fiecare ghilimea escapata.
_SIR_JSON_JETON = re.compile(r'\\.|"(?:[^"\\]|\\.)*"')
_DUPA_CHEIE_JSON = re.compile(r"[ \t\r\n]*:")
_DUPA_CHEIE_JETON = re.compile(r'''[ \t]*(?:=|["'][ \t\r\n]*:)''')


def _pareJeton(valoare):
	"""Forma JWT, hex sau sir opac cu alfabet mixt; fara presupuneri despre numele cheii."""
	from urllib.parse import unquote
	for _incercare in range(2):
		decodat = unquote(valoare)
		if decodat == valoare:
			break
		valoare = decodat
	if len(valoare) < 20 or valoare.startswith(("/usr/", "/etc/", "/media/", "config.")):
		return False
	if re.fullmatch(r"[a-fA-F0-9]{24,}", valoare) and re.search(r"[a-fA-F]", valoare) and re.search(r"[0-9]", valoare):
		return True
	if re.fullmatch(r"eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+", valoare):
		return True
	# Base64 nu cere cifre sau un amestec anume de litere mici si mari.
	if re.fullmatch(r"[a-zA-Z0-9+/_-]+={0,2}", valoare):
		import base64
		try:
			base64.b64decode(valoare + "=" * (-len(valoare) % 4), altchars=b"-_", validate=True)
			return True
		except (ValueError, TypeError):
			pass
	if (len(valoare) >= 32 and re.fullmatch(r"[a-zA-Z0-9_+~-]+={0,2}", valoare)
			and re.search(r"[a-zA-Z]", valoare) and re.search(r"[0-9]", valoare) and len(set(valoare)) >= 12):
		return True
	if (len(valoare) >= 24 and re.fullmatch(r"[a-zA-Z]+={0,2}", valoare) and len(set(valoare)) >= 16
			and sum(c.isupper() for c in valoare) * 3 >= len(valoare)
			and sum(c.islower() for c in valoare) * 3 >= len(valoare)):
		return True
	# Caile si numele obisnuite nu au simultan cifre, litere mici si mari.
	if not all(re.search(p, valoare) for p in (r"[a-z]", r"[A-Z]", r"[0-9]")):
		return False
	return len(set(valoare)) >= 12


def _contineJeton(valoare):
	"""Decodam si delimitatorii URL inainte de a cauta formele opace din interior."""
	from urllib.parse import unquote, unquote_plus
	# Pastram si vederea cu plus literal: base64 poate contine chiar acest semn.
	for decodifica in (unquote, unquote_plus):
		vedere = valoare
		for incercare in range(3):
			if any(_pareJeton(c.group()) for c in _VALOARE_OPACA.finditer(vedere)):
				return True
			if incercare == 2:
				break
			decodat = decodifica(vedere)
			if decodat == vedere:
				break
			vedere = decodat
	return False


def mascheazaJetoane(text):
	"""Textul integral pentru echipa de asistenta."""
	return text or ""


# fisierele de parole nu au o eticheta inaintea valorii: randul din /etc/shadow (nume:hash:zile:...) si cel din smbpasswd
# (nume:uid:LANMAN:NT:...), oriunde ar aparea (op citeste, op comanda)
# 9 campuri, hash-ul cu $ sau crypt de 13 semne: randurile din lamedb (a1b2:00c00000:0407:0001:1:0) nu au voie sa fie prinse
_PAROLA_SISTEM = re.compile(r"(?m)^([A-Za-z_][\w.-]*:)(?:\$[^:\s]+|[./0-9A-Za-z]{13})((?::\d*){7}[ \t]*\r?$)")
_PAROLA_SAMBA = re.compile(r"(?m)^([A-Za-z_][\w.-]*:\d+:)[0-9A-Fa-fX]{32}:[0-9A-Fa-fX]{32}(:)")


def mascheazaParole(text):
	"""Iesirea spre echipa: numai parolele devin ***, plus utilizatorul din adresele de flux (contul liniei); tot restul
	textului ramane cum e. Scoasa din 0.7.8 (REGULA 0) si pusa la loc in 0.8.0: Eduard, 24.11.2026 11:39 („e greseala la
	ultimele doua versiuni”), dupa analiza lui el bandido (LegitFTA 28717 post-110339). Pe televizor si in web parolele
	raman in clar; aici trece numai ce pleaca de pe receptor si jurnalul interfetei de pe disc.
	Un text mare (un jurnal de 1,4 MB: ~10 s pe un SF8008 ocupat) se lucreaza pe bucati de randuri intregi
	(_BUCATA_MASCA), ca lacatul global Python sa fie lasat intre bucati si firul interfetei sa nu stea; rezultatul e
	acelasi ca pe tot textul odata (vezi _PAROLA_VALOARE_DESCHISA)."""
	if not text:
		return ""
	if not _POATE_PAROLA.search(text):
		return text
	if len(text) <= _BUCATA_MASCA:
		text = _mascheazaDupaRand(_PAROLA_RAND.sub(r"\1***", text))
		return _parolaLimbi(text) if _POATE_PAROLA_LIMBI.search(text) else text
	bucati = []
	inceput, lungime = 0, len(text)
	while inceput < lungime:
		capat = inceput + _BUCATA_MASCA
		while True:
			sfarsit = text.find("\n", capat) if capat < lungime else -1
			sfarsit = lungime if sfarsit < 0 else sfarsit + 1
			bucata = text[inceput:sfarsit]
			if not _POATE_PAROLA.search(bucata):
				break
			bucata = _PAROLA_RAND.sub(r"\1***", bucata)
			if sfarsit >= lungime or not _valoareDeschisa(bucata):
				bucata = _mascheazaDupaRand(bucata)
				break
			# o valoare intre ghilimele deschisa aici se inchide in bucata urmatoare: le lucram impreuna
			capat = sfarsit + _BUCATA_MASCA
		bucati.append(bucata)
		inceput = sfarsit
	# ca pe tot textul: etichetele traduse se cauta in toate randurile daca apare un cuvant al lor oriunde
	if any(_POATE_PAROLA_LIMBI.search(b) for b in bucati):
		bucati = [_parolaLimbi(b) for b in bucati]
	return "".join(bucati)


def _valoareDeschisa(bucata):
	"""_PAROLA_VALOARE_DESCHISA, cautata numai de unde poate incepe: ghilimeaua deschisa e ultima de felul ei din bucata,
	iar cheia dinaintea ei sta pe acelasi rand (cheia, spatiile si = nu trec de capatul de rand)."""
	ultime = [i for i in (bucata.rfind('"'), bucata.rfind("'")) if i >= 0]
	if not ultime:
		return False
	return _PAROLA_VALOARE_DESCHISA.search(bucata, bucata.rfind("\n", 0, min(ultime)) + 1) is not None


def _mascheazaDupaRand(text):
	"""Expresiile de dupa _PAROLA_RAND, in aceeasi ordine."""
	text = _PAROLA_VALOARE.sub(_stelutePastreazaGhilimele, text)
	text = _PAROLA_OPTIUNE.sub(r"\1***", text)
	text = _PAROLA_URL.sub(r"\1***\2", text)
	text = _PAROLA_URL_CODAT.sub(r"\1***\2", text)
	text = _PAROLA_URL_GOL.sub(r"\1***\2", text)
	text = _PAROLA_URL_CALE.sub(r"\1***/", text)
	text = _FLUX_CALE.sub(r"\1***/***", text)
	text = _FLUX_CALE_FARA_SCHEMA.sub(r"\1***/***", text)
	text = _FLUX_CALE_CODAT.sub(r"\1***%2f***", text)
	text = _FLUX_CONT.sub(r"\1***:***@", text)
	text = _FLUX_CONT_CODAT.sub(r"\1***%3a***\2", text)
	text = _FLUX_PARAMETRU.sub(r"\1***", text)
	text = _FLUX_PARAMETRU_CODAT.sub(r"\1***", text)
	text = _PAROLA_LINIE.sub(r"\1***", text)
	text = _PAROLA_PRIETEN.sub(r"\1***", text)
	text = _PAROLA_ANTET.sub(r"\1***", text)
	text = _PAROLA_SISTEM.sub(r"\1***\2", text)
	text = _PAROLA_SAMBA.sub(r"\1***\2", text)
	return text


def _parolaLimbi(text):
	"""Eticheta tradusa a unei parole (ecranele in alte limbi: Passwort, Mot de passe, Haslo ...)."""
	randuri = []
	for rand in text.split("\n"):
		m = _ATRIBUIRE.match(rand)
		# o cale (mainmenu/password_setup.png, intr-o lista de fisiere) nu e eticheta unei parole
		if m and "/" not in m.group(1) and _PAROLA_LIMBI.search("".join(c for c in unicodedata.normalize("NFKD", m.group(1))
				if not unicodedata.combining(c))):
			rand = m.group(1) + m.group(2) + "***"
		randuri.append(rand)
	text = "\n".join(randuri)
	return text


RANDURI_LISTA = 40          # cate randuri dintr-o lista (in jurul celui ales)
TEXT_ECRAN_MAX = 4 * 1024 * 1024

_REFERINTA = re.compile(r"^\d+:\d+:[0-9A-Fa-f]+:")
# numele interne din randurile meniurilor (entryID, greutatea): litere mici, cifre, _ . -, fara spatii
_ID_INTERN = re.compile(r"^[a-z0-9_.-]+$")
# atributele cu numele unui rand facut dintr-un obiect
_ATRIBUTE_TEXT = ("titlu", "nume", "text", "name", "title", "eticheta")


def _jurnal(text):
	print("[HdsAsistentaControl] %s" % text)


def N_(text):
	"""Marcaj pentru catalog; traducerea se face cand mesajul este afisat."""
	return text


TEXT_OPRESTE_INTERFATA = N_("Oprește asistența de la distanță înainte să deschizi interfața web a modulului. "
	"O poți porni din nou după ce închizi pagina.")


def asistentaActiva():
	"""Cat poate pleca ceva spre echipa. Dupa Oprește (SE_OPRESTE) nu mai pleaca nimic: un raspuns facut dupa oprire se
	arunca (HdsAsistenta.Sesiune._trimite_raspuns si _ceruta_raspuns), deci omul poate scrie parola imediat, fara sa
	astepte cererea serverului care se mai incheie."""
	from Components import HdsAsistenta
	sesiune = HdsAsistenta.sesiune()
	return sesiune is not None and sesiune.activa()


def _sesiuneInterfata():
	"""Sesiunea enigma2 pentru campurile care nu-si stiu ecranul (Input fara hdsSession, ConfigPassword in afara
	unei liste): mesajul trebuie sa apara, nu doar tasta sa fie oprita."""
	try:
		from Screens.HdsAsistentaSemn import _session
		return _session()
	except Exception:
		return None


def cereOprirePentruSecret(session=None):
	"""Asistenta nu opreste lucrul omului si nu ascunde campuri."""
	return False


_CONT = re.compile(r"(?i)(?:^|[._\s-])(?:user(?:name)?|usr|uname|login|utilizator)(?:[0-9]*$|[._\s-])|nume\s+de\s+utilizator")
# Etichetele ecranelor sunt traduse: parola si numele de utilizator in limbile imaginii (dupa scoaterea diacriticelor),
# si cheile lipite fara despartitor (httpuser, httppwd din sectiunea [webif] a modulelor de acces).
_PAROLA_LIMBI = re.compile(r"(?i)passw|pwd(?:\b|[._0-9])|kennwort|mot de passe|contrase|wachtw|has[lł]o|heslo|"
	r"jelszo|lozink|geslo|salasan|adgangskode|losenord|passord|parool|slaptazod|sifre|senha|lykilor|"
	r"парол|κωδικ|كلمة (?:المرور|السر)")
_CONT_LIMBI = re.compile(r"(?i)user(?:name)?[0-9]*\s*$|benutzer|utilisateur|usuari|utente|gebruiker|uzytkownik|"
	r"uzivatel|felhasznalo|korisni[kc]|uporabni|kayttaja|bruger|anvandar|bruker|kasutaja|naudotoj|lietotaj|"
	r"kullan[ıi]c[ıi]|notand|utilizador|пользовател|"
	r"користувач|корисни|"
	r"χρηστη|مستخدم")


@lru_cache(maxsize=4096)
def _etichetaPrivata(eticheta, cont):
	"""Parola (si, cu cont=True, numele de utilizator) dupa o eticheta in orice limba a imaginii."""
	text = "".join(c for c in unicodedata.normalize("NFKD", eticheta) if not unicodedata.combining(c))
	if _PAROLA_LIMBI.search(text):
		return True
	return bool(cont and (_CONT.search(text) or _CONT_LIMBI.search(text)))


def campSecret(element=None, eticheta="", cont=False):
	"""Asistenta nu opreste lucrul omului si nu ascunde campuri."""
	return False


def _componentaSecreta(comp, nume):
	"""O componenta a ecranului (Label, StaticText) cu valoare privata, dupa marcaj, clasa sau numele ei. Tastele
	colorate (key_red, key_green ...) spun numai ce face tasta: numele lor nu le face secrete."""
	if str(nume).startswith("key_"):
		return campSecret(comp)
	return campSecret(comp, nume, cont=True)


# Eticheta unei parole, in limbile imaginii (dupa scoaterea diacriticelor). campSecret de sus ramane False: pe televizor si
# in web nu se ascunde nimic; ce urmeaza e numai pentru ce pleaca spre echipa (textul ecranului si captura).
_PAROLA_ETICHETA = re.compile(r"(?i)parol|passw|passphrase|(?:^|[._\s])(?:pass|pwd|psk)(?:\b|[._])")


@lru_cache(maxsize=4096)
def _etichetaParola(eticheta):
	text = "".join(c for c in unicodedata.normalize("NFKD", eticheta) if not unicodedata.combining(c))
	return bool(_PAROLA_ETICHETA.search(text) or _PAROLA_LIMBI.search(text))


def campParola(element=None, eticheta=""):
	"""O setare sau un camp cu parola: marcat (hdsSecret), de felul ConfigPassword sau text scris sub o eticheta de parola
	(o alegere Da/Nu cu „parola” in nume nu e o parola)."""
	if getattr(element, "hdsSecret", False) or (element is not None and _elementParola(element)):
		return True
	clase = _clase(element) if element is not None else ()
	return any(n in ("ConfigText", "ConfigSearchText", "Input", "CampText") for n in clase) and _etichetaParola(str(eticheta))


def componentaParola(ecran, comp, nume):
	"""O componenta a ecranului in care se vede o parola scrisa: campul de text al tastaturii de pe ecran sau al unei
	ferestre de scris, cand eticheta lui, numele lui sau titlul ferestrei e al unei parole."""
	if str(nume).startswith("key_"):
		return False
	return campParola(comp, nume) or campParola(comp, _titlu(ecran))


def ecranCuCampSecret(ecran):
	"""Asistenta nu opreste lucrul omului si nu ascunde campuri."""
	return False


def interfataLocalaBlocata(adresa, interfete=None, rezolva=None, verifica_chiar_oprita=False):
	"""Asistenta nu opreste lucrul omului si nu ascunde campuri."""
	return False


# ---------------------------------------------------------------- tastele

def normalizeazaTasta(nume):
	"""(nume, lung) pentru un nume din cerere, sau (None, False) cand nu e in lista alba. ASTEAPTA ramane ASTEAPTA."""
	n = (nume or "").strip().lower()
	lung = False
	if n.endswith(SUFIX_LUNG):
		n = n[:-len(SUFIX_LUNG)]
		lung = True
	if n == ASTEAPTA and not lung:
		return ASTEAPTA, False
	n = ALIASURI.get(n, n)
	if lung and n in TASTE_FARA_LUNG:
		return None, False
	if n in TASTE:
		return n, lung
	return None, False


def imparteTaste(text):
	"""(lista [(nume, lung)], greseli): tastele unei cereri ("menu jos jos ok"); greseli = numele necunoscute."""
	lista, greseli = [], []
	for bucata in (text or "").split():
		nume, lung = normalizeazaTasta(bucata)
		if nume is None:
			greseli.append(bucata)
		else:
			lista.append((nume, lung))
	return lista, greseli


# cate taste ale echipei (op taste, op text) se livreaza acum: fereastra mesajului echipei (Screens/HdsAnuntRetea), care se
# ascunde la prima tasta a omului, nu se ascunde la ele (tastaDeLaEchipa)
_tasteEchipa = [0]


def tastaDeLaEchipa():
	"""True cat se livreaza o tasta trimisa de echipa (apasaTasta): inject trece prin eActionMap pe loc, pe acelasi fir."""
	return _tasteEchipa[0] > 0


def apasaTasta(cod, lung=False):
	"""Tasta ca de pe telecomanda receptorului: scurta prin eRCMapper.inject (dispozitivul nativ, deci legaturile
	keymap.xml ale telecomenzii); lunga (si scurta fara eRCMapper) prin harta de actiuni, cu faza lunga data direct, la
	fel ca interfata web (_apasa).
	Cat se livreaza, tastaDeLaEchipa() spune ca nu e a omului."""
	_tasteEchipa[0] += 1
	try:
		_apasa(cod, lung)
	finally:
		_tasteEchipa[0] -= 1


def _apasa(cod, lung):
	"""Scurta: apasarea si eliberarea prin eRCMapper.inject (drumul telecomenzii). Lunga: apasarea, faza lunga (3) si
	eliberarea direct in harta de actiuni, ca /api/remotecontrol din interfata web (HdsWebControl/plugin.py _trimiteTasta)
	si ca interfata web OE-Alliance cu type=long; cele 5 repetari injectate deodata nu dadeau faza lunga (AS153: green_m,
	4x green_r, green_b, fara green_l), iar faza 3 data direct a pornit actiunea lunga pe V20 (LNG0, 25.11.2026)."""
	if not lung:
		try:
			from enigma import eRCMapper
			m = eRCMapper.getInstance()
		except Exception:
			m = None
		if m is not None:
			m.inject(cod, 0)
			m.inject(cod, 1)
			return
	from enigma import eActionMap
	harta = eActionMap.getInstance()
	dispozitiv = "dreambox advanced remote control (native)"
	try:
		harta.keyPressed(dispozitiv, cod, 0)
		if lung:
			harta.keyPressed(dispozitiv, cod, 3)
	finally:
		harta.keyPressed(dispozitiv, cod, 1)


# ---------------------------------------------------------------- stiva ecranelor

def stiva(session):
	"""Ecranele deschise, de jos in sus: cele din session.dialog_stack (tupluri (ecran, aratat)) si cel de sus."""
	ecrane = []
	for el in list(getattr(session, "dialog_stack", None) or []):
		d = el[0] if isinstance(el, tuple) else el
		if d is not None:
			ecrane.append(d)
	sus = getattr(session, "current_dialog", None)
	if sus is not None and (not ecrane or ecrane[-1] is not sus):
		ecrane.append(sus)
	return ecrane


def _clase(ecran):
	try:
		return [c.__name__ for c in type(ecran).__mro__]
	except Exception:
		return [type(ecran).__name__]


def _modul(ecran):
	return getattr(type(ecran), "__module__", "") or ""


def _elementParola(element):
	return any(n in CAMPURI_PAROLA for n in _clase(element))


def _intrariConfig(ecran):
	"""Intrarile listelor de setari ale ecranului (ConfigList: tupluri (eticheta, element[, ajutor]))."""
	gasite = []
	try:
		componente = list(ecran.values())
	except Exception:
		return gasite
	for comp in componente:
		lista = getattr(comp, "list", None)
		if not isinstance(lista, (list, tuple)):
			continue
		for e in lista:
			if isinstance(e, (list, tuple)) and len(e) >= 2 and _esteElement(e[1]):
				gasite.append(e)
	return gasite


def _esteElement(x):
	return hasattr(x, "getText") and hasattr(x, "value") and not isinstance(x, (str, bytes))


# ---------------------------------------------------------------- textul ecranului

def _titlu(ecran):
	try:
		t = ecran.getTitle()
		if t:
			return str(t)
	except Exception:
		pass
	try:
		t = ecran["Title"].text
		if t:
			return str(t)
	except Exception:
		pass
	return ""


def _text(comp):
	"""Textul unei componente cu text (StaticText, Label, ScrollLabel, Button, Input), sau None."""
	for nume in ("getText",):
		f = getattr(comp, nume, None)
		if callable(f):
			try:
				t = f()
			except Exception:
				return None
			return t if isinstance(t, str) else None
	t = getattr(comp, "text", None)
	return t if isinstance(t, str) else None


def _textRand(e, adancime=0):
	"""Textul unui rand dintr-o lista oarecare: sirurile din el (fara referinte de canal, cai), cel mult trei."""
	if isinstance(e, str):
		return e
	parti = []

	def culege(x, ad):
		if len(parti) >= 3 or ad > 3:
			return
		if isinstance(x, str):
			s = x.strip()
			# dupa primul text, fara numele interne (hds_scanare, 15): nu spun nimic omului din echipa
			if parti and _ID_INTERN.match(s):
				return
			if s and not s.startswith("/") and not _REFERINTA.match(s) and len(s) <= 200 and s not in parti:
				parti.append(s)
		elif isinstance(x, (list, tuple)):
			for y in x:
				culege(y, ad + 1)
		elif x is not None and not isinstance(x, (int, float, bool, bytes)):
			# un rand facut dintr-un obiect (cautarea setarilor, listele noastre): numele lui
			for nume in _ATRIBUTE_TEXT:
				v = getattr(x, nume, None)
				if isinstance(v, str) and v.strip():
					culege(v, ad + 1)
					break
	culege(e, adancime)
	return " | ".join(parti)


def _valoare(element):
	if _elementParola(element):
		return str(getattr(element, "value", ""))
	try:
		v = element.getText()
	except Exception:
		try:
			v = str(element.value)
		except Exception:
			v = "?"
	return v if isinstance(v, str) else str(v)


def _indexAles(comp):
	for nume in ("getCurrentIndex", "getSelectedIndex", "getIndex"):
		f = getattr(comp, nume, None)
		if callable(f):
			try:
				i = f()
				if isinstance(i, int):
					return i
			except Exception:
				pass
	i = getattr(comp, "index", None)
	return i if isinstance(i, int) else None


def _randuriLista(nume, comp):
	lista = getattr(comp, "list", None)
	if not isinstance(lista, (list, tuple)) or not lista:
		return None
	ales = _indexAles(comp)
	n = len(lista)
	inceput = 0
	if ales is not None and ales >= RANDURI_LISTA // 3:
		inceput = max(0, min(ales - RANDURI_LISTA // 3, n - RANDURI_LISTA))
	sfarsit = min(n, inceput + RANDURI_LISTA)
	randuri = ['Lista "%s" (rândul %s din %d):' % (nume, (ales + 1) if ales is not None else "?", n)]
	for i in range(inceput, sfarsit):
		e = lista[i]
		semn = ">" if i == ales else " "
		if isinstance(e, (list, tuple)) and len(e) >= 2 and _esteElement(e[1]):
			valoare = "***" if campParola(e[1], e[0]) else _valoare(e[1])
			rand = "%s [%d] %s = %s" % (semn, i + 1, e[0], valoare)
			if i == ales and len(e) > 2 and isinstance(e[2], str) and e[2].strip():
				rand += "\n      ajutor: " + e[2].strip()
		else:
			rand = "%s [%d] %s" % (semn, i + 1, _textRand(e))
		randuri.append(rand)
	if sfarsit < n:
		randuri.append("  ... încă %d rânduri" % (n - sfarsit))
	return randuri


# flagurile unei referinte de serviciu (lib/service/iservice.h)
_FLAG_DOSAR = 7          # isDirectory | mustDescent | canDescent
_FLAG_MARCAJ = 64        # isMarker
_FLAG_ASCUNS = 512       # isInvisible


def _cheieServiciu(ref):
	f = getattr(ref, "toCompareString", None) or getattr(ref, "toString", None)
	try:
		return f() if callable(f) else ""
	except Exception:
		return ""


def _numeServiciu(ref, centru):
	nume = ""
	try:
		nume = ref.getName() or ""
		if not nume:
			info = centru.info(ref)
			nume = (info.getName(ref) if info is not None else "") or ""
	except Exception:
		pass
	# semnele de evidentiere din numele de canal (0x86/0x87, in UTF-8 C2 86 / C2 87)
	for semn in ("\xc2\x86", "\xc2\x87", "\x86", "\x87"):
		nume = nume.replace(semn, "")
	return " ".join(nume.split())


def _randuriServicii(nume, comp):
	"""Lista de canale sau de buchete (Components/ServiceList: eListbox cu eListboxServiceContent, fara lista Python):
	numele din radacina ei, cu randul ales, fara referinte. None cand comp nu e o lista de servicii."""
	f = getattr(comp, "getRootServices", None)
	if not callable(f) or not callable(getattr(comp, "getCurrent", None)):
		return None
	try:
		from enigma import eServiceCenter, eServiceReference
		centru = eServiceCenter.getInstance()
		root = getattr(comp, "getRoot", lambda: None)()
		adaugate = getattr(comp, "hdsAdaugate", None)
		if root is not None and "FROM SATELLITES" in (root.getPath() or "") and isinstance(adaugate, list):
			# Satelitii sunt numiti si grupati pe TV; recitirea radacinii da dosare brute fara nume.
			refs = list(adaugate)
		else:
			refs = [eServiceReference(s) for s in f()]
		curent = comp.getCurrent()
		ales_cheie = _cheieServiciu(curent) if curent is not None and curent.valid() else ""
	except Exception as e:
		_jurnal("lista de canale: %s" % e)
		return None
	randuri = []
	ales = None
	for ref in refs:
		flags = getattr(ref, "flags", 0) or 0
		if flags & _FLAG_ASCUNS:
			continue
		n = _numeServiciu(ref, centru) or "(fără nume)"
		if flags & _FLAG_MARCAJ:
			n = "--- %s ---" % n
		elif (flags & _FLAG_DOSAR) == _FLAG_DOSAR:
			n += " (buchet)"
		if ales is None and ales_cheie and _cheieServiciu(ref) == ales_cheie:
			ales = len(randuri)
		randuri.append(n)
	if not randuri:
		return ['Lista "%s": goală' % nume]
	n = len(randuri)
	inceput = 0
	if ales is not None and ales >= RANDURI_LISTA // 3:
		inceput = max(0, min(ales - RANDURI_LISTA // 3, n - RANDURI_LISTA))
	sfarsit = min(n, inceput + RANDURI_LISTA)
	rez = ['Lista "%s" (rândul %s din %d):' % (nume, (ales + 1) if ales is not None else "?", n)]
	for i in range(inceput, sfarsit):
		rez.append("%s [%d] %s" % (">" if i == ales else " ", i + 1, randuri[i]))
	if sfarsit < n:
		rez.append("  ... încă %d rânduri" % (n - sfarsit))
	return rez


def textEcran(ecrane, mod_ascii=False, ssh_deschis=False):
	"""Textul ecranului de sus, pentru echipa: stiva (clasele si titlurile), listele cu randul ales, setarile
	"eticheta = valoare", textele si tastele colorate, la fel cum se vad pe televizor. `ssh_deschis` ramane in
	semnatura pentru apelurile de dinainte (nu mai schimba nimic)."""
	if not ecrane:
		return "(niciun ecran deschis)"
	cap = []
	for e in ecrane:
		t = _titlu(e)
		cap.append('%s "%s"' % (type(e).__name__, t) if t else type(e).__name__)
	sus = ecrane[-1]
	parti = ["Ecrane: " + " > ".join(cap),
		"Sus: %s (%s)" % (type(sus).__name__, _modul(sus)),
		"Tastatura: " + ("câmp de text deschis (scrii cu op text)" if mod_ascii else "telecomanda")]
	parti.extend(_randuriDedesubt(ecrane))
	texte, taste, liste = [], [], []
	try:
		componente = list(sus.items())
	except Exception:
		componente = []
	for nume, comp in componente:
		if nume == "Title":
			continue
		r = _randuriLista(nume, comp)
		if r is None:
			r = _randuriServicii(nume, comp)
		if r is not None:
			liste.extend(r)
			continue
		t = _text(comp)
		if t is None or not t.strip():
			continue
		if componentaParola(sus, comp, nume):
			texte.append("  %s: ***" % nume)
			continue
		t = mascheazaSecrete(t)
		t = " ".join(t.split()) if len(t) < 300 else t.strip()
		if nume.startswith("key_"):
			taste.append("%s=%s" % (nume[4:], t))
		else:
			texte.append("  %s: %s" % (nume, t))
	parti.extend(liste)
	if texte:
		parti.append("Texte:")
		parti.extend(texte)
	if taste:
		parti.append("Taste: " + " | ".join(taste))
	text = "\n".join(parti)
	if len(text) > TEXT_ECRAN_MAX:
		text = text[:TEXT_ECRAN_MAX] + "\n... (taiat)"
	return mascheazaSecrete(text)


TEXT_DEDESUBT_MAX = 65536


def _randuriDedesubt(ecrane):
	"""HDSatelit 0.7.6 (ASF, asistenta 222923): "Ecrane:" da numai numele ferestrelor de dedesubt. Pentru cele ramase sub
	InfoBar (deschise de un plugin inaintea lui, la pornire) si pentru orice MessageBox de dedesubt, un rand cu titlul,
	modulul si textul, ca echipa sa afle ce scrie in ele fara sa apese taste (la 222923: MessageBox "Eroare" sub InfoBar)."""
	jos = ecrane[:-1]
	clase = [_clase(e) for e in jos]
	sus_infobar = next((i for i, c in enumerate(clase) if "InfoBar" in c), None)
	randuri = []
	for i, e in enumerate(jos):
		if "InfoBar" in clase[i]:
			continue
		if not ((sus_infobar is not None and i < sus_infobar) or "MessageBox" in clase[i]):
			continue
		text = ""
		for nume in ("text", "Text"):
			try:
				comp = e[nume]
			except Exception:
				continue
			text = _text(comp) or ""
			if text.strip():
				break
		t = _titlu(e)
		r = "Dedesubt: %s (%s)" % ('%s "%s"' % (type(e).__name__, t) if t else type(e).__name__, _modul(e))
		text = " ".join(mascheazaSecrete(text).split()) if text != "[ascuns]" else text
		if text:
			r += ": " + (text if len(text) <= TEXT_DEDESUBT_MAX else text[:TEXT_DEDESUBT_MAX] + "...")
		randuri.append(r)
	return randuri


def _instanteComponenta(ecran, comp):
	instanta = getattr(comp, "instance", None)
	if instanta is not None:
		return [instanta]
	return [r.instance for r in getattr(ecran, "renderer", ())
		if _dinSursa(r, comp) and getattr(r, "instance", None) is not None]


def _dinSursa(renderer, comp):
	"""True cand renderer-ul deseneaza comp, direct sau prin convertori (renderer -> convertor -> ... -> sursa)."""
	s = getattr(renderer, "source", None)
	for _ in range(8):
		if s is None:
			return False
		if s is comp:
			return True
		s = getattr(s, "source", None)
	return False


def _desenata(ecran, comp):
	"""False numai cand componenta nu apare deloc pe ecran: fara instance (lipseste din tema) si niciun renderer al
	ecranului nu o deseneaza, nici prin convertori. Ce nu e desenat nu poate da nimic in captura."""
	if getattr(comp, "instance", None) is not None:
		return True
	return any(_dinSursa(r, comp) for r in getattr(ecran, "renderer", ()))


def _randSecret(rand):
	if isinstance(rand, (tuple, list)) and len(rand) >= 2 and _esteElement(rand[1]):
		return campParola(rand[1], rand[0]) or _textCuSecret(str(rand[1].getText()))
	if _textCuSecret(_textRand(rand)):
		return True
	# Listele multi-content pot avea adrese lungi pe care rezumatul textului le omite.
	if isinstance(rand, (tuple, list)):
		return any(_randSecret(x) for x in rand if isinstance(x, (str, tuple, list)))
	return isinstance(rand, str) and _textCuSecret(rand)


def _dreptunghi(instanta):
	p = instanta.getAbsolutePosition()
	s = instanta.size()
	return p.x(), p.y(), s.width(), s.height()


def dreptunghiuriSecrete(ecrane, motive=None):
	"""Zonele parolelor din OSD (numai pentru captura echipei; pe televizor raman in clar). None refuza captura cand pozitia nu poate fi aflata sigur; in `motive` (o lista,
	daca e data) intra atunci ecranul si componenta, ca refuzul sa aiba un motiv in jurnal si la echipa (0.7.5 JRN,
	TODO 12.11 20:36: "captura nu s-a putut face acum" cu EventView deschis, fara niciun rand care sa spuna de ce).
	O componenta banuita numai dupa text, dar nedesenata (lipseste din tema), nu mai opreste captura: ghidul (EventView)
	are si epg_description si FullDescription, iar multe teme il deseneaza numai pe unul; textul ghidului da des peste
	filtru ("Author:", "Key West:", "Turkey:")."""
	def refuz(motiv):
		if motive is not None:
			motive.append(motiv)
		return None
	rez = []
	for ecran in ecrane:
		if getattr(ecran, "shown", True) is False:
			continue
		try:
			componente = list(ecran.items())
		except Exception:
			continue
		for nume, comp in componente:
			lista = getattr(comp, "list", None)
			secrete = [i for i, rand in enumerate(lista or ()) if _randSecret(rand)] \
				if isinstance(lista, (tuple, list)) else []
			secret = componentaParola(ecran, comp, nume)
			marcat = secret
			text = _text(comp)
			if text and mascheazaSecrete(text) != text:
				secret = True
			if not secret and not secrete:
				continue
			instante = _instanteComponenta(ecran, comp)
			if not instante:
				# banuita numai dupa text (ghidul) si nedesenata: nu are ce scapa; un camp marcat (parola, hdsSecret) sau o
				# lista fara pozitie refuza in continuare (lotul a5parole)
				if not marcat and not secrete and not _desenata(ecran, comp):
					continue
				return refuz("%s.%s: pozitia nu se poate afla" % (type(ecran).__name__, nume))
			for instanta in instante:
				try:
					x, y, latime, inaltime = _dreptunghi(instanta)
					if secrete and not secret:
						sus = instanta.getTopIndex()
						rand_inaltime = instanta.getItemHeight()
						if rand_inaltime <= 0:
							return refuz("%s.%s: inaltimea randului necunoscuta" % (type(ecran).__name__, nume))
						for i in secrete:
							pozitie = (i - sus) * rand_inaltime
							if 0 <= pozitie < inaltime:
								# Numai randul cu datele contului; restul meniului ramane vizibil.
								rez.append((x, y + pozitie, latime, min(rand_inaltime, inaltime - pozitie)))
					else:
						rez.append((x, y, latime, inaltime))
				except Exception as e:
					return refuz("%s.%s: %s" % (type(ecran).__name__, nume, type(e).__name__))
	return rez


def navigatorExternPeEcran():
	try:
		from Plugins.Extensions.HdsNavigator import lansator
	except ImportError:
		return False     # imaginea fara navigator: nu are ce pagina sa fie pe ecran
	navigator = lansator.activ()
	return navigator is not None and navigator.stare == lansator.ARATAT


# motivul ultimului refuz al lui curataCapturaEchipa ("" dupa o captura buna): Screens/HdsAsistentaSemn il da echipei
_motiv_captura = [""]


def motivCaptura():
	"""De ce a refuzat curataCapturaEchipa ultima captura ("" cand n-a refuzat)."""
	return _motiv_captura[0]


def _refuzCaptura(motiv):
	_motiv_captura[0] = motiv
	_jurnal("captura refuzata: %s" % motiv)
	return None


def curataCapturaEchipa(octeti, ecrane, marime):
	"""Curata numai copia din RAM trimisa echipei. Nu modifica framebuffer-ul si nu pastreaza captura pe disc.
	La refuz (None) motivul e in jurnalul interfetei si in motivCaptura()."""
	_motiv_captura[0] = ""
	motive = []
	zone = dreptunghiuriSecrete(ecrane, motive)
	if zone is None:
		return _refuzCaptura("camp cu date private fara pozitie sigura (%s)" % (motive[0] if motive else "?"))
	if not zone:
		return octeti
	try:
		import io
		import math
		from PIL import Image, ImageDraw
		with Image.open(io.BytesIO(octeti)) as sursa:
			imagine = sursa.convert("RGB")
		latime, inaltime = marime
		if latime <= 0 or inaltime <= 0:
			return _refuzCaptura("marimea ecranului necunoscuta")
		sx, sy = imagine.width / float(latime), imagine.height / float(inaltime)
		desen = ImageDraw.Draw(imagine)
		for x, y, w, h in zone:
			if w <= 0 or h <= 0:
				return _refuzCaptura("camp cu date private de marime 0")
			# Acoperim si doua blocuri JPEG MCU de 16 pixeli, ca nici contururile cromatice sa nu ramana.
			x0, y0 = max(0, math.floor(x * sx) - 32), max(0, math.floor(y * sy) - 32)
			x1, y1 = min(imagine.width, math.ceil((x + w) * sx) + 32), min(imagine.height, math.ceil((y + h) * sy) + 32)
			if x1 > x0 and y1 > y0:
				desen.rectangle((x0, y0, x1 - 1, y1 - 1), fill=(20, 28, 40))
		iesire = io.BytesIO()
		imagine.save(iesire, format="PNG")
		return iesire.getvalue()
	except Exception as e:
		return _refuzCaptura("acoperirea campurilor private a cazut: %s" % type(e).__name__)


def modAscii():
	try:
		from Components import HdsMouseEcran
		return HdsMouseEcran.modAscii()
	except Exception:
		return False


# ---------------------------------------------------------------- lucrul pe firul enigma2

class PeFir(object):
	"""Lucrul cerut de firul sesiunii, facut pe firul enigma2. lucru(gata) ruleaza pe firul principal si cheama
	gata(rezultat) o singura data, pe loc sau mai tarziu (din eTimer). trezeste(f): pune f pe firul principal
	(reactor.callFromThread); fara el, coada o goleste numai ceasul controlerului (goleste)."""

	def __init__(self, trezeste=None):
		self._coada = []
		self._lacat = threading.Lock()
		self._trezeste = trezeste

	def cere(self, lucru, termen_s=30):
		"""Rezultatul lui lucru, sau None dupa termen_s (lucrul scos din coada daca n-a inceput)."""
		ev = threading.Event()
		cutie = []

		def gata(rez):
			if not cutie:
				cutie.append(rez)
				ev.set()
		intrare = (lucru, gata)
		with self._lacat:
			self._coada.append(intrare)
		if self._trezeste is not None:
			try:
				self._trezeste(self.goleste)
			except Exception as e:
				_jurnal("trezire: %r" % (e,))
		if not ev.wait(termen_s):
			with self._lacat:
				if intrare in self._coada:
					self._coada.remove(intrare)
			return None
		return cutie[0]

	def goleste(self):
		"""Pe firul principal: face tot ce asteapta in coada."""
		while True:
			with self._lacat:
				if not self._coada:
					return
				lucru, gata = self._coada.pop(0)
			try:
				lucru(gata)
			except Exception as e:
				_jurnal("lucru: %r" % (e,))
				gata(None)

	def asteapta(self):
		with self._lacat:
			return len(self._coada)


class SirTaste(object):
	"""Tastele unei cereri, apasate pe rand (pas() la fiecare tic de PAUZA_MS, pe firul enigma2), ca de pe telecomanda
	omului, pe orice ecran (fara ecrane private)."""

	def __init__(self, taste, ecrane, apasa=apasaTasta, ssh_deschis=None):
		self.taste = list(taste)
		self.ecrane = ecrane            # functie: stiva de acum
		self.apasa = apasa
		self.trimise = []
		self.oprit = ""
		self._asteapta = 0

	def pas(self):
		"""Un tic: True cat mai sunt de facut, False la sfarsit (sau la oprire)."""
		if self._asteapta > 0:
			self._asteapta -= 1
			return True
		if not self.taste:
			return False
		nume, lung = self.taste.pop(0)
		if nume == ASTEAPTA:
			self._asteapta = max(0, ASTEAPTA_MS // PAUZA_MS - 1)
			self.trimise.append(ASTEAPTA)
			return True
		self.apasa(TASTE[nume], lung)
		self.trimise.append(nume + (SUFIX_LUNG if lung else ""))
		return bool(self.taste)


# ---------------------------------------------------------------- scrierea textului

def scrieText(ecrane, text, mod_ascii, scrie, ssh_deschis=False):
	"""(cod, mesaj): scrie text in campul deschis pe ecranul de sus. scrie(text) -> rezultatul lui
	HdsMouseEcran.MouseEcran.text (semnele, prin actiunea gotAsciiCode a ecranului). Refuzat numai cand nu e niciun camp
	de text deschis."""
	if not ecrane:
		return 1, "(niciun ecran deschis)"
	if not mod_ascii:
		return 1, "(niciun câmp de text deschis: deschide-l întâi, de pilda cu OK pe rand)"
	text = text or ""
	semne = 0
	for i in range(0, len(text), 64):
		rez = scrie(text[i:i + 64]) or {}
		if rez.get("facut") != "text":
			return 1, "(campul nu a primit textul: %s)" % rez.get("facut", "nimic")
		semne += int(rez.get("semne") or 0)
	return 0, "scrise %d semne" % semne


def asteptareTaste(n):
	"""Cat poate dura un sir de n taste pe receptor, cu linistea de la sfarsit (pentru termenul cererii)."""
	return (n * max(PAUZA_MS, ASTEAPTA_MS) + LINISTE_MS) / 1000.0 + 10


def acum():
	return time.monotonic()


# ---------------------------------------------------------------- scrierea directa a unei setari (op "setare-scrie")

# ASZ6 (REGULA 0, 22.11.2026): orice cheie config se scrie, oricat de adanca; fara listele de prefixe si de chei
# oprite de pana acum (SETARI_SCRIERE, SETARI_OPRITE; AS91, AS94)
_CHEIE = re.compile(r"^config(\.[^.\x00-\x20=]+)+\Z")


def cheieScriere(cheie):
	"""Orice cheie config valida se poate scrie."""
	return "" if isinstance(cheie, str) and _CHEIE.fullmatch(cheie) else "cheie rea"


def elementSetare(radacina, cheie):
	"""Elementul de setari pentru cheie ("config.av.videomode.HDMI"), urmand atributele si indicii (config.Nims.0...),
	sau None."""
	obj = radacina
	for parte in cheie.split(".")[1:]:
		try:
			if parte.isdigit():
				obj = obj[int(parte)]
			else:
				obj = getattr(obj, parte)
		except Exception:
			return None
	return obj if _esteElement(obj) and hasattr(obj, "save") else None


def scrieSetare(radacina, cheie, valoare, salveaza=None, dupa=None):
	"""(cod, mesaj): pune valoarea (din text, ca in fisierul settings) pe elementul cheii, cu efectele lui (notificarile
	elementului), il salveaza si salveaza fisierul (salveaza(): configfile.save). dupa(cheie): ce mai trebuie facut dupa
	schimbare (la tunere, actualizarea lor, ca din meniu)."""
	motiv = cheieScriere(cheie)
	if motiv:
		return 1, "(%s: %s)" % (motiv, cheie)
	el = elementSetare(radacina, cheie)
	if el is None:
		return 1, "(setare necunoscuta: %s)" % cheie
	vechi = _valoare(el)
	rand = "%s=%s" % (cheie, vechi)
	if "***" in str(valoare) and (_elementParola(el) or mascheazaParole(rand) != rand):
		# valoarea citita de echipa e mascata; scrisa inapoi ar sterge parola omului
		return 1, "(valoarea are *** in locul parolei: %s)" % cheie
	try:
		nou = el.fromstring(valoare) if hasattr(el, "fromstring") else valoare
		el.value = nou
	except Exception as e:
		return 1, "(valoare respinsa pentru %s: %s)" % (cheie, type(e).__name__)
	try:
		el.save()
		if salveaza is not None:
			salveaza()
	except Exception as e:
		return 1, "(nu s-a putut salva %s: %s)" % (cheie, type(e).__name__)
	if dupa is not None:
		try:
			dupa(cheie)
		except Exception as e:
			_jurnal("dupa %s: %r" % (cheie, e))
	return 0, "%s: %s -> %s" % (cheie, vechi, _valoare(el))


# ---------------------------------------------------------------- pachetele din feedurile noastre (instaleaza)

# ASZ6 (REGULA 0): orice nume pe care il primeste opkg (cu + ~ _ si litere mari), fara spatii; prezenta in feedul
# nostru se verifica separat, numai ca sa stim daca trebuie opkg update
PACHET_INSTALARE = re.compile(r"^[^\x00-\x20\x7f]+\Z")
PACHET = PACHET_INSTALARE
# feedurile imaginii (stb.hdsatelit.com) si al pluginurilor si modulelor (Monea Software, moneasoftware.com)
GAZDE_NOASTRE = ("stb.hdsatelit.com", "feed.hdsatelit.com", "moneasoftware.com")
_SRC = re.compile(r"^\s*src(?:/gz)?\s+(\S+)\s+(\S+)")


def feeduriNoastre(dosar="/etc/opkg"):
	"""Numele surselor opkg ale feedurilor noastre (adresa pe una din GAZDE_NOASTRE)."""
	nume = []
	try:
		fisiere = sorted(os.listdir(dosar))
	except Exception:
		return nume
	for f in fisiere:
		if not f.endswith(".conf"):
			continue
		try:
			with open(os.path.join(dosar, f), encoding="utf-8", errors="replace") as h:
				for rand in h:
					m = _SRC.match(rand)
					if m:
						gazda = urlsplit(m.group(2)).hostname
						if gazda:
							nume.append(m.group(1))
		except Exception:
			continue
	return nume


def pachetInFeed(pachet, feeduri, liste="/var/lib/opkg/lists"):
	"""True daca pachetul e in indexul (descarcat de opkg update) al unuia dintre feedurile noastre."""
	semn = "Package: %s\n" % pachet
	for f in feeduri:
		try:
			with open(os.path.join(liste, f), encoding="utf-8", errors="replace") as h:
				if semn in h.read() + "\n":
					return True
		except Exception:
			continue
	return False


# ---------------------------------------------------------------- transponderele din lamedb (citire)

def transpondere(text_lamedb, namespace=None, maxim=1500):
	"""Transponderele din lamedb, cu numele canalelor grupate dupa namespace, TSID si ONID."""
	canale = {}
	linii = (text_lamedb or "").splitlines()
	try:
		i = linii.index("services") + 1
	except ValueError:
		i = len(linii)
	while i + 2 < len(linii) and linii[i].strip() != "end":
		cheie = linii[i].strip().split(":")
		nume = " ".join(linii[i + 1].split())[:200]
		i += 3
		try:
			tp = tuple(int(v, 16) for v in cheie[1:4])
			if len(tp) == 3 and nume:
				canale.setdefault(tp, []).append(nume)
		except ValueError:
			continue
	randuri = []
	sectiune = False
	cap = None
	ns = namespace.lower().lstrip("0") if namespace else None
	for rand in linii:
		r = rand.strip()
		if r == "transponders":
			sectiune = True
			continue
		if not sectiune:
			continue
		if r == "end":
			break
		if r == "/":
			cap = None
			continue
		if cap is None:
			cap = r
			continue
		if ns is not None and cap.split(":")[0].lower().lstrip("0") != ns:
			continue
		randuri.append("%s  %s" % (cap, r))
		try:
			nume = canale.get(tuple(int(v, 16) for v in cap.split(":")), [])
		except ValueError:
			nume = []
		if nume:
			randuri[-1] += "  | Canale: " + ", ".join(nume)
		if len(randuri) >= maxim:
			randuri.append("... (taiat la %d)" % maxim)
			break
	return "\n".join(randuri) or "(niciun transponder)"
