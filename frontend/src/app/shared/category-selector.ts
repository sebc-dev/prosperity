import {
  ChangeDetectionStrategy,
  Component,
  effect,
  input,
  output,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TreeSelectModule } from 'primeng/treeselect';
import { TreeNode } from 'primeng/api';

type SelectionMode = 'single' | 'checkbox';

@Component({
  selector: 'app-category-selector',
  imports: [TreeSelectModule, FormsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (selectionMode() === 'single') {
      <p-treeselect
        [options]="options()"
        [(ngModel)]="selectedNode"
        [filter]="true"
        [showClear]="true"
        selectionMode="single"
        [placeholder]="placeholder()"
        appendTo="body"
        (onNodeSelect)="onSingleSelect($event)"
        (onClear)="onSingleClear()"
        styleClass="w-full"
      />
    } @else {
      <p-treeselect
        [options]="options()"
        [(ngModel)]="selectedNodes"
        [filter]="true"
        [showClear]="true"
        selectionMode="checkbox"
        display="chip"
        [placeholder]="placeholder()"
        appendTo="body"
        [metaKeySelection]="false"
        (onNodeSelect)="onCheckboxChange()"
        (onNodeUnselect)="onCheckboxChange()"
        (onClear)="onCheckboxClear()"
        styleClass="w-full"
      />
    }
  `,
})
export class CategorySelector {
  options = input.required<TreeNode[]>();
  placeholder = input('Categorie parente (optionnel)');
  selectionMode = input<SelectionMode>('single');
  /** Pre-fill selection in checkbox mode (UUID list). Ignored in single mode. */
  selectedIds = input<string[]>([]);

  // Single-mode existing API (unchanged)
  categorySelected = output<string | null>();

  // Checkbox-mode new API
  categoriesSelected = output<string[]>();

  private readonly _selectedNode = signal<TreeNode | null>(null);
  private readonly _selectedNodes = signal<TreeNode[]>([]);

  constructor() {
    // When parent updates selectedIds + options, reflect into the internal multi-selection signal.
    effect(() => {
      if (this.selectionMode() !== 'checkbox') return;
      const ids = new Set(this.selectedIds());
      const flat = this.flatten(this.options());
      this._selectedNodes.set(flat.filter((n) => ids.has(n.data as string)));
    });
  }

  // Single-mode getter/setter for [(ngModel)]
  get selectedNode(): TreeNode | null {
    return this._selectedNode();
  }
  set selectedNode(value: TreeNode | null) {
    this._selectedNode.set(value);
  }

  // Checkbox-mode getter/setter for [(ngModel)]
  get selectedNodes(): TreeNode[] {
    return this._selectedNodes();
  }
  set selectedNodes(value: TreeNode[]) {
    this._selectedNodes.set(value ?? []);
  }

  onSingleSelect(event: { node: TreeNode }): void {
    this.categorySelected.emit(event.node.data as string);
  }

  onSingleClear(): void {
    this._selectedNode.set(null);
    this.categorySelected.emit(null);
  }

  onCheckboxChange(): void {
    const ids = this._selectedNodes().map((n) => n.data as string);
    this.categoriesSelected.emit(ids);
  }

  onCheckboxClear(): void {
    this._selectedNodes.set([]);
    this.categoriesSelected.emit([]);
  }

  /** Programmatically sets the single-mode selection (e.g. edit mode). Triggers change detection via signal. */
  setSelection(node: TreeNode | null): void {
    this._selectedNode.set(node);
  }

  private flatten(nodes: TreeNode[]): TreeNode[] {
    const out: TreeNode[] = [];
    const walk = (list: TreeNode[]) => {
      for (const n of list) {
        out.push(n);
        if (n.children?.length) walk(n.children);
      }
    };
    walk(nodes);
    return out;
  }
}
