/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hds-hbbtv.js: obiectele OIPF/HbbTV 1.5 pentru aplicatiile HbbTV deschise de hds-navigator --hbbtv.
 * Scris de la zero dupa ETSI TS 102 796 V1.2.1 (anexa A, profilul OIPF DAE) si OIPF DAE vol. 5,
 * cap. 7.2 (aplicatiile), 7.3 (configurarea), 7.9 (controlul parental), 7.13 (video/broadcast), 7.15.3
 * (capabilitatile), 7.16 (programele), 6.4 (oipfObjectFactory).
 *
 * Lansatorul il pune in pagina la inceputul fiecarui document (numai cadrul de sus, numai in modul HbbTV), dupa
 * starea venita de la enigma2: window.__hdsHbbtvStare = {app, canal, config, lista, programe, taste}. Starea se tine
 * la zi prin window.__hdsHbbtvPrimeste(cheie, valoare), chemata de lansator; cheia "ev" aduce evenimentele.
 *
 * PUNTEA spre enigma2: window.webkit.messageHandlers.hdshbbtv.postMessage("comanda arg ...") -> lansatorul o verifica
 * si o trimite mai departe ca rand "HDS-NAV HBBTV comanda arg ...". Argumentele sunt numai numere, ccid-uri sau base64
 * (adresa de la createApplication, textele de tradus), deci nimic din pagina nu poate rupe un rand. Comenzile: arata,
 * ascunde, taste, distruge, aplicatie, leaga, canal, urmator, anterior, opreste, elibereaza, ecran-intreg, fereastra si
 * (hds-navigator 0.7.0) tradu.
 *
 * OBIECTELE: <object type="..."> nu are metode in WebKit, iar elementele se pot face oricand (in HTML, din
 * JavaScript, cu oipfObjectFactory) si isi pot primi tipul mai tarziu. De aceea metodele si proprietatile stau pe
 * HTMLObjectElement.prototype si aleg, la fiecare chemare, dupa tipul elementului; starea fiecarui element sta intr-un
 * WeakMap. Pe un <object> de alt tip, numele acestea se poarta ca proprietati obisnuite ale elementului. width si
 * height raman cele ale elementului (standardul le cere asa).
 *
 * FEREASTRA VIDEO: pozitia si marimea obiectului video/broadcast legat merg la enigma2 ("fereastra x y l i",
 * puncte CSS ale paginii de 1280x720; "ecran-intreg 1" la setFullScreen(true)), care muta imaginea canalului acolo.
 *
 * GAURA: la televizoare obiectul video/broadcast e o fereastra in planul grafic: in dreptunghiul lui nu se vede nimic din
 * ce pagina deseneaza sub el (fundalul lui, al parintilor, al panourilor de dedesubt), iar ce e peste el ramane. Unele
 * aplicatii se bizuie pe asta (un fundal gri pe obiect, un panou negru sub el). WebKit nu are asa ceva in CSS, deci aici:
 * (1) fundalul obiectelor video/broadcast e mereu transparent (o regula de stil pusa in pagina); (2) pentru obiectul
 * legat, elementele de sub el (document.elementsFromPoint pe o grila peste dreptunghi) primesc in locul culorii de
 * fundal patru benzi de aceeasi culoare in jurul dreptunghiului, deci in afara lui arata la fel (si bordura de aceeasi
 * culoare); un element cu imagini de fundal (un degradeu pe toata pagina, o poza) primeste o masca opaca peste tot, afara
 * de dreptunghi, unde raman numai cutiile urmasilor lui aflati peste obiect (fara masca posibila, imaginile raman,
 * afara de cazul in care dreptunghiul acopera tot elementul); un element aflat
 * cu totul sub obiect, fara nimic al lui peste obiect, se ascunde (opacity 0). Ce e peste obiect nu se atinge. Textul si
 * pozele de sub obiect ale elementelor care ies din dreptunghi raman (televizoarele le ascund). Valorile vechi se pun la
 * loc cand obiectul se muta, se elibereaza sau cand aplicatia schimba elementul.
 *
 * Unde sta fisierul: in pachetul navigatorului (/usr/share/hds-navigator/hds-hbbtv.js) si in pachetul enigma2
 * (Plugins/Extensions/HdsNavigator/hds-hbbtv.js); lansator.py da navigatorului copia din enigma2 cu --hbbtv-js cand o
 * are, deci o reparatie a stratului ajunge si printr-o actualizare a pachetului enigma2.
 *
 * TRADUCEREA ("Tradu HbbTV", oprita din fabrica): cu config.traducere (pusa de enigma2 numai pe stdin), textele vazute
 * ale paginii se traduc prin receptor si se inlocuiesc pe loc: prin puntea lansatorului (comanda "tradu", raspunsul ca
 * eveniment "traducere") cand lansatorul o are (window.__hdsHbbtvStare.lansator.tradu, hds-navigator 0.7.0), altfel
 * prin interfata web (portul si cheia pornirii); vezi sectiunea "traducerea textelor vazute" de mai jos.
 *
 * CARUSELUL: o aplicatie venita numai prin caruselul DSM-CC al canalului vine de la serverul local al receptorului;
 * adresele dvb:// ale aceluiasi carusel ramase in pagina se rescriu spre el (vezi "adresele dvb:// ale caruselului").
 *
 * FILMELE APLICATIILOR (obiectul A/V: video/mp4, application/dash+xml, HLS, video/mpeg, sunetul): cu un lansator care
 * lasa comanda "av" (hds-navigator 0.7.0-r2, window.__hdsHbbtvStare.lansator.av), filmul il reda playerul receptorului sub
 * pagina; vezi "obiectul A/V" mai jos. Fara acea comanda tipurile nu exista, ca inainte.
 *
 * Ce NU e aici: DRM, citirea caruselului (o face receptorul), evenimentele de flux din carusel, <video> si MSE (WebKit e
 * construit fara video), subtitrarile filmelor, derularea rapida.
 */
(function () {
    "use strict";

    if (window.__hdsHbbtv)
        return;
    try {
        Object.defineProperty(window, "__hdsHbbtv", { value: 1, writable: false, configurable: false, enumerable: false });
    } catch (x) {
        return;
    }

    /* ------------------------------------------------------------ starea, de la enigma2 */

    var S = { app: null, canal: null, config: {}, lista: [], programe: [], taste: null };
    var initial = window.__hdsHbbtvStare;
    /* ce stie lansatorul (hds-navigator 0.7.0: versiunea, "tradu", schema dvb); gol la lansatoarele mai vechi */
    var LANSATOR = initial && initial.lansator && typeof initial.lansator === "object" ? initial.lansator : {};
    /* filmele aplicatiilor (obiectul A/V, mai jos): numai cand lansatorul lasa comanda "av" (hds-navigator 0.7.0-r2) */
    var AV_TIPURI = ["video/mp4", "audio/mp4", "video/mpeg", "audio/mpeg", "audio/mp3", "application/dash+xml",
        "application/vnd.apple.mpegurl", "application/x-mpegurl"];
    var avPornit = LANSATOR.av === 1 || LANSATOR.av === true;
    if (initial && typeof initial === "object") {
        for (var k in S) {
            if (Object.prototype.hasOwnProperty.call(initial, k) && initial[k] !== undefined)
                S[k] = initial[k];
        }
    }
    try {
        delete window.__hdsHbbtvStare;
    } catch (x) {
        window.__hdsHbbtvStare = undefined;
    }
    if (!S.config || typeof S.config !== "object")
        S.config = {};
    if (!Array.isArray(S.lista))
        S.lista = [];
    if (!Array.isArray(S.programe))
        S.programe = [];

    function legata() {
        return !!(S.app && S.app.legat);
    }

    /* ------------------------------------------------------------ puntea */

    var punte = null;
    try {
        punte = window.webkit.messageHandlers.hdshbbtv;
    } catch (x) {
        punte = null;
    }
    var ARG_BUN = /^[A-Za-z0-9+\/=._:,-]{1,2048}$/;

    function trimite() {
        var parti = [];
        for (var i = 0; i < arguments.length; i++) {
            var a = String(arguments[i]);
            parti.push(ARG_BUN.test(a) ? a : "-");
        }
        if (!punte)
            return;
        try {
            punte.postMessage(parti.join(" "));
        } catch (x) {
            /* lansatorul nu are puntea (de exemplu o pagina deschisa altfel): nimic de facut */
        }
    }

    function b64(text) {
        text = String(text);
        var bin = "";
        if (typeof TextEncoder === "function") {
            var o = new TextEncoder().encode(text);
            for (var i = 0; i < o.length; i++)
                bin += String.fromCharCode(o[i]);
        } else {
            bin = unescape(encodeURIComponent(text));
        }
        return btoa(bin);
    }

    function intreg(v) {
        var n = Number(v);
        return isFinite(n) ? Math.floor(n) : NaN;
    }

    function eroareSecuritate() {
        var e = new Error("SecurityError");
        e.name = "SecurityError";
        return e;
    }

    /* Colectiile OIPF (ChannelList, ProgrammeCollection ...): un sir obisnuit cu length si item(i). */
    function colectie(sir) {
        var c = Array.prototype.slice.call(sir || []);
        Object.defineProperty(c, "item", {
            value: function (i) {
                i = intreg(i);
                return i >= 0 && i < this.length ? this[i] : undefined;
            }
        });
        return c;
    }

    function constante(tinta, lista) {
        for (var n in lista)
            Object.defineProperty(tinta, n, { value: lista[n], enumerable: true });
    }

    /* Evenimentele obiectelor: functia "onX" a elementului, apoi evenimentul DOM X pe element (fara bubbling), mereu
     * dupa codul care l-a pornit (aplicatiile isi pun ascultatorii si dupa chemare). Ordinea se pastreaza. */
    function eveniment(el, nume, date, argumente) {
        setTimeout(function () {
            var f = stare(el).h["on" + nume];
            if (typeof f === "function") {
                try {
                    f.apply(el, argumente || []);
                } catch (e) {
                    setTimeout(function () { throw e; }, 0);
                }
            }
            var ev;
            try {
                ev = new Event(nume, { bubbles: false, cancelable: false });
            } catch (x) {
                ev = document.createEvent("Event");
                ev.initEvent(nume, false, false);
            }
            for (var k in date || {}) {
                try {
                    Object.defineProperty(ev, k, { value: date[k], enumerable: true });
                } catch (x) {
                    /* proprietatea exista deja pe eveniment */
                }
            }
            el.dispatchEvent(ev);
        }, 0);
    }

    /* ------------------------------------------------------------ Channel, Programme */

    var CANAL = { TYPE_TV: 0, TYPE_RADIO: 1, TYPE_OTHER: 2, ID_ANALOG: 0, ID_DVB_C: 10, ID_DVB_S: 11, ID_DVB_T: 12,
        ID_DVB_SI_DIRECT: 13, ID_DVB_C2: 14, ID_DVB_S2: 15, ID_DVB_T2: 16, ID_ISDB_C: 20, ID_ISDB_S: 21, ID_ISDB_T: 22,
        ID_ATSC_T: 30, ID_IPTV_SDS: 40, ID_IPTV_URI: 41 };

    function Channel(d) {
        d = d || {};
        this.channelType = d.channelType !== undefined ? d.channelType : 0;
        this.idType = d.idType !== undefined ? d.idType : 11;
        this.ccid = d.ccid;
        this.dsd = d.dsd !== undefined ? d.dsd : "";
        this.onid = d.onid;
        this.tsid = d.tsid;
        this.sid = d.sid;
        this.nid = d.nid;
        this.name = d.name;
        this.majorChannel = d.majorChannel;
        this.minorChannel = undefined;
        this.hidden = false;
        this.locked = false;
        this.manualBlock = false;
        this.isHD = !!d.isHD;
    }
    constante(Channel.prototype, CANAL);

    function canalDin(d) {
        return d && typeof d === "object" ? new Channel(d) : null;
    }

    function ParentalRating(d) {
        this.name = String(d.varsta);
        this.scheme = "dvb-si";
        this.value = d.varsta;
        this.labels = 0;
        this.region = (S.config.tara2 || "").toLowerCase();
    }

    function Programme(d) {
        d = d || {};
        this.name = d.name || "";
        this.description = d.description || "";
        this.longDescription = d.longDescription || "";
        this.startTime = d.startTime;
        this.duration = d.duration;
        this.channelID = d.channelID;
        this.programmeID = d.programmeID;
        this.programmeIDType = d.programmeIDType !== undefined ? d.programmeIDType : 1;
        this.parentalRatings = colectie(d.varsta ? [new ParentalRating(d)] : []);
    }
    constante(Programme.prototype, { ID_TVA_CRID: 0, ID_DVB_EVENT: 1, ID_TVA_GROUP_CRID: 2 });
    Programme.prototype.getSIDescriptors = function () {
        return null;
    };

    /* present/following, numai cele care nu s-au terminat */
    function programele() {
        var acum = Date.now() / 1000;
        return colectie(S.programe.filter(function (p) {
            return p && (p.startTime === undefined || p.duration === undefined || p.startTime + p.duration >= acum);
        }).map(function (p) { return new Programme(p); }));
    }

    function canalCurent() {
        return legata() ? canalDin(S.canal) : null;
    }

    function cautaInLista(onid, tsid, sid) {
        for (var i = 0; i < S.lista.length; i++) {
            var c = S.lista[i];
            if (c && c.onid === onid && c.sid === sid && (isNaN(tsid) || c.tsid === tsid))
                return c;
        }
        return null;
    }

    function cautaCcid(ccid) {
        if (S.canal && S.canal.ccid === ccid)
            return S.canal;
        for (var i = 0; i < S.lista.length; i++) {
            if (S.lista[i] && S.lista[i].ccid === ccid)
                return S.lista[i];
        }
        return null;
    }

    /* ChannelConfig (7.13.9): numai channelList (anexa A); lista e cea a buchetului de acum din enigma2. */
    function listaCanale() {
        var l = colectie(S.lista.map(canalDin));
        Object.defineProperty(l, "getChannel", {
            value: function (ccid) {
                return canalDin(cautaCcid(String(ccid)));
            }
        });
        Object.defineProperty(l, "getChannelByTriplet", {
            value: function (onid, tsid, sid) {
                return canalDin(cautaInLista(intreg(onid), intreg(tsid), intreg(sid)));
            }
        });
        return l;
    }

    /* ------------------------------------------------------------ Keyset, Application */

    var TASTE = { RED: 0x1, GREEN: 0x2, YELLOW: 0x4, BLUE: 0x8, NAVIGATION: 0x10, VCR: 0x20, SCROLL: 0x40, INFO: 0x80,
        NUMERIC: 0x100, ALPHA: 0x200, OTHER: 0x400 };
    /* telecomanda nu are litere, iar OTHER nu e in HbbTV 1.5 (anexa A) */
    var TASTE_MAXIM = 0x1FF;
    var masca = S.taste && isFinite(S.taste.value) ? (S.taste.value & TASTE_MAXIM) : TASTE_MAXIM;

    function Keyset() {}
    constante(Keyset.prototype, TASTE);
    Object.defineProperty(Keyset.prototype, "value", { get: function () { return masca; } });
    Object.defineProperty(Keyset.prototype, "maximumValue", { get: function () { return TASTE_MAXIM; } });
    Keyset.prototype.setValue = function (valoare) {
        var v = intreg(valoare);
        masca = isNaN(v) ? 0 : (v & TASTE_MAXIM);
        trimite("taste", masca);
        return masca;
    };
    var keyset = new Keyset();

    function ApplicationPrivateData() {}
    Object.defineProperty(ApplicationPrivateData.prototype, "keyset", { get: function () { return keyset; } });
    Object.defineProperty(ApplicationPrivateData.prototype, "currentChannel", { get: canalCurent });
    ApplicationPrivateData.prototype.getFreeMem = function () {
        return S.config.memorie || 0;
    };
    var dateAplicatie = new ApplicationPrivateData();

    var vizibila = !!(S.app && S.app.vizibil);

    function Application() {}
    Object.defineProperty(Application.prototype, "visible", { get: function () { return vizibila; } });
    Object.defineProperty(Application.prototype, "privateData", { get: function () { return dateAplicatie; } });
    Application.prototype.show = function () {
        if (!vizibila) {
            vizibila = true;
            trimite("arata");
        }
    };
    Application.prototype.hide = function () {
        if (vizibila) {
            vizibila = false;
            trimite("ascunde");
        }
    };
    /* createApplication("dvb://current.ait/<org>.<app>...") spre o aplicatie care nu e in AIT-ul canalului (S.app.ait,
     * lista celor de pornit trimisa de enigma2): null pe loc, ca pe televizor. Aplicatia trece atunci singura pe adresa
     * ei http (o bara de pornire face "if (createApplication(dvb)) destroyApplication(); else document.location.href =
     * http"), in loc sa se distruga pe ea crezand ca a pornit-o pe cealalta. Fara lista: raspunsul ramane la enigma2. */
    function nesemnalata(u) {
        var m = /^dvb:\/\/current\.ait\/([0-9a-f]{1,8})\.([0-9a-f]{1,4})(?:[?#]|$)/i.exec(u);
        var lista = S.app && S.app.ait;
        if (!m || !Array.isArray(lista) || !lista.length)
            return false;
        var org = parseInt(m[1], 16), id = parseInt(m[2], 16);
        for (var i = 0; i < lista.length; i++) {
            if (Array.isArray(lista[i]) && lista[i][0] === org && lista[i][1] === id)
                return false;
        }
        return true;
    }
    Application.prototype.createApplication = function (uri) {
        var u = typeof uri === "string" ? uri.trim() : "";
        if (!u || u.length > 2048 || !/^(https?:\/\/|dvb:\/\/)/i.test(u))
            return null;
        if (nesemnalata(u))
            return null;
        trimite("aplicatie", b64(u));
        return this;
    };
    Application.prototype.destroyApplication = function () {
        trimite("distruge");
    };
    var aplicatie = new Application();

    /* ------------------------------------------------------------ elementele <object> */

    var stari = typeof WeakMap === "function" ? new WeakMap() : null;
    var stariVechi = [];

    function stare(el) {
        var s = stari ? stari.get(el) : null;
        if (!stari) {
            for (var i = 0; i < stariVechi.length; i++) {
                if (stariVechi[i][0] === el)
                    s = stariVechi[i][1];
            }
        }
        if (!s) {
            s = { h: {}, x: {}, vb: null };
            if (stari)
                stari.set(el, s);
            else
                stariVechi.push([el, s]);
        }
        return s;
    }

    function tipul(el) {
        var t = el.getAttribute ? el.getAttribute("type") : "";
        return t ? String(t).trim().toLowerCase() : "";
    }

    var facute = [];   /* elementele facute de oipfObjectFactory (pot sa nu fie in document) */

    function elementeDeTip(t) {
        var rez = [];
        var toate = document.getElementsByTagName("object");
        for (var i = 0; i < toate.length; i++) {
            if (tipul(toate[i]) === t)
                rez.push(toate[i]);
        }
        facute.forEach(function (el) {
            if (tipul(el) === t && rez.indexOf(el) < 0)
                rez.push(el);
        });
        return rez;
    }

    /* --- application/oipfApplicationManager (7.2.1): getOwnerApplication, onLowMemory, onApplicationLoadError */
    var MANAGER = {
        metode: {
            getOwnerApplication: function () { return aplicatie; },
            getChildApplications: function () { return colectie([]); },
            gc: function () {}
        },
        evenimente: ["onLowMemory", "onApplicationLoadError"]
    };

    /* --- application/oipfConfiguration (7.3.1): configuration (limbile, tara) si localSystem */
    function Configuration() {}
    ["preferredAudioLanguage", "preferredSubtitleLanguage", "preferredUILanguage"].forEach(function (n) {
        Object.defineProperty(Configuration.prototype, n, { get: function () { return S.config[n] || ""; }, enumerable: true });
    });
    Object.defineProperty(Configuration.prototype, "countryId", { get: function () { return S.config.countryId || ""; },
        enumerable: true });
    Object.defineProperty(Configuration.prototype, "countryID", { get: function () { return S.config.countryId || ""; } });
    Object.defineProperty(Configuration.prototype, "regionId", { get: function () { return 0; } });

    function LocalSystem() {}
    var SISTEM = { vendorName: "vendorName", modelName: "modelName", familyName: "familyName",
        softwareVersion: "softwareVersion", hardwareVersion: "hardwareVersion", releaseVersion: "releaseVersion",
        majorVersion: "majorVersion", minorVersion: "minorVersion" };
    Object.keys(SISTEM).forEach(function (n) {
        Object.defineProperty(LocalSystem.prototype, n, { get: function () {
            var v = S.config[SISTEM[n]];
            return v === undefined ? "" : v;
        }, enumerable: true });
    });
    constante(LocalSystem.prototype, { systemReady: true, oipfProfile: "OITF_HD_UIPROF", pvrEnabled: false,
        ciplusEnabled: false, powerState: 1 });
    var CONFIGURARE = {
        proprietati: {
            configuration: { get: function () { return new Configuration(); } },
            localSystem: { get: function () { return new LocalSystem(); } }
        }
    };

    /* --- application/oipfCapabilities (7.15.3; HbbTV cap. 10.2.4) */
    function livrare() {
        var l = Array.isArray(S.config.livrare) && S.config.livrare.length ? S.config.livrare : ["DVB_S"];
        return l.filter(function (x) { return /^[A-Z0-9_]{2,16}$/.test(x); });
    }

    function profilUi() {
        return "OITF_HD_UIPROF" + livrare().map(function (x) { return "+" + x; }).join("");
    }

    /* Profilele filmelor (HbbTV cap. 10.2.4, numele din anexa de formate), numai cu obiectul A/V: MP4 si TS cu H.264
     * (SD si HD) si HE-AAC, sunetul MP3 si HE-AAC. DVB-DASH (transport="dash") numai cu AV_DASH: aplicatiile care il vad
     * aleg DASH in locul MP4 si HLS. Masurat pe receptor: MP4 si HLS din mediateci si un DASH cu avc1 merg, un DVB-DASH
     * cu avc3 (parametrii in flux) ramane negru; pana la o proba pe DASH-ul unei mediateci, aplicatiile primesc MP4 sau
     * HLS. Tipul application/dash+xml ramane (aplicatiile care il folosesc oricum il au). */
    var AV_DASH = false;
    var AV_PROFILE = ["MP4_AVC_SD_25_HEAAC", "MP4_AVC_HD_25_HEAAC"];

    function profileAv() {
        if (!avPornit)
            return "";
        var p = AV_PROFILE.map(function (n) { return "<video_profile name=\"" + n + "\" type=\"video/mp4\"/>"; });
        p.push("<video_profile name=\"TS_AVC_SD_25_HEAAC\" type=\"video/mpeg\"/>",
            "<video_profile name=\"TS_AVC_HD_25_HEAAC\" type=\"video/mpeg\"/>",
            "<audio_profile name=\"MPEG1_L3\" type=\"audio/mpeg\"/>", "<audio_profile name=\"HEAAC\" type=\"audio/mp4\"/>");
        if (AV_DASH) {
            AV_PROFILE.forEach(function (n) {
                p.push("<video_profile name=\"" + n + "\" type=\"video/mp4\" transport=\"dash\"/>");
            });
            p.push("<audio_profile name=\"HEAAC\" type=\"audio/mp4\" transport=\"dash\"/>");
        }
        return p.join("");
    }

    /* Fara +TRICK_MODE (filmele merg numai cu viteza 0 si 1); fara <drm>, +DL, +PVR. */
    function textCapabilitati() {
        return "<profilelist><ui_profile name=\"" + profilUi() + "\"><ext><parentalcontrol schemes=\"dvb-si\">true" +
            "</parentalcontrol></ext></ui_profile>" + profileAv() + "<clientMetadata type=\"dvb-si\">true</clientMetadata>" +
            "</profilelist>";
    }

    var capabilitati = null;
    var CAPABILITATI = {
        proprietati: {
            xmlCapabilities: { get: function () {
                if (!capabilitati)
                    capabilitati = new DOMParser().parseFromString(textCapabilitati(), "text/xml");
                return capabilitati;
            } },
            extraSDVideoDecodes: { get: function () { return 0; } },
            extraHDVideoDecodes: { get: function () { return 0; } }
        },
        metode: {
            hasCapability: function (nume) {
                var n = String(nume);
                if (n === "OITF_HD_UIPROF" || n === profilUi())
                    return true;
                return livrare().some(function (x) { return n === x || n === "+" + x; });
            }
        }
    };

    /* --- application/oipfParentalControlManager (7.9.1): parentalRatingSchemes cu schema dvb-si */
    function schemaDvbSi() {
        var etichete = [];
        for (var v = 4; v <= 18; v++)
            etichete.push(String(v));
        var s = colectie(etichete);
        Object.defineProperty(s, "name", { value: "dvb-si", enumerable: true });
        Object.defineProperty(s, "threshold", { value: new ParentalRating({ varsta: 18 }), enumerable: true });
        Object.defineProperty(s, "iconUri", { value: function () { return null; } });
        Object.defineProperty(s, "indexOf", { value: function (x) { return etichete.indexOf(String(x)); } });
        return s;
    }
    var PARENTAL = {
        proprietati: {
            parentalRatingSchemes: { get: function () {
                var l = colectie([schemaDvbSi()]);
                Object.defineProperty(l, "getParentalRatingScheme", {
                    value: function (n) { return String(n).toLowerCase() === "dvb-si" ? l[0] : null; }
                });
                return l;
            } }
        }
    };

    /* --- video/broadcast (7.13.1 cu A.2.4) */
    var NECONECTAT = 0, CONECTARE = 1, PREZENTARE = 2, OPRIT = 3;
    var vbActiv = null;   /* o singura instanta activa (A.2.4.2) */

    function vb(el) {
        var s = stare(el);
        if (!s.vb)
            s.vb = { joc: NECONECTAT, inainte: NECONECTAT, ecranIntreg: false, cerut: null, fereastra: "", privitor: null,
                ceas: null, inPagina: false };
        return s.vb;
    }

    /* true: elementul e in document; false: nu e; null: documentul nu spune */
    function conectat(el) {
        if (typeof el.isConnected === "boolean")
            return el.isConnected;
        var r = document.documentElement;
        return r && typeof r.contains === "function" ? r.contains(el) : null;
    }

    /* Obiectul activ a fost in pagina, iar pagina l-a scos (si-a refacut continutul, de obicei cu un obiect nou in
     * locul lui): nu mai tine canalul. Starea lui trece in NECONECTAT fara evenimente si fara nicio comanda: imaginea
     * merge mai departe, iar obiectul nou o ia cand se leaga. */
    function scoateActivulDinPagina() {
        if (!vbActiv)
            return;
        var v = vb(vbActiv), c = conectat(vbActiv);
        if (c === true)
            v.inPagina = true;
        if (c !== false || !v.inPagina)
            return;
        urmareste(vbActiv, false);
        v.joc = NECONECTAT;
        v.fereastra = "";
        vbActiv = null;
    }

    function schimbaStarea(el, joc, eroare) {
        var v = vb(el);
        if (v.joc === joc && eroare === undefined)
            return;
        v.joc = joc;
        eveniment(el, "PlayStateChange", { state: joc, error: eroare }, [joc, eroare]);
    }

    function altulActiv(el) {
        if (vbActiv && vbActiv !== el)
            scoateActivulDinPagina();
        return vbActiv && vbActiv !== el && vb(vbActiv).joc !== NECONECTAT;
    }

    /* --- gaura (vezi antetul) */
    var NS_XHTML = "http://www.w3.org/1999/xhtml";
    var STIL_ID = "hds-hbbtv-stil";
    /* cele doua :not(#...) ridica prioritatea regulii peste o regula a aplicatiei care numeste obiectul dupa id; cu
     * filmele aplicatiilor, si obiectele A/V */
    var STIL_TEXT = ["video/broadcast"].concat(avPornit ? AV_TIPURI : []).map(function (t) {
        return "object[type=\"" + t + "\" i]:not(#hds-a):not(#hds-b)";
    }).join(",") + "{background:transparent !important}";
    var GAURA_MARGINE = 4000;   /* benzile trec de element; le taie marginea lui (la radacina, ecranul) */
    var LATURI = ["top", "right", "bottom", "left"];
    var gaura = { el: null, drept: "", cheie: "", atinse: [], privitor: null, schimbat: false, ticuri: 0 };
    var GAURA_CAUTARE_TICURI = 4;   /* elementele de dedesubt se cauta din nou la 4 verificari (2 s) */
    var GAURA_TICURI_LA_INCEPUT = 10;   /* dupa legare sau o schimbare, la fiecare verificare (panourile vin mai tarziu) */
    var iduri = typeof WeakMap === "function" ? new WeakMap() : null;
    var idUrmator = 1;

    /* Regula de stil, o singura data in document (si din nou daca aplicatia a scos-o). Elementul se face in spatiul de
     * nume XHTML: multe aplicatii sunt documente XML. */
    function stilPus() {
        var d = window.document;
        if (!d || typeof d.createElementNS !== "function" || typeof d.getElementById !== "function" || !d.documentElement)
            return;
        var st = d.getElementById(STIL_ID);
        if (st && st.parentNode)
            return;
        try {
            st = d.createElementNS(NS_XHTML, "style");
            st.setAttribute("id", STIL_ID);
            st.textContent = STIL_TEXT;
            (d.head || d.documentElement).appendChild(st);
        } catch (x) {
            /* documentul nu primeste elemente (de exemplu un document de alt tip) */
        }
    }

    function idElement(e) {
        if (!iduri)
            return "";
        var n = iduri.get(e);
        if (!n) {
            n = idUrmator++;
            iduri.set(e, n);
        }
        return n;
    }

    function culoareVazuta(c) {
        if (!c || c === "transparent")
            return false;
        var m = /^rgba\([^,]+,[^,]+,[^,]+,\s*([\d.]+)\s*\)$/.exec(c);
        return !m || parseFloat(m[1]) > 0;
    }

    /* Punctele cautarii pe o latura: capetele (cu 2 puncte inauntru) si intre ele cel putin 3, cel mult la PAS_CAUTARE
     * puncte CSS unul de altul (cel mult PUNCTE_MAXIM pe latura). */
    var PAS_CAUTARE = 120, PUNCTE_MAXIM = 11;

    function puncte(a, b) {
        var n = Math.max(5, Math.min(PUNCTE_MAXIM, Math.ceil((b - a) / PAS_CAUTARE) + 1)), rez = [];
        for (var i = 0; i < n; i++)
            rez.push(i === 0 ? a + 2 : i === n - 1 ? b - 2 : a + (b - a) * i / (n - 1));
        return rez;
    }

    /* Elementele de sub obiect (dupa el in ordinea de desen) si cele de peste el, din punctele unei grile peste
     * dreptunghi; un punct in care obiectul nu e gasit nu spune nimic. */
    function dedesubt(el, x0, y0, x1, y1) {
        var d = window.document, rez = { sub: [], peste: [] };
        if (typeof d.elementsFromPoint !== "function")
            return rez;
        var xs = puncte(x0, x1), ys = puncte(y0, y1);
        for (var i = 0; i < xs.length; i++) {
            for (var j = 0; j < ys.length; j++) {
                var l = d.elementsFromPoint(xs[i], ys[j]) || [];
                var k = Array.prototype.indexOf.call(l, el);
                if (k < 0)
                    continue;
                for (var m = 0; m < l.length; m++) {
                    var lista = m < k ? rez.peste : m > k ? rez.sub : null;
                    if (lista && lista.indexOf(l[m]) < 0)
                        lista.push(l[m]);
                }
            }
        }
        return rez;
    }

    /* Tot ce deseneaza elementul pe ecran: cutia lui si continutul (textul si elementele din el, si cele iesite din
     * cutie), taiat la marginile ferestrei (ce e in afara ei nu se vede oricum). */
    function cuprins(e) {
        var r = e.getBoundingClientRect(), u = { left: r.left, top: r.top, right: r.right, bottom: r.bottom };
        try {
            var g = window.document.createRange();
            g.selectNodeContents(e);
            var c = g.getBoundingClientRect();
            if (c.width > 0 || c.height > 0) {
                u.left = Math.min(u.left, c.left);
                u.top = Math.min(u.top, c.top);
                u.right = Math.max(u.right, c.right);
                u.bottom = Math.max(u.bottom, c.bottom);
            }
        } catch (x) {
            return null;
        }
        u.left = Math.max(u.left, 0);
        u.top = Math.max(u.top, 0);
        u.right = Math.min(u.right, window.innerWidth);
        u.bottom = Math.min(u.bottom, window.innerHeight);
        return u;
    }

    /* Are elementul e ceva peste obiectul el? Cele gasite peste el, apoi fiecare urmas asezat (position, opacitate,
     * transformare), cautat in centrul lui. Un element cu prea multi urmasi sau un punct in care obiectul lipseste
     * se socotesc "da" (elementul nu se ascunde). */
    var URMASI_MAXIM = 300;

    function areCevaPeste(e, el, peste) {
        if (peste.some(function (p) { return e.contains(p); }))
            return true;
        var toate = e.getElementsByTagName("*");
        if (toate.length > URMASI_MAXIM)
            return true;
        for (var i = 0; i < toate.length; i++) {
            var c = toate[i], cs = window.getComputedStyle(c);
            if (cs.position === "static" && cs.opacity === "1" && (!cs.transform || cs.transform === "none"))
                continue;
            var r = c.getBoundingClientRect();
            if (!(r.width > 0 && r.height > 0))
                continue;
            var l = window.document.elementsFromPoint(r.left + r.width / 2, r.top + r.height / 2) || [];
            var ic = Array.prototype.indexOf.call(l, c), iel = Array.prototype.indexOf.call(l, el);
            if (ic >= 0 && (iel < 0 || ic < iel))
                return true;
        }
        return false;
    }

    /* Patru benzi de culoarea c in jurul gaurii (coordonate fata de marginea elementului de l x i). */
    function benzi(c, gx0, gy0, gx1, gy1, l, i) {
        var M = GAURA_MARGINE, g = "linear-gradient(" + c + "," + c + ")";
        var b = [[-M, -M, l + 2 * M, gy0 + M], [-M, gy1, l + 2 * M, i - gy1 + M], [-M, gy0, gx0 + M, gy1 - gy0],
            [gx1, gy0, l - gx1 + M, gy1 - gy0]];
        return {
            "background-color": "transparent",
            "background-image": [g, g, g, g].join(","),
            "background-position": b.map(function (z) { return z[0] + "px " + z[1] + "px"; }).join(","),
            "background-size": b.map(function (z) { return Math.max(0, z[2]) + "px " + Math.max(0, z[3]) + "px"; }).join(","),
            "background-repeat": "no-repeat",
            "background-origin": "border-box",
            "background-attachment": "scroll"
        };
    }

    /* Bordura plina de aceeasi culoare cu fundalul (des folosita la colturile rotunjite): se face transparenta, iar
     * benzile fundalului (desenate si sub bordura) o inlocuiesc in afara gaurii, deci arata la fel. */
    function borduraCaFundalul(cs) {
        var clip = listaCss(cs.backgroundClip), vreuna = false;
        if (clip.length && clip[clip.length - 1] !== "border-box")
            return false;
        for (var i = 0; i < LATURI.length; i++) {
            var l = "border-" + LATURI[i];
            if (!(parseFloat(cs.getPropertyValue(l + "-width")) > 0))
                continue;
            if (cs.getPropertyValue(l + "-style") !== "solid" || cs.getPropertyValue(l + "-color") !== cs.backgroundColor)
                return false;
            vreuna = true;
        }
        return vreuna;
    }

    function faraBordura(z) {
        LATURI.forEach(function (l) { z["border-" + l + "-color"] = "transparent"; });
        return z;
    }

    /* O lista CSS calculata ("a, f(b, c), d"), despartita la virgulele din afara parantezelor. */
    function listaCss(v) {
        var rez = [], adanc = 0, bucata = "";
        v = String(v || "");
        for (var i = 0; i < v.length; i++) {
            var c = v.charAt(i);
            if (c === "(")
                adanc++;
            else if (c === ")")
                adanc--;
            if (c === "," && adanc === 0) {
                rez.push(bucata.trim());
                bucata = "";
            } else
                bucata += c;
        }
        if (bucata.trim())
            rez.push(bucata.trim());
        return rez;
    }

    /* Imaginile de fundal ale elementului raman deasupra, benzile culorii vin sub ele (ultimele straturi). */
    function benziSubImagini(cs, noi) {
        var imagini = listaCss(cs.backgroundImage), n = imagini.length;
        function pentruImagini(valoare) {
            var l = listaCss(valoare), rez = [];
            for (var i = 0; i < n; i++)
                rez.push(l.length ? l[i % l.length] : "");
            return rez;
        }
        var vechi = { "background-image": imagini, "background-position": pentruImagini(cs.backgroundPosition),
            "background-size": pentruImagini(cs.backgroundSize), "background-repeat": pentruImagini(cs.backgroundRepeat),
            "background-origin": pentruImagini(cs.backgroundOrigin),
            "background-attachment": pentruImagini(cs.backgroundAttachment) };
        for (var p in vechi) {
            if (vechi[p].some(function (x) { return !x; }))
                return null;
            noi[p] = vechi[p].concat(listaCss(noi[p]).length === 4 ? listaCss(noi[p]) :
                [noi[p], noi[p], noi[p], noi[p]]).join(",");
        }
        return noi;
    }

    /* Deseneaza elementul ceva al lui, nu numai prin urmasi (fundal, bordura, umbra, text direct, imagine, panza)? Un
     * invelis gol si transparent peste imagine (des pus peste obiect, pentru indicatii) nu deseneaza nimic. */
    function deseneazaCeva(c) {
        var cs = window.getComputedStyle(c);
        if (!cs || cs.visibility !== "visible" || cs.display === "none" || cs.opacity === "0")
            return false;
        if (culoareVazuta(cs.backgroundColor) || (cs.backgroundImage && cs.backgroundImage !== "none"))
            return true;
        if (cs.boxShadow && cs.boxShadow !== "none")
            return true;
        for (var i = 0; i < LATURI.length; i++) {
            var l = "border-" + LATURI[i];
            if (parseFloat(cs.getPropertyValue(l + "-width")) > 0 && culoareVazuta(cs.getPropertyValue(l + "-color")))
                return true;
        }
        if (/^(img|canvas|svg|video|iframe|input|textarea|select|embed)$/i.test(String(c.tagName || "")))
            return true;
        var n = c.childNodes || [];
        for (var k = 0; k < n.length; k++)
            if (n[k].nodeType === 3 && /\S/.test(n[k].nodeValue || ""))
                return true;
        return false;
    }

    /* Masca unui element cu imagini de fundal (degradeu, poza), care nu se pot taia cu benzi de culoare: tot ce
     * deseneaza elementul ramane, afara de gaura; in gaura raman numai cutiile urmasilor lui aflati peste obiect (o bara
     * sau un text peste imagine; un invelis gol peste obiect nu conteaza, deseneazaCeva). Numai cand elementul nu
     * deseneaza nimic in afara cutiei lui (masca taie ce iese) si nu are deja o masca a aplicatiei. o: cutia
     * elementului; tot: ce deseneaza (cuprins). */
    function mascaGaurii(e, el, cs, o, tot, x0, y0, x1, y1, peste) {
        var m = cs.getPropertyValue("-webkit-mask-image") || cs.getPropertyValue("mask-image");
        if (m && m !== "none")
            return null;
        if (!tot || tot.left < Math.max(o.left, 0) - 1 || tot.top < Math.max(o.top, 0) - 1 ||
                tot.right > Math.min(o.right, window.innerWidth) + 1 || tot.bottom > Math.min(o.bottom, window.innerHeight) + 1)
            return null;
        var l = Math.round(o.width), i = Math.round(o.height);
        var gx0 = Math.floor(x0 - o.left), gy0 = Math.floor(y0 - o.top), gx1 = Math.ceil(x1 - o.left),
            gy1 = Math.ceil(y1 - o.top);
        var b = [[0, 0, l, gy0], [0, gy1, l, i - gy1], [0, gy0, gx0, gy1 - gy0], [gx1, gy0, l - gx1, gy1 - gy0]];
        /* pe langa cele gasite de grila: urmasii care intra in gaura si sunt desenati peste obiect (o bara subtire pe
         * marginea imaginii scapa printre punctele grilei), cautati in mijlocul partii lor din gaura */
        var d = window.document, urmasi = e.getElementsByTagName("*"), candidati = peste.slice();
        if (urmasi.length <= URMASI_MAXIM && typeof d.elementsFromPoint === "function") {
            for (var k = 0; k < urmasi.length; k++) {
                var c = urmasi[k];
                if (c === el || candidati.indexOf(c) >= 0 || typeof c.getBoundingClientRect !== "function" ||
                        (typeof c.contains === "function" && c.contains(el)))
                    continue;
                var q = c.getBoundingClientRect();
                var q0 = Math.max(q.left, x0), w0 = Math.max(q.top, y0), q1 = Math.min(q.left + q.width, x1),
                    w1 = Math.min(q.top + q.height, y1);
                if (!(q1 > q0 && w1 > w0))
                    continue;
                var lp = d.elementsFromPoint((q0 + q1) / 2, (w0 + w1) / 2) || [];
                var ic = Array.prototype.indexOf.call(lp, c), iel = Array.prototype.indexOf.call(lp, el);
                if (ic >= 0 && iel >= 0 && ic < iel)
                    candidati.push(c);
            }
        }
        candidati.forEach(function (p) {
            if (p === e || typeof p.getBoundingClientRect !== "function" || !e.contains(p) || !deseneazaCeva(p))
                return;
            var r = p.getBoundingClientRect();
            var a0 = Math.max(r.left, x0), c0 = Math.max(r.top, y0), a1 = Math.min(r.left + r.width, x1),
                c1 = Math.min(r.top + r.height, y1);
            if (a1 > a0 && c1 > c0)
                b.push([Math.floor(a0 - o.left), Math.floor(c0 - o.top), Math.ceil(a1 - a0), Math.ceil(c1 - c0)]);
        });
        b = b.filter(function (z) { return z[2] > 0 && z[3] > 0; });
        if (!b.length)
            return null;
        var g = "linear-gradient(#000,#000)";
        return {
            "-webkit-mask-image": b.map(function () { return g; }).join(","),
            "-webkit-mask-position": b.map(function (z) { return z[0] + "px " + z[1] + "px"; }).join(","),
            "-webkit-mask-size": b.map(function (z) { return z[2] + "px " + z[3] + "px"; }).join(","),
            "-webkit-mask-repeat": "no-repeat",
            "-webkit-mask-origin": "border-box",
            "-webkit-mask-clip": "border-box"
        };
    }

    function gauraInchide() {
        if (gaura.privitor) {
            gaura.privitor.disconnect();
            gaura.privitor = null;
        }
        /* numai ce a pus gaura si aplicatia n-a schimbat intre timp */
        gaura.atinse.forEach(function (a) {
            for (var p in a.pus) {
                if (a.el.style.getPropertyValue(p) !== a.pus[p])
                    continue;
                if (a.vechi[p][0])
                    a.el.style.setProperty(p, a.vechi[p][0], a.vechi[p][1]);
                else
                    a.el.style.removeProperty(p);
            }
        });
        gaura.atinse = [];
        gaura.el = null;
        gaura.drept = "";
        gaura.cheie = "";
        gaura.schimbat = false;
        gaura.ticuri = 0;
    }

    /* Gaura pentru obiectul el in dreptunghiul x0,y0 - x1,y1 (puncte CSS ale ferestrei). Se reface numai cand s-a schimbat
     * dreptunghiul, multimea elementelor de dedesubt sau un element atins (clasa sau stilul, schimbate de aplicatie). */
    function gauraPune(el, x0, y0, x1, y1) {
        var d = window.document;
        if (typeof window.getComputedStyle !== "function" || !d.documentElement)
            return;
        var drept = [x0, y0, x1, y1].join(",");
        var laFel = gaura.el === el && gaura.drept === drept && !gaura.schimbat;
        if (laFel && ++gaura.ticuri % GAURA_CAUTARE_TICURI && gaura.ticuri > GAURA_TICURI_LA_INCEPUT)
            return;
        var gasite = dedesubt(el, x0, y0, x1, y1), sub = gasite.sub;
        /* elementele si cutiile lor: un panou mutat (de pilda de un parinte) reface gaura */
        var cheie = drept + "|" + sub.map(function (e) {
            var c = e.getBoundingClientRect();
            return idElement(e) + ":" + [c.left, c.top, c.width, c.height].map(Math.round).join(" ");
        }).join(",");
        if (laFel && gaura.cheie === cheie)
            return;
        gauraInchide();
        gaura.el = el;
        gaura.drept = drept;
        gaura.cheie = cheie;
        var html = d.documentElement, csHtml = window.getComputedStyle(html);
        var htmlGol = !culoareVazuta(csHtml.backgroundColor) && csHtml.backgroundImage === "none";
        var noi = [];
        sub.forEach(function (e) {
            if (!e.style || typeof e.getBoundingClientRect !== "function")
                return;
            /* un element de sub obiect, cu totul in dreptunghi, fara nimic al lui peste obiect: nu se vede deloc, ca la
             * televizoare (si textul, si pozele lui) */
            var tot = cuprins(e);
            if (tot && e !== html && e !== d.body && typeof e.contains === "function" && !e.contains(el) &&
                    x0 <= tot.left && y0 <= tot.top && x1 >= tot.right && y1 >= tot.bottom &&
                    !areCevaPeste(e, el, gasite.peste)) {
                noi.push([e, { "opacity": "0" }]);
                return;
            }
            var cs = window.getComputedStyle(e);
            var img = cs.backgroundImage && cs.backgroundImage !== "none";
            var col = culoareVazuta(cs.backgroundColor);
            if ((!img && !col) || (cs.transform && cs.transform !== "none") || /text/.test(cs.backgroundClip || ""))
                return;
            /* fundalul radacinii (al lui html sau al lui body, cand html nu are) e al intregului ecran, asezat fata de html */
            var radacina = e === html || (e === d.body && htmlGol);
            var o = (radacina ? html : e).getBoundingClientRect();
            var b = radacina ? { left: 0, top: 0, right: window.innerWidth, bottom: window.innerHeight } :
                e.getBoundingClientRect();
            var acopera = x0 <= b.left + 1 && y0 <= b.top + 1 && x1 >= b.right - 1 && y1 >= b.bottom - 1;
            if (acopera) {
                noi.push([e, faraBordura({ "background-color": "transparent", "background-image": "none" })]);
                return;
            }
            if (img && !radacina && (!col || /gradient\(/.test(cs.backgroundImage))) {
                /* numai imagini, sau un degradeu (de obicei pe tot elementul): benzile culorii nu le-ar taia; masca */
                var mc = mascaGaurii(e, el, cs, b, tot, x0, y0, x1, y1, gasite.peste);
                if (mc) {
                    noi.push([e, mc]);
                    return;
                }
            }
            if (!col)
                return;   /* numai imagini, fara masca posibila: raman */
            var z = benzi(cs.backgroundColor, Math.floor(x0 - o.left), Math.floor(y0 - o.top), Math.ceil(x1 - o.left),
                Math.ceil(y1 - o.top), Math.round(o.width), Math.round(o.height));
            if (img)
                z = benziSubImagini(cs, z);   /* culoarea are gaura, imaginile raman cum sunt */
            if (z && borduraCaFundalul(cs))
                faraBordura(z);
            if (z)
                noi.push([e, z]);
        });
        noi.forEach(function (n) {
            var e = n[0], vechi = {}, pus = {};
            for (var p in n[1]) {
                vechi[p] = [e.style.getPropertyValue(p), e.style.getPropertyPriority(p)];
                e.style.setProperty(p, n[1][p], "important");
                pus[p] = e.style.getPropertyValue(p);
            }
            gaura.atinse.push({ el: e, vechi: vechi, pus: pus });
        });
        if (gaura.atinse.length && typeof MutationObserver === "function") {
            gaura.privitor = new MutationObserver(function () { gaura.schimbat = true; });
            gaura.atinse.forEach(function (a) {
                gaura.privitor.observe(a.el, { attributes: true, attributeFilter: ["class", "style"] });
            });
        }
    }

    /* La fiecare verificare a ferestrei: gaura obiectului legat si vizibil, in dreptunghiul lui (si la
     * setFullScreen(true): imaginea e atunci pe tot ecranul, dar fereastra din pagina ramane cutia obiectului). */
    function gauraVerifica(el, r) {
        stilPus();
        var cs = typeof window.getComputedStyle === "function" ? window.getComputedStyle(el) : null;
        var vazut = cs && cs.display !== "none" && cs.visibility === "visible" && r.width > 0 && r.height > 0;
        if (!vazut) {
            if (gaura.el === el)
                gauraInchide();
            return;
        }
        gauraPune(el, Math.max(0, r.left), Math.max(0, r.top), Math.min(window.innerWidth, r.right),
            Math.min(window.innerHeight, r.bottom));
    }

    /* Pozitia si marimea obiectului (puncte CSS ale paginii de 1280x720), trimise lui enigma2, care muta imaginea
     * canalului in acel dreptunghi (/proc/stb/vmpeg/0). Un obiect ascuns sau de 0x0 trimite 0 0 0 0, iar enigma2
     * pune atunci imaginea pe tot ecranul (la fel cu setFullScreen(true), cu release() si la inchiderea aplicatiei). */
    function fereastra(el) {
        window.requestAnimationFrame(function () {
            var v = vb(el);
            if (v.joc === NECONECTAT) {
                if (gaura.el === el)
                    gauraInchide();
                return;
            }
            if (conectat(el) === true)
                v.inPagina = true;   /* legat inainte de a fi pus in pagina */
            var r = el.getBoundingClientRect();
            var t = [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)].join(" ");
            if (v.ecranIntreg)
                t = "0 0 " + window.innerWidth + " " + window.innerHeight;
            if (t !== v.fereastra) {
                v.fereastra = t;
                var p = t.split(" ");
                trimite("fereastra", p[0], p[1], p[2], p[3]);
            }
            if (avPeEcran())
                return;   /* cat merge un film, gaura e a obiectului A/V */
            gauraVerifica(el, { left: r.left, top: r.top, width: r.width, height: r.height, right: r.left + r.width,
                bottom: r.top + r.height });
        });
    }

    /* Atributele obiectului (MutationObserver) si, la 500 ms, o comparatie ieftina a dreptunghiului: un parinte mutat
     * sau marit nu schimba atributele obiectului. Se trimite numai la o schimbare (fereastra tine minte ultimul). */
    var URMARIRE_MS = 500;

    function urmareste(el, da) {
        var v = vb(el);
        if (da && !v.privitor && typeof MutationObserver === "function") {
            v.privitor = new MutationObserver(function () { fereastra(el); });
            v.privitor.observe(el, { attributes: true, attributeFilter: ["style", "width", "height", "class"] });
        } else if (!da && v.privitor) {
            v.privitor.disconnect();
            v.privitor = null;
        }
        if (!da && gaura.el === el)
            gauraInchide();
        if (da && !v.ceas && typeof window.setInterval === "function")
            v.ceas = window.setInterval(function () { fereastra(el); }, URMARIRE_MS);
        else if (!da && v.ceas) {
            if (typeof window.clearInterval === "function")
                window.clearInterval(v.ceas);
            v.ceas = null;
        }
        if (da)
            fereastra(el);
    }

    function activeaza(el) {
        if (vbActiv && vbActiv !== el)
            urmareste(vbActiv, false);
        vbActiv = el;
        if (conectat(el) === true)
            vb(el).inPagina = true;
        urmareste(el, true);
    }

    function cereCanal(el, comanda, canal, argumente) {
        var v = vb(el);
        if (altulActiv(el)) {
            eveniment(el, "ChannelChangeError", { channel: canal, errorState: 2 }, [canal, 2]);
            return;
        }
        if (v.joc !== CONECTARE)
            v.inainte = v.joc;
        v.cerut = canal;
        activeaza(el);
        schimbaStarea(el, CONECTARE);
        trimite.apply(null, [comanda].concat(argumente || []));
    }

    var VIDEO = {
        proprietati: {
            playState: { get: function () { return vb(this).joc; } },
            fullScreen: { get: function () { return vb(this).ecranIntreg; } },
            currentChannel: { get: function () {
                return vb(this).joc === NECONECTAT ? null : canalCurent();
            } },
            programmes: { get: function () {
                var j = vb(this).joc;
                return (j === PREZENTARE || j === OPRIT) && legata() ? programele() : colectie([]);
            } }
        },
        metode: {
            bindToCurrentChannel: function () {
                if (!legata())
                    throw eroareSecuritate();
                var v = vb(this);
                if (v.joc !== NECONECTAT && v.joc !== OPRIT)
                    return canalCurent();
                if (altulActiv(this)) {
                    schimbaStarea(this, NECONECTAT, 2);
                    return null;
                }
                if (!S.canal) {
                    schimbaStarea(this, NECONECTAT, 100);
                    return null;
                }
                activeaza(this);
                trimite("leaga");
                schimbaStarea(this, PREZENTARE);
                return canalCurent();
            },
            setChannel: function (canal) {
                if (canal === null || canal === undefined) {
                    /* cap. 6.2.2.6: aplicatia devine independenta de canal */
                    trimite("canal", "-");
                    if (S.app)
                        S.app.legat = false;
                    if (vbActiv === this) {
                        urmareste(this, false);
                        vbActiv = null;
                    }
                    eveniment(this, "ChannelChangeSucceeded", { channel: null }, [null]);
                    schimbaStarea(this, NECONECTAT);
                    return;
                }
                if (typeof canal !== "object") {
                    eveniment(this, "ChannelChangeError", { channel: canal, errorState: 0 }, [canal, 0]);
                    return;
                }
                var ccid = typeof canal.ccid === "string" && canal.ccid ? canal.ccid : "-";
                var onid = intreg(canal.onid), tsid = intreg(canal.tsid), sid = intreg(canal.sid);
                if (ccid !== "-" && !cautaCcid(ccid)) {
                    eveniment(this, "ChannelChangeError", { channel: canal, errorState: 5 }, [canal, 5]);
                    return;
                }
                if (ccid === "-" && (isNaN(onid) || isNaN(sid))) {
                    eveniment(this, "ChannelChangeError", { channel: canal, errorState: 0 }, [canal, 0]);
                    return;
                }
                cereCanal(this, "canal", canal, [ccid, intreg(canal.idType) || 11, isNaN(onid) ? -1 : onid,
                    isNaN(tsid) ? -1 : tsid, isNaN(sid) ? -1 : sid]);
            },
            nextChannel: function () {
                if (!legata())
                    throw eroareSecuritate();
                if (vb(this).joc === NECONECTAT) {
                    eveniment(this, "ChannelChangeError", { channel: null, errorState: 10 }, [null, 10]);
                    return;
                }
                cereCanal(this, "urmator", null);
            },
            prevChannel: function () {
                if (!legata())
                    throw eroareSecuritate();
                if (vb(this).joc === NECONECTAT) {
                    eveniment(this, "ChannelChangeError", { channel: null, errorState: 10 }, [null, 10]);
                    return;
                }
                cereCanal(this, "anterior", null);
            },
            stop: function () {
                var v = vb(this);
                if (v.joc === NECONECTAT || !legata())
                    return;
                trimite("opreste");
                schimbaStarea(this, OPRIT);
            },
            release: function () {
                var v = vb(this);
                if (v.joc === NECONECTAT || !legata())
                    return;
                trimite("elibereaza");
                if (vbActiv === this) {
                    urmareste(this, false);
                    vbActiv = null;
                }
                v.fereastra = "";
                schimbaStarea(this, NECONECTAT);
            },
            setFullScreen: function (da) {
                var v = vb(this);
                da = !!da;
                if (v.ecranIntreg === da || !legata())
                    return;
                v.ecranIntreg = da;
                trimite("ecran-intreg", da ? 1 : 0);
                eveniment(this, "FullScreenChange", {}, []);
                fereastra(this);
            },
            getChannelConfig: function () {
                if (!legata())
                    throw eroareSecuritate();
                return { channelList: listaCanale(), favouriteLists: null, currentFavouriteList: null };
            },
            createChannelObject: function (idType, a, b, c) {
                var tip = intreg(idType);
                if (arguments.length <= 3 && typeof a === "string")
                    return new Channel({ idType: tip, dsd: a, sid: intreg(b) });
                var onid = intreg(a), tsid = intreg(b), sid = intreg(c);
                if (isNaN(onid) || isNaN(sid))
                    return null;
                var gasit = cautaInLista(onid, tsid, sid);
                var ch = new Channel(gasit || { idType: tip, onid: onid, tsid: isNaN(tsid) ? undefined : tsid, sid: sid });
                ch.idType = isNaN(tip) ? ch.idType : tip;
                return ch;
            }
        },
        evenimente: ["onPlayStateChange", "onChannelChangeSucceeded", "onChannelChangeError", "onFullScreenChange",
            "onProgrammesChanged"]
    };

    /* --- obiectul A/V (OIPF DAE 7.14 cu anexa A.2.5): filmele aplicatiilor (mediatecile), pe playerul receptorului
     * (enigma2, serviciul 4097: MP4, TS, DASH, HLS), pe acelasi decodor cu canalul, sub pagina, in dreptunghiul
     * obiectului (ca la video/broadcast: "av fereastra x y l i" si gaura in fundalurile de dedesubt). Numai cu un
     * lansator care lasa comanda "av" (LANSATOR.av); altfel tipurile nu exista (isObjectSupported intoarce false).
     * Pagina -> enigma2: "av porneste <id> <base64 adresa> <tip>", "av viteza 0|1", "av cauta <ms>", "av opreste",
     * "av fereastra x y l i", "av ecran-intreg 0|1", "av pista <index>". enigma2 -> pagina: {ev: "av", id, joc, poz,
     * lung, viteza, eroare, cautat} si {ev: "av-piste", id, piste} (Components/HdsHbbtvPornire.py). Un singur film
     * odata; pornirea lui opreste canalul (video/broadcast legat trece in "oprit", iar bindToCurrentChannel il porneste
     * din nou). Vitezele: 0 (pauza) si 1. Pistele de sunet se aleg; subtitrarile filmului nu sunt (getComponents(2) e
     * gol). Un obiect scos din pagina sau cu alt data cat merge filmul il opreste. */
    var AV_OPRIT = 0, AV_REDA = 1, AV_PAUZA = 2, AV_CONECTARE = 3, AV_ASTEAPTA = 4, AV_EROARE = 6;
    var AV_B64_MAXIM = 2048;
    var COMPONENTE = { COMPONENT_TYPE_VIDEO: 0, COMPONENT_TYPE_AUDIO: 1, COMPONENT_TYPE_SUBTITLE: 2 };
    var avActiv = null, avUltimId = 0;

    function av(el) {
        var s = stare(el);
        if (!s.av)
            s.av = { joc: AV_OPRIT, eroare: undefined, poz: 0, pozLa: 0, lung: 0, viteza: 0, id: 0, fereastra: "",
                ecranIntreg: false, privitor: null, ceas: null, inPagina: false, piste: [], pauzaCeruta: false };
        return s.av;
    }

    function avInMers(joc) {
        return joc === AV_REDA || joc === AV_PAUZA || joc === AV_CONECTARE || joc === AV_ASTEAPTA;
    }

    function avPeEcran() {
        return !!avActiv && avInMers(av(avActiv).joc);
    }

    function avSchimba(el, joc, eroare) {
        var a = av(el);
        if (a.joc === joc && eroare === undefined)
            return;
        a.joc = joc;
        a.eroare = joc === AV_EROARE ? eroare : undefined;
        eveniment(el, "PlayStateChange", { state: joc, error: a.eroare }, [joc, a.eroare]);
    }

    /* Adresa filmului: atributul data, intreaga fata de document; numai http(s). */
    function avAdresa(el) {
        var d = el.getAttribute ? el.getAttribute("data") : null;
        if (!d)
            return "";
        var u = String(d).trim();
        try {
            u = new URL(u, document.baseURI || window.location.href).href;
        } catch (x) {
            /* fara URL: adresa asa cum e, daca e intreaga */
        }
        return /^https?:\/\//i.test(u) ? u : "";
    }

    function avPozitie(el) {
        var a = av(el);
        if (a.joc === AV_REDA && a.viteza === 1 && a.pozLa) {
            var p = a.poz + Math.max(0, Date.now() - a.pozLa);
            return a.lung > 0 ? Math.min(p, a.lung) : p;
        }
        return a.poz;
    }

    /* Filmul ia decodorul: alt obiect A/V se opreste, video/broadcast legat trece in "oprit" (canalul s-a oprit). */
    function avIaDecodorul(el) {
        if (avActiv && avActiv !== el) {
            var b = av(avActiv), vechi = avActiv;
            urmaresteAv(vechi, false);
            avActiv = null;
            if (avInMers(b.joc))
                avSchimba(vechi, AV_OPRIT);
        }
        avActiv = el;
        if (vbActiv) {
            var v = vb(vbActiv);
            if (v.joc === PREZENTARE || v.joc === CONECTARE)
                schimbaStarea(vbActiv, OPRIT);
        }
    }

    function avOpresteTot(el) {
        var a = av(el);
        if (avActiv === el && avInMers(a.joc))
            trimite("av", "opreste");
        urmaresteAv(el, false);
        if (avActiv === el)
            avActiv = null;
        a.poz = 0;
        a.pozLa = 0;
        a.pauzaCeruta = false;
        avSchimba(el, AV_OPRIT);
    }

    function fereastraAv(el) {
        window.requestAnimationFrame(function () {
            var a = av(el);
            if (avActiv !== el || !avInMers(a.joc)) {
                if (gaura.el === el)
                    gauraInchide();
                return;
            }
            var c = conectat(el);
            if (c === true)
                a.inPagina = true;
            else if (c === false && a.inPagina) {
                avOpresteTot(el);   /* scos din pagina: filmul se opreste odata cu obiectul */
                return;
            }
            var r = el.getBoundingClientRect();
            var t = [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)].join(" ");
            if (a.ecranIntreg)
                t = "0 0 " + window.innerWidth + " " + window.innerHeight;
            if (t !== a.fereastra) {
                a.fereastra = t;
                var p = t.split(" ");
                trimite("av", "fereastra", p[0], p[1], p[2], p[3]);
            }
            gauraVerifica(el, { left: r.left, top: r.top, width: r.width, height: r.height, right: r.left + r.width,
                bottom: r.top + r.height });
        });
    }

    function urmaresteAv(el, da) {
        var a = av(el);
        if (da && !a.privitor && typeof MutationObserver === "function") {
            a.privitor = new MutationObserver(function (l) {
                for (var i = 0; i < l.length; i++) {
                    if (l[i].attributeName === "data" && avInMers(av(el).joc)) {
                        avOpresteTot(el);   /* alt film in acelasi obiect: cel vechi se opreste (pornit din nou cu play) */
                        return;
                    }
                }
                fereastraAv(el);
            });
            a.privitor.observe(el, { attributes: true, attributeFilter: ["style", "width", "height", "class", "data"] });
        } else if (!da && a.privitor) {
            a.privitor.disconnect();
            a.privitor = null;
        }
        if (!da && gaura.el === el)
            gauraInchide();
        if (da && !a.ceas && typeof window.setInterval === "function")
            a.ceas = window.setInterval(function () { fereastraAv(el); }, URMARIRE_MS);
        else if (!da && a.ceas) {
            if (typeof window.clearInterval === "function")
                window.clearInterval(a.ceas);
            a.ceas = null;
        }
        if (!da)
            a.fereastra = "";
        if (da)
            fereastraAv(el);
    }

    /* AVComponent (DAE 7.16.5.2): video (unul, fara alegere) si pistele de sunet date de enigma2 (pid = indexul pistei) */
    function AVComponent(d) {
        this.componentTag = d.componentTag;
        this.pid = d.pid;
        this.type = d.type;
        this.encoding = d.encoding || "";
        this.encrypted = false;
        if (d.type === 1) {
            this.language = d.language || "";
            this.audioDescription = !!d.audioDescription;
            this.audioChannels = d.audioChannels || 2;
        } else if (d.type === 0)
            this.aspectRatio = 1.78;
    }

    function avComponente(el, tip, numaiActive) {
        var a = av(el), rez = [];
        if (!avInMers(a.joc) || avActiv !== el)
            return colectie([]);
        var t = tip === undefined || tip === null ? -1 : intreg(tip);
        if ((t === -1 || t === 0) && !/^audio\//.test(tipul(el)))
            rez.push(new AVComponent({ componentTag: 0, pid: 0, type: 0 }));
        if (t === -1 || t === 1) {
            a.piste.forEach(function (p) {
                if (!numaiActive || p.activa)
                    rez.push(new AVComponent({ componentTag: p.index, pid: p.index, type: 1, encoding: p.cod,
                        language: p.limba, audioDescription: p.ad, audioChannels: p.canale }));
            });
        }
        return colectie(rez);
    }

    var AV = {
        proprietati: {
            playState: { get: function () { return av(this).joc; } },
            error: { get: function () {
                var a = av(this);
                return a.joc === AV_EROARE ? a.eroare : undefined;
            } },
            playPosition: { get: function () { return avPozitie(this); } },
            playTime: { get: function () { return av(this).lung || 0; } },
            speed: { get: function () {
                var a = av(this);
                return a.joc === AV_REDA || a.joc === AV_ASTEAPTA || a.joc === AV_CONECTARE ? a.viteza : 0;
            } },
            fullScreen: { get: function () { return av(this).ecranIntreg; } },
            COMPONENT_TYPE_VIDEO: { get: function () { return COMPONENTE.COMPONENT_TYPE_VIDEO; } },
            COMPONENT_TYPE_AUDIO: { get: function () { return COMPONENTE.COMPONENT_TYPE_AUDIO; } },
            COMPONENT_TYPE_SUBTITLE: { get: function () { return COMPONENTE.COMPONENT_TYPE_SUBTITLE; } }
        },
        metode: {
            play: function (viteza) {
                var a = av(this);
                var v = viteza === undefined ? 1 : Number(viteza);
                if (v !== 0 && v !== 1)
                    return false;   /* fara derulare rapida */
                if (avInMers(a.joc) && avActiv === this) {
                    if (a.joc === AV_CONECTARE && v === 0) {
                        a.pauzaCeruta = true;   /* pauza abia cand filmul a inceput */
                        return true;
                    }
                    a.pauzaCeruta = false;
                    if (v !== a.viteza)
                        trimite("av", "viteza", v);
                    return true;
                }
                var url = avAdresa(this), tip = tipul(this);
                if (!url || AV_TIPURI.indexOf(tip) < 0)
                    return false;
                var b = b64(url);
                if (b.length > AV_B64_MAXIM) {
                    avSchimba(this, AV_EROARE, 4);
                    return false;
                }
                avIaDecodorul(this);
                a.id = ++avUltimId;
                a.poz = a.pozLa = a.lung = 0;
                a.viteza = 1;
                a.pauzaCeruta = v === 0;
                a.piste = [];
                a.inPagina = false;
                trimite("av", "porneste", a.id, b, tip);
                avSchimba(this, AV_CONECTARE);
                urmaresteAv(this, true);
                return true;
            },
            stop: function () {
                if (av(this).joc !== AV_OPRIT)
                    avOpresteTot(this);
                return true;
            },
            seek: function (pozitie) {
                var a = av(this), p = intreg(pozitie);
                if (avActiv !== this || !avInMers(a.joc) || isNaN(p) || p < 0)
                    return false;
                trimite("av", "cauta", p);
                return true;
            },
            setFullScreen: function (da) {
                var a = av(this);
                da = !!da;
                if (a.ecranIntreg === da)
                    return;
                a.ecranIntreg = da;
                trimite("av", "ecran-intreg", da ? 1 : 0);
                eveniment(this, "FullScreenChange", {}, []);
                fereastraAv(this);
            },
            setVolume: function () { return false; },
            queue: function () { return false; },
            getComponents: function (tip) { return avComponente(this, tip, false); },
            getCurrentActiveComponents: function (tip) { return avComponente(this, tip, true); },
            selectComponent: function (c) {
                var a = av(this);
                if (avActiv !== this || !avInMers(a.joc) || !c || typeof c !== "object" || c.type !== 1)
                    return;   /* numai pistele de sunet; subtitrarile filmului nu sunt */
                var i = intreg(c.pid);
                if (isNaN(i) || !a.piste.some(function (p) { return p.index === i; }))
                    return;
                trimite("av", "pista", i);
            },
            unselectComponent: function () {}
        },
        evenimente: ["onPlayStateChange", "onPlayPositionChanged", "onPlaySpeedChanged", "onFullScreenChange",
            "onSelectedComponentChanged"]
    };

    /* Starea filmului venita de la enigma2 (numai pentru cererea de acum: acelasi id). */
    function avDeLa(e) {
        var el = avActiv;
        if (!el || av(el).id !== e.id)
            return;
        var a = av(el), vitezaVeche = a.viteza;
        if (isFinite(e.lung))
            a.lung = Math.max(0, e.lung);
        if (isFinite(e.poz)) {
            a.poz = Math.max(0, e.poz);
            a.pozLa = Date.now();
        }
        if (e.viteza === 0 || e.viteza === 1)
            a.viteza = e.viteza;
        var joc = intreg(e.joc);
        if (!isNaN(joc) && joc >= 0 && joc <= 6 && joc !== a.joc) {
            if (!avInMers(joc)) {
                urmaresteAv(el, false);
                avActiv = null;
            }
            avSchimba(el, joc, joc === AV_EROARE ? (isFinite(e.eroare) ? e.eroare : 2) : undefined);
        }
        if (a.viteza !== vitezaVeche)
            eveniment(el, "PlaySpeedChanged", { speed: a.viteza }, [a.viteza]);
        if (e.cautat !== undefined)
            eveniment(el, "PlayPositionChanged", { position: a.poz }, [a.poz]);
        if (a.joc === AV_REDA && a.pauzaCeruta) {
            a.pauzaCeruta = false;
            trimite("av", "viteza", 0);
        }
    }

    function avPisteDeLa(e) {
        var el = avActiv;
        if (!el || av(el).id !== e.id || !Array.isArray(e.piste))
            return;
        var a = av(el), activaVeche = a.piste.filter(function (p) { return p.activa; }).map(function (p) { return p.index; });
        a.piste = e.piste.filter(function (p) { return p && isFinite(p.index); });
        var activa = a.piste.filter(function (p) { return p.activa; }).map(function (p) { return p.index; });
        if (activaVeche.length && activaVeche.join() !== activa.join())
            eveniment(el, "SelectedComponentChanged", { componentType: 1 }, [1]);
    }

    var TIPURI = {
        "application/oipfapplicationmanager": MANAGER,
        "application/oipfconfiguration": CONFIGURARE,
        "application/oipfcapabilities": CAPABILITATI,
        "application/oipfparentalcontrolmanager": PARENTAL,
        "video/broadcast": VIDEO
    };
    if (avPornit)
        AV_TIPURI.forEach(function (t) { TIPURI[t] = AV; });

    /* Toate numele, puse o singura data pe HTMLObjectElement.prototype. */
    function pePrototip() {
        var P = window.HTMLObjectElement && window.HTMLObjectElement.prototype;
        if (!P)
            return;
        var nume = {};
        Object.keys(TIPURI).forEach(function (t) {
            var d = TIPURI[t];
            Object.keys(d.proprietati || {}).forEach(function (n) { nume[n] = 1; });
            Object.keys(d.metode || {}).forEach(function (n) { nume[n] = 1; });
            (d.evenimente || []).forEach(function (n) { nume[n] = 1; });
        });
        Object.keys(nume).forEach(function (n) {
            if (Object.prototype.hasOwnProperty.call(P, n))
                return;   /* niciun nume al elementului insusi nu se acopera */
            Object.defineProperty(P, n, {
                configurable: true,
                enumerable: false,
                get: function () {
                    var d = TIPURI[tipul(this)];
                    var s = stare(this);
                    if (d) {
                        if (d.metode && d.metode[n])
                            return d.metode[n];
                        if (d.proprietati && d.proprietati[n])
                            return d.proprietati[n].get.call(this);
                        if (d.evenimente && d.evenimente.indexOf(n) >= 0)
                            return s.h[n] === undefined ? null : s.h[n];
                    }
                    return s.x[n];
                },
                set: function (v) {
                    var d = TIPURI[tipul(this)];
                    var s = stare(this);
                    if (d && d.evenimente && d.evenimente.indexOf(n) >= 0) {
                        s.h[n] = v;
                        return;
                    }
                    if (d && ((d.metode && d.metode[n]) || (d.proprietati && d.proprietati[n])))
                        return;   /* numai citire */
                    s.x[n] = v;
                }
            });
        });
    }
    pePrototip();
    stilPus();
    if (typeof document.addEventListener === "function")
        document.addEventListener("DOMContentLoaded", stilPus, false);

    /* --- oipfObjectFactory (6.4) */
    function obiectNou(tip) {
        var el = document.createElement("object");
        el.setAttribute("type", tip);
        facute.push(el);
        return el;
    }
    var fabrica = {
        isObjectSupported: function (tip) {
            return Object.prototype.hasOwnProperty.call(TIPURI, String(tip).trim().toLowerCase());
        },
        createVideoBroadcastObject: function () { return obiectNou("video/broadcast"); },
        createApplicationManagerObject: function () { return obiectNou("application/oipfApplicationManager"); },
        createConfigurationObject: function () { return obiectNou("application/oipfConfiguration"); },
        createCapabilitiesObject: function () { return obiectNou("application/oipfCapabilities"); },
        createParentalControlManagerObject: function () { return obiectNou("application/oipfParentalControlManager"); },
        createVideoMpegObject: function () { return avPornit ? obiectNou("video/mpeg") : null; }
    };
    if (!window.oipfObjectFactory) {
        try {
            window.oipfObjectFactory = fabrica;
        } catch (x) {
            /* pagina are deja altul, numai de citit */
        }
    }

    /* Anexa A.2.8.1: window.close() si debug(). close() inchide aplicatia (ca destroyApplication); debug() nu scrie
     * nicaieri (nimic din pagini in jurnalul receptorului). */
    try {
        window.close = function () { trimite("distruge"); };
    } catch (x) {
        /* close nu se poate inlocui: ramane cel al navigatorului */
    }
    if (typeof window.debug !== "function")
        window.debug = function () {};

    /* ------------------------------------------------------------ traducerea textelor vazute ("Tradu HbbTV")
     * Cand enigma2 pune in config "traducere" ({port, cheie}: setarea pornita; vine numai pe stdin, dupa pornire),
     * textele vazute ale paginii pleaca la receptor si se inlocuiesc pe loc, ca "Traduce pagina" din browsere: nodurile
     * de text din documentul de sus si din cadrele de pe acelasi domeniu, cu cel putin doua litere, afisate (elementul lor
     * are dreptunghiuri si nu e ascuns), fara script, style, campuri de scris, cod, adrese sau ce are translate="no".
     * Pagina se arata intai in original. Cererea, una singura deodata, cel mult TRAD_PE_CERERE texte:
     *   - prin puntea lansatorului (cand LANSATOR.tradu): "tradu <id> <base64 al {t: [texte]}>", base64 de cel mult
     *     TRAD_B64_MAX semne (cat lasa trimite(); un text care nu incape singur ramane in original); raspunsul vine ca
     *     eveniment {ev: "traducere", id, result, t | oprit} (Components/HdsHbbtvPornire.py); fara raspuns in
     *     TRAD_TERMEN_MS, cererea e un esec. Merge si in paginile https.
     *   - altfel prin interfata web: POST http://127.0.0.1:<port>/api/traducere-hbbtv (HdsWebControl/
     *     traducere_hbbtv_web.py), corpul text simplu {k: cheia, t: [texte]} (fara antete: fara cerere de verificare
     *     CORS). fetch e cel al navigatorului, luat la inceputul documentului (pagina nu-l poate inlocui inainte). O
     *     pagina https nu poate chema http://127.0.0.1 in WebKit (continut amestecat): pe aceasta cale ramane in original.
     * Raspunsul: pentru fiecare text traducerea, 0 (ramane originalul) sau null (inca se traduce: se cere din nou mai
     * tarziu, de cel mult TRAD_REINCERCARI ori). Textele care apar sau se schimba (MutationObserver; si dupa o tasta,
     * cand aplicatia arata alt panou) se strang TRAD_ASTEAPTA_MS. Setarea oprita (config fara "traducere"): textele
     * originale se pun la loc. */
    var TRAD_ASTEAPTA_MS = 400, TRAD_PE_CERERE = 40, TRAD_MAX_TEXT = 1500, TRAD_REINCERCARI = 10, TRAD_PAUZA_MS = 1500,
        TRAD_ESECURI = 3, TRAD_NODURI_PE_TRECERE = 1500, TRAD_B64_MAX = 2048, TRAD_TERMEN_MS = 15000;
    var TRAD_SARITE = { SCRIPT: 1, STYLE: 1, NOSCRIPT: 1, TEXTAREA: 1, INPUT: 1, SELECT: 1, OPTION: 1, OBJECT: 1, EMBED: 1,
        CODE: 1, PRE: 1, KBD: 1, SAMP: 1, VAR: 1, TEMPLATE: 1, SVG: 1, MATH: 1, CANVAS: 1, VIDEO: 1, AUDIO: 1, TITLE: 1 };
    var TRAD_LITERE = /\p{L}[\s\S]*\p{L}/u;
    var TRAD_ADRESA = /^(?:[a-z][a-z0-9+.-]*:\/\/\S*|www\.\S+|\S+@\S+\.\S+|\S+\.(?:html?|php|jpe?g|png|js|css)(?:\?\S*)?)$/i;
    var TRAD_COD = /[{};=<>]{3}|^[\w$.]+\([^)]*\);?$/;
    var tradJson = JSON.stringify;
    var tradFetch = typeof window.fetch === "function" ? window.fetch.bind(window) : null;
    var TradMO = typeof window.MutationObserver === "function" ? window.MutationObserver : null;
    var tr = {
        pornit: false, url: "", cheie: "", prinPunte: false, id: 0, cerere: null,
        noduri: new Map(),      /* nodul tradus -> {orig, pus} */
        texte: new Map(),       /* textul (strans) -> traducerea, 0 = ramane, null = cerut */
        asteapta: new Map(),    /* textul -> Set de noduri care asteapta traducerea lui */
        coada: [], inZbor: false, incercari: new Map(), esecuri: 0,
        radacini: [], ceas: null, observatori: [], documente: new WeakSet()
    };

    function tradStrans(t) {
        return String(t).replace(/\s+/g, " ").trim();
    }

    function tradDeTradus(t) {
        return t.length >= 2 && t.length <= TRAD_MAX_TEXT && TRAD_LITERE.test(t) && !TRAD_ADRESA.test(t) && !TRAD_COD.test(t);
    }

    /* elementul textului si parintii lui: nimic sarit, nimic de scris, nimic cu translate="no"; elementul afisat */
    function tradElementBun(el) {
        var e = el, adancime = 0;
        while (e && e.nodeType === 1 && adancime++ < 64) {
            var nume = String(e.localName || e.tagName || "").toUpperCase();
            if (TRAD_SARITE[nume] || e.isContentEditable)
                return false;
            if (e.getAttribute && (e.getAttribute("translate") === "no" || /(^|\s)notranslate(\s|$)/.test(e.getAttribute("class") || "")))
                return false;
            e = e.parentNode;
        }
        try {
            if (typeof el.getClientRects === "function" && !el.getClientRects().length)
                return false;
            var v = el.ownerDocument && el.ownerDocument.defaultView;
            if (v && typeof v.getComputedStyle === "function") {
                var st = v.getComputedStyle(el);
                if (st && (st.visibility === "hidden" || st.display === "none"))
                    return false;
            }
        } catch (x) {
            return false;
        }
        return true;
    }

    function tradPune(nod, traducere) {
        var orig = String(nod.nodeValue);
        var inceput = /^\s*/.exec(orig)[0], sfarsit = /\s*$/.exec(orig)[0];
        var pus = inceput + traducere + sfarsit;
        tr.noduri.set(nod, { orig: orig, pus: pus });
        if (nod.nodeValue !== pus)
            nod.nodeValue = pus;
    }

    function tradNod(nod) {
        var v = nod.nodeValue;
        if (!v)
            return;
        var rec = tr.noduri.get(nod);
        if (rec) {
            if (v === rec.pus)
                return;               /* tradus de noi */
            tr.noduri.delete(nod);    /* pagina a schimbat textul: e un original nou */
        }
        var t = tradStrans(v);
        if (!tradDeTradus(t) || !tradElementBun(nod.parentNode))
            return;
        var stiut = tr.texte.get(t);
        if (typeof stiut === "string") {
            tradPune(nod, stiut);
            return;
        }
        if (stiut === 0)
            return;
        var lista = tr.asteapta.get(t);
        if (!lista) {
            lista = new Set();
            tr.asteapta.set(t, lista);
        }
        lista.add(nod);
        if (stiut === undefined && tr.coada.indexOf(t) < 0)
            tr.coada.push(t);
    }

    function tradDocument(d) {
        if (!d || tr.documente.has(d))
            return;
        tr.documente.add(d);
        if (!TradMO)
            return;
        try {
            var o = new TradMO(tradSchimbari);
            o.observe(d, { childList: true, subtree: true, characterData: true, attributes: true,
                attributeFilter: ["style", "class", "hidden"] });
            tr.observatori.push(o);
        } catch (x) {
            /* fara urmarire: numai trecerile de la tasta si de la incarcare */
        }
    }

    function tradTrece(radacina) {
        if (!radacina)
            return;
        var d = radacina.nodeType === 9 ? radacina : radacina.ownerDocument;
        if (radacina.nodeType === 3) {
            tradNod(radacina);
            return;
        }
        if (radacina.nodeType === 9)
            radacina = radacina.body || radacina.documentElement;
        if (!radacina || !d || typeof d.createTreeWalker !== "function")
            return;
        var w = d.createTreeWalker(radacina, 4 /* NodeFilter.SHOW_TEXT */, null, false), n, k = 0;
        while ((n = w.nextNode()) && k++ < TRAD_NODURI_PE_TRECERE)
            tradNod(n);
        /* cadrele de pe acelasi domeniu */
        if (typeof radacina.getElementsByTagName === "function") {
            var cadre = radacina.getElementsByTagName("iframe");
            for (var i = 0; i < cadre.length; i++) {
                var cd = null;
                try {
                    cd = cadre[i].contentDocument;
                } catch (x) {
                    cd = null;
                }
                if (cd && (cd.body || cd.documentElement)) {
                    tradDocument(cd);
                    tradTrece(cd);
                }
            }
        }
    }

    function tradCurata() {
        tr.noduri.forEach(function (rec, nod) {
            if (!nod.isConnected)
                tr.noduri.delete(nod);
        });
        tr.asteapta.forEach(function (lista, t) {
            lista.forEach(function (nod) {
                if (!nod.isConnected)
                    lista.delete(nod);
            });
            if (!lista.size)
                tr.asteapta.delete(t);
        });
    }

    function tradPlanifica(radacina) {
        if (!tr.pornit)
            return;
        if (radacina && tr.radacini.indexOf(radacina) < 0)
            tr.radacini.push(radacina);
        if (tr.ceas === null)
            tr.ceas = setTimeout(tradPas, TRAD_ASTEAPTA_MS);
    }

    function tradPas() {
        tr.ceas = null;
        if (!tr.pornit)
            return;
        var radacini = tr.radacini;
        tr.radacini = [];
        tradCurata();
        for (var i = 0; i < radacini.length; i++)
            tradTrece(radacini[i]);
        tradTrimite();
    }

    function tradSchimbari(inregistrari) {
        for (var i = 0; i < inregistrari.length; i++) {
            var r = inregistrari[i];
            if (r.type === "characterData") {
                var rec = tr.noduri.get(r.target);
                if (!rec || r.target.nodeValue !== rec.pus)
                    tradPlanifica(r.target);
            } else if (r.type === "childList") {
                for (var j = 0; j < r.addedNodes.length; j++)
                    tradPlanifica(r.addedNodes[j]);
            } else {
                tradPlanifica(r.target);
            }
        }
    }

    function tradRaspuns(lot, d) {
        if (!d || d.result === false) {
            if (d && d.oprit)
                tradOpreste(false);
            return;
        }
        var t = Array.isArray(d.t) ? d.t : [];
        lot.forEach(function (text, i) {
            var v = t[i];
            if (typeof v === "string" && v) {
                tr.texte.set(text, v);
                (tr.asteapta.get(text) || new Set()).forEach(function (nod) {
                    if (nod.isConnected && tradStrans(nod.nodeValue) === text)
                        tradPune(nod, v);
                });
                tr.asteapta.delete(text);
            } else if (v === 0) {
                tr.texte.set(text, 0);
                tr.asteapta.delete(text);
            } else {
                /* inca se traduce: mai tarziu, din nou */
                var n = (tr.incercari.get(text) || 0) + 1;
                tr.texte.delete(text);
                if (n > TRAD_REINCERCARI) {
                    tr.texte.set(text, 0);
                    tr.asteapta.delete(text);
                    return;
                }
                tr.incercari.set(text, n);
                setTimeout(function () {
                    if (tr.pornit && tr.texte.get(text) === undefined && tr.coada.indexOf(text) < 0) {
                        tr.coada.push(text);
                        tradTrimite();
                    }
                }, TRAD_PAUZA_MS * Math.min(n, 4));
            }
        });
    }

    /* o cerere fara raspuns (receptorul nu raspunde, sau pagina https pe calea web): textele se cer din nou, de cel mult
     * TRAD_ESECURI ori la rand, apoi traducerea se opreste (ramane originalul) */
    function tradEsec(lot) {
        lot.forEach(function (t) { tr.texte.delete(t); });
        if (++tr.esecuri >= TRAD_ESECURI) {
            tradOpreste(false);
            return;
        }
        setTimeout(function () {
            lot.forEach(function (t) {
                if (tr.coada.indexOf(t) < 0)
                    tr.coada.push(t);
            });
            tradTrimite();
        }, TRAD_PAUZA_MS * tr.esecuri);
    }

    function tradGata() {
        tr.inZbor = false;
        if (tr.coada.length)
            setTimeout(tradTrimite, 50);
    }

    /* prin punte: cat incape in TRAD_B64_MAX semne base64; textul care nu incape nici singur ramane in original */
    function tradTrimitePunte() {
        var lot = [], b = "";
        while (tr.coada.length && lot.length < TRAD_PE_CERERE) {
            var t = tr.coada[0], incercat = b64(tradJson({ t: lot.concat([t]) }));
            if (incercat.length > TRAD_B64_MAX) {
                if (lot.length)
                    break;
                tr.coada.shift();
                tr.texte.set(t, 0);
                tr.asteapta.delete(t);
                continue;
            }
            lot.push(tr.coada.shift());
            b = incercat;
        }
        if (!lot.length)
            return;
        lot.forEach(function (t) { tr.texte.set(t, null); });
        tr.inZbor = true;
        var id = (++tr.id).toString(36);
        tr.cerere = { id: id, lot: lot, ceas: setTimeout(function () {
            if (!tr.cerere || tr.cerere.id !== id)
                return;
            tr.cerere = null;
            tradEsec(lot);
            tradGata();
        }, TRAD_TERMEN_MS) };
        trimite("tradu", id, b);
    }

    /* raspunsul punte (evenimentul "traducere" de la enigma2) */
    function tradPrimit(e) {
        var c = tr.cerere;
        if (!c || String(e.id) !== c.id)
            return;
        clearTimeout(c.ceas);
        tr.cerere = null;
        tr.esecuri = 0;
        if (tr.pornit)
            tradRaspuns(c.lot, e);
        tradGata();
    }

    function tradTrimite() {
        if (!tr.pornit || tr.inZbor || !tr.coada.length)
            return;
        if (tr.prinPunte) {
            tradTrimitePunte();
            return;
        }
        if (!tradFetch)
            return;
        var lot = tr.coada.splice(0, TRAD_PE_CERERE);
        lot.forEach(function (t) { tr.texte.set(t, null); });
        tr.inZbor = true;
        var corp;
        try {
            corp = tradJson({ k: tr.cheie, t: lot });
        } catch (x) {
            tr.inZbor = false;
            return;
        }
        tradFetch(tr.url, { method: "POST", body: corp, mode: "cors", credentials: "omit", cache: "no-store" })
            .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
            .then(function (d) {
                tr.esecuri = 0;
                tradRaspuns(lot, d);
            }, function () {
                tradEsec(lot);            /* receptorul nu raspunde (sau pagina https): ramane originalul */
            })
            .then(tradGata);
    }

    function tradOpreste(laLoc) {
        tr.pornit = false;
        if (tr.cerere) {
            clearTimeout(tr.cerere.ceas);
            tr.cerere = null;
            tr.inZbor = false;
        }
        tr.observatori.forEach(function (o) {
            try {
                o.disconnect();
            } catch (x) {
                /* nimic */
            }
        });
        tr.observatori = [];
        tr.documente = new WeakSet();
        if (tr.ceas !== null) {
            clearTimeout(tr.ceas);
            tr.ceas = null;
        }
        if (laLoc) {
            tr.noduri.forEach(function (rec, nod) {
                if (nod.nodeValue === rec.pus)
                    nod.nodeValue = rec.orig;
            });
            tr.noduri.clear();
            tr.texte.clear();
        }
        tr.coada = [];
        tr.asteapta.clear();
        tr.radacini = [];
    }

    function tradPorneste() {
        if (!tr.pornit || typeof document === "undefined")
            return;
        tradDocument(document);
        tradPlanifica(document);
    }

    /* setarea venita de la enigma2 (la inceput si la fiecare "config" nou) */
    function tradSetari() {
        var c = S.config && S.config.traducere;
        var port = c && isFinite(c.port) ? Math.floor(c.port) : 0;
        var https = false;
        try {
            https = window.location && window.location.protocol === "https:";
        } catch (x) {
            https = false;
        }
        var prinPunte = !!(c && LANSATOR.tradu && punte);
        var pornit = !!(c && (prinPunte || (c.cheie && port > 0 && port < 65536 && tradFetch && !https)));
        if (!pornit) {
            if (tr.pornit)
                tradOpreste(true);
            return;
        }
        var url = prinPunte ? "" : "http://127.0.0.1:" + port + "/api/traducere-hbbtv";
        var cheie = prinPunte ? "" : String(c.cheie);
        if (tr.pornit && tr.prinPunte === prinPunte && tr.url === url && tr.cheie === cheie)
            return;
        tr.pornit = true;
        tr.prinPunte = prinPunte;
        tr.url = url;
        tr.cheie = cheie;
        tr.esecuri = 0;
        if (typeof document !== "undefined" && document.readyState === "loading") {
            if (typeof document.addEventListener === "function")
                document.addEventListener("DOMContentLoaded", tradPorneste, false);
        } else {
            tradPorneste();
        }
    }

    /* o tasta schimba de obicei ce arata aplicatia (un alt panou, alta pagina a listei) */
    if (typeof window.addEventListener === "function") {
        window.addEventListener("keydown", function () {
            if (tr.pornit)
                setTimeout(function () { tradPlanifica(document); }, TRAD_ASTEAPTA_MS);
        }, true);
        window.addEventListener("load", function () {
            if (tr.pornit)
                tradPlanifica(document);
        }, false);
    }

    /* ------------------------------------------------------------ adresele dvb:// ale caruselului
     * O aplicatie venita numai prin caruselul DSM-CC al canalului e data de serverul local al receptorului
     * (Components/HdsCaruselServer.py): radacina caruselului e http://127.0.0.1:<port>/, iar enigma2 pune in config
     * "carusel" = {baza, onid, tsid, sid, tag}. Adresele relative si cele care incep cu "/" merg singure. O adresa
     * intreaga a aceluiasi carusel, dvb://<onid>.<tsid>.<sid>.<tag>[$<id>]<cale> (ETSI TS 102 851: numerele in hex,
     * tsid poate lipsi), se rescrie spre server in: src, href, data si poster puse din JavaScript (proprietatile
     * elementelor si setAttribute), XMLHttpRequest.open, fetch si atributele elementelor puse in pagina
     * (MutationObserver si o trecere la DOMContentLoaded). Orice alta adresa ramane cum e (dvb://current.ait/... merge
     * la createApplication). Fara "carusel" in config la pornirea paginii (aplicatiile de pe internet) nu se pune nimic.
     * Nu se pot rescrie de aici: url(dvb://...) din CSS, location.href = "dvb://..." si un <script src="dvb://...">
     * scris in HTML (navigatorul il cere inainte ca atributul sa poata fi schimbat). */
    var CAR_ATRIBUTE = ["src", "href", "data", "poster"];
    var CAR_HEX = /^[0-9a-f]{1,8}$/i;
    var carPuneAtribut = null;

    function caruselul() {
        var c = S.config && S.config.carusel;
        if (!c || typeof c !== "object" || typeof c.baza !== "string" ||
                !/^http:\/\/127\.0\.0\.1:[0-9]{1,5}\/$/.test(c.baza))
            return null;
        return c;
    }

    function carNumar(text, n, golPermis) {
        if (text === "")
            return !!golPermis;
        return CAR_HEX.test(text) && parseInt(text, 16) === n;
    }

    function dinCarusel(u) {
        var c = caruselul();
        if (!c || typeof u !== "string" || !/^\s*dvb:/i.test(u))
            return u;
        var m = /^\s*dvb:\/\/([^\/?#]*)([\/?#][\s\S]*)?$/i.exec(u);
        if (!m)
            return u;
        var p = m[1].split("$")[0].split(".");
        if (p.length !== 4 || !carNumar(p[0], c.onid) || !carNumar(p[1], c.tsid, true) || !carNumar(p[2], c.sid) ||
                !carNumar(p[3], c.tag))
            return u;
        var rest = m[2] || "/";
        return c.baza + (rest.charAt(0) === "/" ? rest.replace(/^\/+/, "") : rest);
    }

    function adresaCarusel(u) {
        if (typeof u === "string")
            return dinCarusel(u);
        if (u && typeof u === "object" && typeof u.href === "string" && /^\s*dvb:/i.test(u.href))
            return dinCarusel(u.href);
        return u;
    }

    function carElement(el) {
        if (!el || el.nodeType !== 1 || typeof el.getAttribute !== "function" || !carPuneAtribut)
            return;
        for (var i = 0; i < CAR_ATRIBUTE.length; i++) {
            var v = el.getAttribute(CAR_ATRIBUTE[i]);
            if (typeof v === "string" && /^\s*dvb:/i.test(v)) {
                var nou = dinCarusel(v);
                if (nou !== v)
                    carPuneAtribut.call(el, CAR_ATRIBUTE[i], nou);
            }
        }
    }

    function carSubarbore(r) {
        carElement(r);
        if (r && typeof r.getElementsByTagName === "function") {
            var toate = r.getElementsByTagName("*");
            for (var i = 0; i < toate.length; i++)
                carElement(toate[i]);
        }
    }

    function puneCaruselul() {
        if (!caruselul())
            return;
        var El = window.Element;
        if (typeof El === "function" && El.prototype && typeof El.prototype.setAttribute === "function") {
            carPuneAtribut = El.prototype.setAttribute;
            El.prototype.setAttribute = function (nume, valoare) {
                if (typeof nume === "string" && CAR_ATRIBUTE.indexOf(nume.toLowerCase()) >= 0 && typeof valoare === "string")
                    valoare = dinCarusel(valoare);
                return carPuneAtribut.call(this, nume, valoare);
            };
        }
        [["HTMLImageElement", "src"], ["HTMLScriptElement", "src"], ["HTMLIFrameElement", "src"],
            ["HTMLFrameElement", "src"], ["HTMLSourceElement", "src"], ["HTMLMediaElement", "src"],
            ["HTMLEmbedElement", "src"], ["HTMLInputElement", "src"], ["HTMLLinkElement", "href"],
            ["HTMLAnchorElement", "href"], ["HTMLAreaElement", "href"], ["HTMLBaseElement", "href"],
            ["HTMLVideoElement", "poster"]].forEach(function (x) {
            var Clasa = window[x[0]];
            var d = Clasa && Clasa.prototype ? Object.getOwnPropertyDescriptor(Clasa.prototype, x[1]) : null;
            if (!d || typeof d.set !== "function" || !d.configurable)
                return;
            try {
                Object.defineProperty(Clasa.prototype, x[1], { configurable: true, enumerable: d.enumerable, get: d.get,
                    set: function (v) { d.set.call(this, adresaCarusel(v)); } });
            } catch (e) {
                /* proprietatea ramane a navigatorului */
            }
        });
        var X = window.XMLHttpRequest;
        if (typeof X === "function" && X.prototype && typeof X.prototype.open === "function") {
            var deschide = X.prototype.open;
            X.prototype.open = function () {
                var a = Array.prototype.slice.call(arguments);
                if (a.length > 1)
                    a[1] = adresaCarusel(a[1]);
                return deschide.apply(this, a);
            };
        }
        if (typeof window.fetch === "function") {
            var aduce = window.fetch;
            window.fetch = function () {
                var a = Array.prototype.slice.call(arguments);
                var c = a[0];
                if (c && typeof c === "object" && typeof c.url === "string" && /^\s*dvb:/i.test(c.url) &&
                        typeof window.Request === "function") {
                    try {
                        a[0] = new window.Request(dinCarusel(c.url), c);
                    } catch (e) {
                        a[0] = dinCarusel(c.url);
                    }
                } else if (a.length) {
                    a[0] = adresaCarusel(c);
                }
                return aduce.apply(window, a);
            };
        }
        if (typeof document === "undefined")
            return;
        var MO = window.MutationObserver;
        if (typeof MO === "function") {
            try {
                new MO(function (inregistrari) {
                    for (var i = 0; i < inregistrari.length; i++) {
                        var r = inregistrari[i];
                        if (r.type === "attributes") {
                            carElement(r.target);
                        } else if (r.addedNodes) {
                            for (var j = 0; j < r.addedNodes.length; j++)
                                carSubarbore(r.addedNodes[j]);
                        }
                    }
                }).observe(document, { childList: true, subtree: true, attributes: true, attributeFilter: CAR_ATRIBUTE });
            } catch (e) {
                /* fara urmarire: numai trecerea de la DOMContentLoaded */
            }
        }
        if (typeof document.addEventListener === "function") {
            document.addEventListener("DOMContentLoaded", function () {
                carSubarbore(document.documentElement);
            }, false);
        }
    }

    /* ------------------------------------------------------------ ce vine de la enigma2 */

    function laEveniment(e) {
        if (!e || typeof e !== "object")
            return;
        var el = vbActiv;
        switch (e.ev) {
        case "vizibil":
            vizibila = !!e.v;
            break;
        case "canal-reusit":
            if (el) {
                var c = canalCurent();
                vb(el).cerut = null;
                schimbaStarea(el, PREZENTARE);
                eveniment(el, "ChannelChangeSucceeded", { channel: c }, [c]);
                fereastra(el);
            }
            break;
        case "canal-eroare":
            if (el) {
                var v = vb(el);
                var cerut = v.cerut;
                var cod = isFinite(e.cod) ? e.cod : 100;
                v.cerut = null;
                schimbaStarea(el, v.inainte, cod);
                eveniment(el, "ChannelChangeError", { channel: cerut, errorState: cod }, [cerut, cod]);
            }
            break;
        case "programe":
            if (el && (vb(el).joc === PREZENTARE || vb(el).joc === OPRIT))
                eveniment(el, "ProgrammesChanged", {}, []);
            break;
        case "aplicatie-eroare":
            elementeDeTip("application/oipfapplicationmanager").forEach(function (m) {
                eveniment(m, "ApplicationLoadError", { appl: aplicatie }, [aplicatie]);
            });
            break;
        case "memorie-putina":
            elementeDeTip("application/oipfapplicationmanager").forEach(function (m) {
                eveniment(m, "LowMemory", {}, []);
            });
            break;
        case "traducere":
            tradPrimit(e);
            break;
        case "av":
            avDeLa(e);
            break;
        case "av-piste":
            avPisteDeLa(e);
            break;
        default:
            break;
        }
    }

    function primeste(cheie, valoare) {
        if (cheie === "ev") {
            laEveniment(valoare);
            return;
        }
        if (!Object.prototype.hasOwnProperty.call(S, cheie))
            return;
        S[cheie] = valoare;
        if (cheie === "lista" && !Array.isArray(S.lista))
            S.lista = [];
        if (cheie === "programe" && !Array.isArray(S.programe))
            S.programe = [];
        if (cheie === "config") {
            if (!S.config || typeof S.config !== "object")
                S.config = {};
            capabilitati = null;
            tradSetari();
        }
        if (cheie === "app")
            vizibila = !!(S.app && S.app.vizibil);
        if (cheie === "taste" && S.taste && isFinite(S.taste.value))
            masca = S.taste.value & TASTE_MAXIM;
    }

    Object.defineProperty(window, "__hdsHbbtvPrimeste", { value: primeste, writable: false, configurable: false,
        enumerable: false });
    puneCaruselul();
    tradSetari();
})();
