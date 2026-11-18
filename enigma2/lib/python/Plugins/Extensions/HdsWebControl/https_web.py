# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Interfata web si pe HTTPS, portul 443, cu certificatul facut de receptor.

DE CE: panoul calculatorului din /fisiere (navigatorul cu doua panouri) foloseste alegerea dosarului din browser
(showDirectoryPicker), care merge numai intr-o pagina sigura (https sau localhost). Pe http://hdsatelit.local nu
exista. Proba din 14.11.2026 (Chrome 157, adresa din casa): pe https cu un certificat facut de noi, dupa
"Avansate" si "Acceseaza", pagina e sigura si alegerea dosarului se deschide. Deci nu trebuie un certificat
de la o firma, nici internet, nici server: receptorul isi face singur certificatul.

CERTIFICATUL: EC P-256, semnat de el insusi, cu numele .local al receptorului (hdsatelit.local, hdsatelit2.local
la al doilea receptor din casa), hdsatelit.local mereu, numele receptorului in retea (de pilda sf8008 si
sf8008.local) si, ca rezerva, adresele IPv4 din momentul facerii. Cheia privata sta in DOSAR (0700, cheia 0600)
si nu se arata niciodata in Fisiere (fisiere_core refuza dosarul).
Se face din nou NUMAI cand lipseste din el un nume dorit (alt nume .local, alt nume al receptorului) sau cand
expira (hotararea coordonatorului, 14.11.2026): o adresa IP noua de la router NU il reface, altfel avertismentul
Chrome ar reveni la fiecare IP nou. Omul foloseste oricum hdsatelit.local. Un nume care lipseste o clipa (numele
.local inca neconfirmat la pornire) nu il reface: conteaza numai numele noi.

PORTUL: 443. Daca e ocupat (alt program al omului), HTTPS nu porneste, iar pagina Fisiere spune motivul;
nu trece pe alt port pe tacute. Aceleasi resurse si aceleasi porti ca pe HTTP (adresa din casa, browserul
asociat, CSRF, accesul din afara casei), fiindca fabrica serverului e aceeasi (plugin._construiesteServer).

FIRUL: certificatul se face pe firul enigma2 (o cheie EC dureaza milisecunde); verificarea schimbarilor o data
pe minut citeste numai fisierul mic de stare al numelui si adresele din tabela de rute.
"""

import datetime
import ipaddress
import json
import os
import socket

DOSAR = "/etc/enigma2/hds-https"
CHEIE = DOSAR + "/cheie.pem"
CERT = DOSAR + "/cert.pem"
DESCRIERE = DOSAR + "/nume.json"
PORT_HTTPS = 443
ZILE_VALABIL = 820
ZILE_REFACERE = 30
VERIFICARE_S = 60

_stare = {"pornit": False, "motiv": "", "nume": [], "port": None}
_fabrica = None
_ceas = None


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, NameError):
		return text


def _jurnal(text):
	print("[HdsWebControl] https: %s" % text)


def numeLocal():
	"""Numele .local publicat de receptor (hdsatelit.local, hdsatelit2.local) sau "" daca nu e publicat."""
	try:
		from Components.HdsComutareRetea import nume_local_confirmat
		return nume_local_confirmat() or ""
	except Exception:
		return ""


def adreseIpv4(fisier_rute="/proc/net/route", fisier_fib="/proc/net/fib_trie"):
	"""Adresele IPv4 ale receptorului (fara 127.x), citite din tabela kernelului; fara comenzi externe."""
	gasite = []
	try:
		with open(fisier_fib, encoding="ascii", errors="replace") as f:
			linii = f.read(262144).splitlines()
		for i, linie in enumerate(linii):
			if "/32 host LOCAL" in linie and i > 0:
				adresa = linii[i - 1].strip().split()[-1]
				try:
					ip = ipaddress.IPv4Address(adresa)
				except ValueError:
					continue
				if not ip.is_loopback and adresa not in gasite:
					gasite.append(adresa)
	except (IOError, OSError):
		pass
	if not gasite:
		try:
			s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
			try:
				s.connect(("192.0.2.1", 9))
				adresa = s.getsockname()[0]
			finally:
				s.close()
			if adresa and not adresa.startswith("127."):
				gasite.append(adresa)
		except OSError:
			pass
	return sorted(gasite)


def _etichetaBuna(text):
	"""O eticheta DNS simpla (litere mici, cifre, liniuta), cum e numele receptorului in retea."""
	return bool(text) and len(text) <= 63 and all(c.isascii() and (c.isalnum() or c == "-") for c in text) 		and not text.startswith("-") and not text.endswith("-")


def numeReceptor(gazda=None):
	"""Numele receptorului in retea si varianta .local (["sf8008", "sf8008.local"]); [] daca nu e unul bun."""
	try:
		gazda = socket.gethostname() if gazda is None else gazda
	except OSError:
		return []
	gazda = (gazda or "").strip().lower().split(".", 1)[0]
	if not _etichetaBuna(gazda) or gazda == "localhost":
		return []
	return [gazda, gazda + ".local"]


def numeDorite(nume_local=None, adrese=None, gazda=None):
	"""(nume DNS, adrese IP) pentru certificat, in ordine fixa (comparatia cu cel de pe disc)."""
	nume = {"hdsatelit.local"}
	local = numeLocal() if nume_local is None else nume_local
	if local:
		nume.add(local.lower())
	nume.update(numeReceptor(gazda))
	return sorted(nume), sorted(adreseIpv4() if adrese is None else adrese)


def _descriereDePeDisc(dosar=DOSAR):
	try:
		with open(os.path.join(dosar, "nume.json"), encoding="utf-8") as f:
			return json.loads(f.read(8192))
	except (IOError, OSError, ValueError):
		return None


def trebuieRefacut(nume, adrese, dosar=DOSAR, acum=None):
	"""True cand certificatul lipseste, ii lipseste un nume dorit ori expira in mai putin de ZILE_REFACERE zile.
	`adrese` nu conteaza (ramane parametru pentru apelanti): un IP nou nu reface certificatul."""
	if not (os.path.exists(os.path.join(dosar, "cheie.pem")) and os.path.exists(os.path.join(dosar, "cert.pem"))):
		return True
	d = _descriereDePeDisc(dosar)
	if not isinstance(d, dict) or not isinstance(d.get("nume"), list) or not set(nume) <= set(d["nume"]):
		return True
	try:
		expira = float(d.get("expira", 0))
	except (TypeError, ValueError):
		return True
	acum = datetime.datetime.now(datetime.timezone.utc).timestamp() if acum is None else acum
	return expira - acum < ZILE_REFACERE * 86400


def _scrieAtomic(cale, date, mod):
	nou = cale + ".nou"
	fd = os.open(nou, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mod)
	try:
		os.write(fd, date)
		os.fsync(fd)
	finally:
		os.close(fd)
	os.chmod(nou, mod)
	os.replace(nou, cale)


def facCertificat(nume, adrese, dosar=DOSAR):
	"""Cheia si certificatul noi, scrise atomic. Intoarce (cert_pem, cheie_pem)."""
	from cryptography import x509
	from cryptography.hazmat.primitives import hashes, serialization
	from cryptography.hazmat.primitives.asymmetric import ec
	from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
	if not os.path.isdir(dosar):
		os.makedirs(dosar, 0o700)
	os.chmod(dosar, 0o700)
	cheie = ec.generate_private_key(ec.SECP256R1())
	subiect = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, nume[-1] if nume else "hdsatelit.local"),
		x509.NameAttribute(NameOID.ORGANIZATION_NAME, "HD Satelit")])
	acum = datetime.datetime.now(datetime.timezone.utc)
	alternative = [x509.DNSName(n) for n in nume] + [x509.IPAddress(ipaddress.ip_address(a)) for a in adrese]
	cert = (x509.CertificateBuilder().subject_name(subiect).issuer_name(subiect).public_key(cheie.public_key())
		.serial_number(x509.random_serial_number())
		.not_valid_before(acum - datetime.timedelta(days=1))
		.not_valid_after(acum + datetime.timedelta(days=ZILE_VALABIL))
		.add_extension(x509.SubjectAlternativeName(alternative), critical=False)
		.add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
		.add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
		.sign(cheie, hashes.SHA256()))
	cert_pem = cert.public_bytes(serialization.Encoding.PEM)
	cheie_pem = cheie.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
		serialization.NoEncryption())
	_scrieAtomic(os.path.join(dosar, "cheie.pem"), cheie_pem, 0o600)
	_scrieAtomic(os.path.join(dosar, "cert.pem"), cert_pem, 0o644)
	expira = (acum + datetime.timedelta(days=ZILE_VALABIL)).timestamp()
	_scrieAtomic(os.path.join(dosar, "nume.json"),
		json.dumps({"nume": list(nume), "adrese": list(adrese), "expira": expira}).encode("utf-8"), 0o644)
	return cert_pem, cheie_pem


def asiguraCertificat(dosar=DOSAR):
	"""Certificatul de acum (facut din nou daca trebuie). Intoarce (cert_pem, cheie_pem, refacut)."""
	nume, adrese = numeDorite()
	if trebuieRefacut(nume, adrese, dosar):
		cert_pem, cheie_pem = facCertificat(nume, adrese, dosar)
		_jurnal("certificat nou pentru %s" % ", ".join(nume + adrese))
		return cert_pem, cheie_pem, True
	with open(os.path.join(dosar, "cert.pem"), "rb") as f:
		cert_pem = f.read(65536)
	with open(os.path.join(dosar, "cheie.pem"), "rb") as f:
		cheie_pem = f.read(65536)
	return cert_pem, cheie_pem, False


def optiuniTls(cert_pem, cheie_pem):
	"""Optiunile TLS ale portului 443: certificatul receptorului si negocierea ALPN cu un singur protocol, http/1.1.
	De ce: toate browserele trimit ALPN (h2 si http/1.1). Fara o lista a serverului, Twisted 26.4 (cel din imagine)
	raspundea cu alerta TLS internal_error, deci https://hdsatelit.local nu se deschidea in niciun browser
	(ERR_SSL_PROTOCOL_ERROR, fara pagina de acceptare a certificatului), iar un browser care trece singur pe https
	(Brave cu upgrade-ul HTTPS strict) nu putea ramane pe https. Lista sta in optiuni, nu in fabrica serverului: asa merge
	si cu Twisted 25.5, unde fabrica cu negociere schimba contextul TLS dupa prima conexiune, iar pyOpenSSL nou refuza.
	Numai http/1.1: canalul serverului (plugin._construiesteServer) nu vorbeste HTTP/2."""
	from twisted.internet import ssl
	certificat = ssl.PrivateCertificate.loadPEM(cert_pem + b"\n" + cheie_pem)
	return ssl.CertificateOptions(privateKey=certificat.privateKey.original, certificate=certificat.original,
		acceptableProtocols=[b"http/1.1"])


def _asculta(reactor):
	cert_pem, cheie_pem, unused = asiguraCertificat()
	port = reactor.listenSSL(PORT_HTTPS, _fabrica(), optiuniTls(cert_pem, cheie_pem))
	nume, adrese = numeDorite()
	_stare.update(pornit=True, motiv="", nume=nume + adrese, port=port)
	_jurnal("pornit pe portul %d" % PORT_HTTPS)


def porneste(reactor, fabrica):
	"""Porneste HTTPS cu `fabrica()` (aceeasi fabrica a serverului ca pe HTTP). Niciodata o exceptie in afara."""
	global _fabrica, _ceas
	_fabrica = fabrica
	try:
		_asculta(reactor)
	except Exception as eroare:
		_stare.update(pornit=False, port=None, motiv=_motiv(eroare))
		_jurnal("nu porneste: %s" % eroare)
	try:
		from twisted.internet import task
		if _ceas is None:
			_ceas = task.LoopingCall(verifica, reactor)
			_ceas.start(VERIFICARE_S, now=False)
	except Exception as eroare:
		_jurnal("verificarea numelui nu porneste: %s" % eroare)


def _motiv(eroare):
	text = str(eroare)
	if "already in use" in text or "Errno 98" in text:
		return _("Portul 443 al receptorului e folosit de alt program.")
	if isinstance(eroare, ImportError):
		return _("Receptorului îi lipsește biblioteca pentru conexiunea criptată.")
	return _("Conexiunea criptată a receptorului nu a pornit.")


def verifica(reactor):
	"""O data pe minut: daca a aparut un nume nou (sau certificatul expira), certificat nou si portul repornit."""
	try:
		nume, adrese = numeDorite()
		if not trebuieRefacut(nume, adrese):
			if not _stare["pornit"] and _fabrica is not None:
				_asculta(reactor)
			return
		port = _stare.get("port")
		_stare.update(pornit=False, port=None)
		if port is not None:
			d = port.stopListening()
			if d is not None:
				d.addBoth(lambda unused: _reasculta(reactor))
				return
		_reasculta(reactor)
	except Exception as eroare:
		_jurnal("verificarea: %s" % eroare)


def _reasculta(reactor):
	try:
		_asculta(reactor)
	except Exception as eroare:
		_stare.update(pornit=False, port=None, motiv=_motiv(eroare))
		_jurnal("nu reporneste: %s" % eroare)


def stare(gazda_cerere=""):
	"""Ce afla pagina Fisiere: daca HTTPS merge, adresa la care sa duca butonul si motivul cand nu merge.
	Adresa foloseste numele .local publicat (regula: catre oameni hdsatelit.local, nu IP-ul); fara nume publicat,
	adresa IP din antetul Host al cererii (si ea e in certificat)."""
	gazda = numeLocal()
	if not gazda:
		gazda = (gazda_cerere or "").strip()
		if gazda.startswith("["):
			gazda = ""
		gazda = gazda.split(":", 1)[0]
		if not gazda or any(c in gazda for c in "\r\n /\\@?#"):
			gazda = "hdsatelit.local"
	return {"pornit": bool(_stare["pornit"]), "adresa": "https://%s/fisiere" % gazda,
		"motiv": "" if _stare["pornit"] else (_stare["motiv"] or _("Conexiunea criptată a receptorului nu a pornit."))}
