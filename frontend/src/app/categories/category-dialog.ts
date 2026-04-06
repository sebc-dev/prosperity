import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ReactiveFormsModule, FormBuilder, Validators } from '@angular/forms';
import { DialogModule } from 'primeng/dialog';
import { FloatLabelModule } from 'primeng/floatlabel';
import { InputTextModule } from 'primeng/inputtext';
import { ButtonModule } from 'primeng/button';
import { MessageModule } from 'primeng/message';
import { TreeNode } from 'primeng/api';
import { HttpErrorResponse } from '@angular/common/http';
import { CategoryService } from './category.service';
import { CategoryResponse } from './category.types';
import { CategorySelector } from '../shared/category-selector';

@Component({
  selector: 'app-category-dialog',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    ReactiveFormsModule,
    DialogModule,
    FloatLabelModule,
    InputTextModule,
    ButtonModule,
    MessageModule,
    CategorySelector,
  ],
  template: `
    <p-dialog
      [header]="dialogHeader()"
      [visible]="visible()"
      (onHide)="onHide()"
      [modal]="true"
      [closable]="true"
      [draggable]="false"
      styleClass="max-w-lg w-full"
    >
      <form [formGroup]="form" (ngSubmit)="onSave()" class="flex flex-col gap-4 p-6">
        <p-floatlabel variant="on">
          <input
            pInputText
            id="categoryName"
            formControlName="name"
            class="w-full"
            maxlength="100"
          />
          <label for="categoryName">Nom de la categorie</label>
        </p-floatlabel>
        @if (form.controls.name.touched && form.controls.name.errors) {
          @if (form.controls.name.errors['required']) {
            <small class="text-red-500">Le nom de la categorie est requis</small>
          }
          @if (form.controls.name.errors['maxlength']) {
            <small class="text-red-500">Le nom ne peut pas depasser 100 caracteres</small>
          }
        }

        @if (!isEdit()) {
          <app-category-selector
            [options]="parentOptions()"
            placeholder="Categorie parente (optionnel)"
            (categorySelected)="onParentSelected($event)"
          />
        }

        @if (error()) {
          <p-message severity="error" [text]="error()!" />
        }
      </form>

      <ng-template pTemplate="footer">
        <div class="flex justify-end gap-2">
          <p-button label="Annuler" [text]="true" severity="secondary" (onClick)="onHide()" />
          <p-button
            [label]="loading() ? 'Enregistrement...' : 'Enregistrer'"
            [loading]="loading()"
            [disabled]="form.invalid || loading()"
            (onClick)="onSave()"
          />
        </div>
      </ng-template>
    </p-dialog>
  `,
})
export class CategoryDialog {
  visible = input(false);
  categoryToEdit = input<CategoryResponse | null>(null);
  allCategories = input<CategoryResponse[]>([]);

  visibleChange = output<boolean>();
  /** Emitted after a successful create or update. Callers must refresh their data source (e.g. call loadCategories()). */
  saved = output<void>();

  private readonly categoryService = inject(CategoryService);
  private readonly fb = inject(FormBuilder);
  private readonly destroyRef = inject(DestroyRef);

  protected form = this.fb.group({
    name: ['', [Validators.required, Validators.maxLength(100)]],
  });

  protected loading = signal(false);
  protected error = signal<string | null>(null);
  protected selectedParentId = signal<string | null>(null);

  protected isEdit = computed(() => this.categoryToEdit() !== null);
  protected dialogHeader = computed(() =>
    this.isEdit() ? 'Modifier la categorie' : 'Ajouter une categorie',
  );

  /** Only root-level categories as selectable parents (depth constraint: max 2 levels) */
  protected parentOptions = computed<TreeNode[]>(() => {
    return this.allCategories()
      .filter((c) => !c.parentId)
      .map((c) => ({ label: c.name, data: c.id }));
  });

  constructor() {
    effect(() => {
      const isVisible = this.visible();
      const cat = this.categoryToEdit();
      if (isVisible && cat) {
        this.form.patchValue({ name: cat.name });
        this.selectedParentId.set(cat.parentId);
      } else if (!isVisible || !cat) {
        this.form.reset({ name: '' });
        this.selectedParentId.set(null);
      }
      this.error.set(null);
    });
  }

  protected onParentSelected(parentId: string | null): void {
    this.selectedParentId.set(parentId);
  }

  protected onSave(): void {
    if (this.form.invalid) return;
    this.loading.set(true);
    this.error.set(null);

    const { name } = this.form.getRawValue();
    const cat = this.categoryToEdit();

    const request$ = cat
      ? this.categoryService.updateCategory(cat.id, { name: name! })
      : this.categoryService.createCategory({
          name: name!,
          parentId: this.selectedParentId(),
        });

    request$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: () => {
        this.loading.set(false);
        this.visibleChange.emit(false);
        this.saved.emit();
      },
      error: (err: HttpErrorResponse) => {
        this.loading.set(false);
        if (err.status === 409) {
          this.error.set(err.error?.message ?? 'Une categorie avec ce nom existe deja.');
        } else {
          this.error.set("Impossible d'enregistrer la categorie. Veuillez reessayer.");
        }
      },
    });
  }

  protected onHide(): void {
    this.visibleChange.emit(false);
  }
}
