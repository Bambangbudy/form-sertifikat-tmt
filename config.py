# -*- coding: utf-8 -*-
import os

# Password admin dibaca dari environment variable ADMIN_PASSWORD (diatur di
# Render, bukan di file ini) supaya tidak ikut ter-commit ke repo publik.
# "ganti-password-ini" cuma fallback untuk jalan di komputer lokal.
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "ganti-password-ini")

# --- Google Sheets ---
# ID Google Sheet tujuan (bagian di URL antara "/d/" dan "/edit"), contoh:
# https://docs.google.com/spreadsheets/d/INI_ID_NYA/edit -> isi "INI_ID_NYA"
GOOGLE_SHEET_ID = "1kfazgV0MBOAnNZ76VFkuGIC1ie3u21Ro0PlDNXvAULQ"

# Nama file JSON kredensial service account. JANGAN commit/share file ini -
# isinya kunci rahasia. Di Render, Secret File selalu ada di /etc/secrets/
# (path root aplikasi tidak selalu konsisten) - pakai itu kalau ada,
# kalau tidak (jalan di komputer lokal) pakai file di folder proyek.
_render_path = "/etc/secrets/service_account.json"
GOOGLE_CREDENTIALS_FILE = _render_path if os.path.exists(_render_path) else "service_account.json"
