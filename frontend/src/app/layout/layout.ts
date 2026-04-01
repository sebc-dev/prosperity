import { ChangeDetectionStrategy, Component, viewChild } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { Header } from './header';
import { Sidebar } from './sidebar';

@Component({
  selector: 'app-layout',
  standalone: true,
  imports: [RouterOutlet, Header, Sidebar],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="min-h-screen flex flex-col">
      <app-header />
      <div class="flex flex-1">
        <app-sidebar #sidebar />
        <main class="flex-1 p-6">
          <router-outlet />
        </main>
      </div>
    </div>
  `,
})
export class Layout {
  readonly sidebar = viewChild<Sidebar>('sidebar');
}
