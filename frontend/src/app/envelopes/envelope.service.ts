import { Injectable, inject, signal } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable, tap } from 'rxjs';
import {
  EnvelopeResponse,
  EnvelopeAllocationResponse,
  EnvelopeHistoryEntry,
  CreateEnvelopeRequest,
  UpdateEnvelopeRequest,
  EnvelopeAllocationRequest,
  EnvelopeListFilters,
} from './envelope.types';

@Injectable({ providedIn: 'root' })
export class EnvelopeService {
  private readonly http = inject(HttpClient);

  /** In-memory cache used by the list page; pages may also read directly from observables. */
  private readonly _envelopes = signal<EnvelopeResponse[]>([]);
  readonly envelopes = this._envelopes.asReadonly();

  // ----- Envelopes -----

  loadEnvelopes(filters: EnvelopeListFilters = {}): Observable<EnvelopeResponse[]> {
    let params = new HttpParams();
    if (filters.accountId) params = params.set('accountId', filters.accountId);
    if (filters.includeArchived) params = params.set('includeArchived', 'true');
    return this.http
      .get<EnvelopeResponse[]>('/api/envelopes', { params })
      .pipe(tap((list) => this._envelopes.set(list)));
  }

  loadEnvelopesForAccount(
    accountId: string,
    includeArchived = false,
  ): Observable<EnvelopeResponse[]> {
    let params = new HttpParams();
    if (includeArchived) params = params.set('includeArchived', 'true');
    return this.http
      .get<EnvelopeResponse[]>(`/api/accounts/${accountId}/envelopes`, { params })
      .pipe(tap((list) => this._envelopes.set(list)));
  }

  getEnvelope(id: string): Observable<EnvelopeResponse> {
    return this.http.get<EnvelopeResponse>(`/api/envelopes/${id}`);
  }

  createEnvelope(
    accountId: string,
    request: CreateEnvelopeRequest,
  ): Observable<EnvelopeResponse> {
    return this.http.post<EnvelopeResponse>(
      `/api/accounts/${accountId}/envelopes`,
      request,
    );
  }

  updateEnvelope(
    id: string,
    request: UpdateEnvelopeRequest,
  ): Observable<EnvelopeResponse> {
    return this.http.put<EnvelopeResponse>(`/api/envelopes/${id}`, request);
  }

  deleteEnvelope(id: string): Observable<void> {
    return this.http.delete<void>(`/api/envelopes/${id}`);
  }

  /** History returns 12 months ending at {@code month} (defaults to current month server-side). */
  getHistory(id: string, month?: string): Observable<EnvelopeHistoryEntry[]> {
    let params = new HttpParams();
    if (month) params = params.set('month', month);
    return this.http.get<EnvelopeHistoryEntry[]>(`/api/envelopes/${id}/history`, {
      params,
    });
  }

  // ----- Allocations -----

  listAllocations(envelopeId: string): Observable<EnvelopeAllocationResponse[]> {
    return this.http.get<EnvelopeAllocationResponse[]>(
      `/api/envelopes/${envelopeId}/allocations`,
    );
  }

  createAllocation(
    envelopeId: string,
    request: EnvelopeAllocationRequest,
  ): Observable<EnvelopeAllocationResponse> {
    return this.http.post<EnvelopeAllocationResponse>(
      `/api/envelopes/${envelopeId}/allocations`,
      request,
    );
  }

  updateAllocation(
    allocationId: string,
    request: EnvelopeAllocationRequest,
  ): Observable<EnvelopeAllocationResponse> {
    return this.http.put<EnvelopeAllocationResponse>(
      `/api/envelopes/allocations/${allocationId}`,
      request,
    );
  }

  deleteAllocation(allocationId: string): Observable<void> {
    return this.http.delete<void>(`/api/envelopes/allocations/${allocationId}`);
  }
}
