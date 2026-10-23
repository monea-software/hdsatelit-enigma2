# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# CamSetup.py: ecranul „Module de acces condiționat” (meniul Acces condiționat), modulele de acces si serverele de
# carduri instalate pe receptor.
#   - lista = numai modulele instalate: scripturile /etc/init.d/<fel>.<x> puse de pachetele lor, plus „Niciunul”
#     (si scripturile serverelor de carduri, numai cand e instalat vreunul); niciun executabil ghicit din /usr/bin;
#     felurile le afla Components/HdsModuleAcces.py dupa forma, fara nume scrise in cod;
#   - fiecare rand spune daca modulul e ales (legatura /etc/init.d/<fel>, pornita la pornirea receptorului) si
#     daca ruleaza (din /proc, fara comenzi pornite pe firul enigma2);
#   - Verde alege si porneste, Rosu opreste, Galben reporneste, numai prin scriptul modulului, fara sa blocheze,
#     cu mesaj cand scriptul a terminat sau a cazut; niciun semnal trimis direct unui proces;
#   - Albastru (0.2.8): interfata web proprie a modulului care ruleaza, deschisa PE TELEVIZOR,
#     neschimbata, in navigatorul imaginii (Plugins/Extensions/HdsNavigator, modul cam: numai adresa ei de pe receptor,
#     127.0.0.1:<portul ei>, aflata la rulare de Components/HdsInterfeteCam.py). Aici nu se citeste si nu se schimba
#     nimic din modul (nici cititoare, nici linii): ce se poate face in pagina lui hotaraste pagina lui. Fara modul
#     pornit: un mesaj, navigatorul nu porneste. INFO deschide „Informații despre decriptare” (Screens/CamInfo.py),
#     care era inainte pe Albastru;
#   - numai cu sagetile si OK: OK pe un modul care ruleaza deschide o lista scurta (Oprește, Repornește, Interfața web,
#     Despre decriptare, si Alege cand nu e ales); pe unul oprit sau pe „Niciunul”, OK face ce face Verde;
#   - detaliile (memoria si firele procesului, in cuvinte simple) se rescriu numai cand s-a schimbat ceva, iar pagina
#     derulata cu Stanga / Dreapta ramane la citirea din 5 in 5 secunde.
# Toata logica e in Components/HdsModuleAcces.py (aceeasi o foloseste interfata web,
# HdsWebControl/acces_conditionat_web.py); ecranul doar o arata. text_rezultat si pid_de_aratat sunt folosite si de pagina web, ca textele sa fie aceleasi.
from enigma import eTimer

from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.MenuList import MenuList
from Components.ScrollLabel import ScrollLabel
from Components.Sources.StaticText import StaticText
from Components import HdsModuleAcces
from Components import HdsInterfeteCam

REIMPROSPATARE = 5000   # ms: starea (ce ruleaza) se reciteste cat timp ecranul e deschis


def _vmrss(sistem, pid):
	"""VmRSS in kB din /proc/<pid>/status, sau -1 cand nu se poate citi"""
	for r in HdsModuleAcces.memorie(sistem, pid):
		parti = r.split()
		if parti[0] == "VmRSS:" and len(parti) > 1 and parti[1].isdigit():
			return int(parti[1])
	return -1


def pid_de_aratat(sistem, pids):
	"""Procesul care lucreaza, dintre cele pornite de acelasi script (HdsModuleAcces.Emulator.pids). Un emulator cu paznic
	intern are doua procese cu acelasi executabil: paznicul (mic, un fir, fara dispozitive) si copilul, care decripteaza.
	Se alege procesul care tine socketul de decriptare (HdsInterfeteCam.SOCKET_DECRIPTARE) sau un cititor de carduri /
	un dispozitiv CA; cand nu se vede niciunul (fara drept de citire in /proc/<pid>/fd), cel cu VmRSS cel mai mare;
	la egalitate, primul. None fara procese."""
	pids = list(pids or [])
	if len(pids) < 2:
		return pids[0] if pids else None
	socketuri = HdsInterfeteCam.inode_decriptare(sistem)
	for pid in pids:
		p = HdsInterfeteCam.citeste_proces(sistem, pid)
		if p is None:
			continue
		if p.socketuri & socketuri:
			return pid
		for d in p.dispozitive:
			if HdsInterfeteCam._CITITOR_CARD.match(d) or HdsInterfeteCam._CA.match(d):
				return pid
	return max(pids, key=lambda pid: _vmrss(sistem, pid))


def randuri_proces(linii):
	"""randurile din /proc/<pid>/status (HdsModuleAcces.memorie sau fisierul intreg) spuse simplu: memoria folosita
	(VmRSS, in MB rotunjiti, cel putin 1) si firele de lucru (Threads); restul randurilor nu se arata"""
	rez = []
	for r in linii:
		parti = r.split()
		if len(parti) < 2 or not parti[1].isdigit():
			continue
		if parti[0] == "VmRSS:":
			rez.append(_("Memoria folosită: %s MB") % max(1, int(round(int(parti[1]) / float(1 << 10)))))
		elif parti[0] == "Threads:":
			rez.append(_("Fire de lucru: %s") % parti[1])
	return rez


def _alegere():
	"""ChoiceBox cu toate actiunile hartilor lui tratate: ChoiceBox leaga si DirectionActions, dar trateaza numai up /
	down, deci fiecare eliberare a unei sageti ar scrie „unknown action” in jurnal"""
	from .ChoiceBox import ChoiceBox

	class Alegere(ChoiceBox):
		def __init__(self, session, **k):
			ChoiceBox.__init__(self, session, **k)
			actiuni = self["actions"].actions
			for nume in ("left", "right", "upUp", "downUp", "leftUp", "rightUp", "upRepeated", "downRepeated",
					"leftRepeated", "rightRepeated"):
				actiuni.setdefault(nume, self.nimic)

		def nimic(self):
			pass
	return Alegere


def _eticheta(fel, nume, principal):
	"""numele randului: al modulelor obisnuite (felul `principal`, primul din HdsModuleAcces.feluri) fara nimic in
	fata, al serverelor de carduri cu "Server de carduri:" in fata"""
	if fel == principal:
		return nume
	return _("Server de carduri: %s") % nume


def text_rezultat(r):
	"""mesajul pentru rezultatul unei operatii (HdsModuleAcces.Operatie)"""
	nume = r.get("nume") or ""
	m = r.get("motiv")
	if m == "ales":
		text = _("%s a pornit.") % nume + " " + _("Pornește la fiecare pornire a receptorului.")
	elif m == "niciunul":
		text = _("La pornirea receptorului nu pornește niciun modul.")
	elif m == "pornit":
		text = _("%s a pornit.") % nume
	elif m == "oprit":
		text = _("%s s-a oprit.") % nume
		if r.get("ramane_ales"):
			text += " " + _("Rămâne ales: pornește din nou la pornirea receptorului.")
	elif m == "repornit":
		text = _("%s a repornit.") % nume
	elif m == "ruleaza_deja":
		text = _("%s rulează deja.") % nume
	elif m == "nimic_pornit":
		text = _("Niciun modul nu rulează.")
	elif m == "niciunul_ales":
		text = _("Nu este ales niciun modul.")
	elif m == "ocupat":
		text = _("Așteaptă să se termine comanda de acum.")
	elif m == "nu_e_legatura":
		text = _("%s nu este o legătură; alegerea nu se schimbă.") % nume
	elif m == "legatura":
		text = _("Alegerea nu s-a putut salva: %s") % (r.get("eroare") or "")
	elif m == "nu_s_a_oprit":
		text = _("%s nu s-a oprit.") % nume
	elif m == "nu_a_pornit":
		text = _("%s nu a pornit.") % nume
	elif m == "termen":
		text = _("Scriptul lui %s nu a terminat în %s secunde.") % (nume, r.get("secunde") or 0)
	else:  # necunoscut
		text = _("%s nu mai este instalat.") % nume
	if not r.get("ok") and r.get("cod") is not None:
		text += "\n" + _("Răspunsul scriptului (codul %s): %s") % (r["cod"], r.get("raspuns") or "-")
	return text


def _limitaPagina(w, pagina):
	"""pagina derulata, cel mult ultima pagina a unui ScrollLabel (atributul pages: None = o singura pagina)"""
	if not hasattr(w, "pages"):
		return pagina
	return max(0, min(pagina, (w.pages or 1) - 1))


def text_pas(actiune, nume):
	"""ce incepe acum o operatie (HdsModuleAcces.Operatie, la_pas): actiunea scriptului si numele modulului"""
	if actiune == "stop":
		return _("Se oprește %s...") % nume
	if actiune == "restart":
		return _("Se repornește %s...") % nume
	return _("Se pornește %s...") % nume


def _anunta_dupa_inchidere(r):
	"""rezultatul unei operatii terminate dupa ce ecranul s-a inchis: o fereastra scurta peste ce e pe ecran"""
	try:
		from Tools import Notifications
		from Screens.MessageBox import MessageBox
		Notifications.AddPopup(text_rezultat(r), MessageBox.TYPE_INFO if r.get("ok") else MessageBox.TYPE_ERROR, 10,
			"HdsModuleAcces")
	except Exception as e:
		print("[CamSetup] rezultat dupa inchidere: %s (%s)" % (r.get("motiv"), e))


class CamSetup(Screen):
	skin = """
	<screen name="CamSetup" position="center,center" size="1240,860" title="Module de acces condiționat">
		<widget name="lista" position="30,20" size="1180,300" font="Regular;30" itemHeight="50" scrollbarMode="showOnDemand" />
		<widget name="stare" position="30,332" size="1180,76" font="Regular;26" foregroundColor="#ffcc66" />
		<widget name="detalii" position="30,418" size="1180,352" font="Regular;24" />
		<widget source="key_red" render="Label" position="30,790" size="280,50" zPosition="1" font="Regular;24" halign="center" valign="center" backgroundColor="#9f1313" transparent="0" />
		<widget source="key_green" render="Label" position="330,790" size="280,50" zPosition="1" font="Regular;24" halign="center" valign="center" backgroundColor="#1f771f" transparent="0" />
		<widget source="key_yellow" render="Label" position="630,790" size="280,50" zPosition="1" font="Regular;24" halign="center" valign="center" backgroundColor="#a08000" transparent="0" />
		<widget source="key_blue" render="Label" position="930,790" size="280,50" zPosition="1" font="Regular;24" halign="center" valign="center" backgroundColor="#185090" transparent="0" />
	</screen>
	"""

	def __init__(self, session):
		Screen.__init__(self, session)
		self.setTitle(_("Module de acces condiționat"))
		self["lista"] = MenuList([])
		self["stare"] = Label("")
		self["detalii"] = ScrollLabel("")
		self["key_red"] = StaticText(_("Oprește"))
		self["key_green"] = StaticText(_("Pornește"))
		self["key_yellow"] = StaticText(_("Repornește"))
		self["key_blue"] = StaticText(_("Interfața web"))

		# WizardActions si ColorActions au numai actiunile de mai jos, toate tratate: niciun „unknown action” in jurnal
		# (DirectionActions ar fi trimis si upUp, downRepeated...). Stanga/Dreapta dau pagina in detalii.
		self["actions"] = ActionMap(["WizardActions", "ColorActions"],
		{
			"ok": self.ok,
			"back": self.close,
			"up": self.sus,
			"down": self.jos,
			"left": self.paginaSus,
			"right": self.paginaJos,
			"red": self.rosu,
			"green": self.verde,
			"yellow": self.galben,
			"blue": self.albastru,
		}, -1)
		# INFO: „Informații despre decriptare”. Contextul InfobarEPGActions are numai tasta INFO (data/keymap.xml), deci
		# nicio actiune netratata.
		self["info_actions"] = ActionMap(["InfobarEPGActions"], {"showEventInfo": self.informatii}, -1)

		self.stari = []          # HdsModuleAcces.Stare, cate una pe fel aratat (primul: al modulelor obisnuite)
		self.randuri = []        # (fel, sufix sau None pentru „Niciunul”), in ordinea din lista
		self.texte = []
		self.textDetalii = None     # textul aratat in detalii si randul lui: la fel = nu se rescrie (derularea ramane)
		self.randDetalii = None
		self.paginaDetalii = 0      # cate pagini s-au derulat in detalii (Stanga / Dreapta), pusa la loc dupa o rescriere
		self.operatie = None
		self.ceas = eTimer()
		self.ceas.callback.append(self.reimprospateaza)
		self["lista"].onSelectionChanged.append(self.arataDetalii)
		self.onLayoutFinish.append(self.porneste)
		self.onClose.append(self.laInchidere)

	# ------------------------------------------------ starea
	def porneste(self):
		self.reimprospateaza()
		self.ceas.start(REIMPROSPATARE, False)

	def laInchidere(self):
		self.ceas.stop()
		del self.ceas.callback[:]
		if self.operatie is not None and not self.operatie.gata:
			self.operatie.desprinde(_anunta_dupa_inchidere)
		self.operatie = None

	def reimprospateaza(self):
		try:
			self.stari = HdsModuleAcces.feluri_de_aratat()
		except Exception as e:
			print("[CamSetup] citirea modulelor: %s" % e)
			self.stari = []
		ales_acum = self.randCurent()
		randuri, texte = [], []
		principal = self.felPrincipal()
		for st in self.stari:
			niciunul = st.ales_emulator() is None
			randuri.append((st.fel, None))
			texte.append(_eticheta(st.fel, _("Niciunul"), principal) + ("  (%s)" % _("ales") if niciunul else ""))
			for e in st.emulatoare:
				semne = []
				if e.ales:
					semne.append(_("ales"))
				if e.pids:
					semne.append(_("rulează"))
				elif e.ales:
					semne.append(_("oprit"))
				texte.append(_eticheta(st.fel, e.sufix, principal) + ("  (%s)" % ", ".join(semne) if semne else ""))
				randuri.append((st.fel, e.sufix))
		if texte != self.texte or randuri != self.randuri:
			self.randuri, self.texte = randuri, texte
			self["lista"].setList([(t, r) for t, r in zip(texte, randuri)])
			if ales_acum in randuri:
				self["lista"].moveToIndex(randuri.index(ales_acum))
			else:
				# la deschidere: randul celui ales
				for i, (fel, sufix) in enumerate(randuri):
					st = self.stare(fel)
					if st is not None and st.ales_emulator() is not None and st.ales_emulator().sufix == sufix:
						self["lista"].moveToIndex(i)
						break
		self.arataDetalii()

	def stare(self, fel):
		for st in self.stari:
			if st.fel == fel:
				return st
		return None

	def felPrincipal(self):
		"""felul modulelor obisnuite: primul aratat (HdsModuleAcces.feluri_de_aratat il pune mereu primul)"""
		return self.stari[0].fel if self.stari else None

	def randCurent(self):
		c = self["lista"].getCurrent()
		return c[1] if c else None

	def arataDetalii(self):
		rand = self.randCurent()
		if rand is None:
			return
		fel, sufix = rand
		st = self.stare(fel)
		if st is None:
			return
		e = st.emulator(sufix) if sufix is not None else None
		randuri = []
		if e is not None:
			if e.descriere:
				randuri.append(_("Descriere: %s") % e.descriere)
			if e.pids:
				randuri.append(_("Rulează (PID %s).") % ", ".join(str(p) for p in e.pids))
				sistem = HdsModuleAcces.SistemAcces()
				randuri += ["  " + r for r in randuri_proces(HdsModuleAcces.memorie(sistem, pid_de_aratat(sistem, e.pids)))]
				randuri.append(_("Apasă OK pentru oprire, repornire sau informații."))
				randuri.append("INFO: " + _("Despre decriptare"))
			else:
				randuri.append(_("Nu rulează."))
			if e.ales:
				randuri.append(_("Pornește la fiecare pornire a receptorului."))
			ales = e.ales
		else:
			if not st.emulatoare:
				randuri.append(_("Nu este instalat niciun modul de acces condiționat. După ce se instalează pachetul unui modul, acesta apare aici."))
				if st.fara_script:
					randuri.append(_("Programe fără script de pornire, care nu se pot porni de aici: %s") % ", ".join(st.fara_script))
			elif st.ales_emulator() is None:
				randuri.append(_("La pornirea receptorului nu pornește niciun modul."))
			ales = st.ales_emulator() is None
		if st.ecm:
			randuri.append("")
			randuri.append(_("Decriptarea de acum (%s):") % HdsModuleAcces.FISIER_ECM)
			randuri += ["  " + r for r in st.ecm]
		self.scrieDetalii("\n".join(randuri), rand)
		self["key_green"].setText(_("Pornește") if ales and e is not None else _("Alege"))

	def scrieDetalii(self, text, rand):
		"""ScrollLabel.setText muta textul la inceput: nimic de rescris cand textul e acelasi; la acelasi rand, cu alt
		text (s-a schimbat memoria sau ecm.info), pagina derulata se pune la loc (ScrollLabel.pageDown se opreste
		singur la ultima pagina)"""
		if text == self.textDetalii and rand == self.randDetalii:
			return
		if rand != self.randDetalii:
			self.paginaDetalii = 0
		self.textDetalii, self.randDetalii = text, rand
		w = self["detalii"]
		w.setText(text)
		self.paginaDetalii = _limitaPagina(w, self.paginaDetalii)
		for _i in range(self.paginaDetalii):
			w.pageDown()

	def sus(self):
		self["lista"].up()

	def jos(self):
		self["lista"].down()

	def paginaSus(self):
		self.paginaDetalii = max(0, self.paginaDetalii - 1)
		self["detalii"].pageUp()

	def paginaJos(self):
		self.paginaDetalii = _limitaPagina(self["detalii"], self.paginaDetalii + 1)
		self["detalii"].pageDown()

	# ------------------------------------------------ comenzile
	def pornesteOperatia(self, cerere, fel, sufix=None):
		if self.operatie is not None and not self.operatie.gata or HdsModuleAcces.in_curs() is not None:
			self["stare"].setText(_("Așteaptă să se termine comanda de acum."))
			return
		self.operatie = HdsModuleAcces.Operatie(cerere, fel=fel, sufix=sufix, la_pas=self.laPas, la_final=self.laFinal)
		self.operatie.porneste()

	def laPas(self, actiune, nume):
		self["stare"].setText(text_pas(actiune, nume))

	def laFinal(self, rezultat):
		self.operatie = None
		self["stare"].setText(text_rezultat(rezultat))
		self.reimprospateaza()

	def ok(self):
		"""pe un modul care ruleaza: lista scurta cu ce se poate face (fara tastele colorate); altfel ca Verde"""
		rand = self.randCurent()
		st = self.stare(rand[0]) if rand is not None else None
		e = st.emulator(rand[1]) if st is not None and rand[1] is not None else None
		if e is None or not e.pids:
			self.verde()
			return
		alegeri = []
		if not e.ales:
			alegeri.append((_("Alege"), "alege"))
		alegeri += [(_("Oprește"), "opreste"), (_("Repornește"), "reporneste"), (_("Interfața web"), "interfata"),
			(_("Despre decriptare"), "informatii")]
		self.session.openWithCallback(self.dupaAlegere, _alegere(), title=_eticheta(rand[0], e.sufix, self.felPrincipal()),
			list=alegeri)

	def dupaAlegere(self, alegere):
		if not alegere:
			return
		cerere = alegere[1]
		if cerere == "alege":
			self.verde()
		elif cerere == "opreste":
			self.rosu()
		elif cerere == "reporneste":
			self.galben()
		elif cerere == "interfata":
			self.albastru()
		elif cerere == "informatii":
			self.informatii()

	def verde(self):
		rand = self.randCurent()
		if rand is None:
			return
		fel, sufix = rand
		st = self.stare(fel)
		ales = st.ales_emulator() if st is not None else None
		if sufix is not None and ales is not None and ales.sufix == sufix:
			self.pornesteOperatia("porneste", fel, sufix)
		else:
			self.pornesteOperatia("alege", fel, sufix if sufix is not None else HdsModuleAcces.SUFIX_GOL)

	def rosu(self):
		rand = self.randCurent()
		if rand is not None:
			self.pornesteOperatia("opreste", rand[0])

	def galben(self):
		rand = self.randCurent()
		if rand is not None:
			self.pornesteOperatia("reporneste", rand[0])

	def albastru(self):
		"""Interfata web a modulului care ruleaza, pe televizor (navigatorul imaginii, modul cam). Modulul il gaseste
		navigatorul, la rulare, dupa portul pe care asculta; cand ruleaza mai multe module cu pagina web, le arata pe
		toate ca sa alegi. Ecranul acesta nu afla si nu tine nicio adresa, niciun utilizator si nicio parola."""
		if not any(st.pornite() for st in self.stari):
			self["stare"].setText(_("Niciun modul nu rulează."))
			return
		try:
			# importat abia la apasare, ca tot navigatorul (nimic din el nu se incarca odata cu ecranul)
			from Plugins.Extensions.HdsNavigator.plugin import deschideInterfataCam
		except ImportError as e:
			print("[CamSetup] navigatorul: %s" % e)
			self["stare"].setText(_("%s nu a pornit.") % _("Interfața web"))
			return
		self["stare"].setText("")
		deschideInterfataCam(self.session)

	def informatii(self):
		"""INFO (si „Despre decriptare” din lista de la OK): Screens/CamInfo.py cu modulul ales, daca ruleaza, altfel
		cu primul pornit"""
		rand = self.randCurent()
		st = self.stare(rand[0]) if rand is not None else None
		pornite = st.pornite() if st is not None else []
		e = st.emulator(rand[1]) if st is not None and rand[1] is not None else None
		if e is None or not e.pids:
			e = pornite[0] if pornite else None
		from .CamInfo import CamInfo
		if e is not None:
			self.session.open(CamInfo, e.sufix, pid_de_aratat(HdsModuleAcces.SistemAcces(), e.pids))
		else:
			self.session.open(CamInfo)
