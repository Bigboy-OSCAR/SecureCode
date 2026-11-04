import * as clineSdk from "@cline/sdk";

console.log("@cline/sdk keys:");
console.log(Object.keys(clineSdk));

const candidates = [
  "ClineCore",
  "create",
  "start",
  "subscribe",
  "abort",
  "stop",
  "dispose",
];

for (const name of candidates) {
  const value = (clineSdk as Record<string, unknown>)[name];
  console.log(name, typeof value);
}
