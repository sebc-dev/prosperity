import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { AuthService } from './auth.service';
import { AuthError, UserResponse } from './auth.types';

describe('AuthService', () => {
  let service: AuthService;
  let httpTesting: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(AuthService);
    httpTesting = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpTesting.verify();
  });

  it('login_sets_current_user_on_success', () => {
    const mockUser: UserResponse = { id: 'user-1', displayName: 'Admin', email: 'admin@test.com', role: 'ADMIN' };

    service.login({ email: 'admin@test.com', password: 'SecurePass123!' }).subscribe();

    const req = httpTesting.expectOne('/api/auth/login');
    expect(req.request.method).toBe('POST');
    req.flush(mockUser);

    expect(service.isAuthenticated()).toBe(true);
    expect(service.user()?.email).toBe('admin@test.com');
  });

  it('logout_clears_current_user', () => {
    // Arrange: set user via login first
    const mockUser: UserResponse = { id: 'user-1', displayName: 'Admin', email: 'admin@test.com', role: 'ADMIN' };
    service.login({ email: 'admin@test.com', password: 'SecurePass123!' }).subscribe();
    httpTesting.expectOne('/api/auth/login').flush(mockUser);

    // Act
    service.logout().subscribe();

    const req = httpTesting.expectOne('/api/auth/logout');
    req.flush(null);

    // Assert
    expect(service.isAuthenticated()).toBe(false);
    expect(service.user()).toBeNull();
  });

  it('logout_clears_user_and_returns_typed_error_on_failure', () => {
    // Arrange
    const mockUser: UserResponse = { id: 'user-1', displayName: 'Admin', email: 'admin@test.com', role: 'ADMIN' };
    let error: AuthError | undefined;
    service.login({ email: 'a@b.com', password: 'p' }).subscribe();
    httpTesting.expectOne('/api/auth/login').flush(mockUser);

    // Act
    service.logout().subscribe({ error: (e) => (error = e) });
    httpTesting
      .expectOne('/api/auth/logout')
      .flush(null, { status: 500, statusText: 'Internal Server Error' });

    // Assert
    expect(error).toBeDefined();
    expect(error!.status).toBe(500);
    expect(service.isAuthenticated()).toBe(false);
  });

  it('check_session_sets_user_when_authenticated', () => {
    const mockUser: UserResponse = { id: 'user-1', displayName: 'Admin', email: 'admin@test.com', role: 'ADMIN' };

    service.checkSession().subscribe();

    const req = httpTesting.expectOne('/api/auth/me');
    req.flush(mockUser);

    expect(service.isAuthenticated()).toBe(true);
  });

  it('check_session_clears_user_on_401', () => {
    service.checkSession().subscribe();

    const req = httpTesting.expectOne('/api/auth/me');
    req.flush(null, { status: 401, statusText: 'Unauthorized' });

    expect(service.isAuthenticated()).toBe(false);
  });

  it('setup_does_not_set_current_user', () => {
    const mockUser: UserResponse = { id: 'user-1', displayName: 'Admin', email: 'admin@test.com', role: 'ADMIN' };

    service
      .setup({ email: 'admin@test.com', password: 'SecurePass123!', displayName: 'Admin' })
      .subscribe();

    const req = httpTesting.expectOne('/api/auth/setup');
    req.flush(mockUser);

    expect(service.isAuthenticated()).toBe(false);
  });

  it('check_status_returns_setup_complete', () => {
    let result: boolean | undefined;

    service.checkStatus().subscribe((status) => (result = status.setupComplete));

    const req = httpTesting.expectOne('/api/auth/status');
    req.flush({ setupComplete: true });

    expect(result).toBe(true);
  });

  it('login_returns_typed_auth_error_on_failure', () => {
    // Arrange
    let error: AuthError | undefined;

    // Act
    service
      .login({ email: 'bad@test.com', password: 'wrong' })
      .subscribe({ error: (e) => (error = e) });
    httpTesting
      .expectOne('/api/auth/login')
      .flush({ error: 'Identifiants invalides' }, { status: 401, statusText: 'Unauthorized' });

    // Assert
    expect(error).toBeDefined();
    expect(error!.status).toBe(401);
    expect(error!.message).toBe('Identifiants invalides');
    expect(service.isAuthenticated()).toBe(false);
  });

  it('setup_returns_typed_auth_error_on_conflict', () => {
    // Arrange
    let error: AuthError | undefined;

    // Act
    service
      .setup({ email: 'admin@test.com', password: 'SecurePass123!', displayName: 'Admin' })
      .subscribe({ error: (e) => (error = e) });
    httpTesting
      .expectOne('/api/auth/setup')
      .flush({ error: 'Admin already exists' }, { status: 409, statusText: 'Conflict' });

    // Assert
    expect(error).toBeDefined();
    expect(error!.status).toBe(409);
    expect(error!.message).toBe('Admin already exists');
  });
});
