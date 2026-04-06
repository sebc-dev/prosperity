import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { By } from '@angular/platform-browser';
import { Categories } from './categories';
import { CategoryResponse } from './category.types';

const makeCategory = (partial: Partial<CategoryResponse> = {}): CategoryResponse => ({
  id: 'cat-1',
  name: 'Alimentation',
  parentId: null,
  parentName: null,
  system: true,
  plaidCategoryId: 'FOOD_AND_DRINK',
  createdAt: '2026-01-01T00:00:00Z',
  ...partial,
});

describe('Categories', () => {
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Categories],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    }).compileComponents();

    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('renders_page_heading', () => {
    // Arrange
    const fixture = TestBed.createComponent(Categories);
    httpMock.expectOne('/api/categories').flush([]);
    fixture.detectChanges();

    // Assert
    const heading = fixture.debugElement.query(By.css('h1'));

    expect(heading.nativeElement.textContent.trim()).toBe('Categories');
  });

  it('renders_add_button', () => {
    // Arrange
    const fixture = TestBed.createComponent(Categories);
    httpMock.expectOne('/api/categories').flush([]);
    fixture.detectChanges();

    // Assert
    const button = fixture.debugElement.query(By.css('p-button[label="Ajouter une categorie"]'));

    expect(button).toBeTruthy();
  });

  it('displays_categories_in_table', () => {
    // Arrange
    const fixture = TestBed.createComponent(Categories);
    const categories = [
      makeCategory({ id: 'cat-1', name: 'Alimentation', system: true }),
      makeCategory({
        id: 'cat-2',
        name: 'Courses',
        parentId: 'cat-1',
        parentName: 'Alimentation',
        system: true,
      }),
    ];

    // Act
    httpMock.expectOne('/api/categories').flush(categories);
    fixture.detectChanges();

    // Assert
    const rows = fixture.debugElement.queryAll(By.css('tbody tr'));

    expect(rows.length).toBe(2);
  });

  it('shows_system_badge_for_system_categories', () => {
    // Arrange
    const fixture = TestBed.createComponent(Categories);

    // Act
    httpMock.expectOne('/api/categories').flush([makeCategory({ system: true })]);
    fixture.detectChanges();

    // Assert
    const tag = fixture.debugElement.query(By.css('p-tag[value="Systeme"]'));

    expect(tag).toBeTruthy();
  });

  it('hides_actions_for_system_categories', () => {
    // Arrange
    const fixture = TestBed.createComponent(Categories);

    // Act
    httpMock
      .expectOne('/api/categories')
      .flush([makeCategory({ name: 'Alimentation', system: true })]);
    fixture.detectChanges();

    // Assert
    const editBtn = fixture.debugElement.query(By.css('[aria-label="Modifier Alimentation"]'));
    const deleteBtn = fixture.debugElement.query(By.css('[aria-label="Supprimer Alimentation"]'));

    expect(editBtn).toBeNull();
    expect(deleteBtn).toBeNull();
  });

  it('shows_actions_for_custom_categories', () => {
    // Arrange
    const fixture = TestBed.createComponent(Categories);

    // Act
    httpMock
      .expectOne('/api/categories')
      .flush([makeCategory({ id: 'cat-99', name: 'Ma categorie', system: false })]);
    fixture.detectChanges();

    // Assert
    const editBtn = fixture.debugElement.query(By.css('[aria-label="Modifier Ma categorie"]'));
    const deleteBtn = fixture.debugElement.query(By.css('[aria-label="Supprimer Ma categorie"]'));

    expect(editBtn).toBeTruthy();
    expect(deleteBtn).toBeTruthy();
  });
});
