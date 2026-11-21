# TEST TUTORIAL: try everything safely before the real party

Goal: prove the QR, the email, the scanner and the food QR work, without emailing any guest.
Time needed: about 30 minutes.

Your folder: C:\Users\ayawk\OneDrive\Desktop\party-qr
Your test address: 25002397@uv.edu.ph
Sheet link (use it in every command):
https://docs.google.com/spreadsheets/d/1vGUigKtklXFcZFl_kATrivCzzxhowgwBNfuiiZQBYqg/edit?usp=sharing

Open Command Prompt or PowerShell and start every session with:
cd C:\Users\ayawk\OneDrive\Desktop\party-qr

Before you start

- The sheet is shared as "Anyone with the link: Viewer".
- The new files from the latest zip are in the folder (send_qr.py, index.html, firebase.json).
- You ran once: pip install -r requirements.txt

---

## TEST 1. Can the script read the sheet? (sends nothing)

    python send_qr.py --sheet "https://docs.google.com/spreadsheets/d/1vGUigKtklXFcZFl_kATrivCzzxhowgwBNfuiiZQBYqg/edit?usp=sharing" --only "Kent Belarmino" --send --dry-run --test-to 25002397@uv.edu.ph

Expected:

- A "Tabs found:" list: BSIT, BSME, BS Arch, BSEE, BSCS/AI, BSCE with "x paid, y not paid" per tab. OVER ALL TOTALS is "skipped".
- "Not paid, skipped (...)" listing names. Compare with your sheet.
- "Created secret.key..." (first run only).
- "Confirmed attendees: 1 (TEST selection)"
- "[dry-run] would send to 25002397@uv.edu.ph (Kent Israel Belarmino)"
  If the numbers per tab do not match your sheet, stop and fix the sheet or tell me.

---

## TEST 2. Send a real test email to yourself

    python send_qr.py --sheet "https://docs.google.com/spreadsheets/d/1vGUigKtklXFcZFl_kATrivCzzxhowgwBNfuiiZQBYqg/edit?usp=sharing" --only "Kent Belarmino" --send --test-to 25002397@uv.edu.ph

1. The terminal shows: open https://microsoft.com/devicelogin and enter a code.
2. Open that page in Brave, type the code, sign in as 25002397@uv.edu.ph, click Accept.
3. Back in the terminal you see "Signed in." then "+ sent: Kent Israel Belarmino -> 25002397@uv.edu.ph".
4. Check your inbox: the email has the QR in the message and as an attachment.
   Nobody else gets anything, and this send is not saved in the sent log.

If the sign-in page says "Need admin approval", your school blocks this method. Use the manual backup instead:
python send_qr.py --sheet "<link>" --only "Kent Belarmino" --manual
Open out\manual_send.html, click Copy QR, then Open in Outlook Web, paste the QR with Ctrl+V and send it to yourself. That path always works.

---

## TEST 3. Does the QR hold the right data?

Scan the emailed QR with your phone camera. You should see:
Kent Israel Belarmino|XXXXXXXXXXXX
(the name, a bar, then 12 letters/numbers). If you only see a name, you are using an old QR. Run the script again.

---

## TEST 4. Start the scanner page

1. Make a small guest list of 5 people (the first 5 paid people):
   python send_qr.py --sheet "<link>" --limit 5
   Entry QR images are in out\qr and food QR images in out\qr_food.
2. In VS Code: File > Open Folder > party-qr. Right-click index.html > Open with Live Server.
3. Make sure the address starts with http://127.0.0.1:5500 or http://localhost:5500.
4. The counter at the top should say "0 checked in of 5".
   Under it you will see "Not connected to Firebase" until Test 7. That is fine for now.

---

## TEST 5. Attendance checks

Attendance tab > Start camera > allow camera. Hold a QR (from your phone, or a PNG from out\qr opened on another screen) in front of the camera.

Do these and compare:
a) Scan a valid QR -> GREEN "Checked in".
b) Scan the same QR again -> YELLOW "Already checked in at ...".
c) Fake name-only QR -> RED "no security code". Make one: search "free QR code generator" on your phone, type only a guest's name, show it to the camera.
d) Name + wrong code -> RED "Invalid QR". In the generator type e.g. Pearl Joy Letigio|AAAAAAAAAAAA
e) Name that is not in the 5 -> RED "Not on the confirmed list".
f) No camera? Type a guest's name in the box and press Check in -> GREEN, and the list shows it as "typed".
Check in at least 3 people.

Camera problems? See the troubleshooting list at the bottom.

---

## TEST 6. Food QR

1. Open the Food tab (the title changes to "Food: scan the FOOD QR").
2. Scan a guest's FOOD QR (the second QR in the test email, or a PNG from out\qr_food) -> GREEN "Food claimed".
3. Scan the same food QR again -> YELLOW "Food already claimed ... One meal only."
4. Scan that guest's ENTRY QR on the Food tab -> RED "This is an ENTRY QR, not a food QR."
5. Go back to the Attendance tab and scan a FOOD QR -> RED "This is a FOOD QR, not an entry QR."
6. Type a name in the box and press Give food -> GREEN (the manual box needs no QR).
7. Checked-in list tab > Download attendance CSV. Open it: the rows are grouped by department (then name), with Checked in, Method and Food claimed columns.

---

## TEST 7. Firebase (shared live data)

Do this only after Tests 1 to 6 pass. Setup steps are in TUTORIAL_FULL.md, Part 5.

1. Fill in firebase-config.js, refresh the page (Ctrl+Shift+R).
2. Under the counter you should see green "Live sync with Firebase is on".
3. Open the same page on your phone (use the https Firebase link, see TUTORIAL_FULL.md Part 6) or in a second browser window.
4. Check someone in on one device: they appear on the other within a second or two.
5. Scan the same QR on the second device: YELLOW "Already checked in" (this proves no double check-in across phones).

---

## TEST 8. Clean up, then go live

1. Checked-in list tab > Reset everything (this clears the shared test data too).
2. Rebuild the FULL guest list (no --only, no --limit):
   python send_qr.py --sheet "<link>"
   The counter should now say "of N" with N = number of paid guests.
3. Reload the scanner (Ctrl+Shift+R) and scan one QR to confirm green, then Reset again.
4. Follow TUTORIAL_FULL.md Part 4 to send the real emails.

---

## Pass checklist

[ ] Tab numbers match the sheet [ ] Test email arrived with QR
[ ] Scan shows Name|CODE [ ] Valid QR = green, repeat = yellow
[ ] Name-only QR = red [ ] Wrong-code QR = red
[ ] Unlisted name = red [ ] Food QR green, repeat = yellow
[ ] Entry QR on Food tab = red [ ] CSV sorted by department
[ ] Firebase live sync (if using it) [ ] Reset done, full list rebuilt

---

## Quick fixes

- Everyone is RED: attendees.js still holds a test list (from --only or --limit). Run the script without them, then Ctrl+Shift+R.
- "NotReadableError": another app or tab is using the camera. Close Zoom/Teams/Camera app/other tabs, check Windows Settings > Privacy & security > Camera, then press Start camera.
- "NotAllowedError": click the lock icon in the address bar, set Camera to Allow, reload.
- Camera blocked: open the page as http://127.0.0.1:5500, never through a 192.168.x.x address.
- "Could not download the sheet": share it as Anyone with the link: Viewer.
- "No paid attendees found": each tab needs a header row with NAMES and STATUS.
- OneDrive "file in use" error: wait a few seconds and run the command again.
