export interface TransactionResponse {
  id: string;
  accountId: string;
  amount: number;
  description: string | null;
  categoryId: string | null;
  categoryName: string | null;
  transactionDate: string; // YYYY-MM-DD
  source: 'MANUAL' | 'PLAID' | 'RECURRING';
  state: 'MANUAL_UNMATCHED' | 'IMPORTED_UNMATCHED' | 'MATCHED';
  pointed: boolean;
  createdAt: string;
  splits: TransactionSplitResponse[];
}

export interface TransactionSplitResponse {
  id: string;
  categoryId: string;
  categoryName: string;
  amount: number;
  description: string | null;
}

export interface CreateTransactionRequest {
  amount: number;
  transactionDate: string;
  description?: string;
  categoryId?: string;
}

export interface UpdateTransactionRequest {
  amount?: number;
  transactionDate?: string;
  description?: string;
  categoryId?: string;
  clearCategory?: boolean;
}

export interface TransactionFilters {
  dateFrom?: string;
  dateTo?: string;
  amountMin?: number;
  amountMax?: number;
  categoryId?: string;
  search?: string;
}

export interface Page<T> {
  content: T[];
  totalElements: number;
  totalPages: number;
  number: number;
  size: number;
}
