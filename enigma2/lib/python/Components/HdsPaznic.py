# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsPaznic.py: legatura dintre enigma2 si paznicul receptorului (hds-watchdog.py, reteta hdsatelit-watchdog).
#
# De ce: la o scanare de mai multi sateliti cu motor paznicul oprea enigma2 la jumatatea ei. Paznicul se uita numai la
# interfata web (/api/statusinfo): daca tacea 60 de secunde, trimitea
# SIGTERM. Interfata web merge pe aceeasi bucla cu enigma2, deci orice operatie lunga de pe firul principal (o mutare de
# motor, un acord greu) o facea sa taca, iar paznicul lua asta drept blocare.
#
# Ce face acest modul (paznicul citeste, nu scrie nimic in enigma2):
#   1. BATAIA: la fiecare BATAIE_S secunde, un eTimer de pe firul principal scrie CALE_BATAIE (/var/run e in RAM pe
#      receptor) cu pid-ul procesului, ceasul monoton (time.monotonic(), adica CLOCK_MONOTONIC, acelasi pentru toate
#      procesele; nu sare cand ora se muta prin NTP sau transponder) si semnul „ocupat”. Daca firul principal
#      se blocheaza, bataia se opreste. E al doilea semn de viata, pe langa interfata web: paznicul reporneste interfata
#      numai cand AMANDOUA tac (sau numai bataia, cand interfata web e oprita din setari), niciodata numai pe tacerea web.
#   2. SEMNUL „OCUPAT”: scanarea (Components/ServiceScan), citirea pistelor (HdsPisteCanale.Actualizare) si rotirea
#      antenei (isRotorMoving, citit la fiecare bataie) spun pana cand (ceas monoton) paznicul sa astepte, chiar daca
#      bataia s-a oprit. Semnul se scrie PE LOC la inceput (nu la urmatoarea bataie), ca sa fie pe disc si cand firul se
#      blocheaza imediat dupa pornire. Cat tine lucrul, fiecare bataie il prelungeste; o inregistrare uitata (lucru
#      oprit fara liber()) cade singura dupa OCUPAT_MAXIM_S.
#   3. SETARILE (config.hds_paznic): paznicul le citeste din /etc/enigma2/settings, unde enigma2 scrie numai valorile
#      schimbate. Valorile implicite de aici sunt aceleasi cu cele din hds-watchdog.py (INTERFATA_IMPLICIT,
#      ASTEPTARE_IMPLICITA_S, ASTEPTARI_PERMISE_S); testul test_paznic_sistem le compara.
#   4. STAREA: paznicul scrie CALE_STARE la fiecare verificare; ecranul „Paznicul receptorului” (Screens/HdsPaznic.py)
#      si pagina web /paznic (HdsWebControl/paznic_web.py) o citesc de aici, cu aceleasi texte.
#   5. REDAREA (nivelul 5 al paznicului: decodorul video care nu mai porneste din lipsa de memorie in
#      nucleu): fiecare bataie scrie si ce reda interfata (redare=tv: un serviciu cu pista video, in afara standby-ului;
#      radio, standby, nimic) si daca o inregistrare merge sau incepe in INREGISTRARE_CURAND_S secunde (inregistrare=1).
#      Paznicul reporneste receptorul pentru decodor numai cu redare=tv si inregistrare=0; cand ele lipsesc sau nu se
#      pot citi (redare= gol, inregistrare=-1) nu reporneste nimic. Tot aici criptat= (1/0, -1 nu se stie) si video=
#      (latimea imaginii decodate, 0 sau -1 fara imagine): le citeste numai raportul pornirii (tools/hds-raport.sh),
#      ca sa deosebeasca un canal TV in clar fara imagine (decodorul tinut de alt program) de unul criptat.
#   6. MEMORIA POZELOR SI A FILMELOR: cand demonul platformei nu si-a putut mapa la pornire
#      memoria prin care driverul video primeste poza posturilor de radio si filmele, paznicul scrie in stare
#      memorie_es=lipsa si memorie_es_cheie=<pid-ul demonului>. enigma2 nu mai scrie atunci in video0 si audio0 (nucleul
#      ar cadea, lib/dvb/hdspazavideo.h), deci poza radio si filmele nu merg pana la repornirea receptorului. Niciun
#      mesaj pe televizor: ecranul si pagina paznicului arata starea ca informatie (stare()["avertisment"]), iar
#      repornirea in standby (punctul 7) o socoteste ca memorie sub prag.
#   7. MEMORIA DECODORULUI (Components/HdsMemorieDriver.py): cea mai mare bucata libera din vmalloc, masurata inainte
#      de esecul de la punctul 6. Bataia tine cea mai mica masuratoare din afara standby-ului si intreaba repornirea in
#      standby (config.hds_paznic.repornire_noapte); stare() da valoarea (memorie_driver) pentru ecran si web. Niciun
#      mesaj pe televizor.
#   8. SETARILE PE DISC: dupa fiecare bataie, setarile salvate in memorie de la ultima scriere (un meniu confirmat,
#      volumul) se scriu in /etc/enigma2/settings (Components/config.py, salveazaSchimbarile), numai cand s-a schimbat
#      ceva; ultimul canal ramane cum e pe disc (il tine Components/HdsCanalTinut.py, dupa 60 s pe ecran). De ce: settings il scrie iesirea curata a enigma2, iar paznicul opreste o interfata care
#      nu mai raspunde cu SIGTERM (bucla twisted nu prinde semnalul, deci procesul moare pe loc) si apoi SIGKILL, fara
#      iesirea curata: ce era numai in memorie se pierdea. Firul principal blocat nu mai schimba nimic, deci tot ce s-a
#      salvat inainte de blocaj e deja pe disc (afara de ultimele cel mult BATAIE_S secunde).
#   9. PLUGINURILE EXTERNE CARE TIN FIRUL PRINCIPAL: un plugin al altcuiva face uneori un lucru lung chiar pe firul
#      principal (AJPanel numara toate fisierele unui dosar inainte de
#      copiere; altele cheama opkg cu os.system sau citesc o adresa fara termen). La celelalte imagini interfata sta pana
#      termina; la noi paznicul o oprea dupa 120 s fara bataie. Un fir de supraveghere (SupraveghetorPluginExtern) se
#      uita la fiecare PAS_PLUGIN_EXTERN_S secunde: cand bataia lipseste de PRAG_PLUGIN_EXTERN_S si stiva firului
#      principal trece printr-un plugin extern (HdsPluginExtern.pluginDinCale), pune semnul „ocupat”
#      plugin-extern:<nume> pentru DURATA_PLUGIN_EXTERN_S, cu bataia VECHE in fisier (o tacere ramane tacere), si il
#      prelungeste cat pluginul inca lucreaza, cel mult TOTAL_PLUGIN_EXTERN_S de la ultima bataie. Dupa aceea, sau cand
#      firul principal nu mai e intr-un plugin extern, semnul se scoate si paznicul face ce face la orice blocaj
#      (stivele, repornirea). Prima bataie noua scoate semnul si scrie in jurnal cat a tinut pluginul firul.
#      Afisajul din fata (0.7.4): cat asteapta paznicul, pe afisajul de 4 cifre scrie TEXT_AFISAJ_PLUGIN („bUSY”), din
#      firul de supraveghere (desenul obisnuit al afisajului merge pe firul principal, care e tinut), o data pe tacere;
#      nu in asteptare si nu pe afisajele color (pe ele deseneaza tot firul principal). Prima bataie noua reface
#      afisajul pe loc (HdsAfisaj.actualizeaza). Pluginurile stiute muta oricum lucrul greu pe un fir
#      (Components/HdsFirPluginuri.py), deci la ele firul principal nu ajunge sa fie tinut.
#
# Paznicul placii (watchdog-ul hardware, 60 s) si oprirea la un blocaj de nucleu (fir in stare D) raman mereu pornite;
# setarea de aici priveste numai repornirea interfetei cand nu mai raspunde.
#
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC il folosesc direct.

import os
import sys
import threading
import time


def scrieExceptie(tip, valoare, stiva, cale=None):
	"""Proba completa inainte de PyErr_Print/bsodFatal, independent de inelul C++ de 16 KiB."""
	import traceback
	cale = cale or os.environ.get("HDS_CADERE_PYTHON", "/tmp/hds-cadere.python")
	nou = cale + ".nou"
	try:
		with os.fdopen(os.open(nou, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as f:
			f.write("pid=%d\nparinte=%d\nfel=python\n" % (os.getpid(), os.getppid()))
			try:
				with open("/proc/uptime") as up:
					f.write("uptime=%s\n" % up.read().split()[0])
			except OSError:
				f.write("uptime=necunoscut\n")
			traceback.print_exception(tip, valoare, stiva, file=f)
			f.flush()
			os.fsync(f.fileno())
		os.replace(nou, cale)
		return True
	except Exception:
		return False


def instaleazaExceptii():
	"""PyErr_Print cheama sys.excepthook inainte ca bsodFatal sa trimita SIGKILL."""
	import sys
	vechi = sys.excepthook
	if getattr(vechi, "_hds_exceptie", False):
		return

	def pastreaza(tip, valoare, stiva):
		scrieExceptie(tip, valoare, stiva)
		vechi(tip, valoare, stiva)
	pastreaza._hds_exceptie = True
	sys.excepthook = pastreaza

CALE_BATAIE = "/var/run/hds-paznic.bataie"
CALE_STARE = "/var/run/hds-paznic.stare"
CALE_JURNAL = "/home/root/hds-watchdog.log"

BATAIE_S = 10                   # cat de des scrie bucla principala bataia
DURATA_SCANARE_S = 20 * 60      # cat asteapta paznicul dupa ultima bataie a unei scanari (o mutare de motor, un acord greu)
DURATA_PISTE_S = 10 * 60        # citirea pistelor: pe fiecare transponder asteapta motorul cat merge, apoi 30 s semnalul
DURATA_MOTOR_S = 6 * 60         # o rotire de la un capat la altul, la viteza cea mai mica presupusa de nucleu
DURATA_PLUGINURI_S = 5 * 60     # lista de pluginuri citita din nou: cat poate sta importul unui singur plugin
TOTAL_PLUGINURI_S = 20 * 60     # toata citirea, oricate pluginuri lente ar avea omul; un plugin care nu mai iese se opreste tot
OCUPAT_MAXIM_S = 6 * 3600       # o inregistrare „ocupat” mai veche de atat se socoteste uitata si se scoate
INREGISTRARE_CURAND_S = 10 * 60 # o inregistrare care incepe in atatea secunde conteaza ca inregistrare in curs

# ce reda interfata (redare= in bataie)
REDARE_TV = "tv"
REDARE_RADIO = "radio"
REDARE_STANDBY = "standby"
REDARE_NIMIC = "nimic"
REDARI = (REDARE_TV, REDARE_RADIO, REDARE_STANDBY, REDARE_NIMIC)

# aceleasi valori ca in hds-watchdog.py (testul test_paznic_sistem le compara)
INTERFATA_IMPLICIT = True
ASTEPTARE_IMPLICITA_S = 120
ASTEPTARI_PERMISE_S = (60, 120, 300)

# memoria pozelor si a filmelor (memorie_es= in starea paznicului)
MEMORIE_ES_LIPSA = "lipsa"

# motivele din semnul „ocupat” (cuvinte scurte, fara spatii; paznicul le scrie in jurnal asa cum sunt)
MOTIV_SCANARE = "scanare"
MOTIV_PISTE = "piste"
MOTIV_MOTOR = "motor"
MOTIV_OARBA = "oarba"           # cautarea oarba pe satelit (Components/HdsCautareOarba.py)
MOTIV_PLUGINURI = "pluginuri"   # lista de pluginuri citita din nou (Components/PluginComponent.py); pluginuri:<dosar> cat se importa acela
CHEIE_PLUGINURI = "lista-pluginuri"
MOTIV_PLUGIN_EXTERN = "plugin-extern"   # plugin-extern:<dosar>: un plugin extern tine firul principal (punctul 9)
MOTIV_ACTUALIZARE = "actualizare"   # opkg instaleaza o actualizare (Components/HdsActualizari.py, 0.7.4): o iesire a enigma2 l-ar opri
CHEIE_PLUGIN_EXTERN = "plugin-extern"

# punctul 9: pluginurile externe care tin firul principal
PRAG_PLUGIN_EXTERN_S = 2 * BATAIE_S + 5    # doua batai ratate si putin: un lucru de cateva secunde nu se socoteste
PAS_PLUGIN_EXTERN_S = 5                    # cat de des se uita firul de supraveghere
DURATA_PLUGIN_EXTERN_S = 60                # cat asteapta paznicul dupa fiecare privire in care pluginul inca lucreaza
TOTAL_PLUGIN_EXTERN_S = 10 * 60            # cel mult atat de la ultima bataie; dupa, paznicul face ce face la orice blocaj
TEXT_AFISAJ_PLUGIN = "bUSY"                # pe afisajul de 4 cifre cat asteapta paznicul (se citeste „busy”)


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


def monotonic():
	return time.monotonic()


def _jurnal(text):
	print("[HdsPaznic] %s" % text)


# ---------------------------------------------------------------- setarile

def initConfig():
	"""config.hds_paznic: „Reporneste interfata cand nu mai raspunde” si „Asteapta inainte de repornire”."""
	from Components.config import config
	if "hds_paznic" in config.content.items:
		return
	from Components.config import ConfigSubsection, ConfigYesNo, ConfigSelection
	config.hds_paznic = ConfigSubsection()
	config.hds_paznic.interfata = ConfigYesNo(default=INTERFATA_IMPLICIT)
	config.hds_paznic.asteptare = ConfigSelection(default=str(ASTEPTARE_IMPLICITA_S), choices=alegeriAsteptare())


def alegeriAsteptare():
	return [(str(s), textDurata(s)) for s in ASTEPTARI_PERMISE_S]


def textDurata(secunde):
	secunde = int(round(secunde))
	if secunde < 90:
		if secunde == 60:
			return _("un minut")
		return _("%d secunde") % secunde
	minute = int(round(secunde / 60.0))
	if minute == 1:
		return _("un minut")
	return _("%d minute") % minute


# ---------------------------------------------------------------- semnul „ocupat” si bataia

class Bataie(object):
	"""Registrul „ocupat” si bataia scrisa pe disc. Un singur obiect pe proces (bataie())."""

	def __init__(self, cale=None, ceas=None, pid=None, rotor=None, redare=None, standby=None, imagine=None, setari=None,
			acordare=None):
		self.cale = cale or CALE_BATAIE
		self.setari = setari if setari is not None else _salveazaSetarile
		self.eroareSetari = None
		self.ceas = ceas or monotonic
		self.pid = pid if pid is not None else os.getpid()
		self.rotor = rotor if rotor is not None else _rotorSeMisca
		self.redare = redare if redare is not None else _redareAcum
		self.imagine = imagine if imagine is not None else _imagineAcum
		self.redareFel = ""     # una din REDARI la ultima citire; "" = nu se stie
		self.inregistrare = -1  # 1: inregistrare acum sau curand, 0: niciuna, -1: nu se stie
		self.criptat = -1       # serviciul de acum: 1 criptat, 0 in clar, -1 nu se stie (tools/hds-raport.sh)
		self.video = -1         # latimea imaginii decodate a serviciului de acum; 0 sau -1: nicio imagine
		# acord=: de ce nu porneste canalul de acum (nr. 77, 09.11.2026): rapoartele "fara imagine" aratau decodorul
		# oprit, dar cauza era acordarea (un tuner nesetat pentru satelitul canalului); fara jurnalul interfetei nu se
		# vedea. Numele din Components/HdsEcranNegru.py (configurare, fara_tuner, acordare, fara_pat, fara_sid, fara_pmt),
		# gol cand nu e nicio eroare sau nu se stie.
		self.acordare = acordare if acordare is not None else _acordareAcum
		self.acord = ""
		self.eroareRedare = None
		self.ocupat = {}        # cheie -> [motiv, durata_s, inceput, pana_la]
		self.eroareScriere = None
		self.timer = None
		self.scrieri = 0
		# punctul 9: registrul si fisierul se ating si din firul de supraveghere; ultimaBataie = ceasul ultimei scrieri
		# de pe firul principal (firul de supraveghere scrie cu ea, nu cu ora lui)
		self.lacat = threading.RLock()
		self.ultimaBataie = None
		self.supraveghetor = None
		# memoria decodorului: cea mai mica masuratoare se tine numai in afara standby-ului
		self.standby = standby if standby is not None else _inStandby

	# ---- registrul ----

	def incepe(self, cheie, motiv, durata_s):
		"""Un lucru lung incepe (sau continua): paznicul asteapta cel putin durata_s de la ultima bataie. Se scrie pe loc."""
		with self.lacat:
			acum = self.ceas()
			vechi = self.ocupat.get(cheie)
			inceput = vechi[2] if vechi else acum
			self.ocupat[cheie] = [motiv, float(durata_s), inceput, acum + float(durata_s)]
			self.scrie(acum)

	def termina(self, cheie):
		"""Lucrul s-a terminat (sau s-a oprit): semnul lui dispare. Se scrie pe loc."""
		with self.lacat:
			if self.ocupat.pop(cheie, None) is not None:
				self.scrie()

	def _curata(self, acum):
		for cheie, (motiv, durata, inceput, pana) in list(self.ocupat.items()):
			if acum - inceput > OCUPAT_MAXIM_S:
				_jurnal("semnul „ocupat” %s (%s) tine de peste %d ore, il scot" % (cheie, motiv, OCUPAT_MAXIM_S // 3600))
				del self.ocupat[cheie]
			else:
				# cat timp lucrul inca e inregistrat, fiecare bataie il prelungeste
				self.ocupat[cheie][3] = acum + durata

	def semn(self, acum=None):
		"""(motive, pana_la): motivele lucrurilor in curs, fara repetari, si termenul cel mai departat (0 = nimic)."""
		if acum is None:
			acum = self.ceas()
		motive = []
		pana = 0.0
		for motiv, durata, inceput, pana_la in self.ocupat.values():
			if pana_la <= acum:
				continue
			if motiv not in motive:
				motive.append(motiv)
			pana = max(pana, pana_la)
		return motive, pana

	# ---- bataia ----

	def pas(self):
		"""O bataie (din eTimer, pe firul principal). Nu arunca niciodata: o eroare aici nu are voie sa lase paznicul
		fara bataie din cauza unui defect al bataii insesi, cand interfata web e oprita."""
		try:
			acum = self.ceas()
			try:
				rotor = self.rotor()
			except Exception as e:
				rotor = False
				_jurnal("rotirea antenei nu se poate citi: %r" % (e,))
			self.citesteRedarea()
			with self.lacat:
				if rotor:
					vechi = self.ocupat.get(MOTIV_MOTOR)
					self.ocupat[MOTIV_MOTOR] = [MOTIV_MOTOR, float(DURATA_MOTOR_S), vechi[2] if vechi else acum,
						acum + DURATA_MOTOR_S]
				else:
					self.ocupat.pop(MOTIV_MOTOR, None)
				# punctul 9: firul principal merge din nou, deci pluginul extern a terminat
				plugin = self.ocupat.pop(CHEIE_PLUGIN_EXTERN, None)
				if plugin is not None and self.ultimaBataie is not None:
					_jurnal("%s a tinut firul principal %d s; paznicul a asteptat" % (plugin[0], int(acum - self.ultimaBataie)))
				self._curata(acum)
				self.scrie(acum)
			if plugin is not None:
				_afisajInapoi()
		except Exception as e:
			_jurnal("bataia: %r" % (e,))
		self.verificaMemoriaDriver()
		self.salveazaSetarile()

	def salveazaSetarile(self):
		"""Punctul 8: setarile salvate in memorie de la ultima scriere ajung pe disc, dupa bataie (o scriere inceata pe
		memoria interna nu intarzie bataia). O eroare intra in jurnal o singura data, pana merge din nou. Nu arunca."""
		try:
			self.setari()
			if self.eroareSetari is not None:
				_jurnal("setarile se scriu din nou pe disc")
			self.eroareSetari = None
		except Exception as e:
			if self.eroareSetari is None:
				_jurnal("setarile nu s-au scris pe disc: %r" % (e,))
			self.eroareSetari = repr(e)

	def verificaMemoriaDriver(self):
		"""Memoria decodorului (Components/HdsMemorieDriver.py): citirile memoriei (crezute numai dupa un minut sub
		prag), cea mai mica masuratoare din afara standby-ului si repornirea in standby. Nimic pe ecran. Nu arunca."""
		try:
			from Components import HdsMemorieDriver as M
		except ImportError:
			return
		try:
			M.pasMasuratoare(self.standby)
			M.repornireStandby().pas()
		except Exception as e:
			_jurnal("memoria decodorului: %r" % (e,))

	def citesteRedarea(self):
		"""redareFel si inregistrare din self.redare(); la orice eroare sau raspuns strain: „nu se stie” (o singura linie
		in jurnal pana la urmatoarea citire reusita). Nu arunca."""
		try:
			fel, inregistrare = self.redare()
			if fel not in REDARI or inregistrare not in (0, 1):
				raise ValueError("raspuns strain: %r" % ((fel, inregistrare),))
			self.redareFel, self.inregistrare = fel, int(inregistrare)
			self.eroareRedare = None
		except Exception as e:
			self.redareFel, self.inregistrare = "", -1
			if self.eroareRedare is None:
				_jurnal("redarea nu se poate citi: %r" % (e,))
			self.eroareRedare = repr(e)
		# criptat= si video= (raportul pornirii, tools/hds-raport.sh: canal TV fara imagine); fara jurnal la eroare
		try:
			criptat, video = self.imagine()
			self.criptat = int(criptat) if int(criptat) in (0, 1) else -1
			self.video = int(video) if -1 <= int(video) <= 16384 else -1
		except Exception:
			self.criptat, self.video = -1, -1
		# acord= (raportul pornirii); in fisier intra numai un nume scurt din litere mici si _
		try:
			acord = self.acordare()
			self.acord = acord if isinstance(acord, str) and len(acord) <= 20 and \
				all("a" <= c <= "z" or c == "_" for c in acord) else ""
		except Exception:
			self.acord = ""

	def text(self, acum, bataie=None):
		"""bataie: ceasul scris in campul bataie=; implicit acum (o bataie adevarata, de pe firul principal)."""
		motive, pana = self.semn(acum)
		return ("pid=%d\nbataie=%.3f\nocupat=%s\nocupat_pana=%.3f\nredare=%s\ninregistrare=%d\ncriptat=%d\nvideo=%d\n"
			"acord=%s\n"
			% (self.pid, acum if bataie is None else bataie, ",".join(motive), pana, self.redareFel, self.inregistrare,
			self.criptat, self.video, self.acord))

	def scrie(self, acum=None, bataieVeche=False):
		"""bataieVeche: scrierea firului de supraveghere (punctul 9): numai semnul „ocupat” e nou, bataia ramane cea de
		pe firul principal, ca paznicul sa vada mai departe de cand tace firul."""
		if acum is None:
			acum = self.ceas()
		nou = self.cale + ".nou"
		try:
			with self.lacat:
				with open(nou, "w") as f:
					f.write(self.text(acum, self.ultimaBataie if bataieVeche else None))
				os.replace(nou, self.cale)
				if not bataieVeche:
					self.ultimaBataie = acum
			self.scrieri += 1
			if self.eroareScriere is not None:
				_jurnal("bataia se scrie din nou in %s" % self.cale)
			self.eroareScriere = None
		except (OSError, IOError) as e:
			if self.eroareScriere is None:
				_jurnal("nu pot scrie bataia in %s: %s" % (self.cale, e))
			self.eroareScriere = str(e)

	def porneste(self):
		from enigma import eTimer
		if self.timer is None:
			self.timer = eTimer()
			self.timer.callback.append(self.pas)
		self.pas()
		self.timer.start(BATAIE_S * 1000, False)
		if self.supraveghetor is None:
			self.supraveghetor = SupraveghetorPluginExtern(self)
			self.supraveghetor.porneste()

	def opreste(self):
		if self.timer is not None:
			self.timer.stop()
		if self.supraveghetor is not None:
			self.supraveghetor.opreste()
			self.supraveghetor = None
		try:
			os.remove(self.cale)
		except OSError:
			pass


def textMemorieEs(activ=None):
	"""Informatia de pe ecranul si pagina paznicului cand memoria pozelor si a filmelor lipseste (niciun mesaj pe
	televizor), cu propozitia eliberarii dupa setarea repornirii in standby."""
	text = _("Filmele și imaginea posturilor de radio nu pot porni acum; canalele TV merg.")
	try:
		from Components import HdsMemorieDriver
		text += " " + HdsMemorieDriver.textEliberare(HdsMemorieDriver.activaStandby() if activ is None else activ)
	except Exception:
		pass
	return text


def _inStandby():
	from Screens import Standby
	return Standby.inStandby is not None


def _rotorSeMisca():
	try:
		from enigma import eDVBSatelliteEquipmentControl
		sec = eDVBSatelliteEquipmentControl.getInstance()
	except Exception:
		return False
	if sec is None:
		return False
	return bool(sec.isRotorMoving())


def _redareAcum():
	"""(redare, inregistrare) din enigma2. redare: „standby” cat ecranul Standby e deschis, „tv” pentru un serviciu cu
	pista video, „radio” pentru unul fara, „nimic” fara serviciu. inregistrare: 1 cand o inregistrare merge sau incepe in
	INREGISTRARE_CURAND_S secunde, altfel 0. Arunca daca navigatia lipseste (bataia scrie atunci „nu se stie”)."""
	import NavigationInstance
	nav = NavigationInstance.instance
	if nav is None:
		raise RuntimeError("navigatia nu e pornita")
	inregistrare = 0
	if nav.getRecordings():
		inregistrare = 1
	else:
		urmatoarea = nav.RecordTimer.getNextRecordingTime()
		if urmatoarea > 0 and urmatoarea - time.time() < INREGISTRARE_CURAND_S:
			inregistrare = 1
	from Screens import Standby
	if Standby.inStandby is not None:
		return REDARE_STANDBY, inregistrare
	serviciu = nav.getCurrentService()
	info = serviciu and serviciu.info()
	if not info:
		return REDARE_NIMIC, inregistrare
	from enigma import iServiceInformation
	return (REDARE_TV if info.getInfo(iServiceInformation.sVideoPID) > 0 else REDARE_RADIO), inregistrare


def _imagineAcum():
	"""(criptat, video) ale serviciului de acum, pentru raportul pornirii (tools/hds-raport.sh): criptat 1/0 (sIsCrypted),
	video = latimea imaginii decodate (sVideoWidth; 0 sau -1 cat decodorul nu a dat nicio imagine). (-1, -1) fara
	serviciu."""
	import NavigationInstance
	nav = NavigationInstance.instance
	serviciu = nav and nav.getCurrentService()
	info = serviciu and serviciu.info()
	if not info:
		return -1, -1
	from enigma import iServiceInformation
	return (1 if info.getInfo(iServiceInformation.sIsCrypted) == 1 else 0), info.getInfo(iServiceInformation.sVideoWidth)


def _acordareAcum():
	"""Eroarea acordarii serviciului de acum, pentru raportul pornirii: numele din Components/HdsEcranNegru.py pentru
	sDVBState (ultimul eveniment al eDVBServicePMTHandler: eventMisconfiguration = configurare, niciun tuner setat
	pentru acest canal; eventNoResources = fara_tuner, toate ocupate; eventTuneFailed = acordare, fara semnal; ...).
	"" fara serviciu sau cand acordarea a mers."""
	import NavigationInstance
	nav = NavigationInstance.instance
	serviciu = nav and nav.getCurrentService()
	info = serviciu and serviciu.info()
	if not info:
		return ""
	from enigma import iServiceInformation
	from Components.HdsEcranNegru import eroare_acordare
	return eroare_acordare(info.getInfo(iServiceInformation.sDVBState)) or ""


# ---------------------------------------------------------------- punctul 9: pluginul extern pe firul principal

def _cadrulFiruluiPrincipal():
	"""Cadrul de acum al firului principal (sys._current_frames), sau None."""
	try:
		return sys._current_frames().get(threading.main_thread().ident)
	except Exception:
		return None


def _pluginDinCale(cale):
	"""(fel, nume) al pluginului extern din calea unui fisier (aceeasi hotarare ca rapoartele pluginurilor externe)."""
	from Components.HdsPluginExtern import pluginDinCale
	return pluginDinCale(cale)


def pluginExternInStiva(cadru, pluginDinCale=None, adancime=200):
	"""Numele pluginului extern al celui mai adanc cadru (cel care lucreaza acum) din stiva care incepe la `cadru`,
	sau None cand stiva nu trece prin niciun plugin extern."""
	pluginDinCale = pluginDinCale or _pluginDinCale
	while cadru is not None and adancime > 0:
		try:
			p = pluginDinCale(cadru.f_code.co_filename)
		except Exception:
			p = None
		if p:
			return p[1]
		cadru = cadru.f_back
		adancime -= 1
	return None


def _semnAfisaj():
	"""Functia care scrie TEXT_AFISAJ_PLUGIN pe afisajul de 4 cifre, facuta pe firul principal (importurile aici); ea
	insasi nu importa nimic nou. Fara afisaj de 4 cifre, in asteptare sau pe un afisaj color nu scrie nimic. Nu arunca."""
	try:
		from Components import HdsAfisaj, HdsAfisajLitere
		from Components import HdsAfisajCompat     # noqa: F401 (Afisaj.scrie il ia din sys.modules)
	except Exception:
		return lambda: False
	octeti = HdsAfisajLitere.octetiText(TEXT_AFISAJ_PLUGIN).decode("latin-1")

	def scrie():
		try:
			a = HdsAfisaj._afisaj
			if a is None or type(a) is not HdsAfisaj.Afisaj or getattr(a, "inAsteptare", False):
				return False
			return bool(a.scrie(octeti))    # ultim = textul nostru: primul pas al afisajului scrie din nou ce arata
		except Exception as e:
			_jurnal("semnul pe afisaj: %r" % (e,))
			return False
	return scrie


def _afisajInapoi():
	"""Pe firul principal, dupa ce pluginul extern a lasat firul: afisajul arata din nou ce arata (pasul lui acum)."""
	try:
		from Components import HdsAfisaj
		HdsAfisaj.actualizeaza()
	except Exception as e:
		_jurnal("afisajul dupa pluginul extern: %r" % (e,))


class SupraveghetorPluginExtern(object):
	"""Punctul 9 din capul fisierului. pas() e o singura privire (testele o cheama direct); porneste() o face pe un fir
	al lui, la fiecare PAS_PLUGIN_EXTERN_S secunde."""

	def __init__(self, bataie, cadru=None, pluginDinCale=None, semn=None):
		self.b = bataie
		self.cadru = cadru or _cadrulFiruluiPrincipal
		self.semn = semn if semn is not None else _semnAfisaj()
		# hotararea se ia o data, aici, pe firul principal: firul de supraveghere nu importa nimic (firul principal poate
		# sta chiar in importul unui plugin, cu lacatul importurilor luat)
		if pluginDinCale is None:
			try:
				from Components.HdsPluginExtern import pluginDinCale
			except Exception as e:
				_jurnal("supravegherea pluginurilor externe fara HdsPluginExtern: %r" % (e,))
				pluginDinCale = lambda cale: None
		self.pluginDinCale = pluginDinCale
		self.anuntat = None     # (ultimaBataie, nume) pentru care s-a scris deja in jurnal
		self.stop = threading.Event()
		self.fir = None

	def _scoate(self, acum):
		if self.b.ocupat.pop(CHEIE_PLUGIN_EXTERN, None) is not None:
			self.b.scrie(acum, bataieVeche=True)

	def pas(self):
		"""Intoarce ce a hotarat: "viu" (bataia e proaspata), "nu-e-plugin" (firul principal tace in afara unui
		plugin extern: paznicul hotaraste ca la orice tacere), "asteapta:<nume>", "prea-mult:<nume>"."""
		b = self.b
		acum = b.ceas()
		ultima = b.ultimaBataie
		if ultima is None or acum - ultima < PRAG_PLUGIN_EXTERN_S:
			return "viu"
		nume = pluginExternInStiva(self.cadru(), self.pluginDinCale)
		with b.lacat:
			if b.ultimaBataie != ultima:
				return "viu"
			if not nume:
				self._scoate(acum)
				return "nu-e-plugin"
			motiv = "%s:%s" % (MOTIV_PLUGIN_EXTERN, nume)
			if acum - ultima >= TOTAL_PLUGIN_EXTERN_S:
				self._scoate(acum)
				if self.anuntat != (ultima, "prea-mult"):
					self.anuntat = (ultima, "prea-mult")
					_jurnal("%s tine firul principal de %d s, peste %d s: paznicul nu mai asteapta"
						% (motiv, int(acum - ultima), TOTAL_PLUGIN_EXTERN_S))
				return "prea-mult:" + nume
			pana = min(acum + DURATA_PLUGIN_EXTERN_S, ultima + TOTAL_PLUGIN_EXTERN_S)
			b.ocupat[CHEIE_PLUGIN_EXTERN] = [motiv, float(DURATA_PLUGIN_EXTERN_S), ultima, pana]
			b.scrie(acum, bataieVeche=True)
		if self.anuntat != (ultima, nume):
			self.anuntat = (ultima, nume)
			_jurnal("%s tine firul principal de %d s; paznicul asteapta cel mult %d s de la ultima bataie"
				% (motiv, int(acum - ultima), TOTAL_PLUGIN_EXTERN_S))
			try:
				self.semn()
			except Exception:
				pass
		return "asteapta:" + nume

	def _bucla(self):
		while not self.stop.wait(PAS_PLUGIN_EXTERN_S):
			try:
				self.pas()
			except Exception as e:
				_jurnal("supravegherea pluginurilor externe: %r" % (e,))

	def porneste(self):
		if self.fir is None:
			self.fir = threading.Thread(target=self._bucla, name="HdsPaznicPluginExtern")
			self.fir.daemon = True
			self.fir.start()

	def opreste(self):
		self.stop.set()
		self.fir = None


_unic = [None]


def _salveazaSetarile():
	"""Punctul 8, cu configfile din enigma2. Fara Components.config sau fara functia (probele altor module pe PC):
	nimic, fara rand in jurnal."""
	try:
		from Components.config import configfile
	except ImportError:
		return
	scrie = getattr(configfile, "salveazaSchimbarile", None)
	if scrie is not None:
		scrie()


def bataie():
	if _unic[0] is None:
		_unic[0] = Bataie()
	return _unic[0]


def porneste():
	"""Din mytest.py, dupa pornirea sesiunii: setarile si bataia."""
	initConfig()
	bataie().porneste()
	_jurnal("bataia pornita (%s, la %d s)" % (bataie().cale, BATAIE_S))
	# setarea repornirii de noapte si, dupa o repornire de noapte, intrarea in standby
	try:
		from Components import HdsMemorieDriver
		HdsMemorieDriver.porneste()
	except Exception as e:
		_jurnal("memoria decodorului: %r" % (e,))


def opreste():
	"""Din mytest.py, la iesirea din enigma2: bataia se opreste si fisierul ei se sterge (procesul urmator scrie altul)."""
	if _unic[0] is not None:
		_unic[0].opreste()


def ocupat(cheie, motiv, durata_s):
	"""Pentru scanare, citirea pistelor si alte lucruri lungi: nu arunca niciodata."""
	try:
		bataie().incepe(cheie, motiv, durata_s)
	except Exception as e:
		_jurnal("ocupat(%s): %r" % (cheie, e))


def liber(cheie):
	try:
		bataie().termina(cheie)
	except Exception as e:
		_jurnal("liber(%s): %r" % (cheie, e))


# ---------------------------------------------------------------- starea, pentru ecran si web

def citesteCheiValori(cale, maxim=4096):
	try:
		with open(cale, "r") as f:
			text = f.read(maxim)
	except (OSError, IOError):
		return None
	d = {}
	for rand in text.splitlines():
		cheie, semn, valoare = rand.partition("=")
		if semn:
			d[cheie.strip()] = valoare.strip()
	return d


def _intreg(valoare, implicit=0):
	try:
		return int(float(valoare))
	except (TypeError, ValueError):
		return implicit


def _procesExista(pid):
	return pid > 0 and os.path.exists("/proc/%d" % pid)


def textMotiv(motiv):
	if motiv.startswith(MOTIV_PLUGINURI + ":"):
		return _("încărcarea pluginului %s") % motiv.split(":", 1)[1]
	if motiv.startswith(MOTIV_PLUGIN_EXTERN + ":"):
		return _("pluginul extern %s") % motiv.split(":", 1)[1]
	return {
		MOTIV_SCANARE: _("scanarea canalelor"),
		MOTIV_PISTE: _("citirea pistelor canalelor"),
		MOTIV_MOTOR: _("rotirea antenei"),
		MOTIV_OARBA: _("căutarea oarbă pe satelit"),
		MOTIV_PLUGINURI: _("citirea listei de pluginuri"),
		MOTIV_ACTUALIZARE: _("instalarea actualizării software"),
	}.get(motiv, motiv)


def textMotive(motive):
	return ", ".join(textMotiv(m) for m in motive if m)


def stare(cale_stare=None, acum=None, pid_paznic_viu=None):
	"""Starea pentru ecran si web: dictionar simplu, cu textul gata de aratat. Nu arunca."""
	cale_stare = cale_stare or CALE_STARE
	acum = monotonic() if acum is None else acum
	viu = pid_paznic_viu or _procesExista
	d = citesteCheiValori(cale_stare)
	rez = {
		"ruleaza": False,
		"stare": "necunoscut",
		"text": "",
		"detaliu": "",
		"placa": False,
		"placa_secunde": 0,
		"ocupat": [],
		"ocupat_text": "",
		"ocupat_ramas_s": 0,
		"bataie_varsta_s": -1,
		"reporniri": 0,
		"ultima_actiune": "",
		"ultima_actiune_ora": 0,
		"verificat_acum_s": -1,
		"memorie_es": "",
		"memorie_es_cheie": "",
		"avertisment": "",
		"memorie_driver": {},
	}
	# memoria decodorului (vmalloc) se masoara aici, pe receptor: nu depinde de paznic; numai informatie
	try:
		from Components import HdsMemorieDriver
		rez["memorie_driver"] = HdsMemorieDriver.stare()
	except Exception:
		pass
	try:
		b = bataie()
		motive, pana = b.semn()
		rez["ocupat"] = motive
		rez["ocupat_text"] = textMotive(motive)
		rez["ocupat_ramas_s"] = int(max(0, pana - b.ceas())) if pana else 0
	except Exception:
		pass
	if not d:
		rez["text"] = _("Paznicul nu rulează sau nu a scris încă nicio stare (imagine fără el, sau pornirea abia a început).")
		return rez
	pid = _intreg(d.get("pid"))
	verificat = d.get("verificat")
	try:
		vechime = acum - float(verificat)
	except (TypeError, ValueError):
		vechime = -1
	rez["verificat_acum_s"] = int(vechime) if vechime >= 0 else -1
	rez["ruleaza"] = bool(viu(pid)) and 0 <= vechime <= 90
	rez["stare"] = d.get("stare", "necunoscut")
	rez["detaliu"] = d.get("detaliu", "")
	rez["placa"] = d.get("placa") == "1"
	rez["placa_secunde"] = _intreg(d.get("placa_secunde"))
	rez["bataie_varsta_s"] = _intreg(d.get("bataie_varsta"), -1)
	rez["reporniri"] = _intreg(d.get("reporniri"))
	rez["ultima_actiune"] = d.get("ultima_actiune", "")
	rez["ultima_actiune_ora"] = _intreg(d.get("ultima_actiune_ora"))
	if not rez["ocupat"] and d.get("ocupat"):
		rez["ocupat"] = [m for m in d.get("ocupat", "").split(",") if m]
		rez["ocupat_text"] = textMotive(rez["ocupat"])
		rez["ocupat_ramas_s"] = _intreg(d.get("ocupat_ramas"))
	rez["memorie_es"] = d.get("memorie_es", "")
	rez["memorie_es_cheie"] = d.get("memorie_es_cheie", "")
	# numai de la un paznic viu: o stare veche (paznicul oprit) nu mai spune nimic despre receptorul de acum
	if rez["ruleaza"] and rez["memorie_es"] == MEMORIE_ES_LIPSA:
		rez["avertisment"] = textMemorieEs()
	rez["text"] = textStare(rez)
	return rez


def stareServicii(cale_stare=None, acum=None, pid_paznic_viu=None):
	"""Serviciile de sistem (D-Bus, avahi, numele hdsatelit.local), din starea paznicului (nivelul 6 din
	hds-watchdog.py): {'ruleaza', 'servicii' (ok, repornit, esec sau ''), 'detaliu', 'ora' (ultima pornire facuta de
	paznic, ora de perete, 0 = niciuna), 'reporniri', 'text'}. Nu arunca."""
	rez = {"ruleaza": False, "servicii": "", "detaliu": "", "ora": 0, "reporniri": 0, "text": ""}
	try:
		d = citesteCheiValori(cale_stare or CALE_STARE) or {}
		if d:
			acum = monotonic() if acum is None else acum
			try:
				vechime = acum - float(d.get("verificat"))
			except (TypeError, ValueError):
				vechime = -1
			rez["ruleaza"] = bool((pid_paznic_viu or _procesExista)(_intreg(d.get("pid")))) and 0 <= vechime <= 90
			rez["servicii"] = d.get("servicii", "")
			rez["detaliu"] = d.get("servicii_detaliu", "")
			rez["ora"] = _intreg(d.get("servicii_ora"))
			rez["reporniri"] = _intreg(d.get("servicii_reporniri"))
	except Exception:
		pass
	rez["text"] = textServicii(rez)
	return rez


def textServicii(s):
	"""Un rand pentru "Informatii jurnale" si pagina web: serviciile de sistem pe intelesul omului."""
	if not s.get("ruleaza") or not s.get("servicii"):
		return _("Paznicul nu a verificat încă serviciile de sistem (o face la 3 minute după pornire).")
	if s.get("servicii") == "esec":
		return _("Nu merg toate serviciile de sistem; paznicul încearcă din nou: %s") % (s.get("detaliu") or "")
	n = s.get("reporniri") or 0
	if n:
		ora = time.strftime("%d.%m %H:%M", time.localtime(s.get("ora"))) if s.get("ora") else "?"
		return _("Serviciile de sistem merg. Porniri făcute de paznic: %d, ultima la %s (vezi hds-servicii.log).") % (
			n, ora)
	return _("Serviciile de sistem (D-Bus, avahi, numele hdsatelit.local) merg.")


def stareEs(cale_stare=None, acum=None, pid_paznic_viu=None):
	"""Numai memoria pozelor si a filmelor, din starea paznicului (pentru repornirea in standby): {'ruleaza',
	'memorie_es', 'memorie_es_cheie'}; ruleaza = paznicul viu, cu stare noua. Nu arunca."""
	rez = {"ruleaza": False, "memorie_es": "", "memorie_es_cheie": ""}
	try:
		d = citesteCheiValori(cale_stare or CALE_STARE)
		if not d:
			return rez
		acum = monotonic() if acum is None else acum
		vechime = acum - float(d.get("verificat"))
		rez["ruleaza"] = bool((pid_paznic_viu or _procesExista)(_intreg(d.get("pid")))) and 0 <= vechime <= 90
		rez["memorie_es"] = d.get("memorie_es", "")
		rez["memorie_es_cheie"] = d.get("memorie_es_cheie", "")
	except Exception:
		pass
	return rez


def textStare(s):
	if not s.get("ruleaza"):
		return _("Paznicul nu rulează acum (fără stare nouă de peste un minut).")
	fel = s.get("stare")
	if fel == "oprit":
		text = _("Repornirea interfeței este oprită din setări. Paznicul plăcii rămâne pornit.")
	elif fel == "ocupat":
		text = _("Interfața lucrează la: %s. Paznicul așteaptă să termine.") % (s.get("ocupat_text") or _("un lucru lung"))
	elif fel == "fara-bataie":
		text = _("Paznicul așteaptă primul semn de viață al interfeței.")
	elif fel == "web-raspunde":
		text = _("Interfața nu a mai trimis semn de viață, dar interfața web răspunde. Paznicul nu o repornește.")
	elif fel == "blocat":
		text = _("Interfața nu a mai răspuns. Paznicul a repornit-o.")
	else:
		text = _("Paznicul supraveghează interfața.")
	if s.get("placa"):
		text += " " + (_("Paznicul plăcii: pornit, %d secunde.") % s["placa_secunde"] if s.get("placa_secunde")
			else _("Paznicul plăcii: pornit."))
	return text


def ultimeleRanduriJurnal(cale=None, randuri=8, maxim=16384):
	"""Ultimele randuri din jurnalul paznicului (texte tehnice, fara diacritice), pentru ecran si web."""
	cale = cale or CALE_JURNAL
	try:
		with open(cale, "rb") as f:
			try:
				f.seek(-maxim, os.SEEK_END)
			except (OSError, IOError):
				f.seek(0)
			date = f.read(maxim)
	except (OSError, IOError):
		return []
	text = date.decode("utf-8", "replace")
	return [r for r in text.splitlines() if r.strip()][-randuri:]


# ---------------------------------------------------------------- schimbarea setarilor (ecran si web)

def seteaza(interfata=None, asteptare=None, noapte=None):
	"""Schimba si salveaza setarile (pe disc, ca paznicul sa le vada la urmatoarea verificare). Intoarce (reusit, mesaj).
	noapte = repornirea de noapte cand memoria decodorului e farmitata (Components/HdsMemorieDriver.py)."""
	from Components.config import config, configfile
	initConfig()
	if noapte is not None:
		from Components import HdsMemorieDriver
		HdsMemorieDriver.initConfig()
		config.hds_paznic.repornire_noapte.value = bool(noapte)
		config.hds_paznic.repornire_noapte.save()
	if asteptare is not None:
		try:
			secunde = int(asteptare)
		except (TypeError, ValueError):
			return False, _("Timpul de așteptare nu este unul din cele permise.")
		if secunde not in ASTEPTARI_PERMISE_S:
			return False, _("Timpul de așteptare nu este unul din cele permise.")
		config.hds_paznic.asteptare.value = str(secunde)
		config.hds_paznic.asteptare.save()
	if interfata is not None:
		config.hds_paznic.interfata.value = bool(interfata)
		config.hds_paznic.interfata.save()
	configfile.save()
	return True, _("Salvat. Paznicul folosește setarea de la următoarea verificare (cel mult 15 secunde).")
