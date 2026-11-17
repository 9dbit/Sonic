# Status rilis SONIC WiFi Finder 1.0.0

Tanggal: 18 November 2026 (WIB)

**Ketiga paket native berhasil dibangun dan lulus tes startup di CI.** Source, aset, dan workflow sudah dipublikasikan ke repository SONIC setelah persetujuan pengguna.

- [Hasil CI final](https://github.com/9dbit/Sonic/actions/runs/44175832044)
- [Commit source rilis `e397b79`](https://github.com/9dbit/Sonic/commit/e397b79f5e830ec8ae47f79f996a9230ebea1189)
- Branch: `build/wifi-finder-20261118`

## Paket hasil build

| Platform | File | Hasil |
| --- | --- | --- |
| Windows x64 | `SONIC-WiFi-Finder-1.0.0-Windows-x64.exe` | Build dan startup lulus |
| Mac Apple Silicon | `SONIC-WiFi-Finder-1.0.0-macOS-AppleSilicon.dmg` | Build dan startup lulus |
| Mac Intel | `SONIC-WiFi-Finder-1.0.0-macOS-Intel.dmg` | Build dan startup lulus |

Setiap paket disertai manifest ukuran, SHA-256, arsitektur, versi runtime, dan status penandatanganan. Artefak CI juga menyediakan laporan startup dan preview UI memakai data demo.

## Verifikasi yang selesai

- Pada **masing-masing platform**, 40 tes lulus: 22 backend dan 18 UI. Semua memakai profil sintetis atau stub OS.
- Executable hasil bundling membuka UI, memuat tiga jaringan demo, dan menampilkan password dalam keadaan tersembunyi pada awal startup.
- Pemeriksaan `font_ready` memastikan huruf Latin dan angka yang diuji tersedia. Tes paket Windows memakai backend tampilan normal dengan `qt_platform=windows`.
- Skrip build Mac memeriksa tanda tangan aplikasi dan integritas DMG menggunakan fasilitas macOS.
- Tidak ada password Wi-Fi pribadi yang dibaca selama pengembangan atau pengujian.

Pemeriksaan font ditambahkan setelah screenshot dari mode uji tanpa layar di Windows menunjukkan karakter kotak. Jalur uji Windows telah diperbaiki dan build verifikasi ulang berhasil.

## Batas verifikasi dan penandatanganan

Paket Windows belum memakai sertifikat penerbit. Paket Mac memakai tanda tangan ad-hoc dan belum dinotarisasi Apple. Izin pembukaan aplikasi serta akses profil/Keychain tetap mengikuti sistem operasi.

Pengujian CI tidak membuktikan bahwa semua profil Wi-Fi nyata, versi OS, atau kebijakan akun memberi izin yang sama. Pemulihan password pada akun pengguna belum diuji langsung. Versi sistem yang benar-benar digunakan tercatat di manifest setiap paket; metadata versi minimum aplikasi bukan jaminan pengujian seluruh versi macOS.

## Kondisi perangkat pengguna

Build melalui CI menyelesaikan pembuatan paket. Kondisi ruang disk dan koneksi perangkat pengguna belum dinyatakan selesai:

- Installer dependensi di TRADEVICEPC sebelumnya melaporkan `No space left on device`; pemeriksaan ruang bebas berikutnya timeout. EXE satu file memerlukan ruang sementara saat dijalankan.
- Setup dan pembacaan log pada SPARK sebelumnya timeout; keberhasilan setup lokal belum dikonfirmasi.

Aplikasi belum dikonfirmasi berjalan atau terpasang pada kedua perangkat tersebut. Panduan penggunaan tersedia pada [README.md](README.md), dan proses build dijelaskan pada [BUILD-AND-VALIDATION.md](docs/BUILD-AND-VALIDATION.md).
