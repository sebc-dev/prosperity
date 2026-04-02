import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { AuthService } from '../auth/auth.service';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="max-w-2xl">
      <h1 class="text-2xl font-semibold leading-tight mb-2">Bienvenue {{ user()?.displayName }}</h1>
      <p class="text-muted-color">
        Votre espace est pret. Les fonctionnalites arrivent dans les prochaines phases.
      </p>
    </div>
  `,
})
export class Dashboard {
  protected readonly user = inject(AuthService).user;
}
