export type EnvelopeStatus = 'GREEN' | 'YELLOW' | 'RED';
export type EnvelopeScope = 'PERSONAL' | 'SHARED';
export type RolloverPolicy = 'RESET' | 'CARRY_OVER';

export interface EnvelopeCategoryRef {
  id: string; // UUID
  name: string;
}

export interface EnvelopeResponse {
  id: string;
  bankAccountId: string;
  bankAccountName: string;
  name: string;
  scope: EnvelopeScope;
  ownerId: string | null;
  categories: EnvelopeCategoryRef[];
  rolloverPolicy: RolloverPolicy;
  defaultBudget: number;
  effectiveBudget: number;
  consumed: number;
  available: number;
  ratio: number;
  status: EnvelopeStatus;
  hasMonthlyOverride: boolean;
  archived: boolean;
  createdAt: string; // ISO 8601 instant
}

export interface EnvelopeAllocationResponse {
  id: string;
  envelopeId: string;
  month: string; // "yyyy-MM"
  allocatedAmount: number;
  createdAt: string;
}

export interface EnvelopeHistoryEntry {
  month: string; // "yyyy-MM"
  effectiveBudget: number;
  consumed: number;
  available: number;
  ratio: number;
  status: EnvelopeStatus;
}

export interface CreateEnvelopeRequest {
  name: string;
  categoryIds: string[];
  budget: number;
  rolloverPolicy: RolloverPolicy;
}

export interface UpdateEnvelopeRequest {
  name?: string | null;
  categoryIds?: string[] | null;
  budget?: number | null;
  rolloverPolicy?: RolloverPolicy | null;
}

export interface EnvelopeAllocationRequest {
  month: string; // "yyyy-MM"
  allocatedAmount: number;
}

export interface EnvelopeListFilters {
  accountId?: string | null;
  includeArchived?: boolean;
}
