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
#   /iptv           IPTV (Screens/IptvSetup.py): listele si conturile omului, adaugare (playlist, cont, portal, lista demo),
#                   actualizare, stergere cu confirmare. Parola merge numai de la browser la receptor, niciodata inapoi.
#                   Parola Xtream numai se scrie sau se sterge, nu se trimite inapoi, si se primeste numai din corpul
#                   cererii. Parola si adresa M3U (care poate avea contul in ea) sunt
#                   campuri text obisnuite, se vad cat le scrii, fara stelute si fara buton Arata / Ascunde; dupa
#                   adaugare campurile se golesc, iar lista surselor nu are nici parola, nici adresa cu parola.
#                   Logica si verificarea textelor: Components/HdsIptvSurse (aceleasi pe televizor).
#   /interfata-web  Interfata web (Screens/HdsWebControlSetup.py): pornirea si portul (oprirea si mutarea cu confirmare
#                   si avertismentul ca pagina se pierde sau se muta), browserele intrate cu parola (deconectarea, cu
#                   confirmare), cheia pentru scripturi (nu se arata pana la butonul Arata cheia, care o cere
#                   intreaga prin POST /api/interfata-web-secrete?ce=cheie, din plugin.py; tasta Cheie noua pentru
#                   panoul web cu confirmare: cheie noua si toate aparatele asociate deconectate, in afara de browserul
#                   care cere, ca pe televizor, cheieNouaPanou). Parola pentru aplicatii la fel: nu se arata pana la butonul
#                   Arata parola (?ce=parola); nici HTML-ul, nici GET-urile paginii nu au parola sau cheia.
#                   Randurile aplicatii, aplicatii_afara, captura_interval (la cate secunde cere prima pagina imaginea
#                   ecranului) si parola pentru aplicatii merg prin rutele care exista deja (plugin.py: /api/interfata-web, /api/interfata-web-seteaza).
#
# Rute (poarta comuna a HdsJsonResource; ce schimba ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF):
#   GET  /api/dvb-i                 starea
#   POST /api/dvb-i-seteaza         activ=0|1 | predefinita=<cheie>&bifata=0|1 | adauga_url=<adresa>
#   POST /api/dvb-i-sterge          index=N, in doi pasi (pas=intreaba, cod=..., pas=renunta)
#   POST /api/dvb-i-reincarca       reincarcarea acum
#   POST /api/dvb-i-cauta           cele mai noi liste acum: registrele, apoi reincarcarea (buchetul DVB-I gol din Canale)
#   GET  /api/mabr                  starea
#   POST /api/mabr-seteaza          activ=0|1 | autodiscover=0|1 | adauga=<adresa:port>
#   POST /api/mabr-sterge           index=N, in doi pasi
#   POST /api/mabr-cauta            cautarea SAP (5 secunde, pe fir); rezultatul vine in GET
#   GET  /api/iptv-4k               cautarea canalelor 4K reale (Components/HdsIptv4K.py): starea, textul de sus, canalele 4K
#   POST /api/iptv-4k-porneste      porneste cautarea (toti candidatii); /api/iptv-4k-opreste o opreste. Pagina: /iptv-4k
#   GET  /api/iptv                  sursele si starea lor (fara parole si fara adrese cu parola)
#   GET  /api/iptv-cont             id=<sursa Xtream>: starea contului (expira, conexiunile, proba), ceruta pe un fir numai cand pagina
#                                   e deschisa (0.7.5, IPI; config.usage.hds_iptv_cont); {"asteapta": true} cat se asteapta serverul
#   GET  /api/iptv-arhiva           emisiunile trecute ale canalului de pe televizor, cand furnizorul tine arhiva (0.7.5, IPI;
#                                   Screens/HdsIptvArhiva.py; config.usage.hds_iptv_arhiva): {"canal": ""} fara arhiva, {"asteapta": true}
#   POST /api/iptv-arhiva-porneste  canal=<sursa/cheie>, i=<randul>: porneste emisiunea pe televizor (numai din lista data mai sus)
#   GET  /api/iptv-grupe            id=<sursa>: tarile si grupele, cu ce se vede
#   POST /api/iptv-grupe-schimba    id=<sursa>, cheie=<rand> sau tot=ascunde|arata
#   POST /api/iptv-adauga           fel=m3u|xtream|stalker|demo, nume, adresa | server, utilizator, parola (numai din corp) |
#                                   portal, mac; lista se aduce pe firul de lucru, rezultatul vine in GET
#   POST /api/iptv-actualizeaza     [id=<sursa>] o sursa sau toate
#   POST /api/iptv-fisier           text=<continutul unui fisier cu adrese, cate una pe rand> (fisierul ales in browser; aceeasi
#                                   citire ca /etc/enigma2/iptv.txt pus prin FTP, Components/HdsIptvFisier.py)
#   POST /api/iptv-sterge           id=<sursa>, in doi pasi
#   GET  /api/iptv-sursa-canale     id=<sursa>[&grupa=<n>&de_la=<n>]: grupele sursei sau canalele unei grupe (butonul Deschide, FLM2
#                                   0.7.7; fisierul se citeste pe un fir, primul raspuns poate fi {"asteapta": true})
#   POST /api/iptv-sursa-porneste   id=<sursa>&cheie=<canal>: canalul porneste pe televizor (filmele si serialele: /api/vod*)
#   GET  /api/interfata-web-detalii pornirea, portul, browserele (fara cheie)
#   POST /api/interfata-web-actiune fapta=activ&valoare=0|1 | fapta=port&valoare=N | fapta=deconecteaza |
#                                   fapta=cheie; cele periculoase in doi pasi (browser_nou, codul de pe televizor, s-a scos)
#   GET  /dvb-i, /mabr, /iptv, /interfata-web   paginile
# Actiunile in doi pasi se refuza cand vin cu ?token= (meniu_comun_web.numaiBrowser).
#
# FIRUL: totul ruleaza pe firul enigma2 si e scurt (fisiere mici); reincarcarea DVB-I si cautarea SAP merg pe firele
# lor (Components), iar pagina citeste starea din nou. Fisierul nu importa nimic din enigma2 la incarcare.

import time

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
	elif st["gata"] and st["succes"] and st.get("fara_liste"):
		# 0.6.2: nicio lista de descarcat (fara tara, liste sau adrese), ca pe televizor (HdsDvbIReloadNow)
		mesaj = _t(D.TEXT_FARA_LISTE)
	elif st["gata"] and st["succes"]:
		mesaj = _t("Reîncărcare terminată cu succes.")
	elif st["gata"]:
		mesaj = _t("Reîncărcarea a eșuat: %s") % (st["eroare"] or "?")
	else:
		mesaj = ""
	return {"in_curs": bool(st["in_curs"]), "gata": bool(st["gata"]), "succes": st["succes"], "mesaj": mesaj,
		"ora": st.get("ora", 0), "fara_liste": bool(st.get("fara_liste"))}


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
	doar = getattr(DD, "doarIn", None)
	for c in DD.canale():
		st, cod, ora = DD.stareUrl(c.get("url", ""))
		n[st] = n.get(st, 0) + 1
		# DVI2: oprit pentru tara, cu tara listei cand se stie: eticheta gata tradusa, ca in lista de canale
		tara = doar(c.get("url", ""), stare=st) if doar is not None and st == "oprit_tara" else ""
		rez.append({"id": c.get("id"), "nr": c.get("nr"), "lcn": c.get("lcn"), "nume": c.get("nume", ""),
			"tip": c.get("tip", "tv"), "url": c.get("url", ""), "sat": bool(c.get("sat")), "stare": st, "cod": cod,
			"ora": ora, "ascuns": bool(c.get("ascuns")),
			"eticheta": (_t(DD.T_DOAR_IN) % tara) if tara else ""})
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
	# DVK (15.11.2026): listele care nu raspund (Components/HdsDvbISurse, prin HdsDvbISetari): "nu_raspunde" la fiecare
	# lista si "adrese_nu_raspund" {adresa: text} pentru adresele proprii (url_uri ramane lista de adrese)
	su = D._surse() if hasattr(D, "textNuRaspunde") else None
	nu = (lambda a: D.textNuRaspunde(a, su)) if su is not None else (lambda a: "")
	rez["adrese_nu_raspund"] = D.stariAdrese(rez["url_uri"], su) if su is not None else {}
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
		"liste_tarii": [dict(l, canale=D.canaleLista(stare, l["adresa"]), nu_raspunde=nu(l["adresa"]) if l.get("aleasa")
			else "") for l in D.listeleTarii(cfg, reg)],
		"rezerva": D.rezervaPornita(cfg),
		"toate_tarile": D.toateTarilePornit(cfg) if hasattr(D, "toateTarilePornit") else None,
		# DVI2: si listele de proba ale registrelor, din toate tarile (ca randul de pe televizor)
		"liste_proba": D.probaPornit(cfg) if hasattr(D, "probaPornit") else None,
		# lista DVB-I in lista de canale (scoasa de om, nu mai revine singura), ca randul de pe televizor
		"in_lista": D.inListaDeCanale() if hasattr(D, "inListaDeCanale") else None,
		"liste_alte_tari": [dict(l, canale=D.canaleLista(stare, l["adresa"]), nu_raspunde=nu(l["adresa"]),
			tara_nume=D.numeTara(l["tara"]) if l["tara"] else "") for l in D.listeleAltorTari(cfg, reg)] if hasattr(D, "listeleAltorTari") and cfg.get("tara") else [],
		"stare": {"culoare": culoare, "text": text, "detalii": detalii},
		"canale": canale, "rezumat": n,
		# EPG2: cate canale nu sunt in buchet pana merg din nou si cate adrese (clipuri, imagini de proba) s-au scos
		"ascunse": sum(1 for c in canale if c.get("ascuns")),
		"scoase": sum(int(v) for v in (stare.get("scoase") or {}).values()) if isinstance(stare.get("scoase"), dict) else 0,
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
	elif "toate_tarile" in arg and hasattr(D, "comutaToateTarile"):
		# TODO 1883: listele din toate tarile (ca pe televizor, randul "Liste din toate țările")
		v = _bool(arg["toate_tarile"])
		if v is None:
			return _cuMesaj(stareDvbi(D, cale), False, _t("Se alege cu toate_tarile=0 sau 1."))
		if v != D.toateTarilePornit(cfg):
			D.comutaToateTarile(cfg)
		mesaj = _t("Salvat. Listele se descarcă din nou.")
		reincarca = True
	elif "liste_proba" in arg and hasattr(D, "comutaProba"):
		# DVI2: listele de proba ale registrelor, din toate tarile (randul "Și listele de probă" de pe televizor)
		v = _bool(arg["liste_proba"])
		if v is None:
			return _cuMesaj(stareDvbi(D, cale), False, _t("Nu s-a trimis nicio setare."))
		if v != D.probaPornit(cfg):
			D.comutaProba(cfg)
		mesaj = _t("Salvat. Listele se descarcă din nou.")
		reincarca = True
	elif "in_lista" in arg and hasattr(D, "puneInLista"):
		# randul "Arată lista în lista de canale": semnul listei scoase si legarea, pe loc; hdsdvbi.conf nu se rescrie
		v = _bool(arg["in_lista"])
		if v is None:
			return _cuMesaj(stareDvbi(D, cale), False, _t("Nu s-a trimis nicio setare."))
		D.puneInLista(v)
		return _cuMesaj(stareDvbi(D, cale), True, _t("Salvat."))
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


def cautaDvbi(D=None, cale=None):
	"""POST /api/dvb-i-cauta: cele mai noi liste DVB-I acum (registrele intrebate din nou, apoi reincarcarea), ca OK in
	buchetul DVB-I gol din lista de canale; rezultatul se vede in GET /api/dvb-i si in lista."""
	D = _dvbi(D)
	if not D.cautaAcum():
		return _cuMesaj(stareDvbi(D, cale), False, _t("O reîncărcare e deja în curs."))
	return _cuMesaj(stareDvbi(D, cale), True, _t("Caut cele mai noi liste DVB-I…"))


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


def _iptv(I=None):
	"""(HdsIptvSurse, HdsIptvClient, HdsIptvLucru); probele de pe PC dau alt obiect cu aceleasi trei."""
	if I is not None:
		return I
	from Components import HdsIptvSurse, HdsIptvClient, HdsIptvLucru
	return HdsIptvSurse, HdsIptvClient, HdsIptvLucru


def _textCanale(n):
	try:
		from Components.HdsIndexCanale import text_numar
		return text_numar(n)
	except Exception:
		return str(n)


def _textExpirare(ora):
	try:
		return (_t(N_("Expiră la %s")) % time.strftime("%d.%m.%Y", time.localtime(int(ora)))) if ora else ""
	except (TypeError, ValueError, OverflowError, OSError):
		return ""


_cont_web = {}       # sursa -> None (se asteapta serverul) | dict | False (nu se stie)


def stareContIptv(arg, I=None, fir=None):
	"""GET /api/iptv-cont: starea contului Xtream (HdsIptvClient.stareContXtream), fara date de acces. Cererea spre server merge pe
	un fir (termen 8 s), ca serverul web sa nu stea: primul raspuns e {"asteapta": true}, pagina intreaba din nou."""
	S, C, L = _iptv(I)
	sid = arg.get("id", "")
	s = S.sursa(sid)
	if not s or s.get("fel") != "xtream" or s.get("neconectata"):
		return {"result": True, "text": ""}
	if sid not in _cont_web:
		_cont_web[sid] = None

		def lucru():
			rez = False
			try:
				rez = C.stareContXtream(s) or False
			except Exception as e:
				_jurnal("starea contului: %s" % type(e).__name__)
			_cont_web[sid] = rez
		if fir is not None:
			fir(lucru)
		else:
			import threading
			threading.Thread(target=lucru, name="IptvStareContWeb", daemon=True).start()
		if _cont_web.get(sid) is None:
			return {"result": True, "asteapta": True}
	v = _cont_web.get(sid)
	if v is None:
		return {"result": True, "asteapta": True}
	del _cont_web[sid]          # data viitoare se intreaba din nou (HdsIptvClient tine minte raspunsul un minut)
	return {"result": True, "text": C.textStareCont(v) if v else "", "stare": v.get("stare", "") if v else ""}


_arhiva_web = {}     # "sursa/cheie" -> [ora, None (se asteapta) | lista | text de eroare, canalul, referinta canalului]
PASTRARE_ARHIVA_S = 120


def _refTv():
	try:
		import NavigationInstance
		nav = NavigationInstance.instance
		ref = nav.getCurrentlyPlayingServiceReference() if nav is not None else None
		return ref.toString() if ref is not None and ref.valid() else ""
	except ImportError:
		return ""


def arhivaIptv(arg, ref_text=None, fir=None):
	"""GET /api/iptv-arhiva: emisiunile trecute ale canalului de pe televizor (Screens/HdsIptvArhiva.py). Serverul se intreaba pe un fir,
	numai cand pagina e deschisa; primul raspuns e {"asteapta": true}. Fara date de acces si fara adrese."""
	from Screens import HdsIptvArhiva as H
	from Components import HdsIptvClient as C
	ref_text = _refTv() if ref_text is None else ref_text
	canal = H.canalCuArhiva(ref_text)
	if canal is None:
		return {"result": True, "canal": ""}
	s, sid, cheie, zile = canal
	k = "%s/%s" % (sid, cheie)
	v = _arhiva_web.get(k)
	if v is None or (v[1] is not None and time.time() - v[0] > PASTRARE_ARHIVA_S):
		_arhiva_web.clear()
		v = _arhiva_web[k] = [time.time(), None, canal, ref_text]

		def lucru():
			try:
				v[1] = C.programeArhiva(s, cheie) or []
			except C.EroareIptv as e:
				v[1] = e.pentruOm()
			except Exception as e:
				_jurnal("arhiva: %s" % type(e).__name__)
				v[1] = C.E_NU_RASPUNDE
		if fir is not None:
			fir(lucru)
		else:
			import threading
			threading.Thread(target=lucru, name="IptvArhivaWeb", daemon=True).start()
	if v[1] is None:
		return {"result": True, "asteapta": True}
	nume = H.numeCanal(v[3], sid, cheie)
	if not isinstance(v[1], list):
		return {"result": True, "canal": nume, "id": k, "programe": [], "mesaj": _t(v[1])}
	acum = time.time()
	return {"result": True, "canal": nume, "id": k, "zile": zile, "mesaj": "" if v[1] else _t(H.T_GOL),
		"programe": [{"text": H.randProgram(p, acum), "descriere": p.get("descriere") or ""} for p in v[1]]}


def pornesteArhivaIptv(arg, nav=None):
	"""POST /api/iptv-arhiva-porneste: emisiunea aleasa din lista data de /api/iptv-arhiva porneste pe televizor (fara sa fie tinuta minte
	ca ultimul canal: dupa o repornire receptorul porneste pe canalul in direct)."""
	from Screens import HdsIptvArhiva as H
	v = _arhiva_web.get(arg.get("canal", ""))
	try:
		i = int(arg.get("i", ""))
	except ValueError:
		i = -1
	if not v or not isinstance(v[1], list) or not 0 <= i < len(v[1]):
		return {"result": False, "message": _t(N_("Lista emisiunilor s-a schimbat. Deschide din nou pagina."))}
	p = v[1][i]
	_s, sid, cheie, _zile = v[2]
	ref = H.refArhiva(v[3], sid, p["cheie"], H.numeArhiva(H.numeCanal(v[3], sid, cheie), p))
	try:
		from enigma import eServiceReference
		if nav is None:
			import NavigationInstance
			nav = NavigationInstance.instance
		nav.playService(eServiceReference(ref))
	except Exception as e:
		_jurnal("arhiva, pornirea: %s" % type(e).__name__)
		return {"result": False, "message": _t(N_("Emisiunea nu a pornit. Încearcă din nou."))}
	return {"result": True, "message": _t(N_("Emisiunea pornește pe televizor."))}


def stareIptv(I=None):
	"""GET /api/iptv: sursele, fara parole si fara adrese cu parola (HdsIptvSurse.publica), plus lista demo, publica, cu acordul
	fiecarui canal, numai daca e pusa."""
	S, C, L = _iptv(I)
	surse = []
	for p in S.citesteSursePublic():
		lucreaza = L.inLucru(p["id"])
		p["lucreaza"] = lucreaza
		p["fel_text"] = _t(S.NUME_FEL.get(p["fel"], p["fel"]))
		p["nume"] = p["nume"] or p["fel_text"]
		p["canale_text"] = _textCanale(p["canale"]) if p["canale"] else ""
		p["eroare"] = _t(p["eroare"]) if p["eroare"] else ""
		# 0.7.7 (IPX, e-mailurile 6514 si 6520): pagina pune "Merge." in fata notei (JS stareSursa), ca pe televizor eticheta verde
		p["fara_https_text"] = _t(S.T_FARA_HTTPS) if p["fara_https"] else ""
		# 0.7.7 (BQT, Ozgur e-mailul 6514): ce n-a incaput, canalele TV si filmele separat, acelasi text ca pe televizor
		# (Screens/IptvSetup.mesajSursa, HdsIptvClient.textTaiate)
		p["taiate_text"] = C.textTaiate(p, _t) if p.get("taiate") else ""
		p["expira_text"] = _textExpirare(p.get("expira"))
		# 0.7.7 (FLM2): cate filme are un playlist in fisierul lor (randul Filme din pagina sursei, butonul Deschide)
		p["filme_sursa"] = S.numarFilme(p) if p["fel"] == "m3u" else 0
		p["epg_text"] = _t(N_("Se încarcă ghidul TV...")) if p.get("epg_stare") == "lucreaza" else _t(p.get("epg_mesaj") or "")
		if p.get("epg_evenimente") and p.get("epg_stare") != "lucreaza":
			p["epg_text"] += " " + _t(N_("%d programe.")) % p["epg_evenimente"]
		surse.append(p)
	rez = {"result": True, "surse": surse, "lucreaza": L.inLucru() or any(p.get("epg_stare") == "lucreaza" for p in surse),
		"plafon": S.MAX_CANALE, "pot_adauga": len(surse) < S.MAX_SURSE, "mac_receptor": S.macReceptor(),
		"maxim_surse": S.MAX_SURSE, "numar_surse": len(surse)}
	if any(p["fel"] == "demo" for p in surse):
		rez["demo"] = C.citesteDemo() or {}
	return rez


def rezultatIptv(arg, I=None):
	"""Ce s-a intamplat cu o sursa ceruta din pagina (dupa ce nu se mai lucreaza la ea)."""
	S, C, L = _iptv(I)
	sid = arg.get("id", "")
	mesaj = L.ultimulMesaj(sid)
	s = S.sursa(sid)
	return {"result": not mesaj and s is not None, "lucreaza": L.inLucru(sid), "message": _t(mesaj) if mesaj else "",
		"sursa": S.publica(s) if s else None}


def stareListeM3u(F=None):
	"""GET /api/iptv?liste_m3u=1: preluarea automata a listelor M3U gasite si cererile in asteptare (space71, 19.11.2026).
	Numai memorie (Components/HdsIptvFisier.stareListe): numele listei, fara cale sau adresa."""
	if F is None:
		from Components import HdsIptvFisier as F
	rez = {"result": True}
	rez.update(F.stareListe())
	return rez


def schimbaListeM3u(arg, F=None):
	"""POST /api/iptv-optiuni cu liste_m3u=1: automat=0/1 (aceeasi setare ca pe televizor) sau jeton + da=0/1 (raspunsul la o
	cerere). Raspunsul e numai memorie: verificarea fisierului se face pe firul de fundal al listelor."""
	if F is None:
		from Components import HdsIptvFisier as F
	if "automat" in arg and "jeton" not in arg:
		if arg["automat"] not in ("0", "1"):
			return {"result": False, "message": _t(N_("Alege Da sau Nu."))}
		F.seteazaPreluare(arg["automat"] == "1")
		rez = {"result": True}
	elif "jeton" in arg and "automat" not in arg and arg.get("da") in ("0", "1"):
		rez = F.raspunde(arg["jeton"], arg["da"] == "1")
	else:
		return {"result": False, "message": _t(N_("Alege Da sau Nu."))}
	rez.update(F.stareListe())
	return rez


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_), fara efect: textele se traduc la folosire."""
	return text


# XTP0 (0.8.0): "player" (4097/5001/5002) se alege si la adaugare, ca pe televizor (HdsIptvClient.verificaOptiuni)
CHEI_IPTV = ("fel", "nume", "adresa", "server", "utilizator", "parola", "portal", "mac", "user_agent", "referer", "x_user_agent", "stb_type",
	"player")


def macNouIptv():
	"""Propunere pentru formular; nu atinge sursele si nu cere nimic portalului."""
	from Components import HdsIptvSurse as S
	return {"result": True, "mac": S.macNouaStalker()}


def macIptv(arg, I=None):
	"""MAC-ul scris de om pentru un portal existent; ID-ul sursei ramane acelasi."""
	S, C, L = _iptv(I)
	s = S.sursa(arg.get("id", ""))
	if not s or s.get("fel") != "stalker":
		return {"result": False, "message": _t("Sursa aleasă nu mai e în listă. Pagina se încarcă din nou.")}
	sursa, eroare = C.verificaDate("stalker", dict(s, mac=arg.get("mac", "")), sursa_id=s["id"])
	if eroare:
		return {"result": False, "message": _t(eroare)}
	if L.adaugaSiCere(sursa) is None:
		return {"result": False, "message": S.textSursePline(_t)}
	rez = _cuMesaj(stareIptv(I), True, _t("Se verifică legătura cu serverul..."))
	rez["id"] = s["id"]
	return rez


def adaugaIptv(arg, din_adresa=(), I=None):
	"""POST /api/iptv-adauga. Parola si adresa M3U se iau numai din corp, niciodata din URL. Se intoarce imediat: lista o aduce firul de
	lucru, iar pagina urmareste rezultatul."""
	S, C, L = _iptv(I)
	fel = arg.get("fel", "")
	if fel == "demo":
		sursa = S.sursaDemo()
	else:
		date = dict((k, arg[k]) for k in CHEI_IPTV if k in arg and not (k in ("parola", "adresa") and k in din_adresa))
		sursa, eroare = C.verificaDate(fel, date)
		if eroare:
			return _cuMesaj(stareIptv(I), False, _t(eroare))
	if L.adaugaSiCere(sursa) is None:
		return _cuMesaj(stareIptv(I), False, S.textSursePline(_t))
	rez = _cuMesaj(stareIptv(I), True, _t("Se verifică legătura cu serverul..."))
	rez["id"] = sursa["id"]
	return rez


# fisierul ales in pagina, cel mult atatea caractere: o lista de canale obisnuita are cateva sute de KB (inainte 40 KB, cat
# incapea in corpul obisnuit de 64 KB, deci listele de canale nu treceau; CRF, TODO 15.11 02:20). Corpul cererii are limita lui
# (plugin.MAX_CORP_IPTV_FISIER: de trei ori atat, fiindca formularul codeaza octetii ca %XX). O lista mai mare merge pe stick sau
# prin FTP in /etc/enigma2 (HdsIptvFisier, cel mult MAX_PLAYLIST_COPIAT); pagina spune asta si nu mai trimite nimic.
MAX_FISIER = 4 * 1024 * 1024


def fisierIptv(arg, I=None):
	"""POST /api/iptv-fisier: adresele din fisierul ales in browser, ca la /etc/enigma2/iptv.txt pus prin FTP. Sursele noi intra in
	lista si firul de lucru le aduce canalele, ca la Adauga. Un fisier care e chiar o lista de canale (#EXTINF, sub MAX_FISIER) se pune
	in IPTV din copia lui de pe receptor (HdsIptvFisier.preiaPlaylistText, CRF, forum 1274)."""
	S, C, L = _iptv(I)
	if arg.get('tip') == 'transfer_bucata':
		from Components import HdsIptvTransfer as F
		return F.primesteBucata(arg, _t)
	from Components import HdsIptvTransfer as Transfer
	if arg.get("tip") in ("stalker", "surse", "transfer_lista") or Transfer._semnContainer(arg.get("text", ""), arg.get("nume", "")):
		F = Transfer
		p = F.citeste(arg.get("text", ""), arg.get("nume", ""))
		if arg.get("tip") == "transfer_lista":
			import json
			try:
				meta = arg.get("meta", "")
				if len(meta) > F.MAX_META:
					raise ValueError()
				F._verificaJson(meta)
				meta = json.loads(meta)
				if not isinstance(meta, dict) or len(p['surse']) != 1 or p['surse'][0].get('fel') != 'm3u' or p.get('eroare'):
					raise ValueError()
				s = F._curata(dict(meta, fel='m3u', continut=p['surse'][0]['continut']))
				import hashlib
				date = arg.get('text', '').encode('utf-8')
				if len(date) != meta.get('octeti') or hashlib.sha256(date).hexdigest() != meta.get('sha256'):
					raise ValueError()
				if not s:
					raise ValueError()
				p['surse'] = [s]
			except (ValueError, TypeError, RecursionError):
				p = dict(surse=[], rele=[], incomplete=[], neacceptate=[], eroare=F.T_CITIRE)
		if arg.get("completari"):
			p = F.completeaza(p, arg["completari"])
		try:
			rez = F.adauga(p) if arg.get("pas") == "adauga" else F.rezumat(p)
		except OSError:
			return {"result": False, "message": _t(N_("Sursele nu s-au putut salva. Verifică spațiul liber."))}
		raspuns = {"result": not rez.get("eroare"), "import_stalker": rez, "message": F.textRezumat(rez, _t),
			"incomplete": [{"rand": d["rand"], "indice": d.get("indice", i), "portal": not bool(d["portal"]), "mac": not bool(d["mac"])} for i, d in enumerate(p.get("incomplete", []))]}
		if arg.get('meta') and len(p['surse']) == 1:
			import hashlib
			raspuns['amprenta_transfer'] = hashlib.sha256(repr(F._identitate(p['surse'][0])).encode('utf-8')).hexdigest()
		return raspuns
	from Components import HdsIptvFisier as F
	text = arg.get("text") or ""
	nume = S.numeCurat(arg.get("nume") or "", "iptv.txt")
	if len(text) > MAX_FISIER:
		# o lista de canale mai mare decat pagina: acelasi sfat ca pe stick (numai scripturile ajung aici, pagina opreste inainte)
		mesaj = _t(F.T_PLAYLIST_PREA_MARE) % nume if F.ePlaylist(text) else _t(F.T_PREA_MARE)
		return _cuMesaj(stareIptv(I), False, mesaj)
	rez = F.preiaText(text, nume, verifica=C.verificaDate, adauga=L.adaugaSiCere, dosar=S.DOSAR, e_plin=lambda: S.textSursePline(_t),
		tine_minte=False)
	if not rez["mesaje"]:
		return _cuMesaj(stareIptv(I), False, _t(F.T_NIMIC))
	return _cuMesaj(stareIptv(I), bool(rez["adaugate"]), " ".join(rez["mesaje"]))


def exportaStalkerIptv():
	"""Export cerut explicit, numai din POST, fara stare privata in GET-ul paginii."""
	from Components import HdsIptvTransfer as F
	return {"result": True, "text": F.exporta(), "nume": "surse-iptv.json"}


def _exportaTransferWeb(request):
	"""Pregatire pe disc in fir separat, apoi transfer cu contrapresiune."""
	import os
	import tempfile
	from twisted.internet.threads import deferToThread
	from twisted.protocols.basic import FileSender
	from twisted.web.server import NOT_DONE_YET
	from Components import HdsIptvTransfer as F
	stare = {'inchis': False}
	def deconectat(esec):
		stare['inchis'] = True
		return None
	request.notifyFinish().addErrback(deconectat)
	def pregateste():
		os.makedirs(F.I.dosarListe(), mode=0o700, exist_ok=True)
		f = tempfile.TemporaryFile(mode='w+b', dir=F.I.dosarListe())
		try:
			F.scrieTransfer(f)
			return f
		except BaseException:
			f.close()
			raise
	def trimite(f):
		if stare['inchis']:
			f.close()
			return
		request.setHeader(b'content-type', b'application/octet-stream')
		request.setHeader(b'content-disposition', b'attachment; filename="surse-iptv.hdsiptv"')
		request.setHeader(b'content-length', str(os.fstat(f.fileno()).st_size).encode('ascii'))
		def termina(rez):
			f.close()
			if not stare['inchis']:
				request.finish()
			return None
		def intrerupt(rez):
			request.unregisterProducer()
			f.close()
			stare['inchis'] = True
			transport = getattr(request, 'transport', None)
			if transport is not None:
				transport.loseConnection()
			return None
		try:
			FileSender().beginFileTransfer(f, request).addCallbacks(termina, intrerupt)
		except BaseException:
			f.close()
			raise
	def esec(rez):
		if not stare['inchis']:
			import json
			request.setResponseCode(400)
			request.setHeader(b'content-type', b'application/json; charset=utf-8')
			request.write(json.dumps(dict(result=False, message=_t(F.T_LOCAL)), ensure_ascii=False).encode('utf-8'))
			request.finish()
		return None
	deferToThread(pregateste).addCallback(trimite).addErrback(esec)
	return NOT_DONE_YET


def actualizeazaIptv(arg, I=None):
	"""POST /api/iptv-actualizeaza: o sursa (id=) sau toate."""
	S, C, L = _iptv(I)
	sid = arg.get("id", "")
	if sid:
		if S.sursa(sid) is None:
			return _cuMesaj(stareIptv(I), False, _t("Sursa aleasă nu mai e în listă. Pagina se încarcă din nou."))
		L.cere(sid)
	else:
		L.cereToate()
	return _cuMesaj(stareIptv(I), True, _t("Se actualizează..."))


# 0.7.7 (FLM2, Eduard 16.11 11:01): butonul "Deschide" de pe o sursa din /iptv, perechea paginii sursei de pe televizor
# (Screens/IptvSetup.IptvCont): canalele, pe grupe, si pornirea lor pe televizor; filmele si serialele vin prin /api/vod si
# /api/vod-reda (HdsWebControl/filme_seriale_web.py, aceleasi ca in Filme si seriale)
PE_PAGINA_WEB = 300
_canale_web = {}     # sursa -> [semnul fisierului, None (se citeste) | grupele (HdsIptvSurse.grupeCanale)]


def _pornesteFir(lucru):
	import threading
	threading.Thread(target=lucru, name="IptvSursaCanaleWeb", daemon=True).start()


def _grupeWeb(S, s, fir=None):
	"""Grupele de canale ale sursei, citite pe un fir (fisierul poate avea 30000 de canale) si tinute minte cat nu se schimba
	fisierul sau grupele ascunse. -> lista sau None (inca se citeste)."""
	import os
	try:
		st = os.stat(os.path.join(S.DOSAR, "canale-%s.json" % s["id"]))
		semn = (st.st_mtime_ns, st.st_size, tuple(sorted(s.get("ascunse") or ())))
	except OSError:
		semn = None
	v = _canale_web.get(s["id"])
	if v is None or v[0] != semn:
		_canale_web.clear()          # o singura sursa in memorie
		v = _canale_web[s["id"]] = [semn, None]

		def lucru(v=v):
			try:
				v[1] = S.grupeCanale(s)
			except Exception as e:
				_jurnal("canalele sursei: %s" % type(e).__name__)
				v[1] = []
		(fir or _pornesteFir)(lucru)
	return v[1]


def canaleSursaIptv(arg, I=None, fir=None):
	"""GET /api/iptv-sursa-canale?id=<sursa>[&grupa=<numarul grupei>&de_la=<n>]: grupele sursei cu cate canale au, sau canalele
	unei grupe (cate PE_PAGINA_WEB: cheie si nume, fara adrese). Primul raspuns poate fi {"asteapta": true}."""
	S, C, L = _iptv(I)
	s = S.sursa(arg.get("id", ""))
	if s is None:
		return {"result": False, "message": _t(N_("Sursa aleasă nu mai e în listă. Pagina se încarcă din nou."))}
	if s.get("neconectata"):
		return {"result": True, "asteapta": True}
	if "neconectata" in s and not s.get("canale") and L.inLucru(s["id"]):
		return {"result": True, "asteapta": True}
	if "neconectata" in s and s.get("eroare") and not s.get("canale"):
		return {"result": False, "message": _t(s["eroare"])}
	grupe = _grupeWeb(S, s, fir)
	if grupe is None:
		return {"result": True, "asteapta": True}
	g = arg.get("grupa", "")
	if g == "":
		return {"result": True, "grupe": [{"nume": nume, "n": len(c), "text": _textCanale(len(c))} for nume, c in grupe]}
	if not g.isdigit() or int(g) >= len(grupe):
		return {"result": False, "message": _t(N_("Lista s-a schimbat. Deschide din nou sursa."))}
	de_la = int(arg.get("de_la", "0")) if arg.get("de_la", "0").isdigit() else 0
	nume, canale = grupe[int(g)]
	return {"result": True, "grupa": nume, "de_la": de_la, "toate": len(canale),
		"canale": [{"cheie": k, "nume": n} for k, n, _d in canale[de_la:de_la + PE_PAGINA_WEB]]}


def pornesteCanalSursaIptv(arg, I=None, nav=None):
	"""POST /api/iptv-sursa-porneste?id=<sursa>&cheie=<canal>: canalul porneste pe televizor (ca OK pe el in pagina sursei)."""
	S, C, L = _iptv(I)
	sid, cheie = arg.get("id", ""), arg.get("cheie", "")
	v = _canale_web.get(sid)
	gasit = None
	for _g, canale in ((v[1] or []) if v else []):
		gasit = next((c for c in canale if c[0] == cheie), None)
		if gasit:
			break
	if gasit is None:
		return {"result": False, "message": _t(N_("Lista s-a schimbat. Deschide din nou sursa."))}
	try:
		from enigma import eServiceReference
		if nav is None:
			import NavigationInstance
			nav = NavigationInstance.instance
		r = eServiceReference(S.refCanal(sid, gasit[0], gasit[2]))
		r.setName(gasit[1])
		nav.playService(r)
	except Exception as e:
		_jurnal("canalul sursei, pornirea: %s" % type(e).__name__)
		return {"result": False, "message": _t(N_("Canalul nu a pornit. Încearcă din nou."))}
	return {"result": True, "message": _t(N_("Canalul pornește pe televizor."))}


def stergeIptv(arg, I=None):
	"""POST /api/iptv-sterge?id=<sursa>: o sursa scoasa, in doi pasi (tinta = identificatorul ei)."""
	S, C, L = _iptv(I)
	sid = arg.get("id", "")
	s = S.sursa(sid)
	if s is None:
		return _cuMesaj(stareIptv(I), False, _t("Sursa aleasă nu mai e în listă. Pagina se încarcă din nou."))

	def fapta():
		L.stergeSiReface(sid)
		return _cuMesaj(stareIptv(I), True, _t("Sursa a fost ștearsă."))

	return _doiPasi(arg, "iptv-sterge", sid, _t("Ștergi sursa?"), _t("Da, șterge"),
		[s.get("nume") or "", _t("Canalele ei dispar de la rândul IPTV. Cele puse de tine în Favorite rămân, dar nu mai pornesc.")], fapta)


def grupeIptv(arg, I=None):
	"""GET /api/iptv-grupe?id=<sursa>: tarile si grupele, cu ce se vede; aceeasi lista ca ecranul Grupele de pe televizor."""
	S, C, L = _iptv(I)
	s = S.sursa(arg.get("id", ""))
	if not s:
		return {"result": False, "message": _t("Sursa aleasă nu mai e în listă. Pagina se încarcă din nou.")}
	taiate, canale = int(s.get("taiate") or 0), int(s.get("canale") or 0)
	randuri = S.randuriGrupe(s)
	for r in randuri:
		r["text"] = u" \u00b7 ".join([r["nume"]] + ([_t(S.T_GRUPE_N) % r["grupe"]] if r.get("grupe") else []) + [_textCanale(r["canale"])] +
			([_t(S.T_GRUPE_PARTE)] if r.get("partial") else []))
	ghid = _t(S.T_GRUPE_TAIATE) % {"vazute": canale, "toate": canale + taiate} if taiate else _t(S.T_GRUPE_GHID)
	return {"result": True, "randuri": randuri, "ghid": ghid}


def schimbaGrupeIptv(arg, I=None):
	"""POST /api/iptv-grupe: id=<sursa> si cheie=<randul> (schimba bifa) sau tot=ascunde|arata. Se aplica pe loc, ca pe televizor."""
	S, C, L = _iptv(I)
	s = S.sursa(arg.get("id", ""))
	if not s:
		return {"result": False, "message": _t("Sursa aleasă nu mai e în listă. Pagina se încarcă din nou.")}
	catalog = S.citesteCatalog(s)
	tot = arg.get("tot", "")
	if tot == "ascunde":
		ascunse = S.ascundeTot(catalog)
	elif tot == "arata":
		ascunse = set()
	elif arg.get("cheie"):
		ascunse = S.comutaGrupa(s.get("ascunse"), catalog, arg["cheie"])
	else:
		return {"result": False, "message": _t("Eroare pe receptor.")}
	L.aplicaAscunse(s["id"], ascunse)
	return grupeIptv({"id": s["id"]}, I)


def optiuniIptv(arg, I=None):
	S, C, L = _iptv(I)
	eroare = C.salveazaOptiuni(arg.get("id", ""), arg)
	if eroare:
		return {"result": False, "message": _t(eroare)}
	return _cuMesaj(stareIptv(I), True, _t(N_("Setările sursei au fost salvate.")))


def anteteIptv(arg, din_adresa=(), I=None):
	"""Antetele sunt numai de scris: nu se intorc in sursa publica."""
	S, C, L = _iptv(I)
	s = S.sursa(arg.get("id", ""))
	if not s or s.get("fel") == "demo":
		return {"result": False, "message": _t("Sursa aleasă nu mai e în listă. Pagina se încarcă din nou.")}
	if any(k in din_adresa for k in ("user_agent", "referer", "x_user_agent", "stb_type")):
		return {"result": False, "message": _t(N_("Trimite antetele numai din formular."))}
	date = dict(s, user_agent=arg.get("user_agent", ""), referer=arg.get("referer", ""))
	for k in ("x_user_agent", "stb_type"):
		if k in arg:
			date[k] = arg[k]
	if s["fel"] == "stalker":
		sursa, eroare = C.verificaDate(s["fel"], date, sursa_id=s["id"])
	else:
		sursa, eroare = C.verificaDate(s["fel"], date)
	if eroare:
		return {"result": False, "message": _t(eroare)}
	if L.adaugaSiCere(sursa) is None:
		return {"result": False, "message": S.textSursePline(_t)}
	return _cuMesaj(stareIptv(I), True, _t(N_("Antetele au fost salvate. Se actualizează sursa...")))


def _seriale(Seriale=None):
	if Seriale is not None:
		return Seriale
	from Components import HdsIptvSeriale
	return HdsIptvSeriale


def stareSeriale(arg, Seriale=None):
	S = _seriale(Seriale)
	cheie = arg.get("cerere")
	if not cheie:
		cheie = S.cere(arg.get("id", ""), arg.get("serial", ""), arg.get("sezon", ""), arg.get("pagina", 0), arg.get("cauta", ""))
	if not cheie:
		return {"result": False, "message": _t(S.E_OCUPAT)}
	rez = S.rezultat(cheie)
	if rez.get("message"):
		rez["message"] = _t(rez["message"])
	return rez


def redaSerial(arg, Seriale=None, P=None):
	S = _seriale(Seriale)
	ref = S.episodDinPagina(arg.get("cerere", ""), arg.get("episod", ""))
	if not ref:
		return {"result": False, "message": _t(S.E_EXPIRAT)}
	merge, _detaliu, _cod = _plugin(P).zapReferinta(ref)
	return {"result": bool(merge), "message": _t(N_("Episodul pornește pe televizor.")) if merge else _t(N_("Episodul nu a pornit. Încearcă din nou."))}


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
			intrebare = _t("Deconectezi toate browserele și telefoanele? Cu parola pusă, fiecare o cere din nou.")
		else:
			intrebare = _t("Deconectezi toate browserele? Cu parola pusă, fiecare o cere din nou.")

		def deconecteaza():
			numar = P.obtineAsociere().deconecteazaToate()
			_jurnal("browsere deconectate din web: %d" % numar)
			return _cuMesaj(stareInterfataWeb(P), True, _t("Deconectate: %d.") % numar)

		return _doiPasi(arg, "web-deconecteaza", "", intrebare, _t("Da, deconectează"),
			[_t("Dacă acest browser a intrat cu parolă, o va cere din nou.")], deconecteaza)
	if fapta == "cheie":
		def cheie():
			numar = cheieNouaPanou(P.config, configfile, P.obtineAsociere(), secret_cerere)
			_jurnal("cheie noua pentru panoul web, din web; aparate deconectate: %d" % numar)
			# pagina se incarca din nou: browserul intrat liber primeste tokenul CSRF facut din cheia noua; cel intrat cu parola
			# isi pastreaza cookie-ul
			rez = _cuMesaj(stareInterfataWeb(P), True, _t("Cheia nouă pentru panoul web e făcută. Pagina se încarcă din nou."))
			rez["reincarca"] = True
			return rez

		return _doiPasi(arg, "web-cheie", "", _t("Faci o cheie nouă pentru panoul web? Cheia veche nu mai merge, iar browserele "
			"intrate cu parolă o cer din nou."), _t("Da, fă cheia nouă"),
			[_t("Acest browser rămâne conectat. Scripturile care folosesc cheia veche nu mai merg până primesc cheia nouă."),
				_t("Browserele intrate liber din rețeaua locală, și această pagină dacă ai intrat liber, trebuie să "
				"încarce din nou pagina după schimbare.")], cheie)
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
					_jurnal("%s: %s" % (functie.__name__, type(eroare).__name__))
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
					_jurnal("%s: %s" % (functie.__name__, type(eroare).__name__))
					return self._eroare(request, _t("Eroare pe receptor."), 500)

			def render_GET(self, request):
				return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST
		return Schimbare()

	CHEI_PASI = ("pas", "cod", "index")

	def dvbi(request):
		return stareDvbi(D, cale_dvbi)

	def dvbi_seteaza(request):
		return seteazaDvbi(_argumente(request, ("activ", "predefinita", "bifata", "adauga_url", "tara", "regiune", "lista",
			"rezerva", "toate_tarile", "liste_proba", "in_lista"), 1024), D, cale_dvbi)

	def dvbi_incearca(request):
		return incearcaDvbi(D, cale_dvbi)

	def dvbi_registre(request):
		return registreDvbi(D, cale_dvbi)

	def dvbi_sterge(request):
		return stergeDvbi(_argumente(request, CHEI_PASI), D, cale_dvbi)

	def dvbi_reincarca(request):
		return reincarcaDvbi(D, cale_dvbi)

	def dvbi_cauta(request):
		return cautaDvbi(D, cale_dvbi)

	def mabr(request):
		return stareMabr(S, cale_mabr)

	def mabr_seteaza(request):
		return seteazaMabr(_argumente(request, ("activ", "autodiscover", "adauga"), 64), S, cale_mabr)

	def mabr_sterge(request):
		return stergeMabr(_argumente(request, CHEI_PASI), S, cale_mabr)

	def mabr_cauta(request):
		return cautaMabr(S, cale_mabr)

	def iptv(request):
		# GET /api/iptv?liste_m3u=1: numai preluarea listelor M3U gasite (space71), din memorie
		if _argumente(request, ("liste_m3u",), 1).get("liste_m3u") == "1":
			return stareListeM3u()
		rez = stareIptv(I)
		sid = _argumente(request, ("id",)).get("id")
		if sid:
			rez["rezultat"] = rezultatIptv({"id": sid}, I)
		return rez

	def iptv_grupe(request):
		return grupeIptv(_argumente(request, ("id",)), I)

	def iptv_cont(request):
		return stareContIptv(_argumente(request, ("id",)), I)

	def iptv_arhiva(request):
		return arhivaIptv({})

	def iptv_arhiva_porneste(request):
		return pornesteArhivaIptv(_argumente(request, ("canal", "i"), 64))

	def iptv_grupe_schimba(request):
		return schimbaGrupeIptv(_argumente(request, ("id", "cheie", "tot"), 512), I)

	def iptv_adauga(request):
		return adaugaIptv(_argumente(request, CHEI_IPTV, 2048), _dinAdresa(request), I)

	def iptv_actualizeaza(request):
		return actualizeazaIptv(_argumente(request, ("id",)), I)

	def iptv_mac(request):
		return macIptv(_argumente(request, ("id", "mac"), 64), I)

	def iptv_fisier(request):
		# Continutul fisierului nu se accepta din URL.
		if getattr(request, "method", b"POST") != b"POST" or {"text", "completari", "meta", "jeton", "pozitie"}.intersection(_dinAdresa(request)):
			return {"result": False, "message": _t(N_("Alege fișierul din pagină."))}
		arg = _argumente(request, ("text", "nume", "tip", "pas", "completari", "meta", "jeton", "pozitie"), MAX_FISIER + 1)
		if arg.get('tip') == 'transfer_lista':
			# Hashul priveste exact octetii, inclusiv newline-ul final.
			args = getattr(request, 'args', {}) or {}
			text = (args.get(b'text') or args.get('text') or [b''])[0]
			try:
				arg['text'] = text.decode('utf-8') if isinstance(text, bytes) else str(text)
			except UnicodeError:
				from Components import HdsIptvTransfer as F
				return {'result': False, 'message': _t(F.T_CITIRE)}
		return fisierIptv(arg, I)

	class FisierIptv(baza):
		schimbaCeva = True
		_ocupat = False

		def render_POST(self, request):
			args = getattr(request, 'args', {}) or {}
			text = (args.get(b'text') or args.get('text') or [b''])[0]
			tip = (args.get(b'tip') or args.get('tip') or [b''])[0]
			if {'text', 'completari', 'meta', 'jeton', 'pozitie'}.intersection(_dinAdresa(request)):
				return self._raspunde(request, dict(result=False, message=_t(N_('Alege fișierul din pagină.'))))
			if getattr(request, 'method', b'POST') != b'POST' or tip not in ('surse', 'stalker', 'transfer_lista', 'transfer_bucata', b'surse', b'stalker', b'transfer_lista', b'transfer_bucata'):
				return _schimbare(iptv_fisier).render_POST(request)
			from twisted.internet.threads import deferToThread
			from twisted.web.server import NOT_DONE_YET
			if FisierIptv._ocupat:
				return self._raspunde(request, dict(result=False, ocupat=True, message=_t('Se încarcă')))
			FisierIptv._ocupat = True
			stare = {'inchis': False}
			def inchide(esec):
				stare['inchis'] = True
				return None
			request.notifyFinish().addErrback(inchide)
			def gata(rez):
				FisierIptv._ocupat = False
				if not stare['inchis']:
					request.write(self._raspunde(request, rez))
					request.finish()
			def esec(rez):
				FisierIptv._ocupat = False
				if not stare['inchis']:
					request.write(self._eroare(request, _t('Eroare pe receptor.'), 500))
					request.finish()
				return None
			deferToThread(iptv_fisier, request).addCallback(gata).addErrback(esec)
			return NOT_DONE_YET

		def render_GET(self, request):
			return self.render_POST(request)

	class ExportStalker(baza):
		schimbaCeva = True
		_ocupat = False

		def render_POST(self, request):
			request.setHeader(b"Cache-Control", b"no-store")
			if _argumente(request, ("format",), 16).get("format") == "transfer":
				return _exportaTransferWeb(request)
			from twisted.internet.threads import deferToThread
			from twisted.web.server import NOT_DONE_YET
			if ExportStalker._ocupat:
				return self._raspunde(request, dict(result=False, ocupat=True, message=_t('Se încarcă')))
			ExportStalker._ocupat = True
			stare = {'inchis': False}
			def inchide(esec):
				stare['inchis'] = True
				return None
			request.notifyFinish().addErrback(inchide)
			def gata(rez):
				ExportStalker._ocupat = False
				if not stare['inchis']:
					request.write(self._raspunde(request, rez))
					request.finish()
			def esec(rez):
				from Components import HdsIptvTransfer as F
				ExportStalker._ocupat = False
				if not stare['inchis']:
					request.write(self._eroare(request, _t(F.T_SURSE_CITIRE)))
					request.finish()
				return None
			deferToThread(exportaStalkerIptv).addCallback(gata).addErrback(esec)
			return NOT_DONE_YET

		def render_GET(self, request):
			return self._eroare(request, _t(N_("Exportul se cere din pagină.")), 405)

	def iptv_sterge(request):
		return stergeIptv(_argumente(request, ("id", "pas", "cod")), I)

	def sursa_antete(request):
		return anteteIptv(_argumente(request, ("id", "user_agent", "referer", "x_user_agent", "stb_type"), 2048), _dinAdresa(request), I)

	def iptv_optiuni(request):
		# POST /api/iptv-optiuni cu liste_m3u=1: setarea Da/Nu sau raspunsul la o cerere, numai din pagina (nu din adresa)
		if _argumente(request, ("liste_m3u",), 1).get("liste_m3u") == "1":
			if {"automat", "jeton", "da"}.intersection(_dinAdresa(request)):
				return {"result": False, "message": _t(N_("Trimite răspunsul din pagină."))}
			return schimbaListeM3u(_argumente(request, ("automat", "jeton", "da"), 64))
		return optiuniIptv(_argumente(request, ("id", "player", "piconuri")), I)

	def iptv_sursa_canale(request):
		return canaleSursaIptv(_argumente(request, ("id", "grupa", "de_la")), I)

	def iptv_sursa_porneste(request):
		return pornesteCanalSursaIptv(_argumente(request, ("id", "cheie")), I)

	def seriale(request):
		return stareSeriale(_argumente(request, ("id", "serial", "sezon", "pagina", "cauta", "cerere"), 128))

	def seriale_reda(request):
		return redaSerial(_argumente(request, ("cerere", "episod"), 64), P=P)

	def interfata_web(request):
		return stareInterfataWeb(P)

	def iptv_4k(request):
		return stareIptv4k()

	def iptv_4k_porneste(request):
		return pornesteIptv4k()

	def iptv_4k_opreste(request):
		return opresteIptv4k()

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
		b"dvb-i-cauta": _schimbare(dvbi_cauta),
		b"dvb-i-incearca": _schimbare(dvbi_incearca),
		b"dvb-i-registre": _schimbare(dvbi_registre),
		b"mabr": _citire(mabr),
		b"mabr-seteaza": _schimbare(mabr_seteaza),
		b"mabr-sterge": _schimbare(mabr_sterge, True),
		b"mabr-cauta": _schimbare(mabr_cauta),
		b"iptv": _citire(iptv),
		b"iptv-grupe": _citire(iptv_grupe),
		b"iptv-grupe-schimba": _schimbare(iptv_grupe_schimba),
		b"iptv-adauga": _schimbare(iptv_adauga),
		b"iptv-mac": _schimbare(iptv_mac),
		b"iptv-mac-nou": _schimbare(lambda request: macNouIptv()),
		b"iptv-actualizeaza": _schimbare(iptv_actualizeaza),
		b"iptv-fisier": FisierIptv(),
		b"iptv-stalker-export": ExportStalker(),
		b"iptv-sterge": _schimbare(iptv_sterge, True),
		b"sursa-antete": _schimbare(sursa_antete),
		b"iptv-optiuni": _schimbare(iptv_optiuni),
		b"iptv-sursa-canale": _citire(iptv_sursa_canale),
		b"iptv-sursa-porneste": _schimbare(iptv_sursa_porneste),
		b"seriale": _citire(seriale),
		b"seriale-reda": _schimbare(seriale_reda),
		b"interfata-web-detalii": _citire(interfata_web),
		b"iptv-4k": _citire(iptv_4k),
		b"iptv-4k-porneste": _schimbare(iptv_4k_porneste),
		b"iptv-4k-opreste": _schimbare(iptv_4k_opreste),
		b"iptv-cont": _citire(iptv_cont),
		b"iptv-arhiva": _citire(iptv_arhiva),
		b"iptv-arhiva-porneste": _schimbare(iptv_arhiva_porneste),
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
		b"iptv-4k": _pagina(pagina_iptv_4k),
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
	return _sablon(_traducePagina(PAGINA_IPTV), stil, config_pagina, "hds_iptv_setup").replace("__MAX_FISIER__", str(MAX_FISIER))


def pagina_iptv_4k(stil, config_pagina):
	return _sablon(_traducePagina(PAGINA_IPTV_4K), stil, config_pagina, "hds_iptv_4k")


# ------------------------------------------------------------------ cautarea canalelor 4K reale (pereche: Screens/HdsIptv4K.py)
def stareIptv4k(K=None, I=None):
	"""Starea cautarii, textul de sus (acelasi ca pe televizor) si canalele verificate, fara adrese (numai numele si ce trimit)."""
	if K is None:
		from Components import HdsIptv4K as K
	if I is None:
		from Components import HdsIptvSurse as I
	st, rez = K.stare(), K.rezultate()
	try:
		from Screens.HdsIptv4K import textStare
		text = textStare(st, rez)
	except Exception:
		text = ""
	try:
		from Screens.HdsIptv4K import notaFullHd
		nota_full_hd = notaFullHd()
	except Exception:
		nota_full_hd = ""
	canale = []
	for v in sorted(rez.values(), key=lambda v: (v[6] if len(v) > 6 else "")):
		if len(v) > 6 and v[0]:
			canale.append({"nume": v[6], "w": v[0], "h": v[1], "cod": v[2], "hdr": v[3], "e4k": v[0] >= K.LATIME_4K,
				"eticheta": K.eticheta4k(v)})
	return {"result": True, "stare": st, "text": text, "canale": canale, "surse": bool(I.areSurse()),
		"pornita": I.optiune("4k"), "mesaj_stare": _(st["mesaj"]) if st.get("mesaj") else "",
		"nota_full_hd": nota_full_hd}


def pornesteIptv4k(K=None, I=None):
	if K is None:
		from Components import HdsIptv4K as K
	if I is None:
		from Components import HdsIptvSurse as I
	if not I.areSurse():
		return {"result": False, "message": _("Nu ai nicio sursă de televiziune prin internet.")}
	if K.omulSeUita():
		return {"result": False, "message": _(K.T_OPRITA_PRIVIRE)}
	# o cautare neterminata (oprita, pauza, repornire) continua de unde a ramas; altfel toate canalele de la capat
	K.porneste(tot=not K.deContinuat())
	rez = stareIptv4k(K, I)
	rez["message"] = _("Căutarea a pornit.")
	return rez


def opresteIptv4k(K=None, I=None):
	if K is None:
		from Components import HdsIptv4K as K
	K.opreste()
	rez = stareIptv4k(K, I)
	rez["message"] = _("Căutarea se oprește după canalul de acum.")
	return rez


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
  .sursa-actiuni{display:flex;flex-wrap:wrap;gap:8px;justify-content:flex-end;}
  #contTitlu,#contNota,#anteteTitlu{overflow-wrap:anywhere;}
  #contLista .lista-rand>span{white-space:normal;overflow-wrap:anywhere;}
  @media(max-width:640px){#surse>.lista-rand{align-items:flex-start;flex-wrap:wrap;}.sursa-actiuni{justify-content:flex-start;}}
  .bifa{display:flex;align-items:center;gap:12px;min-height:44px;padding:4px 0;border-bottom:1px solid var(--bordura);cursor:pointer;}
  .bifa:last-child{border-bottom:0;}
  .bifa span{overflow-wrap:anywhere;}
  .rand input[type=text],.rand input[type=url],.rand input[type=number]{width:100%;}
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
  .dvbi-lista small.dvbi-nu,.dvbi-nu{color:var(--eroare);}
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
      <h2>Liste din toate țările</h2>
      <div class="rand"><label for="toate_tarile">Liste din toate țările, după cele ale țării tale</label>
        <select id="toate_tarile"><option value="1">Da</option><option value="0">Nu</option></select></div>
      <p class="nota">După listele țării tale vin cele ale celorlalte țări, grupate pe țări: canalele merg dacă furnizorul le lasă și din țara ta.</p>
      <div class="rand"><label for="liste_proba">Și listele de probă</label>
        <select id="liste_proba"><option value="1">Da</option><option value="0">Nu</option></select></div>
      <p class="nota">Listele de probă ale registrelor, din toate țările, intră și ele: canalele lor pot să nu meargă.</p>
      <ul id="listeAlteTari"></ul>
    </section>
    <section class="card">
      <h2>Trecere pe internet</h2>
      <div class="rand"><label for="rezerva">Trecere singură pe internet când satelitul nu se recepționează</label>
        <select id="rezerva"><option value="1">Da</option><option value="0">Nu</option></select></div>
      <p class="nota">Canalul de satelit care are și adresă de internet în listele DVB-I trece singur pe internet când satelitul nu se recepționează și se întoarce pe satelit când semnalul revine.</p>
      <p class="nota">Aceeași alegere se găsește în Meniu > Setări > Setări listă de canale: „Când canalul nu pornește, treci singur pe sursa DVB-I a postului”. Este pornită din fabrică și independentă de trecerea pe alt canal cu același nume.</p>
      <p><a href="/setari?id=hds_lista_canale">Setări listă de canale</a></p>
    </section>
    <section class="card" id="cardListe">
      <h2>Listele țării</h2>
      <div id="listeTarii"></div>
      <p class="nota">Toate listele țării sunt bifate singure, și cele de probă cât timp sunt pornite listele de probă; bifele rămân și când schimbi țara.</p>
    </section>
    <section class="card" id="cardReincarcare">
      <h2>Reîncărcare</h2>
      <p class="intrebare" id="reincarcareText"></p>
      <div class="butoane"><button type="button" class="principal" id="reincarca">Reîncarcă acum</button></div>
      <p class="nota">Descarcă acum listele alese; canalele apar în lista de canale, în buchetul Canale de pe internet (DVB-I).</p>
      <div class="rand"><label for="in_lista">Arată lista în lista de canale</label>
        <select id="in_lista"><option value="1">Da</option><option value="0">Nu</option></select></div>
      <p class="nota">Cu Nu, lista Canale de pe internet (DVB-I) iese din lista de canale și nu mai revine singură.</p>
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
    <p class="nota">Pe televizor, ALBASTRU deschide direct tastatura.</p>
  </details>
  <p class="nota">Aceleași setări sunt pe televizor, în __DRUM_MENIU__.</p>
</div>
""" + _COADA + """var DATE = "", PORNIT_SINGUR = false, CEAS = null;
var STARI = {"merge": ["Merge", "bine"], "oprit_tara": ["Oprit pentru țara ta", "chihlimbar"],
  "adresa_moarta": ["Adresă moartă", "rau"], "nu_raspunde": ["Nu răspunde", "slab"], "drm": ["Protejat (DRM)", "rau"], "": ["Neîncercat", "slab gol"]};
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
    if(x.nu_raspunde){ var nr = document.createElement("small"); nr.className = "dvbi-nu"; nr.textContent = x.nu_raspunde; s.appendChild(nr); }
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
  [["merge", "merg"], ["oprit_tara", "oprite pentru țara ta"], ["adresa_moarta", "adrese moarte"], ["nu_raspunde", "fără răspuns"], ["drm", "protejate (DRM)"], ["", "neîncercate"]].forEach(function(k){
    if(n[k[0]]){ p.push(insigna(n[k[0]] + " " + k[1], STARI[k[0]][1])); }
  });
  if(d.ascunse){ p.push(insigna(d.ascunse + " " + "ascunse din lista de canale până merg din nou", "slab")); }
  if(d.scoase){ p.push(insigna(d.scoase + " " + "scoase din liste: clipuri și imagini de probă", "slab")); }
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
    var stare = document.createElement("span"); stare.className = "dvbi-st"; stare.appendChild(insigna((x.eticheta || st[0]) + (x.cod && x.stare !== "merge" && x.stare !== "drm" ? " (" + x.cod + ")" : ""), st[1]));
    if(x.ascuns){ stare.appendChild(insigna("nu e în lista de canale", "slab gol")); }
    r.appendChild(stare);
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
  if(document.activeElement !== $("toate_tarile")){ $("toate_tarile").value = d.toate_tarile === false ? "0" : "1"; }
  if(document.activeElement !== $("liste_proba")){ $("liste_proba").value = d.liste_proba === false ? "0" : "1"; }
  if(document.activeElement !== $("in_lista")){ $("in_lista").value = d.in_lista === false ? "0" : "1"; }
  var ua = $("listeAlteTari"); ua.textContent = "";
  (d.liste_alte_tari || []).forEach(function(l){ var li = document.createElement("li"); li.textContent = (l.tara_nume ? l.tara_nume + ": " : "") + (l.lista || l.adresa) + (l.canale !== null && l.canale !== undefined ? " · " + l.canale : "") + (l.nu_raspunde ? " · " + l.nu_raspunde : ""); if(l.nu_raspunde){ li.className = "dvbi-nu"; } ua.appendChild(li); });
  var r = d.reincarcare || {};
  $("reincarcareText").textContent = r.mesaj || "Listele se reîncarcă singure din oră în oră cât timp receptorul e pornit.";
  $("reincarcareText").classList.toggle("eroare", !!(r.gata && !r.succes));
  $("reincarca").disabled = !!r.in_curs;
  var lucreaza = !!(r.in_curs || (d.incercare && d.incercare.in_curs) || (d.registre && d.registre.in_curs));
  if(lucreaza && !CEAS){ CEAS = setInterval(citeste, 1500); }
  if(!lucreaza && CEAS){ clearInterval(CEAS); CEAS = null; }
  arataTara(d); arataCanale(d);
  var semn = JSON.stringify([d.activ, d.predefinite, d.url_uri, d.liste_tarii, d.adrese_nu_raspund]);
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
  var nuR = d.adrese_nu_raspund || {};
  var a = (d.url_uri || []).map(function(u, i){
    return rand(nuR[u] ? u + " · " + nuR[u] : u, "Șterge", function(){ var q = new URLSearchParams(); q.set("index", String(i)); cuConfirmare("/api/dvb-i-sterge", q, dupa); });
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
["activ", "rezerva", "toate_tarile", "liste_proba", "in_lista", "tara", "regiune"].forEach(function(id){
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
  "adresa_moarta": "Adresa nu mai răspunde", "nu_raspunde": "Nu a răspuns la ultima încercare", "drm": "Canal protejat (DRM)", "": "Neîncercat încă din casa receptorului"};
function nuMerge(text){ $("nuMerge").textContent = text; $("nuMerge").classList.remove("ascuns"); }
function arataCanal(c){
  document.title = c.nume + " · DVB-I";
  $("titlu").textContent = c.nume;
  $("stareCanal").textContent = (STARI[c.stare] || STARI[""]) + (c.cod && c.stare !== "merge" && c.stare !== "drm" ? " (cod " + c.cod + ")" : "") + ".";
  $("adresaFlux").value = c.url;
  // adresa vine dintr-o lista din internet: numai adrese de flux, ca un javascript: din lista sa nu ruleze in pagina receptorului
  if(/^(https?|rtsp|rtmp|mms|udp):/i.test(c.url)){ $("deschide").href = c.url; } else { $("deschide").classList.add("ascuns"); }
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


PAGINA_IPTV = "<!DOCTYPE html>" + _CAP + "IPTV" + _STIL + """<h1>IPTV</h1>
<p class="mesaj" id="incarcare">Se citesc setările...</p>
<div id="continut" class="ascuns">
  <section class="card">
    <h2>Listele și conturile tale</h2>
    <div id="surse"></div>
    <p class="nota">Canalele apar singure în lista de canale, la Sateliți, pe rândul IPTV. Le poți pune în Favorite și în orice buchet, ca pe celelalte.</p>
    <div class="butoane"><button type="button" id="actualizeaza">Actualizează toate</button></div>
  </section>
  <section class="card ascuns" id="cardArhiva">
    <h2>Emisiunile trecute</h2>
    <p class="nota" id="arhivaNota"></p>
    <div id="arhivaLista" style="max-height:60vh;overflow:auto"></div>
    <p class="nota">Pentru alt canal: pornește-l pe televizor, apoi apasă Reîncarcă. Pe televizor: MENU pe canal în lista de canale, apoi Emisiunile trecute.</p>
    <div class="butoane"><button type="button" id="arhivaReincarca">Reîncarcă</button></div>
  </section>
  <section class="card">
    <h2>Adaugă ce ți-a dat furnizorul</h2>
    <div class="rand"><label for="fel">Ce ai primit</label>
      <select id="fel"><option value="m3u">Playlist: o adresă sau un fișier de pe stick</option><option value="xtream">Cont: server, utilizator și parolă</option><option value="stalker">Portal: adresa portalului și adresa MAC</option><option value="demo">Listă demo: canale gratuite care permit asta</option></select></div>
    <div class="rand camp" data-fel="m3u"><label for="adresa">Adresa listei</label>
      <input type="text" inputmode="url" id="adresa" data-hds-secret="1" maxlength="2048" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="http://"></div>
    <div class="rand camp" data-fel="xtream"><label for="server">Server</label>
      <input type="text" id="server" maxlength="512" autocomplete="off" placeholder="http://"></div>
    <div class="rand camp" data-fel="xtream"><label for="utilizator">Utilizator</label>
      <input type="text" id="utilizator" maxlength="512" autocomplete="off"></div>
    <div class="rand camp" data-fel="xtream"><label for="parola">Parolă</label>
      <input type="text" id="parola" maxlength="512" autocomplete="off" autocapitalize="off" spellcheck="false"></div>
    <div class="rand camp" data-fel="stalker"><label for="portal">Adresa portalului</label>
      <input type="text" id="portal" maxlength="512" autocomplete="off" placeholder="http://"></div>
    <div class="rand camp" data-fel="stalker"><label for="mac">Adresa MAC</label>
      <input type="text" id="mac" maxlength="64" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="00:1A:79:12:34:56"></div>
    <p class="camp nota" data-fel="stalker">Pentru un abonament legat de alt receptor, scrie aici adresa MAC de pe acela. Unii furnizori nu permit două receptoare pornite în același timp cu aceeași adresă.</p>
    <div class="camp" data-fel="stalker"><button type="button" id="macFa">Fă o adresă MAC</button>
      <p class="nota">Adresa nouă trebuie dată furnizorului. Pentru un cont mutat de pe alt receptor, scrie adresa de acolo. Se păstrează numai la Salvează.</p>
      <p id="macVechi" class="nota"></p></div>
    <div class="rand" id="rNume"><label for="nume">Nume (opțional)</label>
      <input type="text" id="nume" maxlength="100" autocomplete="off"></div>
    <div class="rand" id="rPlayer"><label for="playerNou">Player în buchete</label><select id="playerNou"><option value="4097">4097 (implicit)</option><option value="5001">5001 (gstreamer)</option><option value="5002">5002 (exteplayer3)</option></select></div>
    <div class="rand" id="rAgent"><label for="user_agent">Agent utilizator (opțional)</label>
      <input type="text" id="user_agent" maxlength="2048" autocomplete="off"></div>
    <div class="rand" id="rReferer"><label for="referer">Referer (opțional)</label>
      <input type="text" id="referer" maxlength="2048" autocomplete="off"></div>
    <div class="rand camp" data-fel="stalker"><label for="x_user_agent">X-User-Agent (opțional)</label><input type="text" id="x_user_agent" maxlength="2048" autocomplete="off"></div>
    <div class="rand camp" data-fel="stalker"><label for="stb_type">Tip decodor (opțional)</label><input type="text" id="stb_type" maxlength="2048" autocomplete="off"></div>
    <p class="nota">Agent utilizator și Referer: goale folosesc valorile implicite.</p>
    <div class="butoane"><button type="button" class="principal" id="adauga">Adaugă</button></div>
    <p class="nota">Parola se vede și după salvare. Dacă adaugi din nou același cont cu altă parolă, canalele din Favorite rămân.</p>
  </section>
  <section class="card">
    <h2>Mai multe adrese dintr-un fișier</h2>
    <div class="rand"><label for="fisierAdrese">Fișierul cu adrese</label>
      <input type="file" id="fisierAdrese" accept=".txt,.m3u,.m3u8,text/plain,audio/x-mpegurl"></div>
    <p class="nota">Un fișier text cu câte o adresă de listă pe rând (http:// sau https://); numele listei poate sta pe același rând. Listele se adaugă imediat ce alegi fișierul.</p>
    <p class="nota">La fel merge și fără browser: copiezi prin FTP fișierul iptv.txt în dosarul /etc/enigma2/ al receptorului, iar listele noi se iau singure în cel mult un minut.</p>
    <p class="nota">O listă de canale (fișier .m3u sau .m3u8) copiată prin FTP în /etc/enigma2/ sau pusă pe un stick sau disc USB apare singură în IPTV, în cel mult un minut.</p>
    <div class="rand"><label for="m3uAutomat">Preia automat listele M3U găsite</label><select id="m3uAutomat"><option value="1">Da</option><option value="0">Nu</option></select></div>
    <p class="nota">Pe Nu, o listă de canale nouă găsită în /etc/enigma2 sau pe un stick așteaptă acordul tău pe televizor sau în pagina IPTV.</p>
    <div id="m3uCereri"></div>
  </section>
  <section class="card">
    <h2>Importă surse IPTV</h2>
    <p class="nota" id="numarSurse"></p>
    <div class="rand"><label for="stalkerFisier">Fișier text, JSON sau HD Satelit</label>
      <input type="file" id="stalkerFisier" accept=".hdsiptv,.txt,.json,.csv,.conf,.m3u,.m3u8,.tv,.pls,.xspf,.strm,text/plain,application/json"></div>
    <div class="rand"><label for="stalkerText">Sau lipește textul aici</label>
      <textarea id="stalkerText" rows="10" style="width:100%;min-height:180px" autocomplete="off" spellcheck="false"></textarea></div>
    <p class="nota">Formatul se recunoaște singur. Importul adaugă sursele fără să le încerce la portal. Cele existente rămân neschimbate.</p>
    <pre id="stalkerRezumat" style="white-space:pre-wrap;max-height:40vh;overflow:auto"></pre>
    <div id="stalkerCompletari"></div>
    <div class="butoane"><button type="button" id="stalkerAdauga" class="principal" disabled>Adaugă sursele</button>
      <button type="button" id="stalkerExport">Exportă toate sursele IPTV</button></div>
  </section>
  <section class="card ascuns" id="cardDemo">
    <h2>Lista demo: acordul fiecărui canal</h2>
    <div id="demo"></div>
  </section>
  <section class="card ascuns" id="cardGrupe">
    <h2 id="grupeTitlu">Grupele</h2>
    <p class="nota" id="grupeGhid"></p>
    <div class="butoane"><button type="button" id="grupeAscunde">Ascunde tot</button><button type="button" id="grupeArata">Arată tot</button><button type="button" id="grupeInchide">Închide</button></div>
    <div class="rand"><label for="grupeCauta">Caută o grupă sau o țară</label><input type="text" id="grupeCauta" maxlength="60" autocomplete="off"></div>
    <div id="grupeLista" style="max-height:60vh;overflow:auto;margin-top:12px"></div>
  </section>
  <section class="card ascuns" id="cardOptiuni">
    <h2>Player și piconuri</h2>
    <p id="optiuniNume"></p>
    <div class="rand"><label for="optiuniPlayer">Player în buchete</label><select id="optiuniPlayer"><option value="4097">4097 (implicit)</option><option value="5001">5001 (gstreamer)</option><option value="5002">5002 (exteplayer3)</option></select></div>
    <div class="rand"><label for="optiuniPiconuri">Descarcă piconurile sursei</label><select id="optiuniPiconuri"><option value="0">Nu</option><option value="1">Da</option></select></div>
    <p class="nota">Setările se aplică acestei surse. Piconurile existente se păstrează.</p>
    <p class="nota">Playerul ales trebuie să fie instalat pe receptor.</p>
    <div class="butoane"><button type="button" id="optiuniSalveaza">Salvează</button><button type="button" id="optiuniInchide">Închide</button></div>
  </section>
  <section class="card ascuns" id="cardAntete">
    <h2 id="anteteTitlu">Antetele sursei</h2>
    <p class="nota">Valorile salvate se văd în lista surselor. Completează ambele câmpuri; gol revine la valoarea implicită.</p>
    <div class="rand"><label for="anteteAgent">Agent utilizator (opțional)</label><input type="text" id="anteteAgent" maxlength="2048" autocomplete="off"></div>
    <div class="rand"><label for="anteteReferer">Referer (opțional)</label><input type="text" id="anteteReferer" maxlength="2048" autocomplete="off"></div>
    <div id="anteteStalker" class="ascuns">
      <div class="rand"><label for="anteteXAgent">X-User-Agent (opțional)</label><input type="text" id="anteteXAgent" maxlength="2048" autocomplete="off"></div>
      <div class="rand"><label for="anteteTip">Tip decodor (opțional)</label><input type="text" id="anteteTip" maxlength="2048" autocomplete="off"></div>
      <p class="nota">X-User-Agent și tipul decodorului: goale păstrează valorile salvate.</p>
      <label><input type="checkbox" id="anteteIdentitateImplicit">Folosește identitatea implicită</label>
    </div>
    <div class="butoane"><button type="button" id="anteteSalveaza">Salvează antetele</button><button type="button" id="anteteInchide">Închide</button></div>
  </section>
  <section class="card ascuns" id="cardMac">
    <h2>Adresa MAC</h2>
    <p id="macNume"></p>
    <div class="rand"><label for="macSursa">Adresa MAC</label><input type="text" id="macSursa" maxlength="64" autocomplete="off" autocapitalize="off" spellcheck="false"></div>
    <p class="nota">Pentru un abonament legat de alt receptor, scrie aici adresa MAC de pe acela. Unii furnizori nu permit două receptoare pornite în același timp cu aceeași adresă.</p>
    <button type="button" id="macSursaFa">Fă o adresă MAC</button>
    <p class="nota">Adresa nouă trebuie dată furnizorului. Pentru un cont mutat de pe alt receptor, scrie adresa de acolo. Se păstrează numai la Salvează.</p>
    <p id="macSursaVechi" class="nota"></p>
    <p class="nota">Scrie MAC-ul contului tău, primit de la furnizor sau copiat de pe receptorul vechi. Schimbarea lui păstrează favoritele și grupele. Sunt acceptate și liniuțe, puncte sau nicio despărțire.</p>
    <div class="butoane"><button type="button" id="macSalveaza">Salvează</button><button type="button" id="macInchide">Închide</button></div>
  </section>
  <section class="card ascuns" id="cardCont">
    <h2 id="contTitlu">IPTV</h2>
    <div class="rand ascuns" id="contCautare"><label for="contText">Caută</label><input type="text" id="contText" maxlength="80" autocomplete="off"></div>
    <div class="butoane"><button type="button" id="contCauta" class="ascuns">Caută</button><button type="button" id="contInapoi">Înapoi</button></div>
    <p class="nota" id="contNota"></p>
    <div id="contLista"></div>
    <div class="butoane ascuns" id="contPagini"><button type="button" id="contPrecedenta">Pagina precedentă</button><button type="button" id="contUrmatoarea">Pagina următoare</button></div>
  </section>
  <p class="nota">OK: canalele, filmele și serialele. MENU: date de acces și grupele.</p>
  <p class="nota">Aceleași liste sunt pe televizor, în __DRUM_MENIU__.</p>
</div>
""" + _COADA + """var ASTEPT = null;
function el(eticheta, clasa, text){ var e = document.createElement(eticheta); if(clasa){ e.className = clasa; } if(text){ e.textContent = text; } return e; }
function textSursa(x){
  var parti = [x.fel_text];
  if(x.gazda){ parti.push(x.gazda); }
  if(x.mac){ parti.push("Adresa MAC" + ": " + x.mac); }
  if(x.utilizator){ parti.push(x.utilizator); }
  if(x.canale_text){ parti.push(x.canale_text); }
  if(x.expira_text){ parti.push(x.expira_text); }
  return x.nume + " (" + parti.join(", ") + ")";
}
function stareSursa(x){
  if(x.lucreaza){ return "Se încarcă..."; }
  if(x.neconectata){ return "Neconectată"; }
  if(x.eroare){ return x.eroare; }
  var nota = [x.fara_https_text, x.taiate_text].filter(Boolean).join(" ");
  return "Merge." + (nota ? " " + nota : "");
}
var CONT = {};
function stareCont(id, incercari){
  if(CONT[id] && incercari === 0){ return; }
  CONT[id] = CONT[id] || {text: "", rau: false};
  var q = new URLSearchParams(); q.set("id", id);
  cerere("/api/iptv-cont?" + q.toString()).then(function(d){
    if(d && d.asteapta && incercari < 12){ setTimeout(function(){ stareCont(id, incercari + 1); }, 1000); return; }
    if(!d || !d.text){ return; }
    CONT[id] = {text: d.text, rau: !!d.stare && d.stare !== "activ"};
    document.querySelectorAll("[data-cont]").forEach(function(e){
      if(e.getAttribute("data-cont") === id){ e.textContent = CONT[id].text; e.className = CONT[id].rau ? "rau" : ""; }
    });
  }).catch(function(){});
}
var DATE = null;
function randSursa(x){
  var d = el("div", "lista-rand");
  var s = el("span", "", textSursa(x));
  s.appendChild(document.createElement("br"));
  s.appendChild(el("small", x.eroare ? "rau" : "", stareSursa(x)));
  if(x.epg_text){ s.appendChild(document.createElement("br")); s.appendChild(el("small", "", x.epg_text)); }
  if(x.fel === "xtream" && !x.neconectata){ var c = el("small", "", CONT[x.id] ? CONT[x.id].text : ""); c.setAttribute("data-cont", x.id); if(CONT[x.id] && CONT[x.id].rau){ c.className = "rau"; } s.appendChild(document.createElement("br")); s.appendChild(c); stareCont(x.id, 0); }
  s.appendChild(document.createElement("br")); s.appendChild(el("small", "", [x.adresa, x.server, x.portal, x.utilizator, x.parola, x.user_agent, x.referer, x.x_user_agent, x.stb_type].filter(Boolean).join(" / ")));
  d.appendChild(s);
  var b = el("span", "sursa-actiuni");
  if(x.fel !== "demo"){
    var deschide = el("button", "principal", "Deschide"); deschide.type = "button";
    deschide.addEventListener("click", function(){ deschideCont(x); }); b.appendChild(deschide);
  }
  if(x.fel !== "demo"){
    var grupe = el("button", "", "Grupele"); grupe.type = "button";
    grupe.addEventListener("click", function(){ deschideGrupe(x); }); b.appendChild(grupe);
    var antete = el("button", "", "Antete"); antete.type = "button";
    antete.addEventListener("click", function(){ deschideAntete(x); }); b.appendChild(antete);
    var opt = el("button", "", "Player și piconuri"); opt.type = "button";
    opt.addEventListener("click", function(){ deschideOptiuni(x); }); b.appendChild(opt);
  }
  if(x.fel === "stalker"){
    var mac = el("button", "", "Adresa MAC"); mac.type = "button";
    mac.addEventListener("click", function(){ deschideMac(x); }); b.appendChild(mac);
  }
  var a = el("button", "", "Actualizează");
  a.type = "button";
  a.addEventListener("click", function(){ var q = new URLSearchParams(); q.set("id", x.id); trimite("/api/iptv-actualizeaza", q); });
  b.appendChild(a);
  var r = el("button", "rosu", "Șterge");
  r.type = "button";
  r.addEventListener("click", function(){ var q = new URLSearchParams(); q.set("id", x.id); cuConfirmare("/api/iptv-sterge", q, dupa); });
  b.appendChild(r);
  d.appendChild(b);
  return d;
}
function arataDemo(demo){
  var c = $("cardDemo");
  if(!demo || !demo.grupe){ c.classList.add("ascuns"); return; }
  c.classList.remove("ascuns");
  var t = [];
  demo.grupe.forEach(function(g){
    t.push(el("h3", "", g.nume || ""));
    (g.canale || []).forEach(function(k){
      var p = el("p");
      p.appendChild(el("strong", "", k.nume || ""));
      if(k.citat){ p.appendChild(document.createElement("br")); p.appendChild(document.createTextNode(k.citat)); }
      if(k.atribuire){ p.appendChild(document.createElement("br")); p.appendChild(document.createTextNode(k.atribuire)); }
      if(/^https:[/][/]/.test(k.pagina || "")){
        p.appendChild(document.createElement("br"));
        var l = el("a", "extern", k.pagina); l.href = k.pagina; l.rel = "noopener noreferrer"; l.target = "_blank"; p.appendChild(l);
      }
      t.push(p);
    });
  });
  pune("demo", t);
}
var MAC_IMPLICIT_PUS = false;
$("mac").addEventListener("input", function(){ MAC_IMPLICIT_PUS = true; });
function arata(d){
  DATE = d;
  if(!MAC_IMPLICIT_PUS && d.mac_receptor !== undefined){
    if(!$("mac").value){ $("mac").value = d.mac_receptor; }
    MAC_IMPLICIT_PUS = true;
  }
  var s = (d.surse || []).map(randSursa);
  $("numarSurse").textContent = "Surse: %d din %d.".replace("%d", d.numar_surse).replace("%d", d.maxim_surse);
  pune("surse", s.length ? s : [gol("Încă nu ai adăugat nimic.")]);
  $("actualizeaza").classList.toggle("ascuns", !s.length);
  arataDemo(d.demo);
  if(d.lucreaza || ASTEPT){ urmareste(); }
}
function dupa(d){ if(d && d.surse){ arata(d); } }
function trimite(cale, q){
  mesaj("Se trimite...");
  return cerere(cale, "POST", q).then(function(d){ mesaj(d.message, !d.result); dupa(d); return d; }).catch(nimicNuRaspunde);
}
var CEAS = null;
function urmareste(){
  if(CEAS){ return; }
  CEAS = setTimeout(function(){
    CEAS = null;
    cerere("/api/iptv" + (ASTEPT ? "?id=" + encodeURIComponent(ASTEPT) : "")).then(function(d){
      var r = d.rezultat;
      if(ASTEPT && r && !r.lucreaza){
        ASTEPT = null;
        if(r.result){ mesaj("Gata. Canalele sunt în lista de canale, la Sateliți, pe rândul IPTV."); MAC_NOU_REV++; $("macVechi").textContent = ""; ["adresa", "server", "utilizator", "parola", "portal", "mac", "nume", "user_agent", "referer", "x_user_agent", "stb_type"].forEach(function(c){ $(c).value = ""; }); $("mac").value = d.mac_receptor || ""; $("playerNou").value = "4097"; }
        else { mesaj(r.message, true); }
      }
      dupa(d);
    }).catch(nimicNuRaspunde);
  }, 1500);
}
function arataCampuri(){
  var f = $("fel").value;
  $("adauga").textContent = f === "stalker" ? "Salvează" : "Adaugă";
  $("rNume").classList.toggle("ascuns", f === "demo");
  $("rPlayer").classList.toggle("ascuns", f === "demo");
  $("rAgent").classList.toggle("ascuns", f === "demo");
  $("rReferer").classList.toggle("ascuns", f === "demo");
  document.querySelectorAll(".camp").forEach(function(r){ r.classList.toggle("ascuns", r.getAttribute("data-fel") !== f); });
}
var M3U_TURA = 0;
function arataListeM3u(d){
  $("m3uAutomat").value = d.automat ? "1" : "0";
  var loc = $("m3uCereri"); loc.textContent = "";
  (d.cereri || []).forEach(function(x){
    var r = document.createElement("div"), t = document.createElement("p");
    r.className = "lista-rand"; t.textContent = x.text; r.appendChild(t);
    [["1", "Adaugă"], ["0", "Refuză"]].forEach(function(b){
      var buton = document.createElement("button"); buton.type = "button"; buton.textContent = b[1];
      buton.addEventListener("click", function(){
        var q = new URLSearchParams(); q.set("liste_m3u", "1"); q.set("jeton", x.jeton); q.set("da", b[0]);
        M3U_TURA++;
        cerere("/api/iptv-optiuni", "POST", q).then(function(rez){ mesaj(rez.message, !rez.result); arataListeM3u(rez); }).catch(nimicNuRaspunde);
      });
      r.appendChild(buton);
    });
    loc.appendChild(r);
  });
}
function citesteListeM3u(){
  var tura = ++M3U_TURA;
  return cerere("/api/iptv?liste_m3u=1").then(function(d){ if(tura === M3U_TURA && d.result){ arataListeM3u(d); } }).catch(nimicNuRaspunde);
}
$("m3uAutomat").addEventListener("change", function(){
  var camp = this, q = new URLSearchParams(); q.set("liste_m3u", "1"); q.set("automat", camp.value);
  M3U_TURA++; camp.disabled = true;
  cerere("/api/iptv-optiuni", "POST", q).then(function(d){ if(!d.result){ mesaj(d.message, true); } arataListeM3u(d); })
    .catch(nimicNuRaspunde).finally(function(){ camp.disabled = false; });
});
citesteListeM3u();
setInterval(citesteListeM3u, 15000);
function citeste(){
  return cerere("/api/iptv").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi setările."; return; }
    arataPagina(); arataCampuri(); arata(d);
  }).catch(faraRaspuns);
}
$("fel").addEventListener("change", function(){ MAC_NOU_REV++; arataCampuri(); });
$("actualizeaza").addEventListener("click", function(){ trimite("/api/iptv-actualizeaza", new URLSearchParams()); });
$("adauga").addEventListener("click", function(){
  MAC_NOU_REV++;
  var f = $("fel").value, q = new URLSearchParams();
  q.set("fel", f); q.set("nume", $("nume").value.trim());
  if(f !== "demo" && $("playerNou").value !== "4097"){ q.set("player", $("playerNou").value); }  // 4097: sursa adaugata din nou isi pastreaza playerul
  q.set("user_agent", $("user_agent").value.trim()); q.set("referer", $("referer").value.trim());
  document.querySelectorAll(".camp").forEach(function(r){
    if(r.getAttribute("data-fel") === f){ r.querySelectorAll("input").forEach(function(i){ q.set(i.id, i.id === "parola" ? i.value : i.value.trim()); }); }
  });
  trimite("/api/iptv-adauga", q).then(function(d){ if(d && d.result && d.id){ ASTEPT = d.id; $("parola").value = ""; $("adresa").value = ""; urmareste(); } });
});
$("fisierAdrese").addEventListener("change", function(){
  var f = this.files && this.files[0], el = this;
  if(!f){ return; }
  if(f.size > __MAX_FISIER__){ mesaj("Fișierul e prea mare pentru pagina web. Pune-l pe un stick sau prin FTP în /etc/enigma2: receptorul îl ia singur.", true); el.value = ""; return; }
  var r = new FileReader();
  r.onload = function(){ var q = new URLSearchParams(); q.set("text", String(r.result || "")); q.set("nume", f.name || ""); trimite("/api/iptv-fisier", q).then(function(d){ el.value = ""; if(d && d.result){ urmareste(); } }); };
  r.onerror = function(){ mesaj("Fișierul nu s-a putut citi.", true); el.value = ""; };
  r.readAsText(f);
});
var STALKER_TEXT = null, STALKER_TURA = 0;
var STALKER_NUME = "", STALKER_TIMER = null, STALKER_OCUPAT = false;
var STALKER_CORECTURI = {}, STALKER_TRANSFER = null;
function corecturiStalker(){
  var date = [];
  $("stalkerCompletari").querySelectorAll(".completare").forEach(function(r){
    var d = {rand:Number(r.dataset.rand), indice:Number(r.dataset.indice)};
    r.querySelectorAll("input").forEach(function(i){ d[i.dataset.camp] = i.value.trim(); });
    STALKER_CORECTURI[d.indice] = d;
  });
  return JSON.stringify(Object.keys(STALKER_CORECTURI).map(function(k){ return STALKER_CORECTURI[k]; }));
}
function formularStalker(date){
  var zona = $("stalkerCompletari"); zona.textContent = "";
  (date || []).forEach(function(d, indice){
    var rand = document.createElement("div"); rand.className = "completare"; rand.dataset.rand = d.rand; rand.dataset.indice = d.indice === undefined ? indice : d.indice;
    var titlu = document.createElement("p"); titlu.textContent = "Completează rândul:" + " " + d.rand; rand.appendChild(titlu);
    ["portal", "mac"].forEach(function(k){
      if(!d[k]){ return; }
      var l = document.createElement("label"); l.textContent = k === "portal" ? "Portal" : "Adresa MAC";
      var i = document.createElement("input"); i.type = "text"; i.autocomplete = "off"; i.dataset.camp = k;
      i.addEventListener("input", function(){ $("stalkerAdauga").disabled = STALKER_OCUPAT; });
      l.appendChild(i); rand.appendChild(l);
    });
    zona.appendChild(rand);
  });
}
function pregatesteStalker(text, nume, tura){
  var q = new URLSearchParams(); q.set("tip", "surse"); q.set("pas", "citeste"); q.set("text", text); q.set("nume", nume);
  cerere("/api/iptv-fisier", "POST", q).then(function(d){
    if(tura !== STALKER_TURA){ return; }
    if(d.ocupat){ STALKER_TIMER=setTimeout(function(){ if(tura === STALKER_TURA){ pregatesteStalker(text,nume,tura); } },500); return; }
    $("stalkerRezumat").textContent = d.message || "";
    formularStalker(d.incomplete);
    if(d.result){
      STALKER_TEXT = text; STALKER_NUME = nume;
      $("stalkerAdauga").disabled = STALKER_OCUPAT || !(d.import_stalker && d.import_stalker.noi);
    }
  }).catch(nimicNuRaspunde);
}
function curataStalker(){
  STALKER_CORECTURI = {}; STALKER_TRANSFER = null;
  STALKER_TEXT = null; $("stalkerAdauga").disabled = true; $("stalkerRezumat").textContent = "";
  $("stalkerCompletari").textContent = "";
  clearTimeout(STALKER_TIMER);
  return ++STALKER_TURA;
}
$("stalkerText").addEventListener("input", function(){
  var text = this.value, tura = curataStalker(); $("stalkerFisier").value = "";
  if(!text.trim()){ return; }
  if(new TextEncoder().encode(text).length > 4194304){ mesaj("Fișierul e prea mare. Alege un fișier de cel mult 4 MB și 10000 de rânduri.", true); return; }
  STALKER_TIMER = setTimeout(function(){ pregatesteStalker(text, "", tura); }, 250);
});
$("stalkerFisier").addEventListener("change", async function(){
  var f = this.files && this.files[0], tura = curataStalker(); $("stalkerText").value = "";
  if(!f){ return; }
  try {
    var prim = new TextDecoder().decode(await f.slice(0,9).arrayBuffer());
    if(tura !== STALKER_TURA){ return; }
    if((/[.]hdsiptv$/i.test(f.name || "") && !/^\\s*\\{/.test(prim)) || prim === "HDSIPTV2\\n" || prim === "HDSIPTV3\\n"){
      await ruleazaTransfer({f:f,arhiva:true},tura,"citeste"); return;
    }
    if(prim === "HDSIPTV1 "){ pregatesteTransfer(f, tura); return; }
    var proba = new TextDecoder().decode(await f.slice(0,4194305).arrayBuffer());
    if(tura !== STALKER_TURA){ return; }
    var nativ = /[.]hdsiptv$/i.test(f.name || "") || /HDSIPTV|"(?:hdsiptv|container|versiune|registru|liste|sha256|octeti|parti)"\\s*:|^[1-9][0-9]{0,7} [0-9a-f]{64}\\r?$/m.test(proba);
    if(nativ && !(/^\\s*\\{/.test(proba) && /"hdsiptv"\\s*:/.test(proba))){
      await ruleazaTransfer({f:f,arhiva:true},tura,"citeste"); return;
    }
  } catch(e){ mesaj("Fișierul nu s-a putut citi.",true); return; }
  if(f.size > 4194304){ mesaj("Fișierul e prea mare. Alege un fișier de cel mult 4 MB și 10000 de rânduri.", true); this.value = ""; return; }
  var r = new FileReader();
  r.onload = function(){
    if(tura !== STALKER_TURA){ return; }
    var text;
    try { text = new TextDecoder("utf-8", {fatal:true}).decode(r.result); }
    catch(e){ mesaj("Fișierul nu s-a putut citi.", true); return; }
    pregatesteStalker(text, f.name || "", tura);
  };
  r.onerror = function(){ if(tura === STALKER_TURA){ mesaj("Fișierul nu s-a putut citi.", true); } };
  r.readAsArrayBuffer(f);
});
$("stalkerAdauga").addEventListener("click", function(){
  if(STALKER_TRANSFER && !this.disabled && !STALKER_OCUPAT){ ruleazaTransfer(STALKER_TRANSFER, STALKER_TURA, "adauga"); return; }
  if(STALKER_TEXT === null || this.disabled || STALKER_OCUPAT){ return; }
  var tura = STALKER_TURA, q = new URLSearchParams(); this.disabled = true; STALKER_OCUPAT = true;
  q.set("tip", "surse"); q.set("pas", "adauga"); q.set("text", STALKER_TEXT); q.set("nume", STALKER_NUME);
  q.set("completari", corecturiStalker());
  function gata(d){
    if(d.ocupat && tura === STALKER_TURA){
      STALKER_TIMER=setTimeout(function(){ cerere("/api/iptv-fisier","POST",q).then(gata).catch(esec); },500);
      return;
    }
    STALKER_OCUPAT = false;
    if(d.result){ citeste(); }
    if(tura !== STALKER_TURA){ $("stalkerAdauga").disabled = STALKER_TEXT === null; return; }
    $("stalkerRezumat").textContent = d.message || "";
    if(d.result && !(d.incomplete || []).length){
      STALKER_TEXT = null; $("stalkerFisier").value = ""; $("stalkerText").value = ""; formularStalker([]);
    } else { formularStalker(d.incomplete); $("stalkerAdauga").disabled = false; }
  }
  function esec(){ STALKER_OCUPAT = false; $("stalkerAdauga").disabled = STALKER_TEXT === null; nimicNuRaspunde(); }
  cerere("/api/iptv-fisier", "POST", q).then(gata).catch(esec);
});
$("stalkerExport").addEventListener("click", function(){
  var b = this; b.disabled = true;
  fetch(adresa("/api/iptv-stalker-export"), {method:"POST", credentials:"same-origin", cache:"no-store",
    headers:{"Content-Type":"application/x-www-form-urlencoded", "X-HDS-CSRF":CFG.csrf || ""}, body:"format=transfer"}).then(function(r){
    if(!r.ok){ return r.json().then(function(d){ mesaj(d.message, true); }); }
    return r.blob().then(function(blob){
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a"); a.href = url; a.download = "surse-iptv.hdsiptv"; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function(){ URL.revokeObjectURL(url); }, 1000);
    });
  }).catch(nimicNuRaspunde).then(function(){ b.disabled = false; });
});
async function pregatesteTransfer(f, tura){
  try {
    var prim = new Uint8Array(await f.slice(0,32).arrayBuffer()), lf = prim.indexOf(10);
    var cap = new TextDecoder("utf-8", {fatal:true}).decode(prim.slice(0,lf));
    var m = /^HDSIPTV1 ([0-9]{1,3})$/.exec(cap);
    if(lf < 0 || !m || Number(m[1]) > 300){ throw Error(); }
    var pos = lf+1, intrari = [];
    for(var k=0; k<Number(m[1]); k++){
      var h = new Uint8Array(await f.slice(pos,pos+16385).arrayBuffer()); lf = h.indexOf(10);
      if(lf < 0 || lf >= 16384){ throw Error(); }
      var meta = JSON.parse(new TextDecoder("utf-8", {fatal:true}).decode(h.slice(0,lf)));
      var n = meta && meta.octeti; pos += lf+1;
      if(!Number.isInteger(n) || n < 0 || n > 67108864 || pos+n >= f.size || ["m3u","xtream","stalker","demo"].indexOf(meta.fel) < 0 || (n && meta.fel !== "m3u")){ throw Error(); }
      if(new Uint8Array(await f.slice(pos+n,pos+n+1).arrayBuffer())[0] !== 10){ throw Error(); }
      intrari.push({meta:meta, pos:pos, n:n}); pos += n+1;
    }
    if(pos !== f.size){ throw Error(); }
    if(tura !== STALKER_TURA){ return; }
    await ruleazaTransfer({f:f, intrari:intrari}, tura, "citeste");
  } catch(e){ if(tura === STALKER_TURA){ mesaj("Fișierul nu s-a putut citi.", true); } }
}
async function ruleazaTransfer(transfer, tura, pas){
  STALKER_OCUPAT = true; $("stalkerAdauga").disabled = true;
  var gasite=0, existente=0, noi=0, adaugate=0, vazute=new Set(), libere=300, total=0, maxim=300, refuzuri=[];
  try {
    if(transfer.arhiva){
      var d=await trimiteListaTransfer(transfer.f,{n:transfer.f.size,pos:0,meta:{fel:"arhiva",octeti:transfer.f.size}},tura,pas);
      if(tura !== STALKER_TURA){ return; }
      if(!d.result){ throw Error(); }
      $("stalkerRezumat").textContent=d.message;
      STALKER_TRANSFER=pas === "adauga" ? null : transfer;
      if(pas === "adauga"){ $("stalkerFisier").value=""; citeste(); }
      return;
    }
    for(var i=0; i<transfer.intrari.length; i++){
      if(tura !== STALKER_TURA){ return; }
      var e=transfer.intrari[i], q=new URLSearchParams();
      q.set("pas",pas); q.set("tip","surse");
      q.set("meta",JSON.stringify(e.meta));
      q.set("text",JSON.stringify(e.meta));
      var d=e.n ? await trimiteListaTransfer(transfer.f,e,tura,pas) : await cerere("/api/iptv-fisier","POST",q);
      while(d.ocupat && tura === STALKER_TURA){
        await new Promise(function(gata){ setTimeout(gata,500); });
        if(tura !== STALKER_TURA){ return; }
        d=await cerere("/api/iptv-fisier","POST",q);
      }
      if(!d.result || !d.import_stalker || (!d.amprenta_transfer && !(d.import_stalker.neacceptate || []).length) || (d.incomplete || []).length){ throw Error(); }
      if(i === 0){ total=d.import_stalker.total; maxim=d.import_stalker.maxim; libere=Math.max(0,maxim-total); }
      (d.import_stalker.neacceptate || []).forEach(function(r){refuzuri.push({rand:i+1,motiv:r.motiv});});
      gasite+=d.import_stalker.gasite;
      if(vazute.has(d.amprenta_transfer)){ existente+=d.import_stalker.gasite; }
      else { existente+=d.import_stalker.existente; noi+=d.import_stalker.noi; vazute.add(d.amprenta_transfer); }
      adaugate+=d.import_stalker.adaugate || 0;
    }
    if(tura !== STALKER_TURA){ return; }
    var text="Găsite: %d. Deja prezente sau repetate: %d. De adăugat: %d. Rânduri necitibile: %d.";
    noi=Math.min(noi,libere);
    [gasite,existente,noi,0].forEach(function(n){text=text.replace("%d",n);});
    if(gasite-existente > libere){
      var limita="Ai %d surse din %d posibile. Nu mai încap: %d.";
      [total,maxim,gasite-existente-libere].forEach(function(n){limita=limita.replace("%d",n);}); text += "\\n"+limita;
    }
    refuzuri.forEach(function(r){
      var refuz="Rândul %d: nu se poate adăuga încă: %s";
      text += "\\n"+refuz.replace("%d",r.rand).replace("%s",r.motiv);
    });
    if(pas === "adauga"){
      text += "\\n" + "Surse adăugate: %d. Deschide o sursă sau apasă Actualizează pe ea ca să te conectezi.".replace("%d",adaugate);
      STALKER_TRANSFER=null; $("stalkerFisier").value=""; citeste();
    } else { STALKER_TRANSFER=transfer; }
    $("stalkerRezumat").textContent=text;
  } catch(e){ if(tura === STALKER_TURA){ mesaj("Fișierul nu s-a putut citi.",true); } }
  finally { STALKER_OCUPAT=false; $("stalkerAdauga").disabled = !STALKER_TRANSFER && STALKER_TEXT === null; }
}
async function trimiteListaTransfer(f,e,tura,pas){
  var jeton="",d;
  try {
    for(var pos=0;pos<e.n;pos+=524288){
      if(tura !== STALKER_TURA){ throw Error(); }
      var b=new Uint8Array(await f.slice(e.pos+pos,e.pos+Math.min(e.n,pos+524288)).arrayBuffer());
      var sir="";
      for(var k=0;k<b.length;k+=8192){ sir+=String.fromCharCode.apply(null,b.subarray(k,k+8192)); }
      var q=new URLSearchParams({tip:"transfer_bucata",pas:pas,meta:JSON.stringify(e.meta),jeton:jeton,pozitie:String(pos),text:btoa(sir)});
      d=await cerere("/api/iptv-fisier","POST",q);
      while(d.ocupat && tura === STALKER_TURA){
        await new Promise(function(gata){setTimeout(gata,500);});
        if(tura !== STALKER_TURA){ throw Error(); }
        d=await cerere("/api/iptv-fisier","POST",q);
      }
      if(!d.result){ throw Error(); }
      jeton=d.jeton || "";
    }
    return d;
  } finally {
    if(jeton){ await cerere("/api/iptv-fisier","POST",new URLSearchParams({tip:"transfer_bucata",pas:"anuleaza",jeton:jeton})); }
  }
}
function faMac(camp, vechi, buton, valid){
  if(buton.disabled){ return; }
  var initial = camp.value;
  buton.disabled = true;
  trimite("/api/iptv-mac-nou", new URLSearchParams()).then(function(d){
    if(d && d.result && valid() && camp.value === initial){
      if(!vechi.textContent && initial){ vechi.textContent = "Adresa de dinainte:" + " " + initial; }
      camp.value = d.mac;
    }
  }).finally(function(){ buton.disabled = false; });
}
var MAC_NOU_REV = 0;
$("macFa").addEventListener("click", function(){
  if(ASTEPT){ return; }
  var rev = MAC_NOU_REV;
  faMac($("mac"), $("macVechi"), this, function(){ return MAC_NOU_REV === rev && $("fel").value === "stalker" && !ASTEPT; });
});
var MAC_ID = "", MAC_REV = 0;
$("macSursaFa").addEventListener("click", function(){
  var rev = MAC_REV;
  if(!MAC_ID || $("macSalveaza").disabled){ return; }
  faMac($("macSursa"), $("macSursaVechi"), this, function(){ return MAC_REV === rev && !!MAC_ID && !$("macSalveaza").disabled; });
});
function deschideMac(x){
  MAC_REV++;
  MAC_ID = x.id;
  $("macSursaVechi").textContent = "";
  $("macNume").textContent = x.nume;
  $("macSursa").value = x.mac || "";
  $("cardMac").classList.remove("ascuns");
  $("cardMac").scrollIntoView({behavior: "smooth", block: "start"});
  $("macSursa").focus();
}
$("macInchide").addEventListener("click", function(){ $("cardMac").classList.add("ascuns"); MAC_ID = ""; MAC_REV++; });
$("macSalveaza").addEventListener("click", function(){
  if(!MAC_ID){ return; }
  if($("macSalveaza").disabled){ return; }
  MAC_REV++;
  var id = MAC_ID, rev = MAC_REV, q = new URLSearchParams(); q.set("id", id); q.set("mac", $("macSursa").value);
  $("macSalveaza").disabled = true;
  trimite("/api/iptv-mac", q).then(function(d){
    $("macSalveaza").disabled = false;
    if(d && d.result && d.id){
      ASTEPT = d.id;
      if(MAC_ID === id && MAC_REV === rev){ $("cardMac").classList.add("ascuns"); MAC_ID = ""; }
      urmareste();
    }
  });
});
var ANTETE_ID = "";
var GRUPE_ID = "", GRUPE_DATE = null;
function arataGrupe(d){
  var l = $("grupeLista"); l.textContent = ""; GRUPE_DATE = d;
  var cauta = $("grupeCauta").value.trim().toLowerCase();
  $("grupeGhid").textContent = d.ghid || "";
  (d.randuri || []).forEach(function(r){
    if(cauta && r.nume.toLowerCase().indexOf(cauta) < 0){ return; }
    var e = document.createElement("label"); e.style.display = "block"; e.style.padding = "6px 0";
    var c = document.createElement("input"); c.type = "checkbox"; c.checked = !!r.vizibil;
    c.addEventListener("change", function(){ schimbaGrupe("cheie", r.cheie); });
    e.appendChild(c);
    e.appendChild(document.createTextNode(" " + r.text));
    l.appendChild(e);
  });
}
function schimbaGrupe(k, v){
  var q = new URLSearchParams(); q.set("id", GRUPE_ID); q.set(k, v);
  return trimite("/api/iptv-grupe-schimba", q).then(function(d){ if(d && d.result){ arataGrupe(d); } });
}
function deschideGrupe(x){
  GRUPE_ID = x.id; $("grupeTitlu").textContent = "Grupele" + ": " + x.nume;
  cerere("/api/iptv-grupe?id=" + encodeURIComponent(x.id)).then(function(d){ if(d && d.result){ arataGrupe(d); } });
  $("cardGrupe").classList.remove("ascuns"); $("cardGrupe").scrollIntoView({block:"start",behavior:"smooth"});
}
$("grupeInchide").addEventListener("click", function(){ $("cardGrupe").classList.add("ascuns"); GRUPE_ID = ""; });
$("grupeCauta").addEventListener("input", function(){ if(GRUPE_DATE){ arataGrupe(GRUPE_DATE); } });
$("grupeAscunde").addEventListener("click", function(){ schimbaGrupe("tot", "ascunde"); });
$("grupeArata").addEventListener("click", function(){ schimbaGrupe("tot", "arata"); });
var OPTIUNI_ID = "";
function deschideOptiuni(x){
  OPTIUNI_ID = x.id; $("optiuniNume").textContent = x.nume;
  $("optiuniPlayer").value = x.player || "4097"; $("optiuniPiconuri").value = x.piconuri ? "1" : "0";
  $("cardOptiuni").classList.remove("ascuns"); $("cardOptiuni").scrollIntoView({block:"start",behavior:"smooth"});
}
$("optiuniInchide").addEventListener("click", function(){ $("cardOptiuni").classList.add("ascuns"); OPTIUNI_ID = ""; });
$("optiuniSalveaza").addEventListener("click", function(){
  if(!OPTIUNI_ID){ return; }
  var q = new URLSearchParams(); q.set("id", OPTIUNI_ID); q.set("player", $("optiuniPlayer").value); q.set("piconuri", $("optiuniPiconuri").value);
  trimite("/api/iptv-optiuni", q).then(function(d){ if(d && d.result){ $("optiuniInchide").click(); } });
});
function deschideAntete(x){
  ANTETE_ID = x.id; $("anteteTitlu").textContent = "Antetele sursei" + ": " + x.nume;
  $("anteteAgent").value = ""; $("anteteReferer").value = "";
  $("anteteXAgent").value = ""; $("anteteTip").value = "";
  $("anteteIdentitateImplicit").checked = false;
  $("anteteStalker").classList.toggle("ascuns", x.fel !== "stalker");
  $("cardAntete").classList.remove("ascuns"); $("cardAntete").scrollIntoView({block:"start",behavior:"smooth"});
}
$("anteteInchide").addEventListener("click", function(){ $("cardAntete").classList.add("ascuns"); ANTETE_ID = ""; $("anteteAgent").value = ""; $("anteteReferer").value = ""; });
$("anteteSalveaza").addEventListener("click", function(){
  if(!ANTETE_ID){ return; } var q = new URLSearchParams(); q.set("id", ANTETE_ID);
  q.set("user_agent", $("anteteAgent").value.trim()); q.set("referer", $("anteteReferer").value.trim());
  if(!$("anteteStalker").classList.contains("ascuns")){
    if($("anteteIdentitateImplicit").checked || $("anteteXAgent").value.trim()){ q.set("x_user_agent", $("anteteXAgent").value.trim()); }
    if($("anteteIdentitateImplicit").checked || $("anteteTip").value.trim()){ q.set("stb_type", $("anteteTip").value.trim()); }
  }
  trimite("/api/sursa-antete", q).then(function(d){ if(d && d.result){ $("anteteInchide").click(); } });
});
var CT = null, CT_TURA = 0;
function deschideCont(x){
  if(x.neconectata){ var q = new URLSearchParams(); q.set("id", x.id); trimite("/api/iptv-actualizeaza", q); }
  CT = {id:x.id, nume:x.nume, fel:x.fel, filme:x.filme_sursa || 0, canale:x.canale_text || "", drum:[], pagina:null};
  $("contText").value = ""; $("cardCont").classList.remove("ascuns");
  $("cardCont").scrollIntoView({block:"start",behavior:"smooth"});
  nivelCont("", arataSectiuni, "");
}
function nivelCont(titlu, fn, tip){ CT.drum.push({titlu:titlu, fn:fn, tip:tip}); fn(); }
function sus(){ return CT.drum[CT.drum.length - 1]; }
function listaCont(randuri, nota){
  $("contTitlu").textContent = [CT.nume].concat(CT.drum.map(function(n){ return n.titlu; }).filter(Boolean)).join(" › ");
  var tip = sus().tip; $("contCautare").classList.toggle("ascuns", !tip); $("contCauta").classList.toggle("ascuns", !tip);
  var p = CT.pagina; $("contPagini").classList.toggle("ascuns", !p);
  if(p){ $("contPrecedenta").disabled = !p.de_la; $("contUrmatoarea").disabled = p.de_la + PE_PAGINA >= p.toate; }
  $("contNota").textContent = nota || ""; pune("contLista", randuri.length ? randuri : [gol("Niciun rezultat.")]);
}
var PE_PAGINA = 300;
function incarcareCont(){ ++CT_TURA; CT.pagina = null; $("contNota").textContent = "Se încarcă..."; pune("contLista", []); return CT_TURA; }
function faraRaspunsCont(tura){ if(CT && tura === CT_TURA){ $("contNota").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; } }
function cerereCanale(q, gata){
  var tura = incarcareCont(); q.set("id", CT.id);
  (function una(n){
    cerere("/api/iptv-sursa-canale?" + q.toString()).then(function(d){
      if(!CT || tura !== CT_TURA){ return; }
      if(d.asteapta && n < 120){ setTimeout(function(){ una(n + 1); }, 500); return; }
      if(!d.result){ $("contNota").textContent = d.message || ""; return; }
      gata(d);
    }).catch(function(){ faraRaspunsCont(tura); });
  })(0);
}
function cerereVod(q, gata){
  var tura = incarcareCont(); q.set("id", CT.id);
  (function una(cale){
    cerere(cale).then(function(d){
      if(!CT || tura !== CT_TURA){ return; }
      if(d.lucreaza){ setTimeout(function(){ una("/api/vod?id=" + encodeURIComponent(CT.id) + "&cerere=" + encodeURIComponent(d.cerere)); }, 500); return; }
      if(!d.result){ $("contNota").textContent = d.message || ""; return; }
      gata(d);
    }).catch(function(){ faraRaspunsCont(tura); });
  })("/api/vod?" + q.toString());
}
function arataSectiuni(){
  ++CT_TURA; CT.pagina = null;
  var r = [rand("Canale TV" + (CT.canale ? " · " + CT.canale : ""), "Deschide", function(){ nivelCont("Canale TV", grupeCont, ""); })];
  if(CT.fel === "xtream" || (CT.fel === "m3u" && CT.filme)){
    r.push(rand("Filme" + (CT.fel === "m3u" ? " · " + CT.filme : ""), "Deschide", function(){ nivelCont("Filme", function(){ categoriiCont("filme"); }, "filme"); }));
  }
  if(CT.fel === "xtream"){ r.push(rand("Seriale", "Deschide", function(){ nivelCont("Seriale", function(){ categoriiCont("seriale"); }, "seriale"); })); }
  listaCont(r);
}
function grupeCont(){
  cerereCanale(new URLSearchParams(), function(d){
    listaCont((d.grupe || []).map(function(g, i){ return rand(g.nume + " · " + g.text, "Deschide", function(){ nivelCont(g.nume, function(){ canaleCont(i, 0); }, ""); }); }));
  });
}
function canaleCont(i, de_la){
  var q = new URLSearchParams(); q.set("grupa", String(i)); q.set("de_la", String(de_la));
  cerereCanale(q, function(d){
    CT.pagina = {grupa:i, de_la:d.de_la, toate:d.toate};
    listaCont((d.canale || []).map(function(c){
      return rand(c.nume, "Pornește pe televizor", function(){
        var p = new URLSearchParams(); p.set("id", CT.id); p.set("cheie", c.cheie);
        cerere("/api/iptv-sursa-porneste", "POST", p).then(function(r){ mesaj(r.message, !r.result); }).catch(nimicNuRaspunde);
      });
    }));
  });
}
function categoriiCont(tip){
  var q = new URLSearchParams(); q.set("fel", "categorii"); q.set("tip", tip);
  cerereVod(q, function(d){
    listaCont((d.categorii || []).map(function(c){ return rand(c.nume, "Deschide", function(){ nivelCont(c.nume, function(){ titluriCont(tip, "rand", c.id); }, tip); }); }));
  });
}
function titluriCont(tip, fel, arg){
  var q = new URLSearchParams(); q.set("fel", fel); q.set("tip", tip); q.set("arg", arg);
  cerereVod(q, function(d){
    listaCont((d.titluri || []).map(function(t){
      var text = [t.nume, t.nota ? t.nota.replace(".", ",") : ""].filter(Boolean).join(" · ");
      if(tip === "seriale"){ return rand(text, "Deschide", function(){ nivelCont(t.nume, function(){ sezoaneCont(t); }, ""); }); }
      return rand(text, "Pornește pe televizor", function(){ redaCont(t, {}); });
    }));
  });
}
function sezoaneCont(t){
  var q = new URLSearchParams(); q.set("fel", "detalii"); q.set("tip", "seriale"); q.set("arg", t.id);
  cerereVod(q, function(d){
    var det = d.detalii || {};
    listaCont((det.sezoane || []).map(function(sz){
      return rand("Sezonul" + " " + sz.numar, "Deschide", function(){
        nivelCont("Sezonul" + " " + sz.numar, function(){
          ++CT_TURA; CT.pagina = null;
          listaCont((sz.episoade || []).map(function(e){
            return rand((e.numar ? e.numar + ". " : "") + e.nume, "Pornește pe televizor", function(){
              redaCont(e, {serial:det.id || t.id, serial_nume:det.nume || t.nume, sezon:sz.numar, numar:e.numar || ""});
            });
          }));
        }, "");
      });
    }), det.descriere || "");
  });
}
function redaCont(t, extra){
  var q = new URLSearchParams(); q.set("id", CT.id); q.set("cheie", t.cheie); q.set("de_la", "1"); q.set("nume", t.nume || ""); q.set("poza", t.poza || "");
  Object.keys(extra).forEach(function(k){ q.set(k, extra[k]); });
  cerere("/api/vod-reda", "POST", q).then(function(r){ mesaj(r.message, !r.result); }).catch(nimicNuRaspunde);
}
$("contInapoi").addEventListener("click", function(){
  if(!CT){ return; }
  if(CT.drum.length > 1){ CT.drum.pop(); sus().fn(); }
  else { CT = null; ++CT_TURA; $("cardCont").classList.add("ascuns"); }
});
$("contCauta").addEventListener("click", function(){
  var text = $("contText").value.trim(), tip = CT ? sus().tip : "";
  if(!CT || !text || !tip){ return; }
  nivelCont(text, function(){ titluriCont(tip, "cauta", text); }, tip);
});
$("contText").addEventListener("keydown", function(e){ if(e.key === "Enter"){ e.preventDefault(); $("contCauta").click(); } });
$("contPrecedenta").addEventListener("click", function(){ var p = CT && CT.pagina; if(p && p.de_la){ canaleCont(p.grupa, Math.max(0, p.de_la - PE_PAGINA)); } });
$("contUrmatoarea").addEventListener("click", function(){ var p = CT && CT.pagina; if(p && p.de_la + PE_PAGINA < p.toate){ canaleCont(p.grupa, p.de_la + PE_PAGINA); } });
var ARHIVA = "";
function arhiva(incercari){
  cerere("/api/iptv-arhiva").then(function(d){
    if(d.asteapta){ if(incercari < 20){ setTimeout(function(){ arhiva(incercari + 1); }, 1000); } return; }
    var card = $("cardArhiva");
    if(!d.canal){ card.classList.add("ascuns"); ARHIVA = ""; return; }
    card.classList.remove("ascuns");
    ARHIVA = d.id || "";
    $("arhivaNota").textContent = d.canal + (d.mesaj ? ": " + d.mesaj : " (" + String(d.programe.length) + ")");
    var randuri = (d.programe || []).map(function(p, i){
      var r = el("div", "lista-rand");
      var s = el("span", "", p.text);
      if(p.descriere){ s.appendChild(document.createElement("br")); s.appendChild(el("small", "", p.descriere)); }
      r.appendChild(s);
      var b = el("button", "", "Pornește pe televizor"); b.type = "button";
      b.addEventListener("click", function(){ var q = new URLSearchParams(); q.set("canal", ARHIVA); q.set("i", String(i)); trimite("/api/iptv-arhiva-porneste", q); });
      r.appendChild(b);
      return r;
    });
    var l = $("arhivaLista"); l.textContent = ""; randuri.forEach(function(r){ l.appendChild(r); });
  }).catch(function(){});
}
$("arhivaReincarca").addEventListener("click", function(){ arhiva(0); });
arhiva(0);
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
    <div class="rand"><label for="capturaInterval">Actualizarea imaginii pe prima pagină web</label>
      <select id="capturaInterval"><option value="0">Oprită</option><option value="1">1 s</option><option value="2">2 s</option><option value="3">3 s</option><option value="4">4 s</option><option value="5">5 s</option><option value="6">6 s</option><option value="7">7 s</option><option value="8">8 s</option><option value="9">9 s</option><option value="10">10 s</option></select></div>
  </section>
  <section class="card">
    <h2>Acces</h2>
    <p class="nota" id="parolaLocala"></p>
    <div class="rand"><label for="aplicatii">Aplicații de telefon</label>
      <select id="aplicatii"><option value="0">Nu</option><option value="1">Da</option></select></div>
    <div class="rand"><label for="aplicatiiAfara">Acces din afara casei</label>
      <select id="aplicatiiAfara"><option value="0">Nu</option><option value="1">Da</option></select></div>
    <p class="nota" id="aplicatiiNota" data-hds-secret="1"></p>
    <div class="butoane"><button type="button" class="ascuns" id="arataParola">Arată parola</button>
      <button type="button" class="ascuns" id="parolaAplicatii">Parolă nouă pentru aplicații</button></div>
  </section>
  <section class="card">
    <h2>Browsere conectate</h2>
    <div id="browsere"></div>
    <div class="butoane"><button type="button" class="rosu" id="deconecteaza">Deconectează browserele</button></div>
  </section>
  <section class="card">
    <h2>Cheia pentru scripturi</h2>
    <div class="status-linie"><span>Cheia</span><span id="cheie" data-hds-secret="1"></span></div>
    <p class="nota">Doar pentru programatori. Browserul obișnuit nu are nevoie de ea. Cheia se vede întreagă mai sus.</p>
    <div class="butoane"><button type="button" id="arataCheie">Arată cheia</button>
      <button type="button" class="rosu" id="cheieNoua">Cheie nouă pentru panoul web</button></div>
  </section>
  <p class="nota">Aceleași setări sunt pe televizor, în __DRUM_MENIU__. Tema și culorile paginilor web sunt în pagina Setări.</p>
</div>
""" + _COADA + """var D = null, A = null, PAROLA = "", CHEIE = "", NEARATATA = "(se arată la buton)";
var PLECATA = false, SECRETE = {parola: {tura: 0, ceas: null, pana: 0}, cheie: {tura: 0, ceas: null, pana: 0}};
function ascundeSecret(ce){
  var s = SECRETE[ce];
  ++s.tura; clearTimeout(s.ceas); s.ceas = null; s.pana = 0;
  if(ce === "parola"){ PAROLA = ""; if(A){ arataAcces(A); } }
  else { CHEIE = ""; if(D){ arata(D); } }
}
function pleaca(){ PLECATA = true; ascundeSecret("parola"); ascundeSecret("cheie"); }
function verificaTimp(){
  Object.keys(SECRETE).forEach(function(ce){ var s = SECRETE[ce]; if(s.pana && Date.now() >= s.pana){ ascundeSecret(ce); } });
}
window.addEventListener("pagehide", pleaca);
window.addEventListener("pageshow", function(){ PLECATA = false; verificaTimp(); });
window.addEventListener("focus", verificaTimp);
document.addEventListener("visibilitychange", verificaTimp);
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
  $("cheie").textContent = aCheie(d) || CHEIE || NEARATATA;
  $("arataCheie").textContent = CHEIE ? "Ascunde cheia" : "Arată cheia";
}
function aCheie(d){ return d.cheie || (A && A.cheie) || ""; }
function arataAcces(a){
  $("cheie").textContent = a.cheie || CHEIE || NEARATATA;
  $("parolaLocala").textContent = a.parola_web ? "Ai pus parolă pentru interfața web: browserele și aplicațiile din casă o cer. O scoți sau o schimbi în Parola receptorului (/acces-ssh)." : "Din rețeaua de acasă nu se cere nici cod, nici parolă. O parolă (una singură, pentru tot) pui numai dacă vrei, în Parola receptorului (/acces-ssh).";
  $("aplicatii").value = a.aplicatii ? "1" : "0";
  $("aplicatiiAfara").value = a.aplicatii_afara ? "1" : "0";
  // la cate secunde cere prima pagina imaginea ecranului (0 = oprita; plugin.intervalCaptura)
  if(a.captura_interval !== undefined){ $("capturaInterval").value = String(a.captura_interval); }
  A = a;
  var p = a.parola_aplicatii || PAROLA || NEARATATA, t = [];
  if(a.aplicatii){
    t.push(a.parola_web ? "Aplicații de telefon: și acasă scrii utilizatorul root și parola ta (pusă în Parola receptorului)." : "Aplicații de telefon: acasă scrii în aplicație numai adresa receptorului, fără utilizator și parolă.");
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
  var s = SECRETE[ce], tura = ++s.tura;
  var q = new URLSearchParams(); q.set("ce", ce);
  cerere("/api/interfata-web-secrete", "POST", q).then(function(d){
    if(PLECATA || tura !== s.tura){ return; }
    if(!d.result){ mesaj(d.message, true); return; }
    gata(d);
    clearTimeout(s.ceas);
    s.pana = Date.now() + 5 * 60 * 1000;
    s.ceas = setTimeout(function(){ ascundeSecret(ce); }, 5 * 60 * 1000);
  }).catch(nimicNuRaspunde);
}
function citesteAcces(){
  return cerere("/api/interfata-web").then(function(a){ if(a.result){ arataAcces(a); } });
}
function dupa(d){
  if(d && d.browsere){ arata(d); }
  if(d && d.result && d.reincarca){ ascundeSecret("cheie"); setTimeout(function(){ location.reload(); }, 1500); }
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
["aplicatii", "aplicatiiAfara", "capturaInterval"].forEach(function(id){
  var cheie = {aplicatii: "aplicatii", aplicatiiAfara: "aplicatii_afara", capturaInterval: "captura_interval"}[id];
  $(id).addEventListener("change", function(){
    var q = new URLSearchParams(); q.set(cheie, $(id).value);
    mesaj("Se salvează...");
    cerere("/api/interfata-web-seteaza", "POST", q).then(function(d){ mesaj(d.message, !d.result); citesteAcces(); }).catch(nimicNuRaspunde);
  });
});
$("parolaAplicatii").addEventListener("click", function(){
  if(!confirm("Faci o parolă nouă pentru aplicații? Din afara casei, aplicațiile care o folosesc pe cea veche nu mai primesc răspuns până nu scrii în ele parola nouă.")){ return; }
  ascundeSecret("parola");
  var q = new URLSearchParams(); q.set("parola_aplicatii_noua", "1");
  cerere("/api/interfata-web-seteaza", "POST", q).then(function(d){ ascundeSecret("parola"); mesaj(d.message, !d.result); citesteAcces(); }).catch(nimicNuRaspunde);
});
$("arataParola").addEventListener("click", function(){
  if(PAROLA){ ascundeSecret("parola"); return; }
  secret("parola", function(d){ PAROLA = d.parola_aplicatii || ""; if(A){ arataAcces(A); } });
});
$("arataCheie").addEventListener("click", function(){
  if(CHEIE){ ascundeSecret("cheie"); return; }
  secret("cheie", function(d){ CHEIE = d.cheie || ""; if(D){ arata(D); } });
});
$("deconecteaza").addEventListener("click", function(){ cuConfirmare("/api/interfata-web-actiune", actiune("deconecteaza"), dupa); });
$("cheieNoua").addEventListener("click", function(){ cuConfirmare("/api/interfata-web-actiune", actiune("cheie"), dupa); });
citeste();""" + _SFARSIT


# ---------------------------------------------------------------- traducerea paginilor
# Textele sabloanelor de mai sus, traduse la cerere in limba receptorului (traducere_pagini.py). Un text
# nou sau schimbat in sablon se scrie si aici (proba textelor paginilor web il cere).
TEXTE_PAGINA = {
	"html": (
		# 0.8.0 DVI2: listele de proba din toate tarile, pornite din fabrica
		N_("Și listele de probă"),
		N_("Listele de probă ale registrelor, din toate țările, intră și ele: canalele lor pot să nu meargă."),
		N_("Toate listele țării sunt bifate singure, și cele de probă cât timp sunt pornite listele de probă; bifele rămân și când schimbi țara."),
		N_("Preia automat listele M3U găsite"),
		N_("Pe Nu, o listă de canale nouă găsită în /etc/enigma2 sau pe un stick așteaptă acordul tău pe televizor sau în pagina IPTV."),
		N_("Importă surse IPTV"),
		N_("Fișier text, JSON sau HD Satelit"),
		N_("Găsite: %d. Deja prezente sau repetate: %d. De adăugat: %d. Rânduri necitibile: %d."),
		N_("Surse adăugate: %d. Deschide o sursă sau apasă Actualizează pe ea ca să te conectezi."),
		N_("Ai %d surse din %d posibile. Nu mai încap: %d."),
		N_("Sau lipește textul aici"),
		N_("Formatul se recunoaște singur. Importul adaugă sursele fără să le încerce la portal. Cele existente rămân neschimbate."),
		N_("Adaugă sursele"),
		N_("Exportă toate sursele IPTV"),
		N_("Player și piconuri"),
		N_("Player în buchete"),
		N_("4097 (implicit)"),
		N_("Descarcă piconurile sursei"),
		N_("Setările se aplică acestei surse. Piconurile existente se păstrează."),
		N_("Playerul ales trebuie să fie instalat pe receptor."),
		N_("Salvează"),
		N_("DVB-I: Configurare"),
		N_("Canale de pe internet (DVB-I)"),
		N_("Se citesc setările..."),
		N_("Țara și regiunea"),
		N_("Țara"),
		N_("Regiunea"),
		N_("Țările vin din registrele DVB-I; listele țării se iau singure și se actualizează din oră în oră."),
		N_("Întreabă din nou registrele"),
		N_("Liste din toate țările"),
		N_("Liste din toate țările, după cele ale țării tale"),
		N_("După listele țării tale vin cele ale celorlalte țări, grupate pe țări: canalele merg dacă furnizorul le lasă și din țara ta."),
		N_("Trecere pe internet"),
		N_("Trecere singură pe internet când satelitul nu se recepționează"),
		N_("Da"),
		N_("Nu"),
		N_("Aceeași alegere se găsește în Meniu > Setări > Setări listă de canale: „Când canalul nu pornește, treci singur pe sursa DVB-I a postului”. Este pornită din fabrică și independentă de trecerea pe alt canal cu același nume."),
		N_("Setări listă de canale"),
		N_("Canalul de satelit care are și adresă de internet în listele DVB-I trece singur pe internet "
			"când satelitul nu se recepționează și se întoarce pe satelit când semnalul revine."),
		N_("Listele țării"),
		N_("Listele adevărate ale țării sunt bifate singure; cele de probă ale registrelor le bifezi numai "
			"dacă vrei să le încerci."),
		N_("Reîncărcare"),
		N_("Reîncarcă acum"),
		N_("Descarcă acum listele alese; canalele apar în lista de canale, în buchetul Canale de pe "
			"internet (DVB-I)."),
		N_("Arată lista în lista de canale"),
		N_("Cu Nu, lista Canale de pe internet (DVB-I) iese din lista de canale și nu mai revine singură."),
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
		N_("Pe televizor, ALBASTRU deschide direct tastatura."),
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
		N_("http://"),
		N_("Listele și conturile tale"),
		N_("OK: canalele, filmele și serialele. MENU: date de acces și grupele."),   # 0.7.7 (FLM2)
		N_("Emisiunile trecute"),
		N_("Pentru alt canal: pornește-l pe televizor, apoi apasă Reîncarcă. Pe televizor: MENU pe canal în lista de canale, apoi Emisiunile trecute."),
		N_("Reîncarcă"),
		N_("Canalele apar singure în lista de canale, la Sateliți, pe rândul IPTV. Le poți pune în Favorite și în orice buchet, ca pe celelalte."),
		N_("Actualizează toate"),
		N_("Adaugă ce ți-a dat furnizorul"),
		N_("Ce ai primit"),
		N_("Playlist: o adresă sau un fișier de pe stick"),
		N_("Cont: server, utilizator și parolă"),
		N_("Portal: adresa portalului și adresa MAC"),
		N_("Listă demo: canale gratuite care permit asta"),
		N_("Adresa listei"),
		N_("Server"),
		N_("Utilizator"),
		N_("Parolă"),
		N_("Adresa portalului"),
		N_("Adresa MAC"),
		N_("Fă o adresă MAC"),
		N_("Adresa de dinainte:"),
		N_("Completează rândul:"),
		N_("Portal"),
		N_("Adresa nouă trebuie dată furnizorului. Pentru un cont mutat de pe alt receptor, scrie adresa de acolo. Se păstrează numai la Salvează."),
		N_("Nume (opțional)"),
		N_("Agent utilizator (opțional)"),
		N_("Referer (opțional)"),
		N_("X-User-Agent (opțional)"),
		N_("Tip decodor (opțional)"),
		N_("X-User-Agent și tipul decodorului: goale păstrează valorile salvate."),
		N_("Folosește identitatea implicită"),
		N_("Pentru un abonament legat de alt receptor, scrie aici adresa MAC de pe acela. Unii furnizori nu permit două receptoare pornite în același timp cu aceeași adresă."),
		N_("Scrie MAC-ul contului tău, primit de la furnizor sau copiat de pe receptorul vechi. Schimbarea lui păstrează favoritele și grupele. Sunt acceptate și liniuțe, puncte sau nicio despărțire."),
		N_("Agent utilizator și Referer: goale folosesc valorile implicite."),
		N_("Grupele"),
		N_("Ascunde tot"),
		N_("Arată tot"),
		N_("Caută o grupă sau o țară"),
		N_("Antetele sursei"),
		N_("Valorile salvate se văd în lista surselor. Completează ambele câmpuri; gol revine la valoarea implicită."),
		N_("Salvează antetele"),
		N_("Închide"),
		N_("Caută"),
		N_("Înapoi"),
		N_("Pagina precedentă"),
		N_("Pagina următoare"),
		N_("Adaugă"),
		N_("Parola se vede și după salvare. Dacă adaugi din nou același cont cu altă parolă, canalele din Favorite "
			"rămân."),
		N_("Lista demo: acordul fiecărui canal"),
		N_("Aceleași liste sunt pe televizor, în __DRUM_MENIU__."),
		N_("Interfața web"),
		N_("Interfața web HD Satelit"),
		N_("Pornire și port"),
		N_("Activează HdsWebControl"),
		N_("Port TCP"),
		N_("Schimbă portul"),
		# 0.7.5 (SCR): la cate secunde cere prima pagina imaginea ecranului (1-10 s raman "N s")
		N_("Actualizarea imaginii pe prima pagină web"),
		N_("Oprită"),
		N_("Acces"),
		N_("Aplicații de telefon"),
		N_("Acces din afara casei"),
		N_("Arată parola"),
		N_("Parolă nouă pentru aplicații"),
		N_("Browsere conectate"),
		N_("Deconectează browserele"),
		N_("Cheia pentru scripturi"),
		N_("Cheia"),
		N_("Doar pentru programatori. Browserul obișnuit nu are nevoie de ea. Cheia se vede întreagă mai sus."),
		N_("Mai multe adrese dintr-un fișier"),
		N_("Fișierul cu adrese"),
		N_("Un fișier text cu câte o adresă de listă pe rând (http:// sau https://); numele listei poate sta pe același rând. "
			"Listele se adaugă imediat ce alegi fișierul."),
		N_("La fel merge și fără browser: copiezi prin FTP fișierul iptv.txt în dosarul /etc/enigma2/ al receptorului, iar listele "
			"noi se iau singure în cel mult un minut."),
		N_("O listă de canale (fișier .m3u sau .m3u8) copiată prin FTP în /etc/enigma2/ sau pusă pe un stick sau disc USB apare "
			"singură în IPTV, în cel mult un minut."),
		N_("Arată cheia"),
		N_("Cheie nouă pentru panoul web"),
		N_("Aceleași setări sunt pe televizor, în __DRUM_MENIU__. Tema și culorile paginilor web sunt în "
			"pagina Setări."),
		# 0.7.5 (PRB, 14.11.2026): textele sablonului care lipseau din lista
		N_("Găsește canalele 4K reale"),
		N_("Se citește starea..."),
		N_("Căutarea"),
		N_("Pornește"),
		N_("Oprește"),
		N_("Receptorul citește câteva secunde din fiecare canal de internet care are 4K, UHD sau HDR în nume și află ce trimite de fapt, fără să-l arate pe ecran. Folosește o singură conexiune și se oprește singur când pornești un canal de internet. Canalele 4K adevărate intră în grupa \"4K adevărat\" din lista de canale. Căutarea săptămânală se pornește sau se oprește în Funcțiile televiziunii prin internet."),
		N_("4K adevărat"),
		N_("Cu 4K în nume, dar HD"),
		N_("Aceeași căutare e pe televizor, în __DRUM_MENIU__."),
	),
	"js": (
		N_("Refuză"),
		N_("Portal"),
		N_("Adresa MAC"),
		N_("Găsite: %d. Deja prezente sau repetate: %d. De adăugat: %d. Rânduri necitibile: %d."),
		N_("Surse adăugate: %d. Deschide o sursă sau apasă Actualizează pe ea ca să te conectezi."),
		N_("Ai %d surse din %d posibile. Nu mai încap: %d."),
		N_("Neconectată"),
		N_("Surse: %d din %d."),
		N_("Rândul %d: nu se poate adăuga încă: %s"),
		N_("Fișierul e prea mare. Alege un fișier de cel mult 4 MB și 10000 de rânduri."),
		N_("Adresa de dinainte:"),
		N_("Completează rândul:"),
		N_("Salvează"),
		N_("Adaugă"),
		N_("Player și piconuri"),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		N_("Merge"),
		N_("Oprit pentru țara ta"),
		N_("Adresă moartă"),
		N_("Nu răspunde"),
		N_("Neîncercat"),
		# 0.8.0 DRM1: canalele DVB-I criptate cu DRM
		N_("Protejat (DRM)"),
		N_("protejate (DRM)"),
		N_("Canal protejat (DRM)"),
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
		N_("ascunse din lista de canale până merg din nou"),
		N_("scoase din liste: clipuri și imagini de probă"),
		N_("nu e în lista de canale"),
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
		N_("Încă nu ai adăugat nimic."),
		N_("Fișierul e prea mare pentru pagina web. Pune-l pe un stick sau prin FTP în /etc/enigma2: receptorul îl ia singur."),
		N_("Fișierul nu s-a putut citi."),
		# 0.7.7 (FLM2): pagina sursei (butonul Deschide): randurile si titlul
		N_("Deschide"),
		N_("Canale TV"),
		N_("Filme"),
		N_("Seriale"),
		N_("Antete"),
		N_("Antetele sursei"),
		N_("Grupele"),
		N_("Sezonul"),
		N_("Niciun rezultat."),
		N_("Se încarcă..."),
		N_("Merge."),
		N_("Pornește pe televizor"),
		N_("Actualizează"),
		N_("Șterge"),
		N_("Se trimite..."),
		N_("Gata. Canalele sunt în lista de canale, la Sateliți, pe rândul IPTV."),
		N_("Activarea și portul se aplică după repornirea interfeței. Acum interfața ascultă pe portul"),
		N_(", la adresa"),
		N_("Oprirea e salvată: după repornirea interfeței, paginile nu mai răspund."),
		N_("Telefon:"),
		N_("Browser"),
		N_(", din"),
		N_("Niciun browser conectat cu cod."),
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
		# 0.7.4 (lotul h2 al traducerilor): textele sablonului care lipseau din lista
		N_("(se arată la buton)"),
		N_("Ai pus parolă pentru interfața web: browserele și aplicațiile din casă o cer. O scoți sau o "
			"schimbi în Parola receptorului (/acces-ssh)."),
		N_("Din rețeaua de acasă nu se cere nici cod, nici parolă. O parolă (una singură, pentru tot) pui "
			"numai dacă vrei, în Parola receptorului (/acces-ssh)."),
		N_("Aplicații de telefon: și acasă scrii utilizatorul root și parola ta (pusă în Parola "
			"receptorului)."),
		# 0.7.5 (PRB, 14.11.2026): textele sablonului care lipseau din lista
		N_("Niciunul încă."),
		N_("Niciunul."),
		N_("Receptorul nu a putut citi starea."),
	),
}


PAGINA_IPTV_4K = "<!DOCTYPE html>" + _CAP + "Găsește canalele 4K reale" + _STIL + """<h1>Găsește canalele 4K reale</h1>
<p class="mesaj" id="incarcare">Se citește starea...</p>
<div id="continut" class="ascuns">
  <section class="card">
    <h2>Căutarea</h2>
    <p id="text"></p>
    <progress id="bara" max="100" value="0" style="width:100%"></progress>
    <div class="butoane"><button type="button" class="principal" id="porneste">Pornește</button>
      <button type="button" id="opreste">Oprește</button></div>
    <p class="nota">Receptorul citește câteva secunde din fiecare canal de internet care are 4K, UHD sau HDR în nume și află ce trimite de fapt, fără să-l arate pe ecran. Folosește o singură conexiune și se oprește singur când pornești un canal de internet. Canalele 4K adevărate intră în grupa "4K adevărat" din lista de canale. Căutarea săptămânală se pornește sau se oprește în Funcțiile televiziunii prin internet.</p>
  </section>
  <section class="card">
    <h2>4K adevărat</h2>
    <p class="nota ascuns" id="notaFullHd"></p>
    <div id="buni"></div>
  </section>
  <section class="card">
    <h2>Cu 4K în nume, dar HD</h2>
    <div id="fals"></div>
  </section>
  <p class="nota">Aceeași căutare e pe televizor, în __DRUM_MENIU__.</p>
</div>
""" + _COADA + """var CEAS = null;
function arata(d){
  $("text").textContent = d.text || "";
  var st = d.stare || {};
  $("bara").value = st.total ? Math.round(100 * (st.facute || 0) / st.total) : 0;
  $("porneste").disabled = !!st.lucreaza || !d.surse;
  $("opreste").disabled = !st.lucreaza;
  var buni = [], fals = [];
  (d.canale || []).forEach(function(c){
    var t = c.nume + " · " + c.w + "x" + c.h + " " + c.cod + (c.hdr ? " · " + c.hdr : "");
    (c.e4k ? buni : fals).push(rand(c.e4k ? t : c.nume + " · " + c.eticheta));
  });
  $("notaFullHd").textContent = d.nota_full_hd || "";
  $("notaFullHd").classList.toggle("ascuns", !d.nota_full_hd);
  pune("buni", buni.length ? buni : [gol("Niciunul încă.")]);
  pune("fals", fals.length ? fals : [gol("Niciunul.")]);
  if(st.lucreaza && !CEAS){ CEAS = setInterval(citeste, 2000); }
  if(!st.lucreaza && CEAS){ clearInterval(CEAS); CEAS = null; }
}
function trimite(cale){
  mesaj("Se trimite...");
  return cerere(cale, "POST", new URLSearchParams()).then(function(d){ mesaj(d.message, !d.result); if(d.stare){ arata(d); citeste(); } }).catch(nimicNuRaspunde);
}
function citeste(){
  return cerere("/api/iptv-4k").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi starea."; return; }
    arataPagina(); arata(d);
  }).catch(faraRaspuns);
}
$("porneste").addEventListener("click", function(){ trimite("/api/iptv-4k-porneste"); });
$("opreste").addEventListener("click", function(){ trimite("/api/iptv-4k-opreste"); });
citeste();""" + _SFARSIT


def _traducePagina(sablon, fel="pagina"):
	"""Sablonul in limba receptorului; fara pachetul HdsWebControl (probele de pe PC), sablonul ca atare."""
	try:
		from .traducere_pagini import traduce
	except ImportError:
		return sablon
	return traduce(sablon, TEXTE_PAGINA, fel)
# ---------------------------------------------------------------- sfarsitul traducerii paginilor
