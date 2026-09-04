# -*- coding: utf-8 -*-
"""
Server web pendaftaran sertifikat / TMT.

Cara jalankan:
    python app.py

Buka http://localhost:5000 di komputer ini, atau dari HP/komputer lain
yang SATU JARINGAN WIFI lewat alamat IP yang dicetak saat server jalan.
ini BUKAN hosting online.

Halaman:
    "/"           -> publik, form pendaftaran (Nominatif Calon Peserta Pelatihan)
    "/login"      -> masuk sebagai admin (password di config.py)
    "/admin"      -> khusus admin, lihat semua data (termasuk NIK & kontak) + link ke Google Sheet

Datanya disimpan di Google Sheets. Setup awal (sekali saja, sudah dilakukan):
service account dibuat di GCP project "berbagidocument", kredensialnya di
service_account.json, sheet ID + path kredensial dikonfigurasi di config.py,
dan sheet-nya sudah di-share (akses Editor) ke email service account itu.
"""
import os
import socket
from functools import wraps

from flask import Flask, request, redirect, url_for, session, render_template

import config
from sheets_io import (
    baca_semua, tambah_pendaftar, sheet_url, KonfigurasiBelumLengkap, KOLOM,
    baca_semua_kepuasan, tambah_kepuasan, KOLOM_KEPUASAN,
)

PERSYARATAN_TMT = {
    "WI Standard 180 JP": "Minimal D3, pengalaman sebagai welder minimal 2 tahun",
    "K3 Umum": "Minimal D3",
    "K3 Listrik": "Minimal S1, pengalaman di bidang kelistrikan minimal 2 tahun",
    "TKBKT": "Minimal SLTA, minimal 1 tahun bekerja di bidang TKBKT",
    "Scaffolder": "Minimal SLTA, minimal 2 tahun di bidang scaffolder",
    "SIO Crane": "Minimal SLTA, minimal 1 tahun di bidang crane",
    "SIO Forklift": "Minimal SLTA, minimal 1 tahun di bidang forklift",
    "Expert": "Minimal S1, pengalaman minimal 5 tahun di bidang terkait",
}
OPSI_TMT = list(PERSYARATAN_TMT.keys())

app = Flask(__name__)
app.secret_key = os.environ.get("TMT_SECRET_KEY", "ganti-kalau-mau-di-hosting-" + os.urandom(8).hex())


def perlu_login(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("admin_ok"):
            return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)
    return wrapper


@app.route("/", methods=["GET", "POST"])
def form():
    pesan = ""
    berhasil = False
    nilai = {}

    if request.method == "POST":
        nilai = {
            "nama": request.form.get("nama", "").strip(),
            "nik": request.form.get("nik", "").strip(),
            "tempat_lahir": request.form.get("tempat_lahir", "").strip(),
            "tanggal_lahir": request.form.get("tanggal_lahir", "").strip(),
            "pendidikan": request.form.get("pendidikan", "").strip(),
            "jurusan": request.form.get("jurusan", "").strip(),
            "angkatan": request.form.get("angkatan", "").strip(),
            "pekerjaan": request.form.get("pekerjaan", "").strip(),
            "no_hp": request.form.get("no_hp", "").strip(),
            "email": request.form.get("email", "").strip(),
            "pelatihan_blk": request.form.get("pelatihan_blk", "").strip(),
        }
        tmt_dipilih = [t for t in request.form.getlist("tmt") if t in OPSI_TMT]
        nilai["tmt"] = tmt_dipilih

        if not nilai["nama"]:
            pesan = "Nama wajib diisi."
        elif not tmt_dipilih:
            pesan = "Pilih minimal satu TMT / skema pelatihan."
        elif nilai["nik"] and (not nilai["nik"].isdigit() or len(nilai["nik"]) != 16):
            pesan = "NIK harus 16 digit angka (atau dikosongkan kalau belum ada)."
        else:
            try:
                for tmt in tmt_dipilih:
                    baris = dict(nilai)
                    baris["tmt"] = tmt
                    tambah_pendaftar(baris)
                pesan = f'Terima kasih, "{nilai["nama"]}" berhasil didaftarkan untuk: {", ".join(tmt_dipilih)}.'
                berhasil = True
                nilai = {}
            except KonfigurasiBelumLengkap as e:
                pesan = f"Belum bisa menyimpan data - setup Google Sheets belum selesai: {e}"
            except Exception:
                app.logger.exception("Gagal menyimpan pendaftaran")
                pesan = "Gagal menyimpan data karena gangguan sementara - silakan coba lagi."

    return render_template("form.html", pesan=pesan, berhasil=berhasil, nilai=nilai,
                           opsi_tmt=OPSI_TMT, syarat_tmt=PERSYARATAN_TMT)


@app.route("/kepuasan", methods=["GET", "POST"])
def kepuasan():
    pesan = ""
    berhasil = False
    nilai = {}

    if request.method == "POST":
        nilai = {
            "nama": request.form.get("nama", "").strip(),
            "no_hp": request.form.get("no_hp", "").strip(),
            "pelatihan": request.form.get("pelatihan", "").strip(),
            "kepuasan_keseluruhan": request.form.get("kepuasan_keseluruhan", "").strip(),
            "kualitas_materi": request.form.get("kualitas_materi", "").strip(),
            "kualitas_instruktur": request.form.get("kualitas_instruktur", "").strip(),
            "fasilitas": request.form.get("fasilitas", "").strip(),
            "rekomendasi": request.form.get("rekomendasi", "").strip(),
            "saran": request.form.get("saran", "").strip(),
        }
        wajib = ["kepuasan_keseluruhan", "kualitas_materi", "kualitas_instruktur", "fasilitas"]
        if any(not nilai[k] for k in wajib):
            pesan = "Semua penilaian (1-5) wajib diisi."
        else:
            try:
                tambah_kepuasan(nilai)
                pesan = "Terima kasih atas penilaian Anda!"
                berhasil = True
                nilai = {}
            except KonfigurasiBelumLengkap as e:
                pesan = f"Belum bisa menyimpan data - setup Google Sheets belum selesai: {e}"
            except Exception:
                app.logger.exception("Gagal menyimpan survey kepuasan")
                pesan = "Gagal menyimpan data karena gangguan sementara - silakan coba lagi."

    return render_template("kepuasan.html", pesan=pesan, berhasil=berhasil, nilai=nilai,
                           opsi_pelatihan=OPSI_TMT)


@app.route("/admin/kepuasan")
@perlu_login
def admin_kepuasan():
    try:
        rows = baca_semua_kepuasan()
    except KonfigurasiBelumLengkap as e:
        return f"Setup Google Sheets belum selesai: {e}", 500
    return render_template("admin.html", rows=rows, kolom=KOLOM_KEPUASAN, sheet_url=sheet_url())


@app.route("/login", methods=["GET", "POST"])
def login():
    pesan = ""
    if request.method == "POST":
        if request.form.get("password", "") == config.ADMIN_PASSWORD:
            session["admin_ok"] = True
            return redirect(request.args.get("next") or url_for("admin"))
        pesan = "Password salah."
    return render_template("login.html", pesan=pesan)


@app.route("/logout")
def logout():
    session.pop("admin_ok", None)
    return redirect(url_for("form"))


@app.route("/admin")
@perlu_login
def admin():
    try:
        rows = baca_semua()
    except KonfigurasiBelumLengkap as e:
        return f"Setup Google Sheets belum selesai: {e}", 500
    return render_template("admin.html", rows=rows, kolom=KOLOM, sheet_url=sheet_url())


def _ip_lokal():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


if __name__ == "__main__":
    ip = _ip_lokal()
    print("=" * 60)
    print("Pendaftaran Sertifikat / TMT - server berjalan")
    print(f"  Di komputer ini   : http://localhost:5000")
    print(f"  Dari HP/komputer lain (satu wifi): http://{ip}:5000")
    print("  Tekan CTRL+C untuk berhenti.")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5000, debug=False)
