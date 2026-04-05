import { ChangeDetectionStrategy, Component } from '@angular/core';

@Component({
  selector: 'app-accounts',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<div class="p-8"><h1 class="text-2xl font-semibold">Comptes bancaires</h1></div>`,
})
export class Accounts {}
