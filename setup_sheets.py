"""
setup_sheets.py — NSE Pro Tracker
Run once to create all tabs with headers, formatting, and formulas.
"""
import os
from dotenv import load_dotenv
import gspread
from oauth2client.service_account import ServiceAccountCredentials

load_dotenv()
CRED = os.getenv("SHEETS_CRED_FILE", "service_account.json")
NAME = os.getenv("SHEETS_DOC_NAME",  "NSE Pro Tracker")

HEADERS = [
    "Scan Time","Symbol","Sector","Conviction","Score /30",
    "Fund /12","Trend /8","Entry /10","Hold Timeframe",
    "Buy Price","SL","T1 5%","T2 10%","T3 15%","RR",
    "ROE %","ROCE %","D/E","Net Margin %","EPS Growth %",
    "Rev Growth %","FCF Cr","Promoter %","Pledging %","Piotroski",
    "RSI","Dip %","Near Support","Near Resistance",
    "Status","Exit Price","P&L %","Notes",
]

def auth():
    scope = ["https://spreadsheets.google.com/feeds",
             "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(CRED, scope)
    return gspread.authorize(creds)

def main():
    client = auth()
    try:
        doc = client.open(NAME); print(f"Found: {NAME}")
    except gspread.SpreadsheetNotFound:
        doc = client.create(NAME); print(f"Created: {NAME}")

    # Signals tab
    try:
        sh = doc.worksheet("Signals"); sh.clear()
    except:
        sh = doc.add_worksheet("Signals", rows=2000, cols=35)
    sh.append_row(HEADERS)
    sh.format("A1:AG1", {
        "textFormat": {"bold": True},
        "backgroundColor": {"red":0.1,"green":0.1,"blue":0.1},
        "horizontalAlignment": "CENTER",
    })
    sh.freeze(rows=1)
    print("  ✅ Signals tab ready")

    # Dashboard tab
    try:
        dash = doc.worksheet("Dashboard"); dash.clear()
    except:
        dash = doc.add_worksheet("Dashboard", rows=40, cols=6)

    dash.update(values=[
        ["NSE PRO TRACKER — DASHBOARD","","","","",""],
        ["","","","","",""],
        ["Metric","Value","","Notes","",""],
        ["Total Signals","=COUNTA(Signals!B2:B2000)","","","",""],
        ["Open Trades","=COUNTIF(Signals!AD2:AD2000,\"OPEN\")","","","",""],
        ["T1 Hit (5%)","=COUNTIF(Signals!AD2:AD2000,\"T1 HIT (5%)\")","","","",""],
        ["T2 Hit (10%)","=COUNTIF(Signals!AD2:AD2000,\"T2 HIT (10%)\")","","","",""],
        ["T3 Hit (15%)","=COUNTIF(Signals!AD2:AD2000,\"T3 HIT (15%)\")","","","",""],
        ["SL Hit","=COUNTIF(Signals!AD2:AD2000,\"SL HIT\")","","","",""],
        ["Win Rate","=IFERROR((D6+D7+D8)/(D6+D7+D8+D9),0)","","Trades reaching T1 or above","",""],
        ["Avg Score /30","=IFERROR(AVERAGE(Signals!E2:E2000),0)","","","",""],
        ["Avg RR","=IFERROR(AVERAGE(Signals!O2:O2000),0)","","","",""],
        ["","","","","",""],
        ["STRONG BUY ★★★ signals","=COUNTIF(Signals!D2:D2000,\"STRONG BUY ★★★\")","","Score 25-30","",""],
        ["GOOD BUY ★★ signals","=COUNTIF(Signals!D2:D2000,\"GOOD BUY ★★\")","","Score 19-24","",""],
        ["","","","","",""],
        ["Reminder: Always honor SL. Strong companies recover — capital protection first.","","","","",""],
        ["Book 30-40% at T1. Move SL to entry. Hold rest for T2 (10%) or T3 (15%).","","","","",""],
    ], range_name="A1")
    dash.format("A1", {"textFormat": {"bold": True, "fontSize": 14}})
    dash.format("A3:B12", {"textFormat": {"bold": True}})
    print("  ✅ Dashboard tab ready")

    try: doc.del_worksheet(doc.worksheet("Sheet1"))
    except: pass

    print(f"\n✅ Setup complete!\n📊 {doc.url}")
    print("Share this sheet with your Google account email for access.\n")

if __name__ == "__main__":
    main()
