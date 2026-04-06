import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { By } from '@angular/platform-browser';
import { CategoryDialog } from './category-dialog';
import { CategoryResponse } from './category.types';

const makeCategory = (partial: Partial<CategoryResponse> = {}): CategoryResponse => ({
  id: 'cat-1',
  name: 'Ma categorie',
  parentId: null,
  parentName: null,
  system: false,
  plaidCategoryId: null,
  createdAt: '2026-01-01T00:00:00Z',
  ...partial,
});

describe('CategoryDialog', () => {
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [CategoryDialog],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();

    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('renders_create_heading_when_no_category', () => {
    // Arrange
    const fixture = TestBed.createComponent(CategoryDialog);
    fixture.componentRef.setInput('categoryToEdit', null);
    fixture.detectChanges();

    // Assert
    const dialog = fixture.debugElement.query(By.css('p-dialog'));
    expect(dialog.componentInstance.header).toBe('Ajouter une categorie');
  });

  it('renders_edit_heading_when_category_provided', () => {
    // Arrange
    const fixture = TestBed.createComponent(CategoryDialog);
    fixture.componentRef.setInput('categoryToEdit', makeCategory());
    fixture.detectChanges();

    // Assert
    const dialog = fixture.debugElement.query(By.css('p-dialog'));
    expect(dialog.componentInstance.header).toBe('Modifier la categorie');
  });

  it('disables_save_when_name_empty', () => {
    // Arrange
    const fixture = TestBed.createComponent(CategoryDialog);
    fixture.componentRef.setInput('visible', true);
    fixture.componentRef.setInput('categoryToEdit', null);
    fixture.detectChanges();

    // Act
    const nameInput = fixture.debugElement.query(By.css('#categoryName'));
    nameInput.nativeElement.value = '';
    nameInput.nativeElement.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    // Assert
    const buttons = fixture.debugElement.queryAll(By.css('p-button'));
    const saveButton = buttons.find((b) => b.componentInstance.label === 'Enregistrer');
    expect(saveButton).toBeTruthy();
    expect(saveButton!.componentInstance.disabled).toBe(true);
  });

  it('create_success_emits_saved_and_closes_dialog', () => {
    // Arrange
    const fixture = TestBed.createComponent(CategoryDialog);
    fixture.componentRef.setInput('visible', true);
    fixture.componentRef.setInput('categoryToEdit', null);
    fixture.componentRef.setInput('allCategories', []);
    fixture.detectChanges();

    const savedSpy = jasmine.createSpy('saved');
    const visibleChangeSpy = jasmine.createSpy('visibleChange');
    fixture.componentInstance.saved.subscribe(savedSpy);
    fixture.componentInstance.visibleChange.subscribe(visibleChangeSpy);

    const nameInput = fixture.debugElement.query(By.css('#categoryName'));
    nameInput.nativeElement.value = 'Nouvelle categorie';
    nameInput.nativeElement.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    // Act
    fixture.componentInstance['onSave']();

    const req = httpMock.expectOne('/api/categories');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ name: 'Nouvelle categorie', parentId: null });
    req.flush(makeCategory({ name: 'Nouvelle categorie' }));
    fixture.detectChanges();

    // Assert
    expect(savedSpy).toHaveBeenCalled();
    expect(visibleChangeSpy).toHaveBeenCalledWith(false);
  });

  it('update_success_sends_put_with_category_id', () => {
    // Arrange
    const category = makeCategory({ id: 'cat-42', name: 'Ancien nom' });
    const fixture = TestBed.createComponent(CategoryDialog);
    fixture.componentRef.setInput('visible', true);
    fixture.componentRef.setInput('categoryToEdit', category);
    fixture.detectChanges();

    const nameInput = fixture.debugElement.query(By.css('#categoryName'));
    nameInput.nativeElement.value = 'Nouveau nom';
    nameInput.nativeElement.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    // Act
    fixture.componentInstance['onSave']();

    // Assert
    const req = httpMock.expectOne('/api/categories/cat-42');
    expect(req.request.method).toBe('PUT');
    expect(req.request.body).toEqual({ name: 'Nouveau nom' });
    req.flush(makeCategory({ id: 'cat-42', name: 'Nouveau nom' }));
  });

  it('save_shows_conflict_error_when_api_returns_409', () => {
    // Arrange
    const fixture = TestBed.createComponent(CategoryDialog);
    fixture.componentRef.setInput('visible', true);
    fixture.componentRef.setInput('categoryToEdit', null);
    fixture.detectChanges();

    const nameInput = fixture.debugElement.query(By.css('#categoryName'));
    nameInput.nativeElement.value = 'Doublon';
    nameInput.nativeElement.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    // Act
    fixture.componentInstance['onSave']();
    httpMock.expectOne('/api/categories').flush(
      { error: 'Une categorie avec ce nom existe deja' },
      { status: 409, statusText: 'Conflict' },
    );
    fixture.detectChanges();

    // Assert
    const errorMsg = fixture.debugElement.query(By.css('p-message'));
    expect(errorMsg).toBeTruthy();
  });

  it('save_shows_generic_error_when_api_returns_500', () => {
    // Arrange
    const fixture = TestBed.createComponent(CategoryDialog);
    fixture.componentRef.setInput('visible', true);
    fixture.componentRef.setInput('categoryToEdit', null);
    fixture.detectChanges();

    const nameInput = fixture.debugElement.query(By.css('#categoryName'));
    nameInput.nativeElement.value = 'Test';
    nameInput.nativeElement.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    // Act
    fixture.componentInstance['onSave']();
    httpMock.expectOne('/api/categories').flush(
      {},
      { status: 500, statusText: 'Internal Server Error' },
    );
    fixture.detectChanges();

    // Assert
    const errorMsg = fixture.debugElement.query(By.css('p-message'));
    expect(errorMsg).toBeTruthy();
  });
});
