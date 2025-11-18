import argparse
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd


def pct_to_float(value) -> Optional[float]:
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        if value.endswith("%"):
            value = value[:-1]
        try:
            return float(value)
        except ValueError:
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def format_currency(value: float) -> str:
    return f"{value:,.2f}"


def summarize_csv(csv_path: Path, verbose: bool = True) -> Dict[str, Any]:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    df = pd.read_csv(csv_path)

    numeric_columns = ["principal_amount", "cost", "fair_value"]
    for col in numeric_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        else:
            df[col] = 0.0

    rate_columns = ["interest_rate", "spread", "floor_rate", "pik_rate"]
    for col in rate_columns:
        if col not in df.columns:
            df[col] = None
        df[f"{col}_pct"] = df[col].apply(pct_to_float)

    if "investment_type" not in df.columns:
        df["investment_type"] = "Unknown"

    for date_col in ["acquisition_date", "maturity_date"]:
        if date_col not in df.columns:
            df[date_col] = pd.NaT
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")

    unknown_mask = (
        df["investment_type"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.lower()
        .eq("unknown")
    )
    missing_type_mask = (
        df["investment_type"].isna()
        | (df["investment_type"].astype(str).str.strip() == "")
    )

    def weighted_average(rate_col: str) -> Optional[float]:
        series = df[rate_col].dropna()
        if series.empty:
            return None
        weights = df.loc[series.index, "principal_amount"]
        nonzero = weights > 0
        if not nonzero.any():
            return None
        series = series[nonzero]
        weights = weights[nonzero]
        return (weights * series).sum() / weights.sum()

    summary = {
        "file": csv_path.name,
        "ticker": csv_path.stem.split("_")[0],
        "positions": int(df.shape[0]),
        "total_principal": df["principal_amount"].sum(),
        "total_cost": df["cost"].sum(),
        "total_fair_value": df["fair_value"].sum(),
        "unknown_positions": int(unknown_mask.sum()),
        "missing_investment_type": int(missing_type_mask.sum()),
        "missing_acquisition_dates": int(df["acquisition_date"].isna().sum()),
        "missing_maturity_dates": int(df["maturity_date"].isna().sum()),
        "acquisition_start": df["acquisition_date"].min(),
        "acquisition_end": df["acquisition_date"].max(),
        "maturity_start": df["maturity_date"].min(),
        "maturity_end": df["maturity_date"].max(),
        "weighted_interest_rate": weighted_average("interest_rate_pct"),
        "weighted_spread": weighted_average("spread_pct"),
        "weighted_floor_rate": weighted_average("floor_rate_pct"),
        "weighted_pik_rate": weighted_average("pik_rate_pct"),
    }

    if verbose:
        print(f"\n=== {csv_path.name} ===")
        print("Summary Stats:")
        print(f"  positions: {summary['positions']}")
        print(f"  total_principal: {format_currency(summary['total_principal'])}")
        print(f"  total_cost: {format_currency(summary['total_cost'])}")
        print(f"  total_fair_value: {format_currency(summary['total_fair_value'])}")

        print("\nWeighted Average Rates (principal-weighted):")
        for key, label in [
            ("weighted_interest_rate", "interest_rate"),
            ("weighted_spread", "spread"),
            ("weighted_floor_rate", "floor_rate"),
            ("weighted_pik_rate", "pik_rate"),
        ]:
            value = summary[key]
            if value is not None:
                print(f"  {label}: {value:.2f}%")

        print("\nDate Coverage:")
        acq_min = summary["acquisition_start"]
        acq_max = summary["acquisition_end"]
        mat_min = summary["maturity_start"]
        mat_max = summary["maturity_end"]
        print(
            "  acquisition_date range: "
            f"{acq_min.date() if pd.notna(acq_min) else None} -> "
            f"{acq_max.date() if pd.notna(acq_max) else None}"
        )
        print(
            "  maturity_date range: "
            f"{mat_min.date() if pd.notna(mat_min) else None} -> "
            f"{mat_max.date() if pd.notna(mat_max) else None}"
        )

        by_type = (
            df.groupby("investment_type")[["principal_amount", "cost", "fair_value"]]
            .sum()
            .sort_values("principal_amount", ascending=False)
        )
        print("\nTotals by investment type:")
        print(by_type.to_string(float_format=lambda x: f"{x:,.2f}"))

        if summary["unknown_positions"] or summary["missing_investment_type"]:
            print(
                f"\n⚠️  Unknown investment_type rows: {summary['unknown_positions']}, "
                f"blank investment_type rows: {summary['missing_investment_type']}"
            )
        if summary["missing_acquisition_dates"] or summary["missing_maturity_dates"]:
            print(
                f"⚠️  Missing acquisition dates: {summary['missing_acquisition_dates']}, "
                f"missing maturity dates: {summary['missing_maturity_dates']}"
            )

    return summary


def summarize_directory(directory: Path) -> None:
    csv_files = sorted(directory.glob("*_investments.csv"))
    if not csv_files:
        raise FileNotFoundError(f"No *_investments.csv files found in {directory}")

    summaries = [summarize_csv(csv_path, verbose=False) for csv_path in csv_files]
    overview = pd.DataFrame(summaries)

    def fmt_date(series_name: str) -> pd.Series:
        return overview[series_name].apply(
            lambda x: x.date().isoformat() if pd.notna(x) else None
        )

    overview_display = overview[
        [
            "ticker",
            "positions",
            "total_principal",
            "total_fair_value",
            "unknown_positions",
            "missing_investment_type",
            "missing_acquisition_dates",
            "missing_maturity_dates",
        ]
    ].copy()
    overview_display["total_principal"] = overview_display["total_principal"].apply(
        format_currency
    )
    overview_display["total_fair_value"] = overview_display["total_fair_value"].apply(
        format_currency
    )
    overview_display["acquisition_start"] = fmt_date("acquisition_start")
    overview_display["acquisition_end"] = fmt_date("acquisition_end")
    overview_display["maturity_start"] = fmt_date("maturity_start")
    overview_display["maturity_end"] = fmt_date("maturity_end")

    print("\n=== Portfolio Overview ===")
    print(
        overview_display.to_string(
            index=False,
            justify="left",
        )
    )

    needs_work = overview[
        (overview["unknown_positions"] > 0)
        | (overview["missing_investment_type"] > 0)
        | (overview["missing_acquisition_dates"] > 0)
        | (overview["missing_maturity_dates"] > 0)
    ]
    if not needs_work.empty:
        print("\n=== Files Needing Follow-up ===")
        print(
            needs_work[
                [
                    "ticker",
                    "unknown_positions",
                    "missing_investment_type",
                    "missing_acquisition_dates",
                    "missing_maturity_dates",
                ]
            ].to_string(index=False)
        )
    else:
        print("\nAll files show complete investment_type and date coverage.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarize an investments CSV or directory of CSVs."
    )
    parser.add_argument(
        "path",
        type=Path,
        help="Path to an investments CSV file or directory containing *_investments.csv files.",
    )
    args = parser.parse_args()

    if args.path.is_dir():
        summarize_directory(args.path)
    else:
        summarize_csv(args.path, verbose=True)


if __name__ == "__main__":
    main()

