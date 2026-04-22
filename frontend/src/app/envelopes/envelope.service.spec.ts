import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import {
  provideHttpClientTesting,
  HttpTestingController,
} from '@angular/common/http/testing';
import { EnvelopeService } from './envelope.service';
import {
  CreateEnvelopeRequest,
  EnvelopeAllocationRequest,
  EnvelopeAllocationResponse,
  EnvelopeHistoryEntry,
  EnvelopeResponse,
  UpdateEnvelopeRequest,
} from './envelope.types';

const mockEnvelope: EnvelopeResponse = {
  id: 'env-1',
  bankAccountId: 'acc-1',
  bankAccountName: 'Compte courant',
  name: 'Vie quotidienne',
  scope: 'PERSONAL',
  ownerId: null,
  categories: [{ id: 'cat-1', name: 'Courses' }],
  rolloverPolicy: 'RESET',
  defaultBudget: 500,
  effectiveBudget: 500,
  consumed: 0,
  available: 500,
  ratio: 0,
  status: 'GREEN',
  hasMonthlyOverride: false,
  archived: false,
  createdAt: '2026-04-01T00:00:00Z',
};

const mockAllocation: EnvelopeAllocationResponse = {
  id: 'alloc-1',
  envelopeId: 'env-1',
  month: '2026-04',
  allocatedAmount: 800,
  createdAt: '2026-04-01T00:00:00Z',
};

describe('EnvelopeService', () => {
  let service: EnvelopeService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(EnvelopeService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
  });

  it('GET_api_envelopes_returns_envelopes', () => {
    // Arrange
    const envelopes = [mockEnvelope];

    // Act
    service.loadEnvelopes().subscribe();

    // Assert
    const req = http.expectOne((r) => r.url === '/api/envelopes' && r.method === 'GET');
    req.flush(envelopes);
    expect(service.envelopes()).toEqual(envelopes);
  });

  it('GET_api_envelopes_accountId_passes_accountId_query_param', () => {
    // Act
    service.loadEnvelopes({ accountId: 'acc-1' }).subscribe();

    // Assert
    const req = http.expectOne(
      (r) => r.url === '/api/envelopes' && r.params.get('accountId') === 'acc-1',
    );
    expect(req.request.method).toBe('GET');
    req.flush([]);
  });

  it('GET_api_envelopes_includeArchived_passes_flag', () => {
    // Act
    service.loadEnvelopes({ includeArchived: true }).subscribe();

    // Assert
    const req = http.expectOne(
      (r) =>
        r.url === '/api/envelopes' && r.params.get('includeArchived') === 'true',
    );
    expect(req.request.method).toBe('GET');
    req.flush([]);
  });

  it('GET_api_accounts_id_envelopes_calls_per_account_endpoint', () => {
    // Act
    service.loadEnvelopesForAccount('acc-1').subscribe();

    // Assert
    const req = http.expectOne('/api/accounts/acc-1/envelopes');
    expect(req.request.method).toBe('GET');
    req.flush([mockEnvelope]);
    expect(service.envelopes()).toEqual([mockEnvelope]);
  });

  it('POST_api_accounts_id_envelopes_sends_create_body', () => {
    // Arrange
    const createBody: CreateEnvelopeRequest = {
      name: 'Vie quotidienne',
      categoryIds: ['cat-1'],
      budget: 500,
      rolloverPolicy: 'RESET',
    };

    // Act
    service.createEnvelope('acc-1', createBody).subscribe();

    // Assert
    const req = http.expectOne('/api/accounts/acc-1/envelopes');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual(createBody);
    req.flush(mockEnvelope);
  });

  it('PUT_api_envelopes_id_sends_update_body', () => {
    // Arrange
    const updateBody: UpdateEnvelopeRequest = {
      name: 'Nouveau nom',
      budget: 600,
    };

    // Act
    service.updateEnvelope('env-1', updateBody).subscribe();

    // Assert
    const req = http.expectOne('/api/envelopes/env-1');
    expect(req.request.method).toBe('PUT');
    expect(req.request.body).toEqual(updateBody);
    req.flush(mockEnvelope);
  });

  it('DELETE_api_envelopes_id_returns_void', () => {
    // Act
    service.deleteEnvelope('env-1').subscribe();

    // Assert
    const req = http.expectOne('/api/envelopes/env-1');
    expect(req.request.method).toBe('DELETE');
    req.flush(null);
  });

  it('GET_api_envelopes_id_history_month_passes_month_param', () => {
    // Arrange
    const history: EnvelopeHistoryEntry[] = [];

    // Act
    service.getHistory('env-1', '2026-04').subscribe();

    // Assert
    const req = http.expectOne(
      (r) =>
        r.url === '/api/envelopes/env-1/history' &&
        r.params.get('month') === '2026-04',
    );
    expect(req.request.method).toBe('GET');
    req.flush(history);
  });

  it('GET_api_envelopes_id_allocations_returns_list', () => {
    // Act
    service.listAllocations('env-1').subscribe();

    // Assert
    const req = http.expectOne('/api/envelopes/env-1/allocations');
    expect(req.request.method).toBe('GET');
    req.flush([mockAllocation]);
  });

  it('POST_api_envelopes_id_allocations_sends_body', () => {
    // Arrange
    const createBody: EnvelopeAllocationRequest = {
      month: '2026-04',
      allocatedAmount: 800,
    };

    // Act
    service.createAllocation('env-1', createBody).subscribe();

    // Assert
    const req = http.expectOne('/api/envelopes/env-1/allocations');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual(createBody);
    req.flush(mockAllocation);
  });

  it('PUT_api_envelopes_allocations_id_sends_body', () => {
    // Arrange
    const updateBody: EnvelopeAllocationRequest = {
      month: '2026-04',
      allocatedAmount: 900,
    };

    // Act
    service.updateAllocation('alloc-1', updateBody).subscribe();

    // Assert
    const req = http.expectOne('/api/envelopes/allocations/alloc-1');
    expect(req.request.method).toBe('PUT');
    expect(req.request.body).toEqual(updateBody);
    req.flush(mockAllocation);
  });

  it('DELETE_api_envelopes_allocations_id_returns_void', () => {
    // Act
    service.deleteAllocation('alloc-1').subscribe();

    // Assert
    const req = http.expectOne('/api/envelopes/allocations/alloc-1');
    expect(req.request.method).toBe('DELETE');
    req.flush(null);
  });

  it('GET_api_envelopes_id_returns_single_envelope', () => {
    // Act
    service.getEnvelope('env-1').subscribe();

    // Assert
    const req = http.expectOne('/api/envelopes/env-1');
    expect(req.request.method).toBe('GET');
    req.flush(mockEnvelope);
  });
});
