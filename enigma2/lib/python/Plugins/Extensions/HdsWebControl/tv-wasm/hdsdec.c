// SPDX-License-Identifier: GPL-2.0-only
// Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
//
// hdsdec.c: puntea dintre playerul wasm al paginii "TV in browser" (hds-worker.js) si decodoarele din libavcodec
// (FFmpeg 8.1.3, LGPL-2.1-or-later, construit fara --enable-gpl). Compilata la WebAssembly cu emscripten 6.0.9 de
// construieste-decodor-wasm.sh (de langa acest fisier); iesirea, hdsdec.js si hdsdec.wasm, sta gata facuta in imagine
// (OpenEmbedded nu are emscripten). Decodoarele din imagine: mpeg1video, mpeg2video, mp2float, mp3float, ac3.
//
// Ce face: primeste bucati de flux elementar (continutul PES-urilor, cu PTS-ul lor in unitati de 90 kHz, deja
// desfacut in timp continuu de hds-worker.js), le taie in cadre cu parserul libavcodec, le decodeaza si da fiecare
// cadru decodat paginii prin doua functii JS (Module.onVideo, Module.onAudio), cu adresele planurilor in memoria wasm.
// Workerul copiaza datele inainte ca dec_push sa se intoarca.
// Fara fire (pagina receptorului e http, deci fara SharedArrayBuffer) si fara libavformat (demuxul TS e in JS).

#include <emscripten.h>
#include <libavcodec/avcodec.h>
#include <libavutil/channel_layout.h>
#include <libavutil/dict.h>
#include <libavutil/frame.h>
#include <libavutil/pixdesc.h>
#include <stdlib.h>
#include <string.h>

typedef struct Dec {
	const AVCodec *codec;
	AVCodecContext *c;
	AVCodecParserContext *p;
	AVPacket *pkt;
	AVFrame *f;
	int video;
	int stereo;
	int erori;
} Dec;

// afd: Active Format Description din datele utilizatorului MPEG-2 ("DTG1"), 0-15, sau -1 cand cadrul nu are
EM_JS(void, js_video, (int w, int h, int fmt, uint8_t *y, uint8_t *u, uint8_t *v, int ly, int lu, int lv, double pts,
	int flags, int sar_n, int sar_d, int matrice, int gama, int afd), {
	Module.onVideo(w, h, fmt, y, u, v, ly, lu, lv, pts, flags, sar_n, sar_d, matrice, gama, afd);
});

EM_JS(void, js_audio, (int n, int canale, int rata, int fmt, uint8_t **date, double pts), {
	Module.onAudio(n, canale, rata, fmt, date, pts);
});

static double pts_d(int64_t v)
{
	return v == AV_NOPTS_VALUE ? -1.0 : (double)v;
}

static void da_cadrele(Dec *d)
{
	while (avcodec_receive_frame(d->c, d->f) == 0) {
		AVFrame *f = d->f;
		double pts = pts_d(f->best_effort_timestamp);
		if (d->video) {
			// fmt pentru JS: adancimea (8 biti) | log2 subesantionarea culorii pe orizontala << 8 | pe verticala << 12
			const AVPixFmtDescriptor *desc = av_pix_fmt_desc_get(f->format);
			int fmt = desc ? (desc->comp[0].depth | (desc->log2_chroma_w << 8) | (desc->log2_chroma_h << 12)) : 0;
			int flags = 0;
			int afd = -1;
			AVFrameSideData *sd = av_frame_get_side_data(f, AV_FRAME_DATA_AFD);
			if (sd && sd->size >= 1)
				afd = sd->data[0] & 0x0F;
			if (f->flags & AV_FRAME_FLAG_INTERLACED)
				flags |= 1;
			if (f->flags & AV_FRAME_FLAG_TOP_FIELD_FIRST)
				flags |= 2;
			if (f->flags & AV_FRAME_FLAG_KEY)
				flags |= 4;
			if (f->repeat_pict)
				flags |= 8;
			if (desc && !(desc->flags & AV_PIX_FMT_FLAG_PLANAR))
				fmt = 0;   // numai formate planare (yuv420p / yuv422p / yuv444p); altceva JS nu deseneaza
			js_video(f->width, f->height, fmt, f->data[0], f->data[1], f->data[2], f->linesize[0],
				f->linesize[1], f->linesize[2], pts, flags, f->sample_aspect_ratio.num,
				f->sample_aspect_ratio.den, (int)f->colorspace, (int)f->color_range, afd);
		} else {
			js_audio(f->nb_samples, f->ch_layout.nb_channels, f->sample_rate, f->format, f->extended_data, pts);
		}
		av_frame_unref(f);
	}
}

static int deschide_contextul(Dec *d)
{
	d->c = avcodec_alloc_context3(d->codec);
	if (!d->c)
		return -1;
	d->c->thread_count = 1;
	d->c->pkt_timebase = (AVRational){1, 90000};
	d->c->time_base = (AVRational){1, 90000};
	AVDictionary *opt = NULL;
	if (d->stereo && d->codec->id == AV_CODEC_ID_AC3)
		av_dict_set(&opt, "downmix", "stereo", 0);
	int r = avcodec_open2(d->c, d->codec, &opt);
	av_dict_free(&opt);
	if (r < 0) {
		avcodec_free_context(&d->c);
		return -1;
	}
	d->p = av_parser_init(d->codec->id);
	return 0;
}

// nume: numele decodorului din libavcodec ("mpeg2video", "mpeg1video", "mp2float", "mp3float", "ac3")
EMSCRIPTEN_KEEPALIVE Dec *dec_open(const char *nume, int stereo)
{
	const AVCodec *codec = avcodec_find_decoder_by_name(nume);
	if (!codec)
		return NULL;
	Dec *d = calloc(1, sizeof(Dec));
	if (!d)
		return NULL;
	d->codec = codec;
	d->video = codec->type == AVMEDIA_TYPE_VIDEO;
	d->stereo = stereo;
	d->pkt = av_packet_alloc();
	d->f = av_frame_alloc();
	if (!d->pkt || !d->f || deschide_contextul(d) < 0) {
		av_packet_free(&d->pkt);
		av_frame_free(&d->f);
		free(d);
		return NULL;
	}
	return d;
}

// date / lung: continutul unui PES (sau o bucata din el); pts: PTS-ul PES-ului care incepe aici, sau -1.
// -> cate pachete au mers la decodor, sau -1 la o eroare a parserului
EMSCRIPTEN_KEEPALIVE int dec_push(Dec *d, const uint8_t *date, int lung, double pts)
{
	int64_t p = pts < 0 ? AV_NOPTS_VALUE : (int64_t)pts;
	int cadre = 0;
	while (lung > 0) {
		uint8_t *iesire = NULL;
		int marime = 0;
		int n;
		if (d->p) {
			n = av_parser_parse2(d->p, d->c, &iesire, &marime, date, lung, p, p, 0);
		} else {
			n = lung;
			iesire = (uint8_t *)date;
			marime = lung;
		}
		if (n < 0)
			return -1;
		date += n;
		lung -= n;
		p = AV_NOPTS_VALUE;
		if (marime > 0) {
			d->pkt->data = iesire;
			d->pkt->size = marime;
			d->pkt->pts = d->p ? d->p->pts : AV_NOPTS_VALUE;
			d->pkt->dts = d->p ? d->p->dts : AV_NOPTS_VALUE;
			d->pkt->flags = (d->p && d->p->key_frame == 1) ? AV_PKT_FLAG_KEY : 0;
			if (avcodec_send_packet(d->c, d->pkt) < 0)
				d->erori++;
			cadre++;
			da_cadrele(d);
		}
	}
	return cadre;
}

// discontinuitate (salt de timp, flux reluat): parserul si decodorul o iau de la capat, fara cadrele vechi
EMSCRIPTEN_KEEPALIVE void dec_reset(Dec *d)
{
	if (!d || !d->c)
		return;
	if (d->p) {
		av_parser_close(d->p);
		d->p = av_parser_init(d->codec->id);
	}
	avcodec_flush_buffers(d->c);
}

EMSCRIPTEN_KEEPALIVE int dec_erori(Dec *d)
{
	return d ? d->erori : 0;
}

EMSCRIPTEN_KEEPALIVE void dec_close(Dec *d)
{
	if (!d)
		return;
	if (d->p)
		av_parser_close(d->p);
	avcodec_free_context(&d->c);
	av_packet_free(&d->pkt);
	av_frame_free(&d->f);
	free(d);
}
