# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsVpn.py: VPN pe receptor. O singura logica pentru ecranul de pe televizor (Screens/HdsVpn.py, Setari > Retea &
# Internet > VPN) si pentru pagina web /vpn (Plugins/Extensions/HdsWebControl/vpn_web.py).
#
# Furnizorii: HMA (HideMyAss) si orice alt furnizor OpenVPN, cu fisierele .ovpn ale omului si cu numele si parola
# contului; WireGuard, cu fisierul .conf al omului. Lista serverelor HMA se face din fisierele HMA importate (cate unul
# pe server): imaginea nu are o lista a lor (nu e publica si se schimba).
#
# Programele: openvpn (pachetul openvpn, cu tun.ko din kernel-module-tun-<nucleu>) si wg (wireguard-tools); nucleul are
# WireGuard in el. Cand lipsesc, instaleaza() scrie /etc/opkg/hdsatelit-extensii.conf (feedul de extensii HD Satelit al
# bazei: https://stb.hdsatelit.com/extensii/<canal>/<baza>/<arh>, fara parola in adresa), apoi opkg update si opkg
# install. Adresa nu se potriveste cu feedul actualizarilor (HdsActualizari._ADRESA_FEED), deci pachetele de aici nu
# intra in planul de actualizare.
#
# Datele: DOSAR (/etc/hdsatelit-vpn, 0700), in afara lui /etc/enigma2: copia setarilor nu le ia, deci numele, parola si
# cheile nu ajung in nicio copie. Acolo: cont (numele si parola, 0600, citit de openvpn cu --auth-user-pass), profiluri/
# (copiile curatate ale fisierelor, 0600; cheia privata WireGuard sta numai aici), profiluri.json (lista lor, fara
# secrete) si setari.json. Numele si parola nu se arata niciodata inapoi (starea spune numai daca sunt salvate) si nu
# intra in jurnal: jurnal() trece totul prin ascunde().
#
# Fisierele de la om: OpenVPN pe o lista ALBA de directive (PERMISE); cele care pornesc programe, deschid receptorul in
# retea sau citesc si scriu fisiere sunt refuzate cu numele lor (REFUZATE), cele de rutare si DNS sunt lasate deoparte
# (IGNORATE: le decide receptorul), cele necunoscute sunt refuzate. Certificatele si cheile de alaturi (din acelasi
# import, numai dupa numele simplu) se pun in linie. WireGuard: PreUp, PostUp, PreDown si PostDown sunt refuzate.
#
# Rutarea (nucleul 4.4 nu are iptables de niciun fel; are reguli de rutare): tot traficul prin VPN cu
#   PRIO_SERVER  to <serverul VPN>/32 lookup main      (legatura VPN iese pe placa de retea)
#   PRIO_CASA    lookup main suppress_prefixlength 0   (reteaua din casa ramane mereu pe placa de retea)
#   PRIO_TOT     lookup TABELA                          (restul prin VPN)
# iar in TABELA ruta implicita prin interfata VPN si, cu oprirea totala, "unreachable default" (metrica mai mare): la
# caderea VPN-ului nu mai iese nimic in internet, in afara de legatura spre server. Modul "ales" pune in locul lui
# PRIO_TOT cate o regula "to <ip>/32 lookup TABELA" pentru gazdele IPTV din buchete si adresele scrise de om. IPv6 nu are
# reguli in acest nucleu: cu tot traficul prin VPN, internetul IPv6 se opreste (unreachable 2000::/3).
# DNS: resolv.conf cu DNS-ul dat de server (sau DNS_REZERVA, prin tunel); cel de dinainte se pune la loc la oprire.
#
# Pornirea: openvpn porneste in sesiunea lui (nu moare cu interfata), cu --route-noexec si cu scripturile noastre
# --up/--down (acest fisier, ca program: openvpn-sus, openvpn-jos), --writepid si --management pe un soclu unix din
# DOSAR_RULARE (0700). La o repornire a interfetei porneste() gaseste procesul si il urmareste mai departe.
# Paza (un fir): starea legaturii la cateva secunde, DNS-ul pus din nou daca l-a schimbat altcineva, adresele modului
# "ales" improspatate, repornirea dupa o cadere (10, 30, 60 s, apoi la 5 minute), oprirea la nume sau parola gresite.
# Lipsa stiuta: intre pornirea receptorului si pornirea interfetei nu exista reguli.
#
# Modul "navigator" (numai navigatorul web si aplicatiile HbbTV prin VPN; nucleul n-are iptables si nici veth): un
# namespace de retea NETNS cu numai interfata VPN in el. WireGuard: interfata se face in namespace-ul de baza (acolo
# ramane socketul UDP, deci legatura criptata iese pe placa de retea) si apoi se muta in NETNS. OpenVPN: procesul ramane
# in namespace-ul de baza, iar scriptul --up muta interfata tun in NETNS si o configureaza acolo (--ifconfig-noexec,
# fara --persist-tun, cu --up-restart: la fiecare reconectare interfata se muta din nou). Ruta implicita si DNS-ul
# (/etc/netns/<NETNS>/resolv.conf, pus de ip netns exec peste /etc/resolv.conf) sunt numai in NETNS; namespace-ul de
# baza nu se atinge (nicio regula, resolv.conf neschimbat). Navigatorul (Plugins/Extensions/HdsNavigator/lansator.py)
# porneste prin prefixNavigator() = ip netns exec NETNS, numai cand VPN-ul e pornit de om in acest mod; altfel ca
# inainte. Cat VPN-ul e cerut, NETNS exista si fara tunel: navigatorul nu iese direct pe internet (oprire totala
# implicita). Interfata camului (127.0.0.1) ramane in afara: TCP local nu trece dintr-un namespace in altul.
#
# Celelalte protocoale (FELURI), in aceeasi forma (profil importat, datele de acces 0600 neafisate, lista alba la ce vine
# de la om, aceleasi moduri de rutare, aceeasi paza), fiecare cu interfata lui tun, deci cu aceeasi rutare ca OpenVPN:
#   openconnect  Cisco AnyConnect (si GlobalProtect, Pulse/Juniper, Fortinet, F5, Array prin --protocol): adresa https
#                a serverului; parola numai prin stdin (--passwd-on-stdin); in locul lui vpnc-script porneste acest
#                fisier (openconnect-script), care pune adresa, rutele si DNS-ul ca scriptul --up al lui openvpn.
#   ikev2        strongSwan: charon cu kernel-libipsec (ESP in spatiul utilizatorului, interfata tun ipsec0; merge si
#                pe nucleele fara XFRM_USER/ESP) si swanctl prin soclul vici din DOSAR_RULARE. Configurarea (cu parola
#                ca 0x<hex>, deci nimic din ea nu se poate citi ca sintaxa) se scrie 0600, se incarca si se sterge.
#                Serverul se verifica mereu cu un certificat: cel din import sau autoritatile din sistem. Jurnalul
#                lui charon (/tmp, 0600, golit la fiecare pornire) poate avea numele contului, niciodata parola.
#   shadowsocks  ss-local (numai pe 127.0.0.1) + hev-socks5-tunnel (interfata tun); numai metodele AEAD, fara plugin=.
#   l2tp         L2TP/IPsec: charon in modul transport (cere XFRM_USER si ESP in nucleu) + xl2tpd + pppd.
# Adauga VPN (adaugaVpn): un fisier, mai multe sau un text lipit, recunoscute dupa continut (recunoaste()), ori
# datele scrise de mana; dupa adaugare serverul e ales singur, iar ce lipseste (numele, parola, cheia comuna) se cere
# apoi (campuriLipsa, salveazaSecrete). Datele de acces ale protocoalelor noi stau langa profil (<id>.secret, 0600);
# OpenVPN pastreaza contul comun (cont). Grupurile (furnizorii) au unul sau mai multe feluri; adaugaGrup() lasa
# HdsVpnFurnizori sa-si puna grupurile lui.
#
# FIRUL: stare() citeste numai fisiere mici si starea tinuta de paza (merge pe firul enigma2); tot ce porneste un
# program merge prin LUCRARI (un fir deodata, comun televizorului si paginii web). Fisierul nu importa nimic din enigma2
# la incarcare: probele de pe PC schimba RADACINA, RULATOR, PORNITOR si REZOLVATOR.

import base64
import binascii
import hashlib
import io
import ipaddress
import json
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
import zipfile

# probele de pe PC: radacina in care se lucreaza (pe receptor goala), cine porneste programele si cine rezolva numele
RADACINA = ""
RULATOR = None
REZOLVATOR = None
# probele de pe PC: cine porneste programele care raman pornite (openconnect, charon, ss-local...): fn(argv, mediu,
# intrare) -> un obiect cu pid, poll() si wait()
PORNITOR = None

DOSAR = "/etc/hdsatelit-vpn"
DOSAR_PROFILURI = DOSAR + "/profiluri"
CALE_SETARI = DOSAR + "/setari.json"
CALE_INDEX = DOSAR + "/profiluri.json"
CALE_CONT = DOSAR + "/cont"
DOSAR_RULARE = "/var/run/hds-vpn"
CALE_PLAN = DOSAR_RULARE + "/plan.json"
CALE_SUS = DOSAR_RULARE + "/sus.json"
CALE_PID = DOSAR_RULARE + "/openvpn.pid"
CALE_SOCLU = DOSAR_RULARE + "/openvpn.sock"
CALE_OPRIRE = DOSAR_RULARE + "/oprire"
CALE_RESOLV_INAINTE = DOSAR_RULARE + "/resolv.inainte"
CALE_WG_CONF = DOSAR_RULARE + "/wg.conf"
CALE_RESOLV = "/etc/resolv.conf"
CALE_JURNAL = "/tmp/hds-vpn.log"
CALE_JURNAL_OPENVPN = "/tmp/hds-vpn-openvpn.log"
CALE_JURNAL_OPKG = "/tmp/hds-vpn-opkg.log"
CALE_CONF_EXTENSII = "/etc/opkg/hdsatelit-extensii.conf"
CALE_MODEL = "/etc/hdsatelit-model"
CALE_MONTARI = "/proc/mounts"
DOSAR_BUCHETE = "/etc/enigma2"
CALE_TUN = "/dev/net/tun"

PROGRAM_OPENVPN = "/usr/sbin/openvpn"
PROGRAM_WG = "/usr/bin/wg"
PROGRAM_IP = "/sbin/ip"
PROGRAM_OPKG = "/usr/bin/opkg"
PROGRAM_MODPROBE = "/sbin/modprobe"
PYTHON = "/usr/bin/python3"

# programele protocoalelor noi: prima cale care exista
CAI_PROGRAME = {
	"openconnect": ("/usr/sbin/openconnect", "/usr/bin/openconnect"),
	"charon": ("/usr/libexec/ipsec/charon", "/usr/lib/ipsec/charon"),
	"swanctl": ("/usr/sbin/swanctl", "/usr/bin/swanctl"),
	"ss-local": ("/usr/bin/ss-local", "/usr/sbin/ss-local"),
	"tun2socks": ("/usr/bin/hev-socks5-tunnel", "/usr/sbin/hev-socks5-tunnel"),
	"xl2tpd": ("/usr/sbin/xl2tpd", "/usr/bin/xl2tpd"),
	"pppd": ("/usr/sbin/pppd", "/usr/bin/pppd"),
}
CALE_CA_SISTEM = ("/etc/ssl/certs/ca-certificates.crt", "/etc/pki/tls/certs/ca-bundle.crt")

INTERFATA_OPENVPN = "hdsvpn1"
INTERFATA_WG = "hdsvpn0"
INTERFATA_OC = "hdsvpn2"
INTERFATA_IPSEC = "ipsec0"      # facuta de kernel-libipsec (numele nu se alege)
INTERFATA_PPP = "hdsvpn4"
INTERFATA_SS = "hdsvpn5"
INTERFETE_TUN = (INTERFATA_OPENVPN, INTERFATA_OC, INTERFATA_IPSEC, INTERFATA_PPP, INTERFATA_SS)
PORT_SOCKS = "10805"
ADRESA_TUN_SS = "198.18.0.1"
CALE_JURNAL_PROTOCOL = "/tmp/hds-vpn-%s.log"
TABELA = "51830"
NETNS = "hdsvpn"
CALE_NETNS = "/var/run/netns/" + NETNS
CALE_RESOLV_NETNS = "/etc/netns/" + NETNS + "/resolv.conf"
PROGRAM_CURL = "/usr/bin/curl"
PRIO_SERVER = "11000"
PRIO_CASA = "11010"
PRIO_TOT = "11020"
PRIO_ALES = "11030"
METRICA_BLOCARE = "4000"
RETEA_IPV6_INTERNET = "2000::/3"
DNS_REZERVA = ("1.1.1.1", "9.9.9.9")
# adresa IP vazuta pe internet si tara ei (cerute numai la conectare si la cerere)
SERVICII_IP = ("https://ipinfo.io/json", "https://api.country.is/")
ADRESA_EXTENSII = "https://stb.hdsatelit.com/extensii"
ARHITECTURI_EXTENSII = ("all", "cortexa15hf-neon-vfpv4", "u57", "viper4kv20")
UA = "hdsatelit-receptor/1"

# furnizorii cu fisiere OpenVPN si nume si parola (HMA, cei cu configurare oficiala pentru routere, oricare altul) si
# WireGuard; textele de ajutor spun de unde ia omul datele (cercetarea: vpn/cercetare-logare-furnizori.md)
# pia si mullvad: grupurile serverelor puse de HdsVpnFurnizori (furnizorii fara fisiere, cu contul si tara)
FURNIZORI = ("hma", "nordvpn", "surfshark", "protonvpn", "pia", "openvpn", "wireguard", "mullvad", "ikev2", "openconnect",
	"shadowsocks", "l2tp")
FURNIZORI_SERVICIU = ("nordvpn", "surfshark", "protonvpn")
MODURI = ("navigator", "tot", "ales")
# felurile de VPN; fiecare grup (furnizor) are unul sau mai multe (primul e cel implicit)
FELURI = ("openvpn", "wireguard", "ikev2", "openconnect", "shadowsocks", "l2tp")
FELURI_FISIER = ("openvpn", "wireguard")
_FELURI_GRUP = {"hma": ("openvpn",), "nordvpn": ("openvpn",), "surfshark": ("openvpn",), "protonvpn": ("openvpn",),
	"pia": ("openvpn",), "openvpn": ("openvpn",), "wireguard": ("wireguard",), "mullvad": ("wireguard",), "ikev2": ("ikev2",), "openconnect": ("openconnect",),
	"shadowsocks": ("shadowsocks",), "l2tp": ("l2tp",)}
# grupul fiecarui fel cand fisierul adaugat nu se potriveste cu furnizorul ales
GRUP_FEL = {"openvpn": "openvpn", "wireguard": "wireguard", "ikev2": "ikev2", "openconnect": "openconnect",
	"shadowsocks": "shadowsocks", "l2tp": "l2tp"}
# grupurile puse de alte module (HdsVpnFurnizori): cheie -> {"feluri", "text", "cum"}
_GRUPURI_ADAUGATE = {}
_CHEIE_GRUP = re.compile(r"^[a-z0-9][a-z0-9_\-]{1,23}\Z")

MAX_FISIER = 65536
MAX_ARHIVA = 8 * 1024 * 1024
MAX_MEMBRI = 2000
MAX_PROFILURI = 2000
MAX_ADRESE = 64
MAX_GAZDE_IPTV = 64
MAX_CAMP_CONT = 128
MAX_BLOC = 32768
MAX_JURNAL = 262144

TIMP_PROGRAM_S = 30
TIMP_CONECTARE_S = 45
TIMP_OPKG_UPDATE_S = 300
TIMP_OPKG_INSTALL_S = 900
TIMP_IP_S = 8
PAZA_S = 3
PAZA_GREA_S = 15
CADERE_LUNGA_S = 90
ALES_IMPROSPATARE_S = 600
REPORNIRI_S = (10, 30, 60, 300)

TEXT_RESOLV = "# HD Satelit: DNS-ul VPN-ului (Components/HdsVpn.py); cel de dinainte se pune la loc la oprire\n"


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_), fara efect: textul se traduce la folosire."""
	return text


# ---------------------------------------------------------------- fisiere


def _cale(cale):
	return RADACINA + cale


def _citeste(cale, maxim=MAX_FISIER * 4):
	try:
		with open(_cale(cale), "rb") as f:
			date = f.read(maxim + 1)
	except (OSError, IOError):
		return None
	return date[:maxim].decode("utf-8", "replace")


def _scrieAtomic(cale, date, mod=0o600, fara_radacina=False):
	"""Scrie intr-un fisier temporar din acelasi dosar, fsync, apoi os.replace: ramane fisierul vechi sau cel nou,
	niciodata unul taiat. O_BINARY: pe PC (probele) os.open ar pune altfel CRLF."""
	if not isinstance(date, bytes):
		date = date.encode("utf-8")
	tinta = cale if fara_radacina else _cale(cale)
	tmp = tinta + ".nou"
	fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0), mod)
	try:
		os.write(fd, date)
		os.fsync(fd)
	finally:
		os.close(fd)
	os.chmod(tmp, mod)
	os.replace(tmp, tinta)


def _dosar(cale, mod=0o700):
	c = _cale(cale)
	if not os.path.isdir(c):
		os.makedirs(c, mod)
	try:
		os.chmod(c, mod)
	except OSError:
		pass


def _sterge(cale):
	try:
		os.remove(_cale(cale))
		return True
	except OSError:
		return False


def _citesteJson(cale, maxim=MAX_FISIER * 32):
	text = _citeste(cale, maxim)
	if not text:
		return None
	try:
		return json.loads(text)
	except ValueError:
		return None


# ---------------------------------------------------------------- jurnalul, fara secrete

# textele de ascuns din jurnal (numele si parola contului, puse cand se citesc sau se scriu)
_SECRETE = set()
_BLOC_PEM = re.compile(r"-----BEGIN [^-\n]{1,60}-----.*?(?:-----END [^-\n]{1,60}-----|\Z)", re.S)
_BLOC_IN_LINIE = re.compile(r"<(key|tls-auth|tls-crypt|tls-crypt-v2|secret|auth-user-pass|pkcs12)>.*?(?:</\1>|\Z)",
	re.S | re.I)
_CHEIE_WG_RAND = re.compile(r"(?im)^([ \t]*(?:PrivateKey|PresharedKey)[ \t]*)=.*$")
_SS_URI = re.compile(r"(?i)(?<![A-Za-z0-9])ss://\S+")
_CHEIE_B64 = re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{42}[AEIMQUYcgkosw048]=(?![A-Za-z0-9+/=])")


def ascunde(text, secrete=None):
	"""Textul fara secrete: numele si parola contului, blocurile PEM si cele in linie (key, tls-auth...), cheile
	WireGuard (PrivateKey, PresharedKey si orice cheie de 32 de octeti in base64)."""
	text = "%s" % (text,)
	for s in sorted(set(_SECRETE if secrete is None else secrete), key=len, reverse=True):
		if s and len(s) >= 3:
			text = text.replace(s, "***")
	text = _BLOC_IN_LINIE.sub(lambda m: "<%s>[ascuns]</%s>" % (m.group(1), m.group(1)), text)
	text = _BLOC_PEM.sub("[bloc ascuns]", text)
	text = _CHEIE_WG_RAND.sub(lambda m: m.group(1) + "= ***", text)
	text = _SS_URI.sub("ss://***", text)
	text = _CHEIE_B64.sub("***", text)
	return text


def jurnal(text):
	curat = ascunde(text)
	print("[HdsVpn] %s" % curat[:300])
	try:
		mod = os.O_WRONLY | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
		try:
			mod |= os.O_TRUNC if os.path.getsize(_cale(CALE_JURNAL)) > MAX_JURNAL else os.O_APPEND
		except OSError:
			mod |= os.O_APPEND
		fd = os.open(_cale(CALE_JURNAL), mod, 0o600)
		try:
			os.write(fd, ("%s %s\n" % (time.strftime("%H:%M:%S"), curat[:600])).encode("utf-8", "replace"))
		finally:
			os.close(fd)
	except (OSError, IOError):
		pass


# ---------------------------------------------------------------- programele

def _ruleaza(argv, timeout=TIMP_PROGRAM_S, iesire=None):
	"""(cod, textul iesirii) al programului `argv` (fara shell). `iesire`: un fisier deschis in care merge iesirea."""
	if RULATOR is not None:
		return RULATOR(list(argv), timeout)
	try:
		if iesire is not None:
			p = subprocess.run(list(argv), stdin=subprocess.DEVNULL, stdout=iesire, stderr=subprocess.STDOUT,
				timeout=timeout)
			return p.returncode, ""
		p = subprocess.run(list(argv), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
			timeout=timeout)
		return p.returncode, p.stdout.decode("utf-8", "replace")
	except subprocess.TimeoutExpired:
		return -2, "timeout"
	except OSError as eroare:
		return -1, str(eroare)


def _ip(*argv):
	return _ruleaza([PROGRAM_IP] + list(argv))


def _executabil(cale):
	return os.access(_cale(cale), os.X_OK)


def versiuneNucleu():
	try:
		return os.uname().release
	except AttributeError:
		return "4.4.35"


def areTun():
	"""tun.ko incarcat, pus pe disc sau nodul /dev/net/tun facut (sau tun in nucleu: /sys/class/misc/tun)"""
	return (os.path.exists(_cale(CALE_TUN)) or os.path.isdir(_cale("/sys/module/tun"))
		or os.path.exists(_cale("/sys/class/misc/tun"))
		or os.path.exists(_cale("/lib/modules/%s/kernel/drivers/net/tun.ko" % versiuneNucleu())))


_MODULE_DISC = {}


def _modulPeDisc(nume):
	"""True cand modulul `nume`.ko e pus pe disc sub /lib/modules/<nucleu> (oriunde, si in extra/). Dosarul se citeste o
	data (stare() ajunge aici de multe ori pe secunda, pe firul enigma2); instaleaza() il face sa fie citit din nou."""
	baza = _cale("/lib/modules/%s" % versiuneNucleu())
	if baza not in _MODULE_DISC:
		gasite = set()
		for _d, _sub, fisiere in os.walk(baza):
			gasite.update(f[:-3] for f in fisiere if f.endswith(".ko"))
		_MODULE_DISC.clear()
		_MODULE_DISC[baza] = gasite
	return nume in _MODULE_DISC[baza]


def areWireguardInNucleu():
	return os.path.isdir(_cale("/sys/module/wireguard"))


def wireguardIndisponibil():
	"""True cand nucleul nu are WireGuard acum: nici in el (/sys/module/wireguard, Viper 4K V20, V30, V40), nici ca
	modul pus pe disc (wireguard.ko sub /lib/modules/<nucleu>). Pe celelalte modele modulul vine din feed
	(kernel-module-wireguard-<nucleu>, cerut explicit de pachete("wireguard")); daca feedul nu il are, instalarea
	spune TEXT_WG_INDISPONIBIL."""
	if areWireguardInNucleu():
		return False
	return not _modulPeDisc("wireguard")


TEXT_WG_INDISPONIBIL = N_("WireGuard nu este disponibil pe acest receptor: nucleul lui nu îl are. Folosește un "
	"furnizor OpenVPN.")


def areNetns():
	"""Nucleul are namespace-uri de retea (CONFIG_NET_NS: /proc/self/ns/net). Lipsesc pe Vu+ (Duo 4K, Uno 4K SE, Solo
	4K, Solo SE): acolo modul "navigator" nu se poate, deci nici nu se arata."""
	return os.path.exists(_cale("/proc/self/ns/net"))


_XFRM = {}


def areXfrm():
	"""IPsec in nucleu cu XFRM_USER si ESP (cerut numai de L2TP/IPsec, modul transport): /proc/sys/net/core/xfrm_* plus
	xfrm_user si esp4 incarcate sau puse pe disc; xfrm_user pus in nucleu se afla o data cu `ip xfrm state count`."""
	if not os.path.exists(_cale("/proc/sys/net/core/xfrm_acq_expires")):
		return False
	user = os.path.isdir(_cale("/sys/module/xfrm_user")) or _modulPeDisc("xfrm_user")
	if not user:
		if "user" not in _XFRM:
			_XFRM["user"] = _ruleaza([PROGRAM_IP, "xfrm", "state", "count"], 5)[0] == 0
		user = _XFRM["user"]
	esp = os.path.isdir(_cale("/sys/module/esp4")) or _modulPeDisc("esp4")
	return user and esp


def arePpp():
	return (os.path.exists(_cale("/dev/ppp")) or os.path.isdir(_cale("/sys/module/ppp_generic"))
		or _modulPeDisc("ppp_generic"))


def _program(nume):
	"""Calea programului `nume` (CAI_PROGRAME) daca e pe receptor, altfel ""."""
	for c in CAI_PROGRAME.get(nume, ()):
		if _executabil(c):
			return c
	return ""


def nucleuPoate(fel):
	"""(poate, motivul) pentru felul de VPN pe nucleul acestui receptor, oricare ar fi programele."""
	if fel == "wireguard":
		return True, ""
	if fel == "l2tp":
		# XFRM e in nucleul tuturor modelelor; xfrm_user, esp4 si modulele PPP vin din feed (pachete("l2tp"))
		if not os.path.exists(_cale("/proc/sys/net/core/xfrm_acq_expires")):
			return False, _("L2TP/IPsec nu merge pe acest receptor: nucleul lui nu are IPsec (XFRM și ESP). Folosește "
				"IKEv2, OpenVPN sau WireGuard.")
		return True, ""
	# tun lipsa nu opreste nimic: modulul vine din feed odata cu programele (pachete())
	return True, ""


def programe():
	"""Felurile de VPN care pot porni acum (programele puse si nucleul in stare)."""
	tun = areTun()
	return {"openvpn": _executabil(PROGRAM_OPENVPN) and tun,
		"wireguard": _executabil(PROGRAM_WG) and (areWireguardInNucleu() or _modulPeDisc("wireguard")),
		"openconnect": bool(_program("openconnect")) and tun,
		"ikev2": bool(_program("charon") and _program("swanctl")) and tun,
		"shadowsocks": bool(_program("ss-local") and _program("tun2socks")) and tun,
		"l2tp": bool(_program("xl2tpd") and _program("pppd") and _program("charon") and _program("swanctl")) and
			nucleuPoate("l2tp")[0] and areXfrm() and arePpp()}


# felurile ale caror programe nu sunt inca in feedul de extensii (OpenEmbedded 6.0 nu are retete pentru
# shadowsocks-libev si hev-socks5-tunnel): se arata numai cand programele sunt deja pe receptor, ca omul sa nu primeasca
# o instalare care cade sigur. Cand stratul VPN le are, felul iese de aici.
FELURI_FARA_PACHET = ("shadowsocks",)


def capabil(fel):
	"""("da", "") cand felul poate porni acum, ("instaleaza", textul) cand lipsesc numai programele (vin din feedul de
	extensii), ("nu", motivul) cand nucleul acestui receptor nu il poate rula sau feedul nu are inca programele."""
	poate, motiv = nucleuPoate(fel)
	if not poate:
		return "nu", motiv
	if programe().get(fel):
		return "da", ""
	if fel in FELURI_FARA_PACHET:
		return "nu", _("Programele pentru %s nu sunt încă în feedul de extensii HD Satelit.") % textFel(fel)
	return "instaleaza", textProgrameLipsa(fel)


def felPosibil(fel):
	"""Felul se arata pe acest receptor (in grupuri si la Adauga VPN)."""
	return capabil(fel)[0] != "nu"


def disponibil():
	"""VPN-ul exista pe receptor numai cu programele lui in imagine (openvpn sau wg, din 0.4.0). Aceeasi regula ca
	SystemInfo["HdsVpn"] (Components/SystemInfo.py): intrarea din meniu, pagina web, pornirea din mytest.py si prefixul
	navigatorului. Pe o imagine fara programe (0.3.x) nimic din VPN nu se vede si nu se instaleaza nimic."""
	return _executabil(PROGRAM_OPENVPN) or _executabil(PROGRAM_WG)


def _incarcaFurnizori():
	"""HdsVpnFurnizori (grupurile furnizorilor cu logare) isi pune grupurile cu adaugaGrup() cand se incarca; aici se
	incarca o data, fara sa cada daca lipseste (probele de pe PC, imaginile fara el)."""
	if _GRUPURI_ADAUGATE.get("__incercat"):
		return
	_GRUPURI_ADAUGATE["__incercat"] = True
	try:
		from Components import HdsVpnFurnizori  # noqa: F401
	except Exception as eroare:
		if not isinstance(eroare, ImportError):
			jurnal("HdsVpnFurnizori: %r" % (eroare,))


def adaugaGrup(cheie, text, feluri, cum_iei=""):
	"""Pentru HdsVpnFurnizori: un grup (furnizor) nou sau felurile unuia existent. `text`: numele aratat (tradus de
	cel care il da), `feluri`: felurile primite (primul e cel implicit), `cum_iei`: de unde ia omul datele. True daca
	l-a pus."""
	feluri = tuple(f for f in (feluri or ()) if f in FELURI)
	if not _CHEIE_GRUP.match(cheie or "") or not feluri:
		return False
	_GRUPURI_ADAUGATE[cheie] = {"feluri": feluri, "text": text or cheie, "cum": cum_iei or ""}
	return True


def furnizori():
	"""Cheile tuturor grupurilor, in ordinea din ecran: cele de baza, apoi cele adaugate."""
	_incarcaFurnizori()
	return list(FURNIZORI) + sorted(k for k in _GRUPURI_ADAUGATE if k not in FURNIZORI and not k.startswith("__"))


def grupCunoscut(grup):
	return grup in FURNIZORI or grup in furnizori()


def feluriGrup(grup):
	x = _GRUPURI_ADAUGATE.get(grup)
	if isinstance(x, dict):
		return x["feluri"]
	return _FELURI_GRUP.get(grup, ("openvpn",))


def felFurnizor(furnizor):
	"""Felul implicit al grupului (primul din feluriGrup)."""
	return feluriGrup(furnizor)[0]


def _modulPachet(nume):
	return "kernel-module-%s-%s" % (nume.replace("_", "-"), versiuneNucleu())


def pachete(fel):
	"""Pachetele de instalat pentru un fel de VPN (dependintele, lzo, lz4, libcap-ng, gnutls..., le aduce opkg). Modulele
	nucleului se cer numai cand lipsesc (nici in nucleu, nici pe disc): un pachet de modul care nu e in feed ar opri
	toata instalarea. WireGuard: modulul se cere explicit (instalarea pune --no-install-recommends, iar pe nucleele fara
	WireGuard modulul era numai o recomandare a lui wireguard-tools)."""
	# hds-vpn-nucleu-tun/-ipsec/-ppp: pachetele-umbrela ale stratului VPN, facute pe fiecare masina din .config-ul
	# nucleului ei (aduc numai modulele care lipsesc; goale unde totul e in nucleu, ca tun pe SF8008)
	if fel == "wireguard":
		return ["wireguard-tools"] + ([_modulPachet("wireguard")] if wireguardIndisponibil() else [])
	if fel == "openconnect":
		return ["openconnect", "hds-vpn-nucleu-tun"]
	if fel == "ikev2":
		# kernel-libipsec: ESP in spatiul utilizatorului, prin tun; modulele IPsec ale nucleului nu trebuie
		return ["strongswan", "hds-vpn-nucleu-tun"]
	if fel == "shadowsocks":
		return ["shadowsocks-libev", "hev-socks5-tunnel", "hds-vpn-nucleu-tun"]
	if fel == "l2tp":
		return ["xl2tpd", "ppp", "strongswan", "hds-vpn-nucleu-ipsec", "hds-vpn-nucleu-ppp"]
	return ["openvpn", "hds-vpn-nucleu-tun"]


# ---------------------------------------------------------------- fisierele OpenVPN (lista alba)

_TOKEN_SIGUR = re.compile(r"^[A-Za-z0-9_.:+\-=@,/ ]{1,200}\Z")
_GAZDA = re.compile(r"^(?=.{1,253}\Z)[A-Za-z0-9](?:[A-Za-z0-9\-]{0,62}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9\-]{0,62}[A-Za-z0-9])?)*\.?\Z")
_NUME_FISIER = re.compile(r"^[A-Za-z0-9_.\- ]{1,120}\Z")
PROTOCOALE = ("udp", "tcp", "tcp-client", "udp4", "tcp4", "udp6", "tcp6", "tcp4-client", "tcp6-client")


def _intreg(minim, maxim):
	def verifica(x):
		try:
			v = int(x, 10)
		except (TypeError, ValueError):
			return False
		return minim <= v <= maxim
	return verifica


def _alege(*valori):
	return lambda x: x.lower() in valori


def _sigur(x):
	return bool(_TOKEN_SIGUR.match(x))


_ORICE_INT = _intreg(0, 2147483647)
_PORT = _intreg(1, 65535)

# directiva -> (cel putin, cel mult argumente, verificarea fiecarui argument sau None)
PERMISE = {
	"client": (0, 0, None), "tls-client": (0, 0, None), "pull": (0, 0, None), "nobind": (0, 0, None),
	"persist-key": (0, 0, None), "persist-remote-ip": (0, 0, None),
	"persist-local-ip": (0, 0, None), "float": (0, 0, None), "auth-nocache": (0, 0, None),
	"mute-replay-warnings": (0, 0, None), "ping-timer-rem": (0, 0, None), "remote-random": (0, 0, None),
	"fast-io": (0, 0, None), "passtos": (0, 0, None), "allow-pull-fqdn": (0, 0, None), "push-peer-info": (0, 0, None),
	"port": (1, 1, _PORT), "rport": (1, 1, _PORT), "lport": (1, 1, _intreg(0, 65535)),
	"connect-retry": (1, 2, _ORICE_INT), "connect-retry-max": (1, 1, _ORICE_INT), "connect-timeout": (1, 1, _ORICE_INT),
	"server-poll-timeout": (1, 1, _ORICE_INT), "hand-window": (1, 1, _ORICE_INT), "tran-window": (1, 1, _ORICE_INT),
	"reneg-sec": (1, 2, _ORICE_INT), "reneg-bytes": (1, 1, _ORICE_INT), "reneg-pkts": (1, 1, _ORICE_INT),
	"ping": (1, 1, _ORICE_INT), "ping-restart": (1, 1, _ORICE_INT), "ping-exit": (1, 1, _ORICE_INT),
	"keepalive": (2, 2, _ORICE_INT), "tun-mtu": (1, 1, _intreg(576, 65535)), "tun-mtu-extra": (1, 1, _ORICE_INT),
	"link-mtu": (1, 1, _intreg(576, 65535)), "fragment": (1, 1, _ORICE_INT), "sndbuf": (1, 1, _ORICE_INT),
	"rcvbuf": (1, 1, _ORICE_INT), "txqueuelen": (1, 1, _ORICE_INT), "mute": (1, 1, _ORICE_INT),
	"verb": (1, 1, _intreg(0, 11)), "key-direction": (1, 1, _alege("0", "1")), "replay-window": (1, 2, _ORICE_INT),
	"tls-timeout": (1, 1, _ORICE_INT), "explicit-exit-notify": (0, 1, _ORICE_INT), "mssfix": (0, 2, _sigur),
	"proto": (1, 1, _alege(*PROTOCOALE)), "dev-type": (1, 1, _alege("tun")), "remote-cert-tls": (1, 1, _alege("server")),
	"ns-cert-type": (1, 1, _alege("server")), "comp-lzo": (0, 1, _alege("yes", "no", "adaptive")),
	"compress": (0, 1, _alege("lzo", "lz4", "lz4-v2", "stub", "stub-v2", "migrate")),
	"allow-compression": (1, 1, _alege("yes", "no", "asym")), "topology": (1, 1, _alege("net30", "p2p", "subnet")),
	"mtu-disc": (1, 1, _alege("no", "maybe", "yes")), "resolv-retry": (1, 1, _sigur),
	"cipher": (1, 1, _sigur), "data-ciphers": (1, 1, _sigur), "ncp-ciphers": (1, 1, _sigur),
	"data-ciphers-fallback": (1, 1, _sigur), "auth": (1, 1, _sigur), "tls-cipher": (1, 1, _sigur),
	"tls-ciphersuites": (1, 1, _sigur), "tls-groups": (1, 1, _sigur), "tls-cert-profile": (1, 1, _sigur),
	"tls-version-min": (1, 2, _sigur), "tls-version-max": (1, 1, _sigur), "remote-cert-ku": (1, 8, _sigur),
	"remote-cert-eku": (1, 1, _sigur), "verify-x509-name": (1, 2, _sigur),
	# in toate fisierele PIA: opreste numai verificarea potrivirii optiunilor cu serverul
	"disable-occ": (0, 0, None),
}
# directivele tratate deosebit: remote, dev, auth-user-pass si fisierele (in linie sau de alaturi)
SPECIALE = ("remote", "dev", "auth-user-pass")
FISIERE = ("ca", "cert", "key", "extra-certs", "tls-auth", "tls-crypt", "tls-crypt-v2", "crl-verify")
# lasate deoparte: rutarea, DNS-ul si ce tine de alte sisteme le decide receptorul
IGNORATE = frozenset((
	"redirect-gateway", "redirect-private", "route", "route-ipv6", "route-gateway", "route-ipv6-gateway", "route-metric",
	"route-delay", "route-method", "route-nopull", "route-noexec", "dhcp-option", "block-outside-dns", "register-dns",
	"ip-win32", "pull-filter", "setenv", "setenv-safe", "ifconfig-ipv6", "tun-ipv6", "user", "group", "auth-retry",
	"machine-readable-output", "suppress-timestamps", "ignore-unknown-option", "nice", "mlock", "ncp-disable",
	"keysize", "lladdr", "inactive", "max-routes", "ifconfig-nowarn", "tls-exit", "auth-token", "auth-token-user",
	"dhcp-release", "dhcp-renew", "show-net-up", "allow-recursive-routing", "disable-dco", "windows-driver",
	"remap-usr1", "connect-freq", "persist-tun",
))
_PROGRAME = N_("pornește programe pe receptor")
_RETEA = N_("deschide receptorul în rețea")
_FIS = N_("citește sau scrie fișiere pe receptor")
_SERVER = N_("e o directivă de server, nu de client")
REFUZATE = {
	"up": _PROGRAME, "down": _PROGRAME, "route-up": _PROGRAME, "route-pre-down": _PROGRAME, "ipchange": _PROGRAME,
	"client-connect": _PROGRAME, "client-disconnect": _PROGRAME, "learn-address": _PROGRAME, "tls-verify": _PROGRAME,
	"auth-user-pass-verify": _PROGRAME, "plugin": _PROGRAME, "script-security": _PROGRAME, "iproute": _PROGRAME,
	"management": _RETEA, "http-proxy": _RETEA, "socks-proxy": _RETEA,
	"config": _FIS, "cd": _FIS, "chroot": _FIS, "daemon": _FIS, "log": _FIS, "log-append": _FIS, "status": _FIS,
	"writepid": _FIS, "askpass": _FIS, "tmp-dir": _FIS, "dev-node": _FIS, "engine": _FIS, "providers": _FIS,
	"pkcs12": _FIS, "http-proxy-user-pass": _FIS,
	"secret": N_("folosește o cheie statică veche, nesigură"), "no-replay": N_("folosește o cheie statică veche, nesigură"),
	"static-challenge": _SERVER, "auth-user-pass-optional": _SERVER, "ifconfig": _SERVER,
	"server": _SERVER, "mode": _SERVER, "tls-server": _SERVER, "client-to-client": _SERVER, "duplicate-cn": _SERVER,
	"push": _SERVER, "dh": _SERVER, "ifconfig-pool": _SERVER, "client-config-dir": _SERVER,
	"connection": N_("folosește câte un fișier pe server"),
}
_NECUNOSCUTA = N_("nu este cunoscută")
BLOCURI_IGNORATE = ("auth-user-pass",)
_RAND_BLOC = re.compile(r"^[\x20-\x7e]{0,256}\Z")
_DESCHIDE_BLOC = re.compile(r"^\s*<([A-Za-z0-9\-]{1,40})>\s*\Z")


def _desparte(rand):
	"""Cuvintele unui rand de configurare OpenVPN (ghilimele duble sau simple, \\ in ghilimele duble); un # sau ; la
	inceputul unui cuvant incepe un comentariu. None pentru un rand stricat (ghilimele neinchise)."""
	cuvinte = []
	i, n = 0, len(rand)
	while i < n:
		c = rand[i]
		if c.isspace():
			i += 1
			continue
		if c in "#;":
			break
		if c in "\"'":
			inchis = c
			i += 1
			cuv = []
			while i < n and rand[i] != inchis:
				if inchis == '"' and rand[i] == "\\" and i + 1 < n:
					i += 1
				cuv.append(rand[i])
				i += 1
			if i >= n:
				return None
			i += 1
			cuvinte.append("".join(cuv))
			continue
		cuv = []
		while i < n and not rand[i].isspace():
			if rand[i] == "\\" and i + 1 < n:
				i += 1
			cuv.append(rand[i])
			i += 1
		cuvinte.append("".join(cuv))
	return cuvinte


def _cuGhilimele(x):
	return '"%s"' % x if (" " in x or not x) else x


def _blocBun(text):
	"""Continutul unui bloc in linie (certificat, cheie): randuri ASCII scurte, fara < si >."""
	if len(text) > MAX_BLOC:
		return False
	for rand in text.split("\n"):
		rand = rand.rstrip("\r")
		if not _RAND_BLOC.match(rand) or "<" in rand or ">" in rand:
			return False
	return "-----BEGIN" in text or "-----BEGIN OpenVPN" in text


def _numeAlaturi(arg):
	"""Numele simplu al unui fisier de alaturi (fara cai), sau None."""
	nume = arg.replace("\\", "/").rsplit("/", 1)[-1]
	if not nume or nume in (".", "..") or not _NUME_FISIER.match(nume):
		return None
	return nume.lower()


def analizeazaOvpn(text, alaturi=None, nume=""):
	"""Fisierul .ovpn verificat. {"ok", "greseli": [...], "note": [...], "curat": textul de pus pe receptor (fara
	remote, dev si auth-user-pass, cu fisierele de alaturi puse in linie), "remote": [(gazda, port, proto)], "proto",
	"cere_cont", "cipher", "data_ciphers", "nobind"}. `alaturi`: {numele simplu cu litere mici: textul} din acelasi
	import."""
	alaturi = alaturi or {}
	greseli, note = [], []
	randuri_curate = []
	blocuri = {}
	remote = []
	proto = ""
	port = "1194"
	cere_cont = False
	cipher = ""
	data_ciphers = False
	are_ca = False
	nobind = True
	vazute_ignorate = set()
	if "\x00" in text:
		return {"ok": False, "greseli": [_("Fișierul nu este text.")], "note": [], "curat": "", "remote": []}
	randuri = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
	i = 0
	while i < len(randuri):
		rand = randuri[i]
		i += 1
		m = _DESCHIDE_BLOC.match(rand)
		if m:
			eticheta = m.group(1).lower()
			continut = []
			inchis = False
			while i < len(randuri):
				r = randuri[i]
				i += 1
				if r.strip().lower() == "</%s>" % eticheta:
					inchis = True
					break
				continut.append(r.rstrip())
			if not inchis:
				greseli.append(_("Blocul <%s> nu este închis.") % eticheta)
				continue
			bloc = "\n".join(continut).strip("\n")
			if eticheta in BLOCURI_IGNORATE:
				cere_cont = True
				note.append(_("Numele și parola din fișier nu se folosesc: se scriu pe receptor."))
				continue
			if eticheta not in FISIERE:
				greseli.append(_("Blocul <%s> nu este primit: %s.") % (eticheta, _(REFUZATE.get(eticheta, _NECUNOSCUTA))))
				continue
			if not _blocBun(bloc):
				greseli.append(_("Blocul <%s> nu arată ca un certificat sau o cheie.") % eticheta)
				continue
			blocuri[eticheta] = bloc
			continue
		cuv = _desparte(rand)
		if cuv is None:
			greseli.append(_("Un rând are ghilimele neînchise: %s") % ascunde(rand.strip())[:60])
			continue
		if not cuv:
			continue
		d = cuv[0].lower()
		if d.startswith("--"):
			d = d[2:]
		arg = cuv[1:]
		if d.startswith("management"):
			greseli.append(_("Directiva %s nu este primită: %s.") % (d, _(_RETEA)))
			continue
		if d in REFUZATE:
			greseli.append(_("Directiva %s nu este primită: %s.") % (d, _(REFUZATE[d])))
			continue
		if d in IGNORATE:
			if d not in vazute_ignorate:
				vazute_ignorate.add(d)
			continue
		if d == "remote":
			if not 1 <= len(arg) <= 3:
				greseli.append(_("Rândul %s nu este bun.") % d)
				continue
			g = arg[0]
			if not _gazdaBuna(g):
				greseli.append(_("Adresa serverului nu este bună: %s") % g[:60])
				continue
			p = arg[1] if len(arg) > 1 else ""
			if p and not _PORT(p):
				greseli.append(_("Rândul %s nu este bun.") % d)
				continue
			pr = arg[2].lower() if len(arg) > 2 else ""
			if pr and pr not in PROTOCOALE:
				greseli.append(_("Rândul %s nu este bun.") % d)
				continue
			remote.append([g, p, pr])
			continue
		if d == "dev":
			if len(arg) != 1 or not arg[0].lower().startswith("tun"):
				greseli.append(_("Numai interfața tun este primită (nu tap)."))
			continue
		if d == "auth-user-pass":
			cere_cont = True
			continue
		if d in FISIERE:
			if not 1 <= len(arg) <= 2:
				greseli.append(_("Rândul %s nu este bun.") % d)
				continue
			if d == "crl-verify" and len(arg) == 2:
				greseli.append(_("Directiva %s nu este primită: %s.") % (d, _(_FIS)))
				continue
			directie = arg[1] if (d == "tls-auth" and len(arg) == 2) else ""
			if directie and directie not in ("0", "1"):
				greseli.append(_("Rândul %s nu este bun.") % d)
				continue
			if arg[0] != "[inline]":
				n = _numeAlaturi(arg[0])
				if n is None or n not in alaturi:
					greseli.append(_("Lipsește fișierul %s: pune-l lângă fișierul de configurare.") % (n or arg[0])[:60])
					continue
				bloc = alaturi[n].replace("\r\n", "\n").strip("\n")
				if not _blocBun(bloc):
					greseli.append(_("Blocul <%s> nu arată ca un certificat sau o cheie.") % d)
					continue
				blocuri[d] = bloc
			if directie:
				randuri_curate.append("key-direction %s" % directie)
			continue
		spec = PERMISE.get(d)
		if spec is None:
			greseli.append(_("Directiva %s nu este primită: %s.") % (d[:40], _(_NECUNOSCUTA)))
			continue
		minim, maxim, verifica = spec
		if not minim <= len(arg) <= maxim or (verifica is not None and not all(verifica(a) for a in arg)):
			greseli.append(_("Rândul %s nu este bun.") % d)
			continue
		if d == "verb":
			arg = [str(min(3, int(arg[0])))]
		if d == "proto":
			proto = arg[0].lower()
		elif d in ("port", "rport"):
			port = arg[0]
		elif d == "cipher":
			cipher = arg[0]
		elif d in ("data-ciphers", "ncp-ciphers"):
			data_ciphers = True
		elif d in ("lport",):
			nobind = False
		randuri_curate.append(" ".join([d] + [_cuGhilimele(a) for a in arg]))
	for d in FISIERE:
		if d in blocuri and d == "ca":
			are_ca = True
	if not remote:
		greseli.append(_("Fișierul nu are niciun rând remote (adresa serverului)."))
	if not are_ca:
		greseli.append(_("Lipsește certificatul serverului (ca)."))
	if "cert" in blocuri and "key" not in blocuri:
		greseli.append(_("Fișierul are certificatul clientului, dar nu și cheia lui."))
	if "cert" not in blocuri and not cere_cont:
		greseli.append(_("Fișierul nu are nici certificat de client, nici nume și parolă (auth-user-pass)."))
	if vazute_ignorate:
		note.append(_("Rutarea și DNS-ul le alege receptorul (lăsate deoparte: %s).") % ", ".join(sorted(vazute_ignorate))[:200])
	for r in remote:
		r[1] = r[1] or port
		r[2] = r[2] or proto or "udp"
	curat = ["# HD Satelit VPN: copia verificata a fisierului %s" % _numeCurat(nume)] + randuri_curate
	for d in FISIERE:
		if d in blocuri:
			curat += ["<%s>" % d, blocuri[d], "</%s>" % d]
	return {"ok": not greseli, "greseli": greseli, "note": note, "curat": "\n".join(curat) + "\n",
		"remote": [tuple(r) for r in remote], "proto": proto or (remote[0][2] if remote else "udp"),
		"cere_cont": cere_cont, "cipher": cipher, "data_ciphers": data_ciphers, "nobind": nobind}


def _numeCurat(nume):
	return re.sub(r"[^A-Za-z0-9_.\- ]", "_", os.path.basename((nume or "").replace("\\", "/")))[:80] or "-"


def _gazdaBuna(g):
	try:
		ipaddress.ip_address(g)
		return True
	except ValueError:
		return bool(_GAZDA.match(g))


# ---------------------------------------------------------------- fisierele WireGuard

_CHEIE_WG = re.compile(r"^[A-Za-z0-9+/]{42}[AEIMQUYcgkosw048]=\Z")
CHEI_WG_REFUZATE = ("preup", "postup", "predown", "postdown")
CHEI_WG_IGNORATE = ("fwmark", "table", "saveconfig")


def _cheieWg(x):
	if not _CHEIE_WG.match(x or ""):
		return False
	try:
		return len(base64.b64decode(x)) == 32
	except (binascii.Error, ValueError):
		return False


def _desparteEndpoint(text):
	"""(gazda, port) din "gazda:port" sau "[v6]:port", None daca nu e bun."""
	m = re.match(r"^\[([0-9A-Fa-f:.]+)\]:(\d{1,5})\Z", text) or re.match(r"^([^:\[\]\s]+):(\d{1,5})\Z", text)
	if not m or not _PORT(m.group(2)) or not _gazdaBuna(m.group(1)):
		return None
	return m.group(1), m.group(2)


def analizeazaWg(text, nume=""):
	"""Fisierul WireGuard verificat: {"ok", "greseli", "note", "curat" (fara cheile refuzate), "adrese" (IPv4),
	"dns", "mtu", "peers": [{"cheie", "psk", "permise", "endpoint": (gazda, port), "keepalive"}], "cheie_privata",
	"port", "plin" (vreun peer are 0.0.0.0/0)}."""
	greseli, note = [], []
	sectiune = None
	interfata = {}
	peers = []
	nr_interfete = 0
	vazute_ignorate = set()
	if "\x00" in text:
		return {"ok": False, "greseli": [_("Fișierul nu este text.")], "note": [], "curat": "", "peers": []}
	for rand in text.replace("\r\n", "\n").split("\n"):
		r = rand.split("#", 1)[0].strip()
		if not r:
			continue
		if r.startswith("["):
			s = r.lower()
			if s == "[interface]":
				nr_interfete += 1
				if nr_interfete == 2:
					greseli.append(_("Rândul %s nu este bun.") % r[:30])
				sectiune = "interface"
			elif s == "[peer]":
				sectiune = "peer"
				peers.append({})
			else:
				greseli.append(_("Rândul %s nu este bun.") % ascunde(r)[:30])
				sectiune = "?"
			continue
		if "=" not in r:
			greseli.append(_("Rândul %s nu este bun.") % ascunde(r)[:30])
			continue
		cheie, valoare = [x.strip() for x in r.split("=", 1)]
		k = cheie.lower()
		if k in CHEI_WG_REFUZATE:
			greseli.append(_("Directiva %s nu este primită: %s.") % (cheie[:40], _(_PROGRAME)))
			continue
		if k in CHEI_WG_IGNORATE:
			vazute_ignorate.add(cheie[:40])
			continue
		if sectiune == "interface":
			if k == "privatekey":
				if not _cheieWg(valoare):
					greseli.append(_("Cheia %s nu este bună.") % cheie)
				interfata["privatekey"] = valoare
			elif k == "address":
				adrese = []
				for a in valoare.split(","):
					a = a.strip()
					try:
						x = ipaddress.ip_interface(a)
					except ValueError:
						greseli.append(_("Adresa %s nu este bună.") % a[:50])
						continue
					if x.version == 4:
						adrese.append(str(x))
				interfata["adrese"] = interfata.get("adrese", []) + adrese
			elif k == "dns":
				dns = []
				for a in valoare.split(","):
					a = a.strip()
					try:
						if ipaddress.ip_address(a).version == 4:
							dns.append(a)
					except ValueError:
						pass
				interfata["dns"] = interfata.get("dns", []) + dns
			elif k == "mtu":
				if not _intreg(1280, 9000)(valoare):
					greseli.append(_("Rândul %s nu este bun.") % cheie)
				else:
					interfata["mtu"] = int(valoare)
			elif k == "listenport":
				if not _PORT(valoare):
					greseli.append(_("Rândul %s nu este bun.") % cheie)
				else:
					interfata["port"] = valoare
			else:
				greseli.append(_("Directiva %s nu este primită: %s.") % (cheie[:40], _(_NECUNOSCUTA)))
		elif sectiune == "peer":
			p = peers[-1]
			if k == "publickey":
				if not _cheieWg(valoare):
					greseli.append(_("Cheia %s nu este bună.") % cheie)
				p["cheie"] = valoare
			elif k == "presharedkey":
				if not _cheieWg(valoare):
					greseli.append(_("Cheia %s nu este bună.") % cheie)
				p["psk"] = valoare
			elif k == "allowedips":
				retele = []
				for a in valoare.split(","):
					a = a.strip()
					try:
						retele.append(str(ipaddress.ip_network(a, strict=False)))
					except ValueError:
						greseli.append(_("Adresa %s nu este bună.") % a[:50])
				p["permise"] = p.get("permise", []) + retele
			elif k == "endpoint":
				e = _desparteEndpoint(valoare)
				if e is None:
					greseli.append(_("Adresa serverului nu este bună: %s") % valoare[:60])
				p["endpoint"] = e
			elif k == "persistentkeepalive":
				if valoare.lower() != "off" and not _intreg(0, 65535)(valoare):
					greseli.append(_("Rândul %s nu este bun.") % cheie)
				else:
					p["keepalive"] = "0" if valoare.lower() == "off" else valoare
			else:
				greseli.append(_("Directiva %s nu este primită: %s.") % (cheie[:40], _(_NECUNOSCUTA)))
		else:
			greseli.append(_("Rândul %s nu este bun.") % cheie[:30])
	if not interfata.get("privatekey"):
		greseli.append(_("În fișier lipsește %s.") % "PrivateKey")
	if not interfata.get("adrese"):
		greseli.append(_("În fișier lipsește %s.") % "Address (IPv4)")
	if not peers:
		greseli.append(_("În fișier lipsește %s.") % "[Peer]")
	for p in peers:
		if not p.get("cheie"):
			greseli.append(_("În fișier lipsește %s.") % "PublicKey")
		if not p.get("permise"):
			greseli.append(_("În fișier lipsește %s.") % "AllowedIPs")
		if not p.get("endpoint"):
			greseli.append(_("În fișier lipsește %s.") % "Endpoint")
	if vazute_ignorate:
		note.append(_("Rutarea și DNS-ul le alege receptorul (lăsate deoparte: %s).") % ", ".join(sorted(vazute_ignorate))[:200])
	plin = any(r == "0.0.0.0/0" for p in peers for r in p.get("permise", []))
	curat = ["# HD Satelit VPN: copia verificata a fisierului %s" % _numeCurat(nume), "[Interface]"]
	if interfata.get("privatekey"):
		curat.append("PrivateKey = %s" % interfata["privatekey"])
	if interfata.get("adrese"):
		curat.append("Address = %s" % ", ".join(interfata["adrese"]))
	if interfata.get("dns"):
		curat.append("DNS = %s" % ", ".join(interfata["dns"]))
	if interfata.get("mtu"):
		curat.append("MTU = %d" % interfata["mtu"])
	if interfata.get("port"):
		curat.append("ListenPort = %s" % interfata["port"])
	for p in peers:
		curat.append("")
		curat.append("[Peer]")
		if p.get("cheie"):
			curat.append("PublicKey = %s" % p["cheie"])
		if p.get("psk"):
			curat.append("PresharedKey = %s" % p["psk"])
		if p.get("permise"):
			curat.append("AllowedIPs = %s" % ", ".join(p["permise"]))
		if p.get("endpoint"):
			g, pt = p["endpoint"]
			curat.append("Endpoint = %s:%s" % (("[%s]" % g) if ":" in g else g, pt))
		if p.get("keepalive"):
			curat.append("PersistentKeepalive = %s" % p["keepalive"])
	return {"ok": not greseli, "greseli": greseli, "note": note, "curat": "\n".join(curat) + "\n",
		"adrese": interfata.get("adrese", []), "dns": interfata.get("dns", []), "mtu": interfata.get("mtu"),
		"peers": peers, "port": interfata.get("port", ""), "plin": plin,
		"remote": [(p["endpoint"][0], p["endpoint"][1], "udp") for p in peers if p.get("endpoint")]}


def textSetconf(analiza, endpointuri):
	"""Textul pentru `wg setconf` (numai cheile lui wg; Address, DNS si MTU le pune receptorul), cu adresele serverelor
	rezolvate (`endpointuri`: {(gazda, port): ip})."""
	r = ["[Interface]", "PrivateKey = %s" % analiza["cheie_privata"]] if analiza.get("cheie_privata") else ["[Interface]"]
	if analiza.get("port"):
		r.append("ListenPort = %s" % analiza["port"])
	for p in analiza["peers"]:
		r += ["", "[Peer]", "PublicKey = %s" % p["cheie"]]
		if p.get("psk"):
			r.append("PresharedKey = %s" % p["psk"])
		r.append("AllowedIPs = %s" % ", ".join(p["permise"]))
		g, pt = p["endpoint"]
		ip = endpointuri.get((g, pt), g)
		r.append("Endpoint = %s:%s" % (("[%s]" % ip) if ":" in ip else ip, pt))
		if p.get("keepalive"):
			r.append("PersistentKeepalive = %s" % p["keepalive"])
	return "\n".join(r) + "\n"


def cheiePrivataWg(text):
	for rand in text.replace("\r\n", "\n").split("\n"):
		r = rand.split("#", 1)[0].strip()
		if r.lower().replace(" ", "").startswith("privatekey="):
			return r.split("=", 1)[1].strip()
	return ""


# ---------------------------------------------------------------- profilurile (serverele importate)

_PROTO_IN_NUME = re.compile(r"(?i)^(tcp|udp)[0-9]*\Z")


def titluDinNume(nume, proto=""):
	"""Romania.Bucharest.UDP.ovpn -> "Romania, Bucharest (UDP)"; protocolul din nume sau cel dat."""
	baza = os.path.basename((nume or "").replace("\\", "/"))
	baza = re.sub(r"(?i)\.(ovpn|conf)\Z", "", baza)
	bucati = [b for b in re.split(r"[._\s\-]+", baza) if b]
	pr = ""
	rest = []
	for b in bucati:
		if _PROTO_IN_NUME.match(b):
			pr = pr or b[:3].lower()
			continue
		rest.append(b)
	pr = pr or (proto or "")[:3].lower()
	if not rest:
		rest = [baza or "VPN"]
	titlu = rest[0] if len(rest) == 1 else "%s, %s" % (rest[0], " ".join(rest[1:]))
	if pr in ("tcp", "udp"):
		titlu += " (%s)" % pr.upper()
	return titlu[:80]


_INDEX = {"semn": None, "lista": []}


def _semnFisier(cale):
	try:
		st = os.stat(_cale(cale))
		return (st.st_ino, st.st_size, st.st_mtime_ns)
	except OSError:
		return None


def profiluri():
	"""Lista serverelor importate: [{"id", "titlu", "fel", "grup", "fisier", "gazde", "proto", "cere_cont", "cipher",
	"data_ciphers", "nobind"}], dupa titlu; citita din nou numai cand profiluri.json s-a schimbat."""
	semn = _semnFisier(CALE_INDEX)
	if semn != _INDEX["semn"]:
		date = _citesteJson(CALE_INDEX) or {}
		lista = [p for p in (date.get("profiluri") or []) if isinstance(p, dict) and re.match(r"^[0-9a-f]{12}\Z",
			str(p.get("id", ""))) and p.get("fel") in FELURI and re.match(
			r"^[0-9a-f]{12}\.(ovpn|conf|json)\Z", str(p.get("fisier", ""))) and isinstance(p.get("titlu"), str)]
		_INDEX["lista"] = lista
		_INDEX["semn"] = semn
	return list(_INDEX["lista"])


def profiluriGrup(grup):
	return [p for p in profiluri() if p.get("grup") == grup]


def profil(id_profil):
	for p in profiluri():
		if p["id"] == id_profil:
			return p
	return None


def _scrieIndex(lista):
	_dosar(DOSAR)
	lista = sorted(lista, key=lambda p: (p.get("titlu", "").lower(), p["id"]))
	_scrieAtomic(CALE_INDEX, json.dumps({"profiluri": lista}, ensure_ascii=False, indent=0), 0o600)
	_INDEX["semn"] = None


def _caleProfil(p):
	return "%s/%s" % (DOSAR_PROFILURI, p["fisier"])


def textProfil(p):
	return _citeste(_caleProfil(p), MAX_FISIER * 2) or ""


def _membriArhiva(nume, date, greseli):
	"""(nume, octeti) din arhiva zip, cu limitele de marime; arhivele din arhiva nu se deschid."""
	rez = []
	try:
		with zipfile.ZipFile(io.BytesIO(date)) as z:
			total = 0
			for info in z.infolist()[:MAX_MEMBRI]:
				if info.is_dir() or info.file_size > MAX_FISIER:
					continue
				n = info.filename.replace("\\", "/")
				if n.lower().endswith(".zip") or "/." in "/" + n:
					continue
				total += info.file_size
				if total > MAX_ARHIVA:
					greseli.append(_("Arhiva %s este prea mare; s-a citit numai începutul ei.") % _numeCurat(nume))
					break
				rez.append((n, z.read(info)))
	except (zipfile.BadZipFile, OSError, ValueError, RuntimeError, NotImplementedError):
		greseli.append(_("Arhiva %s nu se poate deschide.") % _numeCurat(nume))
	return rez


def importa(fisiere, grup):
	"""Importa fisierele (lista de (nume, octeti)): .ovpn, .conf, .zip si fisierele de alaturi (.crt, .key, .pem...).
	(reusit, mesaj, {"adaugate", "la_fel", "refuzate", "motive"})."""
	if not grupCunoscut(grup):
		return False, _("Alege întâi furnizorul."), {}
	greseli = []
	desfacute = []
	for nume, date in fisiere:
		if nume.lower().endswith(".zip"):
			desfacute += _membriArhiva(nume, date, greseli)
		elif len(date) <= MAX_FISIER:
			desfacute.append((nume, date))
		else:
			greseli.append(_("Fișierul %s este prea mare.") % _numeCurat(nume))
	alaturi = {}
	principale = []
	for nume, date in desfacute:
		text = date.decode("utf-8", "replace")
		n = nume.replace("\\", "/").rsplit("/", 1)[-1]
		if n.lower().endswith((".ovpn", ".conf")):
			principale.append((nume, text))
		else:
			nn = _numeAlaturi(n)
			if nn:
				alaturi[nn] = text
	if not principale:
		return False, _("Nu am găsit niciun fișier .ovpn sau .conf."), {"motive": greseli[:3]}
	lista = profiluri()
	ids = set(p["id"] for p in lista)
	titluri = set(p["titlu"] for p in lista if p.get("grup") == grup)
	adaugate = la_fel = refuzate = 0
	motive = list(greseli)
	ids_rez = []
	feluri = feluriGrup(grup)
	for nume, text in principale[:MAX_MEMBRI]:
		este_wg = "[interface]" in text.lower()
		if ("wireguard" if este_wg else "openvpn") not in feluri:
			refuzate += 1
			motive.append(_("%s: e un fișier WireGuard; alege furnizorul WireGuard.") % _numeCurat(nume) if este_wg else
				_("%s: e un fișier OpenVPN; alege un furnizor cu fișiere OpenVPN.") % _numeCurat(nume))
			continue
		a = analizeazaWg(text, nume) if este_wg else analizeazaOvpn(text, alaturi, nume)
		if not a["ok"]:
			refuzate += 1
			motive.append("%s: %s" % (_numeCurat(nume), a["greseli"][0]))
			continue
		id_p = hashlib.sha1(("%s\n%s" % (grup, a["curat"])).encode("utf-8")).hexdigest()[:12]
		if id_p in ids:
			la_fel += 1
			if id_p not in ids_rez:
				ids_rez.append(id_p)
			continue
		if len(lista) >= MAX_PROFILURI:
			refuzate += 1
			motive.append(_("Sunt deja %d servere; șterge din ele.") % MAX_PROFILURI)
			break
		titlu = titluDinNume(nume, a.get("proto", ""))
		baza, k = titlu, 2
		while titlu in titluri:
			titlu = "%s %d" % (baza, k)
			k += 1
		p = {"id": id_p, "titlu": titlu, "fel": "wireguard" if este_wg else "openvpn", "grup": grup,
			"fisier": "%s.%s" % (id_p, "conf" if este_wg else "ovpn"), "nume_fisier": _numeCurat(nume),
			"gazde": ["%s:%s" % (r[0], r[1]) for r in a["remote"]][:16], "proto": a.get("proto", "udp"),
			"remote": [list(r) for r in a["remote"]][:16],
			"cere_cont": bool(a.get("cere_cont")), "cipher": a.get("cipher", ""), "data_ciphers": bool(a.get("data_ciphers")),
			"nobind": a.get("nobind", True), "plin": a.get("plin", True), "adaugat": int(time.time())}
		_dosar(DOSAR)
		_dosar(DOSAR_PROFILURI)
		_scrieAtomic(_caleProfil(p), a["curat"], 0o600)
		lista.append(p)
		ids.add(id_p)
		titluri.add(titlu)
		ids_rez.append(id_p)
		adaugate += 1
	if adaugate:
		_scrieIndex(lista)
	parti = []
	if adaugate:
		parti.append(_("Servere adăugate: %d.") % adaugate)
	if la_fel:
		parti.append(_("Erau deja: %d.") % la_fel)
	if refuzate:
		parti.append(_("Nepotrivite: %d.") % refuzate)
	if motive:
		parti.append(motive[0])
	jurnal("import %s: %d adaugate, %d la fel, %d refuzate %s" % (grup, adaugate, la_fel, refuzate, motive[:3]))
	return bool(adaugate or la_fel), " ".join(parti) or _("Nimic de adăugat."), {"adaugate": adaugate,
		"la_fel": la_fel, "refuzate": refuzate, "motive": motive[:5], "ids": ids_rez}


def stergeProfil(id_profil):
	lista = profiluri()
	p = profil(id_profil)
	if p is None:
		return False, _("Serverul nu mai există.")
	if setari()["pornit"] and setari()["profil"] == id_profil:
		return False, _("Oprește întâi VPN-ul.")
	_sterge(_caleProfil(p))
	_sterge(_caleSecret(p))
	_scrieIndex([x for x in lista if x["id"] != id_profil])
	if setari()["profil"] == id_profil:
		salveazaSetari(profil="")
	return True, _("Serverul %s a fost șters.") % p["titlu"]


def stergeGrup(grup):
	s = setari()
	if s["pornit"] and s["furnizor"] == grup:
		return False, _("Oprește întâi VPN-ul.")
	lista = profiluri()
	pastrate = []
	n = 0
	for p in lista:
		if p.get("grup") == grup:
			_sterge(_caleProfil(p))
			_sterge(_caleSecret(p))
			n += 1
		else:
			pastrate.append(p)
	_scrieIndex(pastrate)
	if profil(s["profil"]) is None:
		salveazaSetari(profil="")
	return True, _("Servere șterse: %d.") % n


# ---------------------------------------------------------------- protocoalele noi: recunoasterea si profilurile

# Shadowsocks: numai metodele AEAD (ss-local); cele vechi (fluxuri fara autentificare) se refuza cu motivul lor
METODE_SS = ("aes-128-gcm", "aes-192-gcm", "aes-256-gcm", "chacha20-ietf-poly1305", "xchacha20-ietf-poly1305")
METODE_SS_VECHI = ("rc4", "rc4-md5", "table", "aes-128-cfb", "aes-192-cfb", "aes-256-cfb", "aes-128-ctr", "aes-192-ctr",
	"aes-256-ctr", "camellia-128-cfb", "camellia-192-cfb", "camellia-256-cfb", "bf-cfb", "cast5-cfb", "des-cfb",
	"idea-cfb", "rc2-cfb", "seed-cfb", "salsa20", "chacha20", "chacha20-ietf")
# OpenConnect: --protocol
PROTOCOALE_OC = ("anyconnect", "gp", "nc", "pulse", "fortinet", "f5", "array")
# campurile de acces ale protocoalelor noi (stau in <id>.secret, 0600)
CAMPURI = ("nume", "parola", "psk")
MAX_SECRET = 256
EXT_ALATURI = (".crt", ".pem", ".cer", ".der", ".key", ".ca")
_URL_OC = re.compile(r"^https://([A-Za-z0-9](?:[A-Za-z0-9.\-]{0,251}[A-Za-z0-9])?)(?::(\d{1,5}))?"
	r"(/[A-Za-z0-9._~\-/%=&+,;@!$]{0,200})?\Z")
# numele contului la IKEv2 si L2TP (ajunge in fisiere de configurare): fara ghilimele, spatii sau semne de sintaxa
_NUME_CONT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@+\-=]{0,127}\Z")
_ID_IKE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@\-]{0,200}\Z")
_PIN_OC = re.compile(r"^pin-sha256:[A-Za-z0-9+/]{43}=\Z")
_PROPUNERE = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*(?:,[a-z0-9]+(?:[-_][a-z0-9]+)*){0,15}\Z")
_PEM_CERT = re.compile(r"-----BEGIN CERTIFICATE-----\s+[A-Za-z0-9+/=\s]{40,32768}?-----END CERTIFICATE-----")
_DOCTYPE_PLIST = re.compile(r'<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1\.0//EN" '
	r'"http://www\.apple\.com/DTDs/PropertyList-1\.0\.dtd">')


def _secretBun(x, maxim=MAX_SECRET):
	"""Parola sau cheia comuna: text pe un singur rand, fara semne de control."""
	return isinstance(x, str) and 0 < len(x) <= maxim and all(ord(c) >= 0x20 and ord(c) != 0x7f for c in x)


def _titluCurat(text, rezerva):
	t = re.sub(r"[\x00-\x1f\x7f<>]", "", "%s" % (text or "")).strip()[:80]
	return t or rezerva


def _textPlist(text):
	"""XML-ul plist dintr-un .mobileconfig (si din cel semnat, unde e in mijlocul unui bloc binar), sau ""."""
	a = text.find("<?xml")
	if a < 0:
		a = text.find("<plist")
	b = text.find("</plist>")
	if a < 0 or b < a:
		return ""
	return text[a:b + 8]


def recunoaste(text, nume=""):
	"""Felul VPN-ului dupa continut (si, unde nu se poate altfel, dupa nume): "openvpn", "wireguard", "ikev2" (.sswan,
	.mobileconfig IKEv2), "l2tp" (.mobileconfig L2TP), "openconnect" (adresa https a serverului), "shadowsocks" (ss://
	sau configurarea JSON) sau "" daca nu se recunoaste."""
	t = (text or "").lstrip("﻿").strip()
	n = (nume or "").lower()
	if not t:
		return ""
	if re.match(r"(?i)^ss://", t):
		return "shadowsocks"
	if n.endswith(".mobileconfig") or "<plist" in t[:65536]:
		x = _textPlist(t)
		if re.search(r"<key>VPNType</key>\s*<string>IKEv2</string>", x):
			return "ikev2"
		if re.search(r"<key>VPNType</key>\s*<string>L2TP</string>", x):
			return "l2tp"
		return ""
	if t.startswith("{"):
		try:
			d = json.loads(t)
		except ValueError:
			return ""
		if isinstance(d, dict):
			if isinstance(d.get("remote"), dict) and str(d.get("type", "")).startswith("ikev2"):
				return "ikev2"
			if isinstance(d.get("servers"), list) or ("server" in d and ("password" in d or "method" in d)):
				return "shadowsocks"
		return ""
	if re.search(r"(?im)^\s*\[interface\]", t) and re.search(r"(?im)^\s*\[peer\]", t):
		return "wireguard"
	if n.endswith(".ovpn") or re.search(r"(?im)^\s*(?:client\s*$|remote\s+\S|dev\s+tun|<ca>\s*$)", t):
		return "openvpn"
	if "\n" not in t and _URL_OC.match(t):
		return "openconnect"
	return ""


def _b64Text(text):
	s = re.sub(r"\s", "", text).replace("-", "+").replace("_", "/")
	s += "=" * (-len(s) % 4)
	return base64.b64decode(s, validate=True).decode("utf-8")


def _pemDinDer(date):
	b = base64.b64encode(date).decode("ascii")
	return "-----BEGIN CERTIFICATE-----\n%s\n-----END CERTIFICATE-----" % "\n".join(b[i:i + 64] for i in range(0, len(b), 64))


def certificateDin(text):
	"""Certificatele PEM dintr-un text (blocurile BEGIN/END CERTIFICATE, verificate ca base64), cel mult 8."""
	rez = []
	for m in _PEM_CERT.finditer(text or ""):
		corp = re.sub(r"\s", "", m.group(0)[len("-----BEGIN CERTIFICATE-----"):-len("-----END CERTIFICATE-----")])
		try:
			der = base64.b64decode(corp, validate=True)
		except (binascii.Error, ValueError):
			continue
		if der[:1] == b"\x30" and len(der) > 64:
			rez.append(_pemDinDer(der))
		if len(rez) >= 8:
			break
	return rez


def _greseala(fel, text):
	return {"ok": False, "fel": fel, "greseli": [text], "note": [], "profiluri": []}


def _analizaBuna(fel, profiluri, note=None):
	return {"ok": bool(profiluri), "fel": fel, "greseli": [] if profiluri else [_("Nimic de adăugat.")],
		"note": note or [], "profiluri": profiluri}


def _profilSs(server, port, metoda, parola, titlu):
	"""Un profil Shadowsocks verificat sau (None, motivul)."""
	if not _gazdaBuna(server) or not _PORT(str(port)):
		return None, _("Adresa serverului nu este bună: %s") % ("%s" % server)[:60]
	metoda = ("%s" % metoda).lower()
	if metoda in METODE_SS_VECHI:
		return None, _("Metoda %s este veche și nesigură; cere furnizorului una nouă (aes-256-gcm sau "
			"chacha20-ietf-poly1305).") % metoda
	if metoda not in METODE_SS:
		return None, _("Metoda %s nu este cunoscută.") % metoda[:40]
	secrete = {}
	campuri = ["parola"]
	if parola:
		if not _secretBun(parola):
			return None, _("Parola nu este bună (cel mult %d semne, pe un singur rând).") % MAX_SECRET
		secrete["parola"] = parola
	return {"titlu": _titluCurat(titlu, "Shadowsocks, %s" % server), "date": {"server": server, "port": str(port),
		"metoda": metoda}, "secrete": secrete, "campuri": campuri, "remote": [(server, str(port), "tcp")]}, ""


def _ssDinUri(uri):
	"""(server, port, metoda, parola, titlu) din ss:// (SIP002 sau forma veche, toata in base64), sau (None, motivul)."""
	try:
		from urllib.parse import unquote
	except ImportError:
		from urllib import unquote
	rest = uri.strip()[5:]
	titlu = ""
	if "#" in rest:
		rest, eticheta = rest.split("#", 1)
		titlu = unquote(eticheta)
	interogare = ""
	if "?" in rest:
		rest, interogare = rest.split("?", 1)
	rest = rest.rstrip("/")
	if re.search(r"(?i)(^|[&;])plugin=", interogare):
		return None, _("Directiva %s nu este primită: %s.") % ("plugin", _(_PROGRAME))
	try:
		if "@" in rest:
			info, gazda = rest.rsplit("@", 1)
			info = unquote(info)
			if ":" not in info:
				info = _b64Text(info)
		else:
			info, gazda = _b64Text(rest).rsplit("@", 1)
	except (ValueError, binascii.Error, UnicodeDecodeError):
		return None, _("Adresa ss:// nu este bună.")
	if ":" not in info:
		return None, _("Adresa ss:// nu este bună.")
	metoda, parola = info.split(":", 1)
	e = _desparteEndpoint(gazda)
	if e is None:
		return None, _("Adresa serverului nu este bună: %s") % gazda[:60]
	return (e[0], e[1], metoda, parola, titlu), ""


def analizeazaSs(text, nume=""):
	"""Shadowsocks: ss:// (unul sau mai multe, cate unul pe rand), configurarea JSON a lui ss-local sau lista SIP008
	{"servers": [...]}. Fiecare server devine un profil."""
	t = (text or "").lstrip("﻿").strip()
	profiluri, greseli = [], []
	if t.lower().startswith("ss://"):
		for rand in t.split():
			if not rand.lower().startswith("ss://"):
				continue
			x, motiv = _ssDinUri(rand)
			if x is None:
				greseli.append(motiv)
				continue
			p, motiv = _profilSs(*x)
			(profiluri.append(p) if p else greseli.append(motiv))
	else:
		try:
			d = json.loads(t)
		except ValueError:
			return _greseala("shadowsocks", _("Fișierul nu este text."))
		lista = d.get("servers") if isinstance(d, dict) and isinstance(d.get("servers"), list) else [d]
		for x in lista[:MAX_MEMBRI]:
			if not isinstance(x, dict):
				continue
			if x.get("plugin"):
				greseli.append(_("Directiva %s nu este primită: %s.") % ("plugin", _(_PROGRAME)))
				continue
			p, motiv = _profilSs(str(x.get("server", "")), str(x.get("server_port", "")), str(x.get("method", "")),
				x.get("password") if isinstance(x.get("password"), str) else "", str(x.get("remarks") or x.get("tag") or ""))
			(profiluri.append(p) if p else greseli.append(motiv))
	rez = _analizaBuna("shadowsocks", profiluri)
	if greseli:
		rez["greseli"] = greseli + (rez["greseli"] if not profiluri else [])
		rez["ok"] = bool(profiluri)
	return rez


def _profilIkev2(server, port="500", id_server="", auth="eap", ca=None, nume="", parola="", psk="", ike="", esp="",
		id_local="", titlu=""):
	"""Un profil IKEv2 verificat sau (None, motivul). `auth`: "eap" (nume si parola, serverul cu certificat), "psk"
	(cheia comuna) sau "psk-eap"."""
	if not _gazdaBuna(server or ""):
		return None, _("Adresa serverului nu este bună: %s") % ("%s" % server)[:60]
	if not _PORT(str(port or "500")):
		return None, _("Rândul %s nu este bun.") % "port"
	id_server = id_server or server
	if not _ID_IKE.match(id_server):
		return None, _("Rândul %s nu este bun.") % "RemoteIdentifier"
	if id_local and not _ID_IKE.match(id_local):
		return None, _("Rândul %s nu este bun.") % "LocalIdentifier"
	for x in (ike, esp):
		if x and not _PROPUNERE.match(x):
			return None, _("Rândul %s nu este bun.") % x[:40]
	if auth not in ("eap", "psk", "psk-eap"):
		return None, _("Autentificarea cu certificatul clientului (.p12) nu este primită încă. Folosește numele și "
			"parola.")
	campuri = (["psk"] if auth.startswith("psk") else []) + (["nume", "parola"] if auth.endswith("eap") else [])
	secrete = {}
	if nume:
		if not _NUME_CONT.match(nume):
			return None, _("Numele nu este bun (litere, cifre și . _ @ + - =, cel mult 128).")
		secrete["nume"] = nume
	for cheie, v in (("parola", parola), ("psk", psk)):
		if v:
			if not _secretBun(v):
				return None, _("Parola nu este bună (cel mult %d semne, pe un singur rând).") % MAX_SECRET
			secrete[cheie] = v
	date = {"server": server, "port": str(port or "500"), "id_server": id_server, "auth": auth, "ca": list(ca or [])[:8],
		"ike": ike or "", "esp": esp or "", "id_local": id_local or ""}
	return {"titlu": _titluCurat(titlu, "IKEv2, %s" % server), "date": date, "secrete": secrete, "campuri": campuri,
		"remote": [(server, str(port or "500"), "udp")]}, ""


def analizeazaSswan(text, ca=None):
	"""Profilul strongSwan pentru Android (.sswan, JSON)."""
	try:
		d = json.loads((text or "").lstrip("﻿"))
	except ValueError:
		return _greseala("ikev2", _("Fișierul nu este text."))
	if not isinstance(d, dict) or not isinstance(d.get("remote"), dict):
		return _greseala("ikev2", _("Fișierul nu are serverul (remote)."))
	r = d["remote"]
	tip = str(d.get("type", ""))
	auth = {"ikev2-eap": "eap", "ikev2-eap-only": "eap"}.get(tip, "cert")
	ca = list(ca or [])
	if isinstance(r.get("cert"), str):
		try:
			ca.append(_pemDinDer(base64.b64decode(r["cert"], validate=True)))
		except (binascii.Error, ValueError):
			return _greseala("ikev2", _("Lipsește certificatul serverului (ca)."))
	local = d.get("local") if isinstance(d.get("local"), dict) else {}
	p, motiv = _profilIkev2(str(r.get("addr", "")), str(r.get("port") or "500"), str(r.get("id") or ""), auth, ca,
		nume=str(local.get("eap_id") or ""), ike=str(d.get("ike-proposal") or ""), esp=str(d.get("esp-proposal") or ""),
		titlu=str(d.get("name") or ""))
	return _analizaBuna("ikev2", [p]) if p else _greseala("ikev2", motiv)


def _plist(text):
	"""Dictionarul unui .mobileconfig (XML), cu DOCTYPE-ul Apple primit si orice alt DOCTYPE sau ENTITY refuzat."""
	x = _textPlist(text)
	if not x:
		return None
	x = _DOCTYPE_PLIST.sub("", x, count=1)
	if "<!DOCTYPE" in x or "<!ENTITY" in x:
		return None
	try:
		import plistlib
	except ImportError:
		return "fara plistlib"
	try:
		return plistlib.loads(x.encode("utf-8"))
	except Exception:
		return None


def _sirPlist(x):
	if isinstance(x, bytes):
		return x.decode("utf-8", "replace")
	return x if isinstance(x, str) else ""


def analizeazaMobileconfig(text, ca=None):
	"""Profilul Apple (.mobileconfig) cu VPN IKEv2 sau L2TP; certificatele radacina din el (com.apple.security.root,
	.pem, .pkcs1) se iau ca autoritati pentru server."""
	d = _plist(text)
	if d == "fara plistlib":
		return _greseala("ikev2", _("Profilurile .mobileconfig nu se pot citi pe acest receptor. Scrie datele de mână."))
	if not isinstance(d, dict):
		return _greseala("ikev2", _("Fișierul nu este un profil .mobileconfig bun."))
	continut = [x for x in (d.get("PayloadContent") or []) if isinstance(x, dict)]
	ca = list(ca or [])
	for x in continut:
		if x.get("PayloadType") in ("com.apple.security.root", "com.apple.security.pem", "com.apple.security.pkcs1"):
			v = x.get("PayloadContent")
			if isinstance(v, bytes) and v[:1] == b"\x30":
				ca.append(_pemDinDer(v))
			elif isinstance(v, (bytes, str)):
				ca += certificateDin(_sirPlist(v))
	profiluri, greseli, fel = [], [], "ikev2"
	for x in continut:
		if x.get("PayloadType") != "com.apple.vpn.managed":
			continue
		titlu = str(x.get("UserDefinedName") or x.get("PayloadDisplayName") or "")
		if x.get("VPNType") == "IKEv2" and isinstance(x.get("IKEv2"), dict):
			k = x["IKEv2"]
			metoda = str(k.get("AuthenticationMethod") or "None")
			eap = bool(k.get("ExtendedAuthEnabled"))
			auth = {"None": "eap", "SharedSecret": "psk-eap" if eap else "psk"}.get(metoda, "cert")
			p, motiv = _profilIkev2(str(k.get("RemoteAddress") or ""), "500", str(k.get("RemoteIdentifier") or ""), auth,
				ca, nume=str(k.get("AuthName") or "") if auth.endswith("eap") else "",
				parola=str(k.get("AuthPassword") or "") if auth.endswith("eap") else "",
				psk=_sirPlist(k.get("SharedSecret")) if auth.startswith("psk") else "",
				id_local=str(k.get("LocalIdentifier") or "") if auth.startswith("psk") else "", titlu=titlu)
			(profiluri.append(p) if p else greseli.append(motiv))
		elif x.get("VPNType") == "L2TP" and isinstance(x.get("PPP"), dict):
			fel = "l2tp"
			ppp, sec = x["PPP"], x.get("IPSec") if isinstance(x.get("IPSec"), dict) else {}
			p, motiv = _profilL2tp(str(ppp.get("CommRemoteAddress") or ""), str(ppp.get("AuthName") or ""),
				str(ppp.get("AuthPassword") or ""), _sirPlist(sec.get("SharedSecret")), titlu)
			(profiluri.append(p) if p else greseli.append(motiv))
		elif x.get("VPNType"):
			greseli.append(_("Felul %s din profil nu este primit.") % str(x.get("VPNType"))[:20])
	rez = _analizaBuna(fel, profiluri)
	if greseli and not profiluri:
		rez["greseli"] = greseli
	return rez


def _profilL2tp(server, nume="", parola="", psk="", titlu=""):
	if not _gazdaBuna(server or ""):
		return None, _("Adresa serverului nu este bună: %s") % ("%s" % server)[:60]
	secrete = {}
	if nume:
		if not _NUME_CONT.match(nume):
			return None, _("Numele nu este bun (litere, cifre și . _ @ + - =, cel mult 128).")
		secrete["nume"] = nume
	for cheie, v in (("parola", parola), ("psk", psk)):
		if v:
			if not _secretBun(v):
				return None, _("Parola nu este bună (cel mult %d semne, pe un singur rând).") % MAX_SECRET
			secrete[cheie] = v
	return {"titlu": _titluCurat(titlu, "L2TP, %s" % server), "date": {"server": server}, "secrete": secrete,
		"campuri": ["psk", "nume", "parola"], "remote": [(server, "500", "udp")]}, ""


def _profilOc(adresa, protocol="anyconnect", grup="", pin="", nume="", parola="", titlu=""):
	"""Un profil OpenConnect verificat sau (None, motivul). `adresa`: https://server[:port][/cale] sau numele serverului."""
	adresa = (adresa or "").strip()
	if adresa and not adresa.lower().startswith("https://"):
		adresa = "https://" + adresa.split("://", 1)[-1]
	m = _URL_OC.match(adresa)
	if not m or not _gazdaBuna(m.group(1)) or (m.group(2) and not _PORT(m.group(2))):
		return None, _("Adresa serverului nu este bună: %s") % adresa[:60]
	protocol = (protocol or "anyconnect").lower()
	if protocol not in PROTOCOALE_OC:
		return None, _("Rândul %s nu este bun.") % "protocol"
	if grup and not _sigur(grup):
		return None, _("Rândul %s nu este bun.") % "authgroup"
	if pin and not _PIN_OC.match(pin):
		return None, _("Rândul %s nu este bun.") % "servercert"
	secrete = {}
	if nume:
		if not _campBun(nume):
			return None, _("Numele nu este bun (cel mult %d semne, pe un singur rând).") % MAX_CAMP_CONT
		secrete["nume"] = nume
	if parola:
		if not _secretBun(parola):
			return None, _("Parola nu este bună (cel mult %d semne, pe un singur rând).") % MAX_SECRET
		secrete["parola"] = parola
	port = m.group(2) or "443"
	return {"titlu": _titluCurat(titlu, "OpenConnect, %s" % m.group(1)), "date": {"url": adresa, "server": m.group(1),
		"port": port, "protocol": protocol, "grup": grup or "", "pin": pin or ""}, "secrete": secrete,
		"campuri": ["nume", "parola"], "remote": [(m.group(1), port, "tcp")]}, ""


def analizeaza(fel, text, nume="", ca=None):
	"""Analiza unui text de felul `fel` (protocoalele noi): {"ok", "fel", "greseli", "note", "profiluri"}."""
	if fel == "shadowsocks":
		return analizeazaSs(text, nume)
	if fel in ("ikev2", "l2tp"):
		if _textPlist(text):
			return analizeazaMobileconfig(text, ca)
		return analizeazaSswan(text, ca)
	if fel == "openconnect":
		p, motiv = _profilOc((text or "").strip())
		return _analizaBuna(fel, [p]) if p else _greseala(fel, motiv)
	return _greseala(fel, _("Felul %s nu este cunoscut.") % fel)


def analizeazaCampuri(campuri, ca=None):
	"""Datele scrise de mana (ecranul, pagina web, HdsVpnFurnizori): {"fel", "server", "nume", "parola", "psk",
	"protocol", "grup", "id_server", "port", "metoda", "titlu"}."""
	c = dict((k, ("%s" % v).strip() if k not in ("parola", "psk") else "%s" % v) for k, v in (campuri or {}).items()
		if v is not None)
	fel = c.get("fel", "")
	server = c.get("server", "")
	if fel == "openconnect":
		p, motiv = _profilOc(server, c.get("protocol") or "anyconnect", c.get("grup", ""), c.get("pin", ""),
			c.get("nume", ""), c.get("parola", ""), c.get("titlu", ""))
	elif fel == "ikev2":
		auth = "psk-eap" if c.get("psk") and c.get("nume") else ("psk" if c.get("psk") else "eap")
		p, motiv = _profilIkev2(server, c.get("port") or "500", c.get("id_server", ""), auth, ca, c.get("nume", ""),
			c.get("parola", ""), c.get("psk", ""), titlu=c.get("titlu", ""))
	elif fel == "l2tp":
		p, motiv = _profilL2tp(server, c.get("nume", ""), c.get("parola", ""), c.get("psk", ""), c.get("titlu", ""))
	elif fel == "shadowsocks":
		gazda, port = server, c.get("port", "")
		e = _desparteEndpoint(server)
		if e:
			gazda, port = e
		p, motiv = _profilSs(gazda, port or "8388", c.get("metoda") or "chacha20-ietf-poly1305", c.get("parola", ""),
			c.get("titlu", ""))
	else:
		return _greseala(fel, _("Alege felul VPN-ului."))
	return _analizaBuna(fel, [p]) if p else _greseala(fel, motiv)


def _caleSecret(p):
	return "%s/%s.secret" % (DOSAR_PROFILURI, p["id"])


def dateProfil(p):
	"""Datele (fara secrete) unui profil al protocoalelor noi, din <id>.json."""
	return _citesteJson(_caleProfil(p), MAX_FISIER * 4) or {}


def secreteProfil(p):
	"""Datele de acces ale profilului (numai pentru pornire; puse si in lista textelor ascunse din jurnal)."""
	d = _citesteJson(_caleSecret(p), 8192) or {}
	rez = dict((k, d[k]) for k in CAMPURI if isinstance(d.get(k), str) and d[k])
	_SECRETE.update(rez.values())
	return rez


def campuriLipsa(p):
	"""Ce trebuie sa mai scrie omul ca profilul `p` (dict sau id) sa porneasca: lista din "nume", "parola", "psk"."""
	if isinstance(p, str):
		p = profil(p)
	if p is None:
		return []
	if p["fel"] == "openvpn":
		return ["nume", "parola"] if (p.get("cere_cont") and not areCont()) else []
	if p["fel"] == "wireguard":
		return []
	d = _citesteJson(_caleSecret(p), 8192) or {}
	return [c for c in (p.get("campuri") or []) if c in CAMPURI and not (isinstance(d.get(c), str) and d[c])]


def _campBunPentru(fel, cheie, v):
	if cheie == "nume":
		if fel in ("ikev2", "l2tp"):
			return bool(_NUME_CONT.match(v or "")), _("Numele nu este bun (litere, cifre și . _ @ + - =, cel mult 128).")
		return _campBun(v), _("Numele nu este bun (cel mult %d semne, pe un singur rând).") % MAX_CAMP_CONT
	return _secretBun(v), _("Parola nu este bună (cel mult %d semne, pe un singur rând).") % MAX_SECRET


def salveazaSecrete(id_profil, **campuri):
	"""Numele, parola sau cheia comuna ale unui profil (0600, langa el; la OpenVPN contul comun). Numai cheile date se
	schimba. (reusit, mesaj)."""
	p = profil(id_profil)
	if p is None:
		return False, _("Serverul nu mai există.")
	campuri = dict((k, v) for k, v in campuri.items() if v is not None)
	if p["fel"] == "openvpn":
		return salveazaCont(campuri.get("nume", ""), campuri.get("parola", ""))
	if p["fel"] == "wireguard":
		return False, _("WireGuard nu are nume și parolă: cheia e în fișier.")
	for k, v in campuri.items():
		if k not in CAMPURI:
			return False, _("Rândul %s nu este bun.") % k[:20]
		if k == "nume":
			v = campuri[k] = v.strip()
		bun, motiv = _campBunPentru(p["fel"], k, v)
		if not bun:
			return False, motiv
	d = _citesteJson(_caleSecret(p), 8192) or {}
	d = dict((k, d[k]) for k in CAMPURI if isinstance(d.get(k), str))
	d.update(campuri)
	_SECRETE.update(v for v in campuri.values() if v)
	_dosar(DOSAR)
	_dosar(DOSAR_PROFILURI)
	_scrieAtomic(_caleSecret(p), json.dumps(d), 0o600)
	jurnal("datele de acces ale serverului %s au fost salvate" % p["id"])
	return True, _("Datele de acces sunt salvate. Nu se mai arată nicăieri.")


def salveazaSecreteGrup(grup, fel, **campuri):
	"""Aceleasi date de acces pe toate profilurile felului `fel` din grup (HdsVpnFurnizori: contul furnizorului)."""
	n = 0
	for p in profiluriGrup(grup):
		if p["fel"] == fel and fel not in FELURI_FISIER:
			reusit, mesaj = salveazaSecrete(p["id"], **campuri)
			if not reusit:
				return False, mesaj
			n += 1
	return True, _("Datele de acces sunt salvate. Nu se mai arată nicăieri.") if n else _("Nimic de adăugat.")


def _salveazaProfilNou(grup, fel, x, lista, ids, titluri, nume_fisier=""):
	"""Pune pe receptor un profil al protocoalelor noi (analiza `x`); (id, nou)."""
	date = dict(x["date"], fel=fel)
	id_p = hashlib.sha1(("%s\n%s" % (grup, json.dumps(date, sort_keys=True))).encode("utf-8")).hexdigest()[:12]
	if id_p in ids:
		return id_p, False
	titlu, baza, k = x["titlu"], x["titlu"], 2
	while titlu in titluri:
		titlu = "%s %d" % (baza, k)
		k += 1
	p = {"id": id_p, "titlu": titlu, "fel": fel, "grup": grup, "fisier": "%s.json" % id_p,
		"nume_fisier": _numeCurat(nume_fisier or titlu), "gazde": ["%s:%s" % (r[0], r[1]) for r in x["remote"]][:16],
		"proto": x["remote"][0][2] if x["remote"] else "udp", "remote": [list(r) for r in x["remote"]][:16],
		"cere_cont": "parola" in x["campuri"], "campuri": [c for c in x["campuri"] if c in CAMPURI], "plin": True,
		"adaugat": int(time.time())}
	_dosar(DOSAR)
	_dosar(DOSAR_PROFILURI)
	_scrieAtomic(_caleProfil(p), json.dumps(date, ensure_ascii=False), 0o600)
	lista.append(p)
	ids.add(id_p)
	titluri.add(titlu)
	return id_p, True


def _grupPentru(fel, grup, s):
	if grup and grupCunoscut(grup) and fel in feluriGrup(grup):
		return grup
	if fel in feluriGrup(s["furnizor"]):
		return s["furnizor"]
	return GRUP_FEL[fel]


def adaugaVpn(fisiere=(), text="", campuri=None, grup=None):
	"""Adauga VPN: fisiere (lista de (nume, octeti), si arhive .zip), un text lipit sau datele scrise de mana
	(`campuri`, vezi analizeazaCampuri), recunoscute dupa continut. Grupul: `grup` daca primeste felul, altfel
	furnizorul ales daca il primeste, altfel grupul felului (GRUP_FEL). Numele, parola si cheia comuna din `campuri`
	se pun pe profilurile adaugate. Cu VPN-ul oprit, primul server adaugat devine cel ales. (reusit, mesaj, {"ids",
	"lipsesc", "fel", "grup", "adaugate", "la_fel", "refuzate", "motive"})."""
	campuri = dict(campuri or {})
	s = setari()
	greseli = []
	desfacute = []
	for nume, date in fisiere or ():
		if nume.lower().endswith(".zip"):
			desfacute += _membriArhiva(nume, date, greseli)
		elif len(date) <= MAX_FISIER:
			desfacute.append((nume, date))
		else:
			greseli.append(_("Fișierul %s este prea mare.") % _numeCurat(nume))
	if text and text.strip():
		if len(text) > MAX_FISIER:
			greseli.append(_("Fișierul %s este prea mare.") % "text")
		else:
			desfacute.append(("", text.encode("utf-8")))
	alaturi, ca = {}, []
	principale = []
	for nume, date in desfacute:
		n = nume.replace("\\", "/").rsplit("/", 1)[-1]
		t = date.decode("utf-8", "replace")
		fel = recunoaste(t, n)
		if fel:
			principale.append((nume, t, fel))
			continue
		if n.lower().endswith(EXT_ALATURI):
			nn = _numeAlaturi(n)
			if date[:1] == b"\x30" and len(date) > 64:
				t = _pemDinDer(date)
			if nn:
				alaturi[nn] = t
			ca += certificateDin(t)
		elif n.lower().endswith((".ovpn", ".conf", ".sswan", ".mobileconfig", ".json", ".txt")) or not nume:
			greseli.append(_("%s: nu recunosc felul VPN-ului din el.") % (_numeCurat(nume) if nume else _("Textul")))
	manual = not principale and campuri.get("fel") in FELURI and bool(campuri.get("server"))
	if not principale and not manual:
		return False, (greseli[0] if greseli else _("Nu am găsit niciun VPN în ce ai dat.")), {"motive": greseli[:5],
			"ids": [], "lipsesc": []}
	lista = profiluri()
	ids = set(p["id"] for p in lista)
	adaugate = la_fel = refuzate = 0
	ids_noi, motive = [], list(greseli)
	grupuri_folosite = []
	pe_grupuri = {}
	for nume, t, fel in principale[:MAX_MEMBRI]:
		if fel in FELURI_FISIER:
			pe_grupuri.setdefault(_grupPentru(fel, grup, s), []).append((nume or "VPN.ovpn", t.encode("utf-8")))
	for g, lot in sorted(pe_grupuri.items()):
		alaturi_lot = [(n, v.encode("utf-8")) for n, v in sorted(alaturi.items())]
		reusit, mesaj, d = importa(lot + alaturi_lot, g)
		adaugate += d.get("adaugate", 0)
		la_fel += d.get("la_fel", 0)
		refuzate += d.get("refuzate", 0)
		motive += d.get("motive", [])
		ids_noi += [i for i in d.get("ids", []) if i not in ids_noi]
		if d.get("ids"):
			grupuri_folosite.append(g)
	lista = profiluri()
	ids = set(p["id"] for p in lista)
	analize = []
	for nume, t, fel in principale[:MAX_MEMBRI]:
		if fel not in FELURI_FISIER:
			analize.append((nume, fel, analizeaza(fel, t, nume, ca)))
	if manual:
		analize.append(("", campuri["fel"], analizeazaCampuri(campuri, ca)))
	schimbat = False
	for nume, fel, a in analize:
		fel = a.get("fel") or fel
		cap, motiv_cap = capabil(fel)
		if cap == "nu":
			refuzate += 1
			motive.append(motiv_cap)
			continue
		if not a["ok"]:
			refuzate += 1
			motive.append(("%s: %s" % (_numeCurat(nume), a["greseli"][0])) if nume else a["greseli"][0])
			continue
		g = _grupPentru(fel, grup, s)
		titluri = set(p["titlu"] for p in lista if p.get("grup") == g)
		for x in a["profiluri"]:
			if len(lista) >= MAX_PROFILURI:
				refuzate += 1
				motive.append(_("Sunt deja %d servere; șterge din ele.") % MAX_PROFILURI)
				break
			id_p, nou = _salveazaProfilNou(g, fel, x, lista, ids, titluri, nume)
			schimbat = schimbat or nou
			adaugate += 1 if nou else 0
			la_fel += 0 if nou else 1
			if id_p not in ids_noi:
				ids_noi.append(id_p)
			if x["secrete"]:
				# datele din fisier (ss://, .mobileconfig) se pun langa profil; cele scrise de mana mai jos
				_scrieSecreteNoi(id_p, x["secrete"])
			if g not in grupuri_folosite:
				grupuri_folosite.append(g)
	if schimbat:
		_scrieIndex(lista)
	secrete_scrise = dict((k, campuri[k]) for k in CAMPURI if campuri.get(k))
	for id_p in ids_noi:
		p = profil(id_p)
		if p and secrete_scrise and p["fel"] not in ("wireguard",):
			if p["fel"] != "openvpn" or ("nume" in secrete_scrise and "parola" in secrete_scrise):
				reusit, mesaj = salveazaSecrete(id_p, **secrete_scrise)
				if not reusit:
					motive.append(mesaj)
	ales = profil(ids_noi[0]) if ids_noi else None
	if ales is not None and not s["pornit"]:
		salveazaSetari(furnizor=ales["grup"], profil=ales["id"])
	lipsesc = campuriLipsa(ales) if ales else []
	parti = []
	if ales is not None:
		parti.append(_("VPN adăugat: %s.") % ales["titlu"] if adaugate <= 1 else _("Servere adăugate: %d.") % adaugate)
		if adaugate == 0 and la_fel:
			parti = [_("Erau deja: %d.") % la_fel]
		if s["pornit"]:
			parti.append(_("Oprește VPN-ul ca să treci pe el."))
		elif lipsesc:
			parti.append(_("Mai scrie: %s.") % ", ".join(textCamp(c) for c in lipsesc))
		else:
			parti.append(_("Apasă VERDE ca să pornești VPN-ul."))
	if refuzate:
		parti.append(_("Nepotrivite: %d.") % refuzate)
	if motive and (refuzate or ales is None):
		parti.append(motive[0])
	jurnal("adauga: %d adaugate, %d la fel, %d refuzate %s" % (adaugate, la_fel, refuzate, motive[:3]))
	return ales is not None, " ".join(parti) or _("Nimic de adăugat."), {"ids": ids_noi, "lipsesc": lipsesc,
		"fel": ales["fel"] if ales else "", "grup": ales["grup"] if ales else "", "adaugate": adaugate, "la_fel": la_fel,
		"refuzate": refuzate, "motive": motive[:5]}


def _scrieSecreteNoi(id_p, secrete):
	p = profil(id_p) or {"id": id_p}
	d = _citesteJson(_caleSecret(p), 8192) or {}
	d.update(dict((k, v) for k, v in secrete.items() if k in CAMPURI and v))
	_SECRETE.update(v for v in secrete.values() if v)
	_dosar(DOSAR_PROFILURI)
	_scrieAtomic(_caleSecret(p), json.dumps(d), 0o600)


def textCamp(c):
	return {"nume": _("numele"), "parola": _("parola"), "psk": _("cheia comună (PSK)")}.get(c, c)


# ---------------------------------------------------------------- stickul

LOCURI_MONTARE = ("/media/", "/run/media/", "/autofs/", "/mnt/")
FS_FARA_DISC = ("tmpfs", "ramfs", "devtmpfs", "proc", "sysfs", "overlay", "squashfs", "nfs", "nfs4", "cifs", "smb3")
DOSAR_STICK = ("hdsatelit", "vpn")


def _montari():
	lista = []
	for linie in (_citeste(CALE_MONTARI) or "").splitlines():
		parti = linie.split()
		if len(parti) >= 3:
			lista.append((parti[1].replace("\\040", " "), parti[2]))
	return lista


def _intrareFaraMajuscule(dosar, nume):
	try:
		for intrare in os.listdir(dosar):
			if intrare.lower() == nume:
				return os.path.join(dosar, intrare)
	except OSError:
		pass
	return None


def dosareStick():
	gasite = []
	for punct, fel in _montari():
		if fel in FS_FARA_DISC or not any(punct.startswith(loc) for loc in LOCURI_MONTARE):
			continue
		cale = _cale(punct)
		for nume in DOSAR_STICK:
			cale = _intrareFaraMajuscule(cale, nume) if cale else None
		if cale and os.path.isdir(cale) and cale not in gasite:
			gasite.append(cale)
	return gasite


def fisiereStick():
	"""(numele relativ, octeti) din dosarele hdsatelit/vpn (si un nivel de subdosare, ca TCP/ si UDP/ din arhive)."""
	rez = []
	for dosar in dosareStick():
		for radacina, dosare, fisiere in os.walk(dosar):
			adancime = radacina[len(dosar):].count(os.sep)
			if adancime >= 1:
				dosare[:] = []
			dosare[:] = sorted(d for d in dosare if not d.startswith("."))
			for n in sorted(fisiere):
				if len(rez) >= MAX_MEMBRI or n.startswith("."):
					continue
				cale = os.path.join(radacina, n)
				try:
					marime = os.path.getsize(cale)
					if marime > (MAX_ARHIVA if n.lower().endswith(".zip") else MAX_FISIER):
						continue
					with open(cale, "rb") as f:
						rez.append((os.path.relpath(cale, dosar).replace(os.sep, "/"), f.read()))
				except (OSError, IOError):
					continue
	return rez


def importaDePeStick(grup):
	if not dosareStick():
		return False, _("Pe stick nu am găsit dosarul hdsatelit/vpn. Pune în el fișierele .ovpn, .conf sau arhiva .zip.")
	fisiere = fisiereStick()
	if not fisiere:
		return False, _("Dosarul hdsatelit/vpn de pe stick este gol.")
	reusit, mesaj, _d = importa(fisiere, grup)
	return reusit, mesaj


def adaugaDePeStick(grup=None):
	"""Adauga VPN de pe stick: tot ce e in hdsatelit/vpn, recunoscut dupa continut (adaugaVpn)."""
	if not dosareStick():
		return False, _("Pe stick nu am găsit dosarul hdsatelit/vpn. Pune în el fișierele .ovpn, .conf sau arhiva .zip.")
	fisiere = fisiereStick()
	if not fisiere:
		return False, _("Dosarul hdsatelit/vpn de pe stick este gol.")
	reusit, mesaj, _d = adaugaVpn(fisiere, grup=grup)
	return reusit, mesaj


# ---------------------------------------------------------------- setarile si contul

SETARI_IMPLICITE = {"furnizor": "hma", "profil": "", "mod": "navigator", "oprire_totala": False, "la_pornire": False,
	"pornit": False, "iptv": True, "adrese": []}


def modEfectiv(s=None):
	"""Modul folosit: "navigator" numai unde nucleul are namespace-uri de retea; altfel "tot" (pe Vu+ alegerea
	navigatorului nici nu se arata)."""
	s = s or setari()
	if s["mod"] == "navigator" and not areNetns():
		return "tot"
	return s["mod"]


def moduriPosibile(fel=""):
	"""Modurile aratate: fara "navigator" pe nucleele fara namespace-uri si la L2TP (interfata ppp nu se muta)."""
	return [m for m in MODURI if m != "navigator" or (areNetns() and fel != "l2tp")]


def adresaBuna(a):
	return bool(a) and len(a) <= 253 and _gazdaBuna(a) and ":" not in a


def setari():
	date = _citesteJson(CALE_SETARI) or {}
	s = dict(SETARI_IMPLICITE)
	if isinstance(date.get("furnizor"), str) and grupCunoscut(date["furnizor"]):
		s["furnizor"] = date["furnizor"]
	if isinstance(date.get("profil"), str) and re.match(r"^([0-9a-f]{12})?\Z", date["profil"]):
		s["profil"] = date["profil"]
	if date.get("mod") in MODURI:
		s["mod"] = date["mod"]
	for k in ("oprire_totala", "la_pornire", "pornit", "iptv"):
		if isinstance(date.get(k), bool):
			s[k] = date[k]
	if isinstance(date.get("adrese"), list):
		s["adrese"] = [a for a in date["adrese"] if isinstance(a, str) and adresaBuna(a)][:MAX_ADRESE]
	return s


def salveazaSetari(**schimbari):
	s = setari()
	for k, v in schimbari.items():
		if k not in SETARI_IMPLICITE:
			raise KeyError(k)
		s[k] = v
	_dosar(DOSAR)
	_scrieAtomic(CALE_SETARI, json.dumps(s, ensure_ascii=False, sort_keys=True), 0o600)
	return s


def adreseDinText(text):
	"""(adresele bune, cele rele) dintr-un text cu nume sau adrese IPv4 despartite prin spatii, virgule sau randuri"""
	bune, rele = [], []
	for a in re.split(r"[\s,;]+", text or ""):
		a = a.strip().lower()
		a = re.sub(r"^[a-z]+://", "", a).split("/", 1)[0]
		if not a:
			continue
		if adresaBuna(a):
			if a not in bune:
				bune.append(a)
		else:
			rele.append(a[:60])
	return bune[:MAX_ADRESE], rele


def areCont():
	text = _citeste(CALE_CONT, 1024)
	return bool(text) and len(text.split("\n")) >= 2 and bool(text.split("\n")[0]) and bool(text.split("\n")[1])


def _campBun(x):
	return isinstance(x, str) and 0 < len(x) <= MAX_CAMP_CONT and all(0x20 <= ord(c) != 0x7f for c in x)


def salveazaCont(nume, parola):
	"""Numele si parola contului (HMA sau alt furnizor OpenVPN), 0600, citite numai de openvpn."""
	nume = (nume or "").strip()
	if not _campBun(nume):
		return False, _("Numele nu este bun (cel mult %d semne, pe un singur rând).") % MAX_CAMP_CONT
	if not _campBun(parola or ""):
		return False, _("Parola nu este bună (cel mult %d semne, pe un singur rând).") % MAX_CAMP_CONT
	_SECRETE.update((nume, parola))
	_dosar(DOSAR)
	_scrieAtomic(CALE_CONT, "%s\n%s\n" % (nume, parola), 0o600)
	jurnal("contul a fost salvat")
	return True, _("Numele și parola sunt salvate. Nu se mai arată nicăieri.")


def stergeCont():
	_sterge(CALE_CONT)
	jurnal("contul a fost sters")
	return True, _("Numele și parola au fost șterse de pe receptor.")


def _secreteDinCont():
	text = _citeste(CALE_CONT, 1024) or ""
	_SECRETE.update(x for x in text.split("\n")[:2] if x)


# ---------------------------------------------------------------- rutarea

def comenziPornire(dev, servere, mod, oprire_totala, ales=(), retele=()):
	"""Comenzile /sbin/ip (fara program) care pun VPN-ul in rutare. `mod`: "tot", "ales" sau "retele" (WireGuard cu
	numai unele retele permise: rute spre ele in tabela principala, ca wg-quick)."""
	c = []
	if mod == "retele":
		for r in retele:
			c.append(["-4", "route", "replace", r, "dev", dev])
		return c
	c.append(["-4", "route", "replace", "default", "dev", dev, "table", TABELA])
	if oprire_totala:
		c.append(["-4", "route", "replace", "unreachable", "default", "metric", METRICA_BLOCARE, "table", TABELA])
	if mod == "tot":
		for ip in servere:
			c.append(["-4", "rule", "add", "to", ip + "/32", "lookup", "main", "priority", PRIO_SERVER])
		c.append(["-4", "rule", "add", "lookup", "main", "suppress_prefixlength", "0", "priority", PRIO_CASA])
		c.append(["-4", "rule", "add", "lookup", TABELA, "priority", PRIO_TOT])
		c.append(["-6", "route", "replace", "unreachable", RETEA_IPV6_INTERNET, "metric", "1"])
	else:
		for ip in ales:
			c.append(["-4", "rule", "add", "to", ip + "/32", "lookup", TABELA, "priority", PRIO_ALES])
	return c


def comenziBlocare(plan):
	"""Oprirea totala fara tunel (cat VPN-ul e cerut, dar nu merge): aceleasi reguli ca la pornire, iar in TABELA numai
	"unreachable default"; legatura spre serverele planului si reteaua din casa raman deschise."""
	c = [["-4", "route", "replace", "unreachable", "default", "metric", METRICA_BLOCARE, "table", TABELA]]
	if plan.get("mod") == "ales":
		return c + comenziReguliAles(plan.get("ales") or [])
	for ip in plan.get("servere") or []:
		c.append(["-4", "rule", "add", "to", ip + "/32", "lookup", "main", "priority", PRIO_SERVER])
	c.append(["-4", "rule", "add", "lookup", "main", "suppress_prefixlength", "0", "priority", PRIO_CASA])
	c.append(["-4", "rule", "add", "lookup", TABELA, "priority", PRIO_TOT])
	c.append(["-6", "route", "replace", "unreachable", RETEA_IPV6_INTERNET, "metric", "1"])
	return c


def aplicaBlocarea(plan):
	return aplicaComenzi(comenziBlocare(plan))


def comenziReguliAles(ales):
	return [["-4", "rule", "add", "to", ip + "/32", "lookup", TABELA, "priority", PRIO_ALES] for ip in ales]


def _stergeReguli(prioritati):
	for p in prioritati:
		for _i in range(MAX_PROFILURI):
			if _ip("-4", "rule", "del", "priority", p)[0] != 0:
				break


def curataRetea(dns=True):
	"""Scoate regulile, tabela VPN si oprirea IPv6; pune la loc DNS-ul de dinainte (`dns`)."""
	_stergeReguli((PRIO_SERVER, PRIO_CASA, PRIO_TOT, PRIO_ALES))
	_ip("-4", "route", "flush", "table", TABELA)
	_ip("-6", "route", "del", "unreachable", RETEA_IPV6_INTERNET, "metric", "1")
	if dns:
		refaDns()


def aplicaComenzi(comenzi):
	rele = 0
	for c in comenzi:
		cod, text = _ip(*c)
		if cod != 0:
			rele += 1
			jurnal("ip %s: %s" % (" ".join(c), text.strip()[:200]))
	return rele


# ---------------------------------------------------------------- DNS

def _caleResolv():
	return os.path.realpath(_cale(CALE_RESOLV))


def aplicaDns(servere):
	"""Pune DNS-ul VPN-ului in resolv.conf; pe cel de dinainte il pastreaza (o data). True daca a scris."""
	servere = [s for s in servere if s][:3] or list(DNS_REZERVA)
	nou = TEXT_RESOLV + "".join("nameserver %s\n" % s for s in servere)
	try:
		with open(_caleResolv(), "rb") as f:
			actual = f.read(65536).decode("utf-8", "replace")
	except (OSError, IOError):
		actual = None
	if actual == nou:
		return False
	if actual is None:
		actual = ""
	if not actual.startswith(TEXT_RESOLV):
		_dosar(DOSAR_RULARE)
		_scrieAtomic(CALE_RESOLV_INAINTE, actual, 0o600)
	_scrieAtomic(_caleResolv(), nou, 0o644, fara_radacina=True)
	return True


def refaDns():
	"""Pune la loc resolv.conf de dinainte de VPN (numai daca acum e al VPN-ului)."""
	inainte = _citeste(CALE_RESOLV_INAINTE)
	if inainte is None:
		return False
	try:
		with open(_caleResolv(), "rb") as f:
			actual = f.read(65536).decode("utf-8", "replace")
	except (OSError, IOError):
		actual = TEXT_RESOLV
	if actual.startswith(TEXT_RESOLV):
		_scrieAtomic(_caleResolv(), inainte, 0o644, fara_radacina=True)
	_sterge(CALE_RESOLV_INAINTE)
	return True


def dnsDinOpenvpn(mediu):
	"""DNS-ul IPv4 dat de server (foreign_option_N = "dhcp-option DNS x.x.x.x")."""
	rez = []
	for i in range(1, 64):
		v = mediu.get("foreign_option_%d" % i)
		if v is None:
			break
		parti = v.split()
		if len(parti) == 3 and parti[0] == "dhcp-option" and parti[1].upper() == "DNS":
			try:
				if ipaddress.ip_address(parti[2]).version == 4 and parti[2] not in rez:
					rez.append(parti[2])
			except ValueError:
				pass
	return rez


# ---------------------------------------------------------------- numele

def rezolva(gazda):
	"""Adresele IPv4 ale gazdei (sau adresa insasi)."""
	try:
		if ipaddress.ip_address(gazda).version == 4:
			return [gazda]
		return []
	except ValueError:
		pass
	if REZOLVATOR is not None:
		return list(REZOLVATOR(gazda))
	try:
		rez = []
		for x in socket.getaddrinfo(gazda, None, socket.AF_INET, socket.SOCK_STREAM):
			if x[4][0] not in rez:
				rez.append(x[4][0])
		return rez
	except (socket.error, UnicodeError, ValueError):
		return []


_URL_IPTV = re.compile(r"(?i)https?%3a//([A-Za-z0-9.\-]{1,253})")


def gazdeIptv():
	"""Gazdele surselor IPTV din buchete (adresele http/https din randurile #SERVICE)."""
	gazde = []
	try:
		nume = sorted(os.listdir(_cale(DOSAR_BUCHETE)))
	except OSError:
		return gazde
	for n in nume[:400]:
		if not (n.startswith("userbouquet.") and n.endswith((".tv", ".radio"))):
			continue
		text = _citeste("%s/%s" % (DOSAR_BUCHETE, n), 4 * 1024 * 1024) or ""
		for rand in text.splitlines():
			if not rand.startswith("#SERVICE "):
				continue
			for g in _URL_IPTV.findall(rand):
				g = g.lower().rstrip(".")
				if adresaBuna(g) and g not in gazde:
					gazde.append(g)
					if len(gazde) >= MAX_GAZDE_IPTV:
						return gazde
	return gazde


def gazdeAles(s=None):
	s = s or setari()
	gazde = list(s["adrese"])
	if s["iptv"]:
		gazde += [g for g in gazdeIptv() if g not in gazde]
	for u in SERVICII_IP:
		g = u.split("/")[2]
		if g not in gazde:
			gazde.append(g)
	return gazde


def ipuriAles(s=None):
	rez = []
	for g in gazdeAles(s):
		for ip in rezolva(g):
			if ip not in rez:
				rez.append(ip)
	return rez[:MAX_ADRESE * 8]


# ---------------------------------------------------------------- procesele

_PROCES = {"openvpn": None}


def _pidViu(pid, semn):
	try:
		with open("/proc/%d/cmdline" % pid, "rb") as f:
			cmd = f.read(8192)
	except (OSError, IOError):
		return False
	return semn.encode("utf-8") in cmd


def pidOpenvpn():
	text = _citeste(CALE_PID, 32)
	try:
		pid = int((text or "").strip())
	except ValueError:
		return None
	if pid > 1 and _pidViu(pid, CALE_PID):
		return pid
	return None


def interfataExista(nume):
	return os.path.isdir(_cale("/sys/class/net/%s" % nume))


def _culegeCopilul():
	p = _PROCES.get("openvpn")
	if p is not None and p.poll() is not None:
		_PROCES["openvpn"] = None


def wgInNetns():
	"""True cand interfata WireGuard a fost mutata in NETNS (sus.json o spune si namespace-ul exista): fara program."""
	sus = _citesteJson(CALE_SUS) or {}
	return sus.get("fel") == "wireguard" and bool(sus.get("netns")) and netnsExista()


def vpnViu():
	_culegeCopilul()
	return (bool(pidOpenvpn()) or interfataExista(INTERFATA_WG) or wgInNetns() or _oricareViu() or
		interfataExista(INTERFATA_PPP))


# ---------------------------------------------------------------- namespace-ul de retea al navigatorului (modul "navigator")

def netnsExista():
	return os.path.exists(_cale(CALE_NETNS)) or os.path.exists(_cale("/run/netns/" + NETNS))


def creeazaNetns():
	"""NETNS cu numai lo pornit (fara nicio iesire pana nu se muta interfata VPN in el). True daca exista dupa."""
	if not netnsExista():
		cod, text = _ip("netns", "add", NETNS)
		if cod != 0:
			jurnal("ip netns add: %s" % text.strip()[:200])
	_ip("-n", NETNS, "link", "set", "lo", "up")
	return netnsExista() or RULATOR is not None


def stergeNetns():
	"""NETNS si DNS-ul lui scoase (VPN-ul nu mai e cerut). Un navigator inca deschis in el ramane fara internet pana se
	inchide (namespace-ul traieste cat il tine un proces)."""
	_ip("-n", NETNS, "link", "del", INTERFATA_WG)
	if netnsExista():
		_ip("netns", "del", NETNS)
	_sterge(CALE_RESOLV_NETNS)


def scrieDnsNetns(servere):
	servere = [s for s in servere if s][:3] or list(DNS_REZERVA)
	d = os.path.dirname(CALE_RESOLV_NETNS)
	_dosar(os.path.dirname(d), 0o755)
	_dosar(d, 0o755)
	_scrieAtomic(CALE_RESOLV_NETNS, TEXT_RESOLV + "".join("nameserver %s\n" % s for s in servere), 0o644)


def prefixNavigator():
	"""Pentru lansatorul navigatorului: [ip, netns, exec, NETNS] cand omul a pornit VPN-ul cu "numai navigatorul si
	HbbTV" (NETNS se face aici daca lipseste: fara tunel inca, navigatorul nu iese direct pe internet), altfel [] (VPN-ul
	oprit sau alt mod: navigatorul porneste ca inainte, fara nicio schimbare)."""
	s = setari()
	if not s["pornit"] or modEfectiv(s) != "navigator":
		return []
	if not netnsExista():
		creeazaNetns()
	return [PROGRAM_IP, "netns", "exec", NETNS]


def comenziNetns(dev, adrese, mtu, plin=True, retele=(), peer=""):
	"""Comenzile /sbin/ip (fara program) care pun interfata VPN `dev` in NETNS: mutarea, adresele, MTU, pornirea si
	rutele (implicita, sau numai retelele permise cand WireGuard nu are 0.0.0.0/0). `peer`: adresa celuilalt capat la
	OpenVPN cu topologia net30/p2p."""
	c = [["link", "set", "dev", dev, "netns", NETNS]]
	for a in adrese:
		c.append(["-n", NETNS, "-4", "address", "add", a] + (["peer", peer] if peer else []) + ["dev", dev])
	c.append(["-n", NETNS, "link", "set", "dev", dev, "mtu", str(mtu), "up"])
	if plin:
		c.append(["-n", NETNS, "-4", "route", "replace", "default", "dev", dev])
	else:
		for r in retele:
			c.append(["-n", NETNS, "-4", "route", "replace", r, "dev", dev])
	return c

def stareOpenvpn(timeout=1.5):
	"""Starea din interfata de administrare a lui openvpn (soclul unix din DOSAR_RULARE): (STARE, adresa din tunel),
	de pilda ("CONNECTED", "10.8.0.6"); ("", "") daca nu raspunde."""
	if not hasattr(socket, "AF_UNIX"):
		return "", ""
	# interfata de administrare primeste un singur client odata: paza si pornirea intreaba pe rand
	with _LACAT_ADMIN:
		return _stareOpenvpn(timeout)


_LACAT_ADMIN = threading.Lock()


def _stareOpenvpn(timeout):
	s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
	s.settimeout(timeout)
	try:
		s.connect(_cale(CALE_SOCLU))
		s.sendall(b"state\n")
		date = b""
		while b"\nEND" not in date and len(date) < 16384:
			bucata = s.recv(4096)
			if not bucata:
				break
			date += bucata
	except (socket.error, OSError):
		return "", ""
	finally:
		try:
			s.close()
		except socket.error:
			pass
	for rand in date.decode("utf-8", "replace").splitlines():
		if rand[:1].isdigit():
			parti = rand.split(",")
			if len(parti) >= 4:
				return parti[1], parti[3]
	return "", ""


def strangereMana(nume=INTERFATA_WG, netns=False):
	"""Secunde de la ultima strangere de mana WireGuard (cea mai noua), None daca nu a fost. Numai
	`wg show <if> latest-handshakes` (niciodata showconf sau dump, care au cheia privata); cu 
etns, in NETNS."""
	pre = [PROGRAM_IP, "netns", "exec", NETNS] if netns else []
	cod, text = _ruleaza(pre + [PROGRAM_WG, "show", nume, "latest-handshakes"], 10)
	if cod != 0:
		return None
	cel_mai_nou = 0
	for rand in text.splitlines():
		parti = rand.split()
		if len(parti) == 2 and parti[1].isdigit():
			cel_mai_nou = max(cel_mai_nou, int(parti[1]))
	if not cel_mai_nou:
		return None
	return max(0, int(time.time()) - cel_mai_nou)


_ERORI_OPENVPN = (
	("AUTH_FAILED", N_("Numele sau parola nu sunt bune. VPN-ul nu mai încearcă singur.")),
	("Cannot open TUN/TAP dev", N_("Interfața tun nu se poate deschide (lipsește tun.ko). Instalează programele VPN.")),
	("TLS key negotiation failed", N_("Serverul nu răspunde. Încearcă alt server sau TCP în loc de UDP.")),
	("TLS handshake failed", N_("Serverul nu răspunde. Încearcă alt server sau TCP în loc de UDP.")),
	("Connection refused", N_("Serverul refuză legătura. Încearcă alt server.")),
	("certificate verify failed", N_("Certificatul serverului nu se potrivește cu fișierul.")),
	("Options error", N_("Fișierul serverului nu merge cu această versiune OpenVPN.")),
	("failed to negotiate cipher", N_("Serverul cere un cifru pe care fișierul nu îl are.")),
	("Unsupported cipher", N_("Serverul cere un cifru pe care fișierul nu îl are.")),
)


def eroareOpenvpn():
	"""(motivul ultimei erori din jurnalul lui openvpn, este eroare de cont)"""
	text = _citeste(CALE_JURNAL_OPENVPN, 262144) or ""
	coada = text[-16384:]
	for semn, motiv in _ERORI_OPENVPN:
		if semn in coada:
			return _(motiv), semn == "AUTH_FAILED"
	return "", False


def _opresteOpenvpn():
	pid = pidOpenvpn()
	p = _PROCES.get("openvpn")
	if pid:
		try:
			os.kill(pid, signal.SIGTERM)
		except OSError:
			pass
		for _i in range(50):
			if not pidOpenvpn():
				break
			time.sleep(0.1)
		if pidOpenvpn():
			try:
				os.kill(pid, signal.SIGKILL)
			except OSError:
				pass
	if p is not None:
		try:
			p.wait(5)
		except Exception:
			pass
		_PROCES["openvpn"] = None
	_sterge(CALE_PID)


def incarcaTun():
	if os.path.exists(_cale(CALE_TUN)):
		return True
	_ruleaza([PROGRAM_MODPROBE, "tun"], 20)
	for _i in range(20):
		if os.path.exists(_cale(CALE_TUN)):
			return True
		time.sleep(0.1)
	if os.path.isdir(_cale("/sys/module/tun")) and hasattr(os, "mknod"):
		try:
			os.makedirs(_cale("/dev/net"), 0o755)
		except OSError:
			pass
		try:
			import stat
			os.mknod(_cale(CALE_TUN), stat.S_IFCHR | 0o600, os.makedev(10, 200))
		except OSError as eroare:
			jurnal("nodul tun: %s" % eroare)
	return os.path.exists(_cale(CALE_TUN))


def _caleScript():
	f = os.path.abspath(__file__)
	return f[:-1] if f.endswith(".pyc") else f


def argumenteOpenvpn(p, remote_ip, cale_profil, netns=False):
	"""Linia de comanda a lui openvpn (fara secrete: numai cai de fisiere). `remote_ip`: [(ip, port, proto)]. Cu
	`netns` (modul "navigator"): interfata o configureaza scriptul --up in NETNS (--ifconfig-noexec), la fiecare
	reconectare (--up-restart, fara --persist-tun: interfata se face din nou si se muta din nou)."""
	script = _caleScript()
	a = [PROGRAM_OPENVPN, "--config", cale_profil, "--client", "--dev", INTERFATA_OPENVPN, "--dev-type", "tun",
		"--route-noexec", "--pull-filter", "ignore", "redirect-gateway", "--pull-filter", "ignore", "route-ipv6",
		"--pull-filter", "ignore", "ifconfig-ipv6", "--pull-filter", "ignore", "block-outside-dns",
		"--persist-key", "--persist-remote-ip", "--resolv-retry", "infinite",
		"--script-security", "2", "--up", "%s %s openvpn-sus" % (PYTHON, script),
		"--down", "%s %s openvpn-jos" % (PYTHON, script),
		"--writepid", CALE_PID, "--management", CALE_SOCLU, "unix", "--auth-retry", "none", "--mute", "20"]
	a += ["--ifconfig-noexec", "--up-restart"] if netns else ["--persist-tun"]
	if p.get("nobind", True):
		a.append("--nobind")
	for ip, port, proto in remote_ip:
		a += ["--remote", ip, str(port), proto]
	if p.get("cere_cont"):
		a += ["--auth-user-pass", CALE_CONT, "--auth-nocache"]
	if p.get("cipher") and not p.get("data_ciphers"):
		a += ["--data-ciphers-fallback", p["cipher"]]
	return a


# ---------------------------------------------------------------- pornirea si oprirea

_LACAT_RETEA = threading.RLock()
# ce stie paza: starea legaturii, ultima eroare, IP-ul vazut pe internet
_STARE = {"legatura": "", "adresa_tunel": "", "eroare": "", "eroare_cont": False, "ip": None, "neconectat_de": 0,
	"reporniri": 0, "urmatoarea": 0, "ales_cand": 0}


def _citestePlan():
	return _citesteJson(CALE_PLAN) or {}


def _rezolvaServere(p):
	"""[(ip, port, proto)] pentru fiecare remote (sau Endpoint) al profilului; si numele care nu s-au rezolvat."""
	rez, nerezolvate = [], []
	remote = [r for r in (p.get("remote") or []) if isinstance(r, list) and len(r) == 3]
	if not remote:
		remote = [list(g.rpartition(":")[::2]) + [p.get("proto", "udp")] for g in p.get("gazde") or []]
	for gazda, port, proto in remote:
		if not (_gazdaBuna(str(gazda)) and _PORT(str(port)) and str(proto) in PROTOCOALE):
			continue
		ips = rezolva(gazda)
		if not ips:
			nerezolvate.append(gazda)
		for ip in ips[:4]:
			rez.append((ip, str(port), str(proto)))
	return rez, nerezolvate


def _pornesteAcum():
	"""Porneste VPN-ul dupa setari (pe firul lucrarilor). (reusit, mesaj)."""
	s = setari()
	p = profil(s["profil"])
	if p is None or p.get("grup") != s["furnizor"]:
		return False, _("Alege întâi un server.")
	fel = p["fel"]
	if fel == "wireguard" and wireguardIndisponibil():
		return False, _(TEXT_WG_INDISPONIBIL)
	poate, motiv = nucleuPoate(fel)
	if not poate:
		return False, motiv
	if not programe().get(fel):
		return False, _("Lipsesc programele VPN. Instalează-le întâi.")
	if fel == "openvpn" and p.get("cere_cont") and not areCont():
		return False, _("Scrie întâi numele și parola contului.")
	lipsa = campuriLipsa(p)
	if lipsa:
		return False, _("Mai scrie: %s.") % ", ".join(textCamp(c) for c in lipsa)
	mod = modEfectiv(s)
	if mod == "navigator" and fel == "l2tp":
		return False, _("L2TP nu poate trece numai navigatorul prin VPN. Alege alt rând la Ce trece prin VPN.")
	navigator = mod == "navigator"
	# oprirea totala cu reguli (tot traficul, adresele alese); in modul navigator o face chiar NETNS, fara reguli
	blocare = s["oprire_totala"] and s["pornit"] and not navigator
	with _LACAT_RETEA:
		vechi = _citestePlan()
		_opresteTot(curata_dns=True, sterge_netns=not (navigator and s["pornit"]))
		if navigator:
			creeazaNetns()
		# cu oprirea totala, internetul ramane oprit si cat se cauta serverul (DNS-ul de acasa merge prin reteaua din
		# casa); legatura spre serverele planului de dinainte ramane deschisa
		if blocare and vechi:
			aplicaBlocarea(vechi)
		_dosar(DOSAR_RULARE)
		_sterge(CALE_OPRIRE)
		_sterge(CALE_SUS)
		_sterge(CALE_SOCLU)
		servere, nerezolvate = _rezolvaServere(p)
		if not servere:
			return False, _("Nu găsesc adresa serverului %s. Verifică legătura la internet.") % ", ".join(nerezolvate)[:80]
		ales = ipuriAles(s) if mod == "ales" else []
		plan = {"fel": fel, "mod": mod, "oprire_totala": s["oprire_totala"], "profil": p["id"],
			"servere": sorted(set(ip for ip, _p, _x in servere)), "ales": ales, "cand": int(time.time())}
		_scrieAtomic(CALE_PLAN, json.dumps(plan), 0o600)
		if blocare:
			curataRetea(dns=False)
			aplicaBlocarea(plan)
		_STARE.update(eroare="", eroare_cont=False, ip=None, neconectat_de=time.time(), ales_cand=time.time())
		if fel == "openvpn":
			reusit, mesaj = _pornesteOpenvpn(p, servere, navigator)
		elif fel == "wireguard":
			reusit, mesaj = _pornesteWg(p, servere, plan)
		else:
			reusit, mesaj = {"openconnect": _pornesteOpenconnect, "shadowsocks": _pornesteSs, "ikev2": _pornesteIkev2,
				"l2tp": _pornesteL2tp}[fel](p, servere, plan)
	if reusit:
		_pornestePaza()
	return reusit, mesaj


def _pornesteOpenvpn(p, servere, netns=False):
	_secreteDinCont()
	if not incarcaTun():
		return False, _("Interfața tun nu se poate deschide (lipsește tun.ko). Instalează programele VPN.")
	argv = argumenteOpenvpn(p, servere, _cale(_caleProfil(p)), netns)
	jurnal("pornesc openvpn: %s" % " ".join(argv))
	try:
		fd = os.open(_cale(CALE_JURNAL_OPENVPN), os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0),
			0o600)
	except OSError:
		fd = subprocess.DEVNULL
	try:
		proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=fd, stderr=subprocess.STDOUT, close_fds=True,
			start_new_session=True, cwd="/")
	except OSError as eroare:
		return False, _("OpenVPN nu a pornit: %s") % eroare
	finally:
		if fd is not subprocess.DEVNULL:
			os.close(fd)
	_PROCES["openvpn"] = proc
	limita = time.time() + TIMP_CONECTARE_S
	while time.time() < limita:
		if proc.poll() is not None:
			motiv, de_cont = eroareOpenvpn()
			_STARE.update(eroare=motiv or _("OpenVPN s-a oprit. Vezi fișierul serverului."), eroare_cont=de_cont)
			# cu oprirea totala si VPN-ul cerut, scriptul --down a lasat oprirea; altfel rutarea se scoate (in modul
			# navigator nu e nimic de scos: NETNS ramane fara iesire)
			if not (setari()["oprire_totala"] and setari()["pornit"]) and not netns:
				curataRetea()
			return False, _STARE["eroare"]
		st, adresa = stareOpenvpn()
		if st == "CONNECTED" and os.path.exists(_cale(CALE_SUS)):
			_STARE.update(legatura="CONNECTED", adresa_tunel=adresa)
			return True, _("Conectat la %s.") % p["titlu"]
		time.sleep(0.5)
	return True, _("Se conectează încă la %s.") % p["titlu"]


def _pornesteWg(p, servere, plan):
	a = analizeazaWg(textProfil(p))
	if not a["ok"]:
		return False, a["greseli"][0]
	a["cheie_privata"] = cheiePrivataWg(textProfil(p))
	endpointuri = {}
	for x in a["peers"]:
		g, pt = x["endpoint"]
		ips = rezolva(g)
		if not ips:
			return False, _("Nu găsesc adresa serverului %s. Verifică legătura la internet.") % g
		endpointuri[(g, pt)] = ips[0]
	navigator = plan["mod"] == "navigator"
	if not areWireguardInNucleu():
		# modulul din feed (kernel-module-wireguard-<nucleu>) nu se incarca singur pe toate imaginile
		_ruleaza([PROGRAM_MODPROBE, "wireguard"], 20)
	_ip("link", "del", INTERFATA_WG)
	if navigator:
		_ip("-n", NETNS, "link", "del", INTERFATA_WG)
	# interfata se face in namespace-ul de baza: acolo ramane socketul UDP (legatura criptata iese pe placa de retea)
	cod, text = _ip("link", "add", "dev", INTERFATA_WG, "type", "wireguard")
	if cod != 0:
		return False, _("Nucleul nu a făcut interfața WireGuard: %s") % text.strip()[:80]
	_scrieAtomic(CALE_WG_CONF, textSetconf(a, endpointuri), 0o600)
	try:
		cod, text = _ruleaza([PROGRAM_WG, "setconf", INTERFATA_WG, _cale(CALE_WG_CONF)])
	finally:
		_sterge(CALE_WG_CONF)
	if cod != 0:
		_ip("link", "del", INTERFATA_WG)
		return False, _("WireGuard nu a primit fișierul: %s") % ascunde(text.strip())[:80]
	if navigator:
		retele = [] if a["plin"] else [r for x in a["peers"] for r in x["permise"] if ":" not in r]
		rele = aplicaComenzi(comenziNetns(INTERFATA_WG, a["adrese"], a.get("mtu") or 1420, a["plin"], retele))
		if rele:
			_ip("-n", NETNS, "link", "del", INTERFATA_WG)
			_ip("link", "del", INTERFATA_WG)
			return False, _("Nucleul nu a făcut interfața WireGuard: %s") % NETNS
		dns = a["dns"] or list(DNS_REZERVA)
		scrieDnsNetns(dns)
		_scrieAtomic(CALE_SUS, json.dumps({"fel": "wireguard", "dev": INTERFATA_WG, "dns": dns, "retele": retele,
			"netns": True, "cand": int(time.time())}), 0o600)
		return True, _("Pornit spre %s.") % p["titlu"]
	for adr in a["adrese"]:
		_ip("-4", "address", "add", adr, "dev", INTERFATA_WG)
	_ip("link", "set", "mtu", str(a.get("mtu") or 1420), "up", "dev", INTERFATA_WG)
	if a["plin"]:
		mod = plan["mod"]
		aplicaComenzi(comenziPornire(INTERFATA_WG, sorted(set(endpointuri.values())), mod, plan["oprire_totala"],
			plan["ales"]))
		dns = a["dns"] or list(DNS_REZERVA)
		if mod == "tot":
			aplicaDns(dns)
		retele = []
	else:
		retele = [r for x in a["peers"] for r in x["permise"] if ":" not in r]
		aplicaComenzi(comenziPornire(INTERFATA_WG, [], "retele", False, retele=retele))
		dns = []
	_scrieAtomic(CALE_SUS, json.dumps({"fel": "wireguard", "dev": INTERFATA_WG, "dns": dns, "retele": retele,
		"cand": int(time.time())}), 0o600)
	return True, _("Pornit spre %s.") % p["titlu"]


def _opresteTot(curata_dns=True, sterge_netns=True):
	"""Opreste procesul si interfetele si scoate rutarea. `sterge_netns` False: NETNS ramane (fara tunel, deci fara
	iesire), cat VPN-ul e cerut in modul navigator."""
	_dosar(DOSAR_RULARE)
	_scrieAtomic(CALE_OPRIRE, "1\n", 0o600)
	_opresteOpenvpn()
	_opresteProtocoale()
	if interfataExista(INTERFATA_WG):
		_ip("link", "del", INTERFATA_WG)
	if netnsExista():
		_ip("-n", NETNS, "link", "del", INTERFATA_WG)
	if sterge_netns:
		stergeNetns()
	curataRetea(dns=curata_dns)
	_sterge(CALE_SUS)
	_STARE.update(legatura="", adresa_tunel="", ip=None)


def _opresteAcum():
	with _LACAT_RETEA:
		_opresteTot()
		_sterge(CALE_PLAN)
	_STARE.update(eroare="", eroare_cont=False, urmatoarea=0, reporniri=0, neconectat_de=0)
	jurnal("VPN oprit")
	return True, _("VPN-ul este oprit. Internetul merge direct.")


# ---------------------------------------------------------------- scripturile lui openvpn (acest fisier ca program)

def scriptOpenvpn(fel, mediu):
	"""--up (fel "sus") si --down (fel "jos"). Merge ca root, pornit de openvpn; intoarce 0 (altfel openvpn s-ar
	opri)."""
	plan = _citestePlan()
	dev = mediu.get("dev", INTERFATA_OPENVPN)
	if not re.match(r"^[A-Za-z0-9_.\-]{1,15}\Z", dev):
		dev = INTERFATA_OPENVPN
	if fel == "sus" and plan.get("mod") == "navigator":
		return _susNetns(dev, mediu)
	if fel == "sus":
		_stergeReguli((PRIO_SERVER, PRIO_CASA, PRIO_TOT, PRIO_ALES))
		_ip("-4", "route", "flush", "table", TABELA)
		mod = plan.get("mod", "tot")
		rele = aplicaComenzi(comenziPornire(dev, plan.get("servere") or [], mod, bool(plan.get("oprire_totala")),
			plan.get("ales") or []))
		dns = dnsDinOpenvpn(mediu)
		if mod == "tot":
			aplicaDns(dns or list(DNS_REZERVA))
		_dosar(DOSAR_RULARE)
		_scrieAtomic(CALE_SUS, json.dumps({"fel": "openvpn", "dev": dev, "dns": dns, "ip_local": mediu.get(
			"ifconfig_local", ""), "cand": int(time.time()), "comenzi_rele": rele}), 0o600)
		jurnal("openvpn sus: %s, %d comenzi rele" % (dev, rele))
		return 0
	_sterge(CALE_SUS)
	if plan.get("mod") == "navigator":
		# interfata tun dispare odata cu ea; NETNS ramane fara iesire (il scoate numai oprirea ceruta de om)
		jurnal("openvpn jos: navigatorul ramane fara internet pana revine VPN-ul")
		return 0
	if os.path.exists(_cale(CALE_OPRIRE)) or not plan.get("oprire_totala"):
		curataRetea()
		jurnal("openvpn jos: rutarea scoasa")
	else:
		jurnal("openvpn jos: oprirea totala ramane (internetul oprit pana revine VPN-ul)")
	return 0


def _susNetns(dev, mediu):
	"""--up in modul navigator: interfata tun mutata in NETNS si configurata acolo (adresa, MTU, ruta implicita), DNS-ul
	in /etc/netns/<NETNS>/resolv.conf. Namespace-ul de baza nu se atinge."""
	creeazaNetns()
	local = mediu.get("ifconfig_local", "")
	adrese, peer = [], ""
	try:
		if local and mediu.get("ifconfig_netmask"):
			adrese = ["%s/%d" % (ipaddress.IPv4Address(local), ipaddress.IPv4Network("0.0.0.0/" + mediu["ifconfig_netmask"])
				.prefixlen)]
		elif local and mediu.get("ifconfig_remote"):
			adrese, peer = [str(ipaddress.IPv4Address(local))], str(ipaddress.IPv4Address(mediu["ifconfig_remote"]))
	except ValueError:
		adrese, peer = [], ""
	mtu = mediu.get("tun_mtu", "1500")
	if not mtu.isdigit():
		mtu = "1500"
	rele = aplicaComenzi(comenziNetns(dev, adrese, mtu, True, peer=peer))
	dns = dnsDinOpenvpn(mediu)
	scrieDnsNetns(dns or list(DNS_REZERVA))
	_dosar(DOSAR_RULARE)
	_scrieAtomic(CALE_SUS, json.dumps({"fel": "openvpn", "dev": dev, "dns": dns, "ip_local": local, "netns": True,
		"cand": int(time.time()), "comenzi_rele": rele}), 0o600)
	jurnal("openvpn sus in %s: %s, %d comenzi rele" % (NETNS, dev, rele))
	return 0


# ---------------------------------------------------------------- protocoalele noi: programele care raman pornite

# ce scrie in linia de comanda a fiecarui program (pid-ul din fisier e al lui numai daca are semnul)
SEMNE_PROCES = {"openconnect": "--interface=" + INTERFATA_OC, "charon": "charon",
	"ss-local": DOSAR_RULARE + "/ss.json", "tun2socks": DOSAR_RULARE + "/tun2socks.yml",
	"xl2tpd": DOSAR_RULARE + "/xl2tpd.conf"}
# programele fiecarui fel, in ordinea opririi (charon la urma)
PROCESE_FEL = {"openconnect": ("openconnect",), "shadowsocks": ("tun2socks", "ss-local"), "ikev2": ("charon",),
	"l2tp": ("xl2tpd", "charon")}
# fisierele cu secrete din DOSAR_RULARE, sterse la oprire (si dupa folosire, unde se poate)
FISIERE_SECRETE_RULARE = ("ss.json", "swanctl/swanctl.conf", "ppp.opt")
TIMP_IPSEC_S = 40
TIMP_INTERFATA_S = 8
_COPII = {}


def _calePid(nume):
	return "%s/%s.pid" % (DOSAR_RULARE, nume)


def pidProces(nume):
	text = _citeste(_calePid(nume), 32)
	try:
		pid = int((text or "").strip())
	except ValueError:
		return None
	if pid > 1 and _pidViu(pid, SEMNE_PROCES.get(nume, nume)):
		return pid
	return None


def procesViu(nume):
	c = _COPII.get(nume)
	if c is not None:
		if c.poll() is None:
			return True
		_COPII.pop(nume, None)
	return pidProces(nume) is not None


def felViu():
	"""Felul protocolului nou ale carui programe merg acum (toate cele ale felului), sau ""."""
	for fel, nume in PROCESE_FEL.items():
		if fel == "l2tp" and not procesViu("xl2tpd"):
			continue
		if fel == "ikev2" and procesViu("xl2tpd"):
			continue
		if all(procesViu(n) for n in nume):
			return fel
	return ""


def _oricareViu():
	return any(procesViu(n) for n in SEMNE_PROCES)


def _pornesteProces(nume, argv, mediu=None, intrare=None):
	"""Porneste `argv` in sesiunea lui (nu moare cu interfata), iesirea in /tmp/hds-vpn-<nume>.log, pid-ul in
	DOSAR_RULARE. `intrare`: textul dat pe stdin (parola lui openconnect), apoi stdin se inchide."""
	_dosar(DOSAR_RULARE)
	jurnal("pornesc %s: %s" % (nume, " ".join(argv)))
	if PORNITOR is not None:
		proc = PORNITOR(list(argv), mediu, intrare)
	else:
		try:
			fd = os.open(_cale(CALE_JURNAL_PROTOCOL % nume), os.O_WRONLY | os.O_CREAT | os.O_TRUNC |
				getattr(os, "O_NOFOLLOW", 0), 0o600)
		except OSError:
			fd = subprocess.DEVNULL
		try:
			proc = subprocess.Popen(argv, stdin=subprocess.PIPE if intrare is not None else subprocess.DEVNULL,
				stdout=fd, stderr=subprocess.STDOUT, close_fds=True, start_new_session=True, cwd="/", env=mediu)
		finally:
			if fd is not subprocess.DEVNULL:
				os.close(fd)
		if intrare is not None:
			try:
				proc.stdin.write(intrare.encode("utf-8"))
				proc.stdin.close()
			except (OSError, IOError):
				pass
	_COPII[nume] = proc
	_scrieAtomic(_calePid(nume), "%d\n" % proc.pid, 0o600)
	return proc


def _opresteProces(nume):
	pid = pidProces(nume)
	c = _COPII.get(nume)
	if pid:
		try:
			os.kill(pid, signal.SIGTERM)
		except OSError:
			pass
		for _i in range(50):
			if not pidProces(nume):
				break
			time.sleep(0.1)
		if pidProces(nume):
			try:
				os.kill(pid, signal.SIGKILL)
			except OSError:
				pass
	elif c is not None and c.poll() is None:
		try:
			c.terminate()
		except OSError:
			pass
	if c is not None:
		try:
			c.wait(5)
		except Exception:
			pass
	_COPII.pop(nume, None)
	_sterge(_calePid(nume))


def _opresteProtocoale():
	for fel in ("openconnect", "shadowsocks", "l2tp", "ikev2"):
		for nume in PROCESE_FEL[fel]:
			if procesViu(nume) or os.path.exists(_cale(_calePid(nume))):
				_opresteProces(nume)
	for f in FISIERE_SECRETE_RULARE:
		_sterge("%s/%s" % (DOSAR_RULARE, f))


def _jurnalProtocol(nume, maxim=16384):
	return (_citeste(CALE_JURNAL_PROTOCOL % nume, 262144) or "")[-maxim:]


def _asteaptaInterfata(dev, secunde=TIMP_INTERFATA_S):
	if RULATOR is not None:
		return True
	for _i in range(int(secunde * 10)):
		if interfataExista(dev):
			return True
		time.sleep(0.1)
	return False


def _numeDev(x, implicit):
	return x if re.match(r"^[A-Za-z0-9_.\-]{1,15}\Z", x or "") else implicit


def _ipv4(x):
	try:
		return str(ipaddress.IPv4Address((x or "").strip()))
	except ValueError:
		return ""


def susTun(fel, dev, adrese, mtu, dns, servere, peer="", configureaza=True):
	"""Interfata VPN `dev` (tun sau ppp) gata: in modul navigator mutata in NETNS si configurata acolo, altfel adresa
	(cu `configureaza`), rutarea dupa plan si DNS-ul in modul tot. Scrie sus.json. Pentru scripturile programelor
	(openconnect-script, ppp-sus) si dupa pornirea lui charon si hev-socks5-tunnel."""
	plan = _citestePlan()
	mtu = str(mtu) if str(mtu).isdigit() else "1400"
	dns = [d for d in dns if _ipv4(d)][:3]
	if plan.get("mod") == "navigator":
		creeazaNetns()
		rele = aplicaComenzi(comenziNetns(dev, adrese, mtu, True, peer=peer))
		scrieDnsNetns(dns or list(DNS_REZERVA))
		_dosar(DOSAR_RULARE)
		_scrieAtomic(CALE_SUS, json.dumps({"fel": fel, "dev": dev, "dns": dns, "ip_local": (adrese or [""])[0],
			"netns": True, "cand": int(time.time()), "comenzi_rele": rele}), 0o600)
		jurnal("%s sus in %s: %s, %d comenzi rele" % (fel, NETNS, dev, rele))
		return rele
	_stergeReguli((PRIO_SERVER, PRIO_CASA, PRIO_TOT, PRIO_ALES))
	_ip("-4", "route", "flush", "table", TABELA)
	rele = 0
	if configureaza:
		for a in adrese:
			rele += aplicaComenzi([["-4", "address", "replace", a] + (["peer", peer] if peer else []) + ["dev", dev]])
		rele += aplicaComenzi([["link", "set", "dev", dev, "mtu", mtu, "up"]])
	mod = plan.get("mod", "tot")
	servere = sorted(set([s for s in servere if _ipv4(s)] + list(plan.get("servere") or [])))
	rele += aplicaComenzi(comenziPornire(dev, servere, mod, bool(plan.get("oprire_totala")), plan.get("ales") or []))
	if mod == "tot":
		aplicaDns(dns or list(DNS_REZERVA))
	_dosar(DOSAR_RULARE)
	_scrieAtomic(CALE_SUS, json.dumps({"fel": fel, "dev": dev, "dns": dns, "ip_local": (adrese or [""])[0],
		"cand": int(time.time()), "comenzi_rele": rele}), 0o600)
	jurnal("%s sus: %s, %d comenzi rele" % (fel, dev, rele))
	return rele


def josTun(fel):
	"""Interfata VPN a cazut (scriptul programului): ca --down la openvpn."""
	plan = _citestePlan()
	_sterge(CALE_SUS)
	if plan.get("mod") == "navigator":
		jurnal("%s jos: navigatorul ramane fara internet pana revine VPN-ul" % fel)
		return 0
	if os.path.exists(_cale(CALE_OPRIRE)) or not plan.get("oprire_totala"):
		curataRetea()
		jurnal("%s jos: rutarea scoasa" % fel)
	else:
		jurnal("%s jos: oprirea totala ramane (internetul oprit pana revine VPN-ul)" % fel)
	return 0


# ---------------------------------------------------------------- OpenConnect

def argumenteOpenconnect(d, nume):
	"""Linia de comanda a lui openconnect (fara parola: ea merge pe stdin). Toate optiunile in forma --x=valoare, iar
	adresa e verificata (https://...), deci nimic de la om nu poate deveni o optiune."""
	a = [_program("openconnect") or CAI_PROGRAME["openconnect"][0], "--non-inter", "--passwd-on-stdin",
		"--interface=" + INTERFATA_OC, "--script=%s %s openconnect-script" % (PYTHON, _caleScript()),
		"--protocol=" + d.get("protocol", "anyconnect"), "--user=" + nume, "--timestamp"]
	if d.get("grup"):
		a.append("--authgroup=" + d["grup"])
	if d.get("pin"):
		a.append("--servercert=" + d["pin"])
	a.append(d["url"])
	return a


_PIN_IN_JURNAL = re.compile(r"--servercert[= ](pin-sha256:[A-Za-z0-9+/]{43}=)")
_ERORI_OC = (
	("Login failed", N_("Numele sau parola nu sunt bune. VPN-ul nu mai încearcă singur."), True),
	("Authentication failed", N_("Numele sau parola nu sunt bune. VPN-ul nu mai încearcă singur."), True),
	("Failed to complete authentication", N_("Numele sau parola nu sunt bune. VPN-ul nu mai încearcă singur."), True),
	("User input required in non-interactive mode", N_("Serverul cere încă un cod (de pe telefon sau prin SMS); "
		"receptorul nu îl poate da."), True),
	("certificate from VPN server", N_("Certificatul serverului nu este de încredere."), False),
	("Failed to open HTTPS connection", N_("Serverul nu răspunde. Verifică adresa lui."), False),
	("Failed to connect to host", N_("Serverul nu răspunde. Verifică adresa lui."), False),
)


def eroareOpenconnect():
	"""(motivul, este eroare de cont, pin-ul propus pentru un certificat necunoscut)"""
	coada = _jurnalProtocol("openconnect")
	m = _PIN_IN_JURNAL.search(coada)
	if m:
		# certificatul nu a fost primit (openconnect propune --servercert); spune si "User input required", fiindca ar
		# fi cerut un da. Cu pin-ul bun in profil, "verify failed" apare tot, dar fara propunere, si legatura merge mai departe
		return _(N_("Certificatul serverului nu este de încredere.")), False, m.group(1)
	for semn, motiv, de_cont in _ERORI_OC:
		if semn in coada:
			return _(motiv), de_cont, (m.group(1) if m else "")
	return "", False, (m.group(1) if m else "")


def _pornesteOpenconnect(p, servere, plan):
	d = dateProfil(p)
	sec = secreteProfil(p)
	if not d.get("url") or not sec.get("nume") or not sec.get("parola"):
		return False, _("Scrie întâi numele și parola contului.")
	if not incarcaTun():
		return False, _("Interfața tun nu se poate deschide (lipsește tun.ko). Instalează programele VPN.")
	_STARE["pin_propus"] = ""
	proc = _pornesteProces("openconnect", argumenteOpenconnect(d, sec["nume"]), intrare=sec["parola"] + "\n")
	limita = time.time() + TIMP_CONECTARE_S
	while time.time() < limita:
		if proc.poll() is not None:
			motiv, de_cont, pin = eroareOpenconnect()
			if pin and not d.get("pin"):
				_STARE["pin_propus"] = pin
			_STARE.update(eroare=motiv or _("OpenConnect s-a oprit. Verifică adresa serverului."), eroare_cont=de_cont)
			if not (setari()["oprire_totala"] and setari()["pornit"]) and plan.get("mod") != "navigator":
				curataRetea()
			return False, _STARE["eroare"]
		sus = _citesteJson(CALE_SUS) or {}
		if sus.get("fel") == "openconnect":
			_STARE.update(legatura="CONNECTED", adresa_tunel=sus.get("ip_local", ""))
			return True, _("Conectat la %s.") % p["titlu"]
		if PORNITOR is not None:
			break
		time.sleep(0.5)
	return True, _("Se conectează încă la %s.") % p["titlu"]


def scriptOpenconnect(mediu):
	"""Scriptul lui openconnect (in locul lui vpnc-script): reason=connect pune interfata, rutarea si DNS-ul;
	disconnect le scoate; restul (pre-init, reconnect, attempt-reconnect) nu schimba nimic (interfata ramane)."""
	motiv = mediu.get("reason", "")
	dev = _numeDev(mediu.get("TUNDEV", ""), INTERFATA_OC)
	if motiv == "connect":
		local = _ipv4(mediu.get("INTERNAL_IP4_ADDRESS", ""))
		if not local:
			jurnal("openconnect connect fara adresa IPv4")
			return 0
		mtu = mediu.get("INTERNAL_IP4_MTU", "1300")
		dns = [x for x in (mediu.get("INTERNAL_IP4_DNS", "") or "").split() if _ipv4(x)]
		susTun("openconnect", dev, ["%s/32" % local], mtu, dns, [_ipv4(mediu.get("VPNGATEWAY", ""))])
		return 0
	if motiv == "disconnect":
		return josTun("openconnect")
	return 0


def pastreazaCertificatul():
	"""Omul are incredere in certificatul serverului OpenConnect aratat la ultima incercare: pin-ul intra in profil.
	(reusit, mesaj)."""
	pin = _STARE.get("pin_propus") or ""
	s = setari()
	p = profil(s["profil"])
	if not pin or p is None or p["fel"] != "openconnect" or not _PIN_OC.match(pin):
		return False, _("Nimic de schimbat.")
	d = dateProfil(p)
	d["pin"] = pin
	_scrieAtomic(_caleProfil(p), json.dumps(d, ensure_ascii=False), 0o600)
	_STARE["pin_propus"] = ""
	jurnal("certificatul serverului %s pastrat: %s" % (p["id"], pin))
	return True, _("Certificatul serverului este păstrat. Pornește din nou VPN-ul.")


# ---------------------------------------------------------------- Shadowsocks

def textTun2socks():
	return ("tunnel:\n  name: %s\n  mtu: 8500\n  ipv4: %s\n"
		"socks5:\n  port: %s\n  address: 127.0.0.1\n  udp: 'udp'\n"
		"misc:\n  log-level: warn\n") % (INTERFATA_SS, ADRESA_TUN_SS, PORT_SOCKS)


def configurareSs(d, parola, ip_server):
	return {"server": ip_server, "server_port": int(d["port"]), "local_address": "127.0.0.1",
		"local_port": int(PORT_SOCKS), "password": parola, "method": d["metoda"], "timeout": 300, "mode": "tcp_and_udp"}


def _pornesteSs(p, servere, plan):
	d = dateProfil(p)
	sec = secreteProfil(p)
	if not sec.get("parola"):
		return False, _("Scrie întâi parola.")
	if d.get("metoda") not in METODE_SS:
		return False, _("Metoda %s nu este cunoscută.") % str(d.get("metoda"))[:40]
	if not incarcaTun():
		return False, _("Interfața tun nu se poate deschide (lipsește tun.ko). Instalează programele VPN.")
	_dosar(DOSAR_RULARE)
	_scrieAtomic(DOSAR_RULARE + "/ss.json", json.dumps(configurareSs(d, sec["parola"], servere[0][0])), 0o600)
	_scrieAtomic(DOSAR_RULARE + "/tun2socks.yml", textTun2socks(), 0o600)
	ss = _pornesteProces("ss-local", [_program("ss-local") or CAI_PROGRAME["ss-local"][0], "-c",
		_cale(DOSAR_RULARE + "/ss.json")])
	t2s = _pornesteProces("tun2socks", [_program("tun2socks") or CAI_PROGRAME["tun2socks"][0],
		_cale(DOSAR_RULARE + "/tun2socks.yml")])
	if not _asteaptaInterfata(INTERFATA_SS) or ss.poll() is not None or t2s.poll() is not None:
		motiv = (_jurnalProtocol("ss-local", 300) + " " + _jurnalProtocol("tun2socks", 300)).strip()
		jurnal("shadowsocks nu a pornit: %s" % motiv)
		_STARE.update(eroare=_("Shadowsocks nu a pornit. Vezi metoda și parola."), eroare_cont=False)
		return False, _STARE["eroare"]
	# ss-local a citit configurarea la pornire: parola nu mai sta pe disc
	_sterge(DOSAR_RULARE + "/ss.json")
	susTun("shadowsocks", INTERFATA_SS, ["%s/32" % ADRESA_TUN_SS], "8500", [], [ip for ip, _p, _x in servere])
	_STARE.update(legatura="CONNECTED", adresa_tunel=ADRESA_TUN_SS)
	return True, _("Pornit spre %s.") % p["titlu"]


# ---------------------------------------------------------------- IKEv2 si L2TP/IPsec (strongSwan)

DOSAR_SWANCTL = DOSAR_RULARE + "/swanctl"
CALE_STRONGSWAN = DOSAR_RULARE + "/strongswan.conf"
CALE_VICI = DOSAR_RULARE + "/charon.vici"
CALE_DNS_IPSEC = DOSAR_RULARE + "/ipsec-dns"
CALE_RESOLVCONF_IPSEC = DOSAR_RULARE + "/ipsec-resolvconf"
CALE_JURNAL_CHARON = "/tmp/hds-vpn-charon-ike.log"
# pluginurile, in ordine: kernel-libipsec inaintea lui kernel-netlink (IPsec-ul il face libipsec, prin tun); cele care
# lipsesc din pachet se sar cu un avertisment
PLUGINURI_IKEV2 = ("random drbg nonce x509 revocation constraints pubkey pkcs1 pkcs7 pkcs8 pkcs12 pem openssl gmp aes "
	"des sha1 sha2 md4 md5 hmac kdf curve25519 kernel-libipsec kernel-netlink resolve socket-default vici "
	"eap-identity eap-mschapv2 eap-md5 xauth-generic")
# L2TP: modul transport, deci IPsec-ul nucleului (fara kernel-libipsec)
PLUGINURI_L2TP = PLUGINURI_IKEV2.replace("kernel-libipsec ", "")


def _hex(text):
	return "0x" + binascii.hexlify(text.encode("utf-8")).decode("ascii")


def textStrongswan(pluginuri):
	return ("charon {\n"
		"  load = %s\n"
		"  port = 0\n  port_nat_t = 0\n"
		"  install_routes = no\n  install_virtual_ip = yes\n"
		"  retransmit_tries = 3\n  close_ike_on_child_failure = yes\n"
		"  plugins {\n"
		"    vici {\n      socket = unix://%s\n    }\n"
		"    resolve {\n      file = %s\n      resolvconf {\n        path = %s\n      }\n    }\n"
		"  }\n"
		"  filelog {\n    hds {\n      path = %s\n      default = 1\n      time_format = %%H:%%M:%%S\n"
		"      append = no\n      flush_line = yes\n    }\n  }\n"
		"  syslog {\n    daemon {\n      default = -1\n    }\n  }\n"
		"}\n") % (pluginuri, _cale(CALE_VICI), _cale(CALE_DNS_IPSEC), _cale(CALE_RESOLVCONF_IPSEC),
		_cale(CALE_JURNAL_CHARON))


def textResolvconfIpsec():
	""""resolvconf" pentru pluginul resolve al lui charon: strongSwan 5.9+ il cheama cand e scris in configurare (si cand
	/sbin/resolvconf exista), altfel scrie in fisier; amandoua duc numai in CALE_DNS_IPSEC, niciodata in
	/etc/resolv.conf. DNS-ul il pune apoi receptorul (susTun), dupa modul ales."""
	return ("#!/bin/sh\n# HdsVpn: DNS-ul dat de serverul IKEv2 ajunge numai aici\n"
		"case \"$1\" in -a) cat >> %s ;; esac\nexit 0\n") % _cale(CALE_DNS_IPSEC)


def certificateCa(d):
	"""Autoritatile cu care se verifica serverul: cele din import, altfel cele ale sistemului (ca-certificates)."""
	if d.get("ca"):
		return [c for c in d["ca"] if isinstance(c, str)][:8]
	for c in CALE_CA_SISTEM:
		text = _citeste(c, 4 * 1024 * 1024)
		if text:
			return _certificateToate(text)
	return []


def _certificateToate(text):
	rez = []
	for m in _PEM_CERT.finditer(text or ""):
		rez.append(m.group(0))
		if len(rez) >= 400:
			break
	return rez


def textSwanctlIkev2(d, sec, ip_servere, nume_ca):
	"""swanctl.conf pentru IKEv2: numai valori verificate (adrese IP, identitati pe lista alba, propuneri pe lista alba,
	numele fisierelor facute de noi) si secretele ca 0x<hex>: nimic de la om nu se poate citi ca sintaxa."""
	auth = d.get("auth", "eap")
	r = ["connections {", "  hds {", "    version = 2", "    remote_addrs = %s" % ",".join(ip_servere),
		"    remote_port = %s" % (d.get("port") or "500"), "    vips = 0.0.0.0", "    encap = yes",
		"    dpd_delay = 30s", "    keyingtries = 1"]
	if d.get("ike"):
		r.append("    proposals = %s,default" % d["ike"])
	r.append("    local {")
	if auth.startswith("psk"):
		r += ["      auth = psk"] + (["      id = %s" % d["id_local"]] if d.get("id_local") else [])
		if auth.endswith("eap"):
			r += ["    }", "    local-eap {", "      auth = eap", "      eap_id = %s" % sec["nume"]]
	else:
		r += ["      auth = eap", "      id = %s" % sec["nume"], "      eap_id = %s" % sec["nume"]]
	r.append("    }")
	r += ["    remote {", "      id = %s" % d["id_server"]]
	if auth.startswith("psk"):
		r.append("      auth = psk")
	else:
		r += ["      auth = pubkey", "      cacerts = %s" % ",".join(nume_ca)]
	r += ["    }", "    children {", "      hds {", "        remote_ts = 0.0.0.0/0", "        dpd_action = restart",
		"        close_action = none"]
	if d.get("esp"):
		r.append("        esp_proposals = %s,default" % d["esp"])
	r += ["      }", "    }", "  }", "}", "secrets {"]
	if auth.endswith("eap"):
		r += ["  eap-hds {", "    id = %s" % sec["nume"], "    secret = %s" % _hex(sec["parola"]), "  }"]
	if auth.startswith("psk"):
		r += ["  ike-hds {", "    id-1 = %s" % d["id_server"], "    secret = %s" % _hex(sec["psk"]), "  }"]
	r.append("}")
	return "\n".join(r) + "\n"


def textSwanctlL2tp(sec, ip_server):
	return "\n".join(["connections {", "  hds {", "    version = 1", "    remote_addrs = %s" % ip_server,
		"    proposals = aes256-sha1-modp2048,aes128-sha1-modp2048,aes256-sha1-modp1024,aes128-sha1-modp1024,"
		"3des-sha1-modp1024,default", "    keyingtries = 1", "    local {", "      auth = psk", "    }",
		"    remote {", "      auth = psk", "    }", "    children {", "      l2tp {", "        mode = transport",
		"        local_ts = dynamic[udp/1701]", "        remote_ts = dynamic[udp/1701]",
		# ESP in nucleu: numai ce au nucleele imaginii (fara SHA-384/512 si ChaCha20; tabelul lui V1)
		"        esp_proposals = aes256-sha256,aes128-sha256,aes256-sha1,aes128-sha1,3des-sha1", "      }", "    }", "  }",
		"}",
		"secrets {", "  ike-hds {", "    secret = %s" % _hex(sec["psk"]), "  }", "}"]) + "\n"


def _swanctl(*argv, **k):
	mediu = dict(os.environ, STRONGSWAN_CONF=_cale(CALE_STRONGSWAN), SWANCTL_DIR=_cale(DOSAR_SWANCTL))
	cmd = [_program("swanctl") or CAI_PROGRAME["swanctl"][0]] + list(argv) + ["--uri", "unix://" + _cale(CALE_VICI)]
	if RULATOR is not None:
		return RULATOR(cmd, k.get("timeout", TIMP_PROGRAM_S))
	try:
		p = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
			timeout=k.get("timeout", TIMP_PROGRAM_S), env=mediu)
		return p.returncode, p.stdout.decode("utf-8", "replace")
	except subprocess.TimeoutExpired:
		return -2, "timeout"
	except OSError as eroare:
		return -1, str(eroare)


_ERORI_IPSEC = (
	("EAP_FAILURE", N_("Numele sau parola nu sunt bune. VPN-ul nu mai încearcă singur."), True),
	("ERROR_AUTHENTICATION_FAILURE", N_("Numele sau parola nu sunt bune. VPN-ul nu mai încearcă singur."), True),
	("EAP_MSCHAPV2 method failed", N_("Numele sau parola nu sunt bune. VPN-ul nu mai încearcă singur."), True),
	("AUTHENTICATION_FAILED", N_("Numele, parola sau cheia comună nu sunt bune. VPN-ul nu mai încearcă singur."), True),
	("no trusted", N_("Certificatul serverului nu se potrivește cu autoritatea lui (CA). Adaugă certificatul CA al "
		"furnizorului."), False),
	("constraint check failed", N_("Certificatul serverului nu se potrivește cu numele lui."), False),
	("no issuer certificate found", N_("Certificatul serverului nu se potrivește cu autoritatea lui (CA). Adaugă "
		"certificatul CA al furnizorului."), False),
	("NO_PROPOSAL_CHOSEN", N_("Serverul nu primește cifrurile receptorului."), False),
	("giving up after", N_("Serverul nu răspunde. Încearcă alt server."), False),
	("unable to resolve", N_("Nu găsesc adresa serverului. Verifică legătura la internet."), False),
)


def eroareIpsec():
	coada = _citeste(CALE_JURNAL_CHARON, 262144) or ""
	coada = coada[-16384:]
	for semn, motiv, de_cont in _ERORI_IPSEC:
		if semn in coada:
			return _(motiv), de_cont
	return "", False


def _pornesteCharon(pluginuri):
	"""charon pornit cu configurarea noastra; True cand soclul vici raspunde."""
	_dosar(DOSAR_RULARE)
	_dosar(DOSAR_SWANCTL)
	for sub in ("x509ca", "x509", "private", "conf.d"):
		_dosar(DOSAR_SWANCTL + "/" + sub)
	_scrieAtomic(CALE_STRONGSWAN, textStrongswan(pluginuri), 0o600)
	_scrieAtomic(CALE_RESOLVCONF_IPSEC, textResolvconfIpsec(), 0o700)
	_sterge(CALE_DNS_IPSEC)
	# charon scrie in jurnalul lui si numele contului (identitatea IKE): fisierul e facut 0600 inainte, charon il
	# deschide fara sa-i schimbe drepturile, si se goleste la fiecare pornire (append = no)
	_scrieAtomic(CALE_JURNAL_CHARON, "", 0o600)
	_sterge(CALE_VICI)
	mediu = dict(os.environ, STRONGSWAN_CONF=_cale(CALE_STRONGSWAN))
	proc = _pornesteProces("charon", [_program("charon") or CAI_PROGRAME["charon"][0]], mediu=mediu)
	for _i in range(100):
		if proc.poll() is not None:
			return False
		if os.path.exists(_cale(CALE_VICI)) or PORNITOR is not None:
			return True
		time.sleep(0.1)
	return False


def _incarcaSiInitiaza(text_conf, copil):
	"""Scrie swanctl.conf (0600), il incarca, il sterge (secretele raman numai in charon) si porneste legatura.
	(reusit, textul lui swanctl)."""
	cale = DOSAR_SWANCTL + "/swanctl.conf"
	_scrieAtomic(cale, text_conf, 0o600)
	try:
		cod, text = _swanctl("--load-all", "--file", _cale(cale))
	finally:
		_sterge(cale)
	if cod != 0:
		jurnal("swanctl --load-all: %s" % ascunde(text.strip())[-300:])
		return False, text
	cod, text = _swanctl("--initiate", "--child", copil, "--timeout", str(TIMP_IPSEC_S), timeout=TIMP_IPSEC_S + 10)
	return cod == 0, text


_VIP = re.compile(r"(?m)^\s*local\s+.*\[(\d{1,3}(?:\.\d{1,3}){3})\]\s*$")


def adresaVirtuala(text):
	"""Adresa data de server (virtual IP) din `swanctl --list-sas`: ultimul [x.x.x.x] de pe randul local."""
	m = _VIP.search(text or "")
	return _ipv4(m.group(1)) if m else ""


def _dnsIpsec():
	return [x for x in re.findall(r"(?m)^nameserver\s+(\S+)", _citeste(CALE_DNS_IPSEC, 4096) or "") if _ipv4(x)]


def _pornesteIkev2(p, servere, plan):
	d = dateProfil(p)
	sec = secreteProfil(p)
	lipsa = campuriLipsa(p)
	if lipsa:
		return False, _("Mai scrie: %s.") % ", ".join(textCamp(c) for c in lipsa)
	if not incarcaTun():
		return False, _("Interfața tun nu se poate deschide (lipsește tun.ko). Instalează programele VPN.")
	ca = [] if d.get("auth", "eap").startswith("psk") else certificateCa(d)
	if not d.get("auth", "eap").startswith("psk") and not ca:
		return False, _("Lipsește certificatul serverului (ca).")
	if not _pornesteCharon(PLUGINURI_IKEV2):
		motiv, _c = eroareIpsec()
		return False, motiv or _("strongSwan nu a pornit.")
	nume_ca = []
	for i, c in enumerate(ca):
		n = "ca%03d.pem" % i
		_scrieAtomic("%s/x509ca/%s" % (DOSAR_SWANCTL, n), c + "\n", 0o600)
		nume_ca.append(n)
	ips = sorted(set(ip for ip, _p, _x in servere))
	reusit, text = _incarcaSiInitiaza(textSwanctlIkev2(d, sec, ips, nume_ca), "hds")
	if not reusit:
		motiv, de_cont = eroareIpsec()
		_STARE.update(eroare=motiv or _("Serverul IKEv2 nu a primit legătura."), eroare_cont=de_cont)
		_opresteProces("charon")
		if not (setari()["oprire_totala"] and setari()["pornit"]) and plan.get("mod") != "navigator":
			curataRetea()
		return False, _STARE["eroare"]
	cod, lista = _swanctl("--list-sas")
	vip = adresaVirtuala(lista)
	if not vip:
		_STARE.update(eroare=_("Serverul nu a dat o adresă receptorului (virtual IP)."), eroare_cont=False)
		_opresteProces("charon")
		return False, _STARE["eroare"]
	if not _asteaptaInterfata(INTERFATA_IPSEC):
		_opresteProces("charon")
		return False, _("Interfața tun nu se poate deschide (lipsește tun.ko). Instalează programele VPN.")
	susTun("ikev2", INTERFATA_IPSEC, ["%s/32" % vip], "1400", _dnsIpsec(), ips)
	_STARE.update(legatura="CONNECTED", adresa_tunel=vip, sa_ok=True)
	return True, _("Conectat la %s.") % p["titlu"]


def legaturaIpsec():
	"""True cand charon are legatura stabilita (`swanctl --list-sas`: ESTABLISHED si INSTALLED)."""
	cod, text = _swanctl("--list-sas", timeout=10)
	return cod == 0 and "ESTABLISHED" in text and "INSTALLED" in text


# L2TP/IPsec: xl2tpd + pppd (prin pty) peste IPsec in modul transport

def _ghilimelePpp(x):
	return '"%s"' % x.replace("\\", "\\\\").replace('"', '\\"')


def textPppOpt(sec):
	"""Optiunile lui pppd (0600, in DOSAR_RULARE, sterse dupa legatura): numele cu lista alba, parola intre ghilimele cu
	\\ si " scapate (pppd le citeste asa); interfata, scripturile si DNS-ul le alege receptorul."""
	return "\n".join(["ipcp-accept-local", "ipcp-accept-remote", "refuse-eap", "noccp", "noauth", "mtu 1400",
		"mru 1400", "nodefaultroute", "noipdefault", "usepeerdns", "persist", "maxfail 3", "lcp-echo-interval 30",
		"lcp-echo-failure 4", "logfd 2", "ifname %s" % INTERFATA_PPP, "ip-up-script %s" % _cale(DOSAR_RULARE + "/ppp-sus"),
		"ip-down-script %s" % _cale(DOSAR_RULARE + "/ppp-jos"), "name %s" % _ghilimelePpp(sec["nume"]),
		"password %s" % _ghilimelePpp(sec["parola"])]) + "\n"


def textXl2tpd(ip_server):
	return "\n".join(["[global]", "port = 1701", "", "[lac hds]", "lns = %s" % ip_server, "ppp debug = no",
		"pppoptfile = %s" % _cale(DOSAR_RULARE + "/ppp.opt"), "length bit = yes", "redial = no",
		"autodial = no"]) + "\n"


def _scriptPpp(fel):
	return "#!/bin/sh\nexec %s %s ppp-%s \"$@\"\n" % (PYTHON, _caleScript(), fel)


def _pornesteL2tp(p, servere, plan):
	if plan.get("mod") == "navigator":
		return False, _("L2TP nu poate trece numai navigatorul prin VPN. Alege alt rând la Ce trece prin VPN.")
	sec = secreteProfil(p)
	lipsa = campuriLipsa(p)
	if lipsa:
		return False, _("Mai scrie: %s.") % ", ".join(textCamp(c) for c in lipsa)
	ok, motiv = nucleuPoate("l2tp")
	if not ok:
		return False, motiv
	for m in ("ppp_generic", "ppp_async", "esp4", "xfrm4_mode_transport", "xfrm_user"):
		_ruleaza([PROGRAM_MODPROBE, m], 20)
	ip = servere[0][0]
	if not _pornesteCharon(PLUGINURI_L2TP):
		motiv, _c = eroareIpsec()
		return False, motiv or _("strongSwan nu a pornit.")
	reusit, text = _incarcaSiInitiaza(textSwanctlL2tp(sec, ip), "l2tp")
	if not reusit:
		motiv, de_cont = eroareIpsec()
		_STARE.update(eroare=motiv or _("Serverul L2TP nu a primit legătura IPsec."), eroare_cont=de_cont)
		_opresteProces("charon")
		return False, _STARE["eroare"]
	for fel in ("sus", "jos"):
		_scrieAtomic(DOSAR_RULARE + "/ppp-" + fel, _scriptPpp(fel), 0o700)
	_scrieAtomic(DOSAR_RULARE + "/ppp.opt", textPppOpt(sec), 0o600)
	_scrieAtomic(DOSAR_RULARE + "/xl2tpd.conf", textXl2tpd(ip), 0o600)
	control = DOSAR_RULARE + "/xl2tpd.control"
	_sterge(control)
	_pornesteProces("xl2tpd", [_program("xl2tpd") or CAI_PROGRAME["xl2tpd"][0], "-D", "-c",
		_cale(DOSAR_RULARE + "/xl2tpd.conf"), "-p", _cale(DOSAR_RULARE + "/xl2tpd.pid.intern"), "-C", _cale(control)])
	for _i in range(50):
		if os.path.exists(_cale(control)) or PORNITOR is not None:
			break
		time.sleep(0.1)
	try:
		fd = os.open(_cale(control), os.O_WRONLY | getattr(os, "O_NONBLOCK", 0))
		try:
			os.write(fd, b"c hds\n")
		finally:
			os.close(fd)
	except OSError as eroare:
		jurnal("xl2tpd control: %s" % eroare)
	limita = time.time() + TIMP_CONECTARE_S
	while time.time() < limita:
		sus = _citesteJson(CALE_SUS) or {}
		if sus.get("fel") == "l2tp":
			_sterge(DOSAR_RULARE + "/ppp.opt")
			_STARE.update(legatura="CONNECTED", adresa_tunel=sus.get("ip_local", ""))
			return True, _("Conectat la %s.") % p["titlu"]
		motiv, de_cont = eroareL2tp()
		if de_cont:
			_STARE.update(eroare=motiv, eroare_cont=True)
			_sterge(DOSAR_RULARE + "/ppp.opt")
			return False, motiv
		if not procesViu("xl2tpd") or PORNITOR is not None:
			break
		time.sleep(0.5)
	if PORNITOR is not None:
		return True, _("Se conectează încă la %s.") % p["titlu"]
	_sterge(DOSAR_RULARE + "/ppp.opt")
	return True, _("Se conectează încă la %s.") % p["titlu"]


def eroareL2tp():
	"""(motivul, este eroare de cont) din iesirea lui xl2tpd si pppd (logfd 2), apoi din jurnalul lui charon."""
	coada = _jurnalProtocol("xl2tpd")
	if "authentication failed" in coada.lower():
		return _("Numele sau parola nu sunt bune. VPN-ul nu mai încearcă singur."), True
	return eroareIpsec()


def scriptPpp(fel, argv, mediu):
	"""ip-up-script / ip-down-script ale lui pppd: argv = interfata, tty, viteza, adresa locala, adresa de dincolo."""
	dev = _numeDev(argv[0] if argv else "", INTERFATA_PPP)
	if fel == "sus":
		local = _ipv4(argv[3] if len(argv) > 3 else "")
		dns = [x for x in (mediu.get("DNS1", ""), mediu.get("DNS2", "")) if _ipv4(x)]
		susTun("l2tp", dev, ["%s/32" % local] if local else [], "1400", dns, [], configureaza=False)
		return 0
	return josTun("l2tp")


def eroareProtocol(fel):
	"""(motivul ultimei erori a felului, este eroare de cont)"""
	if fel == "openvpn":
		return eroareOpenvpn()
	if fel == "openconnect":
		motiv, de_cont, _pin = eroareOpenconnect()
		return motiv, de_cont
	if fel == "l2tp":
		return eroareL2tp()
	if fel == "ikev2":
		return eroareIpsec()
	return "", False


# ---------------------------------------------------------------- IP-ul vazut pe internet

_ULTIMA_EROARE_IP = [None]


def aflaIp():
	"""{"ip", "tara", "oras", "cand"} din SERVICII_IP (primul care raspunde), None daca nu raspunde niciunul (ultima
	eroare ramane in _ULTIMA_EROARE_IP, pentru textul ceasului)."""
	_ULTIMA_EROARE_IP[0] = None
	try:
		from urllib.request import Request, urlopen
	except ImportError:
		return None
	for u in SERVICII_IP:
		try:
			r = urlopen(Request(u, headers={"User-Agent": UA, "Accept": "application/json"}), timeout=TIMP_IP_S)
			date = json.loads(r.read(16384).decode("utf-8", "replace"))
		except Exception as eroare:
			_ULTIMA_EROARE_IP[0] = eroare
			jurnal("IP-ul de la %s: %s" % (u, eroare))
			continue
		rez = _ipDinRaspuns(date)
		if rez:
			return rez
	return None


def _ipDinRaspuns(date):
	if not isinstance(date, dict):
		return None
	ip = str(date.get("ip") or "")[:45]
	try:
		ipaddress.ip_address(ip)
	except ValueError:
		return None
	tara = str(date.get("country") or "")[:2].upper()
	oras = re.sub(r"[^\w .\-]", "", str(date.get("city") or ""), flags=re.U)[:40]
	return {"ip": ip, "tara": tara if re.match(r"^[A-Z]{2}\Z", tara) else "", "oras": oras, "cand": int(time.time())}


def _aflaIpNetns():
	"""Ca aflaIp, dar din NETNS (modul navigator): curl pornit cu ip netns exec, deci prin tunel si cu DNS-ul VPN-ului."""
	_ULTIMA_EROARE_IP[0] = None
	for u in SERVICII_IP:
		cod, text = _ruleaza([PROGRAM_IP, "netns", "exec", NETNS, PROGRAM_CURL, "-sS", "-m", str(TIMP_IP_S), "-A", UA,
			"-H", "Accept: application/json", u], TIMP_IP_S + 5)
		if cod != 0:
			_ULTIMA_EROARE_IP[0] = text.strip()[-300:]
			jurnal("IP-ul din %s de la %s: %s" % (NETNS, u, text.strip()[-200:]))
			continue
		try:
			rez = _ipDinRaspuns(json.loads(text[:16384]))
		except ValueError:
			rez = None
		if rez:
			return rez
	return None


def aflaIpVpn():
	"""Adresa vazuta pe internet prin VPN: din NETNS in modul navigator, altfel din namespace-ul de baza."""
	sus = _citesteJson(CALE_SUS) or {}
	if sus.get("netns") or _citestePlan().get("mod") == "navigator":
		return _aflaIpNetns()
	return aflaIp()


def _mesajCeas(eroare):
	"""Textul "ceasul e in urma" (Components/HdsCeasHttps.py) cand certificatul cade din cauza ceasului, altfel None."""
	if eroare is None:
		return None
	try:
		from Components import HdsCeasHttps
		return HdsCeasHttps.mesaj(eroare)
	except Exception:
		return None


def verificaIp():
	rez = aflaIpVpn() if setari()["pornit"] else aflaIp()
	_STARE["ip"] = rez
	if rez is None:
		return False, _mesajCeas(_ULTIMA_EROARE_IP[0]) or _("Nu am putut afla adresa IP. Verifică legătura la internet.")
	return True, textIp(rez)


# ---------------------------------------------------------------- paza

_PAZA = {"fir": None, "opreste": False}


def _pornestePaza():
	f = _PAZA.get("fir")
	if f is not None and f.is_alive():
		return
	_PAZA["opreste"] = False
	f = threading.Thread(target=_bucla, name="HdsVpn-paza")
	f.daemon = True
	_PAZA["fir"] = f
	f.start()


def _citesteLegatura():
	"""Starea legaturii acum: (felul, conectat, viu)."""
	sus = _citesteJson(CALE_SUS) or {}
	pid = pidOpenvpn()
	if pid:
		st, adresa = stareOpenvpn()
		_STARE.update(legatura=st, adresa_tunel=adresa)
		return "openvpn", st == "CONNECTED", True
	in_ns = not interfataExista(INTERFATA_WG) and wgInNetns() and _ip("-n", NETNS, "link", "show", "dev",
		INTERFATA_WG)[0] == 0
	if interfataExista(INTERFATA_WG) or in_ns:
		# WireGuard nu are o legatura: serverul a raspuns daca a fost o strangere de mana (se reface numai cand trece
		# ceva prin tunel, deci una veche nu inseamna cadere)
		v = strangereMana(netns=in_ns)
		conectat = v is not None
		_STARE.update(legatura="CONNECTED" if conectat else "WAIT", adresa_tunel="")
		return "wireguard", conectat, True
	fel = felViu()
	if fel:
		# programele merg; legatura e gata cand scriptul lor a scris sus.json (la IPsec si cat charon o are stabilita)
		conectat = sus.get("fel") == fel and (fel not in ("ikev2", "l2tp") or _STARE.get("sa_ok", True))
		_STARE.update(legatura="CONNECTED" if conectat else "WAIT", adresa_tunel=sus.get("ip_local", "") if conectat
			else "")
		return fel, conectat, True
	_STARE.update(legatura="", adresa_tunel="")
	return sus.get("fel", ""), False, False


def pasPaza(acum=None, greu=True):
	"""O trecere a pazei (si in probe): starea legaturii; cu `greu`, DNS-ul, adresele modului ales si repornirea."""
	acum = acum or time.time()
	_culegeCopilul()
	s = setari()
	fel, conectat, viu = _citesteLegatura()
	if conectat:
		_STARE["neconectat_de"] = 0
		_STARE["reporniri"] = 0
	elif not _STARE["neconectat_de"]:
		_STARE["neconectat_de"] = acum
	if not greu or not s["pornit"] or LUCRARI.stare()["lucreaza"]:
		return
	plan = _citestePlan()
	if viu and fel in ("ikev2", "l2tp"):
		# charon reface singur legatura (dpd_action=restart); paza vede numai daca o are acum
		_STARE["sa_ok"] = legaturaIpsec()
	with _LACAT_RETEA:
		if viu and conectat:
			sus = _citesteJson(CALE_SUS) or {}
			if plan.get("mod") == "tot" and sus.get("fel"):
				dns = sus.get("dns") or list(DNS_REZERVA)
				if aplicaDns(dns):
					jurnal("DNS-ul VPN-ului pus din nou (l-a schimbat altcineva)")
			if plan.get("mod") == "ales" and acum - _STARE["ales_cand"] > ALES_IMPROSPATARE_S:
				_STARE["ales_cand"] = acum
				ales = ipuriAles(s)
				if ales and set(ales) != set(plan.get("ales") or []):
					_stergeReguli((PRIO_ALES,))
					aplicaComenzi(comenziReguliAles(ales))
					plan["ales"] = ales
					_scrieAtomic(CALE_PLAN, json.dumps(plan), 0o600)
			return
		# in modul navigator nu se opreste: navigatorul tot nu iese direct, iar openvpn revine singur
		if viu and fel not in ("wireguard", "") and not plan.get("oprire_totala") and plan.get("mod") != "navigator" and \
				_STARE["neconectat_de"] and \
				acum - _STARE["neconectat_de"] > CADERE_LUNGA_S:
			jurnal("fara legatura de %d s: opresc openvpn, internetul merge direct pana la repornire" % (
				acum - _STARE["neconectat_de"]))
			_opresteTot()
			viu = False
		if viu:
			return
		motiv, de_cont = eroareProtocol(fel or plan.get("fel", ""))
		if de_cont:
			_STARE.update(eroare=motiv, eroare_cont=True)
			_opresteTot()
			salveazaSetari(pornit=False)
			jurnal("numele sau parola nu sunt bune: VPN-ul ramane oprit")
			return
		if not plan.get("oprire_totala") and plan.get("mod") != "navigator":
			curataRetea()
		if not _STARE["urmatoarea"]:
			pauza = REPORNIRI_S[min(_STARE["reporniri"], len(REPORNIRI_S) - 1)]
			_STARE["urmatoarea"] = acum + pauza
			jurnal("VPN-ul a cazut; repornesc peste %d s" % pauza)
			return
		if acum < _STARE["urmatoarea"]:
			return
		_STARE["urmatoarea"] = 0
		_STARE["reporniri"] += 1
	LUCRARI.porneste(LUCRARE_PORNESTE, _repornesteDupaCadere)


def _repornesteDupaCadere():
	if not setari()["pornit"]:
		return True, ""
	reusit, mesaj = _pornesteAcum()
	if not reusit:
		_STARE["eroare"] = mesaj
	return reusit, mesaj


def _bucla():
	n = 0
	while not _PAZA["opreste"]:
		try:
			pasPaza(greu=(n % (PAZA_GREA_S // PAZA_S) == 0))
		except Exception as eroare:
			jurnal("paza: %r" % (eroare,))
		n += 1
		time.sleep(PAZA_S)
		if not setari()["pornit"] and not vpnViu() and not LUCRARI.stare()["lucreaza"]:
			break
	_PAZA["fir"] = None


# ---------------------------------------------------------------- lucrarile (un fir deodata)

class Lucrari(object):
	"""Ruleaza cate o lucrare (functie care intoarce (reusit, mesaj, ...)) pe un fir separat. `sincron` o ruleaza pe
	loc (probele de pe PC)."""

	def __init__(self):
		self._lacat = threading.Lock()
		self._curenta = None
		self._ultima = None
		self._numar = 0
		self.sincron = False

	def porneste(self, nume, functie, *argumente):
		"""Numarul lucrarii pornite, sau None daca merge deja una."""
		with self._lacat:
			if self._curenta is not None:
				return None
			self._numar += 1
			numar = self._numar
			self._curenta = {"id": numar, "nume": nume}
		if self.sincron:
			self._ruleaza(numar, nume, functie, argumente)
		else:
			fir = threading.Thread(target=self._ruleaza, args=(numar, nume, functie, argumente), name="HdsVpn-" + nume)
			fir.daemon = True
			fir.start()
		return numar

	def _ruleaza(self, numar, nume, functie, argumente):
		try:
			rez = functie(*argumente)
			reusit, mesaj = bool(rez[0]), rez[1]
		except Exception as eroare:
			reusit, mesaj = False, _("Eroare pe receptor: %s") % ascunde(eroare)
			jurnal("lucrarea %s: %r" % (nume, eroare))
		with self._lacat:
			self._ultima = {"id": numar, "nume": nume, "reusit": reusit, "mesaj": mesaj, "ora": time.time()}
			self._curenta = None

	def stare(self):
		with self._lacat:
			return {"lucreaza": self._curenta["nume"] if self._curenta else None,
				"ultima": dict(self._ultima) if self._ultima else None}


LUCRARI = Lucrari()

LUCRARE_PORNESTE = "porneste"
LUCRARE_OPRESTE = "opreste"
LUCRARE_STICK = "stick"
LUCRARE_IP = "ip"
LUCRARE_INSTALEAZA = "instaleaza"
LUCRARE_REPORNESTE = "reporneste"


def _jobPorneste():
	s = salveazaSetari(pornit=True)
	reusit, mesaj = _pornesteAcum()
	if not reusit:
		# motivul se vede in rezultatul lucrarii; starea pastreaza numai erorile legaturii (puse de _pornesteOpenvpn).
		# VPN-ul nu mai e cerut, deci nici oprirea totala: totul se scoate
		salveazaSetari(pornit=False)
		with _LACAT_RETEA:
			_opresteTot()
		return False, mesaj
	if _STARE.get("legatura") == "CONNECTED" or interfataExista(INTERFATA_WG) or wgInNetns():
		ip = aflaIpVpn()
		_STARE["ip"] = ip
		if ip:
			mesaj = "%s %s" % (mesaj, textIp(ip))
	jurnal("VPN pornit (%s, %s)" % (s["furnizor"], s["mod"]))
	return True, mesaj


def _jobOpreste():
	salveazaSetari(pornit=False)
	return _opresteAcum()


def _jobReporneste():
	if not setari()["pornit"]:
		return True, _("Setarea este salvată.")
	reusit, mesaj = _pornesteAcum()
	if not reusit:
		salveazaSetari(pornit=False)
		with _LACAT_RETEA:
			_opresteTot()
		return False, mesaj
	return True, _("Setarea este salvată; VPN-ul a pornit din nou.")


def pornesteVpn():
	return LUCRARI.porneste(LUCRARE_PORNESTE, _jobPorneste)


def opresteVpn():
	return LUCRARI.porneste(LUCRARE_OPRESTE, _jobOpreste)


def pornesteStick():
	return LUCRARI.porneste(LUCRARE_STICK, adaugaDePeStick)


def pornesteIp():
	return LUCRARI.porneste(LUCRARE_IP, verificaIp)


def pornesteInstalarea(fel):
	return LUCRARI.porneste(LUCRARE_INSTALEAZA, instaleaza, fel)


def schimba(**schimbari):
	"""Schimba setarile din ecran sau din pagina: (reusit, mesaj, numarul lucrarii de repornire sau None). Cu VPN-ul
	pornit, o schimbare a serverului, a modului, a opririi totale sau a adreselor il reporneste."""
	s = setari()
	if "furnizor" in schimbari and not grupCunoscut(schimbari["furnizor"]):
		return False, _("Furnizorul nu este cunoscut."), None
	if "mod" in schimbari and schimbari["mod"] not in MODURI:
		return False, _("Alege ce trece prin VPN."), None
	if "profil" in schimbari:
		p = profil(schimbari["profil"])
		grup = schimbari.get("furnizor", s["furnizor"])
		if schimbari["profil"] and (p is None or p.get("grup") != grup):
			return False, _("Serverul nu este al acestui furnizor."), None
	if "adrese" in schimbari:
		schimbari["adrese"] = [a for a in schimbari["adrese"] if adresaBuna(a)][:MAX_ADRESE]
	for k in ("oprire_totala", "la_pornire", "iptv"):
		if k in schimbari:
			schimbari[k] = bool(schimbari[k])
	if s["pornit"] and "furnizor" in schimbari and schimbari["furnizor"] != s["furnizor"]:
		return False, _("Oprește întâi VPN-ul, apoi schimbă furnizorul."), None
	if "furnizor" in schimbari and schimbari["furnizor"] != s["furnizor"] and "profil" not in schimbari:
		schimbari["profil"] = ""
	nou = salveazaSetari(**schimbari)
	cheie = ("profil", "mod", "oprire_totala", "adrese", "iptv")
	if nou["pornit"] and any(nou[k] != s[k] for k in cheie if k in schimbari):
		numar = LUCRARI.porneste(LUCRARE_REPORNESTE, _jobReporneste)
		if numar is None:
			return True, _("Setarea este salvată; se aplică la următoarea pornire a VPN-ului."), None
		return True, _("Setarea este salvată; VPN-ul pornește din nou."), numar
	return True, _("Setarea este salvată."), None


# ---------------------------------------------------------------- instalarea programelor (feedul de extensii)

def bazaImaginii():
	for rand in (_citeste(CALE_MODEL, 4096) or "").splitlines():
		if rand.startswith("version="):
			v = rand.split("=", 1)[1].strip()
			if re.match(r"^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\Z", v):
				return v
	return ""


def canalSiArhitecturi():
	"""(canal, baza, arhitecturi) dupa feedul actualizarilor de pe receptor (proba sau public); fara el: public, baza
	din /etc/hdsatelit-model, arhitecturile imaginii."""
	canal, baza, arh = "public", "", []
	try:
		from Components import HdsActualizari as HA
	except ImportError:
		HA = None
	if HA is not None:
		try:
			c, surse, b = HA.canalul()
			if c:
				canal = "proba" if c.startswith("proba") else "public"
				baza = b
				arh = [x[2] for x in surse if x[2] not in arh]
		except Exception as eroare:
			jurnal("canalul feedului: %r" % (eroare,))
	baza = baza or bazaImaginii()
	return canal, baza, arh or list(ARHITECTURI_EXTENSII)


def textConfExtensii(canal, baza, arhitecturi):
	r = ["# HD Satelit: feedul de extensii al imaginii %s (programele VPN si altele care nu sunt in imagine)." % baza,
		"# Scris de Setari > Retea & Internet > VPN. Nu e feedul actualizarilor."]
	for a in arhitecturi:
		if re.match(r"^[a-z0-9][a-z0-9_\-]{0,63}\Z", a):
			r.append("src/gz hdsatelit-extensii-%s %s/%s/%s/%s" % (a, ADRESA_EXTENSII, canal, baza, a))
	return "\n".join(r) + "\n"


def _ocupatOpkg():
	"""Alt opkg ruleaza acum. Lacatul lui e /run/opkg.lock (pe unele imagini /var/run/opkg.lock): citit din /proc/locks
	cu HdsActualizari.opkg_ocupat, fara sa fie luat; numai unde acela nu se incarca (probele de pe PC), cu lockf."""
	try:
		from Components import HdsExtensiiLucru as X
		if X.lucrareInCurs() or X.descarcareInCurs():
			return True
	except Exception:
		pass
	try:
		from Components import HdsActualizari as HA
		return bool(HA.opkg_ocupat(RADACINA or "/"))
	except Exception:
		pass
	return any(os.path.exists(_cale(c)) and _lacatViu(_cale(c)) for c in ("/run/opkg.lock", "/var/run/opkg.lock"))


def _lacatViu(cale):
	"""True daca alt program tine zavorul lui opkg (lockf, ca libopkg)."""
	try:
		import fcntl
	except ImportError:
		return False
	try:
		with open(cale, "ab") as f:
			fcntl.lockf(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
			fcntl.lockf(f.fileno(), fcntl.LOCK_UN)
		return False
	except (OSError, IOError):
		return True


def instaleaza(fel):
	"""Instaleaza programele VPN din feedul de extensii al bazei. (reusit, mesaj)."""
	if fel not in FELURI:
		return False, _("Felul VPN-ului nu este cunoscut.")
	poate, motiv = nucleuPoate(fel)
	if not poate:
		return False, motiv
	if not _executabil(PROGRAM_OPKG):
		return False, _("Instalarea pachetelor nu este disponibilă în această imagine.")
	canal, baza, arh = canalSiArhitecturi()
	if not baza:
		return False, _("Nu știu imaginea de bază a receptorului, deci nici feedul de extensii.")
	if _ocupatOpkg():
		return False, _("Altă instalare rulează acum. Așteaptă să se termine.")
	text = textConfExtensii(canal, baza, arh)
	_MODULE_DISC.clear()
	if _citeste(CALE_CONF_EXTENSII) != text:
		_scrieAtomic(CALE_CONF_EXTENSII, text, 0o644)
	nume = pachete(fel)
	try:
		fd = os.open(_cale(CALE_JURNAL_OPKG), os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
		iesire = os.fdopen(fd, "wb")
	except OSError:
		iesire = None
	try:
		jurnal("opkg update, apoi opkg install %s" % " ".join(nume))
		cod, _t = _ruleaza([PROGRAM_OPKG, "update"], TIMP_OPKG_UPDATE_S, iesire)
		if cod != 0:
			jurnal("opkg update: cod %s" % cod)
		cod, _t = _ruleaza([PROGRAM_OPKG, "install", "--no-install-recommends"] + nume, TIMP_OPKG_INSTALL_S, iesire)
	finally:
		if iesire is not None:
			iesire.close()
	try:
		from Components import HdsExtensiiLucru as X
		X.catalogVechi()
	except Exception:
		pass
	_MODULE_DISC.clear()
	if fel != "wireguard":
		incarcaTun()
	elif not areWireguardInNucleu():
		_ruleaza([PROGRAM_MODPROBE, "wireguard"], 20)
	if cod == 0 and programe().get(fel):
		return True, _("Programele VPN sunt instalate.")
	if fel == "wireguard" and wireguardIndisponibil():
		# feedul nu are modulul nucleului acestui receptor
		return False, _(TEXT_WG_INDISPONIBIL)
	if cod == -2:
		return False, _("Instalarea nu a terminat la timp. Verifică legătura la internet.")
	# opkg (wget -q) spune numai "wget returned 5" cand certificatul cade; ajutorul comun vede daca e de vina ceasul
	ceas = _mesajCeas((_citeste(CALE_JURNAL_OPKG, 262144) or "")[-4096:])
	if ceas:
		return False, ceas
	return False, _("Programele VPN nu s-au instalat. Feedul de extensii al imaginii %s nu le are încă sau nu răspunde.") % baza


# ---------------------------------------------------------------- pornirea receptorului

def _asteaptaRuta(secunde=60):
	for _i in range(secunde):
		text = _citeste("/proc/net/route", 65536) or ""
		for rand in text.splitlines()[1:]:
			parti = rand.split()
			if len(parti) > 2 and parti[1] == "00000000":
				return True
		time.sleep(1)
	return False


def _jobLaPornire():
	"""Pornirea odata cu receptorul. Daca nu merge din pricina retelei (serverul nu se gaseste, nu raspunde), VPN-ul
	ramane cerut si paza incearca din nou (10, 30, 60 s, apoi la 5 minute); daca lipseste ceva (serverul ales,
	programele, contul), VPN-ul nu mai e cerut."""
	_asteaptaRuta()
	s = setari()
	p = profil(s["profil"])
	if p is None or p.get("grup") != s["furnizor"] or not programe().get(p["fel"]) or (
			p["fel"] == "openvpn" and p.get("cere_cont") and not areCont()):
		return _jobPorneste()
	reusit, mesaj = _pornesteAcum()
	if not reusit:
		_STARE["eroare"] = mesaj
		if not _STARE.get("eroare_cont"):
			_pornestePaza()
		else:
			salveazaSetari(pornit=False)
			with _LACAT_RETEA:
				_opresteTot()
	return reusit, mesaj


def porneste():
	"""Din mytest.py, la pornirea interfetei: urmareste un VPN care merge (repornirea interfetei nu il opreste),
	porneste VPN-ul daca omul a cerut asta la pornirea receptorului, altfel scoate ce a ramas."""
	try:
		s = setari()
		if vpnViu():
			_secreteDinCont()
			_pornestePaza()
			jurnal("VPN-ul mergea deja: il urmaresc")
			return
		if s["pornit"] and s["la_pornire"]:
			LUCRARI.porneste(LUCRARE_PORNESTE, _jobLaPornire)
			return
		if s["pornit"]:
			salveazaSetari(pornit=False)
		if os.path.exists(_cale(CALE_PLAN)) or os.path.exists(_cale(CALE_RESOLV_INAINTE)):
			curataRetea()
			_sterge(CALE_PLAN)
	except Exception as eroare:
		jurnal("pornirea: %r" % (eroare,))


# ---------------------------------------------------------------- starea si textele

def furnizoriVizibili(s=None):
	"""Grupurile aratate in ecran si in pagina: cele cu macar un fel care poate merge pe nucleul acestui receptor (si
	cel ales acum, oricare ar fi)."""
	s = s or setari()
	return [f for f in furnizori() if f == s["furnizor"] or any(felPosibil(x) for x in feluriGrup(f))]


def feluriAdauga():
	"""Felurile care se pot scrie de mana (Adauga VPN, Scriu datele de mana) pe acest receptor: [(fel, text)]."""
	return [(f, textFel(f)) for f in ("ikev2", "openconnect", "l2tp", "shadowsocks") if felPosibil(f)]


def stare():
	"""Tot ce arata ecranul si pagina web, fara secrete."""
	s = setari()
	lista = profiluriGrup(s["furnizor"])
	p = profil(s["profil"])
	if p is not None and p.get("grup") != s["furnizor"]:
		p = None
	fel = p["fel"] if p else felFurnizor(s["furnizor"])
	lucrare = LUCRARI.stare()
	sus = _citesteJson(CALE_SUS) or {}
	viu = vpnViu()
	plan = _citestePlan()
	if lucrare["lucreaza"] in (LUCRARE_PORNESTE, LUCRARE_REPORNESTE):
		legatura = "se_conecteaza"
	elif not viu and not s["pornit"]:
		legatura = "oprit"
	elif viu and _STARE["legatura"] == "CONNECTED":
		legatura = "conectat"
	elif s["pornit"] and (plan.get("oprire_totala") or plan.get("mod") == "navigator"):
		legatura = "blocat"
	elif viu:
		legatura = "se_conecteaza"
	else:
		legatura = "eroare" if _STARE["eroare"] else "oprit"
	cap, motiv_cap = capabil(fel)
	lipsa = campuriLipsa(p) if p else []
	campuri = (["nume", "parola"] if fel == "openvpn" else list(p.get("campuri") or [])) if p else (
		["nume", "parola"] if fel == "openvpn" else [])
	moduri = moduriPosibile(fel)
	mod = modEfectiv(s)
	return {
		"furnizor": s["furnizor"], "fel": fel, "mod": mod if mod in moduri else moduri[0],
		"oprire_totala": s["oprire_totala"], "la_pornire": s["la_pornire"], "pornit": s["pornit"], "iptv": s["iptv"],
		"adrese": list(s["adrese"]),
		"profil": ({"id": p["id"], "titlu": p["titlu"], "fel": p["fel"], "gazde": list(p.get("gazde") or []),
			"plin": p.get("plin", True), "cere_cont": bool(p.get("cere_cont"))} if p else None),
		"profiluri": [{"id": x["id"], "titlu": x["titlu"]} for x in lista],
		"nr_profiluri": len(lista),
		"cont": areCont() if fel == "openvpn" else bool(p) and not any(c in lipsa for c in ("nume", "parola")),
		"campuri": campuri,
		"campuri_lipsa": lipsa,
		"programe": programe(),
		"lipsesc": cap == "instaleaza",
		"indisponibil": cap == "nu",
		"text_indisponibil": motiv_cap if cap == "nu" else "",
		"wg_indisponibil": fel == "wireguard" and cap == "nu",
		"furnizori": furnizoriVizibili(s),
		"moduri": moduri,
		"feluri_adauga": feluriAdauga(),
		"pin_propus": (_STARE.get("pin_propus") or "") if fel == "openconnect" else "",
		"legatura": legatura,
		"eroare": _STARE["eroare"] if legatura in ("eroare", "oprit", "blocat") else "",
		"ip": dict(_STARE["ip"]) if (_STARE["ip"] and legatura == "conectat") else None,
		"interfata": sus.get("dev", ""),
		"retele": list(sus.get("retele") or []),
		"netns": bool(sus.get("netns")),
		"lucrare": lucrare,
	}


def textFel(fel):
	"""Numele felului de VPN (nume proprii, aceleasi in toate limbile)."""
	return {"openvpn": "OpenVPN", "wireguard": "WireGuard", "ikev2": "IKEv2/IPsec",
		"openconnect": "OpenConnect (Cisco AnyConnect, GlobalProtect, Fortinet)", "shadowsocks": "Shadowsocks",
		"l2tp": "L2TP/IPsec"}.get(fel, fel)


def textFurnizor(f):
	x = _GRUPURI_ADAUGATE.get(f)
	if isinstance(x, dict):
		return x["text"]
	return {"hma": _("HMA (HideMyAss), fișiere OpenVPN"), "nordvpn": _("NordVPN, fișiere OpenVPN"),
		"surfshark": _("Surfshark, fișiere OpenVPN"), "protonvpn": _("Proton VPN, fișiere OpenVPN"),
		"openvpn": _("OpenVPN, fișier propriu"), "wireguard": _("WireGuard, fișier propriu"),
		"pia": _("PIA, fișiere OpenVPN"), "mullvad": _("Mullvad, WireGuard"),
		"ikev2": _("IKEv2/IPsec, server propriu"), "openconnect": _("OpenConnect (Cisco AnyConnect și altele)"),
		"shadowsocks": _("Shadowsocks, adresa ss://"), "l2tp": _("L2TP/IPsec, server propriu")}.get(f, f)


def textCont(f):
	"""Eticheta numelui si a parolei, dupa furnizor."""
	if f == "hma":
		return _("Intră cu numele și parola HMA")
	if f in FURNIZORI_SERVICIU:
		return _("Numele și parola de serviciu")
	return _("Numele și parola contului")


def textExplicatieCont(f):
	if f == "hma":
		return _("Numele și parola contului HMA. După salvare nu se mai arată nicăieri. Se scriu mai ușor din telefon, "
			"în interfața web.")
	if f in FURNIZORI_SERVICIU:
		return _("Datele de serviciu pentru configurarea manuală (nu emailul și parola contului); le găsești în contul "
			"furnizorului. După salvare nu se mai arată nicăieri. Se scriu mai ușor din telefon, în interfața web.")
	return _("Ale contului la furnizor (la HMA, cele ale contului HMA). După salvare nu se mai arată nicăieri. Se scriu "
		"mai ușor din telefon, în interfața web.")


def textMod(mod):
	return {"navigator": _("Numai navigatorul și HbbTV"), "tot": _("Tot traficul, în afară de rețeaua din casă"),
		"ales": _("Numai IPTV și adresele alese")}.get(mod, mod)


def textModNavigator():
	# la conditional: alegerea se vede si cu VPN-ul oprit, cand nimic nu trece prin el; incape in 3 randuri pe ecran
	return _("Cu VPN-ul pornit, numai navigatorul și HbbTV trec prin VPN; restul receptorului merge direct. Navigatorul "
		"nu vede atunci rețeaua din casă și, dacă VPN-ul cade, nu iese pe internet până revine. Un navigator deschis "
		"înainte trece prin VPN după ce îl redeschizi.")


def textExplicatieMod(s):
	"""Explicatia alegerii "Ce trece prin VPN" (ecranul si pagina web)."""
	if s["mod"] == "navigator":
		return textModNavigator()
	if s["mod"] == "ales":
		return _("Numai sursele IPTV din liste și adresele scrise în interfața web trec prin VPN (adrese scrise: %d). "
			"DNS-ul rămâne cel de acasă. HbbTV și navigatorul nu trec prin VPN în acest mod.") % len(s["adrese"])
	return _("Tot ce iese din receptor în internet (HbbTV, IPTV, navigatorul, descărcările) trece prin VPN. Rețeaua din "
		"casă (interfața web, SSH, telefoanele) rămâne directă.")


def textLegatura(s):
	return {"oprit": _("Oprit"), "se_conecteaza": _("Se conectează..."), "conectat": _("Conectat"),
		"blocat": _("Fără legătură: navigatorul nu iese pe internet până revine VPN-ul") if s["mod"] == "navigator" else
			_("Fără legătură: internetul este oprit până revine VPN-ul"),
		"eroare": _("Nu s-a conectat")}.get(s["legatura"], "")


def textIp(ip):
	if not ip:
		return ""
	loc = ", ".join(x for x in (ip.get("oras"), ip.get("tara")) if x)
	return _("Adresa văzută pe internet: %s") % ip["ip"] + (" (%s)" % loc if loc else "")


def textDetalii(s):
	"""Randurile de sub starea mare: serverul, ce trece prin VPN, adresa vazuta pe internet sau motivul unei erori."""
	r = []
	if s["profil"]:
		r.append(_("Serverul: %s") % s["profil"]["titlu"])
	else:
		r.append(_("Serverul: niciunul ales"))
	# cu VPN-ul oprit nu se scrie "Prin VPN": nimic nu trece prin el (alegerea se vede numai in randul ei)
	if s["legatura"] == "oprit":
		pass
	elif s["retele"]:
		r.append(_("Prin VPN: numai rețelele din fișier (%s)") % ", ".join(s["retele"][:3]))
	else:
		r.append(_("Prin VPN: %s") % textMod(s["mod"]))
	if s["ip"]:
		r.append(textIp(s["ip"]))
	if s["eroare"]:
		r.append(s["eroare"])
	return r


def textLucrare(nume):
	return {
		LUCRARE_PORNESTE: _("Se pornește VPN-ul..."),
		LUCRARE_OPRESTE: _("Se oprește VPN-ul..."),
		LUCRARE_STICK: _("Se citesc fișierele de pe stick..."),
		LUCRARE_IP: _("Se află adresa văzută pe internet..."),
		LUCRARE_INSTALEAZA: _("Se instalează programele VPN (câteva minute)..."),
		LUCRARE_REPORNESTE: _("VPN-ul pornește din nou cu setarea nouă..."),
	}.get(nume, _("Se lucrează..."))


def textProgrameLipsa(fel):
	if fel == "openconnect":
		return _("Lipsește programul OpenConnect. Se instalează din feedul de extensii HD Satelit.")
	if fel == "ikev2":
		return _("Lipsește programul strongSwan (IKEv2). Se instalează din feedul de extensii HD Satelit.")
	if fel == "shadowsocks":
		return _("Lipsesc programele Shadowsocks (ss-local și hev-socks5-tunnel). Se instalează din feedul de "
			"extensii HD Satelit.")
	if fel == "l2tp":
		return _("Lipsesc programele L2TP (xl2tpd, pppd și strongSwan). Se instalează din feedul de extensii HD "
			"Satelit.")
	if fel == "wireguard":
		return _("Lipsește programul WireGuard (wireguard-tools). Se instalează din feedul de extensii HD Satelit.")
	return _("Lipsește programul OpenVPN (openvpn și tun.ko). Se instalează din feedul de extensii HD Satelit.")


def textCumIeiFisierele(furnizor):
	x = _GRUPURI_ADAUGATE.get(furnizor)
	if isinstance(x, dict) and x.get("cum"):
		return x["cum"]
	if furnizor == "pia":
		return _("PIA: scrii numele și parola la Alege furnizorul (fără fișiere) și alegi țara. Merg și fișierele "
			"OpenVPN de la PIA, pe stick în dosarul hdsatelit/vpn.")
	if furnizor == "mullvad":
		return _("Mullvad: scrii numărul contului la Alege furnizorul (fără fișiere) și alegi țara. Merge și fișierul "
			"WireGuard (.conf) din contul Mullvad, pe stick în dosarul hdsatelit/vpn.")
	if furnizor == "ikev2":
		return _("Furnizorul îți dă adresa serverului, numele și parola pentru IKEv2 (la NordVPN, Surfshark și Proton "
			"VPN sunt cele de serviciu). Alege Adaugă VPN, apoi Scriu datele de mână. Certificatul CA al furnizorului, "
			"dacă îl dă, și profilurile .sswan sau .mobileconfig pune-le pe stick în dosarul hdsatelit/vpn.")
	if furnizor == "openconnect":
		return _("Pentru Cisco AnyConnect, GlobalProtect, Pulse, Fortinet și celelalte: adresa serverului (https://...), "
			"numele și parola. Alege Adaugă VPN, apoi Scriu datele de mână, sau lipește adresa în interfața web.")
	if furnizor == "shadowsocks":
		return _("Adresa ss:// sau fișierul JSON de la furnizor: pune-l pe stick în dosarul hdsatelit/vpn sau lipește-l "
			"în interfața web, la Adaugă VPN.")
	if furnizor == "l2tp":
		return _("Adresa serverului, cheia comună (PSK), numele și parola. Alege Adaugă VPN, apoi Scriu datele de "
			"mână; merge și profilul .mobileconfig.")
	if furnizor == "hma":
		return _("HMA a oprit în 2023 configurarea manuală (routere, Linux): nu mai dă fișiere OpenVPN și nici parole "
			"pentru alte aparate, iar codul de activare merge numai în aplicațiile HMA (Windows, Mac, Android, iOS). Dacă "
			"HMA îți dă totuși fișierele, pune-le pe stick în dosarul hdsatelit/vpn sau trimite-le din telefon. "
			"Configurare oficială pentru routere, cu fișiere OpenVPN și date de serviciu, au NordVPN, Surfshark și "
			"Proton VPN.")
	if furnizor == "nordvpn":
		return _("În contul NordVPN: Set up NordVPN manually. Fișierele OpenVPN (câte unul pe server, sau arhiva "
			"ovpn.zip din ajutorul lor pentru Linux) pune-le pe stick în dosarul hdsatelit/vpn sau trimite-le din "
			"telefon. Numele și parola sunt cele de serviciu (Service credentials), nu emailul contului.")
	if furnizor == "surfshark":
		return _("În contul Surfshark: VPN, Manual setup, OpenVPN. Fișierele (fila Locations sau arhiva din ajutorul lor "
			"pentru Linux) pune-le pe stick în dosarul hdsatelit/vpn sau trimite-le din telefon. Numele și parola sunt "
			"cele din fila Credentials, nu emailul contului. Pentru WireGuard alege furnizorul WireGuard.")
	if furnizor == "protonvpn":
		return _("În contul Proton: Downloads, OpenVPN configuration files (câte unul pe server). Pune-le pe stick în "
			"dosarul hdsatelit/vpn sau trimite-le din telefon. Numele și parola sunt cele de OpenVPN din Account, nu "
			"cele de logare. Pentru WireGuard alege furnizorul WireGuard.")
	if furnizor == "wireguard":
		return _("Fișierul WireGuard (.conf) îl dă furnizorul tău sau serverul tău. Pune-l pe stick în dosarul "
			"hdsatelit/vpn sau trimite-l din telefon, din interfața web.")
	return _("Fișierul OpenVPN (.ovpn) îl dă furnizorul tău. Pune-l pe stick în dosarul hdsatelit/vpn (merge și "
		"arhiva .zip, cu certificatele alături) sau trimite-l din telefon, din interfața web.")


def main(argv):
	if len(argv) >= 2 and argv[1] in ("openvpn-sus", "openvpn-jos"):
		try:
			return scriptOpenvpn(argv[1][8:], os.environ)
		except Exception as eroare:
			jurnal("scriptul %s: %r" % (argv[1], eroare))
			return 0
	if len(argv) >= 2 and argv[1] in ("openconnect-script", "ppp-sus", "ppp-jos"):
		try:
			if argv[1] == "openconnect-script":
				return scriptOpenconnect(os.environ)
			return scriptPpp(argv[1][4:], argv[2:], os.environ)
		except Exception as eroare:
			jurnal("scriptul %s: %r" % (argv[1], eroare))
			return 0
	print("folosire: %s openvpn-sus | openvpn-jos (pornit de openvpn)" % argv[0])
	return 2


if __name__ == "__main__":
	sys.exit(main(sys.argv))
