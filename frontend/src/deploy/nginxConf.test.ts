import conf from "../../nginx.conf?raw";

/** Strukturalna kontrola nginx.conf (nginx -t nie jest dostępny w środowisku deweloperskim). */
function block(selector: string): string {
  const start = conf.indexOf(`location ${selector} {`);
  expect(start, `brak bloku location ${selector}`).toBeGreaterThanOrEqual(0);
  return conf.slice(start, conf.indexOf("}", start) + 1);
}

describe("nginx.conf", () => {
  it("index.html is never cached long (no-cache, exact location)", () => {
    const b = block("= /index.html");
    expect(b).toMatch(/add_header\s+Cache-Control\s+"no-cache";/);
    expect(b).not.toMatch(/expires|immutable/);
  });

  it("keeps the SPA fallback to /index.html and long-lived hashed assets", () => {
    expect(block("/")).toMatch(/try_files \$uri \$uri\/ \/index\.html;/);
    expect(block("/assets/")).toMatch(/immutable/);
  });

  it("has balanced braces", () => {
    expect((conf.match(/\{/g) ?? []).length).toBe((conf.match(/\}/g) ?? []).length);
  });
});
