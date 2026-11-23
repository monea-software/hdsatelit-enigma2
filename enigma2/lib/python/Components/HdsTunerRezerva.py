# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsTunerRezerva.py: tunerul de rezerva din retea (in OE-Alliance "fallback tuner", setarile
# config.usage.remote_fallback_enabled si config.usage.remote_fallback). Cand tunerele receptorului nu pot lua canalul
# cerut (sunt ocupate cu inregistrari, receptorul n-are tunerul de cablu sau de antena terestra al canalului, satelitul
# nu e legat), televizorul primeste canalul de la alt receptor Enigma2 din casa, prin serverul lui de flux (portul 8001),
# ca pe un canal de tip 1 cu adresa http (sursa eHdsFluxHttp, lib/service/hdsfluxhttp.cpp). Bara, ghidul, sigla si lista
# de canale vad canalul obisnuit.
#
# SETAREA: un singur rand, "Tuner de rezervă din rețea": Oprit / fiecare receptor gasit singur in casa / Altă adresă
# (randul adresei apare numai atunci). Pe televizor: Meniu > Tunere si scanare > Tuner de rezerva din retea (locul din
# OE-Alliance) si ultimul rand din Setari tuner (Screens/Satconfig.py); in web /setari?id=hds_tuner_rezerva
# si cartela tunerelor din /antena/tuner (scanare_web.py). config.usage.hds_tuner_rezerva tine alegerea (adresa
# receptorului, "" sau ALTA), config.usage.hds_tuner_rezerva_adresa adresa scrisa de om. La salvare se scriu si numele
# OE-Alliance (remote_fallback_enabled, remote_fallback = http://<gazda>:<port>), pe care le citeste zap-ul si pe care le
# cunosc pluginurile scrise pentru celelalte imagini; o copie de setari adusa din alta imagine OE-Alliance (numai cu
# ele) se recunoaste la pornire.
#
# GASIREA, fara cautare de porturi: o singura intrebare mDNS (224.0.0.251:5353, raspunsul direct la portul intrebarii)
#  - pentru _e2stream._tcp.local: serverul de flux pe care il anunta receptoarele OE-Alliance (streamserverul) si cele
#    HD Satelit de la 0.7.7 (ANUNTUL de mai jos); numele lor .local e numele gazdei, care nu se schimba cand routerul da
#    alta adresa IP;
#  - pentru hdsatelit.local, hdsatelit2.local ...: receptoarele HD Satelit mai vechi, care nu anunta serverul de flux.
# Fiecare receptor gasit primeste o singura conectare TCP la portul lui, fara nicio cerere (nu ia niciun tuner), ca sa
# stim daca serverul primeste cereri din retea. Receptorul insusi nu apare. Se tine minte numele .local, nu adresa IP
# (routerul poate da alta adresa dupa o repornire); la fiecare zap il afla getaddrinfo (libnss-mdns, in imagine).
# Cautarea porneste la deschiderea Setari tuner, a ecranului setarii, a paginii tunerelor si a paginii setarii (daca
# ultima e mai veche de VECHIME_S), pe un fir; ecranele citesc rezultatul din memorie, alegerile se pun pe firul enigma2.
#
# ZAP: Navigation.playServiceUltima (chemata dupa toate extensiile de zap, cand niciuna n-a luat canalul: transmisia in
# browser, Components/HdsTransmisie.py, releele DAB+ / DVB-T2 si fluxurile 8001 cerute din retea, Hds/DabT2/server8001.py
# la_zap, si-au lasat deja tunerul in extensiile lor), pusa numai cat rezerva e aleasa.
# Pentru un canal DVB (tip 1, fara cale) pe care managerul de tunere nu-l poate porni acum (isPlayable), playerul
# primeste referinta canalului cu calea http://<gazda>:<port>/<referinta canalului> (un canal de tip 1 cu adresa http),
# iar navigatia ramane pe canal (ca la Stream Relay, Components/HdsStreamRelay.py). Spre deosebire de Stream Relay,
# spatiul de nume ramane acelasi: aici nimic de pe receptor nu cere canalul adevarat (fluxul vine din alt receptor),
# deci programul din bara vine din ghidul canalului cand fluxul n-are EIT (eDVBServicePlay::getEvent cauta referinta
# fara cale). De la un canal prin rezerva la altul de pe alt transponder,
# playerul porneste dupa INTARZIERE_MS, ca receptorul din casa sa lase intai tunerul canalului vechi.
#
# ANUNTUL: cat serverul de flux al imaginii primeste cereri din retea (config.misc.hds_fluxuri_retea_acasa, pornita din
# fabrica; Hds/DabT2/server8001.py), FISIER_ANUNT anunta _e2stream._tcp pe 8001, ca streamserverul OE-Alliance, deci
# celelalte receptoare din casa il gasesc singure ca rezerva. Oprita, fisierul se scoate. avahi-daemon citeste din nou
# dosarul serviciilor la SIGHUP.
#
# GRUPURILE DE ALTERNATIVE (0.7.7): cand niciuna dintre alternative n-are tuner, nici dupa cedarile extensiilor
# grupului (Navigation.grupFaraTuner), Navigation.grupFaraTunerUltima (laGrup, pusa odata cu playServiceUltima) da
# alternativa DVB aleasa ca de enigma2 intre alternativele libere (dupa prioritatea tipurilor de tuner,
# config.usage.alternatives_priority; la egalitate prima din grup), iar zap-ul o porneste prin rezerva, ca pe orice canal.
#
# LIMITE: inregistrarile si fereastra a doua (PiP) nu folosesc rezerva (inregistrarea fluxurilor din retea nu exista
# inca); canalul trebuie sa fie in lista acestui receptor (lista si ghidul nu se iau de la receptorul din casa). Cand
# receptorul din casa e oprit sau n-are tuner liber, sursa eHdsFluxHttp reincearca singura, cu pauze tot mai mari (ca la
# orice canal de tip 1 cu adresa http), iar imaginea vine cand receptorul din casa raspunde din nou. Televizorul
# receptorului din casa are intaietate: cand el are nevoie de tunerul tinut de acest flux, serverul lui de flux il
# opreste (Hds/DabT2/server8001.py, la_zap), iar aici sursa reincearca pana se elibereaza un tuner acolo.
#
# CU REZERVA OPRITA raman: anuntul (mai jos) si cautarea (o intrebare mDNS si cate o conectare TCP fara cerere spre
# receptoarele gasite), numai la deschiderea Setari tuner, a ecranului si a paginilor de mai sus.
#
# Modulul nu importa nimic din enigma2 la incarcare: probele de pe PC il folosesc direct.

import os
import socket
import struct
import threading
import time

PORT = 8001
SERVICIU = "_e2stream._tcp.local"
NUME_HDS = ["hdsatelit.local"] + ["hdsatelit%d.local" % n for n in range(2, 7)]
MDNS = ("224.0.0.251", 5353)
TERMEN_S = 1.5              # cat se asteapta raspunsurile mDNS la o intrebare
TERMEN_CONECTARE_S = 0.8    # conectarea la portul fiecarui receptor gasit
VECHIME_S = 60.0            # o cautare mai veche se reface la deschiderea ecranelor
INTARZIERE_MS = 600         # de la un canal prin rezerva la altul, pe alt transponder
ANUNT_DUPA_MS = 30000       # anuntul se pune la atata dupa pornirea interfetei
FISIER_ANUNT = "/etc/avahi/services/hds-e2stream.service"
NUME_PROPRIU = "/var/run/hds-nume-local.nume"   # numele hdsatelitN publicat de hds-nume-local (fara .local)
PID_AVAHI = ("/run/avahi-daemon/pid", "/var/run/avahi-daemon/pid")   # /var/run nu e mereu legatura spre /run
OPRIT = ""
ALTA = "adresa"
TIP_A, TIP_PTR, TIP_SRV = 1, 12, 33


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_), fara efect: textele se traduc la folosire."""
	return text


def _t(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


def _jurnal(text):
	print("[HdsTunerRezerva] %s" % text)


T_OPRIT = N_("Oprit")
T_ALTA = N_("Altă adresă")
T_NEGASIT = N_("%s (negăsit acum)")
T_STARE_OPRIT = N_("Oprit: când tunerele acestui receptor sunt ocupate sau nu pot lua canalul, canalul nu pornește.")
T_STARE_PORNIT = N_("Pornit: când tunerele acestui receptor sunt ocupate sau nu pot lua canalul, canalul vine de la %s, prin rețea.")
T_CAUT = N_("Caut receptoarele din casă...")
T_GASITE = N_("Receptoare găsite în casă: %s.")
T_NICIUNUL = N_("Niciun alt receptor găsit în casă. Dacă știi adresa lui, alege Altă adresă și scrie-o.")
T_NU_PRIMESTE = N_("%s nu răspunde la portul fluxurilor. Dacă e un receptor HD Satelit, pe el pornește rândul Fluxuri pentru alte aparate din rețeaua de acasă (Meniu > Acces condiționat > Stream Relay).")
T_FARA_ADRESA = N_("Scrie adresa receptorului din casă (de pildă 192.168.1.20 sau numele lui .local).")
T_ADRESA_GRESITA = N_("Adresa %s nu e bună. Scrie numai adresa receptorului, de pildă 192.168.1.20 sau 192.168.1.20:8001.")
T_ULTIMA = N_("Ultima dată la %s: %s a venit de la %s.")
T_FARA_RETEA = N_("Receptorul nu e conectat la nicio rețea.")


# ------------------------------------------------------------------ adresa

def adresa(text):
	"""Adresa scrisa de om -> "http://<gazda>:<port>" sau "" daca nu e buna. Primeste 192.168.1.20, 192.168.1.20:8001,
	sf8008.local, http://192.168.1.20:8001 si http://utilizator:parola@gazda:port (streamserverul cu parola); fara cale
	dupa port (referinta canalului se pune la zap)."""
	a = (text or "").strip()
	if not a or any(c.isspace() for c in a) or len(a) > 120:
		return ""
	if "://" in a:
		schema, a = a.split("://", 1)
		if schema.lower() != "http":
			return ""
	a, _bara, cale = a.partition("/")
	if cale:
		return ""
	cont = ""
	if "@" in a:
		cont, a = a.rsplit("@", 1)
		cont += "@"
	if not a or a.startswith("["):
		return ""
	gazda, port = a, PORT
	if ":" in a:
		gazda, p = a.rsplit(":", 1)
		try:
			port = int(p)
		except ValueError:
			return ""
		if not 0 < port < 65536:
			return ""
	if not gazda or not all(c.isalnum() or c in ".-_" for c in gazda):
		return ""
	return "http://%s%s:%d" % (cont, gazda, port)


def gazda(url):
	"""Gazda din "http://[cont@]gazda:port" (fara cont), pentru texte."""
	a = (url or "").split("://", 1)[-1].split("/", 1)[0]
	a = a.rsplit("@", 1)[-1]
	return a.rsplit(":", 1)[0] if ":" in a else a


# ------------------------------------------------------------------ intrebarea mDNS

def _nume_dns(nume):
	return b"".join(struct.pack("B", len(e)) + e.encode("utf-8") for e in nume.strip(".").split(".") if e) + b"\x00"


def intrebare(intrebari, ident=0):
	"""Un mesaj mDNS cu intrebarile [(nume, tip)], fiecare cu bitul QU (raspunsul direct la portul intrebarii)."""
	corp = b"".join(_nume_dns(n) + struct.pack(">HH", t, 0x8001) for n, t in intrebari)
	return struct.pack(">HHHHHH", ident, 0, len(intrebari), 0, 0, 0) + corp


def intrebarea_intai():
	return intrebare([(SERVICIU, TIP_PTR)] + [(n, TIP_A) for n in NUME_HDS])


def inregistrari(date):
	"""Raspunsurile unui mesaj mDNS -> [(nume, tip, valoare)]: PTR -> numele instantei, SRV -> (port, tinta),
	A -> adresa IP; restul se sare. Un mesaj stricat da ce s-a putut citi pana la el."""
	from Components.HdsAparateRetea import _citeste_nume
	rez = []
	try:
		if len(date) < 12:
			return rez
		_id, steaguri, qd, an, ns, ar = struct.unpack(">HHHHHH", date[:12])
		if not steaguri & 0x8000 or steaguri & 0x000F:
			return rez
		i = 12
		for _k in range(qd):
			_n, i = _citeste_nume(date, i)
			i += 4
		for _k in range(an + ns + ar):
			nume, i = _citeste_nume(date, i)
			tip, _cls, _ttl, lung = struct.unpack(">HHIH", date[i:i + 10])
			i += 10
			corp = date[i:i + lung]
			if tip == TIP_PTR:
				rez.append((nume.lower(), tip, _citeste_nume(date, i)[0]))
			elif tip == TIP_SRV and lung >= 7:
				_prio, _greut, port = struct.unpack(">HHH", corp[:6])
				rez.append((nume.lower(), tip, (port, _citeste_nume(date, i + 6)[0].lower())))
			elif tip == TIP_A and lung == 4:
				rez.append((nume.lower(), tip, socket.inet_ntoa(corp)))
			i += lung
	except (struct.error, ValueError, IndexError, OSError):
		pass
	return rez


def receptoare(inreg, proprii=()):
	"""Din inregistrarile mDNS -> [{"nume", "gazda", "ip", "port", "url"}], cate unul pe adresa IP, fara adresele
	receptorului (proprii). Instantele _e2stream._tcp au intaietate (numele gazdei nu se schimba); numele HD Satelit
	vechi completeaza. Cele fara adresa IP raman cu ip "" (le cauta urmatoarea intrebare)."""
	instante, srv, adrese, gazde_proprii = [], {}, {}, set()
	sufix = "." + SERVICIU
	for nume, tip, val in inreg:
		if tip == TIP_PTR and nume == SERVICIU and val.lower().endswith(sufix):
			if val not in instante:
				instante.append(val)
		elif tip == TIP_SRV:
			srv[nume] = val
		elif tip == TIP_A:
			adrese.setdefault(nume, val)
			if val in proprii:
				gazde_proprii.add(nume)
	rez, vazute, gazde_vazute = [], set(), set()
	for inst in instante:
		port, tinta = srv.get(inst.lower(), (PORT, ""))
		# Un anunt invalid nu revendica gazda sau IP-ul inaintea unui anunt valid.
		if not 0 < port < 65536:
			continue
		eticheta = inst[:-len(sufix)]
		ip = adrese.get(tinta, "") if tinta else ""
		if ((ip and ip in vazute) or ip in proprii or tinta in gazde_proprii
				or (tinta and tinta in gazde_vazute)):
			continue
		if ip:
			vazute.add(ip)
		if tinta:
			gazde_vazute.add(tinta)
		g = tinta or ""
		rez.append({"nume": eticheta, "gazda": g, "ip": ip, "port": port, "url": "http://%s:%d" % (g, port) if g else ""})
	for n in NUME_HDS:
		ip = adrese.get(n)
		if not ip or ip in vazute or ip in proprii or n in gazde_proprii or n in gazde_vazute:
			continue
		vazute.add(ip)
		rez.append({"nume": "HD Satelit", "gazda": n, "ip": ip, "port": PORT, "url": "http://%s:%d" % (n, PORT)})
	return rez


def eticheta(r):
	"""Textul alegerii: numele anuntat si numele .local (o data, cand sunt la fel)."""
	nume, g = r.get("nume") or "", r.get("gazda") or ""
	scurt = g[:-6] if g.endswith(".local") else g
	if not nume or nume.lower() == scurt.lower():
		return g or r.get("ip") or ""
	return "%s (%s)" % (nume, g) if g else nume


# ------------------------------------------------------------------ cautarea

class Cautare(object):
	"""Cautarea receptoarelor din casa, pe un fir. Pentru probe: fabrica_soclu (socket.socket fals), ceas, adrese_proprii
	(functia adreselor receptorului), conecteaza (functia conectarii TCP)."""

	def __init__(self, fabrica_soclu=None, ceas=None, adrese_proprii=None, conecteaza=None):
		self.fabrica_soclu = fabrica_soclu or socket.socket
		self.ceas = ceas or time.monotonic
		self.adrese_proprii = adrese_proprii or _adrese_proprii
		self.conecteaza = conecteaza or _conecteaza
		self._zavor = threading.Lock()
		self.st = {"stare": "nimic", "receptoare": [], "cand": None, "eroare": ""}
		self.trimise = []

	def rezultat(self):
		with self._zavor:
			st = dict(self.st)
			# Expirarea foloseste acelasi ceas si prag ca reinnoirea cautarii, inclusiv in timpul ei.
			valabil = st["cand"] is not None and 0 <= self.ceas() - st["cand"] <= VECHIME_S
			st["receptoare"] = [dict(r) for r in self.st["receptoare"]] if valabil else []
		return st

	def veche(self):
		st = self.rezultat()
		if st["stare"] == "lucreaza":
			return False
		return st["cand"] is None or self.ceas() - st["cand"] > VECHIME_S

	def porneste(self, la_gata=None, pe_loc=False):
		"""Porneste cautarea (pe un fir; pe_loc=True in probe). False daca una merge deja. la_gata() se cheama la
		sfarsit (pe firul cautarii)."""
		with self._zavor:
			if self.st["stare"] == "lucreaza":
				return False
			self.st = dict(self.st, stare="lucreaza", eroare="")
		if pe_loc:
			self._lucreaza(la_gata)
		else:
			fir = threading.Thread(target=self._lucreaza, args=(la_gata,), name="hdsrezerva")
			fir.daemon = True
			fir.start()
		return True

	def _lucreaza(self, la_gata):
		try:
			gasite, eroare = self._cauta(), ""
		except Exception as e:
			_jurnal("cautarea: %r" % (e,))
			gasite, eroare = [], str(e)
		with self._zavor:
			self.st = {"stare": "gata", "receptoare": gasite, "cand": self.ceas(), "eroare": eroare}
		_jurnal("cautarea: %d receptoare (%s)" % (len(gasite), ", ".join("%s %s" % (r["gazda"], r["ip"]) for r in gasite)))
		if la_gata is not None:
			try:
				la_gata()
			except Exception as e:
				_jurnal("dupa cautare: %r" % (e,))

	def _cauta(self):
		proprii = self.adrese_proprii()
		if not proprii:
			raise RuntimeError(_t(T_FARA_RETEA))
		inreg = self._intreaba(intrebarea_intai(), proprii[0])
		gasite = receptoare(inreg, proprii)
		# a doua intrebare, numai pentru ce lipseste: tintele SRV ale instantelor si adresele tintelor
		lipsa = []
		for r in gasite:
			if not r["gazda"]:
				lipsa.append((r["nume"] + "." + SERVICIU, TIP_SRV))
			elif not r["ip"]:
				lipsa.append((r["gazda"], TIP_A))
		if lipsa:
			inreg += self._intreaba(intrebare(lipsa), proprii[0])
			gasite = receptoare(inreg, proprii)
		gasite = [r for r in gasite if r["gazda"] and r["ip"] and adresa(r["url"])]
		for r in gasite:
			r["primeste"] = bool(self.conecteaza(r["ip"], r["port"]))
		return gasite

	def _intreaba(self, mesaj, ip_propriu):
		s = self.fabrica_soclu(socket.AF_INET, socket.SOCK_DGRAM)
		rez = []
		try:
			try:
				s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
				s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(ip_propriu))
			except (OSError, socket.error, AttributeError):
				pass
			s.sendto(mesaj, MDNS)
			self.trimise.append(MDNS)
			sfarsit = self.ceas() + TERMEN_S
			while True:
				rest = sfarsit - self.ceas()
				if rest <= 0:
					break
				try:
					s.settimeout(min(0.2, rest))
					date, _dela = s.recvfrom(9000)
				except socket.timeout:
					continue
				except (OSError, socket.error):
					time.sleep(0.05)
					continue
				rez.extend(inregistrari(date))
		finally:
			s.close()
		return rez


def _adrese_proprii():
	"""Adresele IPv4 ale receptorului (fara 127.x), prima fiind cea a rutei implicite."""
	from Components import HdsAparateRetea as A
	r = A.reteaua()
	toate = A._adrese_locale()
	if r is not None and r["ip"] in toate:
		toate.remove(r["ip"])
		toate.insert(0, r["ip"])
	return toate


def _conecteaza(ip, port):
	"""O conectare TCP fara nicio cerere: serverul de flux asculta din retea? (nu ia niciun tuner)."""
	s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	s.settimeout(TERMEN_CONECTARE_S)
	try:
		s.connect((ip, int(port)))
		return True
	except (OSError, socket.error, ValueError):
		return False
	finally:
		s.close()


_CAUTARE = []


def cautare():
	if not _CAUTARE:
		_CAUTARE.append(Cautare())
	return _CAUTARE[0]


def cautaDacaE(nevoie=True):
	"""Porneste o cautare daca ultima e mai veche de VECHIME_S (deschiderea ecranelor si a paginilor). Nu asteapta."""
	c = cautare()
	if nevoie and c.veche():
		c.porneste(la_gata=_dupaCautare)


def _dupaCautare():
	"""Pe firul cautarii: alegerile se pun pe firul enigma2."""
	try:
		from twisted.internet import reactor
		reactor.callFromThread(puneAlegerile)
	except Exception:
		pass


# ------------------------------------------------------------------ setarile

def alegeri(gasite, ales="", adresa_scrisa=""):
	"""[(valoare, text)] pentru randul setarii: Oprit, receptoarele gasite, alegerea de acum daca nu e gasita acum,
	Altă adresă."""
	rez = [(OPRIT, _t(T_OPRIT))]
	for r in gasite:
		if r.get("url") and r["url"] not in [v for v, _x in rez]:
			rez.append((r["url"], eticheta(r)))
	# The last destination is retained by remote_fallback when the user selects Off.
	# Keep it selectable even if discovery cannot currently find that receiver.
	for candidat in (ales, adresa(adresa_scrisa) if adresa_scrisa else ""):
		if candidat and candidat not in (OPRIT, ALTA) and candidat not in [v for v, _x in rez]:
			rez.append((candidat, _t(T_NEGASIT) % gazda(candidat)))
	rez.append((ALTA, _t(T_ALTA)))
	return rez


def urlAles(ales, adresa_scrisa):
	"""Adresa folosita la zap pentru alegerea din rand: "" (oprit sau adresa scrisa gresit)."""
	if ales == OPRIT:
		return ""
	if ales == ALTA:
		return adresa(adresa_scrisa)
	return adresa(ales)


def _config():
	from Components.config import config
	return config


def puneAlegerile():
	"""Alegerile randului dupa ultima cautare (firul enigma2); valoarea aleasa ramane."""
	try:
		u = _config().usage
		el = u.hds_tuner_rezerva
	except Exception:
		return
	ales = el.value
	el.setChoices(alegeri(cautare().rezultat()["receptoare"], ales, u.remote_fallback.value), default=OPRIT)
	if el.value != ales:
		el.value = ales


def _schimbat(_el=None):
	"""Notificatorul celor doua randuri (la salvare si la renuntare): numele OE-Alliance si legatura la zap."""
	try:
		config = _config()
		u = config.usage
		url = urlAles(u.hds_tuner_rezerva.value, u.hds_tuner_rezerva_adresa.value)
		if bool(url) != bool(u.remote_fallback_enabled.value) or (url and url != u.remote_fallback.value):
			_jurnal("rezerva: %s" % (gazda(url) or "oprita"))
		u.remote_fallback_enabled.value = bool(url)
		if url:
			u.remote_fallback.value = url
		u.remote_fallback_enabled.save()
		u.remote_fallback.save()
		leagaZap()
	except Exception as e:
		_jurnal("setarea: %r" % (e,))


def initConfig():
	"""Din InitUsageConfig: numele OE-Alliance, randul alegerii si al adresei, legatura la zap si anuntul."""
	from Components.config import config, ConfigYesNo, ConfigText, ConfigSelection
	u = config.usage
	u.remote_fallback_enabled = ConfigYesNo(default=False)
	u.remote_fallback = ConfigText(default="", fixed_size=False)
	u.hds_tuner_rezerva_adresa = ConfigText(default="", fixed_size=False)
	u.hds_tuner_rezerva_adresa.web_text_max = 64
	stocat = u.content.stored_values.get("hds_tuner_rezerva")
	if stocat is None and u.remote_fallback_enabled.value and adresa(u.remote_fallback.value):
		# setarile OE-Alliance aduse din alta imagine, fara alegerea noastra
		stocat = adresa(u.remote_fallback.value)
	u.hds_tuner_rezerva = ConfigSelection(default=OPRIT, choices=alegeri([], stocat or "", u.remote_fallback.value))
	if stocat and u.hds_tuner_rezerva.value != stocat:
		u.hds_tuner_rezerva.value = stocat
		u.hds_tuner_rezerva.save()
	for el in (u.hds_tuner_rezerva, u.hds_tuner_rezerva_adresa):
		el.callNotifiersOnSaveAndCancel = True
		el.addNotifier(_schimbat, initial_call=False)
		el.hdsStare = _stareSetare
	# randul ales si numele OE-Alliance la fel de la pornire (o copie de setari veche le poate avea diferite)
	url = urlAles(u.hds_tuner_rezerva.value, u.hds_tuner_rezerva_adresa.value)
	if bool(url) != bool(u.remote_fallback_enabled.value) or (url and url != u.remote_fallback.value):
		u.remote_fallback_enabled.value = bool(url)
		if url:
			u.remote_fallback.value = url
		u.remote_fallback_enabled.save()
		u.remote_fallback.save()
	leagaZap()
	try:
		config.misc.hds_fluxuri_retea_acasa.addNotifier(_anuntSchimbat, initial_call=False)
		from enigma import eTimer
		_CEAS_ANUNT.append(eTimer())
		_CEAS_ANUNT[0].callback.append(anunta)
		_CEAS_ANUNT[0].start(ANUNT_DUPA_MS, True)
	except Exception as e:
		_jurnal("anuntul: %r" % (e,))


_CEAS_ANUNT = []


def urlFolosit():
	"""Adresa de la zap: numele OE-Alliance (pornit si cu adresa buna), altfel ""."""
	try:
		u = _config().usage
		if not u.remote_fallback_enabled.value:
			return ""
		return adresa(u.remote_fallback.value)
	except Exception:
		return ""


# ------------------------------------------------------------------ starea

_ULTIMA = [None]   # (ora, numele canalului, gazda) ultimei porniri prin rezerva


def liniiStare(st=None, ales=None, adresa_scrisa=None):
	"""Randurile starii, traduse: aceleasi pe televizor (deasupra ajutorului) si in web."""
	if st is None:
		st = cautare().rezultat()
	if ales is None or adresa_scrisa is None:
		try:
			u = _config().usage
			ales, adresa_scrisa = u.hds_tuner_rezerva.value, u.hds_tuner_rezerva_adresa.value
		except Exception:
			ales, adresa_scrisa = OPRIT, ""
	rez = []
	url = urlAles(ales, adresa_scrisa)
	if ales == OPRIT:
		rez.append(_t(T_STARE_OPRIT))
	elif ales == ALTA and not adresa_scrisa.strip():
		rez.append(_t(T_FARA_ADRESA))
	elif not url:
		rez.append(_t(T_ADRESA_GRESITA) % adresa_scrisa.strip()[:40])
	else:
		rez.append(_t(T_STARE_PORNIT) % numeAles(url, st.get("receptoare") or []))
	gasite = st.get("receptoare") or []
	if st.get("stare") == "lucreaza":
		rez.append(_t(T_CAUT))
	elif st.get("eroare"):
		rez.append(st["eroare"])
	elif st.get("cand") is not None:
		if gasite:
			rez.append(_t(T_GASITE) % ", ".join(eticheta(r) for r in gasite))
		else:
			rez.append(_t(T_NICIUNUL))
	for r in gasite:
		if url and r.get("url") == url and r.get("primeste") is False:
			rez.append(_t(T_NU_PRIMESTE) % eticheta(r))
	u = _ULTIMA[0]
	if u and url:
		rez.append(_t(T_ULTIMA) % u)
	return rez


def _stareSetare():
	cautaDacaE()
	puneAlegerile()
	return liniiStare()


def numeAles(url, gasite=None):
	"""Numele receptorului ales, ca in lista (numele anuntat si numele .local), sau gazda din adresa."""
	if gasite is None:
		gasite = cautare().rezultat()["receptoare"]
	for r in gasite:
		if r.get("url") and adresa(r["url"]) == url:
			return eticheta(r)
	return gazda(url)


def stareScurta():
	"""Textul randului din Setari tuner: Oprit sau numele receptorului ales. Porneste si cautarea, daca e veche."""
	cautaDacaE()
	url = urlFolosit()
	return numeAles(url) if url else _t(T_OPRIT)


def stareWeb():
	"""Pentru cartela tunerelor din /antena/tuner: {"pornit", "text", "linii", "adresa"}."""
	cautaDacaE()
	url = urlFolosit()
	return {"pornit": bool(url), "text": numeAles(url) if url else _t(T_OPRIT), "linii": liniiStare(),
		"adresa": "/setari?id=hds_tuner_rezerva"}


# ------------------------------------------------------------------ zap-ul

def textRezerva(cheie_canal, url, nume=""):
	"""Referinta redata prin rezerva pentru un canal (cheia HdsStreamRelay.cheie, "1:0:19:SID:TSID:ONID:NS:0:0:0:"):
	aceleasi 10 campuri, calea <url>/<cheia> (cu ':' scrise %3a, ca in orice referinta), apoi numele."""
	parti = cheie_canal.split(":")
	cale = "%s/%s" % (url.rstrip("/"), cheie_canal)
	nume = (nume or "").replace(":", " ").replace("\n", " ")
	return "%s%s:%s" % (":".join(parti[:10]) + ":", cale.replace(":", "%3a"), nume)


# Prioritatea tipurilor de tuner intre alternativele unui grup, ca prio_map din lib/service/servicedvb.cpp
# (eStaticServiceDVBBouquetInformation::isPlayable): un rand pentru fiecare valoare a config.usage.alternatives_priority
# (0 = DVB-S/-C/-T ... 5 = DVB-T/-S/-C), locurile (DVB-S, DVB-C, DVB-T); mai mare = aleasa intai.
PRIORITATE_TIPURI = ((3, 2, 1), (3, 1, 2), (2, 3, 1), (1, 3, 2), (1, 2, 3), (2, 1, 3))


def ordineTipuri():
	"""config.usage.alternatives_priority ca numar (0-5); 0, ca in fabrica, cand nu se poate citi (probele de pe PC)."""
	try:
		import sys
		v = int(sys.modules["Components.config"].config.usage.alternatives_priority.value)
	except Exception:
		return 0
	return v if 0 <= v < len(PRIORITATE_TIPURI) else 0


def prioritateTip(text, ordine=0):
	"""Locul alternativei `text` (referinta DVB) dupa felul ei de tuner, in ordinea `ordine`: spatiul de nume EEEE....
	= DVB-T, FFFF.... = DVB-C, altfel DVB-S (ca ramura implicita din isPlayable)."""
	rand = PRIORITATE_TIPURI[ordine if 0 <= ordine < len(PRIORITATE_TIPURI) else 0]
	try:
		sus = (int(str(text or "").split(":")[6], 16) >> 16) & 0xFFFF
	except (IndexError, ValueError):
		sus = 0
	return rand[2] if sus == 0xEEEE else rand[1] if sus == 0xFFFF else rand[0]


class Zap(object):
	"""Starea zap-ului prin rezerva. Pentru probe: liber (functia isPlayable), reda (pornirea playerului), nume, ceas,
	ordine (alternatives_priority)."""

	def __init__(self, liber=None, reda=None, nume=None, ceas=None, url=None, propriu=None, ordine=None):
		self.liber = liber or _tunerLiber
		self.reda = reda or _reda
		self.nume = nume or _numeCanal
		self.url = url or urlFolosit
		self.propriu = propriu or gazdaProprie
		self.ordine = ordine or ordineTipuri
		self.ceas = ceas
		self.prin = None          # (url, cheia) canalului de acum pornit prin rezerva
		self.asteapta = None      # (nav, playref, text, url, cheia) pana la INTARZIERE_MS
		self.local = None
		self.generatie = None

	def peZap(self, nav, playref):
		"""Navigation.playServiceUltima: (playref, True) cand canalul porneste prin rezerva, altfel playref."""
		vechi, self.prin = self.prin, None
		self.asteapta = None
		self.local = None
		self.generatie = None
		url = self.url()
		if not url:
			return playref
		from Components.HdsStreamRelay import cheie, _acelasiTransponder
		k = cheie(playref)
		if not k:
			return playref
		if self.liber(playref):
			self.local = (nav, playref, k, getattr(nav, "hdsGeneratieZap", None))
			return playref
		if self.propriu(gazda(url)):
			# numele hdsatelitN.local se pot schimba intre receptoare dupa o pornire deodata: nu se cere de la sine insusi
			_jurnal("adresa rezervei (%s) e chiar acest receptor: canalul porneste direct" % gazda(url))
			return playref
		nume = self.nume(playref)
		text = textRezerva(k, url, nume)
		if vechi and vechi[0] == url and not _acelasiTransponder(k, vechi[1]):
			self.asteapta = (nav, playref, text, url, k)
			self.generatie = getattr(nav, "hdsGeneratieZap", None)
			self._pornesteCeas()
			return playref, True
		if self.reda(nav, text):
			self._pornit(url, k, nume)
			return playref, True
		return playref

	def laEroare(self, nav):
		"""Try the selected reserve once after a local tuning failure."""
		a = self.local
		if a is None or a[0] is not nav or a[3] != getattr(nav, "hdsGeneratieZap", None):
			return False
		from Components.HdsStreamRelay import cheie
		url = self.url()
		acum = nav.getCurrentlyPlayingServiceReference()
		if not url or self.propriu(gazda(url)) or acum is None or cheie(acum) != a[2]:
			return False
		self.local = None
		self.generatie = a[3]
		self.asteapta = (nav, a[1], textRezerva(a[2], url, self.nume(a[1])), url, a[2])
		self._pornesteCeas()
		return True

	def alternativa(self, nav, grup):
		"""Navigation.grupFaraTunerUltima: la un grup de alternative fara nicio alternativa libera (nici dupa cedarile
		extensiilor grupului), alternativa DVB pe care o da rezerva, aleasa ca de enigma2 intre alternativele libere: dupa
		prioritatea tipurilor de tuner (config.usage.alternatives_priority, prioritateTip), la egalitate prima din grup;
		Navigation o porneste, iar peZap (playServiceUltima) o ia prin rezerva. None cand rezerva nu e aleasa sau e chiar
		acest receptor (zap-ul se opreste, ca inainte)."""
		url = self.url()
		if not url or self.propriu(gazda(url)):
			return None
		from Components.HdsStreamRelay import cheie
		ordine = self.ordine()
		alesa, loc = None, 0
		for text in nav.alternativeDvb(grup):
			k = cheie(text)
			if not k:
				continue
			p = prioritateTip(text, ordine)
			if p > loc:
				alesa, loc = (text, k), p
		if alesa is None:
			return None
		text, k = alesa
		try:
			from enigma import eServiceReference
			ref = eServiceReference(text)
		except Exception as e:
			_jurnal("alternativa grupului: %r" % (e,))
			return None
		_jurnal("grupul n-are alternativa libera: %s merge prin rezerva" % k)
		return ref

	def _pornit(self, url, k, nume):
		self.prin = (url, k)
		_ULTIMA[0] = (time.strftime("%H:%M"), nume or k, gazda(url))
		_jurnal("tunerele nu pot lua %s: canalul vine de la %s" % (k, gazda(url)))

	def _pornesteCeas(self):
		if self.ceas is None:
			from enigma import eTimer
			self.ceas = eTimer()
			self.ceas.callback.append(self.dupaIntarziere)
		self.ceas.start(INTARZIERE_MS, True)

	def dupaIntarziere(self):
		a, self.asteapta = self.asteapta, None
		if a is None:
			return
		nav, playref, text, url, k = a
		if self.url() != url or (self.generatie is not None and
				self.generatie != getattr(nav, "hdsGeneratieZap", None)):
			return
		from Components.HdsStreamRelay import cheie
		try:
			acum = nav.getCurrentlyPlayingServiceReference()
		except Exception:
			acum = None
		if acum is None or cheie(acum) != k:
			return      # alt zap intre timp
		generatie = getattr(nav, "hdsGeneratieZap", None)
		redat = self.reda(nav, text)
		if generatie != getattr(nav, "hdsGeneratieZap", None):
			return
		if redat:
			# Replacing the failed service emits evEnd, which clears Navigation's cache.
			nav.currentlyPlayingServiceReference = playref
			nav.currentlyPlayingService = None
			self._pornit(url, k, self.nume(playref))
		else:
			try:
				nav.pnav.playService(playref)
				if generatie == getattr(nav, "hdsGeneratieZap", None):
					nav.currentlyPlayingServiceReference = playref
					nav.currentlyPlayingService = None
			except Exception as e:
				_jurnal("canalul nu a pornit: %r" % (e,))


def gazdaProprie(g, nume_propriu=NUME_PROPRIU, adrese=None):
	"""Gazda din adresa rezervei e chiar acest receptor: numele hdsatelitN.local publicat de el, numele lui de retea
	(.local) sau una din adresele lui IPv4."""
	g = (g or "").lower().rstrip(".")
	if not g:
		return False
	nume = set()
	try:
		nume.add(((_citeste(nume_propriu) or "").strip() + ".local").lower())
	except Exception:
		pass
	try:
		nume.add(socket.gethostname().split(".", 1)[0].lower() + ".local")
	except Exception:
		pass
	if g in nume or g in ("localhost", "127.0.0.1"):
		return True
	try:
		if adrese is None:
			from Components import HdsAparateRetea as A
			adrese = A._adrese_locale()
		return g in adrese
	except Exception:
		return False


def _tunerLiber(ref):
	"""Managerul de tunere poate porni canalul acum (serviciul vechi e deja oprit)."""
	try:
		from enigma import eServiceCenter, eServiceReference
		info = eServiceCenter.getInstance().info(ref)
		return bool(info and info.isPlayable(ref, eServiceReference()))
	except Exception as e:
		_jurnal("isPlayable: %r" % (e,))
		return True


def _reda(nav, text):
	from enigma import eServiceReference
	pnav = getattr(nav, "pnav", None)
	if pnav is None:
		return False
	rez = pnav.playService(eServiceReference(text))
	if rez:
		_jurnal("playerul nu porneste prin rezerva (%s)" % rez)
		return False
	return True


def _numeCanal(ref):
	try:
		from ServiceReference import ServiceReference
		return ServiceReference(ref).getServiceName() or ""
	except Exception:
		return ""


_ZAP = []


def zap():
	if not _ZAP:
		_ZAP.append(Zap())
	return _ZAP[0]


def laZap(nav, playref, event, infobar):
	return zap().peZap(nav, playref)


def laGrup(nav, grup):
	return zap().alternativa(nav, grup)


def leagaEvenimente(nav):
	"""The deferred retry must not replace a service inside event dispatch."""
	from enigma import iPlayableService
	def eveniment(ev):
		if ev == iPlayableService.evTuneFailed:
			zap().laEroare(nav)
	nav.event.append(eveniment)


def textDiagnostic(cod):
	if cod == 400:
		return _t(N_("Receptorul de rezervă a refuzat canalul. Tunerul poate fi ocupat cu alt canal; preluarea nu este posibilă acum."))
	if cod == 404:
		return _t(N_("Receptorul de rezervă nu găsește canalul cerut (HTTP 404)."))
	if cod == 401:
		return _t(N_("Receptorul de rezervă cere autentificare pentru flux (HTTP 401)."))
	if cod == 403:
		return _t(N_("Receptorul de rezervă nu permite acest flux (HTTP 403)."))
	if cod >= 400:
		return _t(N_("Receptorul de rezervă nu poate trimite canalul acum (HTTP %d).")) % cod
	if cod == -1:
		return _t(N_("Receptorul de rezervă nu răspunde la cererea de flux."))
	if cod == -2:
		return _t(N_("Fluxul de la receptorul de rezervă s-a întrerupt sau nu trimite date."))
	if cod == -4:
		return _t(N_("Receptorul de rezervă a răspuns cu un flux care nu poate fi redat."))
	return ""


def diagnostic(ref, service):
	"""Only the source's measured result, with no extra network request."""
	try:
		from Components.HdsStreamRelay import cheie
		z = zap()
		if not z.prin or not ref or cheie(ref) != z.prin[1]:
			return ""
		from enigma import iServiceInformation
		info = service.info() if service is not None else None
		# Older native players return -1 for unknown fields, not a connection failure.
		if info is None or info.getInfo(iServiceInformation.sUser + 43) != 0x484453:
			return ""
		return textDiagnostic(info.getInfo(iServiceInformation.sUser + 42))
	except (AttributeError, ImportError, TypeError):
		return ""


def leagaZap(navigatie=None):
	"""Navigation.playServiceUltima = laZap si Navigation.grupFaraTunerUltima = laGrup numai cat rezerva e aleasa (fara
	ea, zap-ul nu face nimic in plus)."""
	try:
		if navigatie is None:
			from Navigation import Navigation as navigatie
	except Exception:
		return
	if urlFolosit():
		navigatie.playServiceUltima = laZap
		if hasattr(navigatie, "grupFaraTunerUltima"):
			navigatie.grupFaraTunerUltima = laGrup
	else:
		if getattr(navigatie, "playServiceUltima", None) is laZap:
			navigatie.playServiceUltima = None
		if getattr(navigatie, "grupFaraTunerUltima", None) is laGrup:
			navigatie.grupFaraTunerUltima = None


# ------------------------------------------------------------------ anuntul _e2stream._tcp

def numeAnunt():
	"""Numele cu care se anunta receptorul: HD Satelit si modelul (marca si modelul din BoxInfo)."""
	try:
		from Components.SystemInfo import getBoxDisplayName
		marca, model = getBoxDisplayName()
	except Exception:
		marca, model = "", ""
	nume = " ".join(x for x in ("HD Satelit", marca, model) if x).strip()
	nume = "".join(c for c in nume if c.isalnum() or c in " -_+()")
	return nume.encode("utf-8")[:60].decode("utf-8", "ignore").strip() or "HD Satelit"


def textAnunt(nume):
	return ("<?xml version=\"1.0\" standalone='no'?>\n"
		"<!DOCTYPE service-group SYSTEM \"avahi-service.dtd\">\n"
		"<!-- HD Satelit: serverul de flux (portul 8001), ca streamserverul OE-Alliance; il gasesc receptoarele din casa "
		"care il folosesc ca tuner de rezerva -->\n"
		"<service-group>\n"
		"  <name>%s</name>\n"
		"  <service>\n"
		"    <type>_e2stream._tcp</type>\n"
		"    <port>%d</port>\n"
		"  </service>\n"
		"</service-group>\n") % (nume, PORT)


def _citeste(cale):
	try:
		with open(cale, "r") as f:
			return f.read()
	except (IOError, OSError):
		return None


def anunta(pornit=None, cale=FISIER_ANUNT, nume=None, semnal=None):
	"""Pune sau scoate anuntul dupa setarea fluxurilor in retea; avahi-daemon citeste din nou dosarul numai cand
	fisierul s-a schimbat. -> "pus", "scos" sau "" (nimic schimbat)."""
	if pornit is None:
		try:
			pornit = bool(_config().misc.hds_fluxuri_retea_acasa.value)
		except Exception:
			return ""
	vechi = _citeste(cale)
	schimbat = ""
	try:
		if pornit:
			nou = textAnunt(nume or numeAnunt())
			if vechi != nou and os.path.isdir(os.path.dirname(cale)):
				with open(cale + ".nou", "w") as f:
					f.write(nou)
				os.rename(cale + ".nou", cale)
				schimbat = "pus"
		elif vechi is not None:
			os.unlink(cale)
			schimbat = "scos"
	except (IOError, OSError) as e:
		_jurnal("anuntul: %r" % (e,))
		return ""
	if schimbat:
		(semnal or _semnalAvahi)()
		_jurnal("anuntul _e2stream._tcp %s" % schimbat)
	return schimbat


def _anuntSchimbat(_el=None):
	anunta()


def _semnalAvahi():
	import signal
	for cale in PID_AVAHI:
		try:
			os.kill(int((_citeste(cale) or "").strip()), signal.SIGHUP)
			return
		except (ValueError, OSError):
			continue
