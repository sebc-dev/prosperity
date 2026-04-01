import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { Router } from '@angular/router';
import { AuthService } from '../auth/auth.service';
import { ButtonModule } from 'primeng/button';

@Component({
  selector: 'app-header',
  standalone: true,
  imports: [ButtonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <header
      class="h-16 flex items-center justify-between px-6 bg-surface-0 border-b border-surface-200"
    >
      <span class="text-lg font-semibold">Prosperity</span>
      <p-button
        label="Deconnexion"
        [text]="true"
        severity="secondary"
        (onClick)="onLogout()"
        [loading]="loggingOut"
      />
    </header>
  `,
})
export class Header {
  private readonly authService = inject(AuthService);
  private readonly router = inject(Router);
  loggingOut = false;

  onLogout(): void {
    this.loggingOut = true;
    this.authService.logout().subscribe({
      next: () => this.router.navigate(['/login']),
      error: () => {
        this.loggingOut = false;
        this.router.navigate(['/login']);
      },
    });
  }
}
