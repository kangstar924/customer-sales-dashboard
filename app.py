"""B2B 거래처·매출·영업활동 분석 대시보드."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from data import apply_filters, customer_metrics, prepare

st.set_page_config(
    page_title="거래처 매출 분석 대시보드",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

PALETTE = ["#0F766E", "#1D4ED8", "#B45309", "#7C3AED", "#BE123C", "#0369A1", "#15803D"]
STATUS_COLOR = {"완료": "#0F766E", "진행중": "#1D4ED8", "취소": "#94A3B8"}
RESULT_COLOR = {"긍정": "#0F766E", "보류": "#D97706", "부정": "#BE123C"}
GRADE_COLOR = {"VIP": "#B45309", "일반": "#0F766E", "신규": "#1D4ED8"}
FONT = "Malgun Gothic, Apple SD Gothic Neo, Noto Sans KR, sans-serif"

LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family=FONT, color="#0F172A", size=13),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    margin=dict(t=48, r=16, b=32, l=16),
    hoverlabel=dict(font=dict(family=FONT, size=12)),
)

def style_fig(fig: go.Figure, *, height: int = 360) -> go.Figure:
    fig.update_layout(**LAYOUT, height=height)
    fig.update_xaxes(showgrid=False, zeroline=False, tickangle=0, automargin=True)
    fig.update_yaxes(gridcolor="#E2E8F0", zeroline=False, automargin=True)
    return fig


def fmt_won(value: float) -> str:
    n = float(value or 0)
    sign = "-" if n < 0 else ""
    n = abs(n)
    if n >= 1e8:
        return f"{sign}{n / 1e8:,.1f}억"
    if n >= 1e4:
        return f"{sign}{n / 1e4:,.0f}만"
    return f"{sign}{n:,.0f}원"


def fmt_int(value: float) -> str:
    return f"{int(value or 0):,}건"


def inject_css() -> None:
    st.markdown(
        """
        <style>
        .stApp { background: #F4F7F8; }
        header[data-testid="stHeader"] { background: transparent; }
        .hero {
            background: linear-gradient(120deg, #0B3A4D 0%, #0F766E 70%, #1D4ED8 140%);
            color: #fff; padding: 22px 28px; border-radius: 18px; margin-bottom: 8px;
        }
        .hero h1 { font-size: 1.55rem; margin: 0 0 6px 0; letter-spacing: -0.02em; }
        .hero p { margin: 0; opacity: 0.86; font-size: 0.95rem; }
        div[data-testid="stMetric"] {
            background: #fff; border: 1px solid #E2E8F0; border-radius: 14px;
            padding: 12px 16px; box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
        }
        div[data-testid="stMetric"] label { color: #64748B !important; font-weight: 600 !important; }
        .insight {
            background: #fff; border-left: 4px solid #0F766E; border-radius: 10px;
            padding: 12px 16px; margin-bottom: 8px; color: #334155; font-size: 0.92rem;
        }
        .block-container { padding-top: 1.2rem; }
        section[data-testid="stSidebar"] { min-width: 260px; }
        div[data-testid="stToolbar"] { visibility: hidden; }
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner=False)
def load_data():
    return prepare()


def insight_cards(customers: pd.DataFrame, sales: pd.DataFrame, activities: pd.DataFrame) -> list[str]:
    notes: list[str] = []
    if sales.empty:
        return ["선택한 조건에 해당하는 거래가 없습니다. 필터를 조정해 주세요."]

    by_cust = sales.groupby("거래처명")["매출금액"].sum().sort_values(ascending=False)
    if not by_cust.empty:
        notes.append(f"매출 1위 거래처는 <strong>{by_cust.index[0]}</strong> ({fmt_won(by_cust.iloc[0])}) 입니다.")

    by_prod = sales.groupby("제품군")["매출금액"].sum().sort_values(ascending=False)
    if not by_prod.empty:
        share = by_prod.iloc[0] / by_prod.sum() * 100 if by_prod.sum() else 0
        notes.append(f"주력 제품군은 <strong>{by_prod.index[0]}</strong>이며, 매출의 {share:.0f}%를 차지합니다.")

    by_person = sales.groupby("담당영업")["매출금액"].sum().sort_values(ascending=False)
    if not by_person.empty:
        notes.append(f"담당영업 매출 1위는 <strong>{by_person.index[0]}</strong> ({fmt_won(by_person.iloc[0])}) 입니다.")

    cancel = (sales["수주상태"] == "취소").mean() * 100
    notes.append(f"수주 취소율은 <strong>{cancel:.1f}%</strong> ({int((sales['수주상태']=='취소').sum())}건) 입니다.")

    ar = sales["미수금"].sum()
    rev = sales["매출금액"].sum()
    if rev:
        notes.append(f"미수금은 <strong>{fmt_won(ar)}</strong>, 매출 대비 {ar / rev * 100:.1f}% 입니다.")

    if not activities.empty:
        pos = (activities["활동결과"] == "긍정").mean() * 100
        notes.append(f"영업활동 긍정 비율은 <strong>{pos:.1f}%</strong> ({len(activities):,}건 중) 입니다.")

    if not customers.empty:
        vip = customers[customers["등급"] == "VIP"]
        notes.append(f"VIP 거래처는 {len(vip)}곳이며, 마스터 누적매출 기준 {fmt_won(vip['누적매출'].sum())} 입니다.")
    return notes


def kpi_row(sales: pd.DataFrame, customers: pd.DataFrame, activities: pd.DataFrame) -> None:
    revenue = sales["매출금액"].sum()
    order_amt = sales["수주금액"].sum()
    ar = sales["미수금"].sum()
    n_deal = len(sales)
    n_cust = customers["거래처명"].nunique() if not customers.empty else 0
    done_rate = (sales["수주상태"] == "완료").mean() * 100 if n_deal else 0
    pos_rate = (activities["활동결과"] == "긍정").mean() * 100 if len(activities) else 0

    r1 = st.columns(3)
    r1[0].metric("거래처", f"{n_cust:,}곳")
    r1[1].metric("매출", fmt_won(revenue))
    r1[2].metric("수주금액", fmt_won(order_amt))
    r2 = st.columns(3)
    r2[0].metric("미수금", fmt_won(ar))
    r2[1].metric("수주 건수", f"{n_deal:,}건", f"완료율 {done_rate:.0f}%")
    r2[2].metric("영업활동", f"{len(activities):,}건", f"긍정 {pos_rate:.0f}%")


def tab_overview(customers: pd.DataFrame, sales: pd.DataFrame, activities: pd.DataFrame) -> None:
    kpi_row(sales, customers, activities)
    st.write("")

    left, right = st.columns((1.6, 1))
    monthly = (
        sales.groupby("월", as_index=False)
        .agg(매출=("매출금액", "sum"), 수주=("수주금액", "sum"), 건수=("거래ID", "count"))
        .sort_values("월")
    )
    fig = go.Figure()
    fig.add_bar(x=monthly["월"], y=monthly["수주"], name="수주금액", marker_color="#99F6E4")
    fig.add_scatter(
        x=monthly["월"],
        y=monthly["매출"],
        name="매출금액",
        mode="lines+markers",
        line=dict(color="#0F766E", width=3),
        marker=dict(size=7),
    )
    fig.update_layout(yaxis_title="금액(원)", bargap=0.25)
    left.plotly_chart(style_fig(fig, height=390), width="stretch")

    status = sales["수주상태"].value_counts().rename_axis("수주상태").reset_index(name="건수")
    fig_s = px.pie(
        status,
        names="수주상태",
        values="건수",
        hole=0.58,
        color="수주상태",
        color_discrete_map=STATUS_COLOR,
    )
    fig_s.update_traces(textposition="inside", textinfo="percent+label")
    right.plotly_chart(style_fig(fig_s, height=390), width="stretch")

    c1, c2 = st.columns(2)
    q = sales.groupby(["분기", "제품군"], as_index=False)["매출금액"].sum()
    fig_q = px.bar(
        q,
        x="분기",
        y="매출금액",
        color="제품군",
        color_discrete_sequence=PALETTE,
        category_orders={"분기": sorted(sales["분기"].unique())},
    )
    fig_q.update_layout(yaxis_title="매출(원)", barmode="stack")
    c1.plotly_chart(style_fig(fig_q, height=380), width="stretch")

    type_rev = sales.groupby("거래처유형", as_index=False)["매출금액"].sum().sort_values("매출금액")
    fig_t = px.bar(type_rev, x="매출금액", y="거래처유형", orientation="h", color_discrete_sequence=["#0F766E"])
    fig_t.update_layout(xaxis_title="매출(원)")
    c2.plotly_chart(style_fig(fig_t, height=380), width="stretch")

    st.subheader("핵심 인사이트")
    for note in insight_cards(customers, sales, activities):
        st.markdown(f"<div class='insight'>{note}</div>", unsafe_allow_html=True)


def tab_customers(customers: pd.DataFrame, sales: pd.DataFrame, as_of: pd.Timestamp) -> None:
    metrics = customer_metrics(sales, as_of)
    k1, k2, k3, k4 = st.columns(4)
    if metrics.empty:
        st.info("조건에 맞는 거래처 지표가 없습니다.")
        return

    k1.metric("분석 거래처", f"{len(metrics):,}곳")
    k2.metric("우량", f"{int((metrics['거래상태']=='우량').sum())}곳")
    k3.metric("휴면위험", f"{int((metrics['거래상태']=='휴면위험').sum())}곳")
    k4.metric("미수주의", f"{int((metrics['거래상태']=='미수주의').sum())}곳")

    c1, c2, c3 = st.columns(3)
    grade = customers["등급"].value_counts().rename_axis("등급").reset_index(name="수")
    fig_g = px.pie(grade, names="등급", values="수", hole=0.55, color="등급", color_discrete_map=GRADE_COLOR)
    fig_g.update_traces(textposition="inside", textinfo="percent+label")
    c1.plotly_chart(style_fig(fig_g, height=340), width="stretch")

    region = (
        sales.groupby("지역", as_index=False)["매출금액"].sum().sort_values("매출금액", ascending=False)
    )
    fig_r = px.bar(region, x="지역", y="매출금액", color_discrete_sequence=["#1D4ED8"])
    c2.plotly_chart(style_fig(fig_r, height=340), width="stretch")

    health = metrics["거래상태"].value_counts().rename_axis("거래상태").reset_index(name="수")
    fig_h = px.bar(health, x="거래상태", y="수", color="거래상태", color_discrete_sequence=PALETTE)
    c3.plotly_chart(style_fig(fig_h, height=340), width="stretch")

    st.subheader("거래처 매출 상위")
    top_n = st.slider("표시 건수", 5, min(20, len(metrics)), min(10, len(metrics)))
    top = metrics.head(top_n).sort_values("매출금액")
    fig_top = px.bar(
        top,
        x="매출금액",
        y="거래처명",
        color="등급",
        orientation="h",
        color_discrete_map=GRADE_COLOR,
        hover_data=["거래건수", "미수금", "경과일"],
    )
    st.plotly_chart(style_fig(fig_top, height=max(360, top_n * 28)), width="stretch")

    show = metrics.copy()
    show["수주금액"] = show["수주금액"].map(fmt_won)
    show["매출금액"] = show["매출금액"].map(fmt_won)
    show["미수금"] = show["미수금"].map(fmt_won)
    show["객단가"] = show["객단가"].map(fmt_won)
    show["최근수주"] = pd.to_datetime(show["최근수주"]).dt.strftime("%Y-%m-%d")
    st.dataframe(
        show[
            [
                "거래처명",
                "유형",
                "지역",
                "등급",
                "담당영업",
                "거래건수",
                "매출금액",
                "미수금",
                "객단가",
                "최근수주",
                "경과일",
                "거래상태",
            ]
        ],
        width="stretch",
        hide_index=True,
    )


def tab_sales(sales: pd.DataFrame) -> None:
    if sales.empty:
        st.info("조건에 맞는 매출 데이터가 없습니다.")
        return

    c1, c2 = st.columns(2)
    prod = (
        sales.groupby(["제품군", "제품명"], as_index=False)
        .agg(매출=("매출금액", "sum"), 건수=("거래ID", "count"))
        .sort_values("매출", ascending=False)
    )
    fig_p = px.bar(prod, x="제품명", y="매출", color="제품군", color_discrete_sequence=PALETTE)
    fig_p.update_layout(yaxis_title="매출(원)")
    fig_p.update_xaxes(tickangle=-30)
    c1.plotly_chart(style_fig(fig_p, height=400), width="stretch")

    people = (
        sales.groupby("담당영업", as_index=False)
        .agg(매출=("매출금액", "sum"), 수주=("수주금액", "sum"), 건수=("거래ID", "count"), 미수=("미수금", "sum"))
        .sort_values("매출", ascending=False)
    )
    fig_pe = px.bar(people, x="담당영업", y="매출", color_discrete_sequence=["#0F766E"])
    c2.plotly_chart(style_fig(fig_pe, height=400), width="stretch")

    s1, s2 = st.columns(2)
    heat = sales.pivot_table(index="담당영업", columns="제품군", values="매출금액", aggfunc="sum", fill_value=0)
    fig_heat = px.imshow(
        heat,
        color_continuous_scale=["#F0FDFA", "#0F766E"],
        aspect="auto",
        labels=dict(color="매출"),
    )
    s1.plotly_chart(style_fig(fig_heat, height=360), width="stretch")

    lead = sales[sales["수주상태"] != "취소"].groupby("제품군", as_index=False)["납기일수"].mean()
    fig_l = px.bar(lead, x="제품군", y="납기일수", color_discrete_sequence=["#7C3AED"])
    fig_l.update_layout(yaxis_title="평균 납기(일)")
    s2.plotly_chart(style_fig(fig_l, height=360), width="stretch")

    st.subheader("파이프라인 · 미수금")
    p1, p2 = st.columns(2)
    pipeline = sales[sales["수주상태"] == "진행중"].sort_values("수주금액", ascending=False)
    p1.caption("진행중 수주")
    if pipeline.empty:
        p1.info("진행중 건이 없습니다.")
    else:
        view = pipeline[["거래ID", "거래처명", "제품명", "담당영업", "수주일", "수주금액", "분기"]].copy()
        view["수주일"] = view["수주일"].dt.strftime("%Y-%m-%d")
        view["수주금액"] = view["수주금액"].map(fmt_won)
        p1.dataframe(view, width="stretch", hide_index=True, height=320)

    ar = sales[sales["미수금"] > 0].sort_values("미수금", ascending=False)
    p2.caption("미수금 발생 건")
    if ar.empty:
        p2.info("미수금이 없습니다.")
    else:
        view = ar[["거래ID", "거래처명", "담당영업", "매출금액", "미수금", "수주상태"]].copy()
        view["매출금액"] = view["매출금액"].map(fmt_won)
        view["미수금"] = view["미수금"].map(fmt_won)
        p2.dataframe(view, width="stretch", hide_index=True, height=320)

    people["매출"] = people["매출"].map(fmt_won)
    people["수주"] = people["수주"].map(fmt_won)
    people["미수"] = people["미수"].map(fmt_won)
    st.subheader("담당영업 실적")
    st.dataframe(people, width="stretch", hide_index=True)


def tab_activity(activities: pd.DataFrame) -> None:
    if activities.empty:
        st.info("조건에 맞는 영업활동이 없습니다.")
        return

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("활동 건수", f"{len(activities):,}건")
    k2.metric("긍정", f"{int((activities['활동결과']=='긍정').sum())}건")
    k3.metric("보류", f"{int((activities['활동결과']=='보류').sum())}건")
    k4.metric("부정", f"{int((activities['활동결과']=='부정').sum())}건")

    order = ["전화상담", "방문미팅", "제품시연", "제안서발송", "계약협의"]
    types = (
        activities["활동유형"].value_counts().reindex(order).dropna().rename_axis("활동유형").reset_index(name="건수")
    )
    c1, c2 = st.columns(2)
    fig_funnel = px.bar(types, x="건수", y="활동유형", orientation="h", color_discrete_sequence=["#0F766E"])
    fig_funnel.update_layout(yaxis=dict(categoryorder="array", categoryarray=list(reversed(order))))
    c1.plotly_chart(style_fig(fig_funnel, height=380), width="stretch")

    mix = activities.groupby(["활동유형", "활동결과"]).size().reset_index(name="건수")
    fig_mix = px.bar(
        mix,
        x="활동유형",
        y="건수",
        color="활동결과",
        color_discrete_map=RESULT_COLOR,
        category_orders={"활동유형": order, "활동결과": ["긍정", "보류", "부정"]},
        barmode="stack",
    )
    c2.plotly_chart(style_fig(fig_mix, height=380), width="stretch")

    person = (
        activities.groupby("담당영업")
        .agg(
            활동=("활동ID", "count"),
            긍정=("활동결과", lambda s: (s == "긍정").sum()),
            부정=("활동결과", lambda s: (s == "부정").sum()),
        )
        .reset_index()
    )
    person["긍정률"] = (person["긍정"] / person["활동"] * 100).round(1)
    fig_pr = px.bar(person.sort_values("긍정률", ascending=False), x="담당영업", y="긍정률", color_discrete_sequence=["#0F766E"])
    fig_pr.update_layout(yaxis_title="긍정률(%)")
    st.plotly_chart(style_fig(fig_pr, height=340), width="stretch")

    st.subheader("다음 액션")
    next_act = activities["다음액션"].value_counts().reset_index()
    next_act.columns = ["다음액션", "건수"]
    n1, n2 = st.columns((1, 1.4))
    n1.dataframe(next_act, width="stretch", hide_index=True, height=280)
    recent = activities.sort_values("활동일", ascending=False).head(20).copy()
    recent["활동일"] = recent["활동일"].dt.strftime("%Y-%m-%d")
    n2.dataframe(
        recent[["활동일", "거래처명", "담당영업", "활동유형", "활동결과", "다음액션"]],
        width="stretch",
        hide_index=True,
        height=280,
    )


def tab_table(customers: pd.DataFrame, sales: pd.DataFrame, activities: pd.DataFrame) -> None:
    kind = st.radio("데이터", ["매출", "거래처", "영업활동"], horizontal=True)
    if kind == "매출":
        view = sales.copy()
        view["수주일"] = view["수주일"].dt.strftime("%Y-%m-%d")
        view["납품일"] = view["납품일"].dt.strftime("%Y-%m-%d")
        st.dataframe(view, width="stretch", hide_index=True, height=520)
        st.download_button(
            "필터된 매출 CSV 다운로드",
            view.to_csv(index=False, encoding="utf-8-sig"),
            file_name="sales_filtered.csv",
            mime="text/csv",
        )
    elif kind == "거래처":
        view = customers.copy()
        view["첫거래일"] = view["첫거래일"].dt.strftime("%Y-%m-%d")
        st.dataframe(view, width="stretch", hide_index=True, height=520)
        st.download_button(
            "필터된 거래처 CSV 다운로드",
            view.to_csv(index=False, encoding="utf-8-sig"),
            file_name="customers_filtered.csv",
            mime="text/csv",
        )
    else:
        view = activities.copy()
        view["활동일"] = view["활동일"].dt.strftime("%Y-%m-%d")
        st.dataframe(view, width="stretch", hide_index=True, height=520)
        st.download_button(
            "필터된 영업활동 CSV 다운로드",
            view.to_csv(index=False, encoding="utf-8-sig"),
            file_name="activities_filtered.csv",
            mime="text/csv",
        )


def main() -> None:
    inject_css()
    customers, sales, activities = load_data()
    as_of = sales["수주일"].max()

    st.markdown(
        """
        <div class="hero">
            <h1>거래처 매출 분석 대시보드</h1>
            <p>거래처 마스터 · 수주/매출 · 영업활동을 한 화면에서 살펴봅니다. 왼쪽 필터로 기간과 조직을 좁힐 수 있습니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.header("필터")
        min_d = min(sales["수주일"].min(), activities["활동일"].min()).date()
        max_d = max(sales["수주일"].max(), activities["활동일"].max()).date()
        date_range = st.date_input("수주/활동 기간", value=(min_d, max_d), min_value=min_d, max_value=max_d)
        if isinstance(date_range, tuple) and len(date_range) == 2:
            start, end = date_range
        else:
            start, end = min_d, max_d

        types = st.multiselect("거래처유형", sorted(sales["거래처유형"].dropna().unique()))
        regions = st.multiselect("지역", sorted(sales["지역"].dropna().unique()))
        grades = st.multiselect("등급", ["VIP", "일반", "신규"])
        products = st.multiselect("제품군", sorted(sales["제품군"].dropna().unique()))
        people = st.multiselect("담당영업", sorted(sales["담당영업"].dropna().unique()))
        statuses = st.multiselect("수주상태", ["완료", "진행중", "취소"])
        st.caption(f"원본 거래처 {len(customers):,}곳 · 매출 {len(sales):,}건 · 활동 {len(activities):,}건")

    customers_f, sales_f, act_f = apply_filters(
        customers,
        sales,
        activities,
        date_range=(start, end),
        types=types,
        regions=regions,
        grades=grades,
        products=products,
        people=people,
        statuses=statuses,
    )

    t1, t2, t3, t4, t5 = st.tabs(["개요", "거래처", "매출·수주", "영업활동", "데이터"])
    with t1:
        tab_overview(customers_f, sales_f, act_f)
    with t2:
        tab_customers(customers_f, sales_f, as_of)
    with t3:
        tab_sales(sales_f)
    with t4:
        tab_activity(act_f)
    with t5:
        tab_table(customers_f, sales_f, act_f)


if __name__ == "__main__":
    main()
