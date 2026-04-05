// Auth module type contracts. Application code (components, services) imports directly from this file. The auth.service barrel re-export is being removed.
import { HttpErrorResponse } from '@angular/common/http';

export type UserRole = 'ADMIN' | 'USER';

export interface UserResponse {
  id: string;
  displayName: string;
  email: string;
  role: UserRole;
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

export interface AuthError {
  status: number;
  message: string;
  original: HttpErrorResponse;
}
