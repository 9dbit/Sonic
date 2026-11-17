# SONIC WiFi Finder 1.0.0

**Status paket ini — 18 November 2026:** source dan UI sudah dibuat, 40 pengujian otomatis lulus, dan startup UI dengan data demo berhasil. File `.exe` dan `.dmg` belum dihasilkan. Lihat [STATUS-BUILD.md](STATUS-BUILD.md) untuk hambatan build dan langkah yang sudah disiapkan. Nama paket pada tabel di bawah adalah target hasil build.

Aplikasi desktop untuk melihat kembali password Wi-Fi yang sudah tersimpan pada perangkat Anda. Pilih satu jaringan, tampilkan password melalui izin sistem, lalu salin bila diperlukan.

Antarmuka berbahasa Indonesia menggunakan tema hitam–abu dan aksen biru. Tidak perlu memasang Python untuk menjalankan paket aplikasi hasil build.

## Jalankan aplikasi

| Perangkat | Paket | Cara membuka |
| --- | --- | --- |
| Windows x64 | `SONIC-WiFi-Finder-1.0.0-Windows-x64.exe` | Klik dua kali file. Aplikasi bersifat portable. |
| Mac dengan Apple Silicon | `SONIC-WiFi-Finder-1.0.0-macOS-AppleSilicon.dmg` | Buka DMG, seret **SONIC WiFi Finder.app** ke **Applications**, lalu buka aplikasinya. |

Paket Apple Silicon ditujukan untuk Mac seri M, bukan Mac Intel. Lihat catatan build untuk lingkungan yang benar-benar diuji.

Build Windows belum memakai sertifikat penerbit. Build macOS memakai tanda tangan ad-hoc dan belum dinotarisasi Apple. Sistem mungkin meminta tinjauan saat pertama dibuka. Periksa nama file dan asal unduhan; jika macOS memblokir aplikasi, tinjau izin aplikasi tersebut melalui **System Settings → Privacy & Security**. Tidak perlu menonaktifkan perlindungan sistem secara global.

## Cara menggunakan

1. **Pilih jaringan.** Daftar dibaca dari profil yang tersimpan di perangkat. Cari berdasarkan nama atau klik ikon muat ulang. Daftar ini tidak menunjukkan semua jaringan di sekitar Anda.
2. **Klik Tampilkan password.** Jika sistem meminta autentikasi, selesaikan langsung pada dialog Windows atau Keychain macOS. Password dibaca hanya untuk jaringan yang dipilih.
3. **Salin jika diperlukan.** Klik ikon salin di sebelah password. Tempelkan dalam 30 detik. Klik **Sembunyikan password** atau tekan **Esc** setelah selesai.

Password pada layar disembunyikan otomatis setelah 30 detik atau saat berpindah aplikasi. Clipboard yang dibuat melalui aplikasi dibersihkan setelah 30 detik selama aplikasi tetap berjalan; isi clipboard baru dari aplikasi lain tidak dihapus. Riwayat clipboard pihak lain dan salinan yang sudah ditempel tidak dapat ditarik kembali oleh SONIC.

### Jika jaringan atau password belum muncul

| Kondisi | Langkah berikutnya |
| --- | --- |
| Daftar kosong | Muat ulang dan periksa apakah perangkat pernah menyimpan jaringan tersebut. Buka pengaturan Wi-Fi untuk memeriksa adaptor dan profil. |
| Windows menolak akses | Gunakan tampilan password di pengaturan Windows. Jika akun Anda berhak, Anda juga dapat membuka aplikasi dengan **Run as administrator**. Aplikasi tidak menaikkan hak akses secara otomatis. |
| Mac membatasi daftar jaringan | Klik **Masukkan nama Wi-Fi**. Masukkan nama persis, termasuk huruf besar dan spasi. Penambahan nama belum membuktikan bahwa password tersedia. |
| Password tidak ditemukan di Keychain | Klik **Buka app Passwords** dan periksa bagian **Wi-Fi**. Pada sistem yang tidak menyediakan Passwords, aplikasi mencoba membuka Keychain Access. |
| Jaringan terbuka atau kantor | Jaringan terbuka tidak memiliki password bersama. Jaringan dengan autentikasi akun individual/802.1X mungkin tidak menyediakan satu password Wi-Fi yang dapat dipulihkan. |

## Pemrosesan data

Pembacaan profil dan password berjalan lokal melalui fasilitas Windows atau macOS. Aplikasi tidak mengirim password ke server, tidak menyimpan riwayat password ke file, dan tidak memiliki telemetry. Password tersedia sementara dalam memori saat ditampilkan. Hak akses sistem tetap berlaku.

Mode demo menggunakan jaringan dan password buatan. Jalankan `python wifi_finder.py --demo` untuk mencoba antarmuka tanpa membaca profil perangkat.

## Menjalankan dari source

Gunakan Python 3.9 atau lebih baru pada Windows/macOS, lalu jalankan dari folder proyek:

```bash
python -m pip install -r requirements.txt
python wifi_finder.py
```

Di Mac, gunakan `python3` bila perintah `python` tidak tersedia. Dependensi UI dipatok ke PySide6 Essentials 6.8.3. Python diperlukan hanya untuk source dan proses build.

Untuk membuat paket Windows, jalankan `scripts/build_windows.ps1` melalui PowerShell. Untuk macOS, jalankan `sh scripts/build_macos.sh` melalui Terminal. Masing-masing membuat lingkungan build terpisah dan menghasilkan paket di folder `dist`. Proses build memerlukan internet untuk mengunduh dependensi. Detail pengujian tersedia pada [BUILD-AND-VALIDATION.md](docs/BUILD-AND-VALIDATION.md).

Workflow alternatif `ci/sonic-wifi-desktop.yml` disiapkan untuk repository SONIC dengan source aplikasi di `tools/wifi-finder/` dan workflow di `.github/workflows/sonic-wifi-desktop.yml`. Matrix build menargetkan Windows x64, Mac Apple Silicon, dan Mac Intel. Workflow belum dijalankan.

## Referensi resmi

- [Microsoft: melihat password Wi-Fi melalui pengaturan Windows](https://support.microsoft.com/en-us/windows/experience/connectivity-networking/connect-to-a-wi-fi-network-in-windows)
- [Microsoft: izin pembacaan profil WLAN](https://learn.microsoft.com/en-us/windows/win32/api/wlanapi/nf-wlanapi-wlangetprofile)
- [Apple: menemukan password Wi-Fi melalui app Passwords](https://support.apple.com/en-gb/guide/passwords/mchl9f8f63cd/mac)
- [Komponen dan lisensi pihak ketiga](THIRD_PARTY_NOTICES.md)
