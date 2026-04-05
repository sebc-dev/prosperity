import { ComponentFixture, TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { Dashboard } from './dashboard';
import { AuthService } from '../auth/auth.service';
import { UserResponse } from '../auth/auth.types';

class MockAuthService {
  user = signal<UserResponse | null>(null);
}

describe('Dashboard', () => {
  let fixture: ComponentFixture<Dashboard>;
  let mockAuthService: MockAuthService;

  beforeEach(async () => {
    mockAuthService = new MockAuthService();

    await TestBed.configureTestingModule({
      imports: [Dashboard],
      providers: [{ provide: AuthService, useValue: mockAuthService }],
    }).compileComponents();

    fixture = TestBed.createComponent(Dashboard);
  });

  it('displays_user_displayName_when_user_is_authenticated', () => {
    mockAuthService.user.set({
      id: 'user-1',
      displayName: 'Alice',
      email: 'a@b.com',
      role: 'USER',
    });

    fixture.detectChanges();

    const h1: HTMLElement = fixture.nativeElement.querySelector('h1');
    expect(h1.textContent).toContain('Alice');
  });

  it('renders_gracefully_when_user_is_null', () => {
    mockAuthService.user.set(null);

    expect(() => fixture.detectChanges()).not.toThrow();

    const h1: HTMLElement = fixture.nativeElement.querySelector('h1');
    expect(h1.textContent?.trim()).toBe('Bienvenue');
  });
});
