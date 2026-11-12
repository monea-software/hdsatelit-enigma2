/* Din sursele GPL enigma2 (OE-Alliance), commitul 29d951a6ec2e019680741efdad5ca7e7902b20e4, lib/dvb_ci/aes_xcbc_mac.cpp;
   licenta GPLv2 a enigma2. Modificat de moneasoftware.com si hdsatelit.com, 2026: numai legarea de slotul si
   jurnalul nostru (dvbci_hds_compat.h). */
#include <lib/dvb_ci/dvbci_hds_compat.h>
#include <stdint.h>
#include <string.h>
#include <openssl/evp.h>

#include "aes_xcbc_mac.h"

int aes_xcbc_mac_init(struct aes_xcbc_mac_ctx *ctx, const uint8_t *key)
{
	int y, x;
	int outlen;

	EVP_CIPHER_CTX *tmp = EVP_CIPHER_CTX_new();
	EVP_EncryptInit_ex(tmp, EVP_aes_128_ecb(), nullptr, key, nullptr);
	EVP_CIPHER_CTX_set_padding(tmp, 0);

	for (y = 0; y < 3; y++) {
		for (x = 0; x < 16; x++)
			ctx->K[y][x] = y + 1;
		EVP_EncryptUpdate(tmp, ctx->K[y], &outlen, ctx->K[y], 16);
	}

	EVP_CIPHER_CTX_free(tmp);

	/* setup K1 */
	ctx->key = EVP_CIPHER_CTX_new();
	EVP_EncryptInit_ex(ctx->key, EVP_aes_128_ecb(), nullptr, ctx->K[0], nullptr);
	EVP_CIPHER_CTX_set_padding(ctx->key, 0);

	memset(ctx->IV, 0, 16);
	ctx->buflen = 0;

	return 0;
}

int aes_xcbc_mac_process(struct aes_xcbc_mac_ctx *ctx, const uint8_t *in, unsigned int len)
{
	int outlen;

	while (len) {
		if (ctx->buflen == 16) {
			EVP_EncryptUpdate(ctx->key, ctx->IV, &outlen, ctx->IV, 16);
			ctx->buflen = 0;
		}
		ctx->IV[ctx->buflen++] ^= *in++;
		--len;
	}

	return 0;
}

int aes_xcbc_mac_done(struct aes_xcbc_mac_ctx *ctx, uint8_t *out)
{
	int i;
	int outlen;

	if (ctx->buflen == 16) {
		/* K2 */
		for (i = 0; i < 16; i++)
			ctx->IV[i] ^= ctx->K[1][i];
	} else {
		ctx->IV[ctx->buflen] ^= 0x80;
		/* K3 */
		for (i = 0; i < 16; i++)
			ctx->IV[i] ^= ctx->K[2][i];
	}

	EVP_EncryptUpdate(ctx->key, ctx->IV, &outlen, ctx->IV, 16);
	memcpy(out, ctx->IV, 16);

	EVP_CIPHER_CTX_free(ctx->key);
	ctx->key = nullptr;

	return 0;
}
