import { ChangeDetectionStrategy, Component } from '@angular/core';
import { DrawerModule } from 'primeng/drawer';

@Component({
  selector: 'app-sidebar',
  standalone: true,
  imports: [DrawerModule],
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
      <div class="p-4 text-muted-color text-sm">Navigation a venir dans les prochaines phases.</div>
    </p-drawer>
  `,
})
export class Sidebar {
  visible = false;

  toggle(): void {
    this.visible = !this.visible;
  }
}
