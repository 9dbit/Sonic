# Hasil pengujian lokal

Tanggal: 18 November 2026 (WIB)

Perintah:

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -q
```

Hasil aktual:

```text
Ran 40 tests in 1.041s
OK
```

Pengujian terdiri dari 22 pemeriksaan backend dan 18 pemeriksaan UI. Fokusnya: parsing profil Windows, proteksi kunci terenkripsi, jaringan perusahaan/terbuka, pemanggilan Keychain tanpa shell, pemeliharaan spasi SSID/password, timeout/cancel, startup tanpa pembacaan password, pilihan jaringan, filter, reveal/hide, copy, timer, clipboard milik aplikasi, serta penolakan hasil lama setelah pembatalan atau perubahan pilihan.

Startup UI dalam mode demo juga berhasil. Hasil terstruktur tersedia di `smoke-local.json`. Preview yang disertakan menggunakan data demo; bukan daftar jaringan pengguna.

Hasil ini belum mencakup pengujian executable native atau pemulihan password jaringan pribadi secara langsung.
