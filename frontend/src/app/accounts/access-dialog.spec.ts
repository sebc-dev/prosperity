import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { AccessDialog } from './access-dialog';
import { AccountService } from './account.service';
import { AuthService } from '../auth/auth.service';
import { AccountAccessResponse, AccountResponse } from './account.types';
import { of } from 'rxjs';
import { Select } from 'primeng/select';

function makeAccount(overrides: Partial<AccountResponse> = {}): AccountResponse {
  return {
    id: 'acc-1',
    name: 'Compte Commun',
    accountType: 'SHARED',
    balance: 0,
    currency: 'EUR',
    archived: false,
    createdAt: '2026-01-01T00:00:00Z',
    currentUserAccessLevel: 'ADMIN',
    ...overrides,
  };
}

function makeEntry(overrides: Partial<AccountAccessResponse> = {}): AccountAccessResponse {
  return {
    id: 'entry-1',
    userId: 'user-1',
    userEmail: 'alice@example.com',
    userDisplayName: 'Alice',
    accessLevel: 'ADMIN',
    ...overrides,
  };
}

describe('AccessDialog', () => {
  let fixture: ComponentFixture<AccessDialog>;
  let component: AccessDialog;
  let accountService: Partial<AccountService>;
  let authService: Partial<AuthService>;

  beforeEach(async () => {
    accountService = {
      getAccessEntries: () => of([makeEntry()]),
      loadUsers: () => of([]),
      setAccess: (_, req) =>
        of(makeEntry({ userId: req.userId, accessLevel: req.accessLevel })),
      removeAccess: () => of(undefined),
    };

    authService = {
      user: signal({ id: 'user-1', displayName: 'Alice', email: 'alice@example.com', role: 'ADMIN' }),
    };

    await TestBed.configureTestingModule({
      imports: [AccessDialog],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: AccountService, useValue: accountService },
        { provide: AuthService, useValue: authService },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(AccessDialog);
    component = fixture.componentInstance;
  });

  it('should create the component', () => {
    expect(component).toBeTruthy();
  });

  it('should show dialog header with account name', () => {
    fixture.componentRef.setInput('account', makeAccount({ name: 'Compte Test' }));
    fixture.componentRef.setInput('visible', true);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    // The p-dialog header is set via [header] input binding
    expect(compiled.querySelector('p-dialog')).toBeTruthy();
  });

  it('should resolve current user email from auth service', () => {
    // Arrange + Act
    fixture.detectChanges();

    // Assert
    expect(component['currentUserEmail']()).toBe('alice@example.com');
  });

  it('should mark current user row as disabled in the template', () => {
    // Arrange
    accountService.getAccessEntries = () =>
      of([makeEntry({ userId: 'user-1', userEmail: 'alice@example.com' })]);
    fixture.componentRef.setInput('account', makeAccount());
    fixture.componentRef.setInput('visible', true);

    // Act
    fixture.detectChanges();

    // Assert — the p-select for the current user row has [disabled]=true
    const selects = fixture.debugElement.queryAll(
      (el) => el.componentInstance instanceof Select,
    );
    expect(selects.length).toBeGreaterThan(0);
    expect(selects[0].componentInstance.disabled()).toBe(true);
  });
});
