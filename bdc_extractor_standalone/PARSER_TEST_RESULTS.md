# BDC Parser Test Results

Generated: 2025-11-10 15:18:55

## Summary

- **Total Parsers Tested**: 26
- **[OK] Working**: 26
- **[REDO] Needs Redo**: 23
- **[ERROR] Errors**: 0
- **[NO DATA] No Data**: 0

- **Average Time**: 18.3s

## Thresholds

- **Max Time**: 60s (parsers taking longer need redo)
- **Min Coverage**: 80% (parsers with lower coverage need redo)

---

## Parser Results

### [REDO] Needs Redo

| Ticker | Name | Time (s) | Investments | Status | Reasons |
|--------|------|----------|-------------|--------|----------|
| NCDL | Nuveen Churchill Direct Lending Corp | 7.8 | 1482 | success | Low overall coverage: 62.5% (need 80%) |
| CION | CION Investment Corp | 8.2 | 704 | success | Low overall coverage: 68.6% (need 80%) |
| CSWC | Capital Southwest Corp | 8.6 | 946 | success | Low overall coverage: 69.9% (need 80%) |
| CGBD | TCG BDC Inc | 9.6 | 907 | success | Low overall coverage: 65.9% (need 80%) |
| OCSL | Oaktree Specialty Lending Corp | 10.4 | 1169 | success | Low overall coverage: 72.0% (need 80%) |
| OBDC | Blue Owl Capital Corp | 11.7 | 1135 | success | Low overall coverage: 62.6% (need 80%) |
| MSDL | Morgan Stanley Direct Lending Fund | 12.8 | 2076 | success | Low overall coverage: 69.8% (need 80%) |
| FDUS | Fidus Investment Corp | 13.2 | 612 | success | Low overall coverage: 76.0% (need 80%) |
| BBDC | Barings BDC Inc | 13.9 | 1913 | success | Low overall coverage: 72.7% (need 80%) |
| MAIN | Main Street Capital Corp | 14.3 | 1114 | success | Low overall coverage: 51.7% (need 80%) |
| PSEC | Prospect Capital Corp | 14.5 | 582 | success | Low overall coverage: 69.0% (need 80%) |
| PFLT | PennantPark Floating Rate Capital Ltd | 14.7 | 606 | success | Low overall coverage: 67.8% (need 80%) |
| NMFC | New Mountain Finance Corp | 14.8 | 1527 | success | Low overall coverage: 73.2% (need 80%) |
| BCSF | Bain Capital Specialty Finance Inc | 15.1 | 892 | success | Low overall coverage: 79.7% (need 80%) |
| GBDC | Golub Capital BDC Inc | 15.3 | 1862 | success | Low overall coverage: 68.7% (need 80%) |
| GAIN | Gladstone Investment Corp | 15.6 | 190 | success | Low overall coverage: 67.1% (need 80%) |
| TCPC | Blackrock TCP Capital Corp | 16.2 | 732 | success | Low overall coverage: 76.9% (need 80%) |
| TRIN | Trinity Capital Inc | 18.3 | 1193 | success | Low overall coverage: 62.8% (need 80%) |
| MFIC | Midcap Financial Investment Corp | 21.3 | 1551 | success | Low overall coverage: 63.4% (need 80%) |
| TSLX | Sixth Street Specialty Lending Inc | 31.5 | 576 | success | Low overall coverage: 76.9% (need 80%) |
| HTGC | Hercules Capital Inc | 32.7 | 1115 | success | fair_value coverage only 48.7% (need 80%); Low overall coverage: 70.4% (need 80%) |
| FSK | FS KKR Capital Corp | 33.8 | 1902 | success | Low overall coverage: 68.7% (need 80%) |
| ARCC | Ares Capital Corporation | 57.5 | 681 | success | fair_value coverage only 73.1% (need 80%); Low overall coverage: 65.2% (need 80%) |

### [OK] Working Well

| Ticker | Name | Time (s) | Investments | Coverage |
|--------|------|----------|-------------|----------|
| SLRC | SLR Investment Corp | 9.8 | 201 | 98.9% |
| GSBD | Goldman Sachs BDC Inc | 15.2 | 533 | 82.8% |
| BXSL | Blackstone Secured Lending Fund | 38.0 | 72 | 88.4% |

---

## Detailed Results

### NCDL - Nuveen Churchill Direct Lending Corp

- **Status**: success
- **Time**: 7.8s
- **Investments**: 1482
- **Parser Module**: ncdl_parser
- **[REDO] Needs Redo**: Yes
- **Reasons**: Low overall coverage: 62.5% (need 80%)

**Field Coverage:**

| Field | Coverage | Missing |
|-------|----------|----------|
| company_name | 100.0% | 0 |
| investment_type | 74.6% | 377 |
| industry | 100.0% | 0 |
| fair_value | 100.0% | 0 |
| cost | 100.0% | 0 |
| principal_amount | 88.2% | 175 |
| interest_rate | 0.0% | 1482 |
| acquisition_date | 0.0% | 1482 |
| maturity_date | 0.0% | 1482 |

---

### CION - CION Investment Corp

- **Status**: success
- **Time**: 8.2s
- **Investments**: 704
- **Parser Module**: cion_parser
- **[REDO] Needs Redo**: Yes
- **Reasons**: Low overall coverage: 68.6% (need 80%)

**Field Coverage:**

| Field | Coverage | Missing |
|-------|----------|----------|
| company_name | 100.0% | 0 |
| investment_type | 99.9% | 1 |
| industry | 100.0% | 0 |
| fair_value | 93.3% | 47 |
| cost | 76.4% | 166 |
| principal_amount | 60.9% | 275 |
| interest_rate | 57.4% | 300 |
| acquisition_date | 0.0% | 704 |
| maturity_date | 29.4% | 497 |

---

### CSWC - Capital Southwest Corp

- **Status**: success
- **Time**: 8.6s
- **Investments**: 946
- **Parser Module**: cswc_parser
- **[REDO] Needs Redo**: Yes
- **Reasons**: Low overall coverage: 69.9% (need 80%)

**Field Coverage:**

| Field | Coverage | Missing |
|-------|----------|----------|
| company_name | 100.0% | 0 |
| investment_type | 99.9% | 1 |
| industry | 100.0% | 0 |
| fair_value | 100.0% | 0 |
| cost | 96.4% | 34 |
| principal_amount | 69.5% | 289 |
| interest_rate | 63.1% | 349 |
| acquisition_date | 0.0% | 946 |
| maturity_date | 0.0% | 946 |

---

### CGBD - TCG BDC Inc

- **Status**: success
- **Time**: 9.6s
- **Investments**: 907
- **Parser Module**: cgbd_parser
- **[REDO] Needs Redo**: Yes
- **Reasons**: Low overall coverage: 65.9% (need 80%)

**Field Coverage:**

| Field | Coverage | Missing |
|-------|----------|----------|
| company_name | 100.0% | 0 |
| investment_type | 99.6% | 4 |
| industry | 100.0% | 0 |
| fair_value | 100.0% | 0 |
| cost | 71.1% | 262 |
| principal_amount | 60.6% | 357 |
| interest_rate | 62.2% | 343 |
| acquisition_date | 0.0% | 907 |
| maturity_date | 0.0% | 907 |

---

### OCSL - Oaktree Specialty Lending Corp

- **Status**: success
- **Time**: 10.4s
- **Investments**: 1169
- **Parser Module**: ocsl_parser
- **[REDO] Needs Redo**: Yes
- **Reasons**: Low overall coverage: 72.0% (need 80%)

**Field Coverage:**

| Field | Coverage | Missing |
|-------|----------|----------|
| company_name | 100.0% | 0 |
| investment_type | 100.0% | 0 |
| industry | 92.1% | 92 |
| fair_value | 100.0% | 0 |
| cost | 100.0% | 0 |
| principal_amount | 86.6% | 157 |
| interest_rate | 69.5% | 357 |
| acquisition_date | 0.0% | 1169 |
| maturity_date | 0.0% | 1169 |

---

### OBDC - Blue Owl Capital Corp

- **Status**: success
- **Time**: 11.7s
- **Investments**: 1135
- **Parser Module**: obdc_parser
- **[REDO] Needs Redo**: Yes
- **Reasons**: Low overall coverage: 62.6% (need 80%)

**Field Coverage:**

| Field | Coverage | Missing |
|-------|----------|----------|
| company_name | 100.0% | 0 |
| investment_type | 97.8% | 25 |
| industry | 100.0% | 0 |
| fair_value | 100.0% | 0 |
| cost | 84.7% | 174 |
| principal_amount | 67.1% | 373 |
| interest_rate | 13.8% | 978 |
| acquisition_date | 0.0% | 1135 |
| maturity_date | 0.0% | 1135 |

---

### MSDL - Morgan Stanley Direct Lending Fund

- **Status**: success
- **Time**: 12.8s
- **Investments**: 2076
- **Parser Module**: msdl_parser
- **[REDO] Needs Redo**: Yes
- **Reasons**: Low overall coverage: 69.8% (need 80%)

**Field Coverage:**

| Field | Coverage | Missing |
|-------|----------|----------|
| company_name | 100.0% | 0 |
| investment_type | 94.8% | 108 |
| industry | 100.0% | 0 |
| fair_value | 100.0% | 1 |
| cost | 81.1% | 392 |
| principal_amount | 76.1% | 497 |
| interest_rate | 76.3% | 493 |
| acquisition_date | 0.0% | 2076 |
| maturity_date | 0.0% | 2076 |

---

### FDUS - Fidus Investment Corp

- **Status**: success
- **Time**: 13.2s
- **Investments**: 612
- **Parser Module**: fdus_parser
- **[REDO] Needs Redo**: Yes
- **Reasons**: Low overall coverage: 76.0% (need 80%)

**Field Coverage:**

| Field | Coverage | Missing |
|-------|----------|----------|
| company_name | 100.0% | 0 |
| investment_type | 83.5% | 101 |
| industry | 100.0% | 0 |
| fair_value | 90.7% | 57 |
| cost | 98.2% | 11 |
| principal_amount | 39.7% | 369 |
| interest_rate | 41.7% | 357 |
| acquisition_date | 88.2% | 72 |
| maturity_date | 42.3% | 353 |

---

### BBDC - Barings BDC Inc

- **Status**: success
- **Time**: 13.9s
- **Investments**: 1913
- **Parser Module**: bbdc_parser
- **[REDO] Needs Redo**: Yes
- **Reasons**: Low overall coverage: 72.7% (need 80%)

**Field Coverage:**

| Field | Coverage | Missing |
|-------|----------|----------|
| company_name | 100.0% | 0 |
| investment_type | 100.0% | 0 |
| industry | 100.0% | 0 |
| fair_value | 100.0% | 0 |
| cost | 98.4% | 31 |
| principal_amount | 77.2% | 436 |
| interest_rate | 78.9% | 404 |
| acquisition_date | 0.0% | 1913 |
| maturity_date | 0.0% | 1913 |

---

### MAIN - Main Street Capital Corp

- **Status**: success
- **Time**: 14.3s
- **Investments**: 1114
- **Parser Module**: main_parser
- **[REDO] Needs Redo**: Yes
- **Reasons**: Low overall coverage: 51.7% (need 80%)

**Field Coverage:**

| Field | Coverage | Missing |
|-------|----------|----------|
| company_name | 100.0% | 0 |
| investment_type | 99.2% | 9 |
| industry | 11.8% | 983 |
| fair_value | 90.0% | 111 |
| cost | 93.6% | 71 |
| principal_amount | 33.0% | 746 |
| interest_rate | 37.8% | 693 |
| acquisition_date | 0.0% | 1114 |
| maturity_date | 0.0% | 1114 |

---

### PSEC - Prospect Capital Corp

- **Status**: success
- **Time**: 14.5s
- **Investments**: 582
- **Parser Module**: psec_parser
- **[REDO] Needs Redo**: Yes
- **Reasons**: Low overall coverage: 69.0% (need 80%)

**Field Coverage:**

| Field | Coverage | Missing |
|-------|----------|----------|
| company_name | 100.0% | 0 |
| investment_type | 95.5% | 26 |
| industry | 100.0% | 0 |
| fair_value | 100.0% | 0 |
| cost | 86.8% | 77 |
| principal_amount | 66.7% | 194 |
| interest_rate | 72.2% | 162 |
| acquisition_date | 0.0% | 582 |
| maturity_date | 0.0% | 582 |

---

### PFLT - PennantPark Floating Rate Capital Ltd

- **Status**: success
- **Time**: 14.7s
- **Investments**: 606
- **Parser Module**: pflt_parser
- **[REDO] Needs Redo**: Yes
- **Reasons**: Low overall coverage: 67.8% (need 80%)

**Field Coverage:**

| Field | Coverage | Missing |
|-------|----------|----------|
| company_name | 100.0% | 0 |
| investment_type | 93.4% | 40 |
| industry | 100.0% | 0 |
| fair_value | 93.6% | 39 |
| cost | 88.0% | 73 |
| principal_amount | 73.6% | 160 |
| interest_rate | 61.6% | 233 |
| acquisition_date | 0.0% | 606 |
| maturity_date | 0.0% | 606 |

---

### NMFC - New Mountain Finance Corp

- **Status**: success
- **Time**: 14.8s
- **Investments**: 1527
- **Parser Module**: nmfc_parser
- **[REDO] Needs Redo**: Yes
- **Reasons**: Low overall coverage: 73.2% (need 80%)

**Field Coverage:**

| Field | Coverage | Missing |
|-------|----------|----------|
| company_name | 100.0% | 0 |
| investment_type | 99.1% | 14 |
| industry | 100.0% | 0 |
| fair_value | 98.4% | 25 |
| cost | 98.4% | 25 |
| principal_amount | 93.6% | 97 |
| interest_rate | 69.2% | 470 |
| acquisition_date | 0.0% | 1527 |
| maturity_date | 0.0% | 1527 |

---

### BCSF - Bain Capital Specialty Finance Inc

- **Status**: success
- **Time**: 15.1s
- **Investments**: 892
- **Parser Module**: bcsf_parser
- **[REDO] Needs Redo**: Yes
- **Reasons**: Low overall coverage: 79.7% (need 80%)

**Field Coverage:**

| Field | Coverage | Missing |
|-------|----------|----------|
| company_name | 100.0% | 0 |
| investment_type | 98.9% | 10 |
| industry | 100.0% | 0 |
| fair_value | 90.9% | 81 |
| cost | 97.1% | 26 |
| principal_amount | 84.8% | 136 |
| interest_rate | 66.4% | 300 |
| acquisition_date | 0.0% | 892 |
| maturity_date | 79.7% | 181 |

---

### GBDC - Golub Capital BDC Inc

- **Status**: success
- **Time**: 15.3s
- **Investments**: 1862
- **Parser Module**: gbdc_parser
- **[REDO] Needs Redo**: Yes
- **Reasons**: Low overall coverage: 68.7% (need 80%)

**Field Coverage:**

| Field | Coverage | Missing |
|-------|----------|----------|
| company_name | 100.0% | 0 |
| investment_type | 98.4% | 30 |
| industry | 100.0% | 0 |
| fair_value | 100.0% | 0 |
| cost | 98.1% | 35 |
| principal_amount | 59.8% | 748 |
| interest_rate | 62.2% | 704 |
| acquisition_date | 0.0% | 1862 |
| maturity_date | 0.0% | 1862 |

---

### GAIN - Gladstone Investment Corp

- **Status**: success
- **Time**: 15.6s
- **Investments**: 190
- **Parser Module**: gain_parser
- **[REDO] Needs Redo**: Yes
- **Reasons**: Low overall coverage: 67.1% (need 80%)

**Field Coverage:**

| Field | Coverage | Missing |
|-------|----------|----------|
| company_name | 100.0% | 0 |
| investment_type | 91.1% | 17 |
| industry | 100.0% | 0 |
| fair_value | 100.0% | 0 |
| cost | 99.5% | 1 |
| principal_amount | 56.8% | 82 |
| interest_rate | 56.8% | 82 |
| acquisition_date | 0.0% | 190 |
| maturity_date | 0.0% | 190 |

---

### TCPC - Blackrock TCP Capital Corp

- **Status**: success
- **Time**: 16.2s
- **Investments**: 732
- **Parser Module**: tcpc_parser
- **[REDO] Needs Redo**: Yes
- **Reasons**: Low overall coverage: 76.9% (need 80%)

**Field Coverage:**

| Field | Coverage | Missing |
|-------|----------|----------|
| company_name | 100.0% | 0 |
| investment_type | 52.5% | 348 |
| industry | 98.2% | 13 |
| fair_value | 100.0% | 0 |
| cost | 100.0% | 0 |
| principal_amount | 80.1% | 146 |
| interest_rate | 80.9% | 140 |
| acquisition_date | 0.0% | 732 |
| maturity_date | 80.1% | 146 |

---

### TRIN - Trinity Capital Inc

- **Status**: success
- **Time**: 18.3s
- **Investments**: 1193
- **Parser Module**: trin_parser
- **[REDO] Needs Redo**: Yes
- **Reasons**: Low overall coverage: 62.8% (need 80%)

**Field Coverage:**

| Field | Coverage | Missing |
|-------|----------|----------|
| company_name | 100.0% | 0 |
| investment_type | 98.0% | 24 |
| industry | 100.0% | 0 |
| fair_value | 91.6% | 100 |
| cost | 95.1% | 58 |
| principal_amount | 42.6% | 685 |
| interest_rate | 38.3% | 736 |
| acquisition_date | 0.0% | 1193 |
| maturity_date | 0.0% | 1193 |

---

### MFIC - Midcap Financial Investment Corp

- **Status**: success
- **Time**: 21.3s
- **Investments**: 1551
- **Parser Module**: mfic_parser
- **[REDO] Needs Redo**: Yes
- **Reasons**: Low overall coverage: 63.4% (need 80%)

**Field Coverage:**

| Field | Coverage | Missing |
|-------|----------|----------|
| company_name | 100.0% | 0 |
| investment_type | 65.0% | 543 |
| industry | 100.0% | 0 |
| fair_value | 88.5% | 179 |
| cost | 86.8% | 205 |
| principal_amount | 38.0% | 962 |
| interest_rate | 45.6% | 843 |
| acquisition_date | 0.0% | 1551 |
| maturity_date | 46.4% | 832 |

---

### TSLX - Sixth Street Specialty Lending Inc

- **Status**: success
- **Time**: 31.5s
- **Investments**: 576
- **Parser Module**: tslx_parser
- **[REDO] Needs Redo**: Yes
- **Reasons**: Low overall coverage: 76.9% (need 80%)

**Field Coverage:**

| Field | Coverage | Missing |
|-------|----------|----------|
| company_name | 100.0% | 0 |
| investment_type | 62.7% | 215 |
| industry | 100.0% | 0 |
| fair_value | 98.4% | 9 |
| cost | 97.6% | 14 |
| principal_amount | 0.0% | 576 |
| interest_rate | 70.3% | 171 |
| acquisition_date | 94.3% | 33 |
| maturity_date | 68.6% | 181 |

---

### HTGC - Hercules Capital Inc

- **Status**: success
- **Time**: 32.7s
- **Investments**: 1115
- **Parser Module**: htgc_parser
- **[REDO] Needs Redo**: Yes
- **Reasons**: fair_value coverage only 48.7% (need 80%); Low overall coverage: 70.4% (need 80%)

**Field Coverage:**

| Field | Coverage | Missing |
|-------|----------|----------|
| company_name | 100.0% | 0 |
| investment_type | 94.9% | 57 |
| industry | 100.0% | 0 |
| fair_value | 48.7% | 572 |
| cost | 95.4% | 51 |
| principal_amount | 100.0% | 0 |
| interest_rate | 2.9% | 1083 |
| acquisition_date | 0.0% | 1115 |
| maturity_date | 91.5% | 95 |

---

### FSK - FS KKR Capital Corp

- **Status**: success
- **Time**: 33.8s
- **Investments**: 1902
- **Parser Module**: fsk_parser
- **[REDO] Needs Redo**: Yes
- **Reasons**: Low overall coverage: 68.7% (need 80%)

**Field Coverage:**

| Field | Coverage | Missing |
|-------|----------|----------|
| company_name | 100.0% | 0 |
| investment_type | 94.8% | 99 |
| industry | 100.0% | 0 |
| fair_value | 98.3% | 32 |
| cost | 85.1% | 284 |
| principal_amount | 72.9% | 516 |
| interest_rate | 67.0% | 628 |
| acquisition_date | 0.0% | 1902 |
| maturity_date | 0.0% | 1902 |

---

### ARCC - Ares Capital Corporation

- **Status**: success
- **Time**: 57.5s
- **Investments**: 681
- **Parser Module**: auto-detected
- **[REDO] Needs Redo**: Yes
- **Reasons**: fair_value coverage only 73.1% (need 80%); Low overall coverage: 65.2% (need 80%)

**Field Coverage:**

| Field | Coverage | Missing |
|-------|----------|----------|
| company_name | 100.0% | 0 |
| investment_type | 63.6% | 248 |
| industry | 100.0% | 0 |
| fair_value | 73.1% | 183 |
| cost | 78.0% | 150 |
| principal_amount | 60.5% | 269 |
| interest_rate | 25.8% | 505 |
| acquisition_date | 63.6% | 248 |
| maturity_date | 22.2% | 530 |

---

### SLRC - SLR Investment Corp

- **Status**: success
- **Time**: 9.8s
- **Investments**: 201
- **Parser Module**: slrc_parser
- **[OK] Status**: Working well

**Field Coverage:**

| Field | Coverage | Missing |
|-------|----------|----------|
| company_name | 100.0% | 0 |
| investment_type | 100.0% | 0 |
| industry | 100.0% | 0 |
| fair_value | 100.0% | 0 |
| cost | 100.0% | 0 |
| principal_amount | 98.5% | 3 |
| interest_rate | 96.0% | 8 |
| acquisition_date | 100.0% | 0 |
| maturity_date | 96.0% | 8 |

---

### GSBD - Goldman Sachs BDC Inc

- **Status**: success
- **Time**: 15.2s
- **Investments**: 533
- **Parser Module**: gsbd_parser
- **[OK] Status**: Working well

**Field Coverage:**

| Field | Coverage | Missing |
|-------|----------|----------|
| company_name | 100.0% | 0 |
| investment_type | 97.4% | 14 |
| industry | 100.0% | 0 |
| fair_value | 95.9% | 22 |
| cost | 97.6% | 13 |
| principal_amount | 88.9% | 59 |
| interest_rate | 66.4% | 179 |
| acquisition_date | 9.8% | 481 |
| maturity_date | 89.3% | 57 |

---

### BXSL - Blackstone Secured Lending Fund

- **Status**: success
- **Time**: 38.0s
- **Investments**: 72
- **Parser Module**: bxsl_parser
- **[OK] Status**: Working well

**Field Coverage:**

| Field | Coverage | Missing |
|-------|----------|----------|
| company_name | 100.0% | 0 |
| investment_type | 88.9% | 8 |
| industry | 97.2% | 2 |
| fair_value | 88.9% | 8 |
| cost | 94.4% | 4 |
| principal_amount | 76.4% | 17 |
| interest_rate | 83.3% | 12 |
| acquisition_date | 83.3% | 12 |
| maturity_date | 83.3% | 12 |

---

