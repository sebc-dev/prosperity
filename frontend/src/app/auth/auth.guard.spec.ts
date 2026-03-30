import { TestBed } from '@angular/core/testing';
import { Router, UrlTree } from '@angular/router';
import { provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { authGuard, unauthenticatedGuard, noAdminGuard } from './auth.guard';
import { UserResponse } from './auth.service';

describe('Auth Guards', () => {
  let httpTesting: HttpTestingController;
  let router: Router;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideRouter([
          { path: 'login', component: class {} as any },
          { path: 'dashboard', component: class {} as any },
        ]),
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    });
    httpTesting = TestBed.inject(HttpTestingController);
    router = TestBed.inject(Router);
  });

  afterEach(() => {
    httpTesting.verify();
  });

  describe('authGuard', () => {
    it('allows_access_when_authenticated', () => {
      const mockUser: UserResponse = { displayName: 'Admin', email: 'admin@test.com', role: 'ADMIN' };
      let result: boolean | UrlTree | undefined;

      TestBed.runInInjectionContext(() => {
        (authGuard({} as any, {} as any) as any).subscribe((r: any) => result = r);
      });

      httpTesting.expectOne('/api/auth/me').flush(mockUser);
      expect(result).toBe(true);
    });

    it('redirects_to_login_when_not_authenticated', () => {
      let result: boolean | UrlTree | undefined;

      TestBed.runInInjectionContext(() => {
        (authGuard({} as any, {} as any) as any).subscribe((r: any) => result = r);
      });

      httpTesting.expectOne('/api/auth/me').flush(null, { status: 401, statusText: 'Unauthorized' });
      expect(result instanceof UrlTree).toBe(true);
      expect((result as UrlTree).toString()).toBe('/login');
    });
  });

  describe('unauthenticatedGuard', () => {
    it('allows_access_when_not_authenticated', () => {
      let result: boolean | UrlTree | undefined;

      TestBed.runInInjectionContext(() => {
        (unauthenticatedGuard({} as any, {} as any) as any).subscribe((r: any) => result = r);
      });

      httpTesting.expectOne('/api/auth/me').flush(null, { status: 401, statusText: 'Unauthorized' });
      expect(result).toBe(true);
    });

    it('redirects_to_dashboard_when_authenticated', () => {
      const mockUser: UserResponse = { displayName: 'Admin', email: 'admin@test.com', role: 'ADMIN' };
      let result: boolean | UrlTree | undefined;

      TestBed.runInInjectionContext(() => {
        (unauthenticatedGuard({} as any, {} as any) as any).subscribe((r: any) => result = r);
      });

      httpTesting.expectOne('/api/auth/me').flush(mockUser);
      expect(result instanceof UrlTree).toBe(true);
      expect((result as UrlTree).toString()).toBe('/dashboard');
    });
  });

  describe('noAdminGuard', () => {
    it('allows_access_when_setup_not_complete', () => {
      let result: boolean | UrlTree | undefined;

      TestBed.runInInjectionContext(() => {
        (noAdminGuard({} as any, {} as any) as any).subscribe((r: any) => result = r);
      });

      httpTesting.expectOne('/api/auth/status').flush({ setupComplete: false });
      expect(result).toBe(true);
    });

    it('redirects_to_login_when_setup_complete', () => {
      let result: boolean | UrlTree | undefined;

      TestBed.runInInjectionContext(() => {
        (noAdminGuard({} as any, {} as any) as any).subscribe((r: any) => result = r);
      });

      httpTesting.expectOne('/api/auth/status').flush({ setupComplete: true });
      expect(result instanceof UrlTree).toBe(true);
      expect((result as UrlTree).toString()).toBe('/login');
    });
  });
});
