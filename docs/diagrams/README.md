# Diagrams

`diagrams.html` is the source for the README diagrams. Each one is a page view:

```text
diagrams.html?d=system|pipeline|valuation&theme=dark|light
```

To re-render, open each view in Chrome and screenshot the `#canvas` element at 1.5× device scale. Any Playwright
script works, for example:

```js
await page.goto(`file://${path}/diagrams.html?d=system&theme=dark`);
await page.waitForSelector("body[data-ready]");
await page.locator("#canvas").screenshot({ path: "system-dark.png" });
```

Colours follow `frontend/DESIGN.md`. Backgrounds match GitHub's light and dark themes, and the README picks the variant
with `<picture>` and `prefers-color-scheme`.
