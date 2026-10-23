# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsAccesSsh.py: intrarea pe receptor prin SSH (dropbear, ca root). O singura logica pentru ecranul de pe televizor
# (Screens/HdsAccesSsh.py, Setari > Retea & Conexiuni > Acces SSH) si pentru pagina web /acces-ssh
# (Plugins/Extensions/HdsWebControl/acces_ssh_web.py).
#
# Parola lui root: o face numai /usr/sbin/hds-ssh-parola (pachetul hdsatelit-ssh), la prima pornire si la „Fă o parolă
# nouă”; in /etc/shadow intra numai hash-ul. Textul clar sta in /etc/hdsatelit-ssh/parola (0600) pana cand omul spune
# ca l-a notat („ascunde”) sau pana la parola urmatoare. Aici textul clar se citeste numai cand trebuie aratat
# (parolaDeAratat) si nu se copiaza nicaieri; din /etc/shadow se citeste numai felul campului (pusa, blocata, goala).
#
# Cheile: /home/root/.ssh/authorized_keys (dosarul 0700, fisierul 0600, scris atomic). Se primesc numai chei publice
# intregi, fara optiuni in fata: ssh-ed25519, ssh-rsa de cel putin MIN_BITI_RSA biti, ecdsa-sha2-nistp256/384/521 si
# cheile fizice sk-*; blobul base64 se desface si tipul dinauntru trebuie sa fie cel scris in fata. Se primesc si
# blocurile „---- BEGIN SSH2 PUBLIC KEY ----” (PuTTYgen). O cheie privata lipita din greseala e refuzata cu un mesaj
# anume si nu se pastreaza nicaieri. Randurile pe care nu le intelegem (chei cu optiuni puse de mana prin ssh,
# comentarii) raman in fisier neatinse. Amprenta e cea a lui ssh-keygen -l: SHA256, base64 fara „=”.
# Pe stick: dosarul hdsatelit/ssh (literele mari sau mici nu conteaza) de pe orice montare din /media, /run/media,
# /autofs sau /mnt, cu authorized_keys si fisiere *.pub; citite numai la cerere.
#
# „Fără parolă în rețeaua locală”: fisierul de reguli pam_access /etc/security/hds-ssh-retea-locala.conf, citit de
# /etc/pam.d/dropbear la fiecare logare. pam_access intoarce „refuzat” numai cand se potriveste o regula „-”; PAM lasa
# root fara parola numai daca in plus a doua verificare, /etc/security/hds-ssh-retele-locale.conf (fix, din pachet,
# aceleasi RETELE_LOCALE), spune ca adresa e din rețeaua locala. Orice alt rezultat (nicio regula potrivita, fisier
# lipsa sau stricat) duce la verificarea parolei. Pornit: regula „-” cu adresele din RETELE_LOCALE, apoi
# „+ : ALL : ALL”; oprit (implicit): numai „+ : ALL : ALL”. Parola din /etc/shadow nu se goleste niciodata.
#
# Rescrierea lui authorized_keys (adaugare, stergere) lucreaza pe octeti: randurile pe care nu le atingem raman octet cu
# octet, oricat de lungi si in orice codare. Un fisier mai mare decat MAX_FISIER_CHEI nu se rescrie deloc (mesaj, nu
# taiere).
#
# FIRUL: stare() citeste cateva fisiere mici (merge pe firul enigma2); cheile se desfac din nou numai cand
# authorized_keys s-a schimbat (inode, marime, ora). Tot ce scrie sau porneste un program (parola, cheile, stickul,
# optiunea) merge prin LUCRARI: un singur fir deodata, comun televizorului si paginii web, iar ecranul si pagina citesc
# rezultatul din stare(). Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC schimba RADACINA,
# PROGRAM_PAROLA si INTERPRET.
#
# Ecranul deschis: cat ecranul „Acces SSH” e pe televizor (parola mare, comenzile lui), ecranDeschis() e adevarat.
# Interfata web refuza atunci telecomanda si captura de ecran oricui nu e conectat cu codul
# (HdsWebControl/acces_ssh_web.refuzEcranDeschis): altfel un browser intrat fara cod ar citi parola din captura sau ar
# apasa OK in locul omului.

import base64
import binascii
import hashlib
import os
import re
import struct
import subprocess
import threading
import time

# probele de pe PC: radacina in care se lucreaza (pe receptor goala), programul parolei si interpretorul lui (pe PC,
# sh-ul lui Git)
RADACINA = ""
PROGRAM_PAROLA = "/usr/sbin/hds-ssh-parola"
INTERPRET = ()

CALE_PAROLA = "/etc/hdsatelit-ssh/parola"
CALE_SEMN = "/etc/hdsatelit-ssh/facuta"
# semnul lasat de hds-ssh-parola cand parola de la prima pornire nu s-a putut face (sters la prima reusita)
CALE_EROARE = "/etc/hdsatelit-ssh/eroare"
CALE_SHADOW = "/etc/shadow"
CALE_SSH = "/home/root/.ssh"
CALE_CHEI = "/home/root/.ssh/authorized_keys"
CALE_REGULA = "/etc/security/hds-ssh-retea-locala.conf"
CALE_DROPBEAR = "/etc/default/dropbear"
CALE_PAM = "/etc/pam.d/dropbear"
CALE_COMMON_AUTH = "/etc/pam.d/common-auth"
CALE_JURNAL = "/home/root/logs/hds-ssh.log"
CALE_MONTARI = "/proc/mounts"

# dosarul cheilor de pe stick, din radacina montarii
DOSAR_STICK = ("hdsatelit", "ssh")
# unde se cauta montarile stickurilor si discurilor
LOCURI_MONTARE = ("/media/", "/run/media/", "/autofs/", "/mnt/")
FS_FARA_DISC = ("tmpfs", "ramfs", "devtmpfs", "proc", "sysfs", "overlay", "squashfs", "nfs", "nfs4", "cifs", "smb3")

# adresele din reteaua de acasa (IPv4 private, legatura locala, bucla; IPv6 legatura locala si unica locala; IPv4 prin
# socluri IPv6), pentru „Fără parolă în rețeaua locală”
RETELE_LOCALE = (
	"127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16",
	"::1", "fe80::/10", "fc00::/7",
	"::ffff:127.0.0.0/104", "::ffff:10.0.0.0/104", "::ffff:172.16.0.0/108", "::ffff:192.168.0.0/112",
	"::ffff:169.254.0.0/112",
)

# tipurile primite si numele lor pe ecran
TIPURI = {
	"ssh-ed25519": "Ed25519",
	"ssh-rsa": "RSA",
	"ecdsa-sha2-nistp256": "ECDSA",
	"ecdsa-sha2-nistp384": "ECDSA",
	"ecdsa-sha2-nistp521": "ECDSA",
	"sk-ssh-ed25519@openssh.com": "Ed25519-SK",
	"sk-ecdsa-sha2-nistp256@openssh.com": "ECDSA-SK",
}
TIPURI_VECHI = ("ssh-dss",)
MIN_BITI_RSA = 2048
MAX_CHEI = 50
MAX_RAND = 16384
MAX_TEXT = 65536
# authorized_keys mai mare nu se rescrie (adaugarea si stergerea refuza cu un mesaj)
MAX_FISIER_CHEI = 1048576
MAX_COMENTARIU = 80
# comentariul cheii in randul listei si in intrebarea de stergere (amprenta sa ramana in rand si la litere 130 %)
MAX_COMENTARIU_RAND = 16
MAX_FISIERE_STICK = 20
MAX_FISIER_STICK = 65536
# cat asteapta cel mult programul parolei (openssl rand asteapta generatorul nucleului numai la pornire)
TIMP_PROGRAM_S = 60

_B64 = re.compile(r"^[A-Za-z0-9+/]+={0,2}$")
# „nullok” (nu „nullok_secure”, pe care pam_unix 1.7.1 nu-l cunoaste) pe randul pam_unix din common-auth
_NULLOK = re.compile(r"^\s*auth\s.*\bpam_unix\.so\b.*\bnullok\b", re.M)


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


def _cale(cale):
	return RADACINA + cale


def _citeste(cale, maxim=MAX_TEXT):
	"""Textul unui fisier (UTF-8, cel mult `maxim` octeti) sau None daca lipseste sau nu se poate citi."""
	try:
		with open(_cale(cale), "rb") as f:
			date = f.read(maxim + 1)
	except (OSError, IOError):
		return None
	return date[:maxim].decode("utf-8", "replace")


def _citesteOcteti(cale, maxim):
	"""(octetii fisierului, prea_mare): (b"", False) daca lipseste; cu prea_mare adevarat octetii nu se dau."""
	try:
		with open(_cale(cale), "rb") as f:
			date = f.read(maxim + 1)
	except (OSError, IOError):
		return b"", False
	if len(date) > maxim:
		return b"", True
	return date, False


def _scrieAtomic(cale, date, mod):
	"""Scrie `date` (text sau octeti) intr-un fisier temporar din acelasi dosar, fsync, apoi il pune peste `cale`
	(os.replace): la o cadere de curent ramane fisierul vechi sau cel nou, niciodata unul taiat. O_BINARY: pe PC (probele)
	os.open scrie altfel in mod text si ar pune CRLF."""
	if not isinstance(date, bytes):
		date = date.encode("utf-8")
	tinta = _cale(cale)
	tmp = tinta + ".nou"
	fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0), mod)
	try:
		os.write(fd, date)
		os.fsync(fd)
	finally:
		os.close(fd)
	os.chmod(tmp, mod)
	os.replace(tmp, tinta)


# ---------------------------------------------------------------- cheile


def amprenta(blob):
	"""Amprenta SHA256 a cheii, ca in ssh-keygen -l (base64 fara „=”)."""
	return "SHA256:" + base64.b64encode(hashlib.sha256(blob).digest()).decode("ascii").rstrip("=")


def _sir(date, poz):
	"""Un sir SSH (lungime pe 4 octeti, apoi octetii) de la `poz`: (octetii, pozitia de dupa)."""
	if poz + 4 > len(date):
		raise ValueError("scurt")
	n = struct.unpack(">I", date[poz:poz + 4])[0]
	poz += 4
	if n > len(date) - poz:
		raise ValueError("scurt")
	return date[poz:poz + n], poz + n


def analizeazaBlob(tip, blob):
	"""Numarul de biti al cheii dintr-un blob, daca blobul e o cheie publica intreaga de tipul `tip`; altfel ValueError
	cu motivul pe intelesul omului."""
	stricata = _("Cheia e stricată (textul de după tip nu e o cheie întreagă).")
	try:
		interior, poz = _sir(blob, 0)
		if interior != tip.encode("ascii"):
			raise ValueError(_("Tipul scris în fața cheii nu se potrivește cu cheia."))
		if tip in ("ssh-ed25519", "sk-ssh-ed25519@openssh.com"):
			pub, poz = _sir(blob, poz)
			if len(pub) != 32:
				raise ValueError(stricata)
			biti = 256
		elif tip == "ssh-rsa":
			e, poz = _sir(blob, poz)
			n, poz = _sir(blob, poz)
			if not e or not n:
				raise ValueError(stricata)
			biti = int(binascii.hexlify(n), 16).bit_length()
			if biti < MIN_BITI_RSA:
				raise ValueError(_("Cheia RSA are %d de biți. Receptorul primește numai chei RSA de cel puțin %d de biți.") % (biti, MIN_BITI_RSA))
		else:
			curba, poz = _sir(blob, poz)
			asteptata = {"ecdsa-sha2-nistp256": b"nistp256", "ecdsa-sha2-nistp384": b"nistp384",
				"ecdsa-sha2-nistp521": b"nistp521", "sk-ecdsa-sha2-nistp256@openssh.com": b"nistp256"}[tip]
			if curba != asteptata:
				raise ValueError(stricata)
			punct, poz = _sir(blob, poz)
			if not punct or punct[0:1] != b"\x04":
				raise ValueError(stricata)
			biti = {b"nistp256": 256, b"nistp384": 384, b"nistp521": 521}[curba]
		if tip.startswith("sk-"):
			_aplicatie, poz = _sir(blob, poz)
		if poz != len(blob):
			raise ValueError(stricata)
	except (struct.error, KeyError):
		raise ValueError(stricata)
	except ValueError as eroare:
		if str(eroare) == "scurt":
			raise ValueError(stricata)
		raise
	return biti


def _comentariu(text):
	"""Comentariul cheii, numai cu semne tiparibile, scurtat la MAX_COMENTARIU."""
	curat = "".join(c if (c.isprintable() and c not in "\r\n\t") else " " for c in text)
	curat = " ".join(curat.split())
	return curat[:MAX_COMENTARIU]


def _desfaCheie(tip, b64):
	if not _B64.match(b64) or len(b64) % 4:
		raise ValueError(_("Cheia e stricată (textul de după tip nu e o cheie întreagă)."))
	try:
		blob = base64.b64decode(b64.encode("ascii"))
	except (binascii.Error, ValueError):
		raise ValueError(_("Cheia e stricată (textul de după tip nu e o cheie întreagă)."))
	return blob, analizeazaBlob(tip, blob)


def analizeazaRand(rand, cuOptiuni=False):
	"""Cheia dintr-un rand de authorized_keys, ca dictionar (tip, nume_tip, blob, b64, biti, comentariu, amprenta,
	optiuni), sau ValueError cu motivul. Fara `cuOptiuni`, tipul trebuie sa fie primul cuvant (ce se adauga de pe
	ecran, din web sau de pe stick); cu el, primul cuvant care e un tip cunoscut (randurile existente, puse de mana)."""
	rand = rand.strip()
	if len(rand) > MAX_RAND:
		raise ValueError(_("Rândul e prea lung pentru o cheie publică."))
	parti = rand.split()
	if not parti:
		raise ValueError(_("Rândul e gol."))
	start = None
	for i, p in enumerate(parti):
		if p in TIPURI:
			start = i
			break
		if p in TIPURI_VECHI:
			raise ValueError(_("Cheile DSA nu mai sunt primite: sunt prea slabe. Fă o cheie Ed25519."))
		if not cuOptiuni:
			break
	if start is None:
		if not cuOptiuni and len(parti) > 1 and parti[1] in TIPURI:
			raise ValueError(_("Rândul are opțiuni în fața cheii. Pune numai cheia publică, așa cum e în fișierul .pub."))
		raise ValueError(_("Nu e o cheie publică SSH. Cheia începe cu ssh-ed25519, ssh-rsa sau ecdsa-sha2-."))
	if len(parti) < start + 2:
		raise ValueError(_("Cheia e stricată (textul de după tip nu e o cheie întreagă)."))
	tip, b64 = parti[start], parti[start + 1]
	blob, biti = _desfaCheie(tip, b64)
	return {
		"tip": tip,
		"nume_tip": TIPURI[tip],
		"blob": blob,
		"b64": b64,
		"biti": biti,
		"comentariu": _comentariu(" ".join(parti[start + 2:])),
		"amprenta": amprenta(blob),
		"optiuni": start > 0,
	}


def _esteCheiePrivata(text):
	return ("PRIVATE KEY-----" in text) or ("PuTTY-User-Key-File" in text)


def randuriDinText(text):
	"""Randurile de cheie dintr-un text lipit sau dintr-un fisier: blocurile SSH2 (RFC 4716, PuTTYgen) se fac un rand
	„tip base64 comentariu”; randurile goale si comentariile (#) se sar. Intoarce lista de (rand, None) sau
	(textul scurt, motiv) pentru ce nu se poate citi."""
	rez = []
	linii = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
	i = 0
	while i < len(linii):
		linie = linii[i].strip()
		i += 1
		if not linie or linie.startswith("#"):
			continue
		if linie.startswith("---- BEGIN SSH2 PUBLIC KEY"):
			comentariu = ""
			corp = []
			antet = True
			inchis = False
			while i < len(linii):
				l2 = linii[i].strip()
				i += 1
				if l2.startswith("---- END SSH2 PUBLIC KEY"):
					inchis = True
					break
				if antet and ":" in l2 and not _B64.match(l2):
					cheie, _sep, valoare = l2.partition(":")
					while valoare.endswith("\\") and i < len(linii):
						valoare = valoare[:-1] + linii[i].strip()
						i += 1
					if cheie.strip().lower() == "comment":
						comentariu = valoare.strip().strip('"')
					continue
				antet = False
				corp.append(l2)
			b64 = "".join(corp)
			if not inchis or not b64:
				rez.append(("---- BEGIN SSH2 PUBLIC KEY ----", _("Blocul cheii SSH2 nu e întreg.")))
				continue
			try:
				blob = base64.b64decode(b64.encode("ascii"))
				tip = _sir(blob, 0)[0].decode("ascii")
			except (binascii.Error, ValueError, UnicodeDecodeError):
				rez.append(("---- BEGIN SSH2 PUBLIC KEY ----", _("Cheia e stricată (textul de după tip nu e o cheie întreagă).")))
				continue
			rez.append(("%s %s %s" % (tip, b64, comentariu), None))
			continue
		rez.append((linie, None))
	return rez


# ultima citire a lui authorized_keys: (calea, inode, marimea, ora in ns) si rezultatul; stare() o cere la fiecare
# secunda cat ecranul e deschis, iar desfacerea a 50 de chei ar lua zeci de ms pe receptor
_CHEI_CITITE = {"semn": None, "rez": ([], 0)}


def citesteChei():
	"""(cheile intelese din authorized_keys, numarul randurilor neintelese)."""
	cale = _cale(CALE_CHEI)
	try:
		st = os.stat(cale)
		semn = (cale, st.st_ino, st.st_size, st.st_mtime_ns)
	except OSError:
		semn = None
	if semn is not None and semn == _CHEI_CITITE["semn"]:
		chei, alte = _CHEI_CITITE["rez"]
		return list(chei), alte
	date, _prea_mare = _citesteOcteti(CALE_CHEI, MAX_FISIER_CHEI)
	chei = []
	alte = 0
	for rand in date.decode("utf-8", "replace").splitlines():
		r = rand.strip()
		if not r or r.startswith("#"):
			continue
		try:
			chei.append(analizeazaRand(r, cuOptiuni=True))
		except ValueError:
			alte += 1
	_CHEI_CITITE["semn"] = semn
	_CHEI_CITITE["rez"] = (chei, alte)
	return list(chei), alte


def _randuriChei():
	"""Randurile lui authorized_keys ca octeti, fara sfarsitul de rand (un „\\r” ramane al randului), sau None daca
	fisierul e mai mare decat MAX_FISIER_CHEI."""
	date, prea_mare = _citesteOcteti(CALE_CHEI, MAX_FISIER_CHEI)
	if prea_mare:
		return None
	randuri = date.split(b"\n")
	if randuri and randuri[-1] == b"":
		randuri.pop()
	return randuri


def _cheieDinOcteti(rand):
	"""Cheia dintr-un rand existent (octeti, orice codare in comentariu) sau None."""
	try:
		return analizeazaRand(rand.decode("utf-8", "replace"), cuOptiuni=True)
	except ValueError:
		return None


def _textPreaMare():
	return _("Fișierul cheilor de pe receptor e prea mare (peste 1 MB). Scoate prin SSH cheile vechi din el.")


def _pregatesteDosar():
	dosar = _cale(CALE_SSH)
	if not os.path.isdir(dosar):
		os.makedirs(dosar, 0o700)
	os.chmod(dosar, 0o700)


def _scrieChei(randuri):
	"""Scrie randurile (octeti, fara sfarsit de rand) in authorized_keys."""
	_pregatesteDosar()
	_scrieAtomic(CALE_CHEI, b"".join(r + b"\n" for r in randuri), 0o600)


def adaugaChei(text, sursa=""):
	"""Adauga cheile din `text` (lipit in web, citit de pe stick). Intoarce (reusit, mesaj, detalii); detaliile au
	listele „adaugate”, „deja” (amprentele) si „respinse” (rand scurt, motiv)."""
	detalii = {"adaugate": [], "deja": [], "respinse": []}
	if not text or not text.strip():
		return False, _("Nu ai dat nicio cheie."), detalii
	if len(text) > MAX_TEXT:
		return False, _("Textul e prea lung pentru câteva chei publice."), detalii
	if _esteCheiePrivata(text):
		return False, _("Ai dat o cheie privată. Pune cheia publică (fișierul .pub). Cheia privată rămâne numai la tine."), detalii
	vechi = _randuriChei()
	if vechi is None:
		return False, _textPreaMare(), detalii
	existente = {}
	for r in vechi:
		c = _cheieDinOcteti(r)
		if c is not None:
			existente[c["blob"]] = c["amprenta"]
	noi = []
	for rand, motiv in randuriDinText(text):
		scurt = rand if len(rand) <= 60 else rand[:57] + "..."
		if motiv:
			detalii["respinse"].append((scurt, motiv))
			continue
		try:
			c = analizeazaRand(rand)
		except ValueError as eroare:
			detalii["respinse"].append((scurt, str(eroare)))
			continue
		if c["blob"] in existente:
			detalii["deja"].append(c["amprenta"])
			continue
		if len(existente) >= MAX_CHEI:
			detalii["respinse"].append((scurt, _("Receptorul are deja %d de chei, cât primește cel mult.") % MAX_CHEI))
			continue
		existente[c["blob"]] = c["amprenta"]
		linie = "%s %s" % (c["tip"], c["b64"])
		comentariu = c["comentariu"] or sursa
		if comentariu:
			linie += " " + comentariu
		noi.append(linie.encode("utf-8"))
		detalii["adaugate"].append(c["amprenta"])
	if noi:
		_scrieChei(vechi + noi)
	mesaj = _("Chei adăugate: %d. Erau deja: %d. Refuzate: %d.") % (
		len(detalii["adaugate"]), len(detalii["deja"]), len(detalii["respinse"]))
	if detalii["respinse"]:
		mesaj += " " + detalii["respinse"][0][1]
	return bool(noi) or (bool(detalii["deja"]) and not detalii["respinse"]), mesaj, detalii


def stergeCheie(amprenta_cheii):
	"""Scoate din authorized_keys randul (sau randurile) cu amprenta data; celelalte raman octet cu octet."""
	vechi = _randuriChei()
	if vechi is None:
		return False, _textPreaMare()
	ramase = []
	scoase = 0
	for r in vechi:
		c = _cheieDinOcteti(r)
		if c is not None and c["amprenta"] == amprenta_cheii:
			scoase += 1
			continue
		ramase.append(r)
	if not scoase:
		return False, _("Cheia nu mai era pe receptor.")
	_scrieChei(ramase)
	return True, _("Cheia a fost ștearsă. Calculatorul cu această cheie intră de acum numai cu parola.")


# ---------------------------------------------------------------- stickul


def _montari():
	lista = []
	text = _citeste(CALE_MONTARI) or ""
	for linie in text.splitlines():
		parti = linie.split()
		if len(parti) >= 3:
			lista.append((parti[1].replace("\\040", " "), parti[2]))
	return lista


def _intrareFaraMajuscule(dosar, nume):
	"""Calea intrarii `nume` din `dosar`, cu literele mari sau mici oricum (stickurile FAT si ext4 deopotriva)."""
	try:
		for intrare in os.listdir(dosar):
			if intrare.lower() == nume:
				return os.path.join(dosar, intrare)
	except OSError:
		pass
	return None


def dosareStick():
	"""Dosarele hdsatelit/ssh gasite pe montarile stickurilor si discurilor."""
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
	"""(calea, textul) pentru authorized_keys si *.pub din dosarele hdsatelit/ssh, cel mult MAX_FISIERE_STICK."""
	rez = []
	for dosar in dosareStick():
		try:
			nume = sorted(os.listdir(dosar))
		except OSError:
			continue
		for n in nume:
			if n.lower() != "authorized_keys" and not n.lower().endswith(".pub"):
				continue
			cale = os.path.join(dosar, n)
			if not os.path.isfile(cale) or len(rez) >= MAX_FISIERE_STICK:
				continue
			try:
				with open(cale, "rb") as f:
					date = f.read(MAX_FISIER_STICK + 1)
			except (OSError, IOError):
				continue
			if len(date) > MAX_FISIER_STICK:
				continue
			rez.append((cale, date.decode("utf-8", "replace")))
	return rez


def adaugaDePeStick():
	fisiere = fisiereStick()
	if not fisiere:
		return False, _("Pe stick nu am găsit dosarul hdsatelit/ssh cu chei. Pune în el fișierul authorized_keys sau cheile tale .pub.")
	text = "\n".join(t for _c, t in fisiere)
	if _esteCheiePrivata(text):
		return False, _("Pe stick e o cheie privată. Lasă pe stick numai cheile publice (.pub). Cheia privată rămâne numai la tine.")
	reusit, mesaj, _d = adaugaChei(text, sursa="stick")
	return reusit, _("De pe stick, fișiere citite: %d.") % len(fisiere) + " " + mesaj


# ---------------------------------------------------------------- parola


def felParola():
	"""Felul parolei lui root din /etc/shadow, fara hash: pusa | blocata | goala | lipsa."""
	text = _citeste(CALE_SHADOW)
	if text is None:
		return "lipsa"
	for linie in text.splitlines():
		parti = linie.split(":")
		if parti[0] == "root" and len(parti) > 1:
			camp = parti[1]
			if camp == "":
				return "goala"
			if camp[:1] in ("!", "*"):
				return "blocata"
			return "pusa"
	return "lipsa"


def parolaDeAratat():
	"""Textul clar al parolei, cat timp omul nu a spus ca l-a notat; altfel „”."""
	text = _citeste(CALE_PAROLA, 64)
	if not text:
		return ""
	return text.strip()[:32]


def _programParola(comanda):
	"""Porneste hds-ssh-parola cu `comanda`: (reusit, ultimul rand de eroare)."""
	if not os.access(PROGRAM_PAROLA, os.X_OK):
		return False, _("Lipsește programul care face parola (hds-ssh-parola).")
	mediu = dict(os.environ)
	if RADACINA:
		mediu["HDS_SSH_RADACINA"] = RADACINA
	try:
		p = subprocess.run(list(INTERPRET) + [PROGRAM_PAROLA, comanda], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
			stderr=subprocess.PIPE, timeout=TIMP_PROGRAM_S, env=mediu)
	except subprocess.TimeoutExpired:
		return False, _("Programul parolei nu a terminat la timp.")
	except OSError as eroare:
		return False, str(eroare)
	eroare = p.stderr.decode("utf-8", "replace").strip().splitlines()
	return p.returncode == 0, (eroare[-1] if eroare else "")


def faParolaNoua():
	reusit, eroare = _programParola("noua")
	if reusit:
		return True, _("Am făcut o parolă nouă. Cea veche nu mai merge.")
	return False, _("Parola nouă nu s-a putut face. Parola de dinainte rămâne.") + (" (%s)" % eroare if eroare else "")


def ascundeParola():
	reusit, eroare = _programParola("ascunde")
	if reusit:
		return True, _("Textul parolei a fost șters de pe receptor.")
	return False, _("Nu am putut ascunde parola.") + (" (%s)" % eroare if eroare else "")


def semnParola():
	"""Un semn care se schimba cu fiecare parola noua (inode si ora fisierului parolei), fara nimic din parola; „” daca
	parola nu se mai arata. Pagina web cere din nou parola cand semnul se schimba."""
	try:
		st = os.stat(_cale(CALE_PAROLA))
	except OSError:
		return ""
	return "%d-%d" % (st.st_ino, st.st_mtime_ns)


def nullokInPam():
	"""True daca common-auth lasa pam_unix sa primeasca o parola goala (nullok)."""
	return bool(_NULLOK.search(_citeste(CALE_COMMON_AUTH) or ""))


# ---------------------------------------------------------------- „Fără parolă în rețeaua locală”


def faraParolaInRetea():
	"""Pornita daca fisierul de reguli are o regula „-” (singura care duce la intrarea fara parola in PAM)."""
	text = _citeste(CALE_REGULA) or ""
	return any(l.startswith("-") for l in text.splitlines())


def textRegula(pornit):
	"""Regulile pam_access: „-” inseamna aici intrare fara parola (vezi /etc/pam.d/dropbear), „+” verificarea parolei."""
	if pornit:
		return ("# „Fără parolă în rețeaua locală” (Setări > Rețea și internet > Acces SSH): PORNITĂ.\n"
			"# Regula „-” lasă root să intre fără parolă de la adresele din rețeaua locală; de oriunde altundeva se cere parola.\n"
			"- : root : %s\n+ : ALL : ALL\n" % " ".join(RETELE_LOCALE))
	return ("# „Fără parolă în rețeaua locală” (Setări > Rețea și internet > Acces SSH): OPRITĂ.\n"
		"# Nimeni nu intră fără parolă sau cheie.\n+ : ALL : ALL\n")


def seteazaFaraParola(pornit):
	_scrieAtomic(CALE_REGULA, textRegula(bool(pornit)), 0o644)
	if faraParolaInRetea() != bool(pornit):
		return False, _("Setarea nu s-a putut salva.")
	if pornit:
		return True, _("Pornit: din rețeaua ta de acasă se intră pe receptor fără parolă.")
	return True, _("Oprit: pe receptor se intră numai cu parola sau cu o cheie.")


def dropbearFaraDovada():
	"""True daca dropbear e pornit cu -B (logare fara nicio dovada pentru conturile cu parola goala)."""
	text = _citeste(CALE_DROPBEAR) or ""
	for linie in text.splitlines():
		if linie.startswith("DROPBEAR_EXTRA_ARGS="):
			for a in linie.split("=", 1)[1].replace('"', " ").split():
				if a.startswith("-") and not a.startswith("--") and "B" in a:
					return True
	return False


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
			fir = threading.Thread(target=self._ruleaza, args=(numar, nume, functie, argumente), name="HdsAccesSsh-" + nume)
			fir.daemon = True
			fir.start()
		return numar

	def _ruleaza(self, numar, nume, functie, argumente):
		try:
			rez = functie(*argumente)
			reusit, mesaj = bool(rez[0]), rez[1]
		except Exception as eroare:
			reusit, mesaj = False, _("Eroare pe receptor: %s") % eroare
		with self._lacat:
			self._ultima = {"id": numar, "nume": nume, "reusit": reusit, "mesaj": mesaj, "ora": time.time()}
			self._curenta = None

	def stare(self):
		with self._lacat:
			return {
				"lucreaza": self._curenta["nume"] if self._curenta else None,
				"ultima": dict(self._ultima) if self._ultima else None,
			}


LUCRARI = Lucrari()

# numele lucrarilor si functiile lor, aceleasi pe televizor si in web
LUCRARE_PAROLA_NOUA = "parola-noua"
LUCRARE_ASCUNDE = "ascunde-parola"
LUCRARE_CHEI = "adauga-chei"
LUCRARE_STICK = "stick"
LUCRARE_STERGE = "sterge-cheie"
LUCRARE_FARA_PAROLA = "fara-parola"


def pornesteParolaNoua():
	return LUCRARI.porneste(LUCRARE_PAROLA_NOUA, faParolaNoua)


def pornesteAscunde():
	return LUCRARI.porneste(LUCRARE_ASCUNDE, ascundeParola)


def pornesteAdaugaChei(text):
	return LUCRARI.porneste(LUCRARE_CHEI, adaugaChei, text)


def pornesteStick():
	return LUCRARI.porneste(LUCRARE_STICK, adaugaDePeStick)


def pornesteSterge(amprenta_cheii):
	return LUCRARI.porneste(LUCRARE_STERGE, stergeCheie, amprenta_cheii)


def pornesteFaraParola(pornit):
	return LUCRARI.porneste(LUCRARE_FARA_PAROLA, seteazaFaraParola, bool(pornit))


# ---------------------------------------------------------------- ecranul de pe televizor deschis

# cate ecrane „Acces SSH” sunt deschise acum (le numara Screens/HdsAccesSsh.py, pe firul enigma2)
_ECRANE_DESCHISE = [0]


def semnalEcran(deschis):
	"""Ecranul „Acces SSH” spune ca s-a deschis (True) sau s-a inchis (False)."""
	_ECRANE_DESCHISE[0] = max(0, _ECRANE_DESCHISE[0] + (1 if deschis else -1))


def ecranDeschis():
	return _ECRANE_DESCHISE[0] > 0


def textLucrare(nume):
	return {
		LUCRARE_PAROLA_NOUA: _("Se face o parolă nouă..."),
		LUCRARE_ASCUNDE: _("Se ascunde parola..."),
		LUCRARE_CHEI: _("Se adaugă cheile..."),
		LUCRARE_STICK: _("Se citesc cheile de pe stick..."),
		LUCRARE_STERGE: _("Se șterge cheia..."),
		LUCRARE_FARA_PAROLA: _("Se salvează setarea..."),
	}.get(nume, _("Se lucrează..."))


# ---------------------------------------------------------------- starea si textele


def stare():
	"""Tot ce arata ecranul si pagina web, fara parola (parolaDeAratat) si fara hash."""
	chei, alte = citesteChei()
	return {
		"fel_parola": felParola(),
		"parola_de_vazut": os.path.isfile(_cale(CALE_PAROLA)),
		"parola_semn": semnParola(),
		"parola_facuta": os.path.isfile(_cale(CALE_SEMN)),
		"parola_eroare": os.path.isfile(_cale(CALE_EROARE)),
		"program": os.access(PROGRAM_PAROLA, os.X_OK),
		"chei": [dict((k, v) for k, v in c.items() if k not in ("blob", "b64")) for c in chei],
		"randuri_necunoscute": alte,
		"fara_parola": faraParolaInRetea(),
		"fara_dovada": dropbearFaraDovada(),
		"nullok": nullokInPam(),
		"lucrare": LUCRARI.stare(),
	}


def _goalaDeschisa(s):
	"""root fara parola si ceva care o primeste: dropbear -B sau nullok in common-auth."""
	return s["fel_parola"] == "goala" and bool(s.get("fara_dovada") or s.get("nullok"))


def textParola(s):
	"""Textul de sub parola, dupa stare(); parola insasi o arata ecranul, din parolaDeAratat()."""
	fel = s["fel_parola"]
	if fel == "goala":
		if _goalaDeschisa(s):
			return _("Contul root nu are parolă. Alege „Fă o parolă”.")
		return _("Contul root nu are parolă, deci nu se intră cu parolă, numai cu o cheie. Alege „Fă o parolă”.")
	if fel == "lipsa":
		return _("Nu am putut citi parola lui root.")
	if fel == "pusa":
		if s["parola_de_vazut"]:
			return _("Notează parola, apoi alege „Am notat parola”: după aceea nu se mai arată.")
		return _("Dacă ai uitat parola, alege „Fă o parolă nouă”.")
	# blocata: in imagine parola e „*” pana cand o face prima pornire
	if not s["program"]:
		return _("Lipsește programul care face parola (hds-ssh-parola). Se intră numai cu o cheie.")
	if not s["parola_facuta"]:
		if s.get("parola_eroare"):
			return _("Parola nu s-a putut face. Alege „Fă o parolă”. Până atunci se intră numai cu o cheie.")
		return _("Receptorul face parola, durează câteva secunde. Până atunci se intră numai cu o cheie.")
	return _("Contul root nu are parolă: se intră numai cu o cheie. Dacă vrei și parolă, alege „Fă o parolă”.")


def textParolaScurt(s):
	"""Randul mare de sub eticheta parolei cand parola nu se arata: starea in doua-trei cuvinte, citita de la 3 m."""
	fel = s["fel_parola"]
	if fel == "pusa":
		return _("Pusă, nu se mai arată")
	if fel == "goala":
		return _("Fără parolă")
	if fel == "lipsa":
		return _("Necunoscută")
	if s["program"] and not s["parola_facuta"]:
		if s.get("parola_eroare"):
			return _("Nu s-a putut face")
		return _("Se face...")
	return _("Numai cu cheie")


def textAlarme(s):
	"""Starile periculoase, de la cea mai grava: root fara parola care se primeste, „Fără parolă în rețeaua locală”
	pornita, dropbear cu -B. Ecranul arata prima, pagina web pe toate."""
	alarme = []
	if _goalaDeschisa(s):
		alarme.append(_("Atenție: root nu are parolă și oricine din rețea intră pe receptor."))
	if s.get("fara_parola"):
		alarme.append(_("Atenție: „Fără parolă în rețeaua locală” e pornit. Oricine din rețeaua ta de acasă intră pe receptor."))
	if s.get("fara_dovada") and not _goalaDeschisa(s):
		alarme.append(_("Atenție: serverul SSH e pornit cu -B și primește conturi fără parolă."))
	return alarme


def textChei(s):
	"""Randul cu numarul cheilor, acelasi pe televizor si in web."""
	n = len(s["chei"])
	if n:
		return _("Chei SSH pe receptor: %d. Calculatoarele cu aceste chei intră fără parolă.") % n
	return _("Chei SSH pe receptor: niciuna.")


def textCum(adresa):
	"""Randul cu comanda de conectare."""
	if not adresa:
		return _("Adresa receptorului în rețea nu e cunoscută.")
	return _("Te conectezi de pe calculator cu: ssh root@%s") % adresa


def textFaraParola(pornit):
	if pornit:
		return _("Fără parolă în rețeaua locală: pornit. Oricine din rețeaua ta de acasă intră pe receptor fără parolă.")
	return _("Fără parolă în rețeaua locală: oprit.")


def _comentariuScurt(c):
	"""Comentariul cheii de cel mult MAX_COMENTARIU_RAND semne; unul mai lung pastreaza inceputul si sfarsitul (acolo
	sunt de obicei numele calculatorului si ce deosebeste doua chei), cu „…” intre ele."""
	comentariu = c.get("comentariu") or ""
	if len(comentariu) > MAX_COMENTARIU_RAND:
		sfarsit = MAX_COMENTARIU_RAND // 2
		comentariu = comentariu[:MAX_COMENTARIU_RAND - 1 - sfarsit] + "…" + comentariu[-sfarsit:]
	return comentariu


def _amprentaScurta(c):
	"""Inceputul amprentei: „SHA256:” si 8 semne."""
	return c["amprenta"][:15] + "…"


def numeCheie(c):
	"""Cheia in cateva cuvinte: tipul (cu bitii la RSA) si comentariul scurtat, ori inceputul amprentei."""
	nume = "%s %d" % (c["nume_tip"], c["biti"]) if c["nume_tip"] == "RSA" else c["nume_tip"]
	comentariu = _comentariuScurt(c)
	if comentariu:
		return "%s „%s”" % (nume, comentariu)
	return "%s %s" % (nume, _amprentaScurta(c))


def textCheie(c):
	"""O cheie pe un rand: tipul, bitii, comentariul scurtat si inceputul amprentei."""
	nume = "%s %d" % (c["nume_tip"], c["biti"]) if c["nume_tip"] == "RSA" else c["nume_tip"]
	parti = [nume]
	comentariu = _comentariuScurt(c)
	if comentariu:
		parti.append("„%s”" % comentariu)
	parti.append(_amprentaScurta(c))
	return " ".join(parti)


def adresaLocala():
	"""Adresa IPv4 a receptorului in retea (a interfetei cu ruta implicita), fara sa trimita nimic, sau „”."""
	import socket
	s = None
	try:
		s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		s.connect(("192.0.2.1", 9))
		return s.getsockname()[0]
	except (OSError, socket.error):
		return ""
	finally:
		if s is not None:
			s.close()


def paginiBrute(cu_text=True):
	"""(titlu, cale, text) pentru „Text brut”: setarile lui dropbear si ale PAM, regula optiunii, cheile si jurnalul.
	Niciodata /etc/shadow si nici fisierul parolei. Fara `cu_text` numai titlurile si caile (lista din pagina web)."""
	pagini = []
	for titlu, cale in (
			(_("Pornirea serverului SSH"), CALE_DROPBEAR),
			(_("Verificarea parolei (PAM)"), CALE_PAM),
			(_("Regula „Fără parolă în rețeaua locală”"), CALE_REGULA),
			(_("Cheile SSH"), CALE_CHEI),
			(_("Jurnalul parolei"), CALE_JURNAL)):
		if not cu_text:
			pagini.append((titlu, cale, ""))
			continue
		text = _citeste(cale)
		if text is None:
			text = _("(fișierul nu există)")
		elif cale == CALE_JURNAL:
			text = "\n".join(text.splitlines()[-40:])
		pagini.append((titlu, cale, text))
	return pagini
