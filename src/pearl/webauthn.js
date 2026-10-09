// Passkeys in the browser: turn the server's JSON options into the binary
// shapes navigator.credentials wants, and the result back into JSON.
// Written out rather than using the newer PublicKeyCredential.parse*FromJSON
// helpers, which older Safari and Firefox don't have.

const toBytes = (b64url) => {
  const b64 = b64url.replace(/-/g, '+').replace(/_/g, '/')
    .padEnd(Math.ceil(b64url.length / 4) * 4, '=');
  return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
};

const toB64url = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf)))
  .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

export function passkeysSupported() {
  return typeof window !== 'undefined' && !!window.PublicKeyCredential
    && !!navigator.credentials?.create;
}

export async function createPasskey(options, signal) {
  const publicKey = {
    ...options,
    challenge: toBytes(options.challenge),
    user: { ...options.user, id: toBytes(options.user.id) },
    excludeCredentials: (options.excludeCredentials ?? []).map((c) => ({
      ...c, id: toBytes(c.id) })),
  };
  const cred = await navigator.credentials.create({ publicKey, signal });
  return {
    id: cred.id,
    rawId: toB64url(cred.rawId),
    type: cred.type,
    response: {
      clientDataJSON: toB64url(cred.response.clientDataJSON),
      attestationObject: toB64url(cred.response.attestationObject),
      transports: cred.response.getTransports?.() ?? [],
    },
    clientExtensionResults: cred.getClientExtensionResults?.() ?? {},
  };
}

export async function getPasskey(options, signal) {
  const publicKey = {
    ...options,
    challenge: toBytes(options.challenge),
    allowCredentials: (options.allowCredentials ?? []).map((c) => ({
      ...c, id: toBytes(c.id) })),
  };
  const cred = await navigator.credentials.get({ publicKey, signal });
  return {
    id: cred.id,
    rawId: toB64url(cred.rawId),
    type: cred.type,
    response: {
      clientDataJSON: toB64url(cred.response.clientDataJSON),
      authenticatorData: toB64url(cred.response.authenticatorData),
      signature: toB64url(cred.response.signature),
      userHandle: cred.response.userHandle ? toB64url(cred.response.userHandle) : null,
    },
    clientExtensionResults: cred.getClientExtensionResults?.() ?? {},
  };
}
