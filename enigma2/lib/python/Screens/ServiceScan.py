# Modificat de moneasoftware.com si hdsatelit.com, 2026
from .Screen import Screen
from Components.ServiceScan import ServiceScan as CScan
from Components.ProgressBar import ProgressBar
from Components.Label import Label
from Components.Sources.StaticText import StaticText
from Components.ActionMap import ActionMap
from Components.FIFOList import FIFOList
from Components.Sources.FrontendInfo import FrontendInfo
from enigma import eTimer, ePoint, eSize

class ServiceScanSummary(Screen):
	# HDSatelit: numele de culoare dark era definit doar in vechiul data/skin.xml, care nu se
	# mai incarca (jurnalul de pe receptor: eSlider ... not applied); aici e valoarea lui, scrisa direct
	skin = """
	<screen position="0,0" size="132,64">
		<widget name="Title" position="6,4" size="120,42" font="Regular;16" transparent="1" />
		<widget name="scan_progress" position="6,50" zPosition="1" borderWidth="1" size="56,12" backgroundColor="#25062748" />
		<widget name="Service" position="6,22" size="120,26" font="Regular;12" transparent="1" />
	</screen>"""
	
	def __init__(self, session, parent, showStepSlider = True):
		Screen.__init__(self, session, parent)
		
		self["Title"] = Label(parent.title or "ServiceScan")
		self["Service"] = Label("No Service")
		self["scan_progress"] = ProgressBar()
		
	def updateProgress(self, value):
		self["scan_progress"].setValue(value)

	def updateService(self, name):
		self["Service"].setText(name)

class ServiceScan(Screen):

	# HDSatelit: semn ca se cauta. Pe receptorul real (motor USALS, 19.2E) procentul a stat
	# mult pe loc cat se misca antena si ecranul parea blocat. Widgetul scan_activity arata puncte care
	# cresc de la 1 la 3 cat timp merge cautarea; fiecare cadru incepe cu cel dinainte, deci punctele
	# nu se misca pe loc. La sfarsit se opresc si dispar; rezultatul din scan_state trece in locul lor.
	# Un singur eTimer, doar text (fara imagini, fara texte de tradus).
	ACTIVITY_FRAMES = ("\u2022", "\u2022 \u2022", "\u2022 \u2022 \u2022")
	ACTIVITY_INTERVAL = 400 # ms

	def ok(self):
		print("ok")
		if self["scan"].isDone():
			self.close()
	
	def cancel(self):
		self.close()
		
	def __init__(self, session, scanList):
		Screen.__init__(self, session)
		
		self.scanList = scanList
		try:
			from Screens.HdsCautareCanale import noteaza_dupa_scanare
			noteaza_dupa_scanare(None)
		except Exception as e:
			print("[ServiceScan] oferta de piste: %s" % e)
		# HDSatelit: ecranul nu avea titlu (randul de sus ramanea gol); textul exista deja tradus
		self.setTitle(_("Service Scan"))

		self.session.nav.stopService()
		
		self["scan_progress"] = ProgressBar()
		self["scan_state"] = Label(_("scan state"))
		self["scan_activity"] = Label("")
		# HDSatelit: timpul ramas, transponderele (12 din 89) si rezumatul de la sfarsit
		self["scan_eta"] = Label("")
		self["scan_transponders"] = Label("")
		self["scan_result"] = Label("")
		self["network"] = Label()
		self["transponder"] = Label()
		# HDSatelit: caseta retelei gasite (Components/HdsRetele.py): numele retelei din semnal, frecventele anuntate,
		# canalele cu numarul operatorului; aratata la sfarsit, sub rezumat, numai cand scanarea a citit o retea
		self["scan_network_card"] = Label("")
		self["scan_network_heading"] = Label("")
		self["scan_network_name"] = Label("")
		self["scan_network_facts"] = Label("")
		self["scan_network_hint"] = Label("")
		self.onLayoutFinish.append(self.hdsAscundeReteaua)
		# HDSatelit: rezumatul de la sfarsit in casete (cifra mare, eticheta si randul mic), cand skinul le are;
		# scan_result ramane pentru ce nu intra in casete (erori, pozitii fara TV, indicii) si pentru alte skinuri
		for k in self.HDS_CIFRE:
			for parte in ("box", "num", "cap", "sub"):
				self["scan_%s_%s" % (parte, k)] = Label("")
		self["scan_place"] = Label("")
		self["scan_box_place"] = Label("")
		self["scan_hint_ok"] = Label("")
		# tasta albastra ca in celelalte ecrane (HdsCadru1240): semnul colorat apare numai cand are text
		self["key_blue"] = StaticText("")
		self.hdsRezultatWeb = None
		self.onLayoutFinish.append(self.hdsAscundeCifrele)

		self["pass"] = Label("")
		self["servicelist"] = FIFOList(len=10)
		self["FrontendInfo"] = FrontendInfo()
		
		self["actions"] = ActionMap(["OkCancelActions", "ColorActions"],
			{
				"ok": self.ok,
				"cancel": self.cancel,
				"blue": self.hdsCitestePiste
			})

		# numele activityTimer, nu timer: subclasa DefaultServiceScan isi pune propriul self.timer
		self.activityStep = 0
		self.activityTimer = eTimer()
		self.activityTimer.callback.append(self.updateActivity)
		self.onClose.append(self.stopActivity)
		self.onClose.append(self.hdsPisteDupaScanare)

		self.onFirstExecBegin.append(self.doServiceScan)

	HDS_CIFRE = ("canale", "tv", "radio", "transp", "durata")
	HDS_CASETA = ("scan_network_card", "scan_network_heading", "scan_network_name", "scan_network_facts", "scan_network_hint")
	HDS_CASETA_JOS = 912      # sub ea linia de jos a ferestrei (HdsCadru1240)
	HDS_CASETA_SPATIU = 16    # intre rezumat si caseta, si marginea de sus/jos a casetei

	def hdsAscundeReteaua(self):
		# fundalul casetei: un dreptunghi (Pro) care cuprinde textele, sau o linie subtire deasupra lor (Clasic)
		card = self["scan_network_card"].instance
		self.hdsCasetaLinie = card is not None and card.size().height() <= 2
		for nume in self.HDS_CASETA:
			self[nume].hide()

	def hdsAseazaReteaua(self, arata):
		"""Caseta retelei pusa sub textul rezumatului (care are mai multe sau mai putine randuri, la orice marime a
		textului): titlul, numele, datele si indiciul unul sub altul, fiecare cat ii e textul; fundalul casetei
		cuprinde tot (la Clasic e numai linia de deasupra). Fara loc pana la marginea de jos, ultimele texte se strang."""
		if not arata:
			self.hdsAscundeReteaua()
			return
		from Components import HdsMarireText as MT
		rez = self["scan_result"].instance
		card = self["scan_network_card"].instance
		if rez is None or card is None:
			return
		x, w = card.position().x(), card.size().width()
		pad = self.HDS_CASETA_SPATIU
		y0 = rez.position().y() + MT.inaltimeText(rez) + pad
		y = y0 + pad
		for nume in self.HDS_CASETA[1:]:
			inst = self[nume].instance
			if inst is None:
				continue
			h = MT.inaltimeText(inst) if self[nume].getText() else 0
			h = max(0, min(h, self.HDS_CASETA_JOS - pad - y))
			inst.move(ePoint(inst.position().x(), y))
			inst.resize(eSize(inst.size().width(), max(1, h)))
			if h:
				self[nume].show()
				y += h + 4
			else:
				self[nume].hide()
		card.move(ePoint(x, y0))
		if not getattr(self, "hdsCasetaLinie", False):
			card.resize(eSize(w, max(1, min(y + pad - 4, self.HDS_CASETA_JOS) - y0)))
		self["scan_network_card"].show()

	def hdsAreCifre(self):
		"""Skinul are casetele cifrelor (atribute din skin pe cifra canalelor); altfel rezumatul ramane text."""
		return bool(getattr(self["scan_num_canale"], "skinAttributes", None))

	def hdsElementeCifre(self):
		for k in self.HDS_CIFRE:
			for parte in ("box", "num", "cap", "sub"):
				yield "scan_%s_%s" % (parte, k)
		yield "scan_place"
		yield "scan_box_place"
		yield "scan_hint_ok"

	def hdsAscundeCifrele(self):
		rez = self["scan_result"].instance
		if rez is not None:
			self.hdsRezultatLoc = (rez.position().x(), rez.position().y(), rez.size().width(), rez.size().height())
		for nume in self.hdsElementeCifre():
			self[nume].hide()

	@staticmethod
	def hdsTexteCifre(cifre):
		"""Textele casetelor, din cifrele rezumatului: {cheie: (cifra, eticheta, randul mic)}; None la o caseta fara
		valoare (nucleul nu da felurile canalelor, durata necunoscuta). Aceleasi pentru televizor si pagina web."""
		def numar(v):
			return "%d" % v if v is not None else "?"
		subtv = []
		if cifre["hd"] is not None:
			subtv.append(_("HD: %d") % cifre["hd"])
		if cifre["uhd"] is not None:
			subtv.append(_("4K: %d") % cifre["uhd"])
		texte = {
			"canale": (numar(cifre["canale"]), _("Canale găsite"), _("new: %d") % cifre["noi"] if cifre["noi"] is not None else ""),
			"tv": (numar(cifre["tv"]), _("TV"), u" · ".join(subtv)),
			"radio": (numar(cifre["radio"]), _("Radio"), _("other services: %d") % cifre["alte"] if cifre["alte"] else ""),
			"transp": (numar(cifre["transpondere"]), _("Transpondere"),
				_("without signal: %d") % cifre["fara_semnal"] if cifre["fara_semnal"] is not None else ""),
			"durata": (cifre["durata"], _("Durata"), ""),
		}
		if cifre["tv"] is None:
			texte["tv"] = texte["radio"] = None
		if not cifre["durata"]:
			texte["durata"] = None
		return texte

	def hdsArataCifrele(self):
		"""La sfarsit, cand s-a gasit ceva si skinul are casetele: cifrele in casete, locul cautat pe randul lui, iar in
		scan_result numai randurile care nu se vad in casete, mutat sub ele. Pagina web primeste tot textul (hdsRezultatWeb)."""
		scan = self.get("scan")
		if scan is None or getattr(self, "hdsCifrePuse", False):
			return False
		self.hdsCifrePuse = True
		self.hdsRezultatWeb = [r for r in self["scan_result"].getText().split("\n") if r.strip()]
		self.hdsRezultatBaza = len(self.hdsRezultatWeb)
		cifre = scan.hdsCifre() if hasattr(scan, "hdsCifre") else None
		if cifre is None or not self.hdsAreCifre():
			return False

		texte = self.hdsTexteCifre(cifre)
		jos = None
		for k in self.HDS_CIFRE:
			t = texte.get(k)
			for parte, text in zip(("num", "cap", "sub"), t or ("", "", "")):
				self["scan_%s_%s" % (parte, k)].setText(text)
			if not t:
				continue
			for parte in ("box", "num", "cap", "sub"):
				self["scan_%s_%s" % (parte, k)].show()
			for parte in ("box", "num", "sub"):
				inst = self["scan_%s_%s" % (parte, k)].instance
				if inst is not None:
					jos = max(jos or 0, inst.position().y() + inst.size().height())
		self["scan_place"].setText(cifre["loc"])
		loc = self["scan_place"].instance
		if cifre["loc"] and loc is not None:
			self["scan_place"].show()
			self["scan_box_place"].show()
			jos = max(jos or 0, loc.position().y() + loc.size().height())
		# restul randurilor, sub casete
		rest = scan.resultLines(faraCifre=True)
		self["scan_result"].setText("\n".join(rest))
		rez = self["scan_result"].instance
		loc0 = getattr(self, "hdsRezultatLoc", None)
		if rez is not None and loc0 is not None and jos is not None:
			# fara rest, eticheta goala sta lipita de casete, ca loc sa ramana casetei retelei (cablu)
			y = jos + self.HDS_CASETA_SPATIU if rest else jos
			rez.move(ePoint(loc0[0], y))
			rez.resize(eSize(loc0[2], max(1, loc0[1] + loc0[3] - y) if rest else 1))
		# caseta retelei se aseaza din nou sub rezumatul mutat (si in asistent, unde hdsOfertaPiste nu ajunge)
		self.hdsAseazaReteaua(bool(getattr(scan, "hdsRetele", None)))
		return True

	def doServiceScan(self):
		caseta = {"titlu": self["scan_network_heading"], "nume": self["scan_network_name"], "date": self["scan_network_facts"],
			"indiciu": self["scan_network_hint"], "aseaza": self.hdsAseazaReteaua}
		self["scan"] = CScan(self["scan_progress"], self["scan_state"], self["servicelist"], self["pass"], self.scanList, self["network"], self["transponder"], self["FrontendInfo"], self.session.summary,
			eta=self["scan_eta"], transponders=self["scan_transponders"], result=self["scan_result"], networkCard=caseta)
		self.activityStep = 0
		self["scan_activity"].setText(self.ACTIVITY_FRAMES[0])
		self.activityTimer.start(self.ACTIVITY_INTERVAL)

	def updateActivity(self):
		scan = self.get("scan")
		started = False
		try:
			done = scan is not None and scan.isDone()
			started = scan is not None
		except AttributeError: # starea se pune abia la pornirea cautarii (CScan.doRun)
			done = False
		if done:
			self.stopActivity()
			self.hdsArataCifrele()
			self.hdsOfertaPiste()
			self.hdsIndiciuT2()
			self.alignResult()
			return
		self.activityStep = (self.activityStep + 1) % len(self.ACTIVITY_FRAMES)
		self["scan_activity"].setText(self.ACTIVITY_FRAMES[self.activityStep])
		# timpul ramas scade si intre doua transpondere (textul se schimba doar din 10 in 10 s)
		if started:
			scan.refreshEta()

	def stopActivity(self):
		self.activityTimer.stop()
		if "scan_activity" in self:
			self["scan_activity"].setText("")

	def alignResult(self):
		# cand punctele stau pe acelasi rand, in fata starii (skinul HDSatelit), rezultatul final
		# trece in locul lor, aliniat cu randurile de deasupra, in loc sa ramana un gol in fata lui
		try:
			(ax, ay) = self["scan_activity"].getPosition()
			(sx, sy) = self["scan_state"].getPosition()
			if ay == sy and ax < sx:
				st = self["scan_state"].instance
				size = st.size()
				st.move(ePoint(ax, ay))
				st.resize(eSize(size.width() + sx - ax, size.height()))
		except AttributeError: # widget fara instanta
			pass

	def hdsPisteDupaScanare(self):
		# Iesirea pastreaza oferta pentru web. Citirea porneste numai la alegerea ALBASTRU.
		try:
			scan = self.get("scan")
			if scan is None or not scan.isDone():
				return
			if self.hdsDinAsistent():
				return
			ceAScanat = getattr(scan, "hdsCeAScanat", None)
			scanat = ceAScanat() if ceAScanat is not None and getattr(scan, "foundServices", 0) else None
			from Screens.HdsCautareCanale import noteaza_dupa_scanare, intreaba_dupa_scanare
			noteaza_dupa_scanare(scanat)
			if getattr(self, "hdsCitesteLaInchidere", False) and getattr(scan, "foundServices", 0):
				intreaba_dupa_scanare(self.session, scanat=scanat)
		except Exception as e:
			print("[ServiceScan] pistele dupa scanare: %s" % e)

	def hdsOfertaPiste(self):
		scan = self.get("scan")
		if (getattr(self, "hdsOfertaPusa", False) or scan is None
				or not getattr(scan, "foundServices", 0) or self.hdsDinAsistent()):
			return
		self.hdsOfertaPusa = True
		self.hdsPisteDupaScanare()
		indiciu = _("ALBASTRU: citește pistele canalelor găsite. OK sau EXIT: revino la vizionare.")
		if self.hdsAreCifre() and self["scan_num_canale"].getText():
			# skinul cu casete: tasta albastra jos, ca buton, si OK/EXIT langa ea; pagina web pastreaza randul intreg
			self["key_blue"].setText(_("Citește pistele"))
			self["scan_hint_ok"].setText(_("OK sau EXIT: închide"))
			self["scan_hint_ok"].show()
		else:
			label = self["scan_result"]
			label.setText("\n".join([t for t in (label.getText(), indiciu) if t]))
		self.hdsAdaugaWeb([indiciu])
		self.hdsAseazaReteaua(bool(getattr(scan, "hdsRetele", None)))

	def hdsIndiciuT2(self):
		"""A35 (anestis1956, Cipru 39E): canalele DVB-T2 prin satelit stau in pachete T2-MI, pe care cautarea obisnuita nu
		le desface (gaseste cel mult serviciul purtator, fara nume). Dupa o cautare pe o pozitie care are operatori DVB-T2
		in data/operatori-satelit.json, un rand spune unde se gasesc; il vede si pagina web (scan_result). Unde fluxurile
		au programele stiute si transponderul lor s-a prins, ele intra singure in lista (Hds/DabT2/imagine.dupa_scanare,
		ca fluxurile Abertis), iar randul spune in ce buchet."""
		if getattr(self, "hdsIndiciuPus", False) or self.hdsDinAsistent():
			return
		self.hdsIndiciuPus = True
		try:
			scan = self.get("scan")
			ceAScanat = getattr(scan, "hdsCeAScanat", None) if scan is not None else None
			pozitii = set(p for p in ((ceAScanat() or {}).get("pozitii") or ()) if isinstance(p, int)) if ceAScanat else set()
			if not pozitii:
				return
			from Components.HdsOperatoriSatelit import operatori, nume_tara
			from Components.HdsGrade import pozitieOrbitala
			ops = [o for o in operatori("t2mi") if o.get("pozitie") in pozitii]
			# fluxurile cu programele stiute, pe un transponder prins acum, intra singure in lista (imagine.dupa_scanare)
			intra = {}
			if ops:
				from Hds.DabT2 import imagine as hds_imagine
				intra = hds_imagine.buchete_dupa_scanare(list(set(o["pozitie"] for o in ops)))

			def intra_singur(o):
				t = o.get("transponder") or {}
				return any(pol == t.get("pol") and abs(khz - int(t.get("frecventa") or 0)) <= 2000
					for khz, pol in (intra.get(o["pozitie"]) or {}).get("tp", []))
			pe, singure = {}, {}
			for o in ops:
				tara = nume_tara((o.get("tari") or ["?"])[0])
				d = singure if intra_singur(o) else pe
				if tara not in d.setdefault(o["pozitie"], []):
					d[o["pozitie"]].append(tara)
			randuri = []
			for p in sorted(set(pe) | set(singure)):
				if singure.get(p):
					randuri.append(_("Canalele DVB-T2 prin satelit de pe %s (%s) intră singure în lista de canale, în %s.")
						% (pozitieOrbitala(p) or p, ", ".join(singure[p]), ", ".join("„%s”" % b for b in intra[p]["buchete"])))
				rest = [t for t in pe.get(p, []) if t not in singure.get(p, [])]
				if rest:
					randuri.append(_("Pe %s sunt și canale DVB-T2 prin satelit (%s), pe care căutarea obișnuită nu le "
						"vede: Scanare > Satelit > DVB-T2 prin satelit.") % (pozitieOrbitala(p) or p, ", ".join(rest)))
			if randuri:
				label = self["scan_result"]
				label.setText("\n".join([t for t in [label.getText()] + randuri if t]))
				self.hdsAdaugaWeb(randuri)
		except Exception as e:
			print("[ServiceScan] randul DVB-T2 prin satelit: %s" % e)

	def hdsAdaugaWeb(self, randuri):
		if self.hdsRezultatWeb is not None:
			self.hdsRezultatWeb.extend(randuri)

	def hdsRezultatPentruWeb(self):
		"""Toate randurile rezumatului, ca text (pagina web, /api/scanare-stare), si cand televizorul le arata in casete."""
		if self.hdsRezultatWeb is not None:
			return list(self.hdsRezultatWeb)
		return [r for r in self["scan_result"].getText().split("\n") if r.strip()]

	def hdsCifrePentruWeb(self):
		"""Casetele rezumatului pentru pagina web, cu textele televizorului: {"casete": [{"cifra", "eticheta", "sub"}],
		"loc": randul satelitului, "rest": randurile care nu intra in casete}; None pana la sfarsit sau fara canale."""
		scan = self.get("scan")
		try:
			cifre = scan.hdsCifre() if scan is not None and scan.isDone() else None
		except AttributeError:
			return None
		if cifre is None:
			return None
		texte = self.hdsTexteCifre(cifre)
		casete = [{"cheie": k, "cifra": texte[k][0], "eticheta": texte[k][1], "sub": texte[k][2]}
			for k in self.HDS_CIFRE if texte.get(k)]
		toate = self.hdsRezultatPentruWeb()
		rest = scan.resultLines(faraCifre=True)
		# randurile adaugate de ecran (indiciul DVB-T2, tasta albastra) dupa rezumat
		baza = getattr(self, "hdsRezultatBaza", None)
		if baza is not None:
			rest = rest + toate[baza:]
		return {"casete": casete, "loc": cifre["loc"], "rest": rest}

	def hdsCitestePiste(self):
		scan = self.get("scan")
		if (scan is not None and scan.isDone() and getattr(scan, "foundServices", 0)
				and not self.hdsDinAsistent()):
			self.hdsCitesteLaInchidere = True
			self.close()

	def hdsDinAsistent(self):
		try:
			from Components.config import config
			if config.misc.firstrun.value:
				return True
		except (AttributeError, KeyError, ImportError):
			pass
		try:
			from Screens.Wizard import Wizard
		except ImportError:
			return False
		ecrane = [d for (d, _vizibil) in getattr(self.session, "dialog_stack", ())]
		return any(isinstance(d, Wizard) for d in ecrane)

	def createSummary(self):
		print("ServiceScanCreateSummary")
		return ServiceScanSummary
