import { useMemo } from 'react';
import { createColumnHelper, flexRender, getCoreRowModel, getSortedRowModel, SortingState, useReactTable } from '@tanstack/react-table';
import { Holding } from '../data/adapter';
import { ExportBar } from './ExportBar';

type Props = {
  data: Holding[];
};

const columnHelper = createColumnHelper<Holding>();

export function HoldingsTable({ data }: Props) {
  const columns = useMemo(
    () => [
      columnHelper.accessor('company_name', { header: 'Company', cell: (c) => c.getValue() }),
      columnHelper.accessor('investment_type', { header: 'Type', cell: (c) => c.getValue() }),
      columnHelper.accessor('industry', { header: 'Industry', cell: (c) => c.getValue() }),
      columnHelper.accessor('principal_amount', { header: 'Principal', cell: (c) => c.getValue() }),
      columnHelper.accessor('amortized_cost', { header: 'Cost', cell: (c) => c.getValue() }),
      columnHelper.accessor('fair_value', { header: 'Fair Value', cell: (c) => c.getValue() }),
      columnHelper.accessor('interest_rate', { header: 'Rate', cell: (c) => c.getValue() }),
      columnHelper.accessor('spread', { header: 'Spread', cell: (c) => c.getValue() }),
      columnHelper.accessor('acquisition_date', { header: 'Acq', cell: (c) => c.getValue() }),
      columnHelper.accessor('maturity_date', { header: 'Mat', cell: (c) => c.getValue() }),
    ],
    []
  );

  const table = useReactTable({ data, columns, getCoreRowModel: getCoreRowModel(), getSortedRowModel: getSortedRowModel() });

  return (
    <div className="window overflow-hidden flex flex-col">
      <div className="titlebar">
        <div className="text-sm tracking-wide">Holdings</div>
        <div className="text-xs text-silver/70">Rows: {data.length}</div>
      </div>
      <div className="overflow-auto flex-1">
        <table className="w-full text-sm">
          <thead className="bg-panel/60 sticky top-0">
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id} className="border-b border-silver/20">
                {hg.headers.map((h) => (
                  <th key={h.id} className="text-left px-3 py-2 whitespace-nowrap">
                    {h.isPlaceholder ? null : flexRender(h.column.columnDef.header, h.getContext())}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr key={row.id} className="border-b border-silver/10 hover:bg-panel/70">
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className="px-3 py-2 align-top">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ExportBar data={data} />
    </div>
  );
}


