import { HttpErrorResponse } from '@angular/common/http';

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

export interface AuthError {
  status: number;
  message: string;
  original: HttpErrorResponse;
}
