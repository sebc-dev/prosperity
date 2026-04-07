import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import {
  TransactionResponse,
  CreateTransactionRequest,
  UpdateTransactionRequest,
  TransactionFilters,
  Page,
} from './transaction.types';

@Injectable({ providedIn: 'root' })
export class TransactionService {
  private readonly http = inject(HttpClient);

  getTransactions(
    accountId: string,
    page: number,
    size: number,
    filters: TransactionFilters,
  ): Observable<Page<TransactionResponse>> {
    let params = new HttpParams().set('page', page.toString()).set('size', size.toString());
    if (filters.dateFrom) params = params.set('dateFrom', filters.dateFrom);
    if (filters.dateTo) params = params.set('dateTo', filters.dateTo);
    if (filters.amountMin != null) params = params.set('amountMin', filters.amountMin.toString());
    if (filters.amountMax != null) params = params.set('amountMax', filters.amountMax.toString());
    if (filters.categoryId) params = params.set('categoryId', filters.categoryId);
    if (filters.search) params = params.set('search', filters.search);
    return this.http.get<Page<TransactionResponse>>(
      `/api/accounts/${accountId}/transactions`,
      { params },
    );
  }

  createTransaction(
    accountId: string,
    request: CreateTransactionRequest,
  ): Observable<TransactionResponse> {
    return this.http.post<TransactionResponse>(
      `/api/accounts/${accountId}/transactions`,
      request,
    );
  }

  updateTransaction(id: string, request: UpdateTransactionRequest): Observable<TransactionResponse> {
    return this.http.put<TransactionResponse>(`/api/transactions/${id}`, request);
  }

  deleteTransaction(id: string): Observable<void> {
    return this.http.delete<void>(`/api/transactions/${id}`);
  }

  togglePointed(id: string): Observable<TransactionResponse> {
    return this.http.patch<TransactionResponse>(`/api/transactions/${id}/pointed`, {});
  }
}
