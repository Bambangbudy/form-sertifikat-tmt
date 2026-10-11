# -*- coding: utf-8 -*-
"""Aturan berkas unggahan: jenis file yang diizinkan, pengecekan isi file,
dan kelas error. Dipakai oleh drive_io.py dan app.py."""

MIME = {"pdf": "application/pdf", "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}
TANDA_AWAL = {
    "pdf": (b"%PDF",),
    "jpg": (b"\xff\xd8\xff",),
    "jpeg": (b"\xff\xd8\xff",),
    "png": (b"\x89PNG\r\n\x1a\n",),
}


class KonfigurasiBelumLengkap(Exception):
    pass


class BerkasTidakValid(Exception):
    pass


class GagalUpload(Exception):
    pass


def ekstensi(file_storage):
    nama = file_storage.filename or ""
    return nama.rsplit(".", 1)[-1].lower() if "." in nama else ""


def periksa_isi(file_storage, label):
    """Pastikan isi file cocok dengan ekstensinya (bukan sekadar diganti nama).
    Return pesan error (str) atau None kalau valid."""
    if not file_storage or not file_storage.filename:
        return None
    ext = ekstensi(file_storage)
    awal = file_storage.read(16)
    file_storage.seek(0)
    if not any(awal.startswith(tanda) for tanda in TANDA_AWAL.get(ext, ())):
        return f"{label} bukan file {ext.upper()} yang valid."
    return None
