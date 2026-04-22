import { TestBed } from '@angular/core/testing';
import { LOCALE_ID } from '@angular/core';
import { registerLocaleData } from '@angular/common';
import localeFr from '@angular/common/locales/fr';
import { provideHttpClient } from '@angular/common/http';
import {
  provideHttpClientTesting,
  HttpTestingController,
} from '@angular/common/http/testing';
import { ActivatedRoute, Router, convertToParamMap } from '@angular/router';
import { provideRouter } from '@angular/router';
import { By } from '@angular/platform-browser';
import { of } from 'rxjs';
import { EnvelopeDetailsPage } from './envelope-details';
import { EnvelopeHistoryEntry, EnvelopeResponse } from './envelope.types';
import { AccountResponse } from '../accounts/account.types';

registerLocaleData(localeFr);

const makeAccount = (partial: Partial<AccountResponse> = {}): AccountResponse => ({
  id: 'acc-1',
  name: 'Compte courant',
  accountType: 'PERSONAL',
  balance: 1000,
  currency: 'EUR',
  archived: false,
  createdAt: '2026-01-01T00:00:00Z',
  currentUserAccessLevel: 'WRITE',
  ...partial,
});

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
  consumed: 100,
  available: 400,
  ratio: 0.2,
  status: 'GREEN',
  hasMonthlyOverride: false,
  archived: false,
  createdAt: '2026-04-01T00:00:00Z',
  ...partial,
});

const zeroHistory = (): EnvelopeHistoryEntry[] =>
  Array.from({ length: 12 }, (_, i) => ({
    month: `2026-${String(i + 1).padStart(2, '0')}`,
    effectiveBudget: 500,
    consumed: 0,
    available: 500,
    ratio: 0,
    status: 'GREEN' as const,
  }));

const busyHistory = (): EnvelopeHistoryEntry[] =>
  Array.from({ length: 12 }, (_, i) => ({
    month: `2026-${String(i + 1).padStart(2, '0')}`,
    effectiveBudget: 500,
    consumed: 100 + i,
    available: 400 - i,
    ratio: 0.2 + i * 0.01,
    status: 'GREEN' as const,
  }));

function setupComponent(
  envelope: EnvelopeResponse,
  history: EnvelopeHistoryEntry[],
  accounts: AccountResponse[] = [makeAccount()],
) {
  const routeStub = {
    paramMap: of(convertToParamMap({ id: envelope.id })),
    snapshot: { paramMap: convertToParamMap({ id: envelope.id }) },
  };
  TestBed.configureTestingModule({
    imports: [EnvelopeDetailsPage],
    providers: [
      provideHttpClient(),
      provideHttpClientTesting(),
      provideRouter([]),
      { provide: LOCALE_ID, useValue: 'fr-FR' },
      { provide: ActivatedRoute, useValue: routeStub },
    ],
  });

  const httpMock = TestBed.inject(HttpTestingController);
  const fixture = TestBed.createComponent(EnvelopeDetailsPage);

  // Constructor triggers: accounts, categories, envelope, history (in that order).
  httpMock.expectOne('/api/accounts').flush(accounts);
  httpMock.expectOne('/api/categories').flush([]);
  httpMock.expectOne(`/api/envelopes/${envelope.id}`).flush(envelope);
  httpMock.expectOne(`/api/envelopes/${envelope.id}/history`).flush(history);
  fixture.detectChanges();
  return { fixture, httpMock };
}

describe('EnvelopeDetailsPage', () => {
  let httpMock: HttpTestingController;

  afterEach(() => {
    httpMock.verify();
  });

  it('renders_the_envelope_name_in_the_page_header', () => {
    // Arrange & Act
    const { fixture, httpMock: mock } = setupComponent(
      makeEnvelope(),
      busyHistory(),
    );
    httpMock = mock;

    // Assert
    const heading = fixture.debugElement.query(By.css('h1'));
    expect(heading.nativeElement.textContent).toContain('Vie quotidienne');
  });

  it('renders_12_rows_in_the_history_table', () => {
    // Arrange & Act
    const { fixture, httpMock: mock } = setupComponent(
      makeEnvelope(),
      busyHistory(),
    );
    httpMock = mock;

    // Assert
    const bodyRows = fixture.debugElement.queryAll(
      By.css('p-table tbody tr'),
    );
    expect(bodyRows.length).toBe(12);
  });

  it('renders_pas_encore_historique_empty_state_when_all_months_have_zero_consumed', () => {
    // Arrange & Act
    const { fixture, httpMock: mock } = setupComponent(
      makeEnvelope({ consumed: 0 }),
      zeroHistory(),
    );
    httpMock = mock;

    // Assert
    const emptyState = fixture.debugElement.query(By.css('[role="status"]'));
    expect(emptyState).toBeTruthy();
    expect(emptyState.nativeElement.textContent).toContain("Pas encore d'historique");
  });

  it('shows_personnaliser_ce_mois_button_in_the_header', () => {
    // Arrange & Act
    const { fixture, httpMock: mock } = setupComponent(
      makeEnvelope(),
      busyHistory(),
    );
    httpMock = mock;

    // Assert
    const buttons = fixture.debugElement.queryAll(By.css('p-button'));
    const found = buttons.find((b) =>
      (b.nativeElement.textContent ?? '').includes('Personnaliser ce mois'),
    );
    expect(found).toBeTruthy();
  });

  it('opens_edit_dialog_when_modifier_button_clicked', () => {
    // Arrange
    const { fixture, httpMock: mock } = setupComponent(
      makeEnvelope(),
      busyHistory(),
    );
    httpMock = mock;

    // Act
    fixture.componentInstance['openEditDialog']();
    fixture.detectChanges();

    // Assert
    const dialog = fixture.debugElement.query(By.css('app-envelope-dialog'));
    expect(dialog).toBeTruthy();
  });

  it('navigates_to_envelopes_after_successful_delete_confirmation', () => {
    // Arrange
    const { fixture, httpMock: mock } = setupComponent(
      makeEnvelope(),
      busyHistory(),
    );
    httpMock = mock;
    const router = TestBed.inject(Router);
    const navigateSpy = vi.spyOn(router, 'navigate').mockResolvedValue(true);
    // Stub ConfirmationService so the accept callback runs synchronously.
    const confirmationService = fixture.componentInstance['confirmationService'];
    vi.spyOn(confirmationService, 'confirm').mockImplementation((opts) => {
      opts.accept?.();
      return confirmationService;
    });

    // Act
    fixture.componentInstance['confirmArchive']();
    httpMock.expectOne('/api/envelopes/env-1').flush(null);

    // Assert
    expect(navigateSpy).toHaveBeenCalledWith(['/envelopes']);
  });
});
