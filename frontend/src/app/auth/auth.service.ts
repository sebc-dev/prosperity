import { Injectable, inject, signal, computed } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Observable, tap, catchError, of, throwError } from 'rxjs';
import { AuthError, LoginRequest, SetupRequest, StatusResponse, UserResponse } from './auth.types';

export type {
  AuthError,
  LoginRequest,
  SetupRequest,
  StatusResponse,
  UserResponse,
} from './auth.types';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private currentUser = signal<UserResponse | null>(null);

  private readonly http = inject(HttpClient);

  readonly isAuthenticated = computed(() => this.currentUser() !== null);
  readonly user = computed(() => this.currentUser());

  private mapError(err: HttpErrorResponse): Observable<never> {
    const authError: AuthError = {
      status: err.status,
      message: typeof err.error === 'string' ? err.error : (err.error?.error ?? err.statusText),
      original: err,
    };
    return throwError(() => authError);
  }

  checkSession(): Observable<UserResponse | null> {
    return this.http.get<UserResponse>('/api/auth/me').pipe(
      tap((user) => this.currentUser.set(user)),
      catchError(() => {
        this.currentUser.set(null);
        return of(null);
      }),
    );
  }

  checkStatus(): Observable<StatusResponse> {
    return this.http.get<StatusResponse>('/api/auth/status');
  }

  login(request: LoginRequest): Observable<UserResponse> {
    return this.http.post<UserResponse>('/api/auth/login', request).pipe(
      tap((user) => this.currentUser.set(user)),
      catchError((err) => this.mapError(err)),
    );
  }

  setup(request: SetupRequest): Observable<UserResponse> {
    return this.http
      .post<UserResponse>('/api/auth/setup', request)
      .pipe(catchError((err) => this.mapError(err)));
  }

  logout(): Observable<void> {
    return this.http.post<void>('/api/auth/logout', {}).pipe(
      tap(() => this.currentUser.set(null)),
      catchError((err) => {
        this.currentUser.set(null);
        return this.mapError(err);
      }),
    );
  }

  /** @internal Called exclusively by authInterceptor on 401 responses. Do not call from components. */
  clearUser(): void {
    this.currentUser.set(null);
  }
}
