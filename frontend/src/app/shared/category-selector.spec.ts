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

  it('passes_options_to_selector', () => {
    // Assert
    const selector = host.selector()!;

    expect(selector.options()).toEqual(mockOptions);
  });

  it('emits_category_id_on_select', () => {
    // Arrange
    const selector = host.selector()!;

    // Act
    selector.onSingleSelect({ node: { label: 'Alimentation', data: 'cat-1' } });

    // Assert
    expect(host.selectedId).toBe('cat-1');
  });

  it('emits_null_on_clear', () => {
    // Arrange
    const selector = host.selector()!;
    selector.onSingleSelect({ node: { label: 'Alimentation', data: 'cat-1' } });

    // Act
    selector.onSingleClear();

    // Assert
    expect(host.selectedId).toBeNull();
  });
});

describe('CategorySelector checkbox mode', () => {
  function sampleOptions(): TreeNode[] {
    return [
      {
        label: 'Alimentation',
        data: 'cat-root',
        children: [
          { label: 'Courses', data: 'cat-courses' },
          { label: 'Restaurant', data: 'cat-resto' },
        ],
      },
    ];
  }

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [CategorySelector],
    }).compileComponents();
  });

  it('emits_empty_array_on_checkbox_clear', () => {
    // Arrange
    const fixture = TestBed.createComponent(CategorySelector);
    fixture.componentRef.setInput('options', sampleOptions());
    fixture.componentRef.setInput('selectionMode', 'checkbox');
    fixture.componentRef.setInput('selectedIds', []);
    fixture.detectChanges();
    const emitted: string[][] = [];
    fixture.componentInstance.categoriesSelected.subscribe((ids) => emitted.push(ids));

    // Act
    fixture.componentInstance.onCheckboxClear();

    // Assert
    expect(emitted).toEqual([[]]);
  });

  it('emits_selected_ids_array_on_checkbox_change', () => {
    // Arrange
    const fixture = TestBed.createComponent(CategorySelector);
    const opts = sampleOptions();
    fixture.componentRef.setInput('options', opts);
    fixture.componentRef.setInput('selectionMode', 'checkbox');
    fixture.componentRef.setInput('selectedIds', []);
    fixture.detectChanges();
    const emitted: string[][] = [];
    fixture.componentInstance.categoriesSelected.subscribe((ids) => emitted.push(ids));
    fixture.componentInstance.selectedNodes = [opts[0], opts[0].children![0]];

    // Act
    fixture.componentInstance.onCheckboxChange();

    // Assert
    expect(emitted).toEqual([[opts[0].data, opts[0].children![0].data]]);
  });

  it('preserves_single_mode_when_selection_mode_omitted', () => {
    // Arrange
    const fixture = TestBed.createComponent(CategorySelector);
    fixture.componentRef.setInput('options', sampleOptions());
    fixture.detectChanges();
    const emitted: (string | null)[] = [];
    fixture.componentInstance.categorySelected.subscribe((id) => emitted.push(id));

    // Act
    fixture.componentInstance.onSingleSelect({ node: sampleOptions()[0] });

    // Assert
    expect(emitted).toEqual([sampleOptions()[0].data]);
  });
});
