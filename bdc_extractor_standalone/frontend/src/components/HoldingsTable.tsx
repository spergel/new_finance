import { useEffect, useMemo, useState, useRef, memo, useTransition, useCallback } from 'react';
import { createColumnHelper, flexRender, getCoreRowModel, getSortedRowModel, useReactTable } from '@tanstack/react-table';
import type { SortingState } from '@tanstack/react-table';
import type { Holding } from '../data/adapter';
import { checkRedFlags } from '../utils/holdingsAnalytics';
import { ExportBar } from './ExportBar';

type Props = {
  data: Holding[];
  period?: string;
};

const columnHelper = createColumnHelper<Holding>();

function fmtNumber(v: unknown): string {
  if (v === null || v === undefined || v === '') return '';
  const n = Number(v);
  if (Number.isNaN(n)) return String(v);
  return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

// Sorting helpers
function toNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const num = Number(value);
  return Number.isNaN(num) ? null : num;
}

function toPercent(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  if (typeof value === 'string') {
    const cleaned = value.replace(/%/g, '').trim();
    const num = Number(cleaned);
    return Number.isNaN(num) ? null : num;
  }
  const num = Number(value);
  return Number.isNaN(num) ? null : num;
}

function toDateEpoch(value: unknown): number | null {
  if (!value || typeof value !== 'string') return null;
  const t = Date.parse(value);
  return Number.isNaN(t) ? null : t;
}

function compareNullable(a: number | null, b: number | null): number {
  if (a === null && b === null) return 0;
  if (a === null) return 1; // nulls last
  if (b === null) return -1;
  return a - b;
}

function decodeHtmlEntities(text: unknown): string {
  if (text === null || text === undefined || text === '') return '';
  const str = String(text);
  // Decode common HTML entities
  return str
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&apos;/g, "'");
}

// Memoize the component to prevent unnecessary re-renders
function HoldingsTableComponent({ data, period }: Props) {
  const dataRef = useRef<number>(0);
  const [isPending, startTransition] = useTransition();
  const [searchQuery, setSearchQuery] = useState<string>('');

  // Default sort by company name ascending
  const [sorting, setSorting] = useState<SortingState>([{ id: 'company_name', desc: false }]);
  
  // Wrapper to make sorting updates non-blocking
  const handleSortingChange = useCallback((updater: any) => {
    startTransition(() => {
      if (typeof updater === 'function') {
        setSorting(updater);
      } else {
        setSorting(updater);
      }
    });
  }, [startTransition]);
  
  // Reset to default sort when data actually changes (new ticker/period)
  useEffect(() => {
    if (dataRef.current !== data.length) {
      dataRef.current = data.length;
      setSorting([{ id: 'company_name', desc: false }]);
    }
  }, [data.length]);

  // Precompute sort keys once per dataset - decode HTML entities once, compute sort keys
  const processedData = useMemo(() => {
    const processed = data.map((d: any) => {
      const companyName = decodeHtmlEntities(d?.company_name ?? '');
      const investmentType = decodeHtmlEntities(d?.investment_type ?? '');
      const industry = decodeHtmlEntities(d?.industry ?? '');
      
      return {
        ...d,
        // Decode HTML entities for display
        company_name: companyName,
        investment_type: investmentType,
        industry: industry,
        // Pre-computed sort keys (reuse decoded values)
        _s_company: companyName.toLowerCase(),
        _s_type: investmentType.toLowerCase(),
        _s_industry: industry.toLowerCase(),
        _n_principal: toNumber(d?.principal_amount),
        _n_cost: toNumber((d as any)?.cost ?? (d as any)?.amortized_cost),
        _n_fair: toNumber(d?.fair_value),
        _p_rate: toPercent(d?.interest_rate),
        _p_spread: toPercent(d?.spread),
        _t_acq: toDateEpoch(d?.acquisition_date),
        _t_mat: toDateEpoch(d?.maturity_date),
      };
    });
    return processed;
  }, [data]);

  // Filter data based on search query
  const filteredData = useMemo(() => {
    if (!searchQuery.trim()) return processedData;
    
    const query = searchQuery.toLowerCase().trim();
    return processedData.filter((d: any) => {
      // Search across company name, investment type, and industry
      return (
        d._s_company.includes(query) ||
        d._s_type.includes(query) ||
        d._s_industry.includes(query) ||
        (d?.reference_rate && String(d.reference_rate).toLowerCase().includes(query)) ||
        (d?.maturity_date && String(d.maturity_date).toLowerCase().includes(query))
      );
    });
  }, [processedData, searchQuery]);

  const columns = useMemo(
    () => [
      columnHelper.accessor('company_name', {
        header: 'Company',
        cell: (c) => c.getValue() ?? '',
        enableSorting: true,
        sortingFn: (rowA, rowB) => {
          const a = (rowA.original as any)._s_company;
          const b = (rowB.original as any)._s_company;
          return a < b ? -1 : a > b ? 1 : 0;
        },
      }),
      columnHelper.accessor('investment_type', {
        header: 'Type',
        cell: (c) => c.getValue() ?? '',
        enableSorting: true,
        sortingFn: (rowA, rowB) => {
          const a = (rowA.original as any)._s_type;
          const b = (rowB.original as any)._s_type;
          return a < b ? -1 : a > b ? 1 : 0;
        },
      }),
      columnHelper.accessor('industry', {
        header: 'Industry',
        cell: (c) => c.getValue() ?? '',
        enableSorting: true,
        sortingFn: (rowA, rowB) => {
          const a = (rowA.original as any)._s_industry;
          const b = (rowB.original as any)._s_industry;
          return a < b ? -1 : a > b ? 1 : 0;
        },
      }),
      columnHelper.accessor('principal_amount', {
        header: 'Principal',
        cell: (c) => <span className="block text-right">{fmtNumber(c.getValue() as any)}</span>,
        enableSorting: true,
        sortingFn: (rowA, rowB) => compareNullable((rowA.original as any)._n_principal, (rowB.original as any)._n_principal),
      }),
      columnHelper.accessor('amortized_cost', {
        header: 'Cost',
        cell: (c) => <span className="block text-right">{fmtNumber(c.getValue() as any)}</span>,
        enableSorting: true,
        sortingFn: (rowA, rowB) => compareNullable((rowA.original as any)._n_cost, (rowB.original as any)._n_cost),
      }),
      columnHelper.accessor('fair_value', {
        header: 'Fair Value',
        cell: (c) => <span className="block text-right">{fmtNumber(c.getValue() as any)}</span>,
        enableSorting: true,
        sortingFn: (rowA, rowB) => compareNullable((rowA.original as any)._n_fair, (rowB.original as any)._n_fair),
      }),
      columnHelper.accessor('interest_rate', {
        header: 'Rate',
        cell: (c) => <span className="block text-right">{c.getValue() ?? ''}</span>,
        enableSorting: true,
        sortingFn: (rowA, rowB) => compareNullable((rowA.original as any)._p_rate, (rowB.original as any)._p_rate),
      }),
      columnHelper.accessor('spread', {
        header: 'Spread',
        cell: (c) => <span className="block text-right">{c.getValue() ?? ''}</span>,
        enableSorting: true,
        sortingFn: (rowA, rowB) => compareNullable((rowA.original as any)._p_spread, (rowB.original as any)._p_spread),
      }),
      columnHelper.accessor('acquisition_date', {
        header: 'Acq',
        cell: (c) => c.getValue() ?? '',
        enableSorting: true,
        sortingFn: (rowA, rowB) => compareNullable((rowA.original as any)._t_acq, (rowB.original as any)._t_acq),
      }),
      columnHelper.accessor('maturity_date', {
        header: 'Mat',
        cell: (c) => c.getValue() ?? '',
        enableSorting: true,
        sortingFn: (rowA, rowB) => compareNullable((rowA.original as any)._t_mat, (rowB.original as any)._t_mat),
      }),
      columnHelper.display({
        id: 'red_flags',
        header: 'Flags',
        cell: (c) => {
          const holding = c.row.original as Holding;
          const flags = checkRedFlags(holding, period || '');
          if (flags.length === 0) return null;
          return (
            <div className="flex flex-wrap gap-1">
              {flags.slice(0, 2).map((flag, i) => (
                <span
                  key={i}
                  className={`badge text-[10px] ${
                    flag.severity === 'high' ? 'badge-danger' :
                    flag.severity === 'medium' ? 'badge-warn' : 'badge-ok'
                  }`}
                  title={flag.message}
                >
                  {flag.type === 'fv_equals_principal' ? 'FV=Prin' :
                   flag.type === 'fv_below_principal' ? 'FV<Prin' :
                   flag.type === 'fv_below_cost' ? 'FV<Cost' :
                   flag.type === 'has_pik' ? 'PIK' :
                   flag.type === 'near_maturity' ? 'Mat' : flag.type}
                </span>
              ))}
              {flags.length > 2 && (
                <span className="badge badge-ok text-[10px]" title={flags.slice(2).map(f => f.message).join('; ')}>
                  +{flags.length - 2}
                </span>
              )}
            </div>
          );
        },
        enableSorting: false,
      }),
    ],
    [period]
  );

  const table = useReactTable({
    data: filteredData as any,
    columns,
    state: { sorting },
    onSortingChange: handleSortingChange,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    manualSorting: false,
    enableSortingRemoval: true,
  });

  const sortedRows = table.getRowModel().rows;

  // Get filtered/sorted holdings for export
  const exportData = useMemo(() => {
    return sortedRows.map(row => row.original);
  }, [sortedRows]);

  // Generate filename with period if available
  const exportFilename = useMemo(() => {
    const base = 'holdings';
    if (period) {
      const periodStr = period.replace(/[^0-9]/g, '_');
      return `${base}_${periodStr}`;
    }
    return `${base}_${new Date().toISOString().split('T')[0]}`;
  }, [period]);

  return (
    <div className="window flex flex-col h-full min-h-0 overflow-hidden">
      <div className="titlebar flex-shrink-0">
        <div className="text-xs sm:text-sm tracking-wide">Holdings</div>
        <div className="flex items-center gap-2 sm:gap-3 text-xs text-white flex-wrap" aria-live="polite">
          <span className="whitespace-nowrap">Rows: {filteredData.length}{searchQuery ? ` (${data.length})` : ''}</span>
          {isPending ? (
            <span className="inline-flex items-center gap-1 text-[#808080]">
              <span className="h-3 w-3 border-2 border-[#000080] border-t-transparent animate-spin" style={{ borderRadius: 0 }} />
              Sorting
            </span>
          ) : null}
        </div>
      </div>
      <div className="p-2 border-b border-[#c0c0c0] flex-shrink-0">
        <input
          type="text"
          className="input w-full text-xs"
          placeholder="Search by company name, type, industry..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
        />
      </div>
      <div className="overflow-auto flex-1 min-h-0 relative">
        <table className="w-full text-xs sm:text-sm table-excel">
          <thead className="sticky top-0 z-10">
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                <th className="px-1 sm:px-2 py-1 sm:py-2 text-[#808080] text-[9px] sm:text-[10px] text-right border border-[#c0c0c0] bg-[#c0c0c0] sticky left-0 z-10">
                  #
                </th>
                    {hg.headers.map((h, colIdx) => {
                      const colLetter = String.fromCharCode(65 + colIdx + 1); // B, C, D, etc. (A is row number)
                      return (
                      <th
                        key={h.id}
                    className={`px-2 sm:px-3 py-1 sm:py-2 whitespace-nowrap cursor-pointer select-none text-black text-[10px] sm:text-xs relative border border-[#c0c0c0] ${h.column.id === 'principal_amount' || h.column.id === 'amortized_cost' || h.column.id === 'fair_value' || h.column.id === 'interest_rate' || h.column.id === 'spread' ? 'text-right' : 'text-left'}`}
                        onClick={(e) => {
                          const handler = h.column.getToggleSortingHandler();
                          if (handler) {
                            handler(e);
                          }
                        }}
                        aria-sort={h.column.getIsSorted() ? (h.column.getIsSorted() === 'desc' ? 'descending' : 'ascending') : 'none'}
                      >
                        {h.isPlaceholder ? null : (
                          <div className="flex items-center gap-1">
                            {flexRender(h.column.columnDef.header, h.getContext())}
                            {h.column.getIsSorted() === 'asc' ? (
                              <svg viewBox="0 0 20 20" className="h-3 w-3 text-black" aria-hidden="true">
                                <path d="M10 6l-4 6h8l-4-6z" fill="currentColor" />
                              </svg>
                            ) : h.column.getIsSorted() === 'desc' ? (
                              <svg viewBox="0 0 20 20" className="h-3 w-3 text-black" aria-hidden="true">
                                <path d="M10 14l4-6H6l4 6z" fill="currentColor" />
                              </svg>
                            ) : null}
                          </div>
                        )}
                        <span className="cell-ref">{colLetter}1</span>
                      </th>
                    );
                    })}
              </tr>
            ))}
          </thead>
          <tbody className="text-black">
            {sortedRows.map((row, rowIdx) => {
              const rowNum = rowIdx + 2; // Start from row 2 (row 1 is header)
              return (
              <tr key={row.id} className="hover:bg-[#c0c0c0]">
                <td className="px-1 sm:px-2 py-1 text-[#808080] text-[9px] sm:text-[10px] text-right border border-[#c0c0c0] bg-[#c0c0c0] sticky left-0 z-10">
                  {rowNum}
                </td>
                {row.getVisibleCells().map((cell) => {
                  return (
                  <td key={cell.id} className="px-2 sm:px-3 py-1 sm:py-2 align-top relative border border-[#c0c0c0] text-[10px] sm:text-xs">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                  );
                })}
              </tr>
              );
            })}
          </tbody>
        </table>
        {isPending ? (
          <div className="absolute inset-0 bg-[#c0c0c0]/80 flex items-center justify-center z-20">
            <div className="flex items-center gap-2 text-black text-xs">
              <span className="h-5 w-5 border-2 border-[#000080] border-t-transparent animate-spin" style={{ borderRadius: 0 }} />
              <span>Sorting…</span>
            </div>
          </div>
        ) : null}
      </div>
      {exportData.length > 0 && (
        <div className="flex-shrink-0">
          <ExportBar data={exportData as Holding[]} filename={exportFilename} />
        </div>
      )}
    </div>
  );
}

export const HoldingsTable = memo(HoldingsTableComponent);


