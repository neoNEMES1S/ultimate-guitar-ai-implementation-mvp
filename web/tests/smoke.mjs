const webUrl = process.env.DEMO_WEB_URL ?? "http://localhost:3000";
const apiUrl = process.env.DEMO_API_URL ?? "http://localhost:8000";

const [webResponse, healthResponse] = await Promise.all([
  fetch(webUrl),
  fetch(`${apiUrl}/health`),
]);

if (!webResponse.ok) throw new Error(`Web health check failed: ${webResponse.status}`);
if (!healthResponse.ok) throw new Error(`API health check failed: ${healthResponse.status}`);
const html = await webResponse.text();
if (!html.includes("Verify and repair a chord sheet or tab")) {
  throw new Error("The review page did not render its primary heading");
}
const health = await healthResponse.json();
if (health.ok !== true) throw new Error("API health payload was not ok");

// Exercise the multipart image route without needing a fixture file. A tiny
// PNG is expected to be rejected for being too small, proving the route is
// mounted and applying its input guard.
const tinyPng = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
  "base64",
);
const imageForm = new FormData();
imageForm.append("image", new Blob([tinyPng], { type: "image/png" }), "smoke.png");
const imageResponse = await fetch(`${apiUrl}/api/sources/image`, { method: "POST", body: imageForm });
if (imageResponse.status !== 400) throw new Error(`OCR input guard returned ${imageResponse.status}, expected 400`);

console.log(`Smoke checks passed: ${webUrl}, ${apiUrl}`);
