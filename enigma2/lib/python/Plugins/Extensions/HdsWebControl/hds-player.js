/* SPDX-License-Identifier: GPL-2.0-only
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 *
 * hds-player.js: playerul wasm al paginii "TV in browser", pentru canalele cu imagine MPEG-2 / MPEG-1 (SD) si sunet
 * MP2 / MP3 / AC-3, pe care browserele nu le redau singure. Il porneste playerul comun (player.js) in locul lui
 * mpegts.js, pe acelasi /api/tv-flux; receptorul trimite fluxul asa cum vine, fara recodare.
 *
 * Cum lucreaza: hds-worker.js (un Worker) citeste fluxul, il desface si il decodeaza cu decodorul wasm
 * (tv-wasm/hdsdec.wasm: libavcodec din FFmpeg 8.1.3, LGPL-2.1-or-later). Aici: imaginea pe un <canvas> cu WebGL
 * (YUV -> RGB in shader, desentrelasare "bob": fiecare camp devine o imagine, 50 de imagini/s din 25 de cadre
 * intretesute), raportul imaginii dupa SAR (4:3 sau 16:9) si dupa AFD, sunetul cu Web Audio (bucati programate dupa
 * PTS; merge si pe http, fara AudioWorklet). Ceasul comun e ceasul sunetului; fara sunet, ceasul paginii.
 * Pagina receptorului e http: nimic din ce cere context securizat (fara SharedArrayBuffer, WebCodecs, AudioWorklet).
 *
 * Folosire (player.js):
 *   var j = new HdsPlayerWasm(canvas, {antete: {...}, volum: 0.8, mut: false, program: sid, laEveniment: function(tip, date){}});
 *   j.porneste("/api/tv-flux");  j.pause(); j.play(); j.volume = 0.5; j.muted = true;  j.opreste();
 * Evenimente: "info" (fluxurile alese), "primul_cadru", "raport" (raportul imaginii aratate), "schimbare" (pauza,
 * volum, mut), "sunet_blocat" (browserul cere o apasare pentru sunet), "eroare" ({fel, cod, text}).
 */
(function (radacina) {
	"use strict";

	// primele 12 cifre din sha256 al tv-wasm/hdsdec.wasm: adresa decodorului se schimba odata cu el (cache o zi)
	var VERSIUNE_DECODOR = "099cf027855f";
	var COADA_MAX = 50;                       // cadre decodate in asteptare (2 s la 25 de cadre/s)
	var COADA_OCTETI_MAX = 48 * 1024 * 1024;
	var INAINTE_MAX = 90000 * 3;              // un cadru cu peste 3 s inaintea ceasului: ceasul se reia
	var ASTEPTARE_SUNET_MS = 1500;            // fara sunet atata dupa primul cadru: imaginea merge pe ceasul paginii

	// zona activa a cadrului dupa AFD (ETSI TS 101 154, anexa B), in coordonate 0..1 de la stanga sus, si raportul ei.
	// dar = raportul cadrului intreg (latimea * SAR / inaltimea). Codurile 8, 13, 14, 15 si lipsa: tot cadrul.
	function zonaActiva(afd, dar) {
		var tinta = null, sus = false;
		if (afd === 2) { tinta = 16 / 9; sus = true; }
		else if (afd === 3) { tinta = 14 / 9; sus = true; }
		else if (afd === 4 || afd === 10) tinta = 16 / 9;
		else if (afd === 9) tinta = 4 / 3;
		else if (afd === 11) tinta = 14 / 9;
		if (!tinta || !(dar > 0) || Math.abs(tinta - dar) < 0.01) return {x: 0, y: 0, l: 1, h: 1, raport: dar};
		if (tinta < dar) {
			var l = tinta / dar;
			return {x: (1 - l) / 2, y: 0, l: l, h: 1, raport: tinta};
		}
		var h = dar / tinta;
		return {x: 0, y: sus ? 0 : (1 - h) / 2, l: 1, h: h, raport: tinta};
	}

	// dreptunghiul imaginii in canvas (fara sa taie nimic, cu benzi negre): {x, y, l, h} in pixeli, y de jos (WebGL)
	function dreptunghi(raport, cw, ch) {
		if (!(raport > 0) || !cw || !ch) return {x: 0, y: 0, l: cw, h: ch};
		var l = cw, h = Math.round(cw / raport);
		if (h > ch) { h = ch; l = Math.round(ch * raport); }
		return {x: Math.floor((cw - l) / 2), y: Math.floor((ch - h) / 2), l: l, h: h};
	}

	// raportul cadrului: latimea * SAR / inaltimea; fara SAR, pixeli patrati
	function raportCadru(w, h, sar) {
		return h ? w * (sar > 0 ? sar : 1) / h : 16 / 9;
	}

	if (typeof module === "object" && module.exports) {
		module.exports = {zonaActiva: zonaActiva, dreptunghi: dreptunghi, raportCadru: raportCadru,
			VERSIUNE_DECODOR: VERSIUNE_DECODOR, COADA_MAX: COADA_MAX};
		return;
	}
	if (radacina.HdsPlayerWasm) return;

	function HdsPlayerWasm(canvas, o) {
		this.canvas = canvas;
		this.o = o || {};
		this.intarziere_s = this.o.intarziere_s || 0.5;
		this._volum = this.o.volum === undefined ? 1 : Math.max(0, Math.min(1, +this.o.volum));
		this._mut = !!this.o.mut;
		this.paused = false;
		this.oprit = false;
		this.coada = [];
		this.coadaOcteti = 0;
		this.epoca = 0;
		this.ceas0 = null;
		this.ceasPagina = null;
		this.urmAudio = 0;
		this.curent = null;
		this.info = null;
		this.ultimPtsPrimit = -1;
		this.primulCadruT = 0;
		this.ultimSunetT = 0;
		this.raportAratat = 0;
		// tarzii / salturi_ceas: masuratorile probei din 14.10 (zap MPEG-2 -> MPEG-2: ~1 cadru/s pe al doilea player, cu
		// sute de cadre "aruncate"): cadre sosite dupa ora lor (ceasul inaintea imaginii) si salturile ceasului fata de timpul
		// paginii (peste 200 ms intre doua imagini), ca proba pe receptor sa arate care din ele e
		this.st = {afisate: 0, campuri: 0, aruncate: 0, aruncate_coada: 0, sincron: [], audio_bucati: 0, audio_goluri: 0,
			audio_reluari: 0, audio_s: 0, salturi: 0, wst: null, gata: null, primul_cadru_afisat_ms: -1, tarzii: 0,
			salturi_ceas: 0, ceas_salt_max_ms: 0};
		this._ultimCeas = null;
		this._initGl();
	}

	// ---------------------------------------------------------------- ca un element <video> (pentru butoanele playerului)
	Object.defineProperty(HdsPlayerWasm.prototype, "volume", {
		get: function () { return this._volum; },
		set: function (v) { this._volum = Math.max(0, Math.min(1, +v || 0)); this._castig(); this._schimbare(); }
	});
	Object.defineProperty(HdsPlayerWasm.prototype, "muted", {
		get: function () { return this._mut; },
		set: function (v) { this._mut = !!v; this._castig(); this._schimbare(); }
	});

	HdsPlayerWasm.prototype._eveniment = function (tip, date) {
		if (this.o.laEveniment) {
			try { this.o.laEveniment(tip, date || {}); } catch (e) {}
		}
	};
	HdsPlayerWasm.prototype._schimbare = function () { this._eveniment("schimbare"); };
	HdsPlayerWasm.prototype._castig = function () {
		if (this.gain) this.gain.gain.value = this._mut ? 0 : this._volum;
	};

	// ---------------------------------------------------------------- pornirea si oprirea
	HdsPlayerWasm.prototype.porneste = function (url) {
		var self = this;
		this.pornit = performance.now();
		var AC = radacina.AudioContext || radacina.webkitAudioContext;
		if (AC) {
			try { this.ac = new AC({sampleRate: 48000, latencyHint: "playback"}); } catch (e) {
				try { this.ac = new AC(); } catch (e2) { this.ac = null; }
			}
		}
		if (this.ac) {
			this.gain = this.ac.createGain();
			this._castig();
			this.gain.connect(this.ac.destination);
			this.ac.onstatechange = function () {
				// sunetul a pornit (dupa o apasare): ceasul se reia pe sunet
				if (self.ac && self.ac.state === "running" && !self.paused) self._reiaCeasul();
			};
			var r = this.ac.resume();
			if (r && r.catch) r.catch(function () {});
		}
		this.w = new Worker(this.o.worker || "/tv/hds-worker.js");
		this.w.onmessage = function (e) { self._mesaj(e.data); };
		this.w.onerror = function (e) {
			if (!self.oprit) self._eveniment("eroare", {fel: "decodor", cod: 0, text: (e && e.message) || "worker"});
		};
		// programul canalului (sid-ul din referinta lui): la inceputul fluxului pot trece inca PAT-ul si PMT-ul canalului
		// de dinainte (hds-worker.js, Demux); 0 = primul program din PAT
		this.w.postMessage({cmd: "start", url: url, antete: this.o.antete || {}, versiune: VERSIUNE_DECODOR,
			sunet: !!this.ac, program: this.o.program || 0});
		this._vizibil = function () { self._laVizibilitate(); };
		document.addEventListener("visibilitychange", this._vizibil);
		if (document.hidden) this.w.postMessage({cmd: "vizibil", da: false});
		var bucla = function () {
			if (self.oprit) return;
			self._cadru();
			radacina.requestAnimationFrame(bucla);
		};
		radacina.requestAnimationFrame(bucla);
	};

	HdsPlayerWasm.prototype.opreste = function () {
		if (this.oprit) return;
		this.oprit = true;
		document.removeEventListener("visibilitychange", this._vizibil);
		var w = this.w;
		this.w = null;
		if (w) {
			// workerul intrerupe fetch-ul si inchide decodoarele, apoi raspunde "oprit"; dupa 400 ms se opreste oricum
			var gata = false;
			var termina = function () { if (!gata) { gata = true; try { w.terminate(); } catch (e) {} } };
			w.onmessage = function (e) { if (e.data && e.data.tip === "oprit") termina(); };
			try { w.postMessage({cmd: "stop"}); } catch (e) { termina(); }
			setTimeout(termina, 400);
		}
		if (this.ac) {
			var ac = this.ac;
			this.ac = null;
			this.gain = null;
			try { ac.onstatechange = null; ac.close(); } catch (e) {}
		}
		this.coada = [];
		this.coadaOcteti = 0;
		this._elibereazaGl();
	};

	// pauza in direct: sunetul se opreste, cadrele noi nu se mai pastreaza; la reluare, imaginea de acum (nu de unde ramase)
	HdsPlayerWasm.prototype.pause = function () {
		if (this.oprit || this.paused) return;
		this.paused = true;
		if (this.ac) { try { this.ac.suspend(); } catch (e) {} }
		if (this.w) this.w.postMessage({cmd: "vizibil", da: false});
		this.coada = [];
		this.coadaOcteti = 0;
		this._schimbare();
	};

	HdsPlayerWasm.prototype.play = function () {
		var self = this;
		if (this.oprit) return Promise.resolve();
		var era = this.paused;
		this.paused = false;
		if (this.w && !document.hidden) this.w.postMessage({cmd: "vizibil", da: true});
		var p = this.ac && this.ac.state !== "running" ? this.ac.resume() : null;
		if (era) this._reiaCeasul();
		this._schimbare();
		return p && p.then ? p.then(function () { self._reiaCeasul(); }) : Promise.resolve();
	};

	HdsPlayerWasm.prototype._reiaCeasul = function () {
		this.ceas0 = null;
		this._ultimCeas = null;
		this.ceasPagina = null;
		this.urmAudio = 0;
		this.coada = [];
		this.coadaOcteti = 0;
	};

	HdsPlayerWasm.prototype._laVizibilitate = function () {
		if (!this.w) return;
		var vizibil = !document.hidden && !this.paused;
		this.w.postMessage({cmd: "vizibil", da: vizibil});
		if (document.hidden) {
			// cadrele vechi nu se mai arata: memoria se elibereaza; sunetul merge mai departe
			this.coada = [];
			this.coadaOcteti = 0;
		} else if (!this.ac || this.ac.state !== "running") {
			this.ceasPagina = null;
		}
	};

	// ---------------------------------------------------------------- mesajele workerului
	HdsPlayerWasm.prototype._mesaj = function (m) {
		if (this.oprit || !m) return;
		if (m.tip === "v" || m.tip === "a") {
			if (m.epoca < this.epoca) return;
			if (m.epoca > this.epoca) this._epocaNoua(m.epoca);
			if (this.paused) return;
			if (m.tip === "v") this._video(m); else this._audio(m);
			return;
		}
		if (m.tip === "stat") { this.st.wst = m; return; }
		if (m.tip === "gata") { this.st.gata = m; return; }
		if (m.tip === "info") { this.info = m.info; this._eveniment("info", m.info); return; }
		if (m.tip === "eroare") { this._eveniment("eroare", {fel: m.fel, cod: m.cod, text: m.text, video: m.video}); return; }
	};

	HdsPlayerWasm.prototype._epocaNoua = function (e) {
		// salt de timp in flux: imaginea si sunetul se resincronizeaza; sunetul deja programat se termina, apoi continua
		this.epoca = e;
		this.st.salturi++;
		this._ultimCeas = null;
		this.coada = [];
		this.coadaOcteti = 0;
		this.ceasPagina = null;
		this.ceas0 = null;
		this.ultimPtsPrimit = -1;
	};

	HdsPlayerWasm.prototype._video = function (m) {
		if (!this.primulCadruT) this.primulCadruT = performance.now();
		if (m.pts > this.ultimPtsPrimit) this.ultimPtsPrimit = m.pts;
		// ceasul de acum, fara sa-l porneasca (ceas() pune ceasul paginii la primul cadru din coada)
		var c0 = this._ceasSunet();
		if (c0 === null && this.ceasPagina) c0 = this.ceasPagina.pts + (performance.now() - this.ceasPagina.t) * 90;
		if (c0 !== null && m.pts <= c0) this.st.tarzii++;
		var marime = m.buf.byteLength;
		this.coada.push(m);
		this.coadaOcteti += marime;
		// coada are o limita: cand pagina nu tine pasul (procesor ocupat), cadrele cele mai vechi pleaca
		while (this.coada.length > COADA_MAX || (this.coadaOcteti > COADA_OCTETI_MAX && this.coada.length > 1)) {
			var x = this.coada.shift();
			this.coadaOcteti -= x.buf.byteLength;
			this.st.aruncate_coada++;
		}
	};

	HdsPlayerWasm.prototype._audio = function (m) {
		var ac = this.ac;
		if (!ac || ac.state !== "running") return;
		this.ultimSunetT = performance.now();
		var n = m.n || m.l.byteLength / 4;
		var b = ac.createBuffer(2, n, m.rata);
		b.copyToChannel(new Float32Array(m.l), 0);
		b.copyToChannel(new Float32Array(m.r), 1);
		var acum = ac.currentTime;
		if (!this.ceas0) {
			// inceputul (sau dupa un salt): dupa tamponul voit, dar nu peste sunetul deja programat
			this.ceas0 = {ctx: Math.max(acum + this.intarziere_s, this.urmAudio || 0), pts: m.pts};
			this.urmAudio = 0;
		}
		var cand = this.ceas0.ctx + (m.pts - this.ceas0.pts) / 90000;
		if (this.urmAudio && Math.abs(cand - this.urmAudio) < 0.04) cand = this.urmAudio;   // lipit de bucata dinainte
		else if (this.urmAudio) this.st.audio_goluri++;
		if (cand < acum + 0.005 || cand > acum + 5) {
			// sunetul a ramas in urma (procesor ocupat, fila ascunsa) sau a sarit inainte: ceasul se reia de la bucata asta
			this.ceas0 = {ctx: acum + this.intarziere_s, pts: m.pts};
			cand = this.ceas0.ctx;
			this.st.audio_reluari++;
		}
		var s = ac.createBufferSource();
		s.buffer = b;
		s.connect(this.gain);
		s.start(cand);
		this.urmAudio = cand + n / m.rata;
		this.st.audio_bucati++;
		this.st.audio_s += n / m.rata;
	};

	// ---------------------------------------------------------------- ceasul
	HdsPlayerWasm.prototype._ceasSunet = function () {
		var ac = this.ac;
		if (!ac || ac.state !== "running" || !this.ceas0) return null;
		var ctx, ts = ac.getOutputTimestamp ? ac.getOutputTimestamp() : null;
		if (ts && ts.performanceTime) ctx = ts.contextTime + (performance.now() - ts.performanceTime) / 1000;
		else ctx = ac.currentTime - (ac.outputLatency || ac.baseLatency || 0);
		return this.ceas0.pts + (ctx - this.ceas0.ctx) * 90000;
	};

	// PTS-ul (90 kHz) care trebuie aratat acum, sau null cat se asteapta inceputul
	HdsPlayerWasm.prototype.ceas = function () {
		var c = this._ceasSunet();
		if (c !== null) { this.ceasPagina = null; return c; }
		var cuSunet = this.ac && this.ac.state === "running" && this.info && this.info.audio;
		var sunetTarziu = this.primulCadruT && performance.now() - this.primulCadruT > ASTEPTARE_SUNET_MS &&
			performance.now() - this.ultimSunetT > ASTEPTARE_SUNET_MS;
		if (cuSunet && !sunetTarziu) return null;
		if (!this.ceasPagina && this.coada.length) {
			this.ceasPagina = {t: performance.now() + this.intarziere_s * 1000, pts: this.coada[0].pts};
		}
		return this.ceasPagina ? this.ceasPagina.pts + (performance.now() - this.ceasPagina.t) * 90 : null;
	};

	// cat de in urma e imaginea aratata fata de ce a sosit (ms): stratul receptorului se arata cu aceeasi intarziere
	HdsPlayerWasm.prototype.intarziere = function () {
		if (this.paused || this.ultimPtsPrimit < 0) return 0;
		var c = this.ceas();
		if (c === null) return this.intarziere_s * 1000;
		return Math.max(0, Math.min(4000, (this.ultimPtsPrimit - c) / 90));
	};

	// ---------------------------------------------------------------- imaginea
	HdsPlayerWasm.prototype._cadru = function () {
		if (this.paused || !this.gl) return;
		var c = this.ceas();
		if (c === null) { this._ultimCeas = null; return; }
		var t = performance.now();
		if (this._ultimCeas) {
			// ceasul fata de timpul paginii: un salt (inainte sau inapoi) de peste 200 ms se numara
			var salt = Math.abs((c - this._ultimCeas.c) / 90 - (t - this._ultimCeas.t));
			if (salt > 200) this.st.salturi_ceas++;
			if (salt > this.st.ceas_salt_max_ms) this.st.ceas_salt_max_ms = Math.round(salt);
		}
		this._ultimCeas = {c: c, t: t};
		// cadrul de aratat: ultimul cu pts <= ceas (cele sarite se numara)
		var ales = null;
		while (this.coada.length && this.coada[0].pts <= c) {
			if (ales) this.st.aruncate++;
			ales = this.coada.shift();
			this.coadaOcteti -= ales.buf.byteLength;
		}
		if (!ales && this.coada.length && this.coada[0].pts - c > INAINTE_MAX) {
			// imaginea e mult inaintea ceasului (sunetul a stat): totul se reia de la cadrele din coada
			this.ceas0 = null;
			this.ceasPagina = null;
			this.urmAudio = 0;
			this.st.audio_reluari++;
			return;
		}
		if (ales) {
			this._incarca(ales);
			this.curent = ales;
			this.st.afisate++;
			if (this.st.primul_cadru_afisat_ms < 0) {
				this.st.primul_cadru_afisat_ms = performance.now() - this.pornit;
				this._eveniment("primul_cadru");
				// browserul nu porneste sunetul fara o apasare: imaginea merge (ceasul paginii), pagina cere apasarea
				if (this.ac && this.ac.state !== "running" && !this.paused) this._eveniment("sunet_blocat");
			}
			this.st.sincron.push((c - ales.pts) / 90);
			if (this.st.sincron.length > 3000) this.st.sincron.shift();
		}
		if (!this.curent) return;
		var camp = -1;
		if (this.curent.flags & 1) {
			var sus = (this.curent.flags & 2) ? 0 : 1;
			camp = (c - this.curent.pts) >= this.curent.durata / 2 ? 1 - sus : sus;
		}
		if (ales || camp !== this.ultimCamp || this._marimeSchimbata()) {
			this._deseneaza(camp);
			this.st.campuri++;
			this.ultimCamp = camp;
		}
	};

	HdsPlayerWasm.prototype._marimeSchimbata = function () {
		var r = radacina.devicePixelRatio || 1;
		var l = Math.max(2, Math.round((this.canvas.clientWidth || 960) * r));
		var h = Math.max(2, Math.round((this.canvas.clientHeight || 540) * r));
		if (this.canvas.width === l && this.canvas.height === h) return false;
		this.canvas.width = l;
		this.canvas.height = h;
		return true;
	};

	HdsPlayerWasm.prototype._initGl = function () {
		var self = this;
		var gl = this.canvas.getContext("webgl", {alpha: false, antialias: false, preserveDrawingBuffer: false}) ||
			this.canvas.getContext("experimental-webgl");
		this.gl = gl;
		if (!gl) return;
		this._pierdut = function (e) {
			e.preventDefault();
			self.gl = null;
			if (!self.oprit) self._eveniment("eroare", {fel: "decodor", cod: 0, text: "WebGL pierdut"});
		};
		this.canvas.addEventListener("webglcontextlost", this._pierdut);
		var vs = "attribute vec2 p; varying vec2 uv; void main(){ uv = vec2(p.x * 0.5 + 0.5, 0.5 - p.y * 0.5); gl_Position = vec4(p, 0.0, 1.0); }";
		// trecerea 1: YUV -> RGB la marimea cadrului, cu desentrelasarea pe randuri (camp 0 / 1: "bob"; -1: progresiv)
		var fs1 = [
			"precision highp float;",
			"uniform sampler2D ty, tu, tv; uniform vec2 my, mc; uniform float camp; uniform mat3 m; uniform float plin;",
			"varying vec2 uv;",
			"float rand(sampler2D t, vec2 marime, vec2 q) {",
			"  float r = floor(q.y * marime.y);",
			"  if (camp < 0.0 || mod(r, 2.0) == camp) return texture2D(t, vec2(q.x, (r + 0.5) / marime.y)).r;",
			"  float a = r - 1.0, b = r + 1.0;",
			"  if (a < 0.0) a = b;",
			"  if (b > marime.y - 1.0) b = a;",
			"  return 0.5 * (texture2D(t, vec2(q.x, (a + 0.5) / marime.y)).r + texture2D(t, vec2(q.x, (b + 0.5) / marime.y)).r);",
			"}",
			"void main(){",
			"  float y = rand(ty, my, uv), u = rand(tu, mc, uv) - 0.5, v = rand(tv, mc, uv) - 0.5;",
			"  if (plin < 0.5) { y = (y - 16.0 / 255.0) * (255.0 / 219.0); u *= 255.0 / 224.0; v *= 255.0 / 224.0; }",
			"  gl_FragColor = vec4(clamp(m * vec3(y, u, v), 0.0, 1.0), 1.0);",
			"}"].join("\n");
		// trecerea 2: zona activa a cadrului (AFD) in dreptunghiul ei din canvas, marita biliniar
		var fs2 = "precision mediump float; uniform sampler2D t; uniform vec4 zona; varying vec2 uv; " +
			"void main(){ gl_FragColor = texture2D(t, vec2(zona.x + uv.x * zona.z, 1.0 - (zona.y + uv.y * zona.w))); }";
		this.p1 = this._program(vs, fs1);
		this.p2 = this._program(vs, fs2);
		this.varfuri = gl.createBuffer();
		gl.bindBuffer(gl.ARRAY_BUFFER, this.varfuri);
		gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
		this.tex = [0, 1, 2].map(function () {
			var t = gl.createTexture();
			gl.bindTexture(gl.TEXTURE_2D, t);
			gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
			gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
			gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
			gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
			return t;
		});
		gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
		this.rgb = gl.createTexture();
		this.fb = gl.createFramebuffer();
		this.fw = 0;
		this.fh = 0;
		this.loc = {
			p1: gl.getAttribLocation(this.p1, "p"), p2: gl.getAttribLocation(this.p2, "p"),
			my: gl.getUniformLocation(this.p1, "my"), mc: gl.getUniformLocation(this.p1, "mc"),
			camp: gl.getUniformLocation(this.p1, "camp"), plin: gl.getUniformLocation(this.p1, "plin"),
			m: gl.getUniformLocation(this.p1, "m"), t: gl.getUniformLocation(this.p2, "t"),
			zona: gl.getUniformLocation(this.p2, "zona"),
			ty: gl.getUniformLocation(this.p1, "ty"), tu: gl.getUniformLocation(this.p1, "tu"), tv: gl.getUniformLocation(this.p1, "tv")
		};
		gl.clearColor(0, 0, 0, 1);
		gl.clear(gl.COLOR_BUFFER_BIT);
	};

	HdsPlayerWasm.prototype._program = function (vs, fs) {
		var gl = this.gl, p = gl.createProgram();
		[[gl.VERTEX_SHADER, vs], [gl.FRAGMENT_SHADER, fs]].forEach(function (x) {
			var s = gl.createShader(x[0]);
			gl.shaderSource(s, x[1]);
			gl.compileShader(s);
			if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
			gl.attachShader(p, s);
			gl.deleteShader(s);
		});
		gl.linkProgram(p);
		return p;
	};

	HdsPlayerWasm.prototype._elibereazaGl = function () {
		var gl = this.gl;
		if (this._pierdut) this.canvas.removeEventListener("webglcontextlost", this._pierdut);
		if (!gl) return;
		try {
			gl.bindFramebuffer(gl.FRAMEBUFFER, null);
			gl.clearColor(0, 0, 0, 1);
			gl.clear(gl.COLOR_BUFFER_BIT);
			(this.tex || []).forEach(function (t) { gl.deleteTexture(t); });
			gl.deleteTexture(this.rgb);
			gl.deleteFramebuffer(this.fb);
			gl.deleteBuffer(this.varfuri);
			gl.deleteProgram(this.p1);
			gl.deleteProgram(this.p2);
		} catch (e) {}
		this.gl = null;
	};

	HdsPlayerWasm.prototype._incarca = function (f) {
		var gl = this.gl, d = new Uint8Array(f.buf);
		var planuri = [[0, f.w, f.h], [f.w * f.h, f.cw, f.ch], [f.w * f.h + f.cw * f.ch, f.cw, f.ch]];
		for (var i = 0; i < 3; i++) {
			gl.activeTexture(gl.TEXTURE0 + i);
			gl.bindTexture(gl.TEXTURE_2D, this.tex[i]);
			var q = planuri[i];
			gl.texImage2D(gl.TEXTURE_2D, 0, gl.LUMINANCE, q[1], q[2], 0, gl.LUMINANCE, gl.UNSIGNED_BYTE, d.subarray(q[0], q[0] + q[1] * q[2]));
		}
		if (this.fw !== f.w || this.fh !== f.h) {
			this.fw = f.w;
			this.fh = f.h;
			gl.activeTexture(gl.TEXTURE3);
			gl.bindTexture(gl.TEXTURE_2D, this.rgb);
			gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, f.w, f.h, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
			gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
			gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
			gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
			gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
			gl.bindFramebuffer(gl.FRAMEBUFFER, this.fb);
			gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, this.rgb, 0);
			gl.bindFramebuffer(gl.FRAMEBUFFER, null);
		}
		// raportul aratat: zona activa (AFD) a cadrului, cu SAR (720x576: 16:15 = 4:3, 64:45 = 16:9)
		this.zona = zonaActiva(f.afd, raportCadru(f.w, f.h, f.sar));
		if (Math.abs(this.zona.raport - this.raportAratat) > 0.001) {
			this.raportAratat = this.zona.raport;
			this._eveniment("raport", {raport: this.zona.raport, afd: f.afd, sar: f.sar, latime: f.w, inaltime: f.h});
		}
	};

	HdsPlayerWasm.prototype._deseneaza = function (camp) {
		var gl = this.gl, f = this.curent, L = this.loc;
		this._marimeSchimbata();
		// BT.601 pentru SD (si cand nu se stie), BT.709 pentru HD (matricea 1)
		var bt709 = f.matrice === 1 || (f.matrice === 2 && f.h > 576);
		var m = bt709 ? [1, 1, 1, 0, -0.1873, 1.8556, 1.5748, -0.4681, 0] : [1, 1, 1, 0, -0.3441, 1.772, 1.402, -0.7141, 0];
		gl.bindBuffer(gl.ARRAY_BUFFER, this.varfuri);
		gl.useProgram(this.p1);
		gl.bindFramebuffer(gl.FRAMEBUFFER, this.fb);
		gl.viewport(0, 0, f.w, f.h);
		gl.enableVertexAttribArray(L.p1);
		gl.vertexAttribPointer(L.p1, 2, gl.FLOAT, false, 0, 0);
		gl.uniform1i(L.ty, 0);
		gl.uniform1i(L.tu, 1);
		gl.uniform1i(L.tv, 2);
		gl.uniform2f(L.my, f.w, f.h);
		gl.uniform2f(L.mc, f.cw, f.ch);
		gl.uniform1f(L.camp, camp);
		gl.uniform1f(L.plin, f.gama === 2 ? 1 : 0);
		gl.uniformMatrix3fv(L.m, false, m);
		gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
		gl.bindFramebuffer(gl.FRAMEBUFFER, null);
		var cw = this.canvas.width, ch = this.canvas.height, z = this.zona || {x: 0, y: 0, l: 1, h: 1, raport: 16 / 9};
		var d = dreptunghi(z.raport, cw, ch);
		gl.viewport(0, 0, cw, ch);
		gl.clear(gl.COLOR_BUFFER_BIT);
		gl.viewport(d.x, d.y, d.l, d.h);
		gl.useProgram(this.p2);
		gl.enableVertexAttribArray(L.p2);
		gl.vertexAttribPointer(L.p2, 2, gl.FLOAT, false, 0, 0);
		gl.activeTexture(gl.TEXTURE3);
		gl.bindTexture(gl.TEXTURE_2D, this.rgb);
		gl.uniform1i(L.t, 3);
		gl.uniform4f(L.zona, z.x, z.y, z.l, z.h);
		gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
	};

	// ---------------------------------------------------------------- masuratorile (probele de pe PC)
	HdsPlayerWasm.prototype.rezumat = function () {
		var s = this.st, sin = s.sincron.slice().sort(function (a, b) { return a - b; });
		var med = sin.length ? sin.reduce(function (a, b) { return a + b; }, 0) / sin.length : 0;
		var p = function (q) { return sin.length ? sin[Math.min(sin.length - 1, Math.floor(q * sin.length))] : 0; };
		var w = s.wst ? s.wst.st : null, t = s.wst ? s.wst.timp_ms / 1000 : 0;
		return {
			incarcare_wasm_ms: s.gata ? Math.round(s.gata.incarcare_ms) : null,
			primul_cadru_decodat_ms: w ? Math.round(w.primul_cadru_ms) : null,
			primul_cadru_afisat_ms: Math.round(s.primul_cadru_afisat_ms),
			info: this.info, timp_s: +t.toFixed(1),
			cadre_decodate: w ? w.v.cadre : 0, cadre_nevazute: w ? w.v.nevazute : 0, afisate: s.afisate,
			campuri_desenate: s.campuri, aruncate: s.aruncate, aruncate_coada: s.aruncate_coada, coada: this.coada.length,
			video_ms_pe_cadru: w && w.v.cadre ? +(w.v.ms / w.v.cadre).toFixed(2) : null, video_ms_max: w ? +w.v.max.toFixed(1) : null,
			audio_s: +s.audio_s.toFixed(1), audio_goluri: s.audio_goluri, audio_reluari: s.audio_reluari,
			salturi: s.salturi, erori_decodor: w ? w.erori : null, demux: w ? w.demux : null,
			sincron_ms: {medie: +med.toFixed(1), p5: +p(0.05).toFixed(1), p95: +p(0.95).toFixed(1), n: sin.length},
			raport: +(this.raportAratat || 0).toFixed(3), octeti: w ? w.octeti : 0,
			sunet: this.ac ? this.ac.state : "fara",
			tarzii: s.tarzii, salturi_ceas: s.salturi_ceas, ceas_salt_max_ms: s.ceas_salt_max_ms,
			ceas: this._ceasSunet() !== null ? "sunet" : (this.ceasPagina ? "pagina" : "-")
		};
	};

	HdsPlayerWasm.zonaActiva = zonaActiva;
	HdsPlayerWasm.VERSIUNE_DECODOR = VERSIUNE_DECODOR;
	radacina.HdsPlayerWasm = HdsPlayerWasm;
})(typeof window !== "undefined" ? window : this);
