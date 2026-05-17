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
    ('KOSPI', 'KOSDAQ'),
    index=0
)

@st.cache_data(ttl=86400) # 하루 동안 결과 캐싱
def get_kr_top_performers(year_start, year_end, market_type): # market_type 인자 추가
    # 선택된 시장(KOSPI/KOSDAQ)의 종목 리스트 가져오기
    df_krx = fdr.StockListing(market_type)
    
    # 개별주로만 한정: 'Sector' 컬럼이 비어있지 않은 종목만 필터링 (ETF/ETN/ETP 제외)
    df_krx = df_krx[df_krx['Sector'].notna()]

    # yfinance 배치를 위해 티커 변환 (예: 005930.KS)
    suffix = '.KS' if market_type == 'KOSPI' else '.KQ'
    tickers_map = {row['Code'] + suffix: row['Name'] for _, row in df_krx.iterrows()}
    all_tickers = list(tickers_map.keys())
    
    results = []
    batch_size = 200
    progress_bar = st.progress(0, text=f"{market_type} 수익률 분석 중...")
    
    with st.status(f"{market_type} 데이터 수집 중...", expanded=True) as status:
        for i in range(0, len(all_tickers), batch_size):
            batch = all_tickers[i:i+batch_size]
            progress_bar.progress(min(i / len(all_tickers), 1.0))
            try:
                # 한국 주식도 yfinance 배치를 통해 속도 극대화
                data = yf.download(batch, start=year_start, end=year_end, progress=False, threads=True)['Close']
                if not data.empty:
                    temp_df = data if isinstance(data, pd.DataFrame) else data.to_frame()
                    for ticker in temp_df.columns:
                        ticker_series = temp_df[ticker].dropna()
                        if len(ticker_series) >= 2:
                            s_price = float(ticker_series.iloc[0])
                            e_price = float(ticker_series.iloc[-1])
                            if s_price > 0:
                                ret = ((e_price / s_price) - 1) * 100
                                results.append({'종목명': tickers_map[ticker], '수익률(%)': round(ret, 2)})
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
    with st.spinner(f"미국 {market_type} 리스트 구성 중..."):
        if market_type == 'S&P 500':
            all_us_tickers = fdr.StockListing('S&P500')['Symbol'].tolist()
        elif market_type == 'Nasdaq 100':
            # 위키피디아에서 Nasdaq 100 구성 종목 리스트 추출
            url = 'https://en.wikipedia.org/wiki/Nasdaq-100'
            resp = requests.get(url, headers={'User-agent': 'Mozilla/5.0'})
            all_us_tickers = pd.read_html(io.StringIO(resp.text))[4]['Ticker'].tolist()
        elif market_type == 'Dow 30':
            # 위키피디아에서 Dow Jones Industrial Average 구성 종목 리스트 추출
            url = 'https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average'
            resp = requests.get(url, headers={'User-agent': 'Mozilla/5.0'})
            all_us_tickers = pd.read_html(io.StringIO(resp.text))[1]['Symbol'].tolist()

    # yfinance 호환성을 위해 티커 기호 정제 (예: BRK.B -> BRK-B)
    all_us_tickers = [ticker.replace('.', '-') for ticker in all_us_tickers]

    results = []
    batch_size = 200 # API 안정성을 위해 배치 사이즈 축소
    progress_bar = st.progress(0, text=f"미국 {market_type} 수익률 분석 중...")
    
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
