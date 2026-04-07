import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { By } from '@angular/platform-browser';
import { TransactionDialog } from './transaction-dialog';
import { TransactionResponse } from './transaction.types';

const makeTransaction = (partial: Partial<TransactionResponse> = {}): TransactionResponse => ({
  id: 'tx-1',
  accountId: 'acc-1',
  amount: -45.3,
  description: 'Courses Lidl',
  categoryId: null,
  categoryName: null,
  transactionDate: '2026-04-07',
  source: 'MANUAL',
  state: 'MANUAL_UNMATCHED',
  pointed: false,
  createdAt: '2026-04-07T00:00:00Z',
  splits: [],
  ...partial,
});

describe('TransactionDialog', () => {
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [TransactionDialog],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();

    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('should create the dialog', () => {
    // Arrange
    const fixture = TestBed.createComponent(TransactionDialog);
    fixture.componentRef.setInput('accountId', 'acc-1');
    fixture.componentRef.setInput('transaction', null);

    // Act
    fixture.detectChanges();

    // Assert
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('should show create heading when no transaction input', () => {
    // Arrange
    const fixture = TestBed.createComponent(TransactionDialog);
    fixture.componentRef.setInput('accountId', 'acc-1');
    fixture.componentRef.setInput('transaction', null);
    fixture.detectChanges();

    // Assert
    const dialog = fixture.debugElement.query(By.css('p-dialog'));
    expect(dialog.componentInstance.header).toBe('Ajouter une transaction');
  });

  it('should show edit heading when transaction is provided', () => {
    // Arrange
    const fixture = TestBed.createComponent(TransactionDialog);
    fixture.componentRef.setInput('accountId', 'acc-1');
    fixture.componentRef.setInput('transaction', makeTransaction());
    fixture.detectChanges();

    // Assert
    const dialog = fixture.debugElement.query(By.css('p-dialog'));
    expect(dialog.componentInstance.header).toBe('Modifier la transaction');
  });

  it('should pre-fill form in edit mode', () => {
    // Arrange
    const tx = makeTransaction({ amount: -45.3, description: 'Courses Lidl', transactionDate: '2026-04-07' });
    const fixture = TestBed.createComponent(TransactionDialog);
    fixture.componentRef.setInput('accountId', 'acc-1');
    fixture.componentRef.setInput('transaction', tx);
    fixture.detectChanges();

    // Assert
    expect(fixture.componentInstance['amount']).toBe(-45.3);
    expect(fixture.componentInstance['description']).toBe('Courses Lidl');
  });

  it('should disable save button when form invalid', () => {
    // Arrange
    const fixture = TestBed.createComponent(TransactionDialog);
    fixture.componentRef.setInput('accountId', 'acc-1');
    fixture.componentRef.setInput('transaction', null);
    fixture.detectChanges();

    // Ensure amount is null
    fixture.componentInstance['amount'] = null;
    fixture.detectChanges();

    // Assert
    const buttons = fixture.debugElement.queryAll(By.css('p-button'));
    const saveButton = buttons.find((b) =>
      b.componentInstance.label === 'Enregistrer' || b.componentInstance.label === 'Enregistrement...',
    );
    expect(saveButton).toBeTruthy();
    expect(saveButton!.componentInstance.disabled).toBe(true);
  });

  it('should emit saved on successful create', () => {
    // Arrange
    const fixture = TestBed.createComponent(TransactionDialog);
    fixture.componentRef.setInput('accountId', 'acc-1');
    fixture.componentRef.setInput('transaction', null);
    fixture.detectChanges();

    let savedEmitted = false;
    fixture.componentInstance.saved.subscribe(() => {
      savedEmitted = true;
    });

    fixture.componentInstance['amount'] = -45.3;
    fixture.componentInstance['transactionDate'] = new Date('2026-04-07');
    fixture.detectChanges();

    // Act
    fixture.componentInstance['save']();

    const req = httpMock.expectOne('/api/accounts/acc-1/transactions');
    expect(req.request.method).toBe('POST');
    req.flush(makeTransaction());
    fixture.detectChanges();

    // Assert
    expect(savedEmitted).toBe(true);
  });
});
