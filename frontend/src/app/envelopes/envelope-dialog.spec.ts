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
import { By } from '@angular/platform-browser';
import { EnvelopeDialog } from './envelope-dialog';
import { AccountResponse } from '../accounts/account.types';
import { EnvelopeResponse } from './envelope.types';

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

const sharedAccount = makeAccount({
  id: 'acc-shared',
  name: 'Compte commun',
  accountType: 'SHARED',
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
  consumed: 0,
  available: 500,
  ratio: 0,
  status: 'GREEN',
  hasMonthlyOverride: false,
  archived: false,
  createdAt: '2026-04-01T00:00:00Z',
  ...partial,
});

describe('EnvelopeDialog', () => {
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [EnvelopeDialog],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        { provide: LOCALE_ID, useValue: 'fr-FR' },
      ],
    });
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('disables_save_button_when_name_is_blank', () => {
    // Arrange
    const fixture = TestBed.createComponent(EnvelopeDialog);
    fixture.componentRef.setInput('visible', true);
    fixture.componentRef.setInput('accounts', [makeAccount()]);
    fixture.componentRef.setInput('mode', 'create');
    fixture.detectChanges();
    fixture.componentInstance['selectedAccountId'] = 'acc-1';
    fixture.componentInstance['selectedCategoryIds'].set(['cat-1']);
    fixture.componentInstance['budget'] = 500;
    fixture.componentInstance['name'] = '';
    fixture.detectChanges();

    // Act
    const isValid = fixture.componentInstance['isValid']();

    // Assert
    expect(isValid).toBe(false);
  });

  it('disables_save_button_when_no_category_selected', () => {
    // Arrange
    const fixture = TestBed.createComponent(EnvelopeDialog);
    fixture.componentRef.setInput('visible', true);
    fixture.componentRef.setInput('accounts', [makeAccount()]);
    fixture.componentRef.setInput('mode', 'create');
    fixture.detectChanges();
    fixture.componentInstance['selectedAccountId'] = 'acc-1';
    fixture.componentInstance['name'] = 'Test';
    fixture.componentInstance['budget'] = 500;
    fixture.componentInstance['selectedCategoryIds'].set([]);
    fixture.detectChanges();

    // Act
    const isValid = fixture.componentInstance['isValid']();

    // Assert
    expect(isValid).toBe(false);
  });

  it('disables_save_button_when_budget_is_null', () => {
    // Arrange
    const fixture = TestBed.createComponent(EnvelopeDialog);
    fixture.componentRef.setInput('visible', true);
    fixture.componentRef.setInput('accounts', [makeAccount()]);
    fixture.componentRef.setInput('mode', 'create');
    fixture.detectChanges();
    fixture.componentInstance['selectedAccountId'] = 'acc-1';
    fixture.componentInstance['name'] = 'Test';
    fixture.componentInstance['selectedCategoryIds'].set(['cat-1']);
    fixture.componentInstance['budget'] = null;
    fixture.detectChanges();

    // Act
    const isValid = fixture.componentInstance['isValid']();

    // Assert
    expect(isValid).toBe(false);
  });

  it('enables_save_button_when_all_required_fields_are_filled', () => {
    // Arrange
    const fixture = TestBed.createComponent(EnvelopeDialog);
    fixture.componentRef.setInput('visible', true);
    fixture.componentRef.setInput('accounts', [makeAccount()]);
    fixture.componentRef.setInput('mode', 'create');
    fixture.detectChanges();
    fixture.componentInstance['selectedAccountId'] = 'acc-1';
    fixture.componentInstance['name'] = 'Vie quotidienne';
    fixture.componentInstance['selectedCategoryIds'].set(['cat-1']);
    fixture.componentInstance['budget'] = 500;
    fixture.detectChanges();

    // Act
    const isValid = fixture.componentInstance['isValid']();

    // Assert
    expect(isValid).toBe(true);
  });

  it('emits_saved_when_service_createEnvelope_succeeds', () => {
    // Arrange
    const fixture = TestBed.createComponent(EnvelopeDialog);
    fixture.componentRef.setInput('visible', true);
    fixture.componentRef.setInput('accounts', [makeAccount()]);
    fixture.componentRef.setInput('mode', 'create');
    fixture.detectChanges();
    fixture.componentInstance['selectedAccountId'] = 'acc-1';
    fixture.componentInstance['name'] = 'Vie quotidienne';
    fixture.componentInstance['selectedCategoryIds'].set(['cat-1']);
    fixture.componentInstance['budget'] = 500;
    fixture.detectChanges();
    let emitted: EnvelopeResponse | null = null;
    fixture.componentInstance.saved.subscribe((env) => (emitted = env));

    // Act
    fixture.componentInstance['save']();

    // Assert
    const req = httpMock.expectOne('/api/accounts/acc-1/envelopes');
    expect(req.request.method).toBe('POST');
    req.flush(makeEnvelope());
    expect(emitted).not.toBeNull();
  });

  it('shows_409_error_message_when_service_returns_conflict', () => {
    // Arrange
    const fixture = TestBed.createComponent(EnvelopeDialog);
    fixture.componentRef.setInput('visible', true);
    fixture.componentRef.setInput('accounts', [makeAccount()]);
    fixture.componentRef.setInput('mode', 'create');
    fixture.detectChanges();
    fixture.componentInstance['selectedAccountId'] = 'acc-1';
    fixture.componentInstance['name'] = 'Vie quotidienne';
    fixture.componentInstance['selectedCategoryIds'].set(['cat-1']);
    fixture.componentInstance['budget'] = 500;
    fixture.detectChanges();

    // Act
    fixture.componentInstance['save']();
    httpMock
      .expectOne('/api/accounts/acc-1/envelopes')
      .flush({ message: 'conflict' }, { status: 409, statusText: 'Conflict' });

    // Assert
    expect(fixture.componentInstance['error']()).toBe(
      'Une categorie selectionnee appartient deja a une autre enveloppe de ce compte. Choisissez des categories libres.',
    );
  });

  it('shows_403_error_message_when_service_returns_forbidden', () => {
    // Arrange
    const fixture = TestBed.createComponent(EnvelopeDialog);
    fixture.componentRef.setInput('visible', true);
    fixture.componentRef.setInput('accounts', [makeAccount()]);
    fixture.componentRef.setInput('mode', 'create');
    fixture.detectChanges();
    fixture.componentInstance['selectedAccountId'] = 'acc-1';
    fixture.componentInstance['name'] = 'Vie quotidienne';
    fixture.componentInstance['selectedCategoryIds'].set(['cat-1']);
    fixture.componentInstance['budget'] = 500;
    fixture.detectChanges();

    // Act
    fixture.componentInstance['save']();
    httpMock
      .expectOne('/api/accounts/acc-1/envelopes')
      .flush({ message: 'forbidden' }, { status: 403, statusText: 'Forbidden' });

    // Assert
    expect(fixture.componentInstance['error']()).toBe(
      "Vous n'avez pas les droits pour modifier les enveloppes de ce compte.",
    );
  });

  it('shows_generic_error_message_for_500', () => {
    // Arrange
    const fixture = TestBed.createComponent(EnvelopeDialog);
    fixture.componentRef.setInput('visible', true);
    fixture.componentRef.setInput('accounts', [makeAccount()]);
    fixture.componentRef.setInput('mode', 'create');
    fixture.detectChanges();
    fixture.componentInstance['selectedAccountId'] = 'acc-1';
    fixture.componentInstance['name'] = 'Vie quotidienne';
    fixture.componentInstance['selectedCategoryIds'].set(['cat-1']);
    fixture.componentInstance['budget'] = 500;
    fixture.detectChanges();

    // Act
    fixture.componentInstance['save']();
    httpMock
      .expectOne('/api/accounts/acc-1/envelopes')
      .flush({ message: 'boom' }, { status: 500, statusText: 'Server Error' });

    // Assert
    expect(fixture.componentInstance['error']()).toBe(
      "Impossible d'enregistrer l'enveloppe. Veuillez reessayer.",
    );
  });

  it('renders_scope_tag_Commun_with_severity_info_when_selected_account_is_SHARED', () => {
    // Arrange
    const fixture = TestBed.createComponent(EnvelopeDialog);
    fixture.componentRef.setInput('visible', true);
    fixture.componentRef.setInput('accounts', [sharedAccount]);
    fixture.componentRef.setInput('mode', 'create');
    fixture.componentRef.setInput('lockedAccountId', sharedAccount.id);
    fixture.detectChanges();

    // Act
    const tags = fixture.debugElement.queryAll(By.css('p-tag'));

    // Assert
    const commun = tags.find((t) => t.componentInstance.value === 'Commun');
    expect(commun).toBeTruthy();
    expect(commun!.componentInstance.severity).toBe('info');
  });

  it('renders_scope_tag_Personnel_with_severity_secondary_when_selected_account_is_PERSONAL', () => {
    // Arrange
    const fixture = TestBed.createComponent(EnvelopeDialog);
    fixture.componentRef.setInput('visible', true);
    fixture.componentRef.setInput('accounts', [makeAccount()]);
    fixture.componentRef.setInput('mode', 'create');
    fixture.componentRef.setInput('lockedAccountId', 'acc-1');
    fixture.detectChanges();

    // Act
    const tags = fixture.debugElement.queryAll(By.css('p-tag'));

    // Assert
    const personnel = tags.find((t) => t.componentInstance.value === 'Personnel');
    expect(personnel).toBeTruthy();
    expect(personnel!.componentInstance.severity).toBe('secondary');
  });

  it('locks_Compte_field_as_disabled_in_edit_mode', () => {
    // Arrange
    const env = makeEnvelope();
    const fixture = TestBed.createComponent(EnvelopeDialog);
    fixture.componentRef.setInput('visible', true);
    fixture.componentRef.setInput('accounts', [makeAccount()]);
    fixture.componentRef.setInput('mode', 'edit');
    fixture.componentRef.setInput('envelope', env);
    fixture.detectChanges();

    // Act
    const selects = fixture.debugElement.queryAll(By.css('p-select'));

    // Assert
    const accountSelect = selects[0];
    expect(accountSelect).toBeTruthy();
    // PrimeNG 21 exposes inputs as signal-like input functions.
    const disabled = accountSelect.componentInstance.disabled;
    const disabledValue = typeof disabled === 'function' ? disabled() : disabled;
    expect(disabledValue).toBe(true);
  });
});
