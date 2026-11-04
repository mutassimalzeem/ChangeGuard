import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * A semantic table whose column headers carry the sort state. Columns are
 * declared rather than written as markup so header and cell order cannot drift
 * apart, which is the usual cause of a table labelled one way and read another.
 */
export interface Column<T> {
  readonly key: string;
  readonly header: ReactNode;
  readonly align?: "left" | "right";
  readonly sortable?: boolean;
  /** Class for the header cell, letting a column stay narrow or take the slack. */
  readonly headerClassName?: string;
  render(row: T): ReactNode;
}

export type SortDirection = "asc" | "desc";

export interface SortState {
  readonly key: string;
  readonly direction: SortDirection;
}

export interface TableProps<T> {
  readonly columns: readonly Column<T>[];
  readonly rows: readonly T[];
  readonly rowKey: (row: T) => string;
  readonly caption: string;
  /** Visually hides the caption but keeps it for screen readers. */
  readonly captionHidden?: boolean;
  readonly sort?: SortState | null;
  readonly onSortChange?: (key: string) => void;
  readonly loading?: boolean;
  readonly emptyMessage?: ReactNode;
}

const alignClass = (align: "left" | "right" | undefined): string =>
  align === "right" ? "text-right" : "text-left";

/**
 * The header cell is a button when sorting is offered, so the column is
 * reachable and operable by keyboard like any other control, and carries
 * `aria-sort` so the current order is announced.
 */
function HeaderCell<T>({
  column,
  sort,
  onSortChange,
}: {
  column: Column<T>;
  sort: SortState | null;
  onSortChange?: (key: string) => void;
}) {
  const active = sort?.key === column.key ? sort.direction : null;
  const ariaSort = active === "asc" ? "ascending" : active === "desc" ? "descending" : "none";
  const sortable = column.sortable === true && onSortChange !== undefined;

  return (
    <th
      scope="col"
      aria-sort={column.sortable === true ? ariaSort : undefined}
      className={cn(
        "whitespace-nowrap border-b border-border bg-subtle px-4 py-2.5 text-xs font-semibold text-ink-muted",
        alignClass(column.align),
        column.headerClassName,
      )}
    >
      {sortable ? (
        <button
          type="button"
          onClick={() => onSortChange(column.key)}
          className="inline-flex items-center gap-1 rounded hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2"
        >
          {column.header}
          <span aria-hidden className="text-[10px]">
            {active === "asc" ? "▲" : active === "desc" ? "▼" : "⇅"}
          </span>
        </button>
      ) : (
        column.header
      )}
    </th>
  );
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  caption,
  captionHidden = false,
  sort = null,
  onSortChange,
  loading = false,
  emptyMessage = "Nothing to show yet.",
}: TableProps<T>) {
  return (
    <div className="relative w-full overflow-x-auto rounded-[--radius-card] border border-border bg-surface shadow-card">
      <table className="w-full border-collapse text-sm">
        <caption className={cn("px-4 py-3 text-left text-sm text-ink-muted", captionHidden && "sr-only")}>
          {caption}
        </caption>
        <thead>
          <tr>
            {columns.map((column) => (
              <HeaderCell key={column.key} column={column} sort={sort} onSortChange={onSortChange} />
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="px-4 py-10 text-center text-sm text-ink-muted">
                {loading ? "Loading..." : emptyMessage}
              </td>
            </tr>
          ) : (
            rows.map((row) => (
              <tr key={rowKey(row)} className="border-b border-border last:border-b-0 hover:bg-subtle/60">
                {columns.map((column) => (
                  <td
                    key={column.key}
                    className={cn("px-4 py-3 align-top text-ink", alignClass(column.align))}
                  >
                    {column.render(row)}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

export const Table = DataTable;
