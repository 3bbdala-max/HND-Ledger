// Independent JavaScript RFC 8785 implementation cross-check.
const fs = require("node:fs");
const canonicalize = require("canonicalize");
const rawInputs = JSON.parse(fs.readFileSync(0, "utf8"));
if (!Array.isArray(rawInputs) || rawInputs.some((item) => typeof item !== "string")) {
  throw new TypeError("expected an array of raw JSON strings on stdin");
}
const outputs = rawInputs.map((raw) => {
  const value = JSON.parse(raw);
  const canonical = canonicalize(value);
  if (typeof canonical !== "string") throw new TypeError("canonicalize returned no string");
  return canonical;
});
process.stdout.write(JSON.stringify(outputs));
