import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { ActivatedRoute } from '@angular/router';
import { of } from 'rxjs';
import { By } from '@angular/platform-browser';
import { Transactions } from './transactions';
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

const emptyPage = { content: [], totalElements: 0, totalPages: 0, number: 0, size: 20 };
const mockAccounts = [
  {
    id: 'acc-1',
    name: 'Compte Courant',
    accountType: 'PERSONAL' as const,
    balance: 0,
    currency: 'EUR',
    archived: false,
    createdAt: '2026-01-01T00:00:00Z',
    currentUserAccessLevel: 'WRITE' as const,
  },
];

describe('Transactions', () => {
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Transactions],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        {
          provide: ActivatedRoute,
          useValue: {
            params: of({ accountId: 'acc-1' }),
          },
        },
      ],
    }).compileComponents();

    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  /**
   * Creates the component, flushes the initial HTTP requests triggered by constructor
   * and by p-table onLazyLoad, then runs change detection.
   * The p-table does NOT fire onLazyLoad in jsdom because it uses virtual scroll detection;
   * we call loadTransactions manually and flush it.
   */
  function createAndInit(txPage = emptyPage) {
    const fixture = TestBed.createComponent(Transactions);
    // Constructor triggers /api/categories and /api/accounts
    httpMock.expectOne('/api/categories').flush([]);
    httpMock.expectOne('/api/accounts').flush(mockAccounts);
    fixture.detectChanges();
    // Manually trigger loadTransactions to simulate p-table onLazyLoad
    fixture.componentInstance['loadTransactions']({ first: 0, rows: 20 });
    const txReqs = httpMock.match((r) => r.url === '/api/accounts/acc-1/transactions');
    txReqs.forEach((r) => r.flush(txPage));
    fixture.detectChanges();
    return fixture;
  }

  it('should create the component', () => {
    // Arrange & Act
    const fixture = createAndInit();

    // Assert
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('should display page heading with account name', () => {
    // Arrange & Act
    const fixture = createAndInit();

    // Assert
    const heading = fixture.debugElement.query(By.css('h1'));
    expect(heading.nativeElement.textContent).toContain('Compte Courant');
  });

  it('should call getTransactions on lazy load', () => {
    // Arrange
    const fixture = createAndInit();

    // Act — trigger a page change
    fixture.componentInstance['loadTransactions']({ first: 20, rows: 20 });

    // Assert
    const reqs = httpMock.match(
      (r) => r.url === '/api/accounts/acc-1/transactions' && r.method === 'GET',
    );
    expect(reqs.length).toBeGreaterThan(0);
    const pageReq = reqs.find((r) => r.request.params.get('page') === '1');
    expect(pageReq).toBeTruthy();
    reqs.forEach((r) => r.flush({ content: [], totalElements: 0, totalPages: 0, number: 0, size: 20 }));
  });

  it('should show empty state when no transactions', () => {
    // Arrange & Act
    const fixture = createAndInit(emptyPage);

    // Assert
    const emptyState = fixture.debugElement.query(By.css('[role="status"]'));
    expect(emptyState).toBeTruthy();
    expect(emptyState.nativeElement.textContent).toContain('Aucune transaction');
  });
});
