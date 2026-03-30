import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { AuthService } from './auth.service';
import { catchError, throwError } from 'rxjs';

const AUTH_CHECK_URLS = ['/api/auth/me', '/api/auth/status'];
const isAuthCheckUrl = (url: string): boolean => AUTH_CHECK_URLS.some(u => url.includes(u));

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const router = inject(Router);
  const authService = inject(AuthService);

  return next(req).pipe(
    catchError((error: HttpErrorResponse) => {
      if (error.status === 401 && req.url.startsWith('/api/') && !isAuthCheckUrl(req.url)) {
        authService.clearUser();
        router.navigate(['/login']);
      }
      return throwError(() => error);
    })
  );
};
