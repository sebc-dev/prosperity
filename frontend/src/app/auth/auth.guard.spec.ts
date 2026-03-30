import { TestBed } from '@angular/core/testing';
import { ActivatedRouteSnapshot, RouterStateSnapshot, UrlTree } from '@angular/router';
import { provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { Observable } from 'rxjs';
import { authGuard, unauthenticatedGuard, setupGuard } from './auth.guard';
import { UserResponse } from './auth.service';

const MOCK_ROUTE = {} as ActivatedRouteSnapshot;
const MOCK_STATE = {} as RouterStateSnapshot;

function runGuard(guard: typeof authGuard): Observable<boolean | UrlTree> {
  let obs!: Observable<boolean | UrlTree>;
  TestBed.runInInjectionContext(() => {
    obs = guard(MOCK_ROUTE, MOCK_STATE) as Observable<boolean | UrlTree>;
  });
  return obs;
}

describe('Auth Guards', () => {
  let httpTesting: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideRouter([
          { path: 'login', redirectTo: '' },
          { path: 'dashboard', redirectTo: '' },
        ]),
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    });
    httpTesting = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpTesting.verify();
  });

  describe('authGuard', () => {
    it('allows_access_when_authenticated', () => {
      const mockUser: UserResponse = { displayName: 'Admin', email: 'admin@test.com', role: 'ADMIN' };
      let result: boolean | UrlTree | undefined;

      runGuard(authGuard).subscribe(r => result = r);

      httpTesting.expectOne('/api/auth/me').flush(mockUser);
      expect(result).toBe(true);
    });

    it('redirects_to_login_when_not_authenticated', () => {
      let result: boolean | UrlTree | undefined;

      runGuard(authGuard).subscribe(r => result = r);

      httpTesting.expectOne('/api/auth/me').flush(null, { status: 401, statusText: 'Unauthorized' });
      expect((result as UrlTree).toString()).toBe('/login');
    });
  });

  describe('unauthenticatedGuard', () => {
    it('allows_access_when_not_authenticated', () => {
      let result: boolean | UrlTree | undefined;

      runGuard(unauthenticatedGuard).subscribe(r => result = r);

      httpTesting.expectOne('/api/auth/me').flush(null, { status: 401, statusText: 'Unauthorized' });
      expect(result).toBe(true);
    });

    it('redirects_to_dashboard_when_authenticated', () => {
      const mockUser: UserResponse = { displayName: 'Admin', email: 'admin@test.com', role: 'ADMIN' };
      let result: boolean | UrlTree | undefined;

      runGuard(unauthenticatedGuard).subscribe(r => result = r);

      httpTesting.expectOne('/api/auth/me').flush(mockUser);
      expect((result as UrlTree).toString()).toBe('/dashboard');
    });
  });

  describe('setupGuard', () => {
    it('allows_access_when_setup_not_complete', () => {
      let result: boolean | UrlTree | undefined;

      runGuard(setupGuard).subscribe(r => result = r);

      httpTesting.expectOne('/api/auth/status').flush({ setupComplete: false });
      expect(result).toBe(true);
    });

    it('redirects_to_login_when_setup_complete', () => {
      let result: boolean | UrlTree | undefined;

      runGuard(setupGuard).subscribe(r => result = r);

      httpTesting.expectOne('/api/auth/status').flush({ setupComplete: true });
      expect((result as UrlTree).toString()).toBe('/login');
    });

    it('redirects_to_login_when_status_endpoint_errors', () => {
      let result: boolean | UrlTree | undefined;

      runGuard(setupGuard).subscribe(r => result = r);

      httpTesting.expectOne('/api/auth/status').flush(null, { status: 500, statusText: 'Internal Server Error' });
      expect((result as UrlTree).toString()).toBe('/login');
    });
  });
});
