import os, io, json, zipfile
from pathlib import Path
from datetime import datetime
import requests
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
KEY = os.getenv("DART_API_KEY", "").strip()
BASE = "https://opendart.fss.or.kr/api"
TARGET_STOCK_CODE = "458870"  # 씨어스 코스닥 종목코드

def company_code():
    # Do not match by company-name substring: this can select a different issuer.
    z = zipfile.ZipFile(io.BytesIO(get("corpCode.xml").content))
    df = pd.read_xml(io.BytesIO(z.read("CORPCODE.xml")), xpath=".//list", dtype=str)
    for col in ("corp_code", "corp_name", "stock_code"):
        if col not in df.columns:
            raise RuntimeError(f"DART 법인코드 목록에 {col} 필드가 없습니다.")
    df["stock_code"] = df["stock_code"].fillna("").astype(str).str.strip().str.zfill(6)
    df["corp_name"] = df["corp_name"].fillna("").str.strip()
    matches = df[df["stock_code"] == TARGET_STOCK_CODE]
    if len(matches) != 1:
        details = matches[["corp_code", "corp_name", "stock_code"]].to_dict("records") if len(matches) else []
        raise RuntimeError(
            f"종목코드 {TARGET_STOCK_CODE}인 씨어스 법인을 정확히 하나 찾지 못했습니다. "
            f"검색 결과: {details}"
        )
    chosen = matches.iloc[0]
    if "씨어스" not in chosen["corp_name"]:
        raise RuntimeError(
            f"종목코드 {TARGET_STOCK_CODE}의 법인명이 예상과 다릅니다: {chosen['corp_name']}"
        )
    result = {
        "corp_code": str(chosen.corp_code).zfill(8),
        "corp_name": chosen.corp_name,
        "stock_code": TARGET_STOCK_CODE,
        "matched_at": datetime.now().isoformat(timespec="seconds"),
    }
    (DATA / "company_match.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"Verified DART company: {result['corp_name']} "
        f"(stock_code={result['stock_code']}, corp_code={result['corp_code']})"
    )
    return result

def get(endpoint, params=None):
    if not KEY:
        raise RuntimeError("DART_API_KEY가 없습니다. GitHub Actions Secrets를 확인하세요.")
    p = dict(params or {})
    p["crtfc_key"] = KEY
    r = requests.get(f"{BASE}/{endpoint}", params=p, timeout=60)
    r.raise_for_status()
    return r

def company_code():
    z = zipfile.ZipFile(io.BytesIO(get("corpCode.xml").content))
    df = pd.read_xml(io.BytesIO(z.read("CORPCODE.xml")), xpath=".//list", dtype=str)
    df["corp_name"] = df["corp_name"].fillna("").str.strip()
    chosen = None
    for name in COMPANY_NAME_CANDIDATES:
        exact = df[df.corp_name == name]
        if len(exact):
            chosen = exact.iloc[0]; break
    if chosen is None:
        matches = df[df.corp_name.str.contains("씨어스", na=False)]
        if len(matches): chosen = matches.iloc[0]
    if chosen is None:
        raise RuntimeError("DART 법인코드 목록에서 씨어스를 찾지 못했습니다. 정식 법인명을 확인하세요.")
    result = {"corp_code": str(chosen.corp_code).zfill(8), "corp_name": chosen.corp_name,
              "matched_at": datetime.now().isoformat(timespec="seconds")}
    (DATA / "company_match.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("DART company match:", result["corp_name"], result["corp_code"])
    return result

def get_accounts(code, year, reprt):
    params = {"corp_code": code, "bsns_year": str(year), "reprt_code": reprt, "fs_div": "CFS"}
    data = get("fnlttSinglAcntAll.json", params).json()
    if data.get("status") != "000":
        params["fs_div"] = "OFS"
        data = get("fnlttSinglAcntAll.json", params).json()
    return data.get("list", []) if data.get("status") == "000" else []

def amount(v):
    try:
        return float(str(v).replace(",", "")) if str(v).strip() not in ("", "-", "None") else None
    except Exception:
        return None

def main():
    co = company_code()
    now_year = datetime.now().year
    rows = []
    for year in range(START_YEAR, now_year + 1):
        for category, codes in REPORTS.items():
            for reprt in codes:
                for a in get_accounts(co["corp_code"], year, reprt):
                    rows.append({"year": year, "category": category, "report_code": reprt,
                      "statement": a.get("sj_nm"), "account_id": a.get("account_id"),
                      "account": a.get("account_nm"), "current_period": a.get("thstrm_nm"),
                      "amount": amount(a.get("thstrm_amount")), "currency": a.get("currency"),
                      "previous_period": a.get("frmtrm_nm"), "previous_amount": amount(a.get("frmtrm_amount"))})
    df = pd.DataFrame(rows, columns=["year","category","report_code","statement","account_id","account","current_period","amount","currency","previous_period","previous_amount"])
    df.to_csv(DATA / "financial_accounts.csv", index=False, encoding="utf-8-sig")
    def find(y, cat, terms):
        part = df[(df.year == y) & (df.category == cat)]
        for term in terms:
            m = part[part.account.fillna("").str.contains(term, regex=False)]
            if len(m) and pd.notna(m.iloc[0].amount): return float(m.iloc[0].amount)
        return None
    ratios = []
    termmap = {"assets":["자산총계"], "liabilities":["부채총계"], "equity":["자본총계"],
               "revenue":["매출액","영업수익","수익(매출액)"], "operating_profit":["영업이익"],
               "net_income":["당기순이익","당기순손익"]}
    for (y, cat), _ in df.groupby(["year","category"]):
        v = {k: find(int(y), cat, terms) for k, terms in termmap.items()}
        v["debt_ratio_pct"] = v["liabilities"]/v["assets"]*100 if v["liabilities"] is not None and v["assets"] else None
        v["equity_ratio_pct"] = v["equity"]/v["assets"]*100 if v["equity"] is not None and v["assets"] else None
        v["operating_margin_pct"] = v["operating_profit"]/v["revenue"]*100 if v["operating_profit"] is not None and v["revenue"] else None
        v["net_margin_pct"] = v["net_income"]/v["revenue"]*100 if v["net_income"] is not None and v["revenue"] else None
        ratios.append({"year":int(y),"category":cat,**v})
    rdf = pd.DataFrame(ratios)
    rdf.to_csv(DATA / "financial_ratios.csv", index=False, encoding="utf-8-sig")
    filings = []
    # Report-list endpoint is included to preserve source report links/metadata.
    for year in range(START_YEAR, now_year + 1):
        try:
            data = get("list.json", {"corp_code":co["corp_code"],"bgn_de":f"{year}0101","end_de":f"{year}1231","pblntf_ty":"A","page_no":1,"page_count":100}).json()
            for item in data.get("list", []):
                nm = item.get("report_nm", "")
                if any(t in nm for t in ["사업보고서","반기보고서","분기보고서"]):
                    filings.append(item)
        except Exception as e:
            print("filing list warning", year, str(e))
    pd.DataFrame(filings).to_csv(DATA / "filings.csv", index=False, encoding="utf-8-sig")
    payload = {"company":co,"updated_at":datetime.now().isoformat(timespec="seconds"),
      "accounts":df.where(pd.notna(df),None).to_dict("records"),
      "ratios":rdf.where(pd.notna(rdf),None).to_dict("records"),"filings":filings}
    (DATA / "dashboard_data.json").write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"Updated {len(rows)} account rows; {len(filings)} filing metadata rows.")

if __name__ == "__main__":
    main()
