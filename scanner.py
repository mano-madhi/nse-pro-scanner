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
        "HAL","BEL","COCHINSHIP","MAZDOCK",
    ],
    "Metals & Mining": [
        "TATASTEEL","JSWSTEEL","HINDALCO","SAIL","VEDL","NMDC","COALINDIA",
        "APLAPOLLO","RATNAMANI","HINDCOPPER","MOIL",
    ],
    "Cement & Building": [
        "ULTRACEMCO","SHREECEM","AMBUJACEM","ACC","JKCEMENT","RAMCOCEM",
        "DALBHARAT","HEIDELBERG",
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
    "Capital Markets & Exchanges": [
        "CDSL","BSE","MOTILALOFS","ANGELONE","IEX","CAMS","KFINTECH",
        "NUVAMA","IIFL","JMFINANCIL",
    ],
    "Textiles & Apparel": [
        "KPRMILL","TRIDENT","WELSPUNIND","VARDHMAN","GOKEX","RAYMOND",
        "ARVIND",
    ],
    "Shipping & Marine Logistics": [
        "AEGISLOG","GESHIP","GATI","SCI","VRLLOG","MAHLOG",
    ],
    "Media & Entertainment": [
        "PVRINOX","SUNTV","ZEEL","NAZARA","SAREGAMA",
    ],
    "Aviation & Travel": [
        "INDIGO","SPICEJET","IRCTC","THOMASCOOK","EASEMYTRIP",
    ],
    "Defence & PSU Diversified": [
        "HAL","BEL","BEML","MAZDOCK","COCHINSHIP","GRSE",
        "IRCON","RVNL","NBCC","NLCINDIA",
    ],
}

ALL_STOCKS = list(dict.fromkeys(
    sym for stocks in UNIVERSE.values() for sym in stocks
))

# ── curated list above now acts as a FALLBACK only ─────────────────────────
CURATED_FALLBACK = ALL_STOCKS

def nse(sym):
    return f"{sym}.NS"

_DYNAMIC_SECTOR_CACHE: dict = {}

def sector_of(sym):
    if sym in _DYNAMIC_SECTOR_CACHE:
        return _DYNAMIC_SECTOR_CACHE[sym]
    return next((s for s, lst in UNIVERSE.items() if sym in lst), "Unknown")


# ════════════════════════════════════════════════════════════════════════════
# 1b.  FULL NSE UNIVERSE — pulled live, curated list is the fallback only
# ════════════════════════════════════════════════════════════════════════════

NSE_EQUITY_LIST_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
MIN_AVG_TURNOVER_CR = 5.0     # min avg daily turnover (₹ crore) to be considered liquid
MIN_PRICE = 20.0              # exclude sub-₹20 stocks (penny/illiquid, unreliable GTT fills)
LIQUIDITY_LOOKBACK_DAYS = 20  # sessions used to compute avg turnover
BATCH_SIZE = 200              # yf.download batch size for the pre-filter pass


def fetch_nse_equity_list() -> list[str] | None:
    """
    Pull NSE's official mainboard equity list (SERIES == EQ only, excludes
    SME/BE/BZ and other restricted series). Returns None on any failure so
    the caller can fall back to CURATED_FALLBACK instead of breaking the scan.

    NSE blocks direct requests that don't carry session cookies established
    by first visiting the site's homepage -- a bare GET to the CSV endpoint
    is bot-blocked and returns a 404 rather than a clean 403. So we prime a
    session against the homepage first, then reuse those cookies for the
    actual CSV fetch. Tries a couple of known candidate URLs since NSE has
    moved this file between domains before. Logs which exact stage fails so
    a repeat failure is diagnosable from the log alone, no back-and-forth.
    """
    headers = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0 Safari/537.36"),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    candidate_urls = [
        "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv",
        "https://archives.nseindia.com/content/equities/EQUITY_L.csv",
    ]

    session = requests.Session()
    session.headers.update(headers)
    try:
        r1 = session.get("https://www.nseindia.com", timeout=15)
        log.info(f"[NSE list] homepage priming GET -> status {r1.status_code}")
        r2 = session.get("https://www.nseindia.com/market-data/securities-available-for-trading",
                          timeout=15)
        log.info(f"[NSE list] securities-page priming GET -> status {r2.status_code}")
    except Exception as e:
        log.warning(f"[NSE list] session priming failed: {e}. Using curated fallback.")
        return None

    for url in candidate_urls:
        try:
            resp = session.get(url, headers={"Accept": "text/csv,*/*"}, timeout=20)
            log.info(f"[NSE list] GET {url} -> status {resp.status_code}, "
                      f"{len(resp.content)} bytes")
            resp.raise_for_status()
            from io import StringIO
            df = pd.read_csv(StringIO(resp.text))
            df.columns = [c.strip() for c in df.columns]
            df = df[df["SERIES"].str.strip() == "EQ"]
            symbols = df["SYMBOL"].str.strip().tolist()
            if len(symbols) < 500:   # sanity check — a truncated/bad response
                log.warning(f"[NSE list] {url} returned too few symbols "
                             f"({len(symbols)}); trying next candidate.")
                continue
            log.info(f"[NSE list] Live NSE list fetched OK from {url}: "
                      f"{len(symbols)} EQ-series symbols.")
            return list(dict.fromkeys(symbols))
        except Exception as e:
            log.warning(f"[NSE list] {url} failed: {e}")
            continue

    log.warning("[NSE list] All candidate URLs failed. Using curated fallback.")
    return None


def filter_liquid_universe(symbols: list[str]) -> list[str]:
    """
    Cheap batched pre-filter: keep only stocks with enough average daily
    turnover and a sane minimum price, BEFORE the expensive per-stock
    fundamental + full technical pipeline runs on them. Keeps ~2000 raw
    NSE symbols down to a tradeable subset that fits the GH Actions time
    budget and avoids scoring stocks you couldn't reliably fill GTTs on.
    """
    liquid = []
    tickers = [nse(s) for s in symbols]
    for i in range(0, len(tickers), BATCH_SIZE):
        chunk = tickers[i:i + BATCH_SIZE]
        try:
            data = yf.download(chunk, period="1mo", interval="1d",
                                group_by="ticker", auto_adjust=True,
                                progress=False, threads=True)
        except Exception as e:
            log.warning(f"Liquidity pre-filter batch {i}-{i+BATCH_SIZE} failed: {e}")
            continue

        for sym, ticker in zip(symbols[i:i + BATCH_SIZE], chunk):
            try:
                sub = data[ticker] if isinstance(data.columns, pd.MultiIndex) else data
                sub = sub.dropna(subset=["Close", "Volume"]).tail(LIQUIDITY_LOOKBACK_DAYS)
                if sub.empty:
                    continue
                avg_turnover_cr = float((sub["Close"] * sub["Volume"]).mean()) / 1e7
                last_price = float(sub["Close"].iloc[-1])
                if avg_turnover_cr >= MIN_AVG_TURNOVER_CR and last_price >= MIN_PRICE:
                    liquid.append(sym)
            except Exception:
                continue
    return liquid


def build_universe() -> list[str]:
    """
    Live NSE list -> liquidity filter -> tradeable universe.
    Falls back to the curated list at any failure point so a bad network
    day never stops the scan from running.
    """
    raw = fetch_nse_equity_list()
    if not raw:
        log.warning("Using CURATED_FALLBACK universe (live NSE fetch unavailable).")
        return CURATED_FALLBACK

    try:
        liquid = filter_liquid_universe(raw)
    except Exception as e:
        log.warning(f"Liquidity filter failed entirely: {e}. Using curated fallback.")
        return CURATED_FALLBACK

    if len(liquid) < 100:   # filter came back suspiciously small -> distrust it
        log.warning(f"Liquidity-filtered universe too small ({len(liquid)}); using curated fallback.")
        return CURATED_FALLBACK

    # Always keep the curated names in too, even if the liquidity pass missed them
    return list(dict.fromkeys(liquid + CURATED_FALLBACK))


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
        data["sector"]          = info.get("sector") or info.get("industry") or "Unknown"

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

        # ── Promoter pledging from NSE India API ─────────────────────────────
        # NSE India provides shareholding pattern data including pledging
        try:
            nse_session = requests.Session()
            nse_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "*/*",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.nseindia.com/",
            }
            # First visit homepage to get cookies
            nse_session.get("https://www.nseindia.com", headers=nse_headers, timeout=10)
            # Now fetch shareholding data
            sh_url = (f"https://www.nseindia.com/api/corporates-shareholding-patterns"
                      f"?index=equities&symbol={symbol}")
            sh_resp = nse_session.get(sh_url, headers=nse_headers, timeout=10)
            if sh_resp.status_code == 200:
                sh_data = sh_resp.json()
                # Extract latest pledging from promoter category
                if sh_data and isinstance(sh_data, list) and len(sh_data) > 0:
                    latest = sh_data[0]
                    promoter_data = latest.get("promoterAndPromoterGroupShareholding", {})
                    pledged = promoter_data.get("pledgedSharesPercentageToTotalCapital", None)
                    if pledged is not None:
                        data["promoter_pledging"] = float(pledged)
                        log.info(f"  Promoter pledging: {data['promoter_pledging']:.1f}% (from NSE)")
        except Exception as e:
            data["promoter_pledging"] = None
            log.warning(f"NSE pledging fetch failed {symbol}: {e}")

        # ── Quarterly profitability check — last 3 quarters ───────────────────
        # This is our automated replacement for manual Screener check
        try:
            qf = tk.quarterly_financials
            if qf is not None and not qf.empty:
                net_income_row = None
                for idx in qf.index:
                    if "net income" in str(idx).lower() or "profit" in str(idx).lower():
                        net_income_row = idx
                        break
                if net_income_row is not None:
                    last_3q = qf.loc[net_income_row].iloc[:3].tolist()
                    profitable_quarters = sum(1 for v in last_3q if v is not None and float(v) > 0)
                    data["profitable_quarters"] = profitable_quarters
                    data["quarterly_profits"]   = [round(float(v)/1e7, 1) if v is not None else None for v in last_3q]
                    log.info(f"  Quarterly: {profitable_quarters}/3 quarters profitable")
                else:
                    data["profitable_quarters"] = None
        except Exception as e:
            data["profitable_quarters"] = None
            log.warning(f"Quarterly check failed {symbol}: {e}")

        log.info(f"  Fundamentals fetched (some fields may be missing)")

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
    STRONG fundamental filter — institutional grade.
    Real max score is 14 (not 12 — the old docstring/labels undercounted).
    Missing data is no longer a free pass: a stock needs real numbers on
    most core metrics to be trusted, not just a couple of favorable ones
    surrounded by "unavailable" — that combination was letting thinly-
    covered small caps through without genuine verification.
    """
    if not fd:
        return False, "No fundamental data available", 0, []

    is_bank = sector in IS_BANK
    score   = 0
    card    = []

    # ── HARD REJECTS ──────────────────────────────────────────────────────────

    # 1. Promoter Pledging > 20%
    pledging = fd.get("promoter_pledging")
    if pledging is not None and pledging > 20:
        return False, f"Promoter pledging {pledging:.1f}% (>20%)", 0, []

    # 2. Revenue declining > 5%
    rev_g = fd.get("rev_growth_pct")
    if rev_g is not None and rev_g < -5:
        return False, f"Revenue declining ({rev_g:.1f}%) — business shrinking", 0, []

    # 3. Loss-making company
    nm = fd.get("net_margin_latest")
    if nm is not None and nm < 0:
        return False, f"Company loss-making (margin {nm:.1f}%)", 0, []

    # 4. Negative ROE
    roe = fd.get("roe")
    if roe is not None and roe < 0:
        return False, f"ROE negative ({roe:.1f}%) — destroying value", 0, []

    # 5. ROE too weak (non-bank)
    if roe is not None and roe < 8 and not is_bank:
        return False, f"ROE {roe:.1f}% too low (<8%)", 0, []

    # 6. Interest coverage critical
    ic = fd.get("interest_coverage")
    if ic is not None and ic < 1.5 and not is_bank:
        return False, f"Interest coverage {ic:.1f}× — cannot pay interest", 0, []

    # 7. Piotroski too weak
    pio = fd.get("piotroski", 5)
    if pio <= 2:
        return False, f"Piotroski {pio}/9 — company fundamentally weakening", 0, []

    # 8. Quarterly profitability — last 3 quarters
    # If data available: at least 2 out of 3 recent quarters must be profitable
    q_profit = fd.get("profitable_quarters")
    if q_profit is not None and q_profit < 2:
        return False, f"Only {q_profit}/3 recent quarters profitable — inconsistent earnings", 0, []

    # 8. Quarterly profitability — last 3 quarters check
    # If we have data and company lost money in 2+ of last 3 quarters → reject
    pq = fd.get("profitable_quarters")
    if pq is not None and pq <= 1:
        return False, f"Only {pq}/3 recent quarters profitable — not consistently earning", 0, []

    # ── DATA COVERAGE REQUIREMENT ───────────────────────────────────────────────
    # A stock can't be trusted as "strong fundamentals" if most of the core
    # metrics are simply missing — that's unverified, not verified-good.
    # Require at least 6 of these 8 core fields to have real data.
    roce  = fd.get("roce")
    de    = fd.get("de")
    eps_g = fd.get("eps_growth_yoy")
    fcf   = fd.get("fcf")
    core_fields = [roe, roce, nm, de, rev_g, eps_g, fcf, pio]
    coverage = sum(1 for v in core_fields if v is not None)
    if coverage < 6:
        return False, f"Only {coverage}/8 core fundamentals available — data too thin to trust", 0, []

    # ── SCORING ───────────────────────────────────────────────────────────────

    # ROE (max 2)
    if roe is not None:
        if roe >= 20:   score += 2; card.append(f"ROE {roe:.1f}% ★★")
        elif roe >= 12: score += 1; card.append(f"ROE {roe:.1f}% ★")
        else:           card.append(f"ROE {roe:.1f}%")
    else:
        card.append("ROE: unavailable")   # NO bonus for missing data

    # ROCE (max 2)
    if roce is not None:
        if roce >= 20:   score += 2; card.append(f"ROCE {roce:.1f}% ★★")
        elif roce >= 12: score += 1; card.append(f"ROCE {roce:.1f}% ★")
    else:
        card.append("ROCE: unavailable")  # NO bonus for missing data

    # Net Margin (max 1)
    if nm is not None:
        if nm >= 15:   score += 1; card.append(f"Net Margin {nm:.1f}% ★")
        elif nm >= 8:  card.append(f"Net Margin {nm:.1f}%")
        elif nm >= 0:  card.append(f"Net Margin {nm:.1f}% (thin)")
    else:
        card.append("Net Margin: unavailable")  # NO bonus

    # Debt/Equity (max 2)
    if de is not None:
        if de <= (3.0 if is_bank else 0.3):
            score += 2; card.append(f"D/E {de:.2f} ★★ (very low debt)")
        elif de <= (10.0 if is_bank else 1.0):
            score += 1; card.append(f"D/E {de:.2f} ★")
        else:
            card.append(f"⚠️ D/E {de:.2f} (high)")
    else:
        card.append("D/E: unavailable")  # NO bonus

    # Revenue Growth (max 2)
    if rev_g is not None:
        if rev_g >= 15:  score += 2; card.append(f"Rev Growth {rev_g:.1f}% ★★")
        elif rev_g >= 5: score += 1; card.append(f"Rev Growth {rev_g:.1f}% ★")
        elif rev_g >= 0: card.append(f"Rev Growth {rev_g:.1f}% (flat)")
    else:
        card.append("Rev Growth: unavailable")  # NO bonus

    # EPS Growth (max 1)
    if eps_g is not None:
        if eps_g >= 15:  score += 1; card.append(f"EPS Growth {eps_g:.1f}% ★")
        elif eps_g >= 0: card.append(f"EPS Growth {eps_g:.1f}%")
        else:            card.append(f"⚠️ EPS falling {eps_g:.1f}%")
    else:
        card.append("EPS Growth: unavailable")  # NO bonus

    # FCF (max 1)
    if fcf is not None:
        if fcf > 0: score += 1; card.append(f"FCF ₹{fcf:.0f}Cr ★")
        else:       card.append(f"⚠️ FCF negative")
    else:
        card.append("FCF: unavailable")  # NO bonus

    # Market cap (max 1)
    mcap = fd.get("market_cap_cr") or 0
    if mcap >= 20000:
        score += 1; card.append(f"Large cap ₹{mcap:,.0f}Cr ★")
    elif mcap >= 5000:
        card.append(f"Mid cap ₹{mcap:,.0f}Cr")
    else:
        card.append(f"Small cap ₹{mcap:,.0f}Cr")

    # Piotroski (max 1)
    if pio >= 7:   score += 1; card.append(f"Piotroski {pio}/9 ★★")
    elif pio >= 5: card.append(f"Piotroski {pio}/9")
    else:          card.append(f"⚠️ Piotroski {pio}/9 (weak)")

    # Quarterly profitability bonus
    if q_profit is not None:
        if q_profit == 3: score += 1; card.append("3/3 quarters profitable ★★")
        elif q_profit == 2: card.append("2/3 quarters profitable ★")
    else:
        card.append("Quarterly: data pending")

    # ── Minimum: 9/14 from REAL data, plus the coverage gate above ─────────────
    if score < 9:
        return False, f"Fundamental score {score}/14 too low — real data insufficient", 0, []

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

            # ── Drop today's still-forming daily candle ─────────────────────────
            # The scanner runs twice a day (9:20 AM, 3:00 PM) while the market is
            # open, so yfinance's most recent daily bar is only partially formed
            # at scan time -- its Close, and every indicator built on it (RSI,
            # MACD, ATR, Bollinger, S/R), keeps changing between runs. Dropping
            # it means every calculation is anchored to the last FULLY COMPLETED
            # session, so a stock scored strong at 9:20 AM shows identical
            # entry/SL/target at 3:00 PM the same day. Levels then update once
            # per day, when a new session actually finalizes -- not per run.
            #
            # Compared as plain .date() objects, not pd.Timestamp, to sidestep
            # tz-aware vs tz-naive comparison errors -- a date has no timezone
            # ambiguity, which is all this check actually needs.
            today_ist_date = datetime.now(IST).date()
            last_bar_ts = df.index[-1]
            last_bar_date = (last_bar_ts.tz_localize(None) if last_bar_ts.tzinfo
                              else last_bar_ts).date()
            if last_bar_date >= today_ist_date:
                df = df.iloc[:-1]
                if df.empty or len(df) < 120:
                    return None

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

def trend_score(df: pd.DataFrame, fd: dict) -> tuple[bool, int, list, float]:
    """
    Evaluates the full EMA stack and long-term trend.
    Returns (passes, score, reasons, ema200_gap).
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
        return False, 0, [], 0.0

    # ── Hard reject: too far below EMA200 ────────────────────────────────────
    ema200_gap = (close - ema200) / ema200 * 100
    if ema200_gap < -5:
        return False, 0, [], ema200_gap

    # 1. Price above EMA200 — long term uptrend  (2 pts)
    if close >= ema200:
        score += 2; card.append("Price > EMA200 ✅ (long term uptrend)")
    elif ema200_gap >= -2:
        score += 1; card.append(f"Price near EMA200 ({ema200_gap:.1f}%) — recovering")
    else:
        score += 1; card.append(f"Price {ema200_gap:.1f}% below EMA200 — deeper dip")

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

    return True, score, card, ema200_gap
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
        "rsi":           rsi,
        "macd_cross":    macd_cross,
        "stoch_k":       stoch_k,
        "near_support":  near_sup,
        "near_resistance": near_res,
        "vol_drying":    vol_drying if volrat else False,
        "buyers_coming": buyers_coming if volrat else False,
        "obv_positive":  (obv > obv_ema) if (obv and obv_ema) else False,
        "atr":           atr,
        "sr_zones":      sr,     # full S/R zones for technical target calculation
    }

    return True, score, card, entry_data


# ════════════════════════════════════════════════════════════════════════════
# 7B.  SENTIMENT CHECK  (Tier 4 — News + FII/DII flows, max 5 points)
#      Runs ONLY on stocks that already passed Tiers 1–3.
#      Not a hard score requirement (max 3 from this section is informational +
#      a small swing in the final score), but a HARD RED FLAG (negative news +
#      FII/DII selling together) downgrades GOOD BUY -> WATCHLIST and is
#      clearly shown in the Telegram alert so you can verify before entry.
# ════════════════════════════════════════════════════════════════════════════

_NEG_KEYWORDS = [
    "fraud", "raid", "scam", "probe", "investigation", "sebi action",
    "default", "downgrade", "resign", "resignation", "fire", "explosion",
    "accident", "ban", "penalty", "fine", "lawsuit", "scandal",
    "insider trading", "auditor resign", "stake sale", "pledge increase",
    "debt restructur", "loss widens", "plant shut", "strike", "layoff",
    "rating cut", "going concern",
]

_POS_KEYWORDS = [
    "order win", "bags order", "wins contract", "expansion", "capacity expansion",
    "upgrade", "record profit", "record revenue", "new plant", "stake buy",
    "buyback", "dividend", "fii buy", "block deal buy",
]


def fetch_news_sentiment(symbol: str, company_hint: str = "") -> dict:
    """
    Free, no-API-key news check via Google News RSS.
    Scans the latest headlines for the stock and flags strong
    negative/positive keywords. Best-effort only — if it fails,
    returns a neutral result (does not block the signal).
    """
    result = {"checked": False, "neg_hits": [], "pos_hits": [], "note": None}
    try:
        query = f"{symbol} share"
        url = (f"https://news.google.com/rss/search?q={requests.utils.quote(query)}"
               f"+stock+NSE&hl=en-IN&gl=IN&ceid=IN:en")
        resp = requests.get(url, headers=SCREENER_HEADERS, timeout=8)
        if resp.status_code != 200:
            return result

        soup = BeautifulSoup(resp.text, "xml")
        items = soup.find_all("item")[:8]   # latest ~8 headlines
        headlines = [it.title.text for it in items if it.title]

        for h in headlines:
            hl = h.lower()
            for kw in _NEG_KEYWORDS:
                if kw in hl:
                    result["neg_hits"].append((kw, h))
                    break
            for kw in _POS_KEYWORDS:
                if kw in hl:
                    result["pos_hits"].append((kw, h))
                    break

        result["checked"] = True
        if headlines:
            result["note"] = headlines[0][:90]   # top headline as context

    except Exception as e:
        log.warning(f"News sentiment fetch failed for {symbol}: {e}")

    return result


def fetch_fii_dii_activity(symbol: str) -> dict:
    """
    Checks NSE bulk-deals data for recent FII/DII/large institutional
    buy or sell activity in this stock (last available trading session).
    Best-effort — returns neutral if NSE blocks/limits the request.
    """
    result = {"checked": False, "net_buy": None, "note": None}
    try:
        nse_session = requests.Session()
        nse_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.nseindia.com/",
        }
        nse_session.get("https://www.nseindia.com", headers=nse_headers, timeout=10)
        url = "https://www.nseindia.com/api/historical/bulk-deals"
        resp = nse_session.get(url, headers=nse_headers, timeout=10)
        if resp.status_code != 200:
            return result

        data = resp.json()
        rows = data.get("data", []) if isinstance(data, dict) else []
        buy_qty = sell_qty = 0
        hits = 0
        for row in rows:
            sym = (row.get("BD_SYMBOL") or row.get("symbol") or "").upper()
            if sym != symbol.upper():
                continue
            hits += 1
            qty = float(row.get("BD_QTY_TRD") or row.get("quantity") or 0)
            txn = (row.get("BD_BUY_SELL") or row.get("buySell") or "").upper()
            if txn.startswith("B"):
                buy_qty += qty
            elif txn.startswith("S"):
                sell_qty += qty

        if hits:
            net = buy_qty - sell_qty
            result["checked"] = True
            result["net_buy"] = net
            if net > 0:
                result["note"] = f"Bulk deals: net BUY ({hits} entries)"
            elif net < 0:
                result["note"] = f"Bulk deals: net SELL ({hits} entries)"
            else:
                result["note"] = f"Bulk deals: balanced ({hits} entries)"

    except Exception as e:
        log.warning(f"FII/DII bulk-deal fetch failed for {symbol}: {e}")

    return result


def sentiment_score(symbol: str) -> dict:
    """
    Tier 4 — combines news sentiment + FII/DII bulk-deal activity.
    Returns dict with:
      score        : -2 to +3 (added to total, capped so it can't push
                      a stock from WATCHLIST to BUY on its own)
      flags        : list of human-readable warning/positive strings
      hard_red_flag: True if negative news + FII/DII selling both present
      news_note    : top headline (for context, shown in alert)
      fii_dii_note : bulk deal summary (shown in alert)
    """
    news = fetch_news_sentiment(symbol)
    fii  = fetch_fii_dii_activity(symbol)

    score = 0
    flags = []
    hard_red_flag = False

    if news["checked"]:
        if news["neg_hits"]:
            score -= 2
            for kw, h in news["neg_hits"][:2]:
                flags.append(f"⚠️ News flag ('{kw}'): {h[:70]}")
        if news["pos_hits"] and not news["neg_hits"]:
            score += 1
            kw, h = news["pos_hits"][0]
            flags.append(f"✅ Positive news: {h[:70]}")
    else:
        flags.append("ℹ️ News check unavailable (skipped)")

    if fii["checked"]:
        if fii["net_buy"] is not None:
            if fii["net_buy"] > 0:
                score += 1
                flags.append("✅ Recent bulk deals: net institutional BUY")
            elif fii["net_buy"] < 0:
                score -= 1
                flags.append("⚠️ Recent bulk deals: net institutional SELL")
    else:
        flags.append("ℹ️ FII/DII bulk-deal check unavailable (skipped)")

    # Hard red flag: bad news AND institutional selling together
    if news["checked"] and news["neg_hits"] and fii["checked"] and (fii["net_buy"] or 0) < 0:
        hard_red_flag = True
        flags.insert(0, "🛑 HARD FLAG: Negative news + institutional selling — verify before entry!")

    # Cap score contribution to -2..+2 so this tier alone can't flip conviction tiers
    score = max(-2, min(2, score))

    return {
        "score": score,
        "flags": flags,
        "hard_red_flag": hard_red_flag,
        "news_note": news.get("note"),
        "fii_dii_note": fii.get("note"),
    }


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
                 entry_data: dict, ema200_gap: float = 0.0,
                 sentiment_data: dict | None = None) -> dict | None:

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
        gap_to_support = (close - near_sup["level"]) / close * 100
        if gap_to_support <= 5:
            sl = round(near_sup["level"] * 0.988, 2)
            sl_type = f"below support ₹{near_sup['level']} ({near_sup.get('bounces',1)}× bounce)"
        else:
            sl = round(close - 1.2 * atr, 2)
            sl_type = "ATR-based (1.2×ATR)"
    else:
        sl = round(close - 1.2 * atr, 2)
        sl_type = "ATR-based (1.2×ATR)"

    sl_pct = round((close - sl) / close * 100, 1)

    if sl_pct < 1.0 or sl_pct > 8.0:
        return None

    # ── TECHNICAL TARGET CALCULATION ─────────────────────────────────────────
    # Purely structural: resistance zones above entry, or a measured-move
    # multiple of THIS stock's own SL distance when no resistance exists.
    # No fixed percentage floors — a stock with resistance close by should
    # get a close T1, not one artificially pushed out to hit a minimum %.

    sl_dist = close - sl          # actual risk per share (measured move unit)
    buy_ref = buy_high            # reference from top of buy zone

    # Measured move targets using SL distance as unit — used only when there's
    # no resistance zone to anchor to, never as a floor on top of one.
    mm_t1 = buy_ref + 2.0 * sl_dist    # 2:1 reward
    mm_t2 = buy_ref + 4.0 * sl_dist    # 4:1 reward
    mm_t3 = buy_ref + 6.0 * sl_dist    # 6:1 reward

    # Get all resistance zones above entry from S/R analysis
    sr_zones = entry_data.get("sr_zones", {})
    resistances = sr_zones.get("resistances", []) if sr_zones else []
    res_above = sorted(
        [r["level"] for r in resistances if r["level"] > buy_ref * 1.02],
    )

    # T1 — first resistance above entry OR measured move, WHICHEVER IS CLOSER
    # (book profits at the first realistic opportunity, don't overreach)
    if res_above:
        t1 = min(res_above[0] * 0.998, mm_t1)
    else:
        t1 = mm_t1

    # T2 — second resistance OR measured move, whichever is FARTHER (extension target)
    if len(res_above) >= 2:
        t2 = max(res_above[1] * 0.998, mm_t2)
    else:
        t2 = mm_t2

    # T3 — third resistance if it exists, else extended measured move (let it run)
    if len(res_above) >= 3:
        t3 = max(res_above[2] * 0.998, mm_t3)
    else:
        t3 = mm_t3

    # Safety: strict ordering only — T1 < T2 < T3, all above buy_high.
    # Bumps use THIS stock's own SL distance (its real volatility unit) to
    # break a tie, never a blind percentage.
    t1 = round(max(t1, buy_ref + 0.5 * sl_dist), 2)
    t2 = round(max(t2, t1 + 0.5 * sl_dist), 2)
    t3 = round(max(t3, t2 + 0.5 * sl_dist), 2)

    # ── Risk : Reward (based on T2) ───────────────────────────────────────────
    # No minimum enforced here anymore — target and SL both come from real
    # chart structure (resistance zones, swing points, ATR), so whatever RR
    # that structure produces is trusted as-is rather than discarding a
    # structurally-valid setup just because the ratio number looks low.
    # rr is still calculated and shown on every signal for your own judgment.
    rr = round((t2 - buy_ref) / sl_dist, 1)

    # ── Total score ───────────────────────────────────────────────────────────
    total = f_score + t_score + e_score

    # Minimum threshold
    if total < 13:
        return None

    # ── Tier 4: Sentiment / News / FII-DII adjustment ─────────────────────────
    sentiment_data = sentiment_data or {}
    sent_adj  = sentiment_data.get("score", 0)
    hard_flag = sentiment_data.get("hard_red_flag", False)

    total_adjusted = max(0, min(30, total + sent_adj))
    conviction, conv_emoji = get_conviction(total_adjusted)

    # Hard red flag (bad news + institutional selling) — force downgrade
    # from BUY tiers to WATCHLIST regardless of technical score, so it
    # won't go to Telegram without your manual review.
    if hard_flag and conviction != "WATCHLIST ★":
        conviction, conv_emoji = "WATCHLIST ★", "🟡"
        total_adjusted = min(total_adjusted, 18)

    # ── Timeframe / Horizon — ATR-based days-to-target estimate ───────────────
    # Projects how many trading days T1 should take at this stock's own normal
    # daily range (ATR), then classifies for capital-recycling purposes:
    # Momentum Pick = fast in/out, Short Term = medium hold, Long Term =
    # slow mover but only when fundamentals actually justify holding that long.
    daily_progress = max(atr * 0.5, 0.01)   # assume ~50% of ATR captured per day, directionally
    days_to_t1 = max(1, round((t1 - buy_ref) / daily_progress))
    days_to_t2 = max(days_to_t1, round((t2 - buy_ref) / daily_progress))

    if days_to_t1 <= 7:
        horizon = "Momentum Pick"
    elif days_to_t1 <= 20:
        horizon = "Short Term"
    else:
        horizon = "Long Term" if f_score >= 8 else "Short Term"

    timeframe = f"~{days_to_t1}-{days_to_t2} trading days"

    return {
        # Identity
        "symbol":       symbol,
        "sector":       sector,
        "scan_time":    datetime.now(IST).strftime("%Y-%m-%d %H:%M IST"),
        # Conviction
        "conviction":   conviction,
        "conv_emoji":   conv_emoji,
        "total_score":  total_adjusted,
        "f_score":      f_score,
        "t_score":      t_score,
        "e_score":      e_score,
        # Entry
        "close":        close,
        "buy_low":      buy_low,
        "buy_high":     buy_high,
        "buy_ref":      buy_ref,    # reference price for target % calculations
        "sl":           sl,
        "sl_type":      sl_type,
        "sl_pct":       sl_pct,
        "t1":           t1,
        "t2":           t2,
        "t3":           t3,
        "rr_ratio":     rr,
        "timeframe":    timeframe,
        "horizon":      horizon,
        "days_to_t1":   days_to_t1,
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
        "profitable_quarters": fd.get("profitable_quarters"),
        "quarterly_profits":   fd.get("quarterly_profits"),
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
        "profitable_q": fd.get("profitable_quarters"),
        "quarterly_profits": fd.get("quarterly_profits"),
        "pledging_nse": fd.get("promoter_pledging"),
        # EMA200 status
        "ema200_gap":   round(ema200_gap, 1),
        "above_ema200": ema200_gap >= 0,
        # Sentiment / News / FII-DII (Tier 4) — filled in by run_scan
        "sentiment_flags": sentiment_data.get("flags", []),
        "sentiment_score": sent_adj,
        "fii_dii_note":    sentiment_data.get("fii_dii_note"),
        "news_note":       sentiment_data.get("news_note"),
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
    """Clean, well-aligned Telegram BUY signal alert."""

    # ── Data preparation ──────────────────────────────────────────────────────
    roe_s  = f"{sig['roe']:.1f}%"    if sig.get("roe")        else "—"
    roce_s = f"{sig['roce']:.1f}%"   if sig.get("roce")       else "—"
    de_s   = f"{sig['de']:.2f}"      if sig.get("de")         else "—"
    nm_s   = f"{sig['net_margin']:.1f}%" if sig.get("net_margin") else "—"
    revg_s = f"{sig['rev_growth']:+.1f}%" if sig.get("rev_growth") else "—"
    epsg_s = f"{sig['eps_growth']:+.1f}%" if sig.get("eps_growth") else "—"
    pe_s   = f"{sig['pe']:.1f}×"     if sig.get("pe")         else "—"
    pio_s  = f"{sig['piotroski']}/9" if sig.get("piotroski")  else "—"
    rsi_s  = f"{sig['rsi']:.0f}"     if sig.get("rsi")        else "—"
    stoch_s= f"{sig['stoch_k']:.0f}" if sig.get("stoch_k")    else "—"
    macd_s = "✅ Crossover" if sig.get("macd_cross") else "✅ Positive"

    # Volume signals
    vol_signals = []
    if sig.get("vol_drying"):    vol_signals.append("Selling drying ✅")
    if sig.get("buyers_coming"): vol_signals.append("Buyers rising ✅")
    if sig.get("obv_positive"):  vol_signals.append("Smart money in ✅")
    vol_s = "  ·  ".join(vol_signals) if vol_signals else "Neutral"

    # Support / Resistance
    sup_s = f"₹{sig['near_support']} ({sig['sup_bounces']}× bounce) ✅" if sig.get("near_support") else "No nearby zone"
    res_s = f"₹{sig['near_res']} ({round((sig['near_res']-sig['close'])/sig['close']*100,1):+.1f}%)" if sig.get("near_res") else "Clear path"

    # EMA200 status — accurate gap-based label
    if sig.get("above_ema200"):
        ema_status = "✅ Above EMA200"
    elif sig.get("ema200_gap", 0) >= -2:
        ema_status = f"⚠️ Near EMA200 ({sig['ema200_gap']}%)"
    else:
        ema_status = f"⚠️ Below EMA200 ({sig['ema200_gap']}%)"

    # Sentiment / Tier 4 lines
    flags = sig.get("sentiment_flags") or []
    if flags:
        sent_lines = "\n".join(f"   {f}" for f in flags) + "\n"
    else:
        sent_lines = "   No flags — neutral\n"

    # Profit/loss amounts for ₹1L investment
    buy_ref   = sig.get("buy_ref", sig["buy_high"])
    invest    = 100000
    qty       = max(1, int(invest / buy_ref))
    sl_loss   = round(qty * (buy_ref - sig["sl"]), 0)
    t1_profit = round(qty * (sig["t1"] - buy_ref), 0)
    t2_profit = round(qty * (sig["t2"] - buy_ref), 0)

    # T1/T2/T3 percentage gains from buy reference
    t1_pct = round((sig["t1"] - buy_ref) / buy_ref * 100, 1)
    t2_pct = round((sig["t2"] - buy_ref) / buy_ref * 100, 1)
    t3_pct = round((sig["t3"] - buy_ref) / buy_ref * 100, 1)

    return (
        f"{sig['conv_emoji']} <b>{sig['conviction']}</b>  ·  🏷 {sig['horizon']}\n"
        f"<b>📌 {sig['symbol']}</b>  |  {sig['sector']}\n"
        f"⏱ Hold: {sig['timeframe']}  ·  Score: {sig['total_score']}/30\n"
        f"\n"
        f"{'─'*28}\n"
        f"💰 <b>BUY ZONE</b>\n"
        f"   Entry  :  ₹{sig['buy_low']} – ₹{sig['buy_high']}\n"
        f"   SL     :  ₹{sig['sl']}  (−{sig['sl_pct']}%)\n"
        f"\n"
        f"🎯 <b>TARGETS  (Technical)</b>\n"
        f"   T1 +{t1_pct}%  :  ₹{sig['t1']}  → Book 30-40% here\n"
        f"   T2 +{t2_pct}%  :  ₹{sig['t2']}  → <b>Main target</b>\n"
        f"   T3 +{t3_pct}%  :  ₹{sig['t3']}  → Trail SL\n"
        f"   RR Ratio:  1 : {sig['rr_ratio']}\n"
        f"\n"
        f"💵 <b>On ₹1L investment (~{qty} shares)</b>\n"
        f"   If SL hits  : −₹{sl_loss:,.0f}\n"
        f"   T1 profit   : +₹{t1_profit:,.0f}\n"
        f"   T2 profit   : +₹{t2_profit:,.0f}\n"
        f"\n"
        f"{'─'*28}\n"
        f"🏢 <b>FUNDAMENTALS</b>  ({sig['f_score']}/14)\n"
        f"   ROE        :  {roe_s}\n"
        f"   ROCE       :  {roce_s}\n"
        f"   D/E        :  {de_s}\n"
        f"   Net Margin :  {nm_s}\n"
        f"   Rev Growth :  {revg_s}\n"
        f"   EPS Growth :  {epsg_s}\n"
        f"   P/E        :  {pe_s}\n"
        f"   Piotroski  :  {pio_s}\n"
        f"\n"
        f"{'─'*28}\n"
        f"📈 <b>TECHNICALS</b>  (T:{sig['t_score']}/8  E:{sig['e_score']}/10)\n"
        f"   RSI        :  {rsi_s}  (ideal: 35–55)\n"
        f"   MACD       :  {macd_s}\n"
        f"   Stoch RSI  :  {stoch_s}\n"
        f"   Dip        :  {sig['dip_pct']}% from 52W High ₹{sig['high52']}\n"
        f"   EMA Trend  :  {ema_status}\n"
        f"   Support    :  {sup_s}\n"
        f"   Resistance :  {res_s}\n"
        f"   Volume     :  {vol_s}\n"
        f"\n"
        f"{'─'*28}\n"
        f"📰 <b>SENTIMENT</b>  (Tier 4: {sig.get('sentiment_score',0):+d}/2)\n"
        f"{sent_lines}"
        f"\n"
        f"🕐 {sig['scan_time']}\n"
        f"⚠️ <i>Paper trade first. Always set SL.</i>"
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
        f"✅ <b>{len(signals)} signal(s) — Score 22+ only:</b>\n",
    ]
    for s in signals[:15]:
        lines.append(
            f"{s['conv_emoji']} <b>{s['symbol']}</b> ({s['sector'][:10]}) "
            f"| Buy ₹{s['buy_low']} | SL ₹{s['sl']} "
            f"| T1 ₹{s['t1']} | T2 ₹{s['t2']} "
            f"| Score <b>{s['total_score']}/30</b>"
        )
    if len(signals) > 15:
        lines.append(f"\n<i>...and {len(signals)-15} more. Check Google Sheets for full list.</i>")
    lines.append("\n<i>Detailed alert sent for each signal above.</i>")
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


def fmt_entry_triggered(symbol, cmp, sl, t1, t2, t3):
    """
    Sent when a stock we already flagged earlier has now crossed its
    original buy zone -- CMP is fresh, but SL/T1/T2/T3 are the exact same
    numbers given the first time this stock was flagged, never recomputed.
    """
    return (
        f"🔔 <b>ENTRY TRIGGERED — {symbol}</b>\n"
        f"Already flagged earlier — buy zone now crossed.\n"
        f"Buy at CMP ₹{cmp:.2f}\n\n"
        f"SL     :  ₹{sl}  (unchanged from original signal)\n"
        f"T1     :  ₹{t1}\n"
        f"T2     :  ₹{t2}\n"
        f"T3     :  ₹{t3}\n\n"
        f"<i>Targets and SL are the same as originally given — only the "
        f"entry price has moved since then.</i>"
    )


# ════════════════════════════════════════════════════════════════════════════
# 10. GOOGLE SHEETS
# ════════════════════════════════════════════════════════════════════════════

SHEET_HEADERS = [
    "Scan Time","Symbol","Sector","Conviction","Score /30",
    "Fund /14","Trend /8","Entry /10","Hold Timeframe",
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
    """
    Checks every OPEN signal in the Google Sheet against current price and
    reports SL/target hits to Telegram. Reads/writes the Sheet directly --
    NOT a local file -- because GitHub Actions gives every run a fresh repo
    checkout, so anything written to disk in one run is gone by the next.
    A local open_trades.csv can never survive between separate runs; the
    Sheet is the only thing here that actually persists.
    """
    client = sheets_client()
    if not client:
        log.warning("Sheets not configured — cannot watch open trades.")
        return
    try:
        sh = client.open(SHEETS_DOC_NAME).worksheet("Signals")
        data = sh.get_all_values()
    except Exception as e:
        log.error(f"Sheets read failed: {e}")
        return
    if len(data) < 2:
        return

    hdr = data[0]
    def col(name):
        return hdr.index(name)

    sym_c, stat_c   = col("Symbol"),   col("Status")
    buy_c, sl_c     = col("Buy Price"), col("SL")
    t1_c, t2_c, t3_c = col("T1 5%"), col("T2 10%"), col("T3 15%")
    exit_c, pnl_c   = col("Exit Price"), col("P&L %")
    notes_c         = col("Notes")

    open_rows = [(i, row) for i, row in enumerate(data[1:], start=2)
                 if row[stat_c].strip() == "OPEN"]
    if not open_rows:
        log.info("No open trades to watch.")
        return
    log.info(f"Watching {len(open_rows)} open trade(s)...")

    for row_num, row in open_rows:
        sym = row[sym_c]
        try:
            buy_high, sl = float(row[buy_c]), float(row[sl_c])
            t1, t2, t3   = float(row[t1_c]), float(row[t2_c]), float(row[t3_c])
        except (ValueError, IndexError):
            continue

        try:
            d = yf.download(nse(sym), period="1d", interval="5m",
                             auto_adjust=True, progress=False)
            if d.empty:
                continue
            cmp = float(d["Close"].iloc[-1])
        except Exception:
            continue

        t1_done = "T1" in row[notes_c]
        t2_done = "T2" in row[notes_c]
        log.info(f"  {sym}: ₹{cmp:.2f}  (SL {sl}  T1 {t1}  T2 {t2}  T3 {t3})")

        if cmp <= sl:
            _tg(fmt_sl_hit(sym, sl, cmp))
            sh.update_cell(row_num, stat_c + 1, "SL HIT")
            sh.update_cell(row_num, exit_c + 1, cmp)
            sh.update_cell(row_num, pnl_c + 1, f"{(cmp-buy_high)/buy_high*100:.2f}%")

        elif not t1_done and cmp >= t1:
            _tg(fmt_target_hit(sym, 1, t1, cmp, 5))
            sh.update_cell(row_num, notes_c + 1, (row[notes_c] + " T1").strip())
            sh.update_cell(row_num, sl_c + 1, buy_high)   # move SL to breakeven
            sh.update_cell(row_num, stat_c + 1, "T1 HIT (5%)")

        elif t1_done and not t2_done and cmp >= t2:
            _tg(fmt_target_hit(sym, 2, t2, cmp, 10, is_t2=True))
            sh.update_cell(row_num, notes_c + 1, (row[notes_c] + " T2").strip())
            sh.update_cell(row_num, stat_c + 1, "T2 HIT (10%)")

        elif t2_done and cmp >= t3:
            _tg(fmt_target_hit(sym, 3, t3, cmp, 15))
            sh.update_cell(row_num, stat_c + 1, "T3 HIT (15%)")
            sh.update_cell(row_num, exit_c + 1, cmp)
            sh.update_cell(row_num, pnl_c + 1, f"{(cmp-buy_high)/buy_high*100:.2f}%")


# ════════════════════════════════════════════════════════════════════════════
# 12. MAIN SCAN PIPELINE
# ════════════════════════════════════════════════════════════════════════════

def get_open_positions() -> dict:
    """
    Reads every OPEN row from the Signals sheet ONCE at the start of a scan.
    Used to skip re-scoring/re-alerting a stock that's already been flagged
    and hasn't resolved yet — the FundsIndia-style behavior: a stock gets
    its entry/target/SL levels ONCE, and later scans either stay silent
    (price still hasn't reached the original buy zone) or announce "buy at
    CMP" using the SAME original target/SL (price has now crossed into or
    past the original zone) — never a freshly recomputed target/SL for a
    stock that's already been given one.
    """
    client = sheets_client()
    if not client:
        return {}
    try:
        sh = client.open(SHEETS_DOC_NAME).worksheet("Signals")
        data = sh.get_all_values()
    except Exception as e:
        log.warning(f"Could not read open positions: {e}")
        return {}
    if len(data) < 2:
        return {}

    hdr = data[0]
    def col(name):
        return hdr.index(name)

    sym_c, stat_c = col("Symbol"), col("Status")
    buy_c, sl_c   = col("Buy Price"), col("SL")
    t1_c, t2_c, t3_c = col("T1 5%"), col("T2 10%"), col("T3 15%")
    notes_c = col("Notes")

    # Still "active" (not eligible for a fresh new signal) covers OPEN plus
    # partial-target states -- only SL HIT and T3 HIT are truly terminal.
    # A position that's already hit T1 (SL moved to breakeven) is still very
    # much running toward T2/T3 and must not be treated as free to re-flag.
    STILL_ACTIVE = {"OPEN", "T1 HIT (5%)", "T2 HIT (10%)"}

    open_pos = {}
    for i, row in enumerate(data[1:], start=2):
        if row[stat_c].strip() not in STILL_ACTIVE:
            continue
        try:
            open_pos[row[sym_c]] = {
                "row_num": i,
                "buy_high": float(row[buy_c]),
                "sl": float(row[sl_c]),
                "t1": float(row[t1_c]),
                "t2": float(row[t2_c]),
                "t3": float(row[t3_c]),
                "entry_alerted": "ENTRY" in row[notes_c],
                "notes": row[notes_c],
            }
        except (ValueError, IndexError):
            continue
    return open_pos


def check_and_alert_open_position(symbol: str, pos: dict):
    """
    For a stock that already has an OPEN row: fetch CMP, then either stay
    silent (still below original buy zone) or send a one-time "entry
    triggered, buy at CMP" alert reusing the ORIGINAL stored target/SL —
    never recomputed. Marks the row so this only fires once per position.
    """
    try:
        d = yf.download(nse(symbol), period="1d", interval="5m",
                         auto_adjust=True, progress=False)
        if d.empty:
            return
        cmp = float(d["Close"].iloc[-1])
    except Exception:
        return

    if cmp < pos["buy_high"]:
        log.info(f"         ↻ Already flagged, still below buy zone (CMP ₹{cmp:.2f} < ₹{pos['buy_high']:.2f}) — waiting")
        return

    if pos["entry_alerted"]:
        log.info(f"         ↻ Already flagged and entry already alerted — watcher is tracking it")
        return

    log.info(f"         🔔 Already-flagged stock crossed into buy zone — sending entry-at-CMP alert")
    _tg(fmt_entry_triggered(symbol, cmp, pos["sl"], pos["t1"], pos["t2"], pos["t3"]))
    try:
        client = sheets_client()
        sh = client.open(SHEETS_DOC_NAME).worksheet("Signals")
        notes_c = sh.row_values(1).index("Notes") + 1   # 1-based for update_cell
        new_notes = (pos["notes"] + " ENTRY").strip()
        sh.update_cell(pos["row_num"], notes_c, new_notes)
    except Exception as e:
        log.warning(f"Could not mark entry-alerted: {e}")


def run_scan(label="Morning Scan"):
    sep = "═" * 55
    log.info(sep)
    log.info(f"  NSE PRO SCANNER — {label}")
    log.info(f"  {datetime.now(IST).strftime('%d %b %Y  %I:%M %p IST')}")

    universe = build_universe()
    log.info(f"  Universe: {len(universe)} stocks")

    open_positions = get_open_positions()
    log.info(f"  Already-open positions (won't get new levels): {len(open_positions)}")
    log.info(sep)

    signals = []
    f_fail = t_fail = e_fail = 0

    for i, symbol in enumerate(universe):
        sector = sector_of(symbol)
        log.info(f"[{i+1:3}/{len(universe)}] {symbol:15} ({sector[:20]})")

        # Already flagged and unresolved — never recompute new levels for it.
        # Just check whether CMP has now crossed the ORIGINAL buy zone.
        if symbol in open_positions:
            check_and_alert_open_position(symbol, open_positions[symbol])
            continue

        try:
            # ── Tier 1: Fundamentals ──────────────────────────────────────────
            fd = fetch_fundamentals(symbol)
            if fd.get("sector") and fd["sector"] != "Unknown":
                _DYNAMIC_SECTOR_CACHE[symbol] = fd["sector"]
                sector = fd["sector"]
            passes, reason, f_score, f_card = fundamental_score(symbol, sector, fd)
            if not passes:
                log.info(f"         ✗ Fundamental: {reason}")
                f_fail += 1
                continue

            # Redundant safety check — fundamental_score() itself already
            # gates at 9/14, this just guards against future threshold drift
            if f_score < 9:
                log.info(f"         ✗ Fundamental score {f_score}/14 below minimum (9)")
                f_fail += 1
                continue
            log.info(f"         ✓ Fundamental score {f_score}/14")

            # ── Tier 2: Trend & EMA Stack ─────────────────────────────────────
            df = fetch_ohlcv(symbol)
            if df is None:
                log.info("         ✗ No price data")
                continue
            df = add_indicators(df)

            t_passes, t_score, t_card, ema200_gap = trend_score(df, fd)
            if not t_passes:
                log.info(f"         ✗ Trend: price too far below EMA200")
                t_fail += 1
                continue

            # Minimum Tier 2 score: 5/8 — needs genuine trend confluence, not
            # just barely-in-buy-zone. Raised from 3/8 for a stricter filter.
            if t_score < 5:
                log.info(f"         ✗ Trend score {t_score}/8 too weak (min 5) — not in buy zone")
                t_fail += 1
                continue
            log.info(f"         ✓ Trend score {t_score}/8")

            # ── Dip check — must be at least 5% from 52W high ─────────────────
            close  = float(df["Close"].iloc[-1])
            high52 = float(df["High"].tail(252).max())
            dip    = (high52 - close) / high52 * 100
            if dip < 5:
                log.info(f"         ✗ Dip only {dip:.1f}% — not a meaningful entry (min 5%)")
                t_fail += 1
                continue

            # ── Tier 3: Entry Timing ──────────────────────────────────────────
            sr = find_sr_zones(df)
            e_passes, e_score, e_card, entry_data = entry_score(df, sr, fd)
            if not e_passes:
                log.info(f"         ✗ Entry: RSI overbought or insufficient setup")
                e_fail += 1
                continue

            # Minimum Tier 3 score: 7/10 — needs multiple entry-timing signals
            # agreeing together, not just a bare pass. Raised from 4/10.
            if e_score < 7:
                log.info(f"         ✗ Entry score {e_score}/10 too weak (min 7) — timing not right")
                e_fail += 1
                continue
            log.info(f"         ✓ Entry score {e_score}/10")

            # ── Tier 4: Sentiment / News / FII-DII (only for stocks that ──────
            #            already passed Tiers 1-3, to limit network calls)
            sent_data = sentiment_score(symbol)
            if sent_data["flags"]:
                for f in sent_data["flags"]:
                    log.info(f"         {f}")

            # ── Assemble signal ───────────────────────────────────────────────
            sig = build_signal(symbol, sector, df, fd,
                               f_score, t_score, e_score, entry_data,
                               ema200_gap=ema200_gap,
                               sentiment_data=sent_data)
            if sig is None:
                log.info(f"         ✗ Signal rejected (RR too poor or SL invalid)")
                continue

            log.info(
                f"         ✅ SIGNAL — {sig['conviction']} | "
                f"Score {sig['total_score']}/30 | "
                f"Dip {sig['dip_pct']}% | RSI {sig['rsi']:.0f}"
            )

            # Always log to Google Sheets
            log_to_sheets(sig)
            signals.append(sig)

            # ── Telegram only for GOOD BUY ★★ (22+) and STRONG BUY ★★★ (26+) ──
            # Score 22+ means all 3 tiers are genuinely strong
            # WATCHLIST (below 22) → Sheets only, no Telegram noise
            if sig["total_score"] >= 22:
                _tg(fmt_buy_alert(sig))
                log.info(f"         📲 Telegram alert sent!")
                time.sleep(0.5)
            else:
                log.info(f"         📋 Score {sig['total_score']} < 22 — Sheets only, no Telegram")

        except Exception as e:
            log.error(f"         ⚠️ Unexpected error for {symbol}: {e}")
            continue

        time.sleep(0.3)

    # Sort by total score
    signals.sort(key=lambda s: s["total_score"], reverse=True)

    # Only include score 22+ in summary (GOOD BUY and above)
    telegram_signals = [s for s in signals if s["total_score"] >= 22]
    watchlist_signals = [s for s in signals if s["total_score"] < 22]

    log.info(f"  Telegram alerts sent: {len(telegram_signals)} (score 19+)")
    log.info(f"  Watchlist logged to Sheets only: {len(watchlist_signals)}")

    # Send summary — only for actionable signals
    _tg(fmt_summary(telegram_signals, label))

    # No separate save step needed — log_to_sheets() already wrote each
    # telegram-worthy signal to the Sheet with Status=OPEN, and that Sheet
    # (not a local file) is what watch_open_trades() reads from.

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
        # Runs ONCE and exits -- the repeated execution comes from the
        # watcher.yml workflow's own schedule (every ~15 min during market
        # hours), not from an internal loop. A long-lived while-loop doesn't
        # fit a GitHub Actions job, which gets a fresh, short-lived runner
        # each time rather than one continuously running process.
        now = datetime.now(IST)
        if now.weekday() < 5 and (9, 15) <= (now.hour, now.minute) <= (15, 30):
            watch_open_trades()
        else:
            log.info("Outside market hours — skipping this watch run.")

    elif mode == "test":
        sym = sys.argv[2] if len(sys.argv) > 2 else "HDFCBANK"
        log.info(f"TEST MODE — {sym}")
        sector = sector_of(sym)

        fd = fetch_fundamentals(sym)
        passes, reason, f_score, f_card = fundamental_score(sym, sector, fd)
        print(f"\n── Fundamentals ──────────────────────────")
        print(f"Passes: {passes}  Score: {f_score}/14")
        print(f"{'Fail reason: '+reason if not passes else ''}")
        for c in f_card: print(f"  {c}")

        if passes:
            df = fetch_ohlcv(sym)
            if df is not None:
                df = add_indicators(df)
                t_passes, t_score, t_card, ema200_gap = trend_score(df, fd)
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
                        sig = build_signal(sym, sector, df, fd, f_score, t_score, e_score, entry_data, ema200_gap=ema200_gap)
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
        universe = build_universe()
        log.info(f"Fundamentals-only scan — {len(universe)} stocks")
        passed = []
        for sym in universe:
            sec = sector_of(sym)
            fd  = fetch_fundamentals(sym)
            ok, reason, fs, card = fundamental_score(sym, sec, fd)
            status = f"✅ {fs:2}/14  {', '.join(card[:3])}" if ok else f"✗  {reason}"
            print(f"{sym:15} {status}")
            if ok: passed.append(sym)
        print(f"\n{len(passed)}/{len(universe)} pass fundamental filter.")

    else:
        print("Usage: python scanner.py [scan | watch | test SYMBOL | fundamentals]")
