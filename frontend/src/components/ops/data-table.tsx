"use client";
import { useState } from "react";
import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import { ArrowDownUp, ChevronLeft, ChevronRight, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { EmptyState } from "./common";
export function DataTable<T>({
  data,
  columns,
  searchPlaceholder = "Search records…",
  search: externalSearch,
  onSearch,
}: {
  data: T[];
  columns: ColumnDef<T>[];
  searchPlaceholder?: string;
  search?: string;
  onSearch?: (value: string) => void;
}) {
  const [sorting, setSorting] = useState<SortingState>([]),
    [search, setSearch] = useState("");
  const value = externalSearch ?? search;
  // TanStack Table owns a mutable row model, so React Compiler must skip this call.
  // eslint-disable-next-line react-hooks/incompatible-library
  const table = useReactTable({
    data,
    columns,
    state: { sorting, globalFilter: value },
    onSortingChange: setSorting,
    onGlobalFilterChange: onSearch ?? setSearch,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    autoResetPageIndex: true,
    initialState: { pagination: { pageSize: 8 } },
  });
  return (
    <>
      <div className="ops-table-toolbar">
        <label className="ops-search">
          <Search size={14} />
          <input
            value={value}
            onChange={(e) => (onSearch ?? setSearch)(e.target.value)}
            placeholder={searchPlaceholder}
            aria-label={searchPlaceholder}
          />
        </label>
        <span>{table.getFilteredRowModel().rows.length} records</span>
      </div>
      <div className="ops-table-scroll">
        <table className="ops-table">
          <thead>
            {table.getHeaderGroups().map((group) => (
              <tr key={group.id}>
                {group.headers.map((header) => (
                  <th
                    key={header.id}
                    scope="col"
                    aria-sort={
                      header.column.getIsSorted() === "asc"
                        ? "ascending"
                        : header.column.getIsSorted() === "desc"
                          ? "descending"
                          : "none"
                    }
                  >
                    {header.isPlaceholder ? null : (
                      <button
                        disabled={!header.column.getCanSort()}
                        onClick={header.column.getToggleSortingHandler()}
                      >
                        {flexRender(
                          header.column.columnDef.header,
                          header.getContext(),
                        )}
                        {header.column.getCanSort() && (
                          <ArrowDownUp size={10} />
                        )}
                      </button>
                    )}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr key={row.id}>
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {!table.getRowModel().rows.length && (
          <EmptyState title="No matching records." />
        )}
      </div>
      <div className="ops-table-footer">
        <span>
          Page {table.getState().pagination.pageIndex + 1} of{" "}
          {Math.max(1, table.getPageCount())}
        </span>
        <div>
          <Button
            size="icon-sm"
            variant="ghost"
            aria-label="Previous page"
            disabled={!table.getCanPreviousPage()}
            onClick={() => table.previousPage()}
          >
            <ChevronLeft size={15} />
          </Button>
          <Button
            size="icon-sm"
            variant="ghost"
            aria-label="Next page"
            disabled={!table.getCanNextPage()}
            onClick={() => table.nextPage()}
          >
            <ChevronRight size={15} />
          </Button>
        </div>
      </div>
    </>
  );
}
