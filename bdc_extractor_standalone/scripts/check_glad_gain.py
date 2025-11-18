#!/usr/bin/env python3
import pandas as pd

for ticker, filename in [('GLAD', 'GLAD_Gladstone_Capital_Corp_investments.csv'), ('GAIN', 'GAIN_Gladstone_Investment_Corp_investments.csv')]:
    try:
        df = pd.read_csv(f'output/{filename}')
        total = len(df)
        missing_acq = df['acquisition_date'].isna().sum()
        missing_mat = df['maturity_date'].isna().sum()
        with_dates = df[df['acquisition_date'].notna() | df['maturity_date'].notna()].shape[0]
        print(f"{ticker}: {total} total, missing acq: {missing_acq}, missing mat: {missing_mat}, with dates: {with_dates}")
    except Exception as e:
        print(f"{ticker}: Error - {e}")



