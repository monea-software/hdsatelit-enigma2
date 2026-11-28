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
 * pagina; vezi "obiectul A/V" mai jos. Fara acea comanda tipurile nu exista, ca inainte. Pe obiectul A/V sunt si pause()
 * si resume() (in afara standardului; playerele scrise pentru <video> le cheama, de pilda ADN Play), ca play(0) / play(1).
 *
 * <video> / <audio> HTML5 (AS192, HBB9): WebKit e construit fara video, deci cu acelasi lansator un element media cu
 * sursa http(s) HLS / DASH / MP4 / TS / MP3 (dupa extensie sau dupa atributul type) merge tot pe playerul receptorului,
 * prin aceleasi comenzi "av", cu evenimentele si proprietatile unui <video>; vezi "<video> HTML5 pe playerul
 * receptorului" mai jos. Sursa poate veni din JavaScript (src, setAttribute) sau din HTML (atributul src, copiii
 * <source>), luata la load(), la play() sau la autoplay.
 *
 * Ce NU e aici: DRM, citirea caruselului (o face receptorul), evenimentele de flux din carusel, MSE (MediaSource: WebKit e
 * construit fara video), subtitrarile filmelor, derularea rapida.
 *
 * HbbTV 2.0.2 (ETSI TS 102 796 V1.5.1; H20-202, 0.7.5): versiunea declarata ramane HbbTV 1.5 (Components/HdsHbbtv.py), fiindca
 * un aparat 2.0 are <video> HTML5 cu DASH si subtitrari EBU-TT-D, pe care WebKit-ul imaginii nu le are; obiectul A/V ramane
 * si in 2.0 (anexa A.2.5), deci aplicatiile merg pe el. De acolo, aici: application/oipfDrmAgent "fara DRM" (anexa A.1 il cere
 * numai cu DRM sau CI Plus, dar paginile il pun des) si Keyset.supportsPointer (DAE 7.2.5.2).
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
    /* HBW1: "leaga" amanat pana la sfarsitul pasului JavaScript (vezi bindToCurrentChannel); obiectul care l-a cerut */
    var leagaAmanat = null, leagaSaritSpus = false;
    var LEAGA_FARA_GRABA = { fereastra: 1, taste: 1, tradu: 1 };

    function leagaPleaca() {
        if (leagaAmanat === null)
            return;
        leagaAmanat = null;
        trimite("leaga");
    }

    function trimite() {
        /* o cerere a paginii dupa bindToCurrentChannel amanat: "leaga" pleaca intai, ordinea ramane cea a paginii */
        if (leagaAmanat !== null && !LEAGA_FARA_GRABA[arguments[0]])
            leagaPleaca();
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
    /* Masca spre enigma2 (HBT2, 0.8.0): cel mult o trimitere la TASTE_PAS_MS; schimbarile venite mai des se strang si
     * pleaca o data, cu ultima valoare. Aplicatia TVP GO pune masca de 3 ori la rand pentru fiecare tasta pe care si-o
     * inregistreaza (55-88 de mesaje pe secunda), iar lansatorul arunca ce trece de 40 pe secunda: ultima masca putea fi
     * una aruncata, deci tastele ajungeau gresit. Un ceas care nu mai bate (pagina oprita) nu tine trimiterea pe loc:
     * dupa doi pasi, urmatoarea schimbare pleaca direct. */
    var TASTE_PAS_MS = 100;
    var tasteTrimisa = null, tasteLa = 0, tasteCeas = null;

    function tastePleaca() {
        tasteTrimisa = masca;
        tasteLa = Date.now();
        trimite("taste", masca);
    }

    function trimiteTaste() {
        var trecut = Date.now() - tasteLa;
        if (tasteCeas !== null) {
            if (trecut >= 0 && trecut < 2 * TASTE_PAS_MS)
                return;                 /* ultima valoare pleaca atunci cand bate ceasul */
            if (typeof window.clearTimeout === "function")
                window.clearTimeout(tasteCeas);
            tasteCeas = null;
        }
        if (trecut < 0 || trecut >= TASTE_PAS_MS || typeof window.setTimeout !== "function") {
            tastePleaca();
            return;
        }
        tasteCeas = window.setTimeout(function () {
            tasteCeas = null;
            if (masca !== tasteTrimisa)
                tastePleaca();
        }, TASTE_PAS_MS - trecut);
    }

    Keyset.prototype.setValue = function (valoare) {
        var v = intreg(valoare);
        masca = isNaN(v) ? 0 : (v & TASTE_MAXIM);
        trimiteTaste();
        return masca;
    };
    /* supportsPointer (OIPF DAE 7.2.5.2; HbbTV 2.0.2 cap. 10.2.2): aplicatia spune ca stie si mouse. Receptorul nu are
     * mouse, deci valoarea doar se tine minte (niciun eveniment de mouse nu vine). H20-202 */
    var cuMouse = false;
    Object.defineProperty(Keyset.prototype, "supportsPointer", {
        get: function () { return cuMouse; },
        set: function (v) { cuMouse = !!v; }
    });
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

    /* --- application/oipfDrmAgent (DAE 7.6.1, HbbTV 2.0.2 anexa A.1 si A.2.27): receptorul n-are DRM si nici CI Plus, deci
     * standardul nu cere obiectul; multe pagini il pun totusi in HTML (TV Puls pe DVB-T2, sabloanele HbbTV) si ar arunca
     * TypeError la prima chemare. Aici: sendDRMMessage intoarce un id si raspunde asincron cu onDRMMessageResult(id, "", 5)
     * (5 = sistem DRM necunoscut); setActiveDRM(null) si setActiveDRM("urn:hbbtv:oipfdrm:inactive") intorc true (nimic de
     * oprit), orice alt sistem false. isObjectSupported ramane false: aplicatiile care intreaba afla ca nu e DRM. H20-202 */
    var DRM_NECUNOSCUT = 5;
    var drmUltimId = 0;
    /* MDS1 (0.7.8): sistemul DRM cerut de pagina (numai forma urn:dvb:casystemid:<numar>, altfel "nestiut"; nimic alt
     * text al paginii), pentru jurnalul filmelor de mai jos; null daca
     * pagina n-a cerut nicio licenta. Raspunsul dat paginii ramane acelasi (5). */
    var drmCerut = null;
    var DRM_AGENT = {
        metode: {
            sendDRMMessage: function (tip, mesaj, sistem) {
                if (drmCerut === null) {
                    var s = String(sistem === undefined || sistem === null ? "" : sistem);
                    var m = /^urn:dvb:casystemid:(\d{1,5})$/i.exec(s);
                    drmCerut = m ? "urn:dvb:casystemid:" + m[1] : "nestiut";
                    jurnalPagina("pagina cere o licenta DRM (sistem " + drmCerut + "); receptorul nu are DRM, raspuns " +
                        DRM_NECUNOSCUT + " (sistem necunoscut)");
                }
                var id = String(++drmUltimId);
                eveniment(this, "DRMMessageResult", { msgID: id, resultMsg: "", resultCode: DRM_NECUNOSCUT },
                    [id, "", DRM_NECUNOSCUT]);
                return id;
            },
            setActiveDRM: function (sistem) {
                return sistem === null || sistem === undefined || String(sistem) === "urn:hbbtv:oipfdrm:inactive";
            }
        },
        evenimente: ["onDRMMessageResult", "onDRMSystemMessage"]
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
        var tinta = tintePornite(el);
        try {
            gauraCauta(el, x0, y0, x1, y1, drept, laFel);
        } finally {
            if (tinta)
                tinteOprite();
        }
    }

    /* Un obiect cu pointer-events:none (al lui sau mostenit: aplicatia ERT il pune pe parintele filmului, #videodiv, si pe
     * previzualizarea din cardul primei pagini) nu e intors de elementsFromPoint, deci cautarea de mai jos nu l-ar gasi in
     * niciun punct: nicio gaura, iar scena aplicatiei de sub film ramane opaca peste el (filmul se aude, ecranul e negru).
     * Pe durata cautarii (sincron, aplicatia nu apuca sa vada nimic) o regula a stratului face tinta orice element:
     * pointer-events nu schimba nici asezarea, nici desenul, deci ordinea gasita e cea de pe ecran. Numai pentru un astfel de
     * obiect; la celelalte cautarea ramane neschimbata. */
    var TINTE_REGULA = "*:not(#hds-a):not(#hds-b){pointer-events:auto !important}";
    var tinte = null;   /* foaia si locul regulii, cat e pusa */

    function tintePornite(el) {
        try {
            if (window.getComputedStyle(el).pointerEvents !== "none")
                return false;
            var st = window.document.getElementById(STIL_ID), sh = st && st.sheet;
            if (!sh)
                return false;
            tinte = { sh: sh, i: sh.insertRule(TINTE_REGULA, sh.cssRules.length) };
            return true;
        } catch (x) {
            return false;
        }
    }

    function tinteOprite() {
        var t = tinte;
        tinte = null;
        try {
            if (t && t.i < t.sh.cssRules.length && /pointer-events/.test(t.sh.cssRules[t.i].cssText))
                t.sh.deleteRule(t.i);
        } catch (x) {
            /* foaia stratului scoasa intre timp de aplicatie: regula a plecat odata cu ea */
        }
    }

    /* Filmul unei aplicatii (obiectul A/V) pe toata fereastra (HBT2, 0.8.0): la televizoare acopera tot ce pagina
     * deseneaza sub el. Grila din dedesubt() scapa elementele mici dintre punctele ei: hub-ul TVP GO isi lasa sub film
     * antetul (sigla, meniul, ceasul) si randul de categorii, care la noi ramaneau scrise peste imagine. Aici se cauta,
     * de la radacina in jos, ramurile paginii de langa drumul spre obiect, fiecare in mijlocul partii ei din fereastra:
     * gasita sub obiect, ramura intra intreaga la cele de dedesubt (gauraCauta o ascunde daca nimic din ea nu e peste
     * film); gasita peste obiect, ramane neatinsa (comenzile playerului); negasita (o cutie goala, cu urmasii iesiti din
     * ea) sau prea mare ca sa fie judecata intreaga, i se cauta copiii. O ramura cu totul in afara ferestrei nu se
     * cauta. Cel mult FILM_CAUTARI_MAXIM cautari la o trecere. */
    var FILM_CAUTARI_MAXIM = 160;

    function subFilmIntreg(el, rez) {
        var d = window.document, L = window.innerWidth, I = window.innerHeight, ramase = FILM_CAUTARI_MAXIM;
        if (typeof d.elementsFromPoint !== "function" || !d.body || !(L > 0 && I > 0))
            return;

        function copii(c) {
            var n = c.children || [];
            for (var i = 0; i < n.length && ramase > 0; i++)
                cauta(n[i]);
        }

        function cauta(c) {
            if (!c || c === el || c.nodeType !== 1 || typeof c.getBoundingClientRect !== "function")
                return;
            if (typeof c.contains === "function" && c.contains(el)) {
                copii(c);               /* un stramos al obiectului: ramurile lui */
                return;
            }
            if (rez.sub.indexOf(c) >= 0 || rez.peste.indexOf(c) >= 0)
                return;
            var r = c.getBoundingClientRect();
            var a0 = Math.max(r.left, 0), b0 = Math.max(r.top, 0), a1 = Math.min(r.left + r.width, L),
                b1 = Math.min(r.top + r.height, I);
            if (r.width > 0 && r.height > 0) {
                if (!(a1 > a0 && b1 > b0))
                    return;             /* cu totul in afara ferestrei */
                var urmasi = typeof c.getElementsByTagName === "function" ? c.getElementsByTagName("*").length : 0;
                if (urmasi <= URMASI_MAXIM) {
                    ramase--;
                    var l = d.elementsFromPoint((a0 + a1) / 2, (b0 + b1) / 2) || [];
                    var ic = Array.prototype.indexOf.call(l, c), iel = Array.prototype.indexOf.call(l, el);
                    if (ic >= 0 && iel >= 0) {
                        (ic < iel ? rez.peste : rez.sub).push(c);
                        return;
                    }
                }
            }
            copii(c);
        }

        cauta(d.body);
    }

    function gauraCauta(el, x0, y0, x1, y1, drept, laFel) {
        var d = window.document;
        var gasite = dedesubt(el, x0, y0, x1, y1), sub = gasite.sub;
        if (avActiv === el && x0 <= 0 && y0 <= 0 && x1 >= window.innerWidth && y1 >= window.innerHeight)
            subFilmIntreg(el, gasite);
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
        /* HBL1 (0.8.0): un <video>/<audio> al carui film merge pe playerul receptorului se deseneaza el insusi peste
         * imagine; cu fundalul lui (playerul Rubidia: <video class="media"> negru pe tot ecranul) se aude si ecranul e
         * negru (Lanus, AS211). Fundalul elementului devine transparent cat tine gaura si revine la inchiderea ei. */
        if (avActiv === el && av(el).html5 && el.style) {
            var csEl = window.getComputedStyle(el);
            if (culoareVazuta(csEl.backgroundColor) || (csEl.backgroundImage && csEl.backgroundImage !== "none"))
                noi.push([el, { "background-color": "transparent", "background-image": "none" }]);
        }
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

    /* Broadcast metadata is read-only; selection requires a native non-persistent API. */
    var bcStare = S.config.broadcast || { piste: null };
    function bcComponente(el, tip, active) {
        if (!legata())
            throw eroareSecuritate();
        if (!Array.isArray(bcStare.piste))
            return undefined;
        return colectie(bcStare.piste.filter(function (p) {
            return (tip === null || tip === undefined || p.type === tip) && (!active ||
                (p.active && vb(el).joc === PREZENTARE));
        }).map(function (p) {
            var c = {};
            ["type", "pid", "componentTag", "encoding", "encrypted", "language", "audioDescription",
                "audioChannels", "hearingImpaired", "aspectRatio"].forEach(function (k) {
                Object.defineProperty(c, k, { value: p[k] === null ? undefined : p[k], enumerable: true });
            });
            constantesBc(c);
            return c;
        }));
    }
    function constantesBc(c) {
        constante(c, { COMPONENT_TYPE_VIDEO: 0, COMPONENT_TYPE_AUDIO: 1, COMPONENT_TYPE_SUBTITLE: 2 });
    }
    function bcPrimeste(p) {
        var vechi = bcStare;
        bcStare = p || { piste: null };
        if (!vbActiv)
            return;
        [0, 1, 2].forEach(function (tip) {
            function lista(s, active) {
                return (s.piste || []).filter(function (c) { return c.type === tip && (!active || c.active); })
                    .map(function (c) {
                        var copie = {};
                        Object.keys(c).sort().forEach(function (k) { if (k !== "active") copie[k] = c[k]; });
                        return active ? c.id : JSON.stringify(copie);
                    }).join("|");
            }
            if (lista(vechi, false) !== lista(bcStare, false))
                eveniment(vbActiv, "ComponentChanged", { componentType: tip }, [tip]);
            if (lista(vechi, true) !== lista(bcStare, true)) {
                eveniment(vbActiv, "SelectedComponentChanged", { componentType: tip }, [tip]);
                eveniment(vbActiv, "SelectedComponentChange", { componentType: tip }, [tip]);
            }
        });
    }

    var VIDEO = {
        proprietati: {
            COMPONENT_TYPE_VIDEO: { get: function () { return 0; } },
            COMPONENT_TYPE_AUDIO: { get: function () { return 1; } },
            COMPONENT_TYPE_SUBTITLE: { get: function () { return 2; } },
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
                /* HBW1 (0.8.0; AS244, Lanus, wedo tv 13E): aplicatii ca wedo tv "elibereaza decodorul" cu
                 * bindToCurrentChannel() urmat imediat de stop() pe video/broadcast, la 500 ms, cat filmul lor (aici
                 * splash.mp4) merge. Playerul receptorului e unul singur, deci "leaga" oprea filmul paginii, canalul pornea
                 * si se oprea iar; filmul splash nu mai ajungea la 1,2 s si rotita aplicatiei ramanea peste filme. Cand un
                 * film al paginii tine playerul, "leaga" pleaca la sfarsitul pasului (sau inaintea urmatoarei cereri a
                 * paginii); stop() pe acelasi obiect in acelasi pas il anuleaza: canalul ramane oprit, filmul merge.
                 * Pagina vede aceleasi stari ca inainte (prezentare, apoi oprit). Fara film al paginii: ca inainte. */
                if (avPeEcran() && typeof setTimeout === "function") {
                    leagaAmanat = this;
                    setTimeout(leagaPleaca, 0);
                } else
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
                if (leagaAmanat === this) {
                    leagaAmanat = null;   /* HBW1: bindToCurrentChannel + stop() cat merge filmul paginii */
                    if (!leagaSaritSpus) {
                        leagaSaritSpus = true;
                        jurnalPagina("video/broadcast: bindToCurrentChannel + stop() cat merge filmul paginii: " +
                            "filmul ramane, canalul ramane oprit");
                    }
                }
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
            getComponents: function (tip) { return bcComponente(this, tip, false); },
            getCurrentActiveComponents: function (tip) { return bcComponente(this, tip, true); },
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
            "onProgrammesChanged", "onComponentChanged", "onSelectedComponentChanged", "onSelectedComponentChange"]
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
        if (a.html5)
            videoEvenimente(el, joc);
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
            /* load() (H20-TVP): playerele scrise pentru <video> il cheama dupa ce pun data si type; pe obiectul A/V filmul
             * porneste la play(), deci aici nu face nimic */
            load: function () {},
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
            /* pause() / resume() (HBB9): nu sunt in OIPF DAE, dar playerele scrise si pentru <video> le cheama pe obiectul
             * A/V (ADN Play: "t.pause is not a function", rotita fara sfarsit); numai pe filmul pornit, ca play(0) / play(1).
             * Pe un obiect oprit nu pornesc nimic. */
            pause: function () {
                var a = av(this);
                if (avActiv !== this || !avInMers(a.joc))
                    return false;
                return AV.metode.play.call(this, 0);
            },
            resume: function () {
                var a = av(this);
                if (avActiv !== this || !avInMers(a.joc))
                    return false;
                return AV.metode.play.call(this, 1);
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
        if (a.html5 && (isFinite(e.poz) || e.cautat !== undefined))
            videoTrimite(el, e.cautat !== undefined ? ["seeked", "timeupdate"] : ["timeupdate"]);
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
        "application/oipfdrmagent": DRM_AGENT,
        "video/broadcast": VIDEO
    };
    /* tipurile care au metode (paginile nu cad), dar pe care isObjectSupported le spune nesustinute (H20-202) */
    var NUMAI_PENTRU_PAGINI = { "application/oipfdrmagent": 1 };
    if (avPornit)
        AV_TIPURI.forEach(function (t) { TIPURI[t] = AV; });

    /* Toate numele, puse o singura data pe HTMLObjectElement.prototype. */
    function pePrototip() {
        var P = window.HTMLObjectElement && window.HTMLObjectElement.prototype;
        if (!P)
            return;
        var nume = {}, evNume = {};   /* evNume: numele functiilor de eveniment, ale oricarui tip OIPF */
        Object.keys(TIPURI).forEach(function (t) {
            var d = TIPURI[t];
            Object.keys(d.proprietati || {}).forEach(function (n) { nume[n] = 1; });
            Object.keys(d.metode || {}).forEach(function (n) { nume[n] = 1; });
            (d.evenimente || []).forEach(function (n) { nume[n] = 1; evNume[n] = 1; });
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
                    return d || !evNume[n] ? s.x[n] : s.h[n];   /* fara tip inca: functia pusa inainte (TVP) */
                },
                set: function (v) {
                    var d = TIPURI[tipul(this)];
                    var s = stare(this);
                    if (d ? d.evenimente && d.evenimente.indexOf(n) >= 0 : evNume[n]) {   /* si inainte de type (TVP) */
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
    /* canPlayType pe <object> (H20-TVP): playerele cu mai multe motoare (TVP pe DVB-T) aleg obiectul A/V numai daca
     * elementul raspunde „maybe” la tipul filmului; tipul elementului se pune abia la load(), deci raspunsul nu depinde de
     * el. Numai cu obiectul A/V pornit. */
    (function () {
        var P = window.HTMLObjectElement && window.HTMLObjectElement.prototype;
        if (!P || !avPornit || Object.prototype.hasOwnProperty.call(P, "canPlayType"))
            return;
        Object.defineProperty(P, "canPlayType", {
            configurable: true, enumerable: false, writable: true,
            value: function (tip) {
                var t = String(tip === undefined || tip === null ? "" : tip).split(";")[0].trim().toLowerCase();
                return AV_TIPURI.indexOf(t) >= 0 ? "maybe" : "";
            }
        });
    })();
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
            var t = String(tip).trim().toLowerCase();
            return Object.prototype.hasOwnProperty.call(TIPURI, t) && !NUMAI_PENTRU_PAGINI[t];
        },
        createVideoBroadcastObject: function () { return obiectNou("video/broadcast"); },
        createApplicationManagerObject: function () { return obiectNou("application/oipfApplicationManager"); },
        createConfigurationObject: function () { return obiectNou("application/oipfConfiguration"); },
        createCapabilitiesObject: function () { return obiectNou("application/oipfCapabilities"); },
        createParentalControlManagerObject: function () { return obiectNou("application/oipfParentalControlManager"); },
        createDrmAgentObject: function () { return obiectNou("application/oipfDrmAgent"); },
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
        case "anunt":
            anuntPagina(e.text, e.ms);
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

    /* Un anunt scurt al receptorului in pagina (HBL1, 0.8.0; ev "anunt" din Components/HdsHbbtvPornire.py): de pilda
     * filmul aplicatiei cazut inainte de prima imagine. O fereastra de enigma2 peste navigator l-ar ascunde si ar lua
     * tastele (AS211), deci textul (tradus de enigma2) se scrie aici, sus pe mijloc, peste aplicatie, fara sa ia tastele
     * sau clicurile, si pleaca singur dupa ms (ANUNT_MS daca lipseste). Un anunt nou il inlocuieste pe cel vechi. */
    var ANUNT_ID = "hds-anunt", ANUNT_MS = 8000;
    var anuntCeas = null;

    function anuntPagina(text, ms) {
        var d = window.document;
        if (!text || !d || typeof d.createElementNS !== "function" || !d.documentElement)
            return;
        try {
            var vechi = d.getElementById(ANUNT_ID);
            if (vechi && vechi.parentNode)
                vechi.parentNode.removeChild(vechi);
            var a = d.createElementNS(NS_XHTML, "div");
            a.setAttribute("id", ANUNT_ID);
            a.setAttribute("style", "position:fixed;left:140px;right:140px;top:36px;z-index:2147483647;" +
                "pointer-events:none;background:rgba(16,24,32,0.93);color:#f0f0f0;font:24px/1.35 sans-serif;" +
                "padding:14px 24px;border-radius:8px;text-align:center;opacity:1");
            a.textContent = String(text);
            (d.body || d.documentElement).appendChild(a);
            if (anuntCeas !== null)
                window.clearTimeout(anuntCeas);
            anuntCeas = window.setTimeout(function () {
                anuntCeas = null;
                if (a.parentNode)
                    a.parentNode.removeChild(a);
            }, isFinite(ms) && ms > 0 ? ms : ANUNT_MS);
        } catch (x) {
            /* documentul nu primeste elemente: anuntul ramane numai in jurnal */
        }
    }

    function primeste(cheie, valoare) {
        if (cheie === "ev") {
            if (valoare && valoare.ev === "broadcast") {
                bcPrimeste(valoare);
                return;
            }
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
            bcPrimeste(S.config.broadcast);
            tradSetari();
        }
        if (cheie === "app")
            vizibila = !!(S.app && S.app.vizibil);
        /* cat o masca noua asteapta sa plece (trimiteTaste), raspunsul enigma2 la una mai veche nu o schimba */
        if (cheie === "taste" && S.taste && isFinite(S.taste.value) && tasteCeas === null)
            masca = S.taste.value & TASTE_MAXIM;
    }

    /* ------------------------------------------------------------ adaptarile pe situri (0.7.5)
     * O aplicatie stricata la post, reparata aici pentru om, cate o functie pe sit. Fiecare lucreaza numai cand pagina
     * chiar da de greseala (dupa raspunsul serverului postului sau dupa un termen), fara numere scrise de mana, deci nu
     * schimba nimic cand postul isi repara aplicatia. Fiecare scrie un rand in jurnalul erorilor paginii (hdsnaverori).
     *
     * TVP (hbbn.tvp.pl): teaserul canalelor TVP duce ROSU (dupa pagina de confidentialitate) spre hub-ul /apps/hub/ cu
     * ancora #website-<numar>. Serverul TVP raspunde la data_proxy.php?uri=/tv/v2/website/<numar> "Podany zasob nie
     * istnieje" (E-API-08), iar scriptul hub-ului ramane la "Trwa wczytywanie". Cand raspunsul pentru acelasi <numar> e
     * o eroare (cod HTTP de eroare, nu e JSON, success 0, server_response de la 400 in sus, data lipsa sau lista goala)
     * sau, ca rezerva, incarcarea (#mainLoader) e inca pe ecran dupa TVP_ASTEPTARE_MS, hub-ul trece o singura data pe
     * pagina lui principala (ancora #mainpage, "APLIKACJE"), care merge. Un raspuns bun opreste adaptarea. */

    var TVP_ASTEPTARE_MS = 10000;

    function jurnalPagina(text) {
        try {
            window.webkit.messageHandlers.hdsnaverori.postMessage(String(text).slice(0, 200));
        } catch (x) {
            /* lansatorul nu are jurnalul paginii: nimic */
        }
    }

    function raspunsTvpProst(stare, text) {
        if (stare === 0 || stare >= 400)
            return true;
        var o;
        try {
            o = JSON.parse(text);
        } catch (x) {
            return true;
        }
        if (!o || typeof o !== "object")
            return true;
        if (o.success === 0 || o.success === false || Number(o.server_response) >= 400)
            return true;
        return o.data === undefined || o.data === null || (Array.isArray(o.data) && o.data.length === 0);
    }

    function adaptareTvpHub() {
        var loc = window.location;
        if (!loc || loc.hostname !== "hbbn.tvp.pl" || !/^\/apps\/hub\/(index\.php)?$/.test(loc.pathname || ""))
            return false;
        var m = /^#website-([0-9]{1,12})$/.exec(loc.hash || "");
        if (!m)
            return false;
        var ancora = "#website-" + m[1];
        var cerere = new RegExp("[?&]uri=/tv/v2/website/" + m[1] + "(?![0-9])");
        var baza = String(loc.href).split("#")[0];
        var gata = false, bun = false;

        function muta(motiv) {
            if (gata || bun || loc.hash !== ancora)
                return;
            gata = true;
            jurnalPagina("adaptare TVP: sectiunea " + ancora.slice(1) + " " + motiv + "; hub-ul trece pe pagina principala");
            try {
                loc.replace(baza + "#mainpage");
            } catch (x) {
                /* nimic de facut */
            }
        }

        var X = window.XMLHttpRequest;
        if (X && X.prototype && typeof X.prototype.open === "function" && typeof X.prototype.send === "function") {
            var deschide = X.prototype.open, trimiteX = X.prototype.send;
            X.prototype.open = function (metoda, adresa) {
                try {
                    this.__hdsTvpWebsite = cerere.test(String(adresa));
                } catch (x) {
                    /* adresa ciudata: nu e a noastra */
                }
                return deschide.apply(this, arguments);
            };
            X.prototype.send = function () {
                if (this.__hdsTvpWebsite) {
                    var x = this;
                    try {
                        x.addEventListener("loadend", function () {
                            if (raspunsTvpProst(x.status, x.responseText))
                                muta("lipseste la post (" + (x.status || "fara raspuns") + ")");
                            else
                                bun = true;
                        });
                    } catch (e) {
                        /* fara ascultator: ramane rezerva cu termen */
                    }
                }
                return trimiteX.apply(this, arguments);
            };
        }
        setTimeout(function () {
            try {
                var l = document.getElementById("mainLoader");
                if (l && window.getComputedStyle(l).display !== "none")
                    muta("inca se incarca dupa " + TVP_ASTEPTARE_MS / 1000 + " s");
            } catch (x) {
                /* nimic */
            }
        }, TVP_ASTEPTARE_MS);
        return true;
    }

    /* Adaptare TVP (HB4, 0.7.7): aplicatia TVP a canalelor terestre (canalele virtuale, hbb-prod.tvp.pl/apps/manager)
     * citeste starea filmului din extra.stateReady.code, pe care o pun numai motoarele ei html5 si hls.js; motorul "Object"
     * (obiectul A/V) pune extra.statePlay, si acela gol: compara playState (numar, OIPF 0-6) cu starile lor, care sunt
     * siruri ("playing"...). Fara adaptare pagina cade la primul PlayStateChange (3), filmul se opreste si "Trwa
     * wczytywanie..." ramane (olo, forum 1148). Numai pe paginile acelei aplicatii: stateReady, pe obiectele care au
     * statePlay al lor, e starea data de numarul primit de functia de eveniment (extra.event) cand statePlay n-are cod,
     * altfel statePlay; o scriere face proprietatea proprie (ca fara adaptare); playState ramane numar (alte pagini TVP il
     * compara ca numar). Cu obiectul A/V, MediaSource e ascuns acolo: aplicatia alege atunci Object (playerul
     * receptorului) si pe WebKit-ul cu video, nu hls.js pe MSE. */
    var TVP_STARI = ["stopped", "playing", "pause", "connecting", "buffering", "ended", "error"];

    /* A treia greseala TVP (HB4, runda 2): pe virtual-channel proprietatea calculata video face push in
     * usedOrInaccessibleFormats la fiecare citire; cand Vue o citeste de doua ori inainte de player, filmul iese undefined
     * si pagina sta la "Trwa wczytywanie..." fara sa ceara nimic (~1 din 10 porniri, si fara strat). O singura reincarcare
     * a documentului, cand incarcarea e inca pe ecran dupa TVP_REINCARCARE_MS si pagina n-a pornit niciun film prin
     * obiectul A/V; semnul din window.name tine cat traieste navigatorul (alt ROSU = alt navigator). */
    var TVP_REINCARCARE_MS = 20000, TVP_SEMN_REINCARCAT = "hds-tvp-reincarcat";

    function reincarcareTvp(loc) {
        var pagina = /^\/apps\/manager\/virtual-channel/;
        try {
            if (String(window.name || "").indexOf(TVP_SEMN_REINCARCAT) >= 0)
                return false;
        } catch (x) {
            return false;
        }
        setTimeout(function () {
            try {
                if (avUltimId > 0 || !pagina.test(loc.pathname || ""))
                    return;
                var l = document.getElementById("mainLoader");
                if (!l || window.getComputedStyle(l).display === "none")
                    return;
                var nume = String(window.name || "");
                window.name = (nume ? nume + " " : "") + TVP_SEMN_REINCARCAT;
                jurnalPagina("adaptare TVP: incarcarea e inca pe ecran dupa " + TVP_REINCARCARE_MS / 1000 +
                    " s, fara film; pagina se reincarca o data");
                loc.reload();
            } catch (x) {
                /* nimic de facut: ramane ca fara adaptare */
            }
        }, TVP_REINCARCARE_MS);
        return true;
    }

    function adaptareTvpStare() {
        var loc = window.location;
        if (!loc || !/(^|\.)tvp\.pl$/.test(loc.hostname || "") || !/^\/apps\/manager\//.test(loc.pathname || ""))
            return false;
        if ("stateReady" in Object.prototype)
            return false;
        var faraMse = false, scris = false;
        if (/^\/apps\/manager\/virtual-channel/.test(loc.pathname || ""))
            reincarcareTvp(loc);
        if (avPornit) {
            ["MediaSource", "WebKitMediaSource", "ManagedMediaSource"].forEach(function (n) {
                try {
                    if (window[n] !== undefined) {
                        Object.defineProperty(window, n, { value: undefined, writable: true, configurable: true });
                        faraMse = true;
                    }
                } catch (x) {
                    /* proprietatea nu se poate schimba: aplicatia alege ca inainte */
                }
            });
        }
        try {
            Object.defineProperty(Object.prototype, "stateReady", {
                configurable: true,
                enumerable: false,
                get: function () {
                    if (!Object.prototype.hasOwnProperty.call(this, "statePlay"))
                        return undefined;
                    var s = this.statePlay, n = this.event;
                    if (s && typeof s === "object" && s.code === undefined && typeof n === "number" && TVP_STARI[n]) {
                        if (!scris) {
                            scris = true;
                            jurnalPagina("adaptare TVP: starea motorului Object data paginii (" + TVP_STARI[n] + ")" +
                                (faraMse ? "; MediaSource ascuns" : ""));
                        }
                        return { code: TVP_STARI[n], type: TVP_STARI[n].toUpperCase() };
                    }
                    return s;
                },
                set: function (v) {
                    Object.defineProperty(this, "stateReady", { value: v, writable: true, enumerable: true,
                        configurable: true });
                }
            });
        } catch (x) {
            return false;
        }
        return true;
    }

    /* Adaptare TVP (CR2, 0.7.8): hub-ul TVP GO si celelalte pagini ale aplicatiei TVP manager (hbb-prod.tvp.pl/apps/manager/,
     * in afara de virtual-channel, care are reincarcarea ei de mai sus) arata "Trwa wczytywanie..." (.loading, cu animatia
     * ellipsis) cat timp datele paginii (fetch-ul Nuxt, cererile graphql) nu s-au terminat. La un om (TVP 1 de pe satelit,
     * hub-ul hbbtest.v3.tvp.pl/hub/index_tvp_1.php, Vu+ Uno 4K SE) incarcarea a ramas pe ecran; la noi (PC si
     * receptor, din Romania) hub-ul se incarca sub 10 s, deci cauza nu s-a putut vedea. Aici: cand incarcarea sta pe ecran
     * cel putin TVP_MANAGER_MS (acelasi element, vazut la verificarile din TVP_MANAGER_PAS_MS in TVP_MANAGER_PAS_MS: o
     * incarcare noua, de la alta pagina a hub-ului, e alt element) si niciun film n-a pornit prin obiectul A/V, un rand in
     * jurnalul paginii cu calea si cererile inca neterminate (din el aflam cauza) si o singura reincarcare a documentului
     * (semnul din window.name al reincarcarii de pe virtual-channel: cel mult una pe navigator). O incarcare terminata sub 30 s
     * nu schimba nimic; una legitima mai lunga (receptor foarte lent) costa o incarcare in plus, o data. */
    var TVP_MANAGER_MS = 30000, TVP_MANAGER_PAS_MS = 15000;

    function incarcareTvpPeEcran() {
        var l = typeof document.querySelectorAll === "function" ? document.querySelectorAll(".loading") : [];
        for (var i = 0; i < l.length; i++) {
            if (/wczytywanie/i.test(String(l[i].textContent || "")) && window.getComputedStyle(l[i]).display !== "none")
                return l[i];
        }
        return null;
    }

    /* Adaptare TVP (HBT2, 0.8.0): filmele din hub-ul TVP GO (hbb-prod.tvp.pl/apps/manager/hub/, OK pe un film). Aplicatia
     * isi pune datele filmului in depozitul ei (mutatia pages/hub/setChosenPlayerVideoData), iar comenzile playerului
     * citesc din ele, la creare, video.data[0].dates.start. La filmele la cerere raspunsul serverului TVP nu are campul
     * dates (il au numai emisiunile in direct), deci comenzile cad la creare, aplicatia trece in pagina ei de eroare si
     * isi opreste singura filmul abia pornit: la om filmul porneste o clipa, apoi revine canalul si aplicatia nu se mai
     * vede. La fel se intampla pe PC, si fara stratul nostru. Codul comenzilor stie de un inceput nedefinit (arata
     * "-"), deci aici filmul venit fara dates primeste unul gol, inainte ca mutatia sa ajunga in depozit. Numai pe
     * paginile aplicatiei TVP manager; cand campul vine de la TVP, adaptarea nu face nimic. Un rand in jurnalul
     * paginii, o data. */
    var TVP_MUTATIE_FILM = "pages/hub/setChosenPlayerVideoData";

    function adaptareTvpFilm() {
        var loc = window.location;
        if (!loc || !/(^|\.)tvp\.pl$/.test(loc.hostname || "") || !/^\/apps\/manager\//.test(loc.pathname || ""))
            return false;
        var nuxt, scris = false, scrisLive = false;

        function completeaza(date) {
            var f = date && date.video && date.video.data && date.video.data[0];
            if (!f || typeof f !== "object")
                return;
            /* AS222 (26.11.2026): canalele "Na zywo" vin fara akpa_attributes, iar player.vue
             * (getSingleVideoForTokenizerLiveNPVR) cheama e.akpa_attributes.includes dupa mutatie: o lista goala */
            if (f.akpa_attributes === undefined || f.akpa_attributes === null) {
                f.akpa_attributes = [];
                if (!scrisLive) {
                    scrisLive = true;
                    jurnalPagina("adaptare TVP: datele emisiunii in direct au venit fara akpa_attributes; pusa o lista goala");
                }
            }
            if (f.dates !== undefined)
                return;
            f.dates = {};
            if (!scris) {
                scris = true;
                jurnalPagina("adaptare TVP: datele filmului au venit fara dates; pus unul gol, ca playerul sa porneasca");
            }
        }

        function leaga(n) {
            var s = n && n.$store;
            if (!s || typeof s.commit !== "function" || s.commit.__hdsTvpFilm)
                return;
            var comite = s.commit;
            var nou = function (tip, date) {
                try {
                    if (tip === TVP_MUTATIE_FILM)
                        completeaza(date);
                    else if (tip && typeof tip === "object" && tip.type === TVP_MUTATIE_FILM)
                        completeaza(tip);
                } catch (x) {
                    /* date de alta forma: mutatia merge neschimbata */
                }
                return comite.apply(this, arguments);
            };
            nou.__hdsTvpFilm = true;
            s.commit = nou;
        }

        try {
            /* aplicatia (Nuxt) se pune singura in window.$nuxt cand e creata; depozitul ei e atunci gata */
            nuxt = window.$nuxt;
            Object.defineProperty(window, "$nuxt", {
                configurable: true,
                enumerable: true,
                get: function () { return nuxt; },
                set: function (n) {
                    nuxt = n;
                    try {
                        leaga(n);
                    } catch (x) {
                        /* depozit de alta forma: aplicatia merge ca fara adaptare */
                    }
                }
            });
            leaga(nuxt);
        } catch (x) {
            return false;
        }
        return true;
    }

    function adaptareTvpManager() {
        var loc = window.location;
        if (!loc || !/(^|\.)tvp\.pl$/.test(loc.hostname || "") || !/^\/apps\/manager\//.test(loc.pathname || "") ||
                /^\/apps\/manager\/virtual-channel/.test(loc.pathname || ""))
            return false;
        try {
            if (String(window.name || "").indexOf(TVP_SEMN_REINCARCAT) >= 0)
                return false;
        } catch (x) {
            return false;
        }
        var deschise = [], dela = 0, vazut = null, gata = false;

        function scurt(a) {
            return String(a || "").replace(/^[a-z]+:\/\/[^\/]+/i, "").split("?")[0].slice(0, 60);
        }

        function scoate(a) {
            var i = deschise.indexOf(a);
            if (i >= 0)
                deschise.splice(i, 1);
        }

        var X = window.XMLHttpRequest;
        if (X && X.prototype && typeof X.prototype.open === "function" && typeof X.prototype.send === "function") {
            var deschide = X.prototype.open, trimiteX = X.prototype.send;
            X.prototype.open = function (metoda, adresa) {
                try {
                    this.__hdsTvpCale = scurt(adresa);
                } catch (x) {
                    /* adresa ciudata: nu o urmarim */
                }
                return deschide.apply(this, arguments);
            };
            X.prototype.send = function () {
                var x = this, a = x.__hdsTvpCale;
                if (a) {
                    deschise.push(a);
                    try {
                        x.addEventListener("loadend", function () { scoate(a); });
                    } catch (e) {
                        scoate(a);
                    }
                }
                return trimiteX.apply(this, arguments);
            };
        }
        if (typeof window.fetch === "function") {
            var aduceTvp = window.fetch;
            window.fetch = function (cerere) {
                var a = scurt(cerere && typeof cerere === "object" && cerere.url ? cerere.url : cerere);
                var p = aduceTvp.apply(this, arguments);
                if (p && typeof p.then === "function") {
                    deschise.push(a);
                    p.then(function () { scoate(a); }, function () { scoate(a); });
                }
                return p;
            };
        }

        function verifica() {
            if (gata)
                return;
            var acum = Date.now(), el = null;
            try {
                el = incarcareTvpPeEcran();
            } catch (x) {
                /* fara DOM: nu e incarcarea */
            }
            if (!el || avUltimId > 0 || el !== vazut) {
                vazut = avUltimId > 0 ? null : el;
                dela = vazut ? acum : 0;
            } else if (acum - dela >= TVP_MANAGER_MS) {
                gata = true;
                try {
                    var nume = String(window.name || "");
                    window.name = (nume ? nume + " " : "") + TVP_SEMN_REINCARCAT;
                    jurnalPagina("adaptare TVP: reincarc o data, incarcarea sta de " + Math.round((acum - dela) / 1000) + " s pe " +
                        String(loc.pathname || "").slice(0, 40) + " (" + document.readyState + "); neterminate: " +
                        (deschise.length ? deschise.slice(0, 3).map(function (a) { return a.slice(0, 40); }).join(", ") : "niciuna"));
                    loc.reload();
                } catch (x) {
                    /* nimic de facut: ramane ca fara adaptare */
                }
                return;
            }
            setTimeout(verifica, TVP_MANAGER_PAS_MS);
        }
        setTimeout(verifica, TVP_MANAGER_PAS_MS);
        return true;
    }

    /* ------------------------------------------------------------ animatiile cand desenul e pe procesor (0.7.7)
     * Fara placa grafica (rezerva pe procesor: GL cade pe Mali-450, deci pe SF8008 si celelalte cu Mali-450, sau --cpu)
     * pagina n-are compunere: o animatie CSS lunga (o sigla care pulseaza, un cerc care se invarte) se redeseneaza la
     * fiecare cadru pe firul principal al procesului web. Desenul cu procesorul tine cat un cadru sau mai mult, deci firul
     * ramane ocupat, iar ceasurile JavaScript (setTimeout, setInterval) si restul nu mai ajung la rand: aplicatia sta pe
     * ecranul de incarcare (o mediateca cu sigla "pulsate 6s infinite": WPEWebProcess la 100 % minute intregi; cu animatia
     * oprita ajunge la pagina de start in 8 s). Aici, numai fara compunere ((-webkit-transform-3d) fals; config.desen
     * "procesor" sau "gl" o hotaraste in locul ei): animatiile CSS fara sfarsit (animation-iteration-count: infinite) se
     * opresc (pause) la pornire (animationstart) si le mutam noi la fiecare ANIM_PAS_MS (currentTime), ~10 cadre pe secunda:
     * arata la fel, dar lasa firul paginii liber. Cele cu sfarsit raman ale paginii (se termina singure, cu animationend).
     * Cu compunere (placa grafica) nu se schimba nimic. Un rand in jurnalul paginii, o data pe document. */
    var ANIM_PAS_MS = 100;

    function faraCompunere() {
        if (S.config && (S.config.desen === "procesor" || S.config.desen === "gl"))
            return S.config.desen === "procesor";
        try {
            return typeof window.matchMedia === "function" && !window.matchMedia("(-webkit-transform-3d)").matches;
        } catch (x) {
            return false;
        }
    }

    function animatiiPeProcesor() {
        if (typeof window.addEventListener !== "function" || !window.Element || !window.Element.prototype ||
                typeof window.Element.prototype.getAnimations !== "function")
            return false;
        var mutate = [], ceas = null, scris = false, fara = null;

        function pas() {
            ceas = null;
            var acum = Date.now();
            mutate = mutate.filter(function (m) {
                var a = m.a;
                /* oprita, terminata sau scoasa de pagina, ori pornita din nou de ea (play): nu mai e a noastra */
                if (a.playState !== "paused" || (m.el.isConnected === false))
                    return false;
                try {
                    a.currentTime = m.t0 + (acum - m.p0) * (typeof a.playbackRate === "number" ? a.playbackRate : 1);
                } catch (x) {
                    return false;
                }
                return true;
            });
            if (mutate.length)
                ceas = setTimeout(pas, ANIM_PAS_MS);
        }

        function faraSfarsit(a) {
            var t = a.effect && typeof a.effect.getComputedTiming === "function" ? a.effect.getComputedTiming() : null;
            return !!t && t.activeDuration === Infinity;
        }

        window.addEventListener("animationstart", function (e) {
            if (fara === null)
                fara = faraCompunere();
            var el = e && e.target;
            if (!fara || !el || typeof el.getAnimations !== "function")
                return;
            var noi = 0;
            el.getAnimations({ subtree: true }).forEach(function (a) {
                if (a.animationName !== e.animationName || a.playState !== "running" || !faraSfarsit(a))
                    return;
                for (var i = 0; i < mutate.length; i++) {
                    if (mutate[i].a === a)
                        return;
                }
                var t0 = a.currentTime || 0;
                try {
                    a.pause();
                } catch (x) {
                    return;
                }
                mutate.push({ a: a, el: el, t0: t0, p0: Date.now() });
                noi++;
            });
            if (noi && !scris) {
                scris = true;
                jurnalPagina("adaptare desen pe procesor: animatiile fara sfarsit ale paginii merg cu " + 1000 / ANIM_PAS_MS +
                    " cadre pe secunda (" + String(e.animationName).slice(0, 40) + ")");
            }
            if (mutate.length && !ceas)
                ceas = setTimeout(pas, ANIM_PAS_MS);
        }, true);
        return true;
    }

    /* Jurnalul filmelor paginii (MDS1, 0.7.8): cand un element <video>/<audio> al paginii nu poate reda (evenimentul
     * "error" al elementului, prins la capturare pe window), un rand in jurnalul paginii numai cu date controlate: codul
     * MediaError si numele lui, felul sursei (numai din listele inchise de la felSursa, niciodata adresa) si daca pagina a cerut
     * inainte o licenta DRM. Textul liber MediaError.message NU se scrie: poate purta adrese cu jetoane pe care nicio
     * curatare nu le prinde sigur (paranteze, spatii, alte forme). Fara el jurnalul arata
     * numai "promisiune respinsa: The operation is not supported." (play() respinsa de WebKit cand elementul are
     * MEDIA_ERR_SRC_NOT_SUPPORTED), fara sa se vada ce film si de ce (asistenta 162189). Numai citire: pagina
     * primeste aceleasi evenimente si aceleasi promisiuni ca inainte (nimic prins, nimic oprit). Cel mult un rand pe
     * element si FILME_JURNAL_MAXIM pe document (paginile reincearca). */
    var FILME_JURNAL_MAXIM = 4;
    var MEDIA_ERORI = ["", "oprit de pagina", "retea", "decodare", "sursa nesuportata"];

    /* Felul sursei, numai din liste inchise: nicio bucata din adresa paginii nu ajunge in jurnal. Schema: blob (MSE),
     * http, https, data, dvb, altfel "alta"; extensia (numai la http/https): una din FILME_EXTENSII, altfel "necunoscuta". */
    var FILME_SCHEME = { blob: "MSE (blob)", http: "http", https: "https", data: "data", dvb: "dvb" };
    var FILME_EXTENSII = ["mpd", "m3u8", "m3u", "mp4", "m4v", "m4s", "m4a", "ts", "mpg", "mpeg", "webm", "mkv", "mov",
        "mp3", "aac", "ogg", "opus", "wav", "flac", "ism", "isml"];

    function felSursa(el) {
        var u = "";
        try {
            u = String(el.currentSrc || el.getAttribute("src") || "");
        } catch (x) {
            u = "";
        }
        if (!u)
            return "fara sursa";
        var m = /^\s*([a-z][a-z0-9+.-]*):/i.exec(u);
        var schema = m ? m[1].toLowerCase() : "";
        if (!Object.prototype.hasOwnProperty.call(FILME_SCHEME, schema))
            return m ? "alta" : "fara schema";
        if (schema !== "http" && schema !== "https")
            return FILME_SCHEME[schema];
        var cale = u.split(/[?#]/)[0];
        var e = /\.([A-Za-z0-9]{1,5})$/.exec(cale.slice(cale.lastIndexOf("/") + 1));
        var ext = e ? e[1].toLowerCase() : "";
        return FILME_SCHEME[schema] + " " + (FILME_EXTENSII.indexOf(ext) >= 0 ? "." + ext : "necunoscuta");
    }

    function jurnalFilme() {
        var Media = window.HTMLMediaElement;
        if (typeof Media !== "function" || typeof window.addEventListener !== "function")
            return false;
        var vazute = typeof WeakSet === "function" ? new WeakSet() : null, scrise = 0;
        window.addEventListener("error", function (ev) {
            try {
                var el = ev && ev.target;
                if (!vazute || scrise >= FILME_JURNAL_MAXIM || !(el instanceof Media) || vazute.has(el))
                    return;
                var er = el.error;
                if (!er || typeof er.code !== "number")
                    return;
                vazute.add(el);
                scrise++;
                var cod = er.code | 0;
                var t = "filmul paginii nu porneste: <" + (typeof window.HTMLVideoElement === "function" && el instanceof window.HTMLVideoElement ? "video" :
                    "audio") +
                    "> cod " + cod + (MEDIA_ERORI[cod] ? " (" + MEDIA_ERORI[cod] + ")" : "") + "; sursa " + felSursa(el);
                if (drmCerut !== null)
                    t += "; pagina a cerut inainte o licenta DRM (" + drmCerut + "): film probabil protejat";
                jurnalPagina(t);
            } catch (x) {
                /* numai jurnal: pagina merge ca fara el */
            }
        }, true);
        return true;
    }

    /* <video> HTML5 PE PLAYERUL RECEPTORULUI (AS192 si HBB9): WebKit-ul imaginii e construit fara video, deci
     * un <video>/<audio> cu sursa http(s) .m3u8/.mpd/.mp4/.ts da cod 4 (aplicatiile iphd.it: SUPERSIX, Telerent 7Gold,
     * Rete 7). Aici, numai cu obiectul A/V pornit (LANSATOR.av): sursa http(s) cu una din extensiile din VIDEO_TIPURI sau cu
     * un atribut type din AV_TIPURI (al elementului sau al copilului <source>) nu mai ajunge la WebKit; play() porneste
     * filmul pe playerul receptorului ca obiectul A/V (aceleasi comenzi "av"), in dreptunghiul elementului, iar pagina
     * primeste evenimentele unui <video> (loadstart, playing, pause, waiting, timeupdate, ended, error) si proprietatile lui
     * (paused, currentTime, duration, readyState, error). Sursa venita din HTML (atributul src scris in pagina, copiii
     * <source>) se ia la load(), la play() si, pentru elementele cu autoplay, la DOMContentLoaded. Celelalte surse raman
     * la WebKit. */
    var VIDEO_TIPURI = { m3u8: "application/vnd.apple.mpegurl", m3u: "application/vnd.apple.mpegurl",
        mpd: "application/dash+xml", mp4: "video/mp4", m4v: "video/mp4", ts: "video/mpeg", mp3: "audio/mpeg" };

    function videoTrimite(el, nume) {
        nume.forEach(function (n) {
            setTimeout(function () {
                var ev;
                try {
                    ev = new Event(n, { bubbles: false, cancelable: false });
                } catch (x) {
                    ev = document.createEvent("Event");
                    ev.initEvent(n, false, false);
                }
                try {
                    el.dispatchEvent(ev);
                } catch (x) {
                    /* nimic */
                }
            }, 0);
        });
    }

    function videoEvenimente(el, joc) {
        var a = av(el);
        if (joc === AV_CONECTARE)
            videoTrimite(el, ["loadstart", "waiting"]);
        else if (joc === AV_REDA) {
            var l = a.html5Inceput ? ["play", "playing"] : ["durationchange", "loadedmetadata", "loadeddata", "canplay",
                "canplaythrough", "play", "playing"];
            a.html5Inceput = true;
            videoTrimite(el, l);
        } else if (joc === AV_PAUZA)
            videoTrimite(el, ["pause"]);
        else if (joc === AV_ASTEAPTA)
            videoTrimite(el, ["waiting"]);
        else if (joc === 5)
            videoTrimite(el, ["ended"]);
        else if (joc === AV_EROARE)
            videoTrimite(el, ["error"]);
    }

    function videoHtml5() {
        var M = window.HTMLMediaElement;
        if (!avPornit || typeof M !== "function" || !M.prototype)
            return false;
        var P = M.prototype, E = window.Element && window.Element.prototype;
        function desc(n) {
            for (var o = P; o; o = Object.getPrototypeOf(o)) {
                var d = Object.getOwnPropertyDescriptor(o, n);
                if (d)
                    return d;
            }
            return null;
        }
        var nativ = {};
        ["src", "currentSrc", "currentTime", "duration", "paused", "ended", "readyState", "networkState", "error",
            "seeking"].forEach(function (n) { nativ[n] = desc(n); });
        var playNativ = P.play, pauseNativ = P.pause, loadNativ = P.load;
        /* tipul filmului: atributul type (daca e unul al obiectului A/V), altfel extensia adresei; "" = nu e al nostru */
        function tipDe(u, tip) {
            var t = String(tip || "").split(";")[0].trim().toLowerCase();
            if (t && AV_TIPURI.indexOf(t) >= 0)
                return t;
            var cale = u.split(/[?#]/)[0];
            var e = /\.([A-Za-z0-9]{1,5})$/.exec(cale.slice(cale.lastIndexOf("/") + 1));
            return e && VIDEO_TIPURI[e[1].toLowerCase()] || "";
        }
        /* adresa intreaga, daca filmul merge pe playerul receptorului (http/https si tip cunoscut); altfel "" */
        function adresa(u, tip) {
            u = String(u || "").trim();
            if (!u)
                return "";
            try {
                u = new URL(u, document.baseURI || window.location.href).href;
            } catch (x) {
                /* asa cum e */
            }
            if (!/^https?:\/\//i.test(u))
                return "";
            return tipDe(u, tip) ? u : "";
        }
        function atribut(el, n) {
            return E && E.getAttribute ? E.getAttribute.call(el, n) : null;
        }
        /* sursa scrisa in HTML: atributul src al elementului, altfel primul copil <source> bun; null daca nu e */
        function sursaDinHtml(el) {
            var tipEl = atribut(el, "type"), u = adresa(atribut(el, "src"), tipEl);
            if (u)
                return { u: u, tip: tipDe(u, tipEl) };
            var copii = el.children || el.childNodes || [];
            for (var i = 0; i < copii.length; i++) {
                var c = copii[i];
                if (!c || String(c.tagName || "").toUpperCase() !== "SOURCE")
                    continue;
                var t = atribut(c, "type");
                u = adresa(atribut(c, "src"), t);
                if (u)
                    return { u: u, tip: tipDe(u, t) };
            }
            return null;
        }
        function al(el) {
            var a = av(el);
            return a.html5Src ? a : null;
        }
        /* valorile puse de pagina pe un nume pe care WebKit nu-l are pe prototip (n-ar trebui sa fie cazul in WebKit;
         * pastreaza purtarea unei proprietati obisnuite a elementului) */
        var proprii = typeof WeakMap === "function" ? new WeakMap() : null;
        function citeste(n, el) {
            var d = nativ[n];
            if (d && d.get)
                return d.get.call(el);
            var o = proprii && proprii.get(el);
            return o && Object.prototype.hasOwnProperty.call(o, n) ? o[n] : undefined;
        }
        function scrieNativ(n, el, v) {
            var d = nativ[n];
            if (d && d.set)
                d.set.call(el, v);
            else if (!d && proprii) {
                var o = proprii.get(el);
                if (!o)
                    proprii.set(el, o = {});
                o[n] = v;
            }
            /* d fara set (numai citire in WebKit): nimic, ca atribuirea pe o proprietate numai de citit */
        }
        function puneSursa(el, u, tip) {
            var a = av(el);
            if (avActiv === el && avInMers(a.joc))
                avOpresteTot(el);
            /* filmul de dinainte (terminat, cazut) nu-si lasa starea sursei noi: ended, error, currentTime, duration */
            a.joc = AV_OPRIT;
            a.eroare = undefined;
            a.poz = a.pozLa = a.lung = 0;
            a.pauzaCeruta = false;
            a.html5 = true;
            a.html5Src = u;
            a.html5Tip = tipDe(u, tip);
            a.html5Inceput = false;
            videoTrimite(el, ["loadstart", "durationchange", "loadedmetadata", "loadeddata", "canplay", "canplaythrough"]);
            if (el.autoplay || (el.hasAttribute && el.hasAttribute("autoplay")))
                setTimeout(function () { if (av(el).html5Src === u) porneste(el); }, 0);
        }
        function scoateSursa(el) {
            var a = av(el);
            if (a.html5Src && avActiv === el && avInMers(a.joc))
                avOpresteTot(el);
            a.html5Src = "";
            a.html5 = false;
        }
        function porneste(el) {
            var a = av(el);
            if (avActiv === el && avInMers(a.joc)) {
                a.pauzaCeruta = false;
                if (a.viteza === 0) {
                    a.viteza = 1;
                    trimite("av", "viteza", 1);   /* play/playing vin cu starea REDA de la enigma2 */
                }
                return;
            }
            var b = b64(a.html5Src);
            if (b.length > AV_B64_MAXIM) {
                avSchimba(el, AV_EROARE, 4);
                return;
            }
            avIaDecodorul(el);
            a.id = ++avUltimId;
            a.poz = a.pozLa = a.lung = 0;
            a.viteza = 1;
            a.pauzaCeruta = false;
            a.piste = [];
            a.inPagina = false;
            a.ecranIntreg = false;
            trimite("av", "porneste", a.id, b, a.html5Tip || tipDe(a.html5Src));
            avSchimba(el, AV_CONECTARE);
            urmaresteAv(el, true);
        }
        try {
            Object.defineProperty(P, "src", { configurable: true, enumerable: true,
                get: function () {
                    var a = al(this);
                    return a ? a.html5Src : citeste("src", this);
                },
                set: function (u) {
                    var t = atribut(this, "type") || av(this).tipCerut, x = adresa(u, t);
                    if (x) {
                        puneSursa(this, x, t);
                        return;
                    }
                    scoateSursa(this);
                    scrieNativ("src", this, u);
                } });
            Object.defineProperty(P, "currentSrc", { configurable: true, enumerable: true,
                get: function () {
                    var a = al(this);
                    return a ? a.html5Src : citeste("currentSrc", this);
                } });
            Object.defineProperty(P, "currentTime", { configurable: true, enumerable: true,
                get: function () {
                    var a = al(this);
                    return a ? avPozitie(this) / 1000 : citeste("currentTime", this);
                },
                set: function (t) {
                    var a = al(this);
                    if (!a) {
                        scrieNativ("currentTime", this, t);
                        return;
                    }
                    var ms = Math.round(Number(t) * 1000);
                    if (avActiv === this && avInMers(a.joc) && isFinite(ms) && ms >= 0)
                        trimite("av", "cauta", ms);
                } });
            Object.defineProperty(P, "duration", { configurable: true, enumerable: true,
                get: function () {
                    var a = al(this);
                    if (!a)
                        return citeste("duration", this);
                    return a.lung > 0 ? a.lung / 1000 : Infinity;
                } });
            Object.defineProperty(P, "paused", { configurable: true, enumerable: true,
                get: function () {
                    var a = al(this);
                    return a ? !(avInMers(a.joc) && a.viteza === 1) : citeste("paused", this);
                } });
            Object.defineProperty(P, "ended", { configurable: true, enumerable: true,
                get: function () {
                    var a = al(this);
                    return a ? a.joc === 5 : citeste("ended", this);
                } });
            Object.defineProperty(P, "seeking", { configurable: true, enumerable: true,
                get: function () {
                    return al(this) ? false : citeste("seeking", this);
                } });
            Object.defineProperty(P, "readyState", { configurable: true, enumerable: true,
                get: function () {
                    var a = al(this);
                    return a ? (a.joc === AV_ASTEAPTA || a.joc === AV_CONECTARE ? 2 : a.joc === AV_EROARE ? 0 : 4) :
                        citeste("readyState", this);
                } });
            Object.defineProperty(P, "networkState", { configurable: true, enumerable: true,
                get: function () {
                    var a = al(this);
                    return a ? (avInMers(a.joc) ? 2 : 1) : citeste("networkState", this);
                } });
            Object.defineProperty(P, "error", { configurable: true, enumerable: true,
                get: function () {
                    var a = al(this);
                    if (!a)
                        return citeste("error", this);
                    return a.joc === AV_EROARE ? { code: 2, message: "" } : null;
                } });
            /* numele numai de citire primesc si scrierea, trecuta mai departe la WebKit (vezi scrieNativ) */
            ["currentSrc", "duration", "paused", "ended", "seeking", "readyState", "networkState", "error"]
                .forEach(function (n) {
                    var d = Object.getOwnPropertyDescriptor(P, n);
                    Object.defineProperty(P, n, { configurable: true, enumerable: true, get: d.get,
                        set: function (v) { scrieNativ(n, this, v); } });
                });
            /* canPlayType (LAN1): playerele aplicatiilor (Rubidia: Video Mediterraneo, Video Regione, TeleNord) pun sursa
             * HLS pe <video> numai daca el spune ca o poate reda; altfel incearca hls.js (cere MediaSource, care lipseste)
             * si raman pe rotita. Raspunsul WebKit-ului ramane cand nu e gol; altfel tipurile pe care le reda playerul
             * receptorului (AV_TIPURI, si cu parametri: codecs=...) primesc "maybe", iar tipul ramane tinut pe element:
             * sursa pusa dupa aceea fara atributul type si fara extensie cunoscuta (lista HLS cu ?token=) il ia pe el. */
            var canPlayNativ = P.canPlayType;
            P.canPlayType = function (tip) {
                var r = typeof canPlayNativ === "function" ? canPlayNativ.apply(this, arguments) : "";
                if (r)
                    return r;
                var t = String(tip || "").split(";")[0].trim().toLowerCase();
                if (t && AV_TIPURI.indexOf(t) >= 0) {
                    av(this).tipCerut = t;
                    return "maybe";
                }
                return "";
            };
            P.play = function () {
                if (!al(this)) {
                    var h = sursaDinHtml(this);
                    if (!h)
                        return playNativ.apply(this, arguments);
                    puneSursa(this, h.u, h.tip);
                }
                porneste(this);
                return typeof Promise === "function" ? Promise.resolve() : undefined;
            };
            P.pause = function () {
                var a = al(this);
                if (!a)
                    return pauseNativ.apply(this, arguments);
                if (avActiv !== this || !avInMers(a.joc))
                    return;
                if (a.joc === AV_CONECTARE) {
                    a.pauzaCeruta = true;   /* ca la obiectul A/V: pauza abia cand filmul a inceput */
                    return;
                }
                if (a.viteza !== 0) {
                    a.viteza = 0;
                    trimite("av", "viteza", 0);   /* evenimentul pause vine cu starea PAUZA de la enigma2 */
                }
            };
            P.load = function () {
                var a = al(this);
                if (!a) {
                    var h = sursaDinHtml(this);
                    if (!h)
                        return loadNativ.apply(this, arguments);
                    puneSursa(this, h.u, h.tip);   /* puneSursa porneste singura filmul cu autoplay */
                    return;
                }
                videoTrimite(this, ["emptied"]);
                puneSursa(this, a.html5Src, a.html5Tip);   /* opreste filmul, loadstart..canplaythrough, autoplay */
            };
            if (E && E.setAttribute) {
                var setAttrNativ = E.setAttribute;
                E.setAttribute = function (n, v) {
                    if (this instanceof M && String(n).toLowerCase() === "src") {
                        var t = atribut(this, "type") || av(this).tipCerut, x = adresa(v, t);
                        if (x) {
                            puneSursa(this, x, t);
                            return;
                        }
                        scoateSursa(this);
                    }
                    return setAttrNativ.apply(this, arguments);
                };
            }
            if (E && E.removeAttribute) {
                var removeNativ = E.removeAttribute;
                E.removeAttribute = function (n) {
                    if (this instanceof M && String(n).toLowerCase() === "src" && al(this))
                        scoateSursa(this);
                    return removeNativ.apply(this, arguments);
                };
            }
        } catch (x) {
            jurnalPagina("video html5 pe playerul receptorului: nu s-a putut pune (" + (x && x.name) + ")");
            return false;
        }
        /* elementele cu autoplay si sursa scrisa in HTML: filmul porneste singur, ca la un <video> adevarat */
        function autoplayDinHtml() {
            var l = document.querySelectorAll ? document.querySelectorAll("video[autoplay], audio[autoplay]") : [];
            for (var i = 0; i < l.length; i++) {
                if (al(l[i]))
                    continue;
                var h = sursaDinHtml(l[i]);
                if (h)
                    puneSursa(l[i], h.u, h.tip);
            }
        }
        if (typeof document.addEventListener === "function")
            document.addEventListener("DOMContentLoaded", autoplayDinHtml, false);
        hlsJsPePlayer();
        dashJsPePlayer();
        return true;
    }

    /* hls.js PE PLAYERUL RECEPTORULUI (LAN1): multe aplicatii HbbTV (Rubidia: Video Mediterraneo, Video Regione, TeleNord)
     * aleg hls.js pe orice televizor necunoscut si nu mai incearca <video src=.m3u8>; hls.js cere MediaSource, pe care
     * WebKit-ul imaginii nu-l are, deci Hls.isSupported() da false si aplicatia ramane pe rotita. Cand pagina pune
     * window.Hls (biblioteca hls.js) si ea spune ca nu poate reda aici (fara MediaSource), Hls.isSupported() spune da, iar un Hls nou e o punte mica:
     * loadSource + attachMedia pun adresa listei pe <video> (deci pe playerul receptorului, prin videoHtml5), cu
     * evenimentele de baza ale bibliotecii (MEDIA_ATTACHED, MANIFEST_LOADED, MANIFEST_PARSED cu o singura calitate).
     * HBL1 (0.8.0): puntea se pune MEREU, si cand biblioteca spune ca poate reda singura. In navigatorul pornit de
     * enigma2 WebKit are MediaSource cu decodorul imprumutat (HdsDecodorWeb), deci Hls.isSupported() da adevarat, iar
     * hls.js isi reda singur lista: la Lanus (Octagon SF8008, Video Mediterraneo HD, Rubidia) imaginea ingheata dupa 1-2
     * minute si pagina ramane pe rotita; pe playerul receptorului acelasi film a mers 5 minute fara oprire (AS211).
     * Ramane la biblioteca numai un Hls cu filme protejate (config emeEnabled sau drmSystems: EME prin hds-ocdm). */
    /* atributul type de dinaintea puntii, pus inapoi cand puntea lasa elementul (o reclama MP4 pe acelasi <video>) */
    function tipInapoi(m, vechi) {
        if (vechi === null || vechi === undefined)
            m.removeAttribute("type");
        else
            m.setAttribute("type", vechi);
    }

    function hlsJsPePlayer() {
        if (!Object.defineProperty)
            return;
        function punte(Orig) {
            if (typeof Orig !== "function" || Orig.__hdsPunte)
                return Orig;
            var EV = Orig.Events || {};
            function Hls(cfg) {
                /* film protejat: biblioteca, prin EME (drmSystems {} e valoarea din fabrica a bibliotecii: nu conteaza) */
                if (cfg && (cfg.emeEnabled === true || (cfg.drmSystems && typeof cfg.drmSystems === "object" &&
                        Object.keys(cfg.drmSystems).length)))
                    return new Orig(cfg);
                if (!(this instanceof Hls))
                    return new Hls(cfg);
                this.config = cfg || {};
                this.url = "";
                this.media = null;
                this.levels = [];
                this.audioTracks = [];
                this.subtitleTracks = [];
                this.startLevel = -1;
                this.currentLevel = -1;
                this.nextLevel = -1;
                this.loadLevel = -1;
                this.autoLevelEnabled = true;
                this._asc = {};
            }
            var p = Hls.prototype;
            p.on = function (n, f, ctx) {
                if (typeof f === "function")
                    (this._asc[n] = this._asc[n] || []).push({ f: f, s: ctx });
            };
            p.once = function (n, f, ctx) {
                var eu = this;
                function o() { eu.off(n, o); return f.apply(this, arguments); }
                o.original = f;
                this.on(n, o, ctx);
            };
            p.off = function (n, f) {
                var l = this._asc[n];
                if (l)
                    this._asc[n] = f ? l.filter(function (x) { return x.f !== f && x.f.original !== f; }) : [];
            };
            p.removeAllListeners = function (n) {
                if (n)
                    delete this._asc[n];
                else
                    this._asc = {};
            };
            p.listeners = function (n) { return (this._asc[n] || []).map(function (x) { return x.f; }); };
            p.emit = p.trigger = function (n, d) {
                var eu = this;
                (this._asc[n] || []).slice().forEach(function (x) {
                    try {
                        x.f.call(x.s === undefined ? eu : x.s, n, d);
                    } catch (e) {
                        /* ascultatorul paginii: ca la biblioteca, nu opreste celelalte */
                    }
                });
                return true;
            };
            p._pune = function () {
                var eu = this, m = this.media, u = this.url;
                if (!m || !u)
                    return;
                if (this._tipVechi === undefined)
                    this._tipVechi = m.getAttribute("type");
                m.setAttribute("type", "application/vnd.apple.mpegurl");
                m.src = u;
                if (m.src !== u)
                    return;   /* adresa n-a fost luata de playerul receptorului (alta schema): fara evenimentele listei */
                setTimeout(function () {
                    if (eu.media !== m || eu.url !== u)
                        return;
                    var nivel = { url: [u], bitrate: 0, width: 0, height: 0, name: "", attrs: {}, audioCodec: "",
                        videoCodec: "" };
                    eu.levels = [nivel];
                    eu.emit(EV.MANIFEST_LOADED || "hlsManifestLoaded", { url: u, levels: eu.levels, audioTracks: [],
                        subtitles: [] });
                    eu.emit(EV.MANIFEST_PARSED || "hlsManifestParsed", { levels: eu.levels, firstLevel: 0,
                        audioTracks: [], subtitleTracks: [], stats: {}, audio: true, video: true, altAudio: false });
                    if (eu.config.autoStartLoad !== false && m.autoplay)
                        m.play();
                }, 0);
            };
            p.loadSource = function (u) {
                try {
                    u = new URL(String(u), document.baseURI || window.location.href).href;
                } catch (x) {
                    u = String(u);
                }
                this.url = u;
                this.emit(EV.MANIFEST_LOADING || "hlsManifestLoading", { url: u });
                this._pune();
            };
            p.attachMedia = function (m) {
                var eu = this;
                this.media = m;
                this.emit(EV.MEDIA_ATTACHING || "hlsMediaAttaching", { media: m });
                setTimeout(function () {
                    if (eu.media === m)
                        eu.emit(EV.MEDIA_ATTACHED || "hlsMediaAttached", { media: m });
                }, 0);
                this._pune();
            };
            p.detachMedia = function () {
                var m = this.media;
                this.media = null;
                if (m && m.removeAttribute) {
                    m.removeAttribute("src");
                    tipInapoi(m, this._tipVechi);
                }
                this._tipVechi = undefined;
                this.emit(EV.MEDIA_DETACHED || "hlsMediaDetached", {});
            };
            p.destroy = function () {
                this.detachMedia();
                this.emit(EV.DESTROYING || "hlsDestroying", {});
                this._asc = {};
                this.url = "";
            };
            p.startLoad = p.stopLoad = p.recoverMediaError = p.swapAudioCodec = p.removeLevel = function () {};
            Object.keys(Orig).forEach(function (k) {
                try {
                    Hls[k] = Orig[k];
                } catch (x) {
                    /* nimic */
                }
            });
            ["Events", "ErrorTypes", "ErrorDetails", "DefaultConfig", "version"].forEach(function (k) {
                try {
                    if (Orig[k] !== undefined)
                        Hls[k] = Orig[k];
                } catch (x) {
                    /* nimic */
                }
            });
            Hls.isSupported = function () { return true; };
            Hls.isMSESupported = function () { return true; };
            Hls.__hdsPunte = true;
            return Hls;
        }
        var val;
        try {
            Object.defineProperty(window, "Hls", { configurable: true, enumerable: true,
                get: function () { return val; },
                set: function (v) { val = punte(v); } });
        } catch (x) {
            /* window.Hls deja nedefinibil: biblioteca ramane cum e */
        }
    }

    /* dash.js PE PLAYERUL RECEPTORULUI (LAN1): aplicatii ca wedo tv (13E, hbbtv.amtecco.com) pornesc fluxul DASH numai
     * prin dash.js, care cere MediaSource cu decodor; fara el apare "DASH error" si rotita. Cand pagina pune window.dashjs
     * si MSE nu poate reda H.264, dashjs.MediaPlayer().create() da o punte mica: initialize / attachView / attachSource
     * pun adresa pe <video> cu tipul application/dash+xml (deci pe playerul receptorului, prin videoHtml5), play / pause /
     * seek / time / duration merg pe acel <video>, iar evenimentele lui sunt date mai departe cu numele din
     * dashjs.MediaPlayer.events. HBL1 (0.8.0): puntea se pune MEREU, si cand MSE poate reda (in navigatorul pornit de
     * enigma2 MSE are decodorul imprumutat, drumul pe care hls.js ingheata la Lanus, vezi hlsJsPePlayer). Un film
     * protejat (setProtectionData cu date: EME prin hds-ocdm) trece la playerul adevarat al bibliotecii, cu acelasi
     * <video>, aceeasi adresa si aceiasi ascultatori. */
    function dashJsPePlayer() {
        if (!Object.defineProperty)
            return;
        var VIDEO_EV = { play: "PLAYBACK_STARTED", playing: "PLAYBACK_PLAYING", pause: "PLAYBACK_PAUSED",
            timeupdate: "PLAYBACK_TIME_UPDATED", ended: "PLAYBACK_ENDED", waiting: "PLAYBACK_WAITING",
            seeking: "PLAYBACK_SEEKING", seeked: "PLAYBACK_SEEKED", canplay: "CAN_PLAY",
            loadedmetadata: "PLAYBACK_METADATA_LOADED", error: "PLAYBACK_ERROR" };
        function punteMp(OrigMp) {
            var EV = OrigMp.events || {};
            function nume(k) { return EV[k] || k.toLowerCase(); }
            function Player() {
                this._asc = {};
                this._view = null;
                this._url = "";
                this._autoPlay = true;
                this._setari = { debug: {}, streaming: { abr: { autoSwitchBitrate: {}, initialBitrate: {}, maxBitrate: {},
                    minBitrate: {} }, buffer: {}, delay: {}, liveCatchup: {}, text: {}, retryAttempts: {},
                    retryIntervals: {} } };
                this._ascVideo = null;
            }
            var p = Player.prototype;
            p.on = function (n, f, scope) {
                if (typeof f === "function")
                    (this._asc[n] = this._asc[n] || []).push({ f: f, s: scope });
                if (this._real)
                    this._real.on(n, f, scope);
            };
            p.off = function (n, f) {
                var l = this._asc[n];
                if (l)
                    this._asc[n] = f ? l.filter(function (x) { return x.f !== f; }) : [];
                if (this._real)
                    this._real.off(n, f);
            };
            /* filmul protejat: playerul adevarat al bibliotecii ia <video>, adresa si ascultatorii (o singura data) */
            p._laBiblioteca = function (date) {
                var eu = this, v = this._view, u = this._url;
                if (this._real) {
                    this._real.setProtectionData(date);
                    return;
                }
                var r;
                try {
                    r = OrigMp().create();
                } catch (x) {
                    return;   /* biblioteca nu poate crea playerul: ramane puntea */
                }
                this.attachSource("");
                this._leagaVideo(null);
                this._real = r;
                Object.keys(this._asc).forEach(function (n) {
                    eu._asc[n].forEach(function (x) { r.on(n, x.f, x.s); });
                });
                r.setProtectionData(date);
                r.initialize(v || undefined, u || undefined, this._autoPlay);
                jurnalPagina("dash.js: film protejat, pe biblioteca (EME)");
            };
            p._emite = function (k, d) {
                var n = nume(k), ev = d || {};
                ev.type = n;
                (this._asc[n] || []).slice().forEach(function (x) {
                    try {
                        x.f.call(x.s, ev);
                    } catch (e) {
                        /* ascultatorul paginii: nu opreste celelalte */
                    }
                });
            };
            p._leagaVideo = function (v) {
                var eu = this;
                if (this._view && this._ascVideo)
                    Object.keys(this._ascVideo).forEach(function (n) {
                        eu._view.removeEventListener(n, eu._ascVideo[n]);
                    });
                if (this._view && this._view !== v && this._tipVechi !== undefined) {
                    tipInapoi(this._view, this._tipVechi);
                    this._tipVechi = undefined;
                }
                this._view = v || null;
                this._ascVideo = {};
                if (!v)
                    return;
                Object.keys(VIDEO_EV).forEach(function (n) {
                    var f = function () {
                        var d = { time: v.currentTime };
                        if (n === "error")
                            d.error = { code: 0, message: "playerul receptorului" };
                        eu._emite(VIDEO_EV[n], d);
                    };
                    eu._ascVideo[n] = f;
                    v.addEventListener(n, f);
                });
            };
            p._pune = function () {
                var eu = this, v = this._view, u = this._url;
                if (!v || !u)
                    return;
                if (this._tipVechi === undefined)
                    this._tipVechi = v.getAttribute("type");
                v.setAttribute("type", "application/dash+xml");
                v.src = u;
                if (v.src !== u)
                    return;   /* adresa n-a fost luata de playerul receptorului: fara evenimentele fluxului */
                setTimeout(function () {
                    if (eu._view !== v || eu._url !== u)
                        return;
                    eu._emite("MANIFEST_LOADED", { data: {} });
                    eu._emite("STREAM_INITIALIZED", { streamInfo: {} });
                    if (eu._autoPlay)
                        v.play();
                }, 0);
            };
            p.initialize = function (v, u, autoPlay) {
                if (autoPlay !== undefined)
                    this._autoPlay = !!autoPlay;
                if (v)
                    this._leagaVideo(v);
                if (u)
                    this.attachSource(u);
            };
            p.attachView = function (v) {
                if (v === this._view)
                    return;
                this._leagaVideo(v);
                this._pune();
            };
            p.attachSource = function (u) {
                var v = this._view;
                if (!u) {
                    this._url = "";
                    if (v && v.removeAttribute) {
                        v.removeAttribute("src");
                        if (this._tipVechi !== undefined)
                            tipInapoi(v, this._tipVechi);
                    }
                    this._tipVechi = undefined;
                    return;
                }
                try {
                    u = new URL(String(u), document.baseURI || window.location.href).href;
                } catch (x) {
                    u = String(u);
                }
                this._url = u;
                this._pune();
            };
            p.setAutoPlay = function (b) { this._autoPlay = !!b; };
            p.getAutoPlay = function () { return this._autoPlay; };
            p.play = function () { if (this._view) this._view.play(); };
            p.pause = function () { if (this._view) this._view.pause(); };
            p.isPaused = function () { return this._view ? this._view.paused : true; };
            p.seek = function (t) { if (this._view) this._view.currentTime = t; };
            p.time = function () { return this._view ? this._view.currentTime : 0; };
            p.duration = function () { return this._view ? this._view.duration : NaN; };
            p.isReady = function () { return !!(this._view && this._url); };
            p.isDynamic = function () { return !(this._view && isFinite(this._view.duration)); };
            p.getVideoElement = function () { return this._view; };
            p.setMute = function (b) { if (this._view) this._view.muted = !!b; };
            p.isMuted = function () { return !!(this._view && this._view.muted); };
            p.setVolume = function (x) { if (this._view) this._view.volume = x; };
            p.getVolume = function () { return this._view ? this._view.volume : 1; };
            p.updateSettings = function () {};
            p.getSettings = function () { return this._setari; };
            p.resetSettings = function () {};
            p.getBitrateInfoListFor = function () { return []; };
            p.getQualityFor = function () { return 0; };
            p.setQualityFor = function () {};
            p.getTracksFor = function () { return []; };
            p.getVersion = function () { return "punte"; };
            p.getSource = function () { return this._url; };
            p.getDebug = function () {
                var nimic = function () {};
                return { setLogToBrowserConsole: nimic, setLogLevel: nimic, setCalleeNameVisible: nimic,
                    getLogger: function () { return { debug: nimic, info: nimic, warn: nimic, error: nimic,
                        fatal: nimic }; } };
            };
            p.getDashMetrics = function () { return {}; };
            p.getActiveStream = function () { return null; };
            p.setInitialMediaSettingsFor = p.setTextDefaultEnabled = p.enableText = p.attachTTMLRenderingDiv =
                p.setCurrentTrack = p.setTextTrack = function () {};
            p.extend = p.setXHRWithCredentialsForType = function () {};
            p.setProtectionData = function (date) {
                if (date && typeof date === "object" && Object.keys(date).length)
                    this._laBiblioteca(date);
            };
            p.reset = p.destroy = function () {
                this.attachSource("");
                this._leagaVideo(null);
            };
            /* dupa trecerea la biblioteca (_laBiblioteca) orice cerere a paginii merge la playerul adevarat */
            Object.keys(p).forEach(function (k) {
                var f = p[k];
                if (typeof f !== "function" || k.charAt(0) === "_" || k === "on" || k === "off" || k === "setProtectionData")
                    return;
                p[k] = function () {
                    var r = this._real;
                    if (r && typeof r[k] === "function")
                        return r[k].apply(r, arguments);
                    return f.apply(this, arguments);
                };
            });
            function MediaPlayer() {
                return { create: function () { return new Player(); } };
            }
            Object.keys(OrigMp).forEach(function (k) {
                try {
                    MediaPlayer[k] = OrigMp[k];
                } catch (x) {
                    /* nimic */
                }
            });
            MediaPlayer.events = EV;
            MediaPlayer.__hdsPunte = true;
            return MediaPlayer;
        }
        var val;
        try {
            Object.defineProperty(window, "dashjs", { configurable: true, enumerable: true,
                get: function () {
                    if (val && typeof val.MediaPlayer === "function" && !val.MediaPlayer.__hdsPunte)
                        val.MediaPlayer = punteMp(val.MediaPlayer);
                    return val;
                },
                set: function (v) { val = v; } });
        } catch (x) {
            /* window.dashjs deja nedefinibil: biblioteca ramane cum e */
        }
    }

    /* ADN PLAY (HBL1, 0.8.0; AS218, Lanus): aplicatia (gazdele selftv.video, index-legacy-*.js) alege playerul dupa
     * agentul navigatorului (/HbbTV\/\d.(\d)\.\d/): la noi HbbTV/1.2.1 -> modul "1.5", obiectul A/V. In acest mod playerul
     * aplicatiei primeste numai onPlaying/onPause/onWaiting/onEnded, nu si onPlay (singurul care pune playing=true) sau
     * onTimeUpdate, iar bara lui (div cu fundalul maschera3.png) are opacity = playing && !seeking ? 0 : 1: ramane mereu
     * peste film, cu 00:00. Defectul e al aplicatiei (la fel pe orice televizor HbbTV 1.5). Aici bara se ascunde cat
     * obiectul A/V reda (playState 1) si se arata la pauza, la asteptare, ADN_ARATA_MS la pornirea filmului si dupa
     * STANGA / DREAPTA / OK; timpul si bara de progres se scriu din playPosition / playTime. Probat la Lanus pe Casa
     * Sanremo Tv (bara ascunsa la +16 s, DREAPTA -> bara cu timpul adevarat, iar ascunsa dupa 5 s). */
    var ADN_ARATA_MS = 5000, ADN_PAS_MS = 500;

    function adaptareAdnPlay() {
        var loc = window.location;
        if (!loc || !/(^|\.)selftv\.video$/i.test(loc.hostname || "") || typeof window.setInterval !== "function")
            return false;
        var arataPanaLa = 0, ultimaStare = -2, spus = false;
        function doua(n) { return (n < 10 ? "0" : "") + n; }
        function ceas(s) {
            s = Math.max(0, Math.floor(s));
            var o = Math.floor(s / 3600), m = Math.floor(s / 60) % 60, x = s % 60;
            return o > 0 ? doua(o) + ":" + doua(m) + ":" + doua(x) : doua(m) + ":" + doua(x);
        }
        function bara() {
            var d = document.getElementsByTagName("div");
            for (var i = 0; i < d.length; i++) {
                var f = d[i].style && d[i].style.backgroundImage;
                if (f && f.indexOf("maschera3.png") >= 0)
                    return d[i];
            }
            return null;
        }
        function playerul() {
            var o = document.getElementsByTagName("object");
            for (var i = 0; i < o.length; i++) {
                var t = (o[i].getAttribute("type") || "").toLowerCase();
                if (t && t !== "video/broadcast" && /dash|mp4|mpegurl|^video\/|^audio\//.test(t))
                    return o[i];
            }
            return null;
        }
        function scrieTimpul(m, p) {
            var poz = p.playPosition, lung = p.playTime;
            if (typeof poz !== "number" || !(poz >= 0))
                return;
            var jos = m.children[1];
            if (!jos || jos.children.length < 3)
                return;
            jos.children[1].textContent = ceas(poz / 1000);
            if (typeof lung === "number" && lung > 0 && isFinite(lung)) {
                var plin = jos.children[2].firstChild;
                if (plin && plin.style)
                    plin.style.width = Math.min(100, poz / lung * 100) + "%";
                if (jos.children[3])
                    jos.children[3].textContent = ceas((lung - poz) / 1000);
            }
        }
        function pas() {
            try {
                var m = bara();
                if (!m)
                    return;
                var p = playerul();
                var st = p ? p.playState : -1;
                if (!spus) {
                    spus = true;
                    jurnalPagina("adaptare ADN PLAY: bara playerului ascunsa cat filmul reda (player " +
                        (p ? "object " + p.getAttribute("type") : "fara obiect A/V") + ")");
                }
                if (st !== ultimaStare) {
                    if (st === 1 && ultimaStare !== 2)
                        arataPanaLa = Date.now() + ADN_ARATA_MS;
                    ultimaStare = st;
                }
                var ascunde = st === 1 && Date.now() > arataPanaLa;
                m.style.setProperty("opacity", ascunde ? "0" : "1", "important");
                if (p && (st === 1 || st === 2))
                    scrieTimpul(m, p);
            } catch (x) {
                /* nimic: bara ramane cum o lasa aplicatia */
            }
        }
        window.addEventListener("keydown", function (e) {
            var k = e.keyCode;
            if (k === 37 || k === 39 || k === 13)
                arataPanaLa = Date.now() + ADN_ARATA_MS;
        }, true);
        window.setInterval(pas, ADN_PAS_MS);
        return true;
    }

    /* PAGINA XHTML CU GRESELI DE XML (HBL1, 0.8.0; AS220, Lanus, CLUB TV, platforma Premio hbbtv.premio.link): o
     * aplicatie trimisa ca application/vnd.hbbtv.xhtml+xml se citeste ca XML strict; la prima greseala (aici <script async>,
     * atribut fara valoare) WebKit opreste citirea, pune caseta "This page contains the following errors" si pagina ramane
     * fara restul scripturilor si fara <body onload>, deci aplicatia nu cheama niciodata show(). Televizoarele citesc
     * astfel de pagini ingaduitor. Aici, numai cand documentul are <parsererror>: pagina se cere iar (aceeasi adresa), se
     * citeste ca text/html, caseta se scoate, ce lipseste din <head> si <body> se adauga (fara scripturile si foile de stil
     * care exista deja), scripturile ruleaza in ordine, unul dupa altul, apoi onload-ul din <body> si evenimentul load.
     * Limite stiute: documentul ramane XML (createElement, innerHTML, document.write ale unui document XML), load vine a
     * doua oara pe window, scripturile async/defer ruleaza la rand. Probat la Lanus pe CLUB TV (aplicatia se arata). Reparatia
     * curata ar fi in hds-navigator.c (documentele HbbTV XHTML citite ingaduitor); pana atunci, aici. */
    var XML_ASTEPTARI_MS = [4000, 10000], XML_SCRIPT_MS = 8000;

    function xmlIngaduitor() {
        var gata = false;
        if (typeof document.addEventListener !== "function" || typeof XMLHttpRequest !== "function")
            return false;
        function areGreseala() {
            try {
                return document.getElementsByTagName("parsererror").length > 0;
            } catch (e) {
                return false;
            }
        }
        function absolut(u) {
            try {
                var a = document.createElementNS(NS_XHTML, "a");
                a.href = u;
                return a.href;
            } catch (e) {
                return u;
            }
        }
        function nou(el) {
            var n = document.createElementNS(NS_XHTML, el.localName || el.nodeName.toLowerCase());
            for (var i = 0; i < el.attributes.length; i++) {
                var at = el.attributes[i];
                try {
                    n.setAttribute(at.name, at.value);
                } catch (e) {
                    /* atribut cu nume nepermis in XML: ramane afara */
                }
            }
            return n;
        }
        /* copie adanca, cu elemente XHTML (scripturile se pun separat, ca sa ruleze) */
        function copie(el, scripturi) {
            if (el.nodeType === 3)
                return document.createTextNode(el.nodeValue);
            if (el.nodeType !== 1)
                return null;
            if ((el.localName || "").toLowerCase() === "script") {
                scripturi.push(el);
                return null;
            }
            var n = nou(el);
            for (var c = el.firstChild; c; c = c.nextSibling) {
                var k = copie(c, scripturi);
                if (k)
                    n.appendChild(k);
            }
            return n;
        }
        function repara() {
            if (gata || !areGreseala())
                return;
            gata = true;
            var x = new XMLHttpRequest();
            x.open("GET", location.href, true);
            x.onload = function () {
                try {
                    refa(x.responseText || "");
                } catch (e) {
                    jurnalPagina("pagina XML cu greseli: refacerea a cazut (" + (e && e.name) + ")");
                }
            };
            x.onerror = function () { jurnalPagina("pagina XML cu greseli: cererea paginii a cazut"); };
            x.send();
        }
        function refa(text) {
            var d = new DOMParser().parseFromString(text, "text/html");
            if (!d || !d.documentElement)
                return;
            var pe = document.getElementsByTagName("parsererror");
            while (pe.length)
                pe[0].parentNode.removeChild(pe[0]);
            var rad = document.documentElement;
            var head = document.getElementsByTagName("head")[0];
            if (!head) {
                head = document.createElementNS(NS_XHTML, "head");
                rad.insertBefore(head, rad.firstChild);
            }
            var body = document.body || document.getElementsByTagName("body")[0];
            if (!body) {
                body = document.createElementNS(NS_XHTML, "body");
                rad.appendChild(body);
            }
            /* ce exista deja: scripturile (dupa adresa sau dupa text) si foile de stil */
            var aveam = {}, i;
            var vechi = document.getElementsByTagName("script");
            for (i = 0; i < vechi.length; i++) {
                var s = vechi[i].getAttribute("src");
                aveam[s ? "s:" + absolut(s) : "t:" + (vechi[i].textContent || "").replace(/\s+/g, "")] = 1;
            }
            var legaturi = document.getElementsByTagName("link");
            for (i = 0; i < legaturi.length; i++)
                aveam["l:" + absolut(legaturi[i].getAttribute("href") || "")] = 1;
            var scripturi = [];
            var dh = d.head ? d.head.childNodes : [];
            for (i = 0; i < dh.length; i++) {
                var c = dh[i];
                if (c.nodeType !== 1)
                    continue;
                var nume = c.localName.toLowerCase();
                if (nume === "script") {
                    scripturi.push(c);
                    continue;
                }
                if ((nume === "link" && aveam["l:" + absolut(c.getAttribute("href") || "")]) || nume === "title" ||
                        nume === "meta")
                    continue;
                var k = copie(c, scripturi);
                if (k)
                    head.appendChild(k);
            }
            var onload = null;
            if (d.body) {
                for (i = 0; i < d.body.attributes.length; i++) {
                    var at = d.body.attributes[i];
                    if (at.name.toLowerCase() === "onload")
                        onload = at.value;
                    else if (!body.hasAttribute(at.name)) {
                        try {
                            body.setAttribute(at.name, at.value);
                        } catch (e) {
                            /* nimic */
                        }
                    }
                }
                var db = d.body.childNodes;
                for (i = 0; i < db.length; i++) {
                    var kb = copie(db[i], scripturi);
                    if (kb)
                        body.appendChild(kb);
                }
            }
            var deRulat = [];
            for (i = 0; i < scripturi.length; i++) {
                var sc = scripturi[i], src = sc.getAttribute("src");
                var cheie = src ? "s:" + absolut(src) : "t:" + (sc.textContent || "").replace(/\s+/g, "");
                if (aveam[cheie])
                    continue;
                aveam[cheie] = 1;
                deRulat.push(sc);
            }
            jurnalPagina("pagina XML cu greseli citita iar ca HTML: " + deRulat.length + " scripturi adaugate, onload " +
                (onload ? "da" : "nu"));
            var pas = 0;
            function urmatorul() {
                if (pas >= deRulat.length) {
                    incheie();
                    return;
                }
                var v = deRulat[pas++], n = nou(v), sursa = v.getAttribute("src");
                if (sursa) {
                    n.removeAttribute("async");
                    n.removeAttribute("defer");
                    var dus = false;
                    var mai = function () {
                        if (!dus) {
                            dus = true;
                            urmatorul();
                        }
                    };
                    n.onload = mai;
                    n.onerror = mai;
                    setTimeout(mai, XML_SCRIPT_MS);
                    head.appendChild(n);
                } else {
                    n.textContent = v.textContent;
                    try {
                        head.appendChild(n);
                    } catch (e) {
                        /* scriptul paginii a cazut: urmatorul */
                    }
                    urmatorul();
                }
            }
            function incheie() {
                if (onload) {
                    try {
                        (new Function(onload)).call(window);
                    } catch (e) {
                        /* onload-ul paginii a cazut */
                    }
                }
                try {
                    var ev = document.createEvent("Event");
                    ev.initEvent("load", false, false);
                    if (onload)
                        window.onload = null;
                    window.dispatchEvent(ev);
                } catch (e) {
                    /* nimic */
                }
            }
            urmatorul();
        }
        document.addEventListener("DOMContentLoaded", repara, false);
        window.addEventListener("load", repara, false);
        XML_ASTEPTARI_MS.forEach(function (ms) { setTimeout(repara, ms); });
        return true;
    }

    /* AS225 (26.11.2026): canalele virtuale TVP de pe DVB-T (TVP ABC 2, TVP Historia 2, TVP Kultura 2: pagina
     * hbb-prod.tvp.pl/apps/manager/virtual-channel?code_channel=...). Din Polonia currentProgramAsLive da intai
     * application/dash+xml, apoi application/x-mpegurl; pagina alege primul tip cunoscut (DASH), opreste canalul si
     * ramane la "Trwa wczytywanie..." fara sa porneasca filmul (rafejo, Vu+ Uno 4K SE). Din Romania vine numai HLS si
     * filmul porneste. Aici HLS trece inaintea DASH in raspunsul currentProgramAsLive (JSON.parse, numai pe paginile
     * aplicatiei TVP manager); DASH ramane in lista, dupa el. Un rand in jurnalul paginii, o data. */
    function adaptareTvpFormate() {
        var loc = window.location;
        if (!loc || !/(^|\.)tvp\.pl$/.test(loc.hostname || "") || !/^\/apps\/manager\//.test(loc.pathname || ""))
            return false;
        var p0 = JSON.parse, scris = false;
        function hls(f) {
            var t = String(f && f.mime_type || "").toLowerCase();
            return t === "application/x-mpegurl" || t === "application/vnd.apple.mpegurl";
        }
        try {
            JSON.parse = function () {
                var r = p0.apply(this, arguments);
                try {
                    var c = r && r.data && r.data.currentProgramAsLive;
                    var l = c && c.video && c.video.formats;
                    if (l && l.length > 1 && !hls(l[0]) && l.some(hls)) {
                        var a = l.filter(hls), b = l.filter(function (f) { return !hls(f); });
                        c.video.formats = a.concat(b);
                        if (!scris) {
                            scris = true;
                            jurnalPagina("adaptare TVP: canal virtual, HLS pus inaintea " + (l[0] && l[0].mime_type));
                        }
                    }
                } catch (x) {
                    /* alt raspuns: neschimbat */
                }
                return r;
            };
        } catch (x) {
            return false;
        }
        return true;
    }

    Object.defineProperty(window, "__hdsHbbtvPrimeste", { value: primeste, writable: false, configurable: false,
        enumerable: false });
    xmlIngaduitor();   /* intai: in pagina cu greseli de XML o cadere de mai jos nu trebuie sa o opreasca */
    jurnalFilme();
    videoHtml5();
    adaptareTvpHub();
    adaptareTvpStare();
    adaptareTvpManager();
    adaptareTvpFilm();
    adaptareTvpFormate();
    adaptareAdnPlay();
    animatiiPeProcesor();
    puneCaruselul();
    tradSetari();
})();

/*
 * WEBASSEMBLY IN JAVASCRIPT (WAS, 0.7.5; HbbTV 2.0.5, ETSI TS 102 796 V1.8.1 cere WebAssembly): WebKit 2.54 pe receptoarele ARMv7 (32 de biti)
 * nu are WebAssembly: in amonte a fost scos pe ARMv7 in ianuarie 2026 (306366@main, „[ARMV7] Remove WebAssembly”), iar JIT-ul
 * ARMv7 in august 2026 (318389@main). Aici, numai cand pagina nu are WebAssembly (typeof window.WebAssembly === "undefined"),
 * window.WebAssembly devine polyfill-ul de mai jos: fiecare functie a modulului se traduce intr-o functie JavaScript
 * (new Function), deci merge si fara JIT, dar mai incet decat un WebAssembly nativ. Pe receptoarele cu WebAssembly
 * (aarch64, PC) blocul nu face nimic.
 * Ce stie: WebAssembly 1.0 (MVP), bulk memory, sign-extension, nontrapping float-to-int, multi-value, reference types,
 * multi-memory, extended-const, tail call, i64 ca BigInt; Module, Instance, Memory, Table, Global, compile(Streaming),
 * instantiate(Streaming), validate. Ce NU stie: SIMD, GC, validarea completa, opririle („trap”) la impartirea cu 0 si la
 * citirea in afara memoriei, tiparele de biti ale NaN. LinkError si RuntimeError le adaugam noi (glue-ul Emscripten face
 * new WebAssembly.RuntimeError in abort()). Pagini cu Content-Security-Policy fara 'unsafe-eval': polyfill-ul nu poate
 * traduce (new Function e oprit; polywasm il cheama chiar la pornire), deci acolo WebAssembly ramane lipsa, ca inainte
 * (typeof === "undefined"), iar aplicatia isi ia drumul fara WebAssembly (probat pe PC: altfel chiar typeof WebAssembly ar
 * arunca EvalError). Numai in cadrul de sus (acolo pune lansatorul stratul); cadrele interioare si Web Worker-ele raman
 * fara WebAssembly.
 * Mod: lenes (lenes = polywasm se evalueaza abia la prima atingere a lui window.WebAssembly; direct = indata).
 *
 * Codul dintre „polywasm inceput” si „polywasm sfarsit” e polywasm 0.2.0, neschimbat (afara de exportul ES de la sfarsit,
 * inlocuit cu „return wasmAPI”): https://github.com/evanw/polywasm (commit c2b3a7430e29f5cecfd2001cfbd234e4c5dd154e),
 * pachetul npm polywasm 0.2.0 (index.js, sha256 b52d3e02376f2da1317e7652c584ea6c7cb6dc09cc8238bf7f216bc9ff5021c0), luat in
 * noiembrie 2026. Licenta lui, MIT (compatibila cu GPL-2.0), cu nota ceruta:
 *
 * Copyright (c) 2024 Evan Wallace
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in all
 * copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 */
(function () {
    "use strict";
    if (typeof window === "undefined" || typeof window.WebAssembly !== "undefined")
        return;

    function polywasm() {
        /* ---------------------------------------------------------------- polywasm inceput */
        // src/library.ts
        var buffer = new ArrayBuffer(8);
        var f32 = new Float32Array(buffer);
        var f64 = new Float64Array(buffer);
        var i32 = new Int32Array(buffer);
        var i64 = new BigInt64Array(buffer);
        var u64 = new BigUint64Array(buffer);
        var exportedFuncs = /* @__PURE__ */ new WeakMap();
        var emptyArray = [];
        var Trampoline = class {
        };
        var library = {
          N(x, y) {
            return (x < 0 || x === 0 && Object.is(x, -0)) !== (y < 0 || y === 0 && Object.is(y, -0)) ? -x : x;
          },
          p(x) {
            u64[0] = x;
            return i64[0];
          },
          O(x) {
            f32[0] = x;
            return i32[0];
          },
          P(x) {
            i32[0] = x;
            return f32[0];
          },
          Q(x) {
            f64[0] = x;
            return u64[0];
          },
          R(x) {
            u64[0] = x;
            return f64[0];
          },
          S(x, y) {
            return x << y | x >>> 32 - y;
          },
          T(x, y) {
            return x >>> y | x << 32 - y;
          },
          U(x, y) {
            return (x << y | x >> 64n - y) & 0xFFFFFFFFFFFFFFFFn;
          },
          V(x, y) {
            return (x >> y | x << 64n - y) & 0xFFFFFFFFFFFFFFFFn;
          },
          W(x) {
            return x ? Math.clz32(x & -x) ^ 31 : 32;
          },
          X(x) {
            let count = 0;
            while (x) {
              count++;
              x &= x - 1;
            }
            return count;
          },
          Y(x) {
            let count = Math.clz32(Number(x >> 32n & 0xFFFFFFFFn));
            if (count === 32) count += Math.clz32(Number(x & 0xFFFFFFFFn));
            return BigInt(count);
          },
          Z(x) {
            let y = Number(x & 0xFFFFFFFFn);
            if (y) return BigInt(Math.clz32(y & -y) ^ 31);
            y = Number(x >> 32n & 0xFFFFFFFFn);
            return y ? BigInt(32 + Math.clz32(y & -y) ^ 31) : 64n;
          },
          _(x) {
            let count = 0n;
            while (x) {
              count++;
              x &= x - 1n;
            }
            return count;
          },
          z(x) {
            x = Math.trunc(x);
            return x >= 2147483647 ? 2147483647 : x <= -2147483648 ? -2147483648 : x | 0;
          },
          A(x) {
            x = Math.trunc(x);
            return x >= 4294967295 ? -1 : x <= 0 ? 0 : x | 0;
          },
          B(x) {
            x = Math.trunc(x);
            return x >= 9223372036854776e3 ? 0x7FFFFFFFFFFFFFFFn : x <= -9223372036854776e3 ? 0x8000000000000000n : x === x ? BigInt(x) & 0xFFFFFFFFFFFFFFFFn : 0n;
          },
          C(x) {
            x = Math.trunc(x);
            return x >= 18446744073709552e3 ? 0xFFFFFFFFFFFFFFFFn : !(x > 0) ? 0n : (
              // NaN must become 0
              BigInt(x)
            );
          },
          $(x) {
            return x & 0x80n ? x | 0xFFFFFFFFFFFFFF00n : x & 0xFFn;
          },
          aa(x) {
            return x & 0x8000n ? x | 0xFFFFFFFFFFFF0000n : x & 0xFFFFn;
          },
          ba(x) {
            return x & 0x80000000n ? x | 0xFFFFFFFF00000000n : x & 0xFFFFFFFFn;
          },
          D(source, destination, target, start, count) {
            if (source === destination) {
              destination.copyWithin(target, start, start + count);
            } else {
              destination.set(source.subarray(start, start + count), target);
            }
          },
          E(x, y, d, s, n) {
            d >>>= 0;
            s >>>= 0;
            n >>>= 0;
            if (s + n > y.length || d + n > x.length) throw RangeError();
            if (d <= s) {
              for (let j = 0; j < n; j++) x[d + j] = y[s + j];
            } else {
              for (let j = n - 1; j >= 0; j--) x[d + j] = y[s + j];
            }
          },
          F(x, val, n) {
            const sz = x.length;
            n >>>= 0;
            if (sz + n > x.ca) return -1;
            for (let i = 0; i < n; i++) x.push(val);
            return sz;
          },
          da(x, i, val, n) {
            i >>>= 0;
            n >>>= 0;
            if (i + n > x.length) throw RangeError();
            for (let j = 0; j < n; j++) x[i + j] = val;
          },
          G(context, fn, args) {
            if (context instanceof Trampoline) {
              context.q = fn;
              context.ea = args;
              return emptyArray;
            }
            context = new Trampoline();
            let result;
            while (result = fn.apply(context, args), context.q) {
              fn = context.q;
              args = context.ea;
              context.q = null;
            }
            return result;
          },
          r(fn) {
            if (fn === null) return fn;
            const obj = exportedFuncs.get(fn);
            if (obj) return obj;
            throw Error("Unexpected foreign function object");
          },
          s(obj) {
            if (obj === null) return null;
            if (!obj.t) {
              const [argTypes, returnTypes] = obj.fa;
              const argNames = [];
              const argExprs = [];
              for (let i = 0; i < argTypes.length; i++) {
                argNames.push("a" + i);
                argExprs.push(castToWASM("a" + i, argTypes[i]));
              }
              let result = `f.${/* @__KEY__ */ "u"}(${argExprs})`;
              if (returnTypes.length === 1) {
                result = "return " + castToJS(result, returnTypes[0]);
              } else if (returnTypes.length > 1) {
                result = `let r=${result};`;
                for (let i = 0; i < returnTypes.length; i++) result += `r[${i}]=${castToJS(`r[${i}]`, returnTypes[i])};`;
                result += "return r";
              }
              exportedFuncs.set(obj.t = new Function("f", "l", `return(${argNames})=>{${result}}`)(obj, this), obj);
            }
            return obj.t;
          }
        };

        // src/optimize.ts
        var isPayload = (operand) => {
          return typeof operand === "string" ? operand >= "P" && operand <= "S" : operand ? typeof operand[0] !== "string" && operand[0] < 0 : false;
        };
        var rules = [
          // load of (addr + constant) => merge constant into load's offset
          {
            a: [
              [
                "$",
                40 /* i32_load */,
                41 /* i64_load */,
                42 /* f32_load */,
                43 /* f64_load */,
                44 /* i32_load8_s */,
                45 /* i32_load8_u */,
                46 /* i32_load16_s */,
                47 /* i32_load16_u */,
                48 /* i64_load8_s */,
                49 /* i64_load8_u */,
                50 /* i64_load16_s */,
                51 /* i64_load16_u */,
                52 /* i64_load32_s */,
                53 /* i64_load32_u */
              ],
              [106 /* i32_add */, "x", [65 /* i32_const */, "Q"]],
              "P",
              "R"
            ],
            b: ["$", "x", [-2 /* i32_add */, "P", "Q"], "R"]
          },
          // store of (addr + constant) => merge constant into store's offset
          {
            a: [
              [
                "$",
                54 /* i32_store */,
                55 /* i64_store */,
                56 /* f32_store */,
                57 /* f64_store */,
                58 /* i32_store8 */,
                59 /* i32_store16 */,
                60 /* i64_store8 */,
                61 /* i64_store16 */,
                62 /* i64_store32 */
              ],
              [106 /* i32_add */, "x", [65 /* i32_const */, "Q"]],
              "y",
              "P",
              "R"
            ],
            b: ["$", "x", "y", [-2 /* i32_add */, "P", "Q"], "R"]
          },
          // i64_store8 => i32_store8
          {
            a: [60 /* i64_store8 */, "x", "y", "P", "R"],
            f: {
              "y": [
                {
                  a: [66 /* i64_const */, "Q"],
                  b: [58 /* i32_store8 */, "x", [65 /* i32_const */, [-1 /* i64_to_i32 */, "Q"]], "P", "R"]
                },
                {
                  a: [
                    [
                      "$",
                      48 /* i64_load8_s */,
                      49 /* i64_load8_u */,
                      50 /* i64_load16_s */,
                      51 /* i64_load16_u */,
                      52 /* i64_load32_s */,
                      53 /* i64_load32_u */,
                      41 /* i64_load */
                    ],
                    "z",
                    "Q",
                    "S"
                  ],
                  b: [58 /* i32_store8 */, "x", [45 /* i32_load8_u */, "z", "Q", "S"], "P", "R"]
                },
                {
                  a: [["@", 172 /* i64_extend_i32_s */, 173 /* i64_extend_i32_u */], "z"],
                  b: [58 /* i32_store8 */, "x", "z", "P", "R"]
                }
              ]
            }
          },
          // i64_store16 => i32_store16
          {
            a: [61 /* i64_store16 */, "x", "y", "P", "R"],
            f: {
              "y": [
                {
                  a: [66 /* i64_const */, "Q"],
                  b: [59 /* i32_store16 */, "x", [65 /* i32_const */, [-1 /* i64_to_i32 */, "Q"]], "P", "R"]
                },
                {
                  a: [48 /* i64_load8_s */, "z", "Q", "S"],
                  b: [59 /* i32_store16 */, "x", [44 /* i32_load8_s */, "z", "Q", "S"], "P", "R"]
                },
                {
                  a: [49 /* i64_load8_u */, "z", "Q", "S"],
                  b: [59 /* i32_store16 */, "x", [45 /* i32_load8_u */, "z", "Q", "S"], "P", "R"]
                },
                {
                  a: [
                    [
                      "$",
                      50 /* i64_load16_s */,
                      51 /* i64_load16_u */,
                      52 /* i64_load32_s */,
                      53 /* i64_load32_u */,
                      41 /* i64_load */
                    ],
                    "z",
                    "Q",
                    "S"
                  ],
                  b: [59 /* i32_store16 */, "x", [47 /* i32_load16_u */, "z", "Q", "S"], "P", "R"]
                },
                {
                  a: [["@", 172 /* i64_extend_i32_s */, 173 /* i64_extend_i32_u */], "z"],
                  b: [59 /* i32_store16 */, "x", "z", "P", "R"]
                }
              ]
            }
          },
          // i64_store32 => i32_store
          {
            a: [62 /* i64_store32 */, "x", "y", "P", "R"],
            f: {
              "y": [
                {
                  a: [66 /* i64_const */, "Q"],
                  b: [54 /* i32_store */, "x", [65 /* i32_const */, [-1 /* i64_to_i32 */, "Q"]], "P", "R"]
                },
                {
                  a: [48 /* i64_load8_s */, "z", "Q", "S"],
                  b: [54 /* i32_store */, "x", [44 /* i32_load8_s */, "z", "Q", "S"], "P", "R"]
                },
                {
                  a: [49 /* i64_load8_u */, "z", "Q", "S"],
                  b: [54 /* i32_store */, "x", [45 /* i32_load8_u */, "z", "Q", "S"], "P", "R"]
                },
                {
                  a: [50 /* i64_load16_s */, "z", "Q", "S"],
                  b: [54 /* i32_store */, "x", [46 /* i32_load16_s */, "z", "Q", "S"], "P", "R"]
                },
                {
                  a: [51 /* i64_load16_u */, "z", "Q", "S"],
                  b: [54 /* i32_store */, "x", [47 /* i32_load16_u */, "z", "Q", "S"], "P", "R"]
                },
                {
                  a: [
                    [
                      "$",
                      52 /* i64_load32_s */,
                      53 /* i64_load32_u */,
                      41 /* i64_load */
                    ],
                    "z",
                    "Q",
                    "S"
                  ],
                  b: [54 /* i32_store */, "x", [40 /* i32_load */, "z", "Q", "S"], "P", "R"]
                },
                {
                  a: [["@", 172 /* i64_extend_i32_s */, 173 /* i64_extend_i32_u */], "z"],
                  b: [54 /* i32_store */, "x", "z", "P", "R"]
                }
              ]
            }
          },
          // i64_eqz => i32_eqz
          {
            a: [80 /* i64_eqz */, "x"],
            f: {
              "x": [
                {
                  a: [["$", 48 /* i64_load8_s */, 49 /* i64_load8_u */], "y", "P", "R"],
                  b: [69 /* i32_eqz */, [45 /* i32_load8_u */, "y", "P", "R"]]
                },
                {
                  a: [["$", 50 /* i64_load16_s */, 51 /* i64_load16_u */], "y", "P", "R"],
                  b: [69 /* i32_eqz */, [47 /* i32_load16_u */, "y", "P", "R"]]
                },
                {
                  a: [["$", 52 /* i64_load32_s */, 53 /* i64_load32_u */], "y", "P", "R"],
                  b: [69 /* i32_eqz */, [40 /* i32_load */, "y", "P", "R"]]
                },
                {
                  a: [["@", 172 /* i64_extend_i32_s */, 173 /* i64_extend_i32_u */], "y"],
                  b: [69 /* i32_eqz */, "y"]
                }
              ]
            }
          },
          // 64-bit equality on unsigned 32-bit load => 32-bit equality
          {
            a: [81 /* i64_eq */, [49 /* i64_load8_u */, "x", "P", "R"], [66 /* i64_const */, "Q"]],
            b: [70 /* i32_eq */, [45 /* i32_load8_u */, "x", "P", "R"], [65 /* i32_const */, [-1 /* i64_to_i32 */, "Q"]]],
            d: ["Q", "<=", 0xFFn]
          },
          {
            a: [82 /* i64_ne */, [49 /* i64_load8_u */, "x", "P", "R"], [66 /* i64_const */, "Q"]],
            b: [71 /* i32_ne */, [45 /* i32_load8_u */, "x", "P", "R"], [65 /* i32_const */, [-1 /* i64_to_i32 */, "Q"]]],
            d: ["Q", "<=", 0xFFn]
          },
          {
            a: [81 /* i64_eq */, [51 /* i64_load16_u */, "x", "P", "R"], [66 /* i64_const */, "Q"]],
            b: [70 /* i32_eq */, [47 /* i32_load16_u */, "x", "P", "R"], [65 /* i32_const */, [-1 /* i64_to_i32 */, "Q"]]],
            d: ["Q", "<=", 0xFFFFn]
          },
          {
            a: [82 /* i64_ne */, [51 /* i64_load16_u */, "x", "P", "R"], [66 /* i64_const */, "Q"]],
            b: [71 /* i32_ne */, [47 /* i32_load16_u */, "x", "P", "R"], [65 /* i32_const */, [-1 /* i64_to_i32 */, "Q"]]],
            d: ["Q", "<=", 0xFFFFn]
          },
          {
            a: [81 /* i64_eq */, [53 /* i64_load32_u */, "x", "P", "R"], [66 /* i64_const */, "Q"]],
            b: [70 /* i32_eq */, [40 /* i32_load */, "x", "P", "R"], [65 /* i32_const */, [-1 /* i64_to_i32 */, "Q"]]],
            d: ["Q", "<=", 0xFFFFFFFFn]
          },
          {
            a: [82 /* i64_ne */, [53 /* i64_load32_u */, "x", "P", "R"], [66 /* i64_const */, "Q"]],
            b: [71 /* i32_ne */, [40 /* i32_load */, "x", "P", "R"], [65 /* i32_const */, [-1 /* i64_to_i32 */, "Q"]]],
            d: ["Q", "<=", 0xFFFFFFFFn]
          },
          // Optimize boolean operations
          {
            a: [240 /* BOOL */, "x"],
            f: {
              "x": [
                // "if (x ? 1 : 0)" => "if (x)"
                { a: [242 /* BOOL_TO_INT */, "y"], b: [240 /* BOOL */, "y"] },
                // "if (x ? 0 : 1)" => "if (!x)"
                { a: [["@", 69 /* i32_eqz */, 80 /* i64_eqz */], "x"], b: [241 /* BOOL_NOT */, "y"] }
              ]
            }
          },
          {
            a: [241 /* BOOL_NOT */, "x"],
            f: {
              "x": [
                // "if (!(x ? 1 : 0))" => "if (!x)"
                { a: [242 /* BOOL_TO_INT */, "y"], b: [241 /* BOOL_NOT */, "y"] },
                // "if (!(x ? 0 : 1)" => "if (x)"
                { a: [["@", 69 /* i32_eqz */, 80 /* i64_eqz */], "y"], b: [240 /* BOOL */, "y"] },
                // "if (!(x === 0))" => "if (x !== 0)" (note: does not apply to floating-point due to NaN)
                { a: [70 /* i32_eq */, "y", "z"], b: [240 /* BOOL */, [71 /* i32_ne */, "y", "z"]] },
                { a: [71 /* i32_ne */, "y", "z"], b: [240 /* BOOL */, [70 /* i32_eq */, "y", "z"]] },
                { a: [72 /* i32_lt_s */, "y", "z"], b: [240 /* BOOL */, [78 /* i32_ge_s */, "y", "z"]] },
                { a: [73 /* i32_lt_u */, "y", "z"], b: [240 /* BOOL */, [79 /* i32_ge_u */, "y", "z"]] },
                { a: [74 /* i32_gt_s */, "y", "z"], b: [240 /* BOOL */, [76 /* i32_le_s */, "y", "z"]] },
                { a: [75 /* i32_gt_u */, "y", "z"], b: [240 /* BOOL */, [77 /* i32_le_u */, "y", "z"]] },
                { a: [76 /* i32_le_s */, "y", "z"], b: [240 /* BOOL */, [74 /* i32_gt_s */, "y", "z"]] },
                { a: [77 /* i32_le_u */, "y", "z"], b: [240 /* BOOL */, [75 /* i32_gt_u */, "y", "z"]] },
                { a: [78 /* i32_ge_s */, "y", "z"], b: [240 /* BOOL */, [72 /* i32_lt_s */, "y", "z"]] },
                { a: [79 /* i32_ge_u */, "y", "z"], b: [240 /* BOOL */, [73 /* i32_lt_u */, "y", "z"]] },
                { a: [81 /* i64_eq */, "y", "z"], b: [240 /* BOOL */, [82 /* i64_ne */, "y", "z"]] },
                { a: [82 /* i64_ne */, "y", "z"], b: [240 /* BOOL */, [81 /* i64_eq */, "y", "z"]] },
                { a: [83 /* i64_lt_s */, "y", "z"], b: [240 /* BOOL */, [89 /* i64_ge_s */, "y", "z"]] },
                { a: [84 /* i64_lt_u */, "y", "z"], b: [240 /* BOOL */, [90 /* i64_ge_u */, "y", "z"]] },
                { a: [85 /* i64_gt_s */, "y", "z"], b: [240 /* BOOL */, [87 /* i64_le_s */, "y", "z"]] },
                { a: [86 /* i64_gt_u */, "y", "z"], b: [240 /* BOOL */, [88 /* i64_le_u */, "y", "z"]] },
                { a: [87 /* i64_le_s */, "y", "z"], b: [240 /* BOOL */, [85 /* i64_gt_s */, "y", "z"]] },
                { a: [88 /* i64_le_u */, "y", "z"], b: [240 /* BOOL */, [86 /* i64_gt_u */, "y", "z"]] },
                { a: [89 /* i64_ge_s */, "y", "z"], b: [240 /* BOOL */, [83 /* i64_lt_s */, "y", "z"]] },
                { a: [90 /* i64_ge_u */, "y", "z"], b: [240 /* BOOL */, [84 /* i64_lt_u */, "y", "z"]] }
              ]
            }
          },
          // Optimize sign conversions
          {
            a: [243 /* TO_U32 */, "x"],
            f: {
              "x": [
                {
                  a: [40 /* i32_load */, "y", "P", "R"],
                  b: [245 /* U32_LOAD */, "y", "P", "R"]
                }
              ]
            }
          },
          {
            a: [244 /* TO_S64 */, "x"],
            f: {
              "x": [
                {
                  a: [41 /* i64_load */, "y", "P", "R"],
                  b: [246 /* S64_LOAD */, "y", "P", "R"]
                },
                // No sign conversion is needed for values in the shared signed/unsigned range
                {
                  a: [66 /* i64_const */, "P"],
                  b: [66 /* i64_const */, "P"],
                  d: ["P", "<=", 0x7FFFFFFFFFFFFFFFn]
                },
                {
                  a: [["$", 49 /* i64_load8_u */, 51 /* i64_load16_u */, 53 /* i64_load32_u */], "y", "P", "R"],
                  b: ["$", "y", "P", "R"]
                }
              ]
            }
          },
          // i32_wrap_i64 removal
          {
            a: [167 /* i32_wrap_i64 */, "x"],
            f: {
              "x": [
                {
                  a: [66 /* i64_const */, "P"],
                  b: [65 /* i32_const */, [-1 /* i64_to_i32 */, "P"]]
                },
                {
                  a: [48 /* i64_load8_s */, "y", "P", "R"],
                  b: [44 /* i32_load8_s */, "y", "P", "R"]
                },
                {
                  a: [49 /* i64_load8_u */, "y", "P", "R"],
                  b: [45 /* i32_load8_u */, "y", "P", "R"]
                },
                {
                  a: [50 /* i64_load16_s */, "y", "P", "R"],
                  b: [46 /* i32_load16_s */, "y", "P", "R"]
                },
                {
                  a: [51 /* i64_load16_u */, "y", "P", "R"],
                  b: [47 /* i32_load16_u */, "y", "P", "R"]
                },
                {
                  a: [["$", 52 /* i64_load32_s */, 53 /* i64_load32_u */, 41 /* i64_load */], "y", "P", "R"],
                  b: [40 /* i32_load */, "y", "P", "R"]
                },
                {
                  a: [["@", 172 /* i64_extend_i32_s */, 173 /* i64_extend_i32_u */], "y"],
                  b: "y"
                },
                {
                  a: [124 /* i64_add */, [["@", 172 /* i64_extend_i32_s */, 173 /* i64_extend_i32_u */], "y"], [66 /* i64_const */, "P"]],
                  b: [106 /* i32_add */, "y", [65 /* i32_const */, [-1 /* i64_to_i32 */, "P"]]]
                }
              ]
            }
          },
          // i64_and
          {
            a: [131 /* i64_and */, "x", [66 /* i64_const */, "P"]],
            f: {
              "x": [
                {
                  a: [66 /* i64_const */, "Q"],
                  b: [66 /* i64_const */, [-3 /* i64_and */, "P", "Q"]]
                },
                {
                  a: [131 /* i64_and */, "y", [66 /* i64_const */, "Q"]],
                  b: [131 /* i64_and */, "y", [66 /* i64_const */, [-3 /* i64_and */, "P", "Q"]]]
                },
                {
                  a: [49 /* i64_load8_u */, "y", "Q", "S"],
                  b: [49 /* i64_load8_u */, "y", "Q", "S"],
                  d: [["P", "&", 0xFFn], "===", 0xFFn]
                },
                {
                  a: [48 /* i64_load8_s */, "y", "Q", "S"],
                  b: [49 /* i64_load8_u */, "y", "Q", "S"],
                  d: ["P", "===", 0xFFn]
                },
                {
                  a: [51 /* i64_load16_u */, "y", "Q", "S"],
                  b: [51 /* i64_load16_u */, "y", "Q", "S"],
                  d: [["P", "&", 0xFFFFn], "===", 0xFFFFn]
                },
                {
                  a: [50 /* i64_load16_s */, "y", "Q", "S"],
                  b: [51 /* i64_load16_u */, "y", "Q", "S"],
                  d: ["P", "===", 0xFFFFn]
                },
                {
                  a: [53 /* i64_load32_u */, "y", "Q", "S"],
                  b: [53 /* i64_load32_u */, "y", "Q", "S"],
                  d: [["P", "&", 0xFFFFFFFFn], "===", 0xFFFFFFFFn]
                },
                {
                  a: [52 /* i64_load32_s */, "y", "Q", "S"],
                  b: [53 /* i64_load32_u */, "y", "Q", "S"],
                  d: ["P", "===", 0xFFFFFFFFn]
                }
              ]
            }
          }
        ];
        var compileOptimizations = () => {
          let nextVar = 0;
          const newVarName = () => "v" + nextVar++;
          const compileOperand = (ptrVar, index, operands, reusableNodes, then) => {
            if (index < operands.length) {
              const operand = operands[index];
              if (typeof operand === "string") {
                placeholderExprs[operand] = `${astVar}[${ptrVar}+${index + 1}]`;
                compileOperand(ptrVar, index + 1, operands, reusableNodes, then);
              } else {
                const childPtr = newVarName();
                const childOp = newVarName();
                code += `var ${childPtr}=${astVar}[${ptrVar}+${index + 1}],${childOp}=${astVar}[${childPtr}]&${65535 /* OpMask */};`;
                compileMatch(childPtr, childOp, operand, reusableNodes, (reusableNodes2) => {
                  compileOperand(ptrVar, index + 1, operands, reusableNodes2, then);
                });
              }
            } else {
              then(reusableNodes);
            }
          };
          const compileMatch = (ptrVar, opVar, [pattern, ...operands], reusableNodes, then) => {
            const parts = [];
            if (typeof pattern === "number") {
              parts.push(`${opVar}===${pattern}`);
            } else {
              const [name, ...oneOf] = pattern;
              oneOf.sort((a, b) => a - b);
              oneOfOps[name] = {
                v: ptrVar,
                ga: opVar,
                ha: oneOf.some((x) => opCanBeOptimized.has(x))
              };
              for (let i = 0; i < oneOf.length; i++) {
                let run = 1;
                while (i + run < oneOf.length && oneOf[i + run - 1] + 1 === oneOf[i + run]) run++;
                parts.push(run > 2 ? `${opVar}>=${oneOf[i]}&&${opVar}<=${oneOf[i += run - 1]}` : `${opVar}===${oneOf[i]}`);
              }
            }
            reusableNodes = reusableNodes.concat({
              v: ptrVar,
              w: operands.map((x) => typeof x === "string" ? x : null)
            });
            code += `if(${parts.join("||")}){`;
            compileOperand(ptrVar, 0, operands, reusableNodes, then);
            code += "}";
          };
          const compileRules = (ptrVar, opVar, rules2, buildStatName, reusableNodes, placeholderVarsFromParent) => {
            for (const { a: match, f: nested, b: replace, d: onlyIf } of rules2) {
              compileMatch(ptrVar, opVar, match, reusableNodes, (reusableNodes2) => {
                const placeholderVars = Object.create(placeholderVarsFromParent);
                compileOnlyIf(onlyIf, placeholderVars, () => {
                  if (nested) {
                    for (const operand in nested) {
                      storePlaceholderExprToVar(operand, placeholderVars);
                    }
                    for (const operand in nested) {
                      const childPtrVar = placeholderVars[operand];
                      const childOpVar = newVarName();
                      code += `var ${childOpVar}=${astVar}[${childPtrVar}]&${65535 /* OpMask */};`;
                      compileRules(
                        childPtrVar,
                        childOpVar,
                        nested[operand],
                        false ? (subMatch) => buildStatName(substituteMatch(match, operand, subMatch)) : null,
                        reusableNodes2,
                        placeholderVars
                      );
                    }
                  }
                  if (replace) {
                    if (false) code += `${recordStatsVar}(${JSON.stringify(buildStatName(match))});`;
                    const replacePtr = constructReplacement(replace, placeholderVars, reusableNodes2.slice(), `|${astVar}[${rootPtrVar}]&${~0 << 24 /* OutSlotShift */}`);
                    const optimizeAgain = typeof replace !== "string" && (typeof replace[0] === "string" ? oneOfOps[replace[0]].ha : opCanBeOptimized.has(replace[0]));
                    if (optimizeAgain) {
                      if (rootPtrVar !== replacePtr) code += `${rootPtrVar}=${replacePtr};`;
                      code += "continue";
                    } else {
                      code += "return " + replacePtr;
                    }
                  }
                });
              });
            }
          };
          const compileOnlyIf = (onlyIf, placeholderVars, then) => {
            if (onlyIf) {
              const compileCheck = (onlyIf2) => {
                if (typeof onlyIf2 === "string") {
                  return `${constantsVar}[${placeholderVars[onlyIf2] || placeholderExprs[onlyIf2]}]&0xFFFFFFFFFFFFFFFFn`;
                }
                if (typeof onlyIf2 === "bigint") {
                  return onlyIf2 + "n";
                }
                return `(${compileCheck(onlyIf2[0])})${onlyIf2[1]}(${compileCheck(onlyIf2[2])})`;
              };
              code += `if(${compileCheck(onlyIf)}){`;
              then();
              code += "}";
            } else {
              then();
            }
          };
          const storePlaceholderExprToVar = (operand, placeholderVars) => {
            if (!(operand in placeholderVars)) {
              const childPtr = newVarName();
              code += `var ${childPtr}=${placeholderExprs[operand]};`;
              placeholderVars[operand] = childPtr;
            }
          };
          const constructReplacement = (replace, placeholderVars, reusableNodes, outStackSlot = "") => {
            if (typeof replace === "string") return placeholderVars[replace] || placeholderExprs[replace];
            if (replace[0] === -1 /* i64_to_i32 */) {
              const operand = constructReplacement(replace[1], placeholderVars, reusableNodes);
              return `Number(${constantsVar}[${operand}]&0xFFFFFFFFn)`;
            }
            if (replace[0] === -2 /* i32_add */) {
              const operand1 = constructReplacement(replace[1], placeholderVars, reusableNodes);
              const operand2 = constructReplacement(replace[2], placeholderVars, reusableNodes);
              return `${operand1}+${operand2}`;
            }
            if (replace[0] === -3 /* i64_and */) {
              const replace1 = replace[1];
              if (typeof replace1 === "string") {
                storePlaceholderExprToVar(replace1, placeholderVars);
              }
              const operand1 = constructReplacement(replace1, placeholderVars, reusableNodes);
              const operand2 = constructReplacement(replace[2], placeholderVars, reusableNodes);
              code += `${constantsVar}[${operand1}]&=${constantsVar}[${operand2}];`;
              return operand1;
            }
            const [op, ...operands] = replace;
            const childCountWithoutPayloads = operands.length - +isPayload(operands[operands.length - 1]) - +isPayload(operands[operands.length - 2]);
            const shiftedChildCount = childCountWithoutPayloads << 16 /* ChildCountShift */;
            let bestScore = -1;
            let bestIndex;
            let newPtr;
            let existingOperands;
            for (let i = 0; i < reusableNodes.length; i++) {
              const reusableNode = reusableNodes[i];
              if (reusableNode.w.length === operands.length) {
                let score = 0;
                for (let i2 = 0; i2 < operands.length; i2++) {
                  if (operands[i2] === reusableNode.w[i2]) {
                    score++;
                  }
                }
                if (score > bestScore) {
                  bestScore = score;
                  bestIndex = i;
                  newPtr = reusableNode.v;
                  existingOperands = reusableNode.w;
                }
              }
            }
            if (typeof op === "string" && oneOfOps[op].v === newPtr) {
            } else {
              const node = (typeof op === "string" ? `${oneOfOps[op].ga}|${shiftedChildCount}` : `${op | shiftedChildCount}`) + outStackSlot;
              if (newPtr) {
                reusableNodes.splice(bestIndex, 1);
                code += `${astVar}[${newPtr}]=${node};`;
              } else {
                newPtr = newVarName();
                code += `var ${newPtr}=${allocateNode}(${node},${replace.length});`;
              }
            }
            for (let i = 0; i < operands.length; i++) {
              if (existingOperands && operands[i] !== existingOperands[i]) {
                const value = constructReplacement(operands[i], placeholderVars, reusableNodes);
                code += `${astVar}[${newPtr}+${i + 1}]=${value};`;
              }
            }
            return newPtr;
          };
          const placeholderExprs = {};
          const oneOfOps = {};
          const recordStatsVar = newVarName();
          const astVar = newVarName();
          const constantsVar = newVarName();
          const allocateNode = newVarName();
          const rootPtrVar = newVarName();
          const rootOpVar = newVarName();
          const opCanBeOptimized = /* @__PURE__ */ new Set();
          for (const { a: [pattern] } of rules) {
            if (typeof pattern === "number") {
              opCanBeOptimized.add(pattern);
            } else {
              const [, ...oneOf] = pattern;
              for (const op of oneOf) opCanBeOptimized.add(op);
            }
          }
          let code = `for(;;){var ${rootOpVar}=${astVar}[${rootPtrVar}]&${65535 /* OpMask */};`;
          compileRules(rootPtrVar, rootOpVar, rules, false ? matchToStatName : null, [], {});
          code += `return ${rootPtrVar}}`;
          return false ? new Function(recordStatsVar, `return(${astVar},${constantsVar},${allocateNode},${rootPtrVar})=>{${code}}`)(recordStats) : new Function(astVar, constantsVar, allocateNode, rootPtrVar, code);
        };

        // src/parse.ts
        var parse = (bytes) => {
          const dataView = new DataView(bytes.buffer);
          const readU32LEB = () => {
            let value = 0;
            let shift = 0;
            let byte;
            do {
              byte = bytes[ptr++];
              value |= (byte & 127) << shift;
              shift += 7;
            } while (byte & 128);
            return value >>> 0;
          };
          const readI32LEB = () => {
            let value = 0;
            let shift = 0;
            let byte;
            do {
              byte = bytes[ptr++];
              value |= (byte & 127) << shift;
              shift += 7;
            } while (byte & 128);
            return shift < 32 && byte & 64 ? value | ~0 << shift : value;
          };
          const readI64LEB = () => {
            let value = 0n;
            let shift = 0n;
            let byte;
            do {
              byte = bytes[ptr++];
              value |= BigInt(byte & 127) << shift;
              shift += 7n;
            } while (byte & 128);
            return shift < 64 && byte & 64 ? value | ~0n << shift : value;
          };
          const readF32 = () => {
            const value = dataView.getFloat32(ptr, true);
            ptr += 4;
            return value;
          };
          const readF64 = () => {
            const value = dataView.getFloat64(ptr, true);
            ptr += 8;
            return value;
          };
          const readValueTypes = (count = readU32LEB()) => {
            return [...bytes.slice(ptr, ptr += count)];
          };
          const readName = (length = readU32LEB()) => {
            return decodeURIComponent(escape(String.fromCharCode(...bytes.slice(ptr, ptr += length))));
          };
          const readLimits = (kind = bytes[ptr++]) => {
            return [readU32LEB(), kind === 0 /* OnlyMin */ ? Infinity : readU32LEB()];
          };
          const readConstantU32 = () => {
            const stack = [];
            let op;
            while ((op = bytes[ptr++]) !== 11 /* end */) {
              if (op === 65 /* i32_const */) {
                const value = readU32LEB();
                stack.push(() => value);
              } else if (op === 35 /* global_get */) {
                const index = readU32LEB();
                stack.push((globals) => {
                  if (index >= globals.length) throw RangeError();
                  return globals[index];
                });
              } else if (op === 106 /* i32_add */) {
                const right = stack.pop(), left = stack.pop();
                stack.push((globals) => left(globals) + right(globals) | 0);
              } else if (op === 107 /* i32_sub */) {
                const right = stack.pop(), left = stack.pop();
                stack.push((globals) => left(globals) - right(globals) | 0);
              } else if (op === 108 /* i32_mul */) {
                const right = stack.pop(), left = stack.pop();
                stack.push((globals) => Math.imul(left(globals), right(globals)));
              } else {
                throw new CompileError("Unsupported constant instruction: " + formatHexByte(op));
              }
            }
            if (stack.length !== 1) throw new CompileError("Unsupported constant");
            return stack[0];
          };
          const readConstantFuncIndex = () => {
            const op = bytes[ptr++];
            let value;
            if (op === 210 /* ref_func */) value = readU32LEB();
            else if (op === 208 /* ref_null */) {
              if (bytes[ptr++] !== 112 /* FuncRef */) throw new CompileError("Unsupported reference type: " + formatHexByte(bytes[ptr - 1]));
              value = null;
            } else throw new CompileError("Unsupported constant instruction: " + formatHexByte(op));
            if (bytes[ptr++] !== 11 /* end */) throw new CompileError("Expected end after constant: " + formatHexByte(bytes[ptr - 1]));
            return value;
          };
          const readInitializer = (type) => {
            const op = bytes[ptr++];
            let initializer;
            if (op === 65 /* i32_const */ && type === 127 /* I32 */) {
              const value = readI32LEB();
              initializer = () => value;
            } else if (op === 66 /* i64_const */ && type === 126 /* I64 */) {
              const value = readI64LEB();
              initializer = () => value;
            } else if (op === 67 /* f32_const */ && type === 125 /* F32 */) {
              const value = readF32();
              initializer = () => value;
            } else if (op === 68 /* f64_const */ && type === 124 /* F64 */) {
              const value = readF64();
              initializer = () => value;
            } else if (op === 208 /* ref_null */ && (type === 112 /* FuncRef */ || type === 111 /* ExternRef */)) {
              ptr++;
              initializer = () => null;
            } else if (op === 210 /* ref_func */ && type === 112 /* FuncRef */) {
              const index = readU32LEB();
              initializer = (_, createLazyFunc) => createLazyFunc(index);
            } else if (op === 35 /* global_get */) {
              const index = readU32LEB();
              initializer = (globals) => {
                if (index >= globals.length) throw RangeError();
                return globals[index];
              };
            } else throw new CompileError("Unsupported constant instruction: " + formatHexByte(op));
            if (bytes[ptr++] !== 11 /* end */) throw new CompileError("Expected end after constant: " + formatHexByte(bytes[ptr - 1]));
            return initializer;
          };
          const codeSection = [];
          const customSections = [];
          const dataSection = [];
          const elementSection = [];
          const exportSection = [];
          const functionSection = [];
          const globalSection = [];
          const importSection = [];
          const memorySection = [];
          const nameSection = /* @__PURE__ */ new Map();
          const tableSection = [];
          const typeSection = [];
          let startSection = -1;
          let ptr = 8;
          if (bytes.slice(0, 8).join(",") !== "0,97,115,109,1,0,0,0")
            throw new CompileError("Invalid file header");
          while (ptr + 5 < bytes.length) {
            const sectionType = bytes[ptr++];
            const contentsSize = readU32LEB();
            const sectionEnd = ptr + contentsSize;
            if (sectionType === 0 /* Custom */) {
              const sectionName = readName();
              customSections.push([sectionName, bytes.slice(ptr, sectionEnd)]);
              if (sectionName === "name") {
                const subsection = bytes[ptr++];
                const subsectionEnd = ptr + readU32LEB();
                if (subsection === 1 /* Function */) {
                  for (let i = 0, count = readU32LEB(); i < count && ptr < subsectionEnd; i++) {
                    nameSection.set(readU32LEB(), readName());
                  }
                }
              }
            } else if (sectionType === 1 /* Type */) {
              for (let i = 0, typeCount = readU32LEB(); i < typeCount; i++) {
                if (bytes[ptr++] !== 96) throw new CompileError("Invalid function type: " + formatHexByte(bytes[ptr - 1]));
                typeSection.push([readValueTypes(), readValueTypes()]);
              }
            } else if (sectionType === 2 /* Import */) {
              for (let i = 0, importCount = readU32LEB(); i < importCount; i++) {
                const module = readName();
                const name = readName();
                const desc = bytes[ptr++];
                if (desc === 0 /* Func */) importSection.push([module, name, desc, readU32LEB()]);
                else if (desc === 1 /* Table */) importSection.push([module, name, desc, bytes[ptr++], ...readLimits()]);
                else if (desc === 2 /* Mem */) importSection.push([module, name, desc, ...readLimits()]);
                else if (desc === 3 /* Global */) importSection.push([module, name, desc, bytes[ptr++], bytes[ptr++]]);
                else throw new CompileError("Unsupported import type: " + formatHexByte(desc));
              }
            } else if (sectionType === 3 /* Function */) {
              const functionCount = readU32LEB();
              for (let i = 0; i < functionCount; i++) {
                functionSection.push(readU32LEB());
              }
            } else if (sectionType === 4 /* Table */) {
              for (let i = 0, tableCount = readU32LEB(); i < tableCount; i++) {
                tableSection.push([bytes[ptr++], ...readLimits()]);
              }
            } else if (sectionType === 5 /* Memory */) {
              for (let i = 0, memoryCount = readU32LEB(); i < memoryCount; i++) {
                memorySection.push(readLimits());
              }
            } else if (sectionType === 6 /* Global */) {
              for (let i = 0, globalCount = readU32LEB(); i < globalCount; i++) {
                const type = bytes[ptr++];
                const mutable = bytes[ptr++];
                const initializer = readInitializer(type);
                globalSection.push([type, mutable, initializer]);
              }
            } else if (sectionType === 7 /* Export */) {
              for (let i = 0, exportCount = readU32LEB(); i < exportCount; i++) {
                const name = readName();
                const desc = bytes[ptr++];
                const index = readU32LEB();
                exportSection.push([name, desc, index]);
              }
            } else if (sectionType === 8 /* Start */) {
              startSection = readU32LEB();
            } else if (sectionType === 9 /* Element */) {
              for (let i = 0, elementCount = readU32LEB(); i < elementCount; i++) {
                const flags = readU32LEB();
                if (flags > (1 /* Passive */ | 2 /* TableIndex */ | 4 /* Expression */)) {
                  throw new CompileError("Unsupported element kind: " + flags);
                }
                const mode = flags & (1 /* Passive */ | 2 /* TableIndex */);
                const tableIndex = mode === 2 /* TableIndex */ ? readU32LEB() : mode === 0 ? 0 : null;
                const offset = flags & 1 /* Passive */ ? null : readConstantU32();
                if (mode && bytes[ptr++] !== (flags & 4 /* Expression */ ? 112 /* FuncRef */ : 0)) {
                  throw new CompileError("Unsupported element type: " + formatHexByte(bytes[ptr - 1]));
                }
                const indices = [];
                for (let j = 0, count = readU32LEB(); j < count; j++) {
                  indices.push(flags & 4 /* Expression */ ? readConstantFuncIndex() : readU32LEB());
                }
                elementSection.push([tableIndex, offset, indices]);
              }
            } else if (sectionType === 10 /* Code */) {
              for (let i = 0, codeCount = readU32LEB(); i < codeCount; i++) {
                const codeEnd = readU32LEB() + ptr;
                const localsCount = readU32LEB();
                const locals = [];
                for (let j = 0; j < localsCount; j++) locals.push([readU32LEB(), bytes[ptr++]]);
                codeSection.push([locals, ptr, codeEnd]);
                ptr = codeEnd;
              }
            } else if (sectionType === 11 /* Data */) {
              for (let i = 0, dataCount = readU32LEB(); i < dataCount; i++) {
                const mode = readU32LEB();
                if (mode > 2 /* Active */) throw new CompileError("Unsupported data mode: " + mode);
                const memory = mode === 2 /* Active */ ? readU32LEB() : 0;
                const offset = mode === 1 /* Passive */ ? null : readConstantU32();
                const length = readU32LEB();
                dataSection.push([memory, offset, bytes.slice(ptr, ptr += length)]);
              }
            } else if (sectionType === 12 /* DataCount */) {
            } else {
              throw new CompileError("Unsupported section type: " + formatHexByte(sectionType));
            }
            ptr = sectionEnd;
          }
          return {
            ia: bytes,
            h: dataView,
            H: codeSection,
            ta: customSections,
            ja: dataSection,
            ka: elementSection,
            la: exportSection,
            I: functionSection,
            ma: globalSection,
            na: importSection,
            oa: memorySection,
            pa: nameSection,
            qa: startSection,
            ra: tableSection,
            J: typeSection
          };
        };
        var formatHexByte = (x) => {
          return "0x" + x.toString(16).toUpperCase().padStart(2, "0");
        };
        var moduleMap = /* @__PURE__ */ new Map();
        var Module = class {
          constructor(source) {
            moduleMap.set(this, parse(source instanceof Uint8Array ? source : new Uint8Array(source instanceof ArrayBuffer ? source : source.buffer)));
          }
        };
        var CompileError = class extends Error {
          constructor(message) {
            super(message);
            this.name = "CompileError";
          }
        };

        // src/compile.ts
        var liveCastToWASM = (value, type) => {
          if (type === 125 /* F32 */ || type === 124 /* F64 */) return +value;
          if (type === 127 /* I32 */) return value | 0;
          if (type === 126 /* I64 */) return BigInt(value) & 0xFFFFFFFFFFFFFFFFn;
          if (type === 111 /* ExternRef */) return value;
          throw Error("Unsupported cast to type: " + formatHexByte(type));
        };
        var castToWASM = (code, type) => {
          if (type === 125 /* F32 */ || type === 124 /* F64 */) return "+" + code;
          if (type === 127 /* I32 */) return code + "|0";
          if (type === 126 /* I64 */) return `BigInt(${code})&0xFFFFFFFFFFFFFFFFn`;
          if (type === 111 /* ExternRef */) return code;
          if (type === 112 /* FuncRef */) return `l.${/* @__KEY__ */ "r"}(${code})`;
          throw Error("Unsupported cast to type: " + formatHexByte(type));
        };
        var castToJS = (code, type) => {
          if (type === 124 /* F64 */ || type === 127 /* I32 */) return code;
          if (type === 125 /* F32 */) return `Math.fround(${code})`;
          if (type === 126 /* I64 */) return `l.${/* @__KEY__ */ "p"}(${code})`;
          if (type === 111 /* ExternRef */) return code;
          if (type === 112 /* FuncRef */) return `l.${/* @__KEY__ */ "s"}(${code})`;
          throw Error("Unsupported cast to type: " + formatHexByte(type));
        };
        var metaTable = {
          [1 /* nop */]: 512 /* Omit */ | 8 /* Simple */,
          [26 /* drop */]: 1 | 512 /* Omit */ | 8 /* Simple */,
          [32 /* local_get */]: 4 /* Push */ | 16 /* HasIndex */ | 8 /* Simple */,
          [33 /* local_set */]: 1 | 16 /* HasIndex */ | 8 /* Simple */,
          [34 /* local_tee */]: 1 | 4 /* Push */ | 16 /* HasIndex */ | 8 /* Simple */,
          [35 /* global_get */]: 4 /* Push */ | 16 /* HasIndex */ | 8 /* Simple */,
          [36 /* global_set */]: 1 | 16 /* HasIndex */ | 8 /* Simple */,
          [37 /* table_get */]: 1 | 4 /* Push */ | 16 /* HasIndex */ | 8 /* Simple */,
          [38 /* table_set */]: 2 | 16 /* HasIndex */ | 8 /* Simple */,
          [40 /* i32_load */]: 1 | 4 /* Push */ | 32 /* HasMemory */ | 16 /* HasIndex */ | 8 /* Simple */,
          [41 /* i64_load */]: 1 | 4 /* Push */ | 32 /* HasMemory */ | 16 /* HasIndex */ | 8 /* Simple */,
          [42 /* f32_load */]: 1 | 4 /* Push */ | 32 /* HasMemory */ | 16 /* HasIndex */ | 8 /* Simple */,
          [43 /* f64_load */]: 1 | 4 /* Push */ | 32 /* HasMemory */ | 16 /* HasIndex */ | 8 /* Simple */,
          [44 /* i32_load8_s */]: 1 | 4 /* Push */ | 32 /* HasMemory */ | 16 /* HasIndex */ | 8 /* Simple */,
          [45 /* i32_load8_u */]: 1 | 4 /* Push */ | 32 /* HasMemory */ | 16 /* HasIndex */ | 8 /* Simple */,
          [46 /* i32_load16_s */]: 1 | 4 /* Push */ | 32 /* HasMemory */ | 16 /* HasIndex */ | 8 /* Simple */,
          [47 /* i32_load16_u */]: 1 | 4 /* Push */ | 32 /* HasMemory */ | 16 /* HasIndex */ | 8 /* Simple */,
          [48 /* i64_load8_s */]: 1 | 4 /* Push */ | 32 /* HasMemory */ | 16 /* HasIndex */ | 8 /* Simple */,
          [49 /* i64_load8_u */]: 1 | 4 /* Push */ | 32 /* HasMemory */ | 16 /* HasIndex */ | 8 /* Simple */,
          [50 /* i64_load16_s */]: 1 | 4 /* Push */ | 32 /* HasMemory */ | 16 /* HasIndex */ | 8 /* Simple */,
          [51 /* i64_load16_u */]: 1 | 4 /* Push */ | 32 /* HasMemory */ | 16 /* HasIndex */ | 8 /* Simple */,
          [52 /* i64_load32_s */]: 1 | 4 /* Push */ | 32 /* HasMemory */ | 16 /* HasIndex */ | 8 /* Simple */,
          [53 /* i64_load32_u */]: 1 | 4 /* Push */ | 32 /* HasMemory */ | 16 /* HasIndex */ | 8 /* Simple */,
          [54 /* i32_store */]: 2 | 32 /* HasMemory */ | 16 /* HasIndex */ | 8 /* Simple */,
          [55 /* i64_store */]: 2 | 32 /* HasMemory */ | 16 /* HasIndex */ | 8 /* Simple */,
          [56 /* f32_store */]: 2 | 32 /* HasMemory */ | 16 /* HasIndex */ | 8 /* Simple */,
          [57 /* f64_store */]: 2 | 32 /* HasMemory */ | 16 /* HasIndex */ | 8 /* Simple */,
          [58 /* i32_store8 */]: 2 | 32 /* HasMemory */ | 16 /* HasIndex */ | 8 /* Simple */,
          [59 /* i32_store16 */]: 2 | 32 /* HasMemory */ | 16 /* HasIndex */ | 8 /* Simple */,
          [60 /* i64_store8 */]: 2 | 32 /* HasMemory */ | 16 /* HasIndex */ | 8 /* Simple */,
          [61 /* i64_store16 */]: 2 | 32 /* HasMemory */ | 16 /* HasIndex */ | 8 /* Simple */,
          [62 /* i64_store32 */]: 2 | 32 /* HasMemory */ | 16 /* HasIndex */ | 8 /* Simple */,
          [63 /* memory_size */]: 4 /* Push */ | 16 /* HasIndex */ | 8 /* Simple */,
          [64 /* memory_grow */]: 1 | 4 /* Push */ | 16 /* HasIndex */ | 8 /* Simple */,
          [69 /* i32_eqz */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [70 /* i32_eq */]: 2 | 4 /* Push */ | 8 /* Simple */ | 64 /* BoolToInt */,
          [71 /* i32_ne */]: 2 | 4 /* Push */ | 8 /* Simple */ | 64 /* BoolToInt */,
          [72 /* i32_lt_s */]: 2 | 4 /* Push */ | 8 /* Simple */ | 64 /* BoolToInt */,
          [73 /* i32_lt_u */]: 2 | 4 /* Push */ | 8 /* Simple */ | 64 /* BoolToInt */ | 128 /* ToU32 */,
          [74 /* i32_gt_s */]: 2 | 4 /* Push */ | 8 /* Simple */ | 64 /* BoolToInt */,
          [75 /* i32_gt_u */]: 2 | 4 /* Push */ | 8 /* Simple */ | 64 /* BoolToInt */ | 128 /* ToU32 */,
          [76 /* i32_le_s */]: 2 | 4 /* Push */ | 8 /* Simple */ | 64 /* BoolToInt */,
          [77 /* i32_le_u */]: 2 | 4 /* Push */ | 8 /* Simple */ | 64 /* BoolToInt */ | 128 /* ToU32 */,
          [78 /* i32_ge_s */]: 2 | 4 /* Push */ | 8 /* Simple */ | 64 /* BoolToInt */,
          [79 /* i32_ge_u */]: 2 | 4 /* Push */ | 8 /* Simple */ | 64 /* BoolToInt */ | 128 /* ToU32 */,
          [80 /* i64_eqz */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [81 /* i64_eq */]: 2 | 4 /* Push */ | 8 /* Simple */ | 64 /* BoolToInt */,
          [82 /* i64_ne */]: 2 | 4 /* Push */ | 8 /* Simple */ | 64 /* BoolToInt */,
          [83 /* i64_lt_s */]: 2 | 4 /* Push */ | 8 /* Simple */ | 64 /* BoolToInt */ | 256 /* ToS64 */,
          [84 /* i64_lt_u */]: 2 | 4 /* Push */ | 8 /* Simple */ | 64 /* BoolToInt */,
          [85 /* i64_gt_s */]: 2 | 4 /* Push */ | 8 /* Simple */ | 64 /* BoolToInt */ | 256 /* ToS64 */,
          [86 /* i64_gt_u */]: 2 | 4 /* Push */ | 8 /* Simple */ | 64 /* BoolToInt */,
          [87 /* i64_le_s */]: 2 | 4 /* Push */ | 8 /* Simple */ | 64 /* BoolToInt */ | 256 /* ToS64 */,
          [88 /* i64_le_u */]: 2 | 4 /* Push */ | 8 /* Simple */ | 64 /* BoolToInt */,
          [89 /* i64_ge_s */]: 2 | 4 /* Push */ | 8 /* Simple */ | 64 /* BoolToInt */ | 256 /* ToS64 */,
          [90 /* i64_ge_u */]: 2 | 4 /* Push */ | 8 /* Simple */ | 64 /* BoolToInt */,
          [91 /* f32_eq */]: 2 | 4 /* Push */ | 8 /* Simple */ | 64 /* BoolToInt */,
          [92 /* f32_ne */]: 2 | 4 /* Push */ | 8 /* Simple */ | 64 /* BoolToInt */,
          [93 /* f32_lt */]: 2 | 4 /* Push */ | 8 /* Simple */ | 64 /* BoolToInt */,
          [94 /* f32_gt */]: 2 | 4 /* Push */ | 8 /* Simple */ | 64 /* BoolToInt */,
          [95 /* f32_le */]: 2 | 4 /* Push */ | 8 /* Simple */ | 64 /* BoolToInt */,
          [96 /* f32_ge */]: 2 | 4 /* Push */ | 8 /* Simple */ | 64 /* BoolToInt */,
          [97 /* f64_eq */]: 2 | 4 /* Push */ | 8 /* Simple */ | 64 /* BoolToInt */,
          [98 /* f64_ne */]: 2 | 4 /* Push */ | 8 /* Simple */ | 64 /* BoolToInt */,
          [99 /* f64_lt */]: 2 | 4 /* Push */ | 8 /* Simple */ | 64 /* BoolToInt */,
          [100 /* f64_gt */]: 2 | 4 /* Push */ | 8 /* Simple */ | 64 /* BoolToInt */,
          [101 /* f64_le */]: 2 | 4 /* Push */ | 8 /* Simple */ | 64 /* BoolToInt */,
          [102 /* f64_ge */]: 2 | 4 /* Push */ | 8 /* Simple */ | 64 /* BoolToInt */,
          [103 /* i32_clz */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [104 /* i32_ctz */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [105 /* i32_popcnt */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [106 /* i32_add */]: 2 | 4 /* Push */ | 8 /* Simple */,
          [107 /* i32_sub */]: 2 | 4 /* Push */ | 8 /* Simple */,
          [108 /* i32_mul */]: 2 | 4 /* Push */ | 8 /* Simple */,
          [109 /* i32_div_s */]: 2 | 4 /* Push */ | 8 /* Simple */,
          [110 /* i32_div_u */]: 2 | 4 /* Push */ | 8 /* Simple */ | 128 /* ToU32 */,
          [111 /* i32_rem_s */]: 2 | 4 /* Push */ | 8 /* Simple */,
          [112 /* i32_rem_u */]: 2 | 4 /* Push */ | 8 /* Simple */ | 128 /* ToU32 */,
          [113 /* i32_and */]: 2 | 4 /* Push */ | 8 /* Simple */,
          [114 /* i32_or */]: 2 | 4 /* Push */ | 8 /* Simple */,
          [115 /* i32_xor */]: 2 | 4 /* Push */ | 8 /* Simple */,
          [116 /* i32_shl */]: 2 | 4 /* Push */ | 8 /* Simple */,
          [117 /* i32_shr_s */]: 2 | 4 /* Push */ | 8 /* Simple */,
          [118 /* i32_shr_u */]: 2 | 4 /* Push */ | 8 /* Simple */,
          [119 /* i32_rotl */]: 2 | 4 /* Push */ | 8 /* Simple */,
          [120 /* i32_rotr */]: 2 | 4 /* Push */ | 8 /* Simple */,
          [121 /* i64_clz */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [122 /* i64_ctz */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [123 /* i64_popcnt */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [124 /* i64_add */]: 2 | 4 /* Push */ | 8 /* Simple */,
          [125 /* i64_sub */]: 2 | 4 /* Push */ | 8 /* Simple */,
          [126 /* i64_mul */]: 2 | 4 /* Push */ | 8 /* Simple */,
          [127 /* i64_div_s */]: 2 | 4 /* Push */ | 8 /* Simple */ | 256 /* ToS64 */,
          [128 /* i64_div_u */]: 2 | 4 /* Push */ | 8 /* Simple */,
          [129 /* i64_rem_s */]: 2 | 4 /* Push */ | 8 /* Simple */ | 256 /* ToS64 */,
          [130 /* i64_rem_u */]: 2 | 4 /* Push */ | 8 /* Simple */,
          [131 /* i64_and */]: 2 | 4 /* Push */ | 8 /* Simple */,
          [132 /* i64_or */]: 2 | 4 /* Push */ | 8 /* Simple */,
          [133 /* i64_xor */]: 2 | 4 /* Push */ | 8 /* Simple */,
          [134 /* i64_shl */]: 2 | 4 /* Push */ | 8 /* Simple */ | 1024 /* And63 */,
          [135 /* i64_shr_s */]: 2 | 4 /* Push */ | 8 /* Simple */ | 1024 /* And63 */,
          [136 /* i64_shr_u */]: 2 | 4 /* Push */ | 8 /* Simple */ | 1024 /* And63 */,
          [137 /* i64_rotl */]: 2 | 4 /* Push */ | 8 /* Simple */ | 1024 /* And63 */,
          [138 /* i64_rotr */]: 2 | 4 /* Push */ | 8 /* Simple */ | 1024 /* And63 */,
          [139 /* f32_abs */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [140 /* f32_neg */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [141 /* f32_ceil */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [142 /* f32_floor */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [143 /* f32_trunc */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [144 /* f32_nearest */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [145 /* f32_sqrt */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [146 /* f32_add */]: 2 | 4 /* Push */ | 8 /* Simple */,
          [147 /* f32_sub */]: 2 | 4 /* Push */ | 8 /* Simple */,
          [148 /* f32_mul */]: 2 | 4 /* Push */ | 8 /* Simple */,
          [149 /* f32_div */]: 2 | 4 /* Push */ | 8 /* Simple */,
          [150 /* f32_min */]: 2 | 4 /* Push */ | 8 /* Simple */,
          [151 /* f32_max */]: 2 | 4 /* Push */ | 8 /* Simple */,
          [152 /* f32_copysign */]: 2 | 4 /* Push */ | 8 /* Simple */,
          [153 /* f64_abs */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [154 /* f64_neg */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [155 /* f64_ceil */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [156 /* f64_floor */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [157 /* f64_trunc */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [158 /* f64_nearest */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [159 /* f64_sqrt */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [160 /* f64_add */]: 2 | 4 /* Push */ | 8 /* Simple */,
          [161 /* f64_sub */]: 2 | 4 /* Push */ | 8 /* Simple */,
          [162 /* f64_mul */]: 2 | 4 /* Push */ | 8 /* Simple */,
          [163 /* f64_div */]: 2 | 4 /* Push */ | 8 /* Simple */,
          [164 /* f64_min */]: 2 | 4 /* Push */ | 8 /* Simple */,
          [165 /* f64_max */]: 2 | 4 /* Push */ | 8 /* Simple */,
          [166 /* f64_copysign */]: 2 | 4 /* Push */ | 8 /* Simple */,
          [167 /* i32_wrap_i64 */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [168 /* i32_trunc_f32_s */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [169 /* i32_trunc_f32_u */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [170 /* i32_trunc_f64_s */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [171 /* i32_trunc_f64_u */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [172 /* i64_extend_i32_s */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [173 /* i64_extend_i32_u */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [174 /* i64_trunc_f32_s */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [175 /* i64_trunc_f32_u */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [176 /* i64_trunc_f64_s */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [177 /* i64_trunc_f64_u */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [178 /* f32_convert_i32_s */]: 1 | 4 /* Push */ | 512 /* Omit */ | 8 /* Simple */,
          [179 /* f32_convert_i32_u */]: 1 | 4 /* Push */ | 512 /* Omit */ | 8 /* Simple */ | 128 /* ToU32 */,
          [180 /* f32_convert_i64_s */]: 1 | 4 /* Push */ | 8 /* Simple */ | 256 /* ToS64 */,
          [181 /* f32_convert_i64_u */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [182 /* f32_demote_f64 */]: 1 | 4 /* Push */ | 512 /* Omit */ | 8 /* Simple */,
          [183 /* f64_convert_i32_s */]: 1 | 4 /* Push */ | 512 /* Omit */ | 8 /* Simple */,
          [184 /* f64_convert_i32_u */]: 1 | 4 /* Push */ | 512 /* Omit */ | 8 /* Simple */ | 128 /* ToU32 */,
          [185 /* f64_convert_i64_s */]: 1 | 4 /* Push */ | 8 /* Simple */ | 256 /* ToS64 */,
          [186 /* f64_convert_i64_u */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [187 /* f64_promote_f32 */]: 1 | 4 /* Push */ | 512 /* Omit */ | 8 /* Simple */,
          [188 /* i32_reinterpret_f32 */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [189 /* i64_reinterpret_f64 */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [190 /* f32_reinterpret_i32 */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [191 /* f64_reinterpret_i64 */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [192 /* i32_extend8_s */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [193 /* i32_extend16_s */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [194 /* i64_extend8_s */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [195 /* i64_extend16_s */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [196 /* i64_extend32_s */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [209 /* ref_is_null */]: 1 | 4 /* Push */ | 8 /* Simple */ | 64 /* BoolToInt */,
          [210 /* ref_func */]: 4 /* Push */ | 16 /* HasIndex */ | 8 /* Simple */,
          [64512 /* i32_trunc_sat_f32_s */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [64513 /* i32_trunc_sat_f32_u */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [64514 /* i32_trunc_sat_f64_s */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [64515 /* i32_trunc_sat_f64_u */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [64516 /* i64_trunc_sat_f32_s */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [64517 /* i64_trunc_sat_f32_u */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [64518 /* i64_trunc_sat_f64_s */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [64519 /* i64_trunc_sat_f64_u */]: 1 | 4 /* Push */ | 8 /* Simple */,
          [64521 /* data_drop */]: 16 /* HasIndex */ | 8 /* Simple */,
          [64525 /* elem_drop */]: 16 /* HasIndex */ | 8 /* Simple */,
          [64527 /* table_grow */]: 2 | 4 /* Push */ | 16 /* HasIndex */ | 8 /* Simple */,
          [64528 /* table_size */]: 4 /* Push */ | 16 /* HasIndex */ | 8 /* Simple */,
          [64529 /* table_fill */]: 3 | 16 /* HasIndex */ | 8 /* Simple */
        };
        var astBufferSingleton = new Int32Array(1 << 16);
        var optimizeNode = compileOptimizations();
        var compileCode = (funcs, funcTypes, createLazyFunc, tables, dataSegments, elementSegments, globals, context, wasm, codeIndex, funcIndex) => {
          const readU32LEB = () => {
            let value = 0;
            let shift = 0;
            let byte;
            do {
              byte = bytes[bytesPtr++];
              value |= (byte & 127) << shift;
              shift += 7;
            } while (byte & 128);
            return value >>> 0;
          };
          const readI32LEB = () => {
            let value = 0;
            let shift = 0;
            let byte;
            do {
              byte = bytes[bytesPtr++];
              value |= (byte & 127) << shift;
              shift += 7;
            } while (byte & 128);
            return shift < 32 && byte & 64 ? value | ~0 << shift : value;
          };
          const readI64LEB = () => {
            let value = 0n;
            let shift = 0n;
            let byte;
            do {
              byte = bytes[bytesPtr++];
              value |= BigInt(byte & 127) << shift;
              shift += 7n;
            } while (byte & 128);
            return shift < 64 && byte & 64 ? value | ~0n << shift : value;
          };
          const readBlockType = () => {
            const byte = bytes[bytesPtr];
            if (byte === 64) {
              bytesPtr++;
              return [0, 0];
            }
            if (byte & 64) {
              bytesPtr++;
              return [0, 1];
            }
            const typeIndex = readU32LEB();
            const [argTypes2, returnTypes2] = typeSection[typeIndex];
            return [argTypes2.length, returnTypes2.length];
          };
          const ast = astBufferSingleton;
          const astPtrs = [];
          let astNextPtr = 0;
          const constants = [];
          let stackLimit = 0;
          const stackSlotName = (stackSlot) => {
            while (stackLimit < stackSlot) decls.push("s" + ++stackLimit);
            return "s" + stackSlot;
          };
          const usedTables = {};
          const tableName = (index) => {
            if (!usedTables[index]) {
              decls.push(`t${index}=t[${index}]`);
              usedTables[index] = true;
            }
            return "t" + index;
          };
          const load8 = (field, addr, offset, index) => {
            return `c.${field + index}[${emit(addr)}${offset ? "+" + offset : ""}]`;
          };
          const store8 = (field, addr, offset, index, value) => {
            return `c.${field + index}[${emit(addr)}${offset ? "+" + offset : ""}]=${value}`;
          };
          const load = (get, addr, offset, index) => {
            return `c.${/* @__KEY__ */ "h" + index}.get${get}(${emit(addr)}${offset ? "+" + offset : ""},1)`;
          };
          const store = (set, addr, offset, index, value) => {
            return `c.${/* @__KEY__ */ "h" + index}.set${set}(${emit(addr)}${offset ? "+" + offset : ""},${value},1)`;
          };
          const emit = (ptr) => {
            return ptr < 0 ? stackSlotName(-ptr) : `(${emitUnwrapped(ptr)})`;
          };
          const emitUnwrapped = (ptr) => {
            const node = ast[ptr];
            const op = node & 65535 /* OpMask */;
            switch (op) {
              case 16 /* call */:
              case 18 /* return_call */: {
                const childCount = node >> 16 /* ChildCountShift */ & 255 /* ChildCountMask */;
                const funcIndex2 = ast[ptr + childCount + 1];
                const [argTypes2, returnTypes2] = funcTypes[funcIndex2];
                const args = [];
                for (let i = 1; i <= childCount; i++) args.push(emit(ast[ptr + i]));
                const fn = `f[${funcIndex2}]`;
                const code = op === 18 /* return_call */ ? `l.${/* @__KEY__ */ "G"}(this,${fn},[${args}])` : `${fn}(${args})`;
                if (returnTypes2.length < 2) return code;
                const slot = ast[ptr + childCount + 2];
                const returns = [];
                for (let i = 0; i < returnTypes2.length; i++) returns.push(stackSlotName(slot + i));
                return `[${returns}]=${code}`;
              }
              case 17 /* call_indirect */:
              case 19 /* return_call_indirect */: {
                const childCount = node >> 16 /* ChildCountShift */ & 255 /* ChildCountMask */;
                const tableIndex = ast[ptr + childCount + 2];
                const typeIndex = ast[ptr + childCount + 3];
                const [argTypes2, returnTypes2] = typeSection[typeIndex];
                const args = [];
                const funcIndex2 = emit(ast[ptr + 1]);
                for (let i = 1; i <= childCount; i++) args.push(emit(ast[ptr + i + 1]));
                const fn = `${tableName(tableIndex)}[${funcIndex2}].${/* @__KEY__ */ "u"}`;
                const code = op === 19 /* return_call_indirect */ ? `l.${/* @__KEY__ */ "G"}(this,${fn},[${args}])` : `${fn}(${args})`;
                if (returnTypes2.length < 2) return code;
                const slot = ast[ptr + childCount + 4];
                const returns = [];
                for (let i = 0; i < returnTypes2.length; i++) returns.push(stackSlotName(slot + i));
                return `[${returns}]=${code}`;
              }
              case 27 /* select */:
              case 28 /* select_type */:
                return `${emit(ast[ptr + 1])}?${emit(ast[ptr + 2])}:${emit(ast[ptr + 3])}`;
              case 32 /* local_get */:
                return names[ast[ptr + 1]];
              case 33 /* local_set */:
              case 34 /* local_tee */:
                return `${names[ast[ptr + 2]]}=${emit(ast[ptr + 1])}`;
              case 35 /* global_get */:
                return `g[${ast[ptr + 1]}]`;
              case 36 /* global_set */:
                return `g[${ast[ptr + 2]}]=${emit(ast[ptr + 1])}`;
              case 37 /* table_get */:
                return tableName(ast[ptr + 2]) + `[${emit(ast[ptr + 1])}]`;
              case 38 /* table_set */:
                return tableName(ast[ptr + 3]) + `[${emit(ast[ptr + 1])}]=${emit(ast[ptr + 2])}`;
              case 40 /* i32_load */:
                return load("Int32", ast[ptr + 1], ast[ptr + 2], ast[ptr + 3]);
              case 245 /* U32_LOAD */:
                return load("Uint32", ast[ptr + 1], ast[ptr + 2], ast[ptr + 3]);
              case 41 /* i64_load */:
                return load("BigUint64", ast[ptr + 1], ast[ptr + 2], ast[ptr + 3]);
              case 246 /* S64_LOAD */:
                return load("BigInt64", ast[ptr + 1], ast[ptr + 2], ast[ptr + 3]);
              case 42 /* f32_load */:
                return load("Float32", ast[ptr + 1], ast[ptr + 2], ast[ptr + 3]);
              case 43 /* f64_load */:
                return load("Float64", ast[ptr + 1], ast[ptr + 2], ast[ptr + 3]);
              case 44 /* i32_load8_s */:
                return load8(/* @__KEY__ */ "k", ast[ptr + 1], ast[ptr + 2], ast[ptr + 3]);
              case 45 /* i32_load8_u */:
                return load8(/* @__KEY__ */ "e", ast[ptr + 1], ast[ptr + 2], ast[ptr + 3]);
              case 46 /* i32_load16_s */:
                return load("Int16", ast[ptr + 1], ast[ptr + 2], ast[ptr + 3]);
              case 47 /* i32_load16_u */:
                return load("Uint16", ast[ptr + 1], ast[ptr + 2], ast[ptr + 3]);
              case 48 /* i64_load8_s */:
                return `BigInt(${load8(/* @__KEY__ */ "k", ast[ptr + 1], ast[ptr + 2], ast[ptr + 3])})&0xFFFFFFFFFFFFFFFFn`;
              case 49 /* i64_load8_u */:
                return `BigInt(${load8(/* @__KEY__ */ "e", ast[ptr + 1], ast[ptr + 2], ast[ptr + 3])})`;
              case 50 /* i64_load16_s */:
                return `BigInt(${load("Int16", ast[ptr + 1], ast[ptr + 2], ast[ptr + 3])})&0xFFFFFFFFFFFFFFFFn`;
              case 51 /* i64_load16_u */:
                return `BigInt(${load("Uint16", ast[ptr + 1], ast[ptr + 2], ast[ptr + 3])})`;
              case 52 /* i64_load32_s */:
                return `BigInt(${load("Int32", ast[ptr + 1], ast[ptr + 2], ast[ptr + 3])})&0xFFFFFFFFFFFFFFFFn`;
              case 53 /* i64_load32_u */:
                return `BigInt(${load("Uint32", ast[ptr + 1], ast[ptr + 2], ast[ptr + 3])})`;
              case 54 /* i32_store */:
                return store("Int32", ast[ptr + 1], ast[ptr + 3], ast[ptr + 4], emit(ast[ptr + 2]));
              case 55 /* i64_store */:
                return store("BigUint64", ast[ptr + 1], ast[ptr + 3], ast[ptr + 4], emit(ast[ptr + 2]));
              case 56 /* f32_store */:
                return store("Float32", ast[ptr + 1], ast[ptr + 3], ast[ptr + 4], emit(ast[ptr + 2]));
              case 57 /* f64_store */:
                return store("Float64", ast[ptr + 1], ast[ptr + 3], ast[ptr + 4], emit(ast[ptr + 2]));
              case 58 /* i32_store8 */:
                return store8(/* @__KEY__ */ "e", ast[ptr + 1], ast[ptr + 3], ast[ptr + 4], emit(ast[ptr + 2]));
              case 59 /* i32_store16 */:
                return store("Int16", ast[ptr + 1], ast[ptr + 3], ast[ptr + 4], emit(ast[ptr + 2]));
              case 60 /* i64_store8 */:
                return store8(/* @__KEY__ */ "e", ast[ptr + 1], ast[ptr + 3], ast[ptr + 4], `Number(${emit(ast[ptr + 2])}&255n)`);
              case 61 /* i64_store16 */:
                return store("Int16", ast[ptr + 1], ast[ptr + 3], ast[ptr + 4], `Number(${emit(ast[ptr + 2])}&65535n)`);
              case 62 /* i64_store32 */:
                return store("Int32", ast[ptr + 1], ast[ptr + 3], ast[ptr + 4], `Number(${emit(ast[ptr + 2])}&0xFFFFFFFFn)`);
              case 63 /* memory_size */:
                return `c.${/* @__KEY__ */ "K" + ast[ptr + 1]}.${/* @__KEY__ */ "n"}`;
              case 64 /* memory_grow */:
                return `c.${/* @__KEY__ */ "K" + ast[ptr + 2]}.${/* @__KEY__ */ "L"}(${emit(ast[ptr + 1])})`;
              case 65 /* i32_const */:
                return ast[ptr + 1] + "";
              case 66 /* i64_const */:
                return (constants[ast[ptr + 1]] & 0xFFFFFFFFFFFFFFFFn) + "n";
              case 67 /* f32_const */: {
                const value = dataView.getFloat32(ast[ptr + 1], true);
                return Object.is(value, -0) ? "-0" : value + "";
              }
              case 68 /* f64_const */: {
                const value = dataView.getFloat64(ast[ptr + 1], true);
                return Object.is(value, -0) ? "-0" : value + "";
              }
              case 240 /* BOOL */:
                return emit(ast[ptr + 1]);
              case 241 /* BOOL_NOT */:
                return `!${emit(ast[ptr + 1])}`;
              case 242 /* BOOL_TO_INT */:
                return `${emit(ast[ptr + 1])}?1:0`;
              case 243 /* TO_U32 */:
                return `${emit(ast[ptr + 1])}>>>0`;
              case 244 /* TO_S64 */:
                return `l.${/* @__KEY__ */ "p"}(${emit(ast[ptr + 1])})`;
              case 69 /* i32_eqz */:
              case 80 /* i64_eqz */:
                return `${emit(ast[ptr + 1])}?0:1`;
              case 70 /* i32_eq */:
              case 81 /* i64_eq */:
              case 91 /* f32_eq */:
              case 97 /* f64_eq */:
                return `${emit(ast[ptr + 1])}===${emit(ast[ptr + 2])}`;
              case 71 /* i32_ne */:
              case 82 /* i64_ne */:
              case 92 /* f32_ne */:
              case 98 /* f64_ne */:
                return `${emit(ast[ptr + 1])}!==${emit(ast[ptr + 2])}`;
              case 72 /* i32_lt_s */:
              case 73 /* i32_lt_u */:
              case 83 /* i64_lt_s */:
              case 84 /* i64_lt_u */:
              case 93 /* f32_lt */:
              case 99 /* f64_lt */:
                return `${emit(ast[ptr + 1])}<${emit(ast[ptr + 2])}`;
              case 74 /* i32_gt_s */:
              case 75 /* i32_gt_u */:
              case 85 /* i64_gt_s */:
              case 86 /* i64_gt_u */:
              case 94 /* f32_gt */:
              case 100 /* f64_gt */:
                return `${emit(ast[ptr + 1])}>${emit(ast[ptr + 2])}`;
              case 76 /* i32_le_s */:
              case 77 /* i32_le_u */:
              case 87 /* i64_le_s */:
              case 88 /* i64_le_u */:
              case 95 /* f32_le */:
              case 101 /* f64_le */:
                return `${emit(ast[ptr + 1])}<=${emit(ast[ptr + 2])}`;
              case 78 /* i32_ge_s */:
              case 79 /* i32_ge_u */:
              case 89 /* i64_ge_s */:
              case 90 /* i64_ge_u */:
              case 96 /* f32_ge */:
              case 102 /* f64_ge */:
                return `${emit(ast[ptr + 1])}>=${emit(ast[ptr + 2])}`;
              case 103 /* i32_clz */:
                return `Math.clz32(${emit(ast[ptr + 1])})`;
              case 104 /* i32_ctz */:
                return `l.${/* @__KEY__ */ "W"}(${emit(ast[ptr + 1])})`;
              case 105 /* i32_popcnt */:
                return `l.${/* @__KEY__ */ "X"}(${emit(ast[ptr + 1])})`;
              case 106 /* i32_add */:
                return `${emit(ast[ptr + 1])}+${emit(ast[ptr + 2])}|0`;
              case 107 /* i32_sub */:
                return `${emit(ast[ptr + 1])}-${emit(ast[ptr + 2])}|0`;
              case 108 /* i32_mul */:
                return `Math.imul(${emit(ast[ptr + 1])},${emit(ast[ptr + 2])})`;
              case 110 /* i32_div_u */:
              case 109 /* i32_div_s */:
                return `${emit(ast[ptr + 1])}/${emit(ast[ptr + 2])}|0`;
              case 112 /* i32_rem_u */:
              case 111 /* i32_rem_s */:
                return `${emit(ast[ptr + 1])}%${emit(ast[ptr + 2])}|0`;
              case 113 /* i32_and */:
                return `${emit(ast[ptr + 1])}&${emit(ast[ptr + 2])}`;
              case 114 /* i32_or */:
                return `${emit(ast[ptr + 1])}|${emit(ast[ptr + 2])}`;
              case 115 /* i32_xor */:
                return `${emit(ast[ptr + 1])}^${emit(ast[ptr + 2])}`;
              case 116 /* i32_shl */:
                return `${emit(ast[ptr + 1])}<<${emit(ast[ptr + 2])}`;
              case 117 /* i32_shr_s */:
                return `${emit(ast[ptr + 1])}>>${emit(ast[ptr + 2])}`;
              case 118 /* i32_shr_u */:
                return `${emit(ast[ptr + 1])}>>>${emit(ast[ptr + 2])}|0`;
              case 119 /* i32_rotl */:
                return `l.${/* @__KEY__ */ "S"}(${emit(ast[ptr + 1])},${emit(ast[ptr + 2])})`;
              case 120 /* i32_rotr */:
                return `l.${/* @__KEY__ */ "T"}(${emit(ast[ptr + 1])},${emit(ast[ptr + 2])})`;
              case 121 /* i64_clz */:
                return `l.${/* @__KEY__ */ "Y"}(${emit(ast[ptr + 1])})`;
              case 122 /* i64_ctz */:
                return `l.${/* @__KEY__ */ "Z"}(${emit(ast[ptr + 1])})`;
              case 123 /* i64_popcnt */:
                return `l.${/* @__KEY__ */ "_"}(${emit(ast[ptr + 1])})`;
              case 124 /* i64_add */:
                return `(${emit(ast[ptr + 1])}+${emit(ast[ptr + 2])})&0xFFFFFFFFFFFFFFFFn`;
              case 125 /* i64_sub */:
                return `(${emit(ast[ptr + 1])}-${emit(ast[ptr + 2])})&0xFFFFFFFFFFFFFFFFn`;
              case 126 /* i64_mul */:
                return `(${emit(ast[ptr + 1])}*${emit(ast[ptr + 2])})&0xFFFFFFFFFFFFFFFFn`;
              case 127 /* i64_div_s */:
                return `${emit(ast[ptr + 1])}/${emit(ast[ptr + 2])}&0xFFFFFFFFFFFFFFFFn`;
              case 128 /* i64_div_u */:
                return `${emit(ast[ptr + 1])}/${emit(ast[ptr + 2])}`;
              case 129 /* i64_rem_s */:
                return `${emit(ast[ptr + 1])}%${emit(ast[ptr + 2])}&0xFFFFFFFFFFFFFFFFn`;
              case 130 /* i64_rem_u */:
                return `${emit(ast[ptr + 1])}%${emit(ast[ptr + 2])}`;
              case 131 /* i64_and */:
                return `${emit(ast[ptr + 1])}&${emit(ast[ptr + 2])}`;
              case 132 /* i64_or */:
                return `${emit(ast[ptr + 1])}|${emit(ast[ptr + 2])}`;
              case 133 /* i64_xor */:
                return `${emit(ast[ptr + 1])}^${emit(ast[ptr + 2])}`;
              case 134 /* i64_shl */:
                return `${emit(ast[ptr + 1])}<<${emit(ast[ptr + 2])}&0xFFFFFFFFFFFFFFFFn`;
              case 135 /* i64_shr_s */:
                return `l.${/* @__KEY__ */ "p"}(${emit(ast[ptr + 1])})>>${emit(ast[ptr + 2])}&0xFFFFFFFFFFFFFFFFn`;
              case 136 /* i64_shr_u */:
                return `${emit(ast[ptr + 1])}>>${emit(ast[ptr + 2])}`;
              case 137 /* i64_rotl */:
                return `l.${/* @__KEY__ */ "U"}(${emit(ast[ptr + 1])},${emit(ast[ptr + 2])})`;
              case 138 /* i64_rotr */:
                return `l.${/* @__KEY__ */ "V"}(${emit(ast[ptr + 1])},${emit(ast[ptr + 2])})`;
              case 139 /* f32_abs */:
              case 153 /* f64_abs */:
                return `Math.abs(${emit(ast[ptr + 1])})`;
              case 140 /* f32_neg */:
              case 154 /* f64_neg */:
                return `-${emit(ast[ptr + 1])}`;
              case 141 /* f32_ceil */:
              case 155 /* f64_ceil */:
                return `Math.ceil(${emit(ast[ptr + 1])})`;
              case 142 /* f32_floor */:
              case 156 /* f64_floor */:
                return `Math.floor(${emit(ast[ptr + 1])})`;
              case 143 /* f32_trunc */:
              case 157 /* f64_trunc */:
                return `Math.trunc(${emit(ast[ptr + 1])})`;
              case 144 /* f32_nearest */:
              case 158 /* f64_nearest */:
                return `Math.round(${emit(ast[ptr + 1])})`;
              case 145 /* f32_sqrt */:
              case 159 /* f64_sqrt */:
                return `Math.sqrt(${emit(ast[ptr + 1])})`;
              case 146 /* f32_add */:
              case 160 /* f64_add */:
                return `${emit(ast[ptr + 1])}+${emit(ast[ptr + 2])}`;
              case 147 /* f32_sub */:
              case 161 /* f64_sub */:
                return `${emit(ast[ptr + 1])}-${emit(ast[ptr + 2])}`;
              case 148 /* f32_mul */:
              case 162 /* f64_mul */:
                return `${emit(ast[ptr + 1])}*${emit(ast[ptr + 2])}`;
              case 149 /* f32_div */:
              case 163 /* f64_div */:
                return `${emit(ast[ptr + 1])}/${emit(ast[ptr + 2])}`;
              case 150 /* f32_min */:
              case 164 /* f64_min */:
                return `Math.min(${emit(ast[ptr + 1])},${emit(ast[ptr + 2])})`;
              case 151 /* f32_max */:
              case 165 /* f64_max */:
                return `Math.max(${emit(ast[ptr + 1])},${emit(ast[ptr + 2])})`;
              case 152 /* f32_copysign */:
              case 166 /* f64_copysign */:
                return `l.${/* @__KEY__ */ "N"}(${emit(ast[ptr + 1])},${emit(ast[ptr + 2])})`;
              case 167 /* i32_wrap_i64 */:
                return `Number(${emit(ast[ptr + 1])}&0xFFFFFFFFn)|0`;
              case 168 /* i32_trunc_f32_s */:
              case 169 /* i32_trunc_f32_u */:
              case 170 /* i32_trunc_f64_s */:
              case 171 /* i32_trunc_f64_u */:
                return `Math.trunc(${emit(ast[ptr + 1])})|0`;
              case 172 /* i64_extend_i32_s */:
                return `BigInt(${emit(ast[ptr + 1])})`;
              case 173 /* i64_extend_i32_u */:
                return `BigInt(${emit(ast[ptr + 1])}>>>0)`;
              case 174 /* i64_trunc_f32_s */:
              case 175 /* i64_trunc_f32_u */:
              case 176 /* i64_trunc_f64_s */:
              case 177 /* i64_trunc_f64_u */:
                return `BigInt(Math.trunc(${emit(ast[ptr + 1])}))&0xFFFFFFFFFFFFFFFFn`;
              case 180 /* f32_convert_i64_s */:
              case 181 /* f32_convert_i64_u */:
              case 186 /* f64_convert_i64_u */:
              case 185 /* f64_convert_i64_s */:
                return `Number(${emit(ast[ptr + 1])})`;
              case 188 /* i32_reinterpret_f32 */:
                return `l.${/* @__KEY__ */ "O"}(${emit(ast[ptr + 1])})`;
              case 189 /* i64_reinterpret_f64 */:
                return `l.${/* @__KEY__ */ "Q"}(${emit(ast[ptr + 1])})`;
              case 190 /* f32_reinterpret_i32 */:
                return `l.${/* @__KEY__ */ "P"}(${emit(ast[ptr + 1])})`;
              case 191 /* f64_reinterpret_i64 */:
                return `l.${/* @__KEY__ */ "R"}(${emit(ast[ptr + 1])})`;
              case 192 /* i32_extend8_s */:
                return `${emit(ast[ptr + 1])}<<24>>24`;
              case 193 /* i32_extend16_s */:
                return `${emit(ast[ptr + 1])}<<16>>16`;
              case 194 /* i64_extend8_s */:
                return `l.${/* @__KEY__ */ "$"}(${emit(ast[ptr + 1])})`;
              case 195 /* i64_extend16_s */:
                return `l.${/* @__KEY__ */ "aa"}(${emit(ast[ptr + 1])})`;
              case 196 /* i64_extend32_s */:
                return `l.${/* @__KEY__ */ "ba"}(${emit(ast[ptr + 1])})`;
              case 208 /* ref_null */:
                return "null";
              case 209 /* ref_is_null */:
                return `${emit(ast[ptr + 1])}===null`;
              case 210 /* ref_func */:
                return `F(${ast[ptr + 1]})`;
              case 64512 /* i32_trunc_sat_f32_s */:
                return `l.${/* @__KEY__ */ "z"}(${emit(ast[ptr + 1])})`;
              case 64513 /* i32_trunc_sat_f32_u */:
                return `l.${/* @__KEY__ */ "A"}(${emit(ast[ptr + 1])})`;
              case 64514 /* i32_trunc_sat_f64_s */:
                return `l.${/* @__KEY__ */ "z"}(${emit(ast[ptr + 1])})`;
              case 64515 /* i32_trunc_sat_f64_u */:
                return `l.${/* @__KEY__ */ "A"}(${emit(ast[ptr + 1])})`;
              case 64516 /* i64_trunc_sat_f32_s */:
                return `l.${/* @__KEY__ */ "B"}(${emit(ast[ptr + 1])})`;
              case 64517 /* i64_trunc_sat_f32_u */:
                return `l.${/* @__KEY__ */ "C"}(${emit(ast[ptr + 1])})`;
              case 64518 /* i64_trunc_sat_f64_s */:
                return `l.${/* @__KEY__ */ "B"}(${emit(ast[ptr + 1])})`;
              case 64519 /* i64_trunc_sat_f64_u */:
                return `l.${/* @__KEY__ */ "C"}(${emit(ast[ptr + 1])})`;
              case 64520 /* memory_init */:
                return `l.${/* @__KEY__ */ "D"}(d[${ast[ptr + 4]}],c.${/* @__KEY__ */ "e" + ast[ptr + 5]},${emit(ast[ptr + 1])},${emit(ast[ptr + 2])},${emit(ast[ptr + 3])})`;
              case 64521 /* data_drop */:
                return `d[${ast[ptr + 1]}]=new Uint8Array`;
              case 64522 /* memory_copy */:
                return `l.${/* @__KEY__ */ "D"}(c.${/* @__KEY__ */ "e" + ast[ptr + 4]},c.${/* @__KEY__ */ "e" + ast[ptr + 5]},${emit(ast[ptr + 1])},${emit(ast[ptr + 2])},${emit(ast[ptr + 3])})`;
              case 64523 /* memory_fill */:
                return `c.${/* @__KEY__ */ "e" + ast[ptr + 4]}.fill(${emit(ast[ptr + 1])},T=${emit(ast[ptr + 2])},T+${emit(ast[ptr + 3])})`;
              case 64524 /* table_init */:
                return `l.${/* @__KEY__ */ "E"}(${tableName(ast[ptr + 4])},e[${ast[ptr + 5]}],${emit(ast[ptr + 1])},${emit(ast[ptr + 2])},${emit(ast[ptr + 3])})`;
              case 64525 /* elem_drop */:
                return `e[${ast[ptr + 1]}]=[]`;
              case 64526 /* table_copy */:
                return `l.${/* @__KEY__ */ "E"}(${tableName(ast[ptr + 4])},${tableName(ast[ptr + 5])},${emit(ast[ptr + 1])},${emit(ast[ptr + 2])},${emit(ast[ptr + 3])})`;
              case 64527 /* table_grow */:
                return `l.${/* @__KEY__ */ "F"}(${tableName(ast[ptr + 3])},${emit(ast[ptr + 1])},${emit(ast[ptr + 2])})`;
              case 64528 /* table_size */:
                return tableName(ast[ptr + 1]) + ".length";
              case 64529 /* table_fill */:
                return `l.${/* @__KEY__ */ "da"}(${tableName(ast[ptr + 4])},${emit(ast[ptr + 1])},${emit(ast[ptr + 2])},${emit(ast[ptr + 3])})`;
              default:
                throw "Internal error";
            }
          };
          const allocateNode = (node, length) => {
            const ptr = astNextPtr;
            ast[ptr] = node;
            astNextPtr += length;
            return ptr;
          };
          const pushUnary = (op, stackSlot = stackTop) => {
            astPtrs.push(astNextPtr);
            ast[astNextPtr++] = op | 1 << 16 /* ChildCountShift */ | stackSlot << 24 /* OutSlotShift */;
            ast[astNextPtr++] = -stackSlot;
          };
          const handleReturn = () => {
            finalizeBasicBlock();
            jump(0);
            blocks[blocks.length - 1].c = true;
          };
          const finalizeBasicBlock = (popStackTop = false) => {
            const parts = [];
            let i = astPtrs.length - 1;
            const optimizeChildrenAndSelf = (ptr2) => {
              const node = ast[ptr2];
              const op = node & 65535 /* OpMask */;
              const childCount = node >> 16 /* ChildCountShift */ & 255 /* ChildCountMask */;
              const usesTypedArrays = op >= 40 /* i32_load */ && op <= 62 /* i64_store32 */ || op >= 64520 /* memory_init */ && op <= 64523 /* memory_fill */;
              for (let j = childCount - 1; i >= 0 && j >= 0; j--) {
                const stackSlot = -ast[ptr2 + j + 1];
                let didSkip = false;
                for (let k = i; k >= 0; k--) {
                  const prevPtr = astPtrs[k];
                  if (prevPtr === null) continue;
                  const prevNode = ast[prevPtr];
                  const prevOp = prevNode & 65535 /* OpMask */;
                  if (usesTypedArrays && // The only exception we make is for nodes that are trivially safe,
                  // which include terminal nodes without any children that don't
                  // have side effects. The common ones are special-cased below.
                  (prevOp < 65 /* i32_const */ || prevOp > 66 /* i64_const */) && prevOp != 32 /* local_get */) {
                    break;
                  }
                  if (prevNode >>> 24 /* OutSlotShift */ === stackSlot) {
                    astPtrs[k] = null;
                    if (!didSkip) i = k - 1;
                    ast[ptr2 + j + 1] = optimizeChildrenAndSelf(prevPtr);
                    break;
                  }
                  if (prevOp !== 243 /* TO_U32 */ && prevOp !== 244 /* TO_S64 */) break;
                  didSkip = true;
                }
              }
              return optimizeNode(ast, constants, allocateNode, ptr2);
            };
            let ptr;
            while (i >= 0) {
              const index = i--;
              if ((ptr = astPtrs[index]) !== null) {
                astPtrs[index] = optimizeChildrenAndSelf(ptr);
              }
            }
            let result;
            i = astPtrs.length - 1;
            if (popStackTop) {
              if (i >= 0 && (ptr = astPtrs[i]) !== null && ast[ptr] >>> 24 /* OutSlotShift */ === stackTop) {
                result = emitUnwrapped(ptr);
                i--;
              } else {
                result = "s" + stackTop;
              }
              stackTop--;
            }
            while (i >= 0) {
              if ((ptr = astPtrs[i--]) !== null) {
                const stackSlot = ast[ptr] >>> 24 /* OutSlotShift */;
                parts.push(`${stackSlot ? stackSlotName(stackSlot) + "=" : ""}${emitUnwrapped(ptr)};`);
              }
            }
            body += parts.reverse().join("");
            constants.length = 0;
            astPtrs.length = 0;
            astNextPtr = 0;
            return result;
          };
          const {
            ia: bytes,
            h: dataView,
            H: codeSection,
            I: functionSection,
            pa: nameSection,
            J: typeSection
          } = wasm;
          const [argTypes, returnTypes] = typeSection[functionSection[codeIndex]];
          const [locals, codeStart, codeEnd] = codeSection[codeIndex];
          const names = [];
          const argCount = argTypes.length;
          for (let i = 0; i < argCount; i++) {
            names.push("a" + i);
          }
          const decls = ["L", "T"];
          for (const [count, type] of locals) {
            for (let i = 0; i < count; i++) {
              const name2 = "l" + decls.length;
              names.push(name2);
              decls.push(name2 + (type === 126 /* I64 */ ? "=0n" : "=0"));
            }
          }
          const blockDepthLimit = 256;
          const pushBlock = (kind) => {
            const isBelowLimit = blocks.length < blockDepthLimit;
            if (isBelowLimit) {
              body += `b${blocks.length}:`;
            } else if (blocks.length === blockDepthLimit) {
              body += `L=1;b${blocks.length}:for(;;){switch(L){case 1:`;
              nextLabel = 2;
            }
            const labelBreak = isBelowLimit ? -1 : nextLabel++;
            const labelContinueOrElse = isBelowLimit ? -1 : kind !== 0 /* Normal */ ? nextLabel++ : 0;
            const [argCount2, returnCount] = readBlockType();
            blocks.push({
              l: argCount2,
              c: false,
              m: kind,
              x: labelBreak,
              j: labelContinueOrElse,
              i: stackTop - argCount2,
              g: returnCount
            });
            return labelContinueOrElse;
          };
          const jump = (index = blocks.length - readU32LEB() - 1) => {
            if (blocks[blocks.length - 1].c) return;
            const block = blocks[index];
            if (!index) {
              if (block.g === 1) {
                body += `return s${stackTop};`;
              } else if (block.g > 1) {
                const values = [];
                for (let i = block.g - 1; i >= 0; i--) values.push("s" + (stackTop - i));
                body += `return[${values}];`;
              } else {
                body += `return;`;
              }
            } else if (block.m === 1 /* Loop */) {
              if (stackTop > block.i + block.l) {
                for (let i = 1; i <= block.l; i++) {
                  body += `s${block.i + i}=s${stackTop - block.l + i};`;
                }
              }
              body += index < blockDepthLimit ? `continue b${index};` : `L=${block.j};continue;`;
            } else {
              if (stackTop > block.i + block.g) {
                for (let i = 1; i <= block.g; i++) {
                  body += `s${block.i + i}=s${stackTop - block.g + i};`;
                }
              }
              body += index <= blockDepthLimit ? `break b${index};` : `L=${block.x};continue;`;
            }
          };
          const blocks = [{
            l: 0,
            c: false,
            m: 0 /* Normal */,
            x: -1,
            j: -1,
            i: 0,
            g: returnTypes.length
          }];
          const handleSimpleOp = (op) => {
            const flags = metaTable[op] | 0;
            if (!(flags & 8 /* Simple */)) return false;
            if (flags & 8 /* Simple */) {
              if (!blocks[blocks.length - 1].c) {
                const childCount = flags & 3 /* PopMask */;
                if (flags & 1024 /* And63 */) {
                  astPtrs.push(astNextPtr);
                  ast[astNextPtr++] = 66 /* i64_const */ | stackTop + 1 << 24 /* OutSlotShift */;
                  ast[astNextPtr++] = constants.length;
                  constants.push(63n);
                  astPtrs.push(astNextPtr);
                  ast[astNextPtr++] = 131 /* i64_and */ | 2 << 16 /* ChildCountShift */ | stackTop << 24 /* OutSlotShift */;
                  ast[astNextPtr++] = -stackTop;
                  ast[astNextPtr++] = -(stackTop + 1);
                }
                stackTop -= childCount;
                if (flags & (128 /* ToU32 */ | 256 /* ToS64 */)) {
                  for (let i = 0; i < childCount; i++) {
                    pushUnary(flags & 128 /* ToU32 */ ? 243 /* TO_U32 */ : 244 /* TO_S64 */, stackTop + i + 1);
                  }
                }
                if (!(flags & 512 /* Omit */)) {
                  let memoryIndex = 0;
                  if (flags & 32 /* HasMemory */ && bytes[bytesPtr++] & 64) memoryIndex = readU32LEB();
                  astPtrs.push(astNextPtr);
                  if (flags & 4 /* Push */) op |= stackTop + 1 << 24 /* OutSlotShift */;
                  ast[astNextPtr++] = op | childCount << 16 /* ChildCountShift */;
                  for (let i = 1; i <= childCount; i++) ast[astNextPtr++] = -(stackTop + i);
                  if (flags & 16 /* HasIndex */) ast[astNextPtr++] = readU32LEB();
                  if (flags & 32 /* HasMemory */) ast[astNextPtr++] = memoryIndex;
                }
                if (flags & 4 /* Push */) stackTop++;
                if (flags & 64 /* BoolToInt */) pushUnary(242 /* BOOL_TO_INT */);
              } else {
                if (flags & 32 /* HasMemory */ && bytes[bytesPtr++] & 64) readU32LEB();
                if (flags & 16 /* HasIndex */) readU32LEB();
              }
            }
            return true;
          };
          let stackTop = 0;
          let bytesPtr = codeStart;
          let nextLabel = 0;
          let body = "b0:{";
          while (bytesPtr < codeEnd) {
            let op = bytes[bytesPtr++];
            if (handleSimpleOp(op)) {
              continue;
            }
            switch (op) {
              case 0 /* unreachable */: {
                const block = blocks[blocks.length - 1];
                finalizeBasicBlock();
                if (!block.c) {
                  body += '"unreachable"();';
                  block.c = true;
                }
                break;
              }
              case 2 /* block */:
                finalizeBasicBlock();
                if (pushBlock(0 /* Normal */) < 0) body += "{";
                break;
              case 3 /* loop */: {
                finalizeBasicBlock();
                const label = pushBlock(1 /* Loop */);
                body += label < 0 ? "for(;;){" : `case ${label}:`;
                break;
              }
              case 4 /* if */: {
                if (!blocks[blocks.length - 1].c) {
                  pushUnary(blocks.length < blockDepthLimit ? 240 /* BOOL */ : 241 /* BOOL_NOT */);
                }
                const test = finalizeBasicBlock(true);
                const label = pushBlock(2 /* IfElse */);
                body += label < 0 ? `if(${test}){` : `if(${test}){L=${label};continue}`;
                break;
              }
              case 5 /* else */: {
                finalizeBasicBlock();
                const index = blocks.length - 1, block = blocks[index];
                jump(index);
                body += index < blockDepthLimit ? "}else{" : `case ${block.j}:`;
                block.m = 0 /* Normal */;
                stackTop = block.i + block.l;
                block.c = false;
                break;
              }
              case 11 /* end */: {
                finalizeBasicBlock();
                const index = blocks.length - 1, block = blocks[index];
                if (block.m !== 2 /* IfElse */) block.j = 0;
                block.m = 0 /* Normal */;
                jump(index);
                if (index < blockDepthLimit) {
                  body += `}`;
                } else {
                  if (block.j) body += `case ${block.j}:`;
                  body += `case ${block.x}:`;
                  if (index == blockDepthLimit) body += `}break}`;
                }
                stackTop = block.i + block.g;
                blocks.pop();
                break;
              }
              case 12 /* br */:
                finalizeBasicBlock();
                jump();
                blocks[blocks.length - 1].c = true;
                break;
              case 13 /* br_if */: {
                if (!blocks[blocks.length - 1].c) pushUnary(240 /* BOOL */);
                const test = finalizeBasicBlock(true);
                body += `if(${test}){`;
                jump();
                body += "}";
                break;
              }
              case 14 /* br_table */: {
                const test = finalizeBasicBlock(true);
                body += `switch(${test}){`;
                for (let i = 0, tableCount = readU32LEB(); i < tableCount; i++) {
                  body += `case ${i}:`;
                  jump();
                }
                body += "default:";
                jump();
                body += "}";
                blocks[blocks.length - 1].c = true;
                break;
              }
              case 15 /* return */:
                handleReturn();
                break;
              case 16 /* call */:
              case 18 /* return_call */: {
                const needsReturn = op === 18 /* return_call */;
                const funcIndex2 = readU32LEB();
                if (!blocks[blocks.length - 1].c) {
                  const [argTypes2, returnTypes2] = funcTypes[funcIndex2];
                  stackTop -= argTypes2.length;
                  astPtrs.push(astNextPtr);
                  if (returnTypes2.length === 1) op |= stackTop + 1 << 24 /* OutSlotShift */;
                  ast[astNextPtr++] = op | argTypes2.length << 16 /* ChildCountShift */;
                  for (let i = 1; i <= argTypes2.length; i++) ast[astNextPtr++] = -(stackTop + i);
                  ast[astNextPtr++] = funcIndex2;
                  if (returnTypes2.length > 1) ast[astNextPtr++] = stackTop + 1;
                  stackTop += returnTypes2.length;
                }
                if (needsReturn) handleReturn();
                break;
              }
              case 17 /* call_indirect */:
              case 19 /* return_call_indirect */: {
                const needsReturn = op === 19 /* return_call_indirect */;
                const typeIndex = readU32LEB();
                const tableIndex = readU32LEB();
                if (!blocks[blocks.length - 1].c) {
                  const [argTypes2, returnTypes2] = typeSection[typeIndex];
                  stackTop -= argTypes2.length + 1;
                  astPtrs.push(astNextPtr);
                  if (returnTypes2.length === 1) op |= stackTop + 1 << 24 /* OutSlotShift */;
                  ast[astNextPtr++] = op | argTypes2.length << 16 /* ChildCountShift */;
                  ast[astNextPtr++] = -(stackTop + argTypes2.length + 1);
                  for (let i = 1; i <= argTypes2.length; i++) ast[astNextPtr++] = -(stackTop + i);
                  ast[astNextPtr++] = tableIndex;
                  ast[astNextPtr++] = typeIndex;
                  if (returnTypes2.length > 1) ast[astNextPtr++] = stackTop + 1;
                  stackTop += returnTypes2.length;
                }
                if (needsReturn) handleReturn();
                break;
              }
              case 27 /* select */:
              case 28 /* select_type */: {
                if (op === 28 /* select_type */) {
                  const count = readU32LEB();
                  if (count !== 1) throw Error("Unsupported select type count " + count);
                  bytesPtr++;
                }
                if (!blocks[blocks.length - 1].c) {
                  pushUnary(240 /* BOOL */);
                  stackTop -= 2;
                  astPtrs.push(astNextPtr);
                  ast[astNextPtr++] = op | 3 << 16 /* ChildCountShift */ | stackTop << 24 /* OutSlotShift */;
                  ast[astNextPtr++] = -(stackTop + 2);
                  ast[astNextPtr++] = -stackTop;
                  ast[astNextPtr++] = -(stackTop + 1);
                }
                break;
              }
              case 65 /* i32_const */:
                if (!blocks[blocks.length - 1].c) {
                  astPtrs.push(astNextPtr);
                  ast[astNextPtr++] = op | ++stackTop << 24 /* OutSlotShift */;
                  ast[astNextPtr++] = readI32LEB();
                } else {
                  readI32LEB();
                }
                break;
              case 66 /* i64_const */:
                if (!blocks[blocks.length - 1].c) {
                  astPtrs.push(astNextPtr);
                  ast[astNextPtr++] = op | ++stackTop << 24 /* OutSlotShift */;
                  ast[astNextPtr++] = constants.length;
                  constants.push(readI64LEB());
                } else {
                  readI64LEB();
                }
                break;
              case 67 /* f32_const */:
                if (!blocks[blocks.length - 1].c) {
                  astPtrs.push(astNextPtr);
                  ast[astNextPtr++] = op | ++stackTop << 24 /* OutSlotShift */;
                  ast[astNextPtr++] = bytesPtr;
                }
                bytesPtr += 4;
                break;
              case 68 /* f64_const */:
                if (!blocks[blocks.length - 1].c) {
                  astPtrs.push(astNextPtr);
                  ast[astNextPtr++] = op | ++stackTop << 24 /* OutSlotShift */;
                  ast[astNextPtr++] = bytesPtr;
                }
                bytesPtr += 8;
                break;
              case 208 /* ref_null */:
                bytesPtr++;
                if (!blocks[blocks.length - 1].c) {
                  astPtrs.push(astNextPtr);
                  ast[astNextPtr++] = op | ++stackTop << 24 /* OutSlotShift */;
                }
                break;
              case 252:
                op = 64512 | bytes[bytesPtr++];
                if (handleSimpleOp(op)) {
                  continue;
                }
                switch (op) {
                  case 64520 /* memory_init */: {
                    const dataIndex = readU32LEB();
                    const destinationIndex = readU32LEB();
                    if (!blocks[blocks.length - 1].c) {
                      stackTop -= 2;
                      astPtrs.push(astNextPtr);
                      ast[astNextPtr++] = op | 3 << 16 /* ChildCountShift */ | stackTop << 24 /* OutSlotShift */;
                      ast[astNextPtr++] = -stackTop;
                      ast[astNextPtr++] = -(stackTop + 1);
                      ast[astNextPtr++] = -(stackTop + 2);
                      ast[astNextPtr++] = dataIndex;
                      ast[astNextPtr++] = destinationIndex;
                    }
                    break;
                  }
                  case 64522 /* memory_copy */: {
                    const destinationIndex = readU32LEB();
                    const sourceIndex = readU32LEB();
                    if (!blocks[blocks.length - 1].c) {
                      stackTop -= 2;
                      astPtrs.push(astNextPtr);
                      ast[astNextPtr++] = op | 3 << 16 /* ChildCountShift */ | stackTop << 24 /* OutSlotShift */;
                      ast[astNextPtr++] = -stackTop;
                      ast[astNextPtr++] = -(stackTop + 1);
                      ast[astNextPtr++] = -(stackTop + 2);
                      ast[astNextPtr++] = sourceIndex;
                      ast[astNextPtr++] = destinationIndex;
                    }
                    break;
                  }
                  case 64523 /* memory_fill */: {
                    const destinationIndex = readU32LEB();
                    if (!blocks[blocks.length - 1].c) {
                      stackTop -= 2;
                      astPtrs.push(astNextPtr);
                      ast[astNextPtr++] = op | 3 << 16 /* ChildCountShift */ | stackTop << 24 /* OutSlotShift */;
                      ast[astNextPtr++] = -(stackTop + 1);
                      ast[astNextPtr++] = -stackTop;
                      ast[astNextPtr++] = -(stackTop + 2);
                      ast[astNextPtr++] = destinationIndex;
                    }
                    break;
                  }
                  case 64524 /* table_init */: {
                    const elementIndex = readU32LEB();
                    const tableIndex = readU32LEB();
                    if (!blocks[blocks.length - 1].c) {
                      stackTop -= 2;
                      astPtrs.push(astNextPtr);
                      ast[astNextPtr++] = op | 3 << 16 /* ChildCountShift */ | stackTop << 24 /* OutSlotShift */;
                      ast[astNextPtr++] = -stackTop;
                      ast[astNextPtr++] = -(stackTop + 1);
                      ast[astNextPtr++] = -(stackTop + 2);
                      ast[astNextPtr++] = tableIndex;
                      ast[astNextPtr++] = elementIndex;
                    }
                    break;
                  }
                  case 64526 /* table_copy */: {
                    const destination = readU32LEB();
                    const source = readU32LEB();
                    if (!blocks[blocks.length - 1].c) {
                      stackTop -= 2;
                      astPtrs.push(astNextPtr);
                      ast[astNextPtr++] = op | 3 << 16 /* ChildCountShift */ | stackTop << 24 /* OutSlotShift */;
                      ast[astNextPtr++] = -stackTop;
                      ast[astNextPtr++] = -(stackTop + 1);
                      ast[astNextPtr++] = -(stackTop + 2);
                      ast[astNextPtr++] = destination;
                      ast[astNextPtr++] = source;
                    }
                    break;
                  }
                  default:
                    throw Error("Unsupported instruction: 0xFC " + formatHexByte(op & 255));
                }
                break;
              default:
                throw Error("Unsupported instruction: " + formatHexByte(op));
            }
          }
          if (stackLimit > 255) throw Error("Deep stacks are not supported");
          const name = JSON.stringify("wasm:" + (nameSection.get(funcIndex) || `function[${codeIndex}]`));
          const js = `return{${name}(${names.slice(0, argCount)}){var ${decls};${body}}}[${name}]`;
          return new Function("f", "F", "c", "t", "d", "e", "g", "l", js)(
            funcs,
            createLazyFunc,
            context,
            tables,
            dataSegments,
            elementSegments,
            globals,
            library
          );
        };

        // src/instantiate.ts
        var Global = class {
          valueOf() {
            return this.value;
          }
        };
        var compileImportFunc = (funcType, value) => {
          const [argTypes, returnTypes] = funcType;
          const argNames = [];
          const argExprs = [];
          for (let i = 0; i < argTypes.length; i++) {
            argNames.push("a" + i);
            argExprs.push(castToJS("a" + i, argTypes[i]));
          }
          let result = `f(${argExprs})`;
          if (returnTypes.length === 1) {
            result = "return " + castToWASM(result, returnTypes[0]);
          } else if (returnTypes.length > 1) {
            result = `let r=${result};`;
            for (let i = 0; i < returnTypes.length; i++) result += `r[${i}]=${castToWASM(`r[${i}]`, returnTypes[i])};`;
            result += "return r";
          }
          return new Function("f", "l", `return(${argNames})=>{${result}}`)(value, library);
        };
        var Instance = class {
          constructor(module, importObject) {
            const wasm = moduleMap.get(module);
            const {
              H: codeSection,
              ja: dataSection,
              ka: elementSection,
              la: exportSection,
              I: functionSection,
              ma: globalSection,
              na: importSection,
              oa: memorySection,
              qa: startSection,
              ra: tableSection,
              J: typeSection
            } = wasm;
            const exports = this.exports = /* @__PURE__ */ Object.create(null);
            const memories = [];
            const funcs = [];
            const funcTypes = [];
            const globals = [];
            const globalTypes = [];
            const lazyFuncs = {};
            const tables = [];
            const createLazyFunc = (index) => {
              const obj = lazyFuncs[index] || (lazyFuncs[index] = {
                ua: index,
                fa: funcTypes[index],
                t: null,
                u: (...args) => {
                  const result = funcs[index](...args);
                  obj.u = funcs[index];
                  return result;
                }
              });
              return obj;
            };
            for (const tuple of importSection) {
              const [module2, name, desc, payload] = tuple;
              const value = importObject[module2][name];
              if (desc === 0 /* Func */) {
                const funcType = typeSection[payload];
                const index = funcs.length;
                funcs.push((...args) => {
                  return (funcs[index] = compileImportFunc(funcType, value))(...args);
                });
                funcTypes.push(funcType);
              } else if (desc === 1 /* Table */) {
                tables.push(tableRegistry.get(value));
              } else if (desc === 2 /* Mem */) {
                memories.push(memoryRegistry.get(value));
              } else if (desc === 3 /* Global */) {
                globals.push(liveCastToWASM(value, payload));
                globalTypes.push(payload);
              } else {
                throw Error(`Unsupported import type ${formatHexByte(desc)} for "${module2}"."${name}"`);
              }
            }
            const context = {};
            for (const [initial, maximum] of memorySection) {
              memories.push(memoryRegistry.get(new Memory({ initial, maximum: initial > maximum ? initial : maximum })));
            }
            for (let i = 0; i < memories.length; i++) {
              const memory = memories[i];
              const patch = () => {
                context[/* @__KEY__ */ "e" + i] = memory.e;
                context[/* @__KEY__ */ "k" + i] = memory.k;
                context[/* @__KEY__ */ "h" + i] = memory.h;
              };
              context[/* @__KEY__ */ "K" + i] = memory;
              memory.M.push(patch);
              patch();
            }
            for (const [type, mutable, initializer] of globalSection) {
              globals.push(initializer(globals, createLazyFunc));
              globalTypes.push(type);
            }
            const dataSegments = [];
            for (let [index, initializer, data] of dataSection) {
              if (initializer !== null) {
                context[/* @__KEY__ */ "e" + index].set(data, initializer(globals));
                data = new Uint8Array();
              }
              dataSegments.push(data);
            }
            for (let i = 0; i < codeSection.length; i++) {
              const index = funcs.length;
              funcTypes.push(typeSection[functionSection[i]]);
              funcs.push((...args) => {
                return (funcs[index] = compileCode(
                  funcs,
                  funcTypes,
                  createLazyFunc,
                  tables,
                  dataSegments,
                  elementSegments,
                  globals,
                  context,
                  wasm,
                  i,
                  index
                ))(...args);
              });
            }
            const elementSegments = [];
            for (const [type, initial, maximum] of tableSection) {
              if (type !== 112 /* FuncRef */ && type !== 111 /* ExternRef */) throw Error("Unsupported element type: " + formatHexByte(type));
              tables.push(tableRegistry.get(new Table({
                element: type === 111 /* ExternRef */ ? "externref" : "anyfunc",
                initial,
                maximum: initial > maximum ? initial : maximum
              })));
            }
            for (let [tableIndex, initializer, indices] of elementSection) {
              const segment = [];
              for (const index of indices) segment.push(index === null ? null : createLazyFunc(index));
              elementSegments.push(segment);
              if (tableIndex !== null && initializer !== null) {
                const table = tables[tableIndex];
                let offset = initializer(globals);
                for (const value of segment) table[offset++] = value;
              }
            }
            for (const [name, desc, index] of exportSection) {
              if (desc === 0 /* Func */) {
                exports[name] = library.s(createLazyFunc(index));
              } else if (desc === 1 /* Table */) {
                exports[name] = tables[index].y;
              } else if (desc === 2 /* Mem */) {
                exports[name] = memories[index].y;
              } else if (desc === 3 /* Global */) {
                const value = new Global();
                const type = globalTypes[index];
                Object.defineProperty(value, "value", {
                  get: () => globals[index],
                  set: (x) => {
                    globals[index] = liveCastToWASM(x, type);
                  }
                });
                exports[name] = value;
              } else {
                throw Error(`Unsupported export type ${formatHexByte(desc)} for "${name}"`);
              }
            }
            if (startSection >= 0) funcs[startSection]();
          }
        };
        var memoryRegistry = /* @__PURE__ */ new WeakMap();
        var clampPageCount = (x) => Math.max(-1, Math.min(x, 65535)) | 0;
        var Memory = class {
          constructor({ initial, maximum }) {
            initial = clampPageCount(initial);
            maximum = clampPageCount(maximum ?? Infinity);
            if (initial < 0 || initial > maximum) throw RangeError();
            const initialBuffer = new ArrayBuffer(initial << 16);
            const internal = {
              y: this,
              o: initialBuffer,
              e: new Uint8Array(initialBuffer),
              k: new Int8Array(initialBuffer),
              h: new DataView(initialBuffer),
              n: initial,
              sa: maximum,
              M: [],
              L(pageDelta) {
                const oldPageCount = this.n;
                const oldBytes = this.e;
                pageDelta = clampPageCount(pageDelta);
                if (pageDelta < 0 || this.n + pageDelta > this.sa) return -1;
                if (!pageDelta) return oldPageCount;
                const newBuffer = new ArrayBuffer((this.n += pageDelta) << 16);
                const newBytes = new Uint8Array(newBuffer);
                newBytes.set(oldBytes);
                try {
                  structuredClone(this.o, { transfer: [this.o] });
                } catch {
                }
                this.o = newBuffer;
                this.e = newBytes;
                this.k = new Int8Array(newBuffer);
                this.h = new DataView(newBuffer);
                for (const patch of this.M) patch();
                return oldPageCount;
              }
            };
            memoryRegistry.set(this, internal);
            Object.defineProperty(this, "buffer", {
              get: () => internal.o
            });
            this.grow = (pageDelta) => {
              const pageCount = internal.L(pageDelta);
              if (pageCount < 0) throw RangeError();
              return pageCount;
            };
          }
        };
        var tableRegistry = /* @__PURE__ */ new WeakMap();
        var Table = class {
          constructor({ element, initial, maximum }) {
            const isAnyFunc = element == "anyfunc";
            const internal = [];
            if (!isAnyFunc && element !== "externref") throw TypeError();
            internal.y = this;
            internal.ca = Math.min(4294967295, maximum ?? Infinity);
            internal.length = initial;
            for (let i = 0; i < initial; i++) internal[i] = null;
            tableRegistry.set(this, internal);
            Object.defineProperty(this, "length", {
              get: () => internal.length
            });
            this.get = (i) => {
              i >>>= 0;
              if (i >= internal.length) throw RangeError();
              return isAnyFunc ? library.s(internal[i]) : internal[i];
            };
            this.set = (i, value) => {
              i >>>= 0;
              if (i >= internal.length) throw RangeError();
              internal[i] = isAnyFunc ? library.r(value) : value;
            };
            this.grow = (delta, value) => {
              const oldLength = library.F(internal, isAnyFunc ? library.r(value) : value, delta);
              if (oldLength < 0) throw RangeError();
              return oldLength;
            };
          }
        };

        // src/index.ts
        var compile = async (input) => {
          return new Module(input);
        };
        var compileStreaming = async (source) => {
          return new Module(await (await source).arrayBuffer());
        };
        var instantiate = async (input, importObject) => {
          if (input instanceof Module) return new Instance(input, importObject);
          const module = new Module(input);
          return { module, instance: new Instance(module, importObject) };
        };
        var instantiateStreaming = async (source, importObject) => {
          const module = new Module(await (await source).arrayBuffer());
          return { module, instance: new Instance(module, importObject) };
        };
        var validate = (input) => {
          if (!ArrayBuffer.isView(input) && !(input instanceof ArrayBuffer)) {
            throw TypeError("Invalid buffer source");
          }
          try {
            new Module(input);
            return true;
          } catch {
            return false;
          }
        };
        var wasmAPI = {
          Global,
          Instance,
          compile,
          compileStreaming,
          instantiate,
          instantiateStreaming,
          validate,
          Memory,
          Module,
          Table,
          // This cast ignores the lack of a call signature without "new", which we don't support
          CompileError
        };
        /* ---------------------------------------------------------------- polywasm sfarsit */
        return wasmAPI;
    }

    var api = null;

    function fa() {
        if (api)
            return api;
        /* fara new Function (CSP fara 'unsafe-eval') polywasm nu poate porni: WebAssembly ramane lipsa */
        new Function("");
        api = polywasm();
        /* erorile pe care polywasm nu le are, cu numele celor native */
        ["LinkError", "RuntimeError"].forEach(function (nume) {
            if (typeof api[nume] === "function")
                return;
            var E = function (mesaj) {
                var e = new Error(mesaj);
                Object.setPrototypeOf(e, E.prototype);
                return e;
            };
            E.prototype = Object.create(Error.prototype, {
                constructor: { value: E, writable: true, configurable: true },
                name: { value: nume, writable: true, configurable: true }
            });
            Object.setPrototypeOf(E, Error);
            api[nume] = E;
        });
        try {
            Object.defineProperty(api, Symbol.toStringTag, { value: "WebAssembly", configurable: true });
        } catch (x) {
            /* nimic */
        }
        return api;
    }

    function pune(valoare) {
        Object.defineProperty(window, "WebAssembly", { value: valoare, writable: true, configurable: true,
            enumerable: false });
    }

    try {
        if (false) {
            pune(fa());
        } else {
            /* cand CSP-ul paginii (fara 'unsafe-eval') opreste new Function inca de aici, nu se pune nici getter-ul (deci nici
               "WebAssembly" in window nu e adevarat); altfel, de pilda CSP-ul din <meta>, il prinde fa() la prima atingere */
            new Function("");
            Object.defineProperty(window, "WebAssembly", {
                get: function () {
                    var w;
                    try {
                        w = fa();
                    } catch (x) {
                        delete window.WebAssembly;
                        return undefined;
                    }
                    pune(w);
                    return w;
                },
                set: function (v) {
                    pune(v);
                },
                configurable: true,
                enumerable: false
            });
        }
    } catch (x) {
        /* fara WebAssembly, ca inainte */
    }
})();

/* HBW1 (0.8.0; AS244, Lanus, Octagon SF8008, wedo tv de pe 13E): aplicatiile Lightning (Lightning.js) fara WebGL. Cand
 * navigatorul deseneaza pe procesor (fara GL: /etc/enigma2/hds-navigator-gl-cazut, placile fara EGL folosibil) WebKit nu
 * are WebGLRenderingContext, iar Lightning trece singur pe canvas2d. Daca setarile aplicatiei cer readPixelsAfterDraw sau
 * readPixelsBeforeDraw (wedo tv: true), Lightning cheama dupa fiecare cadru stage.gl.readPixels cu gl null:
 * "TypeError: null is not an object (evaluating 'gl.readPixels')", iar aplicatia ramane pe rotita. Fara WebGL optiunile
 * nu au ce citi, deci aici raman false: Stage._setOptions le scrie intr-un obiect gol si trec prin setterul de mai jos.
 * Cu WebGL nu se schimba nimic; numele sunt numai ale lui Lightning. Probat la Lanus (AS244: aplicatia pe ecran, filmele
 * pornesc), acolo numai pe hbbtv.amtecco.com; aici pentru orice pagina fara WebGL. */
(function () {
    try {
        if (window.WebGLRenderingContext)
            return;
    } catch (x) {
        /* fara WebGL */
    }
    ["readPixelsAfterDraw", "readPixelsBeforeDraw"].forEach(function (k) {
        try {
            Object.defineProperty(Object.prototype, k, { configurable: true, enumerable: false,
                get: function () { return undefined; },
                set: function () {
                    Object.defineProperty(this, k, { value: false, writable: true, enumerable: true, configurable: true });
                } });
        } catch (x) {
            /* nimic */
        }
    });
})();

/* HBW1 (AS244): plasa pentru wedo tv (hbbtv.amtecco.com), langa reparatia generala din bindToCurrentChannel. Splash-ul
 * aplicatiei pune pauza la 1,2 s si atunci cheama showHbbtvLoader(true); daca prima redare a fost oprita inainte (playerul
 * receptorului e unul singur), ascultatorul ramane si, dupa Home, rotita (#loader) ramane pentru totdeauna sub panza
 * Lightning, peste filme. Dupa window.homepageLoaded, showHbbtvLoader(true) (numai acel apel) e ignorat. Numai pe gazda
 * aplicatiei, fiindca numele sunt ale ei. */
(function () {
    var loc = typeof window !== "undefined" && window.location;
    if (!loc || !/(^|\.)amtecco\.com$/i.test(loc.hostname || "") || typeof setInterval !== "function")
        return;
    var n = 0;
    var t = setInterval(function () {
        n++;
        var f = window.showHbbtvLoader;
        if (typeof f === "function" && !f.__hdsHbw1) {
            var g = function (transparent) {
                if (transparent === true && window.homepageLoaded)
                    return;
                return f.apply(this, arguments);
            };
            g.__hdsHbw1 = true;
            window.showHbbtvLoader = g;
            clearInterval(t);
        } else if (n > 600) {
            clearInterval(t);
        }
    }, 100);
})();
