import type { ParsedChallenge } from '../tempo-wallet-mpp';

import { describe, expect, it } from 'vitest';

import { buildCredential, parseChallenge, parseTokenAmount } from '../tempo-wallet-mpp';

function base64UrlEncode(s: string): string {
  return globalThis.btoa(s).replaceAll('+', '-').replaceAll('/', '_').replaceAll('=', '');
}

function base64UrlDecode(s: string): string {
  const pad = (4 - (s.length % 4)) % 4;
  return globalThis.atob(s.replaceAll('-', '+').replaceAll('_', '/') + '='.repeat(pad));
}

describe('parseChallenge', () => {
  const requestPayload = {
    amount: '0.10',
    currency: '0xCAFEbabeCAFEbabeCAFEbabeCAFEbabeCAFEbabe',
    recipient: '0xBEEFbeefBEEFbeefBEEFbeefBEEFbeefBEEFbeef'
  };
  const requestB64 = base64UrlEncode(JSON.stringify(requestPayload));
  const header = [
    `Payment id="abc"`,
    `realm="x"`,
    `method="tempo"`,
    `intent="charge"`,
    `request="${requestB64}"`,
    `expires="2026-01-01T00:00:00Z"`
  ].join(', ');

  it('parses all required fields', () => {
    const c = parseChallenge(header);
    expect(c.id).toBe('abc');
    expect(c.realm).toBe('x');
    expect(c.method).toBe('tempo');
    expect(c.intent).toBe('charge');
    expect(c.request).toBe(requestB64);
    expect(c.expires).toBe('2026-01-01T00:00:00Z');
    expect(c.amount).toBe('0.10');
    expect(c.currency).toBe(requestPayload.currency);
    expect(c.recipient).toBe(requestPayload.recipient);
  });

  it('is case-insensitive on the "Payment" prefix', () => {
    const c = parseChallenge(header.replace(/^Payment/, 'payment'));
    expect(c.id).toBe('abc');
  });

  it('throws on missing prefix', () => {
    expect(() => parseChallenge('Bearer foo=bar')).toThrow(/missing "Payment " prefix/);
  });

  it('throws on missing required parameter', () => {
    const stripped = header.replace(/, expires="[^"]*"/, '');
    expect(() => parseChallenge(stripped)).toThrow(/missing required parameter: expires/);
  });

  it('throws when request is not valid base64url JSON', () => {
    const broken = header.replace(/request="[^"]*"/, 'request="not-base64-{}{}"');
    expect(() => parseChallenge(broken)).toThrow(/invalid base64url JSON/);
  });

  it('throws when request JSON is missing currency', () => {
    const badPayload = base64UrlEncode(JSON.stringify({ amount: '1', recipient: '0xabc' }));
    const bad = header.replace(/request="[^"]*"/, `request="${badPayload}"`);
    expect(() => parseChallenge(bad)).toThrow();
  });

  it('tolerates numeric amounts in the request payload', () => {
    const numericPayload = base64UrlEncode(JSON.stringify({ ...requestPayload, amount: 0.42 }));
    const numeric = header.replace(/request="[^"]*"/, `request="${numericPayload}"`);
    const parsed = parseChallenge(numeric);
    expect(parsed.amount).toBe('0.42');
  });
});

describe('buildCredential', () => {
  const challenge: ParsedChallenge = {
    id: 'abc',
    realm: 'x',
    method: 'tempo',
    intent: 'charge',
    request: 'eyJmb28iOiJiYXIifQ', // base64url of {"foo":"bar"}
    expires: '2026-01-01T00:00:00Z',
    amount: '0.10',
    currency: '0xCAFEbabeCAFEbabeCAFEbabeCAFEbabeCAFEbabe',
    recipient: '0xBEEFbeefBEEFbeefBEEFbeefBEEFbeefBEEFbeef'
  };

  it('produces a "Payment <base64url>" string echoing the challenge and tx hash', () => {
    const cred = buildCredential({
      challenge,
      txHash: '0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef',
      signerAddress: '0xAbCdEf0123456789AbCdEf0123456789AbCdEf01',
      chainId: 42_431
    });

    expect(cred.startsWith('Payment ')).toBe(true);
    const body = JSON.parse(base64UrlDecode(cred.slice('Payment '.length))) as {
      challenge: { id: string; request: string };
      payload: { type: string; signature: string };
      source: string;
    };
    expect(body.challenge.id).toBe('abc');
    expect(body.challenge.request).toBe(challenge.request);
    expect(body.payload.type).toBe('transaction');
    expect(body.payload.signature).toBe(
      '0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef'
    );
    expect(body.source).toBe('did:pkh:eip155:42431:0xAbCdEf0123456789AbCdEf0123456789AbCdEf01');
  });
});

describe('parseTokenAmount', () => {
  it('handles integer amounts', () => {
    expect(parseTokenAmount('5', 6)).toBe(5_000_000n);
  });

  it('handles fractional amounts', () => {
    expect(parseTokenAmount('0.10', 6)).toBe(100_000n);
    expect(parseTokenAmount('1.234567', 6)).toBe(1_234_567n);
  });

  it('zero-pads short fractions', () => {
    expect(parseTokenAmount('0.1', 6)).toBe(100_000n);
  });

  it('rejects too many fractional digits', () => {
    expect(() => parseTokenAmount('0.1234567', 6)).toThrow();
  });

  it('rejects garbage', () => {
    expect(() => parseTokenAmount('abc', 6)).toThrow();
    expect(() => parseTokenAmount('1.2.3', 6)).toThrow();
  });
});
