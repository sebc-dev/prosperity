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

  createCategory(request: CreateCategoryRequest): Observable<CategoryResponse> {
    return this.http.post<CategoryResponse>('/api/categories', request);
  }

  updateCategory(id: string, request: UpdateCategoryRequest): Observable<CategoryResponse> {
    return this.http.put<CategoryResponse>(`/api/categories/${id}`, request);
  }

  deleteCategory(id: string): Observable<void> {
    return this.http.delete<void>(`/api/categories/${id}`);
  }
}
