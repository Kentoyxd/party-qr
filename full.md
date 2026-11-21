# FULL TUTORIAL: Acquaintance Party QR check-in, email and food

What you get

- send_qr.py reads your Google Sheet, makes TWO QR codes for every PAID guest (an ENTRY QR and a FOOD QR) and emails both.
  Each QR holds the guest's name plus a secret code, so a homemade QR is rejected. The two codes are different, so an entry QR cannot be used for food.
- index.html is the scanner page: Attendance tab = entry, Food tab = one meal per guest.
- Firebase stores check-ins and food claims online so several phones can scan at once.

Folder: C:\Users\ayawk\OneDrive\Desktop\party-qr (everything is in this one folder)
send_qr.py QR maker, emailer, manual-send maker
requirements.txt Python packages
index.html scanner page (attendance + food)
firebase-config.js your Firebase keys (you fill this in)
attendees.js guest list for the scanner (the script rewrites it)
firebase.json publishes only the page files, never your script, emails or secret key
firestore.rules Firebase security rules
secret.key made by the script: the private key behind all QR codes
out\ made by the script: QR images, sent log, manual-send page
Test first with TUTORIAL_TEST.md.

Sheet link used in every command:
https://docs.google.com/spreadsheets/d/1vGUigKtklXFcZFl_kATrivCzzxhowgwBNfuiiZQBYqg/edit?usp=sharing

---

## PART 1. One-time setup

1. Install Python 3.9+ from python.org (tick "Add Python to PATH").
2. Open Command Prompt or PowerShell:
   cd C:\Users\ayawk\OneDrive\Desktop\party-qr
   pip install -r requirements.txt
   Warnings like "script ... is not on PATH" are harmless.

---

## PART 2. Prepare the sheet

1. Share: Share > General access > "Anyone with the link" > Viewer.
2. The script downloads every tab (BSIT, BSME, BS Arch, BSEE, BSCS/AI, BSCE).
   - The tab name becomes the guest's department.
   - Each tab needs a header row with NAMES, STATUS, PAYMENT METHOD, DATE PAID, Outlook.
   - A tab with no such table (OVER ALL TOTALS) is skipped.
3. Who gets a QR: only rows where STATUS is Paid. Unpaid or blank are skipped. DATE PAID is ignored.
4. Emails come from the Outlook column. Fill in each guest's @uv.edu.ph address. Guests with an empty cell are listed as "without email" and are skipped when sending (give them their QR with the manual-send page).
5. Names: spelling and word order must match between the sheet and the QR. Capitals, commas and extra spaces do not matter ("Alqueza, Fritz Ryan" = "Fritz Ryan Alqueza").

---

## PART 3. Generate the QR codes

    python send_qr.py --sheet "<link>"

It prints a line per tab (paid / not paid / without email), the list of unpaid names, and "Confirmed attendees: N".
It creates:

- out\qr\*.png one ENTRY QR image per guest (name printed under it)
- out\qr_food\*\_FOOD.png one FOOD QR image per guest ("FOOD (1 meal)" printed under it)
- attendees.js the scanner's guest list
- secret.key (first run only) KEEP IT PRIVATE and do not delete it. If it is lost, every QR changes.
  Run this again any time the sheet changes (new payments, new emails). Codes stay the same for the same names.

---

## PART 4. Email the QR codes

Always preview first. Nothing is sent with --dry-run:
python send_qr.py --sheet "<link>" --send --dry-run

A) Outlook on the web account (default)
python send_qr.py --sheet "<https://docs.google.com/spreadsheets/d/1vGUigKtklXFcZFl_kATrivCzzxhowgwBNfuiiZQBYqg/edit?usp=sharing>" --send

1.  The terminal shows: open https://microsoft.com/devicelogin and enter a code.
2.  Open it in Brave, enter the code, sign in as 25002397@uv.edu.ph, click Accept.
3.  The terminal says "Signed in." and sends one email every few seconds (both QR codes are in the message and attached).
    If the page says "Need admin approval", your school blocks it: use B or C.

B) SMTP with password (only if the school allows it; fails when MFA is required)
set SMTP_USER=25002397@uv.edu.ph
set SMTP_PASS=your-password
python send_qr.py --sheet "<link>" --send --method smtp

C) Manual send (always works, uses Outlook on the web)
python send_qr.py --sheet "<link>" --manual
Open out\manual_send.html. For each guest: Copy QR, click Open in Outlook Web (address, subject and message are filled in), paste the QR with Ctrl+V, Send, then tick "Sent". Missing emails can be typed into the box. out\manual_send.csv is for mail merge.

D) Outlook desktop app (only if you have it): add --method outlook

Good to know

- out\sent_log.csv remembers who was emailed. Re-running --send only emails new people, so nobody gets two.
- Send again to everyone (for example after new QR codes): add --resend.
- Guests who ALREADY got their entry QR and now need the food QR: add --food-only. It emails only the food QR and keeps its own log (out\sent_food_log.csv).
- Test sends (--test-to) are never recorded in the log.
- Microsoft limits sending speed, so the script waits 2.5 seconds between emails (--delay changes it).
- If an email fails the script prints "FAILED" with the reason and continues. Run it again to retry only the failed ones.

---

## PART 5. Set up Firebase (free plan is enough, about 10 minutes)

1. console.firebase.google.com > Add project (analytics can be off).
2. Build > Firestore Database > Create database > production mode > a region near you (for example asia-southeast1).
3. Build > Authentication > Get started > Sign-in method > Anonymous > Enable > Save.
4. Firestore Database > Rules > replace everything with the contents of firestore.rules > Publish. (The rules now allow the checkins and food collections.)
5. Project settings (gear) > Your apps > web icon </> > register the app > copy the firebaseConfig values.
6. Open firebase-config.js and replace the four PASTE\_... values. Save.
   Without this the page still works, but saves only on that one device.

---

## PART 6. Open the scanner page

Cameras only work on secure pages (https or localhost).

On your laptop (VS Code Live Server) 1. VS Code: File > Open Folder > party-qr. 2. Right-click index.html > Open with Live Server. 3. Use http://127.0.0.1:5500 or http://localhost:5500. Never use a 192.168.x.x address.

On phones (Firebase Hosting, gives an https link)
npm install -g firebase-tools (needs Node.js from nodejs.org)
firebase login
firebase use --add (pick your project)
firebase deploy --only hosting
It prints a link like https://your-project.web.app. Open it on each scanning phone.
firebase.json publishes only index.html, firebase-config.js and attendees.js.
After changing the guest list, run the script, then deploy again.

---

## PART 7. Event day

Check-in

1. Open the page. The counter shows "x checked in of N". Green text under it: "Live sync with Firebase is on".
2. Attendance tab > Start camera. "Switch camera" flips front/back.
3. Guest shows the QR:
   - GREEN checked in, let them in.
   - YELLOW already checked in earlier (time shown).
   - RED not on the paid list, no security code, or wrong code. Do not let in until payment is checked.
4. Lost QR or dead phone: type the name in the box and press Check in. The list marks these "typed".

Food (one meal per guest)

1. Open the page on the food-counter phone and tap the Food tab. (The title says "Food: scan the FOOD QR".)
2. Guest shows the FOOD QR (second QR in their email):
   - GREEN food claimed, give 1 meal.
   - YELLOW this guest already took their meal (time shown). Do not serve again.
   - RED wrong or fake code, or not on the paid list. If it says "This is an ENTRY QR", ask for the food QR.
3. Lost QR or dead phone: type the name in the box and press Give food.
4. The header shows "x checked in of N · y meals claimed" and stays in sync on every phone.
5. Food does not require check-in first. Use the Attendance tab at the entrance and the Food tab at the counter.

---

## PART 8. After the party

- Checked-in list tab > Download attendance CSV. It is sorted by department, then name: Department, Name, Checked in, Method, Food claimed.
- "Reset everything" wipes the shared database for all devices. Only after saving the CSV.
- Delete the Firebase project if you no longer need it, and keep emails/out\ private (student data).

---

## Troubleshooting

- Everyone is RED on the scanner: attendees.js holds an old or test list. Run the script with no --only/--limit, then Ctrl+Shift+R.
- A paid guest is RED: check the unpaid list printed by the script (their STATUS may not be Paid), the spelling of their name, and that their QR was made after the secret-code update.
- Old QR codes (name only) are RED. Generate again and send with --resend.
- "NotReadableError: Could not start video source": another app or tab holds the camera. Close Zoom/Teams/Camera app/other tabs (and this page opened twice), check Windows Settings > Privacy & security > Camera, press Start camera. Replug a USB webcam or restart Brave if needed.
- "NotAllowedError": lock icon in the address bar > Camera > Allow > reload. Try lowering Brave Shields for the page.
- Camera does not start at all: the address must be https or localhost/127.0.0.1.
- "Scanner library did not load": the device has no internet.
- "Not connected to Firebase": firebase-config.js still has the PASTE\_... values, or was not redeployed.
- "Sync error: Missing or insufficient permissions": Anonymous sign-in is not enabled, or the rules were not published.
- "auth/unauthorized-domain": add your hosting domain in Firebase > Authentication > Settings > Authorized domains.
- "Could not download the sheet": share it as Anyone with the link: Viewer.
- "No paid attendees found": each tab needs a header row with NAMES and STATUS.
- "no email" lines: that guest's Outlook cell is empty.
- "Need admin approval" at sign-in: use method B or C.
- OneDrive "file in use": wait a few seconds and run again.

---

## Security notes

- Each QR contains Name|CODE. The code comes from secret.key. The scanner page only knows a scrambled form of each code, so valid codes cannot be worked out from the page. Name-only or wrong-code QRs show red.
- Keep secret.key private; never share it or upload it. It is excluded from firebase deploy.
- A real QR can still be copied from a screenshot. Tell guests not to post it. Each QR works once: one check-in and one meal per guest.
- The page uses anonymous sign-in, so anyone with your page link can write to the database. Share the link only with organizers and use Reset after the event.
- Do not share out\ or secret.key. They contain student data and the code key.

---

## Command cheat sheet

Make QR codes + guest list python send_qr.py --sheet "<link>"
Preview emails python send_qr.py --sheet "<link>" --send --dry-run
Send emails (Outlook web) python send_qr.py --sheet "<link>" --send
Send again to everyone python send_qr.py --sheet "<link>" --send --resend
Send only the food QR python send_qr.py --sheet "<link>" --send --food-only
Manual-send page python send_qr.py --sheet "<link>" --manual
Test with one person python send_qr.py --sheet "<link>" --only "Name" --send --test-to 25002397@uv.edu.ph
Test list of 5 python send_qr.py --sheet "<link>" --limit 5
