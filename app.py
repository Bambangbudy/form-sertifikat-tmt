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

import berkas_umum
import config
import drive_io
from sheets_io import (
    baca_semua, tambah_pendaftar, sheet_url, KonfigurasiBelumLengkap, KOLOM,
    baca_semua_kepuasan, tambah_kepuasan, KOLOM_KEPUASAN,
    baca_semua_wi_basic, tambah_wi_basic, KOLOM_WI_BASIC,
    baca_semua_anggota, tambah_anggota, KOLOM_ANGGOTA,
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

# Isi SYARAT_WI_BASIC (teks) kalau persyaratan WI Basic sudah ada;
# kosong = kotak persyaratan tidak ditampilkan di form /wi-basic.
SYARAT_WI_BASIC = ""
# (nama field, label di form & di nama file, ekstensi yang diizinkan) - semuanya wajib.
BERKAS_FORM = [
    ("ijazah", "Ijazah Terakhir", {"pdf", "jpg", "jpeg", "png"}),
    ("cv", "CV", {"pdf"}),
    ("sertifikat_blki", "Sertifikat BLKI", {"pdf", "jpg", "jpeg", "png"}),
    ("ktp", "KTP", {"pdf", "jpg", "jpeg", "png"}),
    ("pas_foto", "Pas Foto", {"jpg", "jpeg", "png"}),
]
FIELD_TEKS_BERKAS = ("nama", "nik", "tempat_lahir", "tanggal_lahir", "pendidikan", "jurusan",
                     "angkatan", "pekerjaan", "no_hp", "email", "pelatihan_blk")

# Form data diri + lampiran dokumen. Satu entri per form; form baru = tambah entri di sini,
# tab Google Sheet-nya di sheets_io.py, dan satu rute di bawah.
FORM_BERKAS = {
    "wi_basic": {
        "judul_halaman": "Pendaftaran TMT WI Basic",
        "judul_kartu": "Nominatif Calon Peserta Pelatihan - TMT WI Basic",
        "pengantar": "Isi data diri dan lampirkan dokumen yang diminta. Semua lampiran wajib.",
        "tombol": "Kirim Pendaftaran",
        "awalan_berkas": "WI Basic",
        "pesan_sukses": 'Terima kasih, "{nama}" berhasil didaftarkan untuk TMT WI Basic. Berkas Anda sudah kami terima.',
        "syarat": SYARAT_WI_BASIC,
        "angkatan_wajib": False,
        "simpan": tambah_wi_basic,
    },
    "anggota": {
        "judul_halaman": "Data Anggota",
        "judul_kartu": "Pendataan Anggota",
        "pengantar": "Isi data diri dan lampirkan dokumen yang diminta. Nama dan angkatan wajib diisi, semua lampiran wajib.",
        "tombol": "Kirim Data Anggota",
        "awalan_berkas": "Anggota",
        "pesan_sukses": 'Terima kasih, "{nama}" sudah tercatat sebagai anggota. Berkas Anda sudah kami terima.',
        "syarat": "",
        "angkatan_wajib": True,
        "simpan": tambah_anggota,
    },
}

app = Flask(__name__)
app.secret_key = os.environ.get("TMT_SECRET_KEY", "ganti-kalau-mau-di-hosting-" + os.urandom(8).hex())
app.config["MAX_CONTENT_LENGTH"] = 18 * 1024 * 1024  # total satu permintaan, termasuk 5 berkas @ maks 3 MB


@app.errorhandler(413)
def terlalu_besar(_e):
    return ("Ukuran total berkas terlalu besar (maksimal 18 MB per pendaftaran). "
            "Kecilkan berkasnya lalu kirim ulang."), 413


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


def _validasi_berkas(file_storage, label, diizinkan):
    """Return pesan error (str) atau None kalau berkas valid."""
    if not file_storage or not file_storage.filename:
        return f"{label} wajib dilampirkan."
    if berkas_umum.ekstensi(file_storage) not in diizinkan:
        return f"{label} harus berformat {', '.join(sorted(diizinkan)).upper()}."
    file_storage.seek(0, os.SEEK_END)
    ukuran = file_storage.tell()
    file_storage.seek(0)
    if ukuran == 0:
        return f"{label} kosong."
    if ukuran > config.MAX_UPLOAD_SIZE:
        return f"{label} maksimal {config.MAX_UPLOAD_SIZE // (1024 * 1024)} MB."
    return berkas_umum.periksa_isi(file_storage, label)


def _form_berkas(kunci):
    """Logika bersama form data diri + 5 lampiran (lihat FORM_BERKAS)."""
    k = FORM_BERKAS[kunci]
    pesan = ""
    berhasil = False
    nilai = {}

    if request.method == "POST":
        nilai = {f: request.form.get(f, "").strip() for f in FIELD_TEKS_BERKAS}

        if not nilai["nama"]:
            pesan = "Nama wajib diisi."
        elif k["angkatan_wajib"] and not nilai["angkatan"]:
            pesan = "Angkatan wajib diisi."
        elif nilai["nik"] and (not nilai["nik"].isdigit() or len(nilai["nik"]) != 16):
            pesan = "NIK harus 16 digit angka (atau dikosongkan kalau belum ada)."
        elif not drive_io.siap():
            app.logger.error("DRIVE_SCRIPT_URL / DRIVE_RAHASIA belum diisi - upload berkas form %s ditolak", kunci)
            pesan = "Penyimpanan berkas belum aktif. Silakan hubungi pengelola."
        else:
            masalah = [m for m in (
                _validasi_berkas(request.files.get(f), label, ok) for f, label, ok in BERKAS_FORM
            ) if m]
            if masalah:
                pesan = " ".join(masalah) + " (Pilih ulang berkas yang bermasalah.)"
            else:
                try:
                    data = dict(nilai)
                    for field, label, _ok in BERKAS_FORM:
                        data[field] = drive_io.upload_berkas(
                            request.files[field], nilai["nama"], f'{k["awalan_berkas"]} - {label}')
                    k["simpan"](data)
                    pesan = k["pesan_sukses"].format(nama=nilai["nama"])
                    berhasil = True
                    nilai = {}
                except (KonfigurasiBelumLengkap, berkas_umum.KonfigurasiBelumLengkap):
                    app.logger.exception("Konfigurasi form %s belum lengkap", kunci)
                    pesan = "Belum bisa menyimpan data karena pengaturan sistem belum lengkap. Silakan hubungi pengelola."
                except berkas_umum.BerkasTidakValid as e:
                    pesan = str(e)
                except Exception:
                    app.logger.exception("Gagal menyimpan form %s", kunci)
                    pesan = ("Gagal menyimpan data karena gangguan sementara - silakan coba lagi "
                             "(berkas perlu dipilih ulang).")

    return render_template("form_berkas.html", pesan=pesan, berhasil=berhasil, nilai=nilai,
                           berkas=BERKAS_FORM, judul_halaman=k["judul_halaman"],
                           judul_kartu=k["judul_kartu"], pengantar=k["pengantar"],
                           tombol=k["tombol"], syarat=k["syarat"], angkatan_wajib=k["angkatan_wajib"])


@app.route("/wi-basic", methods=["GET", "POST"])
def wi_basic():
    return _form_berkas("wi_basic")


@app.route("/anggota", methods=["GET", "POST"])
def anggota():
    return _form_berkas("anggota")


@app.route("/admin/wi-basic")
@perlu_login
def admin_wi_basic():
    try:
        rows = baca_semua_wi_basic()
    except KonfigurasiBelumLengkap as e:
        return f"Setup Google Sheets belum selesai: {e}", 500
    return render_template("admin.html", rows=rows, kolom=KOLOM_WI_BASIC, sheet_url=sheet_url())


@app.route("/admin/anggota")
@perlu_login
def admin_anggota():
    try:
        rows = baca_semua_anggota()
    except KonfigurasiBelumLengkap as e:
        return f"Setup Google Sheets belum selesai: {e}", 500
    return render_template("admin.html", rows=rows, kolom=KOLOM_ANGGOTA, sheet_url=sheet_url())


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
