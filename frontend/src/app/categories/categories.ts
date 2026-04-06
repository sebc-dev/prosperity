import { ChangeDetectionStrategy, Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { TableModule } from 'primeng/table';
import { ButtonModule } from 'primeng/button';
import { TagModule } from 'primeng/tag';
import { ConfirmDialogModule } from 'primeng/confirmdialog';
import { MessageModule } from 'primeng/message';
import { TooltipModule } from 'primeng/tooltip';
import { ConfirmationService } from 'primeng/api';
import { CategoryService } from './category.service';
import { CategoryResponse } from './category.types';
import { CategoryDialog } from './category-dialog';
import { HttpErrorResponse } from '@angular/common/http';

@Component({
  selector: 'app-categories',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    TableModule,
    ButtonModule,
    TagModule,
    ConfirmDialogModule,
    MessageModule,
    TooltipModule,
    CategoryDialog,
  ],
  providers: [ConfirmationService],
  template: `
    <div class="p-8">
      <!-- Header row -->
      <div class="flex items-center justify-between mb-6">
        <h1 class="text-2xl font-semibold leading-tight">Categories</h1>
        <p-button label="Ajouter une categorie" icon="pi pi-plus" (onClick)="openCreateDialog()" />
      </div>

      <!-- Error message -->
      @if (error()) {
        <p-message severity="error" [text]="error()!" styleClass="mb-4 w-full" />
      }

      <!-- Empty state -->
      @if (!loading() && categories().length === 0) {
        <div role="status" class="text-center py-12">
          <h2 class="text-lg font-semibold mb-2">Aucune categorie</h2>
          <p class="text-muted-color mb-4">
            Les categories permettent de classer vos transactions. Ajoutez votre premiere categorie
            personnalisee.
          </p>
          <p-button
            label="Ajouter une categorie"
            icon="pi pi-plus"
            (onClick)="openCreateDialog()"
          />
        </div>
      }

      <!-- Table -->
      @if (categories().length > 0) {
        <p-table
          [value]="categories()"
          [stripedRows]="true"
          [sortField]="'name'"
          [sortOrder]="1"
          styleClass="p-datatable-sm"
        >
          <ng-template pTemplate="caption">
            <span class="sr-only">Liste des categories</span>
          </ng-template>
          <ng-template pTemplate="header">
            <tr>
              <th pSortableColumn="name" scope="col">Nom <p-sortIcon field="name" /></th>
              <th scope="col">Categorie parente</th>
              <th scope="col">Type</th>
              <th scope="col">Actions</th>
            </tr>
          </ng-template>
          <ng-template pTemplate="body" let-category>
            <tr>
              <td>{{ category.name }}</td>
              <td>{{ category.parentName ?? '\u2014' }}</td>
              <td>
                @if (category.system) {
                  <p-tag value="Systeme" severity="secondary" />
                } @else {
                  <p-tag value="Custom" severity="info" />
                }
              </td>
              <td>
                @if (!category.system) {
                  <div class="flex gap-1">
                    <p-button
                      icon="pi pi-pencil"
                      [text]="true"
                      severity="secondary"
                      [pTooltip]="'Modifier ' + category.name"
                      (onClick)="openEditDialog(category)"
                      [ariaLabel]="'Modifier ' + category.name"
                    />
                    <p-button
                      icon="pi pi-trash"
                      [text]="true"
                      severity="secondary"
                      [pTooltip]="'Supprimer ' + category.name"
                      (onClick)="confirmDelete(category)"
                      [ariaLabel]="'Supprimer ' + category.name"
                    />
                  </div>
                }
              </td>
            </tr>
          </ng-template>
        </p-table>
      }

      <!-- Confirm dialog -->
      <p-confirmdialog />

      <!-- Create/Edit dialog -->
      <app-category-dialog
        [visible]="dialogVisible()"
        [categoryToEdit]="editingCategory()"
        [allCategories]="categories()"
        (visibleChange)="dialogVisible.set($event)"
        (saved)="onDialogSaved()"
      />
    </div>
  `,
})
export class Categories {
  private readonly categoryService = inject(CategoryService);
  private readonly confirmationService = inject(ConfirmationService);
  private readonly destroyRef = inject(DestroyRef);

  protected loading = signal(true);
  protected error = signal<string | null>(null);

  protected categories = this.categoryService.categories;

  // Dialog state
  protected dialogVisible = signal(false);
  protected editingCategory = signal<CategoryResponse | null>(null);

  constructor() {
    this.loadData();
  }

  protected loadData(): void {
    this.loading.set(true);
    this.error.set(null);
    this.categoryService
      .loadCategories()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => this.loading.set(false),
        error: () => {
          this.loading.set(false);
          this.error.set(
            'Impossible de charger les categories. Verifiez votre connexion et reessayez.',
          );
        },
      });
  }

  protected openCreateDialog(): void {
    this.editingCategory.set(null);
    this.dialogVisible.set(true);
  }

  protected openEditDialog(category: CategoryResponse): void {
    this.editingCategory.set(category);
    this.dialogVisible.set(true);
  }

  protected onDialogSaved(): void {
    this.loadData();
  }

  protected confirmDelete(category: CategoryResponse): void {
    this.confirmationService.confirm({
      header: 'Supprimer la categorie',
      message: `Etes-vous sur de vouloir supprimer "${category.name}" ? Cette action est irreversible.`,
      acceptLabel: 'Supprimer',
      rejectLabel: 'Annuler',
      accept: () => {
        this.categoryService
          .deleteCategory(category.id)
          .pipe(takeUntilDestroyed(this.destroyRef))
          .subscribe({
            next: () => this.loadData(),
            error: (err: HttpErrorResponse) => {
              if (err.status === 409) {
                this.error.set(
                  err.error?.message ??
                    'Cette categorie est utilisee par des transactions et ne peut pas etre supprimee.',
                );
              } else {
                this.error.set('Impossible de supprimer la categorie. Veuillez reessayer.');
              }
            },
          });
      },
    });
  }
}
