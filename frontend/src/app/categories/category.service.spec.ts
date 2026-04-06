import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { CategoryService } from './category.service';
import {
  CategoryResponse,
  CreateCategoryRequest,
  UpdateCategoryRequest,
} from './category.types';

const mockCategory: CategoryResponse = {
  id: 'cat-1',
  name: 'Alimentation',
  parentId: null,
  parentName: null,
  system: true,
  plaidCategoryId: 'FOOD_AND_DRINK',
  createdAt: '2026-01-01T00:00:00Z',
};

describe('CategoryService', () => {
  let service: CategoryService;
  let httpTesting: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(CategoryService);
    httpTesting = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpTesting.verify();
  });

  it('loadCategories_sends_get_request_to_api_categories', () => {
    // Act
    service.loadCategories().subscribe();

    // Assert
    const req = httpTesting.expectOne('/api/categories');
    expect(req.request.method).toBe('GET');
    req.flush([]);
  });

  it('loadCategories_updates_categories_signal_after_successful_response', () => {
    // Arrange
    const mockCategories = [mockCategory];

    // Act
    service.loadCategories().subscribe();
    const req = httpTesting.expectOne('/api/categories');
    req.flush(mockCategories);

    // Assert
    expect(service.categories()).toEqual(mockCategories);
  });

  it('createCategory_sends_post_request', () => {
    // Arrange
    const createRequest: CreateCategoryRequest = { name: 'Ma categorie', parentId: null };

    // Act
    service.createCategory(createRequest).subscribe();

    const req = httpTesting.expectOne('/api/categories');

    // Assert
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual(createRequest);
    req.flush(mockCategory);
  });

  it('updateCategory_sends_put_request', () => {
    // Arrange
    const updateRequest: UpdateCategoryRequest = { name: 'Nouveau nom' };

    // Act
    service.updateCategory('cat-1', updateRequest).subscribe();

    const req = httpTesting.expectOne('/api/categories/cat-1');

    // Assert
    expect(req.request.method).toBe('PUT');
    expect(req.request.body).toEqual(updateRequest);
    req.flush(mockCategory);
  });

  it('deleteCategory_sends_delete_request', () => {
    // Act
    service.deleteCategory('cat-1').subscribe();

    const req = httpTesting.expectOne('/api/categories/cat-1');

    // Assert
    expect(req.request.method).toBe('DELETE');
    req.flush(null);
  });
});
