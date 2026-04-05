import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { AccountService } from './account.service';
import {
  AccountResponse,
  AccountAccessResponse,
  CreateAccountRequest,
  UpdateAccountRequest,
  SetAccessRequest,
} from './account.types';
import { UserResponse } from '../auth/auth.types';

const mockAccount: AccountResponse = {
  id: 'acc-1',
  name: 'Compte courant',
  accountType: 'PERSONAL',
  balance: 150000,
  currency: 'EUR',
  archived: false,
  createdAt: '2026-01-01T00:00:00Z',
  currentUserAccessLevel: 'ADMIN',
};

const mockAccess: AccountAccessResponse = {
  id: 'access-1',
  userId: 'user-1',
  userEmail: 'user@test.com',
  userDisplayName: 'Test User',
  accessLevel: 'READ',
};

describe('AccountService', () => {
  let service: AccountService;
  let httpTesting: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(AccountService);
    httpTesting = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpTesting.verify();
  });

  it('loadAccounts_should_GET_api_accounts_and_update_signal', () => {
    // Arrange
    const mockAccounts = [mockAccount];

    // Act
    service.loadAccounts().subscribe();

    const req = httpTesting.expectOne((r) => r.url === '/api/accounts' && r.method === 'GET');
    req.flush(mockAccounts);

    // Assert
    expect(service.accounts()).toEqual(mockAccounts);
  });

  it('loadAccounts_with_includeArchived_should_pass_query_param', () => {
    // Arrange
    const mockAccounts = [mockAccount];

    // Act
    service.loadAccounts(true).subscribe();

    const req = httpTesting.expectOne(
      (r) =>
        r.url === '/api/accounts' && r.method === 'GET' && r.params.get('includeArchived') === 'true',
    );
    req.flush(mockAccounts);

    // Assert
    expect(service.accounts()).toEqual(mockAccounts);
  });

  it('createAccount_should_POST_api_accounts', () => {
    // Arrange
    const createRequest: CreateAccountRequest = { name: 'Épargne', accountType: 'PERSONAL' };

    // Act
    service.createAccount(createRequest).subscribe();

    const req = httpTesting.expectOne('/api/accounts');

    // Assert
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual(createRequest);
    req.flush(mockAccount);
  });

  it('updateAccount_should_PATCH_api_accounts_id', () => {
    // Arrange
    const updateRequest: UpdateAccountRequest = { name: 'Nouveau nom', archived: false };

    // Act
    service.updateAccount('acc-1', updateRequest).subscribe();

    const req = httpTesting.expectOne('/api/accounts/acc-1');

    // Assert
    expect(req.request.method).toBe('PATCH');
    expect(req.request.body).toEqual(updateRequest);
    req.flush(mockAccount);
  });

  it('getAccessEntries_should_GET_api_accounts_id_access', () => {
    // Arrange
    const mockAccessList = [mockAccess];

    // Act
    service.getAccessEntries('acc-1').subscribe();

    const req = httpTesting.expectOne('/api/accounts/acc-1/access');

    // Assert
    expect(req.request.method).toBe('GET');
    req.flush(mockAccessList);
  });

  it('setAccess_should_POST_api_accounts_id_access', () => {
    // Arrange
    const setRequest: SetAccessRequest = { userId: 'user-1', accessLevel: 'WRITE' };

    // Act
    service.setAccess('acc-1', setRequest).subscribe();

    const req = httpTesting.expectOne('/api/accounts/acc-1/access');

    // Assert
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual(setRequest);
    req.flush(mockAccess);
  });

  it('removeAccess_should_DELETE_api_accounts_id_access_accessId', () => {
    // Act
    service.removeAccess('acc-1', 'access-1').subscribe();

    const req = httpTesting.expectOne('/api/accounts/acc-1/access/access-1');

    // Assert
    expect(req.request.method).toBe('DELETE');
    req.flush(null);
  });

  it('loadUsers_should_GET_api_users', () => {
    // Arrange
    const mockUsers: UserResponse[] = [
      { id: 'user-1', displayName: 'Admin', email: 'admin@test.com', role: 'ADMIN' },
    ];

    // Act
    service.loadUsers().subscribe();

    const req = httpTesting.expectOne('/api/users');

    // Assert
    expect(req.request.method).toBe('GET');
    req.flush(mockUsers);
  });
});
