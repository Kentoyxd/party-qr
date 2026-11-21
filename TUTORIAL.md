# Acquaintance Party QR System: Full Tutorial

What you get

- `send_qr.py` makes two QR codes for every paid attendee (ENTRY and FOOD) and emails both. The QR holds their name plus a secret code, so a homemade QR with just a name is rejected.
- `index.html` is the page you use at the entrance: Attendance tab = entry, Food tab = one meal per guest.
- Firebase stores the check-ins and food claims online, so more than one phone can scan.

Folder contents
party-qr/ (everything is in this one folder)
send_qr.py QR maker + emailer + manual-send maker
requirements.txt Python packages
index.html scanner page (attendance + food)
firebase-config.js paste your Firebase keys here
attendees.js allowed names (the script rewrites it)
firebase.json hosting settings (publishes only the page files, never your emails or script)
firestore.rules Firebase security rules (paste into Firebase)
secret.key created by the script: the private key behind every QR code (never share or upload)
TUTORIAL.md this file
emails.csv you create this (Part 2)
out/ created by the script: QR images, sent log, manual-send page

---

## PART 1. One-time setup on your computer

1. Install Python 3.9 or newer from python.org (tick "Add Python to PATH").
2. Open a terminal (Windows: search "cmd") and go to the folder:
   cd path\to\party-qr
3. Install the packages:
   pip install -r requirements.txt
   (On Windows this also installs pywin32, needed for sending through Outlook.)

---

## PART 2. Prepare the data

1. Google Sheet: Share > General access > "Anyone with the link" > Viewer.
   In each tab the script reads the table headed NAMES / STATUS / PAYMENT METHOD / DATE PAID / Outlook.
   The script downloads every tab (BSIT, BSME, BS Arch, BSEE, BSCS/AI, BSCE). The tab name becomes the department, and a tab such as OVER ALL TOTALS with no NAMES/STATUS table is skipped.
2. Emails come from the OUTLOOK (or EMAIL) column in your sheet, so you do not need `emails.csv` or `--emails`. (Only if the sheet has no email column: create a file `emails.csv` in the party-qr folder:
   name,email
   Pearl Joy Letigio,pearl.letigio@uv.edu.ph
   Daniela Codizar,daniela.codizar@uv.edu.ph
   Names must match the sheet (order of words and commas do not matter). Save as CSV UTF-8.
3. Who counts as "confirmed"? DATE PAID is ignored. If the table has a STATUS column, only people marked Paid are included (Unpaid and blank are skipped). Otherwise a person counts as paid when PAYMENT METHOD is filled in. The script prints which rule it used and lists anyone it skipped as not paid.

---

## PART 3. Generate the QR codes (no emails yet)

       python send_qr.py --sheet "https://docs.google.com/spreadsheets/d/1vGUigKtklXFcZFl_kATrivCzzxhowgwBNfuiiZQBYqg/edit?usp=sharing"

Result:

- `out/qr/` has one PNG per person. Open a few and test them with your phone camera: they should show the name.
- `attendees.js` now holds the real guest list.
  It prints how many people have no email so you can fix them.

---

## PART 3b. Test with one person first

    python send_qr.py --sheet "<link>" --only "Pearl Joy Letigio" --send --test-to yourname@uv.edu.ph

`--only` picks one person (part of the name is enough), and `--test-to` sends their QR to YOUR address instead of theirs, so no guest gets a test email. Test sends are not recorded in the sent log. Remove `--test-to` to send to the guest's own email. Note: with `--only`, `attendees.js` contains only that person, so re-run without `--only` before the party.

---

## PART 4. Send the emails

A) Outlook on the web account (default, no desktop app needed)
The script asks Microsoft to sign you in through your browser, then sends from your @uv.edu.ph mailbox.

1.  Preview first (sends nothing):
    python send_qr.py --sheet "<link>" --send --dry-run
2.  Send for real:
    python send_qr.py --sheet "https://docs.google.com/spreadsheets/d/1vGUigKtklXFcZFl_kATrivCzzxhowgwBNfuiiZQBYqg/edit?usp=sharing" --send
3.  The terminal prints a message like "open https://microsoft.com/devicelogin and enter code ABCD1234".
    Open that page in Brave, enter the code, sign in with your @uv.edu.ph account, and click Accept.
4.  Go back to the terminal. It says "Signed in." and starts sending.
    If the sign-in page says "Need admin approval", your school blocks this method: use B or C.

B) SMTP with your password (only if the school allows it; fails when MFA is required)
set SMTP_USER=25002397@uv.edu.ph (Mac/Linux: export SMTP_USER=...)
set SMTP_PASS=your-password
python send_qr.py --sheet "<link>" --send --method smtp
Microsoft disables this login method by default for school tenants at the end of December 2026. If you see "Login refused", use A or C.

C) Manual send (always works, uses Outlook on the web)
python send_qr.py --sheet "<link>" --manual
Open `out\manual_send.html`. For each person: Copy QR > Open in Outlook Web (address, subject and message are filled in) > paste the QR with Ctrl+V > Send > tick "Sent". `out/manual_send.csv` is for mail merge.

D) Outlook desktop app (only if you have it): add `--method outlook`.

Safe to re-run: `out/sent_log.csv` remembers who already got an email, so nobody gets two.
Microsoft limits how fast you can send; the script waits 2.5 seconds between emails (change with `--delay`).

---

## PART 5. Set up Firebase (about 10 minutes, free plan is enough)

1. Go to console.firebase.google.com > Add project (any name). Analytics can be off.
2. Build > Firestore Database > Create database > production mode > pick a region near you (for example asia-southeast1).
3. Build > Authentication > Get started > Sign-in method > Anonymous > Enable > Save.
4. Firestore Database > Rules tab > delete everything, paste the contents of `firestore.rules` > Publish.
5. Project settings (gear icon) > Your apps > click the web icon </> > register an app (no hosting needed yet) > copy the `firebaseConfig` values.
6. Open `firebase-config.js` and replace the four PASTE\_... values with yours. Save.

---

## PART 6. Put the page online (needed for the camera)

Phone cameras only work on secure pages (HTTPS). Easiest: Firebase Hosting. `firebase.json` is already set up for you.

1. Install Node.js (nodejs.org), then in the terminal:
   npm install -g firebase-tools
   firebase login
2. In the party-qr folder, link the folder to your Firebase project (pick it from the list):
   firebase use --add
3. Publish:
   firebase deploy --only hosting
   It prints a link like https://your-project.web.app. Open it on your phone.
   Only index.html, firebase-config.js and attendees.js are published. The script, emails.csv, the out folder and the guides are ignored.

No hosting? Test on a laptop only: in the party-qr folder run `python -m http.server 8000 --bind 127.0.0.1` and open http://localhost:8000 (camera works on localhost). Netlify Drop or GitHub Pages also work, but put only index.html, firebase-config.js and attendees.js in the upload (never emails.csv), then add that domain in Firebase > Authentication > Settings > Authorized domains.

Tip: after you change the guest list, run the script again and redeploy (`firebase deploy --only hosting`) so `attendees.js` is updated.

---

## PART 7. Event day

Check-in

1. Open your link on each entrance phone. Under the guest counter you should see green text "Live sync with Firebase is on".
2. Attendance tab > Start camera > allow camera access.
3. Guest shows their QR:
   - Green = checked in. Let them in.
   - Yellow = already checked in earlier (shows the time).
   - Red = name not on the confirmed list. Check payment first.
4. QR will not scan, or phone is dead? Type the name in the box, pick from the suggestions, press Check in.
5. "Switch camera" flips between front and back cameras.

Food (one meal per guest)

1. Open the page on the food-counter phone and tap the Food tab. (The title says "Food: scan the FOOD QR".)
2. Guest shows the FOOD QR (second QR in their email):
   - GREEN food claimed, give 1 meal.
   - YELLOW this guest already took their meal (time shown). Do not serve again.
   - RED wrong or fake code, or not on the paid list. If it says "This is an ENTRY QR", ask for the food QR.
3. Lost QR or dead phone: type the name in the box and press Give food.
4. The header shows "x checked in of N · y meals claimed" and stays in sync on every phone.
5. Food does not require check-in first. Use the Attendance tab at the entrance and the Food tab at the counter.

After the party

- "Checked-in list" tab > Download attendance CSV (sorted by department: department, name, checked in, method, food claimed).
- "Reset everything" wipes the database for all devices. Only use it for a test run before the party or after you saved the CSV.

---

## PART 8. Test before the real day

1. Send a QR to yourself and one friend.
2. Scan on the hosted page: expect green, then scan again: expect yellow.
3. Check in 2 or 3 people, give food to a few of them on the Food tab, download the CSV.
4. Press "Reset everything" to clear the test data.

---

## Troubleshooting

- Camera does not start: the page must be HTTPS or localhost, and the browser must have camera permission.
- "NotReadableError: Could not start video source": another app or tab is holding the camera. Close Zoom/Teams/Camera app/other browser tabs (and the same page open twice), then press Start camera. On Windows also check Settings > Privacy & security > Camera (allow apps and desktop apps). Unplug/replug a USB webcam or restart the browser if it persists.
- "NotAllowedError": click the lock icon in the Brave address bar, set Camera to Allow, reload. If Brave Shields is on, try lowering it for the page.
- VS Code Live Server: open http://127.0.0.1:5500 or http://localhost:5500. Do not open it by your 192.168.x.x network address; the camera is blocked there. For phones use the https Firebase link.
- "Scanner library did not load": the device has no internet; the scanner code is loaded from cdnjs.
- Status says "Not connected to Firebase": the PASTE\_... values in `firebase-config.js` were not replaced, or the file was not redeployed.
- "Sync error: Missing or insufficient permissions": Anonymous sign-in is not enabled, or the rules were not published (Part 5, steps 3 and 4).
- "auth/unauthorized-domain": add your hosting domain under Authentication > Settings > Authorized domains.
- Script says "No paid attendees found": each tab needs a header row containing NAMES and STATUS.
- Everyone shows red on the scanner: `attendees.js` has old names. Re-run the script and redeploy.
- A guest's name was spelled differently in the sheet and the QR (for example after a sheet edit): re-run the script to rebuild that QR, or use the manual name box.
- "no email: ..." lines: that person is missing from `emails.csv`.

Privacy and security notes

- Secret codes: each QR contains `Name|CODE`. The code is made from `secret.key` (created the first time you run the script). The scanner page only knows a scrambled form of each code, so people cannot work out valid codes from the page. A QR with only a name, or with a wrong code, shows red "Invalid QR".
- Keep `secret.key` safe and do not delete it. If it is lost or changed, all codes change and every QR must be re-sent (run the script with `--send --resend`). The file is never published by `firebase deploy`.
- After updating to the secret-code version, old name-only QR codes no longer work. Re-run the script, then send again with `--resend`.
- Typing a name in the manual box still works without a code. This is for staff when a guest lost their QR. Those entries are marked "typed" in the list and the CSV.
- A real QR can still be copied from a screenshot. Tell guests not to post it. The scanner blocks a second check-in with the same QR, so a copied QR works only once.
- The page uses anonymous sign-in, so anyone who has your page link can write to the database. Keep the link within your organizers and run Reset after the event. Delete the Firebase project when you no longer need it.
- Do not share `emails.csv` or the `out` folder publicly; they contain student data.
