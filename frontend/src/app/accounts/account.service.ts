import { Injectable, inject, signal } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable, tap } from 'rxjs';
import {
  AccountResponse,
  CreateAccountRequest,
  UpdateAccountRequest,
  AccountAccessResponse,
  SetAccessRequest,
} from './account.types';
import { UserResponse } from '../auth/auth.types';

@Injectable({ providedIn: 'root' })
export class AccountService {
  private readonly http = inject(HttpClient);
  private accountsSignal = signal<AccountResponse[]>([]);

  readonly accounts = this.accountsSignal.asReadonly();

  loadAccounts(includeArchived = false): Observable<AccountResponse[]> {
    let params = new HttpParams();
    if (includeArchived) {
      params = params.set('includeArchived', 'true');
    }
    return this.http
      .get<AccountResponse[]>('/api/accounts', { params })
      .pipe(tap((accounts: AccountResponse[]) => this.accountsSignal.set(accounts)));
  }

  createAccount(request: CreateAccountRequest): Observable<AccountResponse> {
    return this.http.post<AccountResponse>('/api/accounts', request);
  }

  updateAccount(id: string, request: UpdateAccountRequest): Observable<AccountResponse> {
    return this.http.patch<AccountResponse>(`/api/accounts/${id}`, request);
  }

  getAccessEntries(accountId: string): Observable<AccountAccessResponse[]> {
    return this.http.get<AccountAccessResponse[]>(`/api/accounts/${accountId}/access`);
  }

  setAccess(accountId: string, request: SetAccessRequest): Observable<AccountAccessResponse> {
    return this.http.post<AccountAccessResponse>(`/api/accounts/${accountId}/access`, request);
  }

  removeAccess(accountId: string, accessId: string): Observable<void> {
    return this.http.delete<void>(`/api/accounts/${accountId}/access/${accessId}`);
  }

  loadUsers(): Observable<UserResponse[]> {
    return this.http.get<UserResponse[]>('/api/users');
  }
}
