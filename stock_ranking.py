import streamlit as st
import FinanceDataReader as fdr
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import time

st.set_page_config(page_title="Global Stock Yield Ranking", layout="wide")

st.title("🚀 연도별 전 종목 수익률 랭킹 (KR & US)")
st.markdown("모든 상장 종목(개별주, ETF, ETN, 레버리지, 인버스 등)을 포함하여 수익률을 분석합니다.")

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

# 한국 시장 선택 메뉴 추가
kr_market_selection = st.sidebar.radio(
    "한국 시장 선택",
    ('KRX 전체', 'KOSPI', 'KOSDAQ'),
    index=0 # 기본값은 'KRX 전체'
)

# 미국 시장 선택 메뉴 추가
us_market_selection = st.sidebar.radio(
    "미국 시장 선택",
    ('S&P 500', 'NASDAQ', 'NYSE', 'AMEX', 'US 전체'),
    index=0 # 속도를 위해 기본값을 S&P 500으로 설정
)

@st.cache_data(ttl=86400) # 하루 동안 결과 캐싱
def get_kr_top_performers(year_start, year_end, market_type): # market_type 인자 추가
    # 선택된 시장에 따라 종목 리스트 가져오기
    if market_type == 'KRX 전체':
        df_krx = fdr.StockListing('KRX') # KOSPI, KOSDAQ, KONEX 통합
    elif market_type == 'KOSPI':
        df_krx = fdr.StockListing('KOSPI')
    elif market_type == 'KOSDAQ':
        df_krx = fdr.StockListing('KOSDAQ')
    
    tickers = df_krx['Code'].tolist()
    names = dict(zip(df_krx['Code'], df_krx['Name']))
    
    results = []
    progress_bar = st.progress(0, text="한국 시장 전 종목 데이터 수집 중...")
    
    # 한국 주식은 종목수가 많으므로 효율적인 조회를 위해 loop 사용 (fdr 최적화)
    # 실제 운영 환경에서는 병렬 처리가 필요할 수 있습니다.
    with st.status("한국 종목 분석 중...", expanded=True) as status:
        total = len(tickers)
        for i, ticker in enumerate(tickers):
            if i % 100 == 0: progress_bar.progress(i/total)
            try:
                # 기간 내 데이터가 존재하는지 확인하기 위해 수정
                df = fdr.DataReader(ticker, year_start, year_end)['Close']
                if len(df) >= 2:
                    start_price = float(df.iloc[0])
                    end_price = float(df.iloc[-1])
                    if start_price > 0 and not pd.isna(start_price) and not pd.isna(end_price):
                        ret = ((end_price / start_price) - 1) * 100
                        if abs(ret) < 10000: # 비정상적인 데이터(상장폐지 등) 필터링
                            results.append({'종목코드': ticker, '종목명': names.get(ticker, ticker), '수익률(%)': round(ret, 2)})
            except:
                continue
        status.update(label="한국 데이터 분석 완료!", state="complete")
    progress_bar.empty()
    return pd.DataFrame(results).sort_values(by='수익률(%)', ascending=False).head(10)

@st.cache_data(ttl=86400)
def get_us_top_performers(year_start, year_end, market_type):
    with st.spinner("미국 시장 종목 리스트 구성 중..."):
        if market_type == 'S&P 500':
            all_us_tickers = fdr.StockListing('S&P500')['Symbol'].tolist()
        elif market_type == 'NASDAQ':
            all_us_tickers = fdr.StockListing('NASDAQ')['Symbol'].tolist()
        elif market_type == 'NYSE':
            all_us_tickers = fdr.StockListing('NYSE')['Symbol'].tolist()
        elif market_type == 'AMEX':
            all_us_tickers = fdr.StockListing('AMEX')['Symbol'].tolist()
        else: # US 전체
            nasdaq = fdr.StockListing('NASDAQ')['Symbol']
            nyse = fdr.StockListing('NYSE')['Symbol']
            amex = fdr.StockListing('AMEX')['Symbol']
            all_us_tickers = pd.concat([nasdaq, nyse, amex]).unique().tolist()

    results = []
    batch_size = 200 # API 안정성을 위해 배치 사이즈 축소
    progress_bar = st.progress(0, text="미국 시장 수익률 분석 중...")
    
    with st.status("미국 종목 분석 중...", expanded=True) as status:
        for i in range(0, len(all_us_tickers), batch_size):
            batch = all_us_tickers[i:i+batch_size]
            current_progress = min(i / len(all_us_tickers), 1.0)
            progress_bar.progress(current_progress)
            try:
                # yfinance 다운로드 시 발생할 수 있는 오류 방지를 위해 threads=True 사용
                data = yf.download(batch, start=year_start, end=year_end, progress=False, threads=True)['Close']
                if not data.empty:
                    # 단일 종목일 경우와 다중 종목일 경우 처리
                    temp_df = data if isinstance(data, pd.DataFrame) else data.to_frame()
                    for ticker in temp_df.columns:
                        ticker_series = temp_df[ticker].dropna()
                        if len(ticker_series) >= 2:
                            s_price = float(ticker_series.iloc[0])
                            e_price = float(ticker_series.iloc[-1])
                            if s_price > 0:
                                ret = ((e_price / s_price) - 1) * 100
                                results.append({'Ticker': ticker, 'Return(%)': round(float(ret), 2)})
            except:
                continue
        status.update(label="미국 데이터 분석 완료!", state="complete")
    
    progress_bar.empty()
    return pd.DataFrame(results).sort_values(by='Return(%)', ascending=False).head(10)

st.header(f"📅 {display_text} 수익률 리더보드")

col1, col2 = st.columns(2)

with col1:
    st.subheader("🇰🇷 한국 시장 Top 10")
    if st.button(f"{selected_year} 한국 순위 집계 시작"):
        kr_result = get_kr_top_performers(start_dt, end_dt, kr_market_selection) # market_type 전달
        if not kr_result.empty:
            st.dataframe(kr_result, use_container_width=True)
            st.bar_chart(kr_result.set_index('종목명')['수익률(%)'])
        else:
            st.error("데이터를 불러오지 못했습니다.")

with col2:
    st.subheader("🇺🇸 미국 시장 Top 10")
    if st.button(f"{selected_year} 미국 순위 집계 시작"):
        us_result = get_us_top_performers(start_dt, end_dt, us_market_selection)
        if not us_result.empty:
            st.dataframe(us_result, use_container_width=True)
            st.bar_chart(us_result.set_index('Ticker')['Return(%)'])
        else:
            st.error("데이터를 불러오지 못했습니다.")

st.sidebar.markdown("---")
st.sidebar.info(f"""
**분석 정보**
- **시작일**: {start_dt}
- **종료일**: {end_dt}
""")
