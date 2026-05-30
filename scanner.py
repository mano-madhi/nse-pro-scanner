"""
╔══════════════════════════════════════════════════════════════════════════╗
║         NSE PRO SCANNER — Institutional Grade Signal Engine             ║
║                                                                          ║
║  Strategy  : Buy the Dip on Quality — Full Confluence Approach          ║
║  Universe  : ~250 NSE stocks across 15 sectors                          ║
║  Filters   : Screener.in fundamentals + Full EMA Stack + S/R + Volume  ║
║  Alerts    : Telegram Bot (BUY · SL · T1 · T2 · T3)                   ║
║  Tracker   : Google Sheets (live P&L)                                   ║
║                                                                          ║
║  Scoring   : 30 points total                                             ║
║    Tier 1  : Fundamental Quality    (0–12 pts)                          ║
║    Tier 2  : Trend & EMA Stack      (0–8  pts)                          ║
║    Tier 3  : Entry Timing           (0–10 pts)                          ║
║                                                                          ║
║  Conviction:                                                             ║
║    25–30  →  STRONG BUY ★★★  (highest confidence)                      ║
║    19–24  →  GOOD BUY   ★★                                              ║
║    13–18  →  WATCHLIST  ★                                               ║
║    < 13   →  No signal                                                  ║
║                                                                          ║
║  Install:                                                                ║
║    pip install yfinance pandas ta requests gspread                      ║
║               oauth2client python-dotenv beautifulsoup4 lxml numpy      ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

import os, time, logging, json, re
from datetime import datetime, timedelta
from pathlib import Path

import yfinance as yf
import pandas as pd
import numpy as np
import ta as ta_lib
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import pytz

try:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
    SHEETS_OK = True
except ImportError:
    SHEETS_OK = False

# ── Config ───────────────────────────────────────────────────────────────────
load_dotenv()
IST              = pytz.timezone("Asia/Kolkata")
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN",   "YOUR_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID")
SHEETS_CRED_FILE = os.getenv("SHEETS_CRED_FILE", "service_account.json")
SHEETS_DOC_NAME  = os.getenv("SHEETS_DOC_NAME",  "NSE Pro Tracker")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("scanner.log")],
)
log = logging.getLogger(__name__)

SCREENER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


# ════════════════════════════════════════════════════════════════════════════
# 1.  STOCK UNIVERSE  (~250 quality stocks across 15 sectors)
# ════════════════════════════════════════════════════════════════════════════

UNIVERSE = {
    "Banking & Finance": [
        "HDFCBANK","ICICIBANK","KOTAKBANK","AXISBANK","SBIN","INDUSINDBK",
        "BANDHANBNK","FEDERALBNK","IDFCFIRSTB","PNB","BANKBARODA","CANBK",
        "BAJFINANCE","BAJAJFINSV","CHOLAFIN","MUTHOOTFIN","MANAPPURAM",
        "SBILIFE","HDFCLIFE","ICICIGI","ICICIPRULI","LICI","MFSL",
        "PNBHOUSING","LICHSGFIN","RECLTD","PFC","IRFC",
    ],
    "Information Technology": [
        "TCS","INFY","HCLTECH","WIPRO","TECHM","LTIM","PERSISTENT",
        "MPHASIS","COFORGE","OFSS","KPITTECH","TATAELXSI",
        "NIIT","MASTEK","SONATSOFTW",
    ],
    "Consumer & FMCG": [
        "HINDUNILVR","ITC","NESTLEIND","DABUR","MARICO","GODREJCP",
        "COLPAL","EMAMILTD","BRITANNIA","TATACONSUM",
        "RADICO","MCDOWELL-N",
    ],
    "Retail & Lifestyle": [
        "TITAN","ASIANPAINT","BERGEPAINT","PIDILITIND","TRENT","DMART",
        "JUBLFOOD","DEVYANI","WESTLIFE",
    ],
    "Automobile": [
        "MARUTI","M&M","TATAMOTORS","BAJAJ-AUTO","EICHERMOT","HEROMOTOCO",
        "TVSMOTOR","ASHOKLEY","BHARATFORG","MOTHERSON","BOSCHLTD",
        "ENDURANCE","BALKRISIND","APOLLOTYRE","MRF","CEATLTD",
    ],
    "Pharma & Healthcare": [
        "SUNPHARMA","DRREDDY","CIPLA","DIVISLAB","LUPIN","AUROPHARMA",
        "TORNTPHARM","ALKEM","IPCALAB","GLENMARK","BIOCON","ZYDUSLIFE",
        "ABBOTINDIA","APOLLOHOSP","FORTIS","MAXHEALTH",
        "METROPOLIS","LALPATHLAB",
    ],
    "Energy & Power": [
        "RELIANCE","ONGC","BPCL","IOC","HINDPETRO","GAIL","PETRONET",
        "ADANIGREEN","TATAPOWER","TORNTPOWER",
        "POWERGRID","NTPC","NHPC","SJVN","IREDA",
    ],
    "Infrastructure & Capital Goods": [
        "LT","SIEMENS","ABB","HAVELLS","POLYCAB","VOLTAS","BHEL",
        "THERMAX","CUMMINSIND","GRINDWELL","SCHAEFFLER","SKFINDIA",
        "HAL","BEL","COCHINSHIP","MAZAGON",
    ],
    "Metals & Mining": [
        "TATASTEEL","JSWSTEEL","HINDALCO","SAIL","VEDL","NMDC","COALINDIA",
        "APLAPOLLO","RATNAMANI","HINDCOPPER","MOIL",
    ],
    "Cement & Building": [
        "ULTRACEMCO","SHREECEM","AMBUJACEM","ACC","JKCEMENT","RAMCOCEM",
        "DALMIA","HEIDELBERG",
    ],
    "Chemicals & Specialty": [
        "SRF","DEEPAKNITRITE","TATACHEM","GNFC","ATUL","NAVINFLUOR",
        "ALKYLAMINE","VINATIORGA","GALAXYSURF","FINEORG",
    ],
    "Telecom & Logistics": [
        "BHARTIARTL","INDUSTOWER","TATACOMM","RAILTEL",
        "ADANIPORTS","CONCOR","BLUEDART","IRCTC","TCI",
    ],
    "Real Estate": [
        "DLF","GODREJPROP","OBEROIRLTY","PRESTIGE","BRIGADE","SOBHA","PHOENIXLTD",
    ],
    "Consumption & Internet": [
        "PAGEIND","DIXON","AMBER","VGUARD","CROMPTON",
        "FINPIPE","NAUKRI","INDIAMART",
    ],
}

ALL_STOCKS = list(dict.fromkeys(
    sym for stocks in UNIVERSE.values() for sym in stocks
))

def nse(sym):
    return f"{sym}.NS"

def sector_of(sym):
    return next((s for s, lst in UNIVERSE.items() if sym in lst), "Unknown")


# ════════════════════════════════════════════════════════════════════════════
# 2.  FUNDAMENTAL DATA — yfinance PRIMARY + Screener.in FALLBACK
#     yfinance works reliably from GitHub Actions (no blocking)
#     Screener.in used as optional enhancement when available
# ════════════════════════════════════════════════════════════════════════════

_FUND_CACHE: dict = {}

def _parse_num(text: str) -> float | None:
    """Clean and parse a number string."""
    if not text:
        return None
    text = str(text).replace(",","").replace("%","").replace("₹","").strip()
    try:
        return float(text)
    except:
        return None


def fetch_fundamentals(symbol: str) -> dict:
    """
    Fetch fundamentals using yfinance as primary source.
    Reliable from GitHub Actions — no blocking issues.
    """
    if symbol in _FUND_CACHE:
        return _FUND_CACHE[symbol]

    data = {"symbol": symbol}
    ticker = nse(symbol)

    try:
        tk   = yf.Ticker(ticker)
        info = tk.info or {}

        # ── Core metrics from yfinance info ──────────────────────────────────
        data["roe"]             = _parse_num(info.get("returnOnEquity"))
        data["de"]              = _parse_num(info.get("debtToEquity"))
        data["current_ratio"]   = _parse_num(info.get("currentRatio"))
        data["pe"]              = _parse_num(info.get("trailingPE"))
        data["market_cap_cr"]   = (info.get("marketCap") or 0) / 1e7
        data["rev_growth_pct"]  = (_parse_num(info.get("revenueGrowth")) or 0) * 100
        data["net_margin_latest"]= (_parse_num(info.get("profitMargins")) or 0) * 100
        data["eps_growth_yoy"]  = (_parse_num(info.get("earningsGrowth")) or 0) * 100
        data["promoter_holding"]= (_parse_num(info.get("heldPercentInsiders")) or 0) * 100
        data["div_yield"]       = (_parse_num(info.get("dividendYield")) or 0) * 100
        data["book_value"]      = _parse_num(info.get("bookValue"))
        data["52w_high"]        = _parse_num(info.get("fiftyTwoWeekHigh"))
        data["52w_low"]         = _parse_num(info.get("fiftyTwoWeekLow"))

        # Convert ROE from decimal to percentage if needed
        roe = data.get("roe")
        if roe and abs(roe) < 5:
            data["roe"] = roe * 100

        # Convert D/E — yfinance gives it as percentage sometimes
        de = data.get("de")
        if de and de > 20:
            data["de"] = de / 100

        # ── FCF from cashflow statement ───────────────────────────────────────
        try:
            cf = tk.cashflow
            if cf is not None and not cf.empty:
                cfo_row   = None
                capex_row = None
                for idx in cf.index:
                    idx_lower = str(idx).lower()
                    if "operating" in idx_lower and "cash" in idx_lower:
                        cfo_row = idx
                    if "capital" in idx_lower or "capex" in idx_lower:
                        capex_row = idx
                if cfo_row is not None:
                    cfo = float(cf.loc[cfo_row].iloc[0]) / 1e7
                    data["cfo"] = round(cfo, 1)
                    if capex_row is not None:
                        capex = float(cf.loc[capex_row].iloc[0]) / 1e7
                        data["fcf"] = round(cfo + capex, 1)
                    else:
                        data["fcf"] = round(cfo, 1)
        except Exception:
            pass

        # ── ROCE proxy from financials ─────────────────────────────────────────
        try:
            fin = tk.financials
            if fin is not None and not fin.empty:
                ebit_row = None
                for idx in fin.index:
                    if "ebit" in str(idx).lower() or "operating income" in str(idx).lower():
                        ebit_row = idx
                        break
                bs = tk.balance_sheet
                if ebit_row is not None and bs is not None and not bs.empty:
                    ebit = float(fin.loc[ebit_row].iloc[0])
                    total_assets = None
                    current_liab = None
                    for idx in bs.index:
                        il = str(idx).lower()
                        if "total assets" in il:
                            total_assets = float(bs.loc[idx].iloc[0])
                        if "current liabilities" in il:
                            current_liab = float(bs.loc[idx].iloc[0])
                    if total_assets and current_liab:
                        capital_employed = total_assets - current_liab
                        if capital_employed > 0:
                            data["roce"] = round(ebit / capital_employed * 100, 1)
        except Exception:
            pass

        # ── Interest coverage proxy ───────────────────────────────────────────
        try:
            fin = tk.financials
            if fin is not None and not fin.empty:
                ebit_val = int_exp = None
                for idx in fin.index:
                    il = str(idx).lower()
                    if "ebit" in il or "operating income" in il:
                        ebit_val = float(fin.loc[idx].iloc[0])
                    if "interest expense" in il:
                        int_exp = abs(float(fin.loc[idx].iloc[0]))
                if ebit_val and int_exp and int_exp > 0:
                    data["interest_coverage"] = round(ebit_val / int_exp, 1)
                elif int_exp == 0 or int_exp is None:
                    data["interest_coverage"] = 99
        except Exception:
            pass

        # ── Piotroski F-Score ─────────────────────────────────────────────────
        fscore = 0
        if (data.get("net_margin_latest") or 0) > 0:  fscore += 1
        if (data.get("cfo") or 0) > 0:                fscore += 1
        if (data.get("eps_growth_yoy") or 0) > 0:     fscore += 1
        if (data.get("cfo") or 0) > (data.get("net_margin_latest") or 0): fscore += 1
        de2 = data.get("de")
        if de2 is not None and de2 < 1:               fscore += 1
        if (data.get("current_ratio") or 0) > 1:      fscore += 1
        if (data.get("net_margin_latest") or 0) > 8:  fscore += 1
        if (data.get("rev_growth_pct") or 0) > 0:     fscore += 1
        data["piotroski"] = fscore

        # ── Promoter pledging (yfinance doesn't have this — set safe default) ─
        # Screener.in would give this but may be blocked on cloud
        # We'll treat None as "unknown" and not hard-reject on it
        data["promoter_pledging"] = None

        log.info(f"  Fundamentals OK via yfinance: ROE={data.get('roe'):.1f}% D/E={data.get('de')} RevGrow={data.get('rev_growth_pct'):.1f}%"
                 if data.get("roe") and data.get("de") and data.get("rev_growth_pct") else
                 f"  Fundamentals fetched (some fields may be missing)")

    except Exception as e:
        log.warning(f"yfinance fundamentals failed for {symbol}: {e}")
        _FUND_CACHE[symbol] = {}
        return {}

    _FUND_CACHE[symbol] = data
    time.sleep(0.3)
    return data


def fetch_screener(symbol: str) -> dict:
    """
    Scrape key fundamentals from screener.in for a given NSE symbol.
    Returns dict with all key ratios. Returns {} on failure.
    """
    if symbol in _SCREENER_CACHE:
        return _SCREENER_CACHE[symbol]

    url = f"https://www.screener.in/company/{symbol}/consolidated/"
    try:
        resp = requests.get(url, headers=SCREENER_HEADERS, timeout=15)
        if resp.status_code == 404:
            # try standalone
            url = f"https://www.screener.in/company/{symbol}/"
            resp = requests.get(url, headers=SCREENER_HEADERS, timeout=15)
        if resp.status_code != 200:
            log.warning(f"Screener {symbol}: HTTP {resp.status_code}")
            _SCREENER_CACHE[symbol] = {}
            return {}
    except Exception as e:
        log.warning(f"Screener fetch error {symbol}: {e}")
        _SCREENER_CACHE[symbol] = {}
        return {}

    soup = BeautifulSoup(resp.text, "lxml")
    data = {"symbol": symbol}

    # ── Key ratios from the top ratio list ────────────────────────────────────
    ratio_section = soup.find("section", id="top-ratios")
    if ratio_section:
        for li in ratio_section.find_all("li"):
            name_tag = li.find("span", class_="name")
            val_tag  = li.find("span", class_="nowrap")
            if not name_tag or not val_tag:
                continue
            name = name_tag.get_text(strip=True).lower()
            val  = _parse_num(val_tag.get_text(strip=True))
            if "roe" in name:
                data["roe"] = val
            elif "roce" in name:
                data["roce"] = val
            elif "debt" in name and "equity" in name:
                data["de"] = val
            elif "current ratio" in name:
                data["current_ratio"] = val
            elif "p/e" in name or "price to earning" in name:
                data["pe"] = val
            elif "face value" in name:
                data["face_value"] = val
            elif "book value" in name:
                data["book_value"] = val
            elif "market cap" in name:
                data["market_cap_cr"] = val
            elif "dividend yield" in name:
                data["div_yield"] = val

    # ── Shareholding — promoter holding & pledging ────────────────────────────
    sh_section = soup.find("section", id="shareholding")
    if sh_section:
        tables = sh_section.find_all("table")
        for table in tables:
            headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
            rows    = table.find_all("tr")
            for row in rows:
                cols = [td.get_text(strip=True) for td in row.find_all("td")]
                if not cols:
                    continue
                label = cols[0].lower()
                if "promoter" in label and "pledge" not in label and len(cols) > 1:
                    data["promoter_holding"] = _parse_num(cols[-1])
                elif "pledg" in label and len(cols) > 1:
                    data["promoter_pledging"] = _parse_num(cols[-1])

    # ── Annual P&L table — Net Margin, EPS trend, Revenue growth ─────────────
    pl_section = soup.find("section", id="profit-loss")
    if pl_section:
        table = pl_section.find("table")
        if table:
            rows = table.find_all("tr")
            for row in rows:
                cols = [td.get_text(strip=True).replace(",","") for td in row.find_all("td")]
                if not cols:
                    continue
                label = cols[0].lower()

                # Net profit margin row
                if "net profit margin" in label or ("opm" in label and "%" in label):
                    nums = [_parse_num(c) for c in cols[1:] if _parse_num(c) is not None]
                    if nums:
                        data["net_margin_latest"] = nums[-1]
                        data["net_margin_3y_avg"] = sum(nums[-3:]) / len(nums[-3:]) if len(nums) >= 3 else nums[-1]

                # Sales / Revenue row
                if cols[0].lower() in ("sales", "revenue from operations", "net sales"):
                    nums = [_parse_num(c) for c in cols[1:] if _parse_num(c) is not None]
                    if len(nums) >= 2:
                        rev_growth = (nums[-1] - nums[-2]) / abs(nums[-2]) * 100 if nums[-2] != 0 else 0
                        data["rev_growth_pct"] = round(rev_growth, 1)
                    if len(nums) >= 4:
                        data["rev_growth_3y"] = round(
                            (nums[-1] - nums[-4]) / abs(nums[-4]) * 100 / 3
                        if nums[-4] != 0 else 0, 1)

                # EPS row
                if "eps" in label and "dilut" not in label.split("eps")[0]:
                    nums = [_parse_num(c) for c in cols[1:] if _parse_num(c) is not None]
                    if len(nums) >= 2:
                        data["eps_latest"]    = nums[-1]
                        data["eps_prev"]      = nums[-2]
                        data["eps_growth_yoy"]= round((nums[-1]-nums[-2])/abs(nums[-2])*100, 1) if nums[-2] else 0
                    if len(nums) >= 4:
                        data["eps_growth_3y"] = round(
                            (nums[-1]-nums[-4])/abs(nums[-4])*100/3
                        if nums[-4] else 0, 1)

                # Net Profit (for interest coverage proxy)
                if cols[0].lower() in ("net profit", "profit after tax", "pat"):
                    nums = [_parse_num(c) for c in cols[1:] if _parse_num(c) is not None]
                    if nums:
                        data["net_profit_latest"] = nums[-1]

                # Interest expense
                if "interest" in label and "income" not in label:
                    nums = [_parse_num(c) for c in cols[1:] if _parse_num(c) is not None]
                    if nums:
                        data["interest_expense"] = nums[-1]

                # EBIT proxy (Operating Profit)
                if "operating profit" in label or "ebit" in label:
                    nums = [_parse_num(c) for c in cols[1:] if _parse_num(c) is not None]
                    if nums:
                        data["ebit"] = nums[-1]

    # ── Cash Flow — Free Cash Flow ────────────────────────────────────────────
    cf_section = soup.find("section", id="cash-flow")
    if cf_section:
        table = cf_section.find("table")
        if table:
            rows = table.find_all("tr")
            cfo, capex = None, None
            for row in rows:
                cols = [td.get_text(strip=True).replace(",","") for td in row.find_all("td")]
                if not cols: continue
                label = cols[0].lower()
                if "operating" in label or "cfo" in label:
                    nums = [_parse_num(c) for c in cols[1:] if _parse_num(c) is not None]
                    if nums: cfo = nums[-1]
                if "investing" in label or "capex" in label or "capital expenditure" in label:
                    nums = [_parse_num(c) for c in cols[1:] if _parse_num(c) is not None]
                    if nums: capex = nums[-1]
            if cfo is not None and capex is not None:
                data["fcf"] = round(cfo + capex, 1)   # capex is usually negative
                data["cfo"] = cfo

    # ── Compute Interest Coverage ─────────────────────────────────────────────
    ebit     = data.get("ebit")
    interest = data.get("interest_expense")
    if ebit and interest and interest > 0:
        data["interest_coverage"] = round(ebit / interest, 1)
    elif interest == 0 or interest is None:
        data["interest_coverage"] = 99  # debt-free effectively

    # ── Piotroski F-Score (simplified, from available data) ───────────────────
    fscore = 0
    # Profitability (4 points)
    if data.get("net_profit_latest", 0) > 0:          fscore += 1  # positive ROA proxy
    if data.get("cfo", 0) > 0:                         fscore += 1  # positive cash flow
    if data.get("eps_growth_yoy", 0) > 0:              fscore += 1  # improving ROA
    if (data.get("cfo",0) > data.get("net_profit_latest",0)):
        fscore += 1                                                   # accruals (quality of earnings)
    # Leverage / Liquidity (3 points)
    de = data.get("de", 99)
    if de is not None and de < 1:                      fscore += 1  # lower leverage
    if data.get("current_ratio", 0) > 1:               fscore += 1  # current ratio > 1
    # no shares issued check (skip — needs historical share count)
    # Operating Efficiency (2 points)
    if data.get("net_margin_latest", 0) > data.get("net_margin_3y_avg", 0):
        fscore += 1                                                   # improving margin
    if data.get("rev_growth_pct", 0) > 0:              fscore += 1  # revenue growing
    data["piotroski"] = fscore

    _FUND_CACHE[symbol] = data
    time.sleep(1.0)
    return data


# ════════════════════════════════════════════════════════════════════════════
# 3.  FUNDAMENTAL QUALITY FILTER  (Tier 1 — max 12 points)
# ════════════════════════════════════════════════════════════════════════════

IS_BANK = {"Banking & Finance"}

def fundamental_score(sym: str, sector: str, fd: dict) -> tuple[bool, str, int, list]:
    """
    Returns (passes, fail_reason, score, scorecard_lines).
    Only hard-rejects on data we actually have — missing data = skip that check.
    """
    if not fd:
        return False, "No fundamental data available", 0, []

    is_bank = sector in IS_BANK
    score   = 0
    card    = []

    # ── HARD REJECTS — only when data is present and clearly bad ─────────────

    # 1. Promoter Pledging > 25%
    pledging = fd.get("promoter_pledging")
    if pledging is not None and pledging > 25:
        return False, f"Promoter pledging {pledging:.1f}% (>25%)", 0, []

    # 2. Revenue clearly declining
    rev_g = fd.get("rev_growth_pct")
    if rev_g is not None and rev_g < -10:
        return False, f"Revenue falling sharply ({rev_g:.1f}%)", 0, []

    # 3. Clearly loss-making
    nm = fd.get("net_margin_latest")
    if nm is not None and nm < -5:
        return False, f"Company loss-making (margin {nm:.1f}%)", 0, []

    # 4. Interest coverage dangerously low
    ic = fd.get("interest_coverage")
    if ic is not None and ic < 1.0 and not is_bank:
        return False, f"Interest coverage {ic:.1f}× (critical)", 0, []

    # ── SCORING — only score what we have data for ────────────────────────────

    # ROE
    roe = fd.get("roe")
    if roe is not None:
        if roe >= 15:   score += 2; card.append(f"ROE {roe:.1f}% ★★")
        elif roe >= 8:  score += 1; card.append(f"ROE {roe:.1f}% ★")
        elif roe < 0:   return False, f"ROE negative ({roe:.1f}%)", 0, []
    else:
        card.append("ROE: data pending")
        score += 1  # give benefit of doubt for large NSE stocks

    # ROCE
    roce = fd.get("roce")
    if roce is not None:
        if roce >= 15:  score += 2; card.append(f"ROCE {roce:.1f}% ★★")
        elif roce >= 8: score += 1; card.append(f"ROCE {roce:.1f}% ★")
    else:
        score += 1; card.append("ROCE: data pending")

    # Net Margin
    if nm is not None:
        if nm >= 12:    score += 1; card.append(f"Net Margin {nm:.1f}% ★")
        elif nm >= 5:   card.append(f"Net Margin {nm:.1f}%")
    else:
        card.append("Margin: data pending")

    # Debt/Equity
    de = fd.get("de")
    if de is not None:
        max_de = 10.0 if is_bank else 1.5
        if de <= (5.0 if is_bank else 0.5):
            score += 2; card.append(f"D/E {de:.2f} ★★ (low debt)")
        elif de <= max_de:
            score += 1; card.append(f"D/E {de:.2f} ★")
        else:
            card.append(f"⚠️ D/E {de:.2f} (high)")
    else:
        score += 1; card.append("D/E: data pending")

    # Revenue Growth
    if rev_g is not None:
        if rev_g >= 10:  score += 2; card.append(f"Rev Growth {rev_g:.1f}% ★★")
        elif rev_g >= 0: score += 1; card.append(f"Rev Growth {rev_g:.1f}% ★")
        else:            card.append(f"⚠️ Rev Growth {rev_g:.1f}%")
    else:
        score += 1; card.append("Rev Growth: data pending")

    # EPS Growth
    eps_g = fd.get("eps_growth_yoy")
    if eps_g is not None:
        if eps_g >= 10:  score += 1; card.append(f"EPS Growth {eps_g:.1f}% ★")
        elif eps_g >= 0: card.append(f"EPS Growth {eps_g:.1f}%")
        else:            card.append(f"⚠️ EPS {eps_g:.1f}%")
    else:
        card.append("EPS Growth: data pending")

    # FCF
    fcf = fd.get("fcf")
    if fcf is not None:
        if fcf > 0: score += 1; card.append(f"FCF ₹{fcf:.0f}Cr ★")
        else:       card.append(f"⚠️ FCF negative")
    else:
        card.append("FCF: data pending")

    # Market cap — large cap gets bonus
    mcap = fd.get("market_cap_cr") or 0
    if mcap >= 10000:
        score += 1; card.append(f"Large cap ₹{mcap:,.0f}Cr ★")
    elif mcap >= 2000:
        card.append(f"Mid cap ₹{mcap:,.0f}Cr")

    # Minimum score — lower threshold since some data may be missing
    if score < 3:
        return False, f"Fundamental score {score}/12 too low", 0, []

    return True, "", score, card


# ════════════════════════════════════════════════════════════════════════════
# 4.  OHLCV FETCH + FULL INDICATOR SET
# ════════════════════════════════════════════════════════════════════════════

def fetch_ohlcv(symbol: str, period="1y", interval="1d") -> pd.DataFrame | None:
    """Fetch OHLCV with retry for temporary Yahoo Finance failures."""
    for attempt in range(3):
        try:
            df = yf.download(nse(symbol), period=period, interval=interval,
                             auto_adjust=True, progress=False)
            if df.empty or len(df) < 120:
                if attempt < 2:
                    time.sleep(2)
                    continue
                return None
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df.index = pd.to_datetime(df.index)
            return df
        except Exception as e:
            if attempt < 2:
                log.warning(f"OHLCV attempt {attempt+1} failed {symbol}: {e}. Retrying...")
                time.sleep(2)
            else:
                log.warning(f"OHLCV failed after 3 attempts for {symbol}: {e}")
                return None
    return None


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    c = df["Close"].squeeze()
    h = df["High"].squeeze()
    l = df["Low"].squeeze()
    v = df["Volume"].squeeze()

    # ── EMAs (the full stack) ─────────────────────────────────────────────────
    df["ema9"]   = ta_lib.trend.ema_indicator(c, window=9)
    df["ema20"]  = ta_lib.trend.ema_indicator(c, window=20)
    df["ema50"]  = ta_lib.trend.ema_indicator(c, window=50)
    df["ema200"] = ta_lib.trend.ema_indicator(c, window=200)

    # ── Momentum ──────────────────────────────────────────────────────────────
    df["rsi"] = ta_lib.momentum.rsi(c, window=14)

    # MACD
    macd_ind = ta_lib.trend.MACD(c, window_slow=26, window_fast=12, window_sign=9)
    df["macd"]      = macd_ind.macd()
    df["macd_sig"]  = macd_ind.macd_signal()
    df["macd_hist"] = macd_ind.macd_diff()

    # Stochastic RSI
    stoch_rsi = ta_lib.momentum.StochRSIIndicator(c, window=14, smooth1=3, smooth2=3)
    df["stoch_k"] = stoch_rsi.stochrsi_k()
    df["stoch_d"] = stoch_rsi.stochrsi_d()

    # ── Volatility ────────────────────────────────────────────────────────────
    df["atr"] = ta_lib.volatility.average_true_range(h, l, c, window=14)

    # Bollinger Bands
    bb_ind = ta_lib.volatility.BollingerBands(c, window=20, window_dev=2)
    df["bb_upper"] = bb_ind.bollinger_hband()
    df["bb_lower"] = bb_ind.bollinger_lband()
    df["bb_mid"]   = bb_ind.bollinger_mavg()
    df["bb_width"] = bb_ind.bollinger_wband()

    # ── Volume ────────────────────────────────────────────────────────────────
    df["vol20"]  = v.rolling(20).mean()
    df["vol50"]  = v.rolling(50).mean()
    df["volrat"] = v / df["vol20"]

    # On Balance Volume — smart money accumulation
    df["obv"]     = ta_lib.volume.on_balance_volume(c, v)
    df["obv_ema"] = ta_lib.trend.ema_indicator(df["obv"], window=20)

    # ── Trend strength ────────────────────────────────────────────────────────
    adx_ind   = ta_lib.trend.ADXIndicator(h, l, c, window=14)
    df["adx"] = adx_ind.adx()

    return df


# ════════════════════════════════════════════════════════════════════════════
# 5.  SUPPORT & RESISTANCE ENGINE
# ════════════════════════════════════════════════════════════════════════════

def find_sr_zones(df: pd.DataFrame, lookback: int = 180, tol: float = 0.018) -> dict:
    """
    Identify significant support and resistance zones.
    Uses swing highs/lows, volume-weighted price levels, and
    round number proximity.

    Returns dict:
        supports    : list of {level, bounces, strength, type}
        resistances : list of {level, tests, strength, type}
    """
    highs = df["High"].tail(lookback)
    lows  = df["Low"].tail(lookback)
    close = df["Close"].tail(lookback)
    vol   = df["Volume"].tail(lookback)

    supports    = []
    resistances = []

    # ── Method 1: Swing Low Support zones ────────────────────────────────────
    for i, (idx, price) in enumerate(lows.items()):
        zone_lo = price * (1 - tol)
        zone_hi = price * (1 + tol)
        touches = lows[(lows >= zone_lo) & (lows <= zone_hi)]
        if len(touches) >= 2:
            already = any(abs(z["level"] - price) / price < tol for z in supports)
            if not already:
                # Volume at this zone (higher volume = stronger support)
                zone_vol = vol[(lows >= zone_lo) & (lows <= zone_hi)].mean()
                avg_vol  = vol.mean()
                vol_str  = min(round(zone_vol / avg_vol, 1), 3.0)
                strength = len(touches) + (1 if vol_str > 1.2 else 0)
                supports.append({
                    "level":    round(float(price), 2),
                    "bounces":  len(touches),
                    "strength": strength,
                    "vol_ratio": vol_str,
                    "type":     "swing_low",
                })

    # ── Method 2: Swing High Resistance zones ─────────────────────────────────
    for i, (idx, price) in enumerate(highs.items()):
        zone_lo = price * (1 - tol)
        zone_hi = price * (1 + tol)
        tests = highs[(highs >= zone_lo) & (highs <= zone_hi)]
        if len(tests) >= 2:
            already = any(abs(z["level"] - price) / price < tol for z in resistances)
            if not already:
                resistances.append({
                    "level":    round(float(price), 2),
                    "tests":    len(tests),
                    "strength": len(tests),
                    "type":     "swing_high",
                })

    # ── Method 3: Round number zones (psychological levels) ───────────────────
    current_price = float(df["Close"].iloc[-1])
    # Safe guard against NaN price
    if current_price is None or current_price != current_price:  # NaN check
        return {"supports": supports[:6], "resistances": resistances[:6]}
    try:
        current_price = float(current_price)
        magnitude = 10 ** (len(str(int(current_price))) - 2)   # e.g. ₹2850 → 100
    except (ValueError, TypeError):
        return {"supports": supports[:6], "resistances": resistances[:6]}
    for mult in range(-5, 6):
        rnd = round(current_price / magnitude) * magnitude + mult * magnitude
        if rnd <= 0:
            continue
        pct_away = abs(rnd - current_price) / current_price
        if pct_away <= 0.15:
            is_support = rnd < current_price
            zone = {
                "level":    round(rnd, 2),
                "strength": 1,
                "type":     "round_number",
            }
            if is_support:
                if not any(abs(z["level"] - rnd) / rnd < 0.01 for z in supports):
                    zone["bounces"] = 1
                    supports.append(zone)
            else:
                if not any(abs(z["level"] - rnd) / rnd < 0.01 for z in resistances):
                    zone["tests"] = 1
                    resistances.append(zone)

    # Sort by strength
    supports    = sorted(supports,    key=lambda z: z["strength"], reverse=True)
    resistances = sorted(resistances, key=lambda z: z["strength"], reverse=True)

    return {"supports": supports[:6], "resistances": resistances[:6]}


def nearest_support(price: float, zones: list, tol: float = 0.03) -> dict | None:
    """Return the nearest support zone within tol% of current price."""
    candidates = [z for z in zones if abs(price - z["level"]) / price <= tol
                  and z["level"] <= price]
    if not candidates:
        return None
    return min(candidates, key=lambda z: abs(price - z["level"]))


def nearest_resistance(price: float, zones: list) -> dict | None:
    """Return nearest resistance above current price."""
    above = [z for z in zones if z["level"] > price]
    if not above:
        return None
    return min(above, key=lambda z: z["level"])


# ════════════════════════════════════════════════════════════════════════════
# 6.  TREND & EMA STACK SCORER  (Tier 2 — max 8 points)
# ════════════════════════════════════════════════════════════════════════════

def trend_score(df: pd.DataFrame, fd: dict) -> tuple[bool, int, list]:
    """
    Evaluates the full EMA stack and long-term trend.
    Returns (passes, score, reasons).
    Hard reject if price is more than 5% below EMA200.
    """
    last  = df.iloc[-1]
    close = float(last["Close"])
    score = 0
    card  = []

    def s(key):
        try:
            v = last[key]
            if isinstance(v, pd.Series):
                v = v.iloc[0]
            return None if pd.isna(float(v)) else float(v)
        except:
            return None

    ema9   = s("ema9")
    ema20  = s("ema20")
    ema50  = s("ema50")
    ema200 = s("ema200")
    adx    = s("adx")

    if ema200 is None:
        return False, 0, []

    # ── Hard reject: too far below EMA200 ────────────────────────────────────
    ema200_gap = (close - ema200) / ema200 * 100
    if ema200_gap < -5:
        return False, 0, []

    # 1. Price above EMA200 — long term uptrend  (2 pts)
    if close >= ema200:
        score += 2; card.append("Price > EMA200 ✅ (long term uptrend)")
    else:
        score += 1; card.append(f"Price near EMA200 ({ema200_gap:.1f}%) — recovering")

    # 2. EMA50 above EMA200 — medium term healthy  (2 pts)
    if ema50 and ema50 > ema200:
        score += 2; card.append("EMA50 > EMA200 ✅ (medium trend healthy)")
    elif ema50:
        card.append("⚠️ EMA50 < EMA200 (medium term weak)")

    # 3. Price near or touching EMA50 — the ideal dip zone  (2 pts)
    if ema50:
        gap_ema50 = (close - ema50) / ema50 * 100
        if -3 <= gap_ema50 <= 5:
            score += 2; card.append(f"Price near EMA50 ({gap_ema50:+.1f}%) ✅ — ideal dip zone")
        elif -8 <= gap_ema50 < -3:
            score += 1; card.append(f"Price {gap_ema50:.1f}% below EMA50 — deeper dip")
        elif gap_ema50 > 10:
            card.append(f"Price {gap_ema50:.1f}% above EMA50 — extended, wait for pullback")

    # 4. EMA20 turning up  (1 pt)
    if ema20 and ema50:
        prev_ema20 = float(df["ema20"].iloc[-3]) if len(df) >= 3 else ema20
        if ema20 > prev_ema20:
            score += 1; card.append("EMA20 curling up ✅ — momentum returning")

    # 5. ADX trend strength  (1 pt)
    if adx:
        if adx >= 25:
            score += 1; card.append(f"ADX {adx:.0f} ✅ — strong trend")
        elif adx < 15:
            card.append(f"ADX {adx:.0f} — weak trend, sideways market")

    # 52-week dip check (your core strategy: buy the dip)
    high52 = fd.get("52w_high") or float(df["High"].tail(252).max())
    low52  = fd.get("52w_low")  or float(df["Low"].tail(252).min())
    dip_pct = (high52 - close) / high52 * 100

    return True, score, card


# ════════════════════════════════════════════════════════════════════════════
# 7.  ENTRY TIMING SCORER  (Tier 3 — max 10 points)
# ════════════════════════════════════════════════════════════════════════════

def entry_score(df: pd.DataFrame, sr: dict, fd: dict) -> tuple[bool, int, list, dict]:
    """
    Fine-grained entry timing using RSI, MACD, Stoch, Volume, BB, OBV, S/R.
    Returns (passes, score, reasons, entry_data).
    """
    last   = df.iloc[-1]
    prev   = df.iloc[-2]
    prev2  = df.iloc[-3] if len(df) >= 3 else prev
    close  = float(last["Close"])
    score  = 0
    card   = []

    def s(key, row=None):
        if row is None:
            row = last
        try:
            v = row[key]
            if isinstance(v, pd.Series):
                v = v.iloc[0]
            return None if pd.isna(float(v)) else float(v)
        except:
            return None

    rsi      = s("rsi")
    macd     = s("macd")
    macd_s   = s("macd_sig")
    macd_h   = s("macd_hist")
    stoch_k  = s("stoch_k")
    stoch_d  = s("stoch_d")
    atr      = s("atr")
    volrat   = s("volrat")
    bb_lower = s("bb_lower")
    bb_mid   = s("bb_mid")
    obv      = s("obv")
    obv_ema  = s("obv_ema")

    # ── RSI zone  (max 2 pts) ─────────────────────────────────────────────────
    if rsi is None:
        return False, 0, [], {}
    if 35 <= rsi <= 55:
        score += 2; card.append(f"RSI {rsi:.0f} ✅ — ideal buy zone (35–55)")
    elif 55 < rsi <= 65:
        score += 1; card.append(f"RSI {rsi:.0f} — acceptable (55–65)")
    elif 65 < rsi <= 70:
        card.append(f"⚠️ RSI {rsi:.0f} — slightly extended")
    elif rsi > 70:
        return False, 0, [], {}   # overbought — hard reject
    elif rsi < 30:
        card.append(f"⚠️ RSI {rsi:.0f} — oversold, may fall more")

    # ── MACD  (max 2 pts) ─────────────────────────────────────────────────────
    macd_cross = False
    if macd is not None and macd_s is not None:
        prev_macd = s("macd", prev)
        prev_sig  = s("macd_sig", prev)
        if prev_macd is None: prev_macd = macd
        if prev_sig  is None: prev_sig  = macd_s
        macd_cross = (prev_macd < prev_sig) and (macd > macd_s)
        ph = s("macd_hist", prev)
        ph2 = s("macd_hist", prev2)
        hist_turning = (
            macd_h is not None and
            ph is not None and
            ph2 is not None and
            macd_h > ph > ph2
        )
        if macd_cross:
            score += 2; card.append("MACD bullish crossover ✅ — strong entry signal")
        elif hist_turning:
            score += 1; card.append("MACD histogram turning up ✅ — momentum building")
        elif macd > macd_s:
            score += 1; card.append("MACD positive (above signal)")

    # ── Stochastic RSI  (max 1 pt) ───────────────────────────────────────────
    if stoch_k is not None and stoch_d is not None:
        prev_sk = s("stoch_k", prev) or stoch_k
        prev_sd = s("stoch_d", prev) or stoch_d
        stoch_cross = (prev_sk < prev_sd) and (stoch_k > stoch_d)
        if stoch_k < 30 and stoch_cross:
            score += 1; card.append(f"Stoch RSI {stoch_k:.0f} ✅ — oversold crossover")
        elif stoch_k < 40:
            card.append(f"Stoch RSI {stoch_k:.0f} — low, potential reversal")
        elif stoch_k > 80:
            card.append(f"⚠️ Stoch RSI {stoch_k:.0f} — overbought")

    # ── Bollinger Bands  (max 1 pt) ───────────────────────────────────────────
    if bb_lower and bb_mid:
        if close <= bb_lower * 1.01:
            score += 1; card.append("Price at/near lower Bollinger Band ✅ — mean reversion setup")
        elif close < bb_mid:
            card.append("Price below BB midline — cooling off")

    # ── Volume analysis  (max 2 pts) ──────────────────────────────────────────
    if volrat:
        # Check if red days have declining volume (selling exhaustion)
        recent = df.tail(10)
        red_days  = recent[recent["Close"] < recent["Open"]]
        green_days = recent[recent["Close"] >= recent["Open"]]
        avg_vol   = float(last.get("vol20", 1)) or 1

        red_vol_avg   = float(red_days["Volume"].mean())   if not red_days.empty   else avg_vol
        green_vol_avg = float(green_days["Volume"].mean()) if not green_days.empty else avg_vol

        vol_drying    = red_vol_avg < avg_vol * 0.85
        buyers_coming = green_vol_avg > avg_vol * 1.2

        if vol_drying:
            score += 1; card.append("📉 Selling volume drying ✅ — sellers exhausted")
        if buyers_coming:
            score += 1; card.append(f"📈 Buying volume increasing ✅ — buyers returning ({green_vol_avg/avg_vol:.1f}× avg)")
        if not vol_drying and not buyers_coming:
            card.append("Volume neutral — watching for confirmation")

    # ── OBV — Smart money accumulation  (max 1 pt) ────────────────────────────
    if obv and obv_ema:
        if obv > obv_ema:
            score += 1; card.append("OBV above EMA ✅ — smart money accumulating")
        else:
            card.append("⚠️ OBV below EMA — distribution phase")

    # ── Support/Resistance  (max 1 pt) ────────────────────────────────────────
    near_sup = nearest_support(close, sr["supports"], tol=0.03)
    near_res = nearest_resistance(close, sr["resistances"])

    if near_sup:
        score += 1
        card.append(
            f"Near support ₹{near_sup['level']} "
            f"({near_sup.get('bounces',1)}× bounce) ✅"
        )

    # RR sanity: resistance must be far enough for 10% target
    if near_res:
        upside_to_res = (near_res["level"] - close) / close * 100
        if upside_to_res < 5:
            # Resistance too close — 10% target blocked
            card.append(f"⚠️ Resistance at ₹{near_res['level']} ({upside_to_res:.1f}% away) — may limit upside")

    entry_data = {
        "rsi":         rsi,
        "macd_cross":  macd_cross,
        "stoch_k":     stoch_k,
        "near_support": near_sup,
        "near_resistance": near_res,
        "vol_drying":  vol_drying if volrat else False,
        "buyers_coming": buyers_coming if volrat else False,
        "obv_positive": (obv > obv_ema) if (obv and obv_ema) else False,
        "atr":         atr,
    }

    return True, score, card, entry_data


# ════════════════════════════════════════════════════════════════════════════
# 8.  MASTER SIGNAL ASSEMBLER
# ════════════════════════════════════════════════════════════════════════════

CONVICTION_MAP = {
    (25, 30): ("STRONG BUY ★★★", "🟢"),
    (19, 24): ("GOOD BUY ★★",    "🔵"),
    (13, 18): ("WATCHLIST ★",    "🟡"),
}

def get_conviction(score: int) -> tuple[str, str]:
    for (lo, hi), (label, emoji) in CONVICTION_MAP.items():
        if lo <= score <= hi:
            return label, emoji
    return "WATCHLIST ★", "🟡"


def build_signal(symbol: str, sector: str,
                 df: pd.DataFrame, fd: dict,
                 f_score: int, t_score: int, e_score: int,
                 entry_data: dict) -> dict | None:

    close = float(df["Close"].iloc[-1])
    atr   = entry_data.get("atr")
    if not atr:
        return None

    # ── 52-week dip context ───────────────────────────────────────────────────
    high52 = float(df["High"].tail(252).max())
    low52  = float(df["Low"].tail(252).min())
    dip_pct = round((high52 - close) / high52 * 100, 1)

    # ── Entry zone ────────────────────────────────────────────────────────────
    buy_low  = round(close * 0.998, 2)
    buy_high = round(close * 1.003, 2)

    # ── Stop Loss — smarter calculation ──────────────────────────────────────
    near_sup = entry_data.get("near_support")

    if near_sup and near_sup["level"] < close:
        # Use support zone SL — most precise
        gap_to_support = (close - near_sup["level"]) / close * 100
        if gap_to_support <= 5:
            sl = round(near_sup["level"] * 0.988, 2)   # 1.2% below support
            sl_type = f"below support ₹{near_sup['level']} ({near_sup.get('bounces',1)}× bounce)"
        else:
            # Support too far — use ATR
            sl = round(close - 1.0 * atr, 2)
            sl_type = "ATR-based (1×ATR)"
    else:
        # No nearby support — use tighter ATR
        sl = round(close - 1.0 * atr, 2)
        sl_type = "ATR-based (1×ATR)"

    sl_pct = round((close - sl) / close * 100, 1)

    # Hard reject if SL too tight or too wide
    if sl_pct < 1.0 or sl_pct > 8.0:
        return None

    # ── Targets (your 10% goal is T2) ────────────────────────────────────────
    t1 = round(close * 1.05,  2)    # 5%  — partial booking
    t2 = round(close * 1.10,  2)    # 10% — main goal
    t3 = round(close * 1.15,  2)    # 15% — trail and let run

    # Check resistance doesn't block T2
    near_res = entry_data.get("near_resistance")
    if near_res:
        res_pct = (near_res["level"] - close) / close * 100
        if res_pct < 8:
            t1 = round(min(t1, near_res["level"] * 0.995), 2)

    rr = round((t2 - close) / (close - sl), 1)

    if rr < 1.2:
        return None   # poor RR — minimum 1.2

    # ── Total score ───────────────────────────────────────────────────────────
    total = f_score + t_score + e_score

    # Minimum threshold
    if total < 13:
        return None

    conviction, conv_emoji = get_conviction(total)

    # ── Timeframe ─────────────────────────────────────────────────────────────
    if dip_pct <= 8:
        timeframe = "1–2 weeks"
    elif dip_pct <= 15:
        timeframe = "2–4 weeks"
    else:
        timeframe = "4–8 weeks (patient hold)"

    return {
        # Identity
        "symbol":       symbol,
        "sector":       sector,
        "scan_time":    datetime.now(IST).strftime("%Y-%m-%d %H:%M IST"),
        # Conviction
        "conviction":   conviction,
        "conv_emoji":   conv_emoji,
        "total_score":  total,
        "f_score":      f_score,
        "t_score":      t_score,
        "e_score":      e_score,
        # Entry
        "close":        close,
        "buy_low":      buy_low,
        "buy_high":     buy_high,
        "sl":           sl,
        "sl_type":      sl_type,
        "sl_pct":       sl_pct,
        "t1":           t1,
        "t2":           t2,
        "t3":           t3,
        "rr_ratio":     rr,
        "timeframe":    timeframe,
        # Context
        "high52":       round(high52, 2),
        "low52":        round(low52, 2),
        "dip_pct":      dip_pct,
        # Fundamentals
        "roe":          fd.get("roe"),
        "roce":         fd.get("roce"),
        "de":           fd.get("de"),
        "net_margin":   fd.get("net_margin_latest"),
        "eps_growth":   fd.get("eps_growth_yoy"),
        "rev_growth":   fd.get("rev_growth_pct"),
        "fcf":          fd.get("fcf"),
        "promoter":     fd.get("promoter_holding"),
        "pledging":     fd.get("promoter_pledging"),
        "piotroski":    fd.get("piotroski"),
        "pe":           fd.get("pe"),
        "market_cap":   fd.get("market_cap_cr"),
        # Technicals
        "rsi":          entry_data.get("rsi"),
        "macd_cross":   entry_data.get("macd_cross"),
        "stoch_k":      entry_data.get("stoch_k"),
        "near_support": entry_data.get("near_support", {}).get("level") if entry_data.get("near_support") else None,
        "sup_bounces":  entry_data.get("near_support", {}).get("bounces", 0) if entry_data.get("near_support") else 0,
        "near_res":     entry_data.get("near_resistance", {}).get("level") if entry_data.get("near_resistance") else None,
        "vol_drying":   entry_data.get("vol_drying"),
        "buyers_coming":entry_data.get("buyers_coming"),
        "obv_positive": entry_data.get("obv_positive"),
        "atr":          round(atr, 2),
    }


# ════════════════════════════════════════════════════════════════════════════
# 9.  TELEGRAM ALERTS
# ════════════════════════════════════════════════════════════════════════════

def _tg(text: str) -> bool:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
        }, timeout=10)
        r.raise_for_status()
        return True
    except Exception as e:
        log.error(f"Telegram: {e}")
        return False


def _fmt(v, unit="", na="N/A") -> str:
    return f"{v}{unit}" if v is not None else na


def fmt_buy_alert(sig: dict) -> str:
    roe_s  = _fmt(f"{sig['roe']:.1f}"  if sig.get("roe")  else None, "%")
    roce_s = _fmt(f"{sig['roce']:.1f}" if sig.get("roce") else None, "%")
    de_s   = _fmt(f"{sig['de']:.2f}"   if sig.get("de")   else None)
    nm_s   = _fmt(f"{sig['net_margin']:.1f}" if sig.get("net_margin") else None, "%")
    epsg_s = _fmt(f"{sig['eps_growth']:+.1f}" if sig.get("eps_growth") else None, "%")
    revg_s = _fmt(f"{sig['rev_growth']:+.1f}" if sig.get("rev_growth") else None, "%")
    fcf_s  = f"₹{sig['fcf']:.0f} Cr" if sig.get("fcf") else "N/A"
    pro_s  = _fmt(f"{sig['promoter']:.1f}" if sig.get("promoter") else None, "%")
    plg_s  = _fmt(f"{sig['pledging']:.1f}" if sig.get("pledging") is not None else None, "%")
    pio_s  = _fmt(sig.get("piotroski"), "/9")
    pe_s   = _fmt(f"{sig['pe']:.1f}"       if sig.get("pe") else None, "×")
    mc_s   = f"₹{sig['market_cap']:,.0f} Cr" if sig.get("market_cap") else "N/A"

    # Support / Resistance lines
    sup_line = ""
    if sig["near_support"]:
        sup_line = (f"\n   Support: ₹{sig['near_support']} "
                    f"({sig['sup_bounces']}× tested) ✅")
    res_line = ""
    if sig["near_res"]:
        res_pct = round((sig["near_res"] - sig["close"]) / sig["close"] * 100, 1)
        res_line = f"\n   Resistance: ₹{sig['near_res']} ({res_pct:+.1f}% away)"

    # Volume lines
    vol_line = ""
    if sig["vol_drying"]:   vol_line += "\n   📉 Selling volume drying ✅"
    if sig["buyers_coming"]: vol_line += "\n   📈 Buying volume rising ✅"
    obv_line = "\n   OBV: Smart money accumulating ✅" if sig["obv_positive"] else ""

    return (
        f"{sig['conv_emoji']} <b>{sig['conviction']} — {sig['symbol']}</b>\n"
        f"<i>{sig['sector']}  ·  Hold: {sig['timeframe']}</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Buy Zone:</b>  ₹{sig['buy_low']} – ₹{sig['buy_high']}\n"
        f"🛑 <b>Stop Loss:</b> ₹{sig['sl']}  <i>(−{sig['sl_pct']}%  ·  {sig['sl_type']})</i>\n"
        f"🎯 <b>T1  (+5%):</b>  ₹{sig['t1']}  — Book 30–40%\n"
        f"🎯 <b>T2 (+10%):</b>  ₹{sig['t2']}  — <b>Your Main Target</b>\n"
        f"🎯 <b>T3 (+15%):</b>  ₹{sig['t3']}  — Trail SL if momentum continues\n"
        f"📐 <b>Risk : Reward = 1 : {sig['rr_ratio']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏢 <b>Fundamentals</b>  (Score {sig['f_score']}/12)\n"
        f"   ROE: {roe_s}  ·  ROCE: {roce_s}  ·  Net Margin: {nm_s}\n"
        f"   D/E: {de_s}  ·  P/E: {pe_s}  ·  Market Cap: {mc_s}\n"
        f"   EPS Growth: {epsg_s}  ·  Rev Growth: {revg_s}\n"
        f"   FCF: {fcf_s}  ·  Promoter: {pro_s}  ·  Pledging: {plg_s}\n"
        f"   Piotroski: {pio_s}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📈 <b>Technicals</b>  (Trend {sig['t_score']}/8  ·  Entry {sig['e_score']}/10)\n"
        f"   RSI: {sig['rsi']:.0f}  ·  MACD: {'✅ Bullish cross' if sig['macd_cross'] else '✅ Positive'}"
        f"  ·  Stoch: {sig['stoch_k']:.0f if sig['stoch_k'] else 'N/A'}\n"
        f"   52W High: ₹{sig['high52']}  ·  Dip from High: {sig['dip_pct']}%"
        f"{sup_line}{res_line}{vol_line}{obv_line}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏆 <b>Total Score: {sig['total_score']}/30</b>\n"
        f"⚠️ <i>Always honor SL. Strong companies recover — but protect capital first.</i>\n"
        f"🕐 {sig['scan_time']}"
    )


def fmt_summary(signals: list, label: str) -> str:
    now = datetime.now(IST).strftime("%d %b %Y  %I:%M %p IST")
    if not signals:
        return (
            f"📡 <b>Pro Scan — {label}</b>  |  {now}\n\n"
            f"No qualifying signals today.\n"
            f"Markets may be extended or choppy.\n"
            f"<i>No trade is also a good trade. Patience.</i>"
        )
    lines = [
        f"📡 <b>Pro Scan — {label}</b>  |  {now}\n",
        f"✅ <b>{len(signals)} high-quality signal(s):</b>\n",
    ]
    for s in signals:
        lines.append(
            f"{s['conv_emoji']} <b>{s['symbol']}</b> ({s['sector'][:10]}) "
            f"| Buy ₹{s['buy_low']} | SL ₹{s['sl']} | T2 ₹{s['t2']} "
            f"| Score <b>{s['total_score']}/30</b>"
        )
    lines.append("\n<i>Full details sent in individual alerts above.</i>")
    return "\n".join(lines)


def fmt_sl_hit(symbol, sl, cmp):
    return (
        f"🛑 <b>SL HIT — {symbol}</b>\n"
        f"SL ₹{sl} triggered  |  CMP ₹{cmp}\n"
        f"Loss: {round((sl-cmp)/sl*100,2)}%\n\n"
        f"<b>Exit immediately.</b>\n"
        f"<i>This is a strong company. It may recover.\n"
        f"But SL protects your capital for the next trade.\n"
        f"Capital first. Always.</i>"
    )


def fmt_target_hit(symbol, tnum, tprice, cmp, pct, is_t2=False):
    msg = "🎉 10% GOAL ACHIEVED! Book profits or trail SL to T1 level." if is_t2 else \
          f"Book 30–40% of position. Move SL to entry price (breakeven)."
    return (
        f"🎯 <b>TARGET {tnum} ({pct}%) HIT — {symbol}</b>\n"
        f"Target ₹{tprice} reached!  CMP ₹{cmp}\n"
        f"Gain: +{round((cmp-tprice)/tprice*100,2)}%\n\n"
        f"{msg}"
    )


# ════════════════════════════════════════════════════════════════════════════
# 10. GOOGLE SHEETS
# ════════════════════════════════════════════════════════════════════════════

SHEET_HEADERS = [
    "Scan Time","Symbol","Sector","Conviction","Score /30",
    "Fund /12","Trend /8","Entry /10","Hold Timeframe",
    "Buy Price","SL","T1 5%","T2 10%","T3 15%","RR",
    "ROE %","ROCE %","D/E","Net Margin %","EPS Growth %",
    "Rev Growth %","FCF Cr","Promoter %","Pledging %","Piotroski",
    "RSI","Dip from 52W High %","Near Support","Near Resistance",
    "Status","Exit Price","P&L %","Notes",
]

def sheets_client():
    if not SHEETS_OK: return None
    scope = ["https://spreadsheets.google.com/feeds",
             "https://www.googleapis.com/auth/drive"]
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(SHEETS_CRED_FILE, scope)
        return gspread.authorize(creds)
    except Exception as e:
        log.error(f"Sheets auth: {e}"); return None


def log_to_sheets(sig: dict):
    client = sheets_client()
    if not client: return
    try:
        sheet = client.open(SHEETS_DOC_NAME).worksheet("Signals")
        row = [
            sig["scan_time"], sig["symbol"], sig["sector"],
            sig["conviction"], sig["total_score"],
            sig["f_score"], sig["t_score"], sig["e_score"],
            sig["timeframe"],
            sig["buy_high"], sig["sl"],
            sig["t1"], sig["t2"], sig["t3"], sig["rr_ratio"],
            sig.get("roe",""), sig.get("roce",""), sig.get("de",""),
            sig.get("net_margin",""), sig.get("eps_growth",""),
            sig.get("rev_growth",""), sig.get("fcf",""),
            sig.get("promoter",""), sig.get("pledging",""),
            sig.get("piotroski",""),
            sig.get("rsi",""), sig.get("dip_pct",""),
            sig.get("near_support",""), sig.get("near_res",""),
            "OPEN","","","",
        ]
        sheet.append_row(row)
        log.info(f"Sheets: {sig['symbol']} logged")
    except Exception as e:
        log.error(f"Sheets log: {e}")


def update_trade(symbol: str, status: str, exit_price: float = None):
    client = sheets_client()
    if not client: return
    try:
        sh   = client.open(SHEETS_DOC_NAME).worksheet("Signals")
        data = sh.get_all_values()
        hdr  = data[0]
        sym_c  = hdr.index("Symbol") + 1
        stat_c = hdr.index("Status") + 1
        exit_c = hdr.index("Exit Price") + 1
        pnl_c  = hdr.index("P&L %") + 1
        buy_c  = hdr.index("Buy Price") + 1
        for i, row in enumerate(data[1:], 2):
            if row[sym_c-1] == symbol and row[stat_c-1] == "OPEN":
                sh.update_cell(i, stat_c, status)
                if exit_price:
                    sh.update_cell(i, exit_c, exit_price)
                    try:
                        bp = float(row[buy_c-1])
                        sh.update_cell(i, pnl_c, f"{(exit_price-bp)/bp*100:.2f}%")
                    except: pass
                break
    except Exception as e:
        log.error(f"Sheets update: {e}")


# ════════════════════════════════════════════════════════════════════════════
# 11. PRICE WATCHER
# ════════════════════════════════════════════════════════════════════════════

def watch_open_trades():
    fpath = Path("open_trades.csv")
    if not fpath.exists(): return
    trades = pd.read_csv(fpath)
    if trades.empty: return
    closed = []

    for idx, t in trades.iterrows():
        sym = t["symbol"]
        try:
            data = yf.download(nse(sym), period="1d", interval="5m",
                               auto_adjust=True, progress=False)
            if data.empty: continue
            cmp = float(data["Close"].iloc[-1])
        except: continue

        sl, t1, t2, t3 = float(t["sl"]), float(t["t1"]), float(t["t2"]), float(t["t3"])
        t1h = bool(t.get("t1_hit", False))
        t2h = bool(t.get("t2_hit", False))

        log.info(f"Watching {sym}: ₹{cmp:.2f} | SL:{sl} T1:{t1} T2:{t2}")

        if cmp <= sl:
            _tg(fmt_sl_hit(sym, sl, cmp))
            update_trade(sym, "SL HIT", cmp)
            closed.append(idx)
        elif not t1h and cmp >= t1:
            _tg(fmt_target_hit(sym, 1, t1, cmp, 5))
            trades.at[idx, "t1_hit"] = True
            trades.at[idx, "sl"]     = float(t["buy_high"])   # move SL to entry
            update_trade(sym, "T1 HIT (5%)")
        elif t1h and not t2h and cmp >= t2:
            _tg(fmt_target_hit(sym, 2, t2, cmp, 10, is_t2=True))
            trades.at[idx, "t2_hit"] = True
            update_trade(sym, "T2 HIT (10%)")
        elif t2h and cmp >= t3:
            _tg(fmt_target_hit(sym, 3, t3, cmp, 15))
            update_trade(sym, "T3 HIT (15%)", cmp)
            closed.append(idx)

    trades = trades.drop(index=closed).reset_index(drop=True)
    trades.to_csv(fpath, index=False)


def save_open_trades(signals: list):
    fpath = Path("open_trades.csv")
    cols  = ["symbol","buy_high","sl","t1","t2","t3","t1_hit","t2_hit","scan_time"]
    rows  = [{
        "symbol": s["symbol"], "buy_high": s["buy_high"],
        "sl": s["sl"], "t1": s["t1"], "t2": s["t2"], "t3": s["t3"],
        "t1_hit": False, "t2_hit": False, "scan_time": s["scan_time"],
    } for s in signals]
    if not rows: return
    new_df = pd.DataFrame(rows, columns=cols)
    if fpath.exists():
        existing = pd.read_csv(fpath)
        new_df = new_df[~new_df["symbol"].isin(existing["symbol"])]
        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        combined = new_df
    combined.to_csv(fpath, index=False)
    log.info(f"Open trades saved: {len(combined)}")


# ════════════════════════════════════════════════════════════════════════════
# 12. MAIN SCAN PIPELINE
# ════════════════════════════════════════════════════════════════════════════

def run_scan(label="Morning Scan"):
    sep = "═" * 55
    log.info(sep)
    log.info(f"  NSE PRO SCANNER — {label}")
    log.info(f"  {datetime.now(IST).strftime('%d %b %Y  %I:%M %p IST')}")
    log.info(f"  Universe: {len(ALL_STOCKS)} stocks")
    log.info(sep)

    signals = []
    f_fail = t_fail = e_fail = 0

    for i, symbol in enumerate(ALL_STOCKS):
        sector = sector_of(symbol)
        log.info(f"[{i+1:3}/{len(ALL_STOCKS)}] {symbol:15} ({sector[:20]})")

        try:
            # ── Tier 1: Fundamentals (yfinance) ──────────────────────────────
            fd = fetch_fundamentals(symbol)
            passes, reason, f_score, f_card = fundamental_score(symbol, sector, fd)
            if not passes:
                log.info(f"         ✗ Fundamental: {reason}")
                f_fail += 1
                continue
            log.info(f"         ✓ Fundamental score {f_score}/12")

            # ── Tier 2: Trend & EMA Stack ─────────────────────────────────────
            df = fetch_ohlcv(symbol)
            if df is None:
                log.info("         ✗ No price data")
                continue
            df = add_indicators(df)

            t_passes, t_score, t_card = trend_score(df, fd)
            if not t_passes:
                log.info(f"         ✗ Trend: price too far below EMA200")
                t_fail += 1
                continue
            log.info(f"         ✓ Trend score {t_score}/8")

            # ── Tier 3: Entry Timing ──────────────────────────────────────────
            sr = find_sr_zones(df)
            e_passes, e_score, e_card, entry_data = entry_score(df, sr, fd)
            if not e_passes:
                log.info(f"         ✗ Entry: RSI overbought or insufficient setup")
                e_fail += 1
                continue
            log.info(f"         ✓ Entry score {e_score}/10")

            # ── Assemble signal ───────────────────────────────────────────────
            sig = build_signal(symbol, sector, df, fd,
                               f_score, t_score, e_score, entry_data)
            if sig is None:
                log.info(f"         ✗ Signal rejected (RR too poor or SL invalid)")
                continue

            log.info(
                f"         ✅ SIGNAL — {sig['conviction']} | "
                f"Score {sig['total_score']}/30 | "
                f"Dip {sig['dip_pct']}% | RSI {sig['rsi']:.0f}"
            )

            # Send Telegram alert immediately
            _tg(fmt_buy_alert(sig))
            log_to_sheets(sig)
            signals.append(sig)
            time.sleep(0.5)

        except Exception as e:
            log.error(f"         ⚠️ Unexpected error for {symbol}: {e}")
            continue

        time.sleep(0.3)

    # Sort by total score
    signals.sort(key=lambda s: s["total_score"], reverse=True)

    # Summary message
    _tg(fmt_summary(signals, label))

    # Save for price watcher
    save_open_trades(signals)

    log.info(sep)
    log.info(f"  SCAN COMPLETE — {len(signals)} signal(s)")
    log.info(f"  Rejected: Fund {f_fail} · Trend {t_fail} · Entry {e_fail}")
    log.info(sep)
    return signals


# ════════════════════════════════════════════════════════════════════════════
# 13. ENTRY POINT
# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "scan"

    if mode == "scan":
        hour  = datetime.now(IST).hour
        label = "Morning Scan" if hour < 12 else "Pre-Close Scan"
        run_scan(label)

    elif mode == "watch":
        log.info("Price watcher running (every 5 min during market hours)...")
        while True:
            now = datetime.now(IST)
            if now.weekday() < 5 and (9, 15) <= (now.hour, now.minute) <= (15, 30):
                watch_open_trades()
                time.sleep(300)
            else:
                log.info("Outside market hours. Sleeping 10 min...")
                time.sleep(600)

    elif mode == "test":
        sym = sys.argv[2] if len(sys.argv) > 2 else "HDFCBANK"
        log.info(f"TEST MODE — {sym}")
        sector = sector_of(sym)

        fd = fetch_fundamentals(sym)
        passes, reason, f_score, f_card = fundamental_score(sym, sector, fd)
        print(f"\n── Fundamentals ──────────────────────────")
        print(f"Passes: {passes}  Score: {f_score}/12")
        print(f"{'Fail reason: '+reason if not passes else ''}")
        for c in f_card: print(f"  {c}")

        if passes:
            df = fetch_ohlcv(sym)
            if df is not None:
                df = add_indicators(df)
                t_passes, t_score, t_card = trend_score(df, fd)
                print(f"\n── Trend & EMA Stack ─────────────────────")
                print(f"Passes: {t_passes}  Score: {t_score}/8")
                for c in t_card: print(f"  {c}")

                if t_passes:
                    sr = find_sr_zones(df)
                    print(f"\n── Support / Resistance ──────────────────")
                    print(f"Supports:    {[z['level'] for z in sr['supports'][:3]]}")
                    print(f"Resistances: {[z['level'] for z in sr['resistances'][:3]]}")

                    e_passes, e_score, e_card, entry_data = entry_score(df, sr, fd)
                    print(f"\n── Entry Timing ──────────────────────────")
                    print(f"Passes: {e_passes}  Score: {e_score}/10")
                    for c in e_card: print(f"  {c}")

                    if e_passes:
                        sig = build_signal(sym, sector, df, fd, f_score, t_score, e_score, entry_data)
                        if sig:
                            print(f"\n── SIGNAL ────────────────────────────────")
                            print(fmt_buy_alert(sig))
                            _tg(fmt_buy_alert(sig))
                        else:
                            print("\nNo signal — RR ratio too poor or SL invalid.")
                            _tg(f"🔍 Test: {sym}\nPassed all filters but RR ratio too poor right now.\nNot a good entry today.")
                    else:
                        print("\nNo entry signal at this time.")
                        _tg(f"🔍 Test: {sym}\nFund ✅ Trend ✅ Entry ✗\nRSI or MACD not in buy zone right now.")
                else:
                    print("\nTrend filter failed — stock not in buy zone.")
                    _tg(f"🔍 Test: {sym}\nFund ✅ Trend ✗\nPrice too far from EMA50 or below EMA200.")
        else:
            _tg(f"🔍 Test: {sym}\nFundamental filter ✗\nReason: {reason}")

    elif mode == "fundamentals":
        log.info(f"Fundamentals-only scan — {len(ALL_STOCKS)} stocks")
        passed = []
        for sym in ALL_STOCKS:
            sec = sector_of(sym)
            fd  = fetch_fundamentals(sym)
            ok, reason, fs, card = fundamental_score(sym, sec, fd)
            status = f"✅ {fs:2}/12  {', '.join(card[:3])}" if ok else f"✗  {reason}"
            print(f"{sym:15} {status}")
            if ok: passed.append(sym)
        print(f"\n{len(passed)}/{len(ALL_STOCKS)} pass fundamental filter.")

    else:
        print("Usage: python scanner.py [scan | watch | test SYMBOL | fundamentals]")
