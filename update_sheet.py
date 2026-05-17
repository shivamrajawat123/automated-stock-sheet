import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import requests
import zipfile
import io
from datetime import datetime, timedelta
import os
import json

# 1. Credentials Setup
creds_json = os.environ.get('GCP_CREDENTIALS')
if not creds_json:
    print("ERROR: GCP_CREDENTIALS Secret not found!")
    exit(1)

creds_dict = json.loads(creds_json)
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# !!! यहाँ ध्यान दें !!!
# अपनी गूगल शीट की ID (जो आपने भाग 2 के अंत में नोट की थी) को नीचे वाले उद्धरण चिह्नों "" के बीच डालें
spreadsheet_id = "1sY8vnE6FqTh3Wjxtodf5lxmYLtR9T0AGGS-IddR-Agw" 
worksheet = client.open_by_key(spreadsheet_id).worksheet("Top 250 Stocks")

# 2. NSE Data Fetcher
def fetch_bhavcopy_for_date(date_obj):
    date_str = date_obj.strftime("%Y%m%d")
    url = f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{date_str}_F_0000.csv.zip"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                csv_filename = z.namelist()[0]
                with z.open(csv_filename) as f:
                    df = pd.read_csv(f)
            
            sym_col = 'TckrSymb' if 'TckrSymb' in df.columns else 'SYMBOL'
            close_col = 'ClsPric' if 'ClsPric' in df.columns else 'CLOSE'
            series_col = 'SctySrs' if 'SctySrs' in df.columns else 'SERIES'
            
            turnover_col = None
            for c in ['TrdVal', 'TURNOVER', 'NET_TURNOVER']:
                if c in df.columns:
                    turnover_col = c
                    break
            
            if not all([sym_col, close_col, turnover_col]):
                return None
            
            if series_col:
                df = df[df[series_col].astype(str).str.strip() == 'EQ']
            
            filter_keywords = 'BEES|ETF|GOLD|LIQUID|CASE|SILVER|LIQ'
            df = df[~df[sym_col].astype(str).str.contains(filter_keywords, case=False, na=False)]
            
            df[turnover_col] = pd.to_numeric(df[turnover_col], errors='coerce')
            df = df.dropna(subset=[turnover_col])
            
            df_top = df.sort_values(by=turnover_col, ascending=False).head(250)
            return df_top[[sym_col, turnover_col, close_col]].values.tolist()
        return None
    except Exception as e:
        print(f"Error fetching for date {date_str}: {str(e)}")
        return None

# 3. Logic
date = datetime.now()
data_to_insert = None
fetched_date_str = ""
for i in range(7):
    test_date = date - timedelta(days=i)
    if test_date.weekday() >= 5: 
        continue
    data_to_insert = fetch_bhavcopy_for_date(test_date)
    if data_to_insert:
        fetched_date_str = test_date.strftime('%d-%b-%Y')
        break

# 4. Update
if data_to_insert:
    try:
        worksheet.batch_clear(['A2:C251'])
        worksheet.update('A2', data_to_insert)
        ist_now = (datetime.utcnow() + timedelta(hours=5, minutes=30)).strftime('%d-%b %H:%M')
        status_msg = f"Data Date: {fetched_date_str} | Last Update: {ist_now} (IST)"
        worksheet.update('K2', [[status_msg]])
        print("SUCCESS: Sheet Updated!")
    except Exception as e:
        print(f"Google Sheet Error: {str(e)}")
else:
    print("FAILED: No file found.")
