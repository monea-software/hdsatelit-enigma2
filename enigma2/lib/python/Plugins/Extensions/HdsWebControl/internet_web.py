# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# internet_web.py: perechile web ale ecranelor din Meniu > Setari > Surse Internet (HdsWebControl). Orice ecran de pe
# receptor are pereche in interfata web, cu aceleasi setari si actiuni.
#
#   /dvb-i          DVB-I Setup (Screens/HdsDvbI.py HdsDvbISetup): DVB-I activ, listele predefinite bifate, adresele
#                   proprii (adaugare, stergere cu confirmare); /dvb-i?f=reincarca = DVB-I Reload Now (HdsDvbIReloadNow):
#                   reincarcarea porneste singura, cu starea si rezultatul ca pe televizor. Logica: Components/HdsDvbISetari.
#   /mabr           DVB-MABR (Screens/HdsDvbMABR.py, in lucru): activ, autodiscover, grupurile multicast (adaugare,
#                   stergere cu confirmare), cautarea SAP. Logica: Components/HdsMabrSetari.
#   /iptv           IPTV (Screens/IptvSetup.py, in lucru): lista surselor (adaugare M3U, stergere cu confirmare) si
#                   config.hds_iptv.* (tipul sursei, M3U, Stalker, Xtream; pe televizor in "Date de acces", Albastru).
#                   Parola Xtream numai se scrie sau se sterge, nu se arata, si se primeste numai din corpul cererii.
#                   Logica si verificarea textelor: Components/HdsIptvSurse (aceleasi pe televizor).
#   /interfata-web  Interfata web (Screens/HdsWebControlSetup.py): pornirea si portul (oprirea si mutarea cu confirmare
#                   si avertismentul ca pagina se pierde sau se muta), browserele conectate (deconectarea, cod nou pe
#                   televizor, cu confirmare), cheia pentru scripturi (ascunsa, puncte; butonul Arata cheia o cere
#                   intreaga prin POST /api/interfata-web-secrete?ce=cheie, din plugin.py; tasta Cheie noua pentru
#                   panoul web cu confirmare: cheie noua si toate aparatele asociate deconectate, in afara de browserul
#                   care cere, ca pe televizor, cheieNouaPanou). Parola pentru aplicatii la fel: puncte pana la butonul
#                   Arata parola (?ce=parola); nici HTML-ul, nici GET-urile paginii nu au parola sau cheia.
#                   Randurile cod_retea_locala, aplicatii, aplicatii_afara si parola pentru aplicatii merg
#                   prin rutele care exista deja (plugin.py: /api/interfata-web, /api/interfata-web-seteaza).
#
# Rute (poarta comuna a HdsJsonResource; ce schimba ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF):
#   GET  /api/dvb-i                 starea
#   POST /api/dvb-i-seteaza         activ=0|1 | predefinita=<cheie>&bifata=0|1 | adauga_url=<adresa>
#   POST /api/dvb-i-sterge          index=N, in doi pasi (pas=intreaba, cod=..., pas=renunta)
#   POST /api/dvb-i-reincarca       reincarcarea acum
#   GET  /api/mabr                  starea
#   POST /api/mabr-seteaza          activ=0|1 | autodiscover=0|1 | adauga=<adresa:port>
#   POST /api/mabr-sterge           index=N, in doi pasi
#   POST /api/mabr-cauta            cautarea SAP (5 secunde, pe fir); rezultatul vine in GET
#   GET  /api/iptv                  starea (fara parola)
#   POST /api/iptv-seteaza          tip_sursa, m3u_cale, stalker_portal, stalker_mac, xtream_server, xtream_port,
#                                   xtream_user; xtream_parola (numai din corp); sterge=xtream_parola
#   POST /api/iptv-adauga           [m3u_cale=...] adauga sursa M3U, ca Galben pe televizor
#   POST /api/iptv-sterge           index=N, in doi pasi
#   GET  /api/interfata-web-detalii pornirea, portul, browserele (fara cheie)
#   POST /api/interfata-web-actiune fapta=activ&valoare=0|1 | fapta=port&valoare=N | fapta=deconecteaza |
#                                   fapta=cheie | fapta=browser_nou; cele periculoase in doi pasi
#   GET  /dvb-i, /mabr, /iptv, /interfata-web   paginile
# Actiunile in doi pasi se refuza cand vin cu ?token= (meniu_comun_web.numaiBrowser).
#
# FIRUL: totul ruleaza pe firul enigma2 si e scurt (fisiere mici); reincarcarea DVB-I si cautarea SAP merg pe firele
# lor (Components), iar pagina citeste starea din nou. Fisierul nu importa nimic din enigma2 la incarcare.

MAX_TEXT = 512


def _t(text):
	from .meniu_comun_web import _t as t
	return t(text)


def _M():
	from . import meniu_comun_web
	return meniu_comun_web


def _jurnal(text):
	print("[HdsWebControl] internet: %s" % text)


def _bool(text):
	"""'0' / '1' -> False / True; altceva -> None."""
	if text == "1":
		return True
	if text == "0":
		return False
	return None


def _index(text):
	return int(text) if text and text.isdigit() and len(text) < 6 else -1


def _doiPasi(arg, actiune, tinta, intrebare, buton, detalii, fapta):
	"""Confirmarea in doi pasi (meniu_comun_web): pas=intreaba -> intrebarea si codul; pas=renunta -> codul uitat;
	cod=<cod> -> fapta(), numai cu codul cerut pentru aceeasi actiune si tinta."""
	M = _M()
	pas = arg.get("pas", "")
	if pas == "intreaba":
		return M.raspunsIntrebare(actiune, tinta, intrebare, buton, detalii)
	if pas == "renunta":
		M.uita(actiune, tinta)
		return {"result": True, "message": _t("Nu s-a făcut nimic.")}
	if not M.verifica(actiune, tinta, arg.get("cod", "")):
		return M.codGresit()
	return fapta()


def _cuMesaj(rez, reusit, mesaj):
	rez.update({"result": bool(reusit), "message": mesaj})
	return rez


# ================================================================== DVB-I
def _dvbi(D=None):
	if D is not None:
		return D
	from Components import HdsDvbISetari
	return HdsDvbISetari


def _reincarcare(D):
	st = D.stareReincarcare()
	if st["in_curs"]:
		mesaj = _t("Se reîncarcă listele DVB-I configurate...")
	elif st["gata"] and st["succes"]:
		mesaj = _t("Reîncărcare terminată cu succes.")
	elif st["gata"]:
		mesaj = _t("Reîncărcarea a eșuat: %s") % (st["eroare"] or "?")
	else:
		mesaj = ""
	return {"in_curs": bool(st["in_curs"]), "gata": bool(st["gata"]), "succes": st["succes"], "mesaj": mesaj,
		"ora": st.get("ora", 0)}


def _dateDvbi(DD=None):
	if DD is not None:
		return DD
	try:
		from Components import HdsDvbIDate
		return HdsDvbIDate
	except Exception:
		return None


def _pluginDvbi():
	try:
		from Plugins.SystemPlugins.HdsDvbI import plugin
		return plugin
	except Exception:
		return None


def _vpnDvbi():
	"""{disponibil, conectat, mod} pentru nota canalelor oprite pe tara (fara secrete)"""
	try:
		from Components.SystemInfo import SystemInfo
		if not SystemInfo.get("HdsVpn"):
			return {"disponibil": False, "conectat": False, "mod": ""}
		from Components import HdsVpn
		s = HdsVpn.stare()
		return {"disponibil": True, "conectat": s.get("legatura") == "conectat", "mod": s.get("mod", "")}
	except Exception:
		return {"disponibil": False, "conectat": False, "mod": ""}


def _canaleDvbi(DD):
	"""randurile tabelului de canale din pagina: numarul din lista (LCN), locul din buchet, starea incercarii din casa"""
	if DD is None:
		return [], {}
	rez = []
	n = {}
	for c in DD.canale():
		st, cod, ora = DD.stareUrl(c.get("url", ""))
		n[st] = n.get(st, 0) + 1
		rez.append({"id": c.get("id"), "nr": c.get("nr"), "lcn": c.get("lcn"), "nume": c.get("nume", ""),
			"tip": c.get("tip", "tv"), "url": c.get("url", ""), "sat": bool(c.get("sat")), "stare": st, "cod": cod,
			"ora": ora})
	return rez, n


def stareDvbi(D=None, cale=None, DD=None, registru=None):
	"""GET /api/dvb-i."""
	D = _dvbi(D)
	cfg = D.citeste(cale)
	bifate = set(cfg.get("predefinite", []))
	rez = {"result": True, "activ": D.esteActiv(cfg), "text_stare": D.textStare(cfg),
		"predefinite": [{"cheie": c, "descriere": d, "tara": t, "bifata": c in bifate}
			for c, d, _a, t in D.listePredefinite()],
		"url_uri": list(cfg.get("url_uri", [])), "reincarcare": _reincarcare(D)}
	# DVB-I: tara si regiunea din registre, listele tarii, trecerea pe internet, canalele incercate din casa
	if not hasattr(D, "listeleTarii"):
		return rez
	DD = _dateDvbi(DD)
	stare = DD.stare() if DD is not None else {}
	reg = registru if registru is not None else _registruDvbi()
	canale, n = _canaleDvbi(DD)
	culoare, text, detalii = D.rezumatEcran(cfg, reg, stare, D.stareReincarcare())
	p = _pluginDvbi()
	try:
		incercare = p.stareIncercare() if p is not None else {}
	except Exception:
		incercare = {}
	rez.update({
		"tara": cfg.get("tara", ""), "tara_nume": D.numeTara(cfg.get("tara", "")),
		"tari": [{"cod": c, "nume": nume, "liste": k, "reale": r} for c, nume, k, r in D.tariOrdonate(reg)],
		"registre": {"in_curs": bool(D.stareRegistre().get("in_curs")), "ora": int(reg.get("ora", 0) or 0),
			"mesaj": "" if reg.get("liste") else D.textFaraRegistre(reg)},
		"regiune": cfg.get("regiune", ""),
		"regiuni": [{"id": i, "nume": nume, "nivel": niv} for i, nume, niv in D.regiuniTarii(cfg, stare, reg)],
		"liste_tarii": [dict(l, canale=D.canaleLista(stare, l["adresa"])) for l in D.listeleTarii(cfg, reg)],
		"rezerva": D.rezervaPornita(cfg),
		"stare": {"culoare": culoare, "text": text, "detalii": detalii},
		"canale": canale, "rezumat": n,
		"incercare": {"in_curs": bool(incercare.get("in_curs")), "facute": int(incercare.get("facute", 0) or 0),
			"total": int(incercare.get("total", 0) or 0)},
		"vpn": _vpnDvbi(),
	})
	return rez


def dvbiPanou(ref, DD=None):
	"""Randul "Acum pe receptor" din panou (plugin.py StatusInfoResource): {"are", "prin_internet", "retea"}, ca eticheta
	DVB-I si "prin internet" din bara de pe televizor (Converter/HdsInfo HasDvbI / ViaInternet)."""
	DD = _dateDvbi(DD)
	rez = {"are": False, "prin_internet": False, "retea": ""}
	if DD is None or not ref:
		return rez
	rez["prin_internet"] = bool(DD.esteDvbI(ref))
	rez["are"] = rez["prin_internet"] or DD.legaturaRef(ref) is not None
	if rez["prin_internet"]:
		try:
			from Components import HdsStareRetea
			rez["retea"] = HdsStareRetea.text_ajutor(HdsStareRetea.stare())
		except Exception:
			pass
	return rez


def _registruDvbi():
	try:
		from Components import HdsDvbIRegistru
		return HdsDvbIRegistru.incarca()
	except Exception:
		return {"ora": 0, "registre": [], "liste": []}


def seteazaDvbi(arg, D=None, cale=None):
	"""POST /api/dvb-i-seteaza: o singura schimbare pe cerere; o valoare straina nu schimba nimic."""
	D = _dvbi(D)
	cfg = D.citeste(cale)
	reincarca = False
	if "activ" in arg:
		v = _bool(arg["activ"])
		if v is None:
			return _cuMesaj(stareDvbi(D, cale), False, _t("Se alege cu activ=0 sau 1."))
		if v != D.esteActiv(cfg):
			D.comutaActiv(cfg)
		mesaj = _t("Salvat.")
	elif "predefinita" in arg:
		v = _bool(arg.get("bifata", ""))
		cheie = arg["predefinita"]
		if v is None or cheie not in [c for c, _d, _a, _t2 in D.listePredefinite()]:
			return _cuMesaj(stareDvbi(D, cale), False, _t("Lista predefinită aleasă nu există."))
		if v != (cheie in cfg.get("predefinite", [])):
			D.comutaPredefinita(cfg, cheie)
		mesaj = _t("Salvat.")
	elif "adauga_url" in arg:
		reusit, mesaj = D.adaugaUrl(cfg, arg["adauga_url"])
		if not reusit:
			return _cuMesaj(stareDvbi(D, cale), False, mesaj)
		mesaj = _t("Adresa a fost adăugată.")
	elif "tara" in arg and hasattr(D, "seteazaTara"):
		tara = arg["tara"].strip().upper()
		if tara and tara not in [c for c, _n, _a, _b in D.tariOrdonate()]:
			return _cuMesaj(stareDvbi(D, cale), False, _t("Țara aleasă nu are liste DVB-I în registre."))
		D.seteazaTara(cfg, tara)
		mesaj = _t("Salvat. Listele țării se descarcă acum.") if tara else _t("Salvat.")
		reincarca = True
	elif "regiune" in arg and hasattr(D, "seteazaRegiune"):
		regiune = arg["regiune"].strip()
		if regiune and regiune not in [r for r, _n, _v in D.regiuniTarii(cfg)]:
			return _cuMesaj(stareDvbi(D, cale), False, _t("Regiunea aleasă nu e în listele țării."))
		D.seteazaRegiune(cfg, regiune)
		mesaj = _t("Salvat. Listele se descarcă din nou, cu numerele regiunii.")
		reincarca = True
	elif "lista" in arg and hasattr(D, "comutaListaTarii"):
		v = _bool(arg.get("bifata", ""))
		lista = [l for l in D.listeleTarii(cfg) if l["adresa"] == arg["lista"]]
		if v is None or not lista:
			return _cuMesaj(stareDvbi(D, cale), False, _t("Lista aleasă nu e a țării."))
		if v != lista[0]["aleasa"]:
			D.comutaListaTarii(cfg, arg["lista"])
		mesaj = _t("Salvat. Listele se descarcă din nou.")
		reincarca = True
	elif "rezerva" in arg and hasattr(D, "comutaRezerva"):
		v = _bool(arg["rezerva"])
		if v is None:
			return _cuMesaj(stareDvbi(D, cale), False, _t("Se alege cu rezerva=0 sau 1."))
		if v != D.rezervaPornita(cfg):
			D.comutaRezerva(cfg)
		mesaj = _t("Salvat.")
	else:
		return _cuMesaj(stareDvbi(D, cale), False, _t("Nu s-a trimis nicio setare."))
	if not D.scrie(cfg, cale):
		return _cuMesaj(stareDvbi(D, cale), False, _t("Setările nu s-au putut salva."))
	if reincarca:
		D.reincarca()
	return _cuMesaj(stareDvbi(D, cale), True, mesaj)


def incearcaDvbi(D=None, cale=None, P=None):
	"""POST /api/dvb-i-incearca: canalele incercate din nou din casa (Galben pe televizor)"""
	D = _dvbi(D)
	P = P if P is not None else _pluginDvbi()
	if P is None or not P.incearca_acum(forteaza=True):
		return _cuMesaj(stareDvbi(D, cale), False, _t("Canalele se încearcă deja."))
	return _cuMesaj(stareDvbi(D, cale), True, _t("Canalele se încearcă acum din casă, unul câte unul."))


def registreDvbi(D=None, cale=None):
	"""POST /api/dvb-i-registre: registrele DVB-I intrebate din nou (tarile si listele lor)"""
	D = _dvbi(D)
	if not D.intreabaRegistrele():
		return _cuMesaj(stareDvbi(D, cale), False, _t("Registrele se întreabă deja."))
	return _cuMesaj(stareDvbi(D, cale), True, _t("Se întreabă registrele DVB-I..."))


def stergeDvbi(arg, D=None, cale=None):
	"""POST /api/dvb-i-sterge?index=N: o adresa proprie scoasa, in doi pasi (tinta = adresa insasi)."""
	D = _dvbi(D)
	cfg = D.citeste(cale)
	url_uri = cfg.get("url_uri", [])
	i = _index(arg.get("index", ""))
	if not 0 <= i < len(url_uri):
		return _cuMesaj(stareDvbi(D, cale), False, _t("Adresa aleasă nu mai e în listă. Pagina se încarcă din nou."))
	url = url_uri[i]

	def fapta():
		D.stergeUrl(cfg, i)
		if not D.scrie(cfg, cale):
			return _cuMesaj(stareDvbi(D, cale), False, _t("Setările nu s-au putut salva."))
		return _cuMesaj(stareDvbi(D, cale), True, _t("Adresa a fost ștearsă."))

	return _doiPasi(arg, "dvbi-sterge", url, _t("Ștergi adresa din listele DVB-I?"), _t("Da, șterge"), [url], fapta)


def reincarcaDvbi(D=None, cale=None):
	"""POST /api/dvb-i-reincarca: ca DVB-I Reload Now; rezultatul se vede in GET /api/dvb-i."""
	D = _dvbi(D)
	if not D.reincarca():
		return _cuMesaj(stareDvbi(D, cale), False, _t("O reîncărcare e deja în curs."))
	return _cuMesaj(stareDvbi(D, cale), True, _t("Se reîncarcă listele DVB-I configurate..."))


# ================================================================== DVB-MABR
def _mabr(S=None):
	if S is not None:
		return S
	from Components import HdsMabrSetari
	return HdsMabrSetari


def stareMabr(S=None, cale=None):
	"""GET /api/mabr."""
	S = _mabr(S)
	cfg = S.citeste(cale)
	c = S.stareCautare()
	rezultat = c.get("rezultat")
	cautare = {"in_curs": bool(c["in_curs"]), "sesiuni": [], "mesaj": ""}
	if c["in_curs"]:
		cautare["mesaj"] = _t("Se caută sesiuni MABR în rețea (5 secunde)...")
	elif rezultat is not None:
		cautare["sesiuni"] = list(rezultat.get("sesiuni") or [])
		cautare["mesaj"] = S.mesajCautare(rezultat)
	return {"result": True, "activ": S.pornit(cfg, "activ"), "autodiscover": S.pornit(cfg, "autodiscover"),
		"text_stare": S.textStare(cfg),
		"grupuri": [{"adresa": a, "port": p, "text": S.textGrup(a, p)} for a, p in cfg.get("grupuri", [])],
		"cautare": cautare}


def seteazaMabr(arg, S=None, cale=None):
	"""POST /api/mabr-seteaza: o singura schimbare pe cerere."""
	S = _mabr(S)
	cfg = S.citeste(cale)
	cheie = "activ" if "activ" in arg else ("autodiscover" if "autodiscover" in arg else None)
	if cheie is not None:
		v = _bool(arg[cheie])
		if v is None:
			return _cuMesaj(stareMabr(S, cale), False, _t("Se alege cu 0 sau 1."))
		if v != S.pornit(cfg, cheie):
			S.comuta(cfg, cheie)
		mesaj = _t("Salvat.")
	elif "adauga" in arg:
		reusit, mesaj = S.adaugaGrup(cfg, arg["adauga"])
		if not reusit:
			return _cuMesaj(stareMabr(S, cale), False, mesaj)
	else:
		return _cuMesaj(stareMabr(S, cale), False, _t("Nu s-a trimis nicio setare."))
	if not S.scrie(cfg, cale):
		return _cuMesaj(stareMabr(S, cale), False, _t("Setările nu s-au putut salva."))
	return _cuMesaj(stareMabr(S, cale), True, mesaj)


def stergeMabr(arg, S=None, cale=None):
	"""POST /api/mabr-sterge?index=N: un grup scos, in doi pasi (tinta = adresa:port)."""
	S = _mabr(S)
	cfg = S.citeste(cale)
	grupuri = cfg.get("grupuri", [])
	i = _index(arg.get("index", ""))
	if not 0 <= i < len(grupuri):
		return _cuMesaj(stareMabr(S, cale), False, _t("Grupul ales nu mai e în listă. Pagina se încarcă din nou."))
	text = S.textGrup(*grupuri[i])

	def fapta():
		S.stergeGrup(cfg, i)
		if not S.scrie(cfg, cale):
			return _cuMesaj(stareMabr(S, cale), False, _t("Setările nu s-au putut salva."))
		return _cuMesaj(stareMabr(S, cale), True, _t("Grupul a fost șters."))

	return _doiPasi(arg, "mabr-sterge", text, _t("Ștergi grupul multicast?"), _t("Da, șterge"), [text], fapta)


def cautaMabr(S=None, cale=None):
	"""POST /api/mabr-cauta: ca Albastru (Cauta SAP) pe televizor."""
	S = _mabr(S)
	cfg = S.citeste(cale)
	if not S.cauta(cfg.get("interfata", "")):
		return _cuMesaj(stareMabr(S, cale), False, _t("O căutare e deja în curs."))
	return _cuMesaj(stareMabr(S, cale), True, _t("Se caută sesiuni MABR în rețea (5 secunde)..."))


# ================================================================== IPTV
CAMPURI_IPTV = ("m3u_cale", "stalker_portal", "stalker_mac", "xtream_server", "xtream_port", "xtream_user")
SECRETE_IPTV = ("xtream_parola",)


def _iptv(I=None):
	if I is not None:
		return I
	from Components import HdsIptvSurse
	return HdsIptvSurse


def _configIptv(I, config=None):
	if config is None:
		from Components.config import config
	return I.initConfigIptv(config)


def _alegeri(el):
	from .setari_web import _alegeri as a
	return a(el, "alegere")


def stareIptv(I=None, config=None, cale=None):
	"""GET /api/iptv: lista surselor si setarile; parola Xtream numai ca scrisa / nescrisa."""
	I = _iptv(I)
	c = _configIptv(I, config)
	rez = {"result": True, "surse": [{"tip": tip, "nume": nume, "date": date, "text": I.randSursa((tip, nume, date))}
		for tip, nume, date in I.incarcaSurse(cale)],
		"tip_sursa": str(c.tip_sursa.value), "tipuri": _alegeri(c.tip_sursa),
		"xtream_parola_scrisa": bool(c.xtream_parola.value)}
	for cheie in CAMPURI_IPTV:
		rez[cheie] = str(getattr(c, cheie).value)
	return rez


def _valoareIptv(I, cheie, text):
	"""Textul bun pentru `cheie` sau None: aceeasi verificare ca pe televizor (HdsIptvSurse.valoareBuna)."""
	return I.valoareBuna(cheie, text)


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_), fara efect: numele campurilor se traduc la folosire."""
	return text


# aceleasi nume ca randurile de pe televizor (Components/HdsIptvSurse.NUME_CAMPURI; fisierul nu importa Components la
# incarcare, deci lista e scrisa si aici, iar probele le compara)
NUME_CAMPURI_IPTV = {
	"tip_sursa": N_("Tipul sursei"), "m3u_cale": N_("Playlist M3U/M3U8"), "stalker_portal": N_("Portal Stalker"),
	"stalker_mac": N_("Adresa MAC"), "xtream_server": N_("Server Xtream"), "xtream_port": N_("Port Xtream"),
	"xtream_user": N_("Utilizator Xtream"), "xtream_parola": N_("Parola Xtream"),
}


def seteazaIptv(arg, din_adresa=(), I=None, config=None, configfile=None, cale=None):
	"""POST /api/iptv-seteaza. Toate valorile trebuie sa fie bune, altfel nu se schimba nimic. Parola se ia numai din
	corp (`din_adresa` = cheile scrise in adresa); un camp gol de parola nu o schimba, sterge=xtream_parola o sterge."""
	I = _iptv(I)
	c = _configIptv(I, config)
	noi = []
	if "tip_sursa" in arg:
		v = arg["tip_sursa"]
		if v not in [a[0] for a in _alegeri(c.tip_sursa)]:
			return _cuMesaj(stareIptv(I, config, cale), False, _t("Tipul sursei ales nu există."))
		noi.append((c.tip_sursa, v))
	for cheie in CAMPURI_IPTV:
		if cheie in arg:
			v = _valoareIptv(I, cheie, arg[cheie])
			if v is None:
				return _cuMesaj(stareIptv(I, config, cale), False,
					_t("Valoarea nu e bună pentru %s.") % _t(NUME_CAMPURI_IPTV[cheie]))
			noi.append((getattr(c, cheie), v))
	for cheie in SECRETE_IPTV:
		if cheie in arg and cheie not in din_adresa and arg[cheie]:
			v = _valoareIptv(I, cheie, arg[cheie])
			if v is None:
				return _cuMesaj(stareIptv(I, config, cale), False,
					_t("Valoarea nu e bună pentru %s.") % _t(NUME_CAMPURI_IPTV[cheie]))
			noi.append((getattr(c, cheie), v))
	if arg.get("sterge") in SECRETE_IPTV:
		noi.append((getattr(c, arg["sterge"]), ""))
	elif arg.get("sterge"):
		return _cuMesaj(stareIptv(I, config, cale), False, _t("Nu s-a trimis nicio setare."))
	if not noi:
		return _cuMesaj(stareIptv(I, config, cale), False, _t("Nu s-a trimis nicio setare."))
	for el, v in noi:
		if el.value != v:
			el.value = v
		el.save()
	_M().salveazaSetari(configfile)
	return _cuMesaj(stareIptv(I, config, cale), True, _t("Salvat."))


def adaugaIptv(arg, I=None, config=None, configfile=None, cale=None):
	"""POST /api/iptv-adauga: Galben pe televizor (Adauga sursa M3U), din config.hds_iptv.m3u_cale; m3u_cale= in aceeasi
	cerere o scrie intai."""
	I = _iptv(I)
	c = _configIptv(I, config)
	if "m3u_cale" in arg:
		v = _valoareIptv(I, "m3u_cale", arg["m3u_cale"])
		if v is None:
			return _cuMesaj(stareIptv(I, config, cale), False, _t("Valoarea nu e bună pentru %s.") % _t(NUME_CAMPURI_IPTV["m3u_cale"]))
		if c.m3u_cale.value != v:
			c.m3u_cale.value = v
		c.m3u_cale.save()
		_M().salveazaSetari(configfile)
	surse = I.incarcaSurse(cale)
	if I.adaugaM3U(surse, c.m3u_cale.value) is None:
		return _cuMesaj(stareIptv(I, config, cale), False, _t("Scrie întâi calea sau adresa listei M3U."))
	if not I.salveazaSurse(surse, cale):
		return _cuMesaj(stareIptv(I, config, cale), False, _t("Setările nu s-au putut salva."))
	return _cuMesaj(stareIptv(I, config, cale), True, _t("Sursa M3U a fost adăugată."))


def stergeIptv(arg, I=None, config=None, cale=None):
	"""POST /api/iptv-sterge?index=N: o sursa scoasa, in doi pasi (tinta = randul ei din fisier)."""
	I = _iptv(I)
	surse = I.incarcaSurse(cale)
	i = _index(arg.get("index", ""))
	if not 0 <= i < len(surse):
		return _cuMesaj(stareIptv(I, config, cale), False, _t("Sursa aleasă nu mai e în listă. Pagina se încarcă din nou."))
	sursa = surse[i]

	def fapta():
		I.stergeSursa(surse, i)
		if not I.salveazaSurse(surse, cale):
			return _cuMesaj(stareIptv(I, config, cale), False, _t("Setările nu s-au putut salva."))
		return _cuMesaj(stareIptv(I, config, cale), True, _t("Sursa a fost ștearsă."))

	return _doiPasi(arg, "iptv-sterge", "|".join(sursa), _t("Ștergi sursa IPTV?"), _t("Da, șterge"),
		[I.randSursa(sursa)], fapta)


# ================================================================== interfata web (HdsWebControlSetup)
PORT_MIN = 80
PORT_MAX = 65535


def _plugin(P=None):
	if P is not None:
		return P
	from . import plugin
	return plugin


def _cfgWeb(P):
	P.initConfigHdsWebControl()
	return P.config.plugins.hdswebcontrol


def cheieNoua(config=None, configfile=None):
	"""Cheie noua pentru scripturi (config.plugins.hdswebcontrol.token), salvata pe disc: aceeasi pentru ecranul de pe
	televizor (Albastru > Alte optiuni > Cheie noua pentru scripturi) si pentru pagina web."""
	import secrets
	if config is None:
		from Components.config import config
	if configfile is None:
		from Components.config import configfile
	config.plugins.hdswebcontrol.token.value = secrets.token_urlsafe(24)
	config.plugins.hdswebcontrol.token.save()
	configfile.save()


def cheieNouaPanou(config=None, configfile=None, asociere=None, pastreaza=None):
	"""Tasta Cheie noua pentru panoul web, aceeasi pe televizor (Albastru > Alte optiuni) si in web (/interfata-web): cheie
	noua (cheieNoua: secrets, salvata pe disc; cheia veche e refuzata la cererea urmatoare, fiindca poarta citeste
	setarea la fiecare cerere) si toate aparatele asociate deconectate, fiindca cine avea cheia veche putea cere capturi
	de ecran, deci putea citi codul de asociere si asocia un aparat. `pastreaza`: secretul browserului care a cerut
	schimbarea din web (ramane conectat). Cheia nu se scrie nicaieri in afara setarii. Intoarce cate aparate au fost
	deconectate."""
	cheieNoua(config, configfile)
	if asociere is None:
		return 0
	return asociere.deconecteazaToate(pastreaza=pastreaza)


def inceputCheie(cheie):
	"""Numai primele 4 caractere ale cheii: cheia intreaga nu pleaca spre browser."""
	return (cheie[:4] + "...") if len(cheie) > 4 else "..."


def _browsere(P):
	try:
		lista = P.obtineAsociere().listaBrowsere()
	except Exception as eroare:
		_jurnal("lista browserelor: %s" % eroare)
		lista = []
	# numai ce arata si televizorul; nimic din secretul sau amprenta lor
	return [{"nume": str(b.get("nume", "")), "tip": str(b.get("tip", "")), "adresa": str(b.get("adresa", "")),
		"creat": int(b.get("creat", 0) or 0)} for b in lista]


def _adresaPePort(adresa, port):
	"""Adresa interfetei pe alt port: 'http://10.0.0.20' -> 'http://10.0.0.20:8081'."""
	if not adresa:
		return ""
	gazda = adresa.split("://", 1)[-1].split("/", 1)[0]
	if gazda.startswith("["):
		gazda = gazda[:gazda.find("]") + 1]
	else:
		gazda = gazda.split(":", 1)[0]
	return "http://%s" % gazda if port == 80 else "http://%s:%d" % (gazda, port)


def _drumText(id_intrare):
	try:
		from .meniu_web import drumText
		return drumText(id_intrare)
	except Exception:
		return "Meniu"


def stareInterfataWeb(P=None):
	"""GET /api/interfata-web-detalii: ce arata ecranul de pe televizor, in afara randurilor din /api/interfata-web."""
	P = _plugin(P)
	c = _cfgWeb(P)
	return {"result": True, "activ": bool(c.activ.value), "port": int(c.port.value), "port_folosit": int(P.portFolosit()),
		"adresa": P.adresaWeb() or "", "port_min": PORT_MIN, "port_max": PORT_MAX, "browsere": _browsere(P)}


def _salveazaElement(el, valoare, configfile=None):
	if el.value != valoare:
		el.value = valoare
	el.save()
	_M().salveazaSetari(configfile)


def actiuneInterfataWeb(arg, P=None, configfile=None, adresa_client="", secret_cerere=None):
	"""POST /api/interfata-web-actiune. Oprirea, portul nou, deconectarea, cheia noua si codul nou: in doi pasi.
	`secret_cerere`: secretul browserului asociat care a trimis cererea (la cheia noua ramane conectat)."""
	P = _plugin(P)
	c = _cfgWeb(P)
	fapta = arg.get("fapta", "")
	if fapta == "activ":
		v = _bool(arg.get("valoare", ""))
		if v is None:
			return _cuMesaj(stareInterfataWeb(P), False, _t("Se alege cu valoare=0 sau 1."))
		if v:
			_salveazaElement(c.activ, True, configfile)
			return _cuMesaj(stareInterfataWeb(P), True, _t("Salvat. Activarea și portul se aplică după repornirea interfeței."))

		def opreste():
			_salveazaElement(c.activ, False, configfile)
			_jurnal("interfata web oprita din web (de la repornirea interfetei)")
			return _cuMesaj(stareInterfataWeb(P), True, _t("Salvat. După repornirea interfeței, interfața web nu mai pornește."))

		return _doiPasi(arg, "web-opreste", "", _t("Oprești interfața web?"), _t("Da, oprește interfața web"),
			[_t("După repornirea interfeței, paginile web și aplicațiile de telefon nu mai răspund. O pornești din nou "
				"numai de pe televizor, din %s.") % _drumText("hds_webcontrol_setup")], opreste)
	if fapta == "port":
		text = arg.get("valoare", "")
		if not text.isdigit() or len(text) > 5 or not PORT_MIN <= int(text) <= PORT_MAX:
			return _cuMesaj(stareInterfataWeb(P), False, _t("Portul trebuie să fie un număr între %d și %d.") % (PORT_MIN, PORT_MAX))
		port = int(text)
		if port == int(c.port.value):
			return _cuMesaj(stareInterfataWeb(P), True, _t("Nu s-a schimbat nimic."))

		def muta():
			_salveazaElement(c.port, port, configfile)
			_jurnal("portul interfetei web: %d (din web, de la repornirea interfetei)" % port)
			return _cuMesaj(stareInterfataWeb(P), True, _t("Salvat. Activarea și portul se aplică după repornirea interfeței."))

		adresa_noua = _adresaPePort(P.adresaWeb() or "", port)
		return _doiPasi(arg, "web-port", str(port), _t("Muți interfața web pe portul %d?") % port, _t("Da, schimbă portul"),
			[_t("După repornirea interfeței, pagina se deschide la adresa nouă: %s. Adresa de acum nu mai răspunde.")
				% (adresa_noua or _t("adresa receptorului"))], muta)
	if fapta == "deconecteaza":
		are_aplicatii = any(b["tip"] == "aplicatie" for b in _browsere(P))
		if are_aplicatii:
			intrebare = _t("Deconectezi toate browserele și telefoanele? Fiecare va avea nevoie din nou de un cod de pe televizor.")
		else:
			intrebare = _t("Deconectezi toate browserele? Fiecare va avea nevoie din nou de un cod de pe televizor.")

		def deconecteaza():
			numar = P.obtineAsociere().deconecteazaToate()
			_jurnal("browsere deconectate din web: %d" % numar)
			return _cuMesaj(stareInterfataWeb(P), True, _t("Deconectate: %d.") % numar)

		return _doiPasi(arg, "web-deconecteaza", "", intrebare, _t("Da, deconectează"),
			[_t("Dacă acest browser e conectat cu cod, și el va cere codul din nou.")], deconecteaza)
	if fapta == "cheie":
		def cheie():
			numar = cheieNouaPanou(P.config, configfile, P.obtineAsociere(), secret_cerere)
			_jurnal("cheie noua pentru panoul web, din web; aparate deconectate: %d" % numar)
			# pagina se incarca din nou: browserul intrat fara cod primeste tokenul CSRF facut din cheia noua; cel asociat
			# isi pastreaza cookie-ul
			rez = _cuMesaj(stareInterfataWeb(P), True, _t("Cheia nouă pentru panoul web e făcută. Pagina se încarcă din nou."))
			rez["reincarca"] = True
			return rez

		return _doiPasi(arg, "web-cheie", "", _t("Faci o cheie nouă pentru panoul web? Cheia veche nu mai merge, iar toate "
			"telefoanele și browserele asociate vor trebui asociate din nou."), _t("Da, fă cheia nouă"),
			[_t("Acest browser rămâne conectat. Scripturile care folosesc cheia veche nu mai merg până primesc cheia nouă."),
				_t("Browserele intrate fără cod din rețeaua locală, și această pagină dacă ai intrat fără cod, trebuie să "
				"încarce din nou pagina după schimbare.")], cheie)
	if fapta == "browser_nou":
		def cod():
			asociere = P.obtineAsociere()
			asociere.deblocheaza()
			r = asociere.cereCod(tip=P.TIP_BROWSER, adresa=adresa_client)
			if not r.get("cod"):
				return _cuMesaj(stareInterfataWeb(P), False, _t("Codul nu a putut fi făcut acum. Încearcă din nou peste un minut."))
			P._arataCodPeTelevizor(r["cod"], r["ramas"], P.TIP_BROWSER, r.get("adresa", ""), r.get("id_cerere"))
			_jurnal("cod nou pentru un browser cerut din web, de la %s" % (adresa_client or "?"))
			return _cuMesaj(stareInterfataWeb(P), True, _t("Codul e pe televizor. Deschide adresa receptorului în browserul nou "
				"și scrie codul."))

		return _doiPasi(arg, "web-browser-nou", "", _t("Arăți pe televizor un cod nou pentru un browser?"), _t("Da, arată codul"),
			[_t("Codul apare numai pe televizor. Ca pe televizor, asta scoate și pauza de după codurile greșite.")], cod)
	return _cuMesaj(stareInterfataWeb(P), False, _t("Acțiunea cerută nu există."))


# ================================================================== resursele
def _argumente(request, chei, lung=MAX_TEXT):
	return _M().argumente(request, chei, lung)


def _dinAdresa(request):
	from .descarcare_subtitrari_web import _cheiDinAdresa
	return _cheiDinAdresa(request)


def _adresaClient(request):
	try:
		from . import plugin as P
		return P._adresaClient(request) or ""
	except Exception:
		return ""


def rute(baza, resource, D=None, S=None, I=None, P=None, config=None, configfile=None, cale_dvbi=None,
		cale_mabr=None, cale_iptv=None):
	"""({nume: resursa de sub /api}, {nume: resursa pagina}). `baza` e HdsJsonResource din plugin.py; restul sunt
	pentru probele de pe PC."""

	def _citire(functie):
		class Citire(baza):
			def render_GET(self, request):
				try:
					return self._raspunde(request, functie(request))
				except Exception as eroare:
					_jurnal("%s: %r" % (functie.__name__, eroare))
					return self._eroare(request, _t("Eroare pe receptor."), 500)
		return Citire()

	def _schimbare(functie, doi_pasi=False):
		class Schimbare(baza):
			schimbaCeva = True

			def render_POST(self, request):
				if doi_pasi:
					refuz = _M().numaiBrowser(request)
					if refuz:
						return self._raspunde(request, {"result": False, "message": refuz}, 403)
				try:
					return self._raspunde(request, functie(request))
				except Exception as eroare:
					_jurnal("%s: %r" % (functie.__name__, eroare))
					return self._eroare(request, _t("Eroare pe receptor."), 500)

			def render_GET(self, request):
				return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST
		return Schimbare()

	CHEI_PASI = ("pas", "cod", "index")

	def dvbi(request):
		return stareDvbi(D, cale_dvbi)

	def dvbi_seteaza(request):
		return seteazaDvbi(_argumente(request, ("activ", "predefinita", "bifata", "adauga_url", "tara", "regiune", "lista",
			"rezerva"), 1024), D, cale_dvbi)

	def dvbi_incearca(request):
		return incearcaDvbi(D, cale_dvbi)

	def dvbi_registre(request):
		return registreDvbi(D, cale_dvbi)

	def dvbi_sterge(request):
		return stergeDvbi(_argumente(request, CHEI_PASI), D, cale_dvbi)

	def dvbi_reincarca(request):
		return reincarcaDvbi(D, cale_dvbi)

	def mabr(request):
		return stareMabr(S, cale_mabr)

	def mabr_seteaza(request):
		return seteazaMabr(_argumente(request, ("activ", "autodiscover", "adauga"), 64), S, cale_mabr)

	def mabr_sterge(request):
		return stergeMabr(_argumente(request, CHEI_PASI), S, cale_mabr)

	def mabr_cauta(request):
		return cautaMabr(S, cale_mabr)

	def iptv(request):
		return stareIptv(I, config, cale_iptv)

	def iptv_seteaza(request):
		chei = ("tip_sursa", "sterge") + CAMPURI_IPTV + SECRETE_IPTV
		return seteazaIptv(_argumente(request, chei), _dinAdresa(request), I, config, configfile, cale_iptv)

	def iptv_adauga(request):
		return adaugaIptv(_argumente(request, ("m3u_cale",)), I, config, configfile, cale_iptv)

	def iptv_sterge(request):
		return stergeIptv(_argumente(request, CHEI_PASI), I, config, cale_iptv)

	def interfata_web(request):
		return stareInterfataWeb(P)

	def interfata_web_actiune(request):
		# browserul asociat care cere (cookie-ul lui), nu cel intrat fara cod: numai el are o intrare de pastrat
		sesiune = getattr(_plugin(P), "_sesiuneDinCerere", None)
		secret, browser = sesiune(request) if sesiune is not None else (None, None)
		if browser is None or browser.get("liber"):
			secret = None
		return actiuneInterfataWeb(_argumente(request, ("fapta", "valoare") + CHEI_PASI, 16), P, configfile,
			_adresaClient(request), secret)

	api = {
		b"dvb-i": _citire(dvbi),
		b"dvb-i-seteaza": _schimbare(dvbi_seteaza),
		b"dvb-i-sterge": _schimbare(dvbi_sterge, True),
		b"dvb-i-reincarca": _schimbare(dvbi_reincarca),
		b"dvb-i-incearca": _schimbare(dvbi_incearca),
		b"dvb-i-registre": _schimbare(dvbi_registre),
		b"mabr": _citire(mabr),
		b"mabr-seteaza": _schimbare(mabr_seteaza),
		b"mabr-sterge": _schimbare(mabr_sterge, True),
		b"mabr-cauta": _schimbare(mabr_cauta),
		b"iptv": _citire(iptv),
		b"iptv-seteaza": _schimbare(iptv_seteaza),
		b"iptv-adauga": _schimbare(iptv_adauga),
		b"iptv-sterge": _schimbare(iptv_sterge, True),
		b"interfata-web-detalii": _citire(interfata_web),
		b"interfata-web-actiune": _schimbare(interfata_web_actiune, True),
	}

	def _pagina(sablon, cu_csrf=True):
		class Pagina(resource.Resource):
			isLeaf = True

			def render_GET(self, request):
				return _M().pagina(request, sablon, cu_csrf)
		return Pagina()

	pagini = {
		b"dvb-i": _pagina(pagina_dvbi),
		b"dvb-i-priveste": _pagina(pagina_dvbi_priveste, False),
		b"mabr": _pagina(pagina_mabr),
		b"iptv": _pagina(pagina_iptv),
		b"interfata-web": _pagina(pagina_interfata_web),
	}
	return api, pagini


# ================================================================== paginile
def _sablon(text, stil, config_pagina, id_intrare):
	M = _M()
	return M.sablon(text, stil, config_pagina, {"__DRUM_MENIU__": M.drumHtml(id_intrare)})


def pagina_dvbi(stil, config_pagina):
	return _sablon(_traducePagina(PAGINA_DVBI), stil, config_pagina, "dvbi_setup")


def pagina_dvbi_priveste(stil, config_pagina):
	return _sablon(_traducePagina(PAGINA_DVBI_PRIVESTE), stil, config_pagina, "dvbi_setup")


def pagina_mabr(stil, config_pagina):
	return _sablon(_traducePagina(PAGINA_MABR), stil, config_pagina, "mabr_config")


def pagina_iptv(stil, config_pagina):
	return _sablon(_traducePagina(PAGINA_IPTV), stil, config_pagina, "hds_iptv_setup")


def pagina_interfata_web(stil, config_pagina):
	return _sablon(_traducePagina(PAGINA_INTERFATA_WEB), stil, config_pagina, "hds_webcontrol_setup")


# Paginile se lipesc din bucati constante (cu +, nu cu functii), ca probele care cauta toate sabloanele de pagini sa le
# gaseasca (teste/web_meniu_teme_comun.pagini_html).
_CAP = """
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>"""

_STIL = """</title>
<style>__STIL_COMUN__
__STIL_PAGINI__
  .lista-rand{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid var(--bordura);}
  .lista-rand:last-child{border-bottom:0;}
  .lista-rand>span{overflow-wrap:anywhere;min-width:0;}
  .lista-rand button{flex:0 0 auto;}
  .bifa{display:flex;align-items:center;gap:12px;min-height:44px;padding:4px 0;border-bottom:1px solid var(--bordura);cursor:pointer;}
  .bifa:last-child{border-bottom:0;}
  .bifa span{overflow-wrap:anywhere;}
  .rand input[type=text],.rand input[type=url],.rand input[type=password],.rand input[type=number]{width:100%;}
  a.extern{overflow-wrap:anywhere;}
  .dvbi-grila{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:12px;margin:0 0 12px;}
  .dvbi-grila .card{margin:0;}
  .dvbi-stare{font-size:1.05rem;font-weight:bold;margin:0 0 4px;}
  .dvbi-stare::before{content:"";display:inline-block;width:.6em;height:.6em;border-radius:50%;background:currentColor;margin-right:8px;vertical-align:.1em;}
  .dvbi-stare.bun{color:var(--bine);} .dvbi-stare.chihlimbar{color:var(--chihlimbar);} .dvbi-stare.rau{color:var(--eroare);} .dvbi-stare.slab{color:var(--text-slab);}
  .dvbi-insigna{display:inline-block;border-radius:999px;padding:2px 10px;font-size:.82rem;border:1px solid currentColor;white-space:nowrap;margin:2px 6px 2px 0;}
  .dvbi-insigna.bine{color:var(--bine);} .dvbi-insigna.chihlimbar{color:var(--chihlimbar);} .dvbi-insigna.rau{color:var(--eroare);}
  .dvbi-insigna.slab{color:var(--text-slab);} .dvbi-insigna.gol{border-style:dashed;} .dvbi-insigna.albastru{color:var(--accent);}
  .bifa .dvbi-insigna{margin-left:auto;}
  .dvbi-lista{display:flex;flex-direction:column;min-width:0;flex:1;} .dvbi-lista small{color:var(--text-slab);}
  .dvbi-rezumat{margin:0 0 8px;}
  .dvbi-canal{display:grid;grid-template-columns:3em minmax(0,1fr) auto auto auto;gap:10px;align-items:center;padding:8px 0;border-bottom:1px solid var(--bordura);}
  .dvbi-canal:last-child{border-bottom:0;}
  .dvbi-nr{color:var(--text-slab);text-align:right;}
  .dvbi-nume{font-weight:bold;overflow-wrap:anywhere;}
  .dvbi-priveste{display:inline-flex;align-items:center;justify-content:center;min-height:44px;padding:0 14px;border-radius:8px;border:1px solid var(--bordura);color:var(--text);text-decoration:none;}
  .dvbi-video{width:100%;max-height:70vh;background:#000;border-radius:8px;margin:8px 0;}
  .dvbi-vpn{border-left:4px solid var(--chihlimbar);border-radius:6px;padding:10px 12px;margin-top:12px;background:var(--panou-2);}
  details.card summary{cursor:pointer;min-height:44px;} details.card summary h2{display:inline;}
  .dvbi-probe summary{cursor:pointer;min-height:44px;display:flex;align-items:center;color:var(--text-slab);}
  @media (max-width:640px){ .dvbi-canal{grid-template-columns:2.5em minmax(0,1fr);} .dvbi-sat,.dvbi-st{grid-column:2;} .dvbi-priveste{grid-column:1 / -1;} }
</style>
</head>
<body>
<main>
"""

_COADA = """<p class="mesaj" id="mesaj"></p>
<div id="confirmare" class="card ascuns"></div>
</main>
<script>
__SCRIPT_COMUN__
function rand(text, buton, laClic){
  var d = document.createElement("div"); d.className = "lista-rand";
  var s = document.createElement("span"); s.textContent = text; d.appendChild(s);
  if(buton){ var b = document.createElement("button"); b.type = "button"; b.textContent = buton; b.addEventListener("click", laClic); d.appendChild(b); }
  return d;
}
function gol(text){ var p = document.createElement("p"); p.className = "nota"; p.textContent = text; return p; }
function pune(id, copii){ var c = $(id); c.textContent = ""; copii.forEach(function(x){ c.appendChild(x); }); }
function arataPagina(){ $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns"); }
function faraRaspuns(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; }
"""

_SFARSIT = """
</script>
</body>
</html>
"""


PAGINA_DVBI = "<!DOCTYPE html>" + _CAP + "DVB-I: Configurare" + _STIL + """<h1>Canale de pe internet (DVB-I)</h1>
<p class="mesaj" id="incarcare">Se citesc setările...</p>
<div id="continut" class="ascuns">
  <p class="dvbi-stare" id="stareMare"></p>
  <p class="nota" id="detalii"></p>
  <div class="dvbi-grila">
    <section class="card">
      <h2>Țara și regiunea</h2>
      <div class="rand"><label for="tara">Țara</label><select id="tara"></select></div>
      <div class="rand" id="randRegiune"><label for="regiune">Regiunea</label><select id="regiune"></select></div>
      <p class="nota" id="taraNota">Țările vin din registrele DVB-I; listele țării se iau singure și se actualizează din oră în oră.</p>
      <p class="nota eroare ascuns" id="registreMesaj"></p>
      <div class="butoane"><button type="button" id="registre">Întreabă din nou registrele</button></div>
    </section>
    <section class="card">
      <h2>Trecere pe internet</h2>
      <div class="rand"><label for="rezerva">Trecere singură pe internet când satelitul nu se recepționează</label>
        <select id="rezerva"><option value="1">Da</option><option value="0">Nu</option></select></div>
      <p class="nota">Canalul de satelit care are și adresă de internet în listele DVB-I trece singur pe internet când satelitul nu se recepționează și se întoarce pe satelit când semnalul revine.</p>
    </section>
    <section class="card" id="cardListe">
      <h2>Listele țării</h2>
      <div id="listeTarii"></div>
      <p class="nota">Listele adevărate ale țării sunt bifate singure; cele de probă ale registrelor le bifezi numai dacă vrei să le încerci.</p>
    </section>
    <section class="card" id="cardReincarcare">
      <h2>Reîncărcare</h2>
      <p class="intrebare" id="reincarcareText"></p>
      <div class="butoane"><button type="button" class="principal" id="reincarca">Reîncarcă acum</button></div>
      <p class="nota">Descarcă acum listele alese; canalele apar în lista de canale, în buchetul Canale de pe internet (DVB-I).</p>
    </section>
  </div>
  <section class="card">
    <h2>Canalele</h2>
    <p class="dvbi-rezumat" id="rezumat"></p>
    <div class="butoane"><button type="button" id="incearca">Încearcă din nou</button></div>
    <div class="dvbi-tabel" id="canale"></div>
    <div class="dvbi-vpn ascuns" id="notaVpn"><span id="notaVpnText"></span> <a href="/vpn" id="legaturaVpn">Setări VPN</a></div>
  </section>
  <details class="card" id="avansat">
    <summary><h2>Adrese puse de mână și liste predefinite (avansat)</h2></summary>
    <div class="status-linie"><span>Acum</span><span id="stare"></span></div>
    <div class="rand"><label for="activ">DVB-I activ</label>
      <select id="activ"><option value="1">Da</option><option value="0">Nu</option></select></div>
    <h3>Liste predefinite</h3>
    <div id="predefinite"></div>
    <p class="nota">Bifa pornește sau oprește o listă, ca OK pe televizor.</p>
    <h3>Adrese proprii</h3>
    <div id="adrese"></div>
    <div class="rand"><label for="url">Adresă nouă (http:// sau https://)</label>
      <input type="url" id="url" maxlength="1024" placeholder="https://" autocomplete="off"></div>
    <div class="butoane"><button type="button" id="adauga">Adaugă adresa</button></div>
  </details>
  <p class="nota">Aceleași setări sunt pe televizor, în __DRUM_MENIU__.</p>
</div>
""" + _COADA + """var DATE = "", PORNIT_SINGUR = false, CEAS = null;
var STARI = {"merge": ["Merge", "bine"], "oprit_tara": ["Oprit pentru țara ta", "chihlimbar"],
  "adresa_moarta": ["Adresă moartă", "rau"], "nu_raspunde": ["Nu răspunde", "slab"], "": ["Neîncercat", "slab gol"]};
function insigna(text, fel){ var s = document.createElement("span"); s.className = "dvbi-insigna " + fel; s.textContent = text; return s; }
function optiuni(sel, lista, ales){
  if(document.activeElement === sel){ return; }
  sel.textContent = "";
  lista.forEach(function(o){ var x = document.createElement("option"); x.value = o[0]; x.textContent = o[1]; sel.appendChild(x); });
  sel.value = ales;
}
function arataTara(d){
  var tari = [["", "Nicio țară (numai adresele puse de mână)"]].concat((d.tari || []).map(function(t){
    return [t.cod, t.nume + (t.reale ? " · liste: " + t.reale : " · numai liste de probă")];
  }));
  if(d.tara && !(d.tari || []).some(function(t){ return t.cod === d.tara; })){ tari.push([d.tara, d.tara_nume || d.tara]); }
  optiuni($("tara"), tari, d.tara || "");
  var reg = d.regiuni || [];
  $("randRegiune").classList.toggle("ascuns", !d.tara || !reg.length);
  optiuni($("regiune"), [["", "toată țara"]].concat(reg.map(function(r){
    return [r.id, new Array(r.nivel * 3 + 1).join(String.fromCharCode(160)) + r.nume];
  })), d.regiune || "");
  var r = d.registre || {};
  $("registre").disabled = !!r.in_curs;
  $("taraNota").textContent = r.in_curs ? "Se întreabă registrele DVB-I..." : "Țările vin din registrele DVB-I; listele țării se iau singure și se actualizează din oră în oră.";
  $("registreMesaj").textContent = r.in_curs ? "" : (r.mesaj || "");
  $("registreMesaj").classList.toggle("ascuns", !!r.in_curs || !r.mesaj);
}
function arataListe(d){
  $("cardListe").classList.toggle("ascuns", !d.tara);
  var bifa = function(x){
    var e = document.createElement("label"); e.className = "bifa";
    var c = document.createElement("input"); c.type = "checkbox"; c.checked = !!x.aleasa;
    c.addEventListener("change", function(){ var q = new URLSearchParams(); q.set("lista", x.adresa); q.set("bifata", c.checked ? "1" : "0"); trimite("/api/dvb-i-seteaza", q); });
    var s = document.createElement("span"); s.className = "dvbi-lista";
    var n = document.createElement("b"); n.textContent = x.lista || x.adresa; s.appendChild(n);
    var f = document.createElement("small"); f.textContent = "Furnizor: " + (x.furnizor || "?") + (x.proba ? " · listă de probă" : ""); s.appendChild(f);
    e.appendChild(c); e.appendChild(s);
    if(x.canale !== null && x.canale !== undefined){ e.appendChild(insigna("canale: " + x.canale, "slab")); }
    return e;
  };
  var toate = d.liste_tarii || [];
  var l = toate.filter(function(x){ return !x.proba; }).map(bifa);
  var p = toate.filter(function(x){ return x.proba; });
  if(p.length){
    // listele de proba ale registrelor (multe la unele tari) stau stranse; deschise singure daca una e bifata
    var det = document.createElement("details"); det.className = "dvbi-probe";
    det.open = p.some(function(x){ return x.aleasa; });
    var s = document.createElement("summary"); s.textContent = "Liste de probă ale registrelor: " + p.length; det.appendChild(s);
    p.map(bifa).forEach(function(x){ det.appendChild(x); });
    l.push(det);
  }
  pune("listeTarii", l.length ? l : [gol("Țara aleasă nu are liste în registre.")]);
}
function arataCanale(d){
  var n = d.rezumat || {}, c = d.canale || [], p = [];
  if(d.incercare && d.incercare.in_curs){ p.push(insigna("Se încearcă: " + d.incercare.facute + " din " + d.incercare.total, "chihlimbar")); }
  [["merge", "merg"], ["oprit_tara", "oprite pentru țara ta"], ["adresa_moarta", "adrese moarte"], ["nu_raspunde", "fără răspuns"], ["", "neîncercate"]].forEach(function(k){
    if(n[k[0]]){ p.push(insigna(n[k[0]] + " " + k[1], STARI[k[0]][1])); }
  });
  pune("rezumat", p.length ? p : [gol(c.length ? "" : "Niciun canal încă. Alege țara sau o listă, apoi Reîncarcă acum.")]);
  $("incearca").disabled = !c.length || !!(d.incercare && d.incercare.in_curs);
  var rand = function(x){
    var r = document.createElement("div"); r.className = "dvbi-canal";
    var nr = document.createElement("span"); nr.className = "dvbi-nr"; nr.textContent = String(x.lcn || x.nr || ""); r.appendChild(nr);
    var nm = document.createElement("span"); nm.className = "dvbi-nume"; nm.textContent = x.nume + (x.tip === "radio" ? " (radio)" : ""); r.appendChild(nm);
    var sat = document.createElement("span"); sat.className = "dvbi-sat";
    if(x.sat){ sat.appendChild(insigna("și pe satelit", "albastru")); }
    r.appendChild(sat);
    var st = STARI[x.stare] || STARI[""];
    var stare = document.createElement("span"); stare.className = "dvbi-st"; stare.appendChild(insigna(st[0] + (x.cod && x.stare !== "merge" ? " (" + x.cod + ")" : ""), st[1])); r.appendChild(stare);
    var b = document.createElement("a"); b.className = "dvbi-priveste"; b.textContent = "Privește"; b.target = "_blank"; b.rel = "noopener";
    b.href = adresa("/dvb-i-priveste?id=" + encodeURIComponent(String(x.id))); r.appendChild(b);
    return r;
  };
  pune("canale", c.map(rand));
  var oprite = n.oprit_tara || 0, v = d.vpn || {};
  $("notaVpn").classList.toggle("ascuns", !oprite);
  var t = "Canalele oprite pentru țara ta se pot vedea cu VPN-ul receptorului pornit, cu o adresă din " + (d.tara_nume || "țara listei") + ". După pornirea VPN-ului, canalele se încearcă din nou singure.";
  if(v.conectat && v.mod === "navigator"){ t += " Acum VPN-ul duce numai navigatorul: la Ce trece prin VPN alege tot traficul."; }
  $("notaVpnText").textContent = t;
  $("legaturaVpn").classList.toggle("ascuns", !v.disponibil);
}
function arata(d){
  var s = d.stare || {};
  $("stareMare").textContent = s.text || d.text_stare || "";
  $("stareMare").className = "dvbi-stare " + (s.culoare || "slab");
  $("detalii").textContent = s.detalii || "";
  $("stare").textContent = d.text_stare || "";
  if(document.activeElement !== $("activ")){ $("activ").value = d.activ ? "1" : "0"; }
  if(document.activeElement !== $("rezerva")){ $("rezerva").value = d.rezerva === false ? "0" : "1"; }
  var r = d.reincarcare || {};
  $("reincarcareText").textContent = r.mesaj || "Listele se reîncarcă singure din oră în oră cât timp receptorul e pornit.";
  $("reincarcareText").classList.toggle("eroare", !!(r.gata && !r.succes));
  $("reincarca").disabled = !!r.in_curs;
  var lucreaza = !!(r.in_curs || (d.incercare && d.incercare.in_curs) || (d.registre && d.registre.in_curs));
  if(lucreaza && !CEAS){ CEAS = setInterval(citeste, 1500); }
  if(!lucreaza && CEAS){ clearInterval(CEAS); CEAS = null; }
  arataTara(d); arataCanale(d);
  var semn = JSON.stringify([d.activ, d.predefinite, d.url_uri, d.liste_tarii]);
  if(semn === DATE){ return; }
  DATE = semn;
  arataListe(d);
  pune("predefinite", (d.predefinite || []).map(function(p){
    var l = document.createElement("label"); l.className = "bifa";
    var c = document.createElement("input"); c.type = "checkbox"; c.checked = !!p.bifata;
    c.addEventListener("change", function(){ var q = new URLSearchParams(); q.set("predefinita", p.cheie); q.set("bifata", c.checked ? "1" : "0"); trimite("/api/dvb-i-seteaza", q); });
    var s = document.createElement("span"); s.textContent = p.descriere + (p.tara ? " (" + p.tara + ")" : "");
    l.appendChild(c); l.appendChild(s); return l;
  }));
  var a = (d.url_uri || []).map(function(u, i){
    return rand(u, "Șterge", function(){ var q = new URLSearchParams(); q.set("index", String(i)); cuConfirmare("/api/dvb-i-sterge", q, dupa); });
  });
  pune("adrese", a.length ? a : [gol("Nicio adresă proprie.")]);
}
function dupa(d){ if(d && d.predefinite){ arata(d); } }
function trimite(cale, q){
  mesaj("Se salvează...");
  return cerere(cale, "POST", q).then(function(d){ mesaj(d.message, !d.result); dupa(d); return d; }).catch(nimicNuRaspunde);
}
function citeste(){
  return cerere("/api/dvb-i").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi setările."; return; }
    arataPagina(); arata(d);
    if(!PORNIT_SINGUR && new URLSearchParams(location.search).get("f") === "reincarca"){
      PORNIT_SINGUR = true; $("cardReincarcare").scrollIntoView({block: "start"}); reincarca();
    }
  }).catch(faraRaspuns);
}
function reincarca(){ trimite("/api/dvb-i-reincarca", new URLSearchParams()); }
["activ", "rezerva", "tara", "regiune"].forEach(function(id){
  $(id).addEventListener("change", function(){ var q = new URLSearchParams(); q.set(id, $(id).value); trimite("/api/dvb-i-seteaza", q); });
});
$("reincarca").addEventListener("click", reincarca);
$("incearca").addEventListener("click", function(){ trimite("/api/dvb-i-incearca", new URLSearchParams()); });
$("registre").addEventListener("click", function(){ trimite("/api/dvb-i-registre", new URLSearchParams()); });
$("adauga").addEventListener("click", function(){
  var u = $("url").value.trim();
  if(!u){ mesaj("Scrie întâi adresa listei.", true); return; }
  var q = new URLSearchParams(); q.set("adauga_url", u);
  trimite("/api/dvb-i-seteaza", q).then(function(d){ if(d && d.result){ $("url").value = ""; } });
});
citeste();
setInterval(function(){ if(!CEAS){ citeste(); } }, 15000);""" + _SFARSIT


# "Priveste" din /dvb-i: fluxul canalului deschis in browser, direct de la televiziune (nu trece prin receptor). Browserul
# reda singur HLS (.m3u8) unde il stie (Safari, telefoanele) si fluxurile simple; DASH (.mpd) numai unde il stie: altfel
# pagina spune asta si da adresa, de deschis intr-un player. Fara biblioteci straine incarcate de pe internet.
PAGINA_DVBI_PRIVESTE = "<!DOCTYPE html>" + _CAP + "DVB-I: Privește" + _STIL + """<h1 id="titlu">Privește canalul</h1>
<p class="mesaj" id="incarcare">Se citește canalul...</p>
<div id="continut" class="ascuns">
  <section class="card">
    <p class="dvbi-rezumat" id="stareCanal"></p>
    <video id="video" class="dvbi-video" controls autoplay playsinline></video>
    <p class="nota eroare ascuns" id="nuMerge"></p>
    <div class="rand"><label for="adresaFlux">Adresa fluxului</label><input type="text" id="adresaFlux" readonly></div>
    <div class="butoane"><button type="button" id="copiaza">Copiază adresa</button>
      <a class="dvbi-priveste" id="deschide" target="_blank" rel="noopener noreferrer">Deschide adresa</a></div>
    <p class="nota">Fluxul vine direct de la televiziune, prin internetul acestui calculator sau telefon, nu prin receptor. Pe televizor canalul e în buchetul Canale de pe internet (DVB-I).</p>
  </section>
  <p class="nota"><a href="/dvb-i">Înapoi la canalele de pe internet</a>. Aceleași setări sunt pe televizor, în __DRUM_MENIU__.</p>
</div>
""" + _COADA + """var STARI = {"merge": "Merge din casa receptorului", "oprit_tara": "Oprit pentru țara receptorului",
  "adresa_moarta": "Adresa nu mai răspunde", "nu_raspunde": "Nu a răspuns la ultima încercare", "": "Neîncercat încă din casa receptorului"};
function nuMerge(text){ $("nuMerge").textContent = text; $("nuMerge").classList.remove("ascuns"); }
function arataCanal(c){
  document.title = c.nume + " · DVB-I";
  $("titlu").textContent = c.nume;
  $("stareCanal").textContent = (STARI[c.stare] || STARI[""]) + (c.cod && c.stare !== "merge" ? " (cod " + c.cod + ")" : "") + ".";
  $("adresaFlux").value = c.url;
  $("deschide").href = c.url;
  var v = $("video");
  var dash = /[.]mpd($|[?#])/i.test(c.url), hls = /[.]m3u8($|[?#])/i.test(c.url);
  var tip = dash ? "application/dash+xml" : (hls ? "application/vnd.apple.mpegurl" : "");
  if(tip && !v.canPlayType(tip)){
    v.classList.add("ascuns");
    nuMerge(dash ? "Browserul acesta nu redă singur fluxuri DASH (.mpd). Deschide adresa de mai jos într-un player care le redă, de pildă VLC (Media, Deschide flux din rețea)." :
      "Browserul acesta nu redă singur fluxuri HLS (.m3u8). Deschide adresa de mai jos într-un player care le redă, de pildă VLC (Media, Deschide flux din rețea).");
    return;
  }
  v.addEventListener("error", function(){
    nuMerge(c.stare === "oprit_tara" ? "Televiziunea nu dă fluxul în țara din care vine cererea. În browser fluxul trece prin internetul acestui calculator sau telefon: aici ar trebui pornit un VPN cu o adresă din țara canalului." :
      "Fluxul nu a pornit în browser. Adresa de mai jos se poate încerca într-un player, de pildă VLC.");
  });
  v.src = c.url;
  var p = v.play(); if(p && p.catch){ p.catch(function(){}); }
}
function citeste(){
  var id = new URLSearchParams(location.search).get("id");
  return cerere("/api/dvb-i").then(function(d){
    var c = (d.canale || []).filter(function(x){ return String(x.id) === id; })[0];
    if(!c){ $("incarcare").textContent = "Canalul nu mai e în listele DVB-I. Pagina canalelor are lista de acum."; return; }
    arataPagina(); arataCanal(c);
  }).catch(faraRaspuns);
}
$("copiaza").addEventListener("click", function(){
  var a = $("adresaFlux"); a.select();
  var gata = function(){ mesaj("Adresa e copiată."); };
  if(navigator.clipboard && navigator.clipboard.writeText){ navigator.clipboard.writeText(a.value).then(gata, function(){ document.execCommand("copy"); gata(); }); }
  else { document.execCommand("copy"); gata(); }
});
citeste();""" + _SFARSIT


PAGINA_MABR = "<!DOCTYPE html>" + _CAP + "DVB-MABR: IP Multicast" + _STIL + """<h1>DVB-MABR: Configurare IP Multicast</h1>
<p class="mesaj" id="incarcare">Se citesc setările...</p>
<div id="continut" class="ascuns">
  <section class="card">
    <h2>Stare</h2>
    <div class="status-linie"><span>Acum</span><span id="stare"></span></div>
    <div class="rand"><label for="activ">DVB-MABR activ</label>
      <select id="activ"><option value="1">Da</option><option value="0">Nu</option></select></div>
    <div class="rand"><label for="autodiscover">Autodiscover SAP/SD&amp;S</label>
      <select id="autodiscover"><option value="1">Da</option><option value="0">Nu</option></select></div>
  </section>
  <section class="card">
    <h2>Grupuri multicast manuale</h2>
    <div id="grupuri"></div>
    <div class="rand"><label for="grup">Grup nou (adresă:port, de exemplu 239.1.1.1:9000)</label>
      <input type="text" id="grup" maxlength="21" placeholder="239." autocomplete="off" inputmode="decimal"></div>
    <div class="butoane"><button type="button" id="adauga">Adaugă grupul</button></div>
  </section>
  <section class="card">
    <h2>Sesiuni descoperite live (SAP)</h2>
    <div id="sesiuni"></div>
    <div class="butoane"><button type="button" class="principal" id="cauta">Caută SAP</button></div>
  </section>
  <p class="nota">Intrarea e marcată în lucru și pe televizor: setările se salvează, dar nicio parte a receptorului nu le folosește încă. Aceleași setări sunt pe televizor, în __DRUM_MENIU__.</p>
</div>
""" + _COADA + """var DATE = "", CEAS = null;
function arata(d){
  $("stare").textContent = d.text_stare || "";
  if(document.activeElement !== $("activ")){ $("activ").value = d.activ ? "1" : "0"; }
  if(document.activeElement !== $("autodiscover")){ $("autodiscover").value = d.autodiscover ? "1" : "0"; }
  var c = d.cautare || {};
  var s = (c.sesiuni || []).map(function(x){ return rand("udp://@" + x.adresa + ":" + x.port + " · " + (x.nume || "fără nume")); });
  if(!s.length){ s = [gol(c.mesaj || "Apasă Caută SAP pentru a descoperi sesiuni MABR în rețea.")]; }
  pune("sesiuni", s);
  $("cauta").disabled = !!c.in_curs;
  if(c.in_curs && !CEAS){ CEAS = setInterval(citeste, 1500); }
  if(!c.in_curs && CEAS){ clearInterval(CEAS); CEAS = null; }
  var semn = JSON.stringify(d.grupuri);
  if(semn === DATE){ return; }
  DATE = semn;
  var g = (d.grupuri || []).map(function(x, i){
    return rand(x.text, "Șterge", function(){ var q = new URLSearchParams(); q.set("index", String(i)); cuConfirmare("/api/mabr-sterge", q, dupa); });
  });
  pune("grupuri", g.length ? g : [gol("Niciun grup adăugat de mână.")]);
}
function dupa(d){ if(d && d.grupuri){ arata(d); } }
function trimite(cale, q){
  mesaj("Se salvează...");
  return cerere(cale, "POST", q).then(function(d){ mesaj(d.message, !d.result); dupa(d); return d; }).catch(nimicNuRaspunde);
}
function citeste(){
  return cerere("/api/mabr").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi setările."; return; }
    arataPagina(); arata(d);
  }).catch(faraRaspuns);
}
["activ", "autodiscover"].forEach(function(id){
  $(id).addEventListener("change", function(){ var q = new URLSearchParams(); q.set(id, $(id).value); trimite("/api/mabr-seteaza", q); });
});
$("adauga").addEventListener("click", function(){
  var q = new URLSearchParams(); q.set("adauga", $("grup").value.trim());
  trimite("/api/mabr-seteaza", q).then(function(d){ if(d && d.result){ $("grup").value = ""; } });
});
$("cauta").addEventListener("click", function(){ trimite("/api/mabr-cauta", new URLSearchParams()); });
citeste();""" + _SFARSIT


PAGINA_IPTV = "<!DOCTYPE html>" + _CAP + "Televiziune prin IP (IPTV)" + _STIL + """<h1>Televiziune prin IP (IPTV)</h1>
<p class="mesaj" id="incarcare">Se citesc setările...</p>
<div id="continut" class="ascuns">
  <section class="card">
    <h2>Surse</h2>
    <div id="surse"></div>
  </section>
  <section class="card">
    <h2>Adaugă sursă M3U</h2>
    <div class="rand"><label for="m3u_cale">Playlist M3U/M3U8 (fișier local sau URL)</label>
      <input type="text" id="m3u_cale" maxlength="512" autocomplete="off" placeholder="/media/hdd/lista.m3u"></div>
    <div class="butoane"><button type="button" class="principal" id="adauga">Adaugă sursă M3U</button></div>
  </section>
  <section class="card">
    <h2>Date de acces</h2>
    <div class="rand"><label for="tip_sursa">Tipul sursei</label><select id="tip_sursa"></select></div>
    <div class="rand"><label for="stalker_portal">Portal Stalker/Ministra (adresa)</label>
      <input type="text" id="stalker_portal" maxlength="512" autocomplete="off"></div>
    <div class="rand"><label for="stalker_mac">Adresa MAC pentru portal</label>
      <input type="text" id="stalker_mac" maxlength="17" autocomplete="off" placeholder="00:1A:79:00:00:00"></div>
    <div class="rand"><label for="xtream_server">Server Xtream Codes</label>
      <input type="text" id="xtream_server" maxlength="512" autocomplete="off"></div>
    <div class="rand"><label for="xtream_port">Port Xtream Codes</label>
      <input type="text" id="xtream_port" maxlength="5" inputmode="numeric" autocomplete="off"></div>
    <div class="rand"><label for="xtream_user">Utilizator Xtream Codes</label>
      <input type="text" id="xtream_user" maxlength="512" autocomplete="off"></div>
    <div class="rand"><label for="xtream_parola">Parola Xtream Codes <span class="nota" id="parolaStare"></span></label>
      <input type="password" id="xtream_parola" maxlength="512" autocomplete="new-password"></div>
    <div class="butoane"><button type="button" class="principal" id="salveaza">Salvează</button>
      <button type="button" class="ascuns" id="stergeParola">Șterge parola</button></div>
    <p class="nota">Parola nu se arată: o scrii doar când vrei s-o schimbi. Un câmp de parolă gol o lasă cum e.</p>
  </section>
  <p class="nota">Ca pe televizor: Portal Stalker și Xtream Codes, deocamdată numai salvarea datelor de acces; conectarea reală vine în etapa următoare. Sursele M3U se țin în listă, dar canalele lor nu apar încă în lista de canale. Intrarea e marcată în lucru și pe televizor, în __DRUM_MENIU__; acolo aceleași date de acces sunt pe tasta albastră, iar tasta galbenă adaugă o sursă M3U.</p>
</div>
""" + _COADA + """var CAMPURI = ["m3u_cale", "stalker_portal", "stalker_mac", "xtream_server", "xtream_port", "xtream_user"];
var DATE = null;
function arata(d){
  DATE = d;
  var s = (d.surse || []).map(function(x, i){
    return rand(x.text, "Șterge", function(){ var q = new URLSearchParams(); q.set("index", String(i)); cuConfirmare("/api/iptv-sterge", q, dupa); });
  });
  pune("surse", s.length ? s : [gol("Nicio sursă IPTV adăugată încă.")]);
  var t = $("tip_sursa");
  if(document.activeElement !== t){
    t.textContent = "";
    (d.tipuri || []).forEach(function(a){ var o = document.createElement("option"); o.value = a[0]; o.textContent = a[1]; t.appendChild(o); });
    t.value = d.tip_sursa;
  }
  CAMPURI.forEach(function(c){ if(document.activeElement !== $(c)){ $(c).value = d[c] || ""; } });
  $("parolaStare").textContent = d.xtream_parola_scrisa ? "(scrisă)" : "(nescrisă)";
  $("stergeParola").classList.toggle("ascuns", !d.xtream_parola_scrisa);
}
function dupa(d){ if(d && d.surse){ arata(d); } }
function trimite(cale, q){
  mesaj("Se salvează...");
  return cerere(cale, "POST", q).then(function(d){ mesaj(d.message, !d.result); dupa(d); return d; }).catch(nimicNuRaspunde);
}
function citeste(){
  return cerere("/api/iptv").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi setările."; return; }
    arataPagina(); arata(d);
  }).catch(faraRaspuns);
}
$("adauga").addEventListener("click", function(){
  var q = new URLSearchParams(); q.set("m3u_cale", $("m3u_cale").value.trim());
  trimite("/api/iptv-adauga", q);
});
$("salveaza").addEventListener("click", function(){
  if(!DATE){ return; }
  var q = new URLSearchParams(), n = 0;
  if($("tip_sursa").value !== DATE.tip_sursa){ q.set("tip_sursa", $("tip_sursa").value); n++; }
  CAMPURI.forEach(function(c){ var v = $(c).value.trim(); if(v !== (DATE[c] || "")){ q.set(c, v); n++; } });
  if($("xtream_parola").value){ q.set("xtream_parola", $("xtream_parola").value); n++; }
  if(!n){ mesaj("Nu ai schimbat nimic."); return; }
  trimite("/api/iptv-seteaza", q).then(function(d){ if(d && d.result){ $("xtream_parola").value = ""; } });
});
$("stergeParola").addEventListener("click", function(){
  if(!confirm("Ștergi parola Xtream Codes salvată pe receptor?")){ return; }
  var q = new URLSearchParams(); q.set("sterge", "xtream_parola"); trimite("/api/iptv-seteaza", q);
});
citeste();""" + _SFARSIT


PAGINA_INTERFATA_WEB = "<!DOCTYPE html>" + _CAP + "Interfața web" + _STIL + """<h1>Interfața web HD Satelit</h1>
<p class="mesaj" id="incarcare">Se citesc setările...</p>
<div id="continut" class="ascuns">
  <section class="card">
    <h2>Pornire și port</h2>
    <div class="rand"><label for="activ">Activează HdsWebControl</label>
      <select id="activ"><option value="1">Da</option><option value="0">Nu</option></select></div>
    <div class="rand"><label for="port">Port TCP</label>
      <input type="number" id="port" min="80" max="65535" step="1" inputmode="numeric"></div>
    <div class="butoane"><button type="button" id="schimbaPort">Schimbă portul</button></div>
    <p class="nota" id="portNota"></p>
  </section>
  <section class="card">
    <h2>Acces</h2>
    <div class="rand"><label for="codRetea">Cere codul și în rețeaua locală</label>
      <select id="codRetea"><option value="0">Nu</option><option value="1">Da</option></select></div>
    <div class="rand"><label for="aplicatii">Aplicații de telefon</label>
      <select id="aplicatii"><option value="0">Nu</option><option value="1">Da</option></select></div>
    <div class="rand"><label for="aplicatiiAfara">Acces din afara casei</label>
      <select id="aplicatiiAfara"><option value="0">Nu</option><option value="1">Da</option></select></div>
    <p class="nota" id="aplicatiiNota"></p>
    <div class="butoane"><button type="button" class="ascuns" id="arataParola">Arată parola</button>
      <button type="button" class="ascuns" id="parolaAplicatii">Parolă nouă pentru aplicații</button></div>
  </section>
  <section class="card">
    <h2>Browsere conectate</h2>
    <div id="browsere"></div>
    <div class="butoane"><button type="button" class="rosu" id="deconecteaza">Deconectează browserele</button>
      <button type="button" id="browserNou">Conectează un browser nou</button></div>
  </section>
  <section class="card">
    <h2>Cheia pentru scripturi</h2>
    <div class="status-linie"><span>Cheia</span><span id="cheie"></span></div>
    <p class="nota">Doar pentru programatori. Browserul obișnuit nu are nevoie de ea. Cheia e ascunsă: butonul Arată cheia o arată întreagă.</p>
    <div class="butoane"><button type="button" id="arataCheie">Arată cheia</button>
      <button type="button" class="rosu" id="cheieNoua">Cheie nouă pentru panoul web</button></div>
  </section>
  <p class="nota">Aceleași setări sunt pe televizor, în __DRUM_MENIU__. Tema și culorile paginilor web sunt în pagina Setări.</p>
</div>
""" + _COADA + """var D = null, A = null, PAROLA = "", CHEIE = "", PUNCTE = "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022";
function data(t){ return t ? new Date(t * 1000).toLocaleDateString("ro-RO") : ""; }
function arata(d){
  D = d;
  if(document.activeElement !== $("activ")){ $("activ").value = d.activ ? "1" : "0"; }
  if(document.activeElement !== $("port")){ $("port").value = d.port; }
  var n = "Activarea și portul se aplică după repornirea interfeței. Acum interfața ascultă pe portul " + d.port_folosit + (d.adresa ? ", la adresa " + d.adresa : "") + ".";
  if(!d.activ){ n += " Oprirea e salvată: după repornirea interfeței, paginile nu mai răspund."; }
  $("portNota").textContent = n;
  var b = (d.browsere || []).map(function(x){
    var t = (x.tip === "aplicatie" ? "Telefon: " : "") + (x.nume || "Browser") + (x.adresa ? ", " + x.adresa : "") + (x.creat ? ", din " + data(x.creat) : "");
    return rand(t);
  });
  pune("browsere", b.length ? b : [gol("Niciun browser conectat cu cod.")]);
  $("cheie").textContent = CHEIE || PUNCTE;
  $("arataCheie").textContent = CHEIE ? "Ascunde cheia" : "Arată cheia";
}
function arataAcces(a){
  $("codRetea").value = a.cod_retea_locala ? "1" : "0";
  $("aplicatii").value = a.aplicatii ? "1" : "0";
  $("aplicatiiAfara").value = a.aplicatii_afara ? "1" : "0";
  A = a;
  var p = PAROLA || PUNCTE, t = [];
  if(a.aplicatii){
    t.push(a.cod_retea_locala ? "Aplicații de telefon: și acasă scrii utilizatorul root și parola " + p + "." : "Aplicații de telefon: acasă scrii în aplicație numai adresa receptorului, fără utilizator și parolă.");
    t.push(a.aplicatii_afara ? "Din afara casei: utilizatorul root și parola " + p + "." : "Din afara casei: oprit. Pornit, cere utilizatorul root și parola " + p + ".");
    var v = a.aplicatii_vazute || [];
    if(v.length){ t.push("Conectate: " + v.map(function(x){ return x.nume + " (" + x.adresa + ")"; }).join(", ") + "."); }
  } else {
    t.push("Aplicațiile obișnuite de telefon pentru receptoare Enigma2 (canale, telecomandă, ghid, înregistrări) primesc răspuns după ce pornești rândul de mai sus.");
  }
  $("aplicatiiNota").textContent = t.join(" ");
  $("parolaAplicatii").classList.toggle("ascuns", !a.aplicatii);
  $("arataParola").classList.toggle("ascuns", !a.aplicatii);
  $("arataParola").textContent = PAROLA ? "Ascunde parola" : "Arată parola";
}
// parola pentru aplicatii si cheia pentru scripturi: numai la butoanele Arată (POST /api/interfata-web-secrete)
function secret(ce, gata){
  var q = new URLSearchParams(); q.set("ce", ce);
  cerere("/api/interfata-web-secrete", "POST", q).then(function(d){
    if(!d.result){ mesaj(d.message, true); return; }
    gata(d);
  }).catch(nimicNuRaspunde);
}
function citesteAcces(){
  return cerere("/api/interfata-web").then(function(a){ if(a.result){ arataAcces(a); } });
}
function dupa(d){
  if(d && d.browsere){ arata(d); }
  if(d && d.result && d.reincarca){ setTimeout(function(){ location.reload(); }, 1500); }
}
function citeste(){
  return cerere("/api/interfata-web-detalii").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi setările."; return; }
    arataPagina(); arata(d); return citesteAcces();
  }).catch(faraRaspuns);
}
function actiune(fapta, valoare){
  var q = new URLSearchParams(); q.set("fapta", fapta); if(valoare !== undefined){ q.set("valoare", valoare); }
  return q;
}
$("activ").addEventListener("change", function(){
  if($("activ").value === "1"){
    mesaj("Se salvează...");
    cerere("/api/interfata-web-actiune", "POST", actiune("activ", "1")).then(function(d){ mesaj(d.message, !d.result); dupa(d); }).catch(nimicNuRaspunde);
  } else {
    $("activ").value = "1";
    cuConfirmare("/api/interfata-web-actiune", actiune("activ", "0"), dupa);
  }
});
$("schimbaPort").addEventListener("click", function(){ cuConfirmare("/api/interfata-web-actiune", actiune("port", $("port").value.trim()), dupa); });
["codRetea", "aplicatii", "aplicatiiAfara"].forEach(function(id){
  var cheie = {codRetea: "cod_retea_locala", aplicatii: "aplicatii", aplicatiiAfara: "aplicatii_afara"}[id];
  $(id).addEventListener("change", function(){
    var q = new URLSearchParams(); q.set(cheie, $(id).value);
    mesaj("Se salvează...");
    cerere("/api/interfata-web-seteaza", "POST", q).then(function(d){ mesaj(d.message, !d.result); citesteAcces(); }).catch(nimicNuRaspunde);
  });
});
$("parolaAplicatii").addEventListener("click", function(){
  if(!confirm("Faci o parolă nouă pentru aplicații? Din afara casei, aplicațiile care o folosesc pe cea veche nu mai primesc răspuns până nu scrii în ele parola nouă.")){ return; }
  var q = new URLSearchParams(); q.set("parola_aplicatii_noua", "1");
  cerere("/api/interfata-web-seteaza", "POST", q).then(function(d){ PAROLA = ""; mesaj(d.message, !d.result); citesteAcces(); }).catch(nimicNuRaspunde);
});
$("arataParola").addEventListener("click", function(){
  if(PAROLA){ PAROLA = ""; if(A){ arataAcces(A); } return; }
  secret("parola", function(d){ PAROLA = d.parola_aplicatii || ""; if(A){ arataAcces(A); } });
});
$("arataCheie").addEventListener("click", function(){
  if(CHEIE){ CHEIE = ""; if(D){ arata(D); } return; }
  secret("cheie", function(d){ CHEIE = d.cheie || ""; if(D){ arata(D); } });
});
$("deconecteaza").addEventListener("click", function(){ cuConfirmare("/api/interfata-web-actiune", actiune("deconecteaza"), dupa); });
$("browserNou").addEventListener("click", function(){ cuConfirmare("/api/interfata-web-actiune", actiune("browser_nou"), dupa); });
$("cheieNoua").addEventListener("click", function(){ cuConfirmare("/api/interfata-web-actiune", actiune("cheie"), dupa); });
citeste();""" + _SFARSIT


# ---------------------------------------------------------------- traducerea paginilor
# Textele sabloanelor de mai sus, traduse la cerere in limba receptorului (traducere_pagini.py). Un text
# nou sau schimbat in sablon se scrie si aici (proba textelor paginilor web il cere).
TEXTE_PAGINA = {
	"html": (
		N_("DVB-I: Configurare"),
		N_("Canale de pe internet (DVB-I)"),
		N_("Se citesc setările..."),
		N_("Țara și regiunea"),
		N_("Țara"),
		N_("Regiunea"),
		N_("Țările vin din registrele DVB-I; listele țării se iau singure și se actualizează din oră în oră."),
		N_("Întreabă din nou registrele"),
		N_("Trecere pe internet"),
		N_("Trecere singură pe internet când satelitul nu se recepționează"),
		N_("Da"),
		N_("Nu"),
		N_("Canalul de satelit care are și adresă de internet în listele DVB-I trece singur pe internet "
			"când satelitul nu se recepționează și se întoarce pe satelit când semnalul revine."),
		N_("Listele țării"),
		N_("Listele adevărate ale țării sunt bifate singure; cele de probă ale registrelor le bifezi numai "
			"dacă vrei să le încerci."),
		N_("Reîncărcare"),
		N_("Reîncarcă acum"),
		N_("Descarcă acum listele alese; canalele apar în lista de canale, în buchetul Canale de pe "
			"internet (DVB-I)."),
		N_("Canalele"),
		N_("Încearcă din nou"),
		N_("Setări VPN"),
		N_("Adrese puse de mână și liste predefinite (avansat)"),
		N_("Acum"),
		N_("DVB-I activ"),
		N_("Liste predefinite"),
		N_("Bifa pornește sau oprește o listă, ca OK pe televizor."),
		N_("Adrese proprii"),
		N_("Adresă nouă (http:// sau https://)"),
		N_("Adaugă adresa"),
		N_("Aceleași setări sunt pe televizor, în __DRUM_MENIU__."),
		N_("https://"),
		N_("DVB-I: Privește"),
		N_("Privește canalul"),
		N_("Se citește canalul..."),
		N_("Adresa fluxului"),
		N_("Copiază adresa"),
		N_("Deschide adresa"),
		N_("Fluxul vine direct de la televiziune, prin internetul acestui calculator sau telefon, nu prin "
			"receptor. Pe televizor canalul e în buchetul Canale de pe internet (DVB-I)."),
		N_("<a href=\"/dvb-i\">Înapoi la canalele de pe internet</a>. Aceleași setări sunt pe televizor, în "
			"__DRUM_MENIU__."),
		N_("DVB-MABR: IP Multicast"),
		N_("DVB-MABR: Configurare IP Multicast"),
		N_("Stare"),
		N_("DVB-MABR activ"),
		N_("Autodiscover SAP/SD&amp;S"),
		N_("Grupuri multicast manuale"),
		N_("Grup nou (adresă:port, de exemplu 239.1.1.1:9000)"),
		N_("Adaugă grupul"),
		N_("Sesiuni descoperite live (SAP)"),
		N_("Caută SAP"),
		N_("Intrarea e marcată în lucru și pe televizor: setările se salvează, dar nicio parte a "
			"receptorului nu le folosește încă. Aceleași setări sunt pe televizor, în __DRUM_MENIU__."),
		N_("Televiziune prin IP (IPTV)"),
		N_("Surse"),
		N_("Adaugă sursă M3U"),
		N_("Playlist M3U/M3U8 (fișier local sau URL)"),
		N_("Date de acces"),
		N_("Tipul sursei"),
		N_("Portal Stalker/Ministra (adresa)"),
		N_("Adresa MAC pentru portal"),
		N_("Server Xtream Codes"),
		N_("Port Xtream Codes"),
		N_("Utilizator Xtream Codes"),
		N_("Parola Xtream Codes <span class=\"nota\" id=\"parolaStare\"></span>"),
		N_("Salvează"),
		N_("Șterge parola"),
		N_("Parola nu se arată: o scrii doar când vrei s-o schimbi. Un câmp de parolă gol o lasă cum e."),
		N_("Ca pe televizor: Portal Stalker și Xtream Codes, deocamdată numai salvarea datelor de acces; "
			"conectarea reală vine în etapa următoare. Sursele M3U se țin în listă, dar canalele lor nu apar "
			"încă în lista de canale. Intrarea e marcată în lucru și pe televizor, în __DRUM_MENIU__; acolo "
			"aceleași date de acces sunt pe tasta albastră, iar tasta galbenă adaugă o sursă M3U."),
		N_("/media/hdd/lista.m3u"),
		N_("Interfața web"),
		N_("Interfața web HD Satelit"),
		N_("Pornire și port"),
		N_("Activează HdsWebControl"),
		N_("Port TCP"),
		N_("Schimbă portul"),
		N_("Acces"),
		N_("Cere codul și în rețeaua locală"),
		N_("Aplicații de telefon"),
		N_("Acces din afara casei"),
		N_("Arată parola"),
		N_("Parolă nouă pentru aplicații"),
		N_("Browsere conectate"),
		N_("Deconectează browserele"),
		N_("Conectează un browser nou"),
		N_("Cheia pentru scripturi"),
		N_("Cheia"),
		N_("Doar pentru programatori. Browserul obișnuit nu are nevoie de ea. Cheia e ascunsă: butonul Arată "
			"cheia o arată întreagă."),
		N_("Arată cheia"),
		N_("Cheie nouă pentru panoul web"),
		N_("Aceleași setări sunt pe televizor, în __DRUM_MENIU__. Tema și culorile paginilor web sunt în "
			"pagina Setări."),
	),
	"js": (
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		N_("Merge"),
		N_("Oprit pentru țara ta"),
		N_("Adresă moartă"),
		N_("Nu răspunde"),
		N_("Neîncercat"),
		N_("Nicio țară (numai adresele puse de mână)"),
		N_("· liste:"),
		N_("· numai liste de probă"),
		N_("toată țara"),
		N_("Se întreabă registrele DVB-I..."),
		N_("Țările vin din registrele DVB-I; listele țării se iau singure și se actualizează din oră în oră."),
		N_("Furnizor:"),
		N_("· listă de probă"),
		N_("Liste de probă ale registrelor:"),
		N_("Țara aleasă nu are liste în registre."),
		N_("Se încearcă:"),
		N_("din"),
		N_("oprite pentru țara ta"),
		N_("adrese moarte"),
		N_("fără răspuns"),
		N_("neîncercate"),
		N_("Niciun canal încă. Alege țara sau o listă, apoi Reîncarcă acum."),
		N_("și pe satelit"),
		N_("Privește"),
		N_("Canalele oprite pentru țara ta se pot vedea cu VPN-ul receptorului pornit, cu o adresă din"),
		N_("țara listei"),
		N_(". După pornirea VPN-ului, canalele se încearcă din nou singure."),
		N_("Acum VPN-ul duce numai navigatorul: la Ce trece prin VPN alege tot traficul."),
		N_("Listele se reîncarcă singure din oră în oră cât timp receptorul e pornit."),
		N_("Șterge"),
		N_("Nicio adresă proprie."),
		N_("Se salvează..."),
		N_("Receptorul nu a putut citi setările."),
		N_("Scrie întâi adresa listei."),
		N_("Merge din casa receptorului"),
		N_("Oprit pentru țara receptorului"),
		N_("Adresa nu mai răspunde"),
		N_("Nu a răspuns la ultima încercare"),
		N_("Neîncercat încă din casa receptorului"),
		N_("Browserul acesta nu redă singur fluxuri DASH (.mpd). Deschide adresa de mai jos într-un player "
			"care le redă, de pildă VLC (Media, Deschide flux din rețea)."),
		N_("Browserul acesta nu redă singur fluxuri HLS (.m3u8). Deschide adresa de mai jos într-un player "
			"care le redă, de pildă VLC (Media, Deschide flux din rețea)."),
		N_("Televiziunea nu dă fluxul în țara din care vine cererea. În browser fluxul trece prin "
			"internetul acestui calculator sau telefon: aici ar trebui pornit un VPN cu o adresă din țara "
			"canalului."),
		N_("Fluxul nu a pornit în browser. Adresa de mai jos se poate încerca într-un player, de pildă VLC."),
		N_("Canalul nu mai e în listele DVB-I. Pagina canalelor are lista de acum."),
		N_("Adresa e copiată."),
		N_("fără nume"),
		N_("Apasă Caută SAP pentru a descoperi sesiuni MABR în rețea."),
		N_("Niciun grup adăugat de mână."),
		N_("Nicio sursă IPTV adăugată încă."),
		N_("(scrisă)"),
		N_("(nescrisă)"),
		N_("Nu ai schimbat nimic."),
		N_("Ștergi parola Xtream Codes salvată pe receptor?"),
		N_("Activarea și portul se aplică după repornirea interfeței. Acum interfața ascultă pe portul"),
		N_(", la adresa"),
		N_("Oprirea e salvată: după repornirea interfeței, paginile nu mai răspund."),
		N_("Telefon:"),
		N_("Browser"),
		N_(", din"),
		N_("Niciun browser conectat cu cod."),
		N_("Aplicații de telefon: și acasă scrii utilizatorul root și parola"),
		N_("Aplicații de telefon: acasă scrii în aplicație numai adresa receptorului, fără utilizator și "
			"parolă."),
		N_("Din afara casei: utilizatorul root și parola"),
		N_("Din afara casei: oprit. Pornit, cere utilizatorul root și parola"),
		N_("Conectate:"),
		N_("Aplicațiile obișnuite de telefon pentru receptoare Enigma2 (canale, telecomandă, ghid, "
			"înregistrări) primesc răspuns după ce pornești rândul de mai sus."),
		N_("Faci o parolă nouă pentru aplicații? Din afara casei, aplicațiile care o folosesc pe cea veche "
			"nu mai primesc răspuns până nu scrii în ele parola nouă."),
		N_("Arată parola"),
		N_("Ascunde parola"),
		N_("Arată cheia"),
		N_("Ascunde cheia"),
	),
}


def _traducePagina(sablon, fel="pagina"):
	"""Sablonul in limba receptorului; fara pachetul HdsWebControl (probele de pe PC), sablonul ca atare."""
	try:
		from .traducere_pagini import traduce
	except ImportError:
		return sablon
	return traduce(sablon, TEXTE_PAGINA, fel)
# ---------------------------------------------------------------- sfarsitul traducerii paginilor
