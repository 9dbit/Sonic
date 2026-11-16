# SONIC v1.5.3 | Private Owner Portal for iPhone

## Tujuan
Menjaga public preview tetap berjalan di `/` sambil menyediakan login owner privat melalui `/owner`, tanpa pernah memberi hak PC kepada pengunjung biasa.

## Alur
1. Buka `https://sonic-web-staging.up.railway.app/owner` menggunakan Safari iPhone, Chrome, atau mode PWA.
2. Masukkan **owner access token yang telah dimiliki**, bukan token Companion. Token tidak ditampilkan oleh aplikasi dan tidak disimpan di localStorage; SONIC menyimpan hash server-side.
3. Setelah login berhasil, buka menu **Devices → Local AI Control Center**.
4. Tekan **Refresh** untuk memperoleh status terbaru TRADEVICEPC, CPU/RAM/VRAM, kemudian **Start AI** hanya bila resource cukup. Proses tidak auto-start.
5. Tekan **Use for Chat** setelah status model `running`, lalu **Open Chat** untuk bercakap via model GGUF lokal.
6. Setelah selesai, tekan **Stop AI** agar RAM dan VRAM kembali tersedia bagi MT5.
7. Tambahkan halaman `/owner` ke Home Screen iPhone. Manifest owner punya `start_url: "/owner"`; manifest public tidak berubah.

## Keamanan dan pemisahan
- **Public**: `/` dan `/api/preview/*` tetap guest preview dengan kuota dan tanpa PC tools.
- **Owner**: `/owner` aktif hanya pada nonproduction preview ketika `SONIC_OWNER_ENTRY_ENABLED=true`, terpisah dari default `/api/login` yang tetap ditolak saat preview.
- Login owner khusus: `POST /api/owner/login`, JSON + header `X-Sonic-Owner-Entry: 1` + Origin tepat sama dengan `SONIC_PUBLIC_URL`. Validasi token existing dan rate limiter existing dipakai ulang.
- Setelah autentikasi: cookie `sonic_session` yang ditandatangani dan disimpan secara server-side, HttpOnly, SameSite=Strict, Secure on HTTPS; CSRF diperlukan untuk owner writes.
- `GET /api/session` hanya mengembalikan owner bila ada owner session yang *valid dan belum kedaluwarsa*, bukan sekadar guest cookie atau header owner. Tanpa itu tetap preview.
- Tidak ada endpoint baru yang mengizinkan guest memulai AI, mengakses Memory Vault, membaca file, atau mengendalikan PC. `/owner` bukan rahasia autentikasi; kekuatan akses tetap bergantung pada token/passkey.
- SONIC local AI tetap dibatasi teks tanpa PC tools, melalui signed Companion job, dengan resource guard dan allowlist.
- Passkey / Face ID: alur WebAuthn existing tetap kompatibel jika `SONIC_PASSWORDLESS_LOGIN` diaktifkan dan owner benar-benar mendaftarkan passkey. Jangan aktifkan passkey-only sebelum enrollment.
- PWA owner memakai manifest terpisah, noindex dan no-store. Public manifest tetap memulai `/`.

## Feature flag
- Railway `SONIC` → `staging` → `sonic-web`: `SONIC_OWNER_ENTRY_ENABLED=true`
- Biarkan `SONIC_OPEN_PREVIEW=true`. Jangan mengubah `SONIC_PASSWORDLESS_LOGIN` bila belum punya passkey terdaftar.
- Jangan mengubah `SONIC_OWNER_TOKEN_SHA256` atau `SONIC_DEVICE_TOKEN_SHA256` saat rilis ini.
- Pembatalan fitur: set `SONIC_OWNER_ENTRY_ENABLED=false` dan deploy, sehingga route login owner baru kembali 404. Sebagai langkah tambahan bila perlu mengeluarkan sesi yang sudah login, lakukan revokasi sesi owner melalui mekanisme yang tersedia.

## QA
- Synthetic HTTP tests untuk guest/owner separation, origin/header validation, token auth, CSRF, forged cookies, logout, passwordless compatibility dan production gate.
- Browser desktop/mobile iPhone viewport test harus menegaskan root tetap public dan `/owner` menampilkan login tanpa horizontal overflow.
- Full Python, JavaScript, and GitHub Actions regressions.
- Live Railway `/api/health`, `/api/session`, `/owner`, manifest, dan route kontrol tanpa login.
- IPhone fisik yang belum login tidak dapat diklaim sukses E2E tanpa owner menyelesaikan autentikasi pada perangkatnya.