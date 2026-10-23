/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdsdtsac3: element GStreamer care primeste sunet DTS (audio/x-dts, cadre intregi, de la dcaparse) si da AC3
 * (audio/x-ac3, cadre intregi) pentru iesirea digitala a receptorului (HDMI sau optica), cand televizorul sau
 * amplificatorul stie AC3 dar nu DTS.
 *
 * Inauntru: decodorul DTS din libavcodec deschis cu core_only=1 (numai nucleul DTS, cel mult 5.1 la 48 kHz; extensiile
 * XLL, XCH, X96, XXCH si LBR nu se folosesc), apoi codorul AC3 din libavcodec ("ac3", virgula mobila; "ac3_fixed" cand
 * primul lipseste) la DEBIT_IMPLICIT (640 kb/s), cu aceeasi asezare a canalelor ca nucleul DTS (5.1, 5.0, stereo ...).
 * Cadrele DTS au de obicei 512 esantioane, cele AC3 1536: esantioanele decodate se strang intr-un AVAudioFifo si
 * pleaca la codor cate un cadru AC3. Esantioanele intregi (S32P, cand decodorul le da asa) se trec in virgula mobila
 * aici, fara libswresample.
 *
 * Timpul: marcajul primului esantion din coada vine din marcajul cadrului DTS de intrare; fiecare cadru AC3 primeste
 * marcajul cozii, care creste cu 1536 / rata (codorul AC3 intarzie sunetul cu 256 de esantioane, 5,3 ms la 48 kHz,
 * mult sub pragul la care se vede nepotrivirea cu buzele; marcajele raman cele ale intrarii, la pas exact). Un cadru
 * de intrare al carui marcaj difera de cel asteptat cu mai mult de
 * SALT_MAXIM (salt in fisier, pachete pierdute) goleste coada si ia marcajul nou (cadrul de iesire urmator are
 * DISCONT). Golirea fluxului (FLUSH_STOP, cautarea) uita tot: coada, decodorul (avcodec_flush_buffers), codorul (facut
 * din nou), marcajul. La EOS ce a ramas in coada se completeaza cu liniste pana la un cadru intreg si pleaca.
 *
 * Ratele nucleului DTS pe care AC3 nu le are (altele decat 32, 44,1 si 48 kHz) si asezarile pe care codorul AC3 nu le
 * primeste opresc fluxul cu o eroare (not-negotiated), fara iesire falsa.
 *
 * Rangul (PRIMARY + 1) e peste decodoarele DTS obisnuite; decodebin ajunge insa la element numai cand sink-ul nu
 * primeste audio/x-dts (dvbaudiosink il ascunde cand recodarea e pornita), deci altfel nimic nu se schimba.
 */

#ifdef HAVE_CONFIG_H
#include "config.h"
#endif

#include <string.h>

#include <gst/gst.h>
#include <gst/audio/audio.h>

#include <libavcodec/avcodec.h>
#include <libavutil/audio_fifo.h>
#include <libavutil/channel_layout.h>
#include <libavutil/opt.h>

#define DEBIT_IMPLICIT 640000
#define DEBIT_MINIM 192000
#define DEBIT_MAXIM 640000
#define SALT_MAXIM (100 * GST_MSECOND)

GST_DEBUG_CATEGORY_STATIC(hdsdtsac3_debug);
#define GST_CAT_DEFAULT hdsdtsac3_debug

#define GST_TYPE_HDS_DTS_AC3 (gst_hds_dts_ac3_get_type())
G_DECLARE_FINAL_TYPE(GstHdsDtsAc3, gst_hds_dts_ac3, GST, HDS_DTS_AC3, GstElement)

struct _GstHdsDtsAc3 {
    GstElement parent;
    GstPad *sinkpad;
    GstPad *srcpad;

    gint debit;                 /* proprietatea "bitrate" */

    AVCodecContext *dec;
    AVCodecContext *enc;
    AVPacket *pachet;
    AVFrame *cadru_dec;
    AVFrame *cadru_enc;
    AVAudioFifo *coada;
    gint rata;                  /* a codorului deschis (0 = nedeschis) */
    AVChannelLayout asezare;

    GstClockTime pts_coada;     /* marcajul primului esantion din coada */
    gboolean discont;
    gboolean eroare;            /* format neprimit: tot ce vine se arunca */
    GstEvent *segment;          /* segmentul tinut pana la caps-urile iesirii (ordinea evenimentelor) */
};

enum { PROP_0, PROP_BITRATE };

static GstStaticPadTemplate sink_sablon = GST_STATIC_PAD_TEMPLATE("sink", GST_PAD_SINK, GST_PAD_ALWAYS,
    GST_STATIC_CAPS("audio/x-dts, framed = (boolean) true"));

static GstStaticPadTemplate src_sablon = GST_STATIC_PAD_TEMPLATE("src", GST_PAD_SRC, GST_PAD_ALWAYS,
    GST_STATIC_CAPS("audio/x-ac3, framed = (boolean) true, alignment = (string) frame, "
        "rate = (int) { 32000, 44100, 48000 }, channels = (int) [ 1, 6 ]"));

G_DEFINE_TYPE(GstHdsDtsAc3, gst_hds_dts_ac3, GST_TYPE_ELEMENT)

static void eroare_av(GstHdsDtsAc3 *s, const char *ce, int cod)
{
    char text[AV_ERROR_MAX_STRING_SIZE] = { 0 };
    av_strerror(cod, text, sizeof(text));
    GST_WARNING_OBJECT(s, "%s: %s", ce, text);
}

/* ---------------------------------------------------------------- decodorul si codorul */

static void codor_inchide(GstHdsDtsAc3 *s)
{
    avcodec_free_context(&s->enc);
    av_frame_free(&s->cadru_enc);
    if (s->coada) {
        av_audio_fifo_free(s->coada);
        s->coada = NULL;
    }
    av_channel_layout_uninit(&s->asezare);
    s->rata = 0;
}

static void toate_inchide(GstHdsDtsAc3 *s)
{
    codor_inchide(s);
    avcodec_free_context(&s->dec);
    av_packet_free(&s->pachet);
    av_frame_free(&s->cadru_dec);
}

static gboolean decodor_deschide(GstHdsDtsAc3 *s)
{
    const AVCodec *c = avcodec_find_decoder(AV_CODEC_ID_DTS);
    if (!c) {
        GST_ELEMENT_ERROR(s, LIBRARY, INIT, ("Decodorul DTS lipseste din libavcodec."), (NULL));
        return FALSE;
    }
    s->dec = avcodec_alloc_context3(c);
    s->pachet = av_packet_alloc();
    s->cadru_dec = av_frame_alloc();
    if (!s->dec || !s->pachet || !s->cadru_dec)
        return FALSE;
    /* numai nucleul DTS (cel mult 5.1): extensiile nu se decodeaza (AC3 duce oricum cel mult 5.1) */
    AVDictionary *o = NULL;
    av_dict_set(&o, "core_only", "1", 0);
    int r = avcodec_open2(s->dec, c, &o);
    gboolean pus = av_dict_get(o, "core_only", NULL, 0) == NULL;   /* optiunile folosite ies din dictionar */
    av_dict_free(&o);
    if (r < 0 || !pus) {
        eroare_av(s, "decodorul DTS", r);
        GST_ELEMENT_ERROR(s, LIBRARY, INIT, ("Decodorul DTS nu a pornit cu core_only."), (NULL));
        return FALSE;
    }
    return TRUE;
}

static gboolean asezare_primita(const AVCodec *c, AVCodecContext *ctx, const AVChannelLayout *a)
{
    const void *lista = NULL;
    int n = 0;
    if (avcodec_get_supported_config(ctx, c, AV_CODEC_CONFIG_CHANNEL_LAYOUT, 0, &lista, &n) < 0)
        return FALSE;
    if (!lista)
        return TRUE;            /* orice asezare */
    const AVChannelLayout *l = lista;
    for (int i = 0; i < n; i++) {
        if (!av_channel_layout_compare(&l[i], a))
            return TRUE;
    }
    return FALSE;
}

/* Codorul AC3 pentru rata si asezarea nucleului DTS; caps-urile iesirii. */
static gboolean codor_deschide(GstHdsDtsAc3 *s, int rata, const AVChannelLayout *asezare)
{
    codor_inchide(s);
    if (rata != 48000 && rata != 44100 && rata != 32000) {
        GST_ELEMENT_ERROR(s, STREAM, FORMAT, ("Rata sunetului DTS (%d Hz) nu exista in AC3.", rata), (NULL));
        return FALSE;
    }
    const AVCodec *c = avcodec_find_encoder_by_name("ac3");
    enum AVSampleFormat fel = AV_SAMPLE_FMT_FLTP;
    if (!c) {
        c = avcodec_find_encoder_by_name("ac3_fixed");
        fel = AV_SAMPLE_FMT_S32P;
    }
    if (!c) {
        GST_ELEMENT_ERROR(s, LIBRARY, INIT, ("Codorul AC3 lipseste din libavcodec."), (NULL));
        return FALSE;
    }
    s->enc = avcodec_alloc_context3(c);
    if (!s->enc)
        return FALSE;
    if (!asezare_primita(c, s->enc, asezare)) {
        char nume[64] = { 0 };
        av_channel_layout_describe(asezare, nume, sizeof(nume));
        GST_ELEMENT_ERROR(s, STREAM, FORMAT, ("Asezarea canalelor DTS (%s) nu se poate coda in AC3.", nume), (NULL));
        return FALSE;
    }
    s->enc->sample_fmt = fel;
    s->enc->sample_rate = rata;
    s->enc->bit_rate = s->debit;
    s->enc->time_base = (AVRational){ 1, rata };
    av_channel_layout_copy(&s->enc->ch_layout, asezare);
    int r = avcodec_open2(s->enc, c, NULL);
    if (r < 0) {
        eroare_av(s, "codorul AC3", r);
        GST_ELEMENT_ERROR(s, LIBRARY, INIT, ("Codorul AC3 nu a pornit."), (NULL));
        return FALSE;
    }
    s->cadru_enc = av_frame_alloc();
    s->coada = av_audio_fifo_alloc(fel, asezare->nb_channels, s->enc->frame_size * 4);
    if (!s->cadru_enc || !s->coada)
        return FALSE;
    s->cadru_enc->format = fel;
    s->cadru_enc->sample_rate = rata;
    s->cadru_enc->nb_samples = s->enc->frame_size;
    av_channel_layout_copy(&s->cadru_enc->ch_layout, asezare);
    if (av_frame_get_buffer(s->cadru_enc, 0) < 0)
        return FALSE;
    av_channel_layout_copy(&s->asezare, asezare);
    s->rata = rata;

    GstCaps *caps = gst_caps_new_simple("audio/x-ac3", "framed", G_TYPE_BOOLEAN, TRUE, "alignment", G_TYPE_STRING, "frame",
        "rate", G_TYPE_INT, rata, "channels", G_TYPE_INT, asezare->nb_channels, NULL);
    GstCaps *acum = gst_pad_get_current_caps(s->srcpad);
    gboolean bun = acum && gst_caps_is_equal(acum, caps) ? TRUE : gst_pad_set_caps(s->srcpad, caps);
    if (acum)
        gst_caps_unref(acum);
    gst_caps_unref(caps);
    if (bun && s->segment) {
        /* segmentul tinut pleaca dupa caps (stream-start, caps, segment) */
        GstEvent *seg = s->segment;
        s->segment = NULL;
        gst_pad_push_event(s->srcpad, seg);
    }
    GST_INFO_OBJECT(s, "AC3 %d Hz, %d canale, %d b/s, %s", rata, asezare->nb_channels, s->debit, c->name);
    return bun;
}

/* ---------------------------------------------------------------- coada si codarea */

/* Esantioanele cadrului decodat in coada (trecute in formatul codorului daca e nevoie). */
static gboolean coada_pune(GstHdsDtsAc3 *s, AVFrame *f)
{
    enum AVSampleFormat fel = s->enc->sample_fmt;
    int n = f->nb_samples, ch = f->ch_layout.nb_channels;
    if (f->format == fel)
        return av_audio_fifo_write(s->coada, (void **)f->extended_data, n) == n;
    /* S32P <-> FLTP, plan cu plan */
    void **planuri = g_new0(void *, ch);
    for (int c = 0; c < ch; c++) {
        planuri[c] = g_malloc((gsize)n * 4);
        if (f->format == AV_SAMPLE_FMT_S32P && fel == AV_SAMPLE_FMT_FLTP) {
            const gint32 *in = (const gint32 *)f->extended_data[c];
            float *out = planuri[c];
            for (int i = 0; i < n; i++)
                out[i] = (float)in[i] * (1.0f / 2147483648.0f);
        } else if (f->format == AV_SAMPLE_FMT_FLTP && fel == AV_SAMPLE_FMT_S32P) {
            const float *in = (const float *)f->extended_data[c];
            gint32 *out = planuri[c];
            for (int i = 0; i < n; i++) {
                float v = in[i];
                out[i] = v >= 1.0f ? G_MAXINT32 : v <= -1.0f ? G_MININT32 : (gint32)(v * 2147483648.0f);
            }
        } else {
            for (int k = 0; k <= c; k++)
                g_free(planuri[k]);
            g_free(planuri);
            GST_ELEMENT_ERROR(s, STREAM, FORMAT, ("Formatul esantioanelor DTS (%d) nu e cunoscut.", f->format), (NULL));
            return FALSE;
        }
    }
    gboolean bun = av_audio_fifo_write(s->coada, planuri, n) == n;
    for (int c = 0; c < ch; c++)
        g_free(planuri[c]);
    g_free(planuri);
    return bun;
}

/* Pachetele codorului ca buffere GstBuffer, cu marcajul cozii. */
static GstFlowReturn codor_scoate(GstHdsDtsAc3 *s)
{
    GstFlowReturn ret = GST_FLOW_OK;
    AVPacket *p = av_packet_alloc();
    while (ret == GST_FLOW_OK && avcodec_receive_packet(s->enc, p) == 0) {
        GstBuffer *b = gst_buffer_new_allocate(NULL, (gsize)p->size, NULL);
        gst_buffer_fill(b, 0, p->data, (gsize)p->size);
        GstClockTime durata = gst_util_uint64_scale_int(s->enc->frame_size, GST_SECOND, s->rata);
        GST_BUFFER_PTS(b) = s->pts_coada;
        GST_BUFFER_DURATION(b) = durata;
        if (s->discont) {
            GST_BUFFER_FLAG_SET(b, GST_BUFFER_FLAG_DISCONT);
            GST_DEBUG_OBJECT(s, "DISCONT la %" GST_TIME_FORMAT, GST_TIME_ARGS(s->pts_coada));
            s->discont = FALSE;
        }
        if (GST_CLOCK_TIME_IS_VALID(s->pts_coada))
            s->pts_coada += durata;
        av_packet_unref(p);
        ret = gst_pad_push(s->srcpad, b);
    }
    av_packet_free(&p);
    return ret;
}

/* Cat sunt in coada cadre AC3 intregi, le codeaza (cu liniste la sfarsit cand `tot`). */
static GstFlowReturn coada_codeaza(GstHdsDtsAc3 *s, gboolean tot)
{
    GstFlowReturn ret = GST_FLOW_OK;
    int cadru = s->enc->frame_size;
    while (ret == GST_FLOW_OK && (av_audio_fifo_size(s->coada) >= cadru || (tot && av_audio_fifo_size(s->coada) > 0))) {
        if (av_frame_make_writable(s->cadru_enc) < 0)
            return GST_FLOW_ERROR;
        int n = av_audio_fifo_read(s->coada, (void **)s->cadru_enc->extended_data, cadru);
        if (n < cadru)
            av_samples_set_silence(s->cadru_enc->extended_data, n, cadru - n, s->asezare.nb_channels, s->enc->sample_fmt);
        int r = avcodec_send_frame(s->enc, s->cadru_enc);
        if (r < 0) {
            eroare_av(s, "codarea AC3", r);
            return GST_FLOW_ERROR;
        }
        ret = codor_scoate(s);
    }
    return ret;
}

/* ---------------------------------------------------------------- intrarea */

static GstFlowReturn cadru_decodat(GstHdsDtsAc3 *s, AVFrame *f, GstClockTime pts)
{
    if (!s->rata || f->sample_rate != s->rata || av_channel_layout_compare(&f->ch_layout, &s->asezare)) {
        /* primul cadru sau alt format: ce era in coada pleaca intai, apoi codorul nou */
        GstFlowReturn ret = s->rata ? coada_codeaza(s, TRUE) : GST_FLOW_OK;
        if (ret != GST_FLOW_OK)
            return ret;
        if (!codor_deschide(s, f->sample_rate, &f->ch_layout)) {
            s->eroare = TRUE;
            return GST_FLOW_NOT_NEGOTIATED;
        }
        s->pts_coada = GST_CLOCK_TIME_NONE;
    }
    /* marcajul cozii se ia din intrare numai la inceput (sau dupa un salt): altfel creste exact cu cadrele AC3, fara
     * rotunjirile marcajelor DTS (512 esantioane = 10,666... ms) */
    int in_coada = av_audio_fifo_size(s->coada);
    if (GST_CLOCK_TIME_IS_VALID(pts)) {
        if (!GST_CLOCK_TIME_IS_VALID(s->pts_coada)) {
            s->pts_coada = pts - MIN(pts, gst_util_uint64_scale_int(in_coada, GST_SECOND, s->rata));
        } else {
            GstClockTime asteptat = s->pts_coada + gst_util_uint64_scale_int(in_coada, GST_SECOND, s->rata);
            GstClockTimeDiff d = GST_CLOCK_DIFF(asteptat, pts);
            if (d > (GstClockTimeDiff)SALT_MAXIM || d < -(GstClockTimeDiff)SALT_MAXIM) {
                GST_INFO_OBJECT(s, "salt de %" G_GINT64_FORMAT " ms: coada golita", d / GST_MSECOND);
                av_audio_fifo_reset(s->coada);
                s->pts_coada = pts;
                s->discont = TRUE;
            }
        }
    }
    if (!coada_pune(s, f))
        return GST_FLOW_ERROR;
    return coada_codeaza(s, FALSE);
}

static GstFlowReturn hds_chain(GstPad *pad, GstObject *parinte, GstBuffer *buf)
{
    (void)pad;
    GstHdsDtsAc3 *s = GST_HDS_DTS_AC3(parinte);
    GstFlowReturn ret = GST_FLOW_OK;
    if (s->eroare) {
        gst_buffer_unref(buf);
        return GST_FLOW_NOT_NEGOTIATED;
    }
    if (!s->dec && !decodor_deschide(s)) {
        gst_buffer_unref(buf);
        return GST_FLOW_ERROR;
    }
    if (GST_BUFFER_FLAG_IS_SET(buf, GST_BUFFER_FLAG_DISCONT))
        s->discont = TRUE;
    GstClockTime pts = GST_BUFFER_PTS(buf);
    GstMapInfo m;
    if (!gst_buffer_map(buf, &m, GST_MAP_READ)) {
        gst_buffer_unref(buf);
        return GST_FLOW_ERROR;
    }
    int r = av_new_packet(s->pachet, (int)m.size);
    if (r == 0)
        memcpy(s->pachet->data, m.data, m.size);
    gst_buffer_unmap(buf, &m);
    gst_buffer_unref(buf);
    if (r < 0)
        return GST_FLOW_ERROR;
    r = avcodec_send_packet(s->dec, s->pachet);
    av_packet_unref(s->pachet);
    if (r < 0) {
        /* un cadru stricat (semnal, fisier taiat) se sare, ca la decodoarele obisnuite */
        eroare_av(s, "cadrul DTS", r);
        return GST_FLOW_OK;
    }
    while (ret == GST_FLOW_OK && avcodec_receive_frame(s->dec, s->cadru_dec) == 0) {
        ret = cadru_decodat(s, s->cadru_dec, pts);
        pts = GST_CLOCK_TIME_NONE;         /* un al doilea cadru din acelasi buffer ia marcajul din coada */
        av_frame_unref(s->cadru_dec);
    }
    return ret;
}

static void uita(GstHdsDtsAc3 *s)
{
    GST_DEBUG_OBJECT(s, "golire: coada, decodorul si codorul uitate");
    if (s->dec)
        avcodec_flush_buffers(s->dec);
    codor_inchide(s);                       /* codorul AC3 nu se poate goli: se face din nou la cadrul urmator */
    s->pts_coada = GST_CLOCK_TIME_NONE;
    s->discont = TRUE;
    s->eroare = FALSE;
}

static gboolean hds_eveniment(GstPad *pad, GstObject *parinte, GstEvent *ev)
{
    GstHdsDtsAc3 *s = GST_HDS_DTS_AC3(parinte);
    switch (GST_EVENT_TYPE(ev)) {
    case GST_EVENT_CAPS:
        /* caps-urile iesirii se pun la primul cadru decodat (rata si canalele nucleului DTS) */
        gst_event_unref(ev);
        return TRUE;
    case GST_EVENT_SEGMENT:
        if (!gst_pad_has_current_caps(s->srcpad)) {
            gst_event_replace(&s->segment, ev);
            gst_event_unref(ev);
            return TRUE;
        }
        break;
    case GST_EVENT_FLUSH_STOP:
        uita(s);
        break;
    case GST_EVENT_EOS:
        if (s->rata && !s->eroare)
            coada_codeaza(s, TRUE);
        if (s->segment && !gst_pad_has_current_caps(s->srcpad))
            gst_event_replace(&s->segment, NULL);   /* niciun cadru decodat: fara caps, fara segment */
        break;
    default:
        break;
    }
    return gst_pad_event_default(pad, parinte, ev);
}

static GstStateChangeReturn hds_stare(GstElement *e, GstStateChange t)
{
    GstHdsDtsAc3 *s = GST_HDS_DTS_AC3(e);
    GstStateChangeReturn r = GST_ELEMENT_CLASS(gst_hds_dts_ac3_parent_class)->change_state(e, t);
    if (t == GST_STATE_CHANGE_PAUSED_TO_READY) {
        toate_inchide(s);
        gst_event_replace(&s->segment, NULL);
        s->pts_coada = GST_CLOCK_TIME_NONE;
        s->discont = FALSE;
        s->eroare = FALSE;
    }
    return r;
}

/* ---------------------------------------------------------------- proprietati si clasa */

static void hds_set(GObject *o, guint id, const GValue *v, GParamSpec *ps)
{
    GstHdsDtsAc3 *s = GST_HDS_DTS_AC3(o);
    if (id == PROP_BITRATE)
        s->debit = g_value_get_int(v);
    else
        G_OBJECT_WARN_INVALID_PROPERTY_ID(o, id, ps);
}

static void hds_get(GObject *o, guint id, GValue *v, GParamSpec *ps)
{
    GstHdsDtsAc3 *s = GST_HDS_DTS_AC3(o);
    if (id == PROP_BITRATE)
        g_value_set_int(v, s->debit);
    else
        G_OBJECT_WARN_INVALID_PROPERTY_ID(o, id, ps);
}

static void hds_finalize(GObject *o)
{
    toate_inchide(GST_HDS_DTS_AC3(o));
    gst_event_replace(&GST_HDS_DTS_AC3(o)->segment, NULL);
    G_OBJECT_CLASS(gst_hds_dts_ac3_parent_class)->finalize(o);
}

static void gst_hds_dts_ac3_class_init(GstHdsDtsAc3Class *k)
{
    GObjectClass *ok = G_OBJECT_CLASS(k);
    GstElementClass *ek = GST_ELEMENT_CLASS(k);
    ok->set_property = hds_set;
    ok->get_property = hds_get;
    ok->finalize = hds_finalize;
    g_object_class_install_property(ok, PROP_BITRATE, g_param_spec_int("bitrate", "Debitul AC3",
        "Debitul AC3 in biti pe secunda", DEBIT_MINIM, DEBIT_MAXIM, DEBIT_IMPLICIT,
        G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS));
    ek->change_state = hds_stare;
    gst_element_class_add_static_pad_template(ek, &sink_sablon);
    gst_element_class_add_static_pad_template(ek, &src_sablon);
    gst_element_class_set_static_metadata(ek, "DTS recodat in AC3", "Codec/Decoder/Audio",
        "Decodeaza nucleul DTS si il codeaza in AC3 pentru iesirea digitala", "Monea Software pentru HD Satelit");
}

static void gst_hds_dts_ac3_init(GstHdsDtsAc3 *s)
{
    s->sinkpad = gst_pad_new_from_static_template(&sink_sablon, "sink");
    gst_pad_set_chain_function(s->sinkpad, GST_DEBUG_FUNCPTR(hds_chain));
    gst_pad_set_event_function(s->sinkpad, GST_DEBUG_FUNCPTR(hds_eveniment));
    gst_element_add_pad(GST_ELEMENT(s), s->sinkpad);
    s->srcpad = gst_pad_new_from_static_template(&src_sablon, "src");
    gst_pad_use_fixed_caps(s->srcpad);
    gst_element_add_pad(GST_ELEMENT(s), s->srcpad);
    s->debit = DEBIT_IMPLICIT;
    s->pts_coada = GST_CLOCK_TIME_NONE;
}

static gboolean plugin_init(GstPlugin *p)
{
    GST_DEBUG_CATEGORY_INIT(hdsdtsac3_debug, "hdsdtsac3", 0, "DTS recodat in AC3");
    return gst_element_register(p, "hdsdtsac3", GST_RANK_PRIMARY + 1, GST_TYPE_HDS_DTS_AC3);
}

#ifndef VERSIUNE
#define VERSIUNE "1.0"
#endif
#ifndef PACKAGE
#define PACKAGE "hdsdtsac3"
#endif

/* macroul lasa campurile rezervate ale descrierii neinitializate (cu -Wextra: avertisment, nu greseala) */
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wmissing-field-initializers"
GST_PLUGIN_DEFINE(GST_VERSION_MAJOR, GST_VERSION_MINOR, hdsdtsac3, "DTS recodat in AC3 pentru iesirea digitala",
    plugin_init, VERSIUNE, "GPL", "hdsdtsac3", "https://hdsatelit.com")
#pragma GCC diagnostic pop
