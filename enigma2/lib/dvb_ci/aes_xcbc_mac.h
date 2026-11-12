/* Din sursele GPL enigma2 (OE-Alliance), commitul 29d951a6ec2e019680741efdad5ca7e7902b20e4, lib/dvb_ci/aes_xcbc_mac.h;
   licenta GPLv2 a enigma2. Modificat de moneasoftware.com si hdsatelit.com, 2026: numai legarea de slotul si
   jurnalul nostru (dvbci_hds_compat.h). */
#ifndef __AES_XCBC_H_
#define __AES_XCBC_H_

#include <openssl/evp.h>

struct aes_xcbc_mac_ctx {
	uint8_t K[3][16];
	uint8_t IV[16];
	EVP_CIPHER_CTX *key;
	int buflen;
};

int aes_xcbc_mac_init(struct aes_xcbc_mac_ctx *ctx, const uint8_t *key);
int aes_xcbc_mac_process(struct aes_xcbc_mac_ctx *ctx, const uint8_t *in, unsigned int len);
int aes_xcbc_mac_done(struct aes_xcbc_mac_ctx *ctx, uint8_t *out);

#endif
