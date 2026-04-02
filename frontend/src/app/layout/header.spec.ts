import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { NO_ERRORS_SCHEMA } from '@angular/core';
import { Subject } from 'rxjs';
import { Header } from './header';
import { AuthService } from '../auth/auth.service';

describe('Header', () => {
  let authService: AuthService;
  let router: Router;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [Header],
      providers: [
        provideRouter([]),
      ],
      schemas: [NO_ERRORS_SCHEMA],
    });
    authService = TestBed.inject(AuthService);
    router = TestBed.inject(Router);
  });

  it('sets_loggingOut_to_true_when_logout_is_initiated', () => {
    // Arrange
    const logout$ = new Subject<void>();
    vi.spyOn(authService, 'logout').mockReturnValue(logout$.asObservable());
    const fixture = TestBed.createComponent(Header);
    const component = fixture.componentInstance;

    // Act
    component.onLogout();

    // Assert
    expect(component.loggingOut()).toBe(true);
  });

  it('navigates_to_login_and_resets_loggingOut_on_successful_logout', () => {
    // Arrange
    const logout$ = new Subject<void>();
    vi.spyOn(authService, 'logout').mockReturnValue(logout$.asObservable());
    const navigateSpy = vi.spyOn(router, 'navigate').mockResolvedValue(true);
    const fixture = TestBed.createComponent(Header);
    const component = fixture.componentInstance;
    component.onLogout();

    // Act
    logout$.next();
    logout$.complete();

    // Assert
    expect(navigateSpy).toHaveBeenCalledWith(['/login']);
    expect(component.loggingOut()).toBe(false);
  });

  it('navigates_to_login_and_resets_loggingOut_on_logout_error', () => {
    // Arrange
    const logout$ = new Subject<void>();
    vi.spyOn(authService, 'logout').mockReturnValue(logout$.asObservable());
    const navigateSpy = vi.spyOn(router, 'navigate').mockResolvedValue(true);
    const fixture = TestBed.createComponent(Header);
    const component = fixture.componentInstance;
    component.onLogout();

    // Act
    logout$.error(new Error('network error'));

    // Assert
    expect(navigateSpy).toHaveBeenCalledWith(['/login']);
    expect(component.loggingOut()).toBe(false);
  });
});
