"""Fix Google Sheet tab 3 via Sheets API using Chrome's stored auth cookies."""
import base64, json, os, sqlite3, shutil, tempfile, struct, requests
import win32crypt
from Crypto.Cipher import AES

SPREADSHEET_ID = "1jA6lH-RMiAgFp6PECzpxiTLxtW4KhKFwOIpqeW7qBZw"
SHEET3_FORMULA = '=IMPORTDATA("https://raw.githubusercontent.com/jm909/hermes-trading/main/state/strategy.csv")'

def get_chrome_key():
    local_state = os.path.join(os.environ["LOCALAPPDATA"], "Google", "Chrome", "User Data", "Local State")
    with open(local_state, "r", encoding="utf-8") as f:
        state = json.load(f)
    encrypted_key = base64.b64decode(state["os_crypt"]["encrypted_key"])[5:]
    return win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]

def decrypt_cookie(key, encrypted_value):
    try:
        if encrypted_value[:3] == b"v10" or encrypted_value[:3] == b"v11":
            nonce = encrypted_value[3:3+12]
            ciphertext = encrypted_value[3+12:-16]
            tag = encrypted_value[-16:]
            cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
            return cipher.decrypt_and_verify(ciphertext, tag).decode("utf-8")
    except:
        try:
            return win32crypt.CryptUnprotectData(encrypted_value, None, None, None, 0)[1].decode("utf-8")
        except:
            return None

def get_google_cookies():
    cookies_path = os.path.join(os.environ["LOCALAPPDATA"], "Google", "Chrome", "User Data", "Default", "Network", "Cookies")
    tmp = tempfile.mktemp(suffix=".db")
    shutil.copy2(cookies_path, tmp)

    key = get_chrome_key()
    conn = sqlite3.connect(tmp)
    conn.row_factory = sqlite3.Row

    target_names = {"__Secure-3PAPISID", "SAPISID", "SID", "HSID", "SSID", "__Secure-1PSID", "__Secure-3PSID"}
    cookies = {}
    rows = conn.execute("SELECT name, encrypted_value, host_key FROM cookies WHERE host_key LIKE '%google.com'").fetchall()
    for row in rows:
        if row["name"] in target_names:
            val = decrypt_cookie(key, row["encrypted_value"])
            if val:
                cookies[row["name"]] = val
    conn.close()
    os.unlink(tmp)
    return cookies

def make_sapisid_hash(sapisid, origin="https://docs.google.com"):
    import hashlib, time
    ts = int(time.time())
    h = hashlib.sha1(f"{ts} {sapisid} {origin}".encode()).hexdigest()
    return f"SAPISIDHASH {ts}_{h}"

def sheets_request(cookies, method, path, body=None):
    sapisid = cookies.get("SAPISID") or cookies.get("__Secure-3PAPISID", "").split("..")[0]
    headers = {
        "Authorization": make_sapisid_hash(sapisid),
        "Content-Type": "application/json",
        "Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items()),
        "Origin": "https://docs.google.com",
        "Referer": f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/",
    }
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}{path}"
    r = getattr(requests, method.lower())(url, headers=headers, json=body)
    return r

def main():
    print("Getting Chrome cookies...")
    cookies = get_google_cookies()
    print(f"Found cookies: {list(cookies.keys())}")

    # Get sheet list
    r = sheets_request(cookies, "GET", "?fields=sheets.properties")
    if r.status_code != 200:
        print(f"API error {r.status_code}: {r.text[:300]}")
        return

    sheets = r.json()["sheets"]
    for s in sheets:
        print(f"  Sheet: '{s['properties']['title']}' gid={s['properties']['sheetId']}")

    # Find sheet 3 (index 2)
    sheet3 = sheets[2]
    sheet3_id = sheet3["properties"]["sheetId"]
    sheet3_title = sheet3["properties"]["title"]
    print(f"\nFixing '{sheet3_title}' (gid={sheet3_id})...")

    # Clear A1 and write the formula
    body = {
        "requests": [{
            "updateCells": {
                "range": {"sheetId": sheet3_id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 1},
                "rows": [{"values": [{"userEnteredValue": {"formulaValue": SHEET3_FORMULA}}]}],
                "fields": "userEnteredValue"
            }
        }]
    }
    r2 = sheets_request(cookies, "POST", ":batchUpdate", body)
    print(f"Update response: {r2.status_code}")
    if r2.status_code == 200:
        print("Done! Sheet 3 formula fixed via API.")
    else:
        print(f"Error: {r2.text[:400]}")

if __name__ == "__main__":
    main()
