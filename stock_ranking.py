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

@st.cache_data(ttl=86400) # 하루 동안 결과 캐싱
def get_kr_top_performers(year_start, year_end):
    # 한국 시장 전체 리스트 (KOSPI, KOSDAQ, KONEX)
    df_krx = fdr.StockListing('KRX')
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
                df = fdr.DataReader(ticker, year_start, year_end)
                if len(df) > 10:
                    # 첫 거래일과 마지막 거래일 종가 비교
                    start_price = float(df['Close'].iloc[0])
                    end_price = float(df['Close'].iloc[-1])
                    if start_price > 0:
                        ret = ((end_price / start_price) - 1) * 100
                        results.append({'종목코드': ticker, '종목명': names[ticker], '수익률(%)': round(ret, 2)})
            except:
                continue
        status.update(label="한국 데이터 분석 완료!", state="complete")
    progress_bar.empty()
    return pd.DataFrame(results).sort_values(by='수익률(%)', ascending=False).head(10)

@st.cache_data(ttl=86400)
def get_us_top_performers(year_start, year_end):
    # 미국 시장 전체 (NASDAQ, NYSE, AMEX 통합 리스트 추출)
    with st.spinner("미국 시장 종목 리스트 구성 중..."):
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
        progress_bar.progress(min(i/len(all_us_tickers), 1.0))
        try:
            # 시작일과 종료일의 종가만 가져옴
            data = yf.download(batch, start=year_start, end=year_end, progress=False)['Close']
            if not data.empty:
                for ticker in data.columns:
                    ticker_data = data[ticker].dropna()
                    if len(ticker_data) > 2:
                        ret = ((ticker_data.iloc[-1] / ticker_data.iloc[0]) - 1) * 100
                        if float(ticker_data.iloc[0]) > 0:
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
        kr_result = get_kr_top_performers(start_dt, end_dt)
        if not kr_result.empty:
            st.dataframe(kr_result, use_container_width=True)
            st.bar_chart(kr_result.set_index('종목명')['수익률(%)'])
        else:
            st.error("데이터를 불러오지 못했습니다.")

with col2:
    st.subheader("🇺🇸 미국 시장 Top 10")
    if st.button(f"{selected_year} 미국 순위 집계 시작"):
        us_result = get_us_top_performers(start_dt, end_dt)
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
