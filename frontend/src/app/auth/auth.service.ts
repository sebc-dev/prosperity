import { Injectable, signal, computed } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, tap, catchError, of } from 'rxjs';

export interface UserResponse {
  displayName: string;
  email: string;
  role: string;
}

export interface SetupRequest {
  email: string;
  password: string;
  displayName: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface StatusResponse {
  setupComplete: boolean;
}

@Injectable({ providedIn: 'root' })
export class AuthService {
  private currentUser = signal<UserResponse | null>(null);

  readonly isAuthenticated = computed(() => this.currentUser() !== null);
  readonly user = computed(() => this.currentUser());

  constructor(private http: HttpClient) {}

  checkSession(): Observable<UserResponse | null> {
    return this.http.get<UserResponse>('/api/auth/me').pipe(
      tap(user => this.currentUser.set(user)),
      catchError(() => {
        this.currentUser.set(null);
        return of(null);
      })
    );
  }

  checkStatus(): Observable<StatusResponse> {
    return this.http.get<StatusResponse>('/api/auth/status');
  }

  login(request: LoginRequest): Observable<UserResponse> {
    return this.http.post<UserResponse>('/api/auth/login', request).pipe(
      tap(user => this.currentUser.set(user))
    );
  }

  setup(request: SetupRequest): Observable<UserResponse> {
    return this.http.post<UserResponse>('/api/auth/setup', request);
  }

  logout(): Observable<void> {
    return this.http.post<void>('/api/auth/logout', {}).pipe(
      tap(() => this.currentUser.set(null))
    );
  }

  clearUser(): void {
    this.currentUser.set(null);
  }
}
