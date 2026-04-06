import { TreeNode } from 'primeng/api';
import { CategoryResponse } from './category.types';

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
