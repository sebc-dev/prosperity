export type AccountType = 'PERSONAL' | 'SHARED';
export type AccessLevel = 'READ' | 'WRITE' | 'ADMIN';

export interface AccountResponse {
  id: string;
  name: string;
  accountType: AccountType;
  balance: number;
  currency: string;
  archived: boolean;
  createdAt: string;
  currentUserAccessLevel: AccessLevel;
}

export interface CreateAccountRequest {
  name: string;
  accountType: AccountType;
}

export interface UpdateAccountRequest {
  name?: string;
  accountType?: AccountType;
  archived?: boolean;
}

export interface AccountAccessResponse {
  id: string;
  userId: string;
  userEmail: string;
  userDisplayName: string;
  accessLevel: AccessLevel;
}

export interface SetAccessRequest {
  userId: string;
  accessLevel: AccessLevel;
}
