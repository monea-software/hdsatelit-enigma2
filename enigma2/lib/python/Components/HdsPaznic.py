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
#      9b (0.7.8): acelasi semn cand firul principal NU e intr-un plugin extern, dar lucreaza infometat (timpul lui de
#      procesor din /proc/self/task/<tid>/stat creste intre doua priviri, dar sub PRAG_PRINCIPAL_PLIN nuclee), iar firele unui
#      plugin extern (stiva lor trece prin plugin) au luat intre timp cel putin PRAG_FIRE_PLUGIN nuclee: un plugin cu multe
#      fire de procesor (siglele Bouquet Maker Xtream, 20 de fire PIL pe 2 nuclee) lasa firului principal prea putin
#      procesor, deci o pagina web de cateva secunde trecea de 120 s si paznicul oprea o interfata care mergea. Firul principal
#      care nu lucreaza deloc (asteapta un lacat, e blocat) sau care are procesor din plin (o bucla a noastra) nu primeste
#      semnul: paznicul face ce facea. Aceleasi plafoane (DURATA_PLUGIN_EXTERN_S, TOTAL_PLUGIN_EXTERN_S).
#  10. CINE TINE FIRUL PRINCIPAL (0.7.5, lotul PRN: blocajele din primele minute pe Viper 4K V10, SF8008, Trio, Ustym).
#      Bataia de 10 s si pragul paznicului (120 s) nu vad tacerile de cateva secunde, cand tastele stau la coada si apare
#      rotita. Un ceas de TIC_S pe firul principal (numai in memorie) si firul de supraveghere (la PAS_FIR_S) scriu un
#      rand in jurnalul paznicului pentru orice tacere de ~PRAG_FIR_OCUPAT_S (masurata intre batai, +-1 s, deci de la ~2 s):
#      cat, la cat timp de la pornire si locul
#      din cod (FirOcupat). La prima bataie, un rand cu durata pornirii si pasii ei lenti (pasPornire, din
#      PluginComponent si mytest.py), iar la orice TryQuitMainloop un rand cu codul si ecranele deschise (cerereIesire).
#      Jurnalul paznicului pleaca mereu in pachetul beta testerului, deci urmatorul pachet spune singur cine a fost.
#  11. STIVELE TUTUROR FIRELOR LA CEREREA PAZNICULUI (0.7.7): un fir al imaginii (StiveLaCerere, pornit din capul
#      mytest.py) asteapta pe teava CALE_CERERE_STIVE si scrie stivele tuturor firelor citite din Python, in forma
#      faulthandler, la coada fisierului de stive. Paznicul il intreaba intai pe el; semnalele faulthandler din mytest.py
#      raman pentru interfata care tine lacatul Python (atunci firul acesta nu poate raspunde).
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
# 0.7.6 (WDG): semnul iesirii cerute, scris cand bucla principala s-a oprit (iesireInceputa); hds-watchdog.py opreste
# procesul care nu iese in IESIRE_CERUTA_S secunde de la el (asistenta 430032, repornirea interfetei cu o tema straina)
CALE_IESIRE = "/var/run/hds-paznic.iesire"

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
# punctul 9b: firele unui plugin extern tin procesorul, iar firul principal lucreaza incet (0.7.8)
PRAG_FIRE_PLUGIN = 0.5                     # cat procesor (in nuclee) iau firele pluginului intre doua priviri ca sa conteze
PRAG_PRINCIPAL_PLIN = 0.6                  # firul principal care ia atat sau mai mult nu e infometat: tacerea e a lui
CALE_FIR_STAT = "/proc/self/task/%d/stat"


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
		# punctul 10: ceasul de 1 s si firul de supraveghere care spune cine tine firul principal
		self.firOcupat = None
		self.timerTic = None
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
		if self.firOcupat is None:
			self.firOcupat = FirOcupat(ceas=self.ceas)
			self.timerTic = eTimer()
			self.timerTic.callback.append(self.firOcupat.tic)
		self.firOcupat.tic()
		self.timerTic.start(TIC_S * 1000, False)
		if self.supraveghetor is None:
			self.supraveghetor = SupraveghetorPluginExtern(self)
			self.supraveghetor.porneste()

	def opreste(self):
		if self.timer is not None:
			self.timer.stop()
		if self.timerTic is not None:
			self.timerTic.stop()
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


def _nativPrincipal():
	"""Id-ul firului principal in nucleu (/proc/self/task/<tid>), sau None."""
	return getattr(threading.main_thread(), "native_id", None)


def _fireAlte():
	"""[(id-ul in nucleu, cadrul de sus)] ale firelor Python, in afara de cel principal si de cel care priveste."""
	cadre = sys._current_frames()
	eu, principal = threading.get_ident(), threading.main_thread().ident
	rez = []
	for t in threading.enumerate():
		if t.ident in (eu, principal):
			continue
		c = cadre.get(t.ident)
		n = getattr(t, "native_id", None)
		if c is not None and n:
			rez.append((n, c))
	return rez


def _cpuFir(nativ):
	"""Timpul de procesor al firului (utime + stime, in ticuri), sau None."""
	try:
		with open(CALE_FIR_STAT % nativ) as f:
			camp = f.read().rsplit(")", 1)[1].split()
		return int(camp[11]) + int(camp[12])
	except Exception:
		return None


def _ticuriPeSecunda():
	try:
		return float(os.sysconf("SC_CLK_TCK")) or 100.0
	except Exception:
		return 100.0


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

	def __init__(self, bataie, cadru=None, pluginDinCale=None, semn=None, fire=None, cpu=None, principal=None,
			ticuri=None):
		self.b = bataie
		self.cadru = cadru or _cadrulFiruluiPrincipal
		self.semn = semn if semn is not None else _semnAfisaj()
		# punctul 9b: celelalte fire, timpul lor de procesor, firul principal (probele le dau false)
		self.fire = fire or _fireAlte
		self.cpu = cpu or _cpuFir
		self.principal = principal or _nativPrincipal
		self.ticuri = ticuri or _ticuriPeSecunda()
		self.esantion = None    # (ceasul, {fir: ticuri}) la privirea de dinainte, cat tace bataia
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
			self.esantion = None
			return "viu"
		nume = pluginExternInStiva(self.cadru(), self.pluginDinCale)
		fire = 0
		if not nume:
			try:
				nume, fire = self._pluginPeFire(acum)
			except Exception as e:
				_jurnal("firele pluginurilor externe: %r" % (e,))
				nume, fire = None, 0
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
					_jurnal("%s %s de %d s, peste %d s: paznicul nu mai asteapta"
						% (motiv, "tine procesorul cu firele lui" if fire else "tine firul principal", int(acum - ultima),
						TOTAL_PLUGIN_EXTERN_S))
				return "prea-mult:" + nume
			pana = min(acum + DURATA_PLUGIN_EXTERN_S, ultima + TOTAL_PLUGIN_EXTERN_S)
			b.ocupat[CHEIE_PLUGIN_EXTERN] = [motiv, float(DURATA_PLUGIN_EXTERN_S), ultima, pana]
			b.scrie(acum, bataieVeche=True)
		if self.anuntat != (ultima, nume):
			self.anuntat = (ultima, nume)
			if fire:
				_jurnal("%s: %d fire ale pluginului tin procesorul, firul principal lucreaza incet de %d s; paznicul asteapta "
					"cel mult %d s de la ultima bataie" % (motiv, fire, int(acum - ultima), TOTAL_PLUGIN_EXTERN_S))
			else:
				_jurnal("%s tine firul principal de %d s; paznicul asteapta cel mult %d s de la ultima bataie"
					% (motiv, int(acum - ultima), TOTAL_PLUGIN_EXTERN_S))
			try:
				self.semn()
			except Exception:
				pass
		return ("asteapta-fire:" if fire else "asteapta:") + nume

	def _pluginPeFire(self, acum):
		"""Punctul 9b: (numele, cate fire) al pluginului extern ale carui fire au luat cel putin PRAG_FIRE_PLUGIN nuclee de
		la privirea de dinainte, cat firul principal a lucrat si el (timpul lui de procesor a crescut); altfel (None, 0).
		Prima privire a unei taceri numai noteaza timpii."""
		principal = self.principal()
		pluginuri = {}
		for nativ, cadru in self.fire():
			p = pluginExternInStiva(cadru, self.pluginDinCale)
			if p:
				pluginuri[nativ] = p
		ticuri = {}
		for nativ in list(pluginuri) + [principal]:
			t = self.cpu(nativ) if nativ else None
			if t is not None:
				ticuri[nativ] = t
		inainte, self.esantion = self.esantion, (acum, ticuri)
		if inainte is None or principal not in ticuri or principal not in inainte[1]:
			return None, 0
		# media de la privirea de dinainte a aceleiasi taceri, oricat de departe: cand lacatul Python e foarte cautat si firul
		# acesta priveste rar, o privire rara tot spune cine a luat procesorul
		durata = acum - inainte[0]
		if durata <= 0:
			return None, 0
		principal_s = (ticuri[principal] - inainte[1][principal]) / self.ticuri
		if principal_s <= 0:
			return None, 0          # firul principal n-a lucrat deloc: asteapta sau e blocat, nu e infometat
		if principal_s >= PRAG_PRINCIPAL_PLIN * durata:
			return None, 0          # firul principal are procesor: tacerea e a lui (o bucla a noastra), ca pana acum
		pe = {}
		for nativ, p in pluginuri.items():
			if nativ in ticuri and nativ in inainte[1]:
				d = ticuri[nativ] - inainte[1][nativ]
				if d > 0:
					s = pe.setdefault(p, [0, 0])
					s[0] += d
					s[1] += 1
		if not pe:
			return None, 0
		p, (d, n) = max(pe.items(), key=lambda x: x[1][0])
		if d / self.ticuri < PRAG_FIRE_PLUGIN * durata:
			return None, 0
		return p, n

	def _bucla(self):
		# la PAS_FIR_S: privirea punctului 10; la PAS_PLUGIN_EXTERN_S: pas() de mai sus, ca inainte
		pas_s = min(PAS_FIR_S, PAS_PLUGIN_EXTERN_S)
		trecut = 0.0
		inceput = monotonic()
		while not self.stop.wait(pas_s):
			# PLG 0.7.7: cat a stat firul acesta peste pas_s ca sa ruleze din nou (lacatul Python tinut de alt cod)
			intarziere = monotonic() - inceput - pas_s
			fir = getattr(self.b, "firOcupat", None)
			if fir is not None:
				try:
					noteaza = getattr(fir, "intarzierePaznic", None)
					if noteaza is not None:
						noteaza(intarziere)
					fir.privire()
				except Exception as e:
					_jurnal("cine tine firul principal: %r" % (e,))
			trecut += pas_s
			if trecut + 1e-6 < PAS_PLUGIN_EXTERN_S:
				inceput = monotonic()
				continue
			trecut = 0.0
			try:
				self.pas()
			except Exception as e:
				_jurnal("supravegherea pluginurilor externe: %r" % (e,))
			inceput = monotonic()

	def porneste(self):
		if self.fir is None:
			self.fir = threading.Thread(target=self._bucla, name="HdsPaznicPluginExtern")
			self.fir.daemon = True
			self.fir.start()

	def opreste(self):
		self.stop.set()
		self.fir = None


# ---------------------------------------------------------------- punctul 10: cine tine firul principal (0.7.5, PRN)

def jurnalPaznic(text, cale=None):
	"""Un rand „enigma2: ...” in jurnalul paznicului (CALE_JURNAL), care pleaca mereu in pachetul beta testerului (fara
	limita pe zi, Components/HdsBetaTester._randuriNoiPaznic), si acelasi text in jurnalul interfetei. Deschis, scris la
	coada si inchis la fiecare rand (paznicul scrie si el la coada aceluiasi fisier). Nu arunca."""
	_jurnal(text)
	cale = cale or os.environ.get("HDS_WATCHDOG_LOG", CALE_JURNAL)
	try:
		with open(cale, "a") as f:
			f.write("%s enigma2: %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), text))
	except (OSError, IOError):
		pass


def _scurt(cale):
	"""Calea fisierului fara dosarul de instalare: Components/HdsX.py, Plugins/Extensions/Y/plugin.py, python3.14/z.py."""
	cale = cale or "?"
	i = cale.rfind("/python/")
	if i >= 0:
		return cale[i + 8:]
	i = cale.find("/python3")
	return cale[i + 1:] if i >= 0 else cale


_BUCLA = ("e2reactor.py", "mytest.py", "twisted/")


def locDinCadru(cadru, adancime=200):
	"""Unde e firul principal: (interior, intrare) ca texte „Fisier.py:rand functie” (interior = cadrul care lucreaza acum,
	intrare = primul cadru de dupa bucla enigma2, adica cine a fost chemat din C++), sau None cand firul e in bucla C++
	(cadrul de sus e e2reactor.py, poll: lucreaza cod C++ sau un driver) ori cadrul nu se stie."""
	if cadru is None:
		return None
	cod = cadru.f_code
	fisier = cod.co_filename or ""
	if fisier.endswith("e2reactor.py"):
		return None
	interior = "%s:%d %s" % (_scurt(fisier), cadru.f_lineno, cod.co_name)
	intrare = interior
	c = cadru
	while c is not None and adancime > 0:
		f = c.f_code.co_filename or ""
		if any(b in f for b in _BUCLA):
			break
		intrare = "%s:%d %s" % (_scurt(f), c.f_lineno, c.f_code.co_name)
		c = c.f_back
		adancime -= 1
	return interior, intrare


# HDSatelit 0.7.6 (FRZ, rapoartele 2150, 2149, 2096): „isdir <- Screen.py execBegin” nu spunea cine a chemat isdir, iar
# „os.stat <- ActionMap.action” cu 2 priviri in 11 s nu spunea ca firul principal astepta lacatul Python tinut de alt fir (stat pe
# /tmp nu tine 11 s; paznicul e si el un fir Python si n-a putut privi decat de doua ori). Randul are acum cadrul de mijloc
# (primul cadru din codul imaginii sau al unui plugin de deasupra celui interior) si, cand privirile sunt mult mai putine decat
# secundele, locul cel mai des vazut al celorlalte fire Python care lucreaza.
_ASTEAPTA = ("wait", "_wait_for_tstate_lock", "select", "poll", "accept", "recv", "recv_into", "readline", "sleep",
	"_worker", "join")


def _bibliotecaPython(scurt):
	return scurt.startswith("python3") or scurt.startswith("<frozen") or "/python3." in scurt or "twisted/" in scurt


def mijlocDinCadru(cadru, adancime=200):
	"""Cadrul de mijloc ca text „Fisier.py:rand functie”: deasupra celui interior, primul din codul imaginii sau al unui plugin,
	altul decat intrarea; None cand stiva n-are asa ceva (doua cadre, numai biblioteca)."""
	loc = locDinCadru(cadru)
	if loc is None:
		return None
	interior, intrare = loc
	c = cadru.f_back
	while c is not None and adancime > 0:
		f = c.f_code.co_filename or ""
		if any(b in f for b in _BUCLA):
			return None
		text = "%s:%d %s" % (_scurt(f), c.f_lineno, c.f_code.co_name)
		if text == intrare:
			return None
		if not _bibliotecaPython(_scurt(f)) and text != interior:
			return text
		c = c.f_back
		adancime -= 1
	return None


def _cadreleAltorFire():
	"""[(numele firului, cadrul de sus)] pentru firele Python in afara de cel principal si cel care priveste"""
	try:
		cadre = sys._current_frames()
		nume = dict((t.ident, t.name) for t in threading.enumerate())
		eu, principal = threading.get_ident(), threading.main_thread().ident
		return [(nume.get(i, "fir %s" % i), c) for i, c in cadre.items() if i not in (eu, principal)]
	except Exception:
		return []


def locAltFir(cadru):
	"""Locul de sus al altui fir, sau None cand firul asteapta (wait, get, select, sleep ...) ori e in bucla."""
	if cadru is None:
		return None
	cod = cadru.f_code
	if cod.co_name in _ASTEAPTA:
		return None
	f = cod.co_filename or ""
	if any(b in f for b in _BUCLA):
		return None
	return "%s:%d %s" % (_scurt(f), cadru.f_lineno, cod.co_name)


def _secundeDeLaPornire():
	"""Cate secunde are procesul (/proc/self/stat campul 22 fata de /proc/uptime), sau None."""
	try:
		with open("/proc/self/stat") as f:
			camp = f.read().rsplit(")", 1)[1].split()
		with open("/proc/uptime") as f:
			up = float(f.read().split()[0])
		return max(0.0, up - int(camp[19]) / float(os.sysconf("SC_CLK_TCK")))
	except Exception:
		return None


PRAG_FIR_OCUPAT_S = 3.0         # firul principal tace atat (ceasul de 1 s nu a batut): un rand in jurnalul paznicului
INCA_OCUPAT_S = 60.0            # o tacere care tine atat primeste un rand pe loc (paznicul o poate opri la 120 s)
TIC_S = 1                       # ceasul mic de pe firul principal (numai in memorie, nimic pe disc)
PAS_FIR_S = 1                   # cat de des se uita firul de supraveghere la el
RANDURI_FIR_MAX = 20            # cel mult atatea randuri „ocupat” pe proces
# PLG 0.7.7 (randurile de 3,0-3,6 s cu o singura privire din pachetele 2186, 2206 si din 0.7.6: 2454, 2459, 2500): privirile
# incepeau abia la PRAG_FIR_OCUPAT_S de tacere, deci la o tacere de 3-4 s una singura era chiar numarul asteptat si randul nu
# putea spune nici daca firul principal lucra, nici daca astepta lacatul Python tinut de alt fir. Acum privirile incep de la
# PRAG_PRIVIRI_S, iar randul spune si cat a stat paznicul insusi dupa lacatul Python: un fir care nu poate privi la secunda
# inseamna ca altcineva (alt fir sau C++) tine lacatul fara pauza. Randul se scrie tot ca inainte: numai cand o privire a
# prins tacerea la PRAG_FIR_OCUPAT_S sau mai mult (acelasi numar de randuri, plafonul RANDURI_FIR_MAX neschimbat).
PRAG_PRIVIRI_S = 1.0
PRAG_ASTEPTARE_PAZNIC_S = 1.0
PRAG_PAS_PORNIRE_S = 3.0        # un pas al pornirii (importul, AUTOSTART sau SESSIONSTART al unui plugin) mai lung intra in rand


class FirOcupat(object):
	"""Punctul 10. tic() pe firul principal (eTimer la TIC_S); privire() pe firul de supraveghere, la PAS_FIR_S. Cand
	firul principal tace peste PRAG_FIR_OCUPAT_S, fiecare privire ia locul lui din stiva (locDinCadru); cand tacerea se
	termina, un rand: cat a tinut, la cat timp de la pornire si locul vazut cel mai des. Daca nicio privire nu a prins
	cod Python (firul principal tine lacatul Python in C++, deci firul de supraveghere nu poate rula), randul spune „in
	C++”: atunci stivele paznicului (hds-watchdog.py, peste 120 s) au si firele vazute de nucleu. Nimic pe ecran."""

	def __init__(self, ceas=None, cadru=None, scrie=None, varsta=None, alteFire=None):
		self.ceas = ceas or monotonic
		self.cadru = cadru or _cadrulFiruluiPrincipal
		self.scrie = scrie or jurnalPaznic
		self.varsta = varsta or _secundeDeLaPornire
		self.alteFire = alteFire or _cadreleAltorFire
		self.ultimTic = None
		self.inceput = None     # ultimTic de dinaintea tacerii de acum
		self.priviri = {}
		self.mijloace = {}      # (interior, intrare) -> {mijloc: priviri}
		self.altele = {}        # „numele firului locul” -> priviri (celelalte fire Python care lucrau)
		self.anuntat = False    # randul „inca ocupat” al tacerii de acum
		self.randuri = 0
		self.asteptat = 0.0     # cel mai mult cat a stat paznicul dupa lacatul Python in tacerea de acum (PLG 0.7.7)
		self._intarziere = None  # cat a stat firul paznicului inaintea privirii care urmeaza (intarzierePaznic)
		self.pragVazut = False   # o privire a prins tacerea de acum la PRAG_FIR_OCUPAT_S sau mai mult (randul, ca inainte)

	def tic(self):
		self.ultimTic = self.ceas()

	def _loc(self):
		"""(textul locului, priviri in el, priviri in total): intrarea (cine a fost chemat din bucla) vazuta cel mai des,
		cu cadrul interior cel mai des vazut sub ea; C++ cand nu s-a prins niciun cadru Python."""
		if not self.priviri:
			return "in C++ (bucla enigma2 sau un apel in driver)", 0, 0
		total = sum(self.priviri.values())
		pe_intrare = {}
		for loc, n in self.priviri.items():
			cheie = loc[1] if loc is not None else None
			pe_intrare[cheie] = pe_intrare.get(cheie, 0) + n
		intrare, n = max(pe_intrare.items(), key=lambda x: x[1])
		if intrare is None:
			return "in C++ (bucla enigma2 sau un apel in driver)", n, total
		interior = max(((loc[0], m) for loc, m in self.priviri.items() if loc is not None and loc[1] == intrare),
			key=lambda x: x[1])[0]
		if interior == intrare:
			return interior, n, total
		mijloace = self.mijloace.get((interior, intrare)) or {}
		mijloc = max(mijloace.items(), key=lambda x: x[1])[0] if mijloace else None
		if mijloc:
			return "%s <- %s <- %s" % (interior, mijloc, intrare), n, total
		return "%s <- %s" % (interior, intrare), n, total

	def _lacat(self, durata, total):
		"""„; lacatul Python ...” cand paznicul a privit mult mai rar decat o data pe secunda si alt fir lucra; altfel ''"""
		asteptate = max(1.0, (durata - _pragPriviri() + TIC_S) / float(PAS_FIR_S or 1))
		if total * 2 >= asteptate or not self.altele:
			return ""
		loc, n = max(self.altele.items(), key=lambda x: x[1])
		return "; lacatul Python tinut de alt fir (%d priviri in loc de ~%d): %s (%d)" % (total, int(asteptate), loc, n)

	def _rand(self, durata, inca=False):
		loc, n, total = self._loc()
		varsta = None
		try:
			varsta = self.varsta()
		except Exception:
			pass
		la = (" la %d s dupa pornirea interfetei" % int(varsta)) if varsta is not None else ""
		priviri = (" (%d din %d priviri)" % (n, total)) if total else ""
		fel = "inca ocupat de" if inca else "ocupat"
		asteptat = ("; paznicul a asteptat lacatul Python %.1f s" % self.asteptat) if self.asteptat >= PRAG_ASTEPTARE_PAZNIC_S else ""
		return "firul principal %s %.1f s%s: %s%s%s%s" % (fel, durata, la, loc, priviri, self._lacat(durata, total), asteptat)

	def _scrie(self, rand):
		if self.randuri >= RANDURI_FIR_MAX:
			return None
		self.randuri += 1
		if self.randuri == RANDURI_FIR_MAX:
			rand += "; ultimul rand de acest fel pana la repornirea interfetei"
		self.scrie(rand)
		return rand

	def intarzierePaznic(self, secunde):
		"""Din bucla paznicului, inaintea privirii: cat a stat firul lui peste pas ca sa ruleze din nou (lacatul Python)."""
		self._intarziere = secunde

	def privire(self):
		"""O privire. -> randul scris acum, sau None."""
		intarziere, self._intarziere = self._intarziere, None
		tic = self.ultimTic
		if tic is None:
			return None
		acum = self.ceas()
		if acum - tic >= _pragPriviri():
			if self.inceput != tic:
				self.inceput, self.priviri, self.anuntat = tic, {}, False
				self.mijloace, self.altele = {}, {}
				self.asteptat = 0.0
				self.pragVazut = False
			if intarziere is not None and intarziere > self.asteptat:
				self.asteptat = float(intarziere)
			if acum - tic >= PRAG_FIR_OCUPAT_S:
				self.pragVazut = True
			try:
				cadru = self.cadru()
				loc = locDinCadru(cadru)
				mijloc = mijlocDinCadru(cadru) if loc is not None else None
			except Exception:
				loc, mijloc = None, None
			self.priviri[loc] = self.priviri.get(loc, 0) + 1
			if mijloc:
				m = self.mijloace.setdefault(loc, {})
				m[mijloc] = m.get(mijloc, 0) + 1
			try:
				for nume, c in self.alteFire():
					a = locAltFir(c)
					if a:
						cheie = "%s %s" % (nume, a)
						self.altele[cheie] = self.altele.get(cheie, 0) + 1
			except Exception:
				pass
			if not self.anuntat and acum - tic >= INCA_OCUPAT_S:
				self.anuntat = True
				return self._scrie(self._rand(acum - tic, inca=True))
			return None
		if self.inceput is None:
			return None
		# tacerea s-a terminat: de la ultimul tic dinainte pana la primul de dupa, fara pasul ceasului
		durata = max(0.0, tic - self.inceput - TIC_S)
		rand = None
		# (fara nicio privire in tacere, inceput pus din afara: ca inainte)
		if durata >= PRAG_FIR_OCUPAT_S - TIC_S and not self.anuntat and (self.pragVazut or not self.priviri):
			rand = self._scrie(self._rand(durata))
		self.inceput, self.priviri, self.anuntat = None, {}, False
		self.mijloace, self.altele = {}, {}
		self.asteptat = 0.0
		self.pragVazut = False
		return rand


def _pragPriviri():
	"""de la cata tacere incep privirile (cel mult pragul randului)"""
	return min(PRAG_PRIVIRI_S, PRAG_FIR_OCUPAT_S)


# pasii lenti ai pornirii (inainte de prima bataie firul de supraveghere nu merge: bucla enigma2 inca nu ruleaza)
_pasiPornire = []


def pasPornire(fel, nume, secunde):
	"""Din PluginComponent (import, autostart) si mytest.py (sessionstart), la prima pornire: un pas mai lung de
	PRAG_PAS_PORNIRE_S se tine minte pentru randul pornirii (randPornire, la prima bataie). Nu arunca."""
	try:
		if secunde >= PRAG_PAS_PORNIRE_S and len(_pasiPornire) < 50:
			_pasiPornire.append((float(secunde), str(nume), str(fel)))
			_jurnal("pornirea: %s (%s) a tinut %.1f s" % (nume, fel, secunde))
	except Exception:
		pass


def randPornire(varsta, pasi=None):
	"""Textul randului pornirii, sau None cand pornirea a fost scurta si fara pasi lenti."""
	pasi = sorted(_pasiPornire if pasi is None else pasi, reverse=True)
	if not pasi and (varsta is None or varsta < 60):
		return None
	cat = ("pana la prima bataie %d s" % int(varsta)) if varsta is not None else "durata necunoscuta"
	lenti = ", ".join("%s (%s) %.1f s" % (n, f, s) for s, n, f in pasi[:5]) or "niciun pas mai lung de %d s" % int(PRAG_PAS_PORNIRE_S)
	return "pornirea interfetei: %s; pasii cei mai lenti: %s" % (cat, lenti)


def cerereIesire(cod, ecrane):
	"""Din mytest.py, cand se deschide TryQuitMainloop: un rand cu codul cerut si ecranele deschise (cine a cerut
	repornirea). Iesirea merge mai departe neschimbata; daca omul raspunde Nu, randul paznicului „a iesit” nu urmeaza."""
	try:
		# aceleasi numere ca in tools/enigma2.sh.in si Screens/Standby.py (QUIT_*)
		feluri = {0: "repornirea interfetei", 1: "oprire", 2: "repornirea receptorului", 3: "repornirea interfetei",
			4: "actualizarea afisajului din fata", 5: "cadere"}
		jurnalPaznic("cerere de iesire: cod %s (%s), ecranele: %s" % (cod, feluri.get(cod, "alt cod"),
			" > ".join(ecrane) or "niciunul"))
		_cerere[0] = (cod, list(ecrane))
	except Exception:
		pass


# 0.7.6 (WDG): ultima cerere de iesire (cod, ecrane) vazuta de cerereIesire, pentru semnul iesirii
_cerere = [None]


def _curat(text, maxim=160):
	"""Un singur rand, fara '=' la inceput si fara semne de control, cel mult maxim caractere (pentru semnul iesirii)."""
	return " ".join(str(text).split())[:maxim]


def _codIesireCeruta():
	"""Codul iesirii care incepe: al ferestrei TryQuitMainloop inca deschise (Screens/Standby.py: inTryQuitMainloop si
	quitMainloopCode), altfel None (quitMainloop chemat direct de un plugin, SIGTERM din afara: codul nu se stie)."""
	try:
		from Screens import Standby
		if getattr(Standby, "inTryQuitMainloop", False):
			return int(Standby.quitMainloopCode)
		# 0.7.7 (UPD, dorinelu forum 795 #2668): fara intrebare (nicio inregistrare) TryQuitMainloop se inchide inainte sa
		# se arate, deci inTryQuitMainloop nu se pune; codul il tine acum close(True) (Standby.iesireCeruta). Fara el,
		# repornirea receptorului agatata la iesire ajungea dupa paznic numai repornirea interfetei.
		cod = getattr(Standby, "iesireCeruta", None)
		if cod is not None:
			return int(cod)
	except Exception:
		pass
	return None


def _temaAcum():
	try:
		from Components.config import config
		return config.skin.primary_skin.value
	except Exception:
		return ""


def textSemnIesire(pid, ceas, cod, tema, ecrane):
	"""Textul semnului iesirii cerute: randuri cheie=valoare, citite de hds-watchdog.py (citeste_semn_iesire)."""
	return "pid=%d\nceruta=%.3f\ncod=%s\ntema=%s\necrane=%s\n" % (pid, ceas, "-" if cod is None else int(cod),
		_curat(tema), _curat(" > ".join(ecrane or []), 240))


def iesireInceputa(cale=None, ceas=None, pid=None, cod="implicit", tema=None):
	"""Din mytest.py, imediat dupa runReactor(): bucla principala s-a oprit si incepe iesirea (salvarile, oprirea
	modulelor, apoi oprirea Python). Semnul (pid, ceasul monoton, codul cerut, tema, ecranele) ii spune lui hds-watchdog.py
	ca de acum procesul trebuie sa iasa; daca nu iese in IESIRE_CERUTA_S secunde, il opreste si scrie in hds-caderi.log.
	Scris in RAM, atomic. Nu arunca."""
	try:
		cale = cale or CALE_IESIRE
		if cod == "implicit":
			cod = _codIesireCeruta()
		ecrane = []
		cerere = _cerere[0]
		if cerere is not None and cod is not None and cerere[0] == cod:
			ecrane = cerere[1]
		text = textSemnIesire(os.getpid() if pid is None else pid, monotonic() if ceas is None else ceas, cod,
			_temaAcum() if tema is None else tema, ecrane)
		nou = cale + ".nou"
		with open(nou, "w") as f:
			f.write(text)
		os.rename(nou, cale)
	except Exception as e:
		_jurnal("semnul iesirii: %r" % (e,))


# 0.7.7 (IES, asistenta 695315): firele straine care tin iesirea. Dupa "reached rl -1" (salvarile C++ facute: lista de
# canale, EPG) Py_Finalize cheama threading._shutdown, care asteapta FARA termen toate firele non-daemon. Un plugin sau o
# tema straina care tine un fir non-daemon fara sfarsit (un server web, o descarcare de postere) tinea procesul viu dupa
# iesire, iar paza WDG il oprea abia dupa IESIRE_CERUTA_S (45 s) din hds-watchdog.py: o repornire a interfetei din meniu
# dura ~1,5 minute. pazaFirelorLaIesire (din mytest.py, dupa iesireInceputa) inlocuieste numai pasul de la coada lui
# threading._shutdown (threading._thread_shutdown, Python 3.13 si mai nou), dupa functiile threading._register_atexit:
# firele non-daemon sunt asteptate cel mult ASTEPTARE_FIRE_S secunde (cat ruleaza opkg, pana termina, ca la paznic);
# firele imaginii (numele incep cu PREFIXE_FIRE_IMAGINE: lucruri cu capat, de pilda editorul de canale care scrie lista)
# sunt asteptate mai departe, pana cu MARJA_PAZA_S inaintea pazei, ca inainte de IES; cele ramase se scriu (nume, plugin, loc) in jurnalul paznicului si in hds-caderi.log (acelasi rand o singura data pana
# la repornirea receptorului) si nu mai sunt asteptate. Py_Finalize le trateaza apoi ca pe firele daemon (raman oprite
# cand cer lacatul Python), iar restul iesirii merge ca inainte: functiile atexit (si golirea jurnalului interfetei),
# golirea stdout, codul iesirii pus de enigma2. Nimic salvat nu se pierde: salvarile s-au facut inainte, in mytest.py si
# in C++. Un fir tinut in functiile threading._register_atexit (concurrent.futures) sau alt blocaj din Py_Finalize ramane
# la paza de 45 s.
ASTEPTARE_FIRE_S = 5.0          # cat mai asteapta iesirea firele non-daemon dupa salvari
PAZA_IESIRE_S = 45              # IESIRE_CERUTA_S din hds-watchdog.py, socotita de la iesireInceputa
MARJA_PAZA_S = 5                # asteptarea se termina cu atatea secunde inaintea pazei
PAS_FIRE_S = 0.25               # cat de des se uita la firele asteptate
PREFIXE_FIRE_IMAGINE = ("Hds", "hds-")   # numele firelor imaginii (firele straine nu le folosesc)
CALE_CADERI = "/home/root/logs/hds-caderi.log"
CALE_FIRE_IESIRE = "/tmp/hds-fire-iesire.semn"   # firele ultimului rand din hds-caderi.log (RAM: pana la repornire)
MAX_RAND_FIRE = 600
_pazaFire = [None]              # (ceasul monoton al instalarii, threading._thread_shutdown de dinainte)


def fireleCareTinIesirea(fire=None, eu=None):
	"""Firele pe care threading._shutdown le-ar astepta: non-daemon, vii, altele decat firul care iese si cel principal."""
	if fire is None:
		fire = threading.enumerate()
	if eu is None:
		eu = threading.current_thread()
	principal = threading.main_thread()
	rez = []
	for t in fire:
		try:
			if t is not eu and t is not principal and not t.daemon and t.is_alive():
				rez.append(t)
		except Exception:
			pass
	return rez


def alImaginii(fir):
	"""True pentru un fir al imaginii (dupa nume, PREFIXE_FIRE_IMAGINE)."""
	return str(getattr(fir, "name", "") or "").startswith(PREFIXE_FIRE_IMAGINE)


def asteaptaFirele(fire, termen_s, ocupat=None, ceas=None, pas=PAS_FIRE_S):
	"""Asteapta firele cel mult termen_s secunde; dupa termen, mai departe numai cat ocupat() e adevarat (opkg ruleaza:
	o iesire acum l-ar opri la jumatate). -> firele inca vii."""
	ceas = ceas or monotonic
	sfarsit = ceas() + max(0.0, termen_s)
	while True:
		vii = [t for t in fire if t.is_alive()]
		if not vii:
			return []
		ramas = sfarsit - ceas()
		if ramas <= 0:
			try:
				mai_asteapta = bool(ocupat is not None and ocupat())
			except Exception:
				mai_asteapta = False
			if not mai_asteapta:
				return vii
			ramas = pas
		try:
			vii[0].join(min(pas, ramas))
		except Exception:
			return [t for t in fire if t.is_alive()]


def _opkgOcupat():
	"""True cat ruleaza opkg (Components/HdsActualizari.instalare_in_curs)."""
	try:
		from Components.HdsActualizari import instalare_in_curs
		return bool(instalare_in_curs())
	except Exception:
		return False


def descriereFir(fir, cadru=None, pluginDinCale=None):
	"""Un fir ramas pe scurt: numele (fara numele modulelor de acces, ca in fisierul stivelor), pluginul extern din stiva
	lui, unde sta acum si primul cadru din afara bibliotecii Python (al cui e codul)."""
	text = _textFir(getattr(fir, "name", "?")) or "?"
	if cadru is None:
		return text
	try:
		plugin = pluginExternInStiva(cadru, pluginDinCale)
	except Exception:
		plugin = None
	if plugin:
		text += " [%s]" % _textFir(plugin)
	sus = "%s:%d %s" % (_scurt(cadru.f_code.co_filename), cadru.f_lineno, cadru.f_code.co_name)
	text += " la %s" % sus
	c, adancime = cadru, 200
	while c is not None and adancime > 0:
		scurt = _scurt(c.f_code.co_filename)
		if not _bibliotecaPython(scurt):
			loc = "%s:%d %s" % (scurt, c.f_lineno, c.f_code.co_name)
			if loc != sus:
				text += " din %s" % loc
			break
		c = c.f_back
		adancime -= 1
	return text


def textFireRamase(fire, cadre=None, pluginDinCale=None):
	"""(cheia, textul) pentru firele ramase: cheia = descrierile lor (aceleasi fire, acelasi rand), textul = randul din
	jurnale, cel mult MAX_RAND_FIRE caractere."""
	if cadre is None:
		try:
			cadre = sys._current_frames()
		except Exception:
			cadre = {}
	cheie = ", ".join(descriereFir(t, cadre.get(t.ident), pluginDinCale) for t in fire)
	text = "enigma2 pid=%d: iesirea nu mai asteapta firele non-daemon ramase dupa salvari (%d): %s" % (
		os.getpid(), len(fire), cheie)
	return cheie, text[:MAX_RAND_FIRE]


def scrieRandCaderi(text, cheie, cale=None, cale_semn=None):
	"""Randul in hds-caderi.log ("AAAA-LL-ZZ HH:MM:SS text", ca hds-watchdog.py si enigma2.sh), cu fsync; acelasi rand
	(aceeasi cheie) o singura data pana la repornirea receptorului, ca o repornire des a interfetei sa nu impinga caderile
	adevarate afara din jurnal. -> True daca l-a scris. Nu arunca."""
	cale = cale or os.environ.get("HDS_CADERI_JURNAL") or CALE_CADERI
	cale_semn = cale_semn or CALE_FIRE_IESIRE
	try:
		with open(cale_semn, encoding="utf-8", errors="replace") as f:
			if f.read() == cheie:
				return False
	except (OSError, IOError):
		pass
	try:
		dosar = os.path.dirname(cale)
		if dosar and not os.path.isdir(dosar):
			os.makedirs(dosar)
		with open(cale, "a", encoding="utf-8") as f:
			f.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), text))
			f.flush()
			os.fsync(f.fileno())
	except (OSError, IOError):
		return False
	try:
		with open(cale_semn, "w", encoding="utf-8") as f:
			f.write(cheie)
	except (OSError, IOError):
		pass
	return True


def _asteaptaFireleLaIesire():
	"""threading._thread_shutdown cat iese enigma2 (chemat de threading._shutdown din Py_Finalize): firele non-daemon
	asteptate cu termen (ale imaginii pana aproape de paza); cele ramase scrise si lasate. Fara fire ramase (sau la o
	eroare inainte de hotarare), pasul de dinainte. Hotararea nu depinde de scrierea in jurnale."""
	# 0.7.8 (SSO): aici s-au terminat salvarile C++ (~eMain: lista de canale, ghidul); randul iesirii le masoara
	_pasiIesire["fire"] = monotonic()
	if _pazaFire[0] is None:
		return None
	inceput, vechi = _pazaFire[0]
	try:
		pana_la_paza = PAZA_IESIRE_S - MARJA_PAZA_S - (monotonic() - inceput)
		fire = fireleCareTinIesirea()
		ramase = asteaptaFirele(fire, max(0.0, min(ASTEPTARE_FIRE_S, pana_la_paza)), _opkgOcupat) if fire else []
		ale_imaginii = [t for t in ramase if alImaginii(t)]
		if ale_imaginii:
			pana_la_paza = PAZA_IESIRE_S - MARJA_PAZA_S - (monotonic() - inceput)
			ramase = [t for t in ramase if not alImaginii(t)] + asteaptaFirele(ale_imaginii, max(0.0, pana_la_paza),
				_opkgOcupat)
	except Exception as e:
		_jurnal("firele la iesire: %r" % (e,))
		return vechi()
	if not ramase:
		return vechi()
	try:
		cheie, text = textFireRamase(ramase)
		jurnalPaznic(text)
		scrieRandCaderi(text, cheie)
	except Exception as e:
		try:
			_jurnal("firele la iesire, jurnalul: %r" % (e,))
		except Exception:
			pass
	return None
_asteaptaFireleLaIesire._hds_iesire = True


def pazaFirelorLaIesire(modul=None, ceas=None):
	"""Din mytest.py, dupa iesireInceputa: pune _asteaptaFireleLaIesire in locul lui threading._thread_shutdown, pentru
	Py_Finalize. -> False cand Python-ul nu are acel pas (inainte de 3.13): iesirea asteapta firele ca inainte. Nu arunca."""
	modul = threading if modul is None else modul
	try:
		vechi = getattr(modul, "_thread_shutdown", None)
		if not callable(vechi):
			_jurnal("firele la iesire: fara threading._thread_shutdown (Python %s), le asteapta ca inainte"
				% sys.version.split()[0])
			return False
		if getattr(vechi, "_hds_iesire", False) is True:
			return True
		_pazaFire[0] = (monotonic() if ceas is None else ceas, vechi)
		modul._thread_shutdown = _asteaptaFireleLaIesire
		return True
	except Exception as e:
		_jurnal("firele la iesire: %r" % (e,))
		return False



# 0.7.8 (SSO, e-mailurile 6529 si 6531, Vu+ Solo SE): CAT TINE IESIREA INTERFETEI SI CE O TINE. Omul vede ecranul negru
# (sau textul iesirii) cat iese interfata, dar jurnalele nu spuneau ce pas tine: randul "a iesit" din hds-watchdog.py se
# scrie la verificarea paznicului (din 15 in 15 s), nu la iesire, de unde se citise 7-15 s in loc de 3-9 s. Acum fiecare
# pas are ceasul lui (time.monotonic), iar la atexit (dupa salvarile C++ si dupa paza firelor IES) un rand merge in
# jurnalul paznicului (deci in pachetul beta testerului) si in hds-interfata.log:
#   iesirea interfetei pana la curatenia Python: 1.6 s (cod 3); pasii cei mai lenti: salvarile C++ (...) 1.0 s, ...
# DUPA atexit mai urmeaza curatenia Python din Py_Finalize si iesirea din nucleu, pe care randul nu le vede: masurat pe
# doua receptoare ARM de proba, 0.7.7, cea mai mare parte a iesirii (3,0-3,5 s din 4,5-5,2 s), aproape toata in
# trecerile complete ale GC peste tot heap-ul. De aceea:
# - la atexit se scriu in semnul iesirii (CALE_IESIRE) ora cererii si ora atexit (pe /proc/uptime), iar enigma2.sh scrie
#   ora exacta a sfarsitului procesului (sfarsit= in /tmp/hds-enigma2.iesire); la pornirea urmatoare randul
#   "iesirea de dinainte" spune durata adevarata, de la cerere pana dispare procesul, si cat a tinut partea de dupa atexit;
# - CURATENIE_RAPIDA: la atexit, dupa ce totul e salvat (setarile, listele, ghidul, CEC, jurnalele), gc.freeze() muta
#   toate obiectele in generatia permanenta, deci trecerile GC din Py_Finalize nu le mai parcurg. Raman ca inainte:
#   functiile atexit inregistrate inainte (golirea jurnalelor, logging, weakref.finalize), golirea stdout, codul iesirii
#   pus de enigma2, golirea modulelor inca folosite de altele (obiectele lor fara cicluri se distrug prin numarare).
#   CE SE PIERDE (Python nu garanteaza oricum finalizatorii la iesire; proba test_sso_pasi_iesire_078): nu se mai distrug
#   obiectele prinse in cicluri care sunt gunoi la iesire (si cele ramase de mai demult, si cele care devin gunoi la
#   golirea modulelor) si nici cele tinute numai de dictionarul unui modul pe care nu-l mai foloseste nimeni
#   (dictionarul e in ciclu cu functiile lui), de pilda globalele din mytest.py. Memoria si
#   fisierele deschise le elibereaza nucleul. Urmari posibile: un fisier lasat deschis de un plugin nu-si goleste
#   tamponul, iar un proces copil pornit de un plugin printr-un eConsoleAppContainer tinut asa nu mai e oprit la
#   repornirea interfetei (la oprire si la repornirea receptorului il opreste sistemul; pe receptoarele de proba enigma2
#   nu avea niciun copil cand era liniste). Obiectele C++ legate de Python se distrug mai rar dupa "reached rl -1", deci
#   si caderile 139 de la iesire vazute pe receptorul de proba au mai putine prilejuri (DEDUS).
# Pasii: de la cererea omului (Screens/Standby.py, TryQuitMainloop.close: iesireCerutaLa) pana la quitMainloop
# (iesireQuitLa) = "textul si CEC" (textul pe ecran, mesajele CEC si HDMI la oprire); pana la intoarcerea din runReactor =
# "bucla"; apoi fiecare pas din mytest.py (pasIesire dupa el: timpul de la marcajul de dinainte); de la ultimul pas Python
# pana la paza firelor din Py_Finalize = "salvarile C++ (lista de canale, ghidul)" (~eMain: lamedb, epg.dat, nivelurile
# C++); de acolo pana la atexit = "firele ramase" (paza firelor IES; fara ea, Python vechi, cele doua intr-un pas). O
# iesire care nu vine din TryQuitMainloop (quitMainloop chemat de un plugin, SIGTERM) se masoara de la sfarsitul buclei.
# Numai ceasuri si un rand scris: ce se salveaza si ordinea pasilor nu se schimba.
PRAG_PAS_IESIRE_S = 0.2         # pasii mai scurti nu se numesc in rand (intra numai in total)
CURATENIE_RAPIDA = True         # gc.freeze() la atexit, dupa salvari (vezi mai sus)
CALE_IESIRE_SH = "/tmp/hds-enigma2.iesire"   # semnul scris de enigma2.sh dupa iesire (cod, uptime, parinte, sfarsit)
PASI_IESIRE_IN_RAND = 6         # cati pasi lenti se numesc
CEREREA_VECHE_S = 120           # o ora a cererii mai veche de atat nu e a acestei iesiri
_pasiIesire = {"inceput": None, "ultim": None, "pasi": [], "cod": None, "fire": None, "inregistrat": False}


def _oraStandby(nume):
	"""Ora (monotonic) pusa de Screens/Standby.py la cererea iesirii (iesireCerutaLa, iesireQuitLa), sau None."""
	try:
		from Screens import Standby
		v = getattr(Standby, nume, None)
		return None if v is None else float(v)
	except Exception:
		return None


def incepePasiiIesirii(cod="implicit", ceas=None, cerere="implicit", quit_la="implicit", inregistreaza=True):
	"""Din mytest.py, imediat dupa iesireInceputa (bucla s-a oprit): primii pasi din orele lui Standby.py si randul de la
	sfarsit (atexit). Nu arunca: iesirea nu depinde de el."""
	try:
		if cod == "implicit":
			cod = _codIesireCeruta()
		acum = monotonic() if ceas is None else ceas
		cerere = _oraStandby("iesireCerutaLa") if cerere == "implicit" else cerere
		quit_la = _oraStandby("iesireQuitLa") if quit_la == "implicit" else quit_la
		if cerere is not None and not 0 <= acum - cerere <= CEREREA_VECHE_S:
			cerere = None
		pasi = []
		if cerere is not None:
			if quit_la is not None and cerere <= quit_la <= acum:
				pasi.append(("textul si CEC", quit_la - cerere))
				pasi.append(("bucla", acum - quit_la))
			else:
				pasi.append(("bucla", acum - cerere))
		_pasiIesire.update(inceput=acum if cerere is None else cerere, ultim=acum, pasi=pasi, cod=cod, fire=None)
		if inregistreaza and not _pasiIesire["inregistrat"]:
			import atexit
			atexit.register(laSfarsitulIesirii)
			_pasiIesire["inregistrat"] = True
	except Exception as e:
		_jurnal("pasii iesirii: %r" % (e,))


def pasIesire(nume, ceas=None):
	"""Din mytest.py, dupa fiecare pas al iesirii: timpul de la marcajul de dinainte, pe numele pasului. Nu arunca."""
	try:
		if _pasiIesire["ultim"] is None:
			return
		acum = monotonic() if ceas is None else ceas
		_pasiIesire["pasi"].append((str(nume), max(0.0, acum - _pasiIesire["ultim"])))
		_pasiIesire["ultim"] = acum
	except Exception:
		pass


def randIesire(total, pasi, cod=None, prag=PRAG_PAS_IESIRE_S, cati=PASI_IESIRE_IN_RAND):
	"""Textul randului iesirii: totalul pana la atexit, codul si pasii cei mai lungi peste prag (cel mai lung intai)."""
	lungi = sorted([(s, n) for n, s in pasi if s >= prag], key=lambda x: -x[0])[:cati]
	text = "iesirea interfetei pana la curatenia Python: %.1f s" % max(0.0, total)
	if cod is not None:
		text += " (cod %s)" % cod
	if lungi:
		return text + "; pasii cei mai lenti: " + ", ".join("%s %.1f s" % (n, s) for s, n in lungi)
	return text + "; niciun pas peste %.1f s" % prag


def pasiiIesirii(ceas=None):
	"""(totalul, pasii) de pana acum, cu pasii C++ si firele socotiti din ora pazei firelor; None inainte de inceput."""
	if _pasiIesire["inceput"] is None or _pasiIesire["ultim"] is None:
		return None
	acum = monotonic() if ceas is None else ceas
	ultim, fire = _pasiIesire["ultim"], _pasiIesire["fire"]
	pasi = list(_pasiIesire["pasi"])
	if fire is not None and ultim <= fire <= acum:
		pasi.append(("salvarile C++ (lista de canale, ghidul)", fire - ultim))
		pasi.append(("firele ramase", acum - fire))
	else:
		pasi.append(("salvarile C++ si firele", max(0.0, acum - ultim)))
	return acum - _pasiIesire["inceput"], pasi


def _uptime():
	"""/proc/uptime ca float (acelasi ceas cu enigma2.sh), sau None."""
	try:
		with open("/proc/uptime") as f:
			return float(f.read().split()[0])
	except (OSError, IOError, ValueError, IndexError):
		return None


def _citesteSemn(cale):
	"""Randurile cheie=valoare ale unui semn mic din RAM, ca dict (gol daca lipseste)."""
	d = {}
	try:
		with open(cale, encoding="utf-8", errors="replace") as f:
			text = f.read(4096)
	except (OSError, IOError):
		return d
	for rand in text.splitlines():
		cheie, semn, valoare = rand.partition("=")
		if semn:
			d[cheie.strip()] = valoare.strip()
	return d


def scrieOreleIesirii(inceput, ceas=None, cale=None, up=None, parinte=None):
	"""La atexit: ora cererii si ora atexit (pe /proc/uptime) adaugate la semnul iesirii, atomic, pentru randul de la
	pornirea urmatoare. Cheile noi (cerere_up, atexit_up, parinte) nu schimba ce citesc hds-watchdog.py si enigma2.sh."""
	cale = cale or CALE_IESIRE
	acum = monotonic() if ceas is None else ceas
	up = _uptime() if up is None else up
	if up is None or inceput is None:
		return False
	try:
		with open(cale, encoding="utf-8", errors="replace") as f:
			text = f.read(4096)
	except (OSError, IOError):
		text = ""
	randuri = [r for r in text.splitlines() if r.partition("=")[0] not in ("cerere_up", "atexit_up", "parinte")]
	randuri += ["cerere_up=%.2f" % (up - max(0.0, acum - inceput)), "atexit_up=%.2f" % up,
		"parinte=%d" % (os.getppid() if parinte is None else parinte)]
	try:
		nou = cale + ".nou"
		with open(nou, "w") as f:
			f.write("\n".join(randuri) + "\n")
		os.replace(nou, cale)
		return True
	except (OSError, IOError):
		return False


def curatenieRapida(modul_gc=None):
	"""La atexit, dupa salvari: gc.freeze() (vezi CURATENIE_RAPIDA). -> True daca s-a facut."""
	if not CURATENIE_RAPIDA:
		return False
	try:
		g = modul_gc
		if g is None:
			import gc as g
		congeleaza = getattr(g, "freeze", None)
		if congeleaza is None:
			return False
		congeleaza()
		return True
	except Exception:
		return False


def laSfarsitulIesirii(ceas=None, scrie=None, modul_gc=None):
	"""atexit (ruleaza primul dintre functiile atexit, fiind inregistrat la urma): randul iesirii pana la curatenia
	Python, orele in semnul iesirii, apoi curatenia rapida. O singura data. -> textul sau None. Nu arunca."""
	try:
		rez = pasiiIesirii(ceas)
		if rez is None:
			return None
		inceput = _pasiIesire["inceput"]
		_pasiIesire["inceput"] = None
		text = randIesire(rez[0], rez[1], _pasiIesire["cod"])
		(scrie or jurnalPaznic)(text)
		scrieOreleIesirii(inceput, ceas)
		curatenieRapida(modul_gc)
		return text
	except Exception as e:
		try:
			_jurnal("randul iesirii: %r" % (e,))
		except Exception:
			pass
		return None


def randIesireDeDinainte(semn=None, semn_sh=None):
	"""La pornire (porneste, inainte sa stearga semnul): durata adevarata a iesirii procesului de dinainte, din orele
	scrise la atexit si din sfarsitul scris de enigma2.sh (acelasi parinte). -> textul sau None."""
	d = _citesteSemn(CALE_IESIRE) if semn is None else semn
	sh = _citesteSemn(os.environ.get("HDS_IESIRE", CALE_IESIRE_SH)) if semn_sh is None else semn_sh
	try:
		if not d.get("parinte") or d.get("parinte") != sh.get("parinte"):
			return None
		cerere, atexit_up, sfarsit = float(d["cerere_up"]), float(d["atexit_up"]), float(sh["sfarsit"])
	except (KeyError, ValueError):
		return None
	if not cerere <= atexit_up <= sfarsit or sfarsit - cerere > 600:
		return None
	return ("iesirea de dinainte (pid %s, cod %s): %.1f s de la cerere pana la sfarsitul procesului, din care %.1f s "
		"dupa atexit (curatenia Python si iesirea din nucleu)" % (d.get("pid", "?"), sh.get("cod", d.get("cod", "?")),
		sfarsit - cerere, sfarsit - atexit_up))


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
	# 0.7.8 (SSO): inainte, cat a tinut de fapt iesirea procesului de dinainte (randul "iesirea de dinainte")
	try:
		rand = randIesireDeDinainte()
		if rand:
			jurnalPaznic(rand)
	except Exception as e:
		_jurnal("iesirea de dinainte: %r" % (e,))
	# 0.7.6 (WDG): semnul iesirii ramas de la procesul de dinainte nu mai conteaza (hds-watchdog.py cere si pid-ul lui)
	try:
		os.remove(CALE_IESIRE)
	except OSError:
		pass
	initConfig()
	bataie().porneste()
	_jurnal("bataia pornita (%s, la %d s)" % (bataie().cale, BATAIE_S))
	# punctul 10: cat a tinut pornirea si pasii ei lenti (pluginurile), un rand in jurnalul paznicului
	try:
		rand = randPornire(_secundeDeLaPornire())
		if rand:
			jurnalPaznic(rand)
	except Exception as e:
		_jurnal("randul pornirii: %r" % (e,))
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


# ---------------------------------------------------------------- punctul 11: stivele tuturor firelor, la cererea paznicului

CALE_CERERE_STIVE = "/tmp/hds-stive-%d.cerere"   # teava (FIFO) pe care hds-watchdog.py cere stivele; %d = pid-ul enigma2
PREFIX_CERERE_STIVE = "hds-stive-"
MAX_CADRE_STIVA = 100                             # cat scrie faulthandler pentru un fir
SFARSIT_STIVE = "# sfarsit cererea "              # ultimul rand al raspunsului, cu semnul cererii (paznicul il cauta)


def _textFir(nume):
	"""Numele firului pentru randul cu # (ramane in fisierul de pe receptor): litere, cifre si semnele obisnuite; al unui
	modul de acces e numai "(modul-acces)"."""
	nume = "".join(c for c in str(nume)[:40] if c.isalnum() or c in " _.-()[]")
	return "(modul-acces)" if "cam" in nume.lower() else nume


def _numeFire():
	"""{ident: numele firului}, fara lacatul din threading (firul principal poate sta oriunde cand se cer stivele)."""
	try:
		return dict((t.ident, t.name) for t in list(threading._active.values()))
	except Exception:
		return {}


def textStive(cadre, nume=None, principal=None, eu=None, cerere=""):
	"""Stivele firelor (cadre: {ident: cadrul de sus}, ca sys._current_frames()) in forma faulthandler, pe care o citesc
	raportul pornirii (tools/hds-raport.sh, rp_stive), pachetul beta testerului (HdsBetaTester.stiveCurate) si raportul de
	procesor: antetul "Thread 0x... (most recent call first):" (firul principal "Current thread", ca in stivele paznicului
	de pana acum), apoi '  File "cale", line N in functie', cadrul de sus primul, cel mult MAX_CADRE_STIVA, si un rand gol.
	Firul care scrie nu apare. Numele firelor stau pe randuri cu #, pe care cititorii de mai sus le lasa deoparte. Ultimul
	rand: SFARSIT_STIVE si semnul cererii. Numai lucruri deja incarcate: nimic importat, niciun lacat de luat."""
	nume = nume or {}
	r = ["# stivele tuturor firelor Python ale enigma2, citite din Python la cererea paznicului"]
	for ident in sorted(cadre, key=lambda i: (i != principal, i)):
		if ident == eu:
			continue
		adresa = ident & 0xFFFFFFFFFFFFFFFF
		r.append("# fir: %s" % _textFir(nume.get(ident, "?")))
		r.append("%s 0x%0*x (most recent call first):" % ("Current thread" if ident == principal else "Thread",
			8 if adresa < (1 << 32) else 16, adresa))
		c, n = cadre[ident], 0
		if c is None:
			r.append("  <no Python frame>")
		while c is not None and n < MAX_CADRE_STIVA:
			cod = c.f_code
			rand = c.f_lineno
			r.append('  File "%s", line %s in %s' % (cod.co_filename, rand if rand is not None else "???", cod.co_name))
			c = c.f_back
			n += 1
		r.append("")
	r.append(SFARSIT_STIVE + cerere)
	return "\n".join(r) + "\n"


def _semnCerere(date):
	"""semnul cererii din ce a scris paznicul (ultimul cuvant, numai litere si cifre)"""
	cuvinte = date.decode("ascii", "replace").split()
	return "".join(c for c in cuvinte[-1] if c.isalnum())[:32] if cuvinte else ""


class StiveLaCerere(object):
	"""Punctul 11 (0.7.7). Un fir al imaginii asteapta cererile paznicului (hds-watchdog.py, cere_stivele) pe teava
	CALE_CERERE_STIVE si scrie stivele tuturor firelor Python la coada fisierului de stive, acelasi pe care il primeste
	faulthandler in mytest.py, in aceeasi forma. Citite din Python (sys._current_frames, cu lacatul Python luat), stivele
	celorlalte fire nu se schimba sub citire; citite din manerul de semnal (faulthandler cu toate firele), cat alt fir ruleaza
	cod Python, au oprit enigma2 (SIGSEGV in libpython, 1 din ~318 pe receptorul de proba). Cand lacatul Python e tinut (interfata chiar
	sta), firul nu poate raspunde, iar paznicul trece la faulthandler: atunci niciun alt fir nu ruleaza cod Python."""

	def __init__(self, fd, cale=None, pid=None):
		self.fd = fd
		self.pid = pid or os.getpid()
		self.cale = cale or (CALE_CERERE_STIVE % self.pid)
		self.citire = None
		self.fir = None

	def deschide(self):
		"""Teava acestui proces, noua; tevile ramase de la procese care nu mai exista se sterg."""
		dosar = os.path.dirname(self.cale) or "."
		try:
			for n in os.listdir(dosar):
				if not (n.startswith(PREFIX_CERERE_STIVE) and n.endswith(".cerere")):
					continue
				try:
					pid = int(n[len(PREFIX_CERERE_STIVE):-len(".cerere")])
				except ValueError:
					continue
				if pid != self.pid and not _procesExista(pid):
					try:
						os.remove(os.path.join(dosar, n))
					except OSError:
						pass
		except OSError:
			pass
		try:
			os.remove(self.cale)
		except OSError:
			pass
		os.mkfifo(self.cale, 0o600)
		# O_RDWR: deschiderea nu asteapta un scriitor, iar citirea asteapta (nu intoarce sfarsitul) dupa ce paznicul inchide
		self.citire = os.open(self.cale, os.O_RDWR)

	def raspunde(self, cerere=""):
		"""Stivele o data, intr-o singura scriere la coada fisierului. Nu arunca."""
		try:
			text = textStive(sys._current_frames(), _numeFire(), threading.main_thread().ident, threading.get_ident(),
				cerere)
		except Exception as e:
			text = "# stivele nu s-au putut citi: %s\n%s%s\n" % (type(e).__name__, SFARSIT_STIVE, cerere)
		date = text.encode("utf-8", "replace")
		try:
			while date:
				date = date[os.write(self.fd, date):]
		except OSError:
			pass

	def _bucla(self):
		while True:
			try:
				date = os.read(self.citire, 256)
			except OSError:
				return
			if not date:
				return
			self.raspunde(_semnCerere(date))

	def porneste(self):
		self.deschide()
		self.fir = threading.Thread(target=self._bucla, name="hds-stive")
		self.fir.daemon = True
		self.fir.start()


_stiveLaCerere = [None]


def pornesteStiveLaCerere(fisier):
	"""Din capul mytest.py, cu fisierul de stive deschis la coada (acelasi ca al faulthandler). -> StiveLaCerere sau None.
	Nu arunca."""
	if _stiveLaCerere[0] is None:
		try:
			s = StiveLaCerere(fisier if isinstance(fisier, int) else fisier.fileno())
			s.porneste()
			_stiveLaCerere[0] = s
		except Exception as e:
			_jurnal("stivele la cererea paznicului: %r" % (e,))
	return _stiveLaCerere[0]
