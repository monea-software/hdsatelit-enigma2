# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsCeas.py: ceasul receptorului (NTP, ora din transponder, fake-hwclock).
#
# De ce: fara ceas hardware, ceasul pleca la fiecare pornire de la o ora veche si ramanea asa (ore in urma).
#   - Receptorul nu are ceas hardware (RTC): la pornire ora vine din /etc/fake-hwclock.data, adica ultima ora salvata. Ea se
#     salva numai la oprirea curata (rc0/rc6), iar dupa o scoatere din priza ramanea ora de la construirea imaginii.
#   - NTP nu mergea deloc: nimic nu il pornea, iar ecranul „Data si ora” chema `ntpdate`, care nu e in imagine.
#   - Ora din transponder nu muta ceasul: lib/dvb/dvbtime.cpp credea buna ora din fake-hwclock (e dupa 2004) si salva
#     diferenta drept „corectie”. Reparat in C++ (m_time_confirmed, hdsConfirmTime).
#
# Ce face acest modul:
#   1. Setarile (config.hds_time; aceleasi chei ca in vechiul Screens/Time.py, ca setarile salvate sa ramana):
#        sync_mode  „auto” (implicit): Internet (NTP), iar cat NTP nu a reusit in ultimele NTP_RECENT_S secunde, ora din
#                   transponder; „ntp”: numai Internet; „dvb”: numai transponderul. „manual” (vechi, nu facea nimic) nu
#                   mai exista: o valoare salvata „manual” devine „auto” (ConfigSelection.setValue).
#        ntp_server serverul NTP.
#   2. Sincronizarea NTP la pornire si periodic, FARA sa opreasca pornirea: procesul (ntpdate daca exista, altfel ntpd din
#      BusyBox cu -n -q) ruleaza prin eConsoleAppContainer, adica in afara firului principal, si e oprit dupa
#      TIMP_MAXIM_NTP_S secunde (ntpd -q nu iese niciodata singur fara server). Fara retea: incercari din ce in ce mai
#      rare (INCERCARI_S), apoi la 15 minute; dupa o reusita, la DUPA_SUCCES_S.
#   3. Dupa o reusita: C++ afla ca ora e buna (eDVBLocalTimeHandler.hdsConfirmTime: primul transponder nu o mai muta,
#      EPG-ul afla), ora se salveaza in fake-hwclock, iar in „auto” ora din transponder se opreste cat NTP e proaspat.
#   4. fake-hwclock salvat periodic (SALVARE_S), dupa fiecare sincronizare si la iesirea enigma2 (mytest.py), numai cand
#      ora e sigura (vezi mai jos), in formatul scriptului din OE (`date -u '+%Y-%m-%d %H:%M:%S'`), atomic (.nou + fsync
#      + rename). Fara „force” nu se scrie o ora mai veche decat cea salvata (ca `fake-hwclock save`); ora sigura se
#      scrie oricum.
#   5. Starea pentru ecranul „Data si ora” (Screens/Time.py) si pagina web /ceas (HdsWebControl/ceas_web.py).
#
# Ora sigura si ora provizorie: ora de la UN SINGUR transponder e PROVIZORIE (lib/dvb/dvbtime.cpp,
# hdsceas::decide); devine SIGURA numai prin NTP, RTC sau doua multiplexuri diferite de acord. De aici:
#   - fake-hwclock (si ORA SIGURA SALVATA, CALE_ORA_SIGURA, citita de C++ la pornire drept limita de jos) se scriu NUMAI
#     cand ora e sigura: periodic, la iesire si pe loc la trecerea la ora sigura (semnalul m_timeUpdated). Cat ora e
#     provizorie nu se scrie nimic. Imaginea nu mai are scriptul de oprire /etc/rc0.d si rc6.d/K25fake-hwclock, care
#     scria orice ora (meta-local, fake-hwclock.bbappend), deci salvarile de aici sunt singurele. Ora sigura se scrie
#     „fortat” (e mai buna decat orice ora salvata inainte, chiar din viitor, de exemplu una pusa cu mana cu
#     `fake-hwclock save` sau ramasa de la o imagine mai veche).
#   - starea (provizorie, sigura si de unde) se vede pe ecranul „Data si ora” si in /ceas.
#
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC il folosesc direct.

import os
import time

CALE_FAKE_HWCLOCK = "/etc/fake-hwclock.data"
CALE_ORA_SIGURA = "/etc/hds-ora-sigura.data"   # aceeasi cale ca HDS_ORA_SIGURA din lib/dvb/dvbtime.cpp
FORMAT_FAKE_HWCLOCK = "%Y-%m-%d %H:%M:%S"

# starile orei, ca in lib/dvb/dvbtime.h (hdsceas::Stare, eDVBLocalTimeHandler.hdsTimeState())
NECUNOSCUTA, SALVATA, PROVIZORIE, SIGURA_INTERNET, SIGURA_TRANSPONDERE, SIGURA_RTC = range(6)
NUME_STARI = ("necunoscuta", "salvata", "provizorie", "sigura_internet", "sigura_transpondere", "sigura_rtc")

PROGRAME_NTPDATE = ("/usr/bin/ntpdate", "/usr/sbin/ntpdate")
PROGRAME_NTPD = ("/usr/sbin/ntpd", "/usr/bin/ntpd", "/sbin/ntpd", "/bin/ntpd")

PRIMA_INCERCARE_S = 5            # dupa pornirea enigma2 (reteaua poate veni mai tarziu: urmeaza INCERCARI_S)
INCERCARI_S = (20, 40, 80, 160, 300, 600, 900)   # dupa esecuri la rand; apoi la fiecare 900 s
DUPA_SUCCES_S = 3600             # sincronizarea periodica
NTP_RECENT_S = 3 * 3600          # in „auto”, ora din transponder sta oprita cat ultima reusita NTP e mai noua de atat
TIMP_MAXIM_NTP_S = 30            # procesul NTP se opreste dupa atat
SALVARE_S = 30 * 60              # fake-hwclock salvat periodic

MODURI = ("auto", "ntp", "dvb")
MOD_IMPLICIT = "auto"
SERVERE = (
	("ro.pool.ntp.org", "ro.pool.ntp.org (România)"),
	("europe.pool.ntp.org", "europe.pool.ntp.org (Europa)"),
	("pool.ntp.org", "pool.ntp.org (Global)"),
	("time.cloudflare.com", "time.cloudflare.com"),
	("time.google.com", "time.google.com"),
)
SERVER_IMPLICIT = "ro.pool.ntp.org"


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


def _jurnal(text):
	print("[HdsCeas] %s" % text)


def textMod(mod):
	return {
		"auto": _("Internet, apoi transponder"),
		"ntp": _("Numai Internet (NTP)"),
		"dvb": _("Numai transponder (satelit, cablu)"),
	}.get(mod, mod)


def alegeriMod():
	return [(m, textMod(m)) for m in MODURI]


def serverValid(server):
	"""Un nume de gazda sau o adresa, fara nimic altceva: merge ca un singur argument, fara interpretor de comenzi."""
	import re
	return bool(server) and re.match(r"^[A-Za-z0-9][A-Za-z0-9.:\-]{0,252}$", server) is not None


def initConfig():
	"""config.hds_time.sync_mode si .ntp_server (aceleasi chei ca inainte). Se poate chema de oricate ori."""
	from Components.config import config
	if "hds_time" in config.content.items:
		return
	from Components.config import ConfigSubsection, ConfigSelection
	config.hds_time = ConfigSubsection()
	config.hds_time.sync_mode = ConfigSelection(default=MOD_IMPLICIT, choices=alegeriMod())
	config.hds_time.ntp_server = ConfigSelection(default=SERVER_IMPLICIT, choices=list(SERVERE))


def _config():
	from Components.config import config
	initConfig()
	return config.hds_time


# ---------------------------------------------------------------- fake-hwclock

def salveazaCeas(acum=None, cale=None, forteaza=False):
	"""Scrie ora de acum (UTC) in fake-hwclock, in formatul scriptului din OE, atomic. Fara `forteaza` nu scrie o ora
	mai veche decat cea deja salvata (ca `fake-hwclock save`: ora salvata e limita de jos a orei reale la urmatoarea
	pornire). Intoarce (scris, motiv)."""
	cale = cale or CALE_FAKE_HWCLOCK
	acum = time.time() if acum is None else acum
	text = time.strftime(FORMAT_FAKE_HWCLOCK, time.gmtime(acum))
	if not forteaza:
		vechi = citesteCeasSalvat(cale)
		if vechi is not None and vechi > acum:
			return False, "ora salvata (%s) e dupa ora de acum" % time.strftime(FORMAT_FAKE_HWCLOCK, time.gmtime(vechi))
	nou = cale + ".nou"
	try:
		with open(nou, "w") as f:
			f.write(text + "\n")
			f.flush()
			os.fsync(f.fileno())
		os.replace(nou, cale)
	except (OSError, IOError) as e:
		try:
			os.remove(nou)
		except OSError:
			pass
		return False, str(e)
	try:
		fd = os.open(os.path.dirname(cale) or ".", os.O_RDONLY)
		try:
			os.fsync(fd)
		finally:
			os.close(fd)
	except (OSError, AttributeError):
		pass
	return True, text


def citesteCeasSalvat(cale=None):
	"""Ora din fake-hwclock (secunde UTC) sau None."""
	import calendar
	cale = cale or CALE_FAKE_HWCLOCK
	try:
		with open(cale, "r") as f:
			text = f.read(64).strip()
		return calendar.timegm(time.strptime(text, FORMAT_FAKE_HWCLOCK))
	except (OSError, IOError, ValueError):
		return None


# ---------------------------------------------------------------- sincronizarea

def comandaNtp(server, exista=None):
	"""argv pentru eConsoleAppContainer.execute (programul, argv0, argumente) sau None cand nu exista niciun program.
	ntpdate: -b muta ceasul dintr-o data, -u port neprivilegiat, -t 5 secunde pe raspuns. ntpd din BusyBox: -n in
	prim-plan, -q iese dupa ce a pus ora (la o diferenta mare o muta dintr-o data), -p serverul."""
	exista = exista or (lambda cale: os.access(cale, os.X_OK))
	for p in PROGRAME_NTPDATE:
		if exista(p):
			return (p, p, "-b", "-u", "-t", "5", server)
	for p in PROGRAME_NTPD:
		if exista(p):
			return (p, p, "-n", "-q", "-p", server)
	return None


class Executor(object):
	"""porneste(argv, la_final) -> obiect cu opreste(); la_final(cod) vine pe firul enigma2. Fara interpretor de comenzi."""

	def porneste(self, argv, la_final):
		from enigma import eConsoleAppContainer
		c = eConsoleAppContainer()

		def inchis(cod):
			del c.appClosed[:]
			la_final(cod)

		c.appClosed.append(inchis)
		if c.execute(*argv):
			del c.appClosed[:]
			return None
		return c


def _timerEnigma():
	from enigma import eTimer
	return eTimer()


def _handler():
	try:
		from enigma import eDVBLocalTimeHandler
		return eDVBLocalTimeHandler.getInstance()
	except Exception:
		return None


def stareOra(h):
	"""Starea orei din C++ (NECUNOSCUTA .. SIGURA_RTC) sau None cand nu se poate afla."""
	if h is None:
		return None
	try:
		cod = int(h.hdsTimeState())
		return cod if 0 <= cod < len(NUME_STARI) else None
	except Exception:
		return None


def oraSigura(h):
	"""Ora e sigura (NTP, doua transpondere sau RTC)? Fara raspuns de la C++: nu (nu se scrie nimic)."""
	cod = stareOra(h)
	if cod is not None:
		return cod >= SIGURA_INTERNET
	try:
		return h is not None and bool(h.hdsTimeConfirmed())
	except Exception:
		return False


def salveazaOraSigura(acum=None, cale_ceas=None, cale_sigura=None):
	"""Ora de acum, stiuta sigura, in fake-hwclock (ceasul de la pornire) si in CALE_ORA_SIGURA (limita de jos a lui
	C++ la pornire), amandoua „fortat”. Intoarce (scris, motiv)."""
	acum = time.time() if acum is None else acum
	scris1, motiv1 = salveazaCeas(acum, cale_ceas or CALE_FAKE_HWCLOCK, forteaza=True)
	scris2, motiv2 = salveazaCeas(acum, cale_sigura or CALE_ORA_SIGURA, forteaza=True)
	if scris1 and scris2:
		return True, motiv1
	return False, motiv1 if not scris1 else motiv2


class Sincronizator(object):
	def __init__(self, fabrica_timer=None, executor=None, mono=None, perete=None, handler=None, cale_ceas=None,
			exista=None, config=None, cale_sigura=None):
		self.fabrica_timer = fabrica_timer or _timerEnigma
		self.executor = executor or Executor()
		self.mono = mono or time.monotonic
		self.perete = perete or time.time
		self._handler = handler
		self.cale_ceas = cale_ceas or CALE_FAKE_HWCLOCK
		# langa fake-hwclock (pe receptor: /etc/hds-ora-sigura.data, CALE_ORA_SIGURA)
		self.cale_sigura = cale_sigura or os.path.join(os.path.dirname(self.cale_ceas) or ".",
			os.path.basename(CALE_ORA_SIGURA))
		self.exista = exista
		self._cfg = config
		self.proces = None
		self.inceput = None          # (perete, mono) la pornirea procesului
		self.expirat = False
		self.esecuri = 0
		self.ntp_reusit_mono = None
		self.dvb_pornit = None
		self.stare_vazuta = None     # ultima stare a orei vazuta (pentru salvarea pe loc la trecerea la ora sigura)
		self.nesalvat_scris = None   # starea pentru care s-a scris deja „nesalvat” in jurnal
		self.in_confirmare = False
		self.ultima = {"rezultat": "niciuna", "ora": 0, "server": "", "program": "", "pas_s": 0.0, "motiv": ""}
		self.timerNtp = self.fabrica_timer()
		self.timerNtp.callback.append(self.sincronizeaza)
		self.timerLimita = self.fabrica_timer()
		self.timerLimita.callback.append(self._limita)
		self.timerSalvare = self.fabrica_timer()
		self.timerSalvare.callback.append(self._salvarePeriodica)
		self.timerSursa = self.fabrica_timer()
		self.timerSursa.callback.append(self.aplicaSursa)
		self.timerSursa.callback.append(self.verificaStare)

	# ---- setari ----

	def cfg(self):
		return self._cfg if self._cfg is not None else _config()

	def mod(self):
		v = self.cfg().sync_mode.value
		return v if v in MODURI else MOD_IMPLICIT

	def server(self):
		return (self.cfg().ntp_server.value or "").strip()

	def handler(self):
		return self._handler if self._handler is not None else _handler()

	# ---- pornire ----

	def porneste(self):
		c = self.cfg()
		try:
			c.sync_mode.addNotifier(self._modSchimbat, initial_call=False)
			c.ntp_server.addNotifier(self._serverSchimbat, initial_call=False)
		except (AttributeError, TypeError):
			pass
		self.aplicaSursa()
		if self.mod() in ("auto", "ntp"):
			self.timerNtp.start(PRIMA_INCERCARE_S * 1000, True)
		self.timerSalvare.start(SALVARE_S * 1000, False)
		# in „auto”, ora din transponder porneste singura cand NTP nu mai e proaspat; tot aici, starea orei (rezerva
		# pentru semnalul de mai jos)
		self.timerSursa.start(10 * 60 * 1000, False)
		# trecerea la ora sigura (doua transpondere, NTP) se salveaza pe loc: C++ trimite m_timeUpdated
		h = self.handler()
		try:
			h.m_timeUpdated.get().append(self._laOraNoua)
		except Exception as e:
			_jurnal("m_timeUpdated: %r" % (e,))
		self.verificaStare()
		_jurnal("pornit: sursa %s, server %s, ora %s" % (self.mod(), self.server(), self.numeStare()))

	def _modSchimbat(self, element=None):
		self.aplicaSursa()
		self.timerNtp.stop()
		if self.mod() in ("auto", "ntp") and self.proces is None:
			self.timerNtp.start(1000, True)

	def _serverSchimbat(self, element=None):
		self._modSchimbat()

	def ntpProaspat(self):
		return self.ntp_reusit_mono is not None and self.mono() - self.ntp_reusit_mono < NTP_RECENT_S

	def aplicaSursa(self):
		"""Ora din transponder: pornita in „dvb”, oprita in „ntp”; in „auto” pornita cat NTP nu a reusit de curand."""
		mod = self.mod()
		dvb = mod == "dvb" or (mod == "auto" and not self.ntpProaspat())
		h = self.handler()
		if h is not None:
			try:
				h.setUseDVBTime(dvb)
			except Exception as e:
				_jurnal("setUseDVBTime: %r" % (e,))
		if dvb != self.dvb_pornit:
			_jurnal("ora din transponder %s" % ("pornita" if dvb else "oprita"))
		self.dvb_pornit = dvb

	# ---- NTP ----

	def inCurs(self):
		return self.proces is not None

	def sincronizeaza(self):
		"""O incercare NTP acum (si din „Sincronizeaza acum”). Intoarce (pornit, mesaj)."""
		if self.proces is not None:
			return True, _("Sincronizarea este deja în curs.")
		if self.mod() == "dvb":
			return False, _("Sursa aleasă este numai transponderul: ora se ia la acordul pe un canal.")
		server = self.server()
		if not serverValid(server):
			self._rezultat("esuat", server, "", _("Numele serverului NTP nu este valid."))
			return False, self.ultima["motiv"]
		argv = comandaNtp(server, self.exista)
		if argv is None:
			self._rezultat("esuat", server, "", _("Imaginea nu are niciun program NTP (ntpdate sau ntpd)."))
			self._programeaza(False)
			return False, self.ultima["motiv"]
		self.timerNtp.stop()
		self.expirat = False
		self.inceput = (self.perete(), self.mono(), server, os.path.basename(argv[0]))
		proces = self.executor.porneste(argv, self._laSfarsit)
		if proces is None:
			self.inceput = None
			self._rezultat("esuat", server, os.path.basename(argv[0]), _("Programul NTP nu a pornit."))
			self._programeaza(False)
			return False, self.ultima["motiv"]
		self.proces = proces
		self.timerLimita.start(TIMP_MAXIM_NTP_S * 1000, True)
		return True, _("Se sincronizează ora cu %s.") % server

	def _limita(self):
		"""Procesul NTP a trecut de TIMP_MAXIM_NTP_S (ntpd -q fara server nu iese niciodata singur).
		eConsoleAppContainer.kill() (lib/base/console.cpp) inchide tevile inainte ca procesul sa iasa, deci nu mai trimite
		niciodata appClosed si nici nu face waitpid (proces zombi): ar ramane „in curs” pe veci, fara reincercari. De aceea:
		  1. SIGKILL direct procesului (grupului lui, ca in console.cpp), cu tevile deschise: tevile se inchid, containerul
		     face waitpid si trimite appClosed, iar _laSfarsit ruleaza pe calea obisnuita (fara zombi);
		  2. daca appClosed nu vine in 5 s (sau pid-ul nu se stie), kill() pe container si _laSfarsit(-1) chemat de aici.
		Un appClosed intarziat dupa pasul 2 nu mai face nimic (_laSfarsit iese cand inceput e None)."""
		if self.proces is None:
			return
		if not self.expirat:
			self.expirat = True
			try:
				pid = int(self.proces.getPID())
			except Exception:
				pid = -1
			if pid > 0:
				import signal
				sigkill = getattr(signal, "SIGKILL", 9)
				try:
					os.killpg(pid, sigkill)
				except (OSError, AttributeError):
					try:
						os.kill(pid, sigkill)
					except OSError as e:
						_jurnal("SIGKILL procesului NTP %d: %s" % (pid, e))
				self.timerLimita.start(5000, True)
				return
		try:
			self.proces.kill()
		except Exception as e:
			_jurnal("oprirea procesului NTP: %r" % (e,))
		self._laSfarsit(-1)

	def _laSfarsit(self, cod):
		self.timerLimita.stop()
		self.proces = None
		inceput = self.inceput
		self.inceput = None
		if inceput is None:
			return
		p0, m0, server, program = inceput
		pas = (self.perete() - p0) - (self.mono() - m0)
		if cod == 0 and not self.expirat:
			self.ntp_reusit_mono = self.mono()
			self._rezultat("reusit", server, program, "", pas)
			h = self.handler()
			if h is not None and hasattr(h, "hdsConfirmTime"):
				self.in_confirmare = True     # m_timeUpdated vine chiar din hdsConfirmTime: salvarea e mai jos, o data
				try:
					h.hdsConfirmTime()
				except Exception as e:
					_jurnal("hdsConfirmTime: %r" % (e,))
				finally:
					self.in_confirmare = False
			# ora NTP e sigura: fake-hwclock si ora sigura salvata, „fortat”
			scris, motiv = salveazaOraSigura(self.perete(), self.cale_ceas, self.cale_sigura)
			if not scris:
				_jurnal("fake-hwclock: %s" % motiv)
			self.stare_vazuta = stareOra(h)
			self.aplicaSursa()
			_jurnal("NTP reusit (%s, %s), ceasul mutat cu %.1f s" % (server, program, pas if abs(pas) >= 0.05 else 0.0))
			self._programeaza(True)
		else:
			motiv = (_("Serverul nu a răspuns în %d de secunde (fără rețea sau fără acces la Internet).") % TIMP_MAXIM_NTP_S
				if self.expirat else _("Programul NTP a ieșit cu codul %s.") % cod)
			self._rezultat("esuat", server, program, motiv)
			_jurnal("NTP nereusit (%s, %s): %s" % (server, program, "timp depasit" if self.expirat else "cod %s" % cod))
			self._programeaza(False)

	def _rezultat(self, rezultat, server, program, motiv, pas=0.0):
		self.ultima = {"rezultat": rezultat, "ora": self.perete(), "server": server, "program": program, "pas_s": pas,
			"motiv": motiv}

	def _programeaza(self, reusit):
		if self.mod() not in ("auto", "ntp"):
			return
		if reusit:
			self.esecuri = 0
			secunde = DUPA_SUCCES_S
		else:
			secunde = INCERCARI_S[min(self.esecuri, len(INCERCARI_S) - 1)]
			self.esecuri += 1
		self.timerNtp.start(secunde * 1000, True)

	# ---- fake-hwclock (numai ora sigura) ----

	def stareCod(self):
		return stareOra(self.handler())

	def numeStare(self):
		cod = self.stareCod()
		return NUME_STARI[cod] if cod is not None else "necunoscuta (fara C++)"

	def oraSigura(self):
		return oraSigura(self.handler())

	def _salveazaSigur(self, cand):
		"""Scrie ora de acum (sigura) in fake-hwclock si in ora sigura salvata. Intoarce True daca a scris."""
		scris, motiv = salveazaOraSigura(self.perete(), self.cale_ceas, self.cale_sigura)
		if not scris:
			_jurnal("%s: fake-hwclock nesalvat: %s" % (cand, motiv))
		self.nesalvat_scris = None
		return scris

	def _nesalvat(self, cand):
		"""Ora nu e sigura: nu se scrie nimic; un rand in jurnal o data pe stare."""
		cod = self.stareCod()
		if self.nesalvat_scris != cod:
			self.nesalvat_scris = cod
			_jurnal("%s: fake-hwclock nescris, ora nu e sigura (%s)" % (cand, self.numeStare()))

	def verificaStare(self):
		"""La trecerea la ora sigura (sau la schimbarea sursei ei), ora se salveaza pe loc."""
		cod = self.stareCod()
		inainte = self.stare_vazuta
		self.stare_vazuta = cod
		if cod is not None and cod >= SIGURA_INTERNET and cod != inainte:
			_jurnal("ora sigura (%s): salvata" % NUME_STARI[cod])
			self._salveazaSigur("trecerea la ora sigura")

	def _laOraNoua(self):
		"""Din C++ (m_timeUpdated), pe firul enigma2, dupa ce ceasul sau starea lui s-a schimbat."""
		if self.in_confirmare:
			return
		try:
			self.verificaStare()
		except Exception as e:
			_jurnal("verificaStare: %r" % (e,))

	def _salvarePeriodica(self):
		if self.oraSigura():
			self._salveazaSigur("salvarea periodica")
		else:
			self._nesalvat("salvarea periodica")

	def laOprire(self):
		for t in (self.timerNtp, self.timerLimita, self.timerSalvare, self.timerSursa):
			try:
				t.stop()
			except Exception:
				pass
		if self.proces is not None:
			try:
				self.proces.kill()
			except Exception:
				pass
		if self.oraSigura():
			if self._salveazaSigur("la oprire"):
				_jurnal("la oprire: ora sigura salvata (%s)" % self.numeStare())
		else:
			self.nesalvat_scris = None
			self._nesalvat("la oprire")

	# ---- starea, pentru ecran si web ----

	def stare(self):
		h = self.handler()
		cod = stareOra(h)
		confirmata = None
		if cod is not None:
			confirmata = cod >= SIGURA_INTERNET
		else:
			try:
				if h is not None and hasattr(h, "hdsTimeConfirmed"):
					confirmata = bool(h.hdsTimeConfirmed())
			except Exception:
				confirmata = None
		u = dict(self.ultima)
		salvat = citesteCeasSalvat(self.cale_ceas)
		return {
			"mod": self.mod(),
			"mod_text": textMod(self.mod()),
			"server": self.server(),
			"in_curs": self.inCurs(),
			"confirmata": confirmata,
			"stare_cod": cod,
			"stare_ceas": NUME_STARI[cod] if cod is not None else "",
			"transponder_pornit": bool(self.dvb_pornit),
			"ultima": u,
			"ultima_text": textUltima(u, self.perete()),
			"sursa_text": textSursa(cod, u),
			"salvat": salvat or 0,
			"sigura_salvata": citesteCeasSalvat(self.cale_sigura) or 0,
		}


def textDurataScurta(secunde):
	secunde = abs(int(round(secunde)))
	if secunde < 60:
		return _("%d s") % secunde
	minute = secunde // 60
	if minute < 60:
		return _("%d min") % minute
	ore, minute = divmod(minute, 60)
	if ore < 48:
		return _("%d h %d min") % (ore, minute)
	return _("%d zile") % (ore // 24)


def textUltima(u, acum):
	if u.get("rezultat") == "niciuna":
		return _("Încă nicio sincronizare prin Internet de la pornire.")
	cand = time.strftime("%H:%M", time.localtime(u.get("ora") or acum))
	if u.get("rezultat") == "reusit":
		pas = u.get("pas_s") or 0.0
		text = _("Sincronizat prin Internet la %s (%s).") % (cand, u.get("server", ""))
		if abs(pas) >= 1:
			text += " " + (_("Ceasul a fost mutat înainte cu %s.") if pas > 0 else _("Ceasul a fost mutat înapoi cu %s.")) % \
				textDurataScurta(pas)
		return text
	return _("Ultima încercare prin Internet, la %s, nu a reușit: %s") % (cand, u.get("motiv", ""))


def textStare(cod):
	"""Starea orei pe ecranul „Data si ora” si in /ceas."""
	if cod == SIGURA_RTC:
		return _("Ora sigură (ceasul receptorului)")
	if cod == SIGURA_TRANSPONDERE:
		return _("Ora sigură (două transpondere)")
	if cod == SIGURA_INTERNET:
		return _("Ora sigură (Internet)")
	if cod == PROVIZORIE:
		return _("Ora provizorie (de la un transponder)")
	if cod == SALVATA:
		return _("Ora nu este încă sigură: vine din ultima oră salvată. Primul canal o pune provizoriu, iar Internetul "
			"sau un al doilea transponder o confirmă.")
	if cod == NECUNOSCUTA:
		return _("Ora nu este cunoscută încă: se ia de la primul canal sau prin Internet.")
	return ""


def textSursa(cod, u):
	if cod is not None:
		return textStare(cod)
	if u.get("rezultat") == "reusit":    # fara C++ (probe pe PC): numai ce stie Python
		return textStare(SIGURA_INTERNET)
	return ""


# ---------------------------------------------------------------- obiectul unic si ce cheama mytest.py, ecranul si web-ul

_unic = [None]


def sincronizator():
	if _unic[0] is None:
		_unic[0] = Sincronizator()
	return _unic[0]


def porneste():
	"""Din mytest.py, dupa pornirea sesiunii."""
	initConfig()
	sincronizator().porneste()


def laOprire():
	"""Din mytest.py, dupa iesirea din bucla principala. Ora se salveaza numai cand e sigura."""
	if _unic[0] is not None:
		_unic[0].laOprire()
	elif oraSigura(_handler()):
		salveazaOraSigura()
	else:
		_jurnal("la oprire: fake-hwclock nescris, ora nu e sigura")


def stare():
	return sincronizator().stare()


def sincronizeazaAcum():
	return sincronizator().sincronizeaza()


# ---------------------------------------------------------------- fusul orar (acelasi ca in ecranul „Data si ora”)

def fusuri():
	"""Numele fusurilor orare, ca in ecranul „Data si ora” (config.timezone.val, din /etc/timezone.xml)."""
	try:
		from Components.config import config
		return [c for c in config.timezone.val.choices if c]
	except Exception:
		return []


def fusCurent():
	try:
		from Components.config import config
		return config.timezone.val.value
	except Exception:
		return ""


def seteaza(mod=None, server=None, fus=None):
	"""Schimba si salveaza setarile ceasului (web). Intoarce (reusit, mesaj). O valoare straina nu schimba nimic."""
	from Components.config import config, configfile
	c = _config()
	if mod is not None and mod not in MODURI:
		return False, _("Sursa aleasă nu este una din cele permise.")
	if server is not None and server not in [s[0] for s in SERVERE]:
		return False, _("Serverul NTP ales nu este unul din cele permise.")
	if fus is not None:
		lista = fusuri()
		if fus not in lista:
			return False, _("Fusul orar ales nu există pe acest receptor.")
	if fus is not None and fus != config.timezone.val.value:
		config.timezone.val.value = fus      # notificarea din SetupDevices il aplica pe loc
		config.timezone.val.save()
	if server is not None and server != c.ntp_server.value:
		c.ntp_server.value = server
		c.ntp_server.save()
	if mod is not None and mod != c.sync_mode.value:
		c.sync_mode.value = mod
		c.sync_mode.save()
	configfile.save()
	return True, _("Salvat.")
