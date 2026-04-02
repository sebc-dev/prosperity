import {
  afterNextRender,
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  ElementRef,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Router } from '@angular/router';
import { ReactiveFormsModule, FormBuilder, Validators } from '@angular/forms';
import { AuthService } from './auth.service';
import { LoginRequest, AuthError } from './auth.types';
import { FloatLabel } from 'primeng/floatlabel';
import { InputText } from 'primeng/inputtext';
import { Password } from 'primeng/password';
import { Button } from 'primeng/button';
import { Message } from 'primeng/message';

@Component({
  selector: 'app-login',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, FloatLabel, InputText, Password, Button, Message],
  template: `
    <div class="min-h-screen flex items-center justify-center bg-surface-50">
      <div class="w-full max-w-md mx-auto p-8 rounded-xl shadow-md bg-surface-0">
        <div class="text-center mb-6">
          <h1 class="text-2xl font-semibold leading-tight">Connexion</h1>
          <p class="text-sm text-muted-color mt-2">Connectez-vous à votre espace Prosperity.</p>
        </div>

        <form [formGroup]="form" (ngSubmit)="onSubmit()" class="flex flex-col gap-4">
          <p-floatlabel variant="on">
            <input #emailInput id="email" pInputText formControlName="email" class="w-full" />
            <label for="email">Adresse email</label>
          </p-floatlabel>
          @if (form.get('email')?.touched && form.get('email')?.hasError('required')) {
            <small class="text-sm font-normal text-[--p-red-500]"
              >L'adresse email est requise</small
            >
          } @else if (form.get('email')?.touched && form.get('email')?.hasError('email')) {
            <small class="text-sm font-normal text-[--p-red-500]"
              >Format d'email invalide</small
            >
          }

          <p-floatlabel variant="on">
            <p-password
              id="password"
              formControlName="password"
              [toggleMask]="true"
              [feedback]="false"
              styleClass="w-full"
              inputStyleClass="w-full"
            />
            <label for="password">Mot de passe</label>
          </p-floatlabel>
          @if (form.get('password')?.touched && form.get('password')?.hasError('required')) {
            <small class="text-sm font-normal text-[--p-red-500]"
              >Le mot de passe est requis</small
            >
          }

          <p-button
            type="submit"
            [label]="loading() ? 'Connexion...' : 'Se connecter'"
            [loading]="loading()"
            [disabled]="form.invalid || loading()"
            severity="primary"
            styleClass="w-full mt-4"
          />
        </form>

        <div aria-live="polite" class="mt-4">
          @if (errorMessage()) {
            <p-message severity="error" [text]="errorMessage()!" styleClass="w-full" />
          }
        </div>
      </div>
    </div>
  `,
})
export class Login {
  private readonly fb = inject(FormBuilder);
  private readonly authService = inject(AuthService);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  private readonly emailInput = viewChild<ElementRef<HTMLInputElement>>('emailInput');

  constructor() {
    afterNextRender(() => this.emailInput()?.nativeElement.focus());
  }

  readonly loading = signal(false);
  readonly errorMessage = signal<string | null>(null);

  readonly form = this.fb.nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
    password: ['', [Validators.required]],
  });

  onSubmit(): void {
    if (this.form.invalid) return;

    this.loading.set(true);
    this.errorMessage.set(null);

    const request: LoginRequest = this.form.getRawValue();

    this.authService.login(request).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: () => {
        this.loading.set(false);
        this.router.navigate(['/dashboard']);
      },
      error: (err: AuthError) => {
        this.loading.set(false);
        if (err.status === 401) {
          this.errorMessage.set('Identifiants invalides');
        } else {
          this.errorMessage.set('Impossible de joindre le serveur. Vérifiez votre connexion.');
        }
      },
    });
  }
}
