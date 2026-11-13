# SONIC branding assets v1.4.5

## Source
The existing animated web/sonic-mark.svg remains the master. All static assets
are exported from its unanimated face using scripts/generate_brand_assets.py.
No independently reinterpreted brand mark is introduced.

## Deliverables
- /assets/sonic-mark.svg: animated SVG favicon.
- /assets/favicon-16.png and /assets/favicon-32.png: PNG browser icons.
- /favicon.ico: ICO fallback with embedded 16 and 32 PNG images.
- /apple-touch-icon.png: 180x180 opaque Apple Touch Icon.
- /assets/sonic-app-192.png and sonic-app-512.png: web manifest launcher.
- /assets/sonic-og-1200x630.png: Open Graph and Twitter share image.
- /site.webmanifest: minimal launcher metadata (no offline service worker).

## HTML
The home route renders absolute og:url and og:image as well as the canonical
URL from SONIC_PUBLIC_URL, with attribute escaping. No domain is hardcoded.
The main page exposes favicon links, apple-touch-icon, the web manifest,
Open Graph (title, description, type, image dimensions, alt) and Twitter
summary_large_image. Root routes also serve favicon.ico and Apple Touch Icon.
