"""Rename Google Sheet tabs and title via Sheets API using Chrome cookies."""
import base64, hashlib, json, os, shutil, sqlite3, struct, tempfile, time, urllib.request
import win32crypt
from Crypto.Cipher import AES

SPREADSHEET_ID = "1jA6lH-RMiAgFp6PECzpxiTLxtW4KhKFwOIpqeW7qBZw"

def get_chrome_key():
    path = os.path.join(os.environ["LOCALAPPDATA"], "Google", "Chrome", "User Data", "Local State")
    enc_key = base64.b64decode(json.load(open(path))["os_crypt"]["encrypted_key"])[5:]
    return win32crypt.CryptUnprotectData(enc_key, None, None, None, 0)[1]

def decrypt_val(key, enc):
    if enc[:3] in (b"v10", b"v11"):
        cipher = AES.new(key, AES.MODE_GCM, nonce=enc[3:15])
        return cipher.decrypt_and_verify(enc[15:-16], enc[-16:]).decode()
    return win32crypt.CryptUnprotectData(enc, None, None, None, 0)[1].decode()

def get_cookies():
    src = os.path.join(os.environ["LOCALAPPDATA"], "Google", "Chrome", "User Data", "Default", "Network", "Cookies")
    tmp = tempfile.mktemp(suffix=".db")
    # Try shadow copy via robocopy
    os.system(f'robocopy "{os.path.dirname(src)}" "{os.path.dirname(tmp)}" "{os.path.basename(src)}" /B /NJH /NJS /NFL /NDL > nul 2>&1')
    if not os.path.exists(tmp):
        shutil.copy2(src, tmp)
    key = get_chrome_key()
    conn = sqlite3.connect(f"file:{tmp}?immutable=1", uri=True)
    targets = {"SAPISID","__Secure-3PAPISID","SID","HSID","SSID","__Secure-1PSID","__Secure-3PSID","NID"}
    cookies = {}
    for row in conn.execute("SELECT name, encrypted_value FROM cookies WHERE host_key LIKE '%google.com'"):
        if row[0] in targets and row[1]:
            try:
                cookies[row[0]] = decrypt_val(key, row[1])
            except: pass
    conn.close()
    os.unlink(tmp)
    return cookies

def sapisid_hash(sapisid, origin="https://docs.google.com"):
    ts = int(time.time())
    h = hashlib.sha1(f"{ts} {sapisid} {origin}".encode()).hexdigest()
    return f"SAPISIDHASH {ts}_{h}"

def sheets_api(cookies, method, path, body=None):
    sapisid = cookies.get("SAPISID") or cookies.get("__Secure-3PAPISID","")
    headers = {
        "Authorization": sapisid_hash(sapisid),
        "Content-Type": "application/json",
        "Cookie": "; ".join(f"{k}={v}" for k,v in cookies.items()),
        "Origin": "https://docs.google.com",
        "Referer": f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/",
        "X-Origin": "https://docs.google.com",
    }
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

def main():
    print("Getting Chrome cookies...")
    cookies = get_cookies()
    print(f"Found: {list(cookies.keys())}")

    # Get current sheet info
    info = sheets_api(cookies, "GET", "?fields=sheets.properties,properties.title")
    print(f"Spreadsheet: {info['properties']['title']}")
    sheets = info["sheets"]
    for s in sheets:
        print(f"  gid={s['properties']['sheetId']} title={s['properties']['title']}")

    # Build rename requests
    tab_names = ["Trades", "Reflections", "Strategy"]
    requests = []

    # Rename spreadsheet title
    requests.append({"updateSpreadsheetProperties": {
        "properties": {"title": "Hermes Trading - BTC/USDT"},
        "fields": "title"
    }})

    # Rename each sheet tab
    for i, sheet in enumerate(sheets[:3]):
        requests.append({"updateSheetProperties": {
            "properties": {"sheetId": sheet["properties"]["sheetId"], "title": tab_names[i]},
            "fields": "title"
        }})

    result = sheets_api(cookies, "POST", ":batchUpdate", {"requests": requests})
    print(f"Done: {len(result.get('replies', []))} updates applied")
    print("Spreadsheet renamed to: Hermes Trading - BTC/USDT")
    print(f"Tabs renamed to: {', '.join(tab_names)}")

if __name__ == "__main__":
    main()
