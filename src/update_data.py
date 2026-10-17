import io
import json
import os
import zipfile
from datetime import datetime
from pathlib import Path
import xml.etree.ElementTree as ET

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
KEY = os.getenv("DART_API_KEY", "").strip()
BASE = "https://opendart.fss.or.kr/api"
TARGET_STOCK_CODE = "458870"  # 씨어스테크놀로지 코스닥 종목코드
START_YEAR = 2010
REPORTS = {
    "annual": ["11011"],
    "half-year": ["11012"],
    "quarterly": ["11013", "11014"],
}
COLUMNS = ["year", "category", "report_code", "statement", "account_id",
           "account", "current_period", "amount", "currency",
           "previous_period", "previous_amount"]


def get(endpoint, params=None):
    if not KEY:
        raise RuntimeError("DART_API_KEY가 없습니다. GitHub Actions Secrets를 확인하세요.")
    p = dict(params or {})
    p["crtfc_key"] = KEY
    response = requests.get(f"{BASE}/{endpoint}", params=p, timeout=60)
    response.raise_for_status()
    return response


def company_code():
    response = get("corpCode.xml")
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        xml_bytes = archive.read("CORPCODE.xml")
    root = ET.fromstring(xml_bytes)
    matches = []
    for node in root.findall(".//list"):
        stock_code = (node.findtext("stock_code") or "").strip().zfill(6)
        corp_name = (node.findtext("corp_name") or "").strip()
        corp_code = (node.findtext("corp_code") or "").strip()
        if stock_code == TARGET_STOCK_CODE:
            matches.append({"corp_code": corp_code, "corp_name": corp_name,
                            "stock_code": stock_code})
    if len(matches) != 1:
        raise RuntimeError(
            f"DART 종목코드 {TARGET_STOCK_CODE} 검색 결과가 정확히 1개가 아닙니다: {matches}"
        )
    chosen = matches[0]
    if "씨어스" not in chosen["corp_name"]:
        raise RuntimeError(
            f"종목코드 {TARGET_STOCK_CODE}의 법인명이 씨어스와 일치하지 않습니다: "
            f"{chosen['corp_name']}"
        )
    chosen["corp_code"] = chosen["corp_code"].zfill(8)
    chosen["matched_at"] = datetime.now().isoformat(timespec="seconds")
    (DATA / "company_match.json").write_text(
        json.dumps(chosen, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Verified company: {chosen['corp_name']} "
          f"(stock_code={chosen['stock_code']}, corp_code={chosen['corp_code']})")
    return chosen


def get_accounts(code, year, report_code):
    params = {"corp_code": code, "bsns_year": str(year),
              "reprt_code": report_code, "fs_div": "CFS"}
    data = get("fnlttSinglAcntAll.json", params).json()
    if data.get("status") != "000":
        params["fs_div"] = "OFS"
        data = get("fnlttSinglAcntAll.json", params).json()
    return data.get("list", []) if data.get("status") == "000" else []


def amount(value):
    try:
        text = str(value).replace(",", "").strip()
        return float(text) if text not in ("", "-", "None") else None
    except (TypeError, ValueError):
        return None


def main():
    company = company_code()
    current_year = datetime.now().year
    rows = []
    for year in range(START_YEAR, current_year + 1):
        for category, report_codes in REPORTS.items():
            for report_code in report_codes:
                for account in get_accounts(company["corp_code"], year, report_code):
                    rows.append({
                        "year": year, "category": category, "report_code": report_code,
                        "statement": account.get("sj_nm"),
                        "account_id": account.get("account_id"),
                        "account": account.get("account_nm"),
                        "current_period": account.get("thstrm_nm"),
                        "amount": amount(account.get("thstrm_amount")),
                        "currency": account.get("currency"),
                        "previous_period": account.get("frmtrm_nm"),
                        "previous_amount": amount(account.get("frmtrm_amount")),
                    })

    df = pd.DataFrame(rows, columns=COLUMNS)
    df.to_csv(DATA / "financial_accounts.csv", index=False, encoding="utf-8-sig")

    def find_value(year, category, terms):
        subset = df[(df["year"] == year) & (df["category"] == category)]
        for term in terms:
            found = subset[subset["account"].fillna("").str.contains(term, regex=False)]
            if not found.empty and pd.notna(found.iloc[0]["amount"]):
                return float(found.iloc[0]["amount"])
        return None

    term_map = {
        "assets": ["자산총계"], "liabilities": ["부채총계"], "equity": ["자본총계"],
        "revenue": ["매출액", "영업수익", "수익(매출액)"],
        "operating_profit": ["영업이익"], "net_income": ["당기순이익", "당기순손익"],
    }
    ratios = []
    if not df.empty:
        for (year, category), _ in df.groupby(["year", "category"]):
            values = {key: find_value(int(year), category, terms)
                      for key, terms in term_map.items()}
            assets, liabilities = values["assets"], values["liabilities"]
            revenue, op_profit, net_income = (
                values["revenue"], values["operating_profit"], values["net_income"]
            )
            values["debt_ratio_pct"] = liabilities / assets * 100 if liabilities is not None and assets else None
            values["equity_ratio_pct"] = values["equity"] / assets * 100 if values["equity"] is not None and assets else None
            values["operating_margin_pct"] = op_profit / revenue * 100 if op_profit is not None and revenue else None
            values["net_margin_pct"] = net_income / revenue * 100 if net_income is not None and revenue else None
            ratios.append({"year": int(year), "category": category, **values})
    ratio_df = pd.DataFrame(ratios)
    ratio_df.to_csv(DATA / "financial_ratios.csv", index=False, encoding="utf-8-sig")

    filings = []
    for year in range(START_YEAR, current_year + 1):
        try:
            result = get("list.json", {
                "corp_code": company["corp_code"], "bgn_de": f"{year}0101",
                "end_de": f"{year}1231", "pblntf_ty": "A",
                "page_no": 1, "page_count": 100,
            }).json()
            for item in result.get("list", []):
                report_name = item.get("report_nm", "")
                if any(term in report_name for term in ("사업보고서", "반기보고서", "분기보고서")):
                    filings.append(item)
        except Exception as exc:
            print(f"filing list warning ({year}): {exc}")

    pd.DataFrame(filings).to_csv(DATA / "filings.csv", index=False, encoding="utf-8-sig")
    payload = {
        "company": company,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "accounts": df.astype(object).where(pd.notna(df), None).to_dict("records"),
        "ratios": ratio_df.astype(object).where(pd.notna(ratio_df), None).to_dict("records"),
        "filings": filings,
    }
    (DATA / "dashboard_data.json").write_text(
        json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8"
    )
    if not rows:
        raise RuntimeError("DART에서 재무 계정을 가져오지 못했습니다. 배포를 중단합니다.")
    print(f"Updated {len(rows)} account rows; {len(filings)} filing metadata rows.")


if __name__ == "__main__":
    main()
