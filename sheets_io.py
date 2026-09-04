# -*- coding: utf-8 -*-
"""Baca/tulis ke Google Sheets. Satu spreadsheet (config.GOOGLE_SHEET_ID),
beberapa tab/worksheet di dalamnya - satu tab per "jenis form" (Pendaftaran
TMT, Kepuasan Pelanggan, dst). Semua form berbagi service account & sheet
yang sama, tidak perlu setup/share ulang tiap tambah form baru.

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

# --- Tab "Pendaftaran" (form sertifikat/TMT) ---
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

# --- Tab "Kepuasan Pelanggan" (survey CSAT) ---
WORKSHEET_KEPUASAN = "Kepuasan Pelanggan"
KOLOM_KEPUASAN = [
    "No", "Nama", "No. HP", "Pelatihan yang Diikuti",
    "Kepuasan Keseluruhan", "Kualitas Materi", "Kualitas Instruktur", "Fasilitas",
    "Akan Merekomendasikan", "Saran & Masukan", "Waktu Submit",
]
_KEY_KE_LABEL_KEPUASAN = {
    "nama": "Nama", "no_hp": "No. HP", "pelatihan": "Pelatihan yang Diikuti",
    "kepuasan_keseluruhan": "Kepuasan Keseluruhan", "kualitas_materi": "Kualitas Materi",
    "kualitas_instruktur": "Kualitas Instruktur", "fasilitas": "Fasilitas",
    "rekomendasi": "Akan Merekomendasikan", "saran": "Saran & Masukan",
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


def _worksheet(nama_tab, kolom):
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
        return sh.worksheet(nama_tab)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=nama_tab, rows=2000, cols=len(kolom))
        ws.append_row(kolom, value_input_option="RAW")
        return ws


def sheet_url():
    return f"https://docs.google.com/spreadsheets/d/{config.GOOGLE_SHEET_ID}/edit"


def _baca_semua_generik(nama_tab, kolom):
    with _lock:
        ws = _worksheet(nama_tab, kolom)
        records = ws.get_all_records()
    return [r for r in records if str(r.get("Nama", "")).strip()]


def _tambah_baris_generik(nama_tab, kolom, key_ke_label, data, kolom_waktu):
    with _lock:
        ws = _worksheet(nama_tab, kolom)
        header = ws.row_values(1)
        jumlah_baris_data = len(ws.get_all_values()) - 1

        nilai = {"No": jumlah_baris_data + 1}
        if kolom_waktu:
            nilai[kolom_waktu] = datetime.now().strftime("%Y-%m-%d %H:%M")
        for key, label in key_ke_label.items():
            nilai[label] = data.get(key, "")

        baris = [str(nilai.get(label, "")) for label in header]
        ws.append_row(baris, value_input_option="RAW")


# --- API publik: Pendaftaran TMT (tidak berubah, dipakai app.py yang sudah ada) ---

def baca_semua():
    return _dengan_retry(lambda: _baca_semua_generik(WORKSHEET_NAME, KOLOM))


def tambah_pendaftar(data):
    """data: dict dengan key dari _KEY_KE_LABEL (satu nilai 'tmt' per panggilan)."""
    return _dengan_retry(lambda: _tambah_baris_generik(
        WORKSHEET_NAME, KOLOM, _KEY_KE_LABEL, data, "Waktu Daftar"))


# --- API publik: Kepuasan Pelanggan ---

def baca_semua_kepuasan():
    return _dengan_retry(lambda: _baca_semua_generik(WORKSHEET_KEPUASAN, KOLOM_KEPUASAN))


def tambah_kepuasan(data):
    """data: dict dengan key dari _KEY_KE_LABEL_KEPUASAN."""
    return _dengan_retry(lambda: _tambah_baris_generik(
        WORKSHEET_KEPUASAN, KOLOM_KEPUASAN, _KEY_KE_LABEL_KEPUASAN, data, "Waktu Submit"))
