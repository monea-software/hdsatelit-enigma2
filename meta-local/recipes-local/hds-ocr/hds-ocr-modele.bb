SUMMARY = "HDSatelit: modelele tessdata_fast pentru hds-ocr"
DESCRIPTION = "Modelele LSTM rapide (tessdata_fast, Apache-2.0) pentru hds-ocr, in /usr/share/hds-ocr/tessdata. \
Fiecare limba e pachet separat (hds-ocr-modele-<model>). hds-ocr-modele aduce in imagine numai limbile cu cele mai \
multe subtitrari DVB (HDS_OCR_IMAGINE, 23,9 MB) si lista modelelor care se descarca la cerere de pe receptor \
(hds-ocr-modele-lista: /usr/share/hds-ocr/modele.json cu marimea si sha256 al fiecaruia, plus LICENSE). \
Fisierele sunt luate individual de la commitul fix al depozitului tessdata_fast (nu tot depozitul)."
LICENSE = "Apache-2.0"
TESSDATA_REV = "87416418657359cb625c412a48b6e1d6d41c29bd"
LIC_FILES_CHKSUM = "file://tessdata_fast-${TESSDATA_REV}-LICENSE;md5=3b83ef96387f14655fc854ddc3c6bd57"
PV = "4.1.0+git87416418"
PR = "r1"

TD_URL = "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/${TESSDATA_REV}"
TD_DL = "downloadfilename=tessdata_fast-${TESSDATA_REV}"
SRC_URI = "file://hds-ocr-modele.json \
           ${TD_URL}/LICENSE;name=license;${TD_DL}-LICENSE \
           ${TD_URL}/ron.traineddata;name=ron;${TD_DL}-ron.traineddata \
           ${TD_URL}/eng.traineddata;name=eng;${TD_DL}-eng.traineddata \
           ${TD_URL}/deu.traineddata;name=deu;${TD_DL}-deu.traineddata \
           ${TD_URL}/fra.traineddata;name=fra;${TD_DL}-fra.traineddata \
           ${TD_URL}/ita.traineddata;name=ita;${TD_DL}-ita.traineddata \
           ${TD_URL}/spa.traineddata;name=spa;${TD_DL}-spa.traineddata \
           ${TD_URL}/hun.traineddata;name=hun;${TD_DL}-hun.traineddata \
           ${TD_URL}/pol.traineddata;name=pol;${TD_DL}-pol.traineddata \
           ${TD_URL}/ces.traineddata;name=ces;${TD_DL}-ces.traineddata \
           ${TD_URL}/nld.traineddata;name=nld;${TD_DL}-nld.traineddata \
           ${TD_URL}/por.traineddata;name=por;${TD_DL}-por.traineddata \
           ${TD_URL}/rus.traineddata;name=rus;${TD_DL}-rus.traineddata \
           ${TD_URL}/tur.traineddata;name=tur;${TD_DL}-tur.traineddata"
SRC_URI[license.sha256sum] = "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"
SRC_URI[ron.sha256sum] = "9adfde6b51ba4b97efd10ea37c3070fd3fc2bad7815e81f5c3c198cd96216cc9"
SRC_URI[eng.sha256sum] = "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2"
SRC_URI[deu.sha256sum] = "19d219bbb6672c869d20a9636c6816a81eb9a71796cb93ebe0cb1530e2cdb22d"
SRC_URI[fra.sha256sum] = "ced037562e8c80c13122dece28dd477d399af80911a28791a66a63ac1e3445ca"
SRC_URI[ita.sha256sum] = "b8f89e1e785118dac4d51ae042c029a64edb5c3ee42ef73027a6d412748d8827"
SRC_URI[spa.sha256sum] = "6f2e04d02774a18f01bed44b1111f2cd7f3ba7ac9dc4373cd3f898a40ea6b464"
SRC_URI[hun.sha256sum] = "35067e7cfe102dcdc953f9a758fdfaa6296b17a1ee6d874ee780fa306430b9fb"
SRC_URI[pol.sha256sum] = "c4476cdbc0e33d898d32345122b7be1cbf85ace15f920f06c7714756e1ef79b2"
SRC_URI[ces.sha256sum] = "934bcaf97ef3348413263331131c9fa7f55f30db333c711929c124fb635f7e1b"
SRC_URI[nld.sha256sum] = "ced0e5e046a84c908a6aa7accbef9a232c4a5d9a8276691b81c6ee64d02963f6"
SRC_URI[por.sha256sum] = "c4932b937207a9514b7514d518b931a99938c02a28a5a5a553f8599ed58b7deb"
SRC_URI[rus.sha256sum] = "e16e5e036cce1d9ec2b00063cf8b54472625b9e14d893a169e2b0dedeb4df225"
SRC_URI[tur.sha256sum] = "7393381111e1152420fc4092cb44eef4237580d21b92bf30d7d221aad192c6b7"

S = "${UNPACKDIR}"

inherit allarch

# modelele facute ca pachete (cate unul pe limba, pentru un feed); in imagine intra numai HDS_OCR_IMAGINE, prin
# hds-ocr-modele. Celelalte limbi din lista (hds-ocr-modele.json) se descarca pe receptor la cerere, direct de la
# commitul fix, verificate cu sha256 din lista (Components/HdsOcrModele.py).
HDS_OCR_LANGS = "ron eng deu fra ita spa hun pol ces nld por rus tur"
HDS_OCR_IMAGINE = "ron fra pol deu ces hun spa ita"

do_configure[noexec] = "1"
do_compile[noexec] = "1"

do_install() {
    install -d ${D}${datadir}/hds-ocr/tessdata
    for l in ${HDS_OCR_LANGS}; do
        install -m 0644 ${S}/tessdata_fast-${TESSDATA_REV}-$l.traineddata ${D}${datadir}/hds-ocr/tessdata/$l.traineddata
    done
    install -m 0644 ${S}/hds-ocr-modele.json ${D}${datadir}/hds-ocr/modele.json
    install -m 0644 ${S}/tessdata_fast-${TESSDATA_REV}-LICENSE ${D}${datadir}/hds-ocr/LICENSE
}

# proba care cade: lista din imagine are acelasi commit, aceleasi sha256 pentru modelele facute aici si aceeasi
# licenta; limbile din imagine sunt aceleasi in reteta si in lista
python hds_ocr_verifica_lista() {
    import hashlib, json, os
    D = d.getVar('D')
    base = os.path.join(D, d.getVar('datadir').lstrip('/'), 'hds-ocr')
    with open(os.path.join(base, 'modele.json')) as f:
        lista = json.load(f)
    def sha(p):
        h = hashlib.sha256()
        with open(p, 'rb') as f:
            for b in iter(lambda: f.read(1 << 20), b''):
                h.update(b)
        return h.hexdigest()
    if lista.get('commit') != d.getVar('TESSDATA_REV'):
        bb.fatal('hds-ocr-modele.json: alt commit (%s)' % lista.get('commit'))
    if lista.get('licenta_sha256') != sha(os.path.join(base, 'LICENSE')):
        bb.fatal('hds-ocr-modele.json: sha256 al licentei nu se potriveste')
    for l in d.getVar('HDS_OCR_LANGS').split():
        m = lista.get('modele', {}).get(l)
        p = os.path.join(base, 'tessdata', l + '.traineddata')
        if not m or m.get('sha256') != sha(p) or m.get('marime') != os.path.getsize(p):
            bb.fatal('hds-ocr-modele.json: modelul %s lipseste sau nu se potriveste' % l)
    if sorted(lista.get('in_imagine') or []) != sorted(d.getVar('HDS_OCR_IMAGINE').split()):
        bb.fatal('hds-ocr-modele.json: in_imagine difera de HDS_OCR_IMAGINE')
}
do_install[postfuncs] += "hds_ocr_verifica_lista"

python () {
    pn = d.getVar('PN')
    pkgs = []
    for l in d.getVar('HDS_OCR_LANGS').split():
        p = '%s-%s' % (pn, l)
        pkgs.append(p)
        d.setVar('FILES:' + p, '${datadir}/hds-ocr/tessdata/%s.traineddata' % l)
        d.setVar('SUMMARY:' + p, 'Modelul tessdata_fast %s pentru hds-ocr' % l)
    d.setVar('PACKAGES', pn + ' ' + pn + '-lista ' + ' '.join(pkgs))
    d.setVar('RDEPENDS:' + pn, ' '.join(['%s-%s' % (pn, l) for l in d.getVar('HDS_OCR_IMAGINE').split()] + [pn + '-lista']))
}

ALLOW_EMPTY:${PN} = "1"
FILES:${PN} = ""
SUMMARY:${PN}-lista = "Lista modelelor OCR care se descarca la cerere (marimea, sha256) si licenta lor"
FILES:${PN}-lista = "${datadir}/hds-ocr/modele.json ${datadir}/hds-ocr/LICENSE"
