import { ChangeDetectionStrategy, Component, input, output, signal } from '@angular/core';
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

  private readonly _selectedNode = signal<TreeNode | null>(null);

  /** Getter/setter wrapping the signal for [(ngModel)] compatibility with PrimeNG p-treeselect. */
  get selectedNode(): TreeNode | null {
    return this._selectedNode();
  }
  set selectedNode(value: TreeNode | null) {
    this._selectedNode.set(value);
  }

  onSelect(event: { node: TreeNode }): void {
    this.categorySelected.emit(event.node.data as string);
  }

  onClear(): void {
    this._selectedNode.set(null);
    this.categorySelected.emit(null);
  }

  /** Programmatically sets the selection (e.g. edit mode). Triggers change detection via signal. */
  setSelection(node: TreeNode | null): void {
    this._selectedNode.set(node);
  }
}
