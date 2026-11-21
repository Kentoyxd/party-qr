# Acquaintance Party QR system

Read TUTORIAL.md for the full step-by-step guide.

Quick commands (run inside this folder):
pip install -r requirements.txt
python send_qr.py --sheet "<sheet link>" --emails emails.csv # make QR codes + guest list
python send_qr.py --sheet "<sheet link>" --emails emails.csv --send # email via Outlook
python send_qr.py --sheet "<sheet link>" --emails emails.csv --manual # manual-send page (backup)
python send_qr.py --sheet "<sheet link>" --send --food-only # only the food QR (guests who already have their entry QR)
