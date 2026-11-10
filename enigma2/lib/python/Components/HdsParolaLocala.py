# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsParolaLocala.py: parola din reteaua de acasa, una singura si numai daca o vrea omul.
#
# In reteaua de acasa nicio parola si niciun cod intre calculatorul sau
# telefonul omului si receptor. Numai daca omul vrea, isi pune O SINGURA parola (orice text, si "123", fara reguli de
# lungime, fara a doua scriere) si bifeaza unde se aplica. Din fabrica nu e pusa. Din afara retelei de acasa ramane
# totul ca inainte (acolo nu se slabeste nimic).
#
# Forma (a doua parere): fara un rand separat Pornita/Oprita. "Parola: nepusă" inseamna ca in casa nu se
# cere nicio parola; omul scrie una o singura data si ea se aplica peste tot (bifa Toate); apoi poate scoate bife.
# "Șterge parola" o opreste, fara intrebare.
#
# Unde se aplica (SERVICII):
#   web        interfata web a receptorului, aplicatiile de telefon (rutele /web, /api ale lor) si fisierele din web
#   ftp        serverul FTP (vsftpd): /etc/security/hds-ftp-retea-locala.conf, citit de /etc/pam.d/vsftpd
#   ssh        SSH, SFTP si Telnet: /etc/security/hds-ssh-retea-locala.conf, citit de /etc/pam.d/dropbear si de
#              /usr/sbin/hds-telnet-poarta
#   module     interfetele web ale modulelor de acces (sectiunea [webif] din configurarea lor: httpuser, httppwd)
#   pluginuri  alte interfete web ale pluginurilor instalate care au setarea lor de parola (config.<plugin>.auth)
# Fara bifa (sau fara parola pusa), serviciul ramane fara parola in reteaua de acasa: unde un program cere neaparat
# utilizator si parola, merge root cu orice parola (si goala, 1234, admin, root, pass): PAM lasa sa treaca orice
# parola de la adresele din casa (pam_permit dupa regula "-"), iar interfata web nu verifica nimic.
#
# Parola insasi e parola lui root: o pune /usr/sbin/hds-ssh-parola (comanda pune, textul pe stdin), deci e aceeasi
# pentru SSH, FTP, Telnet, web si module. Pe disc stau hash-ul in /etc/shadow si textul in /etc/hdsatelit-ssh/parola
# (0600), din care se scrie parola modulelor de acces si cu care se verifica in web. Textul nu se mai arata nicaieri:
# dupa salvare ecranul si pagina spun numai "pusă" / "nepusă".
#
# Alegerea omului: CALE_ALEGERE (JSON, 0600): {"pusa": bool, "unde": [...]}. "pusa" spune ca parola din /etc/shadow a
# fost scrisa de om (in ecranul acesta sau, inainte de 0.7.3, aleasa cand a oprit "Fără parolă în rețeaua locală");
# parola facuta la intamplare la prima pornire nu se socoteste: omul n-o stie.
#
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC schimba RADACINA.

import json
import os
import time

RADACINA = ""

CALE_ALEGERE = "/etc/hdsatelit-ssh/parola-locala.json"
CALE_PAROLA = "/etc/hdsatelit-ssh/parola"
CALE_REGULA_SSH = "/etc/security/hds-ssh-retea-locala.conf"
CALE_REGULA_FTP = "/etc/security/hds-ftp-retea-locala.conf"

WEB = "web"
FTP = "ftp"
SSH = "ssh"
MODULE = "module"
PLUGINURI = "pluginuri"
SERVICII = (WEB, FTP, SSH, MODULE, PLUGINURI)

# textul unei parole se primeste oricum, numai fara rand nou (parola sta pe un rand in fisiere si in chpasswd)
MAX_PAROLA = 256


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, NameError):
		return text


def N_(text):
	return text


def _cale(cale):
	return RADACINA + cale if RADACINA else cale


# ---------------------------------------------------------------- adresele din reteaua de acasa


def _ipv4(text):
	parti = text.split(".")
	if len(parti) != 4:
		return None
	octeti = []
	for p in parti:
		if not p or len(p) > 3 or any(c not in "0123456789" for c in p):
			return None
		v = int(p)
		if v > 255:
			return None
		octeti.append(v)
	return octeti


def esteAdresaLocala(adresa):
	"""True pentru o adresa din reteaua de acasa: 127/8, 10/8, 172.16/12, 192.168/16, 169.254/16 (si scrise ca IPv6,
	::ffff:a.b.c.d), ::1, fe80::/10, fc00::/7 (deci si fd00::/8). Nu 100.64/10 (NAT-ul operatorului, adrese impartite
	intre abonati) si nicio adresa publica. Fara modulul ipaddress (pachet separat, nu e in imagine)."""
	if not adresa:
		return False
	a = str(adresa).strip().lower()
	if a.startswith("[") and a.endswith("]"):
		a = a[1:-1]
	a = a.split("%", 1)[0]  # zona IPv6 (fe80::1%eth0)
	if a.startswith("::ffff:"):
		a = a[len("::ffff:"):]
	o = _ipv4(a)
	if o is not None:
		return (o[0] in (10, 127) or (o[0] == 172 and 16 <= o[1] <= 31) or (o[0] == 192 and o[1] == 168)
			or (o[0] == 169 and o[1] == 254))
	if ":" not in a or any(c not in "0123456789abcdef:" for c in a):
		return False
	if a == "::1":
		return True
	primul = a.split(":", 1)[0]
	if not primul or len(primul) > 4:
		return False
	v = int(primul, 16)
	return (v & 0xffc0) == 0xfe80 or (v & 0xfe00) == 0xfc00


# ---------------------------------------------------------------- alegerea omului


def _citeste(cale, maxim=65536):
	try:
		with open(_cale(cale), "rb") as f:
			return f.read(maxim).decode("utf-8", "replace")
	except (IOError, OSError):
		return None


def _scrieAtomic(cale, text, mod):
	tinta = _cale(cale)
	dosar = os.path.dirname(tinta)
	if dosar and not os.path.isdir(dosar):
		os.makedirs(dosar, 0o700)
	nou = tinta + ".nou"
	fd = os.open(nou, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mod)
	with os.fdopen(fd, "w", encoding="utf-8") as f:
		f.write(text)
		f.flush()
		try:
			os.fsync(f.fileno())
		except OSError:
			pass
	try:
		os.chmod(nou, mod)
	except OSError:
		pass
	os.replace(nou, tinta)


def _regulaLibera(cale):
	"""True cand fisierul de reguli pam_access are regula "-" (intrare fara parola din casa); None cand lipseste."""
	text = _citeste(cale)
	if text is None:
		return None
	return any(l.startswith("-") for l in text.splitlines())


def _dinFabrica():
	"""Alegerea de dinainte de fisier. Pe un receptor actualizat de la o versiune veche: cine oprise "Fără parolă în
	rețeaua locală" (regula fara "-") isi alesese parola si o vedea pe ecran, deci o stie: parola ramane ceruta pentru
	SSH si FTP, ca inainte. Altfel (din fabrica): nepusa, cu bifa Toate pregatita pentru cand o pune omul."""
	if _regulaLibera(CALE_REGULA_SSH) is False:
		return {"pusa": True, "unde": [SSH, FTP]}
	return {"pusa": False, "unde": list(SERVICII)}


# Alegerea se citeste de pe disc o singura data (si din nou numai cand se schimba RADACINA, in probe). Interfata web o
# intreaba la fiecare cerere, pe firul enigma2, unde discul nu se atinge pentru ea (nici macar un stat). O scrie numai
# acest proces (_salveaza: televizorul si interfata web sunt amandoua in enigma2), iar copia setarilor o pune la loc
# inainte de pornirea interfetei. Cine scrie fisierul din afara (probele, uneltele) cheama uitaAlegerea().
_ALEGERE = {"semn": None, "a": None}
# daca parola din /etc/shadow e inca a omului (parolaPusa): tinut minte cel mult un minut, ca o cerere web sa nu
# citeasca /etc/shadow; o parola schimbata pe alta cale (passwd) se vede dupa cel mult un minut
_PUSA = {"semn": None, "cand": 0.0, "pusa": None}
PUSA_TINUTA = 60.0


def alegere():
	"""{"pusa": bool, "unde": [servicii]}, din memorie dupa prima citire (vezi _ALEGERE)."""
	if _ALEGERE["a"] is None or _ALEGERE["semn"] != RADACINA:
		_ALEGERE["semn"], _ALEGERE["a"] = RADACINA, _alegereDePeDisc()
	a = _ALEGERE["a"]
	return {"pusa": a["pusa"], "unde": list(a["unde"])}


def uitaAlegerea():
	"""Alegerea si starea parolei se citesc din nou de pe disc la urmatoarea intrebare (dupa o scriere din afara)."""
	_ALEGERE["a"] = None
	_PUSA["pusa"] = None


def _alegereDePeDisc():
	text = _citeste(CALE_ALEGERE)
	if text is None:
		return _dinFabrica()
	try:
		d = json.loads(text)
	except ValueError:
		return _dinFabrica()
	if not isinstance(d, dict):
		return _dinFabrica()
	unde = [s for s in SERVICII if s in (d.get("unde") or [])]
	return {"pusa": bool(d.get("pusa")), "unde": unde}


def _salveaza(a):
	nou = {"pusa": bool(a["pusa"]), "unde": [s for s in SERVICII if s in a["unde"]]}
	uitaAlegerea()
	_scrieAtomic(CALE_ALEGERE, json.dumps(nou, sort_keys=True) + "\n", 0o600)
	_ALEGERE["semn"], _ALEGERE["a"] = RADACINA, nou


def parolaPusa(a=None):
	"""True cand omul si-a pus parola si ea e inca parola lui root (nu schimbata pe alta cale, de pilda cu passwd)."""
	a = alegere() if a is None else a
	if not a["pusa"]:
		return False
	acum = time.monotonic()
	if _PUSA["pusa"] is not None and _PUSA["semn"] == RADACINA and 0 <= acum - _PUSA["cand"] < PUSA_TINUTA:
		return _PUSA["pusa"]
	try:
		from Components import HdsAccesSsh as A
	except ImportError:
		return True
	pusa = A.felParola() == "pusa" and not A.parolaAlta()
	_PUSA["semn"], _PUSA["cand"], _PUSA["pusa"] = RADACINA, acum, pusa
	return pusa


def ceruta(serviciu):
	"""True cand serviciul cere parola omului in reteaua de acasa (parola pusa si bifata acolo)."""
	a = alegere()
	return serviciu in a["unde"] and parolaPusa(a)


def verifica(parola):
	"""True cand `parola` e parola omului. Se compara cu textul tinut pe receptor (in timp constant); cand textul
	lipseste, cu hash-ul lui root din /etc/shadow (crypt). Fara parola pusa: False (nimic de verificat)."""
	if not isinstance(parola, str) or "\n" in parola or "\x00" in parola or len(parola) > MAX_PAROLA:
		return False
	if not parolaPusa():
		return False
	import hmac
	text = _citeste(CALE_PAROLA, MAX_PAROLA + 8)
	if text is not None:
		return hmac.compare_digest(text.rstrip("\r\n").encode("utf-8"), parola.encode("utf-8"))
	try:
		import crypt
		for linie in (_citeste("/etc/shadow") or "").splitlines():
			campuri = linie.split(":")
			if campuri[0] == "root" and len(campuri) > 1 and campuri[1][:1] not in ("", "!", "*"):
				facut = crypt.crypt(parola, campuri[1])
				return bool(facut) and hmac.compare_digest(facut, campuri[1])
	except Exception:
		return False
	return False


def motivParola(text):
	"""De ce nu se poate pune textul ca parola, sau "". Orice text merge (si "123"); numai gol si randul nou nu, fiindca
	parola sta pe un singur rand."""
	if not text:
		return _("Scrie parola.")
	if "\n" in text or "\r" in text or "\x00" in text:
		return _("Parola nu poate avea rând nou.")
	# limita programului de hash (openssl passwd -6 ia cel mult 256 de octeti; o litera cu diacritice are 2)
	if len(text.encode("utf-8")) > MAX_PAROLA:
		return _("Parola are prea multe semne: cel mult %d.") % MAX_PAROLA
	return ""


# ---------------------------------------------------------------- aplicarea in fisierele serviciilor


def textRegula(liber, nume):
	"""Regulile pam_access ale unui serviciu: "-" inseamna aici intrare fara parola din casa (vezi /etc/pam.d/*),
	"+ : ALL : ALL" verificarea parolei pentru toti ceilalti."""
	from Components.HdsAccesSsh import RETELE_LOCALE
	if liber:
		return ("# %s: fara parola in reteaua de acasa (Setari > Retea > Parola receptorului).\n"
			"# Regula - lasa root sa intre fara parola de la adresele din reteaua de acasa; din afara casei se cere.\n"
			"- : root : %s\n+ : ALL : ALL\n" % (nume, " ".join(RETELE_LOCALE)))
	return ("# %s: cu parola omului si in reteaua de acasa (Setari > Retea > Parola receptorului).\n"
		"+ : ALL : ALL\n" % nume)


def aplicaReguli(a=None):
	"""Scrie regulile SSH (si Telnet) si FTP dupa alegere. Intoarce True daca amandoua au iesit cum trebuie."""
	a = alegere() if a is None else a
	pusa = parolaPusa(a)
	bine = True
	for serviciu, cale, nume in ((SSH, CALE_REGULA_SSH, "SSH, SFTP si Telnet"), (FTP, CALE_REGULA_FTP, "FTP")):
		liber = not (pusa and serviciu in a["unde"])
		try:
			_scrieAtomic(cale, textRegula(liber, nume), 0o644)
		except (IOError, OSError):
			bine = False
			continue
		if _regulaLibera(cale) is not liber:
			bine = False
	return bine


def aplicaModule(a=None):
	"""Interfetele web ale modulelor de acces: cu bifa, httpuser = root si httppwd = parola omului in [webif]; fara ea,
	randurile scrise de noi se scot (cele puse de om cu mana raman). Se aplica la urmatoarea pornire a modulului."""
	a = alegere() if a is None else a
	parola = None
	if MODULE in a["unde"] and parolaPusa(a):
		parola = (_citeste(CALE_PAROLA, MAX_PAROLA + 8) or "").rstrip("\r\n") or None
	try:
		from Components import HdsModuleAcces as M
		return M.puneParolaWeb(parola)
	except Exception as eroare:
		print("[HdsParolaLocala] interfetele modulelor de acces: %s" % eroare)
		return False


CALE_PLUGINURI = "/etc/hdsatelit-ssh/parola-locala-pluginuri.json"


def aplicaPluginuri(a=None):
	"""Alte interfete web ale pluginurilor care au setarea lor de parola (config.<Plugin>.auth, cu parola lui root). Cu
	bifa se porneste; fara ea se opreste NUMAI unde am pornit-o noi (lista din CALE_PLUGINURI): o parola pusa de om
	direct in plugin ramane, si cu ea paza lui pentru accesul din afara casei. Pe PC (fara enigma2) nu face nimic."""
	a = alegere() if a is None else a
	cere = PLUGINURI in a["unde"] and parolaPusa(a)
	try:
		from Components.config import config, configfile
	except ImportError:
		return False
	try:
		puse = json.loads(_citeste(CALE_PLUGINURI) or "[]")
		puse = [x for x in puse if isinstance(x, str)] if isinstance(puse, list) else []
	except ValueError:
		puse = []
	noi = list(puse)
	schimbat = False
	for nume in list(getattr(config, "content", None) and config.content.items or []):
		if not nume[:1].isupper():
			continue
		sectiune = getattr(config, nume, None)
		auth = getattr(getattr(sectiune, "content", None), "items", {}).get("auth")
		if auth is None or not isinstance(getattr(auth, "value", None), bool):
			continue
		if cere and not auth.value:
			auth.value = True
			auth.save()
			schimbat = True
			noi.append(nume)
		elif not cere and auth.value and nume in puse:
			auth.value = False
			auth.save()
			schimbat = True
			noi.remove(nume)
	if schimbat:
		configfile.save()
	if noi != puse:
		try:
			_scrieAtomic(CALE_PLUGINURI, json.dumps(sorted(set(noi))) + "\n", 0o600)
		except (IOError, OSError):
			return False
	return True


def aplicaTot(a=None):
	a = alegere() if a is None else a
	bine = aplicaReguli(a)
	aplicaModule(a)
	aplicaPluginuri(a)
	return bine


def puneParola(parola, unde=None):
	"""Omul scrie parola (prima data sau alta): (reusit, mesaj). Prima data se aplica peste tot (bifa Toate), apoi
	raman bifele alese. `unde`: bifele noi (None: cele de pana acum)."""
	from Components import HdsAccesSsh as A
	motiv = motivParola(parola)
	if motiv:
		return False, motiv
	a = alegere()
	prima = not parolaPusa(a)
	cod, eroare = A._programParola("pune", parola)
	if cod == 2:
		return False, _("Programul parolei de pe receptor e vechi și nu primește o parolă aleasă. Actualizează "
			"receptorul, apoi încearcă din nou.")
	if cod != 0:
		return False, _("Parola nu s-a putut pune.") + (" (%s)" % eroare if eroare else "")
	a["pusa"] = True
	if unde is not None:
		a["unde"] = [s for s in SERVICII if s in unde]
	elif prima or not a["unde"]:
		a["unde"] = list(SERVICII)
	try:
		_salveaza(a)
	except (IOError, OSError):
		return False, _("Setarea nu s-a putut salva.")
	if not aplicaTot(a):
		return False, _("Parola e pusă, dar regulile pentru SSH și FTP nu s-au putut scrie.")
	return True, _("Parola e pusă. În rețeaua de acasă se cere numai unde e bifată.")


def seteazaUnde(unde):
	"""Bifele: unde se cere parola pusa. Fara nicio bifa parola ramane pusa, dar nu se cere nicaieri."""
	a = alegere()
	a["unde"] = [s for s in SERVICII if s in (unde or [])]
	try:
		_salveaza(a)
	except (IOError, OSError):
		return False, _("Setarea nu s-a putut salva.")
	if not aplicaTot(a):
		return False, _("Setarea e salvată, dar regulile pentru SSH și FTP nu s-au putut scrie.")
	return True, _("Salvat.")


def stergeParola():
	"""Inapoi la "nepusă": in casa nu se mai cere nicio parola. Textul tinut pe receptor se sterge (hds-ssh-parola
	ascunde); hash-ul din /etc/shadow ramane (din afara casei parola nu se primeste oricum, iar in casa PAM lasa orice).
	Bifele raman pregatite pentru data viitoare."""
	from Components import HdsAccesSsh as A
	a = alegere()
	a["pusa"] = False
	try:
		_salveaza(a)
	except (IOError, OSError):
		return False, _("Setarea nu s-a putut salva.")
	bine = aplicaTot(a)
	A._programParola("ascunde")
	if not bine:
		return False, _("Parola e ștearsă, dar regulile pentru SSH și FTP nu s-au putut scrie.")
	return True, _("Parola e ștearsă. În rețeaua de acasă nu se mai cere nicio parolă.")


# ---------------------------------------------------------------- textele (aceleasi pe televizor si in web)

TXT_SERVICII = (
	(WEB, N_("Interfața web și aplicațiile de telefon")),
	(FTP, N_("FTP")),
	(SSH, N_("Telnet și SSH")),
	(MODULE, N_("Interfețele web ale modulelor de acces")),
	(PLUGINURI, N_("Alte interfețe web (pluginuri)")),
)


# numele scurte ale locurilor, pentru randul de sub parola (doua randuri si la litere de 130 %)
TXT_SERVICII_SCURT = (
	(WEB, N_("interfața web")),
	(FTP, N_("FTP")),
	(SSH, N_("Telnet și SSH")),
	(MODULE, N_("modulele de acces")),
	(PLUGINURI, N_("pluginuri")),
)


def textStare(a=None):
	"""Un rand scurt (cel mult doua randuri pe ecran): unde se cere parola acum."""
	a = alegere() if a is None else a
	if not parolaPusa(a) or not a["unde"]:
		return _("În casă nu se cere nicio parolă. Unde un program cere neapărat una, merge root cu orice parolă.")
	if all(s in a["unde"] for s in SERVICII):
		return _("Parola ta se cere în casă peste tot.")
	return _("Parola ta se cere în casă la: %s.") % ", ".join(
		_(t) for s, t in TXT_SERVICII_SCURT if s in a["unde"])


def textParola(a=None):
	"""Randul parolei: dupa salvare valoarea nu se mai arata."""
	return _("pusă") if parolaPusa(a) else _("nepusă")
