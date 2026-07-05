import type {
  ApprovalResult,
  Deal,
  DealInput,
  EvidenceBundle,
  Health,
  SupplierSummary
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-Demo-User": "ivan.petrov",
      ...init?.headers
    }
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const message =
      payload?.detail ?? `${response.status} ${response.statusText}`;
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

function isoDateAfter(days: number): string {
  const value = new Date();
  value.setDate(value.getDate() + days);
  return value.toISOString().slice(0, 10);
}

export const api = {
  health: () => request<Health>("/health"),

  suppliers: () => request<SupplierSummary[]>("/api/v1/suppliers"),

  deals: () => request<Deal[]>("/api/v1/deals"),

  getDeal: (dealId: string) =>
    request<Deal>(`/api/v1/deals/${dealId}`),

  evidence: (dealId: string) =>
    request<EvidenceBundle>(`/api/v1/deals/${dealId}/evidence`),

  createDeal: (input: DealInput) =>
    request<Deal>("/api/v1/deals", {
      method: "POST",
      body: JSON.stringify({
        intent: {
          customer_id: input.customerId,
          product: {
            sku: input.sku,
            name: input.productName,
            category: "mro.standardized",
            quantity: input.quantity
          },
          delivery_city: input.deliveryCity,
          delivery_by: isoDateAfter(input.deliveryDays),
          max_total: input.maxTotal.toFixed(2),
          currency: "RUB"
        },
        mandate: {
          customer_id: input.customerId,
          authorized_by: input.authorizedBy,
          allowed_categories: ["mro.standardized"],
          max_total: input.maxTotal.toFixed(2),
          expires_at: new Date(Date.now() + 86_400_000).toISOString()
        }
      })
    }),

  approve: (
    dealId: string,
    quoteId: string,
    approvedBy: string,
    approvalSnapshotHash: string
  ) =>
    request<ApprovalResult>(`/api/v1/deals/${dealId}/approve`, {
      method: "POST",
      body: JSON.stringify({
        quote_id: quoteId,
        approved_by: approvedBy,
        approval_snapshot_hash: approvalSnapshotHash
      })
    })
};
