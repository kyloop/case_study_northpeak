export interface RowError {
  field: string;
  message: string;
}

// Column names of the upload file (data/bulk_upload_template.csv), in file order.
export const UPLOAD_COLUMNS = [
  "part_number", "supplier_name", "fiscal_period", "submitted_unit_cost", "material_cost",
  "labor_cost", "overhead_cost", "margin_pct", "currency", "submitted_by",
] as const;

export interface ReportRow {
  row: number;
  values: Record<string, string>; // the row as uploaded, keyed by the CSV column names
  status: "saved" | "duplicate" | "failed";
  errors: RowError[];
  warnings: string[];
  submission_id: number | null;
}

export interface UploadReport {
  filename: string;
  identical_file_seen_before: boolean;
  summary: { total: number; saved: number; duplicate: number; failed: number };
  rows: ReportRow[];
}

export interface ReviewRow {
  submission_id: number;
  part_number: string;
  commodity: string;
  supplier_id: number;
  supplier_name: string;
  fiscal_period: string;
  submitted_unit_cost: number;
  should_cost: number;
  sample_size: number;
  pct_over: number;
  status: "pending" | "approved" | "rejected";
  risk_note: string;
}

export interface ReviewResponse {
  threshold_pct: number;
  rows: ReviewRow[];
}

export interface TableInfo {
  name: string;
  count: number;
}

export interface TableData {
  table: string;
  columns: string[];
  rows: Record<string, string | number | null>[];
  total: number;
  page: number;
  pages: number;
  sort: string;
  dir: "asc" | "desc";
  q: string;
  filters: { column: string; value: string }[];
  link: { path: string[] | null; note: string | null } | null;
}
