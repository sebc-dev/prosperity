import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TreeSelectModule } from 'primeng/treeselect';
import { TreeNode } from 'primeng/api';

@Component({
  selector: 'app-category-selector',
  standalone: true,
  imports: [TreeSelectModule, FormsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <p-treeselect
      [options]="options()"
      [(ngModel)]="selectedNode"
      [filter]="true"
      [showClear]="true"
      selectionMode="single"
      [placeholder]="placeholder()"
      appendTo="body"
      (onNodeSelect)="onSelect($event)"
      (onClear)="onClear()"
      styleClass="w-full"
    />
  `,
})
export class CategorySelector {
  options = input.required<TreeNode[]>();
  placeholder = input('Categorie parente (optionnel)');
  categorySelected = output<string | null>();

  protected selectedNode: TreeNode | null = null;

  onSelect(event: { node: TreeNode }): void {
    this.categorySelected.emit(event.node.data as string);
  }

  onClear(): void {
    this.selectedNode = null;
    this.categorySelected.emit(null);
  }

  /** Call this from parent to programmatically set selection (e.g., edit mode) */
  setSelection(node: TreeNode | null): void {
    this.selectedNode = node;
  }
}
