# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# HDS-MARCA: HD Satelit, 2026
#
# A doua bara de informatii (pagina tehnica si ghidul canalului). Paginile si datele lor sunt in
# Components/Converter/HdsCommon.py (merg si pe alte imagini cu skinul HDSatelit); aici sunt tastele imaginii:
# - stanga / dreapta (si CH+/-, PAGE+/-): pagina urmatoare / precedenta, dupa ordinea de aratare (ghidul primul);
# - pagina ghidului (5): sus / jos muta cursorul prin emisiuni; OK cu cursorul mutat arata descrierea intreaga pe
#   loc, iar OK in descriere deschide meniul emisiunii (inregistrare, temporizator, ghidurile), ca totul sa se poata
#   face numai cu sagetile si OK; INFO arata / ascunde descrierea; Verde = temporizatorul; Rosu si REC =
#   inregistrarea dintr-o apasare; Galben si EPG = ghidul canalului pe emisiunea aleasa; Albastru = ghidul tuturor
#   canalelor; EXIT in descriere = inapoi la lista;
# - pagina 3: sus / jos muta cursorul pistelor, OK alege; pagina 4: sus / jos deruleaza lista CAID-urilor.
# Orice ecran deschis din bara o ascunde (Session.execEnd); la inchiderea lui bara revine pe ghid, pe aceeasi
# emisiune, daca programul nu s-a schimbat (HdsCommon.page_resume_set si InfoBarShowHide.hdsArataADoua).
# Tastele care nu au treaba pe pagina de acum merg mai departe, la harta de dedesubt (prioritatea -2) si la bara.

from Screens.Screen import Screen
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.ScrollLabel import ScrollLabel
from Components.Sources.StaticText import StaticText
from Components.ServiceEventTracker import ServiceEventTracker
from enigma import iPlayableService, eTimer
import time

# cat de departe de rosu poate veni ridicarea lui („instantRecord”), ca sa fie luata drept aceeasi apasare
ROSU_RIDICARE_S = 3.0

try:
	from Components.Converter import HdsCommon as C
except Exception:
	C = None

# traducerea automata a ghidului (Components/HdsTraducereEpg.py, „Tradu EPG”): descrierea emisiunii alese; INFO pe o
# descriere tradusa arata originalul, INFO pe original o inchide
try:
	from Components import HdsTraducereEpg as _E
except Exception:
	_E = None


class _HdsSursaServiciu(object):
	# C.Reader(source, what) citeste "source.service", ca sursele reale (FrontendStatus / ServiceEvent) folosite de
	# convertoare; serviciul brut nu are atributul .service.
	__slots__ = ("service",)

	def __init__(self, service):
		self.service = service


class _HartaTacuta(ActionMap):
	"""Harta care leaga contexte intregi (HdsInfobarActions, DirectionActions...) dar prinde numai actiunile ei;
	celelalte trec mai departe fara randul „unknown action” in jurnal. `rosu` = momentul ultimului rosu folosit de
	ghid; orice alta actiune il sterge (vezi SecondInfoBar.hdsRec)."""

	rosu = 0.0

	def action(self, context, action):
		if action not in ("red", "instantRecord"):
			self.rosu = 0.0
		if action in self.actions:
			res = self.actions[action]()
			if res is not None:
				return res
			return 1
		return 0


def _treci():
	"""Actiune care nu face nimic si lasa tasta sa mearga mai departe (ActionMap.action intoarce 0)."""
	return 0


def _skinAre(ecran, widget):
	"""Skinul activ are, in ecranul `ecran`, un widget cu numele `widget` (direct sau printr-un panou)."""
	try:
		import skin
		el, cale = skin.lookupScreen(ecran, 0)
		if el is None:
			return False
		for copil, p in skin.expandPanels(el, cale, 0, ecran):
			if copil.tag == "widget" and copil.attrib.get("name") == widget:
				return True
	except Exception:
		return False
	return False


def _argumenteConvertor(r):
	"""Argumentele primului convertor din skin al unui element (cel mai adanc din lantul de surse): la un FixedLabel
	cu ConditionalShowHide sursa lui directa e ConditionalShowHide (fara argumente, sau "Invert"), iar HdsInfo sta
	sub ea."""
	sursa = getattr(r, "source", None)
	rez = ""
	for _i in range(6):
		if sursa is None:
			break
		arg = getattr(sursa, "converter_arguments", None)
		if arg:
			rez = str(arg)
		sursa = getattr(sursa, "source", None)
	return rez


class SecondInfoBar(Screen):
	ALLOW_SUSPEND = True
	skinName = "SecondInfoBar"

	def __init__(self, session):
		Screen.__init__(self, session)
		self.shown = False
		self["epg_description"] = ScrollLabel()
		self["FullDescription"] = ScrollLabel()
		self["channel"] = Label()
		self["key_red"] = StaticText()
		self["key_green"] = StaticText()
		self["key_yellow"] = StaticText()
		self["key_blue"] = StaticText()
		# descrierea intreaga a emisiunii alese, peste coloana din stanga a ghidului; numai daca skinul o deseneaza
		# (un skin fara ea nu primeste avertismentul „skin is missing element”)
		self._areDescriere = _skinAre(self.skinName, "hdsEpgText")
		if self._areDescriere:
			self["hdsEpgText"] = ScrollLabel()
		self._descriere = False
		self._hdsTradus = False
		self._reiaTimer = None

		self["SecondInfoBarActions"] = ActionMap(
			["InfobarShowHideActions", "2ndInfobarActions", "InfobarChannelSelection", "DirectionActions", "ColorActions", "OkCancelActions"],
			{
				"pageUp": self.prevPage,
				"pageDown": self.nextPage,
				"prevPage": self.prevPage,
				"nextPage": self.nextPage,
				"left": self.prevPage,
				"right": self.nextPage,
				"zapUp": self.prevPage,
				"zapDown": self.nextPage,
				"prevEvent": self.prevPage,
				"nextEvent": self.nextPage,
				"historyBack": self.prevPage,
				"historyNext": self.nextPage,
				"LeftPressed": self.prevPage,
				"RightPressed": self.nextPage,
				"switchChannelUp": self.prevPage,
				"switchChannelDown": self.nextPage,
				"openServiceList": self.nextPage,
				"toggleShow": self.closeScreen,
				"hide": self.closeScreen,
				"ok": self.closeScreen,
				"cancel": self.closeScreen,
				"red": self.closeScreen,
				"green": self.closeScreen,
				"yellow": self.closeScreen,
				"blue": self.closeScreen,
				# ridicarea si tinerea sagetilor (keymap.xml, DirectionActions, flags b / r): trec mai departe, ca pana
				# acum, dar fara randul „unknown action” in jurnal
				"upUp": _treci,
				"downUp": _treci,
				"leftUp": _treci,
				"rightUp": _treci,
				"leftRepeated": _treci,
				"rightRepeated": _treci,
			},
			-2
		)
		# sus / jos, OK, EXIT, culorile, INFO, EPG si REC, cu prioritatea -3, deci inaintea hartii de mai sus: pe pagina
		# ghidului, a pistelor (3) si a accesului (4). Functiile intorc 0 cand tasta nu are treaba pe pagina de acum,
		# iar tasta merge mai departe (OK si EXIT inchid bara, culorile o inchid, INFO si REC merg la bara de jos).
		# Tinerea apasata (upRepeated) muta tot cate un rand. Cifrele nu sunt prinse: schimba canalul.
		self["HdsAfisajActions"] = _HartaTacuta(
			["DirectionActions", "OkCancelActions", "ColorActions", "InfobarEPGActions", "HdsInfobarActions", "InfobarInstantRecord"],
			{
				"up": self.hdsSus,
				"down": self.hdsJos,
				"upRepeated": self.hdsSus,
				"downRepeated": self.hdsJos,
				"ok": self.hdsOk,
				"cancel": self.hdsInapoi,
				"red": self.hdsRosu,
				"instantRecord": self.hdsRec,
				"green": self.hdsTemporizator,
				"yellow": self.hdsGhidCanal,
				"ghidProgram": self.hdsGhidCanal,
				"blue": self.hdsGhidToate,
				"showEventInfo": self.hdsInfo,
			},
			-3
		)

		events = {
			iPlayableService.evUpdatedEventInfo: self.getEvent,
			iPlayableService.evStart: self.__evStart,
		}
		ev_tags = getattr(iPlayableService, "evUpdateTags", None)
		if ev_tags is not None:
			events[ev_tags] = self.getEvent
		self.__event_tracker = ServiceEventTracker(screen=self, eventmap=events)

		if C is not None and hasattr(C, "epg_keys_on"):
			C.epg_keys_on(True)

		self.onShow.append(self.__onShow)
		self.onHide.append(self.__onHide)
		# (getattr: ecranele false ale probelor de pe PC nu au lista)
		getattr(self, "onLayoutFinish", []).append(self._randuriTextMarit)
		getattr(self, "onLayoutFinish", []).append(self._caseteMarite)

	# randurile aliniate sus intr-o banda (pagina pistelor): numele convertorului HdsInfo
	RANDURI_IN_BANDA = ("SelAudio", "SelSub", "SelExtra", "HbbtvRow")

	def _randuriTextMarit(self):
		"""Textul marit (Marimea textului peste 100 %): randurile listelor de pe pagina pistelor (SelAudio, SelSub,
		SelExtra) si randul HbbTV sunt etichete aliniate sus, cu 4 px sub marginea de sus a benzii lor (banda: inaltimea
		etichetei + 4). Cu fontul marit linia de baza cobora sub banda, iar jumatatea de jos a literelor se taia (de la
		115 %). Eticheta urca pana cand linia de baza sta la 2 px deasupra marginii de jos a benzii (ascendentul fontului:
		1,08 x marimea, la toate fonturile skinului) si creste cat randul fontului, ca si cozile (g, p) sa se vada. La 100 %
		nu se schimba nimic."""
		try:
			from Components import HdsMarireText as M
			if not M.marit():
				return
			from enigma import ePoint, eSize
			for r in self.renderer:
				arg = str(getattr(getattr(r, "source", None), "converter_arguments", "") or "")
				inst = getattr(r, "instance", None)
				if inst is None or arg.split(",")[0] not in self.RANDURI_IN_BANDA:
					continue
				# locul din skin (Components/GUISkin poate sa fi crescut deja caseta, HdsMarireText.potrivesteInaltimile)
				x0, y0, l0, h0 = getattr(r, "hdsLocSkin", None) or (inst.position().x(), inst.position().y(),
					inst.size().width(), inst.size().height())
				m = M.marimeFont(inst)
				asc = m * 108 // 100
				y = min(y0, y0 + h0 - 2 - asc)
				h = max(h0 + y0 - y, asc + m * 31 // 100 + 2)
				inst.move(ePoint(x0, y))
				inst.resize(eSize(l0, h))
		except Exception as e:
			print("[SecondInfoBar] textul marit: %s" % e)

	# etichetele pe mai multe randuri ale paginilor: descrierea emisiunii (ghidul), modul procesorului si timpul pe
	# frecvente (receptorul), starea sunetului si de ce (pistele): numele convertorului
	CASETE_PE_RANDURI = ("EpgSelLong", "CpuMod", "CpuTrepte", "SoundState", "SoundWhy")
	# cat ramane liber deasupra textului de dedesubt (sau a marginii de jos a paginii)
	LOC_SUB_CASETA = 4

	def _caseteMarite(self):
		"""Textul marit (Marimea textului peste 100 %): o eticheta pe mai multe randuri isi pastra caseta din skin, facuta
		pentru randurile de la 100 %, deci ultimul rand se vedea taiat pe jumatate (descrierea din ghid la 115 %, timpul pe
		frecvente la 115 si 130 %) sau trecea peste textul de sub el (starea sunetului la 130 %). Acum caseta tine numai
		randuri intregi (randul fontului, ca la ScrollLabel) si, unde e loc sub ea pe pagina (pana la textul urmator din
		coloana sau pana la capatul despartitoarelor paginii), creste; starea sunetului are loc pentru doua randuri, iar
		explicatia de sub ea coboara. Restul descrierii se citeste ca pana acum cu INFO (descrierea intreaga, pe pagini).
		Casetele nu depind de text: se potrivesc o data, la asezare. La 100 % nu se schimba nimic."""
		try:
			from Components import HdsMarireText as M
			if not M.marit():
				return
			from enigma import ePoint, eSize, fontRenderClass
			casete = {}
			pagini = []   # (pagina, x, y, latime, inaltime) din skin, pentru vecinii de dedesubt
			jos = {}
			for r in self.renderer:
				arg = _argumenteConvertor(r)
				inst = getattr(r, "instance", None)
				if inst is None or not arg:
					continue
				parti = arg.split(",")
				loc = getattr(r, "hdsLocSkin", None) or (inst.position().x(), inst.position().y(), inst.size().width(),
					inst.size().height())
				if parti[0] == "Page" and len(parti) > 1:
					jos[parti[1]] = max(jos.get(parti[1], 0), loc[1] + loc[3])
					continue
				pag = [p[1:] for p in parti[1:] if len(p) > 1 and p[0] == "P" and p[1:].isdigit()]
				if not pag:
					continue
				pagini.append((pag[0], loc[0], loc[1], loc[2], loc[3]))
				if parti[0] in self.CASETE_PE_RANDURI and hasattr(inst, "calculateSize"):
					casete[parti[0]] = (inst, pag[0], loc)

			def limita(pag, x, l, y_jos):
				"""y-ul pana la care poate creste o caseta: primul text de dedesubt din coloana ei, pe aceeasi pagina, sau
				capatul despartitoarelor paginii (altfel marginea de jos a ecranului)"""
				sus = [jos.get(pag) or self.instance.size().height()]
				for p, ox, oy, ol, oh in pagini:
					if p == pag and oy >= y_jos and ox < x + l and ox + ol > x:
						sus.append(oy)
				return min(sus) - self.LOC_SUB_CASETA

			def randuri(inst, x, y, l, inalt, minim=1):
				"""caseta la (x, y), cu atatea randuri intregi cate incap in `inalt` (cel putin `minim`): n randuri ale
				fontului (ultimul cu cozile lui), plus cel mult o saisime de rand cand e loc, dar niciodata cat sa se vada
				inceputul randului urmator -> inaltimea pusa"""
				rand = int(fontRenderClass.getInstance().getLineHeight(inst.getFont()) or M.marimeFont(inst) * 4 // 3)
				inalt = int(inalt)
				n = max(minim, inalt // rand)
				h = max(n * rand, min(inalt, n * rand + rand // 6))
				inst.move(ePoint(x, y))
				inst.resize(eSize(l, h))
				return h

			for nume in ("EpgSelLong", "CpuMod", "CpuTrepte"):
				if nume in casete:
					inst, pag, (x, y, l, h) = casete[nume]
					randuri(inst, x, y, l, limita(pag, x, l, y + h) - y)
			if "SoundState" in casete:
				inst, pag, (x, y, l, h) = casete["SoundState"]
				de_jos = casete.get("SoundWhy")
				if de_jos is not None and de_jos[1] == pag and de_jos[2][1] >= y + h:
					# starea (cel mult doua randuri) si explicatia de sub ea, cu distanta din skin intre ele
					jx, jy, jl, jh = de_jos[2]
					h2 = randuri(inst, x, y, l, h, 2)
					y2 = max(jy, y + h2 + (jy - (y + h)))
					randuri(de_jos[0], jx, y2, jl, limita(pag, jx, jl, jy + jh) - y2)
				else:
					randuri(inst, x, y, l, limita(pag, x, l, y + h) - y)
		except Exception as e:
			print("[SecondInfoBar] casetele cu textul marit: %s" % e)

	def __onShow(self):
		self["SecondInfoBarActions"].doBind()
		self["HdsAfisajActions"].doBind()
		self._descriereInchide()
		if C is not None:
			try:
				service = self.session.nav.getCurrentService()
				C.page_start(C.Reader(_HdsSursaServiciu(service), None))
			except Exception:
				pass

	def __onHide(self):
		if hasattr(self["SecondInfoBarActions"], "bound") and self["SecondInfoBarActions"].bound:
			self["SecondInfoBarActions"].doUnbind()
		if getattr(self["HdsAfisajActions"], "bound", False):
			self["HdsAfisajActions"].doUnbind()
		self._descriereInchide()
		if C is not None:
			try:
				C.page_stop()
			except Exception:
				pass

	def __evStart(self):
		self._descriereInchide()

	# Pagina se schimba doar din tastele de mai sus (stanga / dreapta si celelalte puse pe prevPage / nextPage) si
	# ramane pe loc; ecranul se inchide doar cu OK, EXIT si tastele puse pe closeScreen.
	def nextPage(self):
		self._descriereInchide()
		if C is None:
			return
		try:
			C.page_step(1)
		except Exception as e:
			print("[SecondInfoBar] pagina: %s" % e)

	def prevPage(self):
		self._descriereInchide()
		if C is None:
			return
		try:
			C.page_step(-1)
		except Exception as e:
			print("[SecondInfoBar] pagina: %s" % e)

	# ---------------------------------------------------------------- cititorul si pagina de acum

	def _cititor(self):
		try:
			return C.Reader(_HdsSursaServiciu(self.session.nav.getCurrentService()), None)
		except Exception:
			return None

	def _pagina(self):
		try:
			return C.page_active() if C is not None else 0
		except Exception:
			return 0

	def _ghid(self):
		"""Cititorul serviciului cand pagina ghidului e pe ecran si skinul deseneaza lista; altfel None."""
		if C is None or not hasattr(C, "epg_keys_work"):
			return None
		r = self._cititor()
		try:
			if r is not None and C.epg_keys_work(r):
				return r
		except Exception:
			pass
		return None

	# ---------------------------------------------------------------- sus / jos

	def _hdsMuta(self, d):
		pagina = self._pagina()
		if pagina == getattr(C, "EPG_PAGE", 5):
			r = self._ghid()
			if r is None:
				return
			if self._descriere:
				try:
					if d < 0:
						self["hdsEpgText"].pageUp()
					else:
						self["hdsEpgText"].pageDown()
					C.page_touch()
				except Exception:
					pass
				return
			try:
				if C.epg_move(r, d):
					C.page_refresh(C.EPG_PAGE)
			except Exception as e:
				print("[SecondInfoBar] ghid: %s" % e)
			return
		if pagina == 4 and hasattr(C, "ca_scroll"):
			r = self._cititor()
			try:
				if r is not None and C.ca_scroll(r, d):
					C.page_touch()
					C.page_refresh(4)
			except Exception as e:
				print("[SecondInfoBar] acces: %s" % e)
			return
		if pagina == getattr(C, "SEL_PAGE", 3) and hasattr(C, "sel_move"):
			r = self._cititor()
			try:
				if r is not None and C.sel_move(r, d):
					C.page_touch()
					C.page_refresh()
			except Exception as e:
				print("[SecondInfoBar] cursor: %s" % e)
		# alta pagina: sus / jos nu fac nimic (nu schimba nici pagina, nici canalul)

	def hdsSus(self):
		self._hdsMuta(-1)

	def hdsJos(self):
		self._hdsMuta(1)

	# ---------------------------------------------------------------- OK, EXIT, INFO

	def hdsOk(self):
		pagina = self._pagina()
		if pagina == getattr(C, "EPG_PAGE", 5):
			r = self._ghid()
			if r is None:
				return 0
			if self._descriere:
				return self._meniuEmisiune(r)
			if C.epg_moved():
				self._descriereArata(r)
				return None
			return 0  # cursorul nu s-a mutat: OK inchide bara, ca pana acum
		if pagina == getattr(C, "SEL_PAGE", 3) and hasattr(C, "sel_ok"):
			r = self._cititor()
			if r is None:
				return 0
			try:
				if C.sel_ok(r, getattr(self, "hdsProprietar", None)):
					C.page_refresh()
			except Exception as e:
				print("[SecondInfoBar] alegere: %s" % e)
			return None
		return 0

	def hdsInapoi(self):
		if self._descriere:
			self._descriereInchide()
			return None
		return 0

	def hdsInfo(self):
		r = self._ghid()
		if r is None:
			return 0
		if self._descriere:
			if _E is not None and self._hdsTradus and not _E.esteOriginal():
				_E.arataOriginal(True)
				self._descriereArata(r)
				return None
			self._descriereInchide()
		else:
			self._descriereArata(r)
		return None

	def hdsTraducereEpg(self):
		"""Components/HdsTraducereEpg.py: a venit o traducere (sau s-a cerut originalul): descrierea scrisa din nou"""
		if getattr(self, "_descriere", False) and getattr(self, "shown", False):
			r = self._ghid()
			if r is not None:
				self._descriereArata(r)

	def _descriereText(self, r):
		ev = C.epg_event(r)
		if not ev:
			return ""
		texte = [ev["name"], ev["short"], ev["ext"]]
		nota = ""
		self._hdsTradus = False
		if _E is not None:
			stari = []
			traduse = []
			for fel, t in zip(("titlu", "scurta", "lunga"), texte):
				text, stare = _E.traducere(fel, t, self, False)
				traduse.append(text)
				stari.append(stare)
			if _E.STARE_ORIGINAL in stari:
				nota = _("Textul original, netradus. INFO: închide.")
			elif _E.STARE_TRADUS in stari:
				self._hdsTradus = True
				texte = traduse
				nota = _("Tradus automat. INFO: textul original.")
		# randul despre traducere sus, langa ore: descrierea lunga ar ascunde-o la capat
		parti = [texte[0], C.event_line(ev)] + ([nota] if nota else [])
		for t in (texte[1], texte[2]):
			if t and t not in parti:
				parti.append("")
				parti.append(t)
		return C.out("\n".join([p for p in parti if p is not None]))

	def _descriereArata(self, r):
		if not self._areDescriere:
			return
		text = self._descriereText(r)
		if not text:
			return
		try:
			self["hdsEpgText"].setText(text)
			self["hdsEpgText"].show()
			self._descriere = True
			C.page_touch()
			self._ajutorGhid(True)
		except Exception as e:
			print("[SecondInfoBar] descriere: %s" % e)

	def _descriereInchide(self):
		era = self._descriere
		self._descriere = False
		self._hdsTradus = False
		if _E is not None:
			_E.arataOriginal(False)
		if self._areDescriere:
			try:
				self["hdsEpgText"].hide()
			except Exception:
				pass
		if era:
			self._ajutorGhid(False)

	def _ajutorGhid(self, descriere):
		"""Randul de ajutor al ghidului (HdsInfo EpgHelp) spune ce face OK acum: meniul emisiunii in descriere."""
		try:
			if hasattr(C, "epg_desc_set"):
				C.epg_desc_set(descriere)
				C.page_refresh(C.EPG_PAGE)
		except Exception as e:
			print("[SecondInfoBar] ajutor: %s" % e)

	# ---------------------------------------------------------------- ecranele deschise din bara si drumul inapoi

	def _proprietar(self):
		return getattr(self, "hdsProprietar", None)

	def _reluare(self, sref, eid):
		"""Functia de chemat cand ecranul deschis din bara se inchide: bara revine pe ghid, pe emisiunea `eid`, daca
		programul e tot `sref`."""
		prop = self._proprietar()

		def la_final(*args):
			try:
				C.page_resume_set(sref, eid)
				cur = self.session.nav.getCurrentlyPlayingServiceReference()
				if cur is None or C.norm_ref(cur.toString()) != C.norm_ref(sref):
					return
				if prop is not None and hasattr(prop, "hdsArataADoua"):
					prop.hdsArataADoua()
			except Exception as e:
				print("[SecondInfoBar] revenire: %s" % e)
		return la_final

	def _reluareDupaInchidere(self, dlg, la_final):
		"""Pentru ecranele deschise de bara de jos (fara callback de la noi): dupa inchiderea lor, cand bara de jos
		a revenit, se cheama la_final (un ceas de 0 ms, dupa Session.processDelay)."""
		def inchis():
			t = eTimer()
			t.callback.append(la_final)
			self._reiaTimer = t
			t.start(0, True)
		try:
			if dlg is not None and dlg is not self._proprietar():
				dlg.onClose.append(inchis)
		except Exception as e:
			print("[SecondInfoBar] revenire: %s" % e)

	def _nota(self, cheie, text):
		try:
			C.epg_note_set(C.tr(cheie).replace(u"{0}", C.u(text)))
			C.page_refresh(C.EPG_PAGE)
		except Exception:
			pass

	def _intreaba(self, la_final, intrebare, da):
		from Screens.MessageBox import MessageBox

		def raspuns(ok):
			if ok:
				try:
					da()
				except Exception as e:
					print("[SecondInfoBar] temporizator: %s" % e)
			la_final()
		self.session.openWithCallback(raspuns, MessageBox, intrebare, MessageBox.TYPE_YESNO)

	def _scoate(self, la_final, t):
		from Components import HdsTemporizare as T
		nume = T.nume_scurt(t)
		prop = self._proprietar()

		def da():
			lista = getattr(prop, "recording", None)
			if isinstance(lista, list) and t in lista:
				lista.remove(t)
			if T.scoate(t, anunta=True):
				self._nota("epg_timer_removed", nume)
		self._intreaba(la_final, _("Scoți temporizatorul pentru %s?") % nume, da)

	def _suprapunere(self, la_final, suprapuse):
		"""Temporizatorul pus direct se suprapune cu altele: fereastra imaginii pentru suprapuneri."""
		from Components import HdsTemporizare as T
		from Screens.TimerEdit import TimerSanityConflict

		def raspuns(ans):
			if ans and ans[0]:
				try:
					rez, alte = T.pune(ans[1], anunta=True)
					if rez == T.REZULTAT_SUPRAPUS:
						self.session.openWithCallback(raspuns, TimerSanityConflict, alte)
						return
					self._nota("epg_rec_set", T.nume_scurt(ans[1]))
				except Exception as e:
					print("[SecondInfoBar] suprapunere: %s" % e)
			la_final()
		self.session.openWithCallback(raspuns, TimerSanityConflict, suprapuse)

	# ---------------------------------------------------------------- culorile, REC, EPG

	def _live(self):
		"""(cititorul, emisiunea aleasa) pe ghid; emisiunea e None cand serviciul nu e viu (inregistrare redata) sau
		nu are program; (None, None) cand tasta nu are treaba aici."""
		r = self._ghid()
		if r is None:
			return None, None
		try:
			if not C.epg_live(r):
				return r, None
			return r, C.epg_event(r)
		except Exception:
			return r, None

	def hdsRosu(self):
		res = self.hdsInregistrare()
		self["HdsAfisajActions"].rosu = time.time() if res != 0 else 0.0
		return res

	def hdsRec(self):
		# Pe „dreambox remote control (native)” rosul da „red” la apasare si „instantRecord” la ridicare (keymap.xml,
		# InfobarInstantRecord, flags b). O singura apasare pe rosu nu lucreaza de doua ori: a doua ar intreba imediat
		# de scoaterea inregistrarii abia puse. Ridicarea e consumata aici, ca bara de jos sa nu porneasca nici ea
		# inregistrarea. Tasta REC (flags m) nu vine dupa un rosu, deci lucreaza.
		harta = self["HdsAfisajActions"]
		if harta.rosu and 0.0 <= time.time() - harta.rosu < ROSU_RIDICARE_S:
			harta.rosu = 0.0
			return None
		harta.rosu = 0.0
		return self.hdsInregistrare()

	def hdsInregistrare(self):
		r, ev = self._live()
		if r is None:
			return 0
		if ev:
			self._faInregistrare(r.sref(), ev)
		return None  # fara program: tasta nu face nimic pe ghid

	def _faInregistrare(self, sref, ev):
		from Components import HdsTemporizare as T
		la_final = self._reluare(sref, ev["id"])
		# HDSatelit 0.3.0: un program DVB-T2 / post DAB+ din satelit nu se poate inca inregistra: limita spusa pe loc,
		# nu fereastra de suprapunere (RecordTimer.record intoarce temporizatorul refuzat ca „suprapunere”)
		from Components import HdsInregistrariProgramate as HIP
		if HIP.felNeinregistrabil(sref):
			from Screens.MessageBox import MessageBox
			self.session.openWithCallback(la_final, MessageBox, HIP.mesajNeinregistrabil(sref, _), MessageBox.TYPE_INFO)
			return
		t = T.cauta(sref, ev)
		if t is not None:
			self._scoate(la_final, t)
			return
		prop = self._proprietar()
		if T.e_acum(ev, C._now()):
			if prop is None or not hasattr(prop, "startInstantRecording"):
				return
			inainte = len(getattr(prop, "recording", []))
			dlg_inainte = self.session.current_dialog
			prop.startInstantRecording(limitEvent=True)
			if len(getattr(prop, "recording", [])) > inainte:
				self._nota("epg_rec_now", ev["name"])
			if self.session.current_dialog is not dlg_inainte:
				# fereastra de suprapunere deschisa de bara de jos: bara revine dupa ea
				self._reluareDupaInchidere(self.session.current_dialog, la_final)
			return
		rez, x = T.inregistreaza(sref, ev)
		if rez == T.REZULTAT_PUS:
			self._nota("epg_rec_set", T.nume_scurt(x))
		elif rez == T.REZULTAT_SUPRAPUS:
			self._suprapunere(la_final, x)

	def hdsTemporizator(self):
		r, ev = self._live()
		if r is None:
			return 0
		if ev:
			self._faTemporizator(r.sref(), ev)
		return None

	def _faTemporizator(self, sref, ev):
		from Components import HdsTemporizare as T
		la_final = self._reluare(sref, ev["id"])
		t = T.cauta(sref, ev)
		if t is not None:
			self._scoate(la_final, t)
			return
		nume = ev["name"]

		def gata(pus):
			if pus:
				self._nota("epg_timer_set", nume)
			la_final()
		try:
			T.pune_din_fereastra(self.session, sref, ev, gata)
		except Exception as e:
			print("[SecondInfoBar] temporizator: %s" % e)

	def hdsGhidCanal(self):
		r, ev = self._live()
		if r is None:
			return 0
		if ev:
			self._faGhidCanal(r.sref(), ev)
		return None

	def _faGhidCanal(self, sref, ev):
		ref = self.session.nav.getCurrentlyPlayingServiceReference()
		if ref is None:
			return
		try:
			from Screens.EpgSelection import EPGSelection
			dlg = self.session.openWithCallback(self._reluare(sref, ev["id"]), EPGSelection, ref)
			if ev.get("id", -1) >= 0:
				dlg["list"].moveToEventId(ev["id"])
		except Exception as e:
			print("[SecondInfoBar] ghidul canalului: %s" % e)

	def hdsGhidToate(self):
		r, ev = self._live()
		if r is None:
			return 0
		if ev:
			self._faGhidToate(r.sref(), ev)
		return None

	def _faGhidToate(self, sref, ev):
		prop = self._proprietar()
		if prop is None or not hasattr(prop, "openMultiServiceEPG"):
			return
		try:
			inainte = self.session.current_dialog
			prop.openMultiServiceEPG()
			if self.session.current_dialog is not inainte:
				self._reluareDupaInchidere(self.session.current_dialog, self._reluare(sref, ev["id"]))
		except Exception as e:
			print("[SecondInfoBar] ghidul tuturor canalelor: %s" % e)

	def _meniuEmisiune(self, r):
		"""OK in descriere: ce se poate face cu emisiunea aleasa, ca sa ajunga totul numai din sageti si OK. Serviciul
		si emisiunea se tin minte aici: cat e meniul deschis, bara e ascunsa si cursorul ei s-a sters."""
		r, ev = self._live()
		if r is None or not ev:
			self._descriereInchide()
			return None
		from Components import HdsTemporizare as T
		from Screens.ChoiceBox import ChoiceBox
		sref = r.sref()
		lista = []
		if T.cauta(sref, ev) is not None:
			lista.append((_("Scoate temporizatorul"), "scoate"))
		else:
			lista.append((_("Înregistrează"), "inregistreaza"))
			lista.append((_("Pune temporizator"), "temporizator"))
		lista.append((_("Ghidul canalului"), "ghid"))
		lista.append((_("Ghidul tuturor canalelor"), "toate"))

		def ales(raspuns):
			fel = raspuns[1] if raspuns else None
			try:
				if fel in ("scoate", "inregistreaza"):
					self._faInregistrare(sref, ev)
					if fel == "inregistreaza" and self.session.current_dialog is self._proprietar():
						self._reluare(sref, ev["id"])()
				elif fel == "temporizator":
					self._faTemporizator(sref, ev)
				elif fel == "ghid":
					self._faGhidCanal(sref, ev)
				elif fel == "toate":
					self._faGhidToate(sref, ev)
				else:
					self._reluare(sref, ev["id"])()
			except Exception as e:
				print("[SecondInfoBar] meniul emisiunii: %s" % e)
		# bara de titlu a meniului: cand e emisiunea si pe ce canal („Azi 21:45 · Das Erste HD”); se citesc inainte de
		# deschidere, fiindca bara ascunsa isi sterge cursorul
		try:
			info = self.session.nav.getCurrentService().info()
			nume = info.getName() if info else ""
			for semn in (u"\x86", u"\x87"):  # semnele de accent DVB din numele canalului
				nume = nume.replace(semn, "")
			titlu = C.join([C.epg_when_text(r), nume])
		except Exception:
			titlu = u""
		dlg = self.session.openWithCallback(ales, ChoiceBox, title=C.out(ev["name"]), list=lista)
		try:
			if titlu:
				dlg.setTitle(C.out(titlu))
		except Exception as e:
			print("[SecondInfoBar] meniul emisiunii: %s" % e)
		return None

	def closeScreen(self):
		# prima bara pastreaza cronometrul ei (InfoBarShowHide.hideTimer); aici se ascunde doar a doua
		self.hide()

	def getEvent(self):
		pass
