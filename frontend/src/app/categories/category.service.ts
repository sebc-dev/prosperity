import { Injectable, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, tap } from 'rxjs';
import { CategoryResponse, CreateCategoryRequest, UpdateCategoryRequest } from './category.types';

@Injectable({ providedIn: 'root' })
export class CategoryService {
  private readonly http = inject(HttpClient);
  private categoriesSignal = signal<CategoryResponse[]>([]);

  readonly categories = this.categoriesSignal.asReadonly();

  loadCategories(): Observable<CategoryResponse[]> {
    return this.http
      .get<CategoryResponse[]>('/api/categories')
      .pipe(tap((cats: CategoryResponse[]) => this.categoriesSignal.set(cats)));
  }

  /** Creates a new custom category. Does NOT update the categories signal — call loadCategories() after success. */
  createCategory(request: CreateCategoryRequest): Observable<CategoryResponse> {
    return this.http.post<CategoryResponse>('/api/categories', request);
  }

  /** Renames a category. Does NOT update the categories signal — call loadCategories() after success. */
  updateCategory(id: string, request: UpdateCategoryRequest): Observable<CategoryResponse> {
    return this.http.put<CategoryResponse>(`/api/categories/${id}`, request);
  }

  /** Deletes a category. Does NOT update the categories signal — call loadCategories() after success. */
  deleteCategory(id: string): Observable<void> {
    return this.http.delete<void>(`/api/categories/${id}`);
  }
}
