"""거래처·매출·영업활동 CSV를 불러와 분석용으로 정리합니다."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).parent
CUSTOMER_PATH = BASE_DIR / "customer_data.csv"
SALES_PATH = BASE_DIR / "sales_data.csv"
ACTIVITY_PATH = BASE_DIR / "activity_data.csv"


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig")


def load_raw() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    customers = _read_csv(CUSTOMER_PATH)
    sales = _read_csv(SALES_PATH)
    activities = _read_csv(ACTIVITY_PATH)
    return customers, sales, activities


def prepare() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    customers, sales, activities = load_raw()

    customers = customers.copy()
    sales = sales.copy()
    activities = activities.copy()

    customers["첫거래일"] = pd.to_datetime(customers["첫거래일"])
    customers["누적매출"] = pd.to_numeric(customers["누적매출"], errors="coerce").fillna(0)

    sales["수주일"] = pd.to_datetime(sales["수주일"])
    sales["납품일"] = pd.to_datetime(sales["납품일"])
    for col in ("수주금액", "매출금액", "미수금"):
        sales[col] = pd.to_numeric(sales[col], errors="coerce").fillna(0)
    sales["납기일수"] = (sales["납품일"] - sales["수주일"]).dt.days
    sales["연도"] = sales["수주일"].dt.year
    sales["월"] = sales["수주일"].dt.to_period("M").astype(str)
    sales["미수여부"] = sales["미수금"] > 0

    activities["활동일"] = pd.to_datetime(activities["활동일"])
    activities["연도"] = activities["활동일"].dt.year
    activities["월"] = activities["활동일"].dt.to_period("M").astype(str)

    cust_extra = customers[["거래처ID", "거래처명", "등급", "담당자명", "첫거래일", "누적매출"]].rename(
        columns={"담당자명": "고객담당자"}
    )
    sales = sales.merge(cust_extra, on="거래처명", how="left")
    activities = activities.merge(
        customers[["거래처ID", "거래처명", "거래처유형", "지역", "등급"]],
        on="거래처명",
        how="left",
    )
    return customers, sales, activities


def apply_filters(
    customers: pd.DataFrame,
    sales: pd.DataFrame,
    activities: pd.DataFrame,
    *,
    date_range: tuple,
    types: list[str],
    regions: list[str],
    grades: list[str],
    products: list[str],
    people: list[str],
    statuses: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    start, end = date_range
    sales_f = sales[(sales["수주일"] >= pd.Timestamp(start)) & (sales["수주일"] <= pd.Timestamp(end))].copy()
    act_f = activities[
        (activities["활동일"] >= pd.Timestamp(start)) & (activities["활동일"] <= pd.Timestamp(end))
    ].copy()

    if types:
        sales_f = sales_f[sales_f["거래처유형"].isin(types)]
        act_f = act_f[act_f["거래처유형"].isin(types)]
    if regions:
        sales_f = sales_f[sales_f["지역"].isin(regions)]
        act_f = act_f[act_f["지역"].isin(regions)]
    if grades:
        sales_f = sales_f[sales_f["등급"].isin(grades)]
        act_f = act_f[act_f["등급"].isin(grades)]
    if products:
        sales_f = sales_f[sales_f["제품군"].isin(products)]
    if people:
        sales_f = sales_f[sales_f["담당영업"].isin(people)]
        act_f = act_f[act_f["담당영업"].isin(people)]
    if statuses:
        sales_f = sales_f[sales_f["수주상태"].isin(statuses)]

    names = set(sales_f["거래처명"]).union(act_f["거래처명"])
    customers_f = customers[customers["거래처명"].isin(names)].copy() if names else customers.iloc[0:0].copy()
    if types:
        customers_f = customers_f[customers_f["거래처유형"].isin(types)]
    if regions:
        customers_f = customers_f[customers_f["지역"].isin(regions)]
    if grades:
        customers_f = customers_f[customers_f["등급"].isin(grades)]
    return customers_f, sales_f, act_f


def customer_metrics(sales: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    done = sales[sales["수주상태"] != "취소"]
    if done.empty:
        return pd.DataFrame()

    grouped = done.groupby("거래처명").agg(
        거래건수=("거래ID", "count"),
        수주금액=("수주금액", "sum"),
        매출금액=("매출금액", "sum"),
        미수금=("미수금", "sum"),
        최근수주=("수주일", "max"),
        제품군수=("제품군", "nunique"),
        유형=("거래처유형", "first"),
        지역=("지역", "first"),
        등급=("등급", "first"),
        담당영업=("담당영업", lambda s: s.mode().iloc[0] if not s.mode().empty else s.iloc[0]),
    )
    grouped["경과일"] = (as_of - grouped["최근수주"]).dt.days
    grouped["객단가"] = (grouped["매출금액"] / grouped["거래건수"]).round(0)

    def _health(days: int, ar: float, revenue: float) -> str:
        if days > 180:
            return "휴면위험"
        if revenue > 0 and ar / revenue >= 0.15:
            return "미수주의"
        if days <= 60 and revenue >= grouped["매출금액"].median():
            return "우량"
        return "유지"

    grouped["거래상태"] = [
        _health(int(r.경과일), float(r.미수금), float(r.매출금액)) for r in grouped.itertuples()
    ]
    return grouped.reset_index().sort_values("매출금액", ascending=False)
