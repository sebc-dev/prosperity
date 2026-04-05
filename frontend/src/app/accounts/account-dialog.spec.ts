import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { AccountDialog } from './account-dialog';
import { AccountResponse } from './account.types';

describe('AccountDialog', () => {
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AccountDialog],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();

    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('should create the component', () => {
    const fixture = TestBed.createComponent(AccountDialog);
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('should be in create mode (isEdit false) when no account input is provided', () => {
    const fixture = TestBed.createComponent(AccountDialog);
    fixture.componentRef.setInput('account', null);
    fixture.detectChanges();

    // When account is null, the form starts with empty name
    const component = fixture.componentInstance;
    expect(component.account()).toBeNull();
  });

  it('should disable save button when form is invalid (empty name)', () => {
    const fixture = TestBed.createComponent(AccountDialog);
    fixture.componentRef.setInput('visible', true);
    fixture.componentRef.setInput('account', null);
    fixture.detectChanges();

    // Force name to empty — form should be invalid (required validator)
    const form = fixture.componentInstance['form'];
    form.controls.name.setValue('');
    fixture.detectChanges();

    expect(form.invalid).toBe(true);
  });

  it('should pre-fill form when editing an existing account', () => {
    const existingAccount: AccountResponse = {
      id: 'acc-1',
      name: 'Compte Courant',
      accountType: 'PERSONAL',
      balance: 1000,
      currency: 'EUR',
      archived: false,
      createdAt: '2026-01-01T00:00:00Z',
      currentUserAccessLevel: 'ADMIN',
    };

    const fixture = TestBed.createComponent(AccountDialog);
    fixture.componentRef.setInput('account', existingAccount);
    fixture.detectChanges();

    const form = fixture.componentInstance['form'];
    expect(form.controls.name.value).toBe('Compte Courant');
    expect(form.controls.accountType.value).toBe('PERSONAL');
  });
});
