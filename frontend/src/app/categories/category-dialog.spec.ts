import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { CategoryDialog } from './category-dialog';
import { CategoryResponse } from './category.types';

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
    const component = fixture.componentInstance;

    expect(component['dialogHeader']()).toBe('Ajouter une categorie');
  });

  it('renders_edit_heading_when_category_provided', () => {
    // Arrange
    const category: CategoryResponse = {
      id: 'cat-1',
      name: 'Ma categorie',
      parentId: null,
      parentName: null,
      system: false,
      plaidCategoryId: null,
      createdAt: '2026-01-01T00:00:00Z',
    };

    const fixture = TestBed.createComponent(CategoryDialog);
    fixture.componentRef.setInput('categoryToEdit', category);
    fixture.detectChanges();

    // Assert
    const component = fixture.componentInstance;

    expect(component['dialogHeader']()).toBe('Modifier la categorie');
  });

  it('disables_save_when_name_empty', () => {
    // Arrange
    const fixture = TestBed.createComponent(CategoryDialog);
    fixture.componentRef.setInput('visible', true);
    fixture.componentRef.setInput('categoryToEdit', null);
    fixture.detectChanges();

    // Act
    const form = fixture.componentInstance['form'];
    form.controls.name.setValue('');
    fixture.detectChanges();

    // Assert
    expect(form.invalid).toBe(true);
  });
});
