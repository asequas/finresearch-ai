# Valuation reference data

`damodaran_us_industries_2026.csv` is converted from Aswath Damodaran's **"Levered and Unlevered Betas by Industry"
(US)** dataset, `betas.xls`, sheet "Industry Averages", dated 2026-01-05. The source page is
https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datacurrent.html. Columns are kept as published; numbers are
rounded to 6 decimal places.

The synthetic-rating spreads in `backend/valuation/reference.py` come from his `ratings.xls` ("Start here Ratings
sheet", January 2026 update). The equity risk premium is his implied ERP for the S&P 500, as shown on his home
page.

Terms: Damodaran describes his data as free to use with "no strings attached" and appreciates attribution. With
thanks to Professor Damodaran.

Refresh once a year, after his January update:
1. Download `betas.xls`.
2. Re-run the conversion in a scratch venv with `xlrd` (not a project dependency).
3. Bump `INDUSTRY_DATA_DATE` in `reference.py`.
