const fs = require("fs");
const crypto = require("crypto");

const [clientId, privateKeyPath, audience] = process.argv.slice(2);

if (!clientId || !privateKeyPath || !audience) {
  throw new Error("Usage: node community-care-ccg-assertion.js <clientId> <privateKeyPath> <audience>");
}

const privateKey = fs.readFileSync(privateKeyPath, "utf8");
const now = Math.floor(Date.now() / 1000);

const header = { alg: "RS256", typ: "JWT" };

const payload = {
  aud: audience,
  iss: clientId,
  sub: clientId,
  iat: now,
  exp: now + 300,
  jti: crypto.randomUUID(),
};

function base64url(value) {
  return Buffer.from(value)
    .toString("base64")
    .replace(/=/g, "")
    .replace(/\+/g, "-")
    .replace(/\//g, "_");
}

const encodedHeader = base64url(JSON.stringify(header));
const encodedPayload = base64url(JSON.stringify(payload));
const signingInput = encodedHeader + "." + encodedPayload;

const signature = crypto.sign("RSA-SHA256", Buffer.from(signingInput), privateKey);
const encodedSignature = signature
  .toString("base64")
  .replace(/=/g, "")
  .replace(/\+/g, "-")
  .replace(/\//g, "_");

const clientAssertion = signingInput + "." + encodedSignature;

process.stdout.write(JSON.stringify({ clientAssertion }));
