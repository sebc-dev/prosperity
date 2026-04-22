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
import { ActivatedRoute } from '@angular/router';
import { convertToParamMap } from '@angular/router';
import { By } from '@angular/platform-browser';
import { of } from 'rxjs';
import { EnvelopesPage } from './envelopes';
import { EnvelopeResponse } from './envelope.types';
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

function createComponent(
  envelopes: EnvelopeResponse[],
  accounts: AccountResponse[] = [makeAccount()],
  queryParams: Record<string, string> = {},
) {
  const routeStub = {
    queryParamMap: of(convertToParamMap(queryParams)),
    queryParams: of(queryParams),
    snapshot: { queryParamMap: convertToParamMap(queryParams) },
  };

  TestBed.configureTestingModule({
    imports: [EnvelopesPage],
    providers: [
      provideHttpClient(),
      provideHttpClientTesting(),
      provideRouter([]),
      { provide: LOCALE_ID, useValue: 'fr-FR' },
      { provide: ActivatedRoute, useValue: routeStub },
    ],
  });

  const httpMock = TestBed.inject(HttpTestingController);
  const fixture = TestBed.createComponent(EnvelopesPage);

  // Constructor triggers: /api/accounts, /api/categories, /api/envelopes
  httpMock.expectOne('/api/accounts').flush(accounts);
  httpMock.expectOne('/api/categories').flush([]);
  const envReq = httpMock.expectOne((r) => r.url === '/api/envelopes');
  envReq.flush(envelopes);
  fixture.detectChanges();

  return { fixture, httpMock };
}

describe('EnvelopesPage', () => {
  let httpMock: HttpTestingController;

  afterEach(() => {
    httpMock.verify();
  });

  it('renders_status_tag_with_severity_success_when_status_is_GREEN', () => {
    // Arrange
    const env = makeEnvelope({ status: 'GREEN', ratio: 0.5 });

    // Act
    const { fixture, httpMock: mock } = createComponent([env]);
    httpMock = mock;

    // Assert
    const tags = fixture.debugElement.queryAll(By.css('p-tag'));
    const statusTag = tags.find(
      (t) => t.componentInstance.value === 'Sur la bonne voie',
    );
    expect(statusTag).toBeTruthy();
    expect(statusTag!.componentInstance.severity).toBe('success');
  });

  it('renders_status_tag_with_severity_warn_when_status_is_YELLOW', () => {
    // Arrange
    const env = makeEnvelope({ status: 'YELLOW', ratio: 0.9 });

    // Act
    const { fixture, httpMock: mock } = createComponent([env]);
    httpMock = mock;

    // Assert
    const tags = fixture.debugElement.queryAll(By.css('p-tag'));
    const statusTag = tags.find((t) => t.componentInstance.value === 'Attention');
    expect(statusTag).toBeTruthy();
    expect(statusTag!.componentInstance.severity).toBe('warn');
  });

  it('renders_status_tag_with_severity_danger_when_status_is_RED', () => {
    // Arrange
    const env = makeEnvelope({ status: 'RED', ratio: 1.1 });

    // Act
    const { fixture, httpMock: mock } = createComponent([env]);
    httpMock = mock;

    // Assert
    const tags = fixture.debugElement.queryAll(By.css('p-tag'));
    const statusTag = tags.find((t) => t.componentInstance.value === 'Depasse');
    expect(statusTag).toBeTruthy();
    expect(statusTag!.componentInstance.severity).toBe('danger');
  });

  it('clamps_progressbar_value_at_100_when_ratio_exceeds_1', () => {
    // Arrange
    const env = makeEnvelope({ status: 'RED', ratio: 1.25 });

    // Act
    const { fixture, httpMock: mock } = createComponent([env]);
    httpMock = mock;

    // Assert
    const progressbar = fixture.debugElement.query(By.css('p-progressbar'));
    expect(progressbar).toBeTruthy();
    expect(progressbar.componentInstance.value).toBe(100);
  });

  it('shows_Report_tag_when_rolloverPolicy_is_CARRY_OVER', () => {
    // Arrange
    const env = makeEnvelope({ rolloverPolicy: 'CARRY_OVER' });

    // Act
    const { fixture, httpMock: mock } = createComponent([env]);
    httpMock = mock;

    // Assert
    const tags = fixture.debugElement.queryAll(By.css('p-tag'));
    const reportTag = tags.find((t) => t.componentInstance.value === 'Report');
    expect(reportTag).toBeTruthy();
  });

  it('renders_account_name_in_header_when_accountId_filter_is_active', () => {
    // Arrange
    const env = makeEnvelope();

    // Act
    const { fixture, httpMock: mock } = createComponent([env], [makeAccount()], {
      accountId: 'acc-1',
    });
    httpMock = mock;

    // Assert
    const heading = fixture.debugElement.query(By.css('h1'));
    expect(heading.nativeElement.textContent).toContain('Compte courant');
  });

  it('renders_no_envelopes_empty_state_when_list_empty_and_no_filters', () => {
    // Arrange & Act
    const { fixture, httpMock: mock } = createComponent([]);
    httpMock = mock;

    // Assert
    const emptyState = fixture.debugElement.query(By.css('[role="status"]'));
    expect(emptyState).toBeTruthy();
    expect(emptyState.nativeElement.textContent).toContain('Aucune enveloppe');
  });

  it('renders_filtered_empty_state_when_filters_applied_but_no_match', () => {
    // Arrange & Act
    const { fixture, httpMock: mock } = createComponent([], [makeAccount()], {
      accountId: 'acc-1',
    });
    httpMock = mock;

    // Assert
    const emptyState = fixture.debugElement.query(By.css('[role="status"]'));
    expect(emptyState).toBeTruthy();
    expect(emptyState.nativeElement.textContent).toContain(
      'Aucune enveloppe ne correspond',
    );
  });

  it('renders_no_accounts_empty_state_when_accounts_list_is_empty', () => {
    // Arrange & Act
    const { fixture, httpMock: mock } = createComponent([], []);
    httpMock = mock;

    // Assert
    const emptyState = fixture.debugElement.query(By.css('[role="status"]'));
    expect(emptyState).toBeTruthy();
    expect(emptyState.nativeElement.textContent).toContain('Aucun compte disponible');
  });

  it('hides_action_buttons_when_user_has_READ_only_access_on_envelope_account', () => {
    // Arrange
    const readOnlyAccount = makeAccount({ currentUserAccessLevel: 'READ' });
    const env = makeEnvelope({ bankAccountId: readOnlyAccount.id });

    // Act
    const { fixture, httpMock: mock } = createComponent([env], [readOnlyAccount]);
    httpMock = mock;

    // Assert
    const editButton = fixture.debugElement.query(
      By.css('[aria-label="Modifier Vie quotidienne"]'),
    );
    const archiveButton = fixture.debugElement.query(
      By.css('[aria-label="Archiver Vie quotidienne"]'),
    );
    expect(editButton).toBeNull();
    expect(archiveButton).toBeNull();
  });
});
