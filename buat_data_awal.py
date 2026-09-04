# -*- coding: utf-8 -*-
"""Isi data awal (nama-nama dari proposal) ke Google Sheets. Aman dijalankan
berkali-kali? TIDAK - ini akan menambah baris baru setiap kali dijalankan,
jadi hanya jalankan SEKALI saat sheet masih kosong.
"""
import sys

from sheets_io import tambah_pendaftar, KonfigurasiBelumLengkap

# (nama, tmt/skema) - hasil transkripsi dari proposal training yang dikirim.
DATA_AWAL = [
    ("Indra Pramuwibowo", "WI Standard 180 JP"),
    ("Dede Rahmat", "WI Standard 180 JP"),
    ("Althaf", "K3 Umum"),
    ("M Sya'ban Halim", "K3 Umum"),
    ("Eka Habibullah", "K3 Listrik"),
    ("Ricky Lesmana", "K3 Listrik"),
    ("Rafif Ardi Fauzan", "K3 Listrik"),
]

try:
    for nama, tmt in DATA_AWAL:
        tambah_pendaftar({
            "nama": nama,
            "tmt": tmt,
            "keterangan": "Data awal dari proposal - lengkapi data lainnya.",
        })
        print("Ditambahkan:", nama, "-", tmt)
except KonfigurasiBelumLengkap as e:
    sys.exit(f"Setup Google Sheets belum selesai: {e}")

print(f"Selesai, {len(DATA_AWAL)} baris data awal berhasil ditambahkan ke Google Sheets.")
