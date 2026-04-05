import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { By } from '@angular/platform-browser';
import { Accounts } from './accounts';

describe('Accounts', () => {
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Accounts],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();

    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('should create the component', () => {
    const fixture = TestBed.createComponent(Accounts);
    httpMock.expectOne('/api/accounts').flush([]);
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('should display page heading Comptes bancaires', () => {
    const fixture = TestBed.createComponent(Accounts);
    httpMock.expectOne('/api/accounts').flush([]);
    fixture.detectChanges();

    const heading = fixture.debugElement.query(By.css('h1'));
    expect(heading.nativeElement.textContent.trim()).toBe('Comptes bancaires');
  });

  it('should call loadAccounts on initialization', () => {
    TestBed.createComponent(Accounts);

    const req = httpMock.expectOne('/api/accounts');
    expect(req.request.method).toBe('GET');
    req.flush([]);
  });
});
