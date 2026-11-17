# Build dan validasi

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

**Batas bukti:** unit test memeriksa perilaku kode dan kesalahan yang disimulasikan; startup test memeriksa bahwa aplikasi membuka UI dengan data demo. Keduanya tidak membuktikan bahwa setiap profil Wi-Fi nyata atau kebijakan akun akan memberikan password. Manifest dan laporan startup dari build final menjadi catatan lingkungan yang benar-benar diuji. Versi minimum pada metadata APP bukan jaminan pengujian pada seluruh versi macOS tersebut.
