# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsProcesorRaport.py: raportul de procesor, trimis singur cand firul principal al enigma2 tine un nucleu ocupat.
#
# De ce: pe Vu+ Solo SE firul principal tinea un nucleu la 95-99% (jumatate in nucleul Linux),
# iar cauza nu se putea afla de la distanta. Testerul nu face nimic: cand firul principal trece de PRAG (80% dintr-un
# nucleu) neintrerupt cel putin DURATA_S (2 minute, masurat cu ceasul monoton), receptorul culege o fereastra de
# FEREASTRA_S secunde si trimite raportul prin canalul rapoartelor de pornire (tools/hds-raport.sh, "raport manual",
# cu motiv=procesor si declansare=automata in antet; serverul il primeste fara nicio schimbare), o singura data pe
# pornire. Raportul ajunge si pe stickul pus, ca rapoartele de pornire.
#
# Ce culege fereastra (numai date tehnice, din procesul enigma2; nimic despre canale, setari sau modulele de acces):
# - timpii tuturor firelor enigma2 (/proc/self/task/*/stat: numele, starea, timpul in program si in nucleu) la inceput si
#   la sfarsit, ca procent dintr-un nucleu;
# - stiva Python a firului principal, de ESANTIOANE ori: faulthandler e inregistrat pe SEMNAL (SIGRTMIN+8, fisierul lui
#   in /tmp), iar semnalele le trimite un proces sh separat, la ore reale; manerul faulthandler scrie stivele fara GIL,
#   deci un esantion cade si cand C++ tine GIL-ul (de pilda in ioctl-ul tunerului), nu numai intre apelurile Python.
#   Se numara cadrul de sus si primele trei cadre; caile se taie ca in raportul pornirii (dupa enigma2/python/), un cadru
#   cu "cam" in cale e numai "(modul-acces)";
# - clasamentul tuturor proceselor (/proc/*/stat la inceput si la sfarsit; la un tester timpul era in user pe
#   tot sistemul, deci trebuie vazut si daca e alt proces); numele unui modul de acces e numai "modul-acces";
# - contoarele citirilor starii tunerelor (enigma.getFrontendReadCounts(), lib/dvb/hdscitirifrontend.h): cereri, cate au
#   venit din memorie, ioctl-uri, cat timp in ioctl;
# - /proc/interrupts si /proc/stat la inceput si la sfarsit (intreruperile care au crescut cel mai mult).
#
# Partea de calcul (citirea textelor din /proc, pragul, stivele, textul raportului) nu cere enigma2: se poate proba
# separat.

import os
import re
import time

PRAG = 0.80              # din timpul unui nucleu
DURATA_S = 120           # neintrerupt atata timp
PAS_S = 10               # cat de des se masoara firul principal
FEREASTRA_S = 10         # fereastra culegerii
ESANTIOANE = 40          # stivele firului principal in fereastra (un semnal la 250 ms)
SEMNAL_PESTE_RTMIN = 8   # SIGRTMIN+7 e al paznicului (mytest.py), +8 al raportului de procesor
CLK = 100                # tick-uri pe secunda (USER_HZ)
MAX_STIVA = 3            # cadrele numarate impreuna
MAX_RANDURI = 25         # randuri in fiecare clasament

PROGRAM = "/usr/bin/hds-raport.sh"
FISIER_STIVE = "/tmp/hds-procesor-stive.txt"
FISIER_RAPORT = "/tmp/hds-procesor-raport.txt"
SEMN_FACUT = "/tmp/hds-procesor-raport.facut"

_urmaritor = None


# ---------------------------------------------------------------- citirea textelor din /proc (fara enigma2)

def fir_din_stat(text):
	"""(nume, stare, utime, stime) din /proc/<pid>/task/<tid>/stat; numele poate avea spatii si paranteze"""
	i, j = text.find("("), text.rfind(")")
	if i < 0 or j < i:
		return None
	camp = text[j + 2:].split()
	if len(camp) < 13:
		return None
	try:
		return text[i + 1:j], camp[0], int(camp[11]), int(camp[12])
	except ValueError:
		return None


def intreruperi(text):
	"""{eticheta: (total pe toate procesoarele, nume)} din /proc/interrupts"""
	rez = {}
	randuri = text.splitlines()
	if not randuri:
		return rez
	n = len(randuri[0].split())
	for r in randuri[1:]:
		p = r.split()
		if len(p) < 2 or not p[0].endswith(":"):
			continue
		cifre = []
		for x in p[1:1 + n]:
			if x.isdigit():
				cifre.append(int(x))
			else:
				break
		rez[p[0][:-1]] = (sum(cifre), " ".join(p[1 + len(cifre):]))
	return rez


_MODUL_ACCES = re.compile(r"cam|cardd([^a-z]|$)|card[_.-]?serv|(^|[^a-z])[gs]box|newcs([^a-z]|$)|cs3[0-9][0-9]x|"
	r"radegast|smartcard", re.I)


def nume_proces(nume):
	"""numele procesului pentru raport: al unui modul de acces (forma din hds-raport.sh) e "modul-acces" """
	return "modul-acces" if _MODUL_ACCES.search(nume or "") else nume


def cresteri_intreruperi(a, b, maxim=8):
	"""[(eticheta, nume, crestere)] cele mai mari cresteri intre doua citiri"""
	rez = []
	for k, (v, nume) in b.items():
		d = v - a.get(k, (0, ""))[0]
		if d > 0:
			rez.append((k, nume, d))
	rez.sort(key=lambda x: -x[2])
	return rez[:maxim]


def procesor_total(text):
	"""(ocupat, total) in tick-uri, din primul rand "cpu" al /proc/stat"""
	for r in text.splitlines():
		p = r.split()
		if p and p[0] == "cpu":
			v = [int(x) for x in p[1:] if x.isdigit()]
			idle = v[3] + (v[4] if len(v) > 4 else 0)
			return sum(v) - idle, sum(v)
	return 0, 0


class Prag(object):
	"""firul principal peste PRAG neintrerupt DURATA_S, cu ceasul monoton: adauga(acum, tick-uri cumulate) -> True
	cand s-a atins (o singura data, pana la reset)"""

	def __init__(self, prag=PRAG, durata=DURATA_S, clk=CLK):
		self.prag, self.durata, self.clk = prag, durata, clk
		self.ultima = None      # (acum, tick-uri)
		self.de_la = None       # de cand e peste prag
		self.parte = 0.0        # ultima parte masurata

	def adauga(self, acum, ticks):
		if self.ultima is None:
			self.ultima = (acum, ticks)
			return False
		t0, k0 = self.ultima
		self.ultima = (acum, ticks)
		dt = acum - t0
		if dt <= 0 or ticks < k0:
			self.de_la = None
			return False
		self.parte = (ticks - k0) / float(self.clk) / dt
		if self.parte < self.prag:
			self.de_la = None
			return False
		if self.de_la is None:
			self.de_la = t0
		return acum - self.de_la >= self.durata


# ---------------------------------------------------------------- stivele (forma faulthandler)

# Python 3.14 scrie si numele firului: "Thread 0x... [nume] (most recent call first):"
_CAP = re.compile(r"^(?:Current thread|Thread) (0x[0-9A-Fa-f]+)(?: \[[^\]]*\])? \(most recent call first\):\s*$")
_CADRU = re.compile(r'^  File "([^"]*)", line (\d+) in (\S+)\s*$')


def cale_curata(cale):
	"""calea taiata ca in raportul pornirii (rp_stive): dupa enigma2/python/ sau python3.N/, altfel "(alt fisier)";
	orice cale cu "cam" e "(modul-acces)" """
	if "cam" in cale.lower():
		return "(modul-acces)"
	for semn in ("enigma2/python/",):
		i = cale.find(semn)
		if i >= 0:
			return cale[i + len(semn):]
	m = re.search(r"python3(?:\.\d+)?/", cale)
	if m:
		return cale[m.start():]
	return "(alt fisier)"


def stive_fir(text, ident):
	"""lista stivelor (fiecare: [cadrul de sus, ...] ca "cale:rand functie") ale firului cu identificatorul ident, din
	toate scrierile faulthandler din text"""
	rez, cur = [], None
	for r in text.splitlines():
		m = _CAP.match(r)
		if m:
			if cur is not None:
				rez.append(cur)
			cur = [] if int(m.group(1), 16) == ident else None
			continue
		if cur is None:
			continue
		m = _CADRU.match(r)
		if m:
			c = cale_curata(m.group(1))
			cur.append(c if c == "(modul-acces)" else "%s:%s %s" % (c, m.group(2), m.group(3)))
		elif r.strip() == "<no Python frame>":
			cur.append("(fara cadru Python)")
		elif not r.strip():
			rez.append(cur)
			cur = None
	if cur is not None:
		rez.append(cur)
	return rez


def clasamente(stive, adancime=MAX_STIVA):
	"""(cadrul de sus -> numar, primele `adancime` cadre -> numar), descrescator"""
	sus, lant = {}, {}
	for s in stive:
		if not s:
			s = ["(gol)"]
		sus[s[0]] = sus.get(s[0], 0) + 1
		k = " <- ".join(s[:adancime])
		lant[k] = lant.get(k, 0) + 1
	return (sorted(sus.items(), key=lambda x: (-x[1], x[0])), sorted(lant.items(), key=lambda x: (-x[1], x[0])))


# ---------------------------------------------------------------- textul raportului

def _dif32(a, b, cheie):
	try:
		return (int(b[cheie]) - int(a[cheie])) & 0xFFFFFFFF
	except (KeyError, TypeError, ValueError):
		return None


def text_raport(fire_a, fire_b, dt, intr_a, intr_b, proc_a, proc_b, fe_a, fe_b, stive, pid, parte, clk=CLK,
		procese_a=None, procese_b=None):
	"""textul sectiunii raportului; fire_*: {tid: (nume, stare, utime, stime)}"""
	r = ["procesor_fereastra_s=%.1f" % dt, "procesor_prag=%d%%/%ds" % (int(PRAG * 100), DURATA_S),
		"fir_principal_ultima_masura=%d%%" % int(round(parte * 100))]
	ocupat = procesor_total(proc_b)[0] - procesor_total(proc_a)[0]
	total = procesor_total(proc_b)[1] - procesor_total(proc_a)[1]
	if total > 0:
		r.append("procesor_total_ocupat=%d%%" % int(round(100.0 * ocupat / total)))
	r.append("")
	r.append("-- firele enigma2 (procent dintr-un nucleu: in program + in nucleu; starea la sfarsit)")
	randuri = []
	for tid, b in fire_b.items():
		a = fire_a.get(tid)
		if not a or dt <= 0:
			continue
		u = (b[2] - a[2]) * 100.0 / clk / dt
		s = (b[3] - a[3]) * 100.0 / clk / dt
		randuri.append((u + s, "%s%-8d %-16s %s %5.1f%% = %5.1f + %5.1f" % ("*" if tid == pid else " ", tid, b[0][:16],
			b[1], u + s, u, s)))
	randuri.sort(key=lambda x: -x[0])
	r += [x[1] for x in randuri[:MAX_RANDURI]]
	r.append("")
	r.append("-- procesele (procent dintr-un nucleu, tot sistemul)")
	rp = []
	for pid_, b in (procese_b or {}).items():
		a = (procese_a or {}).get(pid_)
		if not a or dt <= 0 or a[0] != b[0]:
			continue
		t = ((b[2] + b[3]) - (a[2] + a[3])) * 100.0 / clk / dt
		if t > 0:
			rp.append((t, "%-8d %-16s %5.1f%%" % (pid_, nume_proces(b[0])[:16], t)))
	rp.sort(key=lambda x: -x[0])
	r += [x[1] for x in rp[:MAX_RANDURI]] or ["(niciun proces cu timp in fereastra)"]
	r.append("")
	r.append("-- citirile starii tunerelor (lib/dvb/hdscitirifrontend.h), pe secunda")
	if fe_a and fe_b and dt > 0:
		d = dict((k, _dif32(fe_a, fe_b, k)) for k in ("cereri", "din_memorie", "ioctl", "ioctl_direct", "erori", "us_ioctl"))
		if None not in d.values():
			r.append("cereri=%.1f din_memorie=%.1f ioctl=%.1f directe=%.1f erori=%d" % (d["cereri"] / dt,
				d["din_memorie"] / dt, d["ioctl"] / dt, d["ioctl_direct"] / dt, d["erori"]))
			r.append("timp_in_ioctl=%.1f ms/s (%.1f%% dintr-un nucleu) cost_mediu=%s us ttl_ms=%s/%s" % (
				d["us_ioctl"] / 1000.0 / dt, d["us_ioctl"] / 10000.0 / dt,
				int(d["us_ioctl"] / d["ioctl"]) if d["ioctl"] else "-", fe_b.get("ttl_ms"), fe_b.get("ttl_lent_ms")))
	else:
		r.append("contoarele nu se pot citi")
	r.append("")
	r.append("-- intreruperile care au crescut (pe secunda)")
	for k, nume, d in cresteri_intreruperi(intr_a, intr_b):
		r.append("%s %s %.1f" % (k, nume, d / dt if dt > 0 else 0))
	r.append("")
	sus, lant = clasamente(stive)
	r.append("-- stiva firului principal: %d esantioane (cadrul de sus)" % len(stive))
	r += ["%3d %s" % (n, k) for k, n in sus[:MAX_RANDURI]]
	r.append("")
	r.append("-- stiva firului principal (primele %d cadre)" % MAX_STIVA)
	r += ["%3d %s" % (n, k) for k, n in lant[:MAX_RANDURI]]
	return "\n".join(r) + "\n"


# ---------------------------------------------------------------- pe receptor

def _citeste(cale, maxim=262144):
	try:
		with open(cale, "r", errors="replace") as f:
			return f.read(maxim)
	except (IOError, OSError):
		return ""


def procese():
	"""{pid: (nume, stare, utime, stime)} ale tuturor proceselor"""
	rez = {}
	try:
		nume = os.listdir("/proc")
	except OSError:
		return rez
	for p in nume:
		if p.isdigit():
			v = fir_din_stat(_citeste("/proc/%s/stat" % p, 4096))
			if v:
				rez[int(p)] = v
	return rez


def fire(pid):
	rez = {}
	baza = "/proc/%d/task" % pid
	try:
		tid_uri = os.listdir(baza)
	except OSError:
		return rez
	for t in tid_uri:
		if t.isdigit():
			v = fir_din_stat(_citeste("%s/%s/stat" % (baza, t), 4096))
			if v:
				rez[int(t)] = v
	return rez


def _contoare_frontend():
	try:
		import enigma
		d = enigma.getFrontendReadCounts()
		return d if isinstance(d, dict) else None
	except Exception:
		return None


def _instantaneu(pid):
	return {"t": time.monotonic(), "fire": fire(pid), "procese": procese(),
		"intr": intreruperi(_citeste("/proc/interrupts")), "stat": _citeste("/proc/stat", 4096), "fe": _contoare_frontend()}


class Urmaritor(object):
	def __init__(self, pid=None):
		self.pid = pid or os.getpid()
		self.prag = Prag()
		self.semnal = None
		self.fisier = None
		self.oprit = False

	def inregistreaza(self):
		"""faulthandler pe SEMNAL, cu fisierul lui (din firul principal, la pornire)"""
		import faulthandler
		import signal
		self.semnal = int(signal.SIGRTMIN) + SEMNAL_PESTE_RTMIN
		self.fisier = open(FISIER_STIVE, "w")
		faulthandler.register(self.semnal, file=self.fisier, all_threads=True, chain=False)

	def porneste(self):
		import threading
		self.ident = threading.main_thread().ident
		threading.Thread(target=self._bucla, name="hds-procesor-raport", daemon=True).start()

	def _bucla(self):
		while not self.oprit:
			time.sleep(PAS_S)
			v = fir_din_stat(_citeste("/proc/%d/task/%d/stat" % (self.pid, self.pid), 4096))
			if not v:
				continue
			if self.prag.adauga(time.monotonic(), v[2] + v[3]):
				if os.path.exists(SEMN_FACUT):
					self.oprit = True
					return
				try:
					self.culege_si_trimite()
				except Exception as e:
					print("[HdsProcesorRaport] culegerea: %s" % e)
				self.oprit = True

	def _esantioneaza(self):
		"""ESANTIOANE semnale de la un proces separat, la ore reale, in FEREASTRA_S secunde"""
		import subprocess
		pas_us = int(FEREASTRA_S * 1000000 / ESANTIOANE)
		cmd = ("i=0; while [ $i -lt %d ]; do kill -%d %d 2>/dev/null || exit 0; usleep %d 2>/dev/null || "
			"sleep %.2f 2>/dev/null || sleep 1; i=$((i+1)); done" % (ESANTIOANE, self.semnal, self.pid, pas_us,
			pas_us / 1000000.0))
		p = subprocess.Popen(["/bin/sh", "-c", cmd], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
			stderr=subprocess.DEVNULL, close_fds=True)
		try:
			p.wait(timeout=FEREASTRA_S * 6)
		except Exception:
			p.kill()

	def culege_si_trimite(self):
		import subprocess
		with open(SEMN_FACUT, "w") as f:
			f.write("%d\n" % int(time.time()))
		self.fisier.seek(0)
		self.fisier.truncate()
		self.fisier.flush()
		a = _instantaneu(self.pid)
		self._esantioneaza()
		b = _instantaneu(self.pid)
		self.fisier.flush()
		stive = stive_fir(_citeste(FISIER_STIVE, 2 * 1024 * 1024), self.ident)
		text = text_raport(a["fire"], b["fire"], b["t"] - a["t"], a["intr"], b["intr"], a["stat"], b["stat"], a["fe"],
			b["fe"], stive, self.pid, self.prag.parte, procese_a=a["procese"], procese_b=b["procese"])
		with open(FISIER_RAPORT, "w") as f:
			f.write(text)
		try:
			os.remove(FISIER_STIVE)
		except OSError:
			pass
		if os.path.isfile(PROGRAM):
			env = dict(os.environ, HDS_RAPORT_MOTIV="procesor", HDS_RAPORT_DECLANSARE="automata",
				HDS_RAPORT_PROCESOR=FISIER_RAPORT)
			subprocess.run(["/bin/sh", PROGRAM, "raport", "manual"], env=env, stdin=subprocess.DEVNULL,
				stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
		print("[HdsProcesorRaport] raportul de procesor scris (%d esantioane)" % len(stive))


def porneste():
	"""din mytest.py, pe firul principal, o data pe proces"""
	global _urmaritor
	if _urmaritor is not None:
		return
	u = Urmaritor()
	u.inregistreaza()
	u.porneste()
	_urmaritor = u
