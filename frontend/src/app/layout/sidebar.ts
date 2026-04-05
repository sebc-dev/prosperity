import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { DrawerModule } from 'primeng/drawer';

@Component({
  selector: 'app-sidebar',
  imports: [DrawerModule, RouterLink, RouterLinkActive],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <p-drawer
      [(visible)]="visible"
      [modal]="false"
      [dismissible]="true"
      styleClass="w-64"
      aria-label="Menu de navigation"
    >
      <ng-template pTemplate="header">
        <span class="text-lg font-semibold">Menu</span>
      </ng-template>
      <nav class="flex flex-col gap-1 p-2">
        <a
          routerLink="/accounts"
          routerLinkActive="bg-surface-100 text-primary font-semibold border-l-3 border-primary"
          class="flex items-center gap-3 px-3 py-2 rounded-md text-muted-color hover:bg-surface-50 transition-colors"
          (click)="visible = false"
        >
          <i class="pi pi-wallet"></i>
          <span>Comptes</span>
        </a>
      </nav>
    </p-drawer>
  `,
})
export class Sidebar {
  protected visible = false;

  toggle(): void {
    this.visible = !this.visible;
  }
}
