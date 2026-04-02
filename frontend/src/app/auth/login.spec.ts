import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { of, throwError } from 'rxjs';
import { Login } from './login';
import { AuthService } from './auth.service';
import { AuthError, UserResponse } from './auth.types';
import { HttpErrorResponse } from '@angular/common/http';

const MOCK_USER: UserResponse = { displayName: 'Admin', email: 'admin@test.com', role: 'ADMIN' };

function makeAuthError(status: number): AuthError {
  return {
    status,
    message: 'error',
    original: new HttpErrorResponse({ status }),
  };
}

describe('Login', () => {
  let authService: AuthService;
  let router: Router;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [Login],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    });
    authService = TestBed.inject(AuthService);
    router = TestBed.inject(Router);
  });

  it('navigates_to_dashboard_on_successful_login', () => {
    // Arrange
    vi.spyOn(authService, 'login').mockReturnValue(of(MOCK_USER));
    const navigateSpy = vi.spyOn(router, 'navigate').mockResolvedValue(true);
    const fixture = TestBed.createComponent(Login);
    fixture.componentInstance.form.setValue({ email: 'admin@test.com', password: 'pass' });

    // Act
    fixture.componentInstance.onSubmit();

    // Assert
    expect(navigateSpy).toHaveBeenCalledWith(['/dashboard']);
  });

  it('shows_invalid_credentials_message_on_401_error', () => {
    // Arrange
    vi.spyOn(authService, 'login').mockReturnValue(throwError(() => makeAuthError(401)));
    const fixture = TestBed.createComponent(Login);
    fixture.componentInstance.form.setValue({ email: 'admin@test.com', password: 'wrong' });

    // Act
    fixture.componentInstance.onSubmit();

    // Assert
    expect(fixture.componentInstance.errorMessage()).toContain('Identifiants');
  });

  it('shows_connection_error_on_non_401_error', () => {
    // Arrange
    vi.spyOn(authService, 'login').mockReturnValue(throwError(() => makeAuthError(500)));
    const fixture = TestBed.createComponent(Login);
    fixture.componentInstance.form.setValue({ email: 'admin@test.com', password: 'pass' });

    // Act
    fixture.componentInstance.onSubmit();

    // Assert
    expect(fixture.componentInstance.errorMessage()).toContain('Impossible');
  });

  it('does_not_call_login_service_when_form_is_invalid', () => {
    // Arrange
    const loginSpy = vi.spyOn(authService, 'login');
    const fixture = TestBed.createComponent(Login);
    // form left empty — invalid state

    // Act
    fixture.componentInstance.onSubmit();

    // Assert
    expect(loginSpy).not.toHaveBeenCalled();
  });
});
