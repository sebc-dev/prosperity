import { toTreeNodes } from './category.utils';
import { CategoryResponse } from './category.types';

const makeCategory = (partial: Partial<CategoryResponse> = {}): CategoryResponse => ({
  id: 'cat-1',
  name: 'Alimentation',
  parentId: null,
  parentName: null,
  system: true,
  plaidCategoryId: null,
  createdAt: '2026-01-01T00:00:00Z',
  ...partial,
});

describe('toTreeNodes', () => {
  it('empty_list_returns_empty_array', () => {
    // Act
    const result = toTreeNodes([]);

    // Assert
    expect(result).toEqual([]);
  });

  it('root_categories_without_children_become_leaf_nodes', () => {
    // Arrange
    const categories = [
      makeCategory({ id: 'cat-1', name: 'Transport', parentId: null }),
    ];

    // Act
    const result = toTreeNodes(categories);

    // Assert
    expect(result).toHaveLength(1);
    expect(result[0].label).toBe('Transport');
    expect(result[0].data).toBe('cat-1');
    expect(result[0].children).toEqual([]);
  });

  it('children_are_nested_under_matching_parent', () => {
    // Arrange
    const categories = [
      makeCategory({ id: 'root', name: 'Alimentation', parentId: null }),
      makeCategory({ id: 'child-1', name: 'Courses', parentId: 'root' }),
      makeCategory({ id: 'child-2', name: 'Restaurant', parentId: 'root' }),
    ];

    // Act
    const result = toTreeNodes(categories);

    // Assert
    expect(result).toHaveLength(1);
    expect(result[0].children).toHaveLength(2);
    expect(result[0].children![0].label).toBe('Courses');
    expect(result[0].children![1].label).toBe('Restaurant');
  });

  it('orphan_child_with_unknown_parentId_is_excluded_from_tree', () => {
    // Arrange
    const categories = [
      makeCategory({ id: 'child-orphan', name: 'Orphelin', parentId: 'nonexistent-parent' }),
    ];

    // Act
    const result = toTreeNodes(categories);

    // Assert
    expect(result).toEqual([]);
  });

  it('multiple_roots_each_get_their_own_children', () => {
    // Arrange
    const categories = [
      makeCategory({ id: 'root-a', name: 'Transport', parentId: null }),
      makeCategory({ id: 'root-b', name: 'Alimentation', parentId: null }),
      makeCategory({ id: 'child-a', name: 'Carburant', parentId: 'root-a' }),
      makeCategory({ id: 'child-b', name: 'Courses', parentId: 'root-b' }),
    ];

    // Act
    const result = toTreeNodes(categories);

    // Assert
    expect(result).toHaveLength(2);
    const transport = result.find((n) => n.label === 'Transport')!;
    const alim = result.find((n) => n.label === 'Alimentation')!;
    expect(transport.children).toHaveLength(1);
    expect(transport.children![0].label).toBe('Carburant');
    expect(alim.children).toHaveLength(1);
    expect(alim.children![0].label).toBe('Courses');
  });
});
