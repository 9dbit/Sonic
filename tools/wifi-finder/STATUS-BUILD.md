# Status SONIC WiFi Finder

Tanggal: 18 November 2026 (WIB)

## Sudah selesai

- Aplikasi Python/PySide6 dengan UI bahasa Indonesia dan tema SONIC hitam–abu–biru.
- Backend Windows Native WLAN dan macOS Keychain untuk satu jaringan tersimpan yang dipilih pengguna.
- Pencarian jaringan, tampilkan/sembunyikan, salin, timer 30 detik, petunjuk izin OS, dan input SSID manual untuk Mac.
- 40 pengujian otomatis lulus: 22 backend dan 18 UI. Semua memakai data sintetis atau stub OS.
- Startup UI berhasil di lingkungan Linux untuk verifikasi antarmuka; 3 jaringan demo dimuat dan password awalnya tersembunyi.
- Pemeriksaan visual pada ukuran 1040 × 740 dan 880 × 650.
- Skrip native PyInstaller, spesifikasi aplikasi, ikon PNG/ICO/ICNS, lisensi, panduan, serta workflow CI alternatif.

## Belum selesai

- Belum ada executable Windows `.exe` atau disk image macOS `.dmg` yang berhasil dibuat.
- Belum ada startup test pada executable Windows atau aplikasi macOS hasil bundling.
- Tidak ada password Wi-Fi pribadi yang dibaca selama pengembangan/pengujian.
- Kompatibilitas pemulihan pada profil Wi-Fi nyata dan kebijakan akun tertentu belum diuji langsung.

## Hambatan yang diamati

1. Instalasi dependensi untuk build Windows pada TRADEVICEPC gagal dengan `OSError: [Errno 28] No space left on device`. Jumlah ruang bebas per drive belum dapat diverifikasi karena pemeriksaan berikutnya timeout.
2. Panggilan build dan pembacaan log ke Mac SPARK tidak mendapat respons hingga timeout; eksekusi setup Mac belum terkonfirmasi. Sambungan kedua perangkat kemudian tidak merespons stabil.
3. Branch `build/wifi-finder-20261118` sudah dibuat pada `9dbit/Sonic`, menunjuk commit awal `89ba913ef2a4282d10ae7c54cb3170019d383bd8`. Belum ada source/aset aplikasi ini yang dipublikasikan.
4. Peninjauan persetujuan otomatis menolak unggah aset pertama ke repository publik tersebut karena belum ada izin eksplisit untuk publikasi paket lokal. Tidak ada percobaan lanjutan untuk melewati penolakan.

## Paket konkret yang siap dibangun

Workflow CI yang disertakan menempatkan aplikasi pada `tools/wifi-finder/` dan menjalankan:

1. Instalasi dependensi yang dipatok versinya.
2. Pengujian backend dan UI memakai data sintetis.
3. Build native pada Windows x64, macOS Apple Silicon, dan macOS Intel.
4. Startup test executable hasil build menggunakan mode demo.
5. Penyediaan paket, manifest SHA-256, laporan startup, dan preview UI.

Publikasi source, ikon, dokumentasi, lisensi, tes, dan workflow ke repository publik SONIC memerlukan persetujuan pengguna untuk menyelesaikan jalur CI. Alternatifnya, build dapat dilanjutkan pada perangkat native setelah sambungan dan ruang disk tersedia.

Paket Windows direncanakan tanpa sertifikat penerbit; paket Mac memakai tanda tangan ad-hoc dan belum dinotarisasi Apple. Semua pemeriksaan izin OS tetap berlaku.
