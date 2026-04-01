import { ChangeDetectionStrategy, Component, DestroyRef, inject, OnInit, signal, computed } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Router } from '@angular/router';
import { ReactiveFormsModule, FormBuilder, Validators } from '@angular/forms';
import { AuthService, SetupRequest, AuthError } from './auth.service';
import { FloatLabel } from 'primeng/floatlabel';
import { InputText } from 'primeng/inputtext';
import { Password } from 'primeng/password';
import { Button } from 'primeng/button';
import { Message } from 'primeng/message';

@Component({
  selector: 'app-setup',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, FloatLabel, InputText, Password, Button, Message],
  template: `
    <div class="min-h-screen flex items-center justify-center bg-surface-50">
      <div class="w-full max-w-md mx-auto p-8 rounded-xl shadow-md bg-surface-0">
        <div class="text-center mb-6">
          <h1 class="text-2xl font-semibold leading-tight">Bienvenue sur Prosperity</h1>
          <p class="text-sm text-muted-color mt-2">Creez le compte administrateur pour demarrer.</p>
        </div>

        <form [formGroup]="form" (ngSubmit)="onSubmit()" class="flex flex-col gap-4">
          <p-floatlabel variant="on">
            <input id="email" pInputText formControlName="email" class="w-full" autofocus />
            <label for="email">Adresse email</label>
          </p-floatlabel>
          @if (form.get('email')?.touched && form.get('email')?.hasError('required')) {
            <small class="text-sm font-normal" style="color: var(--p-red-500)">L'adresse email est requise</small>
          } @else if (form.get('email')?.touched && form.get('email')?.hasError('email')) {
            <small class="text-sm font-normal" style="color: var(--p-red-500)">Format d'email invalide</small>
          }

          <p-floatlabel variant="on">
            <p-password id="password" formControlName="password" [toggleMask]="true" [feedback]="true" styleClass="w-full" inputStyleClass="w-full" />
            <label for="password">Mot de passe</label>
          </p-floatlabel>
          @if (form.get('password')?.touched && form.get('password')?.hasError('required')) {
            <small class="text-sm font-normal" style="color: var(--p-red-500)">Le mot de passe est requis</small>
          }

          <div class="flex flex-col gap-1">
            @for (rule of passwordRules(); track rule.label) {
              <div class="flex items-center gap-2 text-sm font-normal">
                @if (rule.met) {
                  <i class="pi pi-check" style="color: var(--p-green-500)"></i>
                } @else {
                  <i class="pi pi-times" style="color: var(--p-text-muted-color)"></i>
                }
                <span [style.color]="rule.met ? 'var(--p-green-500)' : 'var(--p-text-muted-color)'">{{ rule.label }}</span>
              </div>
            }
          </div>

          <p-floatlabel variant="on">
            <input id="displayName" pInputText formControlName="displayName" class="w-full" />
            <label for="displayName">Nom d'affichage</label>
          </p-floatlabel>
          @if (form.get('displayName')?.touched && form.get('displayName')?.hasError('required')) {
            <small class="text-sm font-normal" style="color: var(--p-red-500)">Le nom d'affichage est requis</small>
          } @else if (form.get('displayName')?.touched && form.get('displayName')?.hasError('minlength')) {
            <small class="text-sm font-normal" style="color: var(--p-red-500)">2 caracteres minimum</small>
          }

          <p-button
            type="submit"
            [label]="loading() ? 'Creation en cours...' : 'Creer le compte'"
            [loading]="loading()"
            [disabled]="form.invalid || loading() || !allPasswordRulesMet()"
            severity="primary"
            styleClass="w-full mt-4"
          />
        </form>

        <div aria-live="polite" class="mt-4">
          @if (successMessage()) {
            <p-message severity="success" [text]="successMessage()!" styleClass="w-full" />
          }
          @if (errorMessage()) {
            <p-message severity="error" [text]="errorMessage()!" styleClass="w-full" />
          }
        </div>
      </div>
    </div>
  `,
})
export class Setup implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly authService = inject(AuthService);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  readonly loading = signal(false);
  readonly successMessage = signal<string | null>(null);
  readonly errorMessage = signal<string | null>(null);
  private redirectTimer?: ReturnType<typeof setTimeout>;

  readonly form = this.fb.nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
    password: ['', [Validators.required]],
    displayName: ['', [Validators.required, Validators.minLength(2)]],
  });

  private readonly password = signal('');

  readonly passwordRules = computed(() => {
    const pwd = this.password();
    return [
      { label: '12 caracteres minimum', met: pwd.length >= 12 },
      { label: '1 lettre majuscule', met: /[A-Z]/.test(pwd) },
      { label: '1 chiffre', met: /\d/.test(pwd) },
      { label: '1 caractere special', met: /[^a-zA-Z0-9]/.test(pwd) },
    ];
  });

  readonly allPasswordRulesMet = computed(() => this.passwordRules().every((r) => r.met));

  ngOnInit(): void {
    this.destroyRef.onDestroy(() => {
      if (this.redirectTimer) clearTimeout(this.redirectTimer);
    });

    this.form.get('password')?.valueChanges.pipe(
      takeUntilDestroyed(this.destroyRef),
    ).subscribe((value: string | null) => {
      this.password.set(value ?? '');
    });
  }

  onSubmit(): void {
    if (this.form.invalid || !this.allPasswordRulesMet()) return;

    this.loading.set(true);
    this.successMessage.set(null);
    this.errorMessage.set(null);

    const request: SetupRequest = this.form.getRawValue();

    this.authService.setup(request).subscribe({
      next: () => {
        this.loading.set(false);
        this.successMessage.set('Compte cree avec succes. Vous pouvez maintenant vous connecter.');
        this.redirectTimer = setTimeout(() => this.router.navigate(['/login']), 2000);
      },
      error: (err: AuthError) => {
        this.loading.set(false);
        if (err.status === 409) {
          this.errorMessage.set('Le compte administrateur existe deja. Rendez-vous sur la page de connexion.');
        } else {
          this.errorMessage.set('Impossible de joindre le serveur. Verifiez votre connexion.');
        }
      },
    });
  }
}
