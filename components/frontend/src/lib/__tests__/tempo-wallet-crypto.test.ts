import { describe, expect, it } from 'vitest';

import {
  decryptPrivateKey,
  encryptPrivateKey,
  generatePrivateKey,
  privateKeyToAddress,
  privateKeyToHex
} from '../tempo-wallet-crypto';

// Real WebCrypto is provided by jsdom + Node's globalThis.crypto.

describe('tempo-wallet-crypto', () => {
  describe('generatePrivateKey', () => {
    it('returns 32 random bytes', () => {
      const a = generatePrivateKey();
      const b = generatePrivateKey();
      expect(a).toHaveLength(32);
      expect(b).toHaveLength(32);
      expect(a).not.toEqual(b);
    });
  });

  describe('privateKeyToAddress', () => {
    // Fixture: viem's documented test key.
    // 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
    // -> 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266 (well-known anvil/hardhat key 0)
    /* eslint-disable unicorn/number-literal-case -- prettier requires lowercase hex */
    const fixtureKey = new Uint8Array([
      0xac, 0x09, 0x74, 0xbe, 0xc3, 0x9a, 0x17, 0xe3, 0x6b, 0xa4, 0xa6, 0xb4, 0xd2, 0x38, 0xff,
      0x94, 0x4b, 0xac, 0xb4, 0x78, 0xcb, 0xed, 0x5e, 0xfc, 0xae, 0x78, 0x4d, 0x7b, 0xf4, 0xf2,
      0xff, 0x80
    ]);
    /* eslint-enable unicorn/number-literal-case */

    it('derives the expected EIP-55 checksummed address', () => {
      const address = privateKeyToAddress(fixtureKey);
      expect(address).toBe('0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266');
    });

    it('hex-encodes the private key with 0x prefix', () => {
      expect(privateKeyToHex(fixtureKey)).toBe(
        '0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80'
      );
    });

    it('rejects keys of wrong length', () => {
      expect(() => privateKeyToHex(new Uint8Array(31))).toThrow();
    });
  });

  describe('encrypt/decrypt round trip', () => {
    it('decrypts back to the original private key', async () => {
      const key = generatePrivateKey();
      const blob = await encryptPrivateKey(key, 'correct horse battery staple');
      const recovered = await decryptPrivateKey(blob, 'correct horse battery staple');
      expect([...recovered]).toEqual([...key]);
    });

    it('produces a different blob each call (random salt + nonce)', async () => {
      const key = generatePrivateKey();
      const a = await encryptPrivateKey(key, 'pw');
      const b = await encryptPrivateKey(key, 'pw');
      expect(a).not.toEqual(b);
    });

    it('fails to decrypt with the wrong passphrase (GCM auth tag mismatch)', async () => {
      const key = generatePrivateKey();
      const blob = await encryptPrivateKey(key, 'right');
      await expect(decryptPrivateKey(blob, 'wrong')).rejects.toThrow();
    });

    it('rejects an obviously truncated blob', async () => {
      await expect(decryptPrivateKey('AAAA', 'pw')).rejects.toThrow();
    });

    it('rejects encrypting a wrong-length key', async () => {
      await expect(encryptPrivateKey(new Uint8Array(16), 'pw')).rejects.toThrow();
    });
  });
});
