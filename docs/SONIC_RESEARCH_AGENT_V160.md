# SONIC v1.6.0 | Read-only AI Research Agent

## Menggunakan dari iPhone
1. Masuk ke https://sonic-web-staging.up.railway.app/owner melalui Safari dan login sebagai owner.
2. Buka **Chat**. Pilih pill **Research Agent**. Mode Chat biasa tetap tidak berubah.
3. Pilih **Find Targets**, **Data & Figures**, atau **References**.
4. Ketik topik riset pendek (5-300 karakter), contoh: "produsen panel akustik Indonesia 2026", "data tren cafe Jakarta 2026", atau "referensi desain restoran Jepang kontemporer".
5. SONIC menjalankan dua pencarian publik, memfilter hasil tidak relevan, lalu membuka maksimal tiga sumber publik, dan menampilkan hingga lima referensi dengan excerpts.
6. Bila GGUF lokal di TRADEVICEPC RUNNING, SONIC mengirim cuplikan sumber tidak tepercaya ke model lokal untuk ringkasan pendek dengan sumber [1], [2]. Bila tidak RUNNING, SONIC tetap memberikan daftar sumber, dilabeli "Sources only".
7. Setelah selesai, buka Devices > Local AI dan Stop model untuk mengembalikan RAM dan VRAM, kecuali masih dibutuhkan.

## Implementasi
- sonic/research_web.py: web.search via Bing public RSS (https://www.bing.com/search?format=rss&q=...), dan web.open via Jina Reader (https://r.jina.ai/https://...).
- sonic/research_agent.py: owner-only GET /api/agent/capabilities dan CSRF-protected POST /api/agent/research. Plan deterministik dan dibatasi, bukan arbitrary model tool call.
- web/research-agent-v160.js + CSS: switch mode di Chat, link source, metadata, read status, langkah tool. Guest preview tak punya akses.
- .env.example: SONIC_RESEARCH_AGENT_ENABLED=false. Set true hanya pada staging setelah QA lulus.
- Menggunakan existing httpx di requirements.txt; tidak perlu menambah API key untuk basic web search. Jina Search sendiri mengharuskan autentikasi dan **tidak dipakai**. Bing RSS terkadang mengembalikan hasil keliru untuk kata kunci niche; filter relevansi mengembalikan 0 sumber daripada membuat sumber fiktif.
- History chat owner menyimpan query, jawaban model, dan URL referensi publik. Tidak menyimpan halaman mentah penuh atau membuat Memory Vault secara otomatis.
- Tidak ada cron atau monitoring otomatis; tiap riset diawali perintah owner.

## Privasi dan keamanan
- Query dikirim ke Bing Search. URL halaman publik dikirim ke Jina Reader. Provider pihak ketiga tersebut mungkin mencatat query atau URL. Cookie owner, password, API key, koneksi database, data trading dan file pribadi tidak ikut dikirim.
- Request egress dari Railway dibatasi ke origin HTTPS Bing dan Jina. Tidak ada direct fetch ke arbitrary domain hasil pencarian dari Railway.
- URL sumber harus HTTPS dengan hostname publik, bukan literal IP, localhost, domain privat, userinfo atau port tidak standar. Reader mengakses halaman publik, bukan browser yang login.
- Tidak ada remote desktop, shell, market order, close trading, payment, GitHub write, deployment ataupun filesystem action dalam Research Agent. Terpisah dari sistem owner PC command existing.
- Halaman web tidak dipercaya sebagai instruksi tool. Model menerima maksimal 1.090 karakter kutipan sebagai data, tanpa schema/function tools.
- Batas: 2 query variants per request, 5 sumber, 3 halaman dibuka, 2 riset bersamaan, 8 riset per owner session per 10 menit (best effort per worker), browser timeout sekitar 40 detik, tambahan inference lokal jika aktif.
- Date metadata berasal dari RSS; periksa publikasi pada situs asal untuk memastikan informasi paling baru.
- GGUF 9B sekarang menggunakan context 1024 token dan output 256 token. Dokumen sangat panjang atau riset mendalam perlu model/context yang lebih besar.

## Tes dan deployment
- Python: python -m pytest -q tests/test_research_agent_v160.py
- Browser Chromium: python scripts/e2e_research_agent_v160.py (synthetic sources only)
- Tes pencarian nyata dilakukan dari TRADEVICEPC dengan query publik, tanpa data internal dan tanpa token.
- CI uses Ubuntu 24.04 untuk Playwright 1.56.0.
- Rollback: set SONIC_RESEARCH_AGENT_ENABLED=false; jika perlu kembali source staging ke commit SONIC v1.5.3 sebelumnya tanpa mengubah auth dan MT5.
- QA owner dari iPhone fisik tetap gerbang acceptance terpisah dari browser simulasi.