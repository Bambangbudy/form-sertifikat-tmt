# -*- coding: utf-8 -*-
"""Unggah berkas pendaftar ke Google Drive pemilik lewat jembatan Google Apps Script.

Service account TIDAK bisa dipakai untuk ini: Google menyatakan service account
tidak punya kuota dan tidak boleh memiliki file (upload gagal 403
storageQuotaExceeded). Jadi file dikirim ke web app Apps Script milik pemilik
Drive (apps-script-upload.gs di proyek database-alumni). Script itu berjalan
sebagai akun pemilik dan menyimpan file ke folder Drive-nya, memakai kuota
Drive pemilik. Yang disimpan di Google Sheet hanya link-nya.

Dua pengaturan WAJIB (environment variable, bukan di kode):
    DRIVE_SCRIPT_URL   alamat web app Apps Script (berakhiran /exec)
    DRIVE_RAHASIA      kunci rahasia yang sama dengan Script Properties RAHASIA
"""
import base64
import re
import uuid

import requests

import config
from berkas_umum import MIME, GagalUpload, KonfigurasiBelumLengkap, ekstensi


def _nama_aman(teks):
    bersih = re.sub(r"[^\w .,-]", "", teks, flags=re.UNICODE).strip()
    return bersih[:60] or "peserta"


def siap():
    """True kalau jembatan Drive sudah dikonfigurasi."""
    return bool(config.DRIVE_SCRIPT_URL and config.DRIVE_RAHASIA)


def upload_berkas(file_storage, nama_peserta, label):
    """Kirim satu berkas ke Drive. Return link Drive (str).

    Berkas harus sudah divalidasi (ekstensi, ukuran, isi) oleh pemanggil."""
    if not siap():
        raise KonfigurasiBelumLengkap("DRIVE_SCRIPT_URL / DRIVE_RAHASIA belum diisi.")

    ext = ekstensi(file_storage)
    payload = {
        "rahasia": config.DRIVE_RAHASIA,
        "nama": f"{label} - {_nama_aman(nama_peserta)} - {uuid.uuid4().hex[:8]}.{ext}",
        "mime": MIME[ext],
        "data_base64": base64.b64encode(file_storage.read()).decode("ascii"),
    }
    try:
        resp = requests.post(config.DRIVE_SCRIPT_URL, json=payload, timeout=90)
    except requests.RequestException as e:
        raise GagalUpload(f"Tidak bisa menghubungi Apps Script: {type(e).__name__}")
    try:
        hasil = resp.json()
    except ValueError:
        raise GagalUpload(f"Jawaban Apps Script bukan JSON (HTTP {resp.status_code}): {resp.text[:200]}")
    if resp.status_code >= 300 or not hasil.get("ok") or not hasil.get("url"):
        raise GagalUpload(f"Apps Script menolak upload: {str(hasil.get('error'))[:200]}")
    return hasil["url"]
