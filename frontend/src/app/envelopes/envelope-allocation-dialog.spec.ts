import { TestBed } from '@angular/core/testing';
import { LOCALE_ID } from '@angular/core';
import { registerLocaleData } from '@angular/common';
import localeFr from '@angular/common/locales/fr';
import { provideHttpClient } from '@angular/common/http';
import {
  provideHttpClientTesting,
  HttpTestingController,
} from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { EnvelopeAllocationDialog } from './envelope-allocation-dialog';
import {
  EnvelopeAllocationResponse,
  EnvelopeResponse,
} from './envelope.types';

registerLocaleData(localeFr);

const makeEnvelope = (partial: Partial<EnvelopeResponse> = {}): EnvelopeResponse => ({
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
  ...partial,
});

const makeAllocation = (
  partial: Partial<EnvelopeAllocationResponse> = {},
): EnvelopeAllocationResponse => ({
  id: 'alloc-1',
  envelopeId: 'env-1',
  month: '2026-04',
  allocatedAmount: 800,
  createdAt: '2026-04-01T00:00:00Z',
  ...partial,
});

function setupDialog(envelope: EnvelopeResponse | null) {
  TestBed.configureTestingModule({
    imports: [EnvelopeAllocationDialog],
    providers: [
      provideHttpClient(),
      provideHttpClientTesting(),
      provideRouter([]),
      { provide: LOCALE_ID, useValue: 'fr-FR' },
    ],
  });
  const httpMock = TestBed.inject(HttpTestingController);
  const fixture = TestBed.createComponent(EnvelopeAllocationDialog);
  fixture.componentRef.setInput('visible', true);
  fixture.componentRef.setInput('envelope', envelope);
  fixture.detectChanges();
  return { fixture, httpMock };
}

describe('EnvelopeAllocationDialog', () => {
  let httpMock: HttpTestingController;

  afterEach(() => {
    httpMock.verify();
  });

  it('defaults_month_to_current_month_when_opened_without_context', () => {
    // Arrange & Act
    const { fixture, httpMock: mock } = setupDialog(makeEnvelope());
    httpMock = mock;
    // Flush the initial listAllocations call.
    httpMock.expectOne('/api/envelopes/env-1/allocations').flush([]);

    // Assert
    const month = fixture.componentInstance['month'] as Date;
    const now = new Date();
    expect(month.getMonth()).toBe(now.getMonth());
    expect(month.getFullYear()).toBe(now.getFullYear());
  });

  it('disables_save_when_allocatedAmount_is_null', () => {
    // Arrange
    const { fixture, httpMock: mock } = setupDialog(makeEnvelope());
    httpMock = mock;
    httpMock.expectOne('/api/envelopes/env-1/allocations').flush([]);
    fixture.componentInstance['allocatedAmount'] = null;

    // Act
    const isValid = fixture.componentInstance['isValid']();

    // Assert
    expect(isValid).toBe(false);
  });

  it('emits_saved_when_service_createAllocation_succeeds', () => {
    // Arrange
    const { fixture, httpMock: mock } = setupDialog(makeEnvelope());
    httpMock = mock;
    httpMock.expectOne('/api/envelopes/env-1/allocations').flush([]);
    fixture.componentInstance['allocatedAmount'] = 800;
    fixture.componentInstance['month'] = new Date(2026, 3, 1); // April 2026
    let emitted: EnvelopeAllocationResponse | null = null;
    fixture.componentInstance.saved.subscribe((a) => (emitted = a));

    // Act
    fixture.componentInstance['save']();

    // Assert
    const req = httpMock.expectOne('/api/envelopes/env-1/allocations');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ month: '2026-04', allocatedAmount: 800 });
    req.flush(makeAllocation());
    expect(emitted).not.toBeNull();
  });

  it('shows_409_error_when_month_already_has_an_allocation', () => {
    // Arrange
    const { fixture, httpMock: mock } = setupDialog(makeEnvelope());
    httpMock = mock;
    httpMock.expectOne('/api/envelopes/env-1/allocations').flush([]);
    fixture.componentInstance['allocatedAmount'] = 800;
    fixture.componentInstance['month'] = new Date(2026, 3, 1);

    // Act
    fixture.componentInstance['save']();
    httpMock
      .expectOne('/api/envelopes/env-1/allocations')
      .flush({ message: 'conflict' }, { status: 409, statusText: 'Conflict' });

    // Assert
    expect(fixture.componentInstance['error']()).toBe(
      'Un budget personnalise existe deja pour ce mois. Modifiez-le depuis la liste ci-dessous.',
    );
  });

  it('lists_existing_overrides_ordered_by_month', () => {
    // Arrange
    const envelope = makeEnvelope();
    const mar = makeAllocation({ id: 'a-mar', month: '2026-03', allocatedAmount: 700 });
    const may = makeAllocation({ id: 'a-may', month: '2026-05', allocatedAmount: 900 });
    const apr = makeAllocation({ id: 'a-apr', month: '2026-04', allocatedAmount: 800 });

    // Act — allocations returned in unsorted order
    const { fixture, httpMock: mock } = setupDialog(envelope);
    httpMock = mock;
    httpMock
      .expectOne('/api/envelopes/env-1/allocations')
      .flush([may, mar, apr]);

    // Assert
    const listed = fixture.componentInstance['existingAllocations']();
    expect(listed.map((a) => a.month)).toEqual(['2026-03', '2026-04', '2026-05']);
  });
});
