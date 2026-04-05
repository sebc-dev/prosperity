import { TestBed } from '@angular/core/testing';
import { provideHttpClient, HttpErrorResponse } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter, Router } from '@angular/router';
import { of, throwError } from 'rxjs';
import { Setup } from './setup';
import { AuthService } from './auth.service';
import { AuthError } from './auth.types';

describe('Setup', () => {
  let component: Setup;
  let authService: AuthService;
  let router: Router;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Setup],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    }).compileComponents();

    const fixture = TestBed.createComponent(Setup);
    component = fixture.componentInstance;
    authService = TestBed.inject(AuthService);
    router = TestBed.inject(Router);
    fixture.detectChanges();
  });

  it('submit_is_blocked_when_password_rules_are_not_met', () => {
    // Arrange
    const setupSpy = vi.spyOn(authService, 'setup');
    component.form.setValue({ email: 'admin@test.com', password: '', displayName: '' });

    // Act
    component.onSubmit();

    // Assert
    expect(setupSpy).not.toHaveBeenCalled();
  });

  it('onSubmit_calls_authService_setup_with_form_raw_value', () => {
    // Arrange
    const mockUser = { id: 'user-1', displayName: 'Admin', email: 'admin@test.com', role: 'ADMIN' as const };
    const setupSpy = vi.spyOn(authService, 'setup').mockReturnValue(of(mockUser));
    const validPassword = 'Secure123!pass';
    component.form.setValue({
      email: 'admin@test.com',
      password: validPassword,
      displayName: 'Admin',
    });

    // Act
    component.onSubmit();

    // Assert
    expect(setupSpy).toHaveBeenCalledWith({
      email: 'admin@test.com',
      password: validPassword,
      displayName: 'Admin',
    });
  });

  it('shows_success_message_and_navigates_after_delay_on_success', async () => {
    // Arrange
    vi.useFakeTimers();
    const mockUser = { id: 'user-1', displayName: 'Admin', email: 'admin@test.com', role: 'ADMIN' as const };
    vi.spyOn(authService, 'setup').mockReturnValue(of(mockUser));
    const navigateSpy = vi
      .spyOn(router, 'navigate')
      .mockImplementation(() => Promise.resolve(true));
    component.form.setValue({
      email: 'admin@test.com',
      password: 'Secure123!pass',
      displayName: 'Admin',
    });

    // Act
    component.onSubmit();
    await vi.runAllTimersAsync();

    // Assert
    expect(component.successMessage()).toBeTruthy();
    expect(navigateSpy).toHaveBeenCalledWith(['/login']);
    vi.useRealTimers();
  });

  it('shows_conflict_error_message_when_status_is_409', () => {
    // Arrange
    const authError: AuthError = {
      status: 409,
      message: 'Admin already exists',
      original: new HttpErrorResponse({ status: 409 }),
    };
    vi.spyOn(authService, 'setup').mockReturnValue(throwError(() => authError));
    component.form.setValue({
      email: 'admin@test.com',
      password: 'Secure123!pass',
      displayName: 'Admin',
    });

    // Act
    component.onSubmit();

    // Assert
    expect(component.errorMessage()).toContain('existe');
  });

  it('shows_generic_error_message_on_server_failure', () => {
    // Arrange
    const authError: AuthError = {
      status: 500,
      message: 'Internal Server Error',
      original: new HttpErrorResponse({ status: 500 }),
    };
    vi.spyOn(authService, 'setup').mockReturnValue(throwError(() => authError));
    component.form.setValue({
      email: 'admin@test.com',
      password: 'Secure123!pass',
      displayName: 'Admin',
    });

    // Act
    component.onSubmit();

    // Assert
    expect(component.errorMessage()).toContain('Impossible');
  });
});
