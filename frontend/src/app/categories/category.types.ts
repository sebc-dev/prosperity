export interface CategoryResponse {
  id: string;
  name: string;
  parentId: string | null;
  parentName: string | null;
  system: boolean;
  plaidCategoryId: string | null;
  createdAt: string;
}

export interface CreateCategoryRequest {
  name: string;
  parentId: string | null;
}

export interface UpdateCategoryRequest {
  name: string;
}
