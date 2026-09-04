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

# Nama file JSON kredensial service account (lihat SETUP_GOOGLE_SHEETS.md).
# JANGAN commit/share file ini - isinya kunci rahasia.
GOOGLE_CREDENTIALS_FILE = "service_account.json"
