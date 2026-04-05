import { ComponentFixture, TestBed } from '@angular/core/testing';
import { CategorySelector } from './category-selector';
import { TreeNode } from 'primeng/api';
import { Component, viewChild } from '@angular/core';

const mockOptions: TreeNode[] = [
  {
    label: 'Alimentation',
    data: 'cat-1',
    children: [{ label: 'Courses', data: 'cat-2' }],
  },
  { label: 'Transport', data: 'cat-3' },
];

@Component({
  standalone: true,
  imports: [CategorySelector],
  template: `<app-category-selector [options]="options" (categorySelected)="onSelected($event)" />`,
})
class TestHost {
  options: TreeNode[] = mockOptions;
  selectedId: string | null = null;
  selector = viewChild(CategorySelector);

  onSelected(id: string | null): void {
    this.selectedId = id;
  }
}

describe('CategorySelector', () => {
  let fixture: ComponentFixture<TestHost>;
  let host: TestHost;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [TestHost],
    }).compileComponents();

    fixture = TestBed.createComponent(TestHost);
    host = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('renders_treeselect_component', () => {
    // Assert
    const treeSelect = fixture.nativeElement.querySelector('p-treeselect');

    expect(treeSelect).toBeTruthy();
  });

  it('emits_category_id_on_select', () => {
    // Arrange
    const selector = host.selector()!;

    // Act
    selector.onSelect({ node: { label: 'Alimentation', data: 'cat-1' } });

    // Assert
    expect(host.selectedId).toBe('cat-1');
  });

  it('emits_null_on_clear', () => {
    // Arrange
    const selector = host.selector()!;
    selector.onSelect({ node: { label: 'Alimentation', data: 'cat-1' } });

    // Act
    selector.onClear();

    // Assert
    expect(host.selectedId).toBeNull();
  });
});
