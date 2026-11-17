# Build dan validasi

## Hasil rilis 1.0.0

[CI final](https://github.com/9dbit/Sonic/actions/runs/44175832044) berhasil untuk Windows x64, Mac Apple Silicon, dan Mac Intel. Paket dibuat dari [commit `e397b79`](https://github.com/9dbit/Sonic/commit/e397b79f5e830ec8ae47f79f996a9230ebea1189). Pada setiap platform, 40 tes backend/UI serta startup executable hasil bundling lulus.

Lingkungan build yang tercatat pada manifest:

| Platform | Sistem build | Python |
| --- | --- | --- |
| Windows x64 | Windows Server 2025, build 26100 | 3.12.10 |
| Mac Apple Silicon | macOS 15.8.2, arm64 | 3.12.10 |
| Mac Intel | macOS 15.7.9, x86_64 | 3.12.10 |

Manifest masing-masing paket menjadi acuan ukuran dan SHA-256. Build Windows belum memiliki sertifikat penerbit; aplikasi Mac bertanda tangan ad-hoc dan belum dinotarisasi Apple.

## Paket native

Source memakai Python, PySide6 Essentials 6.8.3, dan PyInstaller 6.22.3. PyInstaller harus dijalankan pada sistem target: Windows untuk EXE dan macOS untuk APP/DMG. Lihat [dokumentasi resmi PyInstaller](https://pyinstaller.org/en/stable/).

```bash
python -m pip install -r requirements-build.txt
python scripts/build_native.py
```

Skrip menyalin lisensi runtime, memanggil spesifikasi PyInstaller, dan menulis manifest berisi ukuran, SHA-256, arsitektur, versi Python/dependensi, serta status penandatanganan. Pada Mac, skrip memeriksa tanda tangan APP dan struktur DMG memakai fasilitas sistem. Pemeriksaan ini tidak sama dengan notarization Apple; lihat [catatan penandatanganan PyInstaller](https://pyinstaller.org/en/stable/feature-notes.html#macos-binary-code-signing).

## Pengujian

Pengujian otomatis memakai profil sintetis dan stub OS. Tidak perlu membuka password Wi-Fi pribadi untuk menjalankan pengujian.

```bash
python -m unittest discover -s tests -v
python wifi_finder.py --smoke-test --smoke-report smoke.json
python wifi_finder.py --screenshot preview.png
```

Untuk pengujian UI tanpa layar pada Linux, tambahkan `QT_QPA_PLATFORM=offscreen` di depan perintah. Pemulihan profil asli tetap khusus Windows/macOS. Opsi `--screenshot` selalu memakai data demo.

Untuk menguji hasil paket, ganti `python wifi_finder.py` dengan path EXE Windows atau executable dalam `SONIC WiFi Finder.app/Contents/MacOS/SONIC WiFi Finder`. Gunakan tanda kutip jika path mengandung spasi.

Laporan startup memuat `demo_only`, `startup_ok`, `profile_count`, `password_initially_hidden`, `font_ready`, dan `qt_platform`. Pemeriksaan `font_ready` menguji ketersediaan huruf Latin dan angka melalui metrik font Qt. Pada Windows, tes paket menghapus pengaturan `QT_QPA_PLATFORM=offscreen`, kemudian mewajibkan `qt_platform=windows` agar tampilan menggunakan backend Windows normal. Pada Mac, tes tanpa layar juga memeriksa kesiapan font. Preview setiap paket tersedia dalam artefak CI untuk pemeriksaan visual.

**Batas bukti:** unit test memeriksa perilaku kode dan kesalahan yang disimulasikan; startup test memeriksa bahwa executable membuka UI dengan data demo. Tidak ada password pribadi yang diakses. Pengujian ini tidak membuktikan bahwa setiap profil Wi-Fi nyata atau kebijakan akun akan memberikan password. Manifest dan laporan startup menjadi catatan lingkungan yang benar-benar diuji. Versi minimum pada metadata APP bukan jaminan pengujian pada seluruh versi macOS tersebut.

Keberhasilan CI tidak menyelesaikan kondisi perangkat pengguna: ruang disk TRADEVICEPC sebelumnya habis dan koneksi TRADEVICEPC/SPARK belum dikonfirmasi pulih. Aplikasi belum dikonfirmasi berjalan atau terpasang pada perangkat tersebut.
