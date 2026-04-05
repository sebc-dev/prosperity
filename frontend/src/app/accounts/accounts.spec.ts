import { TestBed } from '@angular/core/testing';
import { LOCALE_ID } from '@angular/core';
import { registerLocaleData } from '@angular/common';
import localeFr from '@angular/common/locales/fr';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { By } from '@angular/platform-browser';
import { Accounts } from './accounts';
import { AccountResponse } from './account.types';

registerLocaleData(localeFr);

const makeAccount = (partial: Partial<AccountResponse> = {}): AccountResponse => ({
  id: 'acc-1',
  name: 'Compte Test',
  accountType: 'PERSONAL',
  balance: 1000,
  currency: 'EUR',
  archived: false,
  createdAt: '2024-01-01T00:00:00Z',
  currentUserAccessLevel: 'READ',
  ...partial,
});

describe('Accounts', () => {
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Accounts],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: LOCALE_ID, useValue: 'fr-FR' },
      ],
    }).compileComponents();

    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('should create the component', () => {
    const fixture = TestBed.createComponent(Accounts);
    httpMock.expectOne('/api/accounts').flush([]);
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('should display page heading Comptes bancaires', () => {
    const fixture = TestBed.createComponent(Accounts);
    httpMock.expectOne('/api/accounts').flush([]);
    fixture.detectChanges();

    const heading = fixture.debugElement.query(By.css('h1'));
    expect(heading.nativeElement.textContent.trim()).toBe('Comptes bancaires');
  });

  it('should call loadAccounts on initialization', () => {
    TestBed.createComponent(Accounts);

    const req = httpMock.expectOne('/api/accounts');
    expect(req.request.method).toBe('GET');
    req.flush([]);
  });

  it('should display error message when loadAccounts fails', () => {
    // Arrange
    const fixture = TestBed.createComponent(Accounts);

    // Act
    httpMock.expectOne('/api/accounts').error(new ProgressEvent('network error'));
    fixture.detectChanges();

    // Assert
    const message = fixture.debugElement.query(By.css('p-message'));
    expect(message).toBeTruthy();
  });

  it('should display empty state when accounts list is empty', () => {
    // Arrange
    const fixture = TestBed.createComponent(Accounts);

    // Act
    httpMock.expectOne('/api/accounts').flush([]);
    fixture.detectChanges();

    // Assert
    const emptyState = fixture.debugElement.query(By.css('[role="status"]'));
    expect(emptyState).toBeTruthy();
    expect(emptyState.nativeElement.textContent).toContain('Aucun compte');
  });

  it('should reload with includeArchived true when toggle is activated', () => {
    // Arrange
    const fixture = TestBed.createComponent(Accounts);
    httpMock.expectOne('/api/accounts').flush([]);

    // Act
    fixture.componentInstance['includeArchived'] = true;
    fixture.componentInstance['onToggleArchived']();

    // Assert
    const req = httpMock.expectOne((r) => r.params.get('includeArchived') === 'true');
    expect(req.request.url).toBe('/api/accounts');
    req.flush([]);
  });

  it('should show edit and archive buttons for admin user', () => {
    // Arrange
    const fixture = TestBed.createComponent(Accounts);

    // Act
    httpMock.expectOne('/api/accounts').flush([makeAccount({ currentUserAccessLevel: 'ADMIN' })]);
    fixture.detectChanges();

    // Assert
    expect(fixture.debugElement.query(By.css('[aria-label="Modifier Compte Test"]'))).toBeTruthy();
    expect(fixture.debugElement.query(By.css('[aria-label="Archiver Compte Test"]'))).toBeTruthy();
  });

  it('should not show archive button for read-only user', () => {
    // Arrange
    const fixture = TestBed.createComponent(Accounts);

    // Act
    httpMock.expectOne('/api/accounts').flush([makeAccount({ currentUserAccessLevel: 'READ' })]);
    fixture.detectChanges();

    // Assert
    expect(fixture.debugElement.query(By.css('[aria-label="Archiver Compte Test"]'))).toBeNull();
    expect(fixture.debugElement.query(By.css('[aria-label="Modifier Compte Test"]'))).toBeNull();
  });

  it('should show access management button only for admin on shared account', () => {
    // Arrange
    const fixture = TestBed.createComponent(Accounts);

    // Act
    httpMock.expectOne('/api/accounts').flush([
      makeAccount({ accountType: 'SHARED', currentUserAccessLevel: 'ADMIN' }),
    ]);
    fixture.detectChanges();

    // Assert
    expect(
      fixture.debugElement.query(By.css('[aria-label="Gerer les acces de Compte Test"]')),
    ).toBeTruthy();
  });
});
