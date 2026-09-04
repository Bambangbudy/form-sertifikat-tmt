# -*- coding: utf-8 -*-
"""Baca/tulis data pendaftaran ke Google Sheets (menggantikan excel_io.py
yang berbasis file lokal). Satu baris = satu orang UNTUK SATU skema TMT.

Butuh:
- File kredensial service account (lihat config.GOOGLE_CREDENTIALS_FILE)
- config.GOOGLE_SHEET_ID diisi ID Google Sheet tujuan
- Google Sheet itu sudah di-share (akses Editor) ke email service account
"""
import threading
import time
from datetime import datetime

import gspread
import requests
import google.auth.exceptions
from google.oauth2.service_account import Credentials

import config

_lock = threading.Lock()

# Kesalahan jaringan yang layak dicoba ulang (koneksi ke Google basi/putus
# sesaat - lumrah terjadi di proses server yang hidup lama). google-auth
# membungkus ulang error koneksi yang terjadi saat ambil/refresh token
# jadi TransportError, jadi itu juga perlu ditangkap - bukan cuma
# requests.exceptions langsung.
_ERROR_JARINGAN = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    google.auth.exceptions.TransportError,
)


def _dengan_retry(fn, percobaan=4, jeda=1.5):
    for i in range(percobaan):
        try:
            return fn()
        except _ERROR_JARINGAN:
            if i == percobaan - 1:
                raise
            time.sleep(jeda)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
WORKSHEET_NAME = "Pendaftaran"

KOLOM = [
    "No", "Nama", "NIK", "Tempat Lahir", "Tanggal Lahir", "Pendidikan Terakhir",
    "Jurusan", "Angkatan", "Pekerjaan", "No. HP", "Email",
    "Pelatihan BLK yang Pernah Diikuti", "TMT / Skema yang Diikuti",
    "Waktu Daftar", "Keterangan",
]

_KEY_KE_LABEL = {
    "nama": "Nama", "nik": "NIK", "tempat_lahir": "Tempat Lahir",
    "tanggal_lahir": "Tanggal Lahir", "pendidikan": "Pendidikan Terakhir",
    "jurusan": "Jurusan", "angkatan": "Angkatan", "pekerjaan": "Pekerjaan",
    "no_hp": "No. HP", "email": "Email",
    "pelatihan_blk": "Pelatihan BLK yang Pernah Diikuti",
    "tmt": "TMT / Skema yang Diikuti", "keterangan": "Keterangan",
}


class KonfigurasiBelumLengkap(Exception):
    pass


def _client_gspread():
    # Sengaja TIDAK di-cache/disimpan sebagai variabel global. Server ini
    # jalan lama (proses tunggal, banyak request), dan koneksi HTTP yang
    # disimpan lama-lama bisa basi lalu gagal dengan error
    # "RemoteDisconnected" saat dipakai lagi. Bikin client baru tiap
    # panggilan itu murah (belum ada request jaringan sampai dipakai),
    # jadi lebih aman daripada menghemat sedikit waktu tapi rawan error.
    try:
        creds = Credentials.from_service_account_file(
            config.GOOGLE_CREDENTIALS_FILE, scopes=SCOPES
        )
    except FileNotFoundError:
        raise KonfigurasiBelumLengkap(
            f"File kredensial '{config.GOOGLE_CREDENTIALS_FILE}' belum ada. "
            "Ikuti langkah setup Google Sheets dulu."
        )
    return gspread.authorize(creds)


def _worksheet():
    if not config.GOOGLE_SHEET_ID:
        raise KonfigurasiBelumLengkap("config.GOOGLE_SHEET_ID masih kosong. Isi dulu ID Google Sheet-nya.")
    gc = _client_gspread()
    try:
        sh = gc.open_by_key(config.GOOGLE_SHEET_ID)
    except gspread.exceptions.APIError as e:
        raise KonfigurasiBelumLengkap(
            "Gagal membuka Google Sheet - pastikan sheet-nya sudah di-share "
            f"(akses Editor) ke email service account. Detail: {e}"
        )
    try:
        return sh.worksheet(WORKSHEET_NAME)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=WORKSHEET_NAME, rows=2000, cols=len(KOLOM))
        ws.append_row(KOLOM, value_input_option="RAW")
        return ws


def sheet_url():
    return f"https://docs.google.com/spreadsheets/d/{config.GOOGLE_SHEET_ID}/edit"


def _baca_semua_sekali():
    with _lock:
        ws = _worksheet()
        records = ws.get_all_records()
    return [r for r in records if str(r.get("Nama", "")).strip()]


def baca_semua():
    return _dengan_retry(_baca_semua_sekali)


def _tambah_pendaftar_sekali(data):
    with _lock:
        ws = _worksheet()
        header = ws.row_values(1)
        jumlah_baris_data = len(ws.get_all_values()) - 1

        nilai = {"No": jumlah_baris_data + 1, "Waktu Daftar": datetime.now().strftime("%Y-%m-%d %H:%M")}
        for key, label in _KEY_KE_LABEL.items():
            nilai[label] = data.get(key, "")

        baris = [str(nilai.get(label, "")) for label in header]
        ws.append_row(baris, value_input_option="RAW")


def tambah_pendaftar(data):
    """data: dict dengan key dari _KEY_KE_LABEL (satu nilai 'tmt' per panggilan)."""
    return _dengan_retry(lambda: _tambah_pendaftar_sekali(data))
