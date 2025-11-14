import { useMemo } from 'react';
import { useBDCFinancialsMultiple } from '../api/hooks';

type Props = {
  ticker?: string;
  periods?: string[]; // Support multiple periods
  name?: string;
  mode?: 'overview' | 'historical'; // 'overview' shows key metrics + latest statements, 'historical' shows all line items across periods
};

function fmt(n: unknown) {
  if (n == null) return '';
  const v = Number(n);
  if (Number.isNaN(v)) return '';
  return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function formatLabel(label: string): string {
  if (!label) return '';
  
  // If it already has proper formatting (spaces, capitalization), use it
  if (label.includes(' ') && label !== label.toLowerCase()) {
    return label;
  }
  
  // Convert camelCase/PascalCase/snake_case to Title Case
  let formatted = label
    // Split on camelCase boundaries (handle multiple consecutive capitals)
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/([A-Z]+)([A-Z][a-z])/g, '$1 $2')
    // Split on underscores
    .replace(/_/g, ' ')
    // Split on numbers
    .replace(/([a-z])(\d)/g, '$1 $2')
    .replace(/(\d)([a-z])/g, '$1 $2')
    // Capitalize first letter of each word
    .split(' ')
    .map(word => {
      // Handle common abbreviations
      if (word.toLowerCase() === 'pik') return 'PIK';
      if (word.toLowerCase() === 'nav') return 'NAV';
      if (word.toLowerCase() === 'eps') return 'EPS';
      if (word.toLowerCase() === 'nii') return 'NII';
      if (word.toLowerCase() === 'fx') return 'FX';
      if (word.toLowerCase() === 'sbc') return 'SBC';
      // Capitalize first letter
      return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
    })
    .join(' ')
    .trim();
  
  // Fix common patterns
  formatted = formatted
    .replace(/\bAnd\b/gi, 'and')
    .replace(/\bOf\b/gi, 'of')
    .replace(/\bIn\b/gi, 'in')
    .replace(/\bTo\b/gi, 'to')
    .replace(/\bFor\b/gi, 'for')
    .replace(/\bThe\b/gi, 'the')
    .replace(/\bAt\b/gi, 'at')
    .replace(/\bOn\b/gi, 'on')
    .replace(/\bBy\b/gi, 'by')
    // But capitalize first word
    .replace(/^[a-z]/, (match) => match.toUpperCase());
  
  return formatted;
}

// Map raw statement labels/keys to human-friendly display names
const DISPLAY_NAME_OVERRIDES: Record<string, string> = {
  // Income Statement
  'netincomeloss': 'Net Income',
  'net income loss': 'Net Income',
  'earningspersharebasic': 'EPS (Basic)',
  'earnings per share basic': 'EPS (Basic)',
  'earningspersharediluted': 'EPS (Diluted)',
  'earnings per share diluted': 'EPS (Diluted)',
  'operatingexpenses': 'Operating Expenses',
  'operating expenses': 'Operating Expenses',
  'interestanddividendincomeoperatingpaidincash': 'Interest & Dividend Income (Cash)',
  'interest income operating paid in cash': 'Interest & Dividend Income (Cash)',
  'interestincomeoperatingpaidinkind': 'Interest Income (PIK)',
  'interest income operating paid in kind': 'Interest Income (PIK)',
  'interestanddividendincomeoperating': 'Interest & Dividend Income',
  'interest and dividend income operating': 'Interest & Dividend Income',
  'feeincome': 'Fee Income',
  'fee income': 'Fee Income',
  'grossinvestmentincomeoperating': 'Gross Investment Income',
  'gross investment income operating': 'Gross Investment Income',
  'interestexpensedebt': 'Interest Expense (Debt)',
  'debt related commitment fees and debt issuance costs': 'Debt Fees & Issuance Costs',
  'debtrelatedcommitmentfeesanddebtissuancecosts': 'Debt Fees & Issuance Costs',
  'generalandadministrativeexpense': 'General & Administrative Expense',
  'investmentincomeoperatingtaxexpensebenefit': 'Investment Income Tax (Benefit)',
  'laborandrelatedexpense': 'Labor & Related Expense',
  'employeebenefitsandsharebasedcompensation': 'Employee Benefits & SBC',
  'htgc employeecompensation': 'Employee Compensation',
  'htgc expensesallocatedtoadvisersubsidiary1': 'Expenses Allocated to Adviser Subsidiary',
  'htgc operatingexpensesnet': 'Operating Expenses, Net',
  'netinvestmentincome': 'Net Investment Income',
  'realizedinvestmentgainslosses': 'Realized Investment Gains/Losses',
  'gainslossesonextinguishmentofdebt': 'Gain/Loss on Extinguishment of Debt',
  'htgc realizedinvestmentgainslossandgainlossonextinguishmentofdebt': 'Realized Gains/Losses and Debt Extinguishment',
  'unrealizedgainlossoninvestments': 'Unrealized Gain/Loss on Investments',
  'investmentcompanyrealizedandunrealizedgainlossoninvestmentandforeigncurrency': 'Realized/Unrealized Gain/Loss incl. FX',
  'investmentcompanyinvestmentincomelosspershare': 'Investment Income/Loss per Share',
  'weightedaveragenumberofsharesoutstandingbasic': 'Weighted Avg Shares (Basic)',
  'weightedaveragenumberofdilutedsharesoutstanding': 'Weighted Avg Shares (Diluted)',
  'investmentcompanydistributiontoshareholderspershare': 'Distribution to Shareholders per Share',

  // Cash Flow Statement
  'cashcashequivalentsrestrictedcashandrestrictedcashequivalents': 'Cash & Cash Equivalents (incl. Restricted)',
  'cash flows from financing activities: (aggregated)': 'Cash Flows from Financing (Aggregated)',
  'netcashprovidedbyusedinfinancingactivities': 'Net Cash Provided by (Used in) Financing',
  'paymentsforrepurchaseofcommonstock': 'Repurchase of Common Stock',
  'cash flows from investing activities: (aggregated)': 'Cash Flows from Investing (Aggregated)',
  'netcashprovidedbyusedininvestingactivities': 'Net Cash Provided by (Used in) Investing',
  'payments to acquire businesses (aggregated)': 'Payments to Acquire Businesses',
  'cash flows from operating activities: (aggregated)': 'Cash Flows from Operating (Aggregated)',
  'netcashprovidedbyusedinoperatingactivities': 'Net Cash Provided by (Used in) Operating',
  'adjustments to reconcile net income to net cash provided by operating activities: (aggregated)': 'Adjustments to Reconcile Net Income',
  'sharebasedcompensation': 'Share-based Compensation',
  'cashcashequivalentsrestrictedcashandrestrictedcashequivalentsperiodincreasedecreaseincludingexchangerateeffect': 'Change in Cash & Equivalents (incl. FX)',
  'paymentsforpurchaseofinvestmentoperatingactivity': 'Payments for Purchase of Investments (Operating)',
  'htgc fundingassignedtoadviserfunds': 'Funding Assigned to Adviser Funds',
  'proceedsfromdispositionofinvestmentoperatingactivity': 'Proceeds from Disposition of Investments (Operating)',
  'htgc proceedsfromthesaleofdebtinvestments': 'Proceeds from Sale of Debt Investments',
  'htgc proceedsfromdispositionofinvestmentequityandwarrantsinvestmentsoperatingactivity': 'Proceeds from Sale of Equity & Warrants (Operating)',
  'unrealizedgainlossinvestmentderivativeandforeigncurrencytransactionpricechangeoperatingbeforetax': 'Unrealized Gain/Loss (Investments/Derivatives/FX) Before Tax',
  'realizedgainlossinvestmentandderivativeoperatingaftertax': 'Realized Gain/Loss (Investments/Derivatives) After Tax',
  'htgc paymentforderivativeinstrumentoperatingactivities': 'Payments for Derivative Instruments (Operating)',
  'accretionamortizationofdiscountsandpremiumsinvestments': 'Accretion/Amortization of Discounts and Premiums',
  'htgc accretionamortizationofdiscountsandpremiumsinvestmentsconvertiblenotes': 'Accretion/Amortization on Convertible Notes',
  'htgc accretionofloanexitfees': 'Accretion of Loan Exit Fees',
  'htgc changeinloanincomenetofcollections': 'Change in Loan Income (Net of Collections)',
  'htgc unearnedfeesrelatedtounfundedcommitments': 'Unearned Fees related to Unfunded Commitments',
  'amortizationoffinancingcostsanddiscounts': 'Amortization of Financing Costs and Discounts',
  'depreciationandamortization': 'Depreciation and Amortization',
  
  // Balance Sheet
  'assets': 'Assets',
  'cashandcashequivalentsatcarryingvalue': 'Cash and Cash Equivalents',
  'liabilitiesandstockholdersequity': 'Liabilities and Stockholders\' Equity',
  'liabilities': 'Liabilities',
  'totalcurrentliabilitiesaggregated': 'Total Current Liabilities',
  'retainedearningsaccumulateddeficit': 'Retained Earnings (Accumulated Deficit)',
  'stockholdersequity': 'Stockholders\' Equity',
  'commonstockvalue': 'Common Stock Value',
  'additionalpaidincapital': 'Additional Paid-in Capital',
  'investmentownedatfairvalue': 'Investments at Fair Value',
  'cashheldinforeigncurrency': 'Cash Held in Foreign Currency',
  'restrictedcash': 'Restricted Cash',
  'interestreceivable': 'Interest Receivable',
  'operatingleaserightofuseasset': 'Operating Lease Right-of-Use Asset',
  'otherassets': 'Other Assets',
  'longtermdebt': 'Long-Term Debt',
  'accountspayableandaccruedliabilitiescurrentandnoncurrent': 'Accounts Payable and Accrued Liabilities',
  'operatingleaseliability': 'Operating Lease Liability',
  'commonstocksharesoutstanding': 'Common Stock Shares Outstanding',
  'netassetvaluepershare': 'Net Asset Value per Share',
  'totalassets': 'Total Assets',
  'totalliabilities': 'Total Liabilities',
  'totalequity': 'Total Equity',
  'totalinvestments': 'Total Investments',
  'cashandcashequivalents': 'Cash and Cash Equivalents',
  
  // Cash Flow additional items
  'increasedecreaseinaccruedinterestreceivablenet': 'Increase/(Decrease) in Accrued Interest Receivable, Net',
  'increasedecreaseinotheroperatingassets': 'Increase/(Decrease) in Other Operating Assets',
  'increasedecreaseinaccruedliabilities': 'Increase/(Decrease) in Accrued Liabilities',
  'paymentstoacquireproductiveassets': 'Payments to Acquire Productive Assets',
  'proceedsfromissuanceofcommonstock': 'Proceeds from Issuance of Common Stock',
  'paymentsofstockissuancecosts': 'Payments of Stock Issuance Costs',
  'paymentsofdividends': 'Payments of Dividends',
  'proceedsfromissuanceofdebt': 'Proceeds from Issuance of Debt',
  'repaymentsofdebt': 'Repayments of Debt',
  'paymentsofdebtissuancecosts': 'Payments of Debt Issuance Costs',
  'htgc paymentoffeesforcreditfacilitiesanddebentures': 'Payments of Fees for Credit Facilities and Debentures',
  'interestpaidnet': 'Interest Paid, Net',
  'incometaxespaidnet': 'Income Taxes Paid, Net',
  'htgc distributionsreinvested': 'Distributions Reinvested',
  'netincome': 'Net Income',
};

function normalizeKey(s?: string): string {
  if (!s) return '';
  return s
    .toLowerCase()
    .replace(/[^a-z0-9 ]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function resolveDisplayLabel(k: string, rawLabel?: string): string {
  const fromLabel = DISPLAY_NAME_OVERRIDES[normalizeKey(rawLabel)];
  if (fromLabel) return fromLabel;
  const fromKey = DISPLAY_NAME_OVERRIDES[normalizeKey(k)];
  if (fromKey) return fromKey;
  return formatLabel(rawLabel || k);
}

export function FinancialsPanel({ ticker, periods = [], name, mode = 'overview' }: Props) {
  // Fetch financials for all periods
  const financialsData = useBDCFinancialsMultiple(ticker, periods);

  // Use only periods that successfully loaded data to avoid empty columns
  const availableData = useMemo(() => financialsData.filter(({ data }) => !!data), [financialsData]);
  
  // Check for errors
  const hasErrors = financialsData.some(({ data }) => data === null);
  const errorCount = financialsData.filter(({ data }) => data === null).length;

  const rows = useMemo(() => {
    const metricKeys = [
      { key: 'total_investment_income', label: 'Total Investment Income', source: 'income_statement' },
      { key: 'net_investment_income', label: 'Net Investment Income', source: 'income_statement' },
      { key: 'net_investment_income_per_share', label: 'NII / Share', source: 'income_statement', fallback: 'derived' },
      { key: 'total_expenses', label: 'Total Expenses', source: 'income_statement' },
      { key: 'nav_per_share', label: 'NAV / Share', source: 'balance_sheet' },
      { key: 'total_assets', label: 'Total Assets', source: 'balance_sheet' },
      { key: 'total_liabilities', label: 'Total Liabilities', source: 'balance_sheet' },
      { key: 'shares_outstanding', label: 'Shares Outstanding', source: 'shares' },
      { key: 'debt_to_equity', label: 'Debt / Equity', source: 'derived' },
      { key: 'asset_coverage', label: 'Asset Coverage', source: 'derived' },
    ];

    return metricKeys.map(metric => {
      const values = availableData.map(({ period, data }) => {
        if (!data) return { period, value: null };
        const source = data[metric.source as keyof typeof data] as Record<string, unknown> | undefined;
        const fallback = metric.fallback ? data[metric.fallback as keyof typeof data] as Record<string, unknown> | undefined : undefined;
        const value = source?.[metric.key] ?? fallback?.[metric.key] ?? null;
        return { period, value };
      });
      return { label: metric.label, values };
    });
  }, [availableData]);

  const hasData = availableData.length > 0;

  // Pick the latest period's full statements (first item in list is latest)
  const latestFull = useMemo(() => {
    if (!availableData.length) return null;
    const latest = availableData[0]?.data as any;
    if (!latest) return null;
    return {
      income: latest.full_income_statement as Record<string, { label: string; value: number | null }> | undefined,
      cashflow: latest.full_cash_flow_statement as Record<string, { label: string; value: number | null }> | undefined,
      balance: latest.full_balance_sheet as Record<string, { label: string; value: number | null }> | undefined,
    };
  }, [availableData]);

  // Build historical table data for all statements across all periods
  const historicalData = useMemo(() => {
    if (!availableData.length) return null;
    
    // Collect all unique line items from all statements across all periods
    const lineItemsMap = new Map<string, { 
      key: string; 
      label: string; 
      statement: 'income' | 'balance' | 'cashflow';
    }>();
    
    availableData.forEach(({ period, data }) => {
      if (!data) return;
      const income = (data as any).full_income_statement as Record<string, { label: string; value: number | null }> | undefined;
      const balance = (data as any).full_balance_sheet as Record<string, { label: string; value: number | null }> | undefined;
      const cashflow = (data as any).full_cash_flow_statement as Record<string, { label: string; value: number | null }> | undefined;
      
      if (income) {
        Object.entries(income).forEach(([k, v]) => {
          if (!lineItemsMap.has(`income_${k}`)) {
            lineItemsMap.set(`income_${k}`, {
              key: k,
              label: resolveDisplayLabel(k, v.label),
              statement: 'income',
            });
          }
        });
      }
      if (balance) {
        Object.entries(balance).forEach(([k, v]) => {
          if (!lineItemsMap.has(`balance_${k}`)) {
            lineItemsMap.set(`balance_${k}`, {
              key: k,
              label: resolveDisplayLabel(k, v.label),
              statement: 'balance',
            });
          }
        });
      }
      if (cashflow) {
        Object.entries(cashflow).forEach(([k, v]) => {
          if (!lineItemsMap.has(`cashflow_${k}`)) {
            lineItemsMap.set(`cashflow_${k}`, {
              key: k,
              label: resolveDisplayLabel(k, v.label),
              statement: 'cashflow',
            });
          }
        });
      }
    });
    
    // Build rows: each line item with values across periods
    const rows = Array.from(lineItemsMap.values()).map((item) => {
      const values = availableData.map(({ period, data }) => {
        if (!data) return { period, value: null };
        const stmt = (data as any)[`full_${item.statement}_statement`] as Record<string, { label: string; value: number | null }> | undefined;
        const entry = stmt?.[item.key];
        return { period, value: entry?.value ?? null };
      });
      return {
        ...item,
        values,
      };
    });
    
    // Group by statement type
    const incomeRows = rows.filter(r => r.statement === 'income');
    const balanceRows = rows.filter(r => r.statement === 'balance');
    const cashflowRows = rows.filter(r => r.statement === 'cashflow');
    
    return { incomeRows, balanceRows, cashflowRows };
  }, [availableData]);

  const renderStatement = (title: string, stmt?: Record<string, { label: string; value: number | null }>) => {
    if (!stmt || Object.keys(stmt).length === 0) return null;
    const entries = Object.entries(stmt)
      .map(([k, v]) => ({
        key: k,
        label: resolveDisplayLabel(k, v.label),
        value: v.value,
      }))
      .filter((e) => e.value !== null)
      .slice(0, 50); // Show more items
    if (entries.length === 0) return null;
    return (
      <div className="mt-4">
        <div className="text-sm tracking-wide mb-2 text-[#808080] font-medium">{title} (latest period)</div>
        <div className="window overflow-auto">
          <table className="w-full text-sm border-separate border-spacing-0">
            <thead className="sticky top-0 bg-[#c0c0c0] z-10">
              <tr className="border-b border-[#808080]">
                <th className="text-left py-2 px-3 text-[#808080] font-semibold">Line Item</th>
                <th className="text-right py-2 px-3 text-[#808080] font-semibold">Value</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => (
                <tr key={e.key} className="border-b border-[#c0c0c0] hover:bg-[#c0c0c0]">
                  <td className="py-1.5 px-3 text-black">{e.label}</td>
                  <td className="py-1.5 px-3 text-right font-mono text-black">{fmt(e.value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  const renderHistoricalStatement = (title: string, rows: Array<{ key: string; label: string; statement: 'income' | 'balance' | 'cashflow'; values: Array<{ period: string; value: number | null }> }>) => {
    if (!rows || rows.length === 0) return null;
    
    // Filter out rows where all values are null
    const validRows = rows.filter(row => row.values.some(v => v.value !== null));
    if (validRows.length === 0) return null;
    
    // Helper to determine if period is likely quarterly (10-Q) or annual (10-K)
    // Check if period date is near quarter-end (Mar 31, Jun 30, Sep 30, Dec 31) for annual
    const getPeriodType = (period: string): 'quarterly' | 'annual' => {
      try {
        const date = new Date(period);
        const month = date.getMonth() + 1; // 1-12
        const day = date.getDate();
        // Annual filings typically filed after year-end (Feb-Apr for Dec 31, etc.)
        // Quarterly filings typically filed 1-2 months after quarter-end
        // For now, assume Q4 (Dec) and filings in Jan-Mar are annual, others are quarterly
        if (month === 12 || (month >= 1 && month <= 3)) {
          // Could be annual, but also could be Q4 - check the actual data structure
          // For now, we'll infer from the period date pattern
          return 'annual';
        }
        return 'quarterly';
      } catch {
        return 'quarterly';
      }
    };
    
    return (
      <div className="mt-4">
        <div className="window overflow-auto">
          <div className="titlebar">
            <div className="text-sm tracking-wide">{title}</div>
          </div>
          <table className="w-full text-sm table-excel">
            <thead className="sticky top-0 z-10">
              <tr>
                <th className="text-left py-2 px-3 text-black font-mono text-xs sticky left-0 bg-[#c0c0c0] border border-[#c0c0c0]">Line Item</th>
                {availableData.map(({ period, data }) => {
                  // Try to get form_type from data, or infer from period
                  const formType = (data as any)?.form_type;
                  const periodType = formType === '10-K' ? 'annual' : formType === '10-Q' ? 'quarterly' : getPeriodType(period);
                  const typeLabel = periodType === 'annual' ? ' (Annual)' : ' (Quarterly)';
                  return (
                    <th key={period} className="text-right py-2 px-3 text-black font-mono text-xs min-w-[120px] border border-[#c0c0c0]">
                      <div>{period}</div>
                      <div className="text-[9px] text-[#808080] font-mono">{typeLabel}</div>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {validRows.map((row, rowIdx) => {
                const rowNum = rowIdx + 2;
                return (
                <tr key={`${row.statement}_${row.key}`} className="hover:bg-[#c0c0c0]">
                  <td className="py-1.5 px-3 text-black font-mono text-xs sticky left-0 bg-[#c0c0c0] border border-[#c0c0c0]">{row.label}</td>
                  {row.values.map(({ period, value }, colIdx) => {
                    const colLetter = String.fromCharCode(66 + colIdx); // B, C, D, etc. (A is Line Item)
                    const cellRef = `${colLetter}${rowNum}`;
                    return (
                    <td key={period} className="text-right py-1.5 px-3 font-mono text-black relative border border-[#c0c0c0]">
                      <span className="cell-ref">{cellRef}</span>
                      {fmt(value)}
                    </td>
                    );
                  })}
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  if (mode === 'historical') {
    // Historical mode: show all line items across all periods in big tables
    return (
      <div className="space-y-4">
        {hasErrors && errorCount > 0 && (
          <div className="window p-3 border-l-4 border-yellow-500/50 bg-yellow-500/5">
            <div className="text-xs text-yellow-400">
              ⚠️ {errorCount} of {periods.length} period{errorCount !== 1 ? 's' : ''} failed to load
            </div>
            <div className="text-xs text-[#808080] mt-1">
              Showing available data only
            </div>
          </div>
        )}
        {hasData && historicalData ? (
          <>
            {renderHistoricalStatement('Income Statement', historicalData.incomeRows)}
            {renderHistoricalStatement('Balance Sheet', historicalData.balanceRows)}
            {renderHistoricalStatement('Cash Flow Statement', historicalData.cashflowRows)}
            {(!historicalData.incomeRows.length && !historicalData.balanceRows.length && !historicalData.cashflowRows.length) && (
              <div className="window p-4">
                <div className="text-sm text-[#808080]">No financial data found for selected periods</div>
              </div>
            )}
          </>
        ) : !hasData && periods.length > 0 ? (
          <div className="window p-4">
            <div className="text-sm text-red-400">⚠️ Error loading financials</div>
            <div className="text-xs text-[#808080] mt-1">Unable to load financial data for the selected periods</div>
          </div>
        ) : (
          <div className="text-xs text-silver/60 p-4">Loading financials...</div>
        )}
      </div>
    );
  }

  // Overview mode: show key metrics + latest statements
  return (
    <div className="space-y-4">
      {hasData ? (
        <>
          <div className="window overflow-auto">
            <div className="titlebar">
              <div className="text-sm tracking-wide">Key Metrics</div>
            </div>
            <table className="w-full text-sm border-separate border-spacing-0">
              <thead className="sticky top-0 bg-[#1b1f23] z-10">
                <tr className="border-b border-silver/20">
                  <th className="text-left py-2 px-3 text-[#808080] font-semibold">Metric</th>
                  {availableData.map(({ period }) => (
                    <th key={period} className="text-right py-2 px-3 text-[#808080] font-semibold">
                      {period}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.label} className="border-b border-[#c0c0c0] hover:bg-[#c0c0c0]">
                    <td className="py-1.5 px-3 text-black">{row.label}</td>
                    {row.values.map(({ period, value }) => (
                      <td key={period} className="text-right py-1.5 px-3 font-mono text-black">
                        {fmt(value)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {renderStatement('Income Statement', latestFull?.income)}
          {renderStatement('Balance Sheet', latestFull?.balance)}
          {renderStatement('Cash Flow Statement', latestFull?.cashflow)}
        </>
      ) : (
        <div className="text-xs text-silver/60">Loading financials...</div>
      )}
    </div>
  );
}


