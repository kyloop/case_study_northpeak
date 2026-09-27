import type { ReviewResponse, TableData, TableInfo, UploadReport } from "./types";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") message = body.detail;
    } catch {
      /* keep the status text */
    }
    throw new Error(message);
  }
  return res.json() as Promise<T>;
}

export const api = {
  upload(file: File, uploadedBy: string) {
    const form = new FormData();
    form.append("file", file);
    form.append("uploaded_by", uploadedBy);
    return request<UploadReport>("/api/upload", { method: "POST", body: form });
  },
  review() {
    return request<ReviewResponse>("/api/review");
  },
  decide(id: number, action: "approve" | "reject", actor: string, reason: string) {
    return request<{ submission_id: number; before: string; after: string }>(`/api/review/${id}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, actor, reason }),
    });
  },
  tables() {
    return request<{ tables: TableInfo[] }>("/api/tables");
  },
  table(name: string, params: URLSearchParams) {
    return request<TableData>(`/api/tables/${name}?${params.toString()}`);
  },
};
