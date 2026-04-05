import { TreeNode } from 'primeng/api';

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

export function toTreeNodes(categories: CategoryResponse[]): TreeNode[] {
  const roots = categories.filter((c) => !c.parentId);
  return roots.map((root) => ({
    label: root.name,
    data: root.id,
    children: categories
      .filter((c) => c.parentId === root.id)
      .map((child) => ({ label: child.name, data: child.id })),
  }));
}
