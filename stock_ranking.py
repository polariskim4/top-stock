import streamlit as st
import FinanceDataReader as fdr
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import requests
import time
import io

st.set_page_config(page_title="Global Stock Yield Ranking", layout="wide")

st.title("🚀 연도별 전 종목 수익률 랭킹 (KR & US)")
st.markdown("개별 종목(ETF, ETN 등 제외)을 대상으로 연도별 수익률 순위를 분석합니다.")

# 1. 연도 선택 설정
current_year = datetime.now().year
selected_year = st.sidebar.selectbox("조회할 연도를 선택하세요", range(current_year, 2010, -1))

# 2. 기간 계산 (올해면 YTD, 이전이면 해당 연도 전체)
if selected_year == current_year:
    start_dt = f"{selected_year}-01-01"
    end_dt = datetime.now().strftime('%Y-%m-%d')
    display_text = f"{selected_year}년 (YTD)"
else:
    start_dt = f"{selected_year}-01-01"
    end_dt = f"{selected_year}-12-31"
    display_text = f"{selected_year}년 전체"

# 3. 시장 선택 메뉴 (라디오 버튼으로 변경 및 범위 한정)
kr_market_selection = st.sidebar.radio(
    "🇰🇷 한국 시장 선택 (개별주)",
    ('KOSPI 200', 'KOSDAQ 150'),
    index=0
)

@st.cache_data(ttl=86400) # 하루 동안 결과 캐싱
def get_kr_top_performers(year_start, year_end, market_type): # market_type 인자 추가
    # FinanceDataReader는 'KOSPI200', 'KOSDAQ150' 명칭을 직접 지원하지 않으므로
    # 기본 시장(KOSPI/KOSDAQ) 데이터를 가져온 후 시가총액 상위 종목으로 한정합니다.
    base_market = 'KOSPI' if 'KOSPI' in market_type else 'KOSDAQ'
    df_krx = fdr.StockListing(base_market)
    
    # 시가총액(Marcap) 기준으로 상위 추출
    limit = 200 if '200' in market_type else 150
    if 'Marcap' in df_krx.columns:
        df_krx = df_krx.sort_values('Marcap', ascending=False).head(limit)
    else:
        df_krx = df_krx.head(limit)

    # ETP(ETF, ETN), 스팩(SPAC), 정리매매 종목 필터링 (상장폐지 및 거래종목 관리)
    exclude_keywords = 'ETF|ETN|스팩|제[0-9]+호|정리매매'
    df_krx = df_krx[~df_krx['Name'].str.contains(exclude_keywords, case=False, na=False)]

    # yfinance 배치를 위해 티커 변환 (예: 005930.KS)
    code_col = 'Code' if 'Code' in df_krx.columns else 'Symbol'
    suffix = '.KS' if 'KOSPI' in market_type else '.KQ'
    
    # 마켓 리스트의 코드도 6자리로 정규화하여 섹터 맵과 대조 (종목 정보 맵 생성)
    tickers_info = {}
    for _, row in df_krx.iterrows():
        clean_code = str(row[code_col]).strip().zfill(6)
        # 개별 시장 리스트(df_krx)에서 직접 섹터/산업 정보를 가져와 정확도를 높입니다.
        sector = row.get('Sector', row.get('Industry', '기타'))
        if pd.isna(sector) or str(sector).strip() == '':
            sector = '기타'
        tickers_info[clean_code + suffix] = {
            'name': row['Name'], 
            'sector': str(sector).strip()
        }
    all_tickers = list(tickers_info.keys())
    
    results = []
    batch_size = 200
    progress_bar = st.progress(0, text=f"{market_type} 수익률 분석 중...")
    
    with st.status(f"{market_type} 데이터 수집 중...", expanded=True) as status:
        for i in range(0, len(all_tickers), batch_size):
            batch = all_tickers[i:i+batch_size]
            progress_bar.progress(min(i / len(all_tickers), 1.0))
            try:
                # group_by='ticker'를 사용하여 데이터 구조를 일관되게 유지합니다.
                data = yf.download(batch, start=year_start, end=year_end, progress=False, group_by='ticker')
                if not data.empty:
                    for ticker in batch:
                        if isinstance(data.columns, pd.MultiIndex):
                            ticker_data = data[ticker] if ticker in data.columns.levels[0] else None
                        else:
                            ticker_data = data if ticker in data.columns else None
                        
                        if ticker_data is not None and 'Close' in ticker_data.columns:
                            ticker_series = ticker_data['Close'].dropna()
                            # 데이터가 충분하고, 전체 기간 및 최근 5거래일간 가격 변동이 있는 종목만 (거래정지 제외)
                            if len(ticker_series) > 10 and ticker_series.std() > 0 and ticker_series.tail(5).std() > 0:
                                s_price = float(ticker_series.iloc[0])
                                e_price = float(ticker_series.iloc[-1])
                                if s_price > 0:
                                    ret = ((e_price / s_price) - 1) * 100
                                    results.append({
                                        '섹터': tickers_info[ticker]['sector'],
                                        '종목코드': ticker.split('.')[0], 
                                        '종목명': tickers_info[ticker]['name'], 
                                        '수익률(%)': float(ret)
                                    })
            except:
                continue
        status.update(label=f"{market_type} 분석 완료!", state="complete")
    progress_bar.empty()
    return pd.DataFrame(results).sort_values(by='수익률(%)', ascending=False).head(10)

# 미국 시장 선택 메뉴 (수정)
us_market_selection = st.sidebar.radio(
    "🇺🇸 미국 시장 선택 (개별주)",
    ('S&P 500', 'Nasdaq 100', 'Dow 30'),
    index=0
)

@st.cache_data(ttl=86400)
def get_us_top_performers(year_start, year_end, market_type):
    # 선택된 지수별 구성 종목 리스트 가져오기
    with st.spinner(f"미국 {market_type} 정보 및 상세 섹터 구성 중..."):
        # 1. S&P 500 정보를 먼저 가져와 상세 섹터(GICS Sub-Industry) 마스터 맵 생성
        url_sp500 = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        resp_sp = requests.get(url_sp500, headers={'User-agent': 'Mozilla/5.0'})
        df_sp500 = pd.read_html(io.StringIO(resp_sp.text), match='Symbol')[0]
        
        def extract_sector(row):
            # 1순위: 상세 업종(Sub-Industry), 2순위: 일반 업종(Sector/Industry)
            cols = row.index.tolist()
            # 상세 분류 우선 탐색
            for target in ['Sub-Industry', 'SubIndustry']:
                for c in cols:
                    if target.lower() in c.lower() and pd.notna(row[c]):
                        return str(row[c]).strip()
            # 대분류 탐색
            for target in ['Sector', 'Industry']:
                for c in cols:
                    if target.lower() in c.lower() and pd.notna(row[c]):
                        return str(row[c]).strip()
            return 'Information Technology' # 기본값 변경

        # 상세 섹터(GICS Sub-Industry) 정보를 기본으로 마스터 맵 구축
        master_map = {str(row['Symbol']).strip(): {'name': row['Security'], 'sector': extract_sector(row)} for _, row in df_sp500.iterrows()}

        us_info_map = {}
        if market_type == 'S&P 500':
            us_info_map = master_map
        elif market_type == 'Nasdaq 100':
            # 위키피디아에서 Nasdaq 100 구성 종목 리스트 추출
            url = 'https://en.wikipedia.org/wiki/Nasdaq-100'
            resp = requests.get(url, headers={'User-agent': 'Mozilla/5.0'})
            df_listing = pd.read_html(io.StringIO(resp.text), match='Ticker')[0]
            for _, row in df_listing.iterrows():
                ticker = str(row['Ticker']).strip()
                # 마스터 맵(S&P 500 상세 정보)에 있으면 사용, 없으면 자체 정보 활용
                if ticker in master_map:
                    us_info_map[ticker] = master_map[ticker]
                else:
                    us_info_map[ticker] = {'name': row['Company'], 'sector': extract_sector(row)}
        elif market_type == 'Dow 30':
            # 위키피디아에서 Dow Jones Industrial Average 구성 종목 리스트 추출
            url = 'https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average'
            resp = requests.get(url, headers={'User-agent': 'Mozilla/5.0'})
            df_listing = pd.read_html(io.StringIO(resp.text), match='Symbol')[0]
            for _, row in df_listing.iterrows():
                symbol = str(row['Symbol']).strip()
                if symbol in master_map:
                    us_info_map[symbol] = master_map[symbol]
                else:
                    us_info_map[symbol] = {'name': row['Company'], 'sector': extract_sector(row)}

    # yfinance 호환성을 위해 티커 기호 정제 및 정보 맵 정제
    all_us_tickers = [str(ticker).replace('.', '-') for ticker in us_info_map.keys()]
    us_info_map = {str(k).replace('.', '-'): v for k, v in us_info_map.items()}

    results = []
    batch_size = 200 # API 안정성을 위해 배치 사이즈 축소
    progress_bar = st.progress(0, text=f"미국 {market_type} 수익률 분석 중...")
    
    with st.status("미국 종목 분석 중...", expanded=True) as status:
        for i in range(0, len(all_us_tickers), batch_size):
            batch = all_us_tickers[i:i+batch_size]
            current_progress = min(i / len(all_us_tickers), 1.0)
            progress_bar.progress(current_progress)
            try:
                # 미국 주식도 동일하게 일관된 데이터 구조를 확보합니다.
                data = yf.download(batch, start=year_start, end=year_end, progress=False, group_by='ticker')
                if not data.empty:
                    for ticker in batch:
                        if isinstance(data.columns, pd.MultiIndex):
                            ticker_data = data[ticker] if ticker in data.columns.levels[0] else None
                        else:
                            ticker_data = data if ticker in data.columns else None
                        
                        if ticker_data is not None and 'Close' in ticker_data.columns:
                            ticker_series = ticker_data['Close'].dropna()
                            # 미국 주식도 동일하게 최근 변동성 체크 적용
                            if len(ticker_series) > 5 and ticker_series.tail(5).std() > 0:
                                s_price = float(ticker_series.iloc[0])
                                e_price = float(ticker_series.iloc[-1])
                                if s_price > 0:
                                    ret = ((e_price / s_price) - 1) * 100
                                    results.append({
                                        '섹터': us_info_map.get(ticker, {}).get('sector', 'N/A'),
                                        '티커': ticker.replace('-', '.'), 
                                        '종목명': us_info_map.get(ticker, {}).get('name', ticker), 
                                        '수익률(%)': float(ret)
                                    })
            except:
                continue
        status.update(label="미국 데이터 분석 완료!", state="complete")
    
    progress_bar.empty()
    return pd.DataFrame(results).sort_values(by='수익률(%)', ascending=False).head(10)

st.header(f"📅 {display_text} 수익률 리더보드")

col1, col2 = st.columns(2)

with col1:
    st.subheader("🇰🇷 한국 시장 Top 10")
    if st.button(f"{selected_year} 한국 순위 집계 시작"):
        kr_result = get_kr_top_performers(start_dt, end_dt, kr_market_selection) # market_type 전달
        if not kr_result.empty:
            st.dataframe(
                kr_result,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "수익률(%)": st.column_config.NumberColumn(format="%.1f")
                }
            )
        else:
            st.error("데이터를 불러오지 못했습니다.")

with col2:
    st.subheader("🇺🇸 미국 시장 Top 10")
    if st.button(f"{selected_year} 미국 순위 집계 시작"):
        us_result = get_us_top_performers(start_dt, end_dt, us_market_selection)
        if not us_result.empty:
            st.dataframe(
                us_result,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "수익률(%)": st.column_config.NumberColumn(format="%.1f")
                }
            )
        else:
            st.error("데이터를 불러오지 못했습니다.")

st.sidebar.markdown("---")
st.sidebar.info(f"""
**분석 정보**
- **시작일**: {start_dt}
- **종료일**: {end_dt}
""")
