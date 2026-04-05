import { TestBed } from '@angular/core/testing';
import { provideHttpClient, withInterceptors, HttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { provideRouter, Router } from '@angular/router';
import { authInterceptor } from './auth.interceptor';
import { AuthService } from './auth.service';
import { UserResponse } from './auth.types';

describe('authInterceptor', () => {
  let httpClient: HttpClient;
  let httpTesting: HttpTestingController;
  let authService: AuthService;
  let router: Router;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideRouter([{ path: 'login', redirectTo: '' }]),
        provideHttpClient(withInterceptors([authInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    httpClient = TestBed.inject(HttpClient);
    httpTesting = TestBed.inject(HttpTestingController);
    authService = TestBed.inject(AuthService);
    router = TestBed.inject(Router);
  });

  afterEach(() => {
    httpTesting.verify();
  });

  function loginFirst(): void {
    const mockUser: UserResponse = { id: 'user-1', displayName: 'Admin', email: 'admin@test.com', role: 'ADMIN' };
    authService.login({ email: 'admin@test.com', password: 'pass' }).subscribe();
    httpTesting.expectOne('/api/auth/login').flush(mockUser);
  }

  // eslint-disable-next-line @typescript-eslint/no-empty-function
  const noop = () => {};

  it('clears_user_on_401_for_api_routes', () => {
    // Arrange
    loginFirst();
    // Precondition: verify loginFirst() successfully authenticated the user
    expect(authService.isAuthenticated()).toBe(true);
    const navigateSpy = vi
      .spyOn(router, 'navigate')
      .mockImplementation(() => Promise.resolve(true));

    // Act
    httpClient.get('/api/data').subscribe({ error: noop });
    httpTesting.expectOne('/api/data').flush(null, { status: 401, statusText: 'Unauthorized' });

    // Assert
    expect(authService.isAuthenticated()).toBe(false);
    expect(navigateSpy).toHaveBeenCalledWith(['/login']);
  });

  it('does_not_clear_user_on_401_for_auth_me', () => {
    // Arrange
    loginFirst();

    // Act
    httpClient.get('/api/auth/me').subscribe({ error: noop });
    httpTesting.expectOne('/api/auth/me').flush(null, { status: 401, statusText: 'Unauthorized' });

    // Assert
    expect(authService.isAuthenticated()).toBe(true);
  });

  it('does_not_clear_user_on_401_for_auth_status', () => {
    // Arrange
    loginFirst();

    // Act
    httpClient.get('/api/auth/status').subscribe({ error: noop });
    httpTesting
      .expectOne('/api/auth/status')
      .flush(null, { status: 401, statusText: 'Unauthorized' });

    // Assert
    expect(authService.isAuthenticated()).toBe(true);
  });

  it('does_not_clear_user_on_non_401_errors', () => {
    // Arrange
    loginFirst();

    // Act
    httpClient.get('/api/data').subscribe({ error: noop });
    httpTesting
      .expectOne('/api/data')
      .flush(null, { status: 500, statusText: 'Internal Server Error' });

    // Assert
    expect(authService.isAuthenticated()).toBe(true);
  });

  it('does_not_clear_user_on_401_for_external_urls', () => {
    // Arrange
    loginFirst();

    // Act
    httpClient.get('https://external.com/api').subscribe({ error: noop });
    httpTesting
      .expectOne('https://external.com/api')
      .flush(null, { status: 401, statusText: 'Unauthorized' });

    // Assert
    expect(authService.isAuthenticated()).toBe(true);
  });
});
