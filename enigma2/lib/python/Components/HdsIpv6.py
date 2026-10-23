# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsIpv6.py: setarea "IPv6" (Setari > Retea si Internet > IPv6, sectiunea hds_ipv6 din setup.xml; in web cardul IPv6
# din pagina /retea, retea_web.py).
#
# IPv6 e OPRIT din fabrica. Adevarul e fisierul-semn /etc/hds-ipv6-pornit: exista = IPv6 pornit, lipseste = oprit;
# din fabrica nu exista. Acelasi semn il citeste stratul imaginii la pornirea sistemului, inainte de retea si de
# enigma2 (scriptul hds-ipv6 din rcS pune net.ipv6.conf.all si default.disable_ipv6; poarta /usr/bin/odhcp6c nu
# porneste clientul DHCPv6 fara semn). Aici:
# - setarea config.usage.hds_ipv6 urmeaza semnul la pornire; o schimbare (televizor, web) scrie sau sterge semnul
#   (scriere sigura: fisierul .nou, apoi mutat peste) si aplica pe loc:
#     oprit:  clientul odhcp6c oprit (SIGTERM), daca ruleaza, apoi disable_ipv6 = 1 pe all si default: nucleul scoate
#             adresele IPv6 de pe toate placile si nu le pune nici pe cele care apar mai tarziu (o placa Wi-Fi USB);
#     pornit: disable_ipv6 = 0, apoi clientul pornit pe placile pornite care nu il au, cu argumentele lui ifup: placa
#             cu randul "iface <placa> inet6 dhcp" in /etc/network/interfaces ca ifup-ul din busybox (-Ntry -t120),
#             celelalte ca /etc/network/if-up.d/odhcp6c (-Nnone); -s /usr/sbin/odhcp6c-update cand scriptul exista;
# - la pornirea interfetei (InitUsageConfig) starea se aplica o data: pe o imagine fara stratul de mai sus sistemul a
#   pornit IPv6 si clientul inainte de enigma2; pornit, numai disable_ipv6 = 0 (clientii ii porneste ifup, ca pana acum);
# - dupa ce reteaua porneste din nou din Python (Components/Network.py: restartNetwork, activateInterface;
#   Components/HdsComutareRetea.py: ifup), oprit se aplica din nou, fiindca ifup porneste clientul (fara poarta pe o
#   imagine fara strat); pornit nu face nimic acolo (ca pana acum);
# - stare(): starea reala (semnul, disable_ipv6, clientii care ruleaza, adresele IPv6 din /proc/net/if_inet6) si
#   randurile de aratat, pentru ecran (atributul hdsStare al setarii: Screens/Setup.py le arata deasupra textului de
#   ajutor si le citeste din nou la cateva secunde) si pentru web.
# IPv4 nu se atinge. Setarea nu intra in copia setarilor (Components/HdsCopieSetari.SCOT): semnul e starea receptorului.
#
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau caile lor (CAI) si pornirea programelor.

import os
import signal
import socket

CAI = {
	"semn": "/etc/hds-ipv6-pornit",
	"conf": "/proc/sys/net/ipv6/conf",
	"inet6": "/proc/net/if_inet6",
	"proc": "/proc",
	"interfaces": "/etc/network/interfaces",
	"sysfs": "/sys/class/net",
	"actualizare": "/usr/sbin/odhcp6c-update",
}
CLIENT = "odhcp6c"
# primul rand din semn (numai pentru cine il citeste de mana)
MOTIV_SEMN = "pornit din setari"
IFF_UP = 0x1


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_), fara efect: textele se traduc la afisare."""
	return text


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


T_OPRIT = N_("Oprit acum: plăcile de rețea nu au adrese IPv6, iar clientul IPv6 nu rulează.")
T_PORNIT = N_("Pornit acum.")
T_ADRESE = N_("Adrese IPv6: %s")
T_FARA_ADRESE = N_("Nicio adresă IPv6 încă.")
T_CLIENT = N_("Clientul IPv6 rulează pe: %s")
T_FARA_CLIENT = N_("Clientul IPv6 nu rulează.")
T_RAMAS_PORNIT = N_("Setarea e oprită, dar receptorul are încă IPv6. Se oprește de tot la următoarea pornire.")
T_RAMAS_OPRIT = N_("Setarea e pornită, dar IPv6 e încă oprit. Pornește de tot la următoarea pornire.")
T_NECITIT = N_("Starea IPv6 nu se poate citi pe acest receptor.")


def _jurnal(text):
	print("[HdsIpv6] %s" % text)


def _citeste(cale, maxim=65536):
	try:
		with open(cale, "r", encoding="utf-8", errors="replace") as f:
			return f.read(maxim)
	except (IOError, OSError):
		return None


# ---------------------------------------------------------------- semnul

def pornit():
	"""True daca semnul exista (IPv6 pornit). Din fabrica: False."""
	return os.path.exists(CAI["semn"])


def scrieSemn(da):
	"""da=True: pune semnul (scris intai in .nou, apoi mutat peste); da=False: il sterge. True daca a reusit."""
	semn = CAI["semn"]
	try:
		if da:
			if not os.path.exists(semn):
				nou = semn + ".nou"
				with open(nou, "w", encoding="utf-8") as f:
					f.write(MOTIV_SEMN + "\n")
					f.flush()
					os.fsync(f.fileno())
				os.replace(nou, semn)
		elif os.path.exists(semn):
			os.remove(semn)
		return True
	except (IOError, OSError) as eroare:
		_jurnal("nu pot schimba %s: %s" % (semn, eroare))
		return False


# ---------------------------------------------------------------- nucleul

def disable():
	"""{"all": 0|1|None, "default": 0|1|None} din /proc/sys/net/ipv6/conf (None: nu se poate citi)."""
	rez = {}
	for c in ("all", "default"):
		t = _citeste(os.path.join(CAI["conf"], c, "disable_ipv6"), 16)
		rez[c] = int(t.strip()) if t is not None and t.strip() in ("0", "1") else None
	return rez


def scrieDisable(valoare):
	"""disable_ipv6 = valoare (0 sau 1) pe all si default. Lista erorilor (goala daca a mers)."""
	erori = []
	for c in ("all", "default"):
		cale = os.path.join(CAI["conf"], c, "disable_ipv6")
		try:
			with open(cale, "w", encoding="ascii") as f:
				f.write("%d\n" % valoare)
		except (IOError, OSError) as eroare:
			erori.append("%s: %s" % (cale, eroare))
	for e in erori:
		_jurnal("nu pot scrie disable_ipv6: %s" % e)
	return erori


def adrese():
	"""[(placa, adresa scrisa scurt, "globala"|"locala"|"alta")] din /proc/net/if_inet6, fara lo."""
	t = _citeste(CAI["inet6"])
	rez = []
	for rand in (t or "").splitlines():
		c = rand.split()
		if len(c) < 6 or c[5] == "lo" or len(c[0]) != 32:
			continue
		grupe = [c[0][i:i + 4] for i in range(0, 32, 4)]
		try:
			scris = ":".join("%x" % int(g, 16) for g in grupe)
			scris = socket.inet_ntop(socket.AF_INET6, socket.inet_pton(socket.AF_INET6, scris))
		except (ValueError, OSError, AttributeError):
			pass
		domeniu = {"00": "globala", "20": "locala"}.get(c[3], "alta")
		rez.append((c[5], scris, domeniu))
	return rez


# ---------------------------------------------------------------- clientul DHCPv6

def clienti():
	"""[(pid, placa)] pentru fiecare proces odhcp6c (numele procesului; placa = ultimul argument)."""
	rez = []
	try:
		intrari = os.listdir(CAI["proc"])
	except OSError:
		return rez
	for x in intrari:
		if not x.isdigit():
			continue
		nume = _citeste(os.path.join(CAI["proc"], x, "comm"), 64)
		if nume is None or nume.strip() != CLIENT:
			continue
		linie = _citeste(os.path.join(CAI["proc"], x, "cmdline"), 4096) or ""
		arg = [a for a in linie.split("\0") if a]
		rez.append((int(x), arg[-1] if len(arg) > 1 else ""))
	return sorted(rez)


def opresteClientii():
	"""SIGTERM fiecarui odhcp6c (clientul isi elibereaza adresele si iese). Cati au primit semnalul."""
	n = 0
	for pid, placa in clienti():
		try:
			os.kill(pid, signal.SIGTERM)
			n += 1
		except OSError as eroare:
			_jurnal("nu pot opri clientul %d (%s): %s" % (pid, placa, eroare))
	return n


def _randuriInterfaces():
	return [r.strip().split() for r in (_citeste(CAI["interfaces"]) or "").splitlines()]


def placiConfigurate():
	"""Placile din /etc/network/interfaces cu un rand "iface <placa> inet ..." (fara lo), in ordinea din fisier."""
	rez = []
	for c in _randuriInterfaces():
		if len(c) >= 3 and c[0] == "iface" and c[2] in ("inet", "inet6") and c[1] != "lo" and c[1] not in rez:
			rez.append(c[1])
	return rez


def _pornita(placa):
	t = _citeste(os.path.join(CAI["sysfs"], placa, "flags"), 32)
	try:
		return bool(int(t.strip(), 16) & IFF_UP)
	except (ValueError, AttributeError):
		return False


def argumenteClient(placa):
	"""Argumentele lui odhcp6c pentru placa, ca la ifup (fara numele programului)."""
	inet6 = any(len(c) >= 4 and c[0] == "iface" and c[1] == placa and c[2] == "inet6" and c[3] == "dhcp"
		for c in _randuriInterfaces())
	pid = "/var/run/odhcp6c.%s.pid" % placa
	arg = ["-s", CAI["actualizare"]] if os.path.exists(CAI["actualizare"]) else []
	if inet6:
		return arg + ["-Ntry", "-t120", "-d", "-p", pid, placa]
	return arg + ["-Nnone", "-d", "-p", pid, placa]


_consola = []


def _porneste(argv):
	"""Porneste programul fara sa astepte (odhcp6c -d trece singur in fundal): consola enigma2, ca Network.py; pe PC
	(fara enigma2) subprocess. Probele inlocuiesc functia."""
	try:
		from Components.Console import Console
		if not _consola:
			_consola.append(Console())
		_consola[0].ePopen((argv[0],) + tuple(argv))
		return True
	except ImportError:
		import subprocess
		subprocess.Popen(argv, close_fds=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
			stderr=subprocess.DEVNULL)
		return True


PORNIRE = [_porneste]


def pornesteClientii():
	"""Clientul pe placile configurate si pornite care nu il au. Lista placilor pe care l-a pornit."""
	au = set(p for _pid, p in clienti())
	pornite = []
	for placa in placiConfigurate():
		if placa in au or not _pornita(placa):
			continue
		try:
			PORNIRE[0]([CLIENT] + argumenteClient(placa))
			pornite.append(placa)
		except Exception as eroare:
			_jurnal("nu pot porni clientul pe %s: %s" % (placa, eroare))
	return pornite


# ---------------------------------------------------------------- aplicarea

def aplica(da, clientii=True):
	"""Aplica pe loc: da=False opreste clientii, apoi disable_ipv6 = 1; da=True disable_ipv6 = 0, apoi (cu clientii)
	porneste clientii lipsa. {"erori": [...], "opriti": n, "porniti": [...]}."""
	rez = {"erori": [], "opriti": 0, "porniti": []}
	if da:
		rez["erori"] = scrieDisable(0)
		if clientii:
			rez["porniti"] = pornesteClientii()
	else:
		rez["opriti"] = opresteClientii()
		rez["erori"] = scrieDisable(1)
	_jurnal("%s: disable_ipv6 %s, clienti opriti %d, porniti %s%s" % ("pornit" if da else "oprit", 0 if da else 1,
		rez["opriti"], ",".join(rez["porniti"]) or "-", (", erori: %d" % len(rez["erori"])) if rez["erori"] else ""))
	return rez


def seteaza(da):
	"""Alegerea omului: semnul scris sau sters, apoi aplicarea pe loc. True daca semnul s-a schimbat (aplicarea se
	face oricum, ca starea sa fie cea aleasa cat se poate)."""
	ok = scrieSemn(da)
	aplica(da)
	return ok


def laPornire():
	"""La pornirea interfetei: starea semnului, fara clienti noi (pornit, ii porneste ifup, ca pana acum)."""
	return aplica(pornit(), clientii=False)


def dupaRetea():
	"""Dupa ifup / repornirea retelei din Python: oprit se aplica din nou (ifup a putut porni clientul)."""
	if not pornit():
		return aplica(False)
	return None


# ---------------------------------------------------------------- starea pentru ecran si web

def stare():
	"""Starea reala: {"semn", "disable", "pornit_acum", "clienti", "adrese", "linii"} (linii traduse)."""
	d = disable()
	c = clienti()
	a = adrese()
	semn = pornit()
	if d["all"] is None:
		pornit_acum = None
	else:
		pornit_acum = d["all"] == 0
	return {"semn": semn, "disable": d, "pornit_acum": pornit_acum, "clienti": c, "adrese": a,
		"linii": linii(semn, pornit_acum, c, a)}


def linii(semn, pornit_acum, c, a):
	"""Randurile de aratat (ecran si web), traduse."""
	if pornit_acum is None:
		return [_t(T_NECITIT)]
	rez = []
	if not pornit_acum and not a and not c:
		rez.append(_t(T_OPRIT))
	else:
		if pornit_acum:
			rez.append(_t(T_PORNIT))
		rez.append(_t(T_ADRESE) % ", ".join("%s (%s)" % (adr, placa) for placa, adr, _d in a) if a else _t(T_FARA_ADRESE))
		rez.append(_t(T_CLIENT) % ", ".join(sorted(set(p or "?" for _pid, p in c))) if c else _t(T_FARA_CLIENT))
	if not semn and (pornit_acum or a or c):
		rez.append(_t(T_RAMAS_PORNIT))
	elif semn and not pornit_acum:
		rez.append(_t(T_RAMAS_OPRIT))
	return rez


# ---------------------------------------------------------------- setarea

# ultima valoare pusa de setare (sau citita la pornire): notificarea schimba ceva numai cand valoarea e alta, ca salvarea
# unui ecran (toate randurile) sa nu aplice de doua ori
_aplicata = [None]


def _aplicaSetarea(element):
	valoare = bool(element.value)
	if valoare == _aplicata[0]:
		return
	if seteaza(valoare):
		_aplicata[0] = valoare


def initConfig():
	"""Din InitUsageConfig: config.usage.hds_ipv6 urmeaza semnul; o schimbare din ecran sau din web pune sau scoate
	semnul si aplica pe loc ("Renunta" pune valoarea salvata inapoi, cu aplicarea ei). Apoi starea semnului se aplica o
	data (laPornire)."""
	from Components.config import config, ConfigYesNo
	element = ConfigYesNo(default=False)
	config.usage.hds_ipv6 = element
	element.value = pornit()
	_aplicata[0] = bool(element.value)
	element.save()
	element.callNotifiersOnSaveAndCancel = True
	element.addNotifier(_aplicaSetarea, initial_call=False)
	element.hdsStare = lambda: stare()["linii"]   # starea de acum in ecranul de setari (Screens/Setup.py)
	try:
		laPornire()
	except Exception as eroare:
		_jurnal("aplicarea la pornire: %s" % eroare)
