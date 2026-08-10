# 🇹🇿 Data za Tanzania — Mikoa, Wilaya na Shule

Data hizi zimetolewa kutoka mfumo (field_management / transfer app) tarehe **4 Agosti 2026**.

## 📊 Ukubwa wa data

| Aina | Idadi |
|---|---|
| Mikoa | 26 |
| Wilaya | 188 |
| Shule | 25,489 (Msingi 17,201 + Sekondari ~4,264 + zingine) |

## 📁 Files

### Excel (rahisi kwa watu)
- **`Tanzania_Mikoa_Wilaya_Shule.xlsx`** — sheets 3:
  - **Mikoa** — mkoa + idadi ya wilaya na shule
  - **Wilaya** — wilaya + mkoa wake + idadi ya shule
  - **Shule** — kila shule ikiwa na Mkoa, Wilaya, Aina (Msingi/Sekondari), Code, Umiliki, Mkuu wa Shule, Simu

### CSV (rahisi kwa Excel/Google Sheets/DB)
- `csv/regions.csv` — id, name
- `csv/districts.csv` — id, name, region
- `csv/schools.csv` — school_name, school_code, region, district, level, ownership

### JSON (rahisi kwa programmers/API)
- `json/regions.json` — id, name
- `json/districts.json` — id, name, region_id, region_name
- `json/schools.json` — id, name, school_code, district_id, district_name, region_id, region_name, level, ownership, head_name, head_phone, latitude, longitude, address

## ℹ️ Maelezo
- **school_code** (e.g. S.0106 / P.4567) inapatikana kwa shule ~4,000; shule nyingine (za awali 21,465) hazina code.
- **ownership**: `government` (Serikali) / `private` (Binafsi) — inapatikana kwa sehemu ya shule tu.
- **head_name / head_phone**: inapatikana kwa sehemu ya shule tu.
- **level**: `Primary` (Msingi) / `Secondary` (Sekondari).

---
*Imetolewa na mfumo wa Teacher Transfer / Field Management System.*
